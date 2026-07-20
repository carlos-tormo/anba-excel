import ast
import inspect
import unittest

from app.routes import get_remaining, owner_office, patch_remaining, players, post_remaining
from app.services.assets import AssetAdminService
from app.services.authentication import GoogleOAuthService
from app.services.free_agency import FreeAgencyService
from app.services.player_admin import PlayerAdminService
from app.services.owner_office import OwnerOfficeService
from app.services.player_roster import PlayerRosterService
from app.services.settings import SettingsService
from app.services.team_admin import TeamAdminService
from app.services.trades import TradeService


class ThinRouteBoundaryTests(unittest.TestCase):
    ROUTES = (
        patch_remaining.update_settings,
        patch_remaining.decide_option_request,
        patch_remaining.update_player,
        patch_remaining.decide_free_agent_offer_request,
        post_remaining.process_trade,
        owner_office.update_owner_exit_interview,
        get_remaining.complete_google_oauth,
        patch_remaining.update_team,
        patch_remaining.update_asset,
        patch_remaining.update_dead_contract,
        players.mutate_roster_player,
        players.move_player,
    )

    def test_priority_routes_do_not_call_handler_database(self) -> None:
        for route in self.ROUTES:
            source = inspect.getsource(route)
            self.assertNotIn("handler.db", source, route.__name__)

    def test_priority_routes_are_bounded_http_adapters(self) -> None:
        for route in self.ROUTES:
            tree = ast.parse(inspect.getsource(route))
            function = tree.body[0]
            line_count = function.end_lineno - function.lineno + 1
            self.assertLessEqual(line_count, 60, route.__name__)

    def test_application_services_own_the_extracted_workflows(self) -> None:
        ownership = (
            (SettingsService, "update"),
            (PlayerAdminService, "decide_option"),
            (PlayerAdminService, "update_player"),
            (FreeAgencyService, "decide_offer"),
            (TradeService, "process_request"),
            (OwnerOfficeService, "update_exit_interview"),
            (GoogleOAuthService, "complete"),
            (TeamAdminService, "update"),
            (AssetAdminService, "update_asset"),
            (AssetAdminService, "update_dead_contract"),
            (PlayerRosterService, "mutate"),
            (PlayerRosterService, "move"),
        )
        for service, method in ownership:
            self.assertTrue(callable(getattr(service, method, None)), f"{service.__name__}.{method}")


if __name__ == "__main__":
    unittest.main()
