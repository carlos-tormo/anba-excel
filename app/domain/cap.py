"""Pure salary-cap, luxury-tax, and cap-hold rules."""

from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, List, Optional

from ._values import parse_amount_like, parse_bool, parse_float, parse_int
from .contracts import (
    cap_hold_bird_code_from_years,
    CONTRACT_SEASON_MAX_YEAR,
    has_numeric_season_salary,
    has_standard_cap_hold_marker,
    is_exhibit10_player,
    is_qo_style_option,
    is_restricted_rights_player,
    is_two_way_player,
    maximum_salary_for_experience,
    minimum_salary_for_season,
    minimum_contract_team_salary,
    apron_yos_adjustment,
    roster_contract_counts,
    row_salary_num,
    salary_looks_like_minimum,
    season_option_code,
    season_salary_text_code,
)
from .exceptions import normalize_apron_hard_cap

OPEN_ROSTER_SPOT_MINIMUM = 12
CAP_FORECAST_MIN_YEAR = 2025
CAP_FORECAST_MAX_YEAR = 2035
CAP_FORECAST_WINDOW = 6


def normalize_dead_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"two_way", "tw"}:
        return "two_way"
    if raw in {"draft_hold", "draft_cap_hold", "rookie_hold"}:
        return "draft_hold"
    return "normal"


def dead_contract_salary_num(dead_contract: Dict[str, Any], season: int) -> float:
    value = dead_contract.get(f"salary_{season}_num")
    if value is not None:
        return float(value or 0.0)
    text_value = parse_amount_like(dead_contract.get(f"salary_{season}_text"))
    if text_value is not None:
        return text_value
    if season == 2025:
        amount_value = dead_contract.get("amount_num")
        if amount_value is not None:
            return float(amount_value or 0.0)
        return parse_amount_like(dead_contract.get("amount_text")) or 0.0
    return 0.0


def dead_contract_excluded_from_gasto(dead_contract: Dict[str, Any]) -> bool:
    return parse_bool(dead_contract.get("exclude_from_gasto"))


def dead_contract_excluded_from_cap(dead_contract: Dict[str, Any]) -> bool:
    return parse_bool(dead_contract.get("exclude_from_cap"))


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


def calculate_team_cap_summary(
    team: Dict[str, Any],
    players: List[Dict[str, Any]],
    assets: List[Dict[str, Any]],
    dead_contracts: List[Dict[str, Any]],
    settings: Dict[str, str],
    season_year: Optional[int] = None,
    luxury_repeater: bool = False,
    apron_hard_cap: Any = None,
    include_breakdowns: bool = True,
) -> Dict[str, Any]:
    # Imported lazily because trade rules also use salary-floor calculations.
    from .trade_rules import normalize_move_phase

    current_year = parse_int(season_year) or parse_int(settings.get("current_year")) or 2025
    if current_year < CAP_FORECAST_MIN_YEAR or current_year > CONTRACT_SEASON_MAX_YEAR:
        current_year = max(CAP_FORECAST_MIN_YEAR, min(CONTRACT_SEASON_MAX_YEAR, current_year))
    salary_cap = (
        parse_float(settings.get(f"salary_cap_{current_year}"))
        or parse_float(settings.get("salary_cap_2025"))
        or team["salary_cap"]
    )
    salary_floor = salary_floor_for_season(settings, current_year, salary_cap)

    player_metric_cache: Dict[tuple, float] = {}

    def player_cache_id(player: Dict[str, Any]) -> int:
        return int(player.get("id") or id(player))

    def cached_player_metric(player: Dict[str, Any], metric: str, calculator: Any) -> float:
        key = (metric, player_cache_id(player))
        if key not in player_metric_cache:
            player_metric_cache[key] = float(calculator() or 0.0)
        return player_metric_cache[key]

    def player_cap_hold(player: Dict[str, Any]) -> float:
        return cached_player_metric(
            player,
            "cap_hold",
            lambda: cap_hold_amount(player, current_year, settings, salary_cap),
        )

    def player_minimum_team_salary(player: Dict[str, Any]) -> float:
        return cached_player_metric(
            player,
            "minimum_team_salary",
            lambda: minimum_contract_team_salary(player, current_year, salary_cap),
        )

    def player_apron_yos_adjustment(player: Dict[str, Any]) -> float:
        return cached_player_metric(
            player,
            "apron_yos_adjustment",
            lambda: apron_yos_adjustment(player, current_year, salary_cap),
        )

    def player_salary_for_gasto(player: Dict[str, Any]) -> float:
        if is_exhibit10_player(player):
            return 0.0
        return player_minimum_team_salary(player)

    def player_salary_for_cap(player: Dict[str, Any]) -> float:
        hold = player_cap_hold(player)
        if hold > 0:
            return hold
        if is_two_way_player(player) or is_exhibit10_player(player):
            return 0.0
        return player_minimum_team_salary(player)

    def player_salary_for_apron(player: Dict[str, Any]) -> float:
        if player_cap_hold(player) > 0:
            return 0.0
        if is_two_way_player(player) or is_exhibit10_player(player):
            return 0.0
        return player_minimum_team_salary(player) + player_apron_yos_adjustment(player)

    # CAP Total: player team salary excluding Two-Way and Exhibit 10 contracts.
    cap_figure_players = sum(player_salary_for_cap(p) for p in players)
    # APRON Team Salary: Team Salary less cap holds, plus applicable 0-1 YOS adjustments.
    apron_figure_players = sum(player_salary_for_apron(p) for p in players)
    # GASTO Total: player payroll excluding non-financial Exhibit 10 contracts.
    player_payroll = sum(player_salary_for_gasto(p) for p in players)
    roster_counts = roster_contract_counts(players, current_year)
    roster_standard_count = roster_counts["standard"]
    roster_two_way_count = roster_counts["two_way"]

    dead_cap_team_salary = sum(
        dead_contract_salary_num(d, current_year)
        for d in dead_contracts
        if normalize_dead_type(d.get("dead_type")) in {"normal", "draft_hold"}
        and not dead_contract_excluded_from_cap(d)
    )
    dead_cap_apron = sum(
        dead_contract_salary_num(d, current_year)
        for d in dead_contracts
        if normalize_dead_type(d.get("dead_type")) == "normal"
        and not dead_contract_excluded_from_cap(d)
    )
    dead_cap_draft_hold = sum(
        dead_contract_salary_num(d, current_year)
        for d in dead_contracts
        if normalize_dead_type(d.get("dead_type")) == "draft_hold"
        and not dead_contract_excluded_from_cap(d)
    )
    dead_gasto_normal = sum(
        dead_contract_salary_num(d, current_year)
        for d in dead_contracts
        if normalize_dead_type(d.get("dead_type")) == "normal"
        and not dead_contract_excluded_from_gasto(d)
    )
    dead_gasto_two_way = sum(
        dead_contract_salary_num(d, current_year)
        for d in dead_contracts
        if normalize_dead_type(d.get("dead_type")) == "two_way"
        and not dead_contract_excluded_from_gasto(d)
    )
    open_roster_hold = open_roster_spot_cap_hold(players, current_year, settings, salary_cap)
    open_roster_hold_amount = float(open_roster_hold.get("amount") or 0.0)
    exceptions = sum((a.get("amount_num") or 0.0) for a in assets if a.get("asset_type") == "exception")

    cap_figure_before_floor = cap_figure_players + dead_cap_team_salary + open_roster_hold_amount
    cap_figure = apply_salary_floor(settings, current_year, salary_cap, cap_figure_before_floor)
    salary_floor_adjustment = max(0.0, cap_figure - cap_figure_before_floor)
    apron_figure = apron_figure_players + dead_cap_apron
    payroll = player_payroll + dead_gasto_normal + dead_gasto_two_way

    luxury = salary_cap * 1.215
    luxury_overage = max(0.0, cap_figure - luxury)
    luxury_tax = luxury_tax_amount(luxury_overage, luxury_repeater)
    first_apron = (
        parse_float(settings.get(f"first_apron_{current_year}"))
        or parse_float(settings.get("first_apron"))
        or team["first_apron"]
    )
    second_apron = (
        parse_float(settings.get(f"second_apron_{current_year}"))
        or parse_float(settings.get("second_apron"))
        or team["second_apron"]
    )
    cash_limit_total = parse_float(settings.get("cash_limit_total")) or 0.0
    cash_received = float(team.get("cash_received") or 0.0)
    cash_sent = float(team.get("cash_sent") or 0.0)

    def breakdown_amount(label: str, amount: float) -> Dict[str, Any]:
        return {"label": label, "amount": float(amount or 0.0)}

    def breakdown_text(label: str, text: str) -> Dict[str, Any]:
        return {"label": label, "text": text}

    def player_name(player: Dict[str, Any]) -> str:
        return str(player.get("name") or "Jugador sin nombre").strip() or "Jugador sin nombre"

    def dead_contract_label(dead_contract: Dict[str, Any]) -> str:
        return str(dead_contract.get("label") or "CAP muerto").strip() or "CAP muerto"

    def season_marker(player: Dict[str, Any]) -> str:
        salary_marker = str(player.get(f"salary_{current_year}_text") or "").strip().upper()
        option_marker = str(player.get(f"option_{current_year}") or "").strip().upper()
        if salary_marker in {"NB", "EB", "FB", "QO"}:
            return salary_marker
        if option_marker in {"NB", "EB", "FB", "QO", "GAP"}:
            return option_marker
        return "cap hold"

    def cap_player_detail_lines() -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        for player in players:
            hold = player_cap_hold(player)
            if hold > 0:
                lines.append(
                    breakdown_amount(
                        f"Jugador - {player_name(player)} ({season_marker(player)} hold)",
                        hold,
                    )
                )
                continue
            if is_two_way_player(player) or is_exhibit10_player(player):
                continue
            salary = player_minimum_team_salary(player)
            if salary > 0:
                lines.append(breakdown_amount(f"Jugador - {player_name(player)}", salary))
        return lines

    def payroll_player_detail_lines() -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        for player in players:
            if is_exhibit10_player(player):
                continue
            salary = player_minimum_team_salary(player)
            if salary > 0:
                label = f"Jugador - {player_name(player)}"
                if is_two_way_player(player):
                    label = f"{label} (Two-Way)"
                lines.append(breakdown_amount(label, salary))
        return lines

    def apron_player_detail_lines() -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        for player in players:
            hold = player_cap_hold(player)
            if hold > 0:
                lines.append(
                    breakdown_text(
                        f"Excluido - {player_name(player)}",
                        f"{season_marker(player)} hold no cuenta para apron",
                    )
                )
                continue
            if is_two_way_player(player) or is_exhibit10_player(player):
                continue
            salary = player_minimum_team_salary(player)
            if salary > 0:
                lines.append(breakdown_amount(f"Jugador - {player_name(player)}", salary))
            yos_adjustment = player_apron_yos_adjustment(player)
            if yos_adjustment > 0:
                lines.append(breakdown_amount(f"Ajuste 0-1 YOS - {player_name(player)}", yos_adjustment))
        return lines

    def dead_contract_detail_lines(*, cap_types: set[str], exclude_field: str) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        for dead_contract in dead_contracts:
            dead_type = normalize_dead_type(dead_contract.get("dead_type"))
            if dead_type not in cap_types:
                continue
            if exclude_field == "cap" and dead_contract_excluded_from_cap(dead_contract):
                lines.append(breakdown_text(f"Excluido CAP - {dead_contract_label(dead_contract)}", "Marcado como excluido de CAP"))
                continue
            if exclude_field == "gasto" and dead_contract_excluded_from_gasto(dead_contract):
                lines.append(breakdown_text(f"Excluido gasto - {dead_contract_label(dead_contract)}", "Marcado como excluido de gasto"))
                continue
            amount = dead_contract_salary_num(dead_contract, current_year)
            if amount > 0:
                lines.append(breakdown_amount(f"CAP muerto - {dead_contract_label(dead_contract)}", amount))
        return lines

    def luxury_tax_detail_lines(overage: float, repeater: bool) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        remaining = max(0.0, float(overage or 0.0))
        if not math.isfinite(remaining):
            return lines
        if remaining <= 0:
            return lines
        tier_size = 5_000_000.0
        rates = [2.5, 2.75, 3.5, 4.25] if repeater else [1.5, 1.75, 2.5, 3.25]
        tier_index = 0
        lower_bound = 0.0
        max_detail_tiers = 20
        while remaining > 0 and tier_index < max_detail_tiers:
            taxable = min(tier_size, remaining)
            if tier_index < len(rates):
                rate = rates[tier_index]
            else:
                rate = rates[-1] + ((tier_index - len(rates) + 1) * 0.5)
            upper_bound = lower_bound + taxable
            lines.append(
                breakdown_amount(
                    f"Tramo luxury {int(lower_bound / 1_000_000)}-{int(math.ceil(upper_bound / 1_000_000))}M x{rate:g}",
                    taxable * rate,
                )
            )
            remaining -= taxable
            lower_bound += taxable
            tier_index += 1
        if remaining > 0:
            lines.append(
                breakdown_amount(
                    f"Resto luxury desde {int(lower_bound / 1_000_000)}M",
                    luxury_tax_amount(remaining, repeater),
                )
            )
        return lines

    balance_breakdowns: Dict[str, List[Dict[str, Any]]] = {}
    if include_breakdowns:
        cap_player_lines = cap_player_detail_lines()
        payroll_player_lines = payroll_player_detail_lines()
        apron_player_lines = apron_player_detail_lines()
        dead_cap_team_salary_lines = dead_contract_detail_lines(cap_types={"normal", "draft_hold"}, exclude_field="cap")
        dead_cap_apron_lines = dead_contract_detail_lines(cap_types={"normal"}, exclude_field="cap")
        dead_gasto_normal_lines = dead_contract_detail_lines(cap_types={"normal"}, exclude_field="gasto")
        dead_gasto_two_way_lines = dead_contract_detail_lines(cap_types={"two_way"}, exclude_field="gasto")
        open_roster_lines = (
            [
                breakdown_amount(
                    f"{int(open_roster_hold.get('open_spots') or 0)} plazas x minimo rookie",
                    open_roster_hold_amount,
                )
            ]
            if open_roster_hold_amount > 0
            else []
        )
        salary_floor_lines = (
            [breakdown_amount("Ajuste para llegar al Salary Floor", salary_floor_adjustment)]
            if salary_floor_adjustment > 0
            else []
        )

        balance_breakdowns = {
            "cap_total": [
                breakdown_amount("Jugadores y cap holds computables", cap_figure_players),
                *cap_player_lines,
                breakdown_amount("CAP muerto y rookie scale holds", dead_cap_team_salary),
                *dead_cap_team_salary_lines,
                breakdown_amount("Open roster spot cap holds", open_roster_hold_amount),
                *open_roster_lines,
                breakdown_amount("Ajuste Salary Floor", salary_floor_adjustment),
                *salary_floor_lines,
            ],
            "gasto_total": [
                breakdown_amount("Salarios de jugadores", player_payroll),
                *payroll_player_lines,
                breakdown_amount("CAP muerto", dead_gasto_normal),
                *dead_gasto_normal_lines,
                breakdown_amount("CAP muerto Two-Way", dead_gasto_two_way),
                *dead_gasto_two_way_lines,
            ],
            "apron_account": [
                breakdown_amount("Jugadores sin cap holds", apron_figure_players),
                *apron_player_lines,
                breakdown_amount("CAP muerto computable", dead_cap_apron),
                *dead_cap_apron_lines,
            ],
            "luxury_tax": [
                breakdown_amount("CAP TOTAL", cap_figure),
                breakdown_amount("Luxury cap", luxury),
                breakdown_amount("Exceso sobre luxury", luxury_overage),
                breakdown_text("Tipo de luxury", "Reincidente" if luxury_repeater else "No reincidente"),
                breakdown_amount("Luxury tax calculada", luxury_tax),
                *luxury_tax_detail_lines(luxury_overage, luxury_repeater),
            ],
        }

    return {
        "player_payroll": player_payroll,
        "dead_cap": dead_gasto_normal + dead_gasto_two_way,
        "dead_cap_normal": dead_cap_apron,
        "dead_cap_draft_hold": dead_cap_draft_hold,
        "dead_cap_team_salary": dead_cap_team_salary,
        "dead_cap_two_way": dead_gasto_two_way,
        "dead_gasto_normal": dead_gasto_normal,
        "dead_gasto_two_way": dead_gasto_two_way,
        "open_roster_spot_cap_hold": open_roster_hold_amount,
        "open_roster_spot_count": int(open_roster_hold.get("open_spots") or 0),
        "open_roster_spot_roster_count": int(open_roster_hold.get("roster_count") or 0),
        "open_roster_spot_minimum_salary": float(open_roster_hold.get("minimum_salary") or 0.0),
        "exceptions_total": exceptions,
        "salary_floor": salary_floor,
        "cap_figure_before_floor": cap_figure_before_floor,
        "salary_floor_adjustment": salary_floor_adjustment,
        "cap_figure": cap_figure,
        "apron_account": apron_figure,
        "payroll": payroll,
        "salary_cap_2025": salary_cap,
        "salary_cap": salary_cap,
        "first_apron": first_apron,
        "second_apron": second_apron,
        "current_year": current_year,
        "room_to_cap": salary_cap - cap_figure,
        "room_to_luxury": luxury - cap_figure,
        "room_to_first_apron": first_apron - apron_figure,
        "room_to_second_apron": second_apron - apron_figure,
        "luxury_tax": luxury_tax,
        "balance_breakdowns": balance_breakdowns,
        "cash_received": cash_received,
        "cash_sent": cash_sent,
        "cash_limit_total": cash_limit_total,
        "trade_move_phase": normalize_move_phase(settings.get("trade_move_phase")),
        "trade_move_limit_pre30": max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0),
        "trade_move_limit_post30": max(0, parse_int(settings.get("trade_move_limit_post30")) or 0),
        "roster_standard_count": roster_standard_count,
        "roster_two_way_count": roster_two_way_count,
        "apron_hard_cap": normalize_apron_hard_cap(apron_hard_cap) or "",
    }
