import inspect
import unittest

from app.db.repositories.cartera import CarteraRepository
from app.db.repositories.free_agency import FreeAgencyRepository
from app.db.repositories.gm_workflows import CoadminVoteRepository, GMRequestOperations, GMRequestRepository
from app.db.repositories.offseason_exceptions import OffseasonExceptionRepository
from app.db.repositories.offer_promises import OfferPromiseRepository
from app.db.repositories.player_identity import PlayerIdentityRepository
from app.services.gm_requests import GMRequestService


class FreeAgencyRepositoryBoundaryTests(unittest.TestCase):
    def test_repositories_do_not_delegate_to_league_db_workflow_facades(self) -> None:
        forbidden = (
            "self.db.get_free_agent(",
            "self.db.record_free_agent_interest(",
            "self.db.set_free_agent_favorite(",
            "self.db.sign_free_agent(",
            "self.db.create_gm_",
            "self.db.mark_gm_",
            "self.db.cancel_gm_",
            "self.db.create_free_agent_offer_promise(",
            "self.db.list_free_agent_offer_promises(",
            "self.db.update_free_agent_offer_promise(",
            "self.db.list_cartera_clients_for_session(",
            "self.db.generate_offseason_exceptions(",
            "self.db.create_coadmin_vote(",
            "self.db.submit_coadmin_vote(",
            "self.db._sync_cap_hold_free_agents(",
            "self.db._sync_uncontracted_profile_free_agents(",
            "self.db._sign_free_agent_conn(",
            "self.db.update_player_profile(",
            "self.db.delete_player_profile(",
            "self.db.merge_player_profiles(",
            "self.db.player_identity_integrity_report(",
        )
        source = "\n".join(inspect.getsource(repository) for repository in (
            FreeAgencyRepository,
            GMRequestRepository,
            OfferPromiseRepository,
            CoadminVoteRepository,
            CarteraRepository,
            OffseasonExceptionRepository,
            PlayerIdentityRepository,
        ))
        for call in forbidden:
            self.assertNotIn(call, source)

    def test_low_level_free_agency_mutations_are_repository_owned(self) -> None:
        free_agency_source = inspect.getsource(FreeAgencyRepository)
        identity_source = inspect.getsource(PlayerIdentityRepository)
        self.assertIn("def _sign_free_agent_conn(", free_agency_source)
        self.assertIn("def _record_player_transaction(", free_agency_source)
        self.assertIn("def _retained_rights_only(", free_agency_source)
        self.assertIn("def sync_cap_hold_free_agents(", identity_source)
        self.assertIn("def sync_uncontracted_profile_free_agents(", identity_source)
        for callback_name in (
            "create_player_conn:",
            "find_profile_id:",
            "retained_rights_only:",
            "record_player_transaction:",
        ):
            self.assertNotIn(callback_name, free_agency_source)

    def test_gm_request_repository_does_not_orchestrate_offer_decision_side_effects(self) -> None:
        repository_source = inspect.getsource(GMRequestRepository)
        operations_source = inspect.getsource(GMRequestOperations)
        for dependency in (
            "upsert_offer_promise_conn",
            "create_notification_conn",
            "get_free_agent_conn",
            "sign_free_agent_conn",
            "enqueue_outbox_event_conn",
            "get_player_record",
            "transition_workflow_conn",
        ):
            self.assertNotIn(dependency, operations_source)
        self.assertNotIn("def decide_gm_free_agent_offer_request_command(", repository_source)
        service_source = inspect.getsource(GMRequestService)
        self.assertIn("def decide_free_agent_offer(", service_source)
        self.assertIn("with self.requests.db.transaction(\"IMMEDIATE\")", service_source)


if __name__ == "__main__":
    unittest.main()
