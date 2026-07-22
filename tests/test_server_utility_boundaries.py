import ast
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import server
from app.application import ApplicationConfig, ApplicationContainer


class ServerUtilityBoundaryTests(unittest.TestCase):
    @staticmethod
    def _container_config() -> ApplicationConfig:
        return ApplicationConfig(
            contract_seasons=(2025, 2026), contract_min_year=2025,
            contract_max_start_year=2026, cap_forecast_min_year=2025,
            cap_forecast_max_year=2030, unrestricted_free_agent_type="No restringido",
            cap_hold_source="cap_hold", google_client_id="", google_client_secret="",
            google_redirect_uri="", admin_emails=frozenset(), gm_accounts={},
        )

    @staticmethod
    def _complete_dependency_db(**overrides):
        attrs = {
            attr: object()
            for attr in ApplicationContainer.REQUIRED_LEGACY_DEPENDENCIES
        }
        attrs["_audit_log_service"] = lambda: object()
        attrs.update(overrides)
        return SimpleNamespace(**attrs)

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

    def test_server_supports_direct_script_import_startup_shape(self) -> None:
        server_path = Path(server.__file__)
        original_path = list(sys.path)
        sys.path.insert(0, str(server_path.parent))
        try:
            runpy.run_path(str(server_path), run_name="__codex_import_probe__")
        finally:
            sys.path[:] = original_path

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
        container = ApplicationContainer(
            self._complete_dependency_db(), self._container_config(), opener=lambda *_args, **_kwargs: None,
            now=lambda: "now", log_error=lambda *_args, **_kwargs: None,
        )
        self.assertIs(container.free_agency, container.free_agency)
        self.assertIs(container.draft, container.draft)

    def test_application_container_missing_dependency_fails_loudly(self) -> None:
        container = ApplicationContainer(
            object(), self._container_config(), opener=lambda *_args, **_kwargs: None,
            now=lambda: "now", log_error=lambda *_args, **_kwargs: None,
        )

        with self.assertRaisesRegex(RuntimeError, "application_dependency_missing:_team_repository"):
            _ = container.teams

    def test_application_container_reports_unresolved_legacy_dependencies(self) -> None:
        db = self._complete_dependency_db(_trade_repository=None)
        container = ApplicationContainer(
            db, self._container_config(), opener=lambda *_args, **_kwargs: None,
            now=lambda: "now", log_error=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(["_trade_repository"], container.unresolved_legacy_dependencies())
        with self.assertRaisesRegex(RuntimeError, "application_dependencies_missing:_trade_repository"):
            container.validate_dependencies()

    def test_application_container_complete_dependency_set_has_no_unresolved_dependencies(self) -> None:
        container = ApplicationContainer(
            self._complete_dependency_db(), self._container_config(), opener=lambda *_args, **_kwargs: None,
            now=lambda: "now", log_error=lambda *_args, **_kwargs: None,
        )

        self.assertEqual([], container.unresolved_legacy_dependencies())
        container.validate_dependencies()

    def test_server_startup_validates_application_dependencies(self) -> None:
        db = self._complete_dependency_db()
        db.ensure_auth_schema = lambda: None
        db.warm_tracker_cache = lambda: None

        class FakeServer:
            def __init__(self, *_args, **_kwargs):
                pass

            def serve_forever(self):
                raise RuntimeError("stop_after_validation")

        with patch.object(server, "LeagueDB", return_value=db), \
            patch.object(server, "ThreadingHTTPServer", FakeServer), \
            patch.object(server.os.path, "exists", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "stop_after_validation"):
                server.run_server("/tmp/fake.db", "127.0.0.1", 0)

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
