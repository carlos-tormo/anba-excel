import base64
import os
import sqlite3
import tempfile
import unittest

from app.server import LeagueDB, _spreadsheet_rows_from_payload, _xlsx_workbook_bytes
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> None:
    now = now_iso()
    conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, now, now),
    )


class FreeAgentAgentImportTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-fa-agent-import-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        first_id = self.db.create_free_agent(
            {
                "name": "Nikola Jokic",
                "position": "C",
                "rating": "98",
                "free_agent_type": "No restringido",
            }
        )
        second_id = self.db.create_free_agent(
            {
                "name": "Jrue Holiday",
                "position": "PG",
                "rating": "81",
                "free_agent_type": "No restringido",
                "agent": "Old Rep",
            }
        )
        self.assertIsNotNone(first_id)
        self.assertIsNotNone(second_id)
        self.first_id = int(first_id)
        self.second_id = int(second_id)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_preview_and_apply_free_agent_agent_import(self) -> None:
        rows = [
            ["player", "agent"],
            ["Nikola Jokic", "New Rep"],
            ["Jrue Holiday", "Old Rep"],
        ]

        preview = self.db.preview_free_agent_agent_import(rows)

        self.assertTrue(preview["ok"])
        self.assertEqual([], preview["errors"])
        self.assertEqual(2, preview["summary"]["record_count"])
        self.assertEqual(1, preview["summary"]["changed_count"])
        self.assertEqual(["New Rep", "Old Rep"], preview["new_agents"])

        result = self.db.apply_free_agent_agent_import(preview["records"])

        self.assertEqual(2, result["record_count"])
        self.assertEqual(1, result["changed_count"])
        self.assertEqual(1, result["unchanged_count"])
        free_agents = {item["id"]: item for item in self.db.list_free_agents()}
        self.assertEqual("New Rep", free_agents[self.first_id]["agent"])
        self.assertEqual("Old Rep", free_agents[self.second_id]["agent"])
        settings = self.db.get_settings()
        self.assertIn("New Rep", settings.get("free_agent_reps", ""))
        self.assertIn("Old Rep", settings.get("free_agent_reps", ""))

    def test_xlsx_payload_rows_are_supported(self) -> None:
        data = _xlsx_workbook_bytes(
            [
                {
                    "name": "Agents",
                    "rows": [
                        ["player", "agent"],
                        ["Nikola Jokic", "XLSX Rep"],
                    ],
                }
            ]
        )
        rows = _spreadsheet_rows_from_payload(
            file_name="agents.xlsx",
            file_data_base64=base64.b64encode(data).decode("ascii"),
        )

        preview = self.db.preview_free_agent_agent_import(rows)

        self.assertTrue(preview["ok"])
        self.assertEqual(1, preview["summary"]["record_count"])
        self.assertEqual("XLSX Rep", preview["records"][0]["agent_name"])

    def test_preview_reports_missing_and_ambiguous_names(self) -> None:
        duplicate_id = self.db.create_free_agent({"name": "Nikola Jokic"})
        self.assertIsNotNone(duplicate_id)

        preview = self.db.preview_free_agent_agent_import(
            [
                ["player", "agent"],
                ["Nikola Jokic", "Rep"],
                ["Missing Player", "Rep"],
            ]
        )

        messages = [error["message"] for error in preview["errors"]]
        self.assertFalse(preview["ok"])
        self.assertTrue(any("Nombre ambiguo" in message for message in messages))
        self.assertTrue(any("No se encontró agente libre" in message for message in messages))

    def test_free_agency_mode_adds_expiring_contract_without_cap_hold_marker_to_free_agents(self) -> None:
        self.db.update_setting("current_year", "2026")
        self.db.update_setting("free_agency_mode", "1")
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Expiring Contract",
                "position": "SG",
                "rating": "74",
                "bird_rights": "Reg",
                "salary_2025_text": "10000000",
                "salary_2026_text": "",
                "option_2026": "",
            },
        )
        self.assertIsNotNone(player_id)

        free_agents = self.db.list_free_agents()
        expiring = next((agent for agent in free_agents if agent["name"] == "Expiring Contract"), None)

        self.assertIsNotNone(expiring)
        self.assertEqual("No restringido", expiring["free_agent_type"])
        self.assertEqual("cap_hold", expiring["source"])
        self.assertIsNone(expiring["rights_team_code"])
        self.assertIsNone(expiring["bird_rights"])
        self.assertIn("Contrato expirado", expiring["notes"])

    def test_uncontracted_profile_is_synced_as_free_agent_without_bird_rights(self) -> None:
        timestamp = now_iso()
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO player_profiles (name, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                ("Loose Profile", timestamp, timestamp),
            )
            profile_id = int(cur.lastrowid)
            conn.commit()

        players = self.db.list_players()
        profile = next(item for item in players if int(item["profile_id"]) == profile_id)
        free_agents = self.db.list_free_agents()
        free_agent = next(item for item in free_agents if int(item["profile_id"]) == profile_id)

        self.assertEqual("free_agent", profile["status"])
        self.assertEqual("Agente libre", profile["status_label"])
        self.assertEqual("No restringido", free_agent["free_agent_type"])
        self.assertEqual("uncontracted_profile", free_agent["source"])
        self.assertIsNone(free_agent["rights_team_code"])
        self.assertIsNone(free_agent["bird_rights"])

    def test_current_year_bird_marker_profile_status_preserves_retained_rights(self) -> None:
        self.db.update_setting("current_year", "2026")
        self.db.update_setting("free_agency_mode", "1")
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Bird Rights Guard",
                "position": "PG",
                "rating": "77",
                "bird_rights": "Reg",
                "years_left": "2+",
                "salary_2025_text": "10000000",
                "salary_2026_text": "FB",
                "option_2026": "",
            },
        )
        self.assertIsNotNone(player_id)

        players = self.db.list_players()
        profile = next(item for item in players if item["name"] == "Bird Rights Guard")
        free_agents = self.db.list_free_agents()
        free_agent = next(item for item in free_agents if item["name"] == "Bird Rights Guard")

        self.assertEqual("free_agent", profile["status"])
        self.assertEqual("Agente libre · derechos ATL", profile["status_label"])
        self.assertFalse(profile["active_contract"])
        self.assertEqual("FB", profile["bird_rights"])
        self.assertEqual("ATL", profile["rights_team_code"])
        self.assertEqual("cap_hold", free_agent["source"])
        self.assertEqual("ATL", free_agent["rights_team_code"])
        self.assertEqual("FB", free_agent["bird_rights"])


if __name__ == "__main__":
    unittest.main()
