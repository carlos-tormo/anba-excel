import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

from app.db.connection import DatabaseConnectionMixin, connect_sqlite
from app.db.maintenance import DatabaseMaintenanceMixin
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories import sessions as session_repository
from app.routes import GET_ROUTES
from app.routing import dispatch_routes
from app.services.outbox_delivery import OutboxDeliveryService


class ContentionDB(DatabaseConnectionMixin):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path


class MaintenanceDB(DatabaseMaintenanceMixin):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path


class PublicTrackerReads:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def list(self, season_year=None):
        selected_year = int(season_year or 2027)
        with connect_sqlite(self.db_path) as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT team_code, cap_total
                    FROM tracker_rows
                    WHERE season_year = ?
                    ORDER BY team_code
                    """,
                    (selected_year,),
                ).fetchall()
            ]
        return {
            "rows": rows,
            "season_year": selected_year,
            "seasons": [2027, 2028],
            "timings": {"row_count": float(len(rows))},
        }


def now_iso() -> str:
    return "2026-07-22T10:00:00+00:00"


def create_contention_db() -> str:
    descriptor, db_path = tempfile.mkstemp(prefix="anba-sqlite-contention-", suffix=".db")
    os.close(descriptor)
    with connect_sqlite(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tracker_rows (
                team_code TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                cap_total REAL NOT NULL
            );
            CREATE TABLE mutations (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL
            );
            CREATE TABLE trade_runs (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL
            );
            CREATE TABLE outbox_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                aggregate_type TEXT,
                aggregate_id TEXT,
                idempotency_key TEXT UNIQUE,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                available_at TEXT,
                locked_at TEXT,
                locked_by TEXT,
                last_error_code TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                delivered_at TEXT
            );
            CREATE TABLE admin_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reason TEXT NOT NULL,
                path TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                integrity_check TEXT NOT NULL,
                created_at TEXT NOT NULL,
                verified_at TEXT NOT NULL
            );
            CREATE TABLE sessions (
                session_token TEXT PRIMARY KEY,
                session_token_hash TEXT UNIQUE,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
            """
        )
        conn.executemany(
            "INSERT INTO tracker_rows (team_code, season_year, cap_total) VALUES (?, ?, ?)",
            [
                (f"T{team:02d}", season, 150_000_000 + team)
                for team in range(1, 31)
                for season in (2027, 2028)
            ],
        )
        conn.executemany(
            "INSERT INTO mutations (id, status) VALUES (?, 'pending')",
            [(1,), (2,)],
        )
        conn.execute("INSERT INTO trade_runs (id, status) VALUES (1, 'pending')")
        conn.executemany(
            """
            INSERT INTO sessions (session_token, session_token_hash, data_json, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("expired", "expired", json.dumps({"role": "gm"}), now_iso(), 1_000),
                ("active", "active", json.dumps({"role": "gm"}), now_iso(), 4_102_444_800),
            ],
        )
        conn.commit()
    return db_path


def remove_sqlite_files(db_path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(f"{db_path}{suffix}").unlink()
        except FileNotFoundError:
            pass


class SQLiteContentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = create_contention_db()
        self.db = ContentionDB(self.db_path)

    def tearDown(self) -> None:
        remove_sqlite_files(self.db_path)

    def test_file_backed_connections_enable_wal_and_busy_timeout(self) -> None:
        with connect_sqlite(self.db_path) as conn:
            journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            busy_timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])

        self.assertEqual("wal", journal_mode)
        self.assertEqual(15_000, busy_timeout)

    def test_several_simultaneous_public_tracker_requests_are_read_only(self) -> None:
        def request_tracker():
            handler = SimpleNamespace(
                _send_route_response=Mock(),
                log_message=Mock(),
                app=SimpleNamespace(tracker=PublicTrackerReads(self.db_path)),
            )
            matched = dispatch_routes(handler, urlparse("/api/tracker?season=2027"), GET_ROUTES)
            response = handler._send_route_response.call_args.args[0]
            return matched, response.status, len(response.payload["tracker"])

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = [future.result(timeout=5) for future in [pool.submit(request_tracker) for _ in range(8)]]

        self.assertEqual([(True, 200, 30)] * 8, results)
        with connect_sqlite(self.db_path) as conn:
            self.assertEqual(60, conn.execute("SELECT COUNT(*) FROM tracker_rows").fetchone()[0])
            self.assertEqual(0, conn.total_changes)

    def test_offer_acceptance_commit_succeeds_while_tracker_read_transaction_is_open(self) -> None:
        reader_ready = threading.Event()
        release_reader = threading.Event()

        def hold_tracker_read():
            with connect_sqlite(self.db_path) as conn:
                conn.execute("BEGIN")
                count = conn.execute("SELECT COUNT(*) FROM tracker_rows").fetchone()[0]
                reader_ready.set()
                self.assertTrue(release_reader.wait(timeout=5))
                conn.rollback()
                return count

        def accept_offer():
            self.assertTrue(reader_ready.wait(timeout=5))
            with connect_sqlite(self.db_path) as conn:
                sqlite3.Connection.execute(conn, "PRAGMA busy_timeout = 250")
                conn.execute("UPDATE mutations SET status = 'accepted' WHERE id = 1")
                conn.commit()
            return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(hold_tracker_read)
            writer = pool.submit(accept_offer)
            self.assertTrue(writer.result(timeout=2))
            release_reader.set()
            self.assertEqual(60, reader.result(timeout=2))

        with connect_sqlite(self.db_path) as conn:
            self.assertEqual("accepted", conn.execute("SELECT status FROM mutations WHERE id = 1").fetchone()[0])

    def test_two_administrators_processing_different_mutations_serialize_with_busy_timeout(self) -> None:
        first_holding_lock = threading.Event()
        release_first = threading.Event()

        def update_first():
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("UPDATE mutations SET status = 'processed' WHERE id = 1")
                first_holding_lock.set()
                self.assertTrue(release_first.wait(timeout=5))
            return 1

        def update_second():
            self.assertTrue(first_holding_lock.wait(timeout=5))
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("UPDATE mutations SET status = 'processed' WHERE id = 2")
            return 2

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(update_first)
            second = pool.submit(update_second)
            self.assertTrue(first_holding_lock.wait(timeout=5))
            time.sleep(0.05)
            release_first.set()
            self.assertEqual(1, first.result(timeout=5))
            self.assertEqual(2, second.result(timeout=5))

        with connect_sqlite(self.db_path) as conn:
            statuses = {
                int(row["id"]): str(row["status"])
                for row in conn.execute("SELECT id, status FROM mutations ORDER BY id").fetchall()
            }
        self.assertEqual({1: "processed", 2: "processed"}, statuses)

    def test_outbox_delivery_waits_for_trade_commit_before_external_call(self) -> None:
        delivery_calls = []
        trade_inserted = threading.Event()
        release_trade = threading.Event()
        outbox = OutboxRepository(self.db, now=now_iso)
        delivery = OutboxDeliveryService(
            outbox,
            players=SimpleNamespace(record=Mock()),
            deliver_notification=lambda *_args, **_kwargs: delivery_calls.append("external") or True,
            worker_id="test-worker",
        )

        def commit_trade_with_outbox():
            payload = json.dumps({"result": {"summary": "Trade processed"}}, ensure_ascii=True)
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("UPDATE trade_runs SET status = 'processed' WHERE id = 1")
                conn.execute(
                    """
                    INSERT INTO outbox_events (
                        event_type, aggregate_type, aggregate_id, idempotency_key, payload_json,
                        status, attempts, available_at, created_at, updated_at
                    ) VALUES (
                        'discord.trade_processed', 'trade', '1', 'trade:1', ?,
                        'pending', 0, ?, ?, ?
                    )
                    """,
                    (payload, now_iso(), now_iso(), now_iso()),
                )
                trade_inserted.set()
                self.assertTrue(release_trade.wait(timeout=5))
            return True

        def dispatch_outbox():
            self.assertTrue(trade_inserted.wait(timeout=5))
            return delivery.dispatch([1])

        with ThreadPoolExecutor(max_workers=2) as pool:
            trade = pool.submit(commit_trade_with_outbox)
            dispatched = pool.submit(dispatch_outbox)
            self.assertTrue(trade_inserted.wait(timeout=5))
            time.sleep(0.05)
            self.assertEqual([], delivery_calls)
            release_trade.set()
            self.assertTrue(trade.result(timeout=5))
            self.assertEqual([1], dispatched.result(timeout=5))

        self.assertEqual(["external"], delivery_calls)

    def test_backup_can_run_while_normal_read_transaction_is_open(self) -> None:
        maintenance = MaintenanceDB(self.db_path)
        reader_ready = threading.Event()
        release_reader = threading.Event()

        def hold_normal_read():
            with connect_sqlite(self.db_path) as conn:
                conn.execute("BEGIN")
                count = conn.execute("SELECT COUNT(*) FROM tracker_rows").fetchone()[0]
                reader_ready.set()
                self.assertTrue(release_reader.wait(timeout=5))
                conn.rollback()
                return count

        def create_backup():
            self.assertTrue(reader_ready.wait(timeout=5))
            return maintenance.create_verified_backup("contention_test")

        with ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(hold_normal_read)
            backup = pool.submit(create_backup)
            result = backup.result(timeout=5)
            release_reader.set()
            self.assertEqual(60, reader.result(timeout=2))

        self.assertEqual("ok", str(result.get("integrity_check")).lower())
        Path(str(result["path"])).unlink(missing_ok=True)

    def test_session_cleanup_can_run_while_users_authenticate(self) -> None:
        cleanup_lock = threading.Lock()

        def connect():
            return connect_sqlite(self.db_path)

        def authenticate(index: int):
            token = f"active-{index}"
            created = session_repository.create_session(
                connect,
                token,
                {"role": "gm", "index": index},
                now_iso(),
                4_102_444_800,
            )
            payload = session_repository.get_session(connect, token, now_ts=1_800_000_000)
            return created, payload

        with ThreadPoolExecutor(max_workers=6) as pool:
            cleanup = pool.submit(session_repository.cleanup_expired_sessions, connect, cleanup_lock, 2_000)
            auth_results = [pool.submit(authenticate, index) for index in range(5)]
            cleaned = cleanup.result(timeout=5)
            results = [future.result(timeout=5) for future in auth_results]

        self.assertEqual(1, cleaned)
        self.assertTrue(all(created and payload and payload["role"] == "gm" for created, payload in results))
        with connect_sqlite(self.db_path) as conn:
            self.assertEqual(6, conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
