"""SQLite persistence for site and offline GM identities."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from .base import LeagueRepository

EASTERN_CONFERENCE_TEAM_CODES = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL",
    "NYK", "ORL", "PHI", "TOR", "WAS",
}
WESTERN_CONFERENCE_TEAM_CODES = {
    "DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN", "NOP", "OKC",
    "PHX", "POR", "SAC", "SAS", "UTA",
}


def gm_display_name(row: Any) -> str:
    username = str(row["username"] or "").strip() if "username" in row.keys() else ""
    display_name = str(row["display_name"] or "").strip() if "display_name" in row.keys() else ""
    email = str(row["email"] or "").strip() if "email" in row.keys() else ""
    return username or display_name or email


def clean_gm_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def team_conference(team_code: Any) -> str:
    code = str(team_code or "").strip().upper()
    if code in EASTERN_CONFERENCE_TEAM_CODES:
        return "east"
    if code in WESTERN_CONFERENCE_TEAM_CODES:
        return "west"
    return "other"


def active_years_label(start_date: Any, end_date: Any = None) -> str:
    start = str(start_date or "").strip()[:4]
    end = str(end_date or "").strip()[:4]
    if not start:
        return end or ""
    if not end or end == start:
        return start
    return f"{start}-{end}"


def ensure_user_gm_identity(conn: Any, user_id: int, *, now: str) -> Optional[int]:
    row = conn.execute(
        "SELECT id, username, display_name, email FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if not row:
        return None
    name = gm_display_name(row)
    if not name:
        return None
    existing = conn.execute(
        "SELECT id FROM gm_identities WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE gm_identities
            SET entity_type = 'user',
                display_name = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (name, now, int(existing["id"])),
        )
        return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO gm_identities (
            entity_type, user_id, display_name, created_at, updated_at
        ) VALUES ('user', ?, ?, ?, ?)
        """,
        (int(user_id), name, now, now),
    )
    return int(cur.lastrowid)


def upsert_offline_gm_identity(conn: Any, name: Any, *, now: str) -> Optional[int]:
    display_name = clean_gm_name(name)
    if not display_name:
        return None
    existing = conn.execute(
        """
        SELECT id FROM gm_identities
        WHERE entity_type = 'offline' AND lower(display_name) = lower(?)
        ORDER BY id
        LIMIT 1
        """,
        (display_name,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE gm_identities SET display_name = ?, updated_at = ? WHERE id = ?",
            (display_name, now, int(existing["id"])),
        )
        return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO gm_identities (
            entity_type, user_id, display_name, created_at, updated_at
        ) VALUES ('offline', NULL, ?, ?, ?)
        """,
        (display_name, now, now),
    )
    return int(cur.lastrowid)


class GMIdentityRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str]) -> None:
        super().__init__(db)
        self._now = now

    def list(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            timestamp = self._now()
            for row in conn.execute("SELECT id FROM users ORDER BY id").fetchall():
                ensure_user_gm_identity(conn, int(row["id"]), now=timestamp)
            conn.commit()
            rows = conn.execute(
                """
                SELECT g.id, g.entity_type, g.user_id, g.display_name,
                       u.email, u.username, u.avatar_url,
                       COUNT(h.id) AS history_count,
                       MIN(h.start_date) AS first_start_date,
                       MAX(h.start_date) AS last_start_date
                FROM gm_identities g
                LEFT JOIN users u ON u.id = g.user_id
                LEFT JOIN team_gm_history h ON h.gm_entity_id = g.id
                GROUP BY g.id
                ORDER BY lower(g.display_name), g.id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def create_offline(self, name: Any) -> Dict[str, Any]:
        display_name = clean_gm_name(name)
        if not display_name:
            raise ValueError("gm_name_required")
        if len(display_name) > 120:
            raise ValueError("gm_name_too_long")
        timestamp = self._now()
        with self.db.connect() as conn:
            gm_id = upsert_offline_gm_identity(conn, display_name, now=timestamp)
            conn.commit()
        return next(row for row in self.list() if int(row["id"]) == int(gm_id))

    def list_profiles(self) -> List[Dict[str, Any]]:
        payload = self.directory()
        return payload["gms"]

    @staticmethod
    def _name_key(value: Any) -> str:
        return clean_gm_name(value).casefold()

    @staticmethod
    def _season_label(season_year: Any) -> str:
        try:
            year = int(season_year)
        except (TypeError, ValueError):
            return str(season_year or "").strip() or "Sin temporada"
        return f"{year}-{str(year + 1)[-2:]}"

    @staticmethod
    def _gm_timeline_cache(conn: Any) -> Dict[str, List[Dict[str, Any]]]:
        rows = conn.execute(
            """
            SELECT t.code AS team_code, h.gm_entity_id, h.gm_name, h.start_date,
                   h.row_order, h.id
            FROM team_gm_history h
            JOIN teams t ON t.id = h.team_id
            WHERE h.start_date IS NOT NULL AND trim(h.start_date) <> ''
            ORDER BY t.code, h.start_date, h.row_order, h.id
            """
        ).fetchall()
        cache: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            team_code = str(row["team_code"] or "").strip().upper()
            if not team_code:
                continue
            cache.setdefault(team_code, []).append(
                {
                    "gm_entity_id": int(row["gm_entity_id"]) if row["gm_entity_id"] is not None else None,
                    "gm_name": row["gm_name"],
                    "start_date": str(row["start_date"] or "").strip()[:10],
                }
            )
        return cache

    @staticmethod
    def _timeline_match(
        cache: Dict[str, List[Dict[str, Any]]],
        team_code: Any,
        target_date: Any,
    ) -> Optional[Dict[str, Any]]:
        code = str(team_code or "").strip().upper()
        date_key = str(target_date or "").strip()[:10]
        if not code or not date_key:
            return None
        match: Optional[Dict[str, Any]] = None
        for row in cache.get(code) or []:
            if str(row.get("start_date") or "") <= date_key:
                match = row
            else:
                break
        return match

    def profile(self, gm_id: Any) -> Optional[Dict[str, Any]]:
        try:
            normalized_gm_id = int(gm_id)
        except (TypeError, ValueError):
            return None
        with self.db.connect() as conn:
            identity = conn.execute(
                """
                SELECT g.id, g.entity_type, g.user_id, g.display_name, g.profile_slug,
                       g.notes, g.created_at, g.updated_at,
                       u.email, u.username, u.display_name AS user_display_name,
                       u.avatar_url, u.is_co_admin, u.created_at AS user_created_at
                FROM gm_identities g
                LEFT JOIN users u ON u.id = g.user_id
                WHERE g.id = ?
                """,
                (normalized_gm_id,),
            ).fetchone()
            if not identity:
                return None

            active_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT t.id AS team_id, t.code AS team_code, t.name AS team_name
                    FROM user_team_assignments a
                    JOIN users u ON u.id = a.user_id
                    JOIN gm_identities g ON g.user_id = u.id
                    JOIN teams t ON t.id = a.team_id
                    WHERE g.id = ?
                    ORDER BY t.code
                    """,
                    (normalized_gm_id,),
                ).fetchall()
            ]
            active_team_codes = {
                str(row.get("team_code") or "").strip().upper()
                for row in active_rows
                if row.get("team_code")
            }
            history_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT h.gm_entity_id, h.gm_name, h.start_date, h.color,
                           t.code AS team_code, t.name AS team_name,
                           (
                               SELECT h2.start_date
                               FROM team_gm_history h2
                               WHERE h2.team_id = h.team_id
                                 AND (
                                     h2.start_date > h.start_date
                                     OR (
                                         h2.start_date = h.start_date
                                         AND (
                                             h2.row_order > h.row_order
                                             OR (h2.row_order = h.row_order AND h2.id > h.id)
                                         )
                                     )
                                 )
                               ORDER BY h2.start_date, h2.row_order, h2.id
                               LIMIT 1
                           ) AS end_date
                    FROM team_gm_history h
                    JOIN teams t ON t.id = h.team_id
                    WHERE h.gm_entity_id = ?
                    ORDER BY h.start_date, h.row_order, h.id
                    """,
                    (normalized_gm_id,),
                ).fetchall()
            ]
            history: List[Dict[str, Any]] = []
            for row in history_rows:
                team_code = str(row.get("team_code") or "").strip().upper()
                end_date = row.get("end_date")
                history.append(
                    {
                        "team_code": row.get("team_code"),
                        "team_name": row.get("team_name"),
                        "gm_name": row.get("gm_name"),
                        "start_date": row.get("start_date"),
                        "end_date": end_date,
                        "is_current": bool(not end_date and team_code in active_team_codes),
                        "color": row.get("color"),
                    }
                )

            joined_date = None
            if history:
                joined_date = min(
                    (str(row.get("start_date") or "").strip()[:10] for row in history if row.get("start_date")),
                    default=None,
                )

            display_name = str(identity["display_name"] or "").strip()
            profile = {
                "id": normalized_gm_id,
                "gm_id": normalized_gm_id,
                "nick": display_name,
                "display_name": display_name,
                "entity_type": identity["entity_type"],
                "has_site_user": identity["user_id"] is not None,
                "user_id": identity["user_id"],
                "username": identity["username"],
                "avatar_url": identity["avatar_url"],
                "current_role": self._current_role(active_rows, bool(identity["is_co_admin"]), bool(history)),
                "joined_league_date": joined_date,
                "notes": identity["notes"],
                "history": history,
                "active_teams": active_rows,
            }
            profile["draft_picks"] = self._profile_draft_picks(conn, normalized_gm_id, display_name)
            profile["draft_pick_count"] = len(profile["draft_picks"])
            profile["trades"] = self._profile_trades(conn, normalized_gm_id, display_name)
            profile["trade_count"] = len(profile["trades"])
            profile["trades_by_season"] = self._group_trades_by_season(profile["trades"])
            return profile

    @staticmethod
    def _current_role(active_rows: List[Dict[str, Any]], is_co_admin: bool, has_history: bool) -> str:
        if active_rows:
            teams = ", ".join(str(row.get("team_code") or "").strip().upper() for row in active_rows if row.get("team_code"))
            return f"GM {teams}" if teams else "GM activo"
        if is_co_admin:
            return "Co-admin"
        if has_history:
            return "GM inactivo"
        return "GM"

    def _profile_draft_picks(self, conn: Any, gm_id: int, display_name: str) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT h.id, h.draft_year, h.pick_number, h.draft_round,
                   h.round_pick_number, h.player_name, h.selecting_team_code,
                   COALESCE(selecting.name, h.selecting_team_code) AS selecting_team_name,
                   h.original_team_code,
                   COALESCE(original.name, h.original_team_code) AS original_team_name,
                   h.selection_date, h.selecting_gm_source
            FROM draft_history_selections h
            LEFT JOIN teams selecting ON selecting.code = h.selecting_team_code
            LEFT JOIN teams original ON original.code = h.original_team_code
            WHERE h.selecting_gm_entity_id = ?
               OR lower(h.selecting_gm_name) = lower(?)
            ORDER BY h.draft_year DESC, h.pick_number
            """,
            (int(gm_id), display_name),
        ).fetchall()
        return [dict(row) for row in rows]

    def _profile_trades(self, conn: Any, gm_id: int, display_name: str) -> List[Dict[str, Any]]:
        timeline = self._gm_timeline_cache(conn)
        name_key = self._name_key(display_name)
        rows = conn.execute(
            """
            SELECT tr.id, tr.external_trade_id, tr.trade_date, tr.season_year,
                   tr.total_assets_moved, m.team_code, m.gm_name
            FROM trade_archive tr
            JOIN trade_archive_team_movements m ON m.trade_id = tr.id
            ORDER BY tr.trade_date DESC, tr.id DESC, m.team_code
            """
        ).fetchall()
        matched: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            explicit_name = clean_gm_name(row["gm_name"])
            explicit_match = bool(explicit_name and self._name_key(explicit_name) == name_key)
            timeline_match = self._timeline_match(timeline, row["team_code"], row["trade_date"])
            timeline_gm_id = timeline_match.get("gm_entity_id") if timeline_match else None
            if not explicit_match and timeline_gm_id != int(gm_id):
                continue
            trade_id = int(row["id"])
            entry = matched.setdefault(
                trade_id,
                {
                    "id": trade_id,
                    "trade_id": row["external_trade_id"] or str(trade_id),
                    "external_trade_id": row["external_trade_id"],
                    "trade_date": row["trade_date"],
                    "season_year": int(row["season_year"]),
                    "season_label": self._season_label(row["season_year"]),
                    "total_assets_moved": int(row["total_assets_moved"] or 0),
                    "teams": [],
                    "gm_team_codes": [],
                },
            )
            code = str(row["team_code"] or "").strip().upper()
            if code and code not in entry["gm_team_codes"]:
                entry["gm_team_codes"].append(code)
            if code and code not in entry["teams"]:
                entry["teams"].append(code)
        trades = list(matched.values())
        all_team_rows = conn.execute(
            """
            SELECT trade_id, team_code
            FROM trade_archive_team_movements
            WHERE trade_id IN (
                SELECT id FROM trade_archive
            )
            ORDER BY trade_id, team_code
            """
        ).fetchall()
        by_trade_id: Dict[int, List[str]] = {}
        for row in all_team_rows:
            trade_id = int(row["trade_id"])
            if trade_id not in matched:
                continue
            code = str(row["team_code"] or "").strip().upper()
            if code:
                by_trade_id.setdefault(trade_id, []).append(code)
        for trade in trades:
            trade["teams"] = by_trade_id.get(int(trade["id"]), trade["teams"])
        return sorted(trades, key=lambda row: (str(row.get("trade_date") or ""), int(row.get("id") or 0)), reverse=True)

    @staticmethod
    def _group_trades_by_season(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[int, Dict[str, Any]] = {}
        for trade in trades:
            season_year = int(trade.get("season_year") or 0)
            entry = grouped.setdefault(
                season_year,
                {
                    "season_year": season_year,
                    "season_label": GMIdentityRepository._season_label(season_year),
                    "trades": [],
                },
            )
            entry["trades"].append(trade)
        return [grouped[key] for key in sorted(grouped.keys(), reverse=True)]

    def directory(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            timestamp = self._now()
            for row in conn.execute("SELECT id FROM users ORDER BY id").fetchall():
                ensure_user_gm_identity(conn, int(row["id"]), now=timestamp)
            conn.commit()
            identities = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT g.id, g.entity_type, g.user_id, g.display_name,
                           CASE WHEN g.user_id IS NULL THEN 0 ELSE 1 END AS has_site_user
                    FROM gm_identities g
                    ORDER BY lower(g.display_name), g.id
                    """
                ).fetchall()
            ]
            history_rows = conn.execute(
                """
                SELECT h.gm_entity_id, h.gm_name, h.start_date, h.color,
                       t.code AS team_code, t.name AS team_name
                FROM team_gm_history h
                JOIN teams t ON t.id = h.team_id
                WHERE h.gm_entity_id IS NOT NULL
                ORDER BY h.start_date DESC, t.code, h.row_order, h.id
                """
            ).fetchall()
            histories: Dict[int, List[Dict[str, Any]]] = {}
            for row in history_rows:
                gm_id = int(row["gm_entity_id"])
                histories.setdefault(gm_id, []).append(
                    {
                        "team_code": row["team_code"],
                        "team_name": row["team_name"],
                        "gm_name": row["gm_name"],
                        "start_date": row["start_date"],
                        "color": row["color"],
                    }
                )
            for identity in identities:
                identity["has_site_user"] = bool(identity.get("has_site_user"))
                identity["history"] = histories.get(int(identity["id"]), [])
            active_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT g.id AS gm_id, g.display_name AS gm_name, g.entity_type,
                           u.id AS user_id, t.id AS team_id, t.code AS team_code, t.name AS team_name,
                           (
                               SELECT h.start_date
                               FROM team_gm_history h
                               WHERE h.team_id = t.id AND h.gm_entity_id = g.id
                               ORDER BY h.start_date DESC, h.row_order DESC, h.id DESC
                               LIMIT 1
                           ) AS since_date
                    FROM user_team_assignments a
                    JOIN users u ON u.id = a.user_id
                    JOIN gm_identities g ON g.user_id = u.id
                    JOIN teams t ON t.id = a.team_id
                    ORDER BY t.code, lower(g.display_name), g.id
                    """
                ).fetchall()
            ]
            active_gm_ids = {int(row["gm_id"]) for row in active_rows}
            active_by_conference: Dict[str, List[Dict[str, Any]]] = {"east": [], "west": [], "other": []}
            for row in active_rows:
                entry = {
                    "gm_id": int(row["gm_id"]),
                    "gm_name": row["gm_name"],
                    "entity_type": row["entity_type"],
                    "has_site_user": True,
                    "team_id": int(row["team_id"]),
                    "team_code": row["team_code"],
                    "team_name": row["team_name"],
                    "conference": team_conference(row["team_code"]),
                    "since_date": row["since_date"],
                    "since_year": str(row["since_date"] or "").strip()[:4],
                }
                active_by_conference[entry["conference"]].append(entry)

            inactive_gms: List[Dict[str, Any]] = []
            for identity in identities:
                gm_id = int(identity["id"])
                history = histories.get(gm_id, [])
                if gm_id in active_gm_ids or not history:
                    continue
                years = [
                    str(row.get("start_date") or "").strip()[:4]
                    for row in history
                    if str(row.get("start_date") or "").strip()[:4]
                ]
                teams = sorted({
                    str(row.get("team_code") or "").strip().upper()
                    for row in history
                    if str(row.get("team_code") or "").strip()
                })
                inactive_gms.append(
                    {
                        "gm_id": gm_id,
                        "gm_name": identity["display_name"],
                        "entity_type": identity["entity_type"],
                        "has_site_user": bool(identity.get("has_site_user")),
                        "years_active": active_years_label(min(years) if years else "", max(years) if years else ""),
                        "teams": teams,
                        "history": history,
                    }
                )
            inactive_gms.sort(key=lambda row: (str(row.get("gm_name") or "").casefold(), int(row.get("gm_id") or 0)))
            return {
                "gms": identities,
                "active_gms": active_by_conference,
                "inactive_gms": inactive_gms,
            }
