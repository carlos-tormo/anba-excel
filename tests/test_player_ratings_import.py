import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.db.repositories.player_happiness import PlayerHappinessRepository
from app.db.repositories.player_ratings import PlayerRatingImportRepository
from app.server import LeagueDB
from app.services.player_happiness import PlayerHappinessService
from app.services.player_ratings_import import PlayerRatingImportService
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> int:
    timestamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, timestamp, timestamp),
    )
    return int(cur.lastrowid)


class PlayerRatingImportTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(prefix="anba-player-ratings-", suffix=".db")
        os.close(descriptor)
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            atl_id = insert_team(conn, "ATL", "Atlanta Hawks")
            conn.execute(
                """
                INSERT INTO players (
                    team_id, row_order, bird_rights, rating, name, position,
                    years_left, created_at, updated_at
                ) VALUES (?, 1, NULL, '88', 'D''Angelo Russell', 'PG', NULL, ?, ?)
                """,
                (atl_id, now_iso(), now_iso()),
            )
            conn.execute(
                """
                INSERT INTO players (
                    team_id, row_order, bird_rights, rating, name, position,
                    years_left, created_at, updated_at
                ) VALUES (?, 2, NULL, '#N/A', 'Local Typo Name', 'SG', NULL, ?, ?)
                """,
                (atl_id, now_iso(), now_iso()),
            )
            conn.execute(
                """
                INSERT INTO free_agents (
                    name, position, bird_rights, rating, years_left, created_at, updated_at
                ) VALUES ('Nikola Jokic', 'C', NULL, '97', NULL, ?, ?)
                """,
                (now_iso(), now_iso()),
            )
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        self.service = PlayerRatingImportService(PlayerRatingImportRepository(self.db), now=now_iso)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_preview_matches_exact_normalized_names_and_reports_unmatched(self) -> None:
        payload = {
            "players": {
                "d’angelo russell": {"name": "D’Angelo Russell", "overall": 82, "team": "Atlanta Hawks"},
                "nikola jokic": {"name": "Nikola Jokic", "overall": 98, "team": "Denver Nuggets"},
                "unused player": {"name": "Unused Player", "overall": 74},
            }
        }

        preview = self.service.preview(payload)

        self.assertTrue(preview["ok"])
        self.assertEqual(2, preview["summary"]["matched_count"])
        self.assertEqual(2, preview["summary"]["changed_count"])
        self.assertEqual(1, preview["summary"]["unmatched_target_count"])
        self.assertEqual(1, preview["summary"]["unused_source_count"])
        names = {record["player_name"]: record["new_rating"] for record in preview["records"]}
        self.assertEqual(82, names["D'Angelo Russell"])
        self.assertEqual(98, names["Nikola Jokic"])
        self.assertEqual("Local Typo Name", preview["unmatched_targets"][0]["player_name"])

    def test_apply_updates_roster_and_free_agent_ratings(self) -> None:
        preview = self.service.preview({
            "players": [
                {"name": "D’Angelo Russell", "overall": 82},
                {"name": "Nikola Jokic", "overall": 98},
            ],
        })

        result = self.service.apply([record for record in preview["records"] if record["changed"]])

        self.assertTrue(result["ok"])
        self.assertEqual(2, result["record_count"])
        self.assertEqual(2, result["changed_count"])
        self.assertEqual("valid", result["validation_result"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            player = conn.execute("SELECT rating FROM players WHERE name = 'D''Angelo Russell'").fetchone()
            free_agent = conn.execute("SELECT rating FROM free_agents WHERE name = 'Nikola Jokic'").fetchone()
        self.assertEqual("82", player["rating"])
        self.assertEqual("98", free_agent["rating"])

    def test_apply_rejects_stale_target_name(self) -> None:
        preview = self.service.preview({"players": [{"name": "Nikola Jokic", "overall": 98}]})
        record = dict(preview["records"][0])
        record["player_name"] = "Wrong Name"

        with self.assertRaisesRegex(ValueError, "rating_import_target_changed"):
            self.service.apply([record])

    def test_apply_triggers_happiness_when_drafted_player_reaches_85(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            team_id = insert_team(conn, "BOS", "Boston Celtics")
            traded_team_id = insert_team(conn, "CHA", "Charlotte Hornets")
            conn.execute("UPDATE app_settings SET value = '2026' WHERE key = 'current_year'")
            drafted_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, created_at, updated_at)
                VALUES ('Drafted Rookie', 5, ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            teammate_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, created_at, updated_at)
                VALUES ('Helpful Teammate', 5, ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            traded_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, created_at, updated_at)
                VALUES ('Traded Rookie', 5, ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            drafted_player_id = int(conn.execute(
                """
                INSERT INTO players (
                    team_id, profile_id, row_order, bird_rights, rating, name, position,
                    years_left, created_at, updated_at
                ) VALUES (?, ?, 10, 'R', '84', 'Drafted Rookie', 'SF', NULL, ?, ?)
                """,
                (team_id, drafted_profile_id, timestamp, timestamp),
            ).lastrowid)
            conn.execute(
                """
                INSERT INTO players (
                    team_id, profile_id, row_order, bird_rights, rating, name, position,
                    years_left, created_at, updated_at
                ) VALUES (?, ?, 11, 'Reg', '75', 'Helpful Teammate', 'PG', NULL, ?, ?)
                """,
                (team_id, teammate_profile_id, timestamp, timestamp),
            )
            traded_player_id = int(conn.execute(
                """
                INSERT INTO players (
                    team_id, profile_id, row_order, bird_rights, rating, name, position,
                    years_left, created_at, updated_at
                ) VALUES (?, ?, 12, 'R', '84', 'Traded Rookie', 'SG', NULL, ?, ?)
                """,
                (traded_team_id, traded_profile_id, timestamp, timestamp),
            ).lastrowid)
            conn.execute(
                """
                INSERT INTO player_transactions (profile_id, action, team_code, summary, player_id, created_at)
                VALUES (?, 'create', 'BOS', 'Alta en BOS', ?, ?)
                """,
                (drafted_profile_id, drafted_player_id, timestamp),
            )
            conn.execute(
                """
                INSERT INTO player_transactions (profile_id, action, team_code, summary, created_at)
                VALUES (?, 'create', 'BOS', 'Alta en BOS', ?)
                """,
                (teammate_profile_id, timestamp),
            )
            conn.execute(
                """
                INSERT INTO player_transactions (profile_id, action, team_code, summary, player_id, created_at)
                VALUES (?, 'trade', 'CHA', 'Traspasado a CHA', ?, ?)
                """,
                (traded_profile_id, traded_player_id, timestamp),
            )
            conn.commit()
        service = PlayerRatingImportService(
            PlayerRatingImportRepository(self.db),
            now=now_iso,
            player_happiness=PlayerHappinessService(PlayerHappinessRepository(self.db), now=now_iso),
        )
        preview = service.preview({
            "players": [
                {"name": "Drafted Rookie", "overall": 85},
                {"name": "Traded Rookie", "overall": 85},
            ],
        })

        result = service.apply([record for record in preview["records"] if record["changed"]])

        self.assertEqual(1, len(result["happiness_impacts"]))
        self.assertEqual(1, result["happiness_impacts"][0]["affected_count"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            teammate = conn.execute(
                "SELECT happiness FROM player_profiles WHERE id = ?",
                (teammate_profile_id,),
            ).fetchone()
            events = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT profile_id, event_type, applied_delta, source_entity_type, metadata_json
                    FROM player_happiness_events
                    WHERE event_type = 'drafted_rating_threshold'
                    ORDER BY id
                    """
                ).fetchall()
            ]
        self.assertEqual(5.5, teammate["happiness"])
        self.assertEqual(1, len(events))
        self.assertEqual(teammate_profile_id, events[0]["profile_id"])
        self.assertEqual(0.5, events[0]["applied_delta"])
        self.assertEqual("player_rating_import", events[0]["source_entity_type"])
