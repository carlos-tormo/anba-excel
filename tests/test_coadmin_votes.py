import os
import sqlite3
import tempfile
import unittest

from app.server import LeagueDB
from app.xlsx_import import create_schema, now_iso


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


class CoadminVoteTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-coadmin-votes-", suffix=".db")
        os.close(fd)
        self.db_path = path
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            create_schema(conn)
            insert_team(conn, "ATL", "Atlanta Hawks")
            insert_team(conn, "BKN", "Brooklyn Nets")
            insert_team(conn, "BOS", "Boston Celtics")
            conn.commit()
        self.db = LeagueDB(path)
        self.db.ensure_auth_schema()
        self.user = self.db.upsert_google_user("coadmin-sub", "co@example.com", "Co Admin", None)
        self.db.replace_user_team_assignments(self.user["id"], ["ATL"], is_co_admin=True)
        self.session = {
            "user_id": self.user["id"],
            "email": "co@example.com",
            "name": "Co Admin",
            "role": "co_admin",
            "team_codes": ["ATL"],
        }

    def tearDown(self) -> None:
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def test_coadmin_vote_excludes_own_team_and_calculates_averages(self) -> None:
        vote = self.db.create_coadmin_vote("Valor GM", {"email": "admin@example.com", "name": "Admin"})
        payload = self.db.list_coadmin_votes_for_session(self.session)

        self.assertEqual(["ATL"], payload["own_team_codes"])
        self.assertEqual(1, len(payload["votes"]))
        self.assertEqual(["BKN", "BOS"], [team["code"] for team in payload["votes"][0]["target_teams"]])

        with self.assertRaisesRegex(ValueError, "own_team_score_not_allowed"):
            self.db.submit_coadmin_vote(vote["id"], {"ATL": 90, "BKN": 80, "BOS": 70}, self.session)

        submitted = self.db.submit_coadmin_vote(vote["id"], {"BKN": 80, "BOS": 70}, self.session)
        self.assertTrue(submitted["submitted"])

        admin_votes = self.db.list_admin_coadmin_votes()
        self.assertEqual(1, len(admin_votes))
        self.assertEqual(1, admin_votes[0]["submitted_voter_count"])
        averages = {row["team_code"]: row for row in admin_votes[0]["averages"]}
        self.assertEqual(80.0, averages["BKN"]["average_score"])
        self.assertEqual(70.0, averages["BOS"]["average_score"])
        self.assertIsNone(averages["ATL"]["average_score"])

    def test_closed_vote_rejects_new_submission(self) -> None:
        vote = self.db.create_coadmin_vote("Valor GM", {"email": "admin@example.com", "name": "Admin"})
        self.db.set_coadmin_vote_status(vote["id"], "closed", {"email": "admin@example.com"})

        with self.assertRaisesRegex(ValueError, "vote_closed"):
            self.db.submit_coadmin_vote(vote["id"], {"BKN": 80, "BOS": 70}, self.session)


if __name__ == "__main__":
    unittest.main()
