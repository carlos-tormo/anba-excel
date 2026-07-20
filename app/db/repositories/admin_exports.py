"""Persistence queries used by administrative workbook exports."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import LeagueRepository


class AdminExportRepository(LeagueRepository):
    def economy_rows(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT t.code AS team_code, t.name AS team_name, e.season_year,
                          e.balance, e.revenue, e.expenses
                   FROM team_economy e JOIN teams t ON t.id = e.team_id
                   ORDER BY e.season_year, t.code"""
            ).fetchall()
            return [dict(row) for row in rows]

    def draft_order_rows(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT d.*,
                          COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                          COALESCE(original.name, d.original_team_code) AS original_team_name,
                          s.selection_text, COALESCE(s.skipped, 0) AS skipped
                   FROM draft_order d
                   LEFT JOIN teams owner ON owner.code = d.owner_team_code
                   LEFT JOIN teams original ON original.code = d.original_team_code
                   LEFT JOIN draft_live_selections s ON s.draft_order_id = d.id
                   ORDER BY d.draft_year,
                       CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                       d.pick_number, d.id"""
            ).fetchall()
            return [dict(row) for row in rows]
