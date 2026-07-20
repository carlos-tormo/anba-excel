"""Validation and orchestration for free-agent agent-assignment imports."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_int


def normalize_import_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class FreeAgentAgentImportService:
    def __init__(
        self,
        repository: Any,
        *,
        now: Callable[[], str],
        synchronize_generated: Callable[[Any, Dict[str, str]], Dict[str, Any]],
    ) -> None:
        self.repository = repository
        self._now = now
        self._synchronize_generated = synchronize_generated

    def preview(self, rows: List[List[str]]) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        records: List[Dict[str, Any]] = []
        first_row_index: Optional[int] = next(
            (index for index, row in enumerate(rows) if any(str(cell or "").strip() for cell in row)),
            None,
        )
        if first_row_index is None:
            return {
                "ok": False,
                "errors": [{"line": None, "message": "El archivo no tiene filas con datos."}],
                "records": [],
                "summary": {"record_count": 0, "changed_count": 0, "unchanged_count": 0, "new_agent_count": 0},
                "new_agents": [],
            }
        header = [normalize_import_text(cell) for cell in rows[first_row_index]]
        player_keys = {"player", "player_name", "jugador", "nombre", "name"}
        agent_keys = {"agent", "agente", "rep", "representante", "representante_jugador"}
        player_col = next((index for index, value in enumerate(header) if value in player_keys), None)
        agent_col = next((index for index, value in enumerate(header) if value in agent_keys), None)
        data_start = first_row_index + 1 if player_col is not None and agent_col is not None else first_row_index
        if player_col is None or agent_col is None:
            player_col, agent_col = 0, 1

        with self.repository.connect() as conn:
            settings = self.repository.settings(conn)
            changed = self._synchronize_generated(conn, settings).get("changed")
            if changed:
                conn.commit()
            free_agents = self.repository.free_agents(conn)
            existing_reps = self.repository.configured_reps(conn)

        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for free_agent in free_agents:
            key = normalize_import_text(free_agent.get("name"))
            if key:
                by_name.setdefault(key, []).append(free_agent)
        seen: Dict[int, int] = {}
        for row_index in range(data_start, len(rows)):
            row = rows[row_index]
            line = row_index + 1
            if not any(str(cell or "").strip() for cell in row):
                continue
            player_name = str(row[player_col] if player_col < len(row) else "").strip()
            agent_name = re.sub(r"\s+", " ", str(row[agent_col] if agent_col < len(row) else "").strip())
            if not player_name and not agent_name:
                continue
            if not player_name or not agent_name:
                errors.append({"line": line, "message": "Cada fila debe tener jugador y agente."})
                continue
            matches = by_name.get(normalize_import_text(player_name), [])
            if not matches:
                errors.append({"line": line, "message": f"No se encontró agente libre: {player_name}."})
                continue
            if len(matches) > 1:
                errors.append({"line": line, "message": f"Nombre ambiguo: {player_name}. Hay más de un agente libre con ese nombre."})
                continue
            free_agent = matches[0]
            free_agent_id = int(free_agent["id"])
            if free_agent_id in seen:
                errors.append({"line": line, "message": f"Jugador duplicado en el archivo: {player_name} ya apareció en la línea {seen[free_agent_id]}."})
                continue
            seen[free_agent_id] = line
            current_agent = str(free_agent.get("agent") or "").strip()
            records.append({
                "line": line, "free_agent_id": free_agent_id,
                "player_name": str(free_agent.get("name") or player_name).strip(),
                "input_player_name": player_name, "current_agent": current_agent,
                "agent_name": agent_name,
                "changed": current_agent.casefold() != agent_name.casefold(),
            })
        known_reps = {rep.casefold() for rep in existing_reps}
        new_agents: List[str] = []
        for record in records:
            name = record["agent_name"]
            if name.casefold() not in known_reps:
                known_reps.add(name.casefold())
                new_agents.append(name)
        changed_count = sum(1 for record in records if record["changed"])
        return {
            "ok": not errors, "errors": errors, "records": records,
            "summary": {
                "record_count": len(records), "changed_count": changed_count,
                "unchanged_count": len(records) - changed_count,
                "new_agent_count": len(new_agents),
            },
            "new_agents": new_agents,
        }

    def apply(self, records_payload: Any) -> Dict[str, Any]:
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("records_required")
        cleaned = []
        for raw in records_payload:
            if not isinstance(raw, dict):
                raise ValueError("invalid_records")
            free_agent_id = parse_int(raw.get("free_agent_id"))
            agent_name = re.sub(r"\s+", " ", str(raw.get("agent_name") or "").strip())
            if free_agent_id is None or not agent_name:
                raise ValueError("invalid_records")
            cleaned.append({"free_agent_id": free_agent_id, "agent_name": agent_name})
        return self.repository.apply(cleaned, self._now())
