"""Transactional offseason-exception generation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from ..db.repositories.offseason_exceptions import OffseasonExceptionRepository
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from db.repositories.offseason_exceptions import OffseasonExceptionRepository
    from domain._values import parse_int


@dataclass(frozen=True)
class OffseasonExceptionOperations:
    settings: Callable[[], Dict[str, str]]
    teams: Callable[[], List[Dict[str, Any]]]
    team_detail: Callable[..., Optional[Dict[str, Any]]]
    estimate: Callable[[Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]
    normalize_team_codes: Callable[[Any], List[str]]
    season_label: Callable[[int], str]
    now: Callable[[], str]
    generated_keys: tuple[str, ...]
    definitions: Dict[str, Dict[str, Any]]


class OffseasonExceptionService:
    def __init__(
        self, repository: OffseasonExceptionRepository,
        operations: OffseasonExceptionOperations,
    ) -> None:
        self.repository = repository
        self.operations = operations

    @staticmethod
    def _path_items(estimate: Dict[str, Any], path_key: str) -> List[Dict[str, Any]]:
        path = next((row for row in estimate.get("paths") or []
                     if str(row.get("key") or "").strip() == path_key), {})
        return list(path.get("eligible") or [])

    def generate(
        self, season_year: int, team_codes: Optional[List[str]] = None,
        choices: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        year = parse_int(season_year)
        if year is None:
            raise ValueError("invalid_season_year")
        selected_codes = set(self.operations.normalize_team_codes(team_codes)) if team_codes else None
        normalized_choices = {str(key).upper(): str(value or "").strip().lower()
                              for key, value in (choices or {}).items()}
        prepared: List[Dict[str, Any]] = []
        generated: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        valid_keys = set(self.operations.generated_keys)
        for team in self.operations.teams():
            team_code = str(team.get("code") or "").upper()
            if selected_codes is not None and team_code not in selected_codes:
                continue
            detail = self.operations.team_detail(team_code, move_season_year=year)
            team_row = (detail or {}).get("team") or {}
            team_id = parse_int(team_row.get("id"))
            summary = ((detail or {}).get("season_summaries") or {}).get(str(year))
            if team_id is None or not summary:
                continue
            estimate = self.operations.estimate(summary, detail.get("assets") or [])
            mode = str(estimate.get("operating_mode") or "")
            items = list(estimate.get("eligible") or [])
            if mode == "choice_pending":
                choice = normalized_choices.get(team_code)
                if choice == "room":
                    items = self._path_items(estimate, "room")
                elif choice in {"over_cap", "exceptions"}:
                    items = self._path_items(estimate, "over_cap")
                else:
                    skipped.append({"team_code": team_code, "reason": "choice_pending",
                                    "message": "Decisión pendiente: cap space o excepciones over-the-cap."})
                    continue
            elif mode not in {"room", "over_cap_below_first", "above_first_below_second"}:
                items = []
            values = estimate.get("values") or {}
            normalized_items = []
            for item in items:
                key = str(item.get("key") or "").strip()
                if key not in valid_keys:
                    continue
                definition = self.operations.definitions[key]
                amount = round(float(item.get("amount") or values.get(key) or 0.0))
                normalized_items.append({"key": key, "amount": amount,
                                         "label": definition["label"],
                                         "exception_type": definition["exception_type"],
                                         "detail": ("Excepción oficial generada automáticamente para "
                                                    f"{self.operations.season_label(year)}.")})
            prepared.append({"team_id": team_id, "team_code": team_code,
                             "operating_mode": mode, "items": normalized_items})
        created = self.repository.replace_generated(
            year, prepared, self.operations.generated_keys, self.operations.now()
        )
        for team in prepared:
            generated.append({"team_code": team["team_code"],
                              "operating_mode": team["operating_mode"],
                              "created": created.get(team["team_code"], [])})
        return {"ok": True, "season_year": year,
                "season_label": self.operations.season_label(year),
                "generated": generated, "skipped": skipped}

    def preview(self, season_year: Optional[int] = None) -> Dict[str, Any]:
        current_year = parse_int(self.operations.settings().get("current_year")) or 2025
        selected_year = parse_int(season_year) or current_year
        rows = []
        for team in self.operations.teams():
            detail = self.operations.team_detail(
                str(team.get("code") or ""), move_season_year=selected_year
            )
            summary = ((detail or {}).get("season_summaries") or {}).get(
                str(selected_year)
            )
            if not summary:
                continue
            rows.append(
                {
                    "team_code": team.get("code"),
                    "team_name": team.get("name"),
                    **self.operations.estimate(summary, detail.get("assets") or []),
                }
            )
        return {
            "season_year": selected_year,
            "season_label": self.operations.season_label(selected_year),
            "rows": rows,
        }
