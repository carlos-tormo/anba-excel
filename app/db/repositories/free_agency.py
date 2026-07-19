"""Persistence boundary for the free-agency service."""

from __future__ import annotations

from typing import Any

from .base import LeagueRepository


class FreeAgencyRepository(LeagueRepository):
    def free_agent(self, free_agent_id: int) -> Any:
        return self.db.get_free_agent(free_agent_id)

    def create_offer_request(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.create_gm_free_agent_offer_request(*args, **kwargs)

    def offer_request(self, request_id: int) -> Any:
        return self.db.get_gm_free_agent_offer_request(request_id)

    def cancel_offer_request(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.cancel_gm_free_agent_offer_request(*args, **kwargs)

    def record_interest(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.record_free_agent_interest(*args, **kwargs)

    def set_favorite(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.set_free_agent_favorite(*args, **kwargs)

    def delete_favorite(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.delete_free_agent_favorite(*args, **kwargs)

    def sign(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.sign_free_agent(*args, **kwargs)

    def player_record(self, player_id: int) -> Any:
        return self.db.get_player_record(player_id)

    def create_promise(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.create_free_agent_offer_promise(*args, **kwargs)

    def list_promises(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.list_free_agent_offer_promises(*args, **kwargs)

    def update_promise(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.update_free_agent_offer_promise(*args, **kwargs)

    def create_bird_rights_renounce_request(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.create_gm_bird_rights_renounce_request(*args, **kwargs)

    def decide_offer_request(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.decide_gm_free_agent_offer_request_command(*args, **kwargs)

    def settings(self) -> Any:
        return self.db.get_settings()
