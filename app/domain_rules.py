"""Compatibility façade for the extracted pure domain modules.

New code should import from ``app.domain.cap``, ``contracts``, ``trade_rules``,
or ``exceptions``. Existing imports remain supported during the refactor.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

try:
    from .domain._values import (
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
        season_label,
        settings_int,
    )
    from .domain.cap import *  # noqa: F403 - intentional compatibility export.
    from .domain.contracts import *  # noqa: F403 - intentional compatibility export.
    from .domain.exceptions import *  # noqa: F403 - intentional compatibility export.
    from .domain.trade_rules import *  # noqa: F403 - intentional compatibility export.
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain._values import (
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
        season_label,
        settings_int,
    )
    from domain.cap import *  # type: ignore  # noqa: F403
    from domain.contracts import *  # type: ignore  # noqa: F403
    from domain.exceptions import *  # type: ignore  # noqa: F403
    from domain.trade_rules import *  # type: ignore  # noqa: F403


def parse_free_agent_rep_discord_ids(raw_value: Any) -> Dict[str, str]:
    if isinstance(raw_value, dict):
        items = raw_value.items()
    else:
        text = str(raw_value or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            items = parsed.items()
        else:
            pairs = []
            for line in text.splitlines():
                value = str(line or "").strip()
                if not value:
                    continue
                for delimiter in ["=", "|", ":"]:
                    if delimiter in value:
                        name, discord_id = value.split(delimiter, 1)
                        pairs.append((name, discord_id))
                        break
            items = pairs

    mapping: Dict[str, str] = {}
    seen: set[str] = set()
    for name, discord_id in items:
        clean_name = re.sub(r"\s+", " ", str(name or "").strip())
        clean_id = re.sub(r"\D+", "", str(discord_id or "").strip())
        if not clean_name or not re.fullmatch(r"\d{5,25}", clean_id):
            continue
        key = clean_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        mapping[clean_name] = clean_id
    return mapping


def public_settings_payload(settings: Dict[str, str]) -> Dict[str, Any]:
    current_year = parse_int(settings.get("current_year")) or 2025
    if current_year < CAP_FORECAST_MIN_YEAR or current_year > CONTRACT_SEASON_MAX_START_YEAR:  # noqa: F405
        current_year = 2025
    salary_cap = parse_float(settings.get("salary_cap_2025")) or 154647000.0
    salary_floor = salary_floor_for_season(settings, current_year, salary_cap)  # noqa: F405
    first_apron = parse_float(settings.get("first_apron")) or 195945000.0
    second_apron = parse_float(settings.get("second_apron")) or 207824000.0
    raw_free_agent_reps = str(settings.get("free_agent_reps") or "").strip()
    free_agent_reps: List[str] = []
    if raw_free_agent_reps:
        try:
            parsed_reps = json.loads(raw_free_agent_reps)
            if isinstance(parsed_reps, list):
                free_agent_reps = [str(item).strip() for item in parsed_reps if str(item).strip()]
        except (TypeError, ValueError):
            free_agent_reps = [
                item.strip() for item in raw_free_agent_reps.splitlines() if item.strip()
            ]

    payload = {
        "salary_cap_2025": salary_cap,
        "salary_floor_2025": parse_float(settings.get("salary_floor_2025")) or salary_cap * 0.9,
        "current_year": current_year,
        "current_year_version": parse_int(settings.get("current_year_version")) or 1,
        "first_apron": first_apron,
        "second_apron": second_apron,
        "cash_limit_total": parse_float(settings.get("cash_limit_total")) or 0.0,
        "trade_move_limit_pre30": max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0),
        "trade_move_limit_post30": max(0, parse_int(settings.get("trade_move_limit_post30")) or 0),
        "trade_move_phase": normalize_move_phase(settings.get("trade_move_phase")),  # noqa: F405
        "free_agency_mode": parse_bool(settings.get("free_agency_mode")),
        "discord_free_agent_offer_role_ping_enabled": parse_bool(
            settings.get("discord_free_agent_offer_role_ping_enabled", "1")
        ),
        "roster_standard_min": settings_int(settings, "roster_standard_min", ROSTER_STANDARD_MIN_DEFAULT),  # noqa: F405
        "roster_standard_max": settings_int(settings, "roster_standard_max", ROSTER_STANDARD_MAX_DEFAULT),  # noqa: F405
        "roster_standard_offseason_max": settings_int(
            settings, "roster_standard_offseason_max", ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT  # noqa: F405
        ),
        "roster_two_way_min": settings_int(settings, "roster_two_way_min", ROSTER_TWO_WAY_MIN_DEFAULT),  # noqa: F405
        "roster_two_way_max": settings_int(settings, "roster_two_way_max", ROSTER_TWO_WAY_MAX_DEFAULT),  # noqa: F405
        "luxury_cap": salary_cap * 1.215,
        "minimum_cap_allowed": salary_floor,
        "free_agent_reps": free_agent_reps,
        "free_agent_rep_discord_ids": parse_free_agent_rep_discord_ids(
            settings.get("free_agent_rep_discord_ids")
        ),
    }
    for season in range(current_year, current_year + CAP_FORECAST_WINDOW):  # noqa: F405
        season_cap = parse_float(settings.get(f"salary_cap_{season}")) or salary_cap
        season_salary_floor = salary_floor_for_season(settings, season, season_cap)  # noqa: F405
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
        for pick_number in range(1, 31):
            key = f"rookie_scale_{season}_{pick_number}"
            payload[key] = parse_float(settings.get(key)) or 0.0
    return payload
