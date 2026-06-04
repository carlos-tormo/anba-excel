const MOVE_LIMIT_PRE30 = 20;
const MOVE_LIMIT_POST30 = 4;

const state = {
  teams: [],
  trackerRows: [],
  freeAgents: [],
  draftOrder: {
    draft_year: null,
    draft_order: [],
  },
  teamCode: null,
  teamData: null,
  auth: null,
  csrfToken: null,
  settings: {
    salary_cap_2025: 154647000,
    current_year: 2025,
    cash_limit_total: 0,
    first_apron: 195945000,
    second_apron: 207824000,
    luxury_cap: 187896105,
    minimum_cap_allowed: 139182300,
    roster_standard_min: 14,
    roster_standard_max: 15,
    roster_standard_offseason_max: 18,
    roster_two_way_min: 0,
    roster_two_way_max: 3,
  },
  sort: {
    tracker: { key: 'team_code', dir: 'asc' },
    players: { key: 'position', dir: 'asc' },
    dead_contracts: { key: 'label', dir: 'asc' },
    exceptions: { key: 'label', dir: 'asc' },
    player_rights: { key: 'label', dir: 'asc' },
    free_agents: { key: 'name', dir: 'asc' },
  },
  ui: {
    viewMode: 'tracker',
    activeTeamTab: 'economy',
    rosterView: 'list',
    seasonViewStart: null,
    statusPills: [],
    mobileSidebarOpen: false,
    mobileInfoOpen: false,
  },
  locator: {
    index: null,
    loading: false,
  },
  tradeMachine: {
    selectedTeams: [],
    teamDataByCode: {},
    selections: {},
    seasonStart: null,
    loading: false,
  },
  filters: {
    guaranteedOnly: false,
    optionsOnly: false,
    showEmptyYears: true,
  },
};

const SEASON_WINDOW_SIZE = 6;
const TRADE_MACHINE_MIN_TEAMS = 2;
const TRADE_MACHINE_MAX_TEAMS = 6;
const TRADE_MATCH_LOW_BAND = 7_250_000;
const TRADE_MATCH_HIGH_BAND = 29_000_000;
const TRADE_MATCH_CUSHION = 250_000;
const TRADE_MATCH_EXPANDED_BUFFER_RATIO = 0.05513854478;
const TRADE_MATCH_EXPANDED_BUFFER_FALLBACK = 8_527_000;
const TRADE_PICK_ACTION_SEND = 'send_pick';
const TRADE_PICK_ACTION_SWAP = 'swap_rights';
const LAST_TEAM_STORAGE_KEY = 'anba_last_team_code';
const TEAM_TABS = [
  {
    id: 'economy',
    sections: ['rosterSection', 'deadContractsSection', 'exceptionsSection', 'playerRightsSection'],
  },
  {
    id: 'general',
    sections: ['teamMeta', 'importantFiguresSection', 'gmTimelineSection'],
  },
  {
    id: 'draft',
    sections: ['assetsSection'],
  },
];

const PLAYER_SORT_CYCLE = [
  { key: 'position', dir: 'asc' },
  { key: 'position', dir: 'desc' },
  { key: 'name', dir: 'asc' },
  { key: 'name', dir: 'desc' },
  { key: 'rating', dir: 'desc' },
  { key: 'rating', dir: 'asc' },
];
const POSITION_ORDER = { PG: 1, SG: 2, SF: 3, PF: 4, C: 5, TW: 6 };

function boolValue(value) {
  if (value === true) return true;
  if (typeof value === 'number') return value !== 0;
  return ['1', 'true', 'yes', 'on', 'checked'].includes(String(value || '').trim().toLowerCase());
}

function salaryProvisionalField(season) {
  return `salary_${season}_provisional`;
}

function salaryPartialGuaranteeField(season) {
  return `salary_${season}_partially_guaranteed`;
}

function salaryGuaranteedTextField(season) {
  return `salary_${season}_guaranteed_text`;
}

function salaryNoteField(season) {
  return `salary_${season}_note`;
}

function salaryNoteTextField(season) {
  return `salary_${season}_note_text`;
}

function playerUsesProvisionalAmounts(player) {
  return boolValue(player?.provisional_amounts);
}

function playerUsesPartialGuarantees(player) {
  return boolValue(player?.partially_guaranteed);
}

function playerUsesContractNotes(player) {
  return boolValue(player?.contract_notes);
}

function playerSeasonIsProvisional(player, season) {
  return playerUsesProvisionalAmounts(player) && boolValue(player?.[salaryProvisionalField(season)]);
}

function playerSeasonIsPartiallyGuaranteed(player, season) {
  return playerUsesPartialGuarantees(player) && boolValue(player?.[salaryPartialGuaranteeField(season)]);
}

function playerSeasonHasContractNote(player, season) {
  return playerUsesContractNotes(player) && boolValue(player?.[salaryNoteField(season)]);
}

function salaryInfoMessages(player, season) {
  const messages = [];
  if (playerSeasonIsProvisional(player, season)) {
    messages.push('Cifra provisional');
  }
  if (playerSeasonIsPartiallyGuaranteed(player, season)) {
    const amount = String(player?.[salaryGuaranteedTextField(season)] || '').trim();
    messages.push(amount ? `${amount} guaranteed` : 'Guaranteed amount pending');
  }
  if (playerSeasonHasContractNote(player, season)) {
    const note = String(player?.[salaryNoteTextField(season)] || '').trim();
    messages.push(note || 'Nota pendiente');
  }
  return messages;
}

function salaryInfoHtml(messages) {
  if (!messages.length) return '';
  const label = messages.join(' · ');
  return `
    <button type="button" class="salary-info-button" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}">
      i
      <span class="salary-info-pop">${messages.map((message) => `<span>${escapeHtml(message)}</span>`).join('')}</span>
    </button>
  `;
}

function bindSalaryInfoToggles(root) {
  if (!root) return;
  root.querySelectorAll('.salary-info-button').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      btn.classList.toggle('show-detail');
    });
  });
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

function darkenRgb(rgb, factor = 0.5) {
  return {
    r: Math.max(0, Math.round(rgb.r * factor)),
    g: Math.max(0, Math.round(rgb.g * factor)),
    b: Math.max(0, Math.round(rgb.b * factor)),
  };
}

function applyTeamTheme(code) {
  const theme = TEAM_THEMES[code] || { primary: '#0f766e', secondary: '#99f6e4' };
  const primaryRgb = hexToRgb(theme.primary);
  const secondaryRgb = hexToRgb(theme.secondary);
  const primaryDarkRgb = darkenRgb(primaryRgb, 0.42);
  const root = document.documentElement;
  root.style.setProperty('--team-primary', theme.primary);
  root.style.setProperty('--team-secondary', theme.secondary);
  root.style.setProperty('--team-primary-rgb', `${primaryRgb.r}, ${primaryRgb.g}, ${primaryRgb.b}`);
  root.style.setProperty('--team-secondary-rgb', `${secondaryRgb.r}, ${secondaryRgb.g}, ${secondaryRgb.b}`);
  root.style.setProperty('--team-primary-dark-rgb', `${primaryDarkRgb.r}, ${primaryDarkRgb.g}, ${primaryDarkRgb.b}`);
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

function currentSeasonStart() {
  const currentYear = Number(state.settings.current_year || 2025);
  return Number.isInteger(currentYear) ? currentYear : 2025;
}

function availableSeasonViewStarts() {
  const currentYear = currentSeasonStart();
  return Array.from({ length: SEASON_WINDOW_SIZE }, (_, idx) => currentYear + idx);
}

function normalizeSeasonViewStart(value) {
  const requested = Number(value);
  const starts = availableSeasonViewStarts();
  return starts.includes(requested) ? requested : starts[0];
}

function selectedSeasonStart() {
  const normalized = normalizeSeasonViewStart(state.ui.seasonViewStart);
  state.ui.seasonViewStart = normalized;
  return normalized;
}

function visibleSeasonYears() {
  const start = selectedSeasonStart();
  return Array.from({ length: SEASON_WINDOW_SIZE }, (_, idx) => start + idx);
}

function teamTabForSection(sectionId) {
  return TEAM_TABS.find((tab) => tab.sections.includes(sectionId))?.id || null;
}

function activeTeamTab() {
  return TEAM_TABS.some((tab) => tab.id === state.ui.activeTeamTab)
    ? state.ui.activeTeamTab
    : TEAM_TABS[0].id;
}

function syncTeamTabs() {
  const showTeam = state.ui.viewMode === 'team';
  const active = activeTeamTab();
  const tabs = document.getElementById('teamTabs');
  if (tabs) tabs.classList.toggle('section-hidden', !showTeam);

  document.querySelectorAll('[data-team-tab]').forEach((btn) => {
    const isActive = btn.dataset.teamTab === active;
    btn.classList.toggle('is-active', isActive);
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });

  TEAM_TABS.forEach((tab) => {
    tab.sections.forEach((sectionId) => {
      const section = document.getElementById(sectionId);
      if (!section) return;
      const forceHidden = sectionId === 'gmTimelineSection' && !hasTeamGmTimelineEntries();
      section.classList.toggle('section-hidden', !showTeam || tab.id !== active || forceHidden);
    });
  });
}

function setTeamTab(tabId) {
  state.ui.activeTeamTab = TEAM_TABS.some((tab) => tab.id === tabId) ? tabId : TEAM_TABS[0].id;
  syncTeamTabs();
}

function setupTeamTabs() {
  document.querySelectorAll('[data-team-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      setTeamTab(btn.dataset.teamTab);
    });
  });
  syncTeamTabs();
}

function scrollToTeamSection(sectionId) {
  const tabId = teamTabForSection(sectionId);
  if (tabId) setTeamTab(tabId);
  requestAnimationFrame(() => {
    const section = document.getElementById(sectionId);
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function syncSeasonSortsToVisibleWindow() {
  const visibleSortKeys = new Set(visibleSeasonYears().map((season) => `salary_${season}_num`));
  ['players', 'dead_contracts'].forEach((scope) => {
    const sortCfg = state.sort[scope];
    if (!sortCfg || !String(sortCfg.key || '').startsWith('salary_')) return;
    if (!visibleSortKeys.has(sortCfg.key)) {
      sortCfg.key = `salary_${selectedSeasonStart()}_num`;
    }
  });
}

function applySeasonColumnVisibility() {
  syncSeasonSortsToVisibleWindow();
  const seasons = visibleSeasonYears();
  const tableConfigs = [
    { selector: '#playersTable', seasonOffset: 3 },
    { selector: '#deadContractsTable', seasonOffset: 1 },
  ];
  tableConfigs.forEach(({ selector, seasonOffset }) => {
    const table = document.querySelector(selector);
    if (!table) return;
    seasons.forEach((season, idx) => {
      const columnIndex = seasonOffset + idx + 1;
      table.querySelectorAll(`tr > *:nth-child(${columnIndex})`).forEach((cell) => {
        cell.classList.remove('season-hidden');
        if (cell.tagName === 'TH') {
          const label = seasonLabel(season);
          cell.textContent = label;
          cell.dataset.label = label;
          cell.dataset.sort = `salary_${season}_num`;
        }
      });
    });
  });
}

function normalizeMoveBucket(bucket) {
  return String(bucket || '').trim().toLowerCase() === 'post30' ? 'post30' : 'pre30';
}

function moveBucketLabel(bucket) {
  return normalizeMoveBucket(bucket) === 'post30' ? 'Movimientos restantes (post-30)' : 'Movimientos restantes (pre-30)';
}

function formatMoveLogItem(item) {
  const details = item?.details && typeof item.details === 'object' ? item.details : {};
  const delta = Number(item?.delta || 0);
  const sign = delta > 0 ? '+' : '';
  const bits = [];
  if (Array.isArray(details.players) && details.players.length) bits.push(`Players: ${details.players.join(', ')}`);
  if (Array.isArray(details.pick_refs) && details.pick_refs.length) bits.push(`Picks: ${details.pick_refs.join(', ')}`);
  if (Array.isArray(details.players_excluded) && details.players_excluded.length) bits.push(`Excluded: ${details.players_excluded.join(', ')}`);
  if (details.target_remaining != null) bits.push(`Target remaining: ${details.target_remaining}`);
  return `
    <article class="move-log-item">
      <div class="move-log-head">
        <div>
          <strong>${escapeHtml(item.note || item.source_type || 'Move entry')}</strong>
          <div class="move-log-subhead">${escapeHtml(moveBucketLabel(item.bucket))}</div>
        </div>
        <span class="move-log-delta">${sign}${delta}</span>
      </div>
      ${bits.length ? `<div class="move-log-meta">${escapeHtml(bits.join(' · '))}</div>` : ''}
      <div class="move-log-time">${escapeHtml(String(item.created_at || ''))}</div>
    </article>
  `;
}

function openMoveLog(title, rows) {
  const backdrop = document.getElementById('moveLogBackdrop');
  const titleEl = document.getElementById('moveLogTitle');
  const list = document.getElementById('moveLogList');
  if (!backdrop || !titleEl || !list) return;
  titleEl.textContent = title;
  list.innerHTML = rows.length
    ? rows.map((row) => formatMoveLogItem(row)).join('')
    : '<div class="move-log-empty">No transfer-move entries yet.</div>';
  setMobileOverlayVisible('moveLogBackdrop', true);
}

function closeMoveLog() {
  setMobileOverlayVisible('moveLogBackdrop', false);
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

function salaryTextTagClass(value) {
  const v = String(value || '').trim().toUpperCase();
  if (v === 'FB') return 'salary-text-tag--fb';
  if (v === 'EB') return 'salary-text-tag--eb';
  if (v === 'NB') return 'salary-text-tag--nb';
  return '';
}

function numericSalary(obj, season) {
  const rawNum = obj[`salary_${season}_num`];
  if (rawNum !== null && rawNum !== undefined && Number.isFinite(Number(rawNum))) {
    return Number(rawNum);
  }
  const text = String(obj[`salary_${season}_text`] || '').trim();
  if (!text) return null;
  const cleaned = text.replaceAll(' ', '').replaceAll('.', '').replaceAll(',', '.');
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function hasSpecialTextTag(obj, season) {
  const t = String(obj[`salary_${season}_text`] || '').trim().toUpperCase();
  return t === 'FB' || t === 'EB' || t === 'NB';
}

function hasSeasonCellValue(obj, season) {
  const text = String(obj[`salary_${season}_text`] ?? '').trim();
  if (text) return true;
  const rawNum = obj[`salary_${season}_num`];
  return rawNum !== null && rawNum !== undefined && Number.isFinite(Number(rawNum));
}

function selectedSeasonFiltersActiveRows() {
  return selectedSeasonStart() > currentSeasonStart();
}

function playerHasGuaranteed(p) {
  return visibleSeasonYears().some((season) => {
    if (hasSpecialTextTag(p, season)) return false;
    const val = numericSalary(p, season);
    const option = String(p[`option_${season}`] || '').trim();
    return Number.isFinite(val) && val > 0 && !option;
  });
}

function playerHasOption(p) {
  return visibleSeasonYears().some((season) => Boolean(String(p[`option_${season}`] || '').trim()));
}

function filteredPlayers(players) {
  return players.filter((p) => {
    if (selectedSeasonFiltersActiveRows() && !hasSeasonCellValue(p, selectedSeasonStart())) return false;
    if (state.filters.guaranteedOnly && !playerHasGuaranteed(p)) return false;
    if (state.filters.optionsOnly && !playerHasOption(p)) return false;
    return true;
  });
}

function salaryCellHtml(obj, season, showEmptyYears = true) {
  const text = obj[`salary_${season}_text`];
  const num = obj[`salary_${season}_num`];
  const option = obj[`option_${season}`];
  const optClass = contractOptionClass(option);
  const textTagClass = salaryTextTagClass(text);
  const textTagCode = String(text || '').trim().toUpperCase();
  const optionCode = String(option || '').trim().toUpperCase();
  const hideOptionTag = ['FB', 'EB', 'NB'].includes(textTagCode) || ['FB', 'EB', 'NB'].includes(optionCode);
  const cap = Number(state.settings.salary_cap_2025 || 154647000);
  const isProvisional = playerSeasonIsProvisional(obj, season);
  const isPartiallyGuaranteed = playerSeasonIsPartiallyGuaranteed(obj, season);
  const hasContractNote = playerSeasonHasContractNote(obj, season);
  const infoMessages = salaryInfoMessages(obj, season);
  const infoHtml = salaryInfoHtml(infoMessages);
  const salaryStateClasses = [
    isProvisional ? 'salary-chip--provisional' : '',
    isPartiallyGuaranteed ? 'salary-chip--partial-guarantee' : '',
    hasContractNote ? 'salary-chip--note' : '',
  ].filter(Boolean).join(' ');

  if (num !== null && num !== undefined && Number.isFinite(Number(num))) {
    const val = Number(num);
    const pct = cap > 0 ? `${((val / cap) * 100).toFixed(1)}%` : '';
    return `
      <div class="salary-chip ${optClass} ${salaryStateClasses}">
        <span class="salary-chip-main">${formatDots(val)}</span>
        <span class="salary-chip-pct">${pct}</span>
        ${infoHtml}
      </div>
    `;
  }

  if (text !== null && text !== undefined && String(text).trim() !== '') {
    const upper = escapeHtml(String(text).trim().toUpperCase());
    return `
      <div class="salary-chip salary-chip-text ${textTagClass} ${hideOptionTag ? '' : optClass} ${salaryStateClasses}">
        <span class="salary-chip-main">${upper}</span>
        ${infoHtml}
      </div>
    `;
  }

  if (!showEmptyYears) return '';
  return `
    <div class="salary-empty-wrap ${isProvisional ? 'salary-empty-wrap--provisional' : ''} ${isPartiallyGuaranteed ? 'salary-empty-wrap--partial-guarantee' : ''} ${hasContractNote ? 'salary-empty-wrap--note' : ''}">
      <div class="salary-empty-bar" aria-hidden="true"></div>
      ${infoHtml}
    </div>
  `;
}

function salaryBox(obj, season) {
  return salaryCellHtml(obj, season, false);
}

function deadTypePillHtml(value) {
  const normalized = String(value || '').trim().toLowerCase() === 'two_way' ? 'two_way' : 'normal';
  if (normalized !== 'two_way') return '';
  const label = normalized === 'two_way' ? 'Two Way' : 'Normal';
  return `<span class="dead-type-pill dead-type-pill--${normalized}">${escapeHtml(label)}</span>`;
}

function deadExclusionPillsHtml(dead) {
  const pills = [];
  if (deadContractExcludedFromGasto(dead)) {
    pills.push('<span class="dead-exclusion-pill dead-exclusion-pill--gasto" title="Excluded from GASTO total">No GASTO</span>');
  }
  if (deadContractExcludedFromCap(dead)) {
    pills.push('<span class="dead-exclusion-pill dead-exclusion-pill--cap" title="Excluded from CAP total">No CAP</span>');
  }
  return pills.join('');
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

function seasonSlashLabel(startYear) {
  return seasonLabel(startYear).replace('-', '/');
}

function parseAmountLike(raw) {
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
  } else {
    cleaned = cleaned.replaceAll('.', '');
  }
  cleaned = cleaned.replace(/[^0-9.-]/g, '');
  if (!cleaned || cleaned === '-' || cleaned === '.') return null;
  const num = Number(cleaned);
  return Number.isFinite(num) ? num : null;
}

function salaryNumericValue(row, season) {
  const direct = row?.[`salary_${season}_num`];
  if (direct !== null && direct !== undefined && direct !== '' && Number.isFinite(Number(direct))) {
    return Number(direct);
  }
  return parseAmountLike(row?.[`salary_${season}_text`]) || 0;
}

function amountNumericValue(row) {
  const direct = row?.amount_num;
  if (direct !== null && direct !== undefined && direct !== '' && Number.isFinite(Number(direct))) {
    return Number(direct);
  }
  return parseAmountLike(row?.amount_text) || 0;
}

function isTwoWayPlayer(player) {
  return boolValue(player?.is_two_way) || String(player?.bird_rights || '').trim().toUpperCase() === 'TW';
}

function rosterLimits() {
  const standardMin = Math.max(0, Number(state.settings.roster_standard_min ?? 14) || 0);
  const standardMax = Math.max(standardMin, Number(state.settings.roster_standard_max ?? 15) || 0);
  const standardOffseasonMax = Math.max(standardMax, Number(state.settings.roster_standard_offseason_max ?? 18) || 0);
  const twoWayMin = Math.max(0, Number(state.settings.roster_two_way_min ?? 0) || 0);
  const twoWayMax = Math.max(twoWayMin, Number(state.settings.roster_two_way_max ?? 3) || 0);
  return { standardMin, standardMax, standardOffseasonMax, twoWayMin, twoWayMax };
}

function rosterCountFromPlayers(players = []) {
  return (players || []).reduce((counts, player) => {
    if (isTwoWayPlayer(player)) counts.twoWay += 1;
    else counts.standard += 1;
    return counts;
  }, { standard: 0, twoWay: 0 });
}

function rosterCountFromSummary(summary = {}) {
  const standard = Number(summary.roster_standard_count);
  const twoWay = Number(summary.roster_two_way_count);
  if (Number.isFinite(standard) && Number.isFinite(twoWay)) {
    return { standard, twoWay };
  }
  return rosterCountFromPlayers(state.teamData?.players || []);
}

function rosterCountStatus(kind, count, limits = rosterLimits()) {
  if (kind === 'twoWay') {
    if (count < limits.twoWayMin) {
      return { key: 'under', label: `Bajo mínimo ${limits.twoWayMin}` };
    }
    if (count > limits.twoWayMax) {
      return { key: 'over', label: `Sobre máximo ${limits.twoWayMax}` };
    }
    return { key: 'ok', label: `${limits.twoWayMin}-${limits.twoWayMax}` };
  }
  if (count < limits.standardMin) {
    return { key: 'under', label: `Bajo mínimo ${limits.standardMin}` };
  }
  if (count > limits.standardOffseasonMax) {
    return { key: 'over', label: `Sobre máximo ${limits.standardOffseasonMax}` };
  }
  if (count > limits.standardMax) {
    return { key: 'offseason', label: `Solo offseason (${limits.standardOffseasonMax} max)` };
  }
  return { key: 'ok', label: `${limits.standardMin}-${limits.standardMax}` };
}

function rosterCountChipHtml(kind, count, label) {
  const status = rosterCountStatus(kind, count);
  return `
    <span class="roster-count-chip roster-count-chip--${status.key}">
      <span>${label}</span>
      <strong>${count}</strong>
      <small>${escapeHtml(status.label)}</small>
    </span>
  `;
}

function trackerRosterCountChipHtml(kind, count) {
  const status = rosterCountStatus(kind, count);
  return `
    <span class="tracker-roster-count-chip tracker-roster-count-chip--${status.key}">
      <strong>${count}</strong>
    </span>
  `;
}

function trackerRosterHeaderHtml(kind, label, arrow = '') {
  const limits = rosterLimits();
  const range = kind === 'twoWay'
    ? `Min: ${limits.twoWayMin} · Max: ${limits.twoWayMax}`
    : `Min: ${limits.standardMin} · Max: ${limits.standardMax}`;
  return `<span class="th-main">${label}${arrow}</span><span class="th-sub">${range}</span>`;
}

function trackerSpaceValueHtml(value) {
  const numeric = Number(value || 0);
  const className = numeric < 0 ? 'is-negative' : numeric > 0 ? 'is-positive' : 'is-neutral';
  return `<span class="tracker-space-value ${className}">${formatMoneyDots(numeric)}</span>`;
}

function isTwoWayDeadContract(dead) {
  return String(dead?.dead_type || '').trim().toLowerCase().replaceAll('-', '_') === 'two_way';
}

function deadContractExcludedFromGasto(dead) {
  return boolValue(dead?.exclude_from_gasto);
}

function deadContractExcludedFromCap(dead) {
  return boolValue(dead?.exclude_from_cap);
}

function balanceSeasonYears() {
  const currentYear = currentSeasonStart();
  return Array.from({ length: SEASON_WINDOW_SIZE }, (_, idx) => currentYear + idx);
}

function teamExceptionBalanceTotal(data, season) {
  if (season !== currentSeasonStart()) return 0;
  return (data?.assets || [])
    .filter((asset) => asset.asset_type === 'exception')
    .reduce((sum, asset) => sum + amountNumericValue(asset), 0);
}

function exceptionBalanceTotal(season) {
  return teamExceptionBalanceTotal(state.teamData, season);
}

function luxuryHistoryYears() {
  const currentYear = currentSeasonStart();
  return Array.from({ length: 4 }, (_, idx) => currentYear - idx - 1);
}

function luxuryRepeaterHistoryMap(data) {
  const rows = Array.isArray(data?.luxury_history) ? data.luxury_history : [];
  return new Map(rows.map((row) => [Number(row.season_year), boolValue(row.repeater)]));
}

function luxuryRepeaterForSeason(data, season) {
  const map = luxuryRepeaterHistoryMap(data);
  const year = Number(season);
  if (map.has(year)) return Boolean(map.get(year));
  const currentYear = currentSeasonStart();
  if (year > currentYear && map.has(currentYear)) return Boolean(map.get(currentYear));
  return false;
}

function luxuryTaxAmount(overage, repeater) {
  let remaining = Math.max(0, Number(overage || 0));
  if (!remaining) return 0;
  const tierSize = 5_000_000;
  const baseRates = repeater
    ? [2.5, 2.75, 3.5, 4.25]
    : [1.5, 1.75, 2.5, 3.25];
  let tax = 0;
  let tierIndex = 0;
  while (remaining > 0) {
    const taxable = Math.min(tierSize, remaining);
    const rate = tierIndex < baseRates.length
      ? baseRates[tierIndex]
      : baseRates[baseRates.length - 1] + ((tierIndex - baseRates.length + 1) * 0.5);
    tax += taxable * rate;
    remaining -= taxable;
    tierIndex += 1;
  }
  return tax;
}

function teamSeasonBalances(data, season) {
  const players = data?.players || [];
  const deadContracts = data?.dead_contracts || [];
  const playerTotal = players.reduce((sum, player) => sum + salaryNumericValue(player, season), 0);
  const capPlayerTotal = players
    .filter((player) => !isTwoWayPlayer(player))
    .reduce((sum, player) => sum + salaryNumericValue(player, season), 0);
  const normalDeadCapTotal = deadContracts
    .filter((dead) => !isTwoWayDeadContract(dead) && !deadContractExcludedFromCap(dead))
    .reduce((sum, dead) => sum + salaryNumericValue(dead, season), 0);
  const deadGastoTotal = deadContracts
    .filter((dead) => !deadContractExcludedFromGasto(dead))
    .reduce((sum, dead) => sum + salaryNumericValue(dead, season), 0);
  const capTotal = capPlayerTotal + normalDeadCapTotal;
  const gastoTotal = playerTotal + deadGastoTotal;
  const salaryCap = Number(state.settings.salary_cap_2025 || 0);
  const luxuryCap = Number(state.settings.luxury_cap || salaryCap * 1.215 || 0);
  const luxuryOverage = Math.max(0, capTotal - luxuryCap);
  return {
    cap_total: capTotal,
    gasto_total: gastoTotal,
    apron_account: capTotal,
    luxury_tax: luxuryTaxAmount(luxuryOverage, luxuryRepeaterForSeason(data, season)),
  };
}

function seasonBalances(season) {
  return teamSeasonBalances(state.teamData, season);
}

function tradeMachineSeasonStart() {
  const selected = Number(state.tradeMachine.seasonStart || currentSeasonStart());
  return Number.isInteger(selected) ? selected : currentSeasonStart();
}

function tradeMachineDraftYearStart() {
  return tradeMachineSeasonStart() + 1;
}

function tradeMachineValidTeamCodes() {
  return new Set((state.teams || []).map((team) => team.code));
}

function tradeMachineUniqueCodes(codes) {
  const validCodes = tradeMachineValidTeamCodes();
  const seen = new Set();
  return (codes || [])
    .map((code) => String(code || '').trim().toUpperCase())
    .filter((code) => code && validCodes.has(code) && !seen.has(code) && seen.add(code));
}

function defaultTradeMachineTeams(seedCodes = []) {
  const seeded = tradeMachineUniqueCodes(seedCodes);
  const codes = seeded.length ? seeded : tradeMachineUniqueCodes([state.teamCode]);
  (state.teams || []).forEach((team) => {
    if (codes.length >= TRADE_MACHINE_MIN_TEAMS) return;
    if (!codes.includes(team.code)) codes.push(team.code);
  });
  return codes.slice(0, TRADE_MACHINE_MIN_TEAMS);
}

function tradeMachineTeamName(code) {
  return (state.teams || []).find((team) => team.code === code)?.name || code;
}

function tradeMachineTeamLogoHtml(code) {
  const normalized = String(code || '').trim().toUpperCase();
  const src = teamLogoCandidates(normalized)[0] || '';
  return `
    <span class="trade-machine-team-kicker-logo" aria-hidden="true">
      <span>${escapeHtml(normalized)}</span>
      <img src="${escapeHtml(src)}" alt="" onload="this.previousElementSibling.style.display='none'" onerror="this.style.display='none';this.previousElementSibling.style.display='inline-flex'">
    </span>
  `;
}

function tradeMachineSummaryLogoHtml(code, className = 'trade-machine-summary-mini-logo') {
  const normalized = String(code || '').trim().toUpperCase();
  if (!normalized) return '';
  const src = teamLogoCandidates(normalized)[0] || '';
  return `
    <span class="${className}" title="${escapeHtml(normalized)}" aria-label="${escapeHtml(normalized)}">
      <span>${escapeHtml(normalized)}</span>
      <img src="${escapeHtml(src)}" alt="" onload="this.previousElementSibling.style.display='none'" onerror="this.style.display='none';this.previousElementSibling.style.display='inline-flex'">
    </span>
  `;
}

function tradeMachineRecipientOptions(fromTeam, selectedTo) {
  return (state.tradeMachine.selectedTeams || [])
    .filter((code) => code !== fromTeam)
    .map((code) => `<option value="${code}" ${code === selectedTo ? 'selected' : ''}>${code}</option>`)
    .join('');
}

function tradeMachineDefaultRecipient(fromTeam) {
  return (state.tradeMachine.selectedTeams || []).find((code) => code !== fromTeam) || '';
}

function draftPickType(asset) {
  const type = String(asset?.draft_pick_type || 'own').trim().toLowerCase();
  return ['own', 'acquired', 'sold', 'conditional'].includes(type) ? type : 'own';
}

function draftPickRound(asset) {
  const roundRaw = String(asset?.draft_round || '').trim().toLowerCase();
  if (roundRaw.includes('2')) return '2nd';
  if (roundRaw.includes('1')) return '1st';
  const label = String(asset?.label || '').trim().toLowerCase();
  return label.includes('2') ? '2nd' : '1st';
}

function draftPickCountsFromAssets(assets = []) {
  const draftYearStart = currentSeasonStart() + 1;
  return (assets || []).reduce((counts, asset) => {
    if (asset?.asset_type !== 'draft_pick') return counts;
    if (draftPickType(asset) === 'sold') return counts;
    const year = Number(asset.year);
    if (Number.isFinite(year) && year < draftYearStart) return counts;
    if (draftPickRound(asset) === '2nd') counts.second += 1;
    else counts.first += 1;
    return counts;
  }, { first: 0, second: 0 });
}

function draftPickCountChipHtml(count, label) {
  return `
    <span class="draft-count-chip">
      <span>${label}</span>
      <strong>${count}</strong>
    </span>
  `;
}

function draftPickIsRestricted(asset) {
  return boolValue(asset?.draft_pick_restricted);
}

function draftPickIsProtected(asset) {
  return boolValue(asset?.draft_pick_protected);
}

function draftPickTradeOwner(asset, teamCode) {
  if (draftPickType(asset) === 'conditional') {
    return parseDraftConditionalTeams(asset?.draft_pick_conditional_teams)[0] || String(asset?.original_owner || teamCode || '').toUpperCase();
  }
  return String(asset?.original_owner || teamCode || '').toUpperCase();
}

function draftPickTradeLabel(asset, teamCode) {
  const year = Number(asset?.year);
  const yearLabel = Number.isFinite(year) ? String(year) : 'Sin año';
  const owner = draftPickTradeOwner(asset, teamCode);
  return `${yearLabel} ${draftPickRound(asset).toUpperCase()} ${owner || teamCode}`;
}

function tradeMachinePickAction(value) {
  return value === TRADE_PICK_ACTION_SWAP ? TRADE_PICK_ACTION_SWAP : TRADE_PICK_ACTION_SEND;
}

function tradeMachinePickActionOptions(selectedAction) {
  const selected = tradeMachinePickAction(selectedAction);
  return [
    [TRADE_PICK_ACTION_SEND, 'Enviar ronda'],
    [TRADE_PICK_ACTION_SWAP, 'Vender swap'],
  ].map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${label}</option>`).join('');
}

function tradeMachineAssetForSelection(meta, selection) {
  if (meta?.type !== 'pick') return meta;
  const pickAction = tradeMachinePickAction(selection?.pickAction);
  if (pickAction !== TRADE_PICK_ACTION_SWAP) {
    return { ...meta, pickAction };
  }
  const details = [meta.detail, 'La ronda no cambia de dueño; se venden derechos de intercambio.']
    .filter(Boolean)
    .join(' · ');
  return {
    ...meta,
    type: 'swap_right',
    pickAction,
    label: `Swap ${meta.label}`,
    detail: details,
  };
}

function tradeMachinePickBadges(asset) {
  const badges = [];
  const type = draftPickType(asset);
  if (draftPickIsRestricted(asset)) badges.push('<span class="trade-machine-tag trade-machine-tag--danger">Restringida</span>');
  if (draftPickIsProtected(asset)) badges.push('<span class="trade-machine-tag">Protegida</span>');
  if (type === 'conditional') badges.push('<span class="trade-machine-tag">Condicional</span>');
  if (type === 'acquired') badges.push('<span class="trade-machine-tag">Adquirida</span>');
  return badges.join('');
}

function tradeMachineAssetKey(type, fromTeam, id) {
  return `${type}:${fromTeam}:${id}`;
}

function tradeMachineSelectedAsset(key) {
  return state.tradeMachine.selections[key] || null;
}

function tradeMachineAssetMeta(key) {
  const [type, fromTeam, rawId] = String(key || '').split(':');
  const id = Number(rawId);
  const data = state.tradeMachine.teamDataByCode[fromTeam];
  if (!data || !Number.isFinite(id)) return null;
  if (type === 'player') {
    const player = (data.players || []).find((item) => Number(item.id) === id);
    if (!player) return null;
    const salary = salaryNumericValue(player, tradeMachineSeasonStart());
    return {
      key,
      type,
      id,
      fromTeam,
      label: player.name || 'Jugador',
      detail: [player.position, player.bird_rights].filter(Boolean).join(' · '),
      salary,
      capSalary: isTwoWayPlayer(player) ? 0 : salary,
      isTwoWay: isTwoWayPlayer(player),
      restricted: false,
      protected: false,
      conditional: false,
    };
  }
  if (type === 'pick') {
    const pick = (data.assets || []).find((item) => item.asset_type === 'draft_pick' && Number(item.id) === id);
    if (!pick) return null;
    return {
      key,
      type,
      id,
      fromTeam,
      label: draftPickTradeLabel(pick, fromTeam),
      detail: String(pick.detail || '').trim(),
      salary: 0,
      capSalary: 0,
      restricted: draftPickIsRestricted(pick),
      protected: draftPickIsProtected(pick),
      conditional: draftPickType(pick) === 'conditional',
      round: draftPickRound(pick),
    };
  }
  if (type === 'right') {
    const right = (data.assets || []).find((item) => item.asset_type === 'player_right' && Number(item.id) === id);
    if (!right) return null;
    return {
      key,
      type,
      id,
      fromTeam,
      label: right.label || 'Derecho de jugador',
      detail: String(right.detail || '').trim(),
      salary: 0,
      capSalary: 0,
      restricted: false,
      protected: false,
      conditional: false,
    };
  }
  return null;
}

function pruneTradeMachineSelections() {
  const teams = new Set(state.tradeMachine.selectedTeams || []);
  Object.entries(state.tradeMachine.selections || {}).forEach(([key, selection]) => {
    const meta = tradeMachineAssetMeta(key);
    if (!meta || !teams.has(selection.fromTeam) || !teams.has(selection.toTeam) || selection.fromTeam === selection.toTeam) {
      delete state.tradeMachine.selections[key];
    }
  });
}

async function ensureTradeMachineTeamData(codes) {
  const unique = tradeMachineUniqueCodes(codes);
  const missing = unique.filter((code) => !state.tradeMachine.teamDataByCode[code]);
  if (!missing.length) return;
  state.tradeMachine.loading = true;
  renderTradeMachine();
  try {
    const loaded = await Promise.all(missing.map(async (code) => [code, await api(`/api/teams/${code}`)]));
    loaded.forEach(([code, data]) => {
      state.tradeMachine.teamDataByCode[code] = data;
    });
  } finally {
    state.tradeMachine.loading = false;
  }
}

function renderTradeMachineSeasonControl() {
  const select = document.getElementById('tradeMachineSeasonSelect');
  if (!select) return;
  const current = currentSeasonStart();
  const selected = tradeMachineSeasonStart();
  select.innerHTML = availableSeasonViewStarts()
    .map((season) => {
      const suffix = season === current ? ' (actual)' : '';
      return `<option value="${season}" ${season === selected ? 'selected' : ''}>${seasonLabel(season)}${suffix}</option>`;
    })
    .join('');
}

function tradeMachineTeamSelectHtml(code, index) {
  const used = new Set((state.tradeMachine.selectedTeams || []).filter((_, idx) => idx !== index));
  const options = (state.teams || []).map((team) => `
    <option value="${team.code}" ${team.code === code ? 'selected' : ''} ${used.has(team.code) ? 'disabled' : ''}>
      ${team.code} - ${escapeHtml(team.name || team.code)}
    </option>
  `).join('');
  return `<select data-trade-team-select="${index}" aria-label="Equipo ${index + 1}">${options}</select>`;
}

function tradeMachineThresholds() {
  const salaryCap = Number(state.settings.salary_cap_2025 || 0);
  const luxuryCap = Number(state.settings.luxury_cap || salaryCap * 1.215 || 0);
  return {
    salaryCap,
    luxuryCap,
    firstApron: Number(state.settings.first_apron || 0),
    secondApron: Number(state.settings.second_apron || 0),
  };
}

function tradeMachineBalanceSnapshot(capFigure, apronFigure = capFigure) {
  const thresholds = tradeMachineThresholds();
  return [
    { key: 'cap', label: 'CAP', value: thresholds.salaryCap - Number(capFigure || 0) },
    { key: 'tax', label: 'Impuesto lujo', value: thresholds.luxuryCap - Number(capFigure || 0) },
    { key: 'first_apron', label: '1er apron', value: thresholds.firstApron - Number(apronFigure || 0) },
    { key: 'second_apron', label: '2do apron', value: thresholds.secondApron - Number(apronFigure || 0) },
  ];
}

function tradeMachineFlowSkeleton(code) {
  const data = state.tradeMachine.teamDataByCode[code] || {};
  const season = tradeMachineSeasonStart();
  const seasonTotals = teamSeasonBalances(data, season);
  const summary = data.summary || {};
  const rosterCounts = rosterCountFromPlayers(data.players || []);
  const beforeCap = season === currentSeasonStart() && Number.isFinite(Number(summary.cap_figure))
    ? Number(summary.cap_figure)
    : Number(seasonTotals.cap_total || 0);
  return {
    code,
    beforeCap,
    beforeApronAccount: beforeCap,
    incomingSalary: 0,
    outgoingSalary: 0,
    incomingCapSalary: 0,
    outgoingCapSalary: 0,
    incomingAssets: [],
    outgoingAssets: [],
    postCap: beforeCap,
    postApronAccount: beforeCap,
    beforeRosterStandard: rosterCounts.standard,
    beforeRosterTwoWay: rosterCounts.twoWay,
    postRosterStandard: rosterCounts.standard,
    postRosterTwoWay: rosterCounts.twoWay,
    beforeBalances: tradeMachineBalanceSnapshot(beforeCap),
    afterBalances: tradeMachineBalanceSnapshot(beforeCap),
  };
}

function tradeMachineFlows() {
  const flows = {};
  (state.tradeMachine.selectedTeams || []).forEach((code) => {
    flows[code] = tradeMachineFlowSkeleton(code);
  });
  Object.entries(state.tradeMachine.selections || {}).forEach(([key, selection]) => {
    const meta = tradeMachineAssetMeta(key);
    if (!meta || !flows[selection.fromTeam] || !flows[selection.toTeam]) return;
    const asset = tradeMachineAssetForSelection(meta, selection);
    const salary = Number(asset.salary || 0);
    const capSalary = Number(asset.capSalary ?? asset.salary ?? 0);
    flows[selection.fromTeam].outgoingSalary += salary;
    flows[selection.fromTeam].outgoingCapSalary += capSalary;
    flows[selection.fromTeam].outgoingAssets.push({ ...asset, toTeam: selection.toTeam });
    flows[selection.toTeam].incomingSalary += salary;
    flows[selection.toTeam].incomingCapSalary += capSalary;
    flows[selection.toTeam].incomingAssets.push({ ...asset, fromTeam: selection.fromTeam });
    if (asset.type === 'player') {
      if (asset.isTwoWay) {
        flows[selection.fromTeam].postRosterTwoWay -= 1;
        flows[selection.toTeam].postRosterTwoWay += 1;
      } else {
        flows[selection.fromTeam].postRosterStandard -= 1;
        flows[selection.toTeam].postRosterStandard += 1;
      }
    }
  });
  Object.values(flows).forEach((flow) => {
    flow.postCap = flow.beforeCap + flow.incomingCapSalary - flow.outgoingCapSalary;
    flow.postApronAccount = flow.beforeApronAccount + flow.incomingCapSalary - flow.outgoingCapSalary;
    flow.afterBalances = tradeMachineBalanceSnapshot(flow.postCap, flow.postApronAccount);
  });
  return flows;
}

function tradeMachineExpandedBuffer(salaryCap) {
  const cap = Number(salaryCap || state.settings.salary_cap_2025 || 0);
  const calculated = Math.round(cap * TRADE_MATCH_EXPANDED_BUFFER_RATIO);
  return calculated > 0 ? calculated : TRADE_MATCH_EXPANDED_BUFFER_FALLBACK;
}

function tradeMachineSalaryMatchLimit(outgoingSalary, apronLimited, salaryCap) {
  const outgoing = Number(outgoingSalary || 0);
  if (apronLimited) return outgoing;
  if (outgoing < TRADE_MATCH_LOW_BAND) return outgoing * 2 + TRADE_MATCH_CUSHION;
  if (outgoing <= TRADE_MATCH_HIGH_BAND) return outgoing + tradeMachineExpandedBuffer(salaryCap);
  return outgoing * 1.25;
}

function tradeMachineSalaryMatchIssue(code, flow) {
  const data = state.tradeMachine.teamDataByCode[code];
  if (!data) return null;
  const summary = data.summary || {};
  const thresholds = tradeMachineThresholds();
  const salaryCap = thresholds.salaryCap || Number(summary.salary_cap_2025 || 0);
  const firstApron = thresholds.firstApron;
  const secondApron = thresholds.secondApron;
  const hardCap = String(summary.apron_hard_cap || '').trim().toLowerCase();
  const postApronAccount = Number(flow.postApronAccount ?? flow.postCap ?? 0);
  if (hardCap === 'first' && firstApron > 0 && postApronAccount > firstApron) {
    return {
      severity: 'illegal',
      rule: 'hard_cap',
      teamCode: code,
      message: 'Tiene límite duro en el 1er apron y acabaría por encima.',
    };
  }
  if (hardCap === 'second' && secondApron > 0 && postApronAccount > secondApron) {
    return {
      severity: 'illegal',
      rule: 'hard_cap',
      teamCode: code,
      message: 'Tiene límite duro en el 2do apron y acabaría por encima.',
    };
  }
  if (flow.incomingSalary <= flow.outgoingSalary) return null;
  const capRoom = Math.max(0, salaryCap - flow.beforeCap);
  if (flow.beforeCap < salaryCap && flow.incomingSalary <= flow.outgoingSalary + capRoom) return null;
  if (flow.outgoingSalary <= 0) {
    return {
      severity: 'illegal',
      rule: 'salary',
      teamCode: code,
      message: `Recibe ${formatBalanceMoney(flow.incomingSalary)} sin suficiente salario enviado ni margen salarial.`,
    };
  }
  const apronLimited = hardCap === 'first'
    || hardCap === 'second'
    || (firstApron > 0 && (Number(flow.beforeApronAccount ?? flow.beforeCap ?? 0) >= firstApron || postApronAccount >= firstApron));
  const limit = tradeMachineSalaryMatchLimit(flow.outgoingSalary, apronLimited, salaryCap);
  if (flow.incomingSalary <= limit) return null;
  return {
    severity: 'illegal',
    rule: 'salary',
    teamCode: code,
    message: `Puede recibir hasta ${formatBalanceMoney(limit)} por la regla básica de cuadre salarial, pero recibe ${formatBalanceMoney(flow.incomingSalary)}.`,
  };
}

function tradeMachineIssuesForRule(issues, rule) {
  return (issues || []).filter((issue) => issue.rule === rule);
}

function tradeMachineIssueMessage(issue) {
  const teamPrefix = issue.teamCode ? `${issue.teamCode}: ` : '';
  return `${teamPrefix}${issue.message}`;
}

function tradeMachineRuleChecklist(issues, selectedCount) {
  const salaryIssues = tradeMachineIssuesForRule(issues, 'salary');
  const hardCapIssues = tradeMachineIssuesForRule(issues, 'hard_cap');
  const restrictedIssues = tradeMachineIssuesForRule(issues, 'restricted_pick');
  const manualIssues = tradeMachineIssuesForRule(issues, 'manual_review');
  const rosterIssues = tradeMachineIssuesForRule(issues, 'roster_count');
  return [
    {
      key: 'salary',
      label: 'Cuadre salarial básico',
      status: !selectedCount ? 'pending' : salaryIssues.length ? 'fail' : 'pass',
      messages: !selectedCount
        ? ['Añade activos para evaluar el cuadre salarial.']
        : salaryIssues.length
          ? salaryIssues.map(tradeMachineIssueMessage)
          : ['El cuadre salarial básico pasa para todos los equipos seleccionados.'],
    },
    {
      key: 'hard_cap',
      label: 'Límite duro',
      status: hardCapIssues.length ? 'fail' : 'pass',
      messages: hardCapIssues.length
        ? hardCapIssues.map(tradeMachineIssueMessage)
        : ['No se detecta conflicto de límite duro en el 1er/2do apron.'],
    },
    {
      key: 'restricted_pick',
      label: 'Ronda restringida',
      status: restrictedIssues.length ? 'fail' : 'pass',
      messages: restrictedIssues.length
        ? restrictedIssues.map(tradeMachineIssueMessage)
        : ['No hay ninguna ronda restringida seleccionada.'],
    },
    {
      key: 'manual_review',
      label: 'Stepien/revisión manual',
      status: manualIssues.length ? 'warning' : 'pass',
      messages: manualIssues.length
        ? manualIssues.map(tradeMachineIssueMessage)
        : ['No se activa revisión por protecciones, condiciones, Stepien ni agregación/aprons.'],
    },
    {
      key: 'roster_count',
      label: 'Tamaño de plantilla',
      status: rosterIssues.some((issue) => issue.severity === 'illegal')
        ? 'fail'
        : rosterIssues.some((issue) => issue.severity === 'warning')
          ? 'warning'
          : 'pass',
      messages: rosterIssues.length
        ? rosterIssues.map(tradeMachineIssueMessage)
        : ['El tamaño de plantilla queda dentro de los límites configurados.'],
    },
  ];
}

function tradeMachineRosterCountIssues(code, flow) {
  const limits = rosterLimits();
  const issues = [];
  const standard = Number(flow.postRosterStandard || 0);
  const twoWay = Number(flow.postRosterTwoWay || 0);
  if (standard > limits.standardOffseasonMax) {
    issues.push({
      severity: 'illegal',
      rule: 'roster_count',
      teamCode: code,
      message: `Quedaría con ${standard} contratos estándar; el máximo configurado para offseason es ${limits.standardOffseasonMax}.`,
    });
  } else if (standard > limits.standardMax) {
    issues.push({
      severity: 'warning',
      rule: 'roster_count',
      teamCode: code,
      message: `Quedaría con ${standard} contratos estándar. Solo sería válido en offseason; durante la temporada el máximo es ${limits.standardMax}.`,
    });
  }
  if (standard < limits.standardMin) {
    issues.push({
      severity: 'warning',
      rule: 'roster_count',
      teamCode: code,
      message: `Quedaría con ${standard} contratos estándar, por debajo del mínimo configurado (${limits.standardMin}).`,
    });
  }
  if (twoWay > limits.twoWayMax) {
    issues.push({
      severity: 'illegal',
      rule: 'roster_count',
      teamCode: code,
      message: `Quedaría con ${twoWay} contratos two-way; el máximo configurado es ${limits.twoWayMax}.`,
    });
  }
  if (twoWay < limits.twoWayMin) {
    issues.push({
      severity: 'warning',
      rule: 'roster_count',
      teamCode: code,
      message: `Quedaría con ${twoWay} contratos two-way, por debajo del mínimo configurado (${limits.twoWayMin}).`,
    });
  }
  return issues;
}

function validateTradeMachine() {
  pruneTradeMachineSelections();
  const teams = state.tradeMachine.selectedTeams || [];
  const flows = tradeMachineFlows();
  const issues = [];
  if (teams.length < TRADE_MACHINE_MIN_TEAMS) {
    issues.push({ severity: 'illegal', rule: 'setup', message: 'Selecciona al menos dos equipos.' });
  }
  if (teams.length > TRADE_MACHINE_MAX_TEAMS) {
    issues.push({ severity: 'illegal', rule: 'setup', message: 'Selecciona seis equipos o menos.' });
  }
  const selectedEntries = Object.entries(state.tradeMachine.selections || {});
  if (!selectedEntries.length) {
    issues.push({ severity: 'warning', rule: 'setup', message: 'Selecciona al menos un activo.' });
  }
  selectedEntries.forEach(([key, selection]) => {
    const meta = tradeMachineAssetMeta(key);
    if (!meta) {
      issues.push({ severity: 'illegal', rule: 'setup', message: 'Un activo seleccionado ya no está disponible.' });
      return;
    }
    const pickAction = meta.type === 'pick' ? tradeMachinePickAction(selection.pickAction) : null;
    if (!selection.toTeam || selection.toTeam === selection.fromTeam) {
      issues.push({ severity: 'illegal', rule: 'setup', teamCode: selection.fromTeam, message: `${meta.label} necesita un equipo de destino.` });
    }
    if (meta.restricted) {
      issues.push({ severity: 'illegal', rule: 'restricted_pick', teamCode: selection.fromTeam, message: `${meta.label} está restringida y no se puede mover.` });
    }
    if (meta.conditional || meta.protected) {
      issues.push({ severity: 'warning', rule: 'manual_review', teamCode: selection.fromTeam, message: `${meta.label} necesita revisión manual por condiciones/protecciones.` });
    }
    if (meta.type === 'pick' && pickAction === TRADE_PICK_ACTION_SWAP) {
      issues.push({ severity: 'warning', rule: 'manual_review', teamCode: selection.fromTeam, message: `${meta.label}: derecho de swap seleccionado; revisa protecciones, prioridad y equipo que acabaría eligiendo.` });
    } else if (meta.type === 'pick' && meta.round === '1st') {
      issues.push({ severity: 'warning', rule: 'manual_review', teamCode: selection.fromTeam, message: `${meta.label} necesita revisión de la regla Stepien.` });
    }
  });
  teams.forEach((code) => {
    const flow = flows[code];
    if (!flow) return;
    if (!flow.incomingAssets.length && !flow.outgoingAssets.length) {
      issues.push({ severity: 'warning', rule: 'setup', teamCode: code, message: 'Seleccionado, pero todavía no participa.' });
    }
    const salaryIssue = tradeMachineSalaryMatchIssue(code, flow);
    if (salaryIssue) issues.push(salaryIssue);
    tradeMachineRosterCountIssues(code, flow).forEach((issue) => issues.push(issue));
    const secondApron = Number(state.settings.second_apron || 0);
    const beforeApronAccount = Number(flow.beforeApronAccount ?? flow.beforeCap ?? 0);
    const postApronAccount = Number(flow.postApronAccount ?? flow.postCap ?? 0);
    if (
      secondApron > 0
      && (flow.incomingAssets.length || flow.outgoingAssets.length)
      && (beforeApronAccount >= secondApron || postApronAccount >= secondApron)
    ) {
      issues.push({ severity: 'warning', rule: 'manual_review', teamCode: code, message: 'Cerca/por encima del 2do apron; las restricciones de agregación y excepciones todavía no están completamente validadas.' });
    }
  });
  const hasIllegal = issues.some((issue) => issue.severity === 'illegal');
  const hasWarning = issues.some((issue) => issue.severity === 'warning');
  return {
    status: hasIllegal ? 'illegal' : hasWarning ? 'review' : 'legal',
    issues,
    checklist: tradeMachineRuleChecklist(issues, selectedEntries.length),
    flows,
  };
}

function tradeMachineAssetDetailHtml(detail, mobileDetail) {
  const desktop = String(detail || '').trim();
  const mobile = String(mobileDetail || desktop).trim();
  if (!desktop && !mobile) return '';
  if (!mobile || mobile === desktop) return `<span class="trade-machine-asset-detail">${escapeHtml(desktop || mobile)}</span>`;
  return `
    <span class="trade-machine-asset-detail">
      <span class="trade-machine-detail-desktop">${escapeHtml(desktop)}</span>
      <span class="trade-machine-detail-mobile">${escapeHtml(mobile)}</span>
    </span>
  `;
}

function tradeMachineAssetRowHtml({ key, type, label, detail, mobileDetail, salary, badges = '', disabled = false }) {
  const selected = tradeMachineSelectedAsset(key);
  const fromTeam = key.split(':')[1];
  const selectedTo = selected?.toTeam || tradeMachineDefaultRecipient(fromTeam);
  const selectedPickAction = tradeMachinePickAction(selected?.pickAction);
  const hasPickAction = type === 'pick' && Boolean(selected);
  const salaryHtml = salary > 0
    ? `<span class="trade-machine-asset-salary">${formatBalanceMoney(salary)}</span>`
    : '<span class="trade-machine-asset-salary trade-machine-asset-salary--empty" aria-hidden="true"></span>';
  const pickActionHtml = hasPickAction
    ? `
      <select class="trade-machine-pick-action-select" data-trade-pick-action="${key}" aria-label="Acción para ${escapeHtml(label)}">
        ${tradeMachinePickActionOptions(selectedPickAction)}
      </select>
    `
    : '';
  return `
    <div class="trade-machine-asset-row ${disabled ? 'is-disabled' : ''}">
      <label>
        <input type="checkbox" data-trade-asset-key="${key}" data-trade-asset-type="${type}" ${selected ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
        <span class="trade-machine-asset-main">
          <span class="trade-machine-asset-name">${escapeHtml(label)}</span>
          ${tradeMachineAssetDetailHtml(detail, mobileDetail)}
          ${badges ? `<span class="trade-machine-tags">${badges}</span>` : ''}
        </span>
      </label>
      <div class="trade-machine-asset-route trade-machine-asset-route--${type} ${hasPickAction ? 'has-pick-action' : ''}">
        ${type === 'pick' ? pickActionHtml : salaryHtml}
        <select class="trade-machine-recipient-select" data-trade-recipient="${key}" ${selected ? '' : 'disabled'} aria-label="Destino de ${escapeHtml(label)}">
          ${tradeMachineRecipientOptions(fromTeam, selectedTo)}
        </select>
      </div>
    </div>
  `;
}

function tradeMachinePlayerRowsHtml(data, code) {
  const season = tradeMachineSeasonStart();
  const players = sortedRows(data.players || [], { key: 'position', dir: 'asc' });
  if (!players.length) return '<div class="trade-machine-empty">Sin jugadores</div>';
  return players.map((player) => {
    const key = tradeMachineAssetKey('player', code, player.id);
    const detail = [player.position, player.bird_rights].filter(Boolean).join(' · ');
    const salary = salaryNumericValue(player, season);
    return tradeMachineAssetRowHtml({
      key,
      type: 'player',
      label: player.name || 'Jugador',
      detail,
      mobileDetail: [player.position, salary > 0 ? formatBalanceMoney(salary) : 'Sin salario'].filter(Boolean).join(' · '),
      salary,
    });
  }).join('');
}

function tradeMachinePickRowsHtml(data, code) {
  const minDraftYear = tradeMachineDraftYearStart();
  const picks = (data.assets || [])
    .filter((asset) => asset.asset_type === 'draft_pick')
    .filter((asset) => draftPickType(asset) !== 'sold')
    .filter((asset) => {
      const year = Number(asset.year);
      return !Number.isFinite(year) || year >= minDraftYear;
    })
    .sort((a, b) => {
      const yearA = Number(a.year || 0);
      const yearB = Number(b.year || 0);
      if (yearA !== yearB) return yearA - yearB;
      return draftPickRound(a).localeCompare(draftPickRound(b));
    });
  if (!picks.length) return '<div class="trade-machine-empty">Sin rondas traspasables</div>';
  return picks.map((pick) => {
    const key = tradeMachineAssetKey('pick', code, pick.id);
    const teams = draftPickType(pick) === 'conditional'
      ? parseDraftConditionalTeams(pick.draft_pick_conditional_teams).join(' / ')
      : '';
    const detail = teams || String(pick.detail || '').trim();
    return tradeMachineAssetRowHtml({
      key,
      type: 'pick',
      label: draftPickTradeLabel(pick, code),
      detail,
      badges: tradeMachinePickBadges(pick),
      disabled: draftPickIsRestricted(pick),
      salary: 0,
    });
  }).join('');
}

function tradeMachineRightsRowsHtml(data, code) {
  const rights = (data.assets || []).filter((asset) => asset.asset_type === 'player_right');
  if (!rights.length) return '<div class="trade-machine-empty">Sin derechos de jugadores</div>';
  return rights.map((right) => tradeMachineAssetRowHtml({
    key: tradeMachineAssetKey('right', code, right.id),
    type: 'right',
    label: right.label || 'Derecho de jugador',
    detail: right.detail || '',
    salary: 0,
  })).join('');
}

function tradeMachineLedgerHtml(flow) {
  const net = flow.incomingSalary - flow.outgoingSalary;
  return `
    <div class="trade-machine-ledger">
      <div><span>Recibe</span><strong>${formatBalanceMoney(flow.incomingSalary)}</strong></div>
      <div><span>Envía</span><strong>${formatBalanceMoney(flow.outgoingSalary)}</strong></div>
      <div><span>Neto</span><strong class="${net > 0 ? 'is-negative' : net < 0 ? 'is-positive' : ''}">${formatBalanceMoney(net)}</strong></div>
      <div><span>CAP después</span><strong>${formatBalanceMoney(flow.postCap)}</strong></div>
    </div>
  `;
}

function tradeMachineRosterHtml(flow) {
  const standardStatus = rosterCountStatus('standard', Number(flow.postRosterStandard || 0));
  const twoWayStatus = rosterCountStatus('twoWay', Number(flow.postRosterTwoWay || 0));
  return `
    <div class="trade-machine-roster-counts" aria-label="Tamaño de plantilla después del traspaso">
      <span class="trade-machine-roster-count trade-machine-roster-count--${standardStatus.key}">
        <small>Estándar</small>
        <strong>${flow.beforeRosterStandard} → ${flow.postRosterStandard}</strong>
        <em>${escapeHtml(standardStatus.label)}</em>
      </span>
      <span class="trade-machine-roster-count trade-machine-roster-count--${twoWayStatus.key}">
        <small>Two-way</small>
        <strong>${flow.beforeRosterTwoWay} → ${flow.postRosterTwoWay}</strong>
        <em>${escapeHtml(twoWayStatus.label)}</em>
      </span>
    </div>
  `;
}

function tradeMachinePreviewChipHtml(asset, direction) {
  const partner = direction === 'incoming' ? asset.fromTeam : asset.toTeam;
  const partnerLabel = partner ? `${direction === 'incoming' ? 'desde' : 'a'} ${partner}` : '';
  const salaryLabel = asset.salary > 0 ? formatBalanceMoney(asset.salary) : tradeMachineAssetTypeLabel(asset.type);
  return `
    <span class="trade-machine-preview-chip">
      <span class="trade-machine-preview-chip-main">
        <strong>${escapeHtml(asset.label)}</strong>
        <small>${escapeHtml([partnerLabel, salaryLabel].filter(Boolean).join(' · '))}</small>
      </span>
      <button type="button" data-trade-remove-asset="${asset.key}" aria-label="Quitar ${escapeHtml(asset.label)}">&times;</button>
    </span>
  `;
}

function tradeMachinePreviewListHtml(assets, direction) {
  if (!assets.length) return '<div class="trade-machine-preview-empty">Sin activos</div>';
  return `
    <div class="trade-machine-preview-chips">
      ${assets.map((asset) => tradeMachinePreviewChipHtml(asset, direction)).join('')}
    </div>
  `;
}

function tradeMachineTeamPreviewHtml(flow) {
  const hasAssets = flow.incomingAssets.length || flow.outgoingAssets.length;
  return `
    <div class="trade-machine-team-preview ${hasAssets ? '' : 'is-empty'}" aria-label="Vista previa del traspaso">
      <section>
        <div class="trade-machine-preview-head">
          <span>Salen</span>
        </div>
        ${tradeMachinePreviewListHtml(flow.outgoingAssets, 'outgoing')}
      </section>
      <section>
        <div class="trade-machine-preview-head">
          <span>Entran</span>
        </div>
        ${tradeMachinePreviewListHtml(flow.incomingAssets, 'incoming')}
      </section>
    </div>
  `;
}

function tradeMachineAssetTypeLabel(type) {
  if (type === 'player') return 'Jugador';
  if (type === 'pick') return 'Ronda';
  if (type === 'swap_right') return 'Derecho swap';
  if (type === 'right') return 'Derecho';
  return 'Activo';
}

function tradeMachineAssetSummaryHtml(asset, direction) {
  const partner = direction === 'incoming' ? asset.fromTeam : asset.toTeam;
  const typeClass = `trade-machine-summary-asset--${asset.type || 'asset'}`;
  const partnerLogo = tradeMachineSummaryLogoHtml(partner);
  const salaryHtml = asset.salary > 0 ? `<span class="trade-machine-summary-asset-money">${formatBalanceMoney(asset.salary)}</span>` : '';
  return `
    <li class="trade-machine-summary-asset ${typeClass}">
      <div class="trade-machine-summary-asset-head">
        <strong>${escapeHtml(asset.label)}</strong>
        ${partnerLogo}
      </div>
      ${asset.detail ? `<small>${escapeHtml(asset.detail)}</small>` : ''}
      ${salaryHtml}
    </li>
  `;
}

function tradeMachineAssetSummaryListHtml(assets, direction) {
  if (!assets.length) return '<div class="trade-machine-summary-empty">Nada seleccionado</div>';
  return `<ul>${assets.map((asset) => tradeMachineAssetSummaryHtml(asset, direction)).join('')}</ul>`;
}

function tradeMachineBalanceClass(value) {
  const amount = Number(value || 0);
  if (amount < 0) return 'is-negative';
  if (amount > 0) return 'is-positive';
  return '';
}

function tradeMachineSummaryCountHtml(label, incoming, outgoing, incomingLabel = 'recibidas', outgoingLabel = 'enviadas') {
  return `
    <span class="trade-machine-summary-metric">
      <strong>${escapeHtml(label)}</strong>
      <span class="trade-machine-summary-flow trade-machine-summary-flow--in" title="${escapeHtml(incomingLabel)}" aria-label="${escapeHtml(`${label} ${incomingLabel}`)}">↙ ${incoming}</span>
      <span class="trade-machine-summary-flow trade-machine-summary-flow--out" title="${escapeHtml(outgoingLabel)}" aria-label="${escapeHtml(`${label} ${outgoingLabel}`)}">↗ ${outgoing}</span>
    </span>
  `;
}

function tradeMachineBalanceRowsHtml(flow) {
  const before = flow.beforeBalances || tradeMachineBalanceSnapshot(flow.beforeCap);
  const after = flow.afterBalances || tradeMachineBalanceSnapshot(flow.postCap);
  return before.map((item, idx) => {
    const afterItem = after[idx] || item;
    return `
      <tr>
        <th>${escapeHtml(item.label)}</th>
        <td class="${tradeMachineBalanceClass(item.value)}">${formatBalanceMoney(item.value)}</td>
        <td class="${tradeMachineBalanceClass(afterItem.value)}">${formatBalanceMoney(afterItem.value)}</td>
      </tr>
    `;
  }).join('');
}

function tradeMachineTeamSummaryHtml(code, flow) {
  const net = flow.incomingSalary - flow.outgoingSalary;
  const incomingPicks = flow.incomingAssets.filter((asset) => asset.type === 'pick').length;
  const incomingSwapRights = flow.incomingAssets.filter((asset) => asset.type === 'swap_right').length;
  const incomingRights = flow.incomingAssets.filter((asset) => asset.type === 'right').length;
  const outgoingPicks = flow.outgoingAssets.filter((asset) => asset.type === 'pick').length;
  const outgoingSwapRights = flow.outgoingAssets.filter((asset) => asset.type === 'swap_right').length;
  const outgoingRights = flow.outgoingAssets.filter((asset) => asset.type === 'right').length;
  const countMetrics = [
    tradeMachineSummaryCountHtml('Rondas', incomingPicks, outgoingPicks),
    (incomingSwapRights || outgoingSwapRights) ? tradeMachineSummaryCountHtml('Swaps', incomingSwapRights, outgoingSwapRights, 'recibidos', 'enviados') : '',
    tradeMachineSummaryCountHtml('Derechos', incomingRights, outgoingRights, 'recibidos', 'enviados'),
  ].filter(Boolean).join('');
  return `
    <article class="trade-machine-summary-team">
      <div class="trade-machine-summary-team-head">
        <div class="trade-machine-summary-team-title">
          ${tradeMachineSummaryLogoHtml(code, 'trade-machine-summary-team-logo')}
          <div>
            <strong>${escapeHtml(code)}</strong>
            <span>${flow.incomingAssets.length} entran · ${flow.outgoingAssets.length} salen</span>
          </div>
        </div>
        <div class="trade-machine-summary-counts">
          ${countMetrics}
        </div>
      </div>
      <div class="trade-machine-summary-assets">
        <section>
          <h4>Recibe</h4>
          ${tradeMachineAssetSummaryListHtml(flow.incomingAssets, 'incoming')}
        </section>
        <section>
          <h4>Envía</h4>
          ${tradeMachineAssetSummaryListHtml(flow.outgoingAssets, 'outgoing')}
        </section>
      </div>
      <div class="trade-machine-summary-money">
        <span>Salario recibido <strong>${formatBalanceMoney(flow.incomingSalary)}</strong></span>
        <span>Salario enviado <strong>${formatBalanceMoney(flow.outgoingSalary)}</strong></span>
        <span>Neto <strong class="${net > 0 ? 'is-negative' : net < 0 ? 'is-positive' : ''}">${formatBalanceMoney(net)}</strong></span>
      </div>
      <table class="trade-machine-balance-table">
        <thead>
          <tr>
            <th>Balance</th>
            <th>Antes</th>
            <th>Después</th>
          </tr>
        </thead>
        <tbody>${tradeMachineBalanceRowsHtml(flow)}</tbody>
      </table>
    </article>
  `;
}

function tradeMachineSetupNotesHtml(issues) {
  const setupIssues = (issues || []).filter((issue) => issue.rule === 'setup');
  if (!setupIssues.length) return '';
  return `
    <div class="trade-machine-setup-notes">
      ${setupIssues.map((issue) => `
        <div class="trade-machine-setup-note trade-machine-setup-note--${issue.severity}">
          ${issue.teamCode ? `<strong>${escapeHtml(issue.teamCode)}</strong>` : ''}
          <span>${escapeHtml(issue.message)}</span>
        </div>
      `).join('')}
    </div>
  `;
}

function tradeMachineChecklistHtml(checklist) {
  const statusLabels = {
    pass: 'Correcto',
    fail: 'Error',
    warning: 'Aviso',
    pending: 'Pendiente',
  };
  return `
    <section class="trade-machine-checklist" aria-label="Checklist de validación del traspaso">
      <div class="trade-machine-panel-title">
        <h3>Checklist de reglas</h3>
      </div>
      <div class="trade-machine-checklist-grid">
        ${(checklist || []).map((item) => `
          <article class="trade-machine-check trade-machine-check--${item.status}">
            <div class="trade-machine-check-head">
              <strong>${escapeHtml(item.label)}</strong>
              <span>${statusLabels[item.status] || item.status}</span>
            </div>
            <ul>
              ${(item.messages || []).map((message) => `<li>${escapeHtml(message)}</li>`).join('')}
            </ul>
          </article>
        `).join('')}
      </div>
    </section>
  `;
}

function renderTradeMachineTeamCard(code, index, flow) {
  const data = state.tradeMachine.teamDataByCode[code];
  const canRemove = (state.tradeMachine.selectedTeams || []).length > TRADE_MACHINE_MIN_TEAMS;
  if (!data) {
    return `
      <article class="trade-machine-team-card">
        <div class="trade-machine-team-top">
          <div class="trade-machine-team-select">
            <span class="trade-machine-team-kicker">
              Equipo ${index + 1}
              ${tradeMachineTeamLogoHtml(code)}
            </span>
            ${tradeMachineTeamSelectHtml(code, index)}
          </div>
          ${canRemove ? `<button type="button" class="trade-machine-remove" data-trade-remove-team="${index}" aria-label="Quitar equipo">Quitar</button>` : ''}
        </div>
        <div class="trade-machine-empty">Cargando equipo...</div>
      </article>
    `;
  }
  return `
    <article class="trade-machine-team-card">
      <div class="trade-machine-team-top">
        <div class="trade-machine-team-select">
          <span class="trade-machine-team-kicker">
            Equipo ${index + 1}
            ${tradeMachineTeamLogoHtml(code)}
          </span>
          ${tradeMachineTeamSelectHtml(code, index)}
        </div>
        ${canRemove ? `<button type="button" class="trade-machine-remove" data-trade-remove-team="${index}" aria-label="Quitar ${code}">Quitar</button>` : ''}
      </div>
      ${tradeMachineLedgerHtml(flow)}
      ${tradeMachineRosterHtml(flow)}
      ${tradeMachineTeamPreviewHtml(flow)}
      <div class="trade-machine-assets">
        <section>
          <h3>Plantilla (${(data.players || []).length})</h3>
          <div class="trade-machine-asset-list">${tradeMachinePlayerRowsHtml(data, code)}</div>
        </section>
        <section>
          <h3>Rondas del draft</h3>
          <div class="trade-machine-asset-list">${tradeMachinePickRowsHtml(data, code)}</div>
        </section>
        <section>
          <h3>Derechos de jugadores</h3>
          <div class="trade-machine-asset-list">${tradeMachineRightsRowsHtml(data, code)}</div>
        </section>
      </div>
    </article>
  `;
}

function renderTradeMachineResults(result) {
  const resultEl = document.getElementById('tradeMachineResults');
  if (!resultEl) return;
  const statusLabel = result.status === 'legal' ? 'Válido' : result.status === 'illegal' ? 'No válido' : 'Requiere revisión';
  const selectedCount = Object.keys(state.tradeMachine.selections || {}).length;
  const assetLabel = selectedCount === 1 ? 'activo seleccionado' : 'activos seleccionados';
  const summaryHtml = (state.tradeMachine.selectedTeams || []).map((code) => {
    const flow = result.flows[code] || tradeMachineFlowSkeleton(code);
    return tradeMachineTeamSummaryHtml(code, flow);
  }).join('');
  resultEl.innerHTML = `
    <div class="trade-machine-result-head trade-machine-result-head--${result.status}">
      <span>${statusLabel}</span>
      <strong>${selectedCount} ${assetLabel}</strong>
    </div>
    <section class="trade-machine-summary-panel" aria-label="Resumen del traspaso">
      <div class="trade-machine-panel-title">
        <h3>Resumen del traspaso</h3>
        <span>${seasonLabel(tradeMachineSeasonStart())}</span>
      </div>
      <div class="trade-machine-summary-grid">${summaryHtml}</div>
    </section>
    ${tradeMachineChecklistHtml(result.checklist)}
    ${tradeMachineSetupNotesHtml(result.issues)}
  `;
}

function renderTradeMachine() {
  renderTradeMachineSeasonControl();
  const grid = document.getElementById('tradeMachineTeams');
  const status = document.getElementById('tradeMachineStatus');
  const addBtn = document.getElementById('tradeMachineAddTeamBtn');
  if (!grid) return;
  const codes = state.tradeMachine.selectedTeams || [];
  const result = validateTradeMachine();
  if (status) status.textContent = `${seasonLabel(tradeMachineSeasonStart())} · ${codes.length} equipos`;
  if (addBtn) addBtn.disabled = codes.length >= TRADE_MACHINE_MAX_TEAMS;
  grid.innerHTML = codes
    .map((code, index) => renderTradeMachineTeamCard(code, index, result.flows[code] || tradeMachineFlowSkeleton(code)))
    .join('');
  renderTradeMachineResults(result);
}

async function loadTradeMachine(seedCodes = []) {
  const seed = seedCodes.length
    ? seedCodes
    : (state.tradeMachine.selectedTeams.length ? state.tradeMachine.selectedTeams : [state.teamCode].filter(Boolean));
  state.tradeMachine.selectedTeams = defaultTradeMachineTeams(seed);
  state.tradeMachine.seasonStart = state.tradeMachine.seasonStart || currentSeasonStart();
  state.teamCode = null;
  state.teamData = null;
  setTeamInUrl(null);
  applyTeamTheme('');
  setPageHeading('Máquina de traspasos', '');
  renderCapStatusPills({});
  setViewMode('trade-machine');
  renderTeamStrip();
  renderMobileTeamGrid();
  renderTradeMachine();
  await ensureTradeMachineTeamData(state.tradeMachine.selectedTeams);
  pruneTradeMachineSelections();
  renderTradeMachine();
}

async function updateTradeMachineTeam(index, code) {
  const nextCode = String(code || '').trim().toUpperCase();
  if (!tradeMachineValidTeamCodes().has(nextCode)) return;
  const selected = [...state.tradeMachine.selectedTeams];
  if (selected.some((item, idx) => idx !== index && item === nextCode)) return;
  const oldCode = selected[index];
  selected[index] = nextCode;
  state.tradeMachine.selectedTeams = selected;
  Object.entries(state.tradeMachine.selections).forEach(([key, selection]) => {
    if (selection.fromTeam === oldCode || selection.toTeam === oldCode) delete state.tradeMachine.selections[key];
  });
  renderTradeMachine();
  await ensureTradeMachineTeamData([nextCode]);
  renderTradeMachine();
}

async function addTradeMachineTeam() {
  if (state.tradeMachine.selectedTeams.length >= TRADE_MACHINE_MAX_TEAMS) return;
  const next = (state.teams || []).find((team) => !state.tradeMachine.selectedTeams.includes(team.code));
  if (!next) return;
  state.tradeMachine.selectedTeams.push(next.code);
  renderTradeMachine();
  await ensureTradeMachineTeamData([next.code]);
  renderTradeMachine();
}

function removeTradeMachineTeam(index) {
  if (state.tradeMachine.selectedTeams.length <= TRADE_MACHINE_MIN_TEAMS) return;
  const removed = state.tradeMachine.selectedTeams[index];
  state.tradeMachine.selectedTeams.splice(index, 1);
  Object.entries(state.tradeMachine.selections).forEach(([key, selection]) => {
    if (selection.fromTeam === removed || selection.toTeam === removed) delete state.tradeMachine.selections[key];
  });
  pruneTradeMachineSelections();
  renderTradeMachine();
}

function resetTradeMachine() {
  const seed = [state.tradeMachine.selectedTeams[0] || state.teamCode].filter(Boolean);
  state.tradeMachine.selectedTeams = defaultTradeMachineTeams(seed);
  state.tradeMachine.selections = {};
  state.tradeMachine.seasonStart = currentSeasonStart();
  void ensureTradeMachineTeamData(state.tradeMachine.selectedTeams).then(() => renderTradeMachine());
  renderTradeMachine();
}

function setupTradeMachineControls() {
  const desktopBtn = document.getElementById('tradeMachineHomeBtn');
  const addBtn = document.getElementById('tradeMachineAddTeamBtn');
  const resetBtn = document.getElementById('tradeMachineResetBtn');
  const seasonSelect = document.getElementById('tradeMachineSeasonSelect');
  const grid = document.getElementById('tradeMachineTeams');
  if (desktopBtn) desktopBtn.addEventListener('click', async () => loadTradeMachine());
  if (addBtn) addBtn.addEventListener('click', async () => addTradeMachineTeam());
  if (resetBtn) resetBtn.addEventListener('click', () => resetTradeMachine());
  if (seasonSelect) {
    seasonSelect.addEventListener('change', () => {
      state.tradeMachine.seasonStart = Number(seasonSelect.value || currentSeasonStart());
      renderTradeMachine();
    });
  }
  if (grid) {
    grid.addEventListener('change', async (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.matches('[data-trade-team-select]')) {
        await updateTradeMachineTeam(Number(target.dataset.tradeTeamSelect), target.value);
        return;
      }
      if (target.matches('[data-trade-asset-key]')) {
        const key = target.dataset.tradeAssetKey;
        if (!key) return;
        const meta = tradeMachineAssetMeta(key);
        if (!meta) return;
        if (target.checked) {
          state.tradeMachine.selections[key] = {
            key,
            type: meta.type,
            id: meta.id,
            fromTeam: meta.fromTeam,
            toTeam: tradeMachineDefaultRecipient(meta.fromTeam),
            pickAction: meta.type === 'pick' ? TRADE_PICK_ACTION_SEND : undefined,
          };
        } else {
          delete state.tradeMachine.selections[key];
        }
        renderTradeMachine();
        return;
      }
      if (target.matches('[data-trade-recipient]')) {
        const key = target.dataset.tradeRecipient;
        if (key && state.tradeMachine.selections[key]) {
          state.tradeMachine.selections[key].toTeam = target.value;
          renderTradeMachine();
        }
        return;
      }
      if (target.matches('[data-trade-pick-action]')) {
        const key = target.dataset.tradePickAction;
        if (key && state.tradeMachine.selections[key]) {
          state.tradeMachine.selections[key].pickAction = tradeMachinePickAction(target.value);
          renderTradeMachine();
        }
      }
    });
    grid.addEventListener('click', (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      const removeAssetBtn = target.closest('[data-trade-remove-asset]');
      if (removeAssetBtn) {
        const key = removeAssetBtn.dataset.tradeRemoveAsset;
        if (key) {
          delete state.tradeMachine.selections[key];
          renderTradeMachine();
        }
        return;
      }
      const removeBtn = target.closest('[data-trade-remove-team]');
      if (!removeBtn) return;
      removeTradeMachineTeam(Number(removeBtn.dataset.tradeRemoveTeam));
    });
  }
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
    if (isTwoWayPlayer(row)) return POSITION_ORDER.TW;
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

function rosterPositionKey(player) {
  if (isTwoWayPlayer(player)) return 'TW';
  const raw = String(player?.position || '').trim().toUpperCase();
  const primary = raw.split(/[\/,\s-]+/).find(Boolean) || '';
  return POSITION_ORDER[primary] ? primary : (primary || 'NA');
}

function rosterPositionLabel(positionKey) {
  const labels = {
    PG: 'Point Guards',
    SG: 'Shooting Guards',
    SF: 'Small Forwards',
    PF: 'Power Forwards',
    C: 'Centers',
    TW: 'Two Ways',
    NA: 'Sin posición',
  };
  return labels[positionKey] || positionKey;
}

function rosterPositionCounts(rows) {
  return rows.reduce((counts, player) => {
    const key = rosterPositionKey(player);
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function shouldRenderRosterPositionGroups() {
  return state.sort.players?.key === 'position';
}

function appendRosterPositionSeparator(tbody, positionKey, count, colspan) {
  const tr = document.createElement('tr');
  tr.className = 'roster-position-row';
  tr.innerHTML = `
    <td colspan="${colspan}">
      <span class="roster-position-code">${escapeHtml(positionKey === 'NA' ? '-' : positionKey)}</span>
      <span class="roster-position-name">${escapeHtml(rosterPositionLabel(positionKey))}</span>
      <span class="roster-position-count">${count} ${count === 1 ? 'player' : 'players'}</span>
    </td>
  `;
  tbody.appendChild(tr);
}

function updateSortIndicators(tableId, sortCfg) {
  const headers = document.querySelectorAll(`#${tableId} thead th[data-sort]`);
  let matched = false;
  headers.forEach((th) => {
    const key = th.dataset.sort;
    const isMatch = key === sortCfg.key;
    if (isMatch) matched = true;
    const arrow = isMatch ? (sortCfg.dir === 'asc' ? ' ▲' : ' ▼') : '';
    const label = th.dataset.label || th.textContent.replace(/[ ▲▼]/g, '');
    if (tableId === 'trackerTable' && key === 'roster_standard_count') {
      th.innerHTML = trackerRosterHeaderHtml('standard', label, arrow);
    } else if (tableId === 'trackerTable' && key === 'roster_two_way_count') {
      th.innerHTML = trackerRosterHeaderHtml('twoWay', label, arrow);
    } else {
      th.innerHTML = `<span class="th-main">${label}${arrow}</span>`;
    }
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
  updateSortIndicators('exceptionsTable', state.sort.exceptions);
  updateSortIndicators('playerRightsTable', state.sort.player_rights);
  updateSortIndicators('freeAgentsTable', state.sort.free_agents);

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

  document.querySelectorAll('#freeAgentsTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const curr = state.sort.free_agents;
      state.sort.free_agents = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      renderFreeAgents();
      updateSortIndicators('freeAgentsTable', state.sort.free_agents);
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
    syncMobileAuthControls(auth);
    return;
  }

  const userName = auth.user?.name || auth.user?.email || 'Signed In';
  badge.textContent = `${userName} (${auth.role})`;
  loginLink.hidden = true;
  adminLink.hidden = auth.role !== 'admin';
  logoutBtn.hidden = false;
  syncMobileAuthControls(auth);
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

function ensurePlayerMetaModal() {
  let backdrop = document.getElementById('playerMetaBackdrop');
  if (backdrop) return backdrop;
  backdrop = document.createElement('div');
  backdrop.id = 'playerMetaBackdrop';
  backdrop.className = 'player-meta-backdrop section-hidden';
  backdrop.setAttribute('aria-hidden', 'true');
  backdrop.innerHTML = `
    <div class="player-meta-card" role="dialog" aria-modal="true" aria-label="Player info">
      <div class="player-meta-head">
        <strong id="playerMetaTitle">Player info</strong>
        <button id="playerMetaCloseBtn" type="button" class="player-meta-close-btn" aria-label="Close">✕</button>
      </div>
      <div id="playerMetaContent" class="player-meta-list"></div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const close = () => {
    backdrop.classList.add('section-hidden');
    backdrop.setAttribute('aria-hidden', 'true');
  };
  const closeBtn = backdrop.querySelector('#playerMetaCloseBtn');
  if (closeBtn) closeBtn.addEventListener('click', close);
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });
  return backdrop;
}

function openPlayerMetaModal(playerName, meta) {
  const backdrop = ensurePlayerMetaModal();
  const titleEl = document.getElementById('playerMetaTitle');
  const contentEl = document.getElementById('playerMetaContent');
  if (!titleEl || !contentEl) return;

  const pos = String(meta.position || '').trim() || 'N/A';
  const rating = String(meta.rating || '').trim() || 'N/A';
  const contract = String(meta.contract || '').trim() || 'N/A';
  const years = String(meta.years || '').trim() || 'N/A';
  const contractCls = contract === 'N/A' ? '' : typeClass(contract);

  titleEl.textContent = playerName || 'Player info';
  contentEl.innerHTML = `
    <div class="player-meta-row"><span class="player-meta-label">Position</span><span class="pos-pill">${escapeHtml(pos)}</span></div>
    <div class="player-meta-row"><span class="player-meta-label">Rating</span><span class="meta-pill">${escapeHtml(rating)}</span></div>
    <div class="player-meta-row"><span class="player-meta-label">Tipo</span><span class="${contract === 'N/A' ? 'meta-pill' : `type-pill ${contractCls}`}">${escapeHtml(contract)}</span></div>
    <div class="player-meta-row"><span class="player-meta-label">Years</span><span class="meta-pill">${escapeHtml(years)}</span></div>
  `;
  backdrop.classList.remove('section-hidden');
  backdrop.setAttribute('aria-hidden', 'false');
}

function syncMobileAuthControls(auth) {
  const mobileAdminLink = document.getElementById('mobileAdminLink');
  const mobileLoginLink = document.getElementById('mobileLoginLink');
  const mobileLogoutBtn = document.getElementById('mobileLogoutBtn');
  if (!mobileAdminLink || !mobileLoginLink || !mobileLogoutBtn) return;
  if (!auth || !auth.authenticated) {
    mobileAdminLink.hidden = false;
    mobileLoginLink.hidden = false;
    mobileLogoutBtn.hidden = true;
    return;
  }
  mobileAdminLink.hidden = auth.role !== 'admin';
  mobileLoginLink.hidden = true;
  mobileLogoutBtn.hidden = false;
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

function renderMobileTeamGrid() {
  const grid = document.getElementById('mobileTeamGrid');
  if (!grid) return;
  grid.innerHTML = '';
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
      closeMobileSidebar();
      if (t.code === state.teamCode) return;
      await loadTeam(t.code);
    });
    btn.appendChild(fallback);
    btn.appendChild(img);
    grid.appendChild(btn);
  });
}

function setMobileOverlayVisible(backdropId, isVisible) {
  const backdrop = document.getElementById(backdropId);
  if (!backdrop) return;
  backdrop.classList.toggle('section-hidden', !isVisible);
  backdrop.setAttribute('aria-hidden', isVisible ? 'false' : 'true');
}

function openMobileSidebar() {
  state.ui.mobileSidebarOpen = true;
  setMobileOverlayVisible('mobileSidebarBackdrop', true);
}

function closeMobileSidebar() {
  state.ui.mobileSidebarOpen = false;
  setMobileOverlayVisible('mobileSidebarBackdrop', false);
}

function formatBalanceMoney(n) {
  const value = Math.round(Number(n || 0));
  const sign = value < 0 ? '-' : '';
  return `$${sign}${formatDots(Math.abs(value))}`;
}

function balanceNoticeItems(summary) {
  const s = summary || {};
  const notices = [];
  const hardCap = String(s.apron_hard_cap || '').trim().toLowerCase();
  if (hardCap === 'first') notices.push('Capped at 1st apron');
  if (hardCap === 'second') notices.push('Capped at 2nd apron');
  return notices;
}

function buildBalanceCard(label, value, isWarning = false) {
  const numeric = Number(value || 0);
  const signClass = numeric < 0 ? ' is-negative' : numeric > 0 ? ' is-positive' : '';
  const warningClass = isWarning || numeric < 0 ? ' is-warning' : '';
  return `
    <div class="team-balance-card${warningClass}${signClass}">
      <div class="team-balance-label">${escapeHtml(label)}</div>
      <div class="team-balance-value">${formatBalanceMoney(value)}</div>
    </div>
  `;
}

function buildBalancePanelHtml(summary) {
  const s = summary || {};
  const notices = balanceNoticeItems(s);
  const noticesHtml = notices.length
    ? `<div class="team-balance-notices">${notices.map((txt) => `<div class="team-balance-notice">${escapeHtml(txt)}</div>`).join('')}</div>`
    : '';
  return `
    <div class="team-balance-panel" aria-label="Team balances">
      <div class="team-balance-grid">
        ${buildBalanceCard('CAP SPACE', s.room_to_cap)}
        ${buildBalanceCard('TAX SPACE', s.room_to_luxury)}
        ${buildBalanceCard('1ST APRON SPACE', s.room_to_first_apron, Number(s.room_to_first_apron) < 0)}
        ${buildBalanceCard('2ND APRON SPACE', s.room_to_second_apron, Number(s.room_to_second_apron) < 0)}
      </div>
      ${noticesHtml}
    </div>
  `;
}

function usagePercent(available, limit) {
  const availableNum = Math.max(0, Number(available || 0));
  const limitNum = Math.max(0, Number(limit || 0));
  if (!limitNum) return { raw: 0, clamped: 0 };
  const raw = (availableNum / limitNum) * 100;
  return { raw, clamped: Math.max(0, Math.min(100, raw)) };
}

function gaugeColor(percent) {
  const clamped = Math.max(0, Math.min(100, Number(percent || 0)));
  const hue = Math.round((clamped / 100) * 145);
  return `hsl(${hue} 70% 34%)`;
}

function availableAmount(used, limit) {
  const limitNum = Math.max(0, Number(limit || 0));
  const available = limitNum - Math.max(0, Number(used || 0));
  return Math.max(0, Math.min(limitNum, available));
}

function availableMoves(moveSummary, bucket, limit) {
  const m = moveSummary || {};
  const used = Number(m[`used_${bucket}`]);
  if (Number.isFinite(used)) return availableAmount(used, limit);
  return Math.max(0, Math.min(Number(limit || 0), Number(m[`remaining_${bucket}`] || 0)));
}

function buildUsageGaugeCard({ label, available, limit, valueText, limitText, unitText = 'Available', tone = 'cash', detailHtml = '' }) {
  const pct = usagePercent(available, limit);
  const displayPct = Math.round(pct.raw);
  const isOver = pct.raw > 100;
  const color = gaugeColor(pct.clamped);
  const progressPath = pct.clamped > 0
    ? `<path class="usage-gauge-progress" pathLength="100" stroke-dasharray="${pct.clamped} 100" d="M18 58 A42 42 0 0 1 102 58"></path>`
    : '';
  return `
    <article class="usage-gauge-card usage-gauge-card--${tone}${isOver ? ' is-over' : ''}" style="--gauge-color: ${color};">
      <div class="usage-gauge-title">${escapeHtml(label)}</div>
      <div class="usage-gauge-visual" aria-label="${escapeHtml(`${label}: ${displayPct}% ${unitText}`)}">
        <svg class="usage-gauge-svg" viewBox="0 0 120 72" role="img" aria-hidden="true">
          <path class="usage-gauge-track" pathLength="100" d="M18 58 A42 42 0 0 1 102 58"></path>
          ${progressPath}
        </svg>
        <div class="usage-gauge-center">
          <strong>${displayPct}%</strong>
          <span>${escapeHtml(unitText)}</span>
        </div>
      </div>
      <div class="usage-gauge-meta">
        <strong>${escapeHtml(valueText)}</strong>
        <span>of ${escapeHtml(limitText)}</span>
      </div>
      ${detailHtml}
    </article>
  `;
}

function buildCashGaugePanel(summary) {
  const s = summary || {};
  const limit = Number(s.cash_limit_total || state.settings.cash_limit_total || 0);
  const receivedAvailable = availableAmount(s.cash_received, limit);
  const sentAvailable = availableAmount(s.cash_sent, limit);
  return `
    <div class="usage-gauge-grid">
      ${buildUsageGaugeCard({
        label: 'Cash recibido',
        available: receivedAvailable,
        limit,
        valueText: formatMoneyDots(receivedAvailable),
        limitText: formatMoneyDots(limit),
        unitText: 'Available',
        tone: 'cash',
      })}
      ${buildUsageGaugeCard({
        label: 'Cash enviado',
        available: sentAvailable,
        limit,
        valueText: formatMoneyDots(sentAvailable),
        limitText: formatMoneyDots(limit),
        unitText: 'Available',
        tone: 'cash',
      })}
    </div>
  `;
}

function buildMoveGaugePanel(moveSummary) {
  const m = moveSummary || {};
  const preLimit = MOVE_LIMIT_PRE30;
  const postLimit = MOVE_LIMIT_POST30;
  const preAvailable = availableMoves(m, 'pre30', preLimit);
  const postAvailable = availableMoves(m, 'post30', postLimit);
  return `
    <div class="usage-gauge-grid">
      ${buildUsageGaugeCard({
        label: 'Pre-30 moves',
        available: preAvailable,
        limit: preLimit,
        valueText: formatDots(preAvailable),
        limitText: formatDots(preLimit),
        unitText: 'Available',
        tone: 'moves',
        detailHtml: '<button type="button" class="info-chip-btn usage-gauge-info" data-move-log-bucket="pre30" aria-label="Open pre-30 transfer move log">i</button>',
      })}
      ${buildUsageGaugeCard({
        label: 'Post-30 moves',
        available: postAvailable,
        limit: postLimit,
        valueText: formatDots(postAvailable),
        limitText: formatDots(postLimit),
        unitText: 'Available',
        tone: 'moves',
        detailHtml: '<button type="button" class="info-chip-btn usage-gauge-info" data-move-log-bucket="post30" aria-label="Open post-30 transfer move log">i</button>',
      })}
    </div>
  `;
}

function buildSummaryCardsHtml(summary) {
  const s = summary || {};
  const m = state.teamData?.move_summary || {};
  return `
    ${buildBalancePanelHtml(s)}
    <article class="card card-summary card-summary-split team-operations-card">
      <div class="card-summary-col">
        <div class="label">Cash</div>
        ${buildCashGaugePanel(s)}
      </div>
      <div class="card-summary-col">
        <div class="label">Transfer moves</div>
        ${buildMoveGaugePanel(m)}
      </div>
    </article>
  `;
}

function openMobileInfo() {
  const list = document.getElementById('mobileInfoList');
  if (!list) return;
  const summaryHtml = state.teamData?.summary
    ? `<div class="mobile-info-summary cards team-summary-grid">${buildSummaryCardsHtml(state.teamData.summary)}</div>`
    : '';
  if (!summaryHtml) return;
  list.innerHTML = summaryHtml;
  list.querySelectorAll('[data-move-log-bucket]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const bucket = normalizeMoveBucket(btn.dataset.moveLogBucket);
      const rows = (state.teamData?.move_summary?.log || []).filter((item) => normalizeMoveBucket(item.bucket) === bucket);
      openMoveLog(`${state.teamCode || ''} · ${moveBucketLabel(bucket)}`, rows);
    });
  });
  state.ui.mobileInfoOpen = true;
  setMobileOverlayVisible('mobileInfoBackdrop', true);
}

function closeMobileInfo() {
  state.ui.mobileInfoOpen = false;
  setMobileOverlayVisible('mobileInfoBackdrop', false);
}

function syncMobileInfoButton() {
  const btn = document.getElementById('mobileInfoBtn');
  if (!btn) return;
  const show = Boolean(state.teamData);
  btn.hidden = !show;
}

function setViewMode(mode) {
  state.ui.viewMode = mode;
  const trackerSection = document.getElementById('trackerSection');
  const freeAgentsSection = document.getElementById('freeAgentsSection');
  const draftOrderSection = document.getElementById('draftOrderSection');
  const tradeMachineSection = document.getElementById('tradeMachineSection');
  const showTracker = mode === 'tracker';
  const showFreeAgents = mode === 'free-agents';
  const showDraftOrder = mode === 'draft-order';
  const showTradeMachine = mode === 'trade-machine';

  trackerSection.classList.toggle('section-hidden', !showTracker);
  freeAgentsSection.classList.toggle('section-hidden', !showFreeAgents);
  if (draftOrderSection) draftOrderSection.classList.toggle('section-hidden', !showDraftOrder);
  if (tradeMachineSection) tradeMachineSection.classList.toggle('section-hidden', !showTradeMachine);
  syncTeamTabs();
  syncMobileInfoButton();
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
      <td>${trackerSpaceValueHtml(row.espacio_cap)}</td>
      <td>${trackerSpaceValueHtml(row.espacio_luxury)}</td>
      <td>${trackerSpaceValueHtml(row.espacio_1er_apron)}</td>
      <td>${trackerSpaceValueHtml(row.espacio_2do_apron)}</td>
      <td>${trackerRosterCountChipHtml('standard', Number(row.roster_standard_count || 0))}</td>
      <td>${trackerRosterCountChipHtml('twoWay', Number(row.roster_two_way_count || 0))}</td>
      <td>${draftPickCountChipHtml(Number(row.draft_first_count || 0), '1st')}</td>
      <td>${draftPickCountChipHtml(Number(row.draft_second_count || 0), '2nd')}</td>
    `;
    const teamBtn = tr.querySelector('[data-team-code]');
    teamBtn.addEventListener('click', async () => {
      await loadTeam(row.team_code);
    });
    tbody.appendChild(tr);
  });
}

function renderFreeAgents() {
  const tbody = document.querySelector('#freeAgentsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const rows = sortedRows(state.freeAgents || [], state.sort.free_agents);
  if (!rows.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="6">No free agents listed.</td>';
    tbody.appendChild(tr);
    return;
  }
  rows.forEach((agent) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(agent.name || '')}</td>
      <td>${escapeHtml(agent.position || '')}</td>
      <td>${escapeHtml(agent.bird_rights || '')}</td>
      <td>${escapeHtml(agent.rating || '')}</td>
      <td>${agent.years_left == null ? '' : escapeHtml(agent.years_left)}</td>
      <td class="details-cell">${escapeHtml(agent.notes || '')}</td>
    `;
    tbody.appendChild(tr);
  });
}

function teamByCode(code) {
  const normalized = String(code || '').trim().toUpperCase();
  return (state.teams || []).find((team) => String(team.code || '').toUpperCase() === normalized) || null;
}

function draftOrderLogoHtml(code, className = 'draft-order-team-logo') {
  const normalized = String(code || '').trim().toUpperCase();
  if (!normalized) return '<span class="draft-order-team-fallback">-</span>';
  const src = teamLogoCandidates(normalized)[0];
  return `
    <span class="${className}" title="${escapeHtml(normalized)}" aria-label="${escapeHtml(normalized)}">
      <span>${escapeHtml(normalized)}</span>
      <img src="${escapeHtml(src)}" alt="" onload="this.previousElementSibling.style.display='none'" onerror="this.style.display='none';this.previousElementSibling.style.display='inline-flex'">
    </span>
  `;
}

function draftOrderTeamHtml(code, name) {
  const normalized = String(code || '').trim().toUpperCase();
  const team = teamByCode(normalized);
  const label = String(name || team?.name || normalized || '').trim();
  return `
    <span class="draft-order-team">
      ${draftOrderLogoHtml(normalized)}
      <span class="draft-order-team-text">
        <strong>${escapeHtml(normalized || '-')}</strong>
        <span>${escapeHtml(label || normalized || '-')}</span>
      </span>
    </span>
  `;
}

function draftOrderViaHtml(code, name) {
  const normalized = String(code || '').trim().toUpperCase();
  const team = teamByCode(normalized);
  const label = String(name || team?.name || normalized || '').trim();
  return `
    <span class="draft-order-via" title="${escapeHtml(label || normalized)}">
      <span>(Vía</span>
      ${draftOrderLogoHtml(normalized, 'draft-order-via-logo')}
      <span>)</span>
    </span>
  `;
}

function draftOrderViaCellHtml(row) {
  const owner = String(row?.owner_team_code || '').trim().toUpperCase();
  const original = String(row?.original_team_code || '').trim().toUpperCase();
  if (owner && original && owner === original) return '';
  return draftOrderViaHtml(row?.original_team_code, row?.original_team_name);
}

function renderDraftOrderRound(round, label) {
  const rows = (state.draftOrder?.draft_order || [])
    .filter((row) => String(row.draft_round || '').trim() === round)
    .sort((a, b) => Number(a.pick_number || 0) - Number(b.pick_number || 0));
  const body = rows.length
    ? rows.map((row) => `
        <tr>
          <td class="draft-order-number">${escapeHtml(row.pick_number || '')}</td>
          <td>${draftOrderTeamHtml(row.owner_team_code, row.owner_team_name)}</td>
          <td>${draftOrderViaCellHtml(row)}</td>
        </tr>
      `).join('')
    : '<tr><td colspan="3" class="draft-order-empty">No selections configured.</td></tr>';
  return `
    <article class="draft-order-round">
      <h3>${escapeHtml(label)}</h3>
      <div class="table-wrap draft-order-table-wrap">
        <table class="draft-order-table">
          <thead>
            <tr>
              <th>Number</th>
              <th>Team that owns the pick</th>
              <th>Original pick</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </article>
  `;
}

function renderDraftOrder() {
  const board = document.getElementById('draftOrderBoard');
  const subtitle = document.getElementById('draftOrderSubtitle');
  if (!board) return;
  const draftYear = Number(state.draftOrder?.draft_year || currentSeasonStart() + 1);
  if (subtitle) subtitle.textContent = `${draftYear} order of selection`;
  board.innerHTML = `
    ${renderDraftOrderRound('1st', '1st Round')}
    ${renderDraftOrderRound('2nd', '2nd Round')}
  `;
}

function renderCards() {
  const wrap = document.getElementById('teamMeta');
  const t = state.teamData.team;
  const s = state.teamData.summary;
  setPageHeading(t.name || 'Team', t.gm || '');
  renderCapStatusPills(s);
  wrap.innerHTML = buildSummaryCardsHtml(s);
  wrap.querySelectorAll('[data-move-log-bucket]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const bucket = normalizeMoveBucket(btn.dataset.moveLogBucket);
      const rows = (state.teamData?.move_summary?.log || []).filter((item) => normalizeMoveBucket(item.bucket) === bucket);
      openMoveLog(`${t.code} · ${moveBucketLabel(bucket)}`, rows);
    });
  });
}

function renderImportantFigures() {
  const table = document.getElementById('importantFiguresTable');
  if (!table) return;
  const currentYear = currentSeasonStart();
  const seasons = balanceSeasonYears();
  const seasonData = seasons.map((season) => ({ season, balances: seasonBalances(season) }));
  const rows = [
    ['CAP TOTAL', 'cap_total'],
    ['GASTO TOTAL', 'gasto_total'],
    ['Cuenta del APRON', 'apron_account'],
    ['Luxury tax', 'luxury_tax'],
  ];
  table.innerHTML = `
    <thead>
      <tr>
        <th class="balance-row-heading">Balance</th>
        ${seasons.map((season) => `
          <th class="${season === currentYear ? 'is-current-year' : ''}">${seasonSlashLabel(season)}</th>
        `).join('')}
      </tr>
    </thead>
    <tbody>
      ${rows.map(([label, key]) => `
        <tr>
          <th class="balance-row-label">${label}</th>
          ${seasonData.map(({ season, balances }) => {
            const value = Number(balances[key] || 0);
            const isLiability = key === 'luxury_tax';
            const valueClass = isLiability
              ? (value > 0 ? 'is-negative' : '')
              : (value < 0 ? 'is-negative' : value > 0 ? 'is-positive' : '');
            return `
              <td class="${season === currentYear ? 'is-current-year' : ''}">
                <span class="balance-value ${valueClass}">${formatMoneyDots(value)}</span>
              </td>
            `;
          }).join('')}
        </tr>
      `).join('')}
    </tbody>
  `;

  const appendix = document.getElementById('importantFiguresAppendix');
  if (!appendix) return;
  const salaryCap = Number(state.settings.salary_cap_2025 || 0);
  const luxuryCap = Number(state.settings.luxury_cap || salaryCap * 1.215);
  const firstApron = Number(state.settings.first_apron || 0);
  const secondApron = Number(state.settings.second_apron || 0);
  const minCap = Number(state.settings.minimum_cap_allowed || salaryCap * 0.9);
  const appendixRows = [
    ['Temporada actual', seasonLabel(currentYear)],
    ['Salary cap', formatDots(salaryCap)],
    ['Luxury cap', formatDots(luxuryCap)],
    ['1er Apron', formatDots(firstApron)],
    ['2do Apron', formatDots(secondApron)],
    ['Mínimo cap permitido', formatDots(minCap)],
  ];
  appendix.innerHTML = `
    <div class="important-figures-appendix-title">Cifras importantes</div>
    <div class="important-figures-appendix-list">
      ${appendixRows.map(([label, value]) => `
        <span class="important-figures-appendix-item">
          <span>${label}</span>
          <strong>${value}</strong>
        </span>
      `).join('')}
    </div>
  `;
  renderRosterCountSection();
  renderLuxuryHistory();
}

function renderRosterCountSection() {
  const wrap = document.getElementById('rosterCountSection');
  if (!wrap) return;
  const counts = rosterCountFromSummary(state.teamData?.summary || {});
  const limits = rosterLimits();
  wrap.innerHTML = `
    <div class="roster-count-head">
      <h3>Tamaño de plantilla</h3>
      <span>Contratos activos</span>
    </div>
    <div class="roster-count-grid">
      ${rosterCountChipHtml('standard', counts.standard, 'Estándar')}
      ${rosterCountChipHtml('twoWay', counts.twoWay, 'Two-way')}
    </div>
    <div class="roster-count-note">
      Estándar: ${limits.standardMin}-${limits.standardMax} en temporada, ${limits.standardOffseasonMax} en offseason · Two-way: ${limits.twoWayMin}-${limits.twoWayMax}
    </div>
  `;
}

function renderLuxuryHistory() {
  const wrap = document.getElementById('luxuryHistorySection');
  if (!wrap) return;
  if (!state.teamData) {
    wrap.innerHTML = '';
    return;
  }
  const rows = luxuryHistoryYears().map((year) => ({
    year,
    repeater: luxuryRepeaterForSeason(state.teamData, year),
  }));
  wrap.innerHTML = `
    <h3>Historia de luxury</h3>
    <div class="luxury-history-wrap">
      <table class="luxury-history-table">
        <thead>
          <tr>
            <th></th>
            <th>¿Reincidente?</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(({ year, repeater }) => `
            <tr>
              <th>${seasonSlashLabel(year)}</th>
              <td><span class="luxury-history-value">${repeater ? 'Sí' : 'No'}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function gmTimelineTeam(code) {
  return (state.teams || []).find((team) => team.code === code) || null;
}

function gmTimelineDefaultColor(index, teamCode) {
  const theme = TEAM_THEMES[teamCode] || { primary: '#0f766e', secondary: '#99f6e4' };
  const palette = [theme.primary, theme.secondary, '#334155', '#f8fafc', '#b91c1c', '#d97706'];
  const color = palette[index % palette.length] || theme.primary;
  return color.toUpperCase();
}

function parseGmTimelineDate(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) {
    const date = new Date(`${raw}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const slashMatch = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (slashMatch) {
    const [, dd, mm, yyyy] = slashMatch;
    const date = new Date(`${yyyy}-${mm}-${dd}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
}

function formatGmTimelineDate(value) {
  const date = parseGmTimelineDate(value);
  if (!date) return '';
  const dd = String(date.getUTCDate()).padStart(2, '0');
  const mm = String(date.getUTCMonth() + 1).padStart(2, '0');
  const yyyy = String(date.getUTCFullYear());
  return `${dd}/${mm}/${yyyy}`;
}

function teamGmTimelineEntries() {
  const code = state.teamCode || '';
  return (state.teamData?.gm_history || [])
    .map((entry, idx) => ({
      gm_name: String(entry.gm_name || '').trim(),
      start_date: String(entry.start_date || '').trim(),
      color: String(entry.color || gmTimelineDefaultColor(idx, code)).trim(),
    }))
    .filter((entry) => entry.gm_name && parseGmTimelineDate(entry.start_date))
    .sort((a, b) => {
      const aTime = parseGmTimelineDate(a.start_date)?.getTime() || 0;
      const bTime = parseGmTimelineDate(b.start_date)?.getTime() || 0;
      if (aTime !== bTime) return aTime - bTime;
      return a.gm_name.localeCompare(b.gm_name);
    });
}

function hasTeamGmTimelineEntries() {
  return teamGmTimelineEntries().length > 0;
}

function gmTimelineSvg(entries, teamCode) {
  const team = gmTimelineTeam(teamCode) || { code: teamCode, name: teamCode };
  const theme = TEAM_THEMES[teamCode] || { primary: '#0f766e', secondary: '#99f6e4' };
  const parsedEntries = entries.map((entry, idx) => ({
    ...entry,
    date: parseGmTimelineDate(entry.start_date),
    color: entry.color || gmTimelineDefaultColor(idx, teamCode),
  })).filter((entry) => entry.date);
  const width = 1500;
  const height = 820;
  const left = 90;
  const right = 90;
  const timelineY = 575;
  const barY = 475;
  const barH = 52;
  const today = new Date();
  const present = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()));
  const firstDate = parsedEntries[0]?.date || present;
  const lastStart = parsedEntries[parsedEntries.length - 1]?.date || present;
  const fallbackEnd = new Date(Date.UTC(lastStart.getUTCFullYear() + 1, lastStart.getUTCMonth(), lastStart.getUTCDate()));
  const endDate = present.getTime() > lastStart.getTime() ? present : fallbackEnd;
  const minTime = firstDate.getTime();
  const maxTime = Math.max(endDate.getTime(), minTime + 86400000);
  const xForDate = (date) => {
    const pct = (date.getTime() - minTime) / (maxTime - minTime);
    return left + Math.max(0, Math.min(1, pct)) * (width - left - right);
  };
  const startYear = firstDate.getUTCFullYear();
  const endYear = endDate.getUTCFullYear();
  const tickYears = Array.from({ length: endYear - startYear + 1 }, (_, idx) => startYear + idx);
  const logoHref = teamLogoCandidates(teamCode)[0] || '';
  const segments = parsedEntries.map((entry, idx) => {
    const startX = xForDate(entry.date);
    const end = parsedEntries[idx + 1]?.date || endDate;
    const endX = Math.max(startX + 8, xForDate(end));
    const radius = idx === 0 || idx === parsedEntries.length - 1 ? 24 : 0;
    return `<rect x="${startX.toFixed(1)}" y="${barY}" width="${(endX - startX).toFixed(1)}" height="${barH}" rx="${radius}" fill="${escapeHtml(entry.color)}" opacity="0.94"/>`;
  }).join('');
  const markerLevels = [275, 348, 405, 318];
  const rawMarkerLayout = parsedEntries.map((entry) => {
    const x = xForDate(entry.date);
    const labelWidth = Math.max(130, Math.min(230, String(entry.gm_name || '').length * 16 + 52));
    const preferredLabelX = Math.max(left + labelWidth / 2, Math.min(width - right - labelWidth / 2, x));
    return { entry, x, labelWidth, labelX: preferredLabelX };
  });
  rawMarkerLayout.forEach((layout, idx) => {
    if (idx === 0) return;
    const previous = rawMarkerLayout[idx - 1];
    const minX = previous.labelX + previous.labelWidth / 2 + layout.labelWidth / 2 + 14;
    layout.labelX = Math.max(layout.labelX, minX);
  });
  for (let idx = rawMarkerLayout.length - 1; idx >= 0; idx -= 1) {
    const layout = rawMarkerLayout[idx];
    const maxX = width - right - layout.labelWidth / 2;
    layout.labelX = Math.min(layout.labelX, maxX);
    if (idx < rawMarkerLayout.length - 1) {
      const next = rawMarkerLayout[idx + 1];
      const maxBeforeNext = next.labelX - next.labelWidth / 2 - layout.labelWidth / 2 - 14;
      layout.labelX = Math.min(layout.labelX, maxBeforeNext);
    }
    layout.labelX = Math.max(left + layout.labelWidth / 2, layout.labelX);
  }
  const markerLayout = parsedEntries.map((entry, idx) => {
    const raw = rawMarkerLayout[idx];
    const x = raw?.x ?? xForDate(entry.date);
    const labelX = raw?.labelX ?? x;
    const levelIndex = idx % markerLevels.length;
    const labelY = markerLevels[levelIndex];
    const avatarY = labelY - 72;
    return { entry, x, labelX, labelY, avatarY };
  });
  const markers = markerLayout.map(({ entry, x, labelX, labelY, avatarY }) => {
    const connectorTop = Math.min(barY - 8, labelY + 54);
    return `
      <g>
        <path d="M ${labelX.toFixed(1)} ${connectorTop} L ${labelX.toFixed(1)} ${barY - 22} L ${x.toFixed(1)} ${barY}" fill="none" stroke="#f8fafc" stroke-width="3" opacity="0.88" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${labelX.toFixed(1)}" cy="${avatarY}" r="33" fill="${escapeHtml(entry.color)}" stroke="#f8fafc" stroke-width="3"/>
        <circle cx="${labelX.toFixed(1)}" cy="${avatarY - 9}" r="10" fill="none" stroke="#f8fafc" stroke-width="4"/>
        <path d="M ${labelX - 19} ${avatarY + 18} C ${labelX - 14} ${avatarY + 2}, ${labelX + 14} ${avatarY + 2}, ${labelX + 19} ${avatarY + 18}" fill="none" stroke="#f8fafc" stroke-width="4" stroke-linecap="round"/>
        <text x="${labelX.toFixed(1)}" y="${labelY}" text-anchor="middle" fill="#f8fafc" font-size="28" font-weight="900">${escapeHtml(entry.gm_name)}</text>
        <text x="${labelX.toFixed(1)}" y="${labelY + 34}" text-anchor="middle" fill="#f8fafc" font-size="22" font-weight="700" letter-spacing="1">${escapeHtml(formatGmTimelineDate(entry.start_date))}</text>
      </g>
    `;
  }).join('');
  const ticks = tickYears.map((year) => {
    const x = xForDate(new Date(Date.UTC(year, 0, 1)));
    return `
      <g>
        <line x1="${x.toFixed(1)}" y1="${timelineY - 28}" x2="${x.toFixed(1)}" y2="${timelineY + 20}" stroke="#f8fafc" stroke-width="2" stroke-dasharray="5 8" opacity="0.75"/>
        <circle cx="${x.toFixed(1)}" cy="${timelineY + 28}" r="8" fill="#111827" stroke="#f8fafc" stroke-width="3"/>
        <text x="${x.toFixed(1)}" y="${timelineY + 70}" text-anchor="middle" fill="#f8fafc" font-size="30" font-weight="900" letter-spacing="2">${year}</text>
      </g>
    `;
  }).join('');
  const buildings = Array.from({ length: 22 }, (_, idx) => {
    const bw = 28 + (idx % 4) * 9;
    const bh = 95 + (idx % 5) * 32;
    const x = 28 + idx * 67;
    const y = 360 - bh;
    return `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" fill="#f8fafc" opacity="${0.045 + (idx % 3) * 0.018}"/>`;
  }).join('');

  return `
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(team.name)} GM timeline">
  <defs>
    <radialGradient id="gmBgGlow" cx="50%" cy="40%" r="60%">
      <stop offset="0%" stop-color="${escapeHtml(theme.primary)}" stop-opacity="0.22"/>
      <stop offset="58%" stop-color="#111827" stop-opacity="0.84"/>
      <stop offset="100%" stop-color="#020617" stop-opacity="1"/>
    </radialGradient>
    <linearGradient id="gmBarFrame" x1="0%" x2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.88"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.62"/>
    </linearGradient>
  </defs>
  <rect width="1500" height="820" fill="#020617"/>
  <rect width="1500" height="820" fill="url(#gmBgGlow)"/>
  <g>${buildings}</g>
  <text x="750" y="92" text-anchor="middle" fill="${escapeHtml(theme.primary)}" font-size="70" font-weight="900" letter-spacing="15">${escapeHtml(team.name)}</text>
  <text x="750" y="148" text-anchor="middle" fill="#f8fafc" font-size="38" font-weight="900" letter-spacing="15">GENERAL MANAGERS TIMELINE</text>
  <line x1="390" y1="188" x2="675" y2="188" stroke="${escapeHtml(theme.primary)}" stroke-width="3"/>
  <line x1="825" y1="188" x2="1110" y2="188" stroke="${escapeHtml(theme.primary)}" stroke-width="3"/>
  <image href="${escapeHtml(logoHref)}" x="710" y="158" width="80" height="80" opacity="0.98"/>
  <text x="750" y="610" text-anchor="middle" fill="#f8fafc" font-size="360" font-weight="900" opacity="0.045">${escapeHtml(team.code || teamCode)}</text>
  <rect x="${left}" y="${barY}" width="${width - left - right}" height="${barH}" rx="26" fill="#f8fafc" opacity="0.14"/>
  <rect x="${left}" y="${barY}" width="${width - left - right}" height="${barH}" rx="26" fill="none" stroke="url(#gmBarFrame)" stroke-width="3"/>
  ${segments}
  <line x1="${left}" y1="${timelineY + 28}" x2="${width - right}" y2="${timelineY + 28}" stroke="#f8fafc" stroke-width="3"/>
  ${ticks}
  ${markers}
  <text x="${left}" y="690" text-anchor="start" fill="${escapeHtml(theme.primary)}" font-size="26" font-weight="900" letter-spacing="2">${escapeHtml(formatGmTimelineDate(parsedEntries[0]?.start_date || ''))}</text>
  <text x="${left}" y="720" text-anchor="start" fill="${escapeHtml(theme.primary)}" font-size="25" font-weight="900" letter-spacing="3">START</text>
  <text x="${width - right}" y="690" text-anchor="end" fill="${escapeHtml(theme.primary)}" font-size="26" font-weight="900" letter-spacing="2">${escapeHtml(formatGmTimelineDate(endDate.toISOString().slice(0, 10)))}</text>
  <text x="${width - right}" y="720" text-anchor="end" fill="${escapeHtml(theme.primary)}" font-size="25" font-weight="900" letter-spacing="3">PRESENT</text>
  <text x="750" y="755" text-anchor="middle" fill="#f8fafc" font-size="18" letter-spacing="12" opacity="0.88">BUILDING THE FUTURE. TOGETHER.</text>
  <line x1="520" y1="780" x2="690" y2="780" stroke="${escapeHtml(theme.primary)}" stroke-width="2"/>
  <line x1="810" y1="780" x2="980" y2="780" stroke="${escapeHtml(theme.primary)}" stroke-width="2"/>
  <text x="750" y="789" text-anchor="middle" fill="${escapeHtml(theme.primary)}" font-size="26" font-weight="900">${escapeHtml(team.code || teamCode)}</text>
  <text x="34" y="790" fill="#cbd5e1" font-size="16" font-style="italic" opacity="0.86">All dates in DD/MM/YYYY</text>
</svg>`.trim();
}

function ensureGmTimelineSection() {
  let section = document.getElementById('gmTimelineSection');
  if (section) return section;
  const after = document.getElementById('importantFiguresSection');
  if (!after?.parentElement) return null;
  section = document.createElement('section');
  section.id = 'gmTimelineSection';
  section.className = 'gm-timeline-section section-hidden';
  section.innerHTML = `
    <h2>GM timeline</h2>
    <div id="gmTimelinePreview" class="gm-timeline-preview"></div>
  `;
  after.insertAdjacentElement('afterend', section);
  return section;
}

function renderGmTimelineSection() {
  const section = ensureGmTimelineSection();
  if (!section) return;
  const preview = section.querySelector('#gmTimelinePreview');
  const entries = teamGmTimelineEntries();
  if (!entries.length) {
    if (preview) preview.innerHTML = '';
    section.classList.add('section-hidden');
    return;
  }
  if (preview) preview.innerHTML = gmTimelineSvg(entries, state.teamCode);
  syncTeamTabs();
}

function renderCapStatusPills(summary) {
  const wrap = document.getElementById('capStatusPills');
  if (!wrap) return;
  state.ui.statusPills = balanceNoticeItems(summary);
  wrap.innerHTML = '';
  syncMobileInfoButton();
}

function preferredRosterView() {
  return 'list';
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

function renderSeasonViewControl() {
  const select = document.getElementById('seasonViewSelect');
  if (!select) return;
  const currentYear = currentSeasonStart();
  const selected = selectedSeasonStart();
  select.innerHTML = availableSeasonViewStarts()
    .map((season) => {
      const suffix = season === currentYear ? ' (current)' : '';
      return `<option value="${season}">${seasonLabel(season)}${suffix}</option>`;
    })
    .join('');
  select.value = String(selected);
}

function setSeasonViewStart(startYear) {
  state.ui.seasonViewStart = normalizeSeasonViewStart(startYear);
  renderSeasonViewControl();
  if (state.teamCode) setTeamInUrl(state.teamCode);
  if (!state.teamData) return;
  renderPlayers();
  renderDeadContracts();
  renderExceptions();
  renderAssets();
}

function setupSeasonViewControl() {
  const select = document.getElementById('seasonViewSelect');
  if (!select) return;
  renderSeasonViewControl();
  select.addEventListener('change', () => {
    setSeasonViewStart(select.value);
  });
}

function renderPlayers() {
  const tbody = document.querySelector('#playersTable tbody');
  const cardsWrap = document.getElementById('playersCards');
  tbody.innerHTML = '';
  if (cardsWrap) cardsWrap.innerHTML = '';

  applySeasonColumnVisibility();
  const seasons = visibleSeasonYears();
  const filtered = filteredPlayers(state.teamData.players);
  const rows = sortedRows(filtered, state.sort.players);
  const playerHeader = document.querySelector('#playersTable thead th[data-sort-mode="player-cycle"]');
  if (playerHeader) playerHeader.dataset.label = `PLAYER (${rows.length})`;
  updateSortIndicators('playersTable', state.sort.players);
  const showPositionGroups = shouldRenderRosterPositionGroups();
  const positionCounts = rosterPositionCounts(rows);
  let previousPositionKey = null;
  rows.forEach((p) => {
    if (showPositionGroups) {
      const positionKey = rosterPositionKey(p);
      if (positionKey !== previousPositionKey) {
        appendRosterPositionSeparator(tbody, positionKey, positionCounts[positionKey] || 0, 3 + seasons.length);
        previousPositionKey = positionKey;
      }
    }
    const metaPayload = {
      position: p.position || '',
      rating: p.rating || '',
      contract: p.bird_rights || '',
      years: p.years_left || '',
    };
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <div class="player-cell">
          <div class="player-name-row">
            <span class="player-name">${p.name || ''}</span>
            <button type="button" class="player-meta-btn" data-player-meta='${escapeHtml(JSON.stringify(metaPayload))}' aria-label="Show player info">i</button>
          </div>
          <span class="player-tags">
            ${p.position ? `<span class="pos-pill">${p.position}</span>` : ''}
            ${p.rating ? `<span class="meta-pill">${p.rating}</span>` : ''}
          </span>
        </div>
      </td>
      <td>${p.bird_rights ? `<span class="type-pill ${typeClass(p.bird_rights)}">${p.bird_rights}</span>` : ''}</td>
      <td>${p.years_left || ''}</td>
      ${seasons.map((season) => `<td>${salaryCellHtml(p, season, state.filters.showEmptyYears)}</td>`).join('')}
    `;
    const infoBtn = tr.querySelector('.player-meta-btn');
    if (infoBtn) {
      infoBtn.addEventListener('click', () => {
        const raw = infoBtn.dataset.playerMeta || '{}';
        let meta = {};
        try {
          meta = JSON.parse(raw);
        } catch {
          meta = {};
        }
        openPlayerMetaModal(p.name || 'Player info', meta);
      });
    }
    tbody.appendChild(tr);

    if (cardsWrap) {
      const contractRows = visibleSeasonYears()
        .map((season) => ({
          season,
          content: salaryCellHtml(p, season, state.filters.showEmptyYears),
        }))
        .filter((row) => state.filters.showEmptyYears || Boolean(salaryBox(p, row.season)));
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
  bindSalaryInfoToggles(tbody);
  bindSalaryInfoToggles(cardsWrap);
  renderRosterTotals(rows, seasons);
}

function renderRosterTotals(rows, seasons) {
  const tfoot = document.querySelector('#playersTable tfoot');
  if (!tfoot) return;
  const totals = seasons.map((season) => rows.reduce((sum, player) => sum + salaryNumericValue(player, season), 0));
  tfoot.innerHTML = `
    <tr class="roster-total-row">
      <td class="roster-total-label">Total</td>
      <td></td>
      <td></td>
      ${totals.map((total) => `
        <td><span class="roster-total-amount">${formatMoneyDots(total)}</span></td>
      `).join('')}
    </tr>
  `;
}

function setupRosterFilters() {
  const guaranteed = document.getElementById('filterGuaranteedOnly');
  const options = document.getElementById('filterOptionsOnly');
  const emptyYears = document.getElementById('filterShowEmptyYears');
  if (!guaranteed || !options || !emptyYears) return;

  guaranteed.checked = state.filters.guaranteedOnly;
  options.checked = state.filters.optionsOnly;
  emptyYears.checked = state.filters.showEmptyYears;

  guaranteed.addEventListener('change', () => {
    state.filters.guaranteedOnly = guaranteed.checked;
    renderPlayers();
  });
  options.addEventListener('change', () => {
    state.filters.optionsOnly = options.checked;
    renderPlayers();
  });
  emptyYears.addEventListener('change', () => {
    state.filters.showEmptyYears = emptyYears.checked;
    renderPlayers();
  });
}

function setTeamInUrl(teamCode) {
  const url = new URL(window.location.href);
  if (teamCode) {
    url.searchParams.set('team', teamCode);
    const selected = selectedSeasonStart();
    if (selected !== currentSeasonStart()) url.searchParams.set('season', String(selected));
    else url.searchParams.delete('season');
  } else {
    url.searchParams.delete('team');
    url.searchParams.delete('season');
  }
  window.history.replaceState({}, '', url.toString());
}

function readInitialTeamCode() {
  const fromQuery = new URLSearchParams(window.location.search).get('team');
  if (fromQuery && String(fromQuery).trim()) return String(fromQuery).trim().toUpperCase();
  try {
    const fromStorage = window.localStorage.getItem(LAST_TEAM_STORAGE_KEY);
    if (fromStorage && String(fromStorage).trim()) return String(fromStorage).trim().toUpperCase();
  } catch {
    // ignore localStorage errors
  }
  return null;
}

function readInitialSeasonStart() {
  const fromQuery = new URLSearchParams(window.location.search).get('season');
  const parsed = Number(fromQuery);
  return Number.isInteger(parsed) ? parsed : null;
}

function assetSeasonYear(asset) {
  const rawYear = asset?.year;
  if (rawYear === null || rawYear === undefined || String(rawYear).trim() === '') return null;
  const year = Number(rawYear);
  if (Number.isFinite(year)) return year;
  return null;
}

function isAssetBeforeSelectedSeason(asset) {
  const year = assetSeasonYear(asset);
  const selectedAssetYear = asset?.asset_type === 'draft_pick'
    ? selectedSeasonStart() + 1
    : selectedSeasonStart();
  return Number.isFinite(year) && year < selectedAssetYear;
}

function parseDraftConditionalTeams(value) {
  if (Array.isArray(value)) {
    return Array.from(new Set(value.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)));
  }
  const raw = String(value || '').trim();
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return Array.from(new Set(parsed.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)));
    }
  } catch (err) {
    // Older/manual values may be comma-separated instead of JSON.
  }
  return Array.from(new Set(raw.split(/[,/|]/).map((code) => code.trim().toUpperCase()).filter(Boolean)));
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
    if (type === 'acquired' || type === 'sold' || type === 'conditional') return type;
    return 'own';
  };

  const conditionalTeams = (pick) => parseDraftConditionalTeams(pick.draft_pick_conditional_teams);

  const orderedPicksForSeason = (seasonPicks) => {
    const own1 = [];
    const own2 = [];
    const acq1 = [];
    const acq2 = [];
    const conditional = [];
    const sold = [];
    seasonPicks.forEach((pick) => {
      const t = normalizedType(pick);
      const r = normalizedRound(pick);
      if (t === 'own' && r === '1st') own1.push(pick);
      else if (t === 'own' && r === '2nd') own2.push(pick);
      else if (t === 'acquired' && r === '1st') acq1.push(pick);
      else if (t === 'acquired' && r === '2nd') acq2.push(pick);
      else if (t === 'conditional') conditional.push(pick);
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
    conditional.sort(byOwnerThenId);
    sold.sort(byOwnerThenId);
    return [...own1, ...own2, ...acq1, ...acq2, ...conditional, ...sold];
  };

  const picks = (state.teamData.assets || [])
    .filter((a) => a.asset_type === 'draft_pick' && !isAssetBeforeSelectedSeason(a));
  if (picks.length === 0) {
    board.innerHTML = '<p>No draft picks loaded for this season view.</p>';
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
        const isRestricted = Number(pick.draft_pick_restricted || 0) !== 0;
        const isProtected = Number(pick.draft_pick_protected || 0) !== 0;
        const sourceTeams = conditionalTeams(pick);
        const soldToTeams = parseDraftConditionalTeams(pick.draft_pick_sold_to);
        const soldToLabel = soldToTeams.join(' / ');
        const owner = pickType === 'conditional'
          ? (sourceTeams[0] || state.teamCode)
          : pick.draft_pick_type === 'acquired'
          ? (pick.original_owner || '')
          : state.teamCode;
        const title = `${pickRound.toUpperCase()} Pick`;
        const subtitle = pickType === 'acquired'
          ? `From ${owner || 'other team'}`
          : pickType === 'sold'
            ? `Sold${soldToLabel ? ` to ${soldToLabel}` : ''}`
            : pickType === 'conditional'
              ? `Conditional: ${sourceTeams.length ? sourceTeams.join(' / ') : 'teams TBD'}`
              : 'Own pick';
        const badgesHtml = [
          isRestricted ? '<span class="pick-restricted-tag">Restricted</span>' : '',
          isProtected ? '<span class="pick-protected-tag">Protected</span>' : '',
          pickType === 'conditional' ? '<span class="pick-conditional-tag">Conditional</span>' : '',
        ].filter(Boolean).join('');
        const showDetail = isProtected || pickType === 'conditional';
        const detailText = pickType === 'conditional'
          ? (pick.detail || 'No condition details')
          : (pick.detail || 'No protection details');
        const ownerTheme = TEAM_THEMES[owner] || { primary: '#0f766e', secondary: '#99f6e4' };
        const ownerPrimaryRgb = hexToRgb(ownerTheme.primary);
        const ownerSecondaryRgb = hexToRgb(ownerTheme.secondary);
        const card = document.createElement('article');
        card.className = 'draft-pick-card';
        if (isRestricted) card.classList.add('draft-pick-card--restricted');
        if (isProtected) card.classList.add('draft-pick-card--protected');
        if (pickType === 'sold') card.classList.add('draft-pick-card--sold');
        if (pickType === 'conditional') card.classList.add('draft-pick-card--conditional');
        card.style.setProperty('--pick-primary-rgb', `${ownerPrimaryRgb.r}, ${ownerPrimaryRgb.g}, ${ownerPrimaryRgb.b}`);
        card.style.setProperty('--pick-secondary-rgb', `${ownerSecondaryRgb.r}, ${ownerSecondaryRgb.g}, ${ownerSecondaryRgb.b}`);
        if (showDetail) card.tabIndex = 0;
        card.innerHTML = `
          <div class="pick-card-logo-wrap">
            <span class="pick-owner-fallback">${owner || 'N/A'}</span>
            <img class="pick-owner-logo" alt="${owner || ''} logo">
          </div>
          <div class="pick-card-meta">
            <div class="pick-card-title">${title}</div>
            <div class="pick-card-subtitle">${escapeHtml(subtitle)}</div>
            ${badgesHtml ? `<div class="pick-card-badges">${badgesHtml}</div>` : ''}
          </div>
          ${showDetail ? `<div class="pick-detail">${escapeHtml(detailText)}</div>` : ''}
        `;
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

        if (isProtected) {
          card.addEventListener('click', () => {
            card.classList.toggle('show-detail');
          });
        }
        grid.appendChild(card);
      });

    seasonWrap.appendChild(grid);
    board.appendChild(seasonWrap);
  });
}

function renderDeadContracts() {
  const tbody = document.querySelector('#deadContractsTable tbody');
  tbody.innerHTML = '';

  applySeasonColumnVisibility();
  const seasons = visibleSeasonYears();
  const rows = sortedRows(
    (state.teamData.dead_contracts || []).filter((d) => seasons.some((season) => hasSeasonCellValue(d, season))),
    state.sort.dead_contracts,
  );
  rows.forEach((d) => {
    const tr = document.createElement('tr');
    const typePill = deadTypePillHtml(d.dead_type);
    const exclusionPills = deadExclusionPillsHtml(d);
    tr.innerHTML = `
      <td colspan="3" class="dead-contract-meta-cell">
        <div class="player-cell dead-contract-meta">
          <span class="player-name">${escapeHtml(d.label || '')}</span>
          <span class="player-tags">
            ${typePill}
            ${exclusionPills}
          </span>
        </div>
      </td>
      ${seasons.map((season) => `<td>${salaryCellHtml(d, season, true)}</td>`).join('')}
    `;
    tbody.appendChild(tr);
  });
}

function renderExceptions() {
  const tbody = document.querySelector('#exceptionsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  const rows = sortedRows(
    (state.teamData.assets || []).filter((a) => a.asset_type === 'exception' && !isAssetBeforeSelectedSeason(a)),
    state.sort.exceptions,
  );

  rows.forEach((item) => {
    const tr = document.createElement('tr');
    const hasDetail = Boolean(String(item.detail || '').trim());
    const showTypeTag = String(item.exception_type || '').trim() === 'Excepción de traspaso';
    if (hasDetail) {
      tr.classList.add('exception-row', 'has-detail');
      tr.tabIndex = 0;
    }
    tr.innerHTML = `
      <td colspan="3" class="dead-contract-meta-cell exception-meta-cell">
        <div class="player-cell dead-contract-meta exception-meta">
          <span class="player-name">${escapeHtml(item.label || '')}</span>
          ${hasDetail ? '<span class="exception-detail-icon" aria-hidden="true" title="Has details">!</span>' : ''}
          <span class="player-tags">
            ${showTypeTag ? `<span class="type-pill exception-type-pill">${escapeHtml(item.exception_type)}</span>` : ''}
          </span>
        </div>
        ${hasDetail ? `<div class="exception-detail-pop">${escapeHtml(item.detail || '')}</div>` : ''}
      </td>
      <td>${item.amount_num != null ? `<div class="salary-chip"><span class="salary-chip-main">${formatDots(item.amount_num)}</span></div>` : (item.amount_text || '')}</td>
    `;
    if (hasDetail) {
      tr.addEventListener('click', () => {
        tr.classList.toggle('show-detail');
      });
    }
    tbody.appendChild(tr);
  });
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
    tr.innerHTML = `
      <td>
        <div class="player-cell">
          <span class="player-name">${escapeHtml(item.label || '')}</span>
        </div>
      </td>
      <td class="details-cell">${escapeHtml(item.detail || '')}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadTeam(code) {
  const data = await api(`/api/teams/${code}`);
  state.teamCode = code;
  state.teamData = data;
  setTeamInUrl(code);
  try {
    window.localStorage.setItem(LAST_TEAM_STORAGE_KEY, code);
  } catch {
    // ignore localStorage errors
  }
  applyTeamTheme(code);
  setViewMode('team');
  renderSeasonViewControl();
  renderTeamStrip();
  renderMobileTeamGrid();
  renderCards();
  renderPlayers();
  renderDeadContracts();
  renderExceptions();
  renderAssets();
  renderPlayerRights();
  renderImportantFigures();
  renderGmTimelineSection();
}

async function fetchTrackerRowsFallback() {
  const rows = await Promise.all(state.teams.map(async (t) => {
    const data = await api(`/api/teams/${t.code}`);
    const s = data.summary || {};
    const draftCounts = draftPickCountsFromAssets(data.assets || []);
    return {
      team_code: t.code,
      team_name: t.name,
      cap_total: Number(s.cap_figure || 0),
      gasto_total: Number(s.payroll || 0),
      espacio_cap: Number(s.room_to_cap || 0),
      espacio_luxury: Number(s.room_to_luxury || 0),
      espacio_1er_apron: Number(s.room_to_first_apron || 0),
      espacio_2do_apron: Number(s.room_to_second_apron || 0),
      roster_standard_count: Number(s.roster_standard_count || rosterCountFromPlayers(data.players || []).standard),
      roster_two_way_count: Number(s.roster_two_way_count || rosterCountFromPlayers(data.players || []).twoWay),
      draft_first_count: draftCounts.first,
      draft_second_count: draftCounts.second,
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
  setTeamInUrl(null);
  try {
    window.localStorage.removeItem(LAST_TEAM_STORAGE_KEY);
  } catch {
    // ignore localStorage errors
  }
  applyTeamTheme('');
  setViewMode('tracker');
  setPageHeading('ANBA League Tracker', '');
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  renderTracker();
  renderImportantFigures();
}

async function loadFreeAgents() {
  const res = await api('/api/free-agents');
  state.freeAgents = res.free_agents || [];
  state.teamCode = null;
  state.teamData = null;
  setTeamInUrl(null);
  try {
    window.localStorage.removeItem(LAST_TEAM_STORAGE_KEY);
  } catch {
    // ignore localStorage errors
  }
  applyTeamTheme('');
  setViewMode('free-agents');
  setPageHeading('Free agents', '');
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  renderFreeAgents();
}

async function loadDraftOrder() {
  const res = await api('/api/draft-order');
  state.draftOrder = {
    draft_year: res.draft_year || currentSeasonStart() + 1,
    draft_order: res.draft_order || [],
  };
  state.teamCode = null;
  state.teamData = null;
  setTeamInUrl(null);
  try {
    window.localStorage.removeItem(LAST_TEAM_STORAGE_KEY);
  } catch {
    // ignore localStorage errors
  }
  applyTeamTheme('');
  setViewMode('draft-order');
  setPageHeading('Draft', `${state.draftOrder.draft_year} order of selection`);
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  renderDraftOrder();
}

function normalizeLocatorText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function draftPickSearchRound(asset) {
  const roundRaw = String(asset?.draft_round || '').trim().toLowerCase();
  if (roundRaw.includes('2')) return '2nd';
  if (roundRaw.includes('1')) return '1st';
  const label = String(asset?.label || '').toLowerCase();
  return label.includes('2') ? '2nd' : '1st';
}

function teamCodeFromAssetLabel(label) {
  const upper = String(label || '').toUpperCase();
  return (state.teams || []).map((team) => team.code).find((code) => {
    return new RegExp(`\\b${code}\\b`).test(upper);
  }) || null;
}

function draftPickOriginalOwner(asset, teamCode) {
  const type = String(asset?.draft_pick_type || '').trim().toLowerCase();
  if (type === 'acquired') {
    return String(asset?.original_owner || teamCodeFromAssetLabel(asset?.label) || teamCode || '').toUpperCase();
  }
  if (type === 'conditional') {
    return parseDraftConditionalTeams(asset?.draft_pick_conditional_teams)[0]
      || String(teamCodeFromAssetLabel(asset?.label) || teamCode || '').toUpperCase();
  }
  return String(teamCodeFromAssetLabel(asset?.label) || teamCode || '').toUpperCase();
}

function locatorFallbackDraftYears() {
  const start = currentSeasonStart() + 1;
  return Array.from({ length: SEASON_WINDOW_SIZE }, (_, idx) => start + idx);
}

function populateLocatorDraftControls() {
  const ownerSelect = document.getElementById('locatorDraftOwner');
  const yearSelect = document.getElementById('locatorDraftYear');
  if (!ownerSelect || !yearSelect) return;
  const selectedOwner = ownerSelect.value;
  const selectedYear = yearSelect.value;
  ownerSelect.innerHTML = [
    '<option value="">Original owner</option>',
    ...state.teams.map((team) => `<option value="${team.code}">${team.code} - ${escapeHtml(team.name || team.code)}</option>`),
  ].join('');
  if (selectedOwner) ownerSelect.value = selectedOwner;
  const indexedYears = state.locator.index
    ? Array.from(new Set(state.locator.index.draftPicks.map((pick) => Number(pick.year)).filter(Number.isFinite))).sort((a, b) => a - b)
    : [];
  const years = indexedYears.length ? indexedYears : locatorFallbackDraftYears();
  yearSelect.innerHTML = [
    '<option value="">Year</option>',
    ...years.map((year) => `<option value="${year}">${year}</option>`),
  ].join('');
  if (selectedYear && years.includes(Number(selectedYear))) yearSelect.value = selectedYear;
}

async function ensureLocatorIndex() {
  if (state.locator.index) return state.locator.index;
  if (state.locator.loading) {
    while (state.locator.loading) {
      await new Promise((resolve) => setTimeout(resolve, 80));
    }
    return state.locator.index;
  }
  state.locator.loading = true;
  const results = document.getElementById('locatorResults');
  if (results) results.innerHTML = '<div class="locator-empty">Loading...</div>';
  try {
    const [teamDataRows, freeAgentsRes] = await Promise.all([
      Promise.all(state.teams.map(async (team) => {
        const data = state.teamCode === team.code && state.teamData ? state.teamData : await api(`/api/teams/${team.code}`);
        return { team, data };
      })),
      api('/api/free-agents').catch(() => ({ free_agents: [] })),
    ]);
    const playerEntries = [];
    const draftPicks = [];
    teamDataRows.forEach(({ team, data }) => {
      const teamCode = team.code;
      const teamName = team.name || teamCode;
      (data.players || []).forEach((player) => {
        if (!String(player.name || '').trim()) return;
        playerEntries.push({
          id: `player-${player.id}`,
          name: player.name,
          team_code: teamCode,
          team_name: teamName,
          source: 'Roster',
          section_id: 'rosterSection',
        });
      });
      (data.dead_contracts || []).forEach((item) => {
        if (!String(item.label || '').trim()) return;
        playerEntries.push({
          id: `dead-${item.id}`,
          name: item.label,
          team_code: teamCode,
          team_name: teamName,
          source: 'Dead contract',
          section_id: 'deadContractsSection',
        });
      });
      (data.assets || []).forEach((asset) => {
        if (asset.asset_type === 'player_right' && String(asset.label || '').trim()) {
          playerEntries.push({
            id: `right-${asset.id}`,
            name: asset.label,
            team_code: teamCode,
            team_name: teamName,
            source: 'Player right',
            section_id: 'playerRightsSection',
          });
        }
        if (asset.asset_type === 'exception' && String(asset.label || '').trim()) {
          playerEntries.push({
            id: `exception-${asset.id}`,
            name: asset.label,
            team_code: teamCode,
            team_name: teamName,
            source: 'Exception',
            section_id: 'exceptionsSection',
          });
        }
        if (asset.asset_type === 'draft_pick') {
          const year = Number(asset.year);
          if (!Number.isFinite(year)) return;
          const pickType = String(asset.draft_pick_type || 'own').trim().toLowerCase() || 'own';
          const owners = pickType === 'conditional'
            ? parseDraftConditionalTeams(asset.draft_pick_conditional_teams)
            : [draftPickOriginalOwner(asset, teamCode)];
          (owners.length ? owners : [draftPickOriginalOwner(asset, teamCode)]).forEach((owner) => {
            draftPicks.push({
            id: asset.id,
            team_code: teamCode,
            team_name: teamName,
            label: asset.label || `${draftPickSearchRound(asset)} pick`,
            owner,
            round: draftPickSearchRound(asset),
            year,
            pick_type: pickType,
          });
          });
        }
      });
    });
    (freeAgentsRes.free_agents || []).forEach((agent) => {
      if (!String(agent.name || '').trim()) return;
      playerEntries.push({
        id: `free-agent-${agent.id}`,
        name: agent.name,
        team_code: '',
        team_name: 'Free agents',
        source: 'Free agent',
        section_id: 'freeAgentsSection',
        view_mode: 'free-agents',
      });
    });
    state.locator.index = { playerEntries, draftPicks };
    populateLocatorDraftControls();
    renderLocatorPlayerResults();
    return state.locator.index;
  } finally {
    state.locator.loading = false;
  }
}

function renderLocatorPlayerResults() {
  const input = document.getElementById('locatorSearchInput');
  const results = document.getElementById('locatorResults');
  if (!input || !results) return;
  const query = normalizeLocatorText(input.value);
  if (!query) {
    results.innerHTML = '';
    return;
  }
  if (!state.locator.index) {
    results.innerHTML = '<div class="locator-empty">Loading...</div>';
    return;
  }
  const matches = state.locator.index.playerEntries
    .filter((entry) => normalizeLocatorText(entry.name).includes(query))
    .sort((a, b) => {
      const aName = normalizeLocatorText(a.name);
      const bName = normalizeLocatorText(b.name);
      const aStarts = aName.startsWith(query) ? 0 : 1;
      const bStarts = bName.startsWith(query) ? 0 : 1;
      if (aStarts !== bStarts) return aStarts - bStarts;
      return aName.localeCompare(bName);
    })
    .slice(0, 24);
  if (!matches.length) {
    results.innerHTML = '<div class="locator-empty">No matches</div>';
    return;
  }
  results.innerHTML = matches.map((entry, idx) => `
    <button type="button" class="locator-result" data-result-index="${idx}">
      <span class="locator-result-name">${escapeHtml(entry.name)}</span>
      <span class="locator-result-meta">${escapeHtml(entry.team_code || entry.team_name || '')} · ${escapeHtml(entry.source)}</span>
    </button>
  `).join('');
  results.querySelectorAll('[data-result-index]').forEach((btn) => {
    const entry = matches[Number(btn.dataset.resultIndex)];
    btn.addEventListener('click', () => {
      void goToLocatorEntry(entry);
    });
  });
}

function closeLocatorModal() {
  const modal = document.getElementById('locatorModal');
  if (!modal) return;
  modal.classList.add('section-hidden');
}

function openLocatorModal() {
  const modal = document.getElementById('locatorModal');
  const input = document.getElementById('locatorSearchInput');
  if (!modal || !input) return;
  populateLocatorDraftControls();
  modal.classList.remove('section-hidden');
  renderLocatorPlayerResults();
  requestAnimationFrame(() => input.focus());
  void ensureLocatorIndex().catch((err) => {
    const results = document.getElementById('locatorResults');
    if (results) results.innerHTML = `<div class="locator-empty">${escapeHtml(err.message || 'Search failed')}</div>`;
  });
}

async function goToLocatorEntry(entry) {
  if (!entry) return;
  closeLocatorModal();
  if (entry.view_mode === 'free-agents') {
    await loadFreeAgents();
    scrollToTeamSection('freeAgentsSection');
    return;
  }
  await loadTeam(entry.team_code);
  scrollToTeamSection(entry.section_id || 'rosterSection');
}

function findDraftPickLocatorMatch(owner, round, year) {
  const index = state.locator.index;
  if (!index) return null;
  const matches = index.draftPicks
    .filter((pick) => pick.owner === owner && pick.round === round && Number(pick.year) === Number(year))
    .sort((a, b) => {
      const aSold = a.pick_type === 'sold' ? 1 : 0;
      const bSold = b.pick_type === 'sold' ? 1 : 0;
      if (aSold !== bSold) return aSold - bSold;
      return String(a.team_code).localeCompare(String(b.team_code));
    });
  return matches[0] || null;
}

async function goToDraftPickLocatorMatch(match) {
  if (!match) return;
  state.ui.seasonViewStart = normalizeSeasonViewStart(Number(match.year) - 1);
  closeLocatorModal();
  await loadTeam(match.team_code);
  scrollToTeamSection('assetsSection');
}

async function submitDraftPickLocator() {
  const owner = String(document.getElementById('locatorDraftOwner')?.value || '').trim().toUpperCase();
  const round = String(document.getElementById('locatorDraftRound')?.value || '1st').trim();
  const year = Number(document.getElementById('locatorDraftYear')?.value || 0);
  const status = document.getElementById('locatorDraftStatus');
  if (!owner || !round || !Number.isFinite(year) || year <= 0) {
    if (status) status.textContent = 'Select owner, round, and year.';
    return;
  }
  if (status) status.textContent = state.locator.index ? '' : 'Loading...';
  await ensureLocatorIndex();
  const match = findDraftPickLocatorMatch(owner, round, year);
  if (!match) {
    if (status) status.textContent = 'No matching pick found.';
    return;
  }
  if (status) status.textContent = '';
  await goToDraftPickLocatorMatch(match);
}

function setupLocatorModal() {
  const openBtn = document.getElementById('openLocatorBtn');
  const mobileBtn = document.getElementById('mobileLocatorBtn');
  const closeBtn = document.getElementById('locatorCloseBtn');
  const modal = document.getElementById('locatorModal');
  const input = document.getElementById('locatorSearchInput');
  const draftGoBtn = document.getElementById('locatorDraftGoBtn');
  if (openBtn) openBtn.addEventListener('click', () => openLocatorModal());
  if (mobileBtn) {
    mobileBtn.addEventListener('click', () => {
      closeMobileSidebar();
      openLocatorModal();
    });
  }
  if (closeBtn) closeBtn.addEventListener('click', () => closeLocatorModal());
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeLocatorModal();
    });
  }
  if (input) {
    input.addEventListener('input', () => {
      renderLocatorPlayerResults();
      if (!state.locator.index) void ensureLocatorIndex();
    });
  }
  if (draftGoBtn) {
    draftGoBtn.addEventListener('click', () => {
      void submitDraftPickLocator().catch((err) => {
        const status = document.getElementById('locatorDraftStatus');
        if (status) status.textContent = err.message || 'Draft pick search failed.';
      });
    });
  }
}

function setupMobileNav() {
  const menuBtn = document.getElementById('mobileMenuBtn');
  const closeBtn = document.getElementById('mobileSidebarCloseBtn');
  const backdrop = document.getElementById('mobileSidebarBackdrop');
  const trackerBtn = document.getElementById('mobileTrackerBtn');
  const draftBtn = document.getElementById('mobileDraftBtn');
  const freeAgentsBtn = document.getElementById('mobileFreeAgentsBtn');
  const tradeMachineBtn = document.getElementById('mobileTradeMachineBtn');
  const mobileLogoutBtn = document.getElementById('mobileLogoutBtn');
  const infoBtn = document.getElementById('mobileInfoBtn');
  const infoCloseBtn = document.getElementById('mobileInfoCloseBtn');
  const infoBackdrop = document.getElementById('mobileInfoBackdrop');
  const moveLogCloseBtn = document.getElementById('moveLogCloseBtn');
  const moveLogBackdrop = document.getElementById('moveLogBackdrop');

  if (menuBtn) menuBtn.addEventListener('click', () => openMobileSidebar());
  if (closeBtn) closeBtn.addEventListener('click', () => closeMobileSidebar());
  if (backdrop) {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeMobileSidebar();
    });
  }
  if (trackerBtn) {
    trackerBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadTracker();
    });
  }
  if (draftBtn) {
    draftBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadDraftOrder();
    });
  }
  if (freeAgentsBtn) {
    freeAgentsBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadFreeAgents();
    });
  }
  if (tradeMachineBtn) {
    tradeMachineBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadTradeMachine();
    });
  }
  if (mobileLogoutBtn) {
    mobileLogoutBtn.addEventListener('click', async () => {
      await api('/api/auth/logout', { method: 'POST', body: '{}' });
      window.location.href = '/';
    });
  }
  if (infoBtn) infoBtn.addEventListener('click', () => openMobileInfo());
  if (infoCloseBtn) infoCloseBtn.addEventListener('click', () => closeMobileInfo());
  if (infoBackdrop) {
    infoBackdrop.addEventListener('click', (e) => {
      if (e.target === infoBackdrop) closeMobileInfo();
    });
  }
  if (moveLogCloseBtn) moveLogCloseBtn.addEventListener('click', () => closeMoveLog());
  if (moveLogBackdrop) {
    moveLogBackdrop.addEventListener('click', (e) => {
      if (e.target === moveLogBackdrop) closeMoveLog();
    });
  }
}

async function init() {
  ensurePlayerMetaModal();
  state.auth = await api('/api/auth/status');
  state.csrfToken = state.auth?.csrf_token || null;
  const settingsRes = await api('/api/settings');
  state.settings = settingsRes.settings || state.settings;
  state.ui.seasonViewStart = normalizeSeasonViewStart(readInitialSeasonStart());
  renderAuthControls();

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST', body: '{}' });
    window.location.href = '/';
  });
  document.getElementById('trackerHomeBtn').addEventListener('click', async () => {
    await loadTracker();
  });
  document.getElementById('draftHomeBtn').addEventListener('click', async () => {
    await loadDraftOrder();
  });
  document.getElementById('freeAgentsHomeBtn').addEventListener('click', async () => {
    await loadFreeAgents();
  });

  const teamsRes = await api('/api/teams');
  state.teams = teamsRes.teams;
  setupSorting();
  setupLocatorModal();
  setupMobileNav();
  setupTradeMachineControls();
  setupTeamTabs();
  setupRosterViewControl();
  setupSeasonViewControl();
  setupRosterFilters();
  let savedRosterView = null;
  try {
    savedRosterView = window.localStorage.getItem('anba_roster_view');
  } catch {
    savedRosterView = null;
  }
  const initialRosterView = window.matchMedia('(max-width: 720px)').matches
    ? preferredRosterView()
    : (savedRosterView || preferredRosterView());
  setRosterView(initialRosterView, false);
  renderTeamStrip();
  renderMobileTeamGrid();
  const initialTeam = readInitialTeamCode();
  if (initialTeam && state.teams.some((t) => t.code === initialTeam)) {
    await loadTeam(initialTeam);
  } else {
    await loadTracker();
  }
}

init().catch((err) => {
  console.error(err);
  alert(err.message);
});
