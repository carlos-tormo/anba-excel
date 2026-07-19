import sqlite3
import unittest

from app.db.repositories.notifications import NotificationRepository
from app.db.repositories.press_articles import PressArticleRepository


class _MemoryDB:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

    def connect(self) -> sqlite3.Connection:
        return self.connection


class ContentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _MemoryDB()
        self.db.connection.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            CREATE TABLE user_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT,
                title TEXT,
                body TEXT,
                kind TEXT,
                entity_type TEXT,
                entity_id TEXT,
                read_at TEXT,
                created_at TEXT
            );
            CREATE TABLE news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                body TEXT,
                image_blob BLOB,
                image_mime_type TEXT,
                discord_channel_id TEXT,
                discord_message_id TEXT,
                created_by_email TEXT,
                created_by_name TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            """
        )
        self.db.connection.execute("INSERT INTO users (id) VALUES (7)")

    def tearDown(self) -> None:
        self.db.connection.close()

    def test_notifications_are_idempotent_per_unread_entity_and_session_scoped(self) -> None:
        repository = NotificationRepository(self.db, now=lambda: "2026-07-19T10:00:00+00:00")
        notification = {
            "user_id": 7,
            "email": "gm@example.com",
            "title": "Offer rejected",
            "entity_type": "offer",
            "entity_id": 12,
        }

        first_id = repository.create(**notification)
        second_id = repository.create(**notification)

        self.assertEqual(first_id, second_id)
        self.assertEqual(1, len(repository.list_for_session({"user_id": 7})))
        self.assertEqual([], repository.list_for_session({"email": "other@example.com"}))
        self.assertTrue(repository.mark_read(int(first_id), {"email": "gm@example.com"}))
        self.assertEqual([], repository.list_for_session({"user_id": 7}))

    def test_press_articles_own_image_validation_and_payload_mapping(self) -> None:
        image_bytes = b"safe-image"
        repository = PressArticleRepository(
            self.db,
            detect_image_type=lambda data, declared, allowed: ("png", "image/png"),
            allowed_mime_types={"image/png": "png"},
            max_image_bytes=100,
            now=lambda: "2026-07-19T10:00:00+00:00",
        )

        article = repository.create(
            "Headline\nArticle body",
            image_bytes,
            "image/png",
            {"email": "admin@example.com", "name": "Admin"},
        )

        self.assertEqual("Headline", article["title"])
        self.assertTrue(article["has_image"])
        self.assertEqual("Headline Article body", repository.list()[0]["excerpt"])
        self.assertEqual((image_bytes, "image/png"), repository.image(article["id"]))


if __name__ == "__main__":
    unittest.main()
