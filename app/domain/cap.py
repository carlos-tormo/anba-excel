"""Pure salary-cap, luxury-tax, and cap-hold rules."""

from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, List

from ._values import parse_amount_like, parse_bool, parse_float, parse_int
from .contracts import (
    cap_hold_bird_code_from_years,
    has_numeric_season_salary,
    has_standard_cap_hold_marker,
    is_exhibit10_player,
    is_qo_style_option,
    is_restricted_rights_player,
    is_two_way_player,
    maximum_salary_for_experience,
    minimum_salary_for_season,
    row_salary_num,
    salary_looks_like_minimum,
    season_option_code,
    season_salary_text_code,
)

OPEN_ROSTER_SPOT_MINIMUM = 12
CAP_FORECAST_MIN_YEAR = 2025
CAP_FORECAST_MAX_YEAR = 2035
CAP_FORECAST_WINDOW = 6


def salary_floor_for_season(settings: Dict[str, str], season: int, salary_cap: float) -> float:
    cap = float(salary_cap or 0.0)
    configured = parse_float(settings.get(f"salary_floor_{int(season)}"))
    if configured is None and int(season) == 2025:
        configured = parse_float(settings.get("salary_floor_2025"))
    if configured is not None and configured > 0:
        return float(configured)
    return cap * 0.9


def apply_salary_floor(settings: Dict[str, str], season: int, salary_cap: float, cap_figure: float) -> float:
    raw = float(cap_figure or 0.0)
    if parse_bool(settings.get("free_agency_mode")):
        return raw
    return max(raw, salary_floor_for_season(settings, season, salary_cap))


def luxury_tax_amount(overage: float, repeater: bool) -> float:
    remaining = max(0.0, float(overage or 0.0))
    if not math.isfinite(remaining) or remaining <= 0:
        return 0.0
    tier_size = 5_000_000.0
    base_rates = [2.5, 2.75, 3.5, 4.25] if repeater else [1.5, 1.75, 2.5, 3.25]
    tax = 0.0
    for rate in base_rates:
        if remaining <= 0:
            return tax
        taxable = min(tier_size, remaining)
        tax += taxable * rate
        remaining -= taxable
    if remaining <= 0:
        return tax
    first_extra_rate = base_rates[-1] + 0.5
    full_extra_tiers = int(remaining // tier_size)
    partial_extra = remaining - (full_extra_tiers * tier_size)
    if full_extra_tiers > 0:
        rate_sum = (full_extra_tiers / 2.0) * (
            (2.0 * first_extra_rate) + ((full_extra_tiers - 1) * 0.5)
        )
        tax += tier_size * rate_sum
    if partial_extra > 0:
        tax += partial_extra * (first_extra_rate + (full_extra_tiers * 0.5))
    return tax


def row_salary_history_num(row: Dict[str, Any], season: int) -> float:
    value = row.get(f"salary_{season}_history_num")
    if value is not None:
        return float(value or 0.0)
    return parse_amount_like(row.get(f"salary_{season}_history_text")) or 0.0


def cap_hold_previous_salary_num(row: Dict[str, Any], season: int) -> float:
    previous_season = int(season) - 1
    direct_salary = row_salary_num(row, previous_season)
    return direct_salary if direct_salary > 0 else row_salary_history_num(row, previous_season)


def salary_text_indicates_minimum(value: Any) -> bool:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace(".", "").replace(" ", "")
    return normalized in {"min", "minimo", "minimum"} or normalized.startswith("minimo")


def cap_hold_previous_salary_is_minimum(row: Dict[str, Any], season: int) -> bool:
    previous_season = int(season) - 1
    return salary_text_indicates_minimum(
        row.get(f"salary_{previous_season}_text")
    ) or salary_text_indicates_minimum(row.get(f"salary_{previous_season}_history_text"))


def cap_hold_amount(row: Dict[str, Any], season: int, settings: Dict[str, str], salary_cap: float) -> float:
    if not parse_bool(settings.get("free_agency_mode")):
        return 0.0
    current_year = parse_int(settings.get("current_year")) or 2025
    if int(season) != int(current_year):
        return 0.0

    def capped_hold(raw_amount: float) -> float:
        amount = float(round(raw_amount or 0.0))
        if amount <= 0:
            return 0.0
        return min(amount, maximum_salary_for_experience(salary_cap, row.get("experience_years")))

    text_code = season_salary_text_code(row, season)
    option_code = season_option_code(row, season)
    is_qo = is_qo_style_option(row, season)
    bird_code = (
        text_code
        if text_code in {"NB", "EB", "FB"}
        else option_code if option_code in {"NB", "EB", "FB"} else ""
    )
    if is_qo and not bird_code and not is_restricted_rights_player(row):
        bird_code = cap_hold_bird_code_from_years(row.get("years_left"))
    if not is_qo and has_numeric_season_salary(row, season):
        return 0.0
    if is_two_way_player(row):
        return capped_hold(minimum_salary_for_season(salary_cap, 1, 1)) if is_qo else 0.0

    previous_salary = cap_hold_previous_salary_num(row, season)
    previous_salary_is_minimum = cap_hold_previous_salary_is_minimum(row, season)
    if is_qo and is_restricted_rights_player(row):
        average_salary = parse_float(settings.get(f"average_salary_{season - 1}")) or 0.0
        if previous_salary <= 0 or average_salary <= 0:
            return 0.0
        return capped_hold(previous_salary * (3.0 if previous_salary < average_salary else 2.5))
    if not bird_code or (
        previous_salary <= 0 and not (bird_code == "NB" and previous_salary_is_minimum)
    ):
        return 0.0
    if bird_code == "NB":
        rights = str(row.get("bird_rights") or "").strip().upper()
        previous_cap = parse_float(settings.get(f"salary_cap_{season - 1}")) or salary_cap
        if (
            rights in {"MIN", "TW"}
            or previous_salary_is_minimum
            or salary_looks_like_minimum(previous_salary, previous_cap)
        ):
            return capped_hold(minimum_salary_for_season(salary_cap, 2, 1))
        return capped_hold(previous_salary * 1.2)
    if bird_code == "EB":
        return capped_hold(previous_salary * 1.3)
    if bird_code == "FB":
        average_salary = parse_float(settings.get(f"average_salary_{season - 1}")) or 0.0
        if average_salary <= 0:
            return 0.0
        return capped_hold(previous_salary * (1.9 if previous_salary < average_salary else 1.5))
    return 0.0


def counts_open_roster_minimum(row: Dict[str, Any], season: int, settings: Dict[str, str], salary_cap: float) -> bool:
    if is_two_way_player(row) or is_exhibit10_player(row):
        return False
    return (
        cap_hold_amount(row, season, settings, salary_cap) > 0
        or has_standard_cap_hold_marker(row, season)
        or row_salary_num(row, season) > 0
    )


def open_roster_spot_cap_hold(
    players: List[Dict[str, Any]],
    season: int,
    settings: Dict[str, str],
    salary_cap: float,
) -> Dict[str, float]:
    empty = {"roster_count": 0.0, "open_spots": 0.0, "minimum_salary": 0.0, "amount": 0.0}
    if not parse_bool(settings.get("free_agency_mode")):
        return empty
    current_year = parse_int(settings.get("current_year")) or 2025
    if int(season) != int(current_year):
        return empty
    roster_count = sum(
        1
        for player in players
        if counts_open_roster_minimum(player, season, settings, salary_cap)
    )
    open_spots = max(0, OPEN_ROSTER_SPOT_MINIMUM - roster_count)
    minimum_salary = minimum_salary_for_season(salary_cap, 0, 1)
    return {
        "roster_count": float(roster_count),
        "open_spots": float(open_spots),
        "minimum_salary": float(minimum_salary),
        "amount": float(open_spots * minimum_salary),
    }
