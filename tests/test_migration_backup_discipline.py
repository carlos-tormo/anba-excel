import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

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
        conn = sqlite3.connect(self.db_path)
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

    def test_verified_backup_is_persisted_and_restorable(self) -> None:
        self.db.ensure_auth_schema()
        backup = self.db.create_verified_backup("pre_test_import")

        path = Path(backup["path"])
        self.assertTrue(path.exists())
        self.assertGreater(backup["bytes"], 0)
        self.assertEqual("ok", backup["integrity_check"].lower())
        self.assertEqual(64, len(backup["sha256"]))

        conn = sqlite3.connect(path)
        try:
            team_count = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(1, team_count)

        backups = self.db.maintenance_status()["backups"]
        self.assertTrue(any(row["id"] == backup["id"] for row in backups))


if __name__ == "__main__":
    unittest.main()
