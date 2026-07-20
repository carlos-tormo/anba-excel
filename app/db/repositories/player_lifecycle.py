"""Shared persistence primitives for player and profile lifecycle workflows."""

from __future__ import annotations

import json
import math
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from ...auth.policies import normalize_team_code
    from ...domain._values import parse_amount_like, parse_float, parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_amount_like, parse_float, parse_int

from .base import LeagueRepository


class PlayerLifecycleRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        contract_seasons: Iterable[int],
        normalize_experience: Callable[[Any], Optional[int]],
        unavailable_profile_status: Callable[[Any], bool],
        normalize_profile_status: Callable[[Any], str],
        profile_status_label: Callable[[Any], str],
        retained_rights_only: Callable[..., bool],
        active_row_state: str,
        retained_rights_row_state: str,
        workflows: Any,
    ) -> None:
        super().__init__(db)
        self._now = now
        self._contract_seasons = tuple(contract_seasons)
        self._normalize_experience = normalize_experience
        self._unavailable_profile_status = unavailable_profile_status
        self._normalize_profile_status = normalize_profile_status
        self._profile_status_label = profile_status_label
        self._retained_rights_only = retained_rights_only
        self._active_row_state = active_row_state
        self._retained_rights_row_state = retained_rights_row_state
        self._workflows = workflows

    def make_profile_unavailable(
        self,
        conn: Any,
        profile_id: int,
        status: str,
        timestamp: str,
    ) -> Dict[str, int]:
        """Retire a profile from active player and free-agent workflows."""
        normalized_status = self._normalize_profile_status(status)
        if not self._unavailable_profile_status(normalized_status):
            return {"players": 0, "free_agents": 0, "requests": 0}

        player_rows = conn.execute(
            """SELECT p.id, p.name, t.code AS team_code
               FROM players p JOIN teams t ON t.id = p.team_id
               WHERE p.profile_id = ? ORDER BY p.id""",
            (int(profile_id),),
        ).fetchall()
        for row in player_rows:
            self.record_transaction(
                conn,
                profile_id,
                normalized_status,
                self._profile_status_label(normalized_status),
                player_id=int(row["id"]),
                team_code=row["team_code"],
                from_team_code=row["team_code"],
                details={
                    "player_name": str(row["name"] or "").strip(),
                    "profile_status": normalized_status,
                },
                created_at=timestamp,
            )

        free_agent_ids = [
            int(row["id"])
            for row in conn.execute(
                "SELECT id FROM free_agents WHERE profile_id = ?", (int(profile_id),)
            ).fetchall()
        ]
        request_count = 0
        if free_agent_ids:
            placeholders = ",".join("?" for _ in free_agent_ids)
            for table in (
                "free_agent_interests",
                "free_agent_favorites",
                "free_agent_team_ruleouts",
            ):
                if self.table_exists(conn, table):
                    conn.execute(
                        f"DELETE FROM {table} WHERE free_agent_id IN ({placeholders})",
                        free_agent_ids,
                    )
            request_count = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM gm_free_agent_offer_requests "
                    f"WHERE free_agent_id IN ({placeholders})",
                    free_agent_ids,
                ).fetchone()[0]
            )
            pending_request_ids = [
                int(row["id"])
                for row in conn.execute(
                    f"""SELECT id FROM gm_free_agent_offer_requests
                        WHERE free_agent_id IN ({placeholders}) AND status = 'pending'
                        ORDER BY id""",
                    free_agent_ids,
                ).fetchall()
            ]
            for request_id in pending_request_ids:
                self._workflows.transition_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    request_id,
                    "cancelled",
                    reason=f"player_profile_{normalized_status}",
                    command_id=(
                        f"gm-free-agent-offer:{request_id}:profile-{normalized_status}"
                    ),
                    updates={"updated_at": timestamp, "decided_at": timestamp},
                    metadata={
                        "profile_id": int(profile_id),
                        "profile_status": normalized_status,
                    },
                    timestamp=timestamp,
                )

        player_cur = conn.execute(
            "DELETE FROM players WHERE profile_id = ?", (int(profile_id),)
        )
        free_agent_cur = conn.execute(
            "DELETE FROM free_agents WHERE profile_id = ?", (int(profile_id),)
        )
        return {
            "players": int(player_cur.rowcount or 0),
            "free_agents": int(free_agent_cur.rowcount or 0),
            "requests": request_count,
        }

    @staticmethod
    def table_exists(conn: Any, table_name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone() is not None

    def current_year(self, conn: Any) -> int:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'current_year'"
        ).fetchone()
        return parse_int(row["value"] if row else None) or self._contract_seasons[0]

    def create_profile(
        self,
        conn: Any,
        name: Any,
        experience_years: Any = None,
        reference_image_url: Any = None,
        profile_notes: Any = None,
        timestamp: Optional[str] = None,
    ) -> int:
        created_at = timestamp or self._now()
        cur = conn.execute(
            """INSERT INTO player_profiles (
                   name, experience_years, reference_image_url, profile_notes,
                   created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(name or "").strip() or "New Player",
                self._normalize_experience(experience_years),
                str(reference_image_url or "").strip() or None,
                str(profile_notes or "").strip() or None,
                created_at,
                created_at,
            ),
        )
        return int(cur.lastrowid)

    @staticmethod
    def profile_exists(conn: Any, profile_id: Any) -> bool:
        parsed = parse_int(profile_id)
        return parsed is not None and conn.execute(
            "SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1", (parsed,)
        ).fetchone() is not None

    def existing_profile_id(self, conn: Any, profile_id: Any) -> Optional[int]:
        parsed = parse_int(profile_id)
        return parsed if parsed is not None and self.profile_exists(conn, parsed) else None

    @staticmethod
    def players_have_row_state(conn: Any) -> bool:
        return any(
            row["name"] == "row_state"
            for row in conn.execute("PRAGMA table_info(players)").fetchall()
        )

    def infer_row_state(
        self, conn: Any, player: Any, current_year: Optional[int] = None
    ) -> str:
        year = current_year if current_year is not None else self.current_year(conn)
        if self._retained_rights_only(player, int(year), conn):
            return self._retained_rights_row_state
        return self._active_row_state

    def sync_row_state(
        self, conn: Any, player_id: Any, timestamp: Optional[str] = None
    ) -> Optional[str]:
        if not self.players_have_row_state(conn):
            return None
        parsed = parse_int(player_id)
        if parsed is None:
            return None
        row = conn.execute(
            """SELECT p.*, t.code AS team_code FROM players p
               JOIN teams t ON t.id = p.team_id WHERE p.id = ?""",
            (parsed,),
        ).fetchone()
        if not row:
            return None
        state = self.infer_row_state(conn, row)
        if str(row["row_state"] or "") != state:
            conn.execute(
                "UPDATE players SET row_state = ?, updated_at = COALESCE(?, updated_at) WHERE id = ?",
                (state, timestamp, parsed),
            )
        return state

    def duplicate_active_profile_ids(self, conn: Any) -> List[int]:
        if not self.players_have_row_state(conn):
            return []
        rows = conn.execute(
            """SELECT profile_id FROM players
               WHERE profile_id IS NOT NULL AND row_state = ?
               GROUP BY profile_id HAVING COUNT(*) > 1""",
            (self._active_row_state,),
        ).fetchall()
        return [
            int(row["profile_id"])
            for row in rows
            if parse_int(row["profile_id"]) is not None
        ]

    def profile_has_active_contract(self, conn: Any, profile_id: Any) -> bool:
        parsed = parse_int(profile_id)
        if parsed is None:
            return False
        current_year = self.current_year(conn)
        rows = conn.execute(
            """SELECT p.*, t.code AS team_code FROM players p
               JOIN teams t ON t.id = p.team_id WHERE p.profile_id = ?""",
            (parsed,),
        ).fetchall()
        has_row_state = self.players_have_row_state(conn)
        active = False
        for row in rows:
            inferred = self.infer_row_state(conn, row, current_year)
            if has_row_state and str(row["row_state"] or "") != inferred:
                conn.execute(
                    "UPDATE players SET row_state = ? WHERE id = ?",
                    (inferred, int(row["id"])),
                )
            active = active or inferred == self._active_row_state
        return active

    def resolve_profile(
        self,
        conn: Any,
        payload: Dict[str, Any],
        *,
        name: Any,
        timestamp: str,
        forbid_active_contract: bool = False,
        require_available: bool = False,
    ) -> int:
        profile_id = self.existing_profile_id(conn, payload.get("profile_id"))
        if profile_id is not None:
            if require_available:
                row = conn.execute(
                    "SELECT profile_status FROM player_profiles WHERE id = ?",
                    (profile_id,),
                ).fetchone()
                if row and self._unavailable_profile_status(row["profile_status"]):
                    raise ValueError("profile_unavailable")
            if forbid_active_contract and self.profile_has_active_contract(
                conn, profile_id
            ):
                raise ValueError("profile_has_active_contract")
            return profile_id
        return self.create_profile(
            conn,
            name,
            payload.get("experience_years"),
            payload.get("reference_image_url"),
            payload.get("profile_notes"),
            timestamp,
        )

    def ensure_profile(
        self, conn: Any, player_id: int, timestamp: Optional[str] = None
    ) -> Optional[int]:
        row = conn.execute(
            """SELECT id, profile_id, name, experience_years, reference_image_url,
                      profile_notes, created_at, updated_at
               FROM players WHERE id = ?""",
            (player_id,),
        ).fetchone()
        if not row:
            return None
        existing = parse_int(row["profile_id"])
        if existing is not None:
            return existing
        profile_id = self.create_profile(
            conn,
            row["name"],
            row["experience_years"],
            row["reference_image_url"],
            row["profile_notes"],
            timestamp or row["created_at"] or row["updated_at"] or self._now(),
        )
        conn.execute(
            "UPDATE players SET profile_id = ? WHERE id = ?", (profile_id, player_id)
        )
        return profile_id

    @staticmethod
    def _clean_salary_value(salary_text: Any, salary_num: Any) -> Dict[str, Any]:
        text = str(salary_text or "").strip() or None
        numeric = parse_float(salary_num)
        if numeric is None and text:
            numeric = parse_amount_like(text)
        if numeric is not None and not math.isfinite(float(numeric)):
            numeric = None
        return {"text": text, "num": float(numeric) if numeric is not None else None}

    def upsert_salary_history(
        self,
        conn: Any,
        *,
        profile_id: Any,
        player_id: Any,
        team_code: Any,
        season_year: Any,
        salary_text: Any,
        salary_num: Any,
        source: str,
        salary_type: Any = None,
        timestamp: Optional[str] = None,
    ) -> bool:
        profile = parse_int(profile_id)
        season = parse_int(season_year)
        if profile is None or season is None or not self.profile_exists(conn, profile):
            return False
        cleaned = self._clean_salary_value(salary_text, salary_num)
        if cleaned["text"] is None and cleaned["num"] is None:
            return False
        created_at = timestamp or self._now()
        conn.execute(
            """INSERT INTO player_salary_history (
                   profile_id, player_id, team_code, season_year, salary_text,
                   salary_num, salary_type, source, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id, season_year) DO UPDATE SET
                   player_id = COALESCE(excluded.player_id, player_salary_history.player_id),
                   team_code = COALESCE(excluded.team_code, player_salary_history.team_code),
                   salary_text = COALESCE(excluded.salary_text, player_salary_history.salary_text),
                   salary_num = COALESCE(excluded.salary_num, player_salary_history.salary_num),
                   salary_type = COALESCE(excluded.salary_type, player_salary_history.salary_type),
                   source = excluded.source, updated_at = excluded.updated_at""",
            (
                profile,
                parse_int(player_id),
                normalize_team_code(team_code),
                season,
                cleaned["text"],
                cleaned["num"],
                str(salary_type or "").strip() or None,
                str(source or "unknown").strip() or "unknown",
                created_at,
                created_at,
            ),
        )
        return True

    def attach_salary_history(
        self, conn: Any, players: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        profile_ids = sorted(
            {
                parse_int(player.get("profile_id"))
                for player in players
                if parse_int(player.get("profile_id")) is not None
            }
        )
        if not profile_ids or not self.table_exists(conn, "player_salary_history"):
            return players
        placeholders = ",".join("?" for _ in profile_ids)
        rows = conn.execute(
            f"""SELECT profile_id, season_year, salary_text, salary_num,
                       salary_type, team_code FROM player_salary_history
                WHERE profile_id IN ({placeholders})""",
            profile_ids,
        ).fetchall()
        history: Dict[int, Dict[int, Any]] = {}
        for row in rows:
            profile_id = parse_int(row["profile_id"])
            season = parse_int(row["season_year"])
            if profile_id is not None and season is not None:
                history.setdefault(profile_id, {})[season] = row
        for player in players:
            profile_id = parse_int(player.get("profile_id"))
            for season, row in history.get(profile_id or -1, {}).items():
                player[f"salary_{season}_history_text"] = row["salary_text"]
                player[f"salary_{season}_history_num"] = row["salary_num"]
                player[f"salary_{season}_history_type"] = row["salary_type"]
                player[f"salary_{season}_history_team_code"] = row["team_code"]
        return players

    @staticmethod
    def unique_profile_name_map(conn: Any) -> Dict[str, int]:
        rows = conn.execute(
            """SELECT lower(trim(name)) AS name_key, MIN(id) AS id, COUNT(*) AS count
               FROM player_profiles WHERE COALESCE(trim(name), '') != ''
               GROUP BY lower(trim(name)) HAVING COUNT(*) = 1"""
        ).fetchall()
        return {str(row["name_key"]): int(row["id"]) for row in rows if row["name_key"]}

    def find_profile_id(
        self,
        conn: Any,
        player_id: Any = None,
        free_agent_id: Any = None,
        dead_contract_id: Any = None,
        name: Any = None,
    ) -> Optional[int]:
        for table, entity_id in (
            ("players", player_id),
            ("free_agents", free_agent_id),
            ("dead_contracts", dead_contract_id),
        ):
            parsed = parse_int(entity_id)
            if parsed is None:
                continue
            row = conn.execute(
                f"SELECT profile_id FROM {table} WHERE id = ?", (parsed,)
            ).fetchone()
            profile_id = parse_int(row["profile_id"]) if row else None
            if profile_id is not None and self.profile_exists(conn, profile_id):
                return profile_id
        profile_name = str(name or "").strip()
        if profile_name:
            row = conn.execute(
                """SELECT id FROM player_profiles
                   WHERE lower(trim(name)) = lower(trim(?)) ORDER BY id LIMIT 1""",
                (profile_name,),
            ).fetchone()
            return int(row["id"]) if row else None
        return None

    def record_transaction(
        self,
        conn: Any,
        profile_id: Any,
        action: str,
        summary: str,
        *,
        player_id: Any = None,
        free_agent_id: Any = None,
        dead_contract_id: Any = None,
        team_code: Any = None,
        from_team_code: Any = None,
        to_team_code: Any = None,
        details: Optional[Dict[str, Any]] = None,
        source_log_id: Any = None,
        created_at: Optional[str] = None,
    ) -> None:
        profile = parse_int(profile_id)
        if profile is None or not self.profile_exists(conn, profile):
            return
        action_text = str(action or "").strip().lower() or "update"
        summary_text = str(summary or "").strip() or "Movimiento registrado"
        source_id = parse_int(source_log_id)
        if source_id is not None and conn.execute(
            """SELECT 1 FROM player_transactions
               WHERE source_log_id = ? AND profile_id = ? AND action = ?
                 AND summary = ? LIMIT 1""",
            (source_id, profile, action_text, summary_text),
        ).fetchone():
            return
        conn.execute(
            """INSERT INTO player_transactions (
                   profile_id, player_id, free_agent_id, dead_contract_id, action,
                   team_code, from_team_code, to_team_code, summary, details_json,
                   source_log_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile,
                parse_int(player_id),
                parse_int(free_agent_id),
                parse_int(dead_contract_id),
                action_text,
                normalize_team_code(team_code),
                normalize_team_code(from_team_code),
                normalize_team_code(to_team_code),
                summary_text,
                json.dumps(details or {}, ensure_ascii=True) if details else None,
                source_id,
                created_at or self._now(),
            ),
        )
