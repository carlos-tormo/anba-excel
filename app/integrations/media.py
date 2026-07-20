"""Reusable validation for uploaded and persisted image media."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse


DEFAULT_IMAGE_MAX_DIMENSION = 8192
DEFAULT_IMAGE_MAX_PIXELS = 40_000_000


def sanitize_http_image_url(value: Any, limit: int = 1000) -> str:
    raw = str(value or "").strip()[:limit]
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def sanitize_owner_background_url(value: Any, limit: int = 1000) -> str:
    raw = str(value or "").strip()[:limit]
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return ""
    if not re.fullmatch(r"/api/teams/[A-Z0-9]{2,4}/owner-office/background-image", parsed.path or ""):
        return ""
    return raw


def detect_safe_image_type(
    data: bytes,
    declared_mime: str = "",
    allowed_mime_types: Optional[Dict[str, str]] = None,
    *,
    max_dimension: int = DEFAULT_IMAGE_MAX_DIMENSION,
    max_pixels: int = DEFAULT_IMAGE_MAX_PIXELS,
) -> tuple[str, str]:
    allowed = allowed_mime_types or {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if declared and declared not in allowed:
        raise ValueError("unsupported_upload_type")

    detected_mime = ""
    if len(data) >= 3 and data.startswith(b"\xff\xd8\xff"):
        detected_mime = "image/jpeg"
    elif len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_mime = "image/png"
    elif len(data) >= 16 and data[:4] == b"RIFF" and data[8:12] == b"WEBP" and data[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}:
        detected_mime = "image/webp"
    elif len(data) >= 6 and data[:6] in {b"GIF87a", b"GIF89a"}:
        detected_mime = "image/gif"

    if detected_mime not in allowed or (declared and declared != detected_mime):
        raise ValueError("unsupported_upload_type")
    width, height = image_dimensions(data, detected_mime)
    if width <= 0 or height <= 0:
        raise ValueError("invalid_image_dimensions")
    if width > max_dimension or height > max_dimension or width * height > max_pixels:
        raise ValueError("image_dimensions_too_large")
    return allowed[detected_mime], detected_mime


def image_dimensions(data: bytes, mime_type: str) -> tuple[int, int]:
    if mime_type == "image/png":
        if len(data) < 24 or data[12:16] != b"IHDR":
            raise ValueError("invalid_image_dimensions")
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

    if mime_type == "image/gif":
        if len(data) < 10:
            raise ValueError("invalid_image_dimensions")
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")

    if mime_type == "image/jpeg":
        offset = 2
        sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while offset + 3 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            segment_length = int.from_bytes(data[offset : offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(data):
                break
            if marker in sof_markers:
                if segment_length < 7:
                    break
                height = int.from_bytes(data[offset + 3 : offset + 5], "big")
                width = int.from_bytes(data[offset + 5 : offset + 7], "big")
                return width, height
            offset += segment_length
        raise ValueError("invalid_image_dimensions")

    if mime_type == "image/webp":
        chunk_type = data[12:16]
        if chunk_type == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return width, height
        if chunk_type == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            packed = int.from_bytes(data[21:25], "little")
            return 1 + (packed & 0x3FFF), 1 + ((packed >> 14) & 0x3FFF)
        if chunk_type == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
            return width, height
        raise ValueError("invalid_image_dimensions")

    raise ValueError("unsupported_upload_type")
