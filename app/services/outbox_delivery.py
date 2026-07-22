"""Delivery orchestration for persisted outbox events."""

from __future__ import annotations

import logging
import socket
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain._values import parse_bool, parse_int
    from ..integrations.discord import redact_secrets
    from .notifications import (
        EventNotification,
        NotificationCompositionService,
        free_agent_signed_notification,
    )
except ImportError:  # pragma: no cover
    from domain._values import parse_bool, parse_int
    from integrations.discord import redact_secrets
    from services.notifications import EventNotification, NotificationCompositionService, free_agent_signed_notification


class OutboxDeliveryService:
    """Resolve persisted event types into notifications and record delivery state."""

    def __init__(
        self,
        outbox: Any,
        players: Any,
        *,
        deliver_notification: Callable[..., bool],
        logger: Optional[logging.Logger] = None,
        worker_id: Optional[str] = None,
        lease_seconds: int = 300,
        max_attempts: int = 5,
    ) -> None:
        self.outbox = outbox
        self.players = players
        self.deliver_notification = deliver_notification
        self.logger = logger or logging.getLogger(__name__)
        self.worker_id = str(worker_id or f"{socket.gethostname()}:delivery").strip()[:120]
        self.lease_seconds = max(1, int(lease_seconds or 300))
        self.max_attempts = max(1, int(max_attempts or 5))

    def dispatch(self, event_ids: Optional[List[int]]) -> List[int]:
        delivered: List[int] = []
        for raw_event_id in event_ids or []:
            event_id = parse_int(raw_event_id)
            if event_id is None:
                continue
            if not self._claim(event_id):
                continue
            event = self.outbox.get(event_id)
            if not event:
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            try:
                if event_type == "discord.free_agent_signed":
                    if self._deliver_free_agent_signed(event_id, payload):
                        delivered.append(event_id)
                    continue
                if event_type == "discord.trade_processed":
                    if self._deliver_trade_processed(event_id, payload):
                        delivered.append(event_id)
                    continue
                self._mark_dead_letter(event_id, f"unknown_event_type:{event_type}", "unknown_event_type")
            except Exception as exc:
                clean_error = redact_secrets(exc)
                self.logger.error(
                    "Outbox event delivery failed id=%s type=%s: %s",
                    event_id,
                    event_type,
                    clean_error,
                )
                self._mark_failed(event_id, clean_error[:500], "delivery_exception")
        return delivered

    def dispatch_available(self, *, limit: int = 25) -> List[int]:
        claim_available = getattr(self.outbox, "claim_available", None)
        if not callable(claim_available):
            return []
        event_ids = claim_available(
            limit=limit,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        delivered: List[int] = []
        for event_id in event_ids:
            event = self.outbox.get(event_id)
            if not event:
                continue
            try:
                event_type = str(event.get("event_type") or "").strip()
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                if event_type == "discord.free_agent_signed":
                    if self._deliver_free_agent_signed(int(event_id), payload):
                        delivered.append(int(event_id))
                    continue
                if event_type == "discord.trade_processed":
                    if self._deliver_trade_processed(int(event_id), payload):
                        delivered.append(int(event_id))
                    continue
                self._mark_dead_letter(int(event_id), f"unknown_event_type:{event_type}", "unknown_event_type")
            except Exception as exc:
                clean_error = redact_secrets(exc)
                self.logger.error(
                    "Outbox event delivery failed id=%s type=%s: %s",
                    event_id,
                    event.get("event_type"),
                    clean_error,
                )
                self._mark_failed(int(event_id), clean_error[:500], "delivery_exception")
        return delivered

    def _claim(self, event_id: int) -> bool:
        claim = getattr(self.outbox, "claim", None)
        if not callable(claim):
            return True
        return bool(
            claim(
                event_id,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
        )

    def _mark_failed(self, event_id: int, error: Any, error_code: str) -> bool:
        try:
            return bool(self.outbox.mark_failed(event_id, error, error_code=error_code))
        except TypeError:
            return bool(self.outbox.mark_failed(event_id, error))

    def _mark_dead_letter(self, event_id: int, error: Any, error_code: str) -> bool:
        mark_dead_letter = getattr(self.outbox, "mark_dead_letter", None)
        if callable(mark_dead_letter):
            return bool(mark_dead_letter(event_id, error, error_code=error_code))
        return self._mark_failed(event_id, error, error_code)

    def _deliver_free_agent_signed(self, event_id: int, payload: Dict[str, Any]) -> bool:
        player = self.players.record(payload.get("player_id"))
        if not player:
            self._mark_dead_letter(event_id, "player_not_found", "referenced_entity_missing")
            return False
        event = free_agent_signed_notification(
            player,
            offer_payload=payload.get("offer_payload"),
            offer_type=payload.get("offer_type"),
        )
        sent = self._deliver(event, payload)
        if sent:
            self.outbox.mark_succeeded(event_id)
            return True
        self._mark_failed(event_id, "delivery_returned_false", "delivery_returned_false")
        return False

    def _deliver_trade_processed(self, event_id: int, payload: Dict[str, Any]) -> bool:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else None
        if not result:
            self._mark_dead_letter(event_id, "result_missing", "payload_invalid")
            return False
        event = NotificationCompositionService.trade_processed(result)
        # Preserve existing behavior: trade delivery is considered handled unless it raises.
        self._deliver(event, payload)
        self.outbox.mark_succeeded(event_id)
        return True

    def _deliver(self, event: EventNotification, payload: Dict[str, Any]) -> bool:
        custom_image = payload.get("custom_image") if isinstance(payload.get("custom_image"), dict) else None
        return bool(
            self.deliver_notification(
                event,
                generate_image=parse_bool(payload.get("generate_image")),
                custom_image=custom_image,
            )
        )
