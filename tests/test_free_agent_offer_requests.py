import json
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

    def test_rejected_offer_notification_is_visible_and_dismissible_for_requesting_gm(self) -> None:
        user = self.db.upsert_google_user(
            "google-atl-gm",
            "atl-gm@example.com",
            "ATL GM",
            None,
        )
        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {"contract_type": "Min", "years": 1},
            {
                "user_id": user["id"],
                "email": "atl-gm@example.com",
                "name": "ATL GM",
                "role": "gm",
            },
        )
        self.assertIsNotNone(request)

        notification_id = self.db.create_user_notification(
            user_id=request.get("requester_user_id"),
            email=request.get("requester_email"),
            title="Oferta rechazada: Test Free Agent",
            body="La administración ha rechazado la oferta de ATL por Test Free Agent.",
            kind="free_agent_offer_rejected",
            entity_type="gm_free_agent_offer_request",
            entity_id=request["id"],
        )
        self.assertIsNotNone(notification_id)

        notifications = self.db.list_user_notifications_for_session(
            {"user_id": user["id"], "email": "atl-gm@example.com", "role": "gm"},
        )
        self.assertEqual(1, len(notifications))
        self.assertEqual("Oferta rechazada: Test Free Agent", notifications[0]["title"])
        self.assertEqual("free_agent_offer_rejected", notifications[0]["kind"])

        self.assertTrue(
            self.db.mark_user_notification_read(
                int(notification_id),
                {"user_id": user["id"], "email": "atl-gm@example.com", "role": "gm"},
            )
        )
        self.assertEqual(
            [],
            self.db.list_user_notifications_for_session(
                {"user_id": user["id"], "email": "atl-gm@example.com", "role": "gm"},
            ),
        )

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

    def test_admin_approved_qo_rejection_removes_player_to_unrestricted_free_agency(self) -> None:
        self.db.update_setting("current_year", "2026")
        self.db.update_setting("free_agency_mode", "1")
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Rejected QO Player",
                "position": "PG",
                "rating": "73",
                "bird_rights": "R",
                "years_left": "2+",
                "salary_2025_text": "2296271",
                "salary_2026_text": "2870338",
                "option_2026": "QO",
            },
        )
        self.assertIsNotNone(player_id)
        request = self.db.create_gm_option_request(
            int(player_id),
            "option_2026",
            "QO",
            "rejected",
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )
        self.assertIsNotNone(request)

        handler = object.__new__(Handler)
        handler.db = self.db
        handler.path = f"/api/admin/gm-option-requests/{request['id']}"
        handler._require_admin = lambda: True
        handler._require_csrf = lambda: True
        handler._require_sensitive_rate_limit = lambda _bucket: True
        handler._require_team_write_access = lambda _team_code: True
        handler._read_json = lambda: {"decision": "approved"}
        handler._current_session = lambda: {"email": "admin@example.com", "name": "Admin", "role": "admin"}
        handler._discord_notify_requested = lambda _payload: False
        handler._discord_image_requested = lambda _payload: False
        handler._log_admin_action = lambda *args, **kwargs: None
        captured = {}
        handler._json = lambda status, data: captured.update({"status": status, "data": data})

        Handler.do_PATCH(handler)

        self.assertEqual(200, captured["status"])
        self.assertIsNone(self.db.get_player_record(int(player_id)))
        free_agent = next(
            (agent for agent in self.db.list_free_agents() if agent["name"] == "Rejected QO Player"),
            None,
        )
        self.assertIsNotNone(free_agent)
        self.assertEqual("No restringido", free_agent["free_agent_type"])
        self.assertIsNone(free_agent["rights_team_code"])
        self.assertIsNone(free_agent["bird_rights"])

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

    def test_renewal_discord_notification_uses_offer_years(self) -> None:
        handler = object.__new__(Handler)
        captured = {}

        def fake_news_image_prompt(*_args, **_kwargs):
            return "prompt"

        def fake_notify_discord(title, description, **kwargs):
            captured["title"] = title
            captured["description"] = description
            captured["fields"] = kwargs.get("fields") or []
            return True

        handler._news_image_prompt = fake_news_image_prompt
        handler._notify_discord = fake_notify_discord

        sent = handler._notify_free_agent_signed(
            {
                "team_code": "ATL",
                "team_name": "Atlanta Hawks",
                "name": "Bird Rights Free Agent",
                "position": "SG",
                "bird_rights": "Reg",
                "salary_2025_text": "1.4674E7",
                "salary_2026_text": "21.000.000",
                "salary_2027_text": "22.680.000",
                "salary_2028_text": "24.360.000",
            },
            offer_payload={
                "salary_by_season": {
                    "2026": "21.000.000",
                    "2027": "22.680.000",
                    "2028": "24.360.000",
                },
                "option_by_season": {
                    "2028": "PO",
                },
            },
            offer_type="renewal",
            generate_image=False,
        )

        self.assertTrue(sent)
        self.assertEqual("ATL renueva a Bird Rights Free Agent", captured["title"])
        salary_field = next(field for field in captured["fields"] if field["name"] == "Salario")
        self.assertEqual(
            "2026-27: 21.000.000\n2027-28: 22.680.000\n2028-29: 24.360.000 (PO)",
            salary_field["value"],
        )
        self.assertNotIn("2025-26", salary_field["value"])
        self.assertNotIn("1.4674E7", salary_field["value"])

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

    def test_signing_free_agent_removes_retained_rights_row_on_other_team(self) -> None:
        self.db.update_setting("current_year", "2026")
        player_id = self.db.create_player(
            "BKN",
            {
                "name": "Retained Rights Player",
                "position": "PF",
                "rating": "78",
                "bird_rights": "Reg",
                "years_left": "2+",
                "salary_2025_text": "8.000.000",
                "salary_2026_text": "FB",
            },
        )
        self.assertIsNotNone(player_id)
        player = self.db.get_player_record(int(player_id))
        profile_id = int(player["profile_id"])
        free_agent_id = self.db.create_free_agent(
            {
                "profile_id": profile_id,
                "name": "Retained Rights Player",
                "position": "PF",
                "rating": "78",
                "bird_rights": "FB",
                "years_left": "2+",
                "free_agent_type": "No restringido",
                "source": "cap_hold",
                "rights_team_code": "BKN",
            }
        )
        self.assertIsNotNone(free_agent_id)

        signed_player_id = self.db.sign_free_agent(
            int(free_agent_id),
            "ATL",
            {
                "profile_id": profile_id,
                "name": "Retained Rights Player",
                "bird_rights": "Reg",
                "salary_2026_text": "12.000.000",
                "salary_2027_text": "12.600.000",
            },
        )

        self.assertIsNotNone(signed_player_id)
        self.assertIsNone(self.db.get_free_agent(int(free_agent_id)))
        signed_player = self.db.get_player_record(int(signed_player_id))
        self.assertEqual("ATL", signed_player["team_code"])
        self.assertEqual("12.000.000", signed_player["salary_2026_text"])
        players_for_profile = [
            row for row in self.db.list_players()
            if int(row.get("profile_id") or 0) == profile_id
        ]
        self.assertEqual(1, len(players_for_profile))
        self.assertEqual("ATL", players_for_profile[0]["team_code"])

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

    def test_free_agent_offer_allows_salary_decreases(self) -> None:
        handler = object.__new__(Handler)
        handler.db = self.db

        normalized = handler._validate_and_normalize_free_agent_offer_payload(
            {
                "name": "Declining Free Agent",
                "source": "manual",
                "experience_years": 6,
            },
            "ATL",
            {
                "contract_type": "Reg",
                "years": 3,
                "annual_raise_percent": -8,
                "salary_by_season": {"2025": "10.000.000"},
            },
        )

        self.assertEqual(-8.0, normalized["annual_raise_percent"])
        self.assertEqual("10.000.000", normalized["salary_by_season"]["2025"])
        self.assertEqual("9.200.000", normalized["salary_by_season"]["2026"])
        self.assertEqual("8.400.000", normalized["salary_by_season"]["2027"])

    def test_free_agent_offer_discord_thread_mentions_role_only_on_creation(self) -> None:
        handler = object.__new__(Handler)
        handler.db = self.db
        handler.discord_notifications_enabled = True
        handler.discord_free_agent_offers_webhook_url = "https://discord.example/webhook"
        handler.discord_webhook_url = ""
        handler.discord_free_agent_offers_forum_tag_ids = []
        handler.discord_free_agent_offers_role_id = "485913691045494785"
        handler.discord_bot_token = "discord-bot-token"

        calls = []
        dms = []

        def fake_post_discord_json(payload, **kwargs):
            calls.append({"payload": payload, "kwargs": kwargs})
            if kwargs.get("thread_name"):
                return {"channel_id": "1520310271862902864"}
            return {}

        def fake_send_discord_dm(user_id, payload):
            dms.append({"user_id": user_id, "payload": payload})
            return True

        handler._post_discord_json = fake_post_discord_json
        handler._send_discord_dm = fake_send_discord_dm
        self.db.update_free_agent(self.free_agent_id, {"agent": "Agent Smith"})
        self.db.update_setting("free_agent_rep_discord_ids", json.dumps({"Agent Smith": "123456789012345678"}))
        free_agent = self.db.get_free_agent(self.free_agent_id)
        agent_discord_id = handler._free_agent_agent_discord_id(free_agent)
        self.assertEqual("123456789012345678", agent_discord_id)
        offer_payload = {
            "contract_type": "Reg",
            "years": 1,
            "salary_by_season": {"2026": "10.000.000"},
            "notes": "Private offer details",
        }

        first_result = handler._notify_free_agent_offer(
            free_agent,
            "ATL",
            offer_payload,
            "free_agent_offer",
            agent_discord_id,
        )
        second_result = handler._notify_free_agent_offer(
            free_agent,
            "ATL",
            offer_payload,
            "free_agent_offer",
            agent_discord_id,
        )

        self.assertTrue(first_result["thread_sent"])
        self.assertTrue(first_result["agent_dm_sent"])
        self.assertTrue(second_result["thread_sent"])
        self.assertTrue(second_result["agent_dm_sent"])
        self.assertEqual(2, len(calls))
        self.assertEqual(2, len(dms))
        self.assertEqual("Test Free Agent", calls[0]["kwargs"].get("thread_name"))
        self.assertEqual("<@&485913691045494785>", calls[0]["payload"].get("content"))
        self.assertEqual(
            ["485913691045494785"],
            calls[0]["payload"].get("allowed_mentions", {}).get("roles"),
        )
        self.assertEqual("1520310271862902864", calls[1]["kwargs"].get("thread_id"))
        self.assertNotIn("content", calls[1]["payload"])
        public_payload_text = json.dumps(calls[0]["payload"], ensure_ascii=False)
        self.assertIn("Oferta recibida", public_payload_text)
        self.assertIn("El agente posteará aquí los detalles", public_payload_text)
        self.assertNotIn("ATL", public_payload_text)
        self.assertNotIn("10.000.000", public_payload_text)
        self.assertNotIn("Private offer details", public_payload_text)
        self.assertNotIn("Reg", public_payload_text)
        private_payload_text = json.dumps(dms[0]["payload"], ensure_ascii=False)
        self.assertEqual("123456789012345678", dms[0]["user_id"])
        self.assertIn("ATL", private_payload_text)
        self.assertIn("10.000.000", private_payload_text)
        self.assertIn("Private offer details", private_payload_text)
        self.assertIn("Reg", private_payload_text)

    def test_free_agent_team_appeal_import_preview_and_apply(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            insert_team(conn, "BOS", "Boston Celtics")
            conn.commit()

        rows = [
            [
                "RANKING ATRACTIVO <23",
                "",
                "RANKING ATRACTIVO <27",
                "",
                "RANKING ATRACTIVO 27-33",
                "",
                "RANKING ATRACTIVO +34",
                "",
            ],
            ["Multianual", "1 año", "Multianual", "1 año", "Multianual", "1 año", "Multianual", "1 año"],
            ["BOS", "ATL", "BKN", "BOS", "ATL", "BKN", "BOS", "ATL"],
            ["ATL", "BKN", "BOS", "ATL", "BKN", "BOS", "ATL", "BKN"],
            ["BKN", "BOS", "ATL", "BKN", "BOS", "ATL", "BKN", "BOS"],
        ]

        preview = self.db.preview_free_agent_team_appeal_import(rows)
        self.assertTrue(preview["ok"])
        self.assertEqual(3, preview["summary"]["team_count"])
        self.assertEqual("BOS", preview["rankings"][0]["under_23_multi"]["team_code"])
        self.assertEqual("ATL", preview["rankings"][0]["under_23_single"]["team_code"])

        applied = self.db.apply_free_agent_team_appeal_import(preview["records"])
        self.assertEqual({"record_count": 3}, applied)

        appeal = self.db.list_free_agent_team_appeal()
        atl = next(row for row in appeal["rows"] if row["team_code"] == "ATL")
        self.assertEqual(1.0, atl["under_23_single"])
        self.assertEqual(2.0, atl["under_23_multi"])
        self.assertEqual("BOS", appeal["rankings"][0]["under_23_multi"]["team_code"])

    def test_cartera_clients_include_offer_and_interest_teams(self) -> None:
        self.db.update_free_agent(self.free_agent_id, {"agent": "Agent Smith"})
        self.db.record_free_agent_interest(
            self.free_agent_id,
            "BKN",
            {
                "economic_offer": "12M",
                "role_offer": "Titular",
                "comments": "Interés alto",
            },
            {"email": "bkn-gm@example.com", "name": "BKN GM", "role": "gm"},
        )
        self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Reg",
                "years": 2,
                "salary_by_season": {"2026": "10.000.000"},
            },
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        payload = self.db.list_cartera_clients_for_session(
            {"role": "co_admin", "email": "agent@example.com", "agent_name": "Agent Smith"}
        )

        self.assertFalse(payload.get("missing_agent"))
        self.assertEqual("Agent Smith", payload["agent_name"])
        self.assertEqual(1, len(payload["clients"]))
        client = payload["clients"][0]
        self.assertEqual("Test Free Agent", client["name"])
        self.assertEqual(1, client["interest_count"])
        self.assertEqual(1, client["offer_count"])
        self.assertEqual("BKN", client["interests"][0]["team_code"])
        self.assertEqual("ATL", client["offers"][0]["team_code"])


if __name__ == "__main__":
    unittest.main()
