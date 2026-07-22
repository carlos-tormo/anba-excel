"""Free-agency and waiver HTTP route functions."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult, parse_qs

try:
    from ..auth.policies import normalize_team_code
    from ..domain_rules import parse_int
    from ..routing import RouteResponse, error_response, exact_route, json_response, predicate_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from domain_rules import parse_int
    from routing import RouteResponse, error_response, exact_route, json_response, predicate_route


def _segments(path: str) -> list[str]:
    return path.strip("/").split("/")


def _free_agent_action(path: str, actions: set[str]) -> bool:
    parts = _segments(path)
    return len(parts) == 4 and parts[:2] == ["api", "free-agents"] and parts[3] in actions


def _request_action(path: str, collection: str, action: str) -> bool:
    parts = _segments(path)
    return len(parts) == 4 and parts[:2] == ["api", collection] and parts[3] == action


def get_cartera_promises(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    if not handler._authorize("coadmin.cartera.view"):
        return None
    query = parse_qs(parsed.query)
    status = (query.get("status") or ["all"])[0].strip().lower() or "all"
    try:
        return json_response(200, handler.app.free_agency.list_promises(handler._current_session() or {}, status=status))
    except ValueError as err:
        return error_response(400, str(err) or "invalid_status")
    except PermissionError as err:
        return error_response(403, str(err) or "admin_or_coadmin_required")


def get_free_agents(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    return json_response(200, handler.app.free_agency.list_free_agents(handler._current_session_team_codes()))


def request_bird_rights_renunciation(
    handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]
) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._validate_free_agency_route_payload(payload, "bird_renounce"):
        return
    player_id = parse_int(payload.get("player_id"))
    season_year = parse_int(payload.get("season_year"))
    rights_value = str(payload.get("rights_value") or "").strip().upper()
    if player_id is None:
        return error_response(400, "invalid_player_id")
    if season_year is None:
        return error_response(400, "invalid_renounce_season")
    player = handler.app.players.record(player_id)
    if not player:
        return error_response(404, "player_not_found")
    if not handler._authorize("gm.bird_rights_renounce.create", {"team_code": player.get("team_code")}):
        return
    try:
        result = handler.app.free_agency.request_bird_rights_renunciation(
            player_id,
            season_year,
            rights_value,
            handler._current_session() or {},
            player=player,
        )
    except ValueError as err:
        message = str(err)
        if message == "free_agency_mode_required":
            return error_response(409, "free_agency_mode_required")
        elif message == "invalid_renounce_season":
            return error_response(400, "invalid_renounce_season")
        elif message == "invalid_bird_rights_value":
            return error_response(400, "invalid_bird_rights_value")
        elif message == "bird_rights_mismatch":
            return error_response(409, "bird_rights_changed")
        else:
            raise
    return json_response(201, {"ok": True, "request": result["request"]})


def submit_free_agent_action(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("free_agent_action"):
        return
    parts = _segments(parsed.path)
    try:
        free_agent_id = int(parts[2])
    except ValueError:
        return error_response(400, "invalid_free_agent_id")
    action = parts[3]
    if not handler._validate_free_agency_route_payload(payload, action):
        return
    team_code = normalize_team_code(payload.get("team_code"))
    if not team_code:
        team_codes = handler._current_session_team_codes()
        if len(team_codes) == 1:
            team_code = team_codes[0]
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("gm.free_agent_offer.create", {"team_code": team_code}):
        return
    if action == "offer":
        try:
            submission = handler.app.free_agency.submit_offer(
                free_agent_id, team_code, payload, handler._current_session() or {}
            )
        except ValueError as err:
            message = str(err) or "invalid_free_agent_offer"
            return error_response(404 if message == "free_agent_not_found" else 400, message)
        free_agent = submission["free_agent"]
        team_code = submission["team_code"]
        offer_type = submission["offer_type"]
        normalized_payload = submission["payload"]
        request = submission["request"]
        discord_result = handler.app.free_agent_offer_notifications.deliver(
            free_agent,
            team_code,
            normalized_payload,
            offer_type,
        )
        sent = bool(discord_result.get("thread_sent") and discord_result.get("agent_dm_sent"))
        return json_response(
            201,
            {
                "ok": True,
                "request": request,
                "offer_type": offer_type,
                "discord_sent": sent,
                "discord_thread_sent": bool(discord_result.get("thread_sent")),
                "agent_dm_sent": bool(discord_result.get("agent_dm_sent")),
                "agent_discord_configured": bool(discord_result.get("agent_discord_configured")),
            },
        )
    try:
        negotiation = handler.app.free_agency.negotiate(
            free_agent_id, team_code, payload, handler._current_session() or {}
        )
    except ValueError as err:
        message = str(err) or "invalid_negotiation"
        return error_response(404 if message == "free_agent_not_found" else 400, message)
    handler._log_admin_action(
        "negotiate",
        "free_agent",
        str(free_agent_id),
        negotiation["team_code"],
        negotiation["audit"],
    )
    return json_response(201, {"ok": True, "interest": negotiation["interest"], "interest_recorded": True})


def set_free_agent_favorite(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._validate_free_agency_route_payload(payload, "favorite"):
        return
    parts = _segments(parsed.path)
    try:
        free_agent_id = int(parts[2])
    except ValueError:
        return error_response(400, "invalid_free_agent_id")
    action = parts[3]
    team_code = normalize_team_code(payload.get("team_code"))
    if not team_code:
        team_codes = handler._current_session_team_codes()
        if len(team_codes) == 1:
            team_code = team_codes[0]
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("gm.free_agent_favorite.update", {"team_code": team_code}):
        return
    try:
        result = handler.app.free_agency.set_favorite(
            free_agent_id,
            team_code,
            handler._current_session() or {},
            favorite=action == "favorite",
        )
    except ValueError as err:
        message = str(err) or "invalid_free_agent_favorite"
        return error_response(404 if message == "free_agent_not_found" else 400, message)
    response = {"ok": True, "is_favorite": result["is_favorite"]}
    if result["is_favorite"]:
        response["favorite"] = result.get("favorite")
    return json_response(200, response)


def cancel_free_agent_offer(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._validate_free_agency_route_payload(payload, "cancel"):
        return
    request_id = parse_int(_segments(parsed.path)[2])
    if request_id is None:
        return error_response(400, "invalid_request_id")
    request = handler.app.gm_request_queries.free_agent_offer(request_id)
    if not request:
        return error_response(404, "request_not_found")
    team_code = normalize_team_code(request.get("team_code"))
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("gm.free_agent_offer.cancel", {"team_code": team_code}):
        return
    try:
        result = handler.app.free_agency.cancel_offer(
            request_id, handler._current_session() or {}, request=request
        )
    except ValueError as err:
        message = str(err) or "invalid_request"
        status = 409 if message == "offer_not_pending" else 404 if message == "request_not_found" else 400
        return error_response(status, message)
    canceled = result["request"]
    handler._log_admin_action(
        "cancel",
        "gm_free_agent_offer_request",
        str(request_id),
        team_code,
        {"player_name": canceled.get("player_name"), "offer_type": canceled.get("offer_type")},
    )
    return json_response(200, {"ok": True, "request": canceled})


def submit_waiver_claim(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._require_csrf() or not handler._validate_free_agency_route_payload(payload, "waiver_claim"):
        return
    waiver_id = parse_int(_segments(parsed.path)[2])
    if waiver_id is None:
        return error_response(400, "invalid_waiver_id")
    team_code = normalize_team_code(payload.get("team_code"))
    if not team_code:
        team_codes = handler._current_session_team_codes()
        if len(team_codes) == 1:
            team_code = team_codes[0]
    if not team_code:
        return error_response(400, "team_code_required")
    if not handler._authorize("gm.waiver_claim.create", {"team_code": team_code}):
        return
    try:
        result = handler.app.waivers.submit_claim(
            waiver_id, team_code, payload, handler._current_session() or {}
        )
    except ValueError as err:
        message = str(err) or "not_eligible"
        status = 409 if message == "claim_already_submitted" else 404 if message == "waiver_not_found" else 400
        return error_response(status, message)
    return json_response(201, {"ok": True, "claim": result["claim"]})


def decide_waiver_claim(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._validate_free_agency_route_payload(payload, "admin_decision"):
        return
    request_id = parse_int(_segments(parsed.path)[3])
    if request_id is None:
        return error_response(400, "invalid_request_id")
    decision = str(payload.get("decision") or "").strip().lower()
    request = handler.app.waivers.claim_request(request_id)
    if not request:
        return error_response(404, "request_not_found")
    if str(request.get("status") or "").lower() != "pending":
        return json_response(409, {"error": "request_already_decided", "request": request})
    if not handler._authorize("admin.waiver_claim_request.decide", {"team_code": request.get("team_code")}):
        return
    try:
        result = handler.app.waivers.decide_claim(
            request_id,
            decision,
            handler._current_session() or {},
            note=str(payload.get("note") or "").strip() or None,
            request=request,
        )
    except ValueError as err:
        message = str(err)
        status = 409 if message in {"request_already_decided", "waiver_not_available"} else 404 if message == "request_not_found" else 400
        return error_response(status, message or "waiver_claim_decision_failed")
    handler._log_admin_action(
        decision.rstrip("d"),
        "waiver_claim_request",
        str(request_id),
        request.get("team_code"),
        {
            "waiver_player_id": result.get("waiver_player_id"),
            "player_name": result.get("player_name"),
            "from_team_code": result.get("from_team_code"),
        },
        before={"request": result.get("request_before")},
        after={"result": result.get("result")},
        command_id=result.get("command_id"),
        validation_result=result.get("validation_result"),
        entity_versions=result.get("entity_versions"),
    )
    return json_response(200, {"ok": True, "result": result["result"]})


def update_free_agent(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.free_agent.write"):
        return
    free_agent_id = parse_int(_segments(parsed.path)[2])
    if free_agent_id is None:
        return error_response(400, "invalid_free_agent_id")
    if not handler._validate_free_agent_route_update_payload(payload):
        return
    ok = handler.app.free_agency.update_free_agent(free_agent_id, payload)
    if ok:
        handler._log_admin_action("update", "free_agent", str(free_agent_id), None, {"fields": sorted(payload.keys())})
    return json_response(200 if ok else 404, {"ok": ok})


FREE_AGENCY_GET_ROUTES = (
    exact_route("/api/cartera/promises", get_cartera_promises),
    exact_route("/api/free-agents", get_free_agents),
)

FREE_AGENCY_POST_ROUTES = (
    exact_route(
        "/api/gm/bird-rights-renounce-requests",
        request_bird_rights_renunciation,
        permission="gm.bird_rights_renounce.create",
        csrf=True,
        mutates_league_state=True,
    ),
    predicate_route(
        "free-agent:offer-or-negotiate",
        lambda path: _free_agent_action(path, {"offer", "negotiate"}),
        submit_free_agent_action,
        permission="gm.free_agent_offer.create",
        csrf=True,
        mutates_league_state=True,
    ),
    predicate_route(
        "free-agent:favorite",
        lambda path: _free_agent_action(path, {"favorite", "unfavorite"}),
        set_free_agent_favorite,
        permission="gm.free_agent_favorite.update",
        csrf=True,
        mutates_league_state=True,
    ),
    predicate_route(
        "free-agent-offer:cancel",
        lambda path: _request_action(path, "gm-free-agent-offer-requests", "cancel"),
        cancel_free_agent_offer,
        permission="gm.free_agent_offer.cancel",
        csrf=True,
        mutates_league_state=True,
    ),
    predicate_route(
        "waiver:claim",
        lambda path: _request_action(path, "waivers", "claims"),
        submit_waiver_claim,
        permission="gm.waiver_claim.create",
        csrf=True,
        mutates_league_state=True,
    ),
)

FREE_AGENCY_PATCH_ROUTES = (
    predicate_route(
        "waiver-claim:decision",
        lambda path: len(_segments(path)) == 4 and _segments(path)[:3] == ["api", "admin", "waiver-claims"],
        decide_waiver_claim,
        permission="admin.waiver_claim_request.decide",
        csrf=True,
        mutates_league_state=True,
    ),
    predicate_route(
        "free-agent:update",
        lambda path: len(_segments(path)) == 3 and _segments(path)[:2] == ["api", "free-agents"],
        update_free_agent,
        permission="admin.free_agent.write",
        csrf=True,
        mutates_league_state=True,
    ),
)
