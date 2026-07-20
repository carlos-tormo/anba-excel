"""PATCH route functions extracted by workflow."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..domain_rules import parse_int
    from ..routing import exact_route, prefix_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain_rules import parse_int
    from routing import exact_route, prefix_route


def update_team_economy(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.tracker_economy.write"):
        return
    season_year = parse_int(str(payload.get("season_year") or payload.get("season") or ""))
    if season_year is None or season_year < 2000 or season_year > 2100:
        handler._json(400, {"error": "invalid_season_year"})
        return
    rows = payload.get("rows")
    if not isinstance(rows, list):
        handler._json(400, {"error": "rows_required"})
        return
    try:
        result = handler.app.settings_repository.upsert_team_economy(season_year, rows)
    except ValueError as err:
        message = str(err)
        if message.startswith("invalid_team_code:"):
            handler._json(400, {"error": "invalid_team_code", "team_code": message.split(":", 1)[1]})
            return
        if message == "invalid_season_year":
            handler._json(400, {"error": "invalid_season_year"})
            return
        raise
    handler._log_admin_action(
        "update",
        "team_economy",
        str(season_year),
        None,
        {"season_year": season_year, "row_count": len(rows)},
    )
    handler._json(200, {"ok": True, **result})


def update_coadmin_vote(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.coadmin_vote.write"):
        return
    vote_id = parse_int(parsed.path.split("/")[-1])
    if vote_id is None:
        handler._json(400, {"error": "invalid_vote_id"})
        return
    try:
        vote = handler.app.coadmin_votes.set_coadmin_vote_status(vote_id, payload.get("status"), handler._current_session() or {})
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_vote"})
        return
    if not vote:
        handler._json(404, {"error": "vote_not_found"})
        return
    handler._log_admin_action(
        "update",
        "coadmin_vote",
        str(vote_id),
        None,
        {"status": vote.get("status"), "title": vote.get("title")},
    )
    handler._json(200, {"ok": True, "vote": vote})


PATCH_ROUTES = (
    exact_route("/api/tracker/economy", update_team_economy),
    prefix_route("/api/admin/coadmin-votes/", update_coadmin_vote),
)
