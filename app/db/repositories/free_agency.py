"""Persistence boundary for the free-agency service."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sqlite3
import unicodedata
from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain._values import parse_bool, parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_bool, parse_int

from .base import LeagueRepository


@dataclass(frozen=True)
class FreeAgencyOperations:
    now: Callable[[], str]
    normalize_team_code: Callable[[Any], Optional[str]]
    sync_generated: Callable[[Any, Dict[str, str]], Dict[str, Any]]
    merge_profile: Callable[[Dict[str, Any]], Dict[str, Any]]
    attach_salary_history: Callable[[Any, List[Dict[str, Any]]], List[Dict[str, Any]]]
    sync_lock: Any
    unavailable_statuses: tuple[str, ...]
    player_repository: Any
    normalize_bird_years: Callable[[Any], str]
    normalize_experience_years: Callable[[Any], Any]
    parse_salary_amount: Callable[[Any], Optional[float]]
    unavailable_profile_status: Callable[[Any], bool]
    contract_seasons: tuple[int, ...]
    player_lifecycle: Any
    normalize_free_agent_type: Callable[[Any], str]
    free_agent_update_fields: tuple[str, ...]
    free_agent_type_unrestricted: str
    free_agent_source_renounced_rights: str
    season_label: Callable[[int], str]


class FreeAgencyRepository(LeagueRepository):
    def __init__(self, db: Any, operations: Optional[FreeAgencyOperations] = None) -> None:
        super().__init__(db)
        self.operations = operations

    def _operations(self) -> FreeAgencyOperations:
        if not self.operations:
            raise RuntimeError("free_agency_repository_not_configured")
        return self.operations

    @staticmethod
    def _ruleout_agent_name(free_agent: Any, session: Dict[str, Any]) -> str:
        role = str(session.get("role") or "").strip().lower()
        free_agent_agent = re.sub(r"\s+", " ", str(free_agent["agent"] or "").strip())
        session_agent = re.sub(r"\s+", " ", str(session.get("agent_name") or "").strip())
        if role == "admin":
            if not free_agent_agent:
                raise ValueError("free_agent_agent_required")
            return free_agent_agent
        if role == "co_admin":
            if not free_agent_agent or not session_agent:
                raise PermissionError("agent_required")
            if free_agent_agent.casefold() != session_agent.casefold():
                raise PermissionError("agent_client_required")
            return free_agent_agent
        raise PermissionError("admin_or_coadmin_required")

    @staticmethod
    def _ruleouts_conn(conn: Any, free_agent_id: int, agent_name: str) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """SELECT r.*, t.name AS team_name FROM free_agent_team_ruleouts r
               LEFT JOIN teams t ON t.code = r.team_code
               WHERE r.free_agent_id = ?
                 AND lower(trim(r.agent_name)) = lower(trim(?))
               ORDER BY r.team_code""",
            (free_agent_id, agent_name),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_ruleout(self, free_agent_id: Any, team_code: Any, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        parsed_id = parse_int(free_agent_id)
        normalized_team = self._operations().normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        timestamp = self._operations().now()
        with self.db.connect() as conn:
            free_agent = conn.execute("SELECT id, agent FROM free_agents WHERE id = ?", (parsed_id,)).fetchone()
            if not free_agent:
                raise ValueError("free_agent_not_found")
            agent_name = self._ruleout_agent_name(free_agent, session)
            if not conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone():
                raise ValueError("team_not_found")
            conn.execute(
                """INSERT INTO free_agent_team_ruleouts (
                       free_agent_id, agent_name, team_code, created_by_user_id,
                       created_by_email, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(free_agent_id, agent_name, team_code) DO UPDATE SET
                       created_by_user_id = excluded.created_by_user_id,
                       created_by_email = excluded.created_by_email,
                       updated_at = excluded.updated_at""",
                (parsed_id, agent_name, normalized_team, parse_int(session.get("user_id")),
                 str(session.get("email") or "").strip().lower() or None, timestamp, timestamp),
            )
            rows = self._ruleouts_conn(conn, parsed_id, agent_name)
            conn.commit()
            return rows

    def delete_ruleout(self, free_agent_id: Any, team_code: Any, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        parsed_id = parse_int(free_agent_id)
        normalized_team = self._operations().normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.db.connect() as conn:
            free_agent = conn.execute("SELECT id, agent FROM free_agents WHERE id = ?", (parsed_id,)).fetchone()
            if not free_agent:
                raise ValueError("free_agent_not_found")
            agent_name = self._ruleout_agent_name(free_agent, session)
            conn.execute(
                """DELETE FROM free_agent_team_ruleouts WHERE free_agent_id = ?
                   AND lower(trim(agent_name)) = lower(trim(?)) AND team_code = ?""",
                (parsed_id, agent_name, normalized_team),
            )
            rows = self._ruleouts_conn(conn, parsed_id, agent_name)
            conn.commit()
            return rows

    def favorite_ids_for_team(self, team_code: Any) -> set[int]:
        normalized_team = self._operations().normalize_team_code(team_code)
        if not normalized_team:
            return set()
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT free_agent_id FROM free_agent_favorites WHERE team_code = ?",
                (normalized_team,),
            ).fetchall()
            return {int(row["free_agent_id"]) for row in rows if row["free_agent_id"] is not None}

    @staticmethod
    def _spending_payload(row: Any, team: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = dict(row) if row else {}
        team = team or {}
        amount = max(0, parse_int(data.get("amount")) or 0)
        updated_at = str(data.get("updated_at") or "").strip()
        return {
            "team_code": str(data.get("team_code") or team.get("code") or "").strip().upper() or None,
            "team_name": str(team.get("name") or data.get("team_name") or "").strip(),
            "amount": amount,
            "amount_millions": round(amount / 1_000_000, 3),
            "updated_at": updated_at,
            "updated_by_email": str(data.get("updated_by_email") or "").strip(),
            "has_value": bool(updated_at),
        }

    def spending_limit(self, team_code: Any) -> Dict[str, Any]:
        code = self._operations().normalize_team_code(team_code)
        if not code:
            raise ValueError("team_code_required")
        with self.db.connect() as conn:
            team_row = conn.execute("SELECT code, name FROM teams WHERE code = ?", (code,)).fetchone()
            if not team_row:
                raise ValueError("team_not_found")
            row = conn.execute(
                """SELECT l.*, t.name AS team_name FROM gm_free_agent_spending_limits l
                   JOIN teams t ON t.code = l.team_code WHERE l.team_code = ?""", (code,)
            ).fetchone()
            return self._spending_payload(row, dict(team_row))

    def set_spending_limit(self, team_code: Any, amount_millions: Any, session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code = self._operations().normalize_team_code(team_code)
        try:
            amount = float(amount_millions)
        except (TypeError, ValueError):
            raise ValueError("invalid_amount") from None
        if not code:
            raise ValueError("team_code_required")
        if amount < 0 or amount > 100:
            raise ValueError("amount_out_of_range")
        actor = session or {}
        with self.db.connect() as conn:
            if not conn.execute("SELECT code FROM teams WHERE code = ?", (code,)).fetchone():
                raise ValueError("team_not_found")
            conn.execute(
                """INSERT INTO gm_free_agent_spending_limits
                       (team_code, amount, updated_by_user_id, updated_by_email, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(team_code) DO UPDATE SET amount = excluded.amount,
                       updated_by_user_id = excluded.updated_by_user_id,
                       updated_by_email = excluded.updated_by_email,
                       updated_at = excluded.updated_at""",
                (code, int(round(amount * 1_000_000)), parse_int(actor.get("user_id")),
                 str(actor.get("email") or "").strip().lower(), self._operations().now()),
            )
            conn.commit()
        return self.spending_limit(code)

    def list_spending_limits(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT t.code AS team_code, t.name AS team_name, l.amount,
                          l.updated_at, l.updated_by_email FROM teams t
                   LEFT JOIN gm_free_agent_spending_limits l ON l.team_code = t.code
                   ORDER BY t.code"""
            ).fetchall()
            return [self._spending_payload(row) for row in rows]

    def create_free_agent(self, payload: Dict[str, Any]) -> Optional[int]:
        operations = self._operations()
        name = str(payload.get("name") or "").strip()
        if not name:
            return None
        timestamp = operations.now()
        with self.db.connect() as conn:
            profile_id = operations.player_lifecycle.resolve_profile(
                conn, payload, name=name, timestamp=timestamp
            )
            cur = conn.execute(
                """INSERT INTO free_agents (
                       profile_id, name, position, bird_rights, rating, years_left,
                       free_agent_type, agent, notes, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (profile_id, name, str(payload.get("position") or "").strip() or None,
                 str(payload.get("bird_rights") or "").strip() or None,
                 str(payload.get("rating") or "").strip() or None,
                 operations.normalize_bird_years(payload.get("years_left")),
                 operations.normalize_free_agent_type(payload.get("free_agent_type")),
                 str(payload.get("agent") or "").strip() or None,
                 str(payload.get("notes") or "").strip() or None, timestamp, timestamp),
            )
            free_agent_id = int(cur.lastrowid)
            operations.player_lifecycle.record_transaction(
                conn, profile_id, "free_agent", "Añadido a agentes libres",
                free_agent_id=free_agent_id, details={"player_name": name}, created_at=timestamp,
            )
            conn.commit()
            return free_agent_id

    def bulk_create_free_agents(self, raw_names: Any) -> Dict[str, Any]:
        operations = self._operations()
        lines = [str(item or "").strip() for item in raw_names] if isinstance(raw_names, list) else str(raw_names or "").splitlines()
        cleaned: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for line_number, raw in enumerate(lines, 1):
            name = re.sub(r"\s+", " ", str(raw or "").strip())
            if not name:
                continue
            if name.casefold() in seen:
                skipped.append({"line": line_number, "name": name, "reason": "duplicado en el texto"})
                continue
            seen.add(name.casefold())
            cleaned.append({"line": line_number, "name": name})
        if len(cleaned) > 1000:
            raise ValueError("too_many_names")
        created: List[Dict[str, Any]] = []
        timestamp = operations.now()
        with self.db.connect() as conn:
            for item in cleaned:
                name = item["name"]
                if conn.execute(
                    """SELECT f.id FROM free_agents f LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                       WHERE lower(trim(COALESCE(pp.name, f.name))) = lower(trim(?))
                          OR lower(trim(f.name)) = lower(trim(?)) LIMIT 1""", (name, name)
                ).fetchone():
                    skipped.append({**item, "reason": "ya existe en agentes libres"})
                    continue
                if conn.execute(
                    """SELECT p.id FROM players p LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                       WHERE lower(trim(COALESCE(pp.name, p.name))) = lower(trim(?))
                          OR lower(trim(p.name)) = lower(trim(?)) LIMIT 1""", (name, name)
                ).fetchone():
                    skipped.append({**item, "reason": "ya tiene contrato activo"})
                    continue
                profile_id = operations.player_lifecycle.find_profile_id(conn, name=name)
                if profile_id is None:
                    profile_id = operations.player_lifecycle.create_profile(conn, name, timestamp=timestamp)
                cur = conn.execute(
                    """INSERT INTO free_agents (
                           profile_id, name, position, bird_rights, rating, years_left,
                           free_agent_type, source, agent, notes, created_at, updated_at
                       ) VALUES (?, ?, NULL, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?, ?)""",
                    (profile_id, name, operations.free_agent_type_unrestricted, timestamp, timestamp),
                )
                free_agent_id = int(cur.lastrowid)
                created.append({"id": free_agent_id, **item})
                operations.player_lifecycle.record_transaction(
                    conn, profile_id, "free_agent", "Añadido a agentes libres",
                    free_agent_id=free_agent_id,
                    details={"player_name": name, "bulk_import": True}, created_at=timestamp,
                )
            conn.commit()
        return {"created_count": len(created), "skipped_count": len(skipped), "created": created, "skipped": skipped}

    def update_free_agent(self, free_agent_id: int, payload: Dict[str, Any]) -> bool:
        operations = self._operations()
        assignments: List[str] = []
        values: List[Any] = []
        for field in sorted(operations.free_agent_update_fields):
            if field not in payload:
                continue
            if field == "name":
                value = str(payload[field] or "").strip()
                if not value:
                    return False
            elif field == "years_left":
                value = operations.normalize_bird_years(payload[field])
            elif field == "free_agent_type":
                value = operations.normalize_free_agent_type(payload[field])
            else:
                value = str(payload[field] or "").strip() or None
            assignments.append(f"{field} = ?")
            values.append(value)
        if not assignments:
            return False
        timestamp = operations.now()
        with self.db.connect() as conn:
            profile_id = None
            if "name" in payload:
                row = conn.execute("SELECT profile_id, name FROM free_agents WHERE id = ?", (free_agent_id,)).fetchone()
                if not row:
                    return False
                profile_id = parse_int(row["profile_id"])
                if profile_id is None:
                    profile_id = operations.player_lifecycle.create_profile(conn, payload["name"] or row["name"], timestamp=timestamp)
                    conn.execute("UPDATE free_agents SET profile_id = ? WHERE id = ?", (profile_id, free_agent_id))
            cur = conn.execute(
                f"UPDATE free_agents SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
                [*values, timestamp, free_agent_id],
            )
            if profile_id is not None:
                conn.execute("UPDATE player_profiles SET name = ?, updated_at = ? WHERE id = ?",
                             (str(payload["name"] or "").strip() or "New Player", timestamp, profile_id))
            conn.commit()
            return cur.rowcount > 0

    def delete_free_agent(self, free_agent_id: int, record_transaction: bool = True) -> bool:
        operations = self._operations()
        with self.db.connect() as conn:
            agent = conn.execute(
                """SELECT f.profile_id, COALESCE(pp.name, f.name) AS name FROM free_agents f
                   LEFT JOIN player_profiles pp ON pp.id = f.profile_id WHERE f.id = ?""",
                (free_agent_id,),
            ).fetchone()
            self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, [free_agent_id])
            cur = conn.execute("DELETE FROM free_agents WHERE id = ?", (free_agent_id,))
            if record_transaction and cur.rowcount and agent:
                operations.player_lifecycle.record_transaction(
                    conn, agent["profile_id"], "delete", "Eliminado de agentes libres",
                    free_agent_id=free_agent_id, details={"player_name": agent["name"]},
                )
            conn.commit()
            return cur.rowcount > 0

    def ensure_renounced_rights_free_agent(
        self, player: Dict[str, Any], season_year: int, rights_value: str
    ) -> Optional[int]:
        operations = self._operations()
        season = parse_int(season_year)
        rights = str(rights_value or "").strip().upper()
        if season is None or rights not in {"FB", "EB", "NB"}:
            return None
        timestamp = operations.now()
        with self.db.connect() as conn:
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings")}
            current_year = parse_int(settings.get("current_year")) or 2025
            if not parse_bool(settings.get("free_agency_mode")) or season != current_year:
                return None
            player_id = parse_int(player.get("id"))
            profile_id = parse_int(player.get("profile_id"))
            if profile_id is None and player_id is not None:
                profile_id = operations.player_lifecycle.ensure_profile(conn, player_id, timestamp)
            if profile_id is None:
                return None
            team_code = operations.normalize_team_code(player.get("team_code"))
            name = str(player.get("profile_name") or player.get("name") or "Agente libre").strip() or "Agente libre"
            notes = f"Derechos Bird renunciados por {team_code or 'el equipo'} para {operations.season_label(season)}."
            existing = conn.execute("SELECT id FROM free_agents WHERE profile_id = ? LIMIT 1", (profile_id,)).fetchone()
            values = (name, str(player.get("position") or "").strip() or None,
                      str(player.get("rating") or "").strip() or None,
                      operations.normalize_bird_years(player.get("years_left")),
                      operations.free_agent_type_unrestricted,
                      operations.free_agent_source_renounced_rights, notes, timestamp)
            if existing:
                free_agent_id = int(existing["id"])
                conn.execute(
                    """UPDATE free_agents SET name = ?, position = ?, bird_rights = NULL,
                              rating = ?, years_left = ?, free_agent_type = ?, source = ?,
                              rights_team_code = NULL, notes = CASE WHEN notes IS NULL OR TRIM(notes) = ''
                              OR notes LIKE 'Cap hold retenido por %' OR notes LIKE 'Derechos Bird renunciados por %'
                              THEN ? ELSE notes END, updated_at = ? WHERE id = ?""",
                    (*values, free_agent_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO free_agents (profile_id, name, position, bird_rights, rating,
                           years_left, free_agent_type, source, rights_team_code, notes, created_at, updated_at)
                       VALUES (?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                    (profile_id, *values[:-1], timestamp, timestamp),
                )
                free_agent_id = int(cur.lastrowid)
            operations.player_lifecycle.record_transaction(
                conn, profile_id, "free_agent",
                f"{team_code or 'Equipo'} renuncia los derechos {rights} de {name} para {operations.season_label(season)}",
                player_id=player_id, free_agent_id=free_agent_id, team_code=team_code,
                from_team_code=team_code,
                details={"player_name": name, "season_year": season, "rights_value": rights,
                         "source": operations.free_agent_source_renounced_rights}, created_at=timestamp,
            )
            if player_id is not None:
                conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            conn.commit()
            return free_agent_id

    @staticmethod
    def _offer_thread_key(free_agent: Dict[str, Any]) -> tuple[Optional[int], str, str]:
        profile_id = parse_int(free_agent.get("profile_id"))
        player_name = str(
            free_agent.get("name") or free_agent.get("profile_name") or "Jugador"
        ).strip() or "Jugador"
        normalized_name = unicodedata.normalize("NFKD", player_name)
        name_key = re.sub(
            r"[^a-z0-9]+",
            "-",
            normalized_name.encode("ascii", "ignore").decode("ascii").lower(),
        )
        name_key = name_key.strip("-") or re.sub(r"\W+", "-", player_name.lower()).strip("-") or "jugador"
        return profile_id, name_key[:160], player_name

    def get_offer_thread(self, free_agent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        profile_id, name_key, _player_name = self._offer_thread_key(free_agent)
        with self.db.connect() as conn:
            if profile_id is not None:
                row = conn.execute(
                    "SELECT * FROM discord_free_agent_offer_threads WHERE profile_id = ? LIMIT 1",
                    (profile_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT * FROM discord_free_agent_offer_threads
                       WHERE profile_id IS NULL AND player_name_key = ? LIMIT 1""",
                    (name_key,),
                ).fetchone()
            return dict(row) if row else None

    def upsert_offer_thread(
        self, free_agent: Dict[str, Any], thread_id: str, thread_name: str
    ) -> None:
        clean_thread_id = re.sub(r"\D+", "", str(thread_id or ""))
        if not clean_thread_id:
            return
        profile_id, name_key, player_name = self._offer_thread_key(free_agent)
        timestamp = self._operations().now()
        with self.db.connect() as conn:
            if profile_id is not None:
                conn.execute(
                    """INSERT INTO discord_free_agent_offer_threads (
                           profile_id, player_name_key, player_name, thread_id, thread_name, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(profile_id) WHERE profile_id IS NOT NULL DO UPDATE SET
                           player_name_key = excluded.player_name_key,
                           player_name = excluded.player_name,
                           thread_id = excluded.thread_id,
                           thread_name = excluded.thread_name,
                           updated_at = excluded.updated_at""",
                    (profile_id, name_key, player_name, clean_thread_id, thread_name, timestamp, timestamp),
                )
            else:
                conn.execute(
                    """INSERT INTO discord_free_agent_offer_threads (
                           profile_id, player_name_key, player_name, thread_id, thread_name, created_at, updated_at
                       ) VALUES (NULL, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(player_name_key) WHERE profile_id IS NULL DO UPDATE SET
                           player_name = excluded.player_name,
                           thread_id = excluded.thread_id,
                           thread_name = excluded.thread_name,
                           updated_at = excluded.updated_at""",
                    (name_key, player_name, clean_thread_id, thread_name, timestamp, timestamp),
                )
            conn.commit()

    def _free_agent_conn(self, conn: Any, free_agent_id: int) -> Optional[Dict[str, Any]]:
        operations = self._operations()
        row = conn.execute(
            """SELECT f.*, pp.name AS profile_name,
                      pp.date_of_birth AS profile_date_of_birth,
                      pp.nationality AS profile_nationality,
                      pp.experience_years AS profile_experience_years,
                      pp.yos_source AS profile_yos_source,
                      pp.reference_image_url AS profile_reference_image_url,
                      pp.profile_notes AS profile_profile_notes,
                      pp.transaction_notes AS profile_transaction_notes,
                      pp.profile_status AS profile_status
               FROM free_agents f LEFT JOIN player_profiles pp ON pp.id = f.profile_id
               WHERE f.id = ?""",
            (int(free_agent_id),),
        ).fetchone()
        if not row or str(row["profile_status"] or "active") in operations.unavailable_statuses:
            return None
        item = operations.merge_profile(dict(row))
        enriched = operations.attach_salary_history(conn, [item])
        return enriched[0] if enriched else item

    def free_agent(self, free_agent_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            return self._free_agent_conn(conn, int(free_agent_id))

    def list_free_agents(self) -> List[Dict[str, Any]]:
        operations = self._operations()
        with self.db.connect() as conn:
            settings = {str(row["key"]): str(row["value"])
                        for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}
            try:
                with operations.sync_lock:
                    if operations.sync_generated(conn, settings).get("changed"):
                        conn.commit()
            except sqlite3.OperationalError as exc:
                if "database is locked" not in str(exc).lower():
                    raise
                conn.rollback()
            placeholders = ",".join("?" for _ in operations.unavailable_statuses)
            rows = conn.execute(
                f"""SELECT f.*, pp.name AS profile_name,
                           pp.date_of_birth AS profile_date_of_birth,
                           pp.nationality AS profile_nationality,
                           pp.experience_years AS profile_experience_years,
                           pp.yos_source AS profile_yos_source,
                           pp.reference_image_url AS profile_reference_image_url,
                           pp.profile_notes AS profile_profile_notes,
                           pp.transaction_notes AS profile_transaction_notes,
                           pp.profile_status AS profile_status
                    FROM free_agents f LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                    WHERE COALESCE(pp.profile_status, 'active') NOT IN ({placeholders})
                    ORDER BY COALESCE(pp.name, f.name) COLLATE NOCASE, f.id""",
                operations.unavailable_statuses,
            ).fetchall()
            agents = [operations.merge_profile(dict(row)) for row in rows]
            return operations.attach_salary_history(conn, agents)

    def record_interest(self, *args: Any, **kwargs: Any) -> Any:
        free_agent_id, team_code, payload, session = args
        parsed_id = parse_int(free_agent_id)
        normalized_team = self._operations().normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        economic_offer = re.sub(r"\s+", " ", str(payload.get("economic_offer") or "").strip())
        role_offer = re.sub(r"\s+", " ", str(payload.get("role_offer") or "").strip())
        comments = str(payload.get("comments") or "").strip()
        if not economic_offer and not role_offer and not comments:
            raise ValueError("empty_negotiation")
        timestamp = self._operations().now()
        with self.db.connect() as conn:
            if not conn.execute("SELECT id FROM free_agents WHERE id = ?", (parsed_id,)).fetchone():
                raise ValueError("free_agent_not_found")
            if not conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone():
                raise ValueError("team_not_found")
            conn.execute(
                """INSERT INTO free_agent_interests (
                       free_agent_id, team_code, submitted_by_user_id, submitted_by_email,
                       submitted_by_name, economic_offer, role_offer, comments, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(free_agent_id, team_code) DO UPDATE SET
                       submitted_by_user_id = excluded.submitted_by_user_id,
                       submitted_by_email = excluded.submitted_by_email,
                       submitted_by_name = excluded.submitted_by_name,
                       economic_offer = excluded.economic_offer, role_offer = excluded.role_offer,
                       comments = excluded.comments, updated_at = excluded.updated_at""",
                (parsed_id, normalized_team, parse_int(session.get("user_id")),
                 str(session.get("email") or "").strip().lower() or None,
                 str(session.get("name") or "").strip() or None,
                 economic_offer[:1000], role_offer[:1000], comments[:2000], timestamp, timestamp),
            )
            row = conn.execute(
                "SELECT * FROM free_agent_interests WHERE free_agent_id = ? AND team_code = ?",
                (parsed_id, normalized_team),
            ).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("free_agent_interest_not_saved")
        return dict(row)

    def set_favorite(self, *args: Any, **kwargs: Any) -> Any:
        free_agent_id, team_code, session = args
        parsed_id = parse_int(free_agent_id)
        normalized_team = self._operations().normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        timestamp = self._operations().now()
        with self.db.connect() as conn:
            if not conn.execute("SELECT id FROM free_agents WHERE id = ?", (parsed_id,)).fetchone():
                raise ValueError("free_agent_not_found")
            if not conn.execute("SELECT code FROM teams WHERE code = ?", (normalized_team,)).fetchone():
                raise ValueError("team_not_found")
            conn.execute(
                """INSERT INTO free_agent_favorites (
                       free_agent_id, team_code, user_id, user_email, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(free_agent_id, team_code) DO UPDATE SET
                       user_id = excluded.user_id, user_email = excluded.user_email,
                       updated_at = excluded.updated_at""",
                (parsed_id, normalized_team, parse_int(session.get("user_id")),
                 str(session.get("email") or "").strip().lower() or None, timestamp, timestamp),
            )
            row = conn.execute(
                "SELECT * FROM free_agent_favorites WHERE free_agent_id = ? AND team_code = ?",
                (parsed_id, normalized_team),
            ).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("free_agent_favorite_not_saved")
        return dict(row)

    def delete_favorite(self, *args: Any, **kwargs: Any) -> Any:
        free_agent_id, team_code = args
        parsed_id = parse_int(free_agent_id)
        normalized_team = self._operations().normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_free_agent_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM free_agent_favorites WHERE free_agent_id = ? AND team_code = ?",
                               (parsed_id, normalized_team))
            conn.commit()
            return cur.rowcount > 0

    def sign(self, *args: Any, **kwargs: Any) -> Any:
        free_agent_id, team_code, payload = args
        with self.db.transaction("IMMEDIATE") as conn:
            return self._sign_free_agent_conn(conn, free_agent_id, team_code, payload)

    def settings(self) -> Any:
        with self.db.connect() as conn:
            return {str(row["key"]): str(row["value"])
                    for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}

    def _find_player_profile_id(self, conn: sqlite3.Connection, player_id: Any) -> Optional[int]:
        parsed_player_id = parse_int(player_id)
        if parsed_player_id is None:
            return None
        row = conn.execute("SELECT profile_id FROM players WHERE id = ?", (parsed_player_id,)).fetchone()
        profile_id = parse_int(row["profile_id"]) if row else None
        if profile_id is None:
            return None
        exists = conn.execute("SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1", (profile_id,)).fetchone()
        return profile_id if exists else None

    def _record_player_transaction(
        self,
        conn: sqlite3.Connection,
        profile_id: Any,
        action: str,
        summary: str,
        *,
        player_id: Any = None,
        free_agent_id: Any = None,
        team_code: Any = None,
        from_team_code: Any = None,
        to_team_code: Any = None,
        details: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> None:
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None or not conn.execute(
            "SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1", (parsed_profile_id,)
        ).fetchone():
            return
        normalize_team_code = self.operations.normalize_team_code
        conn.execute(
            """INSERT INTO player_transactions (
                   profile_id, player_id, free_agent_id, dead_contract_id, action,
                   team_code, from_team_code, to_team_code, summary, details_json, source_log_id, created_at
               ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, NULL, ?)""",
            (
                parsed_profile_id,
                parse_int(player_id),
                parse_int(free_agent_id),
                str(action or "").strip().lower() or "update",
                normalize_team_code(team_code),
                normalize_team_code(from_team_code),
                normalize_team_code(to_team_code),
                str(summary or "").strip() or "Movimiento registrado",
                json.dumps(details or {}, ensure_ascii=True) if details else None,
                created_at or self.operations.now(),
            ),
        )

    @staticmethod
    def _approved_option_decision(
        conn: sqlite3.Connection,
        player_id: Any,
        option_field: str,
    ) -> Optional[sqlite3.Row]:
        parsed_player_id = parse_int(player_id)
        if parsed_player_id is None or not re.fullmatch(r"option_(20\d{2})", str(option_field or "").strip()):
            return None
        return conn.execute(
            """SELECT option_value, action, status FROM gm_option_requests
               WHERE player_id = ? AND option_field = ? AND status = 'approved'
               ORDER BY COALESCE(decided_at, updated_at, created_at) DESC, id DESC LIMIT 1""",
            (parsed_player_id, option_field),
        ).fetchone()

    def _retained_rights_only(
        self,
        conn: sqlite3.Connection,
        player: sqlite3.Row,
        current_year: int,
    ) -> bool:
        rights_markers = {"NB", "EB", "FB", "QO", "GAP"}
        for season in self.operations.contract_seasons:
            if season < current_year:
                continue
            salary_text = str(player[f"salary_{season}_text"] or "").strip()
            salary_marker = salary_text.upper()
            option_marker = str(player[f"option_{season}"] or "").strip().upper()
            decision = self._approved_option_decision(conn, player["id"], f"option_{season}")
            accepted_rights_option = bool(
                decision
                and option_marker in {"QO", "GAP"}
                and str(decision["action"] or "").strip().lower() == "accepted"
                and str(decision["option_value"] or "").strip().upper() == option_marker
            )
            salary_num = parse_int(player[f"salary_{season}_num"])
            try:
                numeric_salary = float(player[f"salary_{season}_num"])
            except (TypeError, ValueError):
                numeric_salary = float(salary_num or 0)
            if abs(numeric_salary) > 0 and not accepted_rights_option:
                return False
            salary_amount = self.operations.parse_salary_amount(salary_text)
            if salary_amount is not None and abs(float(salary_amount)) > 0 and not accepted_rights_option:
                return False
            if salary_text and salary_text != "-" and salary_marker not in rights_markers and not accepted_rights_option:
                return False
            if option_marker and option_marker not in rights_markers:
                return False
        return True

    def _remove_retained_rights_player_row_for_signing(
        self,
        conn: sqlite3.Connection,
        player: sqlite3.Row,
        *,
        free_agent_id: int,
        signing_team_code: str,
        player_name: str,
    ) -> None:
        profile_id = parse_int(player["profile_id"])
        old_player_id = parse_int(player["id"])
        old_team_code = self.operations.normalize_team_code(player["team_code"])
        rights_by_season: Dict[str, str] = {}
        for season in self.operations.contract_seasons:
            salary_marker = str(player[f"salary_{season}_text"] or "").strip().upper()
            option_marker = str(player[f"option_{season}"] or "").strip().upper()
            marker = salary_marker or option_marker
            if marker not in {"NB", "EB", "FB", "QO", "GAP"} and option_marker in {"QO", "GAP"}:
                marker = option_marker
            if marker in {"NB", "EB", "FB", "QO", "GAP"}:
                rights_by_season[str(season)] = marker

        conn.execute("DELETE FROM players WHERE id = ?", (old_player_id,))
        self._record_player_transaction(
            conn,
            profile_id,
            "rights_removed",
            f"Derechos eliminados por firma con {signing_team_code}",
            player_id=old_player_id,
            free_agent_id=free_agent_id,
            team_code=old_team_code,
            from_team_code=old_team_code,
            to_team_code=signing_team_code,
            details={
                "player_name": player_name,
                "rights_by_season": rights_by_season,
                "reason": "free_agent_signed_elsewhere",
            },
        )

    def _cleanup_gm_minimum_targets_for_free_agent_ids_conn(
        self,
        conn: sqlite3.Connection,
        free_agent_ids: Any,
    ) -> int:
        parsed_ids = sorted({
            int(parsed_id)
            for parsed_id in (parse_int(value) for value in (free_agent_ids or []))
            if parsed_id is not None and parsed_id > 0
        })
        if not parsed_ids:
            return 0
        placeholders = ",".join("?" for _ in parsed_ids)
        user_rows = conn.execute(
            f"""
            SELECT DISTINCT user_id
            FROM gm_minimum_targets
            WHERE free_agent_id IN ({placeholders})
            """,
            tuple(parsed_ids),
        ).fetchall()
        cur = conn.execute(
            f"DELETE FROM gm_minimum_targets WHERE free_agent_id IN ({placeholders})",
            tuple(parsed_ids),
        )
        deleted = int(cur.rowcount or 0)
        if deleted:
            timestamp = self.operations.now()
            for row in user_rows:
                user_id = parse_int(row["user_id"])
                if user_id is None:
                    continue
                conn.execute(
                    "UPDATE gm_minimum_target_status SET updated_at = ? WHERE user_id = ?",
                    (timestamp, int(user_id)),
                )
        return deleted

    def _delete_free_agent_entries_for_signed_profile_conn(
        self,
        conn: sqlite3.Connection,
        *,
        free_agent_id: Optional[int],
        profile_id: Optional[int],
    ) -> int:
        deleted = 0
        parsed_free_agent_id = parse_int(free_agent_id)
        parsed_profile_id = parse_int(profile_id)
        free_agent_ids: List[int] = []
        if parsed_free_agent_id is not None:
            free_agent_ids.append(int(parsed_free_agent_id))
        if parsed_profile_id is not None:
            rows = conn.execute(
                "SELECT id FROM free_agents WHERE profile_id = ?",
                (int(parsed_profile_id),),
            ).fetchall()
            free_agent_ids.extend(int(row["id"]) for row in rows)
        self._cleanup_gm_minimum_targets_for_free_agent_ids_conn(conn, free_agent_ids)
        if parsed_free_agent_id is not None:
            cur = conn.execute("DELETE FROM free_agents WHERE id = ?", (int(parsed_free_agent_id),))
            deleted += int(cur.rowcount or 0)
        if parsed_profile_id is not None:
            cur = conn.execute("DELETE FROM free_agents WHERE profile_id = ?", (int(parsed_profile_id),))
            deleted += int(cur.rowcount or 0)
        return deleted

    def _sign_free_agent_conn(
        self,
        conn: sqlite3.Connection,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
    ) -> Optional[int]:
        agent = self._free_agent_conn(conn, free_agent_id)
        if not agent:
            return None
        player_payload = dict(payload)
        player_payload["name"] = str(player_payload.get("name") or agent.get("name") or "").strip() or "New Player"
        if agent.get("profile_id") is not None and player_payload.get("profile_id") in (None, ""):
            player_payload["profile_id"] = agent.get("profile_id")
        for key in ["position", "bird_rights", "rating", "years_left", "notes"]:
            if player_payload.get(key) in (None, "") and agent.get(key) not in (None, ""):
                player_payload[key] = agent.get(key)
        player_payload.setdefault("signed_as_free_agent", True)

        profile_id = parse_int(player_payload.get("profile_id")) or parse_int(agent.get("profile_id"))
        normalized_team_code = self.operations.normalize_team_code(team_code)
        if profile_id is not None:
            profile_status_row = conn.execute(
                "SELECT profile_status FROM player_profiles WHERE id = ?",
                (int(profile_id),),
            ).fetchone()
            if profile_status_row and self.operations.unavailable_profile_status(profile_status_row["profile_status"]):
                raise ValueError("profile_unavailable")
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}
            current_year = parse_int(settings.get("current_year")) or self.operations.contract_seasons[0]
            active_rows = conn.execute(
                """
                SELECT p.*, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.profile_id = ?
                ORDER BY p.id
                """,
                (int(profile_id),),
            ).fetchall()
            if active_rows:
                same_team_row = next(
                    (
                        row for row in active_rows
                        if self.operations.normalize_team_code(row["team_code"]) == normalized_team_code
                    ),
                    None,
                )
                if not same_team_row:
                    blocking_rows = [
                        row for row in active_rows
                        if not self._retained_rights_only(conn, row, int(current_year))
                    ]
                    if blocking_rows:
                        raise ValueError("profile_has_active_contract")
                    for row in active_rows:
                        self._remove_retained_rights_player_row_for_signing(
                            conn,
                            row,
                            free_agent_id=free_agent_id,
                            signing_team_code=normalized_team_code,
                            player_name=player_payload["name"],
                        )
                else:
                    return self._apply_free_agent_contract_to_active_player(
                        conn,
                        int(same_team_row["id"]),
                        free_agent_id,
                        normalized_team_code,
                        agent,
                        player_payload,
                        commit=False,
                    )

        rights_team_code = self.operations.normalize_team_code(agent.get("rights_team_code"))
        if not rights_team_code or rights_team_code != normalized_team_code:
            player_payload["years_left"] = "0"

        player_id = self.operations.player_repository.create_conn(conn, team_code, player_payload)
        if not player_id:
            return None
        profile_id = self._find_player_profile_id(conn, player_id) or parse_int(agent.get("profile_id"))
        self._record_player_transaction(
            conn,
            profile_id,
            "sign",
            f"Firmado por {team_code.upper()}",
            player_id=player_id,
            free_agent_id=free_agent_id,
            team_code=team_code,
            to_team_code=team_code,
            details={"player_name": player_payload["name"]},
        )
        self._delete_free_agent_entries_for_signed_profile_conn(
            conn,
            free_agent_id=free_agent_id,
            profile_id=profile_id,
        )
        return player_id

    def _apply_free_agent_contract_to_active_player(
        self,
        conn: sqlite3.Connection,
        player_id: int,
        free_agent_id: int,
        team_code: str,
        agent: Dict[str, Any],
        player_payload: Dict[str, Any],
        *,
        commit: bool = True,
    ) -> Optional[int]:
        player = conn.execute(
            """
            SELECT p.id, p.profile_id, COALESCE(pp.name, p.name) AS player_name,
                   pp.profile_status, t.code AS team_code
            FROM players p
            LEFT JOIN player_profiles pp ON pp.id = p.profile_id
            JOIN teams t ON t.id = p.team_id
            WHERE p.id = ?
            """,
            (player_id,),
        ).fetchone()
        if not player:
            return None
        if self.operations.unavailable_profile_status(player["profile_status"]):
            raise ValueError("profile_unavailable")
        if self.operations.normalize_team_code(player["team_code"]) != self.operations.normalize_team_code(team_code):
            raise ValueError("profile_has_active_contract")

        settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}
        current_year = parse_int(settings.get("current_year")) or self.operations.contract_seasons[0]
        touched_years = [
            season for season in self.operations.contract_seasons
            if f"salary_{season}_text" in player_payload or f"option_{season}" in player_payload
        ]
        start_year = min(touched_years) if touched_years else int(current_year)
        timestamp = self.operations.now()
        assignments: List[str] = []
        values: List[Any] = []

        scalar_fields = [
            "name",
            "bird_rights",
            "rating",
            "position",
            "years_left",
            "notes",
            "reference_image_url",
            "profile_notes",
        ]
        for field in scalar_fields:
            if field not in player_payload:
                continue
            assignments.append(f"{field} = ?")
            if field == "years_left":
                values.append(self.operations.normalize_bird_years(player_payload.get(field)))
            else:
                values.append(player_payload.get(field))

        if "experience_years" in player_payload:
            assignments.append("experience_years = ?")
            values.append(self.operations.normalize_experience_years(player_payload.get("experience_years")))

        assignments.append("signed_as_free_agent = ?")
        values.append(1 if parse_bool(player_payload.get("signed_as_free_agent", True)) else 0)

        if "bird_rights" in player_payload:
            assignments.append("is_two_way = ?")
            values.append(1 if str(player_payload.get("bird_rights") or "").upper() == "TW" else 0)

        for season in self.operations.contract_seasons:
            if season < int(start_year):
                continue
            salary_field = f"salary_{season}_text"
            salary_value = player_payload.get(salary_field) if salary_field in player_payload else None
            assignments.append(f"{salary_field} = ?")
            values.append(salary_value)
            assignments.append(f"salary_{season}_num = ?")
            values.append(self.operations.parse_salary_amount(salary_value))

            guaranteed_field = f"salary_{season}_guaranteed_text"
            assignments.append(f"{guaranteed_field} = ?")
            values.append(player_payload.get(guaranteed_field) if guaranteed_field in player_payload else None)

            note_text_field = f"salary_{season}_note_text"
            assignments.append(f"{note_text_field} = ?")
            values.append(player_payload.get(note_text_field) if note_text_field in player_payload else None)

            option_field = f"option_{season}"
            assignments.append(f"{option_field} = ?")
            values.append(player_payload.get(option_field) if option_field in player_payload else None)

            for bool_suffix in ("provisional", "partially_guaranteed", "note"):
                bool_field = f"salary_{season}_{bool_suffix}"
                assignments.append(f"{bool_field} = ?")
                values.append(1 if parse_bool(player_payload.get(bool_field)) else 0)

        assignments.append("updated_at = ?")
        values.append(timestamp)
        values.append(player_id)
        conn.execute(
            f"UPDATE players SET {', '.join(assignments)} WHERE id = ?",
            values,
        )

        profile_updates: List[str] = []
        profile_values: List[Any] = []
        if "name" in player_payload:
            profile_updates.append("name = ?")
            profile_values.append(str(player_payload.get("name") or "").strip() or "New Player")
        if "experience_years" in player_payload:
            profile_updates.append("experience_years = COALESCE(?, experience_years)")
            profile_values.append(self.operations.normalize_experience_years(player_payload.get("experience_years")))
        if "reference_image_url" in player_payload:
            profile_updates.append("reference_image_url = COALESCE(NULLIF(?, ''), reference_image_url)")
            profile_values.append(str(player_payload.get("reference_image_url") or "").strip())
        if "profile_notes" in player_payload:
            profile_updates.append("profile_notes = COALESCE(?, profile_notes)")
            profile_values.append(player_payload.get("profile_notes"))
        if profile_updates and player["profile_id"] is not None:
            profile_updates.append("updated_at = ?")
            profile_values.append(timestamp)
            profile_values.append(int(player["profile_id"]))
            conn.execute(
                f"UPDATE player_profiles SET {', '.join(profile_updates)} WHERE id = ?",
                profile_values,
            )

        salary_by_season = {
            str(season): player_payload.get(f"salary_{season}_text")
            for season in self.operations.contract_seasons
            if player_payload.get(f"salary_{season}_text") not in (None, "")
        }
        player_name = str(player_payload.get("name") or player["player_name"] or agent.get("name") or "Jugador").strip()
        self._record_player_transaction(
            conn,
            player["profile_id"],
            "renew",
            f"Renovado por {team_code.upper()}",
            player_id=player_id,
            free_agent_id=free_agent_id,
            team_code=team_code,
            to_team_code=team_code,
            details={
                "player_name": player_name,
                "contract_type": player_payload.get("bird_rights"),
                "salary_by_season": salary_by_season,
            },
            created_at=timestamp,
        )
        self._delete_free_agent_entries_for_signed_profile_conn(
            conn,
            free_agent_id=free_agent_id,
            profile_id=parse_int(player["profile_id"]),
        )
        if commit:
            conn.commit()
        return player_id
