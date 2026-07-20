"""Offer-promise access orchestration over repository-owned persistence."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


class OfferPromiseService:
    def __init__(
        self,
        repository: Any,
        *,
        user_access: Callable[[str], Dict[str, Any]],
    ) -> None:
        self.repository = repository
        self._user_access = user_access

    def _session_with_agent_access(self, session: Dict[str, Any]) -> Dict[str, Any]:
        actor = dict(session or {})
        email = str(actor.get("email") or "").strip().lower()
        access = self._user_access(email) if email else {}
        if not str(actor.get("agent_name") or "").strip():
            actor["agent_name"] = str(access.get("agent_name") or "").strip()
        return actor

    def ensure_request_capacity(
        self,
        request_id: int,
        *,
        promise_context: Optional[Dict[str, Any]] = None,
        bypass_role_limits: bool = False,
    ) -> None:
        self.repository.ensure_free_agent_offer_request_promise_capacity(
            request_id,
            promise_context=promise_context,
            bypass_role_limits=bypass_role_limits,
        )

    def list_free_agent_offer_promises(
        self,
        session: Dict[str, Any],
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.repository.list_free_agent_offer_promises(
            self._session_with_agent_access(session),
            status,
        )

    def create_free_agent_offer_promise(
        self,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
        *,
        bypass_role_limits: bool = False,
    ) -> Dict[str, Any]:
        return self.repository.create_free_agent_offer_promise(
            payload,
            actor,
            bypass_role_limits=bypass_role_limits,
        )

    def update_free_agent_offer_promise(
        self,
        promise_id: int,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
        *,
        bypass_role_limits: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return self.repository.update_free_agent_offer_promise(
            promise_id,
            payload,
            actor,
            bypass_role_limits=bypass_role_limits,
        )

    def update_free_agent_offer_promise_status(
        self,
        promise_id: int,
        status: str,
        actor: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self.repository.update_free_agent_offer_promise_status(
            promise_id,
            status,
            actor,
        )
