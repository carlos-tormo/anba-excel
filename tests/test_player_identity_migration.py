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
        with sqlite3.connect(self.db_path) as conn:
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

    def test_create_player_rejects_duplicate_active_profile(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)
        with self.assertRaises(ValueError):
            self.db.create_player("BOS", {"name": "Duplicate Contract", "profile_id": profile_id})
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

    def test_cut_then_sign_preserves_profile_identity(self) -> None:
        profile_id = self._profile_id_for_player(self.legacy_atl_player_id)

        cut_result = self.db.cut_player(self.legacy_atl_player_id)
        self.assertIsNotNone(cut_result)
        self.assertEqual(profile_id, int(cut_result["profile_id"]))

        with self.db.connect() as conn:
            self.assertIsNone(
                conn.execute("SELECT id FROM players WHERE profile_id = ?", (profile_id,)).fetchone()
            )
            dead = conn.execute(
                "SELECT id, profile_id FROM dead_contracts WHERE id = ?",
                (cut_result["dead_contract_id"],),
            ).fetchone()
            free = conn.execute(
                "SELECT id, profile_id FROM free_agents WHERE id = ?",
                (cut_result["free_agent_id"],),
            ).fetchone()
            self.assertEqual(profile_id, int(dead["profile_id"]))
            self.assertEqual(profile_id, int(free["profile_id"]))

        signed_player_id = self.db.sign_free_agent(
            int(cut_result["free_agent_id"]),
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
                conn.execute("SELECT id FROM free_agents WHERE id = ?", (cut_result["free_agent_id"],)).fetchone()
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
