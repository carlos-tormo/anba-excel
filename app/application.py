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
    from .services.trade_archive import TradeArchiveService
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
    from services.trade_archive import TradeArchiveService
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
    REQUIRED_LEGACY_DEPENDENCIES = (
        "_admin_export_service",
        "_asset_repository",
        "_cartera_service",
        "_coadmin_vote_repository",
        "_depth_chart_repository",
        "_draft_repository",
        "_free_agency_repository",
        "_free_agent_agent_import_service",
        "_free_agent_appeal_service",
        "_gm_minimum_target_service",
        "_gm_office_service",
        "_gm_request_repository",
        "_gm_request_service",
        "_notification_repository",
        "_offer_promise_service",
        "_offseason_exception_service",
        "_outbox_repository",
        "_owner_admin_import_service_instance",
        "_owner_office_repository",
        "_player_catalog_service",
        "_player_identity_repository",
        "_player_repository",
        "_press_article_repository",
        "_season_rollover_repository",
        "_settings_repository",
        "_team_detail_service",
        "_team_repository",
        "_tracker_service",
        "_trade_repository",
        "_trade_archive_repository",
        "_user_repository",
        "_waiver_repository",
        "_workflow_repository",
        "_audit_log_service",
    )

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

    def unresolved_legacy_dependencies(self) -> list[str]:
        return [
            attr
            for attr in self.REQUIRED_LEGACY_DEPENDENCIES
            if getattr(self.db, attr, None) is None
        ]

    def validate_dependencies(self) -> None:
        missing = self.unresolved_legacy_dependencies()
        if missing:
            joined = ",".join(missing)
            raise RuntimeError(f"application_dependencies_missing:{joined}")

    def _dependency(self, attr: str) -> Any:
        value = getattr(self.db, attr, None)
        if value is None:
            raise RuntimeError(f"application_dependency_missing:{attr}")
        return value

    @property
    def teams(self) -> Any:
        return self._dependency("_team_repository")

    @property
    def players(self) -> Any:
        return self._dependency("_player_repository")

    @property
    def assets(self) -> Any:
        return self._dependency("_asset_repository")

    @property
    def settings_repository(self) -> Any:
        return self._dependency("_settings_repository")

    @property
    def users(self) -> Any:
        return self._dependency("_user_repository")

    @property
    def press_articles(self) -> Any:
        return self._dependency("_press_article_repository")

    @property
    def user_notifications(self) -> Any:
        return self._dependency("_notification_repository")

    @property
    def coadmin_votes(self) -> Any:
        return self._dependency("_coadmin_vote_repository")

    @property
    def gm_office(self) -> Any:
        return self._dependency("_gm_office_service")

    @property
    def gm_minimum_targets(self) -> Any:
        return self._dependency("_gm_minimum_target_service")

    @property
    def depth_charts(self) -> Any:
        return self._dependency("_depth_chart_repository")

    @property
    def cartera(self) -> Any:
        return self._dependency("_cartera_service")

    @property
    def offseason_exceptions(self) -> Any:
        return self._dependency("_offseason_exception_service")

    @property
    def free_agent_appeal(self) -> Any:
        return self._dependency("_free_agent_appeal_service")

    @property
    def free_agent_agent_import(self) -> Any:
        return self._dependency("_free_agent_agent_import_service")

    @property
    def tracker(self) -> Any:
        return self._dependency("_tracker_service")

    @property
    def player_catalog(self) -> Any:
        return self._dependency("_player_catalog_service")

    @property
    def team_detail(self) -> Any:
        return self._dependency("_team_detail_service")

    @property
    def league_exports(self) -> Any:
        return self._dependency("_admin_export_service")

    @property
    def owner_imports(self) -> Any:
        return self._dependency("_owner_admin_import_service_instance")

    @property
    def trade_repository(self) -> Any:
        return self._dependency("_trade_repository")

    @property
    def trade_archive_repository(self) -> Any:
        return self._dependency("_trade_archive_repository")

    @cached_property
    def gm_request_queries(self) -> GMRequestQueryService:
        return GMRequestQueryService(
            self._dependency("_gm_request_repository"),
            self._dependency("_draft_repository"),
            self._dependency("_waiver_repository"),
        )

    @cached_property
    def audit_logs(self) -> Any:
        factory = self._dependency("_audit_log_service")
        return factory()

    @cached_property
    def maintenance(self) -> DatabaseMaintenanceService:
        return DatabaseMaintenanceService(self.db)

    @cached_property
    def free_agency(self) -> FreeAgencyService:
        return FreeAgencyService(
            self._dependency("_free_agency_repository"),
            contract_seasons=self.config.contract_seasons,
            cap_hold_source=self.config.cap_hold_source,
            gm_requests=self._dependency("_gm_request_service"),
            offer_promises=self._dependency("_offer_promise_service"),
            players=self._dependency("_player_repository"),
        )

    @cached_property
    def trades(self) -> TradeService:
        return TradeService(
            self._dependency("_trade_repository"),
            workflows=self._dependency("_workflow_repository"),
            outbox=self._dependency("_outbox_repository"),
            archive=self._dependency("_trade_archive_repository"),
        )

    @cached_property
    def trade_archive(self) -> TradeArchiveService:
        return TradeArchiveService(self._dependency("_trade_archive_repository"))

    @cached_property
    def waivers(self) -> WaiverService:
        return WaiverService(self._dependency("_waiver_repository"))

    @cached_property
    def draft(self) -> DraftService:
        return DraftService(self._dependency("_draft_repository"))

    @cached_property
    def season_rollover(self) -> SeasonRolloverService:
        return SeasonRolloverService(
            self._dependency("_season_rollover_repository"),
            contract_min_year=self.config.contract_min_year,
            contract_max_start_year=self.config.contract_max_start_year,
        )

    @cached_property
    def settings(self) -> SettingsService:
        return SettingsService(
            self._dependency("_settings_repository"),
            season_rollover=self.season_rollover,
            contract_seasons=self.config.contract_seasons,
            max_start_year=self.config.contract_max_start_year,
        )

    @cached_property
    def player_admin(self) -> PlayerAdminService:
        return PlayerAdminService(
            players=self._dependency("_player_repository"),
            requests=self._dependency("_gm_request_repository"),
            free_agency=self._dependency("_free_agency_repository"),
            settings=self._dependency("_settings_repository"),
            contract_seasons=self.config.contract_seasons,
            unrestricted_type=self.config.unrestricted_free_agent_type,
        )

    @cached_property
    def team_admin(self) -> TeamAdminService:
        return TeamAdminService(
            self._dependency("_team_repository"),
            self._dependency("_settings_repository"),
            min_year=self.config.cap_forecast_min_year,
            max_year=self.config.cap_forecast_max_year,
        )

    @cached_property
    def asset_admin(self) -> AssetAdminService:
        return AssetAdminService(self._dependency("_asset_repository"))

    @cached_property
    def player_roster(self) -> PlayerRosterService:
        return PlayerRosterService(
            self._dependency("_player_repository"),
            self._dependency("_waiver_repository"),
        )

    @cached_property
    def player_identity(self) -> PlayerIdentityService:
        return PlayerIdentityService(
            self._dependency("_player_identity_repository"),
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
            self._dependency("_user_repository"),
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
            self._dependency("_free_agency_repository"),
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
        return OwnerInterviewCompositionService(
            self.openai.text_response,
            model=self.config.openai_text_model,
        )

    @cached_property
    def owner_office(self) -> OwnerOfficeService:
        return OwnerOfficeService(
            self._dependency("_owner_office_repository"),
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
            self._dependency("_outbox_repository"),
            self._dependency("_player_repository"),
            deliver_notification=self.notifications.deliver_event,
        )
