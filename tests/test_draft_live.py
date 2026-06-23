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


if __name__ == "__main__":
    unittest.main()
