import os
import tempfile
import unittest

from tests.db_helpers import connect_test_db

from app.server import LeagueDB
from app.services.waiting_list import (
    WAITING_LIST_DISCORD_ROLE_ID,
    WAITING_LIST_INTEREST_PROMPT,
    WaitingListService,
)
from app.services.waiting_list_discord import WaitingListDiscordService
from app.xlsx_import import create_schema


class FakeDiscord:
    def __init__(self) -> None:
        self.dms = []
        self.interactions = []

    def send_dm(self, user_id, payload):
        self.dms.append((user_id, payload))
        return True

    def respond_to_interaction(self, interaction_id, interaction_token, payload):
        self.interactions.append((interaction_id, interaction_token, payload))
        return {"ok": True}


class WaitingListTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-waiting-list-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with connect_test_db(self.db_path) as conn:
            create_schema(conn)
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()
        self.service = WaitingListService(self.db._waiting_list_repository)

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_create_list_update_delete_entries_and_normalizes_positions(self) -> None:
        first = self.service.create({"display_name": "Carlos", "registered_at": "2026-07-01"})
        second = self.service.create({"display_name": "Ana", "registered_at": "2026-07-02", "position": 1})

        listed = self.service.list()["entries"]
        self.assertEqual(["Ana", "Carlos"], [entry["display_name"] for entry in listed])
        self.assertEqual([1, 2], [entry["position"] for entry in listed])
        self.assertEqual(1, second["position"])
        self.assertEqual("2026-07-01", first["registered_at"])

        updated = self.service.update(first["id"], {"display_name": "Carlos T.", "position": 1})
        self.assertEqual("Carlos T.", updated["display_name"])
        self.assertEqual(2, updated["version"])
        self.assertEqual(["Carlos T.", "Ana"], [entry["display_name"] for entry in self.service.list()["entries"]])

        self.assertTrue(self.service.delete(updated["id"]))
        remaining = self.service.list()["entries"]
        self.assertEqual(["Ana"], [entry["display_name"] for entry in remaining])
        self.assertEqual([1], [entry["position"] for entry in remaining])

    def test_discord_interest_confirmation_upserts_by_discord_id(self) -> None:
        created = self.service.confirm_discord_interest(discord_id="123", display_name="Discord User")
        updated = self.service.confirm_discord_interest(discord_id="123", display_name="Updated Discord User")

        self.assertEqual(created["id"], updated["id"])
        self.assertEqual("Updated Discord User", updated["display_name"])
        self.assertEqual("discord", updated["source"])
        self.assertEqual("123", updated["discord_id"])
        self.assertEqual(1, len(self.service.list()["entries"]))

    def test_monthly_prompt_metadata_is_available_for_discord_worker(self) -> None:
        prompt = self.service.monthly_interest_prompt()

        self.assertEqual(WAITING_LIST_DISCORD_ROLE_ID, prompt["role_id"])
        self.assertIn("check verde", WAITING_LIST_INTEREST_PROMPT)
        self.assertEqual(WAITING_LIST_INTEREST_PROMPT, prompt["message"])

    def test_invite_token_can_be_accepted_and_consumed_after_google_login(self) -> None:
        invite = self.service.create_invite(discord_id="123", discord_username="Discord User", ttl_seconds=3600)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, google_sub, email, display_name, created_at, updated_at)
                VALUES (42, 'google-42', 'user@example.com', 'Google User', '2026-07-22T00:00:00+00:00', '2026-07-22T00:00:00+00:00')
                """
            )
            conn.commit()

        accepted = self.service.accept_invite_token(invite["token"])
        self.assertEqual("accepted", accepted["status"])

        entry = self.service.consume_invite_token(
            token=invite["token"],
            user_id=42,
            display_name="Google User",
        )
        self.assertEqual("Google User", entry["display_name"])
        self.assertEqual("123", entry["discord_id"])
        self.assertEqual(42, entry["user_id"])

        self.assertIsNone(
            self.service.consume_invite_token(
                token=invite["token"],
                user_id=42,
                display_name="Google User",
            )
        )

    def test_discord_service_sends_role_prompt_with_buttons(self) -> None:
        discord = FakeDiscord()
        service = WaitingListDiscordService(self.service, discord, public_base_url="https://league.test")

        result = service.handle_member_update(
            {
                "roles": ["1164127012403810315"],
                "user": {"id": "123", "username": "candidate"},
            }
        )

        self.assertTrue(result["prompt_sent"])
        self.assertEqual("123", discord.dms[0][0])
        payload = discord.dms[0][1]
        self.assertEqual(WAITING_LIST_INTEREST_PROMPT, payload["content"])
        buttons = payload["components"][0]["components"]
        self.assertEqual(["waiting_list:yes", "waiting_list:no"], [button["custom_id"] for button in buttons])

    def test_discord_service_accept_interaction_creates_invite_link(self) -> None:
        discord = FakeDiscord()
        service = WaitingListDiscordService(self.service, discord, public_base_url="https://league.test")

        result = service.handle_interaction(
            {
                "id": "interaction-1",
                "token": "interaction-token",
                "data": {"custom_id": "waiting_list:yes"},
                "user": {"id": "123", "global_name": "Candidate"},
            }
        )

        self.assertTrue(result["handled"])
        self.assertEqual("accepted", result["action"])
        self.assertIn("https://league.test/login?waiting_list_token=", result["invite_url"])
        response_payload = discord.interactions[0][2]
        self.assertEqual(4, response_payload["type"])
        self.assertEqual(64, response_payload["data"]["flags"])
        self.assertIn("Lista de espera", response_payload["data"]["content"])

    def test_discord_service_decline_interaction_records_decline(self) -> None:
        discord = FakeDiscord()
        service = WaitingListDiscordService(self.service, discord, public_base_url="https://league.test")

        result = service.handle_interaction(
            {
                "id": "interaction-2",
                "token": "interaction-token",
                "data": {"custom_id": "waiting_list:no"},
                "user": {"id": "123", "username": "candidate"},
            }
        )

        self.assertTrue(result["handled"])
        self.assertEqual("declined", result["action"])
        self.assertIn("No te añadiremos", discord.interactions[0][2]["data"]["content"])


if __name__ == "__main__":
    unittest.main()
