"""Per-request application dependency container.

HTTP handlers own transport state. This container owns construction and reuse of
application services and integrations consumed by route functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any, Callable, Dict

try:
    from .integrations.discord import DiscordConfig, DiscordIntegration
    from .integrations.google_oauth import GoogleOAuthConfig, GoogleOAuthIntegration
    from .integrations.media import detect_safe_image_type
    from .integrations.openai import OpenAIConfig, OpenAIIntegration
    from .db.maintenance import DatabaseMaintenanceService
    from .services.assets import AssetAdminService
    from .services.authentication import GoogleOAuthService
    from .services.discord_notifications import (
        DiscordNotificationDeliveryConfig,
        DiscordNotificationDeliveryService,
    )
    from .services.draft import DraftService
    from .services.free_agency import FreeAgencyService
    from .services.free_agent_offer_notifications import (
        FreeAgentOfferDiscordConfig,
        FreeAgentOfferNotificationService,
    )
    from .services.news_image_prompts import NewsImagePromptService
    from .services.gm_request_queries import GMRequestQueryService
    from .services.notification_delivery import (
        LeagueNotificationDeliveryService,
        PressPublicationConfig,
        PressPublicationService,
    )
    from .services.outbox_delivery import OutboxDeliveryService
    from .services.owner_interviews import OwnerInterviewCompositionService
    from .services.owner_office import OwnerOfficeService
    from .services.player_admin import PlayerAdminService
    from .services.player_identity import PlayerIdentityService
    from .services.player_roster import PlayerRosterService
    from .services.season_rollover import SeasonRolloverService
    from .services.settings import SettingsService
    from .services.team_admin import TeamAdminService
    from .services.trades import TradeService
    from .services.waivers import WaiverService
except ImportError:  # pragma: no cover - direct script support
    from integrations.discord import DiscordConfig, DiscordIntegration
    from integrations.google_oauth import GoogleOAuthConfig, GoogleOAuthIntegration
    from integrations.media import detect_safe_image_type
    from integrations.openai import OpenAIConfig, OpenAIIntegration
    from db.maintenance import DatabaseMaintenanceService
    from services.assets import AssetAdminService
    from services.authentication import GoogleOAuthService
    from services.discord_notifications import (
        DiscordNotificationDeliveryConfig,
        DiscordNotificationDeliveryService,
    )
    from services.draft import DraftService
    from services.free_agency import FreeAgencyService
    from services.free_agent_offer_notifications import (
        FreeAgentOfferDiscordConfig,
        FreeAgentOfferNotificationService,
    )
    from services.news_image_prompts import NewsImagePromptService
    from services.gm_request_queries import GMRequestQueryService
    from services.notification_delivery import (
        LeagueNotificationDeliveryService,
        PressPublicationConfig,
        PressPublicationService,
    )
    from services.outbox_delivery import OutboxDeliveryService
    from services.owner_interviews import OwnerInterviewCompositionService
    from services.owner_office import OwnerOfficeService
    from services.player_admin import PlayerAdminService
    from services.player_identity import PlayerIdentityService
    from services.player_roster import PlayerRosterService
    from services.season_rollover import SeasonRolloverService
    from services.settings import SettingsService
    from services.team_admin import TeamAdminService
    from services.trades import TradeService
    from services.waivers import WaiverService


@dataclass(frozen=True)
class ApplicationConfig:
    contract_seasons: tuple[int, ...]
    contract_min_year: int
    contract_max_start_year: int
    cap_forecast_min_year: int
    cap_forecast_max_year: int
    unrestricted_free_agent_type: str
    cap_hold_source: str
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    admin_emails: frozenset[str]
    gm_accounts: Dict[str, list[str]]
    discord_webhook_url: str = ""
    discord_bot_token: str = ""
    discord_api_base_url: str = "https://discord.com/api/v10"
    discord_timeout_seconds: int = 5
    discord_press_channel_id: str = ""
    discord_free_agent_offers_webhook_url: str = ""
    discord_free_agent_offers_forum_tag_ids: tuple[str, ...] = ()
    discord_free_agent_offers_role_id: str = ""
    discord_role_id: str = ""
    discord_notifications_enabled: bool = False
    discord_image_notifications_enabled: bool = False
    discord_allowed_image_mime_types: tuple[str, ...] = (
        "image/png", "image/jpeg", "image/webp", "image/gif"
    )
    discord_max_image_base64_chars: int = 12_000_000
    discord_max_image_bytes: int = 8_000_000
    openai_api_key: str = ""
    openai_text_model: str = "gpt-4.1-mini"
    openai_text_timeout_seconds: int = 45
    openai_image_model: str = "gpt-image-2"
    openai_image_size: str = "1536x1024"
    openai_image_quality: str = "high"
    openai_image_format: str = "jpeg"
    openai_image_timeout_seconds: int = 120
    openai_reference_image_timeout_seconds: int = 20
    openai_reference_image_max_bytes: int = 6_000_000
    owner_forecast_window: int = 6
    owner_objective_options: tuple[str, ...] = ()


class ApplicationContainer:
    def __init__(
        self,
        db: Any,
        config: ApplicationConfig,
        *,
        opener: Callable[..., Any],
        now: Callable[[], str],
        log_error: Callable[..., None],
    ) -> None:
        self.db = db
        self.config = config
        self._opener = opener
        self._now = now
        self._log_error = log_error

    @property
    def teams(self) -> Any:
        return getattr(self.db, "_team_repository", None) or self.db

    @property
    def players(self) -> Any:
        return getattr(self.db, "_player_repository", None) or self.db

    @property
    def assets(self) -> Any:
        return getattr(self.db, "_asset_repository", None) or self.db

    @property
    def settings_repository(self) -> Any:
        return getattr(self.db, "_settings_repository", None) or self.db

    @property
    def users(self) -> Any:
        return getattr(self.db, "_user_repository", None) or self.db

    @property
    def press_articles(self) -> Any:
        return getattr(self.db, "_press_article_repository", None) or self.db

    @property
    def user_notifications(self) -> Any:
        return getattr(self.db, "_notification_repository", None) or self.db

    @property
    def coadmin_votes(self) -> Any:
        return getattr(self.db, "_coadmin_vote_repository", None) or self.db

    @property
    def gm_office(self) -> Any:
        return getattr(self.db, "_gm_office_service", None) or self.db

    @property
    def gm_minimum_targets(self) -> Any:
        return getattr(self.db, "_gm_minimum_target_service", None) or self.db

    @property
    def depth_charts(self) -> Any:
        return getattr(self.db, "_depth_chart_repository", None) or self.db

    @property
    def cartera(self) -> Any:
        return getattr(self.db, "_cartera_service", None) or self.db

    @property
    def offseason_exceptions(self) -> Any:
        return getattr(self.db, "_offseason_exception_service", None) or self.db

    @property
    def free_agent_appeal(self) -> Any:
        return getattr(self.db, "_free_agent_appeal_service", None) or self.db

    @property
    def free_agent_agent_import(self) -> Any:
        return getattr(self.db, "_free_agent_agent_import_service", None) or self.db

    @property
    def tracker(self) -> Any:
        return getattr(self.db, "_tracker_service", None) or self.db

    @property
    def player_catalog(self) -> Any:
        return getattr(self.db, "_player_catalog_service", None) or self.db

    @property
    def team_detail(self) -> Any:
        return getattr(self.db, "_team_detail_service", None) or self.db

    @property
    def league_exports(self) -> Any:
        return getattr(self.db, "_admin_export_service", None) or self.db

    @property
    def owner_imports(self) -> Any:
        return getattr(self.db, "_owner_admin_import_service_instance", None) or self.db

    @property
    def trade_repository(self) -> Any:
        return getattr(self.db, "_trade_repository", None) or self.db

    @cached_property
    def gm_request_queries(self) -> GMRequestQueryService:
        return GMRequestQueryService(
            getattr(self.db, "_gm_request_repository", None) or self.db,
            getattr(self.db, "_draft_repository", None) or self.db,
            getattr(self.db, "_waiver_repository", None) or self.db,
        )

    @cached_property
    def audit_logs(self) -> Any:
        factory = getattr(self.db, "_audit_log_service", None)
        return factory() if factory else self.db

    @cached_property
    def maintenance(self) -> DatabaseMaintenanceService:
        return DatabaseMaintenanceService(self.db)

    @cached_property
    def free_agency(self) -> FreeAgencyService:
        return FreeAgencyService(
            getattr(self.db, "_free_agency_repository", None) or self.db,
            contract_seasons=self.config.contract_seasons,
            cap_hold_source=self.config.cap_hold_source,
            gm_requests=getattr(self.db, "_gm_request_service", None),
            offer_promises=getattr(self.db, "_offer_promise_service", None),
            players=getattr(self.db, "_player_repository", None),
        )

    @cached_property
    def trades(self) -> TradeService:
        return TradeService(
            getattr(self.db, "_trade_repository", None) or self.db,
            workflows=getattr(self.db, "_workflow_repository", None),
            outbox=getattr(self.db, "_outbox_repository", None),
        )

    @cached_property
    def waivers(self) -> WaiverService:
        return WaiverService(self.db)

    @cached_property
    def draft(self) -> DraftService:
        return DraftService(self.db)

    @cached_property
    def season_rollover(self) -> SeasonRolloverService:
        return SeasonRolloverService(
            self.db,
            contract_min_year=self.config.contract_min_year,
            contract_max_start_year=self.config.contract_max_start_year,
        )

    @cached_property
    def settings(self) -> SettingsService:
        return SettingsService(
            getattr(self.db, "_settings_repository", None) or self.db,
            season_rollover=self.season_rollover,
            contract_seasons=self.config.contract_seasons,
            max_start_year=self.config.contract_max_start_year,
        )

    @cached_property
    def player_admin(self) -> PlayerAdminService:
        return PlayerAdminService(
            players=getattr(self.db, "_player_repository", None) or self.db,
            requests=getattr(self.db, "_gm_request_repository", None) or self.db,
            free_agency=getattr(self.db, "_free_agency_repository", None) or self.db,
            settings=getattr(self.db, "_settings_repository", None) or self.db,
            contract_seasons=self.config.contract_seasons,
            unrestricted_type=self.config.unrestricted_free_agent_type,
        )

    @cached_property
    def team_admin(self) -> TeamAdminService:
        return TeamAdminService(
            getattr(self.db, "_team_repository", None) or self.db,
            getattr(self.db, "_settings_repository", None) or self.db,
            min_year=self.config.cap_forecast_min_year,
            max_year=self.config.cap_forecast_max_year,
        )

    @cached_property
    def asset_admin(self) -> AssetAdminService:
        return AssetAdminService(getattr(self.db, "_asset_repository", None) or self.db)

    @cached_property
    def player_roster(self) -> PlayerRosterService:
        return PlayerRosterService(
            getattr(self.db, "_player_repository", None) or self.db,
            getattr(self.db, "_waiver_repository", None) or self.db,
        )

    @cached_property
    def player_identity(self) -> PlayerIdentityService:
        return PlayerIdentityService(
            self.db,
            contract_seasons=self.config.contract_seasons,
        )

    @cached_property
    def google_client(self) -> GoogleOAuthIntegration:
        return GoogleOAuthIntegration(
            GoogleOAuthConfig(
                client_id=self.config.google_client_id,
                client_secret=self.config.google_client_secret,
                redirect_uri=self.config.google_redirect_uri,
            ),
            opener=self._opener,
        )

    @property
    def google_enabled(self) -> bool:
        return self.google_client.enabled()

    @cached_property
    def google_oauth(self) -> GoogleOAuthService:
        return GoogleOAuthService(
            self.google_client,
            getattr(self.db, "_user_repository", None) or self.db,
            admin_emails=set(self.config.admin_emails),
            gm_accounts=self.config.gm_accounts,
            now=self._now,
        )

    @cached_property
    def discord(self) -> DiscordIntegration:
        return DiscordIntegration(
            DiscordConfig(
                webhook_url=self.config.discord_webhook_url,
                bot_token=self.config.discord_bot_token,
                api_base_url=self.config.discord_api_base_url,
                timeout_seconds=self.config.discord_timeout_seconds,
            ),
            opener=self._opener,
        )

    @cached_property
    def openai(self) -> OpenAIIntegration:
        return OpenAIIntegration(
            OpenAIConfig(
                api_key=self.config.openai_api_key,
                text_model=self.config.openai_text_model,
                text_timeout_seconds=self.config.openai_text_timeout_seconds,
                image_model=self.config.openai_image_model,
                image_size=self.config.openai_image_size,
                image_quality=self.config.openai_image_quality,
                image_format=self.config.openai_image_format,
                image_timeout_seconds=self.config.openai_image_timeout_seconds,
                reference_image_timeout_seconds=self.config.openai_reference_image_timeout_seconds,
                reference_image_max_bytes=self.config.openai_reference_image_max_bytes,
                image_generation_enabled=self.config.discord_image_notifications_enabled,
            ),
            opener=self._opener,
            log_error=self._log_error,
        )

    @cached_property
    def image_prompts(self) -> NewsImagePromptService:
        return NewsImagePromptService()

    @cached_property
    def discord_notifications(self) -> DiscordNotificationDeliveryService:
        return DiscordNotificationDeliveryService(
            self.discord,
            self.openai,
            DiscordNotificationDeliveryConfig(
                enabled=self.config.discord_notifications_enabled,
                webhook_url=self.config.discord_webhook_url,
                role_id=self.config.discord_role_id,
                allowed_image_mime_types=self.config.discord_allowed_image_mime_types,
                max_image_base64_chars=self.config.discord_max_image_base64_chars,
                max_image_bytes=self.config.discord_max_image_bytes,
            ),
            image_prompt_builder=self.image_prompts.build,
            detect_image_type=detect_safe_image_type,
            log_error=self._log_error,
        )

    @cached_property
    def notifications(self) -> LeagueNotificationDeliveryService:
        return LeagueNotificationDeliveryService(
            self.discord_notifications,
            self.draft,
        )

    @cached_property
    def free_agent_offer_notifications(self) -> FreeAgentOfferNotificationService:
        return FreeAgentOfferNotificationService(
            self.discord,
            getattr(self.db, "_free_agency_repository", None) or self.db,
            self.settings_repository,
            self.free_agency,
            FreeAgentOfferDiscordConfig(
                enabled=self.config.discord_notifications_enabled,
                webhook_url=(
                    self.config.discord_free_agent_offers_webhook_url
                    or self.config.discord_webhook_url
                ),
                forum_tag_ids=self.config.discord_free_agent_offers_forum_tag_ids,
                offer_role_id=self.config.discord_free_agent_offers_role_id,
                bot_token=self.config.discord_bot_token,
            ),
            log_error=self._log_error,
        )

    @cached_property
    def press_publication(self) -> PressPublicationService:
        return PressPublicationService(
            self.press_articles,
            self.discord,
            self.discord_notifications,
            PressPublicationConfig(
                enabled=self.config.discord_notifications_enabled,
                bot_token=self.config.discord_bot_token,
                channel_id=self.config.discord_press_channel_id,
            ),
        )

    @cached_property
    def owner_interviews(self) -> OwnerInterviewCompositionService:
        return OwnerInterviewCompositionService(self.openai.text_response)

    @cached_property
    def owner_office(self) -> OwnerOfficeService:
        return OwnerOfficeService(
            getattr(self.db, "_owner_office_repository", None) or self.db,
            now=self._now,
            min_year=self.config.cap_forecast_min_year,
            max_year=self.config.cap_forecast_max_year,
            forecast_window=self.config.owner_forecast_window,
            objective_options=list(self.config.owner_objective_options),
            interview_composer=self.owner_interviews,
        )

    @cached_property
    def outbox_delivery(self) -> OutboxDeliveryService:
        return OutboxDeliveryService(
            getattr(self.db, "_outbox_repository", None) or self.db,
            getattr(self.db, "_player_repository", None) or self.db,
            deliver_notification=self.notifications.deliver_event,
        )
