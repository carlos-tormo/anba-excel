"""Waiting-list routes."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..domain._values import parse_int
    from ..routing import RouteResponse, error_response, exact_route, json_response, prefix_route
except ImportError:  # pragma: no cover
    from domain._values import parse_int
    from routing import RouteResponse, error_response, exact_route, json_response, prefix_route


def list_waiting_list(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> RouteResponse:
    return json_response(200, handler.app.waiting_list.list())


def create_waiting_list_entry(
    handler: Any,
    parsed: ParseResult,
    payload: Optional[Dict[str, Any]],
) -> Optional[RouteResponse]:
    if not handler._require_csrf():
        return None
    if not handler._require_sensitive_rate_limit("admin_post"):
        return None
    if not handler._authorize("admin.waiting_list.write"):
        return None
    try:
        entry = handler.app.waiting_list.create(payload or {})
    except ValueError as err:
        return error_response(400, str(err) or "invalid_waiting_list_payload")
    handler._log_admin_action(
        "create",
        "waiting_list",
        str(entry.get("id")),
        None,
        {"display_name": entry.get("display_name"), "position": entry.get("position")},
        after=entry,
    )
    return json_response(201, {"ok": True, "entry": entry})


def update_waiting_list_entry(
    handler: Any,
    parsed: ParseResult,
    payload: Optional[Dict[str, Any]],
) -> Optional[RouteResponse]:
    if not handler._require_csrf():
        return None
    if not handler._require_sensitive_rate_limit("admin_post"):
        return None
    if not handler._authorize("admin.waiting_list.write"):
        return None
    entry_id = parse_int(parsed.path.rsplit("/", 1)[-1])
    if entry_id is None:
        return error_response(404, "not_found")
    before = handler.app.waiting_list.get(entry_id)
    try:
        entry = handler.app.waiting_list.update(entry_id, payload or {})
    except ValueError as err:
        return error_response(400, str(err) or "invalid_waiting_list_payload")
    if not entry:
        return error_response(404, "not_found")
    handler._log_admin_action(
        "update",
        "waiting_list",
        str(entry_id),
        None,
        {"fields": sorted((payload or {}).keys())},
        before=before,
        after=entry,
    )
    return json_response(200, {"ok": True, "entry": entry})


def delete_waiting_list_entry(
    handler: Any,
    parsed: ParseResult,
    payload: Optional[Dict[str, Any]],
) -> Optional[RouteResponse]:
    if not handler._require_csrf():
        return None
    if not handler._require_sensitive_rate_limit("admin_post"):
        return None
    if not handler._authorize("admin.waiting_list.write"):
        return None
    entry_id = parse_int(parsed.path.rsplit("/", 1)[-1])
    if entry_id is None:
        return error_response(404, "not_found")
    before = handler.app.waiting_list.get(entry_id)
    ok = handler.app.waiting_list.delete(entry_id)
    if not ok:
        return error_response(404, "not_found")
    handler._log_admin_action(
        "delete",
        "waiting_list",
        str(entry_id),
        None,
        {},
        before=before,
    )
    return json_response(200, {"ok": True})


WAITING_LIST_GET_ROUTES = (
    exact_route("/api/waiting-list", list_waiting_list, auth_exempt_reason="public_waiting_list"),
)

WAITING_LIST_POST_ROUTES = (
    exact_route(
        "/api/waiting-list",
        create_waiting_list_entry,
        permission="admin.waiting_list.write",
        csrf=True,
        mutates_league_state=True,
    ),
)

WAITING_LIST_PATCH_ROUTES = (
    prefix_route(
        "/api/waiting-list/",
        update_waiting_list_entry,
        permission="admin.waiting_list.write",
        csrf=True,
        mutates_league_state=True,
    ),
)

WAITING_LIST_DELETE_ROUTES = (
    prefix_route(
        "/api/waiting-list/",
        delete_waiting_list_entry,
        permission="admin.waiting_list.write",
        csrf=True,
        mutates_league_state=True,
    ),
)
