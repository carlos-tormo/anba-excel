"""Application logging configuration and request-aware formatting."""

from __future__ import annotations

import logging
import json
import os
import re
import sys
from typing import Any, Mapping, Optional, TextIO


LOGGER_NAMESPACE = "anba"
DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s method=%(method)s path=%(path)s %(message)s"


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        for field in ("request_id", "method", "path"):
            if not hasattr(record, field):
                setattr(record, field, "-")
        return super().format(record)


def get_logger(component: Optional[str] = None) -> logging.Logger:
    name = LOGGER_NAMESPACE if not component else f"{LOGGER_NAMESPACE}.{component}"
    return logging.getLogger(name)


def configure_logging(level: Optional[str] = None, stream: Optional[TextIO] = None) -> logging.Logger:
    logger = get_logger()
    configured_level = str(level or os.getenv("LOG_LEVEL", "INFO")).strip().upper()
    numeric_level = getattr(logging, configured_level, logging.INFO)
    logger.setLevel(numeric_level)
    logger.propagate = False
    if not any(getattr(handler, "_anba_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(ContextFormatter(DEFAULT_FORMAT))
        handler._anba_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger


def request_context(request_id: Any = None, method: Any = None, path: Any = None) -> dict[str, str]:
    return {
        "request_id": str(request_id or "-"),
        "method": str(method or "-"),
        "path": str(path or "-"),
    }


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_secrets(str(value))


def redact_secrets(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\b(Bot|Bearer)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]", text)
    text = re.sub(
        r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/[^\s\"'<>]+",
        "https://discord.com/api/webhooks/[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(access_token|refresh_token|client_secret|bot_token|webhook_url|password)\b([\"'\s:=]+)([^&\s\"',}]+)",
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    return text


def structured_event_message(event: str, fields: Mapping[str, Any]) -> str:
    payload = {"event": str(event or "event"), **_safe_json_value(dict(fields or {}))}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def log_structured(logger: logging.Logger, level: int, event: str, fields: Mapping[str, Any]) -> None:
    logger.log(level, structured_event_message(event, fields))
