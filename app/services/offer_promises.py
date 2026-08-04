"""Offer-promise access orchestration over repository-owned persistence."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

try:
    from ..domain._values import parse_int
    from ..domain.player_happiness import EVENT_PROMISE_RESOLUTION, promise_resolution_delta
except ImportError:  # pragma: no cover
    from domain._values import parse_int
    from domain.player_happiness import EVENT_PROMISE_RESOLUTION, promise_resolution_delta


class OfferPromiseService:
    def __init__(
        self,
        repository: Any,
        *,
        user_access: Callable[[str], Dict[str, Any]],
        player_happiness: Any = None,
    ) -> None:
        self.repository = repository
        self._user_access = user_access
        self.player_happiness = player_happiness

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
        promise = self.repository.update_free_agent_offer_promise(
            promise_id,
            payload,
            actor,
            bypass_role_limits=bypass_role_limits,
        )
        return self._with_promise_happiness_impact(promise, actor)

    def update_free_agent_offer_promise_status(
        self,
        promise_id: int,
        status: str,
        actor: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        promise = self.repository.update_free_agent_offer_promise_status(
            promise_id,
            status,
            actor,
        )
        return self._with_promise_happiness_impact(promise, actor)

    def _with_promise_happiness_impact(
        self,
        promise: Optional[Dict[str, Any]],
        actor: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not promise or self.player_happiness is None:
            return promise
        profile_id = parse_int(promise.get("profile_id"))
        if profile_id is None:
            return promise
        delta = promise_resolution_delta(promise.get("previous_status"), promise.get("status"))
        if not delta:
            promise["happiness_impact"] = {
                "ok": True,
                "skipped": True,
                "reason": "promise_status_unchanged_for_happiness",
                "applied_delta": 0,
            }
            return promise
        promise["happiness_impact"] = self.player_happiness.apply_modifier(
            int(profile_id),
            delta,
            event_type=EVENT_PROMISE_RESOLUTION,
            reason=self._promise_happiness_reason(promise, delta),
            source_entity_type="free_agent_offer_promise",
            source_entity_id=promise.get("id"),
            metadata={
                "promise_id": promise.get("id"),
                "previous_status": promise.get("previous_status"),
                "status": promise.get("status"),
                "player_name": promise.get("player_name"),
                "team_code": promise.get("team_code"),
                "role": promise.get("role"),
                "season_year": promise.get("season_year"),
            },
            actor=actor,
        )
        return promise

    @staticmethod
    def _promise_happiness_reason(promise: Dict[str, Any], delta: float) -> str:
        role = str(promise.get("role") or "promesa").strip()
        if delta > 0:
            return f"Promesa cumplida: {role}"
        return f"Promesa incumplida: {role}"
