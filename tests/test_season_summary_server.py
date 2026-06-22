import os
import sqlite3
import tempfile
import unittest

from app.server import LeagueDB
from app.domain_rules import minimum_salary_for_season
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


class SeasonSummaryServerTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-season-summary-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_free_agency_cap_hold_counts_for_cap_but_not_apron(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("free_agency_mode", "1")
        self.db.update_setting("salary_cap_2025", "154647000")
        self.db.update_setting("salary_cap_2026", "154647000")
        self.db.update_setting("average_salary_2025", "10000000")

        self.db.create_player(
            "ATL",
            {
                "name": "QO Hold Player",
                "bird_rights": "R",
                "position": "SF",
                "salary_2025_text": "4000000",
                "salary_2026_text": "QO",
                "option_2026": "QO",
            },
        )

        team = self.db.get_team("ATL")
        self.assertIsNotNone(team)
        summary_2026 = team["season_summaries"]["2026"]
        rookie_minimum = minimum_salary_for_season(154_647_000, 0, 1)
        open_roster_hold = 11 * rookie_minimum

        self.assertEqual(11, int(summary_2026["open_roster_spot_count"]))
        self.assertEqual(open_roster_hold, float(summary_2026["open_roster_spot_cap_hold"]))
        self.assertEqual(12_000_000 + open_roster_hold, round(float(summary_2026["cap_figure"])))
        self.assertEqual(0, round(float(summary_2026["apron_account"])))
        self.assertEqual(
            float(summary_2026["room_to_cap"]),
            float(summary_2026["salary_cap"]) - float(summary_2026["cap_figure"]),
        )

    def test_tracker_uses_same_current_summary_as_team_payload(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("salary_cap_2025", "154647000")

        self.db.create_player(
            "ATL",
            {
                "name": "Tracker Salary Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2025_text": "200000000",
            },
        )

        team = self.db.get_team("ATL")
        self.assertIsNotNone(team)
        tracker = self.db.list_tracker()
        tracker_row = next(row for row in tracker["rows"] if row["team_code"] == "ATL")
        summary = team["summary"]

        self.assertEqual(2025, tracker["season_year"])
        self.assertEqual(round(float(summary["cap_figure"])), round(float(tracker_row["cap_total"])))
        self.assertEqual(round(float(summary["payroll"])), round(float(tracker_row["gasto_total"])))
        self.assertEqual(round(float(summary["room_to_cap"])), round(float(tracker_row["espacio_cap"])))
        self.assertEqual(round(float(summary["room_to_luxury"])), round(float(tracker_row["espacio_luxury"])))
        self.assertEqual(round(float(summary["room_to_first_apron"])), round(float(tracker_row["espacio_1er_apron"])))
        self.assertEqual(round(float(summary["room_to_second_apron"])), round(float(tracker_row["espacio_2do_apron"])))
        self.assertEqual(round(float(summary["luxury_tax"])), round(float(tracker_row["luxury_tax"])))
        self.assertIn("apron_hard_cap", tracker_row)

    def test_tracker_uses_free_agency_default_season(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("free_agency_mode", "1")
        self.db.update_setting("salary_cap_2025", "154647000")
        self.db.update_setting("salary_cap_2026", "154647000")
        self.db.update_setting("average_salary_2025", "10000000")

        self.db.create_player(
            "ATL",
            {
                "name": "Future Hold Player",
                "bird_rights": "R",
                "position": "PF",
                "salary_2025_text": "4000000",
                "salary_2026_text": "QO",
                "option_2026": "QO",
            },
        )

        team = self.db.get_team("ATL")
        self.assertIsNotNone(team)
        tracker = self.db.list_tracker()
        tracker_row = next(row for row in tracker["rows"] if row["team_code"] == "ATL")
        summary = team["season_summaries"]["2026"]

        self.assertEqual(2026, tracker["season_year"])
        self.assertEqual(round(float(summary["cap_figure"])), round(float(tracker_row["cap_total"])))
        self.assertEqual(round(float(summary["payroll"])), round(float(tracker_row["gasto_total"])))
        self.assertEqual(round(float(summary["room_to_cap"])), round(float(tracker_row["espacio_cap"])))
        self.assertEqual(round(float(summary["room_to_luxury"])), round(float(tracker_row["espacio_luxury"])))
        self.assertEqual(round(float(summary["room_to_first_apron"])), round(float(tracker_row["espacio_1er_apron"])))
        self.assertEqual(round(float(summary["room_to_second_apron"])), round(float(tracker_row["espacio_2do_apron"])))
        self.assertEqual(round(float(summary["luxury_tax"])), round(float(tracker_row["luxury_tax"])))

    def test_tracker_can_select_future_season_and_hard_cap(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.assertTrue(self.db.update_team_apron_hard_cap("ATL", 2026, "second"))
        self.db.create_player(
            "ATL",
            {
                "name": "Future Salary Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2026_text": "30000000",
            },
        )

        tracker = self.db.list_tracker(2026)
        tracker_row = next(row for row in tracker["rows"] if row["team_code"] == "ATL")
        team = self.db.get_team("ATL")
        summary = team["season_summaries"]["2026"]

        self.assertEqual(2026, tracker["season_year"])
        self.assertEqual([2025, 2026, 2027, 2028, 2029, 2030], tracker["seasons"])
        self.assertEqual("second", tracker_row["apron_hard_cap"])
        self.assertEqual(round(float(summary["cap_figure"])), round(float(tracker_row["cap_total"])))


if __name__ == "__main__":
    unittest.main()
