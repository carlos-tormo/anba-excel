"""SQLite persistence for transactional season rollover."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain._values import parse_float, parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_float, parse_int

from .base import LeagueRepository


@dataclass(frozen=True)
class SeasonRolloverOperations:
    now: Callable[[], str]
    select_team_players: Callable[..., List[Dict[str, Any]]]
    calc_summary: Callable[..., Dict[str, Any]]
    luxury_repeater: Callable[..., bool]
    apron_hard_cap: Callable[..., str]
    ensure_profile: Callable[..., Optional[int]]
    upsert_salary_history: Callable[..., bool]
    record_transaction: Callable[..., Any]
    upsert_frozen_pick: Callable[..., Dict[str, Any]]
    row_to_dict: Callable[..., Dict[str, Any]]
    increment_bird_years_value: Callable[..., Optional[str]]
    normalize_bird_years: Callable[[Any], Optional[str]]
    dead_contract_salary_num: Callable[[Dict[str, Any], int], float]
    contract_seasons: tuple[int, ...]
    contract_min_year: int
    contract_max_year: int


class SeasonRolloverRepository(LeagueRepository):
    def __init__(self, db: Any, operations: Optional[SeasonRolloverOperations] = None) -> None:
        super().__init__(db)
        self.operations = operations

    def _operations(self) -> SeasonRolloverOperations:
        if not self.operations:
            raise RuntimeError("season_rollover_repository_not_configured")
        return self.operations

    def transaction(self, mode: str = "IMMEDIATE") -> Any:
        return self.db.transaction(mode)

    def now(self) -> str:
        return self._operations().now()

    @staticmethod
    def settings(conn: sqlite3.Connection) -> Dict[str, str]:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    @staticmethod
    def insert_snapshot(
        conn: sqlite3.Connection,
        season_year: int,
        payload_json: str,
        timestamp: str,
    ) -> None:
        conn.execute(
            "INSERT INTO season_snapshots (season_year, payload_json, created_at) VALUES (?, ?, ?)",
            (season_year, payload_json, timestamp),
        )

    @staticmethod
    def current_year_row(conn: sqlite3.Connection) -> Dict[str, Any]:
        row = conn.execute(
            "SELECT value, version FROM app_settings WHERE key = 'current_year'"
        ).fetchone()
        if not row:
            return {"value": None, "version": None}
        return {"value": row["value"], "version": parse_int(row["version"])}

    @staticmethod
    def update_current_year(
        conn: sqlite3.Connection,
        next_year: int,
        timestamp: str,
        *,
        expected_year: Optional[int] = None,
        expected_version: Optional[int] = None,
    ) -> int:
        existing = conn.execute(
            "SELECT value, version FROM app_settings WHERE key = 'current_year'"
        ).fetchone()
        if existing is None:
            if expected_year is not None or expected_version is not None:
                raise ValueError("stale_entity_version")
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES ('current_year', ?, ?)",
                (str(next_year), timestamp),
            )
            return 1
        current_year = parse_int(existing["value"])
        current_version = parse_int(existing["version"]) or 1
        if expected_year is not None and current_year != int(expected_year):
            raise ValueError("stale_entity_version")
        if expected_version is not None and current_version != int(expected_version):
            raise ValueError("stale_entity_version")
        cur = conn.execute(
            """UPDATE app_settings
               SET value = ?, version = COALESCE(version, 0) + 1, updated_at = ?
               WHERE key = 'current_year' AND value = ? AND version = ?""",
            (str(next_year), timestamp, str(current_year), current_version),
        )
        if cur.rowcount != 1:
            raise ValueError("stale_entity_version")
        return current_version + 1

    def snapshot_payload(self, conn: sqlite3.Connection, season_year: int, settings: Dict[str, str]) -> Dict[str, Any]:
        team_cur = conn.execute("SELECT * FROM teams ORDER BY code")
        teams = [self.operations.row_to_dict(team_cur, row) for row in team_cur.fetchall()]
        payload_teams: List[Dict[str, Any]] = []
        for team in teams:
            team_id = team["id"]
            players = self.operations.select_team_players(conn, int(team_id))
            assets_cur = conn.execute(
                "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                (team_id,),
            )
            assets = [self.operations.row_to_dict(assets_cur, row) for row in assets_cur.fetchall()]
            dead_cur = conn.execute(
                "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                (team_id,),
            )
            dead_contracts = [self.operations.row_to_dict(dead_cur, row) for row in dead_cur.fetchall()]
            move_log_cur = conn.execute(
                """
                SELECT id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
                FROM team_move_logs
                WHERE team_id = ? AND season_year = ?
                ORDER BY id ASC
                """,
                (team_id, season_year),
            )
            move_logs = [self.operations.row_to_dict(move_log_cur, row) for row in move_log_cur.fetchall()]
            luxury_repeater = self.operations.luxury_repeater(conn, int(team_id), season_year)
            summary = self.operations.calc_summary(
                team,
                players,
                assets,
                dead_contracts,
                settings,
                season_year=season_year,
                luxury_repeater=luxury_repeater,
            )
            payload_teams.append(
                {
                    "team": team,
                    "players": players,
                    "assets": assets,
                    "dead_contracts": dead_contracts,
                    "move_logs": move_logs,
                    "summary": summary,
                }
            )
        return {
            "season_year": season_year,
            "season_label": f"{season_year}-{str((season_year + 1) % 100).zfill(2)}",
            "created_at": self.operations.now(),
            "settings": settings,
            "teams": payload_teams,
        }

    def store_salary_history(
        self,
        conn: sqlite3.Connection,
        season_year: int,
        timestamp: Optional[str] = None,
        source: str = "season_rollover",
    ) -> int:
        text_col = f"salary_{int(season_year)}_text"
        num_col = f"salary_{int(season_year)}_num"
        player_cols = {row["name"] for row in conn.execute("PRAGMA table_info(players)").fetchall()}
        if text_col not in player_cols and num_col not in player_cols:
            return 0
        rows = conn.execute(
            f"""
            SELECT
                p.id,
                p.profile_id,
                t.code AS team_code,
                p.bird_rights AS salary_type,
                {text_col if text_col in player_cols else "NULL"} AS salary_text,
                {num_col if num_col in player_cols else "NULL"} AS salary_num
            FROM players p
            JOIN teams t ON t.id = p.team_id
            ORDER BY p.id
            """
        ).fetchall()
        count = 0
        for row in rows:
            profile_id = parse_int(row["profile_id"])
            if profile_id is None:
                profile_id = self.operations.ensure_profile(conn, int(row["id"]), timestamp)
            if self.operations.upsert_salary_history(
                conn,
                profile_id=profile_id,
                player_id=row["id"],
                team_code=row["team_code"],
                season_year=season_year,
                salary_text=row["salary_text"],
                salary_num=row["salary_num"],
                salary_type=row["salary_type"],
                source=source,
                timestamp=timestamp,
            ):
                count += 1
        return count

    def increment_bird_years(self, conn: sqlite3.Connection, seasons: int, timestamp: str) -> int:
        steps = max(0, int(seasons or 0))
        if steps <= 0:
            return 0
        cur = conn.execute("SELECT id, years_left FROM players")
        updates: List[tuple[Optional[str], str, int]] = []
        for row in cur.fetchall():
            normalized_current = self.operations.normalize_bird_years(row["years_left"])
            next_value = self.operations.increment_bird_years_value(row["years_left"], steps)
            if next_value != normalized_current:
                updates.append((next_value, timestamp, int(row["id"])))
        if updates:
            conn.executemany(
                "UPDATE players SET years_left = ?, updated_at = ? WHERE id = ?",
                updates,
            )
        return len(updates)

    def move_expired_players(
        self,
        conn: sqlite3.Connection,
        season_year: int,
        timestamp: str,
    ) -> int:
        season = parse_int(season_year)
        if season is None or season < self.operations.contract_min_year or season > self.operations.contract_max_year:
            return 0
        salary_text_field = f"salary_{season}_text"
        salary_num_field = f"salary_{season}_num"
        option_field = f"option_{season}"
        cur = conn.execute(
            f"""
            SELECT
                p.id,
                p.profile_id,
                COALESCE(pp.name, p.name) AS name,
                p.position,
                p.bird_rights,
                p.rating,
                p.years_left,
                p.notes,
                p.{salary_text_field} AS season_salary_text,
                p.{salary_num_field} AS season_salary_num,
                p.{option_field} AS season_option,
                t.code AS team_code
            FROM players p
            LEFT JOIN player_profiles pp ON pp.id = p.profile_id
            JOIN teams t ON t.id = p.team_id
            ORDER BY p.id
            """
        )
        moved = 0
        for row in cur.fetchall():
            salary_text = str(row["season_salary_text"] or "").strip()
            salary_num = parse_float(row["season_salary_num"])
            option_value = str(row["season_option"] or "").strip()
            if salary_text or salary_num is not None or option_value:
                continue
            player_id = int(row["id"])
            profile_id = parse_int(row["profile_id"])
            if profile_id is None:
                profile_id = self.operations.ensure_profile(conn, player_id, timestamp)
            active_elsewhere = None
            if profile_id is not None:
                active_elsewhere = conn.execute(
                    f"""
                    SELECT id
                    FROM players
                    WHERE profile_id = ?
                        AND id != ?
                        AND (
                            COALESCE(TRIM({salary_text_field}), '') != ''
                            OR {salary_num_field} IS NOT NULL
                            OR COALESCE(TRIM({option_field}), '') != ''
                        )
                    LIMIT 1
                    """,
                    (profile_id, player_id),
                ).fetchone()
            if active_elsewhere:
                conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
                moved += 1
                continue

            free_agent_id: Optional[int] = None
            if profile_id is not None:
                existing_free_agent = conn.execute(
                    "SELECT id FROM free_agents WHERE profile_id = ? LIMIT 1",
                    (profile_id,),
                ).fetchone()
                if existing_free_agent:
                    free_agent_id = int(existing_free_agent["id"])
            if free_agent_id is None:
                free_cur = conn.execute(
                    """
                    INSERT INTO free_agents (
                        profile_id, name, position, bird_rights, rating, years_left, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        row["name"] or "Free Agent",
                        row["position"],
                        row["bird_rights"],
                        row["rating"],
                        row["years_left"],
                        row["notes"],
                        timestamp,
                        timestamp,
                    ),
                )
                free_agent_id = int(free_cur.lastrowid)
            self.operations.record_transaction(
                conn,
                profile_id,
                "free_agent",
                f"Pasa a agentes libres al avanzar a {season}-{(season + 1) % 100:02d}",
                player_id=player_id,
                free_agent_id=free_agent_id,
                team_code=row["team_code"],
                from_team_code=row["team_code"],
                details={"player_name": row["name"], "season_year": season},
                created_at=timestamp,
            )
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            moved += 1
        return moved

    def freeze_second_apron_picks(
        self,
        conn: sqlite3.Connection,
        previous_year: int,
        next_year: int,
        settings: Dict[str, str],
        timestamp: str,
    ) -> List[Dict[str, Any]]:
        if int(next_year) <= int(previous_year):
            return []
        frozen_rows: List[Dict[str, Any]] = []
        teams_cur = conn.execute("SELECT * FROM teams ORDER BY code")
        teams = [self.operations.row_to_dict(teams_cur, row) for row in teams_cur.fetchall()]
        for penalty_year in range(int(previous_year), int(next_year)):
            frozen_draft_year = int(penalty_year) + 8
            for team in teams:
                team_id = int(team["id"])
                players = self.operations.select_team_players(conn, team_id)
                assets_cur = conn.execute(
                    "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                    (team_id,),
                )
                assets = [self.operations.row_to_dict(assets_cur, row) for row in assets_cur.fetchall()]
                dead_cur = conn.execute(
                    "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                    (team_id,),
                )
                dead_contracts = [self.operations.row_to_dict(dead_cur, row) for row in dead_cur.fetchall()]
                luxury_repeater = self.operations.luxury_repeater(conn, team_id, int(penalty_year))
                hard_cap = self.operations.apron_hard_cap(conn, team_id, int(penalty_year), team.get("apron_hard_cap"))
                summary = self.operations.calc_summary(
                    team,
                    players,
                    assets,
                    dead_contracts,
                    settings,
                    season_year=int(penalty_year),
                    luxury_repeater=luxury_repeater,
                    apron_hard_cap=hard_cap,
                )
                if float(summary.get("apron_account") or 0.0) <= float(summary.get("second_apron") or 0.0):
                    continue
                frozen_rows.append(
                    self.operations.upsert_frozen_pick(
                        conn,
                        team_id,
                        str(team["code"]),
                        int(penalty_year),
                        int(frozen_draft_year),
                        "1st",
                        "Finalizó por encima del 2do apron",
                        "Bloqueo automático al avanzar la temporada.",
                        timestamp,
                    )
                )
        return frozen_rows

    def _create_missing_future_draft_assets(
        self,
        conn: sqlite3.Connection,
        draft_year: int,
        timestamp: str,
    ) -> List[Dict[str, Any]]:
        created: List[Dict[str, Any]] = []
        teams_cur = conn.execute("SELECT id, code FROM teams ORDER BY code")
        teams = [self.operations.row_to_dict(teams_cur, row) for row in teams_cur.fetchall()]
        for team in teams:
            team_id = int(team["id"])
            team_code = str(team["code"])
            max_order = int(
                conn.execute(
                    "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                    (team_id,),
                ).fetchone()["mx"]
                or 0
            )
            for draft_round in ("1st", "2nd"):
                existing = conn.execute(
                    """
                    SELECT 1
                    FROM assets
                    WHERE team_id = ?
                      AND asset_type = 'draft_pick'
                      AND CAST(COALESCE(year, '') AS INTEGER) = ?
                      AND COALESCE(draft_round, '1st') = ?
                      AND COALESCE(LOWER(draft_pick_type), 'own') IN ('own', 'sold')
                    LIMIT 1
                    """,
                    (team_id, int(draft_year), draft_round),
                ).fetchone()
                if existing:
                    continue
                max_order += 1
                cur = conn.execute(
                    """
                    INSERT INTO assets (
                        team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                        draft_pick_type, draft_round, original_owner, exception_type,
                        draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                        draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                        created_at, updated_at
                    )
                    VALUES (?, ?, 'draft_pick', ?, ?, '', NULL, NULL, 'own', ?, NULL, NULL, 0, 0, 0, NULL, NULL, 0, ?, ?)
                    """,
                    (
                        team_id,
                        max_order,
                        int(draft_year),
                        f"{draft_round} pick",
                        draft_round,
                        timestamp,
                        timestamp,
                    ),
                )
                created.append(
                    {
                        "id": int(cur.lastrowid),
                        "team_code": team_code,
                        "year": int(draft_year),
                        "draft_round": draft_round,
                    }
                )
        return created

    def rollover_draft_assets(
        self,
        conn: sqlite3.Connection,
        previous_year: int,
        next_year: int,
        timestamp: str,
    ) -> Dict[str, Any]:
        if int(next_year) <= int(previous_year):
            return {
                "deleted_draft_assets": 0,
                "deleted_draft_asset_years": [],
                "future_draft_asset_years": [],
                "created_future_draft_assets": [],
            }

        deleted_total = 0
        deleted_years: List[Dict[str, int]] = []
        for season_year in range(int(previous_year), int(next_year)):
            expiring_asset_year = int(season_year) + 1
            deleted = (
                conn.execute(
                    "DELETE FROM assets WHERE asset_type = 'draft_pick' AND CAST(COALESCE(year, '') AS INTEGER) = ?",
                    (expiring_asset_year,),
                ).rowcount
                or 0
            )
            deleted_total += int(deleted)
            deleted_years.append({"year": expiring_asset_year, "count": int(deleted)})

        created: List[Dict[str, Any]] = []
        future_years: List[int] = []
        for season_year in range(int(previous_year) + 1, int(next_year) + 1):
            future_draft_year = int(season_year) + 7
            future_years.append(future_draft_year)
            created.extend(self._create_missing_future_draft_assets(conn, future_draft_year, timestamp))

        return {
            "deleted_draft_assets": deleted_total,
            "deleted_draft_asset_years": deleted_years,
            "future_draft_asset_years": future_years,
            "created_future_draft_assets": created,
        }

    def cleanup_inactive_dead_contracts(
        self,
        conn: sqlite3.Connection,
        current_year: int,
    ) -> Dict[str, Any]:
        active_seasons = [season for season in self.operations.contract_seasons if season >= int(current_year)]
        cur = conn.execute(
            """
            SELECT d.*, t.code AS team_code
            FROM dead_contracts d
            JOIN teams t ON t.id = d.team_id
            ORDER BY d.id
            """
        )
        removed: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            dead_contract = self.operations.row_to_dict(cur, row)
            has_active_salary = any(
                self.operations.dead_contract_salary_num(dead_contract, season) > 0
                for season in active_seasons
            )
            if has_active_salary:
                continue
            removed.append(
                {
                    "id": int(dead_contract["id"]),
                    "team_code": dead_contract.get("team_code"),
                    "label": dead_contract.get("label"),
                }
            )

        if removed:
            conn.executemany(
                "DELETE FROM dead_contracts WHERE id = ?",
                [(item["id"],) for item in removed],
            )

        return {
            "count": len(removed),
            "dead_contracts": removed,
        }
