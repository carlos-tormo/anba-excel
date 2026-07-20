"""Player identity and canonical-profile synchronization service.

The service coordinates profile operations and generated identity projections
through configured repositories while callers use one stable application boundary.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

try:
    from ..db.repositories.player_identity import PlayerIdentityRepository
    from ..domain._values import parse_bool
except ImportError:  # pragma: no cover - supports direct script execution.
    from db.repositories.player_identity import PlayerIdentityRepository
    from domain._values import parse_bool


class PlayerIdentityService:
    def __init__(self, db: Any, *, contract_seasons: Iterable[int]) -> None:
        if isinstance(db, PlayerIdentityRepository):
            self.repository = db
        else:
            self.repository = getattr(db, "_player_identity_repository", None) or PlayerIdentityRepository(db)
        self.contract_seasons = tuple(sorted({int(season) for season in contract_seasons}))
        if not self.contract_seasons:
            raise ValueError("contract_seasons_required")

    def update_profile(self, profile_id: int, payload: Dict[str, Any]) -> bool:
        return bool(self.repository.update_profile(int(profile_id), payload))

    def delete_profile(self, profile_id: int) -> Dict[str, Any]:
        return self.repository.delete_profile(int(profile_id))

    def merge_profiles(
        self, source_profile_id: int, target_profile_id: int
    ) -> Dict[str, Any]:
        return self.repository.merge_profiles(
            int(source_profile_id), int(target_profile_id)
        )

    def integrity_report(self) -> Dict[str, Any]:
        return self.repository.integrity_report()

    def assert_integrity(self) -> None:
        self.repository.assert_integrity()

    def payload_affects_generated_sync(self, payload: Dict[str, Any]) -> bool:
        if "bird_rights" in payload or "years_left" in payload:
            return True
        return any(
            f"salary_{season}_text" in payload or f"option_{season}" in payload
            for season in self.contract_seasons
        )

    def synchronize(self) -> Dict[str, int]:
        """Refresh all generated identity projections in one write transaction."""
        with self.repository.synchronized_transaction() as conn:
            return self.synchronize_generated_free_agents(conn)

    def synchronize_generated_free_agents(
        self,
        conn: Any,
        settings: Optional[Dict[str, str]] = None,
    ) -> Dict[str, int]:
        effective_settings = settings or self._settings(conn)
        cap_hold_changes = int(
            self.repository.sync_cap_hold_free_agents(conn, effective_settings) or 0
        )
        uncontracted_changes = int(
            self.repository.sync_uncontracted_profile_free_agents(conn) or 0
        )
        return {
            "changed": cap_hold_changes + uncontracted_changes,
            "cap_hold_changes": cap_hold_changes,
            "uncontracted_profile_changes": uncontracted_changes,
        }

    def synchronize_for_player_update(
        self,
        conn: Any,
        payload: Dict[str, Any],
    ) -> Dict[str, int]:
        if not self.payload_affects_generated_sync(payload):
            return self._empty_sync_result()
        settings = self._settings(conn)
        if not parse_bool(settings.get("free_agency_mode")):
            return self._empty_sync_result()
        return self.synchronize_generated_free_agents(conn, settings)

    def _settings(self, conn: Any) -> Dict[str, str]:
        return self.repository.settings(conn)

    @staticmethod
    def _empty_sync_result() -> Dict[str, int]:
        return {
            "changed": 0,
            "cap_hold_changes": 0,
            "uncontracted_profile_changes": 0,
        }
