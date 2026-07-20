import unittest

from app.services.free_agent_offer_notifications import (
    FreeAgentOfferDiscordConfig,
    FreeAgentOfferNotificationService,
)


class FakeDiscord:
    def __init__(self):
        self.webhooks = []
        self.dms = []

    def post_webhook_json(self, payload, **kwargs):
        self.webhooks.append((payload, kwargs))
        return {"channel_id": "987654321"} if kwargs.get("thread_name") else None

    def send_dm(self, user_id, payload):
        self.dms.append((user_id, payload))
        return True


class FakeFreeAgents:
    def __init__(self, thread=None):
        self.thread = thread
        self.upserts = []

    def get_offer_thread(self, _free_agent):
        return self.thread

    def upsert_offer_thread(self, free_agent, thread_id, thread_name):
        self.upserts.append((free_agent, thread_id, thread_name))


class FakeSettings:
    def __init__(self, values=None):
        self.values = values or {}

    def get_all(self):
        return self.values


class FakeOfferPolicy:
    @staticmethod
    def is_renewal(_free_agent, _team_code):
        return False


def make_service(discord, free_agents, settings):
    return FreeAgentOfferNotificationService(
        discord,
        free_agents,
        settings,
        FakeOfferPolicy(),
        FreeAgentOfferDiscordConfig(
            enabled=True,
            webhook_url="https://discord.example/offers",
            forum_tag_ids=("tag-1",),
            offer_role_id="role:12345",
            bot_token="token",
        ),
    )


class FreeAgentOfferNotificationServiceTests(unittest.TestCase):
    def test_deliver_creates_thread_persists_it_and_dms_configured_agent(self):
        discord = FakeDiscord()
        free_agents = FakeFreeAgents()
        settings = FakeSettings(
            {
                "free_agent_rep_discord_ids": '{"Agent Smith": "123456789"}',
                "discord_free_agent_offer_role_ping_enabled": "1",
            }
        )
        service = make_service(discord, free_agents, settings)

        result = service.deliver(
            {"name": "Test Player", "agent": "agent smith", "profile_id": 7},
            "ATL",
            {
                "contract_type": "Reg",
                "years": 2,
                "salary_by_season": {"2026": "10.000.000"},
                "notes": "Private details",
            },
            "free_agent_offer",
        )

        self.assertEqual(
            {
                "thread_sent": True,
                "agent_dm_sent": True,
                "agent_discord_configured": True,
            },
            result,
        )
        public_payload, create_options = discord.webhooks[0]
        self.assertEqual("Test Player", create_options["thread_name"])
        self.assertEqual(["tag-1"], public_payload["applied_tags"])
        self.assertEqual("<@&12345>", public_payload["content"])
        self.assertEqual("987654321", free_agents.upserts[0][1])
        self.assertEqual("123456789", discord.dms[0][0])
        self.assertIn("Private details", str(discord.dms[0][1]))
        self.assertNotIn("Private details", str(public_payload))

    def test_existing_thread_is_reused_without_tags_or_role_mention(self):
        discord = FakeDiscord()
        free_agents = FakeFreeAgents({"thread_id": "456789"})
        service = make_service(discord, free_agents, FakeSettings())

        result = service.notify(
            {"name": "Test Player"},
            "ATL",
            {"years": 1, "salary_by_season": {}},
        )

        payload, options = discord.webhooks[0]
        self.assertTrue(result["thread_sent"])
        self.assertEqual("456789", options["thread_id"])
        self.assertNotIn("applied_tags", payload)
        self.assertNotIn("content", payload)
        self.assertEqual([], free_agents.upserts)

if __name__ == "__main__":
    unittest.main()
