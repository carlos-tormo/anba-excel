import os
import sqlite3
import tempfile
import unittest

from app.server import Handler, LeagueDB
from app.services.notifications import NotificationCompositionService
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

    def _two_team_player_trade(self):
        atl_player_id = self.db.create_player(
            "ATL",
            {
                "name": "Atlanta Trade Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2026_text": "10000000",
            },
        )
        bos_player_id = self.db.create_player(
            "BOS",
            {
                "name": "Boston Trade Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2026_text": "10000000",
            },
        )
        payload = {
            "teams": ["ATL", "BOS"],
            "season": 2026,
            "trade_bucket": "pre30",
            "selections": [
                {
                    "type": "player",
                    "id": atl_player_id,
                    "from_team": "ATL",
                    "to_team": "BOS",
                },
                {
                    "type": "player",
                    "id": bos_player_id,
                    "from_team": "BOS",
                    "to_team": "ATL",
                },
            ],
            "cash": [],
        }
        return atl_player_id, bos_player_id, payload

    def _player_team_code(self, player_id: int) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT teams.code
                FROM players
                JOIN teams ON teams.id = players.team_id
                WHERE players.id = ?
                """,
                (player_id,),
            ).fetchone()
        return str(row[0]) if row else ""

    def test_trade_validation_signature_ignores_browser_derived_fields(self) -> None:
        _atl_player_id, _bos_player_id, payload = self._two_team_player_trade()
        clean = self.db.validate_trade_machine(payload)
        browser_claims = self.db.validate_trade_machine(
            {
                **payload,
                "salary_totals": {"ATL": 1, "BOS": 999999999},
                "matching_status": "legal",
                "tax_position": {"ATL": "under_cap"},
                "exception_eligibility": ["NTMLE"],
                "roster_counts": {"ATL": 1},
                "stepien_compliance": True,
                "hard_cap_consequences": [],
            }
        )

        self.assertEqual(clean["validation_hash"], browser_claims["validation_hash"])
        self.assertEqual(clean["rules_version"], browser_claims["rules_version"])
        self.assertEqual(64, len(clean["validation_hash"]))

    def test_trade_command_requires_validation_signature_without_mutating(self) -> None:
        atl_player_id, bos_player_id, payload = self._two_team_player_trade()

        command = self.db.process_trade_command(
            payload,
            require_validation_hash=True,
            notify_discord=False,
        )

        self.assertEqual("trade_validation_required", command["error"])
        self.assertEqual("ATL", self._player_team_code(atl_player_id))
        self.assertEqual("BOS", self._player_team_code(bos_player_id))

    def test_trade_command_rejects_stale_signature_without_mutating(self) -> None:
        atl_player_id, bos_player_id, payload = self._two_team_player_trade()
        preview = self.db.validate_trade_machine(payload)
        self.assertTrue(self.db.update_player(atl_player_id, {"salary_2026_text": "12000000"}))

        command = self.db.process_trade_command(
            payload,
            expected_validation_hash=preview["validation_hash"],
            require_validation_hash=True,
            notify_discord=False,
        )

        self.assertEqual("trade_validation_stale", command["error"])
        self.assertNotEqual(preview["validation_hash"], command["validation"]["validation_hash"])
        self.assertEqual("ATL", self._player_team_code(atl_player_id))
        self.assertEqual("BOS", self._player_team_code(bos_player_id))

    def test_trade_command_revalidates_and_processes_signed_source_inputs(self) -> None:
        atl_player_id, bos_player_id, payload = self._two_team_player_trade()
        preview = self.db.validate_trade_machine(payload)
        self.assertNotEqual("illegal", preview["status"])

        command = self.db.process_trade_command(
            payload,
            expected_validation_hash=preview["validation_hash"],
            require_validation_hash=True,
            notify_discord=False,
        )

        self.assertIsNotNone(command["result"])
        self.assertEqual(preview["validation_hash"], command["validation"]["validation_hash"])
        self.assertEqual("BOS", self._player_team_code(atl_player_id))
        self.assertEqual("ATL", self._player_team_code(bos_player_id))

    def test_discord_trade_summary_lists_pick_rounds(self) -> None:
        result = NotificationCompositionService.trade_asset_summary(
            ["Example Player"],
            2,
            0,
            1,
            ["2028 1ST (ATL)", "2029 2ND (BOS)"],
            ["Swap 2030 1ST (CHA)"],
        )

        self.assertIn("- Example Player", result)
        self.assertIn("- 2028 1ª ronda (ATL)", result)
        self.assertIn("- 2029 2ª ronda (BOS)", result)
        self.assertIn("- Swap 2030 1ª ronda (CHA)", result)
        self.assertNotIn("2 ronda(s) del draft", result)

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

    def test_validation_counts_received_players_for_trade_moves(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO team_move_logs (
                    team_id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
                ) VALUES (?, 2026, 'pre30', 20, 'trade', 'seed', 'Seed usage', '{}', ?)
                """,
                (team_id, now_iso()),
            )
            conn.commit()
        player_id = self.db.create_player(
            "BOS",
            {
                "name": "Incoming Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2026_text": "1000000",
            },
        )

        result = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2026,
                "selections": [
                    {"type": "player", "id": player_id, "from_team": "BOS", "to_team": "ATL"},
                ],
            }
        )

        self.assertTrue(
            any(
                issue["severity"] == "illegal"
                and issue["rule"] == "moves"
                and issue["teamCode"] == "ATL"
                and "Necesita 1 movimiento" in issue["message"]
                for issue in result["issues"]
            )
        )

    def test_cap_hold_assets_move_open_roster_minimum_without_roster_limit_slot(self) -> None:
        self.db.update_setting("free_agency_mode", "1")
        self.db.update_setting("current_year", "2026")
        self.db.update_setting("average_salary_2025", "13254485")
        for idx in range(10):
            self.db.create_player(
                "ATL",
                {
                    "name": f"Active {idx}",
                    "bird_rights": "Reg",
                    "position": "SG",
                    "salary_2026_text": "10000000",
                },
            )
        hold_player_id = self.db.create_player(
            "ATL",
            {
                "name": "Bird Rights Hold",
                "bird_rights": "Reg",
                "position": "SF",
                "salary_2025_text": "5000000",
                "salary_2026_text": "FB",
            },
        )

        result = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2026,
                "selections": [
                    {"type": "player", "id": hold_player_id, "from_team": "ATL", "to_team": "BOS"},
                ],
            }
        )
        atl_flow = result["flows"]["ATL"]
        bos_flow = result["flows"]["BOS"]

        self.assertEqual(10, atl_flow["beforeRosterStandard"])
        self.assertEqual(10, atl_flow["postRosterStandard"])
        self.assertEqual(11, atl_flow["beforeOpenRosterSpotRosterCount"])
        self.assertEqual(10, atl_flow["postOpenRosterSpotRosterCount"])
        self.assertEqual(0, bos_flow["beforeRosterStandard"])
        self.assertEqual(0, bos_flow["postRosterStandard"])
        self.assertEqual(0, bos_flow["beforeOpenRosterSpotRosterCount"])
        self.assertEqual(1, bos_flow["postOpenRosterSpotRosterCount"])

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

    def test_trade_machine_validation_rejects_frozen_pick(self) -> None:
        pick_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2026,
                "draft_pick_frozen": True,
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
            any(issue["severity"] == "illegal" and issue["rule"] == "frozen_pick" for issue in result["issues"])
        )

    def test_second_apron_rollover_freezes_newly_available_first(self) -> None:
        self.db.create_player(
            "ATL",
            {
                "name": "Second Apron Player",
                "position": "SF",
                "salary_2025_text": "220000000",
            },
        )

        result = self.db.update_current_year(2026)
        team = self.db.get_team("ATL")
        frozen_rows = team["frozen_draft_picks"]
        frozen_pick = next(
            (
                asset
                for asset in team["assets"]
                if asset["asset_type"] == "draft_pick"
                and int(asset["year"]) == 2033
                and asset["draft_round"] == "1st"
            ),
            None,
        )

        self.assertEqual(1, result["frozen_picks_created"])
        self.assertEqual(1, len(frozen_rows))
        self.assertEqual(2025, int(frozen_rows[0]["penalty_season_year"]))
        self.assertEqual(2033, int(frozen_rows[0]["draft_year"]))
        self.assertIsNotNone(frozen_pick)
        self.assertEqual(1, int(frozen_pick["draft_pick_frozen"]))

    def test_aggregation_triggers_second_apron_hard_cap_even_when_salary_decreases(self) -> None:
        outgoing_a = self.db.create_player(
            "ATL",
            {"name": "Outgoing One", "position": "SG", "salary_2026_text": "9000000"},
        )
        outgoing_b = self.db.create_player(
            "ATL",
            {"name": "Outgoing Two", "position": "PF", "salary_2026_text": "8000000"},
        )
        incoming = self.db.create_player(
            "BOS",
            {"name": "Incoming Lower", "position": "PG", "salary_2026_text": "11000000"},
        )

        result = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2026,
                "selections": [
                    {"type": "player", "id": outgoing_a, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "player", "id": outgoing_b, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "player", "id": incoming, "from_team": "BOS", "to_team": "ATL"},
                ],
            }
        )

        self.assertTrue(
            any(
                issue["severity"] == "warning"
                and issue["rule"] == "hard_cap_trigger"
                and issue["teamCode"] == "ATL"
                and "2do apron" in issue["message"]
                for issue in result["issues"]
            )
        )

    def test_incoming_minimum_salary_is_excluded_from_salary_matching_only(self) -> None:
        outgoing = self.db.create_player(
            "ATL",
            {"name": "Outgoing Salary", "position": "SG", "salary_2026_text": "10000000"},
        )
        incoming_regular = self.db.create_player(
            "BOS",
            {"name": "Incoming Regular", "position": "PF", "salary_2026_text": "10000000"},
        )
        incoming_minimum = self.db.create_player(
            "BOS",
            {"name": "Incoming Minimum", "position": "PG", "salary_2026_text": "2048494"},
        )

        result = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2026,
                "selections": [
                    {"type": "player", "id": outgoing, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "player", "id": incoming_regular, "from_team": "BOS", "to_team": "ATL"},
                    {"type": "player", "id": incoming_minimum, "from_team": "BOS", "to_team": "ATL"},
                ],
            }
        )

        atl_flow = result["flows"]["ATL"]
        bos_flow = result["flows"]["BOS"]

        self.assertEqual(12048494.0, atl_flow["incomingSalary"])
        self.assertEqual(10000000.0, atl_flow["incomingMatchingSalary"])
        self.assertEqual(12048494.0, bos_flow["outgoingSalary"])
        self.assertEqual(12048494.0, bos_flow["outgoingMatchingSalary"])
        self.assertFalse(
            any(issue["severity"] == "illegal" and issue["rule"] == "salary" and issue["teamCode"] == "ATL" for issue in result["issues"])
        )

    def test_apron_hard_cap_is_scoped_by_season(self) -> None:
        self.assertTrue(self.db.update_team_apron_hard_cap("ATL", 2025, "first"))

        team = self.db.get_team("ATL")

        self.assertEqual("first", team["season_summaries"]["2025"]["apron_hard_cap"])
        self.assertEqual("", team["season_summaries"]["2026"]["apron_hard_cap"])
        by_year = {int(row["season_year"]): row["hard_cap"] for row in team["apron_hard_caps"]}
        self.assertEqual("first", by_year[2025])
        self.assertEqual("", by_year[2026])

    def test_trade_hard_cap_trigger_persists_to_matching_season(self) -> None:
        outgoing_a = self.db.create_player(
            "ATL",
            {"name": "Outgoing One", "position": "SG", "salary_2026_text": "9000000"},
        )
        outgoing_b = self.db.create_player(
            "ATL",
            {"name": "Outgoing Two", "position": "PF", "salary_2026_text": "8000000"},
        )
        incoming = self.db.create_player(
            "BOS",
            {"name": "Incoming Lower", "position": "PG", "salary_2026_text": "11000000"},
        )
        validation = self.db.validate_trade_machine(
            {
                "teams": ["ATL", "BOS"],
                "season": 2026,
                "selections": [
                    {"type": "player", "id": outgoing_a, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "player", "id": outgoing_b, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "player", "id": incoming, "from_team": "BOS", "to_team": "ATL"},
                ],
            }
        )

        applied = self.db.apply_trade_hard_cap_triggers(validation, 2026)
        team = self.db.get_team("ATL")

        self.assertEqual([{"team_code": "ATL", "season_year": 2026, "hard_cap": "second"}], applied)
        self.assertEqual("", team["season_summaries"]["2025"]["apron_hard_cap"])
        self.assertEqual("second", team["season_summaries"]["2026"]["apron_hard_cap"])

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

    def test_selection_process_moves_acquired_pick_without_selling_source_own_pick(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            insert_team(conn, "MIA", "Miami Heat")
            insert_team(conn, "DAL", "Dallas Mavericks")
            conn.commit()
        mia_own_pick_id = self.db.create_asset(
            "MIA",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2027,
                "label": "1st pick",
            },
        )
        dal_pick_id = self.db.create_asset(
            "MIA",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "acquired",
                "draft_round": "1st",
                "year": 2027,
                "original_owner": "DAL",
                "label": "1st pick",
                "detail": "DAL acquired pick",
                "draft_pick_protected": True,
            },
        )

        result = self.db.process_trade_from_payload(
            {
                "teams": ["MIA", "ATL"],
                "season": 2026,
                "selections": [
                    {"type": "pick", "id": dal_pick_id, "from_team": "MIA", "to_team": "ATL"},
                ],
            }
        )

        self.assertIsNotNone(result)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            source_own_pick = conn.execute(
                "SELECT draft_pick_type, draft_pick_sold_to FROM assets WHERE id = ?",
                (mia_own_pick_id,),
            ).fetchone()
            moved_pick = conn.execute(
                """
                SELECT a.draft_pick_type, a.original_owner, a.draft_pick_protected, t.code
                FROM assets a
                JOIN teams t ON t.id = a.team_id
                WHERE a.id = ?
                """,
                (dal_pick_id,),
            ).fetchone()
            remaining_source_dal_picks = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM assets a
                JOIN teams t ON t.id = a.team_id
                WHERE t.code = 'MIA'
                  AND a.asset_type = 'draft_pick'
                  AND CAST(a.year AS INTEGER) = 2027
                  AND a.draft_round = '1st'
                  AND a.original_owner = 'DAL'
                """,
            ).fetchone()["cnt"]

        self.assertEqual("own", source_own_pick["draft_pick_type"])
        self.assertIsNone(source_own_pick["draft_pick_sold_to"])
        self.assertEqual("ATL", moved_pick["code"])
        self.assertEqual("acquired", moved_pick["draft_pick_type"])
        self.assertEqual("DAL", moved_pick["original_owner"])
        self.assertEqual(1, moved_pick["draft_pick_protected"])
        self.assertEqual(0, remaining_source_dal_picks)

    def test_legacy_process_moves_selected_future_second_round_pick(self) -> None:
        player_id = self.db.create_player(
            "BOS",
            {
                "name": "Return Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2026_text": "10000000",
            },
        )
        pick_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "2nd",
                "year": 2030,
                "label": "2nd pick",
                "draft_pick_protected": True,
            },
        )

        result = self.db.process_trade(
            "ATL",
            "BOS",
            [],
            [player_id],
            pick_ids_a=[pick_id],
        )

        self.assertIsNotNone(result)
        self.assertEqual(["2030 2ND (ATL)"], result["pick_refs_a"])
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            source_pick = conn.execute(
                "SELECT draft_pick_type, draft_pick_sold_to FROM assets WHERE id = ?",
                (pick_id,),
            ).fetchone()
            acquired_pick = conn.execute(
                """
                SELECT a.draft_pick_type, a.draft_round, a.original_owner, a.draft_pick_protected, t.code
                FROM assets a
                JOIN teams t ON t.id = a.team_id
                WHERE t.code = 'BOS' AND a.asset_type = 'draft_pick' AND CAST(a.year AS INTEGER) = 2030
                """,
            ).fetchone()

        self.assertEqual("sold", source_pick["draft_pick_type"])
        self.assertEqual("BOS", source_pick["draft_pick_sold_to"])
        self.assertIsNotNone(acquired_pick)
        self.assertEqual("acquired", acquired_pick["draft_pick_type"])
        self.assertEqual("2nd", acquired_pick["draft_round"])
        self.assertEqual("ATL", acquired_pick["original_owner"])
        self.assertEqual(1, acquired_pick["draft_pick_protected"])

    def test_legacy_process_moves_acquired_pick_without_selling_source_own_pick(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            insert_team(conn, "MIA", "Miami Heat")
            insert_team(conn, "DAL", "Dallas Mavericks")
            conn.commit()
        mia_own_pick_id = self.db.create_asset(
            "MIA",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "2nd",
                "year": 2028,
                "label": "2nd pick",
            },
        )
        dal_pick_id = self.db.create_asset(
            "MIA",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "acquired",
                "draft_round": "2nd",
                "year": 2028,
                "original_owner": "DAL",
                "label": "2nd pick",
                "detail": "DAL acquired pick",
            },
        )
        player_id = self.db.create_player(
            "ATL",
            {
                "name": "Return Player",
                "bird_rights": "Reg",
                "position": "SG",
                "salary_2026_text": "10000000",
            },
        )

        result = self.db.process_trade("MIA", "ATL", [], [player_id], pick_ids_a=[dal_pick_id])

        self.assertIsNotNone(result)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            source_own_pick = conn.execute(
                "SELECT draft_pick_type, draft_pick_sold_to FROM assets WHERE id = ?",
                (mia_own_pick_id,),
            ).fetchone()
            moved_pick = conn.execute(
                """
                SELECT a.draft_pick_type, a.original_owner, t.code
                FROM assets a
                JOIN teams t ON t.id = a.team_id
                WHERE a.id = ?
                """,
                (dal_pick_id,),
            ).fetchone()

        self.assertEqual("own", source_own_pick["draft_pick_type"])
        self.assertIsNone(source_own_pick["draft_pick_sold_to"])
        self.assertEqual("ATL", moved_pick["code"])
        self.assertEqual("acquired", moved_pick["draft_pick_type"])
        self.assertEqual("DAL", moved_pick["original_owner"])

    def test_draft_pick_ledger_detects_duplicate_and_missing_picks(self) -> None:
        self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2027,
                "label": "1st pick",
            },
        )
        self.db.create_asset(
            "BOS",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "acquired",
                "draft_round": "1st",
                "year": 2027,
                "original_owner": "ATL",
                "label": "1st pick",
            },
        )
        self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "2nd",
                "year": 2027,
                "label": "2nd pick",
            },
        )
        self.db.create_asset(
            "BOS",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2027,
                "label": "1st pick",
            },
        )

        ledger = self.db.list_draft_pick_ledger(2027)
        rows_by_team = {row["team_code"]: row for row in ledger["rows"]}

        self.assertEqual("duplicate", rows_by_team["ATL"]["first"]["status"])
        self.assertEqual(["ATL", "BOS"], rows_by_team["ATL"]["first"]["holder_team_codes"])
        self.assertEqual("ok", rows_by_team["ATL"]["second"]["status"])
        self.assertEqual("ok", rows_by_team["BOS"]["first"]["status"])
        self.assertEqual("missing", rows_by_team["BOS"]["second"]["status"])
        self.assertEqual(2, ledger["summary"]["error"])
        self.assertTrue(any(issue["rule"] == "duplicate_pick" for issue in ledger["issues"]))
        self.assertTrue(any(issue["rule"] == "missing_pick" for issue in ledger["issues"]))

    def test_draft_pick_ledger_reports_acquired_pick_holder(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            insert_team(conn, "DAL", "Dallas Mavericks")
            conn.commit()
        pick_id = self.db.create_asset(
            "BOS",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "acquired",
                "draft_round": "2nd",
                "year": 2028,
                "original_owner": "DAL",
                "label": "2nd pick",
            },
        )

        ledger = self.db.list_draft_pick_ledger(2028)
        rows_by_team = {row["team_code"]: row for row in ledger["rows"]}

        self.assertEqual("ok", rows_by_team["DAL"]["second"]["status"])
        self.assertEqual(["BOS"], rows_by_team["DAL"]["second"]["holder_team_codes"])
        self.assertEqual([pick_id], rows_by_team["DAL"]["second"]["asset_ids"])
        self.assertEqual("2028-2ND-DAL", rows_by_team["DAL"]["second"]["canonical_id"])

    def test_move_summaries_reset_by_season(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO team_move_logs (
                    team_id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
                ) VALUES (?, 2025, 'pre30', 5, 'trade', 'test', 'Current season trade', '{}', ?)
                """,
                (team_id, now_iso()),
            )
            conn.commit()

        current_team = self.db.get_team("ATL", move_season_year=2025)
        future_team = self.db.get_team("ATL", move_season_year=2026)

        self.assertEqual(15, current_team["move_summary"]["remaining_pre30"])
        self.assertEqual(20, future_team["move_summary"]["remaining_pre30"])
        self.assertEqual(4, future_team["move_summary"]["remaining_post30"])

    def test_post30_trade_counts_players_and_next_first_before_post30(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO team_move_logs (
                    team_id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
                ) VALUES (?, 2026, 'pre30', 19, 'trade', 'seed', 'Seed usage', '{}', ?)
                """,
                (team_id, now_iso()),
            )
            conn.commit()
        player_ids = [
            self.db.create_player(
                "ATL",
                {
                    "name": f"Move Player {idx}",
                    "bird_rights": "Reg",
                    "position": "SG",
                    "salary_2026_text": "1000000",
                },
            )
            for idx in range(2)
        ]
        next_first_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2027,
                "label": "1st pick",
            },
        )
        future_first_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "draft_pick_type": "own",
                "draft_round": "1st",
                "year": 2028,
                "label": "1st pick",
            },
        )
        right_id = self.db.create_asset("ATL", {"asset_type": "player_right", "label": "Rights Player"})

        result = self.db.process_trade_from_payload(
            {
                "teams": ["ATL", "BOS"],
                "season": 2026,
                "trade_bucket": "post30",
                "selections": [
                    *[
                        {"type": "player", "id": player_id, "from_team": "ATL", "to_team": "BOS"}
                        for player_id in player_ids
                    ],
                    {"type": "pick", "id": next_first_id, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "pick", "id": future_first_id, "from_team": "ATL", "to_team": "BOS"},
                    {"type": "right", "id": right_id, "from_team": "ATL", "to_team": "BOS"},
                ],
            }
        )

        self.assertIsNotNone(result)
        self.assertEqual(3, result["team_a"]["move_count"])
        self.assertEqual(3, result["team_b"]["move_count"])
        team = self.db.get_team("ATL", move_season_year=2026)
        self.assertEqual(20, team["move_summary"]["used_pre30"])
        self.assertEqual(2, team["move_summary"]["used_post30"])
        allocated = [
            (row["bucket"], row["delta"])
            for row in team["move_summary"]["log"]
            if row["source_type"] == "trade" and row["source_ref"] != "seed"
        ]
        self.assertIn(("pre30", 1), allocated)
        self.assertIn(("post30", 2), allocated)


if __name__ == "__main__":
    unittest.main()
