"""Role and team-scoped authorization policy."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def normalize_team_code(value: Any) -> Optional[str]:
    code = str(value or "").strip().upper()
    if code == "PHO":
        code = "PHX"
    return code if code else None


def normalize_team_codes(value: Any) -> List[str]:
    if value is None:
        raw_items: List[Any] = []
    elif isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raw_items = []
        else:
            try:
                parsed = json.loads(raw)
                raw_items = parsed if isinstance(parsed, list) else [raw]
            except json.JSONDecodeError:
                raw_items = re.split(r"[,/|]", raw)
    else:
        raw_items = [value]
    codes: List[str] = []
    for item in raw_items:
        code = normalize_team_code(item)
        if code and code not in codes:
            codes.append(code)
    return codes


def parse_gm_account_map(value: Any) -> Dict[str, List[str]]:
    if value is None:
        return {}
    raw = str(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        parsed_items: List[Any] = [
            {"email": email, "teams": teams} for email, teams in parsed.items()
        ]
    elif isinstance(parsed, list):
        parsed_items = parsed
    else:
        parsed_items = re.split(r"[\n,]+", raw)

    mapping: Dict[str, List[str]] = {}
    for item in parsed_items:
        if isinstance(item, dict):
            email = str(item.get("email") or "").strip().lower()
            teams_value = item.get("teams") or item.get("team_codes") or item.get("team_code")
        else:
            text = str(item or "").strip()
            if not text:
                continue
            if "=" in text:
                email, teams_value = text.split("=", 1)
            elif ":" in text:
                email, teams_value = text.split(":", 1)
            else:
                continue
            email = email.strip().lower()
        if email and "@" in email:
            team_codes = normalize_team_codes(teams_value)
            if team_codes:
                mapping[email] = team_codes
    return mapping


def serialize_team_codes(value: Any) -> Optional[str]:
    codes = normalize_team_codes(value)
    return json.dumps(codes, ensure_ascii=True) if codes else None


class AuthorizationError(Exception):
    def __init__(self, status: int, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


AUTH_POLICIES: Dict[str, Dict[str, Any]] = {
    "gm_office.view": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm_office.free_agent_spending_limit.update": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm_office.minimum_targets.update": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm_office.depth_chart.update": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm.option_request.create": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm.bird_rights_renounce.create": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm.free_agent_offer.create": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm.free_agent_favorite.update": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm.free_agent_offer.cancel": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "gm.waiver_claim.create": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "owner_office.view": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "owner_exit_interview.update": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "draft_live.pick_submit": {"roles": {"admin", "gm", "co_admin"}, "team_scope": True},
    "notifications.view": {"roles": {"admin", "gm", "co_admin", "guest"}, "team_scope": False},
    "notifications.read": {"roles": {"admin", "gm", "co_admin", "guest"}, "team_scope": False},
    "coadmin.cartera.view": {"roles": {"admin", "co_admin"}, "team_scope": False},
    "coadmin.cartera.ruleout": {"roles": {"admin", "co_admin"}, "team_scope": False},
    "coadmin.vote.list": {"roles": {"co_admin"}, "team_scope": False},
    "coadmin.vote.submit": {"roles": {"co_admin"}, "team_scope": False},
    "admin.team.write": {"roles": {"admin"}, "team_scope": True},
    "admin.player.write": {"roles": {"admin"}, "team_scope": True},
    "admin.player.cut": {"roles": {"admin"}, "team_scope": True},
    "admin.player.remove": {"roles": {"admin"}, "team_scope": True},
    "admin.player.move": {"roles": {"admin"}, "team_scope": True},
    "admin.free_agent.sign": {"roles": {"admin"}, "team_scope": True},
    "admin.trade.process": {"roles": {"admin"}, "team_scope": True},
    "admin.team_moves.write": {"roles": {"admin"}, "team_scope": True},
    "admin.draft_asset.write": {"roles": {"admin"}, "team_scope": True},
    "admin.frozen_draft_pick.write": {"roles": {"admin"}, "team_scope": True},
    "admin.dead_contract.write": {"roles": {"admin"}, "team_scope": True},
    "admin.gm_history.write": {"roles": {"admin"}, "team_scope": True},
    "admin.gm_draft_pick_request.decide": {"roles": {"admin"}, "team_scope": True},
    "admin.gm_free_agent_offer_request.decide": {"roles": {"admin"}, "team_scope": True},
    "admin.waiver_claim_request.decide": {"roles": {"admin"}, "team_scope": True},
    "admin.gm_option_request.decide": {"roles": {"admin"}, "team_scope": True},
    "admin.player_profile.view": {"roles": {"admin"}, "team_scope": False},
    "admin.player_profile.write": {"roles": {"admin"}, "team_scope": False},
    "admin.player_catalog.view": {"roles": {"admin"}, "team_scope": False},
    "admin.gm_minimum_targets.view": {"roles": {"admin"}, "team_scope": False},
    "admin.gm_minimum_targets.write": {"roles": {"admin"}, "team_scope": False},
    "admin.draft_live.write": {"roles": {"admin"}, "team_scope": False},
    "admin.article.write": {"roles": {"admin"}, "team_scope": False},
    "admin.coadmin_vote.view": {"roles": {"admin"}, "team_scope": False},
    "admin.coadmin_vote.write": {"roles": {"admin"}, "team_scope": False},
    "admin.promise.write": {"roles": {"admin"}, "team_scope": False},
    "admin.offseason_exceptions.view": {"roles": {"admin"}, "team_scope": False},
    "admin.offseason_exceptions.write": {"roles": {"admin"}, "team_scope": False},
    "admin.import.write": {"roles": {"admin"}, "team_scope": False},
    "admin.backup.create": {"roles": {"admin"}, "team_scope": False},
    "admin.draft_order.write": {"roles": {"admin"}, "team_scope": False},
    "admin.free_agent.write": {"roles": {"admin"}, "team_scope": False},
    "admin.tracker_economy.write": {"roles": {"admin"}, "team_scope": False},
    "admin.users.view": {"roles": {"admin"}, "team_scope": False},
    "admin.users.write": {"roles": {"admin"}, "team_scope": False},
    "admin.audit.view": {"roles": {"admin"}, "team_scope": False},
    "admin.maintenance.view": {"roles": {"admin"}, "team_scope": False},
    "admin.gm_history.view": {"roles": {"admin"}, "team_scope": False},
    "admin.gm_option_request.view": {"roles": {"admin"}, "team_scope": False},
    "admin.global.write": {"roles": {"admin"}, "team_scope": False},
}


def authorization_actor_from_session(session: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not session:
        return None
    return {
        "user_id": session.get("user_id"),
        "email": session.get("email"),
        "role": str(session.get("role") or "").strip().lower(),
        "team_codes": normalize_team_codes(session.get("team_codes")),
    }


def authorize_action(
    actor: Optional[Dict[str, Any]],
    action: str,
    resource: Optional[Dict[str, Any]] = None,
) -> bool:
    policy = AUTH_POLICIES.get(action)
    if not policy:
        raise AuthorizationError(403, "action_not_allowed")
    if not actor:
        raise AuthorizationError(401, "auth_required")
    role = str(actor.get("role") or "").strip().lower()
    if role not in policy.get("roles", set()):
        raise AuthorizationError(403, "forbidden")
    if role == "admin":
        return True
    if policy.get("team_scope"):
        team_code = normalize_team_code((resource or {}).get("team_code"))
        if not team_code:
            raise AuthorizationError(400, "team_code_required")
        if team_code not in normalize_team_codes(actor.get("team_codes")):
            raise AuthorizationError(403, "team_access_required")
    return True
