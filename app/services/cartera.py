"""Cartera capacity calculations and agent-client read-model assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    from ..db.repositories.cartera import CarteraRepository
    from ..domain._values import parse_amount_like, parse_int
except ImportError:  # pragma: no cover
    from db.repositories.cartera import CarteraRepository
    from domain._values import parse_amount_like, parse_int


@dataclass(frozen=True)
class CarteraOperations:
    settings: Callable[[], Dict[str, str]]
    teams: Callable[[], List[Dict[str, Any]]]
    team_detail: Callable[..., Optional[Dict[str, Any]]]
    exception_estimate: Callable[[Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]
    cap_hold_amount: Callable[[Dict[str, Any], int, Dict[str, str], float], float]
    cap_hold_label: Callable[[Dict[str, Any], int], str]
    season_label: Callable[[int], str]
    normalize_team_code: Callable[[Any], Optional[str]]
    user_access: Callable[[str], Dict[str, Any]]
    spending_limits: Callable[[], Any]
    forecast_min_year: int
    forecast_max_year: int


class CarteraService:
    def __init__(self, repository: CarteraRepository, operations: CarteraOperations) -> None:
        self.repository = repository
        self.operations = operations

    def cap_hold_rights(
        self, players: List[Dict[str, Any]], season_year: int,
        settings: Dict[str, str], salary_cap: float,
    ) -> List[Dict[str, Any]]:
        rights = []
        for player in players:
            amount = self.operations.cap_hold_amount(player, season_year, settings, salary_cap)
            if amount <= 0:
                continue
            rights.append({
                "player_id": parse_int(player.get("id")),
                "profile_id": parse_int(player.get("profile_id")),
                "player_name": str(player.get("name") or "Jugador").strip() or "Jugador",
                "hold_label": self.operations.cap_hold_label(player, season_year),
                "amount": round(float(amount)),
            })
        return sorted(rights, key=lambda row: (-float(row["amount"]), row["player_name"].lower()))

    @staticmethod
    def exception_paths(estimate: Dict[str, Any], target_amount: float) -> List[Dict[str, Any]]:
        paths: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add(item: Dict[str, Any], source: str, source_key: str = "") -> None:
            key = str(item.get("key") or item.get("short_label") or item.get("label") or "").strip()
            amount = float(item.get("amount") or 0.0)
            dedupe_key = (key, source_key)
            if amount < target_amount or dedupe_key in seen:
                return
            seen.add(dedupe_key)
            hard_cap = str(item.get("hard_cap") or "").strip()
            details = {
                "first": "Hard cap en el 1er apron si se usa.",
                "second": "Hard cap en el 2do apron si se usa.",
            }.get(hard_cap, "")
            paths.append({"type": "exception", "key": key,
                          "label": str(item.get("short_label") or item.get("label") or key).strip(),
                          "amount": round(amount), "source": source,
                          "hard_cap": hard_cap, "details": details})

        for item in estimate.get("eligible") or []:
            add(item, "Elegible según situación proyectada")
        for path in estimate.get("paths") or []:
            source = str(path.get("label") or "Ruta alternativa").strip()
            source_key = str(path.get("key") or source).strip()
            for item in path.get("eligible") or []:
                add(item, source, source_key)
        return paths

    def list_capacity(self, amount: Any, season_year: Optional[int] = None) -> Dict[str, Any]:
        target = parse_amount_like(amount)
        if target is None or target <= 0:
            raise ValueError("invalid_amount")
        settings = self.operations.settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        selected_year = parse_int(season_year) or current_year
        selected_year = max(self.operations.forecast_min_year,
                            min(self.operations.forecast_max_year, selected_year))
        rows = []
        for team in self.operations.teams():
            team_code = str(team.get("code") or "").strip().upper()
            detail = self.operations.team_detail(team_code, move_season_year=selected_year)
            summary = ((detail or {}).get("season_summaries") or {}).get(str(selected_year))
            if not detail or not summary:
                continue
            estimate = self.operations.exception_estimate(summary, detail.get("assets") or [])
            cap_space = float(summary.get("room_to_cap") or 0.0)
            cap_total = float(summary.get("cap_figure") or 0.0)
            salary_cap = float(summary.get("salary_cap") or 0.0)
            paths = []
            if cap_space >= target:
                paths.append({"type": "cap_space", "key": "cap_space", "label": "Espacio salarial",
                              "amount": round(cap_space), "source": "Debajo del Salary Cap",
                              "hard_cap": "", "details": "Puede absorber el importe con espacio salarial."})
            exception_paths = self.exception_paths(estimate, target)
            paths.extend(exception_paths)
            if not paths:
                continue
            rights = self.cap_hold_rights(detail.get("players") or [], selected_year, settings, salary_cap)
            cap_hold_total = sum(float(item["amount"]) for item in rights)
            review = bool(exception_paths and cap_hold_total > 0 and cap_total > salary_cap)
            rows.append({"team_code": team_code, "team_name": team.get("name"),
                         "season_year": selected_year, "season_label": self.operations.season_label(selected_year),
                         "cap_total": round(cap_total), "salary_cap": round(salary_cap),
                         "cap_space": round(cap_space),
                         "apron_account": round(float(summary.get("apron_account") or 0.0)),
                         "first_apron": round(float(summary.get("first_apron") or 0.0)),
                         "second_apron": round(float(summary.get("second_apron") or 0.0)),
                         "operating_mode": estimate.get("operating_mode"),
                         "paths": sorted(paths, key=lambda item: (item.get("type") != "cap_space", -float(item["amount"]))),
                         "cap_hold_total": round(cap_hold_total), "needs_renounce_review": review,
                         "rights_to_renounce": rights if review else []})
        rows.sort(key=lambda row: (
            not any(path.get("type") == "cap_space" for path in row["paths"]),
            -max((float(path["amount"]) for path in row["paths"]), default=0.0), row["team_code"],
        ))
        return {"amount": round(float(target)), "season_year": selected_year,
                "season_label": self.operations.season_label(selected_year),
                "seasons": [current_year + offset for offset in range(6)], "rows": rows}

    def list_clients(self, session: Dict[str, Any]) -> Dict[str, Any]:
        role = str(session.get("role") or "").strip().lower()
        email = str(session.get("email") or "").strip().lower()
        access = self.operations.user_access(email) if email else {}
        agent_name = re.sub(r"\s+", " ", str(
            access.get("agent_name") or session.get("agent_name") or ""
        ).strip())
        limits = self.operations.spending_limits()
        if role == "co_admin" and not agent_name:
            return {"agent_name": "", "clients": [], "missing_agent": True,
                    "gm_spending_limits": limits}
        snapshot = self.repository.client_snapshot(None if role == "admin" and not agent_name else agent_name)
        clients = []
        for row in snapshot["clients"]:
            client_id = int(row["id"])
            interests = snapshot["interests"].get(client_id, [])
            favorites = snapshot["favorites"].get(client_id, [])
            offers = snapshot["offers"].get(client_id, [])
            ruleouts = [item for item in snapshot["ruleouts"].get(client_id, [])
                        if str(item.get("agent_name") or "").strip().casefold()
                        == str(row.get("agent") or "").strip().casefold()]
            team_code = self.operations.normalize_team_code
            clients.append({"id": client_id, "profile_id": parse_int(row.get("profile_id")),
                            "name": str(row.get("name") or "").strip(),
                            "position": str(row.get("position") or "").strip(),
                            "rating": str(row.get("rating") or "").strip(),
                            "free_agent_type": str(row.get("free_agent_type") or "").strip(),
                            "rights_team_code": team_code(row.get("rights_team_code")),
                            "agent": str(row.get("agent") or "").strip(),
                            "interest_count": len(interests), "favorite_count": len(favorites),
                            "offer_count": len(offers),
                            "interests": [{"id": parse_int(item.get("id")), "team_code": team_code(item.get("team_code")),
                                "team_name": str(item.get("team_name") or "").strip(),
                                "economic_offer": str(item.get("economic_offer") or "").strip(),
                                "role_offer": str(item.get("role_offer") or "").strip(),
                                "comments": str(item.get("comments") or "").strip(),
                                "submitted_by_name": str(item.get("submitted_by_name") or "").strip(),
                                "updated_at": str(item.get("updated_at") or "").strip()} for item in interests],
                            "favorites": [{"id": parse_int(item.get("id")), "team_code": team_code(item.get("team_code")),
                                "team_name": str(item.get("team_name") or "").strip(),
                                "updated_at": str(item.get("updated_at") or item.get("created_at") or "").strip()} for item in favorites],
                            "offers": [{"team_code": team_code(item.get("team_code")),
                                "team_name": str(item.get("team_name") or "").strip(),
                                "status": str(item.get("status") or "").strip(),
                                "updated_at": str(item.get("updated_at") or item.get("created_at") or "").strip()} for item in offers],
                            "ruled_out_teams": [{"id": parse_int(item.get("id")), "team_code": team_code(item.get("team_code")),
                                "team_name": str(item.get("team_name") or "").strip(),
                                "updated_at": str(item.get("updated_at") or item.get("created_at") or "").strip()} for item in ruleouts]})
        clients.sort(key=lambda row: (-row["interest_count"], -row["favorite_count"], row["name"].casefold()))
        return {"agent_name": agent_name, "clients": clients, "missing_agent": False,
                "gm_spending_limits": limits}
