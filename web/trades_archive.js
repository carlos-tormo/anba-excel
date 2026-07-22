(function initAnbaTradesArchive(global) {
  const dom = () => global.AnbaDom || {};
  const state = {
    api: null,
    admin: false,
    trades: [],
    selectedSeasonYear: null,
    selectedTeamCode: '',
    selectedGmName: '',
  };

  function clear(node) {
    if (dom().clear) dom().clear(node);
    else if (node) node.replaceChildren();
  }

  function el(parent, tagName, options = {}) {
    if (dom().appendElement && parent) return dom().appendElement(parent, tagName, options);
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

  function formatSeasonLabel(value) {
    const startYear = Number(value);
    if (!Number.isInteger(startYear) || startYear < 1900 || startYear > 2200) return text(value || '-');
    return `${startYear}-${String((startYear + 1) % 100).padStart(2, '0')}`;
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

  function teamDisplayName(movement) {
    return text(movement?.team_name || movement?.team_code || '-');
  }

  function gmDisplayName(movement) {
    return text(movement?.gm_name || movement?.gm || movement?.timeline_gm_name || '');
  }

  function tradeMatchesFilters(trade) {
    const movements = Array.isArray(trade?.team_movements) ? trade.team_movements : [];
    if (state.selectedTeamCode) {
      const teamMatch = movements.some((movement) => text(movement?.team_code).toUpperCase() === state.selectedTeamCode);
      if (!teamMatch) return false;
    }
    if (state.selectedGmName) {
      const gmMatch = movements.some((movement) => gmDisplayName(movement) === state.selectedGmName);
      if (!gmMatch) return false;
    }
    return true;
  }

  function filteredSeason(season) {
    const trades = (Array.isArray(season?.trades) ? season.trades : []).filter(tradeMatchesFilters);
    return { ...(season || {}), trades };
  }

  function teamLogoPath(code) {
    const normalized = text(code).trim().toUpperCase();
    if (!normalized) return '';
    const fileMap = { LAL: 'lal.png' };
    return `/team-icons/${fileMap[normalized] || `${normalized}.png`}`;
  }

  function appendTeamLogo(parent, code) {
    const normalized = text(code).trim().toUpperCase();
    const wrap = el(parent, 'span', { className: 'trade-archive-team-logo', attrs: { 'aria-hidden': 'true' } });
    const fallback = el(wrap, 'span', { text: normalized || '-' });
    const path = teamLogoPath(normalized);
    if (!path) return wrap;
    const img = el(wrap, 'img', { attrs: { alt: '' } });
    fallback.hidden = true;
    img.addEventListener('error', () => {
      img.hidden = true;
      fallback.hidden = false;
    });
    if (dom().setSafeImageSource) {
      dom().setSafeImageSource(img, path);
    } else {
      img.src = path;
    }
    return wrap;
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
    const gmName = gmDisplayName(movement);
    openModal(`Traspaso ${trade.trade_id || trade.id} · ${code}`, (body) => {
      el(body, 'p', { className: 'section-subtitle', text: `${formatDate(trade.trade_date)} · Temporada ${formatSeasonLabel(trade.season_year)}` });
      if (gmName) el(body, 'p', { className: 'section-subtitle', text: `GM: ${gmName}` });
      addMovementList(body, 'Envió', movement?.sent || {});
      addMovementList(body, 'Recibió', movement?.received || {});
    });
  }

  function showAggregateModal(trade) {
    openModal(`Traspaso ${trade.trade_id || trade.id} · Total`, (body) => {
      el(body, 'p', { className: 'section-subtitle', text: `${formatDate(trade.trade_date)} · Temporada ${formatSeasonLabel(trade.season_year)} · ${trade.total_assets_moved || 0} activo(s) movidos` });
      (trade.team_movements || []).forEach((movement) => {
        const card = el(body, 'article', { className: 'trade-archive-team-card' });
        const head = el(card, 'div', { className: 'trade-archive-team-card-head' });
        appendTeamLogo(head, movement.team_code);
        const titleWrap = el(head, 'div');
        el(titleWrap, 'h3', { text: teamDisplayName(movement) });
        if (movement.team_code && teamDisplayName(movement) !== text(movement.team_code)) {
          el(titleWrap, 'p', { className: 'trade-archive-team-code-line', text: movement.team_code });
        }
        if (gmDisplayName(movement)) el(card, 'p', { className: 'trade-archive-gm-line', text: `GM: ${gmDisplayName(movement)}` });
        const movementGrid = el(card, 'div', { className: 'trade-archive-aggregate-movements' });
        const sent = el(movementGrid, 'div');
        addMovementList(sent, 'Envió', movement.sent || {});
        const received = el(movementGrid, 'div');
        addMovementList(received, 'Recibió', movement.received || {});
      });
    });
  }

  function tradeById(tradeId) {
    const parsed = Number(tradeId);
    return state.trades.find((trade) => Number(trade.id) === parsed) || null;
  }

  function renderRowsForSeason(container, season) {
    const article = el(container, 'article', { className: 'draft-order-round trade-archive-season' });
    el(article, 'h3', { text: `Temporada ${formatSeasonLabel(season.season_year)}` });
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
          attrs: {
            type: 'button',
            title: teamDisplayName(movement),
            'data-trade-id': trade.id,
            'data-team-code': movement.team_code,
          },
        });
        const main = el(btn, 'span', { className: 'trade-archive-team-main' });
        appendTeamLogo(main, movement.team_code);
        el(main, 'span', { className: 'trade-archive-team-name', text: movement.team_code || '-' });
        if (gmDisplayName(movement)) {
          el(btn, 'span', { className: 'trade-archive-gm-line', text: `GM: ${gmDisplayName(movement)}` });
        }
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

  function selectedSeason(seasons) {
    const rows = Array.isArray(seasons) ? seasons : [];
    if (!rows.length) return null;
    const selected = Number(state.selectedSeasonYear);
    const existing = rows.find((season) => Number(season.season_year) === selected);
    if (existing) return existing;
    const latest = [...rows].sort((a, b) => Number(b.season_year || 0) - Number(a.season_year || 0))[0];
    state.selectedSeasonYear = Number(latest?.season_year || rows[0].season_year);
    return latest || rows[0];
  }

  function renderSeasonSelector(seasons, activeSeason) {
    const board = document.getElementById('tradeArchiveBoard');
    const parent = board?.parentElement;
    if (!parent || !board) return;
    let controls = document.getElementById('tradeArchiveSeasonControls');
    if (!controls) {
      controls = el(null, 'div', { className: 'trade-archive-season-controls', attrs: { id: 'tradeArchiveSeasonControls' } });
      parent.insertBefore(controls, board);
    }
    clear(controls);
    if (!Array.isArray(seasons) || !seasons.length) {
      controls.classList.add('section-hidden');
      return;
    }
    controls.classList.remove('section-hidden');
    if (seasons.length <= 1) return;
    const label = el(controls, 'label', { className: 'season-view-control', attrs: { for: 'tradeArchiveSeasonSelect' } });
    el(label, 'span', { text: 'Temporada' });
    const select = el(label, 'select', { attrs: { id: 'tradeArchiveSeasonSelect' } });
    [...seasons]
      .sort((a, b) => Number(b.season_year || 0) - Number(a.season_year || 0))
      .forEach((season) => {
        el(select, 'option', {
          attrs: { value: season.season_year, selected: Number(season.season_year) === Number(activeSeason?.season_year) },
          text: formatSeasonLabel(season.season_year),
        });
      });
    select.addEventListener('change', () => {
      state.selectedSeasonYear = Number(select.value);
      render({ trades: state.trades, seasons });
    });
  }

  function filterOptionsForSeason(season) {
    const teams = new Map();
    const gms = new Set();
    (Array.isArray(season?.trades) ? season.trades : []).forEach((trade) => {
      (Array.isArray(trade?.team_movements) ? trade.team_movements : []).forEach((movement) => {
        const code = text(movement?.team_code).trim().toUpperCase();
        if (code) teams.set(code, teamDisplayName(movement));
        const gmName = gmDisplayName(movement);
        if (gmName) gms.add(gmName);
      });
    });
    return {
      teams: [...teams.entries()].sort((a, b) => a[0].localeCompare(b[0], 'es')),
      gms: [...gms].sort((a, b) => a.localeCompare(b, 'es')),
    };
  }

  function renderFilters(seasons, activeSeason) {
    const controls = document.getElementById('tradeArchiveSeasonControls');
    if (!controls || !Array.isArray(seasons) || !seasons.length) return;
    const options = filterOptionsForSeason(activeSeason);
    if (state.selectedTeamCode && !options.teams.some(([code]) => code === state.selectedTeamCode)) {
      state.selectedTeamCode = '';
    }
    if (state.selectedGmName && !options.gms.includes(state.selectedGmName)) {
      state.selectedGmName = '';
    }

    const teamLabel = el(controls, 'label', { className: 'season-view-control', attrs: { for: 'tradeArchiveTeamFilter' } });
    el(teamLabel, 'span', { text: 'Equipo' });
    const teamSelect = el(teamLabel, 'select', { attrs: { id: 'tradeArchiveTeamFilter' } });
    el(teamSelect, 'option', { attrs: { value: '' }, text: 'Todos' });
    options.teams.forEach(([code, label]) => {
      el(teamSelect, 'option', {
        attrs: { value: code, selected: code === state.selectedTeamCode },
        text: label && label !== code ? `${code} · ${label}` : code,
      });
    });
    teamSelect.addEventListener('change', () => {
      state.selectedTeamCode = text(teamSelect.value).toUpperCase();
      render({ trades: state.trades, seasons });
    });

    const gmLabel = el(controls, 'label', { className: 'season-view-control', attrs: { for: 'tradeArchiveGmFilter' } });
    el(gmLabel, 'span', { text: 'GM' });
    const gmSelect = el(gmLabel, 'select', { attrs: { id: 'tradeArchiveGmFilter' } });
    el(gmSelect, 'option', { attrs: { value: '' }, text: 'Todos' });
    options.gms.forEach((gmName) => {
      el(gmSelect, 'option', {
        attrs: { value: gmName, selected: gmName === state.selectedGmName },
        text: gmName,
      });
    });
    gmSelect.addEventListener('change', () => {
      state.selectedGmName = text(gmSelect.value);
      render({ trades: state.trades, seasons });
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
      renderSeasonSelector([], null);
      el(board, 'div', { className: 'draft-order-empty', text: 'No hay traspasos registrados.' });
      return;
    }
    const activeSeason = selectedSeason(seasons);
    renderSeasonSelector(seasons, activeSeason);
    renderFilters(seasons, activeSeason);
    renderRowsForSeason(board, filteredSeason(activeSeason));
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

  function renderImportErrors(errors = []) {
    const container = document.getElementById('tradeArchiveImportErrors');
    clear(container);
    if (!container || !Array.isArray(errors) || !errors.length) return;
    el(container, 'div', { className: 'trade-archive-import-error-title', text: 'Filas con error' });
    const list = el(container, 'ul');
    errors.slice(0, 25).forEach((error) => {
      const index = Number(error?.index);
      const rowLabel = Number.isFinite(index) ? `Fila ${index + 1}` : 'Fila desconocida';
      el(list, 'li', { text: `${rowLabel}: ${text(error?.error || 'trade_import_failed')}` });
    });
    if (errors.length > 25) {
      el(container, 'p', { text: `Hay ${errors.length - 25} error(es) adicionales no mostrados.` });
    }
  }

  function parseTradeJson(raw) {
    const trimmed = String(raw || '').trim();
    if (!trimmed) throw new Error('Pega JSON o selecciona un archivo .json antes de importar.');
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return { trades: parsed };
    if (parsed && typeof parsed === 'object' && Array.isArray(parsed.trades)) return parsed;
    throw new Error('El JSON debe ser un array de traspasos o un objeto con la propiedad "trades".');
  }

  async function loadImportFile(fileInput) {
    const file = fileInput?.files?.[0];
    if (!file) return;
    if (file.size > 1024 * 1024) {
      throw new Error('El archivo JSON supera 1 MB. Divide la importación en archivos más pequeños.');
    }
    const textarea = document.getElementById('tradeArchiveImportInput');
    if (textarea) textarea.value = await file.text();
    renderImportErrors([]);
    setStatus(`Archivo cargado: ${file.name}`);
  }

  async function importTrades(button = null) {
    const submit = async () => {
      renderImportErrors([]);
      setStatus('');
      const textarea = document.getElementById('tradeArchiveImportInput');
      const payload = parseTradeJson(textarea?.value || '');
      const result = await state.api('/api/trades/archive/import', {
        method: 'POST',
        body: JSON.stringify(payload),
      }, { dedupe: true, requestKey: 'POST /api/trades/archive/import' });
      const createdCount = (result.created || []).length;
      const errorCount = (result.errors || []).length;
      const totalCount = result.total ?? createdCount + errorCount;
      setStatus(`${createdCount}/${totalCount} traspaso(s) importados; ${errorCount} error(es).`);
      renderImportErrors(result.errors || []);
      if (textarea && !errorCount) textarea.value = '';
      const fileInput = document.getElementById('tradeArchiveImportFile');
      if (fileInput && !errorCount) fileInput.value = '';
      await refresh();
      return result;
    };
    if (global.AnbaApi?.withSubmissionLock) {
      return global.AnbaApi.withSubmissionLock(button, submit, { pendingText: 'Importando...' });
    }
    return submit();
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
    if (importBtn && importBtn.dataset.tradeArchiveBound !== 'true') {
      importBtn.dataset.tradeArchiveBound = 'true';
      importBtn.addEventListener('click', () => {
        importTrades(importBtn).catch((err) => {
          renderImportErrors([]);
          setStatus(`Import failed: ${err.message || err}`);
        });
      });
    }
    const fileInput = document.getElementById('tradeArchiveImportFile');
    if (fileInput && fileInput.dataset.tradeArchiveBound !== 'true') {
      fileInput.dataset.tradeArchiveBound = 'true';
      fileInput.addEventListener('change', () => {
        loadImportFile(fileInput).catch((err) => {
          fileInput.value = '';
          setStatus(`File load failed: ${err.message || err}`);
        });
      });
    }
    const textarea = document.getElementById('tradeArchiveImportInput');
    if (textarea && textarea.dataset.tradeArchiveBound !== 'true') {
      textarea.dataset.tradeArchiveBound = 'true';
      textarea.addEventListener('input', () => {
        renderImportErrors([]);
      });
    }
  }

  global.AnbaTradesArchive = {
    bindAdminControls,
    load,
    render,
  };
})(window);
