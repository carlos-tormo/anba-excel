"""Persistence primitives for the team-detail aggregate."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import LeagueRepository


class TeamDetailRepository(LeagueRepository):
    def connect(self) -> Any:
        return self.db.connect()

    @staticmethod
    def team(conn: Any, code: str) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            "SELECT * FROM teams WHERE code = ?",
            (code.upper(),),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def assets(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM assets
                WHERE team_id = ? AND asset_type != 'dead_cap'
                ORDER BY asset_type, row_order, id
                """,
                (team_id,),
            ).fetchall()
        ]

    @staticmethod
    def dead_contracts(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM dead_contracts
                WHERE team_id = ?
                ORDER BY dead_type, row_order, id
                """,
                (team_id,),
            ).fetchall()
        ]

    @staticmethod
    def gm_history(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT h.id, t.code AS team_code, t.name AS team_name,
                       h.row_order, h.gm_name, h.start_date, h.color,
                       h.created_at, h.updated_at
                FROM team_gm_history h
                JOIN teams t ON t.id = h.team_id
                WHERE h.team_id = ?
                ORDER BY h.start_date, h.row_order, h.id
                """,
                (team_id,),
            ).fetchall()
        ]
