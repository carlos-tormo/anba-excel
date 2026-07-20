"""Administrative owner economy and owner-office import pipelines."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..domain._values import parse_amount_like, parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_amount_like, parse_int


def normalize_import_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_csv_amount(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()").replace(" ", "")
    cleaned = re.sub(r"[^0-9,.\-]", "", cleaned)
    if not cleaned or cleaned in {"-", ".", ","}:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) > 2 or (
            len(parts) == 2
            and len(parts[-1]) == 3
            and len(parts[0].lstrip("-")) <= 3
            and all(part.lstrip("-").isdigit() for part in parts)
        ):
            cleaned = "".join(parts)
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 2 or (
            len(parts) == 2
            and len(parts[-1]) == 3
            and len(parts[0].lstrip("-")) <= 3
            and all(part.lstrip("-").isdigit() for part in parts)
        ):
            cleaned = "".join(parts)
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return -abs(parsed) if negative else parsed


OWNER_OFFICE_IMPORT_ROWS = {
    "income": [
        {"key": "recaudacion", "label": "Recaudación", "type": "category"},
        {"key": "media_espectadores", "label": "Media espectadores", "type": "field"},
        {"key": "entradas_regular_season", "label": "Entradas Regular Season", "type": "field"},
        {"key": "partidos_playoffs", "label": "Partidos playoffs", "type": "field"},
        {"key": "entradas_playoffs", "label": "Entradas Playoffs", "type": "field"},
        {"key": "precio_medio_entrada", "label": "Precio medio entrada", "type": "field"},
        {"key": "consumiciones", "label": "Consumiciones", "type": "field"},
        {"key": "merchandising", "label": "Merchandising", "type": "category"},
        {"key": "ventas_camisetas_ropa", "label": "Ventas de camisetas y ropa", "type": "field"},
        {"key": "precio_medio_articulo", "label": "Precio medio artículo", "type": "field"},
        {"key": "derechos", "label": "Derechos", "type": "category"},
        {"key": "tv_globales", "label": "TV globales", "type": "field"},
        {"key": "tv_local", "label": "TV local", "type": "field"},
        {"key": "licencias", "label": "Licencias", "type": "field"},
        {"key": "sponsor", "label": "Sponsor", "type": "category"},
        {"key": "patrocinador_jersey", "label": "Patrocinador jersey", "type": "field"},
        {"key": "patrocinador_estadio", "label": "Patrocinador estadio", "type": "field"},
        {"key": "patrocinadores_generales", "label": "Patrocinadores generales", "type": "field"},
        {"key": "flujos_caja_positivos", "label": "Flujos de caja positivos", "type": "category"},
        {"key": "traspasos_positivos", "label": "Traspasos", "type": "field"},
        {"key": "bonificaciones", "label": "Bonificaciones", "type": "field"},
        {"key": "reparto_beneficios_positivo", "label": "Reparto beneficios", "type": "field"},
        {"key": "reparto_impuesto_lujo", "label": "Reparto impuesto de lujo", "type": "field"},
    ],
    "expenses": [
        {"key": "coste_plantilla", "label": "Coste plantilla", "type": "category"},
        {"key": "salarios", "label": "Salarios", "type": "field"},
        {"key": "multa", "label": "Multa", "type": "field"},
        {"key": "cuerpo_tecnico", "label": "Cuerpo técnico", "type": "category"},
        {"key": "multiplicador_exitos", "label": "Multiplicador éxitos", "type": "field"},
        {"key": "gastos_cuerpo_tecnico", "label": "Gastos", "type": "field"},
        {"key": "gastos_estadio", "label": "Gastos de estadio", "type": "category"},
        {"key": "partidos", "label": "Partidos", "type": "field"},
        {"key": "gastos_partido", "label": "Gastos partido", "type": "field"},
        {"key": "indice_coste_estadio", "label": "Índice coste", "type": "field"},
        {"key": "gastos_television", "label": "Gastos de televisión", "type": "category"},
        {"key": "produccion", "label": "Producción", "type": "field"},
        {"key": "costes_marketing", "label": "Costes de marketing", "type": "category"},
        {"key": "indice_coste_marketing", "label": "Índice coste", "type": "field"},
        {"key": "costes_ineficiencia", "label": "Costes ineficiencia", "type": "field"},
        {"key": "unidades", "label": "Unidades", "type": "field"},
        {"key": "coste_por_unidad", "label": "Coste por unidad", "type": "field"},
        {"key": "gastos_operativos", "label": "Gastos operativos", "type": "category"},
        {"key": "gastos_operativos_valor", "label": "Gastos", "type": "field"},
        {"key": "indice_coste_operativo", "label": "Índice coste", "type": "field"},
        {"key": "flujos_caja_negativos", "label": "Flujos de caja negativos", "type": "category"},
        {"key": "traspasos_negativos", "label": "Traspasos", "type": "field"},
        {"key": "sanciones", "label": "Sanciones", "type": "field"},
        {"key": "reparto_beneficios_negativo", "label": "Reparto beneficios", "type": "field"},
    ],
}

ECONOMY_IMPORT_TOTAL_ROWS = [
    {"key": "revenue", "label": "Ingresos", "type": "field"},
    {"key": "expenses", "label": "Gastos", "type": "field"},
    {"key": "balance", "label": "Balance", "type": "field"},
]


def owner_office_import_schema() -> Dict[str, List[Dict[str, str]]]:
    schema: Dict[str, List[Dict[str, str]]] = {}
    for section, rows in OWNER_OFFICE_IMPORT_ROWS.items():
        current_category = {"key": "", "label": ""}
        schema_rows: List[Dict[str, str]] = []
        for row in rows:
            normalized = {
                "key": str(row["key"]),
                "label": str(row["label"]),
                "type": str(row["type"]),
                "category_key": str(current_category["key"]),
                "category_label": str(current_category["label"]),
            }
            schema_rows.append(normalized)
            if normalized["type"] == "category":
                current_category = {"key": normalized["key"], "label": normalized["label"]}
        schema[section] = schema_rows
    schema["economy"] = [
        {
            "key": str(row["key"]),
            "label": str(row["label"]),
            "type": str(row["type"]),
            "category_key": "",
            "category_label": "Totales economía",
        }
        for row in ECONOMY_IMPORT_TOTAL_ROWS
    ]
    return schema


class OwnerAdminImportService:
    def __init__(
        self,
        repository: Any,
        *,
        now: Callable[[], str],
        objective_options: List[str],
    ) -> None:
        self._repository = repository
        self._now = now
        self._objective_options = list(objective_options)

    def _owner_office_rows_from_json(self, value: Any, section: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        rows: List[Dict[str, Any]] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or "").strip()
            label = str(raw.get("label") or "").strip()
            row_type = str(raw.get("type") or "field").strip().lower()
            if row_type not in {"category", "field"}:
                row_type = "field"
            if not key or not label:
                continue
            raw_value = "" if raw.get("value") is None else str(raw.get("value"))
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "type": row_type,
                    "value": self._owner_office_field_value_text(raw_value) if row_type == "field" else raw_value,
                }
            )
        return self._owner_office_apply_calculated_rows(section, rows)

    def _owner_office_field_value_text(self, value: Any) -> str:
        text = "" if value is None else str(value).strip()
        compact = re.sub(r"[€$]", "", text.replace(" ", ""))
        if re.fullmatch(r"-?\d+\.\d{1,2}", compact):
            return text.replace(".", ",")
        return text

    def _normalize_owner_office_rows(self, rows: Any, section: Optional[str] = None) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for idx, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()
            if not label:
                continue
            key = str(raw.get("key") or "").strip() or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or f"row_{idx}"
            row_type = str(raw.get("type") or "field").strip().lower()
            if row_type not in {"category", "field"}:
                row_type = "field"
            raw_value = "" if raw.get("value") is None else str(raw.get("value")).strip()[:500]
            normalized.append(
                {
                    "key": key[:80],
                    "label": label[:160],
                    "type": row_type,
                    "value": self._owner_office_field_value_text(raw_value) if row_type == "field" else raw_value,
                }
            )
        return self._owner_office_apply_calculated_rows(section, normalized)

    def _owner_office_apply_calculated_rows(
        self,
        section: Optional[str],
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if section not in {"income", "expenses"} or not rows:
            return rows

        amounts: Dict[str, float] = {}
        present: set[str] = set()
        for row in rows:
            key = str(row.get("key") or "")
            parsed = parse_amount_like(row.get("value"))
            amounts[key] = float(parsed or 0)
            if parsed is not None:
                present.add(key)

        def value(key: str) -> float:
            return amounts.get(key, 0.0)

        def magnitude(key: str) -> float:
            return abs(value(key))

        def calculated(keys: List[str], amount: float) -> str:
            if not any(key in present for key in keys):
                return ""
            return self._owner_import_value_text(amount)

        if section == "income":
            formulas = {
                "recaudacion": calculated(
                    ["entradas_playoffs", "entradas_regular_season", "precio_medio_entrada", "consumiciones"],
                    (
                        value("entradas_playoffs") + value("entradas_regular_season")
                    ) * (0.6 * value("precio_medio_entrada"))
                    + (
                        value("entradas_playoffs") + value("entradas_regular_season")
                    ) * (0.9 * value("consumiciones")),
                ),
                "merchandising": calculated(
                    ["ventas_camisetas_ropa", "precio_medio_articulo"],
                    value("ventas_camisetas_ropa") * value("precio_medio_articulo"),
                ),
                "derechos": calculated(
                    ["tv_globales", "tv_local", "licencias"],
                    value("tv_globales") + value("tv_local") + value("licencias"),
                ),
                "sponsor": calculated(
                    ["patrocinador_jersey", "patrocinador_estadio", "patrocinadores_generales"],
                    value("patrocinador_jersey")
                    + value("patrocinador_estadio")
                    + value("patrocinadores_generales"),
                ),
                "flujos_caja_positivos": calculated(
                    [
                        "traspasos_positivos",
                        "bonificaciones",
                        "reparto_beneficios_positivo",
                        "reparto_impuesto_lujo",
                    ],
                    value("traspasos_positivos")
                    + value("bonificaciones")
                    + value("reparto_beneficios_positivo")
                    + value("reparto_impuesto_lujo"),
                ),
            }
        else:
            formulas = {
                "coste_plantilla": calculated(
                    ["salarios", "multa"],
                    -magnitude("salarios") - magnitude("multa"),
                ),
                "cuerpo_tecnico": calculated(
                    ["multiplicador_exitos", "gastos_cuerpo_tecnico"],
                    magnitude("multiplicador_exitos") * magnitude("gastos_cuerpo_tecnico") * -1,
                ),
                "gastos_estadio": calculated(
                    ["partidos", "gastos_partido", "indice_coste_estadio"],
                    magnitude("partidos") * magnitude("gastos_partido") * magnitude("indice_coste_estadio") * -1,
                ),
                "gastos_television": calculated(
                    ["produccion"],
                    magnitude("produccion") * -1,
                ),
                "costes_marketing": calculated(
                    ["costes_ineficiencia", "unidades", "coste_por_unidad", "indice_coste_marketing"],
                    -magnitude("costes_ineficiencia")
                    - (magnitude("unidades") * magnitude("coste_por_unidad")) * magnitude("indice_coste_marketing"),
                ),
                "gastos_operativos": calculated(
                    ["gastos_operativos_valor", "indice_coste_operativo"],
                    magnitude("gastos_operativos_valor") * magnitude("indice_coste_operativo") * -1,
                ),
                "flujos_caja_negativos": calculated(
                    ["traspasos_negativos", "sanciones", "reparto_beneficios_negativo"],
                    -magnitude("traspasos_negativos")
                    - magnitude("sanciones")
                    - magnitude("reparto_beneficios_negativo"),
                ),
            }

        calculated_rows: List[Dict[str, Any]] = []
        for row in rows:
            row_copy = dict(row)
            key = str(row_copy.get("key") or "")
            if str(row_copy.get("type") or "") == "category" and key in formulas:
                row_copy["value"] = formulas[key]
            calculated_rows.append(row_copy)
        return calculated_rows

    def _owner_office_breakdown_total(self, section: str, rows: List[Dict[str, Any]]) -> Optional[float]:
        category_keys = {
            "income": {
                "recaudacion",
                "merchandising",
                "derechos",
                "sponsor",
                "flujos_caja_positivos",
            },
            "expenses": {
                "coste_plantilla",
                "cuerpo_tecnico",
                "gastos_estadio",
                "gastos_television",
                "costes_marketing",
                "gastos_operativos",
                "flujos_caja_negativos",
            },
        }.get(section, set())
        total = 0.0
        has_value = False
        for row in rows:
            if str(row.get("key") or "") not in category_keys:
                continue
            parsed = parse_amount_like(row.get("value"))
            if parsed is None:
                continue
            total += float(parsed)
            has_value = True
        return total if has_value else None

    def _owner_import_schema_payload(self) -> Dict[str, Any]:
        schema = owner_office_import_schema()
        return {
            section: [
                {
                    "key": row["key"],
                    "label": row["label"],
                    "type": row["type"],
                    "category_key": row["category_key"],
                    "category_label": row["category_label"],
                }
                for row in rows
            ]
            for section, rows in schema.items()
        }

    def _owner_import_header_value(self, row: Dict[str, Any], aliases: List[str]) -> str:
        normalized_aliases = {normalize_import_text(alias) for alias in aliases}
        for key, value in row.items():
            if normalize_import_text(key) in normalized_aliases:
                return str(value or "").strip()
        return ""

    def _owner_import_key(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]+", "_", text).strip("_")

    def _owner_import_section(self, value: Any) -> str:
        normalized = normalize_import_text(value)
        if normalized in {"income", "ingreso", "ingresos", "revenue", "revenues"}:
            return "income"
        if normalized in {"expense", "expenses", "gasto", "gastos", "coste", "costes"}:
            return "expenses"
        if normalized in {"economy", "economia", "economía", "summary", "totals", "totales", "tracker"}:
            return "economy"
        return ""

    def _owner_import_resolve_row(self, section: str, key_value: str, label_value: str, category_value: str) -> tuple[Optional[Dict[str, str]], Optional[str]]:
        schema = owner_office_import_schema().get(section) or []
        by_key = {row["key"]: row for row in schema}
        candidate_key = self._owner_import_key(key_value)
        if candidate_key:
            row = by_key.get(candidate_key)
            if row and (section == "economy" or row["type"] == "field"):
                return row, None
            if row and row["type"] == "category":
                return None, f"'{key_value}' es una categoría, no una fila importable"
            label_value = label_value or key_value

        label_norm = normalize_import_text(label_value)
        if not label_norm:
            return None, "Falta key o label/concepto"
        matches = [row for row in schema if row["type"] == "field" and normalize_import_text(row["label"]) == label_norm]
        category_norm = normalize_import_text(category_value)
        if category_norm:
            matches = [
                row for row in matches
                if normalize_import_text(row["category_key"]) == category_norm
                or normalize_import_text(row["category_label"]) == category_norm
            ]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"Concepto ambiguo '{label_value}'. Usa la columna key."
        return None, f"Concepto desconocido '{label_value}'"

    def _owner_import_normalize_records(
        self,
        raw_records: List[Dict[str, Any]],
        teams_by_code: Dict[str, Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        normalized_records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for idx, raw in enumerate(raw_records):
            line = parse_int(raw.get("line")) or idx + 2
            season = parse_int(raw.get("season_year") or raw.get("season"))
            team_code = normalize_team_code(raw.get("team_code") or raw.get("team"))
            section = self._owner_import_section(raw.get("section"))
            key_value = str(raw.get("key") or "").strip()
            label_value = str(raw.get("label") or "").strip()
            category_value = str(raw.get("category") or "").strip()
            raw_amount = raw.get("value")
            raw_amount_text = str(raw_amount or "").strip()
            amount = None if not raw_amount_text else parse_csv_amount(raw_amount)
            if season is None or season < 2000 or season > 2100:
                errors.append({"line": line, "message": "Temporada inválida. Usa el año inicial, por ejemplo 2025."})
                continue
            if not team_code or team_code not in teams_by_code:
                errors.append({"line": line, "message": f"Equipo inválido: {team_code or '-'}"})
                continue
            if section not in {"income", "expenses", "economy"}:
                errors.append({"line": line, "message": "Sección inválida. Usa income/ingresos, expenses/gastos o economy/totales."})
                continue
            row_def, row_error = self._owner_import_resolve_row(section, key_value, label_value, category_value)
            if row_error or not row_def:
                errors.append({"line": line, "message": row_error or "Concepto inválido."})
                continue
            if raw_amount_text and amount is None:
                errors.append({"line": line, "message": f"Importe inválido para {team_code} {row_def['label']}."})
                continue
            normalized_amount = None
            if amount is not None:
                if section == "income" or (section == "economy" and row_def["key"] == "revenue"):
                    normalized_amount = abs(float(amount))
                elif section == "expenses" or (section == "economy" and row_def["key"] == "expenses"):
                    normalized_amount = -abs(float(amount))
                else:
                    normalized_amount = float(amount)
            normalized_records.append(
                {
                    "line": line,
                    "season_year": int(season),
                    "team_code": team_code,
                    "team_name": str(teams_by_code[team_code].get("name") or ""),
                    "section": section,
                    "key": row_def["key"],
                    "label": row_def["label"],
                    "category_key": row_def["category_key"],
                    "category_label": row_def["category_label"],
                    "value": normalized_amount,
                }
            )
        return normalized_records, errors

    def _owner_import_group_records(
        self,
        records: List[Dict[str, Any]],
        economy_by_team: Optional[Dict[tuple[int, str], Dict[str, float]]] = None,
    ) -> List[Dict[str, Any]]:
        groups: Dict[tuple[int, str], Dict[str, Any]] = {}
        for record in records:
            key = (int(record["season_year"]), str(record["team_code"]))
            if key not in groups:
                groups[key] = {
                    "season_year": int(record["season_year"]),
                    "team_code": str(record["team_code"]),
                    "team_name": str(record.get("team_name") or ""),
                    "income": {},
                    "expenses": {},
                    "economy": {},
                    "income_rows": 0,
                    "expenses_rows": 0,
                    "economy_rows": 0,
                }
            section = str(record["section"])
            row_key = str(record["key"])
            raw_value = record.get("value")
            if raw_value is None or str(raw_value).strip() == "":
                if row_key not in groups[key][section]:
                    groups[key][section][row_key] = None
            else:
                value = float(raw_value or 0)
                existing = groups[key][section].get(row_key)
                groups[key][section][row_key] = float(existing or 0) + value
            if section == "income":
                groups[key]["income_rows"] += 1
            elif section == "expenses":
                groups[key]["expenses_rows"] += 1
            elif section == "economy":
                groups[key]["economy_rows"] += 1

        summary: List[Dict[str, Any]] = []
        for group in groups.values():
            group_key = (int(group["season_year"]), str(group["team_code"]))
            existing = (economy_by_team or {}).get(group_key) or {}
            economy = group.get("economy") or {}
            revenue = float(
                economy["revenue"]
                if economy.get("revenue") not in (None, "")
                else existing.get("revenue", 0)
            )
            expenses = float(
                economy["expenses"]
                if economy.get("expenses") not in (None, "")
                else existing.get("expenses", 0)
            )
            income_total = self._owner_office_breakdown_total(
                "income",
                self._owner_import_rows_for_json("income", group.get("income") or {}),
            )
            expenses_total = self._owner_office_breakdown_total(
                "expenses",
                self._owner_import_rows_for_json("expenses", group.get("expenses") or {}),
            )
            if income_total is not None:
                revenue = float(income_total)
            if expenses_total is not None:
                expenses = float(expenses_total)
            balance = float(
                economy["balance"]
                if economy.get("balance") not in (None, "") and income_total is None and expenses_total is None
                else existing.get("balance", revenue + expenses)
            )
            if income_total is not None or expenses_total is not None:
                balance = revenue + expenses
            summary.append(
                {
                    "season_year": int(group["season_year"]),
                    "team_code": str(group["team_code"]),
                    "team_name": str(group["team_name"]),
                    "income_rows": int(group["income_rows"]),
                    "expenses_rows": int(group["expenses_rows"]),
                    "economy_rows": int(group["economy_rows"]),
                    "revenue": revenue,
                    "expenses": expenses,
                    "balance": balance,
                    "has_income": bool(group["income"]),
                    "has_expenses": bool(group["expenses"]),
                    "has_economy": bool(group["economy"]),
                }
            )
        return sorted(summary, key=lambda row: (int(row["season_year"]), str(row["team_code"])))

    def _owner_import_value_text(self, value: Any) -> str:
        if value is None or str(value).strip() == "":
            return ""
        amount = float(value or 0)
        rounded = round(amount)
        if abs(amount - rounded) < 0.000001:
            return str(int(rounded))
        return f"{amount:.2f}".rstrip("0").rstrip(".")

    def _owner_import_rows_for_json(self, section: str, values_by_key: Dict[str, float]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for row in owner_office_import_schema().get(section, []):
            if row["type"] == "category":
                rows.append({"key": row["key"], "label": row["label"], "type": "category", "value": ""})
            else:
                rows.append(
                    {
                        "key": row["key"],
                        "label": row["label"],
                        "type": "field",
                        "value": self._owner_import_value_text(
                            values_by_key[row["key"]] if row["key"] in values_by_key else ""
                        ),
                    }
                )
        return self._owner_office_apply_calculated_rows(section, rows)

    def preview_owner_economy_csv(self, csv_text: str) -> Dict[str, Any]:
            text = str(csv_text or "").lstrip("\ufeff")
            if not text.strip():
                return {"ok": False, "errors": [{"line": None, "message": "El CSV está vacío."}], "records": [], "summary": [], "schema": self._owner_import_schema_payload()}
            with self._repository.transaction() as conn:
                teams_by_code = self._repository.teams_by_code(conn)
                economy_by_team = self._repository.economy_by_team(conn)
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            try:
                reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            except csv.Error as err:
                return {"ok": False, "errors": [{"line": None, "message": f"No se pudo leer el CSV: {err}"}], "records": [], "summary": [], "schema": self._owner_import_schema_payload()}
            if not reader.fieldnames:
                return {"ok": False, "errors": [{"line": None, "message": "El CSV no tiene cabeceras."}], "records": [], "summary": [], "schema": self._owner_import_schema_payload()}

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
                            "season": self._owner_import_header_value(row, aliases["season"]),
                            "team": self._owner_import_header_value(row, aliases["team"]),
                            "section": self._owner_import_header_value(row, aliases["section"]),
                            "key": self._owner_import_header_value(row, aliases["key"]),
                            "label": self._owner_import_header_value(row, aliases["label"]),
                            "category": self._owner_import_header_value(row, aliases["category"]),
                            "value": self._owner_import_header_value(row, aliases["value"]),
                        }
                    )
            except csv.Error as err:
                errors.append({"line": None, "message": f"No se pudo leer el CSV: {err}"})
            records, record_errors = self._owner_import_normalize_records(raw_records, teams_by_code)
            errors.extend(record_errors)
            if not records and not errors:
                errors.append({"line": None, "message": "No se encontraron filas importables."})
            return {
                "ok": not errors,
                "errors": errors,
                "records": records,
                "summary": self._owner_import_group_records(records, economy_by_team),
                "schema": self._owner_import_schema_payload(),
            }

    def apply_owner_economy_import(self, records_payload: Any) -> Dict[str, Any]:
            if not isinstance(records_payload, list):
                raise ValueError("records_required")
            with self._repository.transaction() as conn:
                teams_by_code = self._repository.teams_by_code(conn)
                records, errors = self._owner_import_normalize_records(records_payload, teams_by_code)
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
                    existing_economy = self._repository.economy_row(conn, team_id, season_year)
                    existing_owner = self._repository.owner_office_row(conn, team_id, season_year)
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
                        self._owner_import_rows_for_json("income", sections["income"])
                        if has_income
                        else (self._owner_office_rows_from_json(existing_owner["income_json"], "income") if existing_owner else [])
                    )
                    expenses_rows = (
                        self._owner_import_rows_for_json("expenses", sections["expenses"])
                        if has_expenses
                        else (self._owner_office_rows_from_json(existing_owner["expenses_json"], "expenses") if existing_owner else [])
                    )
                    income_total = self._owner_office_breakdown_total("income", income_rows) if has_income else None
                    expenses_total = self._owner_office_breakdown_total("expenses", expenses_rows) if has_expenses else None
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
                    self._repository.upsert_economy(
                        conn,
                        team_id=team_id,
                        season_year=season_year,
                        balance=float(balance),
                        revenue=float(revenue),
                        expenses=float(expenses),
                        updated_at=timestamp,
                    )
                    self._repository.upsert_owner_economy(
                        conn,
                        team_id=team_id,
                        season_year=season_year,
                        revenue=self._owner_import_value_text(revenue),
                        expenses=self._owner_import_value_text(expenses),
                        balance=self._owner_import_value_text(balance),
                        income_json=json.dumps(self._normalize_owner_office_rows(income_rows, "income"), ensure_ascii=True),
                        expenses_json=json.dumps(self._normalize_owner_office_rows(expenses_rows, "expenses"), ensure_ascii=True),
                        updated_at=timestamp,
                    )
            summary = self._owner_import_group_records(records, applied_economy_by_team)
            return {
                "ok": True,
                "record_count": len(records),
                "group_count": len(summary),
                "seasons": sorted({int(row["season_year"]) for row in summary}),
                "summary": summary,
            }

    def _normalize_objective(self, value: Any) -> str:
        text = str(value or "").strip()
        return text if text in self._objective_options else ""

    def _owner_office_import_header_value(self, row: Dict[str, Any], aliases: List[str]) -> str:
        return self._owner_import_header_value(row, aliases)

    def _owner_office_import_normalize_records(
        self,
        raw_records: List[Dict[str, Any]],
        teams_by_code: Dict[str, Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for idx, raw in enumerate(raw_records):
            line = parse_int(raw.get("line")) or idx + 2
            season_year = parse_int(raw.get("season_year") or raw.get("season"))
            team_code = normalize_team_code(raw.get("team_code") or raw.get("team"))
            confidence_current = str(raw.get("confidence_current") or "").strip()[:80]
            confidence_change = str(raw.get("confidence_change") or "").strip()[:80]
            season_goal_set_raw = str(raw.get("season_goal_set") or "").strip()
            season_goal_achieved_raw = str(raw.get("season_goal_achieved") or "").strip()
            history_season_raw = str(raw.get("history_season") or "").strip()
            wins_raw = str(raw.get("wins") or "").strip()
            losses_raw = str(raw.get("losses") or "").strip()
            result = str(raw.get("result") or "").strip()[:80]
            if season_year is None or season_year < 2000 or season_year > 2100:
                errors.append({"line": line, "message": "Temporada inválida. Usa el año inicial, por ejemplo 2025."})
                continue
            if not team_code or team_code not in teams_by_code:
                errors.append({"line": line, "message": f"Equipo inválido: {team_code or '-'}"})
                continue

            season_goal_set = ""
            season_goal_achieved = ""
            if season_goal_set_raw:
                season_goal_set = self._normalize_objective(season_goal_set_raw)
                if not season_goal_set:
                    errors.append({"line": line, "message": f"Objetivo fijado inválido: {season_goal_set_raw}."})
                    continue
            if season_goal_achieved_raw:
                season_goal_achieved = self._normalize_objective(season_goal_achieved_raw)
                if not season_goal_achieved:
                    errors.append({"line": line, "message": f"Objetivo cumplido inválido: {season_goal_achieved_raw}."})
                    continue

            normalized_performance = raw.get("performance_row")
            has_normalized_performance = isinstance(normalized_performance, dict)
            has_performance = has_normalized_performance or any([history_season_raw, wins_raw, losses_raw, result])
            performance_row = None
            if has_normalized_performance:
                history_season = parse_int(normalized_performance.get("season_year"))
                if history_season is None or history_season < 2000 or history_season > 2100:
                    errors.append({"line": line, "message": "Temporada de historial inválida."})
                    continue
                wins = parse_int(normalized_performance.get("wins"))
                losses = parse_int(normalized_performance.get("losses"))
                performance_row = {
                    "season_year": max(2000, min(2100, history_season)),
                    "wins": "" if wins is None else max(0, min(100, wins)),
                    "losses": "" if losses is None else max(0, min(100, losses)),
                    "result": str(normalized_performance.get("result") or "").strip()[:80],
                }
            elif has_performance:
                history_season = parse_int(history_season_raw)
                if history_season is None or history_season < 2000 or history_season > 2100:
                    errors.append({"line": line, "message": "Temporada de historial inválida."})
                    continue
                wins = parse_int(wins_raw)
                losses = parse_int(losses_raw)
                if wins_raw and wins is None:
                    errors.append({"line": line, "message": "Victorias inválidas."})
                    continue
                if losses_raw and losses is None:
                    errors.append({"line": line, "message": "Derrotas inválidas."})
                    continue
                performance_row = {
                    "season_year": max(2000, min(2100, history_season)),
                    "wins": "" if wins is None else max(0, min(100, wins)),
                    "losses": "" if losses is None else max(0, min(100, losses)),
                    "result": result,
                }

            if not any([confidence_current, confidence_change, season_goal_set, season_goal_achieved, performance_row]):
                errors.append({"line": line, "message": "Fila sin datos importables."})
                continue

            records.append(
                {
                    "line": line,
                    "season_year": int(season_year),
                    "team_code": team_code,
                    "team_name": str(teams_by_code[team_code].get("name") or ""),
                    "confidence_current": confidence_current,
                    "confidence_change": confidence_change,
                    "season_goal_set": season_goal_set,
                    "season_goal_achieved": season_goal_achieved,
                    "performance_row": performance_row,
                }
            )
        errors.extend(self._owner_office_import_group_errors(records))
        return records, errors

    def _owner_office_import_group_errors(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[tuple[int, str], List[Dict[str, Any]]] = {}
        for record in records:
            grouped.setdefault((int(record["season_year"]), str(record["team_code"])), []).append(record)
        errors: List[Dict[str, Any]] = []
        for (_season_year, team_code), group_records in grouped.items():
            performance_rows = [row for row in group_records if row.get("performance_row")]
            if len(performance_rows) > 5:
                first_line = performance_rows[0].get("line")
                errors.append(
                    {
                        "line": first_line,
                        "message": f"{team_code} tiene más de 5 filas de historial deportivo para la misma temporada.",
                    }
                )
        return errors

    def _owner_office_import_group_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: Dict[tuple[int, str], Dict[str, Any]] = {}
        for record in records:
            key = (int(record["season_year"]), str(record["team_code"]))
            if key not in groups:
                groups[key] = {
                    "season_year": int(record["season_year"]),
                    "team_code": str(record["team_code"]),
                    "team_name": str(record.get("team_name") or ""),
                    "confidence_current": "",
                    "confidence_change": "",
                    "season_goal_set": "",
                    "season_goal_achieved": "",
                    "performance_rows": [],
                }
            for field in ["confidence_current", "confidence_change", "season_goal_set", "season_goal_achieved"]:
                value = str(record.get(field) or "").strip()
                if value:
                    groups[key][field] = value
            performance_row = record.get("performance_row")
            if isinstance(performance_row, dict):
                groups[key]["performance_rows"].append(performance_row)
        summary: List[Dict[str, Any]] = []
        for group in groups.values():
            group["performance_rows"] = sorted(
                group["performance_rows"],
                key=lambda row: parse_int(row.get("season_year")) or 0,
            )
            summary.append(
                {
                    "season_year": int(group["season_year"]),
                    "team_code": str(group["team_code"]),
                    "team_name": str(group["team_name"]),
                    "confidence_current": str(group["confidence_current"]),
                    "confidence_change": str(group["confidence_change"]),
                    "season_goal_set": str(group["season_goal_set"]),
                    "season_goal_achieved": str(group["season_goal_achieved"]),
                    "performance_count": len(group["performance_rows"]),
                    "performance_rows": group["performance_rows"],
                }
            )
        return sorted(summary, key=lambda row: (int(row["season_year"]), str(row["team_code"])))

    def _owner_performance_rows_from_json(self, value: Any) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        rows: List[Dict[str, Any]] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            season_year = parse_int(raw.get("season_year"))
            wins = parse_int(raw.get("wins"))
            losses = parse_int(raw.get("losses"))
            result = str(raw.get("result") or "").strip()[:80]
            if season_year is None:
                continue
            rows.append(
                {
                    "season_year": season_year,
                    "wins": "" if wins is None else wins,
                    "losses": "" if losses is None else losses,
                    "result": result,
                }
            )
        return rows

    def _normalize_owner_performance_rows(self, rows: Any, season_year: int) -> List[Dict[str, Any]]:
        raw_rows = rows if isinstance(rows, list) else []
        normalized: List[Dict[str, Any]] = []
        for idx in range(5):
            raw = raw_rows[idx] if idx < len(raw_rows) and isinstance(raw_rows[idx], dict) else {}
            fallback_year = int(season_year) - 4 + idx
            row_year = parse_int(raw.get("season_year")) or fallback_year
            wins = parse_int(raw.get("wins"))
            losses = parse_int(raw.get("losses"))
            result = str(raw.get("result") or "").strip()[:80]
            normalized.append(
                {
                    "season_year": max(2000, min(2100, row_year)),
                    "wins": "" if wins is None else max(0, min(100, wins)),
                    "losses": "" if losses is None else max(0, min(100, losses)),
                    "result": result,
                }
            )
        return normalized


    def preview_owner_office_csv(self, csv_text: str) -> Dict[str, Any]:
            text = str(csv_text or "").lstrip("\ufeff")
            if not text.strip():
                return {"ok": False, "errors": [{"line": None, "message": "El CSV está vacío."}], "records": [], "summary": []}
            with self._repository.transaction() as conn:
                teams_by_code = self._repository.teams_by_code(conn)
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
                            "season": self._owner_office_import_header_value(row, aliases["season"]),
                            "team": self._owner_office_import_header_value(row, aliases["team"]),
                            "confidence_current": self._owner_office_import_header_value(row, aliases["confidence_current"]),
                            "confidence_change": self._owner_office_import_header_value(row, aliases["confidence_change"]),
                            "season_goal_set": self._owner_office_import_header_value(row, aliases["season_goal_set"]),
                            "season_goal_achieved": self._owner_office_import_header_value(row, aliases["season_goal_achieved"]),
                            "history_season": self._owner_office_import_header_value(row, aliases["history_season"]),
                            "wins": self._owner_office_import_header_value(row, aliases["wins"]),
                            "losses": self._owner_office_import_header_value(row, aliases["losses"]),
                            "result": self._owner_office_import_header_value(row, aliases["result"]),
                        }
                    )
            except csv.Error as err:
                errors.append({"line": None, "message": f"No se pudo leer el CSV: {err}"})
            records, record_errors = self._owner_office_import_normalize_records(raw_records, teams_by_code)
            errors.extend(record_errors)
            if not records and not errors:
                errors.append({"line": None, "message": "No se encontraron filas importables."})
            return {
                "ok": not errors,
                "errors": errors,
                "records": records,
                "summary": self._owner_office_import_group_records(records),
                "objective_options": self._objective_options,
            }

    def apply_owner_office_import(self, records_payload: Any) -> Dict[str, Any]:
            if not isinstance(records_payload, list):
                raise ValueError("records_required")
            with self._repository.transaction() as conn:
                teams_by_code = self._repository.teams_by_code(conn)
                records, errors = self._owner_office_import_normalize_records(records_payload, teams_by_code)
                if errors:
                    err = ValueError("invalid_records")
                    setattr(err, "errors", errors)
                    raise err
                grouped = self._owner_office_import_group_records(records)
                timestamp = self._now()
                for group in grouped:
                    team = teams_by_code[str(group["team_code"])]
                    team_id = int(team["id"])
                    season_year = int(group["season_year"])
                    existing = self._repository.owner_office_row(conn, team_id, season_year)
                    confidence_current = str(group.get("confidence_current") or "").strip()
                    confidence_change = str(group.get("confidence_change") or "").strip()
                    season_goal_set = str(group.get("season_goal_set") or "").strip()
                    season_goal_achieved = str(group.get("season_goal_achieved") or "").strip()
                    performance_rows = group.get("performance_rows") if isinstance(group.get("performance_rows"), list) else []
                    normalized_performance_rows = (
                        self._normalize_owner_performance_rows(performance_rows, season_year)
                        if performance_rows
                        else (
                            self._owner_performance_rows_from_json(existing["performance_json"])
                            if existing else self._normalize_owner_performance_rows([], season_year)
                        )
                    )
                    self._repository.upsert_owner_office(
                        conn,
                        team_id=team_id,
                        season_year=season_year,
                        confidence_current=confidence_current or (str(existing["confidence_current"] or "") if existing else ""),
                        confidence_change=confidence_change or (str(existing["confidence_change"] or "") if existing else ""),
                        season_goal_set=season_goal_set or (str(existing["season_goal_set"] or "") if existing else ""),
                        season_goal_achieved=season_goal_achieved or (str(existing["season_goal_achieved"] or "") if existing else ""),
                        revenue=str(existing["revenue"]) if existing and existing["revenue"] is not None else None,
                        expenses=str(existing["expenses"]) if existing and existing["expenses"] is not None else None,
                        balance=str(existing["balance"]) if existing and existing["balance"] is not None else None,
                        income_json=str(existing["income_json"]) if existing and existing["income_json"] else "[]",
                        expenses_json=str(existing["expenses_json"]) if existing and existing["expenses_json"] else "[]",
                        performance_json=json.dumps(normalized_performance_rows, ensure_ascii=True),
                        updated_at=timestamp,
                    )
            return {
                "ok": True,
                "record_count": len(records),
                "group_count": len(grouped),
                "seasons": sorted({int(row["season_year"]) for row in grouped}),
                "summary": grouped,
            }
