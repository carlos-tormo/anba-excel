import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

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
        with connect_test_db(self.db_path) as conn:
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

    def test_read_model_does_not_delegate_back_to_league_db_facades(self) -> None:
        def unexpected_delegate(*_args, **_kwargs):
            raise AssertionError("draft read repository delegated back to LeagueDB")

        self.db.current_draft_year = unexpected_delegate
        self.db.list_draft_order = unexpected_delegate
        self.db.list_draft_pick_ledger = unexpected_delegate
        self.db.get_draft_order_entry = unexpected_delegate
        self.db.list_draft_live = unexpected_delegate

        current_year = self.service.current_year()
        order = self.service.list_order(2026)
        ledger = self.service.list_pick_ledger(2026)
        entry = self.service.order_entry(self.first_pick)
        live = self.service.list_live(2026)

        self.assertEqual(2026, current_year)
        self.assertEqual([self.first_pick, self.second_pick], [row["id"] for row in order["draft_order"]])
        self.assertEqual(2026, ledger["draft_year"])
        self.assertEqual(self.first_pick, entry["id"])
        self.assertEqual([self.first_pick, self.second_pick], [row["id"] for row in live["draft_order"]])

    def test_mutations_do_not_delegate_back_to_league_db_facades(self) -> None:
        def unexpected_delegate(*_args, **_kwargs):
            raise AssertionError("draft repository delegated back to LeagueDB")

        for name in (
            "create_draft_order_entry", "update_draft_order_entry", "delete_draft_order_entry",
            "update_draft_live_settings", "control_draft_live", "submit_draft_live_pick",
            "create_gm_draft_pick_request", "get_gm_draft_pick_request",
            "mark_gm_draft_pick_request_decided", "process_draft_results",
        ):
            setattr(self.db, name, unexpected_delegate)

        extra_pick = self.service.create_order_entry({
            "draft_year": 2026, "draft_round": "2nd", "pick_number": 31,
            "owner_team_code": "ATL", "original_team_code": "BKN",
        })
        self.assertTrue(self.service.update_order_entry(extra_pick, {"owner_team_code": "BKN"}))
        self.assertTrue(self.service.delete_order_entry(extra_pick))

        self.service.update_live_settings({"draft_year": 2026, "enabled": True})
        self.service.control_live({"draft_year": 2026, "action": "restart"})
        submission = self.service.submit_pick(
            self.first_pick, {"option_value": "Repository Rookie"}, self.gm, is_admin=False
        )
        decision = self.service.decide_pick_request(
            int(submission["request"]["id"]), "approved", self.admin,
            request=submission["request"],
        )
        self.assertEqual("approved", decision["request"]["status"])

        self.db.update_setting("rookie_scale_2026_1", "10000000")
        processed = self.service.process_results(2026)
        self.assertTrue(processed["ok"])
        self.assertEqual(1, len(processed["created_cap_holds"]))


if __name__ == "__main__":
    unittest.main()
