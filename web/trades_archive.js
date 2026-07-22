(function initAnbaTradesArchive(global) {
  const dom = () => global.AnbaDom || {};
  const state = {
    api: null,
    admin: false,
    trades: [],
  };

  function clear(node) {
    if (dom().clear) dom().clear(node);
    else if (node) node.replaceChildren();
  }

  function el(parent, tagName, options = {}) {
    if (dom().appendElement) return dom().appendElement(parent, tagName, options);
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
  }

  function text(value) {
    return value == null ? '' : String(value);
  }

  function formatDate(value) {
    const raw = text(value).slice(0, 10);
    return raw || '-';
  }

  function movementCount(movement) {
    const row = movement && typeof movement === 'object' ? movement : {};
    return ['players', 'picks', 'swaps', 'rights', 'cash'].reduce((total, key) => {
      const values = row[key];
      return total + (Array.isArray(values) ? values.length : 0);
    }, row.cash_amount ? 1 : 0);
  }

  function movementSummary(movement) {
    const row = movement && typeof movement === 'object' ? movement : {};
    const parts = [];
    if (Array.isArray(row.players) && row.players.length) parts.push(`${row.players.length} jugador(es)`);
    if (Array.isArray(row.picks) && row.picks.length) parts.push(`${row.picks.length} pick(s)`);
    if (Array.isArray(row.swaps) && row.swaps.length) parts.push(`${row.swaps.length} swap(s)`);
    if (Array.isArray(row.rights) && row.rights.length) parts.push(`${row.rights.length} derecho(s)`);
    if ((Array.isArray(row.cash) && row.cash.length) || row.cash_amount) parts.push('cash');
    return parts.join(' · ') || 'Sin movimientos';
  }

  function addMovementList(parent, title, movement) {
    el(parent, 'h4', { text: title });
    const row = movement && typeof movement === 'object' ? movement : {};
    const keys = [
      ['players', 'Jugadores'],
      ['picks', 'Picks'],
      ['swaps', 'Swaps'],
      ['rights', 'Derechos'],
      ['cash', 'Cash'],
    ];
    const list = el(parent, 'ul', { className: 'trade-archive-movement-list' });
    let added = false;
    keys.forEach(([key, label]) => {
      const values = Array.isArray(row[key]) ? row[key] : [];
      values.forEach((value) => {
        added = true;
        el(list, 'li', { text: `${label}: ${text(value)}` });
      });
    });
    if (row.cash_amount) {
      added = true;
      el(list, 'li', { text: `Cash: ${text(row.cash_amount)}` });
    }
    if (!added) el(list, 'li', { text: 'Sin movimientos registrados.' });
  }

  function ensureModal() {
    let backdrop = document.getElementById('tradeArchiveModal');
    if (backdrop) return backdrop;
    backdrop = el(document.body, 'div', {
      className: 'modal-backdrop section-hidden',
      attrs: { id: 'tradeArchiveModal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'tradeArchiveModalTitle' },
    });
    const card = el(backdrop, 'div', { className: 'modal-card trade-archive-modal' });
    const head = el(card, 'div', { className: 'modal-header' });
    el(head, 'h2', { attrs: { id: 'tradeArchiveModalTitle' }, text: 'Traspaso' });
    el(head, 'button', { className: 'danger', attrs: { id: 'tradeArchiveModalCloseBtn', type: 'button' }, text: 'Cerrar' });
    el(card, 'div', { attrs: { id: 'tradeArchiveModalBody' }, className: 'trade-archive-modal-body' });
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) closeModal();
    });
    backdrop.querySelector('#tradeArchiveModalCloseBtn')?.addEventListener('click', closeModal);
    return backdrop;
  }

  function openModal(title, buildBody) {
    const backdrop = ensureModal();
    const titleNode = backdrop.querySelector('#tradeArchiveModalTitle');
    const body = backdrop.querySelector('#tradeArchiveModalBody');
    if (titleNode) titleNode.textContent = title;
    clear(body);
    if (typeof buildBody === 'function') buildBody(body);
    backdrop.classList.remove('section-hidden');
  }

  function closeModal() {
    document.getElementById('tradeArchiveModal')?.classList.add('section-hidden');
  }

  function showTeamModal(trade, movement) {
    const code = text(movement?.team_code || '');
    openModal(`Traspaso ${trade.trade_id || trade.id} · ${code}`, (body) => {
      el(body, 'p', { className: 'section-subtitle', text: `${formatDate(trade.trade_date)} · Temporada ${trade.season_year}` });
      addMovementList(body, 'Envió', movement?.sent || {});
      addMovementList(body, 'Recibió', movement?.received || {});
    });
  }

  function showAggregateModal(trade) {
    openModal(`Traspaso ${trade.trade_id || trade.id} · Total`, (body) => {
      el(body, 'p', { className: 'section-subtitle', text: `${formatDate(trade.trade_date)} · ${trade.total_assets_moved || 0} activo(s) movidos` });
      (trade.team_movements || []).forEach((movement) => {
        const card = el(body, 'article', { className: 'trade-archive-team-card' });
        el(card, 'h3', { text: movement.team_code || '-' });
        el(card, 'p', { text: `Envió: ${movementSummary(movement.sent)}.` });
        el(card, 'p', { text: `Recibió: ${movementSummary(movement.received)}.` });
      });
    });
  }

  function tradeById(tradeId) {
    const parsed = Number(tradeId);
    return state.trades.find((trade) => Number(trade.id) === parsed) || null;
  }

  function renderRowsForSeason(container, season) {
    const article = el(container, 'article', { className: 'draft-order-round trade-archive-season' });
    el(article, 'h3', { text: `Temporada ${season.season_year}` });
    const wrap = el(article, 'div', { className: 'table-wrap draft-order-table-wrap' });
    const table = el(wrap, 'table', { className: 'draft-order-table trade-archive-table' });
    const thead = el(table, 'thead');
    const headRow = el(thead, 'tr');
    ['Trade ID', 'Fecha', 'Equipos', 'Activos movidos'].forEach((label) => el(headRow, 'th', { text: label }));
    if (state.admin) el(headRow, 'th', { text: 'Admin' });
    const tbody = el(table, 'tbody');
    const trades = Array.isArray(season.trades) ? season.trades : [];
    if (!trades.length) {
      const row = el(tbody, 'tr');
      el(row, 'td', { className: 'draft-order-empty', attrs: { colspan: state.admin ? 5 : 4 }, text: 'No hay traspasos registrados.' });
      return;
    }
    trades.forEach((trade) => {
      const row = el(tbody, 'tr');
      el(row, 'td', { text: trade.trade_id || trade.id });
      el(row, 'td', { text: formatDate(trade.trade_date) });
      const teamsCell = el(row, 'td', { className: 'trade-archive-teams-cell' });
      (trade.team_movements || []).forEach((movement) => {
        const btn = el(teamsCell, 'button', {
          className: 'tracker-team-btn trade-archive-team-btn',
          attrs: { type: 'button', 'data-trade-id': trade.id, 'data-team-code': movement.team_code },
          text: movement.team_code || '-',
        });
        btn.addEventListener('click', () => showTeamModal(trade, movement));
      });
      const totalCell = el(row, 'td');
      const totalBtn = el(totalCell, 'button', {
        className: 'ghost-link trade-archive-total-btn',
        attrs: { type: 'button' },
        text: String(trade.total_assets_moved || 0),
      });
      totalBtn.addEventListener('click', () => showAggregateModal(trade));
      if (state.admin) {
        const adminCell = el(row, 'td', { className: 'trade-archive-admin-actions' });
        const editBtn = el(adminCell, 'button', { attrs: { type: 'button' }, text: 'Editar' });
        editBtn.addEventListener('click', () => openEditModal(trade));
        const deleteBtn = el(adminCell, 'button', { className: 'danger', attrs: { type: 'button' }, text: 'Eliminar' });
        deleteBtn.addEventListener('click', () => deleteTrade(trade.id));
      }
    });
  }

  function render(data = {}) {
    state.trades = Array.isArray(data.trades) ? data.trades : [];
    const board = document.getElementById('tradeArchiveBoard');
    const status = document.getElementById('tradeArchiveStatus');
    if (status) status.textContent = '';
    clear(board);
    if (!board) return;
    const seasons = Array.isArray(data.seasons) ? data.seasons : [];
    if (!seasons.length) {
      el(board, 'div', { className: 'draft-order-empty', text: 'No hay traspasos registrados.' });
      return;
    }
    seasons.forEach((season) => renderRowsForSeason(board, season));
  }

  async function load(options = {}) {
    state.api = options.api || state.api || global.AnbaApi?.request;
    state.admin = Boolean(options.admin);
    if (typeof state.api !== 'function') throw new Error('trade_archive_api_missing');
    if (typeof options.setPageHeading === 'function') {
      options.setPageHeading('Traspasos', 'Archivo histórico de movimientos de la liga');
    }
    const data = await state.api('/api/trades/archive');
    render(data);
    return data;
  }

  async function refresh() {
    return load({ api: state.api, admin: state.admin });
  }

  function setStatus(message) {
    const status = document.getElementById('tradeArchiveStatus');
    if (status) status.textContent = message || '';
  }

  function parseTradeJson(raw) {
    const parsed = JSON.parse(String(raw || '').trim() || '[]');
    if (Array.isArray(parsed)) return { trades: parsed };
    return parsed;
  }

  async function importTrades() {
    const textarea = document.getElementById('tradeArchiveImportInput');
    const payload = parseTradeJson(textarea?.value || '');
    const result = await state.api('/api/trades/archive/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, { dedupe: true });
    setStatus(`${(result.created || []).length} traspaso(s) importados; ${(result.errors || []).length} error(es).`);
    if (textarea && !(result.errors || []).length) textarea.value = '';
    await refresh();
  }

  function openEditModal(trade) {
    openModal(`Editar traspaso ${trade.trade_id || trade.id}`, (body) => {
      const form = el(body, 'form', { className: 'trade-archive-edit-form' });
      const dateLabel = el(form, 'label');
      el(dateLabel, 'span', { text: 'Fecha' });
      el(dateLabel, 'input', { attrs: { name: 'trade_date', type: 'date', value: formatDate(trade.trade_date) } });
      const seasonLabel = el(form, 'label');
      el(seasonLabel, 'span', { text: 'Temporada' });
      el(seasonLabel, 'input', { attrs: { name: 'season_year', type: 'number', min: '1900', max: '2200', value: trade.season_year || '' } });
      const externalLabel = el(form, 'label');
      el(externalLabel, 'span', { text: 'Trade ID externo' });
      el(externalLabel, 'input', { attrs: { name: 'external_trade_id', value: trade.external_trade_id || '' } });
      const notesLabel = el(form, 'label');
      el(notesLabel, 'span', { text: 'Notas' });
      el(notesLabel, 'textarea', { attrs: { name: 'notes', rows: '2' }, text: trade.notes || '' });
      const movesLabel = el(form, 'label');
      el(movesLabel, 'span', { text: 'Movimientos por equipo (JSON)' });
      el(movesLabel, 'textarea', {
        attrs: { name: 'team_movements', rows: '10' },
        text: JSON.stringify(trade.team_movements || [], null, 2),
      });
      const actions = el(form, 'div', { className: 'trade-archive-modal-actions' });
      const save = el(actions, 'button', { attrs: { type: 'submit' }, text: 'Guardar' });
      el(actions, 'button', { className: 'danger', attrs: { type: 'button', 'data-close': 'true' }, text: 'Cancelar' })
        .addEventListener('click', closeModal);
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        save.disabled = true;
        try {
          const formData = new FormData(form);
          const payload = {
            trade_date: formData.get('trade_date'),
            season_year: Number(formData.get('season_year') || 0),
            external_trade_id: formData.get('external_trade_id'),
            notes: formData.get('notes'),
            team_movements: JSON.parse(String(formData.get('team_movements') || '[]')),
          };
          await state.api(`/api/trades/archive/${encodeURIComponent(trade.id)}`, {
            method: 'PATCH',
            body: JSON.stringify(payload),
          }, { dedupe: true });
          closeModal();
          await refresh();
        } catch (err) {
          alert(`No se pudo guardar el traspaso: ${err.message || err}`);
        } finally {
          save.disabled = false;
        }
      });
    });
  }

  async function deleteTrade(tradeId) {
    const trade = tradeById(tradeId);
    if (!trade || !confirm(`¿Eliminar el traspaso ${trade.trade_id || trade.id}?`)) return;
    await state.api(`/api/trades/archive/${encodeURIComponent(trade.id)}`, {
      method: 'DELETE',
      body: '{}',
    }, { dedupe: true });
    await refresh();
  }

  function bindAdminControls() {
    const importBtn = document.getElementById('tradeArchiveImportBtn');
    if (!importBtn || importBtn.dataset.tradeArchiveBound === 'true') return;
    importBtn.dataset.tradeArchiveBound = 'true';
    importBtn.addEventListener('click', () => {
      importTrades().catch((err) => {
        setStatus(`Import failed: ${err.message || err}`);
      });
    });
  }

  global.AnbaTradesArchive = {
    bindAdminControls,
    load,
    render,
  };
})(window);
