"""POST route functions extracted by workflow."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..domain_rules import parse_bool, parse_int
    from ..routing import exact_route, prefix_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain_rules import parse_bool, parse_int
    from routing import exact_route, prefix_route


def validate_trade(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    handler._json(200, handler.app.trades.validate(payload or {}))


def update_draft_live_settings(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.draft_live.write") or not handler._require_csrf():
        return
    try:
        result = handler.app.draft.update_live_settings(payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_draft_live_settings"})
        return
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
    )
    handler._json(200, result)


def control_draft_live(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.draft_live.write") or not handler._require_csrf():
        return
    try:
        result = handler.app.draft.control_live(payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_draft_live_control"})
        return
    handler._log_admin_action(
        "control",
        "draft_live",
        str(result.get("draft_year") or ""),
        None,
        {"action": payload.get("action"), "current_pick_id": result.get("current_pick_id")},
    )
    handler._json(200, result)


def process_draft_live(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.draft_live.write") or not handler._require_csrf():
        return
    draft_year = parse_int(str(payload.get("draft_year") or "")) or None
    try:
        result = handler.app.draft.process_results(draft_year)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_draft_processing"})
        return
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
    )
    handler._json(200, result)


def submit_draft_live_pick(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    try:
        draft_order_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_draft_order_id"})
        return
    draft_service = handler.app.draft
    pick = draft_service.order_entry(draft_order_id)
    if not pick:
        handler._json(404, {"error": "draft_pick_not_found"})
        return
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
        conflicts = {"not_current_pick", "draft_mode_inactive"}
        if not is_admin:
            conflicts |= {"pick_already_selected", "too_many_pending_draft_picks"}
        status = 409 if message in conflicts else 400
        if not is_admin and message == "draft_pick_not_found":
            status = 404
        handler._json(status, {"error": message})
        return
    if not is_admin:
        handler._json(201, submission["draft_live"])
        return
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
    handler._json(200, submission["draft_live"])


POST_ROUTES = (
    exact_route("/api/trades/validate", validate_trade),
    exact_route("/api/draft-live/settings", update_draft_live_settings),
    exact_route("/api/draft-live/control", control_draft_live),
    exact_route("/api/draft-live/process", process_draft_live),
    prefix_route("/api/draft-live/picks/", submit_draft_live_pick),
)
