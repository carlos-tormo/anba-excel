"""Pure contract, salary-scale, and roster-slot rules."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from ._values import parse_amount_like, parse_bool

ROSTER_STANDARD_MIN_DEFAULT = 14
ROSTER_STANDARD_MAX_DEFAULT = 15
ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT = 18
ROSTER_TWO_WAY_MIN_DEFAULT = 0
ROSTER_TWO_WAY_MAX_DEFAULT = 3
CONTRACT_SEASON_MAX_YEAR = 2031
CONTRACT_SEASON_WINDOW = 6
CONTRACT_SEASON_MAX_START_YEAR = CONTRACT_SEASON_MAX_YEAR - CONTRACT_SEASON_WINDOW + 1
PLAYER_CONTRACT_SEASONS = tuple(range(2025, CONTRACT_SEASON_MAX_YEAR + 1))
MINIMUM_SALARY_BASE_CAP = 154_647_000.0
MINIMUM_2_YOS_BASE_SALARY = 2_296_274.0
TWO_WAY_MINIMUM_BASE_SALARY = 636_435.0
MINIMUM_SALARY_BASE_ROWS = {
    0: (1_272_870.0, None, None, None, None),
    1: (2_048_494.0, 2_150_917.0, None, None, None),
    2: (2_296_274.0, 2_411_090.0, 2_525_901.0, None, None),
    3: (2_378_870.0, 2_497_812.0, 2_616_754.0, 2_735_698.0, None),
    4: (2_461_463.0, 2_584_539.0, 2_707_612.0, 2_830_685.0, 2_953_760.0),
    5: (2_667_947.0, 2_801_346.0, 2_934_742.0, 3_068_140.0, 3_201_538.0),
    6: (2_874_436.0, 3_018_158.0, 3_161_876.0, 3_305_598.0, 3_449_321.0),
    7: (3_080_921.0, 3_234_968.0, 3_389_014.0, 3_543_059.0, 3_697_107.0),
    8: (3_287_409.0, 3_451_779.0, 3_616_151.0, 3_780_524.0, 3_944_896.0),
    9: (3_493_898.0, 3_659_836.0, 3_825_773.0, 3_991_710.0, 4_157_649.0),
    10: (3_634_153.0, 3_815_861.0, 3_997_570.0, 4_179_277.0, 4_360_985.0),
}


def contract_option_rejection_clear_payload(season: int) -> Dict[str, Any]:
    """Clear the rejected option season and every future contract year."""
    payload: Dict[str, Any] = {}
    for year in PLAYER_CONTRACT_SEASONS:
        if year < season:
            continue
        payload[f"salary_{year}_text"] = None
        payload[f"salary_{year}_guaranteed_text"] = None
        payload[f"salary_{year}_note_text"] = None
        payload[f"option_{year}"] = None
        payload[f"salary_{year}_provisional"] = False
        payload[f"salary_{year}_partially_guaranteed"] = False
        payload[f"salary_{year}_note"] = False
    return payload


def normalize_bird_years(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw or raw == "0":
        return None
    compact = raw.replace(" ", "").replace(",", ".")
    if compact in {"1", "1.0"}:
        return "1"
    if compact in {"2", "2.0"}:
        return "2"
    return "2+" if compact == "2+" else None


def increment_bird_years_value(value: Any, seasons: int = 1) -> Optional[str]:
    steps = max(0, int(seasons or 0))
    level = {"1": 1, "2": 2, "2+": 3}.get(normalize_bird_years(value) or "", 0)
    level = min(3, level + steps)
    if level <= 0:
        return None
    return "2+" if level >= 3 else str(level)


def cap_hold_bird_code_from_years(value: Any) -> str:
    return {"1": "NB", "2": "EB", "2+": "FB"}.get(normalize_bird_years(value) or "", "")


def normalize_experience_years(value: Any) -> Optional[int]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("+"):
        raw = raw[:-1]
    try:
        parsed = int(float(raw.replace(",", ".")))
    except ValueError:
        return None
    return max(0, min(50, parsed))


def row_salary_num(row: Dict[str, Any], season: int) -> float:
    value = row.get(f"salary_{season}_num")
    if value is not None:
        return float(value or 0.0)
    return parse_amount_like(row.get(f"salary_{season}_text")) or 0.0


def has_numeric_season_salary(row: Dict[str, Any], season: int) -> bool:
    value = row.get(f"salary_{season}_num")
    if value is not None:
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            pass
    return parse_amount_like(row.get(f"salary_{season}_text")) is not None


def season_salary_text_code(row: Dict[str, Any], season: int) -> str:
    return str(row.get(f"salary_{season}_text") or "").strip().upper()


def season_option_code(row: Dict[str, Any], season: int) -> str:
    return str(row.get(f"option_{season}") or "").strip().upper()


def option_accepted_by_team(row: Dict[str, Any], season: int, option: str) -> bool:
    expected = str(option or "").strip().upper()
    if not expected or season_option_code(row, season) != expected:
        return False
    decisions = row.get("option_decisions") or {}
    if not isinstance(decisions, dict):
        return False
    decision = decisions.get(f"option_{season}") or {}
    if not isinstance(decision, dict):
        return False
    return (
        str(decision.get("option_value") or "").strip().upper() == expected
        and str(decision.get("action") or "").strip().lower() == "accepted"
        and str(decision.get("status") or "").strip().lower() == "approved"
    )


def is_qo_style_option(row: Dict[str, Any], season: int) -> bool:
    return (
        season_salary_text_code(row, season) == "QO"
        or season_option_code(row, season) == "QO"
        or option_accepted_by_team(row, season, "GAP")
    )


def is_two_way_player(row: Dict[str, Any]) -> bool:
    return parse_bool(row.get("is_two_way")) or str(row.get("bird_rights") or "").strip().upper() == "TW"


def is_exhibit10_player(row: Dict[str, Any]) -> bool:
    normalized = re.sub(r"[\s_-]+", "", str(row.get("bird_rights") or "").strip().upper())
    return normalized in {"E10", "EXHIBIT10"}


def roster_contract_slot_type(row: Dict[str, Any], season: int) -> str:
    if is_exhibit10_player(row) or row_salary_num(row, season) <= 0:
        return ""
    return "two_way" if is_two_way_player(row) else "standard"


def roster_contract_counts(players: List[Dict[str, Any]], season: int) -> Dict[str, int]:
    counts = {"standard": 0, "two_way": 0}
    for player in players:
        slot_type = roster_contract_slot_type(player, season)
        if slot_type:
            counts[slot_type] += 1
    return counts


def is_free_agent_signed_contract(row: Dict[str, Any]) -> bool:
    return parse_bool(row.get("signed_as_free_agent"))


def minimum_salary_2_yos_for_cap(salary_cap: float) -> float:
    cap = float(salary_cap or MINIMUM_SALARY_BASE_CAP)
    return float(round(MINIMUM_2_YOS_BASE_SALARY * (cap / MINIMUM_SALARY_BASE_CAP)))


def scaled_minimum_salary(value: Optional[float], salary_cap: float) -> float:
    if value is None:
        return 0.0
    cap = float(salary_cap or MINIMUM_SALARY_BASE_CAP)
    return float(round(float(value) * (cap / MINIMUM_SALARY_BASE_CAP)))


def minimum_salary_for_season(salary_cap: float, experience_years: int, contract_year: int = 1) -> float:
    experience = max(0, min(10, int(experience_years or 0)))
    contract_idx = max(0, min(4, int(contract_year or 1) - 1))
    row = MINIMUM_SALARY_BASE_ROWS.get(experience)
    return scaled_minimum_salary(row[contract_idx], salary_cap) if row else 0.0


def maximum_salary_for_experience(salary_cap: float, experience_years: Any = None) -> float:
    cap = float(salary_cap or 0.0)
    experience = normalize_experience_years(experience_years)
    percentage = 0.35 if experience is None or experience >= 10 else 0.30 if experience >= 7 else 0.25
    return float(round(cap * percentage))


def minimum_salary_values_for_cap(salary_cap: float) -> List[float]:
    values = [scaled_minimum_salary(TWO_WAY_MINIMUM_BASE_SALARY, salary_cap)]
    for row in MINIMUM_SALARY_BASE_ROWS.values():
        values.extend(scaled_minimum_salary(value, salary_cap) for value in row if value)
    return [value for value in values if value > 0]


def salary_looks_like_minimum(amount: Any, salary_cap: float) -> bool:
    numeric = round(parse_amount_like(amount) or 0.0)
    return numeric > 0 and any(
        abs(numeric - minimum) <= 2 for minimum in minimum_salary_values_for_cap(salary_cap)
    )


def is_standard_minimum_contract(row: Dict[str, Any]) -> bool:
    normalized = unicodedata.normalize("NFKD", str(row.get("bird_rights") or "").strip().upper())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[\s_-]+", "", normalized)
    return normalized in {"MIN", "MINIMO", "MINIMUM"}


def minimum_contract_year_for_season(row: Dict[str, Any], season: int) -> int:
    target = int(season)
    salary_years = []
    for key in row.keys():
        match = re.fullmatch(r"salary_(\d{4})_(?:num|text)", str(key))
        if match and int(match.group(1)) <= target and row_salary_num(row, int(match.group(1))) > 0:
            salary_years.append(int(match.group(1)))
    return max(1, min(5, target - min(salary_years) + 1)) if salary_years else 1


def minimum_contract_team_salary(row: Dict[str, Any], season: int, salary_cap: float) -> float:
    salary = row_salary_num(row, season)
    if salary <= 0 or not is_standard_minimum_contract(row):
        return max(0.0, salary)
    experience = normalize_experience_years(row.get("experience_years"))
    if experience is None or experience <= 2:
        return salary
    contract_year = minimum_contract_year_for_season(row, season)
    return float(
        minimum_salary_for_season(salary_cap, 2, contract_year)
        or minimum_salary_2_yos_for_cap(salary_cap)
    )


def apron_yos_adjustment(row: Dict[str, Any], season: int, salary_cap: float) -> float:
    experience = normalize_experience_years(row.get("experience_years"))
    if experience not in {0, 1} or not is_free_agent_signed_contract(row):
        return 0.0
    salary = row_salary_num(row, season)
    return max(0.0, minimum_salary_2_yos_for_cap(salary_cap) - salary) if salary > 0 else 0.0


def is_restricted_rights_player(row: Dict[str, Any]) -> bool:
    rights = str(row.get("bird_rights") or "").strip().upper()
    return rights == "R" or rights.startswith("R(")


def has_standard_cap_hold_marker(row: Dict[str, Any], season: int) -> bool:
    if is_two_way_player(row) or is_exhibit10_player(row):
        return False
    text_code = season_salary_text_code(row, season)
    option_code = season_option_code(row, season)
    return (
        text_code in {"NB", "EB", "FB", "QO"}
        or option_code in {"NB", "EB", "FB", "QO"}
        or is_qo_style_option(row, season)
    )
