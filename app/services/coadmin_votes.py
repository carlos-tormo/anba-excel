"""Workflow orchestration for co-admin GM attractiveness votes."""

from __future__ import annotations

from typing import Any, Dict, Optional


class CoadminVoteService:
    def __init__(self, repository: Any, *, gm_attractiveness: Any = None) -> None:
        self.repository = repository
        self.gm_attractiveness = gm_attractiveness

    def create_coadmin_vote(self, title: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.repository.create_coadmin_vote(title, actor or {})

    def get_coadmin_vote(self, vote_id: Any) -> Optional[Dict[str, Any]]:
        return self.repository.get_coadmin_vote(vote_id)

    def list_admin_coadmin_votes(self) -> list[Dict[str, Any]]:
        votes = self.repository.list_admin_coadmin_votes()
        active_ranking = self.gm_attractiveness.active_ranking() if self.gm_attractiveness is not None else None
        active_source_vote_id = None
        if isinstance(active_ranking, dict):
            active_source_vote_id = active_ranking.get("source_vote_id")
        for vote in votes:
            vote["published_as_active_ranking"] = bool(active_source_vote_id and int(vote.get("id") or 0) == int(active_source_vote_id))
        return votes

    def list_coadmin_votes_for_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.list_coadmin_votes_for_session(session)

    def submit_coadmin_vote(self, vote_id: Any, scores: Any, session: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.submit_coadmin_vote(vote_id, scores, session)

    def set_coadmin_vote_status(
        self,
        vote_id: Any,
        status: Any,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.gm_attractiveness is None:
            return self.repository.set_coadmin_vote_status(vote_id, status, actor or {})
        with self.repository.transaction("IMMEDIATE") as conn:
            previous = self.repository.get_coadmin_vote_conn(conn, vote_id)
            vote = self.repository.set_coadmin_vote_status_conn(conn, vote_id, status, actor or {})
            if (
                vote
                and str(vote.get("status") or "").strip().lower() == "closed"
                and str((previous or {}).get("status") or "").strip().lower() != "closed"
            ):
                vote["published_ranking"] = self.gm_attractiveness.publish_from_vote_conn(conn, vote.get("id"), actor or {})
            return vote
