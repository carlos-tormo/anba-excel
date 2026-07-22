import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.db_helpers import connect_test_db

from app.server import CURRENT_SCHEMA_VERSION, LeagueDB
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> None:
    now = now_iso()
    conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, now, now),
    )


class MigrationBackupDisciplineTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-maintenance-", suffix=".db")
        os.close(fd)
        self.db_path = Path(path)
        conn = connect_test_db(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            conn.commit()
        finally:
            conn.close()
        self.db = LeagueDB(str(self.db_path))

    def tearDown(self) -> None:
        shutil.rmtree(self.db_path.parent / "backups", ignore_errors=True)
        try:
            self.db_path.unlink()
        except FileNotFoundError:
            pass

    def test_schema_migration_ledger_is_written_on_startup(self) -> None:
        self.db.ensure_auth_schema()
        status = self.db.maintenance_status()

        self.assertEqual(CURRENT_SCHEMA_VERSION, status["schema_version"])
        migrations = status["schema_migrations"]
        self.assertTrue(migrations)
        latest = migrations[0]
        self.assertEqual("success", latest["status"])
        self.assertEqual(CURRENT_SCHEMA_VERSION, latest["schema_version"])
        self.assertIn("schema_signature", latest["details"])

    def test_legacy_outbox_table_is_upgraded_before_delivery_index_creation(self) -> None:
        timestamp = now_iso()
        conn = connect_test_db(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    aggregate_type TEXT,
                    aggregate_id TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivered_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO outbox_events (
                    event_type, aggregate_type, aggregate_id, idempotency_key,
                    payload_json, status, attempts, next_attempt_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "discord.trade",
                    "trade",
                    "legacy-1",
                    "legacy-outbox-1",
                    "{}",
                    "pending",
                    0,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.db.ensure_auth_schema()

        conn = connect_test_db(self.db_path)
        try:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(outbox_events)").fetchall()
            }
            indexes = {
                row["name"]
                for row in conn.execute("PRAGMA index_list(outbox_events)").fetchall()
            }
            row = conn.execute(
                "SELECT available_at, locked_at, locked_by, last_error_code FROM outbox_events WHERE idempotency_key = ?",
                ("legacy-outbox-1",),
            ).fetchone()
        finally:
            conn.close()

        self.assertIn("available_at", columns)
        self.assertIn("locked_at", columns)
        self.assertIn("locked_by", columns)
        self.assertIn("last_error_code", columns)
        self.assertIn("idx_outbox_events_delivery_available", indexes)
        self.assertEqual(timestamp, row["available_at"])

    def test_legacy_trade_archive_movements_gain_optional_gm_name(self) -> None:
        conn = connect_test_db(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_trade_id TEXT UNIQUE,
                    trade_date TEXT NOT NULL,
                    season_year INTEGER NOT NULL,
                    total_assets_moved INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'manual',
                    source_ref TEXT UNIQUE,
                    notes TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_archive_team_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER NOT NULL REFERENCES trade_archive(id) ON DELETE CASCADE,
                    team_code TEXT NOT NULL,
                    team_name TEXT,
                    sent_json TEXT NOT NULL DEFAULT '{}',
                    received_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(trade_id, team_code)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

        self.db.ensure_auth_schema()

        conn = connect_test_db(self.db_path)
        try:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(trade_archive_team_movements)").fetchall()
            }
        finally:
            conn.close()

        self.assertIn("gm_name", columns)

    def test_verified_backup_is_persisted_and_restorable(self) -> None:
        self.db.ensure_auth_schema()
        backup = self.db.create_verified_backup("pre_test_import")

        path = Path(backup["path"])
        self.assertTrue(path.exists())
        self.assertGreater(backup["bytes"], 0)
        self.assertEqual("ok", backup["integrity_check"].lower())
        self.assertEqual(64, len(backup["sha256"]))

        conn = connect_test_db(path)
        try:
            team_count = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(1, team_count)

        backups = self.db.maintenance_status()["backups"]
        self.assertTrue(any(row["id"] == backup["id"] for row in backups))


if __name__ == "__main__":
    unittest.main()
