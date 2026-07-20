"""Assemble the player-profile catalog read model."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

try:
    from ..db.repositories.player_catalog import PlayerCatalogRepository
    from ..domain.contracts import normalize_bird_years
    from ..domain_rules import parse_amount_like, parse_float, parse_int
except ImportError:  # pragma: no cover
    from db.repositories.player_catalog import PlayerCatalogRepository
    from domain.contracts import normalize_bird_years
    from domain_rules import parse_amount_like, parse_float, parse_int


class PlayerCatalogService:
    def __init__(
        self,
        db: Any,
        *,
        normalize_profile_status: Callable[[Any], str],
        is_unavailable_profile_status: Callable[[Any], bool],
        profile_status_label: Callable[[Any], str],
        sync_generated: Callable[..., Dict[str, Any]],
        table_exists: Callable[..., bool],
        min_contract_year: int,
        max_contract_start_year: int,
    ) -> None:
        self._repository = (
            db if isinstance(db, PlayerCatalogRepository)
            else getattr(db, "_player_catalog_repository", None) or PlayerCatalogRepository(db)
        )
        self._normalize_profile_status = normalize_profile_status
        self._is_unavailable = is_unavailable_profile_status
        self._profile_status_label = profile_status_label
        self._sync_generated = sync_generated
        self._min_contract_year = min_contract_year
        self._max_contract_start_year = max_contract_start_year

    @property
    def last_timings(self) -> Dict[str, float]:
        return dict(getattr(self._repository.db, "_last_list_players_timings", {}) or {})

    def list_players(
        self,
        include_private: bool = False,
        sync_generated: bool = True,
        include_salary_history: bool = True,
        collect_timings: bool = False,
    ) -> List[Dict[str, Any]]:
        timings: Dict[str, float] = {}
        started = time.perf_counter()

        def mark(label: str, since: float) -> float:
            current = time.perf_counter()
            if collect_timings:
                timings[label] = round((current - since) * 1000, 2)
            return current

        with self._repository.connection() as conn:
            settings = self._repository.settings(conn)
            checkpoint = mark("settings_ms", started)
            if sync_generated and self._sync_generated(conn, settings)["changed"]:
                self._repository.commit(conn)
            checkpoint = mark("sync_ms", checkpoint)
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < self._min_contract_year or current_year > self._max_contract_start_year:
                current_year = 2025

            profiles: Dict[int, Dict[str, Any]] = {}
            rows = self._repository.profiles(conn)
            for row in rows:
                profile = dict(row)
                profile_id = int(profile["id"])
                happiness = profile.pop("happiness", None)
                status = self._normalize_profile_status(profile.pop("profile_status", None))
                unavailable = self._is_unavailable(status)
                profiles[profile_id] = {
                    **profile, "profile_id": profile_id, "profile_status": status,
                    "status": status if unavailable else "inactive",
                    "status_label": self._profile_status_label(status) if unavailable else "Sin contrato",
                    "team_code": None, "team_name": None, "player_id": None, "free_agent_id": None,
                    "free_agent_type": None, "free_agent_source": None, "rights_team_code": None,
                    "dead_contract_id": None, "dead_contracts": [], "dead_contract_count": 0,
                    "dead_contract_summary": "", "position": None, "bird_rights": None, "rating": None,
                    "years_left": None, "signed_as_free_agent": None, "active_contract": False,
                    "active_contract_summary": "No", "transaction_logs": [],
                }
                if include_private:
                    profiles[profile_id]["happiness"] = happiness
            checkpoint = mark("profiles_ms", checkpoint)

            rows = self._repository.active_contracts(conn, current_year)
            rights_markers = {"NB", "EB", "FB", "QO", "GAP"}
            for row in rows:
                item = dict(row)
                profile_id = parse_int(item.get("profile_id"))
                if profile_id is None or profile_id not in profiles or profiles[profile_id]["active_contract"] or self._is_unavailable(profiles[profile_id]["profile_status"]):
                    continue
                salary_text = str(item.get("current_salary_text") or "").strip()
                option_code = str(item.get("current_option") or "").strip().upper()
                is_rights_marker = salary_text.upper() in rights_markers or option_code in rights_markers
                has_salary = parse_float(item.get("current_salary_num")) is not None or parse_amount_like(salary_text) is not None or (bool(salary_text) and salary_text != "-")
                if is_rights_marker or not has_salary:
                    continue
                parts = [str(item.get("team_code") or "").strip().upper(), str(item.get("position") or "").strip(), str(item.get("bird_rights") or "").strip()]
                bird_years = normalize_bird_years(item.get("years_left"))
                if bird_years is not None:
                    parts.append(f"{bird_years} birds")
                if salary_text:
                    parts.append(salary_text)
                profiles[profile_id].update({
                    "status": "active", "status_label": "En roster", "team_code": item.get("team_code"),
                    "team_name": item.get("team_name"), "player_id": item.get("player_id"),
                    "position": item.get("position"), "bird_rights": item.get("bird_rights"),
                    "rating": item.get("rating"), "years_left": item.get("years_left"),
                    "signed_as_free_agent": item.get("signed_as_free_agent"), "active_contract": True,
                    "active_contract_summary": " · ".join(part for part in parts if part) or "Sí",
                })
            checkpoint = mark("active_contracts_ms", checkpoint)

            rows = self._repository.free_agents(conn)
            for row in rows:
                item = dict(row)
                profile_id = parse_int(item.get("profile_id"))
                if profile_id is None or profile_id not in profiles or profiles[profile_id]["active_contract"] or self._is_unavailable(profiles[profile_id]["profile_status"]):
                    continue
                target = profiles[profile_id]
                rights_team = str(item.get("rights_team_code") or "").strip().upper() or None
                target.update({
                    "status": "free_agent", "status_label": f"Agente libre · derechos {rights_team}" if rights_team else "Agente libre",
                    "free_agent_id": item.get("free_agent_id"), "free_agent_type": item.get("free_agent_type"),
                    "free_agent_source": item.get("source"), "rights_team_code": rights_team,
                    "team_code": rights_team, "team_name": item.get("rights_team_name") if rights_team else None,
                    "position": target.get("position") or item.get("position"),
                    "bird_rights": target.get("bird_rights") or item.get("bird_rights"),
                    "rating": target.get("rating") or item.get("rating"),
                    "years_left": target.get("years_left") if target.get("years_left") is not None else item.get("years_left"),
                })
            checkpoint = mark("free_agents_ms", checkpoint)

            rows = self._repository.dead_contracts(conn)
            for row in rows:
                item = dict(row)
                profile_id = parse_int(item.get("profile_id"))
                if profile_id is None or profile_id not in profiles:
                    continue
                target = profiles[profile_id]
                target["dead_contracts"].append({key: item.get(key) for key in ("dead_contract_id", "team_code", "team_name", "dead_type", "label")})
                target["dead_contract_count"] = len(target["dead_contracts"])
                target["dead_contract_id"] = target.get("dead_contract_id") or item.get("dead_contract_id")
                target["dead_contract_summary"] = ", ".join(str(dead.get("team_code") or "").strip().upper() for dead in target["dead_contracts"] if str(dead.get("team_code") or "").strip())
                if target["status"] == "inactive":
                    target.update({"status": "dead_contract", "status_label": "CAP muerto", "team_code": item.get("team_code"), "team_name": item.get("team_name")})
            checkpoint = mark("dead_contracts_ms", checkpoint)

            rows = self._repository.transactions(conn)
            for row in rows:
                item = dict(row)
                profile_id = parse_int(item.get("profile_id"))
                if profile_id is not None and profile_id in profiles and len(profiles[profile_id]["transaction_logs"]) < 10:
                    profiles[profile_id]["transaction_logs"].append(item)
            checkpoint = mark("transactions_ms", checkpoint)

            if include_private and include_salary_history and profiles and self._repository.has_salary_history(conn):
                profile_ids = sorted(profiles)
                rows = self._repository.salary_history(conn, profile_ids)
                for row in rows:
                    item = dict(row)
                    profile_id = parse_int(item.get("profile_id"))
                    if profile_id is not None and profile_id in profiles:
                        profiles[profile_id].setdefault("salary_history", []).append(item)
            checkpoint = mark("salary_history_ms", checkpoint)

            result = sorted(
                (item for item in profiles.values() if include_private or not self._is_unavailable(item["profile_status"])),
                key=lambda item: str(item.get("name") or "").lower(),
            )
            mark("sort_ms", checkpoint)
            if collect_timings:
                timings.update({"total_ms": round((time.perf_counter() - started) * 1000, 2), "row_count": float(len(result))})
                self._repository.record_timings(timings)
            return result
