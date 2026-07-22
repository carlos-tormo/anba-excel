"""Remaining administrative PATCH route functions."""

from __future__ import annotations

import json
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
    from ..routing import RouteResponse, error_response, exact_route, json_response, predicate_route, prefix_route
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
    from routing import RouteResponse, error_response, exact_route, json_response, predicate_route, prefix_route
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
def update_offer_promise(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.promise.write"):
        return
    promise_id = parse_int(parsed.path.split("/")[-1])
    if promise_id is None:
        return error_response(400, "invalid_promise_id")
    try:
        session = handler._current_session() or {}
        promise = handler.app.free_agency.update_promise(promise_id, payload, session)
    except ValueError as err:
        message = str(err) or "invalid_promise_status"
        if message.startswith("promise_role_limit_exceeded:"):
            _prefix, role, limit = message.split(":", 2)
            return json_response(
                409,
                {
                    "error": "promise_role_limit_exceeded",
                    "role": role,
                    "limit": parse_int(limit),
                    "message": f"Este equipo ya ha alcanzado el máximo de promesas firmadas para {role}.",
                },
            )
        return error_response(400, message)
    if not promise:
        return error_response(404, "promise_not_found")
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
    return json_response(200, {"ok": True, "promise": promise})

def decide_draft_pick_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(payload, validate_admin_decision_payload):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_request_id")
    admin_decision = str(payload.get("decision") or "").strip().lower()
    if admin_decision not in {"approved", "rejected"}:
        return error_response(400, "invalid_decision")
    draft_service = handler.app.draft
    request = draft_service.pick_request(request_id)
    if not request:
        return error_response(404, "request_not_found")
    if str(request.get("status") or "").lower() != "pending":
        return json_response(409, {"error": "request_already_decided", "request": request})
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
        return error_response(status, message)
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
    return json_response(200, response)

def _offer_decision_options(handler: Any, payload: Dict[str, Any], actor: Dict[str, Any]) -> OfferDecisionOptions:
    return OfferDecisionOptions(
        note=str(payload.get("note") or "").strip() or None,
        notify_discord=discord_notify_requested(payload),
        generate_image=discord_image_requested(payload),
        custom_image=(payload.get("discord_custom_image") if isinstance(payload.get("discord_custom_image"), dict) else None),
        bypass_role_limits=str(actor.get("role") or "").strip().lower() == "admin",
    )


def _respond_offer_decision_error(err: ValueError, request: Dict[str, Any]) -> RouteResponse:
    message = str(err) or "gm_free_agent_offer_decision_failed"
    if message.startswith("promise_role_limit_exceeded:"):
        _prefix, role, limit = message.split(":", 2)
        return json_response(409, {
            "error": "promise_role_limit_exceeded", "role": role,
            "limit": parse_int(limit),
            "message": f"{request.get('team_code')} ya ha alcanzado el máximo de promesas firmadas para {role}.",
        })
    status = (
        409 if message in {"profile_has_active_contract", "request_already_decided"}
        else 404 if message in {"free_agent_not_found", "request_not_found", "free_agent_or_team_not_found"}
        else 400
    )
    return error_response(status, message)


def decide_free_agent_offer_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(
        payload, validate_admin_decision_payload
    ):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_request_id")
    decision = str(payload.get("decision") or "").strip().lower()
    service = handler.app.free_agency
    request = service.offer_request(request_id)
    if not request:
        return error_response(404, "request_not_found")
    if str(request.get("status") or "").lower() != "pending":
        return json_response(409, {"error": "request_already_decided", "request": request})
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
        return _respond_offer_decision_error(err, request)
    except Exception as err:
        handler.log_error("GM free-agent offer approval DB failure request=%s: %s", request_id, err)
        return error_response(500, "offer_approval_failed", detail=str(err)[:200])
    delivered = (
        handler.app.outbox_delivery.dispatch(result.get("outbox_event_ids"))
        if options.notify_discord
        else []
    )
    output = service.admin_decision_output(
        request_id, result, discord_sent=bool(delivered)
    )
    audit = output["audit"]
    audit_details = audit.get("details") if isinstance(audit.get("details"), dict) else {}
    handler._log_admin_action(
        audit["action"], "gm_free_agent_offer_request", str(request_id),
        request.get("team_code"), audit_details,
        before=audit.get("before"), after=audit.get("after"),
        command_id=audit_details.get("command_id"),
        validation_result=audit_details.get("validation_result"),
        entity_versions=audit_details.get("entity_versions"),
        integration_outbox_ids=result.get("outbox_event_ids") or [],
    )
    return json_response(200, output["response"])

def _respond_option_decision_error(err: ValueError) -> RouteResponse:
    details = (str(err) or "option_decision_failed").split(":")
    code = details[0]
    if code == "player_team_changed":
        return json_response(409, {
            "error": code,
            "current_team_code": details[1] if len(details) > 1 else None,
            "request_team_code": details[2] if len(details) > 2 else None,
        })
    if code in {"option_changed", "bird_rights_changed"}:
        field = "current_option" if code == "option_changed" else "current_rights"
        return json_response(409, {"error": code, field: details[1] if len(details) > 1 else ""})
    status = 404 if code in {"request_not_found", "player_not_found"} else 409 if code == "request_already_decided" else 400
    return error_response(status, code)


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


def _option_decision_command_metadata(
    request_id: int,
    request_before: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    request_after = (result.get("request") or (result.get("response") or {}).get("request") or {})
    audit = result.get("audit") or {}
    details = audit.get("details") if isinstance(audit.get("details"), dict) else {}
    status = str(request_after.get("status") or details.get("status") or "").strip().lower()
    if not status:
        status = "decided"
    entity_versions = {
        "request_before_status": request_before.get("status"),
        "request_after_status": request_after.get("status"),
        "player_id": request_before.get("player_id"),
        "team_code": request_before.get("team_code"),
        "option_field": request_before.get("option_field"),
        "option_value": request_before.get("option_value"),
        "option_action": request_before.get("action"),
    }
    if "free_agent_id" in details:
        entity_versions["free_agent_id"] = details.get("free_agent_id")
    if "roster_removed" in details:
        entity_versions["roster_removed"] = details.get("roster_removed")
    return {
        "command_id": f"gm-option:{request_id}:{status}",
        "validation_result": "valid",
        "entity_versions": entity_versions,
    }


def decide_option_request(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._validate_specialized_payload_or_error(
        payload, validate_admin_decision_payload
    ):
        return
    try:
        request_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_request_id")
    service = handler.app.player_admin
    request = service.option_request(request_id)
    if not request:
        return error_response(404, "request_not_found")
    if str(request.get("status") or "").lower() != "pending":
        return json_response(409, {"error": "request_already_decided", "request": request})
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
        return _respond_option_decision_error(err)
    audit = result["audit"]
    handler._log_admin_action(
        audit["action"], audit["entity"], str(request_id), request.get("team_code"),
        audit.get("details"), before=audit.get("before"), after=audit.get("after"),
        **_option_decision_command_metadata(request_id, request, result),
    )
    notification = result.get("notification")
    if notification and discord_notify_requested(payload):
        _deliver_option_decision_notification(handler, notification, payload)
    return json_response(200, result["response"])

def update_admin_user(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.users.write"):
        return
    try:
        user_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_user_id")
    team_codes = payload.get("team_codes")
    if team_codes is None and "team_code" in payload:
        team_code = str(payload.get("team_code") or "").strip()
        team_codes = [team_code] if team_code else []
    if team_codes is None:
        return error_response(400, "team_codes_required")
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
            return json_response(400, {"error": "invalid_team_code", "team_code": message.split(":", 1)[1]})
        raise
    if user is None:
        return error_response(404, "user_not_found")
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
    return json_response(200, {"ok": True, "user": user})

def update_settings(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.global.write"):
        return
    try:
        result = handler.app.settings.update(payload)
    except ValueError as err:
        message = str(err) or "invalid_settings"
        return error_response(409 if message == "stale_entity_version" else 400, message)
    handler._log_admin_action(
        "update", "settings", None, None, result.get("audit") or {}
    )
    return json_response(200, {"ok": True, "settings": result["settings"]})

def update_draft_order(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.draft_order.write"):
        return
    try:
        draft_order_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_draft_order_id")
    try:
        ok = handler.app.draft.update_order_entry(draft_order_id, payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_draft_order")
    if ok:
        handler._log_admin_action(
            "update",
            "draft_order",
            str(draft_order_id),
            payload.get("owner_team_code"),
            {"fields": sorted(payload.keys())},
        )
    return json_response(200 if ok else 404, {"ok": ok})

def update_player_transaction(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.player_profile.write"):
        return
    try:
        transaction_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_transaction_id")
    ok = handler.app.players.update_transaction(transaction_id, payload)
    if ok:
        handler._log_admin_action(
            "update",
            "player_transaction",
            str(transaction_id),
            payload.get("team_code"),
            {"fields": sorted(payload.keys())},
        )
    return json_response(200 if ok else 404, {"ok": ok})

def update_player_salary_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.player_profile.write"):
        return
    try:
        salary_history_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_salary_history_id")
    try:
        ok = handler.app.players.update_salary_history(salary_history_id, payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_salary_history")
    if ok:
        handler._log_admin_action(
            "update",
            "player_salary_history",
            str(salary_history_id),
            payload.get("team_code") or payload.get("last_team"),
            {"fields": sorted(payload.keys())},
        )
    return json_response(200 if ok else 404, {"ok": ok})

def update_player_profile(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.player_profile.write"):
        return
    try:
        profile_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_profile_id")
    try:
        ok = handler.app.player_identity.update_profile(profile_id, payload)
    except ValueError as err:
        message = str(err) or "invalid_profile"
        return error_response(409 if message == "stale_entity_version" else 400, message)
    if ok:
        handler._log_admin_action(
            "update",
            "player_profile",
            str(profile_id),
            None,
            {"fields": sorted(payload.keys())},
        )
    return json_response(200 if ok else 404, {"ok": ok})

def update_player(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    try:
        player_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_player_id")
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
        return error_response(404, "player_not_found")
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
        return error_response(404 if message == "player_not_found" else 400, message)
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
    return json_response(200, {"ok": True, "player": result.get("player")})

def update_team_luxury_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    parts = parsed.path.split("/")
    if len(parts) < 5:
        return error_response(404, "not_found")
    code = parts[3]
    if not handler._authorize("admin.team.write", {"team_code": code}):
        return
    season_year = parse_int(payload.get("season_year"))
    if season_year is None or season_year < 2000 or season_year > 2100:
        return error_response(400, "invalid_season_year")
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
    return json_response(200 if ok else 404, {"ok": ok})

def update_team(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    code = parsed.path.split("/")[-1]
    if not handler._authorize("admin.team.write", {"team_code": code}):
        return
    try:
        result = handler.app.team_admin.update(code, payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_team_update")
    if result["audit"]:
        handler._log_admin_action("update", "team", code.upper(), code.upper(), result["audit"])
    return json_response(200 if result["ok"] else 404, {"ok": result["ok"]})

def update_asset(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    try:
        asset_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_asset_id")
    service = handler.app.asset_admin
    asset_before = service.asset(asset_id)
    if not asset_before:
        return error_response(404, "asset_not_found")
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
        return error_response(400, str(err))
    audit = result["audit"]
    if audit:
        handler._log_admin_action(
            audit["action"], audit["entity"], audit["entity_id"], audit["team_code"],
            audit["details"], before=audit["before"], after=audit["after"],
        )
    return json_response(200 if result["ok"] else 404, {"ok": result["ok"]})

def update_frozen_draft_pick(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    try:
        frozen_pick_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_frozen_pick_id")
    before = handler.app.assets.frozen_pick(frozen_pick_id)
    if not before:
        return error_response(404, "frozen_pick_not_found")
    if not handler._authorize("admin.frozen_draft_pick.write", {"team_code": before.get("team_code")}):
        return
    row = handler.app.assets.update_frozen_pick(frozen_pick_id, payload)
    if not row:
        return error_response(404, "frozen_pick_not_found")
    handler._log_admin_action(
        "update",
        "frozen_draft_pick",
        str(frozen_pick_id),
        row.get("team_code"),
        {"fields": sorted(payload.keys())},
        before=before,
        after=row,
    )
    return json_response(200, {"ok": True, "frozen_pick": row})

def update_dead_contract(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    try:
        dead_contract_id = int(parsed.path.split("/")[-1])
    except ValueError:
        return error_response(400, "invalid_dead_contract_id")
    service = handler.app.asset_admin
    dead_before = service.dead_contract(dead_contract_id)
    if not dead_before:
        return error_response(404, "dead_contract_not_found")
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
    return json_response(200 if result["ok"] else 404, {"ok": result["ok"]})


def _team_luxury_history_path(path: str) -> bool:
    return path.startswith("/api/teams/") and path.endswith("/luxury-history")


PATCH_REMAINING_ROUTES = (
    prefix_route("/api/admin/free-agent-offer-promises/", update_offer_promise, permission="admin.promise.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/admin/gm-draft-pick-requests/", decide_draft_pick_request, permission="admin.gm_draft_pick_request.decide", csrf=True, mutates_league_state=True),
    prefix_route("/api/admin/gm-free-agent-offer-requests/", decide_free_agent_offer_request, permission="admin.gm_free_agent_offer_request.decide", csrf=True, mutates_league_state=True),
    prefix_route("/api/admin/gm-option-requests/", decide_option_request, permission="admin.gm_option_request.decide", csrf=True, mutates_league_state=True),
    prefix_route("/api/admin/users/", update_admin_user, permission="admin.users.write", csrf=True, mutates_league_state=True),
    exact_route("/api/settings", update_settings, permission="admin.global.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/draft-order/", update_draft_order, permission="admin.draft_order.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/player-transactions/", update_player_transaction, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/player-salary-history/", update_player_salary_history, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/player-profiles/", update_player_profile, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/players/", update_player, permission="admin.player.write", csrf=True, mutates_league_state=True),
    predicate_route("team-luxury-history", _team_luxury_history_path, update_team_luxury_history, permission="admin.team.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/teams/", update_team, permission="admin.team.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/assets/", update_asset, permission="admin.draft_asset.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/frozen-draft-picks/", update_frozen_draft_pick, permission="admin.frozen_draft_pick.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/dead-contracts/", update_dead_contract, permission="admin.dead_contract.write", csrf=True, mutates_league_state=True),
)
