"""Application-specific HTTP payload validation."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..domain._values import parse_amount_like, parse_int
    from ..routing import (
        RequestValidationError,
        validate_boolean_field,
        validate_json_structure as validate_json_structure_limits,
        validate_number_range,
        validate_payload_fields,
        validate_team_code_field,
        validate_text_field,
    )
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_amount_like, parse_int
    from routing import (
        RequestValidationError,
        validate_boolean_field,
        validate_json_structure as validate_json_structure_limits,
        validate_number_range,
        validate_payload_fields,
        validate_team_code_field,
        validate_text_field,
    )

JSON_MAX_DEPTH = 16
JSON_MAX_CONTAINER_ITEMS = 10_000
JSON_MAX_OBJECT_FIELDS = 2_048
JSON_MAX_TOTAL_NODES = 100_000
JSON_MAX_KEY_LENGTH = 128
PLAYER_CONTRACT_SEASONS = tuple(range(2025, 2032))
FREE_AGENT_ROLE_VALUES = {
    "Titular", "Sexto hombre", "Minutos de rotación (10-20)",
    "Minutos de rotación (0-9)", "Fuera de la rotación",
}
GM_OPTION_REQUEST_FIELDS = {"player_id", "option_field", "option_value", "action"}
GM_BIRD_RENOUNCE_FIELDS = {"player_id", "season_year", "rights_value"}
FREE_AGENT_OFFER_FIELDS = {
    "team_code", "contract_type", "years", "annual_raise_percent", "role",
    "salary_by_season", "option_by_season", "notes",
}
FREE_AGENT_NEGOTIATION_FIELDS = {"team_code", "economic_offer", "role_offer", "comments"}
WAIVER_CLAIM_FIELDS = {"team_code", "contingent_cut_player_id"}
COADMIN_VOTE_SUBMIT_FIELDS = {"scores"}
ADMIN_DECISION_FIELDS = {
    "decision", "note", "notify_discord", "generate_discord_image", "discord_custom_image",
}

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

