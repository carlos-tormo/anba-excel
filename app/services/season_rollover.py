"""Transactional season-rollover application service.

Every rollover mutation uses one explicit SQLite transaction: the season
snapshot, salary history, current-year setting, Bird-year progression, frozen
picks, draft assets, expired players, and dead-contract cleanup either all
commit or all roll back.
"""

from __future__ import annotations

import json
from typing import Any, Dict

try:
    from ..db.repositories.season_rollover import SeasonRolloverRepository
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover - supports direct script execution.
    from db.repositories.season_rollover import SeasonRolloverRepository
    from domain._values import parse_int


class SeasonRolloverService:
    def __init__(
        self,
        db: Any,
        *,
        contract_min_year: int,
        contract_max_start_year: int,
    ) -> None:
        configured_repository = getattr(db, "_season_rollover_repository", None)
        self.repository = db if isinstance(db, SeasonRolloverRepository) else (
            configured_repository or SeasonRolloverRepository(db)
        )
        self.contract_min_year = int(contract_min_year)
        self.contract_max_start_year = int(contract_max_start_year)
        if self.contract_max_start_year < self.contract_min_year:
            raise ValueError("invalid_contract_window")

    def progress_to_next_year(
        self,
        *,
        expected_current_year: Any = None,
        expected_current_year_version: Any = None,
    ) -> Dict[str, Any]:
        with self.repository.transaction("IMMEDIATE") as conn:
            settings = self._settings(conn)
            current_year = self._current_year(settings)
            if current_year >= self.contract_max_start_year:
                raise ValueError("cannot_progress_beyond_contract_window")
            return self._rollover_conn(
                conn,
                settings,
                previous_year=current_year,
                next_year=current_year + 1,
                create_snapshot=True,
                expected_current_year=parse_int(expected_current_year),
                expected_current_year_version=parse_int(expected_current_year_version),
            )

    def update_current_year(
        self,
        next_year: int,
        *,
        expected_current_year: Any = None,
        expected_current_year_version: Any = None,
    ) -> Dict[str, Any]:
        target_year = int(next_year)
        with self.repository.transaction("IMMEDIATE") as conn:
            settings = self._settings(conn)
            return self._rollover_conn(
                conn,
                settings,
                previous_year=self._current_year(settings),
                next_year=target_year,
                create_snapshot=False,
                expected_current_year=parse_int(expected_current_year),
                expected_current_year_version=parse_int(expected_current_year_version),
            )

    def _settings(self, conn: Any) -> Dict[str, str]:
        return self.repository.settings(conn)

    def _current_year(self, settings: Dict[str, str]) -> int:
        current_year = parse_int(settings.get("current_year")) or self.contract_min_year
        if current_year < self.contract_min_year or current_year > self.contract_max_start_year:
            return self.contract_min_year
        return int(current_year)

    def _rollover_conn(
        self,
        conn: Any,
        settings: Dict[str, str],
        *,
        previous_year: int,
        next_year: int,
        create_snapshot: bool,
        expected_current_year: int | None = None,
        expected_current_year_version: int | None = None,
    ) -> Dict[str, Any]:
        timestamp = self.repository.now()
        current_year_row = self.repository.current_year_row(conn)
        current_year_version_before = parse_int(current_year_row.get("version")) or 1
        if create_snapshot:
            snapshot = self.repository.snapshot_payload(conn, previous_year, settings)
            self.repository.insert_snapshot(
                conn, previous_year, json.dumps(snapshot), timestamp
            )

        delta = max(0, int(next_year) - int(previous_year))
        stored_salary_history = (
            self.repository.store_salary_history(
                conn, previous_year, timestamp
            )
            if delta > 0
            else 0
        )
        current_year_version_after = self.repository.update_current_year(
            conn,
            next_year,
            timestamp,
            expected_year=expected_current_year,
            expected_version=expected_current_year_version,
        )
        updated_bird_years = self.repository.increment_bird_years(
            conn, delta, timestamp
        )
        frozen_picks = self.repository.freeze_second_apron_picks(
            conn, previous_year, int(next_year), settings, timestamp
        )
        draft_rollover = self.repository.rollover_draft_assets(
            conn, previous_year, int(next_year), timestamp
        )
        moved_free_agents = (
            self.repository.move_expired_players(
                conn, int(next_year), timestamp
            )
            if delta > 0
            else 0
        )
        dead_contract_cleanup = self.repository.cleanup_inactive_dead_contracts(
            conn, int(next_year)
        )
        return {
            "previous_year": int(previous_year),
            "current_year": int(next_year),
            "command_id": f"season-rollover:{int(previous_year)}:{int(next_year)}",
            "validation_result": "valid",
            "entity_versions": {
                "previous_year": int(previous_year),
                "current_year": int(next_year),
                "current_year_version_before": current_year_version_before,
                "current_year_version_after": current_year_version_after,
                "snapshot_created": bool(create_snapshot),
            },
            "salary_history_rows_stored": stored_salary_history,
            "bird_year_steps": delta,
            "bird_year_players_updated": updated_bird_years,
            "players_moved_to_free_agents": moved_free_agents,
            "dead_contracts_removed": int(dead_contract_cleanup["count"]),
            "removed_dead_contracts": dead_contract_cleanup["dead_contracts"],
            "deleted_draft_assets": int(draft_rollover["deleted_draft_assets"]),
            "deleted_draft_asset_years": draft_rollover["deleted_draft_asset_years"],
            "future_draft_asset_years": draft_rollover["future_draft_asset_years"],
            "created_future_draft_assets": len(
                draft_rollover["created_future_draft_assets"]
            ),
            "future_draft_assets": draft_rollover["created_future_draft_assets"],
            "frozen_picks_created": len(frozen_picks),
            "frozen_picks": frozen_picks,
        }
