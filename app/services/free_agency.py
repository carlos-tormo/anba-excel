"""Free-agency offer application service.

This module owns offer policy and orchestration. HTTP concerns such as CSRF,
authorization, response codes, audit logging, and notification delivery remain
in the request handler.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..db.repositories.free_agency import FreeAgencyRepository
    from ..domain._values import parse_amount_like, parse_int
    from ..domain.cap import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR
    from ..domain.contracts import (
        TWO_WAY_MINIMUM_BASE_SALARY,
        cap_hold_bird_code_from_years,
        maximum_salary_for_experience,
        minimum_salary_for_season,
        normalize_experience_years,
        scaled_minimum_salary,
    )
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from db.repositories.free_agency import FreeAgencyRepository
    from domain._values import parse_amount_like, parse_int
    from domain.cap import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR
    from domain.contracts import (
        TWO_WAY_MINIMUM_BASE_SALARY,
        cap_hold_bird_code_from_years,
        maximum_salary_for_experience,
        minimum_salary_for_season,
        normalize_experience_years,
        scaled_minimum_salary,
    )


@dataclass(frozen=True)
class OfferDecisionOptions:
    note: Optional[str] = None
    notify_discord: bool = False
    generate_image: bool = False
    custom_image: Optional[Dict[str, Any]] = None
    bypass_role_limits: bool = False


class FreeAgencyService:
    """Coordinates free-agent offer policy with persistence."""

    ROLE_OPTIONS = (
        "Titular",
        "Sexto hombre",
        "Minutos de rotación (10-20)",
        "Minutos de rotación (0-9)",
        "Fuera de la rotación",
    )

    def __init__(
        self,
        db: Any,
        *,
        contract_seasons: Iterable[int],
        cap_hold_source: str = "cap_hold",
        gm_requests: Any = None,
        offer_promises: Any = None,
        players: Any = None,
    ) -> None:
        if isinstance(db, FreeAgencyRepository):
            self.repository = db
        else:
            self.repository = getattr(db, "_free_agency_repository", None) or FreeAgencyRepository(db)
        backing_db = getattr(self.repository, "db", db)
        self.gm_requests = gm_requests or getattr(backing_db, "_gm_request_service", None) or getattr(backing_db, "_gm_request_repository", None)
        self.offer_promises = offer_promises or getattr(backing_db, "_offer_promise_service", None) or getattr(backing_db, "_offer_promise_repository", None)
        self.players = players or getattr(backing_db, "_player_repository", None)
        self.contract_seasons = tuple(sorted({int(season) for season in contract_seasons}))
        if not self.contract_seasons:
            raise ValueError("contract_seasons_required")
        self.contract_min_year = min(self.contract_seasons)
        self.contract_max_year = max(self.contract_seasons)
        self.cap_hold_source = str(cap_hold_source or "cap_hold")

    def submit_offer(
        self,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate, normalize, classify, and persist a GM offer."""
        free_agent = self.repository.free_agent(int(free_agent_id))
        if not free_agent:
            raise ValueError("free_agent_not_found")
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("invalid_team_code")
        offer_type = "renewal" if self.is_renewal(free_agent, normalized_team) else "free_agent_offer"
        normalized_payload = self.normalize_offer(free_agent, normalized_team, payload)
        request = self.gm_requests.create_gm_free_agent_offer_request(
            int(free_agent_id),
            normalized_team,
            normalized_payload,
            actor or {},
            offer_type,
        )
        if not request:
            raise ValueError("free_agent_not_found")
        return {
            "free_agent": free_agent,
            "team_code": normalized_team,
            "offer_type": offer_type,
            "payload": normalized_payload,
            "request": request,
        }

    def offer_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        return self.gm_requests.get_gm_free_agent_offer_request(int(request_id))

    def negotiate(
        self,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> Dict[str, Any]:
        free_agent = self.repository.free_agent(int(free_agent_id))
        if not free_agent:
            raise ValueError("free_agent_not_found")
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("invalid_team_code")
        interest = self.repository.record_interest(
            int(free_agent_id), normalized_team, payload, actor or {}
        )
        return {
            "free_agent": free_agent,
            "team_code": normalized_team,
            "interest": interest,
            "audit": {
                "interest_id": interest.get("id"),
                "player_name": free_agent.get("name"),
                "agent": str(free_agent.get("agent") or "").strip(),
                "economic_offer": str(payload.get("economic_offer") or "").strip(),
                "role_offer": str(payload.get("role_offer") or "").strip(),
            },
        }

    def set_favorite(
        self,
        free_agent_id: int,
        team_code: str,
        actor: Dict[str, Any],
        *,
        favorite: bool,
    ) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("invalid_team_code")
        if favorite:
            row = self.repository.set_favorite(
                int(free_agent_id), normalized_team, actor or {}
            )
            return {"favorite": row, "is_favorite": True, "team_code": normalized_team}
        self.repository.delete_favorite(int(free_agent_id), normalized_team)
        return {"favorite": None, "is_favorite": False, "team_code": normalized_team}

    def cancel_offer(
        self,
        request_id: int,
        actor: Dict[str, Any],
        *,
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request_before = request or self.offer_request(request_id)
        if not request_before:
            raise ValueError("request_not_found")
        team_code = normalize_team_code(request_before.get("team_code"))
        if not team_code:
            raise ValueError("team_code_required")
        canceled = self.gm_requests.cancel_gm_free_agent_offer_request(
            int(request_id), team_code, actor=actor or {}
        )
        if not canceled:
            raise ValueError("request_not_found")
        return {
            "request_before": request_before,
            "request": canceled,
            "team_code": team_code,
        }

    def sign_free_agent(
        self,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized_team = normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        player_id = self.repository.sign(int(free_agent_id), normalized_team, payload)
        if not player_id:
            raise ValueError("free_agent_or_team_not_found")
        return {
            "free_agent_id": int(free_agent_id),
            "team_code": normalized_team,
            "player_id": player_id,
            "player": self.players.record(player_id),
        }

    def create_promise(self, payload: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
        is_admin = str((actor or {}).get("role") or "").strip().lower() == "admin"
        return self.offer_promises.create_free_agent_offer_promise(
            payload,
            actor or {},
            bypass_role_limits=is_admin,
        )

    def list_promises(
        self,
        actor: Dict[str, Any],
        *,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.offer_promises.list_free_agent_offer_promises(actor or {}, status=status)

    def update_promise(
        self,
        promise_id: int,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        is_admin = str((actor or {}).get("role") or "").strip().lower() == "admin"
        return self.offer_promises.update_free_agent_offer_promise(
            int(promise_id),
            payload,
            actor or {},
            bypass_role_limits=is_admin,
        )

    def request_bird_rights_renunciation(
        self,
        player_id: int,
        season_year: int,
        rights_value: str,
        actor: Dict[str, Any],
        *,
        player: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        player_record = player or self.players.record(int(player_id))
        if not player_record:
            raise ValueError("player_not_found")
        request = self.gm_requests.create_gm_bird_rights_renounce_request(
            int(player_id), int(season_year), rights_value, actor or {}
        )
        if not request:
            raise ValueError("player_not_found")
        return {"player": player_record, "request": request}

    def decide_offer(
        self,
        request_id: int,
        decision: str,
        actor: Dict[str, Any],
        *,
        options: Optional[OfferDecisionOptions] = None,
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Approve or reject an offer and return audit-ready command output."""
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            raise ValueError("invalid_decision")
        command_options = options or OfferDecisionOptions()
        request_before = request or self.offer_request(request_id)
        if not request_before:
            raise ValueError("request_not_found")
        if str(request_before.get("status") or "").strip().lower() != "pending":
            raise ValueError("request_already_decided")

        if normalized_decision == "rejected":
            result = self.gm_requests.decide_gm_free_agent_offer_request_command(
                int(request_id),
                "rejected",
                actor or {},
                note=command_options.note,
            )
            return {
                **result,
                "decision": "rejected",
                "request_before": request_before,
                "free_agent_id": parse_int(request_before.get("free_agent_id")),
                "team_code": normalize_team_code(request_before.get("team_code")),
                "offer_type": request_before.get("offer_type"),
                "offer_payload": {},
            }

        free_agent_id = parse_int(request_before.get("free_agent_id"))
        if free_agent_id is None:
            raise ValueError("invalid_free_agent_id")
        free_agent = self.repository.free_agent(free_agent_id)
        if not free_agent:
            raise ValueError("free_agent_not_found")
        team_code = normalize_team_code(request_before.get("team_code"))
        if not team_code:
            raise ValueError("invalid_team_code")
        offer_payload = (
            dict(request_before.get("offer_payload"))
            if isinstance(request_before.get("offer_payload"), dict)
            else {}
        )
        if request_before.get("player_name"):
            offer_payload.setdefault("player_name", request_before.get("player_name"))
        sign_payload = self.player_payload_from_offer(free_agent, offer_payload)
        result = self.gm_requests.decide_gm_free_agent_offer_request_command(
            int(request_id),
            "approved",
            actor or {},
            note=command_options.note,
            sign_payload=sign_payload,
            offer_payload=offer_payload,
            notify_discord=command_options.notify_discord,
            generate_image=command_options.generate_image,
            custom_image=command_options.custom_image,
            promise_context={"free_agent": free_agent},
            bypass_role_limits=command_options.bypass_role_limits,
        )
        player_id = result.get("player_id")
        if not player_id:
            raise ValueError("free_agent_or_team_not_found")
        updated = result.get("request")
        if (
            request_before.get("player_name")
            and updated
            and str(updated.get("player_name") or "Agente libre") == "Agente libre"
        ):
            updated["player_name"] = request_before.get("player_name")
        return {
            **result,
            "decision": "approved",
            "request_before": request_before,
            "free_agent_id": free_agent_id,
            "team_code": team_code,
            "offer_type": request_before.get("offer_type"),
            "offer_payload": offer_payload,
        }

    @staticmethod
    def admin_decision_output(
        request_id: int,
        result: Dict[str, Any],
        *,
        discord_sent: bool = False,
    ) -> Dict[str, Any]:
        request_before = result.get("request_before") or {}
        request = result.get("request")
        decision = str(result.get("decision") or "").strip().lower()
        if decision == "rejected":
            return {
                "response": {"ok": True, "request": request},
                "audit": {
                    "action": "reject",
                    "details": {
                        "free_agent_id": result.get("free_agent_id"),
                        "player_name": request_before.get("player_name"),
                        "offer_type": result.get("offer_type"),
                    },
                    "before": {"request": request_before},
                    "after": {"request": request},
                },
            }
        offer_payload = result.get("offer_payload") or {}
        return {
            "response": {
                "ok": True,
                "request": request,
                "player_id": result.get("player_id"),
                "discord_sent": bool(discord_sent),
            },
            "audit": {
                "action": "approve",
                "details": {
                    "free_agent_id": result.get("free_agent_id"),
                    "player_id": result.get("player_id"),
                    "player_name": request_before.get("player_name"),
                    "offer_type": request_before.get("offer_type"),
                    "contract_type": offer_payload.get("contract_type"),
                    "years": offer_payload.get("years"),
                    "sent_to_discord": bool(discord_sent),
                },
                "before": {"request": request_before},
                "after": {"request": request, "player": result.get("player")},
            },
        }

    def is_renewal(self, free_agent: Dict[str, Any], team_code: str) -> bool:
        if str(free_agent.get("source") or "").strip() != self.cap_hold_source:
            return False
        team = normalize_team_code(team_code)
        rights_team = normalize_team_code(free_agent.get("rights_team_code"))
        if not rights_team:
            notes = str(free_agent.get("notes") or "")
            match = re.search(r"Cap hold retenido por\s+([A-Z]{2,4})", notes, flags=re.IGNORECASE)
            if match:
                rights_team = normalize_team_code(match.group(1))
        return bool(team and rights_team and team == rights_team)

    @staticmethod
    def bird_rights_code(free_agent: Dict[str, Any]) -> str:
        raw = re.sub(r"[\s_-]+", "", str(free_agent.get("bird_rights") or "").strip().upper())
        if raw in {"FB", "FULLBIRD"}:
            return "FB"
        if raw in {"EB", "EARLYBIRD"}:
            return "EB"
        if raw in {"NB", "NONBIRD"}:
            return "NB"
        return cap_hold_bird_code_from_years(free_agent.get("years_left"))

    @staticmethod
    def offer_start_season(settings: Dict[str, Any]) -> int:
        current_year = parse_int(settings.get("current_year")) or CAP_FORECAST_MIN_YEAR
        if current_year < CAP_FORECAST_MIN_YEAR or current_year > CAP_FORECAST_MAX_YEAR:
            current_year = CAP_FORECAST_MIN_YEAR
        return int(current_year)

    @staticmethod
    def salary_cap_for_season(settings: Dict[str, Any], season: int) -> float:
        return float(
            parse_amount_like(settings.get(f"salary_cap_{int(season)}"))
            or parse_amount_like(settings.get("salary_cap_2025"))
            or 154_647_000
        )

    def minimum_amount(
        self,
        free_agent: Dict[str, Any],
        settings: Dict[str, Any],
        season: int,
        contract_year: int,
        contract_type: str,
    ) -> float:
        normalized_type = str(contract_type or "").strip().upper()
        if normalized_type == "E10":
            return 0.0
        salary_cap = self.salary_cap_for_season(settings, season)
        if normalized_type == "TW":
            return float(scaled_minimum_salary(TWO_WAY_MINIMUM_BASE_SALARY, salary_cap))
        experience = normalize_experience_years(free_agent.get("experience_years"))
        base_experience = experience or 0
        if normalized_type == "MIN" and base_experience > 2:
            return float(minimum_salary_for_season(salary_cap, 2, contract_year))
        amount = minimum_salary_for_season(salary_cap, base_experience, contract_year)
        if amount:
            return float(amount)
        projected_experience = min(10, base_experience + max(0, int(contract_year or 1) - 1))
        return float(minimum_salary_for_season(salary_cap, projected_experience, 1))

    def maximum_amount(
        self,
        free_agent: Dict[str, Any],
        settings: Dict[str, Any],
        season: int,
        contract_type: str,
    ) -> float:
        if str(contract_type or "").strip().upper() == "E10":
            return float("inf")
        salary_cap = self.salary_cap_for_season(settings, season)
        return float(maximum_salary_for_experience(salary_cap, free_agent.get("experience_years")))

    @staticmethod
    def salary_text(value: float) -> str:
        amount = int(round(float(value or 0)))
        sign = "-" if amount < 0 else ""
        return f"{sign}{abs(amount):,}".replace(",", ".")

    def post_contract_rights_marker(self, offer_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        salary_by_season = offer_payload.get("salary_by_season")
        if not isinstance(salary_by_season, dict) or not salary_by_season:
            return None
        signed_seasons = sorted(
            season
            for season in (parse_int(str(raw_season)) for raw_season in salary_by_season.keys())
            if season is not None
        )
        if not signed_seasons:
            return None
        years = max(1, int(parse_int(offer_payload.get("years")) or len(signed_seasons)))
        final_season = max(signed_seasons)
        normalized_type = re.sub(
            r"[\s_-]+",
            "",
            str(offer_payload.get("contract_type") or "").strip().upper(),
        )
        if normalized_type in {"TW", "TWOWAY", "TWOWAYCONTRACT"}:
            rights_season = final_season + 1
            if rights_season < self.contract_min_year or rights_season > self.contract_max_year:
                return None
            return {"season": rights_season, "marker": "Two-way", "option": "QO"}
        marker = "NB" if years == 1 else "EB" if years == 2 else "FB"
        if years >= 2:
            options = offer_payload.get("option_by_season")
            options = options if isinstance(options, dict) else {}
            final_option = str(options.get(str(final_season)) or options.get(final_season) or "").strip().upper()
            if final_option in {"PO", "TO", "QO", "GAP"}:
                return None
        rights_season = final_season + 1
        if rights_season < self.contract_min_year or rights_season > self.contract_max_year:
            return None
        return {"season": rights_season, "marker": marker}

    def normalize_role(self, raw_role: Any) -> str:
        role = str(raw_role or "").strip()
        if not role:
            return ""
        for option in self.ROLE_OPTIONS:
            if role.casefold() == option.casefold():
                return option
        raise ValueError("invalid_offer_role")

    def normalize_offer(
        self,
        free_agent: Dict[str, Any],
        team_code: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("invalid_free_agent_offer")
        settings = self.repository.settings()
        start_season = self.offer_start_season(settings)
        years = max(1, min(5, int(parse_int(payload.get("years")) or 1)))
        contract_type = str(payload.get("contract_type") or "").strip()
        contract_type_upper = contract_type.upper()
        salaries = payload.get("salary_by_season")
        salaries = salaries if isinstance(salaries, dict) else {}
        options = payload.get("option_by_season")
        options = options if isinstance(options, dict) else {}

        normalized_options: Dict[str, str] = {}
        for raw_season, raw_option in options.items():
            option = str(raw_option or "").strip().upper()
            if not option:
                continue
            season = parse_int(str(raw_season))
            if season is None:
                raise ValueError("invalid_offer_option_season")
            if season == start_season:
                raise ValueError("first_year_option_not_allowed")
            if option in {"QO", "GAP"}:
                raise ValueError("qo_gap_options_are_automatic")
            if option not in {"TO", "PO"}:
                raise ValueError("invalid_offer_option")
            normalized_options[str(season)] = option

        raise_percent = float(parse_amount_like(payload.get("annual_raise_percent")) or 0.0)
        if raise_percent < -8 or raise_percent > 8:
            raise ValueError("invalid_annual_raise_percent")
        rights = self.bird_rights_code(free_agent)
        if raise_percent > 5 and not (self.is_renewal(free_agent, team_code) and rights in {"FB", "EB"}):
            raise ValueError("annual_raise_requires_full_or_early_bird")

        first_raw = salaries.get(str(start_season), salaries.get(start_season))
        first_amount = parse_amount_like(first_raw)
        first_minimum = self.minimum_amount(free_agent, settings, start_season, 1, contract_type_upper)
        first_maximum = self.maximum_amount(free_agent, settings, start_season, contract_type_upper)
        if contract_type_upper == "MIN":
            first_amount = first_minimum
        elif contract_type_upper == "MAX":
            first_amount = first_maximum
        elif contract_type_upper != "E10" and (first_amount is None or first_amount <= 0):
            raise ValueError("first_year_salary_required")
        elif first_amount is None:
            first_amount = 0.0
        if first_amount < first_minimum - 1:
            raise ValueError("first_year_salary_below_minimum")
        if math.isfinite(first_maximum) and first_amount > first_maximum + 1:
            raise ValueError("first_year_salary_above_maximum")

        role = self.normalize_role(payload.get("role"))
        if (contract_type_upper == "MIN" or first_amount <= 5_000_000) and not role:
            raise ValueError("offer_role_required")
        normalized_salaries: Dict[str, str] = {}
        for index in range(years):
            season = start_season + index
            if contract_type_upper == "MIN":
                amount = self.minimum_amount(free_agent, settings, season, index + 1, contract_type_upper)
            else:
                amount = float(first_amount) + (float(first_amount) * (raise_percent / 100.0) * index)
            normalized_salaries[str(season)] = self.salary_text(amount)

        normalized = dict(payload)
        normalized.update(
            years=years,
            annual_raise_percent=raise_percent,
            role=role,
            salary_by_season=normalized_salaries,
            option_by_season=normalized_options,
        )
        return normalized

    def player_payload_from_offer(
        self,
        free_agent: Dict[str, Any],
        offer_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        contract_type = str(offer_payload.get("contract_type") or "").strip()
        player_payload: Dict[str, Any] = {
            "name": str(free_agent.get("name") or free_agent.get("profile_name") or "").strip() or "New Player",
            "position": free_agent.get("position"),
            "rating": free_agent.get("rating"),
            "bird_rights": contract_type or free_agent.get("bird_rights"),
            "notes": str(offer_payload.get("notes") or "").strip() or free_agent.get("notes"),
            "signed_as_free_agent": True,
        }
        if parse_int(free_agent.get("profile_id")) is not None:
            player_payload["profile_id"] = free_agent.get("profile_id")
        for field in ("experience_years", "reference_image_url", "profile_notes"):
            if free_agent.get(field) not in (None, ""):
                player_payload[field] = free_agent.get(field)
        salaries = offer_payload.get("salary_by_season")
        if isinstance(salaries, dict):
            for raw_season, raw_value in salaries.items():
                season = parse_int(str(raw_season))
                value = str(raw_value or "").strip()
                if season in self.contract_seasons and value:
                    player_payload[f"salary_{season}_text"] = value
        options = offer_payload.get("option_by_season")
        if isinstance(options, dict):
            for raw_season, raw_value in options.items():
                season = parse_int(str(raw_season))
                value = str(raw_value or "").strip().upper()
                if season in self.contract_seasons and value:
                    player_payload[f"option_{season}"] = value
        marker = self.post_contract_rights_marker(offer_payload)
        if marker:
            season = int(marker["season"])
            salary_field = f"salary_{season}_text"
            player_payload.setdefault(salary_field, str(marker["marker"]))
            option = str(marker.get("option") or "").strip().upper()
            if option:
                player_payload.setdefault(f"option_{season}", option)
        return player_payload
