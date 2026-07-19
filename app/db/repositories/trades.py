"""Persistence boundary for the trade service."""

from __future__ import annotations

from typing import Any

from .base import LeagueRepository


class TradeRepository(LeagueRepository):
    def normalize_request(self, payload: Any) -> Any:
        return self.db._trade_machine_normalized_request(payload)

    def validate(self, payload: Any) -> Any:
        return self.db.validate_trade_machine(payload)

    def validation_from_process_payload(self, payload: Any) -> Any:
        return self.db.trade_validation_from_process_payload(payload)

    def process_command(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.process_trade_command(*args, **kwargs)
