"""Session, password, and cookie primitives.

The HTTP handler owns request/response orchestration; this module owns the pure
security-sensitive transformations so they can be tested without a handler.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, Optional
from urllib.parse import urlparse


def normalize_same_site(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "strict":
        return "Strict"
    if raw == "none":
        return "None"
    return "Lax"


def pbkdf2_sha256_password_hash(
    password: str,
    *,
    iterations: int = 600_000,
    salt_hex: Optional[str] = None,
) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password_hash(password: str, encoded_hash: str) -> bool:
    parts = str(encoded_hash or "").strip().split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
    except (TypeError, ValueError):
        return False
    if iterations < 100_000:
        return False
    try:
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)


def verify_admin_password(password: str, plaintext_password: str, encoded_hash: str = "") -> bool:
    if str(encoded_hash or "").strip():
        return verify_password_hash(password, encoded_hash)
    return secrets.compare_digest(str(password or ""), str(plaintext_password or ""))


def session_token_digest(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def parse_allowed_origins(value: Any) -> set[str]:
    origins: set[str] = set()
    for raw in str(value or "").split(","):
        origin = raw.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlparse(origin)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            origins.add(f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")
    return origins


def build_cookie(
    name: str,
    value: str,
    *,
    path: str,
    same_site: str,
    max_age: int,
    secure: bool,
    domain: Optional[str] = None,
    priority_high: bool = False,
) -> str:
    parts = [
        f"{name}={value}",
        f"Path={path}",
        "HttpOnly",
        f"SameSite={same_site}",
        f"Max-Age={max_age}",
    ]
    if secure:
        parts.append("Secure")
    if domain:
        parts.append(f"Domain={domain}")
    if priority_high:
        parts.append("Priority=High")
    return "; ".join(parts)

