"""Free-agent team-appeal import validation and ranking composition."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, List

try:
    from ..auth.policies import normalize_team_code
    from ..domain._values import parse_amount_like
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_amount_like


def normalize_import_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class FreeAgentAppealService:
    def __init__(self, repository: Any, *, now: Callable[[], str]) -> None:
        self.repository = repository
        self._now = now

    FREE_AGENT_TEAM_APPEAL_COLUMNS = [
        ("under_23_single", "Menores de 23 · 1 año"),
        ("under_23_multi", "Menores de 23 · multi"),
        ("age_23_26_single", "23-26 · 1 año"),
        ("age_23_26_multi", "23-26 · multi"),
        ("age_27_33_single", "27-33 · 1 año"),
        ("age_27_33_multi", "27-33 · multi"),
        ("over_34_single", "34+ · 1 año"),
        ("over_34_multi", "34+ · multi"),
    ]

    FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS = [
        ("under_23_multi", "Ranking atractivo <23", "Multianual"),
        ("under_23_single", "Ranking atractivo <23", "1 año"),
        ("age_23_26_multi", "Ranking atractivo <27", "Multianual"),
        ("age_23_26_single", "Ranking atractivo <27", "1 año"),
        ("age_27_33_multi", "Ranking atractivo 27-33", "Multianual"),
        ("age_27_33_single", "Ranking atractivo 27-33", "1 año"),
        ("over_34_multi", "Ranking atractivo +34", "Multianual"),
        ("over_34_single", "Ranking atractivo +34", "1 año"),
    ]

    def _free_agent_team_appeal_columns_payload(self) -> List[Dict[str, Any]]:
        return [
            {"key": key, "label": f"{group} · {sub_label}", "group": group, "sub_label": sub_label}
            for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS
        ]

    @staticmethod
    def _free_agent_appeal_header_key(value: Any) -> str:
        text = normalize_import_text(value).casefold()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        aliases = {
            "team": "team_code",
            "equipo": "team_code",
            "franquicia": "team_code",
            "team_code": "team_code",
            "codigo": "team_code",
            "under_23_single": "under_23_single",
            "u23_single": "under_23_single",
            "menor_23_single": "under_23_single",
            "menores_23_single": "under_23_single",
            "under_23_1": "under_23_single",
            "u23_1": "under_23_single",
            "menor_23_1": "under_23_single",
            "menores_23_1": "under_23_single",
            "menos_23_1": "under_23_single",
            "under_23_multi": "under_23_multi",
            "u23_multi": "under_23_multi",
            "menor_23_multi": "under_23_multi",
            "menores_23_multi": "under_23_multi",
            "menos_23_multi": "under_23_multi",
            "23_26_single": "age_23_26_single",
            "age_23_26_single": "age_23_26_single",
            "edad_23_26_single": "age_23_26_single",
            "23_26_1": "age_23_26_single",
            "age_23_26_1": "age_23_26_single",
            "edad_23_26_1": "age_23_26_single",
            "23_26_multi": "age_23_26_multi",
            "age_23_26_multi": "age_23_26_multi",
            "edad_23_26_multi": "age_23_26_multi",
            "27_33_single": "age_27_33_single",
            "age_27_33_single": "age_27_33_single",
            "edad_27_33_single": "age_27_33_single",
            "27_33_1": "age_27_33_single",
            "age_27_33_1": "age_27_33_single",
            "edad_27_33_1": "age_27_33_single",
            "27_33_multi": "age_27_33_multi",
            "age_27_33_multi": "age_27_33_multi",
            "edad_27_33_multi": "age_27_33_multi",
            "over_34_single": "over_34_single",
            "34_single": "over_34_single",
            "34_1": "over_34_single",
            "mas_34_single": "over_34_single",
            "mayor_34_single": "over_34_single",
            "over_34_1": "over_34_single",
            "over_34_multi": "over_34_multi",
            "34_multi": "over_34_multi",
            "mas_34_multi": "over_34_multi",
            "mayor_34_multi": "over_34_multi",
        }
        return aliases.get(text, text)

    def _free_agent_appeal_ranking_header_key(self, group_value: Any, sub_value: Any = "") -> str:
        group = self._free_agent_appeal_header_key(group_value)
        sub = self._free_agent_appeal_header_key(sub_value)
        combined = "_".join(part for part in [group, sub] if part)
        aliases = {
            "under_23_multi": "under_23_multi",
            "u23_multi": "under_23_multi",
            "ranking_atractivo_23_multianual": "under_23_multi",
            "atractivo_23_multianual": "under_23_multi",
            "menores_23_multianual": "under_23_multi",
            "menos_23_multianual": "under_23_multi",
            "under_23_single": "under_23_single",
            "u23_single": "under_23_single",
            "under_23_1": "under_23_single",
            "u23_1": "under_23_single",
            "ranking_atractivo_23_1_ano": "under_23_single",
            "ranking_atractivo_23_1": "under_23_single",
            "atractivo_23_1_ano": "under_23_single",
            "menores_23_1_ano": "under_23_single",
            "menos_23_1_ano": "under_23_single",
            "age_23_26_multi": "age_23_26_multi",
            "23_26_multi": "age_23_26_multi",
            "ranking_atractivo_27_multianual": "age_23_26_multi",
            "atractivo_27_multianual": "age_23_26_multi",
            "menores_27_multianual": "age_23_26_multi",
            "age_23_26_single": "age_23_26_single",
            "23_26_single": "age_23_26_single",
            "23_26_1": "age_23_26_single",
            "ranking_atractivo_27_1_ano": "age_23_26_single",
            "ranking_atractivo_27_1": "age_23_26_single",
            "atractivo_27_1_ano": "age_23_26_single",
            "menores_27_1_ano": "age_23_26_single",
            "age_27_33_multi": "age_27_33_multi",
            "27_33_multi": "age_27_33_multi",
            "ranking_atractivo_27_33_multianual": "age_27_33_multi",
            "atractivo_27_33_multianual": "age_27_33_multi",
            "age_27_33_single": "age_27_33_single",
            "27_33_single": "age_27_33_single",
            "27_33_1": "age_27_33_single",
            "ranking_atractivo_27_33_1_ano": "age_27_33_single",
            "ranking_atractivo_27_33_1": "age_27_33_single",
            "atractivo_27_33_1_ano": "age_27_33_single",
            "over_34_multi": "over_34_multi",
            "34_multi": "over_34_multi",
            "ranking_atractivo_34_multianual": "over_34_multi",
            "atractivo_34_multianual": "over_34_multi",
            "mas_34_multianual": "over_34_multi",
            "mayores_34_multianual": "over_34_multi",
            "over_34_single": "over_34_single",
            "34_single": "over_34_single",
            "34_1": "over_34_single",
            "ranking_atractivo_34_1_ano": "over_34_single",
            "ranking_atractivo_34_1": "over_34_single",
            "atractivo_34_1_ano": "over_34_single",
            "mas_34_1_ano": "over_34_single",
            "mayores_34_1_ano": "over_34_single",
        }
        return aliases.get(combined, aliases.get(group, combined))

    def _free_agent_team_appeal_rankings_from_records(
        self,
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_key = {key: sorted(records, key=lambda record: (float(record.get(key) or 0.0), str(record.get("team_code") or ""))) for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS}
        max_rows = max((len(items) for items in by_key.values()), default=0)
        rankings: List[Dict[str, Any]] = []
        for idx in range(max_rows):
            row: Dict[str, Any] = {"rank": idx + 1}
            for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                item = by_key.get(key, [])[idx] if idx < len(by_key.get(key, [])) else None
                row[key] = {
                    "team_code": str(item.get("team_code") or "").upper() if item else "",
                    "team_name": str(item.get("team_name") or "") if item else "",
                    "value": float(item.get(key) or 0.0) if item else 0.0,
                }
            rankings.append(row)
        return rankings

    def _free_agent_team_appeal_records_from_rows(self, rows: List[List[str]]) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        if not rows:
            return {
                "ok": False,
                "errors": [{"line": None, "message": "El archivo está vacío."}],
                "records": [],
                "summary": {"record_count": 0, "team_count": 0},
                "columns": self._free_agent_team_appeal_columns_payload(),
                "rankings": [],
            }

        first_non_empty_idx = next((idx for idx, row in enumerate(rows) if any(str(cell or "").strip() for cell in row)), None)
        if first_non_empty_idx is None:
            return {
                "ok": False,
                "errors": [{"line": None, "message": "El archivo está vacío."}],
                "records": [],
                "summary": {"record_count": 0, "team_count": 0},
                "columns": self._free_agent_team_appeal_columns_payload(),
                "rankings": [],
            }

        teams = {str(team.get("code") or "").upper(): team for team in self.repository.list_teams()}
        ranking_keys = [key for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS]
        header = rows[first_non_empty_idx]
        normalized_header = [self._free_agent_appeal_header_key(cell) for cell in header]
        required_keys = ["team_code", *[key for key, _label in self.FREE_AGENT_TEAM_APPEAL_COLUMNS]]
        has_header = all(key in normalized_header for key in required_keys)
        if has_header:
            header_map = {key: normalized_header.index(key) for key in required_keys}
            data_rows = rows[first_non_empty_idx + 1 :]
            line_offset = first_non_empty_idx + 2
        else:
            canonical_ranking_header = [self._free_agent_appeal_ranking_header_key(cell) for cell in header]
            has_ranking_header = all(key in canonical_ranking_header for key in ranking_keys)
            if has_ranking_header:
                column_map = {key: canonical_ranking_header.index(key) for key in ranking_keys}
                data_rows = rows[first_non_empty_idx + 1 :]
                line_offset = first_non_empty_idx + 2
                records_by_team: Dict[str, Dict[str, Any]] = {
                    team_code: {
                        "team_code": team_code,
                        "team_name": str(team.get("name") or team_code),
                    }
                    for team_code, team in teams.items()
                }
                seen_by_column: Dict[str, set[str]] = {key: set() for key in ranking_keys}
                for row_idx, row in enumerate(data_rows, start=line_offset):
                    if not any(str(cell or "").strip() for cell in row):
                        continue
                    rank = row_idx - line_offset + 1
                    for key, _group, _sub in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                        team_raw = row[column_map[key]] if column_map[key] < len(row) else ""
                        team_code = normalize_team_code(team_raw)
                        if not team_code:
                            errors.append({"line": row_idx, "message": f"Equipo requerido en {key}."})
                            continue
                        if team_code not in teams:
                            errors.append({"line": row_idx, "message": f"Equipo inválido en {key}: {team_code}."})
                            continue
                        if team_code in seen_by_column[key]:
                            errors.append({"line": row_idx, "message": f"Equipo duplicado en {key}: {team_code}."})
                            continue
                        seen_by_column[key].add(team_code)
                        records_by_team[team_code][key] = float(rank)
                for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                    missing = sorted(set(teams.keys()) - seen_by_column[key])
                    for team_code in missing:
                        errors.append({"line": None, "message": f"Falta {team_code} en {group} · {sub_label}."})
                records = []
                for team_code in sorted(records_by_team.keys()):
                    record = records_by_team[team_code]
                    for key in ranking_keys:
                        record[key] = float(record.get(key) or 0.0)
                    records.append(record)
                return {
                    "ok": not errors,
                    "errors": errors,
                    "records": records,
                    "summary": {"record_count": len(records), "team_count": len(teams)},
                    "columns": self._free_agent_team_appeal_columns_payload(),
                    "rankings": self._free_agent_team_appeal_rankings_from_records(records),
                }

            second_header = rows[first_non_empty_idx + 1] if first_non_empty_idx + 1 < len(rows) else []
            group_values: List[str] = []
            last_group = ""
            max_len = max(len(header), len(second_header))
            for idx in range(max_len):
                group_raw = str(header[idx] if idx < len(header) else "").strip()
                if group_raw:
                    last_group = group_raw
                group_values.append(last_group)
            two_row_keys = [
                self._free_agent_appeal_ranking_header_key(group_values[idx], second_header[idx] if idx < len(second_header) else "")
                for idx in range(max_len)
            ]
            has_two_row_ranking_header = all(key in two_row_keys for key in ranking_keys)
            if has_two_row_ranking_header:
                column_map = {key: two_row_keys.index(key) for key in ranking_keys}
                data_rows = rows[first_non_empty_idx + 2 :]
                line_offset = first_non_empty_idx + 3
                records_by_team = {
                    team_code: {
                        "team_code": team_code,
                        "team_name": str(team.get("name") or team_code),
                    }
                    for team_code, team in teams.items()
                }
                seen_by_column = {key: set() for key in ranking_keys}
                rank = 0
                for row_idx, row in enumerate(data_rows, start=line_offset):
                    if not any(str(cell or "").strip() for cell in row):
                        continue
                    rank += 1
                    for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                        team_raw = row[column_map[key]] if column_map[key] < len(row) else ""
                        team_code = normalize_team_code(team_raw)
                        if not team_code:
                            errors.append({"line": row_idx, "message": f"Equipo requerido en {group} · {sub_label}."})
                            continue
                        if team_code not in teams:
                            errors.append({"line": row_idx, "message": f"Equipo inválido en {group} · {sub_label}: {team_code}."})
                            continue
                        if team_code in seen_by_column[key]:
                            errors.append({"line": row_idx, "message": f"Equipo duplicado en {group} · {sub_label}: {team_code}."})
                            continue
                        seen_by_column[key].add(team_code)
                        records_by_team[team_code][key] = float(rank)
                for key, group, sub_label in self.FREE_AGENT_TEAM_APPEAL_RANKING_COLUMNS:
                    missing = sorted(set(teams.keys()) - seen_by_column[key])
                    for team_code in missing:
                        errors.append({"line": None, "message": f"Falta {team_code} en {group} · {sub_label}."})
                records = []
                for team_code in sorted(records_by_team.keys()):
                    record = records_by_team[team_code]
                    for key in ranking_keys:
                        record[key] = float(record.get(key) or 0.0)
                    records.append(record)
                return {
                    "ok": not errors,
                    "errors": errors,
                    "records": records,
                    "summary": {"record_count": len(records), "team_count": len(teams)},
                    "columns": self._free_agent_team_appeal_columns_payload(),
                    "rankings": self._free_agent_team_appeal_rankings_from_records(records),
                }

            header_map = {key: idx for idx, key in enumerate(required_keys)}
            data_rows = rows[first_non_empty_idx:]
            line_offset = first_non_empty_idx + 1

        records: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row_idx, row in enumerate(data_rows, start=line_offset):
            if not any(str(cell or "").strip() for cell in row):
                continue
            team_raw = row[header_map["team_code"]] if header_map["team_code"] < len(row) else ""
            team_code = normalize_team_code(team_raw)
            if not team_code:
                errors.append({"line": row_idx, "message": "Equipo requerido."})
                continue
            if team_code not in teams:
                errors.append({"line": row_idx, "message": f"Equipo inválido: {team_code}."})
                continue
            if team_code in seen:
                errors.append({"line": row_idx, "message": f"Equipo duplicado: {team_code}."})
                continue
            seen.add(team_code)
            record: Dict[str, Any] = {
                "team_code": team_code,
                "team_name": str(teams[team_code].get("name") or team_code),
            }
            for key, label in self.FREE_AGENT_TEAM_APPEAL_COLUMNS:
                raw_value = row[header_map[key]] if header_map[key] < len(row) else ""
                amount = parse_amount_like(raw_value)
                if amount is None:
                    errors.append({"line": row_idx, "message": f"Valor inválido para {team_code} · {label}."})
                    amount = 0.0
                record[key] = float(amount or 0.0)
            records.append(record)

        missing = sorted(set(teams.keys()) - seen)
        for team_code in missing:
            errors.append({"line": None, "message": f"Falta el equipo {team_code}."})

        return {
            "ok": not errors,
            "errors": errors,
            "records": records,
            "summary": {"record_count": len(records), "team_count": len(seen)},
            "columns": self._free_agent_team_appeal_columns_payload(),
            "rankings": self._free_agent_team_appeal_rankings_from_records(records),
        }


    def preview(self, rows: List[List[str]]) -> Dict[str, Any]:
        return self._free_agent_team_appeal_records_from_rows(rows)

    def apply(self, records_payload: Any) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        required_keys = [key for key, _label in self.FREE_AGENT_TEAM_APPEAL_COLUMNS]
        cleaned: List[Dict[str, Any]] = []
        for raw_record in records_payload:
            if not isinstance(raw_record, dict):
                raise ValueError("invalid_records")
            team_code = normalize_team_code(raw_record.get("team_code"))
            if not team_code:
                raise ValueError("invalid_records")
            record: Dict[str, Any] = {"team_code": team_code}
            for key in required_keys:
                amount = parse_amount_like(raw_record.get(key))
                if amount is None:
                    raise ValueError("invalid_records")
                record[key] = float(amount or 0.0)
            cleaned.append(record)
        imported = self.repository.replace(cleaned, self._now())
        return {"record_count": imported}

    def list(self) -> Dict[str, Any]:
        records = self.repository.list_rows()
        return {
            "columns": self._free_agent_team_appeal_columns_payload(),
            "rows": records,
            "rankings": self._free_agent_team_appeal_rankings_from_records(records),
        }
