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


class ClaimingOutbox(FakeOutbox):
    def __init__(self, events, *, claim_result=True, available_ids=None):
        super().__init__(events)
        self.claim_result = claim_result
        self.available_ids = list(available_ids or [])
        self.claim_calls = []
        self.claim_available_calls = []
        self.dead_letters = []
        self.get_calls = []

    def claim(self, event_id, **kwargs):
        self.claim_calls.append((event_id, kwargs))
        return self.claim_result

    def claim_available(self, **kwargs):
        self.claim_available_calls.append(kwargs)
        return list(self.available_ids)

    def get(self, event_id):
        self.get_calls.append(event_id)
        return super().get(event_id)

    def mark_failed(self, event_id, error, **kwargs):
        self.failed.append((event_id, error, kwargs.get("error_code")))
        return True

    def mark_dead_letter(self, event_id, error, **kwargs):
        self.dead_letters.append((event_id, error, kwargs.get("error_code")))
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

    def test_delivery_exception_is_redacted_before_logging_and_persistence(self):
        outbox = FakeOutbox({
            5: {"event_type": "discord.trade_processed", "payload": {"result": {"teams": []}}},
        })
        service = OutboxDeliveryService(
            outbox,
            FakePlayers({}),
            deliver_notification=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("failed with Bot abc.def.ghi")
            ),
        )

        with self.assertLogs("app.services.outbox_delivery", level="ERROR") as logs:
            self.assertEqual([], service.dispatch([5]))
        self.assertNotIn("abc.def.ghi", "\n".join(logs.output))
        self.assertEqual([(5, "failed with Bot [REDACTED]")], outbox.failed)

    def test_dispatch_skips_event_when_worker_cannot_claim_it(self):
        outbox = ClaimingOutbox({
            6: {"event_type": "discord.trade_processed", "payload": {"result": {"teams": []}}},
        }, claim_result=False)
        service = OutboxDeliveryService(
            outbox,
            FakePlayers({}),
            deliver_notification=lambda *_args, **_kwargs: self.fail("should not deliver locked events"),
            worker_id="worker-a",
        )

        self.assertEqual([], service.dispatch([6]))
        self.assertEqual([6], [call[0] for call in outbox.claim_calls])
        self.assertEqual([], outbox.get_calls)
        self.assertEqual([], outbox.succeeded)
        self.assertEqual([], outbox.failed)

    def test_dispatch_available_delivers_only_repository_claimed_events(self):
        outbox = ClaimingOutbox({
            7: {"event_type": "discord.trade_processed", "payload": {"result": {"teams": []}}},
        }, available_ids=[7])
        delivered = []
        service = OutboxDeliveryService(
            outbox,
            FakePlayers({}),
            deliver_notification=lambda event, **_kwargs: delivered.append(event) or True,
            worker_id="worker-b",
            lease_seconds=45,
        )

        self.assertEqual([7], service.dispatch_available(limit=10))
        self.assertEqual([7], outbox.succeeded)
        self.assertEqual([], outbox.claim_calls)
        self.assertEqual(1, len(outbox.claim_available_calls))
        self.assertEqual("worker-b", outbox.claim_available_calls[0]["worker_id"])
        self.assertEqual(45, outbox.claim_available_calls[0]["lease_seconds"])
        self.assertEqual(1, len(delivered))

    def test_poisonous_event_is_dead_lettered_with_error_code_when_supported(self):
        outbox = ClaimingOutbox({
            8: {"event_type": "discord.free_agent_signed", "payload": {"player_id": 404}},
        })
        service = OutboxDeliveryService(
            outbox,
            FakePlayers({}),
            deliver_notification=lambda *_args, **_kwargs: self.fail("should not deliver invalid events"),
        )

        self.assertEqual([], service.dispatch([8]))
        self.assertEqual([(8, "player_not_found", "referenced_entity_missing")], outbox.dead_letters)
        self.assertEqual([], outbox.failed)

    def test_handler_no_longer_exposes_outbox_dispatch_compatibility(self):
        self.assertNotIn("_dispatch_outbox_events", vars(Handler))
        self.assertNotIn("_outbox_delivery_service", vars(Handler))


if __name__ == "__main__":
    unittest.main()
