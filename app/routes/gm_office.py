"""GM-office and minimum-target HTTP route functions."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult, parse_qs

try:
    from ..auth.policies import normalize_team_code
    from ..domain_rules import parse_int
    from ..routing import (
        RequestValidationError,
        exact_route,
        validate_number_range,
        validate_payload_fields,
        validate_team_code_field,
    )
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from domain_rules import parse_int
    from routing import (
        RequestValidationError,
        exact_route,
        validate_number_range,
        validate_payload_fields,
        validate_team_code_field,
    )


FREE_AGENT_ROLE_VALUES = {
    "Titular",
    "Sexto hombre",
    "Minutos de rotación (10-20)",
    "Minutos de rotación (0-9)",
    "Fuera de la rotación",
}
DEPTH_CHART_POSITIONS = ("PG", "SG", "SF", "PF", "C")
DEPTH_CHART_MAX_DEPTH = 6


def _resolved_team_code(handler: Any, value: Any) -> Optional[str]:
    team_code = normalize_team_code(value)
    if team_code:
        return team_code
    team_codes = handler._current_session_team_codes()
    return team_codes[0] if len(team_codes) == 1 else None


def validate_gm_spending_limit_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, {"team_code", "amount_millions"}, required_fields={"amount_millions"})
    validate_team_code_field(payload)
    validate_number_range(payload, "amount_millions", minimum=0, maximum=100, required=True)


def validate_gm_minimum_targets_payload(payload: Dict[str, Any], *, omit: bool = False) -> None:
    if omit:
        validate_payload_fields(payload, {"team_code"})
        validate_team_code_field(payload)
        return
    validate_payload_fields(payload, {"team_code", "targets"}, required_fields={"targets"})
    validate_team_code_field(payload)
    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise RequestValidationError("invalid_list", field="targets")
    if len(targets) > 10:
        raise RequestValidationError("list_too_large", field="targets", max_items=10)
    ranks, free_agent_ids = set(), set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise RequestValidationError("invalid_field", field=f"targets[{index}]")
        validate_payload_fields(target, {"rank", "free_agent_id", "role"}, required_fields={"rank", "free_agent_id", "role"})
        rank, free_agent_id = parse_int(target.get("rank")), parse_int(target.get("free_agent_id"))
        role = str(target.get("role") or "").strip()
        if rank is None or not 1 <= rank <= 10:
            raise RequestValidationError("invalid_integer_range", field=f"targets[{index}].rank", minimum=1, maximum=10)
        if free_agent_id is None or free_agent_id <= 0:
            raise RequestValidationError("invalid_id", field=f"targets[{index}].free_agent_id")
        if role not in FREE_AGENT_ROLE_VALUES:
            raise RequestValidationError("invalid_enum", field=f"targets[{index}].role")
        if rank in ranks:
            raise RequestValidationError("duplicate_value", field="targets.rank", value=rank)
        if free_agent_id in free_agent_ids:
            raise RequestValidationError("duplicate_ids", field="targets.free_agent_id", id=free_agent_id)
        ranks.add(rank)
        free_agent_ids.add(free_agent_id)


def validate_gm_depth_chart_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, {"team_code", "entries"}, required_fields={"entries"})
    validate_team_code_field(payload)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise RequestValidationError("invalid_list", field="entries")
    if len(entries) > len(DEPTH_CHART_POSITIONS) * DEPTH_CHART_MAX_DEPTH:
        raise RequestValidationError("list_too_large", field="entries", max_items=30)
    player_ids, slots = set(), set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RequestValidationError("invalid_field", field=f"entries[{index}]")
        validate_payload_fields(entry, {"position", "depth_order", "player_id"}, required_fields={"position", "depth_order", "player_id"})
        position = str(entry.get("position") or "").strip().upper()
        depth_order, player_id = parse_int(entry.get("depth_order")), parse_int(entry.get("player_id"))
        if position not in DEPTH_CHART_POSITIONS:
            raise RequestValidationError("invalid_enum", field=f"entries[{index}].position")
        if depth_order is None or not 1 <= depth_order <= DEPTH_CHART_MAX_DEPTH:
            raise RequestValidationError("invalid_integer_range", field=f"entries[{index}].depth_order", minimum=1, maximum=DEPTH_CHART_MAX_DEPTH)
        if player_id is None or player_id <= 0:
            raise RequestValidationError("invalid_id", field=f"entries[{index}].player_id")
        slot = (position, depth_order)
        if slot in slots:
            raise RequestValidationError("duplicate_value", field="entries.slot", value=f"{position}:{depth_order}")
        if player_id in player_ids:
            raise RequestValidationError("duplicate_ids", field="entries.player_id", id=player_id)
        slots.add(slot)
        player_ids.add(player_id)


def get_admin_minimum_targets(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if handler._authorize("admin.gm_minimum_targets.view"):
        handler._json(200, {"lists": handler.db.list_admin_gm_minimum_targets()})


def get_admin_minimum_target_order(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if handler._authorize("admin.gm_minimum_targets.view"):
        handler._json(200, {"scores": handler.db.list_admin_gm_minimum_target_order()})


def get_admin_minimum_target_handicaps(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if handler._authorize("admin.gm_minimum_targets.view"):
        handler._json(200, {"handicaps": handler.db.list_gm_minimum_target_handicaps()})


def get_gm_office(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    query = parse_qs(parsed.query)
    team_code = _resolved_team_code(handler, (query.get("team_code") or [""])[0])
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("gm_office.view", {"team_code": team_code}):
        return
    try:
        data = handler.db.list_gm_office(team_code)
        session = handler._current_session() or {}
        if parse_int(session.get("user_id")):
            data["minimum_targets"] = handler.db.get_gm_minimum_targets(session.get("user_id"), team_code)
        handler._json(200, data)
    except ValueError as err:
        message = str(err) or "invalid_gm_office"
        handler._json(404 if message == "team_not_found" else 400, {"error": message})


def get_gm_minimum_targets(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    query = parse_qs(parsed.query)
    team_code = _resolved_team_code(handler, (query.get("team_code") or [""])[0])
    if team_code and not handler._authorize("gm_office.view", {"team_code": team_code}):
        return
    session = handler._current_session() or {}
    try:
        handler._json(200, handler.db.get_gm_minimum_targets(session.get("user_id"), team_code))
    except ValueError as err:
        message = str(err) or "invalid_minimum_targets"
        handler._json(404 if message in {"team_not_found", "user_not_found"} else 400, {"error": message})


def remove_admin_minimum_target(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.gm_minimum_targets.write") or not handler._require_csrf():
        return
    try:
        result = handler.db.remove_admin_gm_minimum_target(payload.get("user_id"), payload.get("rank"))
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_minimum_target"})
        return
    handler._log_admin_action("remove", "gm_minimum_target", result.get("user_id"), None, {"rank": result.get("rank"), "removed": result.get("removed")})
    handler._json(200, {"ok": True, **result})


def update_admin_minimum_target_handicap(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.gm_minimum_targets.write") or not handler._require_csrf():
        return
    try:
        result = handler.db.set_gm_minimum_target_handicap(payload.get("team_code"), payload.get("handicap"))
    except ValueError as err:
        message = str(err) or "invalid_handicap"
        handler._json(404 if message == "team_not_found" else 400, {"error": message})
        return
    handler._log_admin_action("update", "gm_minimum_target_handicap", result.get("team_code"), result.get("team_code"), {"handicap": result.get("handicap")})
    handler._json(200, {"ok": True, "handicap": result})


def update_spending_limit(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf() or not handler._validate_specialized_payload_or_error(payload, validate_gm_spending_limit_payload):
        return
    team_code = _resolved_team_code(handler, payload.get("team_code"))
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("gm_office.free_agent_spending_limit.update", {"team_code": team_code}):
        return
    try:
        value = handler.db.set_gm_free_agent_spending_limit(team_code, payload.get("amount_millions"), handler._current_session() or {})
    except ValueError as err:
        message = str(err) or "invalid_spending_limit"
        handler._json(404 if message == "team_not_found" else 400, {"error": message})
        return
    handler._json(200, {"ok": True, "free_agent_spending_limit": value})


def update_minimum_targets(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    omit = parsed.path.endswith("/omit")
    if not handler._require_csrf() or not handler._validate_specialized_payload_or_error(payload, validate_gm_minimum_targets_payload, omit=omit):
        return
    session = handler._current_session() or {}
    team_code = _resolved_team_code(handler, payload.get("team_code"))
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("gm_office.minimum_targets.update", {"team_code": team_code}):
        return
    try:
        value = handler.db.omit_gm_minimum_targets(session.get("user_id"), team_code) if omit else handler.db.set_gm_minimum_targets(session.get("user_id"), team_code, payload.get("targets") or [])
    except ValueError as err:
        message = str(err) or "invalid_minimum_targets"
        handler._json(404 if message in {"team_not_found", "user_not_found", "free_agent_not_found"} else 400, {"error": message})
        return
    handler._json(200, {"ok": True, "minimum_targets": value})


def update_depth_chart(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf() or not handler._validate_specialized_payload_or_error(payload, validate_gm_depth_chart_payload):
        return
    team_code = _resolved_team_code(handler, payload.get("team_code"))
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("gm_office.depth_chart.update", {"team_code": team_code}):
        return
    try:
        depth_chart = handler.db.set_team_depth_chart(team_code, payload.get("entries") or [])
    except ValueError as err:
        message = str(err) or "invalid_depth_chart"
        handler._json(404 if message == "team_not_found" else 400, {"error": message})
        return
    handler._json(200, {"ok": True, "depth_chart": depth_chart})


GM_OFFICE_GET_ROUTES = (
    exact_route("/api/admin/gm-minimum-targets", get_admin_minimum_targets),
    exact_route("/api/admin/gm-minimum-targets/order", get_admin_minimum_target_order),
    exact_route("/api/admin/gm-minimum-target-handicaps", get_admin_minimum_target_handicaps),
    exact_route("/api/gm-office", get_gm_office),
    exact_route("/api/gm-office/minimum-targets", get_gm_minimum_targets),
)
GM_OFFICE_POST_ROUTES = (
    exact_route("/api/admin/gm-minimum-targets/remove", remove_admin_minimum_target),
    exact_route("/api/admin/gm-minimum-target-handicaps", update_admin_minimum_target_handicap),
    exact_route("/api/gm-office/free-agent-spending-limit", update_spending_limit),
    exact_route("/api/gm-office/minimum-targets", update_minimum_targets),
    exact_route("/api/gm-office/minimum-targets/omit", update_minimum_targets),
    exact_route("/api/gm-office/depth-chart", update_depth_chart),
)
