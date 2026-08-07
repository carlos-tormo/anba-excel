"""Player happiness import preview/apply orchestration."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain._values import parse_float, parse_int
    from ..domain.player_happiness import (
        DRAFTED_RATING_THRESHOLD,
        DRAFTED_RATING_THRESHOLD_DELTA,
        EVENT_BASELINE_IMPORT,
        EVENT_DRAFTED_RATING_THRESHOLD,
        EVENT_MANUAL_ADJUSTMENT,
        EVENT_MODIFIER,
        EVENT_ROSTER_IMPACT,
        EVENT_TEAMMATE_ZERO_THRESHOLD,
        EVENT_TEAM_JOIN,
        EVENT_TEAM_OBJECTIVE_JOIN_CONTEXT,
        EVENT_TEAM_OBJECTIVE_RESOLUTION,
        EVENT_TEAM_OBJECTIVE_SET,
        EVENT_TRADE_REQUEST_FOLLOWUP,
        EVENT_GM_CHANGE,
        TEAMMATE_ZERO_INITIAL_DELTA,
        TEAMMATE_ZERO_RELIEF_DELTA,
        TEAMMATE_ZERO_RETURN_COHORT_DELTA,
        calculate_change,
        classify_happiness_milestone,
        drafted_rating_threshold_crossed,
        is_free_agent_context,
        is_rookie_scale_contract_type,
        normalize_event_type,
        normalize_happiness,
        recency_recalculated_happiness,
        roster_impact_player_delta,
        roster_rating_impact_delta,
        team_join_happiness,
        team_objective_happiness_delta,
        team_objective_happiness_delta_change,
        team_objective_rating_band,
        team_objective_resolution_delta,
        trade_request_followup_penalties,
        trade_request_eligible,
        triggered_happiness_milestone,
        zero_happiness_transition,
    )
    from ..domain.team_objectives import objective_label, normalize_objective_code
    from ..domain.gm_attractiveness import (
        GM_CHANGE_ENTER,
        GM_CHANGE_LEAVE,
        gm_change_happiness_delta,
    )
except ImportError:  # pragma: no cover
    from domain._values import parse_float, parse_int
    from domain.player_happiness import (
        DRAFTED_RATING_THRESHOLD,
        DRAFTED_RATING_THRESHOLD_DELTA,
        EVENT_BASELINE_IMPORT,
        EVENT_DRAFTED_RATING_THRESHOLD,
        EVENT_MANUAL_ADJUSTMENT,
        EVENT_MODIFIER,
        EVENT_ROSTER_IMPACT,
        EVENT_TEAMMATE_ZERO_THRESHOLD,
        EVENT_TEAM_JOIN,
        EVENT_TEAM_OBJECTIVE_JOIN_CONTEXT,
        EVENT_TEAM_OBJECTIVE_RESOLUTION,
        EVENT_TEAM_OBJECTIVE_SET,
        EVENT_TRADE_REQUEST_FOLLOWUP,
        EVENT_GM_CHANGE,
        TEAMMATE_ZERO_INITIAL_DELTA,
        TEAMMATE_ZERO_RELIEF_DELTA,
        TEAMMATE_ZERO_RETURN_COHORT_DELTA,
        calculate_change,
        classify_happiness_milestone,
        drafted_rating_threshold_crossed,
        is_free_agent_context,
        is_rookie_scale_contract_type,
        normalize_event_type,
        normalize_happiness,
        recency_recalculated_happiness,
        roster_impact_player_delta,
        roster_rating_impact_delta,
        team_join_happiness,
        team_objective_happiness_delta,
        team_objective_happiness_delta_change,
        team_objective_rating_band,
        team_objective_resolution_delta,
        trade_request_followup_penalties,
        trade_request_eligible,
        triggered_happiness_milestone,
        zero_happiness_transition,
    )
    from domain.team_objectives import objective_label, normalize_objective_code
    from domain.gm_attractiveness import (
        GM_CHANGE_ENTER,
        GM_CHANGE_LEAVE,
        gm_change_happiness_delta,
    )


def normalize_happiness_import_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_happiness_value(value: Any) -> int | float:
    return normalize_happiness(value)


class PlayerHappinessService:
    def __init__(self, repository: Any, *, now: Callable[[], str]) -> None:
        self.repository = repository
        self._now = now

    def events(self, profile_id: int, *, limit: int = 100) -> Dict[str, Any]:
        rows = self.repository.events(int(profile_id), limit=limit)
        return {"profile_id": int(profile_id), "events": rows}

    @staticmethod
    def _milestone_payload(value: Any, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        milestone = classify_happiness_milestone(
            value,
            is_last_contract_year=bool(context.get("last_contract_year")),
        )
        return milestone.as_dict() if milestone else None

    @staticmethod
    def _triggered_milestone_payload(
        previous_value: Any,
        new_value: Any,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        milestone = triggered_happiness_milestone(
            previous_value,
            new_value,
            is_last_contract_year=bool(context.get("last_contract_year")),
        )
        return milestone.as_dict() if milestone else None

    def _with_milestone_output(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        current = self._milestone_payload(result.get("new_happiness"), context)
        triggered = self._triggered_milestone_payload(
            result.get("previous_happiness"),
            result.get("new_happiness"),
            context,
        )
        result["contract_context"] = "last_year" if context.get("last_contract_year") else "multiyear"
        result["happiness_milestone"] = current
        result["triggered_happiness_milestone"] = triggered
        result["private_admin_notification"] = bool(triggered and triggered.get("admin_notification"))
        result["discord_news_eligible"] = bool(triggered and triggered.get("discord_news_eligible"))
        return result

    def status(self, profile_id: int) -> Dict[str, Any]:
        context = self.repository.profile_context(int(profile_id))
        if not context:
            raise ValueError("player_profile_not_found")
        current_happiness = float(context.get("happiness") or 0)
        return {
            **context,
            "eligible_for_trade_request": trade_request_eligible(current_happiness),
            "happiness_frozen": is_free_agent_context(context.get("status_label"), context.get("active_contract")),
            "contract_context": "last_year" if context.get("last_contract_year") else "multiyear",
            "happiness_milestone": self._milestone_payload(current_happiness, context),
        }

    def recalculate_recency(
        self,
        *,
        current_year: Any = None,
        profile_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        timestamp = self._now()
        result = self.repository.recalculate_recency(
            current_year=parse_int(current_year),
            profile_ids=profile_ids,
            timestamp=timestamp,
        )
        result["command_id"] = f"player-happiness:recency-recalculation:{result.get('current_year')}"
        result["validation_result"] = "valid"
        result["entity_versions"] = {
            "current_year": result.get("current_year"),
            "updated_count": result.get("updated_count"),
        }
        return result

    def recalculate_recency_conn(
        self,
        conn: Any,
        *,
        current_year: Any = None,
        profile_ids: Optional[List[int]] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = self.repository.recalculate_recency_conn(
            conn,
            current_year=parse_int(current_year),
            profile_ids=profile_ids,
            timestamp=timestamp or self._now(),
        )
        result["command_id"] = f"player-happiness:recency-recalculation:{result.get('current_year')}"
        result["validation_result"] = "valid"
        result["entity_versions"] = {
            "current_year": result.get("current_year"),
            "updated_count": result.get("updated_count"),
        }
        return result

    def set_value(
        self,
        profile_id: int,
        payload: Dict[str, Any],
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        new_value = normalize_happiness_value(payload.get("happiness", payload.get("new_happiness")))
        expected_version = parse_int(payload.get("expected_version"))
        timestamp = self._now()
        command_id = f"player-happiness:{int(profile_id)}:manual:{timestamp}"
        actor_user_id = parse_int((actor or {}).get("user_id"))
        context = self.repository.profile_context(int(profile_id)) or {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata = {
            **metadata,
            "contract_context": "last_year" if context.get("last_contract_year") else "multiyear",
            "happiness_milestone": self._milestone_payload(new_value, context),
            "triggered_happiness_milestone": self._triggered_milestone_payload(
                context.get("happiness") or 0,
                new_value,
                context,
            ),
        }
        result = self.repository.apply_event(
            int(profile_id),
            {
                "event_type": normalize_event_type(payload.get("event_type") or EVENT_MANUAL_ADJUSTMENT),
                "event_date": str(payload.get("event_date") or "")[:10] or None,
                "season_year": parse_int(payload.get("season_year")),
                "proposed_delta": parse_float(str(payload.get("proposed_delta"))) if payload.get("proposed_delta") is not None else None,
                "applied_delta": parse_float(str(payload.get("applied_delta"))) if payload.get("applied_delta") is not None else None,
                "new_value": float(new_value),
                "source_entity_type": str(payload.get("source_entity_type") or "admin_manual").strip() or "admin_manual",
                "source_entity_id": str(payload.get("source_entity_id") or command_id).strip() or command_id,
                "reason": str(payload.get("reason") or "Manual happiness adjustment").strip(),
                "metadata": metadata,
                "expected_version": expected_version,
            },
            timestamp=timestamp,
            command_id=command_id,
            actor_user_id=actor_user_id,
        )
        result["validation_result"] = "valid"
        result["entity_versions"] = {
            "profile_id": int(profile_id),
            "version": result.get("version"),
            "new_happiness": result.get("new_happiness"),
        }
        result["eligible_for_trade_request"] = trade_request_eligible(result.get("new_happiness"))
        result = self._with_milestone_output(result, context)
        result["zero_threshold_impact"] = self.apply_zero_threshold_transition(
            profile_id=int(profile_id),
            previous_value=result.get("previous_happiness"),
            new_value=result.get("new_happiness"),
            source_event=result,
            actor=actor,
        )
        return result

    def apply_modifier(
        self,
        profile_id: int,
        proposed_delta: Any,
        *,
        event_type: str = EVENT_MODIFIER,
        reason: str = "",
        source_entity_type: str = "system",
        source_entity_id: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor: Optional[Dict[str, Any]] = None,
        trigger_zero_rules: bool = True,
    ) -> Dict[str, Any]:
        context = self.repository.profile_context(int(profile_id))
        if not context:
            raise ValueError("player_profile_not_found")
        if is_free_agent_context(context.get("status_label"), context.get("active_contract")):
            return {
                "ok": True,
                "skipped": True,
                "reason": "free_agent_happiness_frozen",
                "profile_id": int(profile_id),
                "current_happiness": float(context.get("happiness") or 0),
            }
        change = calculate_change(context.get("happiness") or 0, proposed_delta=proposed_delta)
        timestamp = self._now()
        command_id = f"player-happiness:{int(profile_id)}:{normalize_event_type(event_type)}:{timestamp}"
        metadata = {
            **(metadata or {}),
            "contract_context": "last_year" if context.get("last_contract_year") else "multiyear",
            "happiness_milestone": self._milestone_payload(change.new_value, context),
            "triggered_happiness_milestone": self._triggered_milestone_payload(
                change.previous_value,
                change.new_value,
                context,
            ),
        }
        result = self.repository.apply_event(
            int(profile_id),
            {
                "event_type": normalize_event_type(event_type),
                "proposed_delta": change.proposed_delta,
                "applied_delta": change.applied_delta,
                "new_value": change.new_value,
                "source_entity_type": source_entity_type,
                "source_entity_id": str(source_entity_id or command_id),
                "reason": reason,
                "metadata": metadata,
            },
            timestamp=timestamp,
            command_id=command_id,
            actor_user_id=parse_int((actor or {}).get("user_id")),
        )
        result["eligible_for_trade_request"] = change.eligible_for_trade_request
        result["validation_result"] = "valid"
        result["entity_versions"] = {"profile_id": int(profile_id), "version": result.get("version")}
        result = self._with_milestone_output(result, context)
        if trigger_zero_rules:
            result["zero_threshold_impact"] = self.apply_zero_threshold_transition(
                profile_id=int(profile_id),
                previous_value=result.get("previous_happiness"),
                new_value=result.get("new_happiness"),
                source_event=result,
                actor=actor,
            )
        return result

    def apply_modifier_conn(
        self,
        conn: Any,
        profile_id: int,
        proposed_delta: Any,
        *,
        event_type: str = EVENT_MODIFIER,
        reason: str = "",
        source_entity_type: str = "system",
        source_entity_id: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        command_id: Optional[str] = None,
        trigger_zero_rules: bool = True,
    ) -> Dict[str, Any]:
        context = self.repository.profile_context_conn(conn, int(profile_id))
        if not context:
            raise ValueError("player_profile_not_found")
        if is_free_agent_context(context.get("status_label"), context.get("active_contract")):
            return {
                "ok": True,
                "skipped": True,
                "reason": "free_agent_happiness_frozen",
                "profile_id": int(profile_id),
                "current_happiness": float(context.get("happiness") or 0),
            }
        change = calculate_change(context.get("happiness") or 0, proposed_delta=proposed_delta)
        event_type = normalize_event_type(event_type)
        timestamp = timestamp or self._now()
        command_id = command_id or f"player-happiness:{int(profile_id)}:{event_type}:{timestamp}"
        metadata = {
            **(metadata or {}),
            "contract_context": "last_year" if context.get("last_contract_year") else "multiyear",
            "happiness_milestone": self._milestone_payload(change.new_value, context),
            "triggered_happiness_milestone": self._triggered_milestone_payload(
                change.previous_value,
                change.new_value,
                context,
            ),
        }
        result = self.repository.apply_event_conn(
            conn,
            int(profile_id),
            {
                "event_type": event_type,
                "proposed_delta": change.proposed_delta,
                "applied_delta": change.applied_delta,
                "new_value": change.new_value,
                "source_entity_type": source_entity_type,
                "source_entity_id": str(source_entity_id or command_id),
                "reason": reason,
                "metadata": metadata,
            },
            timestamp=timestamp,
            command_id=command_id,
            actor_user_id=parse_int((actor or {}).get("user_id")),
        )
        result["eligible_for_trade_request"] = change.eligible_for_trade_request
        result["validation_result"] = "valid"
        result["entity_versions"] = {"profile_id": int(profile_id), "version": result.get("version")}
        result = self._with_milestone_output(result, context)
        if trigger_zero_rules:
            result["zero_threshold_impact"] = self.apply_zero_threshold_transition_conn(
                conn,
                profile_id=int(profile_id),
                previous_value=result.get("previous_happiness"),
                new_value=result.get("new_happiness"),
                source_event=result,
                actor=actor,
                timestamp=timestamp,
            )
        return result

    def reset_for_team_join(
        self,
        profile_id: int,
        team_code: str,
        *,
        player_id: Any = None,
        free_agent_id: Any = None,
        modifiers: Optional[List[Any]] = None,
        modifier_details: Optional[List[Dict[str, Any]]] = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = self._now()
        return self.reset_for_team_join_conn(
            None,
            profile_id,
            team_code,
            player_id=player_id,
            free_agent_id=free_agent_id,
            modifiers=modifiers,
            modifier_details=modifier_details,
            actor=actor,
            timestamp=timestamp,
        )

    def reset_for_team_join_conn(
        self,
        conn: Any,
        profile_id: int,
        team_code: str,
        *,
        player_id: Any = None,
        free_agent_id: Any = None,
        modifiers: Optional[List[Any]] = None,
        modifier_details: Optional[List[Dict[str, Any]]] = None,
        actor: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        command_id: Optional[str] = None,
        source_entity_type: str = "team_join",
        source_entity_id: Any = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        new_value = team_join_happiness(modifiers)
        timestamp = timestamp or self._now()
        command_id = command_id or f"player-happiness:{int(profile_id)}:team-join:{timestamp}"
        context = {"last_contract_year": False}
        event = {
            "event_type": EVENT_TEAM_JOIN,
            "new_value": new_value,
            "source_entity_type": source_entity_type,
            "source_entity_id": str(source_entity_id or player_id or free_agent_id or command_id),
            "reason": f"Player joined {str(team_code or '').upper()}",
            "metadata": {
                **(extra_metadata or {}),
                "team_code": str(team_code or "").upper(),
                "player_id": player_id,
                "free_agent_id": free_agent_id,
                "base_happiness": new_value if not modifiers else 7.0,
                "modifiers": modifiers or [],
                "modifier_details": modifier_details or [],
            },
        }
        if conn is not None:
            result = self.repository.apply_event_conn(
                conn,
                int(profile_id),
                event,
                timestamp=timestamp,
                command_id=command_id,
                actor_user_id=parse_int((actor or {}).get("user_id")),
            )
        else:
            result = self.repository.apply_event(
                int(profile_id),
                event,
                timestamp=timestamp,
                command_id=command_id,
                actor_user_id=parse_int((actor or {}).get("user_id")),
            )
        result["eligible_for_trade_request"] = trade_request_eligible(result.get("new_happiness"))
        result["validation_result"] = "valid"
        result["entity_versions"] = {"profile_id": int(profile_id), "version": result.get("version")}
        return self._with_milestone_output(result, context)

    def team_join_objective_modifier(
        self,
        team_objectives: Any,
        team_code: Any,
        player: Dict[str, Any],
        *,
        conn: Any = None,
        on_date: Any = None,
    ) -> Optional[Dict[str, Any]]:
        if team_objectives is None:
            return None
        if conn is not None and hasattr(team_objectives, "for_player_join_context_conn"):
            context = team_objectives.for_player_join_context_conn(conn, team_code)
        else:
            context = team_objectives.for_player_join_context(team_code)
        objective_code = context.get("join_objective_code")
        if not objective_code:
            return None
        modifier = self.team_objective_join_modifier(
            objective_code,
            (player or {}).get("rating"),
            date_of_birth=(player or {}).get("date_of_birth") or (player or {}).get("profile_date_of_birth"),
            on_date=on_date,
        )
        modifier["team_code"] = str(team_code or "").strip().upper()
        modifier["season_year"] = context.get("season_year")
        modifier["objective_label"] = context.get("join_objective_label")
        return modifier

    def apply_roster_impact(
        self,
        *,
        team_code: str,
        subject_player: Dict[str, Any],
        direction: str,
        source_entity_type: str,
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
        excluded_profile_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        base_delta = roster_rating_impact_delta((subject_player or {}).get("rating"), direction)
        normalized_team = str(team_code or "").strip().upper()
        subject_profile_id = parse_int((subject_player or {}).get("profile_id"))
        subject_player_id = parse_int((subject_player or {}).get("id") or (subject_player or {}).get("player_id"))
        if not normalized_team or not base_delta:
            return {
                "ok": True,
                "team_code": normalized_team,
                "base_delta": base_delta,
                "affected_count": 0,
                "events": [],
            }
        target_data = self.repository.roster_impact_targets(
            normalized_team,
            excluded_profile_id=subject_profile_id,
            excluded_profile_ids=excluded_profile_ids,
        )
        timestamp = self._now()
        events: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for target in target_data.get("targets") or []:
            applied_delta = roster_impact_player_delta(
                base_delta,
                first_season_with_team=bool(target.get("first_season_with_team")),
                date_of_birth=target.get("date_of_birth"),
                on_date=timestamp,
            )
            if not applied_delta:
                skipped.append(
                    {
                        "profile_id": target.get("profile_id"),
                        "player_name": target.get("player_name"),
                        "reason": "roster_impact_delta_zero",
                    }
                )
                continue
            result = self.apply_modifier(
                int(target["profile_id"]),
                applied_delta,
                event_type=EVENT_ROSTER_IMPACT,
                reason=self._roster_impact_reason(subject_player, direction, normalized_team, applied_delta),
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id or subject_player_id,
                metadata={
                    "team_code": normalized_team,
                    "direction": str(direction or "").strip().lower(),
                    "subject_player_id": subject_player_id,
                    "subject_profile_id": subject_profile_id,
                    "subject_player_name": str((subject_player or {}).get("name") or (subject_player or {}).get("player_name") or "").strip(),
                    "subject_rating": (subject_player or {}).get("rating"),
                    "base_delta": base_delta,
                    "first_season_with_team": bool(target.get("first_season_with_team")),
                    "joined_season_year": target.get("joined_season_year"),
                },
                actor=actor,
            )
            events.append(result)
        return {
            "ok": True,
            "team_code": normalized_team,
            "base_delta": base_delta,
            "affected_count": len(events),
            "events": events,
            "skipped": skipped,
        }

    def apply_roster_impact_conn(
        self,
        conn: Any,
        *,
        team_code: str,
        subject_player: Dict[str, Any],
        direction: str,
        source_entity_type: str,
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        command_id_prefix: Optional[str] = None,
        excluded_profile_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        base_delta = roster_rating_impact_delta((subject_player or {}).get("rating"), direction)
        normalized_team = str(team_code or "").strip().upper()
        subject_profile_id = parse_int((subject_player or {}).get("profile_id"))
        subject_player_id = parse_int((subject_player or {}).get("id") or (subject_player or {}).get("player_id"))
        if not normalized_team or not base_delta:
            return {
                "ok": True,
                "team_code": normalized_team,
                "base_delta": base_delta,
                "affected_count": 0,
                "events": [],
            }
        target_data = self.repository.roster_impact_targets_conn(
            conn,
            normalized_team,
            excluded_profile_id=subject_profile_id,
            excluded_profile_ids=excluded_profile_ids,
        )
        timestamp = timestamp or self._now()
        events: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for target in target_data.get("targets") or []:
            target_profile_id = parse_int(target.get("profile_id"))
            if target_profile_id is None:
                continue
            applied_delta = roster_impact_player_delta(
                base_delta,
                first_season_with_team=bool(target.get("first_season_with_team")),
                date_of_birth=target.get("date_of_birth"),
                on_date=timestamp,
            )
            if not applied_delta:
                skipped.append(
                    {
                        "profile_id": target.get("profile_id"),
                        "player_name": target.get("player_name"),
                        "reason": "roster_impact_delta_zero",
                    }
                )
                continue
            command_id = (
                f"{command_id_prefix}:{int(target_profile_id)}:{str(direction or '').strip().lower()}"
                if command_id_prefix
                else None
            )
            result = self.apply_modifier_conn(
                conn,
                int(target_profile_id),
                applied_delta,
                event_type=EVENT_ROSTER_IMPACT,
                reason=self._roster_impact_reason(subject_player, direction, normalized_team, applied_delta),
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id or subject_player_id,
                metadata={
                    "team_code": normalized_team,
                    "direction": str(direction or "").strip().lower(),
                    "subject_player_id": subject_player_id,
                    "subject_profile_id": subject_profile_id,
                    "subject_player_name": str((subject_player or {}).get("name") or (subject_player or {}).get("player_name") or "").strip(),
                    "subject_rating": (subject_player or {}).get("rating"),
                    "base_delta": base_delta,
                    "first_season_with_team": bool(target.get("first_season_with_team")),
                    "joined_season_year": target.get("joined_season_year"),
                },
                actor=actor,
                timestamp=timestamp,
                command_id=command_id,
            )
            events.append(result)
        return {
            "ok": True,
            "team_code": normalized_team,
            "base_delta": base_delta,
            "affected_count": len(events),
            "events": events,
            "skipped": skipped,
        }

    @staticmethod
    def _gm_change_reason(direction: str, gm_name: str, band: str, delta: float) -> str:
        action = "entra" if direction == GM_CHANGE_ENTER else "sale"
        tier = "top 5" if band == "top5" else "bottom 5"
        sign = "+" if delta > 0 else ""
        return f"Cambio de GM: {action} {gm_name or 'GM'} ({tier} atractivo, {sign}{delta})"

    def apply_gm_change_impact(
        self,
        *,
        team_code: str,
        incoming_ranking_entry: Optional[Dict[str, Any]] = None,
        outgoing_ranking_entry: Optional[Dict[str, Any]] = None,
        source_entity_type: str = "gm_assignment",
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = self._now()
        with self.repository.transaction("IMMEDIATE") as conn:
            return self.apply_gm_change_impact_conn(
                conn,
                team_code=team_code,
                incoming_ranking_entry=incoming_ranking_entry,
                outgoing_ranking_entry=outgoing_ranking_entry,
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id,
                actor=actor,
                timestamp=timestamp,
            )

    def apply_gm_change_impact_conn(
        self,
        conn: Any,
        *,
        team_code: str,
        incoming_ranking_entry: Optional[Dict[str, Any]] = None,
        outgoing_ranking_entry: Optional[Dict[str, Any]] = None,
        source_entity_type: str = "gm_assignment",
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_team = str(team_code or "").strip().upper()
        if not normalized_team:
            return {"ok": True, "skipped": True, "reason": "team_code_required", "affected_count": 0, "events": []}
        timestamp = timestamp or self._now()
        source_id = str(source_entity_id or f"{normalized_team}:{timestamp}")
        changes = []
        for direction, entry in (
            (GM_CHANGE_LEAVE, outgoing_ranking_entry),
            (GM_CHANGE_ENTER, incoming_ranking_entry),
        ):
            if not entry:
                continue
            band = str(entry.get("band") or "").strip().lower()
            delta = gm_change_happiness_delta(direction=direction, band=band)
            if not delta:
                continue
            gm_entity_id = parse_int(entry.get("gm_entity_id"))
            changes.append(
                {
                    "direction": direction,
                    "band": band,
                    "delta": delta,
                    "gm_entity_id": gm_entity_id,
                    "gm_name": str(entry.get("gm_name") or "").strip(),
                    "rank_position": entry.get("rank_position"),
                    "standardized_score": entry.get("standardized_score"),
                }
            )
        if not changes:
            return {
                "ok": True,
                "skipped": True,
                "reason": "no_ranked_gm_change_delta",
                "team_code": normalized_team,
                "affected_count": 0,
                "events": [],
            }
        target_data = self.repository.roster_impact_targets_conn(conn, normalized_team)
        events: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for target in target_data.get("targets") or []:
            profile_id = parse_int(target.get("profile_id"))
            if profile_id is None:
                continue
            for change in changes:
                command_id = (
                    f"player-happiness:gm-change:{source_id}:"
                    f"{change['direction']}:{change.get('gm_entity_id') or 'unknown'}:"
                    f"profile:{int(profile_id)}"
                )
                if self.repository.has_event_command_id_conn(conn, command_id):
                    skipped.append(
                        {
                            "profile_id": int(profile_id),
                            "player_name": target.get("player_name"),
                            "direction": change["direction"],
                            "gm_entity_id": change.get("gm_entity_id"),
                            "reason": "gm_change_already_applied",
                        }
                    )
                    continue
                result = self.apply_modifier_conn(
                    conn,
                    int(profile_id),
                    change["delta"],
                    event_type=EVENT_GM_CHANGE,
                    reason=self._gm_change_reason(
                        change["direction"],
                        change.get("gm_name") or "",
                        change["band"],
                        change["delta"],
                    ),
                    source_entity_type=source_entity_type,
                    source_entity_id=source_id,
                    metadata={
                        "team_code": normalized_team,
                        "direction": change["direction"],
                        "gm_entity_id": change.get("gm_entity_id"),
                        "gm_name": change.get("gm_name"),
                        "ranking_band": change.get("band"),
                        "rank_position": change.get("rank_position"),
                        "standardized_score": change.get("standardized_score"),
                        "delta_model": "gm_attractiveness_top_bottom_5_v1",
                    },
                    actor=actor,
                    timestamp=timestamp,
                    command_id=command_id,
                )
                events.append(result)
        return {
            "ok": True,
            "team_code": normalized_team,
            "source_entity_id": source_id,
            "changes": changes,
            "affected_count": len(events),
            "events": events,
            "skipped": skipped,
        }

    def apply_drafted_rating_threshold(
        self,
        *,
        player_id: Any,
        previous_rating: Any,
        new_rating: Any,
        source_entity_type: str,
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.repository.transaction("IMMEDIATE") as conn:
            return self.apply_drafted_rating_threshold_conn(
                conn,
                player_id=player_id,
                previous_rating=previous_rating,
                new_rating=new_rating,
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id,
                actor=actor,
                timestamp=self._now(),
            )

    def apply_drafted_rating_threshold_conn(
        self,
        conn: Any,
        *,
        player_id: Any,
        previous_rating: Any,
        new_rating: Any,
        source_entity_type: str,
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        command_id_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed_player_id = parse_int(player_id)
        if parsed_player_id is None:
            return {"ok": True, "skipped": True, "reason": "invalid_player_id", "affected_count": 0, "events": []}
        if not drafted_rating_threshold_crossed(previous_rating, new_rating):
            return {"ok": True, "skipped": True, "reason": "rating_threshold_not_crossed", "affected_count": 0, "events": []}
        subject = self.repository.drafted_rating_threshold_subject_conn(conn, int(parsed_player_id))
        if not subject:
            return {"ok": True, "skipped": True, "reason": "player_not_found", "affected_count": 0, "events": []}
        if not is_rookie_scale_contract_type(subject.get("bird_rights")):
            return {"ok": True, "skipped": True, "reason": "not_rookie_scale_contract", "affected_count": 0, "events": []}
        if bool(subject.get("has_trade_transaction")):
            return {"ok": True, "skipped": True, "reason": "player_has_trade_transaction", "affected_count": 0, "events": []}
        profile_id = parse_int(subject.get("profile_id"))
        team_code = str(subject.get("team_code") or "").strip().upper()
        if profile_id is None or not team_code:
            return {"ok": True, "skipped": True, "reason": "invalid_player_context", "affected_count": 0, "events": []}
        target_data = self.repository.roster_impact_targets_conn(
            conn,
            team_code,
            excluded_profile_id=int(profile_id),
        )
        timestamp = timestamp or self._now()
        events: List[Dict[str, Any]] = []
        for target in target_data.get("targets") or []:
            target_profile_id = parse_int(target.get("profile_id"))
            if target_profile_id is None:
                continue
            command_id = (
                f"{command_id_prefix}:{int(target_profile_id)}"
                if command_id_prefix
                else None
            )
            result = self.apply_modifier_conn(
                conn,
                int(target_profile_id),
                DRAFTED_RATING_THRESHOLD_DELTA,
                event_type=EVENT_DRAFTED_RATING_THRESHOLD,
                reason=(
                    f"Impacto de desarrollo: {str(subject.get('player_name') or 'Jugador').strip()} "
                    f"alcanzó {DRAFTED_RATING_THRESHOLD}+ de rating"
                ),
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id or parsed_player_id,
                metadata={
                    "team_code": team_code,
                    "subject_player_id": int(parsed_player_id),
                    "subject_profile_id": int(profile_id),
                    "subject_player_name": str(subject.get("player_name") or "").strip(),
                    "previous_rating": previous_rating,
                    "new_rating": new_rating,
                    "threshold": DRAFTED_RATING_THRESHOLD,
                    "contract_type": subject.get("bird_rights"),
                    "has_trade_transaction": bool(subject.get("has_trade_transaction")),
                },
                actor=actor,
                timestamp=timestamp,
                command_id=command_id,
            )
            events.append(result)
        return {
            "ok": True,
            "team_code": team_code,
            "subject_player_id": int(parsed_player_id),
            "subject_profile_id": int(profile_id),
            "subject_player_name": str(subject.get("player_name") or "").strip(),
            "previous_rating": previous_rating,
            "new_rating": new_rating,
            "applied_delta": DRAFTED_RATING_THRESHOLD_DELTA,
            "affected_count": len(events),
            "events": events,
        }

    def team_objective_join_modifier(
        self,
        objective: Any,
        rating: Any,
        *,
        age: Any = None,
        date_of_birth: Any = None,
        on_date: Any = None,
    ) -> Dict[str, Any]:
        objective_code = normalize_objective_code(objective)
        timestamp = on_date or self._now()
        applied_delta = team_objective_happiness_delta(
            objective_code,
            rating,
            age=age,
            date_of_birth=date_of_birth,
            on_date=timestamp,
        )
        return {
            "ok": True,
            "event_type": EVENT_TEAM_OBJECTIVE_JOIN_CONTEXT,
            "objective_code": objective_code,
            "rating": rating,
            "rating_band": team_objective_rating_band(rating),
            "age": parse_int(age) if age is not None else None,
            "date_of_birth": date_of_birth,
            "applied_delta": applied_delta,
        }

    def apply_team_objective_change(
        self,
        *,
        team_code: str,
        previous_objective: Any,
        new_objective: Any,
        season_year: Any = None,
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_team = str(team_code or "").strip().upper()
        previous_code = normalize_objective_code(previous_objective)
        new_code = normalize_objective_code(new_objective)
        if not normalized_team or new_code is None:
            return {
                "ok": True,
                "skipped": True,
                "reason": "invalid_team_objective_context",
                "team_code": normalized_team,
                "affected_count": 0,
                "events": [],
            }
        target_data = self.repository.roster_impact_targets(normalized_team)
        timestamp = self._now()
        events: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for target in target_data.get("targets") or []:
            profile_id = parse_int(target.get("profile_id"))
            if profile_id is None:
                continue
            applied_delta = team_objective_happiness_delta_change(
                previous_code,
                new_code,
                target.get("rating"),
                date_of_birth=target.get("date_of_birth"),
                on_date=timestamp,
            )
            if not applied_delta:
                skipped.append(
                    {
                        "profile_id": int(profile_id),
                        "player_name": target.get("player_name"),
                        "reason": "team_objective_delta_zero",
                        "rating": target.get("rating"),
                        "rating_band": team_objective_rating_band(target.get("rating")),
                    }
                )
                continue
            result = self.apply_modifier(
                int(profile_id),
                applied_delta,
                event_type=EVENT_TEAM_OBJECTIVE_SET,
                reason=self._team_objective_reason(previous_code, new_code, applied_delta),
                source_entity_type="team_season_objective",
                source_entity_id=source_entity_id or f"{normalized_team}:{season_year or target_data.get('current_year')}",
                metadata={
                    "team_code": normalized_team,
                    "season_year": parse_int(season_year) or target_data.get("current_year"),
                    "previous_objective_code": previous_code,
                    "new_objective_code": new_code,
                    "player_rating": target.get("rating"),
                    "rating_band": team_objective_rating_band(target.get("rating")),
                    "date_of_birth": target.get("date_of_birth"),
                    "objective_delta_model": "rating_age_v1",
                },
                actor=actor,
            )
            events.append(result)
        return {
            "ok": True,
            "team_code": normalized_team,
            "season_year": parse_int(season_year) or target_data.get("current_year"),
            "previous_objective_code": previous_code,
            "new_objective_code": new_code,
            "affected_count": len(events),
            "events": events,
            "skipped": skipped,
        }

    def apply_team_objective_resolution(
        self,
        *,
        team_code: str,
        agreed_objective: Any,
        achieved_objective: Any,
        season_year: Any = None,
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_team = str(team_code or "").strip().upper()
        agreed_code = normalize_objective_code(agreed_objective)
        achieved_code = normalize_objective_code(achieved_objective)
        applied_delta = team_objective_resolution_delta(agreed_code, achieved_code)
        parsed_season = parse_int(season_year)
        if not normalized_team or agreed_code is None or achieved_code is None:
            return {
                "ok": True,
                "skipped": True,
                "reason": "invalid_team_objective_resolution_context",
                "team_code": normalized_team,
                "season_year": parsed_season,
                "affected_count": 0,
                "events": [],
            }
        if not applied_delta:
            return {
                "ok": True,
                "skipped": True,
                "reason": "team_objective_resolution_delta_zero",
                "team_code": normalized_team,
                "season_year": parsed_season,
                "agreed_objective_code": agreed_code,
                "achieved_objective_code": achieved_code,
                "applied_delta": 0.0,
                "affected_count": 0,
                "events": [],
            }
        source_id = str(source_entity_id or f"{normalized_team}:{parsed_season or 'current'}")
        timestamp = self._now()
        events: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        resolved_season = parsed_season
        with self.repository.transaction("IMMEDIATE") as conn:
            target_data = self.repository.roster_impact_targets_conn(conn, normalized_team)
            resolved_season = parsed_season or target_data.get("current_year")
            for target in target_data.get("targets") or []:
                profile_id = parse_int(target.get("profile_id"))
                if profile_id is None:
                    continue
                command_id = (
                    f"player-happiness:team-objective-resolution:"
                    f"{source_id}:profile:{int(profile_id)}"
                )
                if self.repository.has_event_command_id_conn(conn, command_id):
                    skipped.append(
                        {
                            "profile_id": int(profile_id),
                            "player_name": target.get("player_name"),
                            "reason": "team_objective_resolution_already_applied",
                        }
                    )
                    continue
                result = self.apply_modifier_conn(
                    conn,
                    int(profile_id),
                    applied_delta,
                    event_type=EVENT_TEAM_OBJECTIVE_RESOLUTION,
                    reason=self._team_objective_resolution_reason(agreed_code, achieved_code, applied_delta),
                    source_entity_type="team_season_objective",
                    source_entity_id=source_id,
                    metadata={
                        "team_code": normalized_team,
                        "season_year": resolved_season,
                        "agreed_objective_code": agreed_code,
                        "achieved_objective_code": achieved_code,
                        "resolution_delta_model": "objective_difficulty_delta_v1",
                    },
                    actor=actor,
                    timestamp=timestamp,
                    command_id=command_id,
                )
                events.append(result)
        return {
            "ok": True,
            "team_code": normalized_team,
            "season_year": resolved_season,
            "agreed_objective_code": agreed_code,
            "achieved_objective_code": achieved_code,
            "applied_delta": applied_delta,
            "affected_count": len(events),
            "events": events,
            "skipped": skipped,
        }

    def apply_trade_request_followups(
        self,
        *,
        as_of_date: Any = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = self._now()
        effective_date = str(as_of_date or timestamp)[:10]
        candidates = self.repository.trade_request_followup_candidates()
        events: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for candidate in candidates:
            profile_id = parse_int(candidate.get("profile_id"))
            request_event_id = parse_int(candidate.get("request_event_id"))
            if profile_id is None or request_event_id is None:
                continue
            penalties = trade_request_followup_penalties(
                candidate.get("request_date") or candidate.get("request_created_at"),
                effective_date,
                current_happiness=candidate.get("current_happiness"),
                is_last_contract_year=bool(candidate.get("is_last_contract_year")),
                applied_stages=candidate.get("applied_stages") or [],
            )
            if not penalties:
                skipped.append(
                    {
                        "profile_id": int(profile_id),
                        "player_name": candidate.get("player_name"),
                        "request_event_id": int(request_event_id),
                        "reason": "trade_request_followup_not_due",
                    }
                )
                continue
            for penalty in penalties:
                stage = str(penalty.get("stage") or "").strip()
                command_id = (
                    f"player-happiness:trade-request-followup:"
                    f"{int(request_event_id)}:{stage}:profile:{int(profile_id)}"
                )
                with self.repository.transaction("IMMEDIATE") as conn:
                    if self.repository.has_event_command_id_conn(conn, command_id):
                        skipped.append(
                            {
                                "profile_id": int(profile_id),
                                "player_name": candidate.get("player_name"),
                                "request_event_id": int(request_event_id),
                                "stage": stage,
                                "reason": "trade_request_followup_already_applied",
                            }
                        )
                        continue
                    result = self.apply_modifier_conn(
                        conn,
                        int(profile_id),
                        penalty.get("applied_delta"),
                        event_type=EVENT_TRADE_REQUEST_FOLLOWUP,
                        reason=self._trade_request_followup_reason(penalty),
                        source_entity_type="player_trade_request",
                        source_entity_id=int(request_event_id),
                        metadata={
                            "trade_request_followup_stage": stage,
                            "trade_request_event_id": int(request_event_id),
                            "trade_request_date": candidate.get("request_date"),
                            "due_date": penalty.get("due_date"),
                            "months_elapsed_threshold": penalty.get("months"),
                            "milestone_code": candidate.get("milestone_code"),
                            "contract_context": candidate.get("contract_context"),
                        },
                        actor=actor,
                        timestamp=timestamp,
                        command_id=command_id,
                    )
                if result.get("skipped"):
                    skipped.append(
                        {
                            "profile_id": int(profile_id),
                            "player_name": candidate.get("player_name"),
                            "request_event_id": int(request_event_id),
                            "stage": stage,
                            "reason": result.get("reason") or "trade_request_followup_skipped",
                        }
                    )
                else:
                    events.append(result)
        return {
            "ok": True,
            "as_of_date": effective_date,
            "candidate_count": len(candidates),
            "affected_count": len(events),
            "events": events,
            "skipped": skipped,
        }

    def apply_zero_threshold_transition(
        self,
        *,
        profile_id: int,
        previous_value: Any,
        new_value: Any,
        source_event: Optional[Dict[str, Any]] = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.repository.transaction("IMMEDIATE") as conn:
            return self.apply_zero_threshold_transition_conn(
                conn,
                profile_id=profile_id,
                previous_value=previous_value,
                new_value=new_value,
                source_event=source_event,
                actor=actor,
                timestamp=self._now(),
            )

    def apply_zero_threshold_transition_conn(
        self,
        conn: Any,
        *,
        profile_id: int,
        previous_value: Any,
        new_value: Any,
        source_event: Optional[Dict[str, Any]] = None,
        actor: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None:
            return {"ok": True, "skipped": True, "reason": "invalid_profile_id", "affected_count": 0, "events": []}
        prior_state = self.repository.latest_zero_threshold_cohort_conn(conn, int(parsed_profile_id))
        transition = zero_happiness_transition(
            previous_value,
            new_value,
            has_prior_zero_cohort=bool(prior_state),
        )
        if not transition:
            return {"ok": True, "skipped": True, "reason": "zero_threshold_not_crossed", "affected_count": 0, "events": []}

        context = self.repository.profile_context_conn(conn, int(parsed_profile_id))
        if not context:
            return {"ok": True, "skipped": True, "reason": "player_profile_not_found", "affected_count": 0, "events": []}
        team_code = str(context.get("team_code") or "").strip().upper()
        if not team_code:
            return {"ok": True, "skipped": True, "reason": "player_not_on_team", "affected_count": 0, "events": []}

        target_data = self.repository.roster_impact_targets_conn(
            conn,
            team_code,
            excluded_profile_id=int(parsed_profile_id),
        )
        current_teammate_ids = self._profile_ids_from_targets(target_data.get("targets") or [])
        original_cohort_ids = self._zero_cohort_ids(prior_state)
        timestamp = timestamp or self._now()
        subject = {
            "profile_id": int(parsed_profile_id),
            "player_name": context.get("player_name"),
            "team_code": team_code,
        }
        source_event = source_event or {}

        if transition == "initial_zero":
            events = self._apply_zero_delta_to_profiles_conn(
                conn,
                current_teammate_ids,
                TEAMMATE_ZERO_INITIAL_DELTA,
                subject=subject,
                transition=transition,
                cohort_profile_ids=current_teammate_ids,
                source_event=source_event,
                actor=actor,
                timestamp=timestamp,
                command_id_prefix=f"player-happiness:zero-threshold:{int(parsed_profile_id)}:{transition}:{timestamp}",
            )
            return self._zero_transition_result(
                transition,
                subject,
                team_code,
                current_teammate_ids,
                current_teammate_ids,
                events,
            )

        if transition == "recovered_above_zero":
            events = self._apply_zero_delta_to_profiles_conn(
                conn,
                original_cohort_ids,
                TEAMMATE_ZERO_RELIEF_DELTA,
                subject=subject,
                transition=transition,
                cohort_profile_ids=original_cohort_ids,
                source_event=source_event,
                actor=actor,
                timestamp=timestamp,
                command_id_prefix=f"player-happiness:zero-threshold:{int(parsed_profile_id)}:{transition}:{timestamp}",
            )
            return self._zero_transition_result(
                transition,
                subject,
                team_code,
                original_cohort_ids,
                current_teammate_ids,
                events,
            )

        original_set = set(original_cohort_ids)
        new_teammate_ids = [profile for profile in current_teammate_ids if profile not in original_set]
        events = []
        events.extend(
            self._apply_zero_delta_to_profiles_conn(
                conn,
                original_cohort_ids,
                TEAMMATE_ZERO_RETURN_COHORT_DELTA,
                subject=subject,
                transition=transition,
                cohort_profile_ids=original_cohort_ids,
                source_event=source_event,
                actor=actor,
                timestamp=timestamp,
                command_id_prefix=f"player-happiness:zero-threshold:{int(parsed_profile_id)}:{transition}:cohort:{timestamp}",
            )
        )
        events.extend(
            self._apply_zero_delta_to_profiles_conn(
                conn,
                new_teammate_ids,
                TEAMMATE_ZERO_INITIAL_DELTA,
                subject=subject,
                transition=transition,
                cohort_profile_ids=original_cohort_ids,
                source_event=source_event,
                actor=actor,
                timestamp=timestamp,
                command_id_prefix=f"player-happiness:zero-threshold:{int(parsed_profile_id)}:{transition}:new:{timestamp}",
            )
        )
        return self._zero_transition_result(
            transition,
            subject,
            team_code,
            original_cohort_ids,
            current_teammate_ids,
            events,
        )

    def apply_zero_trade_relief_conn(
        self,
        conn: Any,
        *,
        profile_id: Any,
        source_entity_id: Any = None,
        actor: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        command_id_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None:
            return {"ok": True, "skipped": True, "reason": "invalid_profile_id", "affected_count": 0, "events": []}
        prior_state = self.repository.latest_zero_threshold_cohort_conn(conn, int(parsed_profile_id))
        if not prior_state:
            return {"ok": True, "skipped": True, "reason": "zero_threshold_cohort_not_found", "affected_count": 0, "events": []}
        context = self.repository.profile_context_conn(conn, int(parsed_profile_id))
        if not context:
            return {"ok": True, "skipped": True, "reason": "player_profile_not_found", "affected_count": 0, "events": []}
        current_happiness = parse_float(str(context.get("happiness") or "0"))
        if current_happiness is None or current_happiness > 0:
            return {"ok": True, "skipped": True, "reason": "subject_happiness_above_zero", "affected_count": 0, "events": []}
        cohort_profile_ids = self._zero_cohort_ids(prior_state)
        timestamp = timestamp or self._now()
        subject = {
            "profile_id": int(parsed_profile_id),
            "player_name": context.get("player_name"),
            "team_code": str(context.get("team_code") or "").strip().upper(),
        }
        events = self._apply_zero_delta_to_profiles_conn(
            conn,
            cohort_profile_ids,
            TEAMMATE_ZERO_RELIEF_DELTA,
            subject=subject,
            transition="traded_after_zero",
            cohort_profile_ids=cohort_profile_ids,
            source_event={"event_type": "trade", "command_id": source_entity_id},
            actor=actor,
            timestamp=timestamp,
            command_id_prefix=command_id_prefix
            or f"player-happiness:zero-threshold:{int(parsed_profile_id)}:traded-after-zero:{timestamp}",
        )
        return self._zero_transition_result(
            "traded_after_zero",
            subject,
            str(context.get("team_code") or "").strip().upper(),
            cohort_profile_ids,
            cohort_profile_ids,
            events,
        )

    @staticmethod
    def _profile_ids_from_targets(targets: List[Dict[str, Any]]) -> List[int]:
        profile_ids: List[int] = []
        seen: set[int] = set()
        for target in targets:
            parsed = parse_int((target or {}).get("profile_id"))
            if parsed is None or int(parsed) in seen:
                continue
            seen.add(int(parsed))
            profile_ids.append(int(parsed))
        return profile_ids

    @staticmethod
    def _zero_cohort_ids(state: Optional[Dict[str, Any]]) -> List[int]:
        zero_threshold = (state or {}).get("zero_threshold") if isinstance(state, dict) else {}
        raw_ids = zero_threshold.get("cohort_profile_ids") if isinstance(zero_threshold, dict) else []
        profile_ids: List[int] = []
        seen: set[int] = set()
        for value in raw_ids or []:
            parsed = parse_int(value)
            if parsed is None or int(parsed) in seen:
                continue
            seen.add(int(parsed))
            profile_ids.append(int(parsed))
        return profile_ids

    def _apply_zero_delta_to_profiles_conn(
        self,
        conn: Any,
        profile_ids: List[int],
        delta: float,
        *,
        subject: Dict[str, Any],
        transition: str,
        cohort_profile_ids: List[int],
        source_event: Dict[str, Any],
        actor: Optional[Dict[str, Any]],
        timestamp: str,
        command_id_prefix: str,
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        subject_profile_id = parse_int(subject.get("profile_id"))
        if subject_profile_id is None:
            return events
        for profile_id in profile_ids:
            command_id = f"{command_id_prefix}:{int(profile_id)}"
            result = self.apply_modifier_conn(
                conn,
                int(profile_id),
                delta,
                event_type=EVENT_TEAMMATE_ZERO_THRESHOLD,
                reason=self._zero_threshold_reason(subject, transition, delta),
                source_entity_type="player_zero_threshold",
                source_entity_id=str(int(subject_profile_id)),
                metadata={
                    "zero_threshold": {
                        "transition": transition,
                        "subject_profile_id": int(subject_profile_id),
                        "subject_player_name": str(subject.get("player_name") or "").strip(),
                        "team_code": str(subject.get("team_code") or "").strip().upper(),
                        "cohort_profile_ids": [int(value) for value in cohort_profile_ids],
                        "source_event_command_id": source_event.get("command_id"),
                        "source_event_type": source_event.get("event_type"),
                    }
                },
                actor=actor,
                timestamp=timestamp,
                command_id=command_id,
                trigger_zero_rules=False,
            )
            if not result.get("skipped"):
                events.append(result)
        return events

    @staticmethod
    def _zero_transition_result(
        transition: str,
        subject: Dict[str, Any],
        team_code: str,
        cohort_profile_ids: List[int],
        current_teammate_ids: List[int],
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "transition": transition,
            "subject_profile_id": parse_int(subject.get("profile_id")),
            "subject_player_name": str(subject.get("player_name") or "").strip(),
            "team_code": str(team_code or "").strip().upper(),
            "cohort_profile_ids": cohort_profile_ids,
            "current_teammate_profile_ids": current_teammate_ids,
            "affected_count": len(events),
            "events": events,
        }

    @staticmethod
    def _zero_threshold_reason(subject: Dict[str, Any], transition: str, delta: float) -> str:
        player_name = str(subject.get("player_name") or "Un compañero").strip()
        if transition == "initial_zero":
            return f"Impacto de vestuario: {player_name} llegó a 0 o menos de felicidad"
        if transition == "traded_after_zero":
            return f"Impacto de vestuario: {player_name} fue traspasado tras llegar a 0 o menos"
        if transition == "recovered_above_zero":
            return f"Impacto de vestuario: {player_name} volvió a subir por encima de 0"
        return f"Impacto de vestuario: {player_name} volvió a 0 o menos ({delta:+g})"

    @staticmethod
    def _team_objective_reason(previous_code: Optional[str], new_code: str, applied_delta: float) -> str:
        previous_label = objective_label(previous_code) if previous_code else "sin objetivo"
        new_label = objective_label(new_code)
        return f"Impacto de objetivo ({applied_delta:+g}): {previous_label} → {new_label}"

    @staticmethod
    def _team_objective_resolution_reason(agreed_code: str, achieved_code: str, applied_delta: float) -> str:
        return (
            f"Resolución de objetivo ({applied_delta:+g}): "
            f"{objective_label(agreed_code)} → {objective_label(achieved_code)}"
        )

    @staticmethod
    def _trade_request_followup_reason(penalty: Dict[str, Any]) -> str:
        months = parse_int(penalty.get("months")) or 0
        delta = parse_float(str(penalty.get("applied_delta") or "0")) or 0
        return f"Seguimiento petición de traspaso: {months} meses sin traspaso ni recuperación ({delta:+g})"

    @staticmethod
    def _roster_impact_reason(
        subject_player: Dict[str, Any],
        direction: str,
        team_code: str,
        applied_delta: float,
    ) -> str:
        player_name = str((subject_player or {}).get("name") or (subject_player or {}).get("player_name") or "Jugador").strip()
        action = "llegó a" if applied_delta > 0 else "salió de"
        return f"Impacto de roster: {player_name} {action} {team_code}"

    @staticmethod
    def _rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid_json") from exc
        if isinstance(payload, dict):
            rows = payload.get("players") or payload.get("rows")
            if rows is None and ("player_name" in payload or "name" in payload or "profile_id" in payload):
                rows = [payload]
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = None
        if not isinstance(rows, list):
            raise ValueError("happiness_import_players_required")
        return [row for row in rows if isinstance(row, dict)]

    def preview(self, payload: Any) -> Dict[str, Any]:
        rows = self._rows_from_payload(payload)
        with self.repository.connect() as conn:
            profiles = self.repository.profiles(conn)

        by_profile_id = {int(profile["profile_id"]): profile for profile in profiles}
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            key = normalize_happiness_import_name(profile.get("name"))
            if key:
                by_name.setdefault(key, []).append(profile)

        records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        ambiguous: List[Dict[str, Any]] = []
        seen_profiles: Dict[int, int] = {}
        for index, row in enumerate(rows):
            line = index + 1
            raw_name = str(row.get("player_name") or row.get("name") or row.get("player") or "").strip()
            raw_profile_id = parse_int(row.get("profile_id") or row.get("id"))
            try:
                happiness = normalize_happiness_value(row.get("happiness"))
            except ValueError:
                errors.append({"line": line, "message": f"Felicidad inválida para {raw_name or raw_profile_id or 'fila'}."})
                continue
            profile: Optional[Dict[str, Any]] = None
            match_method = "name"
            if raw_profile_id is not None:
                profile = by_profile_id.get(int(raw_profile_id))
                match_method = "profile_id"
                if not profile:
                    errors.append({"line": line, "message": f"No existe profile_id {raw_profile_id}."})
                    continue
            else:
                key = normalize_happiness_import_name(raw_name)
                matches = by_name.get(key, []) if key else []
                if not matches:
                    unmatched.append({"line": line, "player_name": raw_name, "happiness": happiness})
                    continue
                if len(matches) > 1:
                    ambiguous.append(
                        {
                            "line": line,
                            "player_name": raw_name,
                            "happiness": happiness,
                            "matches": [
                                {
                                    "profile_id": match.get("profile_id"),
                                    "player_name": match.get("name"),
                                    "current_happiness": match.get("happiness"),
                                    "status_label": match.get("status_label"),
                                    "team_code": match.get("team_code"),
                                }
                                for match in matches
                            ],
                        }
                    )
                    continue
                profile = matches[0]

            profile_id = int(profile["profile_id"])
            if profile_id in seen_profiles:
                errors.append(
                    {
                        "line": line,
                        "message": f"Jugador duplicado: {profile.get('name')} ya apareció en la línea {seen_profiles[profile_id]}.",
                    }
                )
                continue
            seen_profiles[profile_id] = line
            current = float(profile.get("happiness") or 0)
            records.append(
                {
                    "line": line,
                    "profile_id": profile_id,
                    "player_name": str(profile.get("name") or raw_name).strip(),
                    "input_player_name": raw_name,
                    "current_happiness": current,
                    "new_happiness": happiness,
                    "happiness": happiness,
                    "delta": float(happiness) - current,
                    "changed": current != float(happiness),
                    "expected_version": int(profile.get("version") or 1),
                    "match_method": match_method,
                    "status_label": profile.get("status_label"),
                    "team_code": profile.get("team_code"),
                    "profile_status": profile.get("profile_status"),
                    "reason": str(row.get("reason") or "Initial happiness baseline import").strip(),
                    "event_date": str(row.get("event_date") or row.get("date") or "")[:10] or None,
                }
            )
        changed_count = sum(1 for record in records if record["changed"])
        return {
            "ok": not errors and not ambiguous,
            "errors": errors,
            "records": records,
            "summary": {
                "input_count": len(rows),
                "matched_count": len(records),
                "changed_count": changed_count,
                "unchanged_count": len(records) - changed_count,
                "unmatched_count": len(unmatched),
                "ambiguous_count": len(ambiguous),
                "error_count": len(errors),
            },
            "unmatched": unmatched,
            "ambiguous": ambiguous,
        }

    def apply(self, records_payload: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        cleaned: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for raw in records_payload:
            if not isinstance(raw, dict):
                raise ValueError("invalid_records")
            profile_id = parse_int(raw.get("profile_id"))
            expected_version = parse_int(raw.get("expected_version"))
            player_name = str(raw.get("player_name") or "").strip()
            if profile_id is None or expected_version is None or not player_name:
                raise ValueError("invalid_records")
            if int(profile_id) in seen:
                raise ValueError("duplicate_happiness_import_target")
            seen.add(int(profile_id))
            try:
                happiness = normalize_happiness_value(raw.get("happiness", raw.get("new_happiness")))
            except ValueError as exc:
                raise ValueError("invalid_records") from exc
            cleaned.append(
                {
                    "profile_id": int(profile_id),
                    "player_name": player_name,
                    "input_player_name": raw.get("input_player_name"),
                    "happiness": happiness,
                    "expected_version": int(expected_version),
                    "match_method": raw.get("match_method") or "unknown",
                    "reason": raw.get("reason") or "Initial happiness baseline import",
                    "event_date": raw.get("event_date"),
                }
            )
        timestamp = self._now()
        command_id = f"player-happiness:baseline-import:{timestamp}"
        actor_user_id = parse_int((actor or {}).get("user_id"))
        result = self.repository.apply_baseline_import(
            cleaned,
            timestamp=timestamp,
            command_id=command_id,
            actor_user_id=actor_user_id,
        )
        result["command_id"] = command_id
        result["validation_result"] = "valid"
        result["entity_versions"] = {
            "record_count": int(result.get("record_count") or 0),
            "changed_count": int(result.get("changed_count") or 0),
            "unchanged_count": int(result.get("unchanged_count") or 0),
        }
        return result

    def preview_historical_ledger(self, payload: Any) -> Dict[str, Any]:
        rows = self._rows_from_payload(payload)
        with self.repository.connect() as conn:
            profiles = self.repository.profiles(conn)
            current_year = self.repository.current_year_conn(conn)

        by_profile_id = {int(profile["profile_id"]): profile for profile in profiles}
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            key = normalize_happiness_import_name(profile.get("name"))
            if key:
                by_name.setdefault(key, []).append(profile)

        records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        ambiguous: List[Dict[str, Any]] = []
        seen_profiles: Dict[int, int] = {}
        for index, row in enumerate(rows):
            line = index + 1
            raw_name = str(row.get("player_name") or row.get("name") or row.get("player") or "").strip()
            raw_profile_id = parse_int(row.get("profile_id") or row.get("id"))
            profile: Optional[Dict[str, Any]] = None
            match_method = "name"
            if raw_profile_id is not None:
                profile = by_profile_id.get(int(raw_profile_id))
                match_method = "profile_id"
                if not profile:
                    errors.append({"line": line, "message": f"No existe profile_id {raw_profile_id}."})
                    continue
            else:
                key = normalize_happiness_import_name(raw_name)
                matches = by_name.get(key, []) if key else []
                if not matches:
                    unmatched.append({"line": line, "player_name": raw_name})
                    continue
                if len(matches) > 1:
                    ambiguous.append(
                        {
                            "line": line,
                            "player_name": raw_name,
                            "matches": [
                                {
                                    "profile_id": match.get("profile_id"),
                                    "player_name": match.get("name"),
                                    "current_happiness": match.get("happiness"),
                                    "status_label": match.get("status_label"),
                                    "team_code": match.get("team_code"),
                                }
                                for match in matches
                            ],
                        }
                    )
                    continue
                profile = matches[0]

            profile_id = int(profile["profile_id"])
            if profile_id in seen_profiles:
                errors.append({"line": line, "message": f"Jugador duplicado: {profile.get('name')} ya apareció en la línea {seen_profiles[profile_id]}."})
                continue
            seen_profiles[profile_id] = line
            try:
                base_happiness = normalize_happiness_value(row.get("base_happiness", row.get("baseline_happiness", row.get("starting_happiness"))))
            except ValueError:
                errors.append({"line": line, "message": f"Base de felicidad inválida para {raw_name or raw_profile_id or 'fila'}."})
                continue
            raw_events = row.get("events") or row.get("modifiers") or []
            if not isinstance(raw_events, list):
                errors.append({"line": line, "message": "events debe ser una lista."})
                continue
            cleaned_events: List[Dict[str, Any]] = []
            raw_total = 0.0
            simulated_events: List[Dict[str, Any]] = [
                {
                    "id": 1,
                    "event_type": EVENT_BASELINE_IMPORT,
                    "season_year": parse_int(row.get("base_season_year")),
                    "event_date": str(row.get("base_event_date") or row.get("base_date") or "")[:10] or None,
                    "previous_value": 0,
                    "applied_delta": float(base_happiness),
                    "new_value": float(base_happiness),
                }
            ]
            running_value = float(base_happiness)
            for event_index, raw_event in enumerate(raw_events, start=1):
                if not isinstance(raw_event, dict):
                    errors.append({"line": line, "event": event_index, "message": "Evento inválido."})
                    continue
                delta = parse_float(str(raw_event.get("delta", raw_event.get("applied_delta", raw_event.get("modifier", "")))))
                if delta is None:
                    errors.append({"line": line, "event": event_index, "message": "Delta inválido."})
                    continue
                event_date = str(raw_event.get("event_date") or raw_event.get("date") or "")[:10] or None
                season_year = parse_int(raw_event.get("season_year") or raw_event.get("season"))
                if season_year is None and event_date:
                    season_year = self.repository._season_year_for_date(event_date)
                if season_year is None:
                    errors.append({"line": line, "event": event_index, "message": "Cada evento histórico necesita season_year o event_date."})
                    continue
                try:
                    event_type = normalize_event_type(raw_event.get("event_type") or raw_event.get("type") or EVENT_MODIFIER)
                except ValueError:
                    errors.append({"line": line, "event": event_index, "message": f"Tipo de evento inválido: {raw_event.get('event_type') or raw_event.get('type')}"})
                    continue
                previous_value = running_value
                running_value = max(-10.0, min(10.0, running_value + float(delta)))
                cleaned_event = {
                    "line": event_index,
                    "event_type": event_type,
                    "season_year": int(season_year),
                    "event_date": event_date,
                    "applied_delta": float(delta),
                    "reason": str(raw_event.get("reason") or raw_event.get("description") or "Historical happiness modifier").strip(),
                    "metadata": raw_event.get("metadata") if isinstance(raw_event.get("metadata"), dict) else {},
                    "previous_value": previous_value,
                    "new_value": running_value,
                }
                cleaned_events.append(cleaned_event)
                simulated_events.append(
                    {
                        "id": event_index + 1,
                        "event_type": event_type,
                        "season_year": int(season_year),
                        "event_date": event_date,
                        "previous_value": previous_value,
                        "applied_delta": float(delta),
                        "new_value": running_value,
                    }
                )
                raw_total += float(delta)

            if any(error.get("line") == line for error in errors):
                continue
            recalculated = recency_recalculated_happiness(simulated_events, current_year)
            current = float(profile.get("happiness") or 0)
            records.append(
                {
                    "line": line,
                    "profile_id": profile_id,
                    "player_name": str(profile.get("name") or raw_name).strip(),
                    "input_player_name": raw_name,
                    "match_method": match_method,
                    "expected_version": int(profile.get("version") or 1),
                    "current_happiness": current,
                    "base_happiness": base_happiness,
                    "base_season_year": parse_int(row.get("base_season_year")),
                    "base_event_date": str(row.get("base_event_date") or row.get("base_date") or "")[:10] or None,
                    "base_reason": str(row.get("base_reason") or "Historical happiness ledger baseline").strip(),
                    "events": cleaned_events,
                    "event_count": len(cleaned_events),
                    "raw_modifier_total": raw_total,
                    "decayed_modifier_total": recalculated.get("modifier_total"),
                    "recalculated_happiness": recalculated.get("new_value"),
                    "changed": round(current, 4) != round(float(recalculated.get("new_value") or 0), 4),
                    "weighted_events": recalculated.get("weighted_events"),
                    "status_label": profile.get("status_label"),
                    "team_code": profile.get("team_code"),
                }
            )
        changed_count = sum(1 for record in records if record["changed"])
        return {
            "ok": not errors and not ambiguous,
            "current_year": current_year,
            "errors": errors,
            "records": records,
            "summary": {
                "input_count": len(rows),
                "matched_count": len(records),
                "event_count": sum(int(record.get("event_count") or 0) for record in records),
                "changed_count": changed_count,
                "unchanged_count": len(records) - changed_count,
                "unmatched_count": len(unmatched),
                "ambiguous_count": len(ambiguous),
                "error_count": len(errors),
            },
            "unmatched": unmatched,
            "ambiguous": ambiguous,
        }

    def apply_historical_ledger(self, records_payload: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        cleaned: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for raw in records_payload:
            if not isinstance(raw, dict):
                raise ValueError("invalid_records")
            profile_id = parse_int(raw.get("profile_id"))
            expected_version = parse_int(raw.get("expected_version"))
            player_name = str(raw.get("player_name") or "").strip()
            if profile_id is None or expected_version is None or not player_name:
                raise ValueError("invalid_records")
            if int(profile_id) in seen:
                raise ValueError("duplicate_happiness_import_target")
            seen.add(int(profile_id))
            try:
                base_happiness = normalize_happiness_value(raw.get("base_happiness"))
            except ValueError as exc:
                raise ValueError("invalid_records") from exc
            events = raw.get("events")
            if not isinstance(events, list):
                raise ValueError("invalid_records")
            cleaned_events = []
            for event in events:
                if not isinstance(event, dict):
                    raise ValueError("invalid_records")
                event_type = normalize_event_type(event.get("event_type") or EVENT_MODIFIER)
                delta = parse_float(str(event.get("applied_delta", event.get("delta", ""))))
                season_year = parse_int(event.get("season_year"))
                if delta is None or season_year is None:
                    raise ValueError("invalid_records")
                metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
                cleaned_events.append(
                    {
                        "line": parse_int(event.get("line")),
                        "event_type": event_type,
                        "season_year": int(season_year),
                        "event_date": str(event.get("event_date") or "")[:10] or None,
                        "applied_delta": float(delta),
                        "reason": str(event.get("reason") or "Historical happiness modifier").strip(),
                        "metadata": metadata,
                    }
                )
            cleaned.append(
                {
                    "profile_id": int(profile_id),
                    "player_name": player_name,
                    "input_player_name": raw.get("input_player_name"),
                    "match_method": raw.get("match_method") or "unknown",
                    "expected_version": int(expected_version),
                    "base_happiness": base_happiness,
                    "base_season_year": parse_int(raw.get("base_season_year")),
                    "base_event_date": str(raw.get("base_event_date") or "")[:10] or None,
                    "base_reason": raw.get("base_reason") or "Historical happiness ledger baseline",
                    "events": cleaned_events,
                }
            )
        timestamp = self._now()
        command_id = f"player-happiness:historical-ledger-import:{timestamp}"
        result = self.repository.apply_historical_ledger_import(
            cleaned,
            timestamp=timestamp,
            command_id=command_id,
            actor_user_id=parse_int((actor or {}).get("user_id")),
        )
        result["command_id"] = command_id
        result["validation_result"] = "valid"
        result["entity_versions"] = {
            "record_count": int(result.get("record_count") or 0),
            "inserted_event_count": int(result.get("inserted_event_count") or 0),
            "updated_count": int((result.get("recalculation") or {}).get("updated_count") or 0),
        }
        return result
