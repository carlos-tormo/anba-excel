import base64
import unittest
from urllib.error import URLError

from app.services.discord_notifications import (
    DiscordNotificationDeliveryConfig,
    DiscordNotificationDeliveryService,
)
from app.services.notifications import EventNotification


class FakeDiscord:
    def __init__(self, *, multipart_error=None, json_error=None):
        self.multipart_error = multipart_error
        self.json_error = json_error
        self.multipart = []
        self.json = []

    def post_webhook_multipart(self, payload, file_bytes, filename, mime_type):
        self.multipart.append((payload, file_bytes, filename, mime_type))
        if self.multipart_error:
            raise self.multipart_error

    def post_webhook_json(self, payload):
        self.json.append(payload)
        if self.json_error:
            raise self.json_error


class FakeOpenAI:
    def __init__(self, attachment=None):
        self.attachment = attachment
        self.calls = []

    def generate_image(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return self.attachment


def service(discord, openai, *, enabled=True, errors=None):
    return DiscordNotificationDeliveryService(
        discord,
        openai,
        DiscordNotificationDeliveryConfig(
            enabled=enabled,
            webhook_url="https://discord.example/webhook",
            role_id="1234",
        ),
        image_prompt_builder=lambda **prompt: f"prompt:{prompt['headline']}",
        detect_image_type=lambda _data, _mime, _allowed: ("png", "image/png"),
        log_error=lambda *args: errors.append(args) if errors is not None else None,
    )


class DiscordNotificationDeliveryServiceTests(unittest.TestCase):
    def test_disabled_delivery_does_not_call_transports(self):
        discord = FakeDiscord()
        openai = FakeOpenAI()
        result = service(discord, openai, enabled=False).notify("Title", "Description")
        self.assertFalse(result)
        self.assertEqual([], discord.json)
        self.assertEqual([], openai.calls)

    def test_generated_image_uses_multipart_delivery(self):
        discord = FakeDiscord()
        openai = FakeOpenAI((b"image", "news.png", "image/png"))
        result = service(discord, openai).notify(
            "Title", "Description", image_prompt="image prompt", generate_image=True
        )
        self.assertTrue(result)
        self.assertEqual(1, len(discord.multipart))
        self.assertEqual([], discord.json)
        self.assertEqual("attachment://news.png", discord.multipart[0][0]["embeds"][0]["image"]["url"])

    def test_multipart_failure_retries_without_image(self):
        errors = []
        discord = FakeDiscord(multipart_error=URLError("upload failed"))
        openai = FakeOpenAI((b"image", "news.png", "image/png"))
        result = service(discord, openai, errors=errors).notify("Title", "Description")
        self.assertTrue(result)
        self.assertEqual(1, len(discord.json))
        self.assertNotIn("image", discord.json[0]["embeds"][0])
        self.assertTrue(errors)

    def test_custom_image_takes_precedence_over_generation(self):
        discord = FakeDiscord()
        openai = FakeOpenAI((b"generated", "generated.png", "image/png"))
        custom_bytes = b"custom-image"
        result = service(discord, openai).notify(
            "Title",
            "Description",
            custom_image={
                "mime_type": "image/png",
                "base64": base64.b64encode(custom_bytes).decode("ascii"),
                "filename": "custom.png",
            },
        )
        self.assertTrue(result)
        self.assertEqual([], openai.calls)
        self.assertEqual(custom_bytes, discord.multipart[0][1])

    def test_event_delivery_builds_primary_and_fallback_prompts(self):
        discord = FakeDiscord()
        openai = FakeOpenAI()
        event = EventNotification(
            "Title",
            "Description",
            [],
            1,
            {"headline": "Primary", "description": "Description"},
            "https://example.com/player.png",
            {"headline": "Fallback", "description": "Description"},
        )
        service(discord, openai).deliver_event(event, generate_image=True, custom_image=None)
        self.assertEqual("prompt:Primary", openai.calls[0][0])
        self.assertEqual("prompt:Fallback", openai.calls[0][1]["fallback_prompt"])

if __name__ == "__main__":
    unittest.main()
