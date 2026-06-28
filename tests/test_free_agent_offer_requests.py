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


class FreeAgentOfferRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-fa-offer-requests-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        free_agent_id = self.db.create_free_agent(
            {
                "name": "Test Free Agent",
                "position": "SG",
                "rating": "75",
                "free_agent_type": "No restringido",
            }
        )
        self.assertIsNotNone(free_agent_id)
        self.free_agent_id = int(free_agent_id)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_free_agent_offer_request_updates_pending_row_and_lists_with_gm_requests(self) -> None:
        requester = {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"}
        first = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Reg",
                "years": 2,
                "salary_by_season": {"2026": "10.000.000"},
            },
            requester,
            "free_agent_offer",
        )
        second = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Reg",
                "years": 3,
                "salary_by_season": {"2026": "11.000.000"},
            },
            requester,
            "renewal",
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual("renewal", second["offer_type"])
        self.assertEqual(3, second["offer_payload"]["years"])

        requests = self.db.list_gm_option_requests(status="pending")
        offer_requests = [request for request in requests if request["request_type"] == "free_agent_offer"]
        self.assertEqual(1, len(offer_requests))
        self.assertEqual("Test Free Agent", offer_requests[0]["player_name"])
        self.assertEqual("Renovación", offer_requests[0]["option_value"])
        self.assertEqual("Reg · 3 año(s)", offer_requests[0]["season_label"])

    def test_free_agent_offer_request_can_be_marked_decided(self) -> None:
        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {"contract_type": "Min", "years": 1},
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        updated = self.db.mark_gm_free_agent_offer_request_decided(
            int(request["id"]),
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )

        self.assertIsNotNone(updated)
        self.assertEqual("approved", updated["status"])
        self.assertEqual("admin@example.com", updated["admin_email"])

    def test_free_agent_offer_request_survives_signing_player(self) -> None:
        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Min",
                "years": 2,
                "salary_by_season": {"2026": "2.296.274", "2027": "2.411.090"},
            },
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        player_id = self.db.sign_free_agent(
            self.free_agent_id,
            "ATL",
            {
                "name": "Test Free Agent",
                "bird_rights": "Min",
                "salary_2026_text": "2.296.274",
                "salary_2027_text": "2.411.090",
            },
        )
        self.assertIsNotNone(player_id)
        self.assertIsNone(self.db.get_free_agent(self.free_agent_id))

        updated = self.db.mark_gm_free_agent_offer_request_decided(
            int(request["id"]),
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )

        self.assertIsNotNone(updated)
        self.assertEqual("approved", updated["status"])
        self.assertEqual("Test Free Agent", updated["player_name"])

        requests = self.db.list_gm_option_requests(status="all")
        offer_requests = [item for item in requests if item["request_type"] == "free_agent_offer"]
        self.assertEqual(1, len(offer_requests))
        self.assertEqual("Test Free Agent", offer_requests[0]["player_name"])

        player = self.db.get_player_record(int(player_id))
        self.assertIsNotNone(player)
        self.assertEqual("ATL", player["team_code"])
        self.assertEqual("2.296.274", player["salary_2026_text"])


if __name__ == "__main__":
    unittest.main()
