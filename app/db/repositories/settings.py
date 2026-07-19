"""SQLite persistence for application settings and team economy."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain_rules import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR, parse_amount_like, parse_int
except ImportError:  # pragma: no cover
    from domain_rules import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR, parse_amount_like, parse_int

from .base import LeagueRepository


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SettingsRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str] = _now_iso) -> None:
        super().__init__(db)
        self._now = now

    def get_all(self) -> Dict[str, str]:
        with self.db.connect() as conn:
            return {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}

    def update(self, key: str, value: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (key, value, self._now()),
            )
            conn.commit()

    def list_team_economy(self, season_year: Optional[int] = None) -> Dict[str, Any]:
        with self.db.connect() as conn:
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings")}
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < CAP_FORECAST_MIN_YEAR or current_year > CAP_FORECAST_MAX_YEAR:
                current_year = 2025
            season = season_year if season_year is not None else current_year
            if season < 2000 or season > 2100:
                season = current_year
            seasons = {current_year, 2025, *(int(row["season_year"]) for row in conn.execute("SELECT DISTINCT season_year FROM team_economy"))}
            rows = conn.execute(
                """SELECT t.code, t.name, COALESCE(e.balance, 0) AS balance,
                          COALESCE(e.revenue, 0) AS revenue, COALESCE(e.expenses, 0) AS expenses
                   FROM teams t LEFT JOIN team_economy e ON e.team_id = t.id AND e.season_year = ?
                   ORDER BY t.code""",
                (season,),
            ).fetchall()
            return {"season_year": season, "seasons": sorted(seasons), "rows": [
                {"team_code": row["code"], "team_name": row["name"], "season_year": season,
                 "balance": float(row["balance"] or 0), "revenue": float(row["revenue"] or 0),
                 "expenses": float(row["expenses"] or 0)} for row in rows
            ]}

    def upsert_team_economy(self, season_year: int, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if season_year < 2000 or season_year > 2100:
            raise ValueError("invalid_season_year")
        with self.db.connect() as conn:
            team_ids = {str(row["code"]).upper(): int(row["id"]) for row in conn.execute("SELECT id, code FROM teams")}
            for row in rows:
                code = str(row.get("team_code") or row.get("code") or "").strip().upper()
                if code not in team_ids:
                    raise ValueError(f"invalid_team_code:{code}")
                conn.execute(
                    """INSERT INTO team_economy (team_id, season_year, balance, revenue, expenses, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(team_id, season_year) DO UPDATE SET
                       balance = excluded.balance, revenue = excluded.revenue,
                       expenses = excluded.expenses, updated_at = excluded.updated_at""",
                    (team_ids[code], season_year, float(parse_amount_like(row.get("balance")) or 0),
                     float(parse_amount_like(row.get("revenue")) or 0),
                     float(parse_amount_like(row.get("expenses")) or 0), self._now()),
                )
            conn.commit()
        return self.list_team_economy(season_year)
