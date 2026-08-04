"""Persistence for standardized GM attractiveness rankings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from ...domain._values import parse_float, parse_int
    from ...domain.gm_attractiveness import (
        RANKING_BAND_NEUTRAL,
        normalize_ranking_band,
        standardized_ranking,
    )
except ImportError:  # pragma: no cover
    from domain._values import parse_float, parse_int
    from domain.gm_attractiveness import (
        RANKING_BAND_NEUTRAL,
        normalize_ranking_band,
        standardized_ranking,
    )

from .base import LeagueRepository


class GMAttractivenessRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Any) -> None:
        super().__init__(db)
        self._now = now

    def _ranking_from_row(self, conn: Any, row: Any) -> Dict[str, Any]:
        ranking = dict(row)
        ranking["id"] = int(ranking["id"])
        ranking["source_vote_id"] = parse_int(ranking.get("source_vote_id"))
        ranking["published_by_user_id"] = parse_int(ranking.get("published_by_user_id"))
        ranking["entries"] = self._entries_for_ranking(conn, int(ranking["id"]))
        return ranking

    def _entry_from_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["id"] = int(item["id"])
        item["ranking_id"] = int(item["ranking_id"])
        item["gm_entity_id"] = parse_int(item.get("gm_entity_id"))
        item["team_id"] = parse_int(item.get("team_id"))
        item["raw_average"] = parse_float(item.get("raw_average"))
        item["standardized_score"] = float(item.get("standardized_score") or 0.0)
        item["vote_count"] = int(item.get("vote_count") or 0)
        item["rank_position"] = int(item.get("rank_position") or 0)
        item["band"] = normalize_ranking_band(item.get("band"))
        item["manual_override"] = bool(item.get("manual_override"))
        return item

    def _entries_for_ranking(self, conn: Any, ranking_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM gm_attractiveness_ranking_entries
            WHERE ranking_id = ?
            ORDER BY rank_position, lower(gm_name), id
            """,
            (int(ranking_id),),
        ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def active(self) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM gm_attractiveness_rankings
                WHERE status = 'active'
                ORDER BY datetime(published_at) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            return self._ranking_from_row(conn, row) if row else None

    def entry_for_gm(self, gm_entity_id: Any) -> Optional[Dict[str, Any]]:
        parsed_gm_entity_id = parse_int(gm_entity_id)
        if parsed_gm_entity_id is None:
            return None
        with self.db.connect() as conn:
            ranking = conn.execute(
                """
                SELECT id
                FROM gm_attractiveness_rankings
                WHERE status = 'active'
                ORDER BY datetime(published_at) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if not ranking:
                return None
            row = conn.execute(
                """
                SELECT *
                FROM gm_attractiveness_ranking_entries
                WHERE ranking_id = ? AND gm_entity_id = ?
                """,
                (int(ranking["id"]), int(parsed_gm_entity_id)),
            ).fetchone()
            return self._entry_from_row(row) if row else None

    def active_bands_for_gms(self, gm_entity_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        normalized_ids = sorted({int(value) for value in gm_entity_ids if parse_int(value) is not None})
        if not normalized_ids:
            return {}
        with self.db.connect() as conn:
            ranking = conn.execute(
                """
                SELECT id
                FROM gm_attractiveness_rankings
                WHERE status = 'active'
                ORDER BY datetime(published_at) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if not ranking:
                return {}
            placeholders = ",".join("?" for _ in normalized_ids)
            rows = conn.execute(
                f"""
                SELECT *
                FROM gm_attractiveness_ranking_entries
                WHERE ranking_id = ? AND gm_entity_id IN ({placeholders})
                """,
                (int(ranking["id"]), *normalized_ids),
            ).fetchall()
            return {
                int(row["gm_entity_id"]): self._entry_from_row(row)
                for row in rows
                if parse_int(row["gm_entity_id"]) is not None
            }

    @staticmethod
    def _current_gm_for_team_conn(conn: Any, team_id: int) -> Optional[Dict[str, Any]]:
        assigned = conn.execute(
            """
            SELECT
                g.id AS gm_entity_id,
                COALESCE(NULLIF(TRIM(g.display_name), ''), NULLIF(TRIM(u.username), ''),
                         NULLIF(TRIM(u.display_name), ''), u.email) AS gm_name
            FROM user_team_assignments a
            JOIN users u ON u.id = a.user_id
            JOIN gm_identities g ON g.user_id = u.id
            WHERE a.team_id = ?
            ORDER BY datetime(a.created_at), a.user_id
            LIMIT 1
            """,
            (int(team_id),),
        ).fetchone()
        if assigned and parse_int(assigned["gm_entity_id"]) is not None:
            return {
                "gm_entity_id": int(assigned["gm_entity_id"]),
                "gm_name": str(assigned["gm_name"] or "").strip(),
            }
        historical = conn.execute(
            """
            SELECT gm_entity_id, gm_name
            FROM team_gm_history
            WHERE team_id = ? AND gm_entity_id IS NOT NULL
            ORDER BY date(start_date) DESC, row_order DESC, id DESC
            LIMIT 1
            """,
            (int(team_id),),
        ).fetchone()
        if historical and parse_int(historical["gm_entity_id"]) is not None:
            return {
                "gm_entity_id": int(historical["gm_entity_id"]),
                "gm_name": str(historical["gm_name"] or "").strip(),
            }
        return None

    def _vote_score_rows(self, conn: Any, vote_id: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        rows = conn.execute(
            """
            SELECT
                s.voter_user_id,
                s.score,
                t.id AS target_team_id,
                t.code AS target_team_code,
                t.name AS target_team_name
            FROM coadmin_vote_scores s
            JOIN teams t ON t.id = s.target_team_id
            WHERE s.vote_id = ?
            ORDER BY s.voter_user_id, t.code
            """,
            (int(vote_id),),
        ).fetchall()
        score_rows: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        team_cache: Dict[int, Optional[Dict[str, Any]]] = {}
        for row in rows:
            team_id = int(row["target_team_id"])
            if team_id not in team_cache:
                team_cache[team_id] = self._current_gm_for_team_conn(conn, team_id)
            gm = team_cache[team_id]
            if not gm:
                skipped.append(
                    {
                        "team_id": team_id,
                        "team_code": row["target_team_code"],
                        "reason": "gm_entity_not_found",
                    }
                )
                continue
            score_rows.append(
                {
                    "voter_user_id": int(row["voter_user_id"]),
                    "target_id": int(gm["gm_entity_id"]),
                    "target_name": gm["gm_name"],
                    "score": int(row["score"]),
                    "team_id": team_id,
                    "team_code": row["target_team_code"],
                    "team_name": row["target_team_name"],
                }
            )
        return score_rows, skipped

    def publish_from_vote(self, vote_id: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self.db.transaction("IMMEDIATE") as conn:
            return self.publish_from_vote_conn(conn, vote_id, actor)

    def publish_from_vote_conn(self, conn: Any, vote_id: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        parsed_vote_id = parse_int(vote_id)
        if parsed_vote_id is None:
            raise ValueError("invalid_vote_id")
        actor_user_id = parse_int((actor or {}).get("user_id"))
        timestamp = self._now()
        vote = conn.execute("SELECT id, title, status FROM coadmin_votes WHERE id = ?", (int(parsed_vote_id),)).fetchone()
        if not vote:
            raise ValueError("vote_not_found")
        score_rows, skipped = self._vote_score_rows(conn, int(parsed_vote_id))
        ranking_entries = standardized_ranking(score_rows)
        conn.execute(
            """
            UPDATE gm_attractiveness_rankings
            SET status = 'archived', updated_at = ?
            WHERE status = 'active'
            """,
            (timestamp,),
        )
        cur = conn.execute(
            """
            INSERT INTO gm_attractiveness_rankings (
                source_vote_id, status, title, published_at, published_by_user_id, created_at, updated_at
            ) VALUES (?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                int(parsed_vote_id),
                str(vote["title"] or "").strip() or None,
                timestamp,
                actor_user_id,
                timestamp,
                timestamp,
            ),
        )
        ranking_id = int(cur.lastrowid)
        first_team_by_gm: Dict[int, Dict[str, Any]] = {}
        for row in score_rows:
            gm_id = int(row["target_id"])
            first_team_by_gm.setdefault(
                gm_id,
                {
                    "team_id": row.get("team_id"),
                    "team_code": row.get("team_code"),
                    "team_name": row.get("team_name"),
                },
            )
        for entry in ranking_entries:
            team = first_team_by_gm.get(int(entry.target_id), {})
            conn.execute(
                """
                INSERT INTO gm_attractiveness_ranking_entries (
                    ranking_id, gm_entity_id, gm_name, team_id, team_code, team_name,
                    raw_average, standardized_score, vote_count, rank_position, band,
                    manual_override, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    ranking_id,
                    int(entry.target_id),
                    entry.target_name,
                    parse_int(team.get("team_id")),
                    team.get("team_code"),
                    team.get("team_name"),
                    entry.raw_average,
                    entry.standardized_score,
                    entry.vote_count,
                    entry.rank_position,
                    entry.band,
                    timestamp,
                    timestamp,
                ),
            )
        ranking = self._ranking_from_row(conn, conn.execute("SELECT * FROM gm_attractiveness_rankings WHERE id = ?", (ranking_id,)).fetchone())
        ranking["skipped_targets"] = skipped
        return ranking

    def _rerank_conn(self, conn: Any, ranking_id: int, timestamp: str) -> None:
        rows = conn.execute(
            """
            SELECT id, raw_average, standardized_score, gm_name, gm_entity_id
            FROM gm_attractiveness_ranking_entries
            WHERE ranking_id = ?
            ORDER BY standardized_score DESC,
                     COALESCE(raw_average, -999999) DESC,
                     lower(gm_name),
                     gm_entity_id
            """,
            (int(ranking_id),),
        ).fetchall()
        total = len(rows)
        for index, row in enumerate(rows, start=1):
            band = RANKING_BAND_NEUTRAL
            if index <= 5:
                band = "top5"
            elif total > 5 and index > max(total - 5, 5):
                band = "bottom5"
            conn.execute(
                """
                UPDATE gm_attractiveness_ranking_entries
                SET rank_position = ?, band = ?, updated_at = ?
                WHERE id = ?
                """,
                (index, band, timestamp, int(row["id"])),
            )

    def update_active_entry(
        self,
        gm_entity_id: Any,
        payload: Dict[str, Any],
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        parsed_gm_entity_id = parse_int(gm_entity_id)
        if parsed_gm_entity_id is None:
            raise ValueError("invalid_gm_entity_id")
        updates: List[str] = []
        values: List[Any] = []
        if "standardized_score" in payload:
            standardized_score = parse_float(payload.get("standardized_score"))
            if standardized_score is None:
                raise ValueError("invalid_standardized_score")
            updates.append("standardized_score = ?")
            values.append(float(standardized_score))
        if "raw_average" in payload:
            raw_average = parse_float(payload.get("raw_average"))
            updates.append("raw_average = ?")
            values.append(raw_average)
        if "gm_name" in payload:
            gm_name = str(payload.get("gm_name") or "").strip()
            if not gm_name:
                raise ValueError("invalid_gm_name")
            updates.append("gm_name = ?")
            values.append(gm_name)
        if not updates:
            raise ValueError("no_ranking_fields")
        timestamp = self._now()
        with self.db.transaction("IMMEDIATE") as conn:
            ranking = conn.execute(
                """
                SELECT id
                FROM gm_attractiveness_rankings
                WHERE status = 'active'
                ORDER BY datetime(published_at) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if not ranking:
                return None
            entry = conn.execute(
                """
                SELECT id
                FROM gm_attractiveness_ranking_entries
                WHERE ranking_id = ? AND gm_entity_id = ?
                """,
                (int(ranking["id"]), int(parsed_gm_entity_id)),
            ).fetchone()
            if not entry:
                return None
            updates.extend(["manual_override = 1", "updated_at = ?"])
            values.append(timestamp)
            conn.execute(
                f"UPDATE gm_attractiveness_ranking_entries SET {', '.join(updates)} WHERE id = ?",
                (*values, int(entry["id"])),
            )
            self._rerank_conn(conn, int(ranking["id"]), timestamp)
            conn.execute("UPDATE gm_attractiveness_rankings SET updated_at = ? WHERE id = ?", (timestamp, int(ranking["id"])))
            refreshed = self._ranking_from_row(
                conn,
                conn.execute("SELECT * FROM gm_attractiveness_rankings WHERE id = ?", (int(ranking["id"]),)).fetchone(),
            )
            return refreshed
