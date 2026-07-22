"""POST route functions extracted by workflow."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..domain_rules import parse_bool, parse_int
    from ..routing import RouteResponse, error_response, exact_route, json_response, prefix_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain_rules import parse_bool, parse_int
    from routing import RouteResponse, error_response, exact_route, json_response, prefix_route


def validate_trade(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> RouteResponse:
    return json_response(200, handler.app.trades.validate(payload or {}))


def update_draft_live_settings(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.draft_live.write") or not handler._require_csrf():
        return
    try:
        draft_year = parse_int(payload.get("draft_year"))
        list_live = getattr(handler.app.draft, "list_live", None)
        before = list_live(draft_year) if draft_year is not None and callable(list_live) else None
        result = handler.app.draft.update_live_settings(payload)
    except ValueError as err:
        message = str(err) or "invalid_draft_live_settings"
        return error_response(409 if message == "stale_entity_version" else 400, message)
    after = result
    handler._log_admin_action(
        "update",
        "draft_live",
        str(result.get("draft_year") or ""),
        None,
        {
            "enabled": result.get("enabled"),
            "current_pick_id": result.get("current_pick_id"),
            "duration_seconds": result.get("duration_seconds"),
        },
        before=before,
        after=after,
    )
    return json_response(200, result)


def control_draft_live(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.draft_live.write") or not handler._require_csrf():
        return
    try:
        draft_year = parse_int(payload.get("draft_year"))
        list_live = getattr(handler.app.draft, "list_live", None)
        before = list_live(draft_year) if draft_year is not None and callable(list_live) else None
        result = handler.app.draft.control_live(payload)
    except ValueError as err:
        message = str(err) or "invalid_draft_live_control"
        return error_response(409 if message == "stale_entity_version" else 400, message)
    after = result
    handler._log_admin_action(
        "control",
        "draft_live",
        str(result.get("draft_year") or ""),
        None,
        {"action": payload.get("action"), "current_pick_id": result.get("current_pick_id")},
        before=before,
        after=after,
    )
    return json_response(200, result)


def process_draft_live(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.draft_live.write") or not handler._require_csrf():
        return
    draft_year = parse_int(str(payload.get("draft_year") or "")) or None
    try:
        result = handler.app.draft.process_results(draft_year)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_draft_processing")
    handler._log_admin_action(
        "process",
        "draft_live",
        str(result.get("draft_year") or ""),
        None,
        {
            "created_cap_holds": len(result.get("created_cap_holds") or []),
            "created_player_rights": len(result.get("created_player_rights") or []),
            "errors": result.get("errors") or [],
        },
        before=None,
        after={"draft_live": result.get("draft_live")},
        command_id=result.get("command_id"),
        validation_result=result.get("validation_result"),
        entity_versions=result.get("entity_versions"),
    )
    return json_response(200, result)


def submit_draft_live_pick(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    try:
        draft_order_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_draft_order_id")
    draft_service = handler.app.draft
    pick = draft_service.order_entry(draft_order_id)
    if not pick:
        return error_response(404, "draft_pick_not_found")
    if not handler._authorize("draft_live.pick_submit", {"team_code": pick.get("owner_team_code")}):
        return
    is_admin = handler._is_admin()
    try:
        submission = draft_service.submit_pick(
            draft_order_id,
            payload,
            handler._current_session() or {},
            is_admin=is_admin,
            pick=pick,
        )
    except ValueError as err:
        message = str(err) or "invalid_draft_selection"
        conflicts = {"not_current_pick", "draft_mode_inactive", "stale_entity_version"}
        if not is_admin:
            conflicts |= {"pick_already_selected", "too_many_pending_draft_picks"}
        status = 409 if message in conflicts else 400
        if not is_admin and message == "draft_pick_not_found":
            status = 404
        return error_response(status, message)
    if not is_admin:
        return json_response(201, submission["draft_live"])
    handler._log_admin_action(
        "select",
        "draft_live_pick",
        str(draft_order_id),
        pick.get("owner_team_code"),
        {
            "draft_year": pick.get("draft_year"),
            "draft_round": pick.get("draft_round"),
            "pick_number": pick.get("pick_number"),
            "selection": payload.get("custom_text") or payload.get("option_value"),
            "clear": parse_bool(payload.get("clear")),
            "skipped": parse_bool(payload.get("skipped")),
        },
        team_codes=[pick.get("owner_team_code")],
    )
    return json_response(200, submission["draft_live"])


POST_ROUTES = (
    exact_route("/api/trades/validate", validate_trade, auth_exempt_reason="read_only_validation"),
    exact_route(
        "/api/draft-live/settings",
        update_draft_live_settings,
        permission="admin.draft_live.write",
        csrf=True,
        mutates_league_state=True,
    ),
    exact_route(
        "/api/draft-live/control",
        control_draft_live,
        permission="admin.draft_live.write",
        csrf=True,
        mutates_league_state=True,
    ),
    exact_route(
        "/api/draft-live/process",
        process_draft_live,
        permission="admin.draft_live.write",
        csrf=True,
        mutates_league_state=True,
    ),
    prefix_route(
        "/api/draft-live/picks/",
        submit_draft_live_pick,
        permission="draft_live.pick_submit",
        csrf=True,
        mutates_league_state=True,
    ),
)
