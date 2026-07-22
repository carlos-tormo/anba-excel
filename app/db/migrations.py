"""Runtime schema migrations and one-time data backfills."""

from __future__ import annotations

import json
import logging
import math
import secrets
import sqlite3
from datetime import UTC, datetime
from typing import Any, Dict, List

try:
    from ..auth.policies import normalize_team_code, normalize_team_codes
    from ..domain_rules import (
        ROSTER_STANDARD_MAX_DEFAULT,
        ROSTER_STANDARD_MIN_DEFAULT,
        ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT,
        ROSTER_TWO_WAY_MAX_DEFAULT,
        ROSTER_TWO_WAY_MIN_DEFAULT,
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
    )
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code, normalize_team_codes
    from domain_rules import (
        ROSTER_STANDARD_MAX_DEFAULT,
        ROSTER_STANDARD_MIN_DEFAULT,
        ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT,
        ROSTER_TWO_WAY_MAX_DEFAULT,
        ROSTER_TWO_WAY_MIN_DEFAULT,
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
    )


logger = logging.getLogger("anba.migrations")
CURRENT_SCHEMA_VERSION = 2026072201
CURRENT_SCHEMA_MIGRATION_KEY = f"{CURRENT_SCHEMA_VERSION}_runtime_schema_contract"
MIGRATION_CONTRACT_SEASONS = (2025, 2026, 2027, 2028, 2029, 2030, 2031)
MIGRATION_PLAYER_ROW_STATE_ACTIVE = "active_contract"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
    return {cursor.description[idx][0]: row[idx] for idx in range(len(cursor.description))}


def dead_contract_salary_num(dead_contract: Dict[str, Any], season: int) -> float:
    value = dead_contract.get(f"salary_{season}_num")
    if value is not None:
        return float(value or 0.0)
    text_value = parse_amount_like(dead_contract.get(f"salary_{season}_text"))
    if text_value is not None:
        return text_value
    if season == 2025:
        amount_value = dead_contract.get("amount_num")
        if amount_value is not None:
            return float(amount_value or 0.0)
        return parse_amount_like(dead_contract.get("amount_text")) or 0.0
    return 0.0


DEFAULT_TEAM_ECONOMY_2025 = {
    "ATL": {"balance": 49_905_105, "revenue": 372_450_359, "expenses": -322_545_254},
    "BKN": {"balance": 117_587_256, "revenue": 493_925_372, "expenses": -376_338_116},
    "BOS": {"balance": 271_569_320, "revenue": 728_354_717, "expenses": -456_785_397},
    "CHA": {"balance": 105_567_971, "revenue": 452_264_896, "expenses": -346_696_925},
    "CHI": {"balance": 78_874_566, "revenue": 367_686_721, "expenses": -288_812_156},
    "CLE": {"balance": 40_491_791, "revenue": 430_701_221, "expenses": -390_209_430},
    "DAL": {"balance": 74_154_395, "revenue": 439_141_781, "expenses": -364_987_386},
    "DEN": {"balance": -68_704_521, "revenue": 319_379_550, "expenses": -388_084_072},
    "DET": {"balance": 45_663_887, "revenue": 319_379_550, "expenses": -273_715_663},
    "GSW": {"balance": 90_139_132, "revenue": 509_431_397, "expenses": -419_292_264},
    "HOU": {"balance": -13_142_400, "revenue": 319_379_550, "expenses": -332_521_951},
    "IND": {"balance": 63_445_621, "revenue": 319_379_550, "expenses": -255_933_930},
    "LAC": {"balance": 150_815_622, "revenue": 484_347_099, "expenses": -333_531_477},
    "LAL": {"balance": 129_196_200, "revenue": 508_030_229, "expenses": -378_834_030},
    "MEM": {"balance": 70_112_249, "revenue": 351_073_054, "expenses": -280_960_805},
    "MIA": {"balance": 69_616_115, "revenue": 319_379_550, "expenses": -249_763_436},
    "MIL": {"balance": 128_048_578, "revenue": 550_158_841, "expenses": -422_110_263},
    "MIN": {"balance": 143_281_108, "revenue": 594_585_479, "expenses": -451_304_371},
    "NOP": {"balance": 11_427_349, "revenue": 411_477_236, "expenses": -400_049_887},
    "NYK": {"balance": 245_587_170, "revenue": 834_758_507, "expenses": -589_171_337},
    "OKC": {"balance": 48_191_383, "revenue": 547_273_877, "expenses": -499_082_494},
    "ORL": {"balance": 123_982_201, "revenue": 395_622_337, "expenses": -271_640_136},
    "PHI": {"balance": 362_234, "revenue": 393_675_990, "expenses": -393_313_756},
    "PHX": {"balance": 102_680_681, "revenue": 385_631_796, "expenses": -282_951_115},
    "POR": {"balance": -2_020_711, "revenue": 319_379_550, "expenses": -321_400_262},
    "SAC": {"balance": 46_630_060, "revenue": 335_185_585, "expenses": -288_555_525},
    "SAS": {"balance": 114_538_993, "revenue": 437_211_980, "expenses": -322_672_987},
    "TOR": {"balance": 18_099_517, "revenue": 319_379_550, "expenses": -301_280_033},
    "UTA": {"balance": 149_600_215, "revenue": 416_369_384, "expenses": -266_769_169},
    "WAS": {"balance": -26_571_779, "revenue": 355_917_635, "expenses": -382_489_415},
}


class DatabaseMigrationsMixin:
    @staticmethod
    def _migration_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone() is not None

    @staticmethod
    def _migration_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        return {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

    @classmethod
    def _migration_ensure_column(
        cls,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_ddl: str,
    ) -> None:
        if not cls._migration_table_exists(conn, table_name):
            return
        if column_name in cls._migration_table_columns(conn, table_name):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}")

    @staticmethod
    def _migration_current_year(conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'current_year'"
        ).fetchone()
        return parse_int(row["value"] if row else None) or MIGRATION_CONTRACT_SEASONS[0]

    @staticmethod
    def _migration_players_have_row_state(conn: sqlite3.Connection) -> bool:
        return any(
            row["name"] == "row_state"
            for row in conn.execute("PRAGMA table_info(players)").fetchall()
        )

    def _migration_infer_player_row_state(
        self,
        conn: sqlite3.Connection,
        player: sqlite3.Row,
        current_year: int,
    ) -> str:
        if self._player_row_is_retained_rights_only(player, current_year, conn):
            return "retained_rights"
        return MIGRATION_PLAYER_ROW_STATE_ACTIVE

    @classmethod
    def _migration_duplicate_active_profile_ids(cls, conn: sqlite3.Connection) -> List[int]:
        if not cls._migration_players_have_row_state(conn):
            return []
        rows = conn.execute(
            """SELECT profile_id FROM players
               WHERE profile_id IS NOT NULL AND row_state = ?
               GROUP BY profile_id HAVING COUNT(*) > 1""",
            (MIGRATION_PLAYER_ROW_STATE_ACTIVE,),
        ).fetchall()
        return [
            int(row["profile_id"])
            for row in rows
            if parse_int(row["profile_id"]) is not None
        ]

    @staticmethod
    def _migration_player_profile_exists(conn: sqlite3.Connection, profile_id: Any) -> bool:
        parsed = parse_int(profile_id)
        return parsed is not None and conn.execute(
            "SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1", (parsed,)
        ).fetchone() is not None

    @staticmethod
    def _migration_create_player_profile(
        conn: sqlite3.Connection,
        name: Any,
        experience_years: Any = None,
        reference_image_url: Any = None,
        profile_notes: Any = None,
        timestamp: str | None = None,
    ) -> int:
        created_at = timestamp or now_iso()
        cur = conn.execute(
            """INSERT INTO player_profiles (
                   name, experience_years, reference_image_url, profile_notes,
                   created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(name or "").strip() or "New Player",
                parse_int(experience_years),
                str(reference_image_url or "").strip() or None,
                str(profile_notes or "").strip() or None,
                created_at,
                created_at,
            ),
        )
        return int(cur.lastrowid)

    @staticmethod
    def _migration_clean_salary_value(salary_text: Any, salary_num: Any) -> Dict[str, Any]:
        text = str(salary_text or "").strip() or None
        numeric = parse_float(salary_num)
        if numeric is None and text:
            numeric = parse_amount_like(text)
        if numeric is not None and not math.isfinite(float(numeric)):
            numeric = None
        return {"text": text, "num": float(numeric) if numeric is not None else None}

    @classmethod
    def _migration_upsert_player_salary_history_row(
        cls,
        conn: sqlite3.Connection,
        *,
        profile_id: Any,
        player_id: Any,
        team_code: Any,
        season_year: Any,
        salary_text: Any,
        salary_num: Any,
        source: str,
        salary_type: Any = None,
        timestamp: str | None = None,
    ) -> bool:
        profile = parse_int(profile_id)
        season = parse_int(season_year)
        if profile is None or season is None or not cls._migration_player_profile_exists(conn, profile):
            return False
        cleaned = cls._migration_clean_salary_value(salary_text, salary_num)
        if cleaned["text"] is None and cleaned["num"] is None:
            return False
        created_at = timestamp or now_iso()
        conn.execute(
            """INSERT INTO player_salary_history (
                   profile_id, player_id, team_code, season_year, salary_text,
                   salary_num, salary_type, source, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id, season_year) DO UPDATE SET
                   player_id = COALESCE(excluded.player_id, player_salary_history.player_id),
                   team_code = COALESCE(excluded.team_code, player_salary_history.team_code),
                   salary_text = COALESCE(excluded.salary_text, player_salary_history.salary_text),
                   salary_num = COALESCE(excluded.salary_num, player_salary_history.salary_num),
                   salary_type = COALESCE(excluded.salary_type, player_salary_history.salary_type),
                   source = excluded.source, updated_at = excluded.updated_at""",
            (
                profile,
                parse_int(player_id),
                normalize_team_code(team_code),
                season,
                cleaned["text"],
                cleaned["num"],
                str(salary_type or "").strip() or None,
                str(source or "unknown").strip() or "unknown",
                created_at,
                created_at,
            ),
        )
        return True

    @staticmethod
    def _migration_unique_profile_name_map(conn: sqlite3.Connection) -> Dict[str, int]:
        rows = conn.execute(
            """SELECT lower(trim(name)) AS name_key, MIN(id) AS id, COUNT(*) AS count
               FROM player_profiles WHERE COALESCE(trim(name), '') != ''
               GROUP BY lower(trim(name)) HAVING COUNT(*) = 1"""
        ).fetchall()
        return {str(row["name_key"]): int(row["id"]) for row in rows if row["name_key"]}

    @staticmethod
    def _migration_normalize_pick_round(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"2", "2nd", "second", "segunda", "segunda ronda"}:
            return "2nd"
        return "1st"

    @staticmethod
    def _migration_normalize_pick_type(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"sold", "vendida", "vendido"}:
            return "sold"
        if text in {"conditional", "condicional"}:
            return "conditional"
        if text in {"acquired", "adquirida", "adquirido"}:
            return "acquired"
        return "own"

    def _migration_upsert_draft_pick_identity(
        self,
        conn: sqlite3.Connection,
        draft_year: Any,
        draft_round: Any,
        original_team: Any,
        timestamp: str | None = None,
    ) -> int | None:
        year = parse_int(draft_year)
        round_value = self._migration_normalize_pick_round(draft_round)
        team_code = normalize_team_code(original_team)
        if year is None or round_value not in {"1st", "2nd"} or not team_code:
            return None
        created_at = timestamp or now_iso()
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

    def _migration_sync_draft_pick_asset_identity(
        self,
        conn: sqlite3.Connection,
        asset_id: Any,
        timestamp: str | None = None,
    ) -> None:
        parsed_asset_id = parse_int(asset_id)
        if parsed_asset_id is None:
            return
        if not self._migration_table_exists(conn, "draft_picks"):
            return
        if not self._migration_table_exists(conn, "draft_pick_holdings"):
            return
        created_at = timestamp or now_iso()
        conn.execute("DELETE FROM draft_pick_holdings WHERE asset_id = ?", (parsed_asset_id,))
        row = conn.execute(
            """SELECT a.*, t.code AS holder_team FROM assets a
               JOIN teams t ON t.id = a.team_id
               WHERE a.id = ? AND a.asset_type = 'draft_pick'""",
            (parsed_asset_id,),
        ).fetchone()
        if not row:
            return
        draft_year = parse_int(row["year"])
        draft_round = self._migration_normalize_pick_round(row["draft_round"])
        holder_team = normalize_team_code(row["holder_team"])
        if draft_year is None or draft_round not in {"1st", "2nd"} or not holder_team:
            return
        pick_type = self._migration_normalize_pick_type(row["draft_pick_type"])
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
            draft_pick_id = self._migration_upsert_draft_pick_identity(
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

    def _enable_wal_mode(self) -> None:
        with self.connect() as conn:
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                logger.warning("SQLite WAL setup skipped: %s", exc)

    def _ensure_gm_free_agent_offer_requests_are_retained(self, conn: sqlite3.Connection) -> None:
            fk_rows = conn.execute("PRAGMA foreign_key_list(gm_free_agent_offer_requests)").fetchall()
            has_free_agent_cascade = any(
                str(row["table"]) == "free_agents"
                and str(row["from"]) == "free_agent_id"
                and str(row["on_delete"] or "").upper() == "CASCADE"
                for row in fk_rows
            )
            if not has_free_agent_cascade:
                return
    
            backup_table = f"gm_free_agent_offer_requests_old_{secrets.token_hex(4)}"
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")
            try:
                conn.execute(f"ALTER TABLE gm_free_agent_offer_requests RENAME TO {backup_table}")
                version_select = "COALESCE(version, 1)" if "version" in self._migration_table_columns(conn, backup_table) else "1"
                conn.execute(
                    """
                    CREATE TABLE gm_free_agent_offer_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        free_agent_id INTEGER NOT NULL,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        requester_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        requester_email TEXT,
                        requester_name TEXT,
                        offer_payload_json TEXT NOT NULL DEFAULT '{}',
                        offer_type TEXT NOT NULL DEFAULT 'free_agent_offer',
                        status TEXT NOT NULL DEFAULT 'pending',
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        admin_email TEXT,
                        admin_name TEXT,
                        admin_decision_note TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        decided_at TEXT
                    )
                    """
                )
                conn.execute(
                    f"""
                    INSERT INTO gm_free_agent_offer_requests (
                        id,
                        free_agent_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        offer_payload_json,
                        offer_type,
                        status,
                        version,
                        admin_email,
                        admin_name,
                        admin_decision_note,
                        created_at,
                        updated_at,
                        decided_at
                    )
                    SELECT
                        id,
                        free_agent_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        offer_payload_json,
                        offer_type,
                        status,
                        {version_select},
                        admin_email,
                        admin_name,
                        admin_decision_note,
                        created_at,
                        updated_at,
                        decided_at
                    FROM {backup_table}
                    """
                )
                conn.execute(f"DROP TABLE {backup_table}")
                conn.commit()
            finally:
                conn.execute("PRAGMA foreign_keys = ON")

    def _ensure_free_agent_offer_promises_support_manual_rows(self, conn: sqlite3.Connection) -> None:
            if not self._migration_table_exists(conn, "free_agent_offer_promises"):
                return
            columns = conn.execute("PRAGMA table_info(free_agent_offer_promises)").fetchall()
            request_col = next(
                (row for row in columns if str(row["name"]) == "gm_free_agent_offer_request_id"),
                None,
            )
            if request_col is None or int(request_col["notnull"] or 0) == 0:
                return
    
            backup_table = f"free_agent_offer_promises_old_{secrets.token_hex(4)}"
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")
            try:
                conn.execute(f"ALTER TABLE free_agent_offer_promises RENAME TO {backup_table}")
                conn.execute(
                    """
                    CREATE TABLE free_agent_offer_promises (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        gm_free_agent_offer_request_id INTEGER UNIQUE
                            REFERENCES gm_free_agent_offer_requests(id) ON DELETE CASCADE,
                        free_agent_id INTEGER,
                        profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL,
                        player_name TEXT NOT NULL,
                        team_code TEXT NOT NULL,
                        team_name TEXT,
                        agent_name TEXT,
                        season_year INTEGER,
                        season_label TEXT,
                        role TEXT NOT NULL,
                        offer_type TEXT,
                        contract_type TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        admin_email TEXT,
                        admin_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        decided_at TEXT
                    )
                    """
                )
                conn.execute(
                    f"""
                    INSERT INTO free_agent_offer_promises (
                        id,
                        gm_free_agent_offer_request_id,
                        free_agent_id,
                        profile_id,
                        player_name,
                        team_code,
                        team_name,
                        agent_name,
                        season_year,
                        season_label,
                        role,
                        offer_type,
                        contract_type,
                        status,
                        admin_email,
                        admin_name,
                        created_at,
                        updated_at,
                        decided_at
                    )
                    SELECT
                        id,
                        gm_free_agent_offer_request_id,
                        free_agent_id,
                        profile_id,
                        player_name,
                        team_code,
                        team_name,
                        agent_name,
                        season_year,
                        season_label,
                        role,
                        offer_type,
                        contract_type,
                        status,
                        admin_email,
                        admin_name,
                        created_at,
                        updated_at,
                        decided_at
                    FROM {backup_table}
                    """
                )
                conn.execute(f"DROP TABLE {backup_table}")
                conn.commit()
            finally:
                conn.execute("PRAGMA foreign_keys = ON")

    def ensure_auth_schema(self) -> None:
            self._enable_wal_mode()
            with self.transaction("IMMEDIATE") as conn:
                self._ensure_maintenance_schema(conn)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        google_sub TEXT UNIQUE,
                        email TEXT UNIQUE,
                        display_name TEXT,
                        avatar_url TEXT,
                        is_co_admin INTEGER NOT NULL DEFAULT 0,
                        agent_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_team_assignments (
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, team_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gm_option_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        requester_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        requester_email TEXT,
                        requester_name TEXT,
                        option_field TEXT NOT NULL,
                        option_value TEXT NOT NULL,
                        action TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        admin_email TEXT,
                        admin_name TEXT,
                        admin_decision_note TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        decided_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_gm_option_requests_status
                    ON gm_option_requests (status, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_gm_option_requests_pending_unique
                    ON gm_option_requests (player_id, option_field)
                    WHERE status = 'pending'
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gm_draft_pick_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        draft_order_id INTEGER NOT NULL REFERENCES draft_order(id) ON DELETE CASCADE,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        requester_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        requester_email TEXT,
                        requester_name TEXT,
                        option_value TEXT,
                        custom_text TEXT,
                        selection_text TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        admin_email TEXT,
                        admin_name TEXT,
                        admin_decision_note TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        decided_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_gm_draft_pick_requests_status
                    ON gm_draft_pick_requests (status, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_gm_draft_pick_requests_pending_unique
                    ON gm_draft_pick_requests (draft_order_id)
                    WHERE status = 'pending'
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gm_free_agent_offer_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        free_agent_id INTEGER NOT NULL,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        requester_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        requester_email TEXT,
                        requester_name TEXT,
                        offer_payload_json TEXT NOT NULL DEFAULT '{}',
                        offer_type TEXT NOT NULL DEFAULT 'free_agent_offer',
                        status TEXT NOT NULL DEFAULT 'pending',
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        admin_email TEXT,
                        admin_name TEXT,
                        admin_decision_note TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        decided_at TEXT
                    )
                    """
                )
                self._ensure_gm_free_agent_offer_requests_are_retained(conn)
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_gm_free_agent_offer_requests_status
                    ON gm_free_agent_offer_requests (status, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_gm_free_agent_offer_requests_pending_unique
                    ON gm_free_agent_offer_requests (free_agent_id, team_id)
                    WHERE status = 'pending'
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS free_agent_offer_promises (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        gm_free_agent_offer_request_id INTEGER UNIQUE
                            REFERENCES gm_free_agent_offer_requests(id) ON DELETE CASCADE,
                        free_agent_id INTEGER,
                        profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL,
                        player_name TEXT NOT NULL,
                        team_code TEXT NOT NULL,
                        team_name TEXT,
                        agent_name TEXT,
                        season_year INTEGER,
                        season_label TEXT,
                        role TEXT NOT NULL,
                        offer_type TEXT,
                        contract_type TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        admin_email TEXT,
                        admin_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        decided_at TEXT
                    )
                    """
                )
                self._ensure_free_agent_offer_promises_support_manual_rows(conn)
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_free_agent_offer_promises_status
                    ON free_agent_offer_promises (status, season_year, updated_at)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_free_agent_offer_promises_agent
                    ON free_agent_offer_promises (agent_name, status, updated_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS outbox_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        aggregate_type TEXT,
                        aggregate_id TEXT,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        payload_json TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        next_attempt_at TEXT,
                        available_at TEXT,
                        locked_at TEXT,
                        locked_by TEXT,
                        last_error_code TEXT,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        delivered_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_outbox_events_status_created
                    ON outbox_events (status, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_outbox_events_delivery_available
                    ON outbox_events (status, available_at, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_runs (
                        id TEXT PRIMARY KEY,
                        workflow_type TEXT NOT NULL,
                        state TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        actor_email TEXT,
                        actor_name TEXT,
                        reason TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_workflow_runs_type_state
                    ON workflow_runs (workflow_type, state, updated_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_transition_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        workflow_type TEXT NOT NULL,
                        resource_id TEXT NOT NULL,
                        actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        actor_email TEXT,
                        actor_name TEXT,
                        previous_state TEXT NOT NULL,
                        new_state TEXT NOT NULL,
                        reason TEXT,
                        command_id TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        UNIQUE (workflow_type, resource_id, command_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_workflow_transition_resource
                    ON workflow_transition_log (workflow_type, resource_id, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_workflow_transition_command
                    ON workflow_transition_log (command_id, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS coadmin_votes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'open',
                        created_by_email TEXT,
                        created_by_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        closed_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_coadmin_votes_status
                    ON coadmin_votes (status, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS coadmin_vote_scores (
                        vote_id INTEGER NOT NULL REFERENCES coadmin_votes(id) ON DELETE CASCADE,
                        voter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        voter_email TEXT,
                        voter_name TEXT,
                        voter_team_code TEXT,
                        target_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        score INTEGER NOT NULL CHECK(score >= 1 AND score <= 100),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (vote_id, voter_user_id, target_team_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS free_agent_interests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        free_agent_id INTEGER NOT NULL REFERENCES free_agents(id) ON DELETE CASCADE,
                        team_code TEXT NOT NULL,
                        submitted_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        submitted_by_email TEXT,
                        submitted_by_name TEXT,
                        economic_offer TEXT,
                        role_offer TEXT,
                        comments TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(free_agent_id, team_code)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_free_agent_interests_agent
                    ON free_agent_interests (free_agent_id, updated_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS free_agent_favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        free_agent_id INTEGER NOT NULL REFERENCES free_agents(id) ON DELETE CASCADE,
                        team_code TEXT NOT NULL,
                        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        user_email TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(free_agent_id, team_code)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_free_agent_favorites_agent
                    ON free_agent_favorites (free_agent_id, team_code)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS free_agent_team_appeal (
                        team_code TEXT PRIMARY KEY REFERENCES teams(code) ON DELETE CASCADE,
                        under_23_single REAL NOT NULL DEFAULT 0,
                        under_23_multi REAL NOT NULL DEFAULT 0,
                        age_23_26_single REAL NOT NULL DEFAULT 0,
                        age_23_26_multi REAL NOT NULL DEFAULT 0,
                        age_27_33_single REAL NOT NULL DEFAULT 0,
                        age_27_33_multi REAL NOT NULL DEFAULT 0,
                        over_34_single REAL NOT NULL DEFAULT 0,
                        over_34_multi REAL NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_free_agent_favorites_team
                    ON free_agent_favorites (team_code, updated_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gm_free_agent_spending_limits (
                        team_code TEXT PRIMARY KEY REFERENCES teams(code) ON DELETE CASCADE,
                        amount INTEGER NOT NULL DEFAULT 0,
                        updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        updated_by_email TEXT,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gm_minimum_target_status (
                        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        team_code TEXT REFERENCES teams(code) ON DELETE SET NULL,
                        answered INTEGER NOT NULL DEFAULT 0,
                        omitted INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gm_minimum_targets (
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        rank INTEGER NOT NULL CHECK(rank >= 1 AND rank <= 10),
                        free_agent_id INTEGER REFERENCES free_agents(id) ON DELETE SET NULL,
                        profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL,
                        player_name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, rank)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_gm_minimum_targets_free_agent
                    ON gm_minimum_targets (free_agent_id)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gm_minimum_target_handicaps (
                        team_code TEXT PRIMARY KEY REFERENCES teams(code) ON DELETE CASCADE,
                        handicap INTEGER NOT NULL DEFAULT 0 CHECK(handicap >= -9 AND handicap <= 0),
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_depth_charts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                        position TEXT NOT NULL,
                        depth_order INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(team_id, position, depth_order),
                        UNIQUE(team_id, player_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_team_depth_charts_team
                    ON team_depth_charts (team_id, position, depth_order)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_depth_chart_versions (
                        team_id INTEGER PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS free_agent_team_ruleouts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        free_agent_id INTEGER NOT NULL REFERENCES free_agents(id) ON DELETE CASCADE,
                        agent_name TEXT NOT NULL,
                        team_code TEXT NOT NULL REFERENCES teams(code) ON DELETE CASCADE,
                        created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        created_by_email TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(free_agent_id, agent_name, team_code)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_free_agent_team_ruleouts_client
                    ON free_agent_team_ruleouts (free_agent_id, agent_name, team_code)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_coadmin_vote_scores_vote
                    ON coadmin_vote_scores (vote_id)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        email TEXT,
                        title TEXT NOT NULL,
                        body TEXT,
                        kind TEXT NOT NULL DEFAULT 'info',
                        entity_type TEXT,
                        entity_id TEXT,
                        read_at TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_user_notifications_user_read
                    ON user_notifications (user_id, read_at, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_user_notifications_email_read
                    ON user_notifications (email, read_at, created_at)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('salary_cap_2025', '154647000', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('salary_floor_2025', '139182300', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('current_year', '2025', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('first_apron', '195945000', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('second_apron', '207824000', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('cash_limit_total', '0', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('trade_move_limit_pre30', '20', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('trade_move_limit_post30', '4', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    UPDATE app_settings
                    SET value = '20', updated_at = ?
                    WHERE key = 'trade_move_limit_pre30' AND value = '15'
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    UPDATE app_settings
                    SET value = '4', updated_at = ?
                    WHERE key = 'trade_move_limit_post30' AND value = '15'
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('trade_move_phase', 'pre30', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('free_agency_mode', '0', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('free_agent_reps', '[]', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('free_agent_rep_discord_ids', '{}', ?)
                    """,
                    (now_iso(),),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                    VALUES ('discord_free_agent_offer_role_ping_enabled', '1', ?)
                    """,
                    (now_iso(),),
                )
                roster_defaults = {
                    "roster_standard_min": ROSTER_STANDARD_MIN_DEFAULT,
                    "roster_standard_max": ROSTER_STANDARD_MAX_DEFAULT,
                    "roster_standard_offseason_max": ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT,
                    "roster_two_way_min": ROSTER_TWO_WAY_MIN_DEFAULT,
                    "roster_two_way_max": ROSTER_TWO_WAY_MAX_DEFAULT,
                }
                for key, value in roster_defaults.items():
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (key, str(value), now_iso()),
                    )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dead_contracts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL,
                        row_order INTEGER NOT NULL DEFAULT 0,
                        dead_type TEXT NOT NULL DEFAULT 'normal',
                        label TEXT,
                        amount_text TEXT,
                        amount_num REAL,
                        exclude_from_gasto INTEGER NOT NULL DEFAULT 0,
                        exclude_from_cap INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS free_agents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL,
                        name TEXT NOT NULL,
                        position TEXT,
                        bird_rights TEXT,
                        rating TEXT,
                        years_left REAL,
                        free_agent_type TEXT NOT NULL DEFAULT 'No restringido',
                        source TEXT,
                        rights_team_code TEXT,
                        agent TEXT,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS waiver_players (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
                        profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL,
                        from_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        from_team_code TEXT NOT NULL,
                        player_name TEXT NOT NULL,
                        position TEXT,
                        rating TEXT,
                        bird_rights TEXT,
                        years_left REAL,
                        contract_json TEXT NOT NULL,
                        waiver_expires_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        claimed_team_code TEXT,
                        free_agent_id INTEGER REFERENCES free_agents(id) ON DELETE SET NULL,
                        dead_contract_id INTEGER REFERENCES dead_contracts(id) ON DELETE SET NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS waiver_claims (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        waiver_player_id INTEGER NOT NULL REFERENCES waiver_players(id) ON DELETE CASCADE,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        team_code TEXT NOT NULL,
                        requester_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        requester_email TEXT,
                        requester_name TEXT,
                        contingent_cut_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        admin_email TEXT,
                        admin_name TEXT,
                        admin_decision_note TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        decided_at TEXT,
                        UNIQUE(waiver_player_id, team_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_waiver_players_status
                    ON waiver_players (status, waiver_expires_at)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_waiver_claims_status
                    ON waiver_claims (status, created_at)
                    """
                )
                for workflow_table in (
                    "gm_option_requests",
                    "gm_draft_pick_requests",
                    "gm_free_agent_offer_requests",
                    "workflow_runs",
                    "waiver_players",
                    "waiver_claims",
                ):
                    self._migration_ensure_column(
                        conn,
                        workflow_table,
                        "version",
                        "INTEGER NOT NULL DEFAULT 1",
                    )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS discord_free_agent_offer_threads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        profile_id INTEGER,
                        player_name_key TEXT NOT NULL,
                        player_name TEXT NOT NULL,
                        thread_id TEXT NOT NULL,
                        thread_name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_fa_offer_threads_profile
                    ON discord_free_agent_offer_threads (profile_id)
                    WHERE profile_id IS NOT NULL
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_fa_offer_threads_name_key
                    ON discord_free_agent_offer_threads (player_name_key)
                    WHERE profile_id IS NULL
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_articles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        body TEXT NOT NULL,
                        image_blob BLOB,
                        image_mime_type TEXT,
                        discord_channel_id TEXT,
                        discord_message_id TEXT,
                        created_by_email TEXT,
                        created_by_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_news_articles_created_at
                    ON news_articles (created_at DESC, id DESC)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        actor_email TEXT,
                        actor_name TEXT,
                        actor_role TEXT,
                        actor_user_id INTEGER,
                        request_id TEXT,
                        method TEXT,
                        path TEXT,
                        action TEXT NOT NULL,
                        entity TEXT NOT NULL,
                        entity_id TEXT,
                        team_code TEXT,
                        team_codes_json TEXT,
                        player_id TEXT,
                        profile_id TEXT,
                        before_json TEXT,
                        after_json TEXT,
                        command_id TEXT,
                        validation_result TEXT,
                        entity_versions_json TEXT,
                        integration_outbox_ids_json TEXT,
                        details_json TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS season_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        season_year INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_move_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team_id INTEGER NOT NULL,
                        season_year INTEGER NOT NULL,
                        bucket TEXT NOT NULL,
                        delta INTEGER NOT NULL,
                        source_type TEXT NOT NULL,
                        source_ref TEXT,
                        note TEXT,
                        detail_json TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(team_id) REFERENCES teams(id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_luxury_history (
                        team_id INTEGER NOT NULL,
                        season_year INTEGER NOT NULL,
                        repeater INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (team_id, season_year),
                        FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_apron_hard_caps (
                        team_id INTEGER NOT NULL,
                        season_year INTEGER NOT NULL,
                        hard_cap TEXT,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (team_id, season_year),
                        FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_gm_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        row_order INTEGER NOT NULL,
                        gm_name TEXT NOT NULL,
                        start_date TEXT NOT NULL,
                        color TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS draft_order (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        draft_year INTEGER NOT NULL,
                        draft_round TEXT NOT NULL,
                        pick_number INTEGER NOT NULL,
                        owner_team_code TEXT NOT NULL,
                        original_team_code TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(draft_year, draft_round, pick_number)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS draft_live_state (
                        draft_year INTEGER PRIMARY KEY,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        current_draft_order_id INTEGER,
                        duration_seconds INTEGER NOT NULL DEFAULT 180,
                        started_at TEXT,
                        options_text TEXT,
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(current_draft_order_id) REFERENCES draft_order(id) ON DELETE SET NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS draft_live_selections (
                        draft_order_id INTEGER PRIMARY KEY,
                        selection_text TEXT,
                        option_value TEXT,
                        custom_text TEXT,
                        skipped INTEGER NOT NULL DEFAULT 0,
                        selected_by_email TEXT,
                        selected_by_name TEXT,
                        selected_by_role TEXT,
                        selected_at TEXT,
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(draft_order_id) REFERENCES draft_order(id) ON DELETE CASCADE
                    )
                    """
                )
                draft_live_selection_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(draft_live_selections)").fetchall()
                }
                if "processed_type" not in draft_live_selection_cols:
                    conn.execute("ALTER TABLE draft_live_selections ADD COLUMN processed_type TEXT")
                if "processed_dead_contract_id" not in draft_live_selection_cols:
                    conn.execute("ALTER TABLE draft_live_selections ADD COLUMN processed_dead_contract_id INTEGER")
                if "processed_asset_id" not in draft_live_selection_cols:
                    conn.execute("ALTER TABLE draft_live_selections ADD COLUMN processed_asset_id INTEGER")
                if "processed_at" not in draft_live_selection_cols:
                    conn.execute("ALTER TABLE draft_live_selections ADD COLUMN processed_at TEXT")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_economy (
                        team_id INTEGER NOT NULL,
                        season_year INTEGER NOT NULL,
                        balance REAL NOT NULL DEFAULT 0,
                        revenue REAL NOT NULL DEFAULT 0,
                        expenses REAL NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (team_id, season_year),
                        FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_owner_office (
                        team_id INTEGER NOT NULL,
                        season_year INTEGER NOT NULL,
                        confidence_current TEXT,
                        confidence_change TEXT,
                        new_gm_after_dismissal INTEGER NOT NULL DEFAULT 0,
                        gm_midseason_arrival INTEGER NOT NULL DEFAULT 0,
                        season_goal_set TEXT,
                        season_goal_achieved TEXT,
                        revenue TEXT,
                        expenses TEXT,
                        balance TEXT,
                        income_json TEXT NOT NULL DEFAULT '[]',
                        expenses_json TEXT NOT NULL DEFAULT '[]',
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (team_id, season_year),
                        FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_owner_profiles (
                        team_id INTEGER PRIMARY KEY,
                        owner_name TEXT,
                        owner_birth_date TEXT,
                        owner_photo_url TEXT,
                        owner_office_background_url TEXT,
                        owner_office_background_blob BLOB,
                        owner_office_background_mime TEXT,
                        owner_bio TEXT,
                        ambicion_competitiva INTEGER,
                        paciencia INTEGER,
                        intervencionismo INTEGER,
                        orientacion_financiera INTEGER,
                        orientacion_marca INTEGER,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS player_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        date_of_birth TEXT,
                        nationality TEXT,
                        experience_years INTEGER,
                        yos_source TEXT,
                        reference_image_url TEXT,
                        profile_notes TEXT,
                        transaction_notes TEXT,
                        happiness REAL NOT NULL DEFAULT 0,
                        profile_status TEXT NOT NULL DEFAULT 'active',
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS player_salary_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        profile_id INTEGER REFERENCES player_profiles(id) ON DELETE CASCADE,
                        player_id INTEGER,
                        team_code TEXT,
                        season_year INTEGER NOT NULL,
                        salary_text TEXT,
                        salary_num REAL,
                        salary_type TEXT,
                        source TEXT NOT NULL DEFAULT 'season_rollover',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(profile_id, season_year)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS player_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        profile_id INTEGER NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
                        player_id INTEGER,
                        free_agent_id INTEGER,
                        dead_contract_id INTEGER,
                        action TEXT NOT NULL,
                        team_code TEXT,
                        from_team_code TEXT,
                        to_team_code TEXT,
                        summary TEXT NOT NULL,
                        details_json TEXT,
                        source_log_id INTEGER,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS owner_exit_interviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team_id INTEGER NOT NULL,
                        season_year INTEGER NOT NULL,
                        gm_user_id INTEGER,
                        gm_email TEXT,
                        gm_name TEXT,
                        status TEXT NOT NULL DEFAULT 'available',
                        owner_message TEXT,
                        gm_response TEXT,
                        owner_final_message TEXT,
                        owner_conclusion_message TEXT,
                        trust_delta INTEGER,
                        previous_trust TEXT,
                        proposed_trust_delta INTEGER,
                        bounded_trust_delta INTEGER,
                        trust_model TEXT,
                        prompt_template_version TEXT,
                        administrator_override INTEGER NOT NULL DEFAULT 0,
                        conversation_id TEXT,
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT,
                        UNIQUE(team_id, season_year),
                        FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
                        FOREIGN KEY(gm_user_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                    """
                )
                self._drop_player_identity_guards(conn)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_token TEXT PRIMARY KEY,
                        data_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                    ON sessions(expires_at)
                    """
                )
                session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
                if "session_token_hash" not in session_columns:
                    conn.execute("ALTER TABLE sessions ADD COLUMN session_token_hash TEXT")
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_token_hash
                    ON sessions(session_token_hash)
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_players_team_id ON players(team_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_team_type ON assets(team_id, asset_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_dead_contracts_team_id ON dead_contracts(team_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_free_agents_name ON free_agents(name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_team_move_logs_team_season ON team_move_logs(team_id, season_year, bucket)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_team_luxury_history_team_year ON team_luxury_history(team_id, season_year)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_team_apron_hard_caps_team_year ON team_apron_hard_caps(team_id, season_year)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_team_gm_history_team_start ON team_gm_history(team_id, start_date)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_order_year_round ON draft_order(draft_year, draft_round, pick_number)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_live_selections_selected_at ON draft_live_selections(selected_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_team_economy_season ON team_economy(season_year)")
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_owner_exit_interviews_team_season
                    ON owner_exit_interviews(team_id, season_year)
                    """
                )
                economy_timestamp = now_iso()
                for code, values in DEFAULT_TEAM_ECONOMY_2025.items():
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO team_economy (
                            team_id, season_year, balance, revenue, expenses, updated_at
                        )
                        SELECT id, 2025, ?, ?, ?, ?
                        FROM teams
                        WHERE code = ?
                        """,
                        (
                            float(values["balance"]),
                            float(values["revenue"]),
                            float(values["expenses"]),
                            economy_timestamp,
                            code,
                        ),
                    )
                cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(players)").fetchall()
                }
                team_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(teams)").fetchall()
                }
                owner_office_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(team_owner_office)").fetchall()
                }
                owner_exit_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(owner_exit_interviews)").fetchall()
                }
                outbox_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(outbox_events)").fetchall()
                }
                owner_profile_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(team_owner_profiles)").fetchall()
                }
                admin_log_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(admin_logs)").fetchall()
                }
                user_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(users)").fetchall()
                }
                gm_minimum_target_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(gm_minimum_targets)").fetchall()
                }
                outbox_add_columns = {
                    "next_attempt_at": "TEXT",
                    "available_at": "TEXT",
                    "locked_at": "TEXT",
                    "locked_by": "TEXT",
                    "last_error_code": "TEXT",
                }
                for col, ddl in outbox_add_columns.items():
                    if col not in outbox_cols:
                        conn.execute(f"ALTER TABLE outbox_events ADD COLUMN {col} {ddl}")
                conn.execute(
                    """
                    UPDATE outbox_events
                    SET available_at = COALESCE(available_at, next_attempt_at, created_at)
                    WHERE available_at IS NULL
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_outbox_events_delivery_available
                    ON outbox_events (status, available_at, created_at)
                    """
                )
                for table_name in (
                    "app_settings",
                    "draft_live_state",
                    "draft_live_selections",
                    "player_profiles",
                    "owner_exit_interviews",
                ):
                    self._migration_ensure_column(
                        conn,
                        table_name,
                        "version",
                        "INTEGER NOT NULL DEFAULT 1",
                    )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_depth_chart_versions (
                        team_id INTEGER PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
                        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                if "is_co_admin" not in user_cols:
                    conn.execute("ALTER TABLE users ADD COLUMN is_co_admin INTEGER NOT NULL DEFAULT 0")
                if "agent_name" not in user_cols:
                    conn.execute("ALTER TABLE users ADD COLUMN agent_name TEXT")
                if "role" not in gm_minimum_target_cols:
                    conn.execute("ALTER TABLE gm_minimum_targets ADD COLUMN role TEXT")
                admin_log_add_columns = {
                    "actor_role": "TEXT",
                    "actor_user_id": "INTEGER",
                    "request_id": "TEXT",
                    "method": "TEXT",
                    "path": "TEXT",
                    "team_codes_json": "TEXT",
                    "player_id": "TEXT",
                    "profile_id": "TEXT",
                    "before_json": "TEXT",
                    "after_json": "TEXT",
                    "command_id": "TEXT",
                    "validation_result": "TEXT",
                    "entity_versions_json": "TEXT",
                    "integration_outbox_ids_json": "TEXT",
                }
                for col, ddl in admin_log_add_columns.items():
                    if col not in admin_log_cols:
                        conn.execute(f"ALTER TABLE admin_logs ADD COLUMN {col} {ddl}")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_request_id ON admin_logs(request_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_profile_id ON admin_logs(profile_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_player_id ON admin_logs(player_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_command_id ON admin_logs(command_id)")
                if "performance_json" not in owner_office_cols:
                    conn.execute("ALTER TABLE team_owner_office ADD COLUMN performance_json TEXT NOT NULL DEFAULT '[]'")
                if "new_gm_after_dismissal" not in owner_office_cols:
                    conn.execute("ALTER TABLE team_owner_office ADD COLUMN new_gm_after_dismissal INTEGER NOT NULL DEFAULT 0")
                if "gm_midseason_arrival" not in owner_office_cols:
                    conn.execute("ALTER TABLE team_owner_office ADD COLUMN gm_midseason_arrival INTEGER NOT NULL DEFAULT 0")
                if "season_goal_set" not in owner_office_cols:
                    conn.execute("ALTER TABLE team_owner_office ADD COLUMN season_goal_set TEXT")
                if "season_goal_achieved" not in owner_office_cols:
                    conn.execute("ALTER TABLE team_owner_office ADD COLUMN season_goal_achieved TEXT")
                if "owner_conclusion_message" not in owner_exit_cols:
                    conn.execute("ALTER TABLE owner_exit_interviews ADD COLUMN owner_conclusion_message TEXT")
                owner_exit_add_columns = {
                    "previous_trust": "TEXT",
                    "proposed_trust_delta": "INTEGER",
                    "bounded_trust_delta": "INTEGER",
                    "trust_model": "TEXT",
                    "prompt_template_version": "TEXT",
                    "administrator_override": "INTEGER NOT NULL DEFAULT 0",
                    "conversation_id": "TEXT",
                }
                for col, ddl in owner_exit_add_columns.items():
                    if col not in owner_exit_cols:
                        conn.execute(f"ALTER TABLE owner_exit_interviews ADD COLUMN {col} {ddl}")
                if "owner_office_background_url" not in owner_profile_cols:
                    conn.execute("ALTER TABLE team_owner_profiles ADD COLUMN owner_office_background_url TEXT")
                if "owner_office_background_blob" not in owner_profile_cols:
                    conn.execute("ALTER TABLE team_owner_profiles ADD COLUMN owner_office_background_blob BLOB")
                if "owner_office_background_mime" not in owner_profile_cols:
                    conn.execute("ALTER TABLE team_owner_profiles ADD COLUMN owner_office_background_mime TEXT")
                if "cash_received" not in team_cols:
                    conn.execute("ALTER TABLE teams ADD COLUMN cash_received REAL NOT NULL DEFAULT 0")
                if "cash_sent" not in team_cols:
                    conn.execute("ALTER TABLE teams ADD COLUMN cash_sent REAL NOT NULL DEFAULT 0")
                if "apron_hard_cap" not in team_cols:
                    conn.execute("ALTER TABLE teams ADD COLUMN apron_hard_cap TEXT")
                settings_rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
                settings_map = {str(row["key"]): str(row["value"]) for row in settings_rows}
                current_year = parse_int(settings_map.get("current_year")) or 2025
                timestamp = now_iso()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO team_apron_hard_caps (team_id, season_year, hard_cap, updated_at)
                    SELECT id, ?, apron_hard_cap, ?
                    FROM teams
                    WHERE COALESCE(apron_hard_cap, '') != ''
                    """,
                    (int(current_year), timestamp),
                )
                option_cols = [f"option_{season}" for season in MIGRATION_CONTRACT_SEASONS]
                salary_cols = []
                for season in MIGRATION_CONTRACT_SEASONS:
                    salary_cols.append((f"salary_{season}_text", "TEXT"))
                    salary_cols.append((f"salary_{season}_num", "REAL"))
                for col, col_type in salary_cols:
                    if col not in cols:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} {col_type}")
                        cols.add(col)
                for col in option_cols:
                    if col not in cols:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT")
                        cols.add(col)
                if "provisional_amounts" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN provisional_amounts INTEGER NOT NULL DEFAULT 0")
                    cols.add("provisional_amounts")
                provisional_cols = [f"salary_{season}_provisional" for season in MIGRATION_CONTRACT_SEASONS]
                for col in provisional_cols:
                    if col not in cols:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                        cols.add(col)
                if "partially_guaranteed" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN partially_guaranteed INTEGER NOT NULL DEFAULT 0")
                    cols.add("partially_guaranteed")
                if "contract_notes" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN contract_notes INTEGER NOT NULL DEFAULT 0")
                    cols.add("contract_notes")
                partial_guarantee_bool_cols = [f"salary_{season}_partially_guaranteed" for season in MIGRATION_CONTRACT_SEASONS]
                partial_guarantee_text_cols = [f"salary_{season}_guaranteed_text" for season in MIGRATION_CONTRACT_SEASONS]
                contract_note_bool_cols = [f"salary_{season}_note" for season in MIGRATION_CONTRACT_SEASONS]
                contract_note_text_cols = [f"salary_{season}_note_text" for season in MIGRATION_CONTRACT_SEASONS]
                for col in partial_guarantee_bool_cols:
                    if col not in cols:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                        cols.add(col)
                for col in partial_guarantee_text_cols:
                    if col not in cols:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT")
                        cols.add(col)
                for col in contract_note_bool_cols:
                    if col not in cols:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                        cols.add(col)
                for col in contract_note_text_cols:
                    if col not in cols:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT")
                        cols.add(col)
                if "reference_image_url" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN reference_image_url TEXT")
                    cols.add("reference_image_url")
                if "experience_years" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN experience_years INTEGER")
                    cols.add("experience_years")
                if "signed_as_free_agent" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN signed_as_free_agent INTEGER NOT NULL DEFAULT 0")
                    cols.add("signed_as_free_agent")
                if "profile_notes" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN profile_notes TEXT")
                    cols.add("profile_notes")
                if "profile_id" not in cols:
                    conn.execute("ALTER TABLE players ADD COLUMN profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL")
                    cols.add("profile_id")
                if "row_state" not in cols:
                    conn.execute(
                        f"ALTER TABLE players ADD COLUMN row_state TEXT NOT NULL DEFAULT '{MIGRATION_PLAYER_ROW_STATE_ACTIVE}'"
                    )
                    cols.add("row_state")
                free_agent_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(free_agents)").fetchall()
                }
                if "profile_id" not in free_agent_cols:
                    conn.execute("ALTER TABLE free_agents ADD COLUMN profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL")
                if "agent" not in free_agent_cols:
                    conn.execute("ALTER TABLE free_agents ADD COLUMN agent TEXT")
                if "free_agent_type" not in free_agent_cols:
                    conn.execute("ALTER TABLE free_agents ADD COLUMN free_agent_type TEXT NOT NULL DEFAULT 'No restringido'")
                if "source" not in free_agent_cols:
                    conn.execute("ALTER TABLE free_agents ADD COLUMN source TEXT")
                if "rights_team_code" not in free_agent_cols:
                    conn.execute("ALTER TABLE free_agents ADD COLUMN rights_team_code TEXT")
                self._backfill_player_profiles(conn)
                self._backfill_player_row_states(conn)
                profile_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(player_profiles)").fetchall()
                }
                if "date_of_birth" not in profile_cols:
                    conn.execute("ALTER TABLE player_profiles ADD COLUMN date_of_birth TEXT")
                if "nationality" not in profile_cols:
                    conn.execute("ALTER TABLE player_profiles ADD COLUMN nationality TEXT")
                if "yos_source" not in profile_cols:
                    conn.execute("ALTER TABLE player_profiles ADD COLUMN yos_source TEXT")
                if "transaction_notes" not in profile_cols:
                    conn.execute("ALTER TABLE player_profiles ADD COLUMN transaction_notes TEXT")
                if "happiness" not in profile_cols:
                    conn.execute("ALTER TABLE player_profiles ADD COLUMN happiness REAL NOT NULL DEFAULT 0")
                if "profile_status" not in profile_cols:
                    conn.execute("ALTER TABLE player_profiles ADD COLUMN profile_status TEXT NOT NULL DEFAULT 'active'")
                salary_history_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(player_salary_history)").fetchall()
                }
                if "salary_type" not in salary_history_cols:
                    conn.execute("ALTER TABLE player_salary_history ADD COLUMN salary_type TEXT")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS player_profile_aliases (
                        old_profile_id INTEGER PRIMARY KEY,
                        target_profile_id INTEGER NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
                        reason TEXT NOT NULL DEFAULT 'merge',
                        actor TEXT,
                        details_json TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_player_profile_aliases_target
                    ON player_profile_aliases(target_profile_id)
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_players_profile_id ON players(profile_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_player_profiles_status ON player_profiles(profile_status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_free_agents_profile_id ON free_agents(profile_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_free_agents_source ON free_agents(source)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_player_profiles_name ON player_profiles(name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_player_salary_history_profile_season ON player_salary_history(profile_id, season_year)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_player_salary_history_player_season ON player_salary_history(player_id, season_year)")
                self._backfill_player_salary_numeric_values(conn)
                asset_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(assets)").fetchall()
                }
                if "draft_pick_type" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_type TEXT")
                if "draft_round" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_round TEXT")
                if "original_owner" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN original_owner TEXT")
                if "exception_type" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN exception_type TEXT")
                if "draft_pick_restricted" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_restricted INTEGER NOT NULL DEFAULT 0")
                if "draft_pick_stepien_restricted" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_stepien_restricted INTEGER NOT NULL DEFAULT 0")
                if "draft_pick_protected" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_protected INTEGER NOT NULL DEFAULT 0")
                if "draft_pick_sold_to" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_sold_to TEXT")
                if "draft_pick_conditional_teams" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_conditional_teams TEXT")
                if "draft_pick_frozen" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_frozen INTEGER NOT NULL DEFAULT 0")
                if "generated_exception_key" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN generated_exception_key TEXT")
                if "generated_exception_season" not in asset_cols:
                    conn.execute("ALTER TABLE assets ADD COLUMN generated_exception_season INTEGER")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS draft_picks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        draft_year INTEGER NOT NULL,
                        draft_round TEXT NOT NULL CHECK(draft_round IN ('1st', '2nd')),
                        original_team TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(draft_year, draft_round, original_team)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS draft_pick_holdings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        draft_pick_id INTEGER NOT NULL REFERENCES draft_picks(id) ON DELETE CASCADE,
                        holder_team TEXT NOT NULL,
                        asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
                        acquired_transaction_id INTEGER,
                        conditions TEXT,
                        frozen_status TEXT,
                        holding_type TEXT NOT NULL DEFAULT 'held',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(draft_pick_id, holder_team, asset_id)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_pick_holdings_pick ON draft_pick_holdings(draft_pick_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_pick_holdings_holder ON draft_pick_holdings(holder_team)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_pick_holdings_asset ON draft_pick_holdings(asset_id)")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS frozen_draft_picks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                        penalty_season_year INTEGER NOT NULL,
                        draft_year INTEGER NOT NULL,
                        draft_round TEXT NOT NULL DEFAULT '1st',
                        reason TEXT,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_frozen_draft_picks_unique
                    ON frozen_draft_picks(team_id, penalty_season_year, draft_year, draft_round)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_frozen_draft_picks_team
                    ON frozen_draft_picks(team_id, draft_year)
                    """
                )
                conn.execute(
                    """
                    UPDATE assets
                    SET exception_type = COALESCE(exception_type, label)
                    WHERE asset_type = 'exception' AND COALESCE(exception_type, '') = ''
                    """
                )
                dead_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(dead_contracts)").fetchall()
                }
                if "exclude_from_gasto" not in dead_cols:
                    conn.execute("ALTER TABLE dead_contracts ADD COLUMN exclude_from_gasto INTEGER NOT NULL DEFAULT 0")
                if "exclude_from_cap" not in dead_cols:
                    conn.execute("ALTER TABLE dead_contracts ADD COLUMN exclude_from_cap INTEGER NOT NULL DEFAULT 0")
                if "profile_id" not in dead_cols:
                    conn.execute("ALTER TABLE dead_contracts ADD COLUMN profile_id INTEGER REFERENCES player_profiles(id) ON DELETE SET NULL")
                    dead_cols.add("profile_id")
                for season in MIGRATION_CONTRACT_SEASONS:
                    text_col = f"salary_{season}_text"
                    num_col = f"salary_{season}_num"
                    if text_col not in dead_cols:
                        conn.execute(f"ALTER TABLE dead_contracts ADD COLUMN {text_col} TEXT")
                    if num_col not in dead_cols:
                        conn.execute(f"ALTER TABLE dead_contracts ADD COLUMN {num_col} REAL")
                conn.execute(
                    """
                    UPDATE dead_contracts
                    SET
                        salary_2025_text = COALESCE(salary_2025_text, amount_text),
                        salary_2025_num = COALESCE(salary_2025_num, amount_num)
                    WHERE salary_2025_text IS NULL OR salary_2025_num IS NULL
                    """
                )
                self._migrate_legacy_dead_cap_assets(conn)
                self._backfill_dead_contract_profiles(conn)
                self._backfill_draft_pick_identity(conn)
                self._backfill_player_transactions(conn)
                self._backfill_player_salary_history_from_snapshots(conn)
                current_year_row = conn.execute("SELECT value FROM app_settings WHERE key = 'current_year'").fetchone()
                current_year = parse_int(current_year_row["value"] if current_year_row else None)
                if current_year is not None:
                    self._season_rollover_repository.cleanup_inactive_dead_contracts(conn, current_year)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_dead_contracts_profile_id ON dead_contracts(profile_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_player_transactions_profile_created ON player_transactions(profile_id, created_at DESC, id DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_player_transactions_source_log ON player_transactions(source_log_id)")
                self._install_player_identity_guards(conn)
                self._record_schema_migration(
                    conn,
                    CURRENT_SCHEMA_MIGRATION_KEY,
                    "Runtime schema contract for ANBA app tables, indexes, compatibility columns, and player identity guards.",
                    "success",
                    {
                        "schema_version": CURRENT_SCHEMA_VERSION,
                        "schema_signature": self._schema_signature(conn),
                    },
                )
                conn.commit()

    def _drop_player_identity_guards(self, conn: sqlite3.Connection) -> None:
            conn.execute("DROP INDEX IF EXISTS idx_players_unique_active_profile")
            conn.execute("DROP INDEX IF EXISTS idx_draft_pick_holdings_one_current_holder")
            for table in ["players", "free_agents", "dead_contracts"]:
                conn.execute(f"DROP TRIGGER IF EXISTS trg_{table}_profile_required_insert")
                conn.execute(f"DROP TRIGGER IF EXISTS trg_{table}_profile_required_update")

    def _backfill_player_row_states(self, conn: sqlite3.Connection) -> int:
            if not self._migration_players_have_row_state(conn):
                return 0
            current_year = self._migration_current_year(conn)
            rows = conn.execute(
                """
                SELECT p.*, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                ORDER BY p.id
                """
            ).fetchall()
            changed = 0
            for row in rows:
                state = self._migration_infer_player_row_state(conn, row, current_year)
                if str(row["row_state"] or "") != state:
                    conn.execute("UPDATE players SET row_state = ? WHERE id = ?", (state, int(row["id"])))
                    changed += 1
            return changed

    def _backfill_draft_pick_identity(self, conn: sqlite3.Connection) -> None:
            if not self._migration_table_exists(conn, "assets"):
                return
            if not self._migration_table_exists(conn, "draft_picks") or not self._migration_table_exists(conn, "draft_pick_holdings"):
                return
            rows = conn.execute(
                "SELECT id FROM assets WHERE asset_type = 'draft_pick' ORDER BY id"
            ).fetchall()
            now = now_iso()
            for row in rows:
                self._migration_sync_draft_pick_asset_identity(conn, row["id"], now)

    def _migrate_legacy_dead_cap_assets(self, conn: sqlite3.Connection) -> None:
            asset_cols = {row["name"] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
            if "asset_type" not in asset_cols:
                return
            dead_cols = {row["name"] for row in conn.execute("PRAGMA table_info(dead_contracts)").fetchall()}
            has_profile_id = "profile_id" in dead_cols
            rows = conn.execute(
                """
                SELECT id, team_id, row_order, label, amount_text, amount_num, created_at, updated_at
                FROM assets
                WHERE asset_type = 'dead_cap'
                ORDER BY id
                """
            ).fetchall()
            for row in rows:
                existing = conn.execute(
                    """
                    SELECT id
                    FROM dead_contracts
                    WHERE team_id = ?
                      AND row_order = ?
                      AND COALESCE(label, '') = COALESCE(?, '')
                    LIMIT 1
                    """,
                    (row["team_id"], row["row_order"], row["label"]),
                ).fetchone()
                if existing:
                    continue
    
                label = str(row["label"] or "").strip() or f"Dead Contract {int(row['id'])}"
                timestamp = row["created_at"] or row["updated_at"] or now_iso()
                profile_id = (
                    self._find_profile_id(conn, name=label)
                    or self._migration_create_player_profile(conn, label, timestamp=timestamp)
                )
                if has_profile_id:
                    conn.execute(
                        """
                        INSERT INTO dead_contracts (
                            team_id, profile_id, row_order, dead_type, label, amount_text, amount_num,
                            salary_2025_text, salary_2025_num, created_at, updated_at
                        )
                        VALUES (?, ?, ?, 'normal', ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["team_id"],
                            profile_id,
                            row["row_order"],
                            label,
                            row["amount_text"],
                            row["amount_num"],
                            row["amount_text"],
                            row["amount_num"],
                            row["created_at"] or timestamp,
                            row["updated_at"] or timestamp,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO dead_contracts (
                            team_id, row_order, dead_type, label, amount_text, amount_num,
                            salary_2025_text, salary_2025_num, created_at, updated_at
                        )
                        VALUES (?, ?, 'normal', ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["team_id"],
                            row["row_order"],
                            label,
                            row["amount_text"],
                            row["amount_num"],
                            row["amount_text"],
                            row["amount_num"],
                            row["created_at"] or timestamp,
                            row["updated_at"] or timestamp,
                        ),
                    )
    
            if rows:
                conn.execute("DELETE FROM assets WHERE asset_type = 'dead_cap'")

    def _install_player_identity_guards(self, conn: sqlite3.Connection) -> None:
            trigger_specs = [
                ("players", "players_profile_id_required"),
                ("free_agents", "free_agents_profile_id_required"),
                ("dead_contracts", "dead_contracts_profile_id_required"),
            ]
            for table, message in trigger_specs:
                conn.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS trg_{table}_profile_required_insert
                    BEFORE INSERT ON {table}
                    WHEN NEW.profile_id IS NULL
                    BEGIN
                        SELECT RAISE(ABORT, '{message}');
                    END
                    """
                )
                conn.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS trg_{table}_profile_required_update
                    BEFORE UPDATE OF profile_id ON {table}
                    WHEN NEW.profile_id IS NULL
                    BEGIN
                        SELECT RAISE(ABORT, '{message}');
                    END
                    """
                )
    
            if self._migration_players_have_row_state(conn):
                duplicate_profile_ids = self._migration_duplicate_active_profile_ids(conn)
                if duplicate_profile_ids:
                    sample = ", ".join(str(profile_id) for profile_id in duplicate_profile_ids[:10])
                    suffix = "..." if len(duplicate_profile_ids) > 10 else ""
                    logger.warning(
                        "Skipping idx_players_unique_active_profile; duplicate active profile_id values exist: %s%s",
                        sample,
                        suffix,
                    )
                else:
                    conn.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_players_unique_active_profile
                        ON players(profile_id)
                        WHERE profile_id IS NOT NULL
                          AND row_state = 'active_contract'
                        """
                    )

    def _backfill_player_profiles(self, conn: sqlite3.Connection) -> None:
            timestamp = now_iso()
            player_rows = conn.execute(
                """
                SELECT id, name, experience_years, reference_image_url, profile_notes, created_at, updated_at
                FROM players
                WHERE profile_id IS NULL
                ORDER BY id
                """
            ).fetchall()
            for row in player_rows:
                profile_id = self._migration_create_player_profile(
                    conn,
                    row["name"],
                    row["experience_years"],
                    row["reference_image_url"],
                    row["profile_notes"],
                    row["created_at"] or row["updated_at"] or timestamp,
                )
                conn.execute("UPDATE players SET profile_id = ? WHERE id = ?", (profile_id, int(row["id"])))
    
            free_agent_rows = conn.execute(
                """
                SELECT id, name, created_at, updated_at
                FROM free_agents
                WHERE profile_id IS NULL
                ORDER BY id
                """
            ).fetchall()
            for row in free_agent_rows:
                profile_id = self._migration_create_player_profile(
                    conn,
                    row["name"],
                    None,
                    None,
                    None,
                    row["created_at"] or row["updated_at"] or timestamp,
                )
                conn.execute("UPDATE free_agents SET profile_id = ? WHERE id = ?", (profile_id, int(row["id"])))
    
            self._backfill_dead_contract_profiles(conn)

    def _backfill_player_salary_numeric_values(self, conn: sqlite3.Connection) -> int:
            player_cols = {row["name"] for row in conn.execute("PRAGMA table_info(players)").fetchall()}
            updated = 0
            for season in MIGRATION_CONTRACT_SEASONS:
                text_col = f"salary_{season}_text"
                num_col = f"salary_{season}_num"
                if text_col not in player_cols or num_col not in player_cols:
                    continue
                rows = conn.execute(
                    f"""
                    SELECT id, {text_col} AS salary_text
                    FROM players
                    WHERE {num_col} IS NULL
                      AND COALESCE(TRIM({text_col}), '') != ''
                    """
                ).fetchall()
                for row in rows:
                    amount = parse_amount_like(row["salary_text"])
                    if amount is None:
                        continue
                    conn.execute(
                        f"UPDATE players SET {num_col} = ? WHERE id = ?",
                        (amount, int(row["id"])),
                    )
                    updated += 1
            return updated

    def _backfill_player_salary_history_from_snapshots(self, conn: sqlite3.Connection) -> int:
            snapshot_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'season_snapshots'"
            ).fetchone()
            history_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'player_salary_history'"
            ).fetchone()
            if not snapshot_table or not history_table:
                return 0
    
            active_profile_by_player_id = {
                int(row["id"]): int(row["profile_id"])
                for row in conn.execute(
                    """
                    SELECT p.id, p.profile_id
                    FROM players p
                    JOIN player_profiles pp ON pp.id = p.profile_id
                    WHERE p.profile_id IS NOT NULL
                    """
                ).fetchall()
            }
            profile_by_name = self._migration_unique_profile_name_map(conn)
            rows = conn.execute("SELECT season_year, payload_json, created_at FROM season_snapshots ORDER BY id").fetchall()
            count = 0
            for row in rows:
                try:
                    payload = json.loads(str(row["payload_json"] or "{}"))
                except json.JSONDecodeError:
                    continue
                snapshot_season = parse_int(payload.get("season_year")) or parse_int(row["season_year"])
                if snapshot_season is None:
                    continue
                teams_payload = payload.get("teams") or []
                if not isinstance(teams_payload, list):
                    continue
                for team_payload in teams_payload:
                    if not isinstance(team_payload, dict):
                        continue
                    team_info = team_payload.get("team") or {}
                    team_code = normalize_team_code(team_info.get("code") if isinstance(team_info, dict) else None)
                    players_payload = team_payload.get("players") or []
                    if not isinstance(players_payload, list):
                        continue
                    for player in players_payload:
                        if not isinstance(player, dict):
                            continue
                        profile_id = parse_int(player.get("profile_id"))
                        player_id = parse_int(player.get("id"))
                        if profile_id is not None and not self._migration_player_profile_exists(conn, profile_id):
                            profile_id = None
                        if profile_id is None and player_id is not None:
                            profile_id = active_profile_by_player_id.get(player_id)
                        if profile_id is None:
                            name_key = str(player.get("name") or "").strip().lower()
                            profile_id = profile_by_name.get(name_key)
                        if self._migration_upsert_player_salary_history_row(
                            conn,
                            profile_id=profile_id,
                            player_id=player_id,
                            team_code=team_code,
                            season_year=snapshot_season,
                            salary_text=player.get(f"salary_{snapshot_season}_text"),
                            salary_num=player.get(f"salary_{snapshot_season}_num"),
                            salary_type=player.get("bird_rights"),
                            source="season_snapshot",
                            timestamp=str(row["created_at"] or "") or now_iso(),
                        ):
                            count += 1
            return count

    def _backfill_dead_contract_profiles(self, conn: sqlite3.Connection) -> None:
            dead_cols = {row["name"] for row in conn.execute("PRAGMA table_info(dead_contracts)").fetchall()}
            if "profile_id" not in dead_cols:
                return
            rows = conn.execute(
                """
                SELECT id, label, created_at, updated_at
                FROM dead_contracts
                WHERE profile_id IS NULL
                ORDER BY id
                """
            ).fetchall()
            for row in rows:
                label = str(row["label"] or "").strip() or f"Dead Contract {int(row['id'])}"
                profile_id = self._find_profile_id(conn, name=label)
                if profile_id is None:
                    profile_id = self._migration_create_player_profile(
                        conn,
                        label,
                        timestamp=row["created_at"] or row["updated_at"] or now_iso(),
                    )
                if not str(row["label"] or "").strip():
                    conn.execute("UPDATE dead_contracts SET label = ? WHERE id = ?", (label, int(row["id"])))
                conn.execute("UPDATE dead_contracts SET profile_id = ? WHERE id = ?", (profile_id, int(row["id"])))

    def _backfill_player_transactions(self, conn: sqlite3.Connection) -> None:
            tx_exists = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'player_transactions'").fetchone()
            if not tx_exists:
                return
            log_cur = conn.execute(
                """
                SELECT id, created_at, action, entity, entity_id, team_code, details_json
                FROM admin_logs
                ORDER BY id
                """
            )
            for row in log_cur.fetchall():
                log = row_to_dict(log_cur, row)
                try:
                    details = json.loads(str(log.get("details_json") or "{}"))
                    if not isinstance(details, dict):
                        details = {}
                except json.JSONDecodeError:
                    details = {}
                action = str(log.get("action") or "").strip().lower()
                entity = str(log.get("entity") or "").strip().lower()
                source_log_id = parse_int(log.get("id"))
                created_at = str(log.get("created_at") or "") or now_iso()
    
                if entity == "trade" and action in {"trade", "process"}:
                    team_a = normalize_team_code(details.get("team_a"))
                    team_b = normalize_team_code(details.get("team_b"))
                    for player_id in details.get("players_a") or []:
                        profile_id = self._find_profile_id(conn, player_id=player_id)
                        if profile_id is None:
                            continue
                        summary = f"Traspasado de {team_a} a {team_b}" if team_a and team_b else "Traspaso procesado"
                        self._record_player_transaction(
                            conn,
                            profile_id,
                            "trade",
                            summary,
                            player_id=player_id,
                            team_code=team_b,
                            from_team_code=team_a,
                            to_team_code=team_b,
                            details=details,
                            source_log_id=source_log_id,
                            created_at=created_at,
                        )
                    for player_id in details.get("players_b") or []:
                        profile_id = self._find_profile_id(conn, player_id=player_id)
                        if profile_id is None:
                            continue
                        summary = f"Traspasado de {team_b} a {team_a}" if team_a and team_b else "Traspaso procesado"
                        self._record_player_transaction(
                            conn,
                            profile_id,
                            "trade",
                            summary,
                            player_id=player_id,
                            team_code=team_a,
                            from_team_code=team_b,
                            to_team_code=team_a,
                            details=details,
                            source_log_id=source_log_id,
                            created_at=created_at,
                        )
                    continue
    
                profile_id = parse_int(details.get("profile_id"))
                if profile_id is not None:
                    profile_exists = conn.execute(
                        "SELECT 1 FROM player_profiles WHERE id = ? LIMIT 1",
                        (profile_id,),
                    ).fetchone()
                    if not profile_exists:
                        profile_id = None
                if profile_id is None:
                    profile_id = self._find_profile_id(
                        conn,
                        player_id=log.get("entity_id") if entity == "player" else details.get("player_id"),
                        free_agent_id=log.get("entity_id") if entity == "free_agent" else details.get("free_agent_id"),
                        dead_contract_id=details.get("dead_contract_id"),
                        name=details.get("player_name") or details.get("name"),
                    )
                if profile_id is None:
                    continue
                self._record_player_transaction(
                    conn,
                    profile_id,
                    action,
                    self._player_log_summary(log, details),
                    player_id=log.get("entity_id") if entity == "player" else details.get("player_id"),
                    free_agent_id=log.get("entity_id") if entity == "free_agent" else details.get("free_agent_id"),
                    dead_contract_id=details.get("dead_contract_id"),
                    team_code=log.get("team_code"),
                    to_team_code=details.get("to_team_code"),
                    details=details,
                    source_log_id=source_log_id,
                    created_at=created_at,
                )
