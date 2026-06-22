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

    def test_stepien_restricted_pick_only_allows_swap_action(self) -> None:
        pick_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2026,
                "draft_pick_stepien_restricted": True,
            },
        )

        send_result = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2025,
                "selections": [
                    {
                        "type": "pick",
                        "id": pick_id,
                        "from_team": "ATL",
                        "to_team": "BOS",
                        "pick_action": "send_pick",
                    },
                ],
            }
        )
        self.assertEqual("illegal", send_result["status"])
        self.assertTrue(
            any(issue["severity"] == "illegal" and issue["rule"] == "restricted_pick" for issue in send_result["issues"])
        )

        swap_result = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2025,
                "selections": [
                    {
                        "type": "pick",
                        "id": pick_id,
                        "from_team": "ATL",
                        "to_team": "BOS",
                        "pick_action": "swap_rights",
                    },
                ],
            }
        )
        self.assertFalse(
            any(issue["severity"] == "illegal" and issue["rule"] == "restricted_pick" for issue in swap_result["issues"])
        )

    def test_process_payload_validation_allows_stepien_swap_action(self) -> None:
        pick_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2026,
                "draft_pick_stepien_restricted": True,
            },
        )

        send_result = self.db.trade_validation_from_process_payload(
            {
                "team_a": "ATL",
                "team_b": "BOS",
                "pick_ids_a": [pick_id],
                "players_a": [],
                "players_b": [],
            }
        )
        self.assertEqual("illegal", send_result["status"])
        self.assertTrue(
            any(issue["severity"] == "illegal" and issue["rule"] == "restricted_pick" for issue in send_result["issues"])
        )

        swap_result = self.db.trade_validation_from_process_payload(
            {
                "team_a": "ATL",
                "team_b": "BOS",
                "pick_ids_a": [pick_id],
                "pick_actions_a": {str(pick_id): "swap_rights"},
                "players_a": [],
                "players_b": [],
            }
        )
        self.assertFalse(
            any(issue["severity"] == "illegal" and issue["rule"] == "restricted_pick" for issue in swap_result["issues"])
        )

    def test_selection_process_moves_future_second_round_picks_and_player_rights(self) -> None:
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Trade Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2026_text": "10000000",
            },
        )
        pick_id = self.db.create_asset(
            "BOS",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "2nd",
                "year": 2029,
                "label": "2nd pick",
            },
        )
        right_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "player_right",
                "label": "Rights Player",
                "detail": "Draft rights",
            },
        )

        result = self.db.process_trade_from_payload(
            {
                "teams": ["ATL", "BOS"],
                "season": 2026,
                "selections": [
                    {"type": "player", "id": player_id, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "right", "id": right_id, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "pick", "id": pick_id, "from_team": "BOS", "to_team": "ATL"},
                ],
            }
        )

        self.assertIsNotNone(result)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            player_team = conn.execute(
                """
                SELECT t.code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (player_id,),
            ).fetchone()["code"]
            right_team = conn.execute(
                """
                SELECT t.code
                FROM assets a
                JOIN teams t ON t.id = a.team_id
                WHERE a.id = ?
                """,
                (right_id,),
            ).fetchone()["code"]
            source_pick = conn.execute("SELECT draft_pick_type, draft_pick_sold_to FROM assets WHERE id = ?", (pick_id,)).fetchone()
            acquired_pick = conn.execute(
                """
                SELECT a.draft_pick_type, a.draft_round, a.original_owner, t.code
                FROM assets a
                JOIN teams t ON t.id = a.team_id
                WHERE t.code = 'ATL' AND a.asset_type = 'draft_pick' AND CAST(a.year AS INTEGER) = 2029
                """,
            ).fetchone()

        self.assertEqual("BOS", player_team)
        self.assertEqual("BOS", right_team)
        self.assertEqual("sold", source_pick["draft_pick_type"])
        self.assertEqual("ATL", source_pick["draft_pick_sold_to"])
        self.assertIsNotNone(acquired_pick)
        self.assertEqual("acquired", acquired_pick["draft_pick_type"])
        self.assertEqual("2nd", acquired_pick["draft_round"])
        self.assertEqual("BOS", acquired_pick["original_owner"])


if __name__ == "__main__":
    unittest.main()
