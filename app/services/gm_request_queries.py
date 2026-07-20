"""Aggregate reads and submissions for GM workflow requests."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class GMRequestQueryService:
    def __init__(self, requests: Any, draft: Any, waivers: Any) -> None:
        self._requests = requests
        self._draft = draft
        self._waivers = waivers

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        requests = [
            *self._requests.list_requests(status),
            *self._draft.list_pick_requests(status),
            *self._waivers.list_claim_requests(status=status),
        ]
        requests.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        requests.sort(
            key=lambda item: 0 if str(item.get("status") or "") == "pending" else 1
        )
        return requests

    def free_agent_offer(self, request_id: int) -> Optional[Dict[str, Any]]:
        return self._requests.get_gm_free_agent_offer_request(request_id)

    def create_option(
        self,
        player_id: int,
        option_field: str,
        option_value: str,
        action: str,
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._requests.create_gm_option_request(
            player_id, option_field, option_value, action, requester
        )
