"""GM-office aggregate read-model persistence."""

from __future__ import annotations

from typing import Any, Dict

from .base import LeagueRepository


class GMOfficeRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        gm_requests: Any,
        players: Any,
        depth_charts: Any,
    ) -> None:
        super().__init__(db)
        self._gm_requests = gm_requests
        self._players = players
        self._depth_charts = depth_charts

    def read(self, team_code: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            team = conn.execute(
                "SELECT id, code, name FROM teams WHERE code = ?",
                (team_code,),
            ).fetchone()
            if not team:
                raise ValueError("team_not_found")
            team_id = int(team["id"])

            offer_rows = conn.execute(
                """
                SELECT r.*, f.name AS player_name, f.profile_id, f.position,
                       f.rating, f.free_agent_type, f.rights_team_code,
                       t.code AS team_code, t.name AS team_name
                FROM gm_free_agent_offer_requests r
                LEFT JOIN free_agents f ON f.id = r.free_agent_id
                JOIN teams t ON t.id = r.team_id
                WHERE t.code = ? AND r.status <> 'cancelled'
                ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                         r.created_at DESC, r.id DESC
                """,
                (team_code,),
            ).fetchall()
            offers = [self._gm_requests.offer_from_row(row) for row in offer_rows]

            favorite_rows = conn.execute(
                """
                SELECT fav.id AS favorite_id,
                       fav.created_at AS favorite_created_at,
                       f.*, pp.name AS profile_name,
                       pp.experience_years AS profile_experience_years
                FROM free_agent_favorites fav
                JOIN free_agents f ON f.id = fav.free_agent_id
                LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                WHERE fav.team_code = ?
                ORDER BY COALESCE(pp.name, f.name) COLLATE NOCASE, f.id
                """,
                (team_code,),
            ).fetchall()
            favorites = self._players.rows_from_cursor(None, favorite_rows)
            favorites = self._players.attach_salary_history(conn, favorites)

            spending_limit = conn.execute(
                """
                SELECT l.*, t.name AS team_name
                FROM gm_free_agent_spending_limits l
                JOIN teams t ON t.code = l.team_code
                WHERE l.team_code = ?
                """,
                (team_code,),
            ).fetchone()

            return {
                "team": dict(team),
                "offers": offers,
                "favorites": favorites,
                "spending_limit": dict(spending_limit) if spending_limit else None,
                "depth_chart": self._depth_charts.payload(conn, team_id),
                "depth_chart_players": self._depth_charts.team_players(conn, team_id),
            }
