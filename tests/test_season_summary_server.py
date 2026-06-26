import io
import os
import sqlite3
import tempfile
import unittest
import zipfile

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

    def test_salary_floor_lifts_cap_total_when_free_agency_mode_is_off(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("free_agency_mode", "0")
        self.db.update_setting("salary_cap_2025", "100000000")
        self.db.update_setting("salary_floor_2025", "90000000")
        self.db.create_player(
            "ATL",
            {
                "name": "Below Floor Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2025_text": "50000000",
            },
        )

        team = self.db.get_team("ATL")
        tracker = self.db.list_tracker(2025)
        tracker_row = next(row for row in tracker["rows"] if row["team_code"] == "ATL")
        summary = team["summary"]

        self.assertEqual(50_000_000, round(float(summary["cap_figure_before_floor"])))
        self.assertEqual(40_000_000, round(float(summary["salary_floor_adjustment"])))
        self.assertEqual(90_000_000, round(float(summary["cap_figure"])))
        self.assertEqual(50_000_000, round(float(summary["payroll"])))
        self.assertEqual(50_000_000, round(float(summary["apron_account"])))
        self.assertEqual(90_000_000, round(float(tracker_row["cap_total"])))

    def test_salary_floor_does_not_apply_in_free_agency_mode(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("free_agency_mode", "1")
        self.db.update_setting("salary_cap_2025", "100000000")
        self.db.update_setting("salary_floor_2025", "90000000")
        self.db.create_player(
            "ATL",
            {
                "name": "Free Agency Floor Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2025_text": "50000000",
            },
        )

        team = self.db.get_team("ATL")
        summary = team["season_summaries"]["2025"]

        self.assertLess(float(summary["cap_figure"]), 90_000_000)
        self.assertEqual(0, round(float(summary["salary_floor_adjustment"])))

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

    def test_approved_gap_option_request_remains_visible_on_team_payload(self) -> None:
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Gap Option Player",
                "bird_rights": "R",
                "position": "SG",
                "salary_2026_text": "2500000",
                "option_2026": "GAP",
            },
        )
        self.assertIsNotNone(player_id)
        request = self.db.create_gm_option_request(
            int(player_id),
            "option_2026",
            "GAP",
            "accepted",
            {"email": "gm@example.com", "name": "GM"},
        )
        self.assertIsNotNone(request)

        self.assertTrue(self.db.update_player(int(player_id), {"option_2026": "GAP"}))
        self.assertIsNotNone(
            self.db.mark_gm_option_request_decided(
                int(request["id"]),
                "approved",
                {"email": "admin@example.com", "name": "Admin"},
            )
        )
        team = self.db.get_team("ATL")
        player = next(p for p in team["players"] if p["id"] == player_id)
        decision = player["option_decisions"]["option_2026"]

        self.assertEqual("GAP", player["option_2026"])
        self.assertEqual("GAP", decision["option_value"])
        self.assertEqual("accepted", decision["action"])
        self.assertEqual("approved", decision["status"])

    def test_gm_can_request_bird_rights_renounce_in_free_agency_mode(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("free_agency_mode", "1")
        self.db.update_setting("salary_cap_2026", "154647000")
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Bird Hold Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2025_text": "10000000",
                "salary_2026_text": "FB",
            },
        )
        self.assertIsNotNone(player_id)

        request = self.db.create_gm_bird_rights_renounce_request(
            int(player_id),
            2026,
            "FB",
            {"email": "gm@example.com", "name": "GM"},
        )

        self.assertIsNotNone(request)
        self.assertEqual("bird_rights_renounce", request["request_type"])
        self.assertEqual("renounced", request["action"])
        self.assertEqual("salary_2026_text", request["option_field"])
        self.assertEqual("FB", request["option_value"])

        team_before = self.db.get_team("ATL")
        summary_before = team_before["season_summaries"]["2026"]
        self.assertGreater(round(float(summary_before["cap_figure"])), 0)

        self.assertTrue(self.db.update_player(int(player_id), {"salary_2026_text": None}))
        self.assertIsNotNone(
            self.db.mark_gm_option_request_decided(
                int(request["id"]),
                "approved",
                {"email": "admin@example.com", "name": "Admin"},
            )
        )
        player_after = self.db.get_player_record(int(player_id))
        self.assertIsNotNone(player_after)
        self.assertIsNone(player_after["salary_2026_text"])
        self.assertIsNone(player_after["salary_2026_num"])

    def test_progress_to_next_year_moves_players_without_new_year_contract_to_free_agents(self) -> None:
        self.db.update_setting("current_year", "2025")
        expired_player_id = self.db.create_player(
            "ATL",
            {
                "name": "Expired Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2025_text": "10000000",
            },
        )
        hold_player_id = self.db.create_player(
            "ATL",
            {
                "name": "Held Player",
                "bird_rights": "Reg",
                "position": "SF",
                "salary_2025_text": "5000000",
                "salary_2026_text": "NB",
            },
        )
        self.assertIsNotNone(expired_player_id)
        self.assertIsNotNone(hold_player_id)

        result = self.db.progress_to_next_year()

        self.assertEqual(2026, result["current_year"])
        self.assertEqual(1, result["players_moved_to_free_agents"])
        self.assertIsNone(self.db.get_player_record(int(expired_player_id)))
        self.assertIsNotNone(self.db.get_player_record(int(hold_player_id)))
        free_agents = self.db.list_free_agents()
        self.assertTrue(any(agent["name"] == "Expired Player" for agent in free_agents))

    def test_progress_to_next_year_preserves_season_dependent_cash_and_move_phase(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("trade_move_phase", "post30")
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE teams SET cash_received = ?, cash_sent = ? WHERE code = ?",
                (123_456, 654_321, "ATL"),
            )
            conn.commit()

        result = self.db.progress_to_next_year()
        settings = self.db.get_settings()
        team = self.db.get_team("ATL")

        self.assertEqual(2026, result["current_year"])
        self.assertEqual("post30", settings["trade_move_phase"])
        self.assertIsNotNone(team)
        self.assertEqual(123_456, round(float(team["team"]["cash_received"])))
        self.assertEqual(654_321, round(float(team["team"]["cash_sent"])))

    def test_progress_to_next_year_rolls_draft_assets_by_later_season_year(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.assertIsNotNone(
            self.db.create_asset(
                "ATL",
                {
                    "asset_type": "draft_pick",
                    "year": 2025,
                    "label": "Legacy 2025 1st",
                    "draft_pick_type": "own",
                    "draft_round": "1st",
                },
            )
        )
        self.assertIsNotNone(
            self.db.create_asset(
                "ATL",
                {
                    "asset_type": "draft_pick",
                    "year": 2026,
                    "label": "Current 2026 1st",
                    "draft_pick_type": "own",
                    "draft_round": "1st",
                },
            )
        )
        self.assertIsNotNone(
            self.db.create_asset(
                "ATL",
                {
                    "asset_type": "draft_pick",
                    "year": 2026,
                    "label": "Current 2026 2nd",
                    "draft_pick_type": "own",
                    "draft_round": "2nd",
                },
            )
        )
        self.assertIsNotNone(
            self.db.create_asset(
                "ATL",
                {
                    "asset_type": "draft_pick",
                    "year": 2033,
                    "label": "Manual 2033 1st sold",
                    "draft_pick_type": "sold",
                    "draft_round": "1st",
                    "draft_pick_sold_to": ["BOS"],
                },
            )
        )

        result = self.db.progress_to_next_year()
        team = self.db.get_team("ATL")
        assets = [asset for asset in team["assets"] if asset["asset_type"] == "draft_pick"]
        picks_2033 = [asset for asset in assets if int(asset["year"]) == 2033]

        self.assertEqual(2026, result["current_year"])
        self.assertEqual(2, result["deleted_draft_assets"])
        self.assertEqual([{"year": 2026, "count": 2}], result["deleted_draft_asset_years"])
        self.assertEqual([2033], result["future_draft_asset_years"])
        self.assertEqual(1, result["created_future_draft_assets"])
        self.assertTrue(any(int(asset["year"]) == 2025 for asset in assets))
        self.assertFalse(any(int(asset["year"]) == 2026 for asset in assets))
        self.assertEqual(1, sum(1 for asset in picks_2033 if asset["draft_round"] == "1st"))
        self.assertEqual(1, sum(1 for asset in picks_2033 if asset["draft_round"] == "2nd"))
        self.assertTrue(any(asset["draft_round"] == "1st" and asset["draft_pick_type"] == "sold" for asset in picks_2033))
        self.assertTrue(any(asset["draft_round"] == "2nd" and asset["draft_pick_type"] == "own" for asset in picks_2033))

    def test_offseason_exception_estimate_over_cap_below_first_apron(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("salary_cap_2025", "154647000")
        self.db.create_player(
            "ATL",
            {
                "name": "Over Cap Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2025_text": "160000000",
            },
        )

        team = self.db.get_team("ATL")
        estimate = team["exception_estimates"]["2025"]

        self.assertEqual("over_cap_below_first", estimate["operating_mode"])
        self.assertEqual(["ntmle", "bae"], [item["key"] for item in estimate["eligible"]])

    def test_offseason_exception_estimate_above_second_apron_has_no_main_exception(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("salary_cap_2025", "154647000")
        self.db.create_player(
            "ATL",
            {
                "name": "Second Apron Player",
                "bird_rights": "Reg",
                "position": "PF",
                "salary_2025_text": "220000000",
            },
        )

        team = self.db.get_team("ATL")
        estimate = team["exception_estimates"]["2025"]

        self.assertEqual("above_second_apron", estimate["operating_mode"])
        self.assertEqual([], estimate["eligible"])

    def test_generate_offseason_exceptions_is_idempotent(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("salary_cap_2025", "154647000")
        self.db.create_player(
            "ATL",
            {
                "name": "Generated Exception Player",
                "bird_rights": "Reg",
                "position": "C",
                "salary_2025_text": "160000000",
            },
        )

        first = self.db.generate_offseason_exceptions(2025)
        second = self.db.generate_offseason_exceptions(2025)
        team = self.db.get_team("ATL")
        generated = [
            asset for asset in team["assets"]
            if asset.get("asset_type") == "exception"
            and asset.get("generated_exception_season") == 2025
        ]

        self.assertEqual(2, sum(len(row["created"]) for row in first["generated"]))
        self.assertEqual(2, sum(len(row["created"]) for row in second["generated"]))
        self.assertEqual(2, len(generated))
        self.assertEqual({"ntmle", "bae"}, {asset["generated_exception_key"] for asset in generated})

    def test_generate_offseason_exceptions_uses_choice_for_small_cap_space_team(self) -> None:
        self.db.update_setting("current_year", "2025")
        self.db.update_setting("salary_cap_2025", "154647000")
        self.db.create_player(
            "ATL",
            {
                "name": "Small Room Player",
                "bird_rights": "Reg",
                "position": "PG",
                "salary_2025_text": "150000000",
            },
        )

        skipped = self.db.generate_offseason_exceptions(2025)
        chosen = self.db.generate_offseason_exceptions(2025, choices={"ATL": "room"})
        team = self.db.get_team("ATL")
        generated = [
            asset for asset in team["assets"]
            if asset.get("asset_type") == "exception"
            and asset.get("generated_exception_season") == 2025
        ]

        self.assertEqual("choice_pending", team["exception_estimates"]["2025"]["operating_mode"])
        self.assertEqual(1, len(skipped["skipped"]))
        self.assertEqual(1, sum(len(row["created"]) for row in chosen["generated"]))
        self.assertEqual(["room_mle"], [asset["generated_exception_key"] for asset in generated])

    def test_league_export_workbook_contains_public_league_sheets(self) -> None:
        self.db.create_player(
            "ATL",
            {
                "name": "Export Test Player",
                "bird_rights": "Reg",
                "position": "PG",
                "salary_2025_text": "1234567",
            },
        )

        workbook = self.db.export_league_workbook()

        with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
            names = set(archive.namelist())
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("xl/workbook.xml", names)
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertIn('name="Resumen"', workbook_xml)
            self.assertIn('name="Roster"', workbook_xml)
            worksheets = "\n".join(
                archive.read(name).decode("utf-8")
                for name in sorted(names)
                if name.startswith("xl/worksheets/")
            )
            self.assertIn("Export Test Player", worksheets)
            self.assertIn("Atlanta Hawks", worksheets)


if __name__ == "__main__":
    unittest.main()
