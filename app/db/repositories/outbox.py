"""Transactional outbox persistence."""

from __future__ import annotations

import hashlib
import json
import socket
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, Optional

try:
    from ...domain._values import parse_int
    from ...integrations.discord import redact_secrets
except ImportError:  # pragma: no cover
    from domain._values import parse_int
    from integrations.discord import redact_secrets

from .base import LeagueRepository


class OutboxRepository(LeagueRepository):
    DEFAULT_MAX_ATTEMPTS = 5

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
                   status, attempts, available_at, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)""",
            (normalized_event_type, normalized_aggregate_type, normalized_aggregate_id, idempotency_key, payload_json, timestamp, timestamp, timestamp),
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
                       payload_json, status, attempts, next_attempt_at, available_at,
                       locked_at, locked_by, last_error_code, last_error,
                       created_at, updated_at, delivered_at
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

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed

    def _now_datetime(self) -> datetime:
        parsed = self._parse_timestamp(self._now())
        return parsed or datetime.now(UTC)

    def _worker_id(self, worker_id: Optional[str] = None) -> str:
        text = str(worker_id or "").strip()
        if text:
            return text[:120]
        return f"{socket.gethostname()}:outbox"[:120]

    def claim(self, event_id: Any, *, worker_id: Optional[str] = None, lease_seconds: int = 300) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = self._now()
        now_dt = self._now_datetime()
        lease_cutoff = now_dt - timedelta(seconds=max(1, int(lease_seconds or 300)))
        normalized_worker = self._worker_id(worker_id)
        with self.db.transaction("IMMEDIATE") as conn:
            row = conn.execute(
                """SELECT status, available_at, next_attempt_at, locked_at
                   FROM outbox_events WHERE id = ?""",
                (int(parsed_event_id),),
            ).fetchone()
            if not row:
                return False
            status = str(row["status"] or "").strip().lower()
            if status in {"delivered", "failed", "dead_letter"}:
                return False
            if status not in {"pending", "processing"}:
                return False
            available_at = self._parse_timestamp(row["available_at"]) or self._parse_timestamp(row["next_attempt_at"])
            if available_at is not None and available_at > now_dt:
                return False
            locked_at = self._parse_timestamp(row["locked_at"])
            if status == "processing" and locked_at is not None and locked_at > lease_cutoff:
                return False
            cur = conn.execute(
                """UPDATE outbox_events
                   SET status = 'processing',
                       locked_at = ?,
                       locked_by = ?,
                       updated_at = ?
                   WHERE id = ?
                     AND status IN ('pending', 'processing')""",
                (timestamp, normalized_worker, timestamp, int(parsed_event_id)),
            )
            return cur.rowcount == 1

    def claim_available(self, *, limit: int = 25, worker_id: Optional[str] = None, lease_seconds: int = 300) -> list[int]:
        now_dt = self._now_datetime()
        timestamp = self._now()
        lease_cutoff = now_dt - timedelta(seconds=max(1, int(lease_seconds or 300)))
        normalized_worker = self._worker_id(worker_id)
        claimed: list[int] = []
        with self.db.transaction("IMMEDIATE") as conn:
            rows = conn.execute(
                """SELECT id, status, available_at, next_attempt_at, locked_at
                   FROM outbox_events
                   WHERE status IN ('pending', 'processing')
                   ORDER BY COALESCE(available_at, next_attempt_at, created_at), id
                   LIMIT ?""",
                (max(1, int(limit or 25)),),
            ).fetchall()
            for row in rows:
                status = str(row["status"] or "").strip().lower()
                available_at = self._parse_timestamp(row["available_at"]) or self._parse_timestamp(row["next_attempt_at"])
                if available_at is not None and available_at > now_dt:
                    continue
                locked_at = self._parse_timestamp(row["locked_at"])
                if status == "processing" and locked_at is not None and locked_at > lease_cutoff:
                    continue
                cur = conn.execute(
                    """UPDATE outbox_events
                       SET status = 'processing',
                           locked_at = ?,
                           locked_by = ?,
                           updated_at = ?
                       WHERE id = ? AND status IN ('pending', 'processing')""",
                    (timestamp, normalized_worker, timestamp, int(row["id"])),
                )
                if cur.rowcount == 1:
                    claimed.append(int(row["id"]))
        return claimed

    def mark_succeeded(self, event_id: Any) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = self._now()
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'delivered',
                    delivered_at = ?,
                    updated_at = ?,
                    next_attempt_at = NULL,
                    available_at = NULL,
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error_code = NULL,
                    last_error = NULL
                WHERE id = ?
                """,
                (timestamp, timestamp, int(parsed_event_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def _clean_error(error: Any) -> str:
        return redact_secrets(str(error or "")).strip()[:1000] or "unknown_error"

    def mark_failed(self, event_id: Any, error: Any, *, error_code: Optional[str] = None) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = self._now()
        clean_error = self._clean_error(error)
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'failed',
                    attempts = COALESCE(attempts, 0) + 1,
                    next_attempt_at = NULL,
                    available_at = NULL,
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error_code = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (str(error_code or "delivery_failed").strip()[:120], clean_error, timestamp, int(parsed_event_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_dead_letter(self, event_id: Any, error: Any, *, error_code: Optional[str] = None) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = self._now()
        clean_error = self._clean_error(error)
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'dead_letter',
                    attempts = COALESCE(attempts, 0) + 1,
                    next_attempt_at = NULL,
                    available_at = NULL,
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error_code = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (str(error_code or "dead_letter").strip()[:120], clean_error, timestamp, int(parsed_event_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def retry_delay_seconds(attempts: Any, *, base_seconds: int = 30, max_seconds: int = 1800) -> int:
        parsed_attempts = parse_int(attempts) or 0
        exponent = max(0, min(8, parsed_attempts))
        return max(1, min(int(max_seconds), int(base_seconds) * (2 ** exponent)))

    def _timestamp_after(self, seconds: int) -> str:
        try:
            current = datetime.fromisoformat(str(self._now()).replace("Z", "+00:00"))
        except ValueError:
            current = datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return (current + timedelta(seconds=max(1, int(seconds)))).isoformat()

    def mark_retryable_failure(
        self,
        event_id: Any,
        error: Any,
        *,
        delay_seconds: Optional[int] = None,
        error_code: Optional[str] = None,
        max_attempts: Optional[int] = None,
    ) -> bool:
        """Record a redacted failure and schedule the event for a later explicit retry.

        This only mutates delivery state; callers still decide whether retrying an
        event type is safe. It must not be used to blindly re-post Discord messages.
        """
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = self._now()
        clean_error = self._clean_error(error)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT attempts FROM outbox_events WHERE id = ?",
                (int(parsed_event_id),),
            ).fetchone()
            attempts = parse_int(row["attempts"] if row else None) or 0
            next_attempt_count = attempts + 1
            effective_max_attempts = max(1, int(max_attempts or self.DEFAULT_MAX_ATTEMPTS))
            if next_attempt_count >= effective_max_attempts:
                cur = conn.execute(
                    """
                    UPDATE outbox_events
                    SET status = 'dead_letter',
                        attempts = ?,
                        next_attempt_at = NULL,
                        available_at = NULL,
                        locked_at = NULL,
                        locked_by = NULL,
                        last_error_code = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        next_attempt_count,
                        str(error_code or "max_attempts_exceeded").strip()[:120],
                        clean_error,
                        timestamp,
                        int(parsed_event_id),
                    ),
                )
                conn.commit()
                return cur.rowcount > 0
            next_attempt_at = self._timestamp_after(
                delay_seconds if delay_seconds is not None else self.retry_delay_seconds(attempts)
            )
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'pending',
                    attempts = COALESCE(attempts, 0) + 1,
                    next_attempt_at = ?,
                    available_at = ?,
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error_code = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_attempt_at,
                    next_attempt_at,
                    str(error_code or "retryable_delivery_failure").strip()[:120],
                    clean_error,
                    timestamp,
                    int(parsed_event_id),
                ),
            )
            conn.commit()
            return cur.rowcount > 0
