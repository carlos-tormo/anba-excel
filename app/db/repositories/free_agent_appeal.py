"""Persistence for free-agent team-appeal rankings."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .base import LeagueRepository


class FreeAgentAppealRepository(LeagueRepository):
    def list_teams(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT code, name FROM teams ORDER BY code"
                ).fetchall()
            ]

    def replace(self, records: Sequence[Dict[str, Any]], timestamp: str) -> int:
        with self.db.connect() as conn:
            valid_teams = {
                str(row["code"] or "").upper()
                for row in conn.execute("SELECT code FROM teams").fetchall()
            }
            for record in records:
                if record["team_code"] not in valid_teams:
                    raise ValueError("invalid_records")
                conn.execute(
                    """
                    INSERT INTO free_agent_team_appeal (
                        team_code, under_23_single, under_23_multi,
                        age_23_26_single, age_23_26_multi,
                        age_27_33_single, age_27_33_multi,
                        over_34_single, over_34_multi, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_code) DO UPDATE SET
                        under_23_single = excluded.under_23_single,
                        under_23_multi = excluded.under_23_multi,
                        age_23_26_single = excluded.age_23_26_single,
                        age_23_26_multi = excluded.age_23_26_multi,
                        age_27_33_single = excluded.age_27_33_single,
                        age_27_33_multi = excluded.age_27_33_multi,
                        over_34_single = excluded.over_34_single,
                        over_34_multi = excluded.over_34_multi,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record["team_code"], record["under_23_single"],
                        record["under_23_multi"], record["age_23_26_single"],
                        record["age_23_26_multi"], record["age_27_33_single"],
                        record["age_27_33_multi"], record["over_34_single"],
                        record["over_34_multi"], timestamp,
                    ),
                )
            conn.commit()
        return len(records)

    def list_rows(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT t.code AS team_code, t.name AS team_name,
                           COALESCE(a.under_23_single, 0) AS under_23_single,
                           COALESCE(a.under_23_multi, 0) AS under_23_multi,
                           COALESCE(a.age_23_26_single, 0) AS age_23_26_single,
                           COALESCE(a.age_23_26_multi, 0) AS age_23_26_multi,
                           COALESCE(a.age_27_33_single, 0) AS age_27_33_single,
                           COALESCE(a.age_27_33_multi, 0) AS age_27_33_multi,
                           COALESCE(a.over_34_single, 0) AS over_34_single,
                           COALESCE(a.over_34_multi, 0) AS over_34_multi,
                           a.updated_at
                    FROM teams t
                    LEFT JOIN free_agent_team_appeal a ON a.team_code = t.code
                    ORDER BY t.code
                    """
                ).fetchall()
            ]
