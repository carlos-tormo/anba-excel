(function () {
  function htmlEscape(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escapeWith(escapeHtml, value) {
    return typeof escapeHtml === 'function' ? escapeHtml(value) : htmlEscape(value);
  }

  function sourceRows(live, draftOrder) {
    return (draftOrder?.draft_order || live?.draft_order || []);
  }

  function orderedRows(live, draftOrder) {
    return sourceRows(live, draftOrder)
      .slice()
      .sort((a, b) => {
        const roundA = String(a.draft_round || '') === '1st' ? 1 : String(a.draft_round || '') === '2nd' ? 2 : 3;
        const roundB = String(b.draft_round || '') === '1st' ? 1 : String(b.draft_round || '') === '2nd' ? 2 : 3;
        return roundA - roundB || Number(a.pick_number || 0) - Number(b.pick_number || 0) || Number(a.id || 0) - Number(b.id || 0);
      });
  }

  function currentPick(live, draftOrder) {
    const currentId = Number(live?.current_pick_id || 0);
    if (!currentId) return null;
    return (live?.draft_order || draftOrder?.draft_order || [])
      .find((row) => Number(row.id || 0) === currentId) || null;
  }

  function upcomingRows(live, draftOrder) {
    const rows = orderedRows(live, draftOrder);
    if (!rows.length) return [];
    const currentId = Number(live?.current_pick_id || 0);
    let index = currentId ? rows.findIndex((row) => Number(row.id || 0) === currentId) : -1;
    if (index < 0) {
      index = rows.findIndex((row) => !String(row.selection_text || '').trim() && Number(row.skipped || 0) === 0);
    }
    return rows.slice(index >= 0 ? index : 0);
  }

  function remainingSeconds(live, nowMs = Date.now()) {
    const state = live || {};
    const duration = Number(state.duration_seconds || 180);
    if (!state.enabled || !state.started_at) return duration;
    const started = Date.parse(state.started_at);
    const serverNow = Date.parse(state.server_now || '');
    if (!Number.isFinite(started) || !Number.isFinite(serverNow)) {
      return Math.max(0, Number(state.remaining_seconds || duration));
    }
    const loadedAt = Number(state.loaded_at_ms || nowMs);
    const elapsedSinceLoad = Math.max(0, nowMs - loadedAt);
    const estimatedNow = serverNow + elapsedSinceLoad;
    return Math.max(0, Math.ceil((started + duration * 1000 - estimatedNow) / 1000));
  }

  function formatClock(seconds) {
    const total = Math.max(0, Number(seconds || 0));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${mins}:${String(secs).padStart(2, '0')}`;
  }

  function pickLabel(row) {
    if (!row) return 'Sin picks configurados';
    return `#${row.pick_number} · ${row.draft_round} · ${row.owner_team_code}`;
  }

  function upcomingHtml(live, draftOrder, escapeHtml) {
    const rows = upcomingRows(live, draftOrder);
    if (!rows.length) return '';
    const currentId = Number(live?.current_pick_id || 0);
    const esc = (value) => escapeWith(escapeHtml, value);
    return `
      <div class="draft-live-upcoming">
        <div class="draft-live-upcoming-head">
          <span>Orden desde el pick actual</span>
          <strong>${esc(rows.length)} picks</strong>
        </div>
        <ol class="draft-live-upcoming-list">
          ${rows.map((row) => {
            const isCurrent = currentId && Number(row.id || 0) === currentId;
            const selection = String(row.selection_text || '').trim();
            return `
              <li class="${isCurrent ? 'is-current-draft-pick' : ''}">
                <span class="draft-live-upcoming-number">#${esc(row.pick_number || '')}</span>
                <span class="draft-live-upcoming-main">
                  <strong>${esc(row.owner_team_code || '')}</strong>
                  <small>${esc(row.draft_round || '')}${selection ? ` · ${esc(selection)}` : ''}</small>
                </span>
              </li>
            `;
          }).join('')}
        </ol>
      </div>
    `;
  }

  function selectionHtml(row, options = {}) {
    const esc = (value) => escapeWith(options.escapeHtml, value);
    const selection = String(row?.selection_text || '').trim();
    const skipped = Number(row?.skipped || 0) !== 0;
    const pendingSelection = String(row?.pending_selection_text || '').trim();
    const canSelect = typeof options.canSelect === 'function' ? options.canSelect(row) : false;
    if (!selection && canSelect) {
      if (pendingSelection) {
        return `<span class="draft-live-pending draft-live-pending--request">${esc(options.pendingRequestLabel || 'Solicitud enviada')}</span>`;
      }
      return `<button type="button" class="draft-live-pick-btn draft-live-pick-btn--now" data-draft-live-pick="${esc(row?.id)}">${esc(options.selectButtonLabel || 'ELIGE AHORA')}</button>`;
    }
    if (!selection && pendingSelection) {
      return `<span class="draft-live-pending draft-live-pending--request">${esc(options.pendingRequestLabel || 'Solicitud enviada')}</span>`;
    }
    if (!selection) return '<span class="draft-live-pending">Pendiente</span>';
    const cls = skipped ? 'draft-live-selection draft-live-selection--skipped' : 'draft-live-selection';
    const processedType = String(row?.processed_type || '').trim();
    const processedTag = options.includeProcessedTag && processedType
      ? `<span class="draft-live-processed">Procesado: ${processedType === 'draft_cap_hold' ? 'cap hold' : 'derechos'}</span>`
      : '';
    return `<span class="${cls}">${esc(selection)}</span>${processedTag}`;
  }

  function choiceOptionsHtml(live, selected = '', escapeHtml) {
    const normalized = String(selected || '').trim();
    const options = Array.isArray(live?.options) ? live.options : [];
    const esc = (value) => escapeWith(escapeHtml, value);
    return [
      '<option value="">Selecciona jugador</option>',
      ...options.map((option) => `<option value="${esc(option)}"${option === normalized ? ' selected' : ''}>${esc(option)}</option>`),
      `<option value="__other__"${normalized === '__other__' ? ' selected' : ''}>Otro</option>`,
    ].join('');
  }

  function currentPickOptionsHtml(draftOrder, selectedId = '', escapeHtml) {
    const selected = String(selectedId || '');
    const esc = (value) => escapeWith(escapeHtml, value);
    return (draftOrder?.draft_order || [])
      .map((row) => {
        const id = String(row.id || '');
        return `<option value="${esc(id)}"${id === selected ? ' selected' : ''}>${esc(pickLabel(row))}</option>`;
      })
      .join('');
  }

  function adminPanelHtml(live, draftOrder, escapeHtml) {
    const state = live || {};
    const current = currentPick(state, draftOrder) || upcomingRows(state, draftOrder)[0] || null;
    const esc = (value) => escapeWith(escapeHtml, value);
    return `
      <div class="draft-live-card draft-live-card--admin">
        <div class="draft-live-status">
          <span class="draft-live-kicker">${state.enabled ? 'Modo draft activo' : 'Modo draft inactivo'}</span>
          <strong>${esc(pickLabel(current))}</strong>
          <span>${state.enabled ? 'El contador está corriendo para el pick actual.' : 'Activa el modo draft para abrir elecciones de GM.'}</span>
        </div>
        ${state.enabled ? `<div class="draft-live-clock" data-draft-live-countdown>${formatClock(remainingSeconds(state))}</div>` : '<div class="draft-live-clock draft-live-clock--idle">--</div>'}
      </div>
      ${upcomingHtml(state, draftOrder, escapeHtml)}
      <div class="draft-live-admin-controls">
        <label class="settings-check">
          <input id="draftLiveEnabledInput" type="checkbox" ${state.enabled ? 'checked' : ''}>
          <span>Modo draft</span>
        </label>
        <label>
          <span>Duración</span>
          <input id="draftLiveDurationInput" type="number" min="10" max="3600" step="5" value="${esc(state.duration_seconds || 180)}">
        </label>
        <label>
          <span>Pick actual</span>
          <select id="draftLiveCurrentPickSelect">${currentPickOptionsHtml(draftOrder, state.current_pick_id || '', escapeHtml)}</select>
        </label>
        <button id="draftLiveSaveBtn" type="button">Guardar modo draft</button>
        <button id="draftLiveRestartBtn" type="button">Reiniciar contador</button>
        <button id="draftLivePreviousBtn" type="button">Pick anterior</button>
        <button id="draftLiveNextBtn" type="button">Avanzar pick</button>
        <button id="draftLiveSkipBtn" type="button" class="danger">Saltar al siguiente</button>
      </div>
      <label class="draft-live-options-editor">
        <span>Opciones de jugadores elegibles, una por línea</span>
        <textarea id="draftLiveOptionsInput" rows="5" placeholder="Jugador 1&#10;Jugador 2">${esc(state.options_text || '')}</textarea>
      </label>
    `;
  }

  function bindAdminPanelControls(options = {}) {
    const doc = options.document || document;
    const api = options.api;
    const alertFn = options.alert || alert;
    const confirmFn = options.confirm || confirm;
    const draftYear = () => Number(options.getDraftYear ? options.getDraftYear() : 0);
    const currentLive = () => (typeof options.getLive === 'function' ? options.getLive() : options.live) || {};
    const staleMessage = 'El draft cambió en otra pestaña. Actualiza la pantalla e inténtalo de nuevo.';
    const applyResult = (result) => {
      if (typeof options.onState === 'function') options.onState(result);
      if (typeof options.onRefresh === 'function') options.onRefresh();
    };
    const save = async (extra = {}) => {
      const result = await api('/api/draft-live/settings', {
        method: 'POST',
        body: JSON.stringify({
          draft_year: draftYear(),
          enabled: doc.getElementById('draftLiveEnabledInput')?.checked,
          duration_seconds: Number(doc.getElementById('draftLiveDurationInput')?.value || 180),
          current_pick_id: Number(doc.getElementById('draftLiveCurrentPickSelect')?.value || 0) || null,
          options_text: doc.getElementById('draftLiveOptionsInput')?.value || '',
          expected_state_version: currentLive().state_version || undefined,
          ...extra,
        }),
      });
      applyResult(result);
    };
    const control = async (action) => {
      const result = await api('/api/draft-live/control', {
        method: 'POST',
        body: JSON.stringify({
          draft_year: draftYear(),
          action,
          expected_state_version: currentLive().state_version || undefined,
        }),
      });
      applyResult(result);
    };
    doc.getElementById('draftLiveSaveBtn')?.addEventListener('click', () => {
      save().catch((err) => alertFn(err.message === 'stale_entity_version' ? staleMessage : `Draft live save failed: ${err.message}`));
    });
    doc.getElementById('draftLiveRestartBtn')?.addEventListener('click', () => {
      save({ reset_timer: true }).catch((err) => alertFn(err.message === 'stale_entity_version' ? staleMessage : `Draft timer restart failed: ${err.message}`));
    });
    doc.getElementById('draftLivePreviousBtn')?.addEventListener('click', () => {
      control('previous').catch((err) => alertFn(err.message === 'stale_entity_version' ? staleMessage : `Draft previous failed: ${err.message}`));
    });
    doc.getElementById('draftLiveNextBtn')?.addEventListener('click', () => {
      control('next').catch((err) => alertFn(err.message === 'stale_entity_version' ? staleMessage : `Draft next failed: ${err.message}`));
    });
    doc.getElementById('draftLiveSkipBtn')?.addEventListener('click', () => {
      if (!confirmFn('¿Saltar el pick actual y pasar al siguiente?')) return;
      control('skip').catch((err) => alertFn(err.message === 'stale_entity_version' ? staleMessage : `Draft skip failed: ${err.message}`));
    });
  }

  function adminPickModalHtml(row, live, escapeHtml) {
    const esc = (value) => escapeWith(escapeHtml, value);
    const isCurrent = Number(row?.id || 0) === Number(live?.current_pick_id || 0);
    const hasSelection = Boolean(String(row?.selection_text || '').trim());
    const existingOption = String(row?.option_value || '').trim();
    const isOther = hasSelection && existingOption && !(live?.options || []).includes(existingOption) && existingOption !== 'Saltado';
    return {
      isOther,
      html: `
        <div class="draft-live-modal" role="dialog" aria-modal="true" aria-label="Corregir elección">
          <div class="draft-live-modal-head">
            <div>
              <span>${esc(row?.draft_round || '')} · Pick #${esc(row?.pick_number || '')}</span>
              <h3>${esc(row?.owner_team_code || '')} elige</h3>
            </div>
            <button type="button" class="danger" data-draft-live-close>Cerrar</button>
          </div>
          <label>
            <span>Jugador</span>
            <select data-draft-live-choice>${choiceOptionsHtml(live, isOther ? '__other__' : existingOption, escapeHtml)}</select>
          </label>
          <label class="${isOther ? '' : 'section-hidden'}" data-draft-live-custom-wrap>
            <span>Otro</span>
            <input data-draft-live-custom type="text" placeholder="Nombre del jugador" value="${esc(isOther ? row?.selection_text || '' : '')}">
          </label>
          <label class="settings-check">
            <input data-draft-live-advance type="checkbox" ${isCurrent ? 'checked' : ''}>
            <span>Avanzar al siguiente tras guardar</span>
          </label>
          <div class="draft-live-modal-actions">
            ${hasSelection ? '<button type="button" class="danger" data-draft-live-clear>Limpiar elección</button>' : ''}
            <button type="button" data-draft-live-submit>Guardar elección</button>
          </div>
        </div>
      `,
    };
  }

  function openAdminPickModal(row, options = {}) {
    if (!row) return;
    const doc = options.document || document;
    const api = options.api;
    const alertFn = options.alert || alert;
    const confirmFn = options.confirm || confirm;
    const live = options.live || {};
    const staleMessage = 'Esta elección cambió en otra pestaña. Actualiza el draft e inténtalo de nuevo.';
    const existing = doc.querySelector('.draft-live-modal-backdrop');
    if (existing) existing.remove();
    const backdrop = doc.createElement('div');
    backdrop.className = 'draft-live-modal-backdrop';
    backdrop.innerHTML = adminPickModalHtml(row, options.live || {}, options.escapeHtml).html;
    const close = () => backdrop.remove();
    const choice = backdrop.querySelector('[data-draft-live-choice]');
    const customWrap = backdrop.querySelector('[data-draft-live-custom-wrap]');
    const customInput = backdrop.querySelector('[data-draft-live-custom]');
    const syncCustom = () => {
      const show = choice.value === '__other__';
      customWrap.classList.toggle('section-hidden', !show);
      if (show) customInput.focus();
    };
    const applyResult = (result) => {
      if (typeof options.onState === 'function') options.onState(result);
      close();
      if (typeof options.onRefresh === 'function') options.onRefresh();
    };
    choice.addEventListener('change', syncCustom);
    backdrop.querySelector('[data-draft-live-close]')?.addEventListener('click', close);
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) close();
    });
    backdrop.querySelector('[data-draft-live-clear]')?.addEventListener('click', async () => {
      if (!confirmFn('¿Limpiar esta elección?')) return;
      try {
        const result = await api(`/api/draft-live/picks/${encodeURIComponent(row.id)}`, {
          method: 'POST',
          body: JSON.stringify({
            clear: true,
            advance: false,
            expected_state_version: live.state_version || undefined,
            expected_selection_version: row.selection_version || undefined,
          }),
        });
        applyResult(result);
      } catch (err) {
        alertFn(err.message === 'stale_entity_version' ? staleMessage : `Draft pick clear failed: ${err.message}`);
      }
    });
    backdrop.querySelector('[data-draft-live-submit]')?.addEventListener('click', async () => {
      const optionValue = String(choice.value || '').trim();
      const customText = String(customInput.value || '').trim();
      if (!optionValue || (optionValue === '__other__' && !customText)) {
        alertFn('Elige un jugador o escribe el nombre en Otro.');
        return;
      }
      try {
        const result = await api(`/api/draft-live/picks/${encodeURIComponent(row.id)}`, {
          method: 'POST',
          body: JSON.stringify({
            option_value: optionValue,
            custom_text: customText,
            advance: Boolean(backdrop.querySelector('[data-draft-live-advance]')?.checked),
            expected_state_version: live.state_version || undefined,
            expected_selection_version: row.selection_version || undefined,
          }),
        });
        applyResult(result);
      } catch (err) {
        alertFn(err.message === 'stale_entity_version' ? staleMessage : `Draft pick save failed: ${err.message}`);
      }
    });
    doc.body.appendChild(backdrop);
    choice.focus();
    syncCustom();
  }

  function bindAdminPickButtons(container, options = {}) {
    if (!container) return;
    container.querySelectorAll('[data-draft-live-pick]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pickId = Number(btn.dataset.draftLivePick || 0);
        const row = (options.draftOrder?.draft_order || []).find((item) => Number(item.id || 0) === pickId);
        if (row) openAdminPickModal(row, options);
      });
    });
  }

  function guestPanelHtml(live, draftOrder, escapeHtml) {
    const upcoming = upcomingRows(live, draftOrder);
    if (!live?.enabled && !upcoming.length) return '';
    const current = currentPick(live, draftOrder) || upcoming[0] || null;
    const currentLabel = current
      ? `Pick #${current.pick_number} · ${current.draft_round} · ${current.owner_team_code}`
      : 'Sin picks configurados';
    const esc = (value) => escapeWith(escapeHtml, value);
    return `
      <div class="draft-live-card">
        <div>
          <span class="draft-live-kicker">${live?.enabled ? 'Modo draft activo' : 'Modo draft inactivo'}</span>
          <strong>${esc(currentLabel)}</strong>
          ${current ? `<span>Siguiente elección: ${esc(current.owner_team_name || current.owner_team_code || '')}</span>` : '<span>No quedan picks pendientes.</span>'}
        </div>
        ${live?.enabled ? `<div class="draft-live-clock" data-draft-live-countdown>${formatClock(remainingSeconds(live))}</div>` : '<div class="draft-live-clock draft-live-clock--idle">--</div>'}
      </div>
      ${upcomingHtml(live, draftOrder, escapeHtml)}
    `;
  }

  window.AnbaDraftLive = {
    adminPanelHtml,
    bindAdminPanelControls,
    bindAdminPickButtons,
    choiceOptionsHtml,
    currentPick,
    currentPickOptionsHtml,
    formatClock,
    guestPanelHtml,
    orderedRows,
    openAdminPickModal,
    pickLabel,
    remainingSeconds,
    selectionHtml,
    upcomingHtml,
    upcomingRows,
  };
}());
