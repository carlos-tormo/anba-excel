"""Owner-office and exit-interview HTTP route functions."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..auth.policies import normalize_team_code
    from ..domain_rules import parse_bool, parse_int
    from ..routing import predicate_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from domain_rules import parse_bool, parse_int
    from routing import predicate_route


OWNER_BACKGROUND_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _team_workflow_path(path: str, suffix: str) -> bool:
    parts = path.strip("/").split("/")
    suffix_parts = suffix.strip("/").split("/")
    return len(parts) == 3 + len(suffix_parts) and parts[:2] == ["api", "teams"] and parts[3:] == suffix_parts


def get_owner_background_image(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    code = normalize_team_code(parsed.path.strip("/").split("/")[2])
    if not code:
        handler._json(400, {"error": "invalid_team"})
        return
    image = handler.db.get_owner_background_image(code)
    if not image:
        handler._json(404, {"error": "not_found"})
        return
    image_bytes, mime_type = image
    extension = OWNER_BACKGROUND_EXTENSIONS.get(mime_type, "img")
    handler._bytes_response(
        200,
        image_bytes,
        mime_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": f'inline; filename="owner-office-{code}.{extension}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def get_owner_office(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    code = parsed.path.strip("/").split("/")[2]
    if not handler._authorize("owner_office.view", {"team_code": code}):
        return
    data = handler.db.get_team_owner_office(code, include_private=handler._is_admin())
    if not data:
        handler._json(404, {"error": "team_not_found"})
        return
    handler._json(200, {"owner_office": data})


def upload_owner_background(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_upload"):
        return
    code = normalize_team_code(parsed.path.strip("/").split("/")[2])
    if not code:
        handler._json(400, {"error": "invalid_team"})
        return
    if not handler._authorize("admin.team.write", {"team_code": code}):
        return
    try:
        file_bytes, _ext, mime_type = handler._read_multipart_image_upload("background")
        owner_office = handler.db.update_owner_background_image(code, file_bytes, mime_type)
    except ValueError as err:
        error = str(err) or "invalid_upload"
        handler._json(413 if error == "upload_too_large" else 400, {"error": error})
        return
    except sqlite3.Error:
        handler._json(500, {"error": "upload_save_failed"})
        return
    if not owner_office:
        handler._json(404, {"error": "team_not_found"})
        return
    background_url = str((owner_office.get("owner_profile") or {}).get("owner_office_background_url") or "")
    handler._log_admin_action(
        "upload",
        "owner_office_background",
        code,
        code,
        {"url": background_url, "bytes": len(file_bytes), "mime_type": mime_type},
    )
    handler._json(200, {"ok": True, "background_url": background_url, "owner_office": owner_office})


def update_owner_office(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    code = parsed.path.strip("/").split("/")[2]
    if not handler._authorize("admin.team.write", {"team_code": code}):
        return
    try:
        owner_office = handler.db.update_team_owner_office(code, payload)
    except ValueError as err:
        if str(err) == "invalid_season_year":
            handler._json(400, {"error": "invalid_season_year"})
            return
        raise
    if not owner_office:
        handler._json(404, {"error": "team_not_found"})
        return
    handler._log_admin_action(
        "update",
        "team_owner_office",
        f"{code.upper()}:{payload.get('season_year')}",
        code.upper(),
        {"season_year": payload.get("season_year")},
    )
    handler._json(200, {"ok": True, "owner_office": owner_office})


def update_owner_exit_interview(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    parts = parsed.path.strip("/").split("/")
    code, action = parts[2], parts[-1]
    if not handler._require_csrf():
        return
    if not handler._authorize("owner_exit_interview.update", {"team_code": code}):
        return
    settings = handler.db.get_settings()
    current_year = parse_int(settings.get("current_year")) or 2025
    season_year = parse_int(payload.get("season_year")) or current_year
    if season_year != current_year:
        handler._json(400, {"error": "invalid_exit_interview_season", "season_year": current_year})
        return
    if action == "reset":
        if not handler._is_admin():
            handler._json(403, {"error": "admin_required"})
            return
        if not handler.db.reset_owner_exit_interview(code, season_year):
            handler._json(404, {"error": "team_not_found"})
            return
        refreshed = handler.db.get_team_owner_office(code, include_private=True)
        handler._log_admin_action(
            "reset",
            "owner_exit_interview",
            f"{code.upper()}:{season_year}",
            code.upper(),
            {"season_year": season_year},
        )
        handler._json(200, {"ok": True, "owner_office": refreshed})
        return
    if not parse_bool(settings.get("free_agency_mode")):
        handler._json(409, {"error": "free_agency_mode_required"})
        return
    owner_office = handler.db.get_team_owner_office(code, include_private=True)
    if not owner_office:
        handler._json(404, {"error": "team_not_found"})
        return
    session = handler._current_session() or {}
    if action == "start":
        existing = handler.db.get_owner_exit_interview(code, season_year)
        owner_message = str(existing.get("owner_message") or "").strip() if existing else ""
        if not owner_message:
            owner_message = handler._owner_interview_service().opening_message(owner_office, season_year, session=session)
        interview = handler.db.start_owner_exit_interview(code, season_year, session, owner_message)
        if not interview:
            handler._json(404, {"error": "team_not_found"})
            return
        refreshed = handler.db.get_team_owner_office(code, include_private=handler._is_admin())
        handler._json(200, {"ok": True, "interview": interview, "owner_office": refreshed})
        return

    gm_response = str(payload.get("gm_response") or "").strip()
    if not gm_response:
        handler._json(400, {"error": "gm_response_required"})
        return
    if len(gm_response) > 4000:
        handler._json(400, {"error": "gm_response_too_long"})
        return
    existing = handler.db.get_owner_exit_interview(code, season_year)
    if not existing or not str(existing.get("owner_message") or "").strip():
        handler._json(409, {"error": "interview_not_started"})
        return
    if str(existing.get("status") or "").lower() == "completed":
        handler._json(200, {"ok": True, "interview": existing})
        return
    final_message, conclusion_message, trust_delta = handler._owner_interview_service().final_reply(
        owner_office,
        season_year,
        str(existing.get("owner_message") or ""),
        gm_response,
        session=session,
    )
    interview = handler.db.complete_owner_exit_interview(
        code,
        season_year,
        session,
        gm_response,
        final_message,
        conclusion_message,
        trust_delta,
    )
    if not interview:
        handler._json(404, {"error": "interview_not_found"})
        return
    refreshed = handler.db.get_team_owner_office(code, include_private=handler._is_admin())
    handler._json(200, {"ok": True, "interview": interview, "owner_office": refreshed})


def _owner_office_path(path: str) -> bool:
    return _team_workflow_path(path, "owner-office")


def _owner_background_image_path(path: str) -> bool:
    return _team_workflow_path(path, "owner-office/background-image")


def _owner_background_upload_path(path: str) -> bool:
    return _team_workflow_path(path, "owner-office/background")


def _owner_exit_interview_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return (
        len(parts) == 5
        and parts[:2] == ["api", "teams"]
        and parts[3] == "owner-exit-interview"
        and parts[4] in {"start", "reply", "reset"}
    )


OWNER_OFFICE_GET_ROUTES = (
    predicate_route("owner-background-image", _owner_background_image_path, get_owner_background_image),
    predicate_route("owner-office", _owner_office_path, get_owner_office),
)
OWNER_OFFICE_MULTIPART_POST_ROUTES = (
    predicate_route("owner-background-upload", _owner_background_upload_path, upload_owner_background),
)
OWNER_OFFICE_POST_ROUTES = (
    predicate_route("owner-exit-interview", _owner_exit_interview_path, update_owner_exit_interview),
)
OWNER_OFFICE_PATCH_ROUTES = (
    predicate_route("owner-office", _owner_office_path, update_owner_office),
)
