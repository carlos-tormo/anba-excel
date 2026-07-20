"""Pure trade-machine constants and value normalization."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._values import parse_float, parse_int, settings_int
from .cap import salary_floor_for_season
from .contracts import (
    ROSTER_STANDARD_MAX_DEFAULT,
    ROSTER_STANDARD_MIN_DEFAULT,
    ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT,
    ROSTER_TWO_WAY_MAX_DEFAULT,
    ROSTER_TWO_WAY_MIN_DEFAULT,
)
from .exceptions import normalize_apron_hard_cap

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


def normalize_move_phase(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "").replace("-", "")
    return "post30" if raw in {"post30", "post"} else "pre30"


def normalize_trade_bucket(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "").replace("-", "")
    return "post30" if raw in {"post30", "post"} else "pre30"


def format_trade_money(value: Any) -> str:
    amount = parse_float(value) or 0.0
    sign = "-" if amount < 0 else ""
    whole = int(round(abs(amount)))
    return f"${sign}{whole:,}".replace(",", ".")


def trade_move_availability(move_summary: Dict[str, Any], bucket: str) -> Dict[str, Any]:
    bucket_key = normalize_trade_bucket(bucket)
    pre_available = max(0, parse_int(move_summary.get("remaining_pre30")) or 0)
    post_available = max(0, parse_int(move_summary.get("remaining_post30")) or 0)
    if bucket_key == "post30":
        return {
            "bucket": bucket_key,
            "remaining": pre_available + post_available,
            "pre_remaining": pre_available,
            "post_remaining": post_available,
            "label": "pre-30/post-30",
        }
    return {
        "bucket": bucket_key,
        "remaining": pre_available,
        "pre_remaining": pre_available,
        "post_remaining": post_available,
        "label": "pre-30",
    }


def trade_season(
    payload: Dict[str, Any],
    settings: Dict[str, str],
    *,
    contract_min_year: int,
    contract_max_year: int,
    contract_max_start_year: int,
) -> int:
    current_year = parse_int(settings.get("current_year")) or 2025
    if current_year < contract_min_year or current_year > contract_max_start_year:
        current_year = 2025
    season = parse_int(payload.get("season") or payload.get("season_start") or payload.get("seasonStart"))
    if season is None:
        season = current_year
    return min(contract_max_year, max(contract_min_year, season))


def trade_thresholds(settings: Dict[str, str], season: int) -> Dict[str, float]:
    salary_cap = (
        parse_float(settings.get(f"salary_cap_{season}"))
        or parse_float(settings.get("salary_cap_2025"))
        or 154_647_000.0
    )
    first_apron = (
        parse_float(settings.get(f"first_apron_{season}"))
        or parse_float(settings.get("first_apron"))
        or 195_945_000.0
    )
    second_apron = (
        parse_float(settings.get(f"second_apron_{season}"))
        or parse_float(settings.get("second_apron"))
        or 207_824_000.0
    )
    return {
        "salaryCap": salary_cap,
        "salaryFloor": salary_floor_for_season(settings, season, salary_cap),
        "luxuryCap": salary_cap * 1.215,
        "firstApron": first_apron,
        "secondApron": second_apron,
    }


def trade_roster_limits(settings: Dict[str, str]) -> Dict[str, int]:
    standard_min = settings_int(settings, "roster_standard_min", ROSTER_STANDARD_MIN_DEFAULT)
    standard_max = max(
        standard_min,
        settings_int(settings, "roster_standard_max", ROSTER_STANDARD_MAX_DEFAULT),
    )
    offseason_max = max(
        standard_max,
        settings_int(settings, "roster_standard_offseason_max", ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT),
    )
    two_way_min = settings_int(settings, "roster_two_way_min", ROSTER_TWO_WAY_MIN_DEFAULT)
    two_way_max = max(
        two_way_min,
        settings_int(settings, "roster_two_way_max", ROSTER_TWO_WAY_MAX_DEFAULT),
    )
    return {
        "standardMin": max(0, standard_min),
        "standardMax": max(0, standard_max),
        "standardOffseasonMax": max(0, offseason_max),
        "twoWayMin": max(0, two_way_min),
        "twoWayMax": max(0, two_way_max),
    }


def trade_balance_snapshot(
    thresholds: Dict[str, float],
    cap_figure: float,
    apron_figure: Optional[float] = None,
) -> List[Dict[str, Any]]:
    apron = cap_figure if apron_figure is None else apron_figure
    return [
        {"key": "cap", "label": "CAP", "value": thresholds["salaryCap"] - cap_figure},
        {"key": "tax", "label": "Impuesto lujo", "value": thresholds["luxuryCap"] - cap_figure},
        {"key": "first_apron", "label": "1er apron", "value": thresholds["firstApron"] - apron},
        {"key": "second_apron", "label": "2do apron", "value": thresholds["secondApron"] - apron},
    ]


def hard_cap_for_season(team_data: Dict[str, Any], season: int) -> str:
    season_key = str(int(season))
    summaries = team_data.get("season_summaries") or {}
    if isinstance(summaries, dict):
        hard_cap = normalize_apron_hard_cap((summaries.get(season_key) or {}).get("apron_hard_cap"))
        if hard_cap:
            return hard_cap
    for row in team_data.get("apron_hard_caps") or []:
        if parse_int(row.get("season_year")) == int(season):
            return normalize_apron_hard_cap(row.get("hard_cap")) or ""
    summary = team_data.get("summary") or {}
    if parse_int(summary.get("current_year")) == int(season):
        return normalize_apron_hard_cap(summary.get("apron_hard_cap")) or ""
    return ""


def expanded_trade_buffer(salary_cap: float) -> float:
    calculated = round(float(salary_cap or 0.0) * TRADE_MATCH_EXPANDED_BUFFER_RATIO)
    return float(calculated if calculated > 0 else TRADE_MATCH_EXPANDED_BUFFER_FALLBACK)


def expanded_tpe_limit(outgoing_salary: float, salary_cap: float) -> float:
    outgoing = float(outgoing_salary or 0.0)
    if outgoing < TRADE_MATCH_LOW_BAND:
        return outgoing * 2 + TRADE_MATCH_CUSHION
    if outgoing <= TRADE_MATCH_HIGH_BAND:
        return outgoing + expanded_trade_buffer(salary_cap)
    return outgoing * 1.25


def first_apron_limited(flow: Dict[str, Any], thresholds: Dict[str, float]) -> bool:
    first_apron = float(thresholds.get("firstApron") or 0.0)
    before = float(flow.get("beforeApronAccount") or flow.get("beforeCap") or 0.0)
    post = float(flow.get("postApronAccount") or flow.get("postCap") or 0.0)
    return first_apron > 0 and (before >= first_apron or post >= first_apron)


def second_apron_limited(flow: Dict[str, Any], thresholds: Dict[str, float]) -> bool:
    second_apron = float(thresholds.get("secondApron") or 0.0)
    before = float(flow.get("beforeApronAccount") or flow.get("beforeCap") or 0.0)
    post = float(flow.get("postApronAccount") or flow.get("postCap") or 0.0)
    return second_apron > 0 and (before >= second_apron or post >= second_apron)


def salary_match_profile(flow: Dict[str, Any], thresholds: Dict[str, float]) -> Dict[str, Any]:
    raw_incoming_matching = flow.get("incomingMatchingSalary")
    raw_outgoing_matching = flow.get("outgoingMatchingSalary")
    incoming = float(
        raw_incoming_matching
        if raw_incoming_matching is not None
        else flow.get("incomingSalary") or 0.0
    )
    outgoing = float(
        raw_outgoing_matching
        if raw_outgoing_matching is not None
        else flow.get("outgoingSalary") or 0.0
    )
    actual_incoming = float(flow.get("incomingSalary") or 0.0)
    before_cap = float(flow.get("beforeCap") or 0.0)
    post_cap = float(flow.get("postCap") or 0.0)
    outgoing_players = sum(
        1 for asset in flow.get("outgoingAssets") or [] if asset.get("type") == "player"
    )
    incoming_players = sum(
        1 for asset in flow.get("incomingAssets") or [] if asset.get("type") == "player"
    )
    first_limited = first_apron_limited(flow, thresholds)
    second_limited = second_apron_limited(flow, thresholds)
    aggregation_trigger = "second" if outgoing_players > 1 and incoming_players > 0 else ""
    standard_limit = (
        outgoing + TRADE_MATCH_CUSHION
        if outgoing_players > 0 and incoming_players > 0
        else 0.0
    )
    minimum_excluded = max(0.0, actual_incoming - incoming)
    minimum_note = (
        f" {format_trade_money(minimum_excluded)} en mínimos recibidos no computan para el cuadre salarial."
        if minimum_excluded > 0
        else ""
    )
    if incoming <= 0 or incoming <= outgoing:
        return {
            "legal": True,
            "tpe": "none",
            "label": "Sin TPE",
            "limit": outgoing,
            "hardCapTrigger": aggregation_trigger,
            "message": "No recibe salario computable de jugadores."
            if incoming <= 0
            else f"Recibe {format_trade_money(incoming)} computable y envía {format_trade_money(outgoing)}; no necesita recibir más salario del que envía.{minimum_note}",
        }
    if second_limited:
        return {
            "legal": False,
            "tpe": "second_apron_block",
            "label": "Restricción 2do apron",
            "limit": outgoing,
            "message": f"Está limitado por el 2do apron: no puede recibir más salario computable del que envía ({format_trade_money(outgoing)}). Recibe {format_trade_money(incoming)} computable.{minimum_note}",
        }
    if first_limited:
        label = "TPE agregada" if outgoing_players > 1 else "TPE estándar"
        return {
            "legal": outgoing_players > 0 and incoming_players > 0 and incoming <= standard_limit,
            "tpe": "aggregated" if outgoing_players > 1 else "standard",
            "label": label,
            "limit": standard_limit,
            "hardCapTrigger": aggregation_trigger,
            "message": (
                f"Necesita enviar al menos un jugador para usar {label}."
                if outgoing_players <= 0
                else f"Necesita recibir al menos un jugador para usar {label}."
                if incoming_players <= 0
                else f"{label}: puede recibir hasta {format_trade_money(standard_limit)} computable (100% del salario enviado + $250k).{minimum_note}"
                if incoming <= standard_limit
                else f"{label}: puede recibir hasta {format_trade_money(standard_limit)} computable (100% del salario enviado + $250k), pero recibe {format_trade_money(incoming)} computable.{minimum_note}"
            ),
        }

    salary_cap = thresholds["salaryCap"]
    room_limit = outgoing + max(0.0, salary_cap + TRADE_ROOM_TPE_BUFFER - before_cap)
    cap_space_legal = before_cap < salary_cap and incoming_players > 0 and post_cap <= salary_cap
    room_legal = (
        before_cap < salary_cap
        and outgoing_players > 0
        and incoming_players > 0
        and post_cap <= salary_cap + TRADE_ROOM_TPE_BUFFER
    )
    expanded_limit = expanded_tpe_limit(outgoing, salary_cap) if outgoing_players > 0 else 0.0
    expanded_legal = outgoing_players > 0 and incoming_players > 0 and incoming <= expanded_limit
    if cap_space_legal:
        return {
            "legal": True,
            "tpe": "cap_room",
            "label": "Espacio salarial",
            "limit": room_limit,
            "message": f"Absorbe el salario con espacio salarial; límite {format_trade_money(room_limit)} antes de usar el buffer Room TPE.",
        }
    if standard_limit > 0 and incoming <= standard_limit:
        label = "TPE agregada" if outgoing_players > 1 else "TPE estándar"
        return {
            "legal": True,
            "tpe": "aggregated" if outgoing_players > 1 else "standard",
            "label": label,
            "limit": standard_limit,
            "hardCapTrigger": aggregation_trigger,
            "message": f"{label}: puede recibir hasta {format_trade_money(standard_limit)} (100% del salario enviado + $250k).",
        }
    if expanded_legal:
        return {
            "legal": True,
            "tpe": "expanded",
            "label": "TPE expandida",
            "limit": expanded_limit,
            "hardCapTrigger": "first",
            "message": f"TPE expandida: puede recibir hasta {format_trade_money(expanded_limit)} según el salario enviado.",
        }
    if room_legal:
        return {
            "legal": True,
            "tpe": "room",
            "label": "Room TPE",
            "limit": room_limit,
            "message": f"Room TPE: queda hasta $250k por encima del salary cap; límite {format_trade_money(room_limit)} de salario computable recibido.{minimum_note}",
        }
    best_limit = max(expanded_limit, room_limit if before_cap < salary_cap else 0.0)
    reason = (
        "no envía ningún jugador para crear una TPE"
        if outgoing_players <= 0
        else "no recibe ningún jugador"
        if incoming_players <= 0
        else "supera los límites de TPE disponibles"
    )
    return {
        "legal": False,
        "tpe": "none",
        "label": "Sin TPE válida",
        "limit": best_limit,
        "message": f"No hay TPE válida: {reason}. Puede recibir hasta {format_trade_money(best_limit)} computable, pero recibe {format_trade_money(incoming)} computable.{minimum_note}",
    }


def trade_issue_messages(issues: List[Dict[str, Any]], rule: str) -> List[str]:
    messages: List[str] = []
    for issue in issues:
        if issue.get("rule") != rule:
            continue
        prefix = f"{issue.get('teamCode')}: " if issue.get("teamCode") else ""
        messages.append(f"{prefix}{issue.get('message')}")
    return messages


def trade_rule_checklist(
    issues: List[Dict[str, Any]],
    selected_count: int,
    salary_pass_messages: List[str],
) -> List[Dict[str, Any]]:
    def has(rule: str, severity: Optional[str] = None) -> bool:
        return any(
            issue.get("rule") == rule
            and (severity is None or issue.get("severity") == severity)
            for issue in issues
        )

    def messages(rule: str, fallback: List[str]) -> List[str]:
        return trade_issue_messages(issues, rule) or fallback

    definitions = [
        ("cash", "Cash disponible", "El cash incluido queda dentro de los límites disponibles."),
        ("multi_team", "Traspaso multi-equipo", "Si hay más de dos equipos, todos envían y reciben algo."),
        ("hard_cap", "Límite duro", "No se detecta conflicto de límite duro en el 1er/2do apron."),
        ("hard_cap_trigger", "Hard cap generado", "El traspaso no genera un nuevo hard cap de apron para los equipos seleccionados."),
        ("second_apron_aggregation", "Agregación 2do apron", "No se detecta agregación salarial prohibida para equipos en 2do apron."),
        ("minimum_stacking", "Stacking mínimos", "No se detecta combinación de 3+ jugadores con múltiples contratos mínimos enviados por menos jugadores recibidos."),
        ("restricted_pick", "Ronda restringida", "No hay ninguna ronda restringida seleccionada."),
        ("frozen_pick", "Ronda congelada", "No hay ninguna ronda congelada seleccionada."),
        ("manual_review", "Revisión manual ANBA", "No se activa revisión por protecciones, condiciones, Stepien, Ley Randle, BYC/S&T ni restricciones de aprons no modeladas."),
        ("roster_count", "Tamaño de plantilla", "El tamaño de plantilla queda dentro de los límites configurados."),
    ]
    checklist = [
        {
            "key": "salary",
            "label": "Cuadre salarial básico",
            "status": "pending" if not selected_count else "fail" if has("salary") else "pass",
            "messages": ["Añade activos para evaluar el cuadre salarial."]
            if not selected_count
            else messages("salary", salary_pass_messages),
        },
        {
            "key": "moves",
            "label": "Movimientos disponibles",
            "status": "pending" if not selected_count else "fail" if has("moves", "illegal") else "warning" if has("moves", "warning") else "pass",
            "messages": ["Añade activos para evaluar los movimientos disponibles."]
            if not selected_count
            else messages("moves", ["Todos los equipos tienen movimientos suficientes para los activos que envían."]),
        },
    ]
    for key, label, fallback in definitions:
        if key in {"cash", "moves", "minimum_stacking", "roster_count"}:
            status = "fail" if has(key, "illegal") else "warning" if has(key, "warning") else "pass"
        elif key in {"hard_cap_trigger", "manual_review"}:
            status = "warning" if has(key) else "pass"
        else:
            status = "fail" if has(key) else "pass"
        checklist.append({"key": key, "label": label, "status": status, "messages": messages(key, [fallback])})
    return checklist


def hard_cap_issues(
    team_code: str,
    hard_cap: str,
    flow: Dict[str, Any],
    thresholds: Dict[str, float],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if hard_cap == "first" and thresholds["firstApron"] > 0 and flow["postApronAccount"] > thresholds["firstApron"]:
        issues.append({"severity": "illegal", "rule": "hard_cap", "teamCode": team_code, "message": "Tiene límite duro en el 1er apron y acabaría por encima."})
    if hard_cap == "second" and thresholds["secondApron"] > 0 and flow["postApronAccount"] > thresholds["secondApron"]:
        issues.append({"severity": "illegal", "rule": "hard_cap", "teamCode": team_code, "message": "Tiene límite duro en el 2do apron y acabaría por encima."})
    return issues


def apron_restriction_issues(
    team_code: str,
    flow: Dict[str, Any],
    thresholds: Dict[str, float],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    outgoing_players = [asset for asset in flow.get("outgoingAssets") or [] if asset.get("type") == "player"]
    if second_apron_limited(flow, thresholds) and len(outgoing_players) > 1 and float(flow.get("incomingSalary") or 0.0) > 0:
        issues.append({"severity": "illegal", "rule": "second_apron_aggregation", "teamCode": team_code, "message": f"Equipo en 2do apron: no puede agregar salarios de varios jugadores ({len(outgoing_players)}) para recibir salario."})
    if first_apron_limited(flow, thresholds):
        issues.append({"severity": "warning", "rule": "manual_review", "teamCode": team_code, "message": "Equipo limitado por 1er apron: revisar manualmente TPE de temporada anterior, excepciones y jugadores cortados con salario previo > MID si aplican."})
    if second_apron_limited(flow, thresholds):
        issues.append({"severity": "warning", "rule": "manual_review", "teamCode": team_code, "message": "Equipo limitado por 2do apron: revisar manualmente que no haya cash, TPMID ni TPE creada mediante S&T."})
    return issues


def minimum_stacking_issue(team_code: str, flow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    outgoing = [asset for asset in flow.get("outgoingAssets") or [] if asset.get("type") == "player"]
    incoming = [asset for asset in flow.get("incomingAssets") or [] if asset.get("type") == "player"]
    minimums = [asset for asset in outgoing if asset.get("isMinimumContract")]
    if len(outgoing) < 3 or len(incoming) >= len(outgoing) or len(minimums) <= 1:
        return None
    return {"severity": "warning", "rule": "minimum_stacking", "teamCode": team_code, "message": f"Envía {len(outgoing)} jugadores, {len(minimums)} mínimos, y recibe menos jugadores. Puede ser ilegal fuera del periodo 15-Dic/deadline; falta configurar fecha de trade para convertirlo en bloqueo automático."}


def roster_count_issues(
    team_code: str,
    flow: Dict[str, Any],
    limits: Dict[str, int],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    standard = int(flow.get("postRosterStandard") or 0)
    two_way = int(flow.get("postRosterTwoWay") or 0)
    if standard > limits["standardOffseasonMax"]:
        issues.append({"severity": "illegal", "rule": "roster_count", "teamCode": team_code, "message": f"Quedaría con {standard} contratos estándar; el máximo configurado para offseason es {limits['standardOffseasonMax']}."})
    elif standard > limits["standardMax"]:
        issues.append({"severity": "warning", "rule": "roster_count", "teamCode": team_code, "message": f"Quedaría con {standard} contratos estándar. Solo sería válido en offseason; durante la temporada el máximo es {limits['standardMax']}."})
    if standard < limits["standardMin"]:
        issues.append({"severity": "warning", "rule": "roster_count", "teamCode": team_code, "message": f"Quedaría con {standard} contratos estándar, por debajo del mínimo configurado ({limits['standardMin']})."})
    if two_way > limits["twoWayMax"]:
        issues.append({"severity": "illegal", "rule": "roster_count", "teamCode": team_code, "message": f"Quedaría con {two_way} contratos two-way; el máximo configurado es {limits['twoWayMax']}."})
    if two_way < limits["twoWayMin"]:
        issues.append({"severity": "warning", "rule": "roster_count", "teamCode": team_code, "message": f"Quedaría con {two_way} contratos two-way, por debajo del mínimo configurado ({limits['twoWayMin']})."})
    return issues
