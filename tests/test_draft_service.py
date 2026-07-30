import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.services.draft import DraftService
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, timestamp, timestamp),
    )


def insert_gm_history(conn: sqlite3.Connection, team_code: str, gm_name: str, start_date: str) -> int:
    timestamp = now_iso()
    team = conn.execute("SELECT id FROM teams WHERE code = ?", (team_code,)).fetchone()
    if not team:
        raise AssertionError(f"missing team {team_code}")
    gm = conn.execute(
        """
        INSERT INTO gm_identities (
            entity_type, user_id, display_name, created_at, updated_at
        ) VALUES ('offline', NULL, ?, ?, ?)
        """,
        (gm_name, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO team_gm_history (
            team_id, gm_entity_id, row_order, gm_name, start_date, color, created_at, updated_at
        ) VALUES (?, ?, 0, ?, ?, NULL, ?, ?)
        """,
        (int(team["id"]), int(gm.lastrowid), gm_name, start_date, timestamp, timestamp),
    )
    return int(gm.lastrowid)


class DraftServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(prefix="anba-draft-service-", suffix=".db")
        os.close(descriptor)
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            insert_team(conn, "BKN", "Brooklyn Nets")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        self.service = DraftService(self.db)
        self.first_pick = self.service.create_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "1st",
                "pick_number": 1,
                "owner_team_code": "ATL",
                "original_team_code": "ATL",
            }
        )
        self.second_pick = self.service.create_order_entry(
            {
                "draft_year": 2026,
                "draft_round": "1st",
                "pick_number": 2,
                "owner_team_code": "BKN",
                "original_team_code": "BKN",
            }
        )
        self.gm = {"email": "atl-gm@example.com", "name": "ATL GM", "role": "gm"}
        self.admin = {"email": "admin@example.com", "name": "Admin", "role": "admin"}

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def submit_gm_pick(self) -> dict:
        self.service.update_live_settings({"draft_year": 2026, "enabled": True})
        return self.service.submit_pick(
            self.first_pick,
            {"option_value": "Jugador A"},
            self.gm,
            is_admin=False,
        )

    def historical_rows(self, draft_year: int = 2019) -> list[dict]:
        return [
            {
                "draft_year": draft_year,
                "pick_number": pick,
                "player_name": f"Rookie {pick}",
                "team_code": "ATL" if pick % 2 else "BKN",
                "original_team_code": "BKN" if pick % 2 else "ATL",
            }
            for pick in range(1, 61)
        ]

    def test_import_and_list_historical_draft_selections(self) -> None:
        result = self.service.import_history({"draft_year": 2019, "selections": self.historical_rows(2019)})

        self.assertTrue(result["ok"])
        self.assertEqual(60, result["imported_count"])
        self.assertEqual([2019], result["years"])
        self.assertEqual("valid", result["validation_result"])
        self.assertEqual(60, result["entity_versions"]["imported_count"])

        history = self.service.list_history(2019)
        self.assertEqual(2019, history["draft_year"])
        self.assertEqual("history", history["mode"])
        self.assertEqual(60, history["selection_count"])
        self.assertEqual("1st", history["selections"][0]["draft_round"])
        self.assertEqual(1, history["selections"][0]["round_pick_number"])
        self.assertEqual("2nd", history["selections"][30]["draft_round"])
        self.assertEqual(1, history["selections"][30]["round_pick_number"])
        self.assertEqual("Rookie 1", history["selections"][0]["player_name"])
        self.assertIsInstance(history["selections"][0]["draft_pick_id"], int)
        self.assertEqual("2019-1ST-BKN", history["selections"][0]["canonical_id"])
        self.assertEqual("2019-2ND-BKN", history["selections"][30]["canonical_id"])
        with connect_test_db(self.db_path) as conn:
            linked = conn.execute(
                """
                SELECT p.draft_year, p.draft_round, p.original_team
                FROM draft_history_selections h
                JOIN draft_picks p ON p.id = h.draft_pick_id
                WHERE h.draft_year = 2019 AND h.pick_number = 1
                """
            ).fetchone()
        self.assertEqual((2019, "1st", "BKN"), tuple(linked))

    def test_import_historical_draft_with_date_resolves_selecting_gm_snapshot(self) -> None:
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            atl_gm_id = insert_gm_history(conn, "ATL", "ATL Timeline GM", "2018-07-01")
            bkn_gm_id = insert_gm_history(conn, "BKN", "BKN Timeline GM", "2018-07-01")
            conn.commit()

        result = self.service.import_history({
            "draft_year": 2019,
            "draft_date": "2019-06-20",
            "selections": self.historical_rows(2019),
        })

        self.assertEqual(60, result["imported_count"])
        history = self.service.list_history(2019)
        first = history["selections"][0]
        second = history["selections"][1]
        self.assertEqual("2019-06-20", first["selection_date"])
        self.assertEqual(atl_gm_id, first["selecting_gm_entity_id"])
        self.assertEqual("ATL Timeline GM", first["selecting_gm_name"])
        self.assertEqual("timeline", first["selecting_gm_source"])
        self.assertEqual(bkn_gm_id, second["selecting_gm_entity_id"])
        self.assertEqual("BKN Timeline GM", second["selecting_gm_name"])

    def test_update_historical_draft_date_recomputes_gms_without_reimporting_picks(self) -> None:
        self.service.import_history({"draft_year": 2019, "selections": self.historical_rows(2019)})
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            insert_gm_history(conn, "ATL", "Old ATL GM", "2018-07-01")
            atl_new_gm_id = insert_gm_history(conn, "ATL", "New ATL GM", "2019-05-01")
            insert_gm_history(conn, "BKN", "BKN GM", "2018-07-01")
            conn.commit()

        result = self.service.update_history_dates({"draft_year": 2019, "draft_date": "2019-06-20"})

        self.assertTrue(result["ok"])
        self.assertEqual(60, result["updated_count"])
        self.assertEqual(60, result["gm_resolved_count"])
        self.assertEqual("valid", result["validation_result"])
        self.assertEqual(60, result["entity_versions"]["updated_count"])
        history = self.service.list_history(2019)
        self.assertEqual(60, history["selection_count"])
        first = history["selections"][0]
        self.assertEqual("Rookie 1", first["player_name"])
        self.assertEqual("2019-06-20", first["selection_date"])
        self.assertEqual(atl_new_gm_id, first["selecting_gm_entity_id"])
        self.assertEqual("New ATL GM", first["selecting_gm_name"])
        self.assertEqual("timeline", first["selecting_gm_source"])

    def test_update_historical_draft_selection_edits_one_pick_and_refreshes_identity(self) -> None:
        self.service.import_history({"draft_year": 2019, "selections": self.historical_rows(2019)})
        history = self.service.list_history(2019)
        selection_id = int(history["selections"][0]["id"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            bkn_override_id = insert_gm_history(conn, "BKN", "BKN Override GM", "2018-07-01")
            conn.commit()

        result = self.service.update_history_selection(
            selection_id,
            {
                "player_name": "Corrected Rookie",
                "selecting_team_code": "BKN",
                "original_team_code": "ATL",
                "selection_date": "2019-06-20",
                "selecting_gm_entity_id": bkn_override_id,
                "notes": "Corrected after review",
            },
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("Corrected Rookie", result["player_name"])
        self.assertEqual("BKN", result["selecting_team_code"])
        self.assertEqual("ATL", result["original_team_code"])
        self.assertEqual("2019-1ST-ATL", result["canonical_id"])
        self.assertIsInstance(result["draft_pick_id"], int)
        self.assertEqual("2019-06-20", result["selection_date"])
        self.assertEqual(bkn_override_id, result["selecting_gm_entity_id"])
        self.assertEqual("BKN Override GM", result["selecting_gm_name"])
        self.assertEqual("import_override", result["selecting_gm_source"])
        self.assertEqual("valid", result["validation_result"])
        self.assertEqual(selection_id, result["entity_versions"]["selection_id"])

        updated_history = self.service.list_history(2019)
        self.assertEqual(60, updated_history["selection_count"])
        self.assertEqual("Corrected Rookie", updated_history["selections"][0]["player_name"])

    def test_update_historical_draft_selection_can_recompute_gm_from_timeline(self) -> None:
        self.service.import_history({"draft_year": 2019, "selections": self.historical_rows(2019)})
        selection_id = int(self.service.list_history(2019)["selections"][0]["id"])
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            timeline_id = insert_gm_history(conn, "BKN", "Timeline BKN GM", "2019-01-01")
            conn.commit()

        result = self.service.update_history_selection(
            selection_id,
            {
                "selecting_team_code": "BKN",
                "selection_date": "2019-06-20",
                "selecting_gm_entity_id": None,
            },
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(timeline_id, result["selecting_gm_entity_id"])
        self.assertEqual("Timeline BKN GM", result["selecting_gm_name"])
        self.assertEqual("timeline", result["selecting_gm_source"])

    def test_update_historical_draft_selection_can_preserve_manual_gm_snapshot(self) -> None:
        rows = self.historical_rows(2019)
        rows[0]["gm_name"] = "Imported Manual GM"
        self.service.import_history({"draft_year": 2019, "selections": rows})
        selection_id = int(self.service.list_history(2019)["selections"][0]["id"])

        result = self.service.update_history_selection(
            selection_id,
            {
                "player_name": "Corrected Rookie",
                "preserve_selecting_gm_override": True,
            },
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("Corrected Rookie", result["player_name"])
        self.assertIsNone(result["selecting_gm_entity_id"])
        self.assertEqual("Imported Manual GM", result["selecting_gm_name"])
        self.assertEqual("import_override", result["selecting_gm_source"])

    def test_historical_draft_import_requires_60_picks_from_2019_to_past_years(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_draft_year"):
            self.service.import_history({"draft_year": 2018, "selections": self.historical_rows(2018)})

        with self.assertRaisesRegex(ValueError, "draft_history_year_must_be_past"):
            self.service.import_history({"draft_year": 2026, "selections": self.historical_rows(2026)})

        with self.assertRaisesRegex(ValueError, "draft_history_requires_60_picks"):
            self.service.import_history({"draft_year": 2019, "selections": self.historical_rows(2019)[:59]})

    def test_gm_submission_is_queued_without_advancing(self) -> None:
        submission = self.submit_gm_pick()

        self.assertTrue(submission["submitted_for_review"])
        self.assertEqual("pending", submission["request"]["status"])
        self.assertEqual(self.first_pick, submission["draft_live"]["current_pick_id"])

    def test_approve_pick_request_selects_player_and_advances(self) -> None:
        submission = self.submit_gm_pick()

        decision = self.service.decide_pick_request(
            int(submission["request"]["id"]),
            "approved",
            self.admin,
            request=submission["request"],
        )

        self.assertEqual("approved", decision["request"]["status"])
        self.assertEqual(self.second_pick, decision["draft_live"]["current_pick_id"])
        first = next(
            row for row in decision["draft_live"]["draft_order"] if row["id"] == self.first_pick
        )
        self.assertEqual("Jugador A", first["selection_text"])
        self.assertEqual(self.gm["email"], first["selected_by_email"])

    def test_reject_pick_request_keeps_current_pick_open(self) -> None:
        submission = self.submit_gm_pick()

        decision = self.service.decide_pick_request(
            int(submission["request"]["id"]),
            "rejected",
            self.admin,
            note="Invalid selection",
            request=submission["request"],
        )

        self.assertEqual("rejected", decision["request"]["status"])
        live = self.service.list_live(2026)
        self.assertEqual(self.first_pick, live["current_pick_id"])
        first = next(row for row in live["draft_order"] if row["id"] == self.first_pick)
        self.assertIsNone(first["selection_text"])

    def test_rejects_stale_pick_request_decision_version(self) -> None:
        submission = self.submit_gm_pick()
        request = submission["request"]
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE gm_draft_pick_requests SET version = version + 1 WHERE id = ?",
                (int(request["id"]),),
            )

        with self.assertRaisesRegex(ValueError, "stale_entity_version"):
            self.service.decide_pick_request(
                int(request["id"]),
                "rejected",
                self.admin,
                request=request,
            )

        stored = self.service.pick_request(int(request["id"]))
        self.assertEqual("pending", stored["status"])
        live = self.service.list_live(2026)
        self.assertEqual(self.first_pick, live["current_pick_id"])

    def test_read_model_does_not_delegate_back_to_league_db_facades(self) -> None:
        def unexpected_delegate(*_args, **_kwargs):
            raise AssertionError("draft read repository delegated back to LeagueDB")

        self.db.current_draft_year = unexpected_delegate
        self.db.list_draft_order = unexpected_delegate
        self.db.list_draft_pick_ledger = unexpected_delegate
        self.db.list_draft_history = unexpected_delegate
        self.db.get_draft_order_entry = unexpected_delegate
        self.db.list_draft_live = unexpected_delegate

        current_year = self.service.current_year()
        order = self.service.list_order(2026)
        ledger = self.service.list_pick_ledger(2026)
        self.service.import_history({"draft_year": 2019, "selections": self.historical_rows(2019)})
        history = self.service.list_history(2019)
        entry = self.service.order_entry(self.first_pick)
        live = self.service.list_live(2026)

        self.assertEqual(2026, current_year)
        self.assertEqual([self.first_pick, self.second_pick], [row["id"] for row in order["draft_order"]])
        self.assertEqual(2026, ledger["draft_year"])
        self.assertEqual(60, history["selection_count"])
        self.assertEqual(self.first_pick, entry["id"])
        self.assertEqual([self.first_pick, self.second_pick], [row["id"] for row in live["draft_order"]])

    def test_mutations_do_not_delegate_back_to_league_db_facades(self) -> None:
        def unexpected_delegate(*_args, **_kwargs):
            raise AssertionError("draft repository delegated back to LeagueDB")

        for name in (
            "create_draft_order_entry", "update_draft_order_entry", "delete_draft_order_entry",
            "update_draft_live_settings", "control_draft_live", "submit_draft_live_pick",
            "create_gm_draft_pick_request", "get_gm_draft_pick_request",
            "mark_gm_draft_pick_request_decided", "process_draft_results", "import_draft_history",
            "archive_draft_live_history",
        ):
            setattr(self.db, name, unexpected_delegate)

        extra_pick = self.service.create_order_entry({
            "draft_year": 2026, "draft_round": "2nd", "pick_number": 31,
            "owner_team_code": "ATL", "original_team_code": "BKN",
        })
        self.assertTrue(self.service.update_order_entry(extra_pick, {"owner_team_code": "BKN"}))
        self.assertTrue(self.service.delete_order_entry(extra_pick))

        self.service.update_live_settings({"draft_year": 2026, "enabled": True})
        self.service.control_live({"draft_year": 2026, "action": "restart"})
        submission = self.service.submit_pick(
            self.first_pick, {"option_value": "Repository Rookie"}, self.gm, is_admin=False
        )
        decision = self.service.decide_pick_request(
            int(submission["request"]["id"]), "approved", self.admin,
            request=submission["request"],
        )
        self.assertEqual("approved", decision["request"]["status"])

        self.db.update_setting("rookie_scale_2026_1", "10000000")
        processed = self.service.process_results(2026)
        self.assertTrue(processed["ok"])
        self.assertEqual(1, len(processed["created_cap_holds"]))
        self.assertEqual("draft-results:2026:process", processed["command_id"])
        self.assertEqual("valid", processed["validation_result"])
        self.assertEqual(1, processed["entity_versions"]["created_cap_holds"])

        history_result = self.service.import_history({"draft_year": 2019, "selections": self.historical_rows(2019)})
        self.assertEqual(60, history_result["imported_count"])


if __name__ == "__main__":
    unittest.main()
