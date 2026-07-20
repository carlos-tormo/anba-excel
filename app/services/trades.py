"""Trade validation and command orchestration service."""

from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any, Dict, List, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..db.repositories.trades import TradeRepository
    from ..domain._values import parse_bool, parse_int
    from ..domain.trade_rules import normalize_trade_bucket
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from db.repositories.trades import TradeRepository
    from domain._values import parse_bool, parse_int
    from domain.trade_rules import normalize_trade_bucket


class TradeService:
    def __init__(self, db: Any, *, workflows: Any = None, outbox: Any = None):
        configured_repository = getattr(db, "_trade_repository", None)
        self.repository = db if isinstance(db, TradeRepository) else (
            configured_repository or TradeRepository(db)
        )
        backing_db = getattr(self.repository, "db", db)
        self.workflows = workflows or getattr(backing_db, "_workflow_repository", None)
        self.outbox = outbox or getattr(backing_db, "_outbox_repository", None)

    def normalize_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.normalize_request(payload)

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.validate(payload)

    def validate_process_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.validation_from_process_payload(payload)

    def request_team_codes(self, payload: Dict[str, Any]) -> List[str]:
        if isinstance(payload.get("selections"), (list, dict)) or isinstance(payload.get("teams"), list):
            return list(self.normalize_request(payload).get("teams") or [])
        return [
            code
            for code in (
                normalize_team_code(payload.get("team_a")),
                normalize_team_code(payload.get("team_b")),
            )
            if code
        ]

    def process_request(
        self,
        payload: Dict[str, Any],
        *,
        actor: Optional[Dict[str, Any]] = None,
        command_id: Optional[str] = None,
        notify_discord: bool = False,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        modern = isinstance(payload.get("selections"), (list, dict)) or isinstance(payload.get("teams"), list)
        force_trade = parse_bool(payload.get("force_trade"))
        if modern:
            normalized = self.normalize_request(payload)
            teams = list(normalized.get("teams") or [])
            selections = list(normalized.get("selections") or [])
            player_ids = [row.get("id") for row in selections if row.get("type") == "player"]
            asset_ids = [row.get("id") for row in selections if row.get("type") in {"pick", "right"}]
            validation = self.validate({
                **payload,
                "teams": teams,
                "selections": selections,
                "cash": normalized.get("cash") or [],
            })
            command_payload = {
                "teams": teams,
                "season": parse_int(payload.get("season")),
                "selections": selections,
                "cash": normalized.get("cash") or [],
                "trade_bucket": normalize_trade_bucket(payload.get("trade_bucket")),
            }
        else:
            team_a = normalize_team_code(payload.get("team_a")) or ""
            team_b = normalize_team_code(payload.get("team_b")) or ""
            teams = [team_a, team_b]
            player_fields = ("players_a", "players_b")
            asset_fields = ("pick_ids_a", "pick_ids_b", "right_ids_a", "right_ids_b")
            player_ids = [item for field in player_fields for item in (payload.get(field) or []) if isinstance(payload.get(field), list)]
            asset_ids = [item for field in asset_fields for item in (payload.get(field) or []) if isinstance(payload.get(field), list)]
            validation = self.validate_process_payload({**payload, "team_a": team_a, "team_b": team_b})
            command_payload = {
                "team_a": team_a,
                "team_b": team_b,
                "season": parse_int(payload.get("season")),
                **{
                    field: payload.get(field) if isinstance(payload.get(field), list) else []
                    for field in (*player_fields, *asset_fields, "no_count_players_a", "no_count_players_b")
                },
                "pick_actions_a": payload.get("pick_actions_a") if isinstance(payload.get("pick_actions_a"), (dict, list)) else {},
                "pick_actions_b": payload.get("pick_actions_b") if isinstance(payload.get("pick_actions_b"), (dict, list)) else {},
                "trade_bucket": normalize_trade_bucket(payload.get("trade_bucket")),
            }
        illegal = [issue for issue in validation.get("issues") or [] if issue.get("severity") == "illegal"]
        if illegal and not force_trade:
            return {
                "status_code": 422,
                "response": {"ok": False, "error": "trade_invalid", "validation": validation},
                "team_codes": teams,
            }
        before = self.repository.audit_snapshot(teams, player_ids, asset_ids)
        command = self.process_command(
            command_payload,
            validation=validation,
            expected_validation_hash=payload.get("validation_hash"),
            require_validation_hash=True,
            force_trade=force_trade,
            notify_discord=notify_discord,
            generate_image=generate_image,
            custom_image=custom_image,
            legacy=not modern,
            actor=actor,
            command_id=command_id,
        )
        result = command.get("result")
        authoritative = command.get("validation") or validation
        if not result and command.get("error"):
            return {
                "status_code": int(command.get("status_code") or 409),
                "response": {"ok": False, "error": command.get("error"), "validation": authoritative},
                "team_codes": teams,
            }
        audit = None
        if result:
            after = self.repository.audit_snapshot(teams, player_ids, asset_ids)
            details: Dict[str, Any] = {
                "teams": teams,
                "season": result.get("season"),
                "trade_bucket": result.get("trade_bucket"),
                "force_trade": bool(force_trade),
                "validation_issues": authoritative.get("issues") or [],
                "forced_validation_issues": illegal if force_trade else [],
                "applied_hard_caps": command.get("applied_hard_caps") or [],
            }
            if modern:
                details.update(
                    selection_count=len(command_payload.get("selections") or []),
                    team_results=result.get("teams") or [],
                )
            else:
                for field in (
                    "players_a", "players_b", "pick_ids_a", "pick_ids_b",
                    "pick_actions_a", "pick_actions_b", "right_ids_a", "right_ids_b",
                    "no_count_players_a", "no_count_players_b",
                ):
                    details[field] = command_payload.get(field) or ([] if "actions" not in field else {})
                details.update(
                    players_a_count=len(command_payload.get("players_a") or []),
                    players_b_count=len(command_payload.get("players_b") or []),
                    rights_a_count=len(command_payload.get("right_ids_a") or []),
                    rights_b_count=len(command_payload.get("right_ids_b") or []),
                    move_count_a=(result.get("team_a") or {}).get("move_count"),
                    move_count_b=(result.get("team_b") or {}).get("move_count"),
                )
            audit = {"details": details, "before": before, "after": after}
        response = result or {"ok": False}
        status_code = 200 if result else (404 if modern else 400)
        if not modern:
            response = {"ok": bool(result), "result": result, "validation": authoritative}
        return {
            "status_code": status_code,
            "response": response,
            "result": result,
            "audit": audit,
            "team_codes": teams,
            "outbox_event_ids": command.get("outbox_event_ids") or [],
        }

    def process_command(
        self,
        payload: Dict[str, Any],
        *,
        validation: Optional[Dict[str, Any]] = None,
        expected_validation_hash: Optional[str] = None,
        require_validation_hash: bool = False,
        force_trade: bool = False,
        notify_discord: bool = False,
        generate_image: bool = False,
        custom_image: Optional[Dict[str, Any]] = None,
        legacy: bool = False,
        actor: Optional[Dict[str, Any]] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        operations = self.repository._operations()
        workflow_run_id = str(command_id or secrets.token_urlsafe(24)).strip()
        if not workflow_run_id or len(workflow_run_id) > 160:
            raise ValueError("invalid_trade_command_id")
        if not self.workflows:
            raise RuntimeError("trade_workflow_repository_not_configured")
        actor_user_id, actor_email, actor_name = self.workflows.actor_fields(actor)
        timestamp = operations.now()
        initial_metadata = {
            "legacy": bool(legacy),
            "team_codes": [
                code
                for code in (
                    payload.get("teams") if isinstance(payload.get("teams"), list) else [
                        payload.get("team_a"),
                        payload.get("team_b"),
                    ]
                )
                if normalize_team_code(code)
            ],
        }
        with self.repository.transaction("IMMEDIATE") as conn:
            try:
                self.repository.create_command_run_conn(
                    conn,
                    workflow_run_id=workflow_run_id,
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    actor_name=actor_name,
                    metadata_json=json.dumps(initial_metadata, ensure_ascii=False, sort_keys=True),
                    timestamp=timestamp,
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("trade_command_already_exists") from err
            self.workflows.record_creation_conn(
                conn,
                "trade_command",
                workflow_run_id,
                "draft",
                actor=actor,
                reason="trade_command_created",
                command_id=f"{workflow_run_id}:created",
                metadata=initial_metadata,
                timestamp=timestamp,
            )
            self.workflows.transition_conn(
                conn,
                "trade_command",
                workflow_run_id,
                "validating",
                actor=actor,
                reason="trade_validation_completed",
                command_id=f"{workflow_run_id}:validating",
                updates={"updated_at": timestamp},
                metadata={"validation_requested": True},
                timestamp=timestamp,
            )

        result: Optional[Dict[str, Any]] = None
        authoritative_validation: Optional[Dict[str, Any]] = None
        applied_hard_caps: List[Dict[str, Any]] = []
        outbox_event_ids: List[int] = []
        try:
            with self.repository.transaction("IMMEDIATE") as conn:
                # Recalculate from persisted league state while the write reservation is held.
                # The caller-supplied validation object is display context only, never authority.
                authoritative_validation = (
                    self.validate_process_payload(payload)
                    if legacy
                    else self.validate(payload)
                )
                current_hash = str(authoritative_validation.get("validation_hash") or "")
                expected_hash = str(expected_validation_hash or "").strip().lower()
                rejection_error: Optional[str] = None
                rejection_status = 409
                if require_validation_hash and not expected_hash:
                    rejection_error = "trade_validation_required"
                elif expected_hash and not secrets.compare_digest(expected_hash, current_hash):
                    rejection_error = "trade_validation_stale"
                elif any(
                    issue.get("severity") == "illegal"
                    for issue in (authoritative_validation.get("issues") or [])
                ) and not force_trade:
                    rejection_error = "trade_invalid"
                    rejection_status = 422

                if rejection_error:
                    completed_at = operations.now()
                    self.workflows.transition_conn(
                        conn,
                        "trade_command",
                        workflow_run_id,
                        "rejected",
                        actor=actor,
                        reason=rejection_error,
                        command_id=f"{workflow_run_id}:rejected",
                        updates={"updated_at": completed_at, "completed_at": completed_at},
                        metadata={
                            "validation_hash": current_hash,
                            "rules_version": authoritative_validation.get("rules_version"),
                        },
                    )
                    return {
                        "result": None,
                        "validation": authoritative_validation,
                        "error": rejection_error,
                        "status_code": rejection_status,
                        "applied_hard_caps": [],
                        "outbox_event_ids": [],
                        "workflow_run_id": workflow_run_id,
                    }

                self.workflows.transition_conn(
                    conn,
                    "trade_command",
                    workflow_run_id,
                    "processing",
                    actor=actor,
                    reason="trade_processing_started",
                    command_id=f"{workflow_run_id}:processing",
                    updates={"updated_at": operations.now()},
                )
                if legacy:
                    result = self.repository.process_legacy(
                        normalize_team_code(payload.get("team_a")) or "",
                        normalize_team_code(payload.get("team_b")) or "",
                        payload.get("players_a") if isinstance(payload.get("players_a"), list) else [],
                        payload.get("players_b") if isinstance(payload.get("players_b"), list) else [],
                        pick_ids_a=payload.get("pick_ids_a") if isinstance(payload.get("pick_ids_a"), list) else [],
                        pick_ids_b=payload.get("pick_ids_b") if isinstance(payload.get("pick_ids_b"), list) else [],
                        right_ids_a=payload.get("right_ids_a") if isinstance(payload.get("right_ids_a"), list) else [],
                        right_ids_b=payload.get("right_ids_b") if isinstance(payload.get("right_ids_b"), list) else [],
                        no_count_players_a=payload.get("no_count_players_a") if isinstance(payload.get("no_count_players_a"), list) else [],
                        no_count_players_b=payload.get("no_count_players_b") if isinstance(payload.get("no_count_players_b"), list) else [],
                        pick_actions_a=payload.get("pick_actions_a"),
                        pick_actions_b=payload.get("pick_actions_b"),
                        trade_bucket=payload.get("trade_bucket"),
                        conn=conn,
                    )
                else:
                    result = self.repository.process_from_payload(payload, conn=conn)

                if not result:
                    self.workflows.transition_conn(
                        conn,
                        "trade_command",
                        workflow_run_id,
                        "rejected",
                        actor=actor,
                        reason="trade_not_processed",
                        command_id=f"{workflow_run_id}:rejected",
                        updates={"updated_at": operations.now(), "completed_at": operations.now()},
                    )
                    return {
                        "result": None,
                        "applied_hard_caps": [],
                        "outbox_event_ids": [],
                        "workflow_run_id": workflow_run_id,
                    }

                settings = self.repository.settings_conn(conn)
                season_year = (
                    parse_int(result.get("season"))
                    or parse_int(payload.get("season"))
                    or parse_int(settings.get("current_year"))
                    or 2025
                )
                result["season"] = int(season_year)

                if authoritative_validation:
                    applied_hard_caps = operations.apply_hard_cap_triggers(
                        authoritative_validation,
                        int(season_year),
                        conn=conn,
                    )
                    if applied_hard_caps:
                        result["applied_hard_caps"] = applied_hard_caps

                if notify_discord:
                    team_codes = result.get("team_codes") if isinstance(result.get("team_codes"), list) else []
                    if not team_codes:
                        team_codes = []
                        for key in ("team_a", "team_b"):
                            info = result.get(key)
                            if isinstance(info, dict) and info.get("code"):
                                team_codes.append(str(info.get("code")))
                    aggregate_id = "-".join([str(code) for code in team_codes if code]) or workflow_run_id
                    if not self.outbox:
                        raise RuntimeError("trade_outbox_repository_not_configured")
                    event_id = self.outbox.enqueue_conn(
                        conn,
                        "discord.trade_processed",
                        {
                            "result": result,
                            "generate_image": bool(generate_image),
                            "custom_image": custom_image if isinstance(custom_image, dict) else None,
                        },
                        aggregate_type="trade",
                        aggregate_id=aggregate_id,
                    )
                    if event_id:
                        outbox_event_ids.append(int(event_id))

                self.workflows.transition_conn(
                    conn,
                    "trade_command",
                    workflow_run_id,
                    "completed",
                    actor=actor,
                    reason="trade_processed",
                    command_id=f"{workflow_run_id}:completed",
                    updates={
                        "updated_at": operations.now(),
                        "completed_at": operations.now(),
                        "metadata_json": json.dumps(
                            {
                                **initial_metadata,
                                "season": int(season_year),
                                "outbox_event_ids": outbox_event_ids,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                    metadata={"season": int(season_year)},
                )
        except Exception:
            try:
                with self.repository.transaction("IMMEDIATE") as conn:
                    state = self.repository.workflow_state_conn(conn, workflow_run_id)
                    if state in {"validating", "processing"}:
                        self.workflows.transition_conn(
                            conn,
                            "trade_command",
                            workflow_run_id,
                            "failed",
                            actor=actor,
                            reason="trade_processing_failed",
                            command_id=f"{workflow_run_id}:failed",
                            updates={"updated_at": operations.now(), "completed_at": operations.now()},
                        )
            except Exception:
                pass
            raise

        return {
            "result": result,
            "validation": authoritative_validation,
            "applied_hard_caps": applied_hard_caps,
            "outbox_event_ids": outbox_event_ids,
            "workflow_run_id": workflow_run_id,
        }
