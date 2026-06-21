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
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, now, now),
    )
    return int(cur.lastrowid)


class TradeValidationServerTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-trade-validation-", suffix=".db")
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

    def test_trade_machine_validation_rejects_restricted_pick(self) -> None:
        pick_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2026,
                "draft_pick_restricted": True,
            },
        )

        result = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2025,
                "selections": [
                    {"type": "pick", "id": pick_id, "from_team": "ATL", "to_team": "BOS"},
                ],
            }
        )

        self.assertEqual("illegal", result["status"])
        self.assertTrue(
            any(issue["severity"] == "illegal" and issue["rule"] == "restricted_pick" for issue in result["issues"])
        )

    def test_process_payload_validation_rejects_restricted_pick_before_mutation(self) -> None:
        pick_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2026,
                "draft_pick_restricted": True,
            },
        )

        result = self.db.trade_validation_from_process_payload(
            {
                "team_a": "ATL",
                "team_b": "BOS",
                "pick_ids_a": [pick_id],
                "players_a": [],
                "players_b": [],
            }
        )

        self.assertEqual("illegal", result["status"])
        self.assertTrue(
            any(issue["severity"] == "illegal" and issue["rule"] == "restricted_pick" for issue in result["issues"])
        )


if __name__ == "__main__":
    unittest.main()
