(function initAnbaWaitingList(global) {
  const Dom = global.AnbaDom || {};
  const appendElement = Dom.appendElement || ((parent, tagName, options = {}) => {
    const node = document.createElement(tagName);
    if (options.className) node.className = options.className;
    if (options.text !== undefined) node.textContent = options.text == null ? '' : String(options.text);
    parent.appendChild(node);
    return node;
  });
  const clear = Dom.clear || ((node) => node && node.replaceChildren());
  const emptyMessage = Dom.emptyMessage || ((message) => {
    const node = document.createElement('div');
    node.className = 'news-empty';
    node.textContent = message;
    return node;
  });

  const state = {
    api: null,
    admin: false,
    entries: [],
    loading: false,
    error: '',
    boundAdmin: false,
    editingEntry: null,
  };

  function request(path, opts = {}) {
    const api = state.api || global.AnbaApi?.request;
    if (!api) throw new Error('api_unavailable');
    return api(path, opts);
  }

  function todayIsoDate() {
    return new Date().toISOString().slice(0, 10);
  }

  function formatDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return '—';
    const [year, month, day] = raw.slice(0, 10).split('-');
    if (!year || !month || !day) return raw;
    return `${day}/${month}/${year}`;
  }

  function statusNode() {
    return document.getElementById('waitingListStatus');
  }

  function boardNode() {
    return document.getElementById('waitingListBoard');
  }

  function setStatus(message, tone = '') {
    const node = statusNode();
    if (!node) return;
    node.textContent = message || '';
    node.classList.toggle('error', tone === 'error');
  }

  function entryPayloadFromForm(form, options = {}) {
    const data = new FormData(form);
    const payload = {};
    ['display_name', 'registered_at', 'position', 'discord_id', 'notes'].forEach((key) => {
      const value = String(data.get(key) || '').trim();
      if (value || options.includeBlank) payload[key] = value;
    });
    return payload;
  }

  function renderRow(tbody, entry) {
    const tr = appendElement(tbody, 'tr');
    appendElement(tr, 'td', { text: entry.position || entry.plaza || '—', className: 'waiting-list-position-cell' });
    appendElement(tr, 'td', { text: entry.display_name || entry.name || '—', className: 'waiting-list-name-cell' });
    appendElement(tr, 'td', { text: formatDate(entry.registered_at), className: 'waiting-list-date-cell' });
    if (state.admin) {
      const actions = appendElement(tr, 'td', { className: 'waiting-list-actions' });
      const editBtn = appendElement(actions, 'button', { text: 'Editar', className: 'ghost small', attrs: { type: 'button' } });
      editBtn.addEventListener('click', () => showEditModal(entry));
      const deleteBtn = appendElement(actions, 'button', { text: 'Eliminar', className: 'danger small', attrs: { type: 'button' } });
      deleteBtn.addEventListener('click', () => deleteEntry(entry, deleteBtn));
    }
    return tr;
  }

  function renderTable() {
    const board = boardNode();
    if (!board) return;
    clear(board);
    if (state.loading) {
      board.appendChild(emptyMessage('Cargando lista de espera...'));
      return;
    }
    if (state.error) {
      board.appendChild(emptyMessage(state.error, 'news-empty error'));
      return;
    }
    if (!state.entries.length) {
      board.appendChild(emptyMessage('Todavía no hay usuarios en lista de espera.'));
      return;
    }
    const wrap = appendElement(board, 'div', { className: 'draft-order-table-wrap waiting-list-table-wrap' });
    const table = appendElement(wrap, 'table', { className: 'draft-order-table waiting-list-table' });
    const thead = appendElement(table, 'thead');
    const headRow = appendElement(thead, 'tr');
    ['Plaza', 'Nombre', 'Fecha de inscripción'].forEach((label) => appendElement(headRow, 'th', { text: label }));
    if (state.admin) appendElement(headRow, 'th', { text: 'Admin' });
    const tbody = appendElement(table, 'tbody');
    state.entries.forEach((entry) => renderRow(tbody, entry));
  }

  function editModal() {
    let modal = document.getElementById('waitingListEditModal');
    if (modal) return modal;
    modal = appendElement(document.body, 'div', {
      className: 'modal-backdrop section-hidden',
      attrs: {
        id: 'waitingListEditModal',
        role: 'dialog',
        'aria-modal': 'true',
        'aria-labelledby': 'waitingListEditTitle',
      },
    });
    const card = appendElement(modal, 'div', { className: 'modal-card waiting-list-edit-modal' });
    const header = appendElement(card, 'div', { className: 'modal-header' });
    appendElement(header, 'h2', { text: 'Editar plaza', attrs: { id: 'waitingListEditTitle' } });
    const closeBtn = appendElement(header, 'button', { text: 'Cerrar', className: 'danger', attrs: { type: 'button' } });
    const form = appendElement(card, 'form', { className: 'waiting-list-edit-form', attrs: { id: 'waitingListEditForm' } });
    [
      ['waitingListEditNameInput', 'display_name', 'Nombre', 'text'],
      ['waitingListEditDateInput', 'registered_at', 'Fecha de inscripción', 'date'],
      ['waitingListEditPositionInput', 'position', 'Plaza', 'number'],
      ['waitingListEditDiscordInput', 'discord_id', 'Discord ID', 'text'],
      ['waitingListEditNotesInput', 'notes', 'Notas', 'text'],
    ].forEach(([id, name, label, type]) => {
      const labelNode = appendElement(form, 'label', { attrs: { for: id } });
      appendElement(labelNode, 'span', { text: label });
      const attrs = { id, name, type, autocomplete: 'off' };
      if (type === 'number') attrs.min = '1';
      appendElement(labelNode, 'input', { attrs });
    });
    const actions = appendElement(form, 'div', { className: 'waiting-list-modal-actions' });
    appendElement(actions, 'button', { text: 'Guardar cambios', attrs: { type: 'submit' } });
    appendElement(actions, 'button', { text: 'Cancelar', className: 'ghost', attrs: { type: 'button', id: 'waitingListEditCancelBtn' } });
    closeBtn.addEventListener('click', hideEditModal);
    modal.addEventListener('click', (event) => {
      if (event.target === modal) hideEditModal();
    });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      saveEdit(form);
    });
    document.getElementById('waitingListEditCancelBtn')?.addEventListener('click', hideEditModal);
    return modal;
  }

  function showEditModal(entry) {
    state.editingEntry = entry;
    const modal = editModal();
    modal.querySelector('#waitingListEditNameInput').value = entry.display_name || entry.name || '';
    modal.querySelector('#waitingListEditDateInput').value = String(entry.registered_at || '').slice(0, 10);
    modal.querySelector('#waitingListEditPositionInput').value = entry.position || entry.plaza || '';
    modal.querySelector('#waitingListEditDiscordInput').value = entry.discord_id || '';
    modal.querySelector('#waitingListEditNotesInput').value = entry.notes || '';
    modal.classList.remove('section-hidden');
  }

  function hideEditModal() {
    state.editingEntry = null;
    document.getElementById('waitingListEditModal')?.classList.add('section-hidden');
  }

  async function saveEdit(form) {
    if (!state.editingEntry) return;
    const entryId = state.editingEntry.id;
    const button = form.querySelector('button[type="submit"]');
    const run = async () => {
      const data = await request(`/api/waiting-list/${encodeURIComponent(entryId)}`, {
        method: 'PATCH',
        body: JSON.stringify(entryPayloadFromForm(form, { includeBlank: true })),
      });
      const updated = data?.entry;
      if (updated) {
        state.entries = state.entries.map((entry) => (entry.id === updated.id ? updated : entry))
          .sort((a, b) => Number(a.position || 0) - Number(b.position || 0));
      }
      hideEditModal();
      await load({ api: state.api, admin: state.admin });
    };
    try {
      if (global.AnbaApi?.withSubmissionLock) await global.AnbaApi.withSubmissionLock(button, run);
      else await run();
      setStatus('Entrada actualizada.');
    } catch (err) {
      setStatus(err.message || 'No se pudo actualizar la entrada.', 'error');
    }
  }

  async function deleteEntry(entry, button) {
    if (!global.confirm(`Eliminar a ${entry.display_name || entry.name || 'esta persona'} de la lista de espera?`)) return;
    const run = async () => {
      await request(`/api/waiting-list/${encodeURIComponent(entry.id)}`, { method: 'DELETE' });
      state.entries = state.entries.filter((candidate) => candidate.id !== entry.id);
      renderTable();
    };
    try {
      if (global.AnbaApi?.withSubmissionLock) await global.AnbaApi.withSubmissionLock(button, run);
      else await run();
      setStatus('Entrada eliminada.');
    } catch (err) {
      setStatus(err.message || 'No se pudo eliminar la entrada.', 'error');
    }
  }

  function bindAdminControls() {
    if (state.boundAdmin) return;
    const form = document.getElementById('waitingListAdminForm');
    if (!form) return;
    state.boundAdmin = true;
    const dateInput = document.getElementById('waitingListDateInput');
    if (dateInput && !dateInput.value) dateInput.value = todayIsoDate();
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = document.getElementById('waitingListAddBtn');
      const run = async () => {
        const data = await request('/api/waiting-list', {
          method: 'POST',
          body: JSON.stringify(entryPayloadFromForm(form)),
        });
        form.reset();
        if (dateInput) dateInput.value = todayIsoDate();
        if (data?.entry) state.entries.push(data.entry);
        await load({ api: state.api, admin: state.admin });
      };
      try {
        if (global.AnbaApi?.withSubmissionLock) await global.AnbaApi.withSubmissionLock(button, run);
        else await run();
        setStatus('Entrada añadida.');
      } catch (err) {
        setStatus(err.message || 'No se pudo añadir la entrada.', 'error');
      }
    });
  }

  async function load(options = {}) {
    state.api = options.api || state.api;
    state.admin = Boolean(options.admin);
    if (typeof options.setPageHeading === 'function') {
      options.setPageHeading('Lista de espera', 'Usuarios esperando plaza para entrar en la liga');
    }
    if (state.admin) bindAdminControls();
    state.loading = true;
    state.error = '';
    setStatus('');
    renderTable();
    try {
      const data = await request('/api/waiting-list');
      state.entries = Array.isArray(data?.entries) ? data.entries : [];
    } catch (err) {
      state.entries = [];
      state.error = err.message || 'No se pudo cargar la lista de espera.';
    } finally {
      state.loading = false;
      renderTable();
    }
  }

  global.AnbaWaitingList = {
    bindAdminControls,
    load,
  };
})(window);
