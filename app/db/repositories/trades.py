"""Trade validation and mutation persistence."""
from __future__ import annotations
from contextlib import nullcontext
from dataclasses import dataclass
import hashlib
import json
import sqlite3
from typing import Any, Callable, Dict, List, Optional
try:
    from ...auth.policies import normalize_team_code
    from ...domain.trade_rules import (
        TRADE_MACHINE_MAX_TEAMS, TRADE_MACHINE_MIN_TEAMS, TRADE_PICK_ACTION_SEND,
        TRADE_PICK_ACTION_SWAP, apron_restriction_issues,
        format_trade_money, hard_cap_for_season, hard_cap_issues, minimum_stacking_issue,
        normalize_move_phase, normalize_trade_bucket, roster_count_issues,
        salary_match_profile, trade_balance_snapshot, trade_move_availability,
        trade_roster_limits, trade_rule_checklist, trade_season, trade_thresholds,
    )
    from ...domain_rules import (
        OPEN_ROSTER_SPOT_MINIMUM, apply_salary_floor,
        apron_yos_adjustment, cap_hold_amount, counts_open_roster_minimum,
        is_exhibit10_player, is_two_way_player,
        minimum_contract_team_salary, minimum_salary_2_yos_for_cap,
        open_roster_spot_cap_hold, parse_bool, parse_float, parse_int,
        roster_contract_counts, roster_contract_slot_type,
    )
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain.trade_rules import (
        TRADE_MACHINE_MAX_TEAMS, TRADE_MACHINE_MIN_TEAMS, TRADE_PICK_ACTION_SEND,
        TRADE_PICK_ACTION_SWAP, apron_restriction_issues,
        format_trade_money, hard_cap_for_season, hard_cap_issues, minimum_stacking_issue,
        normalize_move_phase, normalize_trade_bucket, roster_count_issues,
        salary_match_profile, trade_balance_snapshot, trade_move_availability,
        trade_roster_limits, trade_rule_checklist, trade_season, trade_thresholds,
    )
    from domain_rules import (
        OPEN_ROSTER_SPOT_MINIMUM, apply_salary_floor,
        apron_yos_adjustment, cap_hold_amount, counts_open_roster_minimum,
        is_exhibit10_player, is_two_way_player,
        minimum_contract_team_salary, minimum_salary_2_yos_for_cap,
        open_roster_spot_cap_hold, parse_bool, parse_float, parse_int,
        roster_contract_counts, roster_contract_slot_type,
    )
from .base import LeagueRepository

@dataclass(frozen=True)
class TradeOperations:
    get_team: Callable[..., Optional[Dict[str, Any]]]
    team_move_summary: Callable[..., Dict[str, Any]]
    upsert_team_move_log: Callable[..., Any]
    record_transaction: Callable[..., Any]
    normalize_pick_type: Callable[[Any], str]
    normalize_pick_round: Callable[[Any], str]
    normalize_dead_type: Callable[[Any], str]
    dead_contract_excluded_from_cap: Callable[[Dict[str, Any]], bool]
    dead_contract_salary_num: Callable[[Dict[str, Any], int], float]
    row_to_dict: Callable[..., Dict[str, Any]]
    now: Callable[[], str]
    rules_version: str
    contract_min_year: int
    contract_max_year: int
    contract_max_start_year: int
    apply_hard_cap_triggers: Callable[..., List[Dict[str, Any]]]

class TradeRepository(LeagueRepository):
    def __init__(self, db: Any, operations: Optional[TradeOperations] = None) -> None:
        super().__init__(db)
        self.operations = operations

    def _operations(self) -> TradeOperations:
        if not self.operations:
            raise RuntimeError("trade_repository_not_configured")
        return self.operations

    def transaction(self, mode: str = "IMMEDIATE") -> Any:
        return self.db.transaction(mode)

    def settings(self) -> Dict[str, str]:
        with self.db.connect() as conn:
            return {str(row["key"]): str(row["value"]) for row in conn.execute(
                "SELECT key, value FROM app_settings"
            ).fetchall()}

    @staticmethod
    def create_command_run_conn(
        conn: sqlite3.Connection,
        *,
        workflow_run_id: str,
        actor_user_id: Any,
        actor_email: Any,
        actor_name: Any,
        metadata_json: str,
        timestamp: str,
    ) -> None:
        conn.execute(
            """INSERT INTO workflow_runs (
                   id, workflow_type, state, actor_user_id, actor_email, actor_name,
                   reason, metadata_json, created_at, updated_at
               ) VALUES (?, 'trade_command', 'draft', ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow_run_id, actor_user_id, actor_email, actor_name,
                "trade_command_created", metadata_json, timestamp, timestamp,
            ),
        )

    @staticmethod
    def settings_conn(conn: sqlite3.Connection) -> Dict[str, str]:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    @staticmethod
    def workflow_state_conn(conn: sqlite3.Connection, workflow_run_id: str) -> str:
        row = conn.execute(
            "SELECT state FROM workflow_runs WHERE id = ?", (workflow_run_id,)
        ).fetchone()
        return str(row["state"] or "") if row else ""
    def _clean_trade_ids(self, values: Any) -> List[int]:
        if not isinstance(values, list):
            return []
        out: List[int] = []
        seen: set[int] = set()
        for value in values:
            parsed = parse_int(str(value))
            if parsed is None or parsed <= 0 or parsed in seen:
                continue
            seen.add(parsed)
            out.append(parsed)
        return out

    def _pick_actual_owner(self, asset_row: Dict[str, Any], source_team_code: str) -> str:
        if self.operations.normalize_pick_type(asset_row.get("draft_pick_type")) == "acquired":
            return normalize_team_code(asset_row.get("original_owner")) or source_team_code
        return source_team_code

    def _insert_trade_move_logs(
        self,
        conn: sqlite3.Connection,
        *,
        team_id: int,
        season_year: int,
        requested_bucket: str,
        move_count: int,
        source_ref: Optional[str],
        note: Optional[str],
        details: Optional[Dict[str, Any]],
        settings: Dict[str, str],
    ) -> None:
        remaining = max(0, int(move_count or 0))
        if not remaining:
            return
        bucket_key = normalize_trade_bucket(requested_bucket)
        allocations: List[tuple[str, int]] = []
        if bucket_key == "post30":
            move_summary = self.team_move_summary(conn, int(team_id), int(season_year), settings)
            pre_remaining = max(0, parse_int(move_summary.get("remaining_pre30")) or 0)
            pre_delta = min(remaining, pre_remaining)
            if pre_delta:
                allocations.append(("pre30", pre_delta))
                remaining -= pre_delta
            if remaining:
                allocations.append(("post30", remaining))
        else:
            allocations.append(("pre30", remaining))

        for allocated_bucket, delta in allocations:
            allocated_details = {
                **(details or {}),
                "requested_bucket": bucket_key,
                "allocated_bucket": allocated_bucket,
            }
            self.upsert_team_move_log(
                conn,
                team_id=int(team_id),
                season_year=int(season_year),
                bucket=allocated_bucket,
                delta=int(delta),
                source_type="trade",
                source_ref=source_ref,
                note=note,
                details=allocated_details,
            )

    def team_move_log_rows(self, conn: Any, team_id: int, season_year: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """SELECT id, season_year, bucket, delta, source_type, source_ref,
                      note, detail_json, created_at FROM team_move_logs
               WHERE team_id = ? AND season_year = ? ORDER BY id DESC""",
            (team_id, season_year),
        ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            try:
                row["details"] = json.loads(row.get("detail_json") or "{}")
            except json.JSONDecodeError:
                row["details"] = {}
        return result

    def team_move_summary(
        self, conn: Any, team_id: int, season_year: int, settings: Dict[str, str]
    ) -> Dict[str, Any]:
        limit_pre30 = max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0)
        limit_post30 = max(0, parse_int(settings.get("trade_move_limit_post30")) or 0)
        rows = self.team_move_log_rows(conn, team_id, season_year)
        used_pre30 = sum(int(row.get("delta") or 0) for row in rows if normalize_trade_bucket(row.get("bucket")) == "pre30")
        used_post30 = sum(int(row.get("delta") or 0) for row in rows if normalize_trade_bucket(row.get("bucket")) == "post30")
        return {
            "season_year": season_year,
            "phase": normalize_move_phase(settings.get("trade_move_phase")),
            "limit_pre30": limit_pre30,
            "limit_post30": limit_post30,
            "used_pre30": used_pre30,
            "used_post30": used_post30,
            "remaining_pre30": limit_pre30 - used_pre30,
            "remaining_post30": limit_post30 - used_post30,
            "log": rows,
        }

    def upsert_team_move_log(
        self, conn: Any, *, team_id: int, season_year: int, bucket: str,
        delta: int, source_type: str, source_ref: Optional[str],
        note: Optional[str], details: Optional[Dict[str, Any]],
    ) -> None:
        conn.execute(
            """INSERT INTO team_move_logs (
                   team_id, season_year, bucket, delta, source_type, source_ref,
                   note, detail_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (team_id, season_year, normalize_trade_bucket(bucket), delta,
             source_type, source_ref, note,
             json.dumps(details or {}, ensure_ascii=True), self._operations().now()),
        )

    def adjust_team_move_remaining(
        self, team_code: str, season_year: int, bucket: str,
        target_remaining: int, actor_note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        bucket_key = normalize_trade_bucket(bucket)
        target = max(0, int(target_remaining))
        with self.db.connect() as conn:
            team = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings")}
            summary = self.team_move_summary(conn, int(team["id"]), season_year, settings)
            limit = int(summary[f"limit_{bucket_key}"])
            current = int(summary[f"remaining_{bucket_key}"])
            delta = (limit - target) - (limit - current)
            if delta:
                self.upsert_team_move_log(
                    conn, team_id=int(team["id"]), season_year=season_year,
                    bucket=bucket_key, delta=delta, source_type="manual_adjustment",
                    source_ref=None, note=actor_note or "Manual adjustment",
                    details={"target_remaining": target},
                )
                conn.commit()
                current = int(self.team_move_summary(conn, int(team["id"]), season_year, settings)[f"remaining_{bucket_key}"])
            return {"team_code": team["code"], "bucket": bucket_key, "remaining": current, "delta": delta}

    def audit_snapshot(
        self, team_codes: List[str], player_ids: Optional[List[Any]] = None,
        asset_ids: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        def clean_ids(values: Optional[List[Any]]) -> List[int]:
            return list(dict.fromkeys(parsed for value in (values or [])
                                      if (parsed := parse_int(str(value))) is not None and parsed > 0))
        teams = list(dict.fromkeys(code for value in (team_codes or [])
                                   if (code := normalize_team_code(value))))
        players = clean_ids(player_ids)
        assets = clean_ids(asset_ids)
        snapshot: Dict[str, Any] = {"teams": [], "players": [], "assets": []}
        with self.db.connect() as conn:
            for code in teams:
                row = conn.execute(
                    """SELECT t.id, t.code, t.gm, t.cash_received, t.cash_sent,
                              t.apron_hard_cap,
                              COALESCE(SUM(CASE WHEN p.id IS NULL THEN 0
                                WHEN COALESCE(p.is_two_way, 0) = 1 OR UPPER(COALESCE(p.bird_rights, '')) = 'TW'
                                THEN 0 ELSE 1 END), 0) AS standard_contracts,
                              COALESCE(SUM(CASE WHEN p.id IS NULL THEN 0
                                WHEN COALESCE(p.is_two_way, 0) = 1 OR UPPER(COALESCE(p.bird_rights, '')) = 'TW'
                                THEN 1 ELSE 0 END), 0) AS two_way_contracts
                       FROM teams t LEFT JOIN players p ON p.team_id = t.id
                       WHERE t.code = ? GROUP BY t.id""", (code,)
                ).fetchone()
                if row:
                    snapshot["teams"].append(dict(row))
            if players:
                marks = ",".join("?" for _ in players)
                rows = conn.execute(
                    f"""SELECT p.id, p.profile_id, COALESCE(pp.name, p.name) AS name,
                               t.code AS team_code, p.position, p.bird_rights, p.rating,
                               p.years_left, p.is_two_way FROM players p
                        LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                        JOIN teams t ON t.id = p.team_id WHERE p.id IN ({marks}) ORDER BY p.id""", players
                ).fetchall()
                snapshot["players"] = [dict(row) for row in rows]
            if assets:
                marks = ",".join("?" for _ in assets)
                rows = conn.execute(
                    f"""SELECT a.id, t.code AS team_code, a.asset_type, a.year, a.label,
                               a.draft_pick_type, a.draft_round, a.original_owner,
                               a.draft_pick_sold_to, a.draft_pick_conditional_teams, a.detail
                        FROM assets a JOIN teams t ON t.id = a.team_id
                        WHERE a.id IN ({marks}) ORDER BY a.id""", assets
                ).fetchall()
                snapshot["assets"] = [dict(row) for row in rows]
        return snapshot






    def _trade_machine_team_balances(
        self,
        team_data: Dict[str, Any],
        season: int,
        salary_cap: float,
        settings: Dict[str, str],
    ) -> Dict[str, float]:
        players = team_data.get("players") or []
        dead_contracts = team_data.get("dead_contracts") or []

        def player_cap_value(player: Dict[str, Any]) -> float:
            hold = cap_hold_amount(player, season, settings, salary_cap)
            if hold > 0:
                return hold
            if is_two_way_player(player) or is_exhibit10_player(player):
                return 0.0
            return minimum_contract_team_salary(player, season, salary_cap)

        def player_apron_value(player: Dict[str, Any]) -> float:
            if cap_hold_amount(player, season, settings, salary_cap) > 0:
                return 0.0
            if is_two_way_player(player) or is_exhibit10_player(player):
                return 0.0
            return minimum_contract_team_salary(player, season, salary_cap) + apron_yos_adjustment(player, season, salary_cap)

        dead_cap_team_salary = sum(
            self.operations.dead_contract_salary_num(d, season)
            for d in dead_contracts
            if self.operations.normalize_dead_type(d.get("dead_type")) in {"normal", "draft_hold"}
            and not self.operations.dead_contract_excluded_from_cap(d)
        )
        dead_cap_apron = sum(
            self.operations.dead_contract_salary_num(d, season)
            for d in dead_contracts
            if self.operations.normalize_dead_type(d.get("dead_type")) == "normal"
            and not self.operations.dead_contract_excluded_from_cap(d)
        )
        open_roster_hold = open_roster_spot_cap_hold(players, season, settings, salary_cap)
        cap_total_before_floor = sum(player_cap_value(p) for p in players) + dead_cap_team_salary + float(open_roster_hold.get("amount") or 0.0)
        cap_total = apply_salary_floor(settings, season, salary_cap, cap_total_before_floor)
        return {
            "cap_total": cap_total,
            "cap_total_before_floor": cap_total_before_floor,
            "salary_floor_adjustment": max(0.0, cap_total - cap_total_before_floor),
            "apron_account": sum(player_apron_value(p) for p in players) + dead_cap_apron,
            "open_roster_spot_cap_hold": float(open_roster_hold.get("amount") or 0.0),
            "open_roster_spot_count": float(open_roster_hold.get("open_spots") or 0.0),
            "open_roster_spot_roster_count": float(open_roster_hold.get("roster_count") or 0.0),
            "open_roster_spot_minimum_salary": float(open_roster_hold.get("minimum_salary") or 0.0),
        }

    def _trade_machine_flow_skeleton(
        self,
        code: str,
        team_data: Dict[str, Any],
        season: int,
        thresholds: Dict[str, float],
        settings: Dict[str, str],
    ) -> Dict[str, Any]:
        balances = self._trade_machine_team_balances(team_data, season, thresholds["salaryCap"], settings)
        players = team_data.get("players") or []
        roster_counts = roster_contract_counts(players, season)
        standard_count = roster_counts["standard"]
        two_way_count = roster_counts["two_way"]
        before_cap = float(balances["cap_total"])
        before_raw_cap = float(balances.get("cap_total_before_floor") or before_cap)
        before_apron = float(balances["apron_account"])
        return {
            "code": code,
            "beforeCap": before_cap,
            "beforeRawCap": before_raw_cap,
            "beforeSalaryFloorAdjustment": float(balances.get("salary_floor_adjustment") or 0.0),
            "beforeApronAccount": before_apron,
            "incomingSalary": 0.0,
            "outgoingSalary": 0.0,
            "incomingMatchingSalary": 0.0,
            "outgoingMatchingSalary": 0.0,
            "incomingCash": 0.0,
            "outgoingCash": 0.0,
            "incomingCapSalary": 0.0,
            "outgoingCapSalary": 0.0,
            "incomingApronSalary": 0.0,
            "outgoingApronSalary": 0.0,
            "incomingAssets": [],
            "outgoingAssets": [],
            "postCap": before_cap,
            "postRawCap": before_raw_cap,
            "postSalaryFloorAdjustment": float(balances.get("salary_floor_adjustment") or 0.0),
            "postApronAccount": before_apron,
            "beforeRosterStandard": standard_count,
            "beforeRosterTwoWay": two_way_count,
            "postRosterStandard": standard_count,
            "postRosterTwoWay": two_way_count,
            "beforeOpenRosterSpotCapHold": float(balances.get("open_roster_spot_cap_hold") or 0.0),
            "postOpenRosterSpotCapHold": float(balances.get("open_roster_spot_cap_hold") or 0.0),
            "beforeOpenRosterSpotCount": int(balances.get("open_roster_spot_count") or 0),
            "postOpenRosterSpotCount": int(balances.get("open_roster_spot_count") or 0),
            "beforeOpenRosterSpotRosterCount": int(balances.get("open_roster_spot_roster_count") or 0),
            "postOpenRosterSpotRosterCount": int(balances.get("open_roster_spot_roster_count") or 0),
            "openRosterSpotMinimumSalary": float(balances.get("open_roster_spot_minimum_salary") or 0.0),
            "beforeBalances": trade_balance_snapshot(thresholds, before_cap, before_apron),
            "afterBalances": trade_balance_snapshot(thresholds, before_cap, before_apron),
        }


    def _trade_machine_pick_owner(self, asset: Dict[str, Any], team_code: str) -> str:
        if self.operations.normalize_pick_type(asset.get("draft_pick_type")) == "conditional":
            raw = asset.get("draft_pick_conditional_teams")
            try:
                teams = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                teams = []
            if isinstance(teams, list):
                for item in teams:
                    code = normalize_team_code(item)
                    if code:
                        return code
        return self._pick_actual_owner(asset, team_code)

    def _trade_machine_pick_label(self, asset: Dict[str, Any], team_code: str) -> str:
        year = parse_int(asset.get("year"))
        year_label = str(year) if year is not None else "Sin año"
        owner = self._trade_machine_pick_owner(asset, team_code) or team_code
        return f"{year_label} {self.operations.normalize_pick_round(asset.get('draft_round')).upper()} {owner}"

    def _trade_machine_asset_meta(
        self,
        team_data: Dict[str, Any],
        from_team: str,
        asset_type: str,
        asset_id: int,
        season: int,
        thresholds: Dict[str, float],
        settings: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        if asset_type == "player":
            player = next((p for p in team_data.get("players") or [] if parse_int(p.get("id")) == asset_id), None)
            if not player:
                return None
            hold = cap_hold_amount(player, season, settings, thresholds["salaryCap"])
            salary = 0.0 if is_exhibit10_player(player) else minimum_contract_team_salary(player, season, thresholds["salaryCap"])
            cap_salary = (
                hold
                if hold > 0
                else 0.0
                if is_two_way_player(player) or is_exhibit10_player(player)
                else minimum_contract_team_salary(player, season, thresholds["salaryCap"])
            )
            apron_salary = (
                0.0
                if hold > 0 or is_two_way_player(player) or is_exhibit10_player(player)
                else minimum_contract_team_salary(player, season, thresholds["salaryCap"])
                + apron_yos_adjustment(player, season, thresholds["salaryCap"])
            )
            minimum_cutoff = minimum_salary_2_yos_for_cap(thresholds["salaryCap"])
            roster_slot = roster_contract_slot_type(player, season)
            counts_open_minimum = counts_open_roster_minimum(player, season, settings, thresholds["salaryCap"])
            return {
                "key": f"player:{from_team}:{asset_id}",
                "type": "player",
                "id": asset_id,
                "fromTeam": from_team,
                "label": player.get("name") or "Jugador",
                "detail": " · ".join(str(part) for part in [player.get("position"), player.get("bird_rights")] if part),
                "salary": salary,
                "capSalary": cap_salary,
                "apronSalary": apron_salary,
                "rating": parse_float(player.get("rating")) or 0.0,
                "ratingText": str(player.get("rating") or "").strip(),
                "isMinimumContract": salary > 0 and salary <= minimum_cutoff,
                "isTwoWay": is_two_way_player(player),
                "isExhibit10": is_exhibit10_player(player),
                "rosterSlot": roster_slot,
                "countsOpenRosterMinimum": counts_open_minimum,
                "restricted": False,
                "protected": False,
                "conditional": False,
            }
        if asset_type == "pick":
            pick = next(
                (
                    a for a in team_data.get("assets") or []
                    if a.get("asset_type") == "draft_pick" and parse_int(a.get("id")) == asset_id
                ),
                None,
            )
            if not pick:
                return None
            return {
                "key": f"pick:{from_team}:{asset_id}",
                "type": "pick",
                "id": asset_id,
                "fromTeam": from_team,
                "label": self._trade_machine_pick_label(pick, from_team),
                "detail": str(pick.get("detail") or "").strip(),
                "salary": 0.0,
                "capSalary": 0.0,
                "apronSalary": 0.0,
                "restricted": parse_bool(pick.get("draft_pick_restricted")),
                "stepienRestricted": parse_bool(pick.get("draft_pick_stepien_restricted")),
                "protected": parse_bool(pick.get("draft_pick_protected")),
                "frozen": parse_bool(pick.get("draft_pick_frozen")),
                "conditional": self.operations.normalize_pick_type(pick.get("draft_pick_type")) == "conditional",
                "sold": self.operations.normalize_pick_type(pick.get("draft_pick_type")) == "sold",
                "round": self.operations.normalize_pick_round(pick.get("draft_round")),
                "year": parse_int(pick.get("year")),
            }
        if asset_type == "right":
            right = next(
                (
                    a for a in team_data.get("assets") or []
                    if a.get("asset_type") == "player_right" and parse_int(a.get("id")) == asset_id
                ),
                None,
            )
            if not right:
                return None
            return {
                "key": f"right:{from_team}:{asset_id}",
                "type": "right",
                "id": asset_id,
                "fromTeam": from_team,
                "label": right.get("label") or "Derecho de jugador",
                "detail": str(right.get("detail") or "").strip(),
                "salary": 0.0,
                "capSalary": 0.0,
                "apronSalary": 0.0,
                "restricted": False,
                "protected": False,
                "conditional": False,
            }
        return None

    def _trade_machine_pick_action(self, value: Any) -> str:
        return TRADE_PICK_ACTION_SWAP if str(value or "").strip() == TRADE_PICK_ACTION_SWAP else TRADE_PICK_ACTION_SEND

    def _trade_process_pick_actions(self, value: Any) -> Dict[int, str]:
        actions: Dict[int, str] = {}
        if isinstance(value, dict):
            items = value.items()
        elif isinstance(value, list):
            items = []
            for item in value:
                if isinstance(item, dict):
                    items.append((item.get("id") or item.get("asset_id"), item.get("action") or item.get("pick_action") or item.get("pickAction")))
        else:
            items = []
        for raw_id, raw_action in items:
            pick_id = parse_int(raw_id)
            if pick_id is None:
                continue
            actions[pick_id] = self._trade_machine_pick_action(raw_action)
        return actions

    def _trade_machine_asset_for_selection(self, meta: Dict[str, Any], selection: Dict[str, Any]) -> Dict[str, Any]:
        if meta.get("type") != "pick":
            return dict(meta)
        pick_action = self._trade_machine_pick_action(selection.get("pick_action") or selection.get("pickAction"))
        asset = dict(meta)
        asset["pickAction"] = pick_action
        if pick_action == TRADE_PICK_ACTION_SWAP:
            asset["type"] = "swap_right"
            asset["label"] = f"Swap {asset.get('label') or ''}".strip()
            detail = str(asset.get("detail") or "").strip()
            asset["detail"] = " · ".join(part for part in [detail, "La ronda no cambia de dueño; se venden derechos de intercambio."] if part)
        return asset

    def _trade_asset_counts_as_move(self, asset: Dict[str, Any], season_year: int) -> bool:
        if not parse_bool(asset.get("countsMove", True)):
            return False
        asset_type = str(asset.get("type") or asset.get("asset_type") or "").strip().lower()
        if asset_type == "player":
            return True
        if asset_type not in {"pick", "draft_pick"}:
            return False
        if self._trade_machine_pick_action(asset.get("pickAction") or asset.get("pick_action")) == TRADE_PICK_ACTION_SWAP:
            return False
        pick_year = parse_int(asset.get("year"))
        pick_round = self.operations.normalize_pick_round(asset.get("round") or asset.get("draft_round"))
        return pick_round == "1st" and pick_year == int(season_year) + 1

    def _trade_flow_move_count(self, flow: Dict[str, Any], season_year: int) -> int:
        outgoing = sum(
            1 for asset in flow.get("outgoingAssets") or []
            if self._trade_asset_counts_as_move(asset, season_year)
        )
        incoming = sum(
            1 for asset in flow.get("incomingAssets") or []
            if self._trade_asset_counts_as_move(asset, season_year)
        )
        return outgoing + incoming

    def normalize_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_teams = payload.get("teams")
        if raw_teams is None:
            raw_teams = payload.get("selectedTeams")
        teams: List[str] = []
        seen: set[str] = set()
        if isinstance(raw_teams, list):
            for item in raw_teams:
                code = normalize_team_code(item)
                if code and code not in seen:
                    seen.add(code)
                    teams.append(code)
        selections: List[Dict[str, Any]] = []
        raw_selections = payload.get("selections")
        if isinstance(raw_selections, dict):
            iterable = raw_selections.values()
        elif isinstance(raw_selections, list):
            iterable = raw_selections
        else:
            iterable = []
        for item in iterable:
            if not isinstance(item, dict):
                continue
            asset_type = str(item.get("type") or item.get("asset_type") or "").strip().lower()
            if asset_type not in {"player", "pick", "right"}:
                continue
            asset_id = parse_int(item.get("id") or item.get("asset_id"))
            from_team = normalize_team_code(item.get("from_team") or item.get("fromTeam"))
            to_team = normalize_team_code(item.get("to_team") or item.get("toTeam"))
            if asset_id is None:
                continue
            selections.append(
                {
                    "type": asset_type,
                    "id": asset_id,
                    "fromTeam": from_team,
                    "toTeam": to_team,
                    "pickAction": self._trade_machine_pick_action(item.get("pick_action") or item.get("pickAction")),
                    "countsMove": False if parse_bool(item.get("no_count") or item.get("noCount")) else True,
                }
            )
            if from_team and from_team not in seen:
                seen.add(from_team)
                teams.append(from_team)
            if to_team and to_team not in seen:
                seen.add(to_team)
                teams.append(to_team)
        cash_transfers: List[Dict[str, Any]] = []
        raw_cash = payload.get("cash")
        if raw_cash is None:
            raw_cash = payload.get("cash_considerations") or payload.get("cashConsiderations")
        if isinstance(raw_cash, dict):
            cash_iterable = raw_cash.values()
        elif isinstance(raw_cash, list):
            cash_iterable = raw_cash
        else:
            cash_iterable = []
        for item in cash_iterable:
            if not isinstance(item, dict):
                continue
            from_team = normalize_team_code(item.get("from_team") or item.get("fromTeam"))
            to_team = normalize_team_code(item.get("to_team") or item.get("toTeam"))
            amount = parse_float(item.get("amount"))
            if amount is None:
                amount = parse_float(item.get("cash_amount") or item.get("cashAmount"))
            if amount is None or amount <= 0:
                continue
            cash_transfers.append(
                {
                    "fromTeam": from_team,
                    "toTeam": to_team,
                    "amount": float(amount),
                }
            )
            if from_team and from_team not in seen:
                seen.add(from_team)
                teams.append(from_team)
            if to_team and to_team not in seen:
                seen.add(to_team)
                teams.append(to_team)
        return {"teams": teams, "selections": selections, "cash": cash_transfers}

    def _trade_validation_fingerprint(
        self,
        payload: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> str:
        """Sign canonical inputs plus the authoritative result/state they produced."""
        normalized = self.normalize_request(payload)
        settings = self.settings()
        season = parse_int(payload.get("season")) or parse_int(settings.get("current_year")) or 2025
        material = {
            "rules_version": self.operations.rules_version,
            "season": int(season),
            "trade_bucket": normalize_trade_bucket(
                payload.get("trade_bucket") or settings.get("trade_move_phase")
            ),
            "request": normalized,
            "result": {
                key: value
                for key, value in validation.items()
                if key not in {"validation_hash", "rules_version"}
            },
        }
        encoded = json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _signed_trade_validation(
        self,
        payload: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = dict(validation)
        result["rules_version"] = self.operations.rules_version
        result["validation_hash"] = self._trade_validation_fingerprint(payload, result)
        return result


    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        settings = self.settings()
        season = trade_season(
            payload,
            settings,
            contract_min_year=self.operations.contract_min_year,
            contract_max_year=self.operations.contract_max_year,
            contract_max_start_year=self.operations.contract_max_start_year,
        )
        thresholds = trade_thresholds(settings, season)
        roster_limits = trade_roster_limits(settings)
        normalized = self.normalize_request(payload)
        teams = normalized["teams"]
        selections = normalized["selections"]
        cash_transfers = normalized.get("cash") or []
        issues: List[Dict[str, Any]] = []
        if len(teams) < TRADE_MACHINE_MIN_TEAMS:
            issues.append({"severity": "illegal", "rule": "setup", "message": "Selecciona al menos dos equipos."})
        if len(teams) > TRADE_MACHINE_MAX_TEAMS:
            issues.append({"severity": "illegal", "rule": "setup", "message": "Selecciona seis equipos o menos."})
        if not selections and not cash_transfers:
            issues.append({"severity": "warning", "rule": "setup", "message": "Selecciona al menos un activo."})

        team_data_by_code: Dict[str, Dict[str, Any]] = {}
        for code in teams:
            data = self.operations.get_team(code, move_season_year=season)
            if not data:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": code, "message": "Equipo no encontrado."})
                continue
            team_data_by_code[code] = data

        flows = {
            code: self._trade_machine_flow_skeleton(code, data, season, thresholds, settings)
            for code, data in team_data_by_code.items()
        }
        selected_count = 0
        any_player_selected = False
        selected_keys: set[str] = set()
        selected_assets: List[Dict[str, Any]] = []
        for selection in selections:
            from_team = selection.get("fromTeam")
            to_team = selection.get("toTeam")
            asset_type = selection.get("type")
            asset_id = parse_int(selection.get("id"))
            if not from_team or from_team not in team_data_by_code:
                issues.append({"severity": "illegal", "rule": "setup", "message": "Un activo seleccionado no tiene equipo origen válido."})
                continue
            if not to_team or to_team not in team_data_by_code or to_team == from_team:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": "Un activo seleccionado necesita un equipo de destino válido."})
                continue
            if asset_id is None:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": "Un activo seleccionado tiene un identificador inválido."})
                continue
            meta = self._trade_machine_asset_meta(team_data_by_code[from_team], from_team, str(asset_type), asset_id, season, thresholds, settings)
            if not meta:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": "Un activo seleccionado ya no está disponible."})
                continue
            if meta["key"] in selected_keys:
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": f"{meta.get('label')} está seleccionado más de una vez."})
                continue
            selected_keys.add(meta["key"])
            selected_count += 1
            selected = self._trade_machine_asset_for_selection(meta, selection)
            selected["toTeam"] = to_team
            selected["fromTeam"] = from_team
            selected["countsMove"] = bool(selection.get("countsMove", True))
            selected_assets.append(selected)
            if meta.get("sold"):
                issues.append({"severity": "illegal", "rule": "setup", "teamCode": from_team, "message": f"{meta.get('label')} ya está vendida y no se puede mover."})
            if meta.get("frozen"):
                issues.append({"severity": "illegal", "rule": "frozen_pick", "teamCode": from_team, "message": f"{meta.get('label')} está congelada por penalización del 2do apron y no se puede mover."})
            if meta.get("restricted"):
                issues.append({"severity": "illegal", "rule": "restricted_pick", "teamCode": from_team, "message": f"{meta.get('label')} está restringida por protecciones previas y no se puede mover ni vender como swap."})
            if meta.get("stepienRestricted") and selected.get("pickAction") != TRADE_PICK_ACTION_SWAP:
                issues.append({"severity": "illegal", "rule": "restricted_pick", "teamCode": from_team, "message": f"{meta.get('label')} está restringida por Stepien y solo puede venderse como derecho de swap."})
            if meta.get("conditional") or meta.get("protected"):
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": from_team, "message": f"{meta.get('label')} necesita revisión manual por condiciones/protecciones."})
            if meta.get("type") == "pick" and selected.get("pickAction") == TRADE_PICK_ACTION_SWAP:
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": from_team, "message": f"{meta.get('label')}: derecho de swap seleccionado; revisa protecciones, prioridad y equipo que acabaría eligiendo."})
            elif meta.get("type") == "pick" and meta.get("round") == "1st" and not meta.get("stepienRestricted"):
                issues.append({"severity": "warning", "rule": "manual_review", "teamCode": from_team, "message": f"{meta.get('label')} necesita revisión de la regla Stepien."})
            if selected.get("type") == "player":
                any_player_selected = True
            salary = float(selected.get("salary") or 0.0)
            matching_salary = 0.0 if selected.get("isMinimumContract") else salary
            cap_salary = float(selected.get("capSalary") if selected.get("capSalary") is not None else salary)
            apron_salary = float(selected.get("apronSalary") if selected.get("apronSalary") is not None else cap_salary)
            from_flow = flows[from_team]
            to_flow = flows[to_team]
            from_flow["outgoingSalary"] += salary
            from_flow["outgoingMatchingSalary"] += salary
            from_flow["outgoingCapSalary"] += cap_salary
            from_flow["outgoingApronSalary"] += apron_salary
            from_flow["outgoingAssets"].append({**selected, "toTeam": to_team})
            to_flow["incomingSalary"] += salary
            to_flow["incomingMatchingSalary"] += matching_salary
            to_flow["incomingCapSalary"] += cap_salary
            to_flow["incomingApronSalary"] += apron_salary
            to_flow["incomingAssets"].append({**selected, "fromTeam": from_team})
            if selected.get("type") == "player":
                roster_slot = selected.get("rosterSlot")
                if roster_slot == "two_way":
                    from_flow["postRosterTwoWay"] -= 1
                    to_flow["postRosterTwoWay"] += 1
                elif roster_slot == "standard":
                    from_flow["postRosterStandard"] -= 1
                    to_flow["postRosterStandard"] += 1
                if selected.get("countsOpenRosterMinimum"):
                    from_flow["postOpenRosterSpotRosterCount"] -= 1
                    to_flow["postOpenRosterSpotRosterCount"] += 1

        for idx, transfer in enumerate(cash_transfers):
            from_team = transfer.get("fromTeam")
            to_team = transfer.get("toTeam")
            amount = float(transfer.get("amount") or 0.0)
            if not from_team or from_team not in team_data_by_code:
                issues.append({"severity": "illegal", "rule": "cash", "message": "Una cantidad de cash no tiene equipo origen válido."})
                continue
            if not to_team or to_team not in team_data_by_code or to_team == from_team:
                issues.append({"severity": "illegal", "rule": "cash", "teamCode": from_team, "message": "Una cantidad de cash necesita un equipo de destino válido."})
                continue
            if amount <= 0:
                issues.append({"severity": "illegal", "rule": "cash", "teamCode": from_team, "message": "La cantidad de cash debe ser mayor que cero."})
                continue
            selected_count += 1
            asset = {
                "key": f"cash:{from_team}:{to_team}:{idx}",
                "type": "cash",
                "fromTeam": from_team,
                "toTeam": to_team,
                "label": "Cash considerations",
                "detail": format_trade_money(amount),
                "salary": 0.0,
                "capSalary": 0.0,
                "apronSalary": 0.0,
                "cashAmount": amount,
                "countsMove": False,
            }
            flows[from_team]["outgoingCash"] += amount
            flows[from_team]["outgoingAssets"].append(dict(asset))
            flows[to_team]["incomingCash"] += amount
            flows[to_team]["incomingAssets"].append(dict(asset))

        for flow in flows.values():
            post_open_roster_count = max(0, int(flow.get("postOpenRosterSpotRosterCount") or 0))
            post_open_spots = max(0, OPEN_ROSTER_SPOT_MINIMUM - post_open_roster_count)
            post_open_hold = float(post_open_spots) * float(flow.get("openRosterSpotMinimumSalary") or 0.0)
            flow["postOpenRosterSpotRosterCount"] = post_open_roster_count
            flow["postOpenRosterSpotCount"] = post_open_spots
            flow["postOpenRosterSpotCapHold"] = post_open_hold
            open_hold_delta = post_open_hold - float(flow.get("beforeOpenRosterSpotCapHold") or 0.0)
            post_raw_cap = float(flow.get("beforeRawCap") or flow.get("beforeCap") or 0.0) + flow["incomingCapSalary"] - flow["outgoingCapSalary"] + open_hold_delta
            flow["postRawCap"] = post_raw_cap
            flow["postCap"] = apply_salary_floor(settings, season, thresholds["salaryCap"], post_raw_cap)
            flow["postSalaryFloorAdjustment"] = max(0.0, flow["postCap"] - post_raw_cap)
            flow["postApronAccount"] = flow["beforeApronAccount"] + flow["incomingApronSalary"] - flow["outgoingApronSalary"]
            flow["afterBalances"] = trade_balance_snapshot(thresholds, flow["postCap"], flow["postApronAccount"])

        if any_player_selected:
            issues.append({
                "severity": "warning",
                "rule": "manual_review",
                "message": "Revisar manualmente si algún jugador es extendido o BYC/S&T: la máquina todavía no tiene campos estructurados para aplicar salario promedio, 30 partidos o 50%/100%.",
            })

        salary_pass_messages: List[str] = []
        for code in teams:
            flow = flows.get(code)
            data = team_data_by_code.get(code)
            if not flow or not data:
                continue
            if len(teams) > 2:
                incoming_count = len(flow.get("incomingAssets") or [])
                outgoing_count = len(flow.get("outgoingAssets") or [])
                if not incoming_count and not outgoing_count:
                    issues.append({"severity": "illegal", "rule": "multi_team", "teamCode": code, "message": "En un traspaso de más de dos equipos, cada equipo seleccionado debe enviar y recibir algo."})
                elif not incoming_count or not outgoing_count:
                    issues.append({
                        "severity": "illegal",
                        "rule": "multi_team",
                        "teamCode": code,
                        "message": f"En un traspaso de más de dos equipos debe enviar y recibir algo; ahora {'recibe' if incoming_count else 'no recibe'} y {'envía' if outgoing_count else 'no envía'}.",
                    })
            elif not flow.get("incomingAssets") and not flow.get("outgoingAssets"):
                issues.append({"severity": "warning", "rule": "setup", "teamCode": code, "message": "Seleccionado, pero todavía no participa."})

            hard_cap = hard_cap_for_season(data, season)
            issues.extend(hard_cap_issues(code, hard_cap, flow, thresholds))

            profile = salary_match_profile(flow, thresholds)
            if profile.get("legal"):
                if flow.get("incomingAssets") or flow.get("outgoingAssets"):
                    if not (profile.get("tpe") == "none" and float(flow.get("incomingSalary") or 0.0) <= 0):
                        salary_pass_messages.append(f"{code}: {profile.get('message')}")
                trigger = str(profile.get("hardCapTrigger") or "").strip().lower()
                if trigger in {"first", "second"}:
                    current_rank = 2 if hard_cap == "first" else 1 if hard_cap == "second" else 0
                    trigger_rank = 2 if trigger == "first" else 1
                    if current_rank < trigger_rank:
                        apron_label = "1er apron" if trigger == "first" else "2do apron"
                        reason = "usar la TPE expandida" if trigger == "first" else "agregar salarios de varios jugadores"
                        issues.append({
                            "severity": "warning",
                            "rule": "hard_cap_trigger",
                            "teamCode": code,
                            "hardCap": trigger,
                            "message": f"El traspaso dejaría al equipo hard-capped en el {apron_label} por {reason}.",
                        })
            else:
                issues.append({"severity": "illegal", "rule": "salary", "teamCode": code, "message": profile.get("message")})

            bucket = normalize_trade_bucket(payload.get("trade_bucket") or settings.get("trade_move_phase"))
            move_summary = data.get("move_summary") or {}
            availability = trade_move_availability(move_summary, bucket)
            remaining = parse_int(availability.get("remaining"))
            move_count = self._trade_flow_move_count(flow, season)
            if move_count:
                if remaining is None:
                    issues.append({"severity": "warning", "rule": "moves", "teamCode": code, "message": f"Necesita {move_count} movimiento(s); no se pudo leer el saldo de movimientos {availability.get('label') or bucket}."})
                elif move_count > remaining:
                    issues.append({"severity": "illegal", "rule": "moves", "teamCode": code, "message": f"Necesita {move_count} movimiento(s) y solo tiene {remaining} disponible(s) en {availability.get('label') or bucket}."})
                elif bucket == "post30" and availability.get("pre_remaining"):
                    issues.append({"severity": "warning", "rule": "moves", "teamCode": code, "message": f"Cuenta como post-30, pero primero consumirá {min(move_count, int(availability.get('pre_remaining') or 0))} movimiento(s) pre-30 disponible(s)."})

            summary = data.get("summary") or {}
            cash_limit = parse_float(summary.get("cash_limit_total")) or parse_float(settings.get("cash_limit_total")) or 0.0
            before_cash_sent = parse_float(summary.get("cash_sent")) or 0.0
            before_cash_received = parse_float(summary.get("cash_received")) or 0.0
            outgoing_cash = float(flow.get("outgoingCash") or 0.0)
            incoming_cash = float(flow.get("incomingCash") or 0.0)
            if cash_limit > 0 and outgoing_cash > 0 and before_cash_sent + outgoing_cash > cash_limit:
                issues.append({
                    "severity": "illegal",
                    "rule": "cash",
                    "teamCode": code,
                    "message": f"Envía {format_trade_money(outgoing_cash)} en cash y superaría su límite disponible.",
                })
            if cash_limit > 0 and incoming_cash > 0 and before_cash_received + incoming_cash > cash_limit:
                issues.append({
                    "severity": "illegal",
                    "rule": "cash",
                    "teamCode": code,
                    "message": f"Recibe {format_trade_money(incoming_cash)} en cash y superaría su límite disponible.",
                })

            issues.extend(apron_restriction_issues(code, flow, thresholds))

            outgoing_players = [a for a in flow.get("outgoingAssets") or [] if a.get("type") == "player"]
            stacking_issue = minimum_stacking_issue(code, flow)
            if stacking_issue:
                issues.append(stacking_issue)
            for asset in outgoing_players:
                rating = float(asset.get("rating") or 0.0)
                if 85 <= rating <= 90:
                    issues.append({"severity": "warning", "rule": "manual_review", "teamCode": code, "message": f"Ley Randle: {asset.get('label')} ({int(rating)}) no puede salir si llegó vía trade esta temporada, salvo lesión de temporada."})
                elif 80 <= rating < 85:
                    issues.append({"severity": "warning", "rule": "manual_review", "teamCode": code, "message": f"Ley Randle: {asset.get('label')} ({int(rating)}) debe esperar 2 meses/preseason o 30 partidos/season desde su llegada vía trade."})

            issues.extend(roster_count_issues(code, flow, roster_limits))

        has_illegal = any(issue.get("severity") == "illegal" for issue in issues)
        has_warning = any(issue.get("severity") == "warning" for issue in issues)
        checklist = trade_rule_checklist(
            issues,
            selected_count,
            salary_pass_messages or ["El cuadre salarial básico pasa para todos los equipos seleccionados."],
        )
        result = {
            "ok": True,
            "authoritative": True,
            "season": season,
            "status": "illegal" if has_illegal else "review" if has_warning else "legal",
            "issues": issues,
            "checklist": checklist,
            "flows": flows,
        }
        return self._signed_trade_validation(payload, result)

    def validation_from_process_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(payload.get("selections"), (list, dict)) or isinstance(payload.get("teams"), list):
            return self.validate(payload)

        team_a = normalize_team_code(payload.get("team_a")) or ""
        team_b = normalize_team_code(payload.get("team_b")) or ""
        no_count_a = set(self._clean_trade_ids(payload.get("no_count_players_a") or []))
        no_count_b = set(self._clean_trade_ids(payload.get("no_count_players_b") or []))
        pick_actions_a = self._trade_process_pick_actions(payload.get("pick_actions_a"))
        pick_actions_b = self._trade_process_pick_actions(payload.get("pick_actions_b"))
        selections: List[Dict[str, Any]] = []
        for player_id in self._clean_trade_ids(payload.get("players_a") or []):
            selections.append({"type": "player", "id": player_id, "from_team": team_a, "to_team": team_b, "no_count": player_id in no_count_a})
        for player_id in self._clean_trade_ids(payload.get("players_b") or []):
            selections.append({"type": "player", "id": player_id, "from_team": team_b, "to_team": team_a, "no_count": player_id in no_count_b})
        for pick_id in self._clean_trade_ids(payload.get("pick_ids_a") or []):
            selections.append({"type": "pick", "id": pick_id, "from_team": team_a, "to_team": team_b, "pick_action": pick_actions_a.get(pick_id)})
        for pick_id in self._clean_trade_ids(payload.get("pick_ids_b") or []):
            selections.append({"type": "pick", "id": pick_id, "from_team": team_b, "to_team": team_a, "pick_action": pick_actions_b.get(pick_id)})
        for right_id in self._clean_trade_ids(payload.get("right_ids_a") or []):
            selections.append({"type": "right", "id": right_id, "from_team": team_a, "to_team": team_b})
        for right_id in self._clean_trade_ids(payload.get("right_ids_b") or []):
            selections.append({"type": "right", "id": right_id, "from_team": team_b, "to_team": team_a})
        settings = self.settings()
        season = parse_int(payload.get("season")) or parse_int(settings.get("current_year")) or 2025
        return self.validate({
            "teams": [team_a, team_b],
            "season": season,
            "selections": selections,
        })

    def process_from_payload(
        self,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized = self.normalize_request(payload)
        teams = normalized.get("teams") or []
        selections = normalized.get("selections") or []
        cash_transfers = normalized.get("cash") or []
        if len(teams) < 2 or (not selections and not cash_transfers):
            return None

        owns_connection = conn is None
        with (self.db.connect() if owns_connection else nullcontext(conn)) as conn:
            team_rows: Dict[str, sqlite3.Row] = {}
            for code in teams:
                row = conn.execute("SELECT id, code FROM teams WHERE code = ?", (code,)).fetchone()
                if not row:
                    return None
                team_rows[code] = row

            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            season_year = parse_int(payload.get("season")) or current_year
            bucket = normalize_trade_bucket(payload.get("trade_bucket") or settings.get("trade_move_phase"))
            timestamp = self.operations.now()
            source_ref = f"{'-'.join(teams)}-{timestamp}"
            summaries: Dict[str, Dict[str, Any]] = {
                code: {
                    "code": code,
                    "move_count": 0,
                    "sent": {"players": [], "pick_count": 0, "swap_count": 0, "right_count": 0, "picks": [], "swaps": [], "rights": [], "cash": [], "cash_amount": 0.0},
                    "received": {"players": [], "pick_count": 0, "swap_count": 0, "right_count": 0, "picks": [], "swaps": [], "rights": [], "cash": [], "cash_amount": 0.0},
                }
                for code in teams
            }

            def add_move_count(code: str) -> None:
                if code in summaries:
                    summaries[code]["move_count"] += 1

            def add_selection_move_counts(from_team: str, to_team: str, asset: Dict[str, Any]) -> None:
                if not self._trade_asset_counts_as_move(asset, season_year):
                    return
                add_move_count(from_team)
                add_move_count(to_team)

            def pick_label(pick_row: Dict[str, Any], source_code: str, prefix: str = "") -> str:
                year = parse_int(pick_row.get("year"))
                year_label = str(year) if year is not None else "Sin año"
                round_label = self.operations.normalize_pick_round(pick_row.get("draft_round")).upper()
                owner = self._pick_actual_owner(pick_row, source_code)
                return f"{prefix}{year_label} {round_label} ({owner})".strip()

            def move_pick(source_team: sqlite3.Row, target_team: sqlite3.Row, pick_row: Dict[str, Any]) -> None:
                actual_owner = self._pick_actual_owner(pick_row, str(source_team["code"]))
                source_pick_type = self.operations.normalize_pick_type(pick_row.get("draft_pick_type"))
                pick_round = self.operations.normalize_pick_round(pick_row.get("draft_round"))
                pick_year = parse_int(pick_row.get("year"))
                if source_pick_type == "conditional":
                    target_pick_type = "conditional"
                    target_original_owner = None
                    target_conditional_teams = pick_row.get("draft_pick_conditional_teams")
                else:
                    target_pick_type = "own" if actual_owner == str(target_team["code"]) else "acquired"
                    target_original_owner = None if target_pick_type == "own" else actual_owner
                    target_conditional_teams = None

                recipient_rows_cur = conn.execute(
                    """
                    SELECT id, draft_pick_type, original_owner, year, draft_round, draft_pick_conditional_teams
                    FROM assets
                    WHERE team_id = ? AND asset_type = 'draft_pick' AND CAST(COALESCE(year, '') AS INTEGER) = ?
                    """,
                    (target_team["id"], pick_year),
                )
                recipient_rows = [self.operations.row_to_dict(recipient_rows_cur, row) for row in recipient_rows_cur.fetchall()]
                recipient_match = None
                for candidate in recipient_rows:
                    candidate_actual_owner = self._pick_actual_owner(candidate, str(target_team["code"]))
                    if candidate_actual_owner == actual_owner and self.operations.normalize_pick_round(candidate.get("draft_round")) == pick_round:
                        recipient_match = candidate
                        break

                sold_label = pick_row.get("label") or f"{pick_round.upper()} pick"
                sold_detail = pick_row.get("detail")

                def update_pick_row(asset_id: int) -> None:
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = ?, original_owner = ?, draft_pick_sold_to = NULL,
                            draft_pick_conditional_teams = ?, label = ?, detail = ?,
                            draft_pick_restricted = ?, draft_pick_stepien_restricted = ?,
                            draft_pick_protected = ?, draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            asset_id,
                        ),
                    )

                if source_pick_type == "own":
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = 'sold', original_owner = ?, draft_pick_sold_to = ?,
                            draft_pick_conditional_teams = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (actual_owner, str(target_team["code"]), timestamp, pick_row["id"]),
                    )
                elif recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    if int(recipient_match["id"]) != int(pick_row["id"]):
                        conn.execute("DELETE FROM assets WHERE id = ?", (pick_row["id"],))
                    return
                else:
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        """
                        UPDATE assets
                        SET team_id = ?, row_order = ?, draft_pick_type = ?, original_owner = ?,
                            draft_pick_sold_to = NULL, draft_pick_conditional_teams = ?,
                            label = ?, detail = ?, draft_pick_restricted = ?,
                            draft_pick_stepien_restricted = ?, draft_pick_protected = ?,
                            draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_team["id"],
                            int(mx) + 1,
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            pick_row["id"],
                        ),
                    )
                    return

                if recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    return

                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (target_team["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    """
                    INSERT INTO assets (
                        team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                        draft_pick_type, draft_round, original_owner, exception_type,
                        draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                        draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                        created_at, updated_at
                    ) VALUES (?, ?, 'draft_pick', ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, ?, ?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (
                        target_team["id"],
                        int(mx) + 1,
                        pick_row.get("year"),
                        sold_label,
                        sold_detail,
                        target_pick_type,
                        pick_round,
                        target_original_owner,
                        1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                        target_conditional_teams,
                        1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                        timestamp,
                        timestamp,
                    ),
                )

            for selection in selections:
                from_team = normalize_team_code(selection.get("fromTeam")) or ""
                to_team = normalize_team_code(selection.get("toTeam")) or ""
                asset_type = str(selection.get("type") or "").strip().lower()
                asset_id = parse_int(selection.get("id"))
                if not from_team or not to_team or from_team == to_team or from_team not in team_rows or to_team not in team_rows or asset_id is None:
                    return None
                source_team = team_rows[from_team]
                target_team = team_rows[to_team]

                if asset_type == "player":
                    row = conn.execute(
                        """
                        SELECT p.id, p.profile_id, p.team_id, COALESCE(pp.name, p.name) AS name
                        FROM players p
                        LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                        WHERE p.id = ?
                        """,
                        (asset_id,),
                    ).fetchone()
                    if not row or int(row["team_id"]) != int(source_team["id"]):
                        return None
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                        (target_team["id"], int(mx) + 1, timestamp, asset_id),
                    )
                    player_name = str(row["name"] or "Jugador")
                    summaries[from_team]["sent"]["players"].append(player_name)
                    summaries[to_team]["received"]["players"].append(player_name)
                    add_selection_move_counts(
                        from_team,
                        to_team,
                        {"type": "player", "countsMove": selection.get("countsMove", True)},
                    )
                    self.operations.record_transaction(
                        conn,
                        row["profile_id"],
                        "trade",
                        f"Traspasado de {from_team} a {to_team}",
                        player_id=row["id"],
                        team_code=to_team,
                        from_team_code=from_team,
                        to_team_code=to_team,
                        details={"player_name": player_name},
                        created_at=timestamp,
                    )
                    continue

                if asset_type == "pick":
                    row = conn.execute(
                        """
                        SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                               draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order,
                               draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                               draft_pick_frozen
                        FROM assets
                        WHERE id = ? AND asset_type = 'draft_pick'
                        """,
                        (asset_id,),
                    ).fetchone()
                    if not row or int(row["team_id"]) != int(source_team["id"]):
                        return None
                    pick_row = dict(row)
                    if self.operations.normalize_pick_type(pick_row.get("draft_pick_type")) == "sold":
                        return None
                    pick_action = self._trade_machine_pick_action(selection.get("pickAction") or selection.get("pick_action"))
                    if pick_action == TRADE_PICK_ACTION_SWAP:
                        label = pick_label(pick_row, from_team, "Swap ")
                        summaries[from_team]["sent"]["swap_count"] += 1
                        summaries[from_team]["sent"]["swaps"].append(label)
                        summaries[to_team]["received"]["swap_count"] += 1
                        summaries[to_team]["received"]["swaps"].append(label)
                    else:
                        label = pick_label(pick_row, from_team)
                        move_pick(source_team, target_team, pick_row)
                        summaries[from_team]["sent"]["pick_count"] += 1
                        summaries[from_team]["sent"]["picks"].append(label)
                        summaries[to_team]["received"]["pick_count"] += 1
                        summaries[to_team]["received"]["picks"].append(label)
                    add_selection_move_counts(
                        from_team,
                        to_team,
                        {
                            **pick_row,
                            "type": "pick",
                            "round": self.operations.normalize_pick_round(pick_row.get("draft_round")),
                            "pickAction": pick_action,
                            "countsMove": selection.get("countsMove", True),
                        },
                    )
                    continue

                if asset_type == "right":
                    row = conn.execute(
                        """
                        SELECT id, team_id, label, detail, row_order
                        FROM assets
                        WHERE id = ? AND asset_type = 'player_right'
                        """,
                        (asset_id,),
                    ).fetchone()
                    if not row or int(row["team_id"]) != int(source_team["id"]):
                        return None
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        "UPDATE assets SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                        (target_team["id"], int(mx) + 1, timestamp, asset_id),
                    )
                    label = str(row["label"] or "Derecho de jugador")
                    summaries[from_team]["sent"]["right_count"] += 1
                    summaries[from_team]["sent"]["rights"].append(label)
                    summaries[to_team]["received"]["right_count"] += 1
                    summaries[to_team]["received"]["rights"].append(label)
                    continue

                return None

            for transfer in cash_transfers:
                from_team = normalize_team_code(transfer.get("fromTeam")) or ""
                to_team = normalize_team_code(transfer.get("toTeam")) or ""
                amount = float(transfer.get("amount") or 0.0)
                if not from_team or not to_team or from_team == to_team or from_team not in team_rows or to_team not in team_rows or amount <= 0:
                    return None
                conn.execute(
                    "UPDATE teams SET cash_sent = COALESCE(cash_sent, 0) + ?, updated_at = ? WHERE id = ?",
                    (amount, timestamp, team_rows[from_team]["id"]),
                )
                conn.execute(
                    "UPDATE teams SET cash_received = COALESCE(cash_received, 0) + ?, updated_at = ? WHERE id = ?",
                    (amount, timestamp, team_rows[to_team]["id"]),
                )
                cash_ref = {"team": to_team, "amount": amount}
                summaries[from_team]["sent"]["cash"].append(cash_ref)
                summaries[from_team]["sent"]["cash_amount"] += amount
                summaries[to_team]["received"]["cash"].append({"team": from_team, "amount": amount})
                summaries[to_team]["received"]["cash_amount"] += amount

            for code, summary in summaries.items():
                move_count = int(summary.get("move_count") or 0)
                if not move_count:
                    continue
                sent = summary.get("sent") or {}
                opponents = sorted(
                    {
                        normalize_team_code(selection.get("toTeam"))
                        for selection in selections
                        if normalize_team_code(selection.get("fromTeam")) == code and normalize_team_code(selection.get("toTeam"))
                    }
                )
                self._insert_trade_move_logs(
                    conn,
                    team_id=int(team_rows[code]["id"]),
                    season_year=season_year,
                    requested_bucket=bucket,
                    move_count=move_count,
                    source_ref=source_ref,
                    note=f"Trade vs {'/'.join(opponents)}" if opponents else "Trade",
                    details={
                        "opponents": opponents,
                        "players": sent.get("players") or [],
                        "players_received": (summary.get("received") or {}).get("players") or [],
                        "pick_count": sent.get("pick_count") or 0,
                        "pick_refs": sent.get("picks") or [],
                        "pick_refs_received": (summary.get("received") or {}).get("picks") or [],
                        "swap_count": sent.get("swap_count") or 0,
                        "swap_refs": sent.get("swaps") or [],
                        "rights": sent.get("rights") or [],
                        "cash": sent.get("cash") or [],
                        "cash_amount": sent.get("cash_amount") or 0.0,
                    },
                    settings=settings,
                )

            if owns_connection:
                conn.commit()

        team_results = [summaries[code] for code in teams]
        result: Dict[str, Any] = {
            "ok": True,
            "trade_bucket": bucket,
            "season": season_year,
            "teams": team_results,
            "team_codes": teams,
        }
        if len(teams) >= 2:
            team_a = teams[0]
            team_b = teams[1]
            result.update(
                {
                    "team_a": {"code": team_a, "move_count": summaries[team_a]["move_count"]},
                    "team_b": {"code": team_b, "move_count": summaries[team_b]["move_count"]},
                    "players_a": summaries[team_a]["sent"]["players"],
                    "players_b": summaries[team_b]["sent"]["players"],
                    "pick_count_a": summaries[team_a]["sent"]["pick_count"],
                    "pick_count_b": summaries[team_b]["sent"]["pick_count"],
                    "pick_refs_a": summaries[team_a]["sent"]["picks"],
                    "pick_refs_b": summaries[team_b]["sent"]["picks"],
                    "swap_count_a": summaries[team_a]["sent"]["swap_count"],
                    "swap_count_b": summaries[team_b]["sent"]["swap_count"],
                    "swap_refs_a": summaries[team_a]["sent"]["swaps"],
                    "swap_refs_b": summaries[team_b]["sent"]["swaps"],
                    "right_count_a": summaries[team_a]["sent"]["right_count"],
                    "right_count_b": summaries[team_b]["sent"]["right_count"],
                    "cash_a": summaries[team_a]["sent"]["cash_amount"],
                    "cash_b": summaries[team_b]["sent"]["cash_amount"],
                }
            )
        return result

    def process_legacy(
        self,
        team_a_code: str,
        team_b_code: str,
        players_a: List[int],
        players_b: List[int],
        pick_ids_a: Optional[List[int]] = None,
        pick_ids_b: Optional[List[int]] = None,
        right_ids_a: Optional[List[int]] = None,
        right_ids_b: Optional[List[int]] = None,
        no_count_players_a: Optional[List[int]] = None,
        no_count_players_b: Optional[List[int]] = None,
        pick_actions_a: Optional[Any] = None,
        pick_actions_b: Optional[Any] = None,
        trade_bucket: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[Dict[str, Any]]:
        def clean_ids(values: Any) -> List[int]:
            if not isinstance(values, list):
                return []
            out: List[int] = []
            seen: set[int] = set()
            for value in values:
                parsed = parse_int(str(value))
                if parsed is None or parsed <= 0 or parsed in seen:
                    continue
                seen.add(parsed)
                out.append(parsed)
            return out

        ids_a = clean_ids(players_a)
        ids_b = clean_ids(players_b)
        pick_a_all = clean_ids(pick_ids_a or [])
        pick_b_all = clean_ids(pick_ids_b or [])
        pick_action_map_a = self._trade_process_pick_actions(pick_actions_a)
        pick_action_map_b = self._trade_process_pick_actions(pick_actions_b)
        pick_swap_a = {pick_id for pick_id in pick_a_all if pick_action_map_a.get(pick_id) == TRADE_PICK_ACTION_SWAP}
        pick_swap_b = {pick_id for pick_id in pick_b_all if pick_action_map_b.get(pick_id) == TRADE_PICK_ACTION_SWAP}
        pick_a = [pick_id for pick_id in pick_a_all if pick_id not in pick_swap_a]
        pick_b = [pick_id for pick_id in pick_b_all if pick_id not in pick_swap_b]
        right_a = clean_ids(right_ids_a or [])
        right_b = clean_ids(right_ids_b or [])
        no_count_a = set(clean_ids(no_count_players_a or []))
        no_count_b = set(clean_ids(no_count_players_b or []))
        if not ids_a and not pick_a_all and not right_a:
            return None
        if not ids_b and not pick_b_all and not right_b:
            return None

        owns_connection = conn is None
        with (self.db.connect() if owns_connection else nullcontext(conn)) as conn:
            team_a = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_a_code.upper(),)).fetchone()
            team_b = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_b_code.upper(),)).fetchone()
            if not team_a or not team_b or team_a["id"] == team_b["id"]:
                return None

            if owns_connection:
                current_year = parse_int(self.settings().get("current_year")) or 2025
            else:
                settings_cur = conn.execute("SELECT key, value FROM app_settings")
                settings_for_year = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
                current_year = parse_int(settings_for_year.get("current_year")) or 2025
            if current_year < self.operations.contract_min_year or current_year > self.operations.contract_max_start_year:
                current_year = 2025

            players_a_rows: List[Dict[str, Any]] = []
            for player_id in ids_a:
                row = conn.execute(
                    """
                    SELECT p.id, p.profile_id, p.team_id, COALESCE(pp.name, p.name) AS name
                    FROM players p
                    LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    WHERE p.id = ?
                    """,
                    (player_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                players_a_rows.append(dict(row))
            players_b_rows: List[Dict[str, Any]] = []
            for player_id in ids_b:
                row = conn.execute(
                    """
                    SELECT p.id, p.profile_id, p.team_id, COALESCE(pp.name, p.name) AS name
                    FROM players p
                    LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    WHERE p.id = ?
                    """,
                    (player_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                players_b_rows.append(dict(row))

            picks_a_rows: List[Dict[str, Any]] = []
            pick_swaps_a_rows: List[Dict[str, Any]] = []
            for asset_id in pick_a_all:
                row = conn.execute(
                    """
                    SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                           draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order,
                           draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                           draft_pick_frozen
                    FROM assets
                    WHERE id = ? AND asset_type = 'draft_pick'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                if self.operations.normalize_pick_type(row["draft_pick_type"]) == "sold":
                    return None
                if asset_id in pick_swap_a:
                    pick_swaps_a_rows.append(dict(row))
                else:
                    picks_a_rows.append(dict(row))

            picks_b_rows: List[Dict[str, Any]] = []
            pick_swaps_b_rows: List[Dict[str, Any]] = []
            for asset_id in pick_b_all:
                row = conn.execute(
                    """
                    SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                           draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order,
                           draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                           draft_pick_frozen
                    FROM assets
                    WHERE id = ? AND asset_type = 'draft_pick'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                if self.operations.normalize_pick_type(row["draft_pick_type"]) == "sold":
                    return None
                if asset_id in pick_swap_b:
                    pick_swaps_b_rows.append(dict(row))
                else:
                    picks_b_rows.append(dict(row))

            rights_a_rows: List[Dict[str, Any]] = []
            for asset_id in right_a:
                row = conn.execute(
                    """
                    SELECT id, team_id, label, detail, row_order
                    FROM assets
                    WHERE id = ? AND asset_type = 'player_right'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                rights_a_rows.append(dict(row))

            rights_b_rows: List[Dict[str, Any]] = []
            for asset_id in right_b:
                row = conn.execute(
                    """
                    SELECT id, team_id, label, detail, row_order
                    FROM assets
                    WHERE id = ? AND asset_type = 'player_right'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                rights_b_rows.append(dict(row))

            timestamp = self.operations.now()
            for player_id in ids_a:
                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                    (team_b["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                    (team_b["id"], int(mx) + 1, timestamp, player_id),
                )
            for row in players_a_rows:
                self.operations.record_transaction(
                    conn,
                    row.get("profile_id"),
                    "trade",
                    f"Traspasado de {team_a['code']} a {team_b['code']}",
                    player_id=row.get("id"),
                    team_code=team_b["code"],
                    from_team_code=team_a["code"],
                    to_team_code=team_b["code"],
                    details={"player_name": row.get("name")},
                    created_at=timestamp,
                )

            for player_id in ids_b:
                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                    (team_a["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                    (team_a["id"], int(mx) + 1, timestamp, player_id),
                )
            for row in players_b_rows:
                self.operations.record_transaction(
                    conn,
                    row.get("profile_id"),
                    "trade",
                    f"Traspasado de {team_b['code']} a {team_a['code']}",
                    player_id=row.get("id"),
                    team_code=team_a["code"],
                    from_team_code=team_b["code"],
                    to_team_code=team_a["code"],
                    details={"player_name": row.get("name")},
                    created_at=timestamp,
                )

            def move_pick(source_team: sqlite3.Row, target_team: sqlite3.Row, pick_row: Dict[str, Any]) -> None:
                actual_owner = self._pick_actual_owner(pick_row, str(source_team["code"]))
                source_pick_type = self.operations.normalize_pick_type(pick_row.get("draft_pick_type"))
                pick_round = self.operations.normalize_pick_round(pick_row.get("draft_round"))
                pick_year = parse_int(pick_row.get("year"))
                if source_pick_type == "conditional":
                    target_pick_type = "conditional"
                    target_original_owner = None
                    target_conditional_teams = pick_row.get("draft_pick_conditional_teams")
                else:
                    target_pick_type = "own" if actual_owner == str(target_team["code"]) else "acquired"
                    target_original_owner = None if target_pick_type == "own" else actual_owner
                    target_conditional_teams = None

                recipient_rows_cur = conn.execute(
                    """
                    SELECT id, draft_pick_type, original_owner, year, draft_round, draft_pick_conditional_teams
                    FROM assets
                    WHERE team_id = ? AND asset_type = 'draft_pick' AND CAST(COALESCE(year, '') AS INTEGER) = ?
                    """,
                    (target_team["id"], pick_year),
                )
                recipient_rows = [self.operations.row_to_dict(recipient_rows_cur, row) for row in recipient_rows_cur.fetchall()]
                recipient_match = None
                for candidate in recipient_rows:
                    candidate_actual_owner = self._pick_actual_owner(candidate, str(target_team["code"]))
                    if candidate_actual_owner == actual_owner and self.operations.normalize_pick_round(candidate.get("draft_round")) == pick_round:
                        recipient_match = candidate
                        break

                sold_label = pick_row.get("label") or f"{pick_round.upper()} pick"
                sold_detail = pick_row.get("detail")

                def update_pick_row(asset_id: int) -> None:
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = ?, original_owner = ?, draft_pick_sold_to = NULL,
                            draft_pick_conditional_teams = ?, label = ?, detail = ?,
                            draft_pick_restricted = ?, draft_pick_stepien_restricted = ?,
                            draft_pick_protected = ?, draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            asset_id,
                        ),
                    )

                if source_pick_type == "own":
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = 'sold', original_owner = ?, draft_pick_sold_to = ?,
                            draft_pick_conditional_teams = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        (actual_owner, str(target_team["code"]), timestamp, pick_row["id"]),
                    )
                elif recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    if int(recipient_match["id"]) != int(pick_row["id"]):
                        conn.execute("DELETE FROM assets WHERE id = ?", (pick_row["id"],))
                    return
                else:
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        """
                        UPDATE assets
                        SET team_id = ?, row_order = ?, draft_pick_type = ?, original_owner = ?,
                            draft_pick_sold_to = NULL, draft_pick_conditional_teams = ?,
                            label = ?, detail = ?, draft_pick_restricted = ?,
                            draft_pick_stepien_restricted = ?, draft_pick_protected = ?,
                            draft_pick_frozen = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_team["id"],
                            int(mx) + 1,
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                            1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                            timestamp,
                            pick_row["id"],
                        ),
                    )
                    return

                if recipient_match:
                    update_pick_row(int(recipient_match["id"]))
                    return

                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (target_team["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    """
                    INSERT INTO assets (
                        team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                        draft_pick_type, draft_round, original_owner, exception_type,
                        draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                        draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                        created_at, updated_at
                    ) VALUES (?, ?, 'draft_pick', ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, ?, ?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (
                        target_team["id"],
                        int(mx) + 1,
                        pick_row.get("year"),
                        sold_label,
                        sold_detail,
                        target_pick_type,
                        pick_round,
                        target_original_owner,
                        1 if parse_bool(pick_row.get("draft_pick_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_stepien_restricted")) else 0,
                        1 if parse_bool(pick_row.get("draft_pick_protected")) else 0,
                        target_conditional_teams,
                        1 if parse_bool(pick_row.get("draft_pick_frozen")) else 0,
                        timestamp,
                        timestamp,
                    ),
                )

            for pick_row in picks_a_rows:
                move_pick(team_a, team_b, pick_row)
            for pick_row in picks_b_rows:
                move_pick(team_b, team_a, pick_row)

            def move_player_rights(target_team: sqlite3.Row, right_rows: List[Dict[str, Any]]) -> None:
                for right_row in right_rows:
                    mx = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                        (target_team["id"],),
                    ).fetchone()["mx"]
                    conn.execute(
                        """
                        UPDATE assets
                        SET team_id = ?, row_order = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (target_team["id"], int(mx) + 1, timestamp, right_row["id"]),
                    )

            move_player_rights(team_b, rights_a_rows)
            move_player_rights(team_a, rights_b_rows)

            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            bucket = normalize_trade_bucket(trade_bucket or settings.get("trade_move_phase"))

            def player_move_count(rows: List[Dict[str, Any]], excluded_ids: set[int]) -> int:
                return sum(
                    1
                    for row in rows
                    if self._trade_asset_counts_as_move(
                        {"type": "player", "countsMove": int(row["id"]) not in excluded_ids},
                        current_year,
                    )
                )

            def pick_move_count(rows: List[Dict[str, Any]]) -> int:
                return sum(
                    1
                    for row in rows
                    if self._trade_asset_counts_as_move(
                        {"type": "pick", "draft_round": row.get("draft_round"), "year": row.get("year")},
                        current_year,
                    )
                )

            move_count_a = (
                player_move_count(players_a_rows, no_count_a)
                + player_move_count(players_b_rows, no_count_b)
                + pick_move_count(picks_a_rows)
                + pick_move_count(picks_b_rows)
            )
            move_count_b = (
                player_move_count(players_b_rows, no_count_b)
                + player_move_count(players_a_rows, no_count_a)
                + pick_move_count(picks_b_rows)
                + pick_move_count(picks_a_rows)
            )

            def pick_ref(pick_row: Dict[str, Any], source_team: sqlite3.Row, prefix: str = "") -> str:
                year = parse_int(pick_row.get("year"))
                year_label = str(year) if year is not None else "Sin año"
                round_label = self.operations.normalize_pick_round(pick_row.get("draft_round")).upper()
                owner = self._pick_actual_owner(pick_row, str(source_team["code"]))
                return f"{prefix}{year_label} {round_label} ({owner})".strip()

            pick_refs_a = [pick_ref(row, team_a) for row in picks_a_rows]
            pick_refs_b = [pick_ref(row, team_b) for row in picks_b_rows]
            swap_refs_a = [pick_ref(row, team_a, "Swap ") for row in pick_swaps_a_rows]
            swap_refs_b = [pick_ref(row, team_b, "Swap ") for row in pick_swaps_b_rows]

            if move_count_a:
                self._insert_trade_move_logs(
                    conn,
                    team_id=int(team_a["id"]),
                    season_year=current_year,
                    requested_bucket=bucket,
                    move_count=move_count_a,
                    source_ref=f"{team_a['code']}-{team_b['code']}-{timestamp}",
                    note=f"Trade vs {team_b['code']}",
                    details={
                        "opponent": team_b["code"],
                        "players": [row["name"] for row in players_a_rows if int(row["id"]) not in no_count_a],
                        "players_received": [row["name"] for row in players_b_rows if int(row["id"]) not in no_count_b],
                        "players_excluded": [row["name"] for row in players_a_rows if int(row["id"]) in no_count_a],
                        "pick_count": len(picks_a_rows),
                        "pick_refs": pick_refs_a,
                        "pick_refs_received": pick_refs_b,
                        "swap_count": len(pick_swaps_a_rows),
                        "swap_refs": swap_refs_a,
                        "rights": [row.get("label") for row in rights_a_rows],
                    },
                    settings=settings,
                )
            if move_count_b:
                self._insert_trade_move_logs(
                    conn,
                    team_id=int(team_b["id"]),
                    season_year=current_year,
                    requested_bucket=bucket,
                    move_count=move_count_b,
                    source_ref=f"{team_b['code']}-{team_a['code']}-{timestamp}",
                    note=f"Trade vs {team_a['code']}",
                    details={
                        "opponent": team_a["code"],
                        "players": [row["name"] for row in players_b_rows if int(row["id"]) not in no_count_b],
                        "players_received": [row["name"] for row in players_a_rows if int(row["id"]) not in no_count_a],
                        "players_excluded": [row["name"] for row in players_b_rows if int(row["id"]) in no_count_b],
                        "pick_count": len(picks_b_rows),
                        "pick_refs": pick_refs_b,
                        "pick_refs_received": pick_refs_a,
                        "swap_count": len(pick_swaps_b_rows),
                        "swap_refs": swap_refs_b,
                        "rights": [row.get("label") for row in rights_b_rows],
                    },
                    settings=settings,
                )

            if owns_connection:
                conn.commit()
            return {
                "ok": True,
                "trade_bucket": bucket,
                "team_a": {"code": team_a["code"], "move_count": move_count_a},
                "team_b": {"code": team_b["code"], "move_count": move_count_b},
                "players_a": [row["name"] for row in players_a_rows],
                "players_b": [row["name"] for row in players_b_rows],
                "pick_count_a": len(picks_a_rows),
                "pick_count_b": len(picks_b_rows),
                "pick_refs_a": pick_refs_a,
                "pick_refs_b": pick_refs_b,
                "swap_count_a": len(pick_swaps_a_rows),
                "swap_count_b": len(pick_swaps_b_rows),
                "swap_refs_a": swap_refs_a,
                "swap_refs_b": swap_refs_b,
                "right_count_a": len(rights_a_rows),
                "right_count_b": len(rights_b_rows),
            }
