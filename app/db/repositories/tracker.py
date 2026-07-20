"""Persistence queries for the league-wide tracker read model."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from .base import LeagueRepository


class TrackerRepository(LeagueRepository):
    @contextmanager
    def connection(self, busy_timeout_ms: Optional[int] = 5000) -> Iterator[Any]:
        with self.db.connect() as conn:
            if busy_timeout_ms is not None:
                timeout = max(100, min(int(busy_timeout_ms), 15000))
                conn.execute(f"PRAGMA busy_timeout = {timeout}")
            yield conn

    @staticmethod
    def settings(conn: Any) -> Dict[str, str]:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    @staticmethod
    def teams(conn: Any) -> List[Dict[str, Any]]:
        return [dict(row) for row in conn.execute("SELECT * FROM teams ORDER BY code").fetchall()]

    @staticmethod
    def assets(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
            (team_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def dead_contracts(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
            (team_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_timings(self, timings: Dict[str, float]) -> None:
        setattr(self.db, "_last_tracker_timings", timings)
