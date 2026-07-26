"""SQLite persistence for site and offline GM identities."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from .base import LeagueRepository


def gm_display_name(row: Any) -> str:
    username = str(row["username"] or "").strip() if "username" in row.keys() else ""
    display_name = str(row["display_name"] or "").strip() if "display_name" in row.keys() else ""
    email = str(row["email"] or "").strip() if "email" in row.keys() else ""
    return username or display_name or email


def clean_gm_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def ensure_user_gm_identity(conn: Any, user_id: int, *, now: str) -> Optional[int]:
    row = conn.execute(
        "SELECT id, username, display_name, email FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if not row:
        return None
    name = gm_display_name(row)
    if not name:
        return None
    existing = conn.execute(
        "SELECT id FROM gm_identities WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE gm_identities
            SET entity_type = 'user',
                display_name = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (name, now, int(existing["id"])),
        )
        return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO gm_identities (
            entity_type, user_id, display_name, created_at, updated_at
        ) VALUES ('user', ?, ?, ?, ?)
        """,
        (int(user_id), name, now, now),
    )
    return int(cur.lastrowid)


def upsert_offline_gm_identity(conn: Any, name: Any, *, now: str) -> Optional[int]:
    display_name = clean_gm_name(name)
    if not display_name:
        return None
    existing = conn.execute(
        """
        SELECT id FROM gm_identities
        WHERE entity_type = 'offline' AND lower(display_name) = lower(?)
        ORDER BY id
        LIMIT 1
        """,
        (display_name,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE gm_identities SET display_name = ?, updated_at = ? WHERE id = ?",
            (display_name, now, int(existing["id"])),
        )
        return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO gm_identities (
            entity_type, user_id, display_name, created_at, updated_at
        ) VALUES ('offline', NULL, ?, ?, ?)
        """,
        (display_name, now, now),
    )
    return int(cur.lastrowid)


class GMIdentityRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str]) -> None:
        super().__init__(db)
        self._now = now

    def list(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            timestamp = self._now()
            for row in conn.execute("SELECT id FROM users ORDER BY id").fetchall():
                ensure_user_gm_identity(conn, int(row["id"]), now=timestamp)
            conn.commit()
            rows = conn.execute(
                """
                SELECT g.id, g.entity_type, g.user_id, g.display_name,
                       u.email, u.username, u.avatar_url,
                       COUNT(h.id) AS history_count,
                       MIN(h.start_date) AS first_start_date,
                       MAX(h.start_date) AS last_start_date
                FROM gm_identities g
                LEFT JOIN users u ON u.id = g.user_id
                LEFT JOIN team_gm_history h ON h.gm_entity_id = g.id
                GROUP BY g.id
                ORDER BY lower(g.display_name), g.id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def create_offline(self, name: Any) -> Dict[str, Any]:
        display_name = clean_gm_name(name)
        if not display_name:
            raise ValueError("gm_name_required")
        if len(display_name) > 120:
            raise ValueError("gm_name_too_long")
        timestamp = self._now()
        with self.db.connect() as conn:
            gm_id = upsert_offline_gm_identity(conn, display_name, now=timestamp)
            conn.commit()
        return next(row for row in self.list() if int(row["id"]) == int(gm_id))

    def list_profiles(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            timestamp = self._now()
            for row in conn.execute("SELECT id FROM users ORDER BY id").fetchall():
                ensure_user_gm_identity(conn, int(row["id"]), now=timestamp)
            conn.commit()
            identities = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT g.id, g.entity_type, g.user_id, g.display_name,
                           CASE WHEN g.user_id IS NULL THEN 0 ELSE 1 END AS has_site_user
                    FROM gm_identities g
                    ORDER BY lower(g.display_name), g.id
                    """
                ).fetchall()
            ]
            history_rows = conn.execute(
                """
                SELECT h.gm_entity_id, h.gm_name, h.start_date, h.color,
                       t.code AS team_code, t.name AS team_name
                FROM team_gm_history h
                JOIN teams t ON t.id = h.team_id
                WHERE h.gm_entity_id IS NOT NULL
                ORDER BY h.start_date DESC, t.code, h.row_order, h.id
                """
            ).fetchall()
            histories: Dict[int, List[Dict[str, Any]]] = {}
            for row in history_rows:
                gm_id = int(row["gm_entity_id"])
                histories.setdefault(gm_id, []).append(
                    {
                        "team_code": row["team_code"],
                        "team_name": row["team_name"],
                        "gm_name": row["gm_name"],
                        "start_date": row["start_date"],
                        "color": row["color"],
                    }
                )
            for identity in identities:
                identity["has_site_user"] = bool(identity.get("has_site_user"))
                identity["history"] = histories.get(int(identity["id"]), [])
            return identities
