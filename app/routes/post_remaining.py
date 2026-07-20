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
    from ..routing import exact_route, predicate_route
    from .validation import validate_coadmin_vote_submit_payload, validate_gm_option_request_payload
    from ..services.notifications import discord_image_requested, discord_notify_requested
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from auth.sessions import verify_admin_password
    from domain.trade_rules import normalize_trade_bucket
    from domain_rules import parse_bool, parse_int, public_settings_payload
    from routing import exact_route, predicate_route
    from routes.validation import validate_coadmin_vote_submit_payload, validate_gm_option_request_payload
    from services.notifications import discord_image_requested, discord_notify_requested


PLAYER_CONTRACT_SEASONS = [2025, 2026, 2027, 2028, 2029, 2030, 2031]
PLAYER_CONTRACT_MIN_YEAR = min(PLAYER_CONTRACT_SEASONS)
PLAYER_CONTRACT_MAX_YEAR = max(PLAYER_CONTRACT_SEASONS)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def logout(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if handler._is_authenticated() and not handler._require_csrf():
        return
    handler._clear_session()
    handler._json(200, {"ok": True}, headers={"Set-Cookie": handler._clear_session_cookie()})
    return

def update_cartera_ruleout(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.ruleout"):
        return
    if not handler._require_csrf():
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 5:
        handler._json(404, {"error": "not_found"})
        return
    free_agent_id = parse_int(parts[3])
    if free_agent_id is None:
        handler._json(400, {"error": "invalid_free_agent_id"})
        return
    team_code = normalize_team_code(payload.get("team_code"))
    ruled_out = parse_bool(payload.get("ruled_out"))
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    try:
        if ruled_out:
            rows = handler.app.free_agency.repository.set_ruleout(
                free_agent_id,
                team_code,
                handler._current_session() or {},
            )
        else:
            rows = handler.app.free_agency.repository.delete_ruleout(
                free_agent_id,
                team_code,
                handler._current_session() or {},
            )
    except PermissionError as err:
        handler._json(403, {"error": str(err) or "agent_client_required"})
        return
    except ValueError as err:
        message = str(err) or "invalid_ruleout"
        status = 404 if message == "free_agent_not_found" else 400
        handler._json(status, {"error": message})
        return
    handler._json(
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
    return

def login(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    ip = handler._client_ip()
    blocked, retry_after = handler._rate_limit_status(ip)
    if blocked:
        handler._json(429, {"error": "too_many_attempts", "retry_after_seconds": retry_after})
        return
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    if username != handler.admin_user or not verify_admin_password(password, handler.admin_password, handler.admin_password_hash):
        handler._rate_limit_fail(ip)
        handler._json(401, {"error": "invalid_credentials"})
        return

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
    handler._json(200, {"ok": True, "csrf_token": csrf_token}, headers={"Set-Cookie": cookie})
    return

def validate_trade_process(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
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
        handler._json(200, {"ok": True, "validation": validation})
        return
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
    handler._json(200, {"ok": True, "validation": validation})
    return

def request_gm_option(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._validate_specialized_payload_or_error(payload, validate_gm_option_request_payload):
        return
    player_id = parse_int(payload.get("player_id"))
    if player_id is None:
        handler._json(400, {"error": "invalid_player_id"})
        return
    option_field = str(payload.get("option_field") or "").strip()
    option_value = str(payload.get("option_value") or "").strip().upper()
    option_action = str(payload.get("action") or "").strip().lower()
    player = handler.app.players.record(player_id)
    if not player:
        handler._json(404, {"error": "player_not_found"})
        return
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
            handler._json(400, {"error": "invalid_option_field"})
            return
        if message == "invalid_option_value":
            handler._json(400, {"error": "invalid_option_value"})
            return
        if message == "invalid_option_action":
            handler._json(400, {"error": "invalid_option_action"})
            return
        if message == "option_mismatch":
            handler._json(409, {"error": "option_changed"})
            return
        raise
    if not request:
        handler._json(404, {"error": "player_not_found"})
        return
    handler._json(201, {"ok": True, "request": request})
    return

def submit_coadmin_vote(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
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
        handler._json(404, {"error": "not_found"})
        return
    vote_id = parse_int(parts[2])
    if vote_id is None:
        handler._json(400, {"error": "invalid_vote_id"})
        return
    try:
        vote = handler.app.coadmin_votes.submit_coadmin_vote(vote_id, payload.get("scores"), session)
    except ValueError as err:
        message = str(err) or "invalid_vote"
        status = 409 if message in {"vote_closed", "vote_not_found"} or message.startswith("missing_scores:") else 400
        handler._json(status, {"error": message})
        return
    handler._json(200, {"ok": True, "vote": vote})
    return

def create_coadmin_vote(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
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
        handler._json(400, {"error": str(err) or "invalid_vote"})
        return
    handler._log_admin_action(
        "create",
        "coadmin_vote",
        str(vote.get("id")),
        None,
        {"title": vote.get("title")},
    )
    handler._json(201, {"ok": True, "vote": vote})
    return

def create_offer_promise(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
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
        status = 404 if message in {"team_not_found", "profile_not_found"} else 400
        handler._json(status, {"error": message})
        return
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
    handler._json(201, {"ok": True, "promise": promise})
    return

def generate_offseason_exceptions(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.offseason_exceptions.write"):
        return
    season_year = parse_int(payload.get("season_year"))
    if season_year is None:
        handler._json(400, {"error": "invalid_season_year"})
        return
    try:
        result = handler.app.offseason_exceptions.generate(
            season_year,
            team_codes=payload.get("team_codes") if isinstance(payload.get("team_codes"), list) else None,
            choices=payload.get("choices") if isinstance(payload.get("choices"), dict) else None,
        )
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_request"})
        return
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
    handler._json(200, result)
    return

def bulk_create_free_agents(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.free_agent.write"):
        return
    try:
        result = handler.app.free_agency.repository.bulk_create_free_agents(payload.get("names") or payload.get("text") or "")
    except ValueError as err:
        if str(err) == "too_many_names":
            handler._json(400, {"error": "too_many_names"})
            return
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
    handler._json(201, result)
    return

def create_free_agent(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.free_agent.write"):
        return
    free_agent_id = handler.app.free_agency.repository.create_free_agent(payload)
    if not free_agent_id:
        handler._json(400, {"error": "name_required"})
        return
    handler._log_admin_action("create", "free_agent", str(free_agent_id), None, {"name": payload.get("name")})
    handler._json(201, {"free_agent_id": free_agent_id})
    return

def create_draft_order(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
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
        handler._json(400, {"error": str(err) or "invalid_draft_order"})
        return
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
    handler._json(201, {"draft_order_id": draft_order_id})
    return

def sign_free_agent(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        handler._json(404, {"error": "not_found"})
        return
    try:
        free_agent_id = int(parts[2])
    except ValueError:
        handler._json(400, {"error": "invalid_free_agent_id"})
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("admin.free_agent.sign", {"team_code": team_code}):
        return
    try:
        result = handler.app.free_agency.sign_free_agent(free_agent_id, team_code, payload)
    except ValueError as err:
        if str(err) == "profile_has_active_contract":
            handler._json(409, {"error": "profile_has_active_contract"})
            return
        if str(err) == "free_agent_or_team_not_found":
            handler._json(404, {"error": "free_agent_or_team_not_found"})
            return
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
    handler._json(200, {"ok": True, "player_id": player_id})
    return

def merge_player_profiles(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.player_profile.write"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        handler._json(404, {"error": "not_found"})
        return
    try:
        target_profile_id = int(parts[2])
    except ValueError:
        handler._json(400, {"error": "invalid_profile_id"})
        return
    source_profile_id = parse_int(payload.get("source_profile_id"))
    if source_profile_id is None:
        handler._json(400, {"error": "source_profile_id_required"})
        return
    try:
        result = handler.app.player_identity.merge_profiles(
            int(source_profile_id), int(target_profile_id)
        )
    except Exception as err:
        handler.log_message(
            "Player profile merge failed source=%s target=%s: %s",
            source_profile_id,
            target_profile_id,
            err,
        )
        handler._json(500, {"error": "merge_failed"})
        return
    if not result.get("ok"):
        status = 409 if result.get("error") == "active_contract_conflict" else 404
        if result.get("error") == "invalid_profile_id":
            status = 400
        handler._json(status, {"error": result.get("error") or "merge_failed"})
        return
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
    handler._json(200, result)
    return

def create_salary_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.player_profile.write"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        handler._json(404, {"error": "not_found"})
        return
    try:
        profile_id = int(parts[2])
    except ValueError:
        handler._json(400, {"error": "invalid_profile_id"})
        return
    try:
        row = handler.app.players.create_salary_history(profile_id, payload)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_salary_history"})
        return
    if not row:
        handler._json(404, {"error": "profile_not_found"})
        return
    handler._log_admin_action(
        "create",
        "player_salary_history",
        str(row.get("id") or ""),
        row.get("team_code"),
        {"profile_id": profile_id, "season_year": row.get("season_year")},
    )
    handler._json(201, {"salary_history": row})
    return

def create_player_transaction(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.player_profile.write"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        handler._json(404, {"error": "not_found"})
        return
    try:
        profile_id = int(parts[2])
    except ValueError:
        handler._json(400, {"error": "invalid_profile_id"})
        return
    transaction_id = handler.app.players.create_transaction(profile_id, payload)
    if not transaction_id:
        handler._json(400, {"error": "transaction_summary_required_or_profile_not_found"})
        return
    handler._log_admin_action(
        "create",
        "player_transaction",
        str(transaction_id),
        payload.get("team_code"),
        {"profile_id": profile_id, "summary": payload.get("summary")},
    )
    handler._json(201, {"transaction_id": transaction_id})
    return

def process_trade(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
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
            command_id=str(handler.headers.get("Idempotency-Key") or "").strip() or None,
            notify_discord=discord_notify_requested(payload),
            generate_image=discord_image_requested(payload),
            custom_image=(
                payload.get("discord_custom_image")
                if isinstance(payload.get("discord_custom_image"), dict)
                else None
            ),
        )
    except ValueError as err:
        handler._json(409, {"ok": False, "error": str(err) or "trade_processing_failed"})
        return
    audit = outcome.get("audit")
    if audit:
        handler._log_admin_action(
            "trade", "trade", None, None, audit.get("details"),
            before=audit.get("before"), after=audit.get("after"),
            team_codes=outcome.get("team_codes") or [],
        )
    delivered = handler.app.outbox_delivery.dispatch(outcome.get("outbox_event_ids"))
    if delivered and isinstance(outcome.get("result"), dict):
        outcome["result"]["delivered_events"] = delivered
    handler._json(int(outcome.get("status_code") or 200), outcome["response"])
    return

def create_move_adjustment(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    parts = parsed.path.split("/")
    if len(parts) < 5:
        handler._json(404, {"error": "not_found"})
        return
    code = parts[3]
    season_year = parse_int(payload.get("season_year"))
    target_remaining = parse_int(payload.get("target_remaining"))
    bucket = payload.get("bucket")
    note = str(payload.get("note") or "").strip() or None
    if season_year is None or season_year < PLAYER_CONTRACT_MIN_YEAR or season_year > PLAYER_CONTRACT_MAX_YEAR:
        handler._json(400, {"error": "invalid_season_year"})
        return
    if target_remaining is None or target_remaining < 0:
        handler._json(400, {"error": "invalid_target_remaining"})
        return
    if not handler._authorize("admin.team_moves.write", {"team_code": code}):
        return
    result = handler.app.trade_repository.adjust_team_move_remaining(code, season_year, bucket, target_remaining, note)
    if result:
        handler._log_admin_action("update", "team_move", code.upper(), code.upper(), result)
    handler._json(200 if result else 404, {"ok": bool(result), "result": result})
    return

def create_asset(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("admin.draft_asset.write", {"team_code": team_code}):
        return
    if str(payload.get("asset_type") or "").strip().lower() == "dead_cap":
        handler._json(400, {"error": "dead_cap_moved_to_dead_contracts"})
        return
    asset_id = handler.app.assets.create_asset(team_code, payload)
    if not asset_id:
        handler._json(404, {"error": "team_not_found"})
        return
    handler._log_admin_action("create", "asset", str(asset_id), str(team_code), {"asset_type": payload.get("asset_type")})
    handler._json(201, {"asset_id": asset_id})
    return

def create_frozen_draft_pick(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("admin.frozen_draft_pick.write", {"team_code": team_code}):
        return
    row = handler.app.assets.create_frozen_pick(team_code, payload)
    if not row:
        handler._json(400, {"error": "invalid_frozen_pick"})
        return
    handler._log_admin_action(
        "create",
        "frozen_draft_pick",
        str(row.get("id")),
        team_code,
        row,
    )
    handler._json(201, {"ok": True, "frozen_pick": row})
    return

def create_dead_contract(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = normalize_team_code(payload.get("team_code")) or ""
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("admin.dead_contract.write", {"team_code": team_code}):
        return
    dead_contract_id = handler.app.assets.create_dead_contract(team_code, payload)
    if not dead_contract_id:
        handler._json(404, {"error": "team_not_found"})
        return
    handler._log_admin_action(
        "create",
        "dead_contract",
        str(dead_contract_id),
        str(team_code),
        {"dead_type": payload.get("dead_type"), "label": payload.get("label")},
    )
    handler._json(201, {"dead_contract_id": dead_contract_id})
    return

def create_gm_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    team_code = str(payload.get("team_code") or "").strip().upper()
    if not team_code:
        handler._json(400, {"error": "team_code_required"})
        return
    if not handler._authorize("admin.gm_history.write", {"team_code": team_code}):
        return
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        handler._json(400, {"error": "entries_required"})
        return
    try:
        rows = handler.app.teams.replace_gm_history(team_code, raw_entries)
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_gm_history"})
        return
    if rows is None:
        handler._json(404, {"error": "team_not_found"})
        return
    handler._log_admin_action(
        "update",
        "gm_history",
        team_code,
        team_code,
        {"entries_count": len(rows)},
    )
    handler._json(200, {"ok": True, "gm_history": rows})
    return

def progress_settings_year(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf():
        return
    if not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.global.write"):
        return
    try:
        result = handler.app.season_rollover.progress_to_next_year()
    except ValueError as err:
        if str(err) in {"cannot_progress_beyond_2030", "cannot_progress_beyond_contract_window"}:
            handler._json(400, {"error": "cannot_progress_beyond_contract_window"})
            return
        raise
    merged = handler.app.settings_repository.get_all()
    handler._log_admin_action("update", "settings", None, None, {"progress_year": result})
    handler._json(
        200,
        {
            "ok": True,
            "result": result,
            "settings": public_settings_payload(merged),
        },
    )
    return


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


EARLY_POST_ROUTES = (exact_route("/api/auth/logout", logout),)
POST_REMAINING_ROUTES = (
    predicate_route("cartera-ruleout", _cartera_ruleout_path, update_cartera_ruleout),
    exact_route("/api/auth/login", login),
    exact_route("/api/trades/process/validate", validate_trade_process),
    exact_route("/api/gm/option-requests", request_gm_option),
    predicate_route("coadmin-vote-submit", _coadmin_vote_submit_path, submit_coadmin_vote),
    exact_route("/api/admin/coadmin-votes", create_coadmin_vote),
    exact_route("/api/admin/free-agent-offer-promises", create_offer_promise),
    exact_route("/api/offseason-exceptions/generate", generate_offseason_exceptions),
    exact_route("/api/free-agents/bulk", bulk_create_free_agents),
    exact_route("/api/free-agents", create_free_agent),
    exact_route("/api/draft-order", create_draft_order),
    predicate_route("free-agent-sign", _free_agent_sign_path, sign_free_agent),
    predicate_route("player-profile-merge", _profile_action_path("merge"), merge_player_profiles),
    predicate_route("player-salary-history-create", _profile_action_path("salary-history"), create_salary_history),
    predicate_route("player-transaction-create", _profile_action_path("transactions"), create_player_transaction),
    exact_route("/api/trades/process", process_trade),
    predicate_route("team-move-adjustment", _team_move_adjustment_path, create_move_adjustment),
    exact_route("/api/assets", create_asset),
    exact_route("/api/frozen-draft-picks", create_frozen_draft_pick),
    exact_route("/api/dead-contracts", create_dead_contract),
    exact_route("/api/gm-history", create_gm_history),
    exact_route("/api/settings/progress-year", progress_settings_year),
)
