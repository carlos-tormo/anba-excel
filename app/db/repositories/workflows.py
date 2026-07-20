"""Persistence for audited workflow state transitions."""

from __future__ import annotations

import json
import secrets
from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain._values import parse_int
    from ...workflow_states import WorkflowTransitionError, workflow_definition
except ImportError:  # pragma: no cover
    from domain._values import parse_int
    from workflow_states import WorkflowTransitionError, workflow_definition

from .base import LeagueRepository


class WorkflowRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str]) -> None:
        super().__init__(db)
        self._now = now

    @staticmethod
    def actor_fields(actor: Optional[Dict[str, Any]]) -> tuple[Optional[int], Optional[str], str]:
        actor = actor or {}
        return (
            parse_int(actor.get("user_id") if actor.get("user_id") is not None else actor.get("id")),
            str(actor.get("email") or "").strip() or None,
            str(actor.get("name") or actor.get("username") or "").strip() or "system",
        )

    def record_creation_conn(
        self,
        conn: Any,
        workflow_type: str,
        resource_id: Any,
        initial_state: str,
        *,
        actor: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        command_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        workflow_definition(workflow_type)
        normalized_command_id = str(command_id or secrets.token_urlsafe(24)).strip()
        actor_user_id, actor_email, actor_name = self.actor_fields(actor)
        conn.execute(
            """
            INSERT OR IGNORE INTO workflow_transition_log (
                workflow_type, resource_id, actor_user_id, actor_email, actor_name,
                previous_state, new_state, reason, command_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, '__none__', ?, ?, ?, ?, ?)
            """,
            (
                workflow_type,
                str(resource_id),
                actor_user_id,
                actor_email,
                actor_name,
                str(initial_state),
                str(reason or "workflow_created").strip(),
                normalized_command_id,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                timestamp or self._now(),
            ),
        )
        return normalized_command_id

    def transition_conn(
        self,
        conn: Any,
        workflow_type: str,
        resource_id: Any,
        new_state: str,
        *,
        actor: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        command_id: Optional[str] = None,
        updates: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        definition = workflow_definition(workflow_type)
        normalized_state = str(new_state or "").strip().lower()
        normalized_command_id = str(command_id or secrets.token_urlsafe(24)).strip()
        resource_key = str(resource_id)
        existing = conn.execute(
            """SELECT previous_state, new_state FROM workflow_transition_log
               WHERE workflow_type = ? AND resource_id = ? AND command_id = ?""",
            (workflow_type, resource_key, normalized_command_id),
        ).fetchone()
        if existing:
            if str(existing["new_state"]) != normalized_state:
                raise WorkflowTransitionError("command_reused", "The workflow command ID was already used for a different transition.")
            return {"previous_state": str(existing["previous_state"]), "new_state": str(existing["new_state"]), "command_id": normalized_command_id, "idempotent": True}

        row = conn.execute(
            f"SELECT {definition.state_column} AS workflow_state FROM {definition.table} WHERE {definition.key_column} = ?",
            (resource_id,),
        ).fetchone()
        if not row:
            raise WorkflowTransitionError("workflow_not_found", "Workflow resource was not found.")
        previous_state = str(row["workflow_state"] or "").strip().lower()
        if normalized_state not in definition.transitions.get(previous_state, frozenset()):
            raise WorkflowTransitionError("invalid_transition", f"Transition {previous_state} -> {normalized_state} is not permitted for {workflow_type}.")

        update_values = dict(updates or {})
        unknown_columns = set(update_values) - set(definition.mutable_columns)
        if unknown_columns:
            raise WorkflowTransitionError("invalid_transition_fields", f"Unsupported workflow update fields: {', '.join(sorted(unknown_columns))}")
        assignments = [f"{definition.state_column} = ?"]
        values: List[Any] = [normalized_state]
        for column, value in update_values.items():
            assignments.append(f"{column} = ?")
            values.append(value)
        values.extend([resource_id, previous_state])
        cur = conn.execute(
            f"UPDATE {definition.table} SET {', '.join(assignments)} WHERE {definition.key_column} = ? AND {definition.state_column} = ?",
            tuple(values),
        )
        if cur.rowcount != 1:
            raise WorkflowTransitionError("transition_conflict", "Workflow state changed before this command could be applied.")

        changed_at = timestamp or self._now()
        actor_user_id, actor_email, actor_name = self.actor_fields(actor)
        conn.execute(
            """
            INSERT INTO workflow_transition_log (
                workflow_type, resource_id, actor_user_id, actor_email, actor_name,
                previous_state, new_state, reason, command_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_type, resource_key, actor_user_id, actor_email, actor_name,
                previous_state, normalized_state,
                str(reason or f"{previous_state}_to_{normalized_state}").strip(),
                normalized_command_id,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                changed_at,
            ),
        )
        return {"previous_state": previous_state, "new_state": normalized_state, "command_id": normalized_command_id, "idempotent": False}
