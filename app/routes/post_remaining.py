"""Remaining authentication and administrative POST routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import ParseResult

try:
    from ..auth.policies import normalize_team_code
    from ..auth.sessions import verify_admin_password
    from ..domain.trade_rules import normalize_trade_bucket
    from ..domain_rules import parse_bool, parse_int, public_settings_payload
    from ..routing import RouteResponse, error_response, exact_route, json_response, predicate_route
    from .validation import validate_coadmin_vote_submit_payload, validate_gm_option_request_payload
    from ..services.notifications import discord_image_requested, discord_notify_requested
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from auth.sessions import verify_admin_password
    from domain.trade_rules import normalize_trade_bucket
    from domain_rules import parse_bool, parse_int, public_settings_payload
    from routing import RouteResponse, error_response, exact_route, json_response, predicate_route
    from routes.validation import validate_coadmin_vote_submit_payload, validate_gm_option_request_payload
    from services.notifications import discord_image_requested, discord_notify_requested


PLAYER_CONTRACT_SEASONS = [2025, 2026, 2027, 2028, 2029, 2030, 2031]
PLAYER_CONTRACT_MIN_YEAR = min(PLAYER_CONTRACT_SEASONS)
PLAYER_CONTRACT_MAX_YEAR = max(PLAYER_CONTRACT_SEASONS)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def logout(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if handler._is_authenticated() and not handler._require_csrf():
        return
    handler._clear_session()
    return json_response(200, {"ok": True}, headers={"Set-Cookie": handler._clear_session_cookie()})

def update_cartera_ruleout(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.ruleout"):
        return
    if not handler._require_csrf():
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 5:
        return error_response(404, "not_found")
    free_agent_id = parse_int(parts[3])
    if free_agent_id is None:
        return error_response(400, "invalid_free_agent_id")
    team_code = normalize_team_code(payload.get("team_code"))
    ruled_out = parse_bool(payload.get("ruled_out"))
    if not team_code:
        return error_response(400, "team_code_required")
    try:
        rows = handler.app.free_agency.set_ruleout(
            free_agent_id,
            team_code,
            handler._current_session() or {},
            ruled_out=ruled_out,
        )
    except PermissionError as err:
        return error_response(403, str(err) or "agent_client_required")
    except ValueError as err:
        message = str(err) or "invalid_ruleout"
        status = 404 if message == "free_agent_not_found" else 400
        return error_response(status, message)
    return json_response(
        200,
        {
            "ok": True,
            "free_agent_id": free_agent_id,
            "team_code": team_code,
            "ruled_out": bool(ruled_out),
            "ruled_out_teams": [
                {
                    "id": parse_int(item.get("id")),
                    "team_code": normalize_team_code(item.get("team_code")),
                    "team_name": str(item.get("team_name") or "").strip(),
                    "updated_at": str(item.get("updated_at") or item.get("created_at") or "").strip(),
                }
                for item in rows
            ],
        },
    )

def login(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> RouteResponse:
    payload = payload or {}
    ip = handler._client_ip()
    blocked, retry_after = handler._rate_limit_status(ip)
    if blocked:
        return json_response(429, {"error": "too_many_attempts", "retry_after_seconds": retry_after})
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    if username != handler.admin_user or not verify_admin_password(password, handler.admin_password, handler.admin_password_hash):
        handler._rate_limit_fail(ip)
        return error_response(401, "invalid_credentials")

    token, csrf_token = handler._start_session(
        {
            "provider": "local",
            "user_id": None,
            "email": username,
            "name": username,
            "role": "admin",
            "logged_in_at": now_iso(),
        }
    )
    handler._rate_limit_success(ip)
    cookie = handler._session_cookie(token)
    return json_response(200, {"ok": True, "csrf_token": csrf_token}, headers={"Set-Cookie": cookie})

def validate_trade_process(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    trade_service = handler.app.trades
    if isinstance(payload.get("selections"), (list, dict)) or isinstance(payload.get("teams"), list):
        normalized = trade_service.normalize_request(payload)
        for code in normalized.get("teams") or []:
            if not handler._authorize("admin.trade.process", {"team_code": code}):
                return
        validation = trade_service.validate(
            {
                **payload,
                "teams": normalized.get("teams") or [],
                "selections": normalized.get("selections") or [],
                "cash": normalized.get("cash") or [],
            }
        )
        return json_response(200, {"ok": True, "validation": validation})
    team_a = normalize_team_code(payload.get("team_a")) or ""
    team_b = normalize_team_code(payload.get("team_b")) or ""
    if not handler._authorize("admin.trade.process", {"team_code": team_a}):
        return
    if not handler._authorize("admin.trade.process", {"team_code": team_b}):
        return
    validation = trade_service.validate_process_payload({
        **payload,
        "team_a": team_a,
        "team_b": team_b,
    })
    return json_response(200, {"ok": True, "validation": validation})

def request_gm_option(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._validate_specialized_payload_or_error(payload, validate_gm_option_request_payload):
        return
    player_id = parse_int(payload.get("player_id"))
    if player_id is None:
        return error_response(400, "invalid_player_id")
    option_field = str(payload.get("option_field") or "").strip()
    option_value = str(payload.get("option_value") or "").strip().upper()
    option_action = str(payload.get("action") or "").strip().lower()
    player = handler.app.players.record(player_id)
    if not player:
        return error_response(404, "player_not_found")
    if not handler._authorize("gm.option_request.create", {"team_code": player.get("team_code")}):
        return
    try:
        request = handler.app.gm_request_queries.create_option(
            player_id,
            option_field,
            option_value,
            option_action,
            handler._current_session() or {},
        )
    except ValueError as err:
        message = str(err)
        if message == "invalid_option_field":
            return error_response(400, "invalid_option_field")
        if message == "invalid_option_value":
            return error_response(400, "invalid_option_value")
        if message == "invalid_option_action":
            return error_response(400, "invalid_option_action")
        if message == "option_mismatch":
            return error_response(409, "option_changed")
        raise
    if not request:
        return error_response(404, "player_not_found")
    return json_response(201, {"ok": True, "request": request})

def submit_coadmin_vote(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("coadmin.vote.submit"):
        return
    if not handler._require_csrf():
        return
    if not handler._validate_specialized_payload_or_error(payload, validate_coadmin_vote_submit_payload):
        return
    session = handler._current_session() or {}
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        return error_response(404, "not_found")
    vote_id = parse_int(parts[2])
    if vote_id is None:
        return error_response(400, "invalid_vote_id")
    try:
        vote = handler.app.coadmin_votes.submit_coadmin_vote(vote_id, payload.get("scores"), session)
    except ValueError as err:
        message = str(err) or "invalid_vote"
        status = 409 if message in {"vote_closed", "vote_not_found"} or message.startswith("missing_scores:") else 400
        return error_response(status, message)
    return json_response(200, {"ok": True, "vote": vote})

def create_coadmin_vote(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.coadmin_vote.write"):
        return
    try:
        vote = handler.app.coadmin_votes.create_coadmin_vote(payload.get("title"), handler._current_session() or {})
    except ValueError as err:
        return error_response(400, str(err) or "invalid_vote")
    handler._log_admin_action(
        "create",
        "coadmin_vote",
        str(vote.get("id")),
        None,
        {"title": vote.get("title")},
        command_id=f"coadmin-vote:{vote.get('id')}:create",
        validation_result="valid",
        entity_versions={
            "vote_id": vote.get("id"),
            "title": vote.get("title"),
            "status": vote.get("status"),
            "created_at": vote.get("created_at"),
        },
    )
    return json_response(201, {"ok": True, "vote": vote})

def create_offer_promise(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.promise.write"):
        return
    try:
        session = handler._current_session() or {}
        promise = handler.app.free_agency.create_promise(payload, session)
    except ValueError as err:
        message = str(err) or "invalid_promise"
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
        status = 404 if message in {"team_not_found", "profile_not_found"} else 400
        return error_response(status, message)
    handler._log_admin_action(
        "create",
        "free_agent_offer_promise",
        str(promise.get("id")),
        promise.get("team_code"),
        {
            "manual": True,
            "status": promise.get("status"),
            "player_name": promise.get("player_name"),
            "role": promise.get("role"),
            "season_year": promise.get("season_year"),
        },
        after={"promise": promise},
    )
    return json_response(201, {"ok": True, "promise": promise})

def generate_offseason_exceptions(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.offseason_exceptions.write"):
        return
    season_year = parse_int(payload.get("season_year"))
    if season_year is None:
        return error_response(400, "invalid_season_year")
    try:
        result = handler.app.offseason_exceptions.generate(
            season_year,
            team_codes=payload.get("team_codes") if isinstance(payload.get("team_codes"), list) else None,
            choices=payload.get("choices") if isinstance(payload.get("choices"), dict) else None,
        )
    except ValueError as err:
        return error_response(400, str(err) or "invalid_request")
    handler._log_admin_action(
        "generate",
        "offseason_exceptions",
        str(season_year),
        None,
        {
            "generated_count": sum(len(row.get("created") or []) for row in result.get("generated", [])),
            "team_count": len(result.get("generated") or []),
            "skipped": result.get("skipped") or [],
        },
    )
    return json_response(200, result)

def bulk_create_free_agents(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.free_agent.write"):
        return
    try:
        result = handler.app.free_agency.bulk_create_free_agents(payload.get("names") or payload.get("text") or "")
    except ValueError as err:
        if str(err) == "too_many_names":
            return error_response(400, "too_many_names")
        raise
    handler._log_admin_action(
        "bulk_create",
        "free_agent",
        None,
        None,
        {
            "created_count": result.get("created_count"),
            "skipped_count": result.get("skipped_count"),
            "created_names": [item.get("name") for item in (result.get("created") or [])[:25]],
        },
    )
    return json_response(201, result)

def create_free_agent(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.free_agent.write"):
        return
    free_agent_id = handler.app.free_agency.create_free_agent(payload)
    if not free_agent_id:
        return error_response(400, "name_required")
    handler._log_admin_action("create", "free_agent", str(free_agent_id), None, {"name": payload.get("name")})
    return json_response(201, {"free_agent_id": free_agent_id})

def create_draft_order(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.draft_order.write"):
        return
    try:
        draft_order_id = handler.app.draft.create_order_entry(payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_draft_order")
    handler._log_admin_action(
        "create",
        "draft_order",
        str(draft_order_id),
        payload.get("owner_team_code"),
        {
            "draft_year": payload.get("draft_year"),
            "draft_round": payload.get("draft_round"),
            "pick_number": payload.get("pick_number"),
            "original_team_code": payload.get("original_team_code"),
        },
    )
    return json_response(201, {"draft_order_id": draft_order_id})

def sign_free_agent(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        return error_response(404, "not_found")
    try:
        free_agent_id = int(parts[2])
    except ValueError:
        return error_response(400, "invalid_free_agent_id")
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("admin.free_agent.sign", {"team_code": team_code}):
        return
    try:
        result = handler.app.free_agency.sign_free_agent(free_agent_id, team_code, payload)
    except ValueError as err:
        if str(err) == "profile_has_active_contract":
            return error_response(409, "profile_has_active_contract")
        if str(err) == "free_agent_or_team_not_found":
            return error_response(404, "free_agent_or_team_not_found")
        raise
    player_id = result["player_id"]
    player_after = result["player"]
    handler._log_admin_action(
        "sign",
        "free_agent",
        str(free_agent_id),
        team_code,
        {"player_id": player_id, "name": payload.get("name")},
        after=player_after,
    )
    if player_after and discord_notify_requested(payload):
        handler.app.notifications.free_agent_signed(
            player_after,
            generate_image=discord_image_requested(payload),
            custom_image=payload.get("discord_custom_image"),
        )
    return json_response(200, {"ok": True, "player_id": player_id})

def merge_player_profiles(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.player_profile.write"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        return error_response(404, "not_found")
    try:
        target_profile_id = int(parts[2])
    except ValueError:
        return error_response(400, "invalid_profile_id")
    source_profile_id = parse_int(payload.get("source_profile_id"))
    if source_profile_id is None:
        return error_response(400, "source_profile_id_required")
    try:
        result = handler.app.player_identity.merge_profiles(
            int(source_profile_id),
            int(target_profile_id),
            expected_source_version=payload.get("expected_source_version"),
            expected_target_version=payload.get("expected_target_version"),
        )
    except Exception as err:
        handler.log_message(
            "Player profile merge failed source=%s target=%s: %s",
            source_profile_id,
            target_profile_id,
            err,
        )
        return error_response(500, "merge_failed")
    if not result.get("ok"):
        status = 409 if result.get("error") == "active_contract_conflict" else 404
        if result.get("error") == "stale_entity_version":
            status = 409
        if result.get("error") == "invalid_profile_id":
            status = 400
        return error_response(status, result.get("error") or "merge_failed")
    handler._log_admin_action(
        "merge",
        "player_profile",
        str(target_profile_id),
        None,
        {
            "source_profile_id": int(source_profile_id),
            "target_profile_id": int(target_profile_id),
            "moved": result.get("moved") or {},
            "deleted": result.get("deleted") or {},
        },
    )
    return json_response(200, result)

def create_salary_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.player_profile.write"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        return error_response(404, "not_found")
    try:
        profile_id = int(parts[2])
    except ValueError:
        return error_response(400, "invalid_profile_id")
    try:
        row = handler.app.players.create_salary_history(profile_id, payload)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_salary_history")
    if not row:
        return error_response(404, "profile_not_found")
    handler._log_admin_action(
        "create",
        "player_salary_history",
        str(row.get("id") or ""),
        row.get("team_code"),
        {"profile_id": profile_id, "season_year": row.get("season_year")},
    )
    return json_response(201, {"salary_history": row})

def create_player_transaction(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.player_profile.write"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        return error_response(404, "not_found")
    try:
        profile_id = int(parts[2])
    except ValueError:
        return error_response(400, "invalid_profile_id")
    transaction_id = handler.app.players.create_transaction(profile_id, payload)
    if not transaction_id:
        return error_response(400, "transaction_summary_required_or_profile_not_found")
    handler._log_admin_action(
        "create",
        "player_transaction",
        str(transaction_id),
        payload.get("team_code"),
        {"profile_id": profile_id, "summary": payload.get("summary")},
    )
    return json_response(201, {"transaction_id": transaction_id})

def process_trade(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    service = handler.app.trades
    teams = service.request_team_codes(payload)
    for team_code in teams:
        if not handler._authorize("admin.trade.process", {"team_code": team_code}):
            return
    try:
        outcome = service.process_request(
            payload,
            actor=handler._current_session(),
            command_id=str(getattr(handler, "headers", {}).get("Idempotency-Key") or "").strip() or None,
            notify_discord=discord_notify_requested(payload),
            generate_image=discord_image_requested(payload),
            custom_image=(
                payload.get("discord_custom_image")
                if isinstance(payload.get("discord_custom_image"), dict)
                else None
            ),
        )
    except ValueError as err:
        return json_response(409, {"ok": False, "error": str(err) or "trade_processing_failed"})
    audit = outcome.get("audit")
    if audit:
        details = audit.get("details") if isinstance(audit.get("details"), dict) else {}
        handler._log_admin_action(
            "trade", "trade", None, None, details,
            before=audit.get("before"), after=audit.get("after"),
            team_codes=outcome.get("team_codes") or [],
            command_id=details.get("command_id"),
            validation_result=details.get("validation_result"),
            entity_versions=details.get("entity_versions"),
            integration_outbox_ids=outcome.get("outbox_event_ids") or [],
        )
    delivered = handler.app.outbox_delivery.dispatch(outcome.get("outbox_event_ids"))
    if delivered and isinstance(outcome.get("result"), dict):
        outcome["result"]["delivered_events"] = delivered
    return json_response(int(outcome.get("status_code") or 200), outcome["response"])

def create_move_adjustment(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    parts = parsed.path.split("/")
    if len(parts) < 5:
        return error_response(404, "not_found")
    code = parts[3]
    season_year = parse_int(payload.get("season_year"))
    target_remaining = parse_int(payload.get("target_remaining"))
    bucket = payload.get("bucket")
    note = str(payload.get("note") or "").strip() or None
    if season_year is None or season_year < PLAYER_CONTRACT_MIN_YEAR or season_year > PLAYER_CONTRACT_MAX_YEAR:
        return error_response(400, "invalid_season_year")
    if target_remaining is None or target_remaining < 0:
        return error_response(400, "invalid_target_remaining")
    if not handler._authorize("admin.team_moves.write", {"team_code": code}):
        return
    result = handler.app.trades.adjust_team_move_remaining(code, season_year, bucket, target_remaining, note)
    if result:
        handler._log_admin_action("update", "team_move", code.upper(), code.upper(), result)
    return json_response(200 if result else 404, {"ok": bool(result), "result": result})

def create_asset(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("admin.draft_asset.write", {"team_code": team_code}):
        return
    if str(payload.get("asset_type") or "").strip().lower() == "dead_cap":
        return error_response(400, "dead_cap_moved_to_dead_contracts")
    asset_id = handler.app.assets.create_asset(team_code, payload)
    if not asset_id:
        return error_response(404, "team_not_found")
    handler._log_admin_action("create", "asset", str(asset_id), str(team_code), {"asset_type": payload.get("asset_type")})
    return json_response(201, {"asset_id": asset_id})

def create_frozen_draft_pick(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("admin.frozen_draft_pick.write", {"team_code": team_code}):
        return
    row = handler.app.assets.create_frozen_pick(team_code, payload)
    if not row:
        return error_response(400, "invalid_frozen_pick")
    handler._log_admin_action(
        "create",
        "frozen_draft_pick",
        str(row.get("id")),
        team_code,
        row,
    )
    return json_response(201, {"ok": True, "frozen_pick": row})

def create_dead_contract(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("admin.dead_contract.write", {"team_code": team_code}):
        return
    dead_contract_id = handler.app.assets.create_dead_contract(team_code, payload)
    if not dead_contract_id:
        return error_response(404, "team_not_found")
    handler._log_admin_action(
        "create",
        "dead_contract",
        str(dead_contract_id),
        str(team_code),
        {"dead_type": payload.get("dead_type"), "label": payload.get("label")},
    )
    return json_response(201, {"dead_contract_id": dead_contract_id})

def create_gm_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = str(payload.get("team_code") or "").strip().upper()
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("admin.gm_history.write", {"team_code": team_code}):
        return
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        return error_response(400, "entries_required")
    try:
        rows = handler.app.teams.replace_gm_history(team_code, raw_entries)
    except ValueError as err:
        return error_response(400, str(err) or "invalid_gm_history")
    if rows is None:
        return error_response(404, "team_not_found")
    handler._log_admin_action(
        "update",
        "gm_history",
        team_code,
        team_code,
        {"entries_count": len(rows)},
    )
    return json_response(200, {"ok": True, "gm_history": rows})

def progress_settings_year(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.global.write"):
        return
    try:
        result = handler.app.season_rollover.progress_to_next_year(
            expected_current_year=payload.get("expected_current_year"),
            expected_current_year_version=payload.get("expected_current_year_version"),
        )
    except ValueError as err:
        if str(err) in {"cannot_progress_beyond_2030", "cannot_progress_beyond_contract_window"}:
            return error_response(400, "cannot_progress_beyond_contract_window")
        if str(err) == "stale_entity_version":
            return error_response(409, "stale_entity_version")
        raise
    merged = handler.app.settings.get_all()
    handler._log_admin_action(
        "update",
        "settings",
        None,
        None,
        {"progress_year": result},
        before={"current_year": result.get("previous_year")},
        after={"current_year": result.get("current_year")},
        command_id=result.get("command_id"),
        validation_result=result.get("validation_result"),
        entity_versions=result.get("entity_versions"),
    )
    return json_response(
        200,
        {
            "ok": True,
            "result": result,
            "settings": public_settings_payload(merged),
        },
    )


def _cartera_ruleout_path(path: str) -> bool:
    return path.startswith("/api/cartera/clients/") and path.endswith("/ruleout")


def _coadmin_vote_submit_path(path: str) -> bool:
    return path.startswith("/api/coadmin-votes/") and path.endswith("/submit")


def _free_agent_sign_path(path: str) -> bool:
    return path.startswith("/api/free-agents/") and path.endswith("/sign")


def _profile_action_path(action: str):
    return lambda path: path.startswith("/api/player-profiles/") and path.endswith(f"/{action}")


def _team_move_adjustment_path(path: str) -> bool:
    return path.startswith("/api/teams/") and path.endswith("/move-adjustment")


EARLY_POST_ROUTES = (exact_route("/api/auth/logout", logout, auth_exempt_reason="session_logout"),)
POST_REMAINING_ROUTES = (
    predicate_route("cartera-ruleout", _cartera_ruleout_path, update_cartera_ruleout, permission="coadmin.cartera.ruleout", csrf=True, mutates_league_state=True),
    exact_route("/api/auth/login", login, auth_exempt_reason="session_login"),
    exact_route("/api/trades/process/validate", validate_trade_process, auth_exempt_reason="read_only_validation"),
    exact_route("/api/gm/option-requests", request_gm_option, permission="gm.option_request.create", csrf=True, mutates_league_state=True),
    predicate_route("coadmin-vote-submit", _coadmin_vote_submit_path, submit_coadmin_vote, permission="coadmin.vote.submit", csrf=True, mutates_league_state=True),
    exact_route("/api/admin/coadmin-votes", create_coadmin_vote, permission="admin.coadmin_vote.write", csrf=True, mutates_league_state=True),
    exact_route("/api/admin/free-agent-offer-promises", create_offer_promise, permission="admin.promise.write", csrf=True, mutates_league_state=True),
    exact_route("/api/offseason-exceptions/generate", generate_offseason_exceptions, permission="admin.offseason_exceptions.write", csrf=True, mutates_league_state=True),
    exact_route("/api/free-agents/bulk", bulk_create_free_agents, permission="admin.free_agent.write", csrf=True, mutates_league_state=True),
    exact_route("/api/free-agents", create_free_agent, permission="admin.free_agent.write", csrf=True, mutates_league_state=True),
    exact_route("/api/draft-order", create_draft_order, permission="admin.draft_order.write", csrf=True, mutates_league_state=True),
    predicate_route("free-agent-sign", _free_agent_sign_path, sign_free_agent, permission="admin.free_agent.sign", csrf=True, mutates_league_state=True),
    predicate_route("player-profile-merge", _profile_action_path("merge"), merge_player_profiles, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    predicate_route("player-salary-history-create", _profile_action_path("salary-history"), create_salary_history, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    predicate_route("player-transaction-create", _profile_action_path("transactions"), create_player_transaction, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    exact_route("/api/trades/process", process_trade, permission="admin.trade.process", csrf=True, mutates_league_state=True),
    predicate_route("team-move-adjustment", _team_move_adjustment_path, create_move_adjustment, permission="admin.team_moves.write", csrf=True, mutates_league_state=True),
    exact_route("/api/assets", create_asset, permission="admin.draft_asset.write", csrf=True, mutates_league_state=True),
    exact_route("/api/frozen-draft-picks", create_frozen_draft_pick, permission="admin.frozen_draft_pick.write", csrf=True, mutates_league_state=True),
    exact_route("/api/dead-contracts", create_dead_contract, permission="admin.dead_contract.write", csrf=True, mutates_league_state=True),
    exact_route("/api/gm-history", create_gm_history, permission="admin.gm_history.write", csrf=True, mutates_league_state=True),
    exact_route("/api/settings/progress-year", progress_settings_year, permission="admin.global.write", csrf=True, mutates_league_state=True),
)
