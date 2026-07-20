"""Delivery orchestration for persisted outbox events."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain._values import parse_bool, parse_int
    from .notifications import (
        EventNotification,
        NotificationCompositionService,
        free_agent_signed_notification,
    )
except ImportError:  # pragma: no cover
    from domain._values import parse_bool, parse_int
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
    ) -> None:
        self.outbox = outbox
        self.players = players
        self.deliver_notification = deliver_notification
        self.logger = logger or logging.getLogger(__name__)

    def dispatch(self, event_ids: Optional[List[int]]) -> List[int]:
        delivered: List[int] = []
        for raw_event_id in event_ids or []:
            event_id = parse_int(raw_event_id)
            if event_id is None:
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
                self.outbox.mark_failed(event_id, f"unknown_event_type:{event_type}")
            except Exception as exc:
                self.logger.error(
                    "Outbox event delivery failed id=%s type=%s: %s",
                    event_id,
                    event_type,
                    exc,
                )
                self.outbox.mark_failed(event_id, str(exc)[:500])
        return delivered

    def _deliver_free_agent_signed(self, event_id: int, payload: Dict[str, Any]) -> bool:
        player = self.players.record(payload.get("player_id"))
        if not player:
            self.outbox.mark_failed(event_id, "player_not_found")
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
        self.outbox.mark_failed(event_id, "delivery_returned_false")
        return False

    def _deliver_trade_processed(self, event_id: int, payload: Dict[str, Any]) -> bool:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else None
        if not result:
            self.outbox.mark_failed(event_id, "result_missing")
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
