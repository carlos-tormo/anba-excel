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
  const state = {
    api: null,
    inactivePage: 1,
    payload: null,
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

  function renderActiveTable(parent, title, rows) {
    const section = appendElement(parent, 'section', { className: 'gms-panel' });
    appendElement(section, 'h3', { text: title });
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
      const tr = appendElement(tbody, 'tr');
      const teamCell = appendElement(tr, 'td', { className: 'gms-team-cell' });
      appendTeamLogo(teamCell, row.team_code, row.team_name);
      appendElement(tr, 'td', { text: row.gm_name || '—' });
      appendElement(tr, 'td', { text: row.since_year ? `Desde ${row.since_year}` : '—' });
    });
  }

  function inactiveRows() {
    return Array.isArray(state.payload?.inactive_gms) ? state.payload.inactive_gms : [];
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
        const tr = appendElement(tbody, 'tr');
        appendElement(tr, 'td', { text: row.gm_name || '—' });
        appendElement(tr, 'td', { text: row.years_active || '—' });
        appendElement(tr, 'td', { text: Array.isArray(row.teams) && row.teams.length ? row.teams.join(', ') : '—' });
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
    const activeSection = appendElement(board, 'section', { className: 'gms-section-block' });
    appendElement(activeSection, 'h2', { text: 'GMs activos' });
    const activeGrid = appendElement(activeSection, 'div', { className: 'gms-conference-grid' });
    renderActiveTable(activeGrid, 'Conferencia Este', activeRows(payload, 'east'));
    renderActiveTable(activeGrid, 'Conferencia Oeste', activeRows(payload, 'west'));
    const otherRows = activeRows(payload, 'other');
    if (otherRows.length) renderActiveTable(activeGrid, 'Otros equipos', otherRows);

    const inactiveDetails = appendElement(board, 'details', { className: 'gms-section-block gms-inactive-details' });
    appendElement(inactiveDetails, 'summary', { text: `GMs inactivos (${inactiveRows().length})` });
    const inactiveContainer = appendElement(inactiveDetails, 'div', { className: 'gms-inactive-table' });
    renderInactiveTable(inactiveContainer);
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
