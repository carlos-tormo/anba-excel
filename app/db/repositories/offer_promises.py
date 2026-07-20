"""Free-agent offer promise persistence and capacity rules."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Callable, Dict, List, Optional

try:
    from ...auth.policies import normalize_team_code
    from ...domain._values import parse_bool, parse_int, season_label
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_bool, parse_int, season_label

from .base import LeagueRepository


class OfferPromiseRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        role_limits: Dict[str, int],
        forecast_min_year: int,
    ) -> None:
        super().__init__(db)
        self._now = now
        self._role_limits = dict(role_limits)
        self._forecast_min_year = int(forecast_min_year)

    @staticmethod
    def _offer_promise_status(raw_status: Any) -> str:
        status = str(raw_status or "").strip().lower()
        aliases = {
            "pending": "pending",
            "pendiente": "pending",
            "fulfilled": "fulfilled",
            "cumplida": "fulfilled",
            "cumplido": "fulfilled",
            "broken": "broken",
            "incumplida": "broken",
            "incumplido": "broken",
        }
        if status not in aliases:
            raise ValueError("invalid_promise_status")
        return aliases[status]

    @staticmethod
    def _normalize_free_agent_promise_role(raw_role: Any) -> str:
        return re.sub(r"\s+", " ", str(raw_role or "").strip())

    def _free_agent_promise_role_limit(self, raw_role: Any) -> Optional[int]:
        return self._role_limits.get(self._normalize_free_agent_promise_role(raw_role))

    def _ensure_free_agent_promise_role_capacity_conn(
        self,
        conn: sqlite3.Connection,
        team_code: Any,
        season_year: Any,
        role: Any,
        exclude_promise_id: Optional[int] = None,
        bypass_role_limits: bool = False,
    ) -> None:
        if bypass_role_limits:
            return
        normalized_team = normalize_team_code(team_code)
        normalized_role = self._normalize_free_agent_promise_role(role)
        parsed_season = parse_int(season_year)
        limit = self._free_agent_promise_role_limit(normalized_role)
        if not normalized_team or parsed_season is None or limit is None:
            return
        params: List[Any] = [normalized_team, parsed_season, normalized_role]
        exclude_clause = ""
        if exclude_promise_id is not None:
            exclude_clause = " AND id <> ?"
            params.append(int(exclude_promise_id))
        cur = conn.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM free_agent_offer_promises
            WHERE UPPER(TRIM(team_code)) = ?
              AND season_year = ?
              AND role = ?
              AND status IN ('pending', 'fulfilled')
              {exclude_clause}
            """,
            params,
        )
        count = int(cur.fetchone()["total"] or 0)
        if count >= limit:
            raise ValueError(f"promise_role_limit_exceeded:{normalized_role}:{limit}")

    def ensure_free_agent_offer_request_promise_capacity(
        self,
        request_id: int,
        promise_context: Optional[Dict[str, Any]] = None,
        bypass_role_limits: bool = False,
    ) -> None:
        if bypass_role_limits:
            return
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT r.*, t.code AS team_code
                FROM gm_free_agent_offer_requests r
                JOIN teams t ON t.id = r.team_id
                WHERE r.id = ?
                """,
                (int(request_id),),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("request_not_found")
            payload = self._free_agent_offer_payload_from_request_row(row)
            role = self._normalize_free_agent_promise_role(payload.get("role"))
            if not role:
                return
            salary_by_season = payload.get("salary_by_season")
            if not isinstance(salary_by_season, dict):
                salary_by_season = {}
            seasons = sorted(
                season
                for season in (parse_int(key) for key in salary_by_season.keys())
                if season is not None
            )
            season_year = seasons[0] if seasons else None
            if season_year is None:
                context = promise_context or {}
                free_agent_context = context.get("free_agent") if isinstance(context.get("free_agent"), dict) else {}
                season_year = parse_int(free_agent_context.get("season_year"))
            self._ensure_free_agent_promise_role_capacity_conn(
                conn,
                row["team_code"],
                season_year,
                role,
            )

    @staticmethod
    def _free_agent_offer_payload_from_request_row(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            payload = json.loads(str(row["offer_payload_json"] or "{}"))
        except (KeyError, json.JSONDecodeError, TypeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _upsert_free_agent_offer_promise_for_request_conn(
        self,
        conn: sqlite3.Connection,
        request_id: int,
        admin: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        promise_context: Optional[Dict[str, Any]] = None,
        bypass_role_limits: bool = False,
    ) -> Optional[int]:
        timestamp = timestamp or self._now()
        cur = conn.execute(
            """
            SELECT
                r.*,
                f.name AS free_agent_name,
                f.profile_id AS free_agent_profile_id,
                f.agent AS free_agent_agent,
                t.code AS team_code,
                t.name AS team_name
            FROM gm_free_agent_offer_requests r
            LEFT JOIN free_agents f ON f.id = r.free_agent_id
            JOIN teams t ON t.id = r.team_id
            WHERE r.id = ? AND r.status = 'approved'
            """,
            (int(request_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        payload = self._free_agent_offer_payload_from_request_row(row)
        role = re.sub(r"\s+", " ", str(payload.get("role") or "").strip())
        if not role:
            return None

        context = promise_context or {}
        free_agent_context = context.get("free_agent") if isinstance(context.get("free_agent"), dict) else {}
        salary_by_season = payload.get("salary_by_season")
        if not isinstance(salary_by_season, dict):
            salary_by_season = {}
        seasons = sorted(
            season
            for season in (parse_int(key) for key in salary_by_season.keys())
            if season is not None
        )
        season_year = seasons[0] if seasons else None
        label = season_label(season_year) if season_year is not None else ""
        profile_id = (
            parse_int(payload.get("profile_id"))
            or parse_int(free_agent_context.get("profile_id"))
            or parse_int(row["free_agent_profile_id"])
        )
        player_name = (
            str(payload.get("player_name") or "").strip()
            or str(free_agent_context.get("name") or "").strip()
            or str(row["free_agent_name"] or "").strip()
            or "Agente libre"
        )
        agent_name = re.sub(
            r"\s+",
            " ",
            str(
                payload.get("agent_name")
                or payload.get("agent")
                or free_agent_context.get("agent")
                or row["free_agent_agent"]
                or ""
            ).strip(),
        )
        admin = admin or {}
        existing_promise = conn.execute(
            "SELECT id FROM free_agent_offer_promises WHERE gm_free_agent_offer_request_id = ?",
            (int(request_id),),
        ).fetchone()
        self._ensure_free_agent_promise_role_capacity_conn(
            conn,
            row["team_code"],
            season_year,
            role,
            exclude_promise_id=int(existing_promise["id"]) if existing_promise else None,
            bypass_role_limits=bypass_role_limits,
        )
        insert_cur = conn.execute(
            """
            INSERT INTO free_agent_offer_promises (
                gm_free_agent_offer_request_id,
                free_agent_id,
                profile_id,
                player_name,
                team_code,
                team_name,
                agent_name,
                season_year,
                season_label,
                role,
                offer_type,
                contract_type,
                status,
                admin_email,
                admin_name,
                created_at,
                updated_at,
                decided_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, NULL)
            ON CONFLICT(gm_free_agent_offer_request_id)
            DO UPDATE SET
                free_agent_id = excluded.free_agent_id,
                profile_id = excluded.profile_id,
                player_name = excluded.player_name,
                team_code = excluded.team_code,
                team_name = excluded.team_name,
                agent_name = excluded.agent_name,
                season_year = excluded.season_year,
                season_label = excluded.season_label,
                role = excluded.role,
                offer_type = excluded.offer_type,
                contract_type = excluded.contract_type,
                admin_email = excluded.admin_email,
                admin_name = excluded.admin_name,
                updated_at = excluded.updated_at
            """,
            (
                int(request_id),
                parse_int(row["free_agent_id"]),
                profile_id,
                player_name,
                normalize_team_code(row["team_code"]) or str(row["team_code"] or "").strip().upper(),
                str(row["team_name"] or "").strip(),
                agent_name,
                season_year,
                label,
                role,
                str(row["offer_type"] or "").strip().lower() or "free_agent_offer",
                str(payload.get("contract_type") or "").strip(),
                str(admin.get("email") or "").strip().lower() or None,
                str(admin.get("name") or "").strip() or None,
                timestamp,
                timestamp,
            ),
        )
        if insert_cur.lastrowid:
            return int(insert_cur.lastrowid)
        existing = conn.execute(
            "SELECT id FROM free_agent_offer_promises WHERE gm_free_agent_offer_request_id = ?",
            (int(request_id),),
        ).fetchone()
        return int(existing["id"]) if existing else None

    def _backfill_free_agent_offer_promises_conn(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute(
            """
            SELECT r.id
            FROM gm_free_agent_offer_requests r
            LEFT JOIN free_agent_offer_promises p
                ON p.gm_free_agent_offer_request_id = r.id
            WHERE r.status = 'approved'
              AND p.id IS NULL
            ORDER BY r.id
            """
        )
        for row in cur.fetchall():
            self._upsert_free_agent_offer_promise_for_request_conn(conn, int(row["id"]))

    def _free_agent_offer_promise_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["id"] = parse_int(item.get("id"))
        item["gm_free_agent_offer_request_id"] = parse_int(item.get("gm_free_agent_offer_request_id"))
        item["free_agent_id"] = parse_int(item.get("free_agent_id"))
        item["profile_id"] = parse_int(item.get("profile_id"))
        item["season_year"] = parse_int(item.get("season_year"))
        item["team_code"] = normalize_team_code(item.get("team_code")) or str(item.get("team_code") or "").strip().upper()
        item["status"] = str(item.get("status") or "pending").strip().lower()
        return item

    def list_free_agent_offer_promises(
        self,
        session: Dict[str, Any],
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        role = str(session.get("role") or "").strip().lower()
        agent_name = re.sub(
            r"\s+",
            " ",
            str(session.get("agent_name") or "").strip(),
        )
        if role not in {"admin", "co_admin"}:
            raise PermissionError("admin_or_coadmin_required")
        if role == "co_admin" and not agent_name:
            return {"agent_name": "", "missing_agent": True, "promises": []}

        where = ["1 = 1"]
        params: List[Any] = []
        normalized_status = str(status or "all").strip().lower()
        if normalized_status and normalized_status != "all":
            where.append("p.status = ?")
            params.append(self._offer_promise_status(normalized_status))
        if role == "co_admin":
            where.append("lower(trim(COALESCE(p.agent_name, ''))) = lower(trim(?))")
            params.append(agent_name)

        with self.db.connect() as conn:
            self._backfill_free_agent_offer_promises_conn(conn)
            conn.commit()
            cur = conn.execute(
                f"""
                SELECT p.*
                FROM free_agent_offer_promises p
                WHERE {' AND '.join(where)}
                ORDER BY
                    COALESCE(p.season_year, 0) DESC,
                    CASE p.status WHEN 'pending' THEN 0 WHEN 'broken' THEN 1 WHEN 'fulfilled' THEN 2 ELSE 3 END,
                    p.updated_at DESC,
                    lower(p.player_name)
                """,
                params,
            )
            promises = [self._free_agent_offer_promise_from_row(cur, row) for row in cur.fetchall()]
        return {"agent_name": agent_name, "missing_agent": False, "promises": promises}

    def create_free_agent_offer_promise(
        self,
        payload: Dict[str, Any],
        admin: Dict[str, Any],
        bypass_role_limits: bool = False,
    ) -> Dict[str, Any]:
        player_name = re.sub(r"\s+", " ", str(payload.get("player_name") or "").strip())
        if not player_name:
            raise ValueError("player_name_required")
        team_code = normalize_team_code(payload.get("team_code"))
        if not team_code:
            raise ValueError("invalid_team")
        role = re.sub(r"\s+", " ", str(payload.get("role") or "").strip())
        if not role:
            raise ValueError("role_required")
        season_year = parse_int(payload.get("season_year"))
        status = self._offer_promise_status(payload.get("status") or "pending")
        agent_name = re.sub(r"\s+", " ", str(payload.get("agent_name") or "").strip())
        contract_type = re.sub(r"\s+", " ", str(payload.get("contract_type") or "").strip())
        offer_type = re.sub(r"\s+", " ", str(payload.get("offer_type") or "manual").strip()) or "manual"
        profile_id = parse_int(payload.get("profile_id"))
        free_agent_id = parse_int(payload.get("free_agent_id"))
        timestamp = self._now()
        admin_email = str(admin.get("email") or "").strip().lower() or None
        admin_name = str(admin.get("name") or "").strip() or None
        with self.db.connect() as conn:
            if season_year is None:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = 'current_year'"
                ).fetchone()
                season_year = parse_int(row["value"]) if row else None
                season_year = season_year or self._forecast_min_year
            if season_year < 2000 or season_year > 2100:
                raise ValueError("invalid_season_year")
            team_row = conn.execute("SELECT code, name FROM teams WHERE code = ?", (team_code,)).fetchone()
            if not team_row:
                raise ValueError("team_not_found")
            if profile_id is not None and not conn.execute(
                "SELECT 1 FROM player_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone():
                raise ValueError("profile_not_found")
            if status in {"pending", "fulfilled"}:
                self._ensure_free_agent_promise_role_capacity_conn(
                    conn,
                    team_code,
                    season_year,
                    role,
                    bypass_role_limits=bypass_role_limits,
                )
            cur = conn.execute(
                """
                INSERT INTO free_agent_offer_promises (
                    gm_free_agent_offer_request_id,
                    free_agent_id,
                    profile_id,
                    player_name,
                    team_code,
                    team_name,
                    agent_name,
                    season_year,
                    season_label,
                    role,
                    offer_type,
                    contract_type,
                    status,
                    admin_email,
                    admin_name,
                    created_at,
                    updated_at,
                    decided_at
                )
                VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    free_agent_id,
                    profile_id,
                    player_name,
                    str(team_row["code"] or "").strip().upper(),
                    str(team_row["name"] or "").strip(),
                    agent_name,
                    season_year,
                    season_label(season_year),
                    role,
                    offer_type,
                    contract_type,
                    status,
                    admin_email,
                    admin_name,
                    timestamp,
                    timestamp,
                    None if status == "pending" else timestamp,
                ),
            )
            conn.commit()
            read_cur = conn.execute("SELECT * FROM free_agent_offer_promises WHERE id = ?", (cur.lastrowid,))
            row = read_cur.fetchone()
            if not row:
                raise ValueError("promise_not_created")
            return self._free_agent_offer_promise_from_row(read_cur, row)

    def update_free_agent_offer_promise(
        self,
        promise_id: Any,
        payload: Dict[str, Any],
        admin: Dict[str, Any],
        bypass_role_limits: bool = False,
    ) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(promise_id)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_promise_id")
        payload = payload if isinstance(payload, dict) else {}
        timestamp = self._now()
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM free_agent_offer_promises WHERE id = ?",
                (parsed_id,),
            ).fetchone()
            if not existing:
                return None
            player_name = re.sub(
                r"\s+",
                " ",
                str(payload.get("player_name") if "player_name" in payload else existing["player_name"] or "").strip(),
            )
            if not player_name:
                raise ValueError("player_name_required")
            team_code = normalize_team_code(payload.get("team_code") if "team_code" in payload else existing["team_code"])
            if not team_code:
                raise ValueError("invalid_team")
            team_row = conn.execute("SELECT code, name FROM teams WHERE code = ?", (team_code,)).fetchone()
            if not team_row:
                raise ValueError("team_not_found")
            role = self._normalize_free_agent_promise_role(
                payload.get("role") if "role" in payload else existing["role"]
            )
            if not role:
                raise ValueError("role_required")
            season_year = parse_int(payload.get("season_year") if "season_year" in payload else existing["season_year"])
            if season_year is None or season_year < 2000 or season_year > 2100:
                raise ValueError("invalid_season_year")
            normalized_status = self._offer_promise_status(
                payload.get("status") if "status" in payload else existing["status"]
            )
            free_agent_id = (
                parse_int(payload.get("free_agent_id"))
                if "free_agent_id" in payload
                else parse_int(existing["free_agent_id"])
            )
            profile_id = (
                parse_int(payload.get("profile_id"))
                if "profile_id" in payload
                else parse_int(existing["profile_id"])
            )
            if profile_id is not None and not conn.execute(
                "SELECT 1 FROM player_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone():
                raise ValueError("profile_not_found")
            agent_name = re.sub(
                r"\s+",
                " ",
                str(payload.get("agent_name") if "agent_name" in payload else existing["agent_name"] or "").strip(),
            )
            contract_type = re.sub(
                r"\s+",
                " ",
                str(payload.get("contract_type") if "contract_type" in payload else existing["contract_type"] or "").strip(),
            )
            offer_type = re.sub(
                r"\s+",
                " ",
                str(payload.get("offer_type") if "offer_type" in payload else existing["offer_type"] or "manual").strip(),
            ) or "manual"
            if normalized_status in {"pending", "fulfilled"}:
                self._ensure_free_agent_promise_role_capacity_conn(
                    conn,
                    team_code,
                    season_year,
                    role,
                    exclude_promise_id=parsed_id,
                    bypass_role_limits=bypass_role_limits,
                )
            cur = conn.execute(
                """
                UPDATE free_agent_offer_promises
                SET
                    free_agent_id = ?,
                    profile_id = ?,
                    player_name = ?,
                    team_code = ?,
                    team_name = ?,
                    agent_name = ?,
                    season_year = ?,
                    season_label = ?,
                    role = ?,
                    offer_type = ?,
                    contract_type = ?,
                    status = ?,
                    admin_email = ?,
                    admin_name = ?,
                    updated_at = ?,
                    decided_at = CASE WHEN ? = 'pending' THEN NULL ELSE ? END
                WHERE id = ?
                """,
                (
                    free_agent_id,
                    profile_id,
                    player_name,
                    str(team_row["code"] or "").strip().upper(),
                    str(team_row["name"] or "").strip(),
                    agent_name,
                    season_year,
                    season_label(season_year),
                    role,
                    offer_type,
                    contract_type,
                    normalized_status,
                    str(admin.get("email") or "").strip().lower() or None,
                    str(admin.get("name") or "").strip() or None,
                    timestamp,
                    normalized_status,
                    timestamp,
                    parsed_id,
                ),
            )
            conn.commit()
            if cur.rowcount < 1:
                return None
            read_cur = conn.execute(
                "SELECT * FROM free_agent_offer_promises WHERE id = ?",
                (parsed_id,),
            )
            row = read_cur.fetchone()
            return self._free_agent_offer_promise_from_row(read_cur, row) if row else None

    def update_free_agent_offer_promise_status(
        self,
        promise_id: Any,
        status: Any,
        admin: Dict[str, Any],
        bypass_role_limits: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return self.update_free_agent_offer_promise(
            promise_id,
            {"status": status},
            admin,
            bypass_role_limits=bypass_role_limits,
        )
