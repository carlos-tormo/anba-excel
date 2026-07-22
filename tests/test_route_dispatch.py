import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

from app.routes import (
    DELETE_ROUTES,
    EARLY_POST_ROUTES,
    GET_ROUTES,
    OWNER_OFFICE_MULTIPART_POST_ROUTES,
    PATCH_ROUTES,
    POST_ROUTES,
)
from app.routing import (
    bytes_response,
    dispatch_routes,
    exact_route,
    json_response,
    predicate_route,
    prefix_route,
    redirect_response,
)
from app.server import Handler


class RouteRegistryTests(unittest.TestCase):
    def test_dispatch_uses_first_matching_route_and_reports_match(self):
        calls = []
        routes = (
            exact_route("/api/items", lambda *_args: calls.append("exact")),
            prefix_route("/api/", lambda *_args: calls.append("prefix")),
        )

        matched = dispatch_routes(object(), urlparse("/api/items"), routes)

        self.assertTrue(matched)
        self.assertEqual(["exact"], calls)
        self.assertFalse(dispatch_routes(object(), urlparse("/outside"), routes))

    def test_dispatch_sends_framework_neutral_response_objects(self):
        handler = SimpleNamespace(_send_route_response=Mock())
        route = exact_route("/api/items", lambda *_args: json_response(202, {"ok": True}))

        matched = dispatch_routes(handler, urlparse("/api/items"), (route,))

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(202, response.status)
        self.assertEqual({"ok": True}, response.payload)

    def test_dispatch_stores_matched_route_name_for_operational_logging(self):
        handler = SimpleNamespace()
        route = exact_route("/api/items", lambda *_args: None, name="items-list")

        self.assertTrue(dispatch_routes(handler, urlparse("/api/items"), (route,)))

        self.assertEqual("items-list", handler._current_route_name)

    def test_dispatch_sends_framework_neutral_byte_responses(self):
        handler = SimpleNamespace(_send_route_response=Mock())
        route = exact_route("/asset", lambda *_args: bytes_response(200, b"abc", "text/plain"))

        matched = dispatch_routes(handler, urlparse("/asset"), (route,))

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual(b"abc", response.body)
        self.assertEqual("text/plain", response.content_type)

    def test_redirect_response_is_empty_body_framework_neutral_response(self):
        handler = SimpleNamespace(_send_route_response=Mock())
        route = exact_route("/login", lambda *_args: redirect_response("/admin", headers={"Set-Cookie": ["a=1", "b=2"]}))

        matched = dispatch_routes(handler, urlparse("/login"), (route,))

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(302, response.status)
        self.assertEqual(b"", response.body)
        self.assertEqual("/admin", response.headers["Location"])
        self.assertEqual(["a=1", "b=2"], response.headers["Set-Cookie"])

    def test_predicate_route_matches_only_the_declared_path_shape(self):
        calls = []
        route = predicate_route(
            "item-action",
            lambda path: path.startswith("/api/items/") and path.endswith("/approve"),
            lambda *_args: calls.append("matched"),
        )

        self.assertTrue(dispatch_routes(object(), urlparse("/api/items/7/approve"), (route,)))
        self.assertFalse(dispatch_routes(object(), urlparse("/api/items/7"), (route,)))
        self.assertEqual(["matched"], calls)

    def test_free_agent_action_routes_do_not_capture_other_free_agent_paths(self):
        self.assertTrue(any(route.matches("/api/free-agents/7/offer") for route in POST_ROUTES))
        self.assertTrue(any(route.matches("/api/free-agents/7/sign") for route in POST_ROUTES))
        self.assertTrue(any(route.matches("/api/free-agents/7") for route in PATCH_ROUTES))
        self.assertFalse(any(route.matches("/api/free-agents/7/offer") for route in PATCH_ROUTES))

    def test_owner_office_routes_match_only_complete_workflow_paths(self):
        self.assertTrue(any(route.matches("/api/teams/ATL/owner-office") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/teams/ATL/owner-office/background-image") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/teams/ATL/owner-exit-interview/start") for route in POST_ROUTES))
        self.assertTrue(any(route.matches("/api/teams/ATL/owner-exit-interview/reply") for route in POST_ROUTES))
        self.assertTrue(any(route.matches("/api/teams/ATL/owner-exit-interview/reset") for route in POST_ROUTES))
        self.assertTrue(
            any(
                route.matches("/api/teams/ATL/owner-office/background")
                for route in OWNER_OFFICE_MULTIPART_POST_ROUTES
            )
        )
        self.assertTrue(any(route.matches("/api/teams/ATL/owner-office") for route in PATCH_ROUTES))
        self.assertFalse(any(route.matches("/api/teams/ATL/owner-exit-interview/unknown") for route in POST_ROUTES))
        owner_route = next(route for route in GET_ROUTES if route.name == "owner-office")
        self.assertFalse(owner_route.matches("/api/teams/ATL/owner-office/extra"))

    def test_owner_office_get_route_returns_framework_neutral_response(self):
        owner_office = SimpleNamespace(get=Mock(return_value={"team_code": "ATL", "season_year": 2026}))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _is_admin=Mock(return_value=False),
            _send_route_response=Mock(),
            app=SimpleNamespace(owner_office=owner_office),
        )

        matched = dispatch_routes(handler, urlparse("/api/teams/ATL/owner-office"), GET_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("owner_office.view", {"team_code": "ATL"})
        owner_office.get.assert_called_once_with("ATL", include_private=False)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"owner_office": {"team_code": "ATL", "season_year": 2026}}, response.payload)

    def test_owner_background_image_route_returns_framework_neutral_byte_response(self):
        owner_office = SimpleNamespace(get_background_image=Mock(return_value=(b"image", "image/png")))
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            app=SimpleNamespace(owner_office=owner_office),
        )

        matched = dispatch_routes(handler, urlparse("/api/teams/ATL/owner-office/background-image"), GET_ROUTES)

        self.assertTrue(matched)
        owner_office.get_background_image.assert_called_once_with("ATL")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual(b"image", response.body)
        self.assertEqual("image/png", response.content_type)
        self.assertEqual('inline; filename="owner-office-ATL.png"', response.headers["Content-Disposition"])

    def test_gm_office_routes_are_registered_by_http_method(self):
        self.assertTrue(any(route.matches("/api/gm-office") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/gm-office/minimum-targets") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/admin/gm-minimum-targets/order") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/gm-office/depth-chart") for route in POST_ROUTES))
        self.assertTrue(any(route.matches("/api/gm-office/minimum-targets/omit") for route in POST_ROUTES))
        self.assertFalse(any(route.matches("/api/gm-office/depth-chart") for route in GET_ROUTES))

    def test_gm_office_get_route_returns_framework_neutral_response(self):
        gm_office = SimpleNamespace(get=Mock(return_value={"team_code": "ATL"}))
        gm_minimum_targets = SimpleNamespace(get=Mock(return_value={"targets": []}))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"user_id": 4}),
            _send_route_response=Mock(),
            app=SimpleNamespace(gm_office=gm_office, gm_minimum_targets=gm_minimum_targets),
        )

        matched = dispatch_routes(handler, urlparse("/api/gm-office?team_code=ATL"), GET_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("gm_office.view", {"team_code": "ATL"})
        gm_office.get.assert_called_once_with("ATL")
        gm_minimum_targets.get.assert_called_once_with(4, "ATL")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"team_code": "ATL", "minimum_targets": {"targets": []}}, response.payload)

    def test_free_agents_get_route_returns_framework_neutral_response(self):
        free_agency = SimpleNamespace(
            list_free_agents=Mock(return_value={
                "free_agents": [{"id": 7, "name": "Player", "is_favorite": True, "favorite_team_code": "ATL"}],
            }),
        )
        handler = SimpleNamespace(
            _current_session_team_codes=Mock(return_value=["ATL"]),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=free_agency),
        )

        matched = dispatch_routes(handler, urlparse("/api/free-agents"), GET_ROUTES)

        self.assertTrue(matched)
        free_agency.list_free_agents.assert_called_once_with(["ATL"])
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual(
            {"free_agents": [{"id": 7, "name": "Player", "is_favorite": True, "favorite_team_code": "ATL"}]},
            response.payload,
        )

    def test_cartera_promises_get_route_maps_errors_to_response(self):
        free_agency = SimpleNamespace(list_promises=Mock(side_effect=ValueError("invalid_status")))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"role": "coadmin"}),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=free_agency),
        )

        matched = dispatch_routes(handler, urlparse("/api/cartera/promises?status=nope"), GET_ROUTES)

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(400, response.status)
        self.assertEqual({"error": "invalid_status"}, response.payload)

    def test_admin_users_get_route_returns_framework_neutral_response(self):
        users = SimpleNamespace(list=Mock(return_value=[
            {"email": "admin@example.com", "team_codes": "", "is_co_admin": 0},
            {"email": "gm@example.com", "team_codes": "ATL,BOS", "is_co_admin": 0},
        ]))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            admin_emails={"admin@example.com"},
            app=SimpleNamespace(users=users),
        )

        matched = dispatch_routes(handler, urlparse("/api/admin/users"), GET_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("admin.users.view")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual("admin", response.payload["users"][0]["role"])
        self.assertEqual("gm", response.payload["users"][1]["role"])
        self.assertEqual("ATL", response.payload["users"][1]["team_code"])
        self.assertEqual(["ATL", "BOS"], response.payload["users"][1]["team_codes"])

    def test_admin_option_requests_get_route_returns_framework_neutral_response(self):
        gm_request_queries = SimpleNamespace(list=Mock(return_value=[{"id": 9, "status": "approved"}]))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(gm_request_queries=gm_request_queries),
        )

        matched = dispatch_routes(handler, urlparse("/api/admin/gm-option-requests?status=approved"), GET_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("admin.gm_option_request.view")
        gm_request_queries.list.assert_called_once_with(status="approved")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"requests": [{"id": 9, "status": "approved"}]}, response.payload)

    def test_coadmin_votes_get_route_returns_framework_neutral_response(self):
        session = {"user_id": 3, "role": "co_admin"}
        coadmin_votes = SimpleNamespace(
            list_coadmin_votes_for_session=Mock(return_value={"votes": [{"id": 4}]})
        )
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value=session),
            _send_route_response=Mock(),
            app=SimpleNamespace(coadmin_votes=coadmin_votes),
        )

        matched = dispatch_routes(handler, urlparse("/api/coadmin-votes"), GET_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("coadmin.vote.list")
        coadmin_votes.list_coadmin_votes_for_session.assert_called_once_with(session)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"votes": [{"id": 4}]}, response.payload)

    def test_tracker_get_route_returns_framework_neutral_response_with_timing_header(self):
        tracker = SimpleNamespace(
            list=Mock(return_value={
                "rows": [{"team_code": "ATL"}],
                "season_year": 2026,
                "seasons": [2025, 2026],
                "timings": {"sql_ms": 1.5},
                "stale": False,
            })
        )
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            log_message=Mock(),
            app=SimpleNamespace(tracker=tracker),
        )

        matched = dispatch_routes(handler, urlparse("/api/tracker?season=2026"), GET_ROUTES)

        self.assertTrue(matched)
        tracker.list.assert_called_once_with(2026)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual([{"team_code": "ATL"}], response.payload["tracker"])
        self.assertEqual(2026, response.payload["season_year"])
        self.assertEqual("sql_ms=1.5", response.headers["X-Tracker-Timing"])

    def test_tracker_get_route_rejects_invalid_season_with_response_object(self):
        tracker = SimpleNamespace(list=Mock())
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            log_message=Mock(),
            app=SimpleNamespace(tracker=tracker),
        )

        matched = dispatch_routes(handler, urlparse("/api/tracker?season=bad"), GET_ROUTES)

        self.assertTrue(matched)
        tracker.list.assert_not_called()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(400, response.status)
        self.assertEqual({"error": "invalid_season_year"}, response.payload)

    def test_cartera_clients_get_route_returns_framework_neutral_response(self):
        session = {"user_id": 3, "role": "co_admin"}
        cartera = SimpleNamespace(list_clients=Mock(return_value={"clients": [{"id": 8}]}))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value=session),
            _send_route_response=Mock(),
            app=SimpleNamespace(cartera=cartera),
        )

        matched = dispatch_routes(handler, urlparse("/api/cartera/clients"), GET_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("coadmin.cartera.view")
        cartera.list_clients.assert_called_once_with(session)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"clients": [{"id": 8}]}, response.payload)

    def test_offseason_exception_preview_rejects_invalid_season_with_response_object(self):
        offseason_exceptions = SimpleNamespace(preview=Mock())
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(offseason_exceptions=offseason_exceptions),
        )

        matched = dispatch_routes(handler, urlparse("/api/offseason-exceptions/preview?season=bad"), GET_ROUTES)

        self.assertTrue(matched)
        offseason_exceptions.preview.assert_not_called()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(400, response.status)
        self.assertEqual({"error": "invalid_season_year"}, response.payload)

    def test_profile_salary_history_get_route_returns_framework_neutral_response(self):
        players = SimpleNamespace(list_salary_history=Mock(return_value=[{"season_year": 2026}]))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(players=players),
        )

        matched = dispatch_routes(handler, urlparse("/api/player-profiles/7/salary-history"), GET_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("admin.player_profile.view")
        players.list_salary_history.assert_called_once_with(7)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"salary_history": [{"season_year": 2026}]}, response.payload)

    def test_admin_player_catalog_get_route_returns_framework_neutral_response_with_timing_header(self):
        player_catalog = SimpleNamespace(
            list_players=Mock(return_value=[{"id": 5, "name": "Player"}]),
            last_timings={"sql_ms": 2.25},
        )
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            log_message=Mock(),
            app=SimpleNamespace(player_catalog=player_catalog),
        )

        matched = dispatch_routes(handler, urlparse("/api/admin/players"), GET_ROUTES)

        self.assertTrue(matched)
        player_catalog.list_players.assert_called_once_with(
            include_private=True,
            sync_generated=False,
            include_salary_history=False,
            collect_timings=True,
        )
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual([{"id": 5, "name": "Player"}], response.payload["players"])
        self.assertEqual("sql_ms=2.25", response.headers["X-Player-Catalog-Timing"])

    def test_gm_history_get_route_maps_missing_team_to_response_object(self):
        teams = SimpleNamespace(list_gm_history=Mock(return_value=None))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(teams=teams),
        )

        matched = dispatch_routes(handler, urlparse("/api/gm-history?team=BAD"), GET_ROUTES)

        self.assertTrue(matched)
        teams.list_gm_history.assert_called_once_with("BAD")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(404, response.status)
        self.assertEqual({"error": "team_not_found"}, response.payload)

    def test_team_detail_get_route_returns_framework_neutral_response(self):
        team_detail = SimpleNamespace(get=Mock(return_value={"team_code": "ATL", "players": []}))
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            app=SimpleNamespace(team_detail=team_detail),
        )

        matched = dispatch_routes(handler, urlparse("/api/teams/ATL?season=2026"), GET_ROUTES)

        self.assertTrue(matched)
        team_detail.get.assert_called_once_with("ATL", move_season_year=2026)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"team_code": "ATL", "players": []}, response.payload)

    def test_remaining_handler_workflow_routes_are_registered(self):
        for path in (
            "/api/players/17/remove",
            "/api/players/17/cut",
            "/api/players",
            "/api/players/move",
            "/api/admin/economy-import/preview",
            "/api/admin/economy-import/import",
            "/api/admin/owner-office-import/preview",
            "/api/admin/free-agent-agent-import/import",
            "/api/admin/free-agent-appeal-import/preview",
            "/api/admin/backup",
            "/api/admin/launch-article",
            "/api/me/notifications/9/read",
        ):
            self.assertTrue(any(route.matches(path) for route in POST_ROUTES), path)
        for path in (
            "/api/export/league.xlsx",
            "/api/me/notifications",
            "/api/news/articles/4",
            "/api/news/articles/4/image",
        ):
            self.assertTrue(any(route.matches(path) for route in GET_ROUTES), path)

    def test_all_http_methods_are_dispatch_only(self):
        for method in (Handler.do_GET, Handler.do_POST, Handler.do_PATCH, Handler.do_DELETE):
            source = inspect.getsource(method)
            self.assertNotIn("parsed.path", source, method.__name__)

    def test_final_extracted_route_groups_are_registered(self):
        for path in (
            "/api/auth/google/start",
            "/api/auth/status",
            "/api/tracker",
            "/api/admin/users",
            "/api/teams/ATL",
            "/api/trades/archive",
        ):
            self.assertTrue(any(route.matches(path) for route in GET_ROUTES), path)
        for path in (
            "/api/auth/login",
            "/api/trades/process",
            "/api/trades/archive",
            "/api/trades/archive/import",
            "/api/player-profiles/4/merge",
            "/api/assets",
            "/api/settings/progress-year",
        ):
            self.assertTrue(any(route.matches(path) for route in POST_ROUTES), path)
        for path in (
            "/api/admin/gm-draft-pick-requests/4",
            "/api/trades/archive/4",
            "/api/settings",
            "/api/players/4",
            "/api/teams/ATL",
            "/api/dead-contracts/4",
        ):
            self.assertTrue(any(route.matches(path) for route in PATCH_ROUTES), path)
        self.assertTrue(any(route.matches("/api/trades/archive/4") for route in DELETE_ROUTES))

    def test_google_oauth_start_disabled_returns_route_redirect(self):
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            app=SimpleNamespace(google_enabled=False),
        )

        matched = dispatch_routes(handler, urlparse("/api/auth/google/start"), GET_ROUTES)

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(302, response.status)
        self.assertEqual(b"", response.body)
        self.assertEqual("/login?error=google_not_configured", response.headers["Location"])

    def test_google_oauth_start_preserves_waiting_list_token_cookie(self):
        google_client = SimpleNamespace(authorization_url=Mock(return_value="https://google.example/auth"))
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            _require_oauth_start_rate_limit=Mock(return_value=True),
            _store_oauth_state=Mock(),
            _oauth_state_cookie=Mock(return_value="oauth_state=state; HttpOnly"),
            app=SimpleNamespace(google_enabled=True, google_client=google_client),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/auth/google/start?waiting_list_token=abcDEF1234567890_abcDEF1234567890"),
            GET_ROUTES,
        )

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual("https://google.example/auth", response.headers["Location"])
        self.assertEqual("oauth_state=state; HttpOnly", response.headers["Set-Cookie"][0])
        self.assertIn("waiting_list_token=abcDEF1234567890_abcDEF1234567890", response.headers["Set-Cookie"][1])
        self.assertIn("Path=/api/auth/google/callback", response.headers["Set-Cookie"][1])

    def test_google_oauth_callback_success_returns_route_redirect_with_session_cookies(self):
        google_oauth = SimpleNamespace(
            complete=Mock(
                return_value={
                    "session": {"user_id": 7},
                    "role": "gm",
                    "team_codes": ["ATL"],
                }
            )
        )
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            _oauth_state_ok=Mock(return_value=True),
            _start_session=Mock(return_value=("session-token", "csrf-token")),
            _session_cookie=Mock(return_value="session=session-token; HttpOnly"),
            _clear_oauth_state_cookie=Mock(return_value="oauth_state=; Max-Age=0"),
            _landing_path_for_session=Mock(return_value="/"),
            _cookie_dict=Mock(return_value={}),
            app=SimpleNamespace(google_oauth=google_oauth),
        )

        matched = dispatch_routes(handler, urlparse("/api/auth/google/callback?code=abc&state=state"), GET_ROUTES)

        self.assertTrue(matched)
        google_oauth.complete.assert_called_once_with("abc")
        handler._start_session.assert_called_once_with({"user_id": 7})
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(302, response.status)
        self.assertEqual("/", response.headers["Location"])
        self.assertEqual(
            ["session=session-token; HttpOnly", "oauth_state=; Max-Age=0"],
            response.headers["Set-Cookie"],
        )

    def test_google_oauth_callback_consumes_waiting_list_token_after_login(self):
        google_oauth = SimpleNamespace(
            complete=Mock(
                return_value={
                    "session": {"user_id": 7, "name": "Candidate"},
                    "role": "guest",
                    "team_codes": [],
                }
            )
        )
        waiting_list = SimpleNamespace(consume_invite_token=Mock(return_value={"id": 1}))
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            _oauth_state_ok=Mock(return_value=True),
            _start_session=Mock(return_value=("session-token", "csrf-token")),
            _session_cookie=Mock(return_value="session=session-token; HttpOnly"),
            _clear_oauth_state_cookie=Mock(return_value="oauth_state=; Max-Age=0"),
            _landing_path_for_session=Mock(return_value="/"),
            _cookie_dict=Mock(return_value={"waiting_list_token": "invite-token"}),
            app=SimpleNamespace(google_oauth=google_oauth, waiting_list=waiting_list),
        )

        matched = dispatch_routes(handler, urlparse("/api/auth/google/callback?code=abc&state=state"), GET_ROUTES)

        self.assertTrue(matched)
        waiting_list.consume_invite_token.assert_called_once_with(
            token="invite-token",
            user_id=7,
            display_name="Candidate",
        )
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual("session=session-token; HttpOnly", response.headers["Set-Cookie"][0])
        self.assertEqual("oauth_state=; Max-Age=0", response.headers["Set-Cookie"][1])
        self.assertIn("waiting_list_token=", response.headers["Set-Cookie"][2])
        self.assertIn("Max-Age=0", response.headers["Set-Cookie"][2])

    def test_trade_archive_get_route_returns_framework_neutral_response(self):
        trade_archive = SimpleNamespace(list=Mock(return_value={"trades": [], "seasons": []}))
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            app=SimpleNamespace(trade_archive=trade_archive),
        )

        matched = dispatch_routes(handler, urlparse("/api/trades/archive?season=2026"), GET_ROUTES)

        self.assertTrue(matched)
        trade_archive.list.assert_called_once_with(season_year=2026)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"trades": [], "seasons": []}, response.payload)

    def test_trade_archive_import_route_uses_service_and_audits(self):
        result = {"ok": True, "created": [{"id": 1}], "errors": []}
        trade_archive = SimpleNamespace(import_trades=Mock(return_value=result))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(trade_archive=trade_archive),
        )

        matched = dispatch_routes(handler, urlparse("/api/trades/archive/import"), POST_ROUTES, {"trades": []})

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("admin.trade_archive.write")
        trade_archive.import_trades.assert_called_once_with({"trades": []})
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual(result, response.payload)

    def test_trade_archive_import_route_accepts_raw_array_payload(self):
        result = {"ok": True, "created": [{"id": 1}], "errors": [], "total": 1}
        trade_archive = SimpleNamespace(import_trades=Mock(return_value=result))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(trade_archive=trade_archive),
        )
        payload = [{"trade_id": "legacy-1"}]

        matched = dispatch_routes(handler, urlparse("/api/trades/archive/import"), POST_ROUTES, payload)

        self.assertTrue(matched)
        trade_archive.import_trades.assert_called_once_with(payload)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual(result, response.payload)

    def test_waiting_list_routes_use_service_and_framework_neutral_responses(self):
        waiting_list = SimpleNamespace(
            list=Mock(return_value={"entries": []}),
            create=Mock(return_value={"id": 1, "display_name": "Carlos", "position": 1}),
            get=Mock(return_value={"id": 1, "display_name": "Carlos", "position": 1}),
            update=Mock(return_value={"id": 1, "display_name": "Carlos T.", "position": 1}),
            delete=Mock(return_value=True),
        )
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(waiting_list=waiting_list),
        )

        self.assertTrue(dispatch_routes(handler, urlparse("/api/waiting-list"), GET_ROUTES))
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"entries": []}, response.payload)
        waiting_list.list.assert_called_once_with()

        self.assertTrue(dispatch_routes(handler, urlparse("/api/waiting-list"), POST_ROUTES, {"display_name": "Carlos"}))
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        waiting_list.create.assert_called_once_with({"display_name": "Carlos"})
        handler._authorize.assert_called_with("admin.waiting_list.write")

        self.assertTrue(dispatch_routes(handler, urlparse("/api/waiting-list/1"), PATCH_ROUTES, {"display_name": "Carlos T."}))
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        waiting_list.update.assert_called_once_with(1, {"display_name": "Carlos T."})

        self.assertTrue(dispatch_routes(handler, urlparse("/api/waiting-list/1"), DELETE_ROUTES))
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        waiting_list.delete.assert_called_once_with(1)

    def test_get_draft_route_rejects_invalid_year_before_service_call(self):
        draft_service = Mock()
        handler = SimpleNamespace(
            _send_route_response=Mock(),
            app=SimpleNamespace(draft=draft_service),
        )

        matched = dispatch_routes(handler, urlparse("/api/draft-order?year=invalid"), GET_ROUTES)

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(400, response.status)
        self.assertEqual({"error": "invalid_draft_year"}, response.payload)
        draft_service.list_order.assert_not_called()

    def test_delete_route_preserves_authorization_audit_and_response(self):
        delete_free_agent = Mock(return_value=True)
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=SimpleNamespace(delete_free_agent=delete_free_agent)),
        )

        matched = dispatch_routes(handler, urlparse("/api/free-agents/17"), DELETE_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("admin.free_agent.write")
        delete_free_agent.assert_called_once_with(17)
        handler._log_admin_action.assert_called_once_with("delete", "free_agent", "17")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True}, response.payload)

    def test_login_route_returns_framework_neutral_cookie_response(self):
        handler = SimpleNamespace(
            admin_user="admin",
            admin_password="secret",
            admin_password_hash="",
            _client_ip=Mock(return_value="127.0.0.1"),
            _rate_limit_status=Mock(return_value=(False, 0)),
            _rate_limit_fail=Mock(),
            _rate_limit_success=Mock(),
            _start_session=Mock(return_value=("session-token", "csrf-token")),
            _session_cookie=Mock(return_value="session=session-token; HttpOnly"),
            _send_route_response=Mock(),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/auth/login"),
            POST_ROUTES,
            {"username": "admin", "password": "secret"},
        )

        self.assertTrue(matched)
        handler._rate_limit_success.assert_called_once_with("127.0.0.1")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True, "csrf_token": "csrf-token"}, response.payload)
        self.assertEqual("session=session-token; HttpOnly", response.headers["Set-Cookie"])

    def test_login_route_maps_invalid_credentials_to_route_response(self):
        handler = SimpleNamespace(
            admin_user="admin",
            admin_password="secret",
            admin_password_hash="",
            _client_ip=Mock(return_value="127.0.0.1"),
            _rate_limit_status=Mock(return_value=(False, 0)),
            _rate_limit_fail=Mock(),
            _send_route_response=Mock(),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/auth/login"),
            POST_ROUTES,
            {"username": "admin", "password": "wrong"},
        )

        self.assertTrue(matched)
        handler._rate_limit_fail.assert_called_once_with("127.0.0.1")
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(401, response.status)
        self.assertEqual({"error": "invalid_credentials"}, response.payload)

    def test_logout_route_returns_framework_neutral_clear_cookie_response(self):
        handler = SimpleNamespace(
            _is_authenticated=Mock(return_value=False),
            _clear_session=Mock(),
            _clear_session_cookie=Mock(return_value="session=; Max-Age=0"),
            _send_route_response=Mock(),
        )

        matched = dispatch_routes(handler, urlparse("/api/auth/logout"), EARLY_POST_ROUTES, {})

        self.assertTrue(matched)
        handler._clear_session.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True}, response.payload)
        self.assertEqual("session=; Max-Age=0", response.headers["Set-Cookie"])

    def test_trade_process_validate_legacy_payload_returns_framework_neutral_response(self):
        trades = SimpleNamespace(validate_process_payload=Mock(return_value={"valid": True}))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(trades=trades),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/trades/process/validate"),
            POST_ROUTES,
            {"team_a": "atl", "team_b": "bos"},
        )

        self.assertTrue(matched)
        handler._authorize.assert_any_call("admin.trade.process", {"team_code": "ATL"})
        handler._authorize.assert_any_call("admin.trade.process", {"team_code": "BOS"})
        trades.validate_process_payload.assert_called_once_with({"team_a": "ATL", "team_b": "BOS"})
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True, "validation": {"valid": True}}, response.payload)

    def test_trade_process_validate_normalized_payload_returns_framework_neutral_response(self):
        trades = SimpleNamespace(
            normalize_request=Mock(return_value={
                "teams": ["ATL", "BOS"],
                "selections": [{"team": "ATL"}],
                "cash": [{"from": "ATL", "to": "BOS", "amount": 1000000}],
            }),
            validate=Mock(return_value={"valid": True, "mode": "normalized"}),
        )
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(trades=trades),
        )
        payload = {"teams": [{"code": "ATL"}, {"code": "BOS"}], "selections": []}

        matched = dispatch_routes(
            handler,
            urlparse("/api/trades/process/validate"),
            POST_ROUTES,
            payload,
        )

        self.assertTrue(matched)
        trades.normalize_request.assert_called_once_with(payload)
        handler._authorize.assert_any_call("admin.trade.process", {"team_code": "ATL"})
        handler._authorize.assert_any_call("admin.trade.process", {"team_code": "BOS"})
        trades.validate.assert_called_once_with({
            **payload,
            "teams": ["ATL", "BOS"],
            "selections": [{"team": "ATL"}],
            "cash": [{"from": "ATL", "to": "BOS", "amount": 1000000}],
        })
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True, "validation": {"valid": True, "mode": "normalized"}}, response.payload)

    def test_gm_option_request_route_returns_framework_neutral_response(self):
        request = {"id": 11, "player_id": 7, "status": "pending"}
        gm_request_queries = SimpleNamespace(create_option=Mock(return_value=request))
        players = SimpleNamespace(record=Mock(return_value={"id": 7, "team_code": "ATL"}))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _validate_specialized_payload_or_error=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"user_id": 4}),
            _send_route_response=Mock(),
            app=SimpleNamespace(players=players, gm_request_queries=gm_request_queries),
        )
        payload = {
            "player_id": 7,
            "option_field": "option_2027",
            "option_value": "po",
            "action": "accepted",
        }

        matched = dispatch_routes(handler, urlparse("/api/gm/option-requests"), POST_ROUTES, payload)

        self.assertTrue(matched)
        players.record.assert_called_once_with(7)
        handler._authorize.assert_called_once_with("gm.option_request.create", {"team_code": "ATL"})
        gm_request_queries.create_option.assert_called_once_with(
            7,
            "option_2027",
            "PO",
            "accepted",
            {"user_id": 4},
        )
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual({"ok": True, "request": request}, response.payload)

    def test_gm_option_request_route_maps_option_mismatch_to_conflict_response(self):
        gm_request_queries = SimpleNamespace(create_option=Mock(side_effect=ValueError("option_mismatch")))
        players = SimpleNamespace(record=Mock(return_value={"id": 7, "team_code": "ATL"}))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _validate_specialized_payload_or_error=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"user_id": 4}),
            _send_route_response=Mock(),
            app=SimpleNamespace(players=players, gm_request_queries=gm_request_queries),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/gm/option-requests"),
            POST_ROUTES,
            {
                "player_id": 7,
                "option_field": "option_2027",
                "option_value": "PO",
                "action": "accepted",
            },
        )

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(409, response.status)
        self.assertEqual({"error": "option_changed"}, response.payload)

    def test_offseason_exception_generate_rejects_invalid_season_with_route_response(self):
        offseason_exceptions = SimpleNamespace(generate=Mock())
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(offseason_exceptions=offseason_exceptions),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/offseason-exceptions/generate"),
            POST_ROUTES,
            {"season_year": "bad"},
        )

        self.assertTrue(matched)
        offseason_exceptions.generate.assert_not_called()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(400, response.status)
        self.assertEqual({"error": "invalid_season_year"}, response.payload)

    def test_offseason_exception_generate_audits_and_returns_route_response(self):
        result = {
            "generated": [
                {"team_code": "ATL", "created": [{"exception": "MLE"}, {"exception": "BAE"}]},
                {"team_code": "BOS", "created": []},
            ],
            "skipped": [{"team_code": "NYK", "reason": "already_exists"}],
        }
        offseason_exceptions = SimpleNamespace(generate=Mock(return_value=result))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(offseason_exceptions=offseason_exceptions),
        )
        payload = {"season_year": 2026, "team_codes": ["ATL", "BOS"], "choices": {"ATL": "non_tax"}}

        matched = dispatch_routes(
            handler,
            urlparse("/api/offseason-exceptions/generate"),
            POST_ROUTES,
            payload,
        )

        self.assertTrue(matched)
        offseason_exceptions.generate.assert_called_once_with(
            2026,
            team_codes=["ATL", "BOS"],
            choices={"ATL": "non_tax"},
        )
        handler._log_admin_action.assert_called_once()
        details = handler._log_admin_action.call_args.args[4]
        self.assertEqual(2, details["generated_count"])
        self.assertEqual(2, details["team_count"])
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual(result, response.payload)

    def test_offer_promise_create_audits_and_returns_route_response(self):
        promise = {"id": 14, "team_code": "ATL", "status": "active", "player_name": "Player", "role": "Sexto hombre", "season_year": 2026}
        free_agency = SimpleNamespace(create_promise=Mock(return_value=promise))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"email": "admin@example.test"}),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=free_agency),
        )
        payload = {"team_code": "ATL", "profile_id": 7, "role": "Sexto hombre"}

        matched = dispatch_routes(
            handler,
            urlparse("/api/admin/free-agent-offer-promises"),
            POST_ROUTES,
            payload,
        )

        self.assertTrue(matched)
        free_agency.create_promise.assert_called_once_with(payload, {"email": "admin@example.test"})
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual({"ok": True, "promise": promise}, response.payload)

    def test_offer_promise_create_maps_role_limit_to_conflict_route_response(self):
        free_agency = SimpleNamespace(
            create_promise=Mock(side_effect=ValueError("promise_role_limit_exceeded:Sexto hombre:1"))
        )
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"email": "admin@example.test"}),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=free_agency),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/admin/free-agent-offer-promises"),
            POST_ROUTES,
            {"team_code": "ATL"},
        )

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(409, response.status)
        self.assertEqual("promise_role_limit_exceeded", response.payload["error"])
        self.assertEqual("Sexto hombre", response.payload["role"])
        self.assertEqual(1, response.payload["limit"])

    def test_bulk_free_agent_create_returns_route_response(self):
        result = {"created_count": 2, "skipped_count": 0, "created": [{"name": "A"}, {"name": "B"}]}
        free_agency = SimpleNamespace(bulk_create_free_agents=Mock(return_value=result))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=free_agency),
        )

        matched = dispatch_routes(handler, urlparse("/api/free-agents/bulk"), POST_ROUTES, {"names": "A\nB"})

        self.assertTrue(matched)
        free_agency.bulk_create_free_agents.assert_called_once_with("A\nB")
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual(result, response.payload)

    def test_create_free_agent_maps_missing_name_to_route_response(self):
        free_agency = SimpleNamespace(create_free_agent=Mock(return_value=None))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=free_agency),
        )

        matched = dispatch_routes(handler, urlparse("/api/free-agents"), POST_ROUTES, {"name": ""})

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(400, response.status)
        self.assertEqual({"error": "name_required"}, response.payload)

    def test_create_free_agent_audits_and_returns_route_response(self):
        free_agency = SimpleNamespace(create_free_agent=Mock(return_value=23))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(free_agency=free_agency),
        )

        matched = dispatch_routes(handler, urlparse("/api/free-agents"), POST_ROUTES, {"name": "Player"})

        self.assertTrue(matched)
        handler._log_admin_action.assert_called_once_with("create", "free_agent", "23", None, {"name": "Player"})
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual({"free_agent_id": 23}, response.payload)

    def test_create_draft_order_audits_and_returns_route_response(self):
        draft = SimpleNamespace(create_order_entry=Mock(return_value=31))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(draft=draft),
        )
        payload = {"draft_year": 2026, "draft_round": "1st", "pick_number": 3, "owner_team_code": "ATL"}

        matched = dispatch_routes(handler, urlparse("/api/draft-order"), POST_ROUTES, payload)

        self.assertTrue(matched)
        draft.create_order_entry.assert_called_once_with(payload)
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual({"draft_order_id": 31}, response.payload)

    def test_create_draft_order_maps_validation_error_to_route_response(self):
        draft = SimpleNamespace(create_order_entry=Mock(side_effect=ValueError("invalid_pick_number")))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _send_route_response=Mock(),
            app=SimpleNamespace(draft=draft),
        )

        matched = dispatch_routes(handler, urlparse("/api/draft-order"), POST_ROUTES, {})

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(400, response.status)
        self.assertEqual({"error": "invalid_pick_number"}, response.payload)

    def test_create_salary_history_audits_and_returns_route_response(self):
        row = {"id": 44, "team_code": "ATL", "season_year": 2026}
        players = SimpleNamespace(create_salary_history=Mock(return_value=row))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(players=players),
        )
        payload = {"season_year": 2026, "salary_text": "1.000.000"}

        matched = dispatch_routes(handler, urlparse("/api/player-profiles/7/salary-history"), POST_ROUTES, payload)

        self.assertTrue(matched)
        players.create_salary_history.assert_called_once_with(7, payload)
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual({"salary_history": row}, response.payload)

    def test_create_player_transaction_audits_and_returns_route_response(self):
        players = SimpleNamespace(create_transaction=Mock(return_value=55))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(players=players),
        )
        payload = {"team_code": "ATL", "summary": "Signed"}

        matched = dispatch_routes(handler, urlparse("/api/player-profiles/7/transactions"), POST_ROUTES, payload)

        self.assertTrue(matched)
        players.create_transaction.assert_called_once_with(7, payload)
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual({"transaction_id": 55}, response.payload)

    def test_create_move_adjustment_returns_route_response(self):
        trades = SimpleNamespace(adjust_team_move_remaining=Mock(return_value={"team_code": "ATL", "remaining": 2}))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(trades=trades),
        )
        payload = {"season_year": 2026, "target_remaining": 2, "bucket": "regular"}

        matched = dispatch_routes(handler, urlparse("/api/teams/ATL/move-adjustment"), POST_ROUTES, payload)

        self.assertTrue(matched)
        trades.adjust_team_move_remaining.assert_called_once_with("ATL", 2026, "regular", 2, None)
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True, "result": {"team_code": "ATL", "remaining": 2}}, response.payload)

    def test_asset_frozen_pick_dead_contract_and_gm_history_create_return_route_responses(self):
        assets = SimpleNamespace(
            create_asset=Mock(return_value=61),
            create_frozen_pick=Mock(return_value={"id": 62, "team_code": "ATL"}),
            create_dead_contract=Mock(return_value=63),
        )
        teams = SimpleNamespace(replace_gm_history=Mock(return_value=[{"name": "GM"}]))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(assets=assets, teams=teams),
        )

        cases = (
            ("/api/assets", {"team_code": "ATL", "asset_type": "draft_pick"}, {"asset_id": 61}),
            ("/api/frozen-draft-picks", {"team_code": "ATL"}, {"ok": True, "frozen_pick": {"id": 62, "team_code": "ATL"}}),
            ("/api/dead-contracts", {"team_code": "ATL", "label": "Dead"}, {"dead_contract_id": 63}),
            ("/api/gm-history", {"team_code": "ATL", "entries": [{"name": "GM"}]}, {"ok": True, "gm_history": [{"name": "GM"}]}),
        )
        for path, payload, expected in cases:
            handler._send_route_response.reset_mock()
            with self.subTest(path=path):
                matched = dispatch_routes(handler, urlparse(path), POST_ROUTES, payload)
                self.assertTrue(matched)
                response = handler._send_route_response.call_args.args[0]
                self.assertEqual(expected, response.payload)
                self.assertIn(response.status, {200, 201})

    def test_post_draft_settings_route_delegates_to_draft_service(self):
        result = {"draft_year": 2026, "enabled": True, "current_pick_id": 4, "duration_seconds": 90}
        draft_service = SimpleNamespace(update_live_settings=Mock(return_value=result))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _require_csrf=Mock(return_value=True),
            app=SimpleNamespace(draft=draft_service),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/draft-live/settings"),
            POST_ROUTES,
            {"draft_year": 2026, "enabled": True},
        )

        self.assertTrue(matched)
        draft_service.update_live_settings.assert_called_once_with({"draft_year": 2026, "enabled": True})
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual(result, response.payload)
        handler._log_admin_action.assert_called_once()

    def test_patch_team_economy_route_validates_and_audits(self):
        settings = SimpleNamespace(
            upsert_team_economy=Mock(return_value={"updated": 2})
        )
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(settings=settings),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/tracker/economy"),
            PATCH_ROUTES,
            {"season_year": 2027, "rows": [{"team_code": "ATL"}, {"team_code": "BOS"}]},
        )

        self.assertTrue(matched)
        settings.upsert_team_economy.assert_called_once_with(
            2027,
            [{"team_code": "ATL"}, {"team_code": "BOS"}],
        )
        handler._log_admin_action.assert_called_once()
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True, "updated": 2}, response.payload)

    def test_coadmin_vote_create_audit_includes_command_metadata(self):
        vote = {"id": 8, "title": "Valor GM", "status": "open", "created_at": "2026-07-21T10:00:00Z"}
        coadmin_votes = SimpleNamespace(create_coadmin_vote=Mock(return_value=vote))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"email": "admin@example.test"}),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(coadmin_votes=coadmin_votes),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/admin/coadmin-votes"),
            POST_ROUTES,
            {"title": "Valor GM"},
        )

        self.assertTrue(matched)
        audit_kwargs = handler._log_admin_action.call_args.kwargs
        self.assertEqual("coadmin-vote:8:create", audit_kwargs["command_id"])
        self.assertEqual("valid", audit_kwargs["validation_result"])
        self.assertEqual(8, audit_kwargs["entity_versions"]["vote_id"])
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(201, response.status)
        self.assertEqual({"ok": True, "vote": vote}, response.payload)

    def test_admin_minimum_target_remove_audit_includes_command_metadata(self):
        result = {"user_id": 4, "rank": 2, "removed": True}
        gm_minimum_targets = SimpleNamespace(remove=Mock(return_value=result))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _require_csrf=Mock(return_value=True),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            app=SimpleNamespace(gm_minimum_targets=gm_minimum_targets),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/admin/gm-minimum-targets/remove"),
            POST_ROUTES,
            {"user_id": 4, "rank": 2},
        )

        self.assertTrue(matched)
        audit_kwargs = handler._log_admin_action.call_args.kwargs
        self.assertEqual("gm-minimum-target:4:2:remove", audit_kwargs["command_id"])
        self.assertEqual("valid", audit_kwargs["validation_result"])
        self.assertEqual({"user_id": 4, "rank": 2, "removed": True}, audit_kwargs["entity_versions"])
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual({"ok": True, **result}, response.payload)

    def test_backup_download_audit_includes_command_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = Path(temp_dir) / "league.db"
            backup_path.write_bytes(b"sqlite-data")
            backup = {"id": "backup-1", "path": str(backup_path), "sha256": "abc123"}
            handler = SimpleNamespace(
                _require_csrf=Mock(return_value=True),
                _require_sensitive_rate_limit=Mock(return_value=True),
                _authorize=Mock(return_value=True),
                _log_admin_action=Mock(),
                _send_route_response=Mock(),
                app=SimpleNamespace(maintenance=SimpleNamespace(create_verified_backup=Mock(return_value=backup))),
            )

            matched = dispatch_routes(handler, urlparse("/api/admin/backup"), POST_ROUTES, {})

        self.assertTrue(matched)
        audit_kwargs = handler._log_admin_action.call_args.kwargs
        self.assertEqual("backup:backup-1:download", audit_kwargs["command_id"])
        self.assertEqual("valid", audit_kwargs["validation_result"])
        self.assertEqual("backup-1", audit_kwargs["entity_versions"]["backup_id"])

    def test_owner_import_audit_includes_command_metadata(self):
        backup = {"id": "backup-import-1", "path": "/tmp/league.db", "sha256": "def456"}
        result = {"ok": True, "seasons": [2026], "record_count": 3, "group_count": 1}
        owner_imports = SimpleNamespace(apply_owner_economy_import=Mock(return_value=result))
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _json=Mock(),
            app=SimpleNamespace(
                maintenance=SimpleNamespace(
                    create_verified_backup=Mock(return_value=backup),
                    public_backup_metadata=Mock(return_value={"id": backup["id"]}),
                ),
                owner_imports=owner_imports,
            ),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/admin/economy-import/import"),
            POST_ROUTES,
            {"records": [{"team_code": "ATL"}]},
        )

        self.assertTrue(matched)
        audit_kwargs = handler._log_admin_action.call_args.kwargs
        self.assertEqual("owner_economy:import:backup-import-1", audit_kwargs["command_id"])
        self.assertEqual("valid", audit_kwargs["validation_result"])
        self.assertEqual([2026], audit_kwargs["entity_versions"]["seasons"])

    def test_press_publication_audit_includes_command_metadata(self):
        result = {
            "article_id": 12,
            "channel_id": "channel-1",
            "message_id": "message-9",
            "article_url": "https://example.test/news?article=12",
        }
        handler = SimpleNamespace(
            _require_csrf=Mock(return_value=True),
            _require_sensitive_rate_limit=Mock(return_value=True),
            _authorize=Mock(return_value=True),
            _current_session=Mock(return_value={"email": "admin@example.test"}),
            _public_url=Mock(return_value="https://example.test/news?article=12"),
            _log_admin_action=Mock(),
            _json=Mock(),
            app=SimpleNamespace(press_publication=SimpleNamespace(publish=Mock(return_value=result))),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/admin/launch-article"),
            POST_ROUTES,
            {"text": "Article text"},
        )

        self.assertTrue(matched)
        audit_kwargs = handler._log_admin_action.call_args.kwargs
        self.assertEqual("press-article:12:launch", audit_kwargs["command_id"])
        self.assertEqual("valid", audit_kwargs["validation_result"])
        self.assertEqual("message-9", audit_kwargs["entity_versions"]["message_id"])


if __name__ == "__main__":
    unittest.main()
