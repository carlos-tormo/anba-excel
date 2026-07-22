"""Trade archive routes."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult, parse_qs

try:
    from ..domain._values import parse_int
    from ..routing import RouteResponse, error_response, exact_route, json_response, prefix_route
except ImportError:  # pragma: no cover
    from domain._values import parse_int
    from routing import RouteResponse, error_response, exact_route, json_response, prefix_route


def list_trade_archive(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> RouteResponse:
    qs = parse_qs(parsed.query)
    season = parse_int((qs.get("season") or [""])[0])
    return json_response(200, handler.app.trade_archive.list(season_year=season))


def create_trade_archive_entry(
    handler: Any,
    parsed: ParseResult,
    payload: Optional[Dict[str, Any]],
) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return None
    if not handler._require_sensitive_rate_limit("admin_post"):
        return None
    if not handler._authorize("admin.trade_archive.write"):
        return None
    try:
        trade = handler.app.trade_archive.create(payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_trade_archive_payload")
    handler._log_admin_action(
        "create",
        "trade_archive",
        str(trade.get("id")),
        None,
        {"teams": trade.get("teams") or [], "season_year": trade.get("season_year")},
        after=trade,
        team_codes=trade.get("teams") or [],
    )
    return json_response(201, {"ok": True, "trade": trade})


def import_trade_archive_entries(
    handler: Any,
    parsed: ParseResult,
    payload: Optional[Any],
) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return None
    if not handler._require_sensitive_rate_limit("admin_upload"):
        return None
    if not handler._authorize("admin.trade_archive.write"):
        return None
    try:
        result = handler.app.trade_archive.import_trades(payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_trade_archive_import")
    handler._log_admin_action(
        "import",
        "trade_archive",
        None,
        None,
        {
            "created_count": len(result.get("created") or []),
            "error_count": len(result.get("errors") or []),
        },
        after=result,
    )
    return json_response(207 if result.get("errors") else 201, result)


def update_trade_archive_entry(
    handler: Any,
    parsed: ParseResult,
    payload: Optional[Dict[str, Any]],
) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return None
    if not handler._require_sensitive_rate_limit("admin_post"):
        return None
    if not handler._authorize("admin.trade_archive.write"):
        return None
    trade_id = parse_int(parsed.path.rsplit("/", 1)[-1])
    if trade_id is None:
        return error_response(404, "not_found")
    before = handler.app.trade_archive.get(trade_id)
    try:
        trade = handler.app.trade_archive.update(trade_id, payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_trade_archive_payload")
    if not trade:
        return error_response(404, "not_found")
    handler._log_admin_action(
        "update",
        "trade_archive",
        str(trade_id),
        None,
        {"fields": sorted((payload or {}).keys())},
        before=before,
        after=trade,
        team_codes=trade.get("teams") or [],
    )
    return json_response(200, {"ok": True, "trade": trade})


def delete_trade_archive_entry(
    handler: Any,
    parsed: ParseResult,
    payload: Optional[Dict[str, Any]],
) -> Optional[RouteResponse]:
    if not handler._require_csrf():
        return None
    if not handler._require_sensitive_rate_limit("admin_post"):
        return None
    if not handler._authorize("admin.trade_archive.write"):
        return None
    trade_id = parse_int(parsed.path.rsplit("/", 1)[-1])
    if trade_id is None:
        return error_response(404, "not_found")
    before = handler.app.trade_archive.get(trade_id)
    ok = handler.app.trade_archive.delete(trade_id)
    if not ok:
        return error_response(404, "not_found")
    handler._log_admin_action(
        "delete",
        "trade_archive",
        str(trade_id),
        None,
        {},
        before=before,
        team_codes=(before or {}).get("teams") or [],
    )
    return json_response(200, {"ok": True})


TRADE_ARCHIVE_GET_ROUTES = (
    exact_route("/api/trades/archive", list_trade_archive, auth_exempt_reason="public_trade_archive"),
)

TRADE_ARCHIVE_POST_ROUTES = (
    exact_route("/api/trades/archive/import", import_trade_archive_entries, permission="admin.trade_archive.write", csrf=True, mutates_league_state=True),
    exact_route("/api/trades/archive", create_trade_archive_entry, permission="admin.trade_archive.write", csrf=True, mutates_league_state=True),
)

TRADE_ARCHIVE_PATCH_ROUTES = (
    prefix_route("/api/trades/archive/", update_trade_archive_entry, permission="admin.trade_archive.write", csrf=True, mutates_league_state=True),
)

TRADE_ARCHIVE_DELETE_ROUTES = (
    prefix_route("/api/trades/archive/", delete_trade_archive_entry, permission="admin.trade_archive.write", csrf=True, mutates_league_state=True),
)
