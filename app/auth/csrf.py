"""Pure origin and CSRF checks used by the HTTP adapter."""

from __future__ import annotations

import secrets
from typing import Any, Mapping, Optional
from urllib.parse import urlparse


def presented_origin(headers: Mapping[str, Any]) -> str:
    origin = str(headers.get("Origin") or "").strip().rstrip("/")
    if origin:
        return origin.lower()
    referer = str(headers.get("Referer") or "").strip()
    if not referer:
        return ""
    parsed = urlparse(referer)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".lower()
    return ""


def same_origin_request_ok(
    headers: Mapping[str, Any],
    request_origin: str,
    allowed_origins: set[str],
) -> bool:
    presented = presented_origin(headers)
    if not presented:
        return True
    if presented == "null":
        return False
    allowed = {str(origin).rstrip("/").lower() for origin in allowed_origins}
    if request_origin:
        allowed.add(request_origin.rstrip("/").lower())
    return presented in allowed


def csrf_token_ok(session: Optional[Mapping[str, Any]], provided_token: Any) -> bool:
    if not session:
        return False
    expected = str(session.get("csrf_token") or "")
    provided = str(provided_token or "").strip()
    return bool(expected and provided and secrets.compare_digest(expected, provided))

