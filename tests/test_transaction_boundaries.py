import ast
import inspect
import unittest

from app.db.repositories.waivers import WaiverRepository
from app.routes import patch_remaining, post_remaining
from app.services.gm_requests import GMRequestService
from app.services.trades import TradeService
from app.services.waivers import WaiverService


class TransactionBoundaryArchitectureTests(unittest.TestCase):
    def test_free_agent_offer_decision_mutation_and_outbox_share_one_transaction(self) -> None:
        source = inspect.getsource(GMRequestService.decide_free_agent_offer)
        transaction_index = source.index('with self.requests.db.transaction("IMMEDIATE") as conn:')
        sign_index = source.index("self.free_agency._sign_free_agent_conn(conn")
        outbox_index = source.index("self.outbox.enqueue_conn(\n                        conn")

        self.assertLess(transaction_index, sign_index)
        self.assertLess(sign_index, outbox_index)
        self.assertIn('"gm_free_agent_offer_request"', source)

    def test_trade_mutation_and_outbox_share_processing_transaction(self) -> None:
        source = inspect.getsource(TradeService.process_command)
        processing_transaction_index = source.index('with self.repository.transaction("IMMEDIATE") as conn:', source.index("try:"))
        process_index = source.index("self.repository.process_", processing_transaction_index)
        outbox_index = source.index("self.outbox.enqueue_conn(\n                        conn", process_index)
        completed_index = source.index('"completed"', outbox_index)

        self.assertLess(processing_transaction_index, process_index)
        self.assertLess(process_index, outbox_index)
        self.assertLess(outbox_index, completed_index)

    def test_waiver_service_owns_claim_submit_and_decision_transactions(self) -> None:
        service_source = inspect.getsource(WaiverService)
        repository_source = inspect.getsource(WaiverRepository)

        self.assertIn('with self.repository.db.transaction("IMMEDIATE") as conn:', service_source)
        self.assertIn("create_claim_conn(", service_source)
        self.assertIn("decide_claim_request_conn(", service_source)
        self.assertIn("def create_claim_conn(", repository_source)
        self.assertIn("def decide_claim_request_conn(", repository_source)

    def test_discord_outbox_delivery_is_route_level_after_service_commit(self) -> None:
        for route_func, service_call in (
            (patch_remaining.decide_free_agent_offer_request, "service.decide_offer("),
            (post_remaining.process_trade, "service.process_request("),
        ):
            with self.subTest(route=route_func.__name__):
                source = inspect.getsource(route_func)
                service_index = source.index(service_call)
                dispatch_index = source.index("outbox_delivery.dispatch", service_index)
                self.assertLess(service_index, dispatch_index)

    def test_critical_services_do_not_call_discord_delivery_directly(self) -> None:
        for cls in (GMRequestService, TradeService, WaiverService):
            with self.subTest(service=cls.__name__):
                tree = ast.parse(inspect.getsource(cls))
                forbidden = [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Attribute)
                    and node.attr in {"dispatch", "deliver", "deliver_event"}
                ]
                self.assertEqual([], forbidden)


if __name__ == "__main__":
    unittest.main()
