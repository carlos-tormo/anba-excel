"""Owner-office and exit-interview HTTP route functions."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..auth.policies import normalize_team_code
    from ..routing import predicate_route
    from ..services.owner_office import OwnerExitInterviewError
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from routing import predicate_route
    from services.owner_office import OwnerExitInterviewError


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
    image = handler.app.owner_office.get_background_image(code)
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
    data = handler.app.owner_office.get(code, include_private=handler._is_admin())
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
        owner_office = handler.app.owner_office.update_background_image(code, file_bytes, mime_type)
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
        owner_office = handler.app.owner_office.update(code, payload)
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
    is_admin = handler._is_admin()
    if action == "reset" and not is_admin:
        handler._json(403, {"error": "admin_required"})
        return
    try:
        result = handler.app.owner_office.update_exit_interview(
            code,
            action,
            payload,
            handler._current_session() or {},
            include_private=is_admin,
        )
    except OwnerExitInterviewError as err:
        status = 404 if err.code in {"team_not_found", "interview_not_found"} else (
            409 if err.code in {"free_agency_mode_required", "interview_not_started"} else 400
        )
        handler._json(status, {"error": err.code, **err.details})
        return
    audit = result.get("audit")
    if audit:
        handler._log_admin_action(
            audit["action"], audit["entity"], audit["entity_id"],
            audit["team_code"], audit["details"],
        )
    handler._json(200, result["response"])


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
