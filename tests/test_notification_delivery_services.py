import unittest
from types import SimpleNamespace

from app.services.notification_delivery import (
    LeagueNotificationDeliveryService,
    PressPublicationConfig,
    PressPublicationService,
)


class FakeEventDelivery:
    def __init__(self):
        self.events = []

    def deliver_event(self, event, **options):
        self.events.append((event, options))
        return True


class FakeArticles:
    def __init__(self):
        self.updated = []

    def create(self, text, image_bytes, mime_type, session):
        self.created = (text, image_bytes, mime_type, session)
        return {"id": 17}

    def update_discord(self, article_id, channel_id, message_id):
        self.updated.append((article_id, channel_id, message_id))


class FakeDiscord:
    def post_bot_multipart(self, endpoint, payload, file_bytes, filename, mime_type):
        self.posted = (endpoint, payload, file_bytes, filename, mime_type)
        return {"id": "message-42"}


class NotificationDeliveryServiceTests(unittest.TestCase):
    def test_league_service_composes_signing_before_delivery(self):
        delivery = FakeEventDelivery()
        service = LeagueNotificationDeliveryService(
            delivery, SimpleNamespace(current_year=lambda: 2026)
        )

        self.assertTrue(
            service.free_agent_signed(
                {"team_code": "ATL", "name": "Test Player"},
                generate_image=False,
            )
        )

        event, options = delivery.events[0]
        self.assertEqual("ATL firma a Test Player", event.title)
        self.assertFalse(options["generate_image"])

    def test_press_service_persists_publishes_and_records_discord_ids(self):
        articles = FakeArticles()
        discord = FakeDiscord()
        image_delivery = SimpleNamespace(
            custom_image_attachment=lambda _payload: (
                b"image-bytes", "article.png", "image/png"
            )
        )
        service = PressPublicationService(
            articles,
            discord,
            image_delivery,
            PressPublicationConfig(True, "bot-token", "channel-9"),
        )

        result = service.publish(
            "Article body",
            lambda article_id: f"https://league.test/news?article={article_id}",
            {"base64": "unused-by-fake"},
            {"role": "admin"},
        )

        self.assertEqual("https://league.test/news?article=17", result["article_url"])
        self.assertEqual([(17, "channel-9", "message-42")], articles.updated)
        self.assertEqual("/channels/channel-9/messages", discord.posted[0])


if __name__ == "__main__":
    unittest.main()
