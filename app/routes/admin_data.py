"""Administrative import, export, economy, and backup HTTP routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..import_export.spreadsheets import spreadsheet_rows_from_payload
    from ..routing import RouteResponse, bytes_response, error_response, exact_route, json_response
except ImportError:  # pragma: no cover
    from import_export.spreadsheets import spreadsheet_rows_from_payload
    from routing import RouteResponse, bytes_response, error_response, exact_route, json_response


def _require_admin_post(handler: Any) -> bool:
    return handler._require_csrf() and handler._require_sensitive_rate_limit("admin_post")


def _backup_entity_versions(backup: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    versions = {
        "backup_id": backup.get("id"),
        "backup_sha256": backup.get("sha256"),
    }
    versions.update(extra)
    return versions


def export_league(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> RouteResponse:
    workbook = handler.app.league_exports.export()
    filename = f"anba-league-export-{datetime.now(UTC).strftime('%Y%m%d')}.xlsx"
    return bytes_response(200, workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
    })


def preview_owner_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    csv_text = str(payload.get("csv_text") or "")
    if len(csv_text.encode("utf-8")) > 2_000_000:
        return error_response(413, "csv_too_large")
    method = handler.app.owner_imports.preview_owner_economy_csv if "economy-import" in parsed.path else handler.app.owner_imports.preview_owner_office_csv
    return json_response(200, method(csv_text))


def apply_owner_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    economy = "economy-import" in parsed.path
    entity = "owner_economy" if economy else "owner_office"
    try:
        backup = handler.app.maintenance.create_verified_backup(f"pre_{entity}_import")
    except Exception as err:
        return error_response(500, "pre_import_backup_failed", detail=str(err))
    try:
        method = handler.app.owner_imports.apply_owner_economy_import if economy else handler.app.owner_imports.apply_owner_office_import
        result = method(payload.get("records"))
    except ValueError as err:
        if str(err) == "records_required":
            return error_response(400, "records_required")
        if str(err) == "invalid_records":
            return error_response(400, "invalid_records", errors=getattr(err, "errors", []))
        raise
    entity_id = ",".join(str(value) for value in result.get("seasons", []))
    details = {
        "record_count": result.get("record_count"), "group_count": result.get("group_count"),
        "backup_id": backup.get("id"), "backup_sha256": backup.get("sha256"),
    }
    handler._log_admin_action(
        "import",
        entity,
        entity_id,
        None,
        details,
        command_id=f"{entity}:import:{backup.get('id')}",
        validation_result="valid",
        entity_versions=_backup_entity_versions(
            backup,
            seasons=result.get("seasons"),
            record_count=result.get("record_count"),
            group_count=result.get("group_count"),
        ),
    )
    result["backup"] = handler.app.maintenance.public_backup_metadata(backup)
    return json_response(200, result)


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
                        for key, group, sub in handler.app.free_agent_appeal.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS],
            "rankings": [],
        }
    return {
        "ok": False, "errors": [{"line": None, "message": label}], "records": [],
        "summary": {"record_count": 0, "changed_count": 0, "unchanged_count": 0, "new_agent_count": 0},
        "new_agents": [],
    }


def preview_free_agent_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    appeal = "appeal-import" in parsed.path
    if appeal and not handler.app.settings.free_agency_mode_enabled():
        return error_response(409, "free_agency_mode_required")
    try:
        rows = spreadsheet_rows_from_payload(
            file_name=str(payload.get("file_name") or ""),
            file_data_base64=str(payload.get("file_data_base64") or ""),
            csv_text=str(payload.get("csv_text") or ""),
        )
        method = handler.app.free_agent_appeal.preview if appeal else handler.app.free_agent_agent_import.preview
        result = method(rows)
    except ValueError as err:
        result = _spreadsheet_error_result(handler, str(err) or "invalid_file", appeal=appeal)
    return json_response(200, result)


def apply_free_agent_import(handler: Any, parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    payload = payload or {}
    if not _require_admin_post(handler) or not handler._authorize("admin.import.write"):
        return
    appeal = "appeal-import" in parsed.path
    if appeal and not handler.app.settings.free_agency_mode_enabled():
        return error_response(409, "free_agency_mode_required")
    entity = "free_agent_team_appeal" if appeal else "free_agent_agents"
    reason = "pre_free_agent_appeal_import" if appeal else "pre_free_agent_agent_import"
    try:
        backup = handler.app.maintenance.create_verified_backup(reason)
    except Exception as err:
        return error_response(500, "pre_import_backup_failed", detail=str(err))
    try:
        method = handler.app.free_agent_appeal.apply if appeal else handler.app.free_agent_agent_import.apply
        result = method(payload.get("records"))
    except ValueError as err:
        if str(err) in {"records_required", "invalid_records"}:
            return error_response(400, str(err))
        raise
    details = {"record_count": result.get("record_count"), "backup_id": backup.get("id"), "backup_sha256": backup.get("sha256")}
    if not appeal:
        details.update({"changed_count": result.get("changed_count"), "new_agents": result.get("new_agents")})
    entity_versions = _backup_entity_versions(
        backup,
        record_count=result.get("record_count"),
        changed_count=result.get("changed_count"),
        new_agent_count=len(result.get("new_agents") or []),
    )
    handler._log_admin_action(
        "import",
        entity,
        "bulk",
        None,
        details,
        command_id=f"{entity}:import:{backup.get('id')}",
        validation_result="valid",
        entity_versions=entity_versions,
    )
    result["backup"] = handler.app.maintenance.public_backup_metadata(backup)
    return json_response(200, result)


def download_backup(handler: Any, _parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    if not _require_admin_post(handler) or not handler._authorize("admin.backup.create"):
        return
    try:
        backup = handler.app.maintenance.create_verified_backup("manual_download")
        data = Path(str(backup["path"])).read_bytes()
    except ValueError as err:
        return error_response(500, "backup_failed", detail=str(err))
    except Exception:
        return error_response(500, "backup_failed")
    filename = f"anba-league-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.db"
    details = {
        "bytes": len(data), "backup_id": backup.get("id"), "backup_sha256": backup.get("sha256"),
    }
    handler._log_admin_action(
        "download",
        "backup",
        filename,
        None,
        details,
        command_id=f"backup:{backup.get('id')}:download",
        validation_result="valid",
        entity_versions=_backup_entity_versions(backup, bytes=len(data), filename=filename),
    )
    return bytes_response(200, data, "application/vnd.sqlite3", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


ADMIN_DATA_GET_ROUTES = (exact_route("/api/export/league.xlsx", export_league),)
ADMIN_DATA_POST_ROUTES = (
    exact_route("/api/admin/economy-import/preview", preview_owner_import, permission="admin.import.write", csrf=True, mutates_league_state=False),
    exact_route("/api/admin/economy-import/import", apply_owner_import, permission="admin.import.write", csrf=True, mutates_league_state=True),
    exact_route("/api/admin/owner-office-import/preview", preview_owner_import, permission="admin.import.write", csrf=True, mutates_league_state=False),
    exact_route("/api/admin/owner-office-import/import", apply_owner_import, permission="admin.import.write", csrf=True, mutates_league_state=True),
    exact_route("/api/admin/free-agent-agent-import/preview", preview_free_agent_import, permission="admin.import.write", csrf=True, mutates_league_state=False),
    exact_route("/api/admin/free-agent-agent-import/import", apply_free_agent_import, permission="admin.import.write", csrf=True, mutates_league_state=True),
    exact_route("/api/admin/free-agent-appeal-import/preview", preview_free_agent_import, permission="admin.import.write", csrf=True, mutates_league_state=False),
    exact_route("/api/admin/free-agent-appeal-import/import", apply_free_agent_import, permission="admin.import.write", csrf=True, mutates_league_state=True),
    exact_route("/api/admin/backup", download_backup, permission="admin.backup.create", csrf=True, mutates_league_state=False),
)
