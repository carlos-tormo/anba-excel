"""Shared value normalization used by pure domain rules."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional


def parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_amount_like(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
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


def season_label(start_year: Any) -> str:
    year = parse_int(str(start_year)) or 2025
    return f"{year}-{(year + 1) % 100:02d}"


def settings_int(settings: Dict[str, str], key: str, default: int) -> int:
    parsed = parse_int(settings.get(key))
    if parsed is None or parsed < 0:
        return default
    return parsed
