"""Structured administrative audit events and persistence."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, ContextManager, Dict, List, Mapping, Optional, Sequence


ConnectionFactory = Callable[[], ContextManager[sqlite3.Connection]]
Clock = Callable[[], str]
TeamCodeNormalizer = Callable[[Any], Optional[str]]


def _parse_int(value: Any) -> Optional[int]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def request_id_from_headers(headers: Mapping[str, Any], existing: Any = None) -> str:
    if existing:
        return str(existing)
    raw = str(headers.get("X-Request-ID") or headers.get("X-Correlation-ID") or "")
    request_id = re.sub(r"[^A-Za-z0-9_.:-]", "", raw).strip()[:80]
    return request_id or secrets.token_urlsafe(12)


def collect_team_codes(
    normalize_team_code: TeamCodeNormalizer,
    team_code: Any = None,
    details: Optional[Dict[str, Any]] = None,
    extra_team_codes: Optional[Sequence[Any]] = None,
) -> List[str]:
    codes: List[str] = []

    def add_code(value: Any) -> None:
        normalized = normalize_team_code(value)
        if normalized and normalized not in codes:
            codes.append(normalized)

    add_code(team_code)
    for value in extra_team_codes or []:
        add_code(value)
    if isinstance(details, dict):
        for key in (
            "team_code",
            "team_a",
            "team_b",
            "from_team_code",
            "to_team_code",
            "current_team_code",
            "request_team_code",
            "owner_team_code",
        ):
            add_code(details.get(key))
        raw_team_codes = details.get("team_codes")
        if isinstance(raw_team_codes, list):
            for value in raw_team_codes:
                add_code(value)
    return codes


def resolve_entity_ids(
    entity: str,
    entity_id: Any = None,
    details: Optional[Dict[str, Any]] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], Optional[str]]:
    normalized_entity = str(entity or "").strip().lower()
    player_id: Optional[str] = None
    profile_id: Optional[str] = None

    def maybe_set_from(source: Optional[Dict[str, Any]]) -> None:
        nonlocal player_id, profile_id
        if not isinstance(source, dict):
            return
        if player_id is None:
            parsed_player = _parse_int(source.get("player_id"))
            if parsed_player is None and normalized_entity == "player" and "id" in source:
                parsed_player = _parse_int(source.get("id"))
            if parsed_player is not None:
                player_id = str(parsed_player)
        if profile_id is None:
            parsed_profile = _parse_int(source.get("profile_id"))
            if parsed_profile is not None:
                profile_id = str(parsed_profile)

    parsed_entity_id = _parse_int(entity_id)
    if normalized_entity == "player" and parsed_entity_id is not None:
        player_id = str(parsed_entity_id)
    if normalized_entity == "player_profile" and parsed_entity_id is not None:
        profile_id = str(parsed_entity_id)
    maybe_set_from(details)
    maybe_set_from(before)
    maybe_set_from(after)
    return player_id, profile_id


@dataclass(frozen=True)
class AuditEvent:
    action: str
    entity: str
    actor_email: Optional[str] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    actor_user_id: Optional[int] = None
    request_id: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    entity_id: Optional[str] = None
    team_code: Optional[str] = None
    team_codes: Sequence[str] = field(default_factory=tuple)
    player_id: Optional[str] = None
    profile_id: Optional[str] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    details: Dict[str, Any] = field(default_factory=dict)


class AuditLogService:
    def __init__(
        self,
        connect: ConnectionFactory,
        clock: Clock,
        normalize_team_code: TeamCodeNormalizer,
    ):
        self._connect = connect
        self._clock = clock
        self._normalize_team_code = normalize_team_code

    def record(self, event: AuditEvent) -> None:
        team_codes = collect_team_codes(self._normalize_team_code, event.team_code, None, event.team_codes)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_logs (
                    created_at, actor_email, actor_name, actor_role, actor_user_id,
                    request_id, method, path, action, entity, entity_id, team_code,
                    team_codes_json, player_id, profile_id, before_json, after_json, details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._clock(),
                    event.actor_email,
                    event.actor_name,
                    event.actor_role,
                    event.actor_user_id,
                    event.request_id,
                    event.method,
                    event.path,
                    event.action,
                    event.entity,
                    event.entity_id,
                    str(event.team_code).upper() if event.team_code else None,
                    json.dumps(team_codes, ensure_ascii=True) if team_codes else None,
                    str(event.player_id) if event.player_id is not None else None,
                    str(event.profile_id) if event.profile_id is not None else None,
                    self._json(event.before) if event.before is not None else None,
                    self._json(event.after) if event.after is not None else None,
                    self._json(event.details or {}),
                ),
            )
            conn.commit()

    def list(self, action: Optional[str] = None, entity: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        query = """
            SELECT
                id, created_at, actor_email, actor_name, actor_role, actor_user_id,
                request_id, method, path, action, entity, entity_id, team_code,
                team_codes_json, player_id, profile_id, before_json, after_json, details_json
            FROM admin_logs
        """
        clauses: List[str] = []
        values: List[Any] = []
        if action:
            clauses.append("action = ?")
            values.append(action.strip().lower())
        if entity:
            clauses.append("entity = ?")
            values.append(entity.strip().lower())
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 500)))

        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(query, values).fetchall()]
        for row in rows:
            row["details"] = self._parse_json(row.get("details_json"), {})
            row["team_codes"] = self._parse_json(row.get("team_codes_json"), [])
            row["before"] = self._parse_json(row.get("before_json"), None)
            row["after"] = self._parse_json(row.get("after_json"), None)
        return rows

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, default=str)

    @staticmethod
    def _parse_json(raw: Any, default: Any) -> Any:
        try:
            return json.loads(raw) if raw else default
        except (TypeError, json.JSONDecodeError):
            return default
