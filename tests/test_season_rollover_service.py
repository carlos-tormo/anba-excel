import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.services.season_rollover import SeasonRolloverService
from app.xlsx_import import create_schema, now_iso


class SeasonRolloverServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(
            prefix="anba-season-rollover-service-", suffix=".db"
        )
        os.close(descriptor)
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO teams (
                    code, name, gm, cash_note, apron_hard_cap,
                    salary_cap, luxury_cap, first_apron, second_apron,
                    created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', NULL, NULL, NULL,
                    154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            )
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        self.db.update_setting("current_year", "2025")
        self.service = SeasonRolloverService(
            self.db,
            contract_min_year=2025,
            contract_max_start_year=2026,
        )

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def snapshot_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM season_snapshots").fetchone()
            return int(row["count"])

    def test_progress_commits_snapshot_and_year_together(self) -> None:
        result = self.service.progress_to_next_year()

        self.assertEqual(2026, result["current_year"])
        self.assertEqual("2026", self.db.get_settings()["current_year"])
        self.assertEqual(1, self.snapshot_count())

    def test_failure_rolls_back_snapshot_and_year_change(self) -> None:
        with mock.patch.object(
            self.service.repository,
            "rollover_draft_assets",
            side_effect=RuntimeError("forced_rollover_failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "forced_rollover_failure"):
                self.service.progress_to_next_year()

        self.assertEqual("2025", self.db.get_settings()["current_year"])
        self.assertEqual(0, self.snapshot_count())


if __name__ == "__main__":
    unittest.main()
