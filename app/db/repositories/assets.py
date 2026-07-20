"""SQLite persistence for team assets and dead contracts."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional

try:
    from ...auth.policies import normalize_team_code, normalize_team_codes
    from ...domain_rules import parse_bool, parse_float, parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code, normalize_team_codes
    from domain_rules import parse_bool, parse_float, parse_int

from .base import LeagueRepository


class AssetRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        asset_update_fields: Iterable[str],
        contract_seasons: Iterable[int],
        normalize_pick_type: Callable[[Any], str],
        normalize_pick_round: Callable[[Any], str],
        serialize_team_codes: Callable[[Any], Optional[str]],
        normalize_exception_type: Callable[[Any], Optional[str]],
        normalize_dead_type: Callable[[Any], str],
        parse_salary_amount: Callable[[Any], Optional[float]],
        resolve_profile: Callable[..., Optional[int]],
        create_profile: Callable[..., int],
    ) -> None:
        super().__init__(db)
        self._now = now
        self._asset_update_fields = tuple(asset_update_fields)
        self._contract_seasons = tuple(contract_seasons)
        self._normalize_pick_type = normalize_pick_type
        self._normalize_pick_round = normalize_pick_round
        self._serialize_team_codes = serialize_team_codes
        self._normalize_exception_type = normalize_exception_type
        self._normalize_dead_type = normalize_dead_type
        self._parse_salary_amount = parse_salary_amount
        self._resolve_profile = resolve_profile
        self._create_profile = create_profile

    def asset(self, asset_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT a.*, t.code AS team_code, t.name AS team_name
                   FROM assets a JOIN teams t ON t.id = a.team_id WHERE a.id = ?""",
                (asset_id,),
            ).fetchone()
            return dict(row) if row else None

    def dead_contract(self, dead_contract_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT d.*, t.code AS team_code, t.name AS team_name
                   FROM dead_contracts d JOIN teams t ON t.id = d.team_id WHERE d.id = ?""",
                (dead_contract_id,),
            ).fetchone()
            return dict(row) if row else None

    def create_asset(self, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        with self.db.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            row_order = conn.execute(
                "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?", (team["id"],)
            ).fetchone()["mx"]
            timestamp = self._now()
            amount_text = payload.get("amount_text")
            asset_type = str(payload.get("asset_type", "draft_pick"))
            is_pick = asset_type == "draft_pick"
            pick_type = self._normalize_pick_type(payload.get("draft_pick_type")) if is_pick else None
            pick_round = self._normalize_pick_round(payload.get("draft_round")) if is_pick else None
            original_owner = normalize_team_code(payload.get("original_owner")) if is_pick else None
            sold_to = self._serialize_team_codes(payload.get("draft_pick_sold_to")) if is_pick else None
            conditional = self._serialize_team_codes(payload.get("draft_pick_conditional_teams")) if is_pick else None
            exception_type = self._normalize_exception_type(payload.get("exception_type")) if asset_type == "exception" else None
            if is_pick and pick_type not in {"acquired", "sold", "conditional"}:
                original_owner = None
            if is_pick and pick_type != "sold":
                sold_to = None
            if is_pick and pick_type != "conditional":
                conditional = None
            cur = conn.execute(
                """INSERT INTO assets (
                       team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                       draft_pick_type, draft_round, original_owner, exception_type,
                       draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                       draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (team["id"], int(row_order) + 1, asset_type, payload.get("year"), payload.get("label", "New Asset"),
                 payload.get("detail"), amount_text, parse_float(amount_text), pick_type, pick_round, original_owner,
                 exception_type, 1 if is_pick and parse_bool(payload.get("draft_pick_restricted")) else 0,
                 1 if is_pick and parse_bool(payload.get("draft_pick_stepien_restricted")) else 0,
                 1 if is_pick and parse_bool(payload.get("draft_pick_protected")) else 0, sold_to, conditional,
                 1 if is_pick and parse_bool(payload.get("draft_pick_frozen")) else 0, timestamp, timestamp),
            )
            asset_id = int(cur.lastrowid)
            self.sync_draft_pick_identity(conn, asset_id, timestamp)
            conn.commit()
            return asset_id

    def update_asset(self, asset_id: int, payload: Dict[str, Any]) -> bool:
        assignments = []
        values = []
        for field in sorted(self._asset_update_fields):
            if field not in payload:
                continue
            value = payload[field]
            if field == "draft_pick_type":
                value = self._normalize_pick_type(value)
            elif field == "draft_round":
                value = self._normalize_pick_round(value)
            elif field == "original_owner":
                value = normalize_team_code(value)
            elif field in {"draft_pick_sold_to", "draft_pick_conditional_teams"}:
                value = self._serialize_team_codes(value)
            elif field == "exception_type":
                value = self._normalize_exception_type(value)
            elif field in {"draft_pick_restricted", "draft_pick_stepien_restricted", "draft_pick_protected", "draft_pick_frozen"}:
                value = 1 if parse_bool(value) else 0
            assignments.append(f"{field} = ?")
            values.append(value)
        if "amount_text" in payload:
            assignments.append("amount_num = ?")
            values.append(parse_float(payload["amount_text"]))
        if "draft_pick_type" in payload:
            pick_type = self._normalize_pick_type(payload["draft_pick_type"])
            for field, keep_type in (("original_owner", {"acquired", "sold", "conditional"}),
                                     ("draft_pick_sold_to", {"sold"}),
                                     ("draft_pick_conditional_teams", {"conditional"})):
                if pick_type not in keep_type:
                    assignments.append(f"{field} = ?")
                    values.append(None)
        if not assignments:
            return False
        timestamp = self._now()
        assignments.append("updated_at = ?")
        values.extend((timestamp, asset_id))
        with self.db.connect() as conn:
            cur = conn.execute(f"UPDATE assets SET {', '.join(assignments)} WHERE id = ?", values)
            if cur.rowcount > 0:
                self.sync_draft_pick_identity(conn, asset_id, timestamp)
            conn.commit()
            return cur.rowcount > 0

    def create_dead_contract(self, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        with self.db.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            row_order = conn.execute(
                "SELECT COALESCE(MAX(row_order), 0) AS mx FROM dead_contracts WHERE team_id = ?", (team["id"],)
            ).fetchone()["mx"]
            timestamp = self._now()
            salaries = {season: payload.get(f"salary_{season}_text") for season in self._contract_seasons}
            legacy_amount = payload.get("amount_text")
            if legacy_amount is not None and salaries.get(2025) is None:
                salaries[2025] = legacy_amount
            label = str(payload.get("label") or "Dead Contract").strip() or "Dead Contract"
            profile_id = self._resolve_profile(conn, payload, name=label, timestamp=timestamp)
            columns = []
            salary_values = []
            for season in self._contract_seasons:
                columns.extend((f"salary_{season}_text", f"salary_{season}_num"))
                salary_values.extend((salaries[season], self._parse_salary_amount(salaries[season])))
            base_columns = ["team_id", "profile_id", "row_order", "dead_type", "label", "amount_text", "amount_num",
                            "exclude_from_gasto", "exclude_from_cap"]
            all_columns = [*base_columns, *columns, "created_at", "updated_at"]
            values = [team["id"], profile_id, int(row_order) + 1, self._normalize_dead_type(payload.get("dead_type")),
                      label, salaries.get(2025), parse_float(salaries.get(2025)),
                      1 if parse_bool(payload.get("exclude_from_gasto")) else 0,
                      1 if parse_bool(payload.get("exclude_from_cap")) else 0,
                      *salary_values, timestamp, timestamp]
            placeholders = ", ".join("?" for _ in values)
            cur = conn.execute(f"INSERT INTO dead_contracts ({', '.join(all_columns)}) VALUES ({placeholders})", values)
            conn.commit()
            return int(cur.lastrowid)

    def update_dead_contract(self, dead_contract_id: int, payload: Dict[str, Any]) -> bool:
        assignments = []
        values = []
        if "dead_type" in payload:
            assignments.append("dead_type = ?")
            values.append(self._normalize_dead_type(payload.get("dead_type")))
        for field in ("exclude_from_gasto", "exclude_from_cap"):
            if field in payload:
                assignments.append(f"{field} = ?")
                values.append(1 if parse_bool(payload.get(field)) else 0)
        if "label" in payload:
            assignments.append("label = ?")
            values.append(payload["label"])
        legacy_amount = payload.get("amount_text") if "amount_text" in payload else None
        for season in self._contract_seasons:
            field = f"salary_{season}_text"
            if field in payload or (season == 2025 and legacy_amount is not None):
                value = payload[field] if field in payload else legacy_amount
                assignments.extend((f"{field} = ?", f"salary_{season}_num = ?"))
                values.extend((value, parse_float(value)))
        if "salary_2025_text" in payload or "amount_text" in payload:
            amount = payload.get("salary_2025_text") if "salary_2025_text" in payload else legacy_amount
            assignments.extend(("amount_text = ?", "amount_num = ?"))
            values.extend((amount, parse_float(amount)))
        if not assignments:
            return False
        timestamp = self._now()
        assignments.append("updated_at = ?")
        values.append(timestamp)
        with self.db.connect() as conn:
            existing = conn.execute("SELECT profile_id, label FROM dead_contracts WHERE id = ?", (dead_contract_id,)).fetchone()
            if not existing:
                return False
            profile_id = parse_int(existing["profile_id"])
            if profile_id is None:
                name = str(payload.get("label") or existing["label"] or f"Dead Contract {dead_contract_id}").strip()
                profile_id = self._create_profile(conn, name, timestamp=timestamp)
                assignments.append("profile_id = ?")
                values.append(profile_id)
            if "label" in payload and profile_id is not None and str(payload.get("label") or "").strip():
                conn.execute("UPDATE player_profiles SET name = ?, updated_at = ? WHERE id = ?",
                             (str(payload["label"]).strip(), timestamp, profile_id))
            values.append(dead_contract_id)
            cur = conn.execute(f"UPDATE dead_contracts SET {', '.join(assignments)} WHERE id = ?", values)
            conn.commit()
            return cur.rowcount > 0

    def delete_dead_contract(self, dead_contract_id: int) -> bool:
        return self._delete("dead_contracts", dead_contract_id)

    def delete_asset(self, asset_id: int) -> bool:
        return self._delete("assets", asset_id)

    def _delete(self, table: str, entity_id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (entity_id,))
            conn.commit()
            return cur.rowcount > 0

    def upsert_draft_pick_identity(
        self,
        conn: Any,
        draft_year: Any,
        draft_round: Any,
        original_team: Any,
        timestamp: Optional[str] = None,
    ) -> Optional[int]:
        year = parse_int(draft_year)
        round_value = self._normalize_pick_round(draft_round)
        team_code = normalize_team_code(original_team)
        if year is None or round_value not in {"1st", "2nd"} or not team_code:
            return None
        created_at = timestamp or self._now()
        conn.execute(
            """INSERT INTO draft_picks (
                   draft_year, draft_round, original_team, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(draft_year, draft_round, original_team) DO UPDATE SET
                   updated_at = excluded.updated_at""",
            (year, round_value, team_code, created_at, created_at),
        )
        row = conn.execute(
            """SELECT id FROM draft_picks
               WHERE draft_year = ? AND draft_round = ? AND original_team = ?""",
            (year, round_value, team_code),
        ).fetchone()
        return int(row["id"]) if row else None

    def sync_draft_pick_identity(
        self, conn: Any, asset_id: Any, timestamp: Optional[str] = None
    ) -> None:
        parsed_asset_id = parse_int(asset_id)
        if parsed_asset_id is None:
            return
        table_exists = lambda name: conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (name,),
        ).fetchone() is not None
        if not table_exists("draft_picks") or not table_exists("draft_pick_holdings"):
            return
        created_at = timestamp or self._now()
        conn.execute(
            "DELETE FROM draft_pick_holdings WHERE asset_id = ?", (parsed_asset_id,)
        )
        row = conn.execute(
            """SELECT a.*, t.code AS holder_team FROM assets a
               JOIN teams t ON t.id = a.team_id
               WHERE a.id = ? AND a.asset_type = 'draft_pick'""",
            (parsed_asset_id,),
        ).fetchone()
        if not row:
            return
        draft_year = parse_int(row["year"])
        draft_round = self._normalize_pick_round(row["draft_round"])
        holder_team = normalize_team_code(row["holder_team"])
        if draft_year is None or draft_round not in {"1st", "2nd"} or not holder_team:
            return
        pick_type = self._normalize_pick_type(row["draft_pick_type"]) or "own"
        original_owner = normalize_team_code(row["original_owner"])
        if pick_type == "sold":
            original_teams = [original_owner or holder_team]
            holder_teams = normalize_team_codes(row["draft_pick_sold_to"]) or [holder_team]
        elif pick_type == "conditional":
            original_teams = normalize_team_codes(row["draft_pick_conditional_teams"]) or [original_owner or holder_team]
            holder_teams = [holder_team]
        elif pick_type == "acquired":
            original_teams = [original_owner or holder_team]
            holder_teams = [holder_team]
        else:
            original_teams = [holder_team]
            holder_teams = [holder_team]
        conditions = str(row["detail"] or "").strip() or None
        frozen_status = "frozen" if parse_bool(row["draft_pick_frozen"]) else None
        for original_team in sorted({team for team in original_teams if team}):
            draft_pick_id = self.upsert_draft_pick_identity(
                conn, draft_year, draft_round, original_team, created_at
            )
            if draft_pick_id is None:
                continue
            for holding_team in sorted({team for team in holder_teams if team}):
                conn.execute(
                    """INSERT INTO draft_pick_holdings (
                           draft_pick_id, holder_team, asset_id, acquired_transaction_id,
                           conditions, frozen_status, holding_type, created_at, updated_at
                       ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?)
                       ON CONFLICT(draft_pick_id, holder_team, asset_id) DO UPDATE SET
                           conditions = excluded.conditions,
                           frozen_status = excluded.frozen_status,
                           holding_type = excluded.holding_type,
                           updated_at = excluded.updated_at""",
                    (
                        draft_pick_id,
                        holding_team,
                        parsed_asset_id,
                        conditions,
                        frozen_status,
                        pick_type,
                        created_at,
                        created_at,
                    ),
                )

    def _set_matching_frozen(
        self,
        conn: Any,
        team_id: int,
        draft_year: int,
        draft_round: str,
        frozen: bool,
        timestamp: str,
    ) -> Optional[int]:
        normalized_round = self._normalize_pick_round(draft_round)
        row = conn.execute(
            """SELECT id FROM assets
               WHERE team_id = ? AND asset_type = 'draft_pick'
                 AND CAST(COALESCE(year, '') AS INTEGER) = ?
                 AND COALESCE(draft_round, '1st') = ?
               ORDER BY CASE WHEN COALESCE(draft_pick_type, 'own') = 'own'
                             THEN 0 ELSE 1 END, id LIMIT 1""",
            (team_id, draft_year, normalized_round),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE assets SET draft_pick_frozen = ?, updated_at = ? WHERE id = ?",
                (1 if frozen else 0, timestamp, int(row["id"])),
            )
            return int(row["id"])
        if not frozen:
            return None
        max_order = conn.execute(
            "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
            (team_id,),
        ).fetchone()["mx"]
        cur = conn.execute(
            """INSERT INTO assets (
                   team_id, row_order, asset_type, year, label, detail,
                   amount_text, amount_num, draft_pick_type, draft_round,
                   original_owner, exception_type, draft_pick_restricted,
                   draft_pick_stepien_restricted, draft_pick_protected,
                   draft_pick_sold_to, draft_pick_conditional_teams,
                   draft_pick_frozen, created_at, updated_at
               ) VALUES (?, ?, 'draft_pick', ?, ?, '', NULL, NULL, 'own', ?,
                         NULL, NULL, 0, 0, 0, NULL, NULL, 1, ?, ?)""",
            (
                team_id,
                int(max_order) + 1,
                str(draft_year),
                f"{normalized_round} pick",
                normalized_round,
                timestamp,
                timestamp,
            ),
        )
        return int(cur.lastrowid)

    def sync_frozen_asset_flag(
        self,
        conn: Any,
        team_id: int,
        team_code: str,
        draft_year: int,
        draft_round: str,
        timestamp: str,
    ) -> Optional[int]:
        del team_code
        normalized_round = self._normalize_pick_round(draft_round)
        active = conn.execute(
            """SELECT 1 FROM frozen_draft_picks
               WHERE team_id = ? AND draft_year = ? AND draft_round = ? LIMIT 1""",
            (team_id, draft_year, normalized_round),
        ).fetchone()
        return self._set_matching_frozen(
            conn, team_id, draft_year, normalized_round, bool(active), timestamp
        )

    def upsert_frozen_pick_conn(
        self,
        conn: Any,
        team_id: int,
        team_code: str,
        penalty_season_year: int,
        draft_year: int,
        draft_round: str,
        reason: Optional[str],
        notes: Optional[str],
        timestamp: str,
    ) -> Dict[str, Any]:
        normalized_round = self._normalize_pick_round(draft_round)
        conn.execute(
            """INSERT INTO frozen_draft_picks (
                   team_id, penalty_season_year, draft_year, draft_round,
                   reason, notes, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(team_id, penalty_season_year, draft_year, draft_round)
               DO UPDATE SET reason = excluded.reason, notes = excluded.notes,
                             updated_at = excluded.updated_at""",
            (
                team_id,
                penalty_season_year,
                draft_year,
                normalized_round,
                reason,
                notes,
                timestamp,
                timestamp,
            ),
        )
        self.sync_frozen_asset_flag(
            conn, team_id, team_code, draft_year, normalized_round, timestamp
        )
        row = conn.execute(
            """SELECT f.*, t.code AS team_code, t.name AS team_name
               FROM frozen_draft_picks f JOIN teams t ON t.id = f.team_id
               WHERE f.team_id = ? AND f.penalty_season_year = ?
                 AND f.draft_year = ? AND f.draft_round = ?""",
            (team_id, penalty_season_year, draft_year, normalized_round),
        ).fetchone()
        return dict(row)

    def create_frozen_pick(
        self, team_code: str, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        code = normalize_team_code(team_code)
        penalty_season = parse_int(payload.get("penalty_season_year"))
        draft_year = parse_int(payload.get("draft_year"))
        if not code or penalty_season is None or draft_year is None:
            return None
        timestamp = self._now()
        with self.db.connect() as conn:
            team = conn.execute(
                "SELECT id, code FROM teams WHERE code = ?", (code,)
            ).fetchone()
            if not team:
                return None
            row = self.upsert_frozen_pick_conn(
                conn,
                int(team["id"]),
                str(team["code"]),
                penalty_season,
                draft_year,
                payload.get("draft_round") or "1st",
                str(payload.get("reason") or "").strip()
                or "Finalizó por encima del 2do apron",
                str(payload.get("notes") or "").strip() or None,
                timestamp,
            )
            conn.commit()
            return row

    def frozen_pick(self, frozen_pick_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT f.*, t.code AS team_code, t.name AS team_name
                   FROM frozen_draft_picks f JOIN teams t ON t.id = f.team_id
                   WHERE f.id = ?""",
                (frozen_pick_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_frozen_pick(
        self, frozen_pick_id: int, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        timestamp = self._now()
        with self.db.connect() as conn:
            old_row = conn.execute(
                """SELECT f.*, t.code AS team_code FROM frozen_draft_picks f
                   JOIN teams t ON t.id = f.team_id WHERE f.id = ?""",
                (frozen_pick_id,),
            ).fetchone()
            if not old_row:
                return None
            old = dict(old_row)
            penalty_season = parse_int(payload.get("penalty_season_year")) or int(old["penalty_season_year"])
            draft_year = parse_int(payload.get("draft_year")) or int(old["draft_year"])
            draft_round = self._normalize_pick_round(payload.get("draft_round") or old["draft_round"])
            reason = str(payload.get("reason") if "reason" in payload else old.get("reason") or "").strip() or None
            notes = str(payload.get("notes") if "notes" in payload else old.get("notes") or "").strip() or None
            conn.execute(
                """UPDATE frozen_draft_picks SET penalty_season_year = ?,
                          draft_year = ?, draft_round = ?, reason = ?, notes = ?,
                          updated_at = ? WHERE id = ?""",
                (penalty_season, draft_year, draft_round, reason, notes, timestamp, frozen_pick_id),
            )
            self.sync_frozen_asset_flag(
                conn, int(old["team_id"]), str(old["team_code"]),
                int(old["draft_year"]), str(old["draft_round"]), timestamp,
            )
            self.sync_frozen_asset_flag(
                conn, int(old["team_id"]), str(old["team_code"]),
                draft_year, draft_round, timestamp,
            )
            row = conn.execute(
                """SELECT f.*, t.code AS team_code, t.name AS team_name
                   FROM frozen_draft_picks f JOIN teams t ON t.id = f.team_id
                   WHERE f.id = ?""",
                (frozen_pick_id,),
            ).fetchone()
            conn.commit()
            return dict(row) if row else None

    def delete_frozen_pick(self, frozen_pick_id: int) -> Optional[Dict[str, Any]]:
        timestamp = self._now()
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT f.*, t.code AS team_code, t.name AS team_name
                   FROM frozen_draft_picks f JOIN teams t ON t.id = f.team_id
                   WHERE f.id = ?""",
                (frozen_pick_id,),
            ).fetchone()
            if not row:
                return None
            deleted = dict(row)
            conn.execute("DELETE FROM frozen_draft_picks WHERE id = ?", (frozen_pick_id,))
            self.sync_frozen_asset_flag(
                conn,
                int(deleted["team_id"]),
                str(deleted["team_code"]),
                int(deleted["draft_year"]),
                str(deleted.get("draft_round") or "1st"),
                timestamp,
            )
            conn.commit()
            return deleted
