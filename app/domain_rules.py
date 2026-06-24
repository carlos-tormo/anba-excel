import math
import re
from typing import Any, Dict, List, Optional


ROSTER_STANDARD_MIN_DEFAULT = 14
ROSTER_STANDARD_MAX_DEFAULT = 15
ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT = 18
ROSTER_TWO_WAY_MIN_DEFAULT = 0
ROSTER_TWO_WAY_MAX_DEFAULT = 3
OPEN_ROSTER_SPOT_MINIMUM = 12
CAP_FORECAST_MIN_YEAR = 2025
CAP_FORECAST_MAX_YEAR = 2035
CAP_FORECAST_WINDOW = 6
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
TRADE_MACHINE_MIN_TEAMS = 2
TRADE_MACHINE_MAX_TEAMS = 6
TRADE_MATCH_LOW_BAND = 7_250_000.0
TRADE_MATCH_HIGH_BAND = 29_000_000.0
TRADE_MATCH_CUSHION = 250_000.0
TRADE_MATCH_EXPANDED_BUFFER_RATIO = 0.05513854478
TRADE_MATCH_EXPANDED_BUFFER_FALLBACK = 8_527_000.0
TRADE_ROOM_TPE_BUFFER = 250_000.0
TRADE_PICK_ACTION_SEND = "send_pick"
TRADE_PICK_ACTION_SWAP = "swap_rights"
OFFSEASON_EXCEPTION_TAXPAYER_MLE_BASE_AMOUNT = 5_500_007.0
OFFSEASON_EXCEPTION_TAXPAYER_MLE_BASE_CAP = 154_647_000.0
OFFSEASON_EXCEPTION_NTMLE_RATIO = 0.0912
OFFSEASON_EXCEPTION_ROOM_MLE_RATIO = 0.05678
OFFSEASON_EXCEPTION_BAE_RATIO = 0.0332


def parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_amount_like(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "e" in text.lower():
        try:
            parsed = float(text)
            return parsed if math.isfinite(parsed) else None
        except ValueError:
            return None
    cleaned = re.sub(r"[€$]", "", text.replace(" ", ""))
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned and re.fullmatch(r"-?\d+\.\d{1,2}", cleaned):
        pass
    else:
        cleaned = cleaned.replace(".", "")
    cleaned = re.sub(r"[^0-9.-]", "", cleaned)
    if cleaned in {"", "-", "."}:
        return None
    try:
        parsed = float(cleaned)
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        return None


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "checked"}


def normalize_bird_years(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw or raw == "0":
        return None
    compact = raw.replace(" ", "").replace(",", ".")
    if compact in {"1", "1.0"}:
        return "1"
    if compact in {"2", "2.0"}:
        return "2"
    if compact == "2+":
        return "2+"
    return None


def increment_bird_years_value(value: Any, seasons: int = 1) -> Optional[str]:
    steps = max(0, int(seasons or 0))
    current = normalize_bird_years(value)
    level = {"1": 1, "2": 2, "2+": 3}.get(current or "", 0)
    level = min(3, level + steps)
    if level <= 0:
        return None
    if level >= 3:
        return "2+"
    return str(level)


def normalize_experience_years(value: Any) -> Optional[int]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("+"):
        raw = raw[:-1]
    raw = raw.replace(",", ".")
    try:
        parsed = int(float(raw))
    except ValueError:
        return None
    return max(0, min(50, parsed))


def season_label(start_year: Any) -> str:
    year = parse_int(str(start_year)) or 2025
    return f"{year}-{(year + 1) % 100:02d}"


def settings_int(settings: Dict[str, str], key: str, default: int) -> int:
    parsed = parse_int(settings.get(key))
    if parsed is None or parsed < 0:
        return default
    return parsed


def normalize_move_phase(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "").replace("-", "")
    if raw in {"post30", "post"}:
        return "post30"
    return "pre30"


def normalize_trade_bucket(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "").replace("-", "")
    if raw in {"post30", "post"}:
        return "post30"
    return "pre30"


def public_settings_payload(settings: Dict[str, str]) -> Dict[str, Any]:
    current_year = parse_int(settings.get("current_year")) or 2025
    if current_year < 2025 or current_year > 2030:
        current_year = 2025
    salary_cap = parse_float(settings.get("salary_cap_2025")) or 154647000.0
    salary_floor = salary_floor_for_season(settings, current_year, salary_cap)
    first_apron = parse_float(settings.get("first_apron")) or 195945000.0
    second_apron = parse_float(settings.get("second_apron")) or 207824000.0
    payload = {
        "salary_cap_2025": salary_cap,
        "salary_floor_2025": parse_float(settings.get("salary_floor_2025")) or salary_cap * 0.9,
        "current_year": current_year,
        "first_apron": first_apron,
        "second_apron": second_apron,
        "cash_limit_total": parse_float(settings.get("cash_limit_total")) or 0.0,
        "trade_move_limit_pre30": max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0),
        "trade_move_limit_post30": max(0, parse_int(settings.get("trade_move_limit_post30")) or 0),
        "trade_move_phase": normalize_move_phase(settings.get("trade_move_phase")),
        "free_agency_mode": parse_bool(settings.get("free_agency_mode")),
        "roster_standard_min": settings_int(settings, "roster_standard_min", ROSTER_STANDARD_MIN_DEFAULT),
        "roster_standard_max": settings_int(settings, "roster_standard_max", ROSTER_STANDARD_MAX_DEFAULT),
        "roster_standard_offseason_max": settings_int(
            settings,
            "roster_standard_offseason_max",
            ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT,
        ),
        "roster_two_way_min": settings_int(settings, "roster_two_way_min", ROSTER_TWO_WAY_MIN_DEFAULT),
        "roster_two_way_max": settings_int(settings, "roster_two_way_max", ROSTER_TWO_WAY_MAX_DEFAULT),
        "luxury_cap": salary_cap * 1.215,
        "minimum_cap_allowed": salary_floor,
    }
    for season in range(current_year, current_year + CAP_FORECAST_WINDOW):
        season_cap = parse_float(settings.get(f"salary_cap_{season}")) or salary_cap
        season_salary_floor = salary_floor_for_season(settings, season, season_cap)
        season_first_apron = parse_float(settings.get(f"first_apron_{season}")) or first_apron
        season_second_apron = parse_float(settings.get(f"second_apron_{season}")) or second_apron
        season_average_salary = parse_float(settings.get(f"average_salary_{season}"))
        payload[f"salary_cap_{season}"] = season_cap
        payload[f"salary_floor_{season}"] = season_salary_floor
        payload[f"first_apron_{season}"] = season_first_apron
        payload[f"second_apron_{season}"] = season_second_apron
        payload[f"average_salary_{season}"] = (
            season_average_salary if season_average_salary and season_average_salary > 0 else 0.0
        )
    return payload


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
    floor = salary_floor_for_season(settings, season, salary_cap)
    return max(raw, floor)


def luxury_tax_amount(overage: float, repeater: bool) -> float:
    remaining = max(0.0, float(overage or 0.0))
    if remaining <= 0:
        return 0.0
    tier_size = 5_000_000.0
    base_rates = [2.5, 2.75, 3.5, 4.25] if repeater else [1.5, 1.75, 2.5, 3.25]
    tax = 0.0
    tier_index = 0
    while remaining > 0:
        taxable = min(tier_size, remaining)
        if tier_index < len(base_rates):
            rate = base_rates[tier_index]
        else:
            rate = base_rates[-1] + ((tier_index - len(base_rates) + 1) * 0.5)
        tax += taxable * rate
        remaining -= taxable
        tier_index += 1
    return tax


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


def is_two_way_player(row: Dict[str, Any]) -> bool:
    return parse_bool(row.get("is_two_way")) or str(row.get("bird_rights") or "").strip().upper() == "TW"


def is_exhibit10_player(row: Dict[str, Any]) -> bool:
    normalized = re.sub(r"[\s_-]+", "", str(row.get("bird_rights") or "").strip().upper())
    return normalized in {"E10", "EXHIBIT10"}


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
    if not row:
        return 0.0
    return scaled_minimum_salary(row[contract_idx], salary_cap)


def minimum_salary_values_for_cap(salary_cap: float) -> List[float]:
    values = [scaled_minimum_salary(TWO_WAY_MINIMUM_BASE_SALARY, salary_cap)]
    for row in MINIMUM_SALARY_BASE_ROWS.values():
        values.extend(scaled_minimum_salary(value, salary_cap) for value in row if value)
    return [value for value in values if value > 0]


def salary_looks_like_minimum(amount: Any, salary_cap: float) -> bool:
    numeric = round(parse_amount_like(amount) or parse_float(amount) or 0.0)
    if numeric <= 0:
        return False
    return any(abs(numeric - minimum) <= 2 for minimum in minimum_salary_values_for_cap(salary_cap))


def apron_yos_adjustment(row: Dict[str, Any], season: int, salary_cap: float) -> float:
    experience = normalize_experience_years(row.get("experience_years"))
    if experience not in {0, 1}:
        return 0.0
    if not is_free_agent_signed_contract(row):
        return 0.0
    salary = row_salary_num(row, season)
    if salary <= 0:
        return 0.0
    return max(0.0, minimum_salary_2_yos_for_cap(salary_cap) - salary)


def is_restricted_rights_player(row: Dict[str, Any]) -> bool:
    rights = str(row.get("bird_rights") or "").strip().upper()
    return rights == "R" or rights.startswith("R(")


def has_standard_cap_hold_marker(row: Dict[str, Any], season: int) -> bool:
    if is_two_way_player(row) or is_exhibit10_player(row):
        return False
    text_code = season_salary_text_code(row, season)
    option_code = season_option_code(row, season)
    return text_code in {"NB", "EB", "FB", "QO"} or option_code in {"NB", "EB", "FB", "QO"}


def cap_hold_amount(row: Dict[str, Any], season: int, settings: Dict[str, str], salary_cap: float) -> float:
    if not parse_bool(settings.get("free_agency_mode")):
        return 0.0
    current_year = parse_int(settings.get("current_year")) or 2025
    if int(season) != int(current_year) + 1:
        return 0.0

    text_code = season_salary_text_code(row, season)
    option_code = season_option_code(row, season)
    is_qo = text_code == "QO" or option_code == "QO"
    bird_code = text_code if text_code in {"NB", "EB", "FB"} else option_code if option_code in {"NB", "EB", "FB"} else ""
    if not is_qo and has_numeric_season_salary(row, season):
        return 0.0

    if is_two_way_player(row):
        return minimum_salary_for_season(salary_cap, 1, 1) if is_qo else 0.0

    previous_salary = row_salary_num(row, season - 1)
    if is_qo and is_restricted_rights_player(row):
        average_salary = parse_float(settings.get(f"average_salary_{season - 1}")) or 0.0
        if previous_salary <= 0 or average_salary <= 0:
            return 0.0
        return float(round(previous_salary * (3.0 if previous_salary < average_salary else 2.5)))

    if not bird_code or previous_salary <= 0:
        return 0.0
    if bird_code == "NB":
        rights = str(row.get("bird_rights") or "").strip().upper()
        previous_cap = parse_float(settings.get(f"salary_cap_{season - 1}")) or salary_cap
        if rights in {"MIN", "TW"} or salary_looks_like_minimum(previous_salary, previous_cap):
            return minimum_salary_for_season(salary_cap, 2, 1)
        return float(round(previous_salary * 1.2))
    if bird_code == "EB":
        return float(round(previous_salary * 1.3))
    if bird_code == "FB":
        average_salary = parse_float(settings.get(f"average_salary_{season - 1}")) or 0.0
        if average_salary <= 0:
            return 0.0
        return float(round(previous_salary * (1.9 if previous_salary < average_salary else 1.5)))
    return 0.0


def open_roster_spot_cap_hold(players: List[Dict[str, Any]], season: int, settings: Dict[str, str], salary_cap: float) -> Dict[str, float]:
    if not parse_bool(settings.get("free_agency_mode")):
        return {"roster_count": 0.0, "open_spots": 0.0, "minimum_salary": 0.0, "amount": 0.0}
    current_year = parse_int(settings.get("current_year")) or 2025
    if int(season) != int(current_year) + 1:
        return {"roster_count": 0.0, "open_spots": 0.0, "minimum_salary": 0.0, "amount": 0.0}

    roster_count = 0
    for player in players:
        if is_two_way_player(player) or is_exhibit10_player(player):
            continue
        if cap_hold_amount(player, season, settings, salary_cap) > 0 or has_standard_cap_hold_marker(player, season):
            roster_count += 1
            continue
        if row_salary_num(player, season) > 0:
            roster_count += 1

    open_spots = max(0, OPEN_ROSTER_SPOT_MINIMUM - roster_count)
    minimum_salary = minimum_salary_for_season(salary_cap, 0, 1)
    return {
        "roster_count": float(roster_count),
        "open_spots": float(open_spots),
        "minimum_salary": float(minimum_salary),
        "amount": float(open_spots * minimum_salary),
    }


def format_trade_money(value: Any) -> str:
    amount = parse_float(value) or 0.0
    sign = "-" if amount < 0 else ""
    whole = int(round(abs(amount)))
    return f"${sign}{whole:,}".replace(",", ".")
