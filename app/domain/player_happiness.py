"""Pure player happiness rules.

This module intentionally contains no database, HTTP, or service concerns.
It defines the deterministic happiness model used by services and repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from calendar import monthrange
from datetime import date
import math
from typing import Any, Dict, Iterable, Optional

from ._values import parse_float, parse_int
from .team_objectives import (
    CHAMPION,
    CONFERENCE_FINALS,
    FINALS,
    FIRST_ROUND,
    OBJECTIVE_DIFFICULTY,
    PLAY_IN,
    PLAY_IN_RACE,
    SECOND_ROUND,
    YOUTH_DEVELOPMENT,
    normalize_objective_code,
)


MIN_HAPPINESS = -10.0
MAX_HAPPINESS = 10.0
TEAM_JOIN_BASE_HAPPINESS = 7.0
TRADE_REQUEST_THRESHOLD = -7.0

EVENT_BASELINE_IMPORT = "baseline_import"
EVENT_MANUAL_ADJUSTMENT = "manual_adjustment"
EVENT_TEAM_JOIN = "team_join"
EVENT_MODIFIER = "modifier"
EVENT_ROSTER_IMPACT = "roster_impact"
EVENT_DRAFTED_RATING_THRESHOLD = "drafted_rating_threshold"
EVENT_TEAMMATE_ZERO_THRESHOLD = "teammate_zero_threshold"
EVENT_PROMISE_RESOLUTION = "promise_resolution"
EVENT_TEAM_OBJECTIVE_SET = "team_objective_set"
EVENT_TEAM_OBJECTIVE_JOIN_CONTEXT = "team_objective_join_context"
EVENT_TEAM_OBJECTIVE_RESOLUTION = "team_objective_resolution"
EVENT_TRADE_REQUEST_FOLLOWUP = "trade_request_followup"
EVENT_GM_CHANGE = "gm_change"

EVENT_TYPES = frozenset(
    {
        EVENT_BASELINE_IMPORT,
        EVENT_MANUAL_ADJUSTMENT,
        EVENT_TEAM_JOIN,
        EVENT_MODIFIER,
        EVENT_ROSTER_IMPACT,
        EVENT_DRAFTED_RATING_THRESHOLD,
        EVENT_TEAMMATE_ZERO_THRESHOLD,
        EVENT_PROMISE_RESOLUTION,
        EVENT_TEAM_OBJECTIVE_SET,
        EVENT_TEAM_OBJECTIVE_JOIN_CONTEXT,
        EVENT_TEAM_OBJECTIVE_RESOLUTION,
        EVENT_TRADE_REQUEST_FOLLOWUP,
        EVENT_GM_CHANGE,
    }
)

MILESTONE_SALARY_REDUCTION = "salary_reduction_possible"
MILESTONE_PRIORITIZE_DESTINATION = "prioritize_destination"
MILESTONE_PRIORITIZE_OTHER_DESTINATIONS = "prioritize_other_destinations"
MILESTONE_SHOW_DISCONTENT = "show_discontent"
MILESTONE_PRIVATE_TRADE_REQUEST = "private_trade_request"
MILESTONE_PUBLIC_TRADE_REQUEST = "public_trade_request"
MILESTONE_REFUSE_TO_PLAY_UNTIL_TRADE = "refuse_to_play_until_trade"

MILESTONE_LABELS = {
    MILESTONE_SALARY_REDUCTION: "Posible rebaja salarial",
    MILESTONE_PRIORITIZE_DESTINATION: "Priorizar este destino en agencia",
    MILESTONE_PRIORITIZE_OTHER_DESTINATIONS: "Priorizar otros destinos en agencia",
    MILESTONE_SHOW_DISCONTENT: "Mostrar descontento",
    MILESTONE_PRIVATE_TRADE_REQUEST: "Petición privada de traspaso",
    MILESTONE_PUBLIC_TRADE_REQUEST: "Petición pública de traspaso",
    MILESTONE_REFUSE_TO_PLAY_UNTIL_TRADE: "Negativa a jugar hasta traspaso",
}

MILESTONE_PUBLIC_CODES = frozenset({MILESTONE_PUBLIC_TRADE_REQUEST})

ROSTER_IMPACT_ADD = "add"
ROSTER_IMPACT_REMOVE = "remove"
DRAFTED_RATING_THRESHOLD = 85
DRAFTED_RATING_THRESHOLD_DELTA = 0.5
ZERO_HAPPINESS_THRESHOLD = 0.0
TEAMMATE_ZERO_INITIAL_DELTA = -1.0
TEAMMATE_ZERO_RELIEF_DELTA = 0.5
TEAMMATE_ZERO_RETURN_COHORT_DELTA = -0.5
PROMISE_STATUS_HAPPINESS_WEIGHTS = {
    "pending": 0.0,
    "fulfilled": 1.0,
    "broken": -1.0,
}
TRADE_REQUEST_FOLLOWUP_THREE_MONTHS = "three_months"
TRADE_REQUEST_FOLLOWUP_NINE_MONTHS = "nine_months"
TRADE_REQUEST_FOLLOWUP_PENALTIES = (
    (TRADE_REQUEST_FOLLOWUP_THREE_MONTHS, 3, -0.5),
    (TRADE_REQUEST_FOLLOWUP_NINE_MONTHS, 9, -1.0),
)

RECENCY_DECAY_WEIGHTS = {
    0: 1.0,
    1: 0.95,
    2: 0.85,
    3: 0.70,
    4: 0.60,
    5: 0.50,
    6: 0.40,
    7: 0.30,
    8: 0.25,
    9: 0.20,
}
HAPPINESS_ANCHOR_EVENT_TYPES = frozenset(
    {
        EVENT_BASELINE_IMPORT,
        EVENT_MANUAL_ADJUSTMENT,
        EVENT_TEAM_JOIN,
    }
)

RATING_BAND_60_74 = "60_74"
RATING_BAND_75_79 = "75_79"
RATING_BAND_80_84 = "80_84"
RATING_BAND_85_89 = "85_89"
RATING_BAND_90_94 = "90_94"
RATING_BAND_95_99 = "95_99"

TEAM_OBJECTIVE_HAPPINESS_DELTAS: Dict[str, Dict[str, tuple[float, float]]] = {
    YOUTH_DEVELOPMENT: {
        RATING_BAND_60_74: (0.0, 0.0),
        RATING_BAND_75_79: (0.0, -1.0),
        RATING_BAND_80_84: (-1.0, -1.0),
        RATING_BAND_85_89: (-1.0, -2.0),
        RATING_BAND_90_94: (-2.0, -2.0),
        RATING_BAND_95_99: (-2.0, -2.0),
    },
    PLAY_IN_RACE: {
        RATING_BAND_60_74: (0.0, 0.0),
        RATING_BAND_75_79: (0.0, -0.5),
        RATING_BAND_80_84: (-0.5, -1.0),
        RATING_BAND_85_89: (-1.0, -2.0),
        RATING_BAND_90_94: (-2.0, -2.0),
        RATING_BAND_95_99: (-2.0, -2.0),
    },
    PLAY_IN: {
        RATING_BAND_60_74: (0.0, 0.0),
        RATING_BAND_75_79: (0.0, 0.0),
        RATING_BAND_80_84: (0.0, -0.5),
        RATING_BAND_85_89: (-0.5, -1.0),
        RATING_BAND_90_94: (-1.0, -2.0),
        RATING_BAND_95_99: (-2.0, -2.0),
    },
    FIRST_ROUND: {
        RATING_BAND_60_74: (0.0, 0.0),
        RATING_BAND_75_79: (0.0, 0.0),
        RATING_BAND_80_84: (0.0, 0.0),
        RATING_BAND_85_89: (0.0, -0.5),
        RATING_BAND_90_94: (-0.5, -1.0),
        RATING_BAND_95_99: (-1.0, -2.0),
    },
    SECOND_ROUND: {
        RATING_BAND_60_74: (0.0, 0.0),
        RATING_BAND_75_79: (0.0, 0.0),
        RATING_BAND_80_84: (0.0, 0.0),
        RATING_BAND_85_89: (0.0, 0.0),
        RATING_BAND_90_94: (0.0, -0.5),
        RATING_BAND_95_99: (-0.5, -1.0),
    },
    CONFERENCE_FINALS: {
        RATING_BAND_60_74: (0.0, 0.0),
        RATING_BAND_75_79: (0.0, 0.0),
        RATING_BAND_80_84: (0.0, 0.0),
        RATING_BAND_85_89: (0.0, 0.0),
        RATING_BAND_90_94: (0.5, 0.0),
        RATING_BAND_95_99: (0.0, 0.0),
    },
    FINALS: {
        RATING_BAND_60_74: (0.0, 0.0),
        RATING_BAND_75_79: (0.0, 0.0),
        RATING_BAND_80_84: (0.0, 0.0),
        RATING_BAND_85_89: (0.0, 0.0),
        RATING_BAND_90_94: (0.5, 0.5),
        RATING_BAND_95_99: (0.5, 0.5),
    },
}


@dataclass(frozen=True)
class HappinessChange:
    previous_value: float
    proposed_delta: float
    applied_delta: float
    new_value: float
    eligible_for_trade_request: bool


@dataclass(frozen=True)
class HappinessMilestone:
    code: str
    label: str
    visibility: str
    admin_notification: bool
    discord_news_eligible: bool
    contract_context: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "visibility": self.visibility,
            "admin_notification": self.admin_notification,
            "discord_news_eligible": self.discord_news_eligible,
            "contract_context": self.contract_context,
        }


def clamp_happiness(value: Any) -> float:
    parsed = parse_float("" if value is None else str(value).strip())
    if parsed is None or not math.isfinite(parsed):
        raise ValueError("invalid_happiness")
    return max(MIN_HAPPINESS, min(MAX_HAPPINESS, float(parsed)))


def normalize_happiness(value: Any) -> int | float:
    clamped = clamp_happiness(value)
    return int(clamped) if float(clamped).is_integer() else clamped


def normalize_event_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in EVENT_TYPES:
        raise ValueError("invalid_happiness_event_type")
    return normalized


def recency_decay_weight(current_year: Any, event_year: Any) -> float:
    current = parse_int(current_year)
    event = parse_int(event_year)
    if current is None or event is None:
        return 1.0
    age = max(0, int(current) - int(event))
    if age >= 10:
        return 0.0
    return float(RECENCY_DECAY_WEIGHTS.get(age, 0.0))


def recency_recalculated_happiness(events: Iterable[Dict[str, Any]], current_year: Any) -> Dict[str, Any]:
    ordered = sorted(
        [event for event in events if isinstance(event, dict)],
        key=lambda item: (
            parse_int(item.get("id")) or 0,
            str(item.get("created_at") or ""),
        ),
    )
    if not ordered:
        return {
            "base_value": 0.0,
            "modifier_total": 0.0,
            "new_value": 0.0,
            "anchor_event_id": None,
            "weighted_events": [],
        }

    anchor_index = -1
    for index, event in enumerate(ordered):
        if str(event.get("event_type") or "").strip().lower() in HAPPINESS_ANCHOR_EVENT_TYPES:
            anchor_index = index

    if anchor_index >= 0:
        anchor = ordered[anchor_index]
        base_value = parse_float(str(anchor.get("new_value") or "0")) or 0.0
        relevant = ordered[anchor_index + 1 :]
        anchor_event_id = parse_int(anchor.get("id"))
    else:
        first = ordered[0]
        base_value = parse_float(str(first.get("previous_value") or "0")) or 0.0
        relevant = ordered
        anchor_event_id = None

    weighted_events: list[Dict[str, Any]] = []
    modifier_total = 0.0
    for event in relevant:
        event_type = str(event.get("event_type") or "").strip().lower()
        if event_type in HAPPINESS_ANCHOR_EVENT_TYPES:
            continue
        event_year = parse_int(event.get("season_year")) or parse_int(event.get("event_year"))
        weight = recency_decay_weight(current_year, event_year)
        applied_delta = parse_float(str(event.get("applied_delta") or "0")) or 0.0
        weighted_delta = applied_delta * weight
        modifier_total += weighted_delta
        weighted_events.append(
            {
                "event_id": parse_int(event.get("id")),
                "event_type": event_type,
                "season_year": event_year,
                "applied_delta": applied_delta,
                "recency_weight": weight,
                "weighted_delta": weighted_delta,
            }
        )

    new_value = clamp_happiness(base_value + modifier_total)
    return {
        "base_value": base_value,
        "modifier_total": modifier_total,
        "new_value": new_value,
        "anchor_event_id": anchor_event_id,
        "weighted_events": weighted_events,
    }


def trade_request_eligible(value: Any) -> bool:
    return clamp_happiness(value) <= TRADE_REQUEST_THRESHOLD


def trade_request_recovery_threshold(*, is_last_contract_year: bool = False) -> float:
    return 3.0 if is_last_contract_year else 2.0


def trade_request_still_unresolved(
    value: Any,
    *,
    is_last_contract_year: bool = False,
) -> bool:
    return clamp_happiness(value) < trade_request_recovery_threshold(
        is_last_contract_year=is_last_contract_year,
    )


def _milestone_payload(code: str, *, is_last_contract_year: bool) -> HappinessMilestone:
    public = code in MILESTONE_PUBLIC_CODES
    return HappinessMilestone(
        code=code,
        label=MILESTONE_LABELS[code],
        visibility="public" if public else "private",
        admin_notification=True,
        discord_news_eligible=public,
        contract_context="last_year" if is_last_contract_year else "multiyear",
    )


def classify_happiness_milestone(
    value: Any,
    *,
    is_last_contract_year: bool = False,
) -> Optional[HappinessMilestone]:
    happiness = clamp_happiness(value)
    if happiness >= 10:
        return _milestone_payload(MILESTONE_SALARY_REDUCTION, is_last_contract_year=is_last_contract_year)
    if 9 <= happiness < 10:
        return _milestone_payload(MILESTONE_PRIORITIZE_DESTINATION, is_last_contract_year=is_last_contract_year)
    if is_last_contract_year:
        if 3 <= happiness < 4:
            return _milestone_payload(MILESTONE_PRIORITIZE_OTHER_DESTINATIONS, is_last_contract_year=True)
        if 2 <= happiness < 3:
            return _milestone_payload(MILESTONE_PRIVATE_TRADE_REQUEST, is_last_contract_year=True)
        if 1 <= happiness < 2:
            return _milestone_payload(MILESTONE_PUBLIC_TRADE_REQUEST, is_last_contract_year=True)
        if happiness < 0:
            return _milestone_payload(MILESTONE_REFUSE_TO_PLAY_UNTIL_TRADE, is_last_contract_year=True)
        return None
    if 2 <= happiness < 3:
        return _milestone_payload(MILESTONE_SHOW_DISCONTENT, is_last_contract_year=False)
    if 1 <= happiness < 2:
        return _milestone_payload(MILESTONE_PRIVATE_TRADE_REQUEST, is_last_contract_year=False)
    if 0 <= happiness < 1:
        return _milestone_payload(MILESTONE_PUBLIC_TRADE_REQUEST, is_last_contract_year=False)
    if happiness < 0:
        return _milestone_payload(MILESTONE_REFUSE_TO_PLAY_UNTIL_TRADE, is_last_contract_year=False)
    return None


def triggered_happiness_milestone(
    previous_value: Any,
    new_value: Any,
    *,
    is_last_contract_year: bool = False,
) -> Optional[HappinessMilestone]:
    previous = classify_happiness_milestone(previous_value, is_last_contract_year=is_last_contract_year)
    current = classify_happiness_milestone(new_value, is_last_contract_year=is_last_contract_year)
    if current is None:
        return None
    if previous is not None and previous.code == current.code:
        return None
    return current


def calculate_change(
    previous_value: Any,
    *,
    new_value: Any = None,
    proposed_delta: Any = None,
    applied_delta: Any = None,
) -> HappinessChange:
    previous = clamp_happiness(previous_value)
    if new_value is None and applied_delta is None and proposed_delta is None:
        raise ValueError("happiness_change_required")
    proposed = parse_float(str(proposed_delta)) if proposed_delta is not None else None
    applied = parse_float(str(applied_delta)) if applied_delta is not None else proposed
    if new_value is not None:
        new = clamp_happiness(new_value)
        default_delta = new - previous
        if proposed is None:
            proposed = default_delta
        if applied is None:
            applied = default_delta
    else:
        if applied is None:
            raise ValueError("applied_delta_required")
        new = clamp_happiness(previous + float(applied))
    return HappinessChange(
        previous_value=previous,
        proposed_delta=float(proposed if proposed is not None else 0.0),
        applied_delta=float(applied if applied is not None else 0.0),
        new_value=new,
        eligible_for_trade_request=trade_request_eligible(new),
    )


def team_join_happiness(modifiers: Optional[Iterable[Any]] = None) -> float:
    value = TEAM_JOIN_BASE_HAPPINESS
    for modifier in modifiers or ():
        parsed = parse_float(str(modifier))
        if parsed is not None and math.isfinite(parsed):
            value += float(parsed)
    return clamp_happiness(value)


def is_free_agent_context(status_label: Any = None, active_contract: Any = None) -> bool:
    normalized_status = str(status_label or "").strip().lower()
    if normalized_status in {"free_agent", "agente libre"}:
        return True
    if active_contract is not None:
        return not bool(active_contract)
    return False


def roster_rating_impact_delta(rating: Any, direction: str) -> float:
    parsed = parse_float("" if rating is None else str(rating).strip())
    if parsed is None or not math.isfinite(parsed):
        return 0.0
    magnitude = 0.0
    if 85 <= parsed < 90:
        magnitude = 1.0
    elif parsed >= 90:
        magnitude = 2.0
    if not magnitude:
        return 0.0
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction in {ROSTER_IMPACT_REMOVE, "leave", "departure", "subtract", "negative"}:
        return -magnitude
    return magnitude


def age_on(dob: Any, on_date: Any) -> Optional[int]:
    raw_dob = str(dob or "").strip()
    raw_date = str(on_date or "").strip()
    if not raw_dob or not raw_date:
        return None
    try:
        birth = date.fromisoformat(raw_dob[:10])
        current = date.fromisoformat(raw_date[:10])
    except ValueError:
        return None
    return current.year - birth.year - ((current.month, current.day) < (birth.month, birth.day))


def roster_impact_player_delta(
    base_delta: Any,
    *,
    first_season_with_team: bool = False,
    date_of_birth: Any = None,
    on_date: Any = None,
) -> float:
    parsed = parse_float("" if base_delta is None else str(base_delta).strip())
    if parsed is None or not math.isfinite(parsed) or parsed == 0:
        return 0.0
    if parsed < 0 and first_season_with_team:
        player_age = age_on(date_of_birth, on_date)
        if player_age is not None and player_age < 26:
            return 0.0
    if first_season_with_team:
        return parsed / 2.0
    return parsed


def is_first_season_with_team(joined_season_year: Any, current_year: Any) -> bool:
    joined = parse_int(joined_season_year)
    current = parse_int(current_year)
    return joined is not None and current is not None and joined == current


def team_objective_rating_band(rating: Any) -> Optional[str]:
    parsed = parse_float("" if rating is None else str(rating).strip())
    if parsed is None or not math.isfinite(parsed):
        return None
    if 60 <= parsed < 75:
        return RATING_BAND_60_74
    if 75 <= parsed < 80:
        return RATING_BAND_75_79
    if 80 <= parsed < 85:
        return RATING_BAND_80_84
    if 85 <= parsed < 90:
        return RATING_BAND_85_89
    if 90 <= parsed < 95:
        return RATING_BAND_90_94
    if 95 <= parsed <= 99:
        return RATING_BAND_95_99
    return None


def team_objective_happiness_delta(
    objective: Any,
    rating: Any,
    *,
    age: Any = None,
    date_of_birth: Any = None,
    on_date: Any = None,
) -> float:
    objective_code = normalize_objective_code(objective)
    band = team_objective_rating_band(rating)
    if objective_code is None or band is None:
        return 0.0
    parsed_age = parse_int(age)
    if parsed_age is None and date_of_birth is not None and on_date is not None:
        parsed_age = age_on(date_of_birth, on_date)
    if parsed_age is None:
        return 0.0
    young_delta, veteran_delta = TEAM_OBJECTIVE_HAPPINESS_DELTAS[objective_code][band]
    return float(young_delta if int(parsed_age) <= 25 else veteran_delta)


def team_objective_happiness_delta_change(
    previous_objective: Any,
    new_objective: Any,
    rating: Any,
    *,
    age: Any = None,
    date_of_birth: Any = None,
    on_date: Any = None,
) -> float:
    previous_delta = team_objective_happiness_delta(
        previous_objective,
        rating,
        age=age,
        date_of_birth=date_of_birth,
        on_date=on_date,
    )
    new_delta = team_objective_happiness_delta(
        new_objective,
        rating,
        age=age,
        date_of_birth=date_of_birth,
        on_date=on_date,
    )
    return float(new_delta - previous_delta)


def team_objective_resolution_delta(
    agreed_objective: Any,
    achieved_objective: Any,
) -> float:
    agreed_code = normalize_objective_code(agreed_objective)
    achieved_code = normalize_objective_code(achieved_objective)
    if agreed_code is None or achieved_code is None:
        return 0.0
    if achieved_code == CHAMPION:
        return 3.0
    if achieved_code == FINALS:
        return 2.0
    difficulty_delta = OBJECTIVE_DIFFICULTY[achieved_code] - OBJECTIVE_DIFFICULTY[agreed_code]
    if difficulty_delta >= 2:
        return 2.0
    if difficulty_delta == 1:
        return 1.5
    if difficulty_delta == 0:
        return 1.0
    if difficulty_delta == -1:
        return -1.0
    return -2.0


def _parse_iso_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if len(raw) < 10:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def trade_request_followup_penalties(
    requested_at: Any,
    as_of_date: Any,
    *,
    current_happiness: Any,
    is_last_contract_year: bool = False,
    applied_stages: Optional[Iterable[Any]] = None,
) -> list[Dict[str, Any]]:
    request_date = _parse_iso_date(requested_at)
    current_date = _parse_iso_date(as_of_date)
    if request_date is None or current_date is None:
        return []
    if not trade_request_still_unresolved(
        current_happiness,
        is_last_contract_year=is_last_contract_year,
    ):
        return []
    applied = {str(stage or "").strip() for stage in (applied_stages or [])}
    penalties: list[Dict[str, Any]] = []
    for stage, months, delta in TRADE_REQUEST_FOLLOWUP_PENALTIES:
        due_date = _add_months(request_date, months)
        if current_date < due_date or stage in applied:
            continue
        penalties.append(
            {
                "stage": stage,
                "months": months,
                "due_date": due_date.isoformat(),
                "applied_delta": delta,
            }
        )
    return penalties


def drafted_rating_threshold_crossed(previous_rating: Any, new_rating: Any) -> bool:
    previous = parse_float("" if previous_rating is None else str(previous_rating).strip())
    new = parse_float("" if new_rating is None else str(new_rating).strip())
    if previous is None or new is None or not math.isfinite(previous) or not math.isfinite(new):
        return False
    return previous < DRAFTED_RATING_THRESHOLD <= new


def is_rookie_scale_contract_type(value: Any) -> bool:
    normalized = str(value or "").strip().upper().replace(" ", "")
    return normalized in {"R", "R(2)"}


def zero_happiness_transition(previous_value: Any, new_value: Any, *, has_prior_zero_cohort: bool = False) -> Optional[str]:
    previous = parse_float("" if previous_value is None else str(previous_value).strip())
    new = parse_float("" if new_value is None else str(new_value).strip())
    if previous is None or new is None or not math.isfinite(previous) or not math.isfinite(new):
        return None
    if previous > ZERO_HAPPINESS_THRESHOLD and new <= ZERO_HAPPINESS_THRESHOLD:
        return "return_to_zero" if has_prior_zero_cohort else "initial_zero"
    if previous <= ZERO_HAPPINESS_THRESHOLD and new > ZERO_HAPPINESS_THRESHOLD:
        return "recovered_above_zero"
    return None


def promise_resolution_delta(previous_status: Any, new_status: Any) -> float:
    previous = str(previous_status or "pending").strip().lower()
    new = str(new_status or "pending").strip().lower()
    return PROMISE_STATUS_HAPPINESS_WEIGHTS.get(new, 0.0) - PROMISE_STATUS_HAPPINESS_WEIGHTS.get(previous, 0.0)
