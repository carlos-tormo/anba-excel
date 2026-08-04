"""Persistence for team season objectives and objective event history."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

try:
    from ...auth.policies import normalize_team_code
    from ...domain._values import parse_int
    from ...domain.team_objectives import (
        OBJECTIVE_LABELS,
        compare_objectives,
        objective_label,
        normalize_objective_code,
        require_objective_code,
        require_objective_result_code,
    )
except ImportError:  # pragma: no cover - direct script import compatibility
    from auth.policies import normalize_team_code
    from domain._values import parse_int
    from domain.team_objectives import (
        OBJECTIVE_LABELS,
        compare_objectives,
        objective_label,
        normalize_objective_code,
        require_objective_code,
        require_objective_result_code,
    )

from .base import LeagueRepository


OBJECTIVE_STATUSES = frozenset({"proposed", "agreed", "locked", "resolved"})


class TeamObjectiveRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str]) -> None:
        super().__init__(db)
        self._now = now

    @staticmethod
    def _normalize_status(value: Any, *, default: str = "proposed") -> str:
        status = str(value or default).strip().lower()
        if status not in OBJECTIVE_STATUSES:
            raise ValueError("invalid_team_objective_status")
        return status

    @staticmethod
    def _actor_user_id(actor: Optional[Dict[str, Any]]) -> Optional[int]:
        return parse_int((actor or {}).get("user_id"))

    @staticmethod
    def _team(conn: Any, team_code: Any) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("invalid_team")
        row = conn.execute(
            "SELECT id, code, name FROM teams WHERE code = ?",
            (normalized_team,),
        ).fetchone()
        if not row:
            raise ValueError("team_not_found")
        return dict(row)

    @staticmethod
    def _row_payload(row: Any) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        payload = dict(row)
        payload["id"] = int(payload["id"])
        payload["team_id"] = int(payload["team_id"])
        payload["season_year"] = int(payload["season_year"])
        payload["version"] = parse_int(payload.get("version")) or 1
        payload["objective"] = {
            "code": payload.get("objective_code"),
            "label": payload.get("objective_label_snapshot") or OBJECTIVE_LABELS.get(str(payload.get("objective_code") or ""), ""),
        }
        achieved_code = normalize_objective_code(payload.get("achieved_code"))
        payload["achieved"] = (
            {
                "code": achieved_code,
                "label": payload.get("achieved_label_snapshot") or OBJECTIVE_LABELS.get(str(achieved_code or ""), ""),
            }
            if achieved_code
            else None
        )
        payload["comparison"] = compare_objectives(payload.get("objective_code"), achieved_code) if achieved_code else None
        return payload

    def get(
        self,
        team_code: Any,
        season_year: Any,
        *,
        include_events: bool = False,
    ) -> Optional[Dict[str, Any]]:
        parsed_season = parse_int(season_year)
        if parsed_season is None:
            raise ValueError("invalid_season_year")
        with self.db.connect() as conn:
            return self.get_conn(conn, team_code, parsed_season, include_events=include_events)

    def get_conn(
        self,
        conn: Any,
        team_code: Any,
        season_year: Any,
        *,
        include_events: bool = False,
    ) -> Optional[Dict[str, Any]]:
        parsed_season = parse_int(season_year)
        if parsed_season is None:
            raise ValueError("invalid_season_year")
        team = self._team(conn, team_code)
        row = conn.execute(
            """
            SELECT o.*, t.code AS team_code, t.name AS team_name,
                   u.email AS agreed_by_email,
                   COALESCE(u.username, u.display_name, u.email) AS agreed_by_name
            FROM team_season_objectives o
            JOIN teams t ON t.id = o.team_id
            LEFT JOIN users u ON u.id = o.agreed_by_user_id
            WHERE o.team_id = ? AND o.season_year = ?
            """,
            (int(team["id"]), int(parsed_season)),
        ).fetchone()
        payload = self._row_payload(row)
        if payload and include_events:
            payload["events"] = self.events_for_objective(int(payload["id"]), conn=conn)
        return payload

    def latest_at_or_before_conn(
        self,
        conn: Any,
        team_code: Any,
        season_year: Any,
    ) -> Optional[Dict[str, Any]]:
        parsed_season = parse_int(season_year)
        if parsed_season is None:
            raise ValueError("invalid_season_year")
        team = self._team(conn, team_code)
        row = conn.execute(
            """
            SELECT o.*, t.code AS team_code, t.name AS team_name,
                   u.email AS agreed_by_email,
                   COALESCE(u.username, u.display_name, u.email) AS agreed_by_name
            FROM team_season_objectives o
            JOIN teams t ON t.id = o.team_id
            LEFT JOIN users u ON u.id = o.agreed_by_user_id
            WHERE o.team_id = ?
              AND o.season_year <= ?
            ORDER BY o.season_year DESC, o.id DESC
            LIMIT 1
            """,
            (int(team["id"]), int(parsed_season)),
        ).fetchone()
        return self._row_payload(row)

    def latest_at_or_before(
        self,
        team_code: Any,
        season_year: Any,
    ) -> Optional[Dict[str, Any]]:
        parsed_season = parse_int(season_year)
        if parsed_season is None:
            raise ValueError("invalid_season_year")
        with self.db.connect() as conn:
            return self.latest_at_or_before_conn(conn, team_code, parsed_season)

    def list_for_season(self, season_year: Any) -> List[Dict[str, Any]]:
        parsed_season = parse_int(season_year)
        if parsed_season is None:
            raise ValueError("invalid_season_year")
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT o.*, t.code AS team_code, t.name AS team_name,
                       u.email AS agreed_by_email,
                       COALESCE(u.username, u.display_name, u.email) AS agreed_by_name
                FROM teams t
                LEFT JOIN team_season_objectives o
                  ON o.team_id = t.id AND o.season_year = ?
                LEFT JOIN users u ON u.id = o.agreed_by_user_id
                WHERE o.id IS NOT NULL
                ORDER BY t.code
                """,
                (int(parsed_season),),
            ).fetchall()
        return [payload for payload in (self._row_payload(row) for row in rows) if payload]

    def current_year(self) -> int:
        with self.db.connect() as conn:
            return self.current_year_conn(conn)

    def current_year_conn(self, conn: Any) -> int:
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'current_year'").fetchone()
        return parse_int(row["value"] if row else None) or 2025

    def set_objective(
        self,
        team_code: Any,
        season_year: Any,
        objective: Any,
        *,
        status: Any = "agreed",
        actor: Optional[Dict[str, Any]] = None,
        owner_conversation_id: Any = None,
        expected_version: Any = None,
        command_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        parsed_season = parse_int(season_year)
        if parsed_season is None or parsed_season < 2000 or parsed_season > 2100:
            raise ValueError("invalid_season_year")
        objective_code = require_objective_code(objective)
        normalized_status = self._normalize_status(status, default="agreed")
        expected = parse_int(expected_version)
        timestamp = self._now()
        actor_user_id = self._actor_user_id(actor)
        with self.db.transaction("IMMEDIATE") as conn:
            team = self._team(conn, team_code)
            existing = conn.execute(
                "SELECT * FROM team_season_objectives WHERE team_id = ? AND season_year = ?",
                (int(team["id"]), int(parsed_season)),
            ).fetchone()
            previous_code = str(existing["objective_code"] or "") if existing else None
            previous_status = str(existing["status"] or "") if existing else None
            if existing and expected is not None and expected != int(existing["version"] or 1):
                raise ValueError("stale_entity_version")

            should_stamp_agreement = normalized_status in {"agreed", "locked", "resolved"}
            agreed_at = (
                (existing["agreed_at"] if existing else None)
                or (timestamp if should_stamp_agreement else None)
            )
            agreed_by = (
                parse_int(existing["agreed_by_user_id"]) if existing else None
            ) or (actor_user_id if should_stamp_agreement else None)
            owner_conversation = (
                str(owner_conversation_id).strip()
                if owner_conversation_id is not None and str(owner_conversation_id).strip()
                else (str(existing["owner_conversation_id"] or "") if existing else "")
            ) or None

            if existing:
                conn.execute(
                    """
                    UPDATE team_season_objectives
                    SET objective_code = ?,
                        objective_label_snapshot = ?,
                        status = ?,
                        agreed_at = ?,
                        agreed_by_user_id = ?,
                        owner_conversation_id = ?,
                        version = version + 1,
                        updated_at = ?
                    WHERE id = ?
                      AND version = ?
                    """,
                    (
                        objective_code,
                        objective_label(objective_code),
                        normalized_status,
                        agreed_at,
                        agreed_by,
                        owner_conversation,
                        timestamp,
                        int(existing["id"]),
                        int(existing["version"] or 1),
                    ),
                )
                objective_id = int(existing["id"])
                event_type = "objective_updated"
            else:
                cur = conn.execute(
                    """
                    INSERT INTO team_season_objectives (
                        team_id, season_year, objective_code, objective_label_snapshot,
                        status, agreed_at, agreed_by_user_id, owner_conversation_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(team["id"]),
                        int(parsed_season),
                        objective_code,
                        objective_label(objective_code),
                        normalized_status,
                        agreed_at,
                        agreed_by,
                        owner_conversation,
                        timestamp,
                        timestamp,
                    ),
                )
                objective_id = int(cur.lastrowid)
                event_type = "objective_created"

            self._record_event_conn(
                conn,
                objective_id,
                event_type,
                previous_code,
                objective_code,
                actor_user_id,
                command_id
                or f"team-objective:{str(team['code']).upper()}:{int(parsed_season)}:{event_type}:{timestamp}",
                timestamp,
                {
                    **(metadata or {}),
                    "team_code": team["code"],
                    "season_year": int(parsed_season),
                    "previous_status": previous_status,
                    "status": normalized_status,
                    "owner_conversation_id": owner_conversation,
                },
            )
            self._sync_owner_office_goal_set_conn(
                conn,
                int(team["id"]),
                int(parsed_season),
                objective_label(objective_code),
                timestamp,
            )
            return self._read_by_id_conn(conn, objective_id)

    def resolve_objective(
        self,
        team_code: Any,
        season_year: Any,
        achieved: Any,
        *,
        actor: Optional[Dict[str, Any]] = None,
        expected_version: Any = None,
        command_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        parsed_season = parse_int(season_year)
        if parsed_season is None:
            raise ValueError("invalid_season_year")
        achieved_code = require_objective_result_code(achieved)
        expected = parse_int(expected_version)
        timestamp = self._now()
        actor_user_id = self._actor_user_id(actor)
        with self.db.transaction("IMMEDIATE") as conn:
            team = self._team(conn, team_code)
            existing = conn.execute(
                "SELECT * FROM team_season_objectives WHERE team_id = ? AND season_year = ?",
                (int(team["id"]), int(parsed_season)),
            ).fetchone()
            if not existing:
                raise ValueError("team_objective_not_found")
            if expected is not None and expected != int(existing["version"] or 1):
                raise ValueError("stale_entity_version")
            conn.execute(
                """
                UPDATE team_season_objectives
                SET achieved_code = ?,
                    achieved_label_snapshot = ?,
                    status = 'resolved',
                    resolved_at = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE id = ?
                  AND version = ?
                """,
                (
                    achieved_code,
                    objective_label(achieved_code),
                    timestamp,
                    timestamp,
                    int(existing["id"]),
                    int(existing["version"] or 1),
                ),
            )
            comparison = compare_objectives(existing["objective_code"], achieved_code)
            self._record_event_conn(
                conn,
                int(existing["id"]),
                "objective_resolved",
                existing["objective_code"],
                achieved_code,
                actor_user_id,
                command_id
                or f"team-objective:{str(team['code']).upper()}:{int(parsed_season)}:objective_resolved:{timestamp}",
                timestamp,
                {
                    **(metadata or {}),
                    "team_code": team["code"],
                    "season_year": int(parsed_season),
                    "status": "resolved",
                    "comparison": comparison,
                    "achieved_label": objective_label(achieved_code),
                },
            )
            self._sync_owner_office_goal_achieved_conn(
                conn,
                int(team["id"]),
                int(parsed_season),
                objective_label(achieved_code),
                timestamp,
            )
            return self._read_by_id_conn(conn, int(existing["id"]))

    def events_for_objective(self, objective_id: int, *, conn: Any = None) -> List[Dict[str, Any]]:
        def read(active_conn: Any) -> List[Dict[str, Any]]:
            rows = active_conn.execute(
                """
                SELECT e.*, u.email AS actor_email,
                       COALESCE(u.username, u.display_name, u.email) AS actor_name
                FROM team_season_objective_events e
                LEFT JOIN users u ON u.id = e.actor_user_id
                WHERE e.objective_id = ?
                ORDER BY e.created_at, e.id
                """,
                (int(objective_id),),
            ).fetchall()
            events: List[Dict[str, Any]] = []
            for row in rows:
                event = dict(row)
                try:
                    event["metadata"] = json.loads(str(event.pop("metadata_json") or "{}"))
                except json.JSONDecodeError:
                    event["metadata"] = {}
                events.append(event)
            return events

        if conn is not None:
            return read(conn)
        with self.db.connect() as active_conn:
            return read(active_conn)

    def _read_by_id_conn(self, conn: Any, objective_id: int) -> Dict[str, Any]:
        row = conn.execute(
            """
            SELECT o.*, t.code AS team_code, t.name AS team_name,
                   u.email AS agreed_by_email,
                   COALESCE(u.username, u.display_name, u.email) AS agreed_by_name
            FROM team_season_objectives o
            JOIN teams t ON t.id = o.team_id
            LEFT JOIN users u ON u.id = o.agreed_by_user_id
            WHERE o.id = ?
            """,
            (int(objective_id),),
        ).fetchone()
        payload = self._row_payload(row)
        if payload is None:
            raise ValueError("team_objective_not_found")
        return payload

    @staticmethod
    def _record_event_conn(
        conn: Any,
        objective_id: int,
        event_type: str,
        previous_objective_code: Optional[str],
        new_objective_code: Optional[str],
        actor_user_id: Optional[int],
        command_id: Optional[str],
        timestamp: str,
        metadata: Dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_season_objective_events (
                objective_id, event_type, previous_objective_code,
                new_objective_code, actor_user_id, metadata_json,
                command_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(objective_id),
                str(event_type or "").strip() or "objective_updated",
                previous_objective_code,
                new_objective_code,
                actor_user_id,
                json.dumps(metadata or {}, ensure_ascii=False),
                command_id,
                timestamp,
            ),
        )

    @staticmethod
    def _sync_owner_office_goal_set_conn(
        conn: Any,
        team_id: int,
        season_year: int,
        label: str,
        timestamp: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_owner_office (
                team_id, season_year, season_goal_set, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(team_id, season_year) DO UPDATE SET
                season_goal_set = excluded.season_goal_set,
                updated_at = excluded.updated_at
            """,
            (int(team_id), int(season_year), str(label or "").strip(), timestamp),
        )

    @staticmethod
    def _sync_owner_office_goal_achieved_conn(
        conn: Any,
        team_id: int,
        season_year: int,
        label: str,
        timestamp: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_owner_office (
                team_id, season_year, season_goal_achieved, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(team_id, season_year) DO UPDATE SET
                season_goal_achieved = excluded.season_goal_achieved,
                updated_at = excluded.updated_at
            """,
            (int(team_id), int(season_year), str(label or "").strip(), timestamp),
        )
