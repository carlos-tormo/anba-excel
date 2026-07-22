import unittest
from unittest.mock import Mock

from app.integrations.discord_gateway import DiscordGatewayClient, DiscordGatewayConfig


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent = []

    def send_json(self, payload):
        self.sent.append(payload)

    def close(self):
        return None


class DiscordGatewayClientTests(unittest.TestCase):
    def test_gateway_url_adds_required_query_parameters(self) -> None:
        self.assertEqual(
            "wss://gateway.discord.gg/?v=10&encoding=json",
            DiscordGatewayClient.gateway_url("wss://gateway.discord.gg/"),
        )

    def test_hello_identifies_and_dispatches_events(self) -> None:
        callback = Mock()
        client = DiscordGatewayClient(
            DiscordGatewayConfig(token="token"),
            on_dispatch=callback,
        )
        fake_ws = FakeWebSocket()
        client._ws = fake_ws

        client._handle_message({"op": 10, "d": {"heartbeat_interval": 60000}})
        client._handle_message({"op": 0, "s": 12, "t": "GUILD_MEMBER_UPDATE", "d": {"user": {"id": "1"}}})

        identify = fake_ws.sent[0]
        self.assertEqual(2, identify["op"])
        self.assertEqual("token", identify["d"]["token"])
        callback.assert_called_once_with("GUILD_MEMBER_UPDATE", {"user": {"id": "1"}})
        client.stop()


if __name__ == "__main__":
    unittest.main()
