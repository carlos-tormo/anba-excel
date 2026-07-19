"""Administrative owner economy and owner-office import pipelines."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Callable, Dict, List


class OwnerAdminImportService:
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        economy_schema_payload: Callable[..., Dict[str, Any]],
        economy_header_value: Callable[..., str],
        normalize_economy_records: Callable[..., Any],
        group_economy_records: Callable[..., List[Dict[str, Any]]],
        rows_for_json: Callable[..., List[Dict[str, Any]]],
        format_value: Callable[[Any], str],
        rows_from_json: Callable[..., List[Dict[str, Any]]],
        normalize_rows: Callable[..., List[Dict[str, Any]]],
        breakdown_total: Callable[..., Any],
        office_header_value: Callable[..., str],
        normalize_office_records: Callable[..., Any],
        group_office_records: Callable[..., List[Dict[str, Any]]],
        performance_from_json: Callable[..., List[Dict[str, Any]]],
        normalize_performance: Callable[..., List[Dict[str, Any]]],
        objective_options: List[str],
    ) -> None:
        self._db = db
        self._now = now
        self._economy_schema_payload = economy_schema_payload
        self._economy_header_value = economy_header_value
        self._normalize_economy_records = normalize_economy_records
        self._group_economy_records = group_economy_records
        self._rows_for_json = rows_for_json
        self._format_value = format_value
        self._rows_from_json = rows_from_json
        self._normalize_rows = normalize_rows
        self._breakdown_total = breakdown_total
        self._office_header_value = office_header_value
        self._normalize_office_records = normalize_office_records
        self._group_office_records = group_office_records
        self._performance_from_json = performance_from_json
        self._normalize_performance = normalize_performance
        self._objective_options = list(objective_options)

    def preview_owner_economy_csv(self, csv_text: str) -> Dict[str, Any]:
            text = str(csv_text or "").lstrip("\ufeff")
            if not text.strip():
                return {"ok": False, "errors": [{"line": None, "message": "El CSV está vacío."}], "records": [], "summary": [], "schema": self._economy_schema_payload()}
            with self._db.connect() as conn:
                teams_by_code = {
                    str(row["code"]).upper(): {"id": int(row["id"]), "name": str(row["name"])}
                    for row in conn.execute("SELECT id, code, name FROM teams").fetchall()
                }
                economy_by_team = {
                    (int(row["season_year"]), str(row["code"]).upper()): {
                        "revenue": float(row["revenue"] or 0),
                        "expenses": float(row["expenses"] or 0),
                        "balance": float(row["balance"] or 0),
                    }
                    for row in conn.execute(
                        """
                        SELECT e.season_year, t.code, e.revenue, e.expenses, e.balance
                        FROM team_economy e
                        JOIN teams t ON t.id = e.team_id
                        """
                    ).fetchall()
                }
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            try:
                reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            except csv.Error as err:
                return {"ok": False, "errors": [{"line": None, "message": f"No se pudo leer el CSV: {err}"}], "records": [], "summary": [], "schema": self._economy_schema_payload()}
            if not reader.fieldnames:
                return {"ok": False, "errors": [{"line": None, "message": "El CSV no tiene cabeceras."}], "records": [], "summary": [], "schema": self._economy_schema_payload()}

            raw_records: List[Dict[str, Any]] = []
            errors: List[Dict[str, Any]] = []
            aliases = {
                "season": ["season", "season_year", "temporada", "year", "año", "ano"],
                "team": ["team", "team_code", "equipo", "codigo", "código", "franquicia"],
                "section": ["section", "seccion", "sección", "tipo", "apartado"],
                "key": ["key", "clave", "campo", "concept_key", "concepto_key", "id"],
                "label": ["label", "concept", "concepto", "partida", "row", "rubro"],
                "category": ["category", "categoria", "categoría", "grupo", "bloque"],
                "value": ["value", "amount", "valor", "importe", "total"],
            }
            try:
                for row in reader:
                    if not any(str(value or "").strip() for value in row.values()):
                        continue
                    raw_records.append(
                        {
                            "line": reader.line_num,
                            "season": self._economy_header_value(row, aliases["season"]),
                            "team": self._economy_header_value(row, aliases["team"]),
                            "section": self._economy_header_value(row, aliases["section"]),
                            "key": self._economy_header_value(row, aliases["key"]),
                            "label": self._economy_header_value(row, aliases["label"]),
                            "category": self._economy_header_value(row, aliases["category"]),
                            "value": self._economy_header_value(row, aliases["value"]),
                        }
                    )
            except csv.Error as err:
                errors.append({"line": None, "message": f"No se pudo leer el CSV: {err}"})
            records, record_errors = self._normalize_economy_records(raw_records, teams_by_code)
            errors.extend(record_errors)
            if not records and not errors:
                errors.append({"line": None, "message": "No se encontraron filas importables."})
            return {
                "ok": not errors,
                "errors": errors,
                "records": records,
                "summary": self._group_economy_records(records, economy_by_team),
                "schema": self._economy_schema_payload(),
            }

    def apply_owner_economy_import(self, records_payload: Any) -> Dict[str, Any]:
            if not isinstance(records_payload, list):
                raise ValueError("records_required")
            with self._db.connect() as conn:
                teams_by_code = {
                    str(row["code"]).upper(): {"id": int(row["id"]), "name": str(row["name"])}
                    for row in conn.execute("SELECT id, code, name FROM teams").fetchall()
                }
                records, errors = self._normalize_economy_records(records_payload, teams_by_code)
                if errors:
                    err = ValueError("invalid_records")
                    setattr(err, "errors", errors)
                    raise err
                grouped_values: Dict[tuple[int, str], Dict[str, Dict[str, float]]] = {}
                for record in records:
                    group_key = (int(record["season_year"]), str(record["team_code"]))
                    grouped_values.setdefault(group_key, {"income": {}, "expenses": {}, "economy": {}})
                    section = str(record["section"])
                    row_key = str(record["key"])
                    raw_value = record.get("value")
                    if raw_value is None or str(raw_value).strip() == "":
                        if row_key not in grouped_values[group_key][section]:
                            grouped_values[group_key][section][row_key] = None
                    else:
                        existing = grouped_values[group_key][section].get(row_key)
                        grouped_values[group_key][section][row_key] = float(existing or 0) + float(raw_value or 0)

                timestamp = self._now()
                applied_economy_by_team: Dict[tuple[int, str], Dict[str, float]] = {}
                for (season_year, team_code), sections in grouped_values.items():
                    team = teams_by_code[team_code]
                    team_id = int(team["id"])
                    existing_economy = conn.execute(
                        """
                        SELECT COALESCE(revenue, 0) AS revenue,
                               COALESCE(expenses, 0) AS expenses
                        FROM team_economy
                        WHERE team_id = ? AND season_year = ?
                        """,
                        (team_id, season_year),
                    ).fetchone()
                    existing_owner = conn.execute(
                        """
                        SELECT income_json, expenses_json
                        FROM team_owner_office
                        WHERE team_id = ? AND season_year = ?
                        """,
                        (team_id, season_year),
                    ).fetchone()
                    has_income = bool(sections["income"])
                    has_expenses = bool(sections["expenses"])
                    economy_values = sections.get("economy") or {}
                    has_economy = bool(economy_values)
                    revenue = (
                        float(economy_values["revenue"])
                        if economy_values.get("revenue") not in (None, "")
                        else (float(existing_economy["revenue"] or 0) if existing_economy else 0.0)
                    )
                    expenses = (
                        float(economy_values["expenses"])
                        if economy_values.get("expenses") not in (None, "")
                        else (float(existing_economy["expenses"] or 0) if existing_economy else 0.0)
                    )
                    balance = (
                        float(economy_values["balance"])
                        if economy_values.get("balance") not in (None, "")
                        else revenue + expenses
                    )
                    income_rows = (
                        self._rows_for_json("income", sections["income"])
                        if has_income
                        else (self._rows_from_json(existing_owner["income_json"], "income") if existing_owner else [])
                    )
                    expenses_rows = (
                        self._rows_for_json("expenses", sections["expenses"])
                        if has_expenses
                        else (self._rows_from_json(existing_owner["expenses_json"], "expenses") if existing_owner else [])
                    )
                    income_total = self._breakdown_total("income", income_rows) if has_income else None
                    expenses_total = self._breakdown_total("expenses", expenses_rows) if has_expenses else None
                    if income_total is not None:
                        revenue = float(income_total)
                    if expenses_total is not None:
                        expenses = float(expenses_total)
                    if income_total is not None or expenses_total is not None:
                        balance = revenue + expenses
                    applied_economy_by_team[(season_year, team_code)] = {
                        "revenue": float(revenue),
                        "expenses": float(expenses),
                        "balance": float(balance),
                    }
                    conn.execute(
                        """
                        INSERT INTO team_economy (
                            team_id, season_year, balance, revenue, expenses, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(team_id, season_year) DO UPDATE SET
                            balance = excluded.balance,
                            revenue = excluded.revenue,
                            expenses = excluded.expenses,
                            updated_at = excluded.updated_at
                        """,
                        (team_id, season_year, float(balance), float(revenue), float(expenses), timestamp),
                    )
                    conn.execute(
                        """
                        INSERT INTO team_owner_office (
                            team_id,
                            season_year,
                            revenue,
                            expenses,
                            balance,
                            income_json,
                            expenses_json,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(team_id, season_year) DO UPDATE SET
                            revenue = excluded.revenue,
                            expenses = excluded.expenses,
                            balance = excluded.balance,
                            income_json = excluded.income_json,
                            expenses_json = excluded.expenses_json,
                            updated_at = excluded.updated_at
                        """,
                        (
                            team_id,
                            season_year,
                            self._format_value(revenue),
                            self._format_value(expenses),
                            self._format_value(balance),
                            json.dumps(self._normalize_rows(income_rows, "income"), ensure_ascii=True),
                            json.dumps(self._normalize_rows(expenses_rows, "expenses"), ensure_ascii=True),
                            timestamp,
                        ),
                    )
                conn.commit()
            summary = self._group_economy_records(records, applied_economy_by_team)
            return {
                "ok": True,
                "record_count": len(records),
                "group_count": len(summary),
                "seasons": sorted({int(row["season_year"]) for row in summary}),
                "summary": summary,
            }

    def preview_owner_office_csv(self, csv_text: str) -> Dict[str, Any]:
            text = str(csv_text or "").lstrip("\ufeff")
            if not text.strip():
                return {"ok": False, "errors": [{"line": None, "message": "El CSV está vacío."}], "records": [], "summary": []}
            with self._db.connect() as conn:
                teams_by_code = {
                    str(row["code"]).upper(): {"id": int(row["id"]), "name": str(row["name"])}
                    for row in conn.execute("SELECT id, code, name FROM teams").fetchall()
                }
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            try:
                reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            except csv.Error as err:
                return {"ok": False, "errors": [{"line": None, "message": f"No se pudo leer el CSV: {err}"}], "records": [], "summary": []}
            if not reader.fieldnames:
                return {"ok": False, "errors": [{"line": None, "message": "El CSV no tiene cabeceras."}], "records": [], "summary": []}
            aliases = {
                "season": ["season", "season_year", "temporada", "año", "ano", "owner_season", "temporada_despacho"],
                "team": ["team", "team_code", "equipo", "codigo", "código", "franquicia"],
                "confidence_current": ["confidence_current", "confianza_actual", "confianza", "trust", "trust_current"],
                "confidence_change": ["confidence_change", "cambio", "cambio_confianza", "trust_change"],
                "season_goal_set": ["season_goal_set", "objetivo_fijado", "objetivo_temporada_fijado"],
                "season_goal_achieved": ["season_goal_achieved", "objetivo_cumplido", "objetivo_temporada_cumplido"],
                "history_season": ["history_season", "historial_temporada", "temporada_historial", "sports_season", "season_history"],
                "wins": ["wins", "victorias", "w"],
                "losses": ["losses", "derrotas", "l"],
                "result": ["result", "resultado", "final_result", "resultado_final"],
            }
            raw_records: List[Dict[str, Any]] = []
            errors: List[Dict[str, Any]] = []
            try:
                for row in reader:
                    if not any(str(value or "").strip() for value in row.values()):
                        continue
                    raw_records.append(
                        {
                            "line": reader.line_num,
                            "season": self._office_header_value(row, aliases["season"]),
                            "team": self._office_header_value(row, aliases["team"]),
                            "confidence_current": self._office_header_value(row, aliases["confidence_current"]),
                            "confidence_change": self._office_header_value(row, aliases["confidence_change"]),
                            "season_goal_set": self._office_header_value(row, aliases["season_goal_set"]),
                            "season_goal_achieved": self._office_header_value(row, aliases["season_goal_achieved"]),
                            "history_season": self._office_header_value(row, aliases["history_season"]),
                            "wins": self._office_header_value(row, aliases["wins"]),
                            "losses": self._office_header_value(row, aliases["losses"]),
                            "result": self._office_header_value(row, aliases["result"]),
                        }
                    )
            except csv.Error as err:
                errors.append({"line": None, "message": f"No se pudo leer el CSV: {err}"})
            records, record_errors = self._normalize_office_records(raw_records, teams_by_code)
            errors.extend(record_errors)
            if not records and not errors:
                errors.append({"line": None, "message": "No se encontraron filas importables."})
            return {
                "ok": not errors,
                "errors": errors,
                "records": records,
                "summary": self._group_office_records(records),
                "objective_options": self._objective_options,
            }

    def apply_owner_office_import(self, records_payload: Any) -> Dict[str, Any]:
            if not isinstance(records_payload, list):
                raise ValueError("records_required")
            with self._db.connect() as conn:
                teams_by_code = {
                    str(row["code"]).upper(): {"id": int(row["id"]), "name": str(row["name"])}
                    for row in conn.execute("SELECT id, code, name FROM teams").fetchall()
                }
                records, errors = self._normalize_office_records(records_payload, teams_by_code)
                if errors:
                    err = ValueError("invalid_records")
                    setattr(err, "errors", errors)
                    raise err
                grouped = self._group_office_records(records)
                timestamp = self._now()
                for group in grouped:
                    team = teams_by_code[str(group["team_code"])]
                    team_id = int(team["id"])
                    season_year = int(group["season_year"])
                    existing = conn.execute(
                        """
                        SELECT *
                        FROM team_owner_office
                        WHERE team_id = ? AND season_year = ?
                        """,
                        (team_id, season_year),
                    ).fetchone()
                    confidence_current = str(group.get("confidence_current") or "").strip()
                    confidence_change = str(group.get("confidence_change") or "").strip()
                    season_goal_set = str(group.get("season_goal_set") or "").strip()
                    season_goal_achieved = str(group.get("season_goal_achieved") or "").strip()
                    performance_rows = group.get("performance_rows") if isinstance(group.get("performance_rows"), list) else []
                    normalized_performance_rows = (
                        self._normalize_performance(performance_rows, season_year)
                        if performance_rows
                        else (
                            self._performance_from_json(existing["performance_json"])
                            if existing else self._normalize_performance([], season_year)
                        )
                    )
                    conn.execute(
                        """
                        INSERT INTO team_owner_office (
                            team_id,
                            season_year,
                            confidence_current,
                            confidence_change,
                            season_goal_set,
                            season_goal_achieved,
                            revenue,
                            expenses,
                            balance,
                            income_json,
                            expenses_json,
                            performance_json,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(team_id, season_year) DO UPDATE SET
                            confidence_current = excluded.confidence_current,
                            confidence_change = excluded.confidence_change,
                            season_goal_set = excluded.season_goal_set,
                            season_goal_achieved = excluded.season_goal_achieved,
                            revenue = excluded.revenue,
                            expenses = excluded.expenses,
                            balance = excluded.balance,
                            income_json = excluded.income_json,
                            expenses_json = excluded.expenses_json,
                            performance_json = excluded.performance_json,
                            updated_at = excluded.updated_at
                        """,
                        (
                            team_id,
                            season_year,
                            confidence_current or (str(existing["confidence_current"] or "") if existing else ""),
                            confidence_change or (str(existing["confidence_change"] or "") if existing else ""),
                            season_goal_set or (str(existing["season_goal_set"] or "") if existing else ""),
                            season_goal_achieved or (str(existing["season_goal_achieved"] or "") if existing else ""),
                            str(existing["revenue"]) if existing and existing["revenue"] is not None else None,
                            str(existing["expenses"]) if existing and existing["expenses"] is not None else None,
                            str(existing["balance"]) if existing and existing["balance"] is not None else None,
                            str(existing["income_json"]) if existing and existing["income_json"] else "[]",
                            str(existing["expenses_json"]) if existing and existing["expenses_json"] else "[]",
                            json.dumps(normalized_performance_rows, ensure_ascii=True),
                            timestamp,
                        ),
                    )
                conn.commit()
            return {
                "ok": True,
                "record_count": len(records),
                "group_count": len(grouped),
                "seasons": sorted({int(row["season_year"]) for row in grouped}),
                "summary": grouped,
            }
