"""PATCH route functions extracted by workflow."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..domain_rules import parse_int
    from ..routing import RouteResponse, error_response, exact_route, json_response, prefix_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain_rules import parse_int
    from routing import RouteResponse, error_response, exact_route, json_response, prefix_route


def update_team_economy(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.tracker_economy.write"):
        return
    season_year = parse_int(str(payload.get("season_year") or payload.get("season") or ""))
    if season_year is None or season_year < 2000 or season_year > 2100:
        return error_response(400, "invalid_season_year")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return error_response(400, "rows_required")
    try:
        result = handler.app.settings.upsert_team_economy(season_year, rows)
    except ValueError as err:
        message = str(err)
        if message.startswith("invalid_team_code:"):
            return json_response(400, {"error": "invalid_team_code", "team_code": message.split(":", 1)[1]})
        if message == "invalid_season_year":
            return error_response(400, "invalid_season_year")
        raise
    handler._log_admin_action(
        "update",
        "team_economy",
        str(season_year),
        None,
        {"season_year": season_year, "row_count": len(rows)},
    )
    return json_response(200, {"ok": True, **result})


def update_coadmin_vote(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.coadmin_vote.write"):
        return
    vote_id = parse_int(parsed.path.split("/")[-1])
    if vote_id is None:
        return error_response(400, "invalid_vote_id")
    try:
        vote = handler.app.coadmin_votes.set_coadmin_vote_status(vote_id, payload.get("status"), handler._current_session() or {})
    except ValueError as err:
        return error_response(400, str(err) or "invalid_vote")
    if not vote:
        return error_response(404, "vote_not_found")
    handler._log_admin_action(
        "update",
        "coadmin_vote",
        str(vote_id),
        None,
        {"status": vote.get("status"), "title": vote.get("title")},
        command_id=f"coadmin-vote:{vote_id}:status-{vote.get('status') or 'unknown'}",
        validation_result="valid",
        entity_versions={
            "vote_id": vote_id,
            "status": vote.get("status"),
            "title": vote.get("title"),
            "updated_at": vote.get("updated_at"),
        },
    )
    return json_response(200, {"ok": True, "vote": vote})

def update_gm_attractiveness_ranking_entry(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not handler._authorize("admin.coadmin_vote.write"):
        return
    gm_entity_id = parse_int(parsed.path.split("/")[-1])
    if gm_entity_id is None:
        return error_response(400, "invalid_gm_entity_id")
    try:
        ranking = handler.app.gm_attractiveness.update_active_entry(
            gm_entity_id,
            payload,
            handler._current_session() or {},
        )
    except ValueError as err:
        message = str(err) or "invalid_ranking_entry"
        return error_response(404 if message == "ranking_entry_not_found" else 400, message)
    handler._log_admin_action(
        "update",
        "gm_attractiveness_ranking_entry",
        str(gm_entity_id),
        None,
        {"fields": sorted(payload.keys())},
        command_id=f"gm-attractiveness-ranking:{gm_entity_id}:manual-update",
        validation_result="valid",
        entity_versions={
            "gm_entity_id": gm_entity_id,
            "ranking_id": ranking.get("id"),
            "updated_at": ranking.get("updated_at"),
        },
    )
    return json_response(200, {"ok": True, "ranking": ranking})


PATCH_ROUTES = (
    exact_route("/api/tracker/economy", update_team_economy, permission="admin.tracker_economy.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/admin/coadmin-votes/", update_coadmin_vote, permission="admin.coadmin_vote.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/admin/gm-attractiveness-ranking/entries/", update_gm_attractiveness_ranking_entry, permission="admin.coadmin_vote.write", csrf=True, mutates_league_state=True),
)
