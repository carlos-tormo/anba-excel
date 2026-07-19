"""Remaining page, authentication, catalog, tracker, and team GET routes."""

from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, parse_qs

try:
    from ..auth.policies import normalize_team_codes
    from ..domain_rules import parse_bool, parse_int
    from ..routing import exact_route, predicate_route, prefix_route
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_codes
    from domain_rules import parse_bool, parse_int
    from routing import exact_route, predicate_route, prefix_route


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
        handler._redirect("/")
        return
    handler._route_html("login.html")
    return

def start_google_oauth(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._google_enabled():
        handler._redirect("/login?error=google_not_configured")
        return
    if not handler._require_oauth_start_rate_limit():
        return
    state = secrets.token_urlsafe(24)
    handler._store_oauth_state(state)
    handler._redirect(
        handler._google_oauth_client().authorization_url(state),
        headers={"Set-Cookie": handler._oauth_state_cookie(state)},
    )
    return

def complete_google_oauth(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    qs = parse_qs(parsed.query)
    if "error" in qs:
        handler._redirect(
            "/login?error=google_auth_denied",
            headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
        )
        return
    code = (qs.get("code") or [""])[0]
    state = (qs.get("state") or [""])[0]
    if not code or not handler._oauth_state_ok(state):
        handler._redirect(
            "/login?error=google_state_invalid",
            headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
        )
        return

    try:
        google_oauth = handler._google_oauth_client()
        token_data = google_oauth.exchange_code(code)
        access_token = token_data.get("access_token")
        if not access_token:
            handler._redirect(
                "/login?error=google_token_failed",
                headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
            )
            return
        userinfo = google_oauth.fetch_userinfo(access_token)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        handler._redirect(
            "/login?error=google_exchange_failed",
            headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
        )
        return

    google_sub = str(userinfo.get("sub") or "").strip()
    email = str(userinfo.get("email") or "").strip().lower()
    name = str(userinfo.get("name") or "").strip() or None
    picture = str(userinfo.get("picture") or "").strip() or None

    if not google_sub or not email:
        handler._redirect(
            "/login?error=google_profile_invalid",
            headers={"Set-Cookie": handler._clear_oauth_state_cookie()},
        )
        return

    user = handler.db.upsert_google_user(google_sub, email, name, picture)
    role, team_codes = handler._google_role_for_email(email)

    token, _ = handler._start_session(
        {
            "provider": "google",
            "user_id": user["id"],
            "email": email,
            "name": user.get("display_name") or email,
            "role": role,
            "team_codes": team_codes,
            "team_code": team_codes[0] if team_codes else None,
            "logged_in_at": now_iso(),
        }
    )
    cookie = handler._session_cookie(token)
    handler._redirect(
        handler._landing_path_for_session(role, team_codes),
        headers={"Set-Cookie": [cookie, handler._clear_oauth_state_cookie()]},
    )
    return

def get_auth_status(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    sess = handler._current_session()
    if not sess:
        handler._json(
            200,
            {
                "authenticated": False,
                "role": None,
                "user": None,
                "google_enabled": handler._google_enabled(),
                "csrf_token": None,
                "team_code": None,
                "team_codes": [],
            },
        )
        return
    handler._json(
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
            "google_enabled": handler._google_enabled(),
            "csrf_token": sess.get("csrf_token"),
        },
    )
    return

def get_profile_salary_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.player_profile.view"):
        return
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4:
        handler._json(404, {"error": "not_found"})
        return
    profile_id = parse_int(parts[2])
    if profile_id is None:
        handler._json(400, {"error": "invalid_profile_id"})
        return
    handler._json(200, {"salary_history": handler.db.list_player_salary_history(int(profile_id))})
    return

def get_admin_players(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.player_catalog.view"):
        return
    try:
        started = time.perf_counter()
        players = handler.db.list_players(
            include_private=True,
            sync_generated=False,
            include_salary_history=False,
            collect_timings=True,
        )
        timings = getattr(handler.db, "_last_list_players_timings", {}) or {}
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        timings_text = ",".join(
            f"{key}={value}"
            for key, value in timings.items()
            if isinstance(value, (int, float))
        )
        if total_ms >= 500:
            handler.log_message("Player catalog slow load %.2fms %s", total_ms, timings_text)
        handler._json(
            200,
            {"players": players, "meta": {"timings": timings}},
            headers={
                "X-Player-Catalog-Timing": timings_text[:3500],
            },
        )
    except Exception as err:
        handler.log_message("Player catalog load failed: %s", err)
        handler._json(500, {"error": "players_unavailable"})
    return

def get_players(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        started = time.perf_counter()
        players = handler.db.list_players(
            sync_generated=False,
            include_salary_history=False,
            collect_timings=True,
        )
        timings = getattr(handler.db, "_last_list_players_timings", {}) or {}
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        timings_text = ",".join(
            f"{key}={value}"
            for key, value in timings.items()
            if isinstance(value, (int, float))
        )
        if total_ms >= 500:
            handler.log_message("Public player catalog slow load %.2fms %s", total_ms, timings_text)
        handler._json(
            200,
            {"players": players, "meta": {"timings": timings}},
            headers={
                "X-Player-Catalog-Timing": timings_text[:3500],
            },
        )
    except Exception as err:
        handler.log_message("Public player catalog load failed: %s", err)
        handler._json(500, {"error": "players_unavailable"})
    return

def get_tracker(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    try:
        started = time.perf_counter()
        qs = parse_qs(parsed.query)
        raw_season = (qs.get("season") or [""])[0].strip()
        season_year = parse_int(raw_season) if raw_season else None
        if raw_season and season_year is None:
            handler._json(400, {"error": "invalid_season_year"})
            return
        tracker = handler.db.list_tracker(season_year)
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
        handler._json(
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
        handler._json(500, {"error": "tracker_unavailable"})
    return

def get_tracker_economy(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    qs = parse_qs(parsed.query)
    raw_season = (qs.get("season") or [""])[0].strip()
    season_year = parse_int(raw_season) if raw_season else None
    if raw_season and season_year is None:
        handler._json(400, {"error": "invalid_season_year"})
        return
    handler._json(200, handler.db.list_team_economy(season_year))
    return

def get_cartera(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.view"):
        return
    qs = parse_qs(parsed.query)
    raw_amount = (qs.get("amount") or [""])[0].strip()
    raw_season = (qs.get("season") or [""])[0].strip()
    season_year = parse_int(raw_season) if raw_season else None
    if raw_season and season_year is None:
        handler._json(400, {"error": "invalid_season_year"})
        return
    try:
        handler._json(200, handler.db.list_cartera(raw_amount, season_year))
    except ValueError as exc:
        handler._json(400, {"error": str(exc)})
    return

def get_cartera_clients(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.view"):
        return
    handler._json(200, handler.db.list_cartera_clients_for_session(handler._current_session() or {}))
    return

def get_cartera_appeal(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("coadmin.cartera.view"):
        return
    handler._json(200, handler.db.list_free_agent_team_appeal())
    return

def get_offseason_exception_preview(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.offseason_exceptions.view"):
        return
    qs = parse_qs(parsed.query)
    raw_season = (qs.get("season") or [""])[0].strip()
    season_year = parse_int(raw_season) if raw_season else None
    if raw_season and season_year is None:
        handler._json(400, {"error": "invalid_season_year"})
        return
    handler._json(200, handler.db.list_offseason_exception_preview(season_year))
    return

def get_gm_history(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.gm_history.view"):
        return
    qs = parse_qs(parsed.query)
    team_code = str((qs.get("team") or [""])[0] or "").strip().upper() or None
    rows = handler.db.list_gm_history(team_code)
    if rows is None:
        handler._json(404, {"error": "team_not_found"})
        return
    handler._json(200, {"gm_history": rows})
    return

def get_admin_users(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.users.view"):
        return
    users = handler.db.list_users()
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
    handler._json(200, {"users": users})
    return

def get_admin_option_requests(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.gm_option_request.view"):
        return
    qs = parse_qs(parsed.query)
    status = (qs.get("status") or ["pending"])[0].strip().lower() or "pending"
    handler._json(200, {"requests": handler.db.list_gm_option_requests(status=status)})
    return

def get_admin_coadmin_votes(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("admin.coadmin_vote.view"):
        return
    handler._json(200, {"votes": handler.db.list_admin_coadmin_votes()})
    return

def get_coadmin_votes(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._authorize("coadmin.vote.list"):
        return
    session = handler._current_session() or {}
    handler._json(200, handler.db.list_coadmin_votes_for_session(session))
    return

def get_team(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    code = parsed.path.split("/")[-1]
    qs = parse_qs(parsed.query)
    raw_season = (qs.get("season") or [""])[0].strip()
    move_season_year = parse_int(raw_season) if raw_season else None
    if raw_season and move_season_year is None:
        handler._json(400, {"error": "invalid_season_year"})
        return
    data = handler.db.get_team(code, move_season_year=move_season_year)
    if not data:
        handler._json(404, {"error": "team_not_found"})
        return
    handler._json(200, data)
    return


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
