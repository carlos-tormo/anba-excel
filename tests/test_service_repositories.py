import unittest
import inspect

from app.db.repositories.draft import DraftRepository
from app.db.repositories.admin_exports import AdminExportRepository
from app.db.repositories.admin_imports import OwnerAdminImportRepository
from app.db.repositories.free_agency import FreeAgencyRepository
from app.db.repositories.free_agent_appeal import FreeAgentAppealRepository
from app.db.repositories.free_agent_agents import FreeAgentAgentRepository
from app.db.repositories.gm_minimum_targets import GMMinimumTargetRepository
from app.db.repositories.gm_office import GMOfficeRepository
from app.db.repositories.owner_office import OwnerOfficeRepository
from app.db.repositories.offer_promises import OfferPromiseRepository
from app.db.repositories.player_identity import PlayerIdentityRepository
from app.db.repositories.player_catalog import PlayerCatalogRepository
from app.db.repositories.season_rollover import SeasonRolloverRepository
from app.db.repositories.trades import TradeRepository
from app.db.repositories.tracker import TrackerRepository
from app.db.repositories.team_detail import TeamDetailRepository
from app.db.repositories.waivers import WaiverRepository
from app.domain.cap import calculate_team_cap_summary
from app.services.draft import DraftService
from app.services.admin_exports import LeagueWorkbookExportService
from app.services.free_agency import FreeAgencyService
from app.services.free_agent_appeal import FreeAgentAppealService
from app.services.free_agent_agents import FreeAgentAgentImportService
from app.services.admin_imports import OwnerAdminImportService
from app.services.gm_minimum_targets import GMMinimumTargetService
from app.services.gm_office import GMOfficeService
from app.services.owner_office import OwnerOfficeService
from app.services.offer_promises import OfferPromiseService
from app.services.player_identity import PlayerIdentityService
from app.services.player_catalog import PlayerCatalogService
from app.services.season_rollover import SeasonRolloverService
from app.services.trades import TradeService
from app.services.tracker import TrackerService
from app.services.team_detail import TeamDetailService
from app.services.waivers import WaiverService


class ServiceRepositoryBoundaryTests(unittest.TestCase):
    def test_remaining_sql_services_use_repository_boundaries(self) -> None:
        service_types = (
            LeagueWorkbookExportService,
            PlayerCatalogService,
            PlayerIdentityService,
            SeasonRolloverService,
            TrackerService,
            TradeService,
        )
        for service_type in service_types:
            with self.subTest(service=service_type.__name__):
                source = inspect.getsource(service_type)
                self.assertNotIn(".execute(", source)
                self.assertNotIn(".executemany(", source)
                self.assertNotIn(".executescript(", source)

        repository_types = (
            AdminExportRepository,
            PlayerCatalogRepository,
            PlayerIdentityRepository,
            SeasonRolloverRepository,
            TrackerRepository,
            TradeRepository,
        )
        for repository_type in repository_types:
            with self.subTest(repository=repository_type.__name__):
                self.assertIn(".execute(", inspect.getsource(repository_type))

    def test_cap_summary_is_pure_domain_logic(self) -> None:
        source = inspect.getsource(calculate_team_cap_summary)
        self.assertNotIn("self.", source)
        self.assertNotIn(".execute(", source)
        self.assertIn('"balance_breakdowns"', source)

    def test_free_agent_appeal_repository_owns_import_sql(self) -> None:
        repository_source = inspect.getsource(FreeAgentAppealRepository)
        service_source = inspect.getsource(FreeAgentAppealService)
        self.assertIn("INSERT INTO free_agent_team_appeal", repository_source)
        self.assertNotIn(".execute(", service_source)
        self.assertNotIn("self.db.", service_source)

    def test_free_agent_agent_repository_owns_assignment_sql(self) -> None:
        repository_source = inspect.getsource(FreeAgentAgentRepository)
        service_source = inspect.getsource(FreeAgentAgentImportService)
        self.assertIn("UPDATE free_agents SET agent", repository_source)
        self.assertIn("free_agent_reps", repository_source)
        self.assertNotIn(".execute(", service_source)

    def test_free_agency_service_owns_cross_repository_orchestration(self) -> None:
        repository_source = inspect.getsource(FreeAgencyRepository)
        service_source = inspect.getsource(FreeAgencyService)
        for facade in (
            "def create_offer_request(",
            "def offer_request(",
            "def cancel_offer_request(",
            "def create_promise(",
            "def list_promises(",
            "def update_promise(",
            "def create_bird_rights_renounce_request(",
            "def decide_offer_request(",
        ):
            self.assertNotIn(facade, repository_source)
        self.assertIn("self.gm_requests", service_source)
        self.assertIn("self.offer_promises", service_source)
        self.assertIn("self.players", service_source)

    def test_offer_promise_repository_owns_sql_without_policy_callbacks(self) -> None:
        repository_source = inspect.getsource(OfferPromiseRepository)
        service_source = inspect.getsource(OfferPromiseService)
        self.assertIn("INSERT INTO free_agent_offer_promises", repository_source)
        self.assertIn("SELECT 1 FROM player_profiles", repository_source)
        self.assertIn("SELECT value FROM app_settings", repository_source)
        for callback in (
            "OfferPromiseOperations",
            "user_access:",
            "settings:",
            "profile_exists_conn:",
            "season_label:",
            "normalize_team_code:",
        ):
            self.assertNotIn(callback, repository_source)
        self.assertIn("self._user_access", service_source)

    def test_owner_office_import_rules_are_service_owned(self) -> None:
        source = inspect.getsource(OwnerAdminImportService)
        for helper in (
            "def _owner_import_normalize_records(",
            "def _owner_import_group_records(",
            "def _owner_office_apply_calculated_rows(",
            "def _owner_office_import_normalize_records(",
            "def _owner_office_import_group_errors(",
            "def _owner_office_import_group_records(",
        ):
            self.assertIn(helper, source)

    def test_owner_admin_import_repository_owns_sql(self) -> None:
        repository_source = inspect.getsource(OwnerAdminImportRepository)
        service_source = inspect.getsource(OwnerAdminImportService)
        self.assertIn("INSERT INTO team_economy", repository_source)
        self.assertIn("INSERT INTO team_owner_office", repository_source)
        self.assertNotIn(".execute(", service_source)
        self.assertNotIn("self._db", service_source)

    def test_owner_office_repository_owns_aggregate_sql(self) -> None:
        repository_source = inspect.getsource(OwnerOfficeRepository)
        service_source = inspect.getsource(OwnerOfficeService)
        for table in (
            "team_owner_profiles",
            "team_owner_office",
            "owner_exit_interviews",
            "team_economy",
        ):
            self.assertIn(table, repository_source)
        self.assertNotIn(".execute(", service_source)
        self.assertNotIn("self._db", service_source)
        self.assertNotIn("OwnerOfficeOperations", service_source)

    def test_owner_office_repository_has_no_league_db_callbacks(self) -> None:
        source = inspect.getsource(OwnerOfficeRepository)
        for callback in (
            "exit_from_row:",
            "confidence_delta:",
            "get_owner_office:",
            "sanitize_background_url:",
            "detect_image_type:",
            "self._get_owner_office",
        ):
            self.assertNotIn(callback, source)

    def test_team_detail_service_has_no_embedded_sql(self) -> None:
        repository_source = inspect.getsource(TeamDetailRepository)
        service_source = inspect.getsource(TeamDetailService)
        for table in ("teams", "assets", "dead_contracts", "team_gm_history"):
            self.assertIn(table, repository_source)
        self.assertNotIn(".execute(", service_source)

    def test_season_rollover_repository_owns_workflow_sql(self) -> None:
        source = inspect.getsource(SeasonRolloverRepository)
        for legacy_helper in (
            "self.db._snapshot_payload_for_season(",
            "self.db._store_player_salary_history_for_season_conn(",
            "self.db._increment_player_bird_years(",
            "self.db._move_expired_players_to_free_agents(",
            "self.db._freeze_second_apron_pick_rollover(",
            "self.db._rollover_draft_assets_conn(",
            "self.db._cleanup_inactive_dead_contracts_conn(",
        ):
            self.assertNotIn(legacy_helper, source)

    def test_trade_repository_does_not_delegate_to_league_db_workflows(self) -> None:
        source = inspect.getsource(TradeRepository)
        for legacy_call in (
            "self.db._trade_machine_normalized_request(",
            "self.db.validate_trade_machine(",
            "self.db.trade_validation_from_process_payload(",
            "self.db.process_trade_command(",
            "self.db.process_trade_from_payload(",
            "self.db.process_trade(",
        ):
            self.assertNotIn(legacy_call, source)

    def test_gm_minimum_target_repository_owns_workflow_sql(self) -> None:
        repository_source = inspect.getsource(GMMinimumTargetRepository)
        service_source = inspect.getsource(GMMinimumTargetService)
        self.assertIn("INSERT INTO gm_minimum_targets", repository_source)
        self.assertIn("SELECT * FROM free_agent_team_appeal", repository_source)
        self.assertNotIn("self.db.set_gm_minimum_targets(", repository_source)
        self.assertNotIn(".execute(", service_source)

    def test_gm_office_repository_owns_aggregate_queries(self) -> None:
        repository_source = inspect.getsource(GMOfficeRepository)
        service_source = inspect.getsource(GMOfficeService)
        for table in (
            "gm_free_agent_offer_requests",
            "free_agent_favorites",
            "gm_free_agent_spending_limits",
        ):
            self.assertIn(table, repository_source)
        self.assertNotIn("self.db.list_gm_office(", repository_source)
        self.assertNotIn(".execute(", service_source)

    def test_services_wrap_legacy_database_with_narrow_repositories(self) -> None:
        legacy_db = object()
        cases = [
            (DraftService(legacy_db), DraftRepository),
            (
                FreeAgencyService(legacy_db, contract_seasons=[2025]),
                FreeAgencyRepository,
            ),
            (
                PlayerIdentityService(legacy_db, contract_seasons=[2025]),
                PlayerIdentityRepository,
            ),
            (
                SeasonRolloverService(
                    legacy_db,
                    contract_min_year=2025,
                    contract_max_start_year=2026,
                ),
                SeasonRolloverRepository,
            ),
            (TradeService(legacy_db), TradeRepository),
            (WaiverService(legacy_db), WaiverRepository),
        ]

        for service, repository_type in cases:
            with self.subTest(service=type(service).__name__):
                self.assertIsInstance(service.repository, repository_type)
                self.assertIs(legacy_db, service.repository.db)

    def test_services_accept_prebuilt_repositories_for_dependency_injection(self) -> None:
        legacy_db = object()
        repository = DraftRepository(legacy_db)

        service = DraftService(repository)

        self.assertIs(repository, service.repository)


if __name__ == "__main__":
    unittest.main()
