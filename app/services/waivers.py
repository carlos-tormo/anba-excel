"""Waiver claim application service.

HTTP adapters remain responsible for authentication, authorization, status-code
mapping, and audit emission. This service owns waiver workflow orchestration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..db.repositories.waivers import WaiverRepository
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from db.repositories.waivers import WaiverRepository
    from domain._values import parse_int


class WaiverService:
    def __init__(
        self,
        db: Any,
        *,
        player_happiness: Any = None,
        players: Any = None,
        team_objectives: Any = None,
    ) -> None:
        if isinstance(db, WaiverRepository):
            self.repository = db
        else:
            self.repository = getattr(db, "_waiver_repository", None) or WaiverRepository(db)
        backing_db = getattr(self.repository, "db", db)
        self.player_happiness = player_happiness or getattr(backing_db, "_player_happiness_service", None)
        self.players = players or getattr(backing_db, "_player_repository", None)
        self.team_objectives = team_objectives or getattr(backing_db, "_team_objective_service", None)

    def list_waivers(self, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.repository.list(actor)

    def process_expired(self) -> Dict[str, Any]:
        return self.repository.process_expired()

    def cut_player(
        self, player_id: int, payload: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        return self.repository.cut_player(player_id, payload)

    def submit_claim(
        self,
        waiver_player_id: int,
        team_code: str,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.repository.db.transaction("IMMEDIATE") as conn:
            claim = self.repository.create_claim_conn(
                conn,
                int(waiver_player_id),
                normalized_team,
                payload,
                actor or {},
            )
        return {
            "claim": claim,
            "team_code": normalized_team,
            "waiver_player_id": int(waiver_player_id),
        }

    def claim_requests(self, *, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.repository.list_claim_requests(status=status)

    def claim_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        parsed_id = int(request_id)
        return next(
            (
                request
                for request in self.claim_requests(status="all")
                if int(request.get("id") or 0) == parsed_id
            ),
            None,
        )

    def decide_claim(
        self,
        request_id: int,
        decision: str,
        actor: Dict[str, Any],
        *,
        note: Optional[str] = None,
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            raise ValueError("invalid_decision")
        request_before = request or self.claim_request(request_id)
        if not request_before:
            raise ValueError("request_not_found")
        if str(request_before.get("status") or "").strip().lower() != "pending":
            raise ValueError("request_already_decided")
        with self.repository.db.transaction("IMMEDIATE") as conn:
            result = self.repository.decide_claim_request_conn(
                conn,
                int(request_id),
                normalized_decision,
                actor or {},
                str(note or "").strip() or None,
                expected_version=parse_int(request_before.get("version")),
            )
        if not result:
            raise ValueError("request_not_found")
        player = self.players.record(result.get("player_id")) if self.players is not None and result.get("player_id") else None
        happiness_event = None
        roster_happiness_impact = None
        if normalized_decision == "approved" and self.player_happiness is not None and player:
            profile_id = parse_int(player.get("profile_id"))
            if profile_id is not None:
                objective_modifier = (
                    self.player_happiness.team_join_objective_modifier(
                        self.team_objectives,
                        normalize_team_code(request_before.get("team_code")) or result.get("team_code") or "",
                        player,
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
                happiness_event = self.player_happiness.reset_for_team_join(
                    int(profile_id),
                    normalize_team_code(request_before.get("team_code")) or result.get("team_code") or "",
                    player_id=result.get("player_id"),
                    free_agent_id=None,
                    modifiers=modifiers,
                    modifier_details=modifier_details,
                    actor=actor or {},
                )
            roster_happiness_impact = self.player_happiness.apply_roster_impact(
                team_code=normalize_team_code(request_before.get("team_code")) or result.get("team_code") or "",
                subject_player=player,
                direction="add",
                source_entity_type="waiver_claim",
                source_entity_id=int(request_id),
                actor=actor or {},
            )
        return {
            "decision": normalized_decision,
            "request_before": request_before,
            "result": result,
            "player": player,
            "happiness_event": happiness_event,
            "roster_happiness_impact": roster_happiness_impact,
            "team_code": normalize_team_code(request_before.get("team_code")),
            "waiver_player_id": request_before.get("waiver_player_id"),
            "player_name": request_before.get("player_name"),
            "from_team_code": request_before.get("from_team_code"),
            "command_id": result.get("command_id") or f"waiver-claim:{int(request_id)}:{normalized_decision}",
            "validation_result": "valid",
            "entity_versions": {
                "request_before_status": request_before.get("status"),
                "request_after_status": result.get("status") or normalized_decision,
                "request_before_version": parse_int(request_before.get("version")),
                "request_after_version": parse_int(result.get("version")),
                "player_id": result.get("player_id"),
            },
        }
