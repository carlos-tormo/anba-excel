"""Remaining page, authentication, catalog, tracker, and team GET routes."""

from __future__ import annotations

import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import ParseResult, parse_qs

try:
    from ..auth.policies import normalize_team_codes
    from ..domain_rules import parse_bool, parse_int
    from ..routing import error_response, exact_route, json_response, predicate_route, prefix_route, redirect_response
    from ..services.authentication import GoogleOAuthCompletionError
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_codes
    from domain_rules import parse_bool, parse_int
    from routing import error_response, exact_route, json_response, predicate_route, prefix_route, redirect_response
    from services.authentication import GoogleOAuthCompletionError


def get_home_page(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    handler._route_html("index.html")
    return

def get_news_page(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    handler._route_html("news.html")
    return

def get_login_page(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    handler._route_html("login.html")
    return

def get_admin_page(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if handler._is_admin():
        handler._route_html("admin.html")
        return
    if handler._is_authenticated():
        return redirect_response("/")
    handler._route_html("login.html")
    return

def start_google_oauth(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler.app.google_enabled:
        return redirect_response("/login?error=google_not_configured")
    if not handler._require_oauth_start_rate_limit():
        return
    state = secrets.token_urlsafe(24)
    handler._store_oauth_state(state)
    return redirect_response(
        handler.app.google_client.authorization_url(state),
        headers={"Set-Cookie": handler._oauth_state_cookie(state)},
    )

def complete_google_oauth(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    qs = parse_qs(parsed.query)
    if "error" in qs:
        return redirect_response(
            "/login?error=google_auth_denied",
            headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
        )
    code = (qs.get("code") or [""])[0]
    state = (qs.get("state") or [""])[0]
    if not code or not handler._oauth_state_ok(state):
        return redirect_response(
            "/login?error=google_state_invalid",
            headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
        )

    try:
        result = handler.app.google_oauth.complete(code)
    except GoogleOAuthCompletionError as err:
        return redirect_response(
            f"/login?error={str(err)}",
            headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
        )
    token, _ = handler._start_session(result["session"])
    cookie = handler._session_cookie(token)
    return redirect_response(
        handler._landing_path_for_session(result["role"], result["team_codes"]),
        headers={"Set-Cookie": [cookie, handler._clear_oauth_state_cookie()]},
    )

def get_auth_status(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    sess = handler._current_session()
    if not sess:
        return json_response(
            200,
            {
                "authenticated": False,
                "role": None,
                "user": None,
                "google_enabled": handler.app.google_enabled,
                "csrf_token": None,
                "team_code": None,
                "team_codes": [],
            },
        )
    return json_response(
        200,
        {
            "authenticated": True,
            "role": sess.get("role"),
            "user": {
                "email": sess.get("email"),
                "name": sess.get("name"),
                "provider": sess.get("provider"),
                "agent_name": sess.get("agent_name"),
            },
            "team_code": sess.get("team_code"),
            "team_codes": sess.get("team_codes") if isinstance(sess.get("team_codes"), list) else [],
            "agent_name": sess.get("agent_name"),
            "google_enabled": handler.app.google_enabled,
            "csrf_token": sess.get("csrf_token"),
        },
    )

def get_profile_salary_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("admin.player_profile.view"):
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        return error_response(404, "not_found")
    profile_id = parse_int(parts[2])
    if profile_id is None:
        return error_response(400, "invalid_profile_id")
    return json_response(200, {"salary_history": handler.app.players.list_salary_history(int(profile_id))})

def get_admin_players(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("admin.player_catalog.view"):
        return None
    try:
        started = time.perf_counter()
        players = handler.app.player_catalog.list_players(
            include_private=True,
            sync_generated=False,
            include_salary_history=False,
            collect_timings=True,
        )
        timings = handler.app.player_catalog.last_timings
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        timings_text = ",".join(
            f"{key}={value}"
            for key, value in timings.items()
            if isinstance(value, (int, float))
        )
        if total_ms >= 500:
            handler.log_message("Player catalog slow load %.2fms %s", total_ms, timings_text)
        return json_response(
            200,
            {"players": players, "meta": {"timings": timings}},
            headers={
                "X-Player-Catalog-Timing": timings_text[:3500],
            },
        )
    except Exception as err:
        handler.log_message("Player catalog load failed: %s", err)
        return error_response(500, "players_unavailable")

def get_players(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    try:
        started = time.perf_counter()
        players = handler.app.player_catalog.list_players(
            sync_generated=False,
            include_salary_history=False,
            collect_timings=True,
        )
        timings = handler.app.player_catalog.last_timings
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        timings_text = ",".join(
            f"{key}={value}"
            for key, value in timings.items()
            if isinstance(value, (int, float))
        )
        if total_ms >= 500:
            handler.log_message("Public player catalog slow load %.2fms %s", total_ms, timings_text)
        return json_response(
            200,
            {"players": players, "meta": {"timings": timings}},
            headers={
                "X-Player-Catalog-Timing": timings_text[:3500],
            },
        )
    except Exception as err:
        handler.log_message("Public player catalog load failed: %s", err)
        return error_response(500, "players_unavailable")

def get_tracker(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    try:
        started = time.perf_counter()
        qs = parse_qs(parsed.query)
        raw_season = (qs.get("season") or [""])[0].strip()
        season_year = parse_int(raw_season) if raw_season else None
        if raw_season and season_year is None:
            return error_response(400, "invalid_season_year")
        tracker = handler.app.tracker.list(season_year)
        timings = tracker.get("timings") if isinstance(tracker.get("timings"), dict) else {}
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        timings_text = ",".join(
            f"{key}={value}"
            for key, value in timings.items()
            if isinstance(value, (int, float))
        )
        if total_ms >= 500:
            handler.log_message("Tracker slow load %.2fms %s", total_ms, timings_text)
        if tracker.get("stale"):
            handler.log_message("Tracker served stale cache season=%s", tracker.get("season_year"))
        return json_response(
            200,
            {
                "tracker": tracker.get("rows") or [],
                "season_year": tracker.get("season_year"),
                "seasons": tracker.get("seasons") or [],
                "meta": {"timings": timings, "stale": bool(tracker.get("stale"))},
            },
            headers={"X-Tracker-Timing": timings_text[:3500]},
        )
    except Exception as err:
        handler.log_message("Tracker load failed: %s", err)
        return error_response(500, "tracker_unavailable")

def get_tracker_economy(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    qs = parse_qs(parsed.query)
    raw_season = (qs.get("season") or [""])[0].strip()
    season_year = parse_int(raw_season) if raw_season else None
    if raw_season and season_year is None:
        return error_response(400, "invalid_season_year")
    return json_response(200, handler.app.settings.list_team_economy(season_year))

def get_cartera(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.view"):
        return None
    qs = parse_qs(parsed.query)
    raw_amount = (qs.get("amount") or [""])[0].strip()
    raw_season = (qs.get("season") or [""])[0].strip()
    season_year = parse_int(raw_season) if raw_season else None
    if raw_season and season_year is None:
        return error_response(400, "invalid_season_year")
    try:
        return json_response(200, handler.app.cartera.list_capacity(raw_amount, season_year))
    except ValueError as exc:
        return error_response(400, str(exc))

def get_cartera_clients(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.view"):
        return None
    return json_response(200, handler.app.cartera.list_clients(handler._current_session() or {}))

def get_cartera_appeal(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.view"):
        return None
    return json_response(200, handler.app.free_agent_appeal.list())

def get_offseason_exception_preview(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("admin.offseason_exceptions.view"):
        return None
    qs = parse_qs(parsed.query)
    raw_season = (qs.get("season") or [""])[0].strip()
    season_year = parse_int(raw_season) if raw_season else None
    if raw_season and season_year is None:
        return error_response(400, "invalid_season_year")
    return json_response(200, handler.app.offseason_exceptions.preview(season_year))

def get_gm_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("admin.gm_history.view"):
        return None
    qs = parse_qs(parsed.query)
    team_code = str((qs.get("team") or [""])[0] or "").strip().upper() or None
    rows = handler.app.teams.list_gm_history(team_code)
    if rows is None:
        return error_response(404, "team_not_found")
    return json_response(200, {"gm_history": rows})

def get_admin_users(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("admin.users.view"):
        return None
    users = handler.app.users.list()
    for user in users:
        email = str(user.get("email") or "").strip().lower()
        team_codes = normalize_team_codes(user.get("team_codes"))
        is_co_admin = bool(parse_bool(user.get("is_co_admin")))
        user["is_co_admin"] = is_co_admin
        user["role"] = (
            "admin"
            if email in handler.admin_emails
            else ("co_admin" if is_co_admin else ("gm" if team_codes else "guest"))
        )
        user["team_code"] = team_codes[0] if team_codes else None
        user["team_codes"] = team_codes
    return json_response(200, {"users": users})

def get_admin_option_requests(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("admin.gm_option_request.view"):
        return None
    qs = parse_qs(parsed.query)
    status = (qs.get("status") or ["pending"])[0].strip().lower() or "pending"
    return json_response(200, {"requests": handler.app.gm_request_queries.list(status=status)})

def get_admin_coadmin_votes(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("admin.coadmin_vote.view"):
        return None
    return json_response(200, {"votes": handler.app.coadmin_votes.list_admin_coadmin_votes()})

def get_coadmin_votes(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._authorize("coadmin.vote.list"):
        return None
    session = handler._current_session() or {}
    return json_response(200, handler.app.coadmin_votes.list_coadmin_votes_for_session(session))

def get_team(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    code = parsed.path.split("/")[-1]
    qs = parse_qs(parsed.query)
    raw_season = (qs.get("season") or [""])[0].strip()
    move_season_year = parse_int(raw_season) if raw_season else None
    if raw_season and move_season_year is None:
        return error_response(400, "invalid_season_year")
    data = handler.app.team_detail.get(code, move_season_year=move_season_year)
    if not data:
        return error_response(404, "team_not_found")
    return json_response(200, data)


def _profile_salary_history_path(path: str) -> bool:
    return path.startswith("/api/player-profiles/") and path.endswith("/salary-history")


GET_REMAINING_ROUTES = (
    exact_route("/", get_home_page),
    exact_route("/news", get_news_page),
    exact_route("/login", get_login_page),
    exact_route("/admin", get_admin_page),
    exact_route("/api/auth/google/start", start_google_oauth),
    exact_route("/api/auth/google/callback", complete_google_oauth),
    exact_route("/api/auth/status", get_auth_status),
    predicate_route("profile-salary-history", _profile_salary_history_path, get_profile_salary_history),
    exact_route("/api/admin/players", get_admin_players),
    exact_route("/api/players", get_players),
    exact_route("/api/tracker", get_tracker),
    exact_route("/api/tracker/economy", get_tracker_economy),
    exact_route("/api/cartera", get_cartera),
    exact_route("/api/cartera/clients", get_cartera_clients),
    exact_route("/api/cartera/appeal", get_cartera_appeal),
    exact_route("/api/offseason-exceptions/preview", get_offseason_exception_preview),
    exact_route("/api/gm-history", get_gm_history),
    exact_route("/api/admin/users", get_admin_users),
    exact_route("/api/admin/gm-option-requests", get_admin_option_requests),
    exact_route("/api/admin/coadmin-votes", get_admin_coadmin_votes),
    exact_route("/api/coadmin-votes", get_coadmin_votes),
    prefix_route("/api/teams/", get_team),
)
