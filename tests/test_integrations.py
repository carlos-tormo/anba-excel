import base64
import json
import unittest
from urllib.error import URLError
from unittest.mock import patch

from app.integrations.discord import DiscordConfig, DiscordIntegration, redact_secrets
from app.integrations.google_oauth import GoogleOAuthConfig, GoogleOAuthIntegration
from app.integrations.openai import OpenAIConfig, OpenAIIntegration


class FakeResponse:
    def __init__(self, body=b"", headers=None):
        self.body = body
        self.headers = headers or {}
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=None):
        self.read_limits.append(_limit)
        return self.body


class QueueOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, **kwargs):
        self.calls.append((request, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


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
        self.assertEqual({"parse": []}, payload["allowed_mentions"])
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

    def test_bot_get_fetches_gateway_metadata(self):
        opener = QueueOpener(FakeResponse(b'{"url":"wss://gateway.discord.gg"}'))
        integration = DiscordIntegration(
            DiscordConfig(bot_token="token", api_base_url="https://discord.example/api"),
            opener=opener,
        )

        result = integration.get_bot_json("/gateway/bot")

        self.assertEqual({"url": "wss://gateway.discord.gg"}, result)
        request, options = opener.calls[0]
        self.assertEqual("GET", request.get_method())
        self.assertEqual("https://discord.example/api/gateway/bot", request.full_url)
        self.assertEqual("Bot token", request.headers["Authorization"])

    def test_interaction_response_uses_callback_endpoint(self):
        opener = QueueOpener(FakeResponse(b'{}'))
        integration = DiscordIntegration(
            DiscordConfig(bot_token="token", api_base_url="https://discord.example/api"),
            opener=opener,
        )

        integration.respond_to_interaction("interaction 123", "interaction-token", {"type": 4})

        request, _options = opener.calls[0]
        self.assertEqual("https://discord.example/api/interactions/123/interaction-token/callback", request.full_url)
        self.assertEqual({"type": 4}, json.loads(request.data.decode("utf-8")))

    def test_bot_request_requires_token(self):
        integration = DiscordIntegration(DiscordConfig(), opener=QueueOpener())
        with self.assertRaisesRegex(RuntimeError, "DISCORD_BOT_TOKEN"):
            integration.post_bot_json("/channels/1/messages", {})

    def test_redaction_removes_tokens_and_webhook_urls(self):
        text = redact_secrets(
            "Bearer sk-secret Bot discord-token "
            "https://discord.com/api/webhooks/123/abc access_token=oauth-secret",
            extra_secrets=["oauth-secret"],
        )

        self.assertNotIn("sk-secret", text)
        self.assertNotIn("discord-token", text)
        self.assertNotIn("/123/abc", text)
        self.assertNotIn("oauth-secret", text)

    def test_webhook_request_records_external_duration(self):
        opener = QueueOpener(FakeResponse(b"{}"))
        integration = DiscordIntegration(
            DiscordConfig(webhook_url="https://discord.example/hooks/1"),
            opener=opener,
        )

        with patch("app.integrations.discord.time.perf_counter", side_effect=[10.0, 12.25]), patch(
            "app.integrations.discord.record_external_call"
        ) as record:
            integration.post_webhook_json({"content": "offer"})

        record.assert_called_once_with("discord", "webhook_json", 2.25, ok=True)


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

    def test_openai_post_records_external_duration(self):
        opener = QueueOpener(FakeResponse(b'{"output_text":"Owner response"}'))
        integration = OpenAIIntegration(OpenAIConfig(api_key="secret"), opener=opener)

        with patch("app.integrations.openai.time.perf_counter", side_effect=[20.0, 22.5]), patch(
            "app.integrations.openai.record_external_call"
        ) as record:
            self.assertEqual("Owner response", integration.text_response("system", "user"))

        record.assert_called_once_with("openai", "post_json", 2.5, ok=True)

    def test_text_response_bounds_prompt_and_output_text(self):
        opener = QueueOpener(FakeResponse(b'{"output_text":"abcdefghij"}'))
        integration = OpenAIIntegration(
            OpenAIConfig(
                api_key="secret",
                max_text_prompt_chars=10,
                max_text_output_chars=5,
            ),
            opener=opener,
        )

        result = integration.text_response("S" * 50, "U" * 50, max_output_tokens=450)

        self.assertEqual("ab...", result)
        payload = json.loads(opener.calls[0][0].data.decode("utf-8"))
        self.assertEqual("S" * 7 + "...", payload["input"][0]["content"][0]["text"])
        self.assertEqual("U" * 7 + "...", payload["input"][1]["content"][0]["text"])

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

    def test_generated_image_over_size_limit_is_ignored(self):
        encoded = base64.b64encode(b"too-large").decode("ascii")
        opener = QueueOpener(FakeResponse(json.dumps({"data": [{"b64_json": encoded}]}).encode("utf-8")))
        errors = []
        integration = OpenAIIntegration(
            OpenAIConfig(
                api_key="secret",
                image_generation_enabled=True,
                generated_image_max_bytes=3,
            ),
            opener=opener,
            log_error=lambda message, *args: errors.append(message % args if args else message),
        )

        self.assertIsNone(integration.generate_image("transaction graphic"))
        self.assertEqual(["OpenAI generated image ignored: file exceeds configured max size"], errors)

    def test_reference_image_get_retries_transient_failure(self):
        sleeps = []
        opener = QueueOpener(
            URLError("temporary failure"),
            FakeResponse(b"image-content", headers={"Content-Type": "image/png"}),
        )
        integration = OpenAIIntegration(
            OpenAIConfig(
                api_key="secret",
                reference_image_max_retries=1,
                reference_image_retry_base_seconds=0.1,
            ),
            opener=opener,
            sleeper=sleeps.append,
        )

        result = integration.fetch_reference_image("https://cdn.example/image.png")

        self.assertEqual((b"image-content", "reference.png", "image/png"), result)
        self.assertEqual(2, len(opener.calls))
        self.assertEqual([0.1], sleeps)


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
