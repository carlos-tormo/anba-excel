"""Pure offseason-exception definitions and amount rules."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._values import parse_float

OFFSEASON_EXCEPTION_TAXPAYER_MLE_BASE_AMOUNT = 6_064_000.0
OFFSEASON_EXCEPTION_TAXPAYER_MLE_BASE_CAP = 165_000_000.0
OFFSEASON_EXCEPTION_NTMLE_RATIO = 0.0912
OFFSEASON_EXCEPTION_ROOM_MLE_RATIO = 0.05678
OFFSEASON_EXCEPTION_BAE_RATIO = 0.0332

OFFSEASON_EXCEPTION_DEFINITIONS = {
    "room_mle": {
        "label": "Room Mid-Level Exception",
        "short_label": "Room MLE",
        "exception_type": "ROOM Mid",
        "hard_cap": "",
        "ratio": OFFSEASON_EXCEPTION_ROOM_MLE_RATIO,
    },
    "ntmle": {
        "label": "Non-Taxpayer Mid-Level Exception",
        "short_label": "NTMLE",
        "exception_type": "Mid-Level",
        "hard_cap": "first",
        "ratio": OFFSEASON_EXCEPTION_NTMLE_RATIO,
    },
    "bae": {
        "label": "Bi-Annual Exception",
        "short_label": "BAE",
        "exception_type": "Bianual",
        "hard_cap": "first",
        "ratio": OFFSEASON_EXCEPTION_BAE_RATIO,
    },
    "tmle": {
        "label": "Taxpayer Mid-Level Exception",
        "short_label": "TMLE",
        "exception_type": "TAXPAYER Mid",
        "hard_cap": "second",
        "ratio": None,
    },
}

GENERATED_OFFSEASON_EXCEPTION_KEYS = tuple(OFFSEASON_EXCEPTION_DEFINITIONS.keys())


def offseason_exception_amounts(salary_cap: Any) -> Dict[str, float]:
    cap = parse_float(str(salary_cap)) or 0.0
    tmle = 0.0
    if cap > 0:
        tmle = OFFSEASON_EXCEPTION_TAXPAYER_MLE_BASE_AMOUNT * (
            cap / OFFSEASON_EXCEPTION_TAXPAYER_MLE_BASE_CAP
        )
    return {
        "room_mle": cap * OFFSEASON_EXCEPTION_ROOM_MLE_RATIO,
        "ntmle": cap * OFFSEASON_EXCEPTION_NTMLE_RATIO,
        "bae": cap * OFFSEASON_EXCEPTION_BAE_RATIO,
        "tmle": tmle,
    }


def offseason_exception_item(key: str, amount: float) -> Dict[str, Any]:
    definition = OFFSEASON_EXCEPTION_DEFINITIONS[key]
    return {
        "key": key,
        "label": definition["label"],
        "short_label": definition["short_label"],
        "exception_type": definition["exception_type"],
        "amount": round(float(amount or 0.0)),
        "hard_cap": definition["hard_cap"],
    }


def normalize_apron_hard_cap(value: Any) -> Optional[str]:
    raw = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    if raw in {"1", "1st", "first", "first apron", "1st apron"}:
        return "first"
    if raw in {"2", "2nd", "second", "second apron", "2nd apron"}:
        return "second"
    return None
