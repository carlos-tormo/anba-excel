import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

from app.db.connection import connect_sqlite
from app.observability.operations import reset_request_metrics, start_request_metrics
from app.observability.performance import (
    ENDPOINT_PERFORMANCE_BUDGETS,
    QUERY_COUNT_BUDGETS,
    QueryBudgetExceeded,
    assert_max_queries,
    query_budget_for,
)
from app.routes import GET_ROUTES
from app.routing import dispatch_routes


class TrackerReadModelFixture:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def list(self, season_year=None):
        selected_year = int(season_year or 2027)
        with connect_sqlite(self.db_path) as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT team_code, cap_total, payroll, roster_count
                    FROM tracker_rows
                    WHERE season_year = ?
                    ORDER BY team_code
                    """,
                    (selected_year,),
                ).fetchall()
            ]
            seasons = [
                int(row["season_year"])
                for row in conn.execute(
                    "SELECT DISTINCT season_year FROM tracker_rows ORDER BY season_year"
                ).fetchall()
            ]
        return {
            "rows": rows,
            "season_year": selected_year,
            "seasons": seasons,
            "timings": {"row_count": float(len(rows)), "fixture": 1.0},
        }


class TeamDetailReadModelFixture:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def get(self, code, move_season_year=None):
        with connect_sqlite(self.db_path) as conn:
            settings = {
                str(row["key"]): str(row["value"])
                for row in conn.execute("SELECT key, value FROM app_settings").fetchall()
            }
            team = conn.execute(
                "SELECT code, name FROM teams WHERE code = ?",
                (str(code or "").upper(),),
            ).fetchone()
            if not team:
                return None
            players = [
                dict(row)
                for row in conn.execute(
                    "SELECT name, salary FROM players WHERE team_code = ? ORDER BY name",
                    (team["code"],),
                ).fetchall()
            ]
            assets = [
                dict(row)
                for row in conn.execute(
                    "SELECT label FROM assets WHERE team_code = ? ORDER BY label",
                    (team["code"],),
                ).fetchall()
            ]
            dead_contracts = [
                dict(row)
                for row in conn.execute(
                    "SELECT label FROM dead_contracts WHERE team_code = ? ORDER BY label",
                    (team["code"],),
                ).fetchall()
            ]
        return {
            "team_code": team["code"],
            "team_name": team["name"],
            "season_year": int(move_season_year or settings.get("current_year") or 2027),
            "players": players,
            "assets": assets,
            "dead_contracts": dead_contracts,
        }


def create_performance_fixture_db() -> str:
    descriptor, db_path = tempfile.mkstemp(prefix="anba-performance-budget-", suffix=".db")
    os.close(descriptor)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE tracker_rows (
                team_code TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                cap_total REAL NOT NULL,
                payroll REAL NOT NULL,
                roster_count INTEGER NOT NULL
            );
            CREATE TABLE teams (code TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE players (
                team_code TEXT NOT NULL,
                name TEXT NOT NULL,
                salary REAL NOT NULL
            );
            CREATE TABLE assets (team_code TEXT NOT NULL, label TEXT NOT NULL);
            CREATE TABLE dead_contracts (team_code TEXT NOT NULL, label TEXT NOT NULL);
            """
        )
        conn.execute("INSERT INTO app_settings (key, value) VALUES ('current_year', '2027')")
        team_rows = [(f"T{index:02d}", f"Team {index:02d}") for index in range(1, 31)]
        conn.executemany("INSERT INTO teams (code, name) VALUES (?, ?)", team_rows)
        conn.executemany(
            """
            INSERT INTO tracker_rows (team_code, season_year, cap_total, payroll, roster_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (code, season_year, 150_000_000 + index, 140_000_000 + index, 15)
                for index, (code, _name) in enumerate(team_rows)
                for season_year in (2027, 2028, 2029)
            ],
        )
        conn.executemany(
            "INSERT INTO players (team_code, name, salary) VALUES (?, ?, ?)",
            [
                (code, f"Player {code}-{slot:02d}", 1_000_000 + slot)
                for code, _name in team_rows
                for slot in range(1, 16)
            ],
        )
        conn.executemany(
            "INSERT INTO assets (team_code, label) VALUES (?, ?)",
            [(code, f"Pick {slot}") for code, _name in team_rows for slot in range(1, 5)],
        )
        conn.executemany(
            "INSERT INTO dead_contracts (team_code, label) VALUES (?, ?)",
            [(code, f"Dead {slot}") for code, _name in team_rows for slot in range(1, 3)],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


class PerformanceBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = create_performance_fixture_db()

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_initial_endpoint_p95_budgets_are_explicit(self) -> None:
        self.assertEqual(250, ENDPOINT_PERFORMANCE_BUDGETS["simple_public_get"].p95_ms)
        self.assertEqual(500, ENDPOINT_PERFORMANCE_BUDGETS["team_detail_get"].p95_ms)
        self.assertEqual(1_000, ENDPOINT_PERFORMANCE_BUDGETS["tracker_get"].p95_ms)
        self.assertEqual(750, ENDPOINT_PERFORMANCE_BUDGETS["normal_mutation"].p95_ms)
        self.assertFalse(ENDPOINT_PERFORMANCE_BUDGETS["normal_mutation"].external_delivery_included)
        self.assertTrue(ENDPOINT_PERFORMANCE_BUDGETS["heavy_import_or_rollover"].measured_separately)

    def test_query_count_budgets_are_explicit(self) -> None:
        self.assertEqual(4, QUERY_COUNT_BUDGETS["simple_public_get"])
        self.assertEqual(8, QUERY_COUNT_BUDGETS["team_detail_get"])
        self.assertEqual(12, QUERY_COUNT_BUDGETS["tracker_get"])
        self.assertEqual(16, QUERY_COUNT_BUDGETS["normal_mutation"])

    def test_assert_max_queries_fails_when_metrics_are_missing(self) -> None:
        with self.assertRaises(QueryBudgetExceeded):
            with assert_max_queries(1, label="missing-metrics"):
                pass

    def test_team_detail_get_stays_within_query_budget(self) -> None:
        token = start_request_metrics("perf-team", "GET", "/api/teams/{code}", "/api/teams/T01")
        try:
            handler = SimpleNamespace(
                _send_route_response=Mock(),
                app=SimpleNamespace(team_detail=TeamDetailReadModelFixture(self.db_path)),
            )
            with assert_max_queries(query_budget_for("team_detail_get"), label="/api/teams/{code}"):
                matched = dispatch_routes(handler, urlparse("/api/teams/T01?season=2027"), GET_ROUTES)
        finally:
            reset_request_metrics(token)

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual(15, len(response.payload["players"]))

    def test_tracker_get_uses_production_sized_fixture_within_query_budget(self) -> None:
        token = start_request_metrics("perf-tracker", "GET", "/api/tracker", "/api/tracker")
        try:
            handler = SimpleNamespace(
                _send_route_response=Mock(),
                log_message=Mock(),
                app=SimpleNamespace(tracker=TrackerReadModelFixture(self.db_path)),
            )
            with assert_max_queries(query_budget_for("tracker_get"), label="/api/tracker"):
                matched = dispatch_routes(handler, urlparse("/api/tracker?season=2027"), GET_ROUTES)
        finally:
            reset_request_metrics(token)

        self.assertTrue(matched)
        response = handler._send_route_response.call_args.args[0]
        self.assertEqual(200, response.status)
        self.assertEqual(30, len(response.payload["tracker"]))
        self.assertEqual(2027, response.payload["season_year"])


if __name__ == "__main__":
    unittest.main()
