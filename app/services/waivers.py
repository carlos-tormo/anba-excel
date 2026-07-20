"""Waiver claim application service.

HTTP adapters remain responsible for authentication, authorization, status-code
mapping, and audit emission. This service owns waiver workflow orchestration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..db.repositories.waivers import WaiverRepository
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from db.repositories.waivers import WaiverRepository


class WaiverService:
    def __init__(self, db: Any) -> None:
        if isinstance(db, WaiverRepository):
            self.repository = db
        else:
            self.repository = getattr(db, "_waiver_repository", None) or WaiverRepository(db)

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
        claim = self.repository.create_claim(
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
        result = self.repository.decide_claim_request(
            int(request_id),
            normalized_decision,
            actor or {},
            str(note or "").strip() or None,
        )
        if not result:
            raise ValueError("request_not_found")
        return {
            "decision": normalized_decision,
            "request_before": request_before,
            "result": result,
            "team_code": normalize_team_code(request_before.get("team_code")),
            "waiver_player_id": request_before.get("waiver_player_id"),
            "player_name": request_before.get("player_name"),
            "from_team_code": request_before.get("from_team_code"),
        }
