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

    def test_trade_archive_import_rejects_oversized_batches(self) -> None:
        service = TradeArchiveService(self.db._trade_archive_repository, max_import_trades=1)

        with self.assertRaisesRegex(ValueError, "too_many_trades"):
            service.import_trades([{}, {}])


if __name__ == "__main__":
    unittest.main()
