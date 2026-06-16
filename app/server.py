#!/usr/bin/env python3
import argparse
import base64
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
ROSTER_STANDARD_MIN_DEFAULT = 14
ROSTER_STANDARD_MAX_DEFAULT = 15
ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT = 18
ROSTER_TWO_WAY_MIN_DEFAULT = 0
ROSTER_TWO_WAY_MAX_DEFAULT = 3
CAP_FORECAST_MIN_YEAR = 2025
CAP_FORECAST_MAX_YEAR = 2035
CAP_FORECAST_WINDOW = 6
TEAM_IMAGE_COLORS = {
    "ATL": "#E03A3E, #C1D32F",
    "BKN": "#000000, #FFFFFF",
    "BOS": "#007A33, #BA9653",
    "CHA": "#1D1160, #00788C",
    "CHI": "#CE1141, #000000",
    "CLE": "#860038, #FDBB30",
    "DAL": "#00538C, #002F5F",
    "DEN": "#0E2240, #FEC524",
    "DET": "#C8102E, #1D42BA",
    "GSW": "#1D428A, #FFC72C",
    "HOU": "#CE1141, #000000",
    "IND": "#002D62, #FDBB30",
    "LAC": "#C8102E, #1D428A",
    "LAL": "#552583, #FDB927",
    "MEM": "#12173F, #5D76A9",
    "MIA": "#98002E, #000000",
    "MIL": "#00471B, #EEE1C6",
    "MIN": "#0C2340, #9EA2A2",
    "NOP": "#0C2340, #C8102E",
    "NYK": "#006BB6, #F58426",
    "OKC": "#007AC1, #EF3B24",
    "ORL": "#0077C0, #000000",
    "PHI": "#006BB6, #ED174C",
    "PHX": "#E56020, #1D1160",
    "POR": "#E03A3E, #000000",
    "SAC": "#5A2D81, #63727A",
    "SAS": "#000000, #C4CED4",
    "TOR": "#CE1141, #000000",
    "UTA": "#002B5C, #00471B",
    "WAS": "#002B5C, #E31837",
}
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


def season_label(start_year: Any) -> str:
    year = parse_int(str(start_year)) or 2025
    return f"{year}-{(year + 1) % 100:02d}"


def settings_int(settings: Dict[str, str], key: str, default: int) -> int:
    parsed = parse_int(settings.get(key))
    if parsed is None or parsed < 0:
        return default
    return parsed


def public_settings_payload(settings: Dict[str, str]) -> Dict[str, Any]:
    current_year = parse_int(settings.get("current_year")) or 2025
    if current_year < 2025 or current_year > 2030:
        current_year = 2025
    salary_cap = parse_float(settings.get("salary_cap_2025")) or 154647000.0
    first_apron = parse_float(settings.get("first_apron")) or 195945000.0
    second_apron = parse_float(settings.get("second_apron")) or 207824000.0
    payload = {
        "salary_cap_2025": salary_cap,
        "current_year": current_year,
        "first_apron": first_apron,
        "second_apron": second_apron,
        "cash_limit_total": parse_float(settings.get("cash_limit_total")) or 0.0,
        "trade_move_limit_pre30": max(0, parse_int(settings.get("trade_move_limit_pre30")) or 0),
        "trade_move_limit_post30": max(0, parse_int(settings.get("trade_move_limit_post30")) or 0),
        "trade_move_phase": normalize_move_phase(settings.get("trade_move_phase")),
        "free_agency_mode": parse_bool(settings.get("free_agency_mode")),
        "roster_standard_min": settings_int(settings, "roster_standard_min", ROSTER_STANDARD_MIN_DEFAULT),
        "roster_standard_max": settings_int(settings, "roster_standard_max", ROSTER_STANDARD_MAX_DEFAULT),
        "roster_standard_offseason_max": settings_int(settings, "roster_standard_offseason_max", ROSTER_STANDARD_OFFSEASON_MAX_DEFAULT),
        "roster_two_way_min": settings_int(settings, "roster_two_way_min", ROSTER_TWO_WAY_MIN_DEFAULT),
        "roster_two_way_max": settings_int(settings, "roster_two_way_max", ROSTER_TWO_WAY_MAX_DEFAULT),
        "luxury_cap": salary_cap * 1.215,
        "minimum_cap_allowed": salary_cap * 0.9,
    }
    for season in range(current_year, current_year + CAP_FORECAST_WINDOW):
        season_cap = parse_float(settings.get(f"salary_cap_{season}")) or salary_cap
        season_first_apron = parse_float(settings.get(f"first_apron_{season}")) or first_apron
        season_second_apron = parse_float(settings.get(f"second_apron_{season}")) or second_apron
        season_average_salary = parse_float(settings.get(f"average_salary_{season}"))
        payload[f"salary_cap_{season}"] = season_cap
        payload[f"first_apron_{season}"] = season_first_apron
        payload[f"second_apron_{season}"] = season_second_apron
        payload[f"average_salary_{season}"] = season_average_salary if season_average_salary and season_average_salary > 0 else 0.0
    return payload


def luxury_tax_amount(overage: float, repeater: bool) -> float:
    remaining = max(0.0, float(overage or 0.0))
    if remaining <= 0:
        return 0.0
    tier_size = 5_000_000.0
    base_rates = [2.5, 2.75, 3.5, 4.25] if repeater else [1.5, 1.75, 2.5, 3.25]
    tax = 0.0
    tier_index = 0
    while remaining > 0:
        taxable = min(tier_size, remaining)
        if tier_index < len(base_rates):
            rate = base_rates[tier_index]
        else:
            rate = base_rates[-1] + ((tier_index - len(base_rates) + 1) * 0.5)
        tax += taxable * rate
        remaining -= taxable
        tier_index += 1
    return tax


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


def parse_gm_account_map(value: Any) -> Dict[str, List[str]]:
    if value is None:
        return {}
    raw = str(value or "").strip()
    if not raw:
        return {}

    parsed_items: List[Any]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        parsed_items = [{"email": email, "teams": teams} for email, teams in parsed.items()]
    elif isinstance(parsed, list):
        parsed_items = parsed
    else:
        parsed_items = re.split(r"[\n,]+", raw)

    mapping: Dict[str, List[str]] = {}
    for item in parsed_items:
        if isinstance(item, dict):
            email = str(item.get("email") or "").strip().lower()
            teams_value = item.get("teams") or item.get("team_codes") or item.get("team_code")
        else:
            text = str(item or "").strip()
            if not text:
                continue
            if "=" in text:
                email, teams_value = text.split("=", 1)
            elif ":" in text:
                email, teams_value = text.split(":", 1)
            else:
                continue
            email = email.strip().lower()

        if not email or "@" not in email:
            continue
        team_codes = normalize_team_codes(teams_value)
        if team_codes:
            mapping[email] = team_codes
    return mapping


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


def normalize_gm_start_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_hex_color(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"#[0-9a-fA-F]{6}", raw):
        return raw.upper()
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
                INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                VALUES ('free_agency_mode', '0', ?)
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(team_id, season_year),
                    FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
                    FOREIGN KEY(gm_user_id) REFERENCES users(id) ON DELETE SET NULL
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_team_gm_history_team_start ON team_gm_history(team_id, start_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_order_year_round ON draft_order(draft_year, draft_round, pick_number)")
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
            owner_profile_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(team_owner_profiles)").fetchall()
            }
            if "performance_json" not in owner_office_cols:
                conn.execute("ALTER TABLE team_owner_office ADD COLUMN performance_json TEXT NOT NULL DEFAULT '[]'")
            if "owner_conclusion_message" not in owner_exit_cols:
                conn.execute("ALTER TABLE owner_exit_interviews ADD COLUMN owner_conclusion_message TEXT")
            if "owner_office_background_url" not in owner_profile_cols:
                conn.execute("ALTER TABLE team_owner_profiles ADD COLUMN owner_office_background_url TEXT")
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
            if "contract_notes" not in cols:
                conn.execute("ALTER TABLE players ADD COLUMN contract_notes INTEGER NOT NULL DEFAULT 0")
            partial_guarantee_bool_cols = [f"salary_{season}_partially_guaranteed" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            partial_guarantee_text_cols = [f"salary_{season}_guaranteed_text" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            contract_note_bool_cols = [f"salary_{season}_note" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            contract_note_text_cols = [f"salary_{season}_note_text" for season in [2025, 2026, 2027, 2028, 2029, 2030]]
            for col in partial_guarantee_bool_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            for col in partial_guarantee_text_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT")
            for col in contract_note_bool_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            for col in contract_note_text_cols:
                if col not in cols:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT")
            if "reference_image_url" not in cols:
                conn.execute("ALTER TABLE players ADD COLUMN reference_image_url TEXT")
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

    def get_user_team_codes_by_email(self, email: str) -> List[str]:
        normalized = str(email or "").strip().lower()
        if not normalized:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.code
                FROM users u
                JOIN user_team_assignments a ON a.user_id = u.id
                JOIN teams t ON t.id = a.team_id
                WHERE lower(u.email) = ?
                ORDER BY t.code
                """,
                (normalized,),
            ).fetchall()
            return [str(row["code"]).upper() for row in rows]

    def list_users(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    u.avatar_url,
                    u.created_at,
                    u.updated_at,
                    GROUP_CONCAT(t.code, ',') AS team_codes
                FROM users u
                LEFT JOIN user_team_assignments a ON a.user_id = u.id
                LEFT JOIN teams t ON t.id = a.team_id
                GROUP BY u.id
                ORDER BY lower(u.email)
                """
            )
            rows = []
            for row in cur.fetchall():
                item = row_to_dict(cur, row)
                item["team_codes"] = normalize_team_codes(item.get("team_codes"))
                rows.append(item)
            return rows

    def replace_user_team_assignments(self, user_id: int, team_codes: Any) -> Optional[Dict[str, Any]]:
        normalized_codes = normalize_team_codes(team_codes)
        timestamp = now_iso()
        with self.connect() as conn:
            user_row = conn.execute("SELECT id FROM users WHERE id = ?", (int(user_id),)).fetchone()
            if not user_row:
                return None

            team_rows_by_code: Dict[str, sqlite3.Row] = {}
            if normalized_codes:
                placeholders = ",".join("?" for _ in normalized_codes)
                team_rows = conn.execute(
                    f"SELECT id, code FROM teams WHERE code IN ({placeholders})",
                    normalized_codes,
                ).fetchall()
                team_rows_by_code = {str(row["code"]).upper(): row for row in team_rows}
                missing = [code for code in normalized_codes if code not in team_rows_by_code]
                if missing:
                    raise ValueError(f"invalid_team_code:{missing[0]}")

            conn.execute("DELETE FROM user_team_assignments WHERE user_id = ?", (int(user_id),))
            for code in normalized_codes:
                team_row = team_rows_by_code[code]
                conn.execute(
                    """
                    INSERT INTO user_team_assignments (user_id, team_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (int(user_id), int(team_row["id"]), timestamp, timestamp),
                )
            conn.execute("UPDATE users SET updated_at = ? WHERE id = ?", (timestamp, int(user_id)))
            conn.commit()

        return next((user for user in self.list_users() if int(user.get("id") or 0) == int(user_id)), None)

    def _gm_option_request_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = row_to_dict(cursor, row)
        raw_field = str(item.get("option_field") or "")
        match = re.fullmatch(r"option_(20\d{2})", raw_field)
        season_year = parse_int(match.group(1)) if match else None
        item["season_year"] = season_year
        item["season_label"] = f"{season_year}-{(season_year + 1) % 100:02d}" if season_year else ""
        return item

    def get_gm_option_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    r.*,
                    p.name AS player_name,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_option_requests r
                JOIN players p ON p.id = r.player_id
                JOIN teams t ON t.id = r.team_id
                WHERE r.id = ?
                """,
                (int(request_id),),
            )
            row = cur.fetchone()
            return self._gm_option_request_from_row(cur, row) if row else None

    def list_gm_option_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        params: List[Any] = []
        where = ""
        if normalized_status and normalized_status != "all":
            where = "WHERE r.status = ?"
            params.append(normalized_status)
        with self.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT
                    r.*,
                    p.name AS player_name,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_option_requests r
                JOIN players p ON p.id = r.player_id
                JOIN teams t ON t.id = r.team_id
                {where}
                ORDER BY
                    CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                    r.created_at DESC,
                    r.id DESC
                """,
                params,
            )
            return [self._gm_option_request_from_row(cur, row) for row in cur.fetchall()]

    def create_gm_option_request(
        self,
        player_id: int,
        option_field: str,
        option_value: str,
        action: str,
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        field = str(option_field or "").strip()
        match = re.fullmatch(r"option_(20\d{2})", field)
        if not match:
            raise ValueError("invalid_option_field")
        option = str(option_value or "").strip().upper()
        if option not in {"TO", "QO", "GAP"}:
            raise ValueError("invalid_option_value")
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"accepted", "rejected"}:
            raise ValueError("invalid_option_action")

        timestamp = now_iso()
        request_id: Optional[int] = None
        with self.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT p.id, p.name, p.team_id, p.{field} AS current_option, t.code AS team_code
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (int(player_id),),
            )
            player = cur.fetchone()
            if not player:
                return None
            current_option = str(player["current_option"] or "").strip().upper()
            if current_option != option:
                raise ValueError("option_mismatch")

            existing = conn.execute(
                """
                SELECT id
                FROM gm_option_requests
                WHERE player_id = ? AND option_field = ? AND status = 'pending'
                """,
                (int(player_id), field),
            ).fetchone()
            if existing:
                request_id = int(existing["id"])
                requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
                conn.execute(
                    """
                    UPDATE gm_option_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        option_value = ?,
                        action = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        option,
                        normalized_action,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_option_requests (
                        player_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        option_field,
                        option_value,
                        action,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(player_id),
                        int(player["team_id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        field,
                        option,
                        normalized_action,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
            conn.commit()

        return self.get_gm_option_request(request_id) if request_id is not None else None

    def mark_gm_option_request_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE gm_option_requests
                SET
                    status = ?,
                    admin_email = ?,
                    admin_name = ?,
                    admin_decision_note = ?,
                    updated_at = ?,
                    decided_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (
                    normalized_status,
                    str(admin.get("email") or "").strip() if admin else None,
                    str(admin.get("name") or "").strip() if admin else None,
                    note,
                    timestamp,
                    timestamp,
                    int(request_id),
                ),
            )
            conn.commit()
            if cur.rowcount < 1:
                return None
        return self.get_gm_option_request(request_id)

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

    def current_draft_year(self) -> int:
        settings = self.get_settings()
        current_year = parse_int(settings.get("current_year")) or 2025
        if current_year < 2025 or current_year > 2030:
            current_year = 2025
        return current_year + 1

    def _normalize_draft_order_payload(
        self,
        conn: sqlite3.Connection,
        payload: Dict[str, Any],
        *,
        existing: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source = dict(existing or {})
        source.update(payload)

        draft_year = parse_int(source.get("draft_year"))
        if draft_year is None:
            draft_year = self.current_draft_year()
        if draft_year < 2000 or draft_year > 2100:
            raise ValueError("invalid_draft_year")

        pick_number = parse_int(source.get("pick_number"))
        if pick_number is None or pick_number <= 0 or pick_number > 300:
            raise ValueError("invalid_pick_number")

        draft_round = normalize_pick_round(source.get("draft_round"))
        owner_team_code = normalize_team_code(source.get("owner_team_code"))
        original_team_code = normalize_team_code(source.get("original_team_code"))
        if not owner_team_code or not original_team_code:
            raise ValueError("team_codes_required")

        existing_codes = {
            str(row["code"]).upper()
            for row in conn.execute(
                "SELECT code FROM teams WHERE code IN (?, ?)",
                (owner_team_code, original_team_code),
            ).fetchall()
        }
        if owner_team_code not in existing_codes or original_team_code not in existing_codes:
            raise ValueError("team_not_found")

        return {
            "draft_year": draft_year,
            "draft_round": draft_round,
            "pick_number": pick_number,
            "owner_team_code": owner_team_code,
            "original_team_code": original_team_code,
        }

    def list_draft_order(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        year = draft_year if draft_year is not None else self.current_draft_year()
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    d.id,
                    d.draft_year,
                    d.draft_round,
                    d.pick_number,
                    d.owner_team_code,
                    COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                    d.original_team_code,
                    COALESCE(original.name, d.original_team_code) AS original_team_name,
                    d.created_at,
                    d.updated_at
                FROM draft_order d
                LEFT JOIN teams owner ON owner.code = d.owner_team_code
                LEFT JOIN teams original ON original.code = d.original_team_code
                WHERE d.draft_year = ?
                ORDER BY
                    CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                    d.pick_number,
                    d.id
                """,
                (int(year),),
            )
            return {
                "draft_year": int(year),
                "draft_order": [row_to_dict(cur, row) for row in cur.fetchall()],
            }

    def create_draft_order_entry(self, payload: Dict[str, Any]) -> int:
        with self.connect() as conn:
            values = self._normalize_draft_order_payload(conn, payload)
            timestamp = now_iso()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO draft_order (
                        draft_year, draft_round, pick_number, owner_team_code,
                        original_team_code, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["draft_year"],
                        values["draft_round"],
                        values["pick_number"],
                        values["owner_team_code"],
                        values["original_team_code"],
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("duplicate_draft_pick") from err
            conn.commit()
            return int(cur.lastrowid)

    def update_draft_order_entry(self, entry_id: int, payload: Dict[str, Any]) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM draft_order WHERE id = ?", (entry_id,)).fetchone()
            if not row:
                return False
            values = self._normalize_draft_order_payload(conn, payload, existing=dict(row))
            try:
                cur = conn.execute(
                    """
                    UPDATE draft_order
                    SET draft_year = ?,
                        draft_round = ?,
                        pick_number = ?,
                        owner_team_code = ?,
                        original_team_code = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        values["draft_year"],
                        values["draft_round"],
                        values["pick_number"],
                        values["owner_team_code"],
                        values["original_team_code"],
                        now_iso(),
                        entry_id,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("duplicate_draft_pick") from err
            conn.commit()
            return cur.rowcount > 0

    def delete_draft_order_entry(self, entry_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM draft_order WHERE id = ?", (entry_id,))
            conn.commit()
            return cur.rowcount > 0

    def _attach_option_decisions(self, conn: sqlite3.Connection, players: List[Dict[str, Any]], team_id: int) -> None:
        if not players:
            return
        player_ids = {int(player["id"]) for player in players if parse_int(player.get("id")) is not None}
        if not player_ids:
            return
        latest_by_key: Dict[tuple[int, str], Dict[str, Any]] = {}
        cur = conn.execute(
            """
            SELECT
                id,
                player_id,
                option_field,
                option_value,
                action,
                status,
                created_at,
                updated_at,
                decided_at
            FROM gm_option_requests
            WHERE team_id = ? AND status = 'approved'
            ORDER BY
                COALESCE(decided_at, updated_at, created_at) DESC,
                id DESC
            """,
            (int(team_id),),
        )
        for row in cur.fetchall():
            player_id = int(row["player_id"])
            if player_id not in player_ids:
                continue
            option_field = str(row["option_field"] or "").strip()
            key = (player_id, option_field)
            if key in latest_by_key:
                continue
            latest_by_key[key] = {
                "request_id": int(row["id"]),
                "option_value": str(row["option_value"] or "").strip().upper(),
                "action": str(row["action"] or "").strip().lower(),
                "status": str(row["status"] or "").strip().lower(),
            }
        for player in players:
            player_id = parse_int(player.get("id"))
            player["option_decisions"] = {}
            if player_id is None:
                continue
            for (decision_player_id, option_field), decision in latest_by_key.items():
                if decision_player_id == player_id:
                    player["option_decisions"][option_field] = decision

    def get_team(self, code: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            team_cur = conn.execute("SELECT * FROM teams WHERE code = ?", (code.upper(),))
            row = team_cur.fetchone()
            if not row:
                return None
            team = row_to_dict(team_cur, row)

            player_cur = conn.execute("SELECT * FROM players WHERE team_id = ? ORDER BY row_order, id", (team["id"],))
            players = [row_to_dict(player_cur, r) for r in player_cur.fetchall()]
            self._attach_option_decisions(conn, players, int(team["id"]))

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
            gm_cur = conn.execute(
                """
                SELECT
                    h.id,
                    t.code AS team_code,
                    t.name AS team_name,
                    h.row_order,
                    h.gm_name,
                    h.start_date,
                    h.color,
                    h.created_at,
                    h.updated_at
                FROM team_gm_history h
                JOIN teams t ON t.id = h.team_id
                WHERE h.team_id = ?
                ORDER BY h.start_date, h.row_order, h.id
                """,
                (team["id"],),
            )
            gm_history = [row_to_dict(gm_cur, r) for r in gm_cur.fetchall()]
            return {
                "team": team,
                "players": players,
                "assets": assets,
                "dead_contracts": dead_contracts,
                "summary": summary,
                "move_summary": move_summary,
                "luxury_history": luxury_history,
                "gm_history": gm_history,
            }

    def get_player_record(self, player_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT p.*, t.code AS team_code, t.name AS team_name
                FROM players p
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (player_id,),
            )
            row = cur.fetchone()
            return row_to_dict(cur, row) if row else None

    def list_gm_history(self, code: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        with self.connect() as conn:
            params: List[Any] = []
            where = ""
            if code:
                where = "WHERE t.code = ?"
                params.append(code.upper())
                exists = conn.execute("SELECT 1 FROM teams WHERE code = ?", (code.upper(),)).fetchone()
                if not exists:
                    return None
            cur = conn.execute(
                f"""
                SELECT
                    h.id,
                    t.code AS team_code,
                    t.name AS team_name,
                    h.row_order,
                    h.gm_name,
                    h.start_date,
                    h.color,
                    h.created_at,
                    h.updated_at
                FROM team_gm_history h
                JOIN teams t ON t.id = h.team_id
                {where}
                ORDER BY t.code, h.start_date, h.row_order, h.id
                """,
                params,
            )
            return [row_to_dict(cur, row) for row in cur.fetchall()]

    def replace_gm_history(self, code: str, entries: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        normalized: List[Dict[str, Any]] = []
        for raw in entries:
            gm_name = str(raw.get("gm_name") or raw.get("name") or "").strip()
            start_date = normalize_gm_start_date(raw.get("start_date"))
            if not gm_name or not start_date:
                raise ValueError("invalid_gm_history_entry")
            normalized.append(
                {
                    "gm_name": gm_name,
                    "start_date": start_date,
                    "color": normalize_hex_color(raw.get("color")),
                }
            )

        normalized.sort(key=lambda row: (row["start_date"], row["gm_name"].lower()))

        with self.connect() as conn:
            team_row = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team_row:
                return None
            team_id = int(team_row["id"])
            timestamp = now_iso()
            conn.execute("DELETE FROM team_gm_history WHERE team_id = ?", (team_id,))
            for idx, entry in enumerate(normalized, start=1):
                conn.execute(
                    """
                    INSERT INTO team_gm_history (
                        team_id, row_order, gm_name, start_date, color, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        team_id,
                        idx,
                        entry["gm_name"],
                        entry["start_date"],
                        entry["color"],
                        timestamp,
                        timestamp,
                    ),
                )
            conn.commit()
        return self.list_gm_history(code)

    def list_tracker(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < 2025 or current_year > 2030:
                current_year = 2025
            team_cur = conn.execute("SELECT * FROM teams ORDER BY code")
            teams = [row_to_dict(team_cur, row) for row in team_cur.fetchall()]
            rows: List[Dict[str, Any]] = []

            draft_year_start = current_year + 1

            def pick_round_for_tracker(asset: Dict[str, Any]) -> str:
                round_raw = str(asset.get("draft_round") or "").strip().lower()
                if "2" in round_raw:
                    return "2nd"
                if "1" in round_raw:
                    return "1st"
                label = str(asset.get("label") or "").strip().lower()
                return "2nd" if "2" in label else "1st"

            def draft_counts_for_tracker(assets: List[Dict[str, Any]]) -> Dict[str, int]:
                counts = {"draft_first_count": 0, "draft_second_count": 0}
                for asset in assets:
                    if asset.get("asset_type") != "draft_pick":
                        continue
                    if normalize_pick_type(asset.get("draft_pick_type")) == "sold":
                        continue
                    year = parse_int(asset.get("year"))
                    if year is not None and year < draft_year_start:
                        continue
                    if pick_round_for_tracker(asset) == "2nd":
                        counts["draft_second_count"] += 1
                    else:
                        counts["draft_first_count"] += 1
                return counts

            for team in teams:
                team_id = int(team["id"])
                player_cur = conn.execute(
                    "SELECT * FROM players WHERE team_id = ? ORDER BY row_order, id",
                    (team_id,),
                )
                players = [row_to_dict(player_cur, row) for row in player_cur.fetchall()]
                asset_cur = conn.execute(
                    "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                    (team_id,),
                )
                assets = [row_to_dict(asset_cur, row) for row in asset_cur.fetchall()]
                dead_cur = conn.execute(
                    "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                    (team_id,),
                )
                dead_contracts = [row_to_dict(dead_cur, row) for row in dead_cur.fetchall()]
                summary = self._calc_summary(team, players, assets, dead_contracts, settings)
                luxury_cap = float(summary["salary_cap_2025"]) * 1.215
                luxury_overage = max(0.0, float(summary["cap_figure"]) - luxury_cap)
                luxury_repeater = self._team_luxury_repeater_for_season(conn, team_id, current_year)
                draft_counts = draft_counts_for_tracker(assets)
                rows.append(
                    {
                        "team_code": team["code"],
                        "team_name": team["name"],
                        "cap_total": float(summary["cap_figure"]),
                        "gasto_total": float(summary["payroll"]),
                        "espacio_cap": float(summary["room_to_cap"]),
                        "espacio_luxury": float(summary["room_to_luxury"]),
                        "luxury_tax": float(luxury_tax_amount(luxury_overage, luxury_repeater)),
                        "espacio_1er_apron": float(summary["room_to_first_apron"]),
                        "espacio_2do_apron": float(summary["room_to_second_apron"]),
                        "roster_standard_count": int(summary["roster_standard_count"]),
                        "roster_two_way_count": int(summary["roster_two_way_count"]),
                        "draft_first_count": int(draft_counts["draft_first_count"]),
                        "draft_second_count": int(draft_counts["draft_second_count"]),
                    }
                )
            return rows

    def list_team_economy(self, season_year: Optional[int] = None) -> Dict[str, Any]:
        with self.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < CAP_FORECAST_MIN_YEAR or current_year > CAP_FORECAST_MAX_YEAR:
                current_year = 2025
            season = season_year if season_year is not None else current_year
            if season < 2000 or season > 2100:
                season = current_year
            seasons = {
                current_year,
                2025,
                *[
                    int(row["season_year"])
                    for row in conn.execute(
                        "SELECT DISTINCT season_year FROM team_economy ORDER BY season_year"
                    ).fetchall()
                ],
            }
            teams_cur = conn.execute(
                """
                SELECT
                    t.id,
                    t.code,
                    t.name,
                    COALESCE(e.balance, 0) AS balance,
                    COALESCE(e.revenue, 0) AS revenue,
                    COALESCE(e.expenses, 0) AS expenses
                FROM teams t
                LEFT JOIN team_economy e
                  ON e.team_id = t.id AND e.season_year = ?
                ORDER BY t.code
                """,
                (season,),
            )
            rows = [
                {
                    "team_code": row["code"],
                    "team_name": row["name"],
                    "season_year": season,
                    "balance": float(row["balance"] or 0),
                    "revenue": float(row["revenue"] or 0),
                    "expenses": float(row["expenses"] or 0),
                }
                for row in teams_cur.fetchall()
            ]
            return {
                "season_year": season,
                "seasons": sorted(seasons),
                "rows": rows,
            }

    def _owner_office_rows_from_json(self, value: Any) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        rows: List[Dict[str, Any]] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or "").strip()
            label = str(raw.get("label") or "").strip()
            row_type = str(raw.get("type") or "field").strip().lower()
            if row_type not in {"category", "field"}:
                row_type = "field"
            if not key or not label:
                continue
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "type": row_type,
                    "value": "" if raw.get("value") is None else str(raw.get("value")),
                }
            )
        return rows

    def _normalize_owner_office_rows(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for idx, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()
            if not label:
                continue
            key = str(raw.get("key") or "").strip() or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or f"row_{idx}"
            row_type = str(raw.get("type") or "field").strip().lower()
            if row_type not in {"category", "field"}:
                row_type = "field"
            normalized.append(
                {
                    "key": key[:80],
                    "label": label[:160],
                    "type": row_type,
                    "value": "" if raw.get("value") is None else str(raw.get("value")).strip()[:500],
                }
            )
        return normalized

    def _owner_performance_rows_from_json(self, value: Any) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        rows: List[Dict[str, Any]] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            season_year = parse_int(raw.get("season_year"))
            wins = parse_int(raw.get("wins"))
            losses = parse_int(raw.get("losses"))
            result = str(raw.get("result") or "").strip()[:80]
            if season_year is None:
                continue
            rows.append(
                {
                    "season_year": season_year,
                    "wins": "" if wins is None else wins,
                    "losses": "" if losses is None else losses,
                    "result": result,
                }
            )
        return rows

    def _normalize_owner_performance_rows(self, rows: Any, season_year: int) -> List[Dict[str, Any]]:
        raw_rows = rows if isinstance(rows, list) else []
        normalized: List[Dict[str, Any]] = []
        for idx in range(5):
            raw = raw_rows[idx] if idx < len(raw_rows) and isinstance(raw_rows[idx], dict) else {}
            fallback_year = int(season_year) - 4 + idx
            row_year = parse_int(raw.get("season_year")) or fallback_year
            wins = parse_int(raw.get("wins"))
            losses = parse_int(raw.get("losses"))
            result = str(raw.get("result") or "").strip()[:80]
            normalized.append(
                {
                    "season_year": max(2000, min(2100, row_year)),
                    "wins": "" if wins is None else max(0, min(100, wins)),
                    "losses": "" if losses is None else max(0, min(100, losses)),
                    "result": result,
                }
            )
        return normalized

    def _owner_attribute_value(self, value: Any) -> Optional[int]:
        parsed = parse_int(value)
        if parsed is None:
            return None
        return max(1, min(10, parsed))

    def _owner_profile_from_row(self, row: Optional[sqlite3.Row], include_private: bool = False) -> Dict[str, Any]:
        profile: Dict[str, Any] = {
            "owner_name": "",
            "owner_birth_date": "",
            "owner_photo_url": "",
            "owner_office_background_url": "",
            "owner_bio": "",
        }
        if row:
            profile.update(
                {
                    "owner_name": str(row["owner_name"] or ""),
                    "owner_birth_date": str(row["owner_birth_date"] or ""),
                    "owner_photo_url": str(row["owner_photo_url"] or ""),
                    "owner_office_background_url": str(row["owner_office_background_url"] or ""),
                    "owner_bio": str(row["owner_bio"] or ""),
                }
            )
        if include_private:
            profile["attributes"] = {
                "ambicion_competitiva": self._owner_attribute_value(row["ambicion_competitiva"]) if row else None,
                "paciencia": self._owner_attribute_value(row["paciencia"]) if row else None,
                "intervencionismo": self._owner_attribute_value(row["intervencionismo"]) if row else None,
                "orientacion_financiera": self._owner_attribute_value(row["orientacion_financiera"]) if row else None,
                "orientacion_marca": self._owner_attribute_value(row["orientacion_marca"]) if row else None,
            }
        return profile

    def _normalize_owner_profile_payload(self, payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None

        def text_value(key: str, limit: int) -> str:
            return str(payload.get(key) or "").strip()[:limit]

        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        return {
            "owner_name": text_value("owner_name", 120),
            "owner_birth_date": text_value("owner_birth_date", 32),
            "owner_photo_url": text_value("owner_photo_url", 1000),
            "owner_office_background_url": text_value("owner_office_background_url", 1000),
            "owner_bio": text_value("owner_bio", 2000),
            "ambicion_competitiva": self._owner_attribute_value(attributes.get("ambicion_competitiva")),
            "paciencia": self._owner_attribute_value(attributes.get("paciencia")),
            "intervencionismo": self._owner_attribute_value(attributes.get("intervencionismo")),
            "orientacion_financiera": self._owner_attribute_value(attributes.get("orientacion_financiera")),
            "orientacion_marca": self._owner_attribute_value(attributes.get("orientacion_marca")),
        }

    def _owner_exit_interview_from_row(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "team_id": int(row["team_id"]),
            "season_year": int(row["season_year"]),
            "gm_email": str(row["gm_email"] or ""),
            "gm_name": str(row["gm_name"] or ""),
            "status": str(row["status"] or "available"),
            "owner_message": str(row["owner_message"] or ""),
            "gm_response": str(row["gm_response"] or ""),
            "owner_final_message": str(row["owner_final_message"] or ""),
            "owner_conclusion_message": str(row["owner_conclusion_message"] or ""),
            "trust_delta": parse_int(row["trust_delta"]),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
        }

    def _owner_confidence_with_delta(self, value: Any, delta: int) -> Optional[str]:
        parsed = parse_float(str(value) if value is not None else None)
        if parsed is None:
            return None
        updated = parsed + int(delta)
        if float(updated).is_integer():
            return str(int(updated))
        return f"{updated:g}"

    def get_owner_exit_interview(self, code: str, season_year: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            row = conn.execute(
                """
                SELECT *
                FROM owner_exit_interviews
                WHERE team_id = ? AND season_year = ?
                """,
                (int(team["id"]), int(season_year)),
            ).fetchone()
            return self._owner_exit_interview_from_row(row)

    def start_owner_exit_interview(
        self,
        code: str,
        season_year: int,
        session: Dict[str, Any],
        owner_message: str,
    ) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            team_id = int(team["id"])
            existing = conn.execute(
                """
                SELECT *
                FROM owner_exit_interviews
                WHERE team_id = ? AND season_year = ?
                """,
                (team_id, int(season_year)),
            ).fetchone()
            if existing:
                return self._owner_exit_interview_from_row(existing)
            gm_user_id = parse_int(session.get("user_id"))
            conn.execute(
                """
                INSERT INTO owner_exit_interviews (
                    team_id,
                    season_year,
                    gm_user_id,
                    gm_email,
                    gm_name,
                    status,
                    owner_message,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'awaiting_gm', ?, ?, ?)
                """,
                (
                    team_id,
                    int(season_year),
                    gm_user_id,
                    str(session.get("email") or "").strip(),
                    str(session.get("name") or "").strip(),
                    str(owner_message or "").strip()[:4000],
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT *
                FROM owner_exit_interviews
                WHERE team_id = ? AND season_year = ?
                """,
                (team_id, int(season_year)),
            ).fetchone()
            return self._owner_exit_interview_from_row(row)

    def complete_owner_exit_interview(
        self,
        code: str,
        season_year: int,
        session: Dict[str, Any],
        gm_response: str,
        owner_final_message: str,
        owner_conclusion_message: str,
        trust_delta: int,
    ) -> Optional[Dict[str, Any]]:
        timestamp = now_iso()
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            team_id = int(team["id"])
            row = conn.execute(
                """
                SELECT *
                FROM owner_exit_interviews
                WHERE team_id = ? AND season_year = ?
                """,
                (team_id, int(season_year)),
            ).fetchone()
            if not row:
                return None
            if str(row["status"] or "").lower() == "completed":
                return self._owner_exit_interview_from_row(row)
            gm_user_id = parse_int(session.get("user_id"))
            normalized_delta = max(-1, min(1, int(trust_delta)))
            conn.execute(
                """
                UPDATE owner_exit_interviews
                SET
                    gm_user_id = COALESCE(?, gm_user_id),
                    gm_email = ?,
                    gm_name = ?,
                    status = 'completed',
                    gm_response = ?,
                    owner_final_message = ?,
                    owner_conclusion_message = ?,
                    trust_delta = ?,
                    updated_at = ?,
                    completed_at = ?
                WHERE team_id = ? AND season_year = ?
                """,
                (
                    gm_user_id,
                    str(session.get("email") or "").strip(),
                    str(session.get("name") or "").strip(),
                    str(gm_response or "").strip()[:4000],
                    str(owner_final_message or "").strip()[:4000],
                    str(owner_conclusion_message or "").strip()[:4000],
                    normalized_delta,
                    timestamp,
                    timestamp,
                    team_id,
                    int(season_year),
                ),
            )
            office_row = conn.execute(
                """
                SELECT confidence_current
                FROM team_owner_office
                WHERE team_id = ? AND season_year = ?
                """,
                (team_id, int(season_year)),
            ).fetchone()
            updated_confidence = self._owner_confidence_with_delta(
                office_row["confidence_current"] if office_row else None,
                normalized_delta,
            )
            if updated_confidence is not None:
                conn.execute(
                    """
                    UPDATE team_owner_office
                    SET confidence_current = ?, updated_at = ?
                    WHERE team_id = ? AND season_year = ?
                    """,
                    (updated_confidence, timestamp, team_id, int(season_year)),
                )
            conn.commit()
            updated = conn.execute(
                """
                SELECT *
                FROM owner_exit_interviews
                WHERE team_id = ? AND season_year = ?
                """,
                (team_id, int(season_year)),
            ).fetchone()
            return self._owner_exit_interview_from_row(updated)

    def reset_owner_exit_interview(self, code: str, season_year: int) -> bool:
        timestamp = now_iso()
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return False
            team_id = int(team["id"])
            row = conn.execute(
                """
                SELECT status, trust_delta
                FROM owner_exit_interviews
                WHERE team_id = ? AND season_year = ?
                """,
                (team_id, int(season_year)),
            ).fetchone()
            if row:
                status = str(row["status"] or "").lower()
                trust_delta = parse_int(row["trust_delta"])
                if status == "completed" and trust_delta:
                    office_row = conn.execute(
                        """
                        SELECT confidence_current
                        FROM team_owner_office
                        WHERE team_id = ? AND season_year = ?
                        """,
                        (team_id, int(season_year)),
                    ).fetchone()
                    reverted_confidence = self._owner_confidence_with_delta(
                        office_row["confidence_current"] if office_row else None,
                        -trust_delta,
                    )
                    if reverted_confidence is not None:
                        conn.execute(
                            """
                            UPDATE team_owner_office
                            SET confidence_current = ?, updated_at = ?
                            WHERE team_id = ? AND season_year = ?
                            """,
                            (reverted_confidence, timestamp, team_id, int(season_year)),
                        )
                conn.execute(
                    "DELETE FROM owner_exit_interviews WHERE team_id = ? AND season_year = ?",
                    (team_id, int(season_year)),
                )
                conn.commit()
            return True

    def get_team_owner_office(self, code: str, include_private: bool = False) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            team = conn.execute("SELECT id, code, name FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if current_year < CAP_FORECAST_MIN_YEAR or current_year > CAP_FORECAST_MAX_YEAR:
                current_year = 2025
            free_agency_mode = parse_bool(settings.get("free_agency_mode"))
            team_id = int(team["id"])
            profile_row = conn.execute(
                """
                SELECT *
                FROM team_owner_profiles
                WHERE team_id = ?
                """,
                (team_id,),
            ).fetchone()
            saved_rows = conn.execute(
                """
                SELECT *
                FROM team_owner_office
                WHERE team_id = ?
                ORDER BY season_year
                """,
                (team_id,),
            ).fetchall()
            interview_rows = conn.execute(
                """
                SELECT *
                FROM owner_exit_interviews
                WHERE team_id = ?
                """,
                (team_id,),
            ).fetchall()
            years = {
                *range(current_year, current_year + CAP_FORECAST_WINDOW),
                *[int(row["season_year"]) for row in saved_rows],
                *[int(row["season_year"]) for row in interview_rows],
                *[
                    int(row["season_year"])
                    for row in conn.execute("SELECT DISTINCT season_year FROM team_economy").fetchall()
                ],
            }
            saved_by_year = {int(row["season_year"]): row for row in saved_rows}
            interviews_by_year = {
                int(row["season_year"]): self._owner_exit_interview_from_row(row)
                for row in interview_rows
            }
            entries: Dict[str, Dict[str, Any]] = {}
            for year in sorted(years):
                economy = conn.execute(
                    """
                    SELECT COALESCE(balance, 0) AS balance,
                           COALESCE(revenue, 0) AS revenue,
                           COALESCE(expenses, 0) AS expenses
                    FROM team_economy
                    WHERE team_id = ? AND season_year = ?
                    """,
                    (team_id, int(year)),
                ).fetchone()
                economy_balance = float(economy["balance"] or 0) if economy else 0.0
                economy_revenue = float(economy["revenue"] or 0) if economy else 0.0
                economy_expenses = float(economy["expenses"] or 0) if economy else 0.0
                rank_rows = conn.execute(
                    """
                    SELECT t.id, COALESCE(e.balance, 0) AS balance
                    FROM teams t
                    LEFT JOIN team_economy e
                      ON e.team_id = t.id AND e.season_year = ?
                    ORDER BY COALESCE(e.balance, 0) DESC, t.code ASC
                    """,
                    (int(year),),
                ).fetchall()
                balance_rank = next((idx + 1 for idx, row in enumerate(rank_rows) if int(row["id"]) == team_id), None)
                saved = saved_by_year.get(int(year))
                interview = interviews_by_year.get(int(year))
                if not interview and free_agency_mode and int(year) == current_year:
                    interview = {
                        "season_year": int(year),
                        "status": "available",
                        "owner_message": "",
                        "gm_response": "",
                        "owner_final_message": "",
                        "owner_conclusion_message": "",
                        "trust_delta": None,
                    }
                entries[str(year)] = {
                    "season_year": int(year),
                    "confidence_current": str(saved["confidence_current"] or "") if saved else "",
                    "confidence_change": str(saved["confidence_change"] or "") if saved else "",
                    "revenue": str(saved["revenue"]) if saved and saved["revenue"] is not None else economy_revenue,
                    "expenses": str(saved["expenses"]) if saved and saved["expenses"] is not None else economy_expenses,
                    "balance": str(saved["balance"]) if saved and saved["balance"] is not None else economy_balance,
                    "balance_rank": balance_rank,
                    "balance_rank_total": len(rank_rows),
                    "income_rows": self._owner_office_rows_from_json(saved["income_json"]) if saved else [],
                    "expenses_rows": self._owner_office_rows_from_json(saved["expenses_json"]) if saved else [],
                    "performance_rows": self._owner_performance_rows_from_json(saved["performance_json"]) if saved else self._normalize_owner_performance_rows([], int(year)),
                    "exit_interview": interview,
                    "updated_at": str(saved["updated_at"] or "") if saved else "",
                }
            return {
                "team_code": str(team["code"]),
                "team_name": str(team["name"]),
                "current_year": current_year,
                "free_agency_mode": free_agency_mode,
                "exit_interview_season": current_year,
                "owner_profile": self._owner_profile_from_row(profile_row, include_private=include_private),
                "seasons": sorted(years),
                "entries": entries,
            }

    def update_team_owner_office(self, code: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        season_year = parse_int(payload.get("season_year"))
        if season_year is None or season_year < 2000 or season_year > 2100:
            raise ValueError("invalid_season_year")
        with self.connect() as conn:
            team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
            if not team:
                return None
            timestamp = now_iso()
            profile_payload = self._normalize_owner_profile_payload(payload.get("owner_profile"))
            if profile_payload is not None:
                conn.execute(
                    """
                    INSERT INTO team_owner_profiles (
                        team_id,
                        owner_name,
                        owner_birth_date,
                        owner_photo_url,
                        owner_office_background_url,
                        owner_bio,
                        ambicion_competitiva,
                        paciencia,
                        intervencionismo,
                        orientacion_financiera,
                        orientacion_marca,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_id) DO UPDATE SET
                        owner_name = excluded.owner_name,
                        owner_birth_date = excluded.owner_birth_date,
                        owner_photo_url = excluded.owner_photo_url,
                        owner_office_background_url = excluded.owner_office_background_url,
                        owner_bio = excluded.owner_bio,
                        ambicion_competitiva = excluded.ambicion_competitiva,
                        paciencia = excluded.paciencia,
                        intervencionismo = excluded.intervencionismo,
                        orientacion_financiera = excluded.orientacion_financiera,
                        orientacion_marca = excluded.orientacion_marca,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(team["id"]),
                        profile_payload["owner_name"],
                        profile_payload["owner_birth_date"],
                        profile_payload["owner_photo_url"],
                        profile_payload["owner_office_background_url"],
                        profile_payload["owner_bio"],
                        profile_payload["ambicion_competitiva"],
                        profile_payload["paciencia"],
                        profile_payload["intervencionismo"],
                        profile_payload["orientacion_financiera"],
                        profile_payload["orientacion_marca"],
                        timestamp,
                    ),
                )
            conn.execute(
                """
                INSERT INTO team_owner_office (
                    team_id,
                    season_year,
                    confidence_current,
                    confidence_change,
                    revenue,
                    expenses,
                    balance,
                    income_json,
                    expenses_json,
                    performance_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id, season_year) DO UPDATE SET
                    confidence_current = excluded.confidence_current,
                    confidence_change = excluded.confidence_change,
                    revenue = excluded.revenue,
                    expenses = excluded.expenses,
                    balance = excluded.balance,
                    income_json = excluded.income_json,
                    expenses_json = excluded.expenses_json,
                    performance_json = excluded.performance_json,
                    updated_at = excluded.updated_at
                """,
                (
                    int(team["id"]),
                    int(season_year),
                    str(payload.get("confidence_current") or "").strip(),
                    str(payload.get("confidence_change") or "").strip(),
                    str(payload.get("revenue") or "").strip(),
                    str(payload.get("expenses") or "").strip(),
                    str(payload.get("balance") or "").strip(),
                    json.dumps(self._normalize_owner_office_rows(payload.get("income_rows")), ensure_ascii=True),
                    json.dumps(self._normalize_owner_office_rows(payload.get("expenses_rows")), ensure_ascii=True),
                    json.dumps(
                        self._normalize_owner_performance_rows(payload.get("performance_rows"), int(season_year)),
                        ensure_ascii=True,
                    ),
                    timestamp,
                ),
            )
            conn.commit()
        return self.get_team_owner_office(code, include_private=True)

    def upsert_team_economy(self, season_year: int, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if season_year < 2000 or season_year > 2100:
            raise ValueError("invalid_season_year")
        timestamp = now_iso()
        with self.connect() as conn:
            team_rows = conn.execute("SELECT id, code FROM teams").fetchall()
            team_ids = {str(row["code"]).upper(): int(row["id"]) for row in team_rows}
            for row in rows:
                code = str(row.get("team_code") or row.get("code") or "").strip().upper()
                if code not in team_ids:
                    raise ValueError(f"invalid_team_code:{code}")
                balance = parse_amount_like(row.get("balance"))
                revenue = parse_amount_like(row.get("revenue"))
                expenses = parse_amount_like(row.get("expenses"))
                conn.execute(
                    """
                    INSERT INTO team_economy (
                        team_id, season_year, balance, revenue, expenses, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_id, season_year) DO UPDATE SET
                        balance = excluded.balance,
                        revenue = excluded.revenue,
                        expenses = excluded.expenses,
                        updated_at = excluded.updated_at
                    """,
                    (
                        team_ids[code],
                        season_year,
                        float(balance or 0),
                        float(revenue or 0),
                        float(expenses or 0),
                        timestamp,
                    ),
                )
            conn.commit()
        return self.list_team_economy(season_year)

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

    def _team_luxury_repeater_for_season(self, conn: sqlite3.Connection, team_id: int, season_year: int) -> bool:
        row = conn.execute(
            """
            SELECT repeater
            FROM team_luxury_history
            WHERE team_id = ? AND season_year = ?
            """,
            (team_id, season_year),
        ).fetchone()
        return bool(row["repeater"]) if row else False

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
        roster_standard_count = sum(
            1
            for p in players
            if not p.get("is_two_way") and str(p.get("bird_rights") or "").strip().upper() != "TW"
        )
        roster_two_way_count = len(players) - roster_standard_count

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
            "roster_standard_count": roster_standard_count,
            "roster_two_way_count": roster_two_way_count,
            "apron_hard_cap": normalize_apron_hard_cap(team.get("apron_hard_cap")) or "",
        }

    def update_player(self, player_id: int, payload: Dict[str, Any]) -> bool:
        fields = [
            "name", "bird_rights", "rating", "position", "years_left",
            "salary_2025_text", "salary_2026_text", "salary_2027_text",
            "salary_2028_text", "salary_2029_text", "salary_2030_text",
            "salary_2025_guaranteed_text", "salary_2026_guaranteed_text", "salary_2027_guaranteed_text",
            "salary_2028_guaranteed_text", "salary_2029_guaranteed_text", "salary_2030_guaranteed_text",
            "salary_2025_note_text", "salary_2026_note_text", "salary_2027_note_text",
            "salary_2028_note_text", "salary_2029_note_text", "salary_2030_note_text",
            "option_2025", "option_2026", "option_2027", "option_2028", "option_2029", "option_2030",
            "notes", "reference_image_url",
        ]
        bool_fields = [
            "provisional_amounts", "partially_guaranteed", "contract_notes",
            "salary_2025_provisional", "salary_2026_provisional", "salary_2027_provisional",
            "salary_2028_provisional", "salary_2029_provisional", "salary_2030_provisional",
            "salary_2025_partially_guaranteed", "salary_2026_partially_guaranteed", "salary_2027_partially_guaranteed",
            "salary_2028_partially_guaranteed", "salary_2029_partially_guaranteed", "salary_2030_partially_guaranteed",
            "salary_2025_note", "salary_2026_note", "salary_2027_note",
            "salary_2028_note", "salary_2029_note", "salary_2030_note",
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
                "reference_image_url": payload.get("reference_image_url"),
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
                    notes, reference_image_url, is_two_way, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    values["reference_image_url"],
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
                SELECT p.*, t.code AS team_code, t.name AS team_name
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
                "team_name": player.get("team_name"),
                "player_name": player.get("name"),
                "reference_image_url": player.get("reference_image_url"),
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
    gm_accounts = parse_gm_account_map(
        os.getenv("GM_ACCOUNTS")
        or os.getenv("GM_EMAILS")
        or os.getenv("GM_EMAIL_MAP")
        or ""
    )
    session_ttl_seconds = max(300, parse_int(os.getenv("SESSION_TTL_SECONDS")) or 28800)
    cookie_secure = str(os.getenv("COOKIE_SECURE", "false")).strip().lower() in {"1", "true", "yes", "on"}
    cookie_same_site = str(os.getenv("COOKIE_SAMESITE", "Lax")).strip() or "Lax"
    cookie_domain = str(os.getenv("COOKIE_DOMAIN", "")).strip() or None

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    discord_role_id = os.getenv("DISCORD_NOTIFY_ROLE_ID", "486604867293544458").strip()
    discord_notifications_enabled = str(os.getenv("DISCORD_NOTIFICATIONS_ENABLED", "true")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    discord_timeout_seconds = max(1, parse_int(os.getenv("DISCORD_WEBHOOK_TIMEOUT_SECONDS")) or 5)
    discord_image_notifications_enabled = str(
        os.getenv("DISCORD_IMAGE_NOTIFICATIONS_ENABLED", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    openai_text_timeout_seconds = max(10, parse_int(os.getenv("OPENAI_TEXT_TIMEOUT_SECONDS")) or 45)
    openai_image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip() or "gpt-image-2"
    openai_image_size = os.getenv("OPENAI_IMAGE_SIZE", "1536x1024").strip() or "1536x1024"
    openai_image_quality = os.getenv("OPENAI_IMAGE_QUALITY", "high").strip() or "high"
    openai_image_format = os.getenv("OPENAI_IMAGE_FORMAT", "jpeg").strip().lower() or "jpeg"
    openai_image_timeout_seconds = max(10, parse_int(os.getenv("OPENAI_IMAGE_TIMEOUT_SECONDS")) or 120)
    openai_reference_image_timeout_seconds = max(
        5,
        parse_int(os.getenv("OPENAI_REFERENCE_IMAGE_TIMEOUT_SECONDS")) or 20,
    )
    openai_reference_image_max_bytes = max(
        250_000,
        parse_int(os.getenv("OPENAI_REFERENCE_IMAGE_MAX_BYTES")) or 6_000_000,
    )

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
        sess = self.db.get_session(token)
        if sess and sess.get("provider") == "google":
            role, team_codes = self._google_role_for_email(str(sess.get("email") or ""))
            sess["role"] = role
            sess["team_codes"] = team_codes
            sess["team_code"] = team_codes[0] if team_codes else None
        return sess

    def _is_authenticated(self) -> bool:
        return self._current_session() is not None

    def _is_admin(self) -> bool:
        sess = self._current_session()
        return bool(sess and sess.get("role") == "admin")

    def _is_gm(self) -> bool:
        sess = self._current_session()
        return bool(sess and sess.get("role") == "gm")

    def _current_session_team_codes(self) -> List[str]:
        sess = self._current_session() or {}
        raw_codes = sess.get("team_codes")
        if isinstance(raw_codes, list):
            return [str(code).strip().upper() for code in raw_codes if str(code or "").strip()]
        return []

    def _can_manage_team(self, team_code: Any) -> bool:
        if self._is_admin():
            return True
        normalized = normalize_team_code(team_code)
        return bool(normalized and normalized in self._current_session_team_codes())

    def _require_admin(self) -> bool:
        if self._is_admin():
            return True
        self._json(401, {"error": "admin_auth_required"})
        return False

    def _require_authenticated(self) -> bool:
        if self._is_authenticated():
            return True
        self._json(401, {"error": "auth_required"})
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

    def _google_role_for_email(self, email: str) -> tuple[str, List[str]]:
        normalized = str(email or "").strip().lower()
        if normalized in self.admin_emails:
            return "admin", []
        db_team_codes = self.db.get_user_team_codes_by_email(normalized)
        if db_team_codes:
            return "gm", db_team_codes
        team_codes = self.gm_accounts.get(normalized, [])
        if team_codes:
            return "gm", team_codes
        return "guest", []

    def _landing_path_for_session(self, role: Any, team_codes: Optional[List[str]] = None) -> str:
        if role == "admin":
            return "/admin"
        if role == "gm":
            team_code = (team_codes or [None])[0]
            if team_code:
                return f"/?team={team_code}"
        return "/"

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

    def _discord_text(self, value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[: max(0, limit - 3)].rstrip()}..."

    def _image_mime_type(self) -> tuple[str, str]:
        image_format = self.openai_image_format.lower()
        if image_format == "webp":
            return "webp", "image/webp"
        if image_format in {"jpg", "jpeg"}:
            return "jpeg", "image/jpeg"
        return "png", "image/png"

    def _team_image_colors(self, team_code: str) -> str:
        return TEAM_IMAGE_COLORS.get(str(team_code or "").upper(), "#0F766E, #111827")

    def _reference_image_mime_type(self, content_type: str, url_path: str) -> tuple[str, str]:
        mime = (content_type or "").split(";", 1)[0].strip().lower()
        if mime in {"image/jpeg", "image/jpg"}:
            return "jpg", "image/jpeg"
        if mime == "image/png":
            return "png", "image/png"
        if mime == "image/webp":
            return "webp", "image/webp"
        path = url_path.lower()
        if path.endswith((".jpg", ".jpeg")):
            return "jpg", "image/jpeg"
        if path.endswith(".webp"):
            return "webp", "image/webp"
        return "png", "image/png"

    def _openai_image_from_response(self, response: Dict[str, Any]) -> Optional[tuple[bytes, str, str]]:
        image_ext, mime_type = self._image_mime_type()
        items = response.get("data") if isinstance(response, dict) else None
        first = items[0] if isinstance(items, list) and items else {}
        if first.get("b64_json"):
            image_bytes = base64.b64decode(str(first["b64_json"]))
        elif first.get("url"):
            with urlopen(str(first["url"]), timeout=self.openai_image_timeout_seconds) as image_resp:
                image_bytes = image_resp.read()
        else:
            return None
        return image_bytes, f"anba-news.{image_ext}", mime_type

    def _http_error_excerpt(self, err: HTTPError, limit: int = 1200) -> str:
        try:
            body = err.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        if len(body) > limit:
            body = f"{body[:limit].rstrip()}..."
        return f"{err} {body}".strip()

    def _fetch_reference_image(self, image_url: str) -> Optional[tuple[bytes, str, str]]:
        image_url = str(image_url or "").strip()
        if not image_url:
            return None
        parsed = urlparse(image_url)
        if parsed.scheme not in {"http", "https"}:
            self.log_error("OpenAI reference image skipped: unsupported URL scheme")
            return None
        req = Request(
            image_url,
            headers={"User-Agent": "anba-excel/1.0"},
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.openai_reference_image_timeout_seconds) as resp:
                content_type = str(resp.headers.get("Content-Type") or "")
                image_bytes = resp.read(self.openai_reference_image_max_bytes + 1)
            if len(image_bytes) > self.openai_reference_image_max_bytes:
                self.log_error("OpenAI reference image skipped: file exceeds configured max size")
                return None
            image_ext, mime_type = self._reference_image_mime_type(content_type, parsed.path)
            if not mime_type.startswith("image/"):
                self.log_error("OpenAI reference image skipped: URL did not return an image")
                return None
            return image_bytes, f"reference.{image_ext}", mime_type
        except HTTPError as err:
            self.log_error("OpenAI reference image fetch failed: %s", self._http_error_excerpt(err))
        except (URLError, TimeoutError, OSError, ValueError) as err:
            self.log_error("OpenAI reference image fetch failed: %s", err)
        return None

    def _news_image_prompt(
        self,
        headline: str,
        description: str,
        *,
        teams: Optional[List[str]] = None,
        players: Optional[List[str]] = None,
        context: Optional[str] = None,
        team_name: Optional[str] = None,
        team_code: Optional[str] = None,
        player_name: Optional[str] = None,
        secondary_headline: Optional[str] = None,
        additional_details: Optional[str] = None,
        transaction_type: Optional[str] = None,
        use_player_reference: bool = False,
    ) -> str:
        if use_player_reference:
            resolved_team_code = str(team_code or (teams or [""])[0] or "").upper()
            resolved_team_name = str(team_name or resolved_team_code or "ANBA").strip()
            resolved_player_name = str(player_name or (players or [""])[0] or "Jugador").strip()
            return f"""Create a professional NBA social media breaking news graphic using the uploaded player image as the primary reference.

IMPORTANT PLAYER REFERENCE INSTRUCTIONS

- Use the uploaded photo as the source reference.
- Preserve the player's facial features, hair, skin tone, expression, body proportions, and overall likeness accurately.
- The player must remain clearly recognizable as the same person from the reference image.
- Do not alter age, ethnicity, facial structure, hairstyle, or physical characteristics.
- Remove the original team uniform and replace it with an authentic, realistic {resolved_team_name} uniform.
- Jersey colors, typography, trim, logos, and styling should accurately reflect the team's current branding.
- Maintain realistic jersey fabric, lighting, wrinkles, and athletic appearance.
- The player should appear as if photographed professionally while playing for {resolved_team_name}.

DESIGN OBJECTIVE

Create a premium NBA transaction announcement graphic suitable for major basketball news accounts on Twitter/X, Instagram, Threads, and sports media websites.

VISUAL STYLE

- Professional NBA media graphic
- Bleacher Report quality
- ESPN social media quality
- House of Highlights quality
- Courtside Buzz style presentation
- Modern sports marketing creative
- Premium Photoshop compositing
- Editorial sports poster
- High-end sports journalism graphic
- Viral social media design
- Clean information hierarchy
- Photorealistic athlete rendering
- Ultra-sharp details
- Dynamic contrast
- Dramatic lighting
- Premium typography

LAYOUT

- Landscape format (16:9)
- Player positioned on the right side occupying approximately 50-60% of the composition
- Large headline typography on the left side
- Team logo integrated into the background at low opacity
- Team branding incorporated throughout the design
- Strong focal point on the player
- Clean visual hierarchy optimized for mobile viewing
- Professional spacing and alignment

BACKGROUND

- Dark textured sports background
- Arena atmosphere
- Subtle smoke and lighting effects
- Team color gradients
- Depth and cinematic lighting
- Modern sports poster aesthetic

TEAM BRANDING

Team:
{resolved_team_name}

Primary Colors:
{self._team_image_colors(resolved_team_code)}

Use the team's visual identity consistently throughout:
- Color palette
- Logo integration
- Background treatments
- Typography accents
- Graphic elements

HEADLINE TEXT

NBA NEWS

{resolved_team_name}

{headline}

SUBHEADLINE

{secondary_headline or description}

PLAYER NAME

{resolved_player_name}

OPTIONAL DETAILS

{additional_details or context or ""}

TRANSACTION CONTEXT

Transaction Type:
{transaction_type or "Transaction"}

Examples:
- Trade
- Signing
- Re-signing
- Contract Extension
- Waived
- Released
- Team Option Exercised
- Team Option Declined
- Qualifying Offer Rejected
- Two-Way Signing
- Conversion to Standard Contract
- Buyout
- Draft Rights Acquired
- Contract Guaranteed
- Contract Non-Guaranteed
- Free Agency Signing

QUALITY REQUIREMENTS

- Photorealistic
- Sports media publication quality
- Crisp typography
- Authentic NBA branding aesthetic
- Realistic jersey replacement
- No distorted anatomy
- No cartoon appearance
- No AI-art look
- Premium Photoshop-style finish
- Suitable for posting directly by an NBA news account
- Highly shareable social media design"""

        team_text = ", ".join(str(t).upper() for t in teams or [] if str(t or "").strip()) or "ANBA"
        player_text = ", ".join(str(p) for p in players or [] if str(p or "").strip())
        parts = [
            "Create a landscape professional basketball news graphic for a Discord/social post.",
            "Use an editorial transaction-news style with dramatic arena lighting, premium sports typography, and team-color accents.",
            f"Main headline text exactly: {headline}",
            f"Post context: {description}",
            f"Relevant team(s): {team_text}.",
            "Avoid official league marks, sponsor logos, watermarks, and unrelated extra text.",
            "Do not include a fake scoreboard or stat table. Leave enough clean space around the headline for mobile readability.",
        ]
        if player_text:
            parts.append(
                f"Relevant player name(s): {player_text}. If showing a player, use a generic basketball player in team-inspired colors."
            )
        if context:
            parts.append(f"Additional context: {context}")
        return "\n".join(parts)

    def _openai_multipart_body(
        self,
        fields: Dict[str, Any],
        files: List[tuple[str, str, str, bytes]],
    ) -> tuple[bytes, str]:
        boundary = f"----anba-openai-{secrets.token_hex(16)}"
        chunks: List[bytes] = []
        for name, value in fields.items():
            if value in (None, ""):
                continue
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for field_name, filename, mime_type, file_bytes in files:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"),
                    f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
                    file_bytes,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(chunks), boundary

    def _generate_openai_image_from_reference(
        self,
        prompt: str,
        reference_image: tuple[bytes, str, str],
    ) -> Optional[tuple[bytes, str, str]]:
        ref_bytes, ref_filename, ref_mime = reference_image
        image_ext, _ = self._image_mime_type()
        body, boundary = self._openai_multipart_body(
            {
                "model": self.openai_image_model,
                "prompt": self._discord_text(prompt, 4000),
                "size": self.openai_image_size,
                "quality": self.openai_image_quality,
                "n": 1,
                "output_format": image_ext,
            },
            [("image[]", ref_filename, ref_mime, ref_bytes)],
        )
        req = Request(
            "https://api.openai.com/v1/images/edits",
            data=body,
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "anba-excel/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.openai_image_timeout_seconds) as resp:
                response = json.loads(resp.read().decode("utf-8"))
            return self._openai_image_from_response(response)
        except HTTPError as err:
            self.log_error("OpenAI reference image generation failed: %s", self._http_error_excerpt(err))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as err:
            self.log_error("OpenAI reference image generation failed: %s", err)
        return None

    def _generate_openai_image_from_prompt(self, prompt: str) -> Optional[tuple[bytes, str, str]]:
        if not prompt.strip() or not self.discord_image_notifications_enabled or not self.openai_api_key:
            return None

        image_ext, mime_type = self._image_mime_type()
        request_payload: Dict[str, Any] = {
            "model": self.openai_image_model,
            "prompt": self._discord_text(prompt, 4000),
            "size": self.openai_image_size,
            "quality": self.openai_image_quality,
            "n": 1,
        }
        if image_ext in {"jpeg", "png", "webp"}:
            request_payload["output_format"] = image_ext

        req = Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "anba-excel/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.openai_image_timeout_seconds) as resp:
                response = json.loads(resp.read().decode("utf-8"))
            return self._openai_image_from_response(response)
        except HTTPError as err:
            self.log_error("OpenAI image generation failed: %s", self._http_error_excerpt(err))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as err:
            self.log_error("OpenAI image generation failed: %s", err)
        return None

    def _generate_openai_image(
        self,
        prompt: str,
        *,
        reference_image_url: Optional[str] = None,
        fallback_prompt: Optional[str] = None,
    ) -> Optional[tuple[bytes, str, str]]:
        if not prompt.strip() or not self.discord_image_notifications_enabled or not self.openai_api_key:
            return None

        if reference_image_url:
            reference_image = self._fetch_reference_image(reference_image_url)
            if reference_image:
                generated = self._generate_openai_image_from_reference(prompt, reference_image)
                if generated:
                    return generated

        return self._generate_openai_image_from_prompt(fallback_prompt or prompt)

    def _openai_text_response(self, system_prompt: str, user_prompt: str, max_output_tokens: int = 700) -> Optional[str]:
        if not self.openai_api_key:
            return None
        request_payload: Dict[str, Any] = {
            "model": self.openai_text_model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": max(100, min(2000, int(max_output_tokens))),
        }
        req = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "anba-excel/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.openai_text_timeout_seconds) as resp:
                response = json.loads(resp.read().decode("utf-8"))
            direct = str(response.get("output_text") or "").strip() if isinstance(response, dict) else ""
            if direct:
                return direct
            for item in response.get("output", []) if isinstance(response, dict) else []:
                if not isinstance(item, dict):
                    continue
                for content in item.get("content", []) or []:
                    if not isinstance(content, dict):
                        continue
                    text = str(content.get("text") or "").strip()
                    if text:
                        return text
            return None
        except HTTPError as err:
            self.log_error("OpenAI owner interview text generation failed: %s", self._http_error_excerpt(err))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as err:
            self.log_error("OpenAI owner interview text generation failed: %s", err)
        return None

    def _owner_interview_entry(self, owner_office: Dict[str, Any], season_year: int) -> Dict[str, Any]:
        entries = owner_office.get("entries") if isinstance(owner_office.get("entries"), dict) else {}
        return entries.get(str(season_year), {}) if isinstance(entries, dict) else {}

    def _owner_interview_context_text(
        self,
        owner_office: Dict[str, Any],
        season_year: int,
        session: Optional[Dict[str, Any]] = None,
    ) -> str:
        profile = owner_office.get("owner_profile") if isinstance(owner_office.get("owner_profile"), dict) else {}
        attrs = profile.get("attributes") if isinstance(profile.get("attributes"), dict) else {}
        entry = self._owner_interview_entry(owner_office, season_year)
        performance_rows = entry.get("performance_rows") if isinstance(entry.get("performance_rows"), list) else []
        session = session if isinstance(session, dict) else {}
        gm_name = str(session.get("name") or "").strip()
        gm_email = str(session.get("email") or "").strip()
        gm_reference = gm_name or gm_email or "GM"
        perf_lines = []
        for row in performance_rows:
            if not isinstance(row, dict):
                continue
            perf_lines.append(
                f"{season_label(row.get('season_year'))}: "
                f"{row.get('wins') or '-'}-{row.get('losses') or '-'}, "
                f"{row.get('result') or 'sin resultado'}"
            )
        return "\n".join(
            [
                f"Equipo: {owner_office.get('team_code') or ''} - {owner_office.get('team_name') or ''}",
                f"Temporada revisada: {season_label(season_year)}",
                f"Propietario: {profile.get('owner_name') or 'Propietario'}",
                f"Biografia propietario: {profile.get('owner_bio') or 'No configurada'}",
                f"GM evaluado: {gm_reference}",
                "Regla de voz: el propietario habla en primera persona; el nombre del propietario NO es el nombre del GM y no debe usarse como destinatario.",
                f"Atributos internos propietario: {json.dumps(attrs, ensure_ascii=False)}",
                f"Confianza actual: {entry.get('confidence_current') or 'No configurada'}",
                f"Cambio confianza temporada: {entry.get('confidence_change') or 'No configurado'}",
                f"Ingresos: {entry.get('revenue') or 'No configurado'}",
                f"Gastos: {entry.get('expenses') or 'No configurado'}",
                f"Balance: {entry.get('balance') or 'No configurado'}",
                f"Ranking balance: #{entry.get('balance_rank') or '-'} de {entry.get('balance_rank_total') or '-'}",
                "Ultimos cinco anos:",
                "\n".join(perf_lines) or "No configurado",
            ]
        )

    def _owner_interview_opening_message(
        self,
        owner_office: Dict[str, Any],
        season_year: int,
        session: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = self._owner_interview_context_text(owner_office, season_year, session=session)
        system_prompt = (
            "Eres el propietario de una franquicia de la liga ANBA. "
            "Escribe en espanol, con tono conversacional de despacho, directo y creible. "
            "Habla siempre en primera persona como propietario y dirigete al GM evaluado, nunca al propietario. "
            "No uses el nombre del propietario como si fuera el nombre del GM. No inventes datos fuera del contexto. "
            "Deja una pista clara de por que la confianza del propietario ha subido o bajado durante la temporada, "
            "usando el cambio de confianza del contexto si esta configurado. "
            "Haz una sola intervencion inicial de 2 a 4 frases, cerrando con una pregunta concreta al GM "
            "sobre su evaluacion de la temporada."
        )
        user_prompt = f"Contexto para la entrevista de salida:\n{context}"
        generated = self._openai_text_response(system_prompt, user_prompt, max_output_tokens=450)
        if generated:
            return generated[:2000]
        team = owner_office.get("team_code") or "el equipo"
        return (
            f"Terminada la temporada {season_label(season_year)}, quiero entender tu lectura de lo que ha pasado con {team}. "
            "Los resultados, la confianza y la situacion economica han movido mi evaluacion del proyecto, y quiero saber si lees igual ese cambio. "
            "Dime con claridad que ha funcionado, que no, y cual es tu plan para corregirlo."
        )

    def _owner_interview_parse_final(self, raw_text: Optional[str], gm_response: str) -> tuple[str, str, int]:
        text = str(raw_text or "").strip()
        parsed: Dict[str, Any] = {}
        if text:
            cleaned = re.sub(r"^```(?:json)?|```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            candidate = match.group(0) if match else cleaned
            try:
                loaded = json.loads(candidate)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = {}
        message = str(parsed.get("message") or parsed.get("owner_reply") or text or "").strip()
        conclusion = str(
            parsed.get("conclusion")
            or parsed.get("owner_conclusion")
            or parsed.get("next_year_message")
            or ""
        ).strip()
        trust_delta = parse_int(parsed.get("trust_delta"))
        if trust_delta is None or trust_delta == 0:
            trust_delta = 1 if len(str(gm_response or "").strip()) >= 80 else -1
        trust_delta = 1 if trust_delta > 0 else -1
        if not message:
            if trust_delta > 0:
                message = "Tu respuesta me da confianza. Veo un plan claro y una lectura responsable de la temporada. Sumaremos un punto de confianza y espero que lo conviertas en decisiones concretas."
            else:
                message = "No termino de ver suficiente claridad en tu respuesta. Necesitaba un diagnostico mas preciso y un plan mas convincente. Restaremos un punto de confianza y tendremos que ver mejoras pronto."
        if not conclusion:
            if trust_delta > 0:
                conclusion = "De cara al proximo ano quiero que conviertas esta lectura en prioridades concretas desde el primer dia. Despues del verano nos sentaremos para fijar objetivos especificos y medir si el proyecto avanza en la direccion correcta."
            else:
                conclusion = "De cara al proximo ano el margen de error sera menor. Despues del verano nos sentaremos para fijar objetivos especificos, pero necesito ver un plan mas claro y decisiones que recuperen mi confianza."
        return message[:2000], conclusion[:2000], trust_delta

    def _owner_interview_final_reply(
        self,
        owner_office: Dict[str, Any],
        season_year: int,
        owner_message: str,
        gm_response: str,
        session: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str, int]:
        context = self._owner_interview_context_text(owner_office, season_year, session=session)
        system_prompt = (
            "Eres el propietario de una franquicia de la liga ANBA. "
            "Evalua la respuesta del GM en espanol. Debes responder SOLO JSON valido con estas claves: "
            "\"message\", \"conclusion\" y \"trust_delta\". trust_delta debe ser exactamente 1 o -1. "
            "message debe ser una respuesta corta, de 1 a 2 frases, profesional y directa, que conteste al punto principal del GM "
            "y comunique claramente si la confianza sube o baja. "
            "conclusion debe ser un cierre separado, de 2 a 4 frases, con un mensaje para el proximo ano. "
            "Ese cierre puede ser duro, optimista, satisfecho o exigente segun resultados, economia, direccion de la franquicia "
            "y atributos del propietario. Debe insinuar que despues del verano propietario y GM se sentaran a definir objetivos concretos. "
            "No trates el nombre del propietario como si fuera el GM."
        )
        user_prompt = (
            f"Contexto:\n{context}\n\n"
            f"Mensaje inicial del propietario:\n{owner_message}\n\n"
            f"Respuesta del GM:\n{gm_response}\n\n"
            "Devuelve el JSON solicitado."
        )
        generated = self._openai_text_response(system_prompt, user_prompt, max_output_tokens=900)
        return self._owner_interview_parse_final(generated, gm_response)

    def _post_discord_json(self, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = Request(
            self.discord_webhook_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "anba-excel/1.0",
            },
            method="POST",
        )
        with urlopen(req, timeout=self.discord_timeout_seconds) as resp:
            resp.read()

    def _post_discord_multipart(
        self,
        payload: Dict[str, Any],
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> None:
        boundary = f"----anba-discord-{secrets.token_hex(16)}"
        payload_json = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        chunks = [
            f"--{boundary}\r\n".encode("utf-8"),
            b'Content-Disposition: form-data; name="payload_json"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            payload_json,
            b"\r\n",
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'.encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
        body = b"".join(chunks)
        req = Request(
            self.discord_webhook_url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "anba-excel/1.0",
            },
            method="POST",
        )
        with urlopen(req, timeout=max(self.discord_timeout_seconds, 15)) as resp:
            resp.read()

    def _notify_discord(
        self,
        title: str,
        description: str,
        fields: Optional[List[Dict[str, Any]]] = None,
        color: int = 0x0F766E,
        image_prompt: Optional[str] = None,
        image_reference_url: Optional[str] = None,
        image_fallback_prompt: Optional[str] = None,
        generate_image: bool = True,
    ) -> None:
        if not self.discord_notifications_enabled or not self.discord_webhook_url:
            return

        normalized_fields: List[Dict[str, Any]] = []
        for field in fields or []:
            name = self._discord_text(field.get("name"), 256)
            value = self._discord_text(field.get("value"), 1024)
            if not name or not value:
                continue
            normalized_fields.append(
                {
                    "name": name,
                    "value": value,
                    "inline": bool(field.get("inline")),
                }
            )

        embed: Dict[str, Any] = {
            "title": self._discord_text(title, 256),
            "description": self._discord_text(description, 4096),
            "color": color,
        }
        if normalized_fields:
            embed["fields"] = normalized_fields[:25]

        image_attachment = None
        if generate_image:
            image_attachment = self._generate_openai_image(
                image_prompt or "",
                reference_image_url=image_reference_url,
                fallback_prompt=image_fallback_prompt,
            )
        if image_attachment:
            _, filename, _ = image_attachment
            embed["image"] = {"url": f"attachment://{filename}"}

        allowed_mentions: Dict[str, Any] = {"parse": []}
        payload: Dict[str, Any] = {
            "embeds": [embed],
            "allowed_mentions": allowed_mentions,
        }
        if re.fullmatch(r"\d+", self.discord_role_id):
            payload["content"] = f"<@&{self.discord_role_id}>"
            allowed_mentions["roles"] = [self.discord_role_id]

        try:
            if image_attachment:
                file_bytes, filename, mime_type = image_attachment
                try:
                    self._post_discord_multipart(payload, file_bytes, filename, mime_type)
                except (HTTPError, URLError, TimeoutError, OSError) as upload_err:
                    self.log_error("Discord image notification failed; retrying text-only: %s", upload_err)
                    embed.pop("image", None)
                    self._post_discord_json(payload)
            else:
                self._post_discord_json(payload)
        except (HTTPError, URLError, TimeoutError, OSError) as err:
            self.log_error("Discord notification failed: %s", err)

    def _discord_notify_requested(self, payload: Dict[str, Any]) -> bool:
        if "notify_discord" not in payload:
            return True
        return parse_bool(payload.get("notify_discord"))

    def _discord_image_requested(self, payload: Dict[str, Any]) -> bool:
        if "generate_discord_image" not in payload:
            return True
        return parse_bool(payload.get("generate_discord_image"))

    def _notify_player_cut(self, result: Dict[str, Any], *, generate_image: bool = True) -> None:
        team_code = str(result.get("team_code") or "").upper()
        team_name = str(result.get("team_name") or team_code)
        player_name = str(result.get("player_name") or "Jugador")
        reference_url = str(result.get("reference_image_url") or "").strip()
        headline = f"{team_code} corta a {player_name}"
        description = "El jugador pasa a agentes libres y su contrato queda registrado como contrato muerto."
        generic_prompt = self._news_image_prompt(
            headline,
            description,
            teams=[team_code],
            players=[player_name],
            context="Transaction: the team cuts the player. Visual should feel like a clean basketball news announcement.",
        )
        reference_prompt = self._news_image_prompt(
            headline,
            description,
            teams=[team_code],
            players=[player_name],
            team_name=team_name,
            team_code=team_code,
            player_name=player_name,
            secondary_headline=description,
            additional_details="El jugador pasa a agentes libres y su contrato queda registrado como contrato muerto.",
            transaction_type="Released",
            use_player_reference=bool(reference_url),
        )
        self._notify_discord(
            headline,
            description,
            fields=[
                {"name": "Equipo", "value": team_code, "inline": True},
                {"name": "Jugador", "value": player_name, "inline": True},
            ],
            color=0xB91C1C,
            image_prompt=reference_prompt,
            image_reference_url=reference_url,
            image_fallback_prompt=generic_prompt,
            generate_image=generate_image,
        )

    def _trade_asset_summary(self, players: List[Any], pick_count: Any, right_count: Any) -> str:
        items = [str(name) for name in players or [] if str(name or "").strip()]
        picks = parse_int(str(pick_count))
        rights = parse_int(str(right_count))
        if picks and picks > 0:
            items.append(f"{picks} ronda(s) del draft")
        if rights and rights > 0:
            items.append(f"{rights} derecho(s) de jugador")
        if not items:
            return "Sin activos registrados"
        return "\n".join(f"- {item}" for item in items)

    def _notify_trade_processed(self, result: Dict[str, Any], *, generate_image: bool = True) -> None:
        team_a = str(result.get("team_a", {}).get("code") or "").upper()
        team_b = str(result.get("team_b", {}).get("code") or "").upper()
        bucket = normalize_trade_bucket(result.get("trade_bucket"))
        bucket_label = "movimientos pre-30" if bucket == "pre30" else "movimientos post-30"
        headline = f"{team_a} y {team_b} cierran un traspaso"
        description = f"El movimiento queda registrado en la cuenta de {bucket_label}."
        team_a_receives = self._trade_asset_summary(result.get("players_b") or [], result.get("pick_count_b"), result.get("right_count_b"))
        team_b_receives = self._trade_asset_summary(result.get("players_a") or [], result.get("pick_count_a"), result.get("right_count_a"))
        player_names = [
            str(name)
            for name in list(result.get("players_a") or []) + list(result.get("players_b") or [])
            if str(name or "").strip()
        ]
        self._notify_discord(
            headline,
            description,
            fields=[
                {
                    "name": f"{team_a} recibe",
                    "value": team_a_receives,
                    "inline": False,
                },
                {
                    "name": f"{team_b} recibe",
                    "value": team_b_receives,
                    "inline": False,
                },
            ],
            color=0x0F766E,
            image_prompt=self._news_image_prompt(
                headline,
                description,
                teams=[team_a, team_b],
                players=player_names[:6],
                context=f"{team_a} receives: {team_a_receives}. {team_b} receives: {team_b_receives}.",
            ),
            generate_image=generate_image,
        )

    def _notify_contract_option_action(
        self,
        player: Dict[str, Any],
        season: int,
        option_value: str,
        action: str,
        *,
        generate_image: bool = True,
    ) -> None:
        team_code = str(player.get("team_code") or "").upper()
        team_name = str(player.get("team_name") or team_code)
        player_name = str(player.get("name") or "Jugador")
        reference_url = str(player.get("reference_image_url") or "").strip()
        option_type = option_value.strip().upper()
        normalized_action = "accepted" if action == "accepted" else "rejected"
        verb = "acepta" if normalized_action == "accepted" else "rechaza"
        season_text = f"{season}-{(season + 1) % 100:02d}"
        if option_type == "TO":
            headline = f"{team_code} {verb} la team option de {player_name}"
        elif option_type == "PO":
            headline = f"{player_name} {verb} su player option con {team_code}"
        elif option_type == "QO":
            headline = f"{team_code} {verb} la qualifying offer de {player_name}"
        elif option_type == "GAP":
            headline = f"{team_code} {verb} la opción GAP de {player_name}"
        else:
            headline = f"{team_code} {verb} la opción {option_type} de {player_name}"
        description = f"Decisión registrada para la temporada {season_text}."
        option_context = {
            "TO": "team option",
            "PO": "player option",
            "QO": "qualifying offer",
            "GAP": "GAP option",
        }.get(option_type, f"{option_type} option")
        transaction_type_map = {
            ("TO", "accepted"): "Team Option Exercised",
            ("TO", "rejected"): "Team Option Declined",
            ("PO", "accepted"): "Player Option Exercised",
            ("PO", "rejected"): "Player Option Declined",
            ("QO", "accepted"): "Qualifying Offer Accepted",
            ("QO", "rejected"): "Qualifying Offer Rejected",
            ("GAP", "accepted"): "Contract Guaranteed",
            ("GAP", "rejected"): "Contract Non-Guaranteed",
        }
        transaction_type = transaction_type_map.get((option_type, normalized_action), "Contract Decision")
        generic_prompt = self._news_image_prompt(
            headline,
            description,
            teams=[team_code],
            players=[player_name],
            context=f"Contract decision: the {option_context} was {normalized_action} for season {season_text}.",
        )
        reference_prompt = self._news_image_prompt(
            headline,
            description,
            teams=[team_code],
            players=[player_name],
            team_name=team_name,
            team_code=team_code,
            player_name=player_name,
            secondary_headline=description,
            additional_details=f"Temporada {season_text}. Opcion: {option_type}. Decision: {normalized_action}.",
            transaction_type=transaction_type,
            use_player_reference=bool(reference_url),
        )
        self._notify_discord(
            headline,
            description,
            fields=[
                {"name": "Equipo", "value": team_code, "inline": True},
                {"name": "Jugador", "value": player_name, "inline": True},
                {"name": "Temporada", "value": season_text, "inline": True},
                {"name": "Opción", "value": option_type, "inline": True},
            ],
            color=0x7C3AED if normalized_action == "accepted" else 0xB91C1C,
            image_prompt=reference_prompt,
            image_reference_url=reference_url,
            image_fallback_prompt=generic_prompt,
            generate_image=generate_image,
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
            role, team_codes = self._google_role_for_email(email)

            token, _ = self._start_session(
                {
                    "provider": "google",
                    "user_id": user["id"],
                    "email": email,
                    "name": user.get("display_name") or email,
                    "role": role,
                    "team_codes": team_codes,
                    "team_code": team_codes[0] if team_codes else None,
                    "logged_in_at": now_iso(),
                }
            )
            cookie = self._session_cookie(token)
            self._redirect(self._landing_path_for_session(role, team_codes), headers={"Set-Cookie": cookie})
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
                        "team_code": None,
                        "team_codes": [],
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
                    "team_code": sess.get("team_code"),
                    "team_codes": sess.get("team_codes") if isinstance(sess.get("team_codes"), list) else [],
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

        if parsed.path == "/api/tracker/economy":
            qs = parse_qs(parsed.query)
            raw_season = (qs.get("season") or [""])[0].strip()
            season_year = parse_int(raw_season) if raw_season else None
            if raw_season and season_year is None:
                self._json(400, {"error": "invalid_season_year"})
                return
            self._json(200, self.db.list_team_economy(season_year))
            return

        if parsed.path == "/api/free-agents":
            self._json(200, {"free_agents": self.db.list_free_agents()})
            return

        if parsed.path == "/api/draft-order":
            qs = parse_qs(parsed.query)
            raw_year = (qs.get("year") or [""])[0].strip()
            draft_year = None
            if raw_year:
                draft_year = parse_int(raw_year)
                if draft_year is None or draft_year < 2000 or draft_year > 2100:
                    self._json(400, {"error": "invalid_draft_year"})
                    return
            self._json(200, self.db.list_draft_order(draft_year))
            return

        if parsed.path == "/api/gm-history":
            if not self._require_admin():
                return
            qs = parse_qs(parsed.query)
            team_code = str((qs.get("team") or [""])[0] or "").strip().upper() or None
            rows = self.db.list_gm_history(team_code)
            if rows is None:
                self._json(404, {"error": "team_not_found"})
                return
            self._json(200, {"gm_history": rows})
            return

        if parsed.path == "/api/settings":
            settings = self.db.get_settings()
            self._json(
                200,
                {"settings": public_settings_payload(settings)},
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

        if parsed.path == "/api/admin/users":
            if not self._require_admin():
                return
            users = self.db.list_users()
            for user in users:
                email = str(user.get("email") or "").strip().lower()
                team_codes = normalize_team_codes(user.get("team_codes"))
                user["role"] = "admin" if email in self.admin_emails else ("gm" if team_codes else "guest")
                user["team_code"] = team_codes[0] if team_codes else None
                user["team_codes"] = team_codes
            self._json(200, {"users": users})
            return

        if parsed.path == "/api/admin/gm-option-requests":
            if not self._require_admin():
                return
            qs = parse_qs(parsed.query)
            status = (qs.get("status") or ["pending"])[0].strip().lower() or "pending"
            self._json(200, {"requests": self.db.list_gm_option_requests(status=status)})
            return

        if parsed.path.startswith("/api/teams/") and parsed.path.endswith("/owner-office"):
            parts = parsed.path.split("/")
            if len(parts) < 5:
                self._json(404, {"error": "not_found"})
                return
            code = parts[3]
            if not self._require_authenticated():
                return
            if not self._can_manage_team(code):
                self._json(403, {"error": "team_access_required"})
                return
            data = self.db.get_team_owner_office(code, include_private=self._is_admin())
            if not data:
                self._json(404, {"error": "team_not_found"})
                return
            self._json(200, {"owner_office": data})
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

        if parsed.path == "/api/gm/option-requests":
            if not self._require_authenticated():
                return
            if not self._require_csrf():
                return
            if not (self._is_gm() or self._is_admin()):
                self._json(403, {"error": "gm_auth_required"})
                return
            player_id = parse_int(payload.get("player_id"))
            if player_id is None:
                self._json(400, {"error": "invalid_player_id"})
                return
            option_field = str(payload.get("option_field") or "").strip()
            option_value = str(payload.get("option_value") or "").strip().upper()
            option_action = str(payload.get("action") or "").strip().lower()
            player = self.db.get_player_record(player_id)
            if not player:
                self._json(404, {"error": "player_not_found"})
                return
            if not self._can_manage_team(player.get("team_code")):
                self._json(403, {"error": "team_access_required"})
                return
            try:
                request = self.db.create_gm_option_request(
                    player_id,
                    option_field,
                    option_value,
                    option_action,
                    self._current_session() or {},
                )
            except ValueError as err:
                message = str(err)
                if message == "invalid_option_field":
                    self._json(400, {"error": "invalid_option_field"})
                    return
                if message == "invalid_option_value":
                    self._json(400, {"error": "invalid_option_value"})
                    return
                if message == "invalid_option_action":
                    self._json(400, {"error": "invalid_option_action"})
                    return
                if message == "option_mismatch":
                    self._json(409, {"error": "option_changed"})
                    return
                raise
            if not request:
                self._json(404, {"error": "player_not_found"})
                return
            self._json(201, {"ok": True, "request": request})
            return

        if parsed.path.startswith("/api/teams/") and "/owner-exit-interview/" in parsed.path:
            parts = parsed.path.split("/")
            if len(parts) < 6:
                self._json(404, {"error": "not_found"})
                return
            code = parts[3]
            action = parts[-1]
            if action not in {"start", "reply", "reset"}:
                self._json(404, {"error": "not_found"})
                return
            if not self._require_authenticated():
                return
            if not self._require_csrf():
                return
            if not (self._is_gm() or self._is_admin()):
                self._json(403, {"error": "gm_auth_required"})
                return
            if not self._can_manage_team(code):
                self._json(403, {"error": "team_access_required"})
                return
            settings = self.db.get_settings()
            current_year = parse_int(settings.get("current_year")) or 2025
            season_year = parse_int(payload.get("season_year")) or current_year
            if season_year != current_year:
                self._json(400, {"error": "invalid_exit_interview_season", "season_year": current_year})
                return
            if action == "reset":
                if not self._is_admin():
                    self._json(403, {"error": "admin_required"})
                    return
                ok = self.db.reset_owner_exit_interview(code, season_year)
                if not ok:
                    self._json(404, {"error": "team_not_found"})
                    return
                refreshed = self.db.get_team_owner_office(code, include_private=True)
                self._log_admin_action(
                    "reset",
                    "owner_exit_interview",
                    f"{code.upper()}:{season_year}",
                    code.upper(),
                    {"season_year": season_year},
                )
                self._json(200, {"ok": True, "owner_office": refreshed})
                return
            if not parse_bool(settings.get("free_agency_mode")):
                self._json(409, {"error": "free_agency_mode_required"})
                return
            owner_office = self.db.get_team_owner_office(code, include_private=True)
            if not owner_office:
                self._json(404, {"error": "team_not_found"})
                return
            session = self._current_session() or {}
            if action == "start":
                existing = self.db.get_owner_exit_interview(code, season_year)
                owner_message = str(existing.get("owner_message") or "").strip() if existing else ""
                if not owner_message:
                    owner_message = self._owner_interview_opening_message(owner_office, season_year, session=session)
                interview = self.db.start_owner_exit_interview(code, season_year, session, owner_message)
                if not interview:
                    self._json(404, {"error": "team_not_found"})
                    return
                refreshed = self.db.get_team_owner_office(code, include_private=self._is_admin())
                self._json(200, {"ok": True, "interview": interview, "owner_office": refreshed})
                return

            gm_response = str(payload.get("gm_response") or "").strip()
            if not gm_response:
                self._json(400, {"error": "gm_response_required"})
                return
            if len(gm_response) > 4000:
                self._json(400, {"error": "gm_response_too_long"})
                return
            existing = self.db.get_owner_exit_interview(code, season_year)
            if not existing or not str(existing.get("owner_message") or "").strip():
                self._json(409, {"error": "interview_not_started"})
                return
            if str(existing.get("status") or "").lower() == "completed":
                self._json(200, {"ok": True, "interview": existing})
                return
            final_message, conclusion_message, trust_delta = self._owner_interview_final_reply(
                owner_office,
                season_year,
                str(existing.get("owner_message") or ""),
                gm_response,
                session=session,
            )
            interview = self.db.complete_owner_exit_interview(
                code,
                season_year,
                session,
                gm_response,
                final_message,
                conclusion_message,
                trust_delta,
            )
            if not interview:
                self._json(404, {"error": "interview_not_found"})
                return
            refreshed = self.db.get_team_owner_office(code, include_private=self._is_admin())
            self._json(200, {"ok": True, "interview": interview, "owner_office": refreshed})
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

        if parsed.path == "/api/draft-order":
            try:
                draft_order_id = self.db.create_draft_order_entry(payload)
            except ValueError as err:
                self._json(400, {"error": str(err) or "invalid_draft_order"})
                return
            self._log_admin_action(
                "create",
                "draft_order",
                str(draft_order_id),
                payload.get("owner_team_code"),
                {
                    "draft_year": payload.get("draft_year"),
                    "draft_round": payload.get("draft_round"),
                    "pick_number": payload.get("pick_number"),
                    "original_team_code": payload.get("original_team_code"),
                },
            )
            self._json(201, {"draft_order_id": draft_order_id})
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
            if self._discord_notify_requested(payload):
                self._notify_player_cut(result, generate_image=self._discord_image_requested(payload))
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
                if self._discord_notify_requested(payload):
                    self._notify_trade_processed(result, generate_image=self._discord_image_requested(payload))
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

        if parsed.path == "/api/gm-history":
            team_code = str(payload.get("team_code") or "").strip().upper()
            if not team_code:
                self._json(400, {"error": "team_code_required"})
                return
            raw_entries = payload.get("entries")
            if not isinstance(raw_entries, list):
                self._json(400, {"error": "entries_required"})
                return
            try:
                rows = self.db.replace_gm_history(team_code, raw_entries)
            except ValueError as err:
                self._json(400, {"error": str(err) or "invalid_gm_history"})
                return
            if rows is None:
                self._json(404, {"error": "team_not_found"})
                return
            self._log_admin_action(
                "update",
                "gm_history",
                team_code,
                team_code,
                {"entries_count": len(rows)},
            )
            self._json(200, {"ok": True, "gm_history": rows})
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
            self._log_admin_action("update", "settings", None, None, {"progress_year": result})
            self._json(
                200,
                {
                    "ok": True,
                    "result": result,
                    "settings": public_settings_payload(merged),
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

        if parsed.path == "/api/tracker/economy":
            parsed_season = parse_int(str(payload.get("season_year") or payload.get("season") or ""))
            if parsed_season is None or parsed_season < 2000 or parsed_season > 2100:
                self._json(400, {"error": "invalid_season_year"})
                return
            rows = payload.get("rows")
            if not isinstance(rows, list):
                self._json(400, {"error": "rows_required"})
                return
            try:
                result = self.db.upsert_team_economy(parsed_season, rows)
            except ValueError as err:
                message = str(err)
                if message.startswith("invalid_team_code:"):
                    self._json(400, {"error": "invalid_team_code", "team_code": message.split(":", 1)[1]})
                    return
                if message == "invalid_season_year":
                    self._json(400, {"error": "invalid_season_year"})
                    return
                raise
            self._log_admin_action(
                "update",
                "team_economy",
                str(parsed_season),
                None,
                {"season_year": parsed_season, "row_count": len(rows)},
            )
            self._json(200, {"ok": True, **result})
            return

        if parsed.path.startswith("/api/admin/gm-option-requests/"):
            try:
                request_id = int(parsed.path.split("/")[-1])
            except ValueError:
                self._json(400, {"error": "invalid_request_id"})
                return
            admin_decision = str(payload.get("decision") or "").strip().lower()
            if admin_decision not in {"approved", "rejected"}:
                self._json(400, {"error": "invalid_decision"})
                return
            request = self.db.get_gm_option_request(request_id)
            if not request:
                self._json(404, {"error": "request_not_found"})
                return
            if str(request.get("status") or "").lower() != "pending":
                self._json(409, {"error": "request_already_decided", "request": request})
                return

            if admin_decision == "rejected":
                updated = self.db.mark_gm_option_request_decided(
                    request_id,
                    "rejected",
                    self._current_session() or {},
                    str(payload.get("note") or "").strip() or None,
                )
                if not updated:
                    self._json(409, {"error": "request_already_decided"})
                    return
                self._log_admin_action(
                    "reject",
                    "gm_option_request",
                    str(request_id),
                    request.get("team_code"),
                    {
                        "player_id": request.get("player_id"),
                        "player_name": request.get("player_name"),
                        "option_action": request.get("action"),
                        "option_field": request.get("option_field"),
                        "option_value": request.get("option_value"),
                    },
                )
                self._json(200, {"ok": True, "request": updated})
                return

            option_field = str(request.get("option_field") or "").strip()
            option_value = str(request.get("option_value") or "").strip().upper()
            option_action = str(request.get("action") or "").strip().lower()
            match = re.fullmatch(r"option_(20\d{2})", option_field)
            option_action_season = parse_int(match.group(1)) if match else None
            if option_action_season is None:
                self._json(400, {"error": "invalid_option_field"})
                return
            if option_value not in {"TO", "PO", "QO", "GAP"}:
                self._json(400, {"error": "invalid_option_value"})
                return
            if option_action not in {"accepted", "rejected"}:
                self._json(400, {"error": "invalid_option_action"})
                return
            player_id = parse_int(str(request.get("player_id") or ""))
            if player_id is None:
                self._json(400, {"error": "invalid_player_id"})
                return
            player_before = self.db.get_player_record(player_id)
            if not player_before:
                self._json(404, {"error": "player_not_found"})
                return
            current_option = str(player_before.get(option_field) or "").strip().upper()
            if current_option != option_value:
                self._json(409, {"error": "option_changed", "current_option": current_option})
                return

            player_payload: Dict[str, Any] = {}
            if option_action == "accepted" and option_value == "QO":
                # Keep the QO marker so cap-hold calculations continue to work.
                player_payload[option_field] = option_value
            else:
                # Rejected options, and accepted non-QO options, remove the
                # pending option marker from the roster cell.
                player_payload[option_field] = None

            ok = self.db.update_player(player_id, player_payload)
            if not ok:
                self._json(404, {"error": "player_not_found"})
                return
            updated = self.db.mark_gm_option_request_decided(
                request_id,
                "approved",
                self._current_session() or {},
                str(payload.get("note") or "").strip() or None,
            )
            if not updated:
                self._json(409, {"error": "request_already_decided"})
                return
            self._log_admin_action(
                "approve",
                "gm_option_request",
                str(request_id),
                request.get("team_code"),
                {
                    "player_id": player_id,
                    "player_name": request.get("player_name"),
                    "option_action": option_action,
                    "option_field": option_field,
                    "option_value": option_value,
                    "option_action_season": option_action_season,
                    "applied_fields": sorted(player_payload.keys()),
                },
            )
            if self._discord_notify_requested(payload):
                self._notify_contract_option_action(
                    player_before,
                    option_action_season,
                    option_value,
                    option_action,
                    generate_image=self._discord_image_requested(payload),
                )
            self._json(200, {"ok": True, "request": updated})
            return

        if parsed.path.startswith("/api/admin/users/"):
            try:
                user_id = int(parsed.path.split("/")[-1])
            except ValueError:
                self._json(400, {"error": "invalid_user_id"})
                return
            team_codes = payload.get("team_codes")
            if team_codes is None and "team_code" in payload:
                team_code = str(payload.get("team_code") or "").strip()
                team_codes = [team_code] if team_code else []
            if team_codes is None:
                self._json(400, {"error": "team_codes_required"})
                return
            try:
                user = self.db.replace_user_team_assignments(user_id, team_codes)
            except ValueError as err:
                message = str(err)
                if message.startswith("invalid_team_code:"):
                    self._json(400, {"error": "invalid_team_code", "team_code": message.split(":", 1)[1]})
                    return
                raise
            if user is None:
                self._json(404, {"error": "user_not_found"})
                return
            assigned_codes = normalize_team_codes(user.get("team_codes"))
            email = str(user.get("email") or "").strip().lower()
            user["role"] = "admin" if email in self.admin_emails else ("gm" if assigned_codes else "guest")
            user["team_code"] = assigned_codes[0] if assigned_codes else None
            user["team_codes"] = assigned_codes
            self._log_admin_action(
                "update",
                "user_access",
                str(user_id),
                assigned_codes[0] if assigned_codes else None,
                {"email": user.get("email"), "team_codes": assigned_codes},
            )
            self._json(200, {"ok": True, "user": user})
            return

        if parsed.path == "/api/settings":
            next_salary_cap: Optional[float] = None
            next_current_year: Optional[int] = None
            next_first_apron: Optional[float] = None
            next_second_apron: Optional[float] = None
            next_cash_limit_total: Optional[float] = None
            next_trade_move_limit_pre30: Optional[int] = None
            next_trade_move_limit_post30: Optional[int] = None
            next_trade_move_phase: Optional[str] = None
            next_free_agency_mode: Optional[bool] = None
            next_roster_standard_min: Optional[int] = None
            next_roster_standard_max: Optional[int] = None
            next_roster_standard_offseason_max: Optional[int] = None
            next_roster_two_way_min: Optional[int] = None
            next_roster_two_way_max: Optional[int] = None
            season_cap_updates: Dict[str, Optional[float]] = {}

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

            if "free_agency_mode" in payload:
                next_free_agency_mode = parse_bool(payload.get("free_agency_mode"))

            for field, raw_value in payload.items():
                match = re.fullmatch(r"(salary_cap|first_apron|second_apron|average_salary)_(\d{4})", str(field))
                if not match:
                    continue
                if field == "salary_cap_2025":
                    continue
                setting_kind = match.group(1)
                season_year = parse_int(match.group(2))
                if season_year is None or season_year < CAP_FORECAST_MIN_YEAR or season_year > CAP_FORECAST_MAX_YEAR:
                    self._json(400, {"error": f"invalid_{field}"})
                    return
                if setting_kind == "average_salary" and (raw_value is None or str(raw_value).strip() == ""):
                    season_cap_updates[str(field)] = None
                    continue
                parsed_value = parse_float(str(raw_value))
                if parsed_value is None or parsed_value <= 0:
                    self._json(400, {"error": f"invalid_{field}"})
                    return
                season_cap_updates[str(field)] = parsed_value

            roster_int_fields = {
                "roster_standard_min": "invalid_roster_standard_min",
                "roster_standard_max": "invalid_roster_standard_max",
                "roster_standard_offseason_max": "invalid_roster_standard_offseason_max",
                "roster_two_way_min": "invalid_roster_two_way_min",
                "roster_two_way_max": "invalid_roster_two_way_max",
            }
            parsed_roster_fields: Dict[str, int] = {}
            for field, error in roster_int_fields.items():
                if field not in payload:
                    continue
                parsed_value = parse_int(str(payload.get(field)))
                if parsed_value is None or parsed_value < 0:
                    self._json(400, {"error": error})
                    return
                parsed_roster_fields[field] = parsed_value
            if "roster_standard_min" in parsed_roster_fields:
                next_roster_standard_min = parsed_roster_fields["roster_standard_min"]
            if "roster_standard_max" in parsed_roster_fields:
                next_roster_standard_max = parsed_roster_fields["roster_standard_max"]
            if "roster_standard_offseason_max" in parsed_roster_fields:
                next_roster_standard_offseason_max = parsed_roster_fields["roster_standard_offseason_max"]
            if "roster_two_way_min" in parsed_roster_fields:
                next_roster_two_way_min = parsed_roster_fields["roster_two_way_min"]
            if "roster_two_way_max" in parsed_roster_fields:
                next_roster_two_way_max = parsed_roster_fields["roster_two_way_max"]

            current_settings = public_settings_payload(self.db.get_settings())
            standard_min_check = next_roster_standard_min if next_roster_standard_min is not None else int(current_settings["roster_standard_min"])
            standard_max_check = next_roster_standard_max if next_roster_standard_max is not None else int(current_settings["roster_standard_max"])
            standard_offseason_max_check = (
                next_roster_standard_offseason_max
                if next_roster_standard_offseason_max is not None
                else int(current_settings["roster_standard_offseason_max"])
            )
            two_way_min_check = next_roster_two_way_min if next_roster_two_way_min is not None else int(current_settings["roster_two_way_min"])
            two_way_max_check = next_roster_two_way_max if next_roster_two_way_max is not None else int(current_settings["roster_two_way_max"])
            if standard_min_check > standard_max_check or standard_max_check > standard_offseason_max_check:
                self._json(400, {"error": "invalid_roster_standard_range"})
                return
            if two_way_min_check > two_way_max_check:
                self._json(400, {"error": "invalid_roster_two_way_range"})
                return

            if (
                next_salary_cap is None
                and next_current_year is None
                and next_first_apron is None
                and next_second_apron is None
                and next_cash_limit_total is None
                and next_trade_move_limit_pre30 is None
                and next_trade_move_limit_post30 is None
                and next_trade_move_phase is None
                and next_free_agency_mode is None
                and not season_cap_updates
                and next_roster_standard_min is None
                and next_roster_standard_max is None
                and next_roster_standard_offseason_max is None
                and next_roster_two_way_min is None
                and next_roster_two_way_max is None
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
            if next_free_agency_mode is not None:
                self.db.update_setting("free_agency_mode", "1" if next_free_agency_mode else "0")
            for key, value in season_cap_updates.items():
                self.db.update_setting(key, "" if value is None else str(int(value)))
            if next_roster_standard_min is not None:
                self.db.update_setting("roster_standard_min", str(next_roster_standard_min))
            if next_roster_standard_max is not None:
                self.db.update_setting("roster_standard_max", str(next_roster_standard_max))
            if next_roster_standard_offseason_max is not None:
                self.db.update_setting("roster_standard_offseason_max", str(next_roster_standard_offseason_max))
            if next_roster_two_way_min is not None:
                self.db.update_setting("roster_two_way_min", str(next_roster_two_way_min))
            if next_roster_two_way_max is not None:
                self.db.update_setting("roster_two_way_max", str(next_roster_two_way_max))
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
                    "free_agency_mode": next_free_agency_mode,
                    "season_cap_updates": season_cap_updates,
                    "roster_standard_min": next_roster_standard_min,
                    "roster_standard_max": next_roster_standard_max,
                    "roster_standard_offseason_max": next_roster_standard_offseason_max,
                    "roster_two_way_min": next_roster_two_way_min,
                    "roster_two_way_max": next_roster_two_way_max,
                },
            )

            merged = self.db.get_settings()
            self._json(
                200,
                {
                    "ok": True,
                    "settings": public_settings_payload(merged),
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

        if parsed.path.startswith("/api/draft-order/"):
            try:
                draft_order_id = int(parsed.path.split("/")[-1])
            except ValueError:
                self._json(400, {"error": "invalid_draft_order_id"})
                return
            try:
                ok = self.db.update_draft_order_entry(draft_order_id, payload)
            except ValueError as err:
                self._json(400, {"error": str(err) or "invalid_draft_order"})
                return
            if ok:
                self._log_admin_action(
                    "update",
                    "draft_order",
                    str(draft_order_id),
                    payload.get("owner_team_code"),
                    {"fields": sorted(payload.keys())},
                )
            self._json(200 if ok else 404, {"ok": ok})
            return

        if parsed.path.startswith("/api/players/"):
            player_id = int(parsed.path.split("/")[-1])
            option_action = str(payload.get("option_action") or "").strip().lower()
            option_action_field = str(payload.get("option_action_field") or "").strip()
            option_action_value = str(payload.get("option_action_value") or "").strip().upper()
            option_action_season: Optional[int] = None
            player_before: Optional[Dict[str, Any]] = None
            if option_action:
                if option_action not in {"accepted", "rejected"}:
                    self._json(400, {"error": "invalid_option_action"})
                    return
                match = re.fullmatch(r"option_(20\d{2})", option_action_field)
                if not match:
                    self._json(400, {"error": "invalid_option_action_field"})
                    return
                option_action_season = parse_int(match.group(1))
                if option_action_season is None:
                    self._json(400, {"error": "invalid_option_action_season"})
                    return
                player_before = self.db.get_player_record(player_id)
                if not player_before:
                    self._json(404, {"error": "player_not_found"})
                    return
                if not option_action_value:
                    option_action_value = str(payload.get(option_action_field) or player_before.get(option_action_field) or "").strip().upper()
                if option_action_value not in {"TO", "PO", "QO", "GAP"}:
                    self._json(400, {"error": "invalid_option_action_value"})
                    return
                if option_action == "accepted" and option_action_value in {"TO", "PO"}:
                    payload[option_action_field] = None
            ok = self.db.update_player(player_id, payload)
            if ok:
                log_details: Dict[str, Any] = {"fields": sorted(payload.keys())}
                if option_action and option_action_season is not None:
                    log_details.update(
                        {
                            "option_action": option_action,
                            "option_action_field": option_action_field,
                            "option_action_value": option_action_value,
                            "option_action_season": option_action_season,
                        }
                    )
                self._log_admin_action("update", "player", str(player_id), None, log_details)
                if (
                    option_action
                    and option_action_season is not None
                    and player_before
                    and self._discord_notify_requested(payload)
                ):
                    self._notify_contract_option_action(
                        player_before,
                        option_action_season,
                        option_action_value,
                        option_action,
                        generate_image=self._discord_image_requested(payload),
                    )
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

        if parsed.path.startswith("/api/teams/") and parsed.path.endswith("/owner-office"):
            parts = parsed.path.split("/")
            if len(parts) < 5:
                self._json(404, {"error": "not_found"})
                return
            code = parts[3]
            try:
                owner_office = self.db.update_team_owner_office(code, payload)
            except ValueError as err:
                if str(err) == "invalid_season_year":
                    self._json(400, {"error": "invalid_season_year"})
                    return
                raise
            if not owner_office:
                self._json(404, {"error": "team_not_found"})
                return
            self._log_admin_action(
                "update",
                "team_owner_office",
                f"{code.upper()}:{payload.get('season_year')}",
                code.upper(),
                {"season_year": payload.get("season_year")},
            )
            self._json(200, {"ok": True, "owner_office": owner_office})
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

        if parsed.path.startswith("/api/draft-order/"):
            try:
                draft_order_id = int(parsed.path.split("/")[-1])
            except ValueError:
                self._json(400, {"error": "invalid_draft_order_id"})
                return
            ok = self.db.delete_draft_order_entry(draft_order_id)
            if ok:
                self._log_admin_action("delete", "draft_order", str(draft_order_id))
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
