#!/usr/bin/env python3
import argparse
import base64
import copy
import csv
import hashlib
import io
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen
from xml.sax.saxutils import escape as xml_escape

try:
    from .auth.csrf import csrf_token_ok, same_origin_request_ok
    from .auth.policies import (
        AUTH_POLICIES,
        AuthorizationError,
        authorization_actor_from_session,
        authorize_action,
        normalize_team_code,
        normalize_team_codes,
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
    from .db.repositories.depth_charts import DepthChartRepository
    from .db.repositories.notifications import NotificationRepository
    from .db.repositories.owner_office import OwnerOfficeRepository
    from .db.repositories.player_identity import PlayerIdentityRepository
    from .db.repositories.players import PlayerRepository
    from .db.repositories.press_articles import PressArticleRepository
    from .db.repositories.settings import SettingsRepository
    from .db.repositories.users import UserRepository
    from .db.repositories.teams import TeamRepository
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
        parse_free_agent_rep_discord_ids,
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
    from .integrations.discord import (
        DiscordConfig,
        DiscordIntegration,
        http_error_excerpt,
        truncate_text,
    )
    from .integrations.google_oauth import GoogleOAuthConfig, GoogleOAuthIntegration
    from .integrations.openai import OpenAIConfig, OpenAIIntegration
    from .db.migrations import DatabaseMigrationsMixin
    from .maintenance import CURRENT_SCHEMA_MIGRATION_KEY, CURRENT_SCHEMA_VERSION, DatabaseMaintenanceMixin
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
    from .services.draft import DraftService
    from .services.admin_exports import LeagueWorkbookExportService
    from .services.admin_imports import OwnerAdminImportService
    from .services.free_agency import FreeAgencyService, OfferDecisionOptions
    from .services.player_catalog import PlayerCatalogService
    from .services.player_identity import PlayerIdentityService
    from .services.owner_office import OwnerOfficeOperations, OwnerOfficeService
    from .services.owner_interviews import OwnerInterviewCompositionService
    from .services.notifications import EventNotification, NotificationCompositionService
    from .services.season_rollover import SeasonRolloverService
    from .services.team_detail import TeamDetailOperations, TeamDetailService
    from .services.tracker import TrackerOperations, TrackerService
    from .services.trades import TradeService
    from .services.waivers import WaiverService
    from .workflow_states import WorkflowTransitionError, workflow_definition
except ImportError:  # pragma: no cover - supports `python3 app/server.py`.
    from auth.csrf import csrf_token_ok, same_origin_request_ok
    from auth.policies import (
        AUTH_POLICIES,
        AuthorizationError,
        authorization_actor_from_session,
        authorize_action,
        normalize_team_code,
        normalize_team_codes,
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
    from db.repositories.depth_charts import DepthChartRepository
    from db.repositories.notifications import NotificationRepository
    from db.repositories.owner_office import OwnerOfficeRepository
    from db.repositories.player_identity import PlayerIdentityRepository
    from db.repositories.players import PlayerRepository
    from db.repositories.press_articles import PressArticleRepository
    from db.repositories.settings import SettingsRepository
    from db.repositories.users import UserRepository
    from db.repositories.teams import TeamRepository
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
        parse_free_agent_rep_discord_ids,
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
    from integrations.discord import (
        DiscordConfig,
        DiscordIntegration,
        http_error_excerpt,
        truncate_text,
    )
    from integrations.google_oauth import GoogleOAuthConfig, GoogleOAuthIntegration
    from integrations.openai import OpenAIConfig, OpenAIIntegration
    from db.migrations import DatabaseMigrationsMixin
    from maintenance import CURRENT_SCHEMA_MIGRATION_KEY, CURRENT_SCHEMA_VERSION, DatabaseMaintenanceMixin
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
    from services.draft import DraftService
    from services.admin_exports import LeagueWorkbookExportService
    from services.admin_imports import OwnerAdminImportService
    from services.free_agency import FreeAgencyService, OfferDecisionOptions
    from services.player_catalog import PlayerCatalogService
    from services.player_identity import PlayerIdentityService
    from services.owner_office import OwnerOfficeOperations, OwnerOfficeService
    from services.owner_interviews import OwnerInterviewCompositionService
    from services.notifications import EventNotification, NotificationCompositionService
    from services.season_rollover import SeasonRolloverService
    from services.team_detail import TeamDetailOperations, TeamDetailService
    from services.tracker import TrackerOperations, TrackerService
    from services.trades import TradeService
    from services.waivers import WaiverService
    from workflow_states import WorkflowTransitionError, workflow_definition

logger = get_logger("server")

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
TRADE_VALIDATION_RULES_VERSION = "2026-07-16.1"
OWNER_BACKGROUND_MAX_BYTES = 12_000_000
CUSTOM_IMAGE_MAX_BYTES = 8 * 1024 * 1024
CUSTOM_IMAGE_MAX_BASE64_CHARS = ((CUSTOM_IMAGE_MAX_BYTES + 2) // 3) * 4 + 16
JSON_REQUEST_MAX_BYTES = 16 * 1024 * 1024
JSON_MAX_DEPTH = 16
JSON_MAX_CONTAINER_ITEMS = 10_000
JSON_MAX_OBJECT_FIELDS = 2_048
JSON_MAX_TOTAL_NODES = 100_000
JSON_MAX_KEY_LENGTH = 128
IMAGE_MAX_DIMENSION = 8192
IMAGE_MAX_PIXELS = 40_000_000
SPREADSHEET_MAX_BYTES = 5_000_000
SPREADSHEET_MAX_BASE64_CHARS = ((SPREADSHEET_MAX_BYTES + 2) // 3) * 4 + 16
XLSX_MAX_ARCHIVE_ENTRIES = 256
XLSX_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
XLSX_MAX_ENTRY_BYTES = 32 * 1024 * 1024
XLSX_MAX_COMPRESSION_RATIO = 200
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
DEPTH_CHART_POSITIONS = ("PG", "SG", "SF", "PF", "C")
DEPTH_CHART_MAX_DEPTH = 6


def static_asset_version() -> str:
    explicit = (
        os.getenv("ASSET_VERSION")
        or os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("SOURCE_VERSION")
        or ""
    ).strip()
    if explicit:
        clean = re.sub(r"[^A-Za-z0-9_.-]", "", explicit)[:24]
        if clean:
            return clean

    digest = hashlib.sha256()
    for filename in STATIC_ASSET_FILES:
        path = WEB_DIR / filename
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        digest.update(filename.encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()[:12]


def normalize_player_happiness(value: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return 0
    parsed = parse_float(raw)
    if parsed is None or not math.isfinite(parsed) or parsed < -10 or parsed > 10:
        raise ValueError("invalid_happiness")
    return int(parsed) if float(parsed).is_integer() else parsed


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
FREE_AGENT_ROLE_VALUES = {
    "Titular",
    "Sexto hombre",
    "Minutos de rotación (10-20)",
    "Minutos de rotación (0-9)",
    "Fuera de la rotación",
}
GM_OPTION_REQUEST_FIELDS = {"player_id", "option_field", "option_value", "action"}
GM_BIRD_RENOUNCE_FIELDS = {"player_id", "season_year", "rights_value"}
FREE_AGENT_OFFER_FIELDS = {
    "team_code", "contract_type", "years", "annual_raise_percent", "role",
    "salary_by_season", "option_by_season", "notes",
}
FREE_AGENT_NEGOTIATION_FIELDS = {"team_code", "economic_offer", "role_offer", "comments"}
FREE_AGENT_FAVORITE_FIELDS = {"team_code"}
OFFER_CANCEL_FIELDS = {"team_code"}
WAIVER_CLAIM_FIELDS = {"team_code", "contingent_cut_player_id"}
COADMIN_VOTE_SUBMIT_FIELDS = {"scores"}
ADMIN_DECISION_FIELDS = {
    "decision", "note", "notify_discord", "generate_discord_image", "discord_custom_image",
}
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


def validate_json_structure(payload: Any) -> None:
    validate_json_structure_limits(
        payload,
        max_depth=JSON_MAX_DEPTH,
        max_container_items=JSON_MAX_CONTAINER_ITEMS,
        max_object_fields=JSON_MAX_OBJECT_FIELDS,
        max_total_nodes=JSON_MAX_TOTAL_NODES,
        max_key_length=JSON_MAX_KEY_LENGTH,
    )


def validate_season_value_map(
    value: Any,
    *,
    field: str,
    numeric: bool,
    allowed_options: Optional[set[str]] = None,
) -> None:
    if not isinstance(value, dict):
        raise RequestValidationError("invalid_field", field=field)
    if len(value) > len(PLAYER_CONTRACT_SEASONS):
        raise RequestValidationError("object_too_large", field=field)
    for raw_year, raw_value in value.items():
        if not re.fullmatch(r"20\d{2}", str(raw_year)) or int(raw_year) not in PLAYER_CONTRACT_SEASONS:
            raise RequestValidationError("invalid_season", field=field, season=str(raw_year))
        if numeric:
            if isinstance(raw_value, bool):
                raise RequestValidationError("invalid_field", field=f"{field}.{raw_year}")
            parsed = parse_amount_like(raw_value)
            if parsed is None or not math.isfinite(parsed) or parsed < 0 or parsed > 1_000_000_000:
                raise RequestValidationError("invalid_field", field=f"{field}.{raw_year}")
        else:
            option = str(raw_value or "").strip().upper()
            if allowed_options is not None and option not in allowed_options:
                raise RequestValidationError("invalid_enum", field=f"{field}.{raw_year}")


def validate_free_agent_offer_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(
        payload,
        FREE_AGENT_OFFER_FIELDS,
        required_fields={"contract_type", "years", "salary_by_season", "option_by_season"},
    )
    validate_team_code_field(payload)
    validate_text_field(payload, "contract_type", max_length=24, required=True)
    years = parse_int(payload.get("years"))
    if years is None or years < 1 or years > 5:
        raise RequestValidationError("invalid_integer_range", field="years", minimum=1, maximum=5)
    validate_number_range(payload, "annual_raise_percent", minimum=-8, maximum=8)
    validate_text_field(payload, "notes", max_length=4_000)
    if "role" in payload and str(payload.get("role") or "").strip() not in ({""} | FREE_AGENT_ROLE_VALUES):
        raise RequestValidationError("invalid_enum", field="role")
    validate_season_value_map(payload.get("salary_by_season"), field="salary_by_season", numeric=True)
    validate_season_value_map(
        payload.get("option_by_season"),
        field="option_by_season",
        numeric=False,
        allowed_options={"", "TO", "PO"},
    )


def validate_free_agent_negotiation_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, FREE_AGENT_NEGOTIATION_FIELDS)
    validate_team_code_field(payload)
    validate_text_field(payload, "economic_offer", max_length=500)
    validate_text_field(payload, "role_offer", max_length=200)
    validate_text_field(payload, "comments", max_length=4_000)


def validate_gm_option_request_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, GM_OPTION_REQUEST_FIELDS, required_fields=GM_OPTION_REQUEST_FIELDS)
    player_id = parse_int(payload.get("player_id"))
    if player_id is None or player_id <= 0:
        raise RequestValidationError("invalid_id", field="player_id")
    option_field = str(payload.get("option_field") or "").strip()
    if not re.fullmatch(r"option_(20\d{2})", option_field) or int(option_field[-4:]) not in PLAYER_CONTRACT_SEASONS:
        raise RequestValidationError("invalid_option_field", field="option_field")
    if str(payload.get("option_value") or "").strip().upper() not in {"TO", "PO", "QO", "GAP"}:
        raise RequestValidationError("invalid_enum", field="option_value")
    if str(payload.get("action") or "").strip().lower() not in {"accepted", "rejected"}:
        raise RequestValidationError("invalid_enum", field="action")


def validate_gm_bird_renounce_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, GM_BIRD_RENOUNCE_FIELDS, required_fields=GM_BIRD_RENOUNCE_FIELDS)
    player_id = parse_int(payload.get("player_id"))
    season_year = parse_int(payload.get("season_year"))
    if player_id is None or player_id <= 0:
        raise RequestValidationError("invalid_id", field="player_id")
    if season_year not in PLAYER_CONTRACT_SEASONS:
        raise RequestValidationError("invalid_season", field="season_year")
    if str(payload.get("rights_value") or "").strip().upper() not in {"FB", "EB", "NB"}:
        raise RequestValidationError("invalid_enum", field="rights_value")


def validate_waiver_claim_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, WAIVER_CLAIM_FIELDS)
    validate_team_code_field(payload)
    if payload.get("contingent_cut_player_id") not in (None, ""):
        player_id = parse_int(payload.get("contingent_cut_player_id"))
        if player_id is None or player_id <= 0:
            raise RequestValidationError("invalid_id", field="contingent_cut_player_id")


def validate_coadmin_vote_submit_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, COADMIN_VOTE_SUBMIT_FIELDS, required_fields={"scores"})
    scores = payload.get("scores")
    if not isinstance(scores, dict) or len(scores) > 30:
        raise RequestValidationError("invalid_field", field="scores")
    normalized_codes = set()
    for team_code, score in scores.items():
        normalized = normalize_team_code(team_code)
        if not normalized or not re.fullmatch(r"[A-Z]{3}", normalized):
            raise RequestValidationError("invalid_team_code", field=f"scores.{team_code}")
        if normalized in normalized_codes:
            raise RequestValidationError("duplicate_value", field="scores.team_code", value=normalized)
        parsed = parse_int(score)
        if parsed is None or parsed < 1 or parsed > 100:
            raise RequestValidationError("invalid_integer_range", field=f"scores.{team_code}", minimum=1, maximum=100)
        normalized_codes.add(normalized)


def validate_admin_decision_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, ADMIN_DECISION_FIELDS, required_fields={"decision"})
    if str(payload.get("decision") or "").strip().lower() not in {"approved", "rejected"}:
        raise RequestValidationError("invalid_enum", field="decision")
    validate_text_field(payload, "note", max_length=2_000)
    validate_boolean_field(payload, "notify_discord")
    validate_boolean_field(payload, "generate_discord_image")
    custom_image = payload.get("discord_custom_image")
    if custom_image is not None and not isinstance(custom_image, dict):
        raise RequestValidationError("invalid_field", field="discord_custom_image")


def contract_option_rejection_clear_payload(season: int) -> Dict[str, Any]:
    """Clear the rejected option season and every future contract year."""
    payload: Dict[str, Any] = {}
    for year in PLAYER_CONTRACT_SEASONS:
        if year < season:
            continue
        payload[f"salary_{year}_text"] = None
        payload[f"salary_{year}_guaranteed_text"] = None
        payload[f"salary_{year}_note_text"] = None
        payload[f"option_{year}"] = None
        payload[f"salary_{year}_provisional"] = False
        payload[f"salary_{year}_partially_guaranteed"] = False
        payload[f"salary_{year}_note"] = False
    return payload
OWNER_OFFICE_IMPORT_ROWS = {
    "income": [
        {"key": "recaudacion", "label": "Recaudación", "type": "category"},
        {"key": "media_espectadores", "label": "Media espectadores", "type": "field"},
        {"key": "entradas_regular_season", "label": "Entradas Regular Season", "type": "field"},
        {"key": "partidos_playoffs", "label": "Partidos playoffs", "type": "field"},
        {"key": "entradas_playoffs", "label": "Entradas Playoffs", "type": "field"},
        {"key": "precio_medio_entrada", "label": "Precio medio entrada", "type": "field"},
        {"key": "consumiciones", "label": "Consumiciones", "type": "field"},
        {"key": "merchandising", "label": "Merchandising", "type": "category"},
        {"key": "ventas_camisetas_ropa", "label": "Ventas de camisetas y ropa", "type": "field"},
        {"key": "precio_medio_articulo", "label": "Precio medio artículo", "type": "field"},
        {"key": "derechos", "label": "Derechos", "type": "category"},
        {"key": "tv_globales", "label": "TV globales", "type": "field"},
        {"key": "tv_local", "label": "TV local", "type": "field"},
        {"key": "licencias", "label": "Licencias", "type": "field"},
        {"key": "sponsor", "label": "Sponsor", "type": "category"},
        {"key": "patrocinador_jersey", "label": "Patrocinador jersey", "type": "field"},
        {"key": "patrocinador_estadio", "label": "Patrocinador estadio", "type": "field"},
        {"key": "patrocinadores_generales", "label": "Patrocinadores generales", "type": "field"},
        {"key": "flujos_caja_positivos", "label": "Flujos de caja positivos", "type": "category"},
        {"key": "traspasos_positivos", "label": "Traspasos", "type": "field"},
        {"key": "bonificaciones", "label": "Bonificaciones", "type": "field"},
        {"key": "reparto_beneficios_positivo", "label": "Reparto beneficios", "type": "field"},
        {"key": "reparto_impuesto_lujo", "label": "Reparto impuesto de lujo", "type": "field"},
    ],
    "expenses": [
        {"key": "coste_plantilla", "label": "Coste plantilla", "type": "category"},
        {"key": "salarios", "label": "Salarios", "type": "field"},
        {"key": "multa", "label": "Multa", "type": "field"},
        {"key": "cuerpo_tecnico", "label": "Cuerpo técnico", "type": "category"},
        {"key": "multiplicador_exitos", "label": "Multiplicador éxitos", "type": "field"},
        {"key": "gastos_cuerpo_tecnico", "label": "Gastos", "type": "field"},
        {"key": "gastos_estadio", "label": "Gastos de estadio", "type": "category"},
        {"key": "partidos", "label": "Partidos", "type": "field"},
        {"key": "gastos_partido", "label": "Gastos partido", "type": "field"},
        {"key": "indice_coste_estadio", "label": "Índice coste", "type": "field"},
        {"key": "gastos_television", "label": "Gastos de televisión", "type": "category"},
        {"key": "produccion", "label": "Producción", "type": "field"},
        {"key": "costes_marketing", "label": "Costes de marketing", "type": "category"},
        {"key": "indice_coste_marketing", "label": "Índice coste", "type": "field"},
        {"key": "costes_ineficiencia", "label": "Costes ineficiencia", "type": "field"},
        {"key": "unidades", "label": "Unidades", "type": "field"},
        {"key": "coste_por_unidad", "label": "Coste por unidad", "type": "field"},
        {"key": "gastos_operativos", "label": "Gastos operativos", "type": "category"},
        {"key": "gastos_operativos_valor", "label": "Gastos", "type": "field"},
        {"key": "indice_coste_operativo", "label": "Índice coste", "type": "field"},
        {"key": "flujos_caja_negativos", "label": "Flujos de caja negativos", "type": "category"},
        {"key": "traspasos_negativos", "label": "Traspasos", "type": "field"},
        {"key": "sanciones", "label": "Sanciones", "type": "field"},
        {"key": "reparto_beneficios_negativo", "label": "Reparto beneficios", "type": "field"},
    ],
}
ECONOMY_IMPORT_TOTAL_ROWS = [
    {"key": "revenue", "label": "Ingresos", "type": "field"},
    {"key": "expenses", "label": "Gastos", "type": "field"},
    {"key": "balance", "label": "Balance", "type": "field"},
]
TEAM_IMAGE_COLORS = {
    "ATL": "#E03A3E, #C1D32F",
    "BKN": "#000000, #FFFFFF",
    "BOS": "#007A33, #BA9653",
    "CHA": "#1D1160, #00788C",
    "CHI": "#CE1141, #000000",
    "CLE": "#860038, #FDBB30",
    "DAL": "#00538C, #002F5F",
    "DEN": "#0E2240, #FEC524",
    "DET": "#C8102E, #1D42BA",
    "GSW": "#1D428A, #FFC72C",
    "HOU": "#CE1141, #000000",
    "IND": "#002D62, #FDBB30",
    "LAC": "#C8102E, #1D428A",
    "LAL": "#552583, #FDB927",
    "MEM": "#12173F, #5D76A9",
    "MIA": "#98002E, #000000",
    "MIL": "#00471B, #EEE1C6",
    "MIN": "#0C2340, #9EA2A2",
    "NOP": "#0C2340, #C8102E",
    "NYK": "#006BB6, #F58426",
    "OKC": "#007AC1, #EF3B24",
    "ORL": "#0077C0, #000000",
    "PHI": "#006BB6, #ED174C",
    "PHX": "#E56020, #1D1160",
    "POR": "#E03A3E, #000000",
    "SAC": "#5A2D81, #63727A",
    "SAS": "#000000, #C4CED4",
    "TOR": "#CE1141, #000000",
    "UTA": "#002B5C, #00471B",
    "WAS": "#002B5C, #E31837",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env_file(Path(os.getenv("ENV_FILE", str(DEFAULT_ENV_FILE))))


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
) -> tuple[str, str]:
    allowed = allowed_mime_types or OWNER_BACKGROUND_ALLOWED_MIME_TYPES
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

    if detected_mime not in allowed:
        raise ValueError("unsupported_upload_type")
    if declared and declared != detected_mime:
        raise ValueError("unsupported_upload_type")
    width, height = image_dimensions(data, detected_mime)
    if width <= 0 or height <= 0:
        raise ValueError("invalid_image_dimensions")
    if width > IMAGE_MAX_DIMENSION or height > IMAGE_MAX_DIMENSION or width * height > IMAGE_MAX_PIXELS:
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


def public_backup_metadata(backup: Dict[str, Any]) -> Dict[str, Any]:
    allowed = ("id", "reason", "bytes", "sha256", "integrity_check", "created_at", "verified_at")
    return {key: backup.get(key) for key in allowed if backup.get(key) is not None}


def normalize_dead_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"two_way", "tw"}:
        return "two_way"
    if raw in {"draft_hold", "draft_cap_hold", "rookie_hold"}:
        return "draft_hold"
    return "normal"


def normalize_free_agent_type(value: Any) -> str:
    raw = str(value or "").strip()
    normalized = (
        raw.lower()
        .replace("-", " ")
        .replace("_", " ")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in {"restringido", "restricted", "rfa"}:
        return FREE_AGENT_TYPE_RESTRICTED
    if normalized in {"no restringido", "unrestricted", "ufa"}:
        return FREE_AGENT_TYPE_UNRESTRICTED
    return FREE_AGENT_TYPE_UNRESTRICTED


PLAYER_PROFILE_STATUS_ACTIVE = "active"
PLAYER_PROFILE_STATUS_OUTSIDE_NBA = "outside_nba"
PLAYER_PROFILE_STATUS_RETIRED = "retired"
PLAYER_PROFILE_STATUSES = {
    PLAYER_PROFILE_STATUS_ACTIVE,
    PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
    PLAYER_PROFILE_STATUS_RETIRED,
}
PLAYER_PROFILE_STATUS_LABELS = {
    PLAYER_PROFILE_STATUS_ACTIVE: "Activo",
    PLAYER_PROFILE_STATUS_OUTSIDE_NBA: "Fuera de la NBA",
    PLAYER_PROFILE_STATUS_RETIRED: "Retirado",
}
UNAVAILABLE_PLAYER_PROFILE_STATUSES = {
    PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
    PLAYER_PROFILE_STATUS_RETIRED,
}


def normalize_player_profile_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"fuera_nba", "fuera_de_nba", "fuera_de_la_nba", "outside", "outside_nba", "out_of_nba"}:
        return PLAYER_PROFILE_STATUS_OUTSIDE_NBA
    if raw in {"retirado", "retired"}:
        return PLAYER_PROFILE_STATUS_RETIRED
    return PLAYER_PROFILE_STATUS_ACTIVE


def player_profile_status_label(value: Any) -> str:
    return PLAYER_PROFILE_STATUS_LABELS.get(normalize_player_profile_status(value), "Activo")


def is_unavailable_player_profile_status(value: Any) -> bool:
    return normalize_player_profile_status(value) in UNAVAILABLE_PLAYER_PROFILE_STATUSES


def dead_contract_salary_num(dead_contract: Dict[str, Any], season: int) -> float:
    value = dead_contract.get(f"salary_{season}_num")
    if value is not None:
        return float(value or 0.0)
    text_value = parse_amount_like(dead_contract.get(f"salary_{season}_text"))
    if text_value is not None:
        return text_value
    if season == 2025:
        amount_value = dead_contract.get("amount_num")
        if amount_value is not None:
            return float(amount_value or 0.0)
        return parse_amount_like(dead_contract.get("amount_text")) or 0.0
    return 0.0


def dead_contract_excluded_from_gasto(dead_contract: Dict[str, Any]) -> bool:
    return parse_bool(dead_contract.get("exclude_from_gasto"))


def dead_contract_excluded_from_cap(dead_contract: Dict[str, Any]) -> bool:
    return parse_bool(dead_contract.get("exclude_from_cap"))


def normalize_pick_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"acquired", "sold", "conditional"}:
        return raw
    return "own"


def normalize_pick_round(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if "2" in raw:
        return "2nd"
    return "1st"


def parse_gm_account_map(value: Any) -> Dict[str, List[str]]:
    if value is None:
        return {}
    raw = str(value or "").strip()
    if not raw:
        return {}

    parsed_items: List[Any]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        parsed_items = [{"email": email, "teams": teams} for email, teams in parsed.items()]
    elif isinstance(parsed, list):
        parsed_items = parsed
    else:
        parsed_items = re.split(r"[\n,]+", raw)

    mapping: Dict[str, List[str]] = {}
    for item in parsed_items:
        if isinstance(item, dict):
            email = str(item.get("email") or "").strip().lower()
            teams_value = item.get("teams") or item.get("team_codes") or item.get("team_code")
        else:
            text = str(item or "").strip()
            if not text:
                continue
            if "=" in text:
                email, teams_value = text.split("=", 1)
            elif ":" in text:
                email, teams_value = text.split(":", 1)
            else:
                continue
            email = email.strip().lower()

        if not email or "@" not in email:
            continue
        team_codes = normalize_team_codes(teams_value)
        if team_codes:
            mapping[email] = team_codes
    return mapping


def serialize_team_codes(value: Any) -> Optional[str]:
    codes = normalize_team_codes(value)
    return json.dumps(codes, ensure_ascii=True) if codes else None


def normalize_exception_type(value: Any) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if "tax" in raw:
        return "TAXPAYER Mid"
    if "room" in raw:
        return "ROOM Mid"
    if "bia" in raw:
        return "Bianual"
    if "traspas" in raw or "trade" in raw:
        return "Excepción de traspaso"
    if "mid" in raw:
        return "Mid-Level"
    return str(value).strip() or None


def parse_salary_amount(value: Any) -> Optional[float]:
    return parse_amount_like(value)


def format_salary_amount_text(value: Any) -> Optional[str]:
    amount = parse_salary_amount(value)
    if amount is None:
        return None
    return f"{int(round(amount)):,}".replace(",", ".")


def normalize_gm_start_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_hex_color(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"#[0-9a-fA-F]{6}", raw):
        return raw.upper()
    return None


def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
    item = {d[0]: row[idx] for idx, d in enumerate(cursor.description)}
    if "years_left" in item:
        item["years_left"] = normalize_bird_years(item.get("years_left"))
    return item


def _xlsx_clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(ch if ch in "\t\n\r" or ord(ch) >= 32 else " " for ch in text)


def _xlsx_attr(value: Any) -> str:
    return xml_escape(_xlsx_clean_text(value), {'"': "&quot;", "'": "&apos;"})


def _xlsx_col_name(index: int) -> str:
    name = ""
    value = int(index)
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_cell_ref(row_index: int, col_index: int) -> str:
    return f"{_xlsx_col_name(col_index)}{row_index}"


def _xlsx_cell(row_index: int, col_index: int, value: Any) -> str:
    ref = _xlsx_cell_ref(row_index, col_index)
    if isinstance(value, bool):
        value = "Sí" if value else "No"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            rendered = str(int(numeric)) if numeric.is_integer() else repr(numeric)
            return f'<c r="{ref}"><v>{rendered}</v></c>'
    text = xml_escape(_xlsx_clean_text(value))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _xlsx_sheet_xml(rows: List[List[Any]]) -> str:
    sheet_rows: List[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(_xlsx_cell(row_index, col_index, value) for col_index, value in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )


def _xlsx_sheet_name(name: str, used_names: set[str]) -> str:
    clean = re.sub(r"[\[\]:*?/\\]", " ", str(name or "Sheet")).strip() or "Sheet"
    clean = clean[:31]
    candidate = clean
    suffix = 1
    while candidate in used_names:
        suffix_text = f" {suffix}"
        candidate = f"{clean[:31 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def _xlsx_workbook_bytes(sheets: List[Dict[str, Any]]) -> bytes:
    used_names: set[str] = set()
    normalized_sheets = [
        {
            "name": _xlsx_sheet_name(str(sheet.get("name") or f"Sheet {idx}"), used_names),
            "rows": sheet.get("rows") or [],
        }
        for idx, sheet in enumerate(sheets, start=1)
    ]
    worksheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for idx, _ in enumerate(normalized_sheets, start=1)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{worksheet_overrides}"
        "</Types>"
    )
    workbook_sheets = "".join(
        f'<sheet name="{_xlsx_attr(sheet["name"])}" sheetId="{idx}" r:id="rId{idx}"/>'
        for idx, sheet in enumerate(normalized_sheets, start=1)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{workbook_sheets}</sheets>"
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{idx}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
            for idx, _ in enumerate(normalized_sheets, start=1)
        )
        + "</Relationships>"
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    created = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>ANBA2K</dc:creator>"
        "<cp:lastModifiedBy>ANBA2K</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>ANBA2K</Application>"
        "</Properties>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for idx, sheet in enumerate(normalized_sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{idx}.xml", _xlsx_sheet_xml(sheet["rows"]))
    return output.getvalue()


def _xlsx_col_index_from_ref(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Za-z]", "", str(cell_ref or ""))
    value = 0
    for char in letters.upper():
        value = value * 26 + (ord(char) - ord("A") + 1)
    return max(1, value)


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    strings: List[str] = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] != "si":
            continue
        parts: List[str] = []
        for child in item.iter():
            if child.tag.rsplit("}", 1)[-1] == "t" and child.text:
                parts.append(child.text)
        strings.append("".join(parts))
    return strings


def _xlsx_cell_text(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = str(cell.attrib.get("t") or "")
    if cell_type == "inlineStr":
        parts: List[str] = []
        for child in cell.iter():
            if child.tag.rsplit("}", 1)[-1] == "t" and child.text:
                parts.append(child.text)
        return "".join(parts).strip()
    value_text = ""
    for child in cell:
        if child.tag.rsplit("}", 1)[-1] == "v":
            value_text = child.text or ""
            break
    if cell_type == "s":
        index = parse_int(value_text)
        if index is not None and 0 <= index < len(shared_strings):
            return str(shared_strings[index]).strip()
        return ""
    return str(value_text or "").strip()


def _xlsx_first_sheet_rows(file_bytes: bytes) -> List[List[str]]:
    with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as archive:
        entries = archive.infolist()
        if len(entries) > XLSX_MAX_ARCHIVE_ENTRIES:
            raise ValueError("xlsx_archive_too_large")
        total_uncompressed = 0
        for entry in entries:
            if entry.is_dir():
                continue
            if entry.file_size > XLSX_MAX_ENTRY_BYTES:
                raise ValueError("xlsx_archive_too_large")
            total_uncompressed += entry.file_size
            if total_uncompressed > XLSX_MAX_UNCOMPRESSED_BYTES:
                raise ValueError("xlsx_archive_too_large")
            if entry.file_size > 0:
                compressed_size = max(1, entry.compress_size)
                if entry.file_size / compressed_size > XLSX_MAX_COMPRESSION_RATIO:
                    raise ValueError("xlsx_suspicious_compression")
        shared_strings = _xlsx_shared_strings(archive)
        try:
            sheet_bytes = archive.read("xl/worksheets/sheet1.xml")
        except KeyError as err:
            raise ValueError("xlsx_first_sheet_missing") from err
        root = ET.fromstring(sheet_bytes)
        rows: List[List[str]] = []
        for row in root.iter():
            if row.tag.rsplit("}", 1)[-1] != "row":
                continue
            values: Dict[int, str] = {}
            max_col = 0
            for cell in row:
                if cell.tag.rsplit("}", 1)[-1] != "c":
                    continue
                col_idx = _xlsx_col_index_from_ref(str(cell.attrib.get("r") or ""))
                max_col = max(max_col, col_idx)
                values[col_idx] = _xlsx_cell_text(cell, shared_strings)
            if max_col <= 0:
                rows.append([])
            else:
                rows.append([values.get(col_idx, "") for col_idx in range(1, max_col + 1)])
        return rows


def _spreadsheet_rows_from_payload(
    file_name: str = "",
    file_data_base64: str = "",
    csv_text: str = "",
) -> List[List[str]]:
    if csv_text:
        text = str(csv_text)
        if len(text.encode("utf-8")) > SPREADSHEET_MAX_BYTES:
            raise ValueError("file_too_large")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [[str(cell or "").strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]

    raw_name = str(file_name or "").strip().lower()
    raw_data = str(file_data_base64 or "").strip()
    if not raw_data:
        raise ValueError("file_required")
    if "," in raw_data and raw_data.lower().startswith("data:"):
        raw_data = raw_data.split(",", 1)[1]
    if len(raw_data) > SPREADSHEET_MAX_BASE64_CHARS:
        raise ValueError("file_too_large")
    try:
        data = base64.b64decode(raw_data, validate=True)
    except (ValueError, TypeError) as err:
        raise ValueError("invalid_file_data") from err
    if len(data) > SPREADSHEET_MAX_BYTES:
        raise ValueError("file_too_large")
    if raw_name.endswith(".xlsx") or data[:2] == b"PK":
        return _xlsx_first_sheet_rows(data)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [[str(cell or "").strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]


def normalize_import_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_csv_amount(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()").replace(" ", "")
    cleaned = re.sub(r"[^0-9,.\-]", "", cleaned)
    if not cleaned or cleaned in {"-", ".", ","}:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) > 2 or (
            len(parts) == 2
            and len(parts[-1]) == 3
            and len(parts[0].lstrip("-")) <= 3
            and all(part.lstrip("-").isdigit() for part in parts)
        ):
            cleaned = "".join(parts)
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 2 or (
            len(parts) == 2
            and len(parts[-1]) == 3
            and len(parts[0].lstrip("-")) <= 3
            and all(part.lstrip("-").isdigit() for part in parts)
        ):
            cleaned = "".join(parts)
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return -abs(parsed) if negative else parsed


def owner_office_import_schema() -> Dict[str, List[Dict[str, str]]]:
    schema: Dict[str, List[Dict[str, str]]] = {}
    for section, rows in OWNER_OFFICE_IMPORT_ROWS.items():
        current_category = {"key": "", "label": ""}
        schema_rows: List[Dict[str, str]] = []
        for row in rows:
            normalized = {
                "key": str(row["key"]),
                "label": str(row["label"]),
                "type": str(row["type"]),
                "category_key": str(current_category["key"]),
                "category_label": str(current_category["label"]),
            }
            schema_rows.append(normalized)
            if normalized["type"] == "category":
                current_category = {"key": normalized["key"], "label": normalized["label"]}
        schema[section] = schema_rows
    schema["economy"] = [
        {
            "key": str(row["key"]),
            "label": str(row["label"]),
            "type": str(row["type"]),
            "category_key": "",
            "category_label": "Totales economía",
        }
        for row in ECONOMY_IMPORT_TOTAL_ROWS
    ]
    return schema


class LeagueDB(DatabaseMigrationsMixin, DatabaseMaintenanceMixin):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._free_agents_sync_lock = threading.Lock()
        self._session_cleanup_lock = threading.Lock()
        self._tracker_cache_lock = threading.Lock()
        self._tracker_cache: Dict[int, Dict[str, Any]] = {}
        self._notification_repository = NotificationRepository(self, now=now_iso)
        self._press_article_repository = PressArticleRepository(
            self,
            detect_image_type=detect_safe_image_type,
            allowed_mime_types=DISCORD_CUSTOM_IMAGE_ALLOWED_MIME_TYPES,
            max_image_bytes=CUSTOM_IMAGE_MAX_BYTES,
            now=now_iso,
        )
        self._settings_repository = SettingsRepository(self, now=now_iso)
        self._user_repository = UserRepository(self, now=now_iso)
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
            sync_draft_pick_identity=self._sync_draft_pick_asset_identity_conn,
            resolve_profile=self._resolve_profile_for_new_row,
            create_profile=self._create_player_profile,
        )
        self._team_repository = TeamRepository(
            self,
            now=now_iso,
            normalize_gm_start_date=normalize_gm_start_date,
            normalize_hex_color=normalize_hex_color,
        )
        self._player_repository = PlayerRepository(
            self,
            now=now_iso,
            select_columns=self._player_select_columns,
            merge_profile=self._merge_player_profile,
            record_transaction=self._record_player_transaction,
            upsert_salary_history=self._upsert_player_salary_history_row_conn,
            attach_salary_history=self._attach_player_salary_history_conn,
            player_text_fields=PLAYER_UPDATE_TEXT_FIELDS,
            player_bool_fields=PLAYER_UPDATE_BOOL_FIELDS,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
            normalize_experience=normalize_experience_years,
            ensure_profile=self._ensure_profile_for_player,
            sync_row_state=self._sync_player_row_state_conn,
            sync_generated_free_agents=self._sync_free_agency_generated_rows_if_needed,
            normalize_happiness=normalize_player_happiness,
            normalize_profile_status=normalize_player_profile_status,
            is_unavailable_profile_status=is_unavailable_player_profile_status,
            make_profile_unavailable=self._make_player_profile_unavailable_conn,
            retained_rights_only=self._player_row_is_retained_rights_only,
            resolve_profile=self._resolve_profile_for_new_row,
            parse_salary_amount=parse_salary_amount,
            free_agent_type_unrestricted=FREE_AGENT_TYPE_UNRESTRICTED,
            free_agent_source_uncontracted=FREE_AGENT_SOURCE_UNCONTRACTED_PROFILE,
        )
        self._player_identity_repository = PlayerIdentityRepository(
            self,
            now=now_iso,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
            retained_rights_only=self._player_row_is_retained_rights_only,
            current_year=self._current_year_conn,
            record_transaction=self._record_player_transaction,
            table_exists=self._table_exists_conn,
        )
        self._owner_office_repository = OwnerOfficeRepository(
            self,
            now=now_iso,
            exit_from_row=self._owner_exit_interview_from_row,
            confidence_delta=self._owner_confidence_with_delta,
            get_owner_office=self.get_team_owner_office,
            sanitize_background_url=sanitize_owner_background_url,
            detect_image_type=detect_safe_image_type,
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

    @staticmethod
    def _workflow_actor_fields(actor: Optional[Dict[str, Any]]) -> tuple[Optional[int], Optional[str], Optional[str]]:
        actor = actor or {}
        actor_user_id = parse_int(actor.get("user_id") if actor.get("user_id") is not None else actor.get("id"))
        actor_email = str(actor.get("email") or "").strip() or None
        actor_name = str(actor.get("name") or actor.get("username") or "").strip() or "system"
        return actor_user_id, actor_email, actor_name

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
        workflow_definition(workflow_type)
        normalized_command_id = str(command_id or secrets.token_urlsafe(24)).strip()
        created_at = timestamp or now_iso()
        normalized_reason = str(reason or "workflow_created").strip()
        actor_user_id, actor_email, actor_name = self._workflow_actor_fields(actor)
        conn.execute(
            """
            INSERT OR IGNORE INTO workflow_transition_log (
                workflow_type, resource_id, actor_user_id, actor_email, actor_name,
                previous_state, new_state, reason, command_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, '__none__', ?, ?, ?, ?, ?)
            """,
            (
                workflow_type,
                str(resource_id),
                actor_user_id,
                actor_email,
                actor_name,
                str(initial_state),
                normalized_reason,
                normalized_command_id,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                created_at,
            ),
        )
        return normalized_command_id

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
        definition = workflow_definition(workflow_type)
        normalized_state = str(new_state or "").strip().lower()
        normalized_command_id = str(command_id or secrets.token_urlsafe(24)).strip()
        resource_key = str(resource_id)
        existing = conn.execute(
            """
            SELECT previous_state, new_state
            FROM workflow_transition_log
            WHERE workflow_type = ? AND resource_id = ? AND command_id = ?
            """,
            (workflow_type, resource_key, normalized_command_id),
        ).fetchone()
        if existing:
            if str(existing["new_state"]) != normalized_state:
                raise WorkflowTransitionError(
                    "command_reused",
                    "The workflow command ID was already used for a different transition.",
                )
            return {
                "previous_state": str(existing["previous_state"]),
                "new_state": str(existing["new_state"]),
                "command_id": normalized_command_id,
                "idempotent": True,
            }

        row = conn.execute(
            f"SELECT {definition.state_column} AS workflow_state "
            f"FROM {definition.table} WHERE {definition.key_column} = ?",
            (resource_id,),
        ).fetchone()
        if not row:
            raise WorkflowTransitionError("workflow_not_found", "Workflow resource was not found.")
        previous_state = str(row["workflow_state"] or "").strip().lower()
        if normalized_state not in definition.transitions.get(previous_state, frozenset()):
            raise WorkflowTransitionError(
                "invalid_transition",
                f"Transition {previous_state} -> {normalized_state} is not permitted for {workflow_type}.",
            )

        update_values = dict(updates or {})
        unknown_columns = set(update_values) - set(definition.mutable_columns)
        if unknown_columns:
            raise WorkflowTransitionError(
                "invalid_transition_fields",
                f"Unsupported workflow update fields: {', '.join(sorted(unknown_columns))}",
            )
        assignments = [f"{definition.state_column} = ?"]
        values: List[Any] = [normalized_state]
        for column, value in update_values.items():
            assignments.append(f"{column} = ?")
            values.append(value)
        values.extend([resource_id, previous_state])
        cur = conn.execute(
            f"UPDATE {definition.table} SET {', '.join(assignments)} "
            f"WHERE {definition.key_column} = ? AND {definition.state_column} = ?",
            tuple(values),
        )
        if cur.rowcount != 1:
            raise WorkflowTransitionError(
                "transition_conflict",
                "Workflow state changed before this command could be applied.",
            )

        changed_at = timestamp or now_iso()
        normalized_reason = str(reason or f"{previous_state}_to_{normalized_state}").strip()
        actor_user_id, actor_email, actor_name = self._workflow_actor_fields(actor)
        conn.execute(
            """
            INSERT INTO workflow_transition_log (
                workflow_type, resource_id, actor_user_id, actor_email, actor_name,
                previous_state, new_state, reason, command_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_type,
                resource_key,
                actor_user_id,
                actor_email,
                actor_name,
                previous_state,
                normalized_state,
                normalized_reason,
                normalized_command_id,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                changed_at,
            ),
        )
        return {
            "previous_state": previous_state,
            "new_state": normalized_state,
            "command_id": normalized_command_id,
            "idempotent": False,
        }

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
        now = timestamp or now_iso()
        profile_name = str(name or "").strip() or "New Player"
        cur = conn.execute(
            """
            INSERT INTO player_profiles (
                name, experience_years, reference_image_url, profile_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                profile_name,
                normalize_experience_years(experience_years),
                str(reference_image_url or "").strip() or None,
                str(profile_notes or "").strip() or None,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


    def _current_year_conn(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'current_year'").fetchone()
        return parse_int(row["value"] if row else None) or PLAYER_CONTRACT_SEASONS[0]

    def _players_have_row_state_conn(self, conn: sqlite3.Connection) -> bool:
        return any(
            row["name"] == "row_state"
            for row in conn.execute("PRAGMA table_info(players)").fetchall()
        )

    def _infer_player_row_state_conn(
        self,
        conn: sqlite3.Connection,
        player: sqlite3.Row,
        current_year: Optional[int] = None,
    ) -> str:
        year = int(current_year if current_year is not None else self._current_year_conn(conn))
        if self._player_row_is_retained_rights_only(player, year, conn):
            return PLAYER_ROW_STATE_RETAINED_RIGHTS
        return PLAYER_ROW_STATE_ACTIVE

    def _sync_player_row_state_conn(
        self,
        conn: sqlite3.Connection,
        player_id: Any,
        timestamp: Optional[str] = None,
    ) -> Optional[str]:
        if not self._players_have_row_state_conn(conn):
            return None
        parsed_player_id = parse_int(player_id)
        if parsed_player_id is None:
            return None
        row = conn.execute(
            """
            SELECT p.*, t.code AS team_code
            FROM players p
            JOIN teams t ON t.id = p.team_id
            WHERE p.id = ?
            """,
            (int(parsed_player_id),),
        ).fetchone()
        if not row:
            return None
        state = self._infer_player_row_state_conn(conn, row)
        if str(row["row_state"] or "") != state:
            conn.execute(
                """
                UPDATE players
                SET row_state = ?,
                    updated_at = COALESCE(?, updated_at)
                WHERE id = ?
                """,
                (state, timestamp, int(parsed_player_id)),
            )
        return state


    def _duplicate_active_profile_ids_conn(self, conn: sqlite3.Connection) -> List[int]:
        if not self._players_have_row_state_conn(conn):
            return []
        rows = conn.execute(
            """
            SELECT profile_id
            FROM players
            WHERE profile_id IS NOT NULL
              AND row_state = ?
            GROUP BY profile_id
            HAVING COUNT(*) > 1
            """,
            (PLAYER_ROW_STATE_ACTIVE,),
        ).fetchall()
        return [int(row["profile_id"]) for row in rows if parse_int(row["profile_id"]) is not None]

    def _profile_has_active_contract_conn(self, conn: sqlite3.Connection, profile_id: Any) -> bool:
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None:
            return False
        current_year = self._current_year_conn(conn)
        rows = conn.execute(
            """
            SELECT p.*, t.code AS team_code
            FROM players p
            JOIN teams t ON t.id = p.team_id
            WHERE p.profile_id = ?
            """,
            (int(parsed_profile_id),),
        ).fetchall()
        has_row_state = self._players_have_row_state_conn(conn)
        has_active_contract = False
        for row in rows:
            inferred_state = self._infer_player_row_state_conn(conn, row, int(current_year))
            if has_row_state and str(row["row_state"] or "") != inferred_state:
                conn.execute(
                    "UPDATE players SET row_state = ? WHERE id = ?",
                    (inferred_state, int(row["id"])),
                )
            if inferred_state == PLAYER_ROW_STATE_ACTIVE:
                has_active_contract = True
        return has_active_contract

    def _upsert_draft_pick_identity_conn(
        self,
        conn: sqlite3.Connection,
        draft_year: Any,
        draft_round: Any,
        original_team: Any,
        timestamp: Optional[str] = None,
    ) -> Optional[int]:
        year = parse_int(draft_year)
        round_value = normalize_pick_round(draft_round)
        team_code = normalize_team_code(original_team)
        if year is None or round_value not in {"1st", "2nd"} or not team_code:
            return None
        now = timestamp or now_iso()
        conn.execute(
            """
            INSERT INTO draft_picks (
                draft_year, draft_round, original_team, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(draft_year, draft_round, original_team) DO UPDATE SET
                updated_at = excluded.updated_at
            """,
            (int(year), round_value, team_code, now, now),
        )
        row = conn.execute(
            """
            SELECT id
            FROM draft_picks
            WHERE draft_year = ? AND draft_round = ? AND original_team = ?
            """,
            (int(year), round_value, team_code),
        ).fetchone()
        return int(row["id"]) if row else None

    def _sync_draft_pick_asset_identity_conn(
        self,
        conn: sqlite3.Connection,
        asset_id: Any,
        timestamp: Optional[str] = None,
    ) -> None:
        parsed_asset_id = parse_int(asset_id)
        if parsed_asset_id is None:
            return
        if not self._table_exists_conn(conn, "draft_picks") or not self._table_exists_conn(conn, "draft_pick_holdings"):
            return
        now = timestamp or now_iso()
        conn.execute("DELETE FROM draft_pick_holdings WHERE asset_id = ?", (int(parsed_asset_id),))
        row = conn.execute(
            """
            SELECT a.*, t.code AS holder_team
            FROM assets a
            JOIN teams t ON t.id = a.team_id
            WHERE a.id = ? AND a.asset_type = 'draft_pick'
            """,
            (int(parsed_asset_id),),
        ).fetchone()
        if not row:
            return
        draft_year = parse_int(row["year"])
        draft_round = normalize_pick_round(row["draft_round"])
        holder_team = normalize_team_code(row["holder_team"])
        if draft_year is None or draft_round not in {"1st", "2nd"} or not holder_team:
            return

        pick_type = normalize_pick_type(row["draft_pick_type"]) or "own"
        original_owner = normalize_team_code(row["original_owner"])
        original_teams: List[str]
        holder_teams: List[str]
        if pick_type == "sold":
            original_teams = [original_owner or holder_team]
            holder_teams = normalize_team_codes(row["draft_pick_sold_to"]) or [holder_team]
        elif pick_type == "conditional":
            original_teams = normalize_team_codes(row["draft_pick_conditional_teams"]) or [original_owner or holder_team]
            holder_teams = [holder_team]
        elif pick_type == "acquired":
            original_teams = [original_owner or holder_team]
            holder_teams = [holder_team]
        else:
            original_teams = [holder_team]
            holder_teams = [holder_team]

        conditions = str(row["detail"] or "").strip() or None
        frozen_status = "frozen" if parse_bool(row["draft_pick_frozen"]) else None
        for original_team in sorted({team for team in original_teams if team}):
            draft_pick_id = self._upsert_draft_pick_identity_conn(
                conn,
                int(draft_year),
                draft_round,
                original_team,
                now,
            )
            if draft_pick_id is None:
                continue
            for holding_team in sorted({team for team in holder_teams if team}):
                conn.execute(
                    """
                    INSERT INTO draft_pick_holdings (
                        draft_pick_id, holder_team, asset_id, acquired_transaction_id,
                        conditions, frozen_status, holding_type, created_at, updated_at
                    ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?)
                    ON CONFLICT(draft_pick_id, holder_team, asset_id) DO UPDATE SET
                        conditions = excluded.conditions,
                        frozen_status = excluded.frozen_status,
                        holding_type = excluded.holding_type,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(draft_pick_id),
                        holding_team,
                        int(parsed_asset_id),
                        conditions,
                        frozen_status,
                        pick_type,
                        now,
                        now,
                    ),
                )


    def _existing_profile_id(self, conn: sqlite3.Connection, profile_id: Any) -> Optional[int]:
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None:
            return None
        row = conn.execute("SELECT id FROM player_profiles WHERE id = ?", (parsed_profile_id,)).fetchone()
        return int(row["id"]) if row else None

    def _resolve_profile_for_new_row(
        self,
        conn: sqlite3.Connection,
        payload: Dict[str, Any],
        *,
        name: Any,
        timestamp: str,
        forbid_active_contract: bool = False,
        require_available: bool = False,
    ) -> int:
        profile_id = self._existing_profile_id(conn, payload.get("profile_id"))
        if profile_id is not None:
            if require_available:
                status_row = conn.execute(
                    "SELECT profile_status FROM player_profiles WHERE id = ?",
                    (profile_id,),
                ).fetchone()
                if status_row and is_unavailable_player_profile_status(status_row["profile_status"]):
                    raise ValueError("profile_unavailable")
            if forbid_active_contract:
                if self._profile_has_active_contract_conn(conn, profile_id):
                    raise ValueError("profile_has_active_contract")
            return profile_id

        return self._create_player_profile(
            conn,
            name,
            payload.get("experience_years"),
            payload.get("reference_image_url"),
            payload.get("profile_notes"),
            timestamp,
        )




    def _clean_salary_history_value(self, salary_text: Any, salary_num: Any) -> Dict[str, Any]:
        text = str(salary_text or "").strip() or None
        numeric = parse_float(salary_num)
        if numeric is None and text:
            numeric = parse_amount_like(text)
        if numeric is not None and not math.isfinite(float(numeric)):
            numeric = None
        return {
            "text": text,
            "num": float(numeric) if numeric is not None else None,
        }

    def _player_profile_exists_conn(self, conn: sqlite3.Connection, profile_id: Any) -> bool:
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None:
            return False
        return conn.execute("SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1", (parsed_profile_id,)).fetchone() is not None

    def _table_exists_conn(self, conn: sqlite3.Connection, table_name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone() is not None

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
        parsed_profile_id = parse_int(profile_id)
        parsed_season_year = parse_int(season_year)
        if parsed_profile_id is None or parsed_season_year is None:
            return False
        if not self._player_profile_exists_conn(conn, parsed_profile_id):
            return False
        cleaned = self._clean_salary_history_value(salary_text, salary_num)
        if cleaned["text"] is None and cleaned["num"] is None:
            return False
        now = timestamp or now_iso()
        conn.execute(
            """
            INSERT INTO player_salary_history (
                profile_id, player_id, team_code, season_year, salary_text,
                salary_num, salary_type, source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, season_year)
            DO UPDATE SET
                player_id = COALESCE(excluded.player_id, player_salary_history.player_id),
                team_code = COALESCE(excluded.team_code, player_salary_history.team_code),
                salary_text = COALESCE(excluded.salary_text, player_salary_history.salary_text),
                salary_num = COALESCE(excluded.salary_num, player_salary_history.salary_num),
                salary_type = COALESCE(excluded.salary_type, player_salary_history.salary_type),
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                parsed_profile_id,
                parse_int(player_id),
                normalize_team_code(team_code),
                parsed_season_year,
                cleaned["text"],
                cleaned["num"],
                str(salary_type or "").strip() or None,
                str(source or "unknown").strip() or "unknown",
                now,
                now,
            ),
        )
        return True

    def _store_player_salary_history_for_season_conn(
        self,
        conn: sqlite3.Connection,
        season_year: int,
        timestamp: Optional[str] = None,
        source: str = "season_rollover",
    ) -> int:
        text_col = f"salary_{int(season_year)}_text"
        num_col = f"salary_{int(season_year)}_num"
        player_cols = {row["name"] for row in conn.execute("PRAGMA table_info(players)").fetchall()}
        if text_col not in player_cols and num_col not in player_cols:
            return 0
        rows = conn.execute(
            f"""
            SELECT
                p.id,
                p.profile_id,
                t.code AS team_code,
                p.bird_rights AS salary_type,
                {text_col if text_col in player_cols else "NULL"} AS salary_text,
                {num_col if num_col in player_cols else "NULL"} AS salary_num
            FROM players p
            JOIN teams t ON t.id = p.team_id
            ORDER BY p.id
            """
        ).fetchall()
        count = 0
        for row in rows:
            profile_id = parse_int(row["profile_id"])
            if profile_id is None:
                profile_id = self._ensure_profile_for_player(conn, int(row["id"]), timestamp)
            if self._upsert_player_salary_history_row_conn(
                conn,
                profile_id=profile_id,
                player_id=row["id"],
                team_code=row["team_code"],
                season_year=season_year,
                salary_text=row["salary_text"],
                salary_num=row["salary_num"],
                salary_type=row["salary_type"],
                source=source,
                timestamp=timestamp,
            ):
                count += 1
        return count

    def _unique_profile_name_map_conn(self, conn: sqlite3.Connection) -> Dict[str, int]:
        rows = conn.execute(
            """
            SELECT lower(trim(name)) AS name_key, MIN(id) AS id, COUNT(*) AS count
            FROM player_profiles
            WHERE COALESCE(trim(name), '') != ''
            GROUP BY lower(trim(name))
            HAVING COUNT(*) = 1
            """
        ).fetchall()
        return {str(row["name_key"]): int(row["id"]) for row in rows if row["name_key"]}



    def _attach_player_salary_history_conn(
        self,
        conn: sqlite3.Connection,
        players: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        profile_ids = sorted({
            parse_int(player.get("profile_id"))
            for player in players
            if parse_int(player.get("profile_id")) is not None
        })
        if not profile_ids:
            return players
        if not self._table_exists_conn(conn, "player_salary_history"):
            return players
        placeholders = ",".join("?" for _ in profile_ids)
        rows = conn.execute(
            f"""
            SELECT profile_id, season_year, salary_text, salary_num, salary_type, team_code
            FROM player_salary_history
            WHERE profile_id IN ({placeholders})
            """,
            profile_ids,
        ).fetchall()
        history: Dict[int, Dict[int, sqlite3.Row]] = {}
        for row in rows:
            profile_id = parse_int(row["profile_id"])
            season_year = parse_int(row["season_year"])
            if profile_id is None or season_year is None:
                continue
            history.setdefault(profile_id, {})[season_year] = row
        for player in players:
            profile_id = parse_int(player.get("profile_id"))
            if profile_id is None:
                continue
            for season_year, row in history.get(profile_id, {}).items():
                player[f"salary_{season_year}_history_text"] = row["salary_text"]
                player[f"salary_{season_year}_history_num"] = row["salary_num"]
                player[f"salary_{season_year}_history_type"] = row["salary_type"]
                player[f"salary_{season_year}_history_team_code"] = row["team_code"]
        return players

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
        def valid_profile_id(value: Any) -> Optional[int]:
            parsed = parse_int(value)
            if parsed is None:
                return None
            exists = conn.execute("SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1", (parsed,)).fetchone()
            return parsed if exists else None

        parsed_player_id = parse_int(player_id)
        if parsed_player_id is not None:
            row = conn.execute("SELECT profile_id FROM players WHERE id = ?", (parsed_player_id,)).fetchone()
            profile_id = valid_profile_id(row["profile_id"]) if row else None
            if profile_id is not None:
                return profile_id

        parsed_free_agent_id = parse_int(free_agent_id)
        if parsed_free_agent_id is not None:
            row = conn.execute("SELECT profile_id FROM free_agents WHERE id = ?", (parsed_free_agent_id,)).fetchone()
            profile_id = valid_profile_id(row["profile_id"]) if row else None
            if profile_id is not None:
                return profile_id

        parsed_dead_contract_id = parse_int(dead_contract_id)
        if parsed_dead_contract_id is not None:
            row = conn.execute("SELECT profile_id FROM dead_contracts WHERE id = ?", (parsed_dead_contract_id,)).fetchone()
            profile_id = valid_profile_id(row["profile_id"]) if row else None
            if profile_id is not None:
                return profile_id

        profile_name = str(name or "").strip()
        if profile_name:
            row = conn.execute(
                """
                SELECT id
                FROM player_profiles
                WHERE lower(trim(name)) = lower(trim(?))
                ORDER BY id
                LIMIT 1
                """,
                (profile_name,),
            ).fetchone()
            if row:
                return int(row["id"])
        return None


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
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None:
            return
        profile_exists = conn.execute(
            "SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1",
            (parsed_profile_id,),
        ).fetchone()
        if not profile_exists:
            return
        action_text = str(action or "").strip().lower() or "update"
        summary_text = str(summary or "").strip() or "Movimiento registrado"
        parsed_source_log_id = parse_int(source_log_id)
        if parsed_source_log_id is not None:
            exists = conn.execute(
                """
                SELECT 1
                FROM player_transactions
                WHERE source_log_id = ?
                  AND profile_id = ?
                  AND action = ?
                  AND summary = ?
                LIMIT 1
                """,
                (parsed_source_log_id, parsed_profile_id, action_text, summary_text),
            ).fetchone()
            if exists:
                return

        conn.execute(
            """
            INSERT INTO player_transactions (
                profile_id, player_id, free_agent_id, dead_contract_id, action,
                team_code, from_team_code, to_team_code, summary, details_json, source_log_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_profile_id,
                parse_int(player_id),
                parse_int(free_agent_id),
                parse_int(dead_contract_id),
                action_text,
                normalize_team_code(team_code),
                normalize_team_code(from_team_code),
                normalize_team_code(to_team_code),
                summary_text,
                json.dumps(details or {}, ensure_ascii=True) if details else None,
                parsed_source_log_id,
                created_at or now_iso(),
            ),
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

    def _player_rows_from_cursor(self, cursor: sqlite3.Cursor, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        return self._player_repository.rows_from_cursor(cursor, rows)

    def _select_team_players(self, conn: sqlite3.Connection, team_id: int) -> List[Dict[str, Any]]:
        return self._player_repository.select_team(conn, team_id)

    def _ensure_profile_for_player(
        self,
        conn: sqlite3.Connection,
        player_id: int,
        timestamp: Optional[str] = None,
    ) -> Optional[int]:
        row = conn.execute(
            """
            SELECT id, profile_id, name, experience_years, reference_image_url, profile_notes, created_at, updated_at
            FROM players
            WHERE id = ?
            """,
            (player_id,),
        ).fetchone()
        if not row:
            return None
        existing = parse_int(row["profile_id"])
        if existing is not None:
            return existing
        profile_id = self._create_player_profile(
            conn,
            row["name"],
            row["experience_years"],
            row["reference_image_url"],
            row["profile_notes"],
            timestamp or row["created_at"] or row["updated_at"] or now_iso(),
        )
        conn.execute("UPDATE players SET profile_id = ? WHERE id = ?", (profile_id, player_id))
        return profile_id

    def get_settings(self) -> Dict[str, str]:
        return self._settings_repository.get_all()

    def create_press_article(
        self,
        body: str,
        image_bytes: bytes,
        image_mime_type: str,
        session: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._press_article_repository.create(body, image_bytes, image_mime_type, session)

    def update_press_article_discord(self, article_id: int, channel_id: str, message_id: str) -> None:
        self._press_article_repository.update_discord(article_id, channel_id, message_id)

    def list_press_articles(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._press_article_repository.list(limit)

    def get_press_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        return self._press_article_repository.get(article_id)

    def get_press_article_image(self, article_id: int) -> Optional[tuple[bytes, str]]:
        return self._press_article_repository.image(article_id)
    def _snapshot_payload_for_season(self, conn: sqlite3.Connection, season_year: int, settings: Dict[str, str]) -> Dict[str, Any]:
        team_cur = conn.execute("SELECT * FROM teams ORDER BY code")
        teams = [row_to_dict(team_cur, row) for row in team_cur.fetchall()]
        payload_teams: List[Dict[str, Any]] = []
        for team in teams:
            team_id = team["id"]
            players = self._select_team_players(conn, int(team_id))
            assets_cur = conn.execute(
                "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                (team_id,),
            )
            assets = [row_to_dict(assets_cur, row) for row in assets_cur.fetchall()]
            dead_cur = conn.execute(
                "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                (team_id,),
            )
            dead_contracts = [row_to_dict(dead_cur, row) for row in dead_cur.fetchall()]
            move_log_cur = conn.execute(
                """
                SELECT id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
                FROM team_move_logs
                WHERE team_id = ? AND season_year = ?
                ORDER BY id ASC
                """,
                (team_id, season_year),
            )
            move_logs = [row_to_dict(move_log_cur, row) for row in move_log_cur.fetchall()]
            luxury_repeater = self._team_luxury_repeater_for_season(conn, int(team_id), season_year)
            summary = self._calc_summary(
                team,
                players,
                assets,
                dead_contracts,
                settings,
                season_year=season_year,
                luxury_repeater=luxury_repeater,
            )
            payload_teams.append(
                {
                    "team": team,
                    "players": players,
                    "assets": assets,
                    "dead_contracts": dead_contracts,
                    "move_logs": move_logs,
                    "summary": summary,
                }
            )
        return {
            "season_year": season_year,
            "season_label": f"{season_year}-{str((season_year + 1) % 100).zfill(2)}",
            "created_at": now_iso(),
            "settings": settings,
            "teams": payload_teams,
        }

    def _team_move_log_rows(self, conn: sqlite3.Connection, team_id: int, season_year: int) -> List[Dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
            FROM team_move_logs
            WHERE team_id = ? AND season_year = ?
            ORDER BY id DESC
            """,
            (team_id, season_year),
        )
        rows = [row_to_dict(cur, row) for row in cur.fetchall()]
        for row in rows:
            raw = row.get("detail_json")
            try:
                row["details"] = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                row["details"] = {}
        return rows

    def _team_move_summary(self, conn: sqlite3.Connection, team_id: int, season_year: int, settings: Dict[str, str]) -> Dict[str, Any]:
        limit_pre30 = max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0)
        limit_post30 = max(0, parse_int(settings.get("trade_move_limit_post30")) or 0)
        phase = normalize_move_phase(settings.get("trade_move_phase"))
        rows = self._team_move_log_rows(conn, team_id, season_year)
        used_pre30 = sum(int(row.get("delta") or 0) for row in rows if normalize_trade_bucket(row.get("bucket")) == "pre30")
        used_post30 = sum(int(row.get("delta") or 0) for row in rows if normalize_trade_bucket(row.get("bucket")) == "post30")
        return {
            "season_year": int(season_year),
            "phase": phase,
            "limit_pre30": limit_pre30,
            "limit_post30": limit_post30,
            "used_pre30": used_pre30,
            "used_post30": used_post30,
            "remaining_pre30": limit_pre30 - used_pre30,
            "remaining_post30": limit_post30 - used_post30,
            "log": rows,
        }

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

    def _trade_move_availability_for_bucket(self, move_summary: Dict[str, Any], bucket: str) -> Dict[str, Any]:
        bucket_key = normalize_trade_bucket(bucket)
        pre_remaining = parse_int(move_summary.get("remaining_pre30"))
        post_remaining = parse_int(move_summary.get("remaining_post30"))
        pre_available = max(0, pre_remaining or 0)
        post_available = max(0, post_remaining or 0)
        if bucket_key == "post30":
            return {
                "bucket": bucket_key,
                "remaining": pre_available + post_available,
                "pre_remaining": pre_available,
                "post_remaining": post_available,
                "label": "pre-30/post-30",
            }
        return {
            "bucket": bucket_key,
            "remaining": pre_available,
            "pre_remaining": pre_available,
            "post_remaining": post_available,
            "label": "pre-30",
        }

    def update_setting(self, key: str, value: str) -> None:
        self._settings_repository.update(key, value)

    def _free_agent_offer_thread_key(self, free_agent: Dict[str, Any]) -> tuple[Optional[int], str, str]:
        profile_id = parse_int(free_agent.get("profile_id"))
        player_name = str(free_agent.get("name") or free_agent.get("profile_name") or "Jugador").strip() or "Jugador"
        normalized_name = unicodedata.normalize("NFKD", player_name)
        name_key = re.sub(r"[^a-z0-9]+", "-", normalized_name.encode("ascii", "ignore").decode("ascii").lower())
        name_key = name_key.strip("-") or re.sub(r"\W+", "-", player_name.lower()).strip("-") or "jugador"
        return profile_id, name_key[:160], player_name

    def get_free_agent_offer_thread(self, free_agent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        profile_id, name_key, _player_name = self._free_agent_offer_thread_key(free_agent)
        with self.connect() as conn:
            if profile_id is not None:
                row = conn.execute(
                    """
                    SELECT *
                    FROM discord_free_agent_offer_threads
                    WHERE profile_id = ?
                    LIMIT 1
                    """,
                    (profile_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT *
                    FROM discord_free_agent_offer_threads
                    WHERE profile_id IS NULL AND player_name_key = ?
                    LIMIT 1
                    """,
                    (name_key,),
                ).fetchone()
            return dict(row) if row else None

    def upsert_free_agent_offer_thread(
        self,
        free_agent: Dict[str, Any],
        thread_id: str,
        thread_name: str,
    ) -> None:
        clean_thread_id = re.sub(r"\D+", "", str(thread_id or ""))
        if not clean_thread_id:
            return
        profile_id, name_key, player_name = self._free_agent_offer_thread_key(free_agent)
        timestamp = now_iso()
        with self.connect() as conn:
            if profile_id is not None:
                conn.execute(
                    """
                    INSERT INTO discord_free_agent_offer_threads (
                        profile_id, player_name_key, player_name, thread_id, thread_name, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id) WHERE profile_id IS NOT NULL
                    DO UPDATE SET
                        player_name_key = excluded.player_name_key,
                        player_name = excluded.player_name,
                        thread_id = excluded.thread_id,
                        thread_name = excluded.thread_name,
                        updated_at = excluded.updated_at
                    """,
                    (profile_id, name_key, player_name, clean_thread_id, thread_name, timestamp, timestamp),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO discord_free_agent_offer_threads (
                        profile_id, player_name_key, player_name, thread_id, thread_name, created_at, updated_at
                    )
                    VALUES (NULL, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(player_name_key) WHERE profile_id IS NULL
                    DO UPDATE SET
                        player_name = excluded.player_name,
                        thread_id = excluded.thread_id,
                        thread_name = excluded.thread_name,
                        updated_at = excluded.updated_at
                    """,
                    (name_key, player_name, clean_thread_id, thread_name, timestamp, timestamp),
                )
            conn.commit()

    def _increment_player_bird_years(self, conn: sqlite3.Connection, seasons: int, timestamp: str) -> int:
        steps = max(0, int(seasons or 0))
        if steps <= 0:
            return 0
        cur = conn.execute("SELECT id, years_left FROM players")
        updates: List[tuple[Optional[str], str, int]] = []
        for row in cur.fetchall():
            normalized_current = normalize_bird_years(row["years_left"])
            next_value = increment_bird_years_value(row["years_left"], steps)
            if next_value != normalized_current:
                updates.append((next_value, timestamp, int(row["id"])))
        if updates:
            conn.executemany(
                "UPDATE players SET years_left = ?, updated_at = ? WHERE id = ?",
                updates,
            )
        return len(updates)

    def _move_expired_players_to_free_agents(
        self,
        conn: sqlite3.Connection,
        season_year: int,
        timestamp: str,
    ) -> int:
        season = parse_int(season_year)
        if season is None or season < PLAYER_CONTRACT_MIN_YEAR or season > PLAYER_CONTRACT_MAX_YEAR:
            return 0
        salary_text_field = f"salary_{season}_text"
        salary_num_field = f"salary_{season}_num"
        option_field = f"option_{season}"
        cur = conn.execute(
            f"""
            SELECT
                p.id,
                p.profile_id,
                COALESCE(pp.name, p.name) AS name,
                p.position,
                p.bird_rights,
                p.rating,
                p.years_left,
                p.notes,
                p.{salary_text_field} AS season_salary_text,
                p.{salary_num_field} AS season_salary_num,
                p.{option_field} AS season_option,
                t.code AS team_code
            FROM players p
            LEFT JOIN player_profiles pp ON pp.id = p.profile_id
            JOIN teams t ON t.id = p.team_id
            ORDER BY p.id
            """
        )
        moved = 0
        for row in cur.fetchall():
            salary_text = str(row["season_salary_text"] or "").strip()
            salary_num = parse_float(row["season_salary_num"])
            option_value = str(row["season_option"] or "").strip()
            if salary_text or salary_num is not None or option_value:
                continue
            player_id = int(row["id"])
            profile_id = parse_int(row["profile_id"])
            if profile_id is None:
                profile_id = self._ensure_profile_for_player(conn, player_id, timestamp)
            active_elsewhere = None
            if profile_id is not None:
                active_elsewhere = conn.execute(
                    f"""
                    SELECT id
                    FROM players
                    WHERE profile_id = ?
                        AND id != ?
                        AND (
                            COALESCE(TRIM({salary_text_field}), '') != ''
                            OR {salary_num_field} IS NOT NULL
                            OR COALESCE(TRIM({option_field}), '') != ''
                        )
                    LIMIT 1
                    """,
                    (profile_id, player_id),
                ).fetchone()
            if active_elsewhere:
                conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
                moved += 1
                continue

            free_agent_id: Optional[int] = None
            if profile_id is not None:
                existing_free_agent = conn.execute(
                    "SELECT id FROM free_agents WHERE profile_id = ? LIMIT 1",
                    (profile_id,),
                ).fetchone()
                if existing_free_agent:
                    free_agent_id = int(existing_free_agent["id"])
            if free_agent_id is None:
                free_cur = conn.execute(
                    """
                    INSERT INTO free_agents (
                        profile_id, name, position, bird_rights, rating, years_left, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        row["name"] or "Free Agent",
                        row["position"],
                        row["bird_rights"],
                        row["rating"],
                        row["years_left"],
                        row["notes"],
                        timestamp,
                        timestamp,
                    ),
                )
                free_agent_id = int(free_cur.lastrowid)
            self._record_player_transaction(
                conn,
                profile_id,
                "free_agent",
                f"Pasa a agentes libres al avanzar a {season}-{(season + 1) % 100:02d}",
                player_id=player_id,
                free_agent_id=free_agent_id,
                team_code=row["team_code"],
                from_team_code=row["team_code"],
                details={"player_name": row["name"], "season_year": season},
                created_at=timestamp,
            )
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            moved += 1
        return moved

    def _freeze_second_apron_pick_rollover(
        self,
        conn: sqlite3.Connection,
        previous_year: int,
        next_year: int,
        settings: Dict[str, str],
        timestamp: str,
    ) -> List[Dict[str, Any]]:
        if int(next_year) <= int(previous_year):
            return []
        frozen_rows: List[Dict[str, Any]] = []
        teams_cur = conn.execute("SELECT * FROM teams ORDER BY code")
        teams = [row_to_dict(teams_cur, row) for row in teams_cur.fetchall()]
        for penalty_year in range(int(previous_year), int(next_year)):
            frozen_draft_year = int(penalty_year) + 8
            for team in teams:
                team_id = int(team["id"])
                players = self._select_team_players(conn, team_id)
                assets_cur = conn.execute(
                    "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                    (team_id,),
                )
                assets = [row_to_dict(assets_cur, row) for row in assets_cur.fetchall()]
                dead_cur = conn.execute(
                    "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                    (team_id,),
                )
                dead_contracts = [row_to_dict(dead_cur, row) for row in dead_cur.fetchall()]
                luxury_repeater = self._team_luxury_repeater_for_season(conn, team_id, int(penalty_year))
                hard_cap = self._team_apron_hard_cap_for_season(conn, team_id, int(penalty_year), team.get("apron_hard_cap"))
                summary = self._calc_summary(
                    team,
                    players,
                    assets,
                    dead_contracts,
                    settings,
                    season_year=int(penalty_year),
                    luxury_repeater=luxury_repeater,
                    apron_hard_cap=hard_cap,
                )
                if float(summary.get("apron_account") or 0.0) <= float(summary.get("second_apron") or 0.0):
                    continue
                frozen_rows.append(
                    self._upsert_frozen_draft_pick_conn(
                        conn,
                        team_id,
                        str(team["code"]),
                        int(penalty_year),
                        int(frozen_draft_year),
                        "1st",
                        "Finalizó por encima del 2do apron",
                        "Bloqueo automático al avanzar la temporada.",
                        timestamp,
                    )
                )
        return frozen_rows

    def _create_missing_future_draft_assets_conn(
        self,
        conn: sqlite3.Connection,
        draft_year: int,
        timestamp: str,
    ) -> List[Dict[str, Any]]:
        created: List[Dict[str, Any]] = []
        teams_cur = conn.execute("SELECT id, code FROM teams ORDER BY code")
        teams = [row_to_dict(teams_cur, row) for row in teams_cur.fetchall()]
        for team in teams:
            team_id = int(team["id"])
            team_code = str(team["code"])
            max_order = int(
                conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (team_id,),
                ).fetchone()["mx"]
                or 0
            )
            for draft_round in ("1st", "2nd"):
                existing = conn.execute(
                    """
                    SELECT 1
                    FROM assets
                    WHERE team_id = ?
                      AND asset_type = 'draft_pick'
                      AND CAST(COALESCE(year, '') AS INTEGER) = ?
                      AND COALESCE(draft_round, '1st') = ?
                      AND COALESCE(LOWER(draft_pick_type), 'own') IN ('own', 'sold')
                    LIMIT 1
                    """,
                    (team_id, int(draft_year), draft_round),
                ).fetchone()
                if existing:
                    continue
                max_order += 1
                cur = conn.execute(
                    """
                    INSERT INTO assets (
                        team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                        draft_pick_type, draft_round, original_owner, exception_type,
                        draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                        draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                        created_at, updated_at
                    )
                    VALUES (?, ?, 'draft_pick', ?, ?, '', NULL, NULL, 'own', ?, NULL, NULL, 0, 0, 0, NULL, NULL, 0, ?, ?)
                    """,
                    (
                        team_id,
                        max_order,
                        int(draft_year),
                        f"{draft_round} pick",
                        draft_round,
                        timestamp,
                        timestamp,
                    ),
                )
                created.append(
                    {
                        "id": int(cur.lastrowid),
                        "team_code": team_code,
                        "year": int(draft_year),
                        "draft_round": draft_round,
                    }
                )
        return created

    def _rollover_draft_assets_conn(
        self,
        conn: sqlite3.Connection,
        previous_year: int,
        next_year: int,
        timestamp: str,
    ) -> Dict[str, Any]:
        if int(next_year) <= int(previous_year):
            return {
                "deleted_draft_assets": 0,
                "deleted_draft_asset_years": [],
                "future_draft_asset_years": [],
                "created_future_draft_assets": [],
            }

        deleted_total = 0
        deleted_years: List[Dict[str, int]] = []
        for season_year in range(int(previous_year), int(next_year)):
            expiring_asset_year = int(season_year) + 1
            deleted = (
                conn.execute(
                    "DELETE FROM assets WHERE asset_type = 'draft_pick' AND CAST(COALESCE(year, '') AS INTEGER) = ?",
                    (expiring_asset_year,),
                ).rowcount
                or 0
            )
            deleted_total += int(deleted)
            deleted_years.append({"year": expiring_asset_year, "count": int(deleted)})

        created: List[Dict[str, Any]] = []
        future_years: List[int] = []
        for season_year in range(int(previous_year) + 1, int(next_year) + 1):
            future_draft_year = int(season_year) + 7
            future_years.append(future_draft_year)
            created.extend(self._create_missing_future_draft_assets_conn(conn, future_draft_year, timestamp))

        return {
            "deleted_draft_assets": deleted_total,
            "deleted_draft_asset_years": deleted_years,
            "future_draft_asset_years": future_years,
            "created_future_draft_assets": created,
        }

    def _cleanup_inactive_dead_contracts_conn(
        self,
        conn: sqlite3.Connection,
        current_year: int,
    ) -> Dict[str, Any]:
        active_seasons = [season for season in PLAYER_CONTRACT_SEASONS if season >= int(current_year)]
        cur = conn.execute(
            """
            SELECT d.*, t.code AS team_code
            FROM dead_contracts d
            JOIN teams t ON t.id = d.team_id
            ORDER BY d.id
            """
        )
        removed: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            dead_contract = row_to_dict(cur, row)
            has_active_salary = any(
                dead_contract_salary_num(dead_contract, season) > 0
                for season in active_seasons
            )
            if has_active_salary:
                continue
            removed.append(
                {
                    "id": int(dead_contract["id"]),
                    "team_code": dead_contract.get("team_code"),
                    "label": dead_contract.get("label"),
                }
            )

        if removed:
            conn.executemany(
                "DELETE FROM dead_contracts WHERE id = ?",
                [(item["id"],) for item in removed],
            )

        return {
            "count": len(removed),
            "dead_contracts": removed,
        }

    def update_current_year(self, next_year: int) -> Dict[str, Any]:
        return self._season_rollover_service().update_current_year(next_year)

    def progress_to_next_year(self) -> Dict[str, Any]:
        return self._season_rollover_service().progress_to_next_year()

    def _season_rollover_service(self) -> SeasonRolloverService:
        return SeasonRolloverService(
            self,
            contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
            contract_max_start_year=PLAYER_CONTRACT_MAX_START_YEAR,
        )

    def upsert_google_user(self, google_sub: str, email: str, display_name: Optional[str], avatar_url: Optional[str]) -> Dict[str, Any]:
        return self._user_repository.upsert_google_user(google_sub, email, display_name, avatar_url)

    def get_user_team_codes_by_email(self, email: str) -> List[str]:
        return self._user_repository.team_codes_by_email(email)

    def list_users(self) -> List[Dict[str, Any]]:
        return self._user_repository.list()

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
    def _coadmin_vote_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = row_to_dict(cursor, row)
        item["id"] = parse_int(item.get("id"))
        item["status"] = str(item.get("status") or "open").strip().lower() or "open"
        return item

    def _coadmin_expected_voters(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                u.id,
                u.email,
                u.display_name,
                GROUP_CONCAT(t.code, ',') AS team_codes
            FROM users u
            LEFT JOIN user_team_assignments a ON a.user_id = u.id
            LEFT JOIN teams t ON t.id = a.team_id
            WHERE COALESCE(u.is_co_admin, 0) = 1
            GROUP BY u.id
            ORDER BY lower(u.email)
            """
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "email": row["email"],
                "display_name": row["display_name"],
                "team_codes": normalize_team_codes(row["team_codes"]),
            }
            for row in rows
        ]

    def create_coadmin_vote(self, title: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cleaned_title = str(title or "").strip()
        if not cleaned_title:
            raise ValueError("title_required")
        if len(cleaned_title) > 140:
            raise ValueError("title_too_long")
        actor = actor or {}
        timestamp = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO coadmin_votes (
                    title, status, created_by_email, created_by_name, created_at, updated_at
                ) VALUES (?, 'open', ?, ?, ?, ?)
                """,
                (
                    cleaned_title,
                    str(actor.get("email") or "").strip() or None,
                    str(actor.get("name") or "").strip() or None,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            vote_id = int(cur.lastrowid)
        vote = self.get_coadmin_vote(vote_id)
        if not vote:
            raise RuntimeError("Failed to create co-admin vote")
        return vote

    def get_coadmin_vote(self, vote_id: Any) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(vote_id)
        if parsed_id is None:
            return None
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM coadmin_votes WHERE id = ?", (parsed_id,))
            row = cur.fetchone()
            return self._coadmin_vote_from_row(cur, row) if row else None

    def set_coadmin_vote_status(
        self,
        vote_id: Any,
        status: Any,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(vote_id)
        normalized_status = str(status or "").strip().lower()
        if parsed_id is None:
            raise ValueError("invalid_vote_id")
        if normalized_status not in {"open", "closed"}:
            raise ValueError("invalid_status")
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM coadmin_votes WHERE id = ?", (parsed_id,)).fetchone()
            if not existing:
                return None
            conn.execute(
                """
                UPDATE coadmin_votes
                SET status = ?,
                    updated_at = ?,
                    closed_at = CASE WHEN ? = 'closed' THEN ? ELSE NULL END
                WHERE id = ?
                """,
                (normalized_status, timestamp, normalized_status, timestamp, parsed_id),
            )
            conn.commit()
        return self.get_coadmin_vote(parsed_id)

    def list_admin_coadmin_votes(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            expected_voters = self._coadmin_expected_voters(conn)
            expected_count = len(expected_voters)
            vote_cur = conn.execute(
                """
                SELECT *
                FROM coadmin_votes
                ORDER BY
                    CASE status WHEN 'open' THEN 0 ELSE 1 END,
                    datetime(created_at) DESC,
                    id DESC
                """
            )
            votes = [self._coadmin_vote_from_row(vote_cur, row) for row in vote_cur.fetchall()]
            teams = [dict(row) for row in conn.execute("SELECT id, code, name FROM teams ORDER BY code").fetchall()]
            for vote in votes:
                vote_id = int(vote["id"] or 0)
                submitted_rows = conn.execute(
                    """
                    SELECT DISTINCT voter_user_id
                    FROM coadmin_vote_scores
                    WHERE vote_id = ?
                    """,
                    (vote_id,),
                ).fetchall()
                submitted_ids = {int(row["voter_user_id"]) for row in submitted_rows}
                avg_rows = conn.execute(
                    """
                    SELECT
                        t.id AS team_id,
                        t.code AS team_code,
                        t.name AS team_name,
                        COUNT(s.score) AS vote_count,
                        AVG(s.score) AS average_score
                    FROM teams t
                    LEFT JOIN coadmin_vote_scores s
                        ON s.target_team_id = t.id
                       AND s.vote_id = ?
                    GROUP BY t.id
                    ORDER BY t.code
                    """,
                    (vote_id,),
                ).fetchall()
                averages = []
                for row in avg_rows:
                    average_score = row["average_score"]
                    averages.append(
                        {
                            "team_id": int(row["team_id"]),
                            "team_code": row["team_code"],
                            "team_name": row["team_name"],
                            "vote_count": int(row["vote_count"] or 0),
                            "average_score": round(float(average_score), 2) if average_score is not None else None,
                        }
                    )
                averages.sort(
                    key=lambda item: (
                        item["average_score"] is None,
                        -(item["average_score"] or 0),
                        str(item["team_code"] or ""),
                    )
                )
                score_rows = conn.execute(
                    """
                    SELECT
                        s.voter_user_id,
                        s.voter_email,
                        s.voter_name,
                        s.voter_team_code,
                        t.id AS target_team_id,
                        t.code AS target_team_code,
                        t.name AS target_team_name,
                        s.score,
                        s.updated_at
                    FROM coadmin_vote_scores s
                    JOIN teams t ON t.id = s.target_team_id
                    WHERE s.vote_id = ?
                    ORDER BY
                        lower(COALESCE(NULLIF(s.voter_name, ''), s.voter_email, CAST(s.voter_user_id AS TEXT))),
                        t.code
                    """,
                    (vote_id,),
                ).fetchall()
                voter_lookup = {int(voter["id"]): voter for voter in expected_voters}
                individual_by_voter: Dict[int, Dict[str, Any]] = {}
                for row in score_rows:
                    voter_id = int(row["voter_user_id"])
                    expected_voter = voter_lookup.get(voter_id, {})
                    item = individual_by_voter.setdefault(
                        voter_id,
                        {
                            "voter_user_id": voter_id,
                            "voter_email": row["voter_email"] or expected_voter.get("email"),
                            "voter_name": row["voter_name"] or expected_voter.get("display_name"),
                            "voter_team_code": row["voter_team_code"],
                            "team_codes": expected_voter.get("team_codes") or normalize_team_codes(row["voter_team_code"]),
                            "scores": [],
                        },
                    )
                    item["scores"].append(
                        {
                            "team_id": int(row["target_team_id"]),
                            "team_code": row["target_team_code"],
                            "team_name": row["target_team_name"],
                            "score": int(row["score"]),
                            "updated_at": row["updated_at"],
                        }
                    )
                individual_scores = list(individual_by_voter.values())
                individual_scores.sort(
                    key=lambda item: str(item.get("voter_name") or item.get("voter_email") or item.get("voter_user_id") or "").lower()
                )
                vote["expected_voter_count"] = expected_count
                vote["submitted_voter_count"] = len(submitted_ids)
                vote["all_submitted"] = expected_count > 0 and len(submitted_ids) >= expected_count
                vote["averages"] = averages
                vote["individual_scores"] = individual_scores
                vote["voters"] = [
                    {
                        **voter,
                        "submitted": int(voter["id"]) in submitted_ids,
                    }
                    for voter in expected_voters
                ]
                vote["teams"] = teams
            return votes

    def list_coadmin_votes_for_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        user_id = parse_int(session.get("user_id"))
        role = str(session.get("role") or "").strip().lower()
        if user_id is None or role != "co_admin":
            return {"votes": [], "own_team_codes": []}
        own_team_codes = normalize_team_codes(session.get("team_codes"))
        with self.connect() as conn:
            team_rows = conn.execute("SELECT id, code, name FROM teams ORDER BY code").fetchall()
            target_teams = [
                {"id": int(row["id"]), "code": row["code"], "name": row["name"]}
                for row in team_rows
                if str(row["code"] or "").strip().upper() not in own_team_codes
            ]
            vote_cur = conn.execute(
                """
                SELECT *
                FROM coadmin_votes
                WHERE status = 'open'
                ORDER BY datetime(created_at) DESC, id DESC
                """
            )
            votes = [self._coadmin_vote_from_row(vote_cur, row) for row in vote_cur.fetchall()]
            expected_count = len(self._coadmin_expected_voters(conn))
            for vote in votes:
                vote_id = int(vote["id"] or 0)
                score_rows = conn.execute(
                    """
                    SELECT t.code AS team_code, s.score
                    FROM coadmin_vote_scores s
                    JOIN teams t ON t.id = s.target_team_id
                    WHERE s.vote_id = ? AND s.voter_user_id = ?
                    """,
                    (vote_id, user_id),
                ).fetchall()
                scores = {str(row["team_code"]).upper(): int(row["score"]) for row in score_rows}
                submitted_count = conn.execute(
                    """
                    SELECT COUNT(DISTINCT voter_user_id)
                    FROM coadmin_vote_scores
                    WHERE vote_id = ?
                    """,
                    (vote_id,),
                ).fetchone()[0]
                vote["target_teams"] = target_teams
                vote["scores"] = scores
                vote["submitted"] = len(scores) >= len(target_teams) and len(target_teams) > 0
                vote["submitted_voter_count"] = int(submitted_count or 0)
                vote["expected_voter_count"] = expected_count
            return {"votes": votes, "own_team_codes": own_team_codes}

    def submit_coadmin_vote(
        self,
        vote_id: Any,
        scores: Any,
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        parsed_vote_id = parse_int(vote_id)
        user_id = parse_int(session.get("user_id"))
        if parsed_vote_id is None:
            raise ValueError("invalid_vote_id")
        if user_id is None or str(session.get("role") or "").strip().lower() != "co_admin":
            raise ValueError("coadmin_required")
        if not isinstance(scores, dict):
            raise ValueError("scores_required")
        own_team_codes = normalize_team_codes(session.get("team_codes"))
        with self.connect() as conn:
            vote_row = conn.execute("SELECT id, status FROM coadmin_votes WHERE id = ?", (parsed_vote_id,)).fetchone()
            if not vote_row:
                raise ValueError("vote_not_found")
            if str(vote_row["status"] or "").lower() != "open":
                raise ValueError("vote_closed")

            team_rows = conn.execute("SELECT id, code FROM teams ORDER BY code").fetchall()
            team_by_code = {str(row["code"]).upper(): int(row["id"]) for row in team_rows}
            target_codes = [code for code in team_by_code if code not in own_team_codes]
            normalized_scores: Dict[str, int] = {}
            for raw_code, raw_score in scores.items():
                code = normalize_team_code(raw_code)
                if not code or code not in team_by_code:
                    raise ValueError("invalid_team_code")
                if code in own_team_codes:
                    raise ValueError("own_team_score_not_allowed")
                score = parse_int(raw_score)
                if score is None or score < 1 or score > 100:
                    raise ValueError("invalid_score")
                normalized_scores[code] = int(score)
            missing = [code for code in target_codes if code not in normalized_scores]
            extra = [code for code in normalized_scores if code not in target_codes]
            if missing:
                raise ValueError(f"missing_scores:{','.join(missing)}")
            if extra:
                raise ValueError("invalid_score_targets")

            timestamp = now_iso()
            voter_email = str(session.get("email") or "").strip() or None
            voter_name = str(session.get("name") or "").strip() or None
            voter_team_code = own_team_codes[0] if own_team_codes else None
            for code, score in normalized_scores.items():
                conn.execute(
                    """
                    INSERT INTO coadmin_vote_scores (
                        vote_id,
                        voter_user_id,
                        voter_email,
                        voter_name,
                        voter_team_code,
                        target_team_id,
                        score,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(vote_id, voter_user_id, target_team_id)
                    DO UPDATE SET
                        voter_email = excluded.voter_email,
                        voter_name = excluded.voter_name,
                        voter_team_code = excluded.voter_team_code,
                        score = excluded.score,
                        updated_at = excluded.updated_at
                    """,
                    (
                        parsed_vote_id,
                        user_id,
                        voter_email,
                        voter_name,
                        voter_team_code,
                        team_by_code[code],
                        score,
                        timestamp,
                        timestamp,
                    ),
                )
            conn.execute("UPDATE coadmin_votes SET updated_at = ? WHERE id = ?", (timestamp, parsed_vote_id))
            conn.commit()
        refreshed = self.list_coadmin_votes_for_session(session)
        return next((vote for vote in refreshed.get("votes", []) if int(vote.get("id") or 0) == parsed_vote_id), {})

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

    def _gm_draft_pick_request_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = row_to_dict(cursor, row)
        item["request_type"] = "draft_pick"
        item["player_name"] = str(item.get("selection_text") or "")
        item["option_field"] = "draft_pick"
        item["action"] = "selected"
        draft_year = parse_int(item.get("draft_year"))
        item["season_year"] = draft_year
        item["season_label"] = f"Draft {draft_year}" if draft_year else "Draft"
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
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    r.*,
                    p.name AS player_name,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_option_requests r
                JOIN players p ON p.id = r.player_id
                JOIN teams t ON t.id = r.team_id
                WHERE r.id = ?
                """,
                (int(request_id),),
            )
            row = cur.fetchone()
            return self._gm_option_request_from_row(cur, row) if row else None

    def list_gm_option_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        params: List[Any] = []
        where = ""
        if normalized_status and normalized_status != "all":
            where = "WHERE r.status = ?"
            params.append(normalized_status)
        with self.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT
                    r.*,
                    p.name AS player_name,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_option_requests r
                JOIN players p ON p.id = r.player_id
                JOIN teams t ON t.id = r.team_id
                {where}
                ORDER BY
                    CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                    r.created_at DESC,
                    r.id DESC
                """,
                params,
            )
            option_requests = [self._gm_option_request_from_row(cur, row) for row in cur.fetchall()]

            draft_cur = conn.execute(
                f"""
                SELECT
                    r.*,
                    d.draft_year,
                    d.draft_round,
                    d.pick_number,
                    d.owner_team_code,
                    d.original_team_code,
                    COALESCE(owner.name, d.owner_team_code) AS team_name,
                    owner.code AS team_code,
                    COALESCE(original.name, d.original_team_code) AS original_team_name
                FROM gm_draft_pick_requests r
                JOIN draft_order d ON d.id = r.draft_order_id
                JOIN teams owner ON owner.id = r.team_id
                LEFT JOIN teams original ON original.code = d.original_team_code
                {where}
                ORDER BY
                    CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                    r.created_at DESC,
                    r.id DESC
                """,
                params,
            )
            draft_requests = [self._gm_draft_pick_request_from_row(draft_cur, row) for row in draft_cur.fetchall()]

            free_agent_cur = conn.execute(
                f"""
                SELECT
                    r.*,
                    f.name AS player_name,
                    f.profile_id,
                    f.position,
                    f.rating,
                    f.free_agent_type,
                    f.rights_team_code,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_free_agent_offer_requests r
                LEFT JOIN free_agents f ON f.id = r.free_agent_id
                JOIN teams t ON t.id = r.team_id
                {where}
                ORDER BY
                    CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                    r.created_at DESC,
                    r.id DESC
                """,
                params,
            )
            free_agent_requests = [
                self._gm_free_agent_offer_request_from_row(free_agent_cur, row)
                for row in free_agent_cur.fetchall()
            ]
            waiver_requests = self.list_waiver_claim_requests(status=status)
            requests = [*option_requests, *draft_requests, *free_agent_requests, *waiver_requests]
            requests.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)), reverse=True)
            requests.sort(key=lambda item: 0 if str(item.get("status") or "") == "pending" else 1)
            return requests

    def get_gm_draft_pick_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    r.*,
                    d.draft_year,
                    d.draft_round,
                    d.pick_number,
                    d.owner_team_code,
                    d.original_team_code,
                    COALESCE(owner.name, d.owner_team_code) AS team_name,
                    owner.code AS team_code,
                    COALESCE(original.name, d.original_team_code) AS original_team_name
                FROM gm_draft_pick_requests r
                JOIN draft_order d ON d.id = r.draft_order_id
                JOIN teams owner ON owner.id = r.team_id
                LEFT JOIN teams original ON original.code = d.original_team_code
                WHERE r.id = ?
                """,
                (int(request_id),),
            )
            row = cur.fetchone()
            return self._gm_draft_pick_request_from_row(cur, row) if row else None

    def _get_gm_free_agent_offer_request_conn(
        self,
        conn: sqlite3.Connection,
        request_id: int,
    ) -> Optional[Dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT
                r.*,
                f.name AS player_name,
                f.profile_id,
                f.position,
                f.rating,
                f.free_agent_type,
                f.rights_team_code,
                t.code AS team_code,
                t.name AS team_name
            FROM gm_free_agent_offer_requests r
            LEFT JOIN free_agents f ON f.id = r.free_agent_id
            JOIN teams t ON t.id = r.team_id
            WHERE r.id = ?
            """,
            (int(request_id),),
        )
        row = cur.fetchone()
        return self._gm_free_agent_offer_request_from_row(cur, row) if row else None

    def get_gm_free_agent_offer_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            return self._get_gm_free_agent_offer_request_conn(conn, request_id)

    def create_gm_option_request(
        self,
        player_id: int,
        option_field: str,
        option_value: str,
        action: str,
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        field = str(option_field or "").strip()
        match = re.fullmatch(r"option_(20\d{2})", field)
        if not match:
            raise ValueError("invalid_option_field")
        option = str(option_value or "").strip().upper()
        if option not in {"TO", "QO", "GAP"}:
            raise ValueError("invalid_option_value")
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"accepted", "rejected"}:
            raise ValueError("invalid_option_action")

        timestamp = now_iso()
        request_id: Optional[int] = None
        with self.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT p.id, COALESCE(pp.name, p.name) AS name, p.team_id, p.{field} AS current_option, t.code AS team_code
                FROM players p
                LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (int(player_id),),
            )
            player = cur.fetchone()
            if not player:
                return None
            current_option = str(player["current_option"] or "").strip().upper()
            if current_option != option:
                raise ValueError("option_mismatch")

            existing = conn.execute(
                """
                SELECT id
                FROM gm_option_requests
                WHERE player_id = ? AND option_field = ? AND status = 'pending'
                """,
                (int(player_id), field),
            ).fetchone()
            if existing:
                request_id = int(existing["id"])
                requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
                conn.execute(
                    """
                    UPDATE gm_option_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        option_value = ?,
                        action = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        option,
                        normalized_action,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_option_requests (
                        player_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        option_field,
                        option_value,
                        action,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(player_id),
                        int(player["team_id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        field,
                        option,
                        normalized_action,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
                self._record_workflow_creation_conn(
                    conn,
                    "gm_option_request",
                    request_id,
                    "pending",
                    actor=requester,
                    reason="option_request_submitted",
                    timestamp=timestamp,
                    metadata={
                        "player_id": int(player_id),
                        "option_field": field,
                        "option_value": option,
                        "action": normalized_action,
                    },
                )
            conn.commit()

        return self.get_gm_option_request(request_id) if request_id is not None else None

    def record_admin_option_decision(
        self,
        player_id: int,
        option_field: str,
        option_value: str,
        action: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        field = str(option_field or "").strip()
        match = re.fullmatch(r"option_(20\d{2})", field)
        if not match:
            raise ValueError("invalid_option_field")
        option = str(option_value or "").strip().upper()
        if option not in {"TO", "PO", "QO", "GAP"}:
            raise ValueError("invalid_option_value")
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"accepted", "rejected"}:
            raise ValueError("invalid_option_action")

        timestamp = now_iso()
        with self.transaction("IMMEDIATE") as conn:
            player = conn.execute(
                f"""
                SELECT p.id, p.team_id, p.{field} AS current_option
                FROM players p
                WHERE p.id = ?
                """,
                (int(player_id),),
            ).fetchone()
            if not player:
                return None
            cur = conn.execute(
                """
                INSERT INTO gm_option_requests (
                    player_id,
                    team_id,
                    requester_user_id,
                    requester_email,
                    requester_name,
                    option_field,
                    option_value,
                    action,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    int(player_id),
                    int(player["team_id"]),
                    parse_int(str(admin.get("user_id") or "")) if admin else None,
                    str(admin.get("email") or "").strip() if admin else None,
                    str(admin.get("name") or "").strip() if admin else None,
                    field,
                    option,
                    normalized_action,
                    timestamp,
                    timestamp,
                ),
            )
            request_id = int(cur.lastrowid)
            metadata = {
                "player_id": int(player_id),
                "option_field": field,
                "option_value": option,
                "action": normalized_action,
            }
            self._record_workflow_creation_conn(
                conn,
                "gm_option_request",
                request_id,
                "pending",
                actor=admin,
                reason="admin_option_decision_created",
                command_id=f"gm-option:{request_id}:created",
                metadata=metadata,
                timestamp=timestamp,
            )
            self._transition_workflow_conn(
                conn,
                "gm_option_request",
                request_id,
                "approved",
                actor=admin,
                reason="admin_option_decision_recorded",
                command_id=f"gm-option:{request_id}:approved",
                updates={
                    "admin_email": str(admin.get("email") or "").strip() if admin else None,
                    "admin_name": str(admin.get("name") or "").strip() if admin else None,
                    "admin_decision_note": note,
                    "updated_at": timestamp,
                    "decided_at": timestamp,
                },
                metadata=metadata,
                timestamp=timestamp,
            )
        return self.get_gm_option_request(request_id)

    def create_gm_bird_rights_renounce_request(
        self,
        player_id: int,
        season_year: int,
        rights_value: str,
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        season = parse_int(season_year)
        if season is None or season < PLAYER_CONTRACT_MIN_YEAR or season > PLAYER_CONTRACT_MAX_YEAR:
            raise ValueError("invalid_renounce_season")
        field = f"salary_{season}_text"
        rights = str(rights_value or "").strip().upper()
        if rights not in {"FB", "EB", "NB"}:
            raise ValueError("invalid_bird_rights_value")

        timestamp = now_iso()
        request_id: Optional[int] = None
        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if not parse_bool(settings.get("free_agency_mode")):
                raise ValueError("free_agency_mode_required")
            if season != int(current_year):
                raise ValueError("invalid_renounce_season")

            cur = conn.execute(
                f"""
                SELECT p.id, COALESCE(pp.name, p.name) AS name, p.team_id, p.{field} AS current_rights, t.code AS team_code
                FROM players p
                LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (int(player_id),),
            )
            player = cur.fetchone()
            if not player:
                return None
            current_rights = str(player["current_rights"] or "").strip().upper()
            if current_rights != rights:
                raise ValueError("bird_rights_mismatch")

            existing = conn.execute(
                """
                SELECT id
                FROM gm_option_requests
                WHERE player_id = ? AND option_field = ? AND status = 'pending'
                """,
                (int(player_id), field),
            ).fetchone()
            requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
            if existing:
                request_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE gm_option_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        option_value = ?,
                        action = 'renounced',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        rights,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_option_requests (
                        player_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        option_field,
                        option_value,
                        action,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'renounced', 'pending', ?, ?)
                    """,
                    (
                        int(player_id),
                        int(player["team_id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        field,
                        rights,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
                self._record_workflow_creation_conn(
                    conn,
                    "gm_option_request",
                    request_id,
                    "pending",
                    actor=requester,
                    reason="bird_rights_renounce_requested",
                    timestamp=timestamp,
                    metadata={
                        "player_id": int(player_id),
                        "season_year": int(season),
                        "rights_value": rights,
                    },
                )
            conn.commit()

        return self.get_gm_option_request(request_id) if request_id is not None else None

    def create_gm_draft_pick_request(
        self,
        draft_order_id: int,
        payload: Dict[str, Any],
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        option_value = str(payload.get("option_value") or "").strip()
        custom_text = str(payload.get("custom_text") or "").strip()
        if not option_value:
            raise ValueError("selection_required")
        if option_value == "__other__" and not custom_text:
            raise ValueError("selection_required")
        selection_text = custom_text if option_value == "__other__" else option_value
        selection_text = selection_text.strip()
        if not selection_text:
            raise ValueError("selection_required")
        if len(selection_text) > 140:
            raise ValueError("selection_too_long")

        timestamp = now_iso()
        request_id: Optional[int] = None
        with self.connect() as conn:
            pick = conn.execute(
                """
                SELECT
                    d.*,
                    t.id AS owner_team_id,
                    t.code AS owner_team_code
                FROM draft_order d
                JOIN teams t ON t.code = d.owner_team_code
                WHERE d.id = ?
                """,
                (int(draft_order_id),),
            ).fetchone()
            if not pick:
                return None
            state_row = self._draft_live_state_row(conn, int(pick["draft_year"]))
            if not parse_bool((state_row or {}).get("enabled")):
                raise ValueError("draft_mode_inactive")
            rows = self._draft_live_order_rows(conn, int(pick["draft_year"]))
            current_pick_id = parse_int((state_row or {}).get("current_draft_order_id"))
            row_ids = {parse_int(row.get("id")) for row in rows}
            if current_pick_id not in row_ids:
                current_pick_id = self._draft_live_first_open_pick_id(rows)
            requestable_pick_ids = self._draft_live_requestable_pick_ids(rows, current_pick_id)
            if int(draft_order_id) not in requestable_pick_ids:
                if self._draft_live_pending_request_count(rows) >= DRAFT_LIVE_MAX_PENDING_REQUESTS:
                    raise ValueError("too_many_pending_draft_picks")
                raise ValueError("not_current_pick")
            existing_selection = conn.execute(
                """
                SELECT draft_order_id
                FROM draft_live_selections
                WHERE draft_order_id = ?
                    AND COALESCE(selection_text, '') != ''
                """,
                (int(draft_order_id),),
            ).fetchone()
            if existing_selection:
                raise ValueError("pick_already_selected")

            existing = conn.execute(
                """
                SELECT id
                FROM gm_draft_pick_requests
                WHERE draft_order_id = ? AND status = 'pending'
                """,
                (int(draft_order_id),),
            ).fetchone()
            requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
            if existing:
                request_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE gm_draft_pick_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        option_value = ?,
                        custom_text = ?,
                        selection_text = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        option_value,
                        custom_text or None,
                        selection_text,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_draft_pick_requests (
                        draft_order_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        option_value,
                        custom_text,
                        selection_text,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(draft_order_id),
                        int(pick["owner_team_id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        option_value,
                        custom_text or None,
                        selection_text,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
                self._record_workflow_creation_conn(
                    conn,
                    "gm_draft_pick_request",
                    request_id,
                    "pending",
                    actor=requester,
                    reason="draft_pick_submitted",
                    timestamp=timestamp,
                    metadata={
                        "draft_order_id": int(draft_order_id),
                        "team_code": str(pick["owner_team_code"]),
                        "selection_text": selection_text,
                    },
                )
            conn.commit()

        return self.get_gm_draft_pick_request(request_id) if request_id is not None else None

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
        normalized_event_type = str(event_type or "").strip()
        if not normalized_event_type:
            raise ValueError("event_type_required")
        payload_json = json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True)
        normalized_aggregate_type = str(aggregate_type or "").strip() or None
        normalized_aggregate_id = str(aggregate_id).strip() if aggregate_id is not None else None
        if not idempotency_key:
            digest_source = "\0".join(
                [
                    normalized_event_type,
                    normalized_aggregate_type or "",
                    normalized_aggregate_id or "",
                    payload_json,
                ]
            )
            digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
            idempotency_key = f"{normalized_event_type}:{digest}"
        timestamp = now_iso()
        conn.execute(
            """
            INSERT OR IGNORE INTO outbox_events (
                event_type,
                aggregate_type,
                aggregate_id,
                idempotency_key,
                payload_json,
                status,
                attempts,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
            """,
            (
                normalized_event_type,
                normalized_aggregate_type,
                normalized_aggregate_id,
                idempotency_key,
                payload_json,
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            "SELECT id FROM outbox_events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return int(row["id"]) if row else None

    def enqueue_outbox_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[int]:
        with self.transaction("IMMEDIATE") as conn:
            return self.enqueue_outbox_event_conn(
                conn,
                event_type,
                payload,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                idempotency_key=idempotency_key,
            )

    def get_outbox_event(self, event_id: Any) -> Optional[Dict[str, Any]]:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return None
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, event_type, aggregate_type, aggregate_id, idempotency_key,
                       payload_json, status, attempts, last_error, created_at, updated_at, delivered_at
                FROM outbox_events
                WHERE id = ?
                """,
                (int(parsed_event_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            event = row_to_dict(cur, row)
            try:
                event["payload"] = json.loads(event.get("payload_json") or "{}")
            except Exception:
                event["payload"] = {}
            return event

    def mark_outbox_event_succeeded(self, event_id: Any) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'delivered',
                    delivered_at = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE id = ?
                """,
                (timestamp, timestamp, int(parsed_event_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    def mark_outbox_event_failed(self, event_id: Any, error: Any) -> bool:
        parsed_event_id = parse_int(event_id)
        if parsed_event_id is None:
            return False
        timestamp = now_iso()
        clean_error = str(error or "").strip()[:1000] or "unknown_error"
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox_events
                SET status = 'failed',
                    attempts = COALESCE(attempts, 0) + 1,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (clean_error, timestamp, int(parsed_event_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    def create_gm_free_agent_offer_request(
        self,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
        requester: Dict[str, Any],
        offer_type: str = "free_agent_offer",
    ) -> Optional[Dict[str, Any]]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("invalid_team_code")
        normalized_offer_type = str(offer_type or "free_agent_offer").strip().lower()
        if normalized_offer_type not in {"free_agent_offer", "renewal"}:
            normalized_offer_type = "free_agent_offer"
        offer_payload = dict(payload) if isinstance(payload, dict) else {}
        requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
        timestamp = now_iso()
        request_id: Optional[int] = None
        with self.transaction("IMMEDIATE") as conn:
            free_agent = conn.execute(
                "SELECT id, name, profile_id FROM free_agents WHERE id = ?",
                (int(free_agent_id),),
            ).fetchone()
            if not free_agent:
                return None
            offer_payload.setdefault("player_name", free_agent["name"])
            if free_agent["profile_id"] is not None:
                offer_payload.setdefault("profile_id", free_agent["profile_id"])
            offer_payload_json = json.dumps(offer_payload, ensure_ascii=False, sort_keys=True)
            team = conn.execute(
                "SELECT id FROM teams WHERE code = ?",
                (normalized_team,),
            ).fetchone()
            if not team:
                raise ValueError("invalid_team_code")
            existing = conn.execute(
                """
                SELECT id
                FROM gm_free_agent_offer_requests
                WHERE free_agent_id = ? AND team_id = ? AND status = 'pending'
                """,
                (int(free_agent_id), int(team["id"])),
            ).fetchone()
            if existing:
                request_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE gm_free_agent_offer_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        offer_payload_json = ?,
                        offer_type = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        offer_payload_json,
                        normalized_offer_type,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_free_agent_offer_requests (
                        free_agent_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        offer_payload_json,
                        offer_type,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(free_agent_id),
                        int(team["id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        offer_payload_json,
                        normalized_offer_type,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
                self._record_workflow_creation_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    request_id,
                    "pending",
                    actor=requester,
                    reason="offer_submitted",
                    timestamp=timestamp,
                    metadata={
                        "team_code": normalized_team,
                        "free_agent_id": int(free_agent_id),
                        "offer_type": normalized_offer_type,
                    },
                )

        return self.get_gm_free_agent_offer_request(request_id) if request_id is not None else None

    def mark_gm_draft_pick_request_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = now_iso()
        with self.transaction("IMMEDIATE") as conn:
            try:
                self._transition_workflow_conn(
                    conn,
                    "gm_draft_pick_request",
                    int(request_id),
                    normalized_status,
                    actor=admin,
                    reason=note or f"admin_{normalized_status}",
                    updates={
                        "admin_email": str(admin.get("email") or "").strip() if admin else None,
                        "admin_name": str(admin.get("name") or "").strip() if admin else None,
                        "admin_decision_note": note,
                        "updated_at": timestamp,
                        "decided_at": timestamp,
                    },
                    timestamp=timestamp,
                )
            except WorkflowTransitionError as exc:
                if exc.code in {"workflow_not_found", "invalid_transition", "transition_conflict"}:
                    return None
                raise
        return self.get_gm_draft_pick_request(request_id)

    def mark_gm_free_agent_offer_request_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
        promise_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = now_iso()
        with self.transaction("IMMEDIATE") as conn:
            try:
                self._transition_workflow_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    int(request_id),
                    normalized_status,
                    actor=admin,
                    reason=note or f"admin_{normalized_status}",
                    updates={
                        "admin_email": str(admin.get("email") or "").strip() if admin else None,
                        "admin_name": str(admin.get("name") or "").strip() if admin else None,
                        "admin_decision_note": note,
                        "updated_at": timestamp,
                        "decided_at": timestamp,
                    },
                    timestamp=timestamp,
                )
            except WorkflowTransitionError as exc:
                if exc.code in {"workflow_not_found", "invalid_transition", "transition_conflict"}:
                    return None
                raise
            if normalized_status == "approved":
                self._upsert_free_agent_offer_promise_for_request_conn(
                    conn,
                    int(request_id),
                    admin,
                    timestamp,
                    promise_context=promise_context,
                )
        return self.get_gm_free_agent_offer_request(request_id)

    def decide_gm_free_agent_offer_request_command(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        *,
        note: Optional[str] = None,
        sign_payload: Optional[Dict[str, Any]] = None,
        offer_payload: Optional[Dict[str, Any]] = None,
        notify_discord: bool = False,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
        promise_context: Optional[Dict[str, Any]] = None,
        bypass_role_limits: bool = False,
    ) -> Dict[str, Any]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = now_iso()
        parsed_request_id = int(request_id)
        player_id: Optional[int] = None
        outbox_event_ids: List[int] = []
        with self.transaction("IMMEDIATE") as conn:
            request = self._get_gm_free_agent_offer_request_conn(conn, parsed_request_id)
            if not request:
                raise ValueError("request_not_found")
            if str(request.get("status") or "").strip().lower() != "pending":
                raise ValueError("request_already_decided")

            if normalized_status == "rejected":
                try:
                    self._transition_workflow_conn(
                        conn,
                        "gm_free_agent_offer_request",
                        parsed_request_id,
                        "rejected",
                        actor=admin,
                        reason=note or "offer_rejected",
                        updates={
                            "admin_email": str(admin.get("email") or "").strip() if admin else None,
                            "admin_name": str(admin.get("name") or "").strip() if admin else None,
                            "admin_decision_note": note,
                            "updated_at": timestamp,
                            "decided_at": timestamp,
                        },
                        command_id=f"gm-free-agent-offer:{parsed_request_id}:rejected",
                    )
                except WorkflowTransitionError as err:
                    raise ValueError("request_already_decided")
                player_name = str(request.get("player_name") or "el agente libre").strip()
                team_code = normalize_team_code(request.get("team_code")) or str(request.get("team_code") or "").upper()
                offer_type = str(request.get("offer_type") or "").strip().lower()
                offer_label = "oferta de renovación" if offer_type == "renewal" else "oferta"
                notification_body = f"La administración ha rechazado la {offer_label} de {team_code} por {player_name}."
                if note:
                    notification_body = f"{notification_body} Nota: {note}"
                self._create_user_notification_conn(
                    conn,
                    user_id=request.get("requester_user_id"),
                    email=request.get("requester_email"),
                    title=f"Oferta rechazada: {player_name}",
                    body=notification_body,
                    kind="free_agent_offer_rejected",
                    entity_type="gm_free_agent_offer_request",
                    entity_id=parsed_request_id,
                )
            else:
                free_agent_id = parse_int(request.get("free_agent_id"))
                team_code = normalize_team_code(request.get("team_code"))
                if free_agent_id is None:
                    raise ValueError("invalid_free_agent_id")
                if not team_code:
                    raise ValueError("invalid_team_code")
                free_agent = self._get_free_agent_conn(conn, free_agent_id)
                if not free_agent:
                    raise ValueError("free_agent_not_found")
                player_id = self._sign_free_agent_conn(conn, free_agent_id, team_code, sign_payload or {})
                if not player_id:
                    raise ValueError("free_agent_or_team_not_found")
                try:
                    self._transition_workflow_conn(
                        conn,
                        "gm_free_agent_offer_request",
                        parsed_request_id,
                        "approved",
                        actor=admin,
                        reason=note or "offer_approved",
                        updates={
                            "admin_email": str(admin.get("email") or "").strip() if admin else None,
                            "admin_name": str(admin.get("name") or "").strip() if admin else None,
                            "admin_decision_note": note,
                            "updated_at": timestamp,
                            "decided_at": timestamp,
                        },
                        command_id=f"gm-free-agent-offer:{parsed_request_id}:approved",
                    )
                except WorkflowTransitionError as err:
                    raise ValueError("request_already_decided")
                self._upsert_free_agent_offer_promise_for_request_conn(
                    conn,
                    parsed_request_id,
                    admin,
                    timestamp,
                    promise_context=promise_context or {"free_agent": free_agent},
                    bypass_role_limits=bypass_role_limits,
                )
                if notify_discord:
                    event_id = self.enqueue_outbox_event_conn(
                        conn,
                        "discord.free_agent_signed",
                        {
                            "player_id": player_id,
                            "offer_payload": offer_payload or {},
                            "offer_type": request.get("offer_type"),
                            "generate_image": bool(generate_image),
                            "custom_image": custom_image,
                        },
                        aggregate_type="gm_free_agent_offer_request",
                        aggregate_id=parsed_request_id,
                        idempotency_key=f"gm_free_agent_offer_request:{parsed_request_id}:discord.free_agent_signed",
                    )
                    if event_id is not None:
                        outbox_event_ids.append(int(event_id))

        updated = self.get_gm_free_agent_offer_request(parsed_request_id)
        player = self.get_player_record(player_id) if player_id is not None else None
        return {
            "request": updated,
            "player_id": player_id,
            "player": player,
            "outbox_event_ids": outbox_event_ids,
        }

    @staticmethod
    def _offer_promise_status(raw_status: Any) -> str:
        status = str(raw_status or "").strip().lower()
        aliases = {
            "pending": "pending",
            "pendiente": "pending",
            "fulfilled": "fulfilled",
            "cumplida": "fulfilled",
            "cumplido": "fulfilled",
            "broken": "broken",
            "incumplida": "broken",
            "incumplido": "broken",
        }
        if status not in aliases:
            raise ValueError("invalid_promise_status")
        return aliases[status]

    @staticmethod
    def _normalize_free_agent_promise_role(raw_role: Any) -> str:
        return re.sub(r"\s+", " ", str(raw_role or "").strip())

    def _free_agent_promise_role_limit(self, raw_role: Any) -> Optional[int]:
        return FREE_AGENT_PROMISE_ROLE_LIMITS.get(self._normalize_free_agent_promise_role(raw_role))

    def _ensure_free_agent_promise_role_capacity_conn(
        self,
        conn: sqlite3.Connection,
        team_code: Any,
        season_year: Any,
        role: Any,
        exclude_promise_id: Optional[int] = None,
        bypass_role_limits: bool = False,
    ) -> None:
        if bypass_role_limits:
            return
        normalized_team = normalize_team_code(team_code)
        normalized_role = self._normalize_free_agent_promise_role(role)
        parsed_season = parse_int(season_year)
        limit = self._free_agent_promise_role_limit(normalized_role)
        if not normalized_team or parsed_season is None or limit is None:
            return
        params: List[Any] = [normalized_team, parsed_season, normalized_role]
        exclude_clause = ""
        if exclude_promise_id is not None:
            exclude_clause = " AND id <> ?"
            params.append(int(exclude_promise_id))
        cur = conn.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM free_agent_offer_promises
            WHERE UPPER(TRIM(team_code)) = ?
              AND season_year = ?
              AND role = ?
              AND status IN ('pending', 'fulfilled')
              {exclude_clause}
            """,
            params,
        )
        count = int(cur.fetchone()["total"] or 0)
        if count >= limit:
            raise ValueError(f"promise_role_limit_exceeded:{normalized_role}:{limit}")

    def ensure_free_agent_offer_request_promise_capacity(
        self,
        request_id: int,
        promise_context: Optional[Dict[str, Any]] = None,
        bypass_role_limits: bool = False,
    ) -> None:
        if bypass_role_limits:
            return
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT r.*, t.code AS team_code
                FROM gm_free_agent_offer_requests r
                JOIN teams t ON t.id = r.team_id
                WHERE r.id = ?
                """,
                (int(request_id),),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("request_not_found")
            payload = self._free_agent_offer_payload_from_request_row(row)
            role = self._normalize_free_agent_promise_role(payload.get("role"))
            if not role:
                return
            salary_by_season = payload.get("salary_by_season")
            if not isinstance(salary_by_season, dict):
                salary_by_season = {}
            seasons = sorted(
                season
                for season in (parse_int(key) for key in salary_by_season.keys())
                if season is not None
            )
            season_year = seasons[0] if seasons else None
            if season_year is None:
                context = promise_context or {}
                free_agent_context = context.get("free_agent") if isinstance(context.get("free_agent"), dict) else {}
                season_year = parse_int(free_agent_context.get("season_year"))
            self._ensure_free_agent_promise_role_capacity_conn(
                conn,
                row["team_code"],
                season_year,
                role,
            )

    @staticmethod
    def _free_agent_offer_payload_from_request_row(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            payload = json.loads(str(row["offer_payload_json"] or "{}"))
        except (KeyError, json.JSONDecodeError, TypeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _upsert_free_agent_offer_promise_for_request_conn(
        self,
        conn: sqlite3.Connection,
        request_id: int,
        admin: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        promise_context: Optional[Dict[str, Any]] = None,
        bypass_role_limits: bool = False,
    ) -> Optional[int]:
        timestamp = timestamp or now_iso()
        cur = conn.execute(
            """
            SELECT
                r.*,
                f.name AS free_agent_name,
                f.profile_id AS free_agent_profile_id,
                f.agent AS free_agent_agent,
                t.code AS team_code,
                t.name AS team_name
            FROM gm_free_agent_offer_requests r
            LEFT JOIN free_agents f ON f.id = r.free_agent_id
            JOIN teams t ON t.id = r.team_id
            WHERE r.id = ? AND r.status = 'approved'
            """,
            (int(request_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        payload = self._free_agent_offer_payload_from_request_row(row)
        role = re.sub(r"\s+", " ", str(payload.get("role") or "").strip())
        if not role:
            return None

        context = promise_context or {}
        free_agent_context = context.get("free_agent") if isinstance(context.get("free_agent"), dict) else {}
        salary_by_season = payload.get("salary_by_season")
        if not isinstance(salary_by_season, dict):
            salary_by_season = {}
        seasons = sorted(
            season
            for season in (parse_int(key) for key in salary_by_season.keys())
            if season is not None
        )
        season_year = seasons[0] if seasons else None
        label = season_label(season_year) if season_year is not None else ""
        profile_id = (
            parse_int(payload.get("profile_id"))
            or parse_int(free_agent_context.get("profile_id"))
            or parse_int(row["free_agent_profile_id"])
        )
        player_name = (
            str(payload.get("player_name") or "").strip()
            or str(free_agent_context.get("name") or "").strip()
            or str(row["free_agent_name"] or "").strip()
            or "Agente libre"
        )
        agent_name = re.sub(
            r"\s+",
            " ",
            str(
                payload.get("agent_name")
                or payload.get("agent")
                or free_agent_context.get("agent")
                or row["free_agent_agent"]
                or ""
            ).strip(),
        )
        admin = admin or {}
        existing_promise = conn.execute(
            "SELECT id FROM free_agent_offer_promises WHERE gm_free_agent_offer_request_id = ?",
            (int(request_id),),
        ).fetchone()
        self._ensure_free_agent_promise_role_capacity_conn(
            conn,
            row["team_code"],
            season_year,
            role,
            exclude_promise_id=int(existing_promise["id"]) if existing_promise else None,
            bypass_role_limits=bypass_role_limits,
        )
        insert_cur = conn.execute(
            """
            INSERT INTO free_agent_offer_promises (
                gm_free_agent_offer_request_id,
                free_agent_id,
                profile_id,
                player_name,
                team_code,
                team_name,
                agent_name,
                season_year,
                season_label,
                role,
                offer_type,
                contract_type,
                status,
                admin_email,
                admin_name,
                created_at,
                updated_at,
                decided_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, NULL)
            ON CONFLICT(gm_free_agent_offer_request_id)
            DO UPDATE SET
                free_agent_id = excluded.free_agent_id,
                profile_id = excluded.profile_id,
                player_name = excluded.player_name,
                team_code = excluded.team_code,
                team_name = excluded.team_name,
                agent_name = excluded.agent_name,
                season_year = excluded.season_year,
                season_label = excluded.season_label,
                role = excluded.role,
                offer_type = excluded.offer_type,
                contract_type = excluded.contract_type,
                admin_email = excluded.admin_email,
                admin_name = excluded.admin_name,
                updated_at = excluded.updated_at
            """,
            (
                int(request_id),
                parse_int(row["free_agent_id"]),
                profile_id,
                player_name,
                normalize_team_code(row["team_code"]) or str(row["team_code"] or "").strip().upper(),
                str(row["team_name"] or "").strip(),
                agent_name,
                season_year,
                label,
                role,
                str(row["offer_type"] or "").strip().lower() or "free_agent_offer",
                str(payload.get("contract_type") or "").strip(),
                str(admin.get("email") or "").strip().lower() or None,
                str(admin.get("name") or "").strip() or None,
                timestamp,
                timestamp,
            ),
        )
        if insert_cur.lastrowid:
            return int(insert_cur.lastrowid)
        existing = conn.execute(
            "SELECT id FROM free_agent_offer_promises WHERE gm_free_agent_offer_request_id = ?",
            (int(request_id),),
        ).fetchone()
        return int(existing["id"]) if existing else None

    def _backfill_free_agent_offer_promises_conn(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute(
            """
            SELECT r.id
            FROM gm_free_agent_offer_requests r
            LEFT JOIN free_agent_offer_promises p
                ON p.gm_free_agent_offer_request_id = r.id
            WHERE r.status = 'approved'
              AND p.id IS NULL
            ORDER BY r.id
            """
        )
        for row in cur.fetchall():
            self._upsert_free_agent_offer_promise_for_request_conn(conn, int(row["id"]))

    def _free_agent_offer_promise_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = row_to_dict(cursor, row)
        item["id"] = parse_int(item.get("id"))
        item["gm_free_agent_offer_request_id"] = parse_int(item.get("gm_free_agent_offer_request_id"))
        item["free_agent_id"] = parse_int(item.get("free_agent_id"))
        item["profile_id"] = parse_int(item.get("profile_id"))
        item["season_year"] = parse_int(item.get("season_year"))
        item["team_code"] = normalize_team_code(item.get("team_code")) or str(item.get("team_code") or "").strip().upper()
        item["status"] = str(item.get("status") or "pending").strip().lower()
        return item

    def list_free_agent_offer_promises(
        self,
        session: Dict[str, Any],
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        role = str(session.get("role") or "").strip().lower()
        email = str(session.get("email") or "").strip().lower()
        access = self.user_access_for_email(email) if email else {}
        agent_name = re.sub(
            r"\s+",
            " ",
            str(access.get("agent_name") or session.get("agent_name") or "").strip(),
        )
        if role not in {"admin", "co_admin"}:
            raise PermissionError("admin_or_coadmin_required")
        if role == "co_admin" and not agent_name:
            return {"agent_name": "", "missing_agent": True, "promises": []}

        where = ["1 = 1"]
        params: List[Any] = []
        normalized_status = str(status or "all").strip().lower()
        if normalized_status and normalized_status != "all":
            where.append("p.status = ?")
            params.append(self._offer_promise_status(normalized_status))
        if role == "co_admin":
            where.append("lower(trim(COALESCE(p.agent_name, ''))) = lower(trim(?))")
            params.append(agent_name)

        with self.connect() as conn:
            self._backfill_free_agent_offer_promises_conn(conn)
            conn.commit()
            cur = conn.execute(
                f"""
                SELECT p.*
                FROM free_agent_offer_promises p
                WHERE {' AND '.join(where)}
                ORDER BY
                    COALESCE(p.season_year, 0) DESC,
                    CASE p.status WHEN 'pending' THEN 0 WHEN 'broken' THEN 1 WHEN 'fulfilled' THEN 2 ELSE 3 END,
                    p.updated_at DESC,
                    lower(p.player_name)
                """,
                params,
            )
            promises = [self._free_agent_offer_promise_from_row(cur, row) for row in cur.fetchall()]
        return {"agent_name": agent_name, "missing_agent": False, "promises": promises}

    def create_free_agent_offer_promise(
        self,
        payload: Dict[str, Any],
        admin: Dict[str, Any],
        bypass_role_limits: bool = False,
    ) -> Dict[str, Any]:
        player_name = re.sub(r"\s+", " ", str(payload.get("player_name") or "").strip())
        if not player_name:
            raise ValueError("player_name_required")
        team_code = normalize_team_code(payload.get("team_code"))
        if not team_code:
            raise ValueError("invalid_team")
        role = re.sub(r"\s+", " ", str(payload.get("role") or "").strip())
        if not role:
            raise ValueError("role_required")
        season_year = parse_int(payload.get("season_year"))
        if season_year is None:
            settings = self.get_settings()
            season_year = parse_int(settings.get("current_year")) or CAP_FORECAST_MIN_YEAR
        if season_year < 2000 or season_year > 2100:
            raise ValueError("invalid_season_year")
        status = self._offer_promise_status(payload.get("status") or "pending")
        agent_name = re.sub(r"\s+", " ", str(payload.get("agent_name") or "").strip())
        contract_type = re.sub(r"\s+", " ", str(payload.get("contract_type") or "").strip())
        offer_type = re.sub(r"\s+", " ", str(payload.get("offer_type") or "manual").strip()) or "manual"
        profile_id = parse_int(payload.get("profile_id"))
        free_agent_id = parse_int(payload.get("free_agent_id"))
        timestamp = now_iso()
        admin_email = str(admin.get("email") or "").strip().lower() or None
        admin_name = str(admin.get("name") or "").strip() or None
        with self.connect() as conn:
            team_row = conn.execute("SELECT code, name FROM teams WHERE code = ?", (team_code,)).fetchone()
            if not team_row:
                raise ValueError("team_not_found")
            if profile_id is not None and not self._player_profile_exists_conn(conn, profile_id):
                raise ValueError("profile_not_found")
            if status in {"pending", "fulfilled"}:
                self._ensure_free_agent_promise_role_capacity_conn(
                    conn,
                    team_code,
                    season_year,
                    role,
                    bypass_role_limits=bypass_role_limits,
                )
            cur = conn.execute(
                """
                INSERT INTO free_agent_offer_promises (
                    gm_free_agent_offer_request_id,
                    free_agent_id,
                    profile_id,
                    player_name,
                    team_code,
                    team_name,
                    agent_name,
                    season_year,
                    season_label,
                    role,
                    offer_type,
                    contract_type,
                    status,
                    admin_email,
                    admin_name,
                    created_at,
                    updated_at,
                    decided_at
                )
                VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    free_agent_id,
                    profile_id,
                    player_name,
                    str(team_row["code"] or "").strip().upper(),
                    str(team_row["name"] or "").strip(),
                    agent_name,
                    season_year,
                    season_label(season_year),
                    role,
                    offer_type,
                    contract_type,
                    status,
                    admin_email,
                    admin_name,
                    timestamp,
                    timestamp,
                    None if status == "pending" else timestamp,
                ),
            )
            conn.commit()
            read_cur = conn.execute("SELECT * FROM free_agent_offer_promises WHERE id = ?", (cur.lastrowid,))
            row = read_cur.fetchone()
            if not row:
                raise ValueError("promise_not_created")
            return self._free_agent_offer_promise_from_row(read_cur, row)

    def update_free_agent_offer_promise(
        self,
        promise_id: Any,
        payload: Dict[str, Any],
        admin: Dict[str, Any],
        bypass_role_limits: bool = False,
    ) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(promise_id)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_promise_id")
        payload = payload if isinstance(payload, dict) else {}
        timestamp = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM free_agent_offer_promises WHERE id = ?",
                (parsed_id,),
            ).fetchone()
            if not existing:
                return None
            player_name = re.sub(
                r"\s+",
                " ",
                str(payload.get("player_name") if "player_name" in payload else existing["player_name"] or "").strip(),
            )
            if not player_name:
                raise ValueError("player_name_required")
            team_code = normalize_team_code(payload.get("team_code") if "team_code" in payload else existing["team_code"])
            if not team_code:
                raise ValueError("invalid_team")
            team_row = conn.execute("SELECT code, name FROM teams WHERE code = ?", (team_code,)).fetchone()
            if not team_row:
                raise ValueError("team_not_found")
            role = self._normalize_free_agent_promise_role(
                payload.get("role") if "role" in payload else existing["role"]
            )
            if not role:
                raise ValueError("role_required")
            season_year = parse_int(payload.get("season_year") if "season_year" in payload else existing["season_year"])
            if season_year is None or season_year < 2000 or season_year > 2100:
                raise ValueError("invalid_season_year")
            normalized_status = self._offer_promise_status(
                payload.get("status") if "status" in payload else existing["status"]
            )
            free_agent_id = (
                parse_int(payload.get("free_agent_id"))
                if "free_agent_id" in payload
                else parse_int(existing["free_agent_id"])
            )
            profile_id = (
                parse_int(payload.get("profile_id"))
                if "profile_id" in payload
                else parse_int(existing["profile_id"])
            )
            if profile_id is not None and not self._player_profile_exists_conn(conn, profile_id):
                raise ValueError("profile_not_found")
            agent_name = re.sub(
                r"\s+",
                " ",
                str(payload.get("agent_name") if "agent_name" in payload else existing["agent_name"] or "").strip(),
            )
            contract_type = re.sub(
                r"\s+",
                " ",
                str(payload.get("contract_type") if "contract_type" in payload else existing["contract_type"] or "").strip(),
            )
            offer_type = re.sub(
                r"\s+",
                " ",
                str(payload.get("offer_type") if "offer_type" in payload else existing["offer_type"] or "manual").strip(),
            ) or "manual"
            if normalized_status in {"pending", "fulfilled"}:
                self._ensure_free_agent_promise_role_capacity_conn(
                    conn,
                    team_code,
                    season_year,
                    role,
                    exclude_promise_id=parsed_id,
                    bypass_role_limits=bypass_role_limits,
                )
            cur = conn.execute(
                """
                UPDATE free_agent_offer_promises
                SET
                    free_agent_id = ?,
                    profile_id = ?,
                    player_name = ?,
                    team_code = ?,
                    team_name = ?,
                    agent_name = ?,
                    season_year = ?,
                    season_label = ?,
                    role = ?,
                    offer_type = ?,
                    contract_type = ?,
                    status = ?,
                    admin_email = ?,
                    admin_name = ?,
                    updated_at = ?,
                    decided_at = CASE WHEN ? = 'pending' THEN NULL ELSE ? END
                WHERE id = ?
                """,
                (
                    free_agent_id,
                    profile_id,
                    player_name,
                    str(team_row["code"] or "").strip().upper(),
                    str(team_row["name"] or "").strip(),
                    agent_name,
                    season_year,
                    season_label(season_year),
                    role,
                    offer_type,
                    contract_type,
                    normalized_status,
                    str(admin.get("email") or "").strip().lower() or None,
                    str(admin.get("name") or "").strip() or None,
                    timestamp,
                    normalized_status,
                    timestamp,
                    parsed_id,
                ),
            )
            conn.commit()
            if cur.rowcount < 1:
                return None
            read_cur = conn.execute(
                "SELECT * FROM free_agent_offer_promises WHERE id = ?",
                (parsed_id,),
            )
            row = read_cur.fetchone()
            return self._free_agent_offer_promise_from_row(read_cur, row) if row else None

    def update_free_agent_offer_promise_status(
        self,
        promise_id: Any,
        status: Any,
        admin: Dict[str, Any],
        bypass_role_limits: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return self.update_free_agent_offer_promise(
            promise_id,
            {"status": status},
            admin,
            bypass_role_limits=bypass_role_limits,
        )

    def mark_gm_option_request_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = now_iso()
        with self.transaction("IMMEDIATE") as conn:
            try:
                self._transition_workflow_conn(
                    conn,
                    "gm_option_request",
                    int(request_id),
                    normalized_status,
                    actor=admin,
                    reason=note or f"admin_{normalized_status}",
                    updates={
                        "admin_email": str(admin.get("email") or "").strip() if admin else None,
                        "admin_name": str(admin.get("name") or "").strip() if admin else None,
                        "admin_decision_note": note,
                        "updated_at": timestamp,
                        "decided_at": timestamp,
                    },
                    timestamp=timestamp,
                )
            except WorkflowTransitionError as exc:
                if exc.code in {"workflow_not_found", "invalid_transition", "transition_conflict"}:
                    return None
                raise
        return self.get_gm_option_request(request_id)

    def _create_user_notification_conn(
        self,
        conn: sqlite3.Connection,
        **notification: Any,
    ) -> Optional[int]:
        return self._notification_repository.create_conn(conn, **notification)

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
        settings = self.get_settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        if current_year < PLAYER_CONTRACT_MIN_YEAR or current_year > PLAYER_CONTRACT_MAX_START_YEAR:
            current_year = 2025
        return current_year + 1

    def _normalize_draft_order_payload(
        self,
        conn: sqlite3.Connection,
        payload: Dict[str, Any],
        *,
        existing: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source = dict(existing or {})
        source.update(payload)

        draft_year = parse_int(source.get("draft_year"))
        if draft_year is None:
            draft_year = self.current_draft_year()
        if draft_year < 2000 or draft_year > 2100:
            raise ValueError("invalid_draft_year")

        pick_number = parse_int(source.get("pick_number"))
        if pick_number is None or pick_number <= 0 or pick_number > 300:
            raise ValueError("invalid_pick_number")

        draft_round = normalize_pick_round(source.get("draft_round"))
        owner_team_code = normalize_team_code(source.get("owner_team_code"))
        original_team_code = normalize_team_code(source.get("original_team_code"))
        if not owner_team_code or not original_team_code:
            raise ValueError("team_codes_required")

        existing_codes = {
            str(row["code"]).upper()
            for row in conn.execute(
                "SELECT code FROM teams WHERE code IN (?, ?)",
                (owner_team_code, original_team_code),
            ).fetchall()
        }
        if owner_team_code not in existing_codes or original_team_code not in existing_codes:
            raise ValueError("team_not_found")

        return {
            "draft_year": draft_year,
            "draft_round": draft_round,
            "pick_number": pick_number,
            "owner_team_code": owner_team_code,
            "original_team_code": original_team_code,
        }

    def list_draft_order(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        year = draft_year if draft_year is not None else self.current_draft_year()
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    d.id,
                    d.draft_year,
                    d.draft_round,
                    d.pick_number,
                    d.owner_team_code,
                    COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                    d.original_team_code,
                    COALESCE(original.name, d.original_team_code) AS original_team_name,
                    d.created_at,
                    d.updated_at
                FROM draft_order d
                LEFT JOIN teams owner ON owner.code = d.owner_team_code
                LEFT JOIN teams original ON original.code = d.original_team_code
                WHERE d.draft_year = ?
                ORDER BY
                    CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                    d.pick_number,
                    d.id
                """,
                (int(year),),
            )
            return {
                "draft_year": int(year),
                "draft_order": [row_to_dict(cur, row) for row in cur.fetchall()],
            }

    def list_draft_pick_ledger(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        year = draft_year if draft_year is not None else self.current_draft_year()
        with self.connect() as conn:
            team_cur = conn.execute(
                "SELECT id, code, name FROM teams ORDER BY code"
            )
            teams = [row_to_dict(team_cur, row) for row in team_cur.fetchall()]
            team_names = {
                str(team.get("code") or "").strip().upper(): str(team.get("name") or team.get("code") or "").strip()
                for team in teams
            }
            asset_cur = conn.execute(
                """
                SELECT
                    a.id,
                    a.team_id,
                    holder.code AS holder_team_code,
                    COALESCE(holder.name, holder.code) AS holder_team_name,
                    a.asset_type,
                    a.label,
                    a.year,
                    a.detail,
                    a.draft_pick_type,
                    a.draft_round,
                    a.original_owner,
                    a.draft_pick_sold_to,
                    a.draft_pick_conditional_teams,
                    a.draft_pick_restricted,
                    a.draft_pick_stepien_restricted,
                    a.draft_pick_protected,
                    a.draft_pick_frozen,
                    a.created_at,
                    a.updated_at
                FROM assets a
                JOIN teams holder ON holder.id = a.team_id
                WHERE a.asset_type = 'draft_pick'
                  AND CAST(COALESCE(a.year, '') AS INTEGER) = ?
                ORDER BY
                    holder.code,
                    CASE COALESCE(a.draft_round, '1st') WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                    CASE COALESCE(a.draft_pick_type, 'own')
                        WHEN 'own' THEN 1
                        WHEN 'acquired' THEN 2
                        WHEN 'conditional' THEN 3
                        WHEN 'sold' THEN 4
                        ELSE 5
                    END,
                    a.id
                """,
                (int(year),),
            )
            assets = [row_to_dict(asset_cur, row) for row in asset_cur.fetchall()]

        def canonical_round(value: Any) -> str:
            return normalize_pick_round(value)

        def canonical_key(owner_code: str, draft_round: str) -> str:
            round_key = "1ST" if draft_round == "1st" else "2ND"
            return f"{int(year)}-{round_key}-{owner_code}"

        def original_owner_codes(asset: Dict[str, Any]) -> List[str]:
            pick_type = normalize_pick_type(asset.get("draft_pick_type"))
            holder = normalize_team_code(asset.get("holder_team_code"))
            original = normalize_team_code(asset.get("original_owner"))
            if pick_type == "conditional":
                codes = normalize_team_codes(asset.get("draft_pick_conditional_teams"))
                return codes or ([original] if original else ([holder] if holder else []))
            if pick_type in {"acquired", "sold"}:
                return [original or holder] if (original or holder) else []
            return [holder] if holder else []

        active_by_key: Dict[str, List[Dict[str, Any]]] = {}
        sold_by_key: Dict[str, List[Dict[str, Any]]] = {}
        unexpected_assets: List[Dict[str, Any]] = []
        valid_team_codes = set(team_names.keys())
        for asset in assets:
            draft_round = canonical_round(asset.get("draft_round"))
            pick_type = normalize_pick_type(asset.get("draft_pick_type"))
            owner_codes = [code for code in original_owner_codes(asset) if code]
            if not owner_codes:
                unexpected_assets.append(asset)
                continue
            for owner_code in owner_codes:
                key = canonical_key(owner_code, draft_round)
                target = sold_by_key if pick_type == "sold" else active_by_key
                target.setdefault(key, []).append(asset)
                if owner_code not in valid_team_codes:
                    unexpected_assets.append(asset)

        def asset_summary(asset: Dict[str, Any]) -> Dict[str, Any]:
            holder_code = normalize_team_code(asset.get("holder_team_code"))
            sold_to_codes = normalize_team_codes(asset.get("draft_pick_sold_to"))
            conditional_codes = normalize_team_codes(asset.get("draft_pick_conditional_teams"))
            return {
                "asset_id": parse_int(asset.get("id")),
                "holder_team_code": holder_code,
                "holder_team_name": asset.get("holder_team_name") or team_names.get(holder_code or "", holder_code or ""),
                "pick_type": normalize_pick_type(asset.get("draft_pick_type")),
                "label": asset.get("label"),
                "detail": asset.get("detail"),
                "sold_to_team_codes": sold_to_codes,
                "conditional_team_codes": conditional_codes,
                "restricted": bool(parse_bool(asset.get("draft_pick_restricted"))),
                "stepien_restricted": bool(parse_bool(asset.get("draft_pick_stepien_restricted"))),
                "protected": bool(parse_bool(asset.get("draft_pick_protected"))),
                "frozen": bool(parse_bool(asset.get("draft_pick_frozen"))),
            }

        def pick_state(owner_code: str, draft_round: str) -> Dict[str, Any]:
            key = canonical_key(owner_code, draft_round)
            active_assets = active_by_key.get(key, [])
            sold_assets = sold_by_key.get(key, [])
            active_summaries = [asset_summary(asset) for asset in active_assets]
            sold_summaries = [asset_summary(asset) for asset in sold_assets]
            holder_codes: List[str] = []
            holder_names: List[str] = []
            pick_types: List[str] = []
            frozen = False
            for item in active_summaries:
                holder_code = item.get("holder_team_code")
                if holder_code and holder_code not in holder_codes:
                    holder_codes.append(holder_code)
                    holder_names.append(item.get("holder_team_name") or team_names.get(holder_code, holder_code))
                pick_type = item.get("pick_type")
                if pick_type and pick_type not in pick_types:
                    pick_types.append(pick_type)
                frozen = frozen or bool(item.get("frozen"))
            if not active_summaries:
                status = "missing"
            elif len(active_summaries) > 1:
                status = "duplicate"
            elif "conditional" in pick_types:
                status = "conditional"
            elif frozen:
                status = "frozen"
            else:
                status = "ok"
            sold_to_codes: List[str] = []
            for item in sold_summaries:
                for code in item.get("sold_to_team_codes") or []:
                    if code not in sold_to_codes:
                        sold_to_codes.append(code)
            return {
                "canonical_id": key,
                "round": draft_round,
                "original_team_code": owner_code,
                "original_team_name": team_names.get(owner_code, owner_code),
                "status": status,
                "holder_team_codes": holder_codes,
                "holder_team_names": holder_names,
                "asset_ids": [item.get("asset_id") for item in active_summaries if item.get("asset_id") is not None],
                "pick_types": pick_types,
                "sold_to_team_codes": sold_to_codes,
                "sold_asset_ids": [item.get("asset_id") for item in sold_summaries if item.get("asset_id") is not None],
                "active_assets": active_summaries,
                "sold_assets": sold_summaries,
            }

        rows: List[Dict[str, Any]] = []
        issues: List[Dict[str, Any]] = []
        summary = {
            "expected": len(teams) * 2,
            "ok": 0,
            "missing": 0,
            "duplicate": 0,
            "conditional": 0,
            "frozen": 0,
            "warning": 0,
            "error": 0,
        }
        for team in teams:
            owner_code = str(team.get("code") or "").strip().upper()
            first = pick_state(owner_code, "1st")
            second = pick_state(owner_code, "2nd")
            rows.append(
                {
                    "team_code": owner_code,
                    "team_name": team.get("name") or owner_code,
                    "first": first,
                    "second": second,
                }
            )
            for state in [first, second]:
                status = str(state.get("status") or "missing")
                if status in summary:
                    summary[status] += 1
                if status == "missing":
                    summary["error"] += 1
                    issues.append(
                        {
                            "severity": "error",
                            "rule": "missing_pick",
                            "canonical_id": state.get("canonical_id"),
                            "message": f"{state.get('canonical_id')} no aparece en ningún equipo.",
                        }
                    )
                elif status == "duplicate":
                    summary["error"] += 1
                    issues.append(
                        {
                            "severity": "error",
                            "rule": "duplicate_pick",
                            "canonical_id": state.get("canonical_id"),
                            "asset_ids": state.get("asset_ids") or [],
                            "holder_team_codes": state.get("holder_team_codes") or [],
                            "message": f"{state.get('canonical_id')} aparece en más de un asset activo.",
                        }
                    )
                elif status in {"conditional", "frozen"}:
                    summary["warning"] += 1
                    issues.append(
                        {
                            "severity": "warning",
                            "rule": f"{status}_pick",
                            "canonical_id": state.get("canonical_id"),
                            "asset_ids": state.get("asset_ids") or [],
                            "holder_team_codes": state.get("holder_team_codes") or [],
                            "message": f"{state.get('canonical_id')} requiere revisión: {status}.",
                        }
                    )

        for asset in unexpected_assets:
            asset_id = parse_int(asset.get("id"))
            issue_key = f"unexpected:{asset_id}"
            if any(str(issue.get("canonical_id")) == issue_key for issue in issues):
                continue
            summary["warning"] += 1
            issues.append(
                {
                    "severity": "warning",
                    "rule": "unexpected_pick_owner",
                    "canonical_id": issue_key,
                    "asset_id": asset_id,
                    "holder_team_code": normalize_team_code(asset.get("holder_team_code")),
                    "message": f"Asset #{asset_id} tiene propietario original no reconocido o vacío.",
                }
            )

        return {
            "draft_year": int(year),
            "summary": summary,
            "rows": rows,
            "issues": issues,
        }

    def create_draft_order_entry(self, payload: Dict[str, Any]) -> int:
        with self.connect() as conn:
            values = self._normalize_draft_order_payload(conn, payload)
            timestamp = now_iso()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO draft_order (
                        draft_year, draft_round, pick_number, owner_team_code,
                        original_team_code, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["draft_year"],
                        values["draft_round"],
                        values["pick_number"],
                        values["owner_team_code"],
                        values["original_team_code"],
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("duplicate_draft_pick") from err
            conn.commit()
            return int(cur.lastrowid)

    def update_draft_order_entry(self, entry_id: int, payload: Dict[str, Any]) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM draft_order WHERE id = ?", (entry_id,)).fetchone()
            if not row:
                return False
            values = self._normalize_draft_order_payload(conn, payload, existing=dict(row))
            try:
                cur = conn.execute(
                    """
                    UPDATE draft_order
                    SET draft_year = ?,
                        draft_round = ?,
                        pick_number = ?,
                        owner_team_code = ?,
                        original_team_code = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        values["draft_year"],
                        values["draft_round"],
                        values["pick_number"],
                        values["owner_team_code"],
                        values["original_team_code"],
                        now_iso(),
                        entry_id,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("duplicate_draft_pick") from err
            conn.commit()
            return cur.rowcount > 0

    def delete_draft_order_entry(self, entry_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM draft_order WHERE id = ?", (entry_id,))
            conn.commit()
            return cur.rowcount > 0

    def get_draft_order_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    d.id,
                    d.draft_year,
                    d.draft_round,
                    d.pick_number,
                    d.owner_team_code,
                    COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                    d.original_team_code,
                    COALESCE(original.name, d.original_team_code) AS original_team_name,
                    d.created_at,
                    d.updated_at
                FROM draft_order d
                LEFT JOIN teams owner ON owner.code = d.owner_team_code
                LEFT JOIN teams original ON original.code = d.original_team_code
                WHERE d.id = ?
                """,
                (int(entry_id),),
            )
            row = cur.fetchone()
            return row_to_dict(cur, row) if row else None

    def _draft_live_order_rows(self, conn: sqlite3.Connection, draft_year: int) -> List[Dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT
                d.id,
                d.draft_year,
                d.draft_round,
                d.pick_number,
                d.owner_team_code,
                COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                d.original_team_code,
                COALESCE(original.name, d.original_team_code) AS original_team_name,
                d.created_at,
                d.updated_at,
                s.selection_text,
                s.option_value,
                s.custom_text,
                COALESCE(s.skipped, 0) AS skipped,
                s.selected_by_email,
                s.selected_by_name,
                s.selected_by_role,
                s.selected_at,
                s.updated_at AS selection_updated_at,
                s.processed_type,
                s.processed_dead_contract_id,
                s.processed_asset_id,
                s.processed_at,
                pr.id AS pending_request_id,
                pr.selection_text AS pending_selection_text,
                pr.option_value AS pending_option_value,
                pr.custom_text AS pending_custom_text,
                pr.requester_email AS pending_requester_email,
                pr.requester_name AS pending_requester_name,
                pr.created_at AS pending_request_created_at
            FROM draft_order d
            LEFT JOIN teams owner ON owner.code = d.owner_team_code
            LEFT JOIN teams original ON original.code = d.original_team_code
            LEFT JOIN draft_live_selections s ON s.draft_order_id = d.id
            LEFT JOIN gm_draft_pick_requests pr
                ON pr.draft_order_id = d.id
                AND pr.status = 'pending'
            WHERE d.draft_year = ?
            ORDER BY
                CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                d.pick_number,
                d.id
            """,
            (int(draft_year),),
        )
        return [row_to_dict(cur, row) for row in cur.fetchall()]

    def _rookie_scale_salary_for_pick(
        self,
        settings: Dict[str, str],
        salary_season: int,
        pick_number: int,
    ) -> Dict[str, Any]:
        checked_keys: List[str] = []

        def setting_amount(key: str) -> Optional[float]:
            checked_keys.append(key)
            parsed = parse_amount_like(settings.get(key))
            if parsed is not None and parsed > 0:
                return parsed
            return None

        exact_key = f"rookie_scale_{int(salary_season)}_{int(pick_number)}"
        exact_amount = setting_amount(exact_key)
        if exact_amount is not None:
            return {
                "salary": exact_amount,
                "salary_season": int(salary_season),
                "setting_key": exact_key,
                "source": "configured",
                "checked_keys": checked_keys,
            }

        base_key = f"rookie_scale_2025_{int(pick_number)}"
        base_amount = setting_amount(base_key) if int(salary_season) != 2025 else None
        if base_amount is not None:
            base_cap = parse_amount_like(settings.get("salary_cap_2025")) or 154_647_000.0
            season_cap = (
                parse_amount_like(settings.get(f"salary_cap_{int(salary_season)}"))
                or parse_amount_like(settings.get("salary_cap_2025"))
                or base_cap
            )
            if base_cap > 0 and season_cap > 0:
                return {
                    "salary": base_amount * (season_cap / base_cap),
                    "salary_season": int(salary_season),
                    "setting_key": base_key,
                    "source": "salary_cap_scaled_from_2025",
                    "checked_keys": checked_keys,
                }

        return {
            "salary": None,
            "salary_season": int(salary_season),
            "setting_key": exact_key,
            "source": "missing",
            "checked_keys": checked_keys,
        }

    def _draft_live_state_row(self, conn: sqlite3.Connection, draft_year: int) -> Optional[Dict[str, Any]]:
        cur = conn.execute("SELECT * FROM draft_live_state WHERE draft_year = ?", (int(draft_year),))
        row = cur.fetchone()
        return row_to_dict(cur, row) if row else None

    def _draft_live_options(self, options_text: Any) -> List[str]:
        seen: set[str] = set()
        options: List[str] = []
        for line in str(options_text or "").splitlines():
            option = line.strip()
            if not option:
                continue
            key = option.casefold()
            if key in seen:
                continue
            seen.add(key)
            options.append(option)
        return sorted(options, key=lambda value: (value.casefold(), value))

    def _draft_live_first_open_pick_id(self, rows: List[Dict[str, Any]]) -> Optional[int]:
        for row in rows:
            if str(row.get("selection_text") or "").strip() or parse_bool(row.get("skipped")):
                continue
            parsed = parse_int(row.get("id"))
            if parsed is not None:
                return int(parsed)
        return parse_int(rows[0].get("id")) if rows else None

    def _draft_live_pending_request_count(self, rows: List[Dict[str, Any]]) -> int:
        return sum(1 for row in rows if parse_int(row.get("pending_request_id")) is not None)

    def _draft_live_requestable_pick_ids(
        self,
        rows: List[Dict[str, Any]],
        current_pick_id: Optional[int],
    ) -> List[int]:
        if self._draft_live_pending_request_count(rows) >= DRAFT_LIVE_MAX_PENDING_REQUESTS:
            return []
        start_index = 0
        if current_pick_id is not None:
            for idx, row in enumerate(rows):
                if parse_int(row.get("id")) == int(current_pick_id):
                    start_index = idx
                    break
        for row in rows[start_index:]:
            if str(row.get("selection_text") or "").strip() or parse_bool(row.get("skipped")):
                continue
            if parse_int(row.get("pending_request_id")) is not None:
                continue
            parsed = parse_int(row.get("id"))
            if parsed is not None:
                return [int(parsed)]
        return []

    def _draft_live_adjacent_pick_id(
        self,
        rows: List[Dict[str, Any]],
        current_pick_id: Optional[int],
        direction: str,
        *,
        prefer_open: bool = False,
    ) -> Optional[int]:
        ids = [int(row["id"]) for row in rows if parse_int(row.get("id")) is not None]
        if not ids:
            return None
        if current_pick_id not in ids:
            return self._draft_live_first_open_pick_id(rows) or ids[0]
        idx = ids.index(int(current_pick_id))
        step = -1 if direction == "previous" else 1
        next_idx = max(0, min(len(ids) - 1, idx + step))
        if prefer_open and step > 0:
            for row in rows[idx + 1:]:
                if str(row.get("selection_text") or "").strip() or parse_bool(row.get("skipped")):
                    continue
                parsed = parse_int(row.get("id"))
                if parsed is not None:
                    return int(parsed)
        return ids[next_idx]

    def _draft_live_remaining_seconds(self, started_at: Any, duration_seconds: int) -> int:
        raw = str(started_at or "").strip()
        if not raw:
            return int(duration_seconds)
        try:
            started = datetime.fromisoformat(raw)
        except ValueError:
            return int(duration_seconds)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return max(0, int(duration_seconds) - int(elapsed))

    def _draft_live_payload(
        self,
        conn: sqlite3.Connection,
        draft_year: int,
        *,
        state_row: Optional[Dict[str, Any]] = None,
        rows: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        rows = rows if rows is not None else self._draft_live_order_rows(conn, draft_year)
        state_row = state_row if state_row is not None else self._draft_live_state_row(conn, draft_year)
        duration_seconds = max(10, min(3600, parse_int((state_row or {}).get("duration_seconds")) or 180))
        enabled = parse_bool((state_row or {}).get("enabled"))
        current_pick_id = parse_int((state_row or {}).get("current_draft_order_id"))
        row_ids = {parse_int(row.get("id")) for row in rows}
        if current_pick_id not in row_ids:
            current_pick_id = self._draft_live_first_open_pick_id(rows)
        started_at = str((state_row or {}).get("started_at") or "").strip() or None
        options_text = str((state_row or {}).get("options_text") or "")
        pending_request_count = self._draft_live_pending_request_count(rows)
        requestable_pick_ids = self._draft_live_requestable_pick_ids(rows, current_pick_id) if enabled else []
        return {
            "draft_year": int(draft_year),
            "enabled": bool(enabled),
            "current_pick_id": current_pick_id,
            "requestable_pick_ids": requestable_pick_ids,
            "pending_request_count": pending_request_count,
            "max_pending_requests": DRAFT_LIVE_MAX_PENDING_REQUESTS,
            "duration_seconds": duration_seconds,
            "started_at": started_at,
            "remaining_seconds": self._draft_live_remaining_seconds(started_at, duration_seconds) if enabled else duration_seconds,
            "server_now": now_iso(),
            "options": self._draft_live_options(options_text),
            "options_text": options_text,
            "draft_order": rows,
        }

    def list_draft_live(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        year = draft_year if draft_year is not None else self.current_draft_year()
        if year < 2000 or year > 2100:
            raise ValueError("invalid_draft_year")
        with self.connect() as conn:
            return self._draft_live_payload(conn, int(year))

    def update_draft_live_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        draft_year = parse_int(payload.get("draft_year")) or self.current_draft_year()
        if draft_year < 2000 or draft_year > 2100:
            raise ValueError("invalid_draft_year")
        enabled = parse_bool(payload.get("enabled"))
        duration_seconds = max(10, min(3600, parse_int(payload.get("duration_seconds")) or 180))
        current_pick_id = parse_int(payload.get("current_pick_id"))
        reset_timer = parse_bool(payload.get("reset_timer"))
        options_text = "\n".join(str(item).strip() for item in payload.get("options") or [] if str(item).strip()) \
            if isinstance(payload.get("options"), list) else str(payload.get("options_text") or "")
        timestamp = now_iso()
        with self.connect() as conn:
            rows = self._draft_live_order_rows(conn, int(draft_year))
            ids = {parse_int(row.get("id")) for row in rows}
            if current_pick_id is None:
                current_pick_id = self._draft_live_first_open_pick_id(rows)
            elif current_pick_id not in ids:
                raise ValueError("invalid_current_pick")
            existing = self._draft_live_state_row(conn, int(draft_year))
            previous_pick_id = parse_int((existing or {}).get("current_draft_order_id"))
            started_at = str((existing or {}).get("started_at") or "").strip() or None
            if enabled and (reset_timer or not started_at or previous_pick_id != current_pick_id or not parse_bool((existing or {}).get("enabled"))):
                started_at = timestamp
            if not enabled:
                started_at = None
            conn.execute(
                """
                INSERT INTO draft_live_state (
                    draft_year, enabled, current_draft_order_id, duration_seconds,
                    started_at, options_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_year)
                DO UPDATE SET
                    enabled = excluded.enabled,
                    current_draft_order_id = excluded.current_draft_order_id,
                    duration_seconds = excluded.duration_seconds,
                    started_at = excluded.started_at,
                    options_text = excluded.options_text,
                    updated_at = excluded.updated_at
                """,
                (
                    int(draft_year),
                    1 if enabled else 0,
                    current_pick_id,
                    duration_seconds,
                    started_at,
                    options_text,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            return self._draft_live_payload(conn, int(draft_year))

    def control_draft_live(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        draft_year = parse_int(payload.get("draft_year")) or self.current_draft_year()
        if draft_year < 2000 or draft_year > 2100:
            raise ValueError("invalid_draft_year")
        action = str(payload.get("action") or "").strip().lower()
        if action not in {"previous", "next", "restart", "skip"}:
            raise ValueError("invalid_draft_control")
        timestamp = now_iso()
        with self.connect() as conn:
            rows = self._draft_live_order_rows(conn, int(draft_year))
            if not rows:
                raise ValueError("draft_order_empty")
            state_row = self._draft_live_state_row(conn, int(draft_year)) or {}
            current_pick_id = parse_int(state_row.get("current_draft_order_id")) or self._draft_live_first_open_pick_id(rows)
            if action == "restart":
                next_pick_id = current_pick_id
            else:
                if action == "skip" and current_pick_id is not None:
                    conn.execute(
                        """
                        INSERT INTO draft_live_selections (
                            draft_order_id, selection_text, option_value, custom_text,
                            skipped, selected_by_email, selected_by_name, selected_by_role,
                            selected_at, updated_at
                        ) VALUES (?, 'Saltado', 'Saltado', NULL, 1, NULL, NULL, 'admin', ?, ?)
                        ON CONFLICT(draft_order_id)
                        DO UPDATE SET
                            selection_text = excluded.selection_text,
                            option_value = excluded.option_value,
                            custom_text = excluded.custom_text,
                            skipped = excluded.skipped,
                            selected_by_email = excluded.selected_by_email,
                            selected_by_name = excluded.selected_by_name,
                            selected_by_role = excluded.selected_by_role,
                            selected_at = excluded.selected_at,
                            updated_at = excluded.updated_at
                        """,
                        (int(current_pick_id), timestamp, timestamp),
                    )
                    rows = self._draft_live_order_rows(conn, int(draft_year))
                next_pick_id = self._draft_live_adjacent_pick_id(
                    rows,
                    current_pick_id,
                    "previous" if action == "previous" else "next",
                    prefer_open=action in {"next", "skip"},
                )
            duration_seconds = max(10, min(3600, parse_int(state_row.get("duration_seconds")) or 180))
            options_text = str(state_row.get("options_text") or "")
            conn.execute(
                """
                INSERT INTO draft_live_state (
                    draft_year, enabled, current_draft_order_id, duration_seconds,
                    started_at, options_text, created_at, updated_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_year)
                DO UPDATE SET
                    enabled = 1,
                    current_draft_order_id = excluded.current_draft_order_id,
                    started_at = excluded.started_at,
                    updated_at = excluded.updated_at
                """,
                (int(draft_year), next_pick_id, duration_seconds, timestamp, options_text, timestamp, timestamp),
            )
            conn.commit()
            return self._draft_live_payload(conn, int(draft_year))

    def submit_draft_live_pick(
        self,
        draft_order_id: int,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
        *,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            pick = conn.execute("SELECT * FROM draft_order WHERE id = ?", (int(draft_order_id),)).fetchone()
            if not pick:
                raise ValueError("draft_pick_not_found")
            draft_year = int(pick["draft_year"])
            state_row = self._draft_live_state_row(conn, draft_year) or {}
            if not is_admin and not parse_bool(state_row.get("enabled")):
                raise ValueError("draft_mode_inactive")
            current_pick_id = parse_int(state_row.get("current_draft_order_id"))
            if current_pick_id is None:
                rows_for_current = self._draft_live_order_rows(conn, draft_year)
                current_pick_id = self._draft_live_first_open_pick_id(rows_for_current)
            if not is_admin and current_pick_id != int(draft_order_id):
                raise ValueError("not_current_pick")

            if parse_bool(payload.get("clear")):
                conn.execute("DELETE FROM draft_live_selections WHERE draft_order_id = ?", (int(draft_order_id),))
            else:
                option_value = str(payload.get("option_value") or "").strip()
                custom_text = str(payload.get("custom_text") or "").strip()
                skipped = parse_bool(payload.get("skipped"))
                if skipped:
                    selection_text = "Saltado"
                    option_value = "Saltado"
                    custom_text = ""
                elif option_value == "__other__":
                    if not custom_text:
                        raise ValueError("selection_required")
                    selection_text = custom_text
                else:
                    if not option_value:
                        raise ValueError("selection_required")
                    selection_text = option_value
                    custom_text = ""
                conn.execute(
                    """
                    INSERT INTO draft_live_selections (
                        draft_order_id, selection_text, option_value, custom_text,
                        skipped, selected_by_email, selected_by_name, selected_by_role,
                        selected_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(draft_order_id)
                    DO UPDATE SET
                        selection_text = excluded.selection_text,
                        option_value = excluded.option_value,
                        custom_text = excluded.custom_text,
                        skipped = excluded.skipped,
                        selected_by_email = excluded.selected_by_email,
                        selected_by_name = excluded.selected_by_name,
                        selected_by_role = excluded.selected_by_role,
                        selected_at = excluded.selected_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(draft_order_id),
                        selection_text,
                        option_value,
                        custom_text or None,
                        1 if skipped else 0,
                        str(actor.get("email") or "").strip() or None,
                        str(actor.get("name") or "").strip() or None,
                        str(actor.get("role") or "").strip() or ("admin" if is_admin else "gm"),
                        timestamp,
                        timestamp,
                    ),
                )

            rows = self._draft_live_order_rows(conn, draft_year)
            state_row = self._draft_live_state_row(conn, draft_year) or state_row
            should_advance = parse_bool(payload.get("advance")) if "advance" in payload else (current_pick_id == int(draft_order_id) and not parse_bool(payload.get("clear")))
            if should_advance:
                next_pick_id = self._draft_live_adjacent_pick_id(rows, int(draft_order_id), "next", prefer_open=True)
                if next_pick_id == int(draft_order_id):
                    next_pick_id = None
                duration_seconds = max(10, min(3600, parse_int(state_row.get("duration_seconds")) or 180))
                options_text = str(state_row.get("options_text") or "")
                conn.execute(
                    """
                    INSERT INTO draft_live_state (
                        draft_year, enabled, current_draft_order_id, duration_seconds,
                        started_at, options_text, created_at, updated_at
                    ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(draft_year)
                    DO UPDATE SET
                        enabled = 1,
                        current_draft_order_id = excluded.current_draft_order_id,
                        started_at = excluded.started_at,
                        updated_at = excluded.updated_at
                    """,
                    (draft_year, next_pick_id, duration_seconds, timestamp, options_text, timestamp, timestamp),
                )
            conn.commit()
            return self._draft_live_payload(conn, draft_year)

    def process_draft_results(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        year = parse_int(str(draft_year)) if draft_year is not None else self.current_draft_year()
        if year is None or year < PLAYER_CONTRACT_MIN_YEAR or year > PLAYER_CONTRACT_MAX_YEAR:
            raise ValueError("unsupported_draft_year")
        settings = self.get_settings()
        timestamp = now_iso()
        supported_salary_seasons = PLAYER_CONTRACT_SEASONS
        created_holds: List[Dict[str, Any]] = []
        created_rights: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    d.id AS draft_order_id,
                    d.draft_year,
                    d.draft_round,
                    d.pick_number,
                    d.owner_team_code,
                    d.original_team_code,
                    t.id AS team_id,
                    COALESCE(t.name, d.owner_team_code) AS team_name,
                    s.selection_text,
                    COALESCE(s.skipped, 0) AS skipped,
                    s.processed_type,
                    s.processed_dead_contract_id,
                    s.processed_asset_id,
                    s.processed_at
                FROM draft_order d
                JOIN teams t ON t.code = d.owner_team_code
                LEFT JOIN draft_live_selections s ON s.draft_order_id = d.id
                WHERE d.draft_year = ?
                ORDER BY
                    CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                    d.pick_number,
                    d.id
                """,
                (int(year),),
            )
            rows = [row_to_dict(cur, row) for row in cur.fetchall()]
            for row in rows:
                draft_order_id = parse_int(row.get("draft_order_id"))
                pick_number = parse_int(row.get("pick_number"))
                draft_round = normalize_pick_round(row.get("draft_round"))
                selection_text = str(row.get("selection_text") or "").strip()
                team_code = normalize_team_code(row.get("owner_team_code")) or ""
                team_id = parse_int(row.get("team_id"))
                if not draft_order_id or not team_id or not team_code:
                    continue
                if parse_bool(row.get("processed_at")) or str(row.get("processed_type") or "").strip():
                    skipped.append({
                        "draft_order_id": draft_order_id,
                        "team_code": team_code,
                        "pick_number": pick_number,
                        "draft_round": draft_round,
                        "reason": "already_processed",
                    })
                    continue
                if parse_bool(row.get("skipped")):
                    skipped.append({
                        "draft_order_id": draft_order_id,
                        "team_code": team_code,
                        "pick_number": pick_number,
                        "draft_round": draft_round,
                        "reason": "pick_skipped",
                    })
                    continue
                if not selection_text:
                    skipped.append({
                        "draft_order_id": draft_order_id,
                        "team_code": team_code,
                        "pick_number": pick_number,
                        "draft_round": draft_round,
                        "reason": "no_selection",
                    })
                    continue
                if draft_round == "1st":
                    if pick_number is None or pick_number < 1 or pick_number > 30:
                        errors.append({
                            "draft_order_id": draft_order_id,
                            "team_code": team_code,
                            "pick_number": pick_number,
                            "draft_round": draft_round,
                            "selection": selection_text,
                            "error": "rookie_scale_pick_out_of_range",
                        })
                        continue
                    scale = self._rookie_scale_salary_for_pick(settings, int(year), int(pick_number))
                    projected_salary = scale.get("salary")
                    if projected_salary is None or projected_salary <= 0:
                        errors.append({
                            "draft_order_id": draft_order_id,
                            "team_code": team_code,
                            "pick_number": pick_number,
                            "draft_round": draft_round,
                            "selection": selection_text,
                            "error": "missing_rookie_scale_salary",
                            "salary_season": scale.get("salary_season"),
                            "setting_key": scale.get("setting_key"),
                            "checked_keys": scale.get("checked_keys") or [],
                        })
                        continue
                    salary_texts = {season: None for season in supported_salary_seasons}
                    salary_season = parse_int(scale.get("salary_season")) or int(year)
                    salary_texts[salary_season] = str(int(round(projected_salary)))
                    max_order = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM dead_contracts WHERE team_id = ?",
                        (team_id,),
                    ).fetchone()["mx"]
                    profile_id = self._resolve_profile_for_new_row(
                        conn,
                        {"name": selection_text},
                        name=selection_text,
                        timestamp=timestamp,
                    )
                    dead_cur = conn.execute(
                        """
                        INSERT INTO dead_contracts (
                            team_id, profile_id, row_order, dead_type, label, amount_text, amount_num,
                            exclude_from_gasto, exclude_from_cap,
                            salary_2025_text, salary_2025_num,
                            salary_2026_text, salary_2026_num,
                            salary_2027_text, salary_2027_num,
                            salary_2028_text, salary_2028_num,
                            salary_2029_text, salary_2029_num,
                            salary_2030_text, salary_2030_num,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, 'draft_hold', ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            team_id,
                            profile_id,
                            int(max_order) + 1,
                            selection_text,
                            salary_texts[2025],
                            parse_salary_amount(salary_texts[2025]),
                            salary_texts[2025],
                            parse_salary_amount(salary_texts[2025]),
                            salary_texts[2026],
                            parse_salary_amount(salary_texts[2026]),
                            salary_texts[2027],
                            parse_salary_amount(salary_texts[2027]),
                            salary_texts[2028],
                            parse_salary_amount(salary_texts[2028]),
                            salary_texts[2029],
                            parse_salary_amount(salary_texts[2029]),
                            salary_texts[2030],
                            parse_salary_amount(salary_texts[2030]),
                            timestamp,
                            timestamp,
                        ),
                    )
                    dead_contract_id = int(dead_cur.lastrowid)
                    if profile_id is not None:
                        self._record_player_transaction(
                            conn,
                            profile_id=int(profile_id),
                            dead_contract_id=dead_contract_id,
                            action="draft_cap_hold",
                            team_code=team_code,
                            summary=f"{team_code} añade el cap hold de draft de {selection_text}",
                            details={
                                "draft_year": int(year),
                                "salary_season": salary_season,
                                "draft_round": draft_round,
                                "pick_number": pick_number,
                                "projected_salary": int(round(projected_salary)),
                                "projected_salary_source": scale.get("source"),
                                "rookie_scale_setting_key": scale.get("setting_key"),
                            },
                            created_at=timestamp,
                        )
                    conn.execute(
                        """
                        UPDATE draft_live_selections
                        SET processed_type = 'draft_cap_hold',
                            processed_dead_contract_id = ?,
                            processed_asset_id = NULL,
                            processed_at = ?,
                            updated_at = ?
                        WHERE draft_order_id = ?
                        """,
                        (dead_contract_id, timestamp, timestamp, draft_order_id),
                    )
                    created_holds.append({
                        "draft_order_id": draft_order_id,
                        "dead_contract_id": dead_contract_id,
                        "team_code": team_code,
                        "pick_number": pick_number,
                        "selection": selection_text,
                        "projected_salary": int(round(projected_salary)),
                        "salary_season": salary_season,
                        "projected_salary_source": scale.get("source"),
                        "rookie_scale_setting_key": scale.get("setting_key"),
                    })
                    continue
                if draft_round == "2nd":
                    max_order = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (team_id,),
                    ).fetchone()["mx"]
                    asset_cur = conn.execute(
                        """
                        INSERT INTO assets (
                            team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                            draft_pick_type, draft_round, original_owner, exception_type,
                            draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                            draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                            created_at, updated_at
                        )
                        VALUES (?, ?, 'player_right', ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, 0, 0, 0, NULL, NULL, 0, ?, ?)
                        """,
                        (
                            team_id,
                            int(max_order) + 1,
                            str(int(year)),
                            selection_text,
                            f"Draft {int(year)} · Pick #{pick_number} · 2ª ronda",
                            timestamp,
                            timestamp,
                        ),
                    )
                    asset_id = int(asset_cur.lastrowid)
                    conn.execute(
                        """
                        UPDATE draft_live_selections
                        SET processed_type = 'player_right',
                            processed_dead_contract_id = NULL,
                            processed_asset_id = ?,
                            processed_at = ?,
                            updated_at = ?
                        WHERE draft_order_id = ?
                        """,
                        (asset_id, timestamp, timestamp, draft_order_id),
                    )
                    created_rights.append({
                        "draft_order_id": draft_order_id,
                        "asset_id": asset_id,
                        "team_code": team_code,
                        "pick_number": pick_number,
                        "selection": selection_text,
                    })
                    continue
                skipped.append({
                    "draft_order_id": draft_order_id,
                    "team_code": team_code,
                    "pick_number": pick_number,
                    "draft_round": draft_round,
                    "reason": "unsupported_round",
                })
            conn.commit()
            return {
                "ok": not errors,
                "draft_year": int(year),
                "created_cap_holds": created_holds,
                "created_player_rights": created_rights,
                "skipped": skipped,
                "errors": errors,
                "draft_live": self._draft_live_payload(conn, int(year)),
            }

    def _attach_option_decisions(self, conn: sqlite3.Connection, players: List[Dict[str, Any]], team_id: int) -> None:
        self._player_repository.attach_option_decisions(conn, players, team_id)

    def get_team(self, code: str, move_season_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        service = TeamDetailService(
            self,
            TeamDetailOperations(
                select_players=self._select_team_players,
                attach_option_decisions=self._attach_option_decisions,
                select_frozen_draft_picks=self._select_frozen_draft_picks,
                get_settings=self.get_settings,
                luxury_repeater=self._team_luxury_repeater_for_season,
                hard_cap=self._team_apron_hard_cap_for_season,
                calculate_summary=self._calc_summary,
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
        return service.get(code, move_season_year)

    def get_player_record(self, player_id: int) -> Optional[Dict[str, Any]]:
        return self._player_repository.record(player_id)

    def get_asset_record(self, asset_id: int) -> Optional[Dict[str, Any]]:
        return self._asset_repository.asset(asset_id)

    def _select_frozen_draft_picks(self, conn: sqlite3.Connection, team_id: int) -> List[Dict[str, Any]]:
        return self._team_repository.select_frozen_draft_picks(conn, team_id)

    def _set_matching_draft_pick_frozen(
        self,
        conn: sqlite3.Connection,
        team_id: int,
        team_code: str,
        draft_year: int,
        draft_round: str,
        frozen: bool,
        timestamp: str,
    ) -> Optional[int]:
        normalized_round = normalize_pick_round(draft_round)
        row = conn.execute(
            """
            SELECT id
            FROM assets
            WHERE team_id = ?
              AND asset_type = 'draft_pick'
              AND CAST(COALESCE(year, '') AS INTEGER) = ?
              AND COALESCE(draft_round, '1st') = ?
            ORDER BY
              CASE WHEN COALESCE(draft_pick_type, 'own') = 'own' THEN 0 ELSE 1 END,
              id
            LIMIT 1
            """,
            (team_id, int(draft_year), normalized_round),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE assets SET draft_pick_frozen = ?, updated_at = ? WHERE id = ?",
                (1 if frozen else 0, timestamp, int(row["id"])),
            )
            return int(row["id"])
        if not frozen:
            return None
        max_order = conn.execute(
            "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
            (team_id,),
        ).fetchone()["mx"]
        cur = conn.execute(
            """
            INSERT INTO assets (
                team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                draft_pick_type, draft_round, original_owner, exception_type,
                draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                created_at, updated_at
            )
            VALUES (?, ?, 'draft_pick', ?, ?, '', NULL, NULL, 'own', ?, NULL, NULL, 0, 0, 0, NULL, NULL, 1, ?, ?)
            """,
            (
                team_id,
                int(max_order) + 1,
                str(int(draft_year)),
                f"{normalized_round} pick",
                normalized_round,
                timestamp,
                timestamp,
            ),
        )
        return int(cur.lastrowid)

    def _sync_frozen_draft_pick_asset_flag(
        self,
        conn: sqlite3.Connection,
        team_id: int,
        team_code: str,
        draft_year: int,
        draft_round: str,
        timestamp: str,
    ) -> Optional[int]:
        normalized_round = normalize_pick_round(draft_round)
        active = conn.execute(
            """
            SELECT 1
            FROM frozen_draft_picks
            WHERE team_id = ?
              AND draft_year = ?
              AND draft_round = ?
            LIMIT 1
            """,
            (team_id, int(draft_year), normalized_round),
        ).fetchone()
        return self._set_matching_draft_pick_frozen(
            conn,
            team_id,
            team_code,
            int(draft_year),
            normalized_round,
            bool(active),
            timestamp,
        )

    def _upsert_frozen_draft_pick_conn(
        self,
        conn: sqlite3.Connection,
        team_id: int,
        team_code: str,
        penalty_season_year: int,
        draft_year: int,
        draft_round: str,
        reason: Optional[str],
        notes: Optional[str],
        timestamp: str,
    ) -> Dict[str, Any]:
        normalized_round = normalize_pick_round(draft_round)
        conn.execute(
            """
            INSERT INTO frozen_draft_picks (
                team_id, penalty_season_year, draft_year, draft_round, reason, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, penalty_season_year, draft_year, draft_round)
            DO UPDATE SET
                reason = excluded.reason,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                team_id,
                int(penalty_season_year),
                int(draft_year),
                normalized_round,
                reason,
                notes,
                timestamp,
                timestamp,
            ),
        )
        self._sync_frozen_draft_pick_asset_flag(conn, team_id, team_code, int(draft_year), normalized_round, timestamp)
        cur = conn.execute(
            """
            SELECT f.*, t.code AS team_code, t.name AS team_name
            FROM frozen_draft_picks f
            JOIN teams t ON t.id = f.team_id
            WHERE f.team_id = ?
              AND f.penalty_season_year = ?
              AND f.draft_year = ?
              AND f.draft_round = ?
            """,
            (team_id, int(penalty_season_year), int(draft_year), normalized_round),
        )
        row = cur.fetchone()
        return row_to_dict(cur, row)

    def create_frozen_draft_pick(self, team_code: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        code = normalize_team_code(team_code)
        penalty_season_year = parse_int(payload.get("penalty_season_year"))
        draft_year = parse_int(payload.get("draft_year"))
        if not code or penalty_season_year is None or draft_year is None:
            return None
        timestamp = now_iso()
        with self.connect() as conn:
            team = conn.execute("SELECT id, code FROM teams WHERE code = ?", (code,)).fetchone()
            if not team:
                return None
            row = self._upsert_frozen_draft_pick_conn(
                conn,
                int(team["id"]),
                str(team["code"]),
                int(penalty_season_year),
                int(draft_year),
                payload.get("draft_round") or "1st",
                str(payload.get("reason") or "").strip() or "Finalizó por encima del 2do apron",
                str(payload.get("notes") or "").strip() or None,
                timestamp,
            )
            conn.commit()
            return row

    def get_frozen_draft_pick_record(self, frozen_pick_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT f.*, t.code AS team_code, t.name AS team_name
                FROM frozen_draft_picks f
                JOIN teams t ON t.id = f.team_id
                WHERE f.id = ?
                """,
                (int(frozen_pick_id),),
            )
            row = cur.fetchone()
            return row_to_dict(cur, row) if row else None

    def update_frozen_draft_pick(self, frozen_pick_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            old_cur = conn.execute(
                """
                SELECT f.*, t.code AS team_code
                FROM frozen_draft_picks f
                JOIN teams t ON t.id = f.team_id
                WHERE f.id = ?
                """,
                (int(frozen_pick_id),),
            )
            old_row = old_cur.fetchone()
            if not old_row:
                return None
            old = row_to_dict(old_cur, old_row)
            team_id = int(old["team_id"])
            team_code = str(old["team_code"])
            penalty_season_year = parse_int(payload.get("penalty_season_year")) or int(old["penalty_season_year"])
            draft_year = parse_int(payload.get("draft_year")) or int(old["draft_year"])
            draft_round = normalize_pick_round(payload.get("draft_round") or old.get("draft_round"))
            reason = str(payload.get("reason") if "reason" in payload else old.get("reason") or "").strip() or None
            notes = str(payload.get("notes") if "notes" in payload else old.get("notes") or "").strip() or None
            conn.execute(
                """
                UPDATE frozen_draft_picks
                SET penalty_season_year = ?, draft_year = ?, draft_round = ?, reason = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (int(penalty_season_year), int(draft_year), draft_round, reason, notes, timestamp, int(frozen_pick_id)),
            )
            self._sync_frozen_draft_pick_asset_flag(
                conn,
                team_id,
                team_code,
                int(old["draft_year"]),
                str(old.get("draft_round") or "1st"),
                timestamp,
            )
            self._sync_frozen_draft_pick_asset_flag(conn, team_id, team_code, int(draft_year), draft_round, timestamp)
            cur = conn.execute(
                """
                SELECT f.*, t.code AS team_code, t.name AS team_name
                FROM frozen_draft_picks f
                JOIN teams t ON t.id = f.team_id
                WHERE f.id = ?
                """,
                (int(frozen_pick_id),),
            )
            row = cur.fetchone()
            conn.commit()
            return row_to_dict(cur, row) if row else None

    def delete_frozen_draft_pick(self, frozen_pick_id: int) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT f.*, t.code AS team_code, t.name AS team_name
                FROM frozen_draft_picks f
                JOIN teams t ON t.id = f.team_id
                WHERE f.id = ?
                """,
                (int(frozen_pick_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            deleted = row_to_dict(cur, row)
            conn.execute("DELETE FROM frozen_draft_picks WHERE id = ?", (int(frozen_pick_id),))
            self._sync_frozen_draft_pick_asset_flag(
                conn,
                int(deleted["team_id"]),
                str(deleted["team_code"]),
                int(deleted["draft_year"]),
                str(deleted.get("draft_round") or "1st"),
                timestamp,
            )
            conn.commit()
            return deleted

    def get_dead_contract_record(self, dead_contract_id: int) -> Optional[Dict[str, Any]]:
        return self._asset_repository.dead_contract(dead_contract_id)

    def audit_trade_snapshot(
        self,
        team_codes: List[str],
        player_ids: Optional[List[Any]] = None,
        asset_ids: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        def clean_ints(values: Optional[List[Any]]) -> List[int]:
            out: List[int] = []
            seen: set[int] = set()
            if not isinstance(values, list):
                return out
            for value in values:
                parsed = parse_int(str(value))
                if parsed is None or parsed <= 0 or parsed in seen:
                    continue
                seen.add(parsed)
                out.append(parsed)
            return out

        normalized_team_codes: List[str] = []
        for code in team_codes or []:
            normalized = normalize_team_code(code)
            if normalized and normalized not in normalized_team_codes:
                normalized_team_codes.append(normalized)

        clean_player_ids = clean_ints(player_ids)
        clean_asset_ids = clean_ints(asset_ids)
        snapshot: Dict[str, Any] = {
            "teams": [],
            "players": [],
            "assets": [],
        }

        with self.connect() as conn:
            for code in normalized_team_codes:
                team_cur = conn.execute(
                    """
                    SELECT
                        t.id,
                        t.code,
                        t.gm,
                        t.cash_received,
                        t.cash_sent,
                        t.apron_hard_cap,
                        COALESCE(SUM(CASE WHEN p.id IS NULL THEN 0 WHEN COALESCE(p.is_two_way, 0) = 1 OR UPPER(COALESCE(p.bird_rights, '')) = 'TW' THEN 0 ELSE 1 END), 0) AS standard_contracts,
                        COALESCE(SUM(CASE WHEN p.id IS NULL THEN 0 WHEN COALESCE(p.is_two_way, 0) = 1 OR UPPER(COALESCE(p.bird_rights, '')) = 'TW' THEN 1 ELSE 0 END), 0) AS two_way_contracts
                    FROM teams t
                    LEFT JOIN players p ON p.team_id = t.id
                    WHERE t.code = ?
                    GROUP BY t.id
                    """,
                    (code,),
                )
                row = team_cur.fetchone()
                if row:
                    snapshot["teams"].append(row_to_dict(team_cur, row))

            if clean_player_ids:
                placeholders = ",".join("?" for _ in clean_player_ids)
                player_cur = conn.execute(
                    f"""
                    SELECT
                        p.id,
                        p.profile_id,
                        COALESCE(pp.name, p.name) AS name,
                        t.code AS team_code,
                        p.position,
                        p.bird_rights,
                        p.rating,
                        p.years_left,
                        p.is_two_way
                    FROM players p
                    LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    JOIN teams t ON t.id = p.team_id
                    WHERE p.id IN ({placeholders})
                    ORDER BY p.id
                    """,
                    clean_player_ids,
                )
                snapshot["players"] = [row_to_dict(player_cur, row) for row in player_cur.fetchall()]

            if clean_asset_ids:
                placeholders = ",".join("?" for _ in clean_asset_ids)
                asset_cur = conn.execute(
                    f"""
                    SELECT
                        a.id,
                        t.code AS team_code,
                        a.asset_type,
                        a.year,
                        a.label,
                        a.draft_pick_type,
                        a.draft_round,
                        a.original_owner,
                        a.draft_pick_sold_to,
                        a.draft_pick_conditional_teams,
                        a.detail
                    FROM assets a
                    JOIN teams t ON t.id = a.team_id
                    WHERE a.id IN ({placeholders})
                    ORDER BY a.id
                    """,
                    clean_asset_ids,
                )
                snapshot["assets"] = [row_to_dict(asset_cur, row) for row in asset_cur.fetchall()]

        return snapshot

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
        service = PlayerCatalogService(
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
        return service.list_players(
            include_private=include_private,
            sync_generated=sync_generated,
            include_salary_history=include_salary_history,
            collect_timings=collect_timings,
        )

    def list_player_salary_history(self, profile_id: int) -> List[Dict[str, Any]]:
        return self._player_repository.list_salary_history(profile_id)

    def player_identity_integrity_report(self) -> Dict[str, Any]:
        return self._player_identity_service().integrity_report()

    def assert_player_identity_integrity(self) -> None:
        self._player_identity_service().assert_integrity()

    def list_gm_history(self, code: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        return self._team_repository.list_gm_history(code)

    def replace_gm_history(self, code: str, entries: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        return self._team_repository.replace_gm_history(code, entries)

    def list_tracker(self, season_year: Optional[int] = None, busy_timeout_ms: int = 5000) -> Dict[str, Any]:
        service = TrackerService(
            self,
            TrackerOperations(
                select_players=self._select_team_players,
                luxury_repeater=self._team_luxury_repeater_for_season,
                hard_cap=self._team_apron_hard_cap_for_season,
                calculate_summary=self._calc_summary,
                normalize_pick_type=normalize_pick_type,
                get_cache=self._get_tracker_cache,
                set_cache=self._set_tracker_cache,
                is_lock_error=self._is_sqlite_lock_error,
            ),
            min_year=CAP_FORECAST_MIN_YEAR,
            max_year=CAP_FORECAST_MAX_YEAR,
        )
        return service.list(season_year, busy_timeout_ms)

    def list_team_economy(self, season_year: Optional[int] = None) -> Dict[str, Any]:
        return self._settings_repository.list_team_economy(season_year)

    def export_league_workbook(self) -> bytes:
        return LeagueWorkbookExportService(
            self,
            get_settings=self.get_settings,
            list_teams=self.list_teams,
            list_tracker=self.list_tracker,
            list_players=self.list_players,
            list_free_agents=self.list_free_agents,
            get_team=self.get_team,
            parse_bool=parse_bool,
            normalize_team_codes=normalize_team_codes,
            season_label=season_label,
            public_settings_payload=public_settings_payload,
            workbook_bytes=_xlsx_workbook_bytes,
            unrestricted_type=FREE_AGENT_TYPE_UNRESTRICTED,
            min_year=CAP_FORECAST_MIN_YEAR,
            max_year=CAP_FORECAST_MAX_YEAR,
        ).export()

    def _owner_office_rows_from_json(self, value: Any, section: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        rows: List[Dict[str, Any]] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or "").strip()
            label = str(raw.get("label") or "").strip()
            row_type = str(raw.get("type") or "field").strip().lower()
            if row_type not in {"category", "field"}:
                row_type = "field"
            if not key or not label:
                continue
            raw_value = "" if raw.get("value") is None else str(raw.get("value"))
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "type": row_type,
                    "value": self._owner_office_field_value_text(raw_value) if row_type == "field" else raw_value,
                }
            )
        return self._owner_office_apply_calculated_rows(section, rows)

    def _owner_office_field_value_text(self, value: Any) -> str:
        text = "" if value is None else str(value).strip()
        compact = re.sub(r"[€$]", "", text.replace(" ", ""))
        if re.fullmatch(r"-?\d+\.\d{1,2}", compact):
            return text.replace(".", ",")
        return text

    def _normalize_owner_office_rows(self, rows: Any, section: Optional[str] = None) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for idx, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()
            if not label:
                continue
            key = str(raw.get("key") or "").strip() or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or f"row_{idx}"
            row_type = str(raw.get("type") or "field").strip().lower()
            if row_type not in {"category", "field"}:
                row_type = "field"
            raw_value = "" if raw.get("value") is None else str(raw.get("value")).strip()[:500]
            normalized.append(
                {
                    "key": key[:80],
                    "label": label[:160],
                    "type": row_type,
                    "value": self._owner_office_field_value_text(raw_value) if row_type == "field" else raw_value,
                }
            )
        return self._owner_office_apply_calculated_rows(section, normalized)

    def _owner_office_apply_calculated_rows(
        self,
        section: Optional[str],
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if section not in {"income", "expenses"} or not rows:
            return rows

        amounts: Dict[str, float] = {}
        present: set[str] = set()
        for row in rows:
            key = str(row.get("key") or "")
            parsed = parse_amount_like(row.get("value"))
            amounts[key] = float(parsed or 0)
            if parsed is not None:
                present.add(key)

        def value(key: str) -> float:
            return amounts.get(key, 0.0)

        def magnitude(key: str) -> float:
            return abs(value(key))

        def calculated(keys: List[str], amount: float) -> str:
            if not any(key in present for key in keys):
                return ""
            return self._owner_import_value_text(amount)

        if section == "income":
            formulas = {
                "recaudacion": calculated(
                    ["entradas_playoffs", "entradas_regular_season", "precio_medio_entrada", "consumiciones"],
                    (
                        value("entradas_playoffs") + value("entradas_regular_season")
                    ) * (0.6 * value("precio_medio_entrada"))
                    + (
                        value("entradas_playoffs") + value("entradas_regular_season")
                    ) * (0.9 * value("consumiciones")),
                ),
                "merchandising": calculated(
                    ["ventas_camisetas_ropa", "precio_medio_articulo"],
                    value("ventas_camisetas_ropa") * value("precio_medio_articulo"),
                ),
                "derechos": calculated(
                    ["tv_globales", "tv_local", "licencias"],
                    value("tv_globales") + value("tv_local") + value("licencias"),
                ),
                "sponsor": calculated(
                    ["patrocinador_jersey", "patrocinador_estadio", "patrocinadores_generales"],
                    value("patrocinador_jersey")
                    + value("patrocinador_estadio")
                    + value("patrocinadores_generales"),
                ),
                "flujos_caja_positivos": calculated(
                    [
                        "traspasos_positivos",
                        "bonificaciones",
                        "reparto_beneficios_positivo",
                        "reparto_impuesto_lujo",
                    ],
                    value("traspasos_positivos")
                    + value("bonificaciones")
                    + value("reparto_beneficios_positivo")
                    + value("reparto_impuesto_lujo"),
                ),
            }
        else:
            formulas = {
                "coste_plantilla": calculated(
                    ["salarios", "multa"],
                    -magnitude("salarios") - magnitude("multa"),
                ),
                "cuerpo_tecnico": calculated(
                    ["multiplicador_exitos", "gastos_cuerpo_tecnico"],
                    magnitude("multiplicador_exitos") * magnitude("gastos_cuerpo_tecnico") * -1,
                ),
                "gastos_estadio": calculated(
                    ["partidos", "gastos_partido", "indice_coste_estadio"],
                    magnitude("partidos") * magnitude("gastos_partido") * magnitude("indice_coste_estadio") * -1,
                ),
                "gastos_television": calculated(
                    ["produccion"],
                    magnitude("produccion") * -1,
                ),
                "costes_marketing": calculated(
                    ["costes_ineficiencia", "unidades", "coste_por_unidad", "indice_coste_marketing"],
                    -magnitude("costes_ineficiencia")
                    - (magnitude("unidades") * magnitude("coste_por_unidad")) * magnitude("indice_coste_marketing"),
                ),
                "gastos_operativos": calculated(
                    ["gastos_operativos_valor", "indice_coste_operativo"],
                    magnitude("gastos_operativos_valor") * magnitude("indice_coste_operativo") * -1,
                ),
                "flujos_caja_negativos": calculated(
                    ["traspasos_negativos", "sanciones", "reparto_beneficios_negativo"],
                    -magnitude("traspasos_negativos")
                    - magnitude("sanciones")
                    - magnitude("reparto_beneficios_negativo"),
                ),
            }

        calculated_rows: List[Dict[str, Any]] = []
        for row in rows:
            row_copy = dict(row)
            key = str(row_copy.get("key") or "")
            if str(row_copy.get("type") or "") == "category" and key in formulas:
                row_copy["value"] = formulas[key]
            calculated_rows.append(row_copy)
        return calculated_rows

    def _owner_office_breakdown_total(self, section: str, rows: List[Dict[str, Any]]) -> Optional[float]:
        category_keys = {
            "income": {
                "recaudacion",
                "merchandising",
                "derechos",
                "sponsor",
                "flujos_caja_positivos",
            },
            "expenses": {
                "coste_plantilla",
                "cuerpo_tecnico",
                "gastos_estadio",
                "gastos_television",
                "costes_marketing",
                "gastos_operativos",
                "flujos_caja_negativos",
            },
        }.get(section, set())
        total = 0.0
        has_value = False
        for row in rows:
            if str(row.get("key") or "") not in category_keys:
                continue
            parsed = parse_amount_like(row.get("value"))
            if parsed is None:
                continue
            total += float(parsed)
            has_value = True
        return total if has_value else None

    def _owner_import_schema_payload(self) -> Dict[str, Any]:
        schema = owner_office_import_schema()
        return {
            section: [
                {
                    "key": row["key"],
                    "label": row["label"],
                    "type": row["type"],
                    "category_key": row["category_key"],
                    "category_label": row["category_label"],
                }
                for row in rows
            ]
            for section, rows in schema.items()
        }

    def _owner_import_header_value(self, row: Dict[str, Any], aliases: List[str]) -> str:
        normalized_aliases = {normalize_import_text(alias) for alias in aliases}
        for key, value in row.items():
            if normalize_import_text(key) in normalized_aliases:
                return str(value or "").strip()
        return ""

    def _owner_import_key(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]+", "_", text).strip("_")

    def _owner_import_section(self, value: Any) -> str:
        normalized = normalize_import_text(value)
        if normalized in {"income", "ingreso", "ingresos", "revenue", "revenues"}:
            return "income"
        if normalized in {"expense", "expenses", "gasto", "gastos", "coste", "costes"}:
            return "expenses"
        if normalized in {"economy", "economia", "economía", "summary", "totals", "totales", "tracker"}:
            return "economy"
        return ""

    def _owner_import_resolve_row(self, section: str, key_value: str, label_value: str, category_value: str) -> tuple[Optional[Dict[str, str]], Optional[str]]:
        schema = owner_office_import_schema().get(section) or []
        by_key = {row["key"]: row for row in schema}
        candidate_key = self._owner_import_key(key_value)
        if candidate_key:
            row = by_key.get(candidate_key)
            if row and (section == "economy" or row["type"] == "field"):
                return row, None
            if row and row["type"] == "category":
                return None, f"'{key_value}' es una categoría, no una fila importable"
            label_value = label_value or key_value

        label_norm = normalize_import_text(label_value)
        if not label_norm:
            return None, "Falta key o label/concepto"
        matches = [row for row in schema if row["type"] == "field" and normalize_import_text(row["label"]) == label_norm]
        category_norm = normalize_import_text(category_value)
        if category_norm:
            matches = [
                row for row in matches
                if normalize_import_text(row["category_key"]) == category_norm
                or normalize_import_text(row["category_label"]) == category_norm
            ]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"Concepto ambiguo '{label_value}'. Usa la columna key."
        return None, f"Concepto desconocido '{label_value}'"

    def _owner_import_normalize_records(
        self,
        raw_records: List[Dict[str, Any]],
        teams_by_code: Dict[str, Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        normalized_records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for idx, raw in enumerate(raw_records):
            line = parse_int(raw.get("line")) or idx + 2
            season = parse_int(raw.get("season_year") or raw.get("season"))
            team_code = normalize_team_code(raw.get("team_code") or raw.get("team"))
            section = self._owner_import_section(raw.get("section"))
            key_value = str(raw.get("key") or "").strip()
            label_value = str(raw.get("label") or "").strip()
            category_value = str(raw.get("category") or "").strip()
            raw_amount = raw.get("value")
            raw_amount_text = str(raw_amount or "").strip()
            amount = None if not raw_amount_text else parse_csv_amount(raw_amount)
            if season is None or season < 2000 or season > 2100:
                errors.append({"line": line, "message": "Temporada inválida. Usa el año inicial, por ejemplo 2025."})
                continue
            if not team_code or team_code not in teams_by_code:
                errors.append({"line": line, "message": f"Equipo inválido: {team_code or '-'}"})
                continue
            if section not in {"income", "expenses", "economy"}:
                errors.append({"line": line, "message": "Sección inválida. Usa income/ingresos, expenses/gastos o economy/totales."})
                continue
            row_def, row_error = self._owner_import_resolve_row(section, key_value, label_value, category_value)
            if row_error or not row_def:
                errors.append({"line": line, "message": row_error or "Concepto inválido."})
                continue
            if raw_amount_text and amount is None:
                errors.append({"line": line, "message": f"Importe inválido para {team_code} {row_def['label']}."})
                continue
            normalized_amount = None
            if amount is not None:
                if section == "income" or (section == "economy" and row_def["key"] == "revenue"):
                    normalized_amount = abs(float(amount))
                elif section == "expenses" or (section == "economy" and row_def["key"] == "expenses"):
                    normalized_amount = -abs(float(amount))
                else:
                    normalized_amount = float(amount)
            normalized_records.append(
                {
                    "line": line,
                    "season_year": int(season),
                    "team_code": team_code,
                    "team_name": str(teams_by_code[team_code].get("name") or ""),
                    "section": section,
                    "key": row_def["key"],
                    "label": row_def["label"],
                    "category_key": row_def["category_key"],
                    "category_label": row_def["category_label"],
                    "value": normalized_amount,
                }
            )
        return normalized_records, errors

    def _owner_import_group_records(
        self,
        records: List[Dict[str, Any]],
        economy_by_team: Optional[Dict[tuple[int, str], Dict[str, float]]] = None,
    ) -> List[Dict[str, Any]]:
        groups: Dict[tuple[int, str], Dict[str, Any]] = {}
        for record in records:
            key = (int(record["season_year"]), str(record["team_code"]))
            if key not in groups:
                groups[key] = {
                    "season_year": int(record["season_year"]),
                    "team_code": str(record["team_code"]),
                    "team_name": str(record.get("team_name") or ""),
                    "income": {},
                    "expenses": {},
                    "economy": {},
                    "income_rows": 0,
                    "expenses_rows": 0,
                    "economy_rows": 0,
                }
            section = str(record["section"])
            row_key = str(record["key"])
            raw_value = record.get("value")
            if raw_value is None or str(raw_value).strip() == "":
                if row_key not in groups[key][section]:
                    groups[key][section][row_key] = None
            else:
                value = float(raw_value or 0)
                existing = groups[key][section].get(row_key)
                groups[key][section][row_key] = float(existing or 0) + value
            if section == "income":
                groups[key]["income_rows"] += 1
            elif section == "expenses":
                groups[key]["expenses_rows"] += 1
            elif section == "economy":
                groups[key]["economy_rows"] += 1

        summary: List[Dict[str, Any]] = []
        for group in groups.values():
            group_key = (int(group["season_year"]), str(group["team_code"]))
            existing = (economy_by_team or {}).get(group_key) or {}
            economy = group.get("economy") or {}
            revenue = float(
                economy["revenue"]
                if economy.get("revenue") not in (None, "")
                else existing.get("revenue", 0)
            )
            expenses = float(
                economy["expenses"]
                if economy.get("expenses") not in (None, "")
                else existing.get("expenses", 0)
            )
            income_total = self._owner_office_breakdown_total(
                "income",
                self._owner_import_rows_for_json("income", group.get("income") or {}),
            )
            expenses_total = self._owner_office_breakdown_total(
                "expenses",
                self._owner_import_rows_for_json("expenses", group.get("expenses") or {}),
            )
            if income_total is not None:
                revenue = float(income_total)
            if expenses_total is not None:
                expenses = float(expenses_total)
            balance = float(
                economy["balance"]
                if economy.get("balance") not in (None, "") and income_total is None and expenses_total is None
                else existing.get("balance", revenue + expenses)
            )
            if income_total is not None or expenses_total is not None:
                balance = revenue + expenses
            summary.append(
                {
                    "season_year": int(group["season_year"]),
                    "team_code": str(group["team_code"]),
                    "team_name": str(group["team_name"]),
                    "income_rows": int(group["income_rows"]),
                    "expenses_rows": int(group["expenses_rows"]),
                    "economy_rows": int(group["economy_rows"]),
                    "revenue": revenue,
                    "expenses": expenses,
                    "balance": balance,
                    "has_income": bool(group["income"]),
                    "has_expenses": bool(group["expenses"]),
                    "has_economy": bool(group["economy"]),
                }
            )
        return sorted(summary, key=lambda row: (int(row["season_year"]), str(row["team_code"])))

    def _owner_import_value_text(self, value: Any) -> str:
        if value is None or str(value).strip() == "":
            return ""
        amount = float(value or 0)
        rounded = round(amount)
        if abs(amount - rounded) < 0.000001:
            return str(int(rounded))
        return f"{amount:.2f}".rstrip("0").rstrip(".")

    def _owner_import_rows_for_json(self, section: str, values_by_key: Dict[str, float]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for row in owner_office_import_schema().get(section, []):
            if row["type"] == "category":
                rows.append({"key": row["key"], "label": row["label"], "type": "category", "value": ""})
            else:
                rows.append(
                    {
                        "key": row["key"],
                        "label": row["label"],
                        "type": "field",
                        "value": self._owner_import_value_text(
                            values_by_key[row["key"]] if row["key"] in values_by_key else ""
                        ),
                    }
                )
        return self._owner_office_apply_calculated_rows(section, rows)

    def _owner_admin_import_service(self) -> OwnerAdminImportService:
        return OwnerAdminImportService(
            self,
            now=now_iso,
            economy_schema_payload=self._owner_import_schema_payload,
            economy_header_value=self._owner_import_header_value,
            normalize_economy_records=self._owner_import_normalize_records,
            group_economy_records=self._owner_import_group_records,
            rows_for_json=self._owner_import_rows_for_json,
            format_value=self._owner_import_value_text,
            rows_from_json=self._owner_office_rows_from_json,
            normalize_rows=self._normalize_owner_office_rows,
            breakdown_total=self._owner_office_breakdown_total,
            office_header_value=self._owner_office_import_header_value,
            normalize_office_records=self._owner_office_import_normalize_records,
            group_office_records=self._owner_office_import_group_records,
            performance_from_json=self._owner_performance_rows_from_json,
            normalize_performance=self._normalize_owner_performance_rows,
            objective_options=OWNER_SEASON_OBJECTIVES,
        )

    def preview_owner_economy_csv(self, csv_text: str) -> Dict[str, Any]:
        return self._owner_admin_import_service().preview_owner_economy_csv(csv_text)

    def apply_owner_economy_import(self, records_payload: Any) -> Dict[str, Any]:
        return self._owner_admin_import_service().apply_owner_economy_import(records_payload)

    def _owner_office_import_header_value(self, row: Dict[str, Any], aliases: List[str]) -> str:
        return self._owner_import_header_value(row, aliases)

    def _owner_office_import_normalize_records(
        self,
        raw_records: List[Dict[str, Any]],
        teams_by_code: Dict[str, Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for idx, raw in enumerate(raw_records):
            line = parse_int(raw.get("line")) or idx + 2
            season_year = parse_int(raw.get("season_year") or raw.get("season"))
            team_code = normalize_team_code(raw.get("team_code") or raw.get("team"))
            confidence_current = str(raw.get("confidence_current") or "").strip()[:80]
            confidence_change = str(raw.get("confidence_change") or "").strip()[:80]
            season_goal_set_raw = str(raw.get("season_goal_set") or "").strip()
            season_goal_achieved_raw = str(raw.get("season_goal_achieved") or "").strip()
            history_season_raw = str(raw.get("history_season") or "").strip()
            wins_raw = str(raw.get("wins") or "").strip()
            losses_raw = str(raw.get("losses") or "").strip()
            result = str(raw.get("result") or "").strip()[:80]
            if season_year is None or season_year < 2000 or season_year > 2100:
                errors.append({"line": line, "message": "Temporada inválida. Usa el año inicial, por ejemplo 2025."})
                continue
            if not team_code or team_code not in teams_by_code:
                errors.append({"line": line, "message": f"Equipo inválido: {team_code or '-'}"})
                continue

            season_goal_set = ""
            season_goal_achieved = ""
            if season_goal_set_raw:
                season_goal_set = self._normalize_owner_season_objective(season_goal_set_raw)
                if not season_goal_set:
                    errors.append({"line": line, "message": f"Objetivo fijado inválido: {season_goal_set_raw}."})
                    continue
            if season_goal_achieved_raw:
                season_goal_achieved = self._normalize_owner_season_objective(season_goal_achieved_raw)
                if not season_goal_achieved:
                    errors.append({"line": line, "message": f"Objetivo cumplido inválido: {season_goal_achieved_raw}."})
                    continue

            normalized_performance = raw.get("performance_row")
            has_normalized_performance = isinstance(normalized_performance, dict)
            has_performance = has_normalized_performance or any([history_season_raw, wins_raw, losses_raw, result])
            performance_row = None
            if has_normalized_performance:
                history_season = parse_int(normalized_performance.get("season_year"))
                if history_season is None or history_season < 2000 or history_season > 2100:
                    errors.append({"line": line, "message": "Temporada de historial inválida."})
                    continue
                wins = parse_int(normalized_performance.get("wins"))
                losses = parse_int(normalized_performance.get("losses"))
                performance_row = {
                    "season_year": max(2000, min(2100, history_season)),
                    "wins": "" if wins is None else max(0, min(100, wins)),
                    "losses": "" if losses is None else max(0, min(100, losses)),
                    "result": str(normalized_performance.get("result") or "").strip()[:80],
                }
            elif has_performance:
                history_season = parse_int(history_season_raw)
                if history_season is None or history_season < 2000 or history_season > 2100:
                    errors.append({"line": line, "message": "Temporada de historial inválida."})
                    continue
                wins = parse_int(wins_raw)
                losses = parse_int(losses_raw)
                if wins_raw and wins is None:
                    errors.append({"line": line, "message": "Victorias inválidas."})
                    continue
                if losses_raw and losses is None:
                    errors.append({"line": line, "message": "Derrotas inválidas."})
                    continue
                performance_row = {
                    "season_year": max(2000, min(2100, history_season)),
                    "wins": "" if wins is None else max(0, min(100, wins)),
                    "losses": "" if losses is None else max(0, min(100, losses)),
                    "result": result,
                }

            if not any([confidence_current, confidence_change, season_goal_set, season_goal_achieved, performance_row]):
                errors.append({"line": line, "message": "Fila sin datos importables."})
                continue

            records.append(
                {
                    "line": line,
                    "season_year": int(season_year),
                    "team_code": team_code,
                    "team_name": str(teams_by_code[team_code].get("name") or ""),
                    "confidence_current": confidence_current,
                    "confidence_change": confidence_change,
                    "season_goal_set": season_goal_set,
                    "season_goal_achieved": season_goal_achieved,
                    "performance_row": performance_row,
                }
            )
        errors.extend(self._owner_office_import_group_errors(records))
        return records, errors

    def _owner_office_import_group_errors(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[tuple[int, str], List[Dict[str, Any]]] = {}
        for record in records:
            grouped.setdefault((int(record["season_year"]), str(record["team_code"])), []).append(record)
        errors: List[Dict[str, Any]] = []
        for (_season_year, team_code), group_records in grouped.items():
            performance_rows = [row for row in group_records if row.get("performance_row")]
            if len(performance_rows) > 5:
                first_line = performance_rows[0].get("line")
                errors.append(
                    {
                        "line": first_line,
                        "message": f"{team_code} tiene más de 5 filas de historial deportivo para la misma temporada.",
                    }
                )
        return errors

    def _owner_office_import_group_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: Dict[tuple[int, str], Dict[str, Any]] = {}
        for record in records:
            key = (int(record["season_year"]), str(record["team_code"]))
            if key not in groups:
                groups[key] = {
                    "season_year": int(record["season_year"]),
                    "team_code": str(record["team_code"]),
                    "team_name": str(record.get("team_name") or ""),
                    "confidence_current": "",
                    "confidence_change": "",
                    "season_goal_set": "",
                    "season_goal_achieved": "",
                    "performance_rows": [],
                }
            for field in ["confidence_current", "confidence_change", "season_goal_set", "season_goal_achieved"]:
                value = str(record.get(field) or "").strip()
                if value:
                    groups[key][field] = value
            performance_row = record.get("performance_row")
            if isinstance(performance_row, dict):
                groups[key]["performance_rows"].append(performance_row)
        summary: List[Dict[str, Any]] = []
        for group in groups.values():
            group["performance_rows"] = sorted(
                group["performance_rows"],
                key=lambda row: parse_int(row.get("season_year")) or 0,
            )
            summary.append(
                {
                    "season_year": int(group["season_year"]),
                    "team_code": str(group["team_code"]),
                    "team_name": str(group["team_name"]),
                    "confidence_current": str(group["confidence_current"]),
                    "confidence_change": str(group["confidence_change"]),
                    "season_goal_set": str(group["season_goal_set"]),
                    "season_goal_achieved": str(group["season_goal_achieved"]),
                    "performance_count": len(group["performance_rows"]),
                    "performance_rows": group["performance_rows"],
                }
            )
        return sorted(summary, key=lambda row: (int(row["season_year"]), str(row["team_code"])))

    def preview_owner_office_csv(self, csv_text: str) -> Dict[str, Any]:
        return self._owner_admin_import_service().preview_owner_office_csv(csv_text)

    def apply_owner_office_import(self, records_payload: Any) -> Dict[str, Any]:
        return self._owner_admin_import_service().apply_owner_office_import(records_payload)

    def _owner_performance_rows_from_json(self, value: Any) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        rows: List[Dict[str, Any]] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            season_year = parse_int(raw.get("season_year"))
            wins = parse_int(raw.get("wins"))
            losses = parse_int(raw.get("losses"))
            result = str(raw.get("result") or "").strip()[:80]
            if season_year is None:
                continue
            rows.append(
                {
                    "season_year": season_year,
                    "wins": "" if wins is None else wins,
                    "losses": "" if losses is None else losses,
                    "result": result,
                }
            )
        return rows

    def _normalize_owner_performance_rows(self, rows: Any, season_year: int) -> List[Dict[str, Any]]:
        raw_rows = rows if isinstance(rows, list) else []
        normalized: List[Dict[str, Any]] = []
        for idx in range(5):
            raw = raw_rows[idx] if idx < len(raw_rows) and isinstance(raw_rows[idx], dict) else {}
            fallback_year = int(season_year) - 4 + idx
            row_year = parse_int(raw.get("season_year")) or fallback_year
            wins = parse_int(raw.get("wins"))
            losses = parse_int(raw.get("losses"))
            result = str(raw.get("result") or "").strip()[:80]
            normalized.append(
                {
                    "season_year": max(2000, min(2100, row_year)),
                    "wins": "" if wins is None else max(0, min(100, wins)),
                    "losses": "" if losses is None else max(0, min(100, losses)),
                    "result": result,
                }
            )
        return normalized

    def _normalize_owner_season_objective(self, value: Any) -> str:
        text = str(value or "").strip()
        return text if text in OWNER_SEASON_OBJECTIVES else ""

    def _owner_season_objective_evaluation(self, target: Any, achieved: Any) -> str:
        target_text = self._normalize_owner_season_objective(target)
        achieved_text = self._normalize_owner_season_objective(achieved)
        if not target_text or not achieved_text:
            return "No evaluable"
        target_rank = OWNER_SEASON_OBJECTIVES.index(target_text)
        achieved_rank = OWNER_SEASON_OBJECTIVES.index(achieved_text)
        difference = achieved_rank - target_rank
        if difference < 0:
            return f"Objetivo superado por {abs(difference)} nivel(es)"
        if difference == 0:
            return "Objetivo cumplido"
        return f"Objetivo no cumplido por {difference} nivel(es)"

    def _owner_attribute_value(self, value: Any) -> Optional[int]:
        parsed = parse_int(value)
        if parsed is None:
            return None
        return max(1, min(10, parsed))

    def _owner_profile_from_row(self, row: Optional[sqlite3.Row], include_private: bool = False) -> Dict[str, Any]:
        profile: Dict[str, Any] = {
            "owner_name": "",
            "owner_birth_date": "",
            "owner_photo_url": "",
            "owner_office_background_url": "",
            "owner_bio": "",
        }
        if row:
            profile.update(
                {
                    "owner_name": str(row["owner_name"] or ""),
                    "owner_birth_date": str(row["owner_birth_date"] or ""),
                    "owner_photo_url": sanitize_http_image_url(row["owner_photo_url"]),
                    "owner_office_background_url": sanitize_owner_background_url(row["owner_office_background_url"]),
                    "owner_bio": str(row["owner_bio"] or ""),
                }
            )
        if include_private:
            profile["attributes"] = {
                "ambicion_competitiva": self._owner_attribute_value(row["ambicion_competitiva"]) if row else None,
                "paciencia": self._owner_attribute_value(row["paciencia"]) if row else None,
                "intervencionismo": self._owner_attribute_value(row["intervencionismo"]) if row else None,
                "orientacion_financiera": self._owner_attribute_value(row["orientacion_financiera"]) if row else None,
                "orientacion_marca": self._owner_attribute_value(row["orientacion_marca"]) if row else None,
            }
        return profile

    def _normalize_owner_profile_payload(self, payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None

        def text_value(key: str, limit: int) -> str:
            return str(payload.get(key) or "").strip()[:limit]

        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        return {
            "owner_name": text_value("owner_name", 120),
            "owner_birth_date": text_value("owner_birth_date", 32),
            "owner_photo_url": sanitize_http_image_url(text_value("owner_photo_url", 1000)),
            "owner_bio": text_value("owner_bio", 2000),
            "ambicion_competitiva": self._owner_attribute_value(attributes.get("ambicion_competitiva")),
            "paciencia": self._owner_attribute_value(attributes.get("paciencia")),
            "intervencionismo": self._owner_attribute_value(attributes.get("intervencionismo")),
            "orientacion_financiera": self._owner_attribute_value(attributes.get("orientacion_financiera")),
            "orientacion_marca": self._owner_attribute_value(attributes.get("orientacion_marca")),
        }

    def _owner_exit_interview_from_row(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "team_id": int(row["team_id"]),
            "season_year": int(row["season_year"]),
            "gm_email": str(row["gm_email"] or ""),
            "gm_name": str(row["gm_name"] or ""),
            "status": str(row["status"] or "available"),
            "owner_message": str(row["owner_message"] or ""),
            "gm_response": str(row["gm_response"] or ""),
            "owner_final_message": str(row["owner_final_message"] or ""),
            "owner_conclusion_message": str(row["owner_conclusion_message"] or ""),
            "trust_delta": parse_int(row["trust_delta"]),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
        }

    def _owner_confidence_with_delta(self, value: Any, delta: int) -> Optional[str]:
        parsed = parse_float(str(value) if value is not None else None)
        if parsed is None:
            return None
        updated = parsed + int(delta)
        if float(updated).is_integer():
            return str(int(updated))
        return f"{updated:g}"

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

    def _owner_office_service(self) -> OwnerOfficeService:
        return OwnerOfficeService(
            self,
            OwnerOfficeOperations(
                profile_from_row=self._owner_profile_from_row,
                normalize_profile=self._normalize_owner_profile_payload,
                exit_interview_from_row=self._owner_exit_interview_from_row,
                rows_from_json=self._owner_office_rows_from_json,
                normalize_rows=self._normalize_owner_office_rows,
                breakdown_total=self._owner_office_breakdown_total,
                performance_from_json=self._owner_performance_rows_from_json,
                normalize_performance=self._normalize_owner_performance_rows,
                normalize_objective=self._normalize_owner_season_objective,
                objective_evaluation=self._owner_season_objective_evaluation,
                format_value=self._owner_import_value_text,
            ),
            now=now_iso,
            min_year=CAP_FORECAST_MIN_YEAR,
            max_year=CAP_FORECAST_MAX_YEAR,
            forecast_window=CAP_FORECAST_WINDOW,
        )

    def get_team_owner_office(self, code: str, include_private: bool = False) -> Optional[Dict[str, Any]]:
        return self._owner_office_service().get(code, include_private)

    def update_team_owner_office(self, code: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._owner_office_service().update(code, payload)

    def update_owner_background_url(self, code: str, background_url: str) -> Optional[Dict[str, Any]]:
        return self._owner_office_repository.update_owner_background_url(code, background_url)

    def update_owner_background_image(self, code: str, file_bytes: bytes, mime_type: str) -> Optional[Dict[str, Any]]:
        return self._owner_office_repository.update_owner_background_image(code, file_bytes, mime_type)

    def get_owner_background_image(self, code: str) -> Optional[tuple[bytes, str]]:
        return self._owner_office_repository.get_owner_background_image(code)

    def upsert_team_economy(self, season_year: int, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._settings_repository.upsert_team_economy(season_year, rows)

    def update_team_fields(self, code: str, payload: Dict[str, Any]) -> bool:
        return self._team_repository.update_fields(code, payload)

    def _team_luxury_history(self, conn: sqlite3.Connection, team_id: int, current_year: int) -> List[Dict[str, Any]]:
        return self._team_repository.luxury_history_conn(conn, team_id, current_year)

    def _team_luxury_repeater_for_season(self, conn: sqlite3.Connection, team_id: int, season_year: int) -> bool:
        return self._team_repository.luxury_repeater_conn(conn, team_id, season_year)

    def update_team_luxury_history(self, code: str, season_year: int, repeater: bool) -> bool:
        return self._team_repository.update_luxury_history(code, season_year, repeater)

    def _team_apron_hard_cap_for_season(self, conn: sqlite3.Connection, team_id: int, season_year: int, fallback: Any = None) -> str:
        return self._team_repository.hard_cap_conn(conn, team_id, season_year, fallback)

    def _team_apron_hard_caps(self, conn: sqlite3.Connection, team_id: int, current_year: int, fallback: Any = None) -> List[Dict[str, Any]]:
        return self._team_repository.hard_caps_conn(conn, team_id, current_year, fallback)

    def _update_team_apron_hard_cap_conn(self, conn: sqlite3.Connection, code: str, season_year: int, hard_cap: Any) -> bool:
        return self._team_repository.update_hard_cap_conn(conn, code, season_year, hard_cap)

    def update_team_apron_hard_cap(self, code: str, season_year: int, hard_cap: Any) -> bool:
        return self._team_repository.update_hard_cap(code, season_year, hard_cap)

    def _calc_summary(
        self,
        team: Dict[str, Any],
        players: List[Dict[str, Any]],
        assets: List[Dict[str, Any]],
        dead_contracts: List[Dict[str, Any]],
        settings: Dict[str, str],
        season_year: Optional[int] = None,
        luxury_repeater: bool = False,
        apron_hard_cap: Any = None,
        include_breakdowns: bool = True,
    ) -> Dict[str, float]:
        current_year = parse_int(season_year) or parse_int(settings.get("current_year")) or 2025
        if current_year < PLAYER_CONTRACT_MIN_YEAR or current_year > PLAYER_CONTRACT_MAX_YEAR:
            current_year = max(PLAYER_CONTRACT_MIN_YEAR, min(PLAYER_CONTRACT_MAX_YEAR, current_year))
        salary_cap = (
            parse_float(settings.get(f"salary_cap_{current_year}"))
            or parse_float(settings.get("salary_cap_2025"))
            or team["salary_cap"]
        )
        salary_floor = salary_floor_for_season(settings, current_year, salary_cap)

        player_metric_cache: Dict[tuple, float] = {}

        def player_cache_id(player: Dict[str, Any]) -> int:
            return int(player.get("id") or id(player))

        def cached_player_metric(player: Dict[str, Any], metric: str, calculator: Any) -> float:
            key = (metric, player_cache_id(player))
            if key not in player_metric_cache:
                player_metric_cache[key] = float(calculator() or 0.0)
            return player_metric_cache[key]

        def player_cap_hold(player: Dict[str, Any]) -> float:
            return cached_player_metric(
                player,
                "cap_hold",
                lambda: cap_hold_amount(player, current_year, settings, salary_cap),
            )

        def player_minimum_team_salary(player: Dict[str, Any]) -> float:
            return cached_player_metric(
                player,
                "minimum_team_salary",
                lambda: minimum_contract_team_salary(player, current_year, salary_cap),
            )

        def player_apron_yos_adjustment(player: Dict[str, Any]) -> float:
            return cached_player_metric(
                player,
                "apron_yos_adjustment",
                lambda: apron_yos_adjustment(player, current_year, salary_cap),
            )

        def player_salary_for_gasto(player: Dict[str, Any]) -> float:
            if is_exhibit10_player(player):
                return 0.0
            return player_minimum_team_salary(player)

        def player_salary_for_cap(player: Dict[str, Any]) -> float:
            hold = player_cap_hold(player)
            if hold > 0:
                return hold
            if is_two_way_player(player) or is_exhibit10_player(player):
                return 0.0
            return player_minimum_team_salary(player)

        def player_salary_for_apron(player: Dict[str, Any]) -> float:
            if player_cap_hold(player) > 0:
                return 0.0
            if is_two_way_player(player) or is_exhibit10_player(player):
                return 0.0
            return player_minimum_team_salary(player) + player_apron_yos_adjustment(player)

        # CAP Total: player team salary excluding Two-Way and Exhibit 10 contracts.
        cap_figure_players = sum(player_salary_for_cap(p) for p in players)
        # APRON Team Salary: Team Salary less cap holds, plus applicable 0-1 YOS adjustments.
        apron_figure_players = sum(player_salary_for_apron(p) for p in players)
        # GASTO Total: player payroll excluding non-financial Exhibit 10 contracts.
        player_payroll = sum(player_salary_for_gasto(p) for p in players)
        roster_counts = roster_contract_counts(players, current_year)
        roster_standard_count = roster_counts["standard"]
        roster_two_way_count = roster_counts["two_way"]

        dead_cap_team_salary = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) in {"normal", "draft_hold"}
            and not dead_contract_excluded_from_cap(d)
        )
        dead_cap_apron = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "normal"
            and not dead_contract_excluded_from_cap(d)
        )
        dead_cap_draft_hold = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "draft_hold"
            and not dead_contract_excluded_from_cap(d)
        )
        dead_gasto_normal = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "normal"
            and not dead_contract_excluded_from_gasto(d)
        )
        dead_gasto_two_way = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "two_way"
            and not dead_contract_excluded_from_gasto(d)
        )
        open_roster_hold = open_roster_spot_cap_hold(players, current_year, settings, salary_cap)
        open_roster_hold_amount = float(open_roster_hold.get("amount") or 0.0)
        exceptions = sum((a.get("amount_num") or 0.0) for a in assets if a.get("asset_type") == "exception")

        cap_figure_before_floor = cap_figure_players + dead_cap_team_salary + open_roster_hold_amount
        cap_figure = apply_salary_floor(settings, current_year, salary_cap, cap_figure_before_floor)
        salary_floor_adjustment = max(0.0, cap_figure - cap_figure_before_floor)
        apron_figure = apron_figure_players + dead_cap_apron
        payroll = player_payroll + dead_gasto_normal + dead_gasto_two_way

        luxury = salary_cap * 1.215
        luxury_overage = max(0.0, cap_figure - luxury)
        luxury_tax = luxury_tax_amount(luxury_overage, luxury_repeater)
        first_apron = (
            parse_float(settings.get(f"first_apron_{current_year}"))
            or parse_float(settings.get("first_apron"))
            or team["first_apron"]
        )
        second_apron = (
            parse_float(settings.get(f"second_apron_{current_year}"))
            or parse_float(settings.get("second_apron"))
            or team["second_apron"]
        )
        cash_limit_total = parse_float(settings.get("cash_limit_total")) or 0.0
        cash_received = float(team.get("cash_received") or 0.0)
        cash_sent = float(team.get("cash_sent") or 0.0)

        def breakdown_amount(label: str, amount: float) -> Dict[str, Any]:
            return {"label": label, "amount": float(amount or 0.0)}

        def breakdown_text(label: str, text: str) -> Dict[str, Any]:
            return {"label": label, "text": text}

        def player_name(player: Dict[str, Any]) -> str:
            return str(player.get("name") or "Jugador sin nombre").strip() or "Jugador sin nombre"

        def dead_contract_label(dead_contract: Dict[str, Any]) -> str:
            return str(dead_contract.get("label") or "CAP muerto").strip() or "CAP muerto"

        def season_marker(player: Dict[str, Any]) -> str:
            salary_marker = str(player.get(f"salary_{current_year}_text") or "").strip().upper()
            option_marker = str(player.get(f"option_{current_year}") or "").strip().upper()
            if salary_marker in {"NB", "EB", "FB", "QO"}:
                return salary_marker
            if option_marker in {"NB", "EB", "FB", "QO", "GAP"}:
                return option_marker
            return "cap hold"

        def cap_player_detail_lines() -> List[Dict[str, Any]]:
            lines: List[Dict[str, Any]] = []
            for player in players:
                hold = player_cap_hold(player)
                if hold > 0:
                    lines.append(
                        breakdown_amount(
                            f"Jugador - {player_name(player)} ({season_marker(player)} hold)",
                            hold,
                        )
                    )
                    continue
                if is_two_way_player(player) or is_exhibit10_player(player):
                    continue
                salary = player_minimum_team_salary(player)
                if salary > 0:
                    lines.append(breakdown_amount(f"Jugador - {player_name(player)}", salary))
            return lines

        def payroll_player_detail_lines() -> List[Dict[str, Any]]:
            lines: List[Dict[str, Any]] = []
            for player in players:
                if is_exhibit10_player(player):
                    continue
                salary = player_minimum_team_salary(player)
                if salary > 0:
                    label = f"Jugador - {player_name(player)}"
                    if is_two_way_player(player):
                        label = f"{label} (Two-Way)"
                    lines.append(breakdown_amount(label, salary))
            return lines

        def apron_player_detail_lines() -> List[Dict[str, Any]]:
            lines: List[Dict[str, Any]] = []
            for player in players:
                hold = player_cap_hold(player)
                if hold > 0:
                    lines.append(
                        breakdown_text(
                            f"Excluido - {player_name(player)}",
                            f"{season_marker(player)} hold no cuenta para apron",
                        )
                    )
                    continue
                if is_two_way_player(player) or is_exhibit10_player(player):
                    continue
                salary = player_minimum_team_salary(player)
                if salary > 0:
                    lines.append(breakdown_amount(f"Jugador - {player_name(player)}", salary))
                yos_adjustment = player_apron_yos_adjustment(player)
                if yos_adjustment > 0:
                    lines.append(breakdown_amount(f"Ajuste 0-1 YOS - {player_name(player)}", yos_adjustment))
            return lines

        def dead_contract_detail_lines(*, cap_types: set[str], exclude_field: str) -> List[Dict[str, Any]]:
            lines: List[Dict[str, Any]] = []
            for dead_contract in dead_contracts:
                dead_type = normalize_dead_type(dead_contract.get("dead_type"))
                if dead_type not in cap_types:
                    continue
                if exclude_field == "cap" and dead_contract_excluded_from_cap(dead_contract):
                    lines.append(breakdown_text(f"Excluido CAP - {dead_contract_label(dead_contract)}", "Marcado como excluido de CAP"))
                    continue
                if exclude_field == "gasto" and dead_contract_excluded_from_gasto(dead_contract):
                    lines.append(breakdown_text(f"Excluido gasto - {dead_contract_label(dead_contract)}", "Marcado como excluido de gasto"))
                    continue
                amount = dead_contract_salary_num(dead_contract, current_year)
                if amount > 0:
                    lines.append(breakdown_amount(f"CAP muerto - {dead_contract_label(dead_contract)}", amount))
            return lines

        def luxury_tax_detail_lines(overage: float, repeater: bool) -> List[Dict[str, Any]]:
            lines: List[Dict[str, Any]] = []
            remaining = max(0.0, float(overage or 0.0))
            if not math.isfinite(remaining):
                return lines
            if remaining <= 0:
                return lines
            tier_size = 5_000_000.0
            rates = [2.5, 2.75, 3.5, 4.25] if repeater else [1.5, 1.75, 2.5, 3.25]
            tier_index = 0
            lower_bound = 0.0
            max_detail_tiers = 20
            while remaining > 0 and tier_index < max_detail_tiers:
                taxable = min(tier_size, remaining)
                if tier_index < len(rates):
                    rate = rates[tier_index]
                else:
                    rate = rates[-1] + ((tier_index - len(rates) + 1) * 0.5)
                upper_bound = lower_bound + taxable
                lines.append(
                    breakdown_amount(
                        f"Tramo luxury {int(lower_bound / 1_000_000)}-{int(math.ceil(upper_bound / 1_000_000))}M x{rate:g}",
                        taxable * rate,
                    )
                )
                remaining -= taxable
                lower_bound += taxable
                tier_index += 1
            if remaining > 0:
                lines.append(
                    breakdown_amount(
                        f"Resto luxury desde {int(lower_bound / 1_000_000)}M",
                        luxury_tax_amount(remaining, repeater),
                    )
                )
            return lines

        balance_breakdowns: Dict[str, List[Dict[str, Any]]] = {}
        if include_breakdowns:
            cap_player_lines = cap_player_detail_lines()
            payroll_player_lines = payroll_player_detail_lines()
            apron_player_lines = apron_player_detail_lines()
            dead_cap_team_salary_lines = dead_contract_detail_lines(cap_types={"normal", "draft_hold"}, exclude_field="cap")
            dead_cap_apron_lines = dead_contract_detail_lines(cap_types={"normal"}, exclude_field="cap")
            dead_gasto_normal_lines = dead_contract_detail_lines(cap_types={"normal"}, exclude_field="gasto")
            dead_gasto_two_way_lines = dead_contract_detail_lines(cap_types={"two_way"}, exclude_field="gasto")
            open_roster_lines = (
                [
                    breakdown_amount(
                        f"{int(open_roster_hold.get('open_spots') or 0)} plazas x minimo rookie",
                        open_roster_hold_amount,
                    )
                ]
                if open_roster_hold_amount > 0
                else []
            )
            salary_floor_lines = (
                [breakdown_amount("Ajuste para llegar al Salary Floor", salary_floor_adjustment)]
                if salary_floor_adjustment > 0
                else []
            )

            balance_breakdowns = {
                "cap_total": [
                    breakdown_amount("Jugadores y cap holds computables", cap_figure_players),
                    *cap_player_lines,
                    breakdown_amount("CAP muerto y rookie scale holds", dead_cap_team_salary),
                    *dead_cap_team_salary_lines,
                    breakdown_amount("Open roster spot cap holds", open_roster_hold_amount),
                    *open_roster_lines,
                    breakdown_amount("Ajuste Salary Floor", salary_floor_adjustment),
                    *salary_floor_lines,
                ],
                "gasto_total": [
                    breakdown_amount("Salarios de jugadores", player_payroll),
                    *payroll_player_lines,
                    breakdown_amount("CAP muerto", dead_gasto_normal),
                    *dead_gasto_normal_lines,
                    breakdown_amount("CAP muerto Two-Way", dead_gasto_two_way),
                    *dead_gasto_two_way_lines,
                ],
                "apron_account": [
                    breakdown_amount("Jugadores sin cap holds", apron_figure_players),
                    *apron_player_lines,
                    breakdown_amount("CAP muerto computable", dead_cap_apron),
                    *dead_cap_apron_lines,
                ],
                "luxury_tax": [
                    breakdown_amount("CAP TOTAL", cap_figure),
                    breakdown_amount("Luxury cap", luxury),
                    breakdown_amount("Exceso sobre luxury", luxury_overage),
                    breakdown_text("Tipo de luxury", "Reincidente" if luxury_repeater else "No reincidente"),
                    breakdown_amount("Luxury tax calculada", luxury_tax),
                    *luxury_tax_detail_lines(luxury_overage, luxury_repeater),
                ],
            }

        return {
            "player_payroll": player_payroll,
            "dead_cap": dead_gasto_normal + dead_gasto_two_way,
            "dead_cap_normal": dead_cap_apron,
            "dead_cap_draft_hold": dead_cap_draft_hold,
            "dead_cap_team_salary": dead_cap_team_salary,
            "dead_cap_two_way": dead_gasto_two_way,
            "dead_gasto_normal": dead_gasto_normal,
            "dead_gasto_two_way": dead_gasto_two_way,
            "open_roster_spot_cap_hold": open_roster_hold_amount,
            "open_roster_spot_count": int(open_roster_hold.get("open_spots") or 0),
            "open_roster_spot_roster_count": int(open_roster_hold.get("roster_count") or 0),
            "open_roster_spot_minimum_salary": float(open_roster_hold.get("minimum_salary") or 0.0),
            "exceptions_total": exceptions,
            "salary_floor": salary_floor,
            "cap_figure_before_floor": cap_figure_before_floor,
            "salary_floor_adjustment": salary_floor_adjustment,
            "cap_figure": cap_figure,
            "apron_account": apron_figure,
            "payroll": payroll,
            "salary_cap_2025": salary_cap,
            "salary_cap": salary_cap,
            "first_apron": first_apron,
            "second_apron": second_apron,
            "current_year": current_year,
            "room_to_cap": salary_cap - cap_figure,
            "room_to_luxury": luxury - cap_figure,
            "room_to_first_apron": first_apron - apron_figure,
            "room_to_second_apron": second_apron - apron_figure,
            "luxury_tax": luxury_tax,
            "balance_breakdowns": balance_breakdowns,
            "cash_received": cash_received,
            "cash_sent": cash_sent,
            "cash_limit_total": cash_limit_total,
            "trade_move_phase": normalize_move_phase(settings.get("trade_move_phase")),
            "trade_move_limit_pre30": max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0),
            "trade_move_limit_post30": max(0, parse_int(settings.get("trade_move_limit_post30")) or 0),
            "roster_standard_count": roster_standard_count,
            "roster_two_way_count": roster_two_way_count,
            "apron_hard_cap": normalize_apron_hard_cap(apron_hard_cap) or "",
        }

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
            summary = self._calc_summary(
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

    def list_offseason_exception_preview(self, season_year: Optional[int] = None) -> Dict[str, Any]:
        with self.connect() as conn:
            settings = self.get_settings()
            current_year = parse_int(settings.get("current_year")) or 2025
            selected_year = parse_int(season_year) or current_year
            teams = self.list_teams()
            rows = []
            for team in teams:
                team_data = self.get_team(str(team.get("code") or ""), move_season_year=selected_year)
                if not team_data:
                    continue
                summary = (team_data.get("season_summaries") or {}).get(str(selected_year))
                if not summary:
                    continue
                estimate = self._offseason_exception_estimate_from_summary(
                    summary,
                    team_data.get("assets") or [],
                )
                rows.append(
                    {
                        "team_code": team.get("code"),
                        "team_name": team.get("name"),
                        **estimate,
                    }
                )
            return {
                "season_year": selected_year,
                "season_label": season_label(selected_year),
                "rows": rows,
            }

    def _cartera_cap_hold_rights(
        self,
        players: List[Dict[str, Any]],
        season_year: int,
        settings: Dict[str, str],
        salary_cap: float,
    ) -> List[Dict[str, Any]]:
        rights: List[Dict[str, Any]] = []
        for player in players:
            hold_amount = cap_hold_amount(player, season_year, settings, salary_cap)
            if hold_amount <= 0:
                continue
            label = self._cap_hold_display_label(player, season_year)
            rights.append(
                {
                    "player_id": parse_int(player.get("id")),
                    "profile_id": parse_int(player.get("profile_id")),
                    "player_name": str(player.get("name") or "Jugador").strip() or "Jugador",
                    "hold_label": label,
                    "amount": round(float(hold_amount or 0.0)),
                }
            )
        return sorted(
            rights,
            key=lambda item: (-float(item.get("amount") or 0.0), str(item.get("player_name") or "").lower()),
        )

    def _cartera_exception_paths(
        self,
        estimate: Dict[str, Any],
        target_amount: float,
    ) -> List[Dict[str, Any]]:
        paths: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_item(item: Dict[str, Any], source_label: str, source_key: str = "") -> None:
            key = str(item.get("key") or item.get("short_label") or item.get("label") or "").strip()
            amount = float(item.get("amount") or 0.0)
            if amount < target_amount:
                return
            dedupe_key = (key, source_key)
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            hard_cap = str(item.get("hard_cap") or "").strip()
            hard_cap_label = ""
            if hard_cap == "first":
                hard_cap_label = "Hard cap en el 1er apron si se usa."
            elif hard_cap == "second":
                hard_cap_label = "Hard cap en el 2do apron si se usa."
            paths.append(
                {
                    "type": "exception",
                    "key": key,
                    "label": str(item.get("short_label") or item.get("label") or key).strip(),
                    "amount": round(amount),
                    "source": source_label,
                    "hard_cap": hard_cap,
                    "details": hard_cap_label,
                }
            )

        for item in estimate.get("eligible") or []:
            add_item(item, "Elegible según situación proyectada")

        for path in estimate.get("paths") or []:
            source_label = str(path.get("label") or "Ruta alternativa").strip()
            source_key = str(path.get("key") or source_label).strip()
            for item in path.get("eligible") or []:
                add_item(item, source_label, source_key)

        return paths

    def list_cartera(self, amount: Any, season_year: Optional[int] = None) -> Dict[str, Any]:
        target_amount = parse_amount_like(amount)
        if target_amount is None or target_amount <= 0:
            raise ValueError("invalid_amount")

        settings = self.get_settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        selected_year = parse_int(season_year) or current_year
        selected_year = max(CAP_FORECAST_MIN_YEAR, min(CAP_FORECAST_MAX_YEAR, selected_year))

        rows: List[Dict[str, Any]] = []
        for team in self.list_teams():
            team_code = str(team.get("code") or "").strip().upper()
            team_data = self.get_team(team_code, move_season_year=selected_year)
            if not team_data:
                continue
            summary = (team_data.get("season_summaries") or {}).get(str(selected_year))
            if not summary:
                continue

            estimate = self._offseason_exception_estimate_from_summary(summary, team_data.get("assets") or [])
            cap_space = float(summary.get("room_to_cap") or 0.0)
            cap_total = float(summary.get("cap_figure") or 0.0)
            apron_account = float(summary.get("apron_account") or 0.0)
            salary_cap = float(summary.get("salary_cap") or 0.0)

            paths: List[Dict[str, Any]] = []
            if cap_space >= target_amount:
                paths.append(
                    {
                        "type": "cap_space",
                        "key": "cap_space",
                        "label": "Espacio salarial",
                        "amount": round(cap_space),
                        "source": "Debajo del Salary Cap",
                        "hard_cap": "",
                        "details": "Puede absorber el importe con espacio salarial.",
                    }
                )

            exception_paths = self._cartera_exception_paths(estimate, target_amount)
            paths.extend(exception_paths)
            if not paths:
                continue

            rights = self._cartera_cap_hold_rights(
                team_data.get("players") or [],
                selected_year,
                settings,
                salary_cap,
            )
            cap_hold_total = sum(float(item.get("amount") or 0.0) for item in rights)
            needs_renounce_review = bool(exception_paths and cap_hold_total > 0 and cap_total > salary_cap)

            rows.append(
                {
                    "team_code": team_code,
                    "team_name": team.get("name"),
                    "season_year": selected_year,
                    "season_label": season_label(selected_year),
                    "cap_total": round(cap_total),
                    "salary_cap": round(salary_cap),
                    "cap_space": round(cap_space),
                    "apron_account": round(apron_account),
                    "first_apron": round(float(summary.get("first_apron") or 0.0)),
                    "second_apron": round(float(summary.get("second_apron") or 0.0)),
                    "operating_mode": estimate.get("operating_mode"),
                    "paths": sorted(paths, key=lambda item: (0 if item.get("type") == "cap_space" else 1, -float(item.get("amount") or 0.0))),
                    "cap_hold_total": round(cap_hold_total),
                    "needs_renounce_review": needs_renounce_review,
                    "rights_to_renounce": rights if needs_renounce_review else [],
                }
            )

        rows.sort(
            key=lambda row: (
                0 if any(path.get("type") == "cap_space" for path in row.get("paths") or []) else 1,
                -max((float(path.get("amount") or 0.0) for path in row.get("paths") or []), default=0.0),
                str(row.get("team_code") or ""),
            )
        )
        return {
            "amount": round(float(target_amount)),
            "season_year": selected_year,
            "season_label": season_label(selected_year),
            "seasons": [current_year + idx for idx in range(6)],
            "rows": rows,
        }

    FREE_AGENT_TEAM_APPEAL_COLUMNS = [
        ("under_23_single", "Menores de 23 · 1 año"),
        ("under_23_multi", "Menores de 23 · multi"),
        ("age_23_26_single", "23-26 · 1 año"),
        ("age_23_26_multi", "23-26 · multi"),
        ("age_27_33_single", "27-33 · 1 año"),
        ("age_27_33_multi", "27-33 · multi"),
        ("over_34_single", "34+ · 1 año"),
        ("over_34_multi", "34+ · multi"),
    ]

    FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS = [
        ("under_23_multi", "Ranking atractivo <23", "Multianual"),
        ("under_23_single", "Ranking atractivo <23", "1 año"),
        ("age_23_26_multi", "Ranking atractivo <27", "Multianual"),
        ("age_23_26_single", "Ranking atractivo <27", "1 año"),
        ("age_27_33_multi", "Ranking atractivo 27-33", "Multianual"),
        ("age_27_33_single", "Ranking atractivo 27-33", "1 año"),
        ("over_34_multi", "Ranking atractivo +34", "Multianual"),
        ("over_34_single", "Ranking atractivo +34", "1 año"),
    ]

    def _free_agent_team_appeal_columns_payload(self) -> List[Dict[str, Any]]:
        return [
            {"key": key, "label": f"{group} · {sub_label}", "group": group, "sub_label": sub_label}
            for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS
        ]

    @staticmethod
    def _free_agent_appeal_header_key(value: Any) -> str:
        text = normalize_import_text(value).casefold()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        aliases = {
            "team": "team_code",
            "equipo": "team_code",
            "franquicia": "team_code",
            "team_code": "team_code",
            "codigo": "team_code",
            "under_23_single": "under_23_single",
            "u23_single": "under_23_single",
            "menor_23_single": "under_23_single",
            "menores_23_single": "under_23_single",
            "under_23_1": "under_23_single",
            "u23_1": "under_23_single",
            "menor_23_1": "under_23_single",
            "menores_23_1": "under_23_single",
            "menos_23_1": "under_23_single",
            "under_23_multi": "under_23_multi",
            "u23_multi": "under_23_multi",
            "menor_23_multi": "under_23_multi",
            "menores_23_multi": "under_23_multi",
            "menos_23_multi": "under_23_multi",
            "23_26_single": "age_23_26_single",
            "age_23_26_single": "age_23_26_single",
            "edad_23_26_single": "age_23_26_single",
            "23_26_1": "age_23_26_single",
            "age_23_26_1": "age_23_26_single",
            "edad_23_26_1": "age_23_26_single",
            "23_26_multi": "age_23_26_multi",
            "age_23_26_multi": "age_23_26_multi",
            "edad_23_26_multi": "age_23_26_multi",
            "27_33_single": "age_27_33_single",
            "age_27_33_single": "age_27_33_single",
            "edad_27_33_single": "age_27_33_single",
            "27_33_1": "age_27_33_single",
            "age_27_33_1": "age_27_33_single",
            "edad_27_33_1": "age_27_33_single",
            "27_33_multi": "age_27_33_multi",
            "age_27_33_multi": "age_27_33_multi",
            "edad_27_33_multi": "age_27_33_multi",
            "over_34_single": "over_34_single",
            "34_single": "over_34_single",
            "34_1": "over_34_single",
            "mas_34_single": "over_34_single",
            "mayor_34_single": "over_34_single",
            "over_34_1": "over_34_single",
            "over_34_multi": "over_34_multi",
            "34_multi": "over_34_multi",
            "mas_34_multi": "over_34_multi",
            "mayor_34_multi": "over_34_multi",
        }
        return aliases.get(text, text)

    def _free_agent_appeal_ranking_header_key(self, group_value: Any, sub_value: Any = "") -> str:
        group = self._free_agent_appeal_header_key(group_value)
        sub = self._free_agent_appeal_header_key(sub_value)
        combined = "_".join(part for part in [group, sub] if part)
        aliases = {
            "under_23_multi": "under_23_multi",
            "u23_multi": "under_23_multi",
            "ranking_atractivo_23_multianual": "under_23_multi",
            "atractivo_23_multianual": "under_23_multi",
            "menores_23_multianual": "under_23_multi",
            "menos_23_multianual": "under_23_multi",
            "under_23_single": "under_23_single",
            "u23_single": "under_23_single",
            "under_23_1": "under_23_single",
            "u23_1": "under_23_single",
            "ranking_atractivo_23_1_ano": "under_23_single",
            "ranking_atractivo_23_1": "under_23_single",
            "atractivo_23_1_ano": "under_23_single",
            "menores_23_1_ano": "under_23_single",
            "menos_23_1_ano": "under_23_single",
            "age_23_26_multi": "age_23_26_multi",
            "23_26_multi": "age_23_26_multi",
            "ranking_atractivo_27_multianual": "age_23_26_multi",
            "atractivo_27_multianual": "age_23_26_multi",
            "menores_27_multianual": "age_23_26_multi",
            "age_23_26_single": "age_23_26_single",
            "23_26_single": "age_23_26_single",
            "23_26_1": "age_23_26_single",
            "ranking_atractivo_27_1_ano": "age_23_26_single",
            "ranking_atractivo_27_1": "age_23_26_single",
            "atractivo_27_1_ano": "age_23_26_single",
            "menores_27_1_ano": "age_23_26_single",
            "age_27_33_multi": "age_27_33_multi",
            "27_33_multi": "age_27_33_multi",
            "ranking_atractivo_27_33_multianual": "age_27_33_multi",
            "atractivo_27_33_multianual": "age_27_33_multi",
            "age_27_33_single": "age_27_33_single",
            "27_33_single": "age_27_33_single",
            "27_33_1": "age_27_33_single",
            "ranking_atractivo_27_33_1_ano": "age_27_33_single",
            "ranking_atractivo_27_33_1": "age_27_33_single",
            "atractivo_27_33_1_ano": "age_27_33_single",
            "over_34_multi": "over_34_multi",
            "34_multi": "over_34_multi",
            "ranking_atractivo_34_multianual": "over_34_multi",
            "atractivo_34_multianual": "over_34_multi",
            "mas_34_multianual": "over_34_multi",
            "mayores_34_multianual": "over_34_multi",
            "over_34_single": "over_34_single",
            "34_single": "over_34_single",
            "34_1": "over_34_single",
            "ranking_atractivo_34_1_ano": "over_34_single",
            "ranking_atractivo_34_1": "over_34_single",
            "atractivo_34_1_ano": "over_34_single",
            "mas_34_1_ano": "over_34_single",
            "mayores_34_1_ano": "over_34_single",
        }
        return aliases.get(combined, aliases.get(group, combined))

    def _free_agent_team_appeal_rankings_from_records(
        self,
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_key = {key: sorted(records, key=lambda record: (float(record.get(key) or 0.0), str(record.get("team_code") or ""))) for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS}
        max_rows = max((len(items) for items in by_key.values()), default=0)
        rankings: List[Dict[str, Any]] = []
        for idx in range(max_rows):
            row: Dict[str, Any] = {"rank": idx + 1}
            for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                item = by_key.get(key, [])[idx] if idx < len(by_key.get(key, [])) else None
                row[key] = {
                    "team_code": str(item.get("team_code") or "").upper() if item else "",
                    "team_name": str(item.get("team_name") or "") if item else "",
                    "value": float(item.get(key) or 0.0) if item else 0.0,
                }
            rankings.append(row)
        return rankings

    def _free_agent_team_appeal_records_from_rows(self, rows: List[List[str]]) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        if not rows:
            return {
                "ok": False,
                "errors": [{"line": None, "message": "El archivo está vacío."}],
                "records": [],
                "summary": {"record_count": 0, "team_count": 0},
                "columns": self._free_agent_team_appeal_columns_payload(),
                "rankings": [],
            }

        first_non_empty_idx = next((idx for idx, row in enumerate(rows) if any(str(cell or "").strip() for cell in row)), None)
        if first_non_empty_idx is None:
            return {
                "ok": False,
                "errors": [{"line": None, "message": "El archivo está vacío."}],
                "records": [],
                "summary": {"record_count": 0, "team_count": 0},
                "columns": self._free_agent_team_appeal_columns_payload(),
                "rankings": [],
            }

        teams = {str(team.get("code") or "").upper(): team for team in self.list_teams()}
        ranking_keys = [key for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS]
        header = rows[first_non_empty_idx]
        normalized_header = [self._free_agent_appeal_header_key(cell) for cell in header]
        required_keys = ["team_code", *[key for key, _label in self.FREE_AGENT_TEAM_APPEAL_COLUMNS]]
        has_header = all(key in normalized_header for key in required_keys)
        if has_header:
            header_map = {key: normalized_header.index(key) for key in required_keys}
            data_rows = rows[first_non_empty_idx + 1 :]
            line_offset = first_non_empty_idx + 2
        else:
            canonical_ranking_header = [self._free_agent_appeal_ranking_header_key(cell) for cell in header]
            has_ranking_header = all(key in canonical_ranking_header for key in ranking_keys)
            if has_ranking_header:
                column_map = {key: canonical_ranking_header.index(key) for key in ranking_keys}
                data_rows = rows[first_non_empty_idx + 1 :]
                line_offset = first_non_empty_idx + 2
                records_by_team: Dict[str, Dict[str, Any]] = {
                    team_code: {
                        "team_code": team_code,
                        "team_name": str(team.get("name") or team_code),
                    }
                    for team_code, team in teams.items()
                }
                seen_by_column: Dict[str, set[str]] = {key: set() for key in ranking_keys}
                for row_idx, row in enumerate(data_rows, start=line_offset):
                    if not any(str(cell or "").strip() for cell in row):
                        continue
                    rank = row_idx - line_offset + 1
                    for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                        team_raw = row[column_map[key]] if column_map[key] < len(row) else ""
                        team_code = normalize_team_code(team_raw)
                        if not team_code:
                            errors.append({"line": row_idx, "message": f"Equipo requerido en {key}."})
                            continue
                        if team_code not in teams:
                            errors.append({"line": row_idx, "message": f"Equipo inválido en {key}: {team_code}."})
                            continue
                        if team_code in seen_by_column[key]:
                            errors.append({"line": row_idx, "message": f"Equipo duplicado en {key}: {team_code}."})
                            continue
                        seen_by_column[key].add(team_code)
                        records_by_team[team_code][key] = float(rank)
                for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                    missing = sorted(set(teams.keys()) - seen_by_column[key])
                    for team_code in missing:
                        errors.append({"line": None, "message": f"Falta {team_code} en {group} · {sub_label}."})
                records = []
                for team_code in sorted(records_by_team.keys()):
                    record = records_by_team[team_code]
                    for key in ranking_keys:
                        record[key] = float(record.get(key) or 0.0)
                    records.append(record)
                return {
                    "ok": not errors,
                    "errors": errors,
                    "records": records,
                    "summary": {"record_count": len(records), "team_count": len(teams)},
                    "columns": self._free_agent_team_appeal_columns_payload(),
                    "rankings": self._free_agent_team_appeal_rankings_from_records(records),
                }

            second_header = rows[first_non_empty_idx + 1] if first_non_empty_idx + 1 < len(rows) else []
            group_values: List[str] = []
            last_group = ""
            max_len = max(len(header), len(second_header))
            for idx in range(max_len):
                group_raw = str(header[idx] if idx < len(header) else "").strip()
                if group_raw:
                    last_group = group_raw
                group_values.append(last_group)
            two_row_keys = [
                self._free_agent_appeal_ranking_header_key(group_values[idx], second_header[idx] if idx < len(second_header) else "")
                for idx in range(max_len)
            ]
            has_two_row_ranking_header = all(key in two_row_keys for key in ranking_keys)
            if has_two_row_ranking_header:
                column_map = {key: two_row_keys.index(key) for key in ranking_keys}
                data_rows = rows[first_non_empty_idx + 2 :]
                line_offset = first_non_empty_idx + 3
                records_by_team = {
                    team_code: {
                        "team_code": team_code,
                        "team_name": str(team.get("name") or team_code),
                    }
                    for team_code, team in teams.items()
                }
                seen_by_column = {key: set() for key in ranking_keys}
                rank = 0
                for row_idx, row in enumerate(data_rows, start=line_offset):
                    if not any(str(cell or "").strip() for cell in row):
                        continue
                    rank += 1
                    for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                        team_raw = row[column_map[key]] if column_map[key] < len(row) else ""
                        team_code = normalize_team_code(team_raw)
                        if not team_code:
                            errors.append({"line": row_idx, "message": f"Equipo requerido en {group} · {sub_label}."})
                            continue
                        if team_code not in teams:
                            errors.append({"line": row_idx, "message": f"Equipo inválido en {group} · {sub_label}: {team_code}."})
                            continue
                        if team_code in seen_by_column[key]:
                            errors.append({"line": row_idx, "message": f"Equipo duplicado en {group} · {sub_label}: {team_code}."})
                            continue
                        seen_by_column[key].add(team_code)
                        records_by_team[team_code][key] = float(rank)
                for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                    missing = sorted(set(teams.keys()) - seen_by_column[key])
                    for team_code in missing:
                        errors.append({"line": None, "message": f"Falta {team_code} en {group} · {sub_label}."})
                records = []
                for team_code in sorted(records_by_team.keys()):
                    record = records_by_team[team_code]
                    for key in ranking_keys:
                        record[key] = float(record.get(key) or 0.0)
                    records.append(record)
                return {
                    "ok": not errors,
                    "errors": errors,
                    "records": records,
                    "summary": {"record_count": len(records), "team_count": len(teams)},
                    "columns": self._free_agent_team_appeal_columns_payload(),
                    "rankings": self._free_agent_team_appeal_rankings_from_records(records),
                }

            header_map = {key: idx for idx, key in enumerate(required_keys)}
            data_rows = rows[first_non_empty_idx:]
            line_offset = first_non_empty_idx + 1

        records: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row_idx, row in enumerate(data_rows, start=line_offset):
            if not any(str(cell or "").strip() for cell in row):
                continue
            team_raw = row[header_map["team_code"]] if header_map["team_code"] < len(row) else ""
            team_code = normalize_team_code(team_raw)
            if not team_code:
                errors.append({"line": row_idx, "message": "Equipo requerido."})
                continue
            if team_code not in teams:
                errors.append({"line": row_idx, "message": f"Equipo inválido: {team_code}."})
                continue
            if team_code in seen:
                errors.append({"line": row_idx, "message": f"Equipo duplicado: {team_code}."})
                continue
            seen.add(team_code)
            record: Dict[str, Any] = {
                "team_code": team_code,
                "team_name": str(teams[team_code].get("name") or team_code),
            }
            for key, label in self.FREE_AGENT_TEAM_APPEAL_COLUMNS:
                raw_value = row[header_map[key]] if header_map[key] < len(row) else ""
                amount = parse_amount_like(raw_value)
                if amount is None:
                    errors.append({"line": row_idx, "message": f"Valor inválido para {team_code} · {label}."})
                    amount = 0.0
                record[key] = float(amount or 0.0)
            records.append(record)

        missing = sorted(set(teams.keys()) - seen)
        for team_code in missing:
            errors.append({"line": None, "message": f"Falta el equipo {team_code}."})

        return {
            "ok": not errors,
            "errors": errors,
            "records": records,
            "summary": {"record_count": len(records), "team_count": len(seen)},
            "columns": self._free_agent_team_appeal_columns_payload(),
            "rankings": self._free_agent_team_appeal_rankings_from_records(records),
        }

    def preview_free_agent_team_appeal_import(self, rows: List[List[str]]) -> Dict[str, Any]:
        return self._free_agent_team_appeal_records_from_rows(rows)

    def apply_free_agent_team_appeal_import(self, records_payload: Any) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        required_keys = [key for key, _label in self.FREE_AGENT_TEAM_APPEAL_COLUMNS]
        timestamp = now_iso()
        with self.connect() as conn:
            team_rows = conn.execute("SELECT code FROM teams").fetchall()
            valid_teams = {str(row["code"] or "").upper() for row in team_rows}
            imported = 0
            for raw_record in records_payload:
                if not isinstance(raw_record, dict):
                    raise ValueError("invalid_records")
                team_code = normalize_team_code(raw_record.get("team_code"))
                if not team_code or team_code not in valid_teams:
                    raise ValueError("invalid_records")
                values: List[float] = []
                for key in required_keys:
                    amount = parse_amount_like(raw_record.get(key))
                    if amount is None:
                        raise ValueError("invalid_records")
                    values.append(float(amount or 0.0))
                conn.execute(
                    """
                    INSERT INTO free_agent_team_appeal (
                        team_code, under_23_single, under_23_multi,
                        age_23_26_single, age_23_26_multi,
                        age_27_33_single, age_27_33_multi,
                        over_34_single, over_34_multi, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_code)
                    DO UPDATE SET
                        under_23_single = excluded.under_23_single,
                        under_23_multi = excluded.under_23_multi,
                        age_23_26_single = excluded.age_23_26_single,
                        age_23_26_multi = excluded.age_23_26_multi,
                        age_27_33_single = excluded.age_27_33_single,
                        age_27_33_multi = excluded.age_27_33_multi,
                        over_34_single = excluded.over_34_single,
                        over_34_multi = excluded.over_34_multi,
                        updated_at = excluded.updated_at
                    """,
                    (team_code, *values, timestamp),
                )
                imported += 1
            conn.commit()
        return {"record_count": imported}

    def list_free_agent_team_appeal(self) -> Dict[str, Any]:
        columns = self._free_agent_team_appeal_columns_payload()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.code AS team_code,
                    t.name AS team_name,
                    COALESCE(a.under_23_single, 0) AS under_23_single,
                    COALESCE(a.under_23_multi, 0) AS under_23_multi,
                    COALESCE(a.age_23_26_single, 0) AS age_23_26_single,
                    COALESCE(a.age_23_26_multi, 0) AS age_23_26_multi,
                    COALESCE(a.age_27_33_single, 0) AS age_27_33_single,
                    COALESCE(a.age_27_33_multi, 0) AS age_27_33_multi,
                    COALESCE(a.over_34_single, 0) AS over_34_single,
                    COALESCE(a.over_34_multi, 0) AS over_34_multi,
                    a.updated_at
                FROM teams t
                LEFT JOIN free_agent_team_appeal a ON a.team_code = t.code
                ORDER BY t.code
                """
            ).fetchall()
        records = [dict(row) for row in rows]
        return {
            "columns": columns,
            "rows": records,
            "rankings": self._free_agent_team_appeal_rankings_from_records(records),
        }

    def record_free_agent_interest(
        self,
        free_agent_id: Any,
        team_code: Any,
        payload: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        parsed_id = parse_int(free_agent_id)
        normalized_team = normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")

        economic_offer = re.sub(r"\s+", " ", str(payload.get("economic_offer") or "").strip())
        role_offer = re.sub(r"\s+", " ", str(payload.get("role_offer") or "").strip())
        comments = str(payload.get("comments") or "").strip()
        if not economic_offer and not role_offer and not comments:
            raise ValueError("empty_negotiation")
        economic_offer = economic_offer[:1000]
        role_offer = role_offer[:1000]
        comments = comments[:2000]

        timestamp = now_iso()
        with self.connect() as conn:
            free_agent = conn.execute("SELECT id FROM free_agents WHERE id = ?", (parsed_id,)).fetchone()
            if not free_agent:
                raise ValueError("free_agent_not_found")
            team = conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            conn.execute(
                """
                INSERT INTO free_agent_interests (
                    free_agent_id, team_code, submitted_by_user_id, submitted_by_email,
                    submitted_by_name, economic_offer, role_offer, comments, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(free_agent_id, team_code)
                DO UPDATE SET
                    submitted_by_user_id = excluded.submitted_by_user_id,
                    submitted_by_email = excluded.submitted_by_email,
                    submitted_by_name = excluded.submitted_by_name,
                    economic_offer = excluded.economic_offer,
                    role_offer = excluded.role_offer,
                    comments = excluded.comments,
                    updated_at = excluded.updated_at
                """,
                (
                    parsed_id,
                    normalized_team,
                    parse_int(session.get("user_id")),
                    str(session.get("email") or "").strip().lower() or None,
                    str(session.get("name") or "").strip() or None,
                    economic_offer,
                    role_offer,
                    comments,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                """
                SELECT *
                FROM free_agent_interests
                WHERE free_agent_id = ? AND team_code = ?
                """,
                (parsed_id, normalized_team),
            ).fetchone()
            conn.commit()
            if not row:
                raise RuntimeError("free_agent_interest_not_saved")
            return dict(row)

    def set_free_agent_favorite(
        self,
        free_agent_id: Any,
        team_code: Any,
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        parsed_id = parse_int(free_agent_id)
        normalized_team = normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        timestamp = now_iso()
        with self.connect() as conn:
            free_agent = conn.execute("SELECT id FROM free_agents WHERE id = ?", (parsed_id,)).fetchone()
            if not free_agent:
                raise ValueError("free_agent_not_found")
            team = conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            conn.execute(
                """
                INSERT INTO free_agent_favorites (
                    free_agent_id, team_code, user_id, user_email, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(free_agent_id, team_code)
                DO UPDATE SET
                    user_id = excluded.user_id,
                    user_email = excluded.user_email,
                    updated_at = excluded.updated_at
                """,
                (
                    parsed_id,
                    normalized_team,
                    parse_int(session.get("user_id")),
                    str(session.get("email") or "").strip().lower() or None,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                """
                SELECT *
                FROM free_agent_favorites
                WHERE free_agent_id = ? AND team_code = ?
                """,
                (parsed_id, normalized_team),
            ).fetchone()
            conn.commit()
            if not row:
                raise RuntimeError("free_agent_favorite_not_saved")
            return dict(row)

    def delete_free_agent_favorite(self, free_agent_id: Any, team_code: Any) -> bool:
        parsed_id = parse_int(free_agent_id)
        normalized_team = normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM free_agent_favorites WHERE free_agent_id = ? AND team_code = ?",
                (parsed_id, normalized_team),
            )
            conn.commit()
            return cur.rowcount > 0

    def _agent_name_for_free_agent_ruleout(
        self,
        free_agent: sqlite3.Row,
        session: Dict[str, Any],
    ) -> str:
        role = str(session.get("role") or "").strip().lower()
        free_agent_agent = re.sub(r"\s+", " ", str(free_agent["agent"] or "").strip())
        session_agent = re.sub(r"\s+", " ", str(session.get("agent_name") or "").strip())
        if role == "admin":
            if not free_agent_agent:
                raise ValueError("free_agent_agent_required")
            return free_agent_agent
        if role == "co_admin":
            if not free_agent_agent or not session_agent:
                raise PermissionError("agent_required")
            if free_agent_agent.casefold() != session_agent.casefold():
                raise PermissionError("agent_client_required")
            return free_agent_agent
        raise PermissionError("admin_or_coadmin_required")

    def _free_agent_team_ruleouts_conn(
        self,
        conn: sqlite3.Connection,
        free_agent_id: int,
        agent_name: str,
    ) -> List[Dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT
                r.*,
                t.name AS team_name
            FROM free_agent_team_ruleouts r
            LEFT JOIN teams t ON t.code = r.team_code
            WHERE r.free_agent_id = ? AND lower(trim(r.agent_name)) = lower(trim(?))
            ORDER BY r.team_code
            """,
            (free_agent_id, agent_name),
        )
        return [row_to_dict(cur, row) for row in cur.fetchall()]

    def set_free_agent_team_ruleout(
        self,
        free_agent_id: Any,
        team_code: Any,
        session: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        parsed_id = parse_int(free_agent_id)
        normalized_team = normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        timestamp = now_iso()
        with self.connect() as conn:
            free_agent = conn.execute(
                "SELECT id, agent FROM free_agents WHERE id = ?",
                (parsed_id,),
            ).fetchone()
            if not free_agent:
                raise ValueError("free_agent_not_found")
            agent_name = self._agent_name_for_free_agent_ruleout(free_agent, session)
            team = conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            conn.execute(
                """
                INSERT INTO free_agent_team_ruleouts (
                    free_agent_id, agent_name, team_code, created_by_user_id,
                    created_by_email, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(free_agent_id, agent_name, team_code)
                DO UPDATE SET
                    created_by_user_id = excluded.created_by_user_id,
                    created_by_email = excluded.created_by_email,
                    updated_at = excluded.updated_at
                """,
                (
                    parsed_id,
                    agent_name,
                    normalized_team,
                    parse_int(session.get("user_id")),
                    str(session.get("email") or "").strip().lower() or None,
                    timestamp,
                    timestamp,
                ),
            )
            rows = self._free_agent_team_ruleouts_conn(conn, parsed_id, agent_name)
            conn.commit()
            return rows

    def delete_free_agent_team_ruleout(
        self,
        free_agent_id: Any,
        team_code: Any,
        session: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        parsed_id = parse_int(free_agent_id)
        normalized_team = normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.connect() as conn:
            free_agent = conn.execute(
                "SELECT id, agent FROM free_agents WHERE id = ?",
                (parsed_id,),
            ).fetchone()
            if not free_agent:
                raise ValueError("free_agent_not_found")
            agent_name = self._agent_name_for_free_agent_ruleout(free_agent, session)
            conn.execute(
                """
                DELETE FROM free_agent_team_ruleouts
                WHERE free_agent_id = ? AND lower(trim(agent_name)) = lower(trim(?)) AND team_code = ?
                """,
                (parsed_id, agent_name, normalized_team),
            )
            rows = self._free_agent_team_ruleouts_conn(conn, parsed_id, agent_name)
            conn.commit()
            return rows

    def free_agent_favorite_ids_for_team(self, team_code: Any) -> set[int]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            return set()
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT free_agent_id FROM free_agent_favorites WHERE team_code = ?",
                (normalized_team,),
            )
            return {int(row["free_agent_id"]) for row in cur.fetchall() if row["free_agent_id"] is not None}

    @staticmethod
    def _gm_spending_limit_payload(row: Optional[sqlite3.Row], team: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        amount = parse_int(row["amount"]) if row and "amount" in row.keys() else 0
        raw_updated_at = row["updated_at"] if row and "updated_at" in row.keys() else ""
        updated_at = str(raw_updated_at or "").strip()
        raw_updated_by_email = row["updated_by_email"] if row and "updated_by_email" in row.keys() else ""
        return {
            "team_code": normalize_team_code(row["team_code"] if row and "team_code" in row.keys() else (team or {}).get("code")),
            "team_name": str((team or {}).get("name") or (row["team_name"] if row and "team_name" in row.keys() else "") or "").strip(),
            "amount": max(0, amount or 0),
            "amount_millions": round(max(0, amount or 0) / 1_000_000, 3),
            "updated_at": updated_at,
            "updated_by_email": str(raw_updated_by_email or "").strip(),
            "has_value": bool(updated_at),
        }

    def get_gm_free_agent_spending_limit(self, team_code: Any) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.connect() as conn:
            team_cur = conn.execute("SELECT code, name FROM teams WHERE code = ?", (normalized_team,))
            team_row = team_cur.fetchone()
            if not team_row:
                raise ValueError("team_not_found")
            team = row_to_dict(team_cur, team_row)
            cur = conn.execute(
                """
                SELECT l.*, t.name AS team_name
                FROM gm_free_agent_spending_limits l
                JOIN teams t ON t.code = l.team_code
                WHERE l.team_code = ?
                """,
                (normalized_team,),
            )
            row = cur.fetchone()
            return self._gm_spending_limit_payload(row, team)

    def set_gm_free_agent_spending_limit(
        self,
        team_code: Any,
        amount_millions: Any,
        session: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        parsed_amount = parse_float(amount_millions)
        if parsed_amount is None:
            raise ValueError("invalid_amount")
        if parsed_amount < 0 or parsed_amount > 100:
            raise ValueError("amount_out_of_range")
        session = session or {}
        now = now_iso()
        full_amount = int(round(parsed_amount * 1_000_000))
        with self.connect() as conn:
            team = conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            conn.execute(
                """
                INSERT INTO gm_free_agent_spending_limits
                    (team_code, amount, updated_by_user_id, updated_by_email, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(team_code) DO UPDATE SET
                    amount = excluded.amount,
                    updated_by_user_id = excluded.updated_by_user_id,
                    updated_by_email = excluded.updated_by_email,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_team,
                    full_amount,
                    parse_int(session.get("user_id")),
                    str(session.get("email") or "").strip().lower(),
                    now,
                ),
            )
            conn.commit()
        return self.get_gm_free_agent_spending_limit(normalized_team)

    def list_gm_free_agent_spending_limits(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    t.code AS team_code,
                    t.name AS team_name,
                    l.amount,
                    l.updated_at,
                    l.updated_by_email
                FROM teams t
                LEFT JOIN gm_free_agent_spending_limits l ON l.team_code = t.code
                ORDER BY t.code
                """
            )
            return [self._gm_spending_limit_payload(row) for row in cur.fetchall()]

    def _minimum_target_payload(
        self,
        status_row: Optional[sqlite3.Row],
        target_rows: Iterable[sqlite3.Row],
        user: Optional[Dict[str, Any]] = None,
        team_code: Any = None,
    ) -> Dict[str, Any]:
        status = dict(status_row) if status_row is not None else {}
        user = user or {}
        normalized_team = normalize_team_code(status.get("team_code") or team_code)
        targets = []
        for raw_row in target_rows:
            row = dict(raw_row)
            player_name = str(row.get("player_name") or row.get("free_agent_name") or "").strip()
            targets.append(
                {
                    "rank": parse_int(row.get("rank")),
                    "free_agent_id": parse_int(row.get("free_agent_id")),
                    "profile_id": parse_int(row.get("profile_id")),
                    "player_name": player_name,
                    "position": str(row.get("position") or "").strip(),
                    "rating": str(row.get("rating") or "").strip(),
                    "free_agent_type": str(row.get("free_agent_type") or "").strip(),
                    "rights_team_code": normalize_team_code(row.get("rights_team_code")),
                    "role": str(row.get("role") or "").strip(),
                }
            )
        return {
            "user_id": parse_int(user.get("id") or status.get("user_id")),
            "user_name": str(user.get("display_name") or user.get("name") or "").strip(),
            "email": str(user.get("email") or "").strip(),
            "team_code": normalized_team,
            "answered": bool(parse_int(status.get("answered"))),
            "omitted": bool(parse_int(status.get("omitted"))),
            "updated_at": str(status.get("updated_at") or "").strip(),
            "targets": targets,
        }

    def get_gm_minimum_targets(self, user_id: Any, team_code: Any = None) -> Dict[str, Any]:
        parsed_user_id = parse_int(user_id)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        normalized_team = normalize_team_code(team_code)
        with self.connect() as conn:
            user_cur = conn.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    GROUP_CONCAT(t.code, ',') AS team_codes
                FROM users u
                LEFT JOIN user_team_assignments ut ON ut.user_id = u.id
                LEFT JOIN teams t ON t.id = ut.team_id
                WHERE u.id = ?
                GROUP BY u.id
                """,
                (parsed_user_id,),
            )
            user_row = user_cur.fetchone()
            if not user_row:
                raise ValueError("user_not_found")
            user = row_to_dict(user_cur, user_row)
            if not normalized_team:
                team_codes = [normalize_team_code(code) for code in str(user.get("team_codes") or "").split(",") if normalize_team_code(code)]
                if len(team_codes) == 1:
                    normalized_team = team_codes[0]
            status_row = conn.execute(
                "SELECT * FROM gm_minimum_target_status WHERE user_id = ?",
                (parsed_user_id,),
            ).fetchone()
            target_cur = conn.execute(
                """
                SELECT
                    mt.*,
                    f.name AS free_agent_name,
                    f.position,
                    f.rating,
                    f.free_agent_type,
                    f.rights_team_code
                FROM gm_minimum_targets mt
                JOIN free_agents f ON f.id = mt.free_agent_id
                WHERE mt.user_id = ?
                ORDER BY mt.rank
                """,
                (parsed_user_id,),
            )
            return self._minimum_target_payload(status_row, target_cur.fetchall(), user, normalized_team)

    def set_gm_minimum_targets(
        self,
        user_id: Any,
        team_code: Any,
        targets: Any,
    ) -> Dict[str, Any]:
        parsed_user_id = parse_int(user_id)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        normalized_team = normalize_team_code(team_code)
        if targets is None:
            targets = []
        if not isinstance(targets, list):
            raise ValueError("invalid_targets")
        if len(targets) > 10:
            raise ValueError("too_many_targets")

        cleaned: List[Dict[str, Any]] = []
        seen_agents = set()
        seen_ranks = set()
        valid_roles = {
            "Titular",
            "Sexto hombre",
            "Minutos de rotación (10-20)",
            "Minutos de rotación (0-9)",
            "Fuera de la rotación",
        }
        for index, raw in enumerate(targets, start=1):
            if not isinstance(raw, dict):
                raise ValueError("invalid_target")
            rank = parse_int(raw.get("rank"))
            if rank is None:
                rank = index
            free_agent_id = parse_int(raw.get("free_agent_id"))
            role = str(raw.get("role") or "").strip()
            if role:
                matched_role = next((option for option in valid_roles if option.casefold() == role.casefold()), None)
                if not matched_role:
                    raise ValueError("invalid_target_role")
                role = matched_role
            elif free_agent_id is not None and free_agent_id > 0:
                raise ValueError("target_role_required")
            if rank is None or rank < 1 or rank > 10:
                raise ValueError("invalid_rank")
            if free_agent_id is None or free_agent_id <= 0:
                continue
            if rank in seen_ranks:
                raise ValueError("duplicate_rank")
            if free_agent_id in seen_agents:
                raise ValueError("duplicate_player")
            seen_ranks.add(rank)
            seen_agents.add(free_agent_id)
            cleaned.append({"rank": rank, "free_agent_id": free_agent_id, "role": role})

        now = now_iso()
        with self.connect() as conn:
            if normalized_team:
                team = conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone()
                if not team:
                    raise ValueError("team_not_found")
            resolved: List[Dict[str, Any]] = []
            for target in cleaned:
                cur = conn.execute(
                    """
                    SELECT id, profile_id, name
                    FROM free_agents
                    WHERE id = ?
                    """,
                    (target["free_agent_id"],),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("free_agent_not_found")
                resolved.append(
                    {
                        "rank": target["rank"],
                        "free_agent_id": int(row["id"]),
                        "profile_id": parse_int(row["profile_id"]),
                        "player_name": str(row["name"] or "").strip(),
                        "role": target.get("role") or "",
                    }
                )
            conn.execute("DELETE FROM gm_minimum_targets WHERE user_id = ?", (parsed_user_id,))
            for target in resolved:
                conn.execute(
                    """
                    INSERT INTO gm_minimum_targets
                        (user_id, rank, free_agent_id, profile_id, player_name, role, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parsed_user_id,
                        target["rank"],
                        target["free_agent_id"],
                        target["profile_id"],
                        target["player_name"],
                        target["role"],
                        now,
                        now,
                    ),
                )
            conn.execute(
                """
                INSERT INTO gm_minimum_target_status
                    (user_id, team_code, answered, omitted, created_at, updated_at)
                VALUES (?, ?, 1, 0, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    team_code = excluded.team_code,
                    answered = 1,
                    omitted = 0,
                    updated_at = excluded.updated_at
                """,
                (parsed_user_id, normalized_team, now, now),
            )
            conn.commit()
        return self.get_gm_minimum_targets(parsed_user_id, normalized_team)

    def omit_gm_minimum_targets(self, user_id: Any, team_code: Any = None) -> Dict[str, Any]:
        parsed_user_id = parse_int(user_id)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        normalized_team = normalize_team_code(team_code)
        now = now_iso()
        with self.connect() as conn:
            if normalized_team:
                team = conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone()
                if not team:
                    raise ValueError("team_not_found")
            conn.execute("DELETE FROM gm_minimum_targets WHERE user_id = ?", (parsed_user_id,))
            conn.execute(
                """
                INSERT INTO gm_minimum_target_status
                    (user_id, team_code, answered, omitted, created_at, updated_at)
                VALUES (?, ?, 1, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    team_code = excluded.team_code,
                    answered = 1,
                    omitted = 1,
                    updated_at = excluded.updated_at
                """,
                (parsed_user_id, normalized_team, now, now),
            )
            conn.commit()
        return self.get_gm_minimum_targets(parsed_user_id, normalized_team)

    def remove_admin_gm_minimum_target(self, user_id: Any, rank: Any) -> Dict[str, Any]:
        parsed_user_id = parse_int(user_id)
        parsed_rank = parse_int(rank)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        if parsed_rank is None or parsed_rank < 1 or parsed_rank > 10:
            raise ValueError("invalid_rank")
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM gm_minimum_targets WHERE user_id = ? AND rank = ?",
                (parsed_user_id, parsed_rank),
            ).fetchone()
            if not existing:
                return {"removed": False, "user_id": parsed_user_id, "rank": parsed_rank}
            conn.execute(
                "DELETE FROM gm_minimum_targets WHERE user_id = ? AND rank = ?",
                (parsed_user_id, parsed_rank),
            )
            conn.execute(
                "UPDATE gm_minimum_target_status SET updated_at = ? WHERE user_id = ?",
                (now_iso(), parsed_user_id),
            )
            conn.commit()
        return {"removed": True, "user_id": parsed_user_id, "rank": parsed_rank}

    def list_gm_minimum_target_handicaps(self) -> Dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT team_code, handicap FROM gm_minimum_target_handicaps ORDER BY team_code"
            ).fetchall()
        handicaps: Dict[str, int] = {}
        for row in rows:
            team_code = normalize_team_code(row["team_code"])
            handicap = parse_int(row["handicap"])
            if team_code and handicap is not None and -9 <= handicap <= 0:
                handicaps[team_code] = handicap
        return handicaps

    def set_gm_minimum_target_handicap(self, team_code: Any, handicap: Any) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        parsed_handicap = parse_int(handicap)
        if not normalized_team:
            raise ValueError("team_required")
        if parsed_handicap is None:
            parsed_handicap = 0
        if parsed_handicap < -9 or parsed_handicap > 0:
            raise ValueError("invalid_handicap")
        now = now_iso()
        with self.connect() as conn:
            team = conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            if parsed_handicap == 0:
                conn.execute("DELETE FROM gm_minimum_target_handicaps WHERE team_code = ?", (normalized_team,))
            else:
                conn.execute(
                    """
                    INSERT INTO gm_minimum_target_handicaps (team_code, handicap, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(team_code) DO UPDATE SET
                        handicap = excluded.handicap,
                        updated_at = excluded.updated_at
                    """,
                    (normalized_team, parsed_handicap, now),
                )
            conn.commit()
        return {"team_code": normalized_team, "handicap": parsed_handicap}

    def list_admin_gm_minimum_targets(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    COALESCE(u.is_co_admin, 0) AS is_co_admin,
                    GROUP_CONCAT(t.code, ',') AS team_codes,
                    s.answered,
                    s.omitted,
                    s.updated_at
                FROM users u
                LEFT JOIN user_team_assignments ut ON ut.user_id = u.id
                LEFT JOIN teams t ON t.id = ut.team_id
                LEFT JOIN gm_minimum_target_status s ON s.user_id = u.id
                WHERE COALESCE(u.is_co_admin, 0) = 1 OR ut.user_id IS NOT NULL OR s.user_id IS NOT NULL
                GROUP BY u.id
                ORDER BY COALESCE(t.code, ''), COALESCE(u.display_name, u.email) COLLATE NOCASE
                """
            )
            users = [row_to_dict(cur, row) for row in cur.fetchall()]
            if not users:
                return []
            user_ids = [int(user["id"]) for user in users]
            placeholders = ",".join("?" for _ in user_ids)
            target_cur = conn.execute(
                f"""
                SELECT
                    mt.*,
                    f.position,
                    f.rating,
                    f.free_agent_type,
                    f.rights_team_code
                FROM gm_minimum_targets mt
                JOIN free_agents f ON f.id = mt.free_agent_id
                WHERE mt.user_id IN ({placeholders})
                ORDER BY mt.user_id, mt.rank
                """,
                tuple(user_ids),
            )
            grouped_targets: Dict[int, List[sqlite3.Row]] = {}
            for row in target_cur.fetchall():
                grouped_targets.setdefault(int(row["user_id"]), []).append(row)
            lists = []
            for user in users:
                team_codes = [normalize_team_code(code) for code in str(user.get("team_codes") or "").split(",") if normalize_team_code(code)]
                lists.append(
                    {
                        "user_id": parse_int(user.get("id")),
                        "user_name": str(user.get("display_name") or user.get("email") or "").strip(),
                        "email": str(user.get("email") or "").strip(),
                        "role": "co_admin" if parse_bool(user.get("is_co_admin")) else ("gm" if team_codes else "guest"),
                        "team_codes": team_codes,
                        "answered": bool(parse_int(user.get("answered"))),
                        "omitted": bool(parse_int(user.get("omitted"))),
                        "updated_at": str(user.get("updated_at") or "").strip(),
                        "targets": self._minimum_target_payload(
                            None,
                            grouped_targets.get(int(user["id"]), []),
                            {"id": user.get("id"), "email": user.get("email"), "display_name": user.get("display_name")},
                        )["targets"],
                    }
                )
            return lists

    @staticmethod
    def _minimum_target_age_from_birth_date(raw_value: Any) -> int:
        text = str(raw_value or "").strip()
        if not text:
            return 20
        parsed: Optional[date] = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            return 20
        today = date.today()
        age = today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day))
        if age < 0 or age > 80:
            return 20
        return age

    @staticmethod
    def _minimum_target_appeal_key_for_age(age: int) -> str:
        if age < 23:
            return "under_23_single"
        if age <= 26:
            return "age_23_26_single"
        if age <= 33:
            return "age_27_33_single"
        return "over_34_single"

    @staticmethod
    def _minimum_target_role_points(role: Any) -> int:
        normalized = normalize_import_text(role).casefold()
        normalized = re.sub(r"\s+", " ", normalized).strip()
        mapping = {
            "titular": 20,
            "sexto hombre": 10,
            "minutos de rotacion 10 20": 4,
            "rotacion 10 20 minutos": 4,
            "rotacion 10 20": 4,
            "minutos de rotacion 0 9": 2,
            "minutos de rotacion 0 10": 2,
            "rol limitado 0 10 minutos": 2,
            "rol limitado 0 9": 2,
            "rotacion 0 9": 2,
            "rotacion 0 10": 2,
            "fuera de la rotacion": 0,
        }
        return mapping.get(normalized, 0)

    @staticmethod
    def _minimum_target_birds_bonus(age: int, team_code: Any, rights_team_code: Any) -> int:
        normalized_team = normalize_team_code(team_code)
        normalized_rights_team = normalize_team_code(rights_team_code)
        if not normalized_team or normalized_team != normalized_rights_team:
            return 0
        if age < 23:
            return 10
        if age <= 28:
            return 6
        if age <= 33:
            return 3
        return 1

    def list_admin_gm_minimum_target_order(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            teams = {
                str(row["code"] or "").upper(): str(row["name"] or row["code"] or "").strip()
                for row in conn.execute("SELECT code, name FROM teams").fetchall()
            }
            user_rows = conn.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    GROUP_CONCAT(t.code, ',') AS team_codes
                FROM users u
                LEFT JOIN user_team_assignments ut ON ut.user_id = u.id
                LEFT JOIN teams t ON t.id = ut.team_id
                GROUP BY u.id
                """
            ).fetchall()
            users_by_id: Dict[int, Dict[str, Any]] = {}
            for row in user_rows:
                user_id = int(row["id"])
                team_codes = [
                    normalize_team_code(code)
                    for code in str(row["team_codes"] or "").split(",")
                    if normalize_team_code(code)
                ]
                users_by_id[user_id] = {
                    "user_id": user_id,
                    "user_name": str(row["display_name"] or row["email"] or "").strip(),
                    "email": str(row["email"] or "").strip(),
                    "team_codes": team_codes,
                    "team_code": team_codes[0] if team_codes else "",
                }
            appeal_rows = conn.execute("SELECT * FROM free_agent_team_appeal").fetchall()
            appeal_by_team = {str(row["team_code"] or "").upper(): dict(row) for row in appeal_rows}
            handicap_rows = conn.execute("SELECT team_code, handicap FROM gm_minimum_target_handicaps").fetchall()
            handicaps = {
                normalize_team_code(row["team_code"]): parse_int(row["handicap"]) or 0
                for row in handicap_rows
                if normalize_team_code(row["team_code"])
            }
            target_rows = conn.execute(
                """
                SELECT
                    mt.user_id,
                    mt.rank,
                    mt.free_agent_id,
                    mt.profile_id,
                    mt.player_name,
                    mt.role,
                    f.position,
                    f.rating,
                    f.rights_team_code,
                    pp.date_of_birth
                FROM gm_minimum_targets mt
                JOIN free_agents f ON f.id = mt.free_agent_id
                LEFT JOIN player_profiles pp ON pp.id = COALESCE(mt.profile_id, f.profile_id)
                ORDER BY mt.user_id, mt.rank
                """
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        effective_ranks_by_user: Dict[int, int] = {}
        for row in target_rows:
            row_user_id = int(row["user_id"])
            user = users_by_id.get(row_user_id)
            if not user:
                continue
            team_code = normalize_team_code(user.get("team_code"))
            original_rank = parse_int(row["rank"]) or 0
            effective_rank = effective_ranks_by_user.get(row_user_id, 0) + 1
            effective_ranks_by_user[row_user_id] = effective_rank
            priority_points = max(0, 11 - effective_rank) if 1 <= effective_rank <= 10 else 0
            age = self._minimum_target_age_from_birth_date(row["date_of_birth"])
            appeal_key = self._minimum_target_appeal_key_for_age(age)
            appeal_rank = parse_float((appeal_by_team.get(team_code) or {}).get(appeal_key))
            appeal_points = max(0, 31 - int(appeal_rank)) if appeal_rank and appeal_rank > 0 else 0
            role_points = self._minimum_target_role_points(row["role"])
            rights_team_code = normalize_team_code(row["rights_team_code"])
            birds_bonus = self._minimum_target_birds_bonus(age, team_code, rights_team_code)
            handicap = handicaps.get(team_code, 0)
            total = priority_points + appeal_points + role_points + birds_bonus + handicap
            scored.append(
                {
                    "total": total,
                    "priority_points": priority_points,
                    "appeal_points": appeal_points,
                    "role_points": role_points,
                    "birds_bonus": birds_bonus,
                    "handicap": handicap,
                    "appeal_rank": int(appeal_rank) if appeal_rank and appeal_rank > 0 else None,
                    "appeal_key": appeal_key,
                    "age": age,
                    "target_rank": effective_rank,
                    "original_target_rank": original_rank,
                    "team_code": team_code,
                    "team_name": teams.get(team_code, team_code),
                    "user_id": user.get("user_id"),
                    "user_name": user.get("user_name") or user.get("email") or "",
                    "player_name": str(row["player_name"] or "").strip(),
                    "free_agent_id": parse_int(row["free_agent_id"]),
                    "profile_id": parse_int(row["profile_id"]),
                    "position": str(row["position"] or "").strip(),
                    "rating": str(row["rating"] or "").strip(),
                    "rights_team_code": rights_team_code,
                    "role": str(row["role"] or "").strip(),
                }
            )
        scored.sort(
            key=lambda item: (
                -int(item.get("total") or 0),
                -int(item.get("priority_points") or 0),
                -int(item.get("appeal_points") or 0),
                -int(item.get("role_points") or 0),
                -int(item.get("birds_bonus") or 0),
                str(item.get("player_name") or ""),
                str(item.get("team_code") or ""),
            )
        )
        return scored

    @staticmethod
    def _depth_chart_player_payload(player: Dict[str, Any]) -> Dict[str, Any]:
        return DepthChartRepository.player_payload(player)

    def _team_depth_chart_players(self, conn: sqlite3.Connection, team_id: int) -> List[Dict[str, Any]]:
        return self._depth_chart_repository.team_players(conn, team_id)

    def _team_depth_chart_payload(self, conn: sqlite3.Connection, team_id: int) -> Dict[str, Any]:
        return self._depth_chart_repository.payload(conn, team_id)

    def set_team_depth_chart(self, team_code: Any, entries: Any) -> Dict[str, Any]:
        return self._depth_chart_repository.set(team_code, entries)

    def list_gm_office(self, team_code: Any) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.connect() as conn:
            team = conn.execute("SELECT id, code, name FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            offer_cur = conn.execute(
                """
                SELECT
                    r.*,
                    f.name AS player_name,
                    f.profile_id,
                    f.position,
                    f.rating,
                    f.free_agent_type,
                    f.rights_team_code,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_free_agent_offer_requests r
                LEFT JOIN free_agents f ON f.id = r.free_agent_id
                JOIN teams t ON t.id = r.team_id
                WHERE t.code = ? AND r.status <> 'cancelled'
                ORDER BY
                    CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                    r.created_at DESC,
                    r.id DESC
                """,
                (normalized_team,),
            )
            offers = [self._gm_free_agent_offer_request_from_row(offer_cur, row) for row in offer_cur.fetchall()]
            favorite_cur = conn.execute(
                """
                SELECT
                    fav.id AS favorite_id,
                    fav.created_at AS favorite_created_at,
                    f.*,
                    pp.name AS profile_name,
                    pp.experience_years AS profile_experience_years
                FROM free_agent_favorites fav
                JOIN free_agents f ON f.id = fav.free_agent_id
                LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                WHERE fav.team_code = ?
                ORDER BY COALESCE(pp.name, f.name) COLLATE NOCASE, f.id
                """,
                (normalized_team,),
            )
            favorites = [
                self._merge_player_profile(row_to_dict(favorite_cur, row))
                for row in favorite_cur.fetchall()
            ]
            favorites = self._attach_player_salary_history_conn(conn, favorites)
            spending_limit = conn.execute(
                """
                SELECT l.*, t.name AS team_name
                FROM gm_free_agent_spending_limits l
                JOIN teams t ON t.code = l.team_code
                WHERE l.team_code = ?
                """,
                (normalized_team,),
            ).fetchone()
            depth_chart = self._team_depth_chart_payload(conn, int(team["id"]))
            depth_chart_players = self._team_depth_chart_players(conn, int(team["id"]))
            # Filled by the route when a current user is known.
            minimum_targets = None
        return {
            "team_code": normalized_team,
            "team_name": str(team["name"] or normalized_team),
            "offers": offers,
            "favorites": favorites,
            "free_agent_spending_limit": self._gm_spending_limit_payload(
                spending_limit,
                {"code": normalized_team, "name": str(team["name"] or normalized_team)},
            ),
            "depth_chart": depth_chart,
            "depth_chart_players": depth_chart_players,
            "minimum_targets": minimum_targets,
        }

    def cancel_gm_free_agent_offer_request(
        self,
        request_id: Any,
        team_code: Any,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(request_id)
        normalized_team = normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_request_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.transaction("IMMEDIATE") as conn:
            cur = conn.execute(
                """
                SELECT
                    r.*,
                    f.name AS player_name,
                    f.profile_id,
                    f.position,
                    f.rating,
                    f.free_agent_type,
                    f.rights_team_code,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_free_agent_offer_requests r
                LEFT JOIN free_agents f ON f.id = r.free_agent_id
                JOIN teams t ON t.id = r.team_id
                WHERE r.id = ? AND t.code = ?
                """,
                (parsed_id, normalized_team),
            )
            row = cur.fetchone()
            if not row:
                return None
            item = self._gm_free_agent_offer_request_from_row(cur, row)
            if str(item.get("status") or "").strip().lower() != "pending":
                raise ValueError("offer_not_pending")
            try:
                self._transition_workflow_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    parsed_id,
                    "cancelled",
                    actor=actor,
                    reason="offer_cancelled_by_team",
                    updates={"updated_at": now_iso(), "decided_at": now_iso()},
                    command_id=f"gm-free-agent-offer:{parsed_id}:cancelled",
                )
            except WorkflowTransitionError as err:
                raise ValueError("offer_not_pending")
            item["status"] = "cancelled"
            return item

    def list_cartera_clients_for_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        role = str(session.get("role") or "").strip().lower()
        email = str(session.get("email") or "").strip().lower()
        access = self.user_access_for_email(email) if email else {}
        agent_name = re.sub(
            r"\s+",
            " ",
            str(access.get("agent_name") or session.get("agent_name") or "").strip(),
        )

        if role == "co_admin" and not agent_name:
            return {
                "agent_name": "",
                "clients": [],
                "missing_agent": True,
                "gm_spending_limits": self.list_gm_free_agent_spending_limits(),
            }

        where = "COALESCE(f.agent, '') != ''"
        params: List[Any] = []
        if role != "admin" or agent_name:
            where = "lower(trim(COALESCE(f.agent, ''))) = lower(trim(?))"
            params.append(agent_name)

        with self.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT
                    f.id,
                    f.profile_id,
                    f.name,
                    f.position,
                    f.rating,
                    f.free_agent_type,
                    f.rights_team_code,
                    f.agent,
                    COUNT(DISTINCT i.id) AS interest_count,
                    COUNT(DISTINCT fav.team_code) AS favorite_count,
                    COUNT(DISTINCT offer.team_id) AS offer_count
                FROM free_agents f
                LEFT JOIN free_agent_interests i ON i.free_agent_id = f.id
                LEFT JOIN free_agent_favorites fav ON fav.free_agent_id = f.id
                LEFT JOIN gm_free_agent_offer_requests offer
                    ON offer.free_agent_id = f.id
                   AND offer.status IN ('pending', 'approved')
                WHERE {where}
                GROUP BY f.id
                ORDER BY COUNT(DISTINCT i.id) DESC, COUNT(DISTINCT fav.team_code) DESC, COUNT(DISTINCT offer.team_id) DESC, lower(f.name)
                """,
                params,
            )
            clients = [row_to_dict(cur, row) for row in cur.fetchall()]
            client_ids = [int(item["id"]) for item in clients if parse_int(item.get("id")) is not None]
            interests_by_client: Dict[int, List[Dict[str, Any]]] = {client_id: [] for client_id in client_ids}
            favorites_by_client: Dict[int, List[Dict[str, Any]]] = {client_id: [] for client_id in client_ids}
            offers_by_client: Dict[int, List[Dict[str, Any]]] = {client_id: [] for client_id in client_ids}
            ruleouts_by_client: Dict[int, List[Dict[str, Any]]] = {client_id: [] for client_id in client_ids}
            if client_ids:
                placeholders = ",".join("?" for _ in client_ids)
                interest_cur = conn.execute(
                    f"""
                    SELECT
                        i.*,
                        t.name AS team_name
                    FROM free_agent_interests i
                    LEFT JOIN teams t ON t.code = i.team_code
                    WHERE i.free_agent_id IN ({placeholders})
                    ORDER BY i.updated_at DESC, i.team_code
                    """,
                    client_ids,
                )
                for row in interest_cur.fetchall():
                    item = row_to_dict(interest_cur, row)
                    free_agent_key = parse_int(item.get("free_agent_id"))
                    if free_agent_key is None:
                        continue
                    interests_by_client.setdefault(free_agent_key, []).append(item)
                favorite_cur = conn.execute(
                    f"""
                    SELECT
                        fav.*,
                        t.name AS team_name
                    FROM free_agent_favorites fav
                    LEFT JOIN teams t ON t.code = fav.team_code
                    WHERE fav.free_agent_id IN ({placeholders})
                    ORDER BY fav.updated_at DESC, fav.team_code
                    """,
                    client_ids,
                )
                for row in favorite_cur.fetchall():
                    item = row_to_dict(favorite_cur, row)
                    free_agent_key = parse_int(item.get("free_agent_id"))
                    if free_agent_key is None:
                        continue
                    favorites_by_client.setdefault(free_agent_key, []).append(item)
                offer_cur = conn.execute(
                    f"""
                    SELECT
                        r.free_agent_id,
                        r.status,
                        r.created_at,
                        r.updated_at,
                        t.code AS team_code,
                        t.name AS team_name
                    FROM gm_free_agent_offer_requests r
                    JOIN teams t ON t.id = r.team_id
                    WHERE r.free_agent_id IN ({placeholders})
                      AND r.status IN ('pending', 'approved')
                    ORDER BY CASE r.status WHEN 'approved' THEN 0 ELSE 1 END, r.updated_at DESC, t.code
                    """,
                    client_ids,
                )
                seen_offer_teams: set[tuple[int, str]] = set()
                for row in offer_cur.fetchall():
                    item = row_to_dict(offer_cur, row)
                    free_agent_key = parse_int(item.get("free_agent_id"))
                    team_code = normalize_team_code(item.get("team_code"))
                    if free_agent_key is None or not team_code:
                        continue
                    seen_key = (free_agent_key, team_code)
                    if seen_key in seen_offer_teams:
                        continue
                    seen_offer_teams.add(seen_key)
                    offers_by_client.setdefault(free_agent_key, []).append(item)
                ruleout_cur = conn.execute(
                    f"""
                    SELECT
                        r.*,
                        t.name AS team_name
                    FROM free_agent_team_ruleouts r
                    LEFT JOIN teams t ON t.code = r.team_code
                    WHERE r.free_agent_id IN ({placeholders})
                    ORDER BY r.updated_at DESC, r.team_code
                    """,
                    client_ids,
                )
                for row in ruleout_cur.fetchall():
                    item = row_to_dict(ruleout_cur, row)
                    free_agent_key = parse_int(item.get("free_agent_id"))
                    if free_agent_key is None:
                        continue
                    ruleouts_by_client.setdefault(free_agent_key, []).append(item)

        normalized_clients: List[Dict[str, Any]] = []
        for client in clients:
            client_id = parse_int(client.get("id")) or 0
            interests = interests_by_client.get(client_id, [])
            favorites = favorites_by_client.get(client_id, [])
            offers = offers_by_client.get(client_id, [])
            ruleouts = [
                item
                for item in ruleouts_by_client.get(client_id, [])
                if str(item.get("agent_name") or "").strip().casefold()
                == str(client.get("agent") or "").strip().casefold()
            ]
            normalized_clients.append(
                {
                    "id": client_id,
                    "profile_id": parse_int(client.get("profile_id")),
                    "name": str(client.get("name") or "").strip(),
                    "position": str(client.get("position") or "").strip(),
                    "rating": str(client.get("rating") or "").strip(),
                    "free_agent_type": str(client.get("free_agent_type") or "").strip(),
                    "rights_team_code": normalize_team_code(client.get("rights_team_code")),
                    "agent": str(client.get("agent") or "").strip(),
                    "interest_count": len(interests),
                    "favorite_count": len(favorites),
                    "offer_count": len(offers),
                    "interests": [
                        {
                            "id": parse_int(item.get("id")),
                            "team_code": normalize_team_code(item.get("team_code")),
                            "team_name": str(item.get("team_name") or "").strip(),
                            "economic_offer": str(item.get("economic_offer") or "").strip(),
                            "role_offer": str(item.get("role_offer") or "").strip(),
                            "comments": str(item.get("comments") or "").strip(),
                            "submitted_by_name": str(item.get("submitted_by_name") or "").strip(),
                            "updated_at": str(item.get("updated_at") or "").strip(),
                        }
                        for item in interests
                    ],
                    "favorites": [
                        {
                            "id": parse_int(item.get("id")),
                            "team_code": normalize_team_code(item.get("team_code")),
                            "team_name": str(item.get("team_name") or "").strip(),
                            "updated_at": str(item.get("updated_at") or item.get("created_at") or "").strip(),
                        }
                        for item in favorites
                    ],
                    "offers": [
                        {
                            "team_code": normalize_team_code(item.get("team_code")),
                            "team_name": str(item.get("team_name") or "").strip(),
                            "status": str(item.get("status") or "").strip(),
                            "updated_at": str(item.get("updated_at") or item.get("created_at") or "").strip(),
                        }
                        for item in offers
                    ],
                    "ruled_out_teams": [
                        {
                            "id": parse_int(item.get("id")),
                            "team_code": normalize_team_code(item.get("team_code")),
                            "team_name": str(item.get("team_name") or "").strip(),
                            "updated_at": str(item.get("updated_at") or item.get("created_at") or "").strip(),
                        }
                        for item in ruleouts
                    ],
                }
            )

        normalized_clients.sort(
            key=lambda item: (
                -int(item.get("interest_count") or 0),
                -int(item.get("favorite_count") or 0),
                str(item.get("name") or "").casefold(),
            )
        )
        return {
            "agent_name": agent_name,
            "clients": normalized_clients,
            "missing_agent": False,
            "gm_spending_limits": self.list_gm_free_agent_spending_limits(),
        }

    def generate_offseason_exceptions(
        self,
        season_year: int,
        team_codes: Optional[List[str]] = None,
        choices: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        selected_year = parse_int(season_year)
        if selected_year is None:
            raise ValueError("invalid_season_year")
        selected_codes = set(normalize_team_codes(team_codes)) if team_codes else None
        choices = {str(k).upper(): str(v or "").strip().lower() for k, v in (choices or {}).items()}
        generated: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        with self.connect() as conn:
            teams = self.list_teams()
            timestamp = now_iso()
            for team in teams:
                team_code = str(team.get("code") or "").upper()
                if selected_codes is not None and team_code not in selected_codes:
                    continue
                team_data = self.get_team(team_code, move_season_year=selected_year)
                if not team_data:
                    continue
                team_row = team_data.get("team") or {}
                team_id = parse_int(team_row.get("id"))
                summary = (team_data.get("season_summaries") or {}).get(str(selected_year))
                if team_id is None or not summary:
                    continue
                estimate = self._offseason_exception_estimate_from_summary(
                    summary,
                    team_data.get("assets") or [],
                )
                mode = str(estimate.get("operating_mode") or "")
                eligible_items = [
                    item
                    for item in estimate.get("eligible") or []
                    if str(item.get("key") or "").strip() in GENERATED_OFFSEASON_EXCEPTION_KEYS
                ]
                if mode == "choice_pending":
                    choice = choices.get(team_code)
                    if choice == "room":
                        room_path = next(
                            (
                                path for path in estimate.get("paths") or []
                                if str(path.get("key") or "").strip() == "room"
                            ),
                            {},
                        )
                        exception_items = [
                            item
                            for item in room_path.get("eligible") or []
                            if str(item.get("key") or "").strip() in GENERATED_OFFSEASON_EXCEPTION_KEYS
                        ]
                    elif choice in {"over_cap", "exceptions"}:
                        over_cap_path = next(
                            (
                                path for path in estimate.get("paths") or []
                                if str(path.get("key") or "").strip() == "over_cap"
                            ),
                            {},
                        )
                        exception_items = [
                            item
                            for item in over_cap_path.get("eligible") or []
                            if str(item.get("key") or "").strip() in GENERATED_OFFSEASON_EXCEPTION_KEYS
                        ]
                    else:
                        skipped.append(
                            {
                                "team_code": team_code,
                                "reason": "choice_pending",
                                "message": "Decisión pendiente: cap space o excepciones over-the-cap.",
                            }
                        )
                        continue
                elif mode == "room":
                    exception_items = eligible_items
                elif mode == "over_cap_below_first":
                    exception_items = eligible_items
                elif mode == "above_first_below_second":
                    exception_items = eligible_items
                else:
                    exception_items = []

                placeholders = ",".join("?" for _ in GENERATED_OFFSEASON_EXCEPTION_KEYS)
                conn.execute(
                    f"""
                    DELETE FROM assets
                    WHERE team_id = ?
                      AND asset_type = 'exception'
                      AND generated_exception_season = ?
                      AND generated_exception_key IN ({placeholders})
                    """,
                    (team_id, selected_year, *GENERATED_OFFSEASON_EXCEPTION_KEYS),
                )

                created_assets = []
                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (team_id,),
                ).fetchone()["mx"]
                row_order = int(mx)
                values = estimate.get("values") or {}
                for item in exception_items:
                    key = str(item.get("key") or "").strip()
                    if key not in GENERATED_OFFSEASON_EXCEPTION_KEYS:
                        continue
                    definition = OFFSEASON_EXCEPTION_DEFINITIONS[key]
                    amount = round(float(item.get("amount") or values.get(key) or 0.0))
                    row_order += 1
                    cur = conn.execute(
                        """
                        INSERT INTO assets (
                            team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                            draft_pick_type, draft_round, original_owner, exception_type,
                            draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                            draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                            generated_exception_key, generated_exception_season,
                            created_at, updated_at
                        )
                        VALUES (?, ?, 'exception', ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, 0, 0, 0, NULL, NULL, 0, ?, ?, ?, ?)
                        """,
                        (
                            team_id,
                            row_order,
                            selected_year,
                            definition["label"],
                            f"Excepción oficial generada automáticamente para {season_label(selected_year)}.",
                            str(amount),
                            float(amount),
                            definition["exception_type"],
                            key,
                            selected_year,
                            timestamp,
                            timestamp,
                        ),
                    )
                    created_assets.append({"id": int(cur.lastrowid), "key": key, "amount": amount})
                generated.append(
                    {
                        "team_code": team_code,
                        "operating_mode": mode,
                        "created": created_assets,
                    }
                )
            conn.commit()
        return {
            "ok": True,
            "season_year": selected_year,
            "season_label": season_label(selected_year),
            "generated": generated,
            "skipped": skipped,
        }

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

    def _player_payload_affects_free_agency_sync(self, payload: Dict[str, Any]) -> bool:
        return self._player_identity_service().payload_affects_generated_sync(payload)

    def _player_identity_service(self) -> PlayerIdentityService:
        return PlayerIdentityService(self, contract_seasons=PLAYER_CONTRACT_SEASONS)

    def _sync_free_agency_generated_rows_if_needed(self, conn: sqlite3.Connection, payload: Dict[str, Any]) -> None:
        self._player_identity_service().synchronize_for_player_update(conn, payload)

    def update_player(self, player_id: int, payload: Dict[str, Any]) -> bool:
        return self._player_repository.update(player_id, payload)


    def _make_player_profile_unavailable_conn(
        self,
        conn: sqlite3.Connection,
        profile_id: int,
        status: str,
        timestamp: str,
    ) -> Dict[str, int]:
        normalized_status = normalize_player_profile_status(status)
        if not is_unavailable_player_profile_status(normalized_status):
            return {"players": 0, "free_agents": 0, "requests": 0}

        player_rows = conn.execute(
            """
            SELECT p.id, p.name, t.code AS team_code
            FROM players p
            JOIN teams t ON t.id = p.team_id
            WHERE p.profile_id = ?
            ORDER BY p.id
            """,
            (int(profile_id),),
        ).fetchall()
        for row in player_rows:
            self._record_player_transaction(
                conn,
                profile_id,
                normalized_status,
                player_profile_status_label(normalized_status),
                player_id=int(row["id"]),
                team_code=row["team_code"],
                from_team_code=row["team_code"],
                details={
                    "player_name": str(row["name"] or "").strip(),
                    "profile_status": normalized_status,
                },
                created_at=timestamp,
            )

        free_agent_ids = [
            int(row["id"])
            for row in conn.execute(
                "SELECT id FROM free_agents WHERE profile_id = ?",
                (int(profile_id),),
            ).fetchall()
        ]
        request_count = 0
        if free_agent_ids:
            placeholders = ",".join("?" for _ in free_agent_ids)
            for table in ("free_agent_interests", "free_agent_favorites", "free_agent_team_ruleouts"):
                if self._table_exists_conn(conn, table):
                    conn.execute(
                        f"DELETE FROM {table} WHERE free_agent_id IN ({placeholders})",
                        free_agent_ids,
                    )
            request_count = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM gm_free_agent_offer_requests WHERE free_agent_id IN ({placeholders})",
                    free_agent_ids,
                ).fetchone()[0]
            )
            pending_request_ids = [
                int(row["id"])
                for row in conn.execute(
                    f"""
                    SELECT id
                    FROM gm_free_agent_offer_requests
                    WHERE free_agent_id IN ({placeholders})
                      AND status = 'pending'
                    ORDER BY id
                    """,
                    free_agent_ids,
                ).fetchall()
            ]
            for pending_request_id in pending_request_ids:
                self._transition_workflow_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    pending_request_id,
                    "cancelled",
                    reason=f"player_profile_{normalized_status}",
                    command_id=(
                        f"gm-free-agent-offer:{pending_request_id}:"
                        f"profile-{normalized_status}"
                    ),
                    updates={"updated_at": timestamp, "decided_at": timestamp},
                    metadata={
                        "profile_id": int(profile_id),
                        "profile_status": normalized_status,
                    },
                    timestamp=timestamp,
                )

        player_cur = conn.execute("DELETE FROM players WHERE profile_id = ?", (int(profile_id),))
        free_agent_cur = conn.execute("DELETE FROM free_agents WHERE profile_id = ?", (int(profile_id),))
        return {
            "players": int(player_cur.rowcount or 0),
            "free_agents": int(free_agent_cur.rowcount or 0),
            "requests": request_count,
        }

    def update_player_profile(self, profile_id: int, payload: Dict[str, Any]) -> bool:
        return self._player_repository.update_profile(profile_id, payload)

    def delete_player_profile(self, profile_id: int) -> Dict[str, Any]:
        return self._player_repository.delete_profile(profile_id)



    def merge_player_profiles(self, source_profile_id: int, target_profile_id: int) -> Dict[str, Any]:
        return self._player_identity_service().merge_profiles(source_profile_id, target_profile_id)

    def create_player_transaction(self, profile_id: int, payload: Dict[str, Any]) -> Optional[int]:
        return self._player_repository.create_transaction(profile_id, payload)

    def update_player_transaction(self, transaction_id: int, payload: Dict[str, Any]) -> bool:
        return self._player_repository.update_transaction(transaction_id, payload)

    def delete_player_transaction(self, transaction_id: int) -> bool:
        return self._player_repository.delete_transaction(transaction_id)

    def create_player_salary_history(self, profile_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._player_repository.create_salary_history(profile_id, payload)

    def update_player_salary_history(self, salary_history_id: int, payload: Dict[str, Any]) -> bool:
        return self._player_repository.update_salary_history(salary_history_id, payload)

    def delete_player_salary_history(self, salary_history_id: int) -> bool:
        return self._player_repository.delete_salary_history(salary_history_id)


    def move_player(self, player_id: int, to_team_code: str) -> bool:
        return self._player_repository.move(player_id, to_team_code)

    def create_player(
        self,
        team_code: str,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[int]:
        return self._player_repository.create(team_code, payload, conn)

    def _create_player_conn(
        self,
        conn: sqlite3.Connection,
        team_code: str,
        payload: Dict[str, Any],
    ) -> Optional[int]:
        return self._player_repository.create_conn(conn, team_code, payload)

    def delete_player(self, player_id: int) -> bool:
        return self._player_repository.delete(player_id)

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

    def _create_waiver_player_conn(
        self,
        conn: sqlite3.Connection,
        player: Dict[str, Any],
        *,
        created_at: str,
        cut_options: Optional[Dict[str, Any]] = None,
    ) -> int:
        expires_at = (datetime.fromisoformat(created_at.replace("Z", "+00:00")) + timedelta(hours=48)).astimezone(UTC)
        expires_text = expires_at.isoformat().replace("+00:00", "Z")
        payload = self._player_contract_snapshot_payload(player)
        normalized_cut_options = self._normalize_cut_options(cut_options)
        if normalized_cut_options.get("buyout") or normalized_cut_options.get("stretch"):
            payload["cut_settings"] = normalized_cut_options
        cur = conn.execute(
            """
            INSERT INTO waiver_players (
                player_id, profile_id, from_team_id, from_team_code, player_name,
                position, rating, bird_rights, years_left, contract_json,
                waiver_expires_at, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                parse_int(player.get("id")),
                parse_int(player.get("profile_id")),
                int(player["team_id"]),
                str(player.get("team_code") or "").upper(),
                str(player.get("name") or "Jugador").strip() or "Jugador",
                str(player.get("position") or "").strip() or None,
                str(player.get("rating") or "").strip() or None,
                str(player.get("bird_rights") or "").strip() or None,
                normalize_bird_years(player.get("years_left")),
                json.dumps(payload, ensure_ascii=False),
                expires_text,
                created_at,
                created_at,
            ),
        )
        waiver_id = int(cur.lastrowid)
        self._record_workflow_creation_conn(
            conn,
            "waiver_player",
            waiver_id,
            "active",
            actor=None,
            reason="player_waived",
            metadata={"profile_id": parse_int(player.get("profile_id")), "team_code": player.get("team_code")},
            command_id=f"waiver-player:{waiver_id}:created",
        )
        return waiver_id

    def _insert_dead_contract_from_waiver_conn(
        self,
        conn: sqlite3.Connection,
        waiver: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        timestamp: str,
    ) -> int:
        team_id = int(waiver["from_team_id"])
        dead_mx = conn.execute(
            "SELECT COALESCE(MAX(row_order), 0) AS mx FROM dead_contracts WHERE team_id = ?",
            (team_id,),
        ).fetchone()["mx"]
        settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}
        current_year = parse_int(settings.get("current_year")) or PLAYER_CONTRACT_SEASONS[0]
        salary_texts, cut_note = self._cut_dead_cap_schedule(
            payload,
            payload.get("cut_settings") if isinstance(payload.get("cut_settings"), dict) else None,
            current_year=int(current_year),
        )
        label = waiver.get("player_name") or payload.get("name") or "Cut Player"
        if cut_note:
            label = f"{label} ({cut_note})"
        first_dead_text = next((salary_texts.get(season) for season in PLAYER_CONTRACT_SEASONS if salary_texts.get(season)), None)
        cur = conn.execute(
            """
            INSERT INTO dead_contracts (
                team_id, profile_id, row_order, dead_type, label, amount_text, amount_num,
                salary_2025_text, salary_2025_num,
                salary_2026_text, salary_2026_num,
                salary_2027_text, salary_2027_num,
                salary_2028_text, salary_2028_num,
                salary_2029_text, salary_2029_num,
                salary_2030_text, salary_2030_num,
                salary_2031_text, salary_2031_num,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                parse_int(waiver.get("profile_id")),
                int(dead_mx) + 1,
                "two_way" if str(payload.get("bird_rights") or "").upper() == "TW" else "normal",
                label,
                first_dead_text,
                parse_salary_amount(first_dead_text),
                salary_texts.get(2025),
                parse_salary_amount(salary_texts.get(2025)),
                salary_texts.get(2026),
                parse_salary_amount(salary_texts.get(2026)),
                salary_texts.get(2027),
                parse_salary_amount(salary_texts.get(2027)),
                salary_texts.get(2028),
                parse_salary_amount(salary_texts.get(2028)),
                salary_texts.get(2029),
                parse_salary_amount(salary_texts.get(2029)),
                salary_texts.get(2030),
                parse_salary_amount(salary_texts.get(2030)),
                salary_texts.get(2031),
                parse_salary_amount(salary_texts.get(2031)),
                timestamp,
                timestamp,
            ),
        )
        return int(cur.lastrowid)

    def _ensure_dead_contract_for_waiver_conn(
        self,
        conn: sqlite3.Connection,
        waiver: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        timestamp: str,
    ) -> int:
        existing_id = parse_int(waiver.get("dead_contract_id"))
        if existing_id is not None:
            existing = conn.execute("SELECT id FROM dead_contracts WHERE id = ?", (existing_id,)).fetchone()
            if existing:
                return int(existing["id"])
        dead_contract_id = self._insert_dead_contract_from_waiver_conn(conn, waiver, payload, timestamp=timestamp)
        conn.execute(
            "UPDATE waiver_players SET dead_contract_id = ?, updated_at = ? WHERE id = ?",
            (dead_contract_id, timestamp, int(waiver["id"])),
        )
        return dead_contract_id

    def _upsert_free_agent_from_waiver_conn(
        self,
        conn: sqlite3.Connection,
        waiver: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        timestamp: str,
    ) -> int:
        profile_id = parse_int(waiver.get("profile_id"))
        name = str(waiver.get("player_name") or payload.get("name") or "Agente libre").strip() or "Agente libre"
        existing = conn.execute(
            "SELECT id FROM free_agents WHERE profile_id = ? LIMIT 1",
            (profile_id,),
        ).fetchone() if profile_id is not None else None
        if existing:
            free_agent_id = int(existing["id"])
            conn.execute(
                """
                UPDATE free_agents
                SET name = ?, position = ?, bird_rights = ?, rating = ?, years_left = ?,
                    free_agent_type = ?, source = ?, rights_team_code = NULL,
                    notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    str(payload.get("position") or waiver.get("position") or "").strip() or None,
                    str(payload.get("bird_rights") or waiver.get("bird_rights") or "").strip() or None,
                    str(payload.get("rating") or waiver.get("rating") or "").strip() or None,
                    normalize_bird_years(payload.get("years_left")),
                    FREE_AGENT_TYPE_UNRESTRICTED,
                    "waiver_expired",
                    "Waivers no reclamado en 48h.",
                    timestamp,
                    free_agent_id,
                ),
            )
            return free_agent_id
        cur = conn.execute(
            """
            INSERT INTO free_agents (
                profile_id, name, position, bird_rights, rating, years_left,
                free_agent_type, source, rights_team_code, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                profile_id,
                name,
                str(payload.get("position") or waiver.get("position") or "").strip() or None,
                str(payload.get("bird_rights") or waiver.get("bird_rights") or "").strip() or None,
                str(payload.get("rating") or waiver.get("rating") or "").strip() or None,
                normalize_bird_years(payload.get("years_left")),
                FREE_AGENT_TYPE_UNRESTRICTED,
                "waiver_expired",
                "Waivers no reclamado en 48h.",
                timestamp,
                timestamp,
            ),
        )
        return int(cur.lastrowid)

    def _create_player_from_contract_payload_conn(
        self,
        conn: sqlite3.Connection,
        team_code: str,
        payload: Dict[str, Any],
        *,
        timestamp: str,
    ) -> Optional[int]:
        team = conn.execute("SELECT id FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
        if not team:
            return None
        mx = conn.execute(
            "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
            (team["id"],),
        ).fetchone()["mx"]
        values = {
            "name": payload.get("name", "New Player"),
            "bird_rights": payload.get("bird_rights"),
            "rating": payload.get("rating"),
            "position": payload.get("position"),
            "years_left": normalize_bird_years(payload.get("years_left")),
            "reference_image_url": payload.get("reference_image_url"),
            "profile_notes": payload.get("profile_notes"),
            "experience_years": normalize_experience_years(payload.get("experience_years")),
            "signed_as_free_agent": 1 if parse_bool(payload.get("signed_as_free_agent")) else 0,
            "notes": payload.get("notes"),
            "provisional_amounts": 1 if parse_bool(payload.get("provisional_amounts")) else 0,
            "partially_guaranteed": 1 if parse_bool(payload.get("partially_guaranteed")) else 0,
        }
        for season in PLAYER_CONTRACT_SEASONS:
            values[f"salary_{season}_text"] = payload.get(f"salary_{season}_text")
            values[f"salary_{season}_guaranteed_text"] = payload.get(f"salary_{season}_guaranteed_text")
            values[f"option_{season}"] = payload.get(f"option_{season}")
            values[f"salary_{season}_provisional"] = 1 if parse_bool(payload.get(f"salary_{season}_provisional")) else 0
            values[f"salary_{season}_partially_guaranteed"] = 1 if parse_bool(payload.get(f"salary_{season}_partially_guaranteed")) else 0
        profile_payload = dict(payload)
        profile_payload["experience_years"] = values["experience_years"]
        profile_id = self._resolve_profile_for_new_row(
            conn,
            profile_payload,
            name=values["name"],
            timestamp=timestamp,
            forbid_active_contract=True,
        )
        cur = conn.execute(
            """
            INSERT INTO players (
                team_id, profile_id, row_order, bird_rights, rating, name, position, years_left,
                salary_2025_text, salary_2025_num,
                salary_2026_text, salary_2026_num,
                salary_2027_text, salary_2027_num,
                salary_2028_text, salary_2028_num,
                salary_2029_text, salary_2029_num,
                salary_2030_text, salary_2030_num,
                salary_2031_text, salary_2031_num,
                option_2025, option_2026, option_2027, option_2028, option_2029, option_2030, option_2031,
                provisional_amounts, partially_guaranteed,
                salary_2025_provisional, salary_2026_provisional, salary_2027_provisional,
                salary_2028_provisional, salary_2029_provisional, salary_2030_provisional, salary_2031_provisional,
                salary_2025_partially_guaranteed, salary_2026_partially_guaranteed, salary_2027_partially_guaranteed,
                salary_2028_partially_guaranteed, salary_2029_partially_guaranteed, salary_2030_partially_guaranteed,
                salary_2031_partially_guaranteed,
                salary_2025_guaranteed_text, salary_2026_guaranteed_text, salary_2027_guaranteed_text,
                salary_2028_guaranteed_text, salary_2029_guaranteed_text, salary_2030_guaranteed_text,
                salary_2031_guaranteed_text,
                notes, reference_image_url, profile_notes, experience_years, signed_as_free_agent,
                is_two_way, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team["id"],
                profile_id,
                int(mx) + 1,
                values["bird_rights"],
                values["rating"],
                values["name"],
                values["position"],
                values["years_left"],
                values["salary_2025_text"], parse_salary_amount(values["salary_2025_text"]),
                values["salary_2026_text"], parse_salary_amount(values["salary_2026_text"]),
                values["salary_2027_text"], parse_salary_amount(values["salary_2027_text"]),
                values["salary_2028_text"], parse_salary_amount(values["salary_2028_text"]),
                values["salary_2029_text"], parse_salary_amount(values["salary_2029_text"]),
                values["salary_2030_text"], parse_salary_amount(values["salary_2030_text"]),
                values["salary_2031_text"], parse_salary_amount(values["salary_2031_text"]),
                values["option_2025"], values["option_2026"], values["option_2027"], values["option_2028"], values["option_2029"], values["option_2030"], values["option_2031"],
                values["provisional_amounts"], values["partially_guaranteed"],
                values["salary_2025_provisional"], values["salary_2026_provisional"], values["salary_2027_provisional"],
                values["salary_2028_provisional"], values["salary_2029_provisional"], values["salary_2030_provisional"], values["salary_2031_provisional"],
                values["salary_2025_partially_guaranteed"], values["salary_2026_partially_guaranteed"], values["salary_2027_partially_guaranteed"],
                values["salary_2028_partially_guaranteed"], values["salary_2029_partially_guaranteed"], values["salary_2030_partially_guaranteed"],
                values["salary_2031_partially_guaranteed"],
                values["salary_2025_guaranteed_text"], values["salary_2026_guaranteed_text"], values["salary_2027_guaranteed_text"],
                values["salary_2028_guaranteed_text"], values["salary_2029_guaranteed_text"], values["salary_2030_guaranteed_text"],
                values["salary_2031_guaranteed_text"],
                values["notes"], values["reference_image_url"], values["profile_notes"], values["experience_years"], values["signed_as_free_agent"],
                1 if str(values["bird_rights"] or "").upper() == "TW" else 0,
                timestamp,
                timestamp,
            ),
        )
        player_id = int(cur.lastrowid)
        self._record_player_transaction(
            conn,
            profile_id,
            "create",
            f"Alta en {team_code.upper()}",
            player_id=player_id,
            team_code=team_code,
            details={"player_name": values["name"]},
            created_at=timestamp,
        )
        return player_id

    def _waive_player_row_conn(
        self,
        conn: sqlite3.Connection,
        player_id: int,
        *,
        timestamp: str,
        cut_options: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        cur = conn.execute(
            f"""
            SELECT {self._player_select_columns()}, t.code AS team_code, t.name AS team_name
            FROM players p
            LEFT JOIN player_profiles pp ON pp.id = p.profile_id
            JOIN teams t ON t.id = p.team_id
            WHERE p.id = ?
            """,
            (player_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        player = self._merge_player_profile(row_to_dict(cur, row))
        profile_id = self._ensure_profile_for_player(conn, player_id, timestamp)
        if profile_id is None:
            return None
        player["profile_id"] = profile_id
        if self._player_is_ten_day_contract(player):
            payload = self._player_contract_snapshot_payload(player)
            waiver_like = {
                "from_team_id": player["team_id"],
                "from_team_code": player.get("team_code"),
                "profile_id": profile_id,
                "player_name": player.get("name"),
            }
            free_agent_id = self._upsert_free_agent_from_waiver_conn(conn, waiver_like, payload, timestamp=timestamp)
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            return {"waiver": False, "dead_contract_id": None, "free_agent_id": free_agent_id, **player}
        waiver_id = self._create_waiver_player_conn(conn, player, created_at=timestamp, cut_options=cut_options)
        waiver_row = conn.execute("SELECT * FROM waiver_players WHERE id = ?", (waiver_id,)).fetchone()
        dead_contract_id = None
        if waiver_row:
            waiver_data = dict(waiver_row)
            payload = json.loads(waiver_data.get("contract_json") or "{}")
            dead_contract_id = self._ensure_dead_contract_for_waiver_conn(
                conn,
                waiver_data,
                payload,
                timestamp=timestamp,
            )
        conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
        return {
            "waiver": True,
            "waiver_id": waiver_id,
            "waiver_expires_at": waiver_row["waiver_expires_at"] if waiver_row else None,
            "dead_contract_id": dead_contract_id,
            **player,
        }

    def _expire_waiver_without_claim_conn(
        self,
        conn: sqlite3.Connection,
        waiver: Dict[str, Any],
        *,
        timestamp: str,
    ) -> Dict[str, Any]:
        payload = json.loads(waiver.get("contract_json") or "{}")
        dead_contract_id = self._ensure_dead_contract_for_waiver_conn(conn, waiver, payload, timestamp=timestamp)
        free_agent_id = self._upsert_free_agent_from_waiver_conn(conn, waiver, payload, timestamp=timestamp)
        self._transition_workflow_conn(
            conn,
            "waiver_player",
            int(waiver["id"]),
            "expired",
            reason="waiver_period_expired_without_claim",
            updates={
                "dead_contract_id": dead_contract_id,
                "free_agent_id": free_agent_id,
                "updated_at": timestamp,
            },
            command_id=f"waiver-player:{int(waiver['id'])}:expired",
        )
        self._record_player_transaction(
            conn,
            parse_int(waiver.get("profile_id")),
            "waiver_expired",
            f"Waivers expirado: {waiver.get('player_name')}",
            free_agent_id=free_agent_id,
            dead_contract_id=dead_contract_id,
            team_code=str(waiver.get("from_team_code") or "").upper(),
            from_team_code=str(waiver.get("from_team_code") or "").upper(),
            details={"player_name": waiver.get("player_name"), "waiver_player_id": waiver.get("id")},
            created_at=timestamp,
        )
        return {"dead_contract_id": dead_contract_id, "free_agent_id": free_agent_id}

    def _approve_waiver_claim_conn(
        self,
        conn: sqlite3.Connection,
        claim: Dict[str, Any],
        *,
        admin: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        timestamp = timestamp or now_iso()
        waiver = conn.execute("SELECT * FROM waiver_players WHERE id = ?", (int(claim["waiver_player_id"]),)).fetchone()
        if not waiver:
            return None
        waiver_data = dict(waiver)
        if str(waiver_data.get("status") or "") not in {"active", "pending_claims"}:
            return None
        payload = json.loads(waiver_data.get("contract_json") or "{}")
        target_team_code = str(claim.get("team_code") or "").upper()
        contingent_cut_id = parse_int(claim.get("contingent_cut_player_id"))
        if contingent_cut_id is not None:
            # The contingent cut opens the roster spot only if this claim wins.
            self._waive_player_row_conn(conn, int(contingent_cut_id), timestamp=timestamp)
        player_id = self._create_player_from_contract_payload_conn(conn, target_team_code, payload, timestamp=timestamp)
        if not player_id:
            return None
        dead_contract_id = parse_int(waiver_data.get("dead_contract_id"))
        if dead_contract_id is not None:
            conn.execute("DELETE FROM dead_contracts WHERE id = ?", (dead_contract_id,))
        pending_claims = conn.execute(
            "SELECT id FROM waiver_claims WHERE waiver_player_id = ? AND status = 'pending'",
            (int(claim["waiver_player_id"]),),
        ).fetchall()
        for pending_claim in pending_claims:
            pending_id = int(pending_claim["id"])
            claim_state = "approved" if pending_id == int(claim["id"]) else "rejected"
            self._transition_workflow_conn(
                conn,
                "waiver_claim",
                pending_id,
                claim_state,
                actor=admin,
                reason=("waiver_claim_selected" if claim_state == "approved" else "waiver_claim_not_selected"),
                updates={
                    "admin_email": str((admin or {}).get("email") or "").strip() or None,
                    "admin_name": str((admin or {}).get("name") or "").strip() or None,
                    "updated_at": timestamp,
                    "decided_at": timestamp,
                },
                command_id=f"waiver-claim:{pending_id}:{claim_state}",
            )
        self._transition_workflow_conn(
            conn,
            "waiver_player",
            int(claim["waiver_player_id"]),
            "claimed",
            actor=admin,
            reason="waiver_claim_awarded",
            updates={
                "claimed_team_code": target_team_code,
                "player_id": player_id,
                "dead_contract_id": None,
                "updated_at": timestamp,
            },
            command_id=f"waiver-player:{int(claim['waiver_player_id'])}:claimed",
            metadata={"claim_id": int(claim["id"]), "team_code": target_team_code},
        )
        self._record_player_transaction(
            conn,
            parse_int(waiver_data.get("profile_id")),
            "waiver_claim",
            f"{target_team_code} reclama de waivers a {waiver_data.get('player_name')}",
            player_id=player_id,
            team_code=target_team_code,
            from_team_code=str(waiver_data.get("from_team_code") or "").upper(),
            to_team_code=target_team_code,
            details={"player_name": waiver_data.get("player_name"), "waiver_player_id": waiver_data.get("id")},
            created_at=timestamp,
        )
        return {"player_id": player_id, "team_code": target_team_code, "player_name": waiver_data.get("player_name")}

    def process_expired_waivers_command(self) -> Dict[str, Any]:
        timestamp = now_iso()
        processed: List[Dict[str, Any]] = []
        with self.transaction("IMMEDIATE") as conn:
            waivers = conn.execute(
                """
                SELECT * FROM waiver_players
                WHERE status IN ('active', 'pending_claims') AND waiver_expires_at <= ?
                ORDER BY waiver_expires_at, id
                """,
                (timestamp,),
            ).fetchall()
            for waiver_row in waivers:
                waiver = dict(waiver_row)
                claims = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT * FROM waiver_claims WHERE waiver_player_id = ? AND status = 'pending' ORDER BY created_at, id",
                        (int(waiver["id"]),),
                    ).fetchall()
                ]
                if len(claims) == 1:
                    result = self._approve_waiver_claim_conn(conn, claims[0], timestamp=timestamp)
                    if result:
                        processed.append({"waiver_player_id": int(waiver["id"]), "action": "claimed", **result})
                elif len(claims) > 1:
                    if str(waiver.get("status") or "") == "active":
                        self._transition_workflow_conn(
                            conn,
                            "waiver_player",
                            int(waiver["id"]),
                            "pending_claims",
                            reason="multiple_waiver_claims_require_admin",
                            updates={"updated_at": timestamp},
                            command_id=f"waiver-player:{int(waiver['id'])}:pending-claims",
                            metadata={"claim_count": len(claims)},
                        )
                    processed.append({"waiver_player_id": int(waiver["id"]), "action": "pending_admin"})
                else:
                    result = self._expire_waiver_without_claim_conn(conn, waiver, timestamp=timestamp)
                    processed.append({"waiver_player_id": int(waiver["id"]), "action": "expired", **result})
        return {"processed": processed, "count": len(processed)}

    def process_expired_waivers(self) -> Dict[str, Any]:
        return self.process_expired_waivers_command()

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
        self.process_expired_waivers()
        settings = self.get_settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        session_team_codes = [
            str(code or "").upper()
            for code in (session or {}).get("team_codes", [])
            if str(code or "").strip()
        ]
        with self.transaction("IMMEDIATE") as conn:
            cur = conn.execute(
                """
                SELECT
                    w.*,
                    t.name AS from_team_name,
                    pp.reference_image_url AS profile_reference_image_url
                FROM waiver_players w
                JOIN teams t ON t.id = w.from_team_id
                LEFT JOIN player_profiles pp ON pp.id = w.profile_id
                WHERE w.status IN ('active', 'pending_claims')
                ORDER BY w.waiver_expires_at, w.created_at, w.id
                """
            )
            rows = [row_to_dict(cur, row) for row in cur.fetchall()]
            claim_rows = conn.execute(
                """
                SELECT c.waiver_player_id, c.team_code
                FROM waiver_claims c
                WHERE c.status = 'pending'
                """
            ).fetchall()
            claimed_by_session = {
                int(row["waiver_player_id"])
                for row in claim_rows
                if str(row["team_code"] or "").upper() in session_team_codes
            }
        waivers: List[Dict[str, Any]] = []
        for row in rows:
            salary = self._waiver_salary_for_season(row, current_year)
            item = {
                "id": row.get("id"),
                "profile_id": row.get("profile_id"),
                "player_name": row.get("player_name"),
                "position": row.get("position"),
                "rating": row.get("rating"),
                "bird_rights": row.get("bird_rights"),
                "years_left": row.get("years_left"),
                "from_team_code": row.get("from_team_code"),
                "from_team_name": row.get("from_team_name"),
                "waiver_expires_at": row.get("waiver_expires_at"),
                "status": row.get("status"),
                "salary_current": round(salary),
                "salary": round(salary),
                "reference_image_url": row.get("profile_reference_image_url"),
                "already_claimed_by_session": int(row.get("id") or 0) in claimed_by_session,
                "already_claimed": int(row.get("id") or 0) in claimed_by_session,
            }
            if len(session_team_codes) == 1:
                item["eligibility"] = self._waiver_claim_eligibility(session_team_codes[0], row, season_year=current_year)
            waivers.append(item)
        return {"waivers": waivers, "count": len(waivers)}

    def create_waiver_claim(
        self,
        waiver_player_id: int,
        team_code: str,
        payload: Dict[str, Any],
        requester: Dict[str, Any],
    ) -> Dict[str, Any]:
        timestamp = now_iso()
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        contingent_cut_player_id = parse_int(payload.get("contingent_cut_player_id"))
        with self.connect() as conn:
            waiver = conn.execute(
                "SELECT * FROM waiver_players WHERE id = ? AND status IN ('active', 'pending_claims')",
                (int(waiver_player_id),),
            ).fetchone()
            if not waiver:
                raise ValueError("waiver_not_found")
            team = conn.execute("SELECT id, code, name FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            eligibility = self._waiver_claim_eligibility(
                normalized_team,
                dict(waiver),
                contingent_cut_player_id=contingent_cut_player_id,
            )
            if not eligibility.get("eligible"):
                raise ValueError(str(eligibility.get("reason") or "not_eligible"))
            try:
                cur = conn.execute(
                    """
                    INSERT INTO waiver_claims (
                        waiver_player_id, team_id, team_code, requester_user_id,
                        requester_email, requester_name, contingent_cut_player_id,
                        status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(waiver_player_id),
                        int(team["id"]),
                        normalized_team,
                        parse_int(requester.get("user_id") or requester.get("id")),
                        str(requester.get("email") or "").strip() or None,
                        str(requester.get("name") or "").strip() or None,
                        contingent_cut_player_id,
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("claim_already_submitted") from err
            claim_id = int(cur.lastrowid)
            self._record_workflow_creation_conn(
                conn,
                "waiver_claim",
                claim_id,
                "pending",
                actor=requester,
                reason="waiver_claim_submitted",
                command_id=f"waiver-claim:{claim_id}:created",
                metadata={"waiver_player_id": int(waiver_player_id), "team_code": normalized_team},
            )
            return {
                "id": claim_id,
                "waiver_player_id": int(waiver_player_id),
                "team_code": normalized_team,
                "status": "pending",
                "eligibility": eligibility,
            }

    def list_waiver_claim_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        params: List[Any] = []
        where = ""
        if normalized_status and normalized_status != "all":
            where = "WHERE c.status = ?"
            params.append(normalized_status)
        with self.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT
                    c.*,
                    w.player_name,
                    w.position,
                    w.rating,
                    w.from_team_code,
                    w.waiver_expires_at,
                    t.name AS team_name
                FROM waiver_claims c
                JOIN waiver_players w ON w.id = c.waiver_player_id
                JOIN teams t ON t.id = c.team_id
                {where}
                ORDER BY
                    CASE c.status WHEN 'pending' THEN 0 ELSE 1 END,
                    c.created_at DESC,
                    c.id DESC
                """,
                params,
            )
            rows = []
            for row in cur.fetchall():
                item = row_to_dict(cur, row)
                item["request_type"] = "waiver_claim"
                item["action"] = "claimed"
                item["option_value"] = "Waivers"
                item["season_label"] = f"Desde {item.get('from_team_code') or ''}"
                rows.append(item)
            return rows

    def decide_waiver_claim_request(
        self,
        request_id: int,
        decision: str,
        admin: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        normalized = str(decision or "").strip().lower()
        if normalized not in {"approved", "rejected"}:
            raise ValueError("invalid_decision")
        with self.transaction("IMMEDIATE") as conn:
            claim_row = conn.execute("SELECT * FROM waiver_claims WHERE id = ?", (int(request_id),)).fetchone()
            if not claim_row:
                return None
            claim = dict(claim_row)
            if str(claim.get("status") or "") != "pending":
                raise ValueError("request_already_decided")
            if normalized == "approved":
                result = self._approve_waiver_claim_conn(conn, claim, admin=admin, timestamp=timestamp)
                if not result:
                    raise ValueError("waiver_not_available")
            else:
                try:
                    self._transition_workflow_conn(
                        conn,
                        "waiver_claim",
                        int(request_id),
                        "rejected",
                        actor=admin,
                        reason=str(note or "").strip() or "waiver_claim_rejected",
                        updates={
                            "admin_email": str((admin or {}).get("email") or "").strip() or None,
                            "admin_name": str((admin or {}).get("name") or "").strip() or None,
                            "admin_decision_note": str(note or "").strip() or None,
                            "updated_at": timestamp,
                            "decided_at": timestamp,
                        },
                        command_id=f"waiver-claim:{int(request_id)}:rejected",
                    )
                except WorkflowTransitionError as err:
                    raise ValueError("request_already_decided")
                result = {"id": int(request_id), "status": "rejected"}
            return result

    def _cap_hold_free_agent_type(self, player: Dict[str, Any], season: int) -> str:
        decision = (player.get("option_decisions") or {}).get(f"option_{int(season)}") or {}
        option_value = str(decision.get("option_value") or "").strip().upper()
        option_action = str(decision.get("action") or "").strip().lower()
        option_status = str(decision.get("status") or "").strip().lower()
        salary_text_code = str(player.get(f"salary_{int(season)}_text") or "").strip().upper()
        option_code = str(player.get(f"option_{int(season)}") or "").strip().upper()
        if salary_text_code == "QO" or option_code == "QO":
            return FREE_AGENT_TYPE_RESTRICTED
        if (
            option_value in {"QO", "GAP"}
            and option_action == "accepted"
            and option_status == "approved"
            and (
                option_code in {"QO", "GAP"}
                or not self._free_agency_has_future_contract_salary(player, int(season))
            )
        ):
            return FREE_AGENT_TYPE_RESTRICTED
        return FREE_AGENT_TYPE_UNRESTRICTED

    def _free_agency_has_future_contract_salary(self, player: Dict[str, Any], season: int) -> bool:
        rights_markers = {"NB", "EB", "FB", "QO", "GAP"}
        for future_season in PLAYER_CONTRACT_SEASONS:
            if int(future_season) <= int(season):
                continue
            salary_text = str(player.get(f"salary_{future_season}_text") or "").strip()
            salary_code = salary_text.upper()
            option_code = str(player.get(f"option_{future_season}") or "").strip().upper()
            salary_num = parse_float(player.get(f"salary_{future_season}_num"))
            if salary_num is not None and abs(float(salary_num)) > 0:
                return True
            salary_text_amount = parse_amount_like(salary_text)
            if salary_text_amount is not None and abs(float(salary_text_amount)) > 0:
                return True
            if salary_text and salary_text != "-" and salary_code not in rights_markers:
                return True
            if option_code and option_code not in rights_markers:
                return True
        return False

    def _free_agency_empty_cell(self, value: Any) -> bool:
        raw = str(value or "").strip()
        return raw in {"", "-", "—", "0"}

    def _free_agency_expiring_contract_without_next_year(self, player: Dict[str, Any], current_year: int, next_year: int) -> bool:
        if is_two_way_player(player) or is_exhibit10_player(player):
            return False
        if row_salary_num(player, int(current_year)) <= 0:
            return False
        if row_salary_num(player, int(next_year)) > 0:
            return False
        return (
            self._free_agency_empty_cell(player.get(f"salary_{int(next_year)}_text"))
            and self._free_agency_empty_cell(player.get(f"option_{int(next_year)}"))
        )

    def ensure_renounced_bird_rights_free_agent(
        self,
        player: Dict[str, Any],
        season_year: int,
        rights_value: str,
    ) -> Optional[int]:
        season = parse_int(season_year)
        rights = str(rights_value or "").strip().upper()
        if season is None or rights not in {"FB", "EB", "NB"}:
            return None

        timestamp = now_iso()
        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if not parse_bool(settings.get("free_agency_mode")) or int(season) != int(current_year):
                return None

            player_id = parse_int(player.get("id"))
            profile_id = parse_int(player.get("profile_id"))
            if profile_id is None and player_id is not None:
                profile_id = self._ensure_profile_for_player(conn, int(player_id), timestamp)
            if profile_id is None:
                return None

            team_code = normalize_team_code(player.get("team_code"))
            name = (
                str(player.get("profile_name") or player.get("name") or "Agente libre").strip()
                or "Agente libre"
            )
            default_notes = (
                f"Derechos Bird renunciados por {team_code or 'el equipo'} "
                f"para {season_label(int(season))}."
            )
            existing = conn.execute(
                "SELECT id, notes FROM free_agents WHERE profile_id = ? LIMIT 1",
                (int(profile_id),),
            ).fetchone()
            if existing:
                free_agent_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE free_agents
                    SET name = ?,
                        position = ?,
                        bird_rights = NULL,
                        rating = ?,
                        years_left = ?,
                        free_agent_type = ?,
                        source = ?,
                        rights_team_code = NULL,
                        notes = CASE
                            WHEN notes IS NULL
                                OR TRIM(notes) = ''
                                OR notes LIKE 'Cap hold retenido por %'
                                OR notes LIKE 'Derechos Bird renunciados por %'
                            THEN ?
                            ELSE notes
                        END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        name,
                        str(player.get("position") or "").strip() or None,
                        str(player.get("rating") or "").strip() or None,
                        normalize_bird_years(player.get("years_left")),
                        FREE_AGENT_TYPE_UNRESTRICTED,
                        FREE_AGENT_SOURCE_RENOUNCED_RIGHTS,
                        default_notes,
                        timestamp,
                        free_agent_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO free_agents (
                        profile_id, name, position, bird_rights, rating, years_left,
                        free_agent_type, source, rights_team_code, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        int(profile_id),
                        name,
                        str(player.get("position") or "").strip() or None,
                        str(player.get("rating") or "").strip() or None,
                        normalize_bird_years(player.get("years_left")),
                        FREE_AGENT_TYPE_UNRESTRICTED,
                        FREE_AGENT_SOURCE_RENOUNCED_RIGHTS,
                        default_notes,
                        timestamp,
                        timestamp,
                    ),
                )
                free_agent_id = int(cur.lastrowid)

            self._record_player_transaction(
                conn,
                profile_id,
                "free_agent",
                f"{team_code or 'Equipo'} renuncia los derechos {rights} de {name} para {season_label(int(season))}",
                player_id=player_id,
                free_agent_id=free_agent_id,
                team_code=team_code,
                from_team_code=team_code,
                details={
                    "player_name": name,
                    "season_year": int(season),
                    "rights_value": rights,
                    "source": FREE_AGENT_SOURCE_RENOUNCED_RIGHTS,
                },
                created_at=timestamp,
            )
            if player_id is not None:
                conn.execute("DELETE FROM players WHERE id = ?", (int(player_id),))
            conn.commit()
            return free_agent_id

    def _cap_hold_free_agent_bird_rights_code(self, player: Dict[str, Any], season: int) -> Optional[str]:
        for key in (f"salary_{int(season)}_text", f"option_{int(season)}"):
            code = str(player.get(key) or "").strip().upper()
            if code in {"NB", "EB", "FB"}:
                return code
        code = cap_hold_bird_code_from_years(player.get("years_left"))
        return code or None

    def _cleanup_active_contract_free_agents_conn(self, conn: sqlite3.Connection, current_year: int) -> int:
        active_profile_ids: List[int] = []
        teams_cur = conn.execute("SELECT id FROM teams ORDER BY id")
        for team in teams_cur.fetchall():
            team_id = parse_int(team["id"])
            if team_id is None:
                continue
            players = self._select_team_players(conn, int(team_id))
            self._attach_option_decisions(conn, players, int(team_id))
            for player in players:
                profile_id = parse_int(player.get("profile_id"))
                if profile_id is None:
                    continue
                has_active_salary = False
                for season in PLAYER_CONTRACT_SEASONS:
                    if int(season) < int(current_year):
                        continue
                    option_code = str(player.get(f"option_{season}") or "").strip().upper()
                    decision = (player.get("option_decisions") or {}).get(f"option_{season}") or {}
                    decision_option = str(decision.get("option_value") or "").strip().upper()
                    decision_action = str(decision.get("action") or "").strip().lower()
                    decision_status = str(decision.get("status") or "").strip().lower()
                    if (
                        decision_option in {"QO", "GAP"}
                        and decision_action == "accepted"
                        and decision_status == "approved"
                        and (
                            option_code in {"QO", "GAP"}
                            or not self._free_agency_has_future_contract_salary(player, int(season))
                        )
                    ):
                        continue
                    salary_num = parse_float(player.get(f"salary_{season}_num"))
                    salary_text_amount = parse_amount_like(player.get(f"salary_{season}_text"))
                    if (salary_num is not None and abs(float(salary_num)) > 0) or (
                        salary_text_amount is not None and abs(float(salary_text_amount)) > 0
                    ):
                        has_active_salary = True
                        break
                if has_active_salary:
                    active_profile_ids.append(int(profile_id))
        if not active_profile_ids:
            return 0
        unique_ids = sorted(set(active_profile_ids))
        placeholders = ",".join("?" for _ in unique_ids)
        free_agent_rows = conn.execute(
            f"""
            SELECT id
            FROM free_agents
            WHERE profile_id IN ({placeholders})
                AND COALESCE(source, '') != ?
            """,
            (*unique_ids, FREE_AGENT_SOURCE_CAP_HOLD),
        ).fetchall()
        self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(
            conn,
            [row["id"] for row in free_agent_rows],
        )
        delete_cur = conn.execute(
            f"""
            DELETE FROM free_agents
            WHERE profile_id IN ({placeholders})
                AND COALESCE(source, '') != ?
            """,
            (*unique_ids, FREE_AGENT_SOURCE_CAP_HOLD),
        )
        return int(delete_cur.rowcount or 0)

    def _sync_cap_hold_free_agents(self, conn: sqlite3.Connection, settings: Dict[str, str]) -> int:
        timestamp = now_iso()
        if not parse_bool(settings.get("free_agency_mode")):
            rows = conn.execute("SELECT id FROM free_agents WHERE source = ?", (FREE_AGENT_SOURCE_CAP_HOLD,)).fetchall()
            self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, [row["id"] for row in rows])
            cur = conn.execute("DELETE FROM free_agents WHERE source = ?", (FREE_AGENT_SOURCE_CAP_HOLD,))
            return int(cur.rowcount or 0)

        current_year = parse_int(settings.get("current_year")) or 2025
        season = int(current_year)
        salary_cap = (
            parse_float(settings.get(f"salary_cap_{season}"))
            or parse_float(settings.get("salary_cap_2025"))
            or 0.0
        )
        valid_profile_ids: List[int] = []
        changed = 0
        teams_cur = conn.execute("SELECT id, code FROM teams ORDER BY code")
        for team in teams_cur.fetchall():
            team_id = int(team["id"])
            team_code = str(team["code"] or "").strip().upper()
            players = self._select_team_players(conn, team_id)
            self._attach_option_decisions(conn, players, team_id)
            for player in players:
                profile_id = parse_int(player.get("profile_id"))
                if profile_id is not None:
                    profile_status_row = conn.execute(
                        "SELECT profile_status FROM player_profiles WHERE id = ?",
                        (int(profile_id),),
                    ).fetchone()
                    if profile_status_row and is_unavailable_player_profile_status(profile_status_row["profile_status"]):
                        continue
                fa_type = self._cap_hold_free_agent_type(player, season)
                has_restricted_option = fa_type == FREE_AGENT_TYPE_RESTRICTED
                hold_amount = cap_hold_amount(player, season, settings, salary_cap)
                has_hold_marker = has_standard_cap_hold_marker(player, season)
                is_expiring_contract = self._free_agency_expiring_contract_without_next_year(
                    player,
                    int(current_year) - 1,
                    int(season),
                )
                if not has_restricted_option and hold_amount <= 0 and not has_hold_marker and not is_expiring_contract:
                    continue
                has_retained_rights = has_restricted_option or hold_amount > 0 or has_hold_marker

                player_id = parse_int(player.get("id"))
                if player_id is None:
                    continue
                if profile_id is None:
                    profile_id = self._ensure_profile_for_player(conn, player_id, timestamp)
                if profile_id is None:
                    continue
                name = str(player.get("name") or player.get("profile_name") or "Agente libre").strip() or "Agente libre"
                default_notes = (
                    f"Cap hold retenido por {team_code} para {season_label(season)}"
                    if has_retained_rights
                    else f"Contrato expirado tras {season_label(int(current_year) - 1)}"
                )
                synced_bird_rights = self._cap_hold_free_agent_bird_rights_code(player, season) if has_retained_rights else None
                synced_rights_team = team_code if has_retained_rights else None
                existing = conn.execute(
                    "SELECT id, notes, source FROM free_agents WHERE profile_id = ? LIMIT 1",
                    (int(profile_id),),
                ).fetchone()
                if existing and str(existing["source"] or "").strip() == FREE_AGENT_SOURCE_RENOUNCED_RIGHTS:
                    continue
                valid_profile_ids.append(int(profile_id))
                if existing:
                    cur = conn.execute(
                        """
                        UPDATE free_agents
                        SET name = ?,
                            position = ?,
                            bird_rights = ?,
                            rating = ?,
                            years_left = ?,
                            free_agent_type = ?,
                            source = ?,
                            rights_team_code = ?,
                            notes = CASE
                                WHEN notes IS NULL OR TRIM(notes) = '' OR notes LIKE 'Cap hold retenido por %'
                                    OR notes LIKE 'Contrato expirado tras %'
                                THEN ?
                                ELSE notes
                            END,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            name,
                            str(player.get("position") or "").strip() or None,
                            synced_bird_rights,
                            str(player.get("rating") or "").strip() or None,
                            normalize_bird_years(player.get("years_left")),
                            fa_type,
                            FREE_AGENT_SOURCE_CAP_HOLD,
                            synced_rights_team,
                            default_notes,
                            timestamp,
                            int(existing["id"]),
                        ),
                    )
                    changed += int(cur.rowcount or 0)
                    continue
                cur = conn.execute(
                    """
                    INSERT INTO free_agents (
                        profile_id, name, position, bird_rights, rating, years_left,
                        free_agent_type, source, rights_team_code, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(profile_id),
                        name,
                        str(player.get("position") or "").strip() or None,
                        synced_bird_rights,
                        str(player.get("rating") or "").strip() or None,
                        normalize_bird_years(player.get("years_left")),
                        fa_type,
                        FREE_AGENT_SOURCE_CAP_HOLD,
                        synced_rights_team,
                        default_notes,
                        timestamp,
                        timestamp,
                    ),
                )
                changed += int(cur.rowcount or 0)

        if valid_profile_ids:
            placeholders = ",".join("?" for _ in valid_profile_ids)
            rows = conn.execute(
                f"""
                SELECT id
                FROM free_agents
                WHERE source = ?
                    AND (
                        profile_id IS NULL
                        OR profile_id NOT IN ({placeholders})
                    )
                """,
                (FREE_AGENT_SOURCE_CAP_HOLD, *valid_profile_ids),
            ).fetchall()
            self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, [row["id"] for row in rows])
            cur = conn.execute(
                f"""
                DELETE FROM free_agents
                WHERE source = ?
                    AND (
                        profile_id IS NULL
                        OR profile_id NOT IN ({placeholders})
                    )
                """,
                (FREE_AGENT_SOURCE_CAP_HOLD, *valid_profile_ids),
            )
        else:
            rows = conn.execute("SELECT id FROM free_agents WHERE source = ?", (FREE_AGENT_SOURCE_CAP_HOLD,)).fetchall()
            self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, [row["id"] for row in rows])
            cur = conn.execute("DELETE FROM free_agents WHERE source = ?", (FREE_AGENT_SOURCE_CAP_HOLD,))
        changed += int(cur.rowcount or 0)
        changed += self._cleanup_active_contract_free_agents_conn(conn, int(current_year))
        return changed

    def _sync_uncontracted_profile_free_agents(self, conn: sqlite3.Connection) -> int:
        """Ensure canonical player profiles without a roster row are visible as free agents."""
        timestamp = now_iso()
        changed = 0
        rows = conn.execute(
            """
            SELECT id
            FROM free_agents
            WHERE source = ?
                AND profile_id IN (
                    SELECT DISTINCT profile_id
                    FROM players
                    WHERE profile_id IS NOT NULL
                )
            """,
            (FREE_AGENT_SOURCE_UNCONTRACTED_PROFILE,),
        ).fetchall()
        self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, [row["id"] for row in rows])
        cur = conn.execute(
            """
            DELETE FROM free_agents
            WHERE source = ?
                AND profile_id IN (
                    SELECT DISTINCT profile_id
                    FROM players
                    WHERE profile_id IS NOT NULL
                )
            """,
            (FREE_AGENT_SOURCE_UNCONTRACTED_PROFILE,),
        )
        changed += int(cur.rowcount or 0)

        cur = conn.execute(
            """
            INSERT INTO free_agents (
                profile_id, name, position, bird_rights, rating, years_left,
                free_agent_type, source, rights_team_code, agent, notes, created_at, updated_at
            )
            SELECT
                pp.id,
                pp.name,
                NULL,
                NULL,
                NULL,
                NULL,
                ?,
                ?,
                NULL,
                NULL,
                'Agente libre sin derechos Bird retenidos.',
                ?,
                ?
            FROM player_profiles pp
            LEFT JOIN players p ON p.profile_id = pp.id
            LEFT JOIN free_agents f ON f.profile_id = pp.id
            WHERE p.id IS NULL
                AND f.id IS NULL
                AND COALESCE(pp.profile_status, 'active') NOT IN (?, ?)
                AND TRIM(COALESCE(pp.name, '')) != ''
            """,
            (
                FREE_AGENT_TYPE_UNRESTRICTED,
                FREE_AGENT_SOURCE_UNCONTRACTED_PROFILE,
                timestamp,
                timestamp,
                PLAYER_PROFILE_STATUS_OUTSIDE_NBA,
                PLAYER_PROFILE_STATUS_RETIRED,
            ),
        )
        changed += int(cur.rowcount or 0)
        return changed

    def list_free_agents(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            try:
                with self._free_agents_sync_lock:
                    changed = self._player_identity_service().synchronize_generated_free_agents(
                        conn, settings
                    )["changed"]
                    if changed:
                        conn.commit()
            except sqlite3.OperationalError as exc:
                if "database is locked" not in str(exc).lower():
                    raise
                logger.warning("Free agent sync skipped: %s", exc)
                conn.rollback()
            cur = conn.execute(
                """
                SELECT
                    f.*,
                    pp.name AS profile_name,
                    pp.date_of_birth AS profile_date_of_birth,
                    pp.nationality AS profile_nationality,
                    pp.experience_years AS profile_experience_years,
                    pp.yos_source AS profile_yos_source,
                    pp.reference_image_url AS profile_reference_image_url,
                    pp.profile_notes AS profile_profile_notes,
                    pp.transaction_notes AS profile_transaction_notes,
                    pp.profile_status AS profile_status
                FROM free_agents f
                LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                WHERE COALESCE(pp.profile_status, 'active') NOT IN (?, ?)
                ORDER BY COALESCE(pp.name, f.name) COLLATE NOCASE, f.id
                """,
                (PLAYER_PROFILE_STATUS_OUTSIDE_NBA, PLAYER_PROFILE_STATUS_RETIRED),
            )
            free_agents = [self._merge_player_profile(row_to_dict(cur, row)) for row in cur.fetchall()]
            return self._attach_player_salary_history_conn(conn, free_agents)

    def _get_free_agent_conn(self, conn: sqlite3.Connection, free_agent_id: int) -> Optional[Dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT
                f.*,
                pp.name AS profile_name,
                pp.date_of_birth AS profile_date_of_birth,
                pp.nationality AS profile_nationality,
                pp.experience_years AS profile_experience_years,
                pp.yos_source AS profile_yos_source,
                pp.reference_image_url AS profile_reference_image_url,
                pp.profile_notes AS profile_profile_notes,
                pp.transaction_notes AS profile_transaction_notes,
                pp.profile_status AS profile_status
            FROM free_agents f
            LEFT JOIN player_profiles pp ON pp.id = f.profile_id
            WHERE f.id = ?
            """,
            (free_agent_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        if is_unavailable_player_profile_status(row["profile_status"]):
            return None
        free_agent = self._merge_player_profile(row_to_dict(cur, row))
        enriched = self._attach_player_salary_history_conn(conn, [free_agent])
        return enriched[0] if enriched else free_agent

    def get_free_agent(self, free_agent_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            return self._get_free_agent_conn(conn, int(free_agent_id))

    def create_free_agent(self, payload: Dict[str, Any]) -> Optional[int]:
        name = str(payload.get("name") or "").strip()
        if not name:
            return None
        now = now_iso()
        with self.connect() as conn:
            profile_id = self._resolve_profile_for_new_row(
                conn,
                payload,
                name=name,
                timestamp=now,
            )
            cur = conn.execute(
                """
                INSERT INTO free_agents (
                    profile_id, name, position, bird_rights, rating, years_left, free_agent_type, agent, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    name,
                    str(payload.get("position") or "").strip() or None,
                    str(payload.get("bird_rights") or "").strip() or None,
                    str(payload.get("rating") or "").strip() or None,
                    normalize_bird_years(payload.get("years_left")),
                    normalize_free_agent_type(payload.get("free_agent_type")),
                    str(payload.get("agent") or "").strip() or None,
                    str(payload.get("notes") or "").strip() or None,
                    now,
                    now,
                ),
            )
            self._record_player_transaction(
                conn,
                profile_id,
                "free_agent",
                "Añadido a agentes libres",
                free_agent_id=int(cur.lastrowid),
                details={"player_name": name},
                created_at=now,
            )
            conn.commit()
            return int(cur.lastrowid)

    def bulk_create_free_agents(self, raw_names: Any) -> Dict[str, Any]:
        if isinstance(raw_names, list):
            lines = [str(item or "").strip() for item in raw_names]
        else:
            lines = str(raw_names or "").splitlines()
        cleaned: List[Dict[str, Any]] = []
        seen_input: set[str] = set()
        skipped: List[Dict[str, Any]] = []
        for line_number, raw in enumerate(lines, start=1):
            name = re.sub(r"\s+", " ", str(raw or "").strip())
            if not name:
                continue
            key = name.casefold()
            if key in seen_input:
                skipped.append({"line": line_number, "name": name, "reason": "duplicado en el texto"})
                continue
            seen_input.add(key)
            cleaned.append({"line": line_number, "name": name})
        if len(cleaned) > 1000:
            raise ValueError("too_many_names")

        timestamp = now_iso()
        created: List[Dict[str, Any]] = []
        with self.connect() as conn:
            for item in cleaned:
                name = item["name"]
                existing_free_agent = conn.execute(
                    """
                    SELECT f.id
                    FROM free_agents f
                    LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                    WHERE lower(trim(COALESCE(pp.name, f.name))) = lower(trim(?))
                        OR lower(trim(f.name)) = lower(trim(?))
                    LIMIT 1
                    """,
                    (name, name),
                ).fetchone()
                if existing_free_agent:
                    skipped.append({"line": item["line"], "name": name, "reason": "ya existe en agentes libres"})
                    continue
                active_player = conn.execute(
                    """
                    SELECT p.id
                    FROM players p
                    LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    WHERE lower(trim(COALESCE(pp.name, p.name))) = lower(trim(?))
                        OR lower(trim(p.name)) = lower(trim(?))
                    LIMIT 1
                    """,
                    (name, name),
                ).fetchone()
                if active_player:
                    skipped.append({"line": item["line"], "name": name, "reason": "ya tiene contrato activo"})
                    continue

                profile_id = self._find_profile_id(conn, name=name)
                if profile_id is None:
                    profile_id = self._create_player_profile(conn, name, timestamp=timestamp)
                cur = conn.execute(
                    """
                    INSERT INTO free_agents (
                        profile_id, name, position, bird_rights, rating, years_left,
                        free_agent_type, source, agent, notes, created_at, updated_at
                    ) VALUES (?, ?, NULL, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (profile_id, name, FREE_AGENT_TYPE_UNRESTRICTED, timestamp, timestamp),
                )
                free_agent_id = int(cur.lastrowid)
                created.append({"id": free_agent_id, "name": name, "line": item["line"]})
                self._record_player_transaction(
                    conn,
                    profile_id,
                    "free_agent",
                    "Añadido a agentes libres",
                    free_agent_id=free_agent_id,
                    details={"player_name": name, "bulk_import": True},
                    created_at=timestamp,
                )
            conn.commit()
        return {
            "created_count": len(created),
            "skipped_count": len(skipped),
            "created": created,
            "skipped": skipped,
        }

    def _free_agent_agent_import_records_from_rows(self, rows: List[List[str]]) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        records: List[Dict[str, Any]] = []
        first_row_index: Optional[int] = None
        for index, row in enumerate(rows):
            if any(str(cell or "").strip() for cell in row):
                first_row_index = index
                break
        if first_row_index is None:
            return {
                "ok": False,
                "errors": [{"line": None, "message": "El archivo no tiene filas con datos."}],
                "records": [],
                "summary": {"record_count": 0, "changed_count": 0, "unchanged_count": 0, "new_agent_count": 0},
                "new_agents": [],
            }

        header = [normalize_import_text(cell) for cell in rows[first_row_index]]
        player_header_keys = {"player", "player_name", "jugador", "nombre", "name"}
        agent_header_keys = {"agent", "agente", "rep", "representante", "representante_jugador"}
        player_col = next((idx for idx, value in enumerate(header) if value in player_header_keys), None)
        agent_col = next((idx for idx, value in enumerate(header) if value in agent_header_keys), None)
        has_header = player_col is not None and agent_col is not None
        if not has_header:
            player_col = 0
            agent_col = 1
            data_start = first_row_index
        else:
            data_start = first_row_index + 1

        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            changed = self._player_identity_service().synchronize_generated_free_agents(
                conn, settings
            )["changed"]
            if changed:
                conn.commit()
            cur = conn.execute(
                """
                SELECT f.id, COALESCE(pp.name, f.name) AS name, f.agent
                FROM free_agents f
                LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                ORDER BY COALESCE(pp.name, f.name) COLLATE NOCASE, f.id
                """
            )
            free_agents = [row_to_dict(cur, row) for row in cur.fetchall()]
            settings_row = conn.execute("SELECT value FROM app_settings WHERE key = 'free_agent_reps'").fetchone()

        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for free_agent in free_agents:
            key = normalize_import_text(free_agent.get("name"))
            if not key:
                continue
            by_name.setdefault(key, []).append(free_agent)

        seen_free_agent_ids: Dict[int, int] = {}
        for row_index in range(data_start, len(rows)):
            row = rows[row_index]
            line_number = row_index + 1
            if not any(str(cell or "").strip() for cell in row):
                continue
            player_name = str(row[player_col] if player_col is not None and player_col < len(row) else "").strip()
            agent_name = re.sub(r"\s+", " ", str(row[agent_col] if agent_col is not None and agent_col < len(row) else "").strip())
            if not player_name and not agent_name:
                continue
            if not player_name or not agent_name:
                errors.append({"line": line_number, "message": "Cada fila debe tener jugador y agente."})
                continue
            matches = by_name.get(normalize_import_text(player_name), [])
            if not matches:
                errors.append({"line": line_number, "message": f"No se encontró agente libre: {player_name}."})
                continue
            if len(matches) > 1:
                errors.append({"line": line_number, "message": f"Nombre ambiguo: {player_name}. Hay más de un agente libre con ese nombre."})
                continue
            free_agent = matches[0]
            free_agent_id = int(free_agent["id"])
            if free_agent_id in seen_free_agent_ids:
                errors.append(
                    {
                        "line": line_number,
                        "message": f"Jugador duplicado en el archivo: {player_name} ya apareció en la línea {seen_free_agent_ids[free_agent_id]}.",
                    }
                )
                continue
            seen_free_agent_ids[free_agent_id] = line_number
            current_agent = str(free_agent.get("agent") or "").strip()
            records.append(
                {
                    "line": line_number,
                    "free_agent_id": free_agent_id,
                    "player_name": str(free_agent.get("name") or player_name).strip(),
                    "input_player_name": player_name,
                    "current_agent": current_agent,
                    "agent_name": agent_name,
                    "changed": current_agent.casefold() != agent_name.casefold(),
                }
            )

        existing_reps: List[str] = []
        if settings_row and settings_row["value"]:
            try:
                parsed_reps = json.loads(str(settings_row["value"]))
                if isinstance(parsed_reps, list):
                    existing_reps = [str(rep or "").strip() for rep in parsed_reps if str(rep or "").strip()]
            except json.JSONDecodeError:
                existing_reps = []
        known_reps = {rep.casefold() for rep in existing_reps}
        new_agents: List[str] = []
        for record in records:
            agent_name = str(record.get("agent_name") or "").strip()
            key = agent_name.casefold()
            if agent_name and key not in known_reps:
                known_reps.add(key)
                new_agents.append(agent_name)

        changed_count = sum(1 for record in records if record.get("changed"))
        summary = {
            "record_count": len(records),
            "changed_count": changed_count,
            "unchanged_count": len(records) - changed_count,
            "new_agent_count": len(new_agents),
        }
        return {
            "ok": not errors,
            "errors": errors,
            "records": records,
            "summary": summary,
            "new_agents": new_agents,
        }

    def preview_free_agent_agent_import(self, rows: List[List[str]]) -> Dict[str, Any]:
        return self._free_agent_agent_import_records_from_rows(rows)

    def apply_free_agent_agent_import(self, records_payload: Any) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        timestamp = now_iso()
        changed_count = 0
        unchanged_count = 0
        imported_agents: List[str] = []
        with self.connect() as conn:
            existing_reps_row = conn.execute("SELECT value FROM app_settings WHERE key = 'free_agent_reps'").fetchone()
            try:
                existing_reps_raw = json.loads(str(existing_reps_row["value"])) if existing_reps_row else []
            except json.JSONDecodeError:
                existing_reps_raw = []
            existing_reps = [
                str(rep or "").strip()
                for rep in (existing_reps_raw if isinstance(existing_reps_raw, list) else [])
                if str(rep or "").strip()
            ]
            known_reps = {rep.casefold() for rep in existing_reps}
            next_reps = list(existing_reps)

            for raw_record in records_payload:
                if not isinstance(raw_record, dict):
                    raise ValueError("invalid_records")
                free_agent_id = parse_int(raw_record.get("free_agent_id"))
                agent_name = re.sub(r"\s+", " ", str(raw_record.get("agent_name") or "").strip())
                if free_agent_id is None or not agent_name:
                    raise ValueError("invalid_records")
                row = conn.execute(
                    """
                    SELECT id, agent
                    FROM free_agents
                    WHERE id = ?
                    """,
                    (free_agent_id,),
                ).fetchone()
                if not row:
                    raise ValueError("invalid_records")
                current_agent = str(row["agent"] or "").strip()
                cur = conn.execute(
                    "UPDATE free_agents SET agent = ?, updated_at = ? WHERE id = ?",
                    (agent_name, timestamp, free_agent_id),
                )
                if cur.rowcount:
                    if current_agent.casefold() == agent_name.casefold():
                        unchanged_count += 1
                    else:
                        changed_count += 1
                key = agent_name.casefold()
                if key not in known_reps:
                    known_reps.add(key)
                    next_reps.append(agent_name)
                    imported_agents.append(agent_name)

            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('free_agent_reps', ?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (json.dumps(next_reps, ensure_ascii=False), timestamp),
            )
            conn.commit()
        return {
            "record_count": changed_count + unchanged_count,
            "changed_count": changed_count,
            "unchanged_count": unchanged_count,
            "new_agents": imported_agents,
            "free_agent_reps": next_reps,
        }

    def update_free_agent(self, free_agent_id: int, payload: Dict[str, Any]) -> bool:
        fields = sorted(FREE_AGENT_UPDATE_FIELDS)
        assigns = []
        vals: List[Any] = []
        for field in fields:
            if field not in payload:
                continue
            if field == "name":
                value = str(payload.get(field) or "").strip()
                if not value:
                    return False
                assigns.append("name = ?")
                vals.append(value)
            elif field == "years_left":
                assigns.append("years_left = ?")
                vals.append(normalize_bird_years(payload.get(field)))
            elif field == "free_agent_type":
                assigns.append("free_agent_type = ?")
                vals.append(normalize_free_agent_type(payload.get(field)))
            else:
                assigns.append(f"{field} = ?")
                vals.append(str(payload.get(field) or "").strip() or None)
        if not assigns:
            return False
        timestamp = now_iso()
        assigns.append("updated_at = ?")
        vals.append(timestamp)
        vals.append(free_agent_id)
        with self.connect() as conn:
            profile_id: Optional[int] = None
            if "name" in payload:
                row = conn.execute("SELECT profile_id, name FROM free_agents WHERE id = ?", (free_agent_id,)).fetchone()
                if not row:
                    return False
                profile_id = parse_int(row["profile_id"])
                if profile_id is None:
                    profile_id = self._create_player_profile(conn, payload.get("name") or row["name"], timestamp=timestamp)
                    conn.execute("UPDATE free_agents SET profile_id = ? WHERE id = ?", (profile_id, free_agent_id))
            cur = conn.execute(f"UPDATE free_agents SET {', '.join(assigns)} WHERE id = ?", vals)
            if profile_id is not None:
                conn.execute(
                    "UPDATE player_profiles SET name = ?, updated_at = ? WHERE id = ?",
                    (str(payload.get("name") or "").strip() or "New Player", timestamp, profile_id),
                )
            conn.commit()
            return cur.rowcount > 0

    def _cleanup_gm_minimum_targets_for_free_agent_ids_conn(
        self,
        conn: sqlite3.Connection,
        free_agent_ids: Any,
    ) -> int:
        parsed_ids = sorted({
            int(parsed_id)
            for parsed_id in (parse_int(value) for value in (free_agent_ids or []))
            if parsed_id is not None and parsed_id > 0
        })
        if not parsed_ids:
            return 0
        placeholders = ",".join("?" for _ in parsed_ids)
        user_rows = conn.execute(
            f"""
            SELECT DISTINCT user_id
            FROM gm_minimum_targets
            WHERE free_agent_id IN ({placeholders})
            """,
            tuple(parsed_ids),
        ).fetchall()
        cur = conn.execute(
            f"DELETE FROM gm_minimum_targets WHERE free_agent_id IN ({placeholders})",
            tuple(parsed_ids),
        )
        deleted = int(cur.rowcount or 0)
        if deleted:
            timestamp = now_iso()
            for row in user_rows:
                user_id = parse_int(row["user_id"])
                if user_id is None:
                    continue
                conn.execute(
                    "UPDATE gm_minimum_target_status SET updated_at = ? WHERE user_id = ?",
                    (timestamp, int(user_id)),
                )
        return deleted

    def delete_free_agent(self, free_agent_id: int, record_transaction: bool = True) -> bool:
        with self.connect() as conn:
            agent = conn.execute(
                """
                SELECT f.profile_id, COALESCE(pp.name, f.name) AS name
                FROM free_agents f
                LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                WHERE f.id = ?
                """,
                (free_agent_id,),
            ).fetchone()
            self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, [free_agent_id])
            cur = conn.execute("DELETE FROM free_agents WHERE id = ?", (free_agent_id,))
            if record_transaction and cur.rowcount and agent:
                self._record_player_transaction(
                    conn,
                    agent["profile_id"],
                    "delete",
                    "Eliminado de agentes libres",
                    free_agent_id=free_agent_id,
                    details={"player_name": agent["name"]},
                )
            conn.commit()
            return cur.rowcount > 0

    def _approved_option_decision_conn(
        self,
        conn: sqlite3.Connection,
        player_id: Any,
        option_field: str,
    ) -> Optional[sqlite3.Row]:
        parsed_player_id = parse_int(player_id)
        field = str(option_field or "").strip()
        if parsed_player_id is None or not re.fullmatch(r"option_(20\d{2})", field):
            return None
        return conn.execute(
            """
            SELECT option_value, action, status
            FROM gm_option_requests
            WHERE player_id = ?
              AND option_field = ?
              AND status = 'approved'
            ORDER BY COALESCE(decided_at, updated_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (int(parsed_player_id), field),
        ).fetchone()

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

    def _remove_retained_rights_player_row_for_signing(
        self,
        conn: sqlite3.Connection,
        player: sqlite3.Row,
        *,
        free_agent_id: int,
        signing_team_code: str,
        player_name: str,
    ) -> None:
        profile_id = parse_int(player["profile_id"])
        old_player_id = parse_int(player["id"])
        old_team_code = normalize_team_code(player["team_code"])
        rights_by_season: Dict[str, str] = {}
        for season in PLAYER_CONTRACT_SEASONS:
            salary_marker = str(player[f"salary_{season}_text"] or "").strip().upper()
            option_marker = str(player[f"option_{season}"] or "").strip().upper()
            marker = salary_marker or option_marker
            if marker not in {"NB", "EB", "FB", "QO", "GAP"} and option_marker in {"QO", "GAP"}:
                marker = option_marker
            if marker in {"NB", "EB", "FB", "QO", "GAP"}:
                rights_by_season[str(season)] = marker

        conn.execute("DELETE FROM players WHERE id = ?", (old_player_id,))
        self._record_player_transaction(
            conn,
            profile_id,
            "rights_removed",
            f"Derechos eliminados por firma con {signing_team_code}",
            player_id=old_player_id,
            free_agent_id=free_agent_id,
            team_code=old_team_code,
            from_team_code=old_team_code,
            to_team_code=signing_team_code,
            details={
                "player_name": player_name,
                "rights_by_season": rights_by_season,
                "reason": "free_agent_signed_elsewhere",
            },
        )

    def _delete_free_agent_entries_for_signed_profile_conn(
        self,
        conn: sqlite3.Connection,
        *,
        free_agent_id: Optional[int],
        profile_id: Optional[int],
    ) -> int:
        deleted = 0
        parsed_free_agent_id = parse_int(free_agent_id)
        parsed_profile_id = parse_int(profile_id)
        free_agent_ids: List[int] = []
        if parsed_free_agent_id is not None:
            free_agent_ids.append(int(parsed_free_agent_id))
        if parsed_profile_id is not None:
            rows = conn.execute(
                "SELECT id FROM free_agents WHERE profile_id = ?",
                (int(parsed_profile_id),),
            ).fetchall()
            free_agent_ids.extend(int(row["id"]) for row in rows)
        self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, free_agent_ids)
        if parsed_free_agent_id is not None:
            cur = conn.execute("DELETE FROM free_agents WHERE id = ?", (int(parsed_free_agent_id),))
            deleted += int(cur.rowcount or 0)
        if parsed_profile_id is not None:
            cur = conn.execute("DELETE FROM free_agents WHERE profile_id = ?", (int(parsed_profile_id),))
            deleted += int(cur.rowcount or 0)
        return deleted

    def sign_free_agent(
        self,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[int]:
        if conn is not None:
            return self._sign_free_agent_conn(conn, free_agent_id, team_code, payload)
        with self.transaction("IMMEDIATE") as owned_conn:
            return self._sign_free_agent_conn(owned_conn, free_agent_id, team_code, payload)

    def _sign_free_agent_conn(
        self,
        conn: sqlite3.Connection,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
    ) -> Optional[int]:
        agent = self._get_free_agent_conn(conn, free_agent_id)
        if not agent:
            return None
        player_payload = dict(payload)
        player_payload["name"] = str(player_payload.get("name") or agent.get("name") or "").strip() or "New Player"
        if agent.get("profile_id") is not None and player_payload.get("profile_id") in (None, ""):
            player_payload["profile_id"] = agent.get("profile_id")
        for key in ["position", "bird_rights", "rating", "years_left", "notes"]:
            if player_payload.get(key) in (None, "") and agent.get(key) not in (None, ""):
                player_payload[key] = agent.get(key)
        player_payload.setdefault("signed_as_free_agent", True)

        profile_id = parse_int(player_payload.get("profile_id")) or parse_int(agent.get("profile_id"))
        normalized_team_code = normalize_team_code(team_code)
        if profile_id is not None:
            profile_status_row = conn.execute(
                "SELECT profile_status FROM player_profiles WHERE id = ?",
                (int(profile_id),),
            ).fetchone()
            if profile_status_row and is_unavailable_player_profile_status(profile_status_row["profile_status"]):
                raise ValueError("profile_unavailable")
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}
            current_year = parse_int(settings.get("current_year")) or PLAYER_CONTRACT_SEASONS[0]
            active_rows = conn.execute(
                """
                SELECT p.*, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.profile_id = ?
                ORDER BY p.id
                """,
                (int(profile_id),),
            ).fetchall()
            if active_rows:
                same_team_row = next(
                    (
                        row for row in active_rows
                        if normalize_team_code(row["team_code"]) == normalized_team_code
                    ),
                    None,
                )
                if not same_team_row:
                    blocking_rows = [
                        row for row in active_rows
                        if not self._player_row_is_retained_rights_only(row, int(current_year), conn)
                    ]
                    if blocking_rows:
                        raise ValueError("profile_has_active_contract")
                    for row in active_rows:
                        self._remove_retained_rights_player_row_for_signing(
                            conn,
                            row,
                            free_agent_id=free_agent_id,
                            signing_team_code=normalized_team_code,
                            player_name=player_payload["name"],
                        )
                else:
                    return self._apply_free_agent_contract_to_active_player(
                        conn,
                        int(same_team_row["id"]),
                        free_agent_id,
                        normalized_team_code,
                        agent,
                        player_payload,
                        commit=False,
                    )

        rights_team_code = normalize_team_code(agent.get("rights_team_code"))
        if not rights_team_code or rights_team_code != normalized_team_code:
            player_payload["years_left"] = "0"

        player_id = self._create_player_conn(conn, team_code, player_payload)
        if not player_id:
            return None
        profile_id = self._find_profile_id(conn, player_id=player_id) or parse_int(agent.get("profile_id"))
        self._record_player_transaction(
            conn,
            profile_id,
            "sign",
            f"Firmado por {team_code.upper()}",
            player_id=player_id,
            free_agent_id=free_agent_id,
            team_code=team_code,
            to_team_code=team_code,
            details={"player_name": player_payload["name"]},
        )
        self._delete_free_agent_entries_for_signed_profile_conn(
            conn,
            free_agent_id=free_agent_id,
            profile_id=profile_id,
        )
        return player_id

    def _apply_free_agent_contract_to_active_player(
        self,
        conn: sqlite3.Connection,
        player_id: int,
        free_agent_id: int,
        team_code: str,
        agent: Dict[str, Any],
        player_payload: Dict[str, Any],
        *,
        commit: bool = True,
    ) -> Optional[int]:
        player = conn.execute(
            """
            SELECT p.id, p.profile_id, COALESCE(pp.name, p.name) AS player_name,
                   pp.profile_status, t.code AS team_code
            FROM players p
            LEFT JOIN player_profiles pp ON pp.id = p.profile_id
            JOIN teams t ON t.id = p.team_id
            WHERE p.id = ?
            """,
            (player_id,),
        ).fetchone()
        if not player:
            return None
        if is_unavailable_player_profile_status(player["profile_status"]):
            raise ValueError("profile_unavailable")
        if normalize_team_code(player["team_code"]) != normalize_team_code(team_code):
            raise ValueError("profile_has_active_contract")

        settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}
        current_year = parse_int(settings.get("current_year")) or PLAYER_CONTRACT_SEASONS[0]
        touched_years = [
            season for season in PLAYER_CONTRACT_SEASONS
            if f"salary_{season}_text" in player_payload or f"option_{season}" in player_payload
        ]
        start_year = min(touched_years) if touched_years else int(current_year)
        timestamp = now_iso()
        assignments: List[str] = []
        values: List[Any] = []

        scalar_fields = [
            "name",
            "bird_rights",
            "rating",
            "position",
            "years_left",
            "notes",
            "reference_image_url",
            "profile_notes",
        ]
        for field in scalar_fields:
            if field not in player_payload:
                continue
            assignments.append(f"{field} = ?")
            if field == "years_left":
                values.append(normalize_bird_years(player_payload.get(field)))
            else:
                values.append(player_payload.get(field))

        if "experience_years" in player_payload:
            assignments.append("experience_years = ?")
            values.append(normalize_experience_years(player_payload.get("experience_years")))

        assignments.append("signed_as_free_agent = ?")
        values.append(1 if parse_bool(player_payload.get("signed_as_free_agent", True)) else 0)

        if "bird_rights" in player_payload:
            assignments.append("is_two_way = ?")
            values.append(1 if str(player_payload.get("bird_rights") or "").upper() == "TW" else 0)

        for season in PLAYER_CONTRACT_SEASONS:
            if season < int(start_year):
                continue
            salary_field = f"salary_{season}_text"
            salary_value = player_payload.get(salary_field) if salary_field in player_payload else None
            assignments.append(f"{salary_field} = ?")
            values.append(salary_value)
            assignments.append(f"salary_{season}_num = ?")
            values.append(parse_salary_amount(salary_value))

            guaranteed_field = f"salary_{season}_guaranteed_text"
            assignments.append(f"{guaranteed_field} = ?")
            values.append(player_payload.get(guaranteed_field) if guaranteed_field in player_payload else None)

            note_text_field = f"salary_{season}_note_text"
            assignments.append(f"{note_text_field} = ?")
            values.append(player_payload.get(note_text_field) if note_text_field in player_payload else None)

            option_field = f"option_{season}"
            assignments.append(f"{option_field} = ?")
            values.append(player_payload.get(option_field) if option_field in player_payload else None)

            for bool_suffix in ("provisional", "partially_guaranteed", "note"):
                bool_field = f"salary_{season}_{bool_suffix}"
                assignments.append(f"{bool_field} = ?")
                values.append(1 if parse_bool(player_payload.get(bool_field)) else 0)

        assignments.append("updated_at = ?")
        values.append(timestamp)
        values.append(player_id)
        conn.execute(
            f"UPDATE players SET {', '.join(assignments)} WHERE id = ?",
            values,
        )

        profile_updates: List[str] = []
        profile_values: List[Any] = []
        if "name" in player_payload:
            profile_updates.append("name = ?")
            profile_values.append(str(player_payload.get("name") or "").strip() or "New Player")
        if "experience_years" in player_payload:
            profile_updates.append("experience_years = COALESCE(?, experience_years)")
            profile_values.append(normalize_experience_years(player_payload.get("experience_years")))
        if "reference_image_url" in player_payload:
            profile_updates.append("reference_image_url = COALESCE(NULLIF(?, ''), reference_image_url)")
            profile_values.append(str(player_payload.get("reference_image_url") or "").strip())
        if "profile_notes" in player_payload:
            profile_updates.append("profile_notes = COALESCE(?, profile_notes)")
            profile_values.append(player_payload.get("profile_notes"))
        if profile_updates and player["profile_id"] is not None:
            profile_updates.append("updated_at = ?")
            profile_values.append(timestamp)
            profile_values.append(int(player["profile_id"]))
            conn.execute(
                f"UPDATE player_profiles SET {', '.join(profile_updates)} WHERE id = ?",
                profile_values,
            )

        salary_by_season = {
            str(season): player_payload.get(f"salary_{season}_text")
            for season in PLAYER_CONTRACT_SEASONS
            if player_payload.get(f"salary_{season}_text") not in (None, "")
        }
        player_name = str(player_payload.get("name") or player["player_name"] or agent.get("name") or "Jugador").strip()
        self._record_player_transaction(
            conn,
            player["profile_id"],
            "renew",
            f"Renovado por {team_code.upper()}",
            player_id=player_id,
            free_agent_id=free_agent_id,
            team_code=team_code,
            to_team_code=team_code,
            details={
                "player_name": player_name,
                "contract_type": player_payload.get("bird_rights"),
                "salary_by_season": salary_by_season,
            },
            created_at=timestamp,
        )
        self._delete_free_agent_entries_for_signed_profile_conn(
            conn,
            free_agent_id=free_agent_id,
            profile_id=parse_int(player["profile_id"]),
        )
        if commit:
            conn.commit()
        return player_id

    def cut_player(self, player_id: int, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            now = now_iso()
            result = self._waive_player_row_conn(conn, int(player_id), timestamp=now, cut_options=payload)
            if not result:
                return None
            team_code = str(result.get("team_code") or "").upper()
            self._record_player_transaction(
                conn,
                result.get("profile_id"),
                "cut",
                f"Cortado por {team_code}",
                player_id=player_id,
                free_agent_id=parse_int(result.get("free_agent_id")),
                dead_contract_id=parse_int(result.get("dead_contract_id")),
                team_code=team_code,
                from_team_code=team_code,
                details={
                    "player_name": result.get("name"),
                    "waiver_player_id": result.get("waiver_id"),
                    "waiver_expires_at": result.get("waiver_expires_at"),
                },
                created_at=now,
            )
            conn.commit()
            return {
                "team_code": team_code,
                "team_name": result.get("team_name"),
                "player_name": result.get("name"),
                "profile_id": result.get("profile_id"),
                "reference_image_url": result.get("reference_image_url"),
                "dead_contract_id": result.get("dead_contract_id"),
                "free_agent_id": result.get("free_agent_id"),
                "waiver": bool(result.get("waiver")),
                "waiver_id": result.get("waiver_id"),
                "waiver_expires_at": result.get("waiver_expires_at"),
            }

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

    def _pick_actual_owner(self, asset_row: Dict[str, Any], source_team_code: str) -> str:
        if normalize_pick_type(asset_row.get("draft_pick_type")) == "acquired":
            return normalize_team_code(asset_row.get("original_owner")) or source_team_code
        return source_team_code

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
        conn.execute(
            """
            INSERT INTO team_move_logs (
                team_id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                season_year,
                normalize_trade_bucket(bucket),
                int(delta),
                source_type,
                source_ref,
                note,
                json.dumps(details or {}, ensure_ascii=True),
                now_iso(),
            ),
        )

    def _insert_trade_move_logs(
        self,
        conn: sqlite3.Connection,
        *,
        team_id: int,
        season_year: int,
        requested_bucket: str,
        move_count: int,
        source_ref: Optional[str],
        note: Optional[str],
        details: Optional[Dict[str, Any]],
        settings: Dict[str, str],
    ) -> None:
        remaining = max(0, int(move_count or 0))
        if not remaining:
            return
        bucket_key = normalize_trade_bucket(requested_bucket)
        allocations: List[tuple[str, int]] = []
        if bucket_key == "post30":
            move_summary = self._team_move_summary(conn, int(team_id), int(season_year), settings)
            pre_remaining = max(0, parse_int(move_summary.get("remaining_pre30")) or 0)
            pre_delta = min(remaining, pre_remaining)
            if pre_delta:
                allocations.append(("pre30", pre_delta))
                remaining -= pre_delta
            if remaining:
                allocations.append(("post30", remaining))
        else:
            allocations.append(("pre30", remaining))

        for allocated_bucket, delta in allocations:
            allocated_details = {
                **(details or {}),
                "requested_bucket": bucket_key,
                "allocated_bucket": allocated_bucket,
            }
            self._upsert_team_move_log(
                conn,
                team_id=int(team_id),
                season_year=int(season_year),
                bucket=allocated_bucket,
                delta=int(delta),
                source_type="trade",
                source_ref=source_ref,
                note=note,
                details=allocated_details,
            )

    def adjust_team_move_remaining(
        self,
        team_code: str,
        season_year: int,
        bucket: str,
        target_remaining: int,
        actor_note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        bucket_key = normalize_trade_bucket(bucket)
        target_remaining = max(0, int(target_remaining))
        with self.connect() as conn:
            team = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            move_summary = self._team_move_summary(conn, int(team["id"]), int(season_year), settings)
            limit = int(move_summary[f"limit_{bucket_key}"])
            current_remaining = int(move_summary[f"remaining_{bucket_key}"])
            target_used = limit - target_remaining
            current_used = limit - current_remaining
            delta = target_used - current_used
            if delta == 0:
                return {
                    "team_code": team["code"],
                    "bucket": bucket_key,
                    "remaining": current_remaining,
                    "delta": 0,
                }
            self._upsert_team_move_log(
                conn,
                team_id=int(team["id"]),
                season_year=int(season_year),
                bucket=bucket_key,
                delta=int(delta),
                source_type="manual_adjustment",
                source_ref=None,
                note=actor_note or "Manual adjustment",
                details={"target_remaining": target_remaining},
            )
            conn.commit()
            refreshed = self._team_move_summary(conn, int(team["id"]), int(season_year), settings)
            return {
                "team_code": team["code"],
                "bucket": bucket_key,
                "remaining": int(refreshed[f"remaining_{bucket_key}"]),
                "delta": int(delta),
            }

    def _clean_trade_ids(self, values: Any) -> List[int]:
        if not isinstance(values, list):
            return []
        out: List[int] = []
        seen: set[int] = set()
        for value in values:
            parsed = parse_int(str(value))
            if parsed is None or parsed <= 0 or parsed in seen:
                continue
            seen.add(parsed)
            out.append(parsed)
        return out

    def _trade_machine_season(self, payload: Dict[str, Any], settings: Dict[str, str]) -> int:
        current_year = parse_int(settings.get("current_year")) or 2025
        if current_year < PLAYER_CONTRACT_MIN_YEAR or current_year > PLAYER_CONTRACT_MAX_START_YEAR:
            current_year = 2025
        season = parse_int(payload.get("season") or payload.get("season_start") or payload.get("seasonStart"))
        if season is None:
            season = current_year
        return min(PLAYER_CONTRACT_MAX_YEAR, max(PLAYER_CONTRACT_MIN_YEAR, season))

    def _trade_machine_thresholds(self, settings: Dict[str, str], season: int) -> Dict[str, float]:
        salary_cap = (
            parse_float(settings.get(f"salary_cap_{season}"))
            or parse_float(settings.get("salary_cap_2025"))
            or 154_647_000.0
        )
        luxury_cap = salary_cap * 1.215
        first_apron = (
            parse_float(settings.get(f"first_apron_{season}"))
            or parse_float(settings.get("first_apron"))
            or 195_945_000.0
        )
        second_apron = (
            parse_float(settings.get(f"second_apron_{season}"))
            or parse_float(settings.get("second_apron"))
            or 207_824_000.0
        )
        return {
            "salaryCap": salary_cap,
            "salaryFloor": salary_floor_for_season(settings, season, salary_cap),
            "luxuryCap": luxury_cap,
            "firstApron": first_apron,
            "secondApron": second_apron,
        }

    def _trade_machine_roster_limits(self, settings: Dict[str, str]) -> Dict[str, int]:
        standard_min = settings_int(settings, "roster_standard_min", ROSTER_STANDARD_MIN_DEFAULT)
        standard_max = max(standard_min, settings_int(settings, "roster_standard_max", ROSTER_STANDARD_MAX_DEFAULT))
        offseason_max = max(standard_max, settings_int(settings, "roster_standard_offseason_max", ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT))
        two_way_min = settings_int(settings, "roster_two_way_min", ROSTER_TWO_WAY_MIN_DEFAULT)
        two_way_max = max(two_way_min, settings_int(settings, "roster_two_way_max", ROSTER_TWO_WAY_MAX_DEFAULT))
        return {
            "standardMin": max(0, standard_min),
            "standardMax": max(0, standard_max),
            "standardOffseasonMax": max(0, offseason_max),
            "twoWayMin": max(0, two_way_min),
            "twoWayMax": max(0, two_way_max),
        }

    def _trade_machine_balance_snapshot(self, thresholds: Dict[str, float], cap_figure: float, apron_figure: Optional[float] = None) -> List[Dict[str, Any]]:
        apron = cap_figure if apron_figure is None else apron_figure
        return [
            {"key": "cap", "label": "CAP", "value": thresholds["salaryCap"] - cap_figure},
            {"key": "tax", "label": "Impuesto lujo", "value": thresholds["luxuryCap"] - cap_figure},
            {"key": "first_apron", "label": "1er apron", "value": thresholds["firstApron"] - apron},
            {"key": "second_apron", "label": "2do apron", "value": thresholds["secondApron"] - apron},
        ]

    def _trade_machine_team_balances(
        self,
        team_data: Dict[str, Any],
        season: int,
        salary_cap: float,
        settings: Dict[str, str],
    ) -> Dict[str, float]:
        players = team_data.get("players") or []
        dead_contracts = team_data.get("dead_contracts") or []

        def player_cap_value(player: Dict[str, Any]) -> float:
            hold = cap_hold_amount(player, season, settings, salary_cap)
            if hold > 0:
                return hold
            if is_two_way_player(player) or is_exhibit10_player(player):
                return 0.0
            return minimum_contract_team_salary(player, season, salary_cap)

        def player_apron_value(player: Dict[str, Any]) -> float:
            if cap_hold_amount(player, season, settings, salary_cap) > 0:
                return 0.0
            if is_two_way_player(player) or is_exhibit10_player(player):
                return 0.0
            return minimum_contract_team_salary(player, season, salary_cap) + apron_yos_adjustment(player, season, salary_cap)

        dead_cap_team_salary = sum(
            dead_contract_salary_num(d, season)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) in {"normal", "draft_hold"}
            and not dead_contract_excluded_from_cap(d)
        )
        dead_cap_apron = sum(
            dead_contract_salary_num(d, season)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "normal"
            and not dead_contract_excluded_from_cap(d)
        )
        open_roster_hold = open_roster_spot_cap_hold(players, season, settings, salary_cap)
        cap_total_before_floor = sum(player_cap_value(p) for p in players) + dead_cap_team_salary + float(open_roster_hold.get("amount") or 0.0)
        cap_total = apply_salary_floor(settings, season, salary_cap, cap_total_before_floor)
        return {
            "cap_total": cap_total,
            "cap_total_before_floor": cap_total_before_floor,
            "salary_floor_adjustment": max(0.0, cap_total - cap_total_before_floor),
            "apron_account": sum(player_apron_value(p) for p in players) + dead_cap_apron,
            "open_roster_spot_cap_hold": float(open_roster_hold.get("amount") or 0.0),
            "open_roster_spot_count": float(open_roster_hold.get("open_spots") or 0.0),
            "open_roster_spot_roster_count": float(open_roster_hold.get("roster_count") or 0.0),
            "open_roster_spot_minimum_salary": float(open_roster_hold.get("minimum_salary") or 0.0),
        }

    def _trade_machine_flow_skeleton(
        self,
        code: str,
        team_data: Dict[str, Any],
        season: int,
        thresholds: Dict[str, float],
        settings: Dict[str, str],
    ) -> Dict[str, Any]:
        balances = self._trade_machine_team_balances(team_data, season, thresholds["salaryCap"], settings)
        players = team_data.get("players") or []
        roster_counts = roster_contract_counts(players, season)
        standard_count = roster_counts["standard"]
        two_way_count = roster_counts["two_way"]
        before_cap = float(balances["cap_total"])
        before_raw_cap = float(balances.get("cap_total_before_floor") or before_cap)
        before_apron = float(balances["apron_account"])
        return {
            "code": code,
            "beforeCap": before_cap,
            "beforeRawCap": before_raw_cap,
            "beforeSalaryFloorAdjustment": float(balances.get("salary_floor_adjustment") or 0.0),
            "beforeApronAccount": before_apron,
            "incomingSalary": 0.0,
            "outgoingSalary": 0.0,
            "incomingMatchingSalary": 0.0,
            "outgoingMatchingSalary": 0.0,
            "incomingCash": 0.0,
            "outgoingCash": 0.0,
            "incomingCapSalary": 0.0,
            "outgoingCapSalary": 0.0,
            "incomingApronSalary": 0.0,
            "outgoingApronSalary": 0.0,
            "incomingAssets": [],
            "outgoingAssets": [],
            "postCap": before_cap,
            "postRawCap": before_raw_cap,
            "postSalaryFloorAdjustment": float(balances.get("salary_floor_adjustment") or 0.0),
            "postApronAccount": before_apron,
            "beforeRosterStandard": standard_count,
            "beforeRosterTwoWay": two_way_count,
            "postRosterStandard": standard_count,
            "postRosterTwoWay": two_way_count,
            "beforeOpenRosterSpotCapHold": float(balances.get("open_roster_spot_cap_hold") or 0.0),
            "postOpenRosterSpotCapHold": float(balances.get("open_roster_spot_cap_hold") or 0.0),
            "beforeOpenRosterSpotCount": int(balances.get("open_roster_spot_count") or 0),
            "postOpenRosterSpotCount": int(balances.get("open_roster_spot_count") or 0),
            "beforeOpenRosterSpotRosterCount": int(balances.get("open_roster_spot_roster_count") or 0),
            "postOpenRosterSpotRosterCount": int(balances.get("open_roster_spot_roster_count") or 0),
            "openRosterSpotMinimumSalary": float(balances.get("open_roster_spot_minimum_salary") or 0.0),
            "beforeBalances": self._trade_machine_balance_snapshot(thresholds, before_cap, before_apron),
            "afterBalances": self._trade_machine_balance_snapshot(thresholds, before_cap, before_apron),
        }

    def _trade_machine_hard_cap_for_season(self, team_data: Dict[str, Any], season: int) -> str:
        season_key = str(int(season))
        summaries = team_data.get("season_summaries") or {}
        if isinstance(summaries, dict):
            summary = summaries.get(season_key) or {}
            hard_cap = normalize_apron_hard_cap(summary.get("apron_hard_cap"))
            if hard_cap:
                return hard_cap
        for row in team_data.get("apron_hard_caps") or []:
            if parse_int(row.get("season_year")) == int(season):
                return normalize_apron_hard_cap(row.get("hard_cap")) or ""
        summary = team_data.get("summary") or {}
        if parse_int(summary.get("current_year")) == int(season):
            return normalize_apron_hard_cap(summary.get("apron_hard_cap")) or ""
        return ""

    def _trade_machine_pick_owner(self, asset: Dict[str, Any], team_code: str) -> str:
        if normalize_pick_type(asset.get("draft_pick_type")) == "conditional":
            raw = asset.get("draft_pick_conditional_teams")
            try:
                teams = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                teams = []
            if isinstance(teams, list):
                for item in teams:
                    code = normalize_team_code(item)
                    if code:
                        return code
        return self._pick_actual_owner(asset, team_code)

    def _trade_machine_pick_label(self, asset: Dict[str, Any], team_code: str) -> str:
        year = parse_int(asset.get("year"))
        year_label = str(year) if year is not None else "Sin año"
        owner = self._trade_machine_pick_owner(asset, team_code) or team_code
        return f"{year_label} {normalize_pick_round(asset.get('draft_round')).upper()} {owner}"

    def _trade_machine_asset_meta(
        self,
        team_data: Dict[str, Any],
        from_team: str,
        asset_type: str,
        asset_id: int,
        season: int,
        thresholds: Dict[str, float],
        settings: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        if asset_type == "player":
            player = next((p for p in team_data.get("players") or [] if parse_int(p.get("id")) == asset_id), None)
            if not player:
                return None
            hold = cap_hold_amount(player, season, settings, thresholds["salaryCap"])
            salary = 0.0 if is_exhibit10_player(player) else minimum_contract_team_salary(player, season, thresholds["salaryCap"])
            cap_salary = (
                hold
                if hold > 0
                else 0.0
                if is_two_way_player(player) or is_exhibit10_player(player)
                else minimum_contract_team_salary(player, season, thresholds["salaryCap"])
            )
            apron_salary = (
                0.0
                if hold > 0 or is_two_way_player(player) or is_exhibit10_player(player)
                else minimum_contract_team_salary(player, season, thresholds["salaryCap"])
                + apron_yos_adjustment(player, season, thresholds["salaryCap"])
            )
            minimum_cutoff = minimum_salary_2_yos_for_cap(thresholds["salaryCap"])
            roster_slot = roster_contract_slot_type(player, season)
            counts_open_minimum = counts_open_roster_minimum(player, season, settings, thresholds["salaryCap"])
            return {
                "key": f"player:{from_team}:{asset_id}",
                "type": "player",
                "id": asset_id,
                "fromTeam": from_team,
                "label": player.get("name") or "Jugador",
                "detail": " · ".join(str(part) for part in [player.get("position"), player.get("bird_rights")] if part),
                "salary": salary,
                "capSalary": cap_salary,
                "apronSalary": apron_salary,
                "rating": parse_float(player.get("rating")) or 0.0,
                "ratingText": str(player.get("rating") or "").strip(),
                "isMinimumContract": salary > 0 and salary <= minimum_cutoff,
                "isTwoWay": is_two_way_player(player),
                "isExhibit10": is_exhibit10_player(player),
                "rosterSlot": roster_slot,
                "countsOpenRosterMinimum": counts_open_minimum,
                "restricted": False,
                "protected": False,
                "conditional": False,
            }
        if asset_type == "pick":
            pick = next(
                (
                    a for a in team_data.get("assets") or []
                    if a.get("asset_type") == "draft_pick" and parse_int(a.get("id")) == asset_id
                ),
                None,
            )
            if not pick:
                return None
            return {
                "key": f"pick:{from_team}:{asset_id}",
                "type": "pick",
                "id": asset_id,
                "fromTeam": from_team,
                "label": self._trade_machine_pick_label(pick, from_team),
                "detail": str(pick.get("detail") or "").strip(),
                "salary": 0.0,
                "capSalary": 0.0,
                "apronSalary": 0.0,
                "restricted": parse_bool(pick.get("draft_pick_restricted")),
                "stepienRestricted": parse_bool(pick.get("draft_pick_stepien_restricted")),
                "protected": parse_bool(pick.get("draft_pick_protected")),
                "frozen": parse_bool(pick.get("draft_pick_frozen")),
                "conditional": normalize_pick_type(pick.get("draft_pick_type")) == "conditional",
                "sold": normalize_pick_type(pick.get("draft_pick_type")) == "sold",
                "round": normalize_pick_round(pick.get("draft_round")),
                "year": parse_int(pick.get("year")),
            }
        if asset_type == "right":
            right = next(
                (
                    a for a in team_data.get("assets") or []
                    if a.get("asset_type") == "player_right" and parse_int(a.get("id")) == asset_id
                ),
                None,
            )
            if not right:
                return None
            return {
                "key": f"right:{from_team}:{asset_id}",
                "type": "right",
                "id": asset_id,
                "fromTeam": from_team,
                "label": right.get("label") or "Derecho de jugador",
                "detail": str(right.get("detail") or "").strip(),
                "salary": 0.0,
                "capSalary": 0.0,
                "apronSalary": 0.0,
                "restricted": False,
                "protected": False,
                "conditional": False,
            }
        return None

    def _trade_machine_pick_action(self, value: Any) -> str:
        return TRADE_PICK_ACTION_SWAP if str(value or "").strip() == TRADE_PICK_ACTION_SWAP else TRADE_PICK_ACTION_SEND

    def _trade_process_pick_actions(self, value: Any) -> Dict[int, str]:
        actions: Dict[int, str] = {}
        if isinstance(value, dict):
            items = value.items()
        elif isinstance(value, list):
            items = []
            for item in value:
                if isinstance(item, dict):
                    items.append((item.get("id") or item.get("asset_id"), item.get("action") or item.get("pick_action") or item.get("pickAction")))
        else:
            items = []
        for raw_id, raw_action in items:
            pick_id = parse_int(raw_id)
            if pick_id is None:
                continue
            actions[pick_id] = self._trade_machine_pick_action(raw_action)
        return actions

    def _trade_machine_asset_for_selection(self, meta: Dict[str, Any], selection: Dict[str, Any]) -> Dict[str, Any]:
        if meta.get("type") != "pick":
            return dict(meta)
        pick_action = self._trade_machine_pick_action(selection.get("pick_action") or selection.get("pickAction"))
        asset = dict(meta)
        asset["pickAction"] = pick_action
        if pick_action == TRADE_PICK_ACTION_SWAP:
            asset["type"] = "swap_right"
            asset["label"] = f"Swap {asset.get('label') or ''}".strip()
            detail = str(asset.get("detail") or "").strip()
            asset["detail"] = " · ".join(part for part in [detail, "La ronda no cambia de dueño; se venden derechos de intercambio."] if part)
        return asset

    def _trade_asset_counts_as_move(self, asset: Dict[str, Any], season_year: int) -> bool:
        if not parse_bool(asset.get("countsMove", True)):
            return False
        asset_type = str(asset.get("type") or asset.get("asset_type") or "").strip().lower()
        if asset_type == "player":
            return True
        if asset_type not in {"pick", "draft_pick"}:
            return False
        if self._trade_machine_pick_action(asset.get("pickAction") or asset.get("pick_action")) == TRADE_PICK_ACTION_SWAP:
            return False
        pick_year = parse_int(asset.get("year"))
        pick_round = normalize_pick_round(asset.get("round") or asset.get("draft_round"))
        return pick_round == "1st" and pick_year == int(season_year) + 1

    def _trade_flow_move_count(self, flow: Dict[str, Any], season_year: int) -> int:
        outgoing = sum(
            1 for asset in flow.get("outgoingAssets") or []
            if self._trade_asset_counts_as_move(asset, season_year)
        )
        incoming = sum(
            1 for asset in flow.get("incomingAssets") or []
            if self._trade_asset_counts_as_move(asset, season_year)
        )
        return outgoing + incoming

    def _trade_machine_normalized_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_teams = payload.get("teams")
        if raw_teams is None:
            raw_teams = payload.get("selectedTeams")
        teams: List[str] = []
        seen: set[str] = set()
        if isinstance(raw_teams, list):
            for item in raw_teams:
                code = normalize_team_code(item)
                if code and code not in seen:
                    seen.add(code)
                    teams.append(code)
        selections: List[Dict[str, Any]] = []
        raw_selections = payload.get("selections")
        if isinstance(raw_selections, dict):
            iterable = raw_selections.values()
        elif isinstance(raw_selections, list):
            iterable = raw_selections
        else:
            iterable = []
        for item in iterable:
            if not isinstance(item, dict):
                continue
            asset_type = str(item.get("type") or item.get("asset_type") or "").strip().lower()
            if asset_type not in {"player", "pick", "right"}:
                continue
            asset_id = parse_int(item.get("id") or item.get("asset_id"))
            from_team = normalize_team_code(item.get("from_team") or item.get("fromTeam"))
            to_team = normalize_team_code(item.get("to_team") or item.get("toTeam"))
            if asset_id is None:
                continue
            selections.append(
                {
                    "type": asset_type,
                    "id": asset_id,
                    "fromTeam": from_team,
                    "toTeam": to_team,
                    "pickAction": self._trade_machine_pick_action(item.get("pick_action") or item.get("pickAction")),
                    "countsMove": False if parse_bool(item.get("no_count") or item.get("noCount")) else True,
                }
            )
            if from_team and from_team not in seen:
                seen.add(from_team)
                teams.append(from_team)
            if to_team and to_team not in seen:
                seen.add(to_team)
                teams.append(to_team)
        cash_transfers: List[Dict[str, Any]] = []
        raw_cash = payload.get("cash")
        if raw_cash is None:
            raw_cash = payload.get("cash_considerations") or payload.get("cashConsiderations")
        if isinstance(raw_cash, dict):
            cash_iterable = raw_cash.values()
        elif isinstance(raw_cash, list):
            cash_iterable = raw_cash
        else:
            cash_iterable = []
        for item in cash_iterable:
            if not isinstance(item, dict):
                continue
            from_team = normalize_team_code(item.get("from_team") or item.get("fromTeam"))
            to_team = normalize_team_code(item.get("to_team") or item.get("toTeam"))
            amount = parse_float(item.get("amount"))
            if amount is None:
                amount = parse_float(item.get("cash_amount") or item.get("cashAmount"))
            if amount is None or amount <= 0:
                continue
            cash_transfers.append(
                {
                    "fromTeam": from_team,
                    "toTeam": to_team,
                    "amount": float(amount),
                }
            )
            if from_team and from_team not in seen:
                seen.add(from_team)
                teams.append(from_team)
            if to_team and to_team not in seen:
                seen.add(to_team)
                teams.append(to_team)
        return {"teams": teams, "selections": selections, "cash": cash_transfers}

    def _trade_validation_fingerprint(
        self,
        payload: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> str:
        """Sign canonical inputs plus the authoritative result/state they produced."""
        normalized = self._trade_machine_normalized_request(payload)
        settings = self.get_settings()
        season = parse_int(payload.get("season")) or parse_int(settings.get("current_year")) or 2025
        material = {
            "rules_version": TRADE_VALIDATION_RULES_VERSION,
            "season": int(season),
            "trade_bucket": normalize_trade_bucket(
                payload.get("trade_bucket") or settings.get("trade_move_phase")
            ),
            "request": normalized,
            "result": {
                key: value
                for key, value in validation.items()
                if key not in {"validation_hash", "rules_version"}
            },
        }
        encoded = json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _signed_trade_validation(
        self,
        payload: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = dict(validation)
        result["rules_version"] = TRADE_VALIDATION_RULES_VERSION
        result["validation_hash"] = self._trade_validation_fingerprint(payload, result)
        return result

    def _trade_machine_expanded_buffer(self, salary_cap: float) -> float:
        calculated = round(float(salary_cap or 0.0) * TRADE_MATCH_EXPANDED_BUFFER_RATIO)
        return float(calculated if calculated > 0 else TRADE_MATCH_EXPANDED_BUFFER_FALLBACK)

    def _trade_machine_expanded_tpe_limit(self, outgoing_salary: float, salary_cap: float) -> float:
        outgoing = float(outgoing_salary or 0.0)
        if outgoing < TRADE_MATCH_LOW_BAND:
            return outgoing * 2 + TRADE_MATCH_CUSHION
        if outgoing <= TRADE_MATCH_HIGH_BAND:
            return outgoing + self._trade_machine_expanded_buffer(salary_cap)
        return outgoing * 1.25

    def _trade_machine_first_apron_limited(self, flow: Dict[str, Any], thresholds: Dict[str, float]) -> bool:
        first_apron = float(thresholds.get("firstApron") or 0.0)
        before = float(flow.get("beforeApronAccount") or flow.get("beforeCap") or 0.0)
        post = float(flow.get("postApronAccount") or flow.get("postCap") or 0.0)
        return first_apron > 0 and (before >= first_apron or post >= first_apron)

    def _trade_machine_second_apron_limited(self, flow: Dict[str, Any], thresholds: Dict[str, float]) -> bool:
        second_apron = float(thresholds.get("secondApron") or 0.0)
        before = float(flow.get("beforeApronAccount") or flow.get("beforeCap") or 0.0)
        post = float(flow.get("postApronAccount") or flow.get("postCap") or 0.0)
        return second_apron > 0 and (before >= second_apron or post >= second_apron)

    def _trade_machine_salary_match_profile(
        self,
        code: str,
        flow: Dict[str, Any],
        team_data: Dict[str, Any],
        thresholds: Dict[str, float],
    ) -> Dict[str, Any]:
        raw_incoming_matching = flow.get("incomingMatchingSalary")
        raw_outgoing_matching = flow.get("outgoingMatchingSalary")
        incoming = float(raw_incoming_matching if raw_incoming_matching is not None else flow.get("incomingSalary") or 0.0)
        outgoing = float(raw_outgoing_matching if raw_outgoing_matching is not None else flow.get("outgoingSalary") or 0.0)
        actual_incoming = float(flow.get("incomingSalary") or 0.0)
        before_cap = float(flow.get("beforeCap") or 0.0)
        post_cap = float(flow.get("postCap") or 0.0)
        outgoing_players = len([a for a in flow.get("outgoingAssets") or [] if a.get("type") == "player"])
        incoming_players = len([a for a in flow.get("incomingAssets") or [] if a.get("type") == "player"])
        first_limited = self._trade_machine_first_apron_limited(flow, thresholds)
        second_limited = self._trade_machine_second_apron_limited(flow, thresholds)
        aggregation_hard_cap_trigger = "second" if outgoing_players > 1 and incoming_players > 0 else ""
        standard_limit = outgoing + TRADE_MATCH_CUSHION if outgoing_players > 0 and incoming_players > 0 else 0.0
        minimum_excluded = max(0.0, actual_incoming - incoming)
        minimum_note = (
            f" {format_trade_money(minimum_excluded)} en mínimos recibidos no computan para el cuadre salarial."
            if minimum_excluded > 0
            else ""
        )
        if incoming <= 0 or incoming <= outgoing:
            return {
                "legal": True,
                "tpe": "none",
                "label": "Sin TPE",
                "limit": outgoing,
                "hardCapTrigger": aggregation_hard_cap_trigger,
                "message": "No recibe salario computable de jugadores."
                if incoming <= 0
                else f"Recibe {format_trade_money(incoming)} computable y envía {format_trade_money(outgoing)}; no necesita recibir más salario del que envía.{minimum_note}",
            }
        if second_limited:
            return {
                "legal": False,
                "tpe": "second_apron_block",
                "label": "Restricción 2do apron",
                "limit": outgoing,
                "message": f"Está limitado por el 2do apron: no puede recibir más salario computable del que envía ({format_trade_money(outgoing)}). Recibe {format_trade_money(incoming)} computable.{minimum_note}",
            }
        if first_limited:
            label = "TPE agregada" if outgoing_players > 1 else "TPE estándar"
            return {
                "legal": outgoing_players > 0 and incoming_players > 0 and incoming <= standard_limit,
                "tpe": "aggregated" if outgoing_players > 1 else "standard",
                "label": label,
                "limit": standard_limit,
                "hardCapTrigger": aggregation_hard_cap_trigger,
                "message": (
                    f"Necesita enviar al menos un jugador para usar {label}."
                    if outgoing_players <= 0
                    else f"Necesita recibir al menos un jugador para usar {label}."
                    if incoming_players <= 0
                    else f"{label}: puede recibir hasta {format_trade_money(standard_limit)} computable (100% del salario enviado + $250k).{minimum_note}"
                    if incoming <= standard_limit
                    else f"{label}: puede recibir hasta {format_trade_money(standard_limit)} computable (100% del salario enviado + $250k), pero recibe {format_trade_money(incoming)} computable.{minimum_note}"
                ),
            }

        salary_cap = thresholds["salaryCap"]
        room_limit = outgoing + max(0.0, salary_cap + TRADE_ROOM_TPE_BUFFER - before_cap)
        cap_space_legal = before_cap < salary_cap and incoming_players > 0 and post_cap <= salary_cap
        room_legal = before_cap < salary_cap and outgoing_players > 0 and incoming_players > 0 and post_cap <= salary_cap + TRADE_ROOM_TPE_BUFFER
        expanded_limit = self._trade_machine_expanded_tpe_limit(outgoing, salary_cap) if outgoing_players > 0 else 0.0
        expanded_legal = outgoing_players > 0 and incoming_players > 0 and incoming <= expanded_limit
        if cap_space_legal:
            return {
                "legal": True,
                "tpe": "cap_room",
                "label": "Espacio salarial",
                "limit": room_limit,
                "message": f"Absorbe el salario con espacio salarial; límite {format_trade_money(room_limit)} antes de usar el buffer Room TPE.",
            }
        if standard_limit > 0 and incoming <= standard_limit:
            label = "TPE agregada" if outgoing_players > 1 else "TPE estándar"
            return {
                "legal": True,
                "tpe": "aggregated" if outgoing_players > 1 else "standard",
                "label": label,
                "limit": standard_limit,
                "hardCapTrigger": aggregation_hard_cap_trigger,
                "message": f"{label}: puede recibir hasta {format_trade_money(standard_limit)} (100% del salario enviado + $250k).",
            }
        if expanded_legal:
            return {
                "legal": True,
                "tpe": "expanded",
                "label": "TPE expandida",
                "limit": expanded_limit,
                "hardCapTrigger": "first",
                "message": f"TPE expandida: puede recibir hasta {format_trade_money(expanded_limit)} según el salario enviado.",
            }
        if room_legal:
            return {
                "legal": True,
                "tpe": "room",
                "label": "Room TPE",
                "limit": room_limit,
                "message": f"Room TPE: queda hasta $250k por encima del salary cap; límite {format_trade_money(room_limit)} de salario computable recibido.{minimum_note}",
            }
        best_limit = max(expanded_limit, room_limit if before_cap < salary_cap else 0.0)
        reason = (
            "no envía ningún jugador para crear una TPE"
            if outgoing_players <= 0
            else "no recibe ningún jugador"
            if incoming_players <= 0
            else "supera los límites de TPE disponibles"
        )
        return {
            "legal": False,
            "tpe": "none",
            "label": "Sin TPE válida",
            "limit": best_limit,
            "message": f"No hay TPE válida: {reason}. Puede recibir hasta {format_trade_money(best_limit)} computable, pero recibe {format_trade_money(incoming)} computable.{minimum_note}",
        }

    def _trade_machine_issue_messages(self, issues: List[Dict[str, Any]], rule: str) -> List[str]:
        messages = []
        for issue in issues:
            if issue.get("rule") != rule:
                continue
            prefix = f"{issue.get('teamCode')}: " if issue.get("teamCode") else ""
            messages.append(f"{prefix}{issue.get('message')}")
        return messages

    def _trade_machine_rule_checklist(
        self,
        issues: List[Dict[str, Any]],
        selected_count: int,
        flows: Dict[str, Any],
        salary_pass_messages: List[str],
    ) -> List[Dict[str, Any]]:
        def has(rule: str, severity: Optional[str] = None) -> bool:
            return any(i.get("rule") == rule and (severity is None or i.get("severity") == severity) for i in issues)

        def messages(rule: str, fallback: List[str]) -> List[str]:
            return self._trade_machine_issue_messages(issues, rule) or fallback

        return [
            {
                "key": "salary",
                "label": "Cuadre salarial básico",
                "status": "pending" if not selected_count else "fail" if has("salary") else "pass",
                "messages": ["Añade activos para evaluar el cuadre salarial."] if not selected_count else messages("salary", salary_pass_messages),
            },
            {
                "key": "moves",
                "label": "Movimientos disponibles",
                "status": "pending" if not selected_count else "fail" if has("moves", "illegal") else "warning" if has("moves", "warning") else "pass",
                "messages": ["Añade activos para evaluar los movimientos disponibles."] if not selected_count else messages("moves", ["Todos los equipos tienen movimientos suficientes para los activos que envían."]),
            },
            {
                "key": "cash",
                "label": "Cash disponible",
                "status": "fail" if has("cash", "illegal") else "warning" if has("cash", "warning") else "pass",
                "messages": messages("cash", ["El cash incluido queda dentro de los límites disponibles."]),
            },
            {
                "key": "multi_team",
                "label": "Traspaso multi-equipo",
                "status": "fail" if has("multi_team") else "pass",
                "messages": messages("multi_team", ["Si hay más de dos equipos, todos envían y reciben algo."]),
            },
            {
                "key": "hard_cap",
                "label": "Límite duro",
                "status": "fail" if has("hard_cap") else "pass",
                "messages": messages("hard_cap", ["No se detecta conflicto de límite duro en el 1er/2do apron."]),
            },
            {
                "key": "hard_cap_trigger",
                "label": "Hard cap generado",
                "status": "warning" if has("hard_cap_trigger") else "pass",
                "messages": messages("hard_cap_trigger", ["El traspaso no genera un nuevo hard cap de apron para los equipos seleccionados."]),
            },
            {
                "key": "second_apron_aggregation",
                "label": "Agregación 2do apron",
                "status": "fail" if has("second_apron_aggregation") else "pass",
                "messages": messages("second_apron_aggregation", ["No se detecta agregación salarial prohibida para equipos en 2do apron."]),
            },
            {
                "key": "minimum_stacking",
                "label": "Stacking mínimos",
                "status": "fail" if has("minimum_stacking", "illegal") else "warning" if has("minimum_stacking", "warning") else "pass",
                "messages": messages("minimum_stacking", ["No se detecta combinación de 3+ jugadores con múltiples contratos mínimos enviados por menos jugadores recibidos."]),
            },
            {
                "key": "restricted_pick",
                "label": "Ronda restringida",
                "status": "fail" if has("restricted_pick") else "pass",
                "messages": messages("restricted_pick", ["No hay ninguna ronda restringida seleccionada."]),
            },
            {
                "key": "frozen_pick",
                "label": "Ronda congelada",
                "status": "fail" if has("frozen_pick") else "pass",
                "messages": messages("frozen_pick", ["No hay ninguna ronda congelada seleccionada."]),
            },
            {
                "key": "manual_review",
                "label": "Revisión manual ANBA",
                "status": "warning" if has("manual_review") else "pass",
                "messages": messages("manual_review", ["No se activa revisión por protecciones, condiciones, Stepien, Ley Randle, BYC/S&T ni restricciones de aprons no modeladas."]),
            },
            {
                "key": "roster_count",
                "label": "Tamaño de plantilla",
                "status": "fail" if has("roster_count", "illegal") else "warning" if has("roster_count", "warning") else "pass",
                "messages": messages("roster_count", ["El tamaño de plantilla queda dentro de los límites configurados."]),
            },
        ]

    def validate_trade_machine(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        settings = self.get_settings()
        season = self._trade_machine_season(payload, settings)
        thresholds = self._trade_machine_thresholds(settings, season)
        roster_limits = self._trade_machine_roster_limits(settings)
        normalized = self._trade_machine_normalized_request(payload)
        teams = normalized["teams"]
        selections = normalized["selections"]
        cash_transfers = normalized.get("cash") or []
        issues: List[Dict[str, Any]] = []
        if len(teams) < TRADE_MACHINE_MIN_TEAMS:
            issues.append({"severity": "illegal", "rule": "setup", "message": "Selecciona al menos dos equipos."})
        if len(teams) > TRADE_MACHINE_MAX_TEAMS:
            issues.append({"severity": "illegal", "rule": "setup", "message": "Selecciona seis equipos o menos."})
        if not selections and not cash_transfers:
            issues.append({"severity": "warning", "rule": "setup", "message": "Selecciona al menos un activo."})

        team_data_by_code: Dict[str, Dict[str, Any]] = {}
        for code in teams:
            data = self.get_team(code, move_season_year=season)
            if not data:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": code, "message": "Equipo no encontrado."})
                continue
            team_data_by_code[code] = data

        flows = {
            code: self._trade_machine_flow_skeleton(code, data, season, thresholds, settings)
            for code, data in team_data_by_code.items()
        }
        selected_count = 0
        any_player_selected = False
        selected_keys: set[str] = set()
        selected_assets: List[Dict[str, Any]] = []
        for selection in selections:
            from_team = selection.get("fromTeam")
            to_team = selection.get("toTeam")
            asset_type = selection.get("type")
            asset_id = parse_int(selection.get("id"))
            if not from_team or from_team not in team_data_by_code:
                issues.append({"severity": "illegal", "rule": "setup", "message": "Un activo seleccionado no tiene equipo origen válido."})
                continue
            if not to_team or to_team not in team_data_by_code or to_team == from_team:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": "Un activo seleccionado necesita un equipo de destino válido."})
                continue
            if asset_id is None:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": "Un activo seleccionado tiene un identificador inválido."})
                continue
            meta = self._trade_machine_asset_meta(team_data_by_code[from_team], from_team, str(asset_type), asset_id, season, thresholds, settings)
            if not meta:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": "Un activo seleccionado ya no está disponible."})
                continue
            if meta["key"] in selected_keys:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": f"{meta.get('label')} está seleccionado más de una vez."})
                continue
            selected_keys.add(meta["key"])
            selected_count += 1
            selected = self._trade_machine_asset_for_selection(meta, selection)
            selected["toTeam"] = to_team
            selected["fromTeam"] = from_team
            selected["countsMove"] = bool(selection.get("countsMove", True))
            selected_assets.append(selected)
            if meta.get("sold"):
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": f"{meta.get('label')} ya está vendida y no se puede mover."})
            if meta.get("frozen"):
                issues.append({"severity": "illegal", "rule": "frozen_pick", "teamCode": from_team, "message": f"{meta.get('label')} está congelada por penalización del 2do apron y no se puede mover."})
            if meta.get("restricted"):
                issues.append({"severity": "illegal", "rule": "restricted_pick", "teamCode": from_team, "message": f"{meta.get('label')} está restringida por protecciones previas y no se puede mover ni vender como swap."})
            if meta.get("stepienRestricted") and selected.get("pickAction") != TRADE_PICK_ACTION_SWAP:
                issues.append({"severity": "illegal", "rule": "restricted_pick", "teamCode": from_team, "message": f"{meta.get('label')} está restringida por Stepien y solo puede venderse como derecho de swap."})
            if meta.get("conditional") or meta.get("protected"):
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": from_team, "message": f"{meta.get('label')} necesita revisión manual por condiciones/protecciones."})
            if meta.get("type") == "pick" and selected.get("pickAction") == TRADE_PICK_ACTION_SWAP:
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": from_team, "message": f"{meta.get('label')}: derecho de swap seleccionado; revisa protecciones, prioridad y equipo que acabaría eligiendo."})
            elif meta.get("type") == "pick" and meta.get("round") == "1st" and not meta.get("stepienRestricted"):
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": from_team, "message": f"{meta.get('label')} necesita revisión de la regla Stepien."})
            if selected.get("type") == "player":
                any_player_selected = True
            salary = float(selected.get("salary") or 0.0)
            matching_salary = 0.0 if selected.get("isMinimumContract") else salary
            cap_salary = float(selected.get("capSalary") if selected.get("capSalary") is not None else salary)
            apron_salary = float(selected.get("apronSalary") if selected.get("apronSalary") is not None else cap_salary)
            from_flow = flows[from_team]
            to_flow = flows[to_team]
            from_flow["outgoingSalary"] += salary
            from_flow["outgoingMatchingSalary"] += salary
            from_flow["outgoingCapSalary"] += cap_salary
            from_flow["outgoingApronSalary"] += apron_salary
            from_flow["outgoingAssets"].append({**selected, "toTeam": to_team})
            to_flow["incomingSalary"] += salary
            to_flow["incomingMatchingSalary"] += matching_salary
            to_flow["incomingCapSalary"] += cap_salary
            to_flow["incomingApronSalary"] += apron_salary
            to_flow["incomingAssets"].append({**selected, "fromTeam": from_team})
            if selected.get("type") == "player":
                roster_slot = selected.get("rosterSlot")
                if roster_slot == "two_way":
                    from_flow["postRosterTwoWay"] -= 1
                    to_flow["postRosterTwoWay"] += 1
                elif roster_slot == "standard":
                    from_flow["postRosterStandard"] -= 1
                    to_flow["postRosterStandard"] += 1
                if selected.get("countsOpenRosterMinimum"):
                    from_flow["postOpenRosterSpotRosterCount"] -= 1
                    to_flow["postOpenRosterSpotRosterCount"] += 1

        for idx, transfer in enumerate(cash_transfers):
            from_team = transfer.get("fromTeam")
            to_team = transfer.get("toTeam")
            amount = float(transfer.get("amount") or 0.0)
            if not from_team or from_team not in team_data_by_code:
                issues.append({"severity": "illegal", "rule": "cash", "message": "Una cantidad de cash no tiene equipo origen válido."})
                continue
            if not to_team or to_team not in team_data_by_code or to_team == from_team:
                issues.append({"severity": "illegal", "rule": "cash", "teamCode": from_team, "message": "Una cantidad de cash necesita un equipo de destino válido."})
                continue
            if amount <= 0:
                issues.append({"severity": "illegal", "rule": "cash", "teamCode": from_team, "message": "La cantidad de cash debe ser mayor que cero."})
                continue
            selected_count += 1
            asset = {
                "key": f"cash:{from_team}:{to_team}:{idx}",
                "type": "cash",
                "fromTeam": from_team,
                "toTeam": to_team,
                "label": "Cash considerations",
                "detail": format_trade_money(amount),
                "salary": 0.0,
                "capSalary": 0.0,
                "apronSalary": 0.0,
                "cashAmount": amount,
                "countsMove": False,
            }
            flows[from_team]["outgoingCash"] += amount
            flows[from_team]["outgoingAssets"].append(dict(asset))
            flows[to_team]["incomingCash"] += amount
            flows[to_team]["incomingAssets"].append(dict(asset))

        for flow in flows.values():
            post_open_roster_count = max(0, int(flow.get("postOpenRosterSpotRosterCount") or 0))
            post_open_spots = max(0, OPEN_ROSTER_SPOT_MINIMUM - post_open_roster_count)
            post_open_hold = float(post_open_spots) * float(flow.get("openRosterSpotMinimumSalary") or 0.0)
            flow["postOpenRosterSpotRosterCount"] = post_open_roster_count
            flow["postOpenRosterSpotCount"] = post_open_spots
            flow["postOpenRosterSpotCapHold"] = post_open_hold
            open_hold_delta = post_open_hold - float(flow.get("beforeOpenRosterSpotCapHold") or 0.0)
            post_raw_cap = float(flow.get("beforeRawCap") or flow.get("beforeCap") or 0.0) + flow["incomingCapSalary"] - flow["outgoingCapSalary"] + open_hold_delta
            flow["postRawCap"] = post_raw_cap
            flow["postCap"] = apply_salary_floor(settings, season, thresholds["salaryCap"], post_raw_cap)
            flow["postSalaryFloorAdjustment"] = max(0.0, flow["postCap"] - post_raw_cap)
            flow["postApronAccount"] = flow["beforeApronAccount"] + flow["incomingApronSalary"] - flow["outgoingApronSalary"]
            flow["afterBalances"] = self._trade_machine_balance_snapshot(thresholds, flow["postCap"], flow["postApronAccount"])

        if any_player_selected:
            issues.append({
                "severity": "warning",
                "rule": "manual_review",
                "message": "Revisar manualmente si algún jugador es extendido o BYC/S&T: la máquina todavía no tiene campos estructurados para aplicar salario promedio, 30 partidos o 50%/100%.",
            })

        salary_pass_messages: List[str] = []
        for code in teams:
            flow = flows.get(code)
            data = team_data_by_code.get(code)
            if not flow or not data:
                continue
            if len(teams) > 2:
                incoming_count = len(flow.get("incomingAssets") or [])
                outgoing_count = len(flow.get("outgoingAssets") or [])
                if not incoming_count and not outgoing_count:
                    issues.append({"severity": "illegal", "rule": "multi_team", "teamCode": code, "message": "En un traspaso de más de dos equipos, cada equipo seleccionado debe enviar y recibir algo."})
                elif not incoming_count or not outgoing_count:
                    issues.append({
                        "severity": "illegal",
                        "rule": "multi_team",
                        "teamCode": code,
                        "message": f"En un traspaso de más de dos equipos debe enviar y recibir algo; ahora {'recibe' if incoming_count else 'no recibe'} y {'envía' if outgoing_count else 'no envía'}.",
                    })
            elif not flow.get("incomingAssets") and not flow.get("outgoingAssets"):
                issues.append({"severity": "warning", "rule": "setup", "teamCode": code, "message": "Seleccionado, pero todavía no participa."})

            hard_cap = self._trade_machine_hard_cap_for_season(data, season)
            if hard_cap == "first" and thresholds["firstApron"] > 0 and flow["postApronAccount"] > thresholds["firstApron"]:
                issues.append({"severity": "illegal", "rule": "hard_cap", "teamCode": code, "message": "Tiene límite duro en el 1er apron y acabaría por encima."})
            if hard_cap == "second" and thresholds["secondApron"] > 0 and flow["postApronAccount"] > thresholds["secondApron"]:
                issues.append({"severity": "illegal", "rule": "hard_cap", "teamCode": code, "message": "Tiene límite duro en el 2do apron y acabaría por encima."})

            profile = self._trade_machine_salary_match_profile(code, flow, data, thresholds)
            if profile.get("legal"):
                if flow.get("incomingAssets") or flow.get("outgoingAssets"):
                    if not (profile.get("tpe") == "none" and float(flow.get("incomingSalary") or 0.0) <= 0):
                        salary_pass_messages.append(f"{code}: {profile.get('message')}")
                trigger = str(profile.get("hardCapTrigger") or "").strip().lower()
                if trigger in {"first", "second"}:
                    current_rank = 2 if hard_cap == "first" else 1 if hard_cap == "second" else 0
                    trigger_rank = 2 if trigger == "first" else 1
                    if current_rank < trigger_rank:
                        apron_label = "1er apron" if trigger == "first" else "2do apron"
                        reason = "usar la TPE expandida" if trigger == "first" else "agregar salarios de varios jugadores"
                        issues.append({
                            "severity": "warning",
                            "rule": "hard_cap_trigger",
                            "teamCode": code,
                            "hardCap": trigger,
                            "message": f"El traspaso dejaría al equipo hard-capped en el {apron_label} por {reason}.",
                        })
            else:
                issues.append({"severity": "illegal", "rule": "salary", "teamCode": code, "message": profile.get("message")})

            bucket = normalize_trade_bucket(payload.get("trade_bucket") or settings.get("trade_move_phase"))
            move_summary = data.get("move_summary") or {}
            availability = self._trade_move_availability_for_bucket(move_summary, bucket)
            remaining = parse_int(availability.get("remaining"))
            move_count = self._trade_flow_move_count(flow, season)
            if move_count:
                if remaining is None:
                    issues.append({"severity": "warning", "rule": "moves", "teamCode": code, "message": f"Necesita {move_count} movimiento(s); no se pudo leer el saldo de movimientos {availability.get('label') or bucket}."})
                elif move_count > remaining:
                    issues.append({"severity": "illegal", "rule": "moves", "teamCode": code, "message": f"Necesita {move_count} movimiento(s) y solo tiene {remaining} disponible(s) en {availability.get('label') or bucket}."})
                elif bucket == "post30" and availability.get("pre_remaining"):
                    issues.append({"severity": "warning", "rule": "moves", "teamCode": code, "message": f"Cuenta como post-30, pero primero consumirá {min(move_count, int(availability.get('pre_remaining') or 0))} movimiento(s) pre-30 disponible(s)."})

            summary = data.get("summary") or {}
            cash_limit = parse_float(summary.get("cash_limit_total")) or parse_float(settings.get("cash_limit_total")) or 0.0
            before_cash_sent = parse_float(summary.get("cash_sent")) or 0.0
            before_cash_received = parse_float(summary.get("cash_received")) or 0.0
            outgoing_cash = float(flow.get("outgoingCash") or 0.0)
            incoming_cash = float(flow.get("incomingCash") or 0.0)
            if cash_limit > 0 and outgoing_cash > 0 and before_cash_sent + outgoing_cash > cash_limit:
                issues.append({
                    "severity": "illegal",
                    "rule": "cash",
                    "teamCode": code,
                    "message": f"Envía {format_trade_money(outgoing_cash)} en cash y superaría su límite disponible.",
                })
            if cash_limit > 0 and incoming_cash > 0 and before_cash_received + incoming_cash > cash_limit:
                issues.append({
                    "severity": "illegal",
                    "rule": "cash",
                    "teamCode": code,
                    "message": f"Recibe {format_trade_money(incoming_cash)} en cash y superaría su límite disponible.",
                })

            if self._trade_machine_second_apron_limited(flow, thresholds):
                outgoing_players = [a for a in flow.get("outgoingAssets") or [] if a.get("type") == "player"]
                if len(outgoing_players) > 1 and float(flow.get("incomingSalary") or 0.0) > 0:
                    issues.append({"severity": "illegal", "rule": "second_apron_aggregation", "teamCode": code, "message": f"Equipo en 2do apron: no puede agregar salarios de varios jugadores ({len(outgoing_players)}) para recibir salario."})
            if self._trade_machine_first_apron_limited(flow, thresholds):
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": code, "message": "Equipo limitado por 1er apron: revisar manualmente TPE de temporada anterior, excepciones y jugadores cortados con salario previo > MID si aplican."})
            if self._trade_machine_second_apron_limited(flow, thresholds):
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": code, "message": "Equipo limitado por 2do apron: revisar manualmente que no haya cash, TPMID ni TPE creada mediante S&T."})

            outgoing_players = [a for a in flow.get("outgoingAssets") or [] if a.get("type") == "player"]
            incoming_players = [a for a in flow.get("incomingAssets") or [] if a.get("type") == "player"]
            minimum_outgoing = [a for a in outgoing_players if a.get("isMinimumContract")]
            if len(outgoing_players) >= 3 and len(incoming_players) < len(outgoing_players) and len(minimum_outgoing) > 1:
                issues.append({"severity": "warning", "rule": "minimum_stacking", "teamCode": code, "message": f"Envía {len(outgoing_players)} jugadores, {len(minimum_outgoing)} mínimos, y recibe menos jugadores. Puede ser ilegal fuera del periodo 15-Dic/deadline; falta configurar fecha de trade para convertirlo en bloqueo automático."})
            for asset in outgoing_players:
                rating = float(asset.get("rating") or 0.0)
                if 85 <= rating <= 90:
                    issues.append({"severity": "warning", "rule": "manual_review", "teamCode": code, "message": f"Ley Randle: {asset.get('label')} ({int(rating)}) no puede salir si llegó vía trade esta temporada, salvo lesión de temporada."})
                elif 80 <= rating < 85:
                    issues.append({"severity": "warning", "rule": "manual_review", "teamCode": code, "message": f"Ley Randle: {asset.get('label')} ({int(rating)}) debe esperar 2 meses/preseason o 30 partidos/season desde su llegada vía trade."})

            standard = int(flow.get("postRosterStandard") or 0)
            two_way = int(flow.get("postRosterTwoWay") or 0)
            if standard > roster_limits["standardOffseasonMax"]:
                issues.append({"severity": "illegal", "rule": "roster_count", "teamCode": code, "message": f"Quedaría con {standard} contratos estándar; el máximo configurado para offseason es {roster_limits['standardOffseasonMax']}."})
            elif standard > roster_limits["standardMax"]:
                issues.append({"severity": "warning", "rule": "roster_count", "teamCode": code, "message": f"Quedaría con {standard} contratos estándar. Solo sería válido en offseason; durante la temporada el máximo es {roster_limits['standardMax']}."})
            if standard < roster_limits["standardMin"]:
                issues.append({"severity": "warning", "rule": "roster_count", "teamCode": code, "message": f"Quedaría con {standard} contratos estándar, por debajo del mínimo configurado ({roster_limits['standardMin']})."})
            if two_way > roster_limits["twoWayMax"]:
                issues.append({"severity": "illegal", "rule": "roster_count", "teamCode": code, "message": f"Quedaría con {two_way} contratos two-way; el máximo configurado es {roster_limits['twoWayMax']}."})
            if two_way < roster_limits["twoWayMin"]:
                issues.append({"severity": "warning", "rule": "roster_count", "teamCode": code, "message": f"Quedaría con {two_way} contratos two-way, por debajo del mínimo configurado ({roster_limits['twoWayMin']})."})

        has_illegal = any(issue.get("severity") == "illegal" for issue in issues)
        has_warning = any(issue.get("severity") == "warning" for issue in issues)
        checklist = self._trade_machine_rule_checklist(
            issues,
            selected_count,
            flows,
            salary_pass_messages or ["El cuadre salarial básico pasa para todos los equipos seleccionados."],
        )
        result = {
            "ok": True,
            "authoritative": True,
            "season": season,
            "status": "illegal" if has_illegal else "review" if has_warning else "legal",
            "issues": issues,
            "checklist": checklist,
            "flows": flows,
        }
        return self._signed_trade_validation(payload, result)

    def trade_validation_from_process_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(payload.get("selections"), (list, dict)) or isinstance(payload.get("teams"), list):
            return self.validate_trade_machine(payload)

        team_a = normalize_team_code(payload.get("team_a")) or ""
        team_b = normalize_team_code(payload.get("team_b")) or ""
        no_count_a = set(self._clean_trade_ids(payload.get("no_count_players_a") or []))
        no_count_b = set(self._clean_trade_ids(payload.get("no_count_players_b") or []))
        pick_actions_a = self._trade_process_pick_actions(payload.get("pick_actions_a"))
        pick_actions_b = self._trade_process_pick_actions(payload.get("pick_actions_b"))
        selections: List[Dict[str, Any]] = []
        for player_id in self._clean_trade_ids(payload.get("players_a") or []):
            selections.append({"type": "player", "id": player_id, "from_team": team_a, "to_team": team_b, "no_count": player_id in no_count_a})
        for player_id in self._clean_trade_ids(payload.get("players_b") or []):
            selections.append({"type": "player", "id": player_id, "from_team": team_b, "to_team": team_a, "no_count": player_id in no_count_b})
        for pick_id in self._clean_trade_ids(payload.get("pick_ids_a") or []):
            selections.append({"type": "pick", "id": pick_id, "from_team": team_a, "to_team": team_b, "pick_action": pick_actions_a.get(pick_id)})
        for pick_id in self._clean_trade_ids(payload.get("pick_ids_b") or []):
            selections.append({"type": "pick", "id": pick_id, "from_team": team_b, "to_team": team_a, "pick_action": pick_actions_b.get(pick_id)})
        for right_id in self._clean_trade_ids(payload.get("right_ids_a") or []):
            selections.append({"type": "right", "id": right_id, "from_team": team_a, "to_team": team_b})
        for right_id in self._clean_trade_ids(payload.get("right_ids_b") or []):
            selections.append({"type": "right", "id": right_id, "from_team": team_b, "to_team": team_a})
        settings = self.get_settings()
        season = parse_int(payload.get("season")) or parse_int(settings.get("current_year")) or 2025
        return self.validate_trade_machine({
            "teams": [team_a, team_b],
            "season": season,
            "selections": selections,
        })

    def process_trade_from_payload(
        self,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized = self._trade_machine_normalized_request(payload)
        teams = normalized.get("teams") or []
        selections = normalized.get("selections") or []
        cash_transfers = normalized.get("cash") or []
        if len(teams) < 2 or (not selections and not cash_transfers):
            return None

        owns_connection = conn is None
        with (self.connect() if owns_connection else nullcontext(conn)) as conn:
            team_rows: Dict[str, sqlite3.Row] = {}
            for code in teams:
                row = conn.execute("SELECT id, code FROM teams WHERE code = ?", (code,)).fetchone()
                if not row:
                    return None
                team_rows[code] = row

            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            season_year = parse_int(payload.get("season")) or current_year
            bucket = normalize_trade_bucket(payload.get("trade_bucket") or settings.get("trade_move_phase"))
            timestamp = now_iso()
            source_ref = f"{'-'.join(teams)}-{timestamp}"
            summaries: Dict[str, Dict[str, Any]] = {
                code: {
                    "code": code,
                    "move_count": 0,
                    "sent": {"players": [], "pick_count": 0, "swap_count": 0, "right_count": 0, "picks": [], "swaps": [], "rights": [], "cash": [], "cash_amount": 0.0},
                    "received": {"players": [], "pick_count": 0, "swap_count": 0, "right_count": 0, "picks": [], "swaps": [], "rights": [], "cash": [], "cash_amount": 0.0},
                }
                for code in teams
            }

            def add_move_count(code: str) -> None:
                if code in summaries:
                    summaries[code]["move_count"] += 1

            def add_selection_move_counts(from_team: str, to_team: str, asset: Dict[str, Any]) -> None:
                if not self._trade_asset_counts_as_move(asset, season_year):
                    return
                add_move_count(from_team)
                add_move_count(to_team)

            def pick_label(pick_row: Dict[str, Any], source_code: str, prefix: str = "") -> str:
                year = parse_int(pick_row.get("year"))
                year_label = str(year) if year is not None else "Sin año"
                round_label = normalize_pick_round(pick_row.get("draft_round")).upper()
                owner = self._pick_actual_owner(pick_row, source_code)
                return f"{prefix}{year_label} {round_label} ({owner})".strip()

            def move_pick(source_team: sqlite3.Row, target_team: sqlite3.Row, pick_row: Dict[str, Any]) -> None:
                actual_owner = self._pick_actual_owner(pick_row, str(source_team["code"]))
                source_pick_type = normalize_pick_type(pick_row.get("draft_pick_type"))
                pick_round = normalize_pick_round(pick_row.get("draft_round"))
                pick_year = parse_int(pick_row.get("year"))
                if source_pick_type == "conditional":
                    target_pick_type = "conditional"
                    target_original_owner = None
                    target_conditional_teams = pick_row.get("draft_pick_conditional_teams")
                else:
                    target_pick_type = "own" if actual_owner == str(target_team["code"]) else "acquired"
                    target_original_owner = None if target_pick_type == "own" else actual_owner
                    target_conditional_teams = None

                recipient_rows_cur = conn.execute(
                    """
                    SELECT id, draft_pick_type, original_owner, year, draft_round, draft_pick_conditional_teams
                    FROM assets
                    WHERE team_id = ? AND asset_type = 'draft_pick' AND CAST(COALESCE(year, '') AS INTEGER) = ?
                    """,
                    (target_team["id"], pick_year),
                )
                recipient_rows = [row_to_dict(recipient_rows_cur, row) for row in recipient_rows_cur.fetchall()]
                recipient_match = None
                for candidate in recipient_rows:
                    candidate_actual_owner = self._pick_actual_owner(candidate, str(target_team["code"]))
                    if candidate_actual_owner == actual_owner and normalize_pick_round(candidate.get("draft_round")) == pick_round:
                        recipient_match = candidate
                        break

                sold_label = pick_row.get("label") or f"{pick_round.upper()} pick"
                sold_detail = pick_row.get("detail")

                def update_pick_row(asset_id: int) -> None:
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = ?, original_owner = ?, draft_pick_sold_to = NULL,
                            draft_pick_conditional_teams = ?, label = ?, detail = ?,
                            draft_pick_restricted = ?, draft_pick_stepien_restricted = ?,
                            draft_pick_protected = ?, draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            asset_id,
                        ),
                    )

                if source_pick_type == "own":
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = 'sold', original_owner = ?, draft_pick_sold_to = ?,
                            draft_pick_conditional_teams = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (actual_owner, str(target_team["code"]), timestamp, pick_row["id"]),
                    )
                elif recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    if int(recipient_match["id"]) != int(pick_row["id"]):
                        conn.execute("DELETE FROM assets WHERE id = ?", (pick_row["id"],))
                    return
                else:
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        """
                        UPDATE assets
                        SET team_id = ?, row_order = ?, draft_pick_type = ?, original_owner = ?,
                            draft_pick_sold_to = NULL, draft_pick_conditional_teams = ?,
                            label = ?, detail = ?, draft_pick_restricted = ?,
                            draft_pick_stepien_restricted = ?, draft_pick_protected = ?,
                            draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_team["id"],
                            int(mx) + 1,
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            pick_row["id"],
                        ),
                    )
                    return

                if recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    return

                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (target_team["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    """
                    INSERT INTO assets (
                        team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                        draft_pick_type, draft_round, original_owner, exception_type,
                        draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                        draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                        created_at, updated_at
                    ) VALUES (?, ?, 'draft_pick', ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, ?, ?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (
                        target_team["id"],
                        int(mx) + 1,
                        pick_row.get("year"),
                        sold_label,
                        sold_detail,
                        target_pick_type,
                        pick_round,
                        target_original_owner,
                        1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                        target_conditional_teams,
                        1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                        timestamp,
                        timestamp,
                    ),
                )

            for selection in selections:
                from_team = normalize_team_code(selection.get("fromTeam")) or ""
                to_team = normalize_team_code(selection.get("toTeam")) or ""
                asset_type = str(selection.get("type") or "").strip().lower()
                asset_id = parse_int(selection.get("id"))
                if not from_team or not to_team or from_team == to_team or from_team not in team_rows or to_team not in team_rows or asset_id is None:
                    return None
                source_team = team_rows[from_team]
                target_team = team_rows[to_team]

                if asset_type == "player":
                    row = conn.execute(
                        """
                        SELECT p.id, p.profile_id, p.team_id, COALESCE(pp.name, p.name) AS name
                        FROM players p
                        LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                        WHERE p.id = ?
                        """,
                        (asset_id,),
                    ).fetchone()
                    if not row or int(row["team_id"]) != int(source_team["id"]):
                        return None
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                        (target_team["id"], int(mx) + 1, timestamp, asset_id),
                    )
                    player_name = str(row["name"] or "Jugador")
                    summaries[from_team]["sent"]["players"].append(player_name)
                    summaries[to_team]["received"]["players"].append(player_name)
                    add_selection_move_counts(
                        from_team,
                        to_team,
                        {"type": "player", "countsMove": selection.get("countsMove", True)},
                    )
                    self._record_player_transaction(
                        conn,
                        row["profile_id"],
                        "trade",
                        f"Traspasado de {from_team} a {to_team}",
                        player_id=row["id"],
                        team_code=to_team,
                        from_team_code=from_team,
                        to_team_code=to_team,
                        details={"player_name": player_name},
                        created_at=timestamp,
                    )
                    continue

                if asset_type == "pick":
                    row = conn.execute(
                        """
                        SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                               draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order,
                               draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                               draft_pick_frozen
                        FROM assets
                        WHERE id = ? AND asset_type = 'draft_pick'
                        """,
                        (asset_id,),
                    ).fetchone()
                    if not row or int(row["team_id"]) != int(source_team["id"]):
                        return None
                    pick_row = dict(row)
                    if normalize_pick_type(pick_row.get("draft_pick_type")) == "sold":
                        return None
                    pick_action = self._trade_machine_pick_action(selection.get("pickAction") or selection.get("pick_action"))
                    if pick_action == TRADE_PICK_ACTION_SWAP:
                        label = pick_label(pick_row, from_team, "Swap ")
                        summaries[from_team]["sent"]["swap_count"] += 1
                        summaries[from_team]["sent"]["swaps"].append(label)
                        summaries[to_team]["received"]["swap_count"] += 1
                        summaries[to_team]["received"]["swaps"].append(label)
                    else:
                        label = pick_label(pick_row, from_team)
                        move_pick(source_team, target_team, pick_row)
                        summaries[from_team]["sent"]["pick_count"] += 1
                        summaries[from_team]["sent"]["picks"].append(label)
                        summaries[to_team]["received"]["pick_count"] += 1
                        summaries[to_team]["received"]["picks"].append(label)
                    add_selection_move_counts(
                        from_team,
                        to_team,
                        {
                            **pick_row,
                            "type": "pick",
                            "round": normalize_pick_round(pick_row.get("draft_round")),
                            "pickAction": pick_action,
                            "countsMove": selection.get("countsMove", True),
                        },
                    )
                    continue

                if asset_type == "right":
                    row = conn.execute(
                        """
                        SELECT id, team_id, label, detail, row_order
                        FROM assets
                        WHERE id = ? AND asset_type = 'player_right'
                        """,
                        (asset_id,),
                    ).fetchone()
                    if not row or int(row["team_id"]) != int(source_team["id"]):
                        return None
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        "UPDATE assets SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                        (target_team["id"], int(mx) + 1, timestamp, asset_id),
                    )
                    label = str(row["label"] or "Derecho de jugador")
                    summaries[from_team]["sent"]["right_count"] += 1
                    summaries[from_team]["sent"]["rights"].append(label)
                    summaries[to_team]["received"]["right_count"] += 1
                    summaries[to_team]["received"]["rights"].append(label)
                    continue

                return None

            for transfer in cash_transfers:
                from_team = normalize_team_code(transfer.get("fromTeam")) or ""
                to_team = normalize_team_code(transfer.get("toTeam")) or ""
                amount = float(transfer.get("amount") or 0.0)
                if not from_team or not to_team or from_team == to_team or from_team not in team_rows or to_team not in team_rows or amount <= 0:
                    return None
                conn.execute(
                    "UPDATE teams SET cash_sent = COALESCE(cash_sent, 0) + ?, updated_at = ? WHERE id = ?",
                    (amount, timestamp, team_rows[from_team]["id"]),
                )
                conn.execute(
                    "UPDATE teams SET cash_received = COALESCE(cash_received, 0) + ?, updated_at = ? WHERE id = ?",
                    (amount, timestamp, team_rows[to_team]["id"]),
                )
                cash_ref = {"team": to_team, "amount": amount}
                summaries[from_team]["sent"]["cash"].append(cash_ref)
                summaries[from_team]["sent"]["cash_amount"] += amount
                summaries[to_team]["received"]["cash"].append({"team": from_team, "amount": amount})
                summaries[to_team]["received"]["cash_amount"] += amount

            for code, summary in summaries.items():
                move_count = int(summary.get("move_count") or 0)
                if not move_count:
                    continue
                sent = summary.get("sent") or {}
                opponents = sorted(
                    {
                        normalize_team_code(selection.get("toTeam"))
                        for selection in selections
                        if normalize_team_code(selection.get("fromTeam")) == code and normalize_team_code(selection.get("toTeam"))
                    }
                )
                self._insert_trade_move_logs(
                    conn,
                    team_id=int(team_rows[code]["id"]),
                    season_year=season_year,
                    requested_bucket=bucket,
                    move_count=move_count,
                    source_ref=source_ref,
                    note=f"Trade vs {'/'.join(opponents)}" if opponents else "Trade",
                    details={
                        "opponents": opponents,
                        "players": sent.get("players") or [],
                        "players_received": (summary.get("received") or {}).get("players") or [],
                        "pick_count": sent.get("pick_count") or 0,
                        "pick_refs": sent.get("picks") or [],
                        "pick_refs_received": (summary.get("received") or {}).get("picks") or [],
                        "swap_count": sent.get("swap_count") or 0,
                        "swap_refs": sent.get("swaps") or [],
                        "rights": sent.get("rights") or [],
                        "cash": sent.get("cash") or [],
                        "cash_amount": sent.get("cash_amount") or 0.0,
                    },
                    settings=settings,
                )

            if owns_connection:
                conn.commit()

        team_results = [summaries[code] for code in teams]
        result: Dict[str, Any] = {
            "ok": True,
            "trade_bucket": bucket,
            "season": season_year,
            "teams": team_results,
            "team_codes": teams,
        }
        if len(teams) >= 2:
            team_a = teams[0]
            team_b = teams[1]
            result.update(
                {
                    "team_a": {"code": team_a, "move_count": summaries[team_a]["move_count"]},
                    "team_b": {"code": team_b, "move_count": summaries[team_b]["move_count"]},
                    "players_a": summaries[team_a]["sent"]["players"],
                    "players_b": summaries[team_b]["sent"]["players"],
                    "pick_count_a": summaries[team_a]["sent"]["pick_count"],
                    "pick_count_b": summaries[team_b]["sent"]["pick_count"],
                    "pick_refs_a": summaries[team_a]["sent"]["picks"],
                    "pick_refs_b": summaries[team_b]["sent"]["picks"],
                    "swap_count_a": summaries[team_a]["sent"]["swap_count"],
                    "swap_count_b": summaries[team_b]["sent"]["swap_count"],
                    "swap_refs_a": summaries[team_a]["sent"]["swaps"],
                    "swap_refs_b": summaries[team_b]["sent"]["swaps"],
                    "right_count_a": summaries[team_a]["sent"]["right_count"],
                    "right_count_b": summaries[team_b]["sent"]["right_count"],
                    "cash_a": summaries[team_a]["sent"]["cash_amount"],
                    "cash_b": summaries[team_b]["sent"]["cash_amount"],
                }
            )
        return result

    def process_trade_command(
        self,
        payload: Dict[str, Any],
        *,
        validation: Optional[Dict[str, Any]] = None,
        expected_validation_hash: Optional[str] = None,
        require_validation_hash: bool = False,
        force_trade: bool = False,
        notify_discord: bool = False,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
        legacy: bool = False,
        actor: Optional[Dict[str, Any]] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        workflow_run_id = str(command_id or secrets.token_urlsafe(24)).strip()
        if not workflow_run_id or len(workflow_run_id) > 160:
            raise ValueError("invalid_trade_command_id")
        actor_user_id, actor_email, actor_name = self._workflow_actor_fields(actor)
        timestamp = now_iso()
        initial_metadata = {
            "legacy": bool(legacy),
            "team_codes": [
                code
                for code in (
                    payload.get("teams") if isinstance(payload.get("teams"), list) else [
                        payload.get("team_a"),
                        payload.get("team_b"),
                    ]
                )
                if normalize_team_code(code)
            ],
        }
        with self.transaction("IMMEDIATE") as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO workflow_runs (
                        id, workflow_type, state, actor_user_id, actor_email, actor_name,
                        reason, metadata_json, created_at, updated_at
                    ) VALUES (?, 'trade_command', 'draft', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow_run_id,
                        actor_user_id,
                        actor_email,
                        actor_name,
                        "trade_command_created",
                        json.dumps(initial_metadata, ensure_ascii=False, sort_keys=True),
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("trade_command_already_exists") from err
            self._record_workflow_creation_conn(
                conn,
                "trade_command",
                workflow_run_id,
                "draft",
                actor=actor,
                reason="trade_command_created",
                command_id=f"{workflow_run_id}:created",
                metadata=initial_metadata,
                timestamp=timestamp,
            )
            self._transition_workflow_conn(
                conn,
                "trade_command",
                workflow_run_id,
                "validating",
                actor=actor,
                reason="trade_validation_completed",
                command_id=f"{workflow_run_id}:validating",
                updates={"updated_at": timestamp},
                metadata={"validation_requested": True},
                timestamp=timestamp,
            )

        result: Optional[Dict[str, Any]] = None
        authoritative_validation: Optional[Dict[str, Any]] = None
        applied_hard_caps: List[Dict[str, Any]] = []
        outbox_event_ids: List[int] = []
        try:
            with self.transaction("IMMEDIATE") as conn:
                # Recalculate from persisted league state while the write reservation is held.
                # The caller-supplied validation object is display context only, never authority.
                authoritative_validation = (
                    self.trade_validation_from_process_payload(payload)
                    if legacy
                    else self.validate_trade_machine(payload)
                )
                current_hash = str(authoritative_validation.get("validation_hash") or "")
                expected_hash = str(expected_validation_hash or "").strip().lower()
                rejection_error: Optional[str] = None
                rejection_status = 409
                if require_validation_hash and not expected_hash:
                    rejection_error = "trade_validation_required"
                elif expected_hash and not secrets.compare_digest(expected_hash, current_hash):
                    rejection_error = "trade_validation_stale"
                elif any(
                    issue.get("severity") == "illegal"
                    for issue in (authoritative_validation.get("issues") or [])
                ) and not force_trade:
                    rejection_error = "trade_invalid"
                    rejection_status = 422

                if rejection_error:
                    completed_at = now_iso()
                    self._transition_workflow_conn(
                        conn,
                        "trade_command",
                        workflow_run_id,
                        "rejected",
                        actor=actor,
                        reason=rejection_error,
                        command_id=f"{workflow_run_id}:rejected",
                        updates={"updated_at": completed_at, "completed_at": completed_at},
                        metadata={
                            "validation_hash": current_hash,
                            "rules_version": authoritative_validation.get("rules_version"),
                        },
                    )
                    return {
                        "result": None,
                        "validation": authoritative_validation,
                        "error": rejection_error,
                        "status_code": rejection_status,
                        "applied_hard_caps": [],
                        "outbox_event_ids": [],
                        "workflow_run_id": workflow_run_id,
                    }

                self._transition_workflow_conn(
                    conn,
                    "trade_command",
                    workflow_run_id,
                    "processing",
                    actor=actor,
                    reason="trade_processing_started",
                    command_id=f"{workflow_run_id}:processing",
                    updates={"updated_at": now_iso()},
                )
                if legacy:
                    result = self.process_trade(
                        normalize_team_code(payload.get("team_a")) or "",
                        normalize_team_code(payload.get("team_b")) or "",
                        payload.get("players_a") if isinstance(payload.get("players_a"), list) else [],
                        payload.get("players_b") if isinstance(payload.get("players_b"), list) else [],
                        pick_ids_a=payload.get("pick_ids_a") if isinstance(payload.get("pick_ids_a"), list) else [],
                        pick_ids_b=payload.get("pick_ids_b") if isinstance(payload.get("pick_ids_b"), list) else [],
                        right_ids_a=payload.get("right_ids_a") if isinstance(payload.get("right_ids_a"), list) else [],
                        right_ids_b=payload.get("right_ids_b") if isinstance(payload.get("right_ids_b"), list) else [],
                        no_count_players_a=payload.get("no_count_players_a") if isinstance(payload.get("no_count_players_a"), list) else [],
                        no_count_players_b=payload.get("no_count_players_b") if isinstance(payload.get("no_count_players_b"), list) else [],
                        pick_actions_a=payload.get("pick_actions_a"),
                        pick_actions_b=payload.get("pick_actions_b"),
                        trade_bucket=payload.get("trade_bucket"),
                        conn=conn,
                    )
                else:
                    result = self.process_trade_from_payload(payload, conn=conn)

                if not result:
                    self._transition_workflow_conn(
                        conn,
                        "trade_command",
                        workflow_run_id,
                        "rejected",
                        actor=actor,
                        reason="trade_not_processed",
                        command_id=f"{workflow_run_id}:rejected",
                        updates={"updated_at": now_iso(), "completed_at": now_iso()},
                    )
                    return {
                        "result": None,
                        "applied_hard_caps": [],
                        "outbox_event_ids": [],
                        "workflow_run_id": workflow_run_id,
                    }

                settings_cur = conn.execute("SELECT key, value FROM app_settings")
                settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
                season_year = (
                    parse_int(result.get("season"))
                    or parse_int(payload.get("season"))
                    or parse_int(settings.get("current_year"))
                    or 2025
                )
                result["season"] = int(season_year)

                if authoritative_validation:
                    applied_hard_caps = self.apply_trade_hard_cap_triggers(
                        authoritative_validation,
                        int(season_year),
                        conn=conn,
                    )
                    if applied_hard_caps:
                        result["applied_hard_caps"] = applied_hard_caps

                if notify_discord:
                    team_codes = result.get("team_codes") if isinstance(result.get("team_codes"), list) else []
                    if not team_codes:
                        team_codes = []
                        for key in ("team_a", "team_b"):
                            info = result.get(key)
                            if isinstance(info, dict) and info.get("code"):
                                team_codes.append(str(info.get("code")))
                    aggregate_id = "-".join([str(code) for code in team_codes if code]) or workflow_run_id
                    event_id = self.enqueue_outbox_event_conn(
                        conn,
                        "discord.trade_processed",
                        {
                            "result": result,
                            "generate_image": bool(generate_image),
                            "custom_image": custom_image if isinstance(custom_image, dict) else None,
                        },
                        aggregate_type="trade",
                        aggregate_id=aggregate_id,
                    )
                    if event_id:
                        outbox_event_ids.append(int(event_id))

                self._transition_workflow_conn(
                    conn,
                    "trade_command",
                    workflow_run_id,
                    "completed",
                    actor=actor,
                    reason="trade_processed",
                    command_id=f"{workflow_run_id}:completed",
                    updates={
                        "updated_at": now_iso(),
                        "completed_at": now_iso(),
                        "metadata_json": json.dumps(
                            {
                                **initial_metadata,
                                "season": int(season_year),
                                "outbox_event_ids": outbox_event_ids,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                    metadata={"season": int(season_year)},
                )
        except Exception:
            try:
                with self.transaction("IMMEDIATE") as conn:
                    state_row = conn.execute(
                        "SELECT state FROM workflow_runs WHERE id = ?",
                        (workflow_run_id,),
                    ).fetchone()
                    state = str(state_row["state"] or "") if state_row else ""
                    if state in {"validating", "processing"}:
                        self._transition_workflow_conn(
                            conn,
                            "trade_command",
                            workflow_run_id,
                            "failed",
                            actor=actor,
                            reason="trade_processing_failed",
                            command_id=f"{workflow_run_id}:failed",
                            updates={"updated_at": now_iso(), "completed_at": now_iso()},
                        )
            except Exception:
                pass
            raise

        return {
            "result": result,
            "validation": authoritative_validation,
            "applied_hard_caps": applied_hard_caps,
            "outbox_event_ids": outbox_event_ids,
            "workflow_run_id": workflow_run_id,
        }

    def process_trade(
        self,
        team_a_code: str,
        team_b_code: str,
        players_a: List[int],
        players_b: List[int],
        pick_ids_a: Optional[List[int]] = None,
        pick_ids_b: Optional[List[int]] = None,
        right_ids_a: Optional[List[int]] = None,
        right_ids_b: Optional[List[int]] = None,
        no_count_players_a: Optional[List[int]] = None,
        no_count_players_b: Optional[List[int]] = None,
        pick_actions_a: Optional[Any] = None,
        pick_actions_b: Optional[Any] = None,
        trade_bucket: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[Dict[str, Any]]:
        def clean_ids(values: Any) -> List[int]:
            if not isinstance(values, list):
                return []
            out: List[int] = []
            seen: set[int] = set()
            for value in values:
                parsed = parse_int(str(value))
                if parsed is None or parsed <= 0 or parsed in seen:
                    continue
                seen.add(parsed)
                out.append(parsed)
            return out

        ids_a = clean_ids(players_a)
        ids_b = clean_ids(players_b)
        pick_a_all = clean_ids(pick_ids_a or [])
        pick_b_all = clean_ids(pick_ids_b or [])
        pick_action_map_a = self._trade_process_pick_actions(pick_actions_a)
        pick_action_map_b = self._trade_process_pick_actions(pick_actions_b)
        pick_swap_a = {pick_id for pick_id in pick_a_all if pick_action_map_a.get(pick_id) == TRADE_PICK_ACTION_SWAP}
        pick_swap_b = {pick_id for pick_id in pick_b_all if pick_action_map_b.get(pick_id) == TRADE_PICK_ACTION_SWAP}
        pick_a = [pick_id for pick_id in pick_a_all if pick_id not in pick_swap_a]
        pick_b = [pick_id for pick_id in pick_b_all if pick_id not in pick_swap_b]
        right_a = clean_ids(right_ids_a or [])
        right_b = clean_ids(right_ids_b or [])
        no_count_a = set(clean_ids(no_count_players_a or []))
        no_count_b = set(clean_ids(no_count_players_b or []))
        if not ids_a and not pick_a_all and not right_a:
            return None
        if not ids_b and not pick_b_all and not right_b:
            return None

        owns_connection = conn is None
        with (self.connect() if owns_connection else nullcontext(conn)) as conn:
            team_a = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_a_code.upper(),)).fetchone()
            team_b = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_b_code.upper(),)).fetchone()
            if not team_a or not team_b or team_a["id"] == team_b["id"]:
                return None

            if owns_connection:
                current_year = parse_int(self.get_settings().get("current_year")) or 2025
            else:
                settings_cur = conn.execute("SELECT key, value FROM app_settings")
                settings_for_year = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
                current_year = parse_int(settings_for_year.get("current_year")) or 2025
            if current_year < PLAYER_CONTRACT_MIN_YEAR or current_year > PLAYER_CONTRACT_MAX_START_YEAR:
                current_year = 2025

            players_a_rows: List[Dict[str, Any]] = []
            for player_id in ids_a:
                row = conn.execute(
                    """
                    SELECT p.id, p.profile_id, p.team_id, COALESCE(pp.name, p.name) AS name
                    FROM players p
                    LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    WHERE p.id = ?
                    """,
                    (player_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                players_a_rows.append(dict(row))
            players_b_rows: List[Dict[str, Any]] = []
            for player_id in ids_b:
                row = conn.execute(
                    """
                    SELECT p.id, p.profile_id, p.team_id, COALESCE(pp.name, p.name) AS name
                    FROM players p
                    LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    WHERE p.id = ?
                    """,
                    (player_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                players_b_rows.append(dict(row))

            picks_a_rows: List[Dict[str, Any]] = []
            pick_swaps_a_rows: List[Dict[str, Any]] = []
            for asset_id in pick_a_all:
                row = conn.execute(
                    """
                    SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                           draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order,
                           draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                           draft_pick_frozen
                    FROM assets
                    WHERE id = ? AND asset_type = 'draft_pick'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                if normalize_pick_type(row["draft_pick_type"]) == "sold":
                    return None
                if asset_id in pick_swap_a:
                    pick_swaps_a_rows.append(dict(row))
                else:
                    picks_a_rows.append(dict(row))

            picks_b_rows: List[Dict[str, Any]] = []
            pick_swaps_b_rows: List[Dict[str, Any]] = []
            for asset_id in pick_b_all:
                row = conn.execute(
                    """
                    SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                           draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order,
                           draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                           draft_pick_frozen
                    FROM assets
                    WHERE id = ? AND asset_type = 'draft_pick'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                if normalize_pick_type(row["draft_pick_type"]) == "sold":
                    return None
                if asset_id in pick_swap_b:
                    pick_swaps_b_rows.append(dict(row))
                else:
                    picks_b_rows.append(dict(row))

            rights_a_rows: List[Dict[str, Any]] = []
            for asset_id in right_a:
                row = conn.execute(
                    """
                    SELECT id, team_id, label, detail, row_order
                    FROM assets
                    WHERE id = ? AND asset_type = 'player_right'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                rights_a_rows.append(dict(row))

            rights_b_rows: List[Dict[str, Any]] = []
            for asset_id in right_b:
                row = conn.execute(
                    """
                    SELECT id, team_id, label, detail, row_order
                    FROM assets
                    WHERE id = ? AND asset_type = 'player_right'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                rights_b_rows.append(dict(row))

            timestamp = now_iso()
            for player_id in ids_a:
                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                    (team_b["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                    (team_b["id"], int(mx) + 1, timestamp, player_id),
                )
            for row in players_a_rows:
                self._record_player_transaction(
                    conn,
                    row.get("profile_id"),
                    "trade",
                    f"Traspasado de {team_a['code']} a {team_b['code']}",
                    player_id=row.get("id"),
                    team_code=team_b["code"],
                    from_team_code=team_a["code"],
                    to_team_code=team_b["code"],
                    details={"player_name": row.get("name")},
                    created_at=timestamp,
                )

            for player_id in ids_b:
                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                    (team_a["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                    (team_a["id"], int(mx) + 1, timestamp, player_id),
                )
            for row in players_b_rows:
                self._record_player_transaction(
                    conn,
                    row.get("profile_id"),
                    "trade",
                    f"Traspasado de {team_b['code']} a {team_a['code']}",
                    player_id=row.get("id"),
                    team_code=team_a["code"],
                    from_team_code=team_b["code"],
                    to_team_code=team_a["code"],
                    details={"player_name": row.get("name")},
                    created_at=timestamp,
                )

            def move_pick(source_team: sqlite3.Row, target_team: sqlite3.Row, pick_row: Dict[str, Any]) -> None:
                actual_owner = self._pick_actual_owner(pick_row, str(source_team["code"]))
                source_pick_type = normalize_pick_type(pick_row.get("draft_pick_type"))
                pick_round = normalize_pick_round(pick_row.get("draft_round"))
                pick_year = parse_int(pick_row.get("year"))
                if source_pick_type == "conditional":
                    target_pick_type = "conditional"
                    target_original_owner = None
                    target_conditional_teams = pick_row.get("draft_pick_conditional_teams")
                else:
                    target_pick_type = "own" if actual_owner == str(target_team["code"]) else "acquired"
                    target_original_owner = None if target_pick_type == "own" else actual_owner
                    target_conditional_teams = None

                recipient_rows_cur = conn.execute(
                    """
                    SELECT id, draft_pick_type, original_owner, year, draft_round, draft_pick_conditional_teams
                    FROM assets
                    WHERE team_id = ? AND asset_type = 'draft_pick' AND CAST(COALESCE(year, '') AS INTEGER) = ?
                    """,
                    (target_team["id"], pick_year),
                )
                recipient_rows = [row_to_dict(recipient_rows_cur, row) for row in recipient_rows_cur.fetchall()]
                recipient_match = None
                for candidate in recipient_rows:
                    candidate_actual_owner = self._pick_actual_owner(candidate, str(target_team["code"]))
                    if candidate_actual_owner == actual_owner and normalize_pick_round(candidate.get("draft_round")) == pick_round:
                        recipient_match = candidate
                        break

                sold_label = pick_row.get("label") or f"{pick_round.upper()} pick"
                sold_detail = pick_row.get("detail")

                def update_pick_row(asset_id: int) -> None:
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = ?, original_owner = ?, draft_pick_sold_to = NULL,
                            draft_pick_conditional_teams = ?, label = ?, detail = ?,
                            draft_pick_restricted = ?, draft_pick_stepien_restricted = ?,
                            draft_pick_protected = ?, draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            asset_id,
                        ),
                    )

                if source_pick_type == "own":
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = 'sold', original_owner = ?, draft_pick_sold_to = ?,
                            draft_pick_conditional_teams = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (actual_owner, str(target_team["code"]), timestamp, pick_row["id"]),
                    )
                elif recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    if int(recipient_match["id"]) != int(pick_row["id"]):
                        conn.execute("DELETE FROM assets WHERE id = ?", (pick_row["id"],))
                    return
                else:
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        """
                        UPDATE assets
                        SET team_id = ?, row_order = ?, draft_pick_type = ?, original_owner = ?,
                            draft_pick_sold_to = NULL, draft_pick_conditional_teams = ?,
                            label = ?, detail = ?, draft_pick_restricted = ?,
                            draft_pick_stepien_restricted = ?, draft_pick_protected = ?,
                            draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_team["id"],
                            int(mx) + 1,
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            pick_row["id"],
                        ),
                    )
                    return

                if recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    return

                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (target_team["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    """
                    INSERT INTO assets (
                        team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                        draft_pick_type, draft_round, original_owner, exception_type,
                        draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                        draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                        created_at, updated_at
                    ) VALUES (?, ?, 'draft_pick', ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, ?, ?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (
                        target_team["id"],
                        int(mx) + 1,
                        pick_row.get("year"),
                        sold_label,
                        sold_detail,
                        target_pick_type,
                        pick_round,
                        target_original_owner,
                        1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                        target_conditional_teams,
                        1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                        timestamp,
                        timestamp,
                    ),
                )

            for pick_row in picks_a_rows:
                move_pick(team_a, team_b, pick_row)
            for pick_row in picks_b_rows:
                move_pick(team_b, team_a, pick_row)

            def move_player_rights(target_team: sqlite3.Row, right_rows: List[Dict[str, Any]]) -> None:
                for right_row in right_rows:
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        """
                        UPDATE assets
                        SET team_id = ?, row_order = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (target_team["id"], int(mx) + 1, timestamp, right_row["id"]),
                    )

            move_player_rights(team_b, rights_a_rows)
            move_player_rights(team_a, rights_b_rows)

            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            bucket = normalize_trade_bucket(trade_bucket or settings.get("trade_move_phase"))

            def player_move_count(rows: List[Dict[str, Any]], excluded_ids: set[int]) -> int:
                return sum(
                    1
                    for row in rows
                    if self._trade_asset_counts_as_move(
                        {"type": "player", "countsMove": int(row["id"]) not in excluded_ids},
                        current_year,
                    )
                )

            def pick_move_count(rows: List[Dict[str, Any]]) -> int:
                return sum(
                    1
                    for row in rows
                    if self._trade_asset_counts_as_move(
                        {"type": "pick", "draft_round": row.get("draft_round"), "year": row.get("year")},
                        current_year,
                    )
                )

            move_count_a = (
                player_move_count(players_a_rows, no_count_a)
                + player_move_count(players_b_rows, no_count_b)
                + pick_move_count(picks_a_rows)
                + pick_move_count(picks_b_rows)
            )
            move_count_b = (
                player_move_count(players_b_rows, no_count_b)
                + player_move_count(players_a_rows, no_count_a)
                + pick_move_count(picks_b_rows)
                + pick_move_count(picks_a_rows)
            )

            def pick_ref(pick_row: Dict[str, Any], source_team: sqlite3.Row, prefix: str = "") -> str:
                year = parse_int(pick_row.get("year"))
                year_label = str(year) if year is not None else "Sin año"
                round_label = normalize_pick_round(pick_row.get("draft_round")).upper()
                owner = self._pick_actual_owner(pick_row, str(source_team["code"]))
                return f"{prefix}{year_label} {round_label} ({owner})".strip()

            pick_refs_a = [pick_ref(row, team_a) for row in picks_a_rows]
            pick_refs_b = [pick_ref(row, team_b) for row in picks_b_rows]
            swap_refs_a = [pick_ref(row, team_a, "Swap ") for row in pick_swaps_a_rows]
            swap_refs_b = [pick_ref(row, team_b, "Swap ") for row in pick_swaps_b_rows]

            if move_count_a:
                self._insert_trade_move_logs(
                    conn,
                    team_id=int(team_a["id"]),
                    season_year=current_year,
                    requested_bucket=bucket,
                    move_count=move_count_a,
                    source_ref=f"{team_a['code']}-{team_b['code']}-{timestamp}",
                    note=f"Trade vs {team_b['code']}",
                    details={
                        "opponent": team_b["code"],
                        "players": [row["name"] for row in players_a_rows if int(row["id"]) not in no_count_a],
                        "players_received": [row["name"] for row in players_b_rows if int(row["id"]) not in no_count_b],
                        "players_excluded": [row["name"] for row in players_a_rows if int(row["id"]) in no_count_a],
                        "pick_count": len(picks_a_rows),
                        "pick_refs": pick_refs_a,
                        "pick_refs_received": pick_refs_b,
                        "swap_count": len(pick_swaps_a_rows),
                        "swap_refs": swap_refs_a,
                        "rights": [row.get("label") for row in rights_a_rows],
                    },
                    settings=settings,
                )
            if move_count_b:
                self._insert_trade_move_logs(
                    conn,
                    team_id=int(team_b["id"]),
                    season_year=current_year,
                    requested_bucket=bucket,
                    move_count=move_count_b,
                    source_ref=f"{team_b['code']}-{team_a['code']}-{timestamp}",
                    note=f"Trade vs {team_a['code']}",
                    details={
                        "opponent": team_a["code"],
                        "players": [row["name"] for row in players_b_rows if int(row["id"]) not in no_count_b],
                        "players_received": [row["name"] for row in players_a_rows if int(row["id"]) not in no_count_a],
                        "players_excluded": [row["name"] for row in players_b_rows if int(row["id"]) in no_count_b],
                        "pick_count": len(picks_b_rows),
                        "pick_refs": pick_refs_b,
                        "pick_refs_received": pick_refs_a,
                        "swap_count": len(pick_swaps_b_rows),
                        "swap_refs": swap_refs_b,
                        "rights": [row.get("label") for row in rights_b_rows],
                    },
                    settings=settings,
                )

            if owns_connection:
                conn.commit()
            return {
                "ok": True,
                "trade_bucket": bucket,
                "team_a": {"code": team_a["code"], "move_count": move_count_a},
                "team_b": {"code": team_b["code"], "move_count": move_count_b},
                "players_a": [row["name"] for row in players_a_rows],
                "players_b": [row["name"] for row in players_b_rows],
                "pick_count_a": len(picks_a_rows),
                "pick_count_b": len(picks_b_rows),
                "pick_refs_a": pick_refs_a,
                "pick_refs_b": pick_refs_b,
                "swap_count_a": len(pick_swaps_a_rows),
                "swap_count_b": len(pick_swaps_b_rows),
                "swap_refs_a": swap_refs_a,
                "swap_refs_b": swap_refs_b,
                "right_count_a": len(rights_a_rows),
                "right_count_b": len(rights_b_rows),
            }

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
    _public_backup_metadata = staticmethod(public_backup_metadata)
    _spreadsheet_rows_from_payload = staticmethod(_spreadsheet_rows_from_payload)

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

    def _google_enabled(self) -> bool:
        return self._google_oauth_client().enabled()

    def _google_oauth_client(self) -> GoogleOAuthIntegration:
        return GoogleOAuthIntegration(
            GoogleOAuthConfig(
                client_id=self.google_client_id,
                client_secret=self.google_client_secret,
                redirect_uri=self.google_redirect_uri,
            ),
            opener=urlopen,
        )

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

    def _discord_text(self, value: Any, limit: int) -> str:
        return truncate_text(value, limit)

    def _discord_client(self) -> DiscordIntegration:
        return DiscordIntegration(
            DiscordConfig(
                webhook_url=self.discord_webhook_url,
                bot_token=self.discord_bot_token,
                api_base_url=self.discord_api_base_url,
                timeout_seconds=self.discord_timeout_seconds,
            ),
            opener=urlopen,
        )

    def _openai_client(self) -> OpenAIIntegration:
        return OpenAIIntegration(
            OpenAIConfig(
                api_key=self.openai_api_key,
                text_model=self.openai_text_model,
                text_timeout_seconds=self.openai_text_timeout_seconds,
                image_model=self.openai_image_model,
                image_size=self.openai_image_size,
                image_quality=self.openai_image_quality,
                image_format=self.openai_image_format,
                image_timeout_seconds=self.openai_image_timeout_seconds,
                reference_image_timeout_seconds=self.openai_reference_image_timeout_seconds,
                reference_image_max_bytes=self.openai_reference_image_max_bytes,
                image_generation_enabled=self.discord_image_notifications_enabled,
            ),
            opener=urlopen,
            log_error=self.log_error,
        )

    def _team_image_colors(self, team_code: str) -> str:
        return TEAM_IMAGE_COLORS.get(str(team_code or "").upper(), "#0F766E, #111827")

    def _http_error_excerpt(self, err: HTTPError, limit: int = 1200) -> str:
        return http_error_excerpt(err, limit)

    def _news_image_prompt(
        self,
        headline: str,
        description: str,
        *,
        teams: Optional[List[str]] = None,
        players: Optional[List[str]] = None,
        context: Optional[str] = None,
        team_name: Optional[str] = None,
        team_code: Optional[str] = None,
        player_name: Optional[str] = None,
        secondary_headline: Optional[str] = None,
        additional_details: Optional[str] = None,
        transaction_type: Optional[str] = None,
        use_player_reference: bool = False,
    ) -> str:
        if use_player_reference:
            resolved_team_code = str(team_code or (teams or [""])[0] or "").upper()
            resolved_team_name = str(team_name or resolved_team_code or "ANBA").strip()
            resolved_player_name = str(player_name or (players or [""])[0] or "Jugador").strip()
            return f"""Create a professional NBA social media breaking news graphic using the uploaded player image as the primary reference.

IMPORTANT PLAYER REFERENCE INSTRUCTIONS

- Use the uploaded photo as the source reference.
- Preserve the player's facial features, hair, skin tone, expression, body proportions, and overall likeness accurately.
- The player must remain clearly recognizable as the same person from the reference image.
- Do not alter age, ethnicity, facial structure, hairstyle, or physical characteristics.
- Remove the original team uniform and replace it with an authentic, realistic {resolved_team_name} uniform.
- Jersey colors, typography, trim, logos, and styling should accurately reflect the team's current branding.
- Maintain realistic jersey fabric, lighting, wrinkles, and athletic appearance.
- The player should appear as if photographed professionally while playing for {resolved_team_name}.

DESIGN OBJECTIVE

Create a premium NBA transaction announcement graphic suitable for major basketball news accounts on Twitter/X, Instagram, Threads, and sports media websites.

VISUAL STYLE

- Professional NBA media graphic
- Bleacher Report quality
- ESPN social media quality
- House of Highlights quality
- Courtside Buzz style presentation
- Modern sports marketing creative
- Premium Photoshop compositing
- Editorial sports poster
- High-end sports journalism graphic
- Viral social media design
- Clean information hierarchy
- Photorealistic athlete rendering
- Ultra-sharp details
- Dynamic contrast
- Dramatic lighting
- Premium typography

LAYOUT

- Landscape format (16:9)
- Player positioned on the right side occupying approximately 50-60% of the composition
- Large headline typography on the left side
- Team logo integrated into the background at low opacity
- Team branding incorporated throughout the design
- Strong focal point on the player
- Clean visual hierarchy optimized for mobile viewing
- Professional spacing and alignment

BACKGROUND

- Dark textured sports background
- Arena atmosphere
- Subtle smoke and lighting effects
- Team color gradients
- Depth and cinematic lighting
- Modern sports poster aesthetic

TEAM BRANDING

Team:
{resolved_team_name}

Primary Colors:
{self._team_image_colors(resolved_team_code)}

Use the team's visual identity consistently throughout:
- Color palette
- Logo integration
- Background treatments
- Typography accents
- Graphic elements

HEADLINE TEXT

NBA NEWS

{resolved_team_name}

{headline}

SUBHEADLINE

{secondary_headline or description}

PLAYER NAME

{resolved_player_name}

OPTIONAL DETAILS

{additional_details or context or ""}

TRANSACTION CONTEXT

Transaction Type:
{transaction_type or "Transaction"}

Examples:
- Trade
- Signing
- Re-signing
- Contract Extension
- Waived
- Released
- Team Option Exercised
- Team Option Declined
- Qualifying Offer Rejected
- Two-Way Signing
- Conversion to Standard Contract
- Buyout
- Draft Rights Acquired
- Contract Guaranteed
- Contract Non-Guaranteed
- Free Agency Signing

QUALITY REQUIREMENTS

- Photorealistic
- Sports media publication quality
- Crisp typography
- Authentic NBA branding aesthetic
- Realistic jersey replacement
- No distorted anatomy
- No cartoon appearance
- No AI-art look
- Premium Photoshop-style finish
- Suitable for posting directly by an NBA news account
- Highly shareable social media design"""

        team_text = ", ".join(str(t).upper() for t in teams or [] if str(t or "").strip()) or "ANBA"
        player_text = ", ".join(str(p) for p in players or [] if str(p or "").strip())
        parts = [
            "Create a landscape professional basketball news graphic for a Discord/social post.",
            "Use an editorial transaction-news style with dramatic arena lighting, premium sports typography, and team-color accents.",
            f"Main headline text exactly: {headline}",
            f"Post context: {description}",
            f"Relevant team(s): {team_text}.",
            "Avoid official league marks, sponsor logos, watermarks, and unrelated extra text.",
            "Do not include a fake scoreboard or stat table. Leave enough clean space around the headline for mobile readability.",
        ]
        if player_text:
            parts.append(
                f"Relevant player name(s): {player_text}. If showing a player, use a generic basketball player in team-inspired colors."
            )
        if context:
            parts.append(f"Additional context: {context}")
        return "\n".join(parts)

    def _generate_openai_image(
        self,
        prompt: str,
        *,
        reference_image_url: Optional[str] = None,
        fallback_prompt: Optional[str] = None,
    ) -> Optional[tuple[bytes, str, str]]:
        return self._openai_client().generate_image(
            prompt,
            reference_image_url=reference_image_url,
            fallback_prompt=fallback_prompt,
        )

    def _openai_text_response(self, system_prompt: str, user_prompt: str, max_output_tokens: int = 700) -> Optional[str]:
        return self._openai_client().text_response(system_prompt, user_prompt, max_output_tokens)

    def _owner_interview_service(self) -> OwnerInterviewCompositionService:
        return OwnerInterviewCompositionService(self._openai_text_response)

    def _discord_webhook_url(
        self,
        webhook_url: str,
        *,
        thread_id: Optional[str] = None,
        wait: bool = False,
    ) -> str:
        return DiscordIntegration.webhook_url(webhook_url, thread_id=thread_id, wait=wait)

    def _post_discord_json(
        self,
        payload: Dict[str, Any],
        *,
        webhook_url: Optional[str] = None,
        thread_name: Optional[str] = None,
        thread_id: Optional[str] = None,
        wait: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return self._discord_client().post_webhook_json(
            payload,
            webhook_url=webhook_url,
            thread_name=thread_name,
            thread_id=thread_id,
            wait=wait,
        )

    def _post_discord_bot_json(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        *,
        method: str = "POST",
    ) -> Optional[Dict[str, Any]]:
        return self._discord_client().post_bot_json(endpoint, payload, method=method)

    def _send_discord_dm(self, user_id: str, payload: Dict[str, Any]) -> bool:
        clean_user_id = re.sub(r"\D+", "", str(user_id or ""))
        if not clean_user_id:
            return False
        channel = self._post_discord_bot_json(
            "/users/@me/channels",
            {"recipient_id": clean_user_id},
        )
        channel_id = str((channel or {}).get("id") or "").strip()
        if not channel_id:
            return False
        self._post_discord_bot_json(f"/channels/{channel_id}/messages", payload)
        return True

    def _post_discord_multipart(
        self,
        payload: Dict[str, Any],
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> None:
        self._discord_client().post_webhook_multipart(payload, file_bytes, filename, mime_type)

    def _post_discord_bot_multipart(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> Optional[Dict[str, Any]]:
        return self._discord_client().post_bot_multipart(endpoint, payload, file_bytes, filename, mime_type)

    def _post_press_article(
        self,
        text: str,
        article_url: str,
        image_attachment: tuple[bytes, str, str],
    ) -> Dict[str, Any]:
        full_article_url = str(article_url or "").strip()
        file_bytes, filename, mime_type = image_attachment
        payload = NotificationCompositionService.press_article_payload(text, full_article_url, filename)
        if not self.discord_notifications_enabled:
            raise RuntimeError("discord_notifications_disabled")
        if not self.discord_bot_token:
            raise RuntimeError("discord_bot_token_required")
        if not self.discord_press_channel_id:
            raise RuntimeError("discord_press_channel_required")

        message = self._post_discord_bot_multipart(
            f"/channels/{self.discord_press_channel_id}/messages",
            payload,
            file_bytes,
            filename,
            mime_type,
        )
        message_id = str((message or {}).get("id") or "")
        return {
            "channel_id": self.discord_press_channel_id,
            "message_id": message_id,
            "article_url": full_article_url,
        }

    def _notify_discord(
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
        if not self.discord_notifications_enabled or not self.discord_webhook_url:
            return False

        image_attachment = None
        if custom_image:
            image_attachment = self._discord_custom_image_attachment(custom_image)
        if not image_attachment and generate_image:
            image_attachment = self._generate_openai_image(
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
            role_id=self.discord_role_id,
            image_filename=image_filename,
        )
        embed = payload["embeds"][0]

        try:
            if image_attachment:
                file_bytes, filename, mime_type = image_attachment
                try:
                    self._post_discord_multipart(payload, file_bytes, filename, mime_type)
                    return True
                except (HTTPError, URLError, TimeoutError, OSError) as upload_err:
                    self.log_error("Discord image notification failed; retrying text-only: %s", upload_err)
                    embed.pop("image", None)
                    self._post_discord_json(payload)
                    return True
            else:
                self._post_discord_json(payload)
                return True
        except (HTTPError, URLError, TimeoutError, OSError) as err:
            self.log_error("Discord notification failed: %s", err)
            return False

    def _deliver_event_notification(
        self,
        event: EventNotification,
        *,
        generate_image: bool,
        custom_image: Optional[Dict[str, Any]],
    ) -> bool:
        image_prompt = self._news_image_prompt(**event.image_prompt)
        fallback_prompt = (
            self._news_image_prompt(**event.image_fallback_prompt)
            if event.image_fallback_prompt
            else None
        )
        return self._notify_discord(
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

    def _discord_notify_requested(self, payload: Dict[str, Any]) -> bool:
        if "notify_discord" not in payload:
            return True
        return parse_bool(payload.get("notify_discord"))

    def _discord_image_requested(self, payload: Dict[str, Any]) -> bool:
        if "generate_discord_image" not in payload:
            return True
        return parse_bool(payload.get("generate_discord_image"))

    def _discord_custom_image_attachment(self, payload: Any) -> Optional[tuple[bytes, str, str]]:
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
        if mime_type not in DISCORD_CUSTOM_IMAGE_ALLOWED_MIME_TYPES or not base64_text:
            self.log_error("Discord custom image ignored: unsupported image type.")
            return None
        if len(base64_text) > CUSTOM_IMAGE_MAX_BASE64_CHARS:
            self.log_error("Discord custom image ignored: encoded payload is too large.")
            return None
        compact_base64 = re.sub(r"\s+", "", base64_text)
        if len(compact_base64) > CUSTOM_IMAGE_MAX_BASE64_CHARS:
            self.log_error("Discord custom image ignored: encoded payload is too large.")
            return None
        try:
            file_bytes = base64.b64decode(compact_base64, validate=True)
        except ValueError:
            self.log_error("Discord custom image ignored: invalid base64 data.")
            return None
        if not file_bytes:
            return None
        if len(file_bytes) > CUSTOM_IMAGE_MAX_BYTES:
            self.log_error("Discord custom image ignored: file is larger than 8 MB.")
            return None
        try:
            detected_ext, detected_mime = detect_safe_image_type(
                file_bytes,
                mime_type,
                DISCORD_CUSTOM_IMAGE_ALLOWED_MIME_TYPES,
            )
        except ValueError:
            self.log_error("Discord custom image ignored: image bytes do not match an allowed type.")
            return None
        raw_filename = str(payload.get("filename") or "notification-image").strip()
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_filename).strip("._-") or "notification-image"
        safe_stem = re.sub(r"\.(png|jpe?g|webp|gif)$", "", safe_stem, flags=re.IGNORECASE)[:80] or "notification-image"
        filename = f"{safe_stem}.{detected_ext}"
        return file_bytes, filename, detected_mime

    def _notify_player_cut(
        self,
        result: Dict[str, Any],
        *,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = NotificationCompositionService.player_cut(result)
        self._deliver_event_notification(
            event,
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def _dispatch_outbox_events(self, event_ids: Optional[List[int]]) -> List[int]:
        delivered: List[int] = []
        for raw_event_id in event_ids or []:
            event_id = parse_int(raw_event_id)
            if event_id is None:
                continue
            event = self.db.get_outbox_event(event_id)
            if not event:
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            try:
                if event_type == "discord.free_agent_signed":
                    player = self.db.get_player_record(payload.get("player_id"))
                    if not player:
                        self.db.mark_outbox_event_failed(event_id, "player_not_found")
                        continue
                    offer_payload = payload.get("offer_payload") if isinstance(payload.get("offer_payload"), dict) else {}
                    custom_image = payload.get("custom_image") if isinstance(payload.get("custom_image"), dict) else None
                    sent = self._notify_free_agent_signed(
                        player,
                        offer_payload=offer_payload,
                        offer_type=payload.get("offer_type"),
                        generate_image=parse_bool(payload.get("generate_image")),
                        custom_image=custom_image,
                    )
                    if sent:
                        self.db.mark_outbox_event_succeeded(event_id)
                        delivered.append(int(event_id))
                    else:
                        self.db.mark_outbox_event_failed(event_id, "delivery_returned_false")
                    continue
                if event_type == "discord.trade_processed":
                    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
                    if not result:
                        self.db.mark_outbox_event_failed(event_id, "result_missing")
                        continue
                    custom_image = payload.get("custom_image") if isinstance(payload.get("custom_image"), dict) else None
                    self._notify_trade_processed(
                        result,
                        generate_image=parse_bool(payload.get("generate_image")),
                        custom_image=custom_image,
                    )
                    self.db.mark_outbox_event_succeeded(event_id)
                    delivered.append(int(event_id))
                    continue
                self.db.mark_outbox_event_failed(event_id, f"unknown_event_type:{event_type}")
            except Exception as err:
                self.log_error("Outbox event delivery failed id=%s type=%s: %s", event_id, event_type, err)
                self.db.mark_outbox_event_failed(event_id, str(err)[:500])
        return delivered

    def _notify_free_agent_signed(
        self,
        player: Dict[str, Any],
        *,
        offer_payload: Optional[Dict[str, Any]] = None,
        offer_type: Optional[str] = None,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> bool:
        salary_summary = ""
        if isinstance(offer_payload, dict) and isinstance(offer_payload.get("salary_by_season"), dict):
            salary_summary = self._contract_offer_salary_lines(offer_payload)
        if not salary_summary or salary_summary == "Sin importes detallados":
            salary_lines: List[str] = []
            for season in range(CAP_FORECAST_MIN_YEAR, CAP_FORECAST_MAX_YEAR + 1):
                salary_text = str(player.get(f"salary_{season}_text") or "").strip()
                if salary_text:
                    amount = parse_amount_like(salary_text)
                    if amount is not None:
                        salary_text = f"{int(round(amount)):,}".replace(",", ".")
                    option_text = str(player.get(f"option_{season}") or "").strip().upper()
                    if option_text:
                        salary_text = f"{salary_text} ({option_text})"
                    salary_lines.append(f"{season_label(season)}: {salary_text}")
            salary_summary = "\n".join(salary_lines[:3]) or "Sin salario registrado"
        event = NotificationCompositionService.free_agent_signed(
            player,
            salary_summary=salary_summary,
            offer_type=offer_type,
        )
        return self._deliver_event_notification(
            event,
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def _contract_offer_salary_lines(self, payload: Dict[str, Any]) -> str:
        raw_by_season = payload.get("salary_by_season")
        raw_options_by_season = payload.get("option_by_season")
        options_by_season = raw_options_by_season if isinstance(raw_options_by_season, dict) else {}

        def value_with_option(season: int, value: str) -> str:
            option = str(
                options_by_season.get(str(season))
                if str(season) in options_by_season
                else options_by_season.get(season, "")
            ).strip().upper()
            return f"{value} ({option})" if option else value

        lines: List[str] = []
        if isinstance(raw_by_season, dict):
            for season_key in sorted(raw_by_season.keys(), key=lambda value: parse_int(str(value)) or 9999):
                season = parse_int(str(season_key))
                if season is None:
                    continue
                value = str(raw_by_season.get(season_key) or "").strip()
                if value:
                    lines.append(f"{season_label(season)}: {value_with_option(season, value)}")
        for season in range(CAP_FORECAST_MIN_YEAR, CAP_FORECAST_MAX_YEAR + 1):
            value = str(payload.get(f"salary_{season}") or "").strip()
            if value and not any(line.startswith(season_label(season)) for line in lines):
                lines.append(f"{season_label(season)}: {value_with_option(season, value)}")
        return "\n".join(lines[:8]) or "Sin importes detallados"

    def _free_agency_service(self) -> FreeAgencyService:
        return FreeAgencyService(
            self.db,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
            cap_hold_source=FREE_AGENT_SOURCE_CAP_HOLD,
        )

    def _waiver_service(self) -> WaiverService:
        return WaiverService(self.db)

    def _draft_service(self) -> DraftService:
        return DraftService(self.db)

    def _season_rollover_service(self) -> SeasonRolloverService:
        return SeasonRolloverService(
            self.db,
            contract_min_year=PLAYER_CONTRACT_MIN_YEAR,
            contract_max_start_year=PLAYER_CONTRACT_MAX_START_YEAR,
        )

    def _player_identity_service(self) -> PlayerIdentityService:
        return PlayerIdentityService(
            self.db,
            contract_seasons=PLAYER_CONTRACT_SEASONS,
        )

    def _free_agent_offer_is_renewal(self, free_agent: Dict[str, Any], team_code: str) -> bool:
        return self._free_agency_service().is_renewal(free_agent, team_code)

    def _free_agent_offer_bird_rights_code(self, free_agent: Dict[str, Any]) -> str:
        return self._free_agency_service().bird_rights_code(free_agent)

    def _free_agent_offer_start_season(self, settings: Dict[str, Any]) -> int:
        return self._free_agency_service().offer_start_season(settings)

    def _settings_salary_cap_for_season(self, settings: Dict[str, Any], season: int) -> float:
        return self._free_agency_service().salary_cap_for_season(settings, season)

    def _free_agent_offer_minimum_amount(
        self,
        free_agent: Dict[str, Any],
        settings: Dict[str, Any],
        season: int,
        contract_year: int,
        contract_type: str,
    ) -> float:
        return self._free_agency_service().minimum_amount(
            free_agent, settings, season, contract_year, contract_type
        )

    def _free_agent_offer_maximum_amount(
        self,
        free_agent: Dict[str, Any],
        settings: Dict[str, Any],
        season: int,
        contract_type: str,
    ) -> float:
        return self._free_agency_service().maximum_amount(free_agent, settings, season, contract_type)

    def _free_agent_offer_salary_text(self, value: float) -> str:
        return self._free_agency_service().salary_text(value)

    def _free_agent_offer_post_contract_rights_marker(
        self,
        offer_payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._free_agency_service().post_contract_rights_marker(offer_payload)

    def _free_agent_offer_role_options(self) -> tuple[str, ...]:
        return self._free_agency_service().ROLE_OPTIONS

    def _normalize_free_agent_offer_role(self, raw_role: Any) -> str:
        return self._free_agency_service().normalize_role(raw_role)

    def _validate_and_normalize_free_agent_offer_payload(
        self,
        free_agent: Dict[str, Any],
        team_code: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._free_agency_service().normalize_offer(free_agent, team_code, payload)

    def _player_payload_from_free_agent_offer(
        self,
        free_agent: Dict[str, Any],
        offer_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._free_agency_service().player_payload_from_offer(free_agent, offer_payload)

    def _notify_free_agent_offer(
        self,
        free_agent: Dict[str, Any],
        team_code: str,
        payload: Dict[str, Any],
        offer_type: Optional[str] = None,
        agent_discord_id: Optional[str] = None,
    ) -> Dict[str, bool]:
        result = {
            "thread_sent": False,
            "agent_dm_sent": False,
            "agent_discord_configured": False,
        }
        webhook_url = self.discord_free_agent_offers_webhook_url or self.discord_webhook_url
        if not self.discord_notifications_enabled:
            return result
        settings = self.db.get_settings()
        offer_role_ping_enabled = parse_bool(settings.get("discord_free_agent_offer_role_ping_enabled", "1"))
        player_name = str(free_agent.get("name") or "Jugador")
        team = normalize_team_code(team_code) or str(team_code or "").upper()
        contract_type = str(payload.get("contract_type") or "").strip() or "Sin tipo definido"
        years = parse_int(payload.get("years"))
        years_text = f"{years} año(s)" if years is not None and years > 0 else "Sin duración definida"
        raise_percent = parse_amount_like(payload.get("annual_raise_percent"))
        if raise_percent is not None and raise_percent > 0:
            raise_text = f"Subidas {raise_percent:g}%"
        elif raise_percent is not None and raise_percent < 0:
            raise_text = f"Bajadas {abs(raise_percent):g}%"
        else:
            raise_text = "Sin subidas"
        salary_lines = self._contract_offer_salary_lines(payload)
        notes = str(payload.get("notes") or "").strip()
        role = str(payload.get("role") or "").strip()
        thread_name = self._discord_text(player_name, 100) or "Jugador"
        normalized_offer_type = str(offer_type or "").strip().lower()
        is_renewal = normalized_offer_type == "renewal" or (
            not normalized_offer_type and self._free_agent_offer_is_renewal(free_agent, team)
        )
        offer_label = "Oferta de renovación" if is_renewal else "Oferta"
        agent_name = str(free_agent.get("agent") or "").strip() or "Agente sin asignar"
        public_embed: Dict[str, Any] = {
            "title": "Oferta recibida",
            "description": (
                "Se ha creado este hilo automáticamente al recibir una oferta por el jugador. "
                "El agente posteará aquí los detalles cuando lo considere necesario."
            ),
            "color": 0x0F766E,
        }
        private_embed: Dict[str, Any] = {
            "title": self._discord_text(
                f"Oferta de renovación de {team} por {player_name}"
                if is_renewal
                else f"Oferta de {team} por {player_name}",
                256,
            ),
            "description": "Detalles privados de la oferta enviada desde agentes libres.",
            "color": 0x0F766E,
            "fields": [
                {"name": "Equipo", "value": team, "inline": True},
                {"name": "Jugador", "value": self._discord_text(player_name, 1024), "inline": True},
                {"name": "Agente", "value": self._discord_text(agent_name, 1024), "inline": True},
                {"name": "Modalidad", "value": offer_label, "inline": True},
                {"name": "Tipo", "value": self._discord_text(contract_type, 1024), "inline": True},
                {"name": "Duración", "value": years_text, "inline": True},
                {"name": "Subidas", "value": raise_text, "inline": True},
                {"name": "Rol", "value": self._discord_text(role or "Sin rol definido", 1024), "inline": True},
                {"name": "Importes", "value": self._discord_text(salary_lines, 1024), "inline": False},
            ],
        }
        if notes:
            private_embed["fields"].append({"name": "Comentarios", "value": self._discord_text(notes, 1024), "inline": False})
        payload_json = {
            "embeds": [public_embed],
            "allowed_mentions": {"parse": []},
        }
        if self.discord_free_agent_offers_forum_tag_ids:
            payload_json["applied_tags"] = self.discord_free_agent_offers_forum_tag_ids
        if webhook_url:
            try:
                existing_thread = self.db.get_free_agent_offer_thread(free_agent)
                if existing_thread and existing_thread.get("thread_id"):
                    try:
                        thread_payload_json = dict(payload_json)
                        thread_payload_json.pop("applied_tags", None)
                        self._post_discord_json(
                            thread_payload_json,
                            webhook_url=webhook_url,
                            thread_id=str(existing_thread.get("thread_id")),
                        )
                        result["thread_sent"] = True
                    except HTTPError as err:
                        if err.code not in {400, 404, 405}:
                            raise
                        self.log_error(
                            "Discord offer thread reuse failed; creating new thread: %s",
                            self._http_error_excerpt(err),
                        )
                if not result["thread_sent"]:
                    try:
                        creation_payload_json = {
                            **payload_json,
                            "allowed_mentions": dict(payload_json.get("allowed_mentions") or {}),
                        }
                        offer_role_id = re.sub(r"\D+", "", str(self.discord_free_agent_offers_role_id or ""))
                        if offer_role_id and offer_role_ping_enabled:
                            creation_payload_json["content"] = f"<@&{offer_role_id}>"
                            creation_payload_json["allowed_mentions"]["parse"] = []
                            creation_payload_json["allowed_mentions"]["roles"] = [offer_role_id]
                        response = self._post_discord_json(
                            creation_payload_json,
                            webhook_url=webhook_url,
                            thread_name=thread_name,
                            wait=True,
                        )
                        if isinstance(response, dict):
                            thread_id = response.get("channel_id")
                            if thread_id:
                                self.db.upsert_free_agent_offer_thread(free_agent, str(thread_id), thread_name)
                        result["thread_sent"] = True
                    except HTTPError as err:
                        if err.code not in {400, 404, 405}:
                            raise
                        self.log_error("Discord offer thread creation failed: %s", self._http_error_excerpt(err))
            except (HTTPError, URLError, TimeoutError, OSError) as err:
                if isinstance(err, HTTPError):
                    self.log_error("Discord free-agent offer notification failed: %s", self._http_error_excerpt(err))
                else:
                    self.log_error("Discord free-agent offer notification failed: %s", err)
        clean_agent_discord_id = re.sub(r"\D+", "", str(agent_discord_id or ""))
        result["agent_discord_configured"] = bool(clean_agent_discord_id)
        if clean_agent_discord_id:
            if not self.discord_bot_token:
                self.log_error("Discord free-agent offer DM failed: DISCORD_BOT_TOKEN is not configured")
            else:
                try:
                    result["agent_dm_sent"] = self._send_discord_dm(
                        clean_agent_discord_id,
                        {
                            "embeds": [private_embed],
                            "allowed_mentions": {"parse": []},
                        },
                    )
                except (HTTPError, URLError, TimeoutError, OSError) as err:
                    if isinstance(err, HTTPError):
                        self.log_error("Discord free-agent offer DM failed: %s", self._http_error_excerpt(err))
                    else:
                        self.log_error("Discord free-agent offer DM failed: %s", err)
                except RuntimeError as err:
                    self.log_error("Discord free-agent offer DM failed: %s", err)
        return result

    def _free_agent_agent_discord_id(self, free_agent: Dict[str, Any]) -> Optional[str]:
        settings_payload = public_settings_payload(self.db.get_settings())
        rep_map = settings_payload.get("free_agent_rep_discord_ids")
        agent_name = str(free_agent.get("agent") or "").strip()
        if isinstance(rep_map, dict) and agent_name:
            for configured_name, configured_id in rep_map.items():
                if str(configured_name).strip().casefold() == agent_name.casefold():
                    return str(configured_id)
        return None

    def _notify_free_agent_negotiation(
        self,
        free_agent: Dict[str, Any],
        team_code: str,
        payload: Dict[str, Any],
        agent_discord_id: Optional[str],
    ) -> bool:
        if not self.discord_notifications_enabled:
            return False
        clean_agent_discord_id = re.sub(r"\D+", "", str(agent_discord_id or ""))
        if not clean_agent_discord_id:
            return False
        if not self.discord_bot_token:
            self.log_error("Discord free-agent negotiation DM failed: DISCORD_BOT_TOKEN is not configured")
            return False
        player_name = str(free_agent.get("name") or "Jugador")
        agent_name = str(free_agent.get("agent") or payload.get("agent") or "").strip() or "Agente sin asignar"
        team = normalize_team_code(team_code) or str(team_code or "").upper()
        economic_offer = str(payload.get("economic_offer") or "").strip() or "Sin oferta económica detallada"
        role_offer = str(payload.get("role_offer") or "").strip() or "Sin rol detallado"
        comments = str(payload.get("comments") or "").strip() or "Sin comentarios adicionales"
        payload_json = NotificationCompositionService.free_agent_negotiation_payload(
            team_code=team,
            player_name=player_name,
            agent_name=agent_name,
            economic_offer=economic_offer,
            role_offer=role_offer,
            comments=comments,
        )
        try:
            return self._send_discord_dm(clean_agent_discord_id, payload_json)
        except (HTTPError, URLError, TimeoutError, OSError) as err:
            if isinstance(err, HTTPError):
                self.log_error("Discord free-agent negotiation DM failed: %s", self._http_error_excerpt(err))
            else:
                self.log_error("Discord free-agent negotiation DM failed: %s", err)
            return False
        except RuntimeError as err:
            self.log_error("Discord free-agent negotiation DM failed: %s", err)
            return False

    def _notify_trade_processed(
        self,
        result: Dict[str, Any],
        *,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = NotificationCompositionService.trade_processed(result)
        self._deliver_event_notification(
            event,
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def _notify_draft_pick_selection(
        self,
        request: Dict[str, Any],
        *,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = NotificationCompositionService.draft_pick_selection(
            request,
            self._draft_service().current_year(),
        )
        self._deliver_event_notification(
            event,
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def _notify_contract_option_action(
        self,
        player: Dict[str, Any],
        season: int,
        option_value: str,
        action: str,
        *,
        generate_image: bool = True,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = NotificationCompositionService.contract_option_action(
            player,
            season,
            option_value,
            action,
        )
        self._deliver_event_notification(
            event,
            generate_image=generate_image,
            custom_image=custom_image,
        )

    def _notify_bird_rights_renounced(
        self,
        player: Dict[str, Any],
        season: int,
        rights_value: str,
        *,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = NotificationCompositionService.bird_rights_renounced(
            player,
            season,
            rights_value,
        )
        self._deliver_event_notification(
            event,
            generate_image=generate_image,
            custom_image=custom_image,
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
