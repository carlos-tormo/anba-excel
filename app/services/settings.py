"""Application service for validating and applying global league settings."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Optional

try:
    from ..domain._values import parse_bool, parse_float, parse_int
    from ..domain.cap import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR
    from ..domain.trade_rules import normalize_move_phase
    from ..domain_rules import parse_free_agent_rep_discord_ids, public_settings_payload
except ImportError:  # pragma: no cover
    from domain._values import parse_bool, parse_float, parse_int
    from domain.cap import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR
    from domain.trade_rules import normalize_move_phase
    from domain_rules import parse_free_agent_rep_discord_ids, public_settings_payload


class SettingsService:
    def __init__(
        self,
        repository: Any,
        *,
        season_rollover: Any,
        contract_seasons: Iterable[int],
        max_start_year: int,
    ) -> None:
        self.repository = repository
        self.season_rollover = season_rollover
        self.contract_seasons = tuple(int(year) for year in contract_seasons)
        self.max_start_year = int(max_start_year)

    @staticmethod
    def _positive(payload: Dict[str, Any], field: str, *, allow_zero: bool = False) -> Optional[float]:
        if field not in payload:
            return None
        value = parse_float(str(payload.get(field)))
        if value is None or value < 0 or (not allow_zero and value <= 0):
            raise ValueError(f"invalid_{field}")
        return value

    @staticmethod
    def _nonnegative_int(payload: Dict[str, Any], field: str) -> Optional[int]:
        if field not in payload:
            return None
        value = parse_int(str(payload.get(field)))
        if value is None or value < 0:
            raise ValueError(f"invalid_{field}")
        return value

    @staticmethod
    def _representatives(raw: Any) -> list[str]:
        values = raw if isinstance(raw, list) else str(raw or "").splitlines()
        result: list[str] = []
        seen = set()
        for raw_value in values:
            value = str(raw_value or "").strip()
            if not value:
                continue
            if len(value) > 80:
                raise ValueError("invalid_free_agent_reps")
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
        if len(result) > 100:
            raise ValueError("invalid_free_agent_reps")
        return result

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        updates: Dict[str, str] = {}
        audit: Dict[str, Any] = {}

        numeric_fields = {
            "salary_cap_2025": False,
            "first_apron": False,
            "second_apron": False,
            "cash_limit_total": True,
        }
        for field, allow_zero in numeric_fields.items():
            value = self._positive(payload, field, allow_zero=allow_zero)
            if value is not None:
                updates[field] = str(int(value))
                audit[field] = value

        current_year = None
        if "current_year" in payload:
            current_year = parse_int(str(payload.get("current_year")))
            if (
                current_year is None
                or current_year < min(self.contract_seasons)
                or current_year > self.max_start_year
            ):
                raise ValueError("invalid_current_year")
            audit["current_year"] = current_year

        for field in ("trade_move_limit_pre30", "trade_move_limit_post30"):
            value = self._nonnegative_int(payload, field)
            if value is not None:
                updates[field] = str(value)
                audit[field] = value

        if "trade_move_phase" in payload:
            value = normalize_move_phase(payload.get("trade_move_phase"))
            updates["trade_move_phase"] = value
            audit["trade_move_phase"] = value
        for field in ("free_agency_mode", "discord_free_agent_offer_role_ping_enabled"):
            if field in payload:
                value = parse_bool(payload.get(field))
                updates[field] = "1" if value else "0"
                audit[field] = value

        season_cap_updates: Dict[str, Optional[float]] = {}
        rookie_scale_updates: Dict[str, Optional[float]] = {}
        for field, raw_value in payload.items():
            cap_match = re.fullmatch(
                r"(salary_cap|salary_floor|first_apron|second_apron|average_salary)_(\d{4})",
                str(field),
            )
            if cap_match and field != "salary_cap_2025":
                year = parse_int(cap_match.group(2))
                if year is None or not CAP_FORECAST_MIN_YEAR <= year <= CAP_FORECAST_MAX_YEAR:
                    raise ValueError(f"invalid_{field}")
                if cap_match.group(1) == "average_salary" and (
                    raw_value is None or not str(raw_value).strip()
                ):
                    value = None
                else:
                    value = parse_float(str(raw_value))
                    if value is None or value <= 0:
                        raise ValueError(f"invalid_{field}")
                season_cap_updates[str(field)] = value
                updates[str(field)] = "" if value is None else str(int(value))
                continue
            rookie_match = re.fullmatch(r"rookie_scale_(\d{4})_([1-9]|[12]\d|30)", str(field))
            if rookie_match:
                year = parse_int(rookie_match.group(1))
                if year is None or not CAP_FORECAST_MIN_YEAR <= year <= CAP_FORECAST_MAX_YEAR:
                    raise ValueError(f"invalid_{field}")
                if raw_value is None or not str(raw_value).strip():
                    value = None
                else:
                    value = parse_float(str(raw_value))
                    if value is None or value <= 0:
                        raise ValueError(f"invalid_{field}")
                rookie_scale_updates[str(field)] = value
                updates[str(field)] = "" if value is None else str(int(value))

        roster_fields = (
            "roster_standard_min",
            "roster_standard_max",
            "roster_standard_offseason_max",
            "roster_two_way_min",
            "roster_two_way_max",
        )
        roster_updates: Dict[str, int] = {}
        for field in roster_fields:
            value = self._nonnegative_int(payload, field)
            if value is not None:
                roster_updates[field] = value
                updates[field] = str(value)
                audit[field] = value

        current = public_settings_payload(self.repository.get_all())
        standard_min = roster_updates.get("roster_standard_min", int(current["roster_standard_min"]))
        standard_max = roster_updates.get("roster_standard_max", int(current["roster_standard_max"]))
        offseason_max = roster_updates.get(
            "roster_standard_offseason_max", int(current["roster_standard_offseason_max"])
        )
        two_way_min = roster_updates.get("roster_two_way_min", int(current["roster_two_way_min"]))
        two_way_max = roster_updates.get("roster_two_way_max", int(current["roster_two_way_max"]))
        if standard_min > standard_max or standard_max > offseason_max:
            raise ValueError("invalid_roster_standard_range")
        if two_way_min > two_way_max:
            raise ValueError("invalid_roster_two_way_range")

        if "free_agent_reps" in payload:
            reps = self._representatives(payload.get("free_agent_reps"))
            updates["free_agent_reps"] = json.dumps(reps, ensure_ascii=False)
            audit["free_agent_reps"] = reps
        if "free_agent_rep_discord_ids" in payload:
            ids = parse_free_agent_rep_discord_ids(payload.get("free_agent_rep_discord_ids"))
            if len(ids) > 100:
                raise ValueError("invalid_free_agent_rep_discord_ids")
            updates["free_agent_rep_discord_ids"] = json.dumps(ids, ensure_ascii=False)
            audit["free_agent_rep_discord_ids"] = ids

        if not updates and current_year is None:
            raise ValueError("settings_payload_required")
        salary_cap_2025 = updates.pop("salary_cap_2025", None)
        if salary_cap_2025 is not None:
            self.repository.update("salary_cap_2025", salary_cap_2025)
        if current_year is not None:
            audit["current_year_update"] = self.season_rollover.update_current_year(
                current_year,
                expected_current_year=payload.get("expected_current_year"),
                expected_current_year_version=payload.get("expected_current_year_version"),
            )
        for key, value in updates.items():
            self.repository.update(key, value)
        audit["season_cap_updates"] = season_cap_updates
        audit["rookie_scale_updates"] = rookie_scale_updates
        return {"settings": public_settings_payload(self.repository.get_all()), "audit": audit}

    def get_all(self) -> Dict[str, str]:
        return self.repository.get_all()

    def public(self) -> Dict[str, Any]:
        return public_settings_payload(self.repository.get_all())

    def free_agency_mode_enabled(self) -> bool:
        return parse_bool(self.repository.get_all().get("free_agency_mode"))

    def list_team_economy(self, season_year: Optional[int] = None) -> Dict[str, Any]:
        return self.repository.list_team_economy(season_year)

    def upsert_team_economy(self, season_year: int, rows: list[Dict[str, Any]]) -> Dict[str, Any]:
        return self.repository.upsert_team_economy(season_year, rows)
