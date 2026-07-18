import os
import sqlite3
import tempfile
import unittest

from app.server import LeagueDB
from app.services.draft import DraftService
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, timestamp, timestamp),
    )


class DraftServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(prefix="anba-draft-service-", suffix=".db")
        os.close(descriptor)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            insert_team(conn, "BKN", "Brooklyn Nets")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        self.service = DraftService(self.db)
        self.first_pick = self.service.create_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "1st",
                "pick_number": 1,
                "owner_team_code": "ATL",
                "original_team_code": "ATL",
            }
        )
        self.second_pick = self.service.create_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "1st",
                "pick_number": 2,
                "owner_team_code": "BKN",
                "original_team_code": "BKN",
            }
        )
        self.gm = {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"}
        self.admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def submit_gm_pick(self) -> dict:
        self.service.update_live_settings({"draft_year": 2026, "enabled": True})
        return self.service.submit_pick(
            self.first_pick,
            {"option_value": "Jugador A"},
            self.gm,
            is_admin=False,
        )

    def test_gm_submission_is_queued_without_advancing(self) -> None:
        submission = self.submit_gm_pick()

        self.assertTrue(submission["submitted_for_review"])
        self.assertEqual("pending", submission["request"]["status"])
        self.assertEqual(self.first_pick, submission["draft_live"]["current_pick_id"])

    def test_approve_pick_request_selects_player_and_advances(self) -> None:
        submission = self.submit_gm_pick()

        decision = self.service.decide_pick_request(
            int(submission["request"]["id"]),
            "approved",
            self.admin,
            request=submission["request"],
        )

        self.assertEqual("approved", decision["request"]["status"])
        self.assertEqual(self.second_pick, decision["draft_live"]["current_pick_id"])
        first = next(
            row for row in decision["draft_live"]["draft_order"] if row["id"] == self.first_pick
        )
        self.assertEqual("Jugador A", first["selection_text"])
        self.assertEqual(self.gm["email"], first["selected_by_email"])

    def test_reject_pick_request_keeps_current_pick_open(self) -> None:
        submission = self.submit_gm_pick()

        decision = self.service.decide_pick_request(
            int(submission["request"]["id"]),
            "rejected",
            self.admin,
            note="Invalid selection",
            request=submission["request"],
        )

        self.assertEqual("rejected", decision["request"]["status"])
        live = self.service.list_live(2026)
        self.assertEqual(self.first_pick, live["current_pick_id"])
        first = next(row for row in live["draft_order"] if row["id"] == self.first_pick)
        self.assertIsNone(first["selection_text"])


if __name__ == "__main__":
    unittest.main()
