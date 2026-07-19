"""Player roster mutation HTTP routes."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..auth.policies import normalize_team_code
    from ..domain_rules import parse_int
    from ..routing import exact_route, predicate_route
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain_rules import parse_int
    from routing import exact_route, predicate_route


def _player_action_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) == 4 and parts[:2] == ["api", "players"] and parts[3] in {"remove", "cut"}


def mutate_roster_player(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    parts = parsed.path.strip("/").split("/")
    try:
        player_id = int(parts[2])
    except ValueError:
        handler._json(400, {"error": "invalid_player_id"})
        return
    action = parts[3]
    player_before = handler.db.get_player_record(player_id)
    if not player_before:
        handler._json(404, {"error": "player_not_found"})
        return
    if not handler._authorize(f"admin.player.{action}", {"team_code": player_before.get("team_code")}):
        return
    result = handler.db.remove_player_from_roster(player_id) if action == "remove" else handler.db.cut_player(player_id, payload)
    if not result:
        handler._json(404, {"error": "player_not_found"})
        return
    details = {
        "profile_id": result.get("profile_id"),
        "player_name": result.get("player_name"),
        "free_agent_id": result.get("free_agent_id"),
    }
    if action == "cut":
        details["dead_contract_id"] = result.get("dead_contract_id")
    handler._log_admin_action(
        action,
        "player",
        str(player_id),
        str(result.get("team_code") or ""),
        details,
        before=player_before,
        after={f"{action}_result": result},
    )
    if action == "cut" and handler._discord_notify_requested(payload):
        handler._notify_player_cut(
            result,
            generate_image=handler._discord_image_requested(payload),
            custom_image=payload.get("discord_custom_image"),
        )
    handler._json(200, {"ok": True, "result": result})


def create_player(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("admin.player.write", {"team_code": team_code}):
        return
    try:
        player_id = handler.db.create_player(team_code, payload)
    except ValueError as err:
        if str(err) == "profile_has_active_contract":
            handler._json(409, {"error": "profile_has_active_contract"})
            return
        raise
    if not player_id:
        handler._json(404, {"error": "team_not_found"})
        return
    player_after = handler.db.get_player_record(player_id)
    handler._log_admin_action("create", "player", str(player_id), team_code, {"name": payload.get("name")}, after=player_after)
    handler._json(201, {"player_id": player_id})


def move_player(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    player_id = payload.get("player_id")
    to_team_code = normalize_team_code(payload.get("to_team_code"))
    if not player_id or not to_team_code:
        handler._json(400, {"error": "player_id_and_to_team_code_required"})
        return
    parsed_player_id = parse_int(str(player_id))
    if parsed_player_id is None:
        handler._json(400, {"error": "invalid_player_id"})
        return
    player_before = handler.db.get_player_record(parsed_player_id)
    if not player_before:
        handler._json(404, {"error": "player_not_found"})
        return
    if not handler._authorize("admin.player.move", {"team_code": player_before.get("team_code")}):
        return
    if not handler._authorize("admin.player.move", {"team_code": to_team_code}):
        return
    ok = handler.db.move_player(parsed_player_id, to_team_code)
    if ok:
        player_after = handler.db.get_player_record(parsed_player_id)
        handler._log_admin_action(
            "move", "player", str(parsed_player_id), str(player_before.get("team_code") or ""),
            {"from_team_code": player_before.get("team_code"), "to_team_code": to_team_code},
            before=player_before, after=player_after,
            team_codes=[player_before.get("team_code"), to_team_code],
        )
    handler._json(200 if ok else 404, {"ok": ok})


PLAYER_POST_ROUTES = (
    predicate_route("player-roster-action", _player_action_path, mutate_roster_player),
    exact_route("/api/players", create_player),
    exact_route("/api/players/move", move_player),
)
