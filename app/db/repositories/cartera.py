"""SQL-owned read models for agent cartera clients."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import LeagueRepository


class CarteraRepository(LeagueRepository):
    def client_snapshot(self, agent_name: Optional[str]) -> Dict[str, Any]:
        where = "COALESCE(f.agent, '') != ''"
        params: List[Any] = []
        if agent_name is not None:
            where = "lower(trim(COALESCE(f.agent, ''))) = lower(trim(?))"
            params.append(str(agent_name))

        with self.db.connect() as conn:
            clients = [dict(row) for row in conn.execute(
                f"""SELECT f.id, f.profile_id, f.name, f.position, f.rating,
                           f.free_agent_type, f.rights_team_code, f.agent,
                           COUNT(DISTINCT i.id) AS interest_count,
                           COUNT(DISTINCT fav.team_code) AS favorite_count,
                           COUNT(DISTINCT offer.team_id) AS offer_count
                    FROM free_agents f
                    LEFT JOIN free_agent_interests i ON i.free_agent_id = f.id
                    LEFT JOIN free_agent_favorites fav ON fav.free_agent_id = f.id
                    LEFT JOIN gm_free_agent_offer_requests offer
                      ON offer.free_agent_id = f.id AND offer.status IN ('pending', 'approved')
                    WHERE {where}
                    GROUP BY f.id
                    ORDER BY COUNT(DISTINCT i.id) DESC,
                             COUNT(DISTINCT fav.team_code) DESC,
                             COUNT(DISTINCT offer.team_id) DESC, lower(f.name)""",
                params,
            ).fetchall()]
            client_ids = [int(row["id"]) for row in clients]
            groups: Dict[str, Dict[int, List[Dict[str, Any]]]] = {
                name: {client_id: [] for client_id in client_ids}
                for name in ("interests", "favorites", "offers", "ruleouts")
            }
            if not client_ids:
                return {"clients": clients, **groups}

            placeholders = ",".join("?" for _ in client_ids)
            queries = {
                "interests": f"""SELECT i.*, t.name AS team_name
                    FROM free_agent_interests i LEFT JOIN teams t ON t.code = i.team_code
                    WHERE i.free_agent_id IN ({placeholders})
                    ORDER BY i.updated_at DESC, i.team_code""",
                "favorites": f"""SELECT fav.*, t.name AS team_name
                    FROM free_agent_favorites fav LEFT JOIN teams t ON t.code = fav.team_code
                    WHERE fav.free_agent_id IN ({placeholders})
                    ORDER BY fav.updated_at DESC, fav.team_code""",
                "offers": f"""SELECT r.free_agent_id, r.status, r.created_at, r.updated_at,
                           t.code AS team_code, t.name AS team_name
                    FROM gm_free_agent_offer_requests r JOIN teams t ON t.id = r.team_id
                    WHERE r.free_agent_id IN ({placeholders})
                      AND r.status IN ('pending', 'approved')
                    ORDER BY CASE r.status WHEN 'approved' THEN 0 ELSE 1 END,
                             r.updated_at DESC, t.code""",
                "ruleouts": f"""SELECT r.*, t.name AS team_name
                    FROM free_agent_team_ruleouts r LEFT JOIN teams t ON t.code = r.team_code
                    WHERE r.free_agent_id IN ({placeholders})
                    ORDER BY r.updated_at DESC, r.team_code""",
            }
            seen_offer_teams: set[tuple[int, str]] = set()
            for group_name, query in queries.items():
                for row in conn.execute(query, client_ids).fetchall():
                    item = dict(row)
                    client_id = int(item["free_agent_id"])
                    if group_name == "offers":
                        dedupe_key = (client_id, str(item.get("team_code") or "").upper())
                        if dedupe_key in seen_offer_teams:
                            continue
                        seen_offer_teams.add(dedupe_key)
                    groups[group_name].setdefault(client_id, []).append(item)
        return {"clients": clients, **groups}
