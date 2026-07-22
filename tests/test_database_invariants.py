import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.xlsx_import import create_schema, now_iso


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> int:
    timestamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195946000, 207825000, ?, ?)
        """,
        (code, name, timestamp, timestamp),
    )
    return int(cur.lastrowid)


def insert_legacy_player(conn: sqlite3.Connection, team_id: int, name: str, row_order: int) -> int:
    timestamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO players (
            team_id, row_order, bird_rights, rating, name, position, years_left,
            salary_2025_text, salary_2025_num, salary_2026_text, salary_2026_num,
            notes, is_two_way, created_at, updated_at
        ) VALUES (?, ?, 'Reg', '70', ?, 'PG', 1, '1000000', 1000000, '1100000', 1100000, NULL, 0, ?, ?)
        """,
        (team_id, row_order, name, timestamp, timestamp),
    )
    return int(cur.lastrowid)


class DatabaseInvariantTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-db-invariants-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with connect_test_db(self.db_path) as conn:
            create_schema(conn)
            self.atl_id = insert_team(conn, "ATL", "Atlanta Hawks")
            self.bos_id = insert_team(conn, "BOS", "Boston Celtics")
            self.atl_player_id = insert_legacy_player(conn, self.atl_id, "Active Hawk", 1)
            self.bos_player_id = insert_legacy_player(conn, self.bos_id, "Active Celtic", 1)
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_one_active_contract_per_profile_is_database_enforced(self) -> None:
        with self.db.connect() as conn:
            atl_profile_id = conn.execute(
                "SELECT profile_id FROM players WHERE id = ?",
                (self.atl_player_id,),
            ).fetchone()["profile_id"]

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE players SET profile_id = ? WHERE id = ?",
                    (atl_profile_id, self.bos_player_id),
                )
            conn.rollback()

            conn.execute(
                "UPDATE players SET row_state = 'retained_rights', profile_id = ? WHERE id = ?",
                (atl_profile_id, self.bos_player_id),
            )
            conn.commit()

    def test_identity_profile_required_update_guards_cover_identity_rows(self) -> None:
        with self.db.connect() as conn:
            timestamp = now_iso()
            free_agent = conn.execute(
                """
                SELECT id
                FROM free_agents
                WHERE profile_id IS NOT NULL
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
            if free_agent is None:
                profile_id = conn.execute(
                    "SELECT profile_id FROM players WHERE id = ?",
                    (self.atl_player_id,),
                ).fetchone()["profile_id"]
                cur = conn.execute(
                    """
                    INSERT INTO free_agents (
                        profile_id, name, free_agent_type, created_at, updated_at
                    ) VALUES (?, 'Guarded FA', 'No restringido', ?, ?)
                    """,
                    (profile_id, timestamp, timestamp),
                )
                free_agent_id = int(cur.lastrowid)
            else:
                free_agent_id = int(free_agent["id"])

            profile_id = conn.execute(
                "SELECT profile_id FROM players WHERE id = ?",
                (self.atl_player_id,),
            ).fetchone()["profile_id"]
            dead_id = conn.execute(
                """
                INSERT INTO dead_contracts (
                    team_id, profile_id, row_order, dead_type, label,
                    amount_text, amount_num, created_at, updated_at
                ) VALUES (?, ?, 500, 'normal', 'Guarded Dead', '1000', 1000, ?, ?)
                """,
                (self.atl_id, profile_id, timestamp, timestamp),
            ).lastrowid
            conn.commit()

            for table, row_id in (
                ("players", self.atl_player_id),
                ("free_agents", free_agent_id),
                ("dead_contracts", int(dead_id)),
            ):
                with self.subTest(table=table):
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(f"UPDATE {table} SET profile_id = NULL WHERE id = ?", (row_id,))
                    conn.rollback()

    def test_multiple_current_holders_per_canonical_draft_pick_are_reported(self) -> None:
        with self.db.connect() as conn:
            timestamp = now_iso()
            pick_id = conn.execute(
                """
                INSERT INTO draft_picks (
                    draft_year, draft_round, original_team, created_at, updated_at
                ) VALUES (2027, '1st', 'DAL', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid
            atl_asset_id = conn.execute(
                """
                INSERT INTO assets (
                    team_id, row_order, asset_type, year, label, detail,
                    amount_text, amount_num, draft_pick_type, draft_round,
                    original_owner, created_at, updated_at
                ) VALUES (?, 500, 'draft_pick', 2027, '2027 DAL 1st', NULL,
                    NULL, NULL, 'acquired', '1st', 'DAL', ?, ?)
                """,
                (self.atl_id, timestamp, timestamp),
            ).lastrowid
            bos_asset_id = conn.execute(
                """
                INSERT INTO assets (
                    team_id, row_order, asset_type, year, label, detail,
                    amount_text, amount_num, draft_pick_type, draft_round,
                    original_owner, created_at, updated_at
                ) VALUES (?, 501, 'draft_pick', 2027, '2027 DAL 1st', NULL,
                    NULL, NULL, 'acquired', '1st', 'DAL', ?, ?)
                """,
                (self.bos_id, timestamp, timestamp),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO draft_pick_holdings (
                    draft_pick_id, holder_team, asset_id, holding_type, created_at, updated_at
                ) VALUES (?, 'ATL', ?, 'acquired', ?, ?)
                """,
                (pick_id, atl_asset_id, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO draft_pick_holdings (
                    draft_pick_id, holder_team, asset_id, holding_type, created_at, updated_at
                ) VALUES (?, 'BOS', ?, 'acquired', ?, ?)
                """,
                (pick_id, bos_asset_id, timestamp, timestamp),
            )
            conn.commit()

        report = self.db._player_identity_repository.integrity_report()
        checks = {error["check"] for error in report["errors"]}
        self.assertIn("draft_pick_multiple_current_holders", checks)

    def test_one_live_selection_per_draft_slot_is_database_enforced(self) -> None:
        with self.db.connect() as conn:
            timestamp = now_iso()
            draft_order_id = conn.execute(
                """
                INSERT INTO draft_order (
                    draft_year, draft_round, pick_number, owner_team_code,
                    original_team_code, created_at, updated_at
                ) VALUES (2027, '1st', 1, 'ATL', 'ATL', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO draft_live_selections (
                    draft_order_id, selection_text, updated_at
                ) VALUES (?, 'First Selection', ?)
                """,
                (draft_order_id, timestamp),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO draft_live_selections (
                        draft_order_id, selection_text, updated_at
                    ) VALUES (?, 'Duplicate Selection', ?)
                    """,
                    (draft_order_id, timestamp),
                )
            conn.rollback()

    def test_duplicate_waiver_claim_by_team_and_waiver_is_database_enforced(self) -> None:
        with self.db.connect() as conn:
            timestamp = now_iso()
            waiver_id = conn.execute(
                """
                INSERT INTO waiver_players (
                    from_team_id, from_team_code, player_name, contract_json,
                    waiver_expires_at, created_at, updated_at
                ) VALUES (?, 'ATL', 'Waived Player', '{}', ?, ?, ?)
                """,
                (self.atl_id, timestamp, timestamp, timestamp),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO waiver_claims (
                    waiver_player_id, team_id, team_code, created_at, updated_at
                ) VALUES (?, ?, 'BOS', ?, ?)
                """,
                (waiver_id, self.bos_id, timestamp, timestamp),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO waiver_claims (
                        waiver_player_id, team_id, team_code, created_at, updated_at
                    ) VALUES (?, ?, 'BOS', ?, ?)
                    """,
                    (waiver_id, self.bos_id, timestamp, timestamp),
                )
            conn.rollback()

    def test_command_and_outbox_deduplication_are_database_enforced(self) -> None:
        with self.db.connect() as conn:
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO outbox_events (
                    event_type, idempotency_key, payload_json, created_at, updated_at
                ) VALUES ('discord.test', 'command-1', '{}', ?, ?)
                """,
                (timestamp, timestamp),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO outbox_events (
                        event_type, idempotency_key, payload_json, created_at, updated_at
                    ) VALUES ('discord.test', 'command-1', '{}', ?, ?)
                    """,
                    (timestamp, timestamp),
                )
            conn.rollback()

            conn.execute(
                """
                INSERT INTO workflow_transition_log (
                    workflow_type, resource_id, previous_state, new_state,
                    command_id, created_at
                ) VALUES ('trade', 'trade:1', 'pending', 'completed', 'trade-command-1', ?)
                """,
                (timestamp,),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO workflow_transition_log (
                        workflow_type, resource_id, previous_state, new_state,
                        command_id, created_at
                    ) VALUES ('trade', 'trade:1', 'pending', 'completed', 'trade-command-1', ?)
                    """,
                    (timestamp,),
                )
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
