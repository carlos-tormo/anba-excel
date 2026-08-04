"""Workflow services for GM attractiveness rankings."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_int


class GMAttractivenessService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def active_ranking(self) -> Dict[str, Any]:
        return self.repository.active() or {"id": None, "entries": []}

    def publish_from_vote(self, vote_id: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.repository.publish_from_vote(vote_id, actor or {})

    def publish_from_vote_conn(self, conn: Any, vote_id: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.repository.publish_from_vote_conn(conn, vote_id, actor or {})

    def update_active_entry(
        self,
        gm_entity_id: Any,
        payload: Dict[str, Any],
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        updated = self.repository.update_active_entry(gm_entity_id, payload or {}, actor or {})
        if updated is None:
            raise ValueError("ranking_entry_not_found")
        return updated

    def bands_for_gm_change(self, *, incoming_gm_entity_id: Any = None, outgoing_gm_entity_id: Any = None) -> Dict[str, Any]:
        ids = [
            parsed
            for parsed in (
                parse_int(incoming_gm_entity_id),
                parse_int(outgoing_gm_entity_id),
            )
            if parsed is not None
        ]
        entries = self.repository.active_bands_for_gms(ids)
        incoming_id = parse_int(incoming_gm_entity_id)
        outgoing_id = parse_int(outgoing_gm_entity_id)
        return {
            "incoming": entries.get(int(incoming_id)) if incoming_id is not None else None,
            "outgoing": entries.get(int(outgoing_id)) if outgoing_id is not None else None,
        }
