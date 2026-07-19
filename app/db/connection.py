"""SQLite connection creation and explicit transaction boundaries."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Callable, ContextManager, Iterator


class ClosingSQLiteConnection(sqlite3.Connection):
    """Connection whose context manager always closes after commit/rollback."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=15.0, factory=ClosingSQLiteConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA synchronous = NORMAL")
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
