"""Preview/apply orchestration for NBA2K player rating imports."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_int


def normalize_player_rating_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class PlayerRatingImportService:
    def __init__(self, repository: Any, *, now: Callable[[], str]) -> None:
        self.repository = repository
        self._now = now

    @staticmethod
    def _ratings_from_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid_json") from exc
        if not isinstance(payload, dict):
            raise ValueError("invalid_rating_import_payload")
        raw_players = payload.get("players")
        if isinstance(raw_players, dict):
            player_items = list(raw_players.values())
        elif isinstance(raw_players, list):
            player_items = raw_players
        elif isinstance(payload.get("ratings"), list):
            player_items = payload.get("ratings") or []
        else:
            raise ValueError("rating_import_players_required")

        by_key: Dict[str, Dict[str, Any]] = {}
        duplicates: List[str] = []
        invalid_count = 0
        for raw in player_items:
            if not isinstance(raw, dict):
                invalid_count += 1
                continue
            name = str(raw.get("name") or raw.get("player_name") or raw.get("player") or "").strip()
            rating = parse_int(raw.get("overall") if "overall" in raw else raw.get("rating"))
            if not name or rating is None or rating < 0 or rating > 100:
                invalid_count += 1
                continue
            key = normalize_player_rating_name(name)
            if not key:
                invalid_count += 1
                continue
            if key in by_key:
                duplicates.append(name)
                continue
            by_key[key] = {
                "source_name": name,
                "name_key": key,
                "overall": int(rating),
                "source_team": str(raw.get("team") or "").strip() or None,
                "positions": [str(item).strip() for item in raw.get("positions") or [] if str(item).strip()]
                if isinstance(raw.get("positions"), list)
                else [],
            }
        return {"ratings": by_key, "duplicates": duplicates, "invalid_count": invalid_count}

    def preview(self, payload: Any) -> Dict[str, Any]:
        parsed = self._ratings_from_payload(payload)
        ratings: Dict[str, Dict[str, Any]] = parsed["ratings"]
        with self.repository.connect() as conn:
            targets = self.repository.rating_targets(conn)

        matched_records: List[Dict[str, Any]] = []
        unmatched_targets: List[Dict[str, Any]] = []
        matched_rating_keys: set[str] = set()
        for target in targets:
            name_key = normalize_player_rating_name(target.get("name"))
            source = ratings.get(name_key)
            if not source:
                unmatched_targets.append(
                    {
                        "target_type": target.get("target_type"),
                        "target_id": target.get("target_id"),
                        "profile_id": target.get("profile_id"),
                        "player_name": target.get("name"),
                        "current_rating": str(target.get("rating") or "").strip(),
                        "team_code": target.get("team_code"),
                        "team_name": target.get("team_name"),
                    }
                )
                continue
            matched_rating_keys.add(name_key)
            current_rating = str(target.get("rating") or "").strip()
            new_rating = str(int(source["overall"]))
            matched_records.append(
                {
                    "target_type": target.get("target_type"),
                    "target_id": int(target["target_id"]),
                    "profile_id": target.get("profile_id"),
                    "player_name": str(target.get("name") or "").strip(),
                    "source_name": source["source_name"],
                    "source_team": source.get("source_team"),
                    "positions": source.get("positions") or [],
                    "current_rating": current_rating,
                    "new_rating": int(source["overall"]),
                    "changed": current_rating != new_rating,
                    "team_code": target.get("team_code"),
                    "team_name": target.get("team_name"),
                }
            )

        unused_source_players = [
            {
                "source_name": value["source_name"],
                "overall": value["overall"],
                "source_team": value.get("source_team"),
            }
            for key, value in sorted(ratings.items(), key=lambda item: item[1]["source_name"].casefold())
            if key not in matched_rating_keys
        ]
        changed_count = sum(1 for record in matched_records if record.get("changed"))
        errors = []
        if parsed["duplicates"]:
            errors.append(
                {
                    "line": None,
                    "message": f"Hay nombres duplicados en el JSON de ratings: {', '.join(parsed['duplicates'][:10])}.",
                }
            )
        return {
            "ok": not errors,
            "errors": errors,
            "records": matched_records,
            "summary": {
                "source_player_count": len(ratings),
                "target_count": len(targets),
                "matched_count": len(matched_records),
                "changed_count": changed_count,
                "unchanged_count": len(matched_records) - changed_count,
                "unmatched_target_count": len(unmatched_targets),
                "unused_source_count": len(unused_source_players),
                "invalid_source_count": int(parsed.get("invalid_count") or 0),
            },
            "unmatched_targets": unmatched_targets,
            "unused_source_players": unused_source_players,
        }

    def apply(self, records_payload: Any) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        cleaned = []
        seen: set[tuple[str, int]] = set()
        for raw in records_payload:
            if not isinstance(raw, dict):
                raise ValueError("invalid_records")
            target_type = str(raw.get("target_type") or "").strip().lower()
            if target_type not in {"player", "free_agent"}:
                raise ValueError("invalid_records")
            target_id = parse_int(raw.get("target_id"))
            new_rating = parse_int(raw.get("new_rating"))
            player_name = str(raw.get("player_name") or "").strip()
            if target_id is None or new_rating is None or new_rating < 0 or new_rating > 100 or not player_name:
                raise ValueError("invalid_records")
            key = (target_type, int(target_id))
            if key in seen:
                raise ValueError("duplicate_rating_import_target")
            seen.add(key)
            cleaned.append(
                {
                    "target_type": target_type,
                    "target_id": int(target_id),
                    "new_rating": int(new_rating),
                    "player_name": player_name,
                }
            )
        result = self.repository.apply(cleaned, self._now())
        result["command_id"] = f"player-ratings:import:{result.get('record_count') or 0}"
        result["validation_result"] = "valid"
        result["entity_versions"] = {
            "record_count": int(result.get("record_count") or 0),
            "changed_count": int(result.get("changed_count") or 0),
            "unchanged_count": int(result.get("unchanged_count") or 0),
        }
        return result
