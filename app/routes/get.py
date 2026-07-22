"""Stable GET route functions."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult, parse_qs

try:
    from ..domain_rules import parse_int
    from ..routing import error_response, exact_route, json_response, response_from_exception
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain_rules import parse_int
    from routing import error_response, exact_route, json_response, response_from_exception


def get_teams(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    return json_response(200, {"teams": handler.app.teams.list()})


def get_news_articles(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    query = parse_qs(parsed.query)
    limit = parse_int((query.get("limit") or ["50"])[0]) or 50
    return json_response(200, {"articles": handler.app.press_articles.list(limit=limit)})


def get_waivers(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    return json_response(200, handler.app.waivers.list_waivers(handler._current_session()))


def _draft_year(parsed: ParseResult) -> tuple[bool, Optional[int]]:
    query = parse_qs(parsed.query)
    raw_year = (query.get("year") or [""])[0].strip()
    if not raw_year:
        return True, None
    draft_year = parse_int(raw_year)
    if draft_year is None or draft_year < 2000 or draft_year > 2100:
        return False, None
    return True, draft_year


def get_draft_order(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    valid, draft_year = _draft_year(parsed)
    if valid:
        return json_response(200, handler.app.draft.list_order(draft_year))
    return error_response(400, "invalid_draft_year")


def get_draft_pick_ledger(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    valid, draft_year = _draft_year(parsed)
    if valid:
        return json_response(200, handler.app.draft.list_pick_ledger(draft_year))
    return error_response(400, "invalid_draft_year")


def get_draft_live(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    valid, draft_year = _draft_year(parsed)
    if not valid:
        return error_response(400, "invalid_draft_year")
    try:
        return json_response(200, handler.app.draft.list_live(draft_year))
    except ValueError as err:
        return response_from_exception(ValueError(str(err) or "invalid_draft_live"))


def get_settings(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    return json_response(200, {"settings": handler.app.settings.public()})


def get_admin_logs(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    if not handler._authorize("admin.audit.view"):
        return
    query = parse_qs(parsed.query)
    action = (query.get("action") or [""])[0].strip() or None
    entity = (query.get("entity") or [""])[0].strip() or None
    limit = parse_int((query.get("limit") or ["200"])[0]) or 200
    return json_response(200, {"logs": handler.app.audit_logs.list(action=action, entity=entity, limit=limit)})


def get_admin_maintenance(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    if handler._authorize("admin.maintenance.view"):
        return json_response(200, handler.app.maintenance.status())
    return None


GET_ROUTES = (
    exact_route("/api/teams", get_teams),
    exact_route("/api/news/articles", get_news_articles),
    exact_route("/api/waivers", get_waivers),
    exact_route("/api/draft-order", get_draft_order),
    exact_route("/api/draft-pick-ledger", get_draft_pick_ledger),
    exact_route("/api/draft-live", get_draft_live),
    exact_route("/api/settings", get_settings),
    exact_route("/api/admin/logs", get_admin_logs),
    exact_route("/api/admin/maintenance", get_admin_maintenance),
)
