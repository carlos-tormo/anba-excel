"""Pure trade-machine constants and value normalization."""

from __future__ import annotations

from typing import Any

from ._values import parse_float

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
