"""Administrative team update workflows."""

from __future__ import annotations

from typing import Any, Dict

try:
    from ..domain.exceptions import normalize_apron_hard_cap
    from ..domain_rules import parse_float, parse_int
except ImportError:  # pragma: no cover
    from domain.exceptions import normalize_apron_hard_cap
    from domain_rules import parse_float, parse_int


class TeamAdminService:
    def __init__(self, teams: Any, settings: Any, *, min_year: int, max_year: int) -> None:
        self.teams = teams
        self.settings = settings
        self.min_year = int(min_year)
        self.max_year = int(max_year)

    def update(self, code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        if "gm" in payload:
            raw = payload.get("gm")
            fields["gm"] = None if raw is None else str(raw).strip() or None
        for field in ("cash_received", "cash_sent"):
            if field not in payload:
                continue
            value = parse_float(str(payload.get(field)))
            if value is None or value < 0:
                raise ValueError(f"invalid_{field}")
            fields[field] = value

        hard_cap_requested = "apron_hard_cap" in payload
        hard_cap = None
        season_year = parse_int(payload.get("season_year"))
        if hard_cap_requested:
            raw_hard_cap = str(payload.get("apron_hard_cap") or "").strip()
            hard_cap = normalize_apron_hard_cap(raw_hard_cap)
            if raw_hard_cap and hard_cap is None:
                raise ValueError("invalid_apron_hard_cap")
            if season_year is None:
                season_year = parse_int(self.settings.get_all().get("current_year")) or 2025
            if season_year < self.min_year or season_year > self.max_year:
                raise ValueError("invalid_season_year")
        if not fields and not hard_cap_requested:
            raise ValueError("team_update_required")

        ok = self.teams.update_fields(code, fields) if fields else True
        if ok and hard_cap_requested:
            ok = self.teams.update_hard_cap(code, int(season_year or 2025), hard_cap)
        details = dict(fields)
        if hard_cap_requested:
            details.update({"apron_hard_cap": hard_cap, "season_year": int(season_year or 2025)})
        return {"ok": ok, "audit": details if ok else None}
