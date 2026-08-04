"""Admin workflows for user access and GM team assignments."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class UserAdminService:
    def __init__(
        self,
        repository: Any,
        *,
        gm_attractiveness: Any = None,
        player_happiness: Any = None,
    ) -> None:
        self.repository = repository
        self.gm_attractiveness = gm_attractiveness
        self.player_happiness = player_happiness

    @staticmethod
    def _by_team(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return {str(row.get("team_code") or "").strip().upper(): row for row in rows if str(row.get("team_code") or "").strip()}

    def list(self) -> List[Dict[str, Any]]:
        return self.repository.list()

    def access_for_email(self, email: str) -> Dict[str, Any]:
        return self.repository.access_for_email(email)

    def upsert_google_user(self, google_sub: str, email: str, display_name: Optional[str], avatar_url: Optional[str]) -> Dict[str, Any]:
        return self.repository.upsert_google_user(google_sub, email, display_name, avatar_url)

    def replace_team_assignments(
        self,
        user_id: int,
        team_codes: Any,
        *,
        is_co_admin: Optional[bool] = None,
        agent_name: Optional[Any] = None,
        username: Optional[Any] = None,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        before = self._by_team(self.repository.team_assignment_gm_snapshot(int(user_id)))
        user = self.repository.replace_team_assignments(
            int(user_id),
            team_codes,
            is_co_admin=is_co_admin,
            agent_name=agent_name,
            username=username,
        )
        if user is None:
            return None
        after = self._by_team(self.repository.team_assignment_gm_snapshot(int(user_id)))
        user["gm_change_happiness_impacts"] = self._apply_gm_change_happiness(
            user_id=int(user_id),
            before=before,
            after=after,
            actor=actor or {},
        )
        return user

    def _apply_gm_change_happiness(
        self,
        *,
        user_id: int,
        before: Dict[str, Dict[str, Any]],
        after: Dict[str, Dict[str, Any]],
        actor: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if self.gm_attractiveness is None or self.player_happiness is None:
            return []
        impacts: List[Dict[str, Any]] = []
        affected_team_codes = sorted(set(before.keys()) ^ set(after.keys()))
        for team_code in affected_team_codes:
            outgoing = before.get(team_code)
            incoming = after.get(team_code)
            ranking_entries = self.gm_attractiveness.bands_for_gm_change(
                incoming_gm_entity_id=(incoming or {}).get("gm_entity_id"),
                outgoing_gm_entity_id=(outgoing or {}).get("gm_entity_id"),
            )
            impact = self.player_happiness.apply_gm_change_impact(
                team_code=team_code,
                incoming_ranking_entry=ranking_entries.get("incoming"),
                outgoing_ranking_entry=ranking_entries.get("outgoing"),
                source_entity_type="user_team_assignment",
                source_entity_id=f"user:{int(user_id)}:team:{team_code}",
                actor=actor,
            )
            if impact.get("affected_count") or not impact.get("skipped"):
                impacts.append(impact)
        return impacts
