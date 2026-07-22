import logging
import unittest
from unittest.mock import patch

from app.auth.policies import normalize_team_code
from app.db.connection import connect_sqlite
from app.observability.audit import collect_team_codes, request_id_from_headers, resolve_entity_ids
from app.observability.logging import ContextFormatter, DEFAULT_FORMAT, request_context, structured_event_message
from app.observability.operations import (
    current_request_metrics,
    finish_request_metrics,
    normalize_route,
    record_db_query,
    record_response_metrics,
    start_request_metrics,
)
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

    def test_structured_event_message_redacts_secret_values(self):
        message = structured_event_message(
            "integration_failure",
            {"error": "failed with Bot abc.def.ghi and access_token=oauth-secret"},
        )

        self.assertIn('"event":"integration_failure"', message)
        self.assertNotIn("abc.def.ghi", message)
        self.assertNotIn("oauth-secret", message)


class OperationalMetricsTests(unittest.TestCase):
    def test_normalize_route_replaces_ids_and_tokens(self):
        self.assertEqual(
            "/api/teams/atl/players/{id}/contracts/{token}",
            normalize_route("/api/teams/ATL/players/123/contracts/abcdef1234567890?debug=1"),
        )

    def test_request_metrics_records_response_and_database_activity(self):
        token = start_request_metrics("req-1", "GET", "team-detail", "/api/teams/ATL")
        try:
            record_db_query("SELECT 1", 0.003)
            record_response_metrics(404, 27, "team_not_found")
            with patch("app.observability.operations.log_structured") as log_structured:
                fields = finish_request_metrics(
                    token,
                    user_id=7,
                    role="gm",
                    team_scope=["ATL"],
                )
        finally:
            if current_request_metrics() is not None:
                from app.observability.operations import reset_request_metrics

                reset_request_metrics(token)

        self.assertEqual("req-1", fields["request_id"])
        self.assertEqual("team-detail", fields["route"])
        self.assertEqual(404, fields["status_code"])
        self.assertEqual("team_not_found", fields["error_classification"])
        self.assertEqual(1, fields["db_query_count"])
        self.assertEqual(27, fields["response_size"])
        self.assertEqual(["ATL"], fields["team_scope"])
        self.assertEqual("gm", fields["role"])
        self.assertEqual("7", fields["user_id"])
        log_structured.assert_called_once()

    def test_sqlite_connection_records_query_count_without_sql_values(self):
        token = start_request_metrics("req-db", "GET", "db-test", "/db-test")
        try:
            with connect_sqlite(":memory:") as conn:
                conn.execute("CREATE TABLE t (secret TEXT)")
                conn.execute("INSERT INTO t (secret) VALUES (?)", ("password-value",))
                conn.execute("SELECT secret FROM t WHERE secret = ?", ("password-value",)).fetchone()
            metrics = current_request_metrics()
            self.assertIsNotNone(metrics)
            self.assertGreaterEqual(metrics.db_query_count, 3)
            self.assertGreater(metrics.db_duration_seconds, 0)
        finally:
            from app.observability.operations import reset_request_metrics

            reset_request_metrics(token)


if __name__ == "__main__":
    unittest.main()
