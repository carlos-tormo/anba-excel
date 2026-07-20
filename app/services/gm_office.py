"""Composition service for the GM-office aggregate read model."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_int


class GMOfficeService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    @staticmethod
    def spending_limit_payload(
        row: Optional[Any],
        team: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        item = dict(row) if row is not None else {}
        team = team or {}
        amount = parse_int(item.get("amount"))
        updated_at = str(item.get("updated_at") or "").strip()
        return {
            "team_code": normalize_team_code(item.get("team_code") or team.get("code")),
            "team_name": str(team.get("name") or item.get("team_name") or "").strip(),
            "amount": max(0, amount or 0),
            "amount_millions": round(max(0, amount or 0) / 1_000_000, 3),
            "updated_at": updated_at,
            "updated_by_email": str(item.get("updated_by_email") or "").strip(),
            "has_value": bool(updated_at),
        }

    def get(self, team_code: Any) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        rows = self.repository.read(normalized_team)
        team = rows["team"]
        team_name = str(team.get("name") or normalized_team)
        return {
            "team_code": normalized_team,
            "team_name": team_name,
            "offers": rows["offers"],
            "favorites": rows["favorites"],
            "free_agent_spending_limit": self.spending_limit_payload(
                rows["spending_limit"],
                {"code": normalized_team, "name": team_name},
            ),
            "depth_chart": rows["depth_chart"],
            "depth_chart_players": rows["depth_chart_players"],
            # Filled by the route when a current user is known.
            "minimum_targets": None,
        }
