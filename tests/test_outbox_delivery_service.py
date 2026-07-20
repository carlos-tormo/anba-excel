import unittest

from app.server import Handler
from app.services.outbox_delivery import OutboxDeliveryService


class FakeOutbox:
    def __init__(self, events):
        self.events = events
        self.succeeded = []
        self.failed = []

    def get(self, event_id):
        return self.events.get(event_id)

    def mark_succeeded(self, event_id):
        self.succeeded.append(event_id)
        return True

    def mark_failed(self, event_id, error):
        self.failed.append((event_id, error))
        return True


class FakePlayers:
    def __init__(self, players):
        self.players = players

    def record(self, player_id):
        return self.players.get(player_id)


class OutboxDeliveryServiceTests(unittest.TestCase):
    def test_dispatches_free_agent_notification_and_marks_success(self):
        outbox = FakeOutbox({
            1: {
                "event_type": "discord.free_agent_signed",
                "payload": {
                    "player_id": 7,
                    "offer_type": "renewal",
                    "offer_payload": {"salary_by_season": {"2026": "21.000.000"}},
                    "generate_image": True,
                },
            }
        })
        delivered = []
        service = OutboxDeliveryService(
            outbox,
            FakePlayers({7: {"name": "Player", "team_code": "ATL"}}),
            deliver_notification=lambda event, **options: delivered.append((event, options)) or True,
        )

        self.assertEqual([1], service.dispatch([1]))
        self.assertEqual([1], outbox.succeeded)
        self.assertEqual([], outbox.failed)
        self.assertEqual("ATL renueva a Player", delivered[0][0].title)
        self.assertTrue(delivered[0][1]["generate_image"])

    def test_records_missing_player_and_unknown_event_failures(self):
        outbox = FakeOutbox({
            2: {"event_type": "discord.free_agent_signed", "payload": {"player_id": 99}},
            3: {"event_type": "discord.unknown", "payload": {}},
        })
        service = OutboxDeliveryService(
            outbox,
            FakePlayers({}),
            deliver_notification=lambda *_args, **_kwargs: True,
        )

        self.assertEqual([], service.dispatch([2, 3]))
        self.assertEqual([(2, "player_not_found"), (3, "unknown_event_type:discord.unknown")], outbox.failed)

    def test_trade_delivery_exception_is_recorded(self):
        outbox = FakeOutbox({
            4: {"event_type": "discord.trade_processed", "payload": {"result": {"teams": []}}},
        })
        service = OutboxDeliveryService(
            outbox,
            FakePlayers({}),
            deliver_notification=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("discord down")),
        )

        with self.assertLogs("app.services.outbox_delivery", level="ERROR"):
            self.assertEqual([], service.dispatch([4]))
        self.assertEqual([(4, "discord down")], outbox.failed)

    def test_handler_no_longer_exposes_outbox_dispatch_compatibility(self):
        self.assertNotIn("_dispatch_outbox_events", vars(Handler))
        self.assertNotIn("_outbox_delivery_service", vars(Handler))


if __name__ == "__main__":
    unittest.main()
