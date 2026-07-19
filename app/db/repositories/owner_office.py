"""Owner-office exit interview and background-media persistence."""

from __future__ import annotations

import secrets
import sqlite3
from typing import Any, Callable, Dict, Optional

try:
    from ...domain_rules import parse_int
except ImportError:  # pragma: no cover
    from domain_rules import parse_int

from .base import LeagueRepository


class OwnerOfficeRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        exit_from_row: Callable[[Any], Optional[Dict[str, Any]]],
        confidence_delta: Callable[[Any, int], Optional[str]],
        get_owner_office: Callable[..., Optional[Dict[str, Any]]],
        sanitize_background_url: Callable[[Any], str],
        detect_image_type: Callable[..., Any],
        allowed_mime_types: Any,
        background_max_bytes: int,
    ) -> None:
        super().__init__(db)
        self._now = now
        self._exit_from_row = exit_from_row
        self._confidence_delta = confidence_delta
        self._get_owner_office = get_owner_office
        self._sanitize_background_url = sanitize_background_url
        self._detect_image_type = detect_image_type
        self._allowed_mime_types = allowed_mime_types
        self._background_max_bytes = background_max_bytes

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

    def update_owner_background_url(self, code: str, background_url: str) -> Optional[Dict[str, Any]]:
            safe_background_url = self._sanitize_background_url(background_url)
            with self.db.connect() as conn:
                team = conn.execute("SELECT id FROM teams WHERE code = ?", (code.upper(),)).fetchone()
                if not team:
                    return None
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
            return self._get_owner_office(code, include_private=True)

    def update_owner_background_image(self, code: str, file_bytes: bytes, mime_type: str) -> Optional[Dict[str, Any]]:
            normalized_code = code.upper()
            if not file_bytes:
                raise ValueError("missing_upload")
            if len(file_bytes) > self._background_max_bytes:
                raise ValueError("upload_too_large")
            _ext, safe_mime_type = self._detect_image_type(file_bytes, mime_type, self._allowed_mime_types)
            with self.db.connect() as conn:
                team = conn.execute("SELECT id FROM teams WHERE code = ?", (normalized_code,)).fetchone()
                if not team:
                    return None
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
            return self._get_owner_office(normalized_code, include_private=True)

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
                    _ext, safe_mime_type = self._detect_image_type(image_bytes, mime_type, self._allowed_mime_types)
                except ValueError:
                    return None
                return image_bytes, safe_mime_type

