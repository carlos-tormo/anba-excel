#!/usr/bin/env python3
import argparse
import json
import os
import secrets
import sqlite3
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


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def normalize_dead_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"two_way", "tw"}:
        return "two_way"
    return "normal"


def normalize_pick_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"acquired", "sold"}:
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
                CREATE TABLE IF NOT EXISTS dead_contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                    row_order INTEGER NOT NULL DEFAULT 0,
                    dead_type TEXT NOT NULL DEFAULT 'normal',
                    label TEXT,
                    amount_text TEXT,
                    amount_num REAL,
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
            cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(players)").fetchall()
            }
            option_cols = [f"option_{season}" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            for col in option_cols:
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
            conn.commit()

    def get_settings(self) -> Dict[str, str]:
        with self.connect() as conn:
            cur = conn.execute("SELECT key, value FROM app_settings")
            return {str(row["key"]): str(row["value"]) for row in cur.fetchall()}

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
            cur = conn.execute("SELECT id, code, name, gm FROM teams ORDER BY code")
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
            return {"team": team, "players": players, "assets": assets, "dead_contracts": dead_contracts, "summary": summary}

    def list_tracker(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            settings = self.get_settings()
            team_cur = conn.execute("SELECT * FROM teams ORDER BY code")
            teams = [row_to_dict(team_cur, row) for row in team_cur.fetchall()]
            rows: List[Dict[str, Any]] = []

            for team in teams:
                players_cur = conn.execute("SELECT * FROM players WHERE team_id = ?", (team["id"],))
                players = [row_to_dict(players_cur, r) for r in players_cur.fetchall()]
                assets_cur = conn.execute("SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap'", (team["id"],))
                assets = [row_to_dict(assets_cur, r) for r in assets_cur.fetchall()]
                dead_cur = conn.execute("SELECT * FROM dead_contracts WHERE team_id = ?", (team["id"],))
                dead_contracts = [row_to_dict(dead_cur, r) for r in dead_cur.fetchall()]
                summary = self._calc_summary(team, players, assets, dead_contracts, settings)
                rows.append(
                    {
                        "team_code": team["code"],
                        "team_name": team["name"],
                        "cap_total": summary["cap_figure"],
                        "gasto_total": summary["payroll"],
                        "espacio_cap": summary["room_to_cap"],
                        "espacio_luxury": summary["room_to_luxury"],
                        "espacio_1er_apron": summary["room_to_first_apron"],
                        "espacio_2do_apron": summary["room_to_second_apron"],
                    }
                )
            return rows

    def update_team_gm(self, code: str, gm: Optional[str]) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE teams SET gm = ?, updated_at = ? WHERE code = ?",
                (gm, now_iso(), code.upper()),
            )
            conn.commit()
            return cur.rowcount > 0

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
        salary_num_key = f"salary_{current_year}_num"

        # CAP Total: current-year player salaries excluding TW contracts.
        cap_figure_players = sum((p.get(salary_num_key) or 0.0) for p in players if not p.get("is_two_way"))
        # GASTO Total: current-year player salaries including TW contracts.
        player_payroll = sum((p.get(salary_num_key) or 0.0) for p in players)

        dead_cap_normal = sum(
            (d.get("amount_num") or 0.0)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "normal"
        )
        dead_cap_two_way = sum(
            (d.get("amount_num") or 0.0)
            for d in dead_contracts
            if normalize_dead_type(d.get("dead_type")) == "two_way"
        )
        exceptions = sum((a.get("amount_num") or 0.0) for a in assets if a.get("asset_type") == "exception")

        cap_figure = cap_figure_players + dead_cap_normal
        payroll = player_payroll + dead_cap_normal + dead_cap_two_way

        salary_cap = parse_float(settings.get("salary_cap_2025")) or team["salary_cap"]
        luxury = team["luxury_cap"]
        first_apron = team["first_apron"]
        second_apron = team["second_apron"]

        return {
            "player_payroll": player_payroll,
            "dead_cap": dead_cap_normal + dead_cap_two_way,
            "dead_cap_normal": dead_cap_normal,
            "dead_cap_two_way": dead_cap_two_way,
            "exceptions_total": exceptions,
            "cap_figure": cap_figure,
            "payroll": payroll,
            "salary_cap_2025": salary_cap,
            "current_year": current_year,
            "room_to_cap": salary_cap - cap_figure,
            "room_to_luxury": luxury - cap_figure,
            "room_to_first_apron": first_apron - cap_figure,
            "room_to_second_apron": second_apron - cap_figure,
        }

    def update_player(self, player_id: int, payload: Dict[str, Any]) -> bool:
        fields = [
            "name", "bird_rights", "rating", "position", "years_left",
            "salary_2025_text", "salary_2026_text", "salary_2027_text",
            "salary_2028_text", "salary_2029_text", "salary_2030_text",
            "option_2025", "option_2026", "option_2027", "option_2028", "option_2029", "option_2030",
            "notes",
        ]
        assignments = []
        values: List[Any] = []

        for f in fields:
            if f in payload:
                assignments.append(f"{f} = ?")
                values.append(payload[f])

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
                "option_2025": payload.get("option_2025"),
                "option_2026": payload.get("option_2026"),
                "option_2027": payload.get("option_2027"),
                "option_2028": payload.get("option_2028"),
                "option_2029": payload.get("option_2029"),
                "option_2030": payload.get("option_2030"),
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
                    notes, is_two_way, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            if asset_type == "draft_pick" and draft_pick_type != "acquired":
                original_owner = None
            cur = conn.execute(
                """
                INSERT INTO assets (
                    team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                    draft_pick_type, draft_round, original_owner, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_asset(self, asset_id: int, payload: Dict[str, Any]) -> bool:
        fields = ["asset_type", "year", "label", "detail", "amount_text", "draft_pick_type", "draft_round", "original_owner"]
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
            amount_text = payload.get("amount_text")
            cur = conn.execute(
                """
                INSERT INTO dead_contracts (team_id, row_order, dead_type, label, amount_text, amount_num, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team["id"],
                    int(mx) + 1,
                    normalize_dead_type(payload.get("dead_type")),
                    payload.get("label", "Dead Contract"),
                    amount_text,
                    parse_float(amount_text),
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_dead_contract(self, dead_contract_id: int, payload: Dict[str, Any]) -> bool:
        fields = ["label", "amount_text"]
        assigns = []
        vals = []
        if "dead_type" in payload:
            assigns.append("dead_type = ?")
            vals.append(normalize_dead_type(payload.get("dead_type")))
        for f in fields:
            if f in payload:
                assigns.append(f"{f} = ?")
                vals.append(payload[f])
        if "amount_text" in payload:
            assigns.append("amount_num = ?")
            vals.append(parse_float(payload["amount_text"]))
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

    def process_trade(self, team_a_code: str, team_b_code: str, players_a: List[int], players_b: List[int]) -> bool:
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
        if not ids_a or not ids_b:
            return False

        with self.connect() as conn:
            team_a = conn.execute("SELECT id FROM teams WHERE code = ?", (team_a_code.upper(),)).fetchone()
            team_b = conn.execute("SELECT id FROM teams WHERE code = ?", (team_b_code.upper(),)).fetchone()
            if not team_a or not team_b or team_a["id"] == team_b["id"]:
                return False

            for player_id in ids_a:
                row = conn.execute("SELECT team_id FROM players WHERE id = ?", (player_id,)).fetchone()
                if not row or int(row["team_id"]) != int(team_a["id"]):
                    return False
            for player_id in ids_b:
                row = conn.execute("SELECT team_id FROM players WHERE id = ?", (player_id,)).fetchone()
                if not row or int(row["team_id"]) != int(team_b["id"]):
                    return False

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
            conn.commit()
            return True

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

        if parsed.path == "/api/settings":
            settings = self.db.get_settings()
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < 2025 or current_year > 2030:
                current_year = 2025
            self._json(
                200,
                {
                    "settings": {
                        "salary_cap_2025": parse_float(settings.get("salary_cap_2025")) or 154647000.0,
                        "current_year": current_year,
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
            ok = self.db.process_trade(team_a, team_b, players_a, players_b)
            if ok:
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
                        "players_a": players_a or [],
                        "players_b": players_b or [],
                    },
                )
            self._json(200 if ok else 400, {"ok": ok})
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

            if next_salary_cap is None and next_current_year is None:
                self._json(400, {"error": "settings_payload_required"})
                return

            if next_salary_cap is not None:
                self.db.update_setting("salary_cap_2025", str(int(next_salary_cap)))
            if next_current_year is not None:
                self.db.update_setting("current_year", str(next_current_year))
            self._log_admin_action(
                "update",
                "settings",
                None,
                None,
                {"salary_cap_2025": next_salary_cap, "current_year": next_current_year},
            )

            merged = self.db.get_settings()
            merged_year = parse_int(merged.get("current_year")) or 2025
            if merged_year < 2025 or merged_year > 2030:
                merged_year = 2025
            self._json(
                200,
                {
                    "ok": True,
                    "settings": {
                        "salary_cap_2025": parse_float(merged.get("salary_cap_2025")) or 154647000.0,
                        "current_year": merged_year,
                    },
                },
            )
            return

        if parsed.path.startswith("/api/players/"):
            player_id = int(parsed.path.split("/")[-1])
            ok = self.db.update_player(player_id, payload)
            if ok:
                self._log_admin_action("update", "player", str(player_id), None, {"fields": sorted(payload.keys())})
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/teams/"):
            code = parsed.path.split("/")[-1]
            if "gm" not in payload:
                self._json(400, {"error": "gm_required"})
                return
            gm_raw = payload.get("gm")
            gm_val = None if gm_raw is None else str(gm_raw).strip()
            ok = self.db.update_team_gm(code, gm_val or None)
            if ok:
                self._log_admin_action("update", "team", code.upper(), code.upper(), {"gm": gm_val or None})
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
