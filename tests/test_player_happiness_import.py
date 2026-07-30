import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.db.repositories.player_happiness import PlayerHappinessRepository
from app.server import LeagueDB
from app.services.player_happiness import PlayerHappinessService
from app.xlsx_import import create_schema, now_iso


class PlayerHappinessImportTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(prefix="anba-player-happiness-", suffix=".db")
        os.close(descriptor)
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO users (id, email, display_name, created_at, updated_at)
                VALUES (42, 'admin@example.test', 'Admin', ?, ?)
                """,
                (timestamp, timestamp),
            )
            self.jokic_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, created_at, updated_at)
                VALUES ('Nikola Jokic', 1.5, ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            self.duplicate_a_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, created_at, updated_at)
                VALUES ('Duplicate Player', 0, ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            self.duplicate_b_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, created_at, updated_at)
                VALUES ('Duplicate Player', 2, ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            conn.commit()
        self.service = PlayerHappinessService(PlayerHappinessRepository(self.db), now=now_iso)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_preview_matches_by_name_and_profile_id(self) -> None:
        preview = self.service.preview({
            "players": [
                {"player_name": "Nikola Jokić", "happiness": 7.5},
                {"profile_id": self.duplicate_a_id, "player_name": "Duplicate Player", "happiness": -1},
                {"player_name": "Missing Player", "happiness": 3},
            ]
        })

        self.assertTrue(preview["ok"])
        self.assertEqual(2, preview["summary"]["matched_count"])
        self.assertEqual(1, preview["summary"]["unmatched_count"])
        by_id = {record["profile_id"]: record for record in preview["records"]}
        self.assertEqual(7.5, by_id[self.jokic_id]["new_happiness"])
        self.assertEqual("name", by_id[self.jokic_id]["match_method"])
        self.assertEqual(-1, by_id[self.duplicate_a_id]["new_happiness"])
        self.assertEqual("profile_id", by_id[self.duplicate_a_id]["match_method"])

    def test_preview_blocks_ambiguous_name_matches(self) -> None:
        preview = self.service.preview({"players": [{"player_name": "Duplicate Player", "happiness": 5}]})

        self.assertFalse(preview["ok"])
        self.assertEqual(1, preview["summary"]["ambiguous_count"])
        self.assertEqual(2, len(preview["ambiguous"][0]["matches"]))

    def test_apply_updates_profile_and_creates_baseline_event(self) -> None:
        preview = self.service.preview({"players": [{"player_name": "Nikola Jokic", "happiness": 7.5}]})

        result = self.service.apply(preview["records"], {"user_id": 42})

        self.assertTrue(result["ok"])
        self.assertEqual(1, result["record_count"])
        self.assertEqual(1, result["changed_count"])
        self.assertEqual("valid", result["validation_result"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            profile = conn.execute(
                "SELECT happiness, version FROM player_profiles WHERE id = ?",
                (self.jokic_id,),
            ).fetchone()
            event = conn.execute(
                """
                SELECT event_type, previous_value, applied_delta, new_value, actor_user_id, command_id
                FROM player_happiness_events
                WHERE profile_id = ?
                """,
                (self.jokic_id,),
            ).fetchone()
        self.assertEqual(7.5, profile["happiness"])
        self.assertEqual(2, profile["version"])
        self.assertEqual("baseline_import", event["event_type"])
        self.assertEqual(1.5, event["previous_value"])
        self.assertEqual(6.0, event["applied_delta"])
        self.assertEqual(7.5, event["new_value"])
        self.assertEqual(42, event["actor_user_id"])
        self.assertEqual(result["command_id"], event["command_id"])

    def test_apply_rejects_stale_version(self) -> None:
        preview = self.service.preview({"players": [{"player_name": "Nikola Jokic", "happiness": 7.5}]})
        with connect_test_db(self.db_path) as conn:
            conn.execute("UPDATE player_profiles SET version = version + 1 WHERE id = ?", (self.jokic_id,))
            conn.commit()

        with self.assertRaisesRegex(ValueError, "stale_entity_version"):
            self.service.apply(preview["records"], {"user_id": 42})
