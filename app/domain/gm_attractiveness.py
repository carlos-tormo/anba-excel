"""Pure rules for GM attractiveness voting and ranking."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


RANKING_BAND_TOP_5 = "top5"
RANKING_BAND_BOTTOM_5 = "bottom5"
RANKING_BAND_NEUTRAL = "neutral"
RANKING_BANDS = frozenset({RANKING_BAND_TOP_5, RANKING_BAND_BOTTOM_5, RANKING_BAND_NEUTRAL})

GM_CHANGE_ENTER = "enter"
GM_CHANGE_LEAVE = "leave"

GM_CHANGE_HAPPINESS_DELTAS = {
    (GM_CHANGE_ENTER, RANKING_BAND_TOP_5): 1.0,
    (GM_CHANGE_ENTER, RANKING_BAND_BOTTOM_5): -1.0,
    (GM_CHANGE_LEAVE, RANKING_BAND_TOP_5): -0.5,
    (GM_CHANGE_LEAVE, RANKING_BAND_BOTTOM_5): 0.5,
}


@dataclass(frozen=True)
class StandardizedRankingEntry:
    target_id: int
    target_name: str
    raw_average: Optional[float]
    standardized_score: float
    vote_count: int
    rank_position: int
    band: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "raw_average": self.raw_average,
            "standardized_score": self.standardized_score,
            "vote_count": self.vote_count,
            "rank_position": self.rank_position,
            "band": self.band,
        }


def normalize_ranking_band(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in RANKING_BANDS else RANKING_BAND_NEUTRAL


def gm_change_happiness_delta(*, direction: Any, band: Any) -> float:
    normalized_direction = str(direction or "").strip().lower()
    normalized_band = normalize_ranking_band(band)
    return float(GM_CHANGE_HAPPINESS_DELTAS.get((normalized_direction, normalized_band), 0.0))


def _standard_deviation(values: List[float], mean: float) -> float:
    if len(values) <= 1:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _band_for_position(position: int, total: int) -> str:
    if position <= 5:
        return RANKING_BAND_TOP_5
    if total > 5 and position > max(total - 5, 5):
        return RANKING_BAND_BOTTOM_5
    return RANKING_BAND_NEUTRAL


def standardized_ranking(score_rows: Iterable[Dict[str, Any]]) -> List[StandardizedRankingEntry]:
    """Return target rankings after normalizing each evaluator's scoring scale.

    Expected row keys:
    - voter_user_id
    - target_id
    - target_name
    - score
    """

    rows: List[Dict[str, Any]] = []
    for raw in score_rows:
        try:
            voter_id = int(raw.get("voter_user_id"))
            target_id = int(raw.get("target_id"))
            score = float(raw.get("score"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue
        rows.append(
            {
                **raw,
                "voter_user_id": voter_id,
                "target_id": target_id,
                "target_name": str(raw.get("target_name") or target_id).strip() or str(target_id),
                "score": score,
            }
        )

    by_voter: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_voter[int(row["voter_user_id"])].append(row)

    standardized_by_target: Dict[int, List[float]] = defaultdict(list)
    raw_by_target: Dict[int, List[float]] = defaultdict(list)
    names_by_target: Dict[int, str] = {}

    for voter_rows in by_voter.values():
        values = [float(row["score"]) for row in voter_rows]
        mean = sum(values) / len(values) if values else 0.0
        deviation = _standard_deviation(values, mean)
        for row in voter_rows:
            target_id = int(row["target_id"])
            z_score = 0.0 if deviation <= 0 else (float(row["score"]) - mean) / deviation
            standardized_by_target[target_id].append(z_score)
            raw_by_target[target_id].append(float(row["score"]))
            names_by_target[target_id] = str(row.get("target_name") or target_id)

    aggregate_rows: List[Dict[str, Any]] = []
    for target_id, values in standardized_by_target.items():
        raw_values = raw_by_target.get(target_id) or []
        aggregate_rows.append(
            {
                "target_id": int(target_id),
                "target_name": names_by_target.get(target_id, str(target_id)),
                "raw_average": (sum(raw_values) / len(raw_values)) if raw_values else None,
                "standardized_score": sum(values) / len(values) if values else 0.0,
                "vote_count": len(values),
            }
        )

    aggregate_rows.sort(
        key=lambda item: (
            -float(item["standardized_score"]),
            -(float(item["raw_average"]) if item["raw_average"] is not None else -999999.0),
            str(item["target_name"]).lower(),
            int(item["target_id"]),
        )
    )
    total = len(aggregate_rows)
    return [
        StandardizedRankingEntry(
            target_id=int(item["target_id"]),
            target_name=str(item["target_name"]),
            raw_average=round(float(item["raw_average"]), 4) if item["raw_average"] is not None else None,
            standardized_score=round(float(item["standardized_score"]), 6),
            vote_count=int(item["vote_count"]),
            rank_position=index,
            band=_band_for_position(index, total),
        )
        for index, item in enumerate(aggregate_rows, start=1)
    ]
