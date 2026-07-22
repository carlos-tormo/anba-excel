"""Trade archive application service."""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from ..auth.policies import normalize_team_code
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_int


class TradeArchiveService:
    def __init__(self, repository: Any):
        self.repository = repository

    @staticmethod
    def _movement_payload(value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        cleaned: Dict[str, Any] = {}
        for key in ("players", "picks", "swaps", "rights", "cash"):
            raw = value.get(key)
            if isinstance(raw, list):
                cleaned[key] = [item for item in raw if str(item or "").strip()]
        if value.get("cash_amount") not in (None, ""):
            cleaned["cash_amount"] = value.get("cash_amount")
        return cleaned

    @classmethod
    def _normalize_team_movements(cls, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("trade_team_movements_required")
        movements: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            team_code = normalize_team_code(item.get("team_code") or item.get("code"))
            if not team_code or team_code in seen:
                continue
            seen.add(team_code)
            movements.append(
                {
                    "team_code": team_code,
                    "team_name": str(item.get("team_name") or "").strip() or None,
                    "sent": cls._movement_payload(item.get("sent")),
                    "received": cls._movement_payload(item.get("received")),
                }
            )
        if len(movements) < 2:
            raise ValueError("trade_requires_multiple_teams")
        return movements

    @classmethod
    def normalize_payload(cls, payload: Dict[str, Any], *, source: str = "manual") -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("invalid_trade_archive_payload")
        season = parse_int(payload.get("season_year") if "season_year" in payload else payload.get("season"))
        if season is None or season < 1900 or season > 2200:
            raise ValueError("invalid_trade_season")
        trade_date = str(payload.get("trade_date") or payload.get("date") or "").strip()
        if not trade_date:
            raise ValueError("trade_date_required")
        team_movements = cls._normalize_team_movements(payload.get("team_movements") or payload.get("teams"))
        normalized = {
            "external_trade_id": str(payload.get("external_trade_id") or payload.get("trade_id") or "").strip() or None,
            "trade_date": trade_date,
            "season_year": season,
            "team_movements": team_movements,
            "total_assets_moved": parse_int(payload.get("total_assets_moved")),
            "source": source,
            "source_ref": str(payload.get("source_ref") or "").strip() or None,
            "notes": str(payload.get("notes") or "").strip() or None,
        }
        return normalized

    @classmethod
    def from_processed_trade_result(
        cls,
        result: Dict[str, Any],
        *,
        workflow_run_id: str,
        actor: Any = None,
        timestamp: str,
    ) -> Dict[str, Any]:
        if not isinstance(result, dict):
            raise ValueError("invalid_processed_trade_result")
        season = parse_int(result.get("season"))
        if season is None:
            raise ValueError("invalid_trade_season")
        team_movements: List[Dict[str, Any]] = []
        teams = result.get("teams") if isinstance(result.get("teams"), list) else []
        if teams:
            for team in teams:
                if not isinstance(team, dict):
                    continue
                team_movements.append(
                    {
                        "team_code": team.get("code"),
                        "team_name": team.get("name"),
                        "sent": team.get("sent") if isinstance(team.get("sent"), dict) else {},
                        "received": team.get("received") if isinstance(team.get("received"), dict) else {},
                    }
                )
        else:
            team_a = result.get("team_a") if isinstance(result.get("team_a"), dict) else {}
            team_b = result.get("team_b") if isinstance(result.get("team_b"), dict) else {}
            code_a = team_a.get("code")
            code_b = team_b.get("code")
            team_movements = [
                {
                    "team_code": code_a,
                    "sent": {
                        "players": result.get("players_a") or [],
                        "picks": result.get("pick_refs_a") or [],
                        "swaps": result.get("swap_refs_a") or [],
                    },
                    "received": {
                        "players": result.get("players_b") or [],
                        "picks": result.get("pick_refs_b") or [],
                        "swaps": result.get("swap_refs_b") or [],
                    },
                },
                {
                    "team_code": code_b,
                    "sent": {
                        "players": result.get("players_b") or [],
                        "picks": result.get("pick_refs_b") or [],
                        "swaps": result.get("swap_refs_b") or [],
                    },
                    "received": {
                        "players": result.get("players_a") or [],
                        "picks": result.get("pick_refs_a") or [],
                        "swaps": result.get("swap_refs_a") or [],
                    },
                },
            ]
        return cls.normalize_payload(
            {
                "external_trade_id": workflow_run_id,
                "trade_date": timestamp[:10],
                "season_year": season,
                "team_movements": team_movements,
                "source_ref": workflow_run_id,
                "notes": f"Processed trade by {actor.get('email')}" if isinstance(actor, dict) and actor.get("email") else None,
            },
            source="processed_trade",
        )

    def list(self, *, season_year: Any = None) -> Dict[str, Any]:
        return self.repository.list(season_year=season_year)

    def get(self, trade_id: Any) -> Dict[str, Any] | None:
        return self.repository.get(trade_id)

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.create(self.normalize_payload(payload))

    def import_trades(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_trades = payload.get("trades") if isinstance(payload, dict) else None
        if not isinstance(raw_trades, list):
            raise ValueError("trades_required")
        created = []
        errors = []
        for index, raw in enumerate(raw_trades):
            try:
                created.append(self.repository.create(self.normalize_payload(raw, source="admin_import")))
            except Exception as err:  # noqa: BLE001 - return row-level import errors to admin.
                errors.append({"index": index, "error": str(err) or "trade_import_failed"})
        return {"ok": not errors, "created": created, "errors": errors}

    def update(self, trade_id: Any, payload: Dict[str, Any]) -> Dict[str, Any] | None:
        existing = self.get(trade_id)
        if not existing:
            return None
        base = dict(existing)
        base.pop("trade_id", None)
        merged = {
            **base,
            **(payload or {}),
            "team_movements": (payload or {}).get("team_movements", existing.get("team_movements")),
        }
        return self.repository.update(trade_id, self.normalize_payload(merged))

    def delete(self, trade_id: Any) -> bool:
        return self.repository.delete(trade_id)
