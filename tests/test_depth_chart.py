import os
import sqlite3
import tempfile
import unittest

from app.server import LeagueDB
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> None:
    now = now_iso()
    conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, now, now),
    )


class TeamDepthChartTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-depth-chart-", suffix=".db")
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
        atl_guard = self.db.create_player(
            "ATL",
            {"name": "Depth Guard", "position": "PG", "rating": "80", "salary_2026_text": "10000000"},
        )
        atl_wing = self.db.create_player(
            "ATL",
            {"name": "Depth Wing", "position": "SF", "rating": "78", "salary_2026_text": "8000000"},
        )
        bos_player = self.db.create_player(
            "BOS",
            {"name": "Other Team Player", "position": "C", "rating": "75", "salary_2026_text": "5000000"},
        )
        self.assertIsNotNone(atl_guard)
        self.assertIsNotNone(atl_wing)
        self.assertIsNotNone(bos_player)
        self.atl_guard_id = int(atl_guard)
        self.atl_wing_id = int(atl_wing)
        self.bos_player_id = int(bos_player)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_team_depth_chart_can_be_saved_and_loaded_from_team_payload(self) -> None:
        chart = self.db.set_team_depth_chart(
            "ATL",
            [
                {"position": "PG", "depth_order": 1, "player_id": self.atl_guard_id},
                {"position": "SF", "depth_order": 2, "player_id": self.atl_wing_id},
            ],
        )

        self.assertTrue(chart["configured"])
        self.assertEqual(["PG", "SG", "SF", "PF", "C"], chart["positions"])
        self.assertEqual(6, chart["max_depth"])
        self.assertEqual(
            [
                ("PG", 1, "Depth Guard"),
                ("SF", 2, "Depth Wing"),
            ],
            [
                (entry["position"], entry["depth_order"], entry["player"]["name"])
                for entry in chart["entries"]
            ],
        )

        team = self.db.get_team("ATL")
        self.assertIsNotNone(team)
        self.assertTrue(team["depth_chart"]["configured"])
        self.assertEqual(2, len(team["depth_chart"]["entries"]))

    def test_team_depth_chart_rejects_duplicate_player_or_cell(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate_player"):
            self.db.set_team_depth_chart(
                "ATL",
                [
                    {"position": "PG", "depth_order": 1, "player_id": self.atl_guard_id},
                    {"position": "SG", "depth_order": 1, "player_id": self.atl_guard_id},
                ],
            )

        with self.assertRaisesRegex(ValueError, "duplicate_depth_cell"):
            self.db.set_team_depth_chart(
                "ATL",
                [
                    {"position": "PG", "depth_order": 1, "player_id": self.atl_guard_id},
                    {"position": "PG", "depth_order": 1, "player_id": self.atl_wing_id},
                ],
            )

    def test_team_depth_chart_rejects_players_from_another_team(self) -> None:
        with self.assertRaisesRegex(ValueError, "player_not_on_team"):
            self.db.set_team_depth_chart(
                "ATL",
                [{"position": "C", "depth_order": 1, "player_id": self.bos_player_id}],
            )


if __name__ == "__main__":
    unittest.main()
