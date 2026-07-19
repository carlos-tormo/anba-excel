import unittest

from app.db.repositories.draft import DraftRepository
from app.db.repositories.free_agency import FreeAgencyRepository
from app.db.repositories.player_identity import PlayerIdentityRepository
from app.db.repositories.season_rollover import SeasonRolloverRepository
from app.db.repositories.trades import TradeRepository
from app.db.repositories.waivers import WaiverRepository
from app.services.draft import DraftService
from app.services.free_agency import FreeAgencyService
from app.services.player_identity import PlayerIdentityService
from app.services.season_rollover import SeasonRolloverService
from app.services.trades import TradeService
from app.services.waivers import WaiverService


class ServiceRepositoryBoundaryTests(unittest.TestCase):
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
