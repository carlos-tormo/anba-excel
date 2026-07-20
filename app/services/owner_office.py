"""Owner-office aggregate reads and transactional updates."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

try:
    from ..domain_rules import parse_amount_like, parse_bool, parse_int
except ImportError:  # pragma: no cover
    from domain_rules import parse_amount_like, parse_bool, parse_int


def sanitize_http_image_url(value: Any, limit: int = 1000) -> str:
    raw = str(value or "").strip()[:limit]
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def sanitize_owner_background_url(value: Any, limit: int = 1000) -> str:
    raw = str(value or "").strip()[:limit]
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return ""
    if not re.fullmatch(r"/api/teams/[A-Z0-9]{2,4}/owner-office/background-image", parsed.path or ""):
        return ""
    return raw


class OwnerExitInterviewError(ValueError):
    """Expected owner exit-interview workflow failure."""

    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


class OwnerOfficeService:
    def __init__(
        self,
        repository: Any,
        *,
        now: Callable[[], str],
        min_year: int,
        max_year: int,
        forecast_window: int,
        objective_options: List[str],
        interview_composer: Optional[Any] = None,
    ) -> None:
        self._repository = repository
        self._now = now
        self._min_year = min_year
        self._max_year = max_year
        self._forecast_window = forecast_window
        self._objective_options = list(objective_options)
        self._interview_composer = interview_composer

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
    def _owner_import_value_text(self, value: Any) -> str:
        if value is None or str(value).strip() == "":
            return ""
        amount = float(value or 0)
        rounded = round(amount)
        if abs(amount - rounded) < 0.000001:
            return str(int(rounded))
        return f"{amount:.2f}".rstrip("0").rstrip(".")

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

    def _normalize_owner_season_objective(self, value: Any) -> str:
        text = str(value or "").strip()
        return text if text in self._objective_options else ""

    def _owner_season_objective_evaluation(self, target: Any, achieved: Any) -> str:
        target_text = self._normalize_owner_season_objective(target)
        achieved_text = self._normalize_owner_season_objective(achieved)
        if not target_text or not achieved_text:
            return "No evaluable"
        target_rank = self._objective_options.index(target_text)
        achieved_rank = self._objective_options.index(achieved_text)
        difference = achieved_rank - target_rank
        if difference < 0:
            return f"Objetivo superado por {abs(difference)} nivel(es)"
        if difference == 0:
            return "Objetivo cumplido"
        return f"Objetivo no cumplido por {difference} nivel(es)"

    def _owner_attribute_value(self, value: Any) -> Optional[int]:
        parsed = parse_int(value)
        if parsed is None:
            return None
        return max(1, min(10, parsed))

    def _owner_profile_from_row(self, row: Optional[Dict[str, Any]], include_private: bool = False) -> Dict[str, Any]:
        profile: Dict[str, Any] = {
            "owner_name": "",
            "owner_birth_date": "",
            "owner_photo_url": "",
            "owner_office_background_url": "",
            "owner_bio": "",
        }
        if row:
            profile.update(
                {
                    "owner_name": str(row["owner_name"] or ""),
                    "owner_birth_date": str(row["owner_birth_date"] or ""),
                    "owner_photo_url": sanitize_http_image_url(row["owner_photo_url"]),
                    "owner_office_background_url": sanitize_owner_background_url(row["owner_office_background_url"]),
                    "owner_bio": str(row["owner_bio"] or ""),
                }
            )
        if include_private:
            profile["attributes"] = {
                "ambicion_competitiva": self._owner_attribute_value(row["ambicion_competitiva"]) if row else None,
                "paciencia": self._owner_attribute_value(row["paciencia"]) if row else None,
                "intervencionismo": self._owner_attribute_value(row["intervencionismo"]) if row else None,
                "orientacion_financiera": self._owner_attribute_value(row["orientacion_financiera"]) if row else None,
                "orientacion_marca": self._owner_attribute_value(row["orientacion_marca"]) if row else None,
            }
        return profile

    def _normalize_owner_profile_payload(self, payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None

        def text_value(key: str, limit: int) -> str:
            return str(payload.get(key) or "").strip()[:limit]

        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        return {
            "owner_name": text_value("owner_name", 120),
            "owner_birth_date": text_value("owner_birth_date", 32),
            "owner_photo_url": sanitize_http_image_url(text_value("owner_photo_url", 1000)),
            "owner_bio": text_value("owner_bio", 2000),
            "ambicion_competitiva": self._owner_attribute_value(attributes.get("ambicion_competitiva")),
            "paciencia": self._owner_attribute_value(attributes.get("paciencia")),
            "intervencionismo": self._owner_attribute_value(attributes.get("intervencionismo")),
            "orientacion_financiera": self._owner_attribute_value(attributes.get("orientacion_financiera")),
            "orientacion_marca": self._owner_attribute_value(attributes.get("orientacion_marca")),
        }

    def _owner_exit_interview_from_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "team_id": int(row["team_id"]),
            "season_year": int(row["season_year"]),
            "gm_email": str(row["gm_email"] or ""),
            "gm_name": str(row["gm_name"] or ""),
            "status": str(row["status"] or "available"),
            "owner_message": str(row["owner_message"] or ""),
            "gm_response": str(row["gm_response"] or ""),
            "owner_final_message": str(row["owner_final_message"] or ""),
            "owner_conclusion_message": str(row["owner_conclusion_message"] or ""),
            "trust_delta": parse_int(row["trust_delta"]),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
        }

    def get(self, code: str, include_private: bool = False) -> Optional[Dict[str, Any]]:
        with self._repository.transaction() as conn:
            team = self._repository.team(conn, code)
            if not team:
                return None
            settings = self._repository.settings(conn)
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < self._min_year or current_year > self._max_year:
                current_year = 2025
            free_agency_mode = parse_bool(settings.get("free_agency_mode"))
            team_id = int(team["id"])
            profile_row = self._repository.profile(conn, team_id)
            saved_rows = self._repository.office_rows(conn, team_id)
            interview_rows = self._repository.exit_interview_rows(conn, team_id)
            years = {
                *range(current_year, current_year + self._forecast_window),
                *(int(row["season_year"]) for row in saved_rows),
                *(int(row["season_year"]) for row in interview_rows),
                *self._repository.economy_years(conn),
            }
            saved_by_year = {int(row["season_year"]): row for row in saved_rows}
            interviews_by_year = {
                int(row["season_year"]): self._owner_exit_interview_from_row(row)
                for row in interview_rows
            }
            entries: Dict[str, Dict[str, Any]] = {}
            for year in sorted(years):
                economy = self._repository.economy(conn, team_id, year)
                economy_balance = float(economy["balance"] or 0) if economy else 0.0
                economy_revenue = float(economy["revenue"] or 0) if economy else 0.0
                economy_expenses = float(economy["expenses"] or 0) if economy else 0.0
                rank_rows = self._repository.balance_ranking(conn, year)
                balance_rank = next((index + 1 for index, row in enumerate(rank_rows) if int(row["id"]) == team_id), None)
                confidence_rows = []
                for row in self._repository.confidence_ranking(conn, year):
                    value = parse_amount_like(row["confidence_current"])
                    if value is not None:
                        confidence_rows.append({"id": int(row["id"]), "code": str(row["code"]), "confidence": float(value)})
                confidence_rows.sort(key=lambda row: (-row["confidence"], row["code"]))
                confidence_rank = next((index + 1 for index, row in enumerate(confidence_rows) if row["id"] == team_id), None)
                saved = saved_by_year.get(year)
                interview = interviews_by_year.get(year)
                if not interview and free_agency_mode and year == current_year:
                    interview = {
                        "season_year": year, "status": "available", "owner_message": "",
                        "gm_response": "", "owner_final_message": "", "owner_conclusion_message": "",
                        "trust_delta": None,
                    }
                income_rows = self._owner_office_rows_from_json(saved["income_json"], "income") if saved else []
                expenses_rows = self._owner_office_rows_from_json(saved["expenses_json"], "expenses") if saved else []
                income_total = self._owner_office_breakdown_total("income", income_rows)
                expenses_total = self._owner_office_breakdown_total("expenses", expenses_rows)
                revenue = self._owner_import_value_text(income_total) if income_total is not None else (
                    str(saved["revenue"]) if saved and saved["revenue"] is not None else economy_revenue
                )
                expenses = self._owner_import_value_text(expenses_total) if expenses_total is not None else (
                    str(saved["expenses"]) if saved and saved["expenses"] is not None else economy_expenses
                )
                if income_total is not None or expenses_total is not None:
                    balance = self._owner_import_value_text(
                        (parse_amount_like(revenue) or 0.0) + (parse_amount_like(expenses) or 0.0)
                    )
                else:
                    balance = str(saved["balance"]) if saved and saved["balance"] is not None else economy_balance
                entries[str(year)] = {
                    "season_year": year,
                    "confidence_current": str(saved["confidence_current"] or "") if saved else "",
                    "confidence_change": str(saved["confidence_change"] or "") if saved else "",
                    "confidence_rank": confidence_rank,
                    "confidence_rank_total": len(confidence_rows),
                    "new_gm_after_dismissal": parse_bool(saved["new_gm_after_dismissal"]) if saved else False,
                    "gm_midseason_arrival": parse_bool(saved["gm_midseason_arrival"]) if saved else False,
                    "season_goal_set": self._normalize_owner_season_objective(saved["season_goal_set"]) if saved else "",
                    "season_goal_achieved": self._normalize_owner_season_objective(saved["season_goal_achieved"]) if saved else "",
                    "season_goal_evaluation": self._owner_season_objective_evaluation(
                        saved["season_goal_set"] if saved else "", saved["season_goal_achieved"] if saved else ""
                    ),
                    "revenue": revenue, "expenses": expenses, "balance": balance,
                    "balance_rank": balance_rank, "balance_rank_total": len(rank_rows),
                    "income_rows": income_rows, "expenses_rows": expenses_rows,
                    "performance_rows": self._owner_performance_rows_from_json(saved["performance_json"])
                    if saved else self._normalize_owner_performance_rows([], year),
                    "exit_interview": interview,
                    "updated_at": str(saved["updated_at"] or "") if saved else "",
                }
            return {
                "team_code": str(team["code"]), "team_name": str(team["name"]),
                "current_year": current_year, "free_agency_mode": free_agency_mode,
                "exit_interview_season": current_year,
                "owner_profile": self._owner_profile_from_row(profile_row, include_private=include_private),
                "seasons": sorted(years), "entries": entries,
            }

    def update(self, code: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        season_year = parse_int(payload.get("season_year"))
        if season_year is None or season_year < 2000 or season_year > 2100:
            raise ValueError("invalid_season_year")
        with self._repository.transaction() as conn:
            team = self._repository.team(conn, code)
            if not team:
                return None
            team_id = int(team["id"])
            timestamp = self._now()
            profile = self._normalize_owner_profile_payload(payload.get("owner_profile"))
            if profile is not None:
                self._repository.upsert_profile(conn, team_id, profile, timestamp)
            income_rows = self._normalize_owner_office_rows(payload.get("income_rows"), "income")
            expense_rows = self._normalize_owner_office_rows(payload.get("expenses_rows"), "expenses")
            income_total = self._owner_office_breakdown_total("income", income_rows)
            expense_total = self._owner_office_breakdown_total("expenses", expense_rows)
            revenue = self._owner_import_value_text(income_total) if income_total is not None else str(payload.get("revenue") or "").strip()
            expenses = self._owner_import_value_text(expense_total) if expense_total is not None else str(payload.get("expenses") or "").strip()
            balance = self._owner_import_value_text((parse_amount_like(revenue) or 0.0) + (parse_amount_like(expenses) or 0.0)) \
                if income_total is not None or expense_total is not None else str(payload.get("balance") or "").strip()
            self._repository.upsert_office_entry(
                conn,
                {
                    "team_id": team_id,
                    "season_year": season_year,
                    "confidence_current": str(payload.get("confidence_current") or "").strip(),
                    "confidence_change": str(payload.get("confidence_change") or "").strip(),
                    "new_gm_after_dismissal": 1 if parse_bool(payload.get("new_gm_after_dismissal")) else 0,
                    "gm_midseason_arrival": 1 if parse_bool(payload.get("gm_midseason_arrival")) else 0,
                    "season_goal_set": self._normalize_owner_season_objective(payload.get("season_goal_set")),
                    "season_goal_achieved": self._normalize_owner_season_objective(payload.get("season_goal_achieved")),
                    "revenue": revenue,
                    "expenses": expenses,
                    "balance": balance,
                    "income_json": json.dumps(income_rows, ensure_ascii=True),
                    "expenses_json": json.dumps(expense_rows, ensure_ascii=True),
                    "performance_json": json.dumps(
                        self._normalize_owner_performance_rows(payload.get("performance_rows"), season_year),
                        ensure_ascii=True,
                    ),
                    "updated_at": timestamp,
                },
            )
        return self.get(code, include_private=True)

    def update_background_url(self, code: str, background_url: str) -> Optional[Dict[str, Any]]:
        if not self._repository.update_owner_background_url(code, background_url):
            return None
        return self.get(code, include_private=True)

    def update_background_image(
        self,
        code: str,
        file_bytes: bytes,
        mime_type: str,
    ) -> Optional[Dict[str, Any]]:
        if not self._repository.update_owner_background_image(code, file_bytes, mime_type):
            return None
        return self.get(code, include_private=True)

    def get_background_image(self, code: str) -> Optional[tuple[bytes, str]]:
        return self._repository.get_owner_background_image(code)

    def _exit_interview_context(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        with self._repository.transaction() as conn:
            settings = self._repository.settings(conn)
        current_year = parse_int(settings.get("current_year")) or 2025
        season_year = parse_int(payload.get("season_year")) or current_year
        if season_year != current_year:
            raise OwnerExitInterviewError(
                "invalid_exit_interview_season",
                season_year=current_year,
            )
        return settings, season_year

    def _start_exit_interview(
        self,
        code: str,
        season_year: int,
        session: Dict[str, Any],
        owner_office: Dict[str, Any],
        include_private: bool,
    ) -> Dict[str, Any]:
        existing = self._repository.get_owner_exit_interview(code, season_year)
        owner_message = str(existing.get("owner_message") or "").strip() if existing else ""
        if not owner_message:
            if self._interview_composer is None:
                raise RuntimeError("owner_interview_composer_required")
            owner_message = self._interview_composer.opening_message(
                owner_office,
                season_year,
                session=session,
            )
        interview = self._repository.start_owner_exit_interview(
            code,
            season_year,
            session,
            owner_message,
        )
        if not interview:
            raise OwnerExitInterviewError("team_not_found")
        return {
            "ok": True,
            "interview": interview,
            "owner_office": self.get(code, include_private=include_private),
        }

    def _complete_exit_interview(
        self,
        code: str,
        season_year: int,
        payload: Dict[str, Any],
        session: Dict[str, Any],
        owner_office: Dict[str, Any],
        include_private: bool,
    ) -> Dict[str, Any]:
        gm_response = str(payload.get("gm_response") or "").strip()
        if not gm_response:
            raise OwnerExitInterviewError("gm_response_required")
        if len(gm_response) > 4000:
            raise OwnerExitInterviewError("gm_response_too_long")
        existing = self._repository.get_owner_exit_interview(code, season_year)
        if not existing or not str(existing.get("owner_message") or "").strip():
            raise OwnerExitInterviewError("interview_not_started")
        if str(existing.get("status") or "").lower() == "completed":
            return {"ok": True, "interview": existing}
        if self._interview_composer is None:
            raise RuntimeError("owner_interview_composer_required")
        final_message, conclusion_message, trust_delta = self._interview_composer.final_reply(
            owner_office,
            season_year,
            str(existing.get("owner_message") or ""),
            gm_response,
            session=session,
        )
        interview = self._repository.complete_owner_exit_interview(
            code,
            season_year,
            session,
            gm_response,
            final_message,
            conclusion_message,
            trust_delta,
        )
        if not interview:
            raise OwnerExitInterviewError("interview_not_found")
        return {
            "ok": True,
            "interview": interview,
            "owner_office": self.get(code, include_private=include_private),
        }

    def update_exit_interview(
        self,
        code: str,
        action: str,
        payload: Dict[str, Any],
        session: Dict[str, Any],
        *,
        include_private: bool,
    ) -> Dict[str, Any]:
        settings, season_year = self._exit_interview_context(payload)
        if action == "reset":
            if not self._repository.reset_owner_exit_interview(code, season_year):
                raise OwnerExitInterviewError("team_not_found")
            return {
                "response": {
                    "ok": True,
                    "owner_office": self.get(code, include_private=True),
                },
                "audit": {
                    "action": "reset",
                    "entity": "owner_exit_interview",
                    "entity_id": f"{code.upper()}:{season_year}",
                    "team_code": code.upper(),
                    "details": {"season_year": season_year},
                },
            }
        if not parse_bool(settings.get("free_agency_mode")):
            raise OwnerExitInterviewError("free_agency_mode_required")
        owner_office = self.get(code, include_private=True)
        if not owner_office:
            raise OwnerExitInterviewError("team_not_found")
        if action == "start":
            response = self._start_exit_interview(
                code,
                season_year,
                session,
                owner_office,
                include_private,
            )
        else:
            response = self._complete_exit_interview(
                code,
                season_year,
                payload,
                session,
                owner_office,
                include_private,
            )
        return {"response": response}
