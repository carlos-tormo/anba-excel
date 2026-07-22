"""Team depth-chart persistence and read-model assembly."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List

try:
    from ...domain_rules import parse_int
except ImportError:  # pragma: no cover
    from domain_rules import parse_int

from .base import LeagueRepository


class DepthChartRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        players: Any,
        now: Callable[[], str],
        normalize_team_code: Callable[[Any], str],
        positions: Iterable[str],
        max_depth: int,
    ) -> None:
        super().__init__(db)
        self._players = players
        self._now = now
        self._normalize_team_code = normalize_team_code
        self._positions = tuple(positions)
        self._max_depth = int(max_depth)

    @staticmethod
    def player_payload(player: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": parse_int(player.get("id")),
            "profile_id": parse_int(player.get("profile_id")),
            "name": str(player.get("name") or "").strip(),
            "position": str(player.get("position") or "").strip(),
            "rating": str(player.get("rating") or "").strip(),
            "contract_type": str(player.get("contract_type") or "").strip(),
        }

    def team_players(self, conn: Any, team_id: int) -> List[Dict[str, Any]]:
        return [self.player_payload(player) for player in self._players.select_team(conn, team_id)]

    def payload(self, conn: Any, team_id: int) -> Dict[str, Any]:
        version_row = conn.execute(
            "SELECT version FROM team_depth_chart_versions WHERE team_id = ?",
            (team_id,),
        ).fetchone()
        version = parse_int(version_row["version"]) if version_row else 1
        cursor = conn.execute(
            f"""SELECT dc.position AS depth_position, dc.depth_order,
                       {self._players.select_columns()}
                FROM team_depth_charts dc
                JOIN players p ON p.id = dc.player_id AND p.team_id = dc.team_id
                LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                WHERE dc.team_id = ? ORDER BY dc.position, dc.depth_order""",
            (team_id,),
        )
        rows = self._players.rows_from_cursor(cursor, cursor.fetchall())
        entries = [
            {
                "position": str(row.get("depth_position") or "").strip().upper(),
                "depth_order": parse_int(row.get("depth_order")),
                "player": self.player_payload(row),
            }
            for row in rows
        ]
        return {
            "positions": list(self._positions),
            "max_depth": self._max_depth,
            "version": version,
            "configured": bool(entries),
            "entries": entries,
        }

    def set(self, team_code: Any, entries: Any, *, expected_version: Any = None) -> Dict[str, Any]:
        normalized_team = self._normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("team_code_required")
        if not isinstance(entries, list):
            raise ValueError("invalid_entries")
        cleaned: List[Dict[str, int | str]] = []
        seen_cells = set()
        seen_players = set()
        for raw in entries:
            if not isinstance(raw, dict):
                raise ValueError("invalid_entry")
            position = str(raw.get("position") or "").strip().upper()
            depth_order = parse_int(raw.get("depth_order"))
            player_id = parse_int(raw.get("player_id"))
            if position not in self._positions:
                raise ValueError("invalid_position")
            if depth_order is None or depth_order < 1 or depth_order > self._max_depth:
                raise ValueError("invalid_depth_order")
            if player_id is None or player_id <= 0:
                raise ValueError("invalid_player_id")
            cell = (position, depth_order)
            if cell in seen_cells:
                raise ValueError("duplicate_depth_cell")
            if player_id in seen_players:
                raise ValueError("duplicate_player")
            seen_cells.add(cell)
            seen_players.add(player_id)
            cleaned.append({"position": position, "depth_order": depth_order, "player_id": player_id})

        timestamp = self._now()
        with self.db.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (normalized_team,)).fetchone()
            if not team:
                raise ValueError("team_not_found")
            team_id = int(team["id"])
            version_row = conn.execute(
                "SELECT version FROM team_depth_chart_versions WHERE team_id = ?",
                (team_id,),
            ).fetchone()
            current_version = parse_int(version_row["version"]) if version_row else 1
            parsed_expected_version = parse_int(expected_version)
            if parsed_expected_version is not None and parsed_expected_version != current_version:
                raise ValueError("stale_entity_version")
            if seen_players:
                placeholders = ",".join("?" for _ in seen_players)
                owned_ids = {int(row["id"]) for row in conn.execute(
                    f"SELECT id FROM players WHERE team_id = ? AND id IN ({placeholders})",
                    (team_id, *seen_players),
                ).fetchall()}
                cleaned = [entry for entry in cleaned if int(entry["player_id"]) in owned_ids]
            conn.execute("DELETE FROM team_depth_charts WHERE team_id = ?", (team_id,))
            conn.executemany(
                """INSERT INTO team_depth_charts
                       (team_id, player_id, position, depth_order, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (team_id, entry["player_id"], entry["position"], entry["depth_order"], timestamp, timestamp)
                    for entry in cleaned
                ],
            )
            if version_row:
                cur = conn.execute(
                    """UPDATE team_depth_chart_versions
                       SET version = COALESCE(version, 0) + 1, updated_at = ?
                       WHERE team_id = ? AND version = ?""",
                    (timestamp, team_id, current_version),
                )
                if cur.rowcount != 1:
                    raise ValueError("stale_entity_version")
            else:
                if parsed_expected_version is not None and parsed_expected_version != 1:
                    raise ValueError("stale_entity_version")
                conn.execute(
                    """INSERT INTO team_depth_chart_versions (team_id, version, updated_at)
                       VALUES (?, 2, ?)""",
                    (team_id, timestamp),
                )
            conn.commit()
            return self.payload(conn, team_id)
