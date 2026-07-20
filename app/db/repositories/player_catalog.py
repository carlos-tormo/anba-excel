"""Persistence queries for the player-catalog read model."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from .base import LeagueRepository


class PlayerCatalogRepository(LeagueRepository):
    @contextmanager
    def connection(self) -> Iterator[Any]:
        with self.db.connect() as conn:
            yield conn

    @staticmethod
    def settings(conn: Any) -> Dict[str, str]:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    @staticmethod
    def profiles(conn: Any) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """SELECT id, name, date_of_birth, nationality, experience_years, yos_source,
                      reference_image_url, profile_notes, transaction_notes, happiness, profile_status,
                      created_at, updated_at
               FROM player_profiles ORDER BY name COLLATE NOCASE, id"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def active_contracts(conn: Any, season_year: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            f"""SELECT p.id AS player_id, p.profile_id, p.position, p.bird_rights, p.rating,
                       p.years_left, p.signed_as_free_agent,
                       p.salary_{int(season_year)}_text AS current_salary_text,
                       p.salary_{int(season_year)}_num AS current_salary_num,
                       p.option_{int(season_year)} AS current_option,
                       t.code AS team_code, t.name AS team_name
                FROM players p JOIN teams t ON t.id = p.team_id
                WHERE p.profile_id IS NOT NULL ORDER BY p.profile_id, p.row_order, p.id"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def free_agents(conn: Any) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """SELECT f.id AS free_agent_id, f.profile_id, f.position, f.bird_rights, f.rating,
                      f.years_left, f.free_agent_type, f.source, f.rights_team_code,
                      rt.name AS rights_team_name
               FROM free_agents f LEFT JOIN teams rt ON rt.code = f.rights_team_code
               WHERE f.profile_id IS NOT NULL ORDER BY f.profile_id, f.id"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def dead_contracts(conn: Any) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """SELECT d.id AS dead_contract_id, d.profile_id, d.dead_type, d.label,
                      t.code AS team_code, t.name AS team_name
               FROM dead_contracts d JOIN teams t ON t.id = d.team_id
               WHERE d.profile_id IS NOT NULL ORDER BY d.profile_id, t.code, d.id DESC"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def transactions(conn: Any) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """SELECT id, profile_id, created_at, action, team_code, from_team_code, to_team_code, summary, details_json
               FROM (SELECT id, profile_id, created_at, action, team_code, from_team_code, to_team_code,
                            summary, details_json, ROW_NUMBER() OVER (PARTITION BY profile_id ORDER BY created_at DESC, id DESC) AS rn
                     FROM player_transactions)
               WHERE rn <= 10 ORDER BY profile_id, created_at DESC, id DESC"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def salary_history(conn: Any, profile_ids: List[int]) -> List[Dict[str, Any]]:
        if not profile_ids:
            return []
        placeholders = ",".join("?" for _ in profile_ids)
        rows = conn.execute(
            f"""SELECT id, profile_id, player_id, team_code, season_year, salary_text,
                       salary_num, salary_type, source, created_at, updated_at
                FROM player_salary_history WHERE profile_id IN ({placeholders})
                ORDER BY profile_id, season_year DESC, id DESC""",
            profile_ids,
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def has_salary_history(conn: Any) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'player_salary_history'"
        ).fetchone()
        return row is not None

    @staticmethod
    def commit(conn: Any) -> None:
        conn.commit()

    def record_timings(self, timings: Dict[str, float]) -> None:
        setattr(self.db, "_last_list_players_timings", timings)
