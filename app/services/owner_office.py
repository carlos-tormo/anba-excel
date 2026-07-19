"""Owner-office aggregate reads and transactional updates."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain_rules import parse_amount_like, parse_bool, parse_int
except ImportError:  # pragma: no cover
    from domain_rules import parse_amount_like, parse_bool, parse_int


@dataclass(frozen=True)
class OwnerOfficeOperations:
    profile_from_row: Callable[..., Dict[str, Any]]
    normalize_profile: Callable[[Any], Optional[Dict[str, Any]]]
    exit_interview_from_row: Callable[[Any], Optional[Dict[str, Any]]]
    rows_from_json: Callable[..., List[Dict[str, Any]]]
    normalize_rows: Callable[..., List[Dict[str, Any]]]
    breakdown_total: Callable[..., Optional[float]]
    performance_from_json: Callable[[Any], List[Dict[str, Any]]]
    normalize_performance: Callable[..., List[Dict[str, Any]]]
    normalize_objective: Callable[[Any], str]
    objective_evaluation: Callable[[Any, Any], str]
    format_value: Callable[[Any], str]


class OwnerOfficeService:
    def __init__(
        self,
        db: Any,
        operations: OwnerOfficeOperations,
        *,
        now: Callable[[], str],
        min_year: int,
        max_year: int,
        forecast_window: int,
    ) -> None:
        self._db = db
        self._operations = operations
        self._now = now
        self._min_year = min_year
        self._max_year = max_year
        self._forecast_window = forecast_window

    def get(self, code: str, include_private: bool = False) -> Optional[Dict[str, Any]]:
        with self._db.connect() as conn:
            team = conn.execute("SELECT id, code, name FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings")}
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < self._min_year or current_year > self._max_year:
                current_year = 2025
            free_agency_mode = parse_bool(settings.get("free_agency_mode"))
            team_id = int(team["id"])
            profile_row = conn.execute("SELECT * FROM team_owner_profiles WHERE team_id = ?", (team_id,)).fetchone()
            saved_rows = conn.execute(
                "SELECT * FROM team_owner_office WHERE team_id = ? ORDER BY season_year", (team_id,)
            ).fetchall()
            interview_rows = conn.execute(
                "SELECT * FROM owner_exit_interviews WHERE team_id = ?", (team_id,)
            ).fetchall()
            years = {
                *range(current_year, current_year + self._forecast_window),
                *(int(row["season_year"]) for row in saved_rows),
                *(int(row["season_year"]) for row in interview_rows),
                *(int(row["season_year"]) for row in conn.execute("SELECT DISTINCT season_year FROM team_economy")),
            }
            saved_by_year = {int(row["season_year"]): row for row in saved_rows}
            interviews_by_year = {
                int(row["season_year"]): self._operations.exit_interview_from_row(row)
                for row in interview_rows
            }
            entries: Dict[str, Dict[str, Any]] = {}
            for year in sorted(years):
                economy = conn.execute(
                    """SELECT COALESCE(balance, 0) AS balance, COALESCE(revenue, 0) AS revenue,
                              COALESCE(expenses, 0) AS expenses
                       FROM team_economy WHERE team_id = ? AND season_year = ?""",
                    (team_id, year),
                ).fetchone()
                economy_balance = float(economy["balance"] or 0) if economy else 0.0
                economy_revenue = float(economy["revenue"] or 0) if economy else 0.0
                economy_expenses = float(economy["expenses"] or 0) if economy else 0.0
                rank_rows = conn.execute(
                    """SELECT t.id, COALESCE(e.balance, 0) AS balance FROM teams t
                       LEFT JOIN team_economy e ON e.team_id = t.id AND e.season_year = ?
                       ORDER BY COALESCE(e.balance, 0) DESC, t.code ASC""",
                    (year,),
                ).fetchall()
                balance_rank = next((index + 1 for index, row in enumerate(rank_rows) if int(row["id"]) == team_id), None)
                confidence_rows = []
                for row in conn.execute(
                    """SELECT t.id, t.code, o.confidence_current FROM teams t
                       JOIN team_owner_office o ON o.team_id = t.id AND o.season_year = ?
                       WHERE TRIM(COALESCE(o.confidence_current, '')) <> ''""",
                    (year,),
                ).fetchall():
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
                income_rows = self._operations.rows_from_json(saved["income_json"], "income") if saved else []
                expenses_rows = self._operations.rows_from_json(saved["expenses_json"], "expenses") if saved else []
                income_total = self._operations.breakdown_total("income", income_rows)
                expenses_total = self._operations.breakdown_total("expenses", expenses_rows)
                revenue = self._operations.format_value(income_total) if income_total is not None else (
                    str(saved["revenue"]) if saved and saved["revenue"] is not None else economy_revenue
                )
                expenses = self._operations.format_value(expenses_total) if expenses_total is not None else (
                    str(saved["expenses"]) if saved and saved["expenses"] is not None else economy_expenses
                )
                if income_total is not None or expenses_total is not None:
                    balance = self._operations.format_value(
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
                    "season_goal_set": self._operations.normalize_objective(saved["season_goal_set"]) if saved else "",
                    "season_goal_achieved": self._operations.normalize_objective(saved["season_goal_achieved"]) if saved else "",
                    "season_goal_evaluation": self._operations.objective_evaluation(
                        saved["season_goal_set"] if saved else "", saved["season_goal_achieved"] if saved else ""
                    ),
                    "revenue": revenue, "expenses": expenses, "balance": balance,
                    "balance_rank": balance_rank, "balance_rank_total": len(rank_rows),
                    "income_rows": income_rows, "expenses_rows": expenses_rows,
                    "performance_rows": self._operations.performance_from_json(saved["performance_json"])
                    if saved else self._operations.normalize_performance([], year),
                    "exit_interview": interview,
                    "updated_at": str(saved["updated_at"] or "") if saved else "",
                }
            return {
                "team_code": str(team["code"]), "team_name": str(team["name"]),
                "current_year": current_year, "free_agency_mode": free_agency_mode,
                "exit_interview_season": current_year,
                "owner_profile": self._operations.profile_from_row(profile_row, include_private=include_private),
                "seasons": sorted(years), "entries": entries,
            }

    def update(self, code: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        season_year = parse_int(payload.get("season_year"))
        if season_year is None or season_year < 2000 or season_year > 2100:
            raise ValueError("invalid_season_year")
        with self._db.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            team_id = int(team["id"])
            timestamp = self._now()
            profile = self._operations.normalize_profile(payload.get("owner_profile"))
            if profile is not None:
                conn.execute(
                    """INSERT INTO team_owner_profiles (
                           team_id, owner_name, owner_birth_date, owner_photo_url, owner_bio,
                           ambicion_competitiva, paciencia, intervencionismo,
                           orientacion_financiera, orientacion_marca, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(team_id) DO UPDATE SET owner_name = excluded.owner_name,
                           owner_birth_date = excluded.owner_birth_date, owner_photo_url = excluded.owner_photo_url,
                           owner_bio = excluded.owner_bio, ambicion_competitiva = excluded.ambicion_competitiva,
                           paciencia = excluded.paciencia, intervencionismo = excluded.intervencionismo,
                           orientacion_financiera = excluded.orientacion_financiera,
                           orientacion_marca = excluded.orientacion_marca, updated_at = excluded.updated_at""",
                    (team_id, profile["owner_name"], profile["owner_birth_date"], profile["owner_photo_url"],
                     profile["owner_bio"], profile["ambicion_competitiva"], profile["paciencia"],
                     profile["intervencionismo"], profile["orientacion_financiera"],
                     profile["orientacion_marca"], timestamp),
                )
            income_rows = self._operations.normalize_rows(payload.get("income_rows"), "income")
            expense_rows = self._operations.normalize_rows(payload.get("expenses_rows"), "expenses")
            income_total = self._operations.breakdown_total("income", income_rows)
            expense_total = self._operations.breakdown_total("expenses", expense_rows)
            revenue = self._operations.format_value(income_total) if income_total is not None else str(payload.get("revenue") or "").strip()
            expenses = self._operations.format_value(expense_total) if expense_total is not None else str(payload.get("expenses") or "").strip()
            balance = self._operations.format_value((parse_amount_like(revenue) or 0.0) + (parse_amount_like(expenses) or 0.0)) \
                if income_total is not None or expense_total is not None else str(payload.get("balance") or "").strip()
            conn.execute(
                """INSERT INTO team_owner_office (
                       team_id, season_year, confidence_current, confidence_change,
                       new_gm_after_dismissal, gm_midseason_arrival, season_goal_set,
                       season_goal_achieved, revenue, expenses, balance, income_json,
                       expenses_json, performance_json, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(team_id, season_year) DO UPDATE SET
                       confidence_current = excluded.confidence_current,
                       confidence_change = excluded.confidence_change,
                       new_gm_after_dismissal = excluded.new_gm_after_dismissal,
                       gm_midseason_arrival = excluded.gm_midseason_arrival,
                       season_goal_set = excluded.season_goal_set,
                       season_goal_achieved = excluded.season_goal_achieved,
                       revenue = excluded.revenue, expenses = excluded.expenses,
                       balance = excluded.balance, income_json = excluded.income_json,
                       expenses_json = excluded.expenses_json, performance_json = excluded.performance_json,
                       updated_at = excluded.updated_at""",
                (team_id, season_year, str(payload.get("confidence_current") or "").strip(),
                 str(payload.get("confidence_change") or "").strip(),
                 1 if parse_bool(payload.get("new_gm_after_dismissal")) else 0,
                 1 if parse_bool(payload.get("gm_midseason_arrival")) else 0,
                 self._operations.normalize_objective(payload.get("season_goal_set")),
                 self._operations.normalize_objective(payload.get("season_goal_achieved")),
                 revenue, expenses, balance, json.dumps(income_rows, ensure_ascii=True),
                 json.dumps(expense_rows, ensure_ascii=True),
                 json.dumps(self._operations.normalize_performance(payload.get("performance_rows"), season_year), ensure_ascii=True),
                 timestamp),
            )
            conn.commit()
        return self.get(code, include_private=True)
