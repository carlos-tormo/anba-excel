import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.services.trade_archive import TradeArchiveService
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


class TradeArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-trade-archive-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with connect_test_db(self.db_path) as conn:
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

    def test_manual_trade_archive_create_list_update_delete(self) -> None:
        service = self.db._trade_archive_repository
        trade = service.create(
            {
                "external_trade_id": "legacy-1",
                "trade_date": "2026-07-01",
                "season_year": 2026,
                "team_movements": [
                    {
                        "team_code": "ATL",
                        "gm_name": "ATL GM",
                        "sent": {"players": ["Player A"]},
                        "received": {"picks": ["2027 BOS 1st"]},
                    },
                    {
                        "team_code": "BOS",
                        "sent": {"picks": ["2027 BOS 1st"]},
                        "received": {"players": ["Player A"]},
                    },
                ],
            }
        )

        self.assertEqual(2, trade["total_assets_moved"])
        self.assertEqual("ATL GM", trade["team_movements"][0]["gm_name"])
        listed = service.list()
        self.assertEqual([2026], [season["season_year"] for season in listed["seasons"]])
        self.assertEqual(["ATL", "BOS"], listed["trades"][0]["teams"])

        updated = service.update(trade["id"], {"notes": "corrected"})
        self.assertEqual("corrected", updated["notes"])
        self.assertEqual(2, updated["version"])

        self.assertTrue(service.delete(trade["id"]))
        self.assertEqual([], service.list()["trades"])

    def test_trade_archive_import_reports_row_errors(self) -> None:
        result = TradeArchiveService(self.db._trade_archive_repository).import_trades(
            {
                "trades": [
                    {
                        "trade_date": "2025-02-01",
                        "season_year": 2025,
                        "team_movements": [
                            {"team_code": "ATL", "sent": {"players": ["A"]}, "received": {}},
                            {"team_code": "BOS", "sent": {}, "received": {"players": ["A"]}},
                        ],
                    },
                    {"season_year": 2025, "team_movements": []},
                ]
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(2, result["total"])
        self.assertEqual(1, len(result["created"]))
        self.assertEqual([{"index": 1, "error": "trade_date_required"}], result["errors"])

    def test_trade_archive_import_accepts_raw_json_array(self) -> None:
        result = TradeArchiveService(self.db._trade_archive_repository).import_trades(
            [
                {
                    "trade_id": "past-1",
                    "date": "2024-08-10",
                    "season": 2024,
                    "teams": [
                        {"code": "ATL", "gm": "Imported ATL GM", "sent": {"players": ["A"]}, "received": {"rights": ["B rights"]}},
                        {"code": "BOS", "sent": {"rights": ["B rights"]}, "received": {"players": ["A"]}},
                    ],
                }
            ]
        )

        self.assertTrue(result["ok"])
        self.assertEqual(1, result["total"])
        self.assertEqual("past-1", result["created"][0]["trade_id"])
        self.assertEqual(["ATL", "BOS"], result["created"][0]["teams"])
        self.assertEqual("Imported ATL GM", result["created"][0]["team_movements"][0]["gm_name"])
        self.assertIsNone(result["created"][0]["team_movements"][1]["gm_name"])

    def test_trade_archive_import_enriches_structured_draft_pick_references(self) -> None:
        result = TradeArchiveService(self.db._trade_archive_repository).import_trades(
            [
                {
                    "trade_id": "pick-ref-1",
                    "date": "2024-08-10",
                    "season": 2024,
                    "teams": [
                        {
                            "code": "ATL",
                            "sent": {"players": ["A"]},
                            "received": {
                                "picks": [
                                    {
                                        "label": "2027 BOS 1st",
                                        "draft_year": 2027,
                                        "draft_round": "1st",
                                        "original_team_code": "BOS",
                                    }
                                ]
                            },
                        },
                        {
                            "code": "BOS",
                            "sent": {
                                "picks": [
                                    {
                                        "draft_year": 2027,
                                        "draft_round": "1st",
                                        "original_team_code": "BOS",
                                    }
                                ]
                            },
                            "received": {"players": ["A"]},
                        },
                    ],
                }
            ]
        )

        self.assertTrue(result["ok"])
        movements = {row["team_code"]: row for row in result["created"][0]["team_movements"]}
        atl_pick = movements["ATL"]["received"]["picks"][0]
        bos_pick = movements["BOS"]["sent"]["picks"][0]
        self.assertEqual("2027-1ST-BOS", atl_pick["canonical_id"])
        self.assertEqual("2027-1ST-BOS", bos_pick["canonical_id"])
        self.assertEqual(atl_pick["draft_pick_id"], bos_pick["draft_pick_id"])
        self.assertEqual("2027 BOS 1st", atl_pick["label"])

    def test_trade_archive_read_enriches_pick_refs_with_historical_selection(self) -> None:
        timestamp = now_iso()
        with connect_test_db(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO draft_picks (
                    draft_year, draft_round, original_team, created_at, updated_at
                ) VALUES (2019, '2nd', 'BOS', ?, ?)
                """,
                (timestamp, timestamp),
            )
            draft_pick_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO draft_history_selections (
                    draft_year, pick_number, draft_round, round_pick_number,
                    player_name, selecting_team_code, original_team_code, draft_pick_id,
                    notes, imported_at, created_at, updated_at
                ) VALUES (2019, 59, '2nd', 29, 'Shamorie Ponds', 'ATL', 'BOS', ?, NULL, ?, ?, ?)
                """,
                (draft_pick_id, timestamp, timestamp, timestamp),
            )
            conn.commit()

        result = TradeArchiveService(self.db._trade_archive_repository).import_trades(
            [
                {
                    "trade_id": "history-pick-1",
                    "date": "2018-11-07",
                    "season": 2018,
                    "teams": [
                        {
                            "code": "ATL",
                            "sent": {},
                            "received": {
                                "picks": [
                                    {
                                        "label": "2ª ronda BOS 2019",
                                        "draft_year": 2019,
                                        "draft_round": "2nd",
                                        "original_team_code": "BOS",
                                    }
                                ]
                            },
                        },
                        {
                            "code": "BOS",
                            "sent": {
                                "picks": [
                                    {
                                        "label": "2ª ronda BOS 2019",
                                        "draft_pick_id": draft_pick_id,
                                    }
                                ]
                            },
                            "received": {},
                        },
                    ],
                }
            ]
        )

        self.assertTrue(result["ok"])
        listed = self.db._trade_archive_repository.list(season_year=2018)["trades"][0]
        movements = {row["team_code"]: row for row in listed["team_movements"]}
        received_pick = movements["ATL"]["received"]["picks"][0]
        sent_pick = movements["BOS"]["sent"]["picks"][0]
        self.assertEqual("2019-2ND-BOS", received_pick["draft_selection"]["canonical_id"])
        self.assertEqual(59, received_pick["draft_selection"]["pick_number"])
        self.assertEqual("Shamorie Ponds", received_pick["draft_selection"]["player_name"])
        self.assertEqual("ATL", received_pick["draft_selection"]["selecting_team_code"])
        self.assertEqual(received_pick["draft_selection"], sent_pick["draft_selection"])

    def test_trade_archive_uses_timeline_gm_when_import_has_no_override(self) -> None:
        with connect_test_db(self.db_path) as conn:
            timestamp = now_iso()
            atl_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            bos_id = conn.execute("SELECT id FROM teams WHERE code = 'BOS'").fetchone()["id"]
            conn.executemany(
                """
                INSERT INTO team_gm_history (
                    team_id, row_order, gm_name, start_date, color, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                """,
                [
                    (atl_id, 1, "Old ATL GM", "2023-07-01", timestamp, timestamp),
                    (atl_id, 2, "Current ATL GM", "2024-07-01", timestamp, timestamp),
                    (bos_id, 1, "Future BOS GM", "2026-07-01", timestamp, timestamp),
                ],
            )
            conn.commit()

        trade = self.db._trade_archive_repository.create(
            {
                "external_trade_id": "timeline-1",
                "trade_date": "2025-02-01",
                "season_year": 2024,
                "team_movements": [
                    {"team_code": "ATL", "sent": {"players": ["A"]}, "received": {}},
                    {"team_code": "BOS", "gm_name": "Imported BOS GM", "sent": {}, "received": {"players": ["A"]}},
                ],
            }
        )

        movements = {row["team_code"]: row for row in trade["team_movements"]}
        self.assertIsNone(movements["ATL"]["gm_name"])
        self.assertEqual("Current ATL GM", movements["ATL"]["timeline_gm_name"])
        self.assertEqual("Imported BOS GM", movements["BOS"]["gm_name"])
        self.assertIsNone(movements["BOS"]["timeline_gm_name"])

        listed = self.db._trade_archive_repository.list()["trades"][0]
        listed_movements = {row["team_code"]: row for row in listed["team_movements"]}
        self.assertEqual("Current ATL GM", listed_movements["ATL"]["timeline_gm_name"])
        self.assertIsNone(listed_movements["BOS"]["timeline_gm_name"])

        updated = TradeArchiveService(self.db._trade_archive_repository).update(
            trade["id"],
            {
                "trade_date": "2023-08-01",
                "team_movements": listed["team_movements"],
            },
        )
        updated_movements = {row["team_code"]: row for row in updated["team_movements"]}
        self.assertIsNone(updated_movements["ATL"]["gm_name"])
        self.assertEqual("Old ATL GM", updated_movements["ATL"]["timeline_gm_name"])
        self.assertEqual("Imported BOS GM", updated_movements["BOS"]["gm_name"])
        self.assertIsNone(updated_movements["BOS"]["timeline_gm_name"])

    def test_trade_archive_falls_back_to_assigned_user_when_no_timeline_gm_exists(self) -> None:
        user = self.db.upsert_google_user("google-atl-gm", "atl@example.com", "Google ATL", None)
        self.db.replace_user_team_assignments(user["id"], ["ATL"], username="Assigned ATL GM")

        trade = self.db._trade_archive_repository.create(
            {
                "external_trade_id": "assigned-1",
                "trade_date": "2025-02-01",
                "season_year": 2024,
                "team_movements": [
                    {"team_code": "ATL", "sent": {"players": ["A"]}, "received": {}},
                    {"team_code": "BOS", "sent": {}, "received": {"players": ["A"]}},
                ],
            }
        )

        movements = {row["team_code"]: row for row in trade["team_movements"]}
        self.assertIsNone(movements["ATL"]["gm_name"])
        self.assertEqual("Assigned ATL GM", movements["ATL"]["timeline_gm_name"])
        self.assertIsNone(movements["BOS"]["timeline_gm_name"])

    def test_trade_archive_import_rejects_oversized_batches(self) -> None:
        service = TradeArchiveService(self.db._trade_archive_repository, max_import_trades=1)

        with self.assertRaisesRegex(ValueError, "too_many_trades"):
            service.import_trades([{}, {}])


if __name__ == "__main__":
    unittest.main()
