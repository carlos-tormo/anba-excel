import os
import sqlite3
import tempfile
import unittest

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


class DraftLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-draft-live-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            insert_team(conn, "BKN", "Brooklyn Nets")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        self.first_pick = self.db.create_draft_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "1st",
                "pick_number": 1,
                "owner_team_code": "ATL",
                "original_team_code": "ATL",
            }
        )
        self.second_pick = self.db.create_draft_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "1st",
                "pick_number": 2,
                "owner_team_code": "BKN",
                "original_team_code": "BKN",
            }
        )
        self.third_pick = self.db.create_draft_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "1st",
                "pick_number": 3,
                "owner_team_code": "ATL",
                "original_team_code": "ATL",
            }
        )

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_draft_live_settings_enable_current_pick_and_options(self) -> None:
        live = self.db.update_draft_live_settings(
            {
                "draft_year": 2026,
                "enabled": True,
                "duration_seconds": 180,
                "options_text": "Jugador B\nJugador A\nJugador B",
            }
        )

        self.assertTrue(live["enabled"])
        self.assertEqual(self.first_pick, live["current_pick_id"])
        self.assertEqual(180, live["duration_seconds"])
        self.assertEqual(["Jugador A", "Jugador B"], live["options"])

    def test_gm_selection_creates_pending_request_without_advancing(self) -> None:
        self.db.update_draft_live_settings({"draft_year": 2026, "enabled": True})

        request = self.db.create_gm_draft_pick_request(
            self.first_pick,
            {"option_value": "Jugador A"},
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )
        live = self.db.list_draft_live(2026)

        self.assertIsNotNone(request)
        self.assertEqual("Jugador A", request["selection_text"])
        first = next(row for row in live["draft_order"] if row["id"] == self.first_pick)
        self.assertEqual("Jugador A", first["pending_selection_text"])
        self.assertEqual("atl-gm@example.com", first["pending_requester_email"])
        self.assertFalse(first["selection_text"])
        self.assertEqual(self.first_pick, live["current_pick_id"])
        self.assertEqual([self.second_pick], live["requestable_pick_ids"])
        self.assertEqual(1, live["pending_request_count"])

    def test_admin_approval_applies_selection_and_advances_to_next_pick(self) -> None:
        self.db.update_draft_live_settings({"draft_year": 2026, "enabled": True})
        request = self.db.create_gm_draft_pick_request(
            self.first_pick,
            {"option_value": "Jugador A"},
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        live = self.db.submit_draft_live_pick(
            self.first_pick,
            {
                "option_value": request["option_value"],
                "custom_text": request["custom_text"] or request["selection_text"],
                "advance": True,
            },
            {"email": request["requester_email"], "name": request["requester_name"], "role": "gm"},
            is_admin=True,
        )
        updated = self.db.mark_gm_draft_pick_request_decided(
            request["id"],
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )

        first = next(row for row in live["draft_order"] if row["id"] == self.first_pick)
        self.assertEqual("Jugador A", first["selection_text"])
        self.assertEqual("atl-gm@example.com", first["selected_by_email"])
        self.assertEqual(self.second_pick, live["current_pick_id"])
        self.assertEqual("approved", updated["status"])

    def test_gm_cannot_select_non_current_pick(self) -> None:
        self.db.update_draft_live_settings({"draft_year": 2026, "enabled": True})

        with self.assertRaises(ValueError) as raised:
            self.db.create_gm_draft_pick_request(
                self.second_pick,
                {"option_value": "Jugador B"},
                {"email": "bkn-gm@example.com", "name": "BKN GM", "role": "gm"},
            )

        self.assertEqual("not_current_pick", str(raised.exception))

    def test_two_pending_draft_pick_requests_can_queue_but_third_waits(self) -> None:
        self.db.update_draft_live_settings({"draft_year": 2026, "enabled": True})

        first_request = self.db.create_gm_draft_pick_request(
            self.first_pick,
            {"option_value": "Jugador A"},
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )
        second_request = self.db.create_gm_draft_pick_request(
            self.second_pick,
            {"option_value": "Jugador B"},
            {"email": "bkn-gm@example.com", "name": "BKN GM", "role": "gm"},
        )
        live = self.db.list_draft_live(2026)

        self.assertIsNotNone(first_request)
        self.assertIsNotNone(second_request)
        self.assertEqual(2, live["pending_request_count"])
        self.assertEqual(2, live["max_pending_requests"])
        self.assertEqual([], live["requestable_pick_ids"])
        with self.assertRaises(ValueError) as raised:
            self.db.create_gm_draft_pick_request(
                self.third_pick,
                {"option_value": "Jugador C"},
                {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
            )

        self.assertEqual("too_many_pending_draft_picks", str(raised.exception))

        self.db.submit_draft_live_pick(
            self.first_pick,
            {
                "option_value": first_request["option_value"],
                "custom_text": first_request["custom_text"] or first_request["selection_text"],
                "advance": True,
            },
            {"email": first_request["requester_email"], "name": first_request["requester_name"], "role": "gm"},
            is_admin=True,
        )
        self.db.mark_gm_draft_pick_request_decided(
            first_request["id"],
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )
        live_after_approval = self.db.list_draft_live(2026)

        self.assertEqual(self.second_pick, live_after_approval["current_pick_id"])
        self.assertEqual(1, live_after_approval["pending_request_count"])
        self.assertEqual([self.third_pick], live_after_approval["requestable_pick_ids"])

    def test_process_draft_creates_first_round_cap_hold(self) -> None:
        self.db.update_setting("rookie_scale_2026_1", "10000000")
        self.db.submit_draft_live_pick(
            self.first_pick,
            {"option_value": "Rookie One", "advance": False},
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
            is_admin=True,
        )

        result = self.db.process_draft_results(2026)

        self.assertTrue(result["ok"])
        self.assertEqual(1, len(result["created_cap_holds"]))
        self.assertEqual(0, len(result["created_player_rights"]))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT d.dead_type, d.label, d.salary_2026_num, d.salary_2025_num,
                       d.exclude_from_gasto, d.exclude_from_cap, t.code
                FROM dead_contracts d
                JOIN teams t ON t.id = d.team_id
                WHERE d.id = ?
                """,
                (result["created_cap_holds"][0]["dead_contract_id"],),
            ).fetchone()
            selection = conn.execute(
                "SELECT processed_type, processed_dead_contract_id, processed_at FROM draft_live_selections WHERE draft_order_id = ?",
                (self.first_pick,),
            ).fetchone()

        self.assertEqual("ATL", row["code"])
        self.assertEqual("draft_hold", row["dead_type"])
        self.assertEqual("Rookie One", row["label"])
        self.assertEqual(10_000_000, int(row["salary_2026_num"]))
        self.assertIsNone(row["salary_2025_num"])
        self.assertEqual(1, row["exclude_from_gasto"])
        self.assertEqual(0, row["exclude_from_cap"])
        self.assertEqual("draft_cap_hold", selection["processed_type"])
        self.assertEqual(result["created_cap_holds"][0]["dead_contract_id"], selection["processed_dead_contract_id"])
        self.assertTrue(selection["processed_at"])

    def test_process_draft_creates_second_round_player_right_and_is_idempotent(self) -> None:
        second_round_pick = self.db.create_draft_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "2nd",
                "pick_number": 31,
                "owner_team_code": "BKN",
                "original_team_code": "ATL",
            }
        )
        self.db.submit_draft_live_pick(
            second_round_pick,
            {"option_value": "Second Rounder", "advance": False},
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
            is_admin=True,
        )

        result = self.db.process_draft_results(2026)
        result_again = self.db.process_draft_results(2026)

        self.assertTrue(result["ok"])
        self.assertEqual(0, len(result["created_cap_holds"]))
        self.assertEqual(1, len(result["created_player_rights"]))
        self.assertEqual(0, len(result_again["created_player_rights"]))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rights_count = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE asset_type = 'player_right' AND label = 'Second Rounder'"
            ).fetchone()[0]
            row = conn.execute(
                """
                SELECT a.asset_type, a.label, a.detail, a.year, t.code
                FROM assets a
                JOIN teams t ON t.id = a.team_id
                WHERE a.id = ?
                """,
                (result["created_player_rights"][0]["asset_id"],),
            ).fetchone()

        self.assertEqual(1, rights_count)
        self.assertEqual("BKN", row["code"])
        self.assertEqual("player_right", row["asset_type"])
        self.assertEqual("Second Rounder", row["label"])
        self.assertEqual(2026, int(row["year"]))
        self.assertIn("Pick #31", row["detail"])

    def test_process_draft_reports_missing_rookie_scale_salary(self) -> None:
        self.db.submit_draft_live_pick(
            self.first_pick,
            {"option_value": "Rookie One", "advance": False},
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
            is_admin=True,
        )

        result = self.db.process_draft_results(2026)

        self.assertFalse(result["ok"])
        self.assertEqual([], result["created_cap_holds"])
        self.assertEqual("missing_rookie_scale_salary", result["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
