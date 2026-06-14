const MOVE_LIMIT_PRE30 = 20;
const MOVE_LIMIT_POST30 = 4;

const state = {
  teams: [],
  trackerRows: [],
  trackerEconomyRows: [],
  trackerEconomySeasons: [],
  economySettingsRows: [],
  economySettingsSeasons: [],
  economySettingsSeason: null,
  adminUsers: [],
  gmOptionRequests: [],
  freeAgents: [],
  draftOrder: {
    draft_year: null,
    draft_order: [],
  },
  teamCode: null,
  teamData: null,
  csrfToken: null,
  settings: {
    salary_cap_2025: 154647000,
    current_year: 2025,
    first_apron: 195945000,
    second_apron: 207824000,
    cash_limit_total: 0,
    trade_move_limit_pre30: MOVE_LIMIT_PRE30,
    trade_move_limit_post30: MOVE_LIMIT_POST30,
    trade_move_phase: 'pre30',
    luxury_cap: 187896105,
    minimum_cap_allowed: 139182300,
    roster_standard_min: 14,
    roster_standard_max: 15,
    roster_standard_offseason_max: 18,
    roster_two_way_min: 0,
    roster_two_way_max: 3,
    free_agency_mode: false,
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
    activeTrackerTab: 'general',
    activeTeamTab: 'economy',
    addingPlayer: false,
    addingDeadContract: false,
    addingDraftPick: false,
    addingDraftOrderRound: null,
    addingPlayerRight: false,
    addingFreeAgent: false,
    signingFreeAgentId: null,
    gmTimelineEntries: [],
    gmTimelineSvg: '',
    figuresSeasonStart: null,
    trackerEconomySeason: null,
  },
  sort: {
    tracker: { key: 'team_code', dir: 'asc' },
    trackerEconomy: { key: 'balance', dir: 'desc' },
    economySettings: { key: 'team_code', dir: 'asc' },
    players: { key: 'position', dir: 'asc' },
    dead_contracts: { key: 'label', dir: 'asc' },
    exceptions: { key: 'label', dir: 'asc' },
    player_rights: { key: 'label', dir: 'asc' },
    free_agents: { key: 'name', dir: 'asc' },
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
const POSITION_ORDER = { PG: 1, SG: 2, SF: 3, PF: 4, C: 5, TW: 6 };
const ALL_SEASONS = [2025, 2026, 2027, 2028, 2029, 2030];
const TAXPAYER_MLE_BASE_AMOUNT = 5_500_007;
const TAXPAYER_MLE_BASE_CAP = 154_647_000;
const MINIMUM_SALARY_BASE_SEASON = 2025;
const MINIMUM_SALARY_BASE_CAP = 154_647_000;
const TWO_WAY_MINIMUM_BASE = 636_435;
const MINIMUM_SALARY_CONTRACT_YEARS = [1, 2, 3, 4, 5];
const MINIMUM_SALARY_BASE_ROWS = [
  { experience: 0, label: '0', salaries: [1_272_870, null, null, null, null] },
  { experience: 1, label: '1', salaries: [2_048_494, 2_150_917, null, null, null] },
  { experience: 2, label: '2', salaries: [2_296_274, 2_411_090, 2_525_901, null, null] },
  { experience: 3, label: '3', salaries: [2_378_870, 2_497_812, 2_616_754, 2_735_698, null] },
  { experience: 4, label: '4', salaries: [2_461_463, 2_584_539, 2_707_612, 2_830_685, 2_953_760] },
  { experience: 5, label: '5', salaries: [2_667_947, 2_801_346, 2_934_742, 3_068_140, 3_201_538] },
  { experience: 6, label: '6', salaries: [2_874_436, 3_018_158, 3_161_876, 3_305_598, 3_449_321] },
  { experience: 7, label: '7', salaries: [3_080_921, 3_234_968, 3_389_014, 3_543_059, 3_697_107] },
  { experience: 8, label: '8', salaries: [3_287_409, 3_451_779, 3_616_151, 3_780_524, 3_944_896] },
  { experience: 9, label: '9', salaries: [3_493_898, 3_659_836, 3_825_773, 3_991_710, 4_157_649] },
  { experience: 10, label: '10+', salaries: [3_634_153, 3_815_861, 3_997_570, 4_179_277, 4_360_985] },
];
const TEAM_TABS = [
  {
    id: 'economy',
    sections: ['rosterSection', 'deadContractsSection', 'assetsSection', 'playerRightsSection'],
  },
  {
    id: 'general',
    sections: ['teamMeta', 'adminTeamControlsSection', 'importantFiguresSection', 'gmTimelineSection'],
  },
  {
    id: 'draft',
    sections: ['draftAssetsSection'],
  },
];

function typeClass(value) {
  const v = String(value || '').toLowerCase().replaceAll('(', '').replaceAll(')', '').replaceAll('/', '').replaceAll(' ', '');
  return v ? `type-pill--${v}` : '';
}

function contractOptionClass(value) {
  const v = String(value || '').toUpperCase();
  if (!v) return '';
  return `salary-option--${v.toLowerCase()}`;
}

function contractOptionActionMessage(teamCode, playerName, season, optionValue, action) {
  const team = String(teamCode || state.teamCode || '').toUpperCase();
  const player = playerName || 'this player';
  const option = String(optionValue || '').toUpperCase();
  const verb = action === 'accepted' ? 'aceptar' : 'rechazar';
  if (option === 'TO') {
    const suffix = action === 'accepted' ? ' La cantidad quedará garantizada y se retirará la marca TO de la celda.' : '';
    return `Confirmar que ${team} va a ${verb} su team option sobre ${player} para ${seasonLabel(season)}.${suffix}`;
  }
  if (option === 'PO') {
    const suffix = action === 'accepted' ? ' La cantidad quedará garantizada y se retirará la marca PO de la celda.' : '';
    return `Confirmar que ${player} va a ${verb} su player option con ${team} para ${seasonLabel(season)}.${suffix}`;
  }
  if (option === 'QO') {
    return `Confirmar que ${team} va a ${verb} la qualifying offer de ${player} para ${seasonLabel(season)}.`;
  }
  if (option === 'GAP') {
    return `Confirmar que ${team} va a ${verb} la opción GAP de ${player} para ${seasonLabel(season)}.`;
  }
  return `Confirmar que ${team} va a ${verb} la opción ${option} de ${player} para ${seasonLabel(season)}.`;
}

function salaryTextTagClass(value) {
  const v = String(value || '').trim().toUpperCase();
  if (v === 'FB') return 'salary-text-tag--fb';
  if (v === 'EB') return 'salary-text-tag--eb';
  if (v === 'NB') return 'salary-text-tag--nb';
  return '';
}

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

function clearSalaryInfoPopover(btn) {
  const pop = btn?.querySelector?.('.salary-info-pop');
  if (!pop) return;
  pop.classList.remove('is-fixed');
  pop.style.left = '';
  pop.style.top = '';
  pop.style.visibility = '';
}

function positionSalaryInfoPopover(btn) {
  const pop = btn?.querySelector?.('.salary-info-pop');
  if (!pop) return;
  pop.classList.add('is-fixed');
  pop.style.visibility = 'hidden';
  pop.style.left = '0px';
  pop.style.top = '0px';

  const btnRect = btn.getBoundingClientRect();
  const popRect = pop.getBoundingClientRect();
  const gap = 8;
  const width = popRect.width || 240;
  const height = popRect.height || 44;
  const maxLeft = Math.max(8, window.innerWidth - width - 8);
  let left = btnRect.left + (btnRect.width / 2) - (width / 2);
  left = Math.max(8, Math.min(left, maxLeft));
  let top = btnRect.bottom + gap;
  if (top + height > window.innerHeight - 8) {
    top = btnRect.top - height - gap;
  }
  top = Math.max(8, top);

  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
  pop.style.visibility = '';
}

function closeSalaryInfoPopovers(except = null) {
  document.querySelectorAll('.salary-info-button.show-detail').forEach((btn) => {
    if (btn === except) return;
    btn.classList.remove('show-detail');
    clearSalaryInfoPopover(btn);
  });
}

function setupSalaryInfoGlobalHandlers() {
  if (window.__salaryInfoGlobalHandlersBound) return;
  window.__salaryInfoGlobalHandlersBound = true;
  document.addEventListener('click', () => closeSalaryInfoPopovers());
  const repositionActive = () => {
    document.querySelectorAll('.salary-info-button.show-detail').forEach(positionSalaryInfoPopover);
  };
  window.addEventListener('resize', repositionActive);
  window.addEventListener('scroll', repositionActive, true);
}

function bindSalaryInfoToggles(root) {
  if (!root) return;
  setupSalaryInfoGlobalHandlers();
  root.querySelectorAll('.salary-info-button').forEach((btn) => {
    btn.addEventListener('mouseenter', () => positionSalaryInfoPopover(btn));
    btn.addEventListener('focus', () => positionSalaryInfoPopover(btn));
    btn.addEventListener('mouseleave', () => {
      if (!btn.classList.contains('show-detail')) clearSalaryInfoPopover(btn);
    });
    btn.addEventListener('blur', () => {
      if (!btn.classList.contains('show-detail')) clearSalaryInfoPopover(btn);
    });
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const willShow = !btn.classList.contains('show-detail');
      closeSalaryInfoPopovers(btn);
      btn.classList.toggle('show-detail', willShow);
      if (willShow) {
        positionSalaryInfoPopover(btn);
      } else {
        clearSalaryInfoPopover(btn);
      }
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

function seasonSlashLabel(startYear) {
  return seasonLabel(startYear).replace('-', '/');
}

function currentSeasonStart() {
  const currentYear = Number(state.settings.current_year || 2025);
  return Number.isInteger(currentYear) ? currentYear : 2025;
}

function availableFiguresSeasonStarts() {
  const currentYear = currentSeasonStart();
  return Array.from({ length: 6 }, (_, idx) => currentYear + idx);
}

function normalizeFiguresSeasonStart(value) {
  const seasons = availableFiguresSeasonStarts();
  const requested = Number(value);
  return seasons.includes(requested) ? requested : seasons[0];
}

function selectedFiguresSeasonStart() {
  const normalized = normalizeFiguresSeasonStart(state.ui.figuresSeasonStart ?? currentSeasonStart());
  state.ui.figuresSeasonStart = normalized;
  return normalized;
}

function trackerEconomySeasonOptions() {
  const seasons = new Set(
    (state.trackerEconomySeasons || [])
      .map((season) => Number(season))
      .filter((season) => Number.isInteger(season) && season >= 2000 && season <= 2100)
  );
  seasons.add(currentSeasonStart());
  seasons.add(2025);
  return Array.from(seasons).sort((a, b) => a - b);
}

function normalizeTrackerEconomySeason(value) {
  const options = trackerEconomySeasonOptions();
  const requested = Number(value);
  if (options.includes(requested)) return requested;
  const current = currentSeasonStart();
  return options.includes(current) ? current : (options[0] || 2025);
}

function selectedTrackerEconomySeason() {
  const normalized = normalizeTrackerEconomySeason(state.ui.trackerEconomySeason);
  state.ui.trackerEconomySeason = normalized;
  return normalized;
}

function freeAgencyModeActive() {
  return boolValue(state.settings.free_agency_mode);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function confirmWithDiscordNotification({
  title,
  message,
  confirmLabel = 'Confirmar',
  notifyLabel = 'Enviar notificación a Discord',
  defaultNotify = true,
  imageLabel = 'Generar imagen con OpenAI',
  defaultGenerateImage = true,
  danger = false,
} = {}) {
  return new Promise((resolve) => {
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop notification-confirm-backdrop';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.innerHTML = `
      <div class="modal-card notification-confirm-modal">
        <div class="modal-header">
          <h2>${escapeHtml(title || 'Confirmar acción')}</h2>
        </div>
        <p class="notification-confirm-message">${escapeHtml(message || '').replaceAll('\n', '<br>')}</p>
        <label class="notify-confirm-toggle">
          <input type="checkbox" data-role="notify-discord" ${defaultNotify ? 'checked' : ''}>
          <span>${escapeHtml(notifyLabel)}</span>
        </label>
        <label class="notify-confirm-toggle">
          <input type="checkbox" data-role="generate-discord-image" ${(defaultNotify && defaultGenerateImage) ? 'checked' : ''} ${defaultNotify ? '' : 'disabled'}>
          <span>${escapeHtml(imageLabel)}</span>
        </label>
        <div class="notification-confirm-actions">
          <button type="button" data-action="cancel">Cancelar</button>
          <button type="button" data-action="confirm" class="${danger ? 'danger' : ''}">${escapeHtml(confirmLabel)}</button>
        </div>
      </div>
    `;

    const cleanup = (value) => {
      document.removeEventListener('keydown', onKeyDown);
      backdrop.remove();
      resolve(value);
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') cleanup({ confirmed: false, notifyDiscord: false, generateDiscordImage: false });
    };
    document.addEventListener('keydown', onKeyDown);
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) cleanup({ confirmed: false, notifyDiscord: false, generateDiscordImage: false });
    });
    backdrop.querySelector('[data-action="cancel"]').addEventListener('click', () => {
      cleanup({ confirmed: false, notifyDiscord: false, generateDiscordImage: false });
    });
    const notifyInput = backdrop.querySelector('[data-role="notify-discord"]');
    const imageInput = backdrop.querySelector('[data-role="generate-discord-image"]');
    notifyInput?.addEventListener('change', () => {
      const notifyEnabled = Boolean(notifyInput.checked);
      if (imageInput) {
        imageInput.disabled = !notifyEnabled;
        if (!notifyEnabled) imageInput.checked = false;
        else if (defaultGenerateImage) imageInput.checked = true;
      }
    });
    backdrop.querySelector('[data-action="confirm"]').addEventListener('click', () => {
      const notifyDiscord = Boolean(notifyInput?.checked);
      const generateDiscordImage = notifyDiscord && Boolean(imageInput?.checked);
      cleanup({ confirmed: true, notifyDiscord, generateDiscordImage });
    });
    document.body.appendChild(backdrop);
    backdrop.querySelector('[data-action="confirm"]')?.focus();
  });
}

function visibleSeasonYears() {
  const currentYear = currentSeasonStart();
  return ALL_SEASONS.filter((season) => season >= currentYear);
}

function salaryNumericValue(row, season) {
  const direct = row?.[`salary_${season}_num`];
  if (direct !== null && direct !== undefined && direct !== '' && Number.isFinite(Number(direct))) {
    return Number(direct);
  }
  return parseAmount(row?.[`salary_${season}_text`]) || 0;
}

function seasonSalaryTextCode(row, season) {
  return String(row?.[`salary_${season}_text`] || '').trim().toUpperCase();
}

function seasonOptionCode(row, season) {
  return String(row?.[`option_${season}`] || '').trim().toUpperCase();
}

function hasNumericSeasonSalary(row, season) {
  const direct = row?.[`salary_${season}_num`];
  if (direct !== null && direct !== undefined && direct !== '' && Number.isFinite(Number(direct))) return true;
  return parseAmount(row?.[`salary_${season}_text`]) !== null;
}

function isRestrictedRightsPlayer(player) {
  const rights = String(player?.bird_rights || '').trim().toUpperCase();
  return rights === 'R' || rights.startsWith('R(');
}

function capHoldTargetSeason() {
  return currentSeasonStart() + 1;
}

function pendingCapHold(shortLabel, message, options = {}) {
  const label = String(shortLabel || '').toUpperCase().startsWith('QO') ? 'QO TBD' : 'Hold TBD';
  return {
    active: true,
    displayable: true,
    amount: 0,
    displayAmount: options.displayAmount,
    pending: true,
    label,
    shortLabel,
    message,
  };
}

function calculatedCapHold(amount, shortLabel, message, options = {}) {
  return {
    active: true,
    displayable: true,
    amount: Math.round(Number(amount || 0)),
    displayAmount: options.displayAmount,
    pending: false,
    label: 'Cap hold',
    shortLabel,
    message,
  };
}

function birdCapHoldInfo(player, season, code) {
  const previousSalary = salaryNumericValue(player, season - 1);
  if (!previousSalary || previousSalary <= 0) {
    return pendingCapHold(`${code} hold`, 'Cap hold pendiente: falta salario anterior.');
  }
  if (code === 'NB') {
    const rights = String(player?.bird_rights || '').trim().toUpperCase();
    if (rights === 'MIN' || rights === 'TW' || salaryLooksLikeMinimum(previousSalary, season - 1)) {
      return calculatedCapHold(
        minimumSalaryForSeason(season, 2, 1),
        'NB hold',
        'Cap hold Non-Bird mínimo: mínimo de veterano de dos años.',
      );
    }
    return calculatedCapHold(previousSalary * 1.2, 'NB hold', 'Cap hold Non-Bird: 120% del salario anterior.');
  }
  if (code === 'EB') {
    return calculatedCapHold(previousSalary * 1.3, 'EB hold', 'Cap hold Early Bird: 130% del salario anterior.');
  }
  if (code === 'FB') {
    const averageSalary = averageSalaryForSeason(season - 1);
    if (!averageSalary) {
      return pendingCapHold('FB hold', 'Cap hold Full Bird pendiente: falta salario medio de la liga.');
    }
    const multiplier = previousSalary < averageSalary ? 1.9 : 1.5;
    return calculatedCapHold(
      previousSalary * multiplier,
      'FB hold',
      `Cap hold Full Bird: ${Math.round(multiplier * 100)}% del salario anterior.`,
    );
  }
  return null;
}

function capHoldInfo(player, season) {
  if (!freeAgencyModeActive() || Number(season) !== capHoldTargetSeason()) {
    return { active: false, displayable: false, amount: 0 };
  }

  const textCode = seasonSalaryTextCode(player, season);
  const optionCode = seasonOptionCode(player, season);
  const isQualifyingOffer = textCode === 'QO' || optionCode === 'QO';
  const birdCode = ['NB', 'EB', 'FB'].includes(textCode)
    ? textCode
    : (['NB', 'EB', 'FB'].includes(optionCode) ? optionCode : '');
  const qualifyingOfferValue = isQualifyingOffer ? salaryNumericValue(player, season) : 0;

  if (!isQualifyingOffer && hasNumericSeasonSalary(player, season)) {
    return { active: false, displayable: false, amount: 0 };
  }

  if (isTwoWayPlayer(player)) {
    if (!isQualifyingOffer) {
      return { active: false, displayable: false, amount: 0 };
    }
    const capHoldAmount = minimumSalaryForSeason(season, 1, 1);
    const details = [
      'Cap hold QO two-way: mínimo de veterano de un año.',
      qualifyingOfferValue > 0 ? `QO visible: ${formatDots(qualifyingOfferValue)}.` : '',
      `Cuenta CAP: ${formatDots(capHoldAmount)}.`,
    ].filter(Boolean).join(' ');
    return calculatedCapHold(
      capHoldAmount,
      'QO hold',
      details,
      { displayAmount: qualifyingOfferValue || undefined },
    );
  }

  if (isQualifyingOffer && isRestrictedRightsPlayer(player)) {
    const previousSalary = salaryNumericValue(player, season - 1);
    const averageSalary = averageSalaryForSeason(season - 1);
    if (!previousSalary || previousSalary <= 0) {
      return pendingCapHold(
        'QO hold',
        'Cap hold QO pendiente: falta salario anterior.',
        { displayAmount: qualifyingOfferValue || undefined },
      );
    }
    if (!averageSalary) {
      return pendingCapHold(
        'QO hold',
        'Cap hold QO pendiente: falta salario medio de la liga para aplicar 300% o 250%.',
        { displayAmount: qualifyingOfferValue || undefined },
      );
    }
    const multiplier = previousSalary < averageSalary ? 3 : 2.5;
    const capHoldAmount = Math.round(previousSalary * multiplier);
    const details = [
      `Cap hold QO: ${Math.round(multiplier * 100)}% del salario anterior.`,
      qualifyingOfferValue > 0 ? `QO visible: ${formatDots(qualifyingOfferValue)}.` : '',
      `Cuenta CAP: ${formatDots(capHoldAmount)}.`,
    ].filter(Boolean).join(' ');
    return calculatedCapHold(
      capHoldAmount,
      'QO hold',
      details,
      { displayAmount: qualifyingOfferValue || undefined },
    );
  }

  if (birdCode) {
    const info = birdCapHoldInfo(player, season, birdCode);
    if (info) return info;
  }

  if (isQualifyingOffer) {
    return pendingCapHold('QO hold', 'Cap hold QO pendiente: falta tipo Bird/NB/EB/FB para calcularlo.');
  }

  return { active: false, displayable: false, amount: 0 };
}

function salaryDisplayNumericValue(row, season) {
  const hold = capHoldInfo(row, season);
  if (hold.displayable && hold.amount > 0) return hold.amount;
  return salaryNumericValue(row, season);
}

function playerCapCountValue(player, season) {
  const hold = capHoldInfo(player, season);
  if (hold.displayable && hold.amount > 0) return hold.amount;
  if (isTwoWayPlayer(player)) return 0;
  return salaryNumericValue(player, season);
}

function playerApronCountValue(player, season) {
  const hold = capHoldInfo(player, season);
  if (hold.displayable) return 0;
  if (isTwoWayPlayer(player)) return 0;
  return salaryNumericValue(player, season);
}

function amountNumericValue(row) {
  const direct = row?.amount_num;
  if (direct !== null && direct !== undefined && direct !== '' && Number.isFinite(Number(direct))) {
    return Number(direct);
  }
  return parseAmount(row?.amount_text) || 0;
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
    if (count < limits.twoWayMin) return { key: 'under', label: `Bajo mínimo ${limits.twoWayMin}` };
    if (count > limits.twoWayMax) return { key: 'over', label: `Sobre máximo ${limits.twoWayMax}` };
    return { key: 'ok', label: `${limits.twoWayMin}-${limits.twoWayMax}` };
  }
  if (count < limits.standardMin) return { key: 'under', label: `Bajo mínimo ${limits.standardMin}` };
  if (count > limits.standardOffseasonMax) return { key: 'over', label: `Sobre máximo ${limits.standardOffseasonMax}` };
  if (count > limits.standardMax) return { key: 'offseason', label: `Solo offseason (${limits.standardOffseasonMax} max)` };
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

function trackerLuxuryTaxValueHtml(value) {
  const numeric = Number(value || 0);
  const className = numeric > 0 ? 'is-negative' : 'is-neutral';
  return `<span class="tracker-tax-value ${className}">${formatMoneyDots(numeric)}</span>`;
}

function trackerEconomyValueHtml(value) {
  const numeric = Number(value || 0);
  const className = numeric < 0 ? 'is-negative' : numeric > 0 ? 'is-positive' : 'is-neutral';
  return `<span class="tracker-space-value ${className}">${formatMoneyDots(numeric)}</span>`;
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
  return Array.from({ length: 6 }, (_, idx) => currentYear + idx);
}

function exceptionBalanceTotal(season) {
  if (season !== currentSeasonStart()) return 0;
  return (state.teamData?.assets || [])
    .filter((asset) => asset.asset_type === 'exception')
    .reduce((sum, asset) => sum + amountNumericValue(asset), 0);
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
  const capPlayerTotal = players.reduce((sum, player) => sum + playerCapCountValue(player, season), 0);
  const apronPlayerTotal = players.reduce((sum, player) => sum + playerApronCountValue(player, season), 0);
  const normalDeadCapTotal = deadContracts
    .filter((dead) => !isTwoWayDeadContract(dead) && !deadContractExcludedFromCap(dead))
    .reduce((sum, dead) => sum + salaryNumericValue(dead, season), 0);
  const deadGastoTotal = deadContracts
    .filter((dead) => !deadContractExcludedFromGasto(dead))
    .reduce((sum, dead) => sum + salaryNumericValue(dead, season), 0);
  const capTotal = capPlayerTotal + normalDeadCapTotal;
  const apronAccount = apronPlayerTotal + normalDeadCapTotal;
  const gastoTotal = playerTotal + deadGastoTotal;
  const salaryCap = capForSeason(season);
  const luxuryCap = luxuryCapForSeason(season);
  const luxuryOverage = Math.max(0, capTotal - luxuryCap);
  return {
    cap_total: capTotal,
    gasto_total: gastoTotal,
    apron_account: apronAccount,
    luxury_tax: luxuryTaxAmount(luxuryOverage, luxuryRepeaterForSeason(data, season)),
  };
}

function seasonBalances(season) {
  return teamSeasonBalances(state.teamData, season);
}

function displayBalanceSeason() {
  return freeAgencyModeActive() ? capHoldTargetSeason() : currentSeasonStart();
}

function summaryForBalanceSeason(data, season = displayBalanceSeason()) {
  const base = data?.summary || {};
  const balances = teamSeasonBalances(data, season);
  const salaryCap = capForSeason(season) || Number(base.salary_cap_2025 || 0);
  const luxuryCap = luxuryCapForSeason(season);
  const firstApron = firstApronForSeason(season) || Number(base.first_apron || 0);
  const secondApron = secondApronForSeason(season) || Number(base.second_apron || 0);
  return {
    ...base,
    current_year: season,
    cap_figure: balances.cap_total,
    payroll: balances.gasto_total,
    room_to_cap: salaryCap - balances.cap_total,
    room_to_luxury: luxuryCap - balances.cap_total,
    room_to_first_apron: firstApron - balances.apron_account,
    room_to_second_apron: secondApron - balances.apron_account,
  };
}

function capForSeason(season) {
  const direct = Number(state.settings[`salary_cap_${season}`]);
  if (Number.isFinite(direct) && direct > 0) return direct;
  return Number(state.settings.salary_cap_2025 || 0);
}

function firstApronForSeason(season) {
  const direct = Number(state.settings[`first_apron_${season}`]);
  if (Number.isFinite(direct) && direct > 0) return direct;
  return Number(state.settings.first_apron || 0);
}

function secondApronForSeason(season) {
  const direct = Number(state.settings[`second_apron_${season}`]);
  if (Number.isFinite(direct) && direct > 0) return direct;
  return Number(state.settings.second_apron || 0);
}

function luxuryCapForSeason(season) {
  return capForSeason(season) * 1.215;
}

function cashLimitForSeason(season) {
  return capForSeason(season) * 0.0515;
}

function averageSalaryForSeason(season) {
  const direct = Number(state.settings[`average_salary_${season}`]);
  return Number.isFinite(direct) && direct > 0 ? direct : 0;
}

function taxpayerMidLevelForSeason(season) {
  const cap = capForSeason(season);
  if (!cap) return 0;
  return TAXPAYER_MLE_BASE_AMOUNT * (cap / TAXPAYER_MLE_BASE_CAP);
}

function minimumSalaryScaleForSeason(season) {
  const cap = capForSeason(season);
  if (!cap) return 1;
  return cap / MINIMUM_SALARY_BASE_CAP;
}

function scaledMinimumSalary(value, season) {
  if (value === null || value === undefined) return null;
  return Math.round(Number(value) * minimumSalaryScaleForSeason(season));
}

function twoWayMinimumSalaryForSeason(season) {
  return scaledMinimumSalary(TWO_WAY_MINIMUM_BASE, season);
}

function minimumSalaryForSeason(season, experienceYears, contractYear = 1) {
  const cappedExperience = Math.max(0, Math.min(10, Number(experienceYears || 0)));
  const row = MINIMUM_SALARY_BASE_ROWS.find((item) => item.experience === cappedExperience);
  if (!row) return null;
  const yearIndex = Math.max(0, Math.min(MINIMUM_SALARY_CONTRACT_YEARS.length - 1, Number(contractYear || 1) - 1));
  return scaledMinimumSalary(row.salaries[yearIndex], season);
}

function minimumSalaryValuesForSeason(season) {
  const values = [twoWayMinimumSalaryForSeason(season)];
  MINIMUM_SALARY_BASE_ROWS.forEach((row) => {
    row.salaries.forEach((salary) => {
      const value = scaledMinimumSalary(salary, season);
      if (value) values.push(value);
    });
  });
  return values;
}

function salaryLooksLikeMinimum(amount, season) {
  const numeric = Math.round(Number(amount || 0));
  if (!numeric) return false;
  return minimumSalaryValuesForSeason(season).some((minimum) => Math.abs(numeric - minimum) <= 2);
}

function figuresSeasonYears() {
  const currentYear = currentSeasonStart();
  return Array.from({ length: 6 }, (_, idx) => currentYear + idx);
}

function maximumSalaryRows() {
  return [
    { label: 'Salario máximo 0-6 años', value: (season) => capForSeason(season) * 0.25 },
    { label: 'Salario máximo 7-9 años', value: (season) => capForSeason(season) * 0.30 },
    { label: 'Salario máximo 10+ años', value: (season) => capForSeason(season) * 0.35 },
  ];
}

function exceptionRows() {
  return [
    { label: 'Mid-Level Exception', value: (season) => capForSeason(season) * 0.0912 },
    { label: 'Room Mid-Level Exception', value: (season) => capForSeason(season) * 0.05678 },
    { label: 'Bi-Annual Exception', value: (season) => capForSeason(season) * 0.0332 },
    { label: 'Tax-Payer Mid-Level Exception', value: taxpayerMidLevelForSeason },
  ];
}

function capLimitRows() {
  return [
    { label: 'Salary cap', value: capForSeason },
    { label: 'Luxury cap', value: luxuryCapForSeason },
    { label: '1er Apron', value: firstApronForSeason },
    { label: '2do Apron', value: secondApronForSeason },
    { label: 'Cash máximo traspasable', value: cashLimitForSeason },
  ];
}

function averageSalaryRows() {
  return [
    { label: 'Salario medio de la liga', value: (season) => averageSalaryForSeason(season) || null },
  ];
}

function figureValueHtml(row, season) {
  const value = row.value(season);
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return '<span class="figures-pending">Pendiente</span>';
  }
  return `<span>${formatMoneyDots(value)}</span>`;
}

function figuresTableHtml(title, rows, seasons, description = '') {
  const currentYear = currentSeasonStart();
  return `
    <section class="figures-group">
      <div class="figures-group-head">
        <h3>${escapeHtml(title)}</h3>
        ${description ? `<p>${escapeHtml(description)}</p>` : ''}
      </div>
      <div class="table-wrap figures-table-wrap">
      <table class="figures-table">
        <thead>
          <tr>
            <th>Cifra</th>
            ${seasons.map((season) => `
              <th class="${season === currentYear ? 'figures-current-season' : ''}">
                ${seasonSlashLabel(season)}
                ${season === currentYear ? '<span>actual</span>' : ''}
              </th>
            `).join('')}
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <th>${escapeHtml(row.label)}</th>
              ${seasons.map((season) => `<td>${figureValueHtml(row, season)}</td>`).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
    </section>
  `;
}

function minimumSalaryTableHtml(season) {
  const currentYear = currentSeasonStart();
  return `
    <article class="minimum-salary-season ${season === currentYear ? 'is-current-season' : ''}">
      <div class="minimum-salary-season-head">
        <h4>
          ${seasonSlashLabel(season)}
          ${season === currentYear ? '<span>actual</span>' : ''}
        </h4>
        <span class="minimum-two-way">Two Way ${formatMoneyDots(twoWayMinimumSalaryForSeason(season))}</span>
      </div>
      <div class="table-wrap minimum-salary-table-wrap">
        <table class="figures-table minimum-salary-table">
          <thead>
            <tr>
              <th>Años exp</th>
              ${MINIMUM_SALARY_CONTRACT_YEARS.map((year) => `<th>Año ${year}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${MINIMUM_SALARY_BASE_ROWS.map((row) => `
              <tr>
                <th>${escapeHtml(row.label)}</th>
                ${row.salaries.map((salary) => {
                  const value = scaledMinimumSalary(salary, season);
                  return `<td class="${value ? '' : 'figures-empty-cell'}">${value ? formatMoneyDots(value) : ''}</td>`;
                }).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </article>
  `;
}

function minimumSalarySectionHtml(seasons) {
  const selectedSeason = selectedFiguresSeasonStart();
  return `
    <section class="figures-group minimum-salary-group">
      <div class="figures-group-head">
        <h3>Salarios mínimos</h3>
        <p>Base 2025/26 escalada por el crecimiento del Salary Cap.</p>
      </div>
      <div class="minimum-salary-grid">
        ${minimumSalaryTableHtml(selectedSeason)}
      </div>
    </section>
  `;
}

function renderFiguresSeasonControl() {
  const select = document.getElementById('figuresSeasonSelect');
  if (!select) return;
  const currentYear = currentSeasonStart();
  const selected = selectedFiguresSeasonStart();
  select.innerHTML = availableFiguresSeasonStarts()
    .map((season) => {
      const suffix = season === currentYear ? ' (current)' : '';
      return `<option value="${season}">${seasonLabel(season)}${suffix}</option>`;
    })
    .join('');
  select.value = String(selected);
}

function setFiguresSeasonStart(startYear) {
  state.ui.figuresSeasonStart = normalizeFiguresSeasonStart(startYear);
  renderFiguresSeasonControl();
  if (state.ui.viewMode === 'figures') renderFigures();
}

function setupFiguresSeasonControl() {
  const select = document.getElementById('figuresSeasonSelect');
  if (!select) return;
  renderFiguresSeasonControl();
  select.addEventListener('change', () => {
    setFiguresSeasonStart(select.value);
  });
}

function setupTrackerEconomySeasonControl() {
  const select = document.getElementById('trackerEconomySeasonSelect');
  if (!select) return;
  select.addEventListener('change', async () => {
    state.ui.trackerEconomySeason = Number(select.value);
    await loadTrackerEconomy(state.ui.trackerEconomySeason);
  });
}

function renderFigures() {
  const board = document.getElementById('figuresBoard');
  if (!board) return;
  const seasons = figuresSeasonYears();
  renderFiguresSeasonControl();
  board.innerHTML = `
    <div class="figures-note">
      Las cifras derivadas se calculan desde el Salary Cap configurado por temporada. Los mínimos parten de la tabla 2025/26 y escalan con el crecimiento del cap.
    </div>
    ${figuresTableHtml('Salarios máximos', maximumSalaryRows(), seasons)}
    ${figuresTableHtml('Excepciones', exceptionRows(), seasons)}
    ${figuresTableHtml('Límites de cap, luxury, aprons y cash', capLimitRows(), seasons)}
    ${minimumSalarySectionHtml(seasons)}
    ${figuresTableHtml('Salario medio', averageSalaryRows(), seasons)}
  `;
}

function applySeasonColumnVisibility() {
  const currentYear = currentSeasonStart();
  const tableConfigs = [
    { selector: '#playersTable', seasonOffset: 6 },
    { selector: '#deadContractsTable', seasonOffset: 4 },
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
  } else if (/^-?\d{1,3}(\.\d{3})+$/.test(cleaned)) {
    cleaned = cleaned.replaceAll('.', '');
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
    if (isTwoWayPlayer(row)) return POSITION_ORDER.TW;
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

  document.querySelectorAll('#trackerEconomyTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const curr = state.sort.trackerEconomy;
      state.sort.trackerEconomy = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      renderTrackerEconomy();
      updateSortIndicators('trackerEconomyTable', state.sort.trackerEconomy);
    });
  });

  document.querySelectorAll('#economySettingsTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      try {
        if (document.querySelector('#economySettingsTable [data-economy-team][data-economy-field]')) {
          state.economySettingsRows = collectEconomySettingsRows();
        }
      } catch (err) {
        alert(err.message || String(err));
        return;
      }
      const key = th.dataset.sort;
      const curr = state.sort.economySettings;
      state.sort.economySettings = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      renderEconomySettingsTable();
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

function renderAdminMobileTeamGrid() {
  const grid = document.getElementById('adminMobileTeamGrid');
  if (!grid) return;
  grid.innerHTML = '';

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
      closeAdminMobileSidebar();
      if (t.code === state.teamCode) return;
      await loadTeam(t.code);
    });

    const label = document.createElement('span');
    label.className = 'team-code-label';
    label.textContent = t.code;

    btn.appendChild(fallback);
    btn.appendChild(img);
    btn.appendChild(label);
    grid.appendChild(btn);
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
  const draftOpt = document.createElement('option');
  draftOpt.value = '__draft_order';
  draftOpt.textContent = 'Draft';
  picker.appendChild(draftOpt);
  const freeAgentsOpt = document.createElement('option');
  freeAgentsOpt.value = '__free_agents';
  freeAgentsOpt.textContent = 'Free agents';
  picker.appendChild(freeAgentsOpt);

  state.teams.forEach((t) => {
    const opt = document.createElement('option');
    opt.value = t.code;
    opt.textContent = `${t.code} - ${t.name}`;
    picker.appendChild(opt);
  });

  picker.value = state.ui.viewMode === 'draft-order'
    ? '__draft_order'
    : (state.ui.viewMode === 'free-agents' ? '__free_agents' : (state.teamCode || ''));
  picker.onchange = async (e) => {
    const code = e.target.value;
    if (!code) {
      await loadTracker();
      return;
    }
    if (code === '__draft_order') {
      await loadDraftOrder();
      return;
    }
    if (code === '__free_agents') {
      await loadFreeAgents();
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

  const ownerOptions = teamOptionsHtml('', { includeCurrent: false });
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

  const decision = await confirmWithDiscordNotification({
    title: 'Confirmar traspaso',
    message: `${teamA}: ${fromA.length} jugador(es), ${pickIdsA.length} ronda(s), ${rightIdsA.length} derecho(s)\n${teamB}: ${fromB.length} jugador(es), ${pickIdsB.length} ronda(s), ${rightIdsB.length} derecho(s)\nCuenta como: ${moveBucketLabel(tradeBucket)}`,
    confirmLabel: 'Confirmar traspaso',
    defaultNotify: true,
  });
  if (!decision.confirmed) return;

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
        notify_discord: decision.notifyDiscord,
        generate_discord_image: decision.generateDiscordImage,
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

function formatUserRole(role) {
  const normalized = String(role || '').trim().toLowerCase();
  if (normalized === 'admin') return 'Admin';
  if (normalized === 'gm') return 'GM';
  return 'Guest';
}

function adminUserTeamOptions(selectedCode) {
  const selected = String(selectedCode || '').toUpperCase();
  return [
    `<option value="" ${selected ? '' : 'selected'}>Guest - no team</option>`,
    ...state.teams.map((team) => {
      const code = String(team.code || '').toUpperCase();
      return `<option value="${escapeHtml(code)}" ${code === selected ? 'selected' : ''}>${escapeHtml(code)} - ${escapeHtml(team.name || code)}</option>`;
    }),
  ].join('');
}

function renderAdminUsers() {
  const tbody = document.querySelector('#adminUsersTable tbody');
  if (!tbody) return;
  const users = state.adminUsers || [];
  tbody.innerHTML = '';
  if (!users.length) {
    tbody.innerHTML = '<tr><td colspan="6">No signed-up users yet.</td></tr>';
    return;
  }

  users.forEach((user) => {
    const tr = document.createElement('tr');
    const userId = Number(user.id);
    const teamCodes = Array.isArray(user.team_codes) ? user.team_codes.filter(Boolean) : [];
    const selectedTeam = user.team_code || teamCodes[0] || '';
    const created = user.created_at ? new Date(user.created_at).toLocaleString() : '';
    const updated = user.updated_at ? new Date(user.updated_at).toLocaleString() : '';
    tr.dataset.adminUserId = String(userId);
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(user.display_name || user.email || 'User')}</strong>
        <div class="muted">${escapeHtml(user.email || '')}</div>
      </td>
      <td><span class="user-role-pill user-role-pill--${escapeHtml(user.role || 'guest')}">${escapeHtml(formatUserRole(user.role))}</span></td>
      <td>
        <select data-admin-user-team="${userId}" aria-label="Team assignment for ${escapeHtml(user.email || 'user')}">
          ${adminUserTeamOptions(selectedTeam)}
        </select>
      </td>
      <td>${escapeHtml(created)}</td>
      <td>${escapeHtml(updated)}</td>
      <td><button type="button" data-admin-user-save="${userId}">Save</button></td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('[data-admin-user-save]').forEach((button) => {
    button.addEventListener('click', async () => {
      await saveAdminUserAccess(Number(button.dataset.adminUserSave), button);
    });
  });
}

async function loadAdminUsers() {
  const res = await api('/api/admin/users');
  state.adminUsers = res.users || [];
  renderAdminUsers();
}

function optionRequestActionLabel(action) {
  return action === 'accepted' ? 'Aceptar opción' : 'Rechazar opción';
}

function updateGmOptionRequestBadges() {
  const count = (state.gmOptionRequests || []).filter((request) => request.status === 'pending').length;
  ['gmOptionRequestsBadge', 'mobileGmOptionRequestsBadge'].forEach((id) => {
    const badge = document.getElementById(id);
    if (!badge) return;
    badge.textContent = String(count);
    badge.hidden = count < 1;
  });
}

function renderGmOptionRequests() {
  const tbody = document.querySelector('#gmOptionRequestsTable tbody');
  if (!tbody) return;
  const requests = state.gmOptionRequests || [];
  tbody.innerHTML = '';
  if (!requests.length) {
    tbody.innerHTML = '<tr><td colspan="8">No pending GM option requests.</td></tr>';
    return;
  }

  requests.forEach((request) => {
    const requestId = Number(request.id);
    const created = request.created_at ? new Date(request.created_at).toLocaleString() : '';
    const submittedBy = request.requester_name || request.requester_email || 'GM';
    const actionClass = request.action === 'accepted' ? 'gm-request-action--accept' : 'gm-request-action--reject';
    const tr = document.createElement('tr');
    tr.dataset.gmOptionRequestId = String(requestId);
    tr.innerHTML = `
      <td><strong>${escapeHtml(request.team_code || '')}</strong><div class="muted">${escapeHtml(request.team_name || '')}</div></td>
      <td>${escapeHtml(request.player_name || '')}</td>
      <td>${escapeHtml(request.season_label || '')}</td>
      <td><span class="contract-opt-pill ${contractOptionClass(request.option_value)}">${escapeHtml(request.option_value || '')}</span></td>
      <td><span class="gm-request-action ${actionClass}">${escapeHtml(optionRequestActionLabel(request.action))}</span></td>
      <td><strong>${escapeHtml(submittedBy)}</strong><div class="muted">${escapeHtml(request.requester_email || '')}</div></td>
      <td>${escapeHtml(created)}</td>
      <td class="gm-request-actions">
        <button type="button" data-gm-request-approve="${requestId}">Approve</button>
        <button type="button" class="danger" data-gm-request-reject="${requestId}">Reject</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('[data-gm-request-approve]').forEach((button) => {
    button.addEventListener('click', async () => {
      await decideGmOptionRequest(Number(button.dataset.gmRequestApprove), 'approved', button);
    });
  });
  tbody.querySelectorAll('[data-gm-request-reject]').forEach((button) => {
    button.addEventListener('click', async () => {
      await decideGmOptionRequest(Number(button.dataset.gmRequestReject), 'rejected', button);
    });
  });
}

async function loadGmOptionRequests() {
  const res = await api('/api/admin/gm-option-requests?status=pending');
  state.gmOptionRequests = res.requests || [];
  updateGmOptionRequestBadges();
  renderGmOptionRequests();
}

async function decideGmOptionRequest(requestId, decision, button) {
  if (!Number.isInteger(requestId) || requestId <= 0) return;
  const label = decision === 'approved' ? 'aprobar' : 'rechazar';
  if (!window.confirm(`¿Confirmas ${label} esta solicitud del GM?`)) return;
  const row = button?.closest('tr');
  const buttons = row ? Array.from(row.querySelectorAll('button')) : [];
  buttons.forEach((btn) => { btn.disabled = true; });
  try {
    await api(`/api/admin/gm-option-requests/${requestId}`, {
      method: 'PATCH',
      body: JSON.stringify({ decision }),
    });
    await loadGmOptionRequests();
  } catch (err) {
    alert(`GM request update failed: ${err.message || err}`);
    buttons.forEach((btn) => { btn.disabled = false; });
  }
}

async function saveAdminUserAccess(userId, button) {
  if (!Number.isInteger(userId) || userId <= 0) return;
  const select = document.querySelector(`[data-admin-user-team="${userId}"]`);
  const teamCode = String(select?.value || '').trim().toUpperCase();
  const originalText = button?.textContent || 'Save';
  if (button) {
    button.disabled = true;
    button.textContent = 'Saving...';
  }
  try {
    const result = await api(`/api/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify({ team_code: teamCode }),
    });
    const updatedUser = result.user;
    if (updatedUser) {
      state.adminUsers = (state.adminUsers || []).map((user) => (
        Number(user.id) === userId ? updatedUser : user
      ));
      renderAdminUsers();
    } else {
      await loadAdminUsers();
    }
  } catch (err) {
    alert(`User save failed: ${err.message || err}`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
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
      section.classList.toggle('section-hidden', !showTeam || tab.id !== active);
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

function activeTrackerTab() {
  return ['general', 'economy'].includes(state.ui.activeTrackerTab)
    ? state.ui.activeTrackerTab
    : 'general';
}

function syncTrackerTabs() {
  const showTracker = state.ui.viewMode === 'tracker';
  const active = activeTrackerTab();
  const tabs = document.getElementById('trackerTabs');
  if (tabs) tabs.classList.toggle('section-hidden', !showTracker);
  document.querySelectorAll('[data-tracker-tab]').forEach((btn) => {
    const isActive = btn.dataset.trackerTab === active;
    btn.classList.toggle('is-active', isActive);
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  const generalPanel = document.getElementById('trackerGeneralPanel');
  const economyPanel = document.getElementById('trackerEconomyPanel');
  if (generalPanel) generalPanel.classList.toggle('section-hidden', !showTracker || active !== 'general');
  if (economyPanel) economyPanel.classList.toggle('section-hidden', !showTracker || active !== 'economy');
}

function setTrackerTab(tabId) {
  state.ui.activeTrackerTab = ['general', 'economy'].includes(tabId) ? tabId : 'general';
  syncTrackerTabs();
}

function setupTrackerTabs() {
  document.querySelectorAll('[data-tracker-tab]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      setTrackerTab(btn.dataset.trackerTab);
      if (state.ui.activeTrackerTab === 'economy') {
        await loadTrackerEconomy();
      }
    });
  });
  syncTrackerTabs();
}

function setViewMode(mode) {
  state.ui.viewMode = mode;
  const showTeam = mode === 'team';
  const showTracker = mode === 'tracker';
  const showFigures = mode === 'figures';
  const showDraftOrder = mode === 'draft-order';
  const showFreeAgents = mode === 'free-agents';
  const showAdminLog = mode === 'admin-log';
  const showAdminUsers = mode === 'admin-users';
  const showGmOptionRequests = mode === 'gm-option-requests';
  const showLeagueSettings = mode === 'admin-settings';

  const toggleSection = (id, hidden) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('section-hidden', hidden);
  };

  toggleSection('trackerSection', !showTracker);
  toggleSection('figuresSection', !showFigures);
  toggleSection('draftOrderSection', !showDraftOrder);
  toggleSection('freeAgentsSection', !showFreeAgents);
  toggleSection('teamTabs', !showTeam);
  toggleSection('teamMeta', !showTeam);
  toggleSection('adminTeamControlsSection', !showTeam);
  toggleSection('settingsSection', !showLeagueSettings);
  toggleSection('adminLogsSection', !showAdminLog);
  toggleSection('adminUsersSection', !showAdminUsers);
  toggleSection('gmOptionRequestsSection', !showGmOptionRequests);
  toggleSection('rosterSection', !showTeam);
  toggleSection('deadContractsSection', !showTeam);
  toggleSection('exceptionsSection', !showTeam);
  toggleSection('assetsSection', !showTeam);
  toggleSection('draftAssetsSection', !showTeam);
  toggleSection('playerRightsSection', !showTeam);
  toggleSection('importantFiguresSection', !showTeam);
  syncTrackerTabs();
  syncTeamTabs();
  syncAdminMobileInfoButton();

  const teamControls = [
    'reloadBtn',
    'addEntryBtn',
    'saveTeamGmInlineBtn',
    'processTradeBtn',
    'teamFirstApronCapInput',
    'teamSecondApronCapInput',
  ];
  teamControls.forEach((id) => {
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
  const openUsersBtn = document.getElementById('openAdminUsersPageBtn');
  const openGmRequestsBtn = document.getElementById('openGmOptionRequestsPageBtn');
  const openSettingsBtn = document.getElementById('openLeagueSettingsPageBtn');
  const gmRequestsBtn = document.getElementById('gmOptionRequestsBtn');

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

  openUsersBtn.addEventListener('click', async () => {
    setViewMode('admin-users');
    setPageHeading('ANBA Users', '');
    renderCapStatusPills({});
    await loadAdminUsers();
  });

  const openGmRequests = async () => {
    setViewMode('gm-option-requests');
    setPageHeading('GM Requests', '');
    renderCapStatusPills({});
    await loadGmOptionRequests();
  };

  openGmRequestsBtn?.addEventListener('click', openGmRequests);
  gmRequestsBtn?.addEventListener('click', openGmRequests);

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
  const s = summaryForBalanceSeason(state.teamData);
  const m = state.teamData.move_summary || {};
  list.innerHTML = `
    <div class="mobile-info-summary cards team-summary-grid">
      ${buildBalancePanelHtml(s)}
      <article class="card card-summary">
        <div class="label">Cash</div>
        ${buildCashGaugePanel(s, false)}
      </article>
      <article class="card card-summary">
        <div class="label">Transfer moves</div>
        ${buildMoveGaugePanel(m, false)}
      </article>
    </div>
  `;
  setAdminMobileOverlayVisible('adminMobileInfoBackdrop', true);
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

function buildUsageGaugeCard({ label, available, limit, valueText, limitText, unitText = 'Available', tone = 'cash', detailHtml = '', controlHtml = '' }) {
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
      ${controlHtml}
      ${detailHtml}
    </article>
  `;
}

function buildCashGaugePanel(summary, editable = false) {
  const s = summary || {};
  const limit = Number(s.cash_limit_total || state.settings.cash_limit_total || 0);
  const receivedAvailable = availableAmount(s.cash_received, limit);
  const sentAvailable = availableAmount(s.cash_sent, limit);
  const receivedControl = editable
    ? `<label class="usage-gauge-edit"><span>Available</span><input id="summaryCashReceivedInput" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(receivedAvailable))}"></label>`
    : '';
  const sentControl = editable
    ? `<label class="usage-gauge-edit"><span>Available</span><input id="summaryCashSentInput" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(sentAvailable))}"></label>`
    : '';
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
        controlHtml: receivedControl,
      })}
      ${buildUsageGaugeCard({
        label: 'Cash enviado',
        available: sentAvailable,
        limit,
        valueText: formatMoneyDots(sentAvailable),
        limitText: formatMoneyDots(limit),
        unitText: 'Available',
        tone: 'cash',
        controlHtml: sentControl,
      })}
    </div>
  `;
}

function buildMoveGaugePanel(moveSummary, editable = false) {
  const m = moveSummary || {};
  const preLimit = MOVE_LIMIT_PRE30;
  const postLimit = MOVE_LIMIT_POST30;
  const preAvailable = availableMoves(m, 'pre30', preLimit);
  const postAvailable = availableMoves(m, 'post30', postLimit);
  const preControl = editable
    ? `<label class="usage-gauge-edit"><span>Available</span><input id="summaryMovePre30AvailableInput" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(preAvailable))}"></label>`
    : '';
  const postControl = editable
    ? `<label class="usage-gauge-edit"><span>Available</span><input id="summaryMovePost30AvailableInput" class="summary-inline-input" type="text" inputmode="numeric" value="${escapeHtml(formatDots(postAvailable))}"></label>`
    : '';
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
        controlHtml: preControl,
        detailHtml: editable ? '<button id="moveLogPre30Btn" type="button" class="info-chip-btn usage-gauge-info" aria-label="Open pre-30 move log">i</button>' : '',
      })}
      ${buildUsageGaugeCard({
        label: 'Post-30 moves',
        available: postAvailable,
        limit: postLimit,
        valueText: formatDots(postAvailable),
        limitText: formatDots(postLimit),
        unitText: 'Available',
        tone: 'moves',
        controlHtml: postControl,
        detailHtml: editable ? '<button id="moveLogPost30Btn" type="button" class="info-chip-btn usage-gauge-info" aria-label="Open post-30 move log">i</button>' : '',
      })}
    </div>
  `;
}

function setupAdminMobileNav() {
  const menuBtn = document.getElementById('mobileMenuBtn');
  const closeBtn = document.getElementById('adminMobileSidebarCloseBtn');
  const backdrop = document.getElementById('adminMobileSidebarBackdrop');
  const trackerBtn = document.getElementById('adminMobileTrackerBtn');
  const figuresBtn = document.getElementById('adminMobileFiguresBtn');
  const draftBtn = document.getElementById('adminMobileDraftBtn');
  const freeAgentsBtn = document.getElementById('adminMobileFreeAgentsBtn');
  const logBtn = document.getElementById('adminMobileLogBtn');
  const usersBtn = document.getElementById('adminMobileUsersBtn');
  const gmRequestsBtn = document.getElementById('adminMobileGmOptionRequestsBtn');
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
  if (figuresBtn) {
    figuresBtn.addEventListener('click', async () => {
      closeAdminMobileSidebar();
      await loadFigures();
    });
  }
  if (draftBtn) {
    draftBtn.addEventListener('click', async () => {
      closeAdminMobileSidebar();
      await loadDraftOrder();
    });
  }
  if (freeAgentsBtn) {
    freeAgentsBtn.addEventListener('click', async () => {
      closeAdminMobileSidebar();
      await loadFreeAgents();
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
  if (usersBtn) {
    usersBtn.addEventListener('click', async () => {
      closeAdminMobileSidebar();
      setViewMode('admin-users');
      setPageHeading('ANBA Users', '');
      renderCapStatusPills({});
      await loadAdminUsers();
    });
  }
  if (gmRequestsBtn) {
    gmRequestsBtn.addEventListener('click', async () => {
      closeAdminMobileSidebar();
      setViewMode('gm-option-requests');
      setPageHeading('GM Requests', '');
      renderCapStatusPills({});
      await loadGmOptionRequests();
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
      <td>${trackerSpaceValueHtml(row.espacio_cap)}</td>
      <td>${trackerSpaceValueHtml(row.espacio_luxury)}</td>
      <td>${trackerLuxuryTaxValueHtml(row.luxury_tax)}</td>
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

function populateTrackerEconomySeasonSelect() {
  const select = document.getElementById('trackerEconomySeasonSelect');
  if (!select) return;
  const selected = selectedTrackerEconomySeason();
  select.innerHTML = trackerEconomySeasonOptions()
    .map((season) => `<option value="${season}"${season === selected ? ' selected' : ''}>${seasonLabel(season)}</option>`)
    .join('');
  select.value = String(selected);
}

function renderTrackerEconomy() {
  const tbody = document.querySelector('#trackerEconomyTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  populateTrackerEconomySeasonSelect();

  const rows = sortedRows(state.trackerEconomyRows || [], state.sort.trackerEconomy);
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><button type="button" class="tracker-team-btn" data-team-code="${escapeHtml(row.team_code)}">${escapeHtml(row.team_code)}</button></td>
      <td>${trackerEconomyValueHtml(row.balance)}</td>
      <td>${trackerEconomyValueHtml(row.revenue)}</td>
      <td>${trackerEconomyValueHtml(row.expenses)}</td>
    `;
    const teamBtn = tr.querySelector('[data-team-code]');
    teamBtn.addEventListener('click', async () => {
      await loadTeam(row.team_code);
    });
    tbody.appendChild(tr);
  });
  if (!rows.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="4">No economy data for this season.</td>';
    tbody.appendChild(tr);
  }
}

function birdRightsOptions(selected = '') {
  const values = ['', 'Min', 'Max', 'Mid', 'TMid', 'Bi', '10d', 'R', 'R(2)', 'TW', 'Room', 'Reg'];
  const normalized = String(selected || '');
  if (normalized && !values.includes(normalized)) values.push(normalized);
  return values
    .map((value) => `<option value="${escapeHtml(value)}"${value === normalized ? ' selected' : ''}>${escapeHtml(value)}</option>`)
    .join('');
}

function optionSelectHtml(fieldName, selected = '', attrName = 'data-sign-option-field') {
  const options = ['', 'TO', 'PO', 'QO', 'GAP'];
  const normalized = String(selected || '');
  return `
    <select ${attrName}="${fieldName}">
      ${options.map((value) => `<option value="${value}"${value === normalized ? ' selected' : ''}>${value || '-'}</option>`).join('')}
    </select>
  `;
}

function freeAgentPayloadFromRow(row, attrName) {
  const payload = {};
  row.querySelectorAll(`[${attrName}]`).forEach((el) => {
    const key = el.getAttribute(attrName);
    const value = String(el.value || '').trim();
    payload[key] = value || null;
  });
  return payload;
}

function renderFreeAgents() {
  const tbody = document.querySelector('#freeAgentsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const rows = sortedRows(state.freeAgents || [], state.sort.free_agents);
  rows.forEach((agent) => {
    const tr = document.createElement('tr');
    tr.dataset.id = agent.id;
    tr.innerHTML = `
      <td><input data-field="name" value="${escapeHtml(agent.name || '')}"></td>
      <td><input data-field="position" value="${escapeHtml(agent.position || '')}"></td>
      <td><select data-field="bird_rights">${birdRightsOptions(agent.bird_rights || '')}</select></td>
      <td><input data-field="rating" value="${escapeHtml(agent.rating || '')}"></td>
      <td><input data-field="years_left" value="${agent.years_left == null ? '' : escapeHtml(agent.years_left)}"></td>
      <td><input data-field="notes" value="${escapeHtml(agent.notes || '')}"></td>
      <td>
        <button data-action="sign-free-agent" type="button">Sign</button>
        <button data-action="delete-free-agent" type="button" class="danger">Delete</button>
      </td>
    `;
    tr.querySelectorAll('[data-field]').forEach((el) => {
      const key = el.dataset.field;
      attachInlineEditor(el, async (value) => {
        await api(`/api/free-agents/${agent.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ [key]: value || null }),
        });
        agent[key] = value || null;
      });
    });
    tr.querySelector('[data-action="sign-free-agent"]').addEventListener('click', () => {
      openSignFreeAgentModal(agent);
    });
    tr.querySelector('[data-action="delete-free-agent"]').addEventListener('click', async () => {
      if (!confirm(`Delete ${agent.name || 'this free agent'}?`)) return;
      await api(`/api/free-agents/${agent.id}`, { method: 'DELETE' });
      await loadFreeAgents();
    });
    tbody.appendChild(tr);
  });

  if (state.ui.addingFreeAgent) {
    const tr = document.createElement('tr');
    tr.className = 'table-add-editor-row';
    tr.innerHTML = `
      <td><input data-new-field="name" data-autofocus placeholder="Player name"></td>
      <td><input data-new-field="position" placeholder="PG"></td>
      <td><select data-new-field="bird_rights">${birdRightsOptions('')}</select></td>
      <td><input data-new-field="rating" placeholder="Rating"></td>
      <td><input data-new-field="years_left" placeholder="Years"></td>
      <td><input data-new-field="notes" placeholder="Notes"></td>
      <td class="table-add-actions-cell">
        <button type="button" class="inline-save" data-action="save-draft">✓</button>
        <button type="button" class="inline-cancel" data-action="discard-draft">✕</button>
      </td>
    `;
    const discard = () => {
      state.ui.addingFreeAgent = false;
      renderFreeAgents();
    };
    const save = async () => {
      const payload = freeAgentPayloadFromRow(tr, 'data-new-field');
      if (!String(payload.name || '').trim()) {
        discard();
        return;
      }
      state.ui.addingFreeAgent = false;
      await api('/api/free-agents', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await loadFreeAgents();
    };
    tbody.appendChild(tr);
    bindDraftEditor(tr, save, discard);
    requestAnimationFrame(() => {
      tr.querySelector('[data-autofocus]')?.focus();
    });
  } else if (!rows.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="7">No free agents listed.</td>';
    tbody.appendChild(tr);
  }
}

function draftOrderRows(round) {
  return (state.draftOrder?.draft_order || [])
    .filter((row) => String(row.draft_round || '').trim() === round)
    .sort((a, b) => Number(a.pick_number || 0) - Number(b.pick_number || 0));
}

function draftOrderNextPickNumber(round) {
  const rows = draftOrderRows(round);
  const max = rows.reduce((acc, row) => Math.max(acc, Number(row.pick_number || 0)), 0);
  return max + 1;
}

function draftOrderTeamOptions(selectedCode = '') {
  const normalized = String(selectedCode || '').trim().toUpperCase();
  return (state.teams || [])
    .map((team) => {
      const code = String(team.code || '').trim().toUpperCase();
      return `<option value="${escapeHtml(code)}"${code === normalized ? ' selected' : ''}>${escapeHtml(code)} - ${escapeHtml(team.name || code)}</option>`;
    })
    .join('');
}

function draftOrderPayloadFromRow(row, attrName = 'data-draft-order-field') {
  const payload = {
    draft_year: Number(state.draftOrder?.draft_year || currentSeasonStart() + 1),
  };
  row.querySelectorAll(`[${attrName}]`).forEach((el) => {
    const key = el.getAttribute(attrName);
    const value = String(el.value || '').trim();
    if (key === 'pick_number' || key === 'draft_year') {
      payload[key] = Number(value || 0);
    } else {
      payload[key] = value || null;
    }
  });
  return payload;
}

function renderDraftOrderTable(round, tableId) {
  const tbody = document.querySelector(`#${tableId} tbody`);
  if (!tbody) return;
  const rows = draftOrderRows(round);
  tbody.innerHTML = '';

  rows.forEach((entry) => {
    const tr = document.createElement('tr');
    tr.dataset.id = entry.id;
    tr.innerHTML = `
      <td><input data-draft-order-field="pick_number" type="number" min="1" step="1" value="${escapeHtml(entry.pick_number || '')}"></td>
      <td><select data-draft-order-field="owner_team_code">${draftOrderTeamOptions(entry.owner_team_code || '')}</select></td>
      <td><select data-draft-order-field="original_team_code">${draftOrderTeamOptions(entry.original_team_code || '')}</select></td>
      <td><button type="button" class="danger" data-action="delete-draft-order">Delete</button></td>
    `;
    tr.querySelectorAll('[data-draft-order-field]').forEach((el) => {
      attachInlineEditor(el, async () => {
        await api(`/api/draft-order/${entry.id}`, {
          method: 'PATCH',
          body: JSON.stringify(draftOrderPayloadFromRow(tr)),
        });
        await loadDraftOrder();
      });
    });
    tr.querySelector('[data-action="delete-draft-order"]').addEventListener('click', async () => {
      if (!confirm(`Delete ${round} pick #${entry.pick_number}?`)) return;
      await api(`/api/draft-order/${entry.id}`, { method: 'DELETE' });
      await loadDraftOrder();
    });
    tbody.appendChild(tr);
  });

  if (state.ui.addingDraftOrderRound === round) {
    const tr = document.createElement('tr');
    tr.className = 'table-add-editor-row';
    const defaultTeam = state.teams[0]?.code || '';
    tr.innerHTML = `
      <td><input data-new-draft-order-field="pick_number" data-autofocus type="number" min="1" step="1" value="${draftOrderNextPickNumber(round)}"></td>
      <td><select data-new-draft-order-field="owner_team_code">${draftOrderTeamOptions(defaultTeam)}</select></td>
      <td><select data-new-draft-order-field="original_team_code">${draftOrderTeamOptions(defaultTeam)}</select></td>
      <td class="table-add-actions-cell">
        <button type="button" class="inline-save" data-action="save-draft">✓</button>
        <button type="button" class="inline-cancel" data-action="discard-draft">✕</button>
      </td>
    `;
    const discard = () => {
      state.ui.addingDraftOrderRound = null;
      renderDraftOrder();
    };
    const save = async () => {
      const payload = draftOrderPayloadFromRow(tr, 'data-new-draft-order-field');
      payload.draft_round = round;
      if (!payload.pick_number || !payload.owner_team_code || !payload.original_team_code) {
        alert('Pick number, owner, and original team are required.');
        return;
      }
      state.ui.addingDraftOrderRound = null;
      await api('/api/draft-order', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await loadDraftOrder();
    };
    tbody.appendChild(tr);
    bindDraftEditor(tr, save, discard);
    requestAnimationFrame(() => tr.querySelector('[data-autofocus]')?.focus());
  } else if (!rows.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="4" class="draft-order-empty">No selections configured.</td>';
    tbody.appendChild(tr);
  }
}

function renderDraftOrder() {
  const subtitle = document.getElementById('draftOrderSubtitle');
  const draftYear = Number(state.draftOrder?.draft_year || currentSeasonStart() + 1);
  if (subtitle) subtitle.textContent = `${draftYear} order of selection`;
  renderDraftOrderTable('1st', 'draftOrderFirstTable');
  renderDraftOrderTable('2nd', 'draftOrderSecondTable');
}

function populateSignFreeAgentTeams(selectedCode = '') {
  const select = document.getElementById('signFreeAgentTeam');
  if (!select) return;
  select.innerHTML = state.teams
    .map((team) => `<option value="${team.code}">${team.code} - ${escapeHtml(team.name || team.code)}</option>`)
    .join('');
  const fallback = selectedCode || state.teamCode || state.teams[0]?.code || '';
  select.value = fallback;
}

function renderSignFreeAgentYearsTable() {
  const tbody = document.querySelector('#signFreeAgentYearsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  ALL_SEASONS.forEach((season) => {
    const tr = document.createElement('tr');
    tr.dataset.season = String(season);
    tr.innerHTML = `
      <td>${seasonLabel(season)}</td>
      <td><input data-sign-field="salary_${season}_text" type="text" placeholder="0"></td>
      <td>${optionSelectHtml(`option_${season}`)}</td>
      <td><input data-sign-bool-field="salary_${season}_provisional" type="checkbox"></td>
      <td><input data-sign-bool-field="salary_${season}_partially_guaranteed" type="checkbox"></td>
      <td><input data-sign-field="salary_${season}_guaranteed_text" type="text" placeholder="Guaranteed amount"></td>
    `;
    tbody.appendChild(tr);
  });
}

function openSignFreeAgentModal(agent) {
  if (!agent) return;
  state.ui.signingFreeAgentId = agent.id;
  populateSignFreeAgentTeams(state.teamCode || '');
  document.getElementById('signFreeAgentName').value = agent.name || '';
  document.getElementById('signFreeAgentPosition').value = agent.position || '';
  document.getElementById('signFreeAgentType').innerHTML = birdRightsOptions(agent.bird_rights || '');
  document.getElementById('signFreeAgentRating').value = agent.rating || '';
  document.getElementById('signFreeAgentYears').value = agent.years_left == null ? '' : agent.years_left;
  document.getElementById('signFreeAgentNotes').value = agent.notes || '';
  document.getElementById('signFreeAgentProvisional').checked = false;
  document.getElementById('signFreeAgentPartial').checked = false;
  renderSignFreeAgentYearsTable();
  document.getElementById('signFreeAgentModal').classList.remove('section-hidden');
}

function closeSignFreeAgentModal() {
  state.ui.signingFreeAgentId = null;
  document.getElementById('signFreeAgentModal')?.classList.add('section-hidden');
}

function signFreeAgentPayload() {
  const payload = {
    team_code: document.getElementById('signFreeAgentTeam')?.value || '',
    name: document.getElementById('signFreeAgentName')?.value.trim() || '',
    position: document.getElementById('signFreeAgentPosition')?.value.trim() || null,
    bird_rights: document.getElementById('signFreeAgentType')?.value.trim() || null,
    rating: document.getElementById('signFreeAgentRating')?.value.trim() || null,
    years_left: document.getElementById('signFreeAgentYears')?.value.trim() || null,
    notes: document.getElementById('signFreeAgentNotes')?.value.trim() || null,
    provisional_amounts: Boolean(document.getElementById('signFreeAgentProvisional')?.checked),
    partially_guaranteed: Boolean(document.getElementById('signFreeAgentPartial')?.checked),
  };
  document.querySelectorAll('#signFreeAgentYearsTable [data-sign-field]').forEach((el) => {
    const key = el.dataset.signField;
    payload[key] = String(el.value || '').trim() || null;
  });
  document.querySelectorAll('#signFreeAgentYearsTable [data-sign-option-field]').forEach((el) => {
    const key = el.dataset.signOptionField;
    payload[key] = String(el.value || '').trim() || null;
  });
  document.querySelectorAll('#signFreeAgentYearsTable [data-sign-bool-field]').forEach((el) => {
    payload[el.dataset.signBoolField] = Boolean(el.checked);
  });
  return payload;
}

async function confirmSignFreeAgent() {
  const freeAgentId = state.ui.signingFreeAgentId;
  if (!freeAgentId) return;
  const payload = signFreeAgentPayload();
  if (!payload.team_code) {
    alert('Select a team.');
    return;
  }
  if (!payload.name) {
    alert('Player name is required.');
    return;
  }
  const btn = document.getElementById('confirmSignFreeAgentBtn');
  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Signing...';
  try {
    await api(`/api/free-agents/${freeAgentId}/sign`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    closeSignFreeAgentModal();
    await loadFreeAgents();
    await refreshAdminLogsSafe();
  } catch (err) {
    alert(`Free agent sign failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
}

function renderCards() {
  const wrap = document.getElementById('teamMeta');
  const t = state.teamData.team;
  const s = summaryForBalanceSeason(state.teamData);
  const m = state.teamData.move_summary || {};
  setPageHeading(t.name || 'Team', t.gm || '');
  renderCapStatusPills(s);
  wrap.innerHTML = `
    ${buildBalancePanelHtml(s)}
    <article class="card card-summary card-summary-split team-operations-card">
      <div class="card-summary-col">
        <div class="label">Cash</div>
        ${buildCashGaugePanel(s, true)}
        <div class="summary-inline-actions">
          <button id="summaryCashSaveBtn" type="button">Save balances</button>
        </div>
      </div>
      <div class="card-summary-col">
        <div class="label">Transfer moves</div>
        ${buildMoveGaugePanel(m, true)}
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
  const summaryMovePre30AvailableInput = document.getElementById('summaryMovePre30AvailableInput');
  const summaryMovePost30AvailableInput = document.getElementById('summaryMovePost30AvailableInput');
  const summaryMovesSaveBtn = document.getElementById('summaryMovesSaveBtn');
  if (summaryMovePre30AvailableInput && summaryMovePost30AvailableInput && summaryMovesSaveBtn) {
    summaryMovesSaveBtn.addEventListener('click', async () => {
      const preAvailable = parseAmount(summaryMovePre30AvailableInput.value);
      const postAvailable = parseAmount(summaryMovePost30AvailableInput.value);
      if (preAvailable == null || preAvailable < 0 || preAvailable > MOVE_LIMIT_PRE30) {
        alert('Invalid pre-30 available value.');
        return;
      }
      if (postAvailable == null || postAvailable < 0 || postAvailable > MOVE_LIMIT_POST30) {
        alert('Invalid post-30 available value.');
        return;
      }
      await saveCurrentTeamMoves(
        { value: String(preAvailable) },
        { value: String(postAvailable) },
        summaryMovesSaveBtn,
      );
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
  const salaryCap = capForSeason(currentYear);
  const luxuryCap = luxuryCapForSeason(currentYear);
  const firstApron = firstApronForSeason(currentYear);
  const secondApron = secondApronForSeason(currentYear);
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
              <td>
                <select data-luxury-repeater-year="${year}" aria-label="Reincidente ${seasonSlashLabel(year)}">
                  <option value="0"${repeater ? '' : ' selected'}>No</option>
                  <option value="1"${repeater ? ' selected' : ''}>Sí</option>
                </select>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
  wrap.querySelectorAll('[data-luxury-repeater-year]').forEach((select) => {
    select.addEventListener('change', async () => {
      const year = Number(select.dataset.luxuryRepeaterYear);
      await saveTeamLuxuryHistory(year, select.value === '1');
    });
  });
}

function renderCapStatusPills(summary) {
  const wrap = document.getElementById('capStatusPills');
  if (!wrap) return;
  wrap.innerHTML = '';
}

function salaryPctHtml(value) {
  const cap = capForSeason(currentSeasonStart()) || 154647000;
  if (!Number.isFinite(value) || cap <= 0) return '';
  return `<span class="salary-pct">${((value / cap) * 100).toFixed(1)}%</span>`;
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

function syncAdminSalaryInfoCell(cellWrap, player, season) {
  if (!cellWrap) return;
  const td = cellWrap.closest('td');
  const messages = salaryInfoMessages(player, season);
  const existing = Array.from(cellWrap.children).find((child) => child.classList?.contains('salary-info-button'));
  if (td) {
    td.classList.toggle('salary-provisional-cell', playerSeasonIsProvisional(player, season));
    td.classList.toggle('salary-partial-guarantee-cell', playerSeasonIsPartiallyGuaranteed(player, season));
    td.classList.toggle('salary-note-cell', playerSeasonHasContractNote(player, season));
  }
  if (existing) {
    existing.remove();
  }
  if (messages.length) {
    cellWrap.insertAdjacentHTML('beforeend', salaryInfoHtml(messages));
    bindSalaryInfoToggles(cellWrap);
  }
}

function appendSalaryProvisionalControl(cellWrap, player, season) {
  if (!cellWrap || !playerUsesProvisionalAmounts(player)) {
    syncAdminSalaryInfoCell(cellWrap, player, season);
    return;
  }
  const field = salaryProvisionalField(season);
  const label = document.createElement('label');
  label.className = 'salary-provisional-toggle';
  label.title = 'Cifra provisional';
  label.innerHTML = `
    <input type="checkbox" data-role="salary-provisional" data-season="${season}">
    <span>Prov.</span>
  `;
  const checkbox = label.querySelector('input');
  checkbox.checked = boolValue(player[field]);
  checkbox.addEventListener('change', async () => {
    const previous = boolValue(player[field]);
    const next = Boolean(checkbox.checked);
    player[field] = next ? 1 : 0;
    syncAdminSalaryInfoCell(cellWrap, player, season);
    checkbox.disabled = true;
    try {
      await api(`/api/players/${player.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: next }),
      });
    } catch (err) {
      player[field] = previous ? 1 : 0;
      checkbox.checked = previous;
      syncAdminSalaryInfoCell(cellWrap, player, season);
      alert(`Provisional amount save failed: ${err.message}`);
    } finally {
      checkbox.disabled = false;
    }
  });
  cellWrap.appendChild(label);
  syncAdminSalaryInfoCell(cellWrap, player, season);
}

function appendSalaryPartialGuaranteeControl(cellWrap, player, season) {
  if (!cellWrap || !playerUsesPartialGuarantees(player)) {
    syncAdminSalaryInfoCell(cellWrap, player, season);
    return;
  }
  const checkedField = salaryPartialGuaranteeField(season);
  const amountField = salaryGuaranteedTextField(season);
  const wrap = document.createElement('div');
  wrap.className = 'salary-partial-control';
  wrap.innerHTML = `
    <label class="salary-partial-toggle" title="Partially guaranteed">
      <input type="checkbox" data-role="salary-partial-guarantee" data-season="${season}">
      <span>Partial</span>
    </label>
    <input class="salary-partial-amount" data-role="salary-guaranteed-amount" data-season="${season}" type="text" placeholder="Guaranteed">
  `;
  const checkbox = wrap.querySelector('[data-role="salary-partial-guarantee"]');
  const amountInput = wrap.querySelector('[data-role="salary-guaranteed-amount"]');
  const syncAmountInput = () => {
    amountInput.disabled = !checkbox.checked;
    amountInput.classList.toggle('section-hidden', !checkbox.checked);
  };
  checkbox.checked = boolValue(player[checkedField]);
  amountInput.value = player[amountField] == null ? '' : player[amountField];
  syncAmountInput();

  checkbox.addEventListener('change', async () => {
    const previous = boolValue(player[checkedField]);
    const next = Boolean(checkbox.checked);
    player[checkedField] = next ? 1 : 0;
    syncAmountInput();
    syncAdminSalaryInfoCell(cellWrap, player, season);
    checkbox.disabled = true;
    try {
      await api(`/api/players/${player.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [checkedField]: next }),
      });
    } catch (err) {
      player[checkedField] = previous ? 1 : 0;
      checkbox.checked = previous;
      syncAmountInput();
      syncAdminSalaryInfoCell(cellWrap, player, season);
      alert(`Partially guaranteed save failed: ${err.message}`);
    } finally {
      checkbox.disabled = false;
    }
  });

  let savingAmount = false;
  const persistAmount = async () => {
    if (savingAmount) return;
    const previous = String(player[amountField] || '');
    const next = amountInput.value.trim();
    if (next === previous) return;
    player[amountField] = next;
    syncAdminSalaryInfoCell(cellWrap, player, season);
    savingAmount = true;
    amountInput.disabled = true;
    try {
      await api(`/api/players/${player.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [amountField]: next || null }),
      });
    } catch (err) {
      player[amountField] = previous;
      amountInput.value = previous;
      syncAdminSalaryInfoCell(cellWrap, player, season);
      alert(`Guaranteed amount save failed: ${err.message}`);
    } finally {
      savingAmount = false;
      syncAmountInput();
    }
  };
  amountInput.addEventListener('blur', () => { void persistAmount(); });
  amountInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      amountInput.blur();
    }
  });
  cellWrap.appendChild(wrap);
  syncAdminSalaryInfoCell(cellWrap, player, season);
}

function appendSalaryNoteControl(cellWrap, player, season) {
  if (!cellWrap || !playerUsesContractNotes(player)) {
    syncAdminSalaryInfoCell(cellWrap, player, season);
    return;
  }
  const checkedField = salaryNoteField(season);
  const textField = salaryNoteTextField(season);
  const wrap = document.createElement('div');
  wrap.className = 'salary-note-control';
  wrap.innerHTML = `
    <label class="salary-note-toggle" title="Contract note">
      <input type="checkbox" data-role="salary-note" data-season="${season}">
      <span>Note</span>
    </label>
    <input class="salary-note-text" data-role="salary-note-text" data-season="${season}" type="text" placeholder="Note">
  `;
  const checkbox = wrap.querySelector('[data-role="salary-note"]');
  const noteInput = wrap.querySelector('[data-role="salary-note-text"]');
  const syncNoteInput = () => {
    noteInput.disabled = !checkbox.checked;
    noteInput.classList.toggle('section-hidden', !checkbox.checked);
  };
  checkbox.checked = boolValue(player[checkedField]);
  noteInput.value = player[textField] == null ? '' : player[textField];
  syncNoteInput();

  checkbox.addEventListener('change', async () => {
    const previous = boolValue(player[checkedField]);
    const next = Boolean(checkbox.checked);
    player[checkedField] = next ? 1 : 0;
    syncNoteInput();
    syncAdminSalaryInfoCell(cellWrap, player, season);
    checkbox.disabled = true;
    try {
      await api(`/api/players/${player.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [checkedField]: next }),
      });
    } catch (err) {
      player[checkedField] = previous ? 1 : 0;
      checkbox.checked = previous;
      syncNoteInput();
      syncAdminSalaryInfoCell(cellWrap, player, season);
      alert(`Contract note save failed: ${err.message}`);
    } finally {
      checkbox.disabled = false;
    }
  });

  let savingNote = false;
  const persistNote = async () => {
    if (savingNote) return;
    const previous = String(player[textField] || '');
    const next = noteInput.value.trim();
    if (next === previous) return;
    player[textField] = next;
    syncAdminSalaryInfoCell(cellWrap, player, season);
    savingNote = true;
    noteInput.disabled = true;
    try {
      await api(`/api/players/${player.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [textField]: next || null }),
      });
    } catch (err) {
      player[textField] = previous;
      noteInput.value = previous;
      syncAdminSalaryInfoCell(cellWrap, player, season);
      alert(`Contract note text save failed: ${err.message}`);
    } finally {
      savingNote = false;
      syncNoteInput();
    }
  };
  noteInput.addEventListener('blur', () => { void persistNote(); });
  noteInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      noteInput.blur();
    }
  });
  cellWrap.appendChild(wrap);
  syncAdminSalaryInfoCell(cellWrap, player, season);
}

function cancelAddPlayerRow() {
  state.ui.addingPlayer = false;
  renderPlayers();
}

function playerDraftPayloadFromRow(row) {
  const payload = { team_code: state.teamCode };
  const fields = ['name', 'position', 'bird_rights', 'rating', 'years_left', 'reference_image_url'];
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
      <input data-new-field="reference_image_url" placeholder="Ref image URL">
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
  const showPositionGroups = shouldRenderRosterPositionGroups();
  const positionCounts = rosterPositionCounts(rows);
  let previousPositionKey = null;
  rows.forEach((p) => {
    if (showPositionGroups) {
      const positionKey = rosterPositionKey(p);
      if (positionKey !== previousPositionKey) {
        appendRosterPositionSeparator(tbody, positionKey, positionCounts[positionKey] || 0, 14);
        previousPositionKey = positionKey;
      }
    }
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
        p[key] = value;
        if (key.startsWith('salary_')) {
          const season = Number(key.split('_')[1] || 0);
          const parsed = parseAmount(value);
          if (Number.isFinite(season)) p[`salary_${season}_num`] = parsed;
          renderRosterTotals(rows, ALL_SEASONS);
          renderImportantFigures();
        }
        await refreshSummary();
      });

      if (key.startsWith('salary_')) {
        wrapper.classList.add('salary-edit');
        const num = parseAmount(fieldEl.value);
        const salarySeason = Number(key.split('_')[1] || currentSeasonStart());
        const salarySeasonCap = capForSeason(salarySeason);
        const pct = document.createElement('span');
        pct.className = 'salary-pct';
        pct.textContent = num && Number.isFinite(num) && salarySeasonCap > 0
          ? `${((num / salarySeasonCap) * 100).toFixed(1)}%`
          : '';
        wrapper.appendChild(pct);

        const refreshPct = () => {
          const parsed = parseAmount(fieldEl.value);
          pct.textContent = parsed && Number.isFinite(parsed) && salarySeasonCap > 0
            ? `${((parsed / salarySeasonCap) * 100).toFixed(1)}%`
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
        if (Number.isFinite(salarySeason)) {
          const cellWrap = fieldEl.closest('.salary-cell-admin');
          appendSalaryProvisionalControl(cellWrap, p, salarySeason);
          appendSalaryPartialGuaranteeControl(cellWrap, p, salarySeason);
          appendSalaryNoteControl(cellWrap, p, salarySeason);
        }
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
      if (key === 'reference_image_url') {
        wrapper.classList.add('reference-image-edit');
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
      const actionWrap = document.createElement('span');
      actionWrap.className = 'option-action-buttons';
      const acceptBtn = document.createElement('button');
      acceptBtn.type = 'button';
      acceptBtn.className = 'option-action-btn option-action-btn--accept';
      acceptBtn.textContent = 'Accept';
      const rejectBtn = document.createElement('button');
      rejectBtn.type = 'button';
      rejectBtn.className = 'option-action-btn option-action-btn--reject';
      rejectBtn.textContent = 'Reject';
      actionWrap.append(acceptBtn, rejectBtn);
      optionSelect.insertAdjacentElement('afterend', actionWrap);

      const syncOptionActions = () => {
        const hasOption = ['TO', 'PO', 'QO', 'GAP'].includes(String(optionSelect.value || '').toUpperCase());
        actionWrap.classList.toggle('section-hidden', !hasOption);
        acceptBtn.disabled = saving || !hasOption;
        rejectBtn.disabled = saving || !hasOption;
      };
      const processOptionAction = async (action) => {
        const optionValue = String(optionSelect.value || '').toUpperCase();
        if (!['TO', 'PO', 'QO', 'GAP'].includes(optionValue)) {
          alert('Select an option type first.');
          return;
        }
        const decision = await confirmWithDiscordNotification({
          title: action === 'accepted' ? 'Aceptar opción' : 'Rechazar opción',
          message: contractOptionActionMessage(state.teamCode, p.name, season, optionValue, action),
          confirmLabel: action === 'accepted' ? 'Accept' : 'Reject',
          danger: action === 'rejected',
          defaultNotify: true,
        });
        if (!decision.confirmed) return;
        const nextOptionValue = action === 'accepted' && ['TO', 'PO'].includes(optionValue) ? '' : optionValue;
        saving = true;
        optionSelect.disabled = true;
        acceptBtn.disabled = true;
        rejectBtn.disabled = true;
        try {
          await api(`/api/players/${p.id}`, {
            method: 'PATCH',
            body: JSON.stringify({
              [optionField]: nextOptionValue || null,
              option_action: action,
              option_action_field: optionField,
              option_action_value: optionValue,
              notify_discord: decision.notifyDiscord,
              generate_discord_image: decision.generateDiscordImage,
            }),
          });
          p[optionField] = nextOptionValue || null;
          optionSelect.value = nextOptionValue;
          applyOptionVisual();
        } catch (err) {
          alert(`No se pudo procesar la opción de contrato: ${err.message}`);
        } finally {
          optionSelect.disabled = false;
          saving = false;
          syncOptionActions();
        }
      };
      applyOptionVisual();
      syncOptionActions();
      optionSelect.addEventListener('change', () => {
        void persistOption().then(syncOptionActions);
      });
      optionSelect.addEventListener('blur', () => {
        void persistOption().then(syncOptionActions);
      });
      acceptBtn.addEventListener('click', () => { void processOptionAction('accepted'); });
      rejectBtn.addEventListener('click', () => { void processOptionAction('rejected'); });
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

    tr.querySelector('[data-action="cut"]').addEventListener('click', async () => {
      const decision = await confirmWithDiscordNotification({
        title: 'Cortar jugador',
        message: `Cut ${p.name || 'this player'}? This creates a dead contract and adds him to Free agents.`,
        confirmLabel: 'Cut',
        danger: true,
        defaultNotify: true,
      });
      if (!decision.confirmed) return;
      await api(`/api/players/${p.id}/cut`, {
        method: 'POST',
        body: JSON.stringify({
          notify_discord: decision.notifyDiscord,
          generate_discord_image: decision.generateDiscordImage,
        }),
      });
      await loadTeam(state.teamCode);
    });

    tr.querySelector('[data-action="delete"]').addEventListener('click', async () => {
      if (!confirm('Delete this player?')) return;
      await api(`/api/players/${p.id}`, { method: 'DELETE' });
      await loadTeam(state.teamCode);
    });

    const provisionalMaster = tr.querySelector('[data-role="provisional-amounts"]');
    if (provisionalMaster) {
      provisionalMaster.checked = playerUsesProvisionalAmounts(p);
      provisionalMaster.addEventListener('change', async () => {
        const previous = playerUsesProvisionalAmounts(p);
        const next = Boolean(provisionalMaster.checked);
        p.provisional_amounts = next ? 1 : 0;
        provisionalMaster.disabled = true;
        try {
          await api(`/api/players/${p.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ provisional_amounts: next }),
          });
          renderPlayers();
        } catch (err) {
          p.provisional_amounts = previous ? 1 : 0;
          provisionalMaster.checked = previous;
          alert(`Provisional amounts save failed: ${err.message}`);
        } finally {
          provisionalMaster.disabled = false;
        }
      });
    }

    const partialMaster = tr.querySelector('[data-role="partially-guaranteed"]');
    if (partialMaster) {
      partialMaster.checked = playerUsesPartialGuarantees(p);
      partialMaster.addEventListener('change', async () => {
        const previous = playerUsesPartialGuarantees(p);
        const next = Boolean(partialMaster.checked);
        p.partially_guaranteed = next ? 1 : 0;
        partialMaster.disabled = true;
        try {
          await api(`/api/players/${p.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ partially_guaranteed: next }),
          });
          renderPlayers();
        } catch (err) {
          p.partially_guaranteed = previous ? 1 : 0;
          partialMaster.checked = previous;
          alert(`Partially guaranteed save failed: ${err.message}`);
        } finally {
          partialMaster.disabled = false;
        }
      });
    }

    const notesMaster = tr.querySelector('[data-role="contract-notes"]');
    if (notesMaster) {
      notesMaster.checked = playerUsesContractNotes(p);
      notesMaster.addEventListener('change', async () => {
        const previous = playerUsesContractNotes(p);
        const next = Boolean(notesMaster.checked);
        p.contract_notes = next ? 1 : 0;
        notesMaster.disabled = true;
        try {
          await api(`/api/players/${p.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ contract_notes: next }),
          });
          renderPlayers();
        } catch (err) {
          p.contract_notes = previous ? 1 : 0;
          notesMaster.checked = previous;
          alert(`Contract notes save failed: ${err.message}`);
        } finally {
          notesMaster.disabled = false;
        }
      });
    }

    tbody.appendChild(frag);
  });
  if (state.ui.addingPlayer) appendAddPlayerRow(tbody);
  else appendAddPlayerTriggerRow(tbody);
  renderRosterTotals(rows, ALL_SEASONS);
  syncSelectAllPlayers();
  applySeasonColumnVisibility();
}

function renderRosterTotals(rows, seasons) {
  const tfoot = document.querySelector('#playersTable tfoot');
  if (!tfoot) return;
  const totals = seasons.map((season) => rows.reduce((sum, player) => sum + salaryDisplayNumericValue(player, season), 0));
  tfoot.innerHTML = `
    <tr class="roster-total-row">
      <td class="roster-total-label">Total</td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      ${totals.map((total) => `
        <td><span class="roster-total-amount">${formatMoneyDots(total)}</span></td>
      `).join('')}
      <td></td>
      <td></td>
    </tr>
  `;
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
      provisional_amounts: playerUsesProvisionalAmounts(p),
      partially_guaranteed: playerUsesPartialGuarantees(p),
    };
    ALL_SEASONS.forEach((season) => {
      payload[`salary_${season}_text`] = p[`salary_${season}_text`] || null;
      payload[`option_${season}`] = p[`option_${season}`] || null;
      payload[salaryProvisionalField(season)] = boolValue(p[salaryProvisionalField(season)]);
      payload[salaryPartialGuaranteeField(season)] = boolValue(p[salaryPartialGuaranteeField(season)]);
      payload[salaryGuaranteedTextField(season)] = p[salaryGuaranteedTextField(season)] || null;
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
  const decision = await confirmWithDiscordNotification({
    title: 'Cortar jugadores',
    message: `Cut ${players.length} selected player(s)? This creates dead contracts, adds them to Free agents, and removes them from the roster.`,
    confirmLabel: 'Cut selected',
    danger: true,
    defaultNotify: true,
  });
  if (!decision.confirmed) return;

  for (const p of players) {
    await api(`/api/players/${p.id}/cut`, {
      method: 'POST',
      body: JSON.stringify({
        notify_discord: decision.notifyDiscord,
        generate_discord_image: decision.generateDiscordImage,
      }),
    });
  }
  await loadTeam(state.teamCode);
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

function teamOptionsHtml(selected = '', { includeCurrent = true } = {}) {
  const selectedCode = String(selected || '').trim().toUpperCase();
  return state.teams
    .filter((team) => includeCurrent || team.code !== state.teamCode)
    .map((team) => `<option value="${team.code}" ${team.code === selectedCode ? 'selected' : ''}>${team.code} - ${escapeHtml(team.name || team.code)}</option>`)
    .join('');
}

function appendConditionalTeamSelect(list, value = '', { removable = true } = {}) {
  if (!list) return null;
  const row = document.createElement('div');
  row.className = 'pick-conditional-team-row';
  row.innerHTML = `
    <select data-conditional-team>
      <option value="">Select team</option>
      ${teamOptionsHtml(value, { includeCurrent: true })}
    </select>
    ${removable ? '<button type="button" class="ghost tiny" data-action="remove-conditional-team">Remove</button>' : ''}
  `;
  list.appendChild(row);
  row.querySelector('[data-action="remove-conditional-team"]')?.addEventListener('click', () => row.remove());
  return row.querySelector('select');
}

function renderConditionalTeamSelects(list, values) {
  if (!list) return;
  list.innerHTML = '';
  const normalized = parseDraftConditionalTeams(values);
  const rows = normalized.length >= 2 ? normalized : [...normalized, ...Array.from({ length: 2 - normalized.length }, () => '')];
  rows.forEach((code, idx) => appendConditionalTeamSelect(list, code, { removable: idx >= 2 }));
}

function readConditionalTeamSelects(container) {
  return Array.from(container.querySelectorAll('[data-conditional-team]'))
    .map((select) => String(select.value || '').trim().toUpperCase())
    .filter(Boolean)
    .filter((code, idx, all) => all.indexOf(code) === idx);
}

function appendSoldToTeamSelect(list, value = '', { removable = true } = {}) {
  if (!list) return null;
  const row = document.createElement('div');
  row.className = 'pick-conditional-team-row';
  row.innerHTML = `
    <select data-sold-to-team>
      <option value="">Select team</option>
      ${teamOptionsHtml(value, { includeCurrent: false })}
    </select>
    ${removable ? '<button type="button" class="ghost tiny" data-action="remove-sold-to-team">Remove</button>' : ''}
  `;
  list.appendChild(row);
  row.querySelector('[data-action="remove-sold-to-team"]')?.addEventListener('click', () => row.remove());
  return row.querySelector('select');
}

function renderSoldToTeamSelects(list, values) {
  if (!list) return;
  list.innerHTML = '';
  const normalized = parseDraftConditionalTeams(values);
  const rows = normalized.length ? normalized : [''];
  rows.forEach((code, idx) => appendSoldToTeamSelect(list, code, { removable: idx > 0 }));
}

function readSoldToTeamSelects(container) {
  return Array.from(container.querySelectorAll('[data-sold-to-team]'))
    .map((select) => String(select.value || '').trim().toUpperCase())
    .filter(Boolean)
    .filter((code, idx, all) => all.indexOf(code) === idx);
}

function renderAssets() {
  const board = document.getElementById('draftAssetsBoard');
  if (!board) return;
  board.innerHTML = '';

  const normalizedRound = (pick) => draftPickRound(pick);

  const normalizedType = (pick) => {
    const type = String(pick.draft_pick_type || 'own').trim().toLowerCase();
    if (type === 'acquired' || type === 'sold' || type === 'conditional') return type;
    return 'own';
  };

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

    const ownerOptions = teamOptionsHtml('', { includeCurrent: false });
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
            <option value="conditional">Conditional</option>
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
        <div data-sold-to-wrap class="pick-conditional-editor">
          <span>Possible drafting teams</span>
          <div data-sold-to-list></div>
          <button type="button" class="ghost tiny" data-action="add-sold-to-team">Add team</button>
        </div>
        <div data-conditional-wrap class="pick-conditional-editor">
          <span>Possible source teams</span>
          <div data-conditional-list></div>
          <button type="button" class="ghost tiny" data-action="add-conditional-team">Add team</button>
        </div>
        <label class="pick-detail-input">Details
          <textarea data-new-field="detail" rows="2"></textarea>
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
    const soldToWrap = card.querySelector('[data-sold-to-wrap]');
    const soldToList = card.querySelector('[data-sold-to-list]');
    const conditionalWrap = card.querySelector('[data-conditional-wrap]');
    const conditionalList = card.querySelector('[data-conditional-list]');
    renderConditionalTeamSelects(conditionalList, []);
    renderSoldToTeamSelects(soldToList, []);
    const syncOwnerField = () => {
      const type = typeSelect.value;
      ownerWrap.style.display = type === 'acquired' ? 'grid' : 'none';
      soldToWrap.style.display = type === 'sold' ? 'grid' : 'none';
      conditionalWrap.style.display = type === 'conditional' ? 'grid' : 'none';
      if (type !== 'acquired') ownerSelect.value = '';
    };
    syncOwnerField();
    typeSelect.addEventListener('change', syncOwnerField);
    card.querySelector('[data-action="add-conditional-team"]')?.addEventListener('click', () => {
      appendConditionalTeamSelect(conditionalList, '', { removable: true });
    });
    card.querySelector('[data-action="add-sold-to-team"]')?.addEventListener('click', () => {
      appendSoldToTeamSelect(soldToList, '', { removable: true });
    });

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
        draft_pick_sold_to: readSoldToTeamSelects(card),
        draft_pick_conditional_teams: readConditionalTeamSelects(card),
        draft_pick_restricted: Boolean(card.querySelector('[data-new-field="draft_pick_restricted"]')?.checked),
        draft_pick_protected: Boolean(card.querySelector('[data-new-field="draft_pick_protected"]')?.checked),
      };
      const hasContent = (
        payload.year !== defaultYear
        || Boolean(payload.detail)
        || Boolean(payload.original_owner)
        || payload.draft_pick_sold_to.length > 0
        || payload.draft_pick_conditional_teams.length > 0
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
      if (payload.draft_pick_type !== 'sold') payload.draft_pick_sold_to = [];
      if (payload.draft_pick_type !== 'conditional') payload.draft_pick_conditional_teams = [];
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
        const sourceTeams = parseDraftConditionalTeams(pick.draft_pick_conditional_teams);
        const ownerCode = pickType === 'conditional'
          ? (sourceTeams[0] || state.teamCode)
          : pick.draft_pick_type === 'acquired'
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
        if (pickType === 'conditional') card.classList.add('draft-pick-card--conditional');
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
                <option value="conditional">Conditional</option>
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
            <div data-sold-to-wrap class="pick-conditional-editor">
              <span>Possible drafting teams</span>
              <div data-sold-to-list></div>
              <button type="button" class="ghost tiny" data-action="add-sold-to-team">Add team</button>
            </div>
            <div data-conditional-wrap class="pick-conditional-editor">
              <span>Possible source teams</span>
              <div data-conditional-list></div>
              <button type="button" class="ghost tiny" data-action="add-conditional-team">Add team</button>
            </div>
            <label class="pick-detail-input">Details
              <textarea data-field="detail" rows="2">${escapeHtml(pick.detail || '')}</textarea>
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
        const soldToWrap = card.querySelector('[data-sold-to-wrap]');
        const soldToList = card.querySelector('[data-sold-to-list]');
        const conditionalWrap = card.querySelector('[data-conditional-wrap]');
        const conditionalList = card.querySelector('[data-conditional-list]');

        typeSelect.value = pick.draft_pick_type || 'own';
        roundSelect.value = pick.draft_round || normalizedRound(pick);
        ownerSelect.value = pick.original_owner || '';
        renderSoldToTeamSelects(soldToList, pick.draft_pick_sold_to);
        renderConditionalTeamSelects(conditionalList, pick.draft_pick_conditional_teams);

        const syncOwnerField = () => {
          const type = typeSelect.value;
          ownerWrap.style.display = type === 'acquired' ? 'grid' : 'none';
          soldToWrap.style.display = type === 'sold' ? 'grid' : 'none';
          conditionalWrap.style.display = type === 'conditional' ? 'grid' : 'none';
          if (type !== 'acquired') ownerSelect.value = '';
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
          const type = typeSelect.value;
          await persist({
            draft_pick_type: type,
            draft_round: roundSelect.value,
            original_owner: type === 'acquired' ? ownerSelect.value || null : null,
            draft_pick_sold_to: type === 'sold' ? readSoldToTeamSelects(card) : [],
            draft_pick_conditional_teams: type === 'conditional' ? readConditionalTeamSelects(card) : [],
          });
        });
        roundSelect.addEventListener('change', async () => {
          await persist({ draft_round: roundSelect.value });
        });
        ownerSelect.addEventListener('change', async () => {
          await persist({ original_owner: ownerSelect.value || null });
        });
        soldToList.addEventListener('change', async (event) => {
          if (!event.target?.matches?.('[data-sold-to-team]')) return;
          await persist({ draft_pick_sold_to: readSoldToTeamSelects(card) });
        });
        soldToList.addEventListener('click', async (event) => {
          if (!event.target?.matches?.('[data-action="remove-sold-to-team"]')) return;
          await persist({ draft_pick_sold_to: readSoldToTeamSelects(card) });
        });
        card.querySelector('[data-action="add-sold-to-team"]')?.addEventListener('click', () => {
          appendSoldToTeamSelect(soldToList, '', { removable: true });
        });
        card.querySelector('[data-action="add-conditional-team"]')?.addEventListener('click', () => {
          appendConditionalTeamSelect(conditionalList, '', { removable: true });
        });
        conditionalList.addEventListener('change', async (event) => {
          if (!event.target?.matches?.('[data-conditional-team]')) return;
          await persist({ draft_pick_conditional_teams: readConditionalTeamSelects(card) });
        });
        conditionalList.addEventListener('click', async (event) => {
          if (!event.target?.matches?.('[data-action="remove-conditional-team"]')) return;
          await persist({ draft_pick_conditional_teams: readConditionalTeamSelects(card) });
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
        d[key] = value;
        if (key.startsWith('salary_')) {
          const season = Number(key.split('_')[1] || 0);
          const parsed = parseAmount(value);
          if (Number.isFinite(season)) d[`salary_${season}_num`] = parsed;
        }
        renderImportantFigures();
        await refreshSummary();
      });

      if (key.startsWith('salary_')) {
        wrapper.classList.add('salary-edit');
      }
    });

    tr.querySelectorAll('[data-dead-flag]').forEach((checkbox) => {
      const key = checkbox.dataset.deadFlag;
      checkbox.checked = boolValue(d[key]);
      checkbox.addEventListener('change', async () => {
        const previous = boolValue(d[key]);
        const next = checkbox.checked;
        checkbox.disabled = true;
        try {
          await api(`/api/dead-contracts/${d.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ [key]: next }),
          });
          d[key] = next;
          renderImportantFigures();
          await refreshSummary();
        } catch (err) {
          checkbox.checked = previous;
          alert(`Dead contract flag save failed: ${err.message}`);
        } finally {
          checkbox.disabled = false;
        }
      });
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
      <td><label class="dead-exclusion-toggle"><input data-new-field="exclude_from_gasto" type="checkbox"></label></td>
      <td><label class="dead-exclusion-toggle"><input data-new-field="exclude_from_cap" type="checkbox"></label></td>
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
        exclude_from_gasto: Boolean(tr.querySelector('[data-new-field="exclude_from_gasto"]')?.checked),
        exclude_from_cap: Boolean(tr.querySelector('[data-new-field="exclude_from_cap"]')?.checked),
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
      <td colspan="11">
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
  syncTeamApronHardCapControls();
  syncTeamLuxuryRepeaterControl();
  renderTeamStrip();
  renderTeamPicker();
  renderAdminMobileTeamGrid();
  renderCards();
  renderPlayers();
  renderDeadContracts();
  renderExceptions();
  renderAssets();
  renderPlayerRights();
  renderImportantFigures();
  syncGmTimelineFromTeamData();
  applySeasonColumnVisibility();
  await refreshAdminLogsSafe();
}

async function fetchTrackerRowsFallback() {
  const season = freeAgencyModeActive() ? capHoldTargetSeason() : currentSeasonStart();
  const salaryCap = capForSeason(season);
  const luxuryCap = luxuryCapForSeason(season);
  const firstApron = firstApronForSeason(season);
  const secondApron = secondApronForSeason(season);
  const rows = await Promise.all(state.teams.map(async (t) => {
    const data = await api(`/api/teams/${t.code}`);
    const s = data.summary || {};
    const balances = teamSeasonBalances(data, season);
    const draftCounts = draftPickCountsFromAssets(data.assets || []);
    return {
      team_code: t.code,
      team_name: t.name,
      cap_total: Number(balances.cap_total || 0),
      gasto_total: Number(balances.gasto_total || 0),
      espacio_cap: salaryCap - Number(balances.cap_total || 0),
      espacio_luxury: luxuryCap - Number(balances.cap_total || 0),
      luxury_tax: Number(balances.luxury_tax || 0),
      espacio_1er_apron: firstApron - Number(balances.apron_account || 0),
      espacio_2do_apron: secondApron - Number(balances.apron_account || 0),
      roster_standard_count: Number(s.roster_standard_count || rosterCountFromPlayers(data.players || []).standard),
      roster_two_way_count: Number(s.roster_two_way_count || rosterCountFromPlayers(data.players || []).twoWay),
      draft_first_count: draftCounts.first,
      draft_second_count: draftCounts.second,
    };
  }));
  return rows;
}

async function loadTrackerEconomy(season = null) {
  const selected = normalizeTrackerEconomySeason(season ?? state.ui.trackerEconomySeason ?? currentSeasonStart());
  try {
    const res = await api(`/api/tracker/economy?season=${encodeURIComponent(selected)}`);
    state.trackerEconomyRows = res.rows || [];
    state.trackerEconomySeasons = res.seasons || [];
    state.ui.trackerEconomySeason = Number(res.season_year || selected);
  } catch (err) {
    if (!String(err.message || '').includes('API 404')) throw err;
    state.trackerEconomyRows = state.teams.map((team) => ({
      team_code: team.code,
      team_name: team.name,
      season_year: selected,
      balance: 0,
      revenue: 0,
      expenses: 0,
    }));
    state.trackerEconomySeasons = [selected];
    state.ui.trackerEconomySeason = selected;
  }
  renderTrackerEconomy();
  updateSortIndicators('trackerEconomyTable', state.sort.trackerEconomy);
}

async function loadTracker() {
  try {
    const res = await api('/api/tracker');
    state.trackerRows = res.tracker || [];
    if (freeAgencyModeActive()) {
      state.trackerRows = await fetchTrackerRowsFallback();
    }
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
  renderAdminMobileTeamGrid();
  renderTracker();
  await loadTrackerEconomy();
  renderImportantFigures();
  await refreshAdminLogsSafe();
}

async function loadFigures() {
  state.teamCode = null;
  state.teamData = null;
  state.selectedPlayerIds.clear();
  applyTeamTheme('');
  setViewMode('figures');
  setPageHeading('Cifras', 'Guía de importes derivados del Salary Cap');
  renderCapStatusPills({});
  renderTeamStrip();
  renderTeamPicker();
  renderAdminMobileTeamGrid();
  renderFigures();
  await refreshAdminLogsSafe();
}

async function loadFreeAgents() {
  const res = await api('/api/free-agents');
  state.freeAgents = res.free_agents || [];
  state.teamCode = null;
  state.teamData = null;
  state.selectedPlayerIds.clear();
  applyTeamTheme('');
  setViewMode('free-agents');
  setPageHeading('ANBA Free Agents', '');
  renderCapStatusPills({});
  renderTeamStrip();
  renderTeamPicker();
  renderAdminMobileTeamGrid();
  renderFreeAgents();
  await refreshAdminLogsSafe();
}

async function loadDraftOrder() {
  const res = await api('/api/draft-order');
  state.draftOrder = {
    draft_year: res.draft_year || currentSeasonStart() + 1,
    draft_order: res.draft_order || [],
  };
  state.teamCode = null;
  state.teamData = null;
  state.selectedPlayerIds.clear();
  applyTeamTheme('');
  setViewMode('draft-order');
  setPageHeading('Draft', `${state.draftOrder.draft_year} order of selection`);
  renderCapStatusPills({});
  renderTeamStrip();
  renderTeamPicker();
  renderAdminMobileTeamGrid();
  renderDraftOrder();
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
  const cashLimit = Number(state.teamData?.summary?.cash_limit_total || state.settings.cash_limit_total || 0);
  const cashReceivedAvailable = parseAmount(receivedInputEl.value);
  const cashSentAvailable = parseAmount(sentInputEl.value);
  if (cashReceivedAvailable == null || cashReceivedAvailable < 0 || cashReceivedAvailable > cashLimit) {
    alert('Invalid cash recibido available value.');
    return;
  }
  if (cashSentAvailable == null || cashSentAvailable < 0 || cashSentAvailable > cashLimit) {
    alert('Invalid cash enviado available value.');
    return;
  }
  const cashReceived = Math.max(0, cashLimit - cashReceivedAvailable);
  const cashSent = Math.max(0, cashLimit - cashSentAvailable);
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

function syncTeamApronHardCapControls() {
  const firstInput = document.getElementById('teamFirstApronCapInput');
  const secondInput = document.getElementById('teamSecondApronCapInput');
  if (!firstInput || !secondInput) return;
  const hardCap = String(state.teamData?.team?.apron_hard_cap || '').trim().toLowerCase();
  firstInput.checked = hardCap === 'first';
  secondInput.checked = hardCap === 'second';
}

async function saveTeamApronHardCap(nextHardCap) {
  if (!state.teamCode) {
    alert('No team selected.');
    syncTeamApronHardCapControls();
    return;
  }
  const firstInput = document.getElementById('teamFirstApronCapInput');
  const secondInput = document.getElementById('teamSecondApronCapInput');
  const inputs = [firstInput, secondInput].filter(Boolean);
  inputs.forEach((input) => { input.disabled = true; });
  try {
    await api(`/api/teams/${state.teamCode}`, {
      method: 'PATCH',
      body: JSON.stringify({ apron_hard_cap: nextHardCap || '' }),
    });
    await loadTeam(state.teamCode);
  } catch (err) {
    syncTeamApronHardCapControls();
    alert(`Apron cap save failed: ${err.message}`);
  } finally {
    inputs.forEach((input) => { input.disabled = false; });
  }
}

function setupTeamApronHardCapControls() {
  const firstInput = document.getElementById('teamFirstApronCapInput');
  const secondInput = document.getElementById('teamSecondApronCapInput');
  if (!firstInput || !secondInput) return;
  firstInput.addEventListener('change', async () => {
    if (firstInput.checked) {
      secondInput.checked = false;
      await saveTeamApronHardCap('first');
    } else {
      await saveTeamApronHardCap(secondInput.checked ? 'second' : '');
    }
  });
  secondInput.addEventListener('change', async () => {
    if (secondInput.checked) {
      firstInput.checked = false;
      await saveTeamApronHardCap('second');
    } else {
      await saveTeamApronHardCap(firstInput.checked ? 'first' : '');
    }
  });
}

function upsertLocalLuxuryHistory(year, repeater) {
  if (!state.teamData) return;
  const seasonYear = Number(year);
  const rows = Array.isArray(state.teamData.luxury_history)
    ? [...state.teamData.luxury_history]
    : [];
  const existing = rows.find((row) => Number(row.season_year) === seasonYear);
  if (existing) {
    existing.repeater = Boolean(repeater);
  } else {
    rows.push({ season_year: seasonYear, repeater: Boolean(repeater) });
  }
  rows.sort((a, b) => Number(b.season_year) - Number(a.season_year));
  state.teamData.luxury_history = rows;
}

function syncTeamLuxuryRepeaterControl() {
  const select = document.getElementById('teamLuxuryRepeaterCurrentSelect');
  if (!select) return;
  select.value = luxuryRepeaterForSeason(state.teamData, currentSeasonStart()) ? '1' : '0';
  select.disabled = !state.teamCode;
}

async function saveTeamLuxuryHistory(year, repeater) {
  if (!state.teamCode) {
    alert('No team selected.');
    syncTeamLuxuryRepeaterControl();
    return;
  }
  const seasonYear = Number(year);
  if (!Number.isInteger(seasonYear)) {
    alert('Invalid luxury season.');
    return;
  }
  const controls = [
    document.getElementById('teamLuxuryRepeaterCurrentSelect'),
    ...document.querySelectorAll(`[data-luxury-repeater-year="${seasonYear}"]`),
  ].filter(Boolean);
  controls.forEach((control) => { control.disabled = true; });
  try {
    await api(`/api/teams/${state.teamCode}/luxury-history`, {
      method: 'PATCH',
      body: JSON.stringify({ season_year: seasonYear, repeater: Boolean(repeater) }),
    });
    upsertLocalLuxuryHistory(seasonYear, Boolean(repeater));
    renderImportantFigures();
    syncTeamLuxuryRepeaterControl();
  } catch (err) {
    renderImportantFigures();
    syncTeamLuxuryRepeaterControl();
    alert(`Luxury history save failed: ${err.message}`);
  } finally {
    controls.forEach((control) => { control.disabled = false; });
  }
}

function setupTeamLuxuryRepeaterControl() {
  const select = document.getElementById('teamLuxuryRepeaterCurrentSelect');
  if (!select) return;
  select.addEventListener('change', async () => {
    await saveTeamLuxuryHistory(currentSeasonStart(), select.value === '1');
  });
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

function isoGmTimelineDate(value) {
  const date = parseGmTimelineDate(value);
  if (!date) return '';
  return date.toISOString().slice(0, 10);
}

function gmTimelineEntriesFromDom() {
  const rows = document.querySelectorAll('#gmTimelineRows [data-gm-row]');
  if (!rows.length) return null;
  return Array.from(rows).map((row, idx) => {
    const valueFor = (field) => String(row.querySelector(`[data-gm-field="${field}"]`)?.value || '').trim();
    return {
      gm_name: valueFor('gm_name'),
      start_date: valueFor('start_date'),
      color: valueFor('color') || gmTimelineDefaultColor(idx, state.teamCode),
    };
  });
}

function normalizeGmTimelineEntries(entries) {
  return (entries || [])
    .map((entry, idx) => ({
      gm_name: String(entry.gm_name || '').trim(),
      start_date: isoGmTimelineDate(entry.start_date),
      color: String(entry.color || gmTimelineDefaultColor(idx, state.teamCode)).trim(),
    }))
    .filter((entry) => entry.gm_name || entry.start_date)
    .sort((a, b) => {
      if (a.start_date < b.start_date) return -1;
      if (a.start_date > b.start_date) return 1;
      return a.gm_name.localeCompare(b.gm_name);
    });
}

function normalizedGmTimelineEntries() {
  const domEntries = gmTimelineEntriesFromDom();
  return normalizeGmTimelineEntries(domEntries || state.ui.gmTimelineEntries || []);
}

function validateGmTimelineEntries(entries) {
  if (!entries.length) return 'Add at least one GM row.';
  const invalid = entries.find((entry) => !entry.gm_name || !entry.start_date);
  if (invalid) return 'Every GM row needs a name and start date.';
  return '';
}

function renderGmTimelineRows() {
  const container = document.getElementById('gmTimelineRows');
  if (!container) return;
  const entries = state.ui.gmTimelineEntries || [];
  if (!entries.length) {
    container.innerHTML = '<tr><td colspan="4" class="gm-timeline-empty-cell">No GM history yet. Add a row to start.</td></tr>';
    return;
  }
  container.innerHTML = entries.map((entry, idx) => `
    <tr class="gm-timeline-row" data-gm-row="${idx}">
      <td><input type="text" data-gm-field="gm_name" value="${escapeHtml(entry.gm_name || '')}" placeholder="GM name"></td>
      <td><input type="date" data-gm-field="start_date" value="${escapeHtml(isoGmTimelineDate(entry.start_date))}"></td>
      <td><input type="color" data-gm-field="color" value="${escapeHtml(entry.color || gmTimelineDefaultColor(idx, state.teamCode))}"></td>
      <td><button type="button" class="danger" data-gm-remove="${idx}">Remove</button></td>
    </tr>
  `).join('');

  container.querySelectorAll('[data-gm-field]').forEach((input) => {
    const syncInputToState = () => {
      const row = input.closest('[data-gm-row]');
      const idx = Number(row?.dataset.gmRow);
      const field = input.dataset.gmField;
      if (!Number.isInteger(idx) || !field || !state.ui.gmTimelineEntries[idx]) return;
      state.ui.gmTimelineEntries[idx][field] = input.value;
    };
    input.addEventListener('input', syncInputToState);
    input.addEventListener('change', syncInputToState);
  });

  container.querySelectorAll('[data-gm-remove]').forEach((button) => {
    button.addEventListener('click', () => {
      const idx = Number(button.dataset.gmRemove);
      state.ui.gmTimelineEntries.splice(idx, 1);
      renderGmTimelineRows();
      renderGmTimelinePreview({ allowEmpty: true });
    });
  });
}

function setGmTimelineStatus(message, kind = '') {
  const status = document.getElementById('gmTimelineStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = `gm-timeline-status ${kind ? `gm-timeline-status--${kind}` : ''}`;
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
    return {
      entry,
      x,
      labelX,
      labelY,
      avatarY,
    };
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

function renderGmTimelinePreview(options = {}) {
  const preview = document.getElementById('gmTimelinePreview');
  if (!preview) return;
  const entries = normalizedGmTimelineEntries();
  const error = validateGmTimelineEntries(entries);
  if (error) {
    state.ui.gmTimelineSvg = '';
    preview.innerHTML = options.allowEmpty
      ? `<div class="gm-timeline-empty">${escapeHtml(error)}</div>`
      : '';
    return;
  }
  const svg = gmTimelineSvg(entries, state.teamCode);
  state.ui.gmTimelineSvg = svg;
  preview.innerHTML = svg;
}

function syncGmTimelineFromTeamData() {
  const code = state.teamCode || '';
  state.ui.gmTimelineEntries = (state.teamData?.gm_history || []).map((row, idx) => ({
    gm_name: row.gm_name || '',
    start_date: row.start_date || '',
    color: row.color || gmTimelineDefaultColor(idx, code),
  }));
  state.ui.gmTimelineSvg = '';
  renderGmTimelineRows();
  renderGmTimelinePreview({ allowEmpty: true });
  setGmTimelineStatus('');
}

async function saveGmTimeline(successMessage = 'Timeline saved.') {
  const entries = normalizedGmTimelineEntries();
  const error = validateGmTimelineEntries(entries);
  if (error) {
    alert(error);
    return false;
  }
  const button = document.getElementById('saveGmTimelineBtn');
  const oldText = button?.textContent || 'Save timeline';
  if (button) {
    button.disabled = true;
    button.textContent = 'Saving...';
  }
  try {
    const result = await api('/api/gm-history', {
      method: 'POST',
      body: JSON.stringify({
        team_code: state.teamCode,
        entries,
      }),
    });
    if (state.teamData) state.teamData.gm_history = result.gm_history || [];
    state.ui.gmTimelineEntries = (result.gm_history || []).map((row, idx) => ({
      gm_name: row.gm_name || '',
      start_date: row.start_date || '',
      color: row.color || gmTimelineDefaultColor(idx, state.teamCode),
    }));
    renderGmTimelineRows();
    renderGmTimelinePreview({ allowEmpty: true });
    setGmTimelineStatus(successMessage, 'success');
    return true;
  } catch (err) {
    setGmTimelineStatus(`Timeline save failed: ${err.message}`, 'error');
    return false;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
}

function addGmTimelineRow() {
  const idx = state.ui.gmTimelineEntries.length;
  state.ui.gmTimelineEntries.push({
    gm_name: '',
    start_date: '',
    color: gmTimelineDefaultColor(idx, state.teamCode),
  });
  renderGmTimelineRows();
}

function downloadGmTimelineSvg() {
  renderGmTimelinePreview();
  const svg = state.ui.gmTimelineSvg;
  if (!svg) {
    alert('Generate a valid timeline first.');
    return;
  }
  const code = state.teamCode || 'team';
  const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${code.toLowerCase()}-gm-timeline.svg`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function setupGmTimelineControls() {
  document.getElementById('addGmTimelineRowBtn')?.addEventListener('click', addGmTimelineRow);
  document.getElementById('saveGmTimelineBtn')?.addEventListener('click', () => { void saveGmTimeline(); });
  document.getElementById('generateGmTimelineBtn')?.addEventListener('click', async () => {
    renderGmTimelinePreview({ allowEmpty: true });
    if (!state.ui.gmTimelineSvg) return;
    const button = document.getElementById('generateGmTimelineBtn');
    const oldText = button?.textContent || 'Generate visual';
    if (button) {
      button.disabled = true;
      button.textContent = 'Saving...';
    }
    try {
      await saveGmTimeline('Visual generated and saved.');
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = oldText;
      }
    }
  });
  document.getElementById('downloadGmTimelineSvgBtn')?.addEventListener('click', downloadGmTimelineSvg);
}

function settingsForecastYears(startYear = currentSeasonStart()) {
  const start = Number(startYear || currentSeasonStart());
  return Array.from({ length: 6 }, (_, idx) => start + idx);
}

function capForecastInputValue(kind, season) {
  const direct = Number(state.settings[`${kind}_${season}`]);
  if (Number.isFinite(direct) && direct > 0) return direct;
  if (kind === 'salary_cap') return Number(state.settings.salary_cap_2025 || 0);
  if (kind === 'first_apron') return Number(state.settings.first_apron || 0);
  if (kind === 'second_apron') return Number(state.settings.second_apron || 0);
  return null;
}

function capForecastInputText(row, season) {
  const value = capForecastInputValue(row.kind, season);
  if (row.optional && (!Number.isFinite(value) || value <= 0)) return '';
  return formatDots(value || 0);
}

function renderSeasonCapSettingsGrid(startYear = currentSeasonStart()) {
  const wrap = document.getElementById('seasonCapSettingsGrid');
  if (!wrap) return;
  const currentYear = currentSeasonStart();
  const rows = [
    { kind: 'salary_cap', label: 'Salary cap' },
    { kind: 'first_apron', label: '1er Apron' },
    { kind: 'second_apron', label: '2do Apron' },
    { kind: 'average_salary', label: 'Average salary', optional: true },
  ];
  const seasons = settingsForecastYears(startYear);
  wrap.innerHTML = `
    <div class="table-wrap settings-cap-table-wrap">
      <table class="settings-cap-table">
        <thead>
          <tr>
            <th>Config</th>
            ${seasons.map((season) => `
              <th class="${season === currentYear ? 'is-current-year' : ''}">
                ${seasonSlashLabel(season)}
                ${season === currentYear ? '<span>actual</span>' : ''}
              </th>
            `).join('')}
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <th>${escapeHtml(row.label)}</th>
              ${seasons.map((season) => `
                <td>
                  <input
                    type="text"
                    inputmode="numeric"
                    data-season-cap-setting="${row.kind}_${season}"
                    aria-label="${escapeHtml(`${row.label} ${seasonSlashLabel(season)}`)}"
                    value="${escapeHtml(capForecastInputText(row, season))}"
                  >
                </td>
              `).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function collectSeasonCapSettingsPayload(selectedYear) {
  const payload = {};
  const inputs = document.querySelectorAll('[data-season-cap-setting]');
  inputs.forEach((input) => {
    const key = input.dataset.seasonCapSetting;
    if (!key) return;
    const rawValue = String(input.value || '').trim();
    if (key.startsWith('average_salary_') && !rawValue) {
      payload[key] = null;
      return;
    }
    const parsed = parseAmount(input.value);
    if (parsed == null || parsed <= 0) {
      throw new Error(`Invalid cap forecast for ${key.replaceAll('_', ' ')}.`);
    }
    payload[key] = parsed;
  });

  const currentSalaryCap = payload[`salary_cap_${selectedYear}`];
  const currentFirstApron = payload[`first_apron_${selectedYear}`];
  const currentSecondApron = payload[`second_apron_${selectedYear}`];
  if (currentSalaryCap == null || currentFirstApron == null || currentSecondApron == null) {
    throw new Error('Missing current-season cap forecast values.');
  }
  payload.salary_cap_2025 = currentSalaryCap;
  payload.first_apron = currentFirstApron;
  payload.second_apron = currentSecondApron;
  return payload;
}

function normalizeEconomySettingsSeason(value) {
  const parsed = Number(String(value || '').trim());
  if (Number.isInteger(parsed) && parsed >= 2000 && parsed <= 2100) return parsed;
  return currentSeasonStart();
}

function economySettingsRowsForTeams() {
  const byCode = new Map((state.economySettingsRows || []).map((row) => [String(row.team_code).toUpperCase(), row]));
  return state.teams.map((team) => ({
    team_code: team.code,
    team_name: team.name,
    balance: Number(byCode.get(team.code)?.balance || 0),
    revenue: Number(byCode.get(team.code)?.revenue || 0),
    expenses: Number(byCode.get(team.code)?.expenses || 0),
  }));
}

function renderEconomySettingsTable() {
  const tbody = document.querySelector('#economySettingsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const rows = sortedRows(economySettingsRowsForTeams(), state.sort.economySettings);
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <div class="settings-economy-team-cell">
          <strong>${escapeHtml(row.team_code)}</strong>
          <span>${escapeHtml(row.team_name || '')}</span>
        </div>
      </td>
      <td>
        <input type="text" inputmode="numeric" data-economy-team="${escapeHtml(row.team_code)}" data-economy-field="balance" value="${escapeHtml(formatDots(row.balance))}">
      </td>
      <td>
        <input type="text" inputmode="numeric" data-economy-team="${escapeHtml(row.team_code)}" data-economy-field="revenue" value="${escapeHtml(formatDots(row.revenue))}">
      </td>
      <td>
        <input type="text" inputmode="numeric" data-economy-team="${escapeHtml(row.team_code)}" data-economy-field="expenses" value="${escapeHtml(formatDots(row.expenses))}">
      </td>
    `;
    tbody.appendChild(tr);
  });
  updateSortIndicators('economySettingsTable', state.sort.economySettings);
}

async function loadEconomySettingsSeason(season = null) {
  const selected = normalizeEconomySettingsSeason(season ?? state.economySettingsSeason ?? currentSeasonStart());
  const input = document.getElementById('economySettingsSeasonInput');
  if (input) input.value = String(selected);
  const res = await api(`/api/tracker/economy?season=${encodeURIComponent(selected)}`);
  state.economySettingsRows = res.rows || [];
  state.economySettingsSeasons = res.seasons || [];
  state.economySettingsSeason = Number(res.season_year || selected);
  if (input) input.value = String(state.economySettingsSeason);
  renderEconomySettingsTable();
}

function collectEconomySettingsRows() {
  const grouped = new Map();
  document.querySelectorAll('[data-economy-team][data-economy-field]').forEach((input) => {
    const code = String(input.dataset.economyTeam || '').trim().toUpperCase();
    const field = String(input.dataset.economyField || '').trim();
    if (!code || !['balance', 'revenue', 'expenses'].includes(field)) return;
    if (!grouped.has(code)) grouped.set(code, { team_code: code });
    const rawValue = String(input.value || '').trim();
    const parsed = rawValue ? parseAmount(rawValue) : 0;
    if (parsed == null) {
      throw new Error(`Invalid ${field} value for ${code}.`);
    }
    grouped.get(code)[field] = parsed;
  });
  return Array.from(grouped.values());
}

async function saveEconomySettingsSeason() {
  const input = document.getElementById('economySettingsSeasonInput');
  const selected = normalizeEconomySettingsSeason(input?.value);
  if (input) input.value = String(selected);
  let rows = [];
  try {
    rows = collectEconomySettingsRows();
  } catch (err) {
    alert(err.message || String(err));
    return;
  }
  const res = await api('/api/tracker/economy', {
    method: 'PATCH',
    body: JSON.stringify({
      season_year: selected,
      rows,
    }),
  });
  state.economySettingsRows = res.rows || [];
  state.economySettingsSeasons = res.seasons || [];
  state.economySettingsSeason = Number(res.season_year || selected);
  renderEconomySettingsTable();
  if (Number(state.ui.trackerEconomySeason) === state.economySettingsSeason) {
    await loadTrackerEconomy(state.economySettingsSeason);
  }
  await refreshAdminLogsSafe();
  alert(`Economy data saved for ${seasonLabel(state.economySettingsSeason)}.`);
}

function setupEconomySettingsControls() {
  document.getElementById('loadEconomySettingsBtn')?.addEventListener('click', async () => {
    const input = document.getElementById('economySettingsSeasonInput');
    await loadEconomySettingsSeason(input?.value);
  });
  document.getElementById('saveEconomySettingsBtn')?.addEventListener('click', async () => {
    await saveEconomySettingsSeason();
  });
  document.getElementById('economySettingsSeasonInput')?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    void loadEconomySettingsSeason(event.currentTarget.value);
  });
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
  const cashLimitTotalInput = document.getElementById('cashLimitTotalInput');
  const tradeMoveLimitPre30Input = document.getElementById('tradeMoveLimitPre30Input');
  const tradeMoveLimitPost30Input = document.getElementById('tradeMoveLimitPost30Input');
  const rosterStandardMinInput = document.getElementById('rosterStandardMinInput');
  const rosterStandardMaxInput = document.getElementById('rosterStandardMaxInput');
  const rosterStandardOffseasonMaxInput = document.getElementById('rosterStandardOffseasonMaxInput');
  const rosterTwoWayMinInput = document.getElementById('rosterTwoWayMinInput');
  const rosterTwoWayMaxInput = document.getElementById('rosterTwoWayMaxInput');
  const tradeMovePhaseSelect = document.getElementById('tradeMovePhaseSelect');
  const currentYearSelect = document.getElementById('currentYearSelect');
  const freeAgencyModeInput = document.getElementById('freeAgencyModeInput');
  cashLimitTotalInput.value = formatDots(state.settings.cash_limit_total);
  tradeMoveLimitPre30Input.value = formatDots(state.settings.trade_move_limit_pre30);
  tradeMoveLimitPost30Input.value = formatDots(state.settings.trade_move_limit_post30);
  rosterStandardMinInput.value = formatDots(state.settings.roster_standard_min);
  rosterStandardMaxInput.value = formatDots(state.settings.roster_standard_max);
  rosterStandardOffseasonMaxInput.value = formatDots(state.settings.roster_standard_offseason_max);
  rosterTwoWayMinInput.value = formatDots(state.settings.roster_two_way_min);
  rosterTwoWayMaxInput.value = formatDots(state.settings.roster_two_way_max);
  tradeMovePhaseSelect.value = normalizeMoveBucket(state.settings.trade_move_phase);
  currentYearSelect.value = String(state.settings.current_year || 2025);
  if (freeAgencyModeInput) freeAgencyModeInput.checked = freeAgencyModeActive();
  renderSeasonCapSettingsGrid(Number(currentYearSelect.value || state.settings.current_year || 2025));
  currentYearSelect.addEventListener('change', () => {
    renderSeasonCapSettingsGrid(Number(currentYearSelect.value || state.settings.current_year || 2025));
  });

  const teamsRes = await api('/api/teams');
  state.teams = teamsRes.teams;
  setupSorting();
  renderTeamStrip();
  renderTeamPicker();
  renderAdminMobileTeamGrid();
  setupTradeModal();
  setupAdminMenu();
  setupAdminMobileNav();
  setupGmTimelineControls();
  setupFiguresSeasonControl();
  setupTrackerTabs();
  setupTrackerEconomySeasonControl();
  setupTeamTabs();
  setupEconomySettingsControls();
  await loadEconomySettingsSeason(Number(state.settings.current_year || 2025));
  document.getElementById('logActionFilter').addEventListener('change', () => { void loadAdminLogs(); });
  document.getElementById('logEntityFilter').addEventListener('change', () => { void loadAdminLogs(); });
  document.getElementById('refreshLogsBtn').addEventListener('click', () => { void loadAdminLogs(); });
  document.getElementById('refreshUsersBtn')?.addEventListener('click', () => { void loadAdminUsers(); });
  document.getElementById('refreshGmOptionRequestsBtn')?.addEventListener('click', () => { void loadGmOptionRequests(); });
  await loadGmOptionRequests();

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
  document.getElementById('figuresHomeBtn').addEventListener('click', async () => {
    await loadFigures();
  });
  document.getElementById('draftHomeBtn').addEventListener('click', async () => {
    await loadDraftOrder();
  });
  document.getElementById('freeAgentsHomeBtn').addEventListener('click', async () => {
    await loadFreeAgents();
  });
  document.getElementById('addDraftOrderFirstBtn').addEventListener('click', () => {
    state.ui.addingDraftOrderRound = '1st';
    renderDraftOrder();
  });
  document.getElementById('addDraftOrderSecondBtn').addEventListener('click', () => {
    state.ui.addingDraftOrderRound = '2nd';
    renderDraftOrder();
  });
  document.getElementById('addFreeAgentBtn').addEventListener('click', () => {
    state.ui.addingFreeAgent = true;
    renderFreeAgents();
  });
  document.getElementById('closeSignFreeAgentModalBtn').addEventListener('click', () => {
    closeSignFreeAgentModal();
  });
  document.getElementById('confirmSignFreeAgentBtn').addEventListener('click', async () => {
    await confirmSignFreeAgent();
  });
  document.getElementById('signFreeAgentModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeSignFreeAgentModal();
  });

  document.getElementById('saveSettingsBtn').addEventListener('click', async () => {
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
    const parsedRosterStandardMin = parseAmount(rosterStandardMinInput.value);
    const parsedRosterStandardMax = parseAmount(rosterStandardMaxInput.value);
    const parsedRosterStandardOffseasonMax = parseAmount(rosterStandardOffseasonMaxInput.value);
    const parsedRosterTwoWayMin = parseAmount(rosterTwoWayMinInput.value);
    const parsedRosterTwoWayMax = parseAmount(rosterTwoWayMaxInput.value);
    if (
      parsedRosterStandardMin == null
      || parsedRosterStandardMax == null
      || parsedRosterStandardOffseasonMax == null
      || parsedRosterStandardMin < 0
      || parsedRosterStandardMax < 0
      || parsedRosterStandardOffseasonMax < 0
      || parsedRosterStandardMin > parsedRosterStandardMax
      || parsedRosterStandardMax > parsedRosterStandardOffseasonMax
    ) {
      alert('Invalid standard roster limits.');
      return;
    }
    if (
      parsedRosterTwoWayMin == null
      || parsedRosterTwoWayMax == null
      || parsedRosterTwoWayMin < 0
      || parsedRosterTwoWayMax < 0
      || parsedRosterTwoWayMin > parsedRosterTwoWayMax
    ) {
      alert('Invalid two-way roster limits.');
      return;
    }
    const selectedYear = Number(currentYearSelect.value);
    if (!Number.isInteger(selectedYear) || selectedYear < 2025 || selectedYear > 2030) {
      alert('Invalid current year.');
      return;
    }
    let capForecastPayload = {};
    try {
      capForecastPayload = collectSeasonCapSettingsPayload(selectedYear);
    } catch (err) {
      alert(err.message || String(err));
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
        ...capForecastPayload,
        current_year: selectedYear,
        cash_limit_total: parsedCashLimitTotal,
        trade_move_limit_pre30: parsedTradeMoveLimitPre30,
        trade_move_limit_post30: parsedTradeMoveLimitPost30,
        trade_move_phase: selectedTradeMovePhase,
        free_agency_mode: Boolean(freeAgencyModeInput?.checked),
        roster_standard_min: parsedRosterStandardMin,
        roster_standard_max: parsedRosterStandardMax,
        roster_standard_offseason_max: parsedRosterStandardOffseasonMax,
        roster_two_way_min: parsedRosterTwoWayMin,
        roster_two_way_max: parsedRosterTwoWayMax,
      }),
    });
    state.settings = {
      ...state.settings,
      ...(result.settings || {}),
      cash_limit_total: result.settings?.cash_limit_total ?? parsedCashLimitTotal,
    };
    renderSeasonCapSettingsGrid(Number(state.settings.current_year || selectedYear));
    cashLimitTotalInput.value = formatDots(state.settings.cash_limit_total);
    tradeMoveLimitPre30Input.value = formatDots(state.settings.trade_move_limit_pre30);
    tradeMoveLimitPost30Input.value = formatDots(state.settings.trade_move_limit_post30);
    rosterStandardMinInput.value = formatDots(state.settings.roster_standard_min);
    rosterStandardMaxInput.value = formatDots(state.settings.roster_standard_max);
    rosterStandardOffseasonMaxInput.value = formatDots(state.settings.roster_standard_offseason_max);
    rosterTwoWayMinInput.value = formatDots(state.settings.roster_two_way_min);
    rosterTwoWayMaxInput.value = formatDots(state.settings.roster_two_way_max);
    tradeMovePhaseSelect.value = normalizeMoveBucket(state.settings.trade_move_phase);
    currentYearSelect.value = String(state.settings.current_year || 2025);
    if (freeAgencyModeInput) freeAgencyModeInput.checked = freeAgencyModeActive();
    if (state.ui.viewMode === 'team' && state.teamCode) {
      await loadTeam(state.teamCode);
    } else if (state.ui.viewMode === 'tracker') {
      await loadTracker();
    } else if (state.ui.viewMode === 'figures') {
      await loadFigures();
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
    renderSeasonCapSettingsGrid(Number(state.settings.current_year || previousYear + 1));
    cashLimitTotalInput.value = formatDots(state.settings.cash_limit_total);
    tradeMoveLimitPre30Input.value = formatDots(state.settings.trade_move_limit_pre30);
    tradeMoveLimitPost30Input.value = formatDots(state.settings.trade_move_limit_post30);
    rosterStandardMinInput.value = formatDots(state.settings.roster_standard_min);
    rosterStandardMaxInput.value = formatDots(state.settings.roster_standard_max);
    rosterStandardOffseasonMaxInput.value = formatDots(state.settings.roster_standard_offseason_max);
    rosterTwoWayMinInput.value = formatDots(state.settings.roster_two_way_min);
    rosterTwoWayMaxInput.value = formatDots(state.settings.roster_two_way_max);
    tradeMovePhaseSelect.value = normalizeMoveBucket(state.settings.trade_move_phase);
    currentYearSelect.value = String(state.settings.current_year || 2025);
    if (freeAgencyModeInput) freeAgencyModeInput.checked = freeAgencyModeActive();

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
  setupTeamApronHardCapControls();
  setupTeamLuxuryRepeaterControl();
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
