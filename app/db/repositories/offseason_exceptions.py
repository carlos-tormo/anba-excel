"""Persistence for automatically generated offseason exceptions."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .base import LeagueRepository


class OffseasonExceptionRepository(LeagueRepository):
    def replace_generated(
        self,
        season_year: int,
        teams: Iterable[Dict[str, Any]],
        generated_keys: Iterable[str],
        timestamp: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        keys = tuple(str(key) for key in generated_keys)
        placeholders = ",".join("?" for _ in keys)
        created_by_team: Dict[str, List[Dict[str, Any]]] = {}
        with self.db.transaction("IMMEDIATE") as conn:
            for team in teams:
                team_id = int(team["team_id"])
                team_code = str(team["team_code"])
                conn.execute(
                    f"""DELETE FROM assets
                        WHERE team_id = ? AND asset_type = 'exception'
                          AND generated_exception_season = ?
                          AND generated_exception_key IN ({placeholders})""",
                    (team_id, int(season_year), *keys),
                )
                row_order = int(conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (team_id,),
                ).fetchone()["mx"])
                created: List[Dict[str, Any]] = []
                for item in team.get("items") or []:
                    row_order += 1
                    cur = conn.execute(
                        """INSERT INTO assets (
                               team_id, row_order, asset_type, year, label, detail,
                               amount_text, amount_num, draft_pick_type, draft_round,
                               original_owner, exception_type, draft_pick_restricted,
                               draft_pick_stepien_restricted, draft_pick_protected,
                               draft_pick_sold_to, draft_pick_conditional_teams,
                               draft_pick_frozen, generated_exception_key,
                               generated_exception_season, created_at, updated_at
                           ) VALUES (?, ?, 'exception', ?, ?, ?, ?, ?, NULL, NULL, NULL, ?,
                                     0, 0, 0, NULL, NULL, 0, ?, ?, ?, ?)""",
                        (team_id, row_order, int(season_year), item["label"], item["detail"],
                         str(item["amount"]), float(item["amount"]), item["exception_type"],
                         item["key"], int(season_year), timestamp, timestamp),
                    )
                    created.append({"id": int(cur.lastrowid), "key": item["key"],
                                    "amount": item["amount"]})
                created_by_team[team_code] = created
        return created_by_team
