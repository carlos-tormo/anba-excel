import logging
import unittest
from unittest.mock import patch

from app.auth.policies import normalize_team_code
from app.observability.audit import collect_team_codes, request_id_from_headers, resolve_entity_ids
from app.observability.logging import ContextFormatter, DEFAULT_FORMAT, request_context
from app.server import Handler


class AuditHelpersTests(unittest.TestCase):
    def test_request_id_is_sanitized_and_bounded(self):
        request_id = request_id_from_headers({"X-Request-ID": " req/<unsafe>:123 " + "x" * 100})

        self.assertEqual(80, len(request_id))
        self.assertTrue(request_id.startswith("requnsafe:123"))
        self.assertNotIn("/", request_id)

    def test_collect_team_codes_deduplicates_all_audit_sources(self):
        result = collect_team_codes(
            normalize_team_code,
            "atl",
            {"team_a": "BOS", "team_codes": ["ATL", "PHO"]},
            ["bos", "LAL"],
        )

        self.assertEqual(["ATL", "BOS", "LAL", "PHX"], result)

    def test_resolve_entity_ids_uses_entity_and_snapshot_fields(self):
        player_id, profile_id = resolve_entity_ids(
            "player",
            "15",
            details={"profile_id": 44},
            before={"player_id": 99, "profile_id": 55},
        )

        self.assertEqual("15", player_id)
        self.assertEqual("44", profile_id)


class LoggingHelpersTests(unittest.TestCase):
    def test_context_formatter_supplies_defaults_for_background_logs(self):
        record = logging.LogRecord("anba.test", logging.WARNING, __file__, 1, "background warning", (), None)

        rendered = ContextFormatter(DEFAULT_FORMAT).format(record)

        self.assertIn("request_id=- method=- path=-", rendered)
        self.assertIn("background warning", rendered)

    def test_request_context_normalizes_missing_values(self):
        self.assertEqual(
            {"request_id": "req-1", "method": "POST", "path": "-"},
            request_context("req-1", "POST", None),
        )

    def test_handler_logging_adds_request_correlation(self):
        handler = object.__new__(Handler)
        handler._audit_request_id = "req-handler-1"
        handler.command = "GET"
        handler.path = "/api/admin/logs?limit=10"

        with patch("app.server.logger.info") as log_info:
            handler.log_message("served %s", "audit")

        log_info.assert_called_once_with(
            "served %s",
            "audit",
            extra={"request_id": "req-handler-1", "method": "GET", "path": "/api/admin/logs"},
        )


if __name__ == "__main__":
    unittest.main()
