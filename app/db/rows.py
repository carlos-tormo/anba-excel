"""SQLite row conversion helpers."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict

try:
    from ..domain.contracts import normalize_bird_years
except ImportError:  # pragma: no cover
    from domain.contracts import normalize_bird_years


def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
    item = {description[0]: row[index] for index, description in enumerate(cursor.description)}
    if "years_left" in item:
        item["years_left"] = normalize_bird_years(item.get("years_left"))
    return item
