import json
import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.db.repositories.player_happiness import PlayerHappinessRepository
from app.server import LeagueDB
from app.services.free_agency import FreeAgencyService
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

    def test_free_agent_join_applies_team_objective_initial_impression_modifier(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO teams (
                    code, name, salary_cap, luxury_cap, first_apron, second_apron,
                    created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', 154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO app_settings (key, value, version, updated_at)
                VALUES ('current_year', '2026', 1, ?)
                """,
                (timestamp,),
            )
            profile_id = int(
                conn.execute(
                    """
                    INSERT INTO player_profiles (name, date_of_birth, happiness, created_at, updated_at)
                    VALUES ('Veteran Star', '1990-01-01', 0, ?, ?)
                    """,
                    (timestamp, timestamp),
                ).lastrowid
            )
            free_agent_id = int(
                conn.execute(
                    """
                    INSERT INTO free_agents (profile_id, name, rating, created_at, updated_at)
                    VALUES (?, 'Veteran Star', '95', ?, ?)
                    """,
                    (profile_id, timestamp, timestamp),
                ).lastrowid
            )
            conn.commit()
        self.db._team_objective_service.set_agreed("ATL", 2026, "Finalista", {"user_id": 42})
        service = FreeAgencyService(
            self.db,
            contract_seasons=range(2025, 2032),
            player_happiness=self.db._player_happiness_service,
            team_objectives=self.db._team_objective_service,
        )

        result = service.sign_free_agent(
            free_agent_id,
            "ATL",
            {"salary_2026_text": "1000000"},
        )

        self.assertIsNotNone(result["player_id"])
        self.assertEqual(7.5, result["happiness_event"]["new_happiness"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            profile = conn.execute(
                "SELECT happiness FROM player_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            event = conn.execute(
                """
                SELECT event_type, new_value, metadata_json
                FROM player_happiness_events
                WHERE profile_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (profile_id,),
            ).fetchone()
        metadata = json.loads(event["metadata_json"])
        self.assertEqual(7.5, profile["happiness"])
        self.assertEqual("team_join", event["event_type"])
        self.assertEqual(7.5, event["new_value"])
        self.assertEqual([0.5], metadata["modifiers"])
        self.assertEqual("team_objective_join_context", metadata["modifier_details"][0]["event_type"])
        self.assertEqual("finals", metadata["modifier_details"][0]["objective_code"])

    def test_set_value_creates_manual_adjustment_event_with_delta_and_metadata(self) -> None:
        result = self.service.set_value(
            self.jokic_id,
            {
                "happiness": 4,
                "expected_version": 1,
                "reason": "Admin correction",
                "metadata": {"source": "admin-profile"},
            },
            {"user_id": 42},
        )

        self.assertTrue(result["ok"])
        self.assertEqual("manual_adjustment", result["event_type"])
        self.assertEqual(1.5, result["previous_happiness"])
        self.assertEqual(2.5, result["proposed_delta"])
        self.assertEqual(2.5, result["applied_delta"])
        self.assertEqual(4.0, result["new_happiness"])
        self.assertEqual(2, result["version"])
        self.assertEqual("valid", result["validation_result"])
        self.assertEqual({"profile_id": self.jokic_id, "version": 2, "new_happiness": 4.0}, result["entity_versions"])

        events = self.service.events(self.jokic_id)["events"]
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual("manual_adjustment", event["event_type"])
        self.assertEqual("Admin correction", event["reason"])
        self.assertEqual("admin-profile", event["metadata"]["source"])
        self.assertEqual("multiyear", event["metadata"]["contract_context"])
        self.assertIsNone(event["metadata"]["happiness_milestone"])
        self.assertIsNone(event["metadata"]["triggered_happiness_milestone"])
        self.assertEqual("Admin", event["actor_name"])

    def test_set_value_rejects_stale_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "stale_entity_version"):
            self.service.set_value(
                self.jokic_id,
                {"happiness": 4, "expected_version": 99},
                {"user_id": 42},
            )

    def test_set_value_reports_public_trade_request_milestone(self) -> None:
        result = self.service.set_value(
            self.jokic_id,
            {"happiness": 0.5, "expected_version": 1, "reason": "Manual correction"},
            {"user_id": 42},
        )

        self.assertEqual("public_trade_request", result["happiness_milestone"]["code"])
        self.assertEqual("public", result["happiness_milestone"]["visibility"])
        self.assertEqual("public_trade_request", result["triggered_happiness_milestone"]["code"])
        self.assertTrue(result["private_admin_notification"])
        self.assertTrue(result["discord_news_eligible"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            event = conn.execute(
                "SELECT metadata_json FROM player_happiness_events WHERE profile_id = ?",
                (self.jokic_id,),
            ).fetchone()
        metadata = json.loads(event["metadata_json"])
        self.assertEqual("public_trade_request", metadata["happiness_milestone"]["code"])
        self.assertEqual("public_trade_request", metadata["triggered_happiness_milestone"]["code"])

    def test_trade_request_followup_applies_three_and_nine_month_penalties_once(self) -> None:
        repository = PlayerHappinessRepository(self.db)
        repository.apply_event(
            self.jokic_id,
            {
                "event_type": "manual_adjustment",
                "event_date": "2026-01-15",
                "new_value": 1.5,
                "source_entity_type": "test",
                "source_entity_id": "trade-request-start",
                "reason": "Trade request threshold reached",
                "metadata": {
                    "contract_context": "multiyear",
                    "triggered_happiness_milestone": {
                        "code": "private_trade_request",
                        "contract_context": "multiyear",
                    },
                },
            },
            timestamp="2026-01-15T12:00:00Z",
            command_id="test:trade-request-start",
            actor_user_id=42,
        )
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            timestamp = "2025-07-01T00:00:00Z"
            team_id = conn.execute(
                """
                INSERT INTO teams (
                    code, name, salary_cap, luxury_cap, first_apron, second_apron,
                    created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', 154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO players (
                    team_id, profile_id, row_order, name, rating,
                    salary_2026_text, created_at, updated_at
                ) VALUES (?, ?, 1, 'Nikola Jokic', '95', '1.000.000', ?, ?)
                """,
                (team_id, self.jokic_id, timestamp, timestamp),
            )
            conn.commit()

        result = self.service.apply_trade_request_followups(
            as_of_date="2026-10-15",
            actor={"user_id": 42},
        )

        self.assertEqual(1, result["candidate_count"])
        self.assertEqual(2, result["affected_count"])
        self.assertEqual([-0.5, -1.0], [event["applied_delta"] for event in result["events"]])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            profile = conn.execute(
                "SELECT happiness FROM player_profiles WHERE id = ?",
                (self.jokic_id,),
            ).fetchone()
            events = conn.execute(
                """
                SELECT event_type, applied_delta, source_entity_type, source_entity_id, metadata_json, command_id
                FROM player_happiness_events
                WHERE profile_id = ?
                ORDER BY id
                """,
                (self.jokic_id,),
            ).fetchall()
        self.assertEqual(0.0, float(profile["happiness"]))
        followups = [event for event in events if event["event_type"] == "trade_request_followup"]
        self.assertEqual(2, len(followups))
        self.assertTrue(all(event["source_entity_type"] == "player_trade_request" for event in followups))
        self.assertEqual(
            ["three_months", "nine_months"],
            [json.loads(event["metadata_json"])["trade_request_followup_stage"] for event in followups],
        )
        self.assertEqual(2, len({event["command_id"] for event in followups}))

        repeated = self.service.apply_trade_request_followups(
            as_of_date="2026-10-15",
            actor={"user_id": 42},
        )

        self.assertEqual(0, repeated["affected_count"])
        with connect_test_db(self.db_path) as conn:
            event_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM player_happiness_events
                WHERE profile_id = ? AND event_type = 'trade_request_followup'
                """,
                (self.jokic_id,),
            ).fetchone()["count"]
        self.assertEqual(2, event_count)

    def test_trade_request_followup_skips_recovered_or_traded_players(self) -> None:
        repository = PlayerHappinessRepository(self.db)
        repository.apply_event(
            self.jokic_id,
            {
                "event_type": "manual_adjustment",
                "event_date": "2026-01-15",
                "new_value": 1.5,
                "source_entity_type": "test",
                "source_entity_id": "recovered-request-start",
                "reason": "Trade request threshold reached",
                "metadata": {
                    "contract_context": "multiyear",
                    "triggered_happiness_milestone": {
                        "code": "private_trade_request",
                        "contract_context": "multiyear",
                    },
                },
            },
            timestamp="2026-01-15T12:00:00Z",
            command_id="test:recovered-request-start",
            actor_user_id=42,
        )
        repository.apply_event(
            self.jokic_id,
            {
                "event_type": "manual_adjustment",
                "event_date": "2026-02-01",
                "new_value": 2.5,
                "source_entity_type": "test",
                "source_entity_id": "recovered-request-end",
                "reason": "Happiness recovered",
                "metadata": {},
            },
            timestamp="2026-02-01T12:00:00Z",
            command_id="test:recovered-request-end",
            actor_user_id=42,
        )
        repository.apply_event(
            self.duplicate_a_id,
            {
                "event_type": "manual_adjustment",
                "event_date": "2026-01-15",
                "new_value": 1.5,
                "source_entity_type": "test",
                "source_entity_id": "traded-request-start",
                "reason": "Trade request threshold reached",
                "metadata": {
                    "contract_context": "multiyear",
                    "triggered_happiness_milestone": {
                        "code": "private_trade_request",
                        "contract_context": "multiyear",
                    },
                },
            },
            timestamp="2026-01-15T12:00:00Z",
            command_id="test:traded-request-start",
            actor_user_id=42,
        )
        with connect_test_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO player_transactions (
                    profile_id, action, team_code, summary, created_at
                ) VALUES (?, 'trade', 'ATL', 'Traded away', ?)
                """,
                (self.duplicate_a_id, "2026-02-01T12:00:00Z"),
            )
            conn.commit()

        result = self.service.apply_trade_request_followups(
            as_of_date="2026-10-15",
            actor={"user_id": 42},
        )

        self.assertEqual(0, result["candidate_count"])
        self.assertEqual(0, result["affected_count"])

    def test_automatic_modifier_is_skipped_for_free_agent_context(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO free_agents (profile_id, name, created_at, updated_at)
                VALUES (?, 'Nikola Jokic', ?, ?)
                """,
                (self.jokic_id, timestamp, timestamp),
            )
            conn.commit()

        result = self.service.apply_modifier(
            self.jokic_id,
            -3,
            reason="Automatic season event",
            source_entity_type="season_event",
            source_entity_id="event-1",
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual("free_agent_happiness_frozen", result["reason"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            profile = conn.execute(
                "SELECT happiness FROM player_profiles WHERE id = ?",
                (self.jokic_id,),
            ).fetchone()
            event_count = conn.execute(
                "SELECT COUNT(*) AS total FROM player_happiness_events WHERE profile_id = ?",
                (self.jokic_id,),
            ).fetchone()["total"]
        self.assertEqual(1.5, profile["happiness"])
        self.assertEqual(0, event_count)

    def test_roster_impact_applies_rating_band_and_first_season_adjustments(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO teams (
                    code, name, salary_cap, luxury_cap, first_apron, second_apron, created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', 154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            )
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.execute(
                """
                INSERT OR REPLACE INTO app_settings (key, value, version, updated_at)
                VALUES ('current_year', '2026', 1, ?)
                """,
                (timestamp,),
            )

            subject_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Star Arrival', 7, '1998-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            veteran_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Veteran Teammate', 5, '1990-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            first_year_adult_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Adult New Teammate', 5, '1995-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            first_year_young_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Young New Teammate', 5, '2002-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            rows = [
                (subject_profile_id, "Star Arrival", "88", "2026-07-10T00:00:00Z"),
                (veteran_profile_id, "Veteran Teammate", "75", "2025-07-10T00:00:00Z"),
                (first_year_adult_profile_id, "Adult New Teammate", "75", "2026-07-10T00:00:00Z"),
                (first_year_young_profile_id, "Young New Teammate", "75", "2026-07-10T00:00:00Z"),
            ]
            for order, (profile_id, name, rating, created_at) in enumerate(rows, start=1):
                conn.execute(
                    """
                    INSERT INTO players (
                        team_id, profile_id, row_order, name, rating,
                        salary_2026_text, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, '1.000.000', ?, ?)
                    """,
                    (team_id, profile_id, order, name, rating, created_at, created_at),
                )
                conn.execute(
                    """
                    INSERT INTO player_transactions (
                        profile_id, action, team_code, summary, created_at
                    ) VALUES (?, 'create', 'ATL', 'Alta en ATL', ?)
                    """,
                    (profile_id, created_at),
                )
            conn.commit()

        arrival = self.service.apply_roster_impact(
            team_code="ATL",
            subject_player={"id": 1, "profile_id": subject_profile_id, "name": "Star Arrival", "rating": "88"},
            direction="add",
            source_entity_type="test",
            source_entity_id="arrival",
        )
        departure = self.service.apply_roster_impact(
            team_code="ATL",
            subject_player={"id": 1, "profile_id": subject_profile_id, "name": "Star Departure", "rating": "90"},
            direction="remove",
            source_entity_type="test",
            source_entity_id="departure",
        )

        self.assertEqual(3, arrival["affected_count"])
        self.assertEqual(2, departure["affected_count"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            values = {
                row["id"]: row["happiness"]
                for row in conn.execute("SELECT id, happiness FROM player_profiles")
            }
            event_rows = conn.execute(
                """
                SELECT event_type, applied_delta, source_entity_id, metadata_json
                FROM player_happiness_events
                WHERE source_entity_type = 'test'
                ORDER BY id
                """
            ).fetchall()
        self.assertEqual(4.0, values[veteran_profile_id])
        self.assertEqual(4.5, values[first_year_adult_profile_id])
        self.assertEqual(5.5, values[first_year_young_profile_id])
        self.assertEqual(5, len(event_rows))
        self.assertTrue(all(row["event_type"] == "roster_impact" for row in event_rows))
        self.assertEqual(["arrival", "arrival", "arrival", "departure", "departure"], [row["source_entity_id"] for row in event_rows])

    def test_zero_threshold_rule_tracks_original_teammate_cohort(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO teams (
                    code, name, salary_cap, luxury_cap, first_apron, second_apron, created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', 154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            )
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            subject_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Zero Subject', 1, '1998-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            teammate_a_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Original Teammate A', 5, '1990-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            teammate_b_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Original Teammate B', 5, '1992-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            for order, (profile_id, name) in enumerate(
                [
                    (subject_profile_id, "Zero Subject"),
                    (teammate_a_id, "Original Teammate A"),
                    (teammate_b_id, "Original Teammate B"),
                ],
                start=1,
            ):
                conn.execute(
                    """
                    INSERT INTO players (
                        team_id, profile_id, row_order, name, rating,
                        salary_2026_text, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, '75', '1.000.000', ?, ?)
                    """,
                    (team_id, profile_id, order, name, timestamp, timestamp),
                )
                conn.execute(
                    """
                    INSERT INTO player_transactions (
                        profile_id, action, team_code, summary, created_at
                    ) VALUES (?, 'create', 'ATL', 'Alta en ATL', ?)
                    """,
                    (profile_id, timestamp),
                )
            conn.commit()

        initial = self.service.set_value(
            subject_profile_id,
            {"happiness": 0, "expected_version": 1, "reason": "Reached zero"},
            {"user_id": 42},
        )
        self.assertEqual("initial_zero", initial["zero_threshold_impact"]["transition"])
        self.assertEqual(2, initial["zero_threshold_impact"]["affected_count"])

        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            subject_version = conn.execute(
                "SELECT version FROM player_profiles WHERE id = ?",
                (subject_profile_id,),
            ).fetchone()["version"]
        recovered = self.service.set_value(
            subject_profile_id,
            {"happiness": 1, "expected_version": subject_version, "reason": "Recovered above zero"},
            {"user_id": 42},
        )
        self.assertEqual("recovered_above_zero", recovered["zero_threshold_impact"]["transition"])
        self.assertEqual(2, recovered["zero_threshold_impact"]["affected_count"])

        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            newcomer_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('New Teammate', 5, '1991-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            conn.execute(
                """
                INSERT INTO players (
                    team_id, profile_id, row_order, name, rating,
                    salary_2026_text, created_at, updated_at
                ) VALUES (?, ?, 4, 'New Teammate', '75', '1.000.000', ?, ?)
                """,
                (team_id, newcomer_id, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO player_transactions (
                    profile_id, action, team_code, summary, created_at
                ) VALUES (?, 'create', 'ATL', 'Alta en ATL', ?)
                """,
                (newcomer_id, timestamp),
            )
            subject_version = conn.execute(
                "SELECT version FROM player_profiles WHERE id = ?",
                (subject_profile_id,),
            ).fetchone()["version"]
            conn.commit()

        returned = self.service.set_value(
            subject_profile_id,
            {"happiness": 0, "expected_version": subject_version, "reason": "Returned to zero"},
            {"user_id": 42},
        )

        self.assertEqual("return_to_zero", returned["zero_threshold_impact"]["transition"])
        self.assertEqual(3, returned["zero_threshold_impact"]["affected_count"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            values = {
                row["id"]: row["happiness"]
                for row in conn.execute(
                    "SELECT id, happiness FROM player_profiles WHERE id IN (?, ?, ?)",
                    (teammate_a_id, teammate_b_id, newcomer_id),
                )
            }
            events = conn.execute(
                """
                SELECT profile_id, applied_delta, metadata_json
                FROM player_happiness_events
                WHERE event_type = 'teammate_zero_threshold'
                ORDER BY id
                """
            ).fetchall()
        self.assertEqual(4.0, values[teammate_a_id])
        self.assertEqual(4.0, values[teammate_b_id])
        self.assertEqual(4.0, values[newcomer_id])
        self.assertEqual(7, len(events))
        initial_metadata = json.loads(events[0]["metadata_json"])
        self.assertEqual(
            [teammate_a_id, teammate_b_id],
            initial_metadata["zero_threshold"]["cohort_profile_ids"],
        )

    def test_zero_trade_relief_applies_to_original_teammates(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                INSERT INTO teams (
                    code, name, salary_cap, luxury_cap, first_apron, second_apron, created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', 154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            )
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            subject_profile_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Trade Relief Subject', 1, '1998-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            teammate_id = int(conn.execute(
                """
                INSERT INTO player_profiles (name, happiness, date_of_birth, created_at, updated_at)
                VALUES ('Relief Teammate', 5, '1990-01-01', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid)
            for order, (profile_id, name) in enumerate(
                [(subject_profile_id, "Trade Relief Subject"), (teammate_id, "Relief Teammate")],
                start=1,
            ):
                conn.execute(
                    """
                    INSERT INTO players (
                        team_id, profile_id, row_order, name, rating,
                        salary_2026_text, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, '75', '1.000.000', ?, ?)
                    """,
                    (team_id, profile_id, order, name, timestamp, timestamp),
                )
            conn.commit()

        self.service.set_value(
            subject_profile_id,
            {"happiness": 0, "expected_version": 1, "reason": "Reached zero"},
            {"user_id": 42},
        )
        with self.service.repository.transaction("IMMEDIATE") as conn:
            relief = self.service.apply_zero_trade_relief_conn(
                conn,
                profile_id=subject_profile_id,
                source_entity_id="trade-123",
                actor={"user_id": 42},
                timestamp=now_iso(),
                command_id_prefix="player-happiness:zero-threshold:trade:123",
            )

        self.assertEqual("traded_after_zero", relief["transition"])
        self.assertEqual(1, relief["affected_count"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            teammate = conn.execute(
                "SELECT happiness FROM player_profiles WHERE id = ?",
                (teammate_id,),
            ).fetchone()
            event = conn.execute(
                """
                SELECT applied_delta, metadata_json
                FROM player_happiness_events
                WHERE profile_id = ? AND event_type = 'teammate_zero_threshold'
                ORDER BY id DESC
                LIMIT 1
                """,
                (teammate_id,),
            ).fetchone()
        self.assertEqual(4.5, teammate["happiness"])
        self.assertEqual(0.5, event["applied_delta"])
        self.assertEqual("traded_after_zero", json.loads(event["metadata_json"])["zero_threshold"]["transition"])
