"""League-event and press-publication notification orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

try:
    from .discord_notifications import DiscordNotificationDeliveryService
    from .notifications import (
        EventNotification,
        NotificationCompositionService,
        free_agent_signed_notification,
    )
except ImportError:  # pragma: no cover - supports direct app imports.
    from services.discord_notifications import DiscordNotificationDeliveryService
    from services.notifications import (
        EventNotification,
        NotificationCompositionService,
        free_agent_signed_notification,
    )


class LeagueNotificationDeliveryService:
    """Composes league events and delegates transport to Discord delivery."""

    def __init__(self, delivery: DiscordNotificationDeliveryService, draft: Any) -> None:
        self._delivery = delivery
        self._draft = draft

    def deliver_event(
        self,
        event: EventNotification,
        *,
        generate_image: bool,
        custom_image: Optional[Dict[str, Any]],
    ) -> bool:
        return self._delivery.deliver_event(
            event,
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def player_cut(
        self,
        result: Dict[str, Any],
        *,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self.deliver_event(
            NotificationCompositionService.player_cut(result),
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def free_agent_signed(
        self,
        player: Dict[str, Any],
        *,
        offer_payload: Optional[Dict[str, Any]] = None,
        offer_type: Optional[str] = None,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self.deliver_event(
            free_agent_signed_notification(
                player,
                offer_payload=offer_payload,
                offer_type=offer_type,
            ),
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def draft_pick_selection(
        self,
        request: Dict[str, Any],
        *,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self.deliver_event(
            NotificationCompositionService.draft_pick_selection(
                request, self._draft.current_year()
            ),
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def contract_option_action(
        self,
        player: Dict[str, Any],
        season: int,
        option_value: str,
        action: str,
        *,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self.deliver_event(
            NotificationCompositionService.contract_option_action(
                player, season, option_value, action
            ),
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def bird_rights_renounced(
        self,
        player: Dict[str, Any],
        season: int,
        rights_value: str,
        *,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self.deliver_event(
            NotificationCompositionService.bird_rights_renounced(
                player, season, rights_value
            ),
            generate_image=generate_image,
            custom_image=custom_image,
        )


@dataclass(frozen=True)
class PressPublicationConfig:
    enabled: bool
    bot_token: str
    channel_id: str


class PressPublicationService:
    """Persists a press article and publishes its image to Discord."""

    def __init__(
        self,
        articles: Any,
        discord: Any,
        delivery: DiscordNotificationDeliveryService,
        config: PressPublicationConfig,
    ) -> None:
        self._articles = articles
        self._discord = discord
        self._delivery = delivery
        self._config = config

    def publish(
        self,
        text: str,
        article_url_for_id: Callable[[int], str],
        custom_image: Any,
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        image_attachment = self._delivery.custom_image_attachment(custom_image)
        if not image_attachment:
            raise ValueError("article_image_required")
        if not self._config.enabled:
            raise RuntimeError("discord_notifications_disabled")
        if not self._config.bot_token:
            raise RuntimeError("discord_bot_token_required")
        if not self._config.channel_id:
            raise RuntimeError("discord_press_channel_required")

        file_bytes, filename, mime_type = image_attachment
        article = self._articles.create(text, file_bytes, mime_type, session)
        article_id = int(article.get("id") or 0)
        article_url = article_url_for_id(article_id)
        payload = NotificationCompositionService.press_article_payload(
            text, article_url, filename
        )
        message = self._discord.post_bot_multipart(
            f"/channels/{self._config.channel_id}/messages",
            payload,
            file_bytes,
            filename,
            mime_type,
        )
        message_id = str((message or {}).get("id") or "")
        self._articles.update_discord(
            article_id, self._config.channel_id, message_id
        )
        return {
            "channel_id": self._config.channel_id,
            "message_id": message_id,
            "article_url": str(article_url or "").strip(),
        }
