"""Pure normalization helpers for league entities and values."""

from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any, Dict, Optional

from ._values import parse_amount_like, parse_bool, parse_float

FREE_AGENT_TYPE_UNRESTRICTED = "No restringido"
FREE_AGENT_TYPE_RESTRICTED = "Restringido"

def normalize_player_happiness(value: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return 0
    parsed = parse_float(raw)
    if parsed is None or not math.isfinite(parsed) or parsed < -10 or parsed > 10:
        raise ValueError("invalid_happiness")
    return int(parsed) if float(parsed).is_integer() else parsed
def normalize_dead_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"two_way", "tw"}:
        return "two_way"
    if raw in {"draft_hold", "draft_cap_hold", "rookie_hold"}:
        return "draft_hold"
    return "normal"


def normalize_free_agent_type(value: Any) -> str:
    raw = str(value or "").strip()
    normalized = (
        raw.lower()
        .replace("-", " ")
        .replace("_", " ")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in {"restringido", "restricted", "rfa"}:
        return FREE_AGENT_TYPE_RESTRICTED
    if normalized in {"no restringido", "unrestricted", "ufa"}:
        return FREE_AGENT_TYPE_UNRESTRICTED
    return FREE_AGENT_TYPE_UNRESTRICTED


PLAYER_PROFILE_STATUS_ACTIVE = "active"
PLAYER_PROFILE_STATUS_OUTSIDE_NBA = "outside_nba"
PLAYER_PROFILE_STATUS_RETIRED = "retired"
PLAYER_PROFILE_STATUSES = {
    PLAYER_PROFILE_STATUS_ACTIVE,
    PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
    PLAYER_PROFILE_STATUS_RETIRED,
}
PLAYER_PROFILE_STATUS_LABELS = {
    PLAYER_PROFILE_STATUS_ACTIVE: "Activo",
    PLAYER_PROFILE_STATUS_OUTSIDE_NBA: "Fuera de la NBA",
    PLAYER_PROFILE_STATUS_RETIRED: "Retirado",
}
UNAVAILABLE_PLAYER_PROFILE_STATUSES = {
    PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
    PLAYER_PROFILE_STATUS_RETIRED,
}


def normalize_player_profile_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"fuera_nba", "fuera_de_nba", "fuera_de_la_nba", "outside", "outside_nba", "out_of_nba"}:
        return PLAYER_PROFILE_STATUS_OUTSIDE_NBA
    if raw in {"retirado", "retired"}:
        return PLAYER_PROFILE_STATUS_RETIRED
    return PLAYER_PROFILE_STATUS_ACTIVE


def player_profile_status_label(value: Any) -> str:
    return PLAYER_PROFILE_STATUS_LABELS.get(normalize_player_profile_status(value), "Activo")


def is_unavailable_player_profile_status(value: Any) -> bool:
    return normalize_player_profile_status(value) in UNAVAILABLE_PLAYER_PROFILE_STATUSES


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


def normalize_pick_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"acquired", "sold", "conditional"}:
        return raw
    return "own"


def normalize_pick_round(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if "2" in raw:
        return "2nd"
    return "1st"
def normalize_exception_type(value: Any) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if "tax" in raw:
        return "TAXPAYER Mid"
    if "room" in raw:
        return "ROOM Mid"
    if "bia" in raw:
        return "Bianual"
    if "traspas" in raw or "trade" in raw:
        return "Excepción de traspaso"
    if "mid" in raw:
        return "Mid-Level"
    return str(value).strip() or None


def parse_salary_amount(value: Any) -> Optional[float]:
    return parse_amount_like(value)


def format_salary_amount_text(value: Any) -> Optional[str]:
    amount = parse_salary_amount(value)
    if amount is None:
        return None
    return f"{int(round(amount)):,}".replace(",", ".")


def normalize_gm_start_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_hex_color(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"#[0-9a-fA-F]{6}", raw):
        return raw.upper()
    return None

