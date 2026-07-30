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
        waiting_list_index = source.index('/waiting_list.js')
        admin_index = source.index('/admin.js')
        self.assertLess(dom_index, admin_index)
        self.assertLess(dom_index, trades_index)
        self.assertLess(dom_index, waiting_list_index)
        self.assertLess(trades_index, admin_index)
        self.assertLess(waiting_list_index, admin_index)

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
        self.assertIn("function renderFilters", source)
        self.assertIn("function tradeMatchesFilters", source)
        self.assertIn("id: 'tradeArchiveTeamFilter'", source)
        self.assertIn("id: 'tradeArchiveGmFilter'", source)
        self.assertIn("function appendTeamLogo", source)
        self.assertIn("function formatSeasonLabel", source)
        self.assertIn("`${startYear}-${String((startYear + 1) % 100).padStart(2, '0')}`", source)
        self.assertIn("movement?.timeline_gm_name", source)
        self.assertIn("gm_entity_id", source)
        self.assertIn("function appendGmProfileLine", source)
        self.assertIn("data-gm-profile-id", source)
        self.assertIn("trade-archive-gm-line", source)
        self.assertIn("function showTradeDetailsModal", source)
        self.assertIn("function openDetailsById", source)
        self.assertIn("openDetailsById", source)
        self.assertIn("function addAssetSection", source)
        self.assertIn("function addAssetRow", source)
        self.assertIn("trade-archive-details-link", source)
        self.assertIn("Ver detalles", source)
        self.assertNotIn(".innerHTML", source)
        self.assertNotIn("insertAdjacentHTML", source)

        styles = web_file("styles.css")
        self.assertIn(".trade-archive-team-entry", styles)
        self.assertIn(".gms-profile-link", styles)
        self.assertIn(".trade-archive-details-grid", styles)
        self.assertIn(".trade-archive-asset-photo", styles)

    def test_trade_archive_is_available_in_guest_and_admin_navigation(self) -> None:
        for name, script in (("index.html", "guest.js"), ("admin.html", "admin.js")):
            with self.subTest(file=name):
                source = web_file(name)
                self.assertIn('data-nav-view="trade-archive"', source)
                self.assertIn('>Trades</button>', source)
                self.assertLess(source.index("/trades_archive.js"), source.index(f"/{script}"))

    def test_main_navigation_groups_and_order_are_intentional(self) -> None:
        expected_liga_order = (
            'data-nav-view="team">Rosters</button>',
            'data-nav-view="league-players">Jugadores</button>',
            'data-nav-view="tracker">Tracker</button>',
            'data-nav-view="figures">Cifras</button>',
            'data-nav-view="draft-order">Draft</button>',
            'data-nav-view="gms">GMs</button>',
            'data-nav-view="waiting-list">Lista de espera</button>',
        )
        for name in ("index.html", "admin.html"):
            with self.subTest(file=name):
                source = web_file(name)
                self.assertIn('<div class="sidebar-section-label">Historia</div>', source)
                self.assertIn('<div class="sidebar-section-label">Gestión</div>', source)
                self.assertNotIn('<div class="sidebar-section-label">Mercado</div>', source)
                previous = -1
                for item in expected_liga_order:
                    current = source.index(item)
                    self.assertGreater(current, previous)
                    previous = current
                self.assertLess(source.index('<div class="sidebar-section-label">Historia</div>'), source.index('data-nav-view="trade-archive">Trades</button>'))

        styles = web_file("styles.css")
        self.assertIn('#tradeArchiveHomeBtn::before { content: "⇄"; }', styles)
        self.assertIn('#waitingListHomeBtn::before { content: "☷"; }', styles)
        self.assertIn('#gmsHomeBtn::before { content: "♟"; }', styles)

    def test_global_typography_hierarchy_primitives_exist(self) -> None:
        styles = web_file("styles.css")

        self.assertIn(".page-title-wrap h1", styles)
        self.assertIn("font-size: clamp(2rem, 3vw, 2.25rem);", styles)
        self.assertIn(".section-head h2", styles)
        self.assertIn("font-size: clamp(1.5rem, 2.25vw, 1.75rem);", styles)
        self.assertIn(".section-subtitle", styles)
        self.assertIn("font-size: 0.95rem;", styles)
        self.assertIn(".admin-tool-card h3", styles)
        self.assertIn("font-size: clamp(1.125rem, 1.45vw, 1.25rem);", styles)

    def test_shared_app_table_primitives_are_opt_in_and_skip_roster_tables(self) -> None:
        styles = web_file("styles.css")

        self.assertIn(".app-table-wrap", styles)
        self.assertIn(".app-table {", styles)
        self.assertIn(".app-table thead th", styles)
        self.assertIn(".app-table tbody tr:nth-child(even) td", styles)
        self.assertIn(".app-table--interactive tbody tr:hover td", styles)
        self.assertIn(".app-table--mobile-wrap th", styles)
        self.assertIn("@media (hover: none)", styles)

        for name in ("index.html", "admin.html"):
            source = web_file(name)
            self.assertIn('id="trackerTable" class="app-table app-table--interactive app-table--numeric app-table--mobile-wrap"', source)
            self.assertIn('id="trackerEconomyTable" class="app-table app-table--interactive app-table--numeric app-table--mobile-wrap"', source)
            for table_id in ("playersTable", "deadContractsTable", "exceptionsTable", "playerRightsTable"):
                marker = f'id="{table_id}"'
                position = source.index(marker)
                table_tag_end = source.index(">", position)
                self.assertNotIn("app-table", source[position:table_tag_end])

        self.assertIn("app-table app-table--interactive app-table--mobile-wrap draft-order-table", web_file("guest.js"))
        self.assertIn("app-table app-table--interactive app-table--mobile-wrap draft-order-table waiting-list-table", web_file("waiting_list.js"))
        self.assertIn("app-table app-table--interactive app-table--mobile-wrap draft-order-table trade-archive-table", web_file("trades_archive.js"))
        self.assertIn("app-table app-table--interactive app-table--mobile-wrap gms-table", web_file("gms.js"))

    def test_draft_history_frontend_switch_and_admin_importer_are_wired(self) -> None:
        guest = web_file("guest.js")
        admin = web_file("admin.js")
        admin_html = web_file("admin.html")

        for source in (guest, admin):
            self.assertIn("function isHistoricalDraftYear", source)
            self.assertIn("for (let year = 2019;", source)
            self.assertIn("/api/draft-history?year=", source)
            self.assertIn("function renderDraftHistoryTable", source)
            self.assertIn("function draftHistoryOriginalPickHtml", source)
            self.assertIn("function draftHistorySelectingTeamHtml", source)
            self.assertIn("selecting_team_code", source)
            self.assertIn("selecting_gm_name", source)
            self.assertIn("via ${original}", source)
            self.assertIn('<th aria-label="Pick original"></th>', source)
            self.assertIn("draft-history-table", source)

        history_render_start = guest.index("function renderDraftHistoryTable")
        history_render_end = guest.index("function draftLiveRemainingSeconds", history_render_start)
        self.assertNotIn("<th>Pick original</th>", guest[history_render_start:history_render_end])
        self.assertNotIn("row.canonical_id", guest[history_render_start:history_render_end])

        self.assertIn('id="openDraftHistoryImportBtn"', admin_html)
        self.assertIn('id="archiveDraftHistoryBtn"', admin_html)
        self.assertIn('id="draftYearNavigator"', admin_html)
        self.assertIn('id="draftYearNavigator"', web_file("index.html"))
        self.assertIn('id="draftHistoryImportModal"', admin_html)
        self.assertIn('id="draftHistoryDateOnlyInput"', admin_html)
        self.assertIn('id="draftHistoryDateOnlyBtn"', admin_html)
        self.assertIn("/api/admin/draft-history/import", admin)
        self.assertIn("/api/admin/draft-history/dates", admin)
        self.assertIn("/api/admin/draft-history/archive-live", admin)
        self.assertIn("archiveDraftHistoryBtn')?.classList.toggle('section-hidden', false)", admin)
        self.assertIn("draft_history_archive", admin)
        self.assertIn("data-draft-year-nav", admin)
        self.assertIn("draft-year-nav-year", admin)
        self.assertIn("draftYearBounds", admin)
        self.assertIn("setupDraftHistoryImportControls()", admin)

    def test_trade_archive_admin_importer_exposes_json_file_and_error_ui(self) -> None:
        source = web_file("admin.html")

        self.assertIn('id="tradeArchiveImportFile"', source)
        self.assertIn('accept="application/json,.json"', source)
        self.assertIn('id="tradeArchiveImportErrors"', source)
        self.assertIn("Formato JSON soportado", source)
        self.assertIn("draft_year", source)
        self.assertIn("original_team_code", source)
        archive_js = web_file("trades_archive.js")
        self.assertIn("function assetMeta", archive_js)
        self.assertIn("canonical_id", archive_js)
        self.assertIn("draft_selection", archive_js)
        self.assertIn("Elegido por", archive_js)

    def test_cartera_view_is_frontend_gated_to_admin_and_coadmin(self) -> None:
        source = web_file("guest.js")

        self.assertIn("function canViewWallet()", source)
        self.assertIn("['admin', 'co_admin'].includes(role)", source)
        self.assertIn("state.ui.viewMode = mode === 'wallet' && !canViewWallet() ? 'tracker' : mode;", source)
        load_wallet_start = source.index("async function loadWallet()")
        guard_index = source.index("if (!canViewWallet())", load_wallet_start)
        set_view_index = source.index("setViewMode('wallet')", load_wallet_start)
        self.assertLess(guard_index, set_view_index)

    def test_waiting_list_frontend_uses_safe_dom_helpers_and_shared_api(self) -> None:
        source = web_file("waiting_list.js")

        self.assertIn("global.AnbaDom", source)
        self.assertIn("global.AnbaApi?.request", source)
        self.assertIn("global.AnbaApi?.withSubmissionLock", source)
        self.assertIn("global.AnbaWaitingList", source)
        self.assertIn("function renderTable", source)
        self.assertIn("function bindAdminControls", source)
        self.assertIn("function showEditModal", source)
        self.assertIn("Plaza", source)
        self.assertIn("Fecha de inscripción", source)
        self.assertNotIn(".innerHTML", source)
        self.assertNotIn("insertAdjacentHTML", source)

    def test_waiting_list_is_available_in_guest_and_admin_navigation(self) -> None:
        for name, script in (("index.html", "guest.js"), ("admin.html", "admin.js")):
            with self.subTest(file=name):
                source = web_file(name)
                self.assertIn('data-nav-view="waiting-list"', source)
                self.assertLess(source.index("/waiting_list.js"), source.index(f"/{script}"))

        admin_source = web_file("admin.html")
        self.assertIn('id="waitingListAdminForm"', admin_source)
        self.assertIn('id="waitingListDiscordInput"', admin_source)

    def test_gms_placeholder_is_wired_in_guest_and_admin(self) -> None:
        gms_source = web_file("gms.js")
        self.assertIn("GMs activos", gms_source)
        self.assertIn("GMs inactivos", gms_source)
        self.assertIn("Conferencia Este", gms_source)
        self.assertIn("Conferencia Oeste", gms_source)
        self.assertIn("const PAGE_SIZE = 20", gms_source)
        self.assertIn("Buscar GM", gms_source)
        self.assertIn("anba:gms:inactive-open", gms_source)
        self.assertIn("gms-filter-chips", gms_source)
        self.assertIn("gms-inactive-card", gms_source)
        self.assertIn("function renderProfile", gms_source)
        self.assertIn("function loadProfile", gms_source)
        self.assertIn("/api/gms/${encodeURIComponent(gmId)}", gms_source)
        self.assertIn("data-gm-profile-id", gms_source)
        self.assertIn("gms-profile-hero", gms_source)
        self.assertIn("rookies seleccionados", gms_source)
        self.assertIn("trades_by_season", gms_source)
        self.assertIn("gms-profile-trade-details-btn", gms_source)
        self.assertIn("AnbaTradesArchive?.openDetailsById", gms_source)
        for name, script in (("index.html", "guest.js"), ("admin.html", "admin.js")):
            with self.subTest(file=name):
                source = web_file(name)
                self.assertIn('id="gmsSection"', source)
                self.assertIn('id="gmsBoard"', source)
                self.assertIn("/gms.js", source)
                self.assertIn('data-nav-view="gms"', source)
                script_source = web_file(script)
                self.assertIn("async function loadGms()", script_source)
                self.assertIn("window.AnbaGms.load({ api })", script_source)
                self.assertIn("window.AnbaOpenGmProfile", script_source)
                self.assertIn("setViewMode('gms')", script_source)

    def test_admin_users_edit_username_and_team_gm_is_assignment_driven(self) -> None:
        admin_html = web_file("admin.html")
        admin_js = web_file("admin.js")

        self.assertIn("<th>Username</th>", admin_html)
        self.assertIn('id="teamAssignedGmInline"', admin_html)
        self.assertIn("Admin Menu → Users → Team assignment", admin_html)
        self.assertNotIn('id="teamGmInlineInput"', admin_html)
        self.assertNotIn('id="saveTeamGmInlineBtn"', admin_html)
        self.assertIn("data-admin-user-username", admin_js)
        self.assertIn("username: String(usernameInput?.value || '').trim()", admin_js)
        self.assertNotIn("async function saveCurrentTeamGm", admin_js)

    def test_gm_timeline_uses_identity_dropdown_and_preserved_label(self) -> None:
        admin_html = web_file("admin.html")
        admin_js = web_file("admin.js")

        self.assertIn("GM entity / historical name", admin_html)
        self.assertIn("async function loadGmIdentities()", admin_js)
        self.assertIn("api('/api/gm-identities')", admin_js)
        self.assertIn('data-gm-field="gm_entity_id"', admin_js)
        self.assertIn('data-gm-field="gm_name"', admin_js)
        self.assertIn("gm_entity_id: Number(entry.gm_entity_id) > 0", admin_js)


if __name__ == "__main__":
    unittest.main()
