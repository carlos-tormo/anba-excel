"""SQLite persistence for authenticated users and team access."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

try:
    from ...auth.policies import normalize_team_codes
    from ...domain_rules import parse_bool
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_codes
    from domain_rules import parse_bool

from .base import LeagueRepository


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class UserRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str] = _now_iso) -> None:
        super().__init__(db)
        self._now = now

    def upsert_google_user(self, google_sub: str, email: str, display_name: Optional[str], avatar_url: Optional[str]) -> Dict[str, Any]:
        timestamp = self._now()
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO users (google_sub, email, display_name, avatar_url, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(google_sub) DO UPDATE SET email = excluded.email,
                       display_name = excluded.display_name, avatar_url = excluded.avatar_url,
                       updated_at = excluded.updated_at""",
                (google_sub, email, display_name, avatar_url, timestamp, timestamp),
            )
            row = conn.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,)).fetchone()
            conn.commit()
            if not row:
                raise RuntimeError("Failed to load Google user after upsert")
            return dict(row)

    def team_codes_by_email(self, email: str) -> List[str]:
        normalized = str(email or "").strip().lower()
        if not normalized:
            return []
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT t.code FROM users u
                   JOIN user_team_assignments a ON a.user_id = u.id
                   JOIN teams t ON t.id = a.team_id
                   WHERE lower(u.email) = ? ORDER BY t.code""",
                (normalized,),
            ).fetchall()
            return [str(row["code"]).upper() for row in rows]

    def list(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT u.id, u.email, u.display_name, u.avatar_url,
                          COALESCE(u.is_co_admin, 0) AS is_co_admin, u.agent_name,
                          u.created_at, u.updated_at, GROUP_CONCAT(t.code, ',') AS team_codes
                   FROM users u
                   LEFT JOIN user_team_assignments a ON a.user_id = u.id
                   LEFT JOIN teams t ON t.id = a.team_id
                   GROUP BY u.id ORDER BY lower(u.email)"""
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["team_codes"] = normalize_team_codes(item.get("team_codes"))
                item["is_co_admin"] = bool(parse_bool(item.get("is_co_admin")))
                result.append(item)
            return result

    def access_for_email(self, email: str) -> Dict[str, Any]:
        normalized = str(email or "").strip().lower()
        if not normalized:
            return {"team_codes": [], "is_co_admin": False}
        with self.db.connect() as conn:
            user = conn.execute(
                "SELECT id, COALESCE(is_co_admin, 0) AS is_co_admin, agent_name FROM users WHERE lower(email) = ?",
                (normalized,),
            ).fetchone()
            if not user:
                return {"team_codes": [], "is_co_admin": False, "agent_name": ""}
            teams = conn.execute(
                """SELECT t.code FROM user_team_assignments a
                   JOIN teams t ON t.id = a.team_id WHERE a.user_id = ? ORDER BY t.code""",
                (int(user["id"]),),
            ).fetchall()
            return {
                "team_codes": [str(row["code"]).upper() for row in teams],
                "is_co_admin": bool(parse_bool(user["is_co_admin"])),
                "agent_name": str(user["agent_name"] or "").strip(),
            }

    def replace_team_assignments(
        self, user_id: int, team_codes: Any, is_co_admin: Optional[bool] = None, agent_name: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        codes = normalize_team_codes(team_codes)
        clean_agent = re.sub(r"\s+", " ", str(agent_name or "").strip()) if agent_name is not None else None
        timestamp = self._now()
        with self.db.connect() as conn:
            if not conn.execute("SELECT id FROM users WHERE id = ?", (int(user_id),)).fetchone():
                return None
            teams: Dict[str, Any] = {}
            if codes:
                placeholders = ",".join("?" for _ in codes)
                rows = conn.execute(f"SELECT id, code FROM teams WHERE code IN ({placeholders})", codes).fetchall()
                teams = {str(row["code"]).upper(): row for row in rows}
                missing = [code for code in codes if code not in teams]
                if missing:
                    raise ValueError(f"invalid_team_code:{missing[0]}")
            conn.execute("DELETE FROM user_team_assignments WHERE user_id = ?", (int(user_id),))
            for code in codes:
                conn.execute(
                    "INSERT INTO user_team_assignments (user_id, team_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (int(user_id), int(teams[code]["id"]), timestamp, timestamp),
                )
            updates = ["updated_at = ?"]
            values: List[Any] = [timestamp]
            if is_co_admin is not None:
                updates.append("is_co_admin = ?")
                values.append(1 if parse_bool(is_co_admin) else 0)
            if agent_name is not None:
                updates.append("agent_name = ?")
                values.append(clean_agent if is_co_admin is None or parse_bool(is_co_admin) else "")
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", (*values, int(user_id)))
            conn.commit()
        return next((user for user in self.list() if int(user.get("id") or 0) == int(user_id)), None)
