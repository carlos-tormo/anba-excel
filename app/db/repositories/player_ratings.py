"""Persistence for player rating imports."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .base import LeagueRepository


class PlayerRatingImportRepository(LeagueRepository):
    def connect(self) -> Any:
        return self.db.connect()

    def rating_targets(self, conn: Any) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT 'player' AS target_type,
                   p.id AS target_id,
                   p.profile_id,
                   p.name,
                   p.rating,
                   t.code AS team_code,
                   t.name AS team_name
            FROM players p
            JOIN teams t ON t.id = p.team_id
            UNION ALL
            SELECT 'free_agent' AS target_type,
                   f.id AS target_id,
                   f.profile_id,
                   COALESCE(pp.name, f.name) AS name,
                   f.rating,
                   NULL AS team_code,
                   NULL AS team_name
            FROM free_agents f
            LEFT JOIN player_profiles pp ON pp.id = f.profile_id
            ORDER BY name COLLATE NOCASE, target_type, target_id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _target_table(target_type: Any) -> str:
        normalized = str(target_type or "").strip().lower()
        if normalized == "player":
            return "players"
        if normalized == "free_agent":
            return "free_agents"
        raise ValueError("invalid_rating_import_target")

    def apply(self, records: Sequence[Dict[str, Any]], timestamp: str) -> Dict[str, Any]:
        changed_count = 0
        unchanged_count = 0
        updated_targets: List[Dict[str, Any]] = []
        with self.db.transaction("IMMEDIATE") as conn:
            for record in records:
                table = self._target_table(record.get("target_type"))
                target_id = int(record["target_id"])
                player_name = str(record.get("player_name") or "").strip()
                rating = str(int(record["new_rating"]))
                if table == "free_agents":
                    row = conn.execute(
                        """
                        SELECT f.id, COALESCE(pp.name, f.name) AS name, f.rating
                        FROM free_agents f
                        LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                        WHERE f.id = ?
                        """,
                        (target_id,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT id, name, rating FROM players WHERE id = ?",
                        (target_id,),
                    ).fetchone()
                if not row:
                    raise ValueError("invalid_records")
                current_name = str(row["name"] or "").strip()
                if player_name and current_name != player_name:
                    raise ValueError("rating_import_target_changed")
                current_rating = str(row["rating"] or "").strip()
                conn.execute(
                    f"UPDATE {table} SET rating = ?, updated_at = ? WHERE id = ?",
                    (rating, timestamp, target_id),
                )
                if current_rating == rating:
                    unchanged_count += 1
                else:
                    changed_count += 1
                updated_targets.append(
                    {
                        "target_type": record.get("target_type"),
                        "target_id": target_id,
                        "player_name": current_name,
                        "previous_rating": current_rating,
                        "new_rating": rating,
                    }
                )
        return {
            "ok": True,
            "record_count": changed_count + unchanged_count,
            "changed_count": changed_count,
            "unchanged_count": unchanged_count,
            "updated_targets": updated_targets,
        }
