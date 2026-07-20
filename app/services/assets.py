"""Administrative asset and dead-contract workflows."""

from __future__ import annotations

from typing import Any, Dict, Optional


class AssetAdminService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def asset(self, asset_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.asset(asset_id)

    def dead_contract(self, dead_contract_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.dead_contract(dead_contract_id)

    def update_asset(
        self,
        asset_id: int,
        payload: Dict[str, Any],
        *,
        before: Dict[str, Any],
    ) -> Dict[str, Any]:
        if str(payload.get("asset_type") or "").strip().lower() == "dead_cap":
            raise ValueError("dead_cap_moved_to_dead_contracts")
        ok = self.repository.update_asset(asset_id, payload)
        after = self.repository.asset(asset_id) if ok else None
        return {
            "ok": ok,
            "audit": {
                "action": "update",
                "entity": "asset",
                "entity_id": str(asset_id),
                "team_code": before.get("team_code"),
                "details": {"fields": sorted(payload.keys())},
                "before": before,
                "after": after,
            } if ok else None,
        }

    def update_dead_contract(
        self,
        dead_contract_id: int,
        payload: Dict[str, Any],
        *,
        before: Dict[str, Any],
    ) -> Dict[str, Any]:
        ok = self.repository.update_dead_contract(dead_contract_id, payload)
        after = self.repository.dead_contract(dead_contract_id) if ok else None
        return {
            "ok": ok,
            "audit": {
                "action": "update",
                "entity": "dead_contract",
                "entity_id": str(dead_contract_id),
                "team_code": before.get("team_code"),
                "details": {"fields": sorted(payload.keys())},
                "before": before,
                "after": after,
            } if ok else None,
        }
