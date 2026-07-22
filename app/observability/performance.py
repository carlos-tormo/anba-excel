"""Explicit performance and query-count budgets for route classes.

The timing targets are production SLO-style budgets. Unit tests should avoid
strict wall-clock assertions, but they can validate that representative
workflows remain within query-count budgets using request metrics.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from .operations import current_request_metrics


@dataclass(frozen=True)
class EndpointPerformanceBudget:
    """Initial p95 target for a class of endpoints."""

    name: str
    p95_ms: int
    external_delivery_included: bool = True
    measured_separately: bool = False


ENDPOINT_PERFORMANCE_BUDGETS: Dict[str, EndpointPerformanceBudget] = {
    "simple_public_get": EndpointPerformanceBudget("simple_public_get", 250),
    "team_detail_get": EndpointPerformanceBudget("team_detail_get", 500),
    "tracker_get": EndpointPerformanceBudget("tracker_get", 1_000),
    "normal_mutation": EndpointPerformanceBudget(
        "normal_mutation",
        750,
        external_delivery_included=False,
    ),
    "heavy_import_or_rollover": EndpointPerformanceBudget(
        "heavy_import_or_rollover",
        0,
        external_delivery_included=False,
        measured_separately=True,
    ),
}


QUERY_COUNT_BUDGETS: Dict[str, int] = {
    "simple_public_get": 4,
    "team_detail_get": 8,
    "tracker_get": 12,
    "normal_mutation": 16,
}


class QueryBudgetExceeded(AssertionError):
    """Raised when an instrumented workflow exceeds its query-count budget."""


@contextmanager
def assert_max_queries(max_queries: int, *, label: Optional[str] = None) -> Iterator[None]:
    """Assert that the active request metrics stay under a query-count ceiling.

    This intentionally depends on ``start_request_metrics`` having been called
    by the test or request lifecycle. If metrics are missing, the assertion
    fails; otherwise query-budget tests could silently stop measuring anything.
    """

    metrics = current_request_metrics()
    if metrics is None:
        raise QueryBudgetExceeded(f"{label or 'query budget'} has no active request metrics")
    before = metrics.db_query_count
    yield
    after_metrics = current_request_metrics()
    if after_metrics is None:
        raise QueryBudgetExceeded(f"{label or 'query budget'} lost request metrics")
    actual = after_metrics.db_query_count - before
    if actual > int(max_queries):
        name = f"{label}: " if label else ""
        raise QueryBudgetExceeded(f"{name}{actual} queries exceeded budget {int(max_queries)}")


def budget_for(endpoint_class: Any) -> EndpointPerformanceBudget:
    return ENDPOINT_PERFORMANCE_BUDGETS[str(endpoint_class)]


def query_budget_for(endpoint_class: Any) -> int:
    return QUERY_COUNT_BUDGETS[str(endpoint_class)]
