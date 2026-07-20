#!/usr/bin/env python3
import argparse
import copy
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen
from functools import partial

try:
    from .application import ApplicationConfig, ApplicationContainer
    from .auth.csrf import csrf_token_ok, same_origin_request_ok
    from .auth.policies import (
        AUTH_POLICIES,
        AuthorizationError,
        authorization_actor_from_session,
        authorize_action,
        normalize_team_code,
        normalize_team_codes,
        parse_gm_account_map,
        serialize_team_codes,
    )
    from .auth.sessions import (
        build_cookie,
        normalize_same_site,
        parse_allowed_origins,
        pbkdf2_sha256_password_hash,
        session_token_digest,
        verify_admin_password,
        verify_password_hash,
    )
    from .db.repositories import sessions as session_repository
    from .db.repositories.assets import AssetRepository
    from .db.repositories.admin_imports import OwnerAdminImportRepository
    from .db.repositories.cartera import CarteraRepository
    from .db.repositories.depth_charts import DepthChartRepository
    from .db.repositories.draft import DraftReadOperations, DraftRepository
    from .db.repositories.free_agency import FreeAgencyOperations, FreeAgencyRepository
    from .db.repositories.free_agent_appeal import FreeAgentAppealRepository
    from .db.repositories.free_agent_agents import FreeAgentAgentRepository
    from .db.repositories.gm_workflows import (
        CoadminVoteRepository,
        GMRequestOperations,
        GMRequestRepository,
    )
    from .db.repositories.gm_minimum_targets import GMMinimumTargetRepository
    from .db.repositories.gm_office import GMOfficeRepository
    from .db.repositories.notifications import NotificationRepository
    from .db.repositories.outbox import OutboxRepository
    from .db.repositories.offer_promises import OfferPromiseRepository
    from .db.repositories.offseason_exceptions import OffseasonExceptionRepository
    from .db.repositories.owner_office import OwnerOfficeRepository
    from .db.repositories.player_identity import PlayerIdentityRepository
    from .db.repositories.player_lifecycle import PlayerLifecycleRepository
    from .db.repositories.players import PlayerRepository
    from .db.repositories.press_articles import PressArticleRepository
    from .db.repositories.season_rollover import SeasonRolloverOperations, SeasonRolloverRepository
    from .db.repositories.settings import SettingsRepository
    from .db.repositories.users import UserRepository
    from .db.repositories.teams import TeamRepository
    from .db.repositories.team_detail import TeamDetailRepository
    from .db.repositories.workflows import WorkflowRepository
    from .db.repositories.trades import TradeOperations, TradeRepository
    from .db.repositories.waivers import WaiverOperations, WaiverRepository
    from .domain_rules import (
        CAP_FORECAST_MAX_YEAR,
        CAP_FORECAST_MIN_YEAR,
        CAP_FORECAST_WINDOW,
        OPEN_ROSTER_SPOT_MINIMUM,
        ROSTER_STANDARD_MAX_DEFAULT,
        ROSTER_STANDARD_MIN_DEFAULT,
        ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT,
        ROSTER_TWO_WAY_MAX_DEFAULT,
        ROSTER_TWO_WAY_MIN_DEFAULT,
        TRADE_MACHINE_MAX_TEAMS,
        TRADE_MACHINE_MIN_TEAMS,
        TRADE_MATCH_CUSHION,
        TRADE_MATCH_EXPANDED_BUFFER_FALLBACK,
        TRADE_MATCH_EXPANDED_BUFFER_RATIO,
        TRADE_MATCH_HIGH_BAND,
        TRADE_MATCH_LOW_BAND,
        TRADE_PICK_ACTION_SEND,
        TRADE_PICK_ACTION_SWAP,
        TRADE_ROOM_TPE_BUFFER,
        TWO_WAY_MINIMUM_BASE_SALARY,
        apron_yos_adjustment,
        cap_hold_bird_code_from_years,
        cap_hold_amount,
        counts_open_roster_minimum,
        format_trade_money,
        has_standard_cap_hold_marker,
        increment_bird_years_value,
        is_exhibit10_player,
        is_two_way_player,
        luxury_tax_amount,
        maximum_salary_for_experience,
        minimum_salary_2_yos_for_cap,
        minimum_contract_team_salary,
        minimum_salary_for_season,
        normalize_bird_years,
        normalize_experience_years,
        normalize_move_phase,
        normalize_trade_bucket,
        open_roster_spot_cap_hold,
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
        public_settings_payload,
        roster_contract_counts,
        roster_contract_slot_type,
        row_salary_num,
        salary_floor_for_season,
        apply_salary_floor,
        scaled_minimum_salary,
        season_label,
        settings_int,
    )
    from .domain.exceptions import (
        GENERATED_OFFSEASON_EXCEPTION_KEYS,
        OFFSEASON_EXCEPTION_DEFINITIONS,
        normalize_apron_hard_cap,
        offseason_exception_amounts,
        offseason_exception_item,
    )
    from .domain.cap import calculate_team_cap_summary
    from .domain.contracts import contract_option_rejection_clear_payload
    from .domain.normalization import (
        dead_contract_excluded_from_cap, dead_contract_excluded_from_gasto,
        dead_contract_salary_num, format_salary_amount_text,
        is_unavailable_player_profile_status, normalize_dead_type,
        normalize_exception_type, normalize_free_agent_type,
        normalize_gm_start_date, normalize_hex_color, normalize_pick_round,
        normalize_pick_type, normalize_player_happiness,
        normalize_player_profile_status, parse_salary_amount,
        player_profile_status_label, PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
        PLAYER_PROFILE_STATUS_RETIRED,
    )
    from .import_export.spreadsheets import xlsx_workbook_bytes
    from .integrations.discord import http_error_excerpt
    from .integrations.media import detect_safe_image_type, sanitize_http_image_url
    from .db.migrations import DatabaseMigrationsMixin
    from .db.maintenance import DatabaseMaintenanceMixin
    from .db.rows import row_to_dict
    from .db.migrations import CURRENT_SCHEMA_MIGRATION_KEY, CURRENT_SCHEMA_VERSION, now_iso
    from .observability.audit import (
        AuditEvent,
        AuditLogService,
        collect_team_codes,
        request_id_from_headers,
        resolve_entity_ids,
    )
    from .observability.logging import configure_logging, get_logger, request_context
    from .routing import (
        RequestValidationError,
        dispatch_routes,
        validate_boolean_field,
        validate_integer_range,
        validate_json_structure as validate_json_structure_limits,
        validate_number_range,
        validate_payload_fields,
        validate_team_code_field,
        validate_text_field,
        validate_unique_integer_ids,
    )
    from .routes import DELETE_ROUTES, EARLY_POST_ROUTES, GET_ROUTES, OWNER_OFFICE_MULTIPART_POST_ROUTES, PATCH_ROUTES, POST_ROUTES
    from .routes.gm_office import (
        validate_gm_depth_chart_payload,
        validate_gm_minimum_targets_payload,
        validate_gm_spending_limit_payload,
    )
    from .routes.validation import (
        validate_admin_decision_payload, validate_coadmin_vote_submit_payload,
        validate_free_agent_negotiation_payload, validate_free_agent_offer_payload,
        validate_gm_bird_renounce_payload, validate_gm_option_request_payload,
        validate_json_structure, validate_season_value_map,
        validate_waiver_claim_payload, JSON_MAX_CONTAINER_ITEMS,
        JSON_MAX_DEPTH, JSON_MAX_KEY_LENGTH, JSON_MAX_OBJECT_FIELDS,
        JSON_MAX_TOTAL_NODES,
    )
    from .runtime import load_env_file, static_asset_version as runtime_static_asset_version
    from .services.cartera import CarteraOperations, CarteraService
    from .services.admin_exports import LeagueWorkbookExportService
    from .services.admin_imports import OwnerAdminImportService
    from .services.free_agent_appeal import FreeAgentAppealService
    from .services.free_agent_agents import FreeAgentAgentImportService
    from .services.gm_minimum_targets import GMMinimumTargetService
    from .services.gm_office import GMOfficeService
    from .services.gm_requests import GMRequestService
    from .services.player_catalog import PlayerCatalogService
    from .services.player_identity import PlayerIdentityService
    from .services.owner_office import OwnerOfficeService
    from .services.owner_interviews import OwnerInterviewCompositionService
    from .services.offseason_exceptions import OffseasonExceptionOperations, OffseasonExceptionService
    from .services.offer_promises import OfferPromiseService
    from .services.season_rollover import SeasonRolloverService
    from .services.team_detail import TeamDetailOperations, TeamDetailService
    from .services.tracker import TrackerOperations, TrackerService
    from .services.trades import TradeService
except ImportError:  # pragma: no cover - supports `python3 app/server.py`.
    from application import ApplicationConfig, ApplicationContainer
    from auth.csrf import csrf_token_ok, same_origin_request_ok
    from auth.policies import (
        AUTH_POLICIES,
        AuthorizationError,
        authorization_actor_from_session,
        authorize_action,
        normalize_team_code,
        normalize_team_codes,
        parse_gm_account_map,
        serialize_team_codes,
    )
    from auth.sessions import (
        build_cookie,
        normalize_same_site,
        parse_allowed_origins,
        pbkdf2_sha256_password_hash,
        session_token_digest,
        verify_admin_password,
        verify_password_hash,
    )
    from db.repositories import sessions as session_repository
    from db.repositories.assets import AssetRepository
    from db.repositories.cartera import CarteraRepository
    from db.repositories.depth_charts import DepthChartRepository
    from db.repositories.draft import DraftReadOperations, DraftRepository
    from db.repositories.free_agency import FreeAgencyOperations, FreeAgencyRepository
    from db.repositories.free_agent_appeal import FreeAgentAppealRepository
    from db.repositories.free_agent_agents import FreeAgentAgentRepository
    from db.repositories.gm_workflows import (
        CoadminVoteRepository,
        GMRequestOperations,
        GMRequestRepository,
    )
    from db.repositories.gm_minimum_targets import GMMinimumTargetRepository
    from db.repositories.gm_office import GMOfficeRepository
    from db.repositories.notifications import NotificationRepository
    from db.repositories.outbox import OutboxRepository
    from db.repositories.offer_promises import OfferPromiseRepository
    from db.repositories.offseason_exceptions import OffseasonExceptionRepository
    from db.repositories.owner_office import OwnerOfficeRepository
    from db.repositories.player_identity import PlayerIdentityRepository
    from db.repositories.player_lifecycle import PlayerLifecycleRepository
    from db.repositories.players import PlayerRepository
    from db.repositories.press_articles import PressArticleRepository
    from db.repositories.season_rollover import SeasonRolloverOperations, SeasonRolloverRepository
    from db.repositories.settings import SettingsRepository
    from db.repositories.admin_imports import OwnerAdminImportRepository
    from db.repositories.users import UserRepository
    from db.repositories.teams import TeamRepository
    from db.repositories.team_detail import TeamDetailRepository
    from db.repositories.workflows import WorkflowRepository
    from db.repositories.trades import TradeOperations, TradeRepository
    from db.repositories.waivers import WaiverOperations, WaiverRepository
    from domain_rules import (
        CAP_FORECAST_MAX_YEAR,
        CAP_FORECAST_MIN_YEAR,
        CAP_FORECAST_WINDOW,
        OPEN_ROSTER_SPOT_MINIMUM,
        ROSTER_STANDARD_MAX_DEFAULT,
        ROSTER_STANDARD_MIN_DEFAULT,
        ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT,
        ROSTER_TWO_WAY_MAX_DEFAULT,
        ROSTER_TWO_WAY_MIN_DEFAULT,
        TRADE_MACHINE_MAX_TEAMS,
        TRADE_MACHINE_MIN_TEAMS,
        TRADE_MATCH_CUSHION,
        TRADE_MATCH_EXPANDED_BUFFER_FALLBACK,
        TRADE_MATCH_EXPANDED_BUFFER_RATIO,
        TRADE_MATCH_HIGH_BAND,
        TRADE_MATCH_LOW_BAND,
        TRADE_PICK_ACTION_SEND,
        TRADE_PICK_ACTION_SWAP,
        TRADE_ROOM_TPE_BUFFER,
        TWO_WAY_MINIMUM_BASE_SALARY,
        apron_yos_adjustment,
        cap_hold_bird_code_from_years,
        cap_hold_amount,
        counts_open_roster_minimum,
        format_trade_money,
        has_standard_cap_hold_marker,
        increment_bird_years_value,
        is_exhibit10_player,
        is_two_way_player,
        luxury_tax_amount,
        maximum_salary_for_experience,
        minimum_salary_2_yos_for_cap,
        minimum_contract_team_salary,
        minimum_salary_for_season,
        normalize_bird_years,
        normalize_experience_years,
        normalize_move_phase,
        normalize_trade_bucket,
        open_roster_spot_cap_hold,
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
        public_settings_payload,
        roster_contract_counts,
        roster_contract_slot_type,
        row_salary_num,
        salary_floor_for_season,
        apply_salary_floor,
        scaled_minimum_salary,
        season_label,
        settings_int,
    )
    from domain.exceptions import (
        GENERATED_OFFSEASON_EXCEPTION_KEYS,
        OFFSEASON_EXCEPTION_DEFINITIONS,
        normalize_apron_hard_cap,
        offseason_exception_amounts,
        offseason_exception_item,
    )
    from domain.cap import calculate_team_cap_summary
    from domain.contracts import contract_option_rejection_clear_payload
    from domain.normalization import (
        dead_contract_excluded_from_cap, dead_contract_excluded_from_gasto,
        dead_contract_salary_num, format_salary_amount_text,
        is_unavailable_player_profile_status, normalize_dead_type,
        normalize_exception_type, normalize_free_agent_type,
        normalize_gm_start_date, normalize_hex_color, normalize_pick_round,
        normalize_pick_type, normalize_player_happiness,
        normalize_player_profile_status, parse_salary_amount,
        player_profile_status_label, PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
        PLAYER_PROFILE_STATUS_RETIRED,
    )
    from import_export.spreadsheets import xlsx_workbook_bytes
    from integrations.discord import http_error_excerpt
    from integrations.media import detect_safe_image_type, sanitize_http_image_url
    from db.migrations import DatabaseMigrationsMixin
    from db.maintenance import DatabaseMaintenanceMixin
    from db.rows import row_to_dict
    from db.migrations import CURRENT_SCHEMA_MIGRATION_KEY, CURRENT_SCHEMA_VERSION, now_iso
    from observability.audit import (
        AuditEvent,
        AuditLogService,
        collect_team_codes,
        request_id_from_headers,
        resolve_entity_ids,
    )
    from observability.logging import configure_logging, get_logger, request_context
    from routing import (
        RequestValidationError,
        dispatch_routes,
        validate_boolean_field,
        validate_integer_range,
        validate_json_structure as validate_json_structure_limits,
        validate_number_range,
        validate_payload_fields,
        validate_team_code_field,
        validate_text_field,
        validate_unique_integer_ids,
    )
    from routes import DELETE_ROUTES, EARLY_POST_ROUTES, GET_ROUTES, OWNER_OFFICE_MULTIPART_POST_ROUTES, PATCH_ROUTES, POST_ROUTES
    from routes.gm_office import (
        validate_gm_depth_chart_payload,
        validate_gm_minimum_targets_payload,
        validate_gm_spending_limit_payload,
    )
    from routes.validation import (
        validate_admin_decision_payload, validate_coadmin_vote_submit_payload,
        validate_free_agent_negotiation_payload, validate_free_agent_offer_payload,
        validate_gm_bird_renounce_payload, validate_gm_option_request_payload,
        validate_json_structure, validate_season_value_map,
        validate_waiver_claim_payload, JSON_MAX_CONTAINER_ITEMS,
        JSON_MAX_DEPTH, JSON_MAX_KEY_LENGTH, JSON_MAX_OBJECT_FIELDS,
        JSON_MAX_TOTAL_NODES,
    )
    from runtime import load_env_file, static_asset_version as runtime_static_asset_version
    from services.cartera import CarteraOperations, CarteraService
    from services.admin_exports import LeagueWorkbookExportService
    from services.admin_imports import OwnerAdminImportService
    from services.free_agent_appeal import FreeAgentAppealService
    from services.free_agent_agents import FreeAgentAgentImportService
    from services.gm_minimum_targets import GMMinimumTargetService
    from services.gm_office import GMOfficeService
    from services.gm_requests import GMRequestService
    from services.player_catalog import PlayerCatalogService
    from services.player_identity import PlayerIdentityService
    from services.owner_office import OwnerOfficeService
    from services.owner_interviews import OwnerInterviewCompositionService
    from services.offseason_exceptions import OffseasonExceptionOperations, OffseasonExceptionService
    from services.offer_promises import OfferPromiseService
    from services.season_rollover import SeasonRolloverService
    from services.team_detail import TeamDetailOperations, TeamDetailService
    from services.tracker import TrackerOperations, TrackerService
    from services.trades import TradeService

logger = get_logger("server")

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
TRADE_VALIDATION_RULES_VERSION = "2026-07-16.1"
OWNER_BACKGROUND_MAX_BYTES = 12_000_000
CUSTOM_IMAGE_MAX_BYTES = 8 * 1024 * 1024
CUSTOM_IMAGE_MAX_BASE64_CHARS = ((CUSTOM_IMAGE_MAX_BYTES + 2) // 3) * 4 + 16
JSON_REQUEST_MAX_BYTES = 16 * 1024 * 1024
IMAGE_MAX_DIMENSION = 8192
IMAGE_MAX_PIXELS = 40_000_000
OWNER_BACKGROUND_ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
STATIC_ASSET_FILES = (
    "styles.css",
    "guest.js",
    "admin.js",
    "login.js",
    "news.js",
)
static_asset_version = partial(runtime_static_asset_version, WEB_DIR, STATIC_ASSET_FILES)
DEPTH_CHART_POSITIONS = ("PG", "SG", "SF", "PF", "C")
DEPTH_CHART_MAX_DEPTH = 6






DISCORD_CUSTOM_IMAGE_ALLOWED_MIME_TYPES = {
    **OWNER_BACKGROUND_ALLOWED_MIME_TYPES,
    "image/gif": "gif",
}
MULTIPART_UPLOAD_MAX_OVERHEAD_BYTES = 16_384
DEFAULT_ENV_FILE = ROOT / ".env"
DRAFT_LIVE_MAX_PENDING_REQUESTS = 2
FREE_AGENT_TYPE_UNRESTRICTED = "No restringido"
FREE_AGENT_TYPE_RESTRICTED = "Restringido"
FREE_AGENT_SOURCE_CAP_HOLD = "cap_hold"
FREE_AGENT_SOURCE_RENOUNCED_RIGHTS = "renounced_rights"
FREE_AGENT_SOURCE_UNCONTRACTED_PROFILE = "uncontracted_profile"
FREE_AGENT_PROMISE_ROLE_LIMITS = {
    "Sexto hombre": 1,
    "Minutos de rotación (10-20)": 5,
    "Minutos de rotación (0-9)": 10,
}
FREE_AGENT_FAVORITE_FIELDS = {"team_code"}
OFFER_CANCEL_FIELDS = {"team_code"}
PLAYER_CONTRACT_SEASONS = [2025, 2026, 2027, 2028, 2029, 2030, 2031]
PLAYER_CONTRACT_MIN_YEAR = min(PLAYER_CONTRACT_SEASONS)
PLAYER_CONTRACT_MAX_YEAR = max(PLAYER_CONTRACT_SEASONS)
PLAYER_CONTRACT_WINDOW_SIZE = 6
PLAYER_CONTRACT_MAX_START_YEAR = PLAYER_CONTRACT_MAX_YEAR - PLAYER_CONTRACT_WINDOW_SIZE + 1
CONTRACT_TERMINATING_OPTION_VALUES = {"TO", "PO"}
PLAYER_ROW_STATE_ACTIVE = "active_contract"
PLAYER_ROW_STATE_RETAINED_RIGHTS = "retained_rights"
PLAYER_ROW_STATES = {PLAYER_ROW_STATE_ACTIVE, PLAYER_ROW_STATE_RETAINED_RIGHTS}
PLAYER_UPDATE_TEXT_FIELDS = {
    "name", "bird_rights", "rating", "position", "years_left", "notes",
    "reference_image_url", "profile_notes",
}
PLAYER_UPDATE_PROFILE_FIELDS = {
    "experience_years", "date_of_birth", "nationality", "yos_source", "transaction_notes",
}
PLAYER_UPDATE_BOOL_FIELDS = {
    "provisional_amounts", "partially_guaranteed", "contract_notes", "signed_as_free_agent",
}
for _contract_season in PLAYER_CONTRACT_SEASONS:
    PLAYER_UPDATE_TEXT_FIELDS.update({
        f"salary_{_contract_season}_text",
        f"salary_{_contract_season}_guaranteed_text",
        f"salary_{_contract_season}_note_text",
        f"option_{_contract_season}",
    })
    PLAYER_UPDATE_BOOL_FIELDS.update({
        f"salary_{_contract_season}_provisional",
        f"salary_{_contract_season}_partially_guaranteed",
        f"salary_{_contract_season}_note",
    })
PLAYER_UPDATE_CONTROL_FIELDS = {
    "option_action", "option_action_field", "option_action_value",
    "notify_discord", "generate_image", "discord_custom_image",
}
PLAYER_UPDATE_ALLOWED_FIELDS = (
    PLAYER_UPDATE_TEXT_FIELDS
    | PLAYER_UPDATE_PROFILE_FIELDS
    | PLAYER_UPDATE_BOOL_FIELDS
    | PLAYER_UPDATE_CONTROL_FIELDS
)
FREE_AGENT_UPDATE_FIELDS = {
    "name", "position", "bird_rights", "rating", "years_left", "free_agent_type", "agent", "notes",
}
ASSET_UPDATE_FIELDS = {
    "asset_type", "year", "label", "detail", "amount_text", "draft_pick_type",
    "draft_round", "original_owner", "exception_type", "draft_pick_restricted",
    "draft_pick_stepien_restricted", "draft_pick_protected", "draft_pick_frozen",
    "draft_pick_sold_to", "draft_pick_conditional_teams",
}
DEAD_CONTRACT_UPDATE_FIELDS = {
    "label", "dead_type", "exclude_from_gasto", "exclude_from_cap", "amount_text",
    *(f"salary_{season}_text" for season in PLAYER_CONTRACT_SEASONS),
}
OWNER_SEASON_OBJECTIVES = [
    "Campeones",
    "Finalistas",
    "Final de conferencia",
    "Segunda ronda",
    "Primera ronda",
    "Entrar en play-in",
    "Luchar por el play-in",
    "Desarrollo de jóvenes",
]

load_env_file(Path(os.getenv("ENV_FILE", str(DEFAULT_ENV_FILE))))

class LeagueDB(DatabaseMigrationsMixin, DatabaseMaintenanceMixin):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._free_agents_sync_lock = threading.Lock()
        self._session_cleanup_lock = threading.Lock()
        self._tracker_cache_lock = threading.Lock()
        self._tracker_cache: Dict[int, Dict[str, Any]] = {}
        self._notification_repository = NotificationRepository(self, now=now_iso)
        self._workflow_repository = WorkflowRepository(self, now=now_iso)
        self._outbox_repository = OutboxRepository(self, now=now_iso)
        self._press_article_repository = PressArticleRepository(
            self,
            detect_image_type=detect_safe_image_type,
            allowed_mime_types=DISCORD_CUSTOM_IMAGE_ALLOWED_MIME_TYPES,
            max_image_bytes=CUSTOM_IMAGE_MAX_BYTES,
            now=now_iso,
        )
        self._settings_repository = SettingsRepository(self, now=now_iso)
        self._user_repository = UserRepository(self, now=now_iso)
        self._coadmin_vote_repository = CoadminVoteRepository(
            self,
            now=now_iso,
            normalize_team_code=normalize_team_code,
            normalize_team_codes=normalize_team_codes,
        )
        self._gm_minimum_target_repository = GMMinimumTargetRepository(self)
        self._gm_minimum_target_service = GMMinimumTargetService(
            self._gm_minimum_target_repository,
            now=now_iso,
        )
        self._offer_promise_repository = OfferPromiseRepository(
            self,
            now=now_iso,
            role_limits=FREE_AGENT_PROMISE_ROLE_LIMITS,
            forecast_min_year=CAP_FORECAST_MIN_YEAR,
        )
        self._offer_promise_service = OfferPromiseService(
            self._offer_promise_repository,
            user_access=self.user_access_for_email,
        )
        self._gm_request_repository = GMRequestRepository(
            self,
            GMRequestOperations(
                now=now_iso,
                normalize_team_code=normalize_team_code,
                contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
                contract_max_year=PLAYER_CONTRACT_MAX_YEAR,
            ),
            workflows=self._workflow_repository,
        )
        self._player_lifecycle_repository = PlayerLifecycleRepository(
            self,
            now=now_iso,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
            normalize_experience=normalize_experience_years,
            unavailable_profile_status=is_unavailable_player_profile_status,
            normalize_profile_status=normalize_player_profile_status,
            profile_status_label=player_profile_status_label,
            retained_rights_only=self._player_row_is_retained_rights_only,
            active_row_state=PLAYER_ROW_STATE_ACTIVE,
            retained_rights_row_state=PLAYER_ROW_STATE_RETAINED_RIGHTS,
            workflows=self._workflow_repository,
        )
        self._asset_repository = AssetRepository(
            self,
            now=now_iso,
            asset_update_fields=ASSET_UPDATE_FIELDS,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
            normalize_pick_type=normalize_pick_type,
            normalize_pick_round=normalize_pick_round,
            serialize_team_codes=serialize_team_codes,
            normalize_exception_type=normalize_exception_type,
            normalize_dead_type=normalize_dead_type,
            parse_salary_amount=parse_salary_amount,
            resolve_profile=self._player_lifecycle_repository.resolve_profile,
            create_profile=self._player_lifecycle_repository.create_profile,
        )
        self._team_repository = TeamRepository(
            self,
            now=now_iso,
            normalize_gm_start_date=normalize_gm_start_date,
            normalize_hex_color=normalize_hex_color,
        )
        self._team_detail_repository = TeamDetailRepository(self)
        self._owner_admin_import_repository = OwnerAdminImportRepository(self)
        self._player_repository = PlayerRepository(
            self,
            now=now_iso,
            select_columns=self._player_select_columns,
            merge_profile=self._merge_player_profile,
            record_transaction=self._player_lifecycle_repository.record_transaction,
            upsert_salary_history=self._player_lifecycle_repository.upsert_salary_history,
            attach_salary_history=self._player_lifecycle_repository.attach_salary_history,
            player_text_fields=PLAYER_UPDATE_TEXT_FIELDS,
            player_bool_fields=PLAYER_UPDATE_BOOL_FIELDS,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
            normalize_experience=normalize_experience_years,
            ensure_profile=self._player_lifecycle_repository.ensure_profile,
            sync_row_state=self._player_lifecycle_repository.sync_row_state,
            sync_generated_free_agents=self._sync_free_agency_generated_rows_if_needed,
            normalize_happiness=normalize_player_happiness,
            normalize_profile_status=normalize_player_profile_status,
            is_unavailable_profile_status=is_unavailable_player_profile_status,
            make_profile_unavailable=self._player_lifecycle_repository.make_profile_unavailable,
            retained_rights_only=self._player_row_is_retained_rights_only,
            resolve_profile=self._player_lifecycle_repository.resolve_profile,
            parse_salary_amount=parse_salary_amount,
            free_agent_type_unrestricted=FREE_AGENT_TYPE_UNRESTRICTED,
            free_agent_source_uncontracted=FREE_AGENT_SOURCE_UNCONTRACTED_PROFILE,
        )
        self._player_identity_repository = PlayerIdentityRepository(
            self,
            now=now_iso,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
            retained_rights_only=self._player_row_is_retained_rights_only,
            current_year=self._player_lifecycle_repository.current_year,
            record_transaction=self._player_lifecycle_repository.record_transaction,
            table_exists=self._player_lifecycle_repository.table_exists,
            select_team_players=self._select_team_players,
            attach_option_decisions=self._attach_option_decisions,
            cleanup_minimum_targets=self._cleanup_gm_minimum_targets_for_free_agent_ids_conn,
            ensure_profile=self._player_lifecycle_repository.ensure_profile,
            unavailable_profile_status=is_unavailable_player_profile_status,
            free_agent_type_restricted=FREE_AGENT_TYPE_RESTRICTED,
            free_agent_type_unrestricted=FREE_AGENT_TYPE_UNRESTRICTED,
            free_agent_source_cap_hold=FREE_AGENT_SOURCE_CAP_HOLD,
            free_agent_source_renounced_rights=FREE_AGENT_SOURCE_RENOUNCED_RIGHTS,
            free_agent_source_uncontracted=FREE_AGENT_SOURCE_UNCONTRACTED_PROFILE,
            unavailable_profile_statuses=(
                PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
                PLAYER_PROFILE_STATUS_RETIRED,
            ),
            profile_repository=self._player_repository,
        )
        self._free_agency_repository = FreeAgencyRepository(
            self,
            FreeAgencyOperations(
                now=now_iso,
                normalize_team_code=normalize_team_code,
                sync_generated=lambda conn, settings: self._player_identity_service().synchronize_generated_free_agents(
                    conn, settings
                ),
                merge_profile=self._merge_player_profile,
                attach_salary_history=self._player_lifecycle_repository.attach_salary_history,
                sync_lock=self._free_agents_sync_lock,
                unavailable_statuses=(
                    PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
                    PLAYER_PROFILE_STATUS_RETIRED,
                ),
                player_repository=self._player_repository,
                normalize_bird_years=normalize_bird_years,
                normalize_experience_years=normalize_experience_years,
                parse_salary_amount=parse_salary_amount,
                unavailable_profile_status=is_unavailable_player_profile_status,
                contract_seasons=tuple(PLAYER_CONTRACT_SEASONS),
                player_lifecycle=self._player_lifecycle_repository,
                normalize_free_agent_type=normalize_free_agent_type,
                free_agent_update_fields=tuple(FREE_AGENT_UPDATE_FIELDS),
                free_agent_type_unrestricted=FREE_AGENT_TYPE_UNRESTRICTED,
                free_agent_source_renounced_rights=FREE_AGENT_SOURCE_RENOUNCED_RIGHTS,
                season_label=season_label,
            ),
        )
        self._gm_request_service = GMRequestService(
            self._gm_request_repository,
            workflows=self._workflow_repository,
            offer_promises=self._offer_promise_repository,
            notifications=self._notification_repository,
            free_agency=self._free_agency_repository,
            outbox=self._outbox_repository,
            players=self._player_repository,
            now=now_iso,
            normalize_team_code=normalize_team_code,
        )
        self._free_agent_appeal_repository = FreeAgentAppealRepository(self)
        self._free_agent_appeal_service = FreeAgentAppealService(
            self._free_agent_appeal_repository,
            now=now_iso,
        )
        self._free_agent_agent_repository = FreeAgentAgentRepository(self)
        self._free_agent_agent_import_service = FreeAgentAgentImportService(
            self._free_agent_agent_repository,
            now=now_iso,
            synchronize_generated=lambda conn, settings: self._player_identity_service().synchronize_generated_free_agents(
                conn, settings
            ),
        )
        self._waiver_repository = WaiverRepository(
            self,
            WaiverOperations(
                now=now_iso,
                settings=self.get_settings,
                salary_for_season=self._waiver_salary_for_season,
                claim_eligibility=self._waiver_claim_eligibility,
                record_player_transaction_conn=self._player_lifecycle_repository.record_transaction,
                player_repository=self._player_repository,
                player_lifecycle=self._player_lifecycle_repository,
                player_select_columns=self._player_select_columns,
                merge_player_profile=self._merge_player_profile,
                contract_snapshot=self._player_contract_snapshot_payload,
                normalize_cut_options=self._normalize_cut_options,
                cut_dead_cap_schedule=self._cut_dead_cap_schedule,
                player_is_ten_day_contract=self._player_is_ten_day_contract,
                normalize_bird_years=normalize_bird_years,
                parse_salary_amount=parse_salary_amount,
                contract_seasons=tuple(PLAYER_CONTRACT_SEASONS),
                free_agent_type_unrestricted=FREE_AGENT_TYPE_UNRESTRICTED,
            ),
            workflows=self._workflow_repository,
        )
        self._draft_repository = DraftRepository(
            self,
            DraftReadOperations(
                normalize_pick_round=normalize_pick_round,
                normalize_pick_type=normalize_pick_type,
                normalize_team_code=normalize_team_code,
                normalize_team_codes=normalize_team_codes,
                now=now_iso,
                contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
                contract_max_start_year=PLAYER_CONTRACT_MAX_START_YEAR,
                max_pending_requests=DRAFT_LIVE_MAX_PENDING_REQUESTS,
                resolve_profile_for_new_row=self._player_lifecycle_repository.resolve_profile,
                record_player_transaction_conn=self._player_lifecycle_repository.record_transaction,
                parse_salary_amount=parse_salary_amount,
                parse_amount_like=parse_amount_like,
                contract_seasons=tuple(PLAYER_CONTRACT_SEASONS),
                contract_max_year=PLAYER_CONTRACT_MAX_YEAR,
            ),
            workflows=self._workflow_repository,
        )
        self._season_rollover_repository = SeasonRolloverRepository(
            self,
            SeasonRolloverOperations(
                now=now_iso,
                select_team_players=self._select_team_players,
                calc_summary=calculate_team_cap_summary,
                luxury_repeater=self._team_luxury_repeater_for_season,
                apron_hard_cap=self._team_apron_hard_cap_for_season,
                ensure_profile=self._player_lifecycle_repository.ensure_profile,
                upsert_salary_history=self._player_lifecycle_repository.upsert_salary_history,
                record_transaction=self._player_lifecycle_repository.record_transaction,
                upsert_frozen_pick=self._asset_repository.upsert_frozen_pick_conn,
                row_to_dict=row_to_dict,
                increment_bird_years_value=increment_bird_years_value,
                normalize_bird_years=normalize_bird_years,
                dead_contract_salary_num=dead_contract_salary_num,
                contract_seasons=tuple(PLAYER_CONTRACT_SEASONS),
                contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
                contract_max_year=PLAYER_CONTRACT_MAX_YEAR,
            ),
        )
        self._trade_repository = TradeRepository(
            self,
            TradeOperations(
                get_team=self.get_team,
                team_move_summary=self._team_move_summary,
                upsert_team_move_log=self._upsert_team_move_log,
                record_transaction=self._player_lifecycle_repository.record_transaction,
                normalize_pick_type=normalize_pick_type,
                normalize_pick_round=normalize_pick_round,
                normalize_dead_type=normalize_dead_type,
                dead_contract_excluded_from_cap=dead_contract_excluded_from_cap,
                dead_contract_salary_num=dead_contract_salary_num,
                row_to_dict=row_to_dict,
                now=now_iso,
                rules_version=TRADE_VALIDATION_RULES_VERSION,
                contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
                contract_max_year=PLAYER_CONTRACT_MAX_YEAR,
                contract_max_start_year=PLAYER_CONTRACT_MAX_START_YEAR,
                apply_hard_cap_triggers=self.apply_trade_hard_cap_triggers,
            ),
        )
        self._cartera_service = CarteraService(
            CarteraRepository(self),
            CarteraOperations(
                settings=self.get_settings,
                teams=self.list_teams,
                team_detail=self.get_team,
                exception_estimate=self._offseason_exception_estimate_from_summary,
                cap_hold_amount=cap_hold_amount,
                cap_hold_label=self._cap_hold_display_label,
                season_label=season_label,
                normalize_team_code=normalize_team_code,
                user_access=self.user_access_for_email,
                spending_limits=self.list_gm_free_agent_spending_limits,
                forecast_min_year=CAP_FORECAST_MIN_YEAR,
                forecast_max_year=CAP_FORECAST_MAX_YEAR,
            ),
        )
        self._offseason_exception_service = OffseasonExceptionService(
            OffseasonExceptionRepository(self),
            OffseasonExceptionOperations(
                settings=self.get_settings,
                teams=self.list_teams,
                team_detail=self.get_team,
                estimate=self._offseason_exception_estimate_from_summary,
                normalize_team_codes=normalize_team_codes,
                season_label=season_label,
                now=now_iso,
                generated_keys=tuple(GENERATED_OFFSEASON_EXCEPTION_KEYS),
                definitions=OFFSEASON_EXCEPTION_DEFINITIONS,
            ),
        )
        self._owner_office_repository = OwnerOfficeRepository(
            self,
            now=now_iso,
            allowed_mime_types=OWNER_BACKGROUND_ALLOWED_MIME_TYPES,
            background_max_bytes=OWNER_BACKGROUND_MAX_BYTES,
        )
        self._depth_chart_repository = DepthChartRepository(
            self,
            players=self._player_repository,
            now=now_iso,
            normalize_team_code=normalize_team_code,
            positions=DEPTH_CHART_POSITIONS,
            max_depth=DEPTH_CHART_MAX_DEPTH,
        )
        self._gm_office_repository = GMOfficeRepository(
            self,
            gm_requests=self._gm_request_repository,
            players=self._player_repository,
            depth_charts=self._depth_chart_repository,
        )
        self._gm_office_service = GMOfficeService(self._gm_office_repository)
        self._team_detail_service = TeamDetailService(
            self._team_detail_repository,
            TeamDetailOperations(
                select_players=self._select_team_players,
                attach_option_decisions=self._attach_option_decisions,
                select_frozen_draft_picks=self._select_frozen_draft_picks,
                get_settings=self.get_settings,
                luxury_repeater=self._team_luxury_repeater_for_season,
                hard_cap=self._team_apron_hard_cap_for_season,
                calculate_summary=calculate_team_cap_summary,
                season_summaries=self._team_season_summaries,
                exception_estimates=self._team_exception_estimates,
                attach_cap_hold_fields=self._attach_cap_hold_display_fields,
                move_summary=self._team_move_summary,
                move_summaries=self._team_move_summaries,
                luxury_history=self._team_luxury_history,
                hard_caps=self._team_apron_hard_caps,
                depth_chart=self._team_depth_chart_payload,
            ),
        )
        self._player_catalog_service = PlayerCatalogService(
            self,
            normalize_profile_status=normalize_player_profile_status,
            is_unavailable_profile_status=is_unavailable_player_profile_status,
            profile_status_label=player_profile_status_label,
            sync_generated=lambda conn, settings: self._player_identity_service().synchronize_generated_free_agents(
                conn, settings
            ),
            table_exists=self._table_exists_conn,
            min_contract_year=PLAYER_CONTRACT_MIN_YEAR,
            max_contract_start_year=PLAYER_CONTRACT_MAX_START_YEAR,
        )
        self._tracker_service = TrackerService(
            self,
            TrackerOperations(
                select_players=self._select_team_players,
                luxury_repeater=self._team_luxury_repeater_for_season,
                hard_cap=self._team_apron_hard_cap_for_season,
                calculate_summary=calculate_team_cap_summary,
                normalize_pick_type=normalize_pick_type,
                get_cache=self._get_tracker_cache,
                set_cache=self._set_tracker_cache,
                is_lock_error=self._is_sqlite_lock_error,
            ),
            min_year=CAP_FORECAST_MIN_YEAR,
            max_year=CAP_FORECAST_MAX_YEAR,
        )
        self._owner_admin_import_service_instance = OwnerAdminImportService(
            self._owner_admin_import_repository,
            now=now_iso,
            objective_options=OWNER_SEASON_OBJECTIVES,
        )
        self._admin_export_service = LeagueWorkbookExportService(
            self,
            get_settings=self.get_settings,
            list_teams=self._team_repository.list,
            list_tracker=self._tracker_service.list,
            list_players=self._player_catalog_service.list_players,
            list_free_agents=self._free_agency_repository.list_free_agents,
            get_team=self._team_detail_service.get,
            parse_bool=parse_bool,
            normalize_team_codes=normalize_team_codes,
            season_label=season_label,
            public_settings_payload=public_settings_payload,
            workbook_bytes=xlsx_workbook_bytes,
            unrestricted_type=FREE_AGENT_TYPE_UNRESTRICTED,
            min_year=CAP_FORECAST_MIN_YEAR,
            max_year=CAP_FORECAST_MAX_YEAR,
        )

    def _audit_log_service(self) -> AuditLogService:
        return AuditLogService(self.connect, now_iso, normalize_team_code)

    @staticmethod
    def _is_sqlite_lock_error(exc: BaseException) -> bool:
        message = str(exc).lower()
        return "database is locked" in message or "database table is locked" in message

    def _get_tracker_cache(self, season_year: Optional[int]) -> Optional[Dict[str, Any]]:
        with self._tracker_cache_lock:
            if season_year is not None and season_year in self._tracker_cache:
                cached = copy.deepcopy(self._tracker_cache[season_year])
            elif self._tracker_cache:
                cached = copy.deepcopy(next(reversed(self._tracker_cache.values())))
            else:
                cached = None
        if cached is not None:
            timings = cached.setdefault("timings", {})
            timings["cache_stale"] = 1.0
            cached["stale"] = True
        return cached

    def _set_tracker_cache(self, season_year: int, payload: Dict[str, Any]) -> None:
        with self._tracker_cache_lock:
            self._tracker_cache[int(season_year)] = copy.deepcopy(payload)

    def _record_workflow_creation_conn(
        self,
        conn: sqlite3.Connection,
        workflow_type: str,
        resource_id: Any,
        initial_state: str,
        *,
        actor: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        command_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        return self._workflow_repository.record_creation_conn(
            conn,
            workflow_type,
            resource_id,
            initial_state,
            actor=actor,
            reason=reason,
            command_id=command_id,
            metadata=metadata,
            timestamp=timestamp,
        )

    def _transition_workflow_conn(
        self,
        conn: sqlite3.Connection,
        workflow_type: str,
        resource_id: Any,
        new_state: str,
        *,
        actor: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        command_id: Optional[str] = None,
        updates: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._workflow_repository.transition_conn(
            conn,
            workflow_type,
            resource_id,
            new_state,
            actor=actor,
            reason=reason,
            command_id=command_id,
            updates=updates,
            metadata=metadata,
            timestamp=timestamp,
        )

    def warm_tracker_cache(self) -> None:
        settings = self.get_settings()
        current_year = parse_int(settings.get("current_year")) or CAP_FORECAST_MIN_YEAR
        current_year = max(CAP_FORECAST_MIN_YEAR, min(CAP_FORECAST_MAX_YEAR, current_year))
        self.list_tracker(current_year, busy_timeout_ms=15000)




    def _create_player_profile(
        self,
        conn: sqlite3.Connection,
        name: Any,
        experience_years: Any = None,
        reference_image_url: Any = None,
        profile_notes: Any = None,
        timestamp: Optional[str] = None,
    ) -> int:
        return self._player_lifecycle_repository.create_profile(
            conn, name, experience_years, reference_image_url, profile_notes, timestamp
        )


    def _current_year_conn(self, conn: sqlite3.Connection) -> int:
        return self._player_lifecycle_repository.current_year(conn)

    def _players_have_row_state_conn(self, conn: sqlite3.Connection) -> bool:
        return self._player_lifecycle_repository.players_have_row_state(conn)

    def _infer_player_row_state_conn(
        self,
        conn: sqlite3.Connection,
        player: sqlite3.Row,
        current_year: Optional[int] = None,
    ) -> str:
        return self._player_lifecycle_repository.infer_row_state(conn, player, current_year)

    def _duplicate_active_profile_ids_conn(self, conn: sqlite3.Connection) -> List[int]:
        return self._player_lifecycle_repository.duplicate_active_profile_ids(conn)

    def _sync_draft_pick_asset_identity_conn(
        self,
        conn: sqlite3.Connection,
        asset_id: Any,
        timestamp: Optional[str] = None,
    ) -> None:
        self._asset_repository.sync_draft_pick_identity(conn, asset_id, timestamp)


    def _player_profile_exists_conn(self, conn: sqlite3.Connection, profile_id: Any) -> bool:
        return self._player_lifecycle_repository.profile_exists(conn, profile_id)

    def _table_exists_conn(self, conn: sqlite3.Connection, table_name: str) -> bool:
        return self._player_lifecycle_repository.table_exists(conn, table_name)

    def _upsert_player_salary_history_row_conn(
        self,
        conn: sqlite3.Connection,
        *,
        profile_id: Any,
        player_id: Any,
        team_code: Any,
        season_year: Any,
        salary_text: Any,
        salary_num: Any,
        source: str,
        salary_type: Any = None,
        timestamp: Optional[str] = None,
    ) -> bool:
        return self._player_lifecycle_repository.upsert_salary_history(
            conn,
            profile_id=profile_id,
            player_id=player_id,
            team_code=team_code,
            season_year=season_year,
            salary_text=salary_text,
            salary_num=salary_num,
            source=source,
            salary_type=salary_type,
            timestamp=timestamp,
        )


    def _unique_profile_name_map_conn(self, conn: sqlite3.Connection) -> Dict[str, int]:
        return self._player_lifecycle_repository.unique_profile_name_map(conn)



    def _cap_hold_display_label(self, player: Dict[str, Any], season: int) -> str:
        salary_marker = str(player.get(f"salary_{season}_text") or "").strip().upper()
        option_marker = str(player.get(f"option_{season}") or "").strip().upper()
        decision = (player.get("option_decisions") or {}).get(f"option_{season}") or {}
        decision_option = str(decision.get("option_value") or "").strip().upper() if isinstance(decision, dict) else ""
        decision_action = str(decision.get("action") or "").strip().lower() if isinstance(decision, dict) else ""
        decision_status = str(decision.get("status") or "").strip().lower() if isinstance(decision, dict) else ""
        is_qo_style = (
            salary_marker == "QO"
            or option_marker == "QO"
            or (
                decision_option in {"QO", "GAP"}
                and decision_action == "accepted"
                and decision_status == "approved"
            )
        )
        if is_qo_style:
            return "QO hold"
        if salary_marker in {"NB", "EB", "FB"}:
            return f"{salary_marker} hold"
        if option_marker in {"NB", "EB", "FB"}:
            return f"{option_marker} hold"
        return "Cap hold"

    def _cap_hold_display_message(self, label: str) -> str:
        normalized = str(label or "").strip().upper()
        if normalized.startswith("QO"):
            return "Cap hold QO calculado con el salario anterior, salario medio y limite maximo por YOS."
        if normalized.startswith("FB"):
            return "Cap hold Full Bird calculado con el salario anterior, salario medio y limite maximo por YOS."
        if normalized.startswith("EB"):
            return "Cap hold Early Bird: 130% del salario anterior, limitado por maximo YOS si aplica."
        if normalized.startswith("NB"):
            return "Cap hold Non-Bird calculado con el salario anterior o minimo aplicable, limitado por maximo YOS si aplica."
        return "Cap hold calculado por el servidor."

    def _attach_cap_hold_display_fields(
        self,
        players: List[Dict[str, Any]],
        settings: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        if not parse_bool(settings.get("free_agency_mode")):
            return players
        season = parse_int(settings.get("current_year")) or 2025
        salary_cap = (
            parse_float(settings.get(f"salary_cap_{season}"))
            or parse_float(settings.get("salary_cap_2025"))
            or 0.0
        )
        if salary_cap <= 0:
            return players
        for player in players:
            amount = cap_hold_amount(player, season, settings, salary_cap)
            if amount <= 0:
                continue
            label = self._cap_hold_display_label(player, season)
            player[f"cap_hold_{season}_displayable"] = True
            player[f"cap_hold_{season}_amount"] = float(amount)
            player[f"cap_hold_{season}_short_label"] = label
            player[f"cap_hold_{season}_message"] = self._cap_hold_display_message(label)
            if label.upper().startswith("QO"):
                qo_value = row_salary_num(player, season)
                if qo_value > 0:
                    player[f"cap_hold_{season}_display_amount"] = float(qo_value)
        return players

    def _find_profile_id(
        self,
        conn: sqlite3.Connection,
        player_id: Any = None,
        free_agent_id: Any = None,
        dead_contract_id: Any = None,
        name: Any = None,
    ) -> Optional[int]:
        return self._player_lifecycle_repository.find_profile_id(conn, player_id, free_agent_id, dead_contract_id, name)


    def _record_player_transaction(
        self,
        conn: sqlite3.Connection,
        profile_id: Any,
        action: str,
        summary: str,
        *,
        player_id: Any = None,
        free_agent_id: Any = None,
        dead_contract_id: Any = None,
        team_code: Any = None,
        from_team_code: Any = None,
        to_team_code: Any = None,
        details: Optional[Dict[str, Any]] = None,
        source_log_id: Any = None,
        created_at: Optional[str] = None,
    ) -> None:
        self._player_lifecycle_repository.record_transaction(
            conn,
            profile_id,
            action,
            summary,
            player_id=player_id,
            free_agent_id=free_agent_id,
            dead_contract_id=dead_contract_id,
            team_code=team_code,
            from_team_code=from_team_code,
            to_team_code=to_team_code,
            details=details,
            source_log_id=source_log_id,
            created_at=created_at,
        )


    def _player_select_columns(self) -> str:
        return """
            p.*,
            pp.name AS profile_name,
            pp.date_of_birth AS profile_date_of_birth,
            pp.nationality AS profile_nationality,
            pp.experience_years AS profile_experience_years,
            pp.yos_source AS profile_yos_source,
            pp.reference_image_url AS profile_reference_image_url,
            pp.profile_notes AS profile_profile_notes,
            pp.transaction_notes AS profile_transaction_notes
        """

    def _merge_player_profile(self, player: Dict[str, Any]) -> Dict[str, Any]:
        if player.get("profile_name"):
            player["contract_name"] = player.get("name")
            player["name"] = player.get("profile_name")
        if player.get("profile_experience_years") is not None:
            player["experience_years"] = player.get("profile_experience_years")
        if player.get("profile_date_of_birth") is not None:
            player["date_of_birth"] = player.get("profile_date_of_birth")
        if player.get("profile_nationality") is not None:
            player["nationality"] = player.get("profile_nationality")
        if player.get("profile_yos_source") is not None:
            player["yos_source"] = player.get("profile_yos_source")
        if player.get("profile_reference_image_url"):
            player["reference_image_url"] = player.get("profile_reference_image_url")
        if player.get("profile_profile_notes") is not None:
            player["profile_notes"] = player.get("profile_profile_notes")
        if player.get("profile_transaction_notes") is not None:
            player["transaction_notes"] = player.get("profile_transaction_notes")
        return player

    def _select_team_players(self, conn: sqlite3.Connection, team_id: int) -> List[Dict[str, Any]]:
        return self._player_repository.select_team(conn, team_id)

    def get_settings(self) -> Dict[str, str]:
        return self._settings_repository.get_all()

    def _team_move_summary(self, conn: sqlite3.Connection, team_id: int, season_year: int, settings: Dict[str, str]) -> Dict[str, Any]:
        return self._trade_repository.team_move_summary(conn, team_id, season_year, settings)

    def _team_move_summaries(
        self,
        conn: sqlite3.Connection,
        team_id: int,
        settings: Dict[str, str],
        include_year: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        current_year = parse_int(settings.get("current_year")) or 2025
        years = {current_year + idx for idx in range(6)}
        if include_year is not None:
            years.add(int(include_year))
        return {
            str(year): self._team_move_summary(conn, team_id, int(year), settings)
            for year in sorted(years)
        }


    def update_setting(self, key: str, value: str) -> None:
        self._settings_repository.update(key, value)

    def update_current_year(self, next_year: int) -> Dict[str, Any]:
        return self._season_rollover_service().update_current_year(next_year)

    def progress_to_next_year(self) -> Dict[str, Any]:
        return self._season_rollover_service().progress_to_next_year()

    def _season_rollover_service(self) -> SeasonRolloverService:
        return SeasonRolloverService(
            self._season_rollover_repository,
            contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
            contract_max_start_year=PLAYER_CONTRACT_MAX_START_YEAR,
        )

    def upsert_google_user(self, google_sub: str, email: str, display_name: Optional[str], avatar_url: Optional[str]) -> Dict[str, Any]:
        return self._user_repository.upsert_google_user(google_sub, email, display_name, avatar_url)

    def user_access_for_email(self, email: str) -> Dict[str, Any]:
        return self._user_repository.access_for_email(email)

    def replace_user_team_assignments(
        self,
        user_id: int,
        team_codes: Any,
        is_co_admin: Optional[bool] = None,
        agent_name: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._user_repository.replace_team_assignments(
            user_id,
            team_codes,
            is_co_admin=is_co_admin,
            agent_name=agent_name,
        )


    def create_coadmin_vote(self, title: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._coadmin_vote_repository.create_coadmin_vote(title, actor)


    def get_coadmin_vote(self, vote_id: Any) -> Optional[Dict[str, Any]]:
        return self._coadmin_vote_repository.get_coadmin_vote(vote_id)


    def set_coadmin_vote_status(self, vote_id: Any, status: Any, actor: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return self._coadmin_vote_repository.set_coadmin_vote_status(vote_id, status, actor)


    def list_admin_coadmin_votes(self) -> List[Dict[str, Any]]:
        return self._coadmin_vote_repository.list_admin_coadmin_votes()


    def list_coadmin_votes_for_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return self._coadmin_vote_repository.list_coadmin_votes_for_session(session)


    def submit_coadmin_vote(self, vote_id: Any, scores: Any, session: Dict[str, Any]) -> Dict[str, Any]:
        return self._coadmin_vote_repository.submit_coadmin_vote(vote_id, scores, session)


    def _gm_option_request_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = row_to_dict(cursor, row)
        item["request_type"] = "option"
        raw_field = str(item.get("option_field") or "")
        salary_text_match = re.fullmatch(r"salary_(20\d{2})_text", raw_field)
        if salary_text_match and str(item.get("action") or "").strip().lower() == "renounced":
            item["request_type"] = "bird_rights_renounce"
            season_year = parse_int(salary_text_match.group(1))
            item["season_year"] = season_year
            item["season_label"] = f"{season_year}-{(season_year + 1) % 100:02d}" if season_year else ""
            return item
        match = re.fullmatch(r"option_(20\d{2})", raw_field)
        season_year = parse_int(match.group(1)) if match else None
        item["season_year"] = season_year
        item["season_label"] = f"{season_year}-{(season_year + 1) % 100:02d}" if season_year else ""
        return item

    def _gm_free_agent_offer_request_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = row_to_dict(cursor, row)
        item["request_type"] = "free_agent_offer"
        item["action"] = "offered"
        item["option_field"] = "free_agent_offer"
        offer_type = str(item.get("offer_type") or "free_agent_offer").strip().lower()
        item["option_value"] = "Renovación" if offer_type == "renewal" else "Oferta FA"
        raw_payload = str(item.get("offer_payload_json") or "{}")
        try:
            offer_payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            offer_payload = {}
        if not isinstance(offer_payload, dict):
            offer_payload = {}
        item["offer_payload"] = offer_payload
        if not str(item.get("player_name") or "").strip():
            item["player_name"] = str(offer_payload.get("player_name") or offer_payload.get("name") or "Agente libre")
        contract_type = str(offer_payload.get("contract_type") or "").strip() or "Sin tipo"
        years = parse_int(offer_payload.get("years"))
        years_text = f"{years} año(s)" if years is not None and years > 0 else "Sin duración"
        item["season_label"] = f"{contract_type} · {years_text}"
        item["offer_contract_type"] = contract_type
        item["offer_years"] = years
        return item

    def get_gm_option_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.get_gm_option_request(request_id)


    def list_gm_option_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        requests = [
            *self._gm_request_repository.list_requests(status),
            *self._draft_repository.list_pick_requests(status),
            *self.list_waiver_claim_requests(status=status),
        ]
        requests.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)), reverse=True)
        requests.sort(key=lambda item: 0 if str(item.get("status") or "") == "pending" else 1)
        return requests


    def _get_gm_free_agent_offer_request_conn(
        self,
        conn: sqlite3.Connection,
        request_id: int,
    ) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository._get_gm_free_agent_offer_request_conn(conn, request_id)

    def get_gm_free_agent_offer_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.get_gm_free_agent_offer_request(request_id)


    def create_gm_option_request(self, player_id: int, option_field: str, option_value: str, action: str, requester: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.create_gm_option_request(player_id, option_field, option_value, action, requester)


    def record_admin_option_decision(
        self,
        player_id: int,
        option_field: str,
        option_value: str,
        action: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.record_admin_option_decision(
            player_id, option_field, option_value, action, admin, note
        )

    def create_gm_bird_rights_renounce_request(self, player_id: int, season_year: int, rights_value: str, requester: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.create_gm_bird_rights_renounce_request(player_id, season_year, rights_value, requester)


    def create_gm_draft_pick_request(
        self,
        draft_order_id: int,
        payload: Dict[str, Any],
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._draft_repository.create_pick_request(draft_order_id, payload, requester)

    def enqueue_outbox_event_conn(
        self,
        conn: sqlite3.Connection,
        event_type: str,
        payload: Dict[str, Any],
        *,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[int]:
        return self._outbox_repository.enqueue_conn(
            conn,
            event_type,
            payload,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
        )

    def enqueue_outbox_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[int]:
        return self._outbox_repository.enqueue(
            event_type,
            payload,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
        )

    def get_outbox_event(self, event_id: Any) -> Optional[Dict[str, Any]]:
        return self._outbox_repository.get(event_id)

    def mark_outbox_event_succeeded(self, event_id: Any) -> bool:
        return self._outbox_repository.mark_succeeded(event_id)

    def mark_outbox_event_failed(self, event_id: Any, error: Any) -> bool:
        return self._outbox_repository.mark_failed(event_id, error)

    def create_gm_free_agent_offer_request(self, free_agent_id: int, team_code: str, payload: Dict[str, Any], requester: Dict[str, Any], offer_type: str = "free_agent_offer") -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.create_gm_free_agent_offer_request(free_agent_id, team_code, payload, requester, offer_type)


    def mark_gm_draft_pick_request_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._draft_repository.mark_pick_request_decided(request_id, status, admin, note)

    def mark_gm_free_agent_offer_request_decided(self, request_id: int, status: str, admin: Dict[str, Any], note: Optional[str] = None, promise_context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return self._gm_request_service.mark_gm_free_agent_offer_request_decided(request_id, status, admin, note, promise_context)


    def decide_gm_free_agent_offer_request_command(self, request_id: int, status: str, admin: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        return self._gm_request_service.decide_gm_free_agent_offer_request_command(request_id, status, admin, **kwargs)


    def ensure_free_agent_offer_request_promise_capacity(self, request_id: int, *, bypass_role_limits: bool = False) -> None:
        return self._offer_promise_service.ensure_request_capacity(request_id, bypass_role_limits=bypass_role_limits)


    def list_free_agent_offer_promises(self, session: Dict[str, Any], status: Optional[str] = None) -> Dict[str, Any]:
        return self._offer_promise_service.list_free_agent_offer_promises(session, status)


    def create_free_agent_offer_promise(self, payload: Dict[str, Any], actor: Dict[str, Any], *, bypass_role_limits: bool = False) -> Dict[str, Any]:
        return self._offer_promise_service.create_free_agent_offer_promise(payload, actor, bypass_role_limits=bypass_role_limits)


    def update_free_agent_offer_promise(self, promise_id: int, payload: Dict[str, Any], actor: Dict[str, Any], *, bypass_role_limits: bool = False) -> Optional[Dict[str, Any]]:
        return self._offer_promise_service.update_free_agent_offer_promise(promise_id, payload, actor, bypass_role_limits=bypass_role_limits)


    def update_free_agent_offer_promise_status(self, promise_id: int, status: str, actor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._offer_promise_service.update_free_agent_offer_promise_status(promise_id, status, actor)


    def mark_gm_option_request_decided(self, request_id: int, status: str, admin: Dict[str, Any], note: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.mark_gm_option_request_decided(request_id, status, admin, note)


    def create_user_notification(self, **notification: Any) -> Optional[int]:
        return self._notification_repository.create(**notification)

    def list_user_notifications_for_session(
        self,
        session: Dict[str, Any],
        *,
        unread_only: bool = True,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self._notification_repository.list_for_session(
            session,
            unread_only=unread_only,
            limit=limit,
        )

    def mark_user_notification_read(self, notification_id: int, session: Dict[str, Any]) -> bool:
        return self._notification_repository.mark_read(notification_id, session)
    def create_session(self, token: str, payload: Dict[str, Any], created_at: str, expires_at: int) -> bool:
        return session_repository.create_session(self.connect, token, payload, created_at, expires_at)

    def get_session(self, token: str, now_ts: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return session_repository.get_session(self.connect, token, now_ts)

    def delete_session(self, token: str) -> None:
        session_repository.delete_session(self.connect, token)

    def cleanup_expired_sessions(self, now_ts: Optional[int] = None) -> int:
        return session_repository.cleanup_expired_sessions(self.connect, self._session_cleanup_lock, now_ts)

    def list_teams(self) -> List[Dict[str, Any]]:
        return self._team_repository.list()

    def current_draft_year(self) -> int:
        return self._draft_repository.current_year()

    def list_draft_order(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self._draft_repository.list_order(draft_year)

    def list_draft_pick_ledger(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self._draft_repository.list_pick_ledger(draft_year)

    def create_draft_order_entry(self, payload: Dict[str, Any]) -> int:
        return self._draft_repository.create_order_entry(payload)

    def get_draft_order_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        return self._draft_repository.order_entry(entry_id)

    def list_draft_live(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self._draft_repository.list_live(draft_year)

    def update_draft_live_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._draft_repository.update_live_settings(payload)

    def submit_draft_live_pick(
        self,
        draft_order_id: int,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
        *,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        return self._draft_repository.submit_live_pick(
            draft_order_id, payload, actor, is_admin=is_admin
        )

    def process_draft_results(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self._draft_repository.process_results(draft_year)

    def _attach_option_decisions(self, conn: sqlite3.Connection, players: List[Dict[str, Any]], team_id: int) -> None:
        self._player_repository.attach_option_decisions(conn, players, team_id)

    def get_team(self, code: str, move_season_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return self._team_detail_service.get(code, move_season_year)

    def get_player_record(self, player_id: int) -> Optional[Dict[str, Any]]:
        return self._player_repository.record(player_id)

    def _select_frozen_draft_picks(self, conn: sqlite3.Connection, team_id: int) -> List[Dict[str, Any]]:
        return self._team_repository.select_frozen_draft_picks(conn, team_id)

    def _player_log_summary(self, log: Dict[str, Any], details: Dict[str, Any]) -> str:
        action = str(log.get("action") or "").strip().lower()
        entity = str(log.get("entity") or "").strip().lower()
        if action == "cut" and entity == "player":
            return "Corte registrado"
        if action == "move" and entity == "player":
            target = str(details.get("to_team_code") or log.get("team_code") or "").strip().upper()
            return f"Movimiento a {target}" if target else "Movimiento de equipo"
        if action == "sign" and entity == "free_agent":
            return "Firmado como agente libre"
        if action == "create" and entity == "player":
            return "Jugador creado"
        if action == "delete" and entity == "player":
            return "Jugador eliminado"
        if action == "update" and entity == "player":
            return "Perfil/contrato actualizado"
        if action in {"process", "trade"} and entity == "trade":
            return "Traspaso procesado"
        return " ".join(part for part in [action, entity] if part).strip() or "Movimiento registrado"

    def list_players(
        self,
        include_private: bool = False,
        sync_generated: bool = True,
        include_salary_history: bool = True,
        collect_timings: bool = False,
    ) -> List[Dict[str, Any]]:
        return self._player_catalog_service.list_players(
            include_private=include_private,
            sync_generated=sync_generated,
            include_salary_history=include_salary_history,
            collect_timings=collect_timings,
        )

    def assert_player_identity_integrity(self) -> None:
        self._player_identity_service().assert_integrity()

    def list_gm_history(self, code: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        return self._team_repository.list_gm_history(code)

    def replace_gm_history(self, code: str, entries: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        return self._team_repository.replace_gm_history(code, entries)

    def list_tracker(self, season_year: Optional[int] = None, busy_timeout_ms: int = 5000) -> Dict[str, Any]:
        return self._tracker_service.list(season_year, busy_timeout_ms)

    def list_team_economy(self, season_year: Optional[int] = None) -> Dict[str, Any]:
        return self._settings_repository.list_team_economy(season_year)

    def export_league_workbook(self) -> bytes:
        return self._admin_export_service.export()

    def _owner_admin_import_service(self) -> OwnerAdminImportService:
        return self._owner_admin_import_service_instance

    def preview_owner_economy_csv(self, csv_text: str) -> Dict[str, Any]:
        return self._owner_admin_import_service().preview_owner_economy_csv(csv_text)

    def apply_owner_economy_import(self, records_payload: Any) -> Dict[str, Any]:
        return self._owner_admin_import_service().apply_owner_economy_import(records_payload)

    def preview_owner_office_csv(self, csv_text: str) -> Dict[str, Any]:
        return self._owner_admin_import_service().preview_owner_office_csv(csv_text)

    def apply_owner_office_import(self, records_payload: Any) -> Dict[str, Any]:
        return self._owner_admin_import_service().apply_owner_office_import(records_payload)

    def get_owner_exit_interview(self, code: str, season_year: int) -> Optional[Dict[str, Any]]:
        return self._owner_office_repository.get_owner_exit_interview(code, season_year)

    def start_owner_exit_interview(
        self,
        code: str,
        season_year: int,
        session: Dict[str, Any],
        owner_message: str,
    ) -> Optional[Dict[str, Any]]:
        return self._owner_office_repository.start_owner_exit_interview(
            code, season_year, session, owner_message
        )

    def complete_owner_exit_interview(
        self,
        code: str,
        season_year: int,
        session: Dict[str, Any],
        gm_response: str,
        owner_final_message: str,
        owner_conclusion_message: str,
        trust_delta: int,
    ) -> Optional[Dict[str, Any]]:
        return self._owner_office_repository.complete_owner_exit_interview(
            code, season_year, session, gm_response, owner_final_message,
            owner_conclusion_message, trust_delta,
        )

    def reset_owner_exit_interview(self, code: str, season_year: int) -> bool:
        return self._owner_office_repository.reset_owner_exit_interview(code, season_year)

    def _owner_office_service(
        self,
        interview_composer: Optional[OwnerInterviewCompositionService] = None,
    ) -> OwnerOfficeService:
        return OwnerOfficeService(
            self._owner_office_repository,
            now=now_iso,
            min_year=CAP_FORECAST_MIN_YEAR,
            max_year=CAP_FORECAST_MAX_YEAR,
            forecast_window=CAP_FORECAST_WINDOW,
            objective_options=OWNER_SEASON_OBJECTIVES,
            interview_composer=interview_composer,
        )

    def get_team_owner_office(self, code: str, include_private: bool = False) -> Optional[Dict[str, Any]]:
        return self._owner_office_service().get(code, include_private)

    def update_team_owner_office(self, code: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._owner_office_service().update(code, payload)

    def update_owner_background_url(self, code: str, background_url: str) -> Optional[Dict[str, Any]]:
        return self._owner_office_service().update_background_url(code, background_url)

    def update_owner_background_image(self, code: str, file_bytes: bytes, mime_type: str) -> Optional[Dict[str, Any]]:
        return self._owner_office_service().update_background_image(code, file_bytes, mime_type)

    def get_owner_background_image(self, code: str) -> Optional[tuple[bytes, str]]:
        return self._owner_office_service().get_background_image(code)

    def upsert_team_economy(self, season_year: int, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._settings_repository.upsert_team_economy(season_year, rows)

    def _team_luxury_history(self, conn: sqlite3.Connection, team_id: int, current_year: int) -> List[Dict[str, Any]]:
        return self._team_repository.luxury_history_conn(conn, team_id, current_year)

    def _team_luxury_repeater_for_season(self, conn: sqlite3.Connection, team_id: int, season_year: int) -> bool:
        return self._team_repository.luxury_repeater_conn(conn, team_id, season_year)

    def _team_apron_hard_cap_for_season(self, conn: sqlite3.Connection, team_id: int, season_year: int, fallback: Any = None) -> str:
        return self._team_repository.hard_cap_conn(conn, team_id, season_year, fallback)

    def _team_apron_hard_caps(self, conn: sqlite3.Connection, team_id: int, current_year: int, fallback: Any = None) -> List[Dict[str, Any]]:
        return self._team_repository.hard_caps_conn(conn, team_id, current_year, fallback)

    def _update_team_apron_hard_cap_conn(self, conn: sqlite3.Connection, code: str, season_year: int, hard_cap: Any) -> bool:
        return self._team_repository.update_hard_cap_conn(conn, code, season_year, hard_cap)

    def update_team_apron_hard_cap(self, code: str, season_year: int, hard_cap: Any) -> bool:
        return self._team_repository.update_hard_cap(code, season_year, hard_cap)

    def _team_season_summaries(
        self,
        conn: sqlite3.Connection,
        team: Dict[str, Any],
        players: List[Dict[str, Any]],
        assets: List[Dict[str, Any]],
        dead_contracts: List[Dict[str, Any]],
        settings: Dict[str, str],
    ) -> Dict[str, Dict[str, Any]]:
        current_year = parse_int(settings.get("current_year")) or 2025
        start_year = max(CAP_FORECAST_MIN_YEAR, min(CAP_FORECAST_MAX_YEAR, current_year))
        team_id = parse_int(team.get("id"))
        summaries: Dict[str, Dict[str, Any]] = {}
        for season_year in range(start_year, CAP_FORECAST_MAX_YEAR + 1):
            repeater = self._team_luxury_repeater_for_season(conn, int(team_id), season_year) if team_id is not None else False
            fallback_hard_cap = team.get("apron_hard_cap") if season_year == current_year else None
            hard_cap = self._team_apron_hard_cap_for_season(conn, int(team_id), season_year, fallback_hard_cap) if team_id is not None else ""
            summary = calculate_team_cap_summary(
                team,
                players,
                assets,
                dead_contracts,
                settings,
                season_year=season_year,
                luxury_repeater=repeater,
                apron_hard_cap=hard_cap,
            )
            summaries[str(season_year)] = summary
        return summaries

    def _official_generated_exception_assets(
        self,
        assets: List[Dict[str, Any]],
        season_year: int,
    ) -> List[Dict[str, Any]]:
        return [
            asset
            for asset in assets
            if asset.get("asset_type") == "exception"
            and parse_int(asset.get("generated_exception_season")) == int(season_year)
            and str(asset.get("generated_exception_key") or "").strip() in GENERATED_OFFSEASON_EXCEPTION_KEYS
        ]

    def _offseason_exception_estimate_from_summary(
        self,
        summary: Dict[str, Any],
        assets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        season_year = parse_int(summary.get("current_year")) or 2025
        salary_cap = float(summary.get("salary_cap") or 0.0)
        first_apron = float(summary.get("first_apron") or 0.0)
        second_apron = float(summary.get("second_apron") or 0.0)
        raw_cap_space = float(summary.get("room_to_cap") or 0.0)
        apron_account = float(summary.get("apron_account") or 0.0)
        amounts = offseason_exception_amounts(salary_cap)
        official = self._official_generated_exception_assets(assets, season_year)

        def items(keys: List[str]) -> List[Dict[str, Any]]:
            return [offseason_exception_item(key, amounts.get(key, 0.0)) for key in keys]

        def split_by_apron_room(keys: List[str], apron_limit: float) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
            apron_room = float(apron_limit or 0.0) - float(apron_account or 0.0)
            available: List[Dict[str, Any]] = []
            blocked: List[Dict[str, Any]] = []
            for item in items(keys):
                if float(item.get("amount") or 0.0) <= max(0.0, apron_room):
                    available.append(item)
                else:
                    item = {**item, "ineligible_reason": "insufficient_apron_room", "apron_room": round(max(0.0, apron_room))}
                    blocked.append(item)
            return available, blocked

        def apron_room(apron_limit: float) -> float:
            return max(0.0, float(apron_limit or 0.0) - float(apron_account or 0.0))

        def insufficient_apron_item(key: str, room: float, apron: str) -> Dict[str, Any]:
            item = offseason_exception_item(key, amounts.get(key, 0.0))
            return {
                **item,
                "ineligible_reason": "insufficient_apron_room",
                "apron_room": round(max(0.0, room)),
                "apron": apron,
            }

        def capped_exception_item(key: str, room: float, apron: str) -> Dict[str, Any]:
            item = offseason_exception_item(key, amounts.get(key, 0.0))
            full_amount = float(item.get("amount") or 0.0)
            capped_amount = min(full_amount, max(0.0, room))
            if capped_amount < full_amount:
                item = {
                    **item,
                    "amount": round(capped_amount),
                    "full_amount": round(full_amount),
                    "capped_by": apron,
                    "apron_room": round(max(0.0, room)),
                }
            return item

        def below_first_apron_exception_availability() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
            first_room = apron_room(first_apron)
            second_room = apron_room(second_apron)
            tmle_amount = float(amounts.get("tmle") or 0.0)
            available: List[Dict[str, Any]] = []
            blocked: List[Dict[str, Any]] = []
            local_notes: List[str] = []

            if first_room >= tmle_amount:
                available.append(capped_exception_item("ntmle", first_room, "first_apron"))
                bae_item = offseason_exception_item("bae", amounts.get("bae", 0.0))
                if float(bae_item.get("amount") or 0.0) <= first_room:
                    available.append(bae_item)
                else:
                    blocked.append(insufficient_apron_item("bae", first_room, "first_apron"))
                if any(item.get("capped_by") for item in available):
                    local_notes.append("La NTMLE se muestra limitada al espacio disponible hasta el 1er apron.")
            else:
                blocked.append(insufficient_apron_item("ntmle", first_room, "first_apron"))
                blocked.append(insufficient_apron_item("bae", first_room, "first_apron"))
                if tmle_amount <= second_room:
                    available.append(offseason_exception_item("tmle", amounts.get("tmle", 0.0)))
                    local_notes.append(
                        "El espacio hasta el 1er apron es inferior a la TMLE; se muestra la TMLE como alternativa."
                    )
                else:
                    blocked.append(insufficient_apron_item("tmle", second_room, "second_apron"))
            return available, blocked, local_notes

        notes: List[str] = []
        paths: List[Dict[str, Any]] = []
        eligible: List[Dict[str, Any]] = []
        ineligible: List[Dict[str, Any]] = []
        operating_mode = "above_second_apron"
        status = "estimate"

        ntmle_amount = float(amounts.get("ntmle") or 0.0)
        if raw_cap_space > 0 and raw_cap_space < ntmle_amount:
            over_cap_eligible, over_cap_blocked, over_cap_notes = below_first_apron_exception_availability()
            operating_mode = "choice_pending"
            status = "choice_pending"
            paths = [
                {
                    "key": "room",
                    "label": "Usar espacio salarial",
                    "description": "Renuncia las excepciones over-the-cap y opera como equipo con espacio.",
                    "eligible": items(["room_mle"]),
                },
                {
                    "key": "over_cap",
                    "label": "Mantener excepciones",
                    "description": "Pierde el espacio salarial y opera como equipo over-the-cap.",
                    "eligible": over_cap_eligible,
                    "ineligible": over_cap_blocked,
                },
            ]
            ineligible = over_cap_blocked
            notes.append(
                "El equipo tiene espacio positivo, pero menor que la NTMLE. Admin debe decidir si usa cap space o mantiene excepciones."
            )
            notes.extend(over_cap_notes)
            notes.append("La BAE queda sujeta a revisar si fue usada la temporada anterior.")
        elif raw_cap_space > 0:
            operating_mode = "room"
            eligible = items(["room_mle"])
            ineligible = items(["ntmle", "bae", "tmle"])
            notes.append("Equipo proyectado con espacio salarial: opera con Room MLE si mantiene ese camino.")
        elif apron_account >= second_apron:
            operating_mode = "above_second_apron"
            eligible = []
            ineligible = items(["room_mle", "ntmle", "bae", "tmle"])
            notes.append("Equipo proyectado por encima del 2do apron: sin excepciones principales disponibles.")
        elif apron_account >= first_apron:
            operating_mode = "above_first_below_second"
            eligible, blocked_by_apron = split_by_apron_room(["tmle"], second_apron)
            ineligible = items(["room_mle", "ntmle", "bae"]) + blocked_by_apron
            if eligible:
                notes.append("El uso de la TMLE genera hard cap en el 2do apron.")
            else:
                notes.append("La TMLE no cabe completa bajo el 2do apron.")
        else:
            operating_mode = "over_cap_below_first"
            eligible, blocked_by_apron, below_first_notes = below_first_apron_exception_availability()
            eligible_keys = {str(item.get("key") or "").strip() for item in eligible}
            ineligible = items(["room_mle"]) + ([] if "tmle" in eligible_keys else items(["tmle"])) + blocked_by_apron
            if any(str(item.get("key") or "").strip() in {"ntmle", "bae"} for item in eligible):
                notes.append("El uso de la NTMLE o BAE genera hard cap en el 1er apron.")
            if any(str(item.get("key") or "").strip() == "tmle" for item in eligible):
                notes.append("El uso de la TMLE genera hard cap en el 2do apron.")
            notes.extend(below_first_notes)
            notes.append("La BAE queda sujeta a revisar si fue usada la temporada anterior.")

        return {
            "season_year": season_year,
            "season_label": season_label(season_year),
            "status": status,
            "operating_mode": operating_mode,
            "raw_cap_space": round(raw_cap_space),
            "cap_figure": round(float(summary.get("cap_figure") or 0.0)),
            "apron_account": round(apron_account),
            "salary_cap": round(salary_cap),
            "first_apron": round(first_apron),
            "second_apron": round(second_apron),
            "values": {key: round(value) for key, value in amounts.items()},
            "eligible": eligible,
            "ineligible": ineligible,
            "paths": paths,
            "notes": notes,
            "official_generated": bool(official),
            "official_exceptions": [
                {
                    "id": asset.get("id"),
                    "key": asset.get("generated_exception_key"),
                    "label": asset.get("label"),
                    "amount": round(float(asset.get("amount_num") or 0.0)),
                    "exception_type": asset.get("exception_type"),
                }
                for asset in official
            ],
        }

    def _team_exception_estimates(
        self,
        season_summaries: Dict[str, Dict[str, Any]],
        assets: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        return {
            str(season_year): self._offseason_exception_estimate_from_summary(summary, assets)
            for season_year, summary in season_summaries.items()
        }

    def _cartera_exception_paths(self, estimate: Dict[str, Any], target_amount: float) -> List[Dict[str, Any]]:
        return self._cartera_service.exception_paths(estimate, target_amount)


    FREE_AGENT_TEAM_APPEAL_COLUMNS = FreeAgentAppealService.FREE_AGENT_TEAM_APPEAL_COLUMNS
    FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS = FreeAgentAppealService.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS

    def preview_free_agent_team_appeal_import(self, rows: List[List[str]]) -> Dict[str, Any]:
        return self._free_agent_appeal_service.preview(rows)

    def apply_free_agent_team_appeal_import(self, records_payload: Any) -> Dict[str, Any]:
        return self._free_agent_appeal_service.apply(records_payload)

    def list_free_agent_team_appeal(self) -> Dict[str, Any]:
        return self._free_agent_appeal_service.list()
    def record_free_agent_interest(self, free_agent_id: Any, team_code: Any, payload: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
        return self._free_agency_repository.record_interest(free_agent_id, team_code, payload, session)


    def set_free_agent_team_ruleout(
        self,
        free_agent_id: Any,
        team_code: Any,
        session: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self._free_agency_repository.set_ruleout(free_agent_id, team_code, session)

    def delete_free_agent_team_ruleout(
        self,
        free_agent_id: Any,
        team_code: Any,
        session: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self._free_agency_repository.delete_ruleout(free_agent_id, team_code, session)

    def set_gm_free_agent_spending_limit(
        self,
        team_code: Any,
        amount_millions: Any,
        session: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._free_agency_repository.set_spending_limit(team_code, amount_millions, session)

    def list_gm_free_agent_spending_limits(self) -> List[Dict[str, Any]]:
        return self._free_agency_repository.list_spending_limits()

    def get_gm_minimum_targets(self, user_id: Any, team_code: Any = None) -> Dict[str, Any]:
        return self._gm_minimum_target_service.get(user_id, team_code)

    def set_gm_minimum_targets(self, user_id: Any, team_code: Any, targets: Any) -> Dict[str, Any]:
        return self._gm_minimum_target_service.set(user_id, team_code, targets)

    def remove_admin_gm_minimum_target(self, user_id: Any, rank: Any) -> Dict[str, Any]:
        return self._gm_minimum_target_service.remove(user_id, rank)

    def set_gm_minimum_target_handicap(self, team_code: Any, handicap: Any) -> Dict[str, Any]:
        return self._gm_minimum_target_service.set_handicap(team_code, handicap)

    def list_admin_gm_minimum_target_order(self) -> List[Dict[str, Any]]:
        return self._gm_minimum_target_service.score_order()

    @staticmethod
    def _minimum_target_birds_bonus(age: int, team_code: Any, rights_team_code: Any) -> int:
        """Compatibility wrapper for callers of the former LeagueDB helper."""
        return GMMinimumTargetService._birds_bonus(age, team_code, rights_team_code)

    def _team_depth_chart_payload(self, conn: sqlite3.Connection, team_id: int) -> Dict[str, Any]:
        return self._depth_chart_repository.payload(conn, team_id)

    def set_team_depth_chart(self, team_code: Any, entries: Any) -> Dict[str, Any]:
        return self._depth_chart_repository.set(team_code, entries)

    def list_gm_office(self, team_code: Any) -> Dict[str, Any]:
        return self._gm_office_service.get(team_code)

    def cancel_gm_free_agent_offer_request(self, request_id: int, team_code: str, actor: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return self._gm_request_repository.cancel_gm_free_agent_offer_request(request_id, team_code, actor)


    def list_cartera_clients_for_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return self._cartera_service.list_clients(session)


    def generate_offseason_exceptions(
        self, season_year: int, team_codes: Optional[List[str]] = None,
        choices: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        return self._offseason_exception_service.generate(season_year, team_codes, choices)


    def _hard_cap_from_trade_issue(self, issue: Dict[str, Any]) -> str:
        raw = normalize_apron_hard_cap(issue.get("hardCap") or issue.get("hard_cap"))
        if raw:
            return raw
        message = str(issue.get("message") or "").lower()
        if "1er apron" in message or "1st apron" in message or "first apron" in message:
            return "first"
        if "2do apron" in message or "2nd apron" in message or "second apron" in message:
            return "second"
        return ""

    def apply_trade_hard_cap_triggers(
        self,
        validation: Dict[str, Any],
        season_year: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        applied: List[Dict[str, Any]] = []
        parsed_season = parse_int(season_year)
        if parsed_season is None:
            return applied
        for issue in validation.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            if issue.get("rule") != "hard_cap_trigger":
                continue
            team_code = normalize_team_code(issue.get("teamCode"))
            hard_cap = self._hard_cap_from_trade_issue(issue)
            if not team_code or hard_cap not in {"first", "second"}:
                continue
            changed = (
                self._update_team_apron_hard_cap_conn(conn, team_code, int(parsed_season), hard_cap)
                if conn is not None
                else self.update_team_apron_hard_cap(team_code, int(parsed_season), hard_cap)
            )
            if changed:
                applied.append(
                    {
                        "team_code": team_code,
                        "season_year": int(parsed_season),
                        "hard_cap": hard_cap,
                    }
                )
        return applied

    def _player_identity_service(self) -> PlayerIdentityService:
        return PlayerIdentityService(self, contract_seasons=PLAYER_CONTRACT_SEASONS)

    def _sync_free_agency_generated_rows_if_needed(self, conn: sqlite3.Connection, payload: Dict[str, Any]) -> None:
        self._player_identity_service().synchronize_for_player_update(conn, payload)

    def update_player(self, player_id: int, payload: Dict[str, Any]) -> bool:
        return self._player_repository.update(player_id, payload)


    def update_player_profile(self, profile_id: int, payload: Dict[str, Any]) -> bool:
        return self._player_identity_service().update_profile(profile_id, payload)

    def delete_player_profile(self, profile_id: int) -> Dict[str, Any]:
        return self._player_identity_service().delete_profile(profile_id)



    def merge_player_profiles(self, source_profile_id: int, target_profile_id: int) -> Dict[str, Any]:
        return self._player_identity_service().merge_profiles(source_profile_id, target_profile_id)

    def create_player_transaction(self, profile_id: int, payload: Dict[str, Any]) -> Optional[int]:
        return self._player_repository.create_transaction(profile_id, payload)

    def create_player_salary_history(self, profile_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._player_repository.create_salary_history(profile_id, payload)

    def move_player(self, player_id: int, to_team_code: str) -> bool:
        return self._player_repository.move(player_id, to_team_code)

    def create_player(
        self,
        team_code: str,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[int]:
        return self._player_repository.create(team_code, payload, conn)

    def remove_player_from_roster(self, player_id: int) -> Optional[Dict[str, Any]]:
        return self._player_repository.remove_from_roster(player_id)


    def _player_contract_snapshot_payload(self, player: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        keys = [
            "profile_id",
            "name",
            "position",
            "bird_rights",
            "rating",
            "years_left",
            "notes",
            "reference_image_url",
            "profile_notes",
            "experience_years",
            "signed_as_free_agent",
            "provisional_amounts",
            "partially_guaranteed",
        ]
        for key in keys:
            payload[key] = player.get(key)
        for season in PLAYER_CONTRACT_SEASONS:
            for suffix in [
                "text",
                "guaranteed_text",
                "provisional",
                "partially_guaranteed",
                "note",
                "note_text",
            ]:
                field = f"salary_{season}_{suffix}"
                if field in player:
                    payload[field] = player.get(field)
            option_field = f"option_{season}"
            if option_field in player:
                payload[option_field] = player.get(option_field)
        return payload

    def _normalize_cut_options(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = payload or {}
        overrides_raw = payload.get("dead_cap_overrides") or payload.get("buyout_dead_cap") or {}
        overrides: Dict[str, str] = {}
        if isinstance(overrides_raw, dict):
            for key, value in overrides_raw.items():
                season = parse_int(key)
                if season is None:
                    continue
                text = format_salary_amount_text(value)
                overrides[str(season)] = text or ""
        return {
            "buyout": 1 if parse_bool(payload.get("buyout")) else 0,
            "stretch": 1 if parse_bool(payload.get("stretch")) else 0,
            "dead_cap_overrides": overrides,
        }

    def _cut_dead_cap_schedule(
        self,
        payload: Dict[str, Any],
        cut_settings: Optional[Dict[str, Any]],
        *,
        current_year: int,
    ) -> tuple[Dict[int, Optional[str]], Optional[str]]:
        cut_settings = cut_settings or {}
        buyout = parse_bool(cut_settings.get("buyout"))
        stretch = parse_bool(cut_settings.get("stretch"))
        overrides = cut_settings.get("dead_cap_overrides") if isinstance(cut_settings.get("dead_cap_overrides"), dict) else {}

        base_schedule: Dict[int, float] = {}
        for season in PLAYER_CONTRACT_SEASONS:
            raw_value = overrides.get(str(season)) if buyout and str(season) in overrides else payload.get(f"salary_{season}_text")
            amount = parse_salary_amount(raw_value)
            if amount is not None and amount > 0:
                base_schedule[int(season)] = float(amount)

        if not stretch:
            return ({season: format_salary_amount_text(base_schedule.get(season)) for season in PLAYER_CONTRACT_SEASONS}, None)

        before_august_31 = date.today() <= date(date.today().year, 8, 31)
        stretch_source_years = [
            season for season, amount in sorted(base_schedule.items())
            if amount > 0 and season >= int(current_year) and (before_august_31 or season > int(current_year))
        ]
        if not stretch_source_years:
            return ({season: format_salary_amount_text(base_schedule.get(season)) for season in PLAYER_CONTRACT_SEASONS}, "stretch sin importes futuros")

        stretched_total = sum(base_schedule.get(season, 0.0) for season in stretch_source_years)
        stretch_year_count = len(stretch_source_years) * 2 + 1
        annual_stretch = stretched_total / stretch_year_count if stretch_year_count > 0 else 0.0
        first_stretch_year = int(current_year) if before_august_31 else int(current_year) + 1
        last_stretch_year = first_stretch_year + stretch_year_count - 1

        final_schedule: Dict[int, float] = {}
        if not before_august_31 and base_schedule.get(int(current_year), 0) > 0:
            final_schedule[int(current_year)] = float(base_schedule[int(current_year)])
        for season in range(first_stretch_year, last_stretch_year + 1):
            final_schedule[season] = final_schedule.get(season, 0.0) + annual_stretch

        note = f"stretch hasta {last_stretch_year}" if last_stretch_year > max(PLAYER_CONTRACT_SEASONS) else None
        return ({season: format_salary_amount_text(final_schedule.get(season)) for season in PLAYER_CONTRACT_SEASONS}, note)

    def _player_is_ten_day_contract(self, player: Dict[str, Any]) -> bool:
        raw = " ".join(
            str(value or "").strip().upper()
            for value in [player.get("bird_rights"), player.get("contract_type"), player.get("notes")]
            if value not in (None, "")
        )
        normalized = re.sub(r"[^A-Z0-9]+", "", raw)
        return normalized in {"10D", "10DAY", "10DIAS", "10DIAS"} or "10DAY" in normalized or "10DIAS" in normalized

    def process_expired_waivers_command(self) -> Dict[str, Any]:
        return self._waiver_repository.process_expired()

    def process_expired_waivers(self) -> Dict[str, Any]:
        return self._waiver_repository.process_expired()

    def _waiver_salary_for_season(self, waiver: Dict[str, Any], season_year: int) -> float:
        try:
            payload = json.loads(waiver.get("contract_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        salary = parse_amount_like(payload.get(f"salary_{int(season_year)}_text"))
        if salary is not None:
            return float(salary)
        for season in PLAYER_CONTRACT_SEASONS:
            if season < int(season_year):
                continue
            salary = parse_amount_like(payload.get(f"salary_{season}_text"))
            if salary is not None:
                return float(salary)
        return 0.0

    def _team_standard_roster_count(self, team_data: Dict[str, Any]) -> int:
        return sum(
            1
            for player in team_data.get("players") or []
            if not is_two_way_player(player) and not is_exhibit10_player(player)
        )

    def _waiver_claim_eligibility(
        self,
        team_code: str,
        waiver: Dict[str, Any],
        *,
        season_year: Optional[int] = None,
        contingent_cut_player_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        settings = self.get_settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        selected_year = parse_int(season_year) or current_year
        team_data = self.get_team(team_code, move_season_year=selected_year)
        if not team_data:
            return {"eligible": False, "reason": "team_not_found"}
        if str(waiver.get("from_team_code") or "").upper() == str(team_code or "").upper():
            return {"eligible": False, "reason": "own_player"}
        max_standard = ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT if parse_bool(settings.get("free_agency_mode")) else ROSTER_STANDARD_MAX_DEFAULT
        standard_count = self._team_standard_roster_count(team_data)
        needs_cut = standard_count >= int(max_standard)
        if needs_cut and contingent_cut_player_id is None:
            return {
                "eligible": False,
                "reason": "roster_spot_required",
                "requires_contingent_cut": True,
                "standard_count": standard_count,
                "standard_max": int(max_standard),
            }
        if contingent_cut_player_id is not None:
            cut_row = next((p for p in team_data.get("players") or [] if int(p.get("id") or 0) == int(contingent_cut_player_id)), None)
            if not cut_row:
                return {"eligible": False, "reason": "contingent_cut_not_found"}
        salary = self._waiver_salary_for_season(waiver, selected_year)
        summary = (team_data.get("season_summaries") or {}).get(str(selected_year)) or team_data.get("summary") or {}
        cap_space = float(summary.get("room_to_cap") or 0.0)
        if salary <= cap_space:
            return {"eligible": True, "path": "cap_space", "salary": round(salary), "cap_space": round(cap_space)}
        estimate = self._offseason_exception_estimate_from_summary(summary, team_data.get("assets") or [])
        exception_paths = self._cartera_exception_paths(estimate, salary)
        if exception_paths:
            return {
                "eligible": True,
                "path": "exception",
                "salary": round(salary),
                "exceptions": exception_paths,
                "cap_space": round(cap_space),
            }
        return {
            "eligible": False,
            "reason": "salary_absorption_required",
            "salary": round(salary),
            "cap_space": round(cap_space),
        }

    def list_waivers(self, session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._waiver_repository.list(session)

    def create_waiver_claim(
        self,
        waiver_player_id: int,
        team_code: str,
        payload: Dict[str, Any],
        requester: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._waiver_repository.create_claim(
            waiver_player_id,
            team_code,
            payload,
            requester,
        )

    def list_waiver_claim_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._waiver_repository.list_claim_requests(status=status)

    def decide_waiver_claim_request(
        self,
        request_id: int,
        decision: str,
        admin: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._waiver_repository.decide_claim_request(
            request_id,
            decision,
            admin,
            note,
        )





    def ensure_renounced_bird_rights_free_agent(
        self,
        player: Dict[str, Any],
        season_year: int,
        rights_value: str,
    ) -> Optional[int]:
        return self._free_agency_repository.ensure_renounced_rights_free_agent(player, season_year, rights_value)





    def list_free_agents(self) -> List[Dict[str, Any]]:
        return self._free_agency_repository.list_free_agents()



    def get_free_agent(self, free_agent_id: int) -> Optional[Dict[str, Any]]:
        return self._free_agency_repository.free_agent(free_agent_id)


    def create_free_agent(self, payload: Dict[str, Any]) -> Optional[int]:
        return self._free_agency_repository.create_free_agent(payload)

    def bulk_create_free_agents(self, raw_names: Any) -> Dict[str, Any]:
        return self._free_agency_repository.bulk_create_free_agents(raw_names)

    def preview_free_agent_agent_import(self, rows: List[List[str]]) -> Dict[str, Any]:
        return self._free_agent_agent_import_service.preview(rows)

    def apply_free_agent_agent_import(self, records_payload: Any) -> Dict[str, Any]:
        return self._free_agent_agent_import_service.apply(records_payload)
    def update_free_agent(self, free_agent_id: int, payload: Dict[str, Any]) -> bool:
        return self._free_agency_repository.update_free_agent(free_agent_id, payload)

    def _cleanup_gm_minimum_targets_for_free_agent_ids_conn(
        self,
        conn: sqlite3.Connection,
        free_agent_ids: Any,
    ) -> int:
        return self._free_agency_repository._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, free_agent_ids)

    def delete_free_agent(self, free_agent_id: int, record_transaction: bool = True) -> bool:
        return self._free_agency_repository.delete_free_agent(free_agent_id, record_transaction)

    def _approved_option_decision_conn(
        self,
        conn: sqlite3.Connection,
        player_id: Any,
        option_field: str,
    ) -> Optional[sqlite3.Row]:
        return self._free_agency_repository._approved_option_decision(conn, player_id, option_field)

    def _player_row_has_accepted_rights_option_conn(
        self,
        conn: Optional[sqlite3.Connection],
        player: sqlite3.Row,
        season: int,
        option_marker: str,
    ) -> bool:
        if conn is None or option_marker not in {"QO", "GAP"}:
            return False
        decision = self._approved_option_decision_conn(conn, player["id"], f"option_{season}")
        if not decision:
            return False
        return (
            str(decision["status"] or "").strip().lower() == "approved"
            and str(decision["action"] or "").strip().lower() == "accepted"
            and str(decision["option_value"] or "").strip().upper() == option_marker
        )

    def _player_row_is_retained_rights_only(
        self,
        player: sqlite3.Row,
        current_year: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> bool:
        rights_markers = {"NB", "EB", "FB", "QO", "GAP"}
        for season in PLAYER_CONTRACT_SEASONS:
            if season < int(current_year):
                continue
            salary_text = str(player[f"salary_{season}_text"] or "").strip()
            salary_marker = salary_text.upper()
            option_marker = str(player[f"option_{season}"] or "").strip().upper()
            accepted_rights_option = self._player_row_has_accepted_rights_option_conn(
                conn,
                player,
                season,
                option_marker,
            )
            salary_num = parse_float(player[f"salary_{season}_num"])
            if salary_num is not None and abs(float(salary_num)) > 0 and not accepted_rights_option:
                return False
            parsed_salary_text = parse_amount_like(salary_text)
            if parsed_salary_text is not None and abs(float(parsed_salary_text)) > 0 and not accepted_rights_option:
                return False
            if salary_text and salary_text != "-" and salary_marker not in rights_markers:
                if not accepted_rights_option:
                    return False
            if option_marker and option_marker not in rights_markers:
                return False
        return True



    def sign_free_agent(self, free_agent_id: int, team_code: str, payload: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
        if conn is not None:
            return self._free_agency_repository._sign_free_agent_conn(conn, free_agent_id, team_code, payload)
        return self._free_agency_repository.sign(free_agent_id, team_code, payload)




    def cut_player(self, player_id: int, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        return self._waiver_repository.cut_player(player_id, payload)

    def create_asset(self, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        return self._asset_repository.create_asset(team_code, payload)

    def update_asset(self, asset_id: int, payload: Dict[str, Any]) -> bool:
        return self._asset_repository.update_asset(asset_id, payload)

    def create_dead_contract(self, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        return self._asset_repository.create_dead_contract(team_code, payload)

    def update_dead_contract(self, dead_contract_id: int, payload: Dict[str, Any]) -> bool:
        return self._asset_repository.update_dead_contract(dead_contract_id, payload)

    def delete_dead_contract(self, dead_contract_id: int) -> bool:
        return self._asset_repository.delete_dead_contract(dead_contract_id)

    def delete_asset(self, asset_id: int) -> bool:
        return self._asset_repository.delete_asset(asset_id)


    def _upsert_team_move_log(
        self,
        conn: sqlite3.Connection,
        *,
        team_id: int,
        season_year: int,
        bucket: str,
        delta: int,
        source_type: str,
        source_ref: Optional[str],
        note: Optional[str],
        details: Optional[Dict[str, Any]],
    ) -> None:
        self._trade_repository.upsert_team_move_log(
            conn, team_id=team_id, season_year=season_year, bucket=bucket, delta=delta,
            source_type=source_type, source_ref=source_ref, note=note, details=details,
        )


    def adjust_team_move_remaining(
        self,
        team_code: str,
        season_year: int,
        bucket: str,
        target_remaining: int,
        actor_note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._trade_repository.adjust_team_move_remaining(
            team_code, season_year, bucket, target_remaining, actor_note
        )
































    def _trade_service(self) -> TradeService:
        return TradeService(self._trade_repository)

    def validate_trade_machine(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._trade_service().validate(payload)

    def trade_validation_from_process_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._trade_service().validate_process_payload(payload)

    def process_trade_from_payload(
        self,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._trade_repository.process_from_payload(payload, conn=conn)

    def process_trade_command(self, payload: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        return self._trade_service().process_command(payload, **kwargs)

    def process_trade(self, *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return self._trade_repository.process_legacy(*args, **kwargs)

    def log_admin_action(
        self,
        actor_email: Optional[str],
        actor_name: Optional[str],
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        team_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        actor_role: Optional[str] = None,
        actor_user_id: Optional[int] = None,
        request_id: Optional[str] = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
        team_codes: Optional[List[str]] = None,
        player_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._audit_log_service().record(
            AuditEvent(
                actor_email=actor_email,
                actor_name=actor_name,
                actor_role=actor_role,
                actor_user_id=actor_user_id,
                request_id=request_id,
                method=method,
                path=path,
                action=action,
                entity=entity,
                entity_id=entity_id,
                team_code=team_code,
                team_codes=team_codes or (),
                player_id=player_id,
                profile_id=profile_id,
                before=before,
                after=after,
                details=details or {},
            )
        )

    def list_admin_logs(
        self,
        action: Optional[str] = None,
        entity: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._audit_log_service().list(action=action, entity=entity, limit=limit)


class Handler(SimpleHTTPRequestHandler):
    db: LeagueDB = None  # type: ignore
    asset_version = static_asset_version()

    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    admin_emails = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    gm_accounts = parse_gm_account_map(
        os.getenv("GM_ACCOUNTS")
        or os.getenv("GM_EMAILS")
        or os.getenv("GM_EMAIL_MAP")
        or ""
    )
    session_ttl_seconds = max(300, parse_int(os.getenv("SESSION_TTL_SECONDS")) or 28800)
    cookie_secure_policy = str(os.getenv("COOKIE_SECURE", "auto")).strip().lower() or "auto"
    cookie_same_site = normalize_same_site(os.getenv("COOKIE_SAMESITE", "Lax"))
    cookie_domain = str(os.getenv("COOKIE_DOMAIN", "")).strip() or None
    allowed_origins = parse_allowed_origins(os.getenv("ALLOWED_ORIGINS", ""))

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    discord_bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    discord_api_base_url = os.getenv("DISCORD_API_BASE_URL", "https://discord.com/api/v10").rstrip("/")
    public_base_url = (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("APP_BASE_URL")
        or os.getenv("SITE_BASE_URL")
        or ""
    ).strip().rstrip("/")
    discord_press_channel_id = re.sub(
        r"\D+",
        "",
        os.getenv("DISCORD_PRESS_CHANNEL_ID", "654717136379314196"),
    )
    discord_free_agent_offers_webhook_url = os.getenv("DISCORD_FREE_AGENT_OFFERS_WEBHOOK_URL", "").strip()
    discord_free_agent_offers_forum_tag_ids = [
        re.sub(r"\D+", "", value)
        for value in os.getenv("DISCORD_FREE_AGENT_OFFERS_FORUM_TAG_IDS", "").split(",")
        if re.sub(r"\D+", "", value)
    ][:5]
    discord_free_agent_offers_role_id = re.sub(
        r"\D+",
        "",
        os.getenv("DISCORD_FREE_AGENT_OFFERS_ROLE_ID", "485913691045494785"),
    )
    discord_role_id = os.getenv("DISCORD_NOTIFY_ROLE_ID", "486604867293544458").strip()
    discord_notifications_enabled = str(os.getenv("DISCORD_NOTIFICATIONS_ENABLED", "true")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    discord_timeout_seconds = max(1, parse_int(os.getenv("DISCORD_WEBHOOK_TIMEOUT_SECONDS")) or 5)
    discord_image_notifications_enabled = str(
        os.getenv("DISCORD_IMAGE_NOTIFICATIONS_ENABLED", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    openai_text_timeout_seconds = max(10, parse_int(os.getenv("OPENAI_TEXT_TIMEOUT_SECONDS")) or 45)
    openai_image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip() or "gpt-image-2"
    openai_image_size = os.getenv("OPENAI_IMAGE_SIZE", "1536x1024").strip() or "1536x1024"
    openai_image_quality = os.getenv("OPENAI_IMAGE_QUALITY", "high").strip() or "high"
    openai_image_format = os.getenv("OPENAI_IMAGE_FORMAT", "jpeg").strip().lower() or "jpeg"
    openai_image_timeout_seconds = max(10, parse_int(os.getenv("OPENAI_IMAGE_TIMEOUT_SECONDS")) or 120)
    openai_reference_image_timeout_seconds = max(
        5,
        parse_int(os.getenv("OPENAI_REFERENCE_IMAGE_TIMEOUT_SECONDS")) or 20,
    )
    openai_reference_image_max_bytes = max(
        250_000,
        parse_int(os.getenv("OPENAI_REFERENCE_IMAGE_MAX_BYTES")) or 6_000_000,
    )

    pending_oauth_states: Dict[str, int] = {}
    login_attempts: Dict[str, Dict[str, Any]] = {}
    sensitive_attempts: Dict[str, Dict[str, Any]] = {}
    login_window_seconds = max(60, parse_int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS")) or 600)
    login_max_attempts = max(1, parse_int(os.getenv("LOGIN_RATE_LIMIT_MAX_ATTEMPTS")) or 5)
    login_block_seconds = max(60, parse_int(os.getenv("LOGIN_RATE_LIMIT_BLOCK_SECONDS")) or 900)
    oauth_state_ttl_seconds = max(60, parse_int(os.getenv("OAUTH_STATE_TTL_SECONDS")) or 600)
    oauth_start_window_seconds = max(60, parse_int(os.getenv("OAUTH_START_RATE_LIMIT_WINDOW_SECONDS")) or 600)
    oauth_start_max_attempts = max(1, parse_int(os.getenv("OAUTH_START_RATE_LIMIT_MAX_ATTEMPTS")) or 20)
    sensitive_window_seconds = max(10, parse_int(os.getenv("SENSITIVE_RATE_LIMIT_WINDOW_SECONDS")) or 60)
    sensitive_max_requests = max(10, parse_int(os.getenv("SENSITIVE_RATE_LIMIT_MAX_REQUESTS")) or 600)
    session_cleanup_interval_seconds = max(30, parse_int(os.getenv("SESSION_CLEANUP_INTERVAL_SECONDS")) or 120)
    _last_session_cleanup_ts = 0

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    @property
    def app(self) -> ApplicationContainer:
        container = getattr(self, "_application_container", None)
        if container is None:
            container = ApplicationContainer(
                self.db,
                ApplicationConfig(
                    contract_seasons=tuple(PLAYER_CONTRACT_SEASONS),
                    contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
                    contract_max_start_year=PLAYER_CONTRACT_MAX_START_YEAR,
                    cap_forecast_min_year=CAP_FORECAST_MIN_YEAR,
                    cap_forecast_max_year=CAP_FORECAST_MAX_YEAR,
                    unrestricted_free_agent_type=FREE_AGENT_TYPE_UNRESTRICTED,
                    cap_hold_source=FREE_AGENT_SOURCE_CAP_HOLD,
                    google_client_id=self.google_client_id,
                    google_client_secret=self.google_client_secret,
                    google_redirect_uri=self.google_redirect_uri,
                    admin_emails=frozenset(self.admin_emails),
                    gm_accounts=self.gm_accounts,
                    discord_webhook_url=self.discord_webhook_url,
                    discord_bot_token=self.discord_bot_token,
                    discord_api_base_url=self.discord_api_base_url,
                    discord_timeout_seconds=self.discord_timeout_seconds,
                    discord_press_channel_id=self.discord_press_channel_id,
                    discord_free_agent_offers_webhook_url=self.discord_free_agent_offers_webhook_url,
                    discord_free_agent_offers_forum_tag_ids=tuple(self.discord_free_agent_offers_forum_tag_ids),
                    discord_free_agent_offers_role_id=self.discord_free_agent_offers_role_id,
                    discord_role_id=self.discord_role_id,
                    discord_notifications_enabled=self.discord_notifications_enabled,
                    discord_image_notifications_enabled=self.discord_image_notifications_enabled,
                    discord_allowed_image_mime_types=tuple(DISCORD_CUSTOM_IMAGE_ALLOWED_MIME_TYPES),
                    discord_max_image_base64_chars=CUSTOM_IMAGE_MAX_BASE64_CHARS,
                    discord_max_image_bytes=CUSTOM_IMAGE_MAX_BYTES,
                    openai_api_key=self.openai_api_key,
                    openai_text_model=self.openai_text_model,
                    openai_text_timeout_seconds=self.openai_text_timeout_seconds,
                    openai_image_model=self.openai_image_model,
                    openai_image_size=self.openai_image_size,
                    openai_image_quality=self.openai_image_quality,
                    openai_image_format=self.openai_image_format,
                    openai_image_timeout_seconds=self.openai_image_timeout_seconds,
                    openai_reference_image_timeout_seconds=self.openai_reference_image_timeout_seconds,
                    openai_reference_image_max_bytes=self.openai_reference_image_max_bytes,
                    owner_forecast_window=CAP_FORECAST_WINDOW,
                    owner_objective_options=tuple(OWNER_SEASON_OBJECTIVES),
                ),
                opener=urlopen,
                now=now_iso,
                log_error=self.log_error,
            )
            self._application_container = container
        return container

    def _request_log_context(self) -> Dict[str, str]:
        return request_context(
            self._request_id(),
            getattr(self, "command", None),
            urlparse(getattr(self, "path", "")).path,
        )

    def log_message(self, format: str, *args: Any) -> None:
        logger.info(format, *args, extra=self._request_log_context())

    def log_error(self, format: str, *args: Any) -> None:
        logger.error(format, *args, extra=self._request_log_context())

    def _request_id(self) -> str:
        existing = getattr(self, "_audit_request_id", None)
        try:
            headers = self.headers
        except AttributeError:
            headers = {}
        request_id = request_id_from_headers(headers, existing)
        self._audit_request_id = request_id
        return request_id

    def _send_extra_headers(self, headers: Optional[Dict[str, Any]] = None) -> None:
        if not headers:
            return
        for key, value in headers.items():
            if isinstance(value, (list, tuple)):
                for item in value:
                    self.send_header(key, str(item))
            else:
                self.send_header(key, str(value))

    def _json(self, status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Request-ID", self._request_id())
        header_keys = {str(key).lower() for key in (headers or {}).keys()}
        if "cache-control" not in header_keys:
            self.send_header("Cache-Control", "no-store")
        self._send_extra_headers(headers)
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            return

    def _bytes_response(self, status: int, data: bytes, content_type: str, headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Request-ID", self._request_id())
        header_keys = {str(key).lower() for key in (headers or {}).keys()}
        if "cache-control" not in header_keys:
            self.send_header("Cache-Control", "no-store")
        self._send_extra_headers(headers)
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            return

    def end_headers(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.lower()
        query = parsed.query
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "font-src 'self' data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "media-src 'self'; "
            "manifest-src 'self'; "
            "worker-src 'none'; "
            "frame-src 'none'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'",
        )
        if self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower() == "https":
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if path.endswith(".html") or path in {"/", "/login", "/admin", "/news"}:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        elif path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico")):
            if query:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
        super().end_headers()

    def _redirect(self, location: str, headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self._send_extra_headers(headers)
        self.end_headers()

    def _read_json(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError) as err:
            raise ValueError("invalid_content_length") from err
        if length < 0:
            raise ValueError("invalid_content_length")
        if length > JSON_REQUEST_MAX_BYTES:
            raise ValueError("request_too_large")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw:
            return {}
        if len(raw) != length:
            raise ValueError("invalid_json")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise ValueError("invalid_json") from err
        if not isinstance(payload, dict):
            raise ValueError("invalid_json")
        validate_json_structure(payload)
        return payload

    def _read_json_or_error(self) -> Optional[Dict[str, Any]]:
        try:
            return self._read_json()
        except RequestValidationError as err:
            self._json(400, err.response_payload())
            return None
        except ValueError as err:
            error = str(err) or "invalid_json"
            self._json(413 if error == "request_too_large" else 400, {"error": error})
            return None

    def _validate_payload_or_error(
        self,
        payload: Dict[str, Any],
        allowed_fields: Iterable[str],
        *,
        required_fields: Iterable[str] = (),
        text_fields: Iterable[tuple[str, int, bool]] = (),
        integer_fields: Iterable[tuple[str, int, int]] = (),
    ) -> bool:
        try:
            validate_payload_fields(payload, allowed_fields, required_fields=required_fields)
            for field, max_length, required in text_fields:
                validate_text_field(payload, field, max_length=max_length, required=required)
            for field, minimum, maximum in integer_fields:
                validate_integer_range(payload, field, minimum=minimum, maximum=maximum)
        except RequestValidationError as err:
            self._json(400, err.response_payload())
            return False
        return True

    def _validate_specialized_payload_or_error(
        self,
        payload: Dict[str, Any],
        validator: Any,
        **validator_kwargs: Any,
    ) -> bool:
        try:
            validator(payload, **validator_kwargs)
        except RequestValidationError as err:
            self._json(400, err.response_payload())
            return False
        return True

    def _validate_free_agency_route_payload(self, payload: Dict[str, Any], action: str) -> bool:
        validators = {
            "bird_renounce": validate_gm_bird_renounce_payload,
            "offer": validate_free_agent_offer_payload,
            "negotiate": validate_free_agent_negotiation_payload,
            "waiver_claim": validate_waiver_claim_payload,
            "admin_decision": validate_admin_decision_payload,
        }
        if action in validators:
            return self._validate_specialized_payload_or_error(payload, validators[action])
        allowed_fields = FREE_AGENT_FAVORITE_FIELDS if action == "favorite" else OFFER_CANCEL_FIELDS
        return self._validate_payload_or_error(payload, allowed_fields)

    def _validate_free_agent_route_update_payload(self, payload: Dict[str, Any]) -> bool:
        return self._validate_payload_or_error(
            payload,
            FREE_AGENT_UPDATE_FIELDS,
            text_fields=(
                ("name", 200, False),
                ("position", 20, False),
                ("bird_rights", 20, False),
                ("rating", 32, False),
                ("free_agent_type", 40, False),
                ("agent", 200, False),
                ("notes", 10_000, False),
            ),
        )

    def _require_json_write_content_type(self) -> bool:
        length = parse_int(self.headers.get("Content-Length")) or 0
        if length <= 0:
            return True
        content_type = str(self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type == "application/json":
            return True
        self._json(415, {"error": "unsupported_media_type"})
        return False

    def _read_multipart_image_upload(self, field_name: str) -> tuple[bytes, str, str]:
        content_type = str(self.headers.get("Content-Type") or "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("invalid_multipart_upload")
        boundary_match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type)
        if not boundary_match:
            raise ValueError("missing_multipart_boundary")
        boundary = (boundary_match.group(1) or boundary_match.group(2) or "").encode("utf-8")
        if not boundary or len(boundary) > 200 or any(byte < 33 or byte > 126 for byte in boundary):
            raise ValueError("invalid_multipart_boundary")
        length = parse_int(self.headers.get("Content-Length"))
        if length is None or length <= 0:
            raise ValueError("missing_upload")
        if length > OWNER_BACKGROUND_MAX_BYTES + MULTIPART_UPLOAD_MAX_OVERHEAD_BYTES:
            raise ValueError("upload_too_large")
        body = self.rfile.read(length)
        delimiter = b"--" + boundary
        for raw_part in body.split(delimiter):
            part = raw_part.strip(b"\r\n")
            if not part or part == b"--":
                continue
            if part.endswith(b"--"):
                part = part[:-2].strip(b"\r\n")
            header_blob, separator, file_bytes = part.partition(b"\r\n\r\n")
            if not separator:
                continue
            headers = header_blob.decode("latin-1", errors="ignore").split("\r\n")
            disposition = next((line for line in headers if line.lower().startswith("content-disposition:")), "")
            if not re.search(rf'name="{re.escape(field_name)}"', disposition):
                continue
            filename_match = re.search(r'filename="([^"]*)"', disposition)
            if not filename_match or not filename_match.group(1):
                raise ValueError("missing_upload")
            mime_header = next((line for line in headers if line.lower().startswith("content-type:")), "")
            declared_mime = mime_header.split(":", 1)[1].strip().lower() if ":" in mime_header else ""
            if declared_mime.split(";", 1)[0].strip().lower() not in OWNER_BACKGROUND_ALLOWED_MIME_TYPES:
                raise ValueError("unsupported_upload_type")
            file_bytes = file_bytes.rstrip(b"\r\n")
            if not file_bytes:
                raise ValueError("missing_upload")
            if len(file_bytes) > OWNER_BACKGROUND_MAX_BYTES:
                raise ValueError("upload_too_large")
            ext, mime_type = self._uploaded_image_type(file_bytes, declared_mime)
            return file_bytes, ext, mime_type
        raise ValueError("missing_upload")

    def _uploaded_image_type(self, data: bytes, declared_mime: str = "") -> tuple[str, str]:
        return detect_safe_image_type(data, declared_mime, OWNER_BACKGROUND_ALLOWED_MIME_TYPES)

    def _client_ip(self) -> str:
        xff = self.headers.get("X-Forwarded-For", "").strip()
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def _cookie_dict(self) -> Dict[str, str]:
        raw = self.headers.get("Cookie", "")
        out: Dict[str, str] = {}
        for chunk in raw.split(";"):
            piece = chunk.strip()
            if not piece or "=" not in piece:
                continue
            k, v = piece.split("=", 1)
            out[k] = v
        return out

    def _request_is_secure(self) -> bool:
        proto = str(self.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
        if proto == "https":
            return True
        forwarded = str(self.headers.get("Forwarded") or "").lower()
        return "proto=https" in forwarded

    def _should_set_secure_cookie(self) -> bool:
        if self.cookie_same_site == "None":
            return True
        if self.cookie_secure_policy in {"1", "true", "yes", "on"}:
            return True
        if self.cookie_secure_policy in {"0", "false", "no", "off"}:
            return False
        return self._request_is_secure()

    def _request_origin(self) -> str:
        host = str(self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").split(",", 1)[0].strip().lower()
        if not host:
            return ""
        proto = str(self.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
        if proto not in {"http", "https"}:
            proto = "https" if self._request_is_secure() else "http"
        return f"{proto}://{host}"

    def _public_url(self, path: str) -> str:
        clean_path = str(path or "").strip()
        if not clean_path.startswith("/"):
            clean_path = f"/{clean_path}"
        base_url = self.public_base_url or self._request_origin()
        return f"{base_url.rstrip('/')}{clean_path}" if base_url else clean_path

    def _same_origin_request_ok(self) -> bool:
        return same_origin_request_ok(self.headers, self._request_origin(), self.allowed_origins)

    def _maybe_cleanup_sessions(self) -> None:
        now_ts = int(datetime.now(UTC).timestamp())
        if now_ts - self._last_session_cleanup_ts < self.session_cleanup_interval_seconds:
            return
        type(self)._last_session_cleanup_ts = now_ts
        try:
            self.db.cleanup_expired_sessions(now_ts)
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc).lower():
                raise
            logger.warning(
                "Session cleanup skipped from request path: %s",
                exc,
                extra=self._request_log_context(),
            )

    def _current_session(self) -> Optional[Dict[str, Any]]:
        self._maybe_cleanup_sessions()
        token = self._cookie_dict().get("session")
        if not token:
            return None
        sess = self.db.get_session(token)
        if sess and sess.get("provider") == "google":
            email = str(sess.get("email") or "")
            role, team_codes = self._google_role_for_email(email)
            access = self.db.user_access_for_email(email)
            sess["role"] = role
            sess["team_codes"] = team_codes
            sess["team_code"] = team_codes[0] if team_codes else None
            sess["agent_name"] = str(access.get("agent_name") or "").strip()
        return sess

    def _is_authenticated(self) -> bool:
        return self._current_session() is not None

    def _is_admin(self) -> bool:
        sess = self._current_session()
        return bool(sess and sess.get("role") == "admin")

    def _is_admin_or_coadmin(self) -> bool:
        sess = self._current_session()
        return bool(sess and sess.get("role") in {"admin", "co_admin"})

    def _is_gm(self) -> bool:
        sess = self._current_session()
        return bool(sess and sess.get("role") in {"gm", "co_admin"})

    def _current_session_team_codes(self) -> List[str]:
        sess = self._current_session() or {}
        raw_codes = sess.get("team_codes")
        if isinstance(raw_codes, list):
            return [str(code).strip().upper() for code in raw_codes if str(code or "").strip()]
        return []

    def _can_manage_team(self, team_code: Any) -> bool:
        if self._is_admin():
            return True
        normalized = normalize_team_code(team_code)
        return bool(normalized and normalized in self._current_session_team_codes())

    def _require_team_write_access(self, team_code: Any) -> bool:
        normalized = normalize_team_code(team_code)
        if not normalized:
            self._json(400, {"error": "invalid_team"})
            return False
        if self._can_manage_team(normalized):
            return True
        self._json(403, {"error": "team_access_required"})
        return False

    def _authorize(self, action: str, resource: Optional[Dict[str, Any]] = None) -> bool:
        try:
            return authorize_action(
                authorization_actor_from_session(self._current_session()),
                action,
                resource or {},
            )
        except AuthorizationError as err:
            self._json(err.status, {"error": err.error})
            return False

    def _require_admin(self) -> bool:
        if self._is_admin():
            return True
        self._json(401, {"error": "admin_auth_required"})
        return False

    def _require_admin_or_coadmin(self) -> bool:
        if self._is_admin_or_coadmin():
            return True
        self._json(403, {"error": "admin_or_coadmin_required"})
        return False

    def _require_authenticated(self) -> bool:
        if self._is_authenticated():
            return True
        self._json(401, {"error": "auth_required"})
        return False

    def _route_html(self, filename: str) -> None:
        path = WEB_DIR / filename
        if not path.exists() or not path.is_file():
            self._json(404, {"error": "not_found"})
            return
        html = path.read_text(encoding="utf-8")
        html = re.sub(r"\?v=[A-Za-z0-9_.-]+", f"?v={self.asset_version}", html)
        self._bytes_response(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _start_session(self, session_payload: Dict[str, Any]) -> tuple[str, str]:
        self._maybe_cleanup_sessions()
        self._clear_session()
        now_ts = int(datetime.now(UTC).timestamp())
        data = dict(session_payload)
        csrf_token = secrets.token_urlsafe(24)
        data["csrf_token"] = csrf_token
        data["created_at_ts"] = now_ts
        data["expires_at"] = now_ts + self.session_ttl_seconds
        while True:
            token = secrets.token_urlsafe(32)
            created = self.db.create_session(token, data, now_iso(), data["expires_at"])
            if created:
                return token, csrf_token

    def _clear_session(self) -> None:
        token = self._cookie_dict().get("session")
        if token:
            self.db.delete_session(token)

    def _session_cookie(self, token: str) -> str:
        return build_cookie(
            "session",
            token,
            path="/",
            same_site=self.cookie_same_site,
            max_age=self.session_ttl_seconds,
            secure=self._should_set_secure_cookie(),
            domain=self.cookie_domain,
            priority_high=True,
        )

    def _clear_session_cookie(self) -> str:
        return build_cookie(
            "session",
            "",
            path="/",
            same_site=self.cookie_same_site,
            max_age=0,
            secure=self._should_set_secure_cookie(),
            domain=self.cookie_domain,
        )

    def _oauth_state_cookie(self, state: str) -> str:
        return build_cookie(
            "oauth_state",
            state,
            path="/api/auth/google/callback",
            same_site=self.cookie_same_site,
            max_age=self.oauth_state_ttl_seconds,
            secure=self._should_set_secure_cookie(),
            domain=self.cookie_domain,
        )

    def _clear_oauth_state_cookie(self) -> str:
        return build_cookie(
            "oauth_state",
            "",
            path="/api/auth/google/callback",
            same_site=self.cookie_same_site,
            max_age=0,
            secure=self._should_set_secure_cookie(),
            domain=self.cookie_domain,
        )

    def _csrf_ok(self) -> bool:
        sess = self._current_session()
        if not self._same_origin_request_ok():
            return False
        return csrf_token_ok(sess, self.headers.get("X-CSRF-Token", ""))

    def _require_csrf(self) -> bool:
        if self._csrf_ok():
            return True
        self._json(403, {"error": "csrf_invalid"})
        return False

    def _cleanup_oauth_states(self) -> None:
        now_ts = int(datetime.now(UTC).timestamp())
        expired = [state for state, expires_at in self.pending_oauth_states.items() if expires_at <= now_ts]
        for state in expired:
            self.pending_oauth_states.pop(state, None)

    def _store_oauth_state(self, state: str) -> None:
        self._cleanup_oauth_states()
        self.pending_oauth_states[state] = int(datetime.now(UTC).timestamp()) + self.oauth_state_ttl_seconds

    def _oauth_state_ok(self, state: str) -> bool:
        self._cleanup_oauth_states()
        expected_cookie = self._cookie_dict().get("oauth_state", "")
        expires_at = self.pending_oauth_states.get(state)
        if not state or not expected_cookie or not expires_at:
            return False
        if not secrets.compare_digest(state, expected_cookie):
            return False
        self.pending_oauth_states.pop(state, None)
        return True

    def _rate_limit_status(self, ip: str) -> tuple[bool, int]:
        now_ts = int(datetime.now(UTC).timestamp())
        rec = self.login_attempts.get(ip)
        if not rec:
            return False, 0
        blocked_until = parse_int(str(rec.get("blocked_until"))) or 0
        if blocked_until > now_ts:
            return True, blocked_until - now_ts
        return False, 0

    def _rate_limit_fail(self, ip: str) -> None:
        now_ts = int(datetime.now(UTC).timestamp())
        rec = self.login_attempts.get(ip)
        if not rec or (parse_int(str(rec.get("window_start"))) or 0) + self.login_window_seconds <= now_ts:
            rec = {"window_start": now_ts, "count": 0, "blocked_until": 0}
        rec["count"] = int(rec.get("count", 0)) + 1
        if rec["count"] >= self.login_max_attempts:
            rec["blocked_until"] = now_ts + self.login_block_seconds
            rec["count"] = 0
            rec["window_start"] = now_ts
        self.login_attempts[ip] = rec

    def _rate_limit_success(self, ip: str) -> None:
        if ip in self.login_attempts:
            del self.login_attempts[ip]

    def _throttle_hit(
        self,
        store: Dict[str, Dict[str, Any]],
        key: str,
        *,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        now_ts = int(datetime.now(UTC).timestamp())
        rec = store.get(key)
        if not rec or (parse_int(str(rec.get("window_start"))) or 0) + window_seconds <= now_ts:
            rec = {"window_start": now_ts, "count": 0}
        rec["count"] = int(rec.get("count", 0)) + 1
        store[key] = rec
        if rec["count"] <= max_requests:
            return False, 0
        retry_after = max(1, ((parse_int(str(rec.get("window_start"))) or now_ts) + window_seconds) - now_ts)
        return True, retry_after

    def _require_oauth_start_rate_limit(self) -> bool:
        limited, retry_after = self._throttle_hit(
            self.sensitive_attempts,
            f"oauth_start:{self._client_ip()}",
            max_requests=self.oauth_start_max_attempts,
            window_seconds=self.oauth_start_window_seconds,
        )
        if not limited:
            return True
        self._json(429, {"error": "too_many_attempts", "retry_after_seconds": retry_after})
        return False

    def _require_sensitive_rate_limit(self, scope: str) -> bool:
        token = self._cookie_dict().get("session") or self._client_ip()
        limited, retry_after = self._throttle_hit(
            self.sensitive_attempts,
            f"{scope}:{token}",
            max_requests=self.sensitive_max_requests,
            window_seconds=self.sensitive_window_seconds,
        )
        if not limited:
            return True
        self._json(429, {"error": "rate_limited", "retry_after_seconds": retry_after})
        return False




    def _google_role_for_email(self, email: str) -> tuple[str, List[str]]:
        normalized = str(email or "").strip().lower()
        if normalized in self.admin_emails:
            return "admin", []
        db_access = self.db.user_access_for_email(normalized)
        db_team_codes = normalize_team_codes(db_access.get("team_codes"))
        if parse_bool(db_access.get("is_co_admin")):
            return "co_admin", db_team_codes
        if db_team_codes:
            return "gm", db_team_codes
        team_codes = self.gm_accounts.get(normalized, [])
        if team_codes:
            return "gm", team_codes
        return "guest", []

    def _landing_path_for_session(self, role: Any, team_codes: Optional[List[str]] = None) -> str:
        if role == "admin":
            return "/admin"
        if role in {"gm", "co_admin"}:
            team_code = (team_codes or [None])[0]
            if team_code:
                return f"/?team={team_code}"
        return "/"

    def _audit_team_codes(
        self,
        team_code: Optional[str],
        details: Optional[Dict[str, Any]],
        extra_team_codes: Optional[List[Any]] = None,
    ) -> List[str]:
        return collect_team_codes(normalize_team_code, team_code, details, extra_team_codes)

    def _audit_entity_ids(
        self,
        entity: str,
        entity_id: Optional[str],
        details: Optional[Dict[str, Any]],
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
    ) -> tuple[Optional[str], Optional[str]]:
        return resolve_entity_ids(entity, entity_id, details, before, after)

    def _log_admin_action(
        self,
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        team_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        team_codes: Optional[List[Any]] = None,
    ) -> None:
        sess = self._current_session() or {}
        if sess.get("role") != "admin":
            return
        audit_team_codes = self._audit_team_codes(team_code, details, team_codes)
        player_id, profile_id = self._audit_entity_ids(entity, entity_id, details, before, after)
        self.db.log_admin_action(
            actor_email=sess.get("email"),
            actor_name=sess.get("name"),
            actor_role=str(sess.get("role") or ""),
            actor_user_id=parse_int(sess.get("user_id")),
            request_id=self._request_id(),
            method=getattr(self, "command", None),
            path=urlparse(getattr(self, "path", "")).path,
            action=action.strip().lower(),
            entity=entity.strip().lower(),
            entity_id=entity_id,
            team_code=team_code,
            team_codes=audit_team_codes,
            player_id=player_id,
            profile_id=profile_id,
            before=before,
            after=after,
            details=details or {},
        )

























    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if dispatch_routes(self, parsed, GET_ROUTES):
            return

        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if dispatch_routes(self, parsed, EARLY_POST_ROUTES):
            return
        if dispatch_routes(self, parsed, OWNER_OFFICE_MULTIPART_POST_ROUTES):
            return
        if not self._require_json_write_content_type():
            return
        payload = self._read_json_or_error()
        if payload is None:
            return
        if not dispatch_routes(self, parsed, POST_ROUTES, payload):
            self._json(404, {"error": "not_found"})

    def do_PATCH(self) -> None:
        if not self._require_csrf():
            return
        if not self._require_sensitive_rate_limit("admin_patch"):
            return
        if not self._require_json_write_content_type():
            return
        parsed = urlparse(self.path)
        payload = self._read_json_or_error()
        if payload is None:
            return
        if dispatch_routes(self, parsed, PATCH_ROUTES, payload):
            return

        self._json(404, {"error": "not_found"})

    def do_DELETE(self) -> None:
        if not self._require_csrf():
            return
        if not self._require_sensitive_rate_limit("admin_delete"):
            return
        if not self._require_json_write_content_type():
            return
        parsed = urlparse(self.path)
        if not dispatch_routes(self, parsed, DELETE_ROUTES):
            self._json(404, {"error": "not_found"})


def run_server(db_path: str, host: str, port: int) -> None:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}. Run app/xlsx_import.py first.")

    configure_logging()
    Handler.db = LeagueDB(db_path)
    Handler.db.ensure_auth_schema()

    server = ThreadingHTTPServer((host, port), Handler)
    logger.info("Serving on http://%s:%s", host, port)

    def warm_tracker_cache_background() -> None:
        try:
            Handler.db.warm_tracker_cache()
        except Exception as err:
            logger.warning("Tracker cache warmup skipped: %s", err)

    threading.Thread(target=warm_tracker_cache_background, daemon=True).start()
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="ANBA roster manager server")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    run_server(args.db, args.host, args.port)


if __name__ == "__main__":
    main()
