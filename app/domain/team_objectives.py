"""Pure team objective rules.

This module intentionally has no database, HTTP, service, or integration
dependencies. It defines the canonical season-objective codes and comparison
helpers used by persistence and workflow layers.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Dict, Iterable, Optional


CHAMPION = "champion"
FINALS = "finals"
CONFERENCE_FINALS = "conference_finals"
SECOND_ROUND = "second_round"
FIRST_ROUND = "first_round"
PLAY_IN = "play_in"
PLAY_IN_RACE = "play_in_race"
YOUTH_DEVELOPMENT = "youth_development"

# Goals a GM can agree to before the season. Champion is intentionally not
# included here; it is a result-only outcome for end-of-season resolution.
OBJECTIVE_CODES = frozenset(
    {
        FINALS,
        CONFERENCE_FINALS,
        SECOND_ROUND,
        FIRST_ROUND,
        PLAY_IN,
        PLAY_IN_RACE,
        YOUTH_DEVELOPMENT,
    }
)

OBJECTIVE_RESULT_CODES = frozenset({CHAMPION, *OBJECTIVE_CODES})

OBJECTIVE_LABELS: Dict[str, str] = {
    CHAMPION: "Campeón",
    FINALS: "Alcanzar las finales",
    CONFERENCE_FINALS: "Alcanzar las finales de conferencia",
    SECOND_ROUND: "Alcanzar la segunda ronda",
    FIRST_ROUND: "Alcanzar la primera ronda",
    PLAY_IN: "Jugar el play-in",
    PLAY_IN_RACE: "Luchar por el play-in",
    YOUTH_DEVELOPMENT: "Desarrollar jóvenes",
}

# Higher value means a harder / better competitive outcome.
OBJECTIVE_DIFFICULTY: Dict[str, int] = {
    YOUTH_DEVELOPMENT: 1,
    PLAY_IN_RACE: 2,
    PLAY_IN: 3,
    FIRST_ROUND: 4,
    SECOND_ROUND: 5,
    CONFERENCE_FINALS: 6,
    FINALS: 7,
    CHAMPION: 8,
}

COMPARISON_EXCEEDED = "exceeded"
COMPARISON_MET = "met"
COMPARISON_MISSED = "missed"
COMPARISON_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TeamObjective:
    code: str
    label: str
    difficulty: int

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "label": self.label, "difficulty": self.difficulty}


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("&", " y ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _objective_aliases() -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for code, label in OBJECTIVE_LABELS.items():
        aliases[_normalize_text(code)] = code
        aliases[_normalize_text(code.replace("_", " "))] = code
        aliases[_normalize_text(label)] = code

    aliases.update(
        {
            _normalize_text("finales"): FINALS,
            _normalize_text("finalista"): FINALS,
            _normalize_text("finals"): FINALS,
            _normalize_text("alcanzar finales"): FINALS,
            _normalize_text("llegar a finales"): FINALS,
            _normalize_text("finales nba"): FINALS,
            _normalize_text("campeon"): CHAMPION,
            _normalize_text("campeón"): CHAMPION,
            _normalize_text("campeones"): CHAMPION,
            _normalize_text("champion"): CHAMPION,
            _normalize_text("champions"): CHAMPION,
            _normalize_text("campeonato"): CHAMPION,
            _normalize_text("ganar anillo"): CHAMPION,
            _normalize_text("ganar el anillo"): CHAMPION,
            _normalize_text("anillo"): CHAMPION,
            _normalize_text("finales de conferencia"): CONFERENCE_FINALS,
            _normalize_text("final de conferencia"): CONFERENCE_FINALS,
            _normalize_text("conference finals"): CONFERENCE_FINALS,
            _normalize_text("cf"): CONFERENCE_FINALS,
            _normalize_text("segunda ronda"): SECOND_ROUND,
            _normalize_text("minimo segunda ronda"): SECOND_ROUND,
            _normalize_text("minimo 2 ronda"): SECOND_ROUND,
            _normalize_text("minimo 2a ronda"): SECOND_ROUND,
            _normalize_text("minimo 2ª ronda"): SECOND_ROUND,
            _normalize_text("second round"): SECOND_ROUND,
            _normalize_text("semifinales de conferencia"): SECOND_ROUND,
            _normalize_text("primera ronda"): FIRST_ROUND,
            _normalize_text("minimo primera ronda"): FIRST_ROUND,
            _normalize_text("minimo 1 ronda"): FIRST_ROUND,
            _normalize_text("minimo 1a ronda"): FIRST_ROUND,
            _normalize_text("minimo 1ª ronda"): FIRST_ROUND,
            _normalize_text("first round"): FIRST_ROUND,
            _normalize_text("playoffs"): FIRST_ROUND,
            _normalize_text("clasificar a playoffs"): FIRST_ROUND,
            _normalize_text("entrar play in"): PLAY_IN,
            _normalize_text("play in"): PLAY_IN,
            _normalize_text("play-in"): PLAY_IN,
            _normalize_text("jugar play in"): PLAY_IN,
            _normalize_text("luchar play in"): PLAY_IN_RACE,
            _normalize_text("luchar por play in"): PLAY_IN_RACE,
            _normalize_text("quedarse cerca del play in"): PLAY_IN_RACE,
            _normalize_text("cerca del play in"): PLAY_IN_RACE,
            _normalize_text("luchar por el play in quedarse cerca"): PLAY_IN_RACE,
            _normalize_text("play in race"): PLAY_IN_RACE,
            _normalize_text("desarrollar"): YOUTH_DEVELOPMENT,
            _normalize_text("desarrollar jovenes"): YOUTH_DEVELOPMENT,
            _normalize_text("desarrollo jovenes"): YOUTH_DEVELOPMENT,
            _normalize_text("ni siquiera estar cerca del play in"): YOUTH_DEVELOPMENT,
            _normalize_text("youth development"): YOUTH_DEVELOPMENT,
            _normalize_text("rebuild"): YOUTH_DEVELOPMENT,
            _normalize_text("reconstruccion"): YOUTH_DEVELOPMENT,
        }
    )
    return aliases


OBJECTIVE_ALIASES = _objective_aliases()


def normalize_objective_code(value: Any) -> Optional[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    return OBJECTIVE_ALIASES.get(normalized)


def require_objective_code(value: Any) -> str:
    code = normalize_objective_code(value)
    if code is None or code not in OBJECTIVE_CODES:
        raise ValueError("invalid_team_objective")
    return code


def require_objective_result_code(value: Any) -> str:
    code = normalize_objective_code(value)
    if code is None or code not in OBJECTIVE_RESULT_CODES:
        raise ValueError("invalid_team_objective")
    return code


def objective_label(value: Any) -> str:
    code = require_objective_result_code(value)
    return OBJECTIVE_LABELS[code]


def objective_difficulty(value: Any) -> int:
    code = require_objective_result_code(value)
    return OBJECTIVE_DIFFICULTY[code]


def objective_payload(value: Any) -> Dict[str, Any]:
    code = require_objective_code(value)
    return TeamObjective(
        code=code,
        label=OBJECTIVE_LABELS[code],
        difficulty=OBJECTIVE_DIFFICULTY[code],
    ).as_dict()


def objective_options(*, hardest_first: bool = True) -> list[Dict[str, Any]]:
    codes = sorted(
        OBJECTIVE_CODES,
        key=lambda code: OBJECTIVE_DIFFICULTY[code],
        reverse=hardest_first,
    )
    return [objective_payload(code) for code in codes]


def compare_objectives(agreed_objective: Any, achieved_result: Any) -> str:
    agreed = normalize_objective_code(agreed_objective)
    achieved = normalize_objective_code(achieved_result)
    if agreed is None or achieved is None:
        return COMPARISON_UNKNOWN
    agreed_score = OBJECTIVE_DIFFICULTY[agreed]
    achieved_score = OBJECTIVE_DIFFICULTY[achieved]
    if achieved_score > agreed_score:
        return COMPARISON_EXCEEDED
    if achieved_score == agreed_score:
        return COMPARISON_MET
    return COMPARISON_MISSED


def objective_met(agreed_objective: Any, achieved_result: Any) -> bool:
    return compare_objectives(agreed_objective, achieved_result) in {
        COMPARISON_MET,
        COMPARISON_EXCEEDED,
    }


def objective_exceeded(agreed_objective: Any, achieved_result: Any) -> bool:
    return compare_objectives(agreed_objective, achieved_result) == COMPARISON_EXCEEDED


def objective_missed(agreed_objective: Any, achieved_result: Any) -> bool:
    return compare_objectives(agreed_objective, achieved_result) == COMPARISON_MISSED


def normalize_objective_list(values: Iterable[Any]) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for value in values:
        code = normalize_objective_code(value)
        if code is None or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes
