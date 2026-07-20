"""Administrative player and contract-option application workflows."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..domain._values import parse_bool, parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_bool, parse_int


class PlayerAdminService:
    def __init__(
        self,
        *,
        players: Any,
        requests: Any,
        free_agency: Any,
        settings: Any,
        contract_seasons: Iterable[int],
        unrestricted_type: str,
    ) -> None:
        self.players = players
        self.requests = requests
        self.free_agency = free_agency
        self.settings = settings
        self.contract_seasons = tuple(int(year) for year in contract_seasons)
        self.unrestricted_type = unrestricted_type

    def player(self, player_id: int) -> Optional[Dict[str, Any]]:
        return self.players.record(int(player_id))

    def option_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        return self.requests.get_gm_option_request(int(request_id))

    def _clear_contract(self, season: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for year in self.contract_seasons:
            if year < season:
                continue
            for suffix in ("text", "guaranteed_text", "note_text"):
                payload[f"salary_{year}_{suffix}"] = None
            payload[f"option_{year}"] = None
            for suffix in ("provisional", "partially_guaranteed", "note"):
                payload[f"salary_{year}_{suffix}"] = False
        return payload

    def decide_option(
        self,
        request_id: int,
        decision: str,
        actor: Dict[str, Any],
        *,
        note: Optional[str] = None,
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request_before = request or self.option_request(request_id)
        if not request_before:
            raise ValueError("request_not_found")
        if str(request_before.get("status") or "").lower() != "pending":
            raise ValueError("request_already_decided")
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            raise ValueError("invalid_decision")
        request_type = str(request_before.get("request_type") or "option")
        if normalized_decision == "rejected":
            updated = self.requests.mark_gm_option_request_decided(
                int(request_id), "rejected", actor or {}, note
            )
            if not updated:
                raise ValueError("request_already_decided")
            return {
                "request": updated,
                "response": {"ok": True, "request": updated},
                "audit": {
                    "action": "reject",
                    "entity": (
                        "gm_bird_rights_renounce_request"
                        if request_type == "bird_rights_renounce"
                        else "gm_option_request"
                    ),
                    "details": self._request_details(request_before),
                    "before": {"request": request_before},
                    "after": {"request": updated},
                },
            }

        option_field = str(request_before.get("option_field") or "").strip()
        option_value = str(request_before.get("option_value") or "").strip().upper()
        option_action = str(request_before.get("action") or "").strip().lower()
        player_id = parse_int(request_before.get("player_id"))
        if player_id is None:
            raise ValueError("invalid_player_id")
        player_before = self.player(player_id)
        if not player_before:
            raise ValueError("player_not_found")
        current_team = normalize_team_code(player_before.get("team_code"))
        request_team = normalize_team_code(request_before.get("team_code"))
        if request_team and current_team != request_team:
            raise ValueError(f"player_team_changed:{current_team or ''}:{request_team}")

        if request_type == "bird_rights_renounce":
            match = re.fullmatch(r"salary_(20\d{2})_text", option_field)
            season = parse_int(match.group(1)) if match else None
            if season is None:
                raise ValueError("invalid_bird_rights_field")
            if option_value not in {"FB", "EB", "NB"}:
                raise ValueError("invalid_bird_rights_value")
            if option_action != "renounced":
                raise ValueError("invalid_bird_rights_action")
            current_rights = str(player_before.get(option_field) or "").strip().upper()
            if current_rights != option_value:
                raise ValueError(f"bird_rights_changed:{current_rights}")
            updated = self._approve_request(request_id, actor, note)
            free_agent_id = self.free_agency.ensure_renounced_rights_free_agent(
                player_before, season, option_value
            )
            player_after = self.player(player_id)
            return self._decision_result(
                request_before,
                updated,
                player_before,
                player_after,
                details={
                    "player_id": player_id,
                    "player_name": request_before.get("player_name"),
                    "rights_action": option_action,
                    "rights_field": option_field,
                    "rights_value": option_value,
                    "rights_season": season,
                    "roster_removed": player_after is None,
                    "free_agent_id": free_agent_id,
                },
                entity="gm_bird_rights_renounce_request",
                notification={
                    "kind": "bird_rights",
                    "player": player_before,
                    "season": season,
                    "value": option_value,
                },
            )

        match = re.fullmatch(r"option_(20\d{2})", option_field)
        season = parse_int(match.group(1)) if match else None
        if season is None:
            raise ValueError("invalid_option_field")
        if option_value not in {"TO", "PO", "QO", "GAP"}:
            raise ValueError("invalid_option_value")
        if option_action not in {"accepted", "rejected"}:
            raise ValueError("invalid_option_action")
        current_option = str(player_before.get(option_field) or "").strip().upper()
        if current_option != option_value:
            raise ValueError(f"option_changed:{current_option}")

        if option_action == "rejected" and option_value == "QO":
            updated = self._approve_request(request_id, actor, note)
            removal = self.players.remove_from_roster(player_id)
            if removal is None:
                raise ValueError("player_not_found")
            player_after = self.player(player_id)
            result = self._decision_result(
                request_before,
                updated,
                player_before,
                player_after,
                details={
                    **self._request_details(request_before),
                    "option_action_season": season,
                    "roster_removed": True,
                    "free_agent_id": removal.get("free_agent_id"),
                    "free_agent_type": self.unrestricted_type,
                },
                notification={
                    "kind": "contract_option",
                    "player": player_before,
                    "season": season,
                    "value": option_value,
                    "action": option_action,
                },
            )
            result["response"].update(player=player_after, free_agent=removal)
            result["audit"]["after"]["free_agent"] = removal
            return result

        player_payload: Dict[str, Any]
        if option_action == "rejected" and option_value in {"TO", "PO"}:
            player_payload = self._clear_contract(season)
        elif option_action == "accepted" and option_value in {"QO", "GAP"}:
            player_payload = {option_field: option_value}
        else:
            player_payload = {option_field: None}
        if not self.players.update(player_id, player_payload):
            raise ValueError("player_not_found")
        player_after = self.player(player_id)
        updated = self._approve_request(request_id, actor, note)
        return self._decision_result(
            request_before,
            updated,
            player_before,
            player_after,
            details={
                **self._request_details(request_before),
                "option_action_season": season,
                "applied_fields": sorted(player_payload),
            },
            notification={
                "kind": "contract_option",
                "player": player_before,
                "season": season,
                "value": option_value,
                "action": option_action,
            },
        )

    def _approve_request(self, request_id: int, actor: Dict[str, Any], note: Optional[str]) -> Dict[str, Any]:
        updated = self.requests.mark_gm_option_request_decided(
            int(request_id), "approved", actor or {}, note
        )
        if not updated:
            raise ValueError("request_already_decided")
        return updated

    @staticmethod
    def _request_details(request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "player_id": request.get("player_id"),
            "player_name": request.get("player_name"),
            "option_action": request.get("action"),
            "option_field": request.get("option_field"),
            "option_value": request.get("option_value"),
        }

    @staticmethod
    def _decision_result(
        request_before: Dict[str, Any],
        request: Dict[str, Any],
        player_before: Dict[str, Any],
        player_after: Optional[Dict[str, Any]],
        *,
        details: Dict[str, Any],
        entity: str = "gm_option_request",
        notification: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "request": request,
            "response": {"ok": True, "request": request, "player": player_after},
            "notification": notification,
            "audit": {
                "action": "approve",
                "entity": entity,
                "details": details,
                "before": {"request": request_before, "player": player_before},
                "after": {"request": request, "player": player_after},
            },
        }

    def update_player(
        self,
        player_id: int,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> Dict[str, Any]:
        player_before = self.player(player_id)
        if not player_before:
            raise ValueError("player_not_found")
        applied = dict(payload)
        option_action = str(applied.pop("option_action", "") or "").strip().lower()
        option_field = str(applied.pop("option_action_field", "") or "").strip()
        option_value = str(applied.pop("option_action_value", "") or "").strip().upper()
        for field in ("notify_discord", "generate_image", "generate_discord_image", "discord_custom_image"):
            applied.pop(field, None)
        season = None
        if option_action:
            if option_action not in {"accepted", "rejected"}:
                raise ValueError("invalid_option_action")
            match = re.fullmatch(r"option_(20\d{2})", option_field)
            if not match:
                raise ValueError("invalid_option_action_field")
            season = parse_int(match.group(1))
            if season is None:
                raise ValueError("invalid_option_action_season")
            if not option_value:
                option_value = str(applied.get(option_field) or player_before.get(option_field) or "").strip().upper()
            if option_value not in {"TO", "PO", "QO", "GAP"}:
                raise ValueError("invalid_option_action_value")
            if option_action == "rejected" and option_value in {"TO", "PO"}:
                applied.update(self._clear_contract(season))
            elif option_action == "accepted" and option_value in {"TO", "PO"}:
                applied[option_field] = None
            elif option_action == "rejected":
                applied[option_field] = None
        if not self.players.update(player_id, applied):
            raise ValueError("player_not_found")
        player_after = self.player(player_id)
        decision = None
        if option_action and season is not None:
            try:
                decision = self.requests.record_admin_option_decision(
                    player_id, option_field, option_value, option_action, actor or {}
                )
            except ValueError:
                decision = None

        details: Dict[str, Any] = {"fields": sorted(applied)}
        settings = self.settings.get_all()
        current_year = parse_int(settings.get("current_year")) or 2025
        rights_field = f"salary_{current_year}_text"
        if (
            parse_bool(settings.get("free_agency_mode"))
            and rights_field in applied
            and str(player_before.get(rights_field) or "").strip().upper() in {"FB", "EB", "NB"}
            and not str((player_after or {}).get(rights_field) or "").strip()
        ):
            rights = str(player_before.get(rights_field) or "").strip().upper()
            free_agent_id = self.free_agency.ensure_renounced_rights_free_agent(
                player_before, current_year, rights
            )
            player_after = self.player(player_id)
            details.update(
                bird_rights_renounced=True,
                roster_removed=player_after is None,
                rights_field=rights_field,
                rights_value=rights,
                rights_season=current_year,
                free_agent_id=free_agent_id,
            )
        if option_action and season is not None:
            details.update(
                option_action=option_action,
                option_action_field=option_field,
                option_action_value=option_value,
                option_action_season=season,
                option_decision_request_id=(decision or {}).get("id"),
            )
        return {
            "player": player_after,
            "player_before": player_before,
            "details": details,
            "notification": (
                {
                    "kind": "contract_option",
                    "player": player_before,
                    "season": season,
                    "value": option_value,
                    "action": option_action,
                }
                if option_action and season is not None
                else None
            ),
        }
