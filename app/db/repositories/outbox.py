"""Transactional outbox persistence."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, Optional

try:
    from ...domain._values import parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_int

from .base import LeagueRepository


class OutboxRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str]) -> None:
        super().__init__(db)
        self._now = now

    def enqueue_conn(self, conn: Any, event_type: str, payload: Dict[str, Any], *, aggregate_type: Optional[str] = None, aggregate_id: Any = None, idempotency_key: Optional[str] = None) -> Optional[int]:
        normalized_event_type = str(event_type or "").strip()
        if not normalized_event_type:
            raise ValueError("event_type_required")
        payload_json = json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True)
        normalized_aggregate_type = str(aggregate_type or "").strip() or None
        normalized_aggregate_id = str(aggregate_id).strip() if aggregate_id is not None else None
        if not idempotency_key:
            source = "\0".join((normalized_event_type, normalized_aggregate_type or "", normalized_aggregate_id or "", payload_json))
            idempotency_key = f"{normalized_event_type}:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"
        timestamp = self._now()
        conn.execute(
            """INSERT OR IGNORE INTO outbox_events (
                   event_type, aggregate_type, aggregate_id, idempotency_key, payload_json,
                   status, attempts, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)""",
            (normalized_event_type, normalized_aggregate_type, normalized_aggregate_id, idempotency_key, payload_json, timestamp, timestamp),
        )
        row = conn.execute("SELECT id FROM outbox_events WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        return int(row["id"]) if row else None

    def enqueue(self, event_type: str, payload: Dict[str, Any], **kwargs: Any) -> Optional[int]:
        with self.db.transaction("IMMEDIATE") as conn:
            return self.enqueue_conn(conn, event_type, payload, **kwargs)

    def get(self, event_id: Any) -> Optional[Dict[str, Any]]:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, event_type, aggregate_type, aggregate_id, idempotency_key,
                       payload_json, status, attempts, last_error, created_at, updated_at,
                       delivered_at
                FROM outbox_events
                WHERE id = ?
                """,
                (int(parsed_event_id),),
            ).fetchone()
        if not row:
            return None
        event = dict(row)
        try:
            payload = json.loads(event.get("payload_json") or "{}")
        except (TypeError, ValueError):
            payload = {}
        event["payload"] = payload if isinstance(payload, dict) else {}
        return event

    def mark_succeeded(self, event_id: Any) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = self._now()
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'delivered', delivered_at = ?, updated_at = ?, last_error = NULL
                WHERE id = ?
                """,
                (timestamp, timestamp, int(parsed_event_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_failed(self, event_id: Any, error: Any) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = self._now()
        clean_error = str(error or "").strip()[:1000] or "unknown_error"
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'failed',
                    attempts = COALESCE(attempts, 0) + 1,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (clean_error, timestamp, int(parsed_event_id)),
            )
            conn.commit()
            return cur.rowcount > 0
