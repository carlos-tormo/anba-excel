"""Minimal Discord Gateway client for worker processes.

This intentionally avoids league-state concerns. It only maintains the Gateway
connection and emits dispatch payloads to a caller-provided callback.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import socket
import ssl
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse


DispatchCallback = Callable[[str, Dict[str, Any]], None]


DISCORD_INTENT_GUILDS = 1 << 0
DISCORD_INTENT_GUILD_MEMBERS = 1 << 1
DISCORD_INTENT_DIRECT_MESSAGES = 1 << 12
DISCORD_INTENT_DIRECT_MESSAGE_REACTIONS = 1 << 13
WAITING_LIST_GATEWAY_INTENTS = (
    DISCORD_INTENT_GUILDS
    | DISCORD_INTENT_GUILD_MEMBERS
    | DISCORD_INTENT_DIRECT_MESSAGES
    | DISCORD_INTENT_DIRECT_MESSAGE_REACTIONS
)


@dataclass(frozen=True)
class DiscordGatewayConfig:
    token: str
    gateway_url: str = "wss://gateway.discord.gg"
    intents: int = WAITING_LIST_GATEWAY_INTENTS
    large_threshold: int = 50


class _WebSocketConnection:
    def __init__(self, url: str, *, timeout_seconds: int = 30) -> None:
        self.url = url
        self.timeout_seconds = max(5, int(timeout_seconds or 30))
        self.sock: Optional[ssl.SSLSocket] = None

    def connect(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme != "wss":
            raise ValueError("discord_gateway_requires_wss")
        host = parsed.hostname or ""
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        raw = socket.create_connection((host, port), timeout=self.timeout_seconds)
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "User-Agent: anba-excel/1.0\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if len(response) > 65536:
                break
        if not response.startswith(b"HTTP/1.1 101") and not response.startswith(b"HTTP/1.0 101"):
            sock.close()
            raise ConnectionError("discord_gateway_upgrade_failed")
        self.sock = sock

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _read_exact(self, length: int) -> bytes:
        if not self.sock:
            raise ConnectionError("discord_gateway_not_connected")
        chunks = []
        remaining = int(length)
        while remaining > 0:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise ConnectionError("discord_gateway_closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def send_json(self, payload: Dict[str, Any]) -> None:
        self._send_frame(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"), opcode=0x1)

    def send_pong(self, payload: bytes = b"") -> None:
        self._send_frame(payload, opcode=0xA)

    def _send_frame(self, payload: bytes, *, opcode: int) -> None:
        if not self.sock:
            raise ConnectionError("discord_gateway_not_connected")
        length = len(payload)
        header = bytearray([0x80 | (opcode & 0x0F)])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def receive_json(self) -> Dict[str, Any]:
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise ConnectionError("discord_gateway_close_frame")
            if opcode == 0x9:
                self.send_pong(payload)
                continue
            if opcode not in {0x1, 0x2}:
                continue
            return json.loads(payload.decode("utf-8"))


class DiscordGatewayClient:
    def __init__(
        self,
        config: DiscordGatewayConfig,
        *,
        on_dispatch: DispatchCallback,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if not str(config.token or "").strip():
            raise ValueError("discord_gateway_token_required")
        self.config = config
        self.on_dispatch = on_dispatch
        self.logger = logger or logging.getLogger(__name__)
        self.sequence: Optional[int] = None
        self._ws: Optional[_WebSocketConnection] = None
        self._heartbeat_interval_seconds = 30.0
        self._stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    @staticmethod
    def gateway_url(base_url: str) -> str:
        parsed = urlparse(str(base_url or "wss://gateway.discord.gg").strip())
        query = dict(parse_qsl(parsed.query))
        query.setdefault("v", "10")
        query.setdefault("encoding", "json")
        rebuilt = parsed._replace(query=urlencode(query))
        return rebuilt.geturl()

    def stop(self) -> None:
        self._stop.set()
        if self._ws:
            self._ws.close()

    def run_forever(self, *, reconnect_delay_seconds: int = 5) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as err:  # noqa: BLE001 - worker reconnect boundary.
                if self._stop.is_set():
                    break
                self.logger.error("Discord Gateway connection failed: %s", err)
                time.sleep(max(1, int(reconnect_delay_seconds or 5)))

    def run_once(self) -> None:
        self.sequence = None
        self._ws = _WebSocketConnection(self.gateway_url(self.config.gateway_url))
        self._ws.connect()
        try:
            while not self._stop.is_set():
                message = self._ws.receive_json()
                self._handle_message(message)
        finally:
            if self._ws:
                self._ws.close()

    def _handle_message(self, message: Dict[str, Any]) -> None:
        op = message.get("op")
        if message.get("s") is not None:
            self.sequence = int(message["s"])
        if op == 10:
            heartbeat_ms = int((message.get("d") or {}).get("heartbeat_interval") or 30000)
            self._heartbeat_interval_seconds = max(1.0, heartbeat_ms / 1000.0)
            self._start_heartbeat()
            self._identify()
            return
        if op == 0:
            event_type = str(message.get("t") or "")
            payload = message.get("d") if isinstance(message.get("d"), dict) else {}
            if event_type:
                self.on_dispatch(event_type, payload)
            return
        if op == 1:
            self._send_heartbeat()
            return
        if op in {7, 9}:
            raise ConnectionError(f"discord_gateway_reconnect:{op}")

    def _identify(self) -> None:
        if not self._ws:
            raise ConnectionError("discord_gateway_not_connected")
        self._ws.send_json(
            {
                "op": 2,
                "d": {
                    "token": self.config.token,
                    "intents": int(self.config.intents),
                    "properties": {
                        "os": "linux",
                        "browser": "anba-excel",
                        "device": "anba-excel",
                    },
                    "large_threshold": int(self.config.large_threshold),
                },
            }
        )

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_interval_seconds):
            try:
                self._send_heartbeat()
            except Exception as err:  # noqa: BLE001 - heartbeat failure is handled by recv reconnect.
                self.logger.warning("Discord Gateway heartbeat failed: %s", err)
                return

    def _send_heartbeat(self) -> None:
        if self._ws:
            self._ws.send_json({"op": 1, "d": self.sequence})
