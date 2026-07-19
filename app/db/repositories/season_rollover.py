"""Persistence boundary for transactional season rollover."""

from __future__ import annotations

from typing import Any

from .base import LeagueRepository


class SeasonRolloverRepository(LeagueRepository):
    def transaction(self, mode: str = "IMMEDIATE") -> Any:
        return self.db.transaction(mode)

    def snapshot_payload(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._snapshot_payload_for_season(*args, **kwargs)

    def store_salary_history(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._store_player_salary_history_for_season_conn(*args, **kwargs)

    def increment_bird_years(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._increment_player_bird_years(*args, **kwargs)

    def freeze_second_apron_picks(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._freeze_second_apron_pick_rollover(*args, **kwargs)

    def rollover_draft_assets(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._rollover_draft_assets_conn(*args, **kwargs)

    def move_expired_players(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._move_expired_players_to_free_agents(*args, **kwargs)

    def cleanup_inactive_dead_contracts(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._cleanup_inactive_dead_contracts_conn(*args, **kwargs)
