import unittest
from unittest.mock import Mock
from urllib.error import URLError

from app.services.assets import AssetAdminService
from app.services.authentication import GoogleOAuthCompletionError, GoogleOAuthService
from app.services.player_roster import PlayerRosterService
from app.services.team_admin import TeamAdminService


class RouteWorkflowServiceTests(unittest.TestCase):
    def test_google_oauth_completion_builds_persisted_user_session(self) -> None:
        integration = Mock()
        integration.exchange_code.return_value = {"access_token": "access"}
        integration.fetch_userinfo.return_value = {
            "sub": "google-1", "email": "GM@Example.com", "name": "GM", "picture": "photo"
        }
        users = Mock()
        users.upsert_google_user.return_value = {"id": 7, "display_name": "General Manager"}
        users.access_for_email.return_value = {"team_codes": ["ATL"], "is_co_admin": False}
        service = GoogleOAuthService(
            integration,
            users,
            admin_emails=[],
            gm_accounts={},
            now=lambda: "2025-01-01T00:00:00Z",
        )

        result = service.complete("authorization-code")

        self.assertEqual(result["role"], "gm")
        self.assertEqual(result["team_codes"], ["ATL"])
        self.assertEqual(result["session"]["user_id"], 7)
        self.assertEqual(result["session"]["email"], "gm@example.com")

    def test_google_oauth_completion_maps_transport_and_profile_failures(self) -> None:
        integration = Mock()
        integration.exchange_code.side_effect = URLError("offline")
        service = GoogleOAuthService(
            integration, Mock(), admin_emails=[], gm_accounts={}, now=lambda: "now"
        )
        with self.assertRaisesRegex(GoogleOAuthCompletionError, "google_exchange_failed"):
            service.complete("code")

        integration.exchange_code.side_effect = None
        integration.exchange_code.return_value = {"access_token": "access"}
        integration.fetch_userinfo.return_value = {"sub": "", "email": ""}
        with self.assertRaisesRegex(GoogleOAuthCompletionError, "google_profile_invalid"):
            service.complete("code")

    def test_team_update_normalizes_fields_and_default_hard_cap_year(self) -> None:
        teams, settings = Mock(), Mock()
        teams.update_fields.return_value = True
        teams.update_hard_cap.return_value = True
        settings.get_all.return_value = {"current_year": "2026"}
        service = TeamAdminService(teams, settings, min_year=2025, max_year=2031)

        result = service.update(
            "atl", {"gm": " New GM ", "cash_sent": "12.5", "apron_hard_cap": "second"}
        )

        teams.update_fields.assert_called_once_with("atl", {"gm": "New GM", "cash_sent": 12.5})
        teams.update_hard_cap.assert_called_once_with("atl", 2026, "second")
        self.assertTrue(result["ok"])
        self.assertEqual(result["audit"]["season_year"], 2026)

    def test_asset_updates_include_before_and_after_audit_snapshots(self) -> None:
        repository = Mock()
        repository.update_asset.return_value = True
        repository.asset.return_value = {"id": 3, "team_code": "ATL", "label": "After"}
        service = AssetAdminService(repository)
        before = {"id": 3, "team_code": "ATL", "label": "Before"}

        result = service.update_asset(3, {"label": "After"}, before=before)

        self.assertEqual(result["audit"]["before"], before)
        self.assertEqual(result["audit"]["after"]["label"], "After")
        with self.assertRaisesRegex(ValueError, "dead_cap_moved_to_dead_contracts"):
            service.update_asset(3, {"asset_type": "dead_cap"}, before=before)

    def test_roster_mutation_and_move_return_audit_commands(self) -> None:
        players, waivers = Mock(), Mock()
        waivers.cut_player.return_value = {
            "profile_id": 4,
            "player_name": "Player",
            "free_agent_id": 8,
            "dead_contract_id": 9,
            "team_code": "ATL",
        }
        players.move.return_value = True
        players.record.return_value = {"id": 5, "team_code": "BKN"}
        service = PlayerRosterService(players, waivers)
        before = {"id": 5, "team_code": "ATL"}

        cut = service.mutate(5, "cut", {}, before=before)
        moved = service.move(5, "BKN", before=before)

        self.assertEqual(cut["audit"]["details"]["dead_contract_id"], 9)
        self.assertEqual(moved["audit"]["team_codes"], ["ATL", "BKN"])
        self.assertEqual(moved["audit"]["after"]["team_code"], "BKN")


if __name__ == "__main__":
    unittest.main()
