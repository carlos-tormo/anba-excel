"""Remaining administrative PATCH route functions."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import ParseResult

try:
    from ..auth.policies import normalize_team_code, normalize_team_codes
    from ..domain.exceptions import normalize_apron_hard_cap
    from ..domain.trade_rules import normalize_move_phase
    from ..domain_rules import (
        CAP_FORECAST_MAX_YEAR,
        CAP_FORECAST_MIN_YEAR,
        parse_bool,
        parse_float,
        parse_free_agent_rep_discord_ids,
        parse_int,
        public_settings_payload,
    )
    from ..routing import (
        RequestValidationError,
        exact_route,
        predicate_route,
        prefix_route,
        validate_boolean_field,
        validate_payload_fields,
        validate_text_field,
    )
    from ..services.free_agency import OfferDecisionOptions
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code, normalize_team_codes
    from domain.exceptions import normalize_apron_hard_cap
    from domain.trade_rules import normalize_move_phase
    from domain_rules import (
        CAP_FORECAST_MAX_YEAR,
        CAP_FORECAST_MIN_YEAR,
        parse_bool,
        parse_float,
        parse_free_agent_rep_discord_ids,
        parse_int,
        public_settings_payload,
    )
    from routing import (
        RequestValidationError,
        exact_route,
        predicate_route,
        prefix_route,
        validate_boolean_field,
        validate_payload_fields,
        validate_text_field,
    )
    from services.free_agency import OfferDecisionOptions


FREE_AGENT_TYPE_UNRESTRICTED = "No restringido"
PLAYER_CONTRACT_SEASONS = [2025, 2026, 2027, 2028, 2029, 2030, 2031]
PLAYER_CONTRACT_MIN_YEAR = min(PLAYER_CONTRACT_SEASONS)
PLAYER_CONTRACT_MAX_START_YEAR = 2026
CONTRACT_TERMINATING_OPTION_VALUES = {"TO", "PO"}
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
for _season in PLAYER_CONTRACT_SEASONS:
    PLAYER_UPDATE_TEXT_FIELDS.update({
        f"salary_{_season}_text", f"salary_{_season}_guaranteed_text",
        f"salary_{_season}_note_text", f"option_{_season}",
    })
    PLAYER_UPDATE_BOOL_FIELDS.update({
        f"salary_{_season}_provisional", f"salary_{_season}_partially_guaranteed",
        f"salary_{_season}_note",
    })
PLAYER_UPDATE_ALLOWED_FIELDS = (
    PLAYER_UPDATE_TEXT_FIELDS
    | PLAYER_UPDATE_PROFILE_FIELDS
    | PLAYER_UPDATE_BOOL_FIELDS
    | {"option_action", "option_action_field", "option_action_value", "notify_discord", "generate_image", "discord_custom_image"}
)
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
ADMIN_DECISION_FIELDS = {
    "decision", "note", "notify_discord", "generate_discord_image", "discord_custom_image",
}


def validate_admin_decision_payload(payload: Dict[str, Any]) -> None:
    validate_payload_fields(payload, ADMIN_DECISION_FIELDS, required_fields={"decision"})
    if str(payload.get("decision") or "").strip().lower() not in {"approved", "rejected"}:
        raise RequestValidationError("invalid_enum", field="decision")
    validate_text_field(payload, "note", max_length=2_000)
    validate_boolean_field(payload, "notify_discord")
    validate_boolean_field(payload, "generate_discord_image")
    if payload.get("discord_custom_image") is not None and not isinstance(payload.get("discord_custom_image"), dict):
        raise RequestValidationError("invalid_field", field="discord_custom_image")


def contract_option_rejection_clear_payload(season: int) -> Dict[str, Any]:
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


def update_offer_promise(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.promise.write"):
        return
    promise_id = parse_int(parsed.path.split("/")[-1])
    if promise_id is None:
        handler._json(400, {"error": "invalid_promise_id"})
        return
    try:
        session = handler._current_session() or {}
        promise = handler._free_agency_service().update_promise(promise_id, payload, session)
    except ValueError as err:
        message = str(err) or "invalid_promise_status"
        if message.startswith("promise_role_limit_exceeded:"):
            _prefix, role, limit = message.split(":", 2)
            handler._json(
                409,
                {
                    "error": "promise_role_limit_exceeded",
                    "role": role,
                    "limit": parse_int(limit),
                    "message": f"Este equipo ya ha alcanzado el máximo de promesas firmadas para {role}.",
                },
            )
            return
        handler._json(400, {"error": message})
        return
    if not promise:
        handler._json(404, {"error": "promise_not_found"})
        return
    handler._log_admin_action(
        "update",
        "free_agent_offer_promise",
        str(promise_id),
        promise.get("team_code"),
        {
            "status": promise.get("status"),
            "player_name": promise.get("player_name"),
            "role": promise.get("role"),
        },
        after={"promise": promise},
    )
    handler._json(200, {"ok": True, "promise": promise})
    return

def decide_draft_pick_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(payload, validate_admin_decision_payload):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_request_id"})
        return
    admin_decision = str(payload.get("decision") or "").strip().lower()
    if admin_decision not in {"approved", "rejected"}:
        handler._json(400, {"error": "invalid_decision"})
        return
    draft_service = handler._draft_service()
    request = draft_service.pick_request(request_id)
    if not request:
        handler._json(404, {"error": "request_not_found"})
        return
    if str(request.get("status") or "").lower() != "pending":
        handler._json(409, {"error": "request_already_decided", "request": request})
        return
    if not handler._authorize("admin.gm_draft_pick_request.decide", {"team_code": request.get("team_code")}):
        return

    try:
        decision_result = draft_service.decide_pick_request(
            request_id,
            admin_decision,
            handler._current_session() or {},
            note=str(payload.get("note") or "").strip() or None,
            request=request,
        )
    except ValueError as err:
        message = str(err) or "draft_selection_failed"
        status = 404 if message == "request_not_found" else 400 if message == "invalid_decision" else 409
        handler._json(status, {"error": message})
        return
    updated = decision_result["request"]
    live = decision_result.get("draft_live")
    audit_details = {
        "draft_order_id": request.get("draft_order_id"),
        "draft_year": request.get("draft_year"),
        "draft_round": request.get("draft_round"),
        "pick_number": request.get("pick_number"),
        "selection": request.get("selection_text"),
    }
    audit_after = {"request": updated}
    if live is not None:
        audit_details["advanced_to"] = live.get("current_pick_id")
        audit_after["draft_live"] = live
    handler._log_admin_action(
        admin_decision.rstrip("d"),
        "gm_draft_pick_request",
        str(request_id),
        request.get("team_code"),
        audit_details,
        before={"request": decision_result.get("request_before")},
        after=audit_after,
    )
    if admin_decision == "approved" and handler._discord_notify_requested(payload):
        handler._notify_draft_pick_selection(
            request,
            generate_image=handler._discord_image_requested(payload),
            custom_image=payload.get("discord_custom_image"),
        )
    response = {"ok": True, "request": updated}
    if live is not None:
        response["draft_live"] = live
    handler._json(200, response)
    return

def decide_free_agent_offer_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(payload, validate_admin_decision_payload):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_request_id"})
        return
    admin_decision = str(payload.get("decision") or "").strip().lower()
    if admin_decision not in {"approved", "rejected"}:
        handler._json(400, {"error": "invalid_decision"})
        return
    request = handler.db.get_gm_free_agent_offer_request(request_id)
    if not request:
        handler._json(404, {"error": "request_not_found"})
        return
    if str(request.get("status") or "").lower() != "pending":
        handler._json(409, {"error": "request_already_decided", "request": request})
        return
    if not handler._authorize("admin.gm_free_agent_offer_request.decide", {"team_code": request.get("team_code")}):
        return

    actor = handler._current_session() or {}
    decision_options = OfferDecisionOptions(
        note=str(payload.get("note") or "").strip() or None,
        notify_discord=handler._discord_notify_requested(payload),
        generate_image=handler._discord_image_requested(payload),
        custom_image=(
            payload.get("discord_custom_image")
            if isinstance(payload.get("discord_custom_image"), dict)
            else None
        ),
        bypass_role_limits=str(actor.get("role") or "").strip().lower() == "admin",
    )
    try:
        result = handler._free_agency_service().decide_offer(
            request_id,
            admin_decision,
            actor,
            options=decision_options,
            request=request,
        )
    except ValueError as err:
        message = str(err) or "gm_free_agent_offer_decision_failed"
        if message.startswith("promise_role_limit_exceeded:"):
            _prefix, role, limit = message.split(":", 2)
            handler._json(
                409,
                {
                    "error": "promise_role_limit_exceeded",
                    "role": role,
                    "limit": parse_int(limit),
                    "message": f"{request.get('team_code')} ya ha alcanzado el máximo de promesas firmadas para {role}.",
                },
            )
            return
        if message in {"profile_has_active_contract", "request_already_decided"}:
            handler._json(409, {"error": message})
            return
        if message in {"free_agent_not_found", "request_not_found", "free_agent_or_team_not_found"}:
            handler._json(404, {"error": message})
            return
        handler._json(400, {"error": message})
        return
    except sqlite3.Error as err:
        handler.log_error(
            "GM free-agent offer approval DB failure request=%s free_agent=%s team=%s: %s",
            request_id,
            request.get("free_agent_id"),
            request.get("team_code"),
            err,
        )
        handler._json(500, {"error": "offer_approval_failed", "detail": str(err)[:200]})
        return
    updated = result.get("request")
    if admin_decision == "rejected":
        handler._log_admin_action(
            "reject",
            "gm_free_agent_offer_request",
            str(request_id),
            request.get("team_code"),
            {
                "free_agent_id": result.get("free_agent_id"),
                "player_name": request.get("player_name"),
                "offer_type": result.get("offer_type"),
            },
            before={"request": result.get("request_before")},
            after={"request": updated},
        )
        handler._json(200, {"ok": True, "request": updated})
        return

    free_agent_id = result.get("free_agent_id")
    offer_payload = result.get("offer_payload") or {}
    player_id = result.get("player_id")
    player_after = result.get("player")
    discord_sent = False
    if decision_options.notify_discord:
        delivered_events = handler._dispatch_outbox_events(result.get("outbox_event_ids"))
        discord_sent = bool(delivered_events)
    handler._log_admin_action(
        "approve",
        "gm_free_agent_offer_request",
        str(request_id),
        request.get("team_code"),
        {
            "free_agent_id": free_agent_id,
            "player_id": player_id,
            "player_name": request.get("player_name"),
            "offer_type": request.get("offer_type"),
            "contract_type": offer_payload.get("contract_type"),
            "years": offer_payload.get("years"),
            "sent_to_discord": discord_sent,
        },
        before={"request": result.get("request_before")},
        after={"request": updated, "player": player_after},
    )
    handler._json(200, {"ok": True, "request": updated, "player_id": player_id, "discord_sent": discord_sent})
    return

def decide_option_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(payload, validate_admin_decision_payload):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_request_id"})
        return
    admin_decision = str(payload.get("decision") or "").strip().lower()
    if admin_decision not in {"approved", "rejected"}:
        handler._json(400, {"error": "invalid_decision"})
        return
    request = handler.db.get_gm_option_request(request_id)
    if not request:
        handler._json(404, {"error": "request_not_found"})
        return
    if str(request.get("status") or "").lower() != "pending":
        handler._json(409, {"error": "request_already_decided", "request": request})
        return
    request_type = str(request.get("request_type") or "option")

    if admin_decision == "rejected":
        updated = handler.db.mark_gm_option_request_decided(
            request_id,
            "rejected",
            handler._current_session() or {},
            str(payload.get("note") or "").strip() or None,
        )
        if not updated:
            handler._json(409, {"error": "request_already_decided"})
            return
        handler._log_admin_action(
            "reject",
            "gm_bird_rights_renounce_request" if request_type == "bird_rights_renounce" else "gm_option_request",
            str(request_id),
            request.get("team_code"),
            {
                "player_id": request.get("player_id"),
                "player_name": request.get("player_name"),
                "option_action": request.get("action"),
                "option_field": request.get("option_field"),
                "option_value": request.get("option_value"),
            },
            before={"request": request},
            after={"request": updated},
        )
        handler._json(200, {"ok": True, "request": updated})
        return

    option_field = str(request.get("option_field") or "").strip()
    option_value = str(request.get("option_value") or "").strip().upper()
    option_action = str(request.get("action") or "").strip().lower()
    if request_type == "bird_rights_renounce":
        match = re.fullmatch(r"salary_(20\d{2})_text", option_field)
        action_season = parse_int(match.group(1)) if match else None
        if action_season is None:
            handler._json(400, {"error": "invalid_bird_rights_field"})
            return
        if option_value not in {"FB", "EB", "NB"}:
            handler._json(400, {"error": "invalid_bird_rights_value"})
            return
        if option_action != "renounced":
            handler._json(400, {"error": "invalid_bird_rights_action"})
            return
        player_id = parse_int(str(request.get("player_id") or ""))
        if player_id is None:
            handler._json(400, {"error": "invalid_player_id"})
            return
        player_before = handler.db.get_player_record(player_id)
        if not player_before:
            handler._json(404, {"error": "player_not_found"})
            return
        current_team_code = normalize_team_code(player_before.get("team_code"))
        request_team_code = normalize_team_code(request.get("team_code"))
        if request_team_code and current_team_code != request_team_code:
            handler._json(
                409,
                {
                    "error": "player_team_changed",
                    "current_team_code": current_team_code,
                    "request_team_code": request_team_code,
                },
            )
            return
        if not handler._authorize("admin.gm_option_request.decide", {"team_code": current_team_code}):
            return
        current_rights = str(player_before.get(option_field) or "").strip().upper()
        if current_rights != option_value:
            handler._json(409, {"error": "bird_rights_changed", "current_rights": current_rights})
            return

        updated = handler.db.mark_gm_option_request_decided(
            request_id,
            "approved",
            handler._current_session() or {},
            str(payload.get("note") or "").strip() or None,
        )
        if not updated:
            handler._json(409, {"error": "request_already_decided"})
            return
        renounced_free_agent_id = handler.db.ensure_renounced_bird_rights_free_agent(
            player_before,
            action_season,
            option_value,
        )
        player_after = handler.db.get_player_record(player_id)
        handler._log_admin_action(
            "approve",
            "gm_bird_rights_renounce_request",
            str(request_id),
            request.get("team_code"),
            {
                "player_id": player_id,
                "player_name": request.get("player_name"),
                "rights_action": option_action,
                "rights_field": option_field,
                "rights_value": option_value,
                "rights_season": action_season,
                "roster_removed": player_after is None,
                "free_agent_id": renounced_free_agent_id,
            },
            before={"request": request, "player": player_before},
            after={"request": updated, "player": player_after},
        )
        if handler._discord_notify_requested(payload):
            handler._notify_bird_rights_renounced(
                player_before,
                action_season,
                option_value,
                generate_image=handler._discord_image_requested(payload),
                custom_image=payload.get("discord_custom_image"),
            )
        handler._json(200, {"ok": True, "request": updated})
        return

    match = re.fullmatch(r"option_(20\d{2})", option_field)
    option_action_season = parse_int(match.group(1)) if match else None
    if option_action_season is None:
        handler._json(400, {"error": "invalid_option_field"})
        return
    if option_value not in {"TO", "PO", "QO", "GAP"}:
        handler._json(400, {"error": "invalid_option_value"})
        return
    if option_action not in {"accepted", "rejected"}:
        handler._json(400, {"error": "invalid_option_action"})
        return
    player_id = parse_int(str(request.get("player_id") or ""))
    if player_id is None:
        handler._json(400, {"error": "invalid_player_id"})
        return
    player_before = handler.db.get_player_record(player_id)
    if not player_before:
        handler._json(404, {"error": "player_not_found"})
        return
    current_team_code = normalize_team_code(player_before.get("team_code"))
    request_team_code = normalize_team_code(request.get("team_code"))
    if request_team_code and current_team_code != request_team_code:
        handler._json(
            409,
            {
                "error": "player_team_changed",
                "current_team_code": current_team_code,
                "request_team_code": request_team_code,
            },
        )
        return
    if not handler._authorize("admin.gm_option_request.decide", {"team_code": current_team_code}):
        return
    current_option = str(player_before.get(option_field) or "").strip().upper()
    if current_option != option_value:
        handler._json(409, {"error": "option_changed", "current_option": current_option})
        return

    if option_action == "rejected" and option_value == "QO":
        updated = handler.db.mark_gm_option_request_decided(
            request_id,
            "approved",
            handler._current_session() or {},
            str(payload.get("note") or "").strip() or None,
        )
        if not updated:
            handler._json(409, {"error": "request_already_decided"})
            return
        removal = handler.db.remove_player_from_roster(player_id)
        if removal is None:
            handler._json(404, {"error": "player_not_found"})
            return
        player_after = handler.db.get_player_record(player_id)
        handler._log_admin_action(
            "approve",
            "gm_option_request",
            str(request_id),
            request.get("team_code"),
            {
                "player_id": player_id,
                "player_name": request.get("player_name"),
                "option_action": option_action,
                "option_field": option_field,
                "option_value": option_value,
                "option_action_season": option_action_season,
                "roster_removed": True,
                "free_agent_id": removal.get("free_agent_id"),
                "free_agent_type": FREE_AGENT_TYPE_UNRESTRICTED,
            },
            before={"request": request, "player": player_before},
            after={"request": updated, "player": player_after, "free_agent": removal},
        )
        if handler._discord_notify_requested(payload):
            handler._notify_contract_option_action(
                player_before,
                option_action_season,
                option_value,
                option_action,
                generate_image=handler._discord_image_requested(payload),
                custom_image=payload.get("discord_custom_image"),
            )
        handler._json(200, {"ok": True, "request": updated, "player": player_after, "free_agent": removal})
        return

    player_payload: Dict[str, Any] = {}
    if option_action == "rejected" and option_value in CONTRACT_TERMINATING_OPTION_VALUES:
        # Rejecting a TO/PO ends that contract path, so the option
        # season and all later contract-year data must disappear.
        player_payload.update(contract_option_rejection_clear_payload(option_action_season))
    elif option_action == "accepted" and option_value in {"QO", "GAP"}:
        # Keep QO/GAP markers so accepted option state and cap-hold UI
        # continue to work until an admin applies the contract outcome.
        player_payload[option_field] = option_value
    else:
        # Rejected options, and accepted TO/PO options, remove the
        # pending option marker from the roster cell.
        player_payload[option_field] = None

    ok = handler.db.update_player(player_id, player_payload)
    if not ok:
        handler._json(404, {"error": "player_not_found"})
        return
    player_after = handler.db.get_player_record(player_id)
    updated = handler.db.mark_gm_option_request_decided(
        request_id,
        "approved",
        handler._current_session() or {},
        str(payload.get("note") or "").strip() or None,
    )
    if not updated:
        handler._json(409, {"error": "request_already_decided"})
        return
    handler._log_admin_action(
        "approve",
        "gm_option_request",
        str(request_id),
        request.get("team_code"),
        {
            "player_id": player_id,
            "player_name": request.get("player_name"),
            "option_action": option_action,
            "option_field": option_field,
            "option_value": option_value,
            "option_action_season": option_action_season,
            "applied_fields": sorted(player_payload.keys()),
        },
        before={"request": request, "player": player_before},
        after={"request": updated, "player": player_after},
    )
    if handler._discord_notify_requested(payload):
        handler._notify_contract_option_action(
            player_before,
            option_action_season,
            option_value,
            option_action,
            generate_image=handler._discord_image_requested(payload),
            custom_image=payload.get("discord_custom_image"),
        )
    handler._json(200, {"ok": True, "request": updated, "player": player_after})
    return

def update_admin_user(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.users.write"):
        return
    try:
        user_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_user_id"})
        return
    team_codes = payload.get("team_codes")
    if team_codes is None and "team_code" in payload:
        team_code = str(payload.get("team_code") or "").strip()
        team_codes = [team_code] if team_code else []
    if team_codes is None:
        handler._json(400, {"error": "team_codes_required"})
        return
    is_co_admin = parse_bool(payload.get("is_co_admin")) if "is_co_admin" in payload else None
    agent_name = payload.get("agent_name") if "agent_name" in payload else None
    try:
        user = handler.db.replace_user_team_assignments(
            user_id,
            team_codes,
            is_co_admin=is_co_admin,
            agent_name=agent_name,
        )
    except ValueError as err:
        message = str(err)
        if message.startswith("invalid_team_code:"):
            handler._json(400, {"error": "invalid_team_code", "team_code": message.split(":", 1)[1]})
            return
        raise
    if user is None:
        handler._json(404, {"error": "user_not_found"})
        return
    assigned_codes = normalize_team_codes(user.get("team_codes"))
    email = str(user.get("email") or "").strip().lower()
    is_co_admin_response = bool(parse_bool(user.get("is_co_admin")))
    user["is_co_admin"] = is_co_admin_response
    user["role"] = (
        "admin"
        if email in handler.admin_emails
        else ("co_admin" if is_co_admin_response else ("gm" if assigned_codes else "guest"))
    )
    user["team_code"] = assigned_codes[0] if assigned_codes else None
    user["team_codes"] = assigned_codes
    handler._log_admin_action(
        "update",
        "user_access",
        str(user_id),
        assigned_codes[0] if assigned_codes else None,
        {
            "email": user.get("email"),
            "team_codes": assigned_codes,
            "is_co_admin": is_co_admin_response,
            "agent_name": user.get("agent_name"),
        },
    )
    handler._json(200, {"ok": True, "user": user})
    return

def update_settings(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.global.write"):
        return
    next_salary_cap: Optional[float] = None
    next_current_year: Optional[int] = None
    next_first_apron: Optional[float] = None
    next_second_apron: Optional[float] = None
    next_cash_limit_total: Optional[float] = None
    next_trade_move_limit_pre30: Optional[int] = None
    next_trade_move_limit_post30: Optional[int] = None
    next_trade_move_phase: Optional[str] = None
    next_free_agency_mode: Optional[bool] = None
    next_free_agent_offer_role_ping_enabled: Optional[bool] = None
    next_roster_standard_min: Optional[int] = None
    next_roster_standard_max: Optional[int] = None
    next_roster_standard_offseason_max: Optional[int] = None
    next_roster_two_way_min: Optional[int] = None
    next_roster_two_way_max: Optional[int] = None
    next_free_agent_reps: Optional[List[str]] = None
    next_free_agent_rep_discord_ids: Optional[Dict[str, str]] = None
    season_cap_updates: Dict[str, Optional[float]] = {}
    rookie_scale_updates: Dict[str, Optional[float]] = {}

    if "salary_cap_2025" in payload:
        cap = payload.get("salary_cap_2025")
        parsed_cap = parse_float(str(cap) if cap is not None else None)
        if parsed_cap is None or parsed_cap <= 0:
            handler._json(400, {"error": "invalid_salary_cap_2025"})
            return
        next_salary_cap = parsed_cap

    if "current_year" in payload:
        parsed_year = parse_int(str(payload.get("current_year")))
        if parsed_year is None or parsed_year < PLAYER_CONTRACT_MIN_YEAR or parsed_year > PLAYER_CONTRACT_MAX_START_YEAR:
            handler._json(400, {"error": "invalid_current_year"})
            return
        next_current_year = parsed_year

    if "first_apron" in payload:
        parsed_first_apron = parse_float(str(payload.get("first_apron")))
        if parsed_first_apron is None or parsed_first_apron <= 0:
            handler._json(400, {"error": "invalid_first_apron"})
            return
        next_first_apron = parsed_first_apron

    if "second_apron" in payload:
        parsed_second_apron = parse_float(str(payload.get("second_apron")))
        if parsed_second_apron is None or parsed_second_apron <= 0:
            handler._json(400, {"error": "invalid_second_apron"})
            return
        next_second_apron = parsed_second_apron

    if "cash_limit_total" in payload:
        parsed_cash_limit_total = parse_float(str(payload.get("cash_limit_total")))
        if parsed_cash_limit_total is None or parsed_cash_limit_total < 0:
            handler._json(400, {"error": "invalid_cash_limit_total"})
            return
        next_cash_limit_total = parsed_cash_limit_total

    if "trade_move_limit_pre30" in payload:
        parsed_trade_move_limit_pre30 = parse_int(str(payload.get("trade_move_limit_pre30")))
        if parsed_trade_move_limit_pre30 is None or parsed_trade_move_limit_pre30 < 0:
            handler._json(400, {"error": "invalid_trade_move_limit_pre30"})
            return
        next_trade_move_limit_pre30 = parsed_trade_move_limit_pre30

    if "trade_move_limit_post30" in payload:
        parsed_trade_move_limit_post30 = parse_int(str(payload.get("trade_move_limit_post30")))
        if parsed_trade_move_limit_post30 is None or parsed_trade_move_limit_post30 < 0:
            handler._json(400, {"error": "invalid_trade_move_limit_post30"})
            return
        next_trade_move_limit_post30 = parsed_trade_move_limit_post30

    if "trade_move_phase" in payload:
        next_trade_move_phase = normalize_move_phase(payload.get("trade_move_phase"))

    if "free_agency_mode" in payload:
        next_free_agency_mode = parse_bool(payload.get("free_agency_mode"))

    if "discord_free_agent_offer_role_ping_enabled" in payload:
        next_free_agent_offer_role_ping_enabled = parse_bool(
            payload.get("discord_free_agent_offer_role_ping_enabled")
        )

    if "free_agent_reps" in payload:
        raw_reps = payload.get("free_agent_reps")
        if isinstance(raw_reps, list):
            rep_values = raw_reps
        else:
            rep_values = str(raw_reps or "").splitlines()
        seen_reps = set()
        next_free_agent_reps = []
        for rep in rep_values:
            value = str(rep or "").strip()
            if not value:
                continue
            key = value.casefold()
            if key in seen_reps:
                continue
            if len(value) > 80:
                handler._json(400, {"error": "invalid_free_agent_reps"})
                return
            seen_reps.add(key)
            next_free_agent_reps.append(value)
        if len(next_free_agent_reps) > 100:
            handler._json(400, {"error": "invalid_free_agent_reps"})
            return

    if "free_agent_rep_discord_ids" in payload:
        raw_map = payload.get("free_agent_rep_discord_ids")
        next_free_agent_rep_discord_ids = parse_free_agent_rep_discord_ids(raw_map)
        if len(next_free_agent_rep_discord_ids) > 100:
            handler._json(400, {"error": "invalid_free_agent_rep_discord_ids"})
            return

    for field, raw_value in payload.items():
        match = re.fullmatch(r"(salary_cap|salary_floor|first_apron|second_apron|average_salary)_(\d{4})", str(field))
        if not match:
            continue
        if field == "salary_cap_2025":
            continue
        setting_kind = match.group(1)
        season_year = parse_int(match.group(2))
        if season_year is None or season_year < CAP_FORECAST_MIN_YEAR or season_year > CAP_FORECAST_MAX_YEAR:
            handler._json(400, {"error": f"invalid_{field}"})
            return
        if setting_kind == "average_salary" and (raw_value is None or str(raw_value).strip() == ""):
            season_cap_updates[str(field)] = None
            continue
        parsed_value = parse_float(str(raw_value))
        if parsed_value is None or parsed_value <= 0:
            handler._json(400, {"error": f"invalid_{field}"})
            return
        season_cap_updates[str(field)] = parsed_value

    for field, raw_value in payload.items():
        match = re.fullmatch(r"rookie_scale_(\d{4})_([1-9]|[12]\d|30)", str(field))
        if not match:
            continue
        season_year = parse_int(match.group(1))
        if season_year is None or season_year < CAP_FORECAST_MIN_YEAR or season_year > CAP_FORECAST_MAX_YEAR:
            handler._json(400, {"error": f"invalid_{field}"})
            return
        if raw_value is None or str(raw_value).strip() == "":
            rookie_scale_updates[str(field)] = None
            continue
        parsed_value = parse_float(str(raw_value))
        if parsed_value is None or parsed_value <= 0:
            handler._json(400, {"error": f"invalid_{field}"})
            return
        rookie_scale_updates[str(field)] = parsed_value

    roster_int_fields = {
        "roster_standard_min": "invalid_roster_standard_min",
        "roster_standard_max": "invalid_roster_standard_max",
        "roster_standard_offseason_max": "invalid_roster_standard_offseason_max",
        "roster_two_way_min": "invalid_roster_two_way_min",
        "roster_two_way_max": "invalid_roster_two_way_max",
    }
    parsed_roster_fields: Dict[str, int] = {}
    for field, error in roster_int_fields.items():
        if field not in payload:
            continue
        parsed_value = parse_int(str(payload.get(field)))
        if parsed_value is None or parsed_value < 0:
            handler._json(400, {"error": error})
            return
        parsed_roster_fields[field] = parsed_value
    if "roster_standard_min" in parsed_roster_fields:
        next_roster_standard_min = parsed_roster_fields["roster_standard_min"]
    if "roster_standard_max" in parsed_roster_fields:
        next_roster_standard_max = parsed_roster_fields["roster_standard_max"]
    if "roster_standard_offseason_max" in parsed_roster_fields:
        next_roster_standard_offseason_max = parsed_roster_fields["roster_standard_offseason_max"]
    if "roster_two_way_min" in parsed_roster_fields:
        next_roster_two_way_min = parsed_roster_fields["roster_two_way_min"]
    if "roster_two_way_max" in parsed_roster_fields:
        next_roster_two_way_max = parsed_roster_fields["roster_two_way_max"]

    current_settings = public_settings_payload(handler.db.get_settings())
    standard_min_check = next_roster_standard_min if next_roster_standard_min is not None else int(current_settings["roster_standard_min"])
    standard_max_check = next_roster_standard_max if next_roster_standard_max is not None else int(current_settings["roster_standard_max"])
    standard_offseason_max_check = (
        next_roster_standard_offseason_max
        if next_roster_standard_offseason_max is not None
        else int(current_settings["roster_standard_offseason_max"])
    )
    two_way_min_check = next_roster_two_way_min if next_roster_two_way_min is not None else int(current_settings["roster_two_way_min"])
    two_way_max_check = next_roster_two_way_max if next_roster_two_way_max is not None else int(current_settings["roster_two_way_max"])
    if standard_min_check > standard_max_check or standard_max_check > standard_offseason_max_check:
        handler._json(400, {"error": "invalid_roster_standard_range"})
        return
    if two_way_min_check > two_way_max_check:
        handler._json(400, {"error": "invalid_roster_two_way_range"})
        return

    if (
        next_salary_cap is None
        and next_current_year is None
        and next_first_apron is None
        and next_second_apron is None
        and next_cash_limit_total is None
        and next_trade_move_limit_pre30 is None
        and next_trade_move_limit_post30 is None
        and next_trade_move_phase is None
        and next_free_agency_mode is None
        and next_free_agent_offer_role_ping_enabled is None
        and not season_cap_updates
        and not rookie_scale_updates
        and next_roster_standard_min is None
        and next_roster_standard_max is None
        and next_roster_standard_offseason_max is None
        and next_roster_two_way_min is None
        and next_roster_two_way_max is None
        and next_free_agent_reps is None
        and next_free_agent_rep_discord_ids is None
    ):
        handler._json(400, {"error": "settings_payload_required"})
        return

    current_year_update_result: Optional[Dict[str, Any]] = None
    if next_salary_cap is not None:
        handler.db.update_setting("salary_cap_2025", str(int(next_salary_cap)))
    if next_current_year is not None:
        current_year_update_result = handler._season_rollover_service().update_current_year(
            next_current_year
        )
    if next_first_apron is not None:
        handler.db.update_setting("first_apron", str(int(next_first_apron)))
    if next_second_apron is not None:
        handler.db.update_setting("second_apron", str(int(next_second_apron)))
    if next_cash_limit_total is not None:
        handler.db.update_setting("cash_limit_total", str(int(next_cash_limit_total)))
    if next_trade_move_limit_pre30 is not None:
        handler.db.update_setting("trade_move_limit_pre30", str(int(next_trade_move_limit_pre30)))
    if next_trade_move_limit_post30 is not None:
        handler.db.update_setting("trade_move_limit_post30", str(int(next_trade_move_limit_post30)))
    if next_trade_move_phase is not None:
        handler.db.update_setting("trade_move_phase", next_trade_move_phase)
    if next_free_agency_mode is not None:
        handler.db.update_setting("free_agency_mode", "1" if next_free_agency_mode else "0")
    if next_free_agent_offer_role_ping_enabled is not None:
        handler.db.update_setting(
            "discord_free_agent_offer_role_ping_enabled",
            "1" if next_free_agent_offer_role_ping_enabled else "0",
        )
    for key, value in season_cap_updates.items():
        handler.db.update_setting(key, "" if value is None else str(int(value)))
    for key, value in rookie_scale_updates.items():
        handler.db.update_setting(key, "" if value is None else str(int(value)))
    if next_roster_standard_min is not None:
        handler.db.update_setting("roster_standard_min", str(next_roster_standard_min))
    if next_roster_standard_max is not None:
        handler.db.update_setting("roster_standard_max", str(next_roster_standard_max))
    if next_roster_standard_offseason_max is not None:
        handler.db.update_setting("roster_standard_offseason_max", str(next_roster_standard_offseason_max))
    if next_roster_two_way_min is not None:
        handler.db.update_setting("roster_two_way_min", str(next_roster_two_way_min))
    if next_roster_two_way_max is not None:
        handler.db.update_setting("roster_two_way_max", str(next_roster_two_way_max))
    if next_free_agent_reps is not None:
        handler.db.update_setting("free_agent_reps", json.dumps(next_free_agent_reps, ensure_ascii=False))
    if next_free_agent_rep_discord_ids is not None:
        handler.db.update_setting(
            "free_agent_rep_discord_ids",
            json.dumps(next_free_agent_rep_discord_ids, ensure_ascii=False),
        )
    handler._log_admin_action(
        "update",
        "settings",
        None,
        None,
        {
            "salary_cap_2025": next_salary_cap,
            "current_year": next_current_year,
            "first_apron": next_first_apron,
            "second_apron": next_second_apron,
            "cash_limit_total": next_cash_limit_total,
            "current_year_update": current_year_update_result,
            "trade_move_limit_pre30": next_trade_move_limit_pre30,
            "trade_move_limit_post30": next_trade_move_limit_post30,
            "trade_move_phase": next_trade_move_phase,
            "free_agency_mode": next_free_agency_mode,
            "discord_free_agent_offer_role_ping_enabled": next_free_agent_offer_role_ping_enabled,
            "season_cap_updates": season_cap_updates,
            "rookie_scale_updates": rookie_scale_updates,
            "roster_standard_min": next_roster_standard_min,
            "roster_standard_max": next_roster_standard_max,
            "roster_standard_offseason_max": next_roster_standard_offseason_max,
            "roster_two_way_min": next_roster_two_way_min,
            "roster_two_way_max": next_roster_two_way_max,
            "free_agent_reps": next_free_agent_reps,
            "free_agent_rep_discord_ids": next_free_agent_rep_discord_ids,
        },
    )

    merged = handler.db.get_settings()
    handler._json(
        200,
        {
            "ok": True,
            "settings": public_settings_payload(merged),
        },
    )
    return

def update_draft_order(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.draft_order.write"):
        return
    try:
        draft_order_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_draft_order_id"})
        return
    try:
        ok = handler._draft_service().update_order_entry(draft_order_id, payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_draft_order"})
        return
    if ok:
        handler._log_admin_action(
            "update",
            "draft_order",
            str(draft_order_id),
            payload.get("owner_team_code"),
            {"fields": sorted(payload.keys())},
        )
    handler._json(200 if ok else 404, {"ok": ok})
    return

def update_player_transaction(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.player_profile.write"):
        return
    try:
        transaction_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_transaction_id"})
        return
    ok = handler.db.update_player_transaction(transaction_id, payload)
    if ok:
        handler._log_admin_action(
            "update",
            "player_transaction",
            str(transaction_id),
            payload.get("team_code"),
            {"fields": sorted(payload.keys())},
        )
    handler._json(200 if ok else 404, {"ok": ok})
    return

def update_player_salary_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.player_profile.write"):
        return
    try:
        salary_history_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_salary_history_id"})
        return
    try:
        ok = handler.db.update_player_salary_history(salary_history_id, payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_salary_history"})
        return
    if ok:
        handler._log_admin_action(
            "update",
            "player_salary_history",
            str(salary_history_id),
            payload.get("team_code") or payload.get("last_team"),
            {"fields": sorted(payload.keys())},
        )
    handler._json(200 if ok else 404, {"ok": ok})
    return

def update_player_profile(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.player_profile.write"):
        return
    try:
        profile_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_profile_id"})
        return
    try:
        ok = handler._player_identity_service().update_profile(profile_id, payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_profile"})
        return
    if ok:
        handler._log_admin_action(
            "update",
            "player_profile",
            str(profile_id),
            None,
            {"fields": sorted(payload.keys())},
        )
    handler._json(200 if ok else 404, {"ok": ok})
    return

def update_player(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        player_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_player_id"})
        return
    if not handler._validate_payload_or_error(
        payload,
        PLAYER_UPDATE_ALLOWED_FIELDS,
        text_fields=(
            ("name", 200, False),
            ("position", 20, False),
            ("bird_rights", 20, False),
            ("rating", 32, False),
            ("notes", 10_000, False),
            ("reference_image_url", 2_048, False),
            ("profile_notes", 10_000, False),
            ("date_of_birth", 32, False),
            ("nationality", 100, False),
            ("yos_source", 500, False),
            ("transaction_notes", 10_000, False),
        ),
        integer_fields=(("experience_years", 0, 99),),
    ):
        return
    option_action = str(payload.get("option_action") or "").strip().lower()
    option_action_field = str(payload.get("option_action_field") or "").strip()
    option_action_value = str(payload.get("option_action_value") or "").strip().upper()
    option_action_season: Optional[int] = None
    player_before = handler.db.get_player_record(player_id)
    if not player_before:
        handler._json(404, {"error": "player_not_found"})
        return
    if not handler._authorize("admin.player.write", {"team_code": player_before.get("team_code")}):
        return
    if option_action:
        if option_action not in {"accepted", "rejected"}:
            handler._json(400, {"error": "invalid_option_action"})
            return
        match = re.fullmatch(r"option_(20\d{2})", option_action_field)
        if not match:
            handler._json(400, {"error": "invalid_option_action_field"})
            return
        option_action_season = parse_int(match.group(1))
        if option_action_season is None:
            handler._json(400, {"error": "invalid_option_action_season"})
            return
        if not option_action_value:
            option_action_value = str(payload.get(option_action_field) or player_before.get(option_action_field) or "").strip().upper()
        if option_action_value not in {"TO", "PO", "QO", "GAP"}:
            handler._json(400, {"error": "invalid_option_action_value"})
            return
        if option_action == "rejected" and option_action_value in CONTRACT_TERMINATING_OPTION_VALUES:
            payload.update(contract_option_rejection_clear_payload(option_action_season))
        elif option_action == "accepted" and option_action_value in {"TO", "PO"}:
            payload[option_action_field] = None
        elif option_action == "rejected":
            payload[option_action_field] = None
    ok = handler.db.update_player(player_id, payload)
    player_after = handler.db.get_player_record(player_id) if ok else None
    if ok:
        log_details: Dict[str, Any] = {"fields": sorted(payload.keys())}
        renounced_free_agent_id: Optional[int] = None
        direct_option_decision: Optional[Dict[str, Any]] = None
        if option_action and option_action_season is not None:
            try:
                direct_option_decision = handler.db.record_admin_option_decision(
                    player_id,
                    option_action_field,
                    option_action_value,
                    option_action,
                    handler._current_session() or {},
                )
            except ValueError:
                direct_option_decision = None
        settings = handler.db.get_settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        renounce_season = int(current_year)
        renounce_field = f"salary_{renounce_season}_text"
        if (
            parse_bool(settings.get("free_agency_mode"))
            and renounce_field in payload
            and str(player_before.get(renounce_field) or "").strip().upper() in {"FB", "EB", "NB"}
            and not str((player_after or {}).get(renounce_field) or "").strip()
        ):
            renounced_rights = str(player_before.get(renounce_field) or "").strip().upper()
            renounced_free_agent_id = handler.db.ensure_renounced_bird_rights_free_agent(
                player_before,
                renounce_season,
                renounced_rights,
            )
            player_after = handler.db.get_player_record(player_id)
            if renounced_free_agent_id is not None:
                log_details.update(
                    {
                        "bird_rights_renounced": True,
                        "roster_removed": player_after is None,
                        "rights_field": renounce_field,
                        "rights_value": renounced_rights,
                        "rights_season": renounce_season,
                        "free_agent_id": renounced_free_agent_id,
                    }
                )
        if option_action and option_action_season is not None:
            log_details.update(
                {
                    "option_action": option_action,
                    "option_action_field": option_action_field,
                    "option_action_value": option_action_value,
                    "option_action_season": option_action_season,
                    "option_decision_request_id": (
                        direct_option_decision.get("id") if isinstance(direct_option_decision, dict) else None
                    ),
                }
            )
        handler._log_admin_action(
            "update",
            "player",
            str(player_id),
            player_before.get("team_code"),
            log_details,
            before=player_before,
            after=player_after,
        )
        if (
            option_action
            and option_action_season is not None
            and player_before
            and handler._discord_notify_requested(payload)
        ):
            handler._notify_contract_option_action(
                player_before,
                option_action_season,
                option_action_value,
                option_action,
                generate_image=handler._discord_image_requested(payload),
                custom_image=payload.get("discord_custom_image"),
            )
    handler._json(200 if ok else 404, {"ok": ok, "player": player_after})
    return

def update_team_luxury_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    parts = parsed.path.split("/")
    if len(parts) < 5:
        handler._json(404, {"error": "not_found"})
        return
    code = parts[3]
    if not handler._authorize("admin.team.write", {"team_code": code}):
        return
    season_year = parse_int(payload.get("season_year"))
    if season_year is None or season_year < 2000 or season_year > 2100:
        handler._json(400, {"error": "invalid_season_year"})
        return
    repeater = parse_bool(payload.get("repeater"))
    ok = handler.db.update_team_luxury_history(code, season_year, repeater)
    if ok:
        handler._log_admin_action(
            "update",
            "team_luxury_history",
            f"{code.upper()}:{season_year}",
            code.upper(),
            {"season_year": season_year, "repeater": repeater},
        )
    handler._json(200 if ok else 404, {"ok": ok})
    return

def update_team(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    code = parsed.path.split("/")[-1]
    if not handler._authorize("admin.team.write", {"team_code": code}):
        return
    update_payload: Dict[str, Any] = {}
    apron_hard_cap_requested = "apron_hard_cap" in payload
    normalized_hard_cap: Optional[str] = None
    apron_hard_cap_season = parse_int(payload.get("season_year"))
    if "gm" in payload:
        gm_raw = payload.get("gm")
        update_payload["gm"] = None if gm_raw is None else str(gm_raw).strip() or None
    if "cash_received" in payload:
        parsed_cash_received = parse_float(str(payload.get("cash_received")))
        if parsed_cash_received is None or parsed_cash_received < 0:
            handler._json(400, {"error": "invalid_cash_received"})
            return
        update_payload["cash_received"] = parsed_cash_received
    if "cash_sent" in payload:
        parsed_cash_sent = parse_float(str(payload.get("cash_sent")))
        if parsed_cash_sent is None or parsed_cash_sent < 0:
            handler._json(400, {"error": "invalid_cash_sent"})
            return
        update_payload["cash_sent"] = parsed_cash_sent
    if "apron_hard_cap" in payload:
        raw_hard_cap = str(payload.get("apron_hard_cap") or "").strip()
        normalized_hard_cap = normalize_apron_hard_cap(raw_hard_cap)
        if raw_hard_cap and normalized_hard_cap is None:
            handler._json(400, {"error": "invalid_apron_hard_cap"})
            return
        if apron_hard_cap_season is None:
            settings = handler.db.get_settings()
            apron_hard_cap_season = parse_int(settings.get("current_year")) or 2025
        if apron_hard_cap_season < CAP_FORECAST_MIN_YEAR or apron_hard_cap_season > CAP_FORECAST_MAX_YEAR:
            handler._json(400, {"error": "invalid_season_year"})
            return
    if not update_payload and not apron_hard_cap_requested:
        handler._json(400, {"error": "team_update_required"})
        return
    ok = True
    if update_payload:
        ok = handler.db.update_team_fields(code, update_payload)
    if ok and apron_hard_cap_requested:
        ok = handler.db.update_team_apron_hard_cap(code, int(apron_hard_cap_season or 2025), normalized_hard_cap)
    if ok:
        details = dict(update_payload)
        if apron_hard_cap_requested:
            details["apron_hard_cap"] = normalized_hard_cap
            details["season_year"] = int(apron_hard_cap_season or 2025)
        handler._log_admin_action("update", "team", code.upper(), code.upper(), details)
    handler._json(200 if ok else 404, {"ok": ok})
    return

def update_asset(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        asset_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_asset_id"})
        return
    asset_before = handler.db.get_asset_record(asset_id)
    if not asset_before:
        handler._json(404, {"error": "asset_not_found"})
        return
    if not handler._authorize("admin.draft_asset.write", {"team_code": asset_before.get("team_code")}):
        return
    if not handler._validate_payload_or_error(
        payload,
        ASSET_UPDATE_FIELDS,
        text_fields=(
            ("asset_type", 40, False),
            ("label", 200, False),
            ("detail", 10_000, False),
            ("amount_text", 64, False),
            ("draft_pick_type", 40, False),
            ("draft_round", 20, False),
            ("original_owner", 8, False),
            ("exception_type", 80, False),
        ),
        integer_fields=(("year", 2000, 2200),),
    ):
        return
    if "asset_type" in payload and str(payload.get("asset_type") or "").strip().lower() == "dead_cap":
        handler._json(400, {"error": "dead_cap_moved_to_dead_contracts"})
        return
    ok = handler.db.update_asset(asset_id, payload)
    if ok:
        asset_after = handler.db.get_asset_record(asset_id)
        handler._log_admin_action(
            "update",
            "asset",
            str(asset_id),
            asset_before.get("team_code"),
            {"fields": sorted(payload.keys())},
            before=asset_before,
            after=asset_after,
        )
    handler._json(200 if ok else 404, {"ok": ok})
    return

def update_frozen_draft_pick(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        frozen_pick_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_frozen_pick_id"})
        return
    before = handler.db.get_frozen_draft_pick_record(frozen_pick_id)
    if not before:
        handler._json(404, {"error": "frozen_pick_not_found"})
        return
    if not handler._authorize("admin.frozen_draft_pick.write", {"team_code": before.get("team_code")}):
        return
    row = handler.db.update_frozen_draft_pick(frozen_pick_id, payload)
    if not row:
        handler._json(404, {"error": "frozen_pick_not_found"})
        return
    handler._log_admin_action(
        "update",
        "frozen_draft_pick",
        str(frozen_pick_id),
        row.get("team_code"),
        {"fields": sorted(payload.keys())},
        before=before,
        after=row,
    )
    handler._json(200, {"ok": True, "frozen_pick": row})
    return

def update_dead_contract(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        dead_contract_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_dead_contract_id"})
        return
    dead_before = handler.db.get_dead_contract_record(dead_contract_id)
    if not dead_before:
        handler._json(404, {"error": "dead_contract_not_found"})
        return
    if not handler._authorize("admin.dead_contract.write", {"team_code": dead_before.get("team_code")}):
        return
    dead_text_fields = [
        ("label", 200, False),
        ("dead_type", 40, False),
        ("amount_text", 64, False),
    ]
    dead_text_fields.extend(
        (f"salary_{season}_text", 64, False)
        for season in PLAYER_CONTRACT_SEASONS
    )
    if not handler._validate_payload_or_error(
        payload,
        DEAD_CONTRACT_UPDATE_FIELDS,
        text_fields=dead_text_fields,
    ):
        return
    ok = handler.db.update_dead_contract(dead_contract_id, payload)
    if ok:
        dead_after = handler.db.get_dead_contract_record(dead_contract_id)
        handler._log_admin_action(
            "update",
            "dead_contract",
            str(dead_contract_id),
            dead_before.get("team_code"),
            {"fields": sorted(payload.keys())},
            before=dead_before,
            after=dead_after,
        )
    handler._json(200 if ok else 404, {"ok": ok})
    return


def _team_luxury_history_path(path: str) -> bool:
    return path.startswith("/api/teams/") and path.endswith("/luxury-history")


PATCH_REMAINING_ROUTES = (
    prefix_route("/api/admin/free-agent-offer-promises/", update_offer_promise),
    prefix_route("/api/admin/gm-draft-pick-requests/", decide_draft_pick_request),
    prefix_route("/api/admin/gm-free-agent-offer-requests/", decide_free_agent_offer_request),
    prefix_route("/api/admin/gm-option-requests/", decide_option_request),
    prefix_route("/api/admin/users/", update_admin_user),
    exact_route("/api/settings", update_settings),
    prefix_route("/api/draft-order/", update_draft_order),
    prefix_route("/api/player-transactions/", update_player_transaction),
    prefix_route("/api/player-salary-history/", update_player_salary_history),
    prefix_route("/api/player-profiles/", update_player_profile),
    prefix_route("/api/players/", update_player),
    predicate_route("team-luxury-history", _team_luxury_history_path, update_team_luxury_history),
    prefix_route("/api/teams/", update_team),
    prefix_route("/api/assets/", update_asset),
    prefix_route("/api/frozen-draft-picks/", update_frozen_draft_pick),
    prefix_route("/api/dead-contracts/", update_dead_contract),
)
