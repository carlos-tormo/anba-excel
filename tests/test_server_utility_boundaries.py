import ast
from pathlib import Path
import unittest

from app import server
from app.application import ApplicationConfig, ApplicationContainer


class ServerUtilityBoundaryTests(unittest.TestCase):
    def test_server_has_no_top_level_utilities_before_league_db(self) -> None:
        source_path = Path(server.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        utility_names = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "LeagueDB":
                break
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                utility_names.append(node.name)
        self.assertEqual([], utility_names)

    def test_compatibility_exports_come_from_focused_modules(self) -> None:
        expected_modules = {
            "validate_free_agent_offer_payload": "app.routes.validation",
            "normalize_player_happiness": "app.domain.normalization",
            "contract_option_rejection_clear_payload": "app.domain.contracts",
            "sanitize_http_image_url": "app.integrations.media",
            "row_to_dict": "app.db.rows",
            "xlsx_workbook_bytes": "app.import_export.spreadsheets",
        }
        for name, expected_module in expected_modules.items():
            with self.subTest(name=name):
                self.assertEqual(expected_module, getattr(server, name).__module__)

    def test_handler_uses_application_container_instead_of_service_factories(self) -> None:
        removed_factories = {
            "_free_agency_service", "_trade_workflow_service", "_waiver_service",
            "_draft_service", "_season_rollover_service", "_settings_service",
            "_player_admin_service", "_team_admin_service", "_asset_admin_service",
            "_player_roster_service", "_player_identity_service", "_google_oauth_service",
            "_outbox_delivery_service", "_discord_client", "_openai_client",
            "_discord_notification_delivery_service", "_free_agent_offer_notification_service",
            "_owner_interview_service", "_owner_office_workflow_service",
            "_notify_player_cut", "_notify_free_agent_signed",
            "_notify_draft_pick_selection", "_notify_contract_option_action",
            "_notify_bird_rights_renounced", "_post_press_article",
        }
        self.assertTrue(removed_factories.isdisjoint(vars(server.Handler)))
        handler_methods = [
            value for value in vars(server.Handler).values() if callable(value)
        ]
        self.assertLessEqual(len(handler_methods), 70)

        routes_dir = Path(server.__file__).parent / "routes"
        route_source = "\n".join(
            path.read_text(encoding="utf-8") for path in routes_dir.glob("*.py")
        )
        for factory in removed_factories:
            self.assertNotIn(f"handler.{factory}(", route_source)
        self.assertNotIn("handler.db", route_source)

    def test_application_container_caches_service_instances(self) -> None:
        config = ApplicationConfig(
            contract_seasons=(2025, 2026), contract_min_year=2025,
            contract_max_start_year=2026, cap_forecast_min_year=2025,
            cap_forecast_max_year=2030, unrestricted_free_agent_type="No restringido",
            cap_hold_source="cap_hold", google_client_id="", google_client_secret="",
            google_redirect_uri="", admin_emails=frozenset(), gm_accounts={},
        )
        container = ApplicationContainer(
            object(), config, opener=lambda *_args, **_kwargs: None,
            now=lambda: "now", log_error=lambda *_args, **_kwargs: None,
        )
        self.assertIs(container.free_agency, container.free_agency)
        self.assertIs(container.draft, container.draft)

    def test_league_db_has_no_unreferenced_compatibility_methods(self) -> None:
        source_path = Path(server.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        league_db = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "LeagueDB"
        )
        methods = {
            node.name
            for node in league_db.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        referenced = set()
        for root in (source_path.parent, source_path.parent.parent / "tests"):
            for path in root.rglob("*.py"):
                parsed = ast.parse(path.read_text(encoding="utf-8"))
                referenced.update(
                    node.attr for node in ast.walk(parsed)
                    if isinstance(node, ast.Attribute)
                )
        self.assertEqual(set(), methods - referenced)
        self.assertLessEqual(len(methods), 200)


if __name__ == "__main__":
    unittest.main()
