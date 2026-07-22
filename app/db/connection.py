"""SQLite connection creation and explicit transaction boundaries."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
import time
from typing import Callable, ContextManager, Iterator

try:
    from ..observability.operations import record_db_query
except ImportError:  # pragma: no cover
    from observability.operations import record_db_query


class ClosingSQLiteConnection(sqlite3.Connection):
    """Connection whose context manager always closes after commit/rollback."""

    def execute(self, sql, parameters=(), /):  # type: ignore[override]
        started = time.perf_counter()
        try:
            return super().execute(sql, parameters)
        finally:
            record_db_query(sql, time.perf_counter() - started)

    def executemany(self, sql, parameters, /):  # type: ignore[override]
        started = time.perf_counter()
        try:
            return super().executemany(sql, parameters)
        finally:
            record_db_query(sql, time.perf_counter() - started)

    def executescript(self, sql_script, /):  # type: ignore[override]
        started = time.perf_counter()
        try:
            return super().executescript(sql_script)
        finally:
            record_db_query("SCRIPT", time.perf_counter() - started)

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=15.0, factory=ClosingSQLiteConnection)
    conn.row_factory = sqlite3.Row
    # Connection setup is infrastructure, not application workflow querying.
    # Bypass the instrumented execute override so per-route query budgets do
    # not count PRAGMAs required for safe SQLite operation.
    sqlite3.Connection.execute(conn, "PRAGMA foreign_keys = ON")
    sqlite3.Connection.execute(conn, "PRAGMA busy_timeout = 15000")
    sqlite3.Connection.execute(conn, "PRAGMA synchronous = NORMAL")
    if str(db_path or "") != ":memory:":
        sqlite3.Connection.execute(conn, "PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction_context(
    connect: Callable[[], sqlite3.Connection],
    mode: str = "IMMEDIATE",
) -> Iterator[sqlite3.Connection]:
    normalized_mode = str(mode or "IMMEDIATE").strip().upper()
    if normalized_mode not in {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}:
        raise ValueError("invalid_transaction_mode")
    conn = connect()
    try:
        conn.execute(f"BEGIN {normalized_mode}")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class DatabaseConnectionMixin:
    db_path: str

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    def transaction(self, mode: str = "IMMEDIATE") -> ContextManager[sqlite3.Connection]:
        return transaction_context(self.connect, mode)
