"""Build the complete team detail read model from repository data and calculators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain_rules import parse_int
except ImportError:  # pragma: no cover
    from domain_rules import parse_int


@dataclass(frozen=True)
class TeamDetailOperations:
    select_players: Callable[..., List[Dict[str, Any]]]
    attach_option_decisions: Callable[..., None]
    select_frozen_draft_picks: Callable[..., List[Dict[str, Any]]]
    get_settings: Callable[[], Dict[str, Any]]
    luxury_repeater: Callable[..., bool]
    hard_cap: Callable[..., str]
    calculate_summary: Callable[..., Dict[str, Any]]
    season_summaries: Callable[..., List[Dict[str, Any]]]
    exception_estimates: Callable[..., Dict[str, Any]]
    attach_cap_hold_fields: Callable[..., None]
    move_summary: Callable[..., Dict[str, Any]]
    move_summaries: Callable[..., List[Dict[str, Any]]]
    luxury_history: Callable[..., List[Dict[str, Any]]]
    hard_caps: Callable[..., List[Dict[str, Any]]]
    depth_chart: Callable[..., Dict[str, Any]]


class TeamDetailService:
    def __init__(self, repository: Any, operations: TeamDetailOperations) -> None:
        self.repository = repository
        self._operations = operations

    def get(self, code: str, move_season_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with self.repository.connect() as conn:
            team = self.repository.team(conn, code)
            if not team:
                return None
            team_id = int(team["id"])

            players = self._operations.select_players(conn, team_id)
            self._operations.attach_option_decisions(conn, players, team_id)
            assets = self.repository.assets(conn, team_id)
            frozen_draft_picks = self._operations.select_frozen_draft_picks(conn, team_id)
            dead_contracts = self.repository.dead_contracts(conn, team_id)

            settings = self._operations.get_settings()
            current_year = parse_int(settings.get("current_year")) or 2025
            luxury_repeater = self._operations.luxury_repeater(conn, team_id, current_year)
            current_hard_cap = self._operations.hard_cap(
                conn, team_id, current_year, team.get("apron_hard_cap")
            )
            summary = self._operations.calculate_summary(
                team,
                players,
                assets,
                dead_contracts,
                settings,
                luxury_repeater=luxury_repeater,
                apron_hard_cap=current_hard_cap,
            )
            season_summaries = self._operations.season_summaries(
                conn, team, players, assets, dead_contracts, settings
            )
            exception_estimates = self._operations.exception_estimates(season_summaries, assets)
            self._operations.attach_cap_hold_fields(players, settings)
            requested_move_year = parse_int(move_season_year) or int(summary["current_year"])
            move_summary = self._operations.move_summary(conn, team_id, requested_move_year, settings)
            move_summaries = self._operations.move_summaries(
                conn, team_id, settings, include_year=requested_move_year
            )
            summary_year = int(summary["current_year"])
            luxury_history = self._operations.luxury_history(conn, team_id, summary_year)
            apron_hard_caps = self._operations.hard_caps(
                conn, team_id, summary_year, team.get("apron_hard_cap")
            )
            depth_chart = self._operations.depth_chart(conn, team_id)
            gm_history = self.repository.gm_history(conn, team_id)
            return {
                "team": team,
                "players": players,
                "assets": assets,
                "frozen_draft_picks": frozen_draft_picks,
                "dead_contracts": dead_contracts,
                "summary": summary,
                "season_summaries": season_summaries,
                "exception_estimates": exception_estimates,
                "move_summary": move_summary,
                "move_summaries": move_summaries,
                "luxury_history": luxury_history,
                "apron_hard_caps": apron_hard_caps,
                "depth_chart": depth_chart,
                "gm_history": gm_history,
            }
