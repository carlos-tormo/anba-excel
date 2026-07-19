"""SQLite persistence for teams and season-specific team state."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain.exceptions import normalize_apron_hard_cap
    from ...domain_rules import parse_int
except ImportError:  # pragma: no cover
    from domain.exceptions import normalize_apron_hard_cap
    from domain_rules import parse_int

from .base import LeagueRepository


class TeamRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        normalize_gm_start_date: Callable[[Any], Optional[str]],
        normalize_hex_color: Callable[[Any], Optional[str]],
    ) -> None:
        super().__init__(db)
        self._now = now
        self._normalize_gm_start_date = normalize_gm_start_date
        self._normalize_hex_color = normalize_hex_color

    def list(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT id, code, name, gm, apron_hard_cap FROM teams ORDER BY code"
            ).fetchall()]

    @staticmethod
    def select_frozen_draft_picks(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """SELECT f.*, t.code AS team_code, t.name AS team_name
               FROM frozen_draft_picks f JOIN teams t ON t.id = f.team_id
               WHERE f.team_id = ? ORDER BY f.draft_year, f.penalty_season_year, f.id""",
            (team_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_gm_history(self, code: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        with self.db.connect() as conn:
            params: List[Any] = []
            where = ""
            if code:
                normalized_code = code.upper()
                if not conn.execute("SELECT 1 FROM teams WHERE code = ?", (normalized_code,)).fetchone():
                    return None
                where = "WHERE t.code = ?"
                params.append(normalized_code)
            rows = conn.execute(
                f"""SELECT h.id, t.code AS team_code, t.name AS team_name, h.row_order,
                           h.gm_name, h.start_date, h.color, h.created_at, h.updated_at
                    FROM team_gm_history h JOIN teams t ON t.id = h.team_id
                    {where} ORDER BY t.code, h.start_date, h.row_order, h.id""",
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def replace_gm_history(self, code: str, entries: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        normalized: List[Dict[str, Any]] = []
        for raw in entries:
            gm_name = str(raw.get("gm_name") or raw.get("name") or "").strip()
            start_date = self._normalize_gm_start_date(raw.get("start_date"))
            if not gm_name or not start_date:
                raise ValueError("invalid_gm_history_entry")
            normalized.append({
                "gm_name": gm_name,
                "start_date": start_date,
                "color": self._normalize_hex_color(raw.get("color")),
            })
        normalized.sort(key=lambda row: (row["start_date"], row["gm_name"].lower()))
        with self.db.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            team_id = int(team["id"])
            timestamp = self._now()
            conn.execute("DELETE FROM team_gm_history WHERE team_id = ?", (team_id,))
            conn.executemany(
                """INSERT INTO team_gm_history (
                       team_id, row_order, gm_name, start_date, color, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (team_id, index, entry["gm_name"], entry["start_date"], entry["color"], timestamp, timestamp)
                    for index, entry in enumerate(normalized, start=1)
                ],
            )
            conn.commit()
        return self.list_gm_history(code)

    def update_fields(self, code: str, payload: Dict[str, Any]) -> bool:
        assignments = []
        values: List[Any] = []
        if "gm" in payload:
            raw = payload.get("gm")
            assignments.append("gm = ?")
            values.append(None if raw is None else str(raw).strip() or None)
        for field in ("cash_received", "cash_sent"):
            if field in payload:
                assignments.append(f"{field} = ?")
                values.append(float(payload.get(field) or 0.0))
        if "apron_hard_cap" in payload:
            assignments.append("apron_hard_cap = ?")
            values.append(normalize_apron_hard_cap(payload.get("apron_hard_cap")))
        if not assignments:
            return False
        with self.db.connect() as conn:
            cur = conn.execute(
                f"UPDATE teams SET {', '.join(assignments)}, updated_at = ? WHERE code = ?",
                (*values, self._now(), code.upper()),
            )
            conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def luxury_history_conn(conn: Any, team_id: int, current_year: int) -> List[Dict[str, Any]]:
        years = [current_year, *[current_year - offset for offset in range(1, 5)]]
        placeholders = ",".join("?" for _ in years)
        rows = conn.execute(
            f"SELECT season_year, repeater FROM team_luxury_history WHERE team_id = ? AND season_year IN ({placeholders})",
            (team_id, *years),
        ).fetchall()
        by_year = {int(row["season_year"]): bool(row["repeater"]) for row in rows}
        return [{"season_year": year, "repeater": bool(by_year.get(year, False))} for year in years]

    @staticmethod
    def luxury_repeater_conn(conn: Any, team_id: int, season_year: int) -> bool:
        row = conn.execute(
            "SELECT repeater FROM team_luxury_history WHERE team_id = ? AND season_year = ?",
            (team_id, season_year),
        ).fetchone()
        return bool(row["repeater"]) if row else False

    def update_luxury_history(self, code: str, season_year: int, repeater: bool) -> bool:
        with self.db.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return False
            conn.execute(
                """INSERT INTO team_luxury_history (team_id, season_year, repeater, updated_at)
                   VALUES (?, ?, ?, ?) ON CONFLICT(team_id, season_year) DO UPDATE SET
                   repeater = excluded.repeater, updated_at = excluded.updated_at""",
                (int(team["id"]), int(season_year), 1 if repeater else 0, self._now()),
            )
            conn.commit()
            return True

    @staticmethod
    def hard_cap_conn(conn: Any, team_id: int, season_year: int, fallback: Any = None) -> str:
        row = conn.execute(
            "SELECT hard_cap FROM team_apron_hard_caps WHERE team_id = ? AND season_year = ?",
            (int(team_id), int(season_year)),
        ).fetchone()
        return normalize_apron_hard_cap(row["hard_cap"] if row else fallback) or ""

    @staticmethod
    def hard_caps_conn(conn: Any, team_id: int, current_year: int, fallback: Any = None) -> List[Dict[str, Any]]:
        years = [current_year + index for index in range(6)]
        placeholders = ",".join("?" for _ in years)
        rows = conn.execute(
            f"SELECT season_year, hard_cap FROM team_apron_hard_caps WHERE team_id = ? AND season_year IN ({placeholders})",
            (int(team_id), *years),
        ).fetchall()
        by_year = {int(row["season_year"]): normalize_apron_hard_cap(row["hard_cap"]) or "" for row in rows}
        return [{"season_year": year, "hard_cap": by_year.get(
            year, (normalize_apron_hard_cap(fallback) or "") if year == current_year else ""
        )} for year in years]

    def update_hard_cap_conn(self, conn: Any, code: str, season_year: int, hard_cap: Any) -> bool:
        normalized = normalize_apron_hard_cap(hard_cap)
        team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
        if not team:
            return False
        timestamp = self._now()
        conn.execute(
            """INSERT INTO team_apron_hard_caps (team_id, season_year, hard_cap, updated_at)
               VALUES (?, ?, ?, ?) ON CONFLICT(team_id, season_year) DO UPDATE SET
               hard_cap = excluded.hard_cap, updated_at = excluded.updated_at""",
            (int(team["id"]), int(season_year), normalized, timestamp),
        )
        settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings")}
        if int(season_year) == (parse_int(settings.get("current_year")) or 2025):
            conn.execute("UPDATE teams SET apron_hard_cap = ?, updated_at = ? WHERE id = ?",
                         (normalized, timestamp, int(team["id"])))
        return True

    def update_hard_cap(self, code: str, season_year: int, hard_cap: Any) -> bool:
        with self.db.transaction("IMMEDIATE") as conn:
            return self.update_hard_cap_conn(conn, code, season_year, hard_cap)
