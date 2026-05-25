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
    cash_limit_total: 0,
    trade_move_limit_pre30: 15,
    trade_move_limit_post30: 15,
    trade_move_phase: 'pre30',
    luxury_cap: 187896105,
    minimum_cap_allowed: 139182300,
  },
  selectedPlayerIds: new Set(),
  trade: {
    teamA: null,
    teamB: null,
    playersByTeam: {},
    picksByTeam: {},
    rightsByTeam: {},
    selectedA: new Set(),
    selectedB: new Set(),
    selectedPicksA: new Set(),
    selectedPicksB: new Set(),
    selectedRightsA: new Set(),
    selectedRightsB: new Set(),
    noCountA: new Set(),
    noCountB: new Set(),
  },
  ui: {
    viewMode: 'tracker',
    addingPlayer: false,
    addingDeadContract: false,
    addingDraftPick: false,
    addingPlayerRight: false,
  },
  sort: {
    tracker: { key: 'team_code', dir: 'asc' },
    players: { key: 'position', dir: 'asc' },
    dead_contracts: { key: 'label', dir: 'asc' },
    exceptions: { key: 'label', dir: 'asc' },
    player_rights: { key: 'label', dir: 'asc' },
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
const ALL_SEASONS = [2025, 2026, 2027, 2028, 2029, 2030];

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

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function visibleSeasonYears() {
  const currentYear = Number(state.settings.current_year || 2025);
  return ALL_SEASONS.filter((season) => season >= currentYear);
}

function applySeasonColumnVisibility() {
  const currentYear = Number(state.settings.current_year || 2025);
  const tableConfigs = [
    { selector: '#playersTable', seasonOffset: 6 },
    { selector: '#deadContractsTable', seasonOffset: 2 },
  ];
  tableConfigs.forEach(({ selector, seasonOffset }) => {
    const table = document.querySelector(selector);
    if (!table) return;
    ALL_SEASONS.forEach((season, idx) => {
      const columnIndex = seasonOffset + idx + 1;
      table.querySelectorAll(`tr > *:nth-child(${columnIndex})`).forEach((cell) => {
        cell.classList.toggle('season-hidden', season < currentYear);
        if (cell.tagName === 'TH') {
          const label = seasonLabel(season);
          cell.textContent = label;
          cell.dataset.label = label;
        }
      });
    });
  });
}

function moveBucketLabel(bucket) {
  return normalizeMoveBucket(bucket) === 'post30' ? 'Movimientos restantes (post-30)' : 'Movimientos restantes (pre-30)';
}

function normalizeMoveBucket(bucket) {
  return String(bucket || '').trim().toLowerCase() === 'post30' ? 'post30' : 'pre30';
}

function formatMoveLogItem(item) {
  const details = item?.details && typeof item.details === 'object' ? item.details : {};
  const delta = Number(item?.delta || 0);
  const sign = delta > 0 ? '+' : '';
  const players = Array.isArray(details.players) ? details.players : [];
  const playersExcluded = Array.isArray(details.players_excluded) ? details.players_excluded : [];
  const pickRefs = Array.isArray(details.pick_refs) ? details.pick_refs : [];
  const bits = [];
  if (players.length) bits.push(`Players: ${players.join(', ')}`);
  if (pickRefs.length) bits.push(`Picks: ${pickRefs.join(', ')}`);
  if (playersExcluded.length) bits.push(`Excluded: ${playersExcluded.join(', ')}`);
  if (details.target_remaining != null) bits.push(`Target remaining: ${details.target_remaining}`);
  const meta = bits.length ? `<div class="move-log-meta">${escapeHtml(bits.join(' · '))}</div>` : '';
  return `
    <article class="move-log-item">
      <div class="move-log-head">
        <div>
          <strong>${escapeHtml(item.note || item.source_type || 'Move entry')}</strong>
          <div class="move-log-subhead">${escapeHtml(moveBucketLabel(item.bucket))}</div>
        </div>
        <span class="move-log-delta">${sign}${delta}</span>
      </div>
      ${meta}
      <div class="move-log-time">${escapeHtml(String(item.created_at || ''))}</div>
    </article>
  `;
}

function openMoveLogModal(title, rows) {
  const modal = document.getElementById('moveLogModal');
  const titleEl = document.getElementById('moveLogModalTitle');
  const body = document.getElementById('moveLogModalBody');
  if (!modal || !titleEl || !body) return;
  titleEl.textContent = title;
  body.innerHTML = rows.length
    ? rows.map((row) => formatMoveLogItem(row)).join('')
    : '<div class="move-log-empty">No transfer-move entries yet.</div>';
  modal.classList.remove('section-hidden');
}

function closeMoveLogModal() {
  document.getElementById('moveLogModal')?.classList.add('section-hidden');
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

function filenameFromContentDisposition(headerValue, fallback) {
  const header = String(headerValue || '');
  const utfMatch = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch) {
    try {
      return decodeURIComponent(utfMatch[1].trim());
    } catch {
      return fallback;
    }
  }
  const plainMatch = header.match(/filename="?([^";]+)"?/i);
  return plainMatch ? plainMatch[1].trim() : fallback;
}

async function downloadBackup(buttonEl) {
  const originalText = buttonEl?.textContent || 'Download backup';
  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = 'Preparing...';
  }
  try {
    const headers = {};
    if (state.csrfToken) headers['X-CSRF-Token'] = state.csrfToken;
    const res = await fetch('/api/admin/backup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: '{}',
    });
    if (!res.ok) {
      if (res.status === 401) {
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }
      if (res.status === 403) {
        throw new Error('Security check failed. Refresh and log in again.');
      }
      const text = await res.text();
      throw new Error(`Backup failed (${res.status}): ${text}`);
    }
    const blob = await res.blob();
    const filename = filenameFromContentDisposition(
      res.headers.get('Content-Disposition'),
      `anba-league-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.db`,
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } finally {
    if (buttonEl) {
      buttonEl.disabled = false;
      buttonEl.textContent = originalText;
    }
  }
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
  updateSortIndicators('playerRightsTable', state.sort.player_rights);

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

  updateSortIndicators('exceptionsTable', state.sort.exceptions);
  document.querySelectorAll('#exceptionsTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const curr = state.sort.exceptions;
      state.sort.exceptions = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      renderExceptions();
      updateSortIndicators('exceptionsTable', state.sort.exceptions);
    });
  });

  document.querySelectorAll('#playerRightsTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const curr = state.sort.player_rights;
      state.sort.player_rights = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      renderPlayerRights();
      updateSortIndicators('playerRightsTable', state.sort.player_rights);
    });
  });
}

function teamLogoCandidates(code) {
  const normalized = String(code || '').trim().toUpperCase();
  const fileMap = {
    LAL: 'lal.png',
  };
  return [`/team-icons/${fileMap[normalized] || `${normalized}.png`}`];
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

    const label = document.createElement('span');
    label.className = 'team-code-label';
    label.textContent = t.code;

    btn.appendChild(fallback);
    btn.appendChild(img);
    btn.appendChild(label);
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
  const currentYear = Number(state.settings.current_year || 2025);
  state.trade.picksByTeam[teamCode] = (data.assets || []).filter((asset) => {
    return asset.asset_type === 'draft_pick'
      && Number(asset.year) === currentYear + 1
      && String(asset.draft_round || '').trim().toLowerCase().includes('1')
      && String(asset.draft_pick_type || '').trim().toLowerCase() !== 'sold';
  });
  state.trade.rightsByTeam[teamCode] = (data.assets || [])
    .filter((asset) => asset.asset_type === 'player_right');
  return state.trade.playersByTeam[teamCode];
}

function renderTradePlayers(side) {
  const isA = side === 'A';
  const teamCode = isA ? state.trade.teamA : state.trade.teamB;
  const list = document.getElementById(isA ? 'tradePlayersA' : 'tradePlayersB');
  const selected = isA ? state.trade.selectedA : state.trade.selectedB;
  const noCount = isA ? state.trade.noCountA : state.trade.noCountB;

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
    const row = document.createElement('div');
    row.className = 'trade-player-row';
    row.innerHTML = `
      <input type="checkbox" data-player-id="${p.id}" ${selected.has(p.id) ? 'checked' : ''} aria-label="Include ${escapeHtml(p.name || 'Unnamed')} in trade">
      <span class="trade-player-name">${p.name || 'Unnamed'}</span>
      <span>${p.position || ''}</span>
      <span>${p.bird_rights || ''}</span>
      <label class="trade-player-flag">
        <input type="checkbox" data-no-count-player-id="${p.id}" ${noCount.has(p.id) ? 'checked' : ''} aria-label="Exclude ${escapeHtml(p.name || 'Unnamed')} from move count">
        <small>No count</small>
      </label>
    `;
    const cb = row.querySelector('input[type="checkbox"]');
    const noCountCb = row.querySelector('[data-no-count-player-id]');
    cb.addEventListener('change', () => {
      if (cb.checked) selected.add(p.id);
      else selected.delete(p.id);
    });
    noCountCb.addEventListener('change', () => {
      if (noCountCb.checked) noCount.add(p.id);
      else noCount.delete(p.id);
    });
    list.appendChild(row);
  });
}

function renderTradePicks(side) {
  const isA = side === 'A';
  const teamCode = isA ? state.trade.teamA : state.trade.teamB;
  const list = document.getElementById(isA ? 'tradePicksA' : 'tradePicksB');
  const selected = isA ? state.trade.selectedPicksA : state.trade.selectedPicksB;

  if (!teamCode) {
    list.innerHTML = '<div>Select a team</div>';
    return;
  }

  const picks = state.trade.picksByTeam[teamCode] || [];
  if (picks.length === 0) {
    list.innerHTML = '<div>No eligible next-year 1st-round picks.</div>';
    return;
  }

  list.innerHTML = '';
  picks.forEach((pick) => {
    const ownerCode = String(pick.draft_pick_type || '').trim().toLowerCase() === 'acquired'
      ? (pick.original_owner || 'Other')
      : teamCode;
    const row = document.createElement('div');
    row.className = 'trade-player-row trade-pick-row';
    row.innerHTML = `
      <input type="checkbox" data-pick-id="${pick.id}" ${selected.has(pick.id) ? 'checked' : ''} aria-label="Include pick in trade">
      <span class="trade-player-name">${escapeHtml(String(pick.label || '1st pick'))}</span>
      <span>${escapeHtml(String(pick.year || ''))}</span>
      <span>${escapeHtml(String(ownerCode || ''))}</span>
    `;
    const cb = row.querySelector('[data-pick-id]');
    cb.addEventListener('change', () => {
      if (cb.checked) selected.add(pick.id);
      else selected.delete(pick.id);
    });
    list.appendChild(row);
  });
}

function renderTradeRights(side) {
  const isA = side === 'A';
  const teamCode = isA ? state.trade.teamA : state.trade.teamB;
  const list = document.getElementById(isA ? 'tradeRightsA' : 'tradeRightsB');
  const selected = isA ? state.trade.selectedRightsA : state.trade.selectedRightsB;

  if (!teamCode) {
    list.innerHTML = '<div>Select a team</div>';
    return;
  }

  const rights = state.trade.rightsByTeam[teamCode] || [];
  if (rights.length === 0) {
    list.innerHTML = '<div>No player rights.</div>';
    return;
  }

  list.innerHTML = '';
  rights.forEach((right) => {
    const row = document.createElement('div');
    row.className = 'trade-player-row trade-right-row';
    row.innerHTML = `
      <input type="checkbox" data-right-id="${right.id}" ${selected.has(right.id) ? 'checked' : ''} aria-label="Include ${escapeHtml(right.label || 'player right')} rights in trade">
      <span class="trade-player-name">${escapeHtml(String(right.label || 'Player right'))}</span>
      <span>${escapeHtml(String(right.detail || ''))}</span>
    `;
    const cb = row.querySelector('[data-right-id]');
    cb.addEventListener('change', () => {
      if (cb.checked) selected.add(right.id);
      else selected.delete(right.id);
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
  renderTradePicks('A');
  renderTradePicks('B');
  renderTradeRights('A');
  renderTradeRights('B');
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
  state.trade.selectedPicksA.clear();
  state.trade.selectedPicksB.clear();
  state.trade.selectedRightsA.clear();
  state.trade.selectedRightsB.clear();
  state.trade.noCountA.clear();
  state.trade.noCountB.clear();
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
  const tradeBucketSelect = document.getElementById('tradeBucketSelect');
  if (tradeBucketSelect) tradeBucketSelect.value = normalizeMoveBucket(state.settings.trade_move_phase);

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
  const pickIdsA = Array.from(state.trade.selectedPicksA);
  const pickIdsB = Array.from(state.trade.selectedPicksB);
  const rightIdsA = Array.from(state.trade.selectedRightsA);
  const rightIdsB = Array.from(state.trade.selectedRightsB);
  if ((fromA.length + pickIdsA.length + rightIdsA.length) === 0 || (fromB.length + pickIdsB.length + rightIdsB.length) === 0) {
    alert('Select at least one outgoing asset from each team.');
    return;
  }
  const tradeBucket = normalizeMoveBucket(document.getElementById('tradeBucketSelect')?.value || state.settings.trade_move_phase);

  const ok = confirm(
    `Confirm trade:\n- ${teamA}: ${fromA.length} player(s), ${pickIdsA.length} pick(s), ${rightIdsA.length} right(s)\n- ${teamB}: ${fromB.length} player(s), ${pickIdsB.length} pick(s), ${rightIdsB.length} right(s)\n- Bucket: ${moveBucketLabel(tradeBucket)}`
  );
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
        pick_ids_a: pickIdsA,
        pick_ids_b: pickIdsB,
        right_ids_a: rightIdsA,
        right_ids_b: rightIdsB,
        no_count_players_a: Array.from(state.trade.noCountA),
        no_count_players_b: Array.from(state.trade.noCountB),
        trade_bucket: tradeBucket,
      }),
    });
    if (!result.ok) {
      throw new Error('Trade validation failed.');
    }
    state.trade.playersByTeam = {};
    state.trade.picksByTeam = {};
    state.trade.rightsByTeam = {};
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
    state.trade.selectedPicksA.clear();
    state.trade.selectedRightsA.clear();
    state.trade.noCountA.clear();
    await loadTradeTeamPlayers(next);
    renderTradePlayers('A');
    renderTradePicks('A');
    renderTradeRights('A');
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
    state.trade.selectedPicksB.clear();
    state.trade.selectedRightsB.clear();
    state.trade.noCountB.clear();
    await loadTradeTeamPlayers(next);
    renderTradePlayers('B');
    renderTradePicks('B');
    renderTradeRights('B');
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

  const toggleSection = (id, hidden) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('section-hidden', hidden);
  };

  toggleSection('trackerSection', !showTracker);
  toggleSection('teamMeta', !showTeam);
  toggleSection('settingsSection', !showLeagueSettings);
  toggleSection('adminLogsSection', !showAdminLog);
  toggleSection('rosterSection', !showTeam);
  toggleSection('deadContractsSection', !showTeam);
  toggleSection('exceptionsSection', !showTeam);
  toggleSection('assetsSection', !showTeam);
  toggleSection('draftAssetsSection', !showTeam);
  toggleSection('playerRightsSection', !showTeam);
  toggleSection('importantFiguresSection', !showTeam);
  syncAdminMobileInfoButton();

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

function setAdminMobileOverlayVisible(backdropId, isVisible) {
  const backdrop = document.getElementById(backdropId);
  if (!backdrop) return;
  backdrop.classList.toggle('section-hidden', !isVisible);
  backdrop.setAttribute('aria-hidden', isVisible ? 'false' : 'true');
}

function closeAdminMobileSidebar() {
  setAdminMobileOverlayVisible('adminMobileSidebarBackdrop', false);
}

function openAdminMobileSidebar() {
  setAdminMobileOverlayVisible('adminMobileSidebarBackdrop', true);
}

function closeAdminMobileInfo() {
  setAdminMobileOverlayVisible('adminMobileInfoBackdrop', false);
}

function syncAdminMobileInfoButton() {
  const btn = document.getElementById('mobileInfoBtn');
  if (!btn) return;
  btn.hidden = !(state.teamData && state.ui.viewMode === 'team');
}

function openAdminMobileInfo() {
  const list = document.getElementById('adminMobileInfoList');
  if (!list || !state.teamData?.summary) return;
  const s = state.teamData.summary;
  const m = state.teamData.move_summary || {};
  const cashLimitTotal = Number(s.cash_limit_total || state.settings.cash_limit_total || 0);
  const pills = [];
  if (Number(s.room_to_luxury) < 0) pills.push('Encima del luxury');
  if (Number(s.room_to_first_apron) < 0) pills.push('Encima del 1er apron');
  if (Number(s.room_to_second_apron) < 0) pills.push('Encima del 2do apron');
  const pillsHtml = pills.length
    ? `<div class="mobile-info-status">${pills.map((txt) => `<div class="mobile-info-pill">${escapeHtml(txt)}</div>`).join('')}</div>`
    : '';
  list.innerHTML = `
    ${pillsHtml}
    <div class="mobile-info-summary cards">
      <article class="card card-summary">
        <div class="label">CAP Total</div>
        <div class="value">${formatMoneyDots(s.cap_figure)}</div>
        <div class="card-modifiers">
          <div class="card-modifier">
            <span class="card-modifier-label">Espacio CAP</span>
            <span class="card-modifier-value">${formatMoneyDots(s.room_to_cap)}</span>
          </div>
          <div class="card-modifier">
            <span class="card-modifier-label">Espacio 1er Apron</span>
            <span class="card-modifier-value">${formatMoneyDots(s.room_to_first_apron)}</span>
          </div>
          <div class="card-modifier">
            <span class="card-modifier-label">Espacio 2do Apron</span>
            <span class="card-modifier-value">${formatMoneyDots(s.room_to_second_apron)}</span>
          </div>
        </div>
      </article>
      <article class="card card-summary">
        <div class="label">Cash</div>
        <div class="card-modifiers card-modifiers-no-border">
          <div class="card-modifier">
            <span class="card-modifier-label">Recibido / total</span>
            <span class="card-modifier-value">${formatMoneyDots(s.cash_received)} / ${formatMoneyDots(cashLimitTotal)}</span>
          </div>
          <div class="card-modifier">
            <span class="card-modifier-label">Enviado / total</span>
            <span class="card-modifier-value">${formatMoneyDots(s.cash_sent)} / ${formatMoneyDots(cashLimitTotal)}</span>
          </div>
        </div>
      </article>
      <article class="card card-summary">
        <div class="label">Transfer moves</div>
        <div class="card-modifiers card-modifiers-no-border">
          <div class="card-modifier">
            <span class="card-modifier-label">Pre-30</span>
            <span class="card-modifier-value">${formatDots(m.remaining_pre30 ?? 0)} / ${formatDots(m.limit_pre30 ?? 0)}</span>
          </div>
          <div class="card-modifier">
            <span class="card-modifier-label">Post-30</span>
            <span class="card-modifier-value">${formatDots(m.remaining_post30 ?? 0)} / ${formatDots(m.limit_post30 ?? 0)}</span>
          </div>
        </div>
      </article>
    </div>
  `;
  setAdminMobileOverlayVisible('adminMobileInfoBackdrop', true);
}

function setupAdminMobileNav() {
  const menuBtn = document.getElementById('mobileMenuBtn');
  const closeBtn = document.getElementById('adminMobileSidebarCloseBtn');
  const backdrop = document.getElementById('adminMobileSidebarBackdrop');
  const trackerBtn = document.getElementById('adminMobileTrackerBtn');
  const logBtn = document.getElementById('adminMobileLogBtn');
  const settingsBtn = document.getElementById('adminMobileSettingsBtn');
  const logoutBtn = document.getElementById('adminMobileLogoutBtn');
  const infoBtn = document.getElementById('mobileInfoBtn');
  const infoCloseBtn = document.getElementById('adminMobileInfoCloseBtn');
  const infoBackdrop = document.getElementById('adminMobileInfoBackdrop');

  if (menuBtn) menuBtn.addEventListener('click', () => openAdminMobileSidebar());
  if (closeBtn) closeBtn.addEventListener('click', () => closeAdminMobileSidebar());
  if (backdrop) {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeAdminMobileSidebar();
    });
  }
  if (trackerBtn) {
    trackerBtn.addEventListener('click', async () => {
      closeAdminMobileSidebar();
      await loadTracker();
    });
  }
  if (logBtn) {
    logBtn.addEventListener('click', async () => {
      closeAdminMobileSidebar();
      setViewMode('admin-log');
      setPageHeading('ANBA Admin Log', '');
      renderCapStatusPills({});
      await loadAdminLogs();
    });
  }
  if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
      closeAdminMobileSidebar();
      setViewMode('admin-settings');
      setPageHeading('ANBA League Settings', '');
      renderCapStatusPills({});
    });
  }
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      await api('/api/auth/logout', { method: 'POST', body: '{}' });
      window.location.href = '/login';
    });
  }
  if (infoBtn) infoBtn.addEventListener('click', () => openAdminMobileInfo());
  if (infoCloseBtn) infoCloseBtn.addEventListener('click', () => closeAdminMobileInfo());
  if (infoBackdrop) {
    infoBackdrop.addEventListener('click', (e) => {
      if (e.target === infoBackdrop) closeAdminMobileInfo();
    });
  }
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
  const m = state.teamData.move_summary || {};
  const currentYear = Number(s.current_year || state.settings.current_year || 2025);
  const currentSeason = seasonLabel(currentYear);
  const cashLimitTotal = Number(s.cash_limit_total || state.settings.cash_limit_total || 0);
  setPageHeading(t.name || 'Team', t.gm || '');
  renderCapStatusPills(s);
  wrap.innerHTML = `
    <article class="card card-summary card-summary-split">
      <div class="card-summary-col">
        <div class="label">CAP Total (${currentSeason})</div>
        <div class="value">${formatMoneyDots(s.cap_figure)}</div>
        <div class="card-modifiers">
          <div class="card-modifier card-modifier-${s.room_to_cap >= 0 ? 'positive' : 'negative'}">
            <span class="card-modifier-label">Espacio CAP</span>
            <span class="card-modifier-value">${formatMoneyDots(s.room_to_cap)}</span>
          </div>
        </div>
      </div>
      <div class="card-summary-col">
        <div class="label">GASTO Total (${currentSeason})</div>
        <div class="value">${formatMoneyDots(s.payroll)}</div>
        <div class="card-modifiers">
          <div class="card-modifier card-modifier-${s.room_to_first_apron >= 0 ? 'positive' : 'negative'}">
            <span class="card-modifier-label">Espacio 1er Apron</span>
            <span class="card-modifier-value">${formatMoneyDots(s.room_to_first_apron)}</span>
          </div>
          <div class="card-modifier card-modifier-${s.room_to_second_apron >= 0 ? 'positive' : 'negative'}">
            <span class="card-modifier-label">Espacio 2do Apron</span>
            <span class="card-modifier-value">${formatMoneyDots(s.room_to_second_apron)}</span>
          </div>
        </div>
      </div>
    </article>
    <article class="card card-summary card-summary-split">
      <div class="card-summary-col">
        <div class="label">Cash</div>
        <div class="card-modifiers card-modifiers-no-border">
          <div class="card-modifier card-modifier-editor">
            <span class="card-modifier-label">Cash recibido / total</span>
            <div class="summary-inline-editor">
              <input id="summaryCashReceivedInput" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(s.cash_received))}">
              <span class="card-modifier-value">${formatMoneyDots(cashLimitTotal)}</span>
            </div>
          </div>
          <div class="card-modifier card-modifier-editor">
            <span class="card-modifier-label">Cash enviado / total</span>
            <div class="summary-inline-editor">
              <input id="summaryCashSentInput" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(s.cash_sent))}">
              <span class="card-modifier-value">${formatMoneyDots(cashLimitTotal)}</span>
            </div>
          </div>
        </div>
        <div class="summary-inline-actions">
          <button id="summaryCashSaveBtn" type="button">Save balances</button>
        </div>
      </div>
      <div class="card-summary-col">
        <div class="label">Transfer moves</div>
        <div class="card-modifiers card-modifiers-no-border">
          <div class="card-modifier card-modifier-editor">
            <span class="card-modifier-label">
              Movimientos restantes (pre-30)
              <button id="moveLogPre30Btn" type="button" class="info-chip-btn" aria-label="Open pre-30 move log">i</button>
            </span>
            <div class="summary-inline-editor">
              <input id="summaryMovePre30Input" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(m.remaining_pre30 ?? 0))}">
              <span class="card-modifier-value">${formatDots(m.limit_pre30 ?? 0)}</span>
            </div>
          </div>
          <div class="card-modifier card-modifier-editor">
            <span class="card-modifier-label">
              Movimientos restantes (post-30)
              <button id="moveLogPost30Btn" type="button" class="info-chip-btn" aria-label="Open post-30 move log">i</button>
            </span>
            <div class="summary-inline-editor">
              <input id="summaryMovePost30Input" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(m.remaining_post30 ?? 0))}">
              <span class="card-modifier-value">${formatDots(m.limit_post30 ?? 0)}</span>
            </div>
          </div>
        </div>
        <div class="summary-inline-actions">
          <button id="summaryMovesSaveBtn" type="button">Save moves</button>
        </div>
      </div>
    </article>
  `;
  const summaryCashReceivedInput = document.getElementById('summaryCashReceivedInput');
  const summaryCashSentInput = document.getElementById('summaryCashSentInput');
  const summaryCashSaveBtn = document.getElementById('summaryCashSaveBtn');
  if (summaryCashReceivedInput && summaryCashSentInput && summaryCashSaveBtn) {
    summaryCashSaveBtn.addEventListener('click', async () => {
      await saveCurrentTeamCash(summaryCashReceivedInput, summaryCashSentInput, summaryCashSaveBtn);
    });
  }
  const summaryMovePre30Input = document.getElementById('summaryMovePre30Input');
  const summaryMovePost30Input = document.getElementById('summaryMovePost30Input');
  const summaryMovesSaveBtn = document.getElementById('summaryMovesSaveBtn');
  if (summaryMovePre30Input && summaryMovePost30Input && summaryMovesSaveBtn) {
    summaryMovesSaveBtn.addEventListener('click', async () => {
      await saveCurrentTeamMoves(summaryMovePre30Input, summaryMovePost30Input, summaryMovesSaveBtn);
    });
  }
  document.getElementById('moveLogPre30Btn')?.addEventListener('click', () => {
    const rows = (state.teamData.move_summary?.log || []).filter((item) => normalizeMoveBucket(item.bucket) === 'pre30');
    openMoveLogModal(`${t.code} · ${moveBucketLabel('pre30')}`, rows);
  });
  document.getElementById('moveLogPost30Btn')?.addEventListener('click', () => {
    const rows = (state.teamData.move_summary?.log || []).filter((item) => normalizeMoveBucket(item.bucket) === 'post30');
    openMoveLogModal(`${t.code} · ${moveBucketLabel('post30')}`, rows);
  });
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

function cancelAddPlayerRow() {
  state.ui.addingPlayer = false;
  renderPlayers();
}

function playerDraftPayloadFromRow(row) {
  const payload = { team_code: state.teamCode };
  const fields = ['name', 'position', 'bird_rights', 'rating', 'years_left'];
  fields.forEach((key) => {
    const el = row.querySelector(`[data-new-field="${key}"]`);
    const value = String(el?.value || '').trim();
    if (value) payload[key] = value;
  });
  for (const season of ALL_SEASONS) {
    const salary = String(row.querySelector(`[data-new-field="salary_${season}_text"]`)?.value || '').trim();
    const option = String(row.querySelector(`[data-new-option-field="option_${season}"]`)?.value || '').trim();
    if (salary) payload[`salary_${season}_text`] = salary;
    if (option) payload[`option_${season}`] = option;
  }
  return payload;
}

function playerDraftHasContent(payload) {
  return Object.entries(payload).some(([key, value]) => key !== 'team_code' && String(value || '').trim() !== '');
}

async function saveAddPlayerRow(row) {
  const payload = playerDraftPayloadFromRow(row);
  if (!playerDraftHasContent(payload)) {
    cancelAddPlayerRow();
    return;
  }
  if (!String(payload.name || '').trim()) payload.name = 'New Player';
  state.ui.addingPlayer = false;
  await api('/api/players', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  await loadTeam(state.teamCode);
}

function bindDraftEditor(container, saveFn, discardFn) {
  let busy = false;
  const guardedSave = async () => {
    if (busy) return;
    busy = true;
    try {
      await saveFn();
    } finally {
      busy = false;
    }
  };

  container.addEventListener('focusout', () => {
    setTimeout(() => {
      if (!document.body.contains(container)) return;
      if (container.contains(document.activeElement)) return;
      void guardedSave().catch((err) => {
        alert(err.message);
      });
    }, 0);
  });

  const saveBtn = container.querySelector('[data-action="save-draft"]');
  const discardBtn = container.querySelector('[data-action="discard-draft"]');
  if (saveBtn) {
    saveBtn.addEventListener('click', (e) => {
      e.preventDefault();
      void guardedSave().catch((err) => {
        alert(err.message);
      });
    });
  }
  if (discardBtn) {
    discardBtn.addEventListener('click', (e) => {
      e.preventDefault();
      discardFn();
    });
  }
}

function appendAddPlayerRow(tbody) {
  const tr = document.createElement('tr');
  tr.className = 'table-add-editor-row';
  tr.innerHTML = `
    <td><span class="table-add-badge">+</span></td>
    <td><input data-new-field="name" data-autofocus placeholder="Player name"></td>
    <td><input data-new-field="position" placeholder="PG"></td>
    <td>
      <select data-new-field="bird_rights">
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
    </td>
    <td><input data-new-field="rating" placeholder="Rating"></td>
    <td><input data-new-field="years_left" placeholder="Years"></td>
    <td><div class="salary-cell-admin"><input data-new-field="salary_2025_text" placeholder="0"><select data-new-option-field="option_2025"><option value="">-</option><option value="TO">TO</option><option value="PO">PO</option><option value="QO">QO</option><option value="GAP">GAP</option></select></div></td>
    <td><div class="salary-cell-admin"><input data-new-field="salary_2026_text" placeholder="0"><select data-new-option-field="option_2026"><option value="">-</option><option value="TO">TO</option><option value="PO">PO</option><option value="QO">QO</option><option value="GAP">GAP</option></select></div></td>
    <td><div class="salary-cell-admin"><input data-new-field="salary_2027_text" placeholder="0"><select data-new-option-field="option_2027"><option value="">-</option><option value="TO">TO</option><option value="PO">PO</option><option value="QO">QO</option><option value="GAP">GAP</option></select></div></td>
    <td><div class="salary-cell-admin"><input data-new-field="salary_2028_text" placeholder="0"><select data-new-option-field="option_2028"><option value="">-</option><option value="TO">TO</option><option value="PO">PO</option><option value="QO">QO</option><option value="GAP">GAP</option></select></div></td>
    <td><div class="salary-cell-admin"><input data-new-field="salary_2029_text" placeholder="0"><select data-new-option-field="option_2029"><option value="">-</option><option value="TO">TO</option><option value="PO">PO</option><option value="QO">QO</option><option value="GAP">GAP</option></select></div></td>
    <td><div class="salary-cell-admin"><input data-new-field="salary_2030_text" placeholder="0"><select data-new-option-field="option_2030"><option value="">-</option><option value="TO">TO</option><option value="PO">PO</option><option value="QO">QO</option><option value="GAP">GAP</option></select></div></td>
    <td></td>
    <td class="table-add-actions-cell">
      <button type="button" class="inline-save" data-action="save-draft">✓</button>
      <button type="button" class="inline-cancel" data-action="discard-draft">✕</button>
    </td>
  `;
  tbody.appendChild(tr);
  bindDraftEditor(
    tr,
    () => saveAddPlayerRow(tr),
    () => cancelAddPlayerRow(),
  );
  requestAnimationFrame(() => {
    tr.querySelector('[data-autofocus]')?.focus();
  });
}

function appendAddPlayerTriggerRow(tbody) {
  const tr = document.createElement('tr');
  tr.className = 'table-add-trigger-row';
  tr.innerHTML = `
    <td colspan="14">
      <button type="button" class="table-add-trigger">
        <span class="table-add-badge">+</span>
        <span>Add player</span>
      </button>
    </td>
  `;
  tr.querySelector('.table-add-trigger').addEventListener('click', () => {
    state.ui.addingPlayer = true;
    renderPlayers();
  });
  tbody.appendChild(tr);
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
  if (state.ui.addingPlayer) appendAddPlayerRow(tbody);
  else appendAddPlayerTriggerRow(tbody);
  syncSelectAllPlayers();
  applySeasonColumnVisibility();
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
      notes: p.notes || null,
    };
    ALL_SEASONS.forEach((season) => {
      payload[`salary_${season}_text`] = p[`salary_${season}_text`] || null;
      payload[`option_${season}`] = p[`option_${season}`] || null;
    });
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
  const appendDraftAddCard = () => {
    if (!state.ui.addingDraftPick) {
      const addCard = document.createElement('button');
      addCard.type = 'button';
      addCard.className = 'draft-pick-card draft-pick-card--add';
      addCard.innerHTML = `
        <span class="table-add-badge">+</span>
        <span class="draft-add-label">Add draft asset</span>
      `;
      addCard.addEventListener('click', () => {
        state.ui.addingDraftPick = true;
        renderAssets();
      });
      board.appendChild(addCard);
      return;
    }

    const ownerOptions = state.teams
      .filter((t) => t.code !== state.teamCode)
      .map((t) => `<option value="${t.code}">${t.code} - ${t.name}</option>`)
      .join('');
    const card = document.createElement('article');
    card.className = 'draft-pick-card admin-pick-card draft-pick-card--editor';
    card.innerHTML = `
      <div class="pick-card-logo-wrap pick-card-logo-wrap--placeholder">
        <span class="pick-owner-fallback">+</span>
      </div>
      <div class="pick-editor-grid">
        <label>Type
          <select data-new-field="draft_pick_type">
            <option value="own">Own</option>
            <option value="acquired">Acquired</option>
            <option value="sold">Sold</option>
          </select>
        </label>
        <label>Round
          <select data-new-field="draft_round">
            <option value="1st">1st round</option>
            <option value="2nd">2nd round</option>
          </select>
        </label>
        <label>Year
          <input data-new-field="year" data-autofocus type="text" value="${state.settings.current_year || 2025}">
        </label>
        <label data-owner-wrap>Original owner
          <select data-new-field="original_owner">
            <option value="">Select owner</option>
            ${ownerOptions}
          </select>
        </label>
        <label class="pick-detail-input">Details
          <input data-new-field="detail" type="text" value="">
        </label>
        <label class="pick-checkbox-field">
          <input data-new-field="draft_pick_restricted" type="checkbox">
          <span>Restricted?</span>
        </label>
        <label class="pick-checkbox-field">
          <input data-new-field="draft_pick_protected" type="checkbox">
          <span>Protected?</span>
        </label>
      </div>
      <div class="pick-card-actions">
        <button type="button" data-action="save-draft" class="inline-save">✓</button>
        <button type="button" data-action="discard-draft" class="inline-cancel">✕</button>
      </div>
    `;

    const typeSelect = card.querySelector('[data-new-field="draft_pick_type"]');
    const ownerWrap = card.querySelector('[data-owner-wrap]');
    const ownerSelect = card.querySelector('[data-new-field="original_owner"]');
    const syncOwnerField = () => {
      ownerWrap.style.display = typeSelect.value === 'acquired' ? 'grid' : 'none';
      if (typeSelect.value !== 'acquired') ownerSelect.value = '';
    };
    syncOwnerField();
    typeSelect.addEventListener('change', syncOwnerField);

    const discard = () => {
      state.ui.addingDraftPick = false;
      renderAssets();
    };
    const save = async () => {
      const defaultYear = String(state.settings.current_year || 2025);
      const payload = {
        team_code: state.teamCode,
        asset_type: 'draft_pick',
        draft_pick_type: String(card.querySelector('[data-new-field="draft_pick_type"]')?.value || 'own').trim() || 'own',
        draft_round: String(card.querySelector('[data-new-field="draft_round"]')?.value || '1st').trim() || '1st',
        year: String(card.querySelector('[data-new-field="year"]')?.value || '').trim(),
        detail: String(card.querySelector('[data-new-field="detail"]')?.value || '').trim(),
        original_owner: String(card.querySelector('[data-new-field="original_owner"]')?.value || '').trim(),
        draft_pick_restricted: Boolean(card.querySelector('[data-new-field="draft_pick_restricted"]')?.checked),
        draft_pick_protected: Boolean(card.querySelector('[data-new-field="draft_pick_protected"]')?.checked),
      };
      const hasContent = (
        payload.year !== defaultYear
        || Boolean(payload.detail)
        || Boolean(payload.original_owner)
        || payload.draft_pick_type !== 'own'
        || payload.draft_round !== '1st'
        || payload.draft_pick_restricted
        || payload.draft_pick_protected
      );
      if (!hasContent) {
        discard();
        return;
      }
      if (!payload.year) payload.year = defaultYear;
      payload.label = `${payload.draft_round} pick`;
      if (payload.draft_pick_type !== 'acquired') payload.original_owner = '';
      state.ui.addingDraftPick = false;
      await api('/api/assets', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await loadTeam(state.teamCode);
    };

    bindDraftEditor(card, save, discard);
    board.appendChild(card);
    requestAnimationFrame(() => {
      card.querySelector('[data-autofocus]')?.focus();
    });
  };

  if (picks.length === 0) {
    appendDraftAddCard();
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
        const isRestricted = Number(pick.draft_pick_restricted || 0) !== 0;
        const ownerTheme = TEAM_THEMES[ownerCode] || { primary: '#0f766e', secondary: '#99f6e4' };
        const ownerPrimaryRgb = hexToRgb(ownerTheme.primary);
        const ownerSecondaryRgb = hexToRgb(ownerTheme.secondary);
        const card = document.createElement('article');
        card.className = 'draft-pick-card admin-pick-card';
        if (isRestricted) card.classList.add('draft-pick-card--restricted');
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
              <input data-field="detail" type="text" value="${escapeHtml(pick.detail || '')}">
            </label>
            <label class="pick-checkbox-field">
              <input data-field="draft_pick_restricted" type="checkbox" ${Number(pick.draft_pick_restricted || 0) ? 'checked' : ''}>
              <span>Restricted?</span>
            </label>
            <label class="pick-checkbox-field">
              <input data-field="draft_pick_protected" type="checkbox" ${Number(pick.draft_pick_protected || 0) ? 'checked' : ''}>
              <span>Protected?</span>
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
        const restrictedInput = card.querySelector('[data-field="draft_pick_restricted"]');
        const protectedInput = card.querySelector('[data-field="draft_pick_protected"]');
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

        const persistDraftFlag = async (input, field) => {
          const previous = Number(pick[field] || 0) !== 0;
          const next = Boolean(input.checked);
          input.disabled = true;
          try {
            await api(`/api/assets/${pick.id}`, {
              method: 'PATCH',
              body: JSON.stringify({ [field]: next }),
            });
            pick[field] = next ? 1 : 0;
            if (field === 'draft_pick_restricted') {
              card.classList.toggle('draft-pick-card--restricted', next);
            }
          } catch (err) {
            input.checked = previous;
            alert(`Draft pick flag save failed: ${err.message}`);
          } finally {
            input.disabled = false;
          }
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
        restrictedInput.addEventListener('change', () => {
          void persistDraftFlag(restrictedInput, 'draft_pick_restricted');
        });
        protectedInput.addEventListener('change', () => {
          void persistDraftFlag(protectedInput, 'draft_pick_protected');
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
  appendDraftAddCard();
}

function renderPlayerRights() {
  const tbody = document.querySelector('#playerRightsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  const rows = sortedRows(
    (state.teamData.assets || []).filter((a) => a.asset_type === 'player_right'),
    state.sort.player_rights,
  );

  rows.forEach((item) => {
    const tr = document.createElement('tr');
    tr.dataset.id = item.id;
    tr.innerHTML = `
      <td><input data-field="label"></td>
      <td><input data-field="detail"></td>
      <td>
        <button data-action="delete-player-right" class="danger" type="button">Delete</button>
      </td>
    `;

    tr.querySelectorAll('[data-field]').forEach((el) => {
      const key = el.dataset.field;
      el.value = item[key] == null ? '' : item[key];
      attachInlineEditor(el, async (value) => {
        await api(`/api/assets/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ [key]: value }),
        });
        await loadTeam(state.teamCode);
      });
    });

    tr.querySelector('[data-action="delete-player-right"]').addEventListener('click', async () => {
      if (!confirm('Delete this player right?')) return;
      await api(`/api/assets/${item.id}`, { method: 'DELETE' });
      await loadTeam(state.teamCode);
    });

    tbody.appendChild(tr);
  });

  if (state.ui.addingPlayerRight) {
    const tr = document.createElement('tr');
    tr.className = 'table-add-editor-row';
    tr.innerHTML = `
      <td><input data-new-field="label" data-autofocus placeholder="Player name"></td>
      <td><input data-new-field="detail" placeholder="Details"></td>
      <td class="table-add-actions-cell">
        <button type="button" class="inline-save" data-action="save-draft">✓</button>
        <button type="button" class="inline-cancel" data-action="discard-draft">✕</button>
      </td>
    `;
    const discard = () => {
      state.ui.addingPlayerRight = false;
      renderPlayerRights();
    };
    const save = async () => {
      const payload = {
        team_code: state.teamCode,
        asset_type: 'player_right',
        label: String(tr.querySelector('[data-new-field="label"]')?.value || '').trim(),
        detail: String(tr.querySelector('[data-new-field="detail"]')?.value || '').trim(),
      };
      if (!payload.label && !payload.detail) {
        discard();
        return;
      }
      if (!payload.label) payload.label = 'Player right';
      state.ui.addingPlayerRight = false;
      await api('/api/assets', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await loadTeam(state.teamCode);
    };
    tbody.appendChild(tr);
    bindDraftEditor(tr, save, discard);
    requestAnimationFrame(() => {
      tr.querySelector('[data-autofocus]')?.focus();
    });
  } else {
    const tr = document.createElement('tr');
    tr.className = 'table-add-trigger-row';
    tr.innerHTML = `
      <td colspan="3">
        <button type="button" class="table-add-trigger">
          <span class="table-add-badge">+</span>
          <span>Add player right</span>
        </button>
      </td>
    `;
    tr.querySelector('.table-add-trigger').addEventListener('click', () => {
      state.ui.addingPlayerRight = true;
      renderPlayerRights();
    });
    tbody.appendChild(tr);
  }
}

function renderExceptions() {
  const tbody = document.querySelector('#exceptionsTable tbody');
  const tpl = document.getElementById('exceptionRowTemplate');
  if (!tbody || !tpl) return;
  tbody.innerHTML = '';

  const rows = sortedRows(
    (state.teamData.assets || []).filter((a) => a.asset_type === 'exception'),
    state.sort.exceptions,
  );

  rows.forEach((item) => {
    const frag = tpl.content.cloneNode(true);
    const tr = frag.querySelector('tr');
    tr.dataset.id = item.id;

    tr.querySelectorAll('[data-field]').forEach((el) => {
      const key = el.dataset.field;
      el.value = item[key] == null ? '' : item[key];
      if (key === 'amount_text' && el.tagName === 'INPUT') {
        const parsed = parseAmount(el.value);
        if (parsed !== null) el.value = formatDots(parsed);
      }
      const wrapper = attachInlineEditor(el, async (value) => {
        await api(`/api/assets/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ [key]: value }),
        });
        await loadTeam(state.teamCode);
      });
      if (key === 'amount_text') {
        wrapper.classList.add('salary-edit');
      }
    });

    tr.querySelector('[data-action="delete-exception"]').addEventListener('click', async () => {
      if (!confirm('Delete this exception?')) return;
      await api(`/api/assets/${item.id}`, { method: 'DELETE' });
      await loadTeam(state.teamCode);
    });

    tbody.appendChild(frag);
  });

  const addRow = document.createElement('tr');
  addRow.className = 'table-add-trigger-row';
  addRow.innerHTML = `
    <td colspan="5">
      <button type="button" class="table-add-trigger">
        <span class="table-add-badge">+</span>
        <span>Add exception</span>
      </button>
    </td>
  `;
  addRow.querySelector('.table-add-trigger').addEventListener('click', async () => {
    const payload = {
      team_code: state.teamCode,
      asset_type: 'exception',
      label: 'New Exception',
      exception_type: 'Mid-Level',
      amount_text: '0',
    };
    await api('/api/assets', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await loadTeam(state.teamCode);
  });
  tbody.appendChild(addRow);
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
      if (key.startsWith('salary_') && el.tagName === 'INPUT') {
        const parsed = parseAmount(el.value);
        if (parsed !== null) el.value = formatDots(parsed);
      }

      const wrapper = attachInlineEditor(el, async (value) => {
        await api(`/api/dead-contracts/${d.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ [key]: value }),
        });
        await refreshSummary();
      });

      if (key.startsWith('salary_')) {
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
  if (state.ui.addingDeadContract) {
    const tr = document.createElement('tr');
    tr.className = 'table-add-editor-row';
    tr.innerHTML = `
      <td><input data-new-field="label" data-autofocus placeholder="Dead Contract"></td>
      <td>
        <select data-new-field="dead_type">
          <option value="normal">Normal</option>
          <option value="two_way">Two Way</option>
        </select>
      </td>
      <td><input data-new-field="salary_2025_text" placeholder="0"></td>
      <td><input data-new-field="salary_2026_text" placeholder="0"></td>
      <td><input data-new-field="salary_2027_text" placeholder="0"></td>
      <td><input data-new-field="salary_2028_text" placeholder="0"></td>
      <td><input data-new-field="salary_2029_text" placeholder="0"></td>
      <td><input data-new-field="salary_2030_text" placeholder="0"></td>
      <td class="table-add-actions-cell">
        <button type="button" class="inline-save" data-action="save-draft">✓</button>
        <button type="button" class="inline-cancel" data-action="discard-draft">✕</button>
      </td>
    `;
    const discard = () => {
      state.ui.addingDeadContract = false;
      renderDeadContracts();
    };
    const save = async () => {
      const payload = {
        team_code: state.teamCode,
        dead_type: String(tr.querySelector('[data-new-field="dead_type"]')?.value || 'normal').trim() || 'normal',
        label: String(tr.querySelector('[data-new-field="label"]')?.value || '').trim(),
      };
      let hasSalary = false;
      for (const season of ALL_SEASONS) {
        const value = String(tr.querySelector(`[data-new-field="salary_${season}_text"]`)?.value || '').trim();
        if (value) hasSalary = true;
        payload[`salary_${season}_text`] = value || null;
      }
      if (!payload.label && !hasSalary && payload.dead_type === 'normal') {
        discard();
        return;
      }
      if (!payload.label) payload.label = 'Dead Contract';
      state.ui.addingDeadContract = false;
      await api('/api/dead-contracts', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await loadTeam(state.teamCode);
    };
    tbody.appendChild(tr);
    bindDraftEditor(tr, save, discard);
    requestAnimationFrame(() => {
      tr.querySelector('[data-autofocus]')?.focus();
    });
  } else {
    const tr = document.createElement('tr');
    tr.className = 'table-add-trigger-row';
    tr.innerHTML = `
      <td colspan="4">
        <button type="button" class="table-add-trigger">
          <span class="table-add-badge">+</span>
          <span>Add dead contract</span>
        </button>
      </td>
    `;
    tr.querySelector('.table-add-trigger').addEventListener('click', () => {
      state.ui.addingDeadContract = true;
      renderDeadContracts();
    });
    tbody.appendChild(tr);
  }
  applySeasonColumnVisibility();
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
  const cashReceivedInput = document.getElementById('teamCashReceivedInput');
  if (cashReceivedInput) cashReceivedInput.value = formatDots(data.team.cash_received || 0);
  const cashSentInput = document.getElementById('teamCashSentInput');
  if (cashSentInput) cashSentInput.value = formatDots(data.team.cash_sent || 0);
  renderTeamStrip();
  renderTeamPicker();
  renderCards();
  renderPlayers();
  renderDeadContracts();
  renderExceptions();
  renderAssets();
  renderPlayerRights();
  renderImportantFigures();
  applySeasonColumnVisibility();
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

async function saveCurrentTeamCash(receivedInputEl, sentInputEl, buttonEl) {
  if (!state.teamCode) {
    alert('No team selected.');
    return;
  }
  if (!receivedInputEl || !sentInputEl || !buttonEl) return;
  const cashReceived = parseAmount(receivedInputEl.value);
  const cashSent = parseAmount(sentInputEl.value);
  if (cashReceived == null || cashReceived < 0) {
    alert('Invalid cash recibido value.');
    return;
  }
  if (cashSent == null || cashSent < 0) {
    alert('Invalid cash enviado value.');
    return;
  }
  buttonEl.disabled = true;
  const oldText = buttonEl.textContent;
  buttonEl.textContent = 'Saving...';
  try {
    await api(`/api/teams/${state.teamCode}`, {
      method: 'PATCH',
      body: JSON.stringify({ cash_received: cashReceived, cash_sent: cashSent }),
    });
    await loadTeam(state.teamCode);
    buttonEl.textContent = 'Saved';
    setTimeout(() => {
      buttonEl.textContent = oldText;
    }, 900);
  } catch (err) {
    buttonEl.textContent = oldText;
    alert(`Cash save failed: ${err.message}`);
  } finally {
    buttonEl.disabled = false;
  }
}

async function saveCurrentTeamMoves(pre30InputEl, post30InputEl, buttonEl) {
  if (!state.teamCode || !state.teamData?.summary) {
    alert('No team selected.');
    return;
  }
  const pre30Remaining = parseAmount(pre30InputEl?.value);
  const post30Remaining = parseAmount(post30InputEl?.value);
  if (pre30Remaining == null || pre30Remaining < 0) {
    alert('Invalid pre-30 remaining value.');
    return;
  }
  if (post30Remaining == null || post30Remaining < 0) {
    alert('Invalid post-30 remaining value.');
    return;
  }
  buttonEl.disabled = true;
  const oldText = buttonEl.textContent;
  buttonEl.textContent = 'Saving...';
  try {
    const seasonYear = Number(state.teamData.summary.current_year || state.settings.current_year || 2025);
    await api(`/api/teams/${state.teamCode}/move-adjustment`, {
      method: 'POST',
      body: JSON.stringify({
        season_year: seasonYear,
        bucket: 'pre30',
        target_remaining: pre30Remaining,
      }),
    });
    await api(`/api/teams/${state.teamCode}/move-adjustment`, {
      method: 'POST',
      body: JSON.stringify({
        season_year: seasonYear,
        bucket: 'post30',
        target_remaining: post30Remaining,
      }),
    });
    await loadTeam(state.teamCode);
    buttonEl.textContent = 'Saved';
    setTimeout(() => {
      buttonEl.textContent = oldText;
    }, 900);
  } catch (err) {
    buttonEl.textContent = oldText;
    alert(`Move save failed: ${err.message}`);
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
  state.settings = { ...state.settings, ...(settingsRes.settings || {}) };
  const capInput = document.getElementById('salaryCap2025Input');
  const firstApronInput = document.getElementById('firstApronInput');
  const secondApronInput = document.getElementById('secondApronInput');
  const cashLimitTotalInput = document.getElementById('cashLimitTotalInput');
  const tradeMoveLimitPre30Input = document.getElementById('tradeMoveLimitPre30Input');
  const tradeMoveLimitPost30Input = document.getElementById('tradeMoveLimitPost30Input');
  const tradeMovePhaseSelect = document.getElementById('tradeMovePhaseSelect');
  const currentYearSelect = document.getElementById('currentYearSelect');
  capInput.value = formatDots(state.settings.salary_cap_2025);
  firstApronInput.value = formatDots(state.settings.first_apron);
  secondApronInput.value = formatDots(state.settings.second_apron);
  cashLimitTotalInput.value = formatDots(state.settings.cash_limit_total);
  tradeMoveLimitPre30Input.value = formatDots(state.settings.trade_move_limit_pre30);
  tradeMoveLimitPost30Input.value = formatDots(state.settings.trade_move_limit_post30);
  tradeMovePhaseSelect.value = normalizeMoveBucket(state.settings.trade_move_phase);
  currentYearSelect.value = String(state.settings.current_year || 2025);

  const teamsRes = await api('/api/teams');
  state.teams = teamsRes.teams;
  setupSorting();
  renderTeamStrip();
  renderTeamPicker();
  setupTradeModal();
  setupAdminMenu();
  setupAdminMobileNav();
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
    const parsedCashLimitTotal = parseAmount(cashLimitTotalInput.value);
    if (parsedCashLimitTotal == null || parsedCashLimitTotal < 0) {
      alert('Invalid cash total value.');
      return;
    }
    const parsedTradeMoveLimitPre30 = parseAmount(tradeMoveLimitPre30Input.value);
    if (parsedTradeMoveLimitPre30 == null || parsedTradeMoveLimitPre30 < 0) {
      alert('Invalid pre-30 move limit.');
      return;
    }
    const parsedTradeMoveLimitPost30 = parseAmount(tradeMoveLimitPost30Input.value);
    if (parsedTradeMoveLimitPost30 == null || parsedTradeMoveLimitPost30 < 0) {
      alert('Invalid post-30 move limit.');
      return;
    }
    const selectedYear = Number(currentYearSelect.value);
    if (!Number.isInteger(selectedYear) || selectedYear < 2025 || selectedYear > 2030) {
      alert('Invalid current year.');
      return;
    }
    const selectedTradeMovePhase = normalizeMoveBucket(tradeMovePhaseSelect.value);
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
        cash_limit_total: parsedCashLimitTotal,
        trade_move_limit_pre30: parsedTradeMoveLimitPre30,
        trade_move_limit_post30: parsedTradeMoveLimitPost30,
        trade_move_phase: selectedTradeMovePhase,
      }),
    });
    state.settings = {
      ...state.settings,
      ...(result.settings || {}),
      cash_limit_total: result.settings?.cash_limit_total ?? parsedCashLimitTotal,
    };
    capInput.value = formatDots(state.settings.salary_cap_2025);
    firstApronInput.value = formatDots(state.settings.first_apron);
    secondApronInput.value = formatDots(state.settings.second_apron);
    cashLimitTotalInput.value = formatDots(state.settings.cash_limit_total);
    tradeMoveLimitPre30Input.value = formatDots(state.settings.trade_move_limit_pre30);
    tradeMoveLimitPost30Input.value = formatDots(state.settings.trade_move_limit_post30);
    tradeMovePhaseSelect.value = normalizeMoveBucket(state.settings.trade_move_phase);
    currentYearSelect.value = String(state.settings.current_year || 2025);
    if (state.ui.viewMode === 'team' && state.teamCode) {
      await loadTeam(state.teamCode);
    } else if (state.ui.viewMode === 'tracker') {
      await loadTracker();
    } else {
      await refreshAdminLogsSafe();
    }
  });

  document.getElementById('downloadBackupBtn').addEventListener('click', async () => {
    const btn = document.getElementById('downloadBackupBtn');
    try {
      await downloadBackup(btn);
    } catch (err) {
      alert(err.message || String(err));
    }
  });

  document.getElementById('progressYearBtn').addEventListener('click', async () => {
    const previousYear = Number(state.settings.current_year || 2025);
    if (previousYear >= 2030) {
      alert('Cannot progress beyond 2030-31 with the current data model.');
      return;
    }
    const fromLabel = seasonLabel(previousYear);
    const toLabel = seasonLabel(previousYear + 1);
    const confirmed = confirm(
      `Progress from ${fromLabel} to ${toLabel}?\n\nThis will:\n- create a season snapshot backup\n- reset cash balances\n- delete ${fromLabel} draft assets\n- hide ${fromLabel} salary columns across the site`
    );
    if (!confirmed) return;

    const result = await api('/api/settings/progress-year', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    state.settings = { ...state.settings, ...(result.settings || {}) };
    capInput.value = formatDots(state.settings.salary_cap_2025);
    firstApronInput.value = formatDots(state.settings.first_apron);
    secondApronInput.value = formatDots(state.settings.second_apron);
    cashLimitTotalInput.value = formatDots(state.settings.cash_limit_total);
    tradeMoveLimitPre30Input.value = formatDots(state.settings.trade_move_limit_pre30);
    tradeMoveLimitPost30Input.value = formatDots(state.settings.trade_move_limit_post30);
    tradeMovePhaseSelect.value = normalizeMoveBucket(state.settings.trade_move_phase);
    currentYearSelect.value = String(state.settings.current_year || 2025);

    if (state.ui.viewMode === 'team' && state.teamCode) {
      await loadTeam(state.teamCode);
    } else {
      await loadTracker();
    }
    alert(`Season progressed to ${seasonLabel(state.settings.current_year || 2025)}.`);
  });

  document.getElementById('saveTeamGmInlineBtn').addEventListener('click', async () => {
    const input = document.getElementById('teamGmInlineInput');
    const btn = document.getElementById('saveTeamGmInlineBtn');
    await saveCurrentTeamGm(input, btn);
  });
  document.getElementById('saveTeamCashInlineBtn').addEventListener('click', async () => {
    const receivedInput = document.getElementById('teamCashReceivedInput');
    const sentInput = document.getElementById('teamCashSentInput');
    const btn = document.getElementById('saveTeamCashInlineBtn');
    await saveCurrentTeamCash(receivedInput, sentInput, btn);
  });
  document.getElementById('closeMoveLogModalBtn')?.addEventListener('click', closeMoveLogModal);
  document.getElementById('moveLogModal')?.addEventListener('click', (e) => {
    if (e.target?.id === 'moveLogModal') closeMoveLogModal();
  });

  await loadTracker();
}

init().catch((err) => {
  console.error(err);
  alert(err.message);
});
