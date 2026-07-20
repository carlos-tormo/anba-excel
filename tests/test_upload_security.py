import base64
import os
import sqlite3
import tempfile
import unittest
import io
import zipfile

from tests.db_helpers import connect_test_db

from app.import_export.spreadsheets import spreadsheet_rows_from_payload
from app.db.maintenance import public_backup_metadata
from app.server import LeagueDB, detect_safe_image_type
from app.xlsx_import import create_schema, now_iso


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def insert_team(conn: sqlite3.Connection, code: str, name: str) -> int:
    now = now_iso()
    cur = conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, apron_hard_cap,
            salary_cap, luxury_cap, first_apron, second_apron,
            created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, NULL, 154647000, 187896105, 195945000, 207824000, ?, ?)
        """,
        (code, name, now, now),
    )
    return int(cur.lastrowid)


class UploadSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-upload-security-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with connect_test_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            conn.commit()
        self.db = LeagueDB(self.db_path)
        self.db.ensure_auth_schema()

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_image_detection_rejects_svg_and_mime_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            detect_safe_image_type(SVG_BYTES, "image/svg+xml")

        with self.assertRaises(ValueError):
            detect_safe_image_type(PNG_BYTES, "image/jpeg")

        ext, mime_type = detect_safe_image_type(PNG_BYTES, "image/png")
        self.assertEqual("png", ext)
        self.assertEqual("image/png", mime_type)

    def test_image_detection_rejects_invalid_or_oversized_dimensions(self) -> None:
        signature_only = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 32)
        with self.assertRaises(ValueError):
            detect_safe_image_type(signature_only, "image/png")

        oversized_png = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\x0dIHDR"
            + (9000).to_bytes(4, "big")
            + (1).to_bytes(4, "big")
        )
        with self.assertRaises(ValueError):
            detect_safe_image_type(oversized_png, "image/png")

    def test_public_backup_metadata_never_exposes_filesystem_path(self) -> None:
        public = public_backup_metadata(
            {
                "id": "backup-1",
                "path": "/private/backups/league.db",
                "bytes": 123,
                "sha256": "abc",
                "integrity_check": "ok",
            }
        )

        self.assertEqual("backup-1", public["id"])
        self.assertNotIn("path", public)

    def test_spreadsheet_import_rejects_suspicious_xlsx_compression(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/worksheets/sheet1.xml", b"A" * 1_000_000)

        with self.assertRaisesRegex(ValueError, "xlsx_suspicious_compression"):
            spreadsheet_rows_from_payload(
                file_name="bomb.xlsx",
                file_data_base64=base64.b64encode(output.getvalue()).decode("ascii"),
            )

    def test_owner_background_upload_uses_internal_url_and_survives_profile_save(self) -> None:
        owner_office = self.db.update_owner_background_image("ATL", PNG_BYTES, "image/png")
        self.assertIsNotNone(owner_office)
        background_url = owner_office["owner_profile"]["owner_office_background_url"]
        self.assertRegex(background_url, r"^/api/teams/ATL/owner-office/background-image\?v=")

        saved = self.db.update_team_owner_office(
            "ATL",
            {
                "season_year": 2025,
                "owner_profile": {
                    "owner_name": "Safe Owner",
                    "owner_photo_url": "javascript:alert(1)",
                    "owner_office_background_url": "https://example.com/evil.svg",
                },
            },
        )

        self.assertIsNotNone(saved)
        profile = saved["owner_profile"]
        self.assertEqual("", profile["owner_photo_url"])
        self.assertEqual(background_url, profile["owner_office_background_url"])

        image = self.db.get_owner_background_image("ATL")
        self.assertIsNotNone(image)
        image_bytes, mime_type = image
        self.assertEqual(PNG_BYTES, image_bytes)
        self.assertEqual("image/png", mime_type)


if __name__ == "__main__":
    unittest.main()
