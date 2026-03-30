const state = {
  teams: [],
  trackerRows: [],
  teamCode: null,
  teamData: null,
  auth: null,
  csrfToken: null,
  settings: {
    salary_cap_2025: 154647000,
    current_year: 2025,
  },
  sort: {
    tracker: { key: 'team_code', dir: 'asc' },
    players: { key: 'position', dir: 'asc' },
    dead_contracts: { key: 'dead_type', dir: 'asc' },
  },
  ui: {
    rosterView: 'list',
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

function typeClass(value) {
  const v = String(value || '').toLowerCase().replaceAll('(', '').replaceAll(')', '').replaceAll('/', '').replaceAll(' ', '');
  return v ? `type-pill--${v}` : '';
}

function contractOptionClass(value) {
  const v = String(value || '').toUpperCase();
  if (!v) return '';
  return `salary-option--${v.toLowerCase()}`;
}

function salaryBox(obj, season) {
  const text = obj[`salary_${season}_text`];
  const num = obj[`salary_${season}_num`];
  const option = obj[`option_${season}`];
  const optClass = contractOptionClass(option);
  const cap = Number(state.settings.salary_cap_2025 || 154647000);
  if (num !== null && num !== undefined && Number.isFinite(Number(num))) {
    const val = Number(num);
    const pct = cap > 0 ? ((val / cap) * 100).toFixed(1) : '0.0';
    return `
      <div class="salary-pill ${optClass}">
        <span class="salary-main">${formatDots(val)}</span>
        <span class="salary-pct">${pct}%</span>
      </div>
      ${option ? `<span class="contract-opt-pill ${optClass}">${option}</span>` : ''}
    `;
  }
  if (text !== null && text !== undefined && String(text).trim() !== '') {
    return `
      <div class="salary-pill salary-pill-text ${optClass}"><span class="salary-main">${escapeHtml(text)}</span></div>
      ${option ? `<span class="contract-opt-pill ${optClass}">${option}</span>` : ''}
    `;
  }
  return '';
}

function salaryText(obj, season) {
  const text = obj[`salary_${season}_text`];
  const num = obj[`salary_${season}_num`];
  if (text !== null && text !== undefined && String(text).trim() !== '') {
    return String(text);
  }
  if (num !== null && num !== undefined) {
    return money(num);
  }
  return '';
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
  const num = Number(String(val).replaceAll('.', '').replaceAll(',', '.'));
  if (Number.isFinite(num) && key.includes('salary_')) return num;
  if (Number.isFinite(num) && (key === 'year' || key === 'rating' || key === 'years_left' || key === 'amount_num')) return num;
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

function renderAuthControls() {
  const badge = document.getElementById('authBadge');
  const loginLink = document.getElementById('loginLink');
  const adminLink = document.getElementById('adminLink');
  const logoutBtn = document.getElementById('logoutBtn');

  const auth = state.auth;
  if (!auth || !auth.authenticated) {
    badge.textContent = '';
    loginLink.hidden = false;
    adminLink.hidden = false;
    logoutBtn.hidden = true;
    return;
  }

  const userName = auth.user?.name || auth.user?.email || 'Signed In';
  badge.textContent = `${userName} (${auth.role})`;
  loginLink.hidden = true;
  adminLink.hidden = auth.role !== 'admin';
  logoutBtn.hidden = false;
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

function setViewMode(mode) {
  const trackerSection = document.getElementById('trackerSection');
  const teamMeta = document.getElementById('teamMeta');
  const rosterSection = document.getElementById('rosterSection');
  const deadContractsSection = document.getElementById('deadContractsSection');
  const assetsSection = document.getElementById('assetsSection');
  const showTeam = mode === 'team';

  trackerSection.classList.toggle('section-hidden', showTeam);
  teamMeta.classList.toggle('section-hidden', !showTeam);
  rosterSection.classList.toggle('section-hidden', !showTeam);
  deadContractsSection.classList.toggle('section-hidden', !showTeam);
  assetsSection.classList.toggle('section-hidden', !showTeam);
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
  const gmText = t.gm ? `GM: ${t.gm}` : 'GM: N/A';
  document.getElementById('pageTitle').textContent = `${t.name} — ${gmText}`;
  renderCapStatusPills(s);
  const items = [
    { label: 'Salary Cap 25/26', value: formatDots(state.settings.salary_cap_2025), tone: '' },
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

function renderCapStatusPills(summary) {
  const wrap = document.getElementById('capStatusPills');
  if (!wrap) return;
  const pills = [];
  if (Number(summary.room_to_luxury) < 0) pills.push('Encima del luxury');
  if (Number(summary.room_to_first_apron) < 0) pills.push('Encima del 1er apron');
  if (Number(summary.room_to_second_apron) < 0) pills.push('Encima del 2do apron');
  wrap.innerHTML = pills.map((txt) => `<span class="top-status-pill">${txt}</span>`).join('');
}

function preferredRosterView() {
  return window.matchMedia('(max-width: 720px)').matches ? 'cards' : 'list';
}

function setRosterView(nextView, savePreference = true) {
  const view = nextView === 'cards' ? 'cards' : 'list';
  state.ui.rosterView = view;
  const tableWrap = document.getElementById('rosterTableWrap');
  const cardsWrap = document.getElementById('playersCards');
  const listBtn = document.getElementById('rosterViewListBtn');
  const cardsBtn = document.getElementById('rosterViewCardsBtn');
  if (tableWrap) tableWrap.classList.toggle('section-hidden', view !== 'list');
  if (cardsWrap) cardsWrap.classList.toggle('section-hidden', view !== 'cards');
  if (listBtn) listBtn.classList.toggle('active', view === 'list');
  if (cardsBtn) cardsBtn.classList.toggle('active', view === 'cards');
  if (!savePreference) return;
  try {
    window.localStorage.setItem('anba_roster_view', view);
  } catch {
    // localStorage may be unavailable in private browsing modes.
  }
}

function setupRosterViewControl() {
  const buttons = document.querySelectorAll('.roster-view-btn[data-view]');
  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      setRosterView(btn.dataset.view || 'list', true);
    });
  });
}

function renderPlayers() {
  const tbody = document.querySelector('#playersTable tbody');
  const cardsWrap = document.getElementById('playersCards');
  tbody.innerHTML = '';
  if (cardsWrap) cardsWrap.innerHTML = '';

  const rows = sortedRows(state.teamData.players, state.sort.players);
  rows.forEach((p) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <div class="player-cell">
          <span class="player-name">${p.name || ''}</span>
          <span class="player-tags">
            ${p.position ? `<span class="pos-pill">${p.position}</span>` : ''}
            ${p.rating ? `<span class="meta-pill">${p.rating}</span>` : ''}
          </span>
        </div>
      </td>
      <td>${p.bird_rights ? `<span class="type-pill ${typeClass(p.bird_rights)}">${p.bird_rights}</span>` : ''}</td>
      <td>${p.years_left || ''}</td>
      <td>${salaryBox(p, 2025)}</td>
      <td>${salaryBox(p, 2026)}</td>
      <td>${salaryBox(p, 2027)}</td>
      <td>${salaryBox(p, 2028)}</td>
      <td>${salaryBox(p, 2029)}</td>
      <td>${salaryBox(p, 2030)}</td>
    `;
    tbody.appendChild(tr);

    if (cardsWrap) {
      const contractRows = [2025, 2026, 2027, 2028, 2029, 2030]
        .map((season) => ({ season, content: salaryBox(p, season) }))
        .filter((row) => Boolean(row.content));
      const card = document.createElement('article');
      card.className = 'player-card';
      card.innerHTML = `
        <div class="player-card-head">
          <div class="player-card-name">${escapeHtml(p.name || '')}</div>
          <div class="player-card-tags">
            ${p.position ? `<span class="pos-pill">${escapeHtml(p.position)}</span>` : ''}
            ${p.rating ? `<span class="meta-pill">${escapeHtml(p.rating)}</span>` : ''}
            ${p.bird_rights ? `<span class="type-pill ${typeClass(p.bird_rights)}">${escapeHtml(p.bird_rights)}</span>` : ''}
            ${p.years_left ? `<span class="meta-pill">${escapeHtml(p.years_left)} yrs</span>` : ''}
          </div>
        </div>
        ${contractRows.length ? `
          <div class="player-card-contracts">
            ${contractRows.map((row) => `
              <div class="player-contract-row">
                <div class="player-contract-season">${seasonLabel(row.season)}</div>
                <div class="player-contract-value">${row.content}</div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      `;
      cardsWrap.appendChild(card);
    }
  });
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
        const pickRound = normalizedRound(pick);
        const owner = pick.draft_pick_type === 'acquired'
          ? (pick.original_owner || '')
          : state.teamCode;
        const ownerTheme = TEAM_THEMES[owner] || { primary: '#0f766e', secondary: '#99f6e4' };
        const ownerPrimaryRgb = hexToRgb(ownerTheme.primary);
        const ownerSecondaryRgb = hexToRgb(ownerTheme.secondary);
        const card = document.createElement('article');
        card.className = 'draft-pick-card';
        if (pickType === 'sold') card.classList.add('draft-pick-card--sold');
        card.style.setProperty('--pick-primary-rgb', `${ownerPrimaryRgb.r}, ${ownerPrimaryRgb.g}, ${ownerPrimaryRgb.b}`);
        card.style.setProperty('--pick-secondary-rgb', `${ownerSecondaryRgb.r}, ${ownerSecondaryRgb.g}, ${ownerSecondaryRgb.b}`);
        card.tabIndex = 0;
        card.innerHTML = `
          <div class="pick-card-logo-wrap">
            <span class="pick-owner-fallback">${owner || 'N/A'}</span>
            <img class="pick-owner-logo" alt="${owner || ''} logo">
          </div>
          <div class="pick-card-meta">
            <div class="pick-year">${pick.year}</div>
            <div class="pick-badges">
              <span class="meta-pill pick-badge-round pick-badge-round--${pickRound === '2nd' ? '2nd' : '1st'}">${pickRound.toUpperCase()}</span>
              <span class="type-pill pick-badge-type pick-badge-type--${pickType}">${pickType.toUpperCase()}</span>
            </div>
          </div>
          <div class="pick-detail">${pick.detail || 'No details'}</div>
        `;
        const roundBadge = card.querySelector('.pick-badge-round');
        if (roundBadge) {
          if (pickRound === '1st') {
            roundBadge.style.background = '#fef3c7';
            roundBadge.style.borderColor = '#f59e0b';
            roundBadge.style.color = '#92400e';
          } else {
            roundBadge.style.background = '#e2e8f0';
            roundBadge.style.borderColor = '#94a3b8';
            roundBadge.style.color = '#334155';
          }
        }
        const typeBadge = card.querySelector('.pick-badge-type');
        if (typeBadge && pickType === 'acquired') {
          typeBadge.style.background = '#dcfce7';
          typeBadge.style.borderColor = '#86efac';
          typeBadge.style.color = '#166534';
        }
        const img = card.querySelector('.pick-owner-logo');
        const fallback = card.querySelector('.pick-owner-fallback');
        const candidates = owner ? teamLogoCandidates(owner) : [];
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

        card.addEventListener('click', () => {
          card.classList.toggle('show-detail');
        });
        grid.appendChild(card);
      });

    seasonWrap.appendChild(grid);
    board.appendChild(seasonWrap);
  });
}

function renderDeadContracts() {
  const tbody = document.querySelector('#deadContractsTable tbody');
  tbody.innerHTML = '';

  const rows = sortedRows(state.teamData.dead_contracts || [], state.sort.dead_contracts);
  rows.forEach((d) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${d.dead_type === 'two_way' ? 'Two Way' : 'Normal'}</td>
      <td>${d.label || ''}</td>
      <td>${d.amount_num ? `<div class="salary-pill"><span class="salary-main">${formatDots(d.amount_num)}</span></div>` : (d.amount_text || '')}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadTeam(code) {
  const data = await api(`/api/teams/${code}`);
  state.teamCode = code;
  state.teamData = data;
  applyTeamTheme(code);
  setViewMode('team');
  renderTeamStrip();
  renderTeamPicker();
  renderCards();
  renderPlayers();
  renderDeadContracts();
  renderAssets();
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
  applyTeamTheme('');
  setViewMode('tracker');
  document.getElementById('pageTitle').textContent = 'ANBA League Tracker';
  renderCapStatusPills({});
  renderTeamStrip();
  renderTeamPicker();
  renderTracker();
}

async function init() {
  state.auth = await api('/api/auth/status');
  state.csrfToken = state.auth?.csrf_token || null;
  const settingsRes = await api('/api/settings');
  state.settings = settingsRes.settings || state.settings;
  renderAuthControls();

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST', body: '{}' });
    window.location.href = '/';
  });
  document.getElementById('trackerHomeBtn').addEventListener('click', async () => {
    await loadTracker();
  });

  const teamsRes = await api('/api/teams');
  state.teams = teamsRes.teams;
  setupSorting();
  setupRosterViewControl();
  let savedRosterView = null;
  try {
    savedRosterView = window.localStorage.getItem('anba_roster_view');
  } catch {
    savedRosterView = null;
  }
  setRosterView(savedRosterView || preferredRosterView(), false);
  renderTeamStrip();
  renderTeamPicker();
  await loadTracker();
}

init().catch((err) => {
  console.error(err);
  alert(err.message);
});
