"""Persistence boundary for the draft service."""

from __future__ import annotations

from typing import Any

from .base import LeagueRepository


class DraftRepository(LeagueRepository):
    def current_year(self) -> Any:
        return self.db.current_draft_year()

    def list_order(self, draft_year: Any = None) -> Any:
        return self.db.list_draft_order(draft_year)

    def list_pick_ledger(self, draft_year: Any = None) -> Any:
        return self.db.list_draft_pick_ledger(draft_year)

    def order_entry(self, draft_order_id: int) -> Any:
        return self.db.get_draft_order_entry(draft_order_id)

    def create_order_entry(self, payload: Any) -> Any:
        return self.db.create_draft_order_entry(payload)

    def update_order_entry(self, draft_order_id: int, payload: Any) -> Any:
        return self.db.update_draft_order_entry(draft_order_id, payload)

    def delete_order_entry(self, draft_order_id: int) -> Any:
        return self.db.delete_draft_order_entry(draft_order_id)

    def list_live(self, draft_year: Any = None) -> Any:
        return self.db.list_draft_live(draft_year)

    def update_live_settings(self, payload: Any) -> Any:
        return self.db.update_draft_live_settings(payload)

    def control_live(self, payload: Any) -> Any:
        return self.db.control_draft_live(payload)

    def process_results(self, draft_year: Any = None) -> Any:
        return self.db.process_draft_results(draft_year)

    def submit_live_pick(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.submit_draft_live_pick(*args, **kwargs)

    def create_pick_request(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.create_gm_draft_pick_request(*args, **kwargs)

    def pick_request(self, request_id: int) -> Any:
        return self.db.get_gm_draft_pick_request(request_id)

    def mark_pick_request_decided(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.mark_gm_draft_pick_request_decided(*args, **kwargs)
