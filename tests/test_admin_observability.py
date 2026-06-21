import os
import sqlite3
import tempfile
import unittest

from app.server import LeagueDB
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> int:
    now = now_iso()
    cur = conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195946000, 207825000, ?, ?)
        """,
        (code, name, now, now),
    )
    return int(cur.lastrowid)


class AdminObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-admin-observability-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            insert_team(conn, "BOS", "Boston Celtics")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_admin_log_keeps_correlation_and_structured_snapshots(self) -> None:
        self.db.log_admin_action(
            actor_email="admin@example.com",
            actor_name="Admin",
            actor_role="admin",
            actor_user_id=7,
            request_id="req-trade-1",
            method="POST",
            path="/api/trades/process",
            action="trade",
            entity="trade",
            team_codes=["ATL", "BOS"],
            player_id="15",
            profile_id="44",
            before={"players": [{"id": 15, "team_code": "ATL"}]},
            after={"players": [{"id": 15, "team_code": "BOS"}]},
            details={"trade_bucket": "pre30"},
        )

        rows = self.db.list_admin_logs()
        self.assertEqual(1, len(rows))
        log = rows[0]
        self.assertEqual("req-trade-1", log["request_id"])
        self.assertEqual("POST", log["method"])
        self.assertEqual("/api/trades/process", log["path"])
        self.assertEqual("admin", log["actor_role"])
        self.assertEqual(7, log["actor_user_id"])
        self.assertEqual(["ATL", "BOS"], log["team_codes"])
        self.assertEqual("15", log["player_id"])
        self.assertEqual("44", log["profile_id"])
        self.assertEqual("ATL", log["before"]["players"][0]["team_code"])
        self.assertEqual("BOS", log["after"]["players"][0]["team_code"])
        self.assertEqual("pre30", log["details"]["trade_bucket"])

    def test_existing_admin_logs_table_is_migrated(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DROP TABLE admin_logs")
            conn.execute(
                """
                CREATE TABLE admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    actor_email TEXT,
                    actor_name TEXT,
                    action TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    entity_id TEXT,
                    team_code TEXT,
                    details_json TEXT
                )
                """
            )
            conn.commit()

        self.db.ensure_auth_schema()

        with self.db.connect() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(admin_logs)").fetchall()}
        for col in [
            "actor_role",
            "actor_user_id",
            "request_id",
            "method",
            "path",
            "team_codes_json",
            "player_id",
            "profile_id",
            "before_json",
            "after_json",
        ]:
            self.assertIn(col, cols)


if __name__ == "__main__":
    unittest.main()
