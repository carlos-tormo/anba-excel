"""Persistence primitives for owner economy and office imports."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from .base import LeagueRepository


class OwnerAdminImportRepository(LeagueRepository):
    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.db.connect() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def teams_by_code(conn: Any) -> Dict[str, Dict[str, Any]]:
        return {
            str(row["code"]).upper(): {"id": int(row["id"]), "name": str(row["name"])}
            for row in conn.execute("SELECT id, code, name FROM teams").fetchall()
        }

    @staticmethod
    def economy_by_team(conn: Any) -> Dict[tuple[int, str], Dict[str, float]]:
        return {
            (int(row["season_year"]), str(row["code"]).upper()): {
                "revenue": float(row["revenue"] or 0),
                "expenses": float(row["expenses"] or 0),
                "balance": float(row["balance"] or 0),
            }
            for row in conn.execute(
                """
                SELECT e.season_year, t.code, e.revenue, e.expenses, e.balance
                FROM team_economy e
                JOIN teams t ON t.id = e.team_id
                """
            ).fetchall()
        }

    @staticmethod
    def economy_row(conn: Any, team_id: int, season_year: int) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            """
            SELECT COALESCE(revenue, 0) AS revenue,
                   COALESCE(expenses, 0) AS expenses
            FROM team_economy
            WHERE team_id = ? AND season_year = ?
            """,
            (team_id, season_year),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def owner_office_row(conn: Any, team_id: int, season_year: int) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            """
            SELECT *
            FROM team_owner_office
            WHERE team_id = ? AND season_year = ?
            """,
            (team_id, season_year),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def upsert_economy(
        conn: Any,
        *,
        team_id: int,
        season_year: int,
        balance: float,
        revenue: float,
        expenses: float,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_economy (
                team_id, season_year, balance, revenue, expenses, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, season_year) DO UPDATE SET
                balance = excluded.balance,
                revenue = excluded.revenue,
                expenses = excluded.expenses,
                updated_at = excluded.updated_at
            """,
            (team_id, season_year, balance, revenue, expenses, updated_at),
        )

    @staticmethod
    def upsert_owner_economy(
        conn: Any,
        *,
        team_id: int,
        season_year: int,
        revenue: str,
        expenses: str,
        balance: str,
        income_json: str,
        expenses_json: str,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_owner_office (
                team_id, season_year, revenue, expenses, balance,
                income_json, expenses_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, season_year) DO UPDATE SET
                revenue = excluded.revenue,
                expenses = excluded.expenses,
                balance = excluded.balance,
                income_json = excluded.income_json,
                expenses_json = excluded.expenses_json,
                updated_at = excluded.updated_at
            """,
            (
                team_id,
                season_year,
                revenue,
                expenses,
                balance,
                income_json,
                expenses_json,
                updated_at,
            ),
        )

    @staticmethod
    def upsert_owner_office(
        conn: Any,
        *,
        team_id: int,
        season_year: int,
        confidence_current: str,
        confidence_change: str,
        season_goal_set: str,
        season_goal_achieved: str,
        revenue: Optional[str],
        expenses: Optional[str],
        balance: Optional[str],
        income_json: str,
        expenses_json: str,
        performance_json: str,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_owner_office (
                team_id, season_year, confidence_current, confidence_change,
                season_goal_set, season_goal_achieved, revenue, expenses,
                balance, income_json, expenses_json, performance_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, season_year) DO UPDATE SET
                confidence_current = excluded.confidence_current,
                confidence_change = excluded.confidence_change,
                season_goal_set = excluded.season_goal_set,
                season_goal_achieved = excluded.season_goal_achieved,
                revenue = excluded.revenue,
                expenses = excluded.expenses,
                balance = excluded.balance,
                income_json = excluded.income_json,
                expenses_json = excluded.expenses_json,
                performance_json = excluded.performance_json,
                updated_at = excluded.updated_at
            """,
            (
                team_id,
                season_year,
                confidence_current,
                confidence_change,
                season_goal_set,
                season_goal_achieved,
                revenue,
                expenses,
                balance,
                income_json,
                expenses_json,
                performance_json,
                updated_at,
            ),
        )
