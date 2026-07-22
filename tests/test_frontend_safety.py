from pathlib import Path
import unittest


WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


def web_file(name: str) -> str:
    return (WEB_ROOT / name).read_text(encoding="utf-8")


class FrontendSafetyTests(unittest.TestCase):
    def test_dom_helpers_are_text_first_and_make_unsafe_html_explicit(self) -> None:
        source = web_file("dom.js")

        self.assertIn("function appendText(", source)
        self.assertIn("document.createTextNode", source)
        self.assertIn("function appendElement(", source)
        self.assertIn("node.textContent", source)
        self.assertIn("function safeUrl(", source)
        self.assertIn("function setSafeImageSource(", source)
        self.assertIn("function setUnsafeHtml(", source)
        self.assertIn("function appendUnsafeHtml(", source)

        for line in source.splitlines():
            if "innerHTML" in line or "insertAdjacentHTML" in line:
                self.assertTrue(
                    "setUnsafeHtml" in line
                    or "appendUnsafeHtml" in line
                    or "parent.innerHTML" in line
                    or "parent.insertAdjacentHTML" in line,
                    line,
                )

    def test_api_helper_centralizes_csrf_errors_uploads_and_duplicate_request_guards(self) -> None:
        source = web_file("api.js")

        self.assertIn("class ApiError extends Error", source)
        self.assertIn("headers['X-CSRF-Token'] = csrfToken", source)
        self.assertIn("onUnauthorized", source)
        self.assertIn("onForbidden", source)
        self.assertIn("onConflict", source)
        self.assertIn("onValidationError", source)
        self.assertIn("inFlightRequestKeys", source)
        self.assertIn("function upload(", source)
        self.assertIn("signal: opts.signal || options.signal", source)
        self.assertIn("function withSubmissionLock(", source)

    def test_primary_api_wrappers_enable_write_deduplication(self) -> None:
        for name in ("admin.js", "guest.js", "login.js"):
            with self.subTest(file=name):
                source = web_file(name)
                self.assertIn("dedupe: method !== 'GET'", source)

    def test_news_dynamic_urls_use_dom_safe_url_helpers(self) -> None:
        source = web_file("news.js")

        self.assertIn("window.AnbaDom.setSafeImageSource", source)
        self.assertIn("window.AnbaDom.safeUrl", source)
        self.assertNotIn("image.src = article.image_url", source)

    def test_admin_owner_background_upload_uses_central_api_upload_and_safe_preview(self) -> None:
        source = web_file("admin.js")

        self.assertIn("window.AnbaApi.upload", source)
        self.assertIn("window.AnbaDom?.safeUrl", source)
        self.assertIn("window.AnbaDom?.setSafeImageSource", source)
        self.assertNotIn("fetch(`/api/teams/${encodeURIComponent(state.teamCode)}/owner-office/background`", source)

    def test_admin_loads_dom_helpers_before_admin_script(self) -> None:
        source = web_file("admin.html")

        dom_index = source.index('/dom.js')
        trades_index = source.index('/trades_archive.js')
        admin_index = source.index('/admin.js')
        self.assertLess(dom_index, admin_index)
        self.assertLess(dom_index, trades_index)
        self.assertLess(trades_index, admin_index)

    def test_trade_archive_frontend_uses_safe_dom_helpers_and_shared_api(self) -> None:
        source = web_file("trades_archive.js")

        self.assertIn("global.AnbaDom", source)
        self.assertIn("global.AnbaApi?.request", source)
        self.assertIn("global.AnbaApi.withSubmissionLock", source)
        self.assertIn("global.AnbaTradesArchive", source)
        self.assertIn("function renderImportErrors", source)
        self.assertIn("function loadImportFile", source)
        self.assertIn("function gmDisplayName", source)
        self.assertIn("function renderSeasonSelector", source)
        self.assertIn("function appendTeamLogo", source)
        self.assertIn("trade-archive-gm-line", source)
        self.assertIn("trade-archive-aggregate-movements", source)
        self.assertNotIn(".innerHTML", source)
        self.assertNotIn("insertAdjacentHTML", source)

    def test_trade_archive_is_available_in_guest_and_admin_navigation(self) -> None:
        for name, script in (("index.html", "guest.js"), ("admin.html", "admin.js")):
            with self.subTest(file=name):
                source = web_file(name)
                self.assertIn('data-nav-view="trade-archive"', source)
                self.assertLess(source.index("/trades_archive.js"), source.index(f"/{script}"))

    def test_trade_archive_admin_importer_exposes_json_file_and_error_ui(self) -> None:
        source = web_file("admin.html")

        self.assertIn('id="tradeArchiveImportFile"', source)
        self.assertIn('accept="application/json,.json"', source)
        self.assertIn('id="tradeArchiveImportErrors"', source)
        self.assertIn("Formato JSON soportado", source)


if __name__ == "__main__":
    unittest.main()
