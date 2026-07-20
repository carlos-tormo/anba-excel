import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
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


class OwnerAdminImportTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-owner-admin-import-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with connect_test_db(path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            conn.commit()
        self.db = LeagueDB(path)
        self.db.ensure_auth_schema()

    def tearDown(self) -> None:
        os.unlink(self.db_path)

    def test_economy_preview_and_apply_use_service_rules_and_repository_writes(self) -> None:
        csv_text = "\n".join(
            (
                "season,team,section,key,value",
                "2025,ATL,economy,revenue,100",
                "2025,ATL,economy,expenses,40",
            )
        )
        preview = self.db.preview_owner_economy_csv(csv_text)
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["summary"][0]["revenue"], 100.0)
        self.assertEqual(preview["summary"][0]["expenses"], -40.0)

        result = self.db.apply_owner_economy_import(preview["records"])
        self.assertTrue(result["ok"])
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT e.revenue, e.expenses, e.balance, o.revenue AS owner_revenue
                FROM team_economy e
                JOIN teams t ON t.id = e.team_id
                JOIN team_owner_office o
                  ON o.team_id = e.team_id AND o.season_year = e.season_year
                WHERE t.code = 'ATL' AND e.season_year = 2025
                """
            ).fetchone()
        self.assertEqual((row["revenue"], row["expenses"], row["balance"]), (100.0, -40.0, 60.0))
        self.assertEqual(row["owner_revenue"], "100")

    def test_owner_office_apply_preserves_economy_fields(self) -> None:
        economy = self.db.preview_owner_economy_csv(
            "season,team,section,key,value\n2025,ATL,economy,revenue,125"
        )
        self.db.apply_owner_economy_import(economy["records"])

        preview = self.db.preview_owner_office_csv(
            "season,team,confidence_current,season_goal_set\n"
            "2025,ATL,Alta,Primera ronda"
        )
        self.assertTrue(preview["ok"])
        result = self.db.apply_owner_office_import(preview["records"])
        self.assertTrue(result["ok"])
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT confidence_current, season_goal_set, revenue
                FROM team_owner_office o
                JOIN teams t ON t.id = o.team_id
                WHERE t.code = 'ATL' AND o.season_year = 2025
                """
            ).fetchone()
        self.assertEqual(row["confidence_current"], "Alta")
        self.assertEqual(row["season_goal_set"], "Primera ronda")
        self.assertEqual(row["revenue"], "125")

    def test_owner_office_aggregate_update_and_read(self) -> None:
        updated = self.db.update_team_owner_office(
            "ATL",
            {
                "season_year": 2025,
                "confidence_current": "7",
                "season_goal_set": "Primera ronda",
                "revenue": "150",
                "expenses": "-50",
                "balance": "100",
                "owner_profile": {
                    "owner_name": "Jane Owner",
                    "owner_photo_url": "https://example.com/owner.png",
                    "attributes": {"paciencia": 8},
                },
            },
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["owner_profile"]["owner_name"], "Jane Owner")
        self.assertEqual(updated["owner_profile"]["attributes"]["paciencia"], 8)
        entry = updated["entries"]["2025"]
        self.assertEqual(entry["confidence_current"], "7")
        self.assertEqual(entry["season_goal_set"], "Primera ronda")
        self.assertEqual(entry["balance"], "100")

    def test_exit_interview_completion_and_reset_adjust_confidence(self) -> None:
        self.db.update_team_owner_office(
            "ATL",
            {"season_year": 2025, "confidence_current": "7"},
        )
        session = {"email": "gm@example.com", "name": "GM"}
        started = self.db.start_owner_exit_interview(
            "ATL", 2025, session, "Balance de temporada"
        )
        self.assertEqual(started["status"], "awaiting_gm")

        completed = self.db.complete_owner_exit_interview(
            "ATL",
            2025,
            session,
            "Respuesta",
            "Mensaje final",
            "Conclusión",
            1,
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["trust_delta"], 1)
        self.assertEqual(
            self.db.get_team_owner_office("ATL", include_private=True)["entries"]["2025"]["confidence_current"],
            "8",
        )

        self.assertTrue(self.db.reset_owner_exit_interview("ATL", 2025))
        self.assertIsNone(self.db.get_owner_exit_interview("ATL", 2025))
        self.assertEqual(
            self.db.get_team_owner_office("ATL", include_private=True)["entries"]["2025"]["confidence_current"],
            "7",
        )


if __name__ == "__main__":
    unittest.main()
