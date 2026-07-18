"""SQLite persistence for authenticated sessions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable, ContextManager, Dict, Optional

try:
    from ...auth.sessions import session_token_digest
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.sessions import session_token_digest

ConnectionFactory = Callable[[], ContextManager[sqlite3.Connection]]


def create_session(
    connect: ConnectionFactory,
    token: str,
    payload: Dict[str, Any],
    created_at: str,
    expires_at: int,
) -> bool:
    token_hash = session_token_digest(token)
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO sessions (session_token, session_token_hash, data_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_hash, token_hash, json.dumps(payload, ensure_ascii=True), created_at, int(expires_at)),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_session(
    connect: ConnectionFactory,
    token: str,
    now_ts: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    token_hash = session_token_digest(token)
    current_ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
    with connect() as conn:
        row = conn.execute(
            """
            SELECT session_token, data_json, expires_at
            FROM sessions
            WHERE session_token_hash = ? OR session_token = ? OR session_token = ?
            LIMIT 1
            """,
            (token_hash, token_hash, token),
        ).fetchone()
        if not row or int(row["expires_at"] or 0) <= current_ts:
            return None
        try:
            payload = json.loads(str(row["data_json"] or "{}"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None


def delete_session(connect: ConnectionFactory, token: str) -> None:
    if not token:
        return
    token_hash = session_token_digest(token)
    with connect() as conn:
        conn.execute(
            """
            DELETE FROM sessions
            WHERE session_token_hash = ? OR session_token = ? OR session_token = ?
            """,
            (token_hash, token_hash, token),
        )
        conn.commit()


def cleanup_expired_sessions(
    connect: ConnectionFactory,
    cleanup_lock: Lock,
    now_ts: Optional[int] = None,
) -> int:
    current_ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
    if not cleanup_lock.acquire(blocking=False):
        return 0
    try:
        with connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (current_ts,))
            conn.commit()
            return int(cur.rowcount or 0)
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise
        print(f"Session cleanup skipped: {exc}", flush=True)
        return 0
    finally:
        cleanup_lock.release()
