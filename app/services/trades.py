"""Trade workflow service.

This module is intentionally small for now: it gives route handlers a stable
trade-facing boundary while the existing LeagueDB implementation is migrated in
smaller, testable slices.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class TradeService:
    """Thin service facade for trade validation and processing workflows."""

    def __init__(self, db: Any):
        self.db = db

    def normalize_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.db._trade_machine_normalized_request(payload)

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.db.validate_trade_machine(payload)

    def validate_process_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.db.trade_validation_from_process_payload(payload)

    def process_command(
        self,
        payload: Dict[str, Any],
        *,
        validation: Optional[Dict[str, Any]] = None,
        expected_validation_hash: Any = None,
        require_validation_hash: bool = False,
        force_trade: bool = False,
        notify_discord: bool = True,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
        legacy: bool = False,
        actor: Optional[Dict[str, Any]] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.db.process_trade_command(
            payload,
            validation=validation,
            expected_validation_hash=expected_validation_hash,
            require_validation_hash=require_validation_hash,
            force_trade=force_trade,
            notify_discord=notify_discord,
            generate_image=generate_image,
            custom_image=custom_image,
            legacy=legacy,
            actor=actor,
            command_id=command_id,
        )

