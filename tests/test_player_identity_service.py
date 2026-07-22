import os
import sqlite3
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB, PLAYER_CONTRACT_SEASONS
from app.services.player_identity import PlayerIdentityService
from app.xlsx_import import create_schema, now_iso


class PlayerIdentityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, self.db_path = tempfile.mkstemp(
            prefix="anba-player-identity-service-", suffix=".db"
        )
        os.close(descriptor)
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO teams (
                    code, name, gm, cash_note, apron_hard_cap,
                    salary_cap, luxury_cap, first_apron, second_apron,
                    created_at, updated_at
                ) VALUES ('ATL', 'Atlanta Hawks', NULL, NULL, NULL,
                    154647000, 187896105, 195945000, 207824000, ?, ?)
                """,
                (timestamp, timestamp),
            )
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        self.service = PlayerIdentityService(
            self.db,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
        )

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def create_player(self, name: str = "Canonical Player") -> tuple[int, int]:
        player_id = self.db.create_player(
            "ATL",
            {
                "name": name,
                "position": "SG",
                "salary_2025_text": "1000000",
            },
        )
        self.assertIsNotNone(player_id)
        player = self.db.get_player_record(int(player_id))
        self.assertIsNotNone(player)
        return int(player_id), int(player["profile_id"])

    def test_profile_update_synchronizes_linked_player_name(self) -> None:
        player_id, profile_id = self.create_player()

        changed = self.service.update_profile(
            profile_id,
            {"name": "Canonical Player Updated"},
        )

        self.assertTrue(changed)
        player = self.db.get_player_record(player_id)
        self.assertEqual("Canonical Player Updated", player["name"])
        self.assertEqual("Canonical Player Updated", player["profile_name"])
        self.assertGreaterEqual(int(player["profile_version"]), 2)

    def test_profile_update_rejects_stale_version(self) -> None:
        player_id, profile_id = self.create_player()
        player = self.db.get_player_record(player_id)
        self.service.update_profile(profile_id, {"name": "First Update"})

        with self.assertRaisesRegex(ValueError, "stale_entity_version"):
            self.service.update_profile(
                profile_id,
                {
                    "name": "Stale Update",
                    "expected_version": player["profile_version"],
                },
            )

        updated = self.db.get_player_record(player_id)
        self.assertEqual("First Update", updated["name"])

    def test_synchronize_projects_uncontracted_profile_to_free_agents(self) -> None:
        player_id, profile_id = self.create_player("Uncontracted Player")
        with self.db.connect() as conn:
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            conn.commit()

        result = self.service.synchronize()

        self.assertGreaterEqual(result["uncontracted_profile_changes"], 1)
        free_agent = next(
            agent
            for agent in self.db.list_free_agents()
            if int(agent["profile_id"]) == profile_id
        )
        self.assertEqual("Uncontracted Player", free_agent["name"])
        self.assertEqual("uncontracted_profile", free_agent["source"])

    def test_integrity_report_is_exposed_through_service(self) -> None:
        self.create_player()

        report = self.service.integrity_report()

        self.assertTrue(report["ok"], report["errors"])


if __name__ == "__main__":
    unittest.main()
