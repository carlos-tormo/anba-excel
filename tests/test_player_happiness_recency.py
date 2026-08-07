import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.xlsx_import import create_schema, now_iso


class PlayerHappinessRecencyTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(
            prefix="anba-player-happiness-recency-", suffix=".db"
        )
        os.close(descriptor)
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        timestamp = now_iso()
        with self.db.transaction("IMMEDIATE") as conn:
            conn.execute(
                """
                INSERT INTO player_profiles (
                    name, happiness, profile_status, version, created_at, updated_at
                ) VALUES ('Test Player', 8, 'active', 1, ?, ?)
                """,
                (timestamp, timestamp),
            )
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('current_year', '2026', ?)",
                (timestamp,),
            )

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_recalculate_recency_updates_cached_profile_happiness_from_ledger(self) -> None:
        timestamp = now_iso()
        with self.db.transaction("IMMEDIATE") as conn:
            profile_id = int(conn.execute("SELECT id FROM player_profiles").fetchone()["id"])
            conn.execute(
                """
                INSERT INTO player_happiness_events (
                    profile_id, event_type, event_date, season_year,
                    previous_value, proposed_delta, applied_delta, new_value,
                    source_entity_type, source_entity_id, reason, metadata_json,
                    command_id, actor_user_id, created_at
                ) VALUES
                    (?, 'baseline_import', NULL, 2024, 0, 7, 7, 7, 'test', 'baseline', 'baseline', '{}', 'baseline', NULL, ?),
                    (?, 'modifier', NULL, 2026, 7, 2, 2, 9, 'test', 'current', 'current', '{}', 'current', NULL, ?),
                    (?, 'gm_change', NULL, 2025, 9, -1, -1, 8, 'test', 'last', 'last', '{}', 'last', NULL, ?)
                """,
                (profile_id, timestamp, profile_id, timestamp, profile_id, timestamp),
            )

        result = self.db._player_happiness_service.recalculate_recency(current_year=2026)

        self.assertEqual(1, result["updated_count"])
        self.assertAlmostEqual(8.05, result["updated_profiles"][0]["new_happiness"])
        with self.db.connect() as conn:
            row = conn.execute("SELECT happiness FROM player_profiles WHERE id = ?", (profile_id,)).fetchone()
        self.assertAlmostEqual(8.05, float(row["happiness"]))


if __name__ == "__main__":
    unittest.main()
