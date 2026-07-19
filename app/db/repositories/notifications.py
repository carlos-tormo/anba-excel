"""SQLite persistence for user notifications."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain_rules import parse_int
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain_rules import parse_int

from .base import LeagueRepository


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class NotificationRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str] = _now_iso) -> None:
        super().__init__(db)
        self._now = now

    def create_conn(
        self,
        conn: Any,
        *,
        user_id: Any = None,
        email: Any = None,
        title: str,
        body: str = "",
        kind: str = "info",
        entity_type: str = "",
        entity_id: Any = None,
    ) -> Optional[int]:
        parsed_user_id = parse_int(user_id)
        normalized_email = str(email or "").strip().lower()
        clean_title = str(title or "").strip()
        if not clean_title or (parsed_user_id is None and not normalized_email):
            return None
        if parsed_user_id is not None:
            user_row = conn.execute("SELECT id FROM users WHERE id = ?", (parsed_user_id,)).fetchone()
            if not user_row:
                parsed_user_id = None
        entity_type_value = str(entity_type or "").strip() or None
        entity_id_value = str(entity_id) if entity_id is not None else None
        if entity_type_value and entity_id_value:
            existing = conn.execute(
                """
                SELECT id
                FROM user_notifications
                WHERE COALESCE(user_id, -1) = COALESCE(?, -1)
                  AND COALESCE(lower(email), '') = COALESCE(?, '')
                  AND entity_type = ?
                  AND entity_id = ?
                  AND read_at IS NULL
                LIMIT 1
                """,
                (parsed_user_id, normalized_email or None, entity_type_value, entity_id_value),
            ).fetchone()
            if existing:
                return int(existing["id"])
        cur = conn.execute(
            """
            INSERT INTO user_notifications (
                user_id, email, title, body, kind, entity_type, entity_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_user_id,
                normalized_email or None,
                clean_title,
                str(body or "").strip() or None,
                str(kind or "info").strip() or "info",
                entity_type_value,
                entity_id_value,
                self._now(),
            ),
        )
        return int(cur.lastrowid)

    def create(self, **kwargs: Any) -> Optional[int]:
        with self.db.connect() as conn:
            notification_id = self.create_conn(conn, **kwargs)
            conn.commit()
            return notification_id

    @staticmethod
    def _session_identity(session: Dict[str, Any]) -> tuple[Optional[int], str]:
        return (
            parse_int((session or {}).get("user_id")),
            str((session or {}).get("email") or "").strip().lower(),
        )

    @staticmethod
    def _identity_filter(user_id: Optional[int], email: str) -> tuple[List[str], List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if email:
            clauses.append("lower(email) = ?")
            params.append(email)
        return clauses, params

    def list_for_session(
        self,
        session: Dict[str, Any],
        *,
        unread_only: bool = True,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        user_id, email = self._session_identity(session)
        clauses, params = self._identity_filter(user_id, email)
        if not clauses:
            return []
        where = f"({' OR '.join(clauses)})"
        if unread_only:
            where = f"{where} AND read_at IS NULL"
        safe_limit = max(1, min(parse_int(limit) or 20, 100))
        with self.db.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT id, title, body, kind, entity_type, entity_id, read_at, created_at
                FROM user_notifications
                WHERE {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                [*params, safe_limit],
            )
            return [dict(row) for row in cur.fetchall()]

    def mark_read(self, notification_id: int, session: Dict[str, Any]) -> bool:
        user_id, email = self._session_identity(session)
        clauses, params = self._identity_filter(user_id, email)
        if not clauses:
            return False
        with self.db.connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE user_notifications
                SET read_at = COALESCE(read_at, ?)
                WHERE id = ? AND ({' OR '.join(clauses)})
                """,
                [self._now(), int(notification_id), *params],
            )
            conn.commit()
            return cur.rowcount > 0
