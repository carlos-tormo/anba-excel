"""Player happiness import preview/apply orchestration."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain._values import parse_float, parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_float, parse_int


def normalize_happiness_import_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_happiness_value(value: Any) -> int | float:
    parsed = parse_float("" if value is None else str(value).strip())
    if parsed is None or not math.isfinite(parsed) or parsed < -10 or parsed > 10:
        raise ValueError("invalid_happiness")
    return int(parsed) if float(parsed).is_integer() else parsed


class PlayerHappinessService:
    def __init__(self, repository: Any, *, now: Callable[[], str]) -> None:
        self.repository = repository
        self._now = now

    @staticmethod
    def _rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid_json") from exc
        if isinstance(payload, dict):
            rows = payload.get("players") or payload.get("rows")
            if rows is None and ("player_name" in payload or "name" in payload or "profile_id" in payload):
                rows = [payload]
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = None
        if not isinstance(rows, list):
            raise ValueError("happiness_import_players_required")
        return [row for row in rows if isinstance(row, dict)]

    def preview(self, payload: Any) -> Dict[str, Any]:
        rows = self._rows_from_payload(payload)
        with self.repository.connect() as conn:
            profiles = self.repository.profiles(conn)

        by_profile_id = {int(profile["profile_id"]): profile for profile in profiles}
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            key = normalize_happiness_import_name(profile.get("name"))
            if key:
                by_name.setdefault(key, []).append(profile)

        records: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        ambiguous: List[Dict[str, Any]] = []
        seen_profiles: Dict[int, int] = {}
        for index, row in enumerate(rows):
            line = index + 1
            raw_name = str(row.get("player_name") or row.get("name") or row.get("player") or "").strip()
            raw_profile_id = parse_int(row.get("profile_id") or row.get("id"))
            try:
                happiness = normalize_happiness_value(row.get("happiness"))
            except ValueError:
                errors.append({"line": line, "message": f"Felicidad inválida para {raw_name or raw_profile_id or 'fila'}."})
                continue
            profile: Optional[Dict[str, Any]] = None
            match_method = "name"
            if raw_profile_id is not None:
                profile = by_profile_id.get(int(raw_profile_id))
                match_method = "profile_id"
                if not profile:
                    errors.append({"line": line, "message": f"No existe profile_id {raw_profile_id}."})
                    continue
            else:
                key = normalize_happiness_import_name(raw_name)
                matches = by_name.get(key, []) if key else []
                if not matches:
                    unmatched.append({"line": line, "player_name": raw_name, "happiness": happiness})
                    continue
                if len(matches) > 1:
                    ambiguous.append(
                        {
                            "line": line,
                            "player_name": raw_name,
                            "happiness": happiness,
                            "matches": [
                                {
                                    "profile_id": match.get("profile_id"),
                                    "player_name": match.get("name"),
                                    "current_happiness": match.get("happiness"),
                                    "status_label": match.get("status_label"),
                                    "team_code": match.get("team_code"),
                                }
                                for match in matches
                            ],
                        }
                    )
                    continue
                profile = matches[0]

            profile_id = int(profile["profile_id"])
            if profile_id in seen_profiles:
                errors.append(
                    {
                        "line": line,
                        "message": f"Jugador duplicado: {profile.get('name')} ya apareció en la línea {seen_profiles[profile_id]}.",
                    }
                )
                continue
            seen_profiles[profile_id] = line
            current = float(profile.get("happiness") or 0)
            records.append(
                {
                    "line": line,
                    "profile_id": profile_id,
                    "player_name": str(profile.get("name") or raw_name).strip(),
                    "input_player_name": raw_name,
                    "current_happiness": current,
                    "new_happiness": happiness,
                    "happiness": happiness,
                    "delta": float(happiness) - current,
                    "changed": current != float(happiness),
                    "expected_version": int(profile.get("version") or 1),
                    "match_method": match_method,
                    "status_label": profile.get("status_label"),
                    "team_code": profile.get("team_code"),
                    "profile_status": profile.get("profile_status"),
                    "reason": str(row.get("reason") or "Initial happiness baseline import").strip(),
                    "event_date": str(row.get("event_date") or row.get("date") or "")[:10] or None,
                }
            )
        changed_count = sum(1 for record in records if record["changed"])
        return {
            "ok": not errors and not ambiguous,
            "errors": errors,
            "records": records,
            "summary": {
                "input_count": len(rows),
                "matched_count": len(records),
                "changed_count": changed_count,
                "unchanged_count": len(records) - changed_count,
                "unmatched_count": len(unmatched),
                "ambiguous_count": len(ambiguous),
                "error_count": len(errors),
            },
            "unmatched": unmatched,
            "ambiguous": ambiguous,
        }

    def apply(self, records_payload: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        cleaned: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for raw in records_payload:
            if not isinstance(raw, dict):
                raise ValueError("invalid_records")
            profile_id = parse_int(raw.get("profile_id"))
            expected_version = parse_int(raw.get("expected_version"))
            player_name = str(raw.get("player_name") or "").strip()
            if profile_id is None or expected_version is None or not player_name:
                raise ValueError("invalid_records")
            if int(profile_id) in seen:
                raise ValueError("duplicate_happiness_import_target")
            seen.add(int(profile_id))
            try:
                happiness = normalize_happiness_value(raw.get("happiness", raw.get("new_happiness")))
            except ValueError as exc:
                raise ValueError("invalid_records") from exc
            cleaned.append(
                {
                    "profile_id": int(profile_id),
                    "player_name": player_name,
                    "input_player_name": raw.get("input_player_name"),
                    "happiness": happiness,
                    "expected_version": int(expected_version),
                    "match_method": raw.get("match_method") or "unknown",
                    "reason": raw.get("reason") or "Initial happiness baseline import",
                    "event_date": raw.get("event_date"),
                }
            )
        timestamp = self._now()
        command_id = f"player-happiness:baseline-import:{timestamp}"
        actor_user_id = parse_int((actor or {}).get("user_id"))
        result = self.repository.apply_baseline_import(
            cleaned,
            timestamp=timestamp,
            command_id=command_id,
            actor_user_id=actor_user_id,
        )
        result["command_id"] = command_id
        result["validation_result"] = "valid"
        result["entity_versions"] = {
            "record_count": int(result.get("record_count") or 0),
            "changed_count": int(result.get("changed_count") or 0),
            "unchanged_count": int(result.get("unchanged_count") or 0),
        }
        return result
