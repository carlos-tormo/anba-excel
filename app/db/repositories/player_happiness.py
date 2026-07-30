"""Persistence for player happiness imports and event history."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from .base import LeagueRepository


class PlayerHappinessRepository(LeagueRepository):
    def connect(self) -> Any:
        return self.db.connect()

    def profiles(self, conn: Any) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT pp.id AS profile_id,
                   pp.name,
                   pp.happiness,
                   pp.profile_status,
                   pp.version,
                   roster.team_code,
                   roster.team_name,
                   CASE WHEN roster.profile_id IS NOT NULL THEN 'roster'
                        WHEN fa.profile_id IS NOT NULL THEN 'free_agent'
                        ELSE pp.profile_status
                   END AS status_label
            FROM player_profiles pp
            LEFT JOIN (
                SELECT p.profile_id, MIN(t.code) AS team_code, MIN(t.name) AS team_name
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.profile_id IS NOT NULL
                GROUP BY p.profile_id
            ) roster ON roster.profile_id = pp.id
            LEFT JOIN (
                SELECT profile_id
                FROM free_agents
                WHERE profile_id IS NOT NULL
                GROUP BY profile_id
            ) fa ON fa.profile_id = pp.id
            ORDER BY pp.name COLLATE NOCASE, pp.id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def apply_baseline_import(
        self,
        records: Sequence[Dict[str, Any]],
        *,
        timestamp: str,
        command_id: str,
        actor_user_id: int | None,
    ) -> Dict[str, Any]:
        changed_count = 0
        unchanged_count = 0
        updated_profiles: List[Dict[str, Any]] = []
        with self.db.transaction("IMMEDIATE") as conn:
            for record in records:
                profile_id = int(record["profile_id"])
                expected_version = int(record["expected_version"])
                new_value = float(record["happiness"])
                row = conn.execute(
                    """
                    SELECT id, name, happiness, version
                    FROM player_profiles
                    WHERE id = ?
                    """,
                    (profile_id,),
                ).fetchone()
                if not row:
                    raise ValueError("invalid_records")
                current_name = str(row["name"] or "").strip()
                if current_name != str(record.get("player_name") or "").strip():
                    raise ValueError("happiness_import_target_changed")
                current_version = int(row["version"])
                if current_version != expected_version:
                    raise ValueError("stale_entity_version")
                previous_value = float(row["happiness"] or 0)
                applied_delta = new_value - previous_value
                cur = conn.execute(
                    """
                    UPDATE player_profiles
                    SET happiness = ?,
                        version = version + 1,
                        updated_at = ?
                    WHERE id = ?
                      AND version = ?
                    """,
                    (new_value, timestamp, profile_id, current_version),
                )
                if cur.rowcount != 1:
                    raise ValueError("stale_entity_version")
                conn.execute(
                    """
                    INSERT INTO player_happiness_events (
                        profile_id, event_type, event_date, season_year,
                        previous_value, proposed_delta, applied_delta, new_value,
                        source_entity_type, source_entity_id, reason, metadata_json,
                        command_id, actor_user_id, created_at
                    ) VALUES (?, 'baseline_import', ?, NULL, ?, ?, ?, ?, 'admin_import', ?,
                              ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        str(record.get("event_date") or "")[:10] or None,
                        previous_value,
                        applied_delta,
                        applied_delta,
                        new_value,
                        command_id,
                        str(record.get("reason") or "Initial happiness baseline import").strip(),
                        json.dumps(
                            {
                                "input_player_name": record.get("input_player_name"),
                                "match_method": record.get("match_method"),
                            },
                            ensure_ascii=False,
                        ),
                        command_id,
                        actor_user_id,
                        timestamp,
                    ),
                )
                if previous_value == new_value:
                    unchanged_count += 1
                else:
                    changed_count += 1
                updated_profiles.append(
                    {
                        "profile_id": profile_id,
                        "player_name": current_name,
                        "previous_happiness": previous_value,
                        "new_happiness": new_value,
                        "version": current_version + 1,
                    }
                )
        return {
            "ok": True,
            "record_count": changed_count + unchanged_count,
            "changed_count": changed_count,
            "unchanged_count": unchanged_count,
            "updated_profiles": updated_profiles,
        }
