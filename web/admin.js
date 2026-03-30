const state = {
  teams: [],
  trackerRows: [],
  teamCode: null,
  teamData: null,
  csrfToken: null,
  settings: {
    salary_cap_2025: 154647000,
    current_year: 2025,
    first_apron: 195945000,
    second_apron: 207824000,
    luxury_cap: 187896105,
    minimum_cap_allowed: 139182300,
  },
  selectedPlayerIds: new Set(),
  trade: {
    teamA: null,
    teamB: null,
    playersByTeam: {},
    selectedA: new Set(),
    selectedB: new Set(),
  },
  ui: {
    viewMode: 'tracker',
  },
  sort: {
    tracker: { key: 'team_code', dir: 'asc' },
    players: { key: 'position', dir: 'asc' },
    dead_contracts: { key: 'dead_type', dir: 'asc' },
  },
};

const PLAYER_SORT_CYCLE = [
  { key: 'position', dir: 'asc' },
  { key: 'position', dir: 'desc' },
  { key: 'name', dir: 'asc' },
  { key: 'name', dir: 'desc' },
  { key: 'rating', dir: 'desc' },
  { key: 'rating', dir: 'asc' },
];
const POSITION_ORDER = { PG: 1, SG: 2, SF: 3, PF: 4, C: 5 };

function typeClass(value) {
  const v = String(value || '').toLowerCase().replaceAll('(', '').replaceAll(')', '').replaceAll('/', '').replaceAll(' ', '');
  return v ? `type-pill--${v}` : '';
}

function contractOptionClass(value) {
  const v = String(value || '').toUpperCase();
  if (!v) return '';
  return `salary-option--${v.toLowerCase()}`;
}

function salaryTextTagClass(value) {
  const v = String(value || '').trim().toUpperCase();
  if (v === 'FB') return 'salary-text-tag--fb';
  if (v === 'EB') return 'salary-text-tag--eb';
  if (v === 'NB') return 'salary-text-tag--nb';
  return '';
}

function describePlayerSort(sortCfg) {
  const key = sortCfg.key;
  const dir = sortCfg.dir === 'asc' ? 'asc' : 'desc';
  if (key === 'position') return `Sort: Position (${dir})`;
  if (key === 'name') return `Sort: Name (${dir})`;
  if (key === 'rating') return `Sort: Rating (${dir})`;
  return `Sort: ${key} (${dir})`;
}

const TEAM_THEMES = {
  ATL: { primary: '#E03A3E', secondary: '#C1D32F' },
  BOS: { primary: '#007A33', secondary: '#BA9653' },
  BKN: { primary: '#000000', secondary: '#FFFFFF' },
  CHA: { primary: '#1D1160', secondary: '#00788C' },
  CHI: { primary: '#CE1141', secondary: '#000000' },
  CLE: { primary: '#860038', secondary: '#FDBB30' },
  DAL: { primary: '#00538C', secondary: '#002F5F' },
  DEN: { primary: '#0E2240', secondary: '#FEC524' },
  DET: { primary: '#C8102E', secondary: '#1D42BA' },
  GSW: { primary: '#1D428A', secondary: '#FFC72C' },
  HOU: { primary: '#CE1141', secondary: '#000000' },
  IND: { primary: '#002D62', secondary: '#FDBB30' },
  LAC: { primary: '#C8102E', secondary: '#1D428A' },
  LAL: { primary: '#552583', secondary: '#FDB927' },
  MEM: { primary: '#12173F', secondary: '#5D76A9' },
  MIA: { primary: '#98002E', secondary: '#000000' },
  MIL: { primary: '#00471B', secondary: '#EEE1C6' },
  MIN: { primary: '#0C2340', secondary: '#9EA2A2' },
  NOP: { primary: '#0C2340', secondary: '#C8102E' },
  NYK: { primary: '#006BB6', secondary: '#F58426' },
  OKC: { primary: '#007AC1', secondary: '#EF3B24' },
  ORL: { primary: '#0077C0', secondary: '#000000' },
  PHI: { primary: '#006BB6', secondary: '#ED174C' },
  PHX: { primary: '#E56020', secondary: '#1D1160' },
  POR: { primary: '#E03A3E', secondary: '#000000' },
  SAC: { primary: '#5A2D81', secondary: '#63727A' },
  SAS: { primary: '#000000', secondary: '#C4CED4' },
  TOR: { primary: '#CE1141', secondary: '#000000' },
  UTA: { primary: '#002B5C', secondary: '#00471B' },
  WAS: { primary: '#002B5C', secondary: '#E31837' },
};

function hexToRgb(hex) {
  const clean = hex.replace('#', '');
  const value = parseInt(clean, 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}

function applyTeamTheme(code) {
  const theme = TEAM_THEMES[code] || { primary: '#0f766e', secondary: '#99f6e4' };
  const primaryRgb = hexToRgb(theme.primary);
  const secondaryRgb = hexToRgb(theme.secondary);
  const root = document.documentElement;
  root.style.setProperty('--team-primary', theme.primary);
  root.style.setProperty('--team-secondary', theme.secondary);
  root.style.setProperty('--team-primary-rgb', `${primaryRgb.r}, ${primaryRgb.g}, ${primaryRgb.b}`);
  root.style.setProperty('--team-secondary-rgb', `${secondaryRgb.r}, ${secondaryRgb.g}, ${secondaryRgb.b}`);
}

function money(n) {
  const v = Number(n || 0);
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);
}

function formatDots(n) {
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(Number(n || 0));
}

function formatMoneyDots(n) {
  const value = Math.round(Number(n || 0));
  const sign = value < 0 ? '-' : '';
  return `${sign}${formatDots(Math.abs(value))}`;
}

function seasonLabel(startYear) {
  const y = Number(startYear || 2025);
  const next = String((y + 1) % 100).padStart(2, '0');
  return `${y}-${next}`;
}

function setPageHeading(title, subtitle = '') {
  const titleEl = document.getElementById('pageTitle');
  const subtitleEl = document.getElementById('pageSubtitle');
  if (titleEl) titleEl.textContent = title || '';
  if (!subtitleEl) return;
  const value = String(subtitle || '').trim();
  subtitleEl.textContent = value;
  subtitleEl.classList.toggle('section-hidden', !value);
}

function parseAmount(raw) {
  if (raw == null) return null;
  const text = String(raw).trim();
  if (!text) return null;
  if (/[eE]/.test(text)) {
    const expNum = Number(text);
    return Number.isFinite(expNum) ? expNum : null;
  }
  let cleaned = text.replaceAll(' ', '');
  if (cleaned.includes(',') && cleaned.includes('.')) {
    cleaned = cleaned.replaceAll('.', '').replaceAll(',', '.');
  } else if (cleaned.includes(',') && !cleaned.includes('.')) {
    cleaned = cleaned.replaceAll(',', '.');
  } else if ((cleaned.match(/\./g) || []).length > 1) {
    cleaned = cleaned.replaceAll('.', '');
  }
  const num = Number(cleaned);
  return Number.isFinite(num) ? num : null;
}

async function api(path, opts = {}) {
  const method = String(opts.method || 'GET').toUpperCase();
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (['POST', 'PATCH', 'DELETE'].includes(method) && state.csrfToken) {
    headers['X-CSRF-Token'] = state.csrfToken;
  }
  const res = await fetch(path, {
    headers,
    ...opts,
  });
  if (!res.ok) {
    if (res.status === 401) {
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }
    if (res.status === 403) {
      throw new Error('Security check failed. Refresh and log in again.');
    }
    if (res.status === 429) {
      const data = await res.json().catch(() => ({}));
      const retry = Number(data.retry_after_seconds || 0);
      if (retry > 0) {
        throw new Error(`Too many attempts. Try again in ${retry}s.`);
      }
      throw new Error('Too many attempts. Try again later.');
    }
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  const data = await res.json();
  if (data && typeof data === 'object' && data.csrf_token) {
    state.csrfToken = data.csrf_token;
  }
  return data;
}

function sortValue(row, key) {
  const val = row?.[key];
  if (val === null || val === undefined || val === '') return null;
  if (key === 'position') {
    return POSITION_ORDER[String(val).toUpperCase()] ?? 999;
  }
  if (typeof val === 'number') return val;
  const num = parseAmount(val);
  if (num !== null && (key.includes('salary_') || key === 'year' || key === 'rating' || key === 'years_left' || key === 'amount_num')) {
    return num;
  }
  return String(val).toLowerCase();
}

function sortedRows(rows, sortCfg) {
  const dir = sortCfg.dir === 'desc' ? -1 : 1;
  return [...rows].sort((a, b) => {
    const va = sortValue(a, sortCfg.key);
    const vb = sortValue(b, sortCfg.key);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    if (va < vb) return -1 * dir;
    if (va > vb) return 1 * dir;
    return 0;
  });
}

function updateSortIndicators(tableId, sortCfg) {
  const headers = document.querySelectorAll(`#${tableId} thead th[data-sort]`);
  let matched = false;
  headers.forEach((th) => {
    const key = th.dataset.sort;
    const isMatch = key === sortCfg.key;
    if (isMatch) matched = true;
    const arrow = isMatch ? (sortCfg.dir === 'asc' ? ' ▲' : ' ▼') : '';
    th.innerHTML = `<span class="th-main">${th.dataset.label || th.textContent.replace(/[ ▲▼]/g, '')}${arrow}</span>`;
  });
  const cycleHeader = document.querySelector(`#${tableId} thead th[data-sort-mode="player-cycle"]`);
  if (cycleHeader && tableId === 'playersTable') {
    const base = cycleHeader.dataset.label || cycleHeader.textContent.replace(/[ ▲▼]/g, '');
    const arrow = sortCfg.dir === 'asc' ? ' ▲' : ' ▼';
    cycleHeader.innerHTML = `<span class="th-main">${base}${arrow}</span><span class="th-sub">${describePlayerSort(sortCfg)}</span>`;
  } else if (!matched && cycleHeader) {
    const base = cycleHeader.dataset.label || cycleHeader.textContent.replace(/[ ▲▼]/g, '');
    cycleHeader.innerHTML = `<span class="th-main">${base}</span>`;
  }
}

function setupSorting() {
  document.querySelectorAll('#trackerTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const curr = state.sort.tracker;
      state.sort.tracker = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      renderTracker();
      updateSortIndicators('trackerTable', state.sort.tracker);
    });
  });

  document.querySelectorAll('#playersTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      if (th.dataset.sortMode === 'player-cycle') {
        const curr = state.sort.players;
        const idx = PLAYER_SORT_CYCLE.findIndex((s) => s.key === curr.key && s.dir === curr.dir);
        state.sort.players = PLAYER_SORT_CYCLE[(idx + 1) % PLAYER_SORT_CYCLE.length];
      } else {
        const key = th.dataset.sort;
        const curr = state.sort.players;
        state.sort.players = {
          key,
          dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
        };
      }
      renderPlayers();
      updateSortIndicators('playersTable', state.sort.players);
    });
  });

  updateSortIndicators('trackerTable', state.sort.tracker);
  updateSortIndicators('playersTable', state.sort.players);
  updateSortIndicators('deadContractsTable', state.sort.dead_contracts);

  document.querySelectorAll('#deadContractsTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const curr = state.sort.dead_contracts;
      state.sort.dead_contracts = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      renderDeadContracts();
      updateSortIndicators('deadContractsTable', state.sort.dead_contracts);
    });
  });
}

function teamLogoCandidates(code) {
  return [`/team-icons/${code}.svg`, `/team-icons/${code}.png`];
}

function renderTeamStrip() {
  const strip = document.getElementById('teamStrip');
  strip.innerHTML = '';

  state.teams.forEach((t) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `team-btn${state.teamCode === t.code ? ' active' : ''}`;
    btn.title = `${t.code} - ${t.name}`;
    btn.setAttribute('aria-label', `${t.code} - ${t.name}`);

    const fallback = document.createElement('span');
    fallback.className = 'team-fallback';
    fallback.textContent = t.code;

    const img = document.createElement('img');
    img.className = 'team-logo';

    const candidates = teamLogoCandidates(t.code);
    let idx = 0;

    const tryNext = () => {
      if (idx >= candidates.length) {
        img.style.display = 'none';
        fallback.style.display = 'flex';
        return;
      }
      img.src = candidates[idx];
      idx += 1;
    };

    img.onerror = () => tryNext();
    img.onload = () => {
      fallback.style.display = 'none';
      img.style.display = 'block';
    };

    tryNext();

    btn.addEventListener('click', async () => {
      await loadTeam(t.code);
    });

    btn.appendChild(fallback);
    btn.appendChild(img);
    strip.appendChild(btn);
  });
}

function renderTeamPicker() {
  const picker = document.getElementById('teamPickerMobile');
  if (!picker) return;

  picker.innerHTML = '';
  const trackerOpt = document.createElement('option');
  trackerOpt.value = '';
  trackerOpt.textContent = 'Tracker';
  picker.appendChild(trackerOpt);

  state.teams.forEach((t) => {
    const opt = document.createElement('option');
    opt.value = t.code;
    opt.textContent = `${t.code} - ${t.name}`;
    picker.appendChild(opt);
  });

  picker.value = state.teamCode || '';
  picker.onchange = async (e) => {
    const code = e.target.value;
    if (!code) {
      await loadTracker();
      return;
    }
    if (code === state.teamCode) return;
    await loadTeam(code);
  };
}

function renderAddEntryFields() {
  const wrap = document.getElementById('addEntryFields');
  const type = document.getElementById('addEntryType').value;
  if (!wrap) return;

  if (type === 'player') {
    wrap.innerHTML = `
      <label for="addPlayerName">Name</label>
      <input id="addPlayerName" type="text" placeholder="Player name">
      <label for="addPlayerPos">Pos</label>
      <input id="addPlayerPos" type="text" placeholder="PG / SG / SF / PF / C">
      <label for="addPlayerTipo">Tipo</label>
      <select id="addPlayerTipo">
        <option value=""></option>
        <option value="Min">Min</option>
        <option value="Max">Max</option>
        <option value="Mid">Mid</option>
        <option value="TMid">TMid</option>
        <option value="Bi">Bi</option>
        <option value="10d">10d</option>
        <option value="R">R</option>
        <option value="R(2)">R(2)</option>
        <option value="TW">TW</option>
        <option value="Room">Room</option>
        <option value="Reg">Reg</option>
      </select>
      <label for="addPlayerSalary">2025-26</label>
      <input id="addPlayerSalary" type="text" placeholder="0">
    `;
    return;
  }

  if (type === 'dead_contract') {
    wrap.innerHTML = `
      <label for="addDeadType">Type</label>
      <select id="addDeadType">
        <option value="normal">Normal</option>
        <option value="two_way">Two Way</option>
      </select>
      <label for="addDeadLabel">Label</label>
      <input id="addDeadLabel" type="text" placeholder="Dead contract label">
      <label for="addDeadAmount">Amount</label>
      <input id="addDeadAmount" type="text" placeholder="0">
    `;
    return;
  }

  const ownerOptions = state.teams
    .filter((t) => t.code !== state.teamCode)
    .map((t) => `<option value="${t.code}">${t.code} - ${t.name}</option>`)
    .join('');
  wrap.innerHTML = `
    <label for="addPickType">Type</label>
    <select id="addPickType">
      <option value="own">Own</option>
      <option value="acquired">Acquired</option>
      <option value="sold">Sold</option>
    </select>
    <label for="addPickRound">Round</label>
    <select id="addPickRound">
      <option value="1st">1st round</option>
      <option value="2nd">2nd round</option>
    </select>
    <label for="addPickYear">Year</label>
    <input id="addPickYear" type="text" placeholder="2026">
    <label for="addPickOriginalOwner">Original Owner</label>
    <select id="addPickOriginalOwner">
      <option value="">Select owner</option>
      ${ownerOptions}
    </select>
    <label for="addPickDetails">Details</label>
    <input id="addPickDetails" type="text" placeholder="Details">
  `;
  const pickTypeEl = document.getElementById('addPickType');
  const ownerEl = document.getElementById('addPickOriginalOwner');
  const syncOwnerVisibility = () => {
    ownerEl.disabled = pickTypeEl.value !== 'acquired';
    if (ownerEl.disabled) ownerEl.value = '';
  };
  pickTypeEl.addEventListener('change', syncOwnerVisibility);
  syncOwnerVisibility();
}

function closeAddEntryPopover() {
  const popover = document.getElementById('addEntryPopover');
  if (!popover) return;
  popover.classList.add('section-hidden');
}

function closeAdminMenuPopover() {
  const popover = document.getElementById('adminMenuPopover');
  if (!popover) return;
  popover.classList.add('section-hidden');
}

function openAddEntryPopover() {
  const popover = document.getElementById('addEntryPopover');
  if (!popover) return;
  popover.classList.remove('section-hidden');
  renderAddEntryFields();
}

async function submitAddEntry() {
  if (!state.teamCode) {
    alert('No team selected.');
    return;
  }

  const type = document.getElementById('addEntryType').value;
  if (type === 'player') {
    const name = document.getElementById('addPlayerName').value.trim();
    const position = document.getElementById('addPlayerPos').value.trim();
    const birdRights = document.getElementById('addPlayerTipo').value.trim();
    const salary = document.getElementById('addPlayerSalary').value.trim();
    if (!name) {
      alert('Player name is required.');
      return;
    }
    const payload = { team_code: state.teamCode, name };
    if (position) payload.position = position;
    if (birdRights) payload.bird_rights = birdRights;
    if (salary) payload.salary_2025_text = salary;
    await api('/api/players', { method: 'POST', body: JSON.stringify(payload) });
  } else if (type === 'dead_contract') {
    const deadType = document.getElementById('addDeadType').value || 'normal';
    const label = document.getElementById('addDeadLabel').value.trim();
    const amount = document.getElementById('addDeadAmount').value.trim();
    const payload = {
      team_code: state.teamCode,
      dead_type: deadType,
      label: label || 'Dead Contract',
    };
    if (amount) payload.amount_text = amount;
    await api('/api/dead-contracts', { method: 'POST', body: JSON.stringify(payload) });
  } else {
    const pickType = document.getElementById('addPickType').value || 'own';
    const pickRound = document.getElementById('addPickRound').value || '1st';
    const year = document.getElementById('addPickYear').value.trim();
    const originalOwner = document.getElementById('addPickOriginalOwner').value.trim();
    const detail = document.getElementById('addPickDetails').value.trim();
    const payload = {
      team_code: state.teamCode,
      asset_type: 'draft_pick',
      draft_pick_type: pickType,
      draft_round: pickRound,
      label: `${pickRound} pick`,
    };
    if (!year) {
      alert('Year is required for draft picks.');
      return;
    }
    payload.year = year;
    if (pickType === 'acquired' && originalOwner) payload.original_owner = originalOwner;
    if (detail) payload.detail = detail;
    await api('/api/assets', { method: 'POST', body: JSON.stringify(payload) });
  }

  closeAddEntryPopover();
  await loadTeam(state.teamCode);
}

function setupAddEntryPopover() {
  const addBtn = document.getElementById('addEntryBtn');
  const popover = document.getElementById('addEntryPopover');
  const typeSelect = document.getElementById('addEntryType');
  const submitBtn = document.getElementById('addEntrySubmit');
  const cancelBtn = document.getElementById('addEntryCancel');

  addBtn.addEventListener('click', () => {
    if (!state.teamCode) return;
    const isHidden = popover.classList.contains('section-hidden');
    if (isHidden) openAddEntryPopover();
    else closeAddEntryPopover();
  });
  typeSelect.addEventListener('change', renderAddEntryFields);
  submitBtn.addEventListener('click', async () => {
    try {
      await submitAddEntry();
    } catch (err) {
      alert(`Create failed: ${err.message}`);
    }
  });
  cancelBtn.addEventListener('click', closeAddEntryPopover);

  document.addEventListener('click', (e) => {
    if (popover.classList.contains('section-hidden')) return;
    if (popover.contains(e.target) || addBtn.contains(e.target)) return;
    closeAddEntryPopover();
  });
}

async function loadTradeTeamPlayers(teamCode) {
  if (!teamCode) return [];
  if (state.trade.playersByTeam[teamCode]) return state.trade.playersByTeam[teamCode];
  const data = await api(`/api/teams/${teamCode}`);
  state.trade.playersByTeam[teamCode] = data.players || [];
  return state.trade.playersByTeam[teamCode];
}

function renderTradePlayers(side) {
  const isA = side === 'A';
  const teamCode = isA ? state.trade.teamA : state.trade.teamB;
  const list = document.getElementById(isA ? 'tradePlayersA' : 'tradePlayersB');
  const selected = isA ? state.trade.selectedA : state.trade.selectedB;

  if (!teamCode) {
    list.innerHTML = '<div>Select a team</div>';
    return;
  }

  const players = state.trade.playersByTeam[teamCode] || [];
  if (players.length === 0) {
    list.innerHTML = '<div>No players on this roster.</div>';
    return;
  }

  list.innerHTML = '';
  players.forEach((p) => {
    const row = document.createElement('label');
    row.className = 'trade-player-row';
    row.innerHTML = `
      <input type="checkbox" data-player-id="${p.id}" ${selected.has(p.id) ? 'checked' : ''}>
      <span class="trade-player-name">${p.name || 'Unnamed'}</span>
      <span>${p.position || ''}</span>
      <span>${p.bird_rights || ''}</span>
    `;
    const cb = row.querySelector('input[type="checkbox"]');
    cb.addEventListener('change', () => {
      if (cb.checked) selected.add(p.id);
      else selected.delete(p.id);
    });
    list.appendChild(row);
  });
}

async function refreshTradeModalPlayers() {
  await Promise.all([
    loadTradeTeamPlayers(state.trade.teamA),
    loadTradeTeamPlayers(state.trade.teamB),
  ]);
  renderTradePlayers('A');
  renderTradePlayers('B');
}

function closeTradeModal() {
  document.getElementById('tradeModal').classList.add('section-hidden');
}

async function openTradeModal(options = {}) {
  if (!state.teams.length) return;

  const allCodes = state.teams.map((t) => t.code);
  const fallbackA = state.teamCode || allCodes[0] || null;
  if (!state.trade.teamA || !allCodes.includes(state.trade.teamA)) state.trade.teamA = fallbackA;
  if (!state.trade.teamB || !allCodes.includes(state.trade.teamB) || state.trade.teamB === state.trade.teamA) {
    state.trade.teamB = allCodes.find((c) => c !== state.trade.teamA) || null;
  }
  state.trade.selectedA.clear();
  state.trade.selectedB.clear();
  const preselectedA = Array.isArray(options.preselectedA) ? options.preselectedA : [];
  preselectedA.forEach((id) => {
    const parsed = Number(id);
    if (Number.isFinite(parsed) && parsed > 0) {
      state.trade.selectedA.add(parsed);
    }
  });

  const teamASelect = document.getElementById('tradeTeamA');
  const teamBSelect = document.getElementById('tradeTeamB');
  const optionsHtml = state.teams.map((t) => `<option value="${t.code}">${t.code} - ${t.name}</option>`).join('');
  teamASelect.innerHTML = optionsHtml;
  teamBSelect.innerHTML = optionsHtml;
  teamASelect.value = state.trade.teamA || '';
  teamBSelect.value = state.trade.teamB || '';

  await refreshTradeModalPlayers();
  document.getElementById('tradeModal').classList.remove('section-hidden');
}

async function confirmTrade() {
  const teamA = state.trade.teamA;
  const teamB = state.trade.teamB;
  if (!teamA || !teamB) {
    alert('Select two teams.');
    return;
  }
  if (teamA === teamB) {
    alert('Teams must be different.');
    return;
  }

  const fromA = Array.from(state.trade.selectedA);
  const fromB = Array.from(state.trade.selectedB);
  if (fromA.length === 0 || fromB.length === 0) {
    alert('Select at least one player from each team.');
    return;
  }

  const ok = confirm(`Confirm trade: ${fromA.length} player(s) from ${teamA} and ${fromB.length} player(s) from ${teamB}?`);
  if (!ok) return;

  const btn = document.getElementById('confirmTradeBtn');
  btn.disabled = true;
  try {
    const result = await api('/api/trades/process', {
      method: 'POST',
      body: JSON.stringify({
        team_a: teamA,
        team_b: teamB,
        players_a: fromA,
        players_b: fromB,
      }),
    });
    if (!result.ok) {
      throw new Error('Trade validation failed.');
    }
    state.trade.playersByTeam = {};
    closeTradeModal();
    if (state.teamCode) await loadTeam(state.teamCode);
    else await loadTracker();
    await loadAdminLogs();
  } finally {
    btn.disabled = false;
  }
}

function setupTradeModal() {
  const modal = document.getElementById('tradeModal');
  const openBtn = document.getElementById('processTradeBtn');
  const closeBtn = document.getElementById('closeTradeModalBtn');
  const confirmBtn = document.getElementById('confirmTradeBtn');
  const teamASelect = document.getElementById('tradeTeamA');
  const teamBSelect = document.getElementById('tradeTeamB');

  openBtn.addEventListener('click', () => { void openTradeModal(); });
  closeBtn.addEventListener('click', closeTradeModal);
  confirmBtn.addEventListener('click', () => {
    void confirmTrade().catch((err) => {
      alert(`Trade failed: ${err.message}`);
    });
  });

  teamASelect.addEventListener('change', async () => {
    const next = teamASelect.value;
    if (next === state.trade.teamB) {
      alert('Teams must be different.');
      teamASelect.value = state.trade.teamA || '';
      return;
    }
    state.trade.teamA = next;
    state.trade.selectedA.clear();
    await loadTradeTeamPlayers(next);
    renderTradePlayers('A');
  });

  teamBSelect.addEventListener('change', async () => {
    const next = teamBSelect.value;
    if (next === state.trade.teamA) {
      alert('Teams must be different.');
      teamBSelect.value = state.trade.teamB || '';
      return;
    }
    state.trade.teamB = next;
    state.trade.selectedB.clear();
    await loadTradeTeamPlayers(next);
    renderTradePlayers('B');
  });

  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeTradeModal();
  });
}

function formatLogDetails(details) {
  if (!details || typeof details !== 'object') return '';
  const text = JSON.stringify(details);
  return text.length > 180 ? `${text.slice(0, 177)}...` : text;
}

async function loadAdminLogs() {
  const action = (document.getElementById('logActionFilter')?.value || '').trim();
  const entity = (document.getElementById('logEntityFilter')?.value || '').trim();
  const params = new URLSearchParams();
  if (action) params.set('action', action);
  if (entity) params.set('entity', entity);
  params.set('limit', '200');

  const res = await api(`/api/admin/logs?${params.toString()}`);
  const rows = res.logs || [];
  const tbody = document.querySelector('#adminLogsTable tbody');
  tbody.innerHTML = '';

  rows.forEach((row) => {
    const tr = document.createElement('tr');
    const when = row.created_at ? new Date(row.created_at).toLocaleString() : '';
    tr.innerHTML = `
      <td>${when}</td>
      <td>${row.actor_email || row.actor_name || ''}</td>
      <td>${row.action || ''}</td>
      <td>${row.entity || ''}</td>
      <td>${row.entity_id || ''}</td>
      <td>${row.team_code || ''}</td>
      <td>${formatLogDetails(row.details)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function refreshAdminLogsSafe() {
  try {
    await loadAdminLogs();
  } catch (err) {
    console.error('Failed to load admin logs', err);
  }
}

function setViewMode(mode) {
  state.ui.viewMode = mode;
  const showTeam = mode === 'team';
  const showTracker = mode === 'tracker';
  const showAdminLog = mode === 'admin-log';
  const showLeagueSettings = mode === 'admin-settings';

  document.getElementById('trackerSection').classList.toggle('section-hidden', !showTracker);
  document.getElementById('teamMeta').classList.toggle('section-hidden', !showTeam);
  document.getElementById('settingsSection').classList.toggle('section-hidden', !showLeagueSettings);
  document.getElementById('adminLogsSection').classList.toggle('section-hidden', !showAdminLog);
  document.getElementById('rosterSection').classList.toggle('section-hidden', !showTeam);
  document.getElementById('deadContractsSection').classList.toggle('section-hidden', !showTeam);
  document.getElementById('assetsSection').classList.toggle('section-hidden', !showTeam);
  document.getElementById('importantFiguresSection').classList.toggle('section-hidden', !showTeam);

  const teamButtons = ['reloadBtn', 'addEntryBtn', 'saveTeamGmInlineBtn', 'processTradeBtn'];
  teamButtons.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !showTeam;
  });
  if (!showTeam) closeAddEntryPopover();
  closeAdminMenuPopover();
}

function setupAdminMenu() {
  const menuBtn = document.getElementById('adminMenuBtn');
  const menu = document.getElementById('adminMenuPopover');
  const openLogBtn = document.getElementById('openAdminLogPageBtn');
  const openSettingsBtn = document.getElementById('openLeagueSettingsPageBtn');

  menuBtn.addEventListener('click', () => {
    const isHidden = menu.classList.contains('section-hidden');
    if (isHidden) menu.classList.remove('section-hidden');
    else menu.classList.add('section-hidden');
  });

  openLogBtn.addEventListener('click', async () => {
    setViewMode('admin-log');
    setPageHeading('ANBA Admin Log', '');
    renderCapStatusPills({});
    await loadAdminLogs();
  });

  openSettingsBtn.addEventListener('click', () => {
    setViewMode('admin-settings');
    setPageHeading('ANBA League Settings', '');
    renderCapStatusPills({});
  });

  document.addEventListener('click', (e) => {
    if (menu.classList.contains('section-hidden')) return;
    if (menu.contains(e.target) || menuBtn.contains(e.target)) return;
    closeAdminMenuPopover();
  });
}

function renderTracker() {
  const tbody = document.querySelector('#trackerTable tbody');
  tbody.innerHTML = '';

  const rows = sortedRows(state.trackerRows, state.sort.tracker);
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><button type="button" class="tracker-team-btn" data-team-code="${row.team_code}">${row.team_code}</button></td>
      <td>${formatMoneyDots(row.cap_total)}</td>
      <td>${formatMoneyDots(row.gasto_total)}</td>
      <td>${formatMoneyDots(row.espacio_cap)}</td>
      <td>${formatMoneyDots(row.espacio_luxury)}</td>
      <td>${formatMoneyDots(row.espacio_1er_apron)}</td>
      <td>${formatMoneyDots(row.espacio_2do_apron)}</td>
    `;
    const teamBtn = tr.querySelector('[data-team-code]');
    teamBtn.addEventListener('click', async () => {
      await loadTeam(row.team_code);
    });
    tbody.appendChild(tr);
  });
}

function renderCards() {
  const wrap = document.getElementById('teamMeta');
  const t = state.teamData.team;
  const s = state.teamData.summary;
  const currentYear = Number(s.current_year || state.settings.current_year || 2025);
  const currentSeason = seasonLabel(currentYear);
  setPageHeading(t.name || 'Team', t.gm || '');
  renderCapStatusPills(s);
  const items = [
    { label: `CAP Total (${currentSeason})`, value: formatMoneyDots(s.cap_figure), tone: '' },
    { label: `GASTO Total (${currentSeason})`, value: formatMoneyDots(s.payroll), tone: '' },
    { label: 'Espacio CAP', value: formatMoneyDots(s.room_to_cap), tone: s.room_to_cap >= 0 ? 'positive' : 'negative' },
    { label: 'Espacio Luxury', value: formatMoneyDots(s.room_to_luxury), tone: s.room_to_luxury >= 0 ? 'positive' : 'negative' },
    { label: 'Espacio 1er Apron', value: formatMoneyDots(s.room_to_first_apron), tone: s.room_to_first_apron >= 0 ? 'positive' : 'negative' },
    { label: 'Espacio 2do Apron', value: formatMoneyDots(s.room_to_second_apron), tone: s.room_to_second_apron >= 0 ? 'positive' : 'negative' },
  ];
  wrap.innerHTML = items.map((item) => `
    <article class="card ${item.tone ? `card-${item.tone}` : ''}">
      <div class="label">${item.label}</div>
      <div class="value">${item.value}</div>
    </article>
  `).join('');
}

function renderImportantFigures() {
  const tbody = document.querySelector('#importantFiguresTable tbody');
  if (!tbody) return;
  const season = seasonLabel(Number(state.settings.current_year || 2025));
  const salaryCap = Number(state.settings.salary_cap_2025 || 0);
  const luxuryCap = Number(state.settings.luxury_cap || salaryCap * 1.215);
  const firstApron = Number(state.settings.first_apron || 0);
  const secondApron = Number(state.settings.second_apron || 0);
  const minCap = Number(state.settings.minimum_cap_allowed || salaryCap * 0.9);
  const rows = [
    ['Temporada actual', season],
    ['Salary cap', formatDots(salaryCap)],
    ['Luxury cap', formatDots(luxuryCap)],
    ['1er Apron', formatDots(firstApron)],
    ['2do Apron', formatDots(secondApron)],
    ['Mínimo cap permitido', formatDots(minCap)],
  ];
  tbody.innerHTML = rows
    .map((row) => `<tr><th>${row[0]}</th><td>${row[1]}</td></tr>`)
    .join('');
}

function renderCapStatusPills(summary) {
  const wrap = document.getElementById('capStatusPills');
  if (!wrap) return;
  const pills = [];
  if (Number(summary.room_to_luxury) < 0) pills.push('Encima del luxury');
  if (Number(summary.room_to_first_apron) < 0) pills.push('Encima del 1er apron');
  if (Number(summary.room_to_second_apron) < 0) pills.push('Encima del 2do apron');
  wrap.innerHTML = pills.map((txt) => `<span class="top-status-pill">${txt}</span>`).join('');
}

function salaryPctHtml(value) {
  const cap = Number(state.settings.salary_cap_2025 || 154647000);
  if (!Number.isFinite(value) || cap <= 0) return '';
  return `<span class="salary-pct">${((value / cap) * 100).toFixed(1)}%</span>`;
}

function buildMoveSelect(el) {
  el.innerHTML = '';
  state.teams.forEach((t) => {
    const opt = document.createElement('option');
    opt.value = t.code;
    opt.textContent = t.code;
    el.appendChild(opt);
  });
}

async function refreshSummary() {
  const data = await api(`/api/teams/${state.teamCode}`);
  state.teamData.team = data.team;
  state.teamData.summary = data.summary;
  renderCards();
}

function attachInlineEditor(fieldEl, onSaveField) {
  const td = fieldEl.parentElement;
  const wrapper = document.createElement('div');
  wrapper.className = 'inline-editor locked';

  td.insertBefore(wrapper, fieldEl);
  wrapper.appendChild(fieldEl);

  const tick = document.createElement('button');
  tick.type = 'button';
  tick.className = 'inline-save';
  tick.textContent = '✓';
  tick.hidden = true;
  wrapper.appendChild(tick);

  const isSelect = fieldEl.tagName === 'SELECT';
  const normalize = () => String(fieldEl.value ?? '').trim();
  fieldEl.dataset.initialValue = normalize();

  const setEditable = (editable) => {
    if (isSelect) {
      fieldEl.disabled = false;
    } else {
      fieldEl.readOnly = !editable;
    }
    wrapper.classList.toggle('locked', !editable);
    wrapper.classList.toggle('unlocked', editable);
    tick.hidden = !editable;
  };

  let saving = false;

  const persist = async () => {
    if (saving) return;
    const current = normalize();
    if (current === fieldEl.dataset.initialValue) {
      setEditable(false);
      return;
    }

    saving = true;
    tick.disabled = true;

    try {
      await onSaveField(current);
      fieldEl.dataset.initialValue = current;
      setEditable(false);
    } catch (err) {
      alert(err.message);
      setEditable(true);
    } finally {
      saving = false;
      tick.disabled = false;
    }
  };

  setEditable(false);

  wrapper.addEventListener('click', (e) => {
    if (e.target === tick) return;
    if (wrapper.classList.contains('locked')) {
      setEditable(true);
      fieldEl.focus();
      if (isSelect) {
        setTimeout(() => fieldEl.click(), 0);
      }
    }
  });

  if (!isSelect) {
    fieldEl.addEventListener('blur', () => {
      void persist();
    });
  } else {
    fieldEl.addEventListener('change', () => {
      void persist();
    });
    fieldEl.addEventListener('blur', () => {
      void persist();
    });
  }

  tick.addEventListener('click', (e) => {
    e.preventDefault();
    void persist();
  });

  return wrapper;
}

async function movePlayer(playerId, row) {
  const select = row.querySelector('select[data-role="move-team"]');
  await api('/api/players/move', {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, to_team_code: select.value }),
  });
}

function renderPlayers() {
  const tbody = document.querySelector('#playersTable tbody');
  const tpl = document.getElementById('playerRowTemplate');
  tbody.innerHTML = '';

  const rows = sortedRows(state.teamData.players, state.sort.players);
  rows.forEach((p) => {
    const frag = tpl.content.cloneNode(true);
    const tr = frag.querySelector('tr');
    tr.dataset.id = p.id;
    const selectCb = tr.querySelector('[data-role="select-player"]');
    if (selectCb) {
      selectCb.checked = state.selectedPlayerIds.has(p.id);
      selectCb.addEventListener('change', () => {
        if (selectCb.checked) state.selectedPlayerIds.add(p.id);
        else state.selectedPlayerIds.delete(p.id);
        syncSelectAllPlayers();
      });
    }

    tr.querySelectorAll('[data-field]').forEach((fieldEl) => {
      const key = fieldEl.dataset.field;
      fieldEl.value = p[key] == null ? '' : p[key];

      if (fieldEl.tagName === 'SELECT' && key === 'bird_rights') {
        const hasValue = Array.from(fieldEl.options).some((opt) => opt.value === fieldEl.value);
        if (!hasValue && fieldEl.value) {
          const extra = document.createElement('option');
          extra.value = fieldEl.value;
          extra.textContent = fieldEl.value;
          fieldEl.appendChild(extra);
        }
      }

      if (key.startsWith('salary_') && fieldEl.tagName === 'INPUT') {
        const parsed = parseAmount(fieldEl.value);
        if (parsed !== null) fieldEl.value = formatDots(parsed);
      }
      const wrapper = attachInlineEditor(fieldEl, async (value) => {
        await api(`/api/players/${p.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ [key]: value }),
        });
        await refreshSummary();
      });

      if (key.startsWith('salary_')) {
        wrapper.classList.add('salary-edit');
        const num = parseAmount(fieldEl.value);
        const pct = document.createElement('span');
        pct.className = 'salary-pct';
        pct.textContent = num && Number.isFinite(num) && state.settings.salary_cap_2025 > 0
          ? `${((num / state.settings.salary_cap_2025) * 100).toFixed(1)}%`
          : '';
        wrapper.appendChild(pct);

        const refreshPct = () => {
          const parsed = parseAmount(fieldEl.value);
          pct.textContent = parsed && Number.isFinite(parsed) && state.settings.salary_cap_2025 > 0
            ? `${((parsed / state.settings.salary_cap_2025) * 100).toFixed(1)}%`
            : '';
          const td = fieldEl.closest('td');
          if (td) {
            Array.from(td.classList)
              .filter((c) => c.startsWith('salary-text-tag--'))
              .forEach((c) => td.classList.remove(c));
            const tag = salaryTextTagClass(fieldEl.value);
            if (tag) td.classList.add(tag);
          }
        };
        fieldEl.addEventListener('input', refreshPct);
        fieldEl.addEventListener('blur', refreshPct);
        refreshPct();
      }
      if (key === 'position') {
        wrapper.classList.add('pos-edit');
      }
      if (key === 'bird_rights') {
        wrapper.classList.add('type-edit');
        const applyClass = () => {
          const cl = Array.from(wrapper.classList).filter((c) => c.startsWith('type-pill--'));
          cl.forEach((c) => wrapper.classList.remove(c));
          const next = typeClass(fieldEl.value);
          if (next) wrapper.classList.add(next);
        };
        applyClass();
        fieldEl.addEventListener('change', applyClass);
      }
    });

    tr.querySelectorAll('select[data-option-field]').forEach((optionSelect) => {
      const optionField = optionSelect.dataset.optionField;
      const season = Number(optionField.split('_')[1] || 0);
      optionSelect.innerHTML = `
        <option value="">-</option>
        <option value="TO">TO</option>
        <option value="PO">PO</option>
        <option value="QO">QO</option>
        <option value="GAP">GAP</option>
      `;
      optionSelect.value = p[optionField] || '';
      const td = optionSelect.closest('td');
      const applyOptionVisual = () => {
        if (!td) return;
        Array.from(td.classList)
          .filter((c) => c.startsWith('salary-option--'))
          .forEach((c) => td.classList.remove(c));
        const cl = contractOptionClass(optionSelect.value);
        if (cl) td.classList.add(cl);
      };
      let saving = false;
      const persistOption = async () => {
        if (saving) return;
        saving = true;
        optionSelect.disabled = true;
        try {
          await api(`/api/players/${p.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ [optionField]: optionSelect.value || null }),
          });
          p[optionField] = optionSelect.value || null;
          applyOptionVisual();
        } catch (err) {
          alert(`No se pudo guardar la opción de contrato: ${err.message}`);
        } finally {
          optionSelect.disabled = false;
          saving = false;
        }
      };
      applyOptionVisual();
      optionSelect.addEventListener('change', () => { void persistOption(); });
      optionSelect.addEventListener('blur', () => { void persistOption(); });
    });

    const nameInput = tr.querySelector('input[data-field="name"]');
    if (nameInput) {
      const td = nameInput.closest('td');
      if (td) {
        const tags = document.createElement('span');
        tags.className = 'player-tags';
        if (p.position) {
          const posTag = document.createElement('span');
          posTag.className = 'pos-pill';
          posTag.textContent = p.position;
          tags.appendChild(posTag);
        }
        if (p.rating) {
          const ratingTag = document.createElement('span');
          ratingTag.className = 'meta-pill';
          ratingTag.textContent = p.rating;
          tags.appendChild(ratingTag);
        }
        if (tags.childElementCount > 0) {
          td.appendChild(tags);
        }
      }
    }

    const moveSelect = tr.querySelector('select[data-role="move-team"]');
    buildMoveSelect(moveSelect);
    moveSelect.value = state.teamCode;

    tr.querySelector('[data-action="move"]').addEventListener('click', async () => {
      await movePlayer(p.id, tr);
      await loadTeam(state.teamCode);
    });

    tr.querySelector('[data-action="delete"]').addEventListener('click', async () => {
      if (!confirm('Delete this player?')) return;
      await api(`/api/players/${p.id}`, { method: 'DELETE' });
      await loadTeam(state.teamCode);
    });

    tbody.appendChild(frag);
  });
  syncSelectAllPlayers();
}

function syncSelectAllPlayers() {
  const selectAll = document.getElementById('selectAllPlayers');
  const actionsBar = document.getElementById('selectedPlayerActions');
  const selectedCountEl = document.getElementById('selectedPlayersCount');
  if (!selectAll || !state.teamData) return;
  const total = state.teamData.players.length;
  const selected = state.selectedPlayerIds.size;
  selectAll.indeterminate = selected > 0 && selected < total;
  selectAll.checked = total > 0 && selected === total;
  if (actionsBar) actionsBar.classList.toggle('section-hidden', selected === 0);
  if (selectedCountEl) selectedCountEl.textContent = `${selected} selected`;
}

function selectedPlayers() {
  if (!state.teamData) return [];
  const selected = new Set(state.selectedPlayerIds);
  return state.teamData.players.filter((p) => selected.has(p.id));
}

async function deleteSelectedPlayersAction() {
  const players = selectedPlayers();
  if (players.length === 0) {
    alert('Select at least one player.');
    return;
  }
  if (!confirm(`Delete ${players.length} selected player(s)?`)) return;
  for (const p of players) {
    await api(`/api/players/${p.id}`, { method: 'DELETE' });
  }
  await loadTeam(state.teamCode);
}

async function duplicateSelectedPlayersAction() {
  const players = selectedPlayers();
  if (players.length === 0) {
    alert('Select at least one player.');
    return;
  }
  for (const p of players) {
    const payload = {
      team_code: state.teamCode,
      name: p.name ? `${p.name} (Copy)` : 'Copy',
      bird_rights: p.bird_rights || null,
      rating: p.rating || null,
      position: p.position || null,
      years_left: p.years_left || null,
      salary_2025_text: p.salary_2025_text || null,
      salary_2026_text: p.salary_2026_text || null,
      salary_2027_text: p.salary_2027_text || null,
      salary_2028_text: p.salary_2028_text || null,
      salary_2029_text: p.salary_2029_text || null,
      salary_2030_text: p.salary_2030_text || null,
      option_2025: p.option_2025 || null,
      option_2026: p.option_2026 || null,
      option_2027: p.option_2027 || null,
      option_2028: p.option_2028 || null,
      option_2029: p.option_2029 || null,
      option_2030: p.option_2030 || null,
      notes: p.notes || null,
    };
    await api('/api/players', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }
  await loadTeam(state.teamCode);
}

async function tradeSelectedPlayersAction() {
  const players = selectedPlayers();
  if (players.length === 0) {
    alert('Select at least one player.');
    return;
  }
  state.trade.teamA = state.teamCode;
  if (state.trade.teamB === state.teamA) state.trade.teamB = null;
  await openTradeModal({ preselectedA: players.map((p) => p.id) });
}

async function cutSelectedPlayersAction() {
  const players = selectedPlayers();
  if (players.length === 0) {
    alert('Select at least one player.');
    return;
  }
  if (!confirm(`Cut ${players.length} selected player(s)? This creates dead contracts and removes the players from roster.`)) return;

  const currentYear = Number(state.settings.current_year || 2025);
  for (const p of players) {
    const deadType = String(p.bird_rights || '').trim().toUpperCase() === 'TW' ? 'two_way' : 'normal';
    const salaryNum = Number(p[`salary_${currentYear}_num`] || 0);
    const salaryText = String(p[`salary_${currentYear}_text`] || '').trim();
    const deadPayload = {
      team_code: state.teamCode,
      dead_type: deadType,
      label: p.name || 'Cut Player',
    };
    if (Number.isFinite(salaryNum) && salaryNum > 0) {
      deadPayload.amount_text = String(Math.round(salaryNum));
    } else if (salaryText) {
      deadPayload.amount_text = salaryText;
    }
    await api('/api/dead-contracts', {
      method: 'POST',
      body: JSON.stringify(deadPayload),
    });
    await api(`/api/players/${p.id}`, { method: 'DELETE' });
  }
  await loadTeam(state.teamCode);
}

function renderAssets() {
  const board = document.getElementById('draftAssetsBoard');
  if (!board) return;
  board.innerHTML = '';

  const normalizedRound = (pick) => {
    const roundRaw = String(pick.draft_round || '').trim().toLowerCase();
    if (roundRaw.includes('2')) return '2nd';
    if (roundRaw.includes('1')) return '1st';
    const label = String(pick.label || '').trim().toLowerCase();
    return label.includes('2') ? '2nd' : '1st';
  };

  const normalizedType = (pick) => {
    const type = String(pick.draft_pick_type || 'own').trim().toLowerCase();
    if (type === 'acquired' || type === 'sold') return type;
    return 'own';
  };

  const orderedPicksForSeason = (seasonPicks) => {
    const own1 = [];
    const own2 = [];
    const acq1 = [];
    const acq2 = [];
    const sold = [];
    seasonPicks.forEach((pick) => {
      const t = normalizedType(pick);
      const r = normalizedRound(pick);
      if (t === 'own' && r === '1st') own1.push(pick);
      else if (t === 'own' && r === '2nd') own2.push(pick);
      else if (t === 'acquired' && r === '1st') acq1.push(pick);
      else if (t === 'acquired' && r === '2nd') acq2.push(pick);
      else sold.push(pick);
    });
    const byOwnerThenId = (a, b) => {
      const ownerA = String(a.original_owner || '');
      const ownerB = String(b.original_owner || '');
      if (ownerA < ownerB) return -1;
      if (ownerA > ownerB) return 1;
      return Number(a.id || 0) - Number(b.id || 0);
    };
    own1.sort(byOwnerThenId);
    own2.sort(byOwnerThenId);
    acq1.sort(byOwnerThenId);
    acq2.sort(byOwnerThenId);
    sold.sort(byOwnerThenId);
    return [...own1, ...own2, ...acq1, ...acq2, ...sold];
  };

  const picks = (state.teamData.assets || []).filter((a) => a.asset_type === 'draft_pick');
  if (picks.length === 0) {
    board.innerHTML = '<p>No draft picks loaded.</p>';
    return;
  }

  const seasonKeys = Array.from(new Set(picks.map((p) => {
    const y = Number(p.year);
    return Number.isFinite(y) ? String(y) : 'No year';
  }))).sort((a, b) => {
    if (a === 'No year') return 1;
    if (b === 'No year') return -1;
    return Number(a) - Number(b);
  });
  const ownerOptions = state.teams
    .filter((t) => t.code !== state.teamCode)
    .map((t) => `<option value="${t.code}">${t.code} - ${t.name}</option>`)
    .join('');

  seasonKeys.forEach((seasonKey) => {
    const seasonWrap = document.createElement('div');
    seasonWrap.className = 'draft-season-group';
    seasonWrap.innerHTML = `<h3>${seasonKey}</h3>`;
    const grid = document.createElement('div');
    grid.className = 'draft-picks-grid';

    orderedPicksForSeason(
      picks
      .filter((p) => {
        const y = Number(p.year);
        return Number.isFinite(y) ? String(y) === seasonKey : seasonKey === 'No year';
      })
    )
      .forEach((pick) => {
        const pickType = normalizedType(pick);
        const ownerCode = pick.draft_pick_type === 'acquired'
          ? (pick.original_owner || '')
          : state.teamCode;
        const ownerTheme = TEAM_THEMES[ownerCode] || { primary: '#0f766e', secondary: '#99f6e4' };
        const ownerPrimaryRgb = hexToRgb(ownerTheme.primary);
        const ownerSecondaryRgb = hexToRgb(ownerTheme.secondary);
        const card = document.createElement('article');
        card.className = 'draft-pick-card admin-pick-card';
        if (pickType === 'sold') card.classList.add('draft-pick-card--sold');
        card.style.setProperty('--pick-primary-rgb', `${ownerPrimaryRgb.r}, ${ownerPrimaryRgb.g}, ${ownerPrimaryRgb.b}`);
        card.style.setProperty('--pick-secondary-rgb', `${ownerSecondaryRgb.r}, ${ownerSecondaryRgb.g}, ${ownerSecondaryRgb.b}`);
        card.innerHTML = `
          <div class="pick-card-logo-wrap">
            <span class="pick-owner-fallback">${ownerCode || 'N/A'}</span>
            <img class="pick-owner-logo" alt="${ownerCode || ''} logo">
          </div>
          <div class="pick-editor-grid">
            <label>Type
              <select data-field="draft_pick_type">
                <option value="own">Own</option>
                <option value="acquired">Acquired</option>
                <option value="sold">Sold</option>
              </select>
            </label>
            <label>Round
              <select data-field="draft_round">
                <option value="1st">1st round</option>
                <option value="2nd">2nd round</option>
              </select>
            </label>
            <label>Year
              <input data-field="year" type="text" value="${pick.year || ''}">
            </label>
            <label data-owner-wrap>Original owner
              <select data-field="original_owner">
                <option value="">Select owner</option>
                ${ownerOptions}
              </select>
            </label>
            <label class="pick-detail-input">Details
              <input data-field="detail" type="text" value="${pick.detail || ''}">
            </label>
          </div>
          <div class="pick-card-actions">
            <button data-action="delete-pick" class="danger" type="button">Delete</button>
          </div>
        `;

        const img = card.querySelector('.pick-owner-logo');
        const fallback = card.querySelector('.pick-owner-fallback');
        const candidates = ownerCode ? teamLogoCandidates(ownerCode) : [];
        let idx = 0;
        const tryNext = () => {
          if (idx >= candidates.length) {
            img.style.display = 'none';
            fallback.style.display = 'flex';
            return;
          }
          img.src = candidates[idx];
          idx += 1;
        };
        img.onerror = () => tryNext();
        img.onload = () => {
          fallback.style.display = 'none';
          img.style.display = 'block';
        };
        tryNext();

        const typeSelect = card.querySelector('[data-field="draft_pick_type"]');
        const roundSelect = card.querySelector('[data-field="draft_round"]');
        const yearInput = card.querySelector('[data-field="year"]');
        const ownerSelect = card.querySelector('[data-field="original_owner"]');
        const detailInput = card.querySelector('[data-field="detail"]');
        const ownerWrap = card.querySelector('[data-owner-wrap]');

        typeSelect.value = pick.draft_pick_type || 'own';
        roundSelect.value = pick.draft_round || '1st';
        ownerSelect.value = pick.original_owner || '';

        const syncOwnerField = () => {
          ownerWrap.style.display = typeSelect.value === 'acquired' ? 'grid' : 'none';
          if (typeSelect.value !== 'acquired') ownerSelect.value = '';
        };
        syncOwnerField();

        const persist = async (payload) => {
          await api(`/api/assets/${pick.id}`, {
            method: 'PATCH',
            body: JSON.stringify(payload),
          });
          await loadTeam(state.teamCode);
        };

        typeSelect.addEventListener('change', async () => {
          syncOwnerField();
          await persist({ draft_pick_type: typeSelect.value, original_owner: ownerSelect.value || null });
        });
        roundSelect.addEventListener('change', async () => {
          await persist({ draft_round: roundSelect.value });
        });
        ownerSelect.addEventListener('change', async () => {
          await persist({ original_owner: ownerSelect.value || null });
        });
        yearInput.addEventListener('blur', async () => {
          const val = yearInput.value.trim();
          if (!val) return;
          await persist({ year: val });
        });
        detailInput.addEventListener('blur', async () => {
          await persist({ detail: detailInput.value.trim() });
        });
        card.querySelector('[data-action="delete-pick"]').addEventListener('click', async () => {
          if (!confirm('Delete this draft pick?')) return;
          await api(`/api/assets/${pick.id}`, { method: 'DELETE' });
          await loadTeam(state.teamCode);
        });

        grid.appendChild(card);
      });

    seasonWrap.appendChild(grid);
    board.appendChild(seasonWrap);
  });
}

function renderDeadContracts() {
  const tbody = document.querySelector('#deadContractsTable tbody');
  const tpl = document.getElementById('deadContractRowTemplate');
  tbody.innerHTML = '';

  const rows = sortedRows(state.teamData.dead_contracts || [], state.sort.dead_contracts);
  rows.forEach((d) => {
    const frag = tpl.content.cloneNode(true);
    const tr = frag.querySelector('tr');
    tr.dataset.id = d.id;

    tr.querySelectorAll('[data-field]').forEach((el) => {
      const key = el.dataset.field;
      if (key === 'dead_type') {
        el.value = d[key] === 'two_way' ? 'two_way' : 'normal';
      } else {
        el.value = d[key] == null ? '' : d[key];
      }

      const wrapper = attachInlineEditor(el, async (value) => {
        await api(`/api/dead-contracts/${d.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ [key]: value }),
        });
        await refreshSummary();
      });

      if (key === 'amount_text') {
        wrapper.classList.add('salary-edit');
      }
    });

    tr.querySelector('[data-action="delete-dead-contract"]').addEventListener('click', async () => {
      if (!confirm('Delete this dead contract?')) return;
      await api(`/api/dead-contracts/${d.id}`, { method: 'DELETE' });
      await loadTeam(state.teamCode);
    });

    tbody.appendChild(frag);
  });
}

async function loadTeam(code) {
  const data = await api(`/api/teams/${code}`);
  state.teamCode = code;
  state.teamData = data;
  state.selectedPlayerIds.clear();
  applyTeamTheme(code);
  setViewMode('team');
  const gmInlineInput = document.getElementById('teamGmInlineInput');
  if (gmInlineInput) gmInlineInput.value = data.team.gm || '';
  renderTeamStrip();
  renderTeamPicker();
  renderCards();
  renderPlayers();
  renderDeadContracts();
  renderAssets();
  renderImportantFigures();
  await refreshAdminLogsSafe();
}

async function fetchTrackerRowsFallback() {
  const rows = await Promise.all(state.teams.map(async (t) => {
    const data = await api(`/api/teams/${t.code}`);
    const s = data.summary || {};
    return {
      team_code: t.code,
      team_name: t.name,
      cap_total: Number(s.cap_figure || 0),
      gasto_total: Number(s.payroll || 0),
      espacio_cap: Number(s.room_to_cap || 0),
      espacio_luxury: Number(s.room_to_luxury || 0),
      espacio_1er_apron: Number(s.room_to_first_apron || 0),
      espacio_2do_apron: Number(s.room_to_second_apron || 0),
    };
  }));
  return rows;
}

async function loadTracker() {
  try {
    const res = await api('/api/tracker');
    state.trackerRows = res.tracker || [];
  } catch (err) {
    if (!String(err.message || '').includes('API 404')) throw err;
    console.warn('API /api/tracker not available, using client fallback.');
    state.trackerRows = await fetchTrackerRowsFallback();
  }
  state.teamCode = null;
  state.teamData = null;
  state.selectedPlayerIds.clear();
  applyTeamTheme('');
  setViewMode('tracker');
  setPageHeading('ANBA Tracker (Admin)', '');
  renderCapStatusPills({});
  renderTeamStrip();
  renderTeamPicker();
  renderTracker();
  renderImportantFigures();
  await refreshAdminLogsSafe();
}

async function saveCurrentTeamGm(inputEl, buttonEl) {
  if (!state.teamCode) {
    alert('No team selected.');
    return;
  }
  if (!inputEl || !buttonEl) return;
  const gm = inputEl.value.trim();
  buttonEl.disabled = true;
  const oldText = buttonEl.textContent;
  buttonEl.textContent = 'Saving...';
  try {
    await api(`/api/teams/${state.teamCode}`, {
      method: 'PATCH',
      body: JSON.stringify({ gm }),
    });
    await loadTeam(state.teamCode);
    buttonEl.textContent = 'Saved';
    setTimeout(() => {
      buttonEl.textContent = oldText;
    }, 900);
  } catch (err) {
    buttonEl.textContent = oldText;
    alert(`GM save failed: ${err.message}`);
  } finally {
    buttonEl.disabled = false;
  }
}

async function init() {
  const auth = await api('/api/auth/status');
  state.csrfToken = auth.csrf_token || null;
  if (!auth.authenticated) {
    window.location.href = '/login';
    return;
  }
  if (auth.role !== 'admin') {
    window.location.href = '/';
    return;
  }

  const settingsRes = await api('/api/settings');
  state.settings = settingsRes.settings || state.settings;
  const capInput = document.getElementById('salaryCap2025Input');
  const firstApronInput = document.getElementById('firstApronInput');
  const secondApronInput = document.getElementById('secondApronInput');
  const currentYearSelect = document.getElementById('currentYearSelect');
  capInput.value = formatDots(state.settings.salary_cap_2025);
  firstApronInput.value = formatDots(state.settings.first_apron);
  secondApronInput.value = formatDots(state.settings.second_apron);
  currentYearSelect.value = String(state.settings.current_year || 2025);

  const teamsRes = await api('/api/teams');
  state.teams = teamsRes.teams;
  setupSorting();
  renderTeamStrip();
  renderTeamPicker();
  setupAddEntryPopover();
  setupTradeModal();
  setupAdminMenu();
  document.getElementById('logActionFilter').addEventListener('change', () => { void loadAdminLogs(); });
  document.getElementById('logEntityFilter').addEventListener('change', () => { void loadAdminLogs(); });
  document.getElementById('refreshLogsBtn').addEventListener('click', () => { void loadAdminLogs(); });

  document.getElementById('reloadBtn').addEventListener('click', async () => {
    if (!state.teamCode) return;
    await loadTeam(state.teamCode);
  });

  document.getElementById('selectAllPlayers').addEventListener('change', (e) => {
    const checked = Boolean(e.target.checked);
    state.selectedPlayerIds.clear();
    if (checked && state.teamData) {
      state.teamData.players.forEach((p) => state.selectedPlayerIds.add(p.id));
    }
    renderPlayers();
  });

  document.getElementById('applyBulkBtn').addEventListener('click', async () => {
    const ids = Array.from(state.selectedPlayerIds);
    if (ids.length === 0) {
      alert('Selecciona al menos un jugador.');
      return;
    }
    const payload = {};
    const bulkTipo = document.getElementById('bulkTipo').value.trim();
    const bulkPos = document.getElementById('bulkPos').value.trim();
    const bulkRating = document.getElementById('bulkRating').value.trim();
    const bulkYears = document.getElementById('bulkYears').value.trim();
    if (bulkTipo) payload.bird_rights = bulkTipo;
    if (bulkPos) payload.position = bulkPos;
    if (bulkRating) payload.rating = bulkRating;
    if (bulkYears) payload.years_left = bulkYears;
    if (Object.keys(payload).length === 0) {
      alert('No hay cambios para aplicar.');
      return;
    }
    for (const id of ids) {
      await api(`/api/players/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
    }
    await loadTeam(state.teamCode);
  });

  document.getElementById('deleteBulkBtn').addEventListener('click', async () => {
    const ids = Array.from(state.selectedPlayerIds);
    if (ids.length === 0) {
      alert('Selecciona al menos un jugador.');
      return;
    }
    if (!confirm(`Eliminar ${ids.length} jugador(es) seleccionados?`)) return;
    for (const id of ids) {
      await api(`/api/players/${id}`, { method: 'DELETE' });
    }
    await loadTeam(state.teamCode);
  });

  document.getElementById('selectedDeleteBtn').addEventListener('click', async () => {
    await deleteSelectedPlayersAction();
  });
  document.getElementById('selectedDuplicateBtn').addEventListener('click', async () => {
    await duplicateSelectedPlayersAction();
  });
  document.getElementById('selectedTradeBtn').addEventListener('click', async () => {
    await tradeSelectedPlayersAction();
  });
  document.getElementById('selectedCutBtn').addEventListener('click', async () => {
    await cutSelectedPlayersAction();
  });

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST', body: '{}' });
    window.location.href = '/login';
  });
  document.getElementById('trackerHomeBtn').addEventListener('click', async () => {
    await loadTracker();
  });

  document.getElementById('saveSettingsBtn').addEventListener('click', async () => {
    const parsed = parseAmount(capInput.value);
    if (!parsed || parsed <= 0) {
      alert('Invalid salary cap value.');
      return;
    }
    const parsedFirstApron = parseAmount(firstApronInput.value);
    if (!parsedFirstApron || parsedFirstApron <= 0) {
      alert('Invalid 1st apron value.');
      return;
    }
    const parsedSecondApron = parseAmount(secondApronInput.value);
    if (!parsedSecondApron || parsedSecondApron <= 0) {
      alert('Invalid 2nd apron value.');
      return;
    }
    const selectedYear = Number(currentYearSelect.value);
    if (!Number.isInteger(selectedYear) || selectedYear < 2025 || selectedYear > 2030) {
      alert('Invalid current year.');
      return;
    }
    const previousYear = Number(state.settings.current_year || 2025);
    if (selectedYear !== previousYear) {
      const fromLabel = seasonLabel(previousYear);
      const toLabel = seasonLabel(selectedYear);
      if (!confirm(`Change current year from ${fromLabel} to ${toLabel}? This updates CAP Total and GASTO Total calculations.`)) {
        currentYearSelect.value = String(previousYear);
        return;
      }
    }
    const result = await api('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify({
        salary_cap_2025: parsed,
        current_year: selectedYear,
        first_apron: parsedFirstApron,
        second_apron: parsedSecondApron,
      }),
    });
    state.settings = result.settings || state.settings;
    capInput.value = formatDots(state.settings.salary_cap_2025);
    firstApronInput.value = formatDots(state.settings.first_apron);
    secondApronInput.value = formatDots(state.settings.second_apron);
    currentYearSelect.value = String(state.settings.current_year || 2025);
    if (state.ui.viewMode === 'team' && state.teamCode) {
      await loadTeam(state.teamCode);
    } else if (state.ui.viewMode === 'tracker') {
      await loadTracker();
    } else {
      await refreshAdminLogsSafe();
    }
  });

  document.getElementById('saveTeamGmInlineBtn').addEventListener('click', async () => {
    const input = document.getElementById('teamGmInlineInput');
    const btn = document.getElementById('saveTeamGmInlineBtn');
    await saveCurrentTeamGm(input, btn);
  });

  await loadTracker();
}

init().catch((err) => {
  console.error(err);
  alert(err.message);
});
