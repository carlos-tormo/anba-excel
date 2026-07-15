import os
import sqlite3
import tempfile
import unittest

from app.server import (
    AuthorizationError,
    Handler,
    LeagueDB,
    authorize_action,
    pbkdf2_sha256_password_hash,
    session_token_digest,
    verify_admin_password,
)
from app.xlsx_import import create_schema, now_iso


def make_handler(headers=None):
    handler = Handler.__new__(Handler)
    handler.headers = headers or {}
    handler.cookie_same_site = "Lax"
    handler.cookie_secure_policy = "auto"
    handler.cookie_domain = None
    handler.session_ttl_seconds = 3600
    handler.oauth_state_ttl_seconds = 600
    handler.allowed_origins = set()
    handler.pending_oauth_states = {}
    return handler


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


class AuthSecurityTests(unittest.TestCase):
    def test_authorize_action_denies_unknown_actions_by_default(self) -> None:
        actor = {"role": "admin", "team_codes": []}

        with self.assertRaises(AuthorizationError) as ctx:
            authorize_action(actor, "unknown.action", {"team_code": "ATL"})

        self.assertEqual(403, ctx.exception.status)
        self.assertEqual("action_not_allowed", ctx.exception.error)

    def test_authorize_action_requires_authenticated_actor(self) -> None:
        with self.assertRaises(AuthorizationError) as ctx:
            authorize_action(None, "gm_office.view", {"team_code": "ATL"})

        self.assertEqual(401, ctx.exception.status)
        self.assertEqual("auth_required", ctx.exception.error)

    def test_authorize_action_allows_admin_override(self) -> None:
        actor = {"role": "admin", "team_codes": []}

        self.assertTrue(authorize_action(actor, "gm_office.depth_chart.update", {"team_code": "BOS"}))

    def test_authorize_action_enforces_team_scope_for_gms(self) -> None:
        actor = {"role": "gm", "team_codes": ["ATL"]}

        self.assertTrue(authorize_action(actor, "gm.free_agent_offer.create", {"team_code": "ATL"}))
        with self.assertRaises(AuthorizationError) as ctx:
            authorize_action(actor, "gm.free_agent_offer.create", {"team_code": "BOS"})

        self.assertEqual(403, ctx.exception.status)
        self.assertEqual("team_access_required", ctx.exception.error)

    def test_authorize_action_normalizes_legacy_phoenix_code(self) -> None:
        actor = {"role": "gm", "team_codes": ["PHO"]}

        self.assertTrue(authorize_action(actor, "draft_live.pick_submit", {"team_code": "PHX"}))

    def test_admin_policy_rejects_gm_even_for_own_team(self) -> None:
        actor = {"role": "gm", "team_codes": ["ATL"]}

        with self.assertRaises(AuthorizationError) as ctx:
            authorize_action(actor, "admin.player.write", {"team_code": "ATL"})

        self.assertEqual(403, ctx.exception.status)
        self.assertEqual("forbidden", ctx.exception.error)

    def test_global_admin_policy_rejects_gm(self) -> None:
        actor = {"role": "gm", "team_codes": ["ATL"]}

        with self.assertRaises(AuthorizationError) as ctx:
            authorize_action(actor, "admin.global.write", {})

        self.assertEqual(403, ctx.exception.status)
        self.assertEqual("forbidden", ctx.exception.error)

    def test_admin_password_hash_verification(self) -> None:
        encoded = pbkdf2_sha256_password_hash(
            "correct horse battery staple",
            iterations=120_000,
            salt_hex="00" * 16,
        )

        self.assertTrue(verify_admin_password("correct horse battery staple", "", encoded))
        self.assertFalse(verify_admin_password("wrong", "", encoded))
        self.assertTrue(verify_admin_password("plain-secret", "plain-secret", ""))
        self.assertFalse(verify_admin_password("wrong", "plain-secret", ""))

    def test_session_cookie_flags_are_secure_for_https_proxy(self) -> None:
        handler = make_handler({"X-Forwarded-Proto": "https", "Host": "anba.example"})
        cookie = handler._session_cookie("session-token")

        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("Priority=High", cookie)

    def test_session_cookie_remains_localhost_compatible_by_default(self) -> None:
        handler = make_handler({"Host": "127.0.0.1:8000"})
        cookie = handler._session_cookie("session-token")

        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn("Secure", cookie)

    def test_sessions_store_token_digests_for_new_sessions(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-auth-session-", suffix=".db")
        os.close(fd)
        try:
            with sqlite3.connect(path) as conn:
                conn.row_factory = sqlite3.Row
                create_schema(conn)
                conn.commit()

            db = LeagueDB(path)
            db.ensure_auth_schema()
            self.assertTrue(db.create_session("raw-session-token", {"role": "admin"}, now_iso(), 4_102_444_800))

            with db.connect() as conn:
                row = conn.execute("SELECT session_token, session_token_hash FROM sessions").fetchone()

            expected = session_token_digest("raw-session-token")
            self.assertEqual(expected, row["session_token"])
            self.assertEqual(expected, row["session_token_hash"])
            self.assertNotEqual("raw-session-token", row["session_token"])
            self.assertEqual({"role": "admin"}, db.get_session("raw-session-token", now_ts=1_800_000_000))

            db.delete_session("raw-session-token")
            self.assertIsNone(db.get_session("raw-session-token", now_ts=1_800_000_000))
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_legacy_raw_session_rows_remain_readable_until_expiry(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-auth-legacy-session-", suffix=".db")
        os.close(fd)
        try:
            with sqlite3.connect(path) as conn:
                conn.row_factory = sqlite3.Row
                create_schema(conn)
                conn.commit()

            db = LeagueDB(path)
            db.ensure_auth_schema()
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (session_token, data_json, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("legacy-token", '{"role":"gm"}', now_iso(), 4_102_444_800),
                )
                conn.commit()

            self.assertEqual({"role": "gm"}, db.get_session("legacy-token", now_ts=1_800_000_000))
            db.delete_session("legacy-token")
            self.assertIsNone(db.get_session("legacy-token", now_ts=1_800_000_000))
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_same_site_none_forces_secure_cookie(self) -> None:
        handler = make_handler({"Host": "127.0.0.1:8000"})
        handler.cookie_same_site = "None"
        cookie = handler._session_cookie("session-token")

        self.assertIn("SameSite=None", cookie)
        self.assertIn("Secure", cookie)

    def test_same_origin_checks_reject_cross_origin_requests(self) -> None:
        same_origin = make_handler(
            {
                "Host": "anba.example",
                "X-Forwarded-Proto": "https",
                "Origin": "https://anba.example",
            }
        )
        self.assertTrue(same_origin._same_origin_request_ok())

        cross_origin = make_handler(
            {
                "Host": "anba.example",
                "X-Forwarded-Proto": "https",
                "Origin": "https://evil.example",
            }
        )
        self.assertFalse(cross_origin._same_origin_request_ok())

        no_origin = make_handler({"Host": "anba.example"})
        self.assertTrue(no_origin._same_origin_request_ok())

    def test_oauth_state_is_browser_bound_and_one_time_use(self) -> None:
        state = "oauth-state-token"
        handler = make_handler({"Cookie": f"oauth_state={state}"})
        handler._store_oauth_state(state)

        self.assertTrue(handler._oauth_state_ok(state))
        self.assertNotIn(state, handler.pending_oauth_states)
        self.assertFalse(handler._oauth_state_ok(state))

        other = make_handler({"Cookie": "oauth_state=other-state"})
        other._store_oauth_state(state)
        self.assertFalse(other._oauth_state_ok(state))

    def test_google_user_can_resolve_as_co_admin_without_full_admin_role(self) -> None:
        fd, path = tempfile.mkstemp(prefix="anba-auth-coadmin-", suffix=".db")
        os.close(fd)
        try:
            with sqlite3.connect(path) as conn:
                conn.row_factory = sqlite3.Row
                create_schema(conn)
                insert_team(conn, "ATL", "Atlanta Hawks")
                conn.commit()

            db = LeagueDB(path)
            db.ensure_auth_schema()
            user = db.upsert_google_user("google-coadmin", "co@example.com", "Co Admin", None)
            updated = db.replace_user_team_assignments(user["id"], ["ATL"], is_co_admin=True)

            self.assertIsNotNone(updated)
            self.assertTrue(updated["is_co_admin"])
            self.assertEqual(["ATL"], updated["team_codes"])

            handler = make_handler()
            handler.db = db
            handler.admin_emails = {"admin@example.com"}
            handler.gm_accounts = {}

            role, team_codes = handler._google_role_for_email("co@example.com")
            self.assertEqual("co_admin", role)
            self.assertEqual(["ATL"], team_codes)
            self.assertEqual("/?team=ATL", handler._landing_path_for_session(role, team_codes))

            admin_role, admin_team_codes = handler._google_role_for_email("admin@example.com")
            self.assertEqual("admin", admin_role)
            self.assertEqual([], admin_team_codes)
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
