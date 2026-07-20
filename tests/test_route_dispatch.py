import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

from app.routes import DELETE_ROUTES, GET_ROUTES, OWNER_OFFICE_MULTIPART_POST_ROUTES, PATCH_ROUTES, POST_ROUTES
from app.routing import dispatch_routes, exact_route, predicate_route, prefix_route
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

    def test_gm_office_routes_are_registered_by_http_method(self):
        self.assertTrue(any(route.matches("/api/gm-office") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/gm-office/minimum-targets") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/admin/gm-minimum-targets/order") for route in GET_ROUTES))
        self.assertTrue(any(route.matches("/api/gm-office/depth-chart") for route in POST_ROUTES))
        self.assertTrue(any(route.matches("/api/gm-office/minimum-targets/omit") for route in POST_ROUTES))
        self.assertFalse(any(route.matches("/api/gm-office/depth-chart") for route in GET_ROUTES))

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
        ):
            self.assertTrue(any(route.matches(path) for route in GET_ROUTES), path)
        for path in (
            "/api/auth/login",
            "/api/trades/process",
            "/api/player-profiles/4/merge",
            "/api/assets",
            "/api/settings/progress-year",
        ):
            self.assertTrue(any(route.matches(path) for route in POST_ROUTES), path)
        for path in (
            "/api/admin/gm-draft-pick-requests/4",
            "/api/settings",
            "/api/players/4",
            "/api/teams/ATL",
            "/api/dead-contracts/4",
        ):
            self.assertTrue(any(route.matches(path) for route in PATCH_ROUTES), path)

    def test_get_draft_route_rejects_invalid_year_before_service_call(self):
        draft_service = Mock()
        handler = SimpleNamespace(
            _json=Mock(),
            app=SimpleNamespace(draft=draft_service),
        )

        matched = dispatch_routes(handler, urlparse("/api/draft-order?year=invalid"), GET_ROUTES)

        self.assertTrue(matched)
        handler._json.assert_called_once_with(400, {"error": "invalid_draft_year"})
        draft_service.list_order.assert_not_called()

    def test_delete_route_preserves_authorization_audit_and_response(self):
        delete_free_agent = Mock(return_value=True)
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _json=Mock(),
            app=SimpleNamespace(
                free_agency=SimpleNamespace(
                    repository=SimpleNamespace(delete_free_agent=delete_free_agent)
                )
            ),
        )

        matched = dispatch_routes(handler, urlparse("/api/free-agents/17"), DELETE_ROUTES)

        self.assertTrue(matched)
        handler._authorize.assert_called_once_with("admin.free_agent.write")
        delete_free_agent.assert_called_once_with(17)
        handler._log_admin_action.assert_called_once_with("delete", "free_agent", "17")
        handler._json.assert_called_once_with(200, {"ok": True})

    def test_post_draft_settings_route_delegates_to_draft_service(self):
        result = {"draft_year": 2026, "enabled": True, "current_pick_id": 4, "duration_seconds": 90}
        draft_service = SimpleNamespace(update_live_settings=Mock(return_value=result))
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _require_csrf=Mock(return_value=True),
            app=SimpleNamespace(draft=draft_service),
            _log_admin_action=Mock(),
            _json=Mock(),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/draft-live/settings"),
            POST_ROUTES,
            {"draft_year": 2026, "enabled": True},
        )

        self.assertTrue(matched)
        draft_service.update_live_settings.assert_called_once_with({"draft_year": 2026, "enabled": True})
        handler._json.assert_called_once_with(200, result)
        handler._log_admin_action.assert_called_once()

    def test_patch_team_economy_route_validates_and_audits(self):
        settings_repository = SimpleNamespace(
            upsert_team_economy=Mock(return_value={"updated": 2})
        )
        handler = SimpleNamespace(
            _authorize=Mock(return_value=True),
            _log_admin_action=Mock(),
            _json=Mock(),
            app=SimpleNamespace(settings_repository=settings_repository),
        )

        matched = dispatch_routes(
            handler,
            urlparse("/api/tracker/economy"),
            PATCH_ROUTES,
            {"season_year": 2027, "rows": [{"team_code": "ATL"}, {"team_code": "BOS"}]},
        )

        self.assertTrue(matched)
        settings_repository.upsert_team_economy.assert_called_once_with(
            2027,
            [{"team_code": "ATL"}, {"team_code": "BOS"}],
        )
        handler._log_admin_action.assert_called_once()
        handler._json.assert_called_once_with(200, {"ok": True, "updated": 2})


if __name__ == "__main__":
    unittest.main()
