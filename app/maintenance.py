import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CURRENT_SCHEMA_VERSION = 2026062101
CURRENT_SCHEMA_MIGRATION_KEY = f"{CURRENT_SCHEMA_VERSION}_runtime_schema_contract"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
    return {cursor.description[idx][0]: row[idx] for idx in range(len(cursor.description))}


class ClosingSQLiteConnection(sqlite3.Connection):
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
    return conn


class DatabaseMaintenanceMixin:
    db_path: str

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    def backup_dir(self) -> Path:
        configured = str(os.getenv("BACKUP_DIR") or "").strip()
        if configured:
            return Path(configured).expanduser()
        return Path(self.db_path).resolve().parent / "backups"

    def _ensure_maintenance_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_key TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migration_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_key TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reason TEXT NOT NULL,
                path TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                integrity_check TEXT NOT NULL,
                created_at TEXT NOT NULL,
                verified_at TEXT NOT NULL
            )
            """
        )

    def _schema_signature(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        tables = [
            str(row["name"])
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]
        return {
            "tables": {
                table: [
                    {"name": str(col["name"]), "type": str(col["type"] or "")}
                    for col in conn.execute(f"PRAGMA table_info({table})").fetchall()
                ]
                for table in tables
            }
        }

    def _record_schema_migration(
        self,
        conn: sqlite3.Connection,
        migration_key: str,
        description: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        timestamp = now_iso()
        details_json = json.dumps(details or {}, ensure_ascii=True, sort_keys=True)
        conn.execute(
            """
            INSERT INTO schema_migrations (
                migration_key, schema_version, description, status, details_json, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(migration_key) DO UPDATE SET
                schema_version = excluded.schema_version,
                description = excluded.description,
                status = excluded.status,
                details_json = excluded.details_json,
                finished_at = excluded.finished_at
            """,
            (
                migration_key,
                CURRENT_SCHEMA_VERSION,
                description,
                status,
                details_json,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """
            INSERT INTO schema_migration_events (
                migration_key, schema_version, status, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (migration_key, CURRENT_SCHEMA_VERSION, status, details_json, timestamp),
        )

    def _verify_backup_file(self, path: Path) -> str:
        with sqlite3.connect(path, factory=ClosingSQLiteConnection) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row else "")

    def create_verified_backup(self, reason: str) -> Dict[str, Any]:
        backup_dir = self.backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        safe_reason = re.sub(r"[^A-Za-z0-9._-]+", "_", str(reason or "manual")).strip("._-") or "manual"
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = backup_dir / f"anba-{safe_reason}-{timestamp}-{secrets.token_hex(4)}.db"
        try:
            with self.connect() as source:
                with sqlite3.connect(path, factory=ClosingSQLiteConnection) as target:
                    source.backup(target)
            integrity = self._verify_backup_file(path)
            if integrity.lower() != "ok":
                raise ValueError(f"backup_integrity_failed:{integrity}")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            timestamp_iso = now_iso()
            with self.connect() as conn:
                self._ensure_maintenance_schema(conn)
                cur = conn.execute(
                    """
                    INSERT INTO admin_backups (
                        reason, path, bytes, sha256, integrity_check, created_at, verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        safe_reason,
                        str(path),
                        len(data),
                        digest,
                        integrity,
                        timestamp_iso,
                        timestamp_iso,
                    ),
                )
                conn.commit()
                backup_id = int(cur.lastrowid)
            return {
                "id": backup_id,
                "reason": safe_reason,
                "path": str(path),
                "bytes": len(data),
                "sha256": digest,
                "integrity_check": integrity,
                "created_at": timestamp_iso,
                "verified_at": timestamp_iso,
            }
        except Exception:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise

    def list_admin_backups(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._ensure_maintenance_schema(conn)
            cur = conn.execute(
                """
                SELECT id, reason, path, bytes, sha256, integrity_check, created_at, verified_at
                FROM admin_backups
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            )
            return [row_to_dict(cur, row) for row in cur.fetchall()]

    def list_schema_migrations(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._ensure_maintenance_schema(conn)
            cur = conn.execute(
                """
                SELECT migration_key, schema_version, description, status, details_json, started_at, finished_at
                FROM schema_migrations
                ORDER BY schema_version DESC, migration_key DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            )
            rows = [row_to_dict(cur, row) for row in cur.fetchall()]
            for row in rows:
                try:
                    row["details"] = json.loads(row.pop("details_json") or "{}")
                except json.JSONDecodeError:
                    row["details"] = {}
            return rows

    def maintenance_status(self) -> Dict[str, Any]:
        return {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "schema_migrations": self.list_schema_migrations(),
            "backups": self.list_admin_backups(),
        }

    def backup_bytes(self) -> bytes:
        fd, tmp_path = tempfile.mkstemp(prefix="anba-backup-", suffix=".db")
        os.close(fd)
        try:
            with self.connect() as source:
                with sqlite3.connect(tmp_path, factory=ClosingSQLiteConnection) as target:
                    source.backup(target)
            with open(tmp_path, "rb") as fh:
                return fh.read()
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
