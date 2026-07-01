#!/usr/bin/env python3
"""Import admin-only player happiness values from CSV or Google Sheets.

Expected columns, with flexible Spanish/English aliases:

    profile_id,player_name,felicidad
    275,Nikola Jokic,8.5

`profile_id` is preferred. If it is missing, the script tries an exact
case-insensitive name match against the player profile catalog.

Examples:

    # Preview a public Google Sheet tab exported as CSV.
    python3 scripts/import_player_happiness.py \
      --base-url http://127.0.0.1:8000 \
      --username admin \
      --password admin123 \
      --sheet-id 1abc... \
      --gid 0

    # Apply changes after reviewing the preview.
    python3 scripts/import_player_happiness.py \
      --base-url https://anba-excel-production.up.railway.app \
      --username "$ANBA_ADMIN_USER" \
      --password "$ANBA_ADMIN_PASSWORD" \
      --csv-url "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0" \
      --apply

    # Local DB mode, useful before deploying or for recovery work.
    python3 scripts/import_player_happiness.py --db data/league.db --file happiness.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import math
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


PROFILE_ID_HEADERS = {
    "profile_id",
    "profileid",
    "player_profile_id",
    "playerprofileid",
    "perfil_id",
    "id_perfil",
    "id",
}
NAME_HEADERS = {"player_name", "player", "name", "jugador", "nombre", "playername"}
HAPPINESS_HEADERS = {"felicidad", "happiness", "happy", "valor", "value"}


@dataclass
class ImportRow:
    line_number: int
    profile_id: Optional[int]
    player_name: str
    happiness: Any


@dataclass
class ResolvedRow:
    line_number: int
    profile_id: int
    player_name: str
    current_happiness: Optional[Any]
    next_happiness: Any
    warning: str = ""


def normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "", str(value or "").strip().lower().replace(" ", "_"))


def normalize_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    if not number.is_integer():
        return None
    return int(number)


def parse_decimal(value: Any) -> Optional[Any]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def parse_happiness(value: Any) -> Any:
    number = parse_decimal(value)
    if number is None or number < -10 or number > 10:
        raise ValueError("felicidad debe ser un número entre -10 y 10")
    return number


def read_csv_text(args: argparse.Namespace) -> str:
    sources = [bool(args.file), bool(args.csv_url), bool(args.sheet_id)]
    if sum(1 for item in sources if item) != 1:
        raise SystemExit("Usa exactamente una fuente: --file, --csv-url o --sheet-id.")
    if args.file:
        return Path(args.file).read_text(encoding="utf-8-sig")
    if args.csv_url:
        url = args.csv_url
    else:
        params = {"format": "csv"}
        if args.gid:
            params["gid"] = str(args.gid)
        url = f"https://docs.google.com/spreadsheets/d/{args.sheet_id}/export?{urlencode(params)}"
    try:
        with urlopen(url, timeout=args.timeout_seconds) as response:
            return response.read().decode("utf-8-sig")
    except HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"No se pudo descargar el CSV: HTTP {err.code}: {body}") from err
    except URLError as err:
        raise SystemExit(f"No se pudo descargar el CSV: {err}") from err


def find_column(fieldnames: Iterable[str], aliases: set[str]) -> Optional[str]:
    for field in fieldnames:
        if normalize_header(field) in aliases:
            return field
    return None


def parse_rows(csv_text: str) -> Tuple[List[ImportRow], List[str]]:
    try:
        dialect = csv.Sniffer().sniff(csv_text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(csv_text.splitlines(), dialect=dialect)
    if not reader.fieldnames:
        return [], ["El CSV no tiene cabecera."]
    profile_col = find_column(reader.fieldnames, PROFILE_ID_HEADERS)
    name_col = find_column(reader.fieldnames, NAME_HEADERS)
    happiness_col = find_column(reader.fieldnames, HAPPINESS_HEADERS)
    errors: List[str] = []
    if not profile_col and not name_col:
        errors.append("Falta columna profile_id o player_name/nombre.")
    if not happiness_col:
        errors.append("Falta columna felicidad.")
    if errors:
        return [], errors

    rows: List[ImportRow] = []
    for index, row in enumerate(reader, start=2):
        raw_profile_id = row.get(profile_col, "") if profile_col else ""
        raw_name = row.get(name_col, "") if name_col else ""
        raw_happiness = row.get(happiness_col, "") if happiness_col else ""
        if not any(str(value or "").strip() for value in row.values()):
            continue
        profile_id = parse_int(raw_profile_id)
        player_name = re.sub(r"\s+", " ", str(raw_name or "").strip())
        try:
            happiness = parse_happiness(raw_happiness)
        except ValueError as err:
            errors.append(f"Línea {index}: {err}.")
            continue
        if profile_id is None and not player_name:
            errors.append(f"Línea {index}: falta profile_id o nombre de jugador.")
            continue
        rows.append(ImportRow(index, profile_id, player_name, happiness))
    return rows, errors


class ApiClient:
    def __init__(self, base_url: str, username: str, password: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf_token = ""

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if method.upper() in {"POST", "PATCH", "DELETE"} and self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        req = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method.upper())
        try:
            with self.opener.open(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: HTTP {err.code}: {body}") from err
        except URLError as err:
            raise RuntimeError(f"{method} {path} failed: {err}") from err
        return json.loads(body) if body else {}

    def login(self) -> None:
        response = self.request("POST", "/api/auth/login", {"username": self.username, "password": self.password})
        self.csrf_token = str(response.get("csrf_token") or "")
        if not self.csrf_token:
            status = self.request("GET", "/api/auth/status")
            self.csrf_token = str(status.get("csrf_token") or "")
        if not self.csrf_token:
            raise RuntimeError("Login correcto, pero no se recibió csrf_token.")

    def list_players(self) -> List[Dict[str, Any]]:
        response = self.request("GET", "/api/admin/players")
        return list(response.get("players") or [])

    def update_happiness(self, profile_id: int, happiness: Any) -> None:
        self.request("PATCH", f"/api/player-profiles/{profile_id}", {"happiness": happiness})


def db_list_players(db_path: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        profile_cols = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(player_profiles)").fetchall()
        }
        happiness_expr = "happiness" if "happiness" in profile_cols else "0 AS happiness"
        rows = conn.execute(
            f"""
            SELECT id AS profile_id, name, {happiness_expr}
            FROM player_profiles
            ORDER BY name COLLATE NOCASE, id
            """
        ).fetchall()
        return [dict(row) for row in rows]


def db_update_happiness(db_path: str, profile_id: int, happiness: Any) -> None:
    with sqlite3.connect(db_path) as conn:
        profile_cols = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(player_profiles)").fetchall()
        }
        if "happiness" not in profile_cols:
            conn.execute("ALTER TABLE player_profiles ADD COLUMN happiness REAL NOT NULL DEFAULT 0")
        cur = conn.execute(
            """
            UPDATE player_profiles
            SET happiness = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (happiness, profile_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"profile_id no encontrado: {profile_id}")
        conn.commit()


def resolve_rows(import_rows: List[ImportRow], players: List[Dict[str, Any]]) -> Tuple[List[ResolvedRow], List[str]]:
    by_id: Dict[int, Dict[str, Any]] = {}
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for player in players:
        profile_id = parse_int(player.get("profile_id") or player.get("id"))
        if profile_id is None:
            continue
        normalized = normalize_name(player.get("name"))
        player = {**player, "profile_id": profile_id}
        by_id[profile_id] = player
        if normalized:
            by_name.setdefault(normalized, []).append(player)

    resolved: List[ResolvedRow] = []
    errors: List[str] = []
    seen_profile_ids: set[int] = set()
    for item in import_rows:
        profile: Optional[Dict[str, Any]] = None
        warning = ""
        if item.profile_id is not None:
            profile = by_id.get(item.profile_id)
            if not profile:
                errors.append(f"Línea {item.line_number}: profile_id no encontrado: {item.profile_id}.")
                continue
            if item.player_name and normalize_name(item.player_name) != normalize_name(profile.get("name")):
                warning = f"nombre CSV '{item.player_name}' != perfil '{profile.get('name')}'"
        else:
            matches = by_name.get(normalize_name(item.player_name), [])
            if not matches:
                errors.append(f"Línea {item.line_number}: jugador no encontrado por nombre: {item.player_name}.")
                continue
            if len(matches) > 1:
                ids = ", ".join(str(match.get("profile_id")) for match in matches)
                errors.append(f"Línea {item.line_number}: nombre duplicado '{item.player_name}', usa profile_id. Perfiles: {ids}.")
                continue
            profile = matches[0]
        profile_id = int(profile["profile_id"])
        if profile_id in seen_profile_ids:
            errors.append(f"Línea {item.line_number}: profile_id duplicado en el CSV: {profile_id}.")
            continue
        seen_profile_ids.add(profile_id)
        resolved.append(
            ResolvedRow(
                line_number=item.line_number,
                profile_id=profile_id,
                player_name=str(profile.get("name") or item.player_name),
                current_happiness=parse_decimal(profile.get("happiness")),
                next_happiness=item.happiness,
                warning=warning,
            )
        )
    return resolved, errors


def print_preview(rows: List[ResolvedRow], errors: List[str]) -> None:
    if errors:
        print("Errores:")
        for error in errors:
            print(f"  - {error}")
    if rows:
        print("\nCambios detectados:")
        for row in rows:
            suffix = f"  WARNING: {row.warning}" if row.warning else ""
            print(
                f"  Línea {row.line_number}: #{row.profile_id} {row.player_name}: "
                f"{row.current_happiness if row.current_happiness is not None else 'N/A'} -> {row.next_happiness}{suffix}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import player happiness values from CSV or Google Sheets.")
    source = parser.add_argument_group("source")
    source.add_argument("--file", help="Local CSV file exported from Google Sheets.")
    source.add_argument("--csv-url", help="Direct CSV export URL.")
    source.add_argument("--sheet-id", help="Google Sheets spreadsheet ID. The sheet must be accessible as CSV.")
    source.add_argument("--gid", default="0", help="Google Sheets tab gid when using --sheet-id. Default: 0.")
    target = parser.add_argument_group("target")
    target.add_argument("--base-url", default=os.getenv("ANBA_BASE_URL", ""), help="Site URL for API mode.")
    target.add_argument("--username", default=os.getenv("ANBA_ADMIN_USER", ""), help="Admin username for API mode.")
    target.add_argument("--password", default=os.getenv("ANBA_ADMIN_PASSWORD", ""), help="Admin password for API mode.")
    target.add_argument("--db", help="SQLite DB path for direct local update mode.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Omit for dry-run preview.")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    csv_text = read_csv_text(args)
    import_rows, parse_errors = parse_rows(csv_text)
    if parse_errors:
        print_preview([], parse_errors)
        return 1
    if not import_rows:
        print("No hay filas importables.")
        return 0

    if args.db:
        players = db_list_players(args.db)
        updater = lambda profile_id, happiness: db_update_happiness(args.db, profile_id, happiness)
    else:
        if not args.base_url or not args.username or not args.password:
            if args.base_url and args.username and not args.password:
                args.password = getpass.getpass("Admin password: ")
            else:
                print("API mode requiere --base-url y --username. La contraseña puede ir en --password, ANBA_ADMIN_PASSWORD o prompt.", file=sys.stderr)
                return 1
        client = ApiClient(args.base_url, args.username, args.password, args.timeout_seconds)
        client.login()
        players = client.list_players()
        updater = client.update_happiness

    resolved, resolve_errors = resolve_rows(import_rows, players)
    print_preview(resolved, resolve_errors)
    if resolve_errors:
        return 1
    if not args.apply:
        print("\nDry run. Repite el comando con --apply para actualizar.")
        return 0

    changed = 0
    for row in resolved:
        if row.current_happiness == row.next_happiness:
            continue
        updater(row.profile_id, row.next_happiness)
        changed += 1
    print(f"\nImport completado. Filas procesadas: {len(resolved)}. Cambios aplicados: {changed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
