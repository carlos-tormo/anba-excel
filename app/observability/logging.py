"""Application logging configuration and request-aware formatting."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional, TextIO


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
