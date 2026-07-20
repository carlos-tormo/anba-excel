"""Owner-office exit interview and background-media persistence."""

from __future__ import annotations

from contextlib import contextmanager
import secrets
import sqlite3
from typing import Any, Callable, Dict, Iterator, List, Optional

try:
    from ...domain_rules import parse_float, parse_int
    from ...integrations.media import detect_safe_image_type, sanitize_owner_background_url
except ImportError:  # pragma: no cover
    from domain_rules import parse_float, parse_int
    from integrations.media import detect_safe_image_type, sanitize_owner_background_url

from .base import LeagueRepository


class OwnerOfficeRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        allowed_mime_types: Any,
        background_max_bytes: int,
    ) -> None:
        super().__init__(db)
        self._now = now
        self._allowed_mime_types = allowed_mime_types
        self._background_max_bytes = background_max_bytes

    @staticmethod
    def _exit_from_row(row: Any) -> Optional[Dict[str, Any]]:
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

    @staticmethod
    def _confidence_delta(value: Any, delta: int) -> Optional[str]:
        parsed = parse_float(str(value) if value is not None else None)
        if parsed is None:
            return None
        updated = parsed + int(delta)
        if float(updated).is_integer():
            return str(int(updated))
        return f"{updated:g}"

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.db.connect() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def team(conn: Any, code: str) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            "SELECT id, code, name FROM teams WHERE code = ?",
            (code.upper(),),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def settings(conn: Any) -> Dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM app_settings").fetchall()
        }

    @staticmethod
    def profile(conn: Any, team_id: int) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            "SELECT * FROM team_owner_profiles WHERE team_id = ?",
            (team_id,),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def office_rows(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM team_owner_office WHERE team_id = ? ORDER BY season_year",
                (team_id,),
            ).fetchall()
        ]

    @staticmethod
    def exit_interview_rows(conn: Any, team_id: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM owner_exit_interviews WHERE team_id = ?",
                (team_id,),
            ).fetchall()
        ]

    @staticmethod
    def economy_years(conn: Any) -> List[int]:
        return [
            int(row["season_year"])
            for row in conn.execute("SELECT DISTINCT season_year FROM team_economy").fetchall()
        ]

    @staticmethod
    def economy(conn: Any, team_id: int, season_year: int) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            """
            SELECT COALESCE(balance, 0) AS balance,
                   COALESCE(revenue, 0) AS revenue,
                   COALESCE(expenses, 0) AS expenses
            FROM team_economy
            WHERE team_id = ? AND season_year = ?
            """,
            (team_id, season_year),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def balance_ranking(conn: Any, season_year: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT t.id, COALESCE(e.balance, 0) AS balance
                FROM teams t
                LEFT JOIN team_economy e
                  ON e.team_id = t.id AND e.season_year = ?
                ORDER BY COALESCE(e.balance, 0) DESC, t.code ASC
                """,
                (season_year,),
            ).fetchall()
        ]

    @staticmethod
    def confidence_ranking(conn: Any, season_year: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT t.id, t.code, o.confidence_current
                FROM teams t
                JOIN team_owner_office o
                  ON o.team_id = t.id AND o.season_year = ?
                WHERE TRIM(COALESCE(o.confidence_current, '')) <> ''
                """,
                (season_year,),
            ).fetchall()
        ]

    @staticmethod
    def upsert_profile(conn: Any, team_id: int, profile: Dict[str, Any], updated_at: str) -> None:
        conn.execute(
            """
            INSERT INTO team_owner_profiles (
                team_id, owner_name, owner_birth_date, owner_photo_url, owner_bio,
                ambicion_competitiva, paciencia, intervencionismo,
                orientacion_financiera, orientacion_marca, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                owner_name = excluded.owner_name,
                owner_birth_date = excluded.owner_birth_date,
                owner_photo_url = excluded.owner_photo_url,
                owner_bio = excluded.owner_bio,
                ambicion_competitiva = excluded.ambicion_competitiva,
                paciencia = excluded.paciencia,
                intervencionismo = excluded.intervencionismo,
                orientacion_financiera = excluded.orientacion_financiera,
                orientacion_marca = excluded.orientacion_marca,
                updated_at = excluded.updated_at
            """,
            (
                team_id,
                profile["owner_name"],
                profile["owner_birth_date"],
                profile["owner_photo_url"],
                profile["owner_bio"],
                profile["ambicion_competitiva"],
                profile["paciencia"],
                profile["intervencionismo"],
                profile["orientacion_financiera"],
                profile["orientacion_marca"],
                updated_at,
            ),
        )

    @staticmethod
    def upsert_office_entry(conn: Any, entry: Dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO team_owner_office (
                team_id, season_year, confidence_current, confidence_change,
                new_gm_after_dismissal, gm_midseason_arrival, season_goal_set,
                season_goal_achieved, revenue, expenses, balance, income_json,
                expenses_json, performance_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, season_year) DO UPDATE SET
                confidence_current = excluded.confidence_current,
                confidence_change = excluded.confidence_change,
                new_gm_after_dismissal = excluded.new_gm_after_dismissal,
                gm_midseason_arrival = excluded.gm_midseason_arrival,
                season_goal_set = excluded.season_goal_set,
                season_goal_achieved = excluded.season_goal_achieved,
                revenue = excluded.revenue,
                expenses = excluded.expenses,
                balance = excluded.balance,
                income_json = excluded.income_json,
                expenses_json = excluded.expenses_json,
                performance_json = excluded.performance_json,
                updated_at = excluded.updated_at
            """,
            (
                entry["team_id"], entry["season_year"], entry["confidence_current"],
                entry["confidence_change"], entry["new_gm_after_dismissal"],
                entry["gm_midseason_arrival"], entry["season_goal_set"],
                entry["season_goal_achieved"], entry["revenue"], entry["expenses"],
                entry["balance"], entry["income_json"], entry["expenses_json"],
                entry["performance_json"], entry["updated_at"],
            ),
        )

    def get_owner_exit_interview(self, code: str, season_year: int) -> Optional[Dict[str, Any]]:
            with self.db.connect() as conn:
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
                return self._exit_from_row(row)

    def start_owner_exit_interview(
            self,
            code: str,
            season_year: int,
            session: Dict[str, Any],
            owner_message: str,
        ) -> Optional[Dict[str, Any]]:
            timestamp = self._now()
            with self.db.connect() as conn:
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
                    return self._exit_from_row(existing)
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
                return self._exit_from_row(row)

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
            timestamp = self._now()
            with self.db.connect() as conn:
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
                    return self._exit_from_row(row)
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
                updated_confidence = self._confidence_delta(
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
                return self._exit_from_row(updated)

    def reset_owner_exit_interview(self, code: str, season_year: int) -> bool:
            timestamp = self._now()
            with self.db.connect() as conn:
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
                        reverted_confidence = self._confidence_delta(
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

    def update_owner_background_url(self, code: str, background_url: str) -> bool:
            safe_background_url = sanitize_owner_background_url(background_url)
            with self.db.connect() as conn:
                team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
                if not team:
                    return False
                timestamp = self._now()
                conn.execute(
                    """
                    INSERT INTO team_owner_profiles (
                        team_id,
                        owner_office_background_url,
                        updated_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(team_id) DO UPDATE SET
                        owner_office_background_url = excluded.owner_office_background_url,
                        updated_at = excluded.updated_at
                    """,
                    (int(team["id"]), safe_background_url, timestamp),
                )
                conn.commit()
            return True

    def update_owner_background_image(self, code: str, file_bytes: bytes, mime_type: str) -> bool:
            normalized_code = code.upper()
            if not file_bytes:
                raise ValueError("missing_upload")
            if len(file_bytes) > self._background_max_bytes:
                raise ValueError("upload_too_large")
            _ext, safe_mime_type = detect_safe_image_type(file_bytes, mime_type, self._allowed_mime_types)
            with self.db.connect() as conn:
                team = conn.execute("SELECT id FROM teams WHERE code = ?", (normalized_code,)).fetchone()
                if not team:
                    return False
                timestamp = self._now()
                cache_key = secrets.token_urlsafe(12)
                background_url = f"/api/teams/{normalized_code}/owner-office/background-image?v={cache_key}"
                conn.execute(
                    """
                    INSERT INTO team_owner_profiles (
                        team_id,
                        owner_office_background_url,
                        owner_office_background_blob,
                        owner_office_background_mime,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(team_id) DO UPDATE SET
                        owner_office_background_url = excluded.owner_office_background_url,
                        owner_office_background_blob = excluded.owner_office_background_blob,
                        owner_office_background_mime = excluded.owner_office_background_mime,
                        updated_at = excluded.updated_at
                    """,
                    (int(team["id"]), background_url, sqlite3.Binary(file_bytes), safe_mime_type, timestamp),
                )
                conn.commit()
            return True

    def get_owner_background_image(self, code: str) -> Optional[tuple[bytes, str]]:
            with self.db.connect() as conn:
                row = conn.execute(
                    """
                    SELECT p.owner_office_background_blob AS image_blob,
                           p.owner_office_background_mime AS mime_type
                    FROM team_owner_profiles p
                    JOIN teams t ON t.id = p.team_id
                    WHERE t.code = ?
                    """,
                    (code.upper(),),
                ).fetchone()
                if not row or row["image_blob"] is None:
                    return None
                image_bytes = bytes(row["image_blob"])
                mime_type = str(row["mime_type"] or "application/octet-stream")
                if not image_bytes:
                    return None
                try:
                    _ext, safe_mime_type = detect_safe_image_type(image_bytes, mime_type, self._allowed_mime_types)
                except ValueError:
                    return None
                return image_bytes, safe_mime_type
