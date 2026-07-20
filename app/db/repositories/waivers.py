"""SQL ownership for waiver players and waiver claim requests."""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

try:
    from ...auth.policies import normalize_team_code
    from ...domain._values import parse_int
    from ...workflow_states import WorkflowTransitionError
except ImportError:  # pragma: no cover - supports direct app imports.
    from auth.policies import normalize_team_code
    from domain._values import parse_int
    from workflow_states import WorkflowTransitionError

from .base import LeagueRepository


@dataclass(frozen=True)
class WaiverOperations:
    """Shared domain operations used while the waiver repository owns its SQL."""

    now: Callable[[], str]
    settings: Callable[[], Dict[str, str]]
    salary_for_season: Callable[[Dict[str, Any], int], float]
    claim_eligibility: Callable[..., Dict[str, Any]]
    record_player_transaction_conn: Callable[..., Any]
    player_repository: Any
    player_lifecycle: Any
    player_select_columns: Callable[[], str]
    merge_player_profile: Callable[[Dict[str, Any]], Dict[str, Any]]
    contract_snapshot: Callable[[Dict[str, Any]], Dict[str, Any]]
    normalize_cut_options: Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]
    cut_dead_cap_schedule: Callable[..., Any]
    player_is_ten_day_contract: Callable[[Dict[str, Any]], bool]
    normalize_bird_years: Callable[[Any], Optional[str]]
    parse_salary_amount: Callable[[Any], Optional[float]]
    contract_seasons: tuple[int, ...]
    free_agent_type_unrestricted: str


class WaiverRepository(LeagueRepository):
    def __init__(self, db: Any, operations: Optional[WaiverOperations] = None, *, workflows: Any = None) -> None:
        super().__init__(db)
        self.operations = operations
        self.workflows = workflows or getattr(db, "_workflow_repository", None)

    @property
    def configured(self) -> bool:
        return self.operations is not None

    def _operations(self) -> WaiverOperations:
        if not self.operations:
            raise RuntimeError("waiver_repository_not_configured")
        return self.operations

    def cut_player(
        self, player_id: int, payload: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        operations = self._operations()
        with self.db.transaction("IMMEDIATE") as conn:
            timestamp = operations.now()
            result = self.waive_player_conn(
                conn, int(player_id), timestamp=timestamp, cut_options=payload
            )
            if not result:
                return None
            team_code = str(result.get("team_code") or "").upper()
            operations.record_player_transaction_conn(
                conn,
                result.get("profile_id"),
                "cut",
                f"Cortado por {team_code}",
                player_id=player_id,
                free_agent_id=parse_int(result.get("free_agent_id")),
                dead_contract_id=parse_int(result.get("dead_contract_id")),
                team_code=team_code,
                from_team_code=team_code,
                details={
                    "player_name": result.get("name"),
                    "waiver_player_id": result.get("waiver_id"),
                    "waiver_expires_at": result.get("waiver_expires_at"),
                },
                created_at=timestamp,
            )
            return {
                "team_code": team_code,
                "team_name": result.get("team_name"),
                "player_name": result.get("name"),
                "profile_id": result.get("profile_id"),
                "reference_image_url": result.get("reference_image_url"),
                "dead_contract_id": result.get("dead_contract_id"),
                "free_agent_id": result.get("free_agent_id"),
                "waiver": bool(result.get("waiver")),
                "waiver_id": result.get("waiver_id"),
                "waiver_expires_at": result.get("waiver_expires_at"),
            }

    def list(self, actor: Any = None) -> Dict[str, Any]:
        operations = self._operations()
        self.process_expired()
        settings = operations.settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        session_team_codes = [
            str(code or "").upper()
            for code in (actor or {}).get("team_codes", [])
            if str(code or "").strip()
        ]
        with self.db.transaction("IMMEDIATE") as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT w.*, t.name AS from_team_name,
                           pp.reference_image_url AS profile_reference_image_url
                    FROM waiver_players w
                    JOIN teams t ON t.id = w.from_team_id
                    LEFT JOIN player_profiles pp ON pp.id = w.profile_id
                    WHERE w.status IN ('active', 'pending_claims')
                    ORDER BY w.waiver_expires_at, w.created_at, w.id
                    """
                ).fetchall()
            ]
            claim_rows = conn.execute(
                "SELECT waiver_player_id, team_code FROM waiver_claims WHERE status = 'pending'"
            ).fetchall()
            claimed_by_session = {
                int(row["waiver_player_id"])
                for row in claim_rows
                if str(row["team_code"] or "").upper() in session_team_codes
            }

        waivers: List[Dict[str, Any]] = []
        for row in rows:
            salary = operations.salary_for_season(row, current_year)
            item = {
                "id": row.get("id"),
                "profile_id": row.get("profile_id"),
                "player_name": row.get("player_name"),
                "position": row.get("position"),
                "rating": row.get("rating"),
                "bird_rights": row.get("bird_rights"),
                "years_left": row.get("years_left"),
                "from_team_code": row.get("from_team_code"),
                "from_team_name": row.get("from_team_name"),
                "waiver_expires_at": row.get("waiver_expires_at"),
                "status": row.get("status"),
                "salary_current": round(salary),
                "salary": round(salary),
                "reference_image_url": row.get("profile_reference_image_url"),
                "already_claimed_by_session": int(row.get("id") or 0) in claimed_by_session,
                "already_claimed": int(row.get("id") or 0) in claimed_by_session,
            }
            if len(session_team_codes) == 1:
                item["eligibility"] = operations.claim_eligibility(
                    session_team_codes[0], row, season_year=current_year
                )
            waivers.append(item)
        return {"waivers": waivers, "count": len(waivers)}

    def process_expired(self) -> Dict[str, Any]:
        operations = self._operations()
        timestamp = operations.now()
        processed: List[Dict[str, Any]] = []
        with self.db.transaction("IMMEDIATE") as conn:
            waivers = conn.execute(
                """
                SELECT * FROM waiver_players
                WHERE status IN ('active', 'pending_claims') AND waiver_expires_at <= ?
                ORDER BY waiver_expires_at, id
                """,
                (timestamp,),
            ).fetchall()
            for waiver_row in waivers:
                waiver = dict(waiver_row)
                claims = [
                    dict(row)
                    for row in conn.execute(
                        """SELECT * FROM waiver_claims
                           WHERE waiver_player_id = ? AND status = 'pending'
                           ORDER BY created_at, id""",
                        (int(waiver["id"]),),
                    ).fetchall()
                ]
                if len(claims) == 1:
                    result = self.approve_claim_conn(conn, claims[0], timestamp=timestamp)
                    if result:
                        processed.append({"waiver_player_id": int(waiver["id"]), "action": "claimed", **result})
                elif len(claims) > 1:
                    if str(waiver.get("status") or "") == "active":
                        self.workflows.transition_conn(
                            conn,
                            "waiver_player",
                            int(waiver["id"]),
                            "pending_claims",
                            reason="multiple_waiver_claims_require_admin",
                            updates={"updated_at": timestamp},
                            command_id=f"waiver-player:{int(waiver['id'])}:pending-claims",
                            metadata={"claim_count": len(claims)},
                        )
                    processed.append({"waiver_player_id": int(waiver["id"]), "action": "pending_admin"})
                else:
                    result = self.expire_without_claim_conn(conn, waiver, timestamp=timestamp)
                    processed.append({"waiver_player_id": int(waiver["id"]), "action": "expired", **result})
        return {"processed": processed, "count": len(processed)}

    def create_claim(
        self,
        waiver_player_id: int,
        team_code: str,
        payload: Dict[str, Any],
        requester: Dict[str, Any],
    ) -> Dict[str, Any]:
        operations = self._operations()
        timestamp = operations.now()
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        contingent_cut_player_id = parse_int(payload.get("contingent_cut_player_id"))
        with self.db.connect() as conn:
            waiver = conn.execute(
                "SELECT * FROM waiver_players WHERE id = ? AND status IN ('active', 'pending_claims')",
                (int(waiver_player_id),),
            ).fetchone()
            if not waiver:
                raise ValueError("waiver_not_found")
            team = conn.execute("SELECT id, code, name FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            eligibility = operations.claim_eligibility(
                normalized_team,
                dict(waiver),
                contingent_cut_player_id=contingent_cut_player_id,
            )
            if not eligibility.get("eligible"):
                raise ValueError(str(eligibility.get("reason") or "not_eligible"))
            try:
                cur = conn.execute(
                    """
                    INSERT INTO waiver_claims (
                        waiver_player_id, team_id, team_code, requester_user_id,
                        requester_email, requester_name, contingent_cut_player_id,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(waiver_player_id),
                        int(team["id"]),
                        normalized_team,
                        parse_int(requester.get("user_id") or requester.get("id")),
                        str(requester.get("email") or "").strip() or None,
                        str(requester.get("name") or "").strip() or None,
                        contingent_cut_player_id,
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("claim_already_submitted") from err
            claim_id = int(cur.lastrowid)
            self.workflows.record_creation_conn(
                conn,
                "waiver_claim",
                claim_id,
                "pending",
                actor=requester,
                reason="waiver_claim_submitted",
                command_id=f"waiver-claim:{claim_id}:created",
                metadata={"waiver_player_id": int(waiver_player_id), "team_code": normalized_team},
            )
            return {
                "id": claim_id,
                "waiver_player_id": int(waiver_player_id),
                "team_code": normalized_team,
                "status": "pending",
                "eligibility": eligibility,
            }

    def list_claim_requests(self, *, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        params: List[Any] = []
        where = ""
        if normalized_status and normalized_status != "all":
            where = "WHERE c.status = ?"
            params.append(normalized_status)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT c.*, w.player_name, w.position, w.rating, w.from_team_code,
                       w.waiver_expires_at, t.name AS team_name
                FROM waiver_claims c
                JOIN waiver_players w ON w.id = c.waiver_player_id
                JOIN teams t ON t.id = c.team_id
                {where}
                ORDER BY CASE c.status WHEN 'pending' THEN 0 ELSE 1 END,
                         c.created_at DESC, c.id DESC
                """,
                params,
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item.update(
                request_type="waiver_claim",
                action="claimed",
                option_value="Waivers",
                season_label=f"Desde {item.get('from_team_code') or ''}",
            )
            result.append(item)
        return result

    def decide_claim_request(
        self,
        request_id: int,
        decision: str,
        admin: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        operations = self._operations()
        timestamp = operations.now()
        normalized = str(decision or "").strip().lower()
        if normalized not in {"approved", "rejected"}:
            raise ValueError("invalid_decision")
        with self.db.transaction("IMMEDIATE") as conn:
            claim_row = conn.execute("SELECT * FROM waiver_claims WHERE id = ?", (int(request_id),)).fetchone()
            if not claim_row:
                return None
            claim = dict(claim_row)
            if str(claim.get("status") or "") != "pending":
                raise ValueError("request_already_decided")
            if normalized == "approved":
                result = self.approve_claim_conn(conn, claim, admin=admin, timestamp=timestamp)
                if not result:
                    raise ValueError("waiver_not_available")
                return result
            try:
                self.workflows.transition_conn(
                    conn,
                    "waiver_claim",
                    int(request_id),
                    "rejected",
                    actor=admin,
                    reason=str(note or "").strip() or "waiver_claim_rejected",
                    updates={
                        "admin_email": str((admin or {}).get("email") or "").strip() or None,
                        "admin_name": str((admin or {}).get("name") or "").strip() or None,
                        "admin_decision_note": str(note or "").strip() or None,
                        "updated_at": timestamp,
                        "decided_at": timestamp,
                    },
                    command_id=f"waiver-claim:{int(request_id)}:rejected",
                )
            except WorkflowTransitionError as err:
                raise ValueError("request_already_decided") from err
            return {"id": int(request_id), "status": "rejected"}

    def expire_without_claim_conn(
        self,
        conn: Any,
        waiver: Dict[str, Any],
        *,
        timestamp: str,
    ) -> Dict[str, Any]:
        operations = self._operations()
        payload = json.loads(waiver.get("contract_json") or "{}")
        dead_contract_id = self.ensure_dead_contract_conn(conn, waiver, payload, timestamp=timestamp)
        free_agent_id = self.upsert_free_agent_conn(conn, waiver, payload, timestamp=timestamp)
        self.workflows.transition_conn(
            conn,
            "waiver_player",
            int(waiver["id"]),
            "expired",
            reason="waiver_period_expired_without_claim",
            updates={
                "dead_contract_id": dead_contract_id,
                "free_agent_id": free_agent_id,
                "updated_at": timestamp,
            },
            command_id=f"waiver-player:{int(waiver['id'])}:expired",
        )
        operations.record_player_transaction_conn(
            conn,
            parse_int(waiver.get("profile_id")),
            "waiver_expired",
            f"Waivers expirado: {waiver.get('player_name')}",
            free_agent_id=free_agent_id,
            dead_contract_id=dead_contract_id,
            team_code=str(waiver.get("from_team_code") or "").upper(),
            from_team_code=str(waiver.get("from_team_code") or "").upper(),
            details={"player_name": waiver.get("player_name"), "waiver_player_id": waiver.get("id")},
            created_at=timestamp,
        )
        return {"dead_contract_id": dead_contract_id, "free_agent_id": free_agent_id}

    def approve_claim_conn(
        self,
        conn: Any,
        claim: Dict[str, Any],
        *,
        admin: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        operations = self._operations()
        timestamp = timestamp or operations.now()
        waiver = conn.execute(
            "SELECT * FROM waiver_players WHERE id = ?", (int(claim["waiver_player_id"]),)
        ).fetchone()
        if not waiver:
            return None
        waiver_data = dict(waiver)
        if str(waiver_data.get("status") or "") not in {"active", "pending_claims"}:
            return None
        payload = json.loads(waiver_data.get("contract_json") or "{}")
        target_team_code = str(claim.get("team_code") or "").upper()
        contingent_cut_id = parse_int(claim.get("contingent_cut_player_id"))
        if contingent_cut_id is not None:
            self.waive_player_conn(conn, int(contingent_cut_id), timestamp=timestamp)
        player_id = operations.player_repository.create_conn(conn, target_team_code, payload)
        if not player_id:
            return None
        dead_contract_id = parse_int(waiver_data.get("dead_contract_id"))
        if dead_contract_id is not None:
            conn.execute("DELETE FROM dead_contracts WHERE id = ?", (dead_contract_id,))
        pending_claims = conn.execute(
            "SELECT id FROM waiver_claims WHERE waiver_player_id = ? AND status = 'pending'",
            (int(claim["waiver_player_id"]),),
        ).fetchall()
        for pending_claim in pending_claims:
            pending_id = int(pending_claim["id"])
            claim_state = "approved" if pending_id == int(claim["id"]) else "rejected"
            self.workflows.transition_conn(
                conn,
                "waiver_claim",
                pending_id,
                claim_state,
                actor=admin,
                reason="waiver_claim_selected" if claim_state == "approved" else "waiver_claim_not_selected",
                updates={
                    "admin_email": str((admin or {}).get("email") or "").strip() or None,
                    "admin_name": str((admin or {}).get("name") or "").strip() or None,
                    "updated_at": timestamp,
                    "decided_at": timestamp,
                },
                command_id=f"waiver-claim:{pending_id}:{claim_state}",
            )
        self.workflows.transition_conn(
            conn,
            "waiver_player",
            int(claim["waiver_player_id"]),
            "claimed",
            actor=admin,
            reason="waiver_claim_awarded",
            updates={
                "claimed_team_code": target_team_code,
                "player_id": player_id,
                "dead_contract_id": None,
                "updated_at": timestamp,
            },
            command_id=f"waiver-player:{int(claim['waiver_player_id'])}:claimed",
            metadata={"claim_id": int(claim["id"]), "team_code": target_team_code},
        )
        operations.record_player_transaction_conn(
            conn,
            parse_int(waiver_data.get("profile_id")),
            "waiver_claim",
            f"{target_team_code} reclama de waivers a {waiver_data.get('player_name')}",
            player_id=player_id,
            team_code=target_team_code,
            from_team_code=str(waiver_data.get("from_team_code") or "").upper(),
            to_team_code=target_team_code,
            details={"player_name": waiver_data.get("player_name"), "waiver_player_id": waiver_data.get("id")},
            created_at=timestamp,
        )
        return {"player_id": player_id, "team_code": target_team_code, "player_name": waiver_data.get("player_name")}

    def create_waiver_player_conn(
        self,
        conn: Any,
        player: Dict[str, Any],
        *,
        created_at: str,
        cut_options: Optional[Dict[str, Any]] = None,
    ) -> int:
        operations = self._operations()
        expires_at = (
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            + timedelta(hours=48)
        ).astimezone(UTC)
        payload = operations.contract_snapshot(player)
        normalized_cut_options = operations.normalize_cut_options(cut_options)
        if normalized_cut_options.get("buyout") or normalized_cut_options.get("stretch"):
            payload["cut_settings"] = normalized_cut_options
        cur = conn.execute(
            """INSERT INTO waiver_players (
                   player_id, profile_id, from_team_id, from_team_code, player_name,
                   position, rating, bird_rights, years_left, contract_json,
                   waiver_expires_at, status, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                parse_int(player.get("id")),
                parse_int(player.get("profile_id")),
                int(player["team_id"]),
                str(player.get("team_code") or "").upper(),
                str(player.get("name") or "Jugador").strip() or "Jugador",
                str(player.get("position") or "").strip() or None,
                str(player.get("rating") or "").strip() or None,
                str(player.get("bird_rights") or "").strip() or None,
                operations.normalize_bird_years(player.get("years_left")),
                json.dumps(payload, ensure_ascii=False),
                expires_at.isoformat().replace("+00:00", "Z"),
                created_at,
                created_at,
            ),
        )
        waiver_id = int(cur.lastrowid)
        self.workflows.record_creation_conn(
            conn,
            "waiver_player",
            waiver_id,
            "active",
            reason="player_waived",
            metadata={
                "profile_id": parse_int(player.get("profile_id")),
                "team_code": player.get("team_code"),
            },
            command_id=f"waiver-player:{waiver_id}:created",
        )
        return waiver_id

    def insert_dead_contract_conn(
        self,
        conn: Any,
        waiver: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        timestamp: str,
    ) -> int:
        operations = self._operations()
        team_id = int(waiver["from_team_id"])
        dead_mx = conn.execute(
            "SELECT COALESCE(MAX(row_order), 0) AS mx FROM dead_contracts WHERE team_id = ?",
            (team_id,),
        ).fetchone()["mx"]
        settings = {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM app_settings").fetchall()
        }
        current_year = parse_int(settings.get("current_year")) or operations.contract_seasons[0]
        salary_texts, cut_note = operations.cut_dead_cap_schedule(
            payload,
            payload.get("cut_settings") if isinstance(payload.get("cut_settings"), dict) else None,
            current_year=int(current_year),
        )
        label = waiver.get("player_name") or payload.get("name") or "Cut Player"
        if cut_note:
            label = f"{label} ({cut_note})"
        first_dead_text = next(
            (salary_texts.get(season) for season in operations.contract_seasons if salary_texts.get(season)),
            None,
        )
        salary_columns: List[str] = []
        salary_values: List[Any] = []
        for season in operations.contract_seasons:
            salary_columns.extend((f"salary_{season}_text", f"salary_{season}_num"))
            value = salary_texts.get(season)
            salary_values.extend((value, operations.parse_salary_amount(value)))
        columns = [
            "team_id", "profile_id", "row_order", "dead_type", "label",
            "amount_text", "amount_num", *salary_columns, "created_at", "updated_at",
        ]
        values = [
            team_id,
            parse_int(waiver.get("profile_id")),
            int(dead_mx) + 1,
            "two_way" if str(payload.get("bird_rights") or "").upper() == "TW" else "normal",
            label,
            first_dead_text,
            operations.parse_salary_amount(first_dead_text),
            *salary_values,
            timestamp,
            timestamp,
        ]
        cur = conn.execute(
            f"INSERT INTO dead_contracts ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            values,
        )
        return int(cur.lastrowid)

    def ensure_dead_contract_conn(
        self,
        conn: Any,
        waiver: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        timestamp: str,
    ) -> int:
        existing_id = parse_int(waiver.get("dead_contract_id"))
        if existing_id is not None:
            existing = conn.execute(
                "SELECT id FROM dead_contracts WHERE id = ?", (existing_id,)
            ).fetchone()
            if existing:
                return int(existing["id"])
        dead_contract_id = self.insert_dead_contract_conn(
            conn, waiver, payload, timestamp=timestamp
        )
        conn.execute(
            "UPDATE waiver_players SET dead_contract_id = ?, updated_at = ? WHERE id = ?",
            (dead_contract_id, timestamp, int(waiver["id"])),
        )
        return dead_contract_id

    def upsert_free_agent_conn(
        self,
        conn: Any,
        waiver: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        timestamp: str,
    ) -> int:
        operations = self._operations()
        profile_id = parse_int(waiver.get("profile_id"))
        name = str(
            waiver.get("player_name") or payload.get("name") or "Agente libre"
        ).strip() or "Agente libre"
        existing = (
            conn.execute(
                "SELECT id FROM free_agents WHERE profile_id = ? LIMIT 1", (profile_id,)
            ).fetchone()
            if profile_id is not None
            else None
        )
        values = (
            name,
            str(payload.get("position") or waiver.get("position") or "").strip() or None,
            str(payload.get("bird_rights") or waiver.get("bird_rights") or "").strip() or None,
            str(payload.get("rating") or waiver.get("rating") or "").strip() or None,
            operations.normalize_bird_years(payload.get("years_left")),
            operations.free_agent_type_unrestricted,
            "waiver_expired",
            "Waivers no reclamado en 48h.",
            timestamp,
        )
        if existing:
            free_agent_id = int(existing["id"])
            conn.execute(
                """UPDATE free_agents SET name = ?, position = ?, bird_rights = ?,
                          rating = ?, years_left = ?, free_agent_type = ?, source = ?,
                          rights_team_code = NULL, notes = ?, updated_at = ? WHERE id = ?""",
                (*values, free_agent_id),
            )
            return free_agent_id
        cur = conn.execute(
            """INSERT INTO free_agents (
                   profile_id, name, position, bird_rights, rating, years_left,
                   free_agent_type, source, rights_team_code, notes, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
            (profile_id, *values[:-1], timestamp, timestamp),
        )
        return int(cur.lastrowid)

    def waive_player_conn(
        self,
        conn: Any,
        player_id: int,
        *,
        timestamp: str,
        cut_options: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        operations = self._operations()
        row = conn.execute(
            f"""SELECT {operations.player_select_columns()}, t.code AS team_code,
                       t.name AS team_name
                FROM players p LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                JOIN teams t ON t.id = p.team_id WHERE p.id = ?""",
            (player_id,),
        ).fetchone()
        if not row:
            return None
        player = operations.merge_player_profile(dict(row))
        profile_id = operations.player_lifecycle.ensure_profile(conn, player_id, timestamp)
        if profile_id is None:
            return None
        player["profile_id"] = profile_id
        if operations.player_is_ten_day_contract(player):
            payload = operations.contract_snapshot(player)
            free_agent_id = self.upsert_free_agent_conn(
                conn,
                {
                    "from_team_id": player["team_id"],
                    "from_team_code": player.get("team_code"),
                    "profile_id": profile_id,
                    "player_name": player.get("name"),
                },
                payload,
                timestamp=timestamp,
            )
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            return {
                "waiver": False,
                "dead_contract_id": None,
                "free_agent_id": free_agent_id,
                **player,
            }
        waiver_id = self.create_waiver_player_conn(
            conn, player, created_at=timestamp, cut_options=cut_options
        )
        waiver_row = conn.execute(
            "SELECT * FROM waiver_players WHERE id = ?", (waiver_id,)
        ).fetchone()
        dead_contract_id = None
        if waiver_row:
            waiver_data = dict(waiver_row)
            dead_contract_id = self.ensure_dead_contract_conn(
                conn,
                waiver_data,
                json.loads(waiver_data.get("contract_json") or "{}"),
                timestamp=timestamp,
            )
        conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
        return {
            "waiver": True,
            "waiver_id": waiver_id,
            "waiver_expires_at": waiver_row["waiver_expires_at"] if waiver_row else None,
            "dead_contract_id": dead_contract_id,
            **player,
        }
