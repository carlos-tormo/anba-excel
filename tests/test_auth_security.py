import unittest

from app.server import (
    Handler,
    pbkdf2_sha256_password_hash,
    verify_admin_password,
)


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


class AuthSecurityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
