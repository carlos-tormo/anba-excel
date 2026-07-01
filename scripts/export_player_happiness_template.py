#!/usr/bin/env python3
"""Export a CSV template with player profile IDs for happiness imports.

The generated CSV can be edited in Google Sheets and then fed back into
`scripts/import_player_happiness.py`. Extra context columns are included for
humans; the importer only needs `profile_id`, `player_name`, and `felicidad`.

Examples:

    python3 scripts/export_player_happiness_template.py \
      --base-url https://anba-excel-production.up.railway.app \
      --username "$ANBA_ADMIN_USER" \
      --output /Users/carlos.tormo/Downloads/felicidad_template.csv

    python3 scripts/export_player_happiness_template.py \
      --db data/league.db \
      --output /Users/carlos.tormo/Downloads/felicidad_template.csv
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from import_player_happiness import ApiClient, parse_int


EXPORT_COLUMNS = [
    "profile_id",
    "player_name",
    "felicidad",
    "status",
    "team_code",
    "position",
    "rating",
    "active_contract_summary",
]


def db_list_players_with_context(db_path: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        profile_cols = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(player_profiles)").fetchall()
        }
        happiness_expr = "pp.happiness" if "happiness" in profile_cols else "0 AS happiness"
        rows = conn.execute(
            f"""
            SELECT
                pp.id AS profile_id,
                pp.name AS name,
                {happiness_expr},
                CASE
                    WHEN p.id IS NOT NULL THEN 'active'
                    WHEN f.id IS NOT NULL THEN 'free_agent'
                    WHEN d.id IS NOT NULL THEN 'dead_contract'
                    ELSE 'inactive'
                END AS status,
                t.code AS team_code,
                COALESCE(p.position, f.position) AS position,
                COALESCE(p.rating, f.rating) AS rating,
                CASE WHEN p.id IS NOT NULL THEN 'Sí' ELSE 'No' END AS active_contract_summary
            FROM player_profiles pp
            LEFT JOIN players p ON p.profile_id = pp.id
            LEFT JOIN teams t ON t.id = p.team_id
            LEFT JOIN free_agents f ON f.profile_id = pp.id
            LEFT JOIN dead_contracts d ON d.profile_id = pp.id
            GROUP BY pp.id
            ORDER BY pp.name COLLATE NOCASE, pp.id
            """
        ).fetchall()
        return [dict(row) for row in rows]


def player_to_export_row(player: Dict[str, Any]) -> Dict[str, Any]:
    profile_id = parse_int(player.get("profile_id") or player.get("id"))
    return {
        "profile_id": profile_id or "",
        "player_name": player.get("name") or player.get("player_name") or "",
        "felicidad": player.get("happiness") if player.get("happiness") is not None else 0,
        "status": player.get("status") or "",
        "team_code": player.get("team_code") or "",
        "position": player.get("position") or "",
        "rating": player.get("rating") or "",
        "active_contract_summary": player.get("active_contract_summary") or "",
    }


def write_csv(rows: List[Dict[str, Any]], output: Optional[str]) -> None:
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w", encoding="utf-8-sig", newline="")
        should_close = True
    else:
        handle = sys.stdout
        should_close = False
    try:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(player_to_export_row(row))
    finally:
        if should_close:
            handle.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export player profile IDs for happiness import templates.")
    target = parser.add_argument_group("source")
    target.add_argument("--base-url", default=os.getenv("ANBA_BASE_URL", ""), help="Site URL for API mode.")
    target.add_argument("--username", default=os.getenv("ANBA_ADMIN_USER", ""), help="Admin username for API mode.")
    target.add_argument("--password", default=os.getenv("ANBA_ADMIN_PASSWORD", ""), help="Admin password for API mode.")
    target.add_argument("--db", help="SQLite DB path for direct local export mode.")
    parser.add_argument("--output", help="CSV output path. Omit to print to stdout.")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.db:
        players = db_list_players_with_context(args.db)
    else:
        if not args.base_url or not args.username:
            print("API mode requiere --base-url y --username, o sus variables ANBA_*.", file=sys.stderr)
            return 1
        if not args.password:
            args.password = getpass.getpass("Admin password: ")
        client = ApiClient(args.base_url, args.username, args.password, args.timeout_seconds)
        client.login()
        players = client.list_players()
    rows = sorted(players, key=lambda item: (str(item.get("name") or "").casefold(), parse_int(item.get("profile_id")) or 0))
    write_csv(rows, args.output)
    if args.output:
        print(f"Export completado: {args.output} ({len(rows)} jugadores)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
