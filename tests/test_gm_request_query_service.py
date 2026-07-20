import unittest

from app.services.gm_request_queries import GMRequestQueryService


class FakeRequests:
    def list_requests(self, _status):
        return [
            {"id": 1, "status": "approved", "created_at": "2026-01-03"},
            {"id": 2, "status": "pending", "created_at": "2026-01-01"},
        ]

    def get_gm_free_agent_offer_request(self, request_id):
        return {"id": request_id, "request_type": "free_agent_offer"}

    def create_gm_option_request(self, *args):
        return {"id": 9, "args": args}


class FakeDraft:
    def list_pick_requests(self, _status):
        return [{"id": 3, "status": "pending", "created_at": "2026-01-02"}]


class FakeWaivers:
    def list_claim_requests(self, *, status):
        return [{"id": 4, "status": status, "created_at": "2026-01-04"}]


class GMRequestQueryServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = GMRequestQueryService(FakeRequests(), FakeDraft(), FakeWaivers())

    def test_combines_request_sources_with_pending_items_first(self):
        rows = self.service.list("pending")
        self.assertEqual([4, 3, 2, 1], [row["id"] for row in rows])

    def test_exposes_offer_lookup_and_option_submission(self):
        self.assertEqual(7, self.service.free_agent_offer(7)["id"])
        request = self.service.create_option(5, "option_2027", "PO", "accepted", {"id": 2})
        self.assertEqual(9, request["id"])
        self.assertEqual(5, request["args"][0])


if __name__ == "__main__":
    unittest.main()
