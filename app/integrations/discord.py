"""Discord HTTP transport.

League-specific notification wording and delivery policy deliberately live outside
this module.  This adapter only knows how to call Discord's webhook and bot APIs.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from ..observability.operations import record_external_call
except ImportError:  # pragma: no cover
    from observability.operations import record_external_call


UrlOpener = Callable[..., Any]


def truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def redact_secrets(value: Any, *, extra_secrets: Optional[list[str]] = None) -> str:
    """Return a log-safe error string without webhook URLs or bearer/bot tokens."""
    text = str(value or "")
    for secret in extra_secrets or []:
        secret_text = str(secret or "")
        if len(secret_text) >= 6:
            text = text.replace(secret_text, "[REDACTED]")
    text = re.sub(r"\b(Bot|Bearer)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]", text)
    text = re.sub(
        r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/[^\s\"'<>]+",
        "https://discord.com/api/webhooks/[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(access_token|refresh_token|client_secret|bot_token|webhook_url)\b([\"'\s:=]+)([^&\s\"',}]+)",
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    return text


def neutralize_discord_mentions(value: Any) -> str:
    """Escape user-provided mention syntax while preserving readable text."""
    text = str(value or "")
    text = re.sub(r"@(?=everyone\b|here\b|[!&]?\d)", "@\u200b", text, flags=re.IGNORECASE)
    text = text.replace("<@", "<@\u200b")
    return text


def http_error_excerpt(err: HTTPError, limit: int = 1200) -> str:
    try:
        body = err.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    if len(body) > limit:
        body = f"{body[:limit].rstrip()}..."
    return redact_secrets(f"{err} {body}".strip())


@dataclass(frozen=True)
class DiscordConfig:
    webhook_url: str = ""
    bot_token: str = ""
    api_base_url: str = "https://discord.com/api/v10"
    timeout_seconds: int = 5


class DiscordIntegration:
    def __init__(self, config: DiscordConfig, *, opener: UrlOpener = urlopen):
        self.config = config
        self._open = opener

    @staticmethod
    def webhook_url(webhook_url: str, *, thread_id: Optional[str] = None, wait: bool = False) -> str:
        query: Dict[str, str] = {}
        if thread_id:
            query["thread_id"] = re.sub(r"\D+", "", str(thread_id))
        if wait:
            query["wait"] = "true"
        if not query:
            return webhook_url
        separator = "&" if "?" in webhook_url else "?"
        return f"{webhook_url}{separator}{urlencode(query)}"

    def post_webhook_json(
        self,
        payload: Dict[str, Any],
        *,
        webhook_url: Optional[str] = None,
        thread_name: Optional[str] = None,
        thread_id: Optional[str] = None,
        wait: bool = False,
    ) -> Optional[Dict[str, Any]]:
        body_payload = self._payload_with_safe_mentions(payload)
        if thread_name and not thread_id:
            body_payload["thread_name"] = truncate_text(thread_name, 100)
        request = Request(
            self.webhook_url(webhook_url or self.config.webhook_url, thread_id=thread_id, wait=wait),
            data=json.dumps(body_payload, ensure_ascii=True).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "anba-excel/1.0"},
            method="POST",
        )
        started = time.perf_counter()
        ok = False
        try:
            with self._open(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read()
            ok = True
        finally:
            record_external_call("discord", "webhook_json", time.perf_counter() - started, ok=ok)
        return self._json_object(raw) if wait and raw else None

    def post_bot_json(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        *,
        method: str = "POST",
    ) -> Optional[Dict[str, Any]]:
        self._require_bot_token()
        endpoint_path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        body_payload = self._payload_with_safe_mentions(payload) if endpoint_path.endswith("/messages") else dict(payload)
        request = Request(
            f"{self.config.api_base_url.rstrip('/')}{endpoint_path}",
            data=json.dumps(body_payload, ensure_ascii=True).encode("utf-8"),
            headers={
                "Authorization": f"Bot {self.config.bot_token}",
                "Content-Type": "application/json",
                "User-Agent": "anba-excel/1.0",
            },
            method=method,
        )
        started = time.perf_counter()
        ok = False
        try:
            with self._open(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read()
            ok = True
        finally:
            record_external_call("discord", "bot_json", time.perf_counter() - started, ok=ok)
        return self._json_object(raw)

    def send_dm(self, user_id: str, payload: Dict[str, Any]) -> bool:
        clean_user_id = re.sub(r"\D+", "", str(user_id or ""))
        if not clean_user_id:
            return False
        channel = self.post_bot_json("/users/@me/channels", {"recipient_id": clean_user_id})
        channel_id = str((channel or {}).get("id") or "").strip()
        if not channel_id:
            return False
        self.post_bot_json(f"/channels/{channel_id}/messages", payload)
        return True

    def post_webhook_multipart(
        self,
        payload: Dict[str, Any],
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> None:
        body, boundary = self._multipart_body(
            self._payload_with_safe_mentions(payload),
            file_bytes,
            filename,
            mime_type,
            "anba-discord",
        )
        request = Request(
            self.config.webhook_url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "anba-excel/1.0",
            },
            method="POST",
        )
        started = time.perf_counter()
        ok = False
        try:
            with self._open(request, timeout=max(self.config.timeout_seconds, 15)) as response:
                response.read()
            ok = True
        finally:
            record_external_call("discord", "webhook_multipart", time.perf_counter() - started, ok=ok)

    def post_bot_multipart(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> Optional[Dict[str, Any]]:
        self._require_bot_token()
        endpoint_path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        body, boundary = self._multipart_body(
            self._payload_with_safe_mentions(payload),
            file_bytes,
            filename,
            mime_type,
            "anba-discord-bot",
        )
        request = Request(
            f"{self.config.api_base_url.rstrip('/')}{endpoint_path}",
            data=body,
            headers={
                "Authorization": f"Bot {self.config.bot_token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "anba-excel/1.0",
            },
            method="POST",
        )
        started = time.perf_counter()
        ok = False
        try:
            with self._open(request, timeout=max(self.config.timeout_seconds, 15)) as response:
                raw = response.read()
            ok = True
        finally:
            record_external_call("discord", "bot_multipart", time.perf_counter() - started, ok=ok)
        return self._json_object(raw)

    def _require_bot_token(self) -> None:
        if not self.config.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN is not configured")

    @staticmethod
    def _payload_with_safe_mentions(payload: Dict[str, Any]) -> Dict[str, Any]:
        body_payload = dict(payload or {})
        if "allowed_mentions" not in body_payload:
            body_payload["allowed_mentions"] = {"parse": []}
        return body_payload

    @staticmethod
    def _json_object(raw: bytes) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _multipart_body(
        payload: Dict[str, Any],
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        boundary_prefix: str,
    ) -> tuple[bytes, str]:
        boundary = f"----{boundary_prefix}-{secrets.token_hex(16)}"
        payload_json = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        chunks = [
            f"--{boundary}\r\n".encode("utf-8"),
            b'Content-Disposition: form-data; name="payload_json"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            payload_json,
            b"\r\n",
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'.encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
        return b"".join(chunks), boundary
