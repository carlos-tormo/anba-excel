import base64
import json
import unittest

from app.integrations.discord import DiscordConfig, DiscordIntegration
from app.integrations.google_oauth import GoogleOAuthConfig, GoogleOAuthIntegration
from app.integrations.openai import OpenAIConfig, OpenAIIntegration


class FakeResponse:
    def __init__(self, body=b"", headers=None):
        self.body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=None):
        return self.body


class QueueOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, **kwargs):
        self.calls.append((request, kwargs))
        return self.responses.pop(0)


class DiscordIntegrationTests(unittest.TestCase):
    def test_webhook_thread_request_returns_wait_response(self):
        opener = QueueOpener(FakeResponse(b'{"id":"message-1"}'))
        integration = DiscordIntegration(
            DiscordConfig(webhook_url="https://discord.example/hooks/1", timeout_seconds=7),
            opener=opener,
        )

        result = integration.post_webhook_json(
            {"content": "offer"},
            thread_name="A" * 120,
            wait=True,
        )

        self.assertEqual({"id": "message-1"}, result)
        request, options = opener.calls[0]
        self.assertEqual("https://discord.example/hooks/1?wait=true", request.full_url)
        self.assertEqual(7, options["timeout"])
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual("offer", payload["content"])
        self.assertEqual(100, len(payload["thread_name"]))
        self.assertTrue(payload["thread_name"].endswith("..."))

    def test_send_dm_creates_channel_then_posts_message(self):
        opener = QueueOpener(FakeResponse(b'{"id":"channel-9"}'), FakeResponse())
        integration = DiscordIntegration(
            DiscordConfig(bot_token="token", api_base_url="https://discord.example/api"),
            opener=opener,
        )

        self.assertTrue(integration.send_dm("user: 123", {"content": "hello"}))

        first_request = opener.calls[0][0]
        second_request = opener.calls[1][0]
        self.assertEqual("https://discord.example/api/users/@me/channels", first_request.full_url)
        self.assertEqual({"recipient_id": "123"}, json.loads(first_request.data.decode("utf-8")))
        self.assertEqual("https://discord.example/api/channels/channel-9/messages", second_request.full_url)
        self.assertEqual("Bot token", second_request.headers["Authorization"])

    def test_bot_request_requires_token(self):
        integration = DiscordIntegration(DiscordConfig(), opener=QueueOpener())
        with self.assertRaisesRegex(RuntimeError, "DISCORD_BOT_TOKEN"):
            integration.post_bot_json("/channels/1/messages", {})


class OpenAIIntegrationTests(unittest.TestCase):
    def test_text_response_uses_responses_api_and_direct_output(self):
        opener = QueueOpener(FakeResponse(b'{"output_text":"Owner response"}'))
        integration = OpenAIIntegration(
            OpenAIConfig(api_key="secret", text_model="text-model", text_timeout_seconds=33),
            opener=opener,
        )

        result = integration.text_response("system", "user", max_output_tokens=450)

        self.assertEqual("Owner response", result)
        request, options = opener.calls[0]
        self.assertEqual("https://api.openai.com/v1/responses", request.full_url)
        self.assertEqual(33, options["timeout"])
        self.assertEqual("Bearer secret", request.headers["Authorization"])
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual("text-model", payload["model"])
        self.assertEqual(450, payload["max_output_tokens"])

    def test_prompt_image_decodes_base64_attachment(self):
        encoded = base64.b64encode(b"image-content").decode("ascii")
        opener = QueueOpener(FakeResponse(json.dumps({"data": [{"b64_json": encoded}]}).encode("utf-8")))
        integration = OpenAIIntegration(
            OpenAIConfig(
                api_key="secret",
                image_model="image-model",
                image_format="webp",
                image_generation_enabled=True,
            ),
            opener=opener,
        )

        result = integration.generate_image("transaction graphic")

        self.assertEqual((b"image-content", "anba-news.webp", "image/webp"), result)
        payload = json.loads(opener.calls[0][0].data.decode("utf-8"))
        self.assertEqual("image-model", payload["model"])
        self.assertEqual("webp", payload["output_format"])

    def test_disabled_image_generation_does_not_call_network(self):
        opener = QueueOpener()
        integration = OpenAIIntegration(OpenAIConfig(api_key="secret"), opener=opener)

        self.assertIsNone(integration.generate_image("transaction graphic"))
        self.assertEqual([], opener.calls)


class GoogleOAuthIntegrationTests(unittest.TestCase):
    def test_authorization_url_contains_expected_openid_parameters(self):
        integration = GoogleOAuthIntegration(
            GoogleOAuthConfig(client_id="client-1", client_secret="secret", redirect_uri="https://app.example/callback")
        )

        url = integration.authorization_url("state token")

        self.assertIn("https://accounts.google.com/o/oauth2/v2/auth?", url)
        self.assertIn("client_id=client-1", url)
        self.assertIn("redirect_uri=https%3A%2F%2Fapp.example%2Fcallback", url)
        self.assertIn("scope=openid+email+profile", url)
        self.assertIn("state=state+token", url)

    def test_exchange_code_posts_form_and_fetches_userinfo_with_bearer_token(self):
        opener = QueueOpener(
            FakeResponse(b'{"access_token":"access-1"}'),
            FakeResponse(b'{"sub":"google-1","email":"gm@example.com"}'),
        )
        integration = GoogleOAuthIntegration(
            GoogleOAuthConfig(
                client_id="client-1",
                client_secret="secret-1",
                redirect_uri="https://app.example/callback",
                timeout_seconds=22,
            ),
            opener=opener,
        )

        token = integration.exchange_code("auth-code")
        profile = integration.fetch_userinfo(token["access_token"])

        token_request, token_options = opener.calls[0]
        self.assertEqual("https://oauth2.googleapis.com/token", token_request.full_url)
        self.assertEqual("POST", token_request.get_method())
        self.assertIn(b"code=auth-code", token_request.data)
        self.assertIn(b"client_secret=secret-1", token_request.data)
        self.assertEqual(22, token_options["timeout"])
        userinfo_request, userinfo_options = opener.calls[1]
        self.assertEqual("https://www.googleapis.com/oauth2/v3/userinfo", userinfo_request.full_url)
        self.assertEqual("Bearer access-1", userinfo_request.headers["Authorization"])
        self.assertEqual(22, userinfo_options["timeout"])
        self.assertEqual("google-1", profile["sub"])


if __name__ == "__main__":
    unittest.main()
