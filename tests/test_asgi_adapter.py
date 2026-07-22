import asyncio
import json
import unittest
from types import SimpleNamespace
from urllib.parse import urlparse

from app.asgi import create_asgi_app
from app.routes import DELETE_ROUTES, PATCH_ROUTES, POST_ROUTES
from app.routing import RouteResponse, dispatch_routes


def run_asgi_request(
    app,
    *,
    path: str,
    method: str = "GET",
    query_string: bytes = b"",
    body: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
):
    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "method": method,
                "path": path,
                "query_string": query_string,
                "headers": headers or [],
            },
            receive,
            send,
        )
    )
    status = messages[0]["status"]
    body = messages[1]["body"]
    headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in messages[0]["headers"]}
    try:
        decoded_body = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        decoded_body = body
    return status, decoded_body, headers


def route_response_tuple(response: RouteResponse):
    if response.body is not None:
        body = response.body
    else:
        body = json.loads(json.dumps(response.payload).encode("utf-8").decode("utf-8"))
    return response.status, body, response.content_type


def authorized_context(application):
    return SimpleNamespace(
        app=application,
        response=None,
        headers={},
        _require_csrf=lambda: True,
        _require_sensitive_rate_limit=lambda *_args, **_kwargs: True,
        _authorize=lambda *_args, **_kwargs: True,
        _validate_specialized_payload_or_error=lambda payload, validator, **kwargs: (
            validator(payload, **kwargs) or True
        ),
        _current_session=lambda: {"user_id": 4, "role": "gm", "team_codes": ["ATL"]},
        _current_session_team_codes=lambda: ["ATL"],
        _log_admin_action=lambda *_args, **_kwargs: None,
    )


def login_context(_application):
    return SimpleNamespace(
        response=None,
        admin_user="admin",
        admin_password="secret",
        admin_password_hash="",
        _client_ip=lambda: "127.0.0.1",
        _rate_limit_status=lambda _ip: (False, 0),
        _rate_limit_fail=lambda _ip: None,
        _rate_limit_success=lambda _ip: None,
        _start_session=lambda _session: ("session-token", "csrf-token"),
        _session_cookie=lambda _token: "session=session-token; HttpOnly",
    )


def call_through_stdlib_dispatch(application, routes, *, path: str, payload=None, context_factory=None):
    context = context_factory(application) if callable(context_factory) else SimpleNamespace(app=application)
    context.response = None

    def send_route_response(response):
        context.response = response

    context._send_route_response = send_route_response
    matched = dispatch_routes(context, urlparse(path), routes, payload)
    if not matched:
        return 404, {"error": "not_found"}, "application/json; charset=utf-8"
    return route_response_tuple(context.response)


class AsgiAdapterTests(unittest.TestCase):
    def test_asgi_adapter_serves_converted_public_get_route(self):
        application = SimpleNamespace(
            teams=SimpleNamespace(list=lambda: [{"code": "ATL"}]),
            settings_repository=SimpleNamespace(get_all=lambda: {}),
            press_articles=SimpleNamespace(
                list=lambda limit=50: [],
                get=lambda article_id: {"id": article_id, "title": "Draft night"},
                image=lambda article_id: (b"image-bytes", "image/png"),
            ),
            waivers=SimpleNamespace(list_waivers=lambda _session: {"waivers": []}),
            free_agency=SimpleNamespace(
                list_free_agents=lambda _team_codes=(): {
                    "free_agents": [{"id": 7, "name": "Player", "is_favorite": False}],
                },
            ),
            draft=SimpleNamespace(
                list_order=lambda draft_year=None: {"draft_year": draft_year, "order": []},
                list_pick_ledger=lambda draft_year=None: {"draft_year": draft_year, "ledger": []},
                list_live=lambda draft_year=None: {"draft_year": draft_year, "live": []},
            ),
        )

        status, body, _headers = run_asgi_request(create_asgi_app(application), path="/api/teams")

        self.assertEqual(200, status)
        self.assertEqual({"teams": [{"code": "ATL"}]}, body)

        status, body, _headers = run_asgi_request(create_asgi_app(application), path="/api/free-agents")

        self.assertEqual(200, status)
        self.assertEqual({"free_agents": [{"id": 7, "name": "Player", "is_favorite": False}]}, body)

    def test_asgi_adapter_serves_public_article_json_and_image_routes(self):
        application = SimpleNamespace(
            teams=SimpleNamespace(list=lambda: []),
            settings_repository=SimpleNamespace(get_all=lambda: {}),
            press_articles=SimpleNamespace(
                list=lambda limit=50: [],
                get=lambda article_id: {"id": article_id, "title": "Draft night"},
                image=lambda article_id: (b"image-bytes", "image/png"),
            ),
            waivers=SimpleNamespace(list_waivers=lambda _session: {"waivers": []}),
            draft=SimpleNamespace(
                list_order=lambda draft_year=None: {"draft_year": draft_year, "order": []},
                list_pick_ledger=lambda draft_year=None: {"draft_year": draft_year, "ledger": []},
                list_live=lambda draft_year=None: {"draft_year": draft_year, "live": []},
            ),
        )
        app = create_asgi_app(application)

        status, body, _headers = run_asgi_request(app, path="/api/news/articles/7")
        self.assertEqual(200, status)
        self.assertEqual({"article": {"id": 7, "title": "Draft night"}}, body)

        status, body, headers = run_asgi_request(app, path="/api/news/articles/7/image")
        self.assertEqual(200, status)
        self.assertEqual(b"image-bytes", body)
        self.assertEqual("image/png", headers["content-type"])

    def test_asgi_adapter_maps_validation_and_method_errors(self):
        application = SimpleNamespace(
            teams=SimpleNamespace(list=lambda: []),
            settings_repository=SimpleNamespace(get_all=lambda: {}),
            press_articles=SimpleNamespace(list=lambda limit=50: [], get=lambda _id: None, image=lambda _id: None),
            waivers=SimpleNamespace(list_waivers=lambda _session: {"waivers": []}),
            draft=SimpleNamespace(
                list_order=lambda draft_year=None: {"draft_year": draft_year, "order": []},
                list_pick_ledger=lambda draft_year=None: {"draft_year": draft_year, "ledger": []},
                list_live=lambda draft_year=None: {"draft_year": draft_year, "live": []},
            ),
        )
        app = create_asgi_app(application)

        status, body, _headers = run_asgi_request(app, path="/api/draft-order", query_string=b"year=bad")
        self.assertEqual(400, status)
        self.assertEqual({"error": "invalid_draft_year"}, body)

        status, body, _headers = run_asgi_request(app, path="/api/teams", method="POST")
        self.assertEqual(405, status)
        self.assertEqual({"error": "method_not_allowed"}, body)

    def test_post_route_contract_is_equivalent_through_stdlib_dispatch_and_asgi(self):
        application = SimpleNamespace(
            trades=SimpleNamespace(validate=lambda payload: {"valid": True, "payload": payload}),
        )
        payload = {"teams": [{"code": "ATL"}]}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/trades/validate")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/trades/validate",
            payload=payload,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes),
            path="/api/trades/validate",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_protected_post_route_contract_is_equivalent_when_context_is_explicit(self):
        free_agency = SimpleNamespace(
            set_spending_limit=lambda team_code, amount, session: {
                "team_code": team_code,
                "amount_millions": amount,
                "actor": session["user_id"],
            }
        )
        application = SimpleNamespace(free_agency=free_agency)
        payload = {"team_code": "ATL", "amount_millions": 12.5}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/gm-office/free-agent-spending-limit")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/gm-office/free-agent-spending-limit",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/gm-office/free-agent-spending-limit",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_login_contract_preserves_cookie_header_through_stdlib_and_asgi(self):
        application = SimpleNamespace()
        payload = {"username": "admin", "password": "secret"}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/auth/login")
        stdlib_context = login_context(application)

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/auth/login",
            payload=payload,
            context_factory=lambda _application: stdlib_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=login_context),
            path="/api/auth/login",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))
        self.assertEqual(stdlib_context.response.headers["Set-Cookie"], asgi_headers["set-cookie"])

    def test_coadmin_vote_create_contract_is_equivalent_through_stdlib_and_asgi(self):
        vote = {"id": 8, "title": "Valor GM", "status": "open", "created_at": "2026-07-21T10:00:00Z"}
        application = SimpleNamespace(
            coadmin_votes=SimpleNamespace(create_coadmin_vote=lambda title, _session: {**vote, "title": title}),
        )
        payload = {"title": "Valor GM"}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/admin/coadmin-votes")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/admin/coadmin-votes",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/admin/coadmin-votes",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_trade_process_validate_contract_is_equivalent_through_stdlib_and_asgi(self):
        application = SimpleNamespace(
            trades=SimpleNamespace(
                validate_process_payload=lambda payload: {"valid": True, "teams": [payload["team_a"], payload["team_b"]]},
            ),
        )
        payload = {"team_a": "atl", "team_b": "bos"}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/trades/process/validate")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/trades/process/validate",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/trades/process/validate",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_gm_option_request_contract_is_equivalent_through_stdlib_and_asgi(self):
        request = {"id": 11, "player_id": 7, "status": "pending"}
        application = SimpleNamespace(
            players=SimpleNamespace(record=lambda _player_id: {"id": 7, "team_code": "ATL"}),
            gm_request_queries=SimpleNamespace(
                create_option=lambda player_id, option_field, option_value, action, _session: {
                    **request,
                    "player_id": player_id,
                    "option_field": option_field,
                    "option_value": option_value,
                    "action": action,
                }
            ),
        )
        payload = {
            "player_id": 7,
            "option_field": "option_2027",
            "option_value": "po",
            "action": "accepted",
        }
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/gm/option-requests")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/gm/option-requests",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/gm/option-requests",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_offseason_exception_generate_contract_is_equivalent_through_stdlib_and_asgi(self):
        result = {"generated": [{"team_code": "ATL", "created": [{"exception": "MLE"}]}], "skipped": []}
        application = SimpleNamespace(
            offseason_exceptions=SimpleNamespace(
                generate=lambda season_year, *, team_codes=None, choices=None: {
                    **result,
                    "season_year": season_year,
                    "team_codes": team_codes,
                    "choices": choices,
                }
            ),
        )
        payload = {"season_year": 2026, "team_codes": ["ATL"], "choices": {"ATL": "non_tax"}}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/offseason-exceptions/generate")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/offseason-exceptions/generate",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/offseason-exceptions/generate",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_offer_promise_create_contract_is_equivalent_through_stdlib_and_asgi(self):
        promise = {"id": 14, "team_code": "ATL", "status": "active", "player_name": "Player"}
        application = SimpleNamespace(
            free_agency=SimpleNamespace(
                create_promise=lambda payload, _session: {
                    **promise,
                    "team_code": payload["team_code"],
                    "role": payload["role"],
                }
            )
        )
        payload = {"team_code": "ATL", "profile_id": 7, "role": "Sexto hombre"}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/admin/free-agent-offer-promises")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/admin/free-agent-offer-promises",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/admin/free-agent-offer-promises",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_draft_order_create_contract_is_equivalent_through_stdlib_and_asgi(self):
        application = SimpleNamespace(draft=SimpleNamespace(create_order_entry=lambda _payload: 31))
        payload = {"draft_year": 2026, "draft_round": "1st", "pick_number": 3, "owner_team_code": "ATL"}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/draft-order")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/draft-order",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/draft-order",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_trade_process_contract_is_equivalent_through_stdlib_and_asgi(self):
        trade_result = {"trade_id": 42}

        application = SimpleNamespace(
            trades=SimpleNamespace(
                request_team_codes=lambda payload: [payload["team_a"], payload["team_b"]],
                process_request=lambda _payload, **_kwargs: {
                    "status_code": 200,
                    "response": {"ok": True, "result": trade_result},
                    "result": trade_result,
                    "team_codes": ["ATL", "BOS"],
                    "outbox_event_ids": [91],
                    "audit": {
                        "details": {
                            "command_id": "trade:42",
                            "validation_result": "valid",
                            "entity_versions": {"trade": 3},
                        },
                        "before": {"status": "pending"},
                        "after": {"status": "processed"},
                    },
                },
            ),
            outbox_delivery=SimpleNamespace(dispatch=lambda event_ids: list(event_ids or [])),
        )
        payload = {"team_a": "ATL", "team_b": "BOS"}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/trades/process")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/trades/process",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/trades/process",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_settings_progress_year_contract_is_equivalent_through_stdlib_and_asgi(self):
        result = {
            "previous_year": 2026,
            "current_year": 2027,
            "command_id": "season:2027",
            "validation_result": "valid",
            "entity_versions": {"settings": 8},
        }
        application = SimpleNamespace(
            season_rollover=SimpleNamespace(progress_to_next_year=lambda **_kwargs: result),
            settings=SimpleNamespace(get_all=lambda: {"current_year": 2027, "discord_bot_token": "redacted"}),
        )
        payload = {"expected_current_year": 2026, "expected_current_year_version": 7}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in POST_ROUTES if route.path == "/api/settings/progress-year")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/settings/progress-year",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/settings/progress-year",
            method="POST",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_patch_route_contract_is_equivalent_through_stdlib_and_asgi(self):
        application = SimpleNamespace(
            settings=SimpleNamespace(upsert_team_economy=lambda season_year, rows: {"season_year": season_year, "updated": len(rows)})
        )
        payload = {"season_year": 2027, "rows": [{"team_code": "ATL"}, {"team_code": "BOS"}]}
        body = json.dumps(payload).encode("utf-8")
        routes = tuple(route for route in PATCH_ROUTES if route.path == "/api/tracker/economy")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/tracker/economy",
            payload=payload,
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/tracker/economy",
            method="PATCH",
            body=body,
            headers=[(b"content-type", b"application/json")],
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))

    def test_delete_route_contract_is_equivalent_through_stdlib_and_asgi(self):
        application = SimpleNamespace(
            free_agency=SimpleNamespace(delete_free_agent=lambda free_agent_id: free_agent_id == 17)
        )
        routes = tuple(route for route in DELETE_ROUTES if route.path == "/api/free-agents/")

        stdlib_result = call_through_stdlib_dispatch(
            application,
            routes,
            path="/api/free-agents/17",
            context_factory=authorized_context,
        )
        asgi_status, asgi_body, asgi_headers = run_asgi_request(
            create_asgi_app(application, routes, context_factory=authorized_context),
            path="/api/free-agents/17",
            method="DELETE",
        )

        self.assertEqual(stdlib_result, (asgi_status, asgi_body, asgi_headers["content-type"]))


if __name__ == "__main__":
    unittest.main()
