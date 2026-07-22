"""Small ASGI adapter for framework-neutral JSON routes.

This module is intentionally narrow: it proves the route/response boundary
without requiring the project to take a FastAPI or Starlette dependency yet.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse

try:
    from .routes.free_agency import FREE_AGENCY_GET_ROUTES
    from .routes.get import GET_ROUTES as BASE_GET_ROUTES
    from .routes.press import PRESS_GET_ROUTES
    from .routing import Route, RouteResponse, dispatch_routes, error_response, route_with_method
    from .routes.validation import json_write_content_type_supported, parse_json_request_body
except ImportError:  # pragma: no cover - direct script support
    from routes.free_agency import FREE_AGENCY_GET_ROUTES
    from routes.get import GET_ROUTES as BASE_GET_ROUTES
    from routes.press import PRESS_GET_ROUTES
    from routing import Route, RouteResponse, dispatch_routes, error_response, route_with_method
    from routes.validation import json_write_content_type_supported, parse_json_request_body


PUBLIC_ASGI_GET_ROUTE_NAMES = frozenset(
    {
        "exact:/api/teams",
        "exact:/api/news/articles",
        "exact:/api/waivers",
        "exact:/api/draft-order",
        "exact:/api/draft-pick-ledger",
        "exact:/api/draft-live",
        "exact:/api/free-agents",
        "exact:/api/settings",
        "press-article",
    }
)
PUBLIC_ASGI_GET_ROUTES = tuple(
    route_with_method(route, "GET")
    for route in (*BASE_GET_ROUTES, *FREE_AGENCY_GET_ROUTES, *PRESS_GET_ROUTES)
    if route.name in PUBLIC_ASGI_GET_ROUTE_NAMES
)


class _AsgiRouteContext(SimpleNamespace):
    def _current_session(self):
        return None

    def _current_session_team_codes(self):
        return []

    def _send_route_response(self, response: RouteResponse) -> None:
        self.response = response


def _headers(response: RouteResponse) -> list[tuple[bytes, bytes]]:
    header_items: list[tuple[str, str]] = [
        ("content-type", response.content_type),
        ("cache-control", "no-store"),
    ]
    for key, value in response.headers.items():
        normalized_key = str(key).lower()
        if isinstance(value, (list, tuple)):
            header_items.extend((normalized_key, str(item)) for item in value)
        else:
            header_items.append((normalized_key, str(value)))
    return [(key.encode("latin-1"), value.encode("latin-1")) for key, value in header_items]


def _body(response: RouteResponse) -> bytes:
    if response.body is not None:
        return response.body
    return json.dumps(response.payload).encode("utf-8")


class _AsgiHeaders(dict):
    def get(self, key: str, default: Any = None) -> Any:
        lowered = str(key or "").lower()
        for stored_key, value in self.items():
            if str(stored_key).lower() == lowered:
                return value
        return default


def _scope_headers(scope: dict[str, Any]) -> _AsgiHeaders:
    headers = _AsgiHeaders()
    for raw_key, raw_value in scope.get("headers") or []:
        key = raw_key.decode("latin-1") if isinstance(raw_key, bytes) else str(raw_key)
        value = raw_value.decode("latin-1") if isinstance(raw_value, bytes) else str(raw_value)
        headers[key] = value
    return headers


async def _read_body(receive: Any) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            continue
        body = message.get("body") or b""
        if isinstance(body, str):
            body = body.encode("utf-8")
        chunks.append(body)
        if not message.get("more_body"):
            break
    return b"".join(chunks)


def _payload_from_body(headers: _AsgiHeaders, body: bytes) -> Optional[dict[str, Any] | RouteResponse]:
    if not body:
        return {}
    headers_with_length = _AsgiHeaders(headers)
    headers_with_length["Content-Length"] = str(len(body))
    if not json_write_content_type_supported(headers_with_length):
        return error_response(415, "unsupported_media_type")
    try:
        return parse_json_request_body(headers_with_length, lambda length: body[:length])
    except ValueError as err:
        error = str(err) or "invalid_json"
        return error_response(413 if error == "request_too_large" else 400, error)


def _routes_for_method(method: str, routes: Iterable[Route]) -> tuple[Route, ...]:
    normalized = str(method or "GET").upper()
    return tuple(
        route
        for route in routes
        if route.method is None or str(route.method or "").upper() == normalized
    )


def _route_context(application: Any, context_factory: Optional[Callable[[Any], Any]] = None) -> Any:
    context = context_factory(application) if callable(context_factory) else _AsgiRouteContext(app=application)
    if not hasattr(context, "app"):
        context.app = application
    context.response = None
    if not callable(getattr(context, "_send_route_response", None)):
        context._send_route_response = lambda response: setattr(context, "response", response)
    return context


def _response_for_request(
    application: Any,
    method: str,
    path: str,
    query: str,
    routes: Iterable[Route],
    payload: Optional[dict[str, Any]] = None,
    context_factory: Optional[Callable[[Any], Any]] = None,
) -> RouteResponse:
    parsed = urlparse(str(path or "/") + (f"?{query}" if query else ""))
    context = _route_context(application, context_factory)
    try:
        matched = dispatch_routes(context, parsed, tuple(routes), payload)
        return context.response if matched and context.response else error_response(404, "not_found")
    except Exception:
        return error_response(500, "internal_error")


def create_asgi_app(
    application: Any,
    routes: Iterable[Route] = PUBLIC_ASGI_GET_ROUTES,
    *,
    context_factory: Optional[Callable[[Any], Any]] = None,
):
    route_tuple = tuple(routes)

    async def app(scope, receive, send) -> None:
        if scope.get("type") != "http":
            raise RuntimeError("unsupported_scope_type")
        method = str(scope.get("method") or "GET").upper()
        method_routes = _routes_for_method(method, route_tuple)
        if not method_routes:
            response = error_response(405, "method_not_allowed")
        else:
            payload: Optional[dict[str, Any]] = None
            if method in {"POST", "PATCH", "PUT"}:
                parsed_payload = _payload_from_body(_scope_headers(scope), await _read_body(receive))
                if isinstance(parsed_payload, RouteResponse):
                    response = parsed_payload
                    body = _body(response)
                    await send(
                        {
                            "type": "http.response.start",
                            "status": response.status,
                            "headers": [*_headers(response), (b"content-length", str(len(body)).encode("ascii"))],
                        }
                    )
                    await send({"type": "http.response.body", "body": body})
                    return
                payload = parsed_payload
            raw_query = scope.get("query_string") or b""
            query = raw_query.decode("latin-1") if isinstance(raw_query, bytes) else str(raw_query)
            response = _response_for_request(
                application,
                method,
                str(scope.get("path") or "/"),
                query,
                method_routes,
                payload,
                context_factory,
            )
        body = _body(response)
        await send(
            {
                "type": "http.response.start",
                "status": response.status,
                "headers": [*_headers(response), (b"content-length", str(len(body)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return app


def create_fastapi_app(
    application: Any,
    routes: Iterable[Route] = PUBLIC_ASGI_GET_ROUTES,
    *,
    context_factory: Optional[Callable[[Any], Any]] = None,
):
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, Response
    except ImportError as err:  # pragma: no cover - optional framework dependency.
        raise RuntimeError("fastapi_not_installed") from err

    route_tuple = tuple(routes)
    app = FastAPI()

    @app.get("/{path:path}")
    async def handle_get(path: str, request: Request):
        response = _response_for_request(
            application,
            "GET",
            "/" + path,
            str(request.url.query),
            _routes_for_method("GET", route_tuple),
            context_factory=context_factory,
        )
        if response.body is not None:
            return Response(
                content=response.body,
                status_code=response.status,
                headers=response.headers,
                media_type=response.content_type,
            )
        return JSONResponse(
            status_code=response.status,
            content=response.payload,
            headers=response.headers,
            media_type=response.content_type,
        )

    return app
