"""Application orchestration for GM request decisions."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain._values import parse_int
    from ..workflow_states import WorkflowTransitionError
except ImportError:  # pragma: no cover
    from domain._values import parse_int
    from workflow_states import WorkflowTransitionError


class GMRequestService:
    """Coordinates cross-aggregate GM request commands in one transaction."""

    def __init__(
        self,
        requests: Any,
        *,
        workflows: Any,
        offer_promises: Any,
        notifications: Any,
        free_agency: Any,
        outbox: Any,
        players: Any,
        now: Callable[[], str],
        normalize_team_code: Callable[[Any], Optional[str]],
    ) -> None:
        self.requests = requests
        self.workflows = workflows
        self.offer_promises = offer_promises
        self.notifications = notifications
        self.free_agency = free_agency
        self.outbox = outbox
        self.players = players
        self.now = now
        self.normalize_team_code = normalize_team_code

    def __getattr__(self, name: str) -> Any:
        """Expose request-only repository operations to existing service clients."""
        return getattr(self.requests, name)

    def mark_free_agent_offer_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
        promise_context: Optional[Dict[str, Any]] = None,
        expected_version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = self.now()
        with self.requests.db.transaction("IMMEDIATE") as conn:
            try:
                self.workflows.transition_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    int(request_id),
                    normalized_status,
                    actor=admin,
                    reason=note or f"admin_{normalized_status}",
                    updates=self._decision_updates(admin, note, timestamp),
                    timestamp=timestamp,
                    expected_version=expected_version,
                )
            except WorkflowTransitionError as exc:
                if exc.code in {"workflow_not_found", "invalid_transition", "transition_conflict", "version_conflict"}:
                    return None
                raise
            if normalized_status == "approved":
                self.offer_promises._upsert_free_agent_offer_promise_for_request_conn(
                    conn, int(request_id), admin, timestamp, promise_context=promise_context
                )
        return self.requests.get_gm_free_agent_offer_request(request_id)

    def mark_gm_free_agent_offer_request_decided(self, request_id: int, status: str, admin: Dict[str, Any], note: Optional[str] = None, promise_context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return self.mark_free_agent_offer_decided(request_id, status, admin, note, promise_context)

    @staticmethod
    def _decision_updates(admin: Dict[str, Any], note: Optional[str], timestamp: str) -> Dict[str, Any]:
        return {
            "admin_email": str(admin.get("email") or "").strip() if admin else None,
            "admin_name": str(admin.get("name") or "").strip() if admin else None,
            "admin_decision_note": note,
            "updated_at": timestamp,
            "decided_at": timestamp,
        }

    def decide_free_agent_offer(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        *,
        note: Optional[str] = None,
        sign_payload: Optional[Dict[str, Any]] = None,
        offer_payload: Optional[Dict[str, Any]] = None,
        notify_discord: bool = False,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
        promise_context: Optional[Dict[str, Any]] = None,
        bypass_role_limits: bool = False,
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = self.now()
        parsed_request_id = int(request_id)
        player_id: Optional[int] = None
        outbox_event_ids: List[int] = []
        with self.requests.db.transaction("IMMEDIATE") as conn:
            request = self.requests._get_gm_free_agent_offer_request_conn(conn, parsed_request_id)
            if not request:
                raise ValueError("request_not_found")
            if str(request.get("status") or "").strip().lower() != "pending":
                raise ValueError("request_already_decided")

            if normalized_status == "rejected":
                self._transition_offer(conn, parsed_request_id, "rejected", admin, note, timestamp, expected_version=expected_version)
                player_name = str(request.get("player_name") or "el agente libre").strip()
                team_code = self.normalize_team_code(request.get("team_code")) or str(request.get("team_code") or "").upper()
                offer_label = "oferta de renovación" if str(request.get("offer_type") or "").strip().lower() == "renewal" else "oferta"
                body = f"La administración ha rechazado la {offer_label} de {team_code} por {player_name}."
                if note:
                    body = f"{body} Nota: {note}"
                self.notifications.create_conn(
                    conn,
                    user_id=request.get("requester_user_id"),
                    email=request.get("requester_email"),
                    title=f"Oferta rechazada: {player_name}",
                    body=body,
                    kind="free_agent_offer_rejected",
                    entity_type="gm_free_agent_offer_request",
                    entity_id=parsed_request_id,
                )
            else:
                free_agent_id = parse_int(request.get("free_agent_id"))
                team_code = self.normalize_team_code(request.get("team_code"))
                if free_agent_id is None:
                    raise ValueError("invalid_free_agent_id")
                if not team_code:
                    raise ValueError("invalid_team_code")
                free_agent = self.free_agency._free_agent_conn(conn, free_agent_id)
                if not free_agent:
                    raise ValueError("free_agent_not_found")
                player_id = self.free_agency._sign_free_agent_conn(conn, free_agent_id, team_code, sign_payload or {})
                if not player_id:
                    raise ValueError("free_agent_or_team_not_found")
                self._transition_offer(conn, parsed_request_id, "approved", admin, note, timestamp, expected_version=expected_version)
                self.offer_promises._upsert_free_agent_offer_promise_for_request_conn(
                    conn,
                    parsed_request_id,
                    admin,
                    timestamp,
                    promise_context=promise_context or {"free_agent": free_agent},
                    bypass_role_limits=bypass_role_limits,
                )
                if notify_discord:
                    event_id = self.outbox.enqueue_conn(
                        conn,
                        "discord.free_agent_signed",
                        {"player_id": player_id, "offer_payload": offer_payload or {}, "offer_type": request.get("offer_type"), "generate_image": bool(generate_image), "custom_image": custom_image},
                        aggregate_type="gm_free_agent_offer_request",
                        aggregate_id=parsed_request_id,
                        idempotency_key=f"gm_free_agent_offer_request:{parsed_request_id}:discord.free_agent_signed",
                    )
                    if event_id is not None:
                        outbox_event_ids.append(int(event_id))

        return {
            "request": self.requests.get_gm_free_agent_offer_request(parsed_request_id),
            "player_id": player_id,
            "player": self.players.record(player_id) if player_id is not None else None,
            "outbox_event_ids": outbox_event_ids,
            "command_id": f"gm-free-agent-offer:{parsed_request_id}:{normalized_status}",
            "validation_result": "valid",
        }

    def decide_gm_free_agent_offer_request_command(self, request_id: int, status: str, admin: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        return self.decide_free_agent_offer(request_id, status, admin, **kwargs)

    def _transition_offer(
        self,
        conn: Any,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str],
        timestamp: str,
        *,
        expected_version: Optional[int] = None,
    ) -> None:
        try:
            self.workflows.transition_conn(
                conn,
                "gm_free_agent_offer_request",
                request_id,
                status,
                actor=admin,
                reason=note or f"offer_{status}",
                updates=self._decision_updates(admin, note, timestamp),
                command_id=f"gm-free-agent-offer:{request_id}:{status}",
                timestamp=timestamp,
                expected_version=expected_version,
            )
        except WorkflowTransitionError as exc:
            if exc.code == "version_conflict":
                raise ValueError("stale_entity_version") from exc
            raise ValueError("request_already_decided") from exc
