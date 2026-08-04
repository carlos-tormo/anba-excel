"""Application service for team season objectives."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from ..domain._values import parse_int
    from ..domain.team_objectives import (
        compare_objectives,
        objective_options,
        require_objective_code,
        require_objective_result_code,
    )
except ImportError:  # pragma: no cover - direct script import compatibility
    from domain._values import parse_int
    from domain.team_objectives import (
        compare_objectives,
        objective_options,
        require_objective_code,
        require_objective_result_code,
    )


class TeamObjectiveService:
    def __init__(self, repository: Any, *, player_happiness: Any = None) -> None:
        self.repository = repository
        self.player_happiness = player_happiness

    def options(self) -> Dict[str, Any]:
        return {"objectives": objective_options()}

    def get(
        self,
        team_code: Any,
        season_year: Any = None,
        *,
        include_events: bool = False,
    ) -> Optional[Dict[str, Any]]:
        year = self._season_or_current(season_year)
        return self.repository.get(team_code, year, include_events=include_events)

    def current_for_team(
        self,
        team_code: Any,
        *,
        include_events: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return self.get(team_code, self.repository.current_year(), include_events=include_events)

    def for_team_context(self, team_code: Any, season_year: Any = None) -> Dict[str, Any]:
        year = self._season_or_current(season_year)
        objective = self.repository.get(team_code, year)
        return {
            "team_code": str(team_code or "").strip().upper(),
            "season_year": year,
            "objective": objective,
            "has_objective": objective is not None,
        }

    def for_player_join_context(self, team_code: Any, season_year: Any = None) -> Dict[str, Any]:
        context = self.for_team_context(team_code, season_year)
        if context.get("objective") is None and hasattr(self.repository, "latest_at_or_before"):
            context["objective"] = self.repository.latest_at_or_before(team_code, context["season_year"])
            context["has_objective"] = context["objective"] is not None
            context["objective_source"] = "latest_prior" if context["objective"] is not None else "none"
        else:
            context["objective_source"] = "current"
        objective = context.get("objective") or {}
        context["objective_season_year"] = objective.get("season_year")
        context["join_objective_code"] = objective.get("objective_code")
        context["join_objective_label"] = objective.get("objective_label_snapshot")
        return context

    def for_player_join_context_conn(
        self,
        conn: Any,
        team_code: Any,
        season_year: Any = None,
    ) -> Dict[str, Any]:
        year = parse_int(season_year)
        if year is None:
            year = self.repository.current_year_conn(conn)
        if year < 2000 or year > 2100:
            raise ValueError("invalid_season_year")
        objective = self.repository.get_conn(conn, team_code, year)
        objective_source = "current"
        if objective is None and hasattr(self.repository, "latest_at_or_before_conn"):
            objective = self.repository.latest_at_or_before_conn(conn, team_code, year)
            objective_source = "latest_prior" if objective is not None else "none"
        context = {
            "team_code": str(team_code or "").strip().upper(),
            "season_year": year,
            "objective": objective,
            "has_objective": objective is not None,
            "objective_source": objective_source,
        }
        objective = objective or {}
        context["objective_season_year"] = objective.get("season_year")
        context["join_objective_code"] = objective.get("objective_code")
        context["join_objective_label"] = objective.get("objective_label_snapshot")
        return context

    def list_for_season(self, season_year: Any = None) -> Dict[str, Any]:
        year = self._season_or_current(season_year)
        return {"season_year": year, "objectives": self.repository.list_for_season(year)}

    def set_agreed(
        self,
        team_code: Any,
        season_year: Any,
        objective: Any,
        actor: Optional[Dict[str, Any]] = None,
        *,
        status: Any = "agreed",
        owner_conversation_id: Any = None,
        expected_version: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        require_objective_code(objective)
        year = self._season_or_current(season_year)
        previous = self.repository.get(team_code, year)
        result = self.repository.set_objective(
            team_code,
            year,
            objective,
            status=status,
            actor=actor or {},
            owner_conversation_id=owner_conversation_id,
            expected_version=expected_version,
            metadata=metadata,
        )
        if self.player_happiness is not None:
            result["happiness_impact"] = self.player_happiness.apply_team_objective_change(
                team_code=str(team_code or "").strip().upper(),
                previous_objective=(previous or {}).get("objective_code"),
                new_objective=result.get("objective_code"),
                season_year=year,
                source_entity_id=result.get("id"),
                actor=actor or {},
            )
        return result

    def set_objective(
        self,
        team_code: Any,
        season_year: Any,
        objective: Any,
        actor: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self.set_agreed(team_code, season_year, objective, actor, **kwargs)

    def resolve(
        self,
        team_code: Any,
        season_year: Any,
        achieved: Any,
        actor: Optional[Dict[str, Any]] = None,
        *,
        expected_version: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        require_objective_result_code(achieved)
        result = self.repository.resolve_objective(
            team_code,
            self._season_or_current(season_year),
            achieved,
            actor=actor or {},
            expected_version=expected_version,
            metadata=metadata,
        )
        result["comparison"] = compare_objectives(result.get("objective_code"), result.get("achieved_code"))
        if self.player_happiness is not None:
            result["happiness_impact"] = self.player_happiness.apply_team_objective_resolution(
                team_code=str(team_code or "").strip().upper(),
                agreed_objective=result.get("objective_code"),
                achieved_objective=result.get("achieved_code"),
                season_year=result.get("season_year"),
                source_entity_id=result.get("id"),
                actor=actor or {},
            )
        return result

    def _season_or_current(self, season_year: Any = None) -> int:
        parsed = parse_int(season_year)
        if parsed is None:
            parsed = self.repository.current_year()
        if parsed < 2000 or parsed > 2100:
            raise ValueError("invalid_season_year")
        return int(parsed)
