"""Historical trade archive persistence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

try:
    from ...auth.policies import normalize_team_code
    from ...domain._values import parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_int

from .base import LeagueRepository
from .team_assignments import assigned_gm_names_by_team


class TradeArchiveRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Any) -> None:
        super().__init__(db)
        self.now = now

    @staticmethod
    def _decode_json(value: Any, fallback: Any) -> Any:
        if value in (None, ""):
            return fallback
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback

    @staticmethod
    def _encode_json(value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _normalize_pick_round(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"2", "2nd", "second", "segunda", "segunda ronda"}:
            return "2nd"
        return "1st"

    @staticmethod
    def _canonical_pick_id(draft_year: Any, draft_round: Any, original_team: Any) -> Optional[str]:
        year = parse_int(draft_year)
        team = normalize_team_code(original_team)
        if year is None or not team:
            return None
        round_token = "2ND" if TradeArchiveRepository._normalize_pick_round(draft_round) == "2nd" else "1ST"
        return f"{int(year)}-{round_token}-{team}"

    def _resolve_draft_pick_reference(
        self,
        conn: sqlite3.Connection,
        item: Any,
        *,
        timestamp: str,
    ) -> Any:
        if not isinstance(item, dict):
            return item
        has_pick_ref = any(
            key in item
            for key in (
                "draft_pick_id",
                "draft_year",
                "year",
                "draft_round",
                "round",
                "original_team_code",
                "original_team",
                "original_owner",
            )
        )
        if not has_pick_ref:
            return item

        draft_pick_id = parse_int(item.get("draft_pick_id"))
        if draft_pick_id is not None:
            row = conn.execute(
                "SELECT id, draft_year, draft_round, original_team FROM draft_picks WHERE id = ?",
                (int(draft_pick_id),),
            ).fetchone()
            if not row:
                raise ValueError("draft_pick_not_found")
            resolved = dict(item)
            resolved.update(
                {
                    "draft_pick_id": int(row["id"]),
                    "draft_year": int(row["draft_year"]),
                    "draft_round": row["draft_round"],
                    "original_team_code": row["original_team"],
                    "canonical_id": self._canonical_pick_id(row["draft_year"], row["draft_round"], row["original_team"]),
                }
            )
            if not str(resolved.get("label") or "").strip():
                resolved["label"] = resolved["canonical_id"]
            return resolved

        draft_year = parse_int(item.get("draft_year") if "draft_year" in item else item.get("year"))
        draft_round = self._normalize_pick_round(item.get("draft_round") if "draft_round" in item else item.get("round"))
        original_team = normalize_team_code(
            item.get("original_team_code")
            or item.get("original_team")
            or item.get("original_owner")
        )
        if draft_year is None or not original_team:
            raise ValueError("invalid_draft_pick_reference")
        conn.execute(
            """INSERT INTO draft_picks (
                   draft_year, draft_round, original_team, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(draft_year, draft_round, original_team) DO UPDATE SET
                   updated_at = excluded.updated_at""",
            (int(draft_year), draft_round, original_team, timestamp, timestamp),
        )
        row = conn.execute(
            """SELECT id FROM draft_picks
               WHERE draft_year = ? AND draft_round = ? AND original_team = ?""",
            (int(draft_year), draft_round, original_team),
        ).fetchone()
        if not row:
            raise ValueError("draft_pick_not_found")
        canonical_id = self._canonical_pick_id(draft_year, draft_round, original_team)
        resolved = dict(item)
        resolved.update(
            {
                "draft_pick_id": int(row["id"]),
                "draft_year": int(draft_year),
                "draft_round": draft_round,
                "original_team_code": original_team,
                "canonical_id": canonical_id,
            }
        )
        if not str(resolved.get("label") or "").strip():
            resolved["label"] = canonical_id
        return resolved

    def _resolve_movement_references(
        self,
        conn: sqlite3.Connection,
        movement: Any,
        *,
        timestamp: str,
    ) -> Dict[str, Any]:
        if not isinstance(movement, dict):
            return {}
        resolved = dict(movement)
        picks = movement.get("picks")
        if isinstance(picks, list):
            resolved["picks"] = [
                self._resolve_draft_pick_reference(conn, item, timestamp=timestamp)
                for item in picks
            ]
        return resolved

    def _draft_pick_refs_from_movements(self, team_movements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        refs: List[Dict[str, Any]] = []
        for movement in team_movements:
            for side in ("sent", "received"):
                data = movement.get(side)
                if not isinstance(data, dict):
                    continue
                for item in data.get("picks") or []:
                    if isinstance(item, dict):
                        refs.append(item)
        return refs

    def _selection_payload(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "draft_year": int(row["draft_year"]),
            "pick_number": int(row["pick_number"]),
            "draft_round": row["draft_round"],
            "round_pick_number": int(row["round_pick_number"]),
            "player_name": row["player_name"],
            "selecting_team_code": row["selecting_team_code"],
            "selecting_team_name": row["selecting_team_name"],
            "original_team_code": row["original_team_code"],
            "canonical_id": self._canonical_pick_id(
                row["draft_year"],
                row["draft_round"],
                row["original_team_code"],
            ),
        }

    def _enrich_draft_selection_refs(
        self,
        conn: sqlite3.Connection,
        team_movements: List[Dict[str, Any]],
    ) -> None:
        refs = self._draft_pick_refs_from_movements(team_movements)
        if not refs:
            return
        pick_ids = sorted(
            {
                int(value)
                for value in (parse_int(ref.get("draft_pick_id")) for ref in refs)
                if value is not None
            }
        )
        keys: set[Tuple[int, str, str]] = set()
        for ref in refs:
            year = parse_int(ref.get("draft_year") if "draft_year" in ref else ref.get("year"))
            round_value = self._normalize_pick_round(ref.get("draft_round") if "draft_round" in ref else ref.get("round"))
            original_team = normalize_team_code(
                ref.get("original_team_code")
                or ref.get("original_team")
                or ref.get("original_owner")
            )
            if year is not None and original_team:
                keys.add((int(year), round_value, original_team))

        by_id: Dict[int, Dict[str, Any]] = {}
        by_key: Dict[Tuple[int, str, str], Dict[str, Any]] = {}
        if pick_ids:
            placeholders = ", ".join("?" for _ in pick_ids)
            rows = conn.execute(
                f"""
                SELECT h.draft_pick_id, h.draft_year, h.pick_number, h.draft_round,
                       h.round_pick_number, h.player_name, h.selecting_team_code,
                       COALESCE(selecting.name, h.selecting_team_code) AS selecting_team_name,
                       h.original_team_code
                FROM draft_history_selections h
                LEFT JOIN teams selecting ON selecting.code = h.selecting_team_code
                WHERE h.draft_pick_id IN ({placeholders})
                """,
                pick_ids,
            ).fetchall()
            for row in rows:
                payload = self._selection_payload(row)
                by_id[int(row["draft_pick_id"])] = payload
                by_key[(int(row["draft_year"]), row["draft_round"], row["original_team_code"])] = payload

        if keys:
            clauses = []
            params: List[Any] = []
            for year, round_value, original_team in sorted(keys):
                clauses.append("(h.draft_year = ? AND h.draft_round = ? AND h.original_team_code = ?)")
                params.extend([year, round_value, original_team])
            rows = conn.execute(
                f"""
                SELECT h.draft_pick_id, h.draft_year, h.pick_number, h.draft_round,
                       h.round_pick_number, h.player_name, h.selecting_team_code,
                       COALESCE(selecting.name, h.selecting_team_code) AS selecting_team_name,
                       h.original_team_code
                FROM draft_history_selections h
                LEFT JOIN teams selecting ON selecting.code = h.selecting_team_code
                WHERE {' OR '.join(clauses)}
                """,
                params,
            ).fetchall()
            for row in rows:
                payload = self._selection_payload(row)
                if row["draft_pick_id"] is not None:
                    by_id[int(row["draft_pick_id"])] = payload
                by_key[(int(row["draft_year"]), row["draft_round"], row["original_team_code"])] = payload

        for ref in refs:
            selection = None
            draft_pick_id = parse_int(ref.get("draft_pick_id"))
            if draft_pick_id is not None:
                selection = by_id.get(int(draft_pick_id))
            if selection is None:
                year = parse_int(ref.get("draft_year") if "draft_year" in ref else ref.get("year"))
                round_value = self._normalize_pick_round(ref.get("draft_round") if "draft_round" in ref else ref.get("round"))
                original_team = normalize_team_code(
                    ref.get("original_team_code")
                    or ref.get("original_team")
                    or ref.get("original_owner")
                )
                if year is not None and original_team:
                    selection = by_key.get((int(year), round_value, original_team))
            if selection is not None:
                ref["draft_selection"] = selection

    @staticmethod
    def _asset_count(movement: Dict[str, Any]) -> int:
        if not isinstance(movement, dict):
            return 0
        total = 0
        for key in ("players", "picks", "swaps", "rights"):
            values = movement.get(key)
            if isinstance(values, list):
                total += len(values)
        cash = movement.get("cash")
        if isinstance(cash, list):
            total += len(cash)
        elif movement.get("cash_amount"):
            total += 1
        return total

    @classmethod
    def total_assets_moved(cls, team_movements: List[Dict[str, Any]]) -> int:
        return sum(cls._asset_count(row.get("sent") or {}) for row in team_movements if isinstance(row, dict))

    @staticmethod
    def _gm_timeline_cache(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
        rows = conn.execute(
            """
            SELECT t.code AS team_code, h.gm_name, h.start_date
            FROM team_gm_history h
            JOIN teams t ON t.id = h.team_id
            ORDER BY t.code, h.start_date, h.row_order, h.id
            """
        ).fetchall()
        cache: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            code = normalize_team_code(row["team_code"])
            if not code:
                continue
            cache.setdefault(code, []).append(
                {
                    "gm_name": str(row["gm_name"] or "").strip(),
                    "start_date": str(row["start_date"] or "").strip(),
                }
            )
        return cache

    @staticmethod
    def _gm_from_timeline(
        timeline_cache: Dict[str, List[Dict[str, Any]]],
        team_code: Any,
        trade_date: Any,
    ) -> Optional[str]:
        code = normalize_team_code(team_code)
        date_key = str(trade_date or "").strip()[:10]
        if not code or len(date_key) != 10:
            return None
        match = None
        for row in timeline_cache.get(code) or []:
            if str(row.get("start_date") or "") <= date_key:
                match = row
            else:
                break
        return str((match or {}).get("gm_name") or "").strip() or None

    def _row_to_trade(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        timeline_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        assigned_gm_cache: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        gm_timeline = timeline_cache if timeline_cache is not None else self._gm_timeline_cache(conn)
        assigned_gms = assigned_gm_cache if assigned_gm_cache is not None else assigned_gm_names_by_team(conn)
        trade_id = int(row["id"])
        movement_rows = conn.execute(
            """SELECT team_code, team_name, gm_name, sent_json, received_json
               FROM trade_archive_team_movements
               WHERE trade_id = ?
               ORDER BY team_code""",
            (trade_id,),
        ).fetchall()
        team_movements = []
        for movement in movement_rows:
            team_movements.append(
                {
                    "team_code": str(movement["team_code"] or ""),
                    "team_name": movement["team_name"],
                    "gm_name": movement["gm_name"],
                    "timeline_gm_name": (
                        None
                        if movement["gm_name"]
                        else (
                            self._gm_from_timeline(gm_timeline, movement["team_code"], row["trade_date"])
                            or assigned_gms.get(normalize_team_code(movement["team_code"]) or "")
                        )
                    ),
                    "sent": self._decode_json(movement["sent_json"], {}),
                    "received": self._decode_json(movement["received_json"], {}),
                }
            )
        self._enrich_draft_selection_refs(conn, team_movements)
        team_codes = [row["team_code"] for row in team_movements if row.get("team_code")]
        return {
            "id": trade_id,
            "trade_id": row["external_trade_id"] or str(trade_id),
            "external_trade_id": row["external_trade_id"],
            "trade_date": row["trade_date"],
            "season_year": row["season_year"],
            "teams": team_codes,
            "team_movements": team_movements,
            "total_assets_moved": int(row["total_assets_moved"] or 0),
            "source": row["source"],
            "source_ref": row["source_ref"],
            "notes": row["notes"],
            "version": int(row["version"] or 1),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self, *, season_year: Any = None) -> Dict[str, Any]:
        parsed_season = parse_int(season_year)
        params: List[Any] = []
        where = ""
        if parsed_season is not None:
            where = "WHERE season_year = ?"
            params.append(parsed_season)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT id, external_trade_id, trade_date, season_year, total_assets_moved,
                          source, source_ref, notes, version, created_at, updated_at
                  FROM trade_archive
                  {where}
                  ORDER BY trade_date DESC, id DESC""",
                params,
            ).fetchall()
            timeline_cache = self._gm_timeline_cache(conn)
            assigned_gm_cache = assigned_gm_names_by_team(conn)
            trades = [
                self._row_to_trade(
                    conn,
                    row,
                    timeline_cache=timeline_cache,
                    assigned_gm_cache=assigned_gm_cache,
                )
                for row in rows
            ]
        seasons_map: Dict[int, List[Dict[str, Any]]] = {}
        for trade in trades:
            season = parse_int(trade.get("season_year")) or 0
            seasons_map.setdefault(season, []).append(trade)
        seasons = [
            {"season_year": season, "trades": rows}
            for season, rows in sorted(seasons_map.items(), key=lambda item: item[0], reverse=True)
        ]
        return {"trades": trades, "seasons": seasons}

    def get(self, trade_id: Any) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(trade_id)
        if parsed_id is None:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT id, external_trade_id, trade_date, season_year, total_assets_moved,
                          source, source_ref, notes, version, created_at, updated_at
                   FROM trade_archive WHERE id = ?""",
                (parsed_id,),
            ).fetchone()
            return self._row_to_trade(conn, row) if row else None

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.db.transaction("IMMEDIATE") as conn:
            return self.create_conn(conn, payload)

    def create_conn(self, conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = self.now()
        team_movements = payload.get("team_movements") if isinstance(payload.get("team_movements"), list) else []
        total_assets = parse_int(payload.get("total_assets_moved"))
        if total_assets is None:
            total_assets = self.total_assets_moved(team_movements)
        cur = conn.execute(
            """INSERT INTO trade_archive (
                   external_trade_id, trade_date, season_year, total_assets_moved,
                   source, source_ref, notes, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(payload.get("external_trade_id") or "").strip() or None,
                str(payload.get("trade_date") or timestamp[:10]).strip(),
                int(parse_int(payload.get("season_year")) or parse_int(payload.get("season")) or 0),
                int(total_assets or 0),
                str(payload.get("source") or "manual").strip() or "manual",
                str(payload.get("source_ref") or "").strip() or None,
                str(payload.get("notes") or "").strip() or None,
                timestamp,
                timestamp,
            ),
        )
        trade_id = int(cur.lastrowid)
        self.replace_movements_conn(conn, trade_id, team_movements, timestamp=timestamp)
        row = conn.execute(
            """SELECT id, external_trade_id, trade_date, season_year, total_assets_moved,
                      source, source_ref, notes, version, created_at, updated_at
               FROM trade_archive WHERE id = ?""",
            (trade_id,),
        ).fetchone()
        return self._row_to_trade(conn, row)

    def update(self, trade_id: Any, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(trade_id)
        if parsed_id is None:
            return None
        with self.db.transaction("IMMEDIATE") as conn:
            existing = conn.execute("SELECT id FROM trade_archive WHERE id = ?", (parsed_id,)).fetchone()
            if not existing:
                return None
            timestamp = self.now()
            team_movements = payload.get("team_movements") if isinstance(payload.get("team_movements"), list) else None
            total_assets = parse_int(payload.get("total_assets_moved"))
            if total_assets is None and team_movements is not None:
                total_assets = self.total_assets_moved(team_movements)
            fields: List[str] = []
            values: List[Any] = []
            field_map = {
                "external_trade_id": str(payload.get("external_trade_id") or "").strip() or None,
                "trade_date": str(payload.get("trade_date") or "").strip() or None,
                "season_year": parse_int(payload.get("season_year") if "season_year" in payload else payload.get("season")),
                "total_assets_moved": total_assets,
                "notes": str(payload.get("notes") or "").strip() or None,
            }
            for key, value in field_map.items():
                if key in payload or (key == "season_year" and "season" in payload):
                    fields.append(f"{key} = ?")
                    values.append(value)
            fields.extend(["version = version + 1", "updated_at = ?"])
            values.append(timestamp)
            values.append(parsed_id)
            conn.execute(f"UPDATE trade_archive SET {', '.join(fields)} WHERE id = ?", values)
            if team_movements is not None:
                self.replace_movements_conn(conn, parsed_id, team_movements, timestamp=timestamp)
                conn.execute(
                    "UPDATE trade_archive SET total_assets_moved = ?, updated_at = ? WHERE id = ?",
                    (self.total_assets_moved(team_movements), timestamp, parsed_id),
                )
            row = conn.execute(
                """SELECT id, external_trade_id, trade_date, season_year, total_assets_moved,
                          source, source_ref, notes, version, created_at, updated_at
                   FROM trade_archive WHERE id = ?""",
                (parsed_id,),
            ).fetchone()
            return self._row_to_trade(conn, row) if row else None

    def replace_movements_conn(
        self,
        conn: sqlite3.Connection,
        trade_id: int,
        team_movements: List[Dict[str, Any]],
        *,
        timestamp: Optional[str] = None,
    ) -> None:
        ts = timestamp or self.now()
        conn.execute("DELETE FROM trade_archive_team_movements WHERE trade_id = ?", (trade_id,))
        for movement in team_movements:
            if not isinstance(movement, dict):
                continue
            team_code = normalize_team_code(movement.get("team_code") or movement.get("code"))
            if not team_code:
                continue
            conn.execute(
                """INSERT INTO trade_archive_team_movements (
                       trade_id, team_code, team_name, gm_name, sent_json, received_json, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_id,
                    team_code,
                    str(movement.get("team_name") or "").strip() or None,
                    str(movement.get("gm_name") or movement.get("gm") or "").strip() or None,
                    self._encode_json(self._resolve_movement_references(conn, movement.get("sent"), timestamp=ts)),
                    self._encode_json(self._resolve_movement_references(conn, movement.get("received"), timestamp=ts)),
                    ts,
                    ts,
                ),
            )

    def delete(self, trade_id: Any) -> bool:
        parsed_id = parse_int(trade_id)
        if parsed_id is None:
            return False
        with self.db.transaction("IMMEDIATE") as conn:
            cur = conn.execute("DELETE FROM trade_archive WHERE id = ?", (parsed_id,))
            return cur.rowcount > 0
