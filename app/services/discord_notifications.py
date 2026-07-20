"""Discord notification delivery policy above the transport integrations."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError

try:
    from ..integrations.discord import DiscordIntegration
    from ..integrations.openai import OpenAIIntegration
    from .notifications import EventNotification, NotificationCompositionService
except ImportError:  # pragma: no cover
    from integrations.discord import DiscordIntegration
    from integrations.openai import OpenAIIntegration
    from services.notifications import EventNotification, NotificationCompositionService


ImageAttachment = tuple[bytes, str, str]


@dataclass(frozen=True)
class DiscordNotificationDeliveryConfig:
    enabled: bool
    webhook_url: str
    role_id: str = ""
    allowed_image_mime_types: tuple[str, ...] = ("image/png", "image/jpeg", "image/webp", "image/gif")
    max_image_base64_chars: int = 12_000_000
    max_image_bytes: int = 8_000_000


class DiscordNotificationDeliveryService:
    def __init__(
        self,
        discord: DiscordIntegration,
        openai: OpenAIIntegration,
        config: DiscordNotificationDeliveryConfig,
        *,
        image_prompt_builder: Callable[..., str],
        detect_image_type: Callable[..., tuple[str, str]],
        log_error: Optional[Callable[..., None]] = None,
    ) -> None:
        self.discord = discord
        self.openai = openai
        self.config = config
        self.image_prompt_builder = image_prompt_builder
        self.detect_image_type = detect_image_type
        self.log_error = log_error or (lambda *_args: None)

    def deliver_event(
        self,
        event: EventNotification,
        *,
        generate_image: bool,
        custom_image: Optional[Dict[str, Any]],
    ) -> bool:
        image_prompt = self.image_prompt_builder(**event.image_prompt)
        fallback_prompt = (
            self.image_prompt_builder(**event.image_fallback_prompt)
            if event.image_fallback_prompt
            else None
        )
        return self.notify(
            event.title,
            event.description,
            fields=event.fields,
            color=event.color,
            image_prompt=image_prompt,
            image_reference_url=event.image_reference_url,
            image_fallback_prompt=fallback_prompt,
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def notify(
        self,
        title: str,
        description: str,
        fields: Optional[List[Dict[str, Any]]] = None,
        color: int = 0x0F766E,
        image_prompt: Optional[str] = None,
        image_reference_url: Optional[str] = None,
        image_fallback_prompt: Optional[str] = None,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not self.config.enabled or not self.config.webhook_url:
            return False

        image_attachment = self.custom_image_attachment(custom_image) if custom_image else None
        if not image_attachment and generate_image:
            image_attachment = self.openai.generate_image(
                image_prompt or "",
                reference_image_url=image_reference_url,
                fallback_prompt=image_fallback_prompt,
            )
        image_filename = image_attachment[1] if image_attachment else None
        payload = NotificationCompositionService.notification_payload(
            title,
            description,
            fields=fields,
            color=color,
            role_id=self.config.role_id,
            image_filename=image_filename,
        )

        try:
            if image_attachment:
                file_bytes, filename, mime_type = image_attachment
                try:
                    self.discord.post_webhook_multipart(payload, file_bytes, filename, mime_type)
                    return True
                except (HTTPError, URLError, TimeoutError, OSError) as upload_error:
                    self.log_error("Discord image notification failed; retrying text-only: %s", upload_error)
                    payload["embeds"][0].pop("image", None)
            self.discord.post_webhook_json(payload)
            return True
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            self.log_error("Discord notification failed: %s", error)
            return False

    def custom_image_attachment(self, payload: Any) -> Optional[ImageAttachment]:
        if not isinstance(payload, dict):
            return None
        data_url = str(payload.get("data_url") or "").strip()
        mime_type = str(payload.get("mime_type") or "").strip().lower()
        base64_text = str(payload.get("base64") or "").strip()
        if data_url:
            match = re.match(r"^data:(image/(?:png|jpeg|webp|gif));base64,(.+)$", data_url, re.IGNORECASE | re.DOTALL)
            if not match:
                self.log_error("Discord custom image ignored: invalid data URL.")
                return None
            mime_type = match.group(1).lower()
            base64_text = match.group(2)
        allowed_mime_types = tuple(self.config.allowed_image_mime_types)
        if mime_type not in allowed_mime_types or not base64_text:
            self.log_error("Discord custom image ignored: unsupported image type.")
            return None
        if len(base64_text) > self.config.max_image_base64_chars:
            self.log_error("Discord custom image ignored: encoded payload is too large.")
            return None
        compact_base64 = re.sub(r"\s+", "", base64_text)
        if len(compact_base64) > self.config.max_image_base64_chars:
            self.log_error("Discord custom image ignored: encoded payload is too large.")
            return None
        try:
            file_bytes = base64.b64decode(compact_base64, validate=True)
        except ValueError:
            self.log_error("Discord custom image ignored: invalid base64 data.")
            return None
        if not file_bytes:
            return None
        if len(file_bytes) > self.config.max_image_bytes:
            self.log_error("Discord custom image ignored: file is larger than 8 MB.")
            return None
        try:
            detected_ext, detected_mime = self.detect_image_type(
                file_bytes,
                mime_type,
                allowed_mime_types,
            )
        except ValueError:
            self.log_error("Discord custom image ignored: image bytes do not match an allowed type.")
            return None
        raw_filename = str(payload.get("filename") or "notification-image").strip()
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_filename).strip("._-") or "notification-image"
        safe_stem = re.sub(r"\.(png|jpe?g|webp|gif)$", "", safe_stem, flags=re.IGNORECASE)[:80] or "notification-image"
        return file_bytes, f"{safe_stem}.{detected_ext}", detected_mime
