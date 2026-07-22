"""Structured operational metrics for HTTP requests and database activity."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, Iterable, Optional

from .logging import get_logger, log_structured


HTTP_SLOW_SECONDS = 1.0
DB_QUERY_SLOW_SECONDS = 0.250
DB_LOCK_WAIT_SLOW_SECONDS = 0.500
EXTERNAL_CALL_SLOW_SECONDS = 2.0

_CURRENT_REQUEST_METRICS: ContextVar[Optional["RequestMetrics"]] = ContextVar(
    "anba_request_metrics",
    default=None,
)


@dataclass
class RequestMetrics:
    request_id: str
    method: str
    route: str
    path: str
    started_at: float = field(default_factory=time.perf_counter)
    status_code: int = 0
    response_size: int = 0
    error_classification: str = ""
    db_query_count: int = 0
    db_duration_seconds: float = 0.0
    db_wait_seconds: float = 0.0
    user_id: str = ""
    role: str = ""
    team_scope: list[str] = field(default_factory=list)

    def record_response(self, status_code: Any, response_size: Any, error_classification: Any = "") -> None:
        try:
            self.status_code = int(status_code)
        except (TypeError, ValueError):
            self.status_code = 0
        try:
            self.response_size = max(0, int(response_size))
        except (TypeError, ValueError):
            self.response_size = 0
        if error_classification:
            self.error_classification = str(error_classification)

    def record_db_query(self, sql: Any, duration_seconds: float) -> None:
        self.db_query_count += 1
        self.db_duration_seconds += max(0.0, float(duration_seconds))
        if is_lock_wait_sql(sql):
            self.db_wait_seconds += max(0.0, float(duration_seconds))

    def finish_fields(self, *, user_id: Any = "", role: Any = "", team_scope: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
        duration_seconds = max(0.0, time.perf_counter() - self.started_at)
        status = self.status_code or 500
        classification = self.error_classification or classify_status(status)
        scope = [str(item).strip().upper() for item in (team_scope or self.team_scope or []) if str(item or "").strip()]
        return {
            "request_id": self.request_id,
            "method": self.method,
            "route": self.route,
            "path": self.path,
            "user_id": str(user_id or self.user_id or ""),
            "role": str(role or self.role or ""),
            "team_scope": sorted(dict.fromkeys(scope)),
            "status_code": status,
            "duration_ms": round(duration_seconds * 1000, 2),
            "db_wait_ms": round(self.db_wait_seconds * 1000, 2),
            "db_query_count": self.db_query_count,
            "db_duration_ms": round(self.db_duration_seconds * 1000, 2),
            "response_size": self.response_size,
            "error_classification": classification,
            "slow": duration_seconds >= HTTP_SLOW_SECONDS,
        }


def classify_status(status_code: int) -> str:
    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "client_error"
    return "ok"


def normalize_route(path: Any) -> str:
    text = str(path or "").split("?", 1)[0] or "/"
    pieces = []
    for part in text.strip("/").split("/"):
        if not part:
            continue
        lowered = part.lower()
        if lowered.isdigit():
            pieces.append("{id}")
        elif len(lowered) >= 16 and all(ch.isalnum() or ch in {"-", "_"} for ch in lowered):
            pieces.append("{token}")
        else:
            pieces.append(lowered)
    return "/" + "/".join(pieces) if pieces else "/"


def is_lock_wait_sql(sql: Any) -> bool:
    text = str(sql or "").strip().upper()
    return text.startswith("BEGIN IMMEDIATE") or text.startswith("BEGIN EXCLUSIVE")


def db_operation(sql: Any) -> str:
    text = str(sql or "").strip().split(None, 1)
    return text[0].upper() if text else "SQL"


def start_request_metrics(request_id: str, method: Any, route: Any, path: Any) -> Token:
    return _CURRENT_REQUEST_METRICS.set(
        RequestMetrics(
            request_id=str(request_id or "-"),
            method=str(method or "-"),
            route=str(route or normalize_route(path)),
            path=str(path or "-"),
        )
    )


def current_request_metrics() -> Optional[RequestMetrics]:
    return _CURRENT_REQUEST_METRICS.get()


def reset_request_metrics(token: Token) -> None:
    _CURRENT_REQUEST_METRICS.reset(token)


def record_response_metrics(status_code: Any, response_size: Any, error_classification: Any = "") -> None:
    metrics = current_request_metrics()
    if metrics:
        metrics.record_response(status_code, response_size, error_classification)


def record_db_query(sql: Any, duration_seconds: float, *, logger: Optional[logging.Logger] = None) -> None:
    metrics = current_request_metrics()
    if metrics:
        metrics.record_db_query(sql, duration_seconds)
    threshold = DB_LOCK_WAIT_SLOW_SECONDS if is_lock_wait_sql(sql) else DB_QUERY_SLOW_SECONDS
    if duration_seconds >= threshold:
        log_structured(
            logger or get_logger("db"),
            logging.WARNING,
            "db_slow_operation",
            {
                "operation": db_operation(sql),
                "duration_ms": round(max(0.0, duration_seconds) * 1000, 2),
                "lock_wait": is_lock_wait_sql(sql),
            },
        )


def record_external_call(
    provider: Any,
    operation: Any,
    duration_seconds: float,
    *,
    ok: bool,
    status_code: Any = None,
    error_classification: Any = "",
    logger: Optional[logging.Logger] = None,
) -> None:
    if duration_seconds < EXTERNAL_CALL_SLOW_SECONDS:
        return
    log_structured(
        logger or get_logger("external"),
        logging.WARNING,
        "external_slow_call",
        {
            "provider": str(provider or ""),
            "operation": str(operation or ""),
            "duration_ms": round(max(0.0, float(duration_seconds)) * 1000, 2),
            "ok": bool(ok),
            "status_code": str(status_code or ""),
            "error_classification": str(error_classification or ""),
        },
    )


def finish_request_metrics(
    token: Token,
    *,
    user_id: Any = "",
    role: Any = "",
    team_scope: Optional[Iterable[Any]] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    metrics = current_request_metrics()
    fields: Dict[str, Any] = {}
    if metrics:
        fields = metrics.finish_fields(user_id=user_id, role=role, team_scope=team_scope)
        log_structured(logger or get_logger("http"), logging.INFO, "http_request", fields)
    reset_request_metrics(token)
    return fields
