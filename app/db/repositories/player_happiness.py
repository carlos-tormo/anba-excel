"""Persistence for player happiness imports and event history."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

try:
    from ...domain._values import parse_int
    from ...domain.player_happiness import (
        EVENT_TRADE_REQUEST_FOLLOWUP,
        MILESTONE_PRIVATE_TRADE_REQUEST,
        MILESTONE_PUBLIC_TRADE_REQUEST,
        calculate_change,
        normalize_event_type,
        trade_request_recovery_threshold,
    )
except ImportError:  # pragma: no cover - direct script import compatibility
    from domain._values import parse_int
    from domain.player_happiness import (
        EVENT_TRADE_REQUEST_FOLLOWUP,
        MILESTONE_PRIVATE_TRADE_REQUEST,
        MILESTONE_PUBLIC_TRADE_REQUEST,
        calculate_change,
        normalize_event_type,
        trade_request_recovery_threshold,
    )

from .base import LeagueRepository

HAPPINESS_CONTRACT_SEASONS = tuple(range(2025, 2032))


class PlayerHappinessRepository(LeagueRepository):
    def connect(self) -> Any:
        return self.db.connect()

    def transaction(self, mode: str = "IMMEDIATE") -> Any:
        return self.db.transaction(mode)

    def profiles(self, conn: Any) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT pp.id AS profile_id,
                   pp.name,
                   pp.happiness,
                   pp.profile_status,
                   pp.version,
                   roster.team_code,
                   roster.team_name,
                   CASE WHEN roster.profile_id IS NOT NULL THEN 'roster'
                        WHEN fa.profile_id IS NOT NULL THEN 'free_agent'
                        ELSE pp.profile_status
                   END AS status_label
            FROM player_profiles pp
            LEFT JOIN (
                SELECT p.profile_id, MIN(t.code) AS team_code, MIN(t.name) AS team_name
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.profile_id IS NOT NULL
                GROUP BY p.profile_id
            ) roster ON roster.profile_id = pp.id
            LEFT JOIN (
                SELECT profile_id
                FROM free_agents
                WHERE profile_id IS NOT NULL
                GROUP BY profile_id
            ) fa ON fa.profile_id = pp.id
            ORDER BY pp.name COLLATE NOCASE, pp.id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def events(self, profile_id: int, *, limit: int = 100) -> List[Dict[str, Any]]:
        bounded_limit = max(1, min(int(limit or 100), 500))
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.profile_id, pp.name AS player_name,
                       e.event_type, e.event_date, e.season_year,
                       e.previous_value, e.proposed_delta, e.applied_delta,
                       e.new_value, e.source_entity_type, e.source_entity_id,
                       e.reason, e.metadata_json, e.command_id,
                       e.actor_user_id, u.email AS actor_email,
                       COALESCE(u.display_name, u.username, u.email) AS actor_name,
                       e.created_at
                FROM player_happiness_events e
                JOIN player_profiles pp ON pp.id = e.profile_id
                LEFT JOIN users u ON u.id = e.actor_user_id
                WHERE e.profile_id = ?
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT ?
                """,
                (int(profile_id), bounded_limit),
            ).fetchall()
        events: List[Dict[str, Any]] = []
        for row in rows:
            event = dict(row)
            metadata_raw = event.pop("metadata_json", None)
            try:
                event["metadata"] = json.loads(str(metadata_raw or "{}"))
            except json.JSONDecodeError:
                event["metadata"] = {}
            events.append(event)
        return events

    def profile_context(self, profile_id: int) -> Dict[str, Any] | None:
        with self.db.connect() as conn:
            return self.profile_context_conn(conn, profile_id)

    def profile_context_conn(self, conn: Any, profile_id: int) -> Dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT pp.id AS profile_id,
                   pp.name AS player_name,
                   pp.date_of_birth,
                   pp.happiness,
                   pp.version,
                   CASE WHEN roster.profile_id IS NOT NULL THEN 'roster'
                        WHEN fa.profile_id IS NOT NULL THEN 'free_agent'
                        ELSE pp.profile_status
                   END AS status_label,
                   CASE WHEN roster.profile_id IS NOT NULL THEN 1 ELSE 0 END AS active_contract,
                   roster.player_id AS active_player_id,
                   roster.team_code,
                   fa.free_agent_id
            FROM player_profiles pp
            LEFT JOIN (
                SELECT p.profile_id, MIN(p.id) AS player_id, MIN(t.code) AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.profile_id IS NOT NULL
                GROUP BY profile_id
            ) roster ON roster.profile_id = pp.id
            LEFT JOIN (
                SELECT profile_id, MIN(id) AS free_agent_id
                FROM free_agents
                WHERE profile_id IS NOT NULL
                GROUP BY profile_id
            ) fa ON fa.profile_id = pp.id
            WHERE pp.id = ?
            """,
            (int(profile_id),),
        ).fetchone()
        if not row:
            return None
        context = dict(row)
        current_year_row = conn.execute("SELECT value FROM app_settings WHERE key = 'current_year'").fetchone()
        current_year = int(current_year_row["value"]) if current_year_row and str(current_year_row["value"] or "").isdigit() else HAPPINESS_CONTRACT_SEASONS[0]
        if current_year not in HAPPINESS_CONTRACT_SEASONS:
            current_year = HAPPINESS_CONTRACT_SEASONS[0]
        context["current_year"] = current_year
        context["last_contract_year"] = False
        player_id = context.get("active_player_id")
        if player_id is not None:
            salary_columns = ", ".join(f"salary_{season}_text" for season in HAPPINESS_CONTRACT_SEASONS)
            salary_row = conn.execute(
                f"SELECT {salary_columns} FROM players WHERE id = ?",
                (int(player_id),),
            ).fetchone()
            if salary_row:
                current_salary = str(salary_row[f"salary_{current_year}_text"] or "").strip()
                future_salary = any(
                    str(salary_row[f"salary_{season}_text"] or "").strip()
                    for season in HAPPINESS_CONTRACT_SEASONS
                    if season > current_year
                )
                context["last_contract_year"] = bool(current_salary and not future_salary)
        return context

    @staticmethod
    def _season_year_for_date(value: Any) -> int | None:
        raw = str(value or "").strip()
        if len(raw) < 10:
            return None
        year = parse_int(raw[:4])
        month = parse_int(raw[5:7])
        if year is None or month is None:
            return None
        return year if month >= 7 else year - 1

    def roster_impact_targets(
        self,
        team_code: str,
        *,
        excluded_profile_id: int | None = None,
        excluded_profile_ids: Sequence[int] | None = None,
    ) -> Dict[str, Any]:
        normalized_team = str(team_code or "").strip().upper()
        if not normalized_team:
            return {"team_code": "", "current_year": None, "targets": []}
        with self.db.connect() as conn:
            return self.roster_impact_targets_conn(
                conn,
                normalized_team,
                excluded_profile_id=excluded_profile_id,
                excluded_profile_ids=excluded_profile_ids,
            )

    def roster_impact_targets_conn(
        self,
        conn: Any,
        team_code: str,
        *,
        excluded_profile_id: int | None = None,
        excluded_profile_ids: Sequence[int] | None = None,
    ) -> Dict[str, Any]:
        normalized_team = str(team_code or "").strip().upper()
        if not normalized_team:
            return {"team_code": "", "current_year": None, "targets": []}
        excluded_ids = {
            int(parsed)
            for parsed in (parse_int(value) for value in (excluded_profile_ids or []))
            if parsed is not None
        }
        if excluded_profile_id is not None:
            excluded_ids.add(int(excluded_profile_id))
        current_year_row = conn.execute("SELECT value FROM app_settings WHERE key = 'current_year'").fetchone()
        current_year = parse_int(current_year_row["value"] if current_year_row else None) or HAPPINESS_CONTRACT_SEASONS[0]
        rows = conn.execute(
            """
            SELECT p.id AS player_id,
                   p.profile_id,
                   COALESCE(pp.name, p.name) AS player_name,
                   p.rating,
                   pp.happiness,
                   pp.date_of_birth,
                   p.created_at AS roster_created_at,
                   t.code AS team_code
            FROM players p
            JOIN teams t ON t.id = p.team_id
            LEFT JOIN player_profiles pp ON pp.id = p.profile_id
            WHERE t.code = ?
              AND p.profile_id IS NOT NULL
            ORDER BY p.row_order, p.id
            """,
            (normalized_team,),
        ).fetchall()
        targets: List[Dict[str, Any]] = []
        for row in rows:
            profile_id = parse_int(row["profile_id"])
            if profile_id is None or int(profile_id) in excluded_ids:
                continue
            joined_row = conn.execute(
                """
                SELECT MIN(created_at) AS joined_at
                FROM player_transactions
                WHERE profile_id = ?
                  AND (team_code = ? OR to_team_code = ?)
                  AND action IN ('create', 'sign', 'move', 'waiver_claim', 'trade')
                """,
                (int(profile_id), normalized_team, normalized_team),
            ).fetchone()
            joined_at = (joined_row["joined_at"] if joined_row else None) or row["roster_created_at"]
            joined_season_year = self._season_year_for_date(joined_at)
            targets.append(
                {
                    **dict(row),
                    "profile_id": int(profile_id),
                    "joined_at": joined_at,
                    "joined_season_year": joined_season_year,
                    "first_season_with_team": joined_season_year == current_year,
                }
            )
        return {"team_code": normalized_team, "current_year": current_year, "targets": targets}

    def drafted_rating_threshold_subject_conn(
        self,
        conn: Any,
        player_id: int,
    ) -> Dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT p.id AS player_id,
                   p.profile_id,
                   COALESCE(pp.name, p.name) AS player_name,
                   p.rating,
                   p.bird_rights,
                   t.code AS team_code,
                   EXISTS (
                       SELECT 1
                       FROM player_transactions tx
                       WHERE tx.profile_id = p.profile_id
                         AND tx.action = 'trade'
                       LIMIT 1
                   ) AS has_trade_transaction
            FROM players p
            JOIN teams t ON t.id = p.team_id
            LEFT JOIN player_profiles pp ON pp.id = p.profile_id
            WHERE p.id = ?
              AND p.profile_id IS NOT NULL
            """,
            (int(player_id),),
        ).fetchone()
        return dict(row) if row else None

    def latest_zero_threshold_cohort_conn(self, conn: Any, profile_id: int) -> Dict[str, Any] | None:
        rows = conn.execute(
            """
            SELECT id, metadata_json, command_id, created_at
            FROM player_happiness_events
            WHERE source_entity_type = 'player_zero_threshold'
              AND source_entity_id = ?
              AND metadata_json LIKE '%"zero_threshold"%'
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (str(int(profile_id)),),
        ).fetchall()
        for row in rows:
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except json.JSONDecodeError:
                continue
            zero_threshold = metadata.get("zero_threshold")
            if isinstance(zero_threshold, dict):
                cohort = zero_threshold.get("cohort_profile_ids")
                if isinstance(cohort, list):
                    return {
                        "event_id": int(row["id"]),
                        "command_id": row["command_id"],
                        "created_at": row["created_at"],
                        "metadata": metadata,
                        "zero_threshold": zero_threshold,
                    }
        return None

    def trade_request_followup_candidates(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id AS request_event_id,
                       e.profile_id,
                       pp.name AS player_name,
                       pp.happiness AS current_happiness,
                       e.event_date AS request_event_date,
                       e.created_at AS request_created_at,
                       e.metadata_json
                FROM player_happiness_events e
                JOIN player_profiles pp ON pp.id = e.profile_id
                WHERE e.metadata_json LIKE '%"triggered_happiness_milestone"%'
                  AND (
                    e.metadata_json LIKE '%"private_trade_request"%'
                    OR e.metadata_json LIKE '%"public_trade_request"%'
                  )
                ORDER BY e.profile_id, e.created_at, e.id
                """
            ).fetchall()
            by_profile: Dict[int, Dict[str, Any]] = {}
            for row in rows:
                candidate = self._trade_request_followup_candidate_conn(conn, row)
                if not candidate:
                    continue
                profile_id = int(candidate["profile_id"])
                if profile_id not in by_profile:
                    by_profile[profile_id] = candidate
            return list(by_profile.values())

    def _trade_request_followup_candidate_conn(self, conn: Any, row: Any) -> Dict[str, Any] | None:
        payload = dict(row)
        try:
            metadata = json.loads(str(payload.get("metadata_json") or "{}"))
        except json.JSONDecodeError:
            return None
        triggered = metadata.get("triggered_happiness_milestone")
        if not isinstance(triggered, dict):
            return None
        milestone_code = str(triggered.get("code") or "").strip()
        if milestone_code not in {MILESTONE_PRIVATE_TRADE_REQUEST, MILESTONE_PUBLIC_TRADE_REQUEST}:
            return None
        profile_id = int(payload["profile_id"])
        request_created_at = str(payload.get("request_created_at") or "").strip()
        contract_context = str(triggered.get("contract_context") or metadata.get("contract_context") or "").strip()
        is_last_contract_year = contract_context == "last_year"
        current_happiness = float(payload.get("current_happiness") or 0)
        if current_happiness >= trade_request_recovery_threshold(is_last_contract_year=is_last_contract_year):
            return None
        recovered = conn.execute(
            """
            SELECT 1
            FROM player_happiness_events
            WHERE profile_id = ?
              AND created_at > ?
              AND new_value >= ?
            LIMIT 1
            """,
            (
                profile_id,
                request_created_at,
                trade_request_recovery_threshold(is_last_contract_year=is_last_contract_year),
            ),
        ).fetchone()
        if recovered:
            return None
        traded = conn.execute(
            """
            SELECT 1
            FROM player_transactions
            WHERE profile_id = ?
              AND action = 'trade'
              AND created_at > ?
            LIMIT 1
            """,
            (profile_id, request_created_at),
        ).fetchone()
        if traded:
            return None
        applied_rows = conn.execute(
            """
            SELECT metadata_json
            FROM player_happiness_events
            WHERE profile_id = ?
              AND event_type = ?
              AND source_entity_id = ?
            """,
            (profile_id, EVENT_TRADE_REQUEST_FOLLOWUP, str(int(payload["request_event_id"]))),
        ).fetchall()
        applied_stages: List[str] = []
        for applied_row in applied_rows:
            try:
                applied_metadata = json.loads(str(applied_row["metadata_json"] or "{}"))
            except json.JSONDecodeError:
                continue
            stage = str(applied_metadata.get("trade_request_followup_stage") or "").strip()
            if stage:
                applied_stages.append(stage)
        return {
            "request_event_id": int(payload["request_event_id"]),
            "profile_id": profile_id,
            "player_name": str(payload.get("player_name") or "").strip(),
            "request_date": str(payload.get("request_event_date") or payload.get("request_created_at") or "")[:10],
            "request_created_at": request_created_at,
            "current_happiness": current_happiness,
            "milestone_code": milestone_code,
            "contract_context": contract_context or ("last_year" if is_last_contract_year else "multiyear"),
            "is_last_contract_year": is_last_contract_year,
            "applied_stages": applied_stages,
        }

    def apply_event(
        self,
        profile_id: int,
        event: Dict[str, Any],
        *,
        timestamp: str,
        command_id: str,
        actor_user_id: int | None,
    ) -> Dict[str, Any]:
        with self.db.transaction("IMMEDIATE") as conn:
            return self.apply_event_conn(
                conn,
                profile_id,
                event,
                timestamp=timestamp,
                command_id=command_id,
                actor_user_id=actor_user_id,
            )

    def apply_event_conn(
        self,
        conn: Any,
        profile_id: int,
        event: Dict[str, Any],
        *,
        timestamp: str,
        command_id: str,
        actor_user_id: int | None,
    ) -> Dict[str, Any]:
        row = conn.execute(
            """
            SELECT id, name, happiness, version
            FROM player_profiles
            WHERE id = ?
            """,
            (int(profile_id),),
        ).fetchone()
        if not row:
            raise ValueError("player_profile_not_found")
        expected_version = event.get("expected_version")
        current_version = int(row["version"] or 1)
        if expected_version is not None and int(expected_version) != current_version:
            raise ValueError("stale_entity_version")
        change = calculate_change(
            row["happiness"] or 0,
            new_value=event.get("new_value"),
            proposed_delta=event.get("proposed_delta"),
            applied_delta=event.get("applied_delta"),
        )
        cur = conn.execute(
            """
            UPDATE player_profiles
            SET happiness = ?,
                version = version + 1,
                updated_at = ?
            WHERE id = ?
              AND version = ?
            """,
            (change.new_value, timestamp, int(profile_id), current_version),
        )
        if cur.rowcount != 1:
            raise ValueError("stale_entity_version")
        event_type = normalize_event_type(event.get("event_type") or "manual_adjustment")
        conn.execute(
            """
            INSERT INTO player_happiness_events (
                profile_id, event_type, event_date, season_year,
                previous_value, proposed_delta, applied_delta, new_value,
                source_entity_type, source_entity_id, reason, metadata_json,
                command_id, actor_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(profile_id),
                event_type,
                event.get("event_date"),
                event.get("season_year"),
                change.previous_value,
                change.proposed_delta,
                change.applied_delta,
                change.new_value,
                str(event.get("source_entity_type") or "admin").strip() or "admin",
                str(event.get("source_entity_id") or command_id).strip() or command_id,
                str(event.get("reason") or "").strip() or None,
                json.dumps(event.get("metadata") or {}, ensure_ascii=False),
                command_id,
                actor_user_id,
                timestamp,
            ),
        )
        return {
            "ok": True,
            "profile_id": int(profile_id),
            "player_name": str(row["name"] or "").strip(),
            "event_type": event_type,
            "previous_happiness": change.previous_value,
            "proposed_delta": change.proposed_delta,
            "applied_delta": change.applied_delta,
            "new_happiness": change.new_value,
            "version": current_version + 1,
            "command_id": command_id,
        }

    @staticmethod
    def has_event_command_id_conn(conn: Any, command_id: Any) -> bool:
        normalized = str(command_id or "").strip()
        if not normalized:
            return False
        row = conn.execute(
            "SELECT 1 FROM player_happiness_events WHERE command_id = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        return row is not None

    def apply_baseline_import(
        self,
        records: Sequence[Dict[str, Any]],
        *,
        timestamp: str,
        command_id: str,
        actor_user_id: int | None,
    ) -> Dict[str, Any]:
        changed_count = 0
        unchanged_count = 0
        updated_profiles: List[Dict[str, Any]] = []
        with self.db.transaction("IMMEDIATE") as conn:
            for record in records:
                profile_id = int(record["profile_id"])
                expected_version = int(record["expected_version"])
                new_value = float(record["happiness"])
                row = conn.execute(
                    """
                    SELECT id, name, happiness, version
                    FROM player_profiles
                    WHERE id = ?
                    """,
                    (profile_id,),
                ).fetchone()
                if not row:
                    raise ValueError("invalid_records")
                current_name = str(row["name"] or "").strip()
                if current_name != str(record.get("player_name") or "").strip():
                    raise ValueError("happiness_import_target_changed")
                current_version = int(row["version"])
                if current_version != expected_version:
                    raise ValueError("stale_entity_version")
                previous_value = float(row["happiness"] or 0)
                applied_delta = new_value - previous_value
                cur = conn.execute(
                    """
                    UPDATE player_profiles
                    SET happiness = ?,
                        version = version + 1,
                        updated_at = ?
                    WHERE id = ?
                      AND version = ?
                    """,
                    (new_value, timestamp, profile_id, current_version),
                )
                if cur.rowcount != 1:
                    raise ValueError("stale_entity_version")
                conn.execute(
                    """
                    INSERT INTO player_happiness_events (
                        profile_id, event_type, event_date, season_year,
                        previous_value, proposed_delta, applied_delta, new_value,
                        source_entity_type, source_entity_id, reason, metadata_json,
                        command_id, actor_user_id, created_at
                    ) VALUES (?, 'baseline_import', ?, NULL, ?, ?, ?, ?, 'admin_import', ?,
                              ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        str(record.get("event_date") or "")[:10] or None,
                        previous_value,
                        applied_delta,
                        applied_delta,
                        new_value,
                        command_id,
                        str(record.get("reason") or "Initial happiness baseline import").strip(),
                        json.dumps(
                            {
                                "input_player_name": record.get("input_player_name"),
                                "match_method": record.get("match_method"),
                            },
                            ensure_ascii=False,
                        ),
                        command_id,
                        actor_user_id,
                        timestamp,
                    ),
                )
                if previous_value == new_value:
                    unchanged_count += 1
                else:
                    changed_count += 1
                updated_profiles.append(
                    {
                        "profile_id": profile_id,
                        "player_name": current_name,
                        "previous_happiness": previous_value,
                        "new_happiness": new_value,
                        "version": current_version + 1,
                    }
                )
        return {
            "ok": True,
            "record_count": changed_count + unchanged_count,
            "changed_count": changed_count,
            "unchanged_count": unchanged_count,
            "updated_profiles": updated_profiles,
        }
