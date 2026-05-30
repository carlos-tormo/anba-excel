#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import secrets
import sqlite3
import tempfile
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DEFAULT_ENV_FILE = ROOT / ".env"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env_file(Path(os.getenv("ENV_FILE", str(DEFAULT_ENV_FILE))))


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_amount_like(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "e" in text.lower():
        try:
            parsed = float(text)
            return parsed if math.isfinite(parsed) else None
        except ValueError:
            return None
    cleaned = text.replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(".", "")
    cleaned = re.sub(r"[^0-9.-]", "", cleaned)
    if cleaned in {"", "-", "."}:
        return None
    try:
        parsed = float(cleaned)
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        return None


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "checked"}


def normalize_dead_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"two_way", "tw"}:
        return "two_way"
    return "normal"


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


def dead_contract_excluded_from_gasto(dead_contract: Dict[str, Any]) -> bool:
    return parse_bool(dead_contract.get("exclude_from_gasto"))


def dead_contract_excluded_from_cap(dead_contract: Dict[str, Any]) -> bool:
    return parse_bool(dead_contract.get("exclude_from_cap"))


def row_salary_num(row: Dict[str, Any], season: int) -> float:
    value = row.get(f"salary_{season}_num")
    if value is not None:
        return float(value or 0.0)
    return parse_amount_like(row.get(f"salary_{season}_text")) or 0.0


def normalize_pick_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"acquired", "sold", "conditional"}:
        return raw
    return "own"


def normalize_pick_round(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if "2" in raw:
        return "2nd"
    return "1st"


def normalize_team_code(value: Any) -> Optional[str]:
    code = str(value or "").strip().upper()
    return code if code else None


def normalize_team_codes(value: Any) -> List[str]:
    if value is None:
        raw_items: List[Any] = []
    elif isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raw_items = []
        else:
            try:
                parsed = json.loads(raw)
                raw_items = parsed if isinstance(parsed, list) else [raw]
            except json.JSONDecodeError:
                raw_items = re.split(r"[,/|]", raw)
    else:
        raw_items = [value]
    codes: List[str] = []
    for item in raw_items:
        code = normalize_team_code(item)
        if code and code not in codes:
            codes.append(code)
    return codes


def serialize_team_codes(value: Any) -> Optional[str]:
    codes = normalize_team_codes(value)
    return json.dumps(codes, ensure_ascii=True) if codes else None


def normalize_exception_type(value: Any) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if "tax" in raw:
        return "TAXPAYER Mid"
    if "room" in raw:
        return "ROOM Mid"
    if "bia" in raw:
        return "Bianual"
    if "traspas" in raw or "trade" in raw:
        return "Excepción de traspaso"
    if "mid" in raw:
        return "Mid-Level"
    return str(value).strip() or None


def normalize_move_phase(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "").replace("-", "")
    if raw in {"post30", "post"}:
        return "post30"
    return "pre30"


def normalize_trade_bucket(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "").replace("-", "")
    if raw in {"post30", "post"}:
        return "post30"
    return "pre30"


def normalize_apron_hard_cap(value: Any) -> Optional[str]:
    raw = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    if not raw:
        return None
    if raw in {"1", "1st", "first", "first apron", "1st apron"}:
        return "first"
    if raw in {"2", "2nd", "second", "second apron", "2nd apron"}:
        return "second"
    return None


def row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
    return {d[0]: row[idx] for idx, d in enumerate(cursor.description)}


class LeagueDB:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def backup_bytes(self) -> bytes:
        fd, tmp_path = tempfile.mkstemp(prefix="anba-backup-", suffix=".db")
        os.close(fd)
        try:
            with self.connect() as source:
                with sqlite3.connect(tmp_path) as target:
                    source.backup(target)
            with open(tmp_path, "rb") as fh:
                return fh.read()
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass

    def ensure_auth_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    google_sub TEXT UNIQUE,
                    email TEXT UNIQUE,
                    display_name TEXT,
                    avatar_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS dead_contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
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
                    name TEXT NOT NULL,
                    position TEXT,
                    bird_rights TEXT,
                    rating TEXT,
                    years_left REAL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    actor_email TEXT,
                    actor_name TEXT,
                    action TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    entity_id TEXT,
                    team_code TEXT,
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_players_team_id ON players(team_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_team_type ON assets(team_id, asset_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dead_contracts_team_id ON dead_contracts(team_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_free_agents_name ON free_agents(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_team_move_logs_team_season ON team_move_logs(team_id, season_year, bucket)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_team_luxury_history_team_year ON team_luxury_history(team_id, season_year)")
            cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(players)").fetchall()
            }
            team_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(teams)").fetchall()
            }
            if "cash_received" not in team_cols:
                conn.execute("ALTER TABLE teams ADD COLUMN cash_received REAL NOT NULL DEFAULT 0")
            if "cash_sent" not in team_cols:
                conn.execute("ALTER TABLE teams ADD COLUMN cash_sent REAL NOT NULL DEFAULT 0")
            if "apron_hard_cap" not in team_cols:
                conn.execute("ALTER TABLE teams ADD COLUMN apron_hard_cap TEXT")
            option_cols = [f"option_{season}" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            for col in option_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT")
            if "provisional_amounts" not in cols:
                conn.execute("ALTER TABLE players ADD COLUMN provisional_amounts INTEGER NOT NULL DEFAULT 0")
            provisional_cols = [f"salary_{season}_provisional" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            for col in provisional_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            if "partially_guaranteed" not in cols:
                conn.execute("ALTER TABLE players ADD COLUMN partially_guaranteed INTEGER NOT NULL DEFAULT 0")
            partial_guarantee_bool_cols = [f"salary_{season}_partially_guaranteed" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            partial_guarantee_text_cols = [f"salary_{season}_guaranteed_text" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            for col in partial_guarantee_bool_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            for col in partial_guarantee_text_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT")
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
            if "draft_pick_protected" not in asset_cols:
                conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_protected INTEGER NOT NULL DEFAULT 0")
            if "draft_pick_sold_to" not in asset_cols:
                conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_sold_to TEXT")
            if "draft_pick_conditional_teams" not in asset_cols:
                conn.execute("ALTER TABLE assets ADD COLUMN draft_pick_conditional_teams TEXT")
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
            for season in [2025, 2026, 2027, 2028, 2029, 2030]:
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
            conn.execute(
                """
                INSERT INTO dead_contracts (
                    team_id, row_order, dead_type, label, amount_text, amount_num,
                    salary_2025_text, salary_2025_num, created_at, updated_at
                )
                SELECT
                    a.team_id,
                    a.row_order,
                    'normal',
                    a.label,
                    a.amount_text,
                    a.amount_num,
                    a.amount_text,
                    a.amount_num,
                    a.created_at,
                    a.updated_at
                FROM assets a
                WHERE a.asset_type = 'dead_cap'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM dead_contracts d
                    WHERE d.team_id = a.team_id
                      AND d.row_order = a.row_order
                      AND COALESCE(d.label, '') = COALESCE(a.label, '')
                  )
                """
            )
            conn.commit()

    def get_settings(self) -> Dict[str, str]:
        with self.connect() as conn:
            cur = conn.execute("SELECT key, value FROM app_settings")
            return {str(row["key"]): str(row["value"]) for row in cur.fetchall()}

    def _snapshot_payload_for_season(self, conn: sqlite3.Connection, season_year: int, settings: Dict[str, str]) -> Dict[str, Any]:
        team_cur = conn.execute("SELECT * FROM teams ORDER BY code")
        teams = [row_to_dict(team_cur, row) for row in team_cur.fetchall()]
        payload_teams: List[Dict[str, Any]] = []
        for team in teams:
            team_id = team["id"]
            player_cur = conn.execute("SELECT * FROM players WHERE team_id = ? ORDER BY row_order, id", (team_id,))
            players = [row_to_dict(player_cur, row) for row in player_cur.fetchall()]
            assets_cur = conn.execute(
                "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                (team_id,),
            )
            assets = [row_to_dict(assets_cur, row) for row in assets_cur.fetchall()]
            dead_cur = conn.execute(
                "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                (team_id,),
            )
            dead_contracts = [row_to_dict(dead_cur, row) for row in dead_cur.fetchall()]
            move_log_cur = conn.execute(
                """
                SELECT id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
                FROM team_move_logs
                WHERE team_id = ? AND season_year = ?
                ORDER BY id ASC
                """,
                (team_id, season_year),
            )
            move_logs = [row_to_dict(move_log_cur, row) for row in move_log_cur.fetchall()]
            summary = self._calc_summary(team, players, assets, dead_contracts, settings)
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
            "created_at": now_iso(),
            "settings": settings,
            "teams": payload_teams,
        }

    def _team_move_log_rows(self, conn: sqlite3.Connection, team_id: int, season_year: int) -> List[Dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
            FROM team_move_logs
            WHERE team_id = ? AND season_year = ?
            ORDER BY id DESC
            """,
            (team_id, season_year),
        )
        rows = [row_to_dict(cur, row) for row in cur.fetchall()]
        for row in rows:
            raw = row.get("detail_json")
            try:
                row["details"] = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                row["details"] = {}
        return rows

    def _team_move_summary(self, conn: sqlite3.Connection, team_id: int, season_year: int, settings: Dict[str, str]) -> Dict[str, Any]:
        limit_pre30 = max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0)
        limit_post30 = max(0, parse_int(settings.get("trade_move_limit_post30")) or 0)
        phase = normalize_move_phase(settings.get("trade_move_phase"))
        rows = self._team_move_log_rows(conn, team_id, season_year)
        used_pre30 = sum(int(row.get("delta") or 0) for row in rows if normalize_trade_bucket(row.get("bucket")) == "pre30")
        used_post30 = sum(int(row.get("delta") or 0) for row in rows if normalize_trade_bucket(row.get("bucket")) == "post30")
        return {
            "phase": phase,
            "limit_pre30": limit_pre30,
            "limit_post30": limit_post30,
            "used_pre30": used_pre30,
            "used_post30": used_post30,
            "remaining_pre30": limit_pre30 - used_pre30,
            "remaining_post30": limit_post30 - used_post30,
            "log": rows,
        }

    def update_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, now_iso()),
            )
            conn.commit()

    def progress_to_next_year(self) -> Dict[str, Any]:
        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < 2025 or current_year > 2030:
                current_year = 2025
            if current_year >= 2030:
                raise ValueError("cannot_progress_beyond_2030")

            snapshot_payload = self._snapshot_payload_for_season(conn, current_year, settings)
            conn.execute(
                "INSERT INTO season_snapshots (season_year, payload_json, created_at) VALUES (?, ?, ?)",
                (current_year, json.dumps(snapshot_payload), now_iso()),
            )

            deleted_draft_assets = conn.execute(
                "DELETE FROM assets WHERE asset_type = 'draft_pick' AND CAST(COALESCE(year, '') AS INTEGER) = ?",
                (current_year,),
            ).rowcount or 0

            next_year = current_year + 1
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('current_year', ?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (str(next_year), timestamp),
            )
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('trade_move_phase', 'pre30', ?)
                ON CONFLICT(key)
                DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (timestamp,),
            )
            conn.execute(
                "UPDATE teams SET cash_received = 0, cash_sent = 0, updated_at = ?",
                (timestamp,),
            )
            conn.commit()
            return {
                "previous_year": current_year,
                "current_year": next_year,
                "deleted_draft_assets": int(deleted_draft_assets),
            }

    def upsert_google_user(self, google_sub: str, email: str, display_name: Optional[str], avatar_url: Optional[str]) -> Dict[str, Any]:
        now = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (google_sub, email, display_name, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(google_sub)
                DO UPDATE SET
                    email = excluded.email,
                    display_name = excluded.display_name,
                    avatar_url = excluded.avatar_url,
                    updated_at = excluded.updated_at
                """,
                (google_sub, email, display_name, avatar_url, now, now),
            )
            row = conn.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,)).fetchone()
            conn.commit()
            if not row:
                raise RuntimeError("Failed to load Google user after upsert")
            return dict(row)

    def create_session(self, token: str, payload: Dict[str, Any], created_at: str, expires_at: int) -> bool:
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO sessions (session_token, data_json, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (token, json.dumps(payload, ensure_ascii=True), created_at, int(expires_at)),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_session(self, token: str, now_ts: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        current_ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            row = conn.execute(
                "SELECT data_json, expires_at FROM sessions WHERE session_token = ?",
                (token,),
            ).fetchone()
            if not row:
                return None
            expires_at = int(row["expires_at"] or 0)
            if expires_at <= current_ts:
                conn.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
                conn.commit()
                return None
            try:
                payload = json.loads(str(row["data_json"] or "{}"))
            except json.JSONDecodeError:
                conn.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
                conn.commit()
                return None
            return payload if isinstance(payload, dict) else None

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
            conn.commit()

    def cleanup_expired_sessions(self, now_ts: Optional[int] = None) -> int:
        current_ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (current_ts,))
            conn.commit()
            return int(cur.rowcount or 0)

    def list_teams(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute("SELECT id, code, name, gm, apron_hard_cap FROM teams ORDER BY code")
            return [row_to_dict(cur, row) for row in cur.fetchall()]

    def get_team(self, code: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            team_cur = conn.execute("SELECT * FROM teams WHERE code = ?", (code.upper(),))
            row = team_cur.fetchone()
            if not row:
                return None
            team = row_to_dict(team_cur, row)

            player_cur = conn.execute("SELECT * FROM players WHERE team_id = ? ORDER BY row_order, id", (team["id"],))
            players = [row_to_dict(player_cur, r) for r in player_cur.fetchall()]

            assets_cur = conn.execute(
                "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                (team["id"],),
            )
            assets = [row_to_dict(assets_cur, r) for r in assets_cur.fetchall()]

            dead_cur = conn.execute(
                "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                (team["id"],),
            )
            dead_contracts = [row_to_dict(dead_cur, r) for r in dead_cur.fetchall()]

            settings = self.get_settings()
            summary = self._calc_summary(team, players, assets, dead_contracts, settings)
            move_summary = self._team_move_summary(conn, int(team["id"]), int(summary["current_year"]), settings)
            luxury_history = self._team_luxury_history(conn, int(team["id"]), int(summary["current_year"]))
            return {
                "team": team,
                "players": players,
                "assets": assets,
                "dead_contracts": dead_contracts,
                "summary": summary,
                "move_summary": move_summary,
                "luxury_history": luxury_history,
            }

    def list_tracker(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < 2025 or current_year > 2030:
                current_year = 2025
            salary_num_col = f"salary_{current_year}_num"

            team_cur = conn.execute("SELECT * FROM teams ORDER BY code")
            teams = [row_to_dict(team_cur, row) for row in team_cur.fetchall()]
            rows: List[Dict[str, Any]] = []

            player_aggs: Dict[int, Dict[str, float]] = {}
            players_cur = conn.execute(
                f"""
                SELECT
                    team_id,
                    SUM(CASE WHEN COALESCE(is_two_way, 0) = 0 THEN COALESCE({salary_num_col}, 0) ELSE 0 END) AS cap_players,
                    SUM(COALESCE({salary_num_col}, 0)) AS payroll_players
                FROM players
                GROUP BY team_id
                """
            )
            for row in players_cur.fetchall():
                player_aggs[int(row["team_id"])] = {
                    "cap_players": float(row["cap_players"] or 0.0),
                    "payroll_players": float(row["payroll_players"] or 0.0),
                }

            dead_aggs: Dict[int, Dict[str, float]] = {}
            dead_cur = conn.execute(
                f"""
                SELECT
                    team_id,
                    SUM(CASE WHEN dead_type = 'two_way' AND COALESCE(exclude_from_gasto, 0) = 0 THEN COALESCE({salary_num_col}, CASE WHEN {current_year} = 2025 THEN amount_num ELSE 0 END, 0) ELSE 0 END) AS dead_two_way_gasto,
                    SUM(CASE WHEN dead_type != 'two_way' AND COALESCE(exclude_from_gasto, 0) = 0 THEN COALESCE({salary_num_col}, CASE WHEN {current_year} = 2025 THEN amount_num ELSE 0 END, 0) ELSE 0 END) AS dead_normal_gasto,
                    SUM(CASE WHEN dead_type != 'two_way' AND COALESCE(exclude_from_cap, 0) = 0 THEN COALESCE({salary_num_col}, CASE WHEN {current_year} = 2025 THEN amount_num ELSE 0 END, 0) ELSE 0 END) AS dead_normal_cap
                FROM dead_contracts
                GROUP BY team_id
                """
            )
            for row in dead_cur.fetchall():
                dead_aggs[int(row["team_id"])] = {
                    "dead_two_way_gasto": float(row["dead_two_way_gasto"] or 0.0),
                    "dead_normal_gasto": float(row["dead_normal_gasto"] or 0.0),
                    "dead_normal_cap": float(row["dead_normal_cap"] or 0.0),
                }

            salary_cap = parse_float(settings.get("salary_cap_2025")) or 154647000.0
            luxury_cap = salary_cap * 1.215
            first_apron_setting = parse_float(settings.get("first_apron"))
            second_apron_setting = parse_float(settings.get("second_apron"))
            for team in teams:
                team_id = int(team["id"])
                p = player_aggs.get(team_id, {"cap_players": 0.0, "payroll_players": 0.0})
                d = dead_aggs.get(team_id, {"dead_two_way_gasto": 0.0, "dead_normal_gasto": 0.0, "dead_normal_cap": 0.0})

                cap_figure = float(p["cap_players"]) + float(d["dead_normal_cap"])
                payroll = float(p["payroll_players"]) + float(d["dead_normal_gasto"]) + float(d["dead_two_way_gasto"])
                first_apron = float(first_apron_setting) if first_apron_setting is not None else float(team["first_apron"] or 0.0)
                second_apron = float(second_apron_setting) if second_apron_setting is not None else float(team["second_apron"] or 0.0)
                rows.append(
                    {
                        "team_code": team["code"],
                        "team_name": team["name"],
                        "cap_total": cap_figure,
                        "gasto_total": payroll,
                        "espacio_cap": salary_cap - cap_figure,
                        "espacio_luxury": luxury_cap - cap_figure,
                        "espacio_1er_apron": first_apron - cap_figure,
                        "espacio_2do_apron": second_apron - cap_figure,
                    }
                )
            return rows

    def update_team_fields(self, code: str, payload: Dict[str, Any]) -> bool:
        assignments = []
        values: List[Any] = []
        if "gm" in payload:
            gm_raw = payload.get("gm")
            assignments.append("gm = ?")
            values.append(None if gm_raw is None else str(gm_raw).strip() or None)
        if "cash_received" in payload:
            assignments.append("cash_received = ?")
            values.append(float(payload.get("cash_received") or 0.0))
        if "cash_sent" in payload:
            assignments.append("cash_sent = ?")
            values.append(float(payload.get("cash_sent") or 0.0))
        if "apron_hard_cap" in payload:
            assignments.append("apron_hard_cap = ?")
            values.append(normalize_apron_hard_cap(payload.get("apron_hard_cap")))
        if not assignments:
            return False
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE teams SET {', '.join(assignments)}, updated_at = ? WHERE code = ?",
                (*values, now_iso(), code.upper()),
            )
            conn.commit()
            return cur.rowcount > 0

    def _team_luxury_history(self, conn: sqlite3.Connection, team_id: int, current_year: int) -> List[Dict[str, Any]]:
        years = [current_year, *[current_year - offset for offset in range(1, 5)]]
        placeholders = ",".join("?" for _ in years)
        rows = conn.execute(
            f"""
            SELECT season_year, repeater
            FROM team_luxury_history
            WHERE team_id = ? AND season_year IN ({placeholders})
            """,
            (team_id, *years),
        ).fetchall()
        by_year = {int(row["season_year"]): bool(row["repeater"]) for row in rows}
        return [
            {
                "season_year": year,
                "repeater": bool(by_year.get(year, False)),
            }
            for year in years
        ]

    def update_team_luxury_history(self, code: str, season_year: int, repeater: bool) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not row:
                return False
            conn.execute(
                """
                INSERT INTO team_luxury_history (team_id, season_year, repeater, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(team_id, season_year) DO UPDATE SET
                    repeater = excluded.repeater,
                    updated_at = excluded.updated_at
                """,
                (int(row["id"]), int(season_year), 1 if repeater else 0, now_iso()),
            )
            conn.commit()
            return True

    def _calc_summary(
        self,
        team: Dict[str, Any],
        players: List[Dict[str, Any]],
        assets: List[Dict[str, Any]],
        dead_contracts: List[Dict[str, Any]],
        settings: Dict[str, str],
    ) -> Dict[str, float]:
        current_year = parse_int(settings.get("current_year")) or 2025
        if current_year < 2025 or current_year > 2030:
            current_year = 2025

        # CAP Total: current-year player salaries excluding TW contracts.
        cap_figure_players = sum(row_salary_num(p, current_year) for p in players if not p.get("is_two_way"))
        # GASTO Total: current-year player salaries including TW contracts.
        player_payroll = sum(row_salary_num(p, current_year) for p in players)

        dead_cap_normal = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "normal"
            and not dead_contract_excluded_from_cap(d)
        )
        dead_gasto_normal = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "normal"
            and not dead_contract_excluded_from_gasto(d)
        )
        dead_gasto_two_way = sum(
            dead_contract_salary_num(d, current_year)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "two_way"
            and not dead_contract_excluded_from_gasto(d)
        )
        exceptions = sum((a.get("amount_num") or 0.0) for a in assets if a.get("asset_type") == "exception")

        cap_figure = cap_figure_players + dead_cap_normal
        payroll = player_payroll + dead_gasto_normal + dead_gasto_two_way

        salary_cap = parse_float(settings.get("salary_cap_2025")) or team["salary_cap"]
        luxury = salary_cap * 1.215
        first_apron = parse_float(settings.get("first_apron")) or team["first_apron"]
        second_apron = parse_float(settings.get("second_apron")) or team["second_apron"]
        cash_limit_total = parse_float(settings.get("cash_limit_total")) or 0.0
        cash_received = float(team.get("cash_received") or 0.0)
        cash_sent = float(team.get("cash_sent") or 0.0)

        return {
            "player_payroll": player_payroll,
            "dead_cap": dead_gasto_normal + dead_gasto_two_way,
            "dead_cap_normal": dead_cap_normal,
            "dead_cap_two_way": dead_gasto_two_way,
            "dead_gasto_normal": dead_gasto_normal,
            "dead_gasto_two_way": dead_gasto_two_way,
            "exceptions_total": exceptions,
            "cap_figure": cap_figure,
            "payroll": payroll,
            "salary_cap_2025": salary_cap,
            "current_year": current_year,
            "room_to_cap": salary_cap - cap_figure,
            "room_to_luxury": luxury - cap_figure,
            "room_to_first_apron": first_apron - cap_figure,
            "room_to_second_apron": second_apron - cap_figure,
            "cash_received": cash_received,
            "cash_sent": cash_sent,
            "cash_limit_total": cash_limit_total,
            "trade_move_phase": normalize_move_phase(settings.get("trade_move_phase")),
            "trade_move_limit_pre30": max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0),
            "trade_move_limit_post30": max(0, parse_int(settings.get("trade_move_limit_post30")) or 0),
            "apron_hard_cap": normalize_apron_hard_cap(team.get("apron_hard_cap")) or "",
        }

    def update_player(self, player_id: int, payload: Dict[str, Any]) -> bool:
        fields = [
            "name", "bird_rights", "rating", "position", "years_left",
            "salary_2025_text", "salary_2026_text", "salary_2027_text",
            "salary_2028_text", "salary_2029_text", "salary_2030_text",
            "salary_2025_guaranteed_text", "salary_2026_guaranteed_text", "salary_2027_guaranteed_text",
            "salary_2028_guaranteed_text", "salary_2029_guaranteed_text", "salary_2030_guaranteed_text",
            "option_2025", "option_2026", "option_2027", "option_2028", "option_2029", "option_2030",
            "notes",
        ]
        bool_fields = [
            "provisional_amounts", "partially_guaranteed",
            "salary_2025_provisional", "salary_2026_provisional", "salary_2027_provisional",
            "salary_2028_provisional", "salary_2029_provisional", "salary_2030_provisional",
            "salary_2025_partially_guaranteed", "salary_2026_partially_guaranteed", "salary_2027_partially_guaranteed",
            "salary_2028_partially_guaranteed", "salary_2029_partially_guaranteed", "salary_2030_partially_guaranteed",
        ]
        assignments = []
        values: List[Any] = []

        for f in fields:
            if f in payload:
                assignments.append(f"{f} = ?")
                values.append(payload[f])

        for f in bool_fields:
            if f in payload:
                assignments.append(f"{f} = ?")
                values.append(1 if parse_bool(payload[f]) else 0)

        for season in [2025, 2026, 2027, 2028, 2029, 2030]:
            text_field = f"salary_{season}_text"
            if text_field in payload:
                assignments.append(f"salary_{season}_num = ?")
                values.append(parse_float(payload[text_field]))

        if "bird_rights" in payload:
            assignments.append("is_two_way = ?")
            values.append(1 if str(payload["bird_rights"]).upper() == "TW" else 0)

        if not assignments:
            return False

        assignments.append("updated_at = ?")
        values.append(now_iso())
        values.append(player_id)

        with self.connect() as conn:
            cur = conn.execute(f"UPDATE players SET {', '.join(assignments)} WHERE id = ?", values)
            conn.commit()
            return cur.rowcount > 0

    def move_player(self, player_id: int, to_team_code: str) -> bool:
        with self.connect() as conn:
            target = conn.execute("SELECT id FROM teams WHERE code = ?", (to_team_code.upper(),)).fetchone()
            if not target:
                return False
            max_row = conn.execute(
                "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                (target["id"],),
            ).fetchone()["mx"]
            cur = conn.execute(
                "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                (target["id"], int(max_row) + 1, now_iso(), player_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def create_player(self, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            mx = conn.execute(
                "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                (team["id"],),
            ).fetchone()["mx"]
            now = now_iso()
            values = {
                "name": payload.get("name", "New Player"),
                "bird_rights": payload.get("bird_rights"),
                "rating": payload.get("rating"),
                "position": payload.get("position"),
                "years_left": parse_float(payload.get("years_left")) if payload.get("years_left") is not None else None,
                "salary_2025_text": payload.get("salary_2025_text"),
                "salary_2026_text": payload.get("salary_2026_text"),
                "salary_2027_text": payload.get("salary_2027_text"),
                "salary_2028_text": payload.get("salary_2028_text"),
                "salary_2029_text": payload.get("salary_2029_text"),
                "salary_2030_text": payload.get("salary_2030_text"),
                "salary_2025_guaranteed_text": payload.get("salary_2025_guaranteed_text"),
                "salary_2026_guaranteed_text": payload.get("salary_2026_guaranteed_text"),
                "salary_2027_guaranteed_text": payload.get("salary_2027_guaranteed_text"),
                "salary_2028_guaranteed_text": payload.get("salary_2028_guaranteed_text"),
                "salary_2029_guaranteed_text": payload.get("salary_2029_guaranteed_text"),
                "salary_2030_guaranteed_text": payload.get("salary_2030_guaranteed_text"),
                "option_2025": payload.get("option_2025"),
                "option_2026": payload.get("option_2026"),
                "option_2027": payload.get("option_2027"),
                "option_2028": payload.get("option_2028"),
                "option_2029": payload.get("option_2029"),
                "option_2030": payload.get("option_2030"),
                "provisional_amounts": 1 if parse_bool(payload.get("provisional_amounts")) else 0,
                "partially_guaranteed": 1 if parse_bool(payload.get("partially_guaranteed")) else 0,
                "salary_2025_provisional": 1 if parse_bool(payload.get("salary_2025_provisional")) else 0,
                "salary_2026_provisional": 1 if parse_bool(payload.get("salary_2026_provisional")) else 0,
                "salary_2027_provisional": 1 if parse_bool(payload.get("salary_2027_provisional")) else 0,
                "salary_2028_provisional": 1 if parse_bool(payload.get("salary_2028_provisional")) else 0,
                "salary_2029_provisional": 1 if parse_bool(payload.get("salary_2029_provisional")) else 0,
                "salary_2030_provisional": 1 if parse_bool(payload.get("salary_2030_provisional")) else 0,
                "salary_2025_partially_guaranteed": 1 if parse_bool(payload.get("salary_2025_partially_guaranteed")) else 0,
                "salary_2026_partially_guaranteed": 1 if parse_bool(payload.get("salary_2026_partially_guaranteed")) else 0,
                "salary_2027_partially_guaranteed": 1 if parse_bool(payload.get("salary_2027_partially_guaranteed")) else 0,
                "salary_2028_partially_guaranteed": 1 if parse_bool(payload.get("salary_2028_partially_guaranteed")) else 0,
                "salary_2029_partially_guaranteed": 1 if parse_bool(payload.get("salary_2029_partially_guaranteed")) else 0,
                "salary_2030_partially_guaranteed": 1 if parse_bool(payload.get("salary_2030_partially_guaranteed")) else 0,
                "notes": payload.get("notes"),
            }
            cur = conn.execute(
                """
                INSERT INTO players (
                    team_id, row_order, bird_rights, rating, name, position, years_left,
                    salary_2025_text, salary_2025_num,
                    salary_2026_text, salary_2026_num,
                    salary_2027_text, salary_2027_num,
                    salary_2028_text, salary_2028_num,
                    salary_2029_text, salary_2029_num,
                    salary_2030_text, salary_2030_num,
                    option_2025, option_2026, option_2027, option_2028, option_2029, option_2030,
                    provisional_amounts, partially_guaranteed,
                    salary_2025_provisional, salary_2026_provisional, salary_2027_provisional,
                    salary_2028_provisional, salary_2029_provisional, salary_2030_provisional,
                    salary_2025_partially_guaranteed, salary_2026_partially_guaranteed, salary_2027_partially_guaranteed,
                    salary_2028_partially_guaranteed, salary_2029_partially_guaranteed, salary_2030_partially_guaranteed,
                    salary_2025_guaranteed_text, salary_2026_guaranteed_text, salary_2027_guaranteed_text,
                    salary_2028_guaranteed_text, salary_2029_guaranteed_text, salary_2030_guaranteed_text,
                    notes, is_two_way, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team["id"],
                    int(mx) + 1,
                    values["bird_rights"],
                    values["rating"],
                    values["name"],
                    values["position"],
                    values["years_left"],
                    values["salary_2025_text"],
                    parse_float(values["salary_2025_text"]),
                    values["salary_2026_text"],
                    parse_float(values["salary_2026_text"]),
                    values["salary_2027_text"],
                    parse_float(values["salary_2027_text"]),
                    values["salary_2028_text"],
                    parse_float(values["salary_2028_text"]),
                    values["salary_2029_text"],
                    parse_float(values["salary_2029_text"]),
                    values["salary_2030_text"],
                    parse_float(values["salary_2030_text"]),
                    values["option_2025"],
                    values["option_2026"],
                    values["option_2027"],
                    values["option_2028"],
                    values["option_2029"],
                    values["option_2030"],
                    values["provisional_amounts"],
                    values["partially_guaranteed"],
                    values["salary_2025_provisional"],
                    values["salary_2026_provisional"],
                    values["salary_2027_provisional"],
                    values["salary_2028_provisional"],
                    values["salary_2029_provisional"],
                    values["salary_2030_provisional"],
                    values["salary_2025_partially_guaranteed"],
                    values["salary_2026_partially_guaranteed"],
                    values["salary_2027_partially_guaranteed"],
                    values["salary_2028_partially_guaranteed"],
                    values["salary_2029_partially_guaranteed"],
                    values["salary_2030_partially_guaranteed"],
                    values["salary_2025_guaranteed_text"],
                    values["salary_2026_guaranteed_text"],
                    values["salary_2027_guaranteed_text"],
                    values["salary_2028_guaranteed_text"],
                    values["salary_2029_guaranteed_text"],
                    values["salary_2030_guaranteed_text"],
                    values["notes"],
                    1 if str(values["bird_rights"] or "").upper() == "TW" else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def delete_player(self, player_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            conn.commit()
            return cur.rowcount > 0

    def list_free_agents(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT id, name, position, bird_rights, rating, years_left, notes, created_at, updated_at
                FROM free_agents
                ORDER BY name COLLATE NOCASE, id
                """
            )
            return [row_to_dict(cur, row) for row in cur.fetchall()]

    def get_free_agent(self, free_agent_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM free_agents WHERE id = ?", (free_agent_id,))
            row = cur.fetchone()
            return row_to_dict(cur, row) if row else None

    def create_free_agent(self, payload: Dict[str, Any]) -> Optional[int]:
        name = str(payload.get("name") or "").strip()
        if not name:
            return None
        now = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO free_agents (
                    name, position, bird_rights, rating, years_left, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    str(payload.get("position") or "").strip() or None,
                    str(payload.get("bird_rights") or "").strip() or None,
                    str(payload.get("rating") or "").strip() or None,
                    parse_float(payload.get("years_left")) if payload.get("years_left") is not None else None,
                    str(payload.get("notes") or "").strip() or None,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_free_agent(self, free_agent_id: int, payload: Dict[str, Any]) -> bool:
        fields = ["name", "position", "bird_rights", "rating", "years_left", "notes"]
        assigns = []
        vals: List[Any] = []
        for field in fields:
            if field not in payload:
                continue
            if field == "name":
                value = str(payload.get(field) or "").strip()
                if not value:
                    return False
                assigns.append("name = ?")
                vals.append(value)
            elif field == "years_left":
                assigns.append("years_left = ?")
                vals.append(parse_float(payload.get(field)) if payload.get(field) is not None else None)
            else:
                assigns.append(f"{field} = ?")
                vals.append(str(payload.get(field) or "").strip() or None)
        if not assigns:
            return False
        assigns.append("updated_at = ?")
        vals.append(now_iso())
        vals.append(free_agent_id)
        with self.connect() as conn:
            cur = conn.execute(f"UPDATE free_agents SET {', '.join(assigns)} WHERE id = ?", vals)
            conn.commit()
            return cur.rowcount > 0

    def delete_free_agent(self, free_agent_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM free_agents WHERE id = ?", (free_agent_id,))
            conn.commit()
            return cur.rowcount > 0

    def sign_free_agent(self, free_agent_id: int, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        agent = self.get_free_agent(free_agent_id)
        if not agent:
            return None
        player_payload = dict(payload)
        player_payload["name"] = str(player_payload.get("name") or agent.get("name") or "").strip() or "New Player"
        for key in ["position", "bird_rights", "rating", "years_left", "notes"]:
            if player_payload.get(key) in (None, "") and agent.get(key) not in (None, ""):
                player_payload[key] = agent.get(key)
        player_id = self.create_player(team_code, player_payload)
        if not player_id:
            return None
        self.delete_free_agent(free_agent_id)
        return player_id

    def cut_player(self, player_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT p.*, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (player_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            player = row_to_dict(cur, row)
            now = now_iso()
            team_id = int(player["team_id"])
            team_code = str(player["team_code"])
            dead_mx = conn.execute(
                "SELECT COALESCE(MAX(row_order), 0) AS mx FROM dead_contracts WHERE team_id = ?",
                (team_id,),
            ).fetchone()["mx"]
            salary_texts = {
                season: player.get(f"salary_{season}_text")
                for season in [2025, 2026, 2027, 2028, 2029, 2030]
            }
            amount_text = salary_texts[2025]
            dead_cur = conn.execute(
                """
                INSERT INTO dead_contracts (
                    team_id, row_order, dead_type, label, amount_text, amount_num,
                    salary_2025_text, salary_2025_num,
                    salary_2026_text, salary_2026_num,
                    salary_2027_text, salary_2027_num,
                    salary_2028_text, salary_2028_num,
                    salary_2029_text, salary_2029_num,
                    salary_2030_text, salary_2030_num,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team_id,
                    int(dead_mx) + 1,
                    "two_way" if str(player.get("bird_rights") or "").upper() == "TW" else "normal",
                    player.get("name") or "Cut Player",
                    amount_text,
                    parse_float(amount_text),
                    salary_texts[2025],
                    parse_float(salary_texts[2025]),
                    salary_texts[2026],
                    parse_float(salary_texts[2026]),
                    salary_texts[2027],
                    parse_float(salary_texts[2027]),
                    salary_texts[2028],
                    parse_float(salary_texts[2028]),
                    salary_texts[2029],
                    parse_float(salary_texts[2029]),
                    salary_texts[2030],
                    parse_float(salary_texts[2030]),
                    now,
                    now,
                ),
            )
            free_cur = conn.execute(
                """
                INSERT INTO free_agents (
                    name, position, bird_rights, rating, years_left, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    player.get("name") or "Cut Player",
                    player.get("position"),
                    player.get("bird_rights"),
                    player.get("rating"),
                    player.get("years_left"),
                    player.get("notes"),
                    now,
                    now,
                ),
            )
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            conn.commit()
            return {
                "team_code": team_code,
                "player_name": player.get("name"),
                "dead_contract_id": int(dead_cur.lastrowid),
                "free_agent_id": int(free_cur.lastrowid),
            }

    def create_asset(self, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            mx = conn.execute(
                "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?",
                (team["id"],),
            ).fetchone()["mx"]
            now = now_iso()
            amount_text = payload.get("amount_text")
            asset_type = str(payload.get("asset_type", "draft_pick"))
            draft_pick_type = normalize_pick_type(payload.get("draft_pick_type")) if asset_type == "draft_pick" else None
            draft_round = normalize_pick_round(payload.get("draft_round")) if asset_type == "draft_pick" else None
            original_owner = normalize_team_code(payload.get("original_owner")) if asset_type == "draft_pick" else None
            draft_pick_sold_to = serialize_team_codes(payload.get("draft_pick_sold_to")) if asset_type == "draft_pick" else None
            draft_pick_conditional_teams = serialize_team_codes(payload.get("draft_pick_conditional_teams")) if asset_type == "draft_pick" else None
            exception_type = normalize_exception_type(payload.get("exception_type")) if asset_type == "exception" else None
            draft_pick_restricted = 1 if asset_type == "draft_pick" and parse_bool(payload.get("draft_pick_restricted")) else 0
            draft_pick_protected = 1 if asset_type == "draft_pick" and parse_bool(payload.get("draft_pick_protected")) else 0
            if asset_type == "draft_pick" and draft_pick_type != "acquired":
                original_owner = None
            if asset_type == "draft_pick" and draft_pick_type != "sold":
                draft_pick_sold_to = None
            if asset_type == "draft_pick" and draft_pick_type != "conditional":
                draft_pick_conditional_teams = None
            cur = conn.execute(
                """
                INSERT INTO assets (
                    team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                    draft_pick_type, draft_round, original_owner, exception_type,
                    draft_pick_restricted, draft_pick_protected, draft_pick_sold_to,
                    draft_pick_conditional_teams, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team["id"],
                    int(mx) + 1,
                    asset_type,
                    payload.get("year"),
                    payload.get("label", "New Asset"),
                    payload.get("detail"),
                    amount_text,
                    parse_float(amount_text),
                    draft_pick_type,
                    draft_round,
                    original_owner,
                    exception_type,
                    draft_pick_restricted,
                    draft_pick_protected,
                    draft_pick_sold_to,
                    draft_pick_conditional_teams,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_asset(self, asset_id: int, payload: Dict[str, Any]) -> bool:
        fields = [
            "asset_type", "year", "label", "detail", "amount_text", "draft_pick_type",
            "draft_round", "original_owner", "exception_type", "draft_pick_restricted",
            "draft_pick_protected", "draft_pick_sold_to", "draft_pick_conditional_teams",
        ]
        assigns = []
        vals = []
        for f in fields:
            if f in payload:
                if f == "draft_pick_type":
                    assigns.append("draft_pick_type = ?")
                    vals.append(normalize_pick_type(payload[f]))
                elif f == "draft_round":
                    assigns.append("draft_round = ?")
                    vals.append(normalize_pick_round(payload[f]))
                elif f == "original_owner":
                    assigns.append("original_owner = ?")
                    vals.append(normalize_team_code(payload[f]))
                elif f == "draft_pick_sold_to":
                    assigns.append("draft_pick_sold_to = ?")
                    vals.append(serialize_team_codes(payload[f]))
                elif f == "draft_pick_conditional_teams":
                    assigns.append("draft_pick_conditional_teams = ?")
                    vals.append(serialize_team_codes(payload[f]))
                elif f == "exception_type":
                    assigns.append("exception_type = ?")
                    vals.append(normalize_exception_type(payload[f]))
                elif f in {"draft_pick_restricted", "draft_pick_protected"}:
                    assigns.append(f"{f} = ?")
                    vals.append(1 if parse_bool(payload[f]) else 0)
                else:
                    assigns.append(f"{f} = ?")
                    vals.append(payload[f])
        if "amount_text" in payload:
            assigns.append("amount_num = ?")
            vals.append(parse_float(payload["amount_text"]))
        if "draft_pick_type" in payload:
            pick_type = normalize_pick_type(payload["draft_pick_type"])
            if pick_type != "acquired":
                assigns.append("original_owner = ?")
                vals.append(None)
            if pick_type != "sold":
                assigns.append("draft_pick_sold_to = ?")
                vals.append(None)
            if pick_type != "conditional":
                assigns.append("draft_pick_conditional_teams = ?")
                vals.append(None)
        if not assigns:
            return False
        assigns.append("updated_at = ?")
        vals.append(now_iso())
        vals.append(asset_id)
        with self.connect() as conn:
            cur = conn.execute(f"UPDATE assets SET {', '.join(assigns)} WHERE id = ?", vals)
            conn.commit()
            return cur.rowcount > 0

    def create_dead_contract(self, team_code: str, payload: Dict[str, Any]) -> Optional[int]:
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            mx = conn.execute(
                "SELECT COALESCE(MAX(row_order), 0) AS mx FROM dead_contracts WHERE team_id = ?",
                (team["id"],),
            ).fetchone()["mx"]
            now = now_iso()
            salary_texts = {
                season: payload.get(f"salary_{season}_text")
                for season in [2025, 2026, 2027, 2028, 2029, 2030]
            }
            legacy_amount_text = payload.get("amount_text")
            if legacy_amount_text is not None and salary_texts[2025] is None:
                salary_texts[2025] = legacy_amount_text
            amount_text = salary_texts[2025]
            cur = conn.execute(
                """
                INSERT INTO dead_contracts (
                    team_id, row_order, dead_type, label, amount_text, amount_num,
                    exclude_from_gasto, exclude_from_cap,
                    salary_2025_text, salary_2025_num,
                    salary_2026_text, salary_2026_num,
                    salary_2027_text, salary_2027_num,
                    salary_2028_text, salary_2028_num,
                    salary_2029_text, salary_2029_num,
                    salary_2030_text, salary_2030_num,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team["id"],
                    int(mx) + 1,
                    normalize_dead_type(payload.get("dead_type")),
                    payload.get("label", "Dead Contract"),
                    amount_text,
                    parse_float(amount_text),
                    1 if parse_bool(payload.get("exclude_from_gasto")) else 0,
                    1 if parse_bool(payload.get("exclude_from_cap")) else 0,
                    salary_texts[2025],
                    parse_float(salary_texts[2025]),
                    salary_texts[2026],
                    parse_float(salary_texts[2026]),
                    salary_texts[2027],
                    parse_float(salary_texts[2027]),
                    salary_texts[2028],
                    parse_float(salary_texts[2028]),
                    salary_texts[2029],
                    parse_float(salary_texts[2029]),
                    salary_texts[2030],
                    parse_float(salary_texts[2030]),
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_dead_contract(self, dead_contract_id: int, payload: Dict[str, Any]) -> bool:
        fields = ["label"]
        assigns = []
        vals = []
        if "dead_type" in payload:
            assigns.append("dead_type = ?")
            vals.append(normalize_dead_type(payload.get("dead_type")))
        for bool_field in ["exclude_from_gasto", "exclude_from_cap"]:
            if bool_field in payload:
                assigns.append(f"{bool_field} = ?")
                vals.append(1 if parse_bool(payload.get(bool_field)) else 0)
        for f in fields:
            if f in payload:
                assigns.append(f"{f} = ?")
                vals.append(payload[f])
        legacy_amount = payload.get("amount_text") if "amount_text" in payload else None
        for season in [2025, 2026, 2027, 2028, 2029, 2030]:
            text_field = f"salary_{season}_text"
            if text_field in payload or (season == 2025 and legacy_amount is not None):
                value = payload[text_field] if text_field in payload else legacy_amount
                assigns.append(f"{text_field} = ?")
                vals.append(value)
                assigns.append(f"salary_{season}_num = ?")
                vals.append(parse_float(value))
        if "salary_2025_text" in payload or "amount_text" in payload:
            amount_source = payload.get("salary_2025_text") if "salary_2025_text" in payload else legacy_amount
            assigns.append("amount_text = ?")
            vals.append(amount_source)
            assigns.append("amount_num = ?")
            vals.append(parse_float(amount_source))
        if not assigns:
            return False
        assigns.append("updated_at = ?")
        vals.append(now_iso())
        vals.append(dead_contract_id)
        with self.connect() as conn:
            cur = conn.execute(f"UPDATE dead_contracts SET {', '.join(assigns)} WHERE id = ?", vals)
            conn.commit()
            return cur.rowcount > 0

    def delete_dead_contract(self, dead_contract_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM dead_contracts WHERE id = ?", (dead_contract_id,))
            conn.commit()
            return cur.rowcount > 0

    def delete_asset(self, asset_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            conn.commit()
            return cur.rowcount > 0

    def _pick_actual_owner(self, asset_row: Dict[str, Any], source_team_code: str) -> str:
        if normalize_pick_type(asset_row.get("draft_pick_type")) == "acquired":
            return normalize_team_code(asset_row.get("original_owner")) or source_team_code
        return source_team_code

    def _upsert_team_move_log(
        self,
        conn: sqlite3.Connection,
        *,
        team_id: int,
        season_year: int,
        bucket: str,
        delta: int,
        source_type: str,
        source_ref: Optional[str],
        note: Optional[str],
        details: Optional[Dict[str, Any]],
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_move_logs (
                team_id, season_year, bucket, delta, source_type, source_ref, note, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                season_year,
                normalize_trade_bucket(bucket),
                int(delta),
                source_type,
                source_ref,
                note,
                json.dumps(details or {}, ensure_ascii=True),
                now_iso(),
            ),
        )

    def adjust_team_move_remaining(
        self,
        team_code: str,
        season_year: int,
        bucket: str,
        target_remaining: int,
        actor_note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        bucket_key = normalize_trade_bucket(bucket)
        target_remaining = max(0, int(target_remaining))
        with self.connect() as conn:
            team = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_code.upper(),)).fetchone()
            if not team:
                return None
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            move_summary = self._team_move_summary(conn, int(team["id"]), int(season_year), settings)
            limit = int(move_summary[f"limit_{bucket_key}"])
            current_remaining = int(move_summary[f"remaining_{bucket_key}"])
            target_used = limit - target_remaining
            current_used = limit - current_remaining
            delta = target_used - current_used
            if delta == 0:
                return {
                    "team_code": team["code"],
                    "bucket": bucket_key,
                    "remaining": current_remaining,
                    "delta": 0,
                }
            self._upsert_team_move_log(
                conn,
                team_id=int(team["id"]),
                season_year=int(season_year),
                bucket=bucket_key,
                delta=int(delta),
                source_type="manual_adjustment",
                source_ref=None,
                note=actor_note or "Manual adjustment",
                details={"target_remaining": target_remaining},
            )
            conn.commit()
            refreshed = self._team_move_summary(conn, int(team["id"]), int(season_year), settings)
            return {
                "team_code": team["code"],
                "bucket": bucket_key,
                "remaining": int(refreshed[f"remaining_{bucket_key}"]),
                "delta": int(delta),
            }

    def process_trade(
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
        trade_bucket: Optional[str] = None,
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
        pick_a = clean_ids(pick_ids_a or [])
        pick_b = clean_ids(pick_ids_b or [])
        right_a = clean_ids(right_ids_a or [])
        right_b = clean_ids(right_ids_b or [])
        no_count_a = set(clean_ids(no_count_players_a or []))
        no_count_b = set(clean_ids(no_count_players_b or []))
        if not ids_a and not pick_a and not right_a:
            return None
        if not ids_b and not pick_b and not right_b:
            return None

        with self.connect() as conn:
            team_a = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_a_code.upper(),)).fetchone()
            team_b = conn.execute("SELECT id, code FROM teams WHERE code = ?", (team_b_code.upper(),)).fetchone()
            if not team_a or not team_b or team_a["id"] == team_b["id"]:
                return None

            current_year = parse_int(self.get_settings().get("current_year")) or 2025
            if current_year < 2025 or current_year > 2030:
                current_year = 2025
            next_pick_year = current_year + 1

            players_a_rows: List[Dict[str, Any]] = []
            for player_id in ids_a:
                row = conn.execute("SELECT id, team_id, name FROM players WHERE id = ?", (player_id,)).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                players_a_rows.append(dict(row))
            players_b_rows: List[Dict[str, Any]] = []
            for player_id in ids_b:
                row = conn.execute("SELECT id, team_id, name FROM players WHERE id = ?", (player_id,)).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                players_b_rows.append(dict(row))

            picks_a_rows: List[Dict[str, Any]] = []
            for asset_id in pick_a:
                row = conn.execute(
                    """
                    SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                           draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order
                    FROM assets
                    WHERE id = ? AND asset_type = 'draft_pick'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return None
                if normalize_pick_type(row["draft_pick_type"]) == "sold":
                    return None
                if normalize_pick_round(row["draft_round"]) != "1st":
                    return None
                if parse_int(row["year"]) != next_pick_year:
                    return None
                picks_a_rows.append(dict(row))

            picks_b_rows: List[Dict[str, Any]] = []
            for asset_id in pick_b:
                row = conn.execute(
                    """
                    SELECT id, team_id, year, label, draft_pick_type, draft_round, original_owner,
                           draft_pick_sold_to, draft_pick_conditional_teams, detail, row_order
                    FROM assets
                    WHERE id = ? AND asset_type = 'draft_pick'
                    """,
                    (asset_id,),
                ).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return None
                if normalize_pick_type(row["draft_pick_type"]) == "sold":
                    return None
                if normalize_pick_round(row["draft_round"]) != "1st":
                    return None
                if parse_int(row["year"]) != next_pick_year:
                    return None
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

            timestamp = now_iso()
            for player_id in ids_a:
                mx = conn.execute(
                    "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
                    (team_b["id"],),
                ).fetchone()["mx"]
                conn.execute(
                    "UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                    (team_b["id"], int(mx) + 1, timestamp, player_id),
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

            def move_pick(source_team: sqlite3.Row, target_team: sqlite3.Row, pick_row: Dict[str, Any]) -> None:
                actual_owner = self._pick_actual_owner(pick_row, str(source_team["code"]))
                source_pick_type = normalize_pick_type(pick_row.get("draft_pick_type"))
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
                    (target_team["id"], next_pick_year),
                )
                recipient_rows = [row_to_dict(recipient_rows_cur, row) for row in recipient_rows_cur.fetchall()]
                recipient_match = None
                for candidate in recipient_rows:
                    candidate_actual_owner = self._pick_actual_owner(candidate, str(target_team["code"]))
                    if candidate_actual_owner == actual_owner and normalize_pick_round(candidate.get("draft_round")) == "1st":
                        recipient_match = candidate
                        break

                sold_label = pick_row.get("label") or "1st pick"
                sold_detail = pick_row.get("detail")
                conn.execute(
                    """
                    UPDATE assets
                    SET draft_pick_type = 'sold', original_owner = ?, draft_pick_sold_to = ?,
                        draft_pick_conditional_teams = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (actual_owner, str(target_team["code"]), timestamp, pick_row["id"]),
                )

                if recipient_match:
                    conn.execute(
                        """
                        UPDATE assets
                        SET draft_pick_type = ?, original_owner = ?, draft_pick_sold_to = NULL,
                            draft_pick_conditional_teams = ?, label = ?, detail = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            target_pick_type,
                            target_original_owner,
                            target_conditional_teams,
                            sold_label,
                            sold_detail,
                            timestamp,
                            recipient_match["id"],
                        ),
                    )
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
                        draft_pick_sold_to, draft_pick_conditional_teams, created_at, updated_at
                    ) VALUES (?, ?, 'draft_pick', ?, ?, ?, NULL, NULL, ?, '1st', ?, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        target_team["id"],
                        int(mx) + 1,
                        pick_row.get("year"),
                        sold_label,
                        sold_detail,
                        target_pick_type,
                        target_original_owner,
                        target_conditional_teams,
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
            move_count_a = len([row for row in players_a_rows if int(row["id"]) not in no_count_a]) + len(picks_a_rows) + len(rights_a_rows)
            move_count_b = len([row for row in players_b_rows if int(row["id"]) not in no_count_b]) + len(picks_b_rows) + len(rights_b_rows)

            if move_count_a:
                self._upsert_team_move_log(
                    conn,
                    team_id=int(team_a["id"]),
                    season_year=current_year,
                    bucket=bucket,
                    delta=move_count_a,
                    source_type="trade",
                    source_ref=f"{team_a['code']}-{team_b['code']}-{timestamp}",
                    note=f"Trade vs {team_b['code']}",
                    details={
                        "opponent": team_b["code"],
                        "players": [row["name"] for row in players_a_rows if int(row["id"]) not in no_count_a],
                        "players_excluded": [row["name"] for row in players_a_rows if int(row["id"]) in no_count_a],
                        "pick_count": len(picks_a_rows),
                        "pick_refs": [f"{next_pick_year} 1st ({self._pick_actual_owner(row, str(team_a['code']))})" for row in picks_a_rows],
                        "rights": [row.get("label") for row in rights_a_rows],
                    },
                )
            if move_count_b:
                self._upsert_team_move_log(
                    conn,
                    team_id=int(team_b["id"]),
                    season_year=current_year,
                    bucket=bucket,
                    delta=move_count_b,
                    source_type="trade",
                    source_ref=f"{team_b['code']}-{team_a['code']}-{timestamp}",
                    note=f"Trade vs {team_a['code']}",
                    details={
                        "opponent": team_a["code"],
                        "players": [row["name"] for row in players_b_rows if int(row["id"]) not in no_count_b],
                        "players_excluded": [row["name"] for row in players_b_rows if int(row["id"]) in no_count_b],
                        "pick_count": len(picks_b_rows),
                        "pick_refs": [f"{next_pick_year} 1st ({self._pick_actual_owner(row, str(team_b['code']))})" for row in picks_b_rows],
                        "rights": [row.get("label") for row in rights_b_rows],
                    },
                )

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
                "right_count_a": len(rights_a_rows),
                "right_count_b": len(rights_b_rows),
            }

    def log_admin_action(
        self,
        actor_email: Optional[str],
        actor_name: Optional[str],
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        team_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_logs (created_at, actor_email, actor_name, action, entity, entity_id, team_code, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    actor_email,
                    actor_name,
                    action,
                    entity,
                    entity_id,
                    team_code.upper() if team_code else None,
                    json.dumps(details or {}, ensure_ascii=True),
                ),
            )
            conn.commit()

    def list_admin_logs(
        self,
        action: Optional[str] = None,
        entity: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT id, created_at, actor_email, actor_name, action, entity, entity_id, team_code, details_json
            FROM admin_logs
        """
        clauses: List[str] = []
        values: List[Any] = []
        if action:
            clauses.append("action = ?")
            values.append(action.strip().lower())
        if entity:
            clauses.append("entity = ?")
            values.append(entity.strip().lower())
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 500)))

        with self.connect() as conn:
            cur = conn.execute(query, values)
            rows = [row_to_dict(cur, row) for row in cur.fetchall()]
            for row in rows:
                raw = row.get("details_json")
                try:
                    row["details"] = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    row["details"] = {}
            return rows


class Handler(SimpleHTTPRequestHandler):
    db: LeagueDB = None  # type: ignore

    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    admin_emails = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    session_ttl_seconds = max(300, parse_int(os.getenv("SESSION_TTL_SECONDS")) or 28800)
    cookie_secure = str(os.getenv("COOKIE_SECURE", "false")).strip().lower() in {"1", "true", "yes", "on"}
    cookie_same_site = str(os.getenv("COOKIE_SAMESITE", "Lax")).strip() or "Lax"
    cookie_domain = str(os.getenv("COOKIE_DOMAIN", "")).strip() or None

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")

    pending_oauth_states: set[str] = set()
    login_attempts: Dict[str, Dict[str, Any]] = {}
    login_window_seconds = max(60, parse_int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS")) or 600)
    login_max_attempts = max(1, parse_int(os.getenv("LOGIN_RATE_LIMIT_MAX_ATTEMPTS")) or 5)
    login_block_seconds = max(60, parse_int(os.getenv("LOGIN_RATE_LIMIT_BLOCK_SECONDS")) or 900)
    session_cleanup_interval_seconds = max(30, parse_int(os.getenv("SESSION_CLEANUP_INTERVAL_SECONDS")) or 120)
    _last_session_cleanup_ts = 0

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _json(self, status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _bytes_response(self, status: int, data: bytes, content_type: str, headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.lower()
        query = parsed.query
        if path.endswith(".html") or path in {"/", "/login", "/admin"}:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        elif path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico")):
            if query:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
        super().end_headers()

    def _redirect(self, location: str, headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _client_ip(self) -> str:
        xff = self.headers.get("X-Forwarded-For", "").strip()
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def _cookie_dict(self) -> Dict[str, str]:
        raw = self.headers.get("Cookie", "")
        out: Dict[str, str] = {}
        for chunk in raw.split(";"):
            piece = chunk.strip()
            if not piece or "=" not in piece:
                continue
            k, v = piece.split("=", 1)
            out[k] = v
        return out

    def _maybe_cleanup_sessions(self) -> None:
        now_ts = int(datetime.now(UTC).timestamp())
        if now_ts - self._last_session_cleanup_ts < self.session_cleanup_interval_seconds:
            return
        type(self)._last_session_cleanup_ts = now_ts
        self.db.cleanup_expired_sessions(now_ts)

    def _current_session(self) -> Optional[Dict[str, Any]]:
        self._maybe_cleanup_sessions()
        token = self._cookie_dict().get("session")
        if not token:
            return None
        return self.db.get_session(token)

    def _is_authenticated(self) -> bool:
        return self._current_session() is not None

    def _is_admin(self) -> bool:
        sess = self._current_session()
        return bool(sess and sess.get("role") == "admin")

    def _require_admin(self) -> bool:
        if self._is_admin():
            return True
        self._json(401, {"error": "admin_auth_required"})
        return False

    def _route_html(self, filename: str) -> None:
        self.path = f"/{filename}"
        super().do_GET()

    def _start_session(self, session_payload: Dict[str, Any]) -> tuple[str, str]:
        self._maybe_cleanup_sessions()
        now_ts = int(datetime.now(UTC).timestamp())
        data = dict(session_payload)
        csrf_token = secrets.token_urlsafe(24)
        data["csrf_token"] = csrf_token
        data["created_at_ts"] = now_ts
        data["expires_at"] = now_ts + self.session_ttl_seconds
        while True:
            token = secrets.token_urlsafe(32)
            created = self.db.create_session(token, data, now_iso(), data["expires_at"])
            if created:
                return token, csrf_token

    def _clear_session(self) -> None:
        token = self._cookie_dict().get("session")
        if token:
            self.db.delete_session(token)

    def _session_cookie(self, token: str) -> str:
        parts = [
            f"session={token}",
            "Path=/",
            "HttpOnly",
            f"SameSite={self.cookie_same_site}",
            f"Max-Age={self.session_ttl_seconds}",
        ]
        if self.cookie_secure:
            parts.append("Secure")
        if self.cookie_domain:
            parts.append(f"Domain={self.cookie_domain}")
        return "; ".join(parts)

    def _clear_session_cookie(self) -> str:
        parts = [
            "session=",
            "Path=/",
            "HttpOnly",
            f"SameSite={self.cookie_same_site}",
            "Max-Age=0",
        ]
        if self.cookie_secure:
            parts.append("Secure")
        if self.cookie_domain:
            parts.append(f"Domain={self.cookie_domain}")
        return "; ".join(parts)

    def _csrf_ok(self) -> bool:
        sess = self._current_session()
        if not sess:
            return False
        expected = str(sess.get("csrf_token") or "")
        provided = str(self.headers.get("X-CSRF-Token", "")).strip()
        if not expected or not provided:
            return False
        return secrets.compare_digest(expected, provided)

    def _require_csrf(self) -> bool:
        if self._csrf_ok():
            return True
        self._json(403, {"error": "csrf_invalid"})
        return False

    def _rate_limit_status(self, ip: str) -> tuple[bool, int]:
        now_ts = int(datetime.now(UTC).timestamp())
        rec = self.login_attempts.get(ip)
        if not rec:
            return False, 0
        blocked_until = parse_int(str(rec.get("blocked_until"))) or 0
        if blocked_until > now_ts:
            return True, blocked_until - now_ts
        return False, 0

    def _rate_limit_fail(self, ip: str) -> None:
        now_ts = int(datetime.now(UTC).timestamp())
        rec = self.login_attempts.get(ip)
        if not rec or (parse_int(str(rec.get("window_start"))) or 0) + self.login_window_seconds <= now_ts:
            rec = {"window_start": now_ts, "count": 0, "blocked_until": 0}
        rec["count"] = int(rec.get("count", 0)) + 1
        if rec["count"] >= self.login_max_attempts:
            rec["blocked_until"] = now_ts + self.login_block_seconds
            rec["count"] = 0
            rec["window_start"] = now_ts
        self.login_attempts[ip] = rec

    def _rate_limit_success(self, ip: str) -> None:
        if ip in self.login_attempts:
            del self.login_attempts[ip]

    def _google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.google_redirect_uri)

    def _log_admin_action(
        self,
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        team_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        sess = self._current_session() or {}
        if sess.get("role") != "admin":
            return
        self.db.log_admin_action(
            actor_email=sess.get("email"),
            actor_name=sess.get("name"),
            action=action.strip().lower(),
            entity=entity.strip().lower(),
            entity_id=entity_id,
            team_code=team_code,
            details=details or {},
        )

    def _exchange_google_code(self, code: str) -> Dict[str, Any]:
        payload = urlencode(
            {
                "code": code,
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret,
                "redirect_uri": self.google_redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        req = Request(
            "https://oauth2.googleapis.com/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fetch_google_userinfo(self, access_token: str) -> Dict[str, Any]:
        req = Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self._route_html("index.html")
            return

        if parsed.path == "/login":
            self._route_html("login.html")
            return

        if parsed.path == "/admin":
            if self._is_admin():
                self._route_html("admin.html")
                return
            if self._is_authenticated():
                self._redirect("/")
                return
            self._route_html("login.html")
            return

        if parsed.path == "/api/auth/google/start":
            if not self._google_enabled():
                self._redirect("/login?error=google_not_configured")
                return
            state = secrets.token_urlsafe(24)
            self.pending_oauth_states.add(state)
            params = urlencode(
                {
                    "client_id": self.google_client_id,
                    "redirect_uri": self.google_redirect_uri,
                    "response_type": "code",
                    "scope": "openid email profile",
                    "state": state,
                    "prompt": "select_account",
                }
            )
            self._redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")
            return

        if parsed.path == "/api/auth/google/callback":
            qs = parse_qs(parsed.query)
            if "error" in qs:
                self._redirect("/login?error=google_auth_denied")
                return
            code = (qs.get("code") or [""])[0]
            state = (qs.get("state") or [""])[0]
            if not code or not state or state not in self.pending_oauth_states:
                self._redirect("/login?error=google_state_invalid")
                return
            self.pending_oauth_states.discard(state)

            try:
                token_data = self._exchange_google_code(code)
                access_token = token_data.get("access_token")
                if not access_token:
                    self._redirect("/login?error=google_token_failed")
                    return
                userinfo = self._fetch_google_userinfo(access_token)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                self._redirect("/login?error=google_exchange_failed")
                return

            google_sub = str(userinfo.get("sub") or "").strip()
            email = str(userinfo.get("email") or "").strip().lower()
            name = str(userinfo.get("name") or "").strip() or None
            picture = str(userinfo.get("picture") or "").strip() or None

            if not google_sub or not email:
                self._redirect("/login?error=google_profile_invalid")
                return

            user = self.db.upsert_google_user(google_sub, email, name, picture)
            role = "admin" if email in self.admin_emails else "viewer"

            token, _ = self._start_session(
                {
                    "provider": "google",
                    "user_id": user["id"],
                    "email": email,
                    "name": user.get("display_name") or email,
                    "role": role,
                    "logged_in_at": now_iso(),
                }
            )
            cookie = self._session_cookie(token)
            self._redirect("/admin" if role == "admin" else "/", headers={"Set-Cookie": cookie})
            return

        if parsed.path == "/api/auth/status":
            sess = self._current_session()
            if not sess:
                self._json(
                    200,
                    {
                        "authenticated": False,
                        "role": None,
                        "user": None,
                        "google_enabled": self._google_enabled(),
                        "csrf_token": None,
                    },
                )
                return
            self._json(
                200,
                {
                    "authenticated": True,
                    "role": sess.get("role"),
                    "user": {
                        "email": sess.get("email"),
                        "name": sess.get("name"),
                        "provider": sess.get("provider"),
                    },
                    "google_enabled": self._google_enabled(),
                    "csrf_token": sess.get("csrf_token"),
                },
            )
            return

        if parsed.path == "/api/teams":
            self._json(200, {"teams": self.db.list_teams()})
            return

        if parsed.path == "/api/tracker":
            self._json(200, {"tracker": self.db.list_tracker()})
            return

        if parsed.path == "/api/free-agents":
            self._json(200, {"free_agents": self.db.list_free_agents()})
            return

        if parsed.path == "/api/settings":
            settings = self.db.get_settings()
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < 2025 or current_year > 2030:
                current_year = 2025
            salary_cap = parse_float(settings.get("salary_cap_2025")) or 154647000.0
            cash_limit_total = parse_float(settings.get("cash_limit_total")) or 0.0
            trade_move_limit_pre30 = max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0)
            trade_move_limit_post30 = max(0, parse_int(settings.get("trade_move_limit_post30")) or 0)
            trade_move_phase = normalize_move_phase(settings.get("trade_move_phase"))
            self._json(
                200,
                {
                    "settings": {
                        "salary_cap_2025": salary_cap,
                        "current_year": current_year,
                        "first_apron": parse_float(settings.get("first_apron")) or 195945000.0,
                        "second_apron": parse_float(settings.get("second_apron")) or 207824000.0,
                        "cash_limit_total": cash_limit_total,
                        "trade_move_limit_pre30": trade_move_limit_pre30,
                        "trade_move_limit_post30": trade_move_limit_post30,
                        "trade_move_phase": trade_move_phase,
                        "luxury_cap": salary_cap * 1.215,
                        "minimum_cap_allowed": salary_cap * 0.9,
                    }
                },
            )
            return

        if parsed.path == "/api/admin/logs":
            if not self._require_admin():
                return
            qs = parse_qs(parsed.query)
            action = (qs.get("action") or [""])[0].strip() or None
            entity = (qs.get("entity") or [""])[0].strip() or None
            limit = parse_int((qs.get("limit") or ["200"])[0]) or 200
            self._json(200, {"logs": self.db.list_admin_logs(action=action, entity=entity, limit=limit)})
            return

        if parsed.path.startswith("/api/teams/"):
            code = parsed.path.split("/")[-1]
            data = self.db.get_team(code)
            if not data:
                self._json(404, {"error": "team_not_found"})
                return
            self._json(200, data)
            return

        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/auth/logout":
            if self._is_authenticated() and not self._require_csrf():
                return
            self._clear_session()
            self._json(200, {"ok": True}, headers={"Set-Cookie": self._clear_session_cookie()})
            return

        payload = self._read_json()

        if parsed.path == "/api/auth/login":
            ip = self._client_ip()
            blocked, retry_after = self._rate_limit_status(ip)
            if blocked:
                self._json(429, {"error": "too_many_attempts", "retry_after_seconds": retry_after})
                return
            username = str(payload.get("username") or "")
            password = str(payload.get("password") or "")
            if username != self.admin_user or password != self.admin_password:
                self._rate_limit_fail(ip)
                self._json(401, {"error": "invalid_credentials"})
                return

            token, csrf_token = self._start_session(
                {
                    "provider": "local",
                    "user_id": None,
                    "email": username,
                    "name": username,
                    "role": "admin",
                    "logged_in_at": now_iso(),
                }
            )
            self._rate_limit_success(ip)
            cookie = self._session_cookie(token)
            self._json(200, {"ok": True, "csrf_token": csrf_token}, headers={"Set-Cookie": cookie})
            return

        if not self._require_admin():
            return
        if not self._require_csrf():
            return

        if parsed.path == "/api/admin/backup":
            try:
                data = self.db.backup_bytes()
            except (OSError, sqlite3.Error):
                self._json(500, {"error": "backup_failed"})
                return
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            filename = f"anba-league-{timestamp}.db"
            self._log_admin_action("download", "backup", filename, None, {"bytes": len(data)})
            self._bytes_response(
                200,
                data,
                "application/vnd.sqlite3",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
            return

        if parsed.path == "/api/free-agents":
            free_agent_id = self.db.create_free_agent(payload)
            if not free_agent_id:
                self._json(400, {"error": "name_required"})
                return
            self._log_admin_action("create", "free_agent", str(free_agent_id), None, {"name": payload.get("name")})
            self._json(201, {"free_agent_id": free_agent_id})
            return

        if parsed.path.startswith("/api/free-agents/") and parsed.path.endswith("/sign"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 4:
                self._json(404, {"error": "not_found"})
                return
            try:
                free_agent_id = int(parts[2])
            except ValueError:
                self._json(400, {"error": "invalid_free_agent_id"})
                return
            team_code = str(payload.get("team_code") or "").strip().upper()
            if not team_code:
                self._json(400, {"error": "team_code_required"})
                return
            player_id = self.db.sign_free_agent(free_agent_id, team_code, payload)
            if not player_id:
                self._json(404, {"error": "free_agent_or_team_not_found"})
                return
            self._log_admin_action(
                "sign",
                "free_agent",
                str(free_agent_id),
                team_code,
                {"player_id": player_id, "name": payload.get("name")},
            )
            self._json(200, {"ok": True, "player_id": player_id})
            return

        if parsed.path.startswith("/api/players/") and parsed.path.endswith("/cut"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 4:
                self._json(404, {"error": "not_found"})
                return
            try:
                player_id = int(parts[2])
            except ValueError:
                self._json(400, {"error": "invalid_player_id"})
                return
            result = self.db.cut_player(player_id)
            if not result:
                self._json(404, {"error": "player_not_found"})
                return
            self._log_admin_action(
                "cut",
                "player",
                str(player_id),
                str(result.get("team_code") or ""),
                {
                    "player_name": result.get("player_name"),
                    "dead_contract_id": result.get("dead_contract_id"),
                    "free_agent_id": result.get("free_agent_id"),
                },
            )
            self._json(200, {"ok": True, "result": result})
            return

        if parsed.path == "/api/players":
            team_code = payload.get("team_code")
            if not team_code:
                self._json(400, {"error": "team_code_required"})
                return
            player_id = self.db.create_player(team_code, payload)
            if not player_id:
                self._json(404, {"error": "team_not_found"})
                return
            self._log_admin_action("create", "player", str(player_id), str(team_code), {"name": payload.get("name")})
            self._json(201, {"player_id": player_id})
            return

        if parsed.path == "/api/players/move":
            player_id = payload.get("player_id")
            to_team_code = payload.get("to_team_code")
            if not player_id or not to_team_code:
                self._json(400, {"error": "player_id_and_to_team_code_required"})
                return
            ok = self.db.move_player(int(player_id), str(to_team_code))
            if ok:
                self._log_admin_action(
                    "move",
                    "player",
                    str(player_id),
                    str(to_team_code),
                    {"to_team_code": str(to_team_code).upper()},
                )
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path == "/api/trades/process":
            team_a = str(payload.get("team_a") or "").strip().upper()
            team_b = str(payload.get("team_b") or "").strip().upper()
            players_a = payload.get("players_a")
            players_b = payload.get("players_b")
            pick_ids_a = payload.get("pick_ids_a")
            pick_ids_b = payload.get("pick_ids_b")
            right_ids_a = payload.get("right_ids_a")
            right_ids_b = payload.get("right_ids_b")
            no_count_players_a = payload.get("no_count_players_a")
            no_count_players_b = payload.get("no_count_players_b")
            trade_bucket = payload.get("trade_bucket")
            result = self.db.process_trade(
                team_a,
                team_b,
                players_a,
                players_b,
                pick_ids_a=pick_ids_a,
                pick_ids_b=pick_ids_b,
                right_ids_a=right_ids_a,
                right_ids_b=right_ids_b,
                no_count_players_a=no_count_players_a,
                no_count_players_b=no_count_players_b,
                trade_bucket=trade_bucket,
            )
            if result:
                self._log_admin_action(
                    "trade",
                    "trade",
                    None,
                    None,
                    {
                        "team_a": team_a,
                        "team_b": team_b,
                        "players_a_count": len(players_a or []),
                        "players_b_count": len(players_b or []),
                        "rights_a_count": len(right_ids_a or []),
                        "rights_b_count": len(right_ids_b or []),
                        "players_a": players_a or [],
                        "players_b": players_b or [],
                        "pick_ids_a": pick_ids_a or [],
                        "pick_ids_b": pick_ids_b or [],
                        "right_ids_a": right_ids_a or [],
                        "right_ids_b": right_ids_b or [],
                        "no_count_players_a": no_count_players_a or [],
                        "no_count_players_b": no_count_players_b or [],
                        "trade_bucket": result.get("trade_bucket"),
                        "move_count_a": result.get("team_a", {}).get("move_count"),
                        "move_count_b": result.get("team_b", {}).get("move_count"),
                    },
                )
            self._json(200 if result else 400, {"ok": bool(result), "result": result})
            return

        if parsed.path.startswith("/api/teams/") and parsed.path.endswith("/move-adjustment"):
            parts = parsed.path.split("/")
            if len(parts) < 5:
                self._json(404, {"error": "not_found"})
                return
            code = parts[3]
            season_year = parse_int(payload.get("season_year"))
            target_remaining = parse_int(payload.get("target_remaining"))
            bucket = payload.get("bucket")
            note = str(payload.get("note") or "").strip() or None
            if season_year is None or season_year < 2025 or season_year > 2030:
                self._json(400, {"error": "invalid_season_year"})
                return
            if target_remaining is None or target_remaining < 0:
                self._json(400, {"error": "invalid_target_remaining"})
                return
            result = self.db.adjust_team_move_remaining(code, season_year, bucket, target_remaining, note)
            if result:
                self._log_admin_action("update", "team_move", code.upper(), code.upper(), result)
            self._json(200 if result else 404, {"ok": bool(result), "result": result})
            return

        if parsed.path == "/api/assets":
            team_code = payload.get("team_code")
            if not team_code:
                self._json(400, {"error": "team_code_required"})
                return
            if str(payload.get("asset_type") or "").strip().lower() == "dead_cap":
                self._json(400, {"error": "dead_cap_moved_to_dead_contracts"})
                return
            asset_id = self.db.create_asset(team_code, payload)
            if not asset_id:
                self._json(404, {"error": "team_not_found"})
                return
            self._log_admin_action("create", "asset", str(asset_id), str(team_code), {"asset_type": payload.get("asset_type")})
            self._json(201, {"asset_id": asset_id})
            return

        if parsed.path == "/api/dead-contracts":
            team_code = payload.get("team_code")
            if not team_code:
                self._json(400, {"error": "team_code_required"})
                return
            dead_contract_id = self.db.create_dead_contract(team_code, payload)
            if not dead_contract_id:
                self._json(404, {"error": "team_not_found"})
                return
            self._log_admin_action(
                "create",
                "dead_contract",
                str(dead_contract_id),
                str(team_code),
                {"dead_type": payload.get("dead_type"), "label": payload.get("label")},
            )
            self._json(201, {"dead_contract_id": dead_contract_id})
            return

        if parsed.path == "/api/settings/progress-year":
            try:
                result = self.db.progress_to_next_year()
            except ValueError as err:
                if str(err) == "cannot_progress_beyond_2030":
                    self._json(400, {"error": "cannot_progress_beyond_2030"})
                    return
                raise
            merged = self.db.get_settings()
            merged_year = parse_int(merged.get("current_year")) or 2025
            if merged_year < 2025 or merged_year > 2030:
                merged_year = 2025
            merged_salary_cap = parse_float(merged.get("salary_cap_2025")) or 154647000.0
            merged_cash_limit_total = parse_float(merged.get("cash_limit_total")) or 0.0
            merged_trade_move_limit_pre30 = max(0, parse_int(merged.get("trade_move_limit_pre30")) or 0)
            merged_trade_move_limit_post30 = max(0, parse_int(merged.get("trade_move_limit_post30")) or 0)
            merged_trade_move_phase = normalize_move_phase(merged.get("trade_move_phase"))
            self._log_admin_action("update", "settings", None, None, {"progress_year": result})
            self._json(
                200,
                {
                    "ok": True,
                    "result": result,
                    "settings": {
                        "salary_cap_2025": merged_salary_cap,
                        "current_year": merged_year,
                        "first_apron": parse_float(merged.get("first_apron")) or 195945000.0,
                        "second_apron": parse_float(merged.get("second_apron")) or 207824000.0,
                        "cash_limit_total": merged_cash_limit_total,
                        "trade_move_limit_pre30": merged_trade_move_limit_pre30,
                        "trade_move_limit_post30": merged_trade_move_limit_post30,
                        "trade_move_phase": merged_trade_move_phase,
                        "luxury_cap": merged_salary_cap * 1.215,
                        "minimum_cap_allowed": merged_salary_cap * 0.9,
                    },
                },
            )
            return

        self._json(404, {"error": "not_found"})

    def do_PATCH(self) -> None:
        if not self._require_admin():
            return
        if not self._require_csrf():
            return
        parsed = urlparse(self.path)
        payload = self._read_json()

        if parsed.path == "/api/settings":
            next_salary_cap: Optional[float] = None
            next_current_year: Optional[int] = None
            next_first_apron: Optional[float] = None
            next_second_apron: Optional[float] = None
            next_cash_limit_total: Optional[float] = None
            next_trade_move_limit_pre30: Optional[int] = None
            next_trade_move_limit_post30: Optional[int] = None
            next_trade_move_phase: Optional[str] = None

            if "salary_cap_2025" in payload:
                cap = payload.get("salary_cap_2025")
                parsed_cap = parse_float(str(cap) if cap is not None else None)
                if parsed_cap is None or parsed_cap <= 0:
                    self._json(400, {"error": "invalid_salary_cap_2025"})
                    return
                next_salary_cap = parsed_cap

            if "current_year" in payload:
                parsed_year = parse_int(str(payload.get("current_year")))
                if parsed_year is None or parsed_year < 2025 or parsed_year > 2030:
                    self._json(400, {"error": "invalid_current_year"})
                    return
                next_current_year = parsed_year

            if "first_apron" in payload:
                parsed_first_apron = parse_float(str(payload.get("first_apron")))
                if parsed_first_apron is None or parsed_first_apron <= 0:
                    self._json(400, {"error": "invalid_first_apron"})
                    return
                next_first_apron = parsed_first_apron

            if "second_apron" in payload:
                parsed_second_apron = parse_float(str(payload.get("second_apron")))
                if parsed_second_apron is None or parsed_second_apron <= 0:
                    self._json(400, {"error": "invalid_second_apron"})
                    return
                next_second_apron = parsed_second_apron

            if "cash_limit_total" in payload:
                parsed_cash_limit_total = parse_float(str(payload.get("cash_limit_total")))
                if parsed_cash_limit_total is None or parsed_cash_limit_total < 0:
                    self._json(400, {"error": "invalid_cash_limit_total"})
                    return
                next_cash_limit_total = parsed_cash_limit_total

            if "trade_move_limit_pre30" in payload:
                parsed_trade_move_limit_pre30 = parse_int(str(payload.get("trade_move_limit_pre30")))
                if parsed_trade_move_limit_pre30 is None or parsed_trade_move_limit_pre30 < 0:
                    self._json(400, {"error": "invalid_trade_move_limit_pre30"})
                    return
                next_trade_move_limit_pre30 = parsed_trade_move_limit_pre30

            if "trade_move_limit_post30" in payload:
                parsed_trade_move_limit_post30 = parse_int(str(payload.get("trade_move_limit_post30")))
                if parsed_trade_move_limit_post30 is None or parsed_trade_move_limit_post30 < 0:
                    self._json(400, {"error": "invalid_trade_move_limit_post30"})
                    return
                next_trade_move_limit_post30 = parsed_trade_move_limit_post30

            if "trade_move_phase" in payload:
                next_trade_move_phase = normalize_move_phase(payload.get("trade_move_phase"))

            if (
                next_salary_cap is None
                and next_current_year is None
                and next_first_apron is None
                and next_second_apron is None
                and next_cash_limit_total is None
                and next_trade_move_limit_pre30 is None
                and next_trade_move_limit_post30 is None
                and next_trade_move_phase is None
            ):
                self._json(400, {"error": "settings_payload_required"})
                return

            if next_salary_cap is not None:
                self.db.update_setting("salary_cap_2025", str(int(next_salary_cap)))
            if next_current_year is not None:
                self.db.update_setting("current_year", str(next_current_year))
            if next_first_apron is not None:
                self.db.update_setting("first_apron", str(int(next_first_apron)))
            if next_second_apron is not None:
                self.db.update_setting("second_apron", str(int(next_second_apron)))
            if next_cash_limit_total is not None:
                self.db.update_setting("cash_limit_total", str(int(next_cash_limit_total)))
            if next_trade_move_limit_pre30 is not None:
                self.db.update_setting("trade_move_limit_pre30", str(int(next_trade_move_limit_pre30)))
            if next_trade_move_limit_post30 is not None:
                self.db.update_setting("trade_move_limit_post30", str(int(next_trade_move_limit_post30)))
            if next_trade_move_phase is not None:
                self.db.update_setting("trade_move_phase", next_trade_move_phase)
            self._log_admin_action(
                "update",
                "settings",
                None,
                None,
                {
                    "salary_cap_2025": next_salary_cap,
                    "current_year": next_current_year,
                    "first_apron": next_first_apron,
                    "second_apron": next_second_apron,
                    "cash_limit_total": next_cash_limit_total,
                    "trade_move_limit_pre30": next_trade_move_limit_pre30,
                    "trade_move_limit_post30": next_trade_move_limit_post30,
                    "trade_move_phase": next_trade_move_phase,
                },
            )

            merged = self.db.get_settings()
            merged_year = parse_int(merged.get("current_year")) or 2025
            if merged_year < 2025 or merged_year > 2030:
                merged_year = 2025
            merged_salary_cap = parse_float(merged.get("salary_cap_2025")) or 154647000.0
            merged_cash_limit_total = parse_float(merged.get("cash_limit_total")) or 0.0
            merged_trade_move_limit_pre30 = max(0, parse_int(merged.get("trade_move_limit_pre30")) or 0)
            merged_trade_move_limit_post30 = max(0, parse_int(merged.get("trade_move_limit_post30")) or 0)
            merged_trade_move_phase = normalize_move_phase(merged.get("trade_move_phase"))
            self._json(
                200,
                {
                    "ok": True,
                    "settings": {
                        "salary_cap_2025": merged_salary_cap,
                        "current_year": merged_year,
                        "first_apron": parse_float(merged.get("first_apron")) or 195945000.0,
                        "second_apron": parse_float(merged.get("second_apron")) or 207824000.0,
                        "cash_limit_total": merged_cash_limit_total,
                        "trade_move_limit_pre30": merged_trade_move_limit_pre30,
                        "trade_move_limit_post30": merged_trade_move_limit_post30,
                        "trade_move_phase": merged_trade_move_phase,
                        "luxury_cap": merged_salary_cap * 1.215,
                        "minimum_cap_allowed": merged_salary_cap * 0.9,
                    },
                },
            )
            return

        if parsed.path.startswith("/api/free-agents/"):
            try:
                free_agent_id = int(parsed.path.split("/")[-1])
            except ValueError:
                self._json(400, {"error": "invalid_free_agent_id"})
                return
            ok = self.db.update_free_agent(free_agent_id, payload)
            if ok:
                self._log_admin_action("update", "free_agent", str(free_agent_id), None, {"fields": sorted(payload.keys())})
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/players/"):
            player_id = int(parsed.path.split("/")[-1])
            ok = self.db.update_player(player_id, payload)
            if ok:
                self._log_admin_action("update", "player", str(player_id), None, {"fields": sorted(payload.keys())})
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/teams/") and parsed.path.endswith("/luxury-history"):
            parts = parsed.path.split("/")
            if len(parts) < 5:
                self._json(404, {"error": "not_found"})
                return
            code = parts[3]
            season_year = parse_int(payload.get("season_year"))
            if season_year is None or season_year < 2000 or season_year > 2100:
                self._json(400, {"error": "invalid_season_year"})
                return
            repeater = parse_bool(payload.get("repeater"))
            ok = self.db.update_team_luxury_history(code, season_year, repeater)
            if ok:
                self._log_admin_action(
                    "update",
                    "team_luxury_history",
                    f"{code.upper()}:{season_year}",
                    code.upper(),
                    {"season_year": season_year, "repeater": repeater},
                )
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/teams/"):
            code = parsed.path.split("/")[-1]
            update_payload: Dict[str, Any] = {}
            if "gm" in payload:
                gm_raw = payload.get("gm")
                update_payload["gm"] = None if gm_raw is None else str(gm_raw).strip() or None
            if "cash_received" in payload:
                parsed_cash_received = parse_float(str(payload.get("cash_received")))
                if parsed_cash_received is None or parsed_cash_received < 0:
                    self._json(400, {"error": "invalid_cash_received"})
                    return
                update_payload["cash_received"] = parsed_cash_received
            if "cash_sent" in payload:
                parsed_cash_sent = parse_float(str(payload.get("cash_sent")))
                if parsed_cash_sent is None or parsed_cash_sent < 0:
                    self._json(400, {"error": "invalid_cash_sent"})
                    return
                update_payload["cash_sent"] = parsed_cash_sent
            if "apron_hard_cap" in payload:
                raw_hard_cap = str(payload.get("apron_hard_cap") or "").strip()
                normalized_hard_cap = normalize_apron_hard_cap(raw_hard_cap)
                if raw_hard_cap and normalized_hard_cap is None:
                    self._json(400, {"error": "invalid_apron_hard_cap"})
                    return
                update_payload["apron_hard_cap"] = normalized_hard_cap
            if not update_payload:
                self._json(400, {"error": "team_update_required"})
                return
            ok = self.db.update_team_fields(code, update_payload)
            if ok:
                self._log_admin_action("update", "team", code.upper(), code.upper(), update_payload)
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/assets/"):
            asset_id = int(parsed.path.split("/")[-1])
            if "asset_type" in payload and str(payload.get("asset_type") or "").strip().lower() == "dead_cap":
                self._json(400, {"error": "dead_cap_moved_to_dead_contracts"})
                return
            ok = self.db.update_asset(asset_id, payload)
            if ok:
                self._log_admin_action("update", "asset", str(asset_id), None, {"fields": sorted(payload.keys())})
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/dead-contracts/"):
            dead_contract_id = int(parsed.path.split("/")[-1])
            ok = self.db.update_dead_contract(dead_contract_id, payload)
            if ok:
                self._log_admin_action("update", "dead_contract", str(dead_contract_id), None, {"fields": sorted(payload.keys())})
            self._json(200 if ok else 404, {"ok": ok})
            return

        self._json(404, {"error": "not_found"})

    def do_DELETE(self) -> None:
        if not self._require_admin():
            return
        if not self._require_csrf():
            return
        parsed = urlparse(self.path)

        if parsed.path.startswith("/api/free-agents/"):
            try:
                free_agent_id = int(parsed.path.split("/")[-1])
            except ValueError:
                self._json(400, {"error": "invalid_free_agent_id"})
                return
            ok = self.db.delete_free_agent(free_agent_id)
            if ok:
                self._log_admin_action("delete", "free_agent", str(free_agent_id))
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/players/"):
            player_id = int(parsed.path.split("/")[-1])
            ok = self.db.delete_player(player_id)
            if ok:
                self._log_admin_action("delete", "player", str(player_id))
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/assets/"):
            asset_id = int(parsed.path.split("/")[-1])
            ok = self.db.delete_asset(asset_id)
            if ok:
                self._log_admin_action("delete", "asset", str(asset_id))
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/dead-contracts/"):
            dead_contract_id = int(parsed.path.split("/")[-1])
            ok = self.db.delete_dead_contract(dead_contract_id)
            if ok:
                self._log_admin_action("delete", "dead_contract", str(dead_contract_id))
            self._json(200 if ok else 404, {"ok": ok})
            return

        self._json(404, {"error": "not_found"})


def run_server(db_path: str, host: str, port: int) -> None:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}. Run app/xlsx_import.py first.")

    Handler.db = LeagueDB(db_path)
    Handler.db.ensure_auth_schema()

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="ANBA roster manager server")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    run_server(args.db, args.host, args.port)


if __name__ == "__main__":
    main()
