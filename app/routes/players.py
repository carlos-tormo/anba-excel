"""Player roster mutation HTTP routes."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..auth.policies import normalize_team_code
    from ..domain_rules import parse_int
    from ..routing import RouteResponse, error_response, exact_route, json_response, predicate_route
    from ..services.notifications import discord_image_requested, discord_notify_requested
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain_rules import parse_int
    from routing import RouteResponse, error_response, exact_route, json_response, predicate_route
    from services.notifications import discord_image_requested, discord_notify_requested


def _player_action_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) == 4 and parts[:2] == ["api", "players"] and parts[3] in {"remove", "cut"}


def mutate_roster_player(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    parts = parsed.path.strip("/").split("/")
    try:
        player_id = int(parts[2])
    except ValueError:
        return error_response(400, "invalid_player_id")
    action = parts[3]
    service = handler.app.player_roster
    player_before = service.player(player_id)
    if not player_before:
        return error_response(404, "player_not_found")
    if not handler._authorize(f"admin.player.{action}", {"team_code": player_before.get("team_code")}):
        return
    outcome = service.mutate(player_id, action, payload, before=player_before)
    if not outcome:
        return error_response(404, "player_not_found")
    result, audit = outcome["result"], outcome["audit"]
    handler._log_admin_action(
        audit["action"], audit["entity"], audit["entity_id"], audit["team_code"],
        audit["details"], before=audit["before"], after=audit["after"],
    )
    if action == "cut" and discord_notify_requested(payload):
        handler.app.notifications.player_cut(
            result,
            generate_image=discord_image_requested(payload),
            custom_image=payload.get("discord_custom_image"),
        )
    return json_response(200, {"ok": True, "result": result})


def create_player(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("admin.player.write", {"team_code": team_code}):
        return
    try:
        player_id = handler.app.players.create(team_code, payload)
    except ValueError as err:
        if str(err) == "profile_has_active_contract":
            return error_response(409, "profile_has_active_contract")
        raise
    if not player_id:
        return error_response(404, "team_not_found")
    player_after = handler.app.players.record(player_id)
    handler._log_admin_action("create", "player", str(player_id), team_code, {"name": payload.get("name")}, after=player_after)
    return json_response(201, {"player_id": player_id})


def move_player(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    player_id = payload.get("player_id")
    to_team_code = normalize_team_code(payload.get("to_team_code"))
    if not player_id or not to_team_code:
        return error_response(400, "player_id_and_to_team_code_required")
    parsed_player_id = parse_int(str(player_id))
    if parsed_player_id is None:
        return error_response(400, "invalid_player_id")
    service = handler.app.player_roster
    player_before = service.player(parsed_player_id)
    if not player_before:
        return error_response(404, "player_not_found")
    if not handler._authorize("admin.player.move", {"team_code": player_before.get("team_code")}):
        return
    if not handler._authorize("admin.player.move", {"team_code": to_team_code}):
        return
    result = service.move(parsed_player_id, to_team_code, before=player_before)
    audit = result["audit"]
    if audit:
        handler._log_admin_action(
            audit["action"], audit["entity"], audit["entity_id"], audit["team_code"],
            audit["details"], before=audit["before"], after=audit["after"],
            team_codes=audit["team_codes"],
        )
    return json_response(200 if result["ok"] else 404, {"ok": result["ok"]})


PLAYER_POST_ROUTES = (
    predicate_route("player-roster-action", _player_action_path, mutate_roster_player, permission="admin.player.write", csrf=True, mutates_league_state=True),
    exact_route("/api/players", create_player, permission="admin.player.write", csrf=True, mutates_league_state=True),
    exact_route("/api/players/move", move_player, permission="admin.player.move", csrf=True, mutates_league_state=True),
)
