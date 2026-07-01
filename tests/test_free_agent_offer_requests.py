import os
import sqlite3
import tempfile
import unittest

from app.server import Handler, LeagueDB
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
            insert_team(conn, "BKN", "Brooklyn Nets")
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

    def test_renewal_offer_updates_existing_active_contract_row(self) -> None:
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Bird Rights Free Agent",
                "position": "SG",
                "rating": "80",
                "bird_rights": "Reg",
                "years_left": "2+",
                "salary_2025_text": "5.000.000",
                "salary_2026_text": "FB",
                "salary_2029_text": "FB",
            },
        )
        self.assertIsNotNone(player_id)
        player = self.db.get_player_record(int(player_id))
        profile_id = int(player["profile_id"])
        free_agent_id = self.db.create_free_agent(
            {
                "profile_id": profile_id,
                "name": "Bird Rights Free Agent",
                "position": "SG",
                "rating": "80",
                "bird_rights": "FB",
                "years_left": "2+",
                "free_agent_type": "No restringido",
                "notes": "Cap hold retenido por ATL para 2026-27",
            }
        )
        self.assertIsNotNone(free_agent_id)

        signed_player_id = self.db.sign_free_agent(
            int(free_agent_id),
            "ATL",
            {
                "profile_id": profile_id,
                "name": "Bird Rights Free Agent",
                "bird_rights": "Reg",
                "salary_2026_text": "21.000.000",
                "salary_2027_text": "22.680.000",
                "salary_2028_text": "24.360.000",
                "option_2028": "PO",
            },
        )

        self.assertEqual(player_id, signed_player_id)
        self.assertIsNone(self.db.get_free_agent(int(free_agent_id)))
        updated = self.db.get_player_record(int(player_id))
        self.assertEqual("5.000.000", updated["salary_2025_text"])
        self.assertEqual("21.000.000", updated["salary_2026_text"])
        self.assertEqual("22.680.000", updated["salary_2027_text"])
        self.assertEqual("24.360.000", updated["salary_2028_text"])
        self.assertEqual("PO", updated["option_2028"])
        self.assertIsNone(updated["salary_2029_text"])
        self.assertEqual("Reg", updated["bird_rights"])

        players = [
            row for row in self.db.list_players()
            if int(row.get("profile_id") or 0) == profile_id
        ]
        self.assertEqual(1, len(players))

    def test_signing_free_agent_with_active_contract_on_other_team_still_fails(self) -> None:
        player_id = self.db.create_player(
            "BKN",
            {
                "name": "Other Team Player",
                "position": "SF",
                "rating": "77",
                "bird_rights": "Reg",
                "salary_2026_text": "10.000.000",
            },
        )
        self.assertIsNotNone(player_id)
        player = self.db.get_player_record(int(player_id))
        free_agent_id = self.db.create_free_agent(
            {
                "profile_id": int(player["profile_id"]),
                "name": "Other Team Player",
                "position": "SF",
                "rating": "77",
                "free_agent_type": "No restringido",
            }
        )
        self.assertIsNotNone(free_agent_id)

        with self.assertRaises(ValueError) as ctx:
            self.db.sign_free_agent(
                int(free_agent_id),
                "ATL",
                {
                    "profile_id": int(player["profile_id"]),
                    "name": "Other Team Player",
                    "bird_rights": "Reg",
                    "salary_2026_text": "12.000.000",
                },
            )
        self.assertEqual("profile_has_active_contract", str(ctx.exception))

    def test_renewal_offer_uses_bird_years_for_large_raises(self) -> None:
        handler = object.__new__(Handler)
        handler.db = self.db

        normalized = handler._validate_and_normalize_free_agent_offer_payload(
            {
                "name": "Bird Rights Free Agent",
                "source": "cap_hold",
                "rights_team_code": "ATL",
                "years_left": "2+",
                "bird_rights": "",
                "experience_years": 10,
            },
            "ATL",
            {
                "contract_type": "Max",
                "years": 5,
                "annual_raise_percent": 8,
                "salary_by_season": {},
            },
        )

        self.assertEqual(8.0, normalized["annual_raise_percent"])
        self.assertEqual(5, normalized["years"])
        self.assertEqual("54.126.450", normalized["salary_by_season"]["2025"])

    def test_free_agent_offer_discord_thread_mentions_role_only_on_creation(self) -> None:
        handler = object.__new__(Handler)
        handler.db = self.db
        handler.discord_notifications_enabled = True
        handler.discord_free_agent_offers_webhook_url = "https://discord.example/webhook"
        handler.discord_webhook_url = ""
        handler.discord_free_agent_offers_forum_tag_ids = []
        handler.discord_free_agent_offers_role_id = "485913691045494785"

        calls = []

        def fake_post_discord_json(payload, **kwargs):
            calls.append({"payload": payload, "kwargs": kwargs})
            if kwargs.get("thread_name"):
                return {"channel_id": "1520310271862902864"}
            return {}

        handler._post_discord_json = fake_post_discord_json
        free_agent = self.db.get_free_agent(self.free_agent_id)
        offer_payload = {
            "contract_type": "Reg",
            "years": 1,
            "salary_by_season": {"2026": "10.000.000"},
        }

        first_sent = handler._notify_free_agent_offer(
            free_agent,
            "ATL",
            offer_payload,
            "free_agent_offer",
        )
        second_sent = handler._notify_free_agent_offer(
            free_agent,
            "ATL",
            offer_payload,
            "free_agent_offer",
        )

        self.assertTrue(first_sent)
        self.assertTrue(second_sent)
        self.assertEqual(2, len(calls))
        self.assertEqual("Test Free Agent", calls[0]["kwargs"].get("thread_name"))
        self.assertEqual("<@&485913691045494785>", calls[0]["payload"].get("content"))
        self.assertEqual(
            ["485913691045494785"],
            calls[0]["payload"].get("allowed_mentions", {}).get("roles"),
        )
        self.assertEqual("1520310271862902864", calls[1]["kwargs"].get("thread_id"))
        self.assertNotIn("content", calls[1]["payload"])


if __name__ == "__main__":
    unittest.main()
