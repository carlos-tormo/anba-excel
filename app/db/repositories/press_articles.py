"""SQLite persistence for press articles and their images."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

from .base import LeagueRepository


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class PressArticleRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        detect_image_type: Callable[[bytes, str, Optional[Dict[str, str]]], tuple[str, str]],
        allowed_mime_types: Dict[str, str],
        max_image_bytes: int,
        now: Callable[[], str] = _now_iso,
    ) -> None:
        super().__init__(db)
        self._detect_image_type = detect_image_type
        self._allowed_mime_types = allowed_mime_types
        self._max_image_bytes = max_image_bytes
        self._now = now

    @staticmethod
    def _plain_excerpt(text: Any, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: max(0, limit - 3)].rstrip()}..."

    def _payload(self, row: Any, *, include_body: bool = False) -> Dict[str, Any]:
        article = dict(row)
        image_mime = str(article.get("image_mime_type") or "").strip()
        article["has_image"] = bool(image_mime)
        article["image_url"] = f"/api/news/articles/{article['id']}/image" if image_mime else ""
        if not include_body:
            article.pop("body", None)
            article["excerpt"] = self._plain_excerpt(row["body"], 220)
        return article

    def create(
        self,
        body: str,
        image_bytes: bytes,
        image_mime_type: str,
        session: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        text = str(body or "").strip()
        if not text:
            raise ValueError("article_text_required")
        if not image_bytes or len(image_bytes) > self._max_image_bytes:
            raise ValueError("invalid_article_image")
        _extension, safe_mime = self._detect_image_type(
            image_bytes,
            image_mime_type,
            self._allowed_mime_types,
        )
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        title = self._plain_excerpt(first_line or "ANBA News", 140)
        timestamp = self._now()
        actor = session or {}
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO news_articles (
                    title, body, image_blob, image_mime_type,
                    created_by_email, created_by_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    text,
                    image_bytes,
                    safe_mime,
                    str(actor.get("email") or "").strip() or None,
                    str(actor.get("name") or "").strip() or None,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute("SELECT * FROM news_articles WHERE id = ?", (int(cur.lastrowid),)).fetchone()
            if not row:
                raise ValueError("article_create_failed")
            return self._payload(row, include_body=True)

    def update_discord(self, article_id: int, channel_id: str, message_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE news_articles
                SET discord_channel_id = ?, discord_message_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(channel_id or ""), str(message_id or ""), self._now(), int(article_id)),
            )

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 100))
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, body, image_mime_type, discord_channel_id,
                       discord_message_id, created_by_name, created_at, updated_at
                FROM news_articles
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            return [self._payload(row) for row in rows]

    def get(self, article_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, title, body, image_mime_type, discord_channel_id,
                       discord_message_id, created_by_name, created_at, updated_at
                FROM news_articles
                WHERE id = ?
                """,
                (int(article_id),),
            ).fetchone()
            return self._payload(row, include_body=True) if row else None

    def image(self, article_id: int) -> Optional[tuple[bytes, str]]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT image_blob, image_mime_type FROM news_articles WHERE id = ?",
                (int(article_id),),
            ).fetchone()
            if not row or not row["image_blob"] or not row["image_mime_type"]:
                return None
            image_bytes = bytes(row["image_blob"])
            try:
                _extension, safe_mime = self._detect_image_type(
                    image_bytes,
                    str(row["image_mime_type"]),
                    self._allowed_mime_types,
                )
            except ValueError:
                return None
            return image_bytes, safe_mime
