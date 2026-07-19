"""Shared support for incremental LeagueDB repository adapters."""

from __future__ import annotations

from typing import Any


class LeagueRepository:
    def __init__(self, db: Any) -> None:
        self.db = db
