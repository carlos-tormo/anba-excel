"""Remaining administrative PATCH route functions."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import ParseResult

try:
    from ..auth.policies import normalize_team_code, normalize_team_codes
    from ..domain.trade_rules import normalize_move_phase
    from ..domain_rules import (
        parse_bool,
        parse_free_agent_rep_discord_ids,
        parse_int,
        public_settings_payload,
    )
    from ..routing import exact_route, predicate_route, prefix_route
    from .validation import validate_admin_decision_payload
    from ..services.free_agency import OfferDecisionOptions
    from ..services.notifications import discord_image_requested, discord_notify_requested
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code, normalize_team_codes
    from domain.trade_rules import normalize_move_phase
    from domain_rules import (
        parse_bool,
        parse_free_agent_rep_discord_ids,
        parse_int,
        public_settings_payload,
    )
    from routing import exact_route, predicate_route, prefix_route
    from routes.validation import validate_admin_decision_payload
    from services.free_agency import OfferDecisionOptions
    from services.notifications import discord_image_requested, discord_notify_requested


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
        promise = handler.app.free_agency.update_promise(promise_id, payload, session)
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
    draft_service = handler.app.draft
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
    if admin_decision == "approved" and discord_notify_requested(payload):
        handler.app.notifications.draft_pick_selection(
            request,
            generate_image=discord_image_requested(payload),
            custom_image=payload.get("discord_custom_image"),
        )
    response = {"ok": True, "request": updated}
    if live is not None:
        response["draft_live"] = live
    handler._json(200, response)
    return

def _offer_decision_options(handler: Any, payload: Dict[str, Any], actor: Dict[str, Any]) -> OfferDecisionOptions:
    return OfferDecisionOptions(
        note=str(payload.get("note") or "").strip() or None,
        notify_discord=discord_notify_requested(payload),
        generate_image=discord_image_requested(payload),
        custom_image=(payload.get("discord_custom_image") if isinstance(payload.get("discord_custom_image"), dict) else None),
        bypass_role_limits=str(actor.get("role") or "").strip().lower() == "admin",
    )


def _respond_offer_decision_error(handler: Any, err: ValueError, request: Dict[str, Any]) -> None:
    message = str(err) or "gm_free_agent_offer_decision_failed"
    if message.startswith("promise_role_limit_exceeded:"):
        _prefix, role, limit = message.split(":", 2)
        handler._json(409, {
            "error": "promise_role_limit_exceeded", "role": role,
            "limit": parse_int(limit),
            "message": f"{request.get('team_code')} ya ha alcanzado el máximo de promesas firmadas para {role}.",
        })
        return
    status = (
        409 if message in {"profile_has_active_contract", "request_already_decided"}
        else 404 if message in {"free_agent_not_found", "request_not_found", "free_agent_or_team_not_found"}
        else 400
    )
    handler._json(status, {"error": message})


def decide_free_agent_offer_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(
        payload, validate_admin_decision_payload
    ):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_request_id"})
        return
    decision = str(payload.get("decision") or "").strip().lower()
    service = handler.app.free_agency
    request = service.offer_request(request_id)
    if not request:
        handler._json(404, {"error": "request_not_found"})
        return
    if str(request.get("status") or "").lower() != "pending":
        handler._json(409, {"error": "request_already_decided", "request": request})
        return
    if not handler._authorize(
        "admin.gm_free_agent_offer_request.decide",
        {"team_code": request.get("team_code")},
    ):
        return
    actor = handler._current_session() or {}
    options = _offer_decision_options(handler, payload, actor)
    try:
        result = service.decide_offer(
            request_id, decision, actor, options=options, request=request
        )
    except ValueError as err:
        _respond_offer_decision_error(handler, err, request)
        return
    except sqlite3.Error as err:
        handler.log_error("GM free-agent offer approval DB failure request=%s: %s", request_id, err)
        handler._json(500, {"error": "offer_approval_failed", "detail": str(err)[:200]})
        return
    delivered = (
        handler.app.outbox_delivery.dispatch(result.get("outbox_event_ids"))
        if options.notify_discord
        else []
    )
    output = service.admin_decision_output(
        request_id, result, discord_sent=bool(delivered)
    )
    audit = output["audit"]
    handler._log_admin_action(
        audit["action"], "gm_free_agent_offer_request", str(request_id),
        request.get("team_code"), audit.get("details"),
        before=audit.get("before"), after=audit.get("after"),
    )
    handler._json(200, output["response"])
    return

def _respond_option_decision_error(handler: Any, err: ValueError) -> None:
    details = (str(err) or "option_decision_failed").split(":")
    code = details[0]
    if code == "player_team_changed":
        handler._json(409, {
            "error": code,
            "current_team_code": details[1] if len(details) > 1 else None,
            "request_team_code": details[2] if len(details) > 2 else None,
        })
        return
    if code in {"option_changed", "bird_rights_changed"}:
        field = "current_option" if code == "option_changed" else "current_rights"
        handler._json(409, {"error": code, field: details[1] if len(details) > 1 else ""})
        return
    status = 404 if code in {"request_not_found", "player_not_found"} else 409 if code == "request_already_decided" else 400
    handler._json(status, {"error": code})


def _deliver_option_decision_notification(handler: Any, notification: Dict[str, Any], payload: Dict[str, Any]) -> None:
    kwargs = {
        "generate_image": discord_image_requested(payload),
        "custom_image": payload.get("discord_custom_image"),
    }
    if notification["kind"] == "bird_rights":
        handler.app.notifications.bird_rights_renounced(
            notification["player"], notification["season"], notification["value"], **kwargs
        )
    else:
        handler.app.notifications.contract_option_action(
            notification["player"], notification["season"], notification["value"],
            notification["action"], **kwargs
        )


def decide_option_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(
        payload, validate_admin_decision_payload
    ):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_request_id"})
        return
    service = handler.app.player_admin
    request = service.option_request(request_id)
    if not request:
        handler._json(404, {"error": "request_not_found"})
        return
    if str(request.get("status") or "").lower() != "pending":
        handler._json(409, {"error": "request_already_decided", "request": request})
        return
    if not handler._authorize(
        "admin.gm_option_request.decide", {"team_code": request.get("team_code")}
    ):
        return
    try:
        result = service.decide_option(
            request_id,
            str(payload.get("decision") or "").strip().lower(),
            handler._current_session() or {},
            note=str(payload.get("note") or "").strip() or None,
            request=request,
        )
    except ValueError as err:
        _respond_option_decision_error(handler, err)
        return
    audit = result["audit"]
    handler._log_admin_action(
        audit["action"], audit["entity"], str(request_id), request.get("team_code"),
        audit.get("details"), before=audit.get("before"), after=audit.get("after"),
    )
    notification = result.get("notification")
    if notification and discord_notify_requested(payload):
        _deliver_option_decision_notification(handler, notification, payload)
    handler._json(200, result["response"])
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
        user = handler.app.users.replace_team_assignments(
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
    try:
        result = handler.app.settings.update(payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_settings"})
        return
    handler._log_admin_action(
        "update", "settings", None, None, result.get("audit") or {}
    )
    handler._json(200, {"ok": True, "settings": result["settings"]})
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
        ok = handler.app.draft.update_order_entry(draft_order_id, payload)
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
    ok = handler.app.players.update_transaction(transaction_id, payload)
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
        ok = handler.app.players.update_salary_history(salary_history_id, payload)
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
        ok = handler.app.player_identity.update_profile(profile_id, payload)
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
            ("name", 200, False), ("position", 20, False),
            ("bird_rights", 20, False), ("rating", 32, False),
            ("notes", 10_000, False), ("reference_image_url", 2_048, False),
            ("profile_notes", 10_000, False), ("date_of_birth", 32, False),
            ("nationality", 100, False), ("yos_source", 500, False),
            ("transaction_notes", 10_000, False),
        ),
        integer_fields=(("experience_years", 0, 99),),
    ):
        return
    service = handler.app.player_admin
    player_before = service.player(player_id)
    if not player_before:
        handler._json(404, {"error": "player_not_found"})
        return
    if not handler._authorize(
        "admin.player.write", {"team_code": player_before.get("team_code")}
    ):
        return
    try:
        result = service.update_player(
            player_id, payload, handler._current_session() or {}
        )
    except ValueError as err:
        message = str(err) or "invalid_player_update"
        handler._json(404 if message == "player_not_found" else 400, {"error": message})
        return
    handler._log_admin_action(
        "update", "player", str(player_id), player_before.get("team_code"),
        result.get("details") or {}, before=result.get("player_before"),
        after=result.get("player"),
    )
    notification = result.get("notification")
    if notification and discord_notify_requested(payload):
        handler.app.notifications.contract_option_action(
            notification["player"], notification["season"], notification["value"],
            notification["action"],
            generate_image=discord_image_requested(payload),
            custom_image=payload.get("discord_custom_image"),
        )
    handler._json(200, {"ok": True, "player": result.get("player")})
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
    ok = handler.app.teams.update_luxury_history(code, season_year, repeater)
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
    try:
        result = handler.app.team_admin.update(code, payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_team_update"})
        return
    if result["audit"]:
        handler._log_admin_action("update", "team", code.upper(), code.upper(), result["audit"])
    handler._json(200 if result["ok"] else 404, {"ok": result["ok"]})
    return

def update_asset(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        asset_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_asset_id"})
        return
    service = handler.app.asset_admin
    asset_before = service.asset(asset_id)
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
    try:
        result = service.update_asset(asset_id, payload, before=asset_before)
    except ValueError as err:
        handler._json(400, {"error": str(err)})
        return
    audit = result["audit"]
    if audit:
        handler._log_admin_action(
            audit["action"], audit["entity"], audit["entity_id"], audit["team_code"],
            audit["details"], before=audit["before"], after=audit["after"],
        )
    handler._json(200 if result["ok"] else 404, {"ok": result["ok"]})
    return

def update_frozen_draft_pick(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        frozen_pick_id = int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": "invalid_frozen_pick_id"})
        return
    before = handler.app.assets.frozen_pick(frozen_pick_id)
    if not before:
        handler._json(404, {"error": "frozen_pick_not_found"})
        return
    if not handler._authorize("admin.frozen_draft_pick.write", {"team_code": before.get("team_code")}):
        return
    row = handler.app.assets.update_frozen_pick(frozen_pick_id, payload)
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
    service = handler.app.asset_admin
    dead_before = service.dead_contract(dead_contract_id)
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
    result = service.update_dead_contract(dead_contract_id, payload, before=dead_before)
    audit = result["audit"]
    if audit:
        handler._log_admin_action(
            audit["action"], audit["entity"], audit["entity_id"], audit["team_code"],
            audit["details"], before=audit["before"], after=audit["after"],
        )
    handler._json(200 if result["ok"] else 404, {"ok": result["ok"]})
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
