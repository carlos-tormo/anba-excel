"""Application workflow for GM minimum-target submissions and scoring."""

from __future__ import annotations

from datetime import date, datetime
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

try:
    from ..auth.policies import normalize_team_code
    from ..db.repositories.gm_minimum_targets import GMMinimumTargetRepository
    from ..domain._values import parse_bool, parse_float, parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from db.repositories.gm_minimum_targets import GMMinimumTargetRepository
    from domain._values import parse_bool, parse_float, parse_int


class GMMinimumTargetService:
    VALID_ROLES = (
        "Titular",
        "Sexto hombre",
        "Minutos de rotación (10-20)",
        "Minutos de rotación (0-9)",
        "Fuera de la rotación",
    )

    def __init__(self, repository: GMMinimumTargetRepository, *, now: Callable[[], str]) -> None:
        self.repository = repository
        self._now = now

    @staticmethod
    def _team_codes(value: Any) -> List[str]:
        return [
            code for raw in str(value or "").split(",")
            if (code := normalize_team_code(raw))
        ]

    @staticmethod
    def _target_payload(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "rank": parse_int(row.get("rank")),
                "free_agent_id": parse_int(row.get("free_agent_id")),
                "profile_id": parse_int(row.get("profile_id")),
                "player_name": str(row.get("player_name") or row.get("free_agent_name") or "").strip(),
                "position": str(row.get("position") or "").strip(),
                "rating": str(row.get("rating") or "").strip(),
                "free_agent_type": str(row.get("free_agent_type") or "").strip(),
                "rights_team_code": normalize_team_code(row.get("rights_team_code")),
                "role": str(row.get("role") or "").strip(),
            }
            for row in rows
        ]

    def get(self, user_id: Any, team_code: Any = None) -> Dict[str, Any]:
        parsed_user_id = parse_int(user_id)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        rows = self.repository.get_submission_rows(parsed_user_id)
        user = rows["user"]
        status = rows["status"] or {}
        normalized_team = normalize_team_code(status.get("team_code") or team_code)
        team_codes = self._team_codes(user.get("team_codes"))
        if not normalized_team and len(team_codes) == 1:
            normalized_team = team_codes[0]
        return {
            "user_id": parse_int(user.get("id") or status.get("user_id")),
            "user_name": str(user.get("display_name") or "").strip(),
            "email": str(user.get("email") or "").strip(),
            "team_code": normalized_team,
            "answered": bool(parse_int(status.get("answered"))),
            "omitted": bool(parse_int(status.get("omitted"))),
            "updated_at": str(status.get("updated_at") or "").strip(),
            "targets": self._target_payload(rows["targets"]),
        }

    def set(self, user_id: Any, team_code: Any, targets: Any) -> Dict[str, Any]:
        parsed_user_id = parse_int(user_id)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        if targets is None:
            targets = []
        if not isinstance(targets, list):
            raise ValueError("invalid_targets")
        if len(targets) > 10:
            raise ValueError("too_many_targets")
        cleaned: List[Dict[str, Any]] = []
        seen_agents, seen_ranks = set(), set()
        for index, raw in enumerate(targets, start=1):
            if not isinstance(raw, dict):
                raise ValueError("invalid_target")
            rank = parse_int(raw.get("rank"))
            if rank is None:
                rank = index
            free_agent_id = parse_int(raw.get("free_agent_id"))
            role = str(raw.get("role") or "").strip()
            if role:
                role = next(
                    (option for option in self.VALID_ROLES if option.casefold() == role.casefold()),
                    "",
                )
                if not role:
                    raise ValueError("invalid_target_role")
            elif free_agent_id is not None and free_agent_id > 0:
                raise ValueError("target_role_required")
            if rank < 1 or rank > 10:
                raise ValueError("invalid_rank")
            if free_agent_id is None or free_agent_id <= 0:
                continue
            if rank in seen_ranks:
                raise ValueError("duplicate_rank")
            if free_agent_id in seen_agents:
                raise ValueError("duplicate_player")
            seen_ranks.add(rank)
            seen_agents.add(free_agent_id)
            cleaned.append({"rank": rank, "free_agent_id": free_agent_id, "role": role})
        normalized_team = normalize_team_code(team_code)
        self.repository.replace_submission(parsed_user_id, normalized_team, cleaned, self._now())
        return self.get(parsed_user_id, normalized_team)

    def omit(self, user_id: Any, team_code: Any = None) -> Dict[str, Any]:
        parsed_user_id = parse_int(user_id)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        normalized_team = normalize_team_code(team_code)
        self.repository.omit_submission(parsed_user_id, normalized_team, self._now())
        return self.get(parsed_user_id, normalized_team)

    def remove(self, user_id: Any, rank: Any) -> Dict[str, Any]:
        parsed_user_id, parsed_rank = parse_int(user_id), parse_int(rank)
        if parsed_user_id is None or parsed_user_id <= 0:
            raise ValueError("user_required")
        if parsed_rank is None or parsed_rank < 1 or parsed_rank > 10:
            raise ValueError("invalid_rank")
        removed = self.repository.remove_target(parsed_user_id, parsed_rank, self._now())
        return {"removed": removed, "user_id": parsed_user_id, "rank": parsed_rank}

    def list_handicaps(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for row in self.repository.list_handicap_rows():
            code, handicap = normalize_team_code(row.get("team_code")), parse_int(row.get("handicap"))
            if code and handicap is not None and -9 <= handicap <= 0:
                result[code] = handicap
        return result

    def set_handicap(self, team_code: Any, handicap: Any) -> Dict[str, Any]:
        code, value = normalize_team_code(team_code), parse_int(handicap)
        if not code:
            raise ValueError("team_required")
        value = value if value is not None else 0
        if value < -9 or value > 0:
            raise ValueError("invalid_handicap")
        self.repository.set_handicap(code, value, self._now())
        return {"team_code": code, "handicap": value}

    def list_admin(self) -> List[Dict[str, Any]]:
        rows = self.repository.list_admin_submission_rows()
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for target in rows["targets"]:
            grouped.setdefault(int(target["user_id"]), []).append(target)
        result = []
        for user in rows["users"]:
            user_id = int(user["id"])
            team_codes = self._team_codes(user.get("team_codes"))
            result.append({
                "user_id": user_id,
                "user_name": str(user.get("display_name") or user.get("email") or "").strip(),
                "email": str(user.get("email") or "").strip(),
                "role": "co_admin" if parse_bool(user.get("is_co_admin")) else ("gm" if team_codes else "guest"),
                "team_codes": team_codes,
                "answered": bool(parse_int(user.get("answered"))),
                "omitted": bool(parse_int(user.get("omitted"))),
                "updated_at": str(user.get("updated_at") or "").strip(),
                "targets": self._target_payload(grouped.get(user_id, [])),
            })
        return result

    @staticmethod
    def _age(value: Any) -> int:
        text = str(value or "").strip()
        parsed: Optional[date] = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            return 20
        today = date.today()
        age = today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day))
        return age if 0 <= age <= 80 else 20

    @staticmethod
    def _appeal_key(age: int) -> str:
        if age < 23: return "under_23_single"
        if age <= 26: return "age_23_26_single"
        if age <= 33: return "age_27_33_single"
        return "over_34_single"

    @staticmethod
    def _normalized_text(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
        return re.sub(r"[^a-z0-9]+", " ", text).strip()

    @classmethod
    def _role_points(cls, role: Any) -> int:
        return {
            "titular": 20, "sexto hombre": 10,
            "minutos de rotacion 10 20": 4, "rotacion 10 20 minutos": 4,
            "rotacion 10 20": 4, "minutos de rotacion 0 9": 2,
            "minutos de rotacion 0 10": 2, "rol limitado 0 10 minutos": 2,
            "rol limitado 0 9": 2, "rotacion 0 9": 2,
            "rotacion 0 10": 2, "fuera de la rotacion": 0,
        }.get(cls._normalized_text(role), 0)

    @staticmethod
    def _birds_bonus(age: int, team_code: Any, rights_team_code: Any) -> int:
        if not team_code or normalize_team_code(team_code) != normalize_team_code(rights_team_code): return 0
        if age < 23: return 10
        if age <= 28: return 6
        if age <= 33: return 3
        return 1

    def score_order(self) -> List[Dict[str, Any]]:
        rows = self.repository.scoring_rows()
        teams = {normalize_team_code(row["code"]): str(row.get("name") or row["code"]).strip() for row in rows["teams"]}
        users = {}
        for row in rows["users"]:
            codes = self._team_codes(row.get("team_codes"))
            users[int(row["id"])] = {**row, "team_code": codes[0] if codes else ""}
        appeals = {normalize_team_code(row.get("team_code")): row for row in rows["appeals"]}
        handicaps = {normalize_team_code(row.get("team_code")): parse_int(row.get("handicap")) or 0 for row in rows["handicaps"]}
        effective_ranks: Dict[int, int] = {}
        scored = []
        for row in rows["targets"]:
            user_id = int(row["user_id"])
            user = users.get(user_id)
            if not user: continue
            team_code = normalize_team_code(user.get("team_code"))
            effective_rank = effective_ranks.get(user_id, 0) + 1
            effective_ranks[user_id] = effective_rank
            age = self._age(row.get("date_of_birth"))
            appeal_key = self._appeal_key(age)
            appeal_rank = parse_float((appeals.get(team_code) or {}).get(appeal_key))
            priority_points = max(0, 11 - effective_rank) if effective_rank <= 10 else 0
            appeal_points = max(0, 31 - int(appeal_rank)) if appeal_rank and appeal_rank > 0 else 0
            role_points = self._role_points(row.get("role"))
            rights_code = normalize_team_code(row.get("rights_team_code"))
            birds_bonus = self._birds_bonus(age, team_code, rights_code)
            handicap = handicaps.get(team_code, 0)
            scored.append({
                "total": priority_points + appeal_points + role_points + birds_bonus + handicap,
                "priority_points": priority_points, "appeal_points": appeal_points,
                "role_points": role_points, "birds_bonus": birds_bonus, "handicap": handicap,
                "appeal_rank": int(appeal_rank) if appeal_rank and appeal_rank > 0 else None,
                "appeal_key": appeal_key, "age": age, "target_rank": effective_rank,
                "original_target_rank": parse_int(row.get("rank")) or 0,
                "team_code": team_code, "team_name": teams.get(team_code, team_code),
                "user_id": user_id,
                "user_name": str(user.get("display_name") or user.get("email") or "").strip(),
                "player_name": str(row.get("player_name") or "").strip(),
                "free_agent_id": parse_int(row.get("free_agent_id")),
                "profile_id": parse_int(row.get("profile_id")),
                "position": str(row.get("position") or "").strip(),
                "rating": str(row.get("rating") or "").strip(),
                "rights_team_code": rights_code, "role": str(row.get("role") or "").strip(),
            })
        scored.sort(key=lambda item: (-item["total"], -item["priority_points"], -item["appeal_points"], -item["role_points"], -item["birds_bonus"], item["player_name"], item["team_code"]))
        return scored
