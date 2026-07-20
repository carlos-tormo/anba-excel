import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.services.waivers import WaiverService
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


class WaiverServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, path = tempfile.mkstemp(prefix="anba-waiver-service-", suffix=".db")
        os.close(descriptor)
        self.db_path = path
        with connect_test_db(path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            insert_team(conn, "BOS", "Boston Celtics")
            conn.commit()
        self.db = LeagueDB(path)
        self.db.ensure_auth_schema()
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Waiver Service Player",
                "position": "SG",
                "rating": "72",
                "bird_rights": "Reg",
                "salary_2025_text": "1.000.000",
            },
        )
        self.assertIsNotNone(player_id)
        cut = self.db.cut_player(int(player_id))
        self.assertIsNotNone(cut)
        self.assertTrue(cut["waiver"])
        self.waiver_id = int(cut["waiver_id"])
        self.service = WaiverService(self.db)
        self.gm = {"email": "bos-gm@example.com", "name": "BOS GM", "role": "gm"}
        self.admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def submit_claim(self) -> dict:
        submission = self.service.submit_claim(self.waiver_id, "bos", {}, self.gm)
        return submission["claim"]

    def test_submit_and_approve_claim_moves_player(self) -> None:
        claim = self.submit_claim()
        request = self.service.claim_request(int(claim["id"]))

        decision = self.service.decide_claim(
            int(claim["id"]),
            "approved",
            self.admin,
            request=request,
        )

        self.assertEqual("approved", decision["decision"])
        self.assertEqual("BOS", decision["team_code"])
        self.assertIsNotNone(decision["result"]["player_id"])
        player = self.db.get_player_record(int(decision["result"]["player_id"]))
        self.assertEqual("BOS", player["team_code"])

    def test_submit_and_reject_claim_keeps_waiver_active(self) -> None:
        claim = self.submit_claim()
        request = self.service.claim_request(int(claim["id"]))

        decision = self.service.decide_claim(
            int(claim["id"]),
            "rejected",
            self.admin,
            note="Rejected in service test",
            request=request,
        )

        self.assertEqual("rejected", decision["decision"])
        self.assertEqual("rejected", decision["result"]["status"])
        waivers = self.service.list_waivers(self.gm)
        self.assertEqual([self.waiver_id], [int(item["id"]) for item in waivers["waivers"]])

    def test_service_does_not_delegate_back_to_league_db_waiver_facades(self) -> None:
        def unexpected_delegate(*_args, **_kwargs):
            raise AssertionError("waiver repository delegated back to LeagueDB")

        self.db.list_waivers = unexpected_delegate
        self.db.process_expired_waivers_command = unexpected_delegate
        self.db.create_waiver_claim = unexpected_delegate
        self.db.list_waiver_claim_requests = unexpected_delegate
        self.db.decide_waiver_claim_request = unexpected_delegate

        listed = self.service.list_waivers(self.gm)
        claim = self.service.submit_claim(self.waiver_id, "BOS", {}, self.gm)["claim"]
        requests = self.service.claim_requests(status="pending")
        decision = self.service.decide_claim(
            int(claim["id"]),
            "rejected",
            self.admin,
            request=requests[0],
        )

        self.assertEqual(1, listed["count"])
        self.assertEqual([int(claim["id"])], [int(item["id"]) for item in requests])
        self.assertEqual("rejected", decision["result"]["status"])

    def test_repository_processes_expired_waiver_without_claim(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE waiver_players SET waiver_expires_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00Z", self.waiver_id),
            )

        result = self.service.process_expired()

        self.assertEqual(1, result["count"])
        self.assertEqual("expired", result["processed"][0]["action"])
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT status, free_agent_id FROM waiver_players WHERE id = ?",
                (self.waiver_id,),
            ).fetchone()
        self.assertEqual("expired", row["status"])
        self.assertIsNotNone(row["free_agent_id"])


if __name__ == "__main__":
    unittest.main()
