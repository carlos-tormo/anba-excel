"""Administrative import, export, economy, and backup HTTP routes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..domain_rules import parse_bool
    from ..routing import exact_route
except ImportError:  # pragma: no cover
    from domain_rules import parse_bool
    from routing import exact_route


def _require_admin_post(handler: Any) -> bool:
    return handler._require_csrf() and handler._require_sensitive_rate_limit("admin_post")


def export_league(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    workbook = handler.db.export_league_workbook()
    filename = f"anba-league-export-{datetime.now(UTC).strftime('%Y%m%d')}.xlsx"
    handler._bytes_response(200, workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
    })


def preview_owner_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    csv_text = str(payload.get("csv_text") or "")
    if len(csv_text.encode("utf-8")) > 2_000_000:
        handler._json(413, {"error": "csv_too_large"})
        return
    method = handler.db.preview_owner_economy_csv if "economy-import" in parsed.path else handler.db.preview_owner_office_csv
    handler._json(200, method(csv_text))


def apply_owner_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    economy = "economy-import" in parsed.path
    entity = "owner_economy" if economy else "owner_office"
    try:
        backup = handler.db.create_verified_backup(f"pre_{entity}_import")
    except (OSError, sqlite3.Error, ValueError) as err:
        handler._json(500, {"error": "pre_import_backup_failed", "detail": str(err)})
        return
    try:
        method = handler.db.apply_owner_economy_import if economy else handler.db.apply_owner_office_import
        result = method(payload.get("records"))
    except ValueError as err:
        if str(err) == "records_required":
            handler._json(400, {"error": "records_required"})
            return
        if str(err) == "invalid_records":
            handler._json(400, {"error": "invalid_records", "errors": getattr(err, "errors", [])})
            return
        raise
    handler._log_admin_action("import", entity, ",".join(str(value) for value in result.get("seasons", [])), None, {
        "record_count": result.get("record_count"), "group_count": result.get("group_count"),
        "backup_id": backup.get("id"), "backup_sha256": backup.get("sha256"),
    })
    result["backup"] = handler._public_backup_metadata(backup)
    handler._json(200, result)


def _spreadsheet_error_result(handler: Any, message: str, *, appeal: bool) -> Dict[str, Any]:
    label = {
        "file_required": "Selecciona un archivo CSV o XLSX.",
        "file_too_large": "El archivo supera el tamaño máximo de 5 MB.",
        "invalid_file_data": "No se pudo leer el archivo.",
        "xlsx_first_sheet_missing": "No se pudo encontrar la primera hoja del XLSX.",
    }.get(message, "No se pudo procesar el archivo.")
    if appeal:
        return {
            "ok": False, "errors": [{"line": None, "message": label}], "records": [],
            "summary": {"record_count": 0, "team_count": 0},
            "columns": [{"key": key, "label": f"{group} · {sub}", "group": group, "sub_label": sub}
                        for key, group, sub in handler.db.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS],
            "rankings": [],
        }
    return {
        "ok": False, "errors": [{"line": None, "message": label}], "records": [],
        "summary": {"record_count": 0, "changed_count": 0, "unchanged_count": 0, "new_agent_count": 0},
        "new_agents": [],
    }


def preview_free_agent_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    appeal = "appeal-import" in parsed.path
    if appeal and not parse_bool(handler.db.get_settings().get("free_agency_mode")):
        handler._json(409, {"error": "free_agency_mode_required"})
        return
    try:
        rows = handler._spreadsheet_rows_from_payload(
            file_name=str(payload.get("file_name") or ""),
            file_data_base64=str(payload.get("file_data_base64") or ""),
            csv_text=str(payload.get("csv_text") or ""),
        )
        method = handler.db.preview_free_agent_team_appeal_import if appeal else handler.db.preview_free_agent_agent_import
        result = method(rows)
    except ValueError as err:
        result = _spreadsheet_error_result(handler, str(err) or "invalid_file", appeal=appeal)
    handler._json(200, result)


def apply_free_agent_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    appeal = "appeal-import" in parsed.path
    if appeal and not parse_bool(handler.db.get_settings().get("free_agency_mode")):
        handler._json(409, {"error": "free_agency_mode_required"})
        return
    entity = "free_agent_team_appeal" if appeal else "free_agent_agents"
    reason = "pre_free_agent_appeal_import" if appeal else "pre_free_agent_agent_import"
    try:
        backup = handler.db.create_verified_backup(reason)
    except (OSError, sqlite3.Error, ValueError) as err:
        handler._json(500, {"error": "pre_import_backup_failed", "detail": str(err)})
        return
    try:
        method = handler.db.apply_free_agent_team_appeal_import if appeal else handler.db.apply_free_agent_agent_import
        result = method(payload.get("records"))
    except ValueError as err:
        if str(err) in {"records_required", "invalid_records"}:
            handler._json(400, {"error": str(err)})
            return
        raise
    details = {"record_count": result.get("record_count"), "backup_id": backup.get("id"), "backup_sha256": backup.get("sha256")}
    if not appeal:
        details.update({"changed_count": result.get("changed_count"), "new_agents": result.get("new_agents")})
    handler._log_admin_action("import", entity, "bulk", None, details)
    result["backup"] = handler._public_backup_metadata(backup)
    handler._json(200, result)


def download_backup(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if not _require_admin_post(handler) or not handler._authorize("admin.backup.create"):
        return
    try:
        backup = handler.db.create_verified_backup("manual_download")
        data = Path(str(backup["path"])).read_bytes()
    except (OSError, sqlite3.Error):
        handler._json(500, {"error": "backup_failed"})
        return
    except ValueError as err:
        handler._json(500, {"error": "backup_failed", "detail": str(err)})
        return
    filename = f"anba-league-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.db"
    handler._log_admin_action("download", "backup", filename, None, {
        "bytes": len(data), "backup_id": backup.get("id"), "backup_sha256": backup.get("sha256"),
    })
    handler._bytes_response(200, data, "application/vnd.sqlite3", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


ADMIN_DATA_GET_ROUTES = (exact_route("/api/export/league.xlsx", export_league),)
ADMIN_DATA_POST_ROUTES = (
    exact_route("/api/admin/economy-import/preview", preview_owner_import),
    exact_route("/api/admin/economy-import/import", apply_owner_import),
    exact_route("/api/admin/owner-office-import/preview", preview_owner_import),
    exact_route("/api/admin/owner-office-import/import", apply_owner_import),
    exact_route("/api/admin/free-agent-agent-import/preview", preview_free_agent_import),
    exact_route("/api/admin/free-agent-agent-import/import", apply_free_agent_import),
    exact_route("/api/admin/free-agent-appeal-import/preview", preview_free_agent_import),
    exact_route("/api/admin/free-agent-appeal-import/import", apply_free_agent_import),
    exact_route("/api/admin/backup", download_backup),
)

