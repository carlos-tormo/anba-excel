"""Persistence boundary for the waiver service."""

from __future__ import annotations

from typing import Any

from .base import LeagueRepository


class WaiverRepository(LeagueRepository):
    def list(self, actor: Any = None) -> Any:
        return self.db.list_waivers(actor)

    def process_expired(self) -> Any:
        return self.db.process_expired_waivers_command()

    def create_claim(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.create_waiver_claim(*args, **kwargs)

    def list_claim_requests(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.list_waiver_claim_requests(*args, **kwargs)

    def decide_claim_request(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.decide_waiver_claim_request(*args, **kwargs)
