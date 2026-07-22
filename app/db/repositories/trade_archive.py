"""Historical trade archive persistence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

try:
    from ...auth.policies import normalize_team_code
    from ...domain._values import parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain._values import parse_int

from .base import LeagueRepository


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

    def _row_to_trade(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
        trade_id = int(row["id"])
        movement_rows = conn.execute(
            """SELECT team_code, team_name, sent_json, received_json
               FROM trade_archive_team_movements
               WHERE trade_id = ?
               ORDER BY team_code""",
            (trade_id,),
        ).fetchall()
        team_movements = [
            {
                "team_code": str(movement["team_code"] or ""),
                "team_name": movement["team_name"],
                "sent": self._decode_json(movement["sent_json"], {}),
                "received": self._decode_json(movement["received_json"], {}),
            }
            for movement in movement_rows
        ]
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
            trades = [self._row_to_trade(conn, row) for row in rows]
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
                       trade_id, team_code, team_name, sent_json, received_json, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_id,
                    team_code,
                    str(movement.get("team_name") or "").strip() or None,
                    self._encode_json(movement.get("sent") if isinstance(movement.get("sent"), dict) else {}),
                    self._encode_json(movement.get("received") if isinstance(movement.get("received"), dict) else {}),
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
