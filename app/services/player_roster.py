"""Player roster mutation workflows."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_int


class PlayerRosterService:
    def __init__(
        self,
        players: Any,
        waivers: Any,
        player_happiness: Any = None,
        team_objectives: Any = None,
    ) -> None:
        self.players = players
        self.waivers = waivers
        self.player_happiness = player_happiness
        self.team_objectives = team_objectives

    def player(self, player_id: int) -> Optional[Dict[str, Any]]:
        return self.players.record(player_id)

    def create(self, team_code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        player_id = self.players.create(team_code, payload)
        if not player_id:
            return {"player_id": None, "player": None, "happiness_impact": None}
        player = self.players.record(player_id)
        join_happiness_event = self._reset_join_happiness(
            team_code,
            player or {"id": player_id, **(payload or {})},
            source_player_id=player_id,
        )
        happiness_impact = self._apply_roster_impact(
            team_code,
            player or {"id": player_id, **(payload or {})},
            "add",
            source_entity_type="player_create",
            source_entity_id=player_id,
        )
        return {
            "player_id": player_id,
            "player": player,
            "join_happiness_event": join_happiness_event,
            "happiness_impact": happiness_impact,
        }

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
        happiness_impact = self._apply_roster_impact(
            str(result.get("team_code") or before.get("team_code") or ""),
            before,
            "remove",
            source_entity_type=f"player_{action}",
            source_entity_id=player_id,
        )
        details = {
            "profile_id": result.get("profile_id"),
            "player_name": result.get("player_name"),
            "free_agent_id": result.get("free_agent_id"),
        }
        if action == "cut":
            details["dead_contract_id"] = result.get("dead_contract_id")
        return {
            "result": result,
            "happiness_impact": happiness_impact,
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
        departure_impact = None
        arrival_impact = None
        join_happiness_event = None
        if ok:
            departure_impact = self._apply_roster_impact(
                str(from_team_code or ""),
                before,
                "remove",
                source_entity_type="player_move",
                source_entity_id=player_id,
            )
            arrival_impact = self._apply_roster_impact(
                to_team_code,
                after or before,
                "add",
                source_entity_type="player_move",
                source_entity_id=player_id,
            )
            join_happiness_event = self._reset_join_happiness(
                to_team_code,
                after or before,
                source_player_id=player_id,
            )
        return {
            "ok": ok,
            "happiness_impact": {
                "departure": departure_impact,
                "arrival": arrival_impact,
                "join": join_happiness_event,
            } if ok else None,
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

    def _apply_roster_impact(
        self,
        team_code: str,
        subject_player: Dict[str, Any],
        direction: str,
        *,
        source_entity_type: str,
        source_entity_id: Any = None,
    ) -> Optional[Dict[str, Any]]:
        if self.player_happiness is None:
            return None
        return self.player_happiness.apply_roster_impact(
            team_code=team_code,
            subject_player=subject_player,
            direction=direction,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
        )

    def _reset_join_happiness(
        self,
        team_code: str,
        player: Dict[str, Any],
        *,
        source_player_id: Any = None,
    ) -> Optional[Dict[str, Any]]:
        if self.player_happiness is None:
            return None
        profile_id = parse_int((player or {}).get("profile_id"))
        if profile_id is None:
            return None
        objective_modifier = (
            self.player_happiness.team_join_objective_modifier(
                self.team_objectives,
                team_code,
                player or {},
            )
            if self.team_objectives is not None
            and hasattr(self.player_happiness, "team_join_objective_modifier")
            else None
        )
        modifier_details = (
            [objective_modifier]
            if objective_modifier and objective_modifier.get("applied_delta")
            else None
        )
        modifiers = (
            [objective_modifier["applied_delta"]]
            if objective_modifier and objective_modifier.get("applied_delta")
            else None
        )
        return self.player_happiness.reset_for_team_join(
            int(profile_id),
            team_code,
            player_id=source_player_id or (player or {}).get("id") or (player or {}).get("player_id"),
            modifiers=modifiers,
            modifier_details=modifier_details,
        )
