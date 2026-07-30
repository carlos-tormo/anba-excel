(function initAnbaGms(global) {
  const Dom = global.AnbaDom || {};
  const appendElement = Dom.appendElement || ((parent, tagName, options = {}) => {
    const node = document.createElement(tagName);
    if (options.className) node.className = options.className;
    if (options.text !== undefined) node.textContent = options.text == null ? '' : String(options.text);
    if (options.attrs) {
      Object.entries(options.attrs).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value === true ? '' : String(value));
      });
    }
    if (parent) parent.appendChild(node);
    return node;
  });
  const clear = Dom.clear || ((node) => node && node.replaceChildren());
  const PAGE_SIZE = 20;
  const INACTIVE_STATE_KEY = 'anba:gms:inactive-open';
  const state = {
    api: null,
    inactivePage: 1,
    payload: null,
    query: '',
    filter: 'all',
  };

  function text(value) {
    return value == null ? '' : String(value);
  }

  function request(path, opts = {}) {
    const api = state.api || global.AnbaApi?.request;
    if (!api) throw new Error('api_unavailable');
    return api(path, opts);
  }

  function formatDate(value) {
    const raw = text(value).trim().slice(0, 10);
    if (!raw) return '—';
    const [year, month, day] = raw.split('-');
    if (!year || !month || !day) return raw;
    return `${day}/${month}/${year}`;
  }

  function gmProfileUrl(gmId) {
    return `?view=gms&gm=${encodeURIComponent(gmId)}`;
  }

  function appendGmLink(parent, gmId, name, className = 'gms-profile-link') {
    const label = text(name || '—');
    if (!gmId) return appendElement(parent, 'span', { text: label });
    const link = appendElement(parent, 'a', {
      text: label,
      className,
      attrs: { href: gmProfileUrl(gmId), 'data-gm-profile-id': String(gmId) },
    });
    link.addEventListener('click', (event) => {
      event.preventDefault();
      void navigateToProfile(gmId);
    });
    return link;
  }

  function normalized(value) {
    return text(value).trim().toLowerCase();
  }

  function teamLogoPath(code) {
    const normalized = text(code).trim().toUpperCase();
    if (!normalized) return '';
    const fileMap = { LAL: 'lal.png' };
    return `/team-icons/${fileMap[normalized] || `${normalized}.png`}`;
  }

  function appendTeamLogo(parent, code, teamName = '') {
    const normalized = text(code).trim().toUpperCase();
    const wrap = appendElement(parent, 'span', { className: 'gms-team-logo-wrap' });
    const img = appendElement(wrap, 'img', { attrs: { alt: normalized ? `${normalized} logo` : '' } });
    const fallback = appendElement(wrap, 'span', { text: normalized || '—' });
    fallback.hidden = true;
    img.addEventListener('error', () => {
      img.hidden = true;
      fallback.hidden = false;
    });
    const path = teamLogoPath(normalized);
    if (path) {
      if (Dom.setSafeImageSource) Dom.setSafeImageSource(img, path);
      else img.src = path;
    } else {
      img.hidden = true;
      fallback.hidden = false;
    }
    appendElement(parent, 'span', { text: normalized || teamName || '—', className: 'gms-team-code' });
  }

  function boardNode() {
    return document.getElementById('gmsBoard');
  }

  function statusNode() {
    return document.getElementById('gmsStatus');
  }

  function setStatus(message, tone = '') {
    const node = statusNode();
    if (!node) return;
    node.textContent = message || '';
    node.classList.toggle('error', tone === 'error');
  }

  function activeRows(payload, key) {
    return Array.isArray(payload?.active_gms?.[key]) ? payload.active_gms[key] : [];
  }

  function matchesSearch(row) {
    const query = normalized(state.query);
    if (!query) return true;
    const haystack = [
      row.gm_name,
      row.display_name,
      row.team_code,
      row.team_name,
      row.years_active,
      ...(Array.isArray(row.teams) ? row.teams : []),
    ].map(normalized).join(' ');
    return haystack.includes(query);
  }

  function activeRowsFor(key) {
    if (state.filter === 'inactive') return [];
    if (state.filter === 'east' && key !== 'east') return [];
    if (state.filter === 'west' && key !== 'west') return [];
    return activeRows(state.payload, key).filter(matchesSearch);
  }

  function inactiveRows() {
    if (!['all', 'inactive'].includes(state.filter)) return [];
    return (Array.isArray(state.payload?.inactive_gms) ? state.payload.inactive_gms : []).filter(matchesSearch);
  }

  function allInactiveCount() {
    return Array.isArray(state.payload?.inactive_gms) ? state.payload.inactive_gms.length : 0;
  }

  function visibleActiveCount() {
    return ['east', 'west', 'other'].reduce((total, key) => total + activeRowsFor(key).length, 0);
  }

  function isInactiveOpen() {
    try {
      return global.localStorage?.getItem(INACTIVE_STATE_KEY) === 'open';
    } catch {
      return false;
    }
  }

  function rememberInactiveOpen(open) {
    try {
      global.localStorage?.setItem(INACTIVE_STATE_KEY, open ? 'open' : 'closed');
    } catch {
      // ignore storage errors
    }
  }

  function renderToolbar(parent) {
    const toolbar = appendElement(parent, 'div', { className: 'gms-toolbar' });
    const searchWrap = appendElement(toolbar, 'label', { className: 'gms-search' });
    appendElement(searchWrap, 'span', { text: 'Buscar GM' });
    const input = appendElement(searchWrap, 'input', {
      attrs: {
        type: 'search',
        placeholder: 'Buscar GM...',
        value: state.query,
        autocomplete: 'off',
      },
    });
    input.addEventListener('input', () => {
      state.query = input.value;
      state.inactivePage = 1;
      render(state.payload);
      const next = document.querySelector('.gms-search input');
      if (next) {
        next.focus();
        const position = next.value.length;
        next.setSelectionRange(position, position);
      }
    });
    const chips = appendElement(toolbar, 'div', { className: 'gms-filter-chips', attrs: { 'aria-label': 'Filtros de GMs' } });
    [
      ['all', 'Todos'],
      ['active', 'Activos'],
      ['inactive', 'Inactivos'],
      ['east', 'Este'],
      ['west', 'Oeste'],
    ].forEach(([value, label]) => {
      const button = appendElement(chips, 'button', {
        text: label,
        className: value === state.filter ? 'is-active' : '',
        attrs: { type: 'button' },
      });
      button.addEventListener('click', () => {
        state.filter = value;
        state.inactivePage = 1;
        render(state.payload);
      });
    });
  }

  function renderActiveTable(parent, title, rows) {
    const section = appendElement(parent, 'section', { className: 'gms-panel' });
    const panelHead = appendElement(section, 'div', { className: 'gms-panel-head' });
    appendElement(panelHead, 'h3', { text: title });
    appendElement(panelHead, 'span', { text: `${rows.length} GMs`, className: 'gms-count-pill' });
    const wrap = appendElement(section, 'div', { className: 'table-wrap app-table-wrap gms-table-wrap' });
    const table = appendElement(wrap, 'table', { className: 'app-table app-table--interactive app-table--mobile-wrap gms-table' });
    const thead = appendElement(table, 'thead');
    const header = appendElement(thead, 'tr');
    ['Equipo', 'GM', 'Desde'].forEach((label) => appendElement(header, 'th', { text: label }));
    const tbody = appendElement(table, 'tbody');
    if (!rows.length) {
      const tr = appendElement(tbody, 'tr');
      appendElement(tr, 'td', { text: 'Sin GMs activos configurados.', attrs: { colspan: '3' } });
      return;
    }
    rows.forEach((row) => {
      const tr = appendElement(tbody, 'tr', { className: 'gms-data-row' });
      const teamCell = appendElement(tr, 'td', { className: 'gms-team-cell' });
      appendTeamLogo(teamCell, row.team_code, row.team_name);
      const gmCell = appendElement(tr, 'td');
      appendGmLink(gmCell, row.gm_id, row.gm_name || '—');
      appendElement(tr, 'td', { text: row.since_year || '—' });
    });
  }

  function renderInactiveTable(container) {
    clear(container);
    const rows = inactiveRows();
    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    state.inactivePage = Math.max(1, Math.min(totalPages, state.inactivePage));
    const start = (state.inactivePage - 1) * PAGE_SIZE;
    const pageRows = rows.slice(start, start + PAGE_SIZE);
    const wrap = appendElement(container, 'div', { className: 'table-wrap app-table-wrap gms-table-wrap' });
    const table = appendElement(wrap, 'table', { className: 'app-table app-table--interactive app-table--mobile-wrap gms-table' });
    const thead = appendElement(table, 'thead');
    const header = appendElement(thead, 'tr');
    ['GM', 'Years active', 'Teams'].forEach((label) => appendElement(header, 'th', { text: label }));
    const tbody = appendElement(table, 'tbody');
    if (!pageRows.length) {
      const tr = appendElement(tbody, 'tr');
      appendElement(tr, 'td', { text: 'Sin GMs inactivos todavía.', attrs: { colspan: '3' } });
    } else {
      pageRows.forEach((row) => {
        const tr = appendElement(tbody, 'tr', { className: 'gms-data-row' });
        const gmCell = appendElement(tr, 'td');
        appendGmLink(gmCell, row.gm_id, row.gm_name || '—');
        appendElement(tr, 'td', { text: row.years_active || '—' });
        appendElement(tr, 'td', { text: Array.isArray(row.teams) && row.teams.length ? row.teams.join(', ') : '—' });
      });
    }
    const cards = appendElement(container, 'div', { className: 'gms-inactive-cards' });
    if (!pageRows.length) {
      appendElement(cards, 'div', { text: 'Sin GMs inactivos todavía.', className: 'gms-empty-card' });
    } else {
      pageRows.forEach((row) => {
        const card = appendElement(cards, 'article', { className: 'gms-inactive-card' });
        const heading = appendElement(card, 'h3');
        appendGmLink(heading, row.gm_id, row.gm_name || '—');
        const meta = appendElement(card, 'dl');
        appendElement(meta, 'dt', { text: 'Años' });
        appendElement(meta, 'dd', { text: row.years_active || '—' });
        appendElement(meta, 'dt', { text: 'Equipos' });
        appendElement(meta, 'dd', { text: Array.isArray(row.teams) && row.teams.length ? row.teams.join(', ') : '—' });
      });
    }
    const pager = appendElement(container, 'div', { className: 'gms-pager' });
    const prev = appendElement(pager, 'button', { text: 'Anterior', attrs: { type: 'button' } });
    appendElement(pager, 'span', { text: `${state.inactivePage} / ${totalPages}` });
    const next = appendElement(pager, 'button', { text: 'Siguiente', attrs: { type: 'button' } });
    prev.disabled = state.inactivePage <= 1;
    next.disabled = state.inactivePage >= totalPages;
    prev.addEventListener('click', () => {
      state.inactivePage -= 1;
      renderInactiveTable(container);
    });
    next.addEventListener('click', () => {
      state.inactivePage += 1;
      renderInactiveTable(container);
    });
  }

  function render(payload) {
    const board = boardNode();
    if (!board) return;
    clear(board);
    renderToolbar(board);
    if (state.filter !== 'inactive') {
      const activeSection = appendElement(board, 'section', { className: 'gms-section-block' });
      const activeHead = appendElement(activeSection, 'div', { className: 'gms-section-title-row gms-section-title-row--active' });
      appendElement(activeHead, 'span', { text: '●', className: 'gms-status-dot' });
      appendElement(activeHead, 'h2', { text: 'GMs activos' });
      appendElement(activeHead, 'span', { text: `${visibleActiveCount()} activos`, className: 'gms-section-badge' });
      const activeGrid = appendElement(activeSection, 'div', { className: 'gms-conference-grid' });
      renderActiveTable(activeGrid, 'Conferencia Este', activeRowsFor('east'));
      renderActiveTable(activeGrid, 'Conferencia Oeste', activeRowsFor('west'));
      const otherRows = activeRowsFor('other');
      if (otherRows.length) renderActiveTable(activeGrid, 'Otros equipos', otherRows);
    }

    if (['all', 'inactive'].includes(state.filter)) {
      const inactiveDetails = appendElement(board, 'details', { className: 'gms-section-block gms-inactive-details' });
      inactiveDetails.open = state.filter === 'inactive' || isInactiveOpen();
      const summary = appendElement(inactiveDetails, 'summary');
      const summaryInner = appendElement(summary, 'span', { className: 'gms-summary-inner' });
      appendElement(summaryInner, 'span', { text: '○', className: 'gms-status-dot gms-status-dot--inactive' });
      appendElement(summaryInner, 'span', { text: 'GMs inactivos', className: 'gms-summary-title' });
      appendElement(summaryInner, 'span', { text: `${inactiveRows().length} visibles · ${allInactiveCount()} total`, className: 'gms-section-badge' });
      inactiveDetails.addEventListener('toggle', () => rememberInactiveOpen(inactiveDetails.open));
      const inactiveContainer = appendElement(inactiveDetails, 'div', { className: 'gms-inactive-table' });
      renderInactiveTable(inactiveContainer);
    }
  }

  function renderProfileSummary(parent, profile) {
    const hero = appendElement(parent, 'article', { className: 'gms-profile-hero' });
    const avatar = appendElement(hero, 'div', { className: 'gms-profile-avatar' });
    if (profile.avatar_url) {
      const img = appendElement(avatar, 'img', { attrs: { alt: `${profile.nick || profile.display_name || 'GM'} avatar` } });
      if (Dom.setSafeImageSource) Dom.setSafeImageSource(img, profile.avatar_url);
      else img.src = profile.avatar_url;
    } else {
      appendElement(avatar, 'span', { text: text(profile.nick || profile.display_name || 'GM').slice(0, 2).toUpperCase() || 'GM' });
    }
    const body = appendElement(hero, 'div', { className: 'gms-profile-hero-body' });
    appendElement(body, 'p', { text: 'Perfil de GM', className: 'gms-profile-kicker' });
    appendElement(body, 'h2', { text: profile.nick || profile.display_name || 'GM' });
    const meta = appendElement(body, 'dl', { className: 'gms-profile-meta' });
    [
      ['Rol actual', profile.current_role || '—'],
      ['En la liga desde', formatDate(profile.joined_league_date)],
      ['Tipo', profile.has_site_user ? 'Usuario del sitio' : 'GM offline'],
    ].forEach(([label, value]) => {
      appendElement(meta, 'dt', { text: label });
      appendElement(meta, 'dd', { text: value });
    });
  }

  function renderProfileHistory(parent, history) {
    const section = appendElement(parent, 'section', { className: 'gms-profile-card' });
    appendElement(section, 'h3', { text: 'Trayectoria' });
    const rows = Array.isArray(history) ? history : [];
    if (!rows.length) {
      appendElement(section, 'p', { text: 'Sin trayectoria registrada todavía.', className: 'muted-text' });
      return;
    }
    const list = appendElement(section, 'ol', { className: 'gms-profile-timeline' });
    rows.forEach((row) => {
      const item = appendElement(list, 'li');
      const team = appendElement(item, 'span', { className: 'gms-profile-team-chip' });
      appendTeamLogo(team, row.team_code, row.team_name);
      appendElement(item, 'strong', { text: row.team_code || row.team_name || 'Equipo' });
      const end = row.end_date ? formatDate(row.end_date) : (row.is_current ? 'Actualidad' : 'Fecha fin no registrada');
      appendElement(item, 'span', { text: `${formatDate(row.start_date)} – ${end}`, className: 'gms-profile-date-range' });
    });
  }

  function renderDraftPicks(parent, profile) {
    const details = appendElement(parent, 'details', { className: 'gms-profile-card gms-profile-details' });
    const summary = appendElement(details, 'summary');
    appendElement(summary, 'span', { text: 'Draft picks' });
    appendElement(summary, 'strong', { text: `${profile.draft_pick_count || 0} rookies seleccionados` });
    const rows = Array.isArray(profile.draft_picks) ? profile.draft_picks : [];
    if (!rows.length) {
      appendElement(details, 'p', { text: 'Sin selecciones históricas asociadas.', className: 'muted-text' });
      return;
    }
    const list = appendElement(details, 'div', { className: 'gms-profile-pick-list' });
    rows.forEach((pick) => {
      const row = appendElement(list, 'article', { className: 'gms-profile-pick-row' });
      appendElement(row, 'strong', { text: `#${pick.pick_number || '—'} · ${pick.player_name || '—'}` });
      appendElement(row, 'span', { text: `${pick.draft_year || '—'} · ${pick.selecting_team_code || '—'}${pick.original_team_code && pick.original_team_code !== pick.selecting_team_code ? ` vía ${pick.original_team_code}` : ''}` });
    });
  }

  function renderTrades(parent, profile) {
    const details = appendElement(parent, 'details', { className: 'gms-profile-card gms-profile-details' });
    const summary = appendElement(details, 'summary');
    appendElement(summary, 'span', { text: 'Trades' });
    appendElement(summary, 'strong', { text: `${profile.trade_count || 0} trades` });
    const seasons = Array.isArray(profile.trades_by_season) ? profile.trades_by_season : [];
    if (!seasons.length) {
      appendElement(details, 'p', { text: 'Sin trades asociados.', className: 'muted-text' });
      return;
    }
    seasons.forEach((season) => {
      const seasonBlock = appendElement(details, 'section', { className: 'gms-profile-trade-season' });
      appendElement(seasonBlock, 'h4', { text: `Temporada ${season.season_label || season.season_year || '—'}` });
      const list = appendElement(seasonBlock, 'div', { className: 'gms-profile-trade-list' });
      (Array.isArray(season.trades) ? season.trades : []).forEach((trade) => {
        const row = appendElement(list, 'article', { className: 'gms-profile-trade-row' });
        appendElement(row, 'strong', { text: `Trade ${trade.trade_id || trade.id}` });
        appendElement(row, 'span', { text: `${formatDate(trade.trade_date)} · ${(trade.teams || []).join(', ') || '—'} · ${trade.total_assets_moved || 0} activos` });
        const detailsButton = appendElement(row, 'button', {
          text: 'Ver detalles',
          className: 'trade-archive-details-link gms-profile-trade-details-btn',
          attrs: { type: 'button' },
        });
        detailsButton.addEventListener('click', async () => {
          try {
            await global.AnbaTradesArchive?.openDetailsById?.(trade.id, { api: state.api });
          } catch (err) {
            setStatus(`No se pudieron cargar los detalles del trade: ${err.message || err}`, 'error');
          }
        });
      });
    });
  }

  function renderProfile(profile) {
    const board = boardNode();
    if (!board) return;
    clear(board);
    const back = appendElement(board, 'button', { text: '← Volver a GMs', className: 'ghost gms-profile-back', attrs: { type: 'button' } });
    back.addEventListener('click', () => {
      try {
        global.history.pushState({}, '', '?view=gms');
      } catch {
        // ignore history errors
      }
      if (state.payload) render(state.payload);
      else void load();
    });
    renderProfileSummary(board, profile);
    renderProfileHistory(board, profile.history);
    const grid = appendElement(board, 'div', { className: 'gms-profile-grid' });
    renderDraftPicks(grid, profile);
    renderTrades(grid, profile);
  }

  async function loadProfile(gmId, options = {}) {
    state.api = options.api || state.api;
    setStatus('Cargando perfil de GM...');
    try {
      const profile = await request(`/api/gms/${encodeURIComponent(gmId)}`);
      renderProfile(profile);
      setStatus('');
    } catch (err) {
      const board = boardNode();
      clear(board);
      setStatus(`No se pudo cargar el perfil de GM: ${err.message || err}`, 'error');
    }
  }

  async function navigateToProfile(gmId) {
    try {
      global.history.pushState({}, '', gmProfileUrl(gmId));
    } catch {
      // ignore history errors
    }
    if (typeof global.AnbaOpenGmProfile === 'function') {
      await global.AnbaOpenGmProfile(gmId);
      return;
    }
    await loadProfile(gmId);
  }

  async function load(options = {}) {
    state.api = options.api || state.api;
    const gmId = new URLSearchParams(global.location?.search || '').get('gm');
    if (gmId) {
      await loadProfile(gmId, options);
      return;
    }
    setStatus('Cargando GMs...');
    try {
      state.payload = await request('/api/gms');
      state.inactivePage = 1;
      render(state.payload);
      setStatus('');
    } catch (err) {
      const board = boardNode();
      clear(board);
      setStatus(`No se pudieron cargar los GMs: ${err.message || err}`, 'error');
    }
  }

  document.addEventListener('click', (event) => {
    if (event.defaultPrevented) return;
    const link = event.target?.closest?.('[data-gm-profile-id]');
    if (!link) return;
    const gmId = link.getAttribute('data-gm-profile-id');
    if (!gmId) return;
    event.preventDefault();
    void navigateToProfile(gmId);
  });

  global.AnbaGms = { load, loadProfile, profileUrl: gmProfileUrl };
})(window);
