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
    const wrap = appendElement(section, 'div', { className: 'table-wrap gms-table-wrap' });
    const table = appendElement(wrap, 'table', { className: 'gms-table' });
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
      appendElement(tr, 'td', { text: row.gm_name || '—' });
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
    const wrap = appendElement(container, 'div', { className: 'table-wrap gms-table-wrap' });
    const table = appendElement(wrap, 'table', { className: 'gms-table' });
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
        appendElement(tr, 'td', { text: row.gm_name || '—' });
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
        appendElement(card, 'h3', { text: row.gm_name || '—' });
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

  async function load(options = {}) {
    state.api = options.api || state.api;
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

  global.AnbaGms = { load };
})(window);
