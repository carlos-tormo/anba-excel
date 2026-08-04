import json
import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.db.repositories.team_objectives import TeamObjectiveRepository
from app.domain.team_objectives import (
    CHAMPION,
    COMPARISON_EXCEEDED,
    FINALS,
    PLAY_IN,
    SECOND_ROUND,
)
from app.server import LeagueDB
from app.services.team_objectives import TeamObjectiveService
from app.xlsx_import import create_schema, now_iso


class TeamObjectiveRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(prefix="anba-team-objectives-", suffix=".db")
        os.close(descriptor)
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO teams (
                    code, name, salary_cap, luxury_cap, first_apron, second_apron,
                    created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', 154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            )
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        with connect_test_db(self.db_path) as conn:
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO users (id, email, username, display_name, created_at, updated_at)
                VALUES (42, 'admin@example.test', 'admin', 'Admin', ?, ?)
                """,
                (timestamp, timestamp),
            )
            conn.commit()
        self.repository = TeamObjectiveRepository(self.db, now=now_iso)
        self.service = TeamObjectiveService(
            self.repository,
            player_happiness=self.db._player_happiness_service,
        )

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_migration_creates_objective_tables_and_indexes(self) -> None:
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            indexes = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            schema_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'team_season_objectives'"
            ).fetchone()["sql"]

        self.assertIn("team_season_objectives", tables)
        self.assertIn("team_season_objective_events", tables)
        self.assertIn("idx_team_season_objectives_season", indexes)
        self.assertIn("idx_team_season_objective_events_objective", indexes)
        self.assertIn("'champion'", schema_sql)

    def test_migration_upgrades_existing_objective_table_to_allow_champion_result(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE IF EXISTS team_season_objective_events")
            conn.execute("DROP TABLE IF EXISTS team_season_objectives")
            conn.execute(
                """
                CREATE TABLE team_season_objectives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                    season_year INTEGER NOT NULL CHECK(season_year >= 2000 AND season_year <= 2100),
                    objective_code TEXT NOT NULL CHECK(objective_code IN (
                        'finals', 'conference_finals', 'second_round', 'first_round',
                        'play_in', 'play_in_race', 'youth_development'
                    )),
                    objective_label_snapshot TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN (
                        'proposed', 'agreed', 'locked', 'resolved'
                    )),
                    agreed_at TEXT,
                    agreed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    owner_conversation_id TEXT,
                    achieved_code TEXT CHECK(achieved_code IS NULL OR achieved_code IN (
                        'finals', 'conference_finals', 'second_round', 'first_round',
                        'play_in', 'play_in_race', 'youth_development'
                    )),
                    achieved_label_snapshot TEXT,
                    resolved_at TEXT,
                    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(team_id, season_year)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE team_season_objective_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    objective_id INTEGER NOT NULL REFERENCES team_season_objectives(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    previous_objective_code TEXT,
                    new_objective_code TEXT,
                    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    command_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO team_season_objectives (
                    team_id, season_year, objective_code, objective_label_snapshot,
                    status, agreed_at, agreed_by_user_id, created_at, updated_at
                ) VALUES (?, 2026, 'first_round', 'Alcanzar la primera ronda',
                          'agreed', ?, 42, ?, ?)
                """,
                (team_id, timestamp, timestamp, timestamp),
            )
            conn.commit()

        self.db.ensure_auth_schema()
        resolved = self.repository.resolve_objective("ATL", 2026, "Campeón")

        self.assertEqual(CHAMPION, resolved["achieved_code"])

    def test_set_update_and_resolve_objective_records_events(self) -> None:
        created = self.repository.set_objective(
            "ATL",
            2026,
            "Jugar el play-in",
            status="agreed",
            actor={"user_id": 42},
            owner_conversation_id="owner-chat-1",
        )

        self.assertEqual(PLAY_IN, created["objective_code"])
        self.assertEqual("Jugar el play-in", created["objective_label_snapshot"])
        self.assertEqual("agreed", created["status"])
        self.assertEqual(1, created["version"])
        self.assertEqual("ATL", created["team_code"])
        self.assertEqual(42, created["agreed_by_user_id"])
        self.assertTrue(created["agreed_at"])

        updated = self.repository.set_objective(
            "ATL",
            2026,
            "Alcanzar la segunda ronda",
            status="locked",
            actor={"user_id": 42},
            expected_version=created["version"],
            metadata={"source": "admin-test"},
        )
        self.assertEqual(SECOND_ROUND, updated["objective_code"])
        self.assertEqual("locked", updated["status"])
        self.assertEqual(2, updated["version"])

        resolved = self.repository.resolve_objective(
            "ATL",
            2026,
            "Campeón",
            actor={"user_id": 42},
            expected_version=updated["version"],
        )

        self.assertEqual("resolved", resolved["status"])
        self.assertEqual(CHAMPION, resolved["achieved_code"])
        self.assertEqual("Campeón", resolved["achieved_label_snapshot"])
        self.assertEqual(COMPARISON_EXCEEDED, resolved["comparison"])
        self.assertEqual(3, resolved["version"])

        loaded = self.repository.get("ATL", 2026, include_events=True)
        self.assertIsNotNone(loaded)
        self.assertEqual(3, loaded["version"])
        self.assertEqual(3, len(loaded["events"]))
        self.assertEqual(
            ["objective_created", "objective_updated", "objective_resolved"],
            [event["event_type"] for event in loaded["events"]],
        )
        self.assertIsNone(loaded["events"][0]["previous_objective_code"])
        self.assertEqual(PLAY_IN, loaded["events"][0]["new_objective_code"])
        self.assertEqual(PLAY_IN, loaded["events"][1]["previous_objective_code"])
        self.assertEqual(SECOND_ROUND, loaded["events"][1]["new_objective_code"])
        self.assertEqual("admin-test", loaded["events"][1]["metadata"]["source"])

    def test_rejects_stale_versions_and_invalid_objectives(self) -> None:
        created = self.repository.set_objective("ATL", 2026, PLAY_IN)

        with self.assertRaisesRegex(ValueError, "stale_entity_version"):
            self.repository.set_objective("ATL", 2026, SECOND_ROUND, expected_version=99)
        with self.assertRaisesRegex(ValueError, "invalid_team_objective"):
            self.repository.set_objective("ATL", 2026, "ganar 50 partidos", expected_version=created["version"])
        with self.assertRaisesRegex(ValueError, "invalid_team_objective"):
            self.repository.set_objective("ATL", 2026, "Campeón", expected_version=created["version"])
        with self.assertRaisesRegex(ValueError, "invalid_team_objective_status"):
            self.repository.set_objective("ATL", 2026, PLAY_IN, status="done", expected_version=created["version"])

    def test_list_for_season_returns_only_persisted_objectives(self) -> None:
        self.repository.set_objective("ATL", 2026, PLAY_IN)

        objectives = self.repository.list_for_season(2026)

        self.assertEqual(1, len(objectives))
        self.assertEqual("ATL", objectives[0]["team_code"])
        self.assertEqual(PLAY_IN, objectives[0]["objective"]["code"])

    def test_service_exposes_current_and_player_join_context(self) -> None:
        with connect_test_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO app_settings (key, value, version, updated_at)
                VALUES ('current_year', '2026', 1, ?)
                """,
                (now_iso(),),
            )
            conn.commit()
        self.service.set_agreed("ATL", 2026, "Luchar por el play-in", {"user_id": 42})

        current = self.service.current_for_team("ATL")
        join_context = self.service.for_player_join_context("ATL")

        self.assertIsNotNone(current)
        self.assertEqual("play_in_race", current["objective_code"])
        self.assertEqual("play_in_race", join_context["join_objective_code"])
        self.assertEqual("Luchar por el play-in", join_context["join_objective_label"])

        fallback_context = self.service.for_player_join_context("ATL", 2027)
        self.assertEqual("play_in_race", fallback_context["join_objective_code"])
        self.assertEqual(2026, fallback_context["objective_season_year"])
        self.assertEqual("latest_prior", fallback_context["objective_source"])

    def test_service_applies_happiness_impact_when_objective_changes(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            profiles = [
                (101, "Young Star", "2002-01-01", 5.0),
                (102, "Veteran Star", "1990-01-01", 5.0),
                (103, "Low Rated Vet", "1990-01-01", 5.0),
            ]
            conn.executemany(
                """
                INSERT INTO player_profiles (id, name, date_of_birth, happiness, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(profile_id, name, dob, happiness, timestamp, timestamp) for profile_id, name, dob, happiness in profiles],
            )
            conn.executemany(
                """
                INSERT INTO players (
                    team_id, row_order, bird_rights, rating, name,
                    salary_2026_text, created_at, updated_at, profile_id
                ) VALUES (?, ?, 'Bird', ?, ?, '1', ?, ?, ?)
                """,
                [
                    (team_id, 1, "90", "Young Star", timestamp, timestamp, 101),
                    (team_id, 2, "90", "Veteran Star", timestamp, timestamp, 102),
                    (team_id, 3, "70", "Low Rated Vet", timestamp, timestamp, 103),
                ],
            )
            conn.commit()

        created = self.service.set_agreed("ATL", 2026, "Finalista", {"user_id": 42})

        self.assertEqual(2, created["happiness_impact"]["affected_count"])
        with connect_test_db(self.db_path) as conn:
            rows = {
                int(row["id"]): float(row["happiness"])
                for row in conn.execute("SELECT id, happiness FROM player_profiles WHERE id IN (101, 102, 103)")
            }
        self.assertEqual({101: 5.5, 102: 5.5, 103: 5.0}, rows)

        updated = self.service.set_agreed(
            "ATL",
            2026,
            "Desarrollar jóvenes",
            {"user_id": 42},
            expected_version=created["version"],
        )

        self.assertEqual(2, updated["happiness_impact"]["affected_count"])
        with connect_test_db(self.db_path) as conn:
            rows = {
                int(row["id"]): float(row["happiness"])
                for row in conn.execute("SELECT id, happiness FROM player_profiles WHERE id IN (101, 102, 103)")
            }
            events = conn.execute(
                """
                SELECT event_type, applied_delta, source_entity_type
                FROM player_happiness_events
                WHERE profile_id IN (101, 102)
                ORDER BY id
                """
            ).fetchall()
        self.assertEqual({101: 3.0, 102: 3.0, 103: 5.0}, rows)
        self.assertEqual(4, len(events))
        self.assertTrue(all(row["event_type"] == "team_objective_set" for row in events))
        self.assertTrue(all(row["source_entity_type"] == "team_season_objective" for row in events))

    def test_setting_and_resolving_objective_syncs_owner_office_snapshots(self) -> None:
        created = self.service.set_agreed(
            "ATL",
            2026,
            "Segunda ronda",
            {"user_id": 42},
        )
        resolved = self.service.resolve(
            "ATL",
            2026,
            "Finales",
            {"user_id": 42},
            expected_version=created["version"],
        )

        self.assertEqual(COMPARISON_EXCEEDED, resolved["comparison"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            snapshot = conn.execute(
                """
                SELECT season_goal_set, season_goal_achieved
                FROM team_owner_office o
                JOIN teams t ON t.id = o.team_id
                WHERE t.code = 'ATL' AND o.season_year = 2026
                """
            ).fetchone()

        self.assertEqual("Alcanzar la segunda ronda", snapshot["season_goal_set"])
        self.assertEqual("Alcanzar las finales", snapshot["season_goal_achieved"])

        office = self.db.get_team_owner_office("ATL", include_private=True)
        entry = office["entries"]["2026"]
        self.assertEqual("Alcanzar la segunda ronda", entry["season_goal_set"])
        self.assertEqual("Alcanzar las finales", entry["season_goal_achieved"])
        self.assertEqual("Objetivo superado", entry["season_goal_evaluation"])

    def test_resolving_objective_applies_player_happiness_impact_once_per_player(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.executemany(
                """
                INSERT INTO player_profiles (id, name, date_of_birth, happiness, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (201, "Rotation Player", "1999-01-01", 5.0, timestamp, timestamp),
                    (202, "Bench Player", "2001-01-01", 6.0, timestamp, timestamp),
                ],
            )
            conn.executemany(
                """
                INSERT INTO players (
                    team_id, row_order, bird_rights, rating, name,
                    salary_2026_text, created_at, updated_at, profile_id
                ) VALUES (?, ?, 'Bird', ?, ?, '1', ?, ?, ?)
                """,
                [
                    (team_id, 1, "70", "Rotation Player", timestamp, timestamp, 201),
                    (team_id, 2, "70", "Bench Player", timestamp, timestamp, 202),
                ],
            )
            conn.commit()

        created = self.service.set_agreed("ATL", 2026, "Segunda ronda", {"user_id": 42})
        resolved = self.service.resolve(
            "ATL",
            2026,
            "Finales",
            {"user_id": 42},
            expected_version=created["version"],
        )

        self.assertEqual(COMPARISON_EXCEEDED, resolved["comparison"])
        self.assertEqual(2.0, resolved["happiness_impact"]["applied_delta"])
        self.assertEqual(2, resolved["happiness_impact"]["affected_count"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = {
                int(row["id"]): float(row["happiness"])
                for row in conn.execute("SELECT id, happiness FROM player_profiles WHERE id IN (201, 202)")
            }
            events = conn.execute(
                """
                SELECT event_type, applied_delta, source_entity_type, source_entity_id, command_id
                FROM player_happiness_events
                WHERE profile_id IN (201, 202)
                ORDER BY id
                """
            ).fetchall()
        self.assertEqual({201: 7.0, 202: 8.0}, rows)
        self.assertEqual(2, len(events))
        self.assertTrue(all(row["event_type"] == "team_objective_resolution" for row in events))
        self.assertTrue(all(row["source_entity_type"] == "team_season_objective" for row in events))
        self.assertTrue(all(str(row["source_entity_id"]) == str(resolved["id"]) for row in events))
        self.assertEqual(2, len({row["command_id"] for row in events}))

        repeated = self.service.resolve(
            "ATL",
            2026,
            "Finales",
            {"user_id": 42},
            expected_version=resolved["version"],
        )

        self.assertEqual(0, repeated["happiness_impact"]["affected_count"])
        self.assertEqual(2, len(repeated["happiness_impact"]["skipped"]))
        with connect_test_db(self.db_path) as conn:
            rows = {
                int(row["id"]): float(row["happiness"])
                for row in conn.execute("SELECT id, happiness FROM player_profiles WHERE id IN (201, 202)")
            }
            event_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM player_happiness_events
                WHERE event_type = 'team_objective_resolution'
                  AND profile_id IN (201, 202)
                """
            ).fetchone()["count"]
        self.assertEqual({201: 7.0, 202: 8.0}, rows)
        self.assertEqual(2, event_count)


if __name__ == "__main__":
    unittest.main()
