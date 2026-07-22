import unittest
import re
from pathlib import Path
from unittest.mock import patch

from app import server
from app.server import Handler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HTML_FILES = tuple(sorted((PROJECT_ROOT / "web").glob("*.html")))


def rendered_headers(path="/api/private", headers=None, *, env=None, pre_headers=None):
    handler = object.__new__(Handler)
    handler.path = path
    handler.headers = headers or {}
    handler.request_version = "HTTP/1.1"
    handler._headers_buffer = []
    handler._sent_response_header_names = set()
    for key, value in pre_headers or ():
        Handler.send_header(handler, key, value)
    patched_env = {"CSP_ENFORCE": "", "CSP_REPORT_ONLY": ""}
    patched_env.update(env or {})
    with patch.object(server.SimpleHTTPRequestHandler, "end_headers", lambda _self: None):
        with patch.dict(server.os.environ, patched_env, clear=False):
            Handler.end_headers(handler)
    parsed = {}
    for raw in handler._headers_buffer:
        line = raw.decode("latin-1").strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed.setdefault(key, []).append(value.strip())
    return parsed


class SecurityHeaderTests(unittest.TestCase):
    def test_default_security_headers_enforce_csp_and_frame_ancestors(self) -> None:
        headers = rendered_headers()

        self.assertEqual(["nosniff"], headers["X-Content-Type-Options"])
        self.assertEqual(["strict-origin-when-cross-origin"], headers["Referrer-Policy"])
        self.assertIn("camera=()", headers["Permissions-Policy"][0])
        self.assertIn("microphone=()", headers["Permissions-Policy"][0])
        self.assertEqual(["DENY"], headers["X-Frame-Options"])
        self.assertIn("Content-Security-Policy", headers)
        self.assertNotIn("Content-Security-Policy-Report-Only", headers)
        csp = headers["Content-Security-Policy"][0]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("base-uri 'none'", csp)

    def test_csp_can_be_returned_to_report_only_for_rollout_testing(self) -> None:
        headers = rendered_headers(env={"CSP_REPORT_ONLY": "true"})

        self.assertIn("Content-Security-Policy-Report-Only", headers)
        self.assertNotIn("Content-Security-Policy", headers)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy-Report-Only"][0])

    def test_legacy_csp_enforce_false_keeps_report_only_mode(self) -> None:
        headers = rendered_headers(env={"CSP_ENFORCE": "false"})

        self.assertIn("Content-Security-Policy-Report-Only", headers)
        self.assertNotIn("Content-Security-Policy", headers)

    def test_top_level_html_pages_are_compatible_with_strict_csp(self) -> None:
        inline_script = re.compile(r"<script\b(?![^>]*\bsrc\s*=)", re.IGNORECASE)
        inline_style = re.compile(r"<style\b", re.IGNORECASE)
        inline_event = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
        javascript_url = re.compile(r"javascript\s*:", re.IGNORECASE)

        violations = []
        for path in HTML_FILES:
            html = path.read_text(encoding="utf-8")
            if inline_script.search(html):
                violations.append(f"{path.name}: inline <script>")
            if inline_style.search(html):
                violations.append(f"{path.name}: inline <style>")
            if inline_event.search(html):
                violations.append(f"{path.name}: inline event handler")
            if javascript_url.search(html):
                violations.append(f"{path.name}: javascript: URL")
        self.assertEqual([], violations)

    def test_hsts_is_sent_for_https_proxy_requests(self) -> None:
        headers = rendered_headers(headers={"X-Forwarded-Proto": "https"})

        self.assertEqual(
            ["max-age=31536000; includeSubDomains"],
            headers["Strict-Transport-Security"],
        )

    def test_hsts_is_not_sent_for_plain_http_development_requests(self) -> None:
        headers = rendered_headers(headers={})

        self.assertNotIn("Strict-Transport-Security", headers)

    def test_private_responses_default_to_no_store_without_duplicate_cache_control(self) -> None:
        headers = rendered_headers(
            path="/api/auth/status",
            pre_headers=[("Cache-Control", "no-store")],
        )

        self.assertEqual(["no-store"], headers["Cache-Control"])

    def test_html_and_static_cache_policies_are_explicit(self) -> None:
        html_headers = rendered_headers(path="/admin")
        static_headers = rendered_headers(path="/admin.js?v=20260721a")
        plain_static_headers = rendered_headers(path="/styles.css")

        self.assertEqual(["no-cache, no-store, must-revalidate"], html_headers["Cache-Control"])
        self.assertEqual(["public, max-age=31536000, immutable"], static_headers["Cache-Control"])
        self.assertEqual(["public, max-age=3600"], plain_static_headers["Cache-Control"])

    def test_route_specific_public_cache_control_wins(self) -> None:
        headers = rendered_headers(
            path="/api/news/articles/1/image",
            pre_headers=[("Cache-Control", "public, max-age=31536000, immutable")],
        )

        self.assertEqual(["public, max-age=31536000, immutable"], headers["Cache-Control"])


if __name__ == "__main__":
    unittest.main()
