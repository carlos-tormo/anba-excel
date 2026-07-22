"""HTTP security and cache header policy."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse


STATIC_ASSET_EXTENSIONS = (".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico")
HTML_PATHS = {"/", "/login", "/admin", "/news"}


def has_response_header(handler: Any, keyword: str) -> bool:
    sent = getattr(handler, "_sent_response_header_names", set())
    return str(keyword or "").lower() in sent


def is_https_request(headers: Any) -> bool:
    forwarded_proto = headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
    if forwarded_proto == "https":
        return True
    forwarded = str(headers.get("Forwarded", "") or "").lower()
    if "proto=https" in forwarded:
        return True
    if str(headers.get("X-Forwarded-Ssl", "")).strip().lower() == "on":
        return True
    if str(headers.get("Front-End-Https", "")).strip().lower() == "on":
        return True
    return False


def content_security_policy() -> str:
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "font-src 'self' data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self'; "
        "media-src 'self'; "
        "manifest-src 'self'; "
        "worker-src 'none'; "
        "frame-src 'none'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )


def csp_header_name() -> str:
    explicit_report_only = str(os.getenv("CSP_REPORT_ONLY") or "").strip().lower() in {"1", "true", "yes", "on"}
    explicit_enforce = str(os.getenv("CSP_ENFORCE") or "").strip().lower()
    if explicit_report_only or explicit_enforce in {"0", "false", "no", "off"}:
        return "Content-Security-Policy-Report-Only"
    return "Content-Security-Policy"


def send_security_headers(handler: Any, headers: Any) -> None:
    if not has_response_header(handler, "X-Content-Type-Options"):
        handler.send_header("X-Content-Type-Options", "nosniff")
    if not has_response_header(handler, "Referrer-Policy"):
        handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
    if not has_response_header(handler, "Permissions-Policy"):
        handler.send_header(
            "Permissions-Policy",
            "accelerometer=(), autoplay=(), camera=(), encrypted-media=(), "
            "fullscreen=(self), geolocation=(), gyroscope=(), magnetometer=(), "
            "microphone=(), payment=(), usb=()",
        )
    if not has_response_header(handler, "Cross-Origin-Opener-Policy"):
        handler.send_header("Cross-Origin-Opener-Policy", "same-origin")
    if not has_response_header(handler, "X-Frame-Options"):
        handler.send_header("X-Frame-Options", "DENY")
    csp_name = csp_header_name()
    if not has_response_header(handler, csp_name):
        handler.send_header(csp_name, content_security_policy())
    if is_https_request(headers) and not has_response_header(handler, "Strict-Transport-Security"):
        handler.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


def send_cache_header(handler: Any, path: str) -> None:
    if has_response_header(handler, "Cache-Control"):
        return
    parsed = urlparse(path)
    normalized_path = parsed.path.lower()
    if normalized_path.endswith(".html") or normalized_path in HTML_PATHS:
        handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
    elif normalized_path.endswith(STATIC_ASSET_EXTENSIONS):
        if parsed.query:
            handler.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            handler.send_header("Cache-Control", "public, max-age=3600")
    else:
        handler.send_header("Cache-Control", "no-store")
