import json
import os
import sqlite3
import tempfile
import unittest

from app.server import Handler, LeagueDB
from app.domain_rules import minimum_salary_for_season
from app.services.free_agency import FreeAgencyService, OfferDecisionOptions
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

    def test_free_agency_service_submits_normalized_offer(self) -> None:
        service = FreeAgencyService(
            self.db,
            contract_seasons=range(2025, 2032),
        )

        submission = service.submit_offer(
            self.free_agent_id,
            "atl",
            {
                "contract_type": "Reg",
                "years": 2,
                "annual_raise_percent": 5,
                "salary_by_season": {"2025": "10.000.000"},
                "option_by_season": {},
            },
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        self.assertEqual("ATL", submission["team_code"])
        self.assertEqual("free_agent_offer", submission["offer_type"])
        self.assertEqual("10.500.000", submission["payload"]["salary_by_season"]["2026"])
        self.assertEqual("pending", submission["request"]["status"])

    def test_free_agency_service_approves_offer_and_signs_player(self) -> None:
        service = FreeAgencyService(self.db, contract_seasons=range(2025, 2032))
        submission = service.submit_offer(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Reg",
                "years": 1,
                "annual_raise_percent": 0,
                "role": "Titular",
                "salary_by_season": {"2025": "10.000.000"},
                "option_by_season": {},
            },
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        result = service.decide_offer(
            int(submission["request"]["id"]),
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
            options=OfferDecisionOptions(note="Approved in service test", bypass_role_limits=True),
            request=submission["request"],
        )

        self.assertEqual("approved", result["decision"])
        self.assertEqual("approved", result["request"]["status"])
        self.assertIsNotNone(result["player_id"])
        self.assertEqual("10.000.000", result["player"]["salary_2025_text"])
        self.assertIsNone(self.db.get_free_agent(self.free_agent_id))

    def test_free_agency_service_rejects_offer_without_signing_player(self) -> None:
        service = FreeAgencyService(self.db, contract_seasons=range(2025, 2032))
        submission = service.submit_offer(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Reg",
                "years": 1,
                "annual_raise_percent": 0,
                "salary_by_season": {"2025": "10.000.000"},
                "option_by_season": {},
            },
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        result = service.decide_offer(
            int(submission["request"]["id"]),
            "rejected",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
            request=submission["request"],
        )

        self.assertEqual("rejected", result["decision"])
        self.assertEqual("rejected", result["request"]["status"])
        self.assertIsNotNone(self.db.get_free_agent(self.free_agent_id))

    def test_free_agency_service_manages_negotiation_favorite_and_cancellation(self) -> None:
        service = FreeAgencyService(self.db, contract_seasons=range(2025, 2032))
        actor = {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"}

        negotiation = service.negotiate(
            self.free_agent_id,
            "ATL",
            {"economic_offer": "10M", "role_offer": "Titular", "comments": "Interested"},
            actor,
        )
        favorite = service.set_favorite(
            self.free_agent_id,
            "ATL",
            actor,
            favorite=True,
        )
        submission = service.submit_offer(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Reg",
                "years": 1,
                "annual_raise_percent": 0,
                "salary_by_season": {"2025": "10.000.000"},
                "option_by_season": {},
            },
            actor,
        )
        cancellation = service.cancel_offer(
            int(submission["request"]["id"]),
            actor,
            request=submission["request"],
        )
        unfavorite = service.set_favorite(
            self.free_agent_id,
            "ATL",
            actor,
            favorite=False,
        )

        self.assertEqual("ATL", negotiation["team_code"])
        self.assertEqual("10M", negotiation["interest"]["economic_offer"])
        self.assertTrue(favorite["is_favorite"])
        self.assertEqual("cancelled", cancellation["request"]["status"])
        self.assertFalse(unfavorite["is_favorite"])

    def test_free_agency_service_creates_and_updates_manual_promise(self) -> None:
        service = FreeAgencyService(self.db, contract_seasons=range(2025, 2032))
        admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}

        promise = service.create_promise(
            {
                "player_name": "Manual Promise",
                "team_code": "ATL",
                "role": "Titular",
                "season_year": 2025,
                "status": "pending",
            },
            admin,
        )
        updated = service.update_promise(
            int(promise["id"]),
            {"status": "fulfilled"},
            admin,
        )

        self.assertEqual("pending", promise["status"])
        self.assertIsNotNone(updated)
        self.assertEqual("fulfilled", updated["status"])

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

    def test_free_agent_offer_request_decision_is_single_use(self) -> None:
        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {"contract_type": "Min", "years": 1},
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        first = self.db.mark_gm_free_agent_offer_request_decided(
            int(request["id"]),
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )
        second = self.db.mark_gm_free_agent_offer_request_decided(
            int(request["id"]),
            "rejected",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )
        stored = self.db.get_gm_free_agent_offer_request(int(request["id"]))

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertIsNotNone(stored)
        self.assertEqual("approved", stored["status"])

    def test_decided_free_agent_offer_request_cannot_be_cancelled(self) -> None:
        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {"contract_type": "Min", "years": 1},
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )
        self.db.mark_gm_free_agent_offer_request_decided(
            int(request["id"]),
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )

        with self.assertRaises(ValueError) as ctx:
            self.db.cancel_gm_free_agent_offer_request(int(request["id"]), "ATL")

        self.assertEqual("offer_not_pending", str(ctx.exception))
        self.assertIsNotNone(self.db.get_gm_free_agent_offer_request(int(request["id"])))

    def test_outbox_events_are_idempotent_by_key(self) -> None:
        first = self.db.enqueue_outbox_event(
            "discord.free_agent_offer",
            {"request_id": 1, "player": "Test Free Agent"},
            aggregate_type="gm_free_agent_offer_request",
            aggregate_id=1,
            idempotency_key="gm-free-agent-offer:1:approved",
        )
        second = self.db.enqueue_outbox_event(
            "discord.free_agent_offer",
            {"request_id": 1, "player": "Test Free Agent"},
            aggregate_type="gm_free_agent_offer_request",
            aggregate_id=1,
            idempotency_key="gm-free-agent-offer:1:approved",
        )

        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE idempotency_key = ?",
                ("gm-free-agent-offer:1:approved",),
            ).fetchone()[0]

        self.assertEqual(first, second)
        self.assertEqual(1, count)

    def test_approved_offer_with_role_creates_agent_promise(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE free_agents SET agent = ? WHERE id = ?", ("Agent One", self.free_agent_id))
            conn.commit()

        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Min",
                "years": 1,
                "salary_by_season": {"2026": "2.296.274"},
                "role": "Minutos de rotación (10-20)",
            },
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        updated = self.db.mark_gm_free_agent_offer_request_decided(
            int(request["id"]),
            "approved",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )

        self.assertIsNotNone(updated)
        agent_view = self.db.list_free_agent_offer_promises(
            {"email": "agent@example.com", "name": "Agent", "role": "co_admin", "agent_name": "Agent One"},
            status="all",
        )
        self.assertFalse(agent_view["missing_agent"])
        self.assertEqual(1, len(agent_view["promises"]))
        promise = agent_view["promises"][0]
        self.assertEqual("Test Free Agent", promise["player_name"])
        self.assertEqual("ATL", promise["team_code"])
        self.assertEqual("Agent One", promise["agent_name"])
        self.assertEqual("Minutos de rotación (10-20)", promise["role"])
        self.assertEqual("pending", promise["status"])

        changed = self.db.update_free_agent_offer_promise_status(
            int(promise["id"]),
            "fulfilled",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )
        self.assertEqual("fulfilled", changed["status"])
        filtered = self.db.list_free_agent_offer_promises(
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
            status="fulfilled",
        )
        self.assertEqual(1, len(filtered["promises"]))

    def test_promise_role_limits_block_only_active_signed_promises(self) -> None:
        admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}
        self.db.create_free_agent_offer_promise(
            {
                "player_name": "Existing Sixth Man",
                "team_code": "ATL",
                "season_year": 2026,
                "role": "Sexto hombre",
                "status": "pending",
            },
            admin,
        )

        with self.assertRaises(ValueError) as ctx:
            self.db.create_free_agent_offer_promise(
                {
                    "player_name": "Second Sixth Man",
                    "team_code": "ATL",
                    "season_year": 2026,
                    "role": "Sexto hombre",
                    "status": "pending",
                },
                admin,
            )
        self.assertEqual("promise_role_limit_exceeded:Sexto hombre:1", str(ctx.exception))

        broken = self.db.update_free_agent_offer_promise_status(
            1,
            "broken",
            admin,
        )
        self.assertEqual("broken", broken["status"])
        replacement = self.db.create_free_agent_offer_promise(
            {
                "player_name": "Replacement Sixth Man",
                "team_code": "ATL",
                "season_year": 2026,
                "role": "Sexto hombre",
                "status": "pending",
            },
            admin,
        )
        self.assertEqual("Replacement Sixth Man", replacement["player_name"])

    def test_admin_can_bypass_promise_role_limit_for_manual_corrections(self) -> None:
        admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}
        self.db.create_free_agent_offer_promise(
            {
                "player_name": "First Sixth Man",
                "team_code": "ATL",
                "season_year": 2026,
                "role": "Sexto hombre",
                "status": "pending",
            },
            admin,
        )

        duplicate = self.db.create_free_agent_offer_promise(
            {
                "player_name": "Admin Override Sixth Man",
                "team_code": "ATL",
                "season_year": 2026,
                "role": "Sexto hombre",
                "status": "pending",
            },
            admin,
            bypass_role_limits=True,
        )

        self.assertEqual("Admin Override Sixth Man", duplicate["player_name"])
        self.assertEqual("pending", duplicate["status"])

    def test_admin_can_edit_existing_free_agent_offer_promise(self) -> None:
        admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}
        promise = self.db.create_free_agent_offer_promise(
            {
                "player_name": "Misspelled Player",
                "team_code": "ATL",
                "season_year": 2026,
                "role": "Minutos de rotación (0-9)",
                "agent_name": "Agent One",
                "contract_type": "Min · 1 año",
                "status": "pending",
            },
            admin,
        )

        updated = self.db.update_free_agent_offer_promise(
            int(promise["id"]),
            {
                "player_name": "Corrected Player",
                "team_code": "BKN",
                "season_year": 2027,
                "role": "Sexto hombre",
                "agent_name": "Agent Two",
                "contract_type": "Reg · 2 años",
                "offer_type": "manual",
                "status": "fulfilled",
            },
            admin,
            bypass_role_limits=True,
        )

        self.assertIsNotNone(updated)
        self.assertEqual("Corrected Player", updated["player_name"])
        self.assertEqual("BKN", updated["team_code"])
        self.assertEqual(2027, updated["season_year"])
        self.assertEqual("Sexto hombre", updated["role"])
        self.assertEqual("Agent Two", updated["agent_name"])
        self.assertEqual("Reg · 2 años", updated["contract_type"])
        self.assertEqual("fulfilled", updated["status"])

    def test_free_agent_offer_approval_checks_promise_role_capacity_before_signing(self) -> None:
        admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}
        self.db.create_free_agent_offer_promise(
            {
                "player_name": "Signed Sixth Man",
                "team_code": "ATL",
                "season_year": 2026,
                "role": "Sexto hombre",
                "status": "fulfilled",
            },
            admin,
        )
        request = self.db.create_gm_free_agent_offer_request(
            self.free_agent_id,
            "ATL",
            {
                "contract_type": "Min",
                "years": 1,
                "salary_by_season": {"2026": "2.296.274"},
                "role": "Sexto hombre",
            },
            {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"},
        )

        with self.assertRaises(ValueError) as ctx:
            self.db.ensure_free_agent_offer_request_promise_capacity(int(request["id"]))
        self.assertEqual("promise_role_limit_exceeded:Sexto hombre:1", str(ctx.exception))
        self.assertIsNotNone(self.db.get_free_agent(self.free_agent_id))
        self.assertEqual("pending", self.db.get_gm_free_agent_offer_request(int(request["id"]))["status"])

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
        self.assertEqual(2_296_274, round(float(player["salary_2026_num"])))

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
        handler._require_json_write_content_type = lambda: True
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
        self.assertEqual(21_000_000, round(float(updated["salary_2026_num"])))
        self.assertEqual(22_680_000, round(float(updated["salary_2027_num"])))
        self.assertEqual(24_360_000, round(float(updated["salary_2028_num"])))
        self.assertEqual("PO", updated["option_2028"])
        self.assertIsNone(updated["salary_2029_text"])
        self.assertEqual("Reg", updated["bird_rights"])
        self.assertEqual("2+", updated["years_left"])

        players = [
            row for row in self.db.list_players()
            if int(row.get("profile_id") or 0) == profile_id
        ]
        self.assertEqual(1, len(players))

    def test_player_payload_from_free_agent_offer_adds_post_contract_bird_markers(self) -> None:
        handler = object.__new__(Handler)

        one_year = handler._player_payload_from_free_agent_offer(
            {"name": "One Year FA"},
            {
                "contract_type": "Reg",
                "years": 1,
                "salary_by_season": {"2026": "10.000.000"},
            },
        )
        self.assertEqual("NB", one_year["salary_2027_text"])

        two_year = handler._player_payload_from_free_agent_offer(
            {"name": "Two Year FA"},
            {
                "contract_type": "Reg",
                "years": 2,
                "salary_by_season": {
                    "2026": "10.000.000",
                    "2027": "11.000.000",
                },
            },
        )
        self.assertEqual("EB", two_year["salary_2028_text"])

        long_contract = handler._player_payload_from_free_agent_offer(
            {"name": "Long FA"},
            {
                "contract_type": "Reg",
                "years": 3,
                "salary_by_season": {
                    "2026": "10.000.000",
                    "2027": "11.000.000",
                    "2028": "12.000.000",
                },
            },
        )
        self.assertEqual("FB", long_contract["salary_2029_text"])

    def test_player_payload_from_two_way_offer_adds_qo_two_way_marker(self) -> None:
        handler = object.__new__(Handler)

        payload = handler._player_payload_from_free_agent_offer(
            {"name": "Two Way FA"},
            {
                "contract_type": "Two-way",
                "years": 1,
                "salary_by_season": {"2026": "636.435"},
            },
        )

        self.assertEqual("Two-way", payload["salary_2027_text"])
        self.assertEqual("QO", payload["option_2027"])

    def test_player_payload_from_free_agent_offer_skips_post_contract_marker_when_final_year_has_option(self) -> None:
        handler = object.__new__(Handler)

        payload = handler._player_payload_from_free_agent_offer(
            {"name": "Option FA"},
            {
                "contract_type": "Reg",
                "years": 2,
                "salary_by_season": {
                    "2026": "10.000.000",
                    "2027": "11.000.000",
                },
                "option_by_season": {"2027": "PO"},
            },
        )

        self.assertNotIn("salary_2028_text", payload)

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
        self.assertIsNone(signed_player["years_left"])
        players_for_profile = [
            row for row in self.db.list_players()
            if int(row.get("profile_id") or 0) == profile_id
        ]
        self.assertEqual(1, len(players_for_profile))
        self.assertEqual("ATL", players_for_profile[0]["team_code"])

    def test_signing_free_agent_overrides_accepted_qo_rights_on_other_team(self) -> None:
        self.db.update_setting("current_year", "2026")
        player_id = self.db.create_player(
            "BKN",
            {
                "name": "Accepted QO Player",
                "position": "SG",
                "rating": "76",
                "bird_rights": "R",
                "years_left": "1",
                "salary_2026_text": "6.250.000",
                "option_2026": "QO",
            },
        )
        self.assertIsNotNone(player_id)
        player = self.db.get_player_record(int(player_id))
        profile_id = int(player["profile_id"])
        self.db.record_admin_option_decision(
            int(player_id),
            "option_2026",
            "QO",
            "accepted",
            {"email": "admin@example.com", "name": "Admin", "role": "admin"},
        )
        free_agent_id = self.db.create_free_agent(
            {
                "profile_id": profile_id,
                "name": "Accepted QO Player",
                "position": "SG",
                "rating": "76",
                "bird_rights": "QO",
                "free_agent_type": "Restringido",
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
                "name": "Accepted QO Player",
                "bird_rights": "Reg",
                "salary_2026_text": "12.000.000",
                "salary_2027_text": "12.600.000",
            },
        )

        self.assertIsNotNone(signed_player_id)
        self.assertIsNone(self.db.get_free_agent(int(free_agent_id)))
        players_for_profile = [
            row for row in self.db.list_players()
            if int(row.get("profile_id") or 0) == profile_id
        ]
        self.assertEqual(1, len(players_for_profile))
        self.assertEqual("ATL", players_for_profile[0]["team_code"])
        signed_player = self.db.get_player_record(int(signed_player_id))
        self.assertEqual("12.000.000", signed_player["salary_2026_text"])
        self.assertIsNone(signed_player["years_left"])

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

    def test_free_agent_offer_requires_role_for_low_salary_or_minimum(self) -> None:
        handler = object.__new__(Handler)
        handler.db = self.db
        free_agent = {
            "name": "Low Salary Free Agent",
            "source": "manual",
            "experience_years": 2,
        }

        with self.assertRaisesRegex(ValueError, "offer_role_required"):
            handler._validate_and_normalize_free_agent_offer_payload(
                free_agent,
                "ATL",
                {
                    "contract_type": "Reg",
                    "years": 1,
                    "annual_raise_percent": 0,
                    "salary_by_season": {"2025": "5.000.000"},
                },
            )

        normalized = handler._validate_and_normalize_free_agent_offer_payload(
            free_agent,
            "ATL",
            {
                "contract_type": "Min",
                "years": 1,
                "annual_raise_percent": 0,
                "role": "sexto hombre",
                "salary_by_season": {},
            },
        )

        self.assertEqual("Sexto hombre", normalized["role"])

    def test_minimum_offer_for_over_2_yos_uses_2_yos_team_salary(self) -> None:
        handler = object.__new__(Handler)
        handler.db = self.db

        normalized = handler._validate_and_normalize_free_agent_offer_payload(
            {
                "name": "Veteran Minimum Free Agent",
                "source": "manual",
                "experience_years": 10,
            },
            "ATL",
            {
                "contract_type": "Min",
                "years": 2,
                "annual_raise_percent": 0,
                "role": "Minutos de rotación (0-9)",
                "salary_by_season": {},
            },
        )

        self.assertEqual(
            f"{int(minimum_salary_for_season(154_647_000, 2, 1)):,}".replace(",", "."),
            normalized["salary_by_season"]["2025"],
        )
        self.assertEqual(
            f"{int(minimum_salary_for_season(154_647_000, 2, 2)):,}".replace(",", "."),
            normalized["salary_by_season"]["2026"],
        )

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

    def test_minimum_target_order_includes_bird_rights_bonus(self) -> None:
        user = self.db.upsert_google_user("google-atl-gm", "atl-gm@example.com", "ATL GM", None)
        self.db.replace_user_team_assignments(int(user["id"]), ["ATL"])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE free_agents SET rights_team_code = ? WHERE id = ?",
                ("ATL", self.free_agent_id),
            )
            conn.commit()

        self.db.set_gm_minimum_targets(
            int(user["id"]),
            "ATL",
            [
                {
                    "rank": 1,
                    "free_agent_id": self.free_agent_id,
                    "role": "Titular",
                }
            ],
        )

        scores = self.db.list_admin_gm_minimum_target_order()

        self.assertEqual(1, len(scores))
        self.assertEqual("ATL", scores[0]["team_code"])
        self.assertEqual("ATL", scores[0]["rights_team_code"])
        self.assertEqual(10, scores[0]["priority_points"])
        self.assertEqual(20, scores[0]["role_points"])
        self.assertEqual(10, scores[0]["birds_bonus"])
        self.assertEqual(40, scores[0]["total"])
        self.assertEqual(0, scores[0]["handicap"])

        self.db.set_gm_minimum_target_handicap("ATL", -3)
        scores = self.db.list_admin_gm_minimum_target_order()
        self.assertEqual(-3, scores[0]["handicap"])
        self.assertEqual(37, scores[0]["total"])
        self.assertEqual(6, self.db._minimum_target_birds_bonus(23, "ATL", "ATL"))
        self.assertEqual(6, self.db._minimum_target_birds_bonus(28, "ATL", "ATL"))
        self.assertEqual(3, self.db._minimum_target_birds_bonus(29, "ATL", "ATL"))
        self.assertEqual(1, self.db._minimum_target_birds_bonus(34, "ATL", "ATL"))
        self.assertEqual(0, self.db._minimum_target_birds_bonus(22, "BKN", "ATL"))

    def test_minimum_target_order_compresses_empty_priority_slots(self) -> None:
        user = self.db.upsert_google_user("google-atl-gm", "atl-gm@example.com", "ATL GM", None)
        self.db.replace_user_team_assignments(int(user["id"]), ["ATL"])
        self.db.set_gm_minimum_targets(
            int(user["id"]),
            "ATL",
            [
                {
                    "rank": 3,
                    "free_agent_id": self.free_agent_id,
                    "role": "Titular",
                }
            ],
        )

        scores = self.db.list_admin_gm_minimum_target_order()

        self.assertEqual(1, len(scores))
        self.assertEqual(10, scores[0]["priority_points"])
        self.assertEqual(1, scores[0]["target_rank"])
        self.assertEqual(3, scores[0]["original_target_rank"])

    def test_admin_can_remove_minimum_target_from_user_list(self) -> None:
        user = self.db.upsert_google_user("google-atl-gm", "atl-gm@example.com", "ATL GM", None)
        self.db.replace_user_team_assignments(int(user["id"]), ["ATL"])
        self.db.set_gm_minimum_targets(
            int(user["id"]),
            "ATL",
            [
                {
                    "rank": 1,
                    "free_agent_id": self.free_agent_id,
                    "role": "Titular",
                }
            ],
        )

        result = self.db.remove_admin_gm_minimum_target(int(user["id"]), 1)

        self.assertTrue(result["removed"])
        minimum_targets = self.db.get_gm_minimum_targets(int(user["id"]), "ATL")
        self.assertEqual([], minimum_targets["targets"])

    def test_signing_free_agent_removes_minimum_targets_for_every_gm(self) -> None:
        atl_user = self.db.upsert_google_user("google-atl-gm", "atl-gm@example.com", "ATL GM", None)
        bkn_user = self.db.upsert_google_user("google-bkn-gm", "bkn-gm@example.com", "BKN GM", None)
        self.db.replace_user_team_assignments(int(atl_user["id"]), ["ATL"])
        self.db.replace_user_team_assignments(int(bkn_user["id"]), ["BKN"])
        self.db.set_gm_minimum_targets(
            int(atl_user["id"]),
            "ATL",
            [{"rank": 1, "free_agent_id": self.free_agent_id, "role": "Titular"}],
        )
        self.db.set_gm_minimum_targets(
            int(bkn_user["id"]),
            "BKN",
            [{"rank": 2, "free_agent_id": self.free_agent_id, "role": "Sexto hombre"}],
        )

        player_id = self.db.sign_free_agent(
            self.free_agent_id,
            "ATL",
            {
                "name": "Test Free Agent",
                "bird_rights": "Min",
                "salary_2026_text": "2.296.274",
            },
        )

        self.assertIsNotNone(player_id)
        self.assertEqual([], self.db.get_gm_minimum_targets(int(atl_user["id"]), "ATL")["targets"])
        self.assertEqual([], self.db.get_gm_minimum_targets(int(bkn_user["id"]), "BKN")["targets"])
        self.assertEqual([], self.db.list_admin_gm_minimum_target_order())

    def test_deleting_free_agent_removes_minimum_targets_for_every_gm(self) -> None:
        user = self.db.upsert_google_user("google-atl-gm", "atl-gm@example.com", "ATL GM", None)
        self.db.replace_user_team_assignments(int(user["id"]), ["ATL"])
        self.db.set_gm_minimum_targets(
            int(user["id"]),
            "ATL",
            [{"rank": 1, "free_agent_id": self.free_agent_id, "role": "Titular"}],
        )

        deleted = self.db.delete_free_agent(self.free_agent_id)

        self.assertTrue(deleted)
        self.assertEqual([], self.db.get_gm_minimum_targets(int(user["id"]), "ATL")["targets"])
        self.assertEqual([], self.db.list_admin_gm_minimum_target_order())

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

    def test_gm_spending_limits_are_persisted_and_visible_to_cartera(self) -> None:
        saved = self.db.set_gm_free_agent_spending_limit(
            "ATL",
            "12.5",
            {"email": "atl-gm@example.com", "role": "gm"},
        )

        self.assertEqual("ATL", saved["team_code"])
        self.assertEqual(12500000, saved["amount"])
        self.assertEqual(12.5, saved["amount_millions"])
        self.assertTrue(saved["has_value"])

        office = self.db.list_gm_office("ATL")
        self.assertEqual(12500000, office["free_agent_spending_limit"]["amount"])
        self.assertTrue(office["free_agent_spending_limit"]["has_value"])

        self.db.update_free_agent(self.free_agent_id, {"agent": "Agent Smith"})
        payload = self.db.list_cartera_clients_for_session(
            {"role": "co_admin", "email": "agent@example.com", "agent_name": "Agent Smith"}
        )
        limits = {item["team_code"]: item for item in payload["gm_spending_limits"]}
        self.assertEqual(12500000, limits["ATL"]["amount"])
        self.assertTrue(limits["ATL"]["has_value"])
        self.assertFalse(limits["BKN"]["has_value"])

        minimum_only = self.db.set_gm_free_agent_spending_limit(
            "BKN",
            "0",
            {"email": "bkn-gm@example.com", "role": "gm"},
        )
        self.assertEqual(0, minimum_only["amount"])
        self.assertTrue(minimum_only["has_value"])

    def test_cartera_clients_include_persisted_ruleouts_for_agent(self) -> None:
        self.db.update_free_agent(self.free_agent_id, {"agent": "Agent Smith"})
        session = {"role": "co_admin", "email": "agent@example.com", "agent_name": "Agent Smith"}

        rows = self.db.set_free_agent_team_ruleout(self.free_agent_id, "BKN", session)
        self.assertEqual("BKN", rows[0]["team_code"])

        with self.assertRaises(PermissionError):
            self.db.set_free_agent_team_ruleout(
                self.free_agent_id,
                "ATL",
                {"role": "co_admin", "email": "other-agent@example.com", "agent_name": "Other Agent"},
            )

        payload = self.db.list_cartera_clients_for_session(session)
        client = payload["clients"][0]
        self.assertEqual("BKN", client["ruled_out_teams"][0]["team_code"])

        rows = self.db.delete_free_agent_team_ruleout(self.free_agent_id, "BKN", session)
        self.assertEqual([], rows)


if __name__ == "__main__":
    unittest.main()
