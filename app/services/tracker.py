"""League-wide cap tracker read model with lock-safe caching."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional

try:
    from ..domain_rules import parse_int
except ImportError:  # pragma: no cover
    from domain_rules import parse_int


@dataclass(frozen=True)
class TrackerOperations:
    select_players: Callable[..., List[Dict[str, Any]]]
    luxury_repeater: Callable[..., bool]
    hard_cap: Callable[..., str]
    calculate_summary: Callable[..., Dict[str, Any]]
    normalize_pick_type: Callable[[Any], str]
    get_cache: Callable[[Optional[int]], Optional[Dict[str, Any]]]
    set_cache: Callable[[int, Dict[str, Any]], None]
    is_lock_error: Callable[[BaseException], bool]


class TrackerService:
    def __init__(self, db: Any, operations: TrackerOperations, *, min_year: int, max_year: int) -> None:
        self._db = db
        self._operations = operations
        self._min_year = min_year
        self._max_year = max_year

    def list(self, season_year: Optional[int] = None, busy_timeout_ms: int = 5000) -> Dict[str, Any]:
        timings: Dict[str, float] = {}
        started = time.perf_counter()
        requested_year = parse_int(season_year)
        cache_lookup_year = requested_year

        def mark(label: str, since: float) -> float:
            current = time.perf_counter()
            timings[label] = round((current - since) * 1000, 2)
            return current

        try:
            with self._db.connect() as conn:
                if busy_timeout_ms is not None:
                    conn.execute(f"PRAGMA busy_timeout = {max(100, min(int(busy_timeout_ms), 15000))}")
                settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings")}
                checkpoint = mark("settings_ms", started)
                current_year = parse_int(settings.get("current_year")) or 2025
                if current_year < self._min_year or current_year > self._max_year:
                    current_year = self._min_year
                tracker_year = requested_year if requested_year is not None else current_year
                tracker_year = max(self._min_year, min(self._max_year, tracker_year))
                cache_lookup_year = tracker_year
                teams = [dict(row) for row in conn.execute("SELECT * FROM teams ORDER BY code").fetchall()]
                checkpoint = mark("teams_ms", checkpoint)
                result_rows: List[Dict[str, Any]] = []
                draft_year_start = current_year + 1

                def draft_counts(assets: List[Dict[str, Any]]) -> Dict[str, int]:
                    counts = {"draft_first_count": 0, "draft_second_count": 0}
                    for asset in assets:
                        if asset.get("asset_type") != "draft_pick" or self._operations.normalize_pick_type(asset.get("draft_pick_type")) == "sold":
                            continue
                        year = parse_int(asset.get("year"))
                        if year is not None and year < draft_year_start:
                            continue
                        round_text = str(asset.get("draft_round") or "").strip().lower()
                        if "2" in round_text:
                            key = "draft_second_count"
                        elif "1" in round_text:
                            key = "draft_first_count"
                        else:
                            label = str(asset.get("label") or "").strip().lower()
                            key = "draft_second_count" if "2" in label else "draft_first_count"
                        counts[key] += 1
                    return counts

                for team in teams:
                    team_id = int(team["id"])
                    team_code = str(team["code"])
                    team_started = time.perf_counter()
                    query_started = time.perf_counter()
                    players = self._operations.select_players(conn, team_id)
                    players_ms = round((time.perf_counter() - query_started) * 1000, 2)
                    query_started = time.perf_counter()
                    assets = [dict(row) for row in conn.execute(
                        "SELECT * FROM assets WHERE team_id = ? AND asset_type != 'dead_cap' ORDER BY asset_type, row_order, id",
                        (team_id,),
                    ).fetchall()]
                    assets_ms = round((time.perf_counter() - query_started) * 1000, 2)
                    query_started = time.perf_counter()
                    dead_contracts = [dict(row) for row in conn.execute(
                        "SELECT * FROM dead_contracts WHERE team_id = ? ORDER BY dead_type, row_order, id",
                        (team_id,),
                    ).fetchall()]
                    dead_ms = round((time.perf_counter() - query_started) * 1000, 2)
                    query_started = time.perf_counter()
                    luxury_repeater = self._operations.luxury_repeater(conn, team_id, tracker_year)
                    luxury_ms = round((time.perf_counter() - query_started) * 1000, 2)
                    query_started = time.perf_counter()
                    hard_cap = self._operations.hard_cap(
                        conn, team_id, tracker_year,
                        team.get("apron_hard_cap") if tracker_year == current_year else None,
                    )
                    hardcap_ms = round((time.perf_counter() - query_started) * 1000, 2)
                    summary_started = time.perf_counter()
                    summary = self._operations.calculate_summary(
                        team, players, assets, dead_contracts, settings,
                        season_year=tracker_year, luxury_repeater=luxury_repeater,
                        apron_hard_cap=hard_cap, include_breakdowns=False,
                    )
                    summary_ms = round((time.perf_counter() - summary_started) * 1000, 2)
                    counts = draft_counts(assets)
                    result_rows.append({
                        "team_code": team["code"], "team_name": team["name"],
                        "cap_total": float(summary["cap_figure"]), "gasto_total": float(summary["payroll"]),
                        "espacio_cap": float(summary["room_to_cap"]),
                        "espacio_luxury": float(summary["room_to_luxury"]),
                        "luxury_tax": float(summary["luxury_tax"]),
                        "espacio_1er_apron": float(summary["room_to_first_apron"]),
                        "espacio_2do_apron": float(summary["room_to_second_apron"]),
                        "roster_standard_count": int(summary["roster_standard_count"]),
                        "roster_two_way_count": int(summary["roster_two_way_count"]),
                        **counts, "apron_hard_cap": summary["apron_hard_cap"],
                    })
                    team_ms = round((time.perf_counter() - team_started) * 1000, 2)
                    timings[f"team_{team_code}_ms"] = team_ms
                    if team_ms >= 500:
                        print(
                            f"Tracker team slow {team_code} {team_ms:.2f}ms "
                            f"players_ms={players_ms},assets_ms={assets_ms},dead_ms={dead_ms},"
                            f"luxury_ms={luxury_ms},hardcap_ms={hardcap_ms},summary_ms={summary_ms}",
                            flush=True,
                        )
                mark("rows_ms", checkpoint)
                timings.update({"total_ms": round((time.perf_counter() - started) * 1000, 2), "row_count": float(len(result_rows))})
                setattr(self._db, "_last_tracker_timings", timings)
                result = {
                    "rows": result_rows, "season_year": tracker_year,
                    "seasons": [current_year + index for index in range(6)], "timings": timings,
                }
                self._operations.set_cache(tracker_year, result)
                return result
        except sqlite3.OperationalError as exc:
            if self._operations.is_lock_error(exc):
                cached = self._operations.get_cache(cache_lookup_year)
                if cached is not None:
                    print(f"Tracker served from cache after SQLite lock: {exc}", flush=True)
                    return cached
            raise
