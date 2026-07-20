"""Player roster mutation workflows."""

from __future__ import annotations

from typing import Any, Dict, Optional


class PlayerRosterService:
    def __init__(self, players: Any, waivers: Any) -> None:
        self.players = players
        self.waivers = waivers

    def player(self, player_id: int) -> Optional[Dict[str, Any]]:
        return self.players.record(player_id)

    def mutate(
        self,
        player_id: int,
        action: str,
        payload: Dict[str, Any],
        *,
        before: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        result = (
            self.players.remove_from_roster(player_id)
            if action == "remove"
            else self.waivers.cut_player(player_id, payload)
        )
        if not result:
            return None
        details = {
            "profile_id": result.get("profile_id"),
            "player_name": result.get("player_name"),
            "free_agent_id": result.get("free_agent_id"),
        }
        if action == "cut":
            details["dead_contract_id"] = result.get("dead_contract_id")
        return {
            "result": result,
            "audit": {
                "action": action,
                "entity": "player",
                "entity_id": str(player_id),
                "team_code": str(result.get("team_code") or ""),
                "details": details,
                "before": before,
                "after": {f"{action}_result": result},
            },
        }

    def move(
        self,
        player_id: int,
        to_team_code: str,
        *,
        before: Dict[str, Any],
    ) -> Dict[str, Any]:
        ok = self.players.move(player_id, to_team_code)
        after = self.players.record(player_id) if ok else None
        from_team_code = before.get("team_code")
        return {
            "ok": ok,
            "audit": {
                "action": "move",
                "entity": "player",
                "entity_id": str(player_id),
                "team_code": str(from_team_code or ""),
                "details": {
                    "from_team_code": from_team_code,
                    "to_team_code": to_team_code,
                },
                "before": before,
                "after": after,
                "team_codes": [from_team_code, to_team_code],
            } if ok else None,
        }
