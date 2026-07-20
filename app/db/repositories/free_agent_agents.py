"""Persistence for free-agent agent-assignment imports."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from .base import LeagueRepository


class FreeAgentAgentRepository(LeagueRepository):
    def connect(self) -> Any:
        return self.db.connect()

    @staticmethod
    def settings(conn: Any) -> Dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM app_settings").fetchall()
        }

    @staticmethod
    def free_agents(conn: Any) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT f.id, COALESCE(pp.name, f.name) AS name, f.agent
                FROM free_agents f
                LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                ORDER BY COALESCE(pp.name, f.name) COLLATE NOCASE, f.id
                """
            ).fetchall()
        ]

    @staticmethod
    def configured_reps(conn: Any) -> List[str]:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'free_agent_reps'"
        ).fetchone()
        if not row or not row["value"]:
            return []
        try:
            parsed = json.loads(str(row["value"]))
        except json.JSONDecodeError:
            return []
        return [
            str(rep or "").strip()
            for rep in parsed if isinstance(parsed, list) and str(rep or "").strip()
        ] if isinstance(parsed, list) else []

    def apply(self, records: Sequence[Dict[str, Any]], timestamp: str) -> Dict[str, Any]:
        changed_count = 0
        unchanged_count = 0
        imported_agents: List[str] = []
        with self.db.connect() as conn:
            existing_reps = self.configured_reps(conn)
            known_reps = {rep.casefold() for rep in existing_reps}
            next_reps = list(existing_reps)
            for record in records:
                row = conn.execute(
                    "SELECT id, agent FROM free_agents WHERE id = ?",
                    (record["free_agent_id"],),
                ).fetchone()
                if not row:
                    raise ValueError("invalid_records")
                current_agent = str(row["agent"] or "").strip()
                agent_name = record["agent_name"]
                conn.execute(
                    "UPDATE free_agents SET agent = ?, updated_at = ? WHERE id = ?",
                    (agent_name, timestamp, record["free_agent_id"]),
                )
                if current_agent.casefold() == agent_name.casefold():
                    unchanged_count += 1
                else:
                    changed_count += 1
                key = agent_name.casefold()
                if key not in known_reps:
                    known_reps.add(key)
                    next_reps.append(agent_name)
                    imported_agents.append(agent_name)
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('free_agent_reps', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (json.dumps(next_reps, ensure_ascii=False), timestamp),
            )
            conn.commit()
        return {
            "record_count": changed_count + unchanged_count,
            "changed_count": changed_count,
            "unchanged_count": unchanged_count,
            "new_agents": imported_agents,
            "free_agent_reps": next_reps,
        }
