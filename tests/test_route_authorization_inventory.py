from types import SimpleNamespace
from urllib.parse import urlparse
import unittest
from unittest.mock import Mock

from app.auth.policies import AuthorizationError, AUTH_POLICIES, authorization_actor_from_session, authorize_action
from app.routes import (
    DELETE_ROUTES,
    EARLY_POST_ROUTES,
    OWNER_OFFICE_MULTIPART_POST_ROUTES,
    PATCH_ROUTES,
    POST_ROUTES,
)
from app.routing import dispatch_routes


UNSAFE_ROUTES = (
    *EARLY_POST_ROUTES,
    *OWNER_OFFICE_MULTIPART_POST_ROUTES,
    *POST_ROUTES,
    *PATCH_ROUTES,
    *DELETE_ROUTES,
)


class AuthorizingRouteHandler(SimpleNamespace):
    def __init__(self, session, app):
        super().__init__(
            app=app,
            _json=Mock(),
            _log_admin_action=Mock(),
            _send_route_response=Mock(),
            log_error=Mock(),
        )
        self._session = session
        self._require_csrf = Mock(return_value=True)
        self._require_sensitive_rate_limit = Mock(return_value=True)
        self._validate_specialized_payload_or_error = Mock(return_value=True)

    def _current_session(self):
        return self._session

    def _current_session_team_codes(self):
        actor = authorization_actor_from_session(self._session)
        return list((actor or {}).get("team_codes") or [])

    def _is_admin(self):
        return str((self._session or {}).get("role") or "").lower() == "admin"

    def _authorize(self, action, resource=None):
        try:
            return authorize_action(authorization_actor_from_session(self._session), action, resource)
        except AuthorizationError as err:
            self._json(err.status, {"error": err.error})
            return False


def session(role: str, teams=None):
    return {
        "user_id": 1,
        "email": f"{role or 'guest'}@example.test",
        "role": role,
        "team_codes": teams or [],
    }


class RouteAuthorizationInventoryTests(unittest.TestCase):
    def test_all_unsafe_routes_have_machine_readable_auth_metadata(self) -> None:
        violations = []
        for route in UNSAFE_ROUTES:
            if route.auth_exempt_reason:
                continue
            if route.method not in {"POST", "PATCH", "PUT", "DELETE"}:
                violations.append(f"{route.name}: missing unsafe HTTP method")
            if not route.permission:
                violations.append(f"{route.method} {route.path or route.name}: missing permission")
            if not route.csrf:
                violations.append(f"{route.method} {route.path or route.name}: missing csrf=True")
        self.assertEqual([], violations)

    def test_route_permissions_are_known_policy_names(self) -> None:
        unknown = sorted(
            f"{route.method} {route.path or route.name}: {route.permission}"
            for route in UNSAFE_ROUTES
            if route.permission and route.permission not in AUTH_POLICIES
        )
        self.assertEqual([], unknown)

    def test_mutating_routes_are_not_auth_exempt(self) -> None:
        exempt_mutations = [
            f"{route.method} {route.path or route.name}: {route.auth_exempt_reason}"
            for route in UNSAFE_ROUTES
            if route.mutates_league_state and route.auth_exempt_reason
        ]
        self.assertEqual([], exempt_mutations)

    def test_expected_high_risk_route_inventory_entries(self) -> None:
        by_path = {(route.method, route.path or route.name): route for route in UNSAFE_ROUTES}
        expected = {
            ("POST", "/api/trades/process"): ("admin.trade.process", True),
            ("POST", "/api/trades/archive/import"): ("admin.trade_archive.write", True),
            ("POST", "/api/waiting-list"): ("admin.waiting_list.write", True),
            ("PATCH", "/api/waiting-list/"): ("admin.waiting_list.write", True),
            ("DELETE", "/api/waiting-list/"): ("admin.waiting_list.write", True),
            ("POST", "/api/gm-office/depth-chart"): ("gm_office.depth_chart.update", True),
            ("PATCH", "/api/admin/gm-free-agent-offer-requests/"): (
                "admin.gm_free_agent_offer_request.decide",
                True,
            ),
            ("POST", "/api/draft-live/process"): ("admin.draft_live.write", True),
        }
        for key, (permission, csrf) in expected.items():
            with self.subTest(route=key):
                route = by_path[key]
                self.assertEqual(permission, route.permission)
                self.assertEqual(csrf, route.csrf)
                self.assertTrue(route.mutates_league_state)

    def test_depth_chart_direct_api_role_matrix(self) -> None:
        cases = (
            ("guest", None, False),
            ("gm-own", session("gm", ["ATL"]), True),
            ("gm-other", session("gm", ["BOS"]), False),
            ("agent", session("agent", ["ATL"]), False),
            ("admin", session("admin"), True),
        )
        for label, actor_session, allowed in cases:
            with self.subTest(actor=label):
                depth_charts = SimpleNamespace(set=Mock(return_value={"team_code": "ATL"}))
                handler = AuthorizingRouteHandler(actor_session, SimpleNamespace(depth_charts=depth_charts))
                matched = dispatch_routes(
                    handler,
                    urlparse("/api/gm-office/depth-chart"),
                    POST_ROUTES,
                    {"team_code": "ATL", "entries": [{"position": "PG", "depth_order": 1, "player_id": 7}]},
                )
                self.assertTrue(matched)
                self.assertEqual(allowed, depth_charts.set.called)

    def test_free_agent_offer_approval_direct_api_role_matrix(self) -> None:
        request = {"id": 9, "status": "pending", "team_code": "ATL", "free_agent_id": 7}
        cases = (
            ("guest", None, False),
            ("gm-own", session("gm", ["ATL"]), False),
            ("gm-other", session("gm", ["BOS"]), False),
            ("agent", session("agent", ["ATL"]), False),
            ("admin", session("admin"), True),
        )
        for label, actor_session, allowed in cases:
            with self.subTest(actor=label):
                free_agency = SimpleNamespace(
                    offer_request=Mock(return_value=dict(request)),
                    decide_offer=Mock(return_value={
                        "decision": "rejected",
                        "request": {"status": "rejected"},
                        "request_before": dict(request),
                        "outbox_event_ids": [],
                    }),
                    admin_decision_output=Mock(return_value={
                        "response": {"ok": True, "request": {"status": "rejected"}},
                        "audit": {"action": "reject", "details": {}},
                    }),
                )
                app = SimpleNamespace(free_agency=free_agency, outbox_delivery=SimpleNamespace(dispatch=Mock()))
                handler = AuthorizingRouteHandler(actor_session, app)
                matched = dispatch_routes(
                    handler,
                    urlparse("/api/admin/gm-free-agent-offer-requests/9"),
                    PATCH_ROUTES,
                    {"decision": "rejected"},
                )
                self.assertTrue(matched)
                self.assertEqual(allowed, free_agency.decide_offer.called)

    def test_draft_pick_submission_direct_api_role_matrix(self) -> None:
        cases = (
            ("guest", None, False),
            ("current-owner", session("gm", ["ATL"]), True),
            ("other-gm", session("gm", ["BOS"]), False),
            ("agent", session("agent", ["ATL"]), False),
            ("admin", session("admin"), True),
        )
        for label, actor_session, allowed in cases:
            with self.subTest(actor=label):
                draft = SimpleNamespace(
                    order_entry=Mock(return_value={"id": 12, "owner_team_code": "ATL", "draft_year": 2026}),
                    submit_pick=Mock(return_value={"draft_live": {"current_pick_id": 13}}),
                )
                handler = AuthorizingRouteHandler(actor_session, SimpleNamespace(draft=draft))
                matched = dispatch_routes(
                    handler,
                    urlparse("/api/draft-live/picks/12"),
                    POST_ROUTES,
                    {"option_value": "Player"},
                )
                self.assertTrue(matched)
                self.assertEqual(allowed, draft.submit_pick.called)


if __name__ == "__main__":
    unittest.main()
