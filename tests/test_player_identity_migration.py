import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

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
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195946000, 207825000, ?, ?)
        """,
        (code, name, now, now),
    )
    return int(cur.lastrowid)


def insert_legacy_player(conn: sqlite3.Connection, team_id: int, name: str, row_order: int) -> int:
    now = now_iso()
    cur = conn.execute(
        """
        INSERT INTO players (
            team_id, row_order, bird_rights, rating, name, position, years_left,
            salary_2025_text, salary_2025_num,
            salary_2026_text, salary_2026_num,
            notes, is_two_way, created_at, updated_at
        ) VALUES (?, ?, 'Reg', '70', ?, 'PG', 1, '1000000', 1000000, '1100000', 1100000, NULL, 0, ?, ?)
        """,
        (team_id, row_order, name, now, now),
    )
    return int(cur.lastrowid)


class PlayerIdentityMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-player-identity-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            atl_id = insert_team(conn, "ATL", "Atlanta Hawks")
            bos_id = insert_team(conn, "BOS", "Boston Celtics")
            self.legacy_atl_player_id = insert_legacy_player(conn, atl_id, "Legacy Hawk", 1)
            self.legacy_bos_player_id = insert_legacy_player(conn, bos_id, "Legacy Celtic", 1)
            now = now_iso()
            conn.execute(
                """
                INSERT INTO free_agents (
                    name, position, bird_rights, rating, years_left, notes, created_at, updated_at
                ) VALUES ('Legacy Free Agent', 'SG', 'Reg', '68', 1, NULL, ?, ?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO assets (
                    team_id, row_order, asset_type, year, label, detail,
                    amount_text, amount_num, created_at, updated_at
                ) VALUES (?, 99, 'dead_cap', NULL, 'Legacy Dead Money', NULL, '500000', 500000, ?, ?)
                """,
                (atl_id, now, now),
            )
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def _profile_id_for_player(self, player_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute("SELECT profile_id FROM players WHERE id = ?", (player_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertIsNotNone(row["profile_id"])
            return int(row["profile_id"])

    def test_legacy_migration_backfills_profiles_and_installs_guards(self) -> None:
        self.db.assert_player_identity_integrity()

        with self.db.connect() as conn:
            self.assertEqual(
                0,
                conn.execute("SELECT COUNT(*) FROM players WHERE profile_id IS NULL").fetchone()[0],
            )
            self.assertEqual(
                0,
                conn.execute("SELECT COUNT(*) FROM free_agents WHERE profile_id IS NULL").fetchone()[0],
            )
            self.assertEqual(
                0,
                conn.execute("SELECT COUNT(*) FROM dead_contracts WHERE profile_id IS NULL").fetchone()[0],
            )
            player_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(players)").fetchall()
            }
            self.assertIn("row_state", player_cols)
            self.assertEqual(
                0,
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM players
                    WHERE row_state IS NULL
                       OR row_state NOT IN ('active_contract', 'retained_rights')
                    """
                ).fetchone()[0],
            )
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO players (
                        team_id, row_order, name, created_at, updated_at
                    ) VALUES (?, 500, 'No Profile', ?, ?)
                    """,
                    (team_id, now_iso(), now_iso()),
                )

    def test_transaction_backfill_skips_orphan_profile_ids_from_admin_logs(self) -> None:
        now = now_iso()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_logs (
                    created_at, actor_email, actor_name, action, entity, entity_id,
                    team_code, details_json
                ) VALUES (?, 'admin@example.com', 'Admin', 'update', 'player', '999999', 'ATL', ?)
                """,
                (
                    now,
                    '{"profile_id":999999,"player_name":"Orphaned Historical Player"}',
                ),
            )
            conn.commit()

        with self.db.connect() as conn:
            self.db._backfill_player_transactions(conn)
            conn.commit()
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM player_transactions WHERE profile_id = 999999"
                ).fetchone()[0],
            )

    def test_player_happiness_is_private_admin_profile_data(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)

        self.assertTrue(self.db.update_player_profile(profile_id, {"happiness": 7.5}))

        public_player = next(
            player for player in self.db.list_players()
            if int(player["profile_id"]) == profile_id
        )
        private_player = next(
            player for player in self.db.list_players(include_private=True)
            if int(player["profile_id"]) == profile_id
        )

        self.assertNotIn("happiness", public_player)
        self.assertEqual(7.5, private_player["happiness"])
        with self.assertRaises(ValueError):
            self.db.update_player_profile(profile_id, {"happiness": 11})

    def test_list_players_tolerates_missing_salary_history_table(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DROP TABLE IF EXISTS player_salary_history")
            conn.commit()

        players = self.db.list_players(include_private=True)

        self.assertGreaterEqual(len(players), 1)
        self.assertTrue(any(player["name"] == "Legacy Hawk" for player in players))

    def test_merge_player_profiles_keeps_dead_contracts_with_active_contract(self) -> None:
        active_player_id = self.db.create_player(
            "BOS",
            {
                "name": "Ty Jerome",
                "position": "PG",
                "rating": "75",
                "bird_rights": "Mid",
                "salary_2026_text": "9.975.000",
            },
        )
        self.assertIsNotNone(active_player_id)
        target_profile_id = self._profile_id_for_player(int(active_player_id))

        now = now_iso()
        with self.db.connect() as conn:
            source_cur = conn.execute(
                """
                INSERT INTO player_profiles (name, created_at, updated_at)
                VALUES ('Ty Jerome', ?, ?)
                """,
                (now, now),
            )
            source_profile_id = int(source_cur.lastrowid)
            atl_team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            dead_cur = conn.execute(
                """
                INSERT INTO dead_contracts (
                    team_id, profile_id, row_order, dead_type, label, amount_text, amount_num,
                    salary_2026_text, salary_2026_num, created_at, updated_at
                ) VALUES (?, ?, 1, 'normal', 'Ty Jerome', '765425', 765425, '765425', 765425, ?, ?)
                """,
                (atl_team_id, source_profile_id, now, now),
            )
            dead_contract_id = int(dead_cur.lastrowid)
            conn.commit()

        result = self.db.merge_player_profiles(source_profile_id, target_profile_id)

        self.assertTrue(result["ok"])
        with self.db.connect() as conn:
            self.assertIsNone(
                conn.execute("SELECT id FROM player_profiles WHERE id = ?", (source_profile_id,)).fetchone()
            )
            dead_row = conn.execute(
                "SELECT profile_id FROM dead_contracts WHERE id = ?",
                (dead_contract_id,),
            ).fetchone()
            self.assertIsNotNone(dead_row)
            self.assertEqual(target_profile_id, int(dead_row["profile_id"]))
            player_rows = conn.execute(
                "SELECT id, profile_id FROM players WHERE profile_id = ?",
                (target_profile_id,),
            ).fetchall()
            self.assertEqual(1, len(player_rows))
            self.assertEqual(int(active_player_id), int(player_rows[0]["id"]))
            alias = conn.execute(
                "SELECT target_profile_id FROM player_profile_aliases WHERE old_profile_id = ?",
                (source_profile_id,),
            ).fetchone()
            self.assertIsNotNone(alias)
            self.assertEqual(target_profile_id, int(alias["target_profile_id"]))

    def test_merge_player_profiles_blocks_two_active_contracts(self) -> None:
        first_player_id = self.db.create_player(
            "ATL",
            {
                "name": "Duplicate Active A",
                "position": "SG",
                "salary_2026_text": "5.000.000",
            },
        )
        second_player_id = self.db.create_player(
            "BOS",
            {
                "name": "Duplicate Active B",
                "position": "SG",
                "salary_2026_text": "6.000.000",
            },
        )
        self.assertIsNotNone(first_player_id)
        self.assertIsNotNone(second_player_id)

        result = self.db.merge_player_profiles(
            self._profile_id_for_player(int(first_player_id)),
            self._profile_id_for_player(int(second_player_id)),
        )

        self.assertFalse(result["ok"])
        self.assertEqual("active_contract_conflict", result["error"])

    def test_create_player_rejects_duplicate_active_profile(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        with self.assertRaises(ValueError):
            self.db.create_player("BOS", {"name": "Duplicate Contract", "profile_id": profile_id})
        self.db.assert_player_identity_integrity()

    def test_retained_rights_row_does_not_block_active_contract_profile(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        now = now_iso()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('current_year', '2026', ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE players
                SET salary_2025_text = NULL,
                    salary_2025_num = NULL,
                    salary_2026_text = 'FB',
                    salary_2026_num = NULL,
                    salary_2027_text = NULL,
                    salary_2027_num = NULL,
                    salary_2028_text = NULL,
                    salary_2028_num = NULL,
                    salary_2029_text = NULL,
                    salary_2029_num = NULL,
                    salary_2030_text = NULL,
                    salary_2030_num = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, self.legacy_atl_player_id),
            )
            conn.commit()

        new_id = self.db.create_player(
            "BOS",
            {
                "name": "Legacy Hawk",
                "profile_id": profile_id,
                "position": "PG",
                "salary_2026_text": "4.000.000",
            },
        )

        self.assertIsNotNone(new_id)
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, row_state FROM players WHERE profile_id = ? ORDER BY id",
                (profile_id,),
            ).fetchall()
            self.assertEqual(2, len(rows))
            self.assertEqual("retained_rights", rows[0]["row_state"])
            self.assertEqual("active_contract", rows[1]["row_state"])
            bos_team_id = conn.execute("SELECT id FROM teams WHERE code = 'BOS'").fetchone()["id"]
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO players (
                        team_id, profile_id, row_state, row_order,
                        bird_rights, rating, name, position, years_left,
                        salary_2026_text, salary_2026_num,
                        notes, is_two_way, created_at, updated_at
                    ) VALUES (?, ?, 'active_contract', 999, 'Reg', '70', 'Duplicate Active',
                        'PG', 1, '5.000.000', 5000000, NULL, 0, ?, ?)
                    """,
                    (bos_team_id, profile_id, now_iso(), now_iso()),
                )
        self.db.assert_player_identity_integrity()

    def test_draft_pick_assets_are_synced_to_canonical_identity(self) -> None:
        asset_id = self.db.create_asset(
            "ATL",
            {
                "asset_type": "draft_pick",
                "year": 2027,
                "draft_round": "1st",
                "draft_pick_type": "acquired",
                "original_owner": "DAL",
                "label": "2027 1st DAL",
                "detail": "Top protected",
            },
        )

        self.assertIsNotNone(asset_id)
        with self.db.connect() as conn:
            pick = conn.execute(
                """
                SELECT id
                FROM draft_picks
                WHERE draft_year = 2027
                  AND draft_round = '1st'
                  AND original_team = 'DAL'
                """
            ).fetchone()
            self.assertIsNotNone(pick)
            holding = conn.execute(
                """
                SELECT holder_team, asset_id, conditions, holding_type
                FROM draft_pick_holdings
                WHERE draft_pick_id = ?
                """,
                (pick["id"],),
            ).fetchone()
            self.assertIsNotNone(holding)
            self.assertEqual("ATL", holding["holder_team"])
            self.assertEqual(asset_id, int(holding["asset_id"]))
            self.assertEqual("Top protected", holding["conditions"])
            self.assertEqual("acquired", holding["holding_type"])
        self.db.assert_player_identity_integrity()

    def test_profile_can_have_active_contract_and_multiple_dead_contracts(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)

        atl_dead_id = self.db.create_dead_contract(
            "ATL",
            {"label": "Legacy Hawk", "profile_id": profile_id, "salary_2025_text": "250000"},
        )
        bos_dead_id = self.db.create_dead_contract(
            "BOS",
            {"label": "Legacy Hawk", "profile_id": profile_id, "salary_2025_text": "500000"},
        )

        self.assertIsNotNone(atl_dead_id)
        self.assertIsNotNone(bos_dead_id)
        with self.db.connect() as conn:
            active_count = conn.execute(
                "SELECT COUNT(*) FROM players WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()[0]
            dead_rows = conn.execute(
                """
                SELECT d.profile_id, t.code AS team_code
                FROM dead_contracts d
                JOIN teams t ON t.id = d.team_id
                WHERE d.profile_id = ?
                ORDER BY t.code
                """,
                (profile_id,),
            ).fetchall()
            self.assertEqual(1, active_count)
            self.assertEqual(["ATL", "BOS"], [row["team_code"] for row in dead_rows])

        profile = next(
            player for player in self.db.list_players()
            if int(player["profile_id"]) == profile_id
        )
        self.assertTrue(profile["active_contract"])
        self.assertEqual("active", profile["status"])
        self.assertEqual(2, profile["dead_contract_count"])
        self.assertEqual(
            ["ATL", "BOS"],
            sorted(item["team_code"] for item in profile["dead_contracts"]),
        )
        self.db.assert_player_identity_integrity()

    def test_remove_player_from_roster_moves_profile_to_free_agents_without_dead_contract(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)

        result = self.db.remove_player_from_roster(self.legacy_atl_player_id)

        self.assertIsNotNone(result)
        self.assertEqual("ATL", result["team_code"])
        self.assertEqual(profile_id, result["profile_id"])
        self.assertIsNotNone(result["free_agent_id"])
        with self.db.connect() as conn:
            self.assertIsNone(
                conn.execute("SELECT id FROM players WHERE id = ?", (self.legacy_atl_player_id,)).fetchone()
            )
            free_agent = conn.execute(
                """
                SELECT name, bird_rights, years_left, free_agent_type, source, rights_team_code, notes
                FROM free_agents
                WHERE profile_id = ?
                """,
                (profile_id,),
            ).fetchone()
            self.assertIsNotNone(free_agent)
            self.assertEqual("Legacy Hawk", free_agent["name"])
            self.assertIsNone(free_agent["bird_rights"])
            self.assertIsNone(free_agent["years_left"])
            self.assertEqual("No restringido", free_agent["free_agent_type"])
            self.assertEqual("uncontracted_profile", free_agent["source"])
            self.assertIsNone(free_agent["rights_team_code"])
            self.assertIsNone(free_agent["notes"])
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM dead_contracts WHERE profile_id = ?",
                    (profile_id,),
                ).fetchone()[0],
            )
            transaction = conn.execute(
                """
                SELECT action, free_agent_id, dead_contract_id, from_team_code
                FROM player_transactions
                WHERE profile_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (profile_id,),
            ).fetchone()
            self.assertIsNotNone(transaction)
            self.assertEqual("remove", transaction["action"])
            self.assertEqual(result["free_agent_id"], transaction["free_agent_id"])
            self.assertIsNone(transaction["dead_contract_id"])
            self.assertEqual("ATL", transaction["from_team_code"])
        self.db.assert_player_identity_integrity()

    def test_delete_player_profile_removes_linked_rows(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        now = now_iso()

        self.db.create_dead_contract(
            "ATL",
            {"label": "Legacy Hawk", "profile_id": profile_id, "salary_2025_text": "250000"},
        )
        self.db.create_player_transaction(
            profile_id,
            {"summary": "Manual cleanup marker", "action": "manual", "team_code": "ATL"},
        )
        free_agent_id = None
        with self.db.connect() as conn:
            free_agent_cur = conn.execute(
                """
                INSERT INTO free_agents (
                    profile_id, name, position, bird_rights, rating, years_left,
                    free_agent_type, source, rights_team_code, agent, notes, created_at, updated_at
                ) VALUES (?, 'Legacy Hawk', 'PG', 'Reg', '70', 1, 'No restringido', 'manual', NULL, NULL, NULL, ?, ?)
                """,
                (profile_id, now, now),
            )
            free_agent_id = int(free_agent_cur.lastrowid)
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO gm_free_agent_offer_requests (
                    free_agent_id, team_id, requester_email, requester_name,
                    offer_payload_json, offer_type, status, created_at, updated_at
                ) VALUES (?, ?, 'gm@example.com', 'GM', '{}', 'free_agent_offer', 'pending', ?, ?)
                """,
                (free_agent_id, team_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO discord_free_agent_offer_threads (
                    profile_id, player_name_key, player_name, thread_id, thread_name, created_at, updated_at
                ) VALUES (?, 'legacy hawk', 'Legacy Hawk', 'thread-1', 'Legacy Hawk', ?, ?)
                """,
                (profile_id, now, now),
            )
            conn.commit()

        result = self.db.delete_player_profile(profile_id)

        self.assertTrue(result["ok"])
        self.assertEqual(1, result["deleted"]["active_contracts"])
        self.assertEqual(1, result["deleted"]["free_agents"])
        self.assertEqual(1, result["deleted"]["dead_contracts"])
        self.assertEqual(1, result["deleted"]["transactions"])
        self.assertEqual(1, result["deleted"]["discord_offer_threads"])
        self.assertEqual(1, result["deleted"]["free_agent_offer_requests"])
        with self.db.connect() as conn:
            for table in (
                "player_profiles",
                "players",
                "free_agents",
                "dead_contracts",
                "player_transactions",
                "discord_free_agent_offer_threads",
            ):
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE profile_id = ?"
                    if table != "player_profiles"
                    else "SELECT COUNT(*) FROM player_profiles WHERE id = ?",
                    (profile_id,),
                ).fetchone()[0]
                self.assertEqual(0, count, table)
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM gm_free_agent_offer_requests WHERE free_agent_id = ?",
                    (free_agent_id,),
                ).fetchone()[0],
            )

        self.db.assert_player_identity_integrity()

    def test_unavailable_player_status_hides_public_profile_and_removes_active_rows(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        now = now_iso()

        with self.db.connect() as conn:
            free_agent_cur = conn.execute(
                """
                INSERT INTO free_agents (
                    profile_id, name, position, bird_rights, rating, years_left,
                    free_agent_type, source, created_at, updated_at
                ) VALUES (?, 'Legacy Hawk', 'PG', NULL, '70', NULL, 'No restringido', 'manual', ?, ?)
                """,
                (profile_id, now, now),
            )
            free_agent_id = int(free_agent_cur.lastrowid)
            team_id = conn.execute("SELECT id FROM teams WHERE code = 'ATL'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO gm_free_agent_offer_requests (
                    free_agent_id, team_id, requester_email, requester_name,
                    offer_payload_json, offer_type, status, created_at, updated_at
                ) VALUES (?, ?, 'gm@example.com', 'GM', '{}', 'free_agent_offer', 'pending', ?, ?)
                """,
                (free_agent_id, team_id, now, now),
            )
            conn.commit()

        self.assertTrue(self.db.update_player_profile(profile_id, {"profile_status": "outside_nba"}))

        public_profiles = self.db.list_players()
        private_profiles = self.db.list_players(include_private=True)

        self.assertFalse(any(int(player["profile_id"]) == profile_id for player in public_profiles))
        unavailable = next(
            player for player in private_profiles
            if int(player["profile_id"]) == profile_id
        )
        self.assertEqual("outside_nba", unavailable["profile_status"])
        self.assertEqual("outside_nba", unavailable["status"])
        self.assertEqual("Fuera de la NBA", unavailable["status_label"])
        with self.db.connect() as conn:
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM players WHERE profile_id = ?",
                    (profile_id,),
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM free_agents WHERE profile_id = ?",
                    (profile_id,),
                ).fetchone()[0],
            )
            self.assertEqual(
                "cancelled",
                conn.execute(
                    "SELECT status FROM gm_free_agent_offer_requests WHERE free_agent_id = ?",
                    (free_agent_id,),
                ).fetchone()["status"],
            )

        self.assertFalse(
            any(int(free_agent["profile_id"]) == profile_id for free_agent in self.db.list_free_agents())
        )
        with self.assertRaises(ValueError):
            self.db.create_player("BOS", {"name": "Legacy Hawk", "profile_id": profile_id})
        self.db.assert_player_identity_integrity()

    def test_cut_then_sign_preserves_profile_identity(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)

        cut_result = self.db.cut_player(self.legacy_atl_player_id)
        self.assertIsNotNone(cut_result)
        self.assertEqual(profile_id, int(cut_result["profile_id"]))
        self.assertTrue(cut_result["waiver"])
        self.assertIsNotNone(cut_result["waiver_id"])
        self.assertIsNotNone(cut_result["dead_contract_id"])

        with self.db.connect() as conn:
            self.assertIsNone(
                conn.execute("SELECT id FROM players WHERE profile_id = ?", (profile_id,)).fetchone()
            )
            waiver = conn.execute(
                "SELECT dead_contract_id, free_agent_id, status FROM waiver_players WHERE id = ?",
                (cut_result["waiver_id"],),
            ).fetchone()
            self.assertEqual("active", waiver["status"])
            self.assertEqual(cut_result["dead_contract_id"], waiver["dead_contract_id"])
            self.assertIsNone(waiver["free_agent_id"])
            dead = conn.execute(
                "SELECT id, profile_id, label, salary_2025_num, salary_2026_num FROM dead_contracts WHERE id = ?",
                (cut_result["dead_contract_id"],),
            ).fetchone()
            self.assertEqual(profile_id, int(dead["profile_id"]))
            self.assertEqual("Legacy Hawk", dead["label"])
            self.assertEqual(1000000, dead["salary_2025_num"])
            self.assertEqual(1100000, dead["salary_2026_num"])

            conn.execute(
                "UPDATE waiver_players SET waiver_expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
                (cut_result["waiver_id"],),
            )
            conn.commit()

        expired = self.db.process_expired_waivers()
        self.assertEqual(1, expired["count"])
        self.assertEqual(cut_result["dead_contract_id"], expired["processed"][0]["dead_contract_id"])

        with self.db.connect() as conn:
            waiver = conn.execute(
                "SELECT dead_contract_id, free_agent_id, status FROM waiver_players WHERE id = ?",
                (cut_result["waiver_id"],),
            ).fetchone()
            self.assertEqual("expired", waiver["status"])
            self.assertEqual(cut_result["dead_contract_id"], waiver["dead_contract_id"])
            self.assertIsNotNone(waiver["free_agent_id"])
            free = conn.execute(
                "SELECT id, profile_id FROM free_agents WHERE id = ?",
                (waiver["free_agent_id"],),
            ).fetchone()
            self.assertEqual(profile_id, int(free["profile_id"]))
            free_agent_id = int(free["id"])

        signed_player_id = self.db.sign_free_agent(
            free_agent_id,
            "BOS",
            {"salary_2025_text": "1200000"},
        )
        self.assertIsNotNone(signed_player_id)

        with self.db.connect() as conn:
            active = conn.execute(
                """
                SELECT p.profile_id, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (signed_player_id,),
            ).fetchone()
            self.assertEqual(profile_id, int(active["profile_id"]))
            self.assertEqual("BOS", active["team_code"])
            self.assertIsNone(
                conn.execute("SELECT id FROM free_agents WHERE id = ?", (free_agent_id,)).fetchone()
            )
            actions = [
                row["action"]
                for row in conn.execute(
                    "SELECT action FROM player_transactions WHERE profile_id = ? ORDER BY id",
                    (profile_id,),
                ).fetchall()
            ]
            self.assertIn("cut", actions)
            self.assertIn("sign", actions)

        self.db.assert_player_identity_integrity()

    def test_approved_waiver_claim_removes_temporary_dead_cap(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        cut_result = self.db.cut_player(self.legacy_atl_player_id)
        self.assertIsNotNone(cut_result)
        dead_contract_id = cut_result["dead_contract_id"]

        with self.db.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = 'BOS'").fetchone()
            now = now_iso()
            claim_cur = conn.execute(
                """
                INSERT INTO waiver_claims (
                    waiver_player_id, team_id, team_code, status, created_at, updated_at
                ) VALUES (?, ?, 'BOS', 'pending', ?, ?)
                """,
                (cut_result["waiver_id"], team["id"], now, now),
            )
            claim = dict(conn.execute("SELECT * FROM waiver_claims WHERE id = ?", (claim_cur.lastrowid,)).fetchone())
            result = self.db._waiver_repository.approve_claim_conn(conn, claim, timestamp=now)
            conn.commit()

        self.assertIsNotNone(result)
        with self.db.connect() as conn:
            self.assertIsNone(conn.execute("SELECT id FROM dead_contracts WHERE id = ?", (dead_contract_id,)).fetchone())
            waiver = conn.execute(
                "SELECT status, dead_contract_id, claimed_team_code FROM waiver_players WHERE id = ?",
                (cut_result["waiver_id"],),
            ).fetchone()
            self.assertEqual("claimed", waiver["status"])
            self.assertIsNone(waiver["dead_contract_id"])
            self.assertEqual("BOS", waiver["claimed_team_code"])
            player = conn.execute(
                """
                SELECT p.id
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.profile_id = ? AND t.code = 'BOS'
                """,
                (profile_id,),
            ).fetchone()
            self.assertIsNotNone(player)

        self.db.assert_player_identity_integrity()

    def test_buyout_stretch_dead_cap_uses_adjusted_integer_amount_after_waivers(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        with self.db.connect() as conn:
            now = now_iso()
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('current_year', '2026', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE players
                SET salary_2026_text = '15000000',
                    salary_2026_num = 15000000,
                    salary_2027_text = NULL,
                    salary_2027_num = NULL
                WHERE id = ?
                """,
                (self.legacy_atl_player_id,),
            )
            conn.commit()

        cut_result = self.db.cut_player(
            self.legacy_atl_player_id,
            {
                "buyout": True,
                "stretch": True,
                "dead_cap_overrides": {"2026": "11000000"},
            },
        )
        self.assertIsNotNone(cut_result)
        self.assertTrue(cut_result["waiver"])
        dead_contract_id = cut_result["dead_contract_id"]

        with self.db.connect() as conn:
            dead = conn.execute(
                """
                SELECT profile_id, salary_2026_text, salary_2026_num,
                       salary_2027_text, salary_2027_num,
                       salary_2028_text, salary_2028_num
                FROM dead_contracts
                WHERE id = ?
                """,
                (dead_contract_id,),
            ).fetchone()
            self.assertEqual(profile_id, int(dead["profile_id"]))
            self.assertEqual("3.666.667", dead["salary_2026_text"])
            self.assertEqual(3_666_667, int(dead["salary_2026_num"]))
            self.assertEqual("3.666.667", dead["salary_2027_text"])
            self.assertEqual(3_666_667, int(dead["salary_2027_num"]))
            self.assertEqual("3.666.667", dead["salary_2028_text"])
            self.assertEqual(3_666_667, int(dead["salary_2028_num"]))

            conn.execute(
                "UPDATE waiver_players SET waiver_expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
                (cut_result["waiver_id"],),
            )
            conn.commit()

        expired = self.db.process_expired_waivers()
        self.assertEqual(1, expired["count"])
        self.assertEqual(dead_contract_id, expired["processed"][0]["dead_contract_id"])

        with self.db.connect() as conn:
            dead = conn.execute(
                """
                SELECT salary_2026_text, salary_2026_num,
                       salary_2027_text, salary_2027_num,
                       salary_2028_text, salary_2028_num
                FROM dead_contracts
                WHERE id = ?
                """,
                (dead_contract_id,),
            ).fetchone()
            self.assertIsNotNone(dead)
            self.assertEqual("3.666.667", dead["salary_2026_text"])
            self.assertEqual(3_666_667, int(dead["salary_2026_num"]))
            self.assertEqual("3.666.667", dead["salary_2027_text"])
            self.assertEqual(3_666_667, int(dead["salary_2027_num"]))
            self.assertEqual("3.666.667", dead["salary_2028_text"])
            self.assertEqual(3_666_667, int(dead["salary_2028_num"]))

        self.db.assert_player_identity_integrity()

    def test_trade_preserves_contract_row_profile_identity(self) -> None:
        atl_profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        bos_profile_id = self._profile_id_for_player(self.legacy_bos_player_id)

        result = self.db.process_trade(
            "ATL",
            "BOS",
            [self.legacy_atl_player_id],
            [self.legacy_bos_player_id],
        )
        self.assertIsNotNone(result)

        with self.db.connect() as conn:
            atl_player = conn.execute(
                """
                SELECT p.profile_id, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (self.legacy_atl_player_id,),
            ).fetchone()
            bos_player = conn.execute(
                """
                SELECT p.profile_id, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (self.legacy_bos_player_id,),
            ).fetchone()
            self.assertEqual(atl_profile_id, int(atl_player["profile_id"]))
            self.assertEqual("BOS", atl_player["team_code"])
            self.assertEqual(bos_profile_id, int(bos_player["profile_id"]))
            self.assertEqual("ATL", bos_player["team_code"])
            trade_tx_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM player_transactions
                WHERE action = 'trade'
                  AND profile_id IN (?, ?)
                """,
                (atl_profile_id, bos_profile_id),
            ).fetchone()[0]
            self.assertEqual(2, trade_tx_count)

        self.db.assert_player_identity_integrity()


if __name__ == "__main__":
    unittest.main()
