const MOVE_LIMIT_PRE30 = 20;
const MOVE_LIMIT_POST30 = 4;

const state = {
  teams: [],
  trackerRows: [],
  trackerSeasons: [],
  trackerEconomyRows: [],
  trackerEconomySeasons: [],
  leaguePlayers: [],
  freeAgents: [],
  waivers: [],
  gmNotifications: [],
  coadminVotes: [],
  wallet: {
    activeTab: 'clients',
    amountText: '',
    season: null,
    seasons: [],
    rows: [],
    appealRows: [],
    appealColumns: [],
    appealRankings: [],
    appealLoading: false,
    appealError: '',
    appealSelectedFreeAgentId: null,
    clients: [],
    clientsPage: 1,
    expandedClientIds: new Set(),
    expandedFavoriteClientIds: new Set(),
    clientsSort: { key: 'interest_count', dir: 'desc' },
    agentName: '',
    missingAgent: false,
    clientsLoading: false,
    clientsError: '',
    loading: false,
    error: '',
  },
  gmOffice: {
    teamCode: '',
    teamName: '',
    offers: [],
    favorites: [],
    loading: false,
    error: '',
  },
  draftOrder: {
    draft_year: null,
    draft_order: [],
  },
  draftLedger: null,
  draftLive: null,
  teamCode: null,
  teamData: null,
  auth: null,
  csrfToken: null,
  settings: {
    salary_cap_2025: 154647000,
    salary_floor_2025: 139182300,
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
    free_agency_mode: false,
    free_agent_reps: [],
    free_agent_rep_discord_ids: {},
  },
  sort: {
    tracker: { key: 'team_code', dir: 'asc' },
    trackerEconomy: { key: 'balance', dir: 'desc' },
    players: { key: 'position', dir: 'asc' },
    dead_contracts: { key: 'label', dir: 'asc' },
    exceptions: { key: 'label', dir: 'asc' },
    player_rights: { key: 'label', dir: 'asc' },
    league_players: { key: 'name', dir: 'asc' },
    free_agents: { key: 'name', dir: 'asc' },
  },
  ui: {
    viewMode: 'tracker',
    activeTrackerTab: 'general',
    activeTeamTab: 'economy',
    rosterView: 'list',
    seasonViewStart: null,
    figuresSeasonStart: null,
    ownerOfficeSeason: null,
    trackerSeason: null,
    trackerEconomySeason: null,
    freeAgentSearch: '',
    contractCalculator: {
      firstAmount: '',
      years: 5,
      raisePct: 8,
    },
    freeAgentsPage: 1,
    freeAgentsPageSize: 50,
    leaguePlayersPage: 1,
    leaguePlayersPageSize: 50,
    freeAgentActionId: null,
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
    cashTransfers: {},
    seasonStart: null,
    loading: false,
    validationResult: null,
    validationSignature: null,
    validationLoadingSignature: null,
    validationErrorSignature: null,
    validationError: null,
  },
  filters: {
    guaranteedOnly: false,
    optionsOnly: false,
    showEmptyYears: true,
  },
};

let draftLiveTimer = null;
let draftLivePollTimer = null;
let gmNotificationsPollTimer = null;

const SEASON_WINDOW_SIZE = 6;
const TRADE_MACHINE_MIN_TEAMS = 2;
const TRADE_MACHINE_MAX_TEAMS = 6;
const TRADE_DRAFT_YEAR_WINDOW = 7;
const PAGINATED_TABLE_PAGE_SIZES = [50, 100, 200];
const PAGINATED_TABLE_CONFIG = {
  freeAgents: { tableId: 'freeAgentsTable', pageKey: 'freeAgentsPage', sizeKey: 'freeAgentsPageSize' },
  leaguePlayers: { tableId: 'leaguePlayersTable', pageKey: 'leaguePlayersPage', sizeKey: 'leaguePlayersPageSize' },
};
const FREE_AGENT_PRIMARY_SORT_CYCLE = [
  { key: 'name', dir: 'asc', label: 'Nombre' },
  { key: 'rating', dir: 'desc', label: 'Rating' },
  { key: 'position', dir: 'asc', label: 'Posición' },
];
const TRADE_PICK_ACTION_SEND = 'send_pick';
const TRADE_PICK_ACTION_SWAP = 'swap_rights';
const LAST_TEAM_STORAGE_KEY = 'anba_last_team_code';
const TAXPAYER_MLE_BASE_AMOUNT = 6_064_000;
const TAXPAYER_MLE_BASE_CAP = 165_000_000;
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
  {
    id: 'owner-office',
    sections: ['ownerOfficeSection'],
    requiresOwnerOffice: true,
  },
];

const OWNER_OFFICE_INCOME_ROWS = [
  { key: 'recaudacion', label: 'Recaudación', type: 'category' },
  { key: 'media_espectadores', label: 'Media espectadores', type: 'field' },
  { key: 'entradas_regular_season', label: 'Entradas Regular Season', type: 'field' },
  { key: 'partidos_playoffs', label: 'Partidos playoffs', type: 'field' },
  { key: 'entradas_playoffs', label: 'Entradas Playoffs', type: 'field' },
  { key: 'precio_medio_entrada', label: 'Precio medio entrada', type: 'field' },
  { key: 'consumiciones', label: 'Consumiciones', type: 'field' },
  { key: 'merchandising', label: 'Merchandising', type: 'category' },
  { key: 'ventas_camisetas_ropa', label: 'Ventas de camisetas y ropa', type: 'field' },
  { key: 'precio_medio_articulo', label: 'Precio medio artículo', type: 'field' },
  { key: 'derechos', label: 'Derechos', type: 'category' },
  { key: 'tv_globales', label: 'TV globales', type: 'field' },
  { key: 'tv_local', label: 'TV local', type: 'field' },
  { key: 'licencias', label: 'Licencias', type: 'field' },
  { key: 'sponsor', label: 'Sponsor', type: 'category' },
  { key: 'patrocinador_jersey', label: 'Patrocinador jersey', type: 'field' },
  { key: 'patrocinador_estadio', label: 'Patrocinador estadio', type: 'field' },
  { key: 'patrocinadores_generales', label: 'Patrocinadores generales', type: 'field' },
  { key: 'flujos_caja_positivos', label: 'Flujos de caja positivos', type: 'category' },
  { key: 'traspasos_positivos', label: 'Traspasos', type: 'field' },
  { key: 'bonificaciones', label: 'Bonificaciones', type: 'field' },
  { key: 'reparto_beneficios_positivo', label: 'Reparto beneficios', type: 'field' },
  { key: 'reparto_impuesto_lujo', label: 'Reparto impuesto de lujo', type: 'field' },
];

const OWNER_OFFICE_EXPENSE_ROWS = [
  { key: 'coste_plantilla', label: 'Coste plantilla', type: 'category' },
  { key: 'salarios', label: 'Salarios', type: 'field' },
  { key: 'multa', label: 'Multa', type: 'field' },
  { key: 'cuerpo_tecnico', label: 'Cuerpo técnico', type: 'category' },
  { key: 'multiplicador_exitos', label: 'Multiplicador éxitos', type: 'field' },
  { key: 'gastos_cuerpo_tecnico', label: 'Gastos', type: 'field' },
  { key: 'gastos_estadio', label: 'Gastos de estadio', type: 'category' },
  { key: 'partidos', label: 'Partidos', type: 'field' },
  { key: 'gastos_partido', label: 'Gastos partido', type: 'field' },
  { key: 'indice_coste_estadio', label: 'Índice coste', type: 'field' },
  { key: 'gastos_television', label: 'Gastos de televisión', type: 'category' },
  { key: 'produccion', label: 'Producción', type: 'field' },
  { key: 'costes_marketing', label: 'Costes de marketing', type: 'category' },
  { key: 'indice_coste_marketing', label: 'Índice coste', type: 'field' },
  { key: 'costes_ineficiencia', label: 'Costes ineficiencia', type: 'field' },
  { key: 'unidades', label: 'Unidades', type: 'field' },
  { key: 'coste_por_unidad', label: 'Coste por unidad', type: 'field' },
  { key: 'gastos_operativos', label: 'Gastos operativos', type: 'category' },
  { key: 'gastos_operativos_valor', label: 'Gastos', type: 'field' },
  { key: 'indice_coste_operativo', label: 'Índice coste', type: 'field' },
  { key: 'flujos_caja_negativos', label: 'Flujos de caja negativos', type: 'category' },
  { key: 'traspasos_negativos', label: 'Traspasos', type: 'field' },
  { key: 'sanciones', label: 'Sanciones', type: 'field' },
  { key: 'reparto_beneficios_negativo', label: 'Reparto beneficios', type: 'field' },
];

const OWNER_OFFICE_RESULT_OPTIONS = [
  '',
  'Campeón',
  'Finalista',
  'Final de conferencia',
  'Semifinal de conferencia',
  'Primera ronda',
  'Play-in',
  'Lotería',
  'Reconstrucción',
];

const OWNER_SEASON_OBJECTIVE_OPTIONS = [
  '',
  'Campeones',
  'Finalistas',
  'Final de conferencia',
  'Segunda ronda',
  'Primera ronda',
  'Entrar en play-in',
  'Luchar por el play-in',
  'Desarrollo de jóvenes',
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

function freeAgencyModeActive() {
  return boolValue(state.settings.free_agency_mode);
}

function defaultSeasonViewStart() {
  const currentYear = currentSeasonStart();
  return currentYear;
}

function availableSeasonViewStarts() {
  const currentYear = currentSeasonStart();
  return Array.from({ length: SEASON_WINDOW_SIZE }, (_, idx) => currentYear + idx);
}

function normalizeSeasonViewStart(value) {
  const starts = availableSeasonViewStarts();
  if (value === null || value === undefined || value === '') {
    const defaultStart = defaultSeasonViewStart();
    return starts.includes(defaultStart) ? defaultStart : starts[0];
  }
  const requested = Number(value);
  if (starts.includes(requested)) return requested;
  const defaultStart = defaultSeasonViewStart();
  return starts.includes(defaultStart) ? defaultStart : starts[0];
}

function selectedSeasonStart() {
  const normalized = normalizeSeasonViewStart(state.ui.seasonViewStart);
  state.ui.seasonViewStart = normalized;
  return normalized;
}

function normalizeFiguresSeasonStart(value) {
  const starts = availableSeasonViewStarts();
  const requested = Number(value);
  return starts.includes(requested) ? requested : starts[0];
}

function selectedFiguresSeasonStart() {
  const normalized = normalizeFiguresSeasonStart(state.ui.figuresSeasonStart ?? currentSeasonStart());
  state.ui.figuresSeasonStart = normalized;
  return normalized;
}

function trackerSeasonOptions() {
  const seasons = new Set(
    (state.trackerSeasons || [])
      .map((season) => Number(season))
      .filter((season) => Number.isInteger(season) && availableSeasonViewStarts().includes(season))
  );
  availableSeasonViewStarts().forEach((season) => seasons.add(season));
  return Array.from(seasons).sort((a, b) => a - b);
}

function normalizeTrackerSeason(value) {
  const options = trackerSeasonOptions();
  const requested = Number(value);
  if (options.includes(requested)) return requested;
  const defaultStart = defaultSeasonViewStart();
  return options.includes(defaultStart) ? defaultStart : (options[0] || currentSeasonStart());
}

function selectedTrackerSeason() {
  const normalized = normalizeTrackerSeason(state.ui.trackerSeason);
  state.ui.trackerSeason = normalized;
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

function visibleSeasonYears() {
  const start = selectedSeasonStart();
  return Array.from({ length: SEASON_WINDOW_SIZE }, (_, idx) => start + idx);
}

function hasGmLevelRole(role) {
  return ['gm', 'co_admin'].includes(String(role || '').trim().toLowerCase());
}

function canViewGmNotifications() {
  return Boolean(state.auth?.authenticated && hasGmLevelRole(state.auth?.role));
}

function gmNotificationHtml(notification) {
  const id = escapeHtml(notification?.id);
  const kind = escapeHtml(notification?.kind || 'info');
  const title = escapeHtml(notification?.title || 'Notificación');
  const body = String(notification?.body || '').trim();
  return `
    <article class="gm-notification-card gm-notification-card--${kind}">
      <div class="gm-notification-copy">
        <strong>${title}</strong>
        ${body ? `<p>${escapeHtml(body)}</p>` : ''}
      </div>
      <button type="button" data-gm-notification-read="${id}">Cerrar</button>
    </article>
  `;
}

function renderGmNotifications() {
  const panel = document.getElementById('gmNotificationsPanel');
  if (!panel) return;
  const notifications = Array.isArray(state.gmNotifications) ? state.gmNotifications : [];
  panel.classList.toggle('section-hidden', !notifications.length);
  if (!notifications.length) {
    panel.innerHTML = '';
    return;
  }
  panel.innerHTML = `
    <div class="gm-notifications-head">
      <strong>Notificaciones</strong>
      <span>${notifications.length} pendiente${notifications.length === 1 ? '' : 's'}</span>
    </div>
    <div class="gm-notifications-list">
      ${notifications.map((notification) => gmNotificationHtml(notification)).join('')}
    </div>
  `;
  panel.querySelectorAll('[data-gm-notification-read]').forEach((button) => {
    button.addEventListener('click', async () => {
      const id = Number(button.dataset.gmNotificationRead);
      if (!Number.isFinite(id)) return;
      button.disabled = true;
      try {
        await api(`/api/me/notifications/${id}/read`, { method: 'POST', body: '{}' });
        state.gmNotifications = notifications.filter((notification) => Number(notification.id) !== id);
        renderGmNotifications();
      } catch (err) {
        console.error(err);
        button.disabled = false;
      }
    });
  });
}

async function loadGmNotifications() {
  if (!canViewGmNotifications()) {
    state.gmNotifications = [];
    renderGmNotifications();
    return;
  }
  const data = await api('/api/me/notifications?unread=1&limit=10');
  state.gmNotifications = Array.isArray(data.notifications) ? data.notifications : [];
  renderGmNotifications();
}

function startGmNotificationsPolling() {
  if (gmNotificationsPollTimer) {
    clearInterval(gmNotificationsPollTimer);
    gmNotificationsPollTimer = null;
  }
  if (!canViewGmNotifications()) return;
  gmNotificationsPollTimer = setInterval(() => {
    if (document.hidden) return;
    loadGmNotifications().catch((err) => console.warn('Could not refresh GM notifications', err));
  }, 45000);
}

function isCoAdminRole(role) {
  return String(role || '').trim().toLowerCase() === 'co_admin';
}

function canViewWallet() {
  const role = String(state.auth?.role || '').trim().toLowerCase();
  return Boolean(state.auth?.authenticated && ['admin', 'co_admin'].includes(role));
}

function canViewGmOffice() {
  const auth = state.auth || {};
  return Boolean(auth.authenticated && (auth.role === 'admin' || hasGmLevelRole(auth.role)) && freeAgentActionTeamCodes().length);
}

function canViewOwnerOfficeForTeam(code = state.teamCode) {
  const auth = state.auth || {};
  if (!auth.authenticated) return false;
  if (auth.role === 'admin') return true;
  if (!hasGmLevelRole(auth.role)) return false;
  const teamCodes = Array.isArray(auth.team_codes)
    ? auth.team_codes.map((teamCode) => String(teamCode || '').toUpperCase()).filter(Boolean)
    : [];
  return teamCodes.includes(String(code || '').toUpperCase());
}

function visibleTeamTabs() {
  return TEAM_TABS.filter((tab) => !tab.requiresOwnerOffice || canViewOwnerOfficeForTeam());
}

function teamTabForSection(sectionId) {
  return visibleTeamTabs().find((tab) => tab.sections.includes(sectionId))?.id || null;
}

function activeTeamTab() {
  const tabs = visibleTeamTabs();
  return tabs.some((tab) => tab.id === state.ui.activeTeamTab)
    ? state.ui.activeTeamTab
    : (tabs[0]?.id || TEAM_TABS[0].id);
}

function syncTeamTabs() {
  const showTeam = state.ui.viewMode === 'team';
  const active = activeTeamTab();
  const tabs = document.getElementById('teamTabs');
  if (tabs) tabs.classList.toggle('section-hidden', !showTeam);

  document.querySelectorAll('[data-team-tab]').forEach((btn) => {
    const tab = TEAM_TABS.find((item) => item.id === btn.dataset.teamTab);
    const allowed = Boolean(tab && (!tab.requiresOwnerOffice || canViewOwnerOfficeForTeam()));
    btn.classList.toggle('section-hidden', !showTeam || !allowed);
    const isActive = allowed && btn.dataset.teamTab === active;
    btn.classList.toggle('is-active', isActive);
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });

  TEAM_TABS.forEach((tab) => {
    const allowed = !tab.requiresOwnerOffice || canViewOwnerOfficeForTeam();
    tab.sections.forEach((sectionId) => {
      const section = document.getElementById(sectionId);
      if (!section) return;
      const forceHidden = sectionId === 'gmTimelineSection' && !hasTeamGmTimelineEntries();
      section.classList.toggle('section-hidden', !showTeam || !allowed || tab.id !== active || forceHidden);
    });
  });
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

function setupTrackerSeasonControl() {
  const select = document.getElementById('trackerSeasonSelect');
  if (!select) return;
  select.addEventListener('change', async () => {
    state.ui.trackerSeason = Number(select.value);
    await loadTracker(state.ui.trackerSeason);
  });
}

function setTeamTab(tabId) {
  const tabs = visibleTeamTabs();
  state.ui.activeTeamTab = tabs.some((tab) => tab.id === tabId) ? tabId : (tabs[0]?.id || TEAM_TABS[0].id);
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

function normalizeBirdYears(value) {
  const compact = String(value ?? '').trim().replace(/\s+/g, '').replace(',', '.');
  if (!compact || compact === '0') return '';
  if (compact === '1' || compact === '1.0') return '1';
  if (compact === '2' || compact === '2.0') return '2';
  if (compact === '2+') return '2+';
  return '';
}

function birdYearsSortValue(value) {
  const normalized = normalizeBirdYears(value);
  if (!normalized) return null;
  return normalized === '2+' ? 3 : Number(normalized);
}

function capHoldBirdCodeFromYears(value) {
  const normalized = normalizeBirdYears(value);
  if (normalized === '1') return 'NB';
  if (normalized === '2') return 'EB';
  if (normalized === '2+') return 'FB';
  return '';
}

function birdYearsCellHtml(value) {
  const normalized = normalizeBirdYears(value);
  if (!normalized) return '';
  const plusClass = normalized === '2+' ? ' bird-years-pill--plus' : '';
  return `<span class="bird-years-pill${plusClass}">${escapeHtml(normalized)}</span>`;
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
  const hold = capHoldInfo(obj, season);
  if (hold.displayable) return true;
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

function playerHasVisibleCapHold(player) {
  return visibleSeasonYears().some((season) => capHoldInfo(player, season).displayable);
}

function salaryCellHtml(obj, season, showEmptyYears = true) {
  const capHold = capHoldInfo(obj, season);
  if (capHold.displayable) {
    const gmActions = gmOptionRequestActionsHtml(obj, season, seasonOptionCode(obj, season));
    const birdRightsActions = gmBirdRightsRenounceRequestHtml(obj, season, seasonSalaryTextCode(obj, season));
    const qoAcceptedHtml = qoAcceptedIndicatorHtml(obj, season);
    const seasonCap = capForSeason(season);
    const capHoldAmount = Number(capHold.amount || 0);
    const qoValue = Number(capHold.displayAmount || 0);
    const pct = capHoldAmount > 0 && seasonCap > 0
      ? `${((capHoldAmount / seasonCap) * 100).toFixed(1)}%`
      : '';
    const main = capHoldAmount > 0 ? formatDots(capHoldAmount) : escapeHtml(capHold.label || 'Hold TBD');
    const message = capHold.message || 'Cap hold pending';
    const qoValueHtml = qoValue > 0
      ? `<span class="salary-cap-hold-qo-value">Valor QO = ${formatDots(qoValue)}</span>`
      : '';
    return `
      <div class="salary-cap-hold-cell">
        <div class="salary-chip salary-chip--cap-hold ${capHold.pending ? 'salary-chip--cap-hold-pending' : ''}">
          <span class="salary-chip-main">${main}</span>
          ${pct ? `<span class="salary-chip-pct">${pct}</span>` : ''}
        </div>
        <div class="salary-cap-hold-side">
          <span class="salary-cap-hold-ref">${escapeHtml(capHold.shortLabel || 'Cap hold')}</span>
          ${salaryInfoHtml([message])}
          ${qoValueHtml}
          ${qoAcceptedHtml}
          ${gmActions}
          ${birdRightsActions}
        </div>
      </div>
    `;
  }

  const text = obj[`salary_${season}_text`];
  const num = obj[`salary_${season}_num`];
  const option = obj[`option_${season}`];
  const optClass = contractOptionClass(option);
  const textTagClass = salaryTextTagClass(text);
  const textTagCode = String(text || '').trim().toUpperCase();
  const optionCode = String(option || '').trim().toUpperCase();
  const hideOptionTag = ['FB', 'EB', 'NB'].includes(textTagCode) || ['FB', 'EB', 'NB'].includes(optionCode);
  const cap = capForSeason(season) || 154647000;
  const isProvisional = playerSeasonIsProvisional(obj, season);
  const isPartiallyGuaranteed = playerSeasonIsPartiallyGuaranteed(obj, season);
  const hasContractNote = playerSeasonHasContractNote(obj, season);
  const infoMessages = salaryInfoMessages(obj, season);
  const infoHtml = salaryInfoHtml(infoMessages);
  const gmActions = gmOptionRequestActionsHtml(obj, season, optionCode);
  const qoAcceptedHtml = qoAcceptedIndicatorHtml(obj, season);
  const salaryStateClasses = [
    isProvisional ? 'salary-chip--provisional' : '',
    isPartiallyGuaranteed ? 'salary-chip--partial-guarantee' : '',
    hasContractNote ? 'salary-chip--note' : '',
  ].filter(Boolean).join(' ');

  if (num !== null && num !== undefined && Number.isFinite(Number(num))) {
    const val = Number(num);
    const pct = cap > 0 ? `${((val / cap) * 100).toFixed(1)}%` : '';
    const sideHtml = `${qoAcceptedHtml}${gmActions}`;
    return `
      <div class="salary-cell-with-side">
        <div class="salary-chip ${optClass} ${salaryStateClasses}">
          <span class="salary-chip-main">${formatDots(val)}</span>
          <span class="salary-chip-pct">${pct}</span>
          ${infoHtml}
        </div>
        ${sideHtml ? `<div class="salary-cell-side">${sideHtml}</div>` : ''}
      </div>
    `;
  }

  if (text !== null && text !== undefined && String(text).trim() !== '') {
    const upper = escapeHtml(String(text).trim().toUpperCase());
    const sideHtml = `${qoAcceptedHtml}${gmActions}`;
    return `
      <div class="salary-cell-with-side">
        <div class="salary-chip salary-chip-text ${textTagClass} ${hideOptionTag ? '' : optClass} ${salaryStateClasses}">
          <span class="salary-chip-main">${upper}</span>
          ${infoHtml}
        </div>
        ${sideHtml ? `<div class="salary-cell-side">${sideHtml}</div>` : ''}
      </div>
    `;
  }

  if (!showEmptyYears && !gmActions && !qoAcceptedHtml) return '';
  const sideHtml = `${qoAcceptedHtml}${gmActions}`;
  return `
    <div class="salary-cell-with-side salary-cell-with-side--empty">
      <div class="salary-empty-wrap ${isProvisional ? 'salary-empty-wrap--provisional' : ''} ${isPartiallyGuaranteed ? 'salary-empty-wrap--partial-guarantee' : ''} ${hasContractNote ? 'salary-empty-wrap--note' : ''}">
        <div class="salary-empty-bar" aria-hidden="true"></div>
        ${infoHtml}
      </div>
      ${sideHtml ? `<div class="salary-cell-side">${sideHtml}</div>` : ''}
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

function salaryHistoryNumericValue(row, season) {
  const direct = row?.[`salary_${season}_history_num`];
  if (direct !== null && direct !== undefined && direct !== '' && Number.isFinite(Number(direct))) {
    return Number(direct);
  }
  return parseAmountLike(row?.[`salary_${season}_history_text`]) || 0;
}

function capHoldPreviousSalaryValue(row, season) {
  const previousSeason = Number(season) - 1;
  const directSalary = salaryNumericValue(row, previousSeason);
  return directSalary > 0 ? directSalary : salaryHistoryNumericValue(row, previousSeason);
}

function salaryTextIndicatesMinimum(value) {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[.\s]/g, '');
  return ['min', 'minimo', 'minimum'].includes(normalized) || normalized.startsWith('minimo');
}

function capHoldPreviousSalaryIsMinimum(row, season) {
  const previousSeason = Number(season) - 1;
  return salaryTextIndicatesMinimum(row?.[`salary_${previousSeason}_text`])
    || salaryTextIndicatesMinimum(row?.[`salary_${previousSeason}_history_text`]);
}

function seasonSalaryTextCode(row, season) {
  return String(row?.[`salary_${season}_text`] || '').trim().toUpperCase();
}

function seasonOptionCode(row, season) {
  return String(row?.[`option_${season}`] || '').trim().toUpperCase();
}

function optionDecisionForSeason(row, season) {
  return row?.option_decisions?.[`option_${season}`] || null;
}

function optionAcceptedByTeam(row, season, expectedOption = '') {
  const option = seasonOptionCode(row, season);
  const decision = optionDecisionForSeason(row, season);
  if (!['QO', 'GAP'].includes(option) || !decision) return false;
  const expected = String(expectedOption || '').trim().toUpperCase();
  if (expected && option !== expected) return false;
  const decisionOption = String(decision.option_value || '').trim().toUpperCase();
  const action = String(decision.action || '').trim().toLowerCase();
  const status = String(decision.status || '').trim().toLowerCase();
  return decisionOption === option
    && action === 'accepted'
    && status === 'approved';
}

function qoAcceptedByTeam(row, season) {
  return optionAcceptedByTeam(row, season, 'QO');
}

function acceptedOptionLabel(optionValue) {
  return 'QO aceptada por el equipo';
}

function optionAcceptedIndicatorHtml(row, season) {
  const option = seasonOptionCode(row, season);
  if (!optionAcceptedByTeam(row, season, option)) return '';
  const label = acceptedOptionLabel(option);
  return `<span class="qo-accepted-indicator" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">✓</span>`;
}

function qoAcceptedIndicatorHtml(row, season) {
  return optionAcceptedIndicatorHtml(row, season);
}

function canSubmitGmOptionRequest(row, season, optionCode) {
  if (!row?.id) return false;
  const option = String(optionCode || '').trim().toUpperCase();
  if (!['TO', 'QO', 'GAP'].includes(option)) return false;
  const auth = state.auth || {};
  if (!auth.authenticated || !hasGmLevelRole(auth.role)) return false;
  const teamCodes = Array.isArray(auth.team_codes)
    ? auth.team_codes.map((code) => String(code || '').toUpperCase()).filter(Boolean)
    : [];
  return teamCodes.includes(String(state.teamCode || '').toUpperCase());
}

function gmOptionRequestActionsHtml(row, season, optionCode) {
  const option = String(optionCode || '').trim().toUpperCase();
  if (!canSubmitGmOptionRequest(row, season, option)) return '';
  const hideAccept = ['QO', 'GAP'].includes(option) && optionAcceptedByTeam(row, season, option);
  return `
    <span class="gm-option-request-actions" data-player-id="${escapeHtml(row.id)}" data-option-field="option_${escapeHtml(season)}" data-option-value="${escapeHtml(option)}">
      ${hideAccept ? '' : '<button type="button" data-gm-option-action="accepted">Aceptar</button>'}
      <button type="button" data-gm-option-action="rejected">Rechazar</button>
    </span>
  `;
}

function canSubmitGmBirdRightsRenounceRequest(row, season, rightsCode) {
  if (!row?.id) return false;
  if (!freeAgencyModeActive() || Number(season) !== capHoldTargetSeason()) return false;
  const rights = String(rightsCode || '').trim().toUpperCase();
  if (!['FB', 'EB', 'NB'].includes(rights)) return false;
  const auth = state.auth || {};
  if (!auth.authenticated || !hasGmLevelRole(auth.role)) return false;
  const teamCodes = Array.isArray(auth.team_codes)
    ? auth.team_codes.map((code) => String(code || '').toUpperCase()).filter(Boolean)
    : [];
  return teamCodes.includes(String(state.teamCode || '').toUpperCase());
}

function gmBirdRightsRenounceRequestHtml(row, season, rightsCode) {
  const rights = String(rightsCode || '').trim().toUpperCase();
  if (!canSubmitGmBirdRightsRenounceRequest(row, season, rights)) return '';
  return `
    <span class="gm-option-request-actions gm-option-request-actions--renounce" data-player-id="${escapeHtml(row.id)}" data-season-year="${escapeHtml(season)}" data-rights-value="${escapeHtml(rights)}">
      <button type="button" data-gm-bird-renounce="1">Renunciar derechos</button>
    </span>
  `;
}

async function submitGmOptionRequest(button) {
  const wrap = button.closest('.gm-option-request-actions');
  if (!wrap) return;
  if (button.dataset.gmSubmitting === '1') return;
  const action = String(button.dataset.gmOptionAction || '').trim();
  const playerId = Number(wrap.dataset.playerId);
  const optionField = String(wrap.dataset.optionField || '').trim();
  const optionValue = String(wrap.dataset.optionValue || '').trim().toUpperCase();
  if (!Number.isInteger(playerId) || playerId <= 0 || !optionField || !optionValue || !action) return;
  const actionText = action === 'accepted' ? 'aceptar' : 'rechazar';
  const confirmed = window.confirm(`¿Seguro que quieres ${actionText} esta opción ${optionValue}?`);
  if (!confirmed) return;
  button.dataset.gmSubmitting = '1';
  const buttons = Array.from(wrap.querySelectorAll('button'));
  buttons.forEach((btn) => { btn.disabled = true; });
  try {
    await api('/api/gm/option-requests', {
      method: 'POST',
      body: JSON.stringify({
        player_id: playerId,
        option_field: optionField,
        option_value: optionValue,
        action,
      }),
    });
    wrap.innerHTML = '<span class="gm-option-request-sent">Solicitud enviada</span>';
    alert('Tu petición ha sido enviada a la administración. Será procesada pronto.');
  } catch (err) {
    alert(`No se pudo enviar la solicitud: ${err.message || err}`);
    delete button.dataset.gmSubmitting;
    buttons.forEach((btn) => { btn.disabled = false; });
  }
}

async function submitGmBirdRightsRenounceRequest(button) {
  const wrap = button.closest('.gm-option-request-actions--renounce');
  if (!wrap) return;
  if (button.dataset.gmSubmitting === '1') return;
  const playerId = Number(wrap.dataset.playerId);
  const seasonYear = Number(wrap.dataset.seasonYear);
  const rightsValue = String(wrap.dataset.rightsValue || '').trim().toUpperCase();
  if (!Number.isInteger(playerId) || playerId <= 0 || !Number.isInteger(seasonYear) || !rightsValue) return;
  const confirmed = window.confirm(`¿Seguro que quieres solicitar la renuncia a los derechos ${rightsValue}? Si la administración lo aprueba, desaparecerá el cap hold.`);
  if (!confirmed) return;
  button.dataset.gmSubmitting = '1';
  const buttons = Array.from(wrap.querySelectorAll('button'));
  buttons.forEach((btn) => { btn.disabled = true; });
  try {
    await api('/api/gm/bird-rights-renounce-requests', {
      method: 'POST',
      body: JSON.stringify({
        player_id: playerId,
        season_year: seasonYear,
        rights_value: rightsValue,
      }),
    });
    wrap.innerHTML = '<span class="gm-option-request-sent">Solicitud enviada</span>';
    alert('Tu petición ha sido enviada a la administración. Será procesada pronto.');
  } catch (err) {
    alert(`No se pudo enviar la solicitud: ${err.message || err}`);
    delete button.dataset.gmSubmitting;
    buttons.forEach((btn) => { btn.disabled = false; });
  }
}

function bindGmOptionRequestButtons(root) {
  if (!root) return;
  root.querySelectorAll('[data-gm-option-action]').forEach((button) => {
    if (button.dataset.gmOptionBound === '1') return;
    button.dataset.gmOptionBound = '1';
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      void submitGmOptionRequest(button);
    });
  });
  root.querySelectorAll('[data-gm-bird-renounce]').forEach((button) => {
    if (button.dataset.gmBirdRenounceBound === '1') return;
    button.dataset.gmBirdRenounceBound = '1';
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      void submitGmBirdRightsRenounceRequest(button);
    });
  });
}

function setupGmOptionRequestDelegation() {
  if (state.ui.gmOptionDelegationBound) return;
  state.ui.gmOptionDelegationBound = true;
  document.addEventListener('click', (event) => {
    const optionButton = event.target.closest('[data-gm-option-action]');
    if (optionButton) {
      event.preventDefault();
      event.stopPropagation();
      void submitGmOptionRequest(optionButton);
      return;
    }
    const renounceButton = event.target.closest('[data-gm-bird-renounce]');
    if (renounceButton) {
      event.preventDefault();
      event.stopPropagation();
      void submitGmBirdRightsRenounceRequest(renounceButton);
    }
  });
}

function hasNumericSeasonSalary(row, season) {
  const direct = row?.[`salary_${season}_num`];
  if (direct !== null && direct !== undefined && direct !== '' && Number.isFinite(Number(direct))) return true;
  return parseAmountLike(row?.[`salary_${season}_text`]) !== null;
}

function isRestrictedRightsPlayer(player) {
  const rights = String(player?.bird_rights || '').trim().toUpperCase();
  return rights === 'R' || rights.startsWith('R(');
}

function capHoldTargetSeason() {
  return currentSeasonStart();
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
  const clamp = capHoldClampInfo(options.player, options.season, amount);
  const clampMessage = clamp.clamped
    ? ` Limitado al salario máximo por YOS: ${formatDots(clamp.limit)}.`
    : '';
  return {
    active: true,
    displayable: true,
    amount: clamp.amount,
    displayAmount: options.displayAmount,
    pending: false,
    label: 'Cap hold',
    shortLabel,
    message: `${message || ''}${clampMessage}`,
  };
}

function maximumSalaryForExperience(season, experienceYears) {
  const cap = capForSeason(season);
  const experience = normalizeExperienceYears(experienceYears);
  let percentage = 0.35;
  if (experience !== null && experience < 7) {
    percentage = 0.25;
  } else if (experience !== null && experience < 10) {
    percentage = 0.30;
  }
  return Math.round(Number(cap || 0) * percentage);
}

function capHoldClampInfo(player, season, amount) {
  const rawAmount = Math.round(Number(amount || 0));
  if (!player || !Number(season) || rawAmount <= 0) {
    return { amount: Math.max(0, rawAmount), limit: 0, clamped: false };
  }
  const limit = maximumSalaryForExperience(season, player.experience_years);
  if (!limit || rawAmount <= limit) {
    return { amount: rawAmount, limit, clamped: false };
  }
  return { amount: limit, limit, clamped: true };
}

function birdCapHoldInfo(player, season, code) {
  const previousSalary = capHoldPreviousSalaryValue(player, season);
  const previousSalaryIsMinimum = capHoldPreviousSalaryIsMinimum(player, season);
  if ((!previousSalary || previousSalary <= 0) && !(code === 'NB' && previousSalaryIsMinimum)) {
    return pendingCapHold(`${code} hold`, 'Cap hold pendiente: falta salario anterior.');
  }
  if (code === 'NB') {
    const rights = String(player?.bird_rights || '').trim().toUpperCase();
    if (rights === 'MIN' || rights === 'TW' || previousSalaryIsMinimum || salaryLooksLikeMinimum(previousSalary, season - 1)) {
      return calculatedCapHold(
        minimumSalaryForSeason(season, 2, 1),
        'NB hold',
        'Cap hold Non-Bird mínimo: mínimo de veterano de dos años.',
        { player, season },
      );
    }
    return calculatedCapHold(previousSalary * 1.2, 'NB hold', 'Cap hold Non-Bird: 120% del salario anterior.', { player, season });
  }
  if (code === 'EB') {
    return calculatedCapHold(previousSalary * 1.3, 'EB hold', 'Cap hold Early Bird: 130% del salario anterior.', { player, season });
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
      { player, season },
    );
  }
  return null;
}

function serverCapHoldInfo(player, season) {
  const amount = Number(player?.[`cap_hold_${season}_amount`] || 0);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  const displayAmount = Number(player?.[`cap_hold_${season}_display_amount`] || 0);
  return {
    active: true,
    displayable: true,
    amount,
    displayAmount: Number.isFinite(displayAmount) && displayAmount > 0 ? displayAmount : undefined,
    pending: false,
    label: 'Cap hold',
    shortLabel: String(player?.[`cap_hold_${season}_short_label`] || 'Cap hold'),
    message: String(player?.[`cap_hold_${season}_message`] || 'Cap hold calculado por el servidor.'),
  };
}

function capHoldInfo(player, season) {
  if (!freeAgencyModeActive() || Number(season) !== capHoldTargetSeason()) {
    return { active: false, displayable: false, amount: 0 };
  }
  const serverInfo = serverCapHoldInfo(player, season);
  if (serverInfo) return serverInfo;

  const textCode = seasonSalaryTextCode(player, season);
  const optionCode = seasonOptionCode(player, season);
  const isQualifyingOffer = textCode === 'QO' || optionCode === 'QO' || optionAcceptedByTeam(player, season, 'GAP');
  let birdCode = ['NB', 'EB', 'FB'].includes(textCode)
    ? textCode
    : (['NB', 'EB', 'FB'].includes(optionCode) ? optionCode : '');
  if (isQualifyingOffer && !birdCode && !isRestrictedRightsPlayer(player)) {
    birdCode = capHoldBirdCodeFromYears(player?.years_left);
  }
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
      { displayAmount: qualifyingOfferValue || undefined, player, season },
    );
  }

  if (isQualifyingOffer && isRestrictedRightsPlayer(player)) {
    const previousSalary = capHoldPreviousSalaryValue(player, season);
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
      { displayAmount: qualifyingOfferValue || undefined, player, season },
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
  if (isExhibit10Player(row)) return 0;
  const hold = capHoldInfo(row, season);
  if (hold.displayable && hold.amount > 0) return hold.amount;
  return salaryNumericValue(row, season);
}

function playerCapCountValue(player, season) {
  if (isExhibit10Player(player)) return 0;
  const hold = capHoldInfo(player, season);
  if (hold.displayable && hold.amount > 0) return hold.amount;
  if (isTwoWayPlayer(player)) return 0;
  return salaryNumericValue(player, season);
}

function playerApronCountValue(player, season) {
  if (isExhibit10Player(player)) return 0;
  const hold = capHoldInfo(player, season);
  if (hold.displayable) return 0;
  if (isTwoWayPlayer(player)) return 0;
  const salary = salaryNumericValue(player, season);
  return salary + apronYosAdjustmentValue(player, season, salary);
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

function isExhibit10Player(player) {
  const normalized = String(player?.bird_rights || '').trim().toUpperCase().replace(/[\s_-]/g, '');
  return normalized === 'E10' || normalized === 'EXHIBIT10';
}

function normalizeExperienceYears(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const parsed = Number(raw.replace('+', '').replace(',', '.'));
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.min(50, Math.floor(parsed)));
}

function isFreeAgentSignedContract(player) {
  return boolValue(player?.signed_as_free_agent);
}

function apronYosAdjustmentValue(player, season, salary = salaryNumericValue(player, season)) {
  const experience = normalizeExperienceYears(player?.experience_years);
  if (experience !== 0 && experience !== 1) return 0;
  if (!isFreeAgentSignedContract(player)) return 0;
  const salaryValue = Number(salary || 0);
  if (!Number.isFinite(salaryValue) || salaryValue <= 0) return 0;
  const minimumTwoYos = minimumSalaryForSeason(season, 2, 1);
  if (!minimumTwoYos) return 0;
  return Math.max(0, minimumTwoYos - salaryValue);
}

function capTotalTooltipText() {
  return 'CAP TOTAL incluye: salarios de jugadores, Dead Contracts, retirados bajo contrato, cap holds activos y, en modo agencia libre, el Open Roster Spot Cap Hold si el equipo no llega a 12 huecos computables. Cuando el modo agencia libre está desactivado, si el equipo queda por debajo del Salary Floor, el CAP TOTAL sube hasta ese mínimo. Excluye: cap holds renunciados, contratos Two-Way, cap holds Two-Way y contratos Exhibit 10.';
}

function apronTooltipText() {
  return 'Cuenta del APRON = Team Salary sin cap holds. Incluye salarios de jugadores, Dead Contracts y el ajuste 0-1 YOS cuando aplica: si un jugador con 0 o 1 año de servicio firma como agente libre, cuenta como mínimo de 2 YOS si su salario queda por debajo. Excluye cap holds, Two-Way y Exhibit 10. Unlikely bonuses, grievances, QO/matches, tenders y SRP Exception no aplican o se omiten por ahora.';
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

function trackerHardCapBadgeHtml(value) {
  const hardCap = String(value || '').trim().toLowerCase();
  if (hardCap === 'first') {
    return '<span class="tracker-hard-cap-badge tracker-hard-cap-badge--first">1er apron</span>';
  }
  if (hardCap === 'second') {
    return '<span class="tracker-hard-cap-badge tracker-hard-cap-badge--second">2do apron</span>';
  }
  return '<span class="tracker-hard-cap-badge tracker-hard-cap-badge--none">Sin hard cap</span>';
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
  const selectedYear = selectedSeasonStart();
  return Array.from({ length: SEASON_WINDOW_SIZE }, (_, idx) => selectedYear + idx);
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

function serverSeasonSummary(data, season) {
  const summaries = data?.season_summaries || {};
  const direct = summaries[String(season)];
  if (direct) return direct;
  const base = data?.summary || null;
  return Number(base?.current_year) === Number(season) ? base : null;
}

function teamSeasonBalances(data, season) {
  const serverSummary = serverSeasonSummary(data, season);
  const capFigure = Number(serverSummary?.cap_figure || 0);
  const rawCapFigure = Number(serverSummary?.cap_figure_before_floor ?? capFigure);
  return {
    cap_total: capFigure,
    cap_total_before_floor: rawCapFigure,
    salary_floor_adjustment: Number(serverSummary?.salary_floor_adjustment || 0),
    gasto_total: Number(serverSummary?.payroll || 0),
    apron_account: Number(serverSummary?.apron_account || 0),
    luxury_tax: Number(serverSummary?.luxury_tax || 0),
    breakdowns: serverSummary?.balance_breakdowns || {},
    missing_server_summary: !serverSummary,
  };
}

function seasonBalances(season) {
  return teamSeasonBalances(state.teamData, season);
}

function balanceBreakdownLines(balances, key) {
  const lines = balances?.breakdowns?.[key];
  return Array.isArray(lines) ? lines : [];
}

function balanceBreakdownTooltip(label, value, lines) {
  const output = [`${label}: ${formatMoneyDots(value)}`];
  if (!lines.length) {
    output.push('', 'Desglose no disponible para esta temporada.');
    return output.join('\n');
  }
  output.push('', keyLabelForBreakdown(label));
  lines.forEach((line) => {
    const lineLabel = String(line?.label || '').trim() || 'Partida';
    if (line && Object.prototype.hasOwnProperty.call(line, 'text')) {
      output.push(`- ${lineLabel}: ${line.text || ''}`);
    } else {
      output.push(`- ${lineLabel}: ${formatMoneyDots(line?.amount || 0)}`);
    }
  });
  return output.join('\n');
}

function keyLabelForBreakdown(label) {
  return String(label || '').toLowerCase().includes('luxury')
    ? 'Cálculo:'
    : 'Desglose:';
}

function balanceInfoControlHtml(tooltip) {
  const safeTooltip = escapeHtml(tooltip);
  return `
    <button class="balance-info-btn" type="button" aria-label="Ver desglose de balance" data-balance-info-toggle>i</button>
    <span class="balance-info-popover" role="tooltip">${safeTooltip}</span>
  `;
}

let balanceInfoPortal = null;

function ensureBalanceInfoPortal() {
  if (balanceInfoPortal) return balanceInfoPortal;
  balanceInfoPortal = document.createElement('div');
  balanceInfoPortal.className = 'balance-info-popover balance-info-popover--portal';
  balanceInfoPortal.setAttribute('role', 'tooltip');
  document.body.appendChild(balanceInfoPortal);
  return balanceInfoPortal;
}

function balanceInfoTextForButton(btn) {
  const wrap = btn.closest('.balance-value-wrap');
  return wrap?.querySelector('.balance-info-popover')?.textContent || '';
}

function showBalanceInfoPopover(btn) {
  const text = balanceInfoTextForButton(btn);
  if (!text) return;
  const portal = ensureBalanceInfoPortal();
  portal.textContent = text;
  portal.classList.add('is-visible');
  portal.style.left = '0px';
  portal.style.top = '0px';

  const rect = btn.getBoundingClientRect();
  const gap = 8;
  const margin = 12;
  const width = portal.offsetWidth;
  const height = portal.offsetHeight;
  const maxLeft = window.innerWidth - width - margin;
  let left = Math.min(Math.max(margin, rect.right - width), Math.max(margin, maxLeft));
  let top = rect.bottom + gap;
  if (top + height > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - height - gap);
  }
  portal.style.left = `${left}px`;
  portal.style.top = `${top}px`;
}

function hideBalanceInfoPortal() {
  if (balanceInfoPortal) balanceInfoPortal.classList.remove('is-visible');
}

function closeBalanceInfoPopovers() {
  document.querySelectorAll('.balance-info-btn.is-open').forEach((btn) => btn.classList.remove('is-open'));
  hideBalanceInfoPortal();
}

function setupBalanceInfoButton(btn) {
  btn.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const shouldOpen = !btn.classList.contains('is-open');
    closeBalanceInfoPopovers();
    if (shouldOpen) {
      btn.classList.add('is-open');
      showBalanceInfoPopover(btn);
    }
  });
  btn.addEventListener('mouseenter', () => showBalanceInfoPopover(btn));
  btn.addEventListener('mouseleave', () => {
    if (!btn.classList.contains('is-open')) hideBalanceInfoPortal();
  });
  btn.addEventListener('focus', () => showBalanceInfoPopover(btn));
  btn.addEventListener('blur', () => {
    if (!btn.classList.contains('is-open')) hideBalanceInfoPortal();
  });
}

function displayBalanceSeason() {
  return state.ui.viewMode === 'team' ? selectedSeasonStart() : defaultSeasonViewStart();
}

function summaryForBalanceSeason(data, season = displayBalanceSeason()) {
  const base = data?.summary || {};
  const serverSummary = serverSeasonSummary(data, season);
  if (serverSummary) {
    return { ...base, ...serverSummary, current_year: season };
  }
  return {
    ...base,
    current_year: season,
    cap_figure: 0,
    payroll: 0,
    apron_account: 0,
    luxury_tax: 0,
    room_to_cap: 0,
    room_to_luxury: 0,
    room_to_first_apron: 0,
    room_to_second_apron: 0,
    missing_server_summary: true,
  };
}

function openRosterSpotHoldForSeason(season) {
  const summary = serverSeasonSummary(state.teamData, season);
  const amount = Number(summary?.open_roster_spot_cap_hold || 0);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  return {
    amount,
    count: Number(summary?.open_roster_spot_count || 0),
    rosterCount: Number(summary?.open_roster_spot_roster_count || 0),
    minimumSalary: Number(summary?.open_roster_spot_minimum_salary || 0),
  };
}

function openRosterSpotDeadContractRow(seasons) {
  const row = {
    id: 'system-open-roster-spot-cap-hold',
    label: 'Open Roster Spot Cap Hold',
    dead_type: 'normal',
    is_system_cap_hold: true,
    contract_notes: true,
  };
  let hasAmount = false;
  seasons.forEach((season) => {
    const hold = openRosterSpotHoldForSeason(season);
    if (!hold) return;
    row[`salary_${season}_num`] = hold.amount;
    row[`salary_${season}_text`] = String(Math.round(hold.amount));
    row[`salary_${season}_note`] = true;
    row[`salary_${season}_note_text`] = `${hold.count} hueco(s) de roster x mínimo rookie (${formatDots(hold.minimumSalary)}). Cuenta de roster para el mínimo: ${hold.rosterCount}/12.`;
    hasAmount = true;
  });
  return hasAmount ? row : null;
}

function capForSeason(season) {
  const direct = Number(state.settings[`salary_cap_${season}`]);
  if (Number.isFinite(direct) && direct > 0) return direct;
  return Number(state.settings.salary_cap_2025 || 0);
}

function salaryFloorForSeason(season) {
  const direct = Number(state.settings[`salary_floor_${season}`]);
  if (Number.isFinite(direct) && direct > 0) return direct;
  return capForSeason(season) * 0.9;
}

function applySalaryFloorForSeason(season, amount) {
  const raw = Number(amount || 0);
  if (freeAgencyModeActive()) return raw;
  return Math.max(raw, salaryFloorForSeason(season));
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
  return availableSeasonViewStarts();
}

function maximumSalaryRows() {
  return [
    { label: '0-6 años', value: (season) => capForSeason(season) * 0.25 },
    { label: '7-9 años', value: (season) => capForSeason(season) * 0.30 },
    { label: '10+ años', value: (season) => capForSeason(season) * 0.35 },
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
    { label: 'Salary floor', value: salaryFloorForSeason },
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

function contractCalculatorState() {
  if (!state.ui.contractCalculator) {
    state.ui.contractCalculator = { firstAmount: '', years: 5, raisePct: 8 };
  }
  return state.ui.contractCalculator;
}

function normalizeContractCalculatorYears(value) {
  const years = Number(value || 5);
  return Math.min(5, Math.max(1, Number.isFinite(years) ? Math.round(years) : 5));
}

function contractCalculatorYears() {
  return normalizeContractCalculatorYears(contractCalculatorState().years);
}

function normalizeContractCalculatorRaisePct(value) {
  const pct = Number(value || 0);
  if (!Number.isFinite(pct)) return 0;
  return Math.min(8, Math.max(0, pct));
}

function contractCalculatorRaisePct() {
  return normalizeContractCalculatorRaisePct(contractCalculatorState().raisePct);
}

function contractCalculatorRows() {
  const firstAmount = parseAmountLike(contractCalculatorState().firstAmount);
  const years = contractCalculatorYears();
  const raisePct = contractCalculatorRaisePct() / 100;
  if (!firstAmount || firstAmount <= 0) {
    return Array.from({ length: years }, (_, idx) => ({
      year: idx + 1,
      amount: null,
    }));
  }
  const annualRaise = firstAmount * raisePct;
  return Array.from({ length: years }, (_, idx) => ({
    year: idx + 1,
    amount: Math.round(firstAmount + (annualRaise * idx)),
  }));
}

function contractCalculatorSummary() {
  const amounts = contractCalculatorRows()
    .map((row) => row.amount)
    .filter((amount) => Number.isFinite(Number(amount)));
  const total = amounts.reduce((sum, amount) => sum + Number(amount), 0);
  return {
    total: amounts.length ? total : null,
    average: amounts.length ? Math.round(total / amounts.length) : null,
  };
}

function contractCalculatorValueHtml(value) {
  return Number.isFinite(Number(value))
    ? formatMoneyDots(value)
    : '<span class="figures-pending">Pendiente</span>';
}

function renderContractCalculatorResults() {
  const tbody = document.getElementById('contractCalculatorResults');
  const totalEl = document.getElementById('contractCalculatorTotal');
  const averageEl = document.getElementById('contractCalculatorAverage');
  if (!tbody || !totalEl || !averageEl) return;
  const rows = contractCalculatorRows();
  tbody.innerHTML = rows.map((row) => `
    <tr>
      <th>${row.year}º año</th>
      <td>${contractCalculatorValueHtml(row.amount)}</td>
    </tr>
  `).join('');
  const summary = contractCalculatorSummary();
  totalEl.innerHTML = contractCalculatorValueHtml(summary.total);
  averageEl.innerHTML = contractCalculatorValueHtml(summary.average);
}

function setupContractCalculator() {
  const root = document.getElementById('contractCalculator');
  if (!root) return;
  const calculator = contractCalculatorState();
  const firstAmountInput = document.getElementById('contractCalculatorFirstAmount');
  const yearsInput = document.getElementById('contractCalculatorYears');
  const raiseInput = document.getElementById('contractCalculatorRaisePct');
  if (firstAmountInput) firstAmountInput.value = calculator.firstAmount || '';
  if (yearsInput) yearsInput.value = String(contractCalculatorYears());
  if (raiseInput) raiseInput.value = String(contractCalculatorRaisePct());
  const sync = () => {
    calculator.firstAmount = String(firstAmountInput?.value || '');
    calculator.years = normalizeContractCalculatorYears(yearsInput?.value);
    calculator.raisePct = normalizeContractCalculatorRaisePct(raiseInput?.value);
    if (yearsInput && yearsInput.value !== String(calculator.years)) yearsInput.value = String(calculator.years);
    if (raiseInput && raiseInput.value !== String(calculator.raisePct)) raiseInput.value = String(calculator.raisePct);
    renderContractCalculatorResults();
  };
  [firstAmountInput, yearsInput, raiseInput].forEach((input) => {
    input?.addEventListener('input', sync);
    input?.addEventListener('change', sync);
  });
  renderContractCalculatorResults();
}

function contractCalculatorHtml() {
  const calculator = contractCalculatorState();
  return `
    <section id="contractCalculator" class="figures-group contract-calculator-card">
      <div class="figures-group-head">
        <h3>Calculadora de contrato</h3>
        <p>Calcula importes por año, total y media desde el primer salario.</p>
      </div>
      <div class="contract-calculator-grid">
        <label>
          <span>Importe 1er año</span>
          <input id="contractCalculatorFirstAmount" type="text" inputmode="numeric" placeholder="49.488.300" value="${escapeHtml(calculator.firstAmount || '')}">
        </label>
        <label>
          <span>Años</span>
          <select id="contractCalculatorYears">
            ${[1, 2, 3, 4, 5].map((year) => `<option value="${year}"${year === contractCalculatorYears() ? ' selected' : ''}>${year}</option>`).join('')}
          </select>
        </label>
        <label>
          <span>Subida anual (%)</span>
          <input id="contractCalculatorRaisePct" type="number" min="0" max="8" step="0.5" value="${escapeHtml(contractCalculatorRaisePct())}">
        </label>
      </div>
      <div class="contract-calculator-output">
        <div class="table-wrap contract-calculator-table-wrap">
          <table class="contract-calculator-table">
            <thead>
              <tr>
                <th>Año</th>
                <th>Importe</th>
              </tr>
            </thead>
            <tbody id="contractCalculatorResults"></tbody>
            <tfoot>
              <tr>
                <th>Total</th>
                <td id="contractCalculatorTotal"></td>
              </tr>
              <tr>
                <th>Media</th>
                <td id="contractCalculatorAverage"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </section>
  `;
}

function figuresTableHtml(title, rows, seasons, description = '') {
  const currentYear = currentSeasonStart();
  const selectedSeason = selectedFiguresSeasonStart();
  return `
    <section class="figures-group">
      <div class="figures-group-head">
        <h3>${escapeHtml(title)}</h3>
        ${description ? `<p>${escapeHtml(description)}</p>` : ''}
      </div>
      <div class="table-wrap figures-table-wrap">
        <table class="figures-table figures-table--desktop">
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
        <table class="figures-table figures-table--mobile">
          <thead>
            <tr>
              <th>Cifra</th>
              <th class="${selectedSeason === currentYear ? 'figures-current-season' : ''}">
                ${seasonSlashLabel(selectedSeason)}
                ${selectedSeason === currentYear ? '<span>actual</span>' : ''}
              </th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <th>${escapeHtml(row.label)}</th>
                <td>${figureValueHtml(row, selectedSeason)}</td>
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

function renderFigures() {
  const board = document.getElementById('figuresBoard');
  if (!board) return;
  const seasons = figuresSeasonYears();
  renderFiguresSeasonControl();
  board.innerHTML = `
    <div class="figures-note">
      Cifras derivadas del Salary Cap configurado. Los mínimos escalan desde la tabla 2025/26.
    </div>
    ${contractCalculatorHtml()}
    ${figuresTableHtml('Salarios máximos', maximumSalaryRows(), seasons)}
    ${figuresTableHtml('Excepciones', exceptionRows(), seasons)}
    ${figuresTableHtml('Límites de cap, luxury, aprons y cash', capLimitRows(), seasons)}
    ${minimumSalarySectionHtml(seasons)}
    ${figuresTableHtml('Salario medio', averageSalaryRows(), seasons)}
  `;
  setupContractCalculator();
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

function draftPickIsStepienRestricted(asset) {
  return boolValue(asset?.draft_pick_stepien_restricted);
}

function draftPickIsProtected(asset) {
  return boolValue(asset?.draft_pick_protected);
}

function draftPickIsFrozen(asset) {
  return boolValue(asset?.draft_pick_frozen);
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

function tradeMachinePickActionOptions(selectedAction, stepienOnly = false) {
  const selected = tradeMachinePickAction(selectedAction);
  const actions = stepienOnly ? [
    [TRADE_PICK_ACTION_SWAP, 'Vender swap'],
  ] : [
    [TRADE_PICK_ACTION_SEND, 'Enviar ronda'],
    [TRADE_PICK_ACTION_SWAP, 'Vender swap'],
  ];
  return actions.map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${label}</option>`).join('');
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
  if (draftPickIsFrozen(asset)) badges.push('<span class="trade-machine-tag trade-machine-tag--danger">Congelada</span>');
  if (draftPickIsRestricted(asset)) badges.push('<span class="trade-machine-tag trade-machine-tag--danger">Restringida</span>');
  if (draftPickIsStepienRestricted(asset)) badges.push('<span class="trade-machine-tag trade-machine-tag--warning">Stepien</span>');
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
    const season = tradeMachineSeasonStart();
    const salary = isExhibit10Player(player) ? 0 : salaryNumericValue(player, season);
    const capSalary = playerCapCountValue(player, season);
    const apronSalary = playerApronCountValue(player, season);
    return {
      key,
      type,
      id,
      fromTeam,
      label: player.name || 'Jugador',
      detail: [player.position, player.bird_rights].filter(Boolean).join(' · '),
      salary,
      capSalary,
      apronSalary,
      rating: Number(player.rating || 0) || 0,
      ratingText: String(player.rating || '').trim(),
      isMinimumContract: salaryLooksLikeMinimum(salary, tradeMachineSeasonStart()),
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
      apronSalary: 0,
      restricted: draftPickIsRestricted(pick),
      stepienRestricted: draftPickIsStepienRestricted(pick),
      protected: draftPickIsProtected(pick),
      frozen: draftPickIsFrozen(pick),
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
      apronSalary: 0,
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
  Object.entries(state.tradeMachine.cashTransfers || {}).forEach(([fromTeam, transfer]) => {
    if (!teams.has(fromTeam) || !teams.has(transfer?.toTeam) || fromTeam === transfer?.toTeam) {
      delete state.tradeMachine.cashTransfers[fromTeam];
    }
  });
}

async function ensureTradeMachineTeamData(codes) {
  const unique = tradeMachineUniqueCodes(codes);
  const season = tradeMachineSeasonStart();
  const missing = unique.filter((code) => {
    const cached = state.tradeMachine.teamDataByCode[code];
    return !cached || Number(cached._tradeMachineSeasonStart) !== season;
  });
  if (!missing.length) return;
  state.tradeMachine.loading = true;
  try {
    const loaded = await Promise.all(
      missing.map(async (code) => [
        code,
        await api(`/api/teams/${encodeURIComponent(code)}?season=${encodeURIComponent(season)}`),
      ]),
    );
    loaded.forEach(([code, data]) => {
      data._tradeMachineSeasonStart = season;
      state.tradeMachine.teamDataByCode[code] = data;
    });
  } finally {
    state.tradeMachine.loading = false;
  }
  if (state.ui.viewMode === 'trade-machine') {
    renderTradeMachine();
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
  const season = tradeMachineSeasonStart();
  const salaryCap = capForSeason(season);
  const luxuryCap = luxuryCapForSeason(season);
  return {
    salaryCap,
    luxuryCap,
    firstApron: firstApronForSeason(season),
    secondApron: secondApronForSeason(season),
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
  const beforeRawCap = season === currentSeasonStart() && Number.isFinite(Number(summary.cap_figure_before_floor))
    ? Number(summary.cap_figure_before_floor)
    : Number(seasonTotals.cap_total_before_floor ?? beforeCap);
  const beforeApronAccount = season === currentSeasonStart() && Number.isFinite(Number(summary.apron_account))
    ? Number(summary.apron_account)
    : Number(seasonTotals.apron_account || beforeCap);
  return {
    code,
    beforeCap,
    beforeRawCap,
    beforeSalaryFloorAdjustment: Math.max(0, beforeCap - beforeRawCap),
    beforeApronAccount,
    incomingSalary: 0,
    outgoingSalary: 0,
    incomingMatchingSalary: 0,
    outgoingMatchingSalary: 0,
    incomingCash: 0,
    outgoingCash: 0,
    incomingCapSalary: 0,
    outgoingCapSalary: 0,
    incomingApronSalary: 0,
    outgoingApronSalary: 0,
    incomingAssets: [],
    outgoingAssets: [],
    postCap: beforeCap,
    postRawCap: beforeRawCap,
    postSalaryFloorAdjustment: Math.max(0, beforeCap - beforeRawCap),
    postApronAccount: beforeApronAccount,
    beforeRosterStandard: rosterCounts.standard,
    beforeRosterTwoWay: rosterCounts.twoWay,
    postRosterStandard: rosterCounts.standard,
    postRosterTwoWay: rosterCounts.twoWay,
    beforeBalances: tradeMachineBalanceSnapshot(beforeCap, beforeApronAccount),
    afterBalances: tradeMachineBalanceSnapshot(beforeCap, beforeApronAccount),
  };
}

function tradeMachineCashTransfersForPayload() {
  return Object.entries(state.tradeMachine.cashTransfers || {}).map(([fromTeam, transfer]) => {
    const amount = parseAmountLike(transfer?.amountText ?? transfer?.amount);
    const toTeam = String(transfer?.toTeam || tradeMachineDefaultRecipient(fromTeam) || '').trim().toUpperCase();
    if (!Number.isFinite(amount) || amount <= 0 || !fromTeam || !toTeam || fromTeam === toTeam) return null;
    return {
      from_team: fromTeam,
      to_team: toTeam,
      amount,
    };
  }).filter(Boolean);
}

function tradeMachineApplyCashTransfersToFlows(flows) {
  tradeMachineCashTransfersForPayload().forEach((transfer, index) => {
    const fromTeam = transfer.from_team;
    const toTeam = transfer.to_team;
    const amount = Number(transfer.amount || 0);
    if (!flows[fromTeam] || !flows[toTeam] || amount <= 0) return;
    const asset = {
      key: `cash:${fromTeam}:${toTeam}:${index}`,
      type: 'cash',
      label: 'Cash considerations',
      detail: formatBalanceMoney(amount),
      salary: 0,
      cashAmount: amount,
      fromTeam,
      toTeam,
    };
    flows[fromTeam].outgoingCash = Number(flows[fromTeam].outgoingCash || 0) + amount;
    flows[fromTeam].outgoingAssets.push(asset);
    flows[toTeam].incomingCash = Number(flows[toTeam].incomingCash || 0) + amount;
    flows[toTeam].incomingAssets.push(asset);
  });
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
    const matchingSalary = asset.isMinimumContract ? 0 : salary;
    const capSalary = Number(asset.capSalary ?? asset.salary ?? 0);
    const apronSalary = Number(asset.apronSalary ?? asset.capSalary ?? asset.salary ?? 0);
    flows[selection.fromTeam].outgoingSalary += salary;
    flows[selection.fromTeam].outgoingMatchingSalary += salary;
    flows[selection.fromTeam].outgoingCapSalary += capSalary;
    flows[selection.fromTeam].outgoingApronSalary += apronSalary;
    flows[selection.fromTeam].outgoingAssets.push({ ...asset, toTeam: selection.toTeam });
    flows[selection.toTeam].incomingSalary += salary;
    flows[selection.toTeam].incomingMatchingSalary += matchingSalary;
    flows[selection.toTeam].incomingCapSalary += capSalary;
    flows[selection.toTeam].incomingApronSalary += apronSalary;
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
  tradeMachineApplyCashTransfersToFlows(flows);
  Object.values(flows).forEach((flow) => {
    flow.postRawCap = flow.beforeRawCap + flow.incomingCapSalary - flow.outgoingCapSalary;
    flow.postCap = applySalaryFloorForSeason(tradeMachineSeasonStart(), flow.postRawCap);
    flow.postSalaryFloorAdjustment = Math.max(0, flow.postCap - flow.postRawCap);
    flow.postApronAccount = flow.beforeApronAccount + flow.incomingApronSalary - flow.outgoingApronSalary;
    flow.afterBalances = tradeMachineBalanceSnapshot(flow.postCap, flow.postApronAccount);
  });
  return flows;
}

function tradeMachineValidationPayload() {
  const selections = Object.entries(state.tradeMachine.selections || {}).map(([key, selection]) => {
    const meta = tradeMachineAssetMeta(key);
    const [type, fromTeam, rawId] = key.split(':');
    const id = meta?.id || Number(rawId);
    if (!Number.isFinite(id)) return null;
    return {
      type: meta?.type || type,
      id,
      from_team: selection?.fromTeam || meta?.fromTeam || fromTeam,
      to_team: selection?.toTeam || '',
      pick_action: selection?.pickAction,
      no_count: selection?.countsMove === false,
    };
  }).filter(Boolean);
  return {
    teams: state.tradeMachine.selectedTeams || [],
    season: tradeMachineSeasonStart(),
    selections,
    cash: tradeMachineCashTransfersForPayload(),
  };
}

function tradeMachineValidationSignature(payload = tradeMachineValidationPayload()) {
  return JSON.stringify(payload);
}

async function refreshTradeMachineValidation() {
  const payload = tradeMachineValidationPayload();
  const signature = tradeMachineValidationSignature(payload);
  if (state.tradeMachine.validationLoadingSignature === signature) return;
  state.tradeMachine.validationLoadingSignature = signature;
  try {
    const result = await api('/api/trades/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (state.tradeMachine.validationLoadingSignature !== signature) return;
    state.tradeMachine.validationSignature = signature;
    state.tradeMachine.validationResult = result;
    state.tradeMachine.validationErrorSignature = null;
    state.tradeMachine.validationError = null;
    renderTradeMachineDynamicSections();
  } catch (err) {
    console.warn('Trade validation failed', err);
    if (state.tradeMachine.validationLoadingSignature === signature) {
      state.tradeMachine.validationSignature = null;
      state.tradeMachine.validationResult = null;
      state.tradeMachine.validationErrorSignature = signature;
      state.tradeMachine.validationError = err;
    }
  } finally {
    if (state.tradeMachine.validationLoadingSignature === signature) {
      state.tradeMachine.validationLoadingSignature = null;
    }
    if (state.tradeMachine.validationErrorSignature === signature) {
      renderTradeMachineDynamicSections();
    }
  }
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

function tradeMachineAssetRowHtml({ key, type, label, detail, mobileDetail, salary, badges = '', disabled = false, stepienRestricted = false }) {
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
        ${tradeMachinePickActionOptions(selectedPickAction, stepienRestricted)}
      </select>
    `
    : '';
  return `
    <div class="trade-machine-asset-row ${selected ? 'is-selected' : ''} ${disabled ? 'is-disabled' : ''}" data-trade-asset-row="${escapeHtml(key)}">
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
    const salary = isExhibit10Player(player) ? 0 : salaryNumericValue(player, season);
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
  const maxDraftYear = minDraftYear + TRADE_DRAFT_YEAR_WINDOW - 1;
  const picks = (data.assets || [])
    .filter((asset) => asset.asset_type === 'draft_pick')
    .filter((asset) => draftPickType(asset) !== 'sold')
    .filter((asset) => {
      const year = Number(asset.year);
      return Number.isFinite(year) && year >= minDraftYear && year <= maxDraftYear;
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
      disabled: draftPickIsRestricted(pick) || draftPickIsFrozen(pick),
      stepienRestricted: draftPickIsStepienRestricted(pick),
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

function tradeMachineCashHtml(code) {
  const transfer = state.tradeMachine.cashTransfers?.[code] || {};
  const selectedTo = transfer.toTeam || tradeMachineDefaultRecipient(code);
  const amountText = transfer.amountText ?? '';
  return `
    <section class="trade-machine-cash-panel">
      <h3>Cash considerations</h3>
      <div class="trade-machine-cash-row">
        <input
          type="text"
          inputmode="numeric"
          data-trade-cash-amount="${escapeHtml(code)}"
          value="${escapeHtml(amountText)}"
          placeholder="0"
          aria-label="Cash enviado por ${escapeHtml(code)}"
        >
        <select data-trade-cash-recipient="${escapeHtml(code)}" aria-label="Destino del cash de ${escapeHtml(code)}">
          ${tradeMachineRecipientOptions(code, selectedTo)}
        </select>
      </div>
    </section>
  `;
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

function tradeMachinePreviewChipControlsHtml(asset, direction) {
  if (direction !== 'outgoing' || !asset?.key) return '';
  const selected = tradeMachineSelectedAsset(asset.key);
  if (!selected) return '';
  const meta = tradeMachineAssetMeta(asset.key);
  const fromTeam = selected.fromTeam || meta?.fromTeam || asset.fromTeam;
  const toTeam = selected.toTeam || asset.toTeam || tradeMachineDefaultRecipient(fromTeam);
  const recipientHtml = fromTeam
    ? `
      <select class="trade-machine-chip-select" data-trade-recipient="${escapeHtml(asset.key)}" aria-label="Destino de ${escapeHtml(asset.label)}">
        ${tradeMachineRecipientOptions(fromTeam, toTeam)}
      </select>
    `
    : '';
  const pickActionHtml = meta?.type === 'pick'
    ? `
      <select class="trade-machine-chip-select trade-machine-chip-select--pick" data-trade-pick-action="${escapeHtml(asset.key)}" aria-label="Acción para ${escapeHtml(asset.label)}">
        ${tradeMachinePickActionOptions(tradeMachinePickAction(selected.pickAction), Boolean(meta.stepienRestricted))}
      </select>
    `
    : '';
  if (!recipientHtml && !pickActionHtml) return '';
  return `<span class="trade-machine-preview-chip-controls">${pickActionHtml}${recipientHtml}</span>`;
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
      ${tradeMachinePreviewChipControlsHtml(asset, direction)}
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
  if (type === 'cash') return 'Cash';
  return 'Activo';
}

function tradeMachineAssetSummaryHtml(asset, direction) {
  const partner = direction === 'incoming' ? asset.fromTeam : asset.toTeam;
  const typeClass = `trade-machine-summary-asset--${asset.type || 'asset'}`;
  const partnerLogo = tradeMachineSummaryLogoHtml(partner);
  const salaryHtml = asset.salary > 0 ? `<span class="trade-machine-summary-asset-money">${formatBalanceMoney(asset.salary)}</span>` : '';
  const cashHtml = asset.type === 'cash' && Number(asset.cashAmount || 0) > 0
    ? `<span class="trade-machine-summary-asset-money">${formatBalanceMoney(asset.cashAmount)}</span>`
    : '';
  return `
    <li class="trade-machine-summary-asset ${typeClass}">
      <div class="trade-machine-summary-asset-head">
        <strong>${escapeHtml(asset.label)}</strong>
        ${partnerLogo}
      </div>
      ${asset.detail ? `<small>${escapeHtml(asset.detail)}</small>` : ''}
      ${salaryHtml || cashHtml}
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
    const tooltip = String(item.label || '').toUpperCase().includes('APRON') ? apronTooltipText() : '';
    return `
      <tr${tooltip ? ` title="${escapeHtml(tooltip)}"` : ''}>
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

function tradeMachineServerValidationPlaceholder(flows, validationState = 'loading') {
  const isError = validationState === 'error';
  return {
    status: isError ? 'review' : 'pending',
    issues: [],
    checklist: [
      {
        key: 'server_validation',
        label: 'Validación del servidor',
        status: isError ? 'warning' : 'pending',
        messages: [
          isError
            ? 'No se pudo completar la validación del servidor. Cambia el traspaso o recarga para volver a intentarlo.'
            : 'Validando reglas con el servidor. El resultado local solo muestra el resumen visual, no determina si el traspaso es válido.',
        ],
      },
    ],
    flows,
  };
}

function renderTradeMachineTeamCard(code, index, flow) {
  const data = state.tradeMachine.teamDataByCode[code];
  const canRemove = (state.tradeMachine.selectedTeams || []).length > TRADE_MACHINE_MIN_TEAMS;
  if (!data) {
    return `
      <article class="trade-machine-team-card" data-trade-team-card="${escapeHtml(code)}">
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
    <article class="trade-machine-team-card" data-trade-team-card="${escapeHtml(code)}">
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
      ${tradeMachineCashHtml(code)}
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
  const statusLabel = result.status === 'legal'
    ? 'Válido'
    : result.status === 'illegal'
      ? 'No válido'
      : result.status === 'pending'
        ? 'Validando...'
        : 'Requiere revisión';
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

function tradeMachineRenderContext() {
  const codes = state.tradeMachine.selectedTeams || [];
  pruneTradeMachineSelections();
  const previewFlows = tradeMachineFlows();
  const validationPayload = tradeMachineValidationPayload();
  const validationSignature = tradeMachineValidationSignature(validationPayload);
  const serverResult = state.tradeMachine.validationSignature === validationSignature
    ? state.tradeMachine.validationResult
    : null;
  const validationError = state.tradeMachine.validationErrorSignature === validationSignature
    ? state.tradeMachine.validationError
    : null;
  const result = serverResult || tradeMachineServerValidationPlaceholder(previewFlows, validationError ? 'error' : 'loading');
  return { codes, result, validationSignature, serverResult, validationError };
}

function syncTradeMachineAssetRows() {
  document.querySelectorAll('[data-trade-asset-row]').forEach((row) => {
    const key = row.dataset.tradeAssetRow;
    const selected = key ? tradeMachineSelectedAsset(key) : null;
    row.classList.toggle('is-selected', Boolean(selected));
    const checkbox = row.querySelector('[data-trade-asset-key]');
    if (checkbox) checkbox.checked = Boolean(selected);
    const recipient = row.querySelector('[data-trade-recipient]');
    if (recipient) {
      recipient.disabled = !selected;
      if (selected?.toTeam) recipient.value = selected.toTeam;
    }
  });
}

function renderTradeMachineDynamicSections() {
  const grid = document.getElementById('tradeMachineTeams');
  const status = document.getElementById('tradeMachineStatus');
  const addBtn = document.getElementById('tradeMachineAddTeamBtn');
  if (!grid) return null;
  const context = tradeMachineRenderContext();
  const { codes, result, validationSignature, serverResult, validationError } = context;
  if (status) status.textContent = `${seasonLabel(tradeMachineSeasonStart())} · ${codes.length} equipos`;
  if (addBtn) addBtn.disabled = codes.length >= TRADE_MACHINE_MAX_TEAMS;
  codes.forEach((code, index) => {
    const card = Array.from(grid.querySelectorAll('[data-trade-team-card]'))
      .find((item) => item.dataset.tradeTeamCard === code);
    const flow = result.flows[code] || tradeMachineFlowSkeleton(code);
    const isLoadingCard = Boolean(card?.querySelector('.trade-machine-team-top + .trade-machine-empty'));
    if (card && state.tradeMachine.teamDataByCode[code] && (!card.querySelector('.trade-machine-ledger') || isLoadingCard)) {
      card.outerHTML = renderTradeMachineTeamCard(code, index, flow);
      return;
    }
    const ledger = card?.querySelector('.trade-machine-ledger');
    if (ledger) ledger.outerHTML = tradeMachineLedgerHtml(flow);
    const roster = card?.querySelector('.trade-machine-roster-counts');
    if (roster) roster.outerHTML = tradeMachineRosterHtml(flow);
    const preview = card?.querySelector('.trade-machine-team-preview');
    if (preview) preview.outerHTML = tradeMachineTeamPreviewHtml(flow);
  });
  renderTradeMachineResults(result);
  syncTradeMachineAssetRows();
  if (
    !serverResult
    && !validationError
    && state.tradeMachine.validationLoadingSignature !== validationSignature
  ) {
    void refreshTradeMachineValidation();
  }
  return context;
}

function renderTradeMachine() {
  renderTradeMachineSeasonControl();
  const grid = document.getElementById('tradeMachineTeams');
  const status = document.getElementById('tradeMachineStatus');
  const addBtn = document.getElementById('tradeMachineAddTeamBtn');
  if (!grid) return;
  const { codes, result, validationSignature, serverResult, validationError } = tradeMachineRenderContext();
  if (status) status.textContent = `${seasonLabel(tradeMachineSeasonStart())} · ${codes.length} equipos`;
  if (addBtn) addBtn.disabled = codes.length >= TRADE_MACHINE_MAX_TEAMS;
  grid.innerHTML = codes
    .map((code, index) => renderTradeMachineTeamCard(code, index, result.flows[code] || tradeMachineFlowSkeleton(code)))
    .join('');
  renderTradeMachineResults(result);
  syncTradeMachineAssetRows();
  if (
    !serverResult
    && !validationError
    && state.tradeMachine.validationLoadingSignature !== validationSignature
  ) {
    void refreshTradeMachineValidation();
  }
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
  state.tradeMachine.cashTransfers = {};
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
    seasonSelect.addEventListener('change', async () => {
      state.tradeMachine.seasonStart = Number(seasonSelect.value || currentSeasonStart());
      renderTradeMachine();
      await ensureTradeMachineTeamData(state.tradeMachine.selectedTeams);
      pruneTradeMachineSelections();
      renderTradeMachine();
    });
  }
  if (grid) {
    grid.addEventListener('input', (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      if (!target.matches('[data-trade-cash-amount]')) return;
      const fromTeam = target.dataset.tradeCashAmount;
      if (!fromTeam) return;
      const existing = state.tradeMachine.cashTransfers[fromTeam] || {};
      state.tradeMachine.cashTransfers[fromTeam] = {
        ...existing,
        amountText: target.value,
        toTeam: existing.toTeam || tradeMachineDefaultRecipient(fromTeam),
      };
      renderTradeMachineDynamicSections();
    });
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
            pickAction: meta.type === 'pick'
              ? (meta.stepienRestricted ? TRADE_PICK_ACTION_SWAP : TRADE_PICK_ACTION_SEND)
              : undefined,
          };
        } else {
          delete state.tradeMachine.selections[key];
        }
        renderTradeMachineDynamicSections();
        return;
      }
      if (target.matches('[data-trade-recipient]')) {
        const key = target.dataset.tradeRecipient;
        if (key && state.tradeMachine.selections[key]) {
          state.tradeMachine.selections[key].toTeam = target.value;
          renderTradeMachineDynamicSections();
        }
        return;
      }
      if (target.matches('[data-trade-cash-recipient]')) {
        const fromTeam = target.dataset.tradeCashRecipient;
        if (fromTeam) {
          const existing = state.tradeMachine.cashTransfers[fromTeam] || {};
          state.tradeMachine.cashTransfers[fromTeam] = {
            ...existing,
            amountText: existing.amountText ?? '',
            toTeam: target.value,
          };
          renderTradeMachineDynamicSections();
        }
        return;
      }
      if (target.matches('[data-trade-pick-action]')) {
        const key = target.dataset.tradePickAction;
        if (key && state.tradeMachine.selections[key]) {
          state.tradeMachine.selections[key].pickAction = tradeMachinePickAction(target.value);
          renderTradeMachineDynamicSections();
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
          renderTradeMachineDynamicSections();
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
    return POSITION_ORDER[rosterPositionKey(row)] ?? 999;
  }
  if (key === 'years_left') return birdYearsSortValue(val);
  if (typeof val === 'number') return val;
  const num = Number(String(val).replaceAll('.', '').replaceAll(',', '.'));
  if (Number.isFinite(num) && key.includes('salary_')) return num;
  if (Number.isFinite(num) && (key === 'year' || key === 'rating' || key === 'amount_num')) return num;
  return String(val).toLowerCase();
}

function playerSalarySortValue(row) {
  const value = salaryDisplayNumericValue(row, selectedSeasonStart());
  return Number.isFinite(Number(value)) ? Number(value) : 0;
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
    if (sortCfg.key === 'position') {
      const salaryDiff = playerSalarySortValue(b) - playerSalarySortValue(a);
      if (salaryDiff !== 0) return salaryDiff;
      const nameA = String(a?.name || '').toLowerCase();
      const nameB = String(b?.name || '').toLowerCase();
      if (nameA < nameB) return -1;
      if (nameA > nameB) return 1;
    }
    return 0;
  });
}

function nextFreeAgentPrimarySort(curr) {
  const currentKey = String(curr?.key || '').trim();
  const index = FREE_AGENT_PRIMARY_SORT_CYCLE.findIndex((item) => item.key === currentKey);
  return FREE_AGENT_PRIMARY_SORT_CYCLE[(index + 1) % FREE_AGENT_PRIMARY_SORT_CYCLE.length];
}

function syncFreeAgentPrimarySortHeader(sortCfg = state.sort.free_agents) {
  const th = document.querySelector('#freeAgentsTable thead th[data-free-agent-primary-sort]');
  if (!th) return;
  const selected = FREE_AGENT_PRIMARY_SORT_CYCLE.find((item) => item.key === sortCfg?.key)
    || FREE_AGENT_PRIMARY_SORT_CYCLE[0];
  th.dataset.sort = selected.key;
  th.dataset.label = selected.label;
}

function normalizedPaginationSize(value) {
  const parsed = Number(value);
  return PAGINATED_TABLE_PAGE_SIZES.includes(parsed) ? parsed : PAGINATED_TABLE_PAGE_SIZES[0];
}

function resetPagination(kind) {
  const config = PAGINATED_TABLE_CONFIG[kind];
  if (!config) return;
  state.ui[config.pageKey] = 1;
}

function paginatedRows(rows, kind) {
  const config = PAGINATED_TABLE_CONFIG[kind];
  const allRows = Array.isArray(rows) ? rows : [];
  if (!config) {
    return {
      rows: allRows,
      total: allRows.length,
      page: 1,
      pageSize: allRows.length || PAGINATED_TABLE_PAGE_SIZES[0],
      pageCount: 1,
      start: 0,
      end: allRows.length,
    };
  }
  const pageSize = normalizedPaginationSize(state.ui[config.sizeKey]);
  state.ui[config.sizeKey] = pageSize;
  const total = allRows.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.max(1, Number(state.ui[config.pageKey]) || 1);
  const page = Math.min(currentPage, pageCount);
  state.ui[config.pageKey] = page;
  const start = total ? (page - 1) * pageSize : 0;
  const end = Math.min(start + pageSize, total);
  return {
    rows: allRows.slice(start, end),
    total,
    page,
    pageSize,
    pageCount,
    start,
    end,
  };
}

function ensurePaginationContainer(kind, position) {
  const config = PAGINATED_TABLE_CONFIG[kind];
  if (!config) return null;
  const table = document.getElementById(config.tableId);
  if (!table) return null;
  const wrapper = table.closest('.table-wrap') || table;
  const parent = wrapper.parentElement;
  if (!parent) return null;
  const id = `${kind}Pagination${position === 'top' ? 'Top' : 'Bottom'}`;
  let container = document.getElementById(id);
  if (!container) {
    container = document.createElement('div');
    container.id = id;
    container.className = `table-pagination table-pagination--${position}`;
    if (position === 'top') parent.insertBefore(container, wrapper);
    else parent.insertBefore(container, wrapper.nextSibling);
  }
  return container;
}

function rerenderPaginatedTable(kind) {
  if (kind === 'freeAgents') renderFreeAgents();
  if (kind === 'leaguePlayers') renderLeaguePlayers();
}

function renderPaginationControl(container, kind, meta) {
  if (!container) return;
  if (!meta.total) {
    container.innerHTML = '';
    return;
  }
  const first = meta.start + 1;
  const last = meta.end;
  container.innerHTML = `
    <div class="table-pagination-summary">Mostrando ${first}-${last} de ${meta.total}</div>
    <div class="table-pagination-controls">
      <label>
        <span>Por página</span>
        <select data-pagination-size="${escapeHtml(kind)}">
          ${PAGINATED_TABLE_PAGE_SIZES.map((size) => `<option value="${size}"${size === meta.pageSize ? ' selected' : ''}>${size}</option>`).join('')}
        </select>
      </label>
      <button type="button" data-pagination-page="${escapeHtml(kind)}" data-page="${meta.page - 1}"${meta.page <= 1 ? ' disabled' : ''}>Anterior</button>
      <span class="table-pagination-current">Página ${meta.page} / ${meta.pageCount}</span>
      <button type="button" data-pagination-page="${escapeHtml(kind)}" data-page="${meta.page + 1}"${meta.page >= meta.pageCount ? ' disabled' : ''}>Siguiente</button>
    </div>
  `;
  container.querySelector('[data-pagination-size]')?.addEventListener('change', (event) => {
    const config = PAGINATED_TABLE_CONFIG[kind];
    if (!config) return;
    state.ui[config.sizeKey] = normalizedPaginationSize(event.target.value);
    state.ui[config.pageKey] = 1;
    rerenderPaginatedTable(kind);
  });
  container.querySelectorAll('[data-pagination-page]').forEach((button) => {
    button.addEventListener('click', () => {
      const config = PAGINATED_TABLE_CONFIG[kind];
      if (!config) return;
      const nextPage = Number(button.dataset.page);
      if (!Number.isFinite(nextPage)) return;
      state.ui[config.pageKey] = Math.max(1, nextPage);
      rerenderPaginatedTable(kind);
    });
  });
}

function renderPaginationControls(kind, meta) {
  renderPaginationControl(ensurePaginationContainer(kind, 'top'), kind, meta);
  renderPaginationControl(ensurePaginationContainer(kind, 'bottom'), kind, meta);
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
      <div class="roster-position-sticky-content">
        <span class="roster-position-code">${escapeHtml(positionKey === 'NA' ? '-' : positionKey)}</span>
        <span class="roster-position-name">${escapeHtml(rosterPositionLabel(positionKey))}</span>
        <span class="roster-position-count">${count} ${count === 1 ? 'player' : 'players'}</span>
      </div>
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
  updateSortIndicators('leaguePlayersTable', state.sort.league_players);
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
      const curr = state.sort.free_agents;
      if (th.dataset.freeAgentPrimarySort) {
        const next = nextFreeAgentPrimarySort(curr);
        state.sort.free_agents = { key: next.key, dir: next.dir };
        syncFreeAgentPrimarySortHeader(state.sort.free_agents);
      } else {
        const key = th.dataset.sort;
        state.sort.free_agents = {
          key,
          dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
        };
      }
      resetPagination('freeAgents');
      renderFreeAgents();
      syncFreeAgentPrimarySortHeader(state.sort.free_agents);
      updateSortIndicators('freeAgentsTable', state.sort.free_agents);
    });
  });

  document.querySelectorAll('#leaguePlayersTable thead th[data-sort]').forEach((th) => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      const curr = state.sort.league_players;
      state.sort.league_players = {
        key,
        dir: curr.key === key && curr.dir === 'asc' ? 'desc' : 'asc',
      };
      resetPagination('leaguePlayers');
      renderLeaguePlayers();
      updateSortIndicators('leaguePlayersTable', state.sort.league_players);
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
    syncCoadminVoteNav();
    syncWalletNav();
    syncGmOfficeNav();
    return;
  }

  const userName = auth.user?.name || auth.user?.email || 'Signed In';
  const teamCodes = Array.isArray(auth.team_codes) ? auth.team_codes.filter(Boolean) : [];
  const roleLabel = hasGmLevelRole(auth.role) && teamCodes.length
    ? `${auth.role === 'co_admin' ? 'Co-admin' : 'GM'} ${teamCodes.join('/')}`
    : auth.role;
  badge.textContent = `${userName} (${roleLabel})`;
  loginLink.hidden = true;
  adminLink.hidden = auth.role !== 'admin';
  logoutBtn.hidden = false;
  syncMobileAuthControls(auth);
  syncCoadminVoteNav();
  syncWalletNav();
  syncGmOfficeNav();
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

async function loadCurrentTeamHome() {
  const currentCode = String(state.teamCode || state.teamData?.team?.code || '').trim().toUpperCase();
  const fallbackCode = String((state.teams || [])[0]?.code || '').trim().toUpperCase();
  const code = currentCode || fallbackCode;
  if (code) await loadTeam(code);
}

function currentTeamIndex() {
  const code = String(state.teamCode || '').trim().toUpperCase();
  if (!code) return -1;
  return (state.teams || []).findIndex((team) => String(team.code || '').toUpperCase() === code);
}

function adjacentTeam(delta) {
  const teams = state.teams || [];
  if (!teams.length) return null;
  const index = currentTeamIndex();
  if (index < 0) return null;
  const nextIndex = (index + delta + teams.length) % teams.length;
  return teams[nextIndex] || null;
}

function updateTeamNavButtons() {
  const show = Boolean(state.teamCode && state.teamData && (state.teams || []).length > 1);
  const prevTeam = show ? adjacentTeam(-1) : null;
  const nextTeam = show ? adjacentTeam(1) : null;
  const titleWrap = document.querySelector('.page-title-wrap');
  if (titleWrap) titleWrap.classList.toggle('has-team-nav', show);
  const controls = [
    ['mobilePrevTeamBtn', prevTeam, 'Previous'],
    ['desktopPrevTeamBtn', prevTeam, 'Previous'],
    ['mobileNextTeamBtn', nextTeam, 'Next'],
    ['desktopNextTeamBtn', nextTeam, 'Next'],
  ];

  controls.forEach(([id, team, label]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.hidden = !show || !team;
    btn.disabled = !show || !team;
    const teamLabel = team ? `${team.code} - ${team.name || team.code}` : `${label} team`;
    btn.setAttribute('aria-label', `${label} team: ${teamLabel}`);
    btn.title = teamLabel;
  });
}

async function navigateAdjacentTeam(delta) {
  const target = adjacentTeam(delta);
  if (!target?.code || target.code === state.teamCode) return;
  await loadTeam(target.code);
}

function setupTeamNavControls() {
  [
    ['mobilePrevTeamBtn', -1],
    ['desktopPrevTeamBtn', -1],
    ['mobileNextTeamBtn', 1],
    ['desktopNextTeamBtn', 1],
  ].forEach(([id, delta]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener('click', async () => {
      await navigateAdjacentTeam(delta);
    });
  });
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
  const years = normalizeBirdYears(meta.years) || 'N/A';
  const contractCls = contract === 'N/A' ? '' : typeClass(contract);

  titleEl.textContent = playerName || 'Player info';
  contentEl.innerHTML = `
    <div class="player-meta-row"><span class="player-meta-label">Position</span><span class="pos-pill">${escapeHtml(pos)}</span></div>
    <div class="player-meta-row"><span class="player-meta-label">Rating</span><span class="meta-pill">${escapeHtml(rating)}</span></div>
    <div class="player-meta-row"><span class="player-meta-label">Tipo</span><span class="${contract === 'N/A' ? 'meta-pill' : `type-pill ${contractCls}`}">${escapeHtml(contract)}</span></div>
    <div class="player-meta-row"><span class="player-meta-label">Bird years</span>${years === 'N/A' ? `<span class="meta-pill">${escapeHtml(years)}</span>` : birdYearsCellHtml(years)}</div>
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

function syncCoadminVoteNav() {
  const show = Boolean(state.auth?.authenticated && isCoAdminRole(state.auth?.role));
  ['coadminVotesHomeBtn', 'mobileCoadminVotesBtn'].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = !show;
    el.classList.toggle('section-hidden', !show);
  });
}

function syncWalletNav() {
  const show = canViewWallet();
  ['walletHomeBtn', 'mobileWalletBtn'].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = !show;
    el.classList.toggle('section-hidden', !show);
  });
}

function syncGmOfficeNav() {
  const show = canViewGmOffice();
  ['gmOfficeHomeBtn', 'mobileGmOfficeBtn'].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = !show;
    el.classList.toggle('section-hidden', !show);
  });
}

function syncCoadminVoteBadges() {
  const count = Array.isArray(state.coadminVotes) ? state.coadminVotes.length : 0;
  ['coadminVotesBadge', 'mobileCoadminVotesBadge'].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = String(count);
    el.hidden = count <= 0;
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
  let activeButton = null;

  state.teams.forEach((t) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `team-btn${state.teamCode === t.code ? ' active' : ''}`;
    btn.title = `${t.code} - ${t.name}`;
    if (state.teamCode === t.code) activeButton = btn;

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

  updateTeamNavButtons();
  if (activeButton && window.matchMedia('(min-width: 721px)').matches) {
    window.requestAnimationFrame(() => {
      activeButton.scrollIntoView({ block: 'nearest', inline: 'center' });
    });
  }
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
  const tooltip = String(label || '').toUpperCase().includes('APRON') ? apronTooltipText() : '';
  return `
    <div class="team-balance-card${warningClass}${signClass}"${tooltip ? ` title="${escapeHtml(tooltip)}"` : ''}>
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

function moveSummaryForSeason(data = state.teamData, season = selectedSeasonStart()) {
  const selected = Number(season || selectedSeasonStart());
  const summaries = data?.move_summaries || {};
  const keyed = summaries[String(selected)];
  if (keyed) return keyed;
  const current = data?.move_summary || {};
  if (Number(current.season_year) === selected) return current;
  return current;
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
  const m = moveSummaryForSeason(state.teamData, selectedSeasonStart());
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
  const summary = state.teamData ? summaryForBalanceSeason(state.teamData) : null;
  const summaryHtml = summary
    ? `<div class="mobile-info-summary cards team-summary-grid">${buildSummaryCardsHtml(summary)}</div>`
    : '';
  if (!summaryHtml) return;
  list.innerHTML = summaryHtml;
  list.querySelectorAll('[data-move-log-bucket]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const bucket = normalizeMoveBucket(btn.dataset.moveLogBucket);
      const selectedSeason = selectedSeasonStart();
      const rows = (moveSummaryForSeason(state.teamData, selectedSeason)?.log || []).filter((item) => normalizeMoveBucket(item.bucket) === bucket);
      openMoveLog(`${state.teamCode || ''} · ${seasonLabel(selectedSeason)} · ${moveBucketLabel(bucket)}`, rows);
    });
  });
  state.ui.mobileInfoOpen = true;
  setMobileOverlayVisible('mobileInfoBackdrop', true);
}

function closeMobileInfo() {
  state.ui.mobileInfoOpen = false;
  setMobileOverlayVisible('mobileInfoBackdrop', false);
}

function syncMainNavState() {
  const mode = String(state.ui.viewMode || '');
  document.querySelectorAll('[data-nav-view]').forEach((el) => {
    const modes = String(el.dataset.navView || '').split(/\s+/).filter(Boolean);
    const isActive = modes.includes(mode);
    el.classList.toggle('is-active', isActive);
    if (isActive) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
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
  const figuresSection = document.getElementById('figuresSection');
  const freeAgentsSection = document.getElementById('freeAgentsSection');
  const gmOfficeSection = document.getElementById('gmOfficeSection');
  const leaguePlayersSection = document.getElementById('leaguePlayersSection');
  const draftOrderSection = document.getElementById('draftOrderSection');
  const tradeMachineSection = document.getElementById('tradeMachineSection');
  const walletSection = document.getElementById('walletSection');
  const coadminVotesSection = document.getElementById('coadminVotesSection');
  const showTracker = mode === 'tracker';
  const showFigures = mode === 'figures';
  const showFreeAgents = mode === 'free-agents';
  const showGmOffice = mode === 'gm-office';
  const showLeaguePlayers = mode === 'league-players';
  const showDraftOrder = mode === 'draft-order';
  const showTradeMachine = mode === 'trade-machine';
  const showWallet = mode === 'wallet';
  const showCoadminVotes = mode === 'coadmin-votes';

  trackerSection.classList.toggle('section-hidden', !showTracker);
  if (figuresSection) figuresSection.classList.toggle('section-hidden', !showFigures);
  freeAgentsSection.classList.toggle('section-hidden', !showFreeAgents);
  if (gmOfficeSection) gmOfficeSection.classList.toggle('section-hidden', !showGmOffice);
  if (leaguePlayersSection) leaguePlayersSection.classList.toggle('section-hidden', !showLeaguePlayers);
  if (draftOrderSection) draftOrderSection.classList.toggle('section-hidden', !showDraftOrder);
  if (tradeMachineSection) tradeMachineSection.classList.toggle('section-hidden', !showTradeMachine);
  if (walletSection) walletSection.classList.toggle('section-hidden', !showWallet);
  if (coadminVotesSection) coadminVotesSection.classList.toggle('section-hidden', !showCoadminVotes);
  syncTrackerTabs();
  syncTeamTabs();
  syncMainNavState();
  syncMobileInfoButton();
}

function renderTracker() {
  const tbody = document.querySelector('#trackerTable tbody');
  tbody.innerHTML = '';
  populateTrackerSeasonSelect();

  const rows = sortedRows(state.trackerRows, state.sort.tracker);
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><button type="button" class="tracker-team-btn" data-team-code="${row.team_code}">${row.team_code}</button></td>
      <td>${trackerHardCapBadgeHtml(row.apron_hard_cap)}</td>
      <td><span class="cap-total-tooltip" title="${escapeHtml(capTotalTooltipText())}">${formatMoneyDots(row.cap_total)}</span></td>
      <td>${formatMoneyDots(row.gasto_total)}</td>
      <td>${trackerSpaceValueHtml(row.espacio_cap)}</td>
      <td>${trackerSpaceValueHtml(row.espacio_luxury)}</td>
      <td>${trackerLuxuryTaxValueHtml(row.luxury_tax)}</td>
      <td title="${escapeHtml(apronTooltipText())}">${trackerSpaceValueHtml(row.espacio_1er_apron)}</td>
      <td title="${escapeHtml(apronTooltipText())}">${trackerSpaceValueHtml(row.espacio_2do_apron)}</td>
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

function populateTrackerSeasonSelect() {
  const select = document.getElementById('trackerSeasonSelect');
  if (!select) return;
  const selected = selectedTrackerSeason();
  select.innerHTML = trackerSeasonOptions()
    .map((season) => `<option value="${season}">${seasonLabel(season)}${season === currentSeasonStart() ? ' (current)' : ''}</option>`)
    .join('');
  select.value = String(selected);
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

function freeAgentById(id) {
  const parsed = Number(id);
  return (state.freeAgents || []).find((agent) => Number(agent.id) === parsed) || null;
}

function freeAgentActionTeamCodes() {
  const auth = state.auth || {};
  if (auth.role === 'admin') {
    return (state.teams || []).map((team) => team.code).filter(Boolean);
  }
  if (!hasGmLevelRole(auth.role)) return [];
  return Array.isArray(auth.team_codes)
    ? auth.team_codes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)
    : [];
}

function canSubmitFreeAgentAction() {
  const auth = state.auth || {};
  return Boolean(
    auth.authenticated
      && (auth.role === 'admin' || hasGmLevelRole(auth.role))
      && freeAgentActionTeamCodes().length
  );
}

function preferredFreeAgentActionTeamCode() {
  const codes = freeAgentActionTeamCodes();
  return codes.length === 1 ? codes[0] : '';
}

function freeAgentRequestStatusLabel(status) {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'approved') return 'Aprobada';
  if (normalized === 'rejected') return 'Rechazada';
  if (normalized === 'pending') return 'Pendiente';
  return normalized || 'Sin estado';
}

function freeAgentOfferSummaryText(offer) {
  const payload = offer?.offer_payload || {};
  const type = payload.contract_type || offer?.offer_contract_type || 'Contrato';
  const years = Number(payload.years || offer?.offer_years || 0);
  const start = payload.start_season_label || payload.start_season || '';
  const rawRaise = payload.annual_raise_percent ?? payload.raise_pct;
  const raiseValue = rawRaise !== undefined && rawRaise !== null && rawRaise !== '' ? Number(rawRaise) : 0;
  const raise = Number.isFinite(raiseValue) && raiseValue !== 0
    ? ` · ${raiseValue > 0 ? 'Subidas' : 'Bajadas'} ${Math.abs(raiseValue)}%`
    : '';
  const salaryBySeason = payload.salary_by_season && typeof payload.salary_by_season === 'object' ? payload.salary_by_season : {};
  const firstSalaryBySeason = Object.keys(salaryBySeason).sort().map((year) => salaryBySeason[year]).find(Boolean);
  const firstAmount = firstSalaryBySeason || (Array.isArray(payload.year_salaries) && payload.year_salaries.length
    ? payload.year_salaries[0]?.amount
    : payload.first_year_amount);
  const amount = firstAmount
    ? ` · Desde ${typeof firstAmount === 'string' ? firstAmount : formatMoneyDots(firstAmount)}`
    : '';
  return `${type}${years ? ` · ${years} año${years === 1 ? '' : 's'}` : ''}${start ? ` · ${start}` : ''}${raise}${amount}`;
}

function updateWaiverBadges() {
  const count = Array.isArray(state.waivers) ? state.waivers.length : 0;
  ['freeAgentsHomeBtn', 'mobileFreeAgentsBtn'].forEach((id) => {
    const button = document.getElementById(id);
    if (!button) return;
    button.querySelector('.waiver-count-badge')?.remove();
    if (count < 1) return;
    const badge = document.createElement('span');
    badge.className = 'waiver-count-badge';
    badge.textContent = String(count);
    badge.setAttribute('aria-label', `${count} jugador${count === 1 ? '' : 'es'} en waivers`);
    button.appendChild(badge);
  });
}

async function refreshWaiverBadges() {
  try {
    const waiverRes = await api('/api/waivers');
    state.waivers = Array.isArray(waiverRes.waivers) ? waiverRes.waivers : [];
    updateWaiverBadges();
  } catch {
    state.waivers = [];
    updateWaiverBadges();
  }
}

function populateFreeAgentActionTeams(selectId, selected = '') {
  const select = document.getElementById(selectId);
  if (!select) return;
  const codes = freeAgentActionTeamCodes();
  const preferred = String(selected || state.teamCode || codes[0] || '').toUpperCase();
  select.innerHTML = codes
    .map((code) => {
      const team = (state.teams || []).find((item) => item.code === code);
      const label = team ? `${team.code} - ${team.name}` : code;
      return `<option value="${escapeHtml(code)}"${code === preferred ? ' selected' : ''}>${escapeHtml(label)}</option>`;
    })
    .join('');
  if (preferred && codes.includes(preferred)) select.value = preferred;
}

function setFreeAgentActionStatus(kind, message = '', isError = false) {
  const el = document.getElementById(kind === 'offer' ? 'freeAgentOfferStatus' : 'freeAgentNegotiateStatus');
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('error-text', Boolean(isError));
}

function formatWaiverExpiry(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || '');
  return date.toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function waiverEligibilityMessage(waiver) {
  const eligibility = waiver?.eligibility || {};
  if (waiver?.already_claimed) return 'Ya has enviado una reclamación por este jugador.';
  if (eligibility.eligible) return '';
  if (eligibility.requires_contingent_cut) return 'Necesitas liberar una plaza. Elige un jugador para cortar solo si la reclamación se aprueba.';
  const reason = String(eligibility.reason || '').trim();
  if (reason === 'same_team') return 'El equipo que cortó al jugador no puede reclamarlo.';
  if (reason === 'salary_room_required') return 'Tu equipo no tiene espacio salarial ni excepción suficiente para absorber este contrato.';
  if (reason === 'team_not_found') return 'No se pudo validar el equipo.';
  return 'Tu equipo no cumple los requisitos para reclamar este jugador.';
}

async function askWaiverContingentCutPlayer(teamCode) {
  const data = await api(`/api/teams/${encodeURIComponent(teamCode)}`);
  const players = Array.isArray(data.players) ? data.players : [];
  const standardPlayers = players.filter((player) => String(player.bird_rights || '').trim().toUpperCase() !== 'TW');
  if (!standardPlayers.length) return null;
  const options = standardPlayers
    .map((player) => `${player.id}: ${player.name || 'Jugador sin nombre'}`)
    .join('\n');
  const answer = window.prompt(
    `No hay hueco de plantilla. Escribe el ID del jugador que se cortará si la reclamación prospera:\n\n${options}`
  );
  if (answer === null) return null;
  const selectedId = Number(answer.trim());
  if (!Number.isInteger(selectedId) || !standardPlayers.some((player) => Number(player.id) === selectedId)) {
    alert('ID de jugador no válido.');
    return null;
  }
  return selectedId;
}

async function submitWaiverClaim(waiver) {
  if (!canSubmitFreeAgentAction()) {
    alert('Necesitas iniciar sesión como GM para reclamar waivers.');
    return;
  }
  if (waiver?.already_claimed) {
    alert('Ya has enviado una reclamación por este jugador. Las reclamaciones no se pueden retirar.');
    return;
  }
  const codes = freeAgentActionTeamCodes();
  const teamCode = codes.length === 1
    ? codes[0]
    : window.prompt(`Equipo que reclama (${codes.join(', ')}):`, codes[0] || '');
  const normalizedTeam = String(teamCode || '').trim().toUpperCase();
  if (!normalizedTeam || !codes.includes(normalizedTeam)) return;
  const eligibility = waiver?.eligibility || {};
  let contingentCutPlayerId = null;
  if (eligibility.requires_contingent_cut) {
    contingentCutPlayerId = await askWaiverContingentCutPlayer(normalizedTeam);
    if (!contingentCutPlayerId) return;
  } else if (!eligibility.eligible) {
    alert(waiverEligibilityMessage(waiver));
    return;
  }
  if (!window.confirm(`¿Confirmas reclamar de waivers a ${waiver.player_name || 'este jugador'}? La solicitud no se puede retirar.`)) {
    return;
  }
  try {
    await api(`/api/waivers/${waiver.id}/claims`, {
      method: 'POST',
      body: JSON.stringify({
        team_code: normalizedTeam,
        contingent_cut_player_id: contingentCutPlayerId,
      }),
    });
    alert('Reclamación enviada. Quedará pendiente hasta que expire el plazo de waivers o la administración resuelva múltiples solicitudes.');
    await loadFreeAgents();
  } catch (err) {
    alert(`No se pudo reclamar el jugador: ${err.message || err}`);
  }
}

function renderWaiversPanel() {
  const panel = document.getElementById('waiversPanel');
  if (!panel) return;
  const waivers = Array.isArray(state.waivers) ? state.waivers : [];
  updateWaiverBadges();
  if (!waivers.length) {
    panel.innerHTML = '';
    return;
  }
  panel.innerHTML = `
    <div class="waivers-panel">
      <div class="waivers-panel-header">
        <h3>Waivers</h3>
        <span class="waivers-count">${waivers.length}</span>
      </div>
      <div class="table-wrap waivers-table-wrap">
        <table class="waivers-table">
          <thead>
            <tr>
              <th>Jugador</th>
              <th>Origen</th>
              <th>Salario</th>
              <th>Expira</th>
              <th>Acción</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  `;
  const tbody = panel.querySelector('tbody');
  waivers.forEach((waiver) => {
    const message = waiverEligibilityMessage(waiver);
    const disabled = waiver.already_claimed || (!waiver?.eligibility?.eligible && !waiver?.eligibility?.requires_contingent_cut);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${escapeHtml(waiver.player_name || '')}</strong><div class="muted">${escapeHtml(waiver.position || '')}${waiver.rating ? ` · ${escapeHtml(waiver.rating)}` : ''}</div></td>
      <td>${escapeHtml(waiver.from_team_code || '')}</td>
      <td>${formatMoneyDots(waiver.salary || 0)}</td>
      <td>${escapeHtml(formatWaiverExpiry(waiver.waiver_expires_at))}</td>
      <td>
        <button type="button" data-waiver-claim="${escapeHtml(waiver.id)}" ${disabled ? 'disabled' : ''}>${waiver.already_claimed ? 'Reclamado' : 'Reclamar'}</button>
        ${message ? `<div class="muted waiver-eligibility-note">${escapeHtml(message)}</div>` : ''}
      </td>
    `;
    tr.querySelector('[data-waiver-claim]')?.addEventListener('click', () => submitWaiverClaim(waiver));
    tbody.appendChild(tr);
  });
}

function freeAgentActionSummary(agent, includeAgent = false) {
  const parts = [
    `<strong>${escapeHtml(agent?.name || 'Agente libre')}</strong>`,
    agent?.position ? escapeHtml(agent.position) : '',
    agent?.rating ? `Rating ${escapeHtml(agent.rating)}` : '',
    includeAgent && agent?.agent ? `Agente: ${escapeHtml(agent.agent)}` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

function freeAgentOfferIsRenewal(agent, teamCode) {
  const team = String(teamCode || '').trim().toUpperCase();
  if (!team || String(agent?.source || '').trim() !== 'cap_hold') return false;
  let rightsTeam = String(agent?.rights_team_code || '').trim().toUpperCase();
  if (!rightsTeam) {
    const match = String(agent?.notes || '').match(/Cap hold retenido por\s+([A-Z]{2,4})/i);
    rightsTeam = match ? String(match[1] || '').trim().toUpperCase() : '';
  }
  return Boolean(rightsTeam && rightsTeam === team);
}

function freeAgentOfferParseAmount(raw) {
  if (typeof parseAmountLike === 'function') return parseAmountLike(raw);
  if (typeof parseAmount === 'function') return parseAmount(raw);
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : null;
}

function freeAgentOfferExperienceYears(agent) {
  const experience = normalizeExperienceYears(agent?.experience_years);
  return experience === null ? 0 : experience;
}

function freeAgentOfferContractType() {
  return String(document.getElementById('freeAgentOfferType')?.value || '').trim();
}

function freeAgentOfferRaisePercent() {
  const input = document.getElementById('freeAgentOfferRaisePct');
  const value = Number(input?.value || 0);
  return Number.isFinite(value) ? value : 0;
}

function freeAgentOfferBirdRightsCode(agent) {
  const raw = String(agent?.bird_rights || '').trim().toUpperCase().replace(/[\s_-]+/g, '');
  if (raw === 'FB' || raw === 'FULLBIRD') return 'FB';
  if (raw === 'EB' || raw === 'EARLYBIRD') return 'EB';
  if (raw === 'NB' || raw === 'NONBIRD') return 'NB';
  return capHoldBirdCodeFromYears(agent?.years_left);
}

function freeAgentOfferCanUseBirdRaises(agent) {
  const teamCode = document.getElementById('freeAgentOfferTeam')?.value || '';
  const rights = freeAgentOfferBirdRightsCode(agent);
  return freeAgentOfferIsRenewal(agent, teamCode) && ['FB', 'EB'].includes(rights);
}

function freeAgentOfferMinimumAmount(agent, season, contractYear = 1) {
  const type = freeAgentOfferContractType().toUpperCase();
  if (type === 'E10') return 0;
  if (type === 'TW') return twoWayMinimumSalaryForSeason(season) || 0;
  const experience = freeAgentOfferExperienceYears(agent);
  return (
    minimumSalaryForSeason(season, experience, contractYear)
    || minimumSalaryForSeason(season, Math.min(10, experience + contractYear - 1), 1)
    || 0
  );
}

function freeAgentOfferMaximumAmount(agent, season) {
  const type = freeAgentOfferContractType().toUpperCase();
  if (type === 'E10') return Infinity;
  return maximumSalaryForExperience(season, agent?.experience_years) || Infinity;
}

function setFreeAgentOfferValidation(message = '', isError = false) {
  const alert = document.getElementById('freeAgentOfferValidation');
  if (alert) {
    alert.textContent = message;
    alert.classList.toggle('section-hidden', !message);
    alert.classList.toggle('is-error', Boolean(isError));
  }
  const btn = document.getElementById('freeAgentOfferSubmitBtn');
  if (btn) btn.disabled = Boolean(isError);
  return !isError;
}

function syncFreeAgentOfferAmounts() {
  const agent = freeAgentById(state.ui.freeAgentActionId);
  const inputs = Array.from(document.querySelectorAll('[data-offer-salary-season]'));
  const raiseInput = document.getElementById('freeAgentOfferRaisePct');
  const contractType = freeAgentOfferContractType().toUpperCase();
  if (!agent || !inputs.length) {
    setFreeAgentOfferValidation();
    return true;
  }

  const isMinimumContract = contractType === 'MIN';
  const isMaximumContract = contractType === 'MAX';
  if (raiseInput) {
    raiseInput.disabled = isMinimumContract;
    if (isMinimumContract) raiseInput.value = '0';
  }

  const firstInput = inputs[0];
  const firstSeason = Number(firstInput?.dataset.offerSalarySeason || defaultSeasonViewStart());
  const firstMinimum = freeAgentOfferMinimumAmount(agent, firstSeason, 1);
  const firstMaximum = freeAgentOfferMaximumAmount(agent, firstSeason);
  if (firstInput) {
    if (isMinimumContract) {
      firstInput.value = formatDots(firstMinimum);
    } else if (isMaximumContract && Number.isFinite(firstMaximum)) {
      firstInput.value = formatDots(firstMaximum);
    }
  }
  if (firstInput) firstInput.readOnly = isMinimumContract || isMaximumContract;

  const firstAmount = firstInput ? freeAgentOfferParseAmount(firstInput.value) : null;
  const raisePercent = freeAgentOfferRaisePercent();
  const canUseBirdRaises = freeAgentOfferCanUseBirdRaises(agent);
  inputs.forEach((input, idx) => {
    if (idx === 0) return;
    input.readOnly = true;
    const season = Number(input.dataset.offerSalarySeason || firstSeason + idx);
    if (isMinimumContract) {
      input.value = formatDots(freeAgentOfferMinimumAmount(agent, season, idx + 1));
      return;
    }
    if (firstAmount === null || firstAmount <= 0) {
      input.value = '';
      return;
    }
    const annualRaise = firstAmount * (raisePercent / 100);
    input.value = formatDots(Math.round(firstAmount + (annualRaise * idx)));
  });

  if (contractType !== 'E10' && (firstAmount === null || firstAmount <= 0)) {
    return setFreeAgentOfferValidation('Introduce el importe del primer año.', true);
  }
  if (firstAmount !== null && firstAmount < firstMinimum) {
    return setFreeAgentOfferValidation(`El importe del primer año no puede ser inferior al mínimo: ${formatDots(firstMinimum)}.`, true);
  }
  if (firstAmount !== null && Number.isFinite(firstMaximum) && firstAmount > firstMaximum) {
    return setFreeAgentOfferValidation(`El importe del primer año supera el máximo permitido para este jugador: ${formatDots(firstMaximum)}.`, true);
  }
  if (raisePercent < -8 || raisePercent > 8) {
    return setFreeAgentOfferValidation('Los incrementos interanuales deben estar entre -8% y 8%.', true);
  }
  if (raisePercent > 5 && !canUseBirdRaises) {
    return setFreeAgentOfferValidation('Solo los equipos con Full Bird o Early Bird pueden ofrecer subidas superiores al 5%.', true);
  }
  return setFreeAgentOfferValidation();
}

function updateFreeAgentOfferSummary() {
  const agent = freeAgentById(state.ui.freeAgentActionId);
  const summary = document.getElementById('freeAgentOfferSummary');
  if (!agent || !summary) return;
  const teamCode = document.getElementById('freeAgentOfferTeam')?.value || '';
  const renewalBadge = freeAgentOfferIsRenewal(agent, teamCode)
    ? ' · <span class="free-agent-offer-kind free-agent-offer-kind--renewal">Oferta de renovación</span>'
    : ' · <span class="free-agent-offer-kind">Oferta FA</span>';
  summary.innerHTML = `${freeAgentActionSummary(agent)}${renewalBadge}`;
}

function renderFreeAgentOfferYearsTable(options = {}) {
  const tbody = document.querySelector('#freeAgentOfferYearsTable tbody');
  const yearsSelect = document.getElementById('freeAgentOfferYears');
  if (!tbody || !yearsSelect) return;
  const previousFirstAmount = options.preserveFirstAmount
    ? String(document.querySelector('[data-offer-salary-season]')?.value || '')
    : '';
  const years = Math.max(1, Math.min(5, Number(yearsSelect.value || 1)));
  const start = defaultSeasonViewStart();
  tbody.innerHTML = Array.from({ length: years }, (_, idx) => {
    const season = start + idx;
    return `
      <tr>
        <td>${seasonLabel(season)}</td>
        <td><input data-offer-salary-season="${season}" data-offer-salary-index="${idx}" type="text" inputmode="numeric" placeholder="Importe"${idx === 0 ? '' : ' readonly'}></td>
        <td>
          <select data-offer-option-season="${season}"${idx === 0 ? ' disabled' : ''}>
            <option value="">${idx === 0 ? 'No disponible' : ''}</option>
            ${idx === 0 ? '' : '<option value="TO">TO</option><option value="PO">PO</option>'}
          </select>
        </td>
      </tr>
    `;
  }).join('');
  const firstInput = tbody.querySelector('[data-offer-salary-index="0"]');
  if (firstInput && previousFirstAmount) firstInput.value = previousFirstAmount;
  tbody.querySelectorAll('[data-offer-salary-season]').forEach((input) => {
    input.addEventListener('input', syncFreeAgentOfferAmounts);
  });
  syncFreeAgentOfferAmounts();
}

function openFreeAgentOfferModal(agent) {
  if (!canSubmitFreeAgentAction()) {
    alert('Inicia sesión como GM para enviar ofertas.');
    return;
  }
  if (!agent) return;
  state.ui.freeAgentActionId = Number(agent.id);
  populateFreeAgentActionTeams('freeAgentOfferTeam');
  updateFreeAgentOfferSummary();
  document.getElementById('freeAgentOfferType').value = 'Reg';
  document.getElementById('freeAgentOfferYears').value = '1';
  document.getElementById('freeAgentOfferRaisePct').value = '0';
  document.getElementById('freeAgentOfferNotes').value = '';
  renderFreeAgentOfferYearsTable();
  setFreeAgentActionStatus('offer');
  document.getElementById('freeAgentOfferModal')?.classList.remove('section-hidden');
}

function closeFreeAgentOfferModal() {
  state.ui.freeAgentActionId = null;
  document.getElementById('freeAgentOfferModal')?.classList.add('section-hidden');
}

function freeAgentOfferPayload() {
  const salaryBySeason = {};
  const optionBySeason = {};
  document.querySelectorAll('[data-offer-salary-season]').forEach((input) => {
    const season = input.dataset.offerSalarySeason;
    const value = String(input.value || '').trim();
    if (value) salaryBySeason[season] = value;
  });
  document.querySelectorAll('[data-offer-option-season]').forEach((select) => {
    const season = select.dataset.offerOptionSeason;
    const value = String(select.value || '').trim();
    if (value) optionBySeason[season] = value;
  });
  return {
    team_code: document.getElementById('freeAgentOfferTeam')?.value || '',
    contract_type: document.getElementById('freeAgentOfferType')?.value || '',
    years: Number(document.getElementById('freeAgentOfferYears')?.value || 1),
    annual_raise_percent: freeAgentOfferRaisePercent(),
    salary_by_season: salaryBySeason,
    option_by_season: optionBySeason,
    notes: document.getElementById('freeAgentOfferNotes')?.value.trim() || '',
  };
}

async function submitFreeAgentOffer() {
  const agent = freeAgentById(state.ui.freeAgentActionId);
  if (!agent) return;
  if (!syncFreeAgentOfferAmounts()) return;
  const payload = freeAgentOfferPayload();
  if (!payload.team_code) {
    setFreeAgentActionStatus('offer', 'Selecciona un equipo.', true);
    return;
  }
  const btn = document.getElementById('freeAgentOfferSubmitBtn');
  const oldText = btn?.textContent || '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Enviando...';
  }
  try {
    const result = await api(`/api/free-agents/${agent.id}/offer`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const requestKind = result.offer_type === 'renewal' ? 'Oferta de renovación' : 'Oferta';
    if (result.discord_sent) {
      setFreeAgentActionStatus('offer', `${requestKind} enviada a la administración y comunicada por Discord al agente. Quedará pendiente de aprobación.`);
    } else if (result.discord_thread_sent) {
      setFreeAgentActionStatus(
        'offer',
        `${requestKind} enviada a la administración. Se avisó en el hilo público, pero el DM privado al agente no está configurado o falló.`,
        true,
      );
    } else {
      setFreeAgentActionStatus(
        'offer',
        `${requestKind} enviada a la administración. Quedará pendiente de aprobación, pero Discord no está configurado o falló.`,
        true,
      );
    }
    if (document.getElementById('gmOfficeSection') && !document.getElementById('gmOfficeSection').classList.contains('section-hidden')) {
      await fetchGmOffice();
    }
  } catch (err) {
    setFreeAgentActionStatus('offer', `No se pudo enviar la oferta: ${err.message}`, true);
  } finally {
    if (btn) {
      btn.textContent = oldText;
    }
    syncFreeAgentOfferAmounts();
  }
}

function openFreeAgentNegotiateModal(agent) {
  if (!canSubmitFreeAgentAction()) {
    alert('Inicia sesión como GM para negociar con agentes.');
    return;
  }
  if (!agent) return;
  state.ui.freeAgentActionId = Number(agent.id);
  document.getElementById('freeAgentNegotiateSummary').innerHTML = freeAgentActionSummary(agent, true);
  populateFreeAgentActionTeams('freeAgentNegotiateTeam');
  document.getElementById('freeAgentNegotiateEconomic').value = '';
  document.getElementById('freeAgentNegotiateRole').value = '';
  document.getElementById('freeAgentNegotiateComments').value = '';
  setFreeAgentActionStatus('negotiate');
  document.getElementById('freeAgentNegotiateModal')?.classList.remove('section-hidden');
}

function closeFreeAgentNegotiateModal() {
  state.ui.freeAgentActionId = null;
  document.getElementById('freeAgentNegotiateModal')?.classList.add('section-hidden');
}

async function submitFreeAgentNegotiation() {
  const agent = freeAgentById(state.ui.freeAgentActionId);
  if (!agent) return;
  const payload = {
    team_code: document.getElementById('freeAgentNegotiateTeam')?.value || '',
    economic_offer: document.getElementById('freeAgentNegotiateEconomic')?.value.trim() || '',
    role_offer: document.getElementById('freeAgentNegotiateRole')?.value.trim() || '',
    comments: document.getElementById('freeAgentNegotiateComments')?.value.trim() || '',
  };
  if (!payload.team_code) {
    setFreeAgentActionStatus('negotiate', 'Selecciona un equipo.', true);
    return;
  }
  const btn = document.getElementById('freeAgentNegotiateSubmitBtn');
  const oldText = btn?.textContent || '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Enviando...';
  }
  try {
    await api(`/api/free-agents/${agent.id}/negotiate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    setFreeAgentActionStatus('negotiate', 'Interés registrado en la cartera del agente.');
  } catch (err) {
    setFreeAgentActionStatus('negotiate', `No se pudo registrar el interés: ${err.message}`, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  }
}

function coadminVoteTeamInputHtml(team, scores = {}) {
  const code = String(team.code || '').trim().toUpperCase();
  const score = scores && Object.prototype.hasOwnProperty.call(scores, code) ? scores[code] : '';
  return `
    <label class="coadmin-vote-team">
      <span class="coadmin-vote-team-identity">
        ${draftOrderLogoHtml(code, 'coadmin-vote-team-logo')}
        <span>
          <strong>${escapeHtml(code)}</strong>
          <small>${escapeHtml(team.name || code)}</small>
        </span>
      </span>
      <input
        type="number"
        min="1"
        max="100"
        step="1"
        inputmode="numeric"
        value="${escapeHtml(score)}"
        data-coadmin-vote-score="${escapeHtml(code)}"
        aria-label="Puntuación para ${escapeHtml(code)}"
      >
    </label>
  `;
}

function renderCoadminVotes() {
  const board = document.getElementById('coadminVotesBoard');
  const subtitle = document.getElementById('coadminVotesSubtitle');
  if (!board) return;
  if (!isCoAdminRole(state.auth?.role)) {
    board.innerHTML = '<p class="muted">No tienes votaciones pendientes.</p>';
    if (subtitle) subtitle.textContent = '';
    return;
  }
  const votes = Array.isArray(state.coadminVotes) ? state.coadminVotes : [];
  if (subtitle) subtitle.textContent = votes.length ? `${votes.length} votación(es) abiertas.` : 'No tienes votaciones abiertas.';
  if (!votes.length) {
    board.innerHTML = '<article class="coadmin-vote-card"><p class="muted">No hay votaciones abiertas ahora mismo.</p></article>';
    return;
  }
  board.innerHTML = votes.map((vote) => {
    const teams = Array.isArray(vote.target_teams) ? vote.target_teams : [];
    const submitted = Boolean(vote.submitted);
    return `
      <article class="coadmin-vote-card ${submitted ? 'is-submitted' : ''}" data-coadmin-vote-card="${escapeHtml(vote.id)}">
        <div class="coadmin-vote-head">
          <div>
            <h3>${escapeHtml(vote.title || 'Votación')}</h3>
            <p>${submitted ? 'Voto enviado. Puedes actualizarlo mientras siga abierta.' : `Completa ${teams.length} puntuaciones del 1 al 100.`}</p>
          </div>
          <span class="coadmin-vote-status">${submitted ? 'Enviada' : 'Pendiente'}</span>
        </div>
        <div class="coadmin-vote-progress">
          ${escapeHtml(vote.submitted_voter_count || 0)} / ${escapeHtml(vote.expected_voter_count || 0)} co-admins han votado
        </div>
        <div class="coadmin-vote-grid">
          ${teams.map((team) => coadminVoteTeamInputHtml(team, vote.scores || {})).join('')}
        </div>
        <div class="coadmin-vote-actions">
          <span class="coadmin-vote-message" data-coadmin-vote-message></span>
          <button type="button" data-coadmin-vote-submit="${escapeHtml(vote.id)}">${submitted ? 'Actualizar voto' : 'Enviar voto'}</button>
        </div>
      </article>
    `;
  }).join('');
}

async function submitCoadminVote(voteId) {
  const card = document.querySelector(`[data-coadmin-vote-card="${Number(voteId)}"]`);
  if (!card) return;
  const inputs = Array.from(card.querySelectorAll('[data-coadmin-vote-score]'));
  const scores = {};
  let invalid = false;
  inputs.forEach((input) => {
    const code = String(input.dataset.coadminVoteScore || '').trim().toUpperCase();
    const value = Number(input.value);
    if (!code || !Number.isInteger(value) || value < 1 || value > 100) {
      invalid = true;
      input.classList.add('is-invalid');
      return;
    }
    input.classList.remove('is-invalid');
    scores[code] = value;
  });
  const message = card.querySelector('[data-coadmin-vote-message]');
  if (invalid || Object.keys(scores).length !== inputs.length) {
    if (message) message.textContent = 'Completa todas las puntuaciones con números del 1 al 100.';
    return;
  }
  const button = card.querySelector('[data-coadmin-vote-submit]');
  const oldText = button?.textContent || '';
  if (button) {
    button.disabled = true;
    button.textContent = 'Enviando...';
  }
  if (message) message.textContent = '';
  try {
    const result = await api(`/api/coadmin-votes/${voteId}/submit`, {
      method: 'POST',
      body: JSON.stringify({ scores }),
    });
    const updated = result.vote;
    if (updated && Array.isArray(state.coadminVotes)) {
      state.coadminVotes = state.coadminVotes.map((vote) => (
        String(vote.id) === String(voteId) ? updated : vote
      ));
    }
    syncCoadminVoteBadges();
    renderCoadminVotes();
  } catch (err) {
    if (message) message.textContent = `No se pudo enviar: ${err.message}`;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
}

async function loadCoadminVotes() {
  setPageHeading('Votaciones', 'Tarjetas de co-admin');
  setViewMode('coadmin-votes');
  if (!isCoAdminRole(state.auth?.role)) {
    state.coadminVotes = [];
    renderCoadminVotes();
    return;
  }
  const result = await api('/api/coadmin-votes');
  state.coadminVotes = Array.isArray(result.votes) ? result.votes : [];
  syncCoadminVoteBadges();
  renderCoadminVotes();
}

async function refreshCoadminVoteRequests({ silent = true } = {}) {
  if (!isCoAdminRole(state.auth?.role)) {
    state.coadminVotes = [];
    syncCoadminVoteBadges();
    return;
  }
  try {
    const result = await api('/api/coadmin-votes');
    state.coadminVotes = Array.isArray(result.votes) ? result.votes : [];
    syncCoadminVoteBadges();
  } catch (err) {
    if (!silent) throw err;
  }
}

function renderFreeAgents() {
  const tbody = document.querySelector('#freeAgentsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const searchInput = document.getElementById('freeAgentSearchInput');
  if (searchInput && searchInput.value !== String(state.ui.freeAgentSearch || '')) {
    searchInput.value = state.ui.freeAgentSearch || '';
  }
  const query = String(state.ui.freeAgentSearch || '').trim().toLowerCase();
  const filteredRows = query
    ? (state.freeAgents || []).filter((agent) => String(agent.name || '').toLowerCase().includes(query))
    : (state.freeAgents || []);
  const allRows = sortedRows(filteredRows, state.sort.free_agents);
  const pagination = paginatedRows(allRows, 'freeAgents');
  syncFreeAgentPrimarySortHeader(state.sort.free_agents);
  renderPaginationControls('freeAgents', pagination);
  if (!allRows.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="4">No hay agentes libres registrados.</td>';
    tbody.appendChild(tr);
    return;
  }
  pagination.rows.forEach((agent) => {
    const freeAgentType = String(agent.free_agent_type || 'No restringido').trim() === 'Restringido' ? 'Restringido' : 'No restringido';
    const canAct = canSubmitFreeAgentAction();
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="free-agent-player-cell">
        <div class="free-agent-player-row">
          <div class="free-agent-player-main">
            <strong>${escapeHtml(agent.name || '')}</strong>
            <div class="free-agent-player-tags">
              ${agent.position ? `<span class="free-agent-meta-tag free-agent-meta-tag--position">${escapeHtml(agent.position)}</span>` : ''}
              ${agent.rating ? `<span class="free-agent-meta-tag">${escapeHtml(agent.rating)}</span>` : ''}
            </div>
          </div>
          <div class="free-agent-inline-actions">
            <button data-action="offer-free-agent" type="button" ${canAct ? '' : 'disabled'}>Ofertar</button>
            <button data-action="negotiate-free-agent" type="button" class="ghost" ${canAct ? '' : 'disabled'}>Negociar</button>
            <button
              data-action="favorite-free-agent"
              type="button"
              class="free-agent-favorite-btn ${agent.is_favorite ? 'is-favorite' : ''}"
              title="${agent.is_favorite ? 'Quitar de favoritos' : 'Añadir a favoritos'}"
              aria-label="${agent.is_favorite ? 'Quitar de favoritos' : 'Añadir a favoritos'}"
              ${canAct ? '' : 'disabled'}
            >${agent.is_favorite ? '♥' : '♡'}</button>
          </div>
        </div>
      </td>
      <td><span class="free-agent-type-pill ${freeAgentType === 'Restringido' ? 'free-agent-type-pill--restricted' : ''}">${escapeHtml(freeAgentType)}</span></td>
      <td>${escapeHtml(agent.agent || '')}</td>
      <td class="details-cell">${escapeHtml(agent.notes || '')}</td>
    `;
    tr.querySelector('[data-action="offer-free-agent"]')?.addEventListener('click', () => {
      openFreeAgentOfferModal(agent);
    });
    tr.querySelector('[data-action="negotiate-free-agent"]')?.addEventListener('click', () => {
      openFreeAgentNegotiateModal(agent);
    });
    tr.querySelector('[data-action="favorite-free-agent"]')?.addEventListener('click', () => {
      void toggleFreeAgentFavorite(agent);
    });
    tbody.appendChild(tr);
  });
}

async function toggleFreeAgentFavorite(agent) {
  if (!agent || !agent.id) return;
  const teamCode = preferredFreeAgentActionTeamCode();
  if (!teamCode) {
    alert('Selecciona un equipo antes de guardar favoritos.');
    return;
  }
  const nextFavorite = !agent.is_favorite;
  try {
    await api(`/api/free-agents/${agent.id}/${nextFavorite ? 'favorite' : 'unfavorite'}`, {
      method: 'POST',
      body: JSON.stringify({ team_code: teamCode }),
    });
    state.freeAgents = (state.freeAgents || []).map((item) => (
      Number(item.id) === Number(agent.id)
        ? { ...item, is_favorite: nextFavorite, favorite_team_code: teamCode }
        : item
    ));
    state.gmOffice.favorites = nextFavorite
      ? state.gmOffice.favorites
      : (state.gmOffice.favorites || []).filter((item) => Number(item.id) !== Number(agent.id));
    renderFreeAgents();
    if (state.ui.viewMode === 'gm-office') renderGmOffice();
  } catch (err) {
    alert(`No se pudo actualizar favoritos: ${err.message}`);
  }
}

function gmOfficeStatusBadge(status) {
  const normalized = String(status || '').trim().toLowerCase();
  const label = freeAgentRequestStatusLabel(normalized);
  return `<span class="gm-office-status-badge gm-office-status-badge--${escapeHtml(normalized || 'default')}">${escapeHtml(label)}</span>`;
}

function renderGmOffice() {
  const subtitle = document.getElementById('gmOfficeSubtitle');
  const offersStatus = document.getElementById('gmOfficeOffersStatus');
  const favoritesStatus = document.getElementById('gmOfficeFavoritesStatus');
  const offersBody = document.querySelector('#gmOfficeOffersTable tbody');
  const favoritesBody = document.querySelector('#gmOfficeFavoritesTable tbody');
  if (!offersBody || !favoritesBody) return;

  const offers = Array.isArray(state.gmOffice.offers) ? state.gmOffice.offers : [];
  const favorites = Array.isArray(state.gmOffice.favorites) ? state.gmOffice.favorites : [];
  if (subtitle) {
    const teamLabel = state.gmOffice.teamCode
      ? `${state.gmOffice.teamCode}${state.gmOffice.teamName ? ` · ${state.gmOffice.teamName}` : ''}`
      : 'Equipo GM';
    subtitle.textContent = `Ofertas enviadas y favoritos guardados para ${teamLabel}.`;
  }
  if (offersStatus) {
    offersStatus.classList.toggle('is-error', Boolean(state.gmOffice.error));
    offersStatus.textContent = state.gmOffice.loading
      ? 'Cargando despachos...'
      : (state.gmOffice.error || `${offers.length} oferta${offers.length === 1 ? '' : 's'} registrada${offers.length === 1 ? '' : 's'}.`);
  }
  if (favoritesStatus) {
    favoritesStatus.textContent = `${favorites.length} favorito${favorites.length === 1 ? '' : 's'} guardado${favorites.length === 1 ? '' : 's'}.`;
  }

  if (state.gmOffice.loading) {
    offersBody.innerHTML = '<tr><td colspan="5">Cargando...</td></tr>';
    favoritesBody.innerHTML = '<tr><td colspan="6">Cargando...</td></tr>';
    return;
  }
  if (!offers.length) {
    offersBody.innerHTML = '<tr><td colspan="5">No hay ofertas enviadas todavía.</td></tr>';
  } else {
    offersBody.innerHTML = offers.map((offer) => {
      const status = String(offer.status || '').trim().toLowerCase();
      const canCancel = status === 'pending';
      return `
        <tr>
          <td>
            <strong>${escapeHtml(offer.player_name || 'Jugador')}</strong>
            <small>${escapeHtml(offer.option_value || '')}</small>
          </td>
          <td>${escapeHtml(freeAgentOfferSummaryText(offer))}</td>
          <td>${gmOfficeStatusBadge(status)}</td>
          <td>${escapeHtml(shortDateTime(offer.updated_at || offer.created_at || ''))}</td>
          <td>
            <button
              type="button"
              class="ghost ${canCancel ? '' : 'is-disabled'}"
              data-gm-offer-cancel="${escapeHtml(offer.id)}"
              ${canCancel ? '' : 'disabled'}
            >Cancelar</button>
          </td>
        </tr>
      `;
    }).join('');
  }
  if (!favorites.length) {
    favoritesBody.innerHTML = '<tr><td colspan="6">No tienes favoritos guardados.</td></tr>';
  } else {
    favoritesBody.innerHTML = favorites.map((agent) => {
      const rights = String(agent.rights_team_code || '').trim().toUpperCase();
      return `
        <tr>
          <td><strong>${escapeHtml(agent.name || '')}</strong></td>
          <td>${escapeHtml(agent.position || '')}</td>
          <td>${escapeHtml(agent.rating || '')}</td>
          <td>${escapeHtml(agent.free_agent_type || 'No restringido')}</td>
          <td>${rights || 'Sin derechos'}</td>
          <td>
            <button type="button" class="ghost" data-gm-favorite-remove="${escapeHtml(agent.id)}">Quitar</button>
          </td>
        </tr>
      `;
    }).join('');
  }

  offersBody.querySelectorAll('[data-gm-offer-cancel]').forEach((button) => {
    button.addEventListener('click', () => {
      void cancelGmOfficeOffer(button.dataset.gmOfferCancel);
    });
  });
  favoritesBody.querySelectorAll('[data-gm-favorite-remove]').forEach((button) => {
    button.addEventListener('click', () => {
      const agent = (state.gmOffice.favorites || []).find((item) => Number(item.id) === Number(button.dataset.gmFavoriteRemove));
      if (agent) void toggleFreeAgentFavorite({ ...agent, is_favorite: true });
    });
  });
}

async function fetchGmOffice() {
  const teamCode = preferredFreeAgentActionTeamCode();
  if (!teamCode) {
    state.gmOffice = { ...state.gmOffice, offers: [], favorites: [], error: 'No tienes un equipo asignado para Despachos.', loading: false };
    renderGmOffice();
    return;
  }
  state.gmOffice.loading = true;
  state.gmOffice.error = '';
  renderGmOffice();
  try {
    const data = await api(`/api/gm-office?team_code=${encodeURIComponent(teamCode)}`);
    state.gmOffice.teamCode = String(data.team_code || teamCode).toUpperCase();
    state.gmOffice.teamName = String(data.team_name || '').trim();
    state.gmOffice.offers = Array.isArray(data.offers) ? data.offers : [];
    state.gmOffice.favorites = Array.isArray(data.favorites) ? data.favorites.map((item) => ({ ...item, is_favorite: true })) : [];
    state.gmOffice.error = '';
  } catch (err) {
    state.gmOffice.offers = [];
    state.gmOffice.favorites = [];
    state.gmOffice.error = err.message || 'No se pudo cargar Despachos.';
  } finally {
    state.gmOffice.loading = false;
    renderGmOffice();
  }
}

async function cancelGmOfficeOffer(offerId) {
  const teamCode = state.gmOffice.teamCode || preferredFreeAgentActionTeamCode();
  if (!offerId || !teamCode) return;
  if (!window.confirm('¿Cancelar esta oferta? Desaparecerá de la lista de solicitudes activas.')) return;
  try {
    await api(`/api/gm-free-agent-offer-requests/${offerId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ team_code: teamCode }),
    });
    await fetchGmOffice();
  } catch (err) {
    alert(`No se pudo cancelar la oferta: ${err.message}`);
  }
}

async function loadGmOffice() {
  state.teamCode = null;
  state.teamData = null;
  setTeamInUrl(null);
  applyTeamTheme('');
  setViewMode('gm-office');
  setPageHeading('Despachos', 'Ofertas enviadas y favoritos');
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  if (!canViewGmOffice()) {
    state.gmOffice = { ...state.gmOffice, offers: [], favorites: [], error: 'Esta sección solo está disponible para GMs, co-admins y admins con equipo asignado.', loading: false };
    renderGmOffice();
    return;
  }
  await fetchGmOffice();
}

function leaguePlayerLogsHtml(player) {
  const logs = Array.isArray(player?.transaction_logs) ? player.transaction_logs : [];
  if (!logs.length) return '<span class="muted-text">Sin movimientos recientes</span>';
  return `
    <ul class="player-log-list">
      ${logs.slice(0, 3).map((log) => `
        <li>
          <span>${escapeHtml(log.summary || 'Movimiento registrado')}</span>
          ${log.created_at ? `<small>${escapeHtml(shortDateTime(log.created_at))}</small>` : ''}
        </li>
      `).join('')}
    </ul>
  `;
}

function shortDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || '');
  return date.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function leaguePlayerTeamHtml(player) {
  const code = String(player?.team_code || '').trim().toUpperCase();
  if (!code) return '<span class="muted-text">Sin equipo</span>';
  return `
    <button type="button" class="tracker-team-btn league-player-team-btn" data-team-code="${escapeHtml(code)}">
      ${draftOrderLogoHtml(code, 'league-player-team-logo')}
      <span>${escapeHtml(code)}</span>
    </button>
  `;
}

function leaguePlayerStatusHtml(player) {
  const status = String(player?.status || 'inactive').trim().toLowerCase();
  const label = String(player?.status_label || 'Agente libre').trim();
  return `<span class="league-player-status league-player-status--${escapeHtml(status)}">${escapeHtml(label)}</span>`;
}

function leaguePlayerContractHtml(player) {
  const summary = String(player?.active_contract_summary || '').trim();
  if (!summary || summary === 'No') return '<span class="muted-text">Sin contrato activo</span>';
  return `<span class="league-player-contract">${escapeHtml(summary)}</span>`;
}

function leaguePlayerProfileSummaryHtml(player) {
  const items = [
    ['DOB', player?.date_of_birth],
    ['Nacionalidad', player?.nationality],
    ['Fuente YOS', player?.yos_source],
    ['Notas', player?.profile_notes],
    ['Movimientos', player?.transaction_notes],
  ].filter(([, value]) => String(value || '').trim());
  if (!items.length) return '<span class="muted-text">Sin datos de perfil</span>';
  return `
    <div class="league-player-profile-summary">
      ${items.map(([label, value]) => `
        <span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</span>
      `).join('')}
    </div>
  `;
}

function renderLeaguePlayers() {
  const tbody = document.querySelector('#leaguePlayersTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const allRows = sortedRows(state.leaguePlayers || [], state.sort.league_players);
  const pagination = paginatedRows(allRows, 'leaguePlayers');
  renderPaginationControls('leaguePlayers', pagination);
  if (!allRows.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="7">No hay jugadores cargados.</td>';
    tbody.appendChild(tr);
    return;
  }
  pagination.rows.forEach((player) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(player.name || '')}</td>
      <td>${leaguePlayerStatusHtml(player)}</td>
      <td>${leaguePlayerTeamHtml(player)}</td>
      <td>${player.experience_years == null ? '' : escapeHtml(player.experience_years)}</td>
      <td>${leaguePlayerProfileSummaryHtml(player)}</td>
      <td>${leaguePlayerContractHtml(player)}</td>
      <td>${leaguePlayerLogsHtml(player)}</td>
    `;
    const teamBtn = tr.querySelector('[data-team-code]');
    if (teamBtn) {
      teamBtn.addEventListener('click', async () => {
        await loadTeam(teamBtn.dataset.teamCode);
      });
    }
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
      <span class="draft-order-via-label">Vía</span>
      ${draftOrderLogoHtml(normalized, 'draft-order-via-logo')}
      <strong class="draft-order-via-code">${escapeHtml(normalized || '-')}</strong>
    </span>
  `;
}

function draftOrderViaCellHtml(row) {
  const owner = String(row?.owner_team_code || '').trim().toUpperCase();
  const original = String(row?.original_team_code || '').trim().toUpperCase();
  if (owner && original && owner === original) return '';
  return draftOrderViaHtml(row?.original_team_code, row?.original_team_name);
}

function draftLedgerStatusLabel(status) {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'ok') return 'Localizada';
  if (normalized === 'missing') return 'Perdida';
  if (normalized === 'duplicate') return 'Duplicada';
  if (normalized === 'conditional') return 'Condicional';
  if (normalized === 'frozen') return 'Bloqueada';
  return normalized || 'Revisar';
}

function draftLedgerPickHtml(pick, showAssetIds = false) {
  if (!pick) return '';
  const status = String(pick.status || 'missing').trim().toLowerCase();
  const holderCodes = Array.isArray(pick.holder_team_codes) ? pick.holder_team_codes : [];
  const holderNames = Array.isArray(pick.holder_team_names) ? pick.holder_team_names : [];
  const holderHtml = holderCodes.length
    ? holderCodes.map((code, index) => {
      const name = holderNames[index] || code;
      return `
        <span class="draft-ledger-holder" title="${escapeHtml(name)}">
          ${draftOrderLogoHtml(code, 'draft-order-via-logo')}
          <strong>${escapeHtml(code)}</strong>
        </span>
      `;
    }).join('<span class="draft-ledger-holder-separator">/</span>')
    : '<span class="draft-ledger-holder draft-ledger-holder--missing">Sin localizar</span>';
  const assetIds = Array.isArray(pick.asset_ids) ? pick.asset_ids.filter((id) => id !== null && id !== undefined) : [];
  const soldToCodes = Array.isArray(pick.sold_to_team_codes) ? pick.sold_to_team_codes.filter(Boolean) : [];
  const metaItems = [];
  if (soldToCodes.length) metaItems.push(`Vendida a ${soldToCodes.join('/')}`);
  if (showAssetIds && assetIds.length) metaItems.push(`Assets ${assetIds.join(', ')}`);
  return `
    <div class="draft-ledger-pick draft-ledger-pick--${escapeHtml(status)}">
      <div class="draft-ledger-pick-main">
        ${holderHtml}
        <span class="draft-ledger-status draft-ledger-status--${escapeHtml(status)}">${escapeHtml(draftLedgerStatusLabel(status))}</span>
      </div>
      <small>${escapeHtml(pick.canonical_id || '')}</small>
      ${metaItems.length ? `<small>${escapeHtml(metaItems.join(' · '))}</small>` : ''}
    </div>
  `;
}

function renderDraftPickLedger(showAssetIds = false) {
  const ledger = state.draftLedger || {};
  const rows = Array.isArray(ledger.rows) ? ledger.rows : [];
  const summary = ledger.summary || {};
  if (!rows.length) return '';
  const issueCount = Number(summary.error || 0) + Number(summary.warning || 0);
  return `
    <article class="draft-pick-ledger">
      <div class="draft-pick-ledger-head">
        <div>
          <h3>Mapa de rondas ${escapeHtml(ledger.draft_year || state.draftOrder?.draft_year || '')}</h3>
          <p>Resumen por equipo original y localización actual de cada ronda.</p>
        </div>
        <div class="draft-pick-ledger-summary">
          <span class="draft-ledger-summary-pill draft-ledger-summary-pill--ok">${escapeHtml(summary.ok || 0)} OK</span>
          <span class="draft-ledger-summary-pill ${Number(summary.error || 0) ? 'draft-ledger-summary-pill--error' : ''}">${escapeHtml(summary.error || 0)} errores</span>
          <span class="draft-ledger-summary-pill ${Number(summary.warning || 0) ? 'draft-ledger-summary-pill--warning' : ''}">${escapeHtml(summary.warning || 0)} avisos</span>
        </div>
      </div>
      ${issueCount ? `
        <div class="draft-pick-ledger-alert">
          Hay ${escapeHtml(issueCount)} incidencia(s) de tracking para revisar.
        </div>
      ` : ''}
      <div class="table-wrap draft-pick-ledger-table-wrap">
        <table class="draft-pick-ledger-table">
          <thead>
            <tr>
              <th>Equipo original</th>
              <th>1ª ronda</th>
              <th>2ª ronda</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${draftOrderTeamHtml(row.team_code, row.team_name)}</td>
                <td>${draftLedgerPickHtml(row.first, showAssetIds)}</td>
                <td>${draftLedgerPickHtml(row.second, showAssetIds)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </article>
  `;
}

function draftYearOptions() {
  const current = currentSeasonStart();
  const years = new Set();
  for (let offset = 1; offset <= 7; offset += 1) {
    years.add(current + offset);
  }
  const active = Number(state.draftOrder?.draft_year || 0);
  if (Number.isInteger(active) && active >= 2000 && active <= 2100) years.add(active);
  return Array.from(years).sort((a, b) => a - b);
}

function renderDraftYearSelect(draftYear) {
  const select = document.getElementById('draftYearSelect');
  if (!select) return;
  const selected = Number(draftYear || state.draftOrder?.draft_year || currentSeasonStart() + 1);
  select.innerHTML = draftYearOptions()
    .map((year) => `<option value="${escapeHtml(year)}"${year === selected ? ' selected' : ''}>${escapeHtml(year)}</option>`)
    .join('');
  select.value = String(selected);
  select.onchange = () => {
    loadDraftOrder(Number(select.value || 0)).catch((err) => alert(`No se pudo cargar el draft: ${err.message}`));
  };
}

function setDraftLiveState(data) {
  state.draftLive = data || null;
  if (data && Array.isArray(data.draft_order)) {
    state.draftOrder = {
      draft_year: data.draft_year || currentSeasonStart() + 1,
      draft_order: data.draft_order || [],
    };
    state.draftLive.loaded_at_ms = Date.now();
  }
}

function draftLiveCurrentPick() {
  const currentId = Number(state.draftLive?.current_pick_id || 0);
  if (!currentId) return null;
  return (state.draftLive?.draft_order || state.draftOrder?.draft_order || [])
    .find((row) => Number(row.id || 0) === currentId) || null;
}

function draftLiveOrderedRows() {
  return (state.draftOrder?.draft_order || state.draftLive?.draft_order || [])
    .slice()
    .sort((a, b) => {
      const roundA = String(a.draft_round || '') === '1st' ? 1 : String(a.draft_round || '') === '2nd' ? 2 : 3;
      const roundB = String(b.draft_round || '') === '1st' ? 1 : String(b.draft_round || '') === '2nd' ? 2 : 3;
      return roundA - roundB || Number(a.pick_number || 0) - Number(b.pick_number || 0) || Number(a.id || 0) - Number(b.id || 0);
    });
}

function draftLiveUpcomingRows() {
  const rows = draftLiveOrderedRows();
  if (!rows.length) return [];
  const currentId = Number(state.draftLive?.current_pick_id || 0);
  let index = currentId ? rows.findIndex((row) => Number(row.id || 0) === currentId) : -1;
  if (index < 0) {
    index = rows.findIndex((row) => !String(row.selection_text || '').trim() && Number(row.skipped || 0) === 0);
  }
  return rows.slice(index >= 0 ? index : 0);
}

function draftLiveUpcomingHtml() {
  const rows = draftLiveUpcomingRows();
  if (!rows.length) return '';
  const currentId = Number(state.draftLive?.current_pick_id || 0);
  return `
    <div class="draft-live-upcoming">
      <div class="draft-live-upcoming-head">
        <span>Orden desde el pick actual</span>
        <strong>${escapeHtml(rows.length)} picks</strong>
      </div>
      <ol class="draft-live-upcoming-list">
        ${rows.map((row) => {
          const isCurrent = currentId && Number(row.id || 0) === currentId;
          const selection = String(row.selection_text || '').trim();
          return `
            <li class="${isCurrent ? 'is-current-draft-pick' : ''}">
              <span class="draft-live-upcoming-number">#${escapeHtml(row.pick_number || '')}</span>
              <span class="draft-live-upcoming-main">
                <strong>${escapeHtml(row.owner_team_code || '')}</strong>
                <small>${escapeHtml(row.draft_round || '')}${selection ? ` · ${selection}` : ''}</small>
              </span>
            </li>
          `;
        }).join('')}
      </ol>
    </div>
  `;
}

function draftLiveRemainingSeconds() {
  const live = state.draftLive || {};
  const duration = Number(live.duration_seconds || 180);
  if (!live.enabled || !live.started_at) return duration;
  const started = Date.parse(live.started_at);
  const serverNow = Date.parse(live.server_now || '');
  if (!Number.isFinite(started) || !Number.isFinite(serverNow)) {
    return Math.max(0, Number(live.remaining_seconds || duration));
  }
  const loadedAt = Number(live.loaded_at_ms || Date.now());
  const elapsedSinceLoad = Math.max(0, Date.now() - loadedAt);
  const estimatedNow = serverNow + elapsedSinceLoad;
  return Math.max(0, Math.ceil((started + duration * 1000 - estimatedNow) / 1000));
}

function formatDraftLiveClock(seconds) {
  const total = Math.max(0, Number(seconds || 0));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

function updateDraftLiveClock() {
  const remaining = draftLiveRemainingSeconds();
  document.querySelectorAll('[data-draft-live-countdown]').forEach((el) => {
    el.textContent = formatDraftLiveClock(remaining);
    el.classList.toggle('is-expired', remaining <= 0);
  });
}

function startDraftLiveTimer() {
  if (draftLiveTimer) {
    clearInterval(draftLiveTimer);
    draftLiveTimer = null;
  }
  if (draftLivePollTimer) {
    clearInterval(draftLivePollTimer);
    draftLivePollTimer = null;
  }
  updateDraftLiveClock();
  if (!state.draftLive?.enabled) return;
  draftLiveTimer = setInterval(updateDraftLiveClock, 1000);
  draftLivePollTimer = setInterval(async () => {
    if (state.ui.viewMode !== 'draft-order') return;
    if (document.querySelector('.draft-live-modal-backdrop')) return;
    try {
      const draftYear = Number(state.draftOrder?.draft_year || currentSeasonStart() + 1);
      const res = await api(`/api/draft-live?year=${encodeURIComponent(draftYear)}`);
      setDraftLiveState(res);
      renderDraftOrder();
    } catch (err) {
      console.warn('Draft live refresh failed', err);
    }
  }, 8000);
}

function canSelectDraftLivePick(row) {
  const live = state.draftLive || {};
  const auth = state.auth || {};
  if (!live.enabled || !auth.authenticated) return false;
  const requestableIds = Array.isArray(live.requestable_pick_ids)
    ? live.requestable_pick_ids.map((id) => Number(id || 0)).filter(Boolean)
    : [];
  const isRequestable = requestableIds.length
    ? requestableIds.includes(Number(row?.id || 0))
    : Number(row?.id || 0) === Number(live.current_pick_id || 0);
  if (!isRequestable) return false;
  if (auth.role === 'admin') return true;
  if (!hasGmLevelRole(auth.role)) return false;
  const owned = String(row?.owner_team_code || '').trim().toUpperCase();
  const teamCodes = Array.isArray(auth.team_codes)
    ? auth.team_codes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)
    : [];
  return Boolean(owned && teamCodes.includes(owned));
}

function draftLiveSelectionHtml(row) {
  const selection = String(row?.selection_text || '').trim();
  const skipped = Number(row?.skipped || 0) !== 0;
  const pendingSelection = String(row?.pending_selection_text || '').trim();
  if (!selection && canSelectDraftLivePick(row)) {
    if (pendingSelection) {
      return `<span class="draft-live-pending draft-live-pending--request">Solicitud enviada</span>`;
    }
    return `<button type="button" class="draft-live-pick-btn draft-live-pick-btn--now" data-draft-live-pick="${escapeHtml(row.id)}">ELIGE AHORA</button>`;
  }
  if (!selection && pendingSelection) return '<span class="draft-live-pending draft-live-pending--request">Solicitud enviada</span>';
  if (!selection) return '<span class="draft-live-pending">Pendiente</span>';
  const cls = skipped ? 'draft-live-selection draft-live-selection--skipped' : 'draft-live-selection';
  return `<span class="${cls}">${escapeHtml(selection)}</span>`;
}

function renderDraftLivePanel() {
  const panel = document.getElementById('draftLivePanel');
  if (!panel) return;
  const live = state.draftLive || {};
  const upcoming = draftLiveUpcomingRows();
  if (!live.enabled && !upcoming.length) {
    panel.classList.add('section-hidden');
    panel.innerHTML = '';
    startDraftLiveTimer();
    return;
  }
  const current = draftLiveCurrentPick() || upcoming[0] || null;
  const currentLabel = current
    ? `Pick #${current.pick_number} · ${current.draft_round} · ${current.owner_team_code}`
    : 'Sin picks configurados';
  panel.classList.remove('section-hidden');
  panel.innerHTML = `
    <div class="draft-live-card">
      <div>
        <span class="draft-live-kicker">${live.enabled ? 'Modo draft activo' : 'Modo draft inactivo'}</span>
        <strong>${escapeHtml(currentLabel)}</strong>
        ${current ? `<span>Siguiente elección: ${escapeHtml(current.owner_team_name || current.owner_team_code || '')}</span>` : '<span>No quedan picks pendientes.</span>'}
      </div>
      ${live.enabled ? `<div class="draft-live-clock" data-draft-live-countdown>${formatDraftLiveClock(draftLiveRemainingSeconds())}</div>` : '<div class="draft-live-clock draft-live-clock--idle">--</div>'}
    </div>
    ${draftLiveUpcomingHtml()}
  `;
  startDraftLiveTimer();
}

function draftLiveChoiceOptionsHtml(selected = '') {
  const normalized = String(selected || '').trim();
  const options = Array.isArray(state.draftLive?.options) ? state.draftLive.options : [];
  return [
    '<option value="">Selecciona jugador</option>',
    ...options.map((option) => `<option value="${escapeHtml(option)}"${option === normalized ? ' selected' : ''}>${escapeHtml(option)}</option>`),
    `<option value="__other__"${normalized === '__other__' ? ' selected' : ''}>Otro</option>`,
  ].join('');
}

function openDraftLivePickModal(row) {
  const existing = document.querySelector('.draft-live-modal-backdrop');
  if (existing) existing.remove();
  const backdrop = document.createElement('div');
  backdrop.className = 'draft-live-modal-backdrop';
  backdrop.innerHTML = `
    <div class="draft-live-modal" role="dialog" aria-modal="true" aria-label="Elegir jugador">
      <div class="draft-live-modal-head">
        <div>
          <span>${escapeHtml(row.draft_round || '')} · Pick #${escapeHtml(row.pick_number || '')}</span>
          <h3>${escapeHtml(row.owner_team_code || '')} elige</h3>
        </div>
        <button type="button" class="danger" data-draft-live-close>Cerrar</button>
      </div>
      <label>
        <span>Jugador</span>
        <select data-draft-live-choice>${draftLiveChoiceOptionsHtml()}</select>
      </label>
      <label class="section-hidden" data-draft-live-custom-wrap>
        <span>Otro</span>
        <input data-draft-live-custom type="text" placeholder="Nombre del jugador">
      </label>
      <div class="draft-live-modal-actions">
        <button type="button" data-draft-live-submit>Confirmar elección</button>
      </div>
    </div>
  `;
  const close = () => backdrop.remove();
  const choice = backdrop.querySelector('[data-draft-live-choice]');
  const customWrap = backdrop.querySelector('[data-draft-live-custom-wrap]');
  const customInput = backdrop.querySelector('[data-draft-live-custom]');
  const syncCustom = () => {
    const isOther = choice.value === '__other__';
    customWrap.classList.toggle('section-hidden', !isOther);
    if (isOther) customInput.focus();
  };
  choice.addEventListener('change', syncCustom);
  backdrop.querySelector('[data-draft-live-close]').addEventListener('click', close);
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) close();
  });
  backdrop.querySelector('[data-draft-live-submit]').addEventListener('click', async () => {
    const optionValue = String(choice.value || '').trim();
    const customText = String(customInput.value || '').trim();
    if (!optionValue || (optionValue === '__other__' && !customText)) {
      alert('Elige un jugador o escribe el nombre en Otro.');
      return;
    }
    try {
      const result = await api(`/api/draft-live/picks/${encodeURIComponent(row.id)}`, {
        method: 'POST',
        body: JSON.stringify({
          option_value: optionValue,
          custom_text: customText,
          advance: true,
        }),
      });
      setDraftLiveState(result);
      close();
      renderDraftOrder();
      alert('Tu elección ha sido enviada a la administración. Será procesada pronto.');
    } catch (err) {
      alert(`No se pudo registrar la elección: ${err.message}`);
    }
  });
  document.body.appendChild(backdrop);
  choice.focus();
  syncCustom();
}

function bindDraftLiveButtons(container) {
  container.querySelectorAll('[data-draft-live-pick]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const pickId = Number(btn.dataset.draftLivePick || 0);
      const row = (state.draftOrder?.draft_order || []).find((item) => Number(item.id || 0) === pickId);
      if (row) openDraftLivePickModal(row);
    });
  });
}

function renderDraftOrderRound(round, label) {
  const rows = (state.draftOrder?.draft_order || [])
    .filter((row) => String(row.draft_round || '').trim() === round)
    .sort((a, b) => Number(a.pick_number || 0) - Number(b.pick_number || 0));
  const body = rows.length
    ? rows.map((row) => `
        <tr class="${Number(row.id || 0) === Number(state.draftLive?.current_pick_id || 0) ? 'is-current-draft-pick' : ''}">
          <td class="draft-order-number">${escapeHtml(row.pick_number || '')}</td>
          <td>${draftOrderTeamHtml(row.owner_team_code, row.owner_team_name)}</td>
          <td>${draftOrderViaCellHtml(row)}</td>
          <td>${draftLiveSelectionHtml(row)}</td>
        </tr>
      `).join('')
    : '<tr><td colspan="4" class="draft-order-empty">No selections configured.</td></tr>';
  return `
    <article class="draft-order-round">
      <h3>${escapeHtml(label)}</h3>
      <div class="table-wrap draft-order-table-wrap">
        <table class="draft-order-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Team</th>
              <th>Via</th>
              <th>Elección</th>
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
  renderDraftYearSelect(draftYear);
  renderDraftLivePanel();
  board.innerHTML = `
    ${renderDraftOrderRound('1st', '1st Round')}
    ${renderDraftOrderRound('2nd', '2nd Round')}
    ${renderDraftPickLedger(false)}
  `;
  bindDraftLiveButtons(board);
}

function ownerOfficeSeasonOptions() {
  const seasons = new Set(availableSeasonViewStarts());
  (state.teamData?.owner_office?.seasons || []).forEach((season) => {
    const parsed = Number(season);
    if (Number.isInteger(parsed) && parsed >= 2000 && parsed <= 2100) seasons.add(parsed);
  });
  return Array.from(seasons).sort((a, b) => a - b);
}

function ownerOfficeDefaultSeason() {
  const configured = Number(state.teamData?.owner_office?.exit_interview_season);
  if (Number.isInteger(configured) && configured >= 2000 && configured <= 2100) return configured;
  return currentSeasonStart();
}

function selectedOwnerOfficeSeason() {
  const options = ownerOfficeSeasonOptions();
  const requested = Number(state.ui.ownerOfficeSeason);
  const fallback = ownerOfficeDefaultSeason();
  const selected = options.includes(requested)
    ? requested
    : (options.includes(fallback) ? fallback : (options[0] || currentSeasonStart()));
  state.ui.ownerOfficeSeason = selected;
  return selected;
}

function ownerOfficeEntryForSeason(season) {
  return state.teamData?.owner_office?.entries?.[String(season)] || {};
}

function ownerOfficeDisplayValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number' && Number.isFinite(value)) return formatMoneyDots(value);
  const parsed = parseOwnerOfficeDisplayAmount(value);
  if (parsed !== null && String(value).trim().match(/^[\s€$0-9.,-]+$/)) return formatMoneyDots(parsed);
  return String(value);
}

function parseOwnerOfficeDisplayAmount(value) {
  const text = String(value || '').trim();
  const compact = text.replace(/[€$]/g, '').replace(/\s+/g, '');
  if (/^-?\d+[.,]\d{1,2}$/.test(compact)) {
    const decimal = Number(compact.replace(',', '.'));
    return Number.isFinite(decimal) ? decimal : null;
  }
  return parseAmountLike(value);
}

function ownerOfficeAgeFromBirthDate(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const birthDate = new Date(`${raw}T00:00:00`);
  if (Number.isNaN(birthDate.getTime())) return '';
  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const birthdayPassed = today.getMonth() > birthDate.getMonth()
    || (today.getMonth() === birthDate.getMonth() && today.getDate() >= birthDate.getDate());
  if (!birthdayPassed) age -= 1;
  return age >= 0 && age < 130 ? String(age) : '';
}

function ownerOfficeProfileAvatarHtml(profile) {
  const name = String(profile?.owner_name || state.teamCode || 'AN').trim();
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('') || 'AN';
  const photoUrl = String(profile?.owner_photo_url || '').trim();
  return `
    <div class="owner-office-avatar" aria-hidden="true">
      <span class="owner-office-avatar-fallback">${escapeHtml(initials)}</span>
      ${photoUrl ? `<img src="${escapeHtml(photoUrl)}" alt="" onload="this.previousElementSibling.style.display='none'" onerror="this.style.display='none';this.previousElementSibling.style.display='grid'">` : ''}
    </div>
  `;
}

function ownerOfficeProfileSummary(profile) {
  const name = String(profile?.owner_name || '').trim() || 'Propietario';
  const age = ownerOfficeAgeFromBirthDate(profile?.owner_birth_date);
  const bio = String(profile?.owner_bio || '').trim();
  return `
    <article class="owner-office-panel owner-office-profile-panel owner-office-profile-panel--readonly">
      <h3>Perfil del propietario</h3>
      <div class="owner-office-profile-card">
        ${ownerOfficeProfileAvatarHtml(profile)}
        <div class="owner-office-profile-copy">
          <div class="owner-office-owner-name">${escapeHtml(name)}</div>
          <div class="owner-office-owner-meta">${age ? `${escapeHtml(age)} años` : 'Edad no configurada'}</div>
          <p>${bio ? escapeHtml(bio) : 'Descripción pendiente.'}</p>
        </div>
      </div>
    </article>
  `;
}

function ownerOfficeMergedRows(defaultRows, savedRows) {
  const savedByKey = new Map((savedRows || []).map((row) => [String(row.key || ''), row]));
  return defaultRows.map((row) => ({
    ...row,
    value: savedByKey.get(row.key)?.value || '',
  }));
}

function ownerOfficeReadonlyCell(value, extraHtml = '') {
  return `
    <div class="owner-office-value">
      <strong>${escapeHtml(ownerOfficeDisplayValue(value))}</strong>
      ${extraHtml}
    </div>
  `;
}

function ownerOfficeBreakdownTable(title, kind, rows) {
  const tableClass = kind === 'income' ? 'owner-office-table--income' : 'owner-office-table--expenses';
  return `
    <article class="owner-office-panel">
      <h3>${escapeHtml(title)}</h3>
      <div class="table-wrap owner-office-table-wrap">
        <table class="owner-office-table ${tableClass}">
          <thead>
            <tr>
              <th>Concepto</th>
              <th>Valor</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr class="${row.type === 'category' ? 'owner-office-category-row' : ''}">
                <td>${escapeHtml(row.label)}</td>
                <td>${row.type === 'category'
                  ? `<span class="owner-office-calculated-value">${escapeHtml(ownerOfficeDisplayValue(row.value))}</span>`
                  : ownerOfficeReadonlyCell(row.value)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </article>
  `;
}

function ownerOfficePerformanceRows(entry, season) {
  const savedRows = Array.isArray(entry?.performance_rows) ? entry.performance_rows : [];
  return Array.from({ length: 5 }, (_, idx) => {
    const fallbackYear = Number(season) - 4 + idx;
    const saved = savedRows[idx] || {};
    return {
      season_year: Number(saved.season_year) || fallbackYear,
      wins: saved.wins ?? '',
      losses: saved.losses ?? '',
      result: saved.result || '',
    };
  });
}

function ownerOfficePerformanceTable(entry, season) {
  const rows = ownerOfficePerformanceRows(entry, season);
  return `
    <article class="owner-office-panel owner-office-performance-panel">
      <h3>Historial deportivo</h3>
      <div class="table-wrap owner-office-table-wrap">
        <table class="owner-office-table owner-office-performance-table">
          <thead>
            <tr>
              <th>Temporada</th>
              <th>Victorias</th>
              <th>Derrotas</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${escapeHtml(seasonLabel(row.season_year))}</td>
                <td>${ownerOfficeReadonlyCell(row.wins)}</td>
                <td>${ownerOfficeReadonlyCell(row.losses)}</td>
                <td>${ownerOfficeReadonlyCell(row.result)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </article>
  `;
}

function ownerOfficeExitInterviewCard(entry, season) {
  if (!freeAgencyModeActive() || Number(season) !== currentSeasonStart()) return '';
  const auth = state.auth || {};
  if (!hasGmLevelRole(auth.role)) return '';
  const interview = entry?.exit_interview || { status: 'available' };
  const status = String(interview.status || 'available').toLowerCase();
  const completed = status === 'completed';
  const awaiting = status === 'awaiting_gm';
  const trustDelta = Number(interview.trust_delta || 0);
  const statusText = completed
    ? `Entrevista completada · impacto confianza ${trustDelta > 0 ? '+1' : '-1'}`
    : (awaiting ? 'Entrevista iniciada · respuesta pendiente' : 'Entrevista de salida disponible');
  const buttonText = completed ? 'Ver entrevista' : (awaiting ? 'Continuar entrevista' : 'Abrir entrevista');
  return `
    <article class="owner-office-panel owner-exit-card">
      <div>
        <h3>Entrevista de salida</h3>
        <p>${escapeHtml(statusText)}</p>
      </div>
      <button type="button" class="owner-exit-open-btn" data-owner-exit-open>${escapeHtml(buttonText)}</button>
    </article>
  `;
}

function ownerExitInterviewSeason() {
  return currentSeasonStart();
}

function ownerExitInterviewForSeason(season = ownerExitInterviewSeason()) {
  return ownerOfficeEntryForSeason(season)?.exit_interview || null;
}

function updateOwnerExitInterviewState(interview) {
  if (!state.teamData?.owner_office || !interview) return;
  const season = Number(interview.season_year || ownerExitInterviewSeason());
  const entries = state.teamData.owner_office.entries || {};
  const key = String(season);
  entries[key] = {
    ...(entries[key] || {}),
    season_year: season,
    exit_interview: interview,
  };
  state.teamData.owner_office.entries = entries;
}

function ownerExitTrustDeltaHtml(interview) {
  if (!interview || String(interview.status || '').toLowerCase() !== 'completed') return '';
  const delta = Number(interview.trust_delta || 0);
  const cls = delta > 0 ? 'owner-exit-delta--positive' : 'owner-exit-delta--negative';
  const label = delta > 0 ? '+1 confianza' : '-1 confianza';
  return `<span class="owner-exit-delta ${cls}">${escapeHtml(label)}</span>`;
}

function ownerExitDialogueHtml(kind, text, profile = {}, interview = {}) {
  const owner = kind === 'owner';
  const speaker = owner ? String(profile?.owner_name || 'Propietario').trim() : String(interview?.gm_name || 'GM').trim();
  return `
    <div class="owner-exit-dialogue owner-exit-dialogue--${owner ? 'owner' : 'gm'}">
      <div class="owner-exit-speaker">
        ${owner ? ownerOfficeProfileAvatarHtml(profile) : '<div class="owner-exit-gm-avatar" aria-hidden="true">GM</div>'}
        <span>${escapeHtml(speaker || (owner ? 'Propietario' : 'GM'))}</span>
      </div>
      <div class="owner-exit-bubble" role="log">
        <p>${escapeHtml(text || '')}</p>
      </div>
    </div>
  `;
}

function ownerExitBackgroundHtml(profile) {
  const backgroundUrl = String(profile?.owner_office_background_url || '').trim();
  if (backgroundUrl) {
    return `<img class="owner-exit-background-image" src="${escapeHtml(backgroundUrl)}" alt="" loading="lazy">`;
  }
  const teamName = String(state.teamData?.team?.name || state.teamData?.owner_office?.team_name || state.teamCode || 'ANBA').trim();
  const logo = teamLogoCandidates(state.teamCode)[0] || '';
  return `
    <div class="owner-exit-background-fallback">
      ${logo ? `<img src="${escapeHtml(logo)}" alt="">` : ''}
      <span>${escapeHtml(teamName)}</span>
    </div>
  `;
}

function renderOwnerExitModal(interview, options = {}) {
  const modal = document.getElementById('ownerExitModal');
  const content = document.getElementById('ownerExitModalContent');
  if (!modal || !content) return;
  const profile = state.teamData?.owner_office?.owner_profile || {};
  const status = String(interview?.status || 'available').toLowerCase();
  const loading = Boolean(options.loading);
  const ownerMessage = String(interview?.owner_message || '');
  const gmResponse = String(interview?.gm_response || '');
  const ownerFinal = String(interview?.owner_final_message || '');
  const ownerConclusion = String(interview?.owner_conclusion_message || '');
  const teamName = String(state.teamData?.team?.name || state.teamData?.owner_office?.team_name || state.teamCode || '').trim();
  const logo = teamLogoCandidates(state.teamCode)[0] || '';
  content.innerHTML = `
    <div class="owner-exit-game">
      <div class="owner-exit-background" aria-hidden="true">
        ${ownerExitBackgroundHtml(profile)}
      </div>
      <div class="owner-exit-scene-shade" aria-hidden="true"></div>
      <div class="owner-exit-scene-hud">
        <div class="owner-exit-scene-team">
          ${logo ? `<img src="${escapeHtml(logo)}" alt="">` : ''}
          <span>${escapeHtml(teamName || 'Despacho del propietario')}</span>
        </div>
        ${status === 'completed' ? ownerExitTrustDeltaHtml(interview) : ''}
      </div>
      <div class="owner-exit-dialogue-panel">
        <div class="owner-exit-chat">
          ${ownerMessage ? ownerExitDialogueHtml('owner', ownerMessage, profile, interview) : ''}
          ${gmResponse ? ownerExitDialogueHtml('gm', gmResponse, profile, interview) : ''}
          ${ownerFinal ? ownerExitDialogueHtml('owner', ownerFinal, profile, interview) : ''}
          ${ownerConclusion ? ownerExitDialogueHtml('owner', ownerConclusion, profile, interview) : ''}
          ${loading ? '<div class="owner-exit-typing">El propietario está escribiendo...</div>' : ''}
          ${!ownerMessage && !loading ? '<p class="owner-exit-empty">La entrevista todavía no ha empezado.</p>' : ''}
        </div>
        ${status === 'awaiting_gm' && !loading ? `
          <form id="ownerExitResponseForm" class="owner-exit-form">
            <label for="ownerExitResponseText">Respuesta del GM</label>
            <textarea id="ownerExitResponseText" rows="4" maxlength="4000" placeholder="Escribe tu respuesta al propietario..."></textarea>
            <div class="owner-exit-actions">
              <button type="submit">Enviar respuesta</button>
            </div>
          </form>
        ` : ''}
      </div>
    </div>
  `;
  modal.classList.add('owner-exit-backdrop');
  modal.classList.remove('section-hidden');
  document.getElementById('ownerExitResponseForm')?.addEventListener('submit', (event) => {
    event.preventDefault();
    void submitOwnerExitResponse();
  });
}

function closeOwnerExitModal() {
  const modal = document.getElementById('ownerExitModal');
  modal?.classList.add('section-hidden');
}

async function openOwnerExitInterview() {
  if (!state.teamCode) return;
  const season = ownerExitInterviewSeason();
  const existing = ownerExitInterviewForSeason(season);
  const status = String(existing?.status || 'available').toLowerCase();
  renderOwnerExitModal(existing || { status: 'available', season_year: season }, { loading: status === 'available' });
  if (status !== 'available' || existing?.owner_message) return;
  try {
    const result = await api(`/api/teams/${encodeURIComponent(state.teamCode)}/owner-exit-interview/start`, {
      method: 'POST',
      body: JSON.stringify({ season_year: season }),
    });
    if (result.owner_office) state.teamData.owner_office = result.owner_office;
    else updateOwnerExitInterviewState(result.interview);
    renderOwnerOffice();
    renderOwnerExitModal(result.interview);
  } catch (err) {
    renderOwnerExitModal(existing || { status: 'available', season_year: season });
    alert(`No se pudo iniciar la entrevista: ${err.message || err}`);
  }
}

async function submitOwnerExitResponse() {
  const textarea = document.getElementById('ownerExitResponseText');
  const response = String(textarea?.value || '').trim();
  if (!response) {
    alert('Escribe una respuesta antes de enviarla.');
    return;
  }
  const season = ownerExitInterviewSeason();
  const current = ownerExitInterviewForSeason(season);
  renderOwnerExitModal({ ...(current || {}), gm_response: response, status: 'awaiting_gm' }, { loading: true });
  try {
    const result = await api(`/api/teams/${encodeURIComponent(state.teamCode)}/owner-exit-interview/reply`, {
      method: 'POST',
      body: JSON.stringify({
        season_year: season,
        gm_response: response,
      }),
    });
    if (result.owner_office) state.teamData.owner_office = result.owner_office;
    else updateOwnerExitInterviewState(result.interview);
    renderOwnerOffice();
    renderOwnerExitModal(result.interview);
  } catch (err) {
    renderOwnerExitModal(current || { status: 'awaiting_gm', season_year: season });
    alert(`No se pudo enviar la respuesta: ${err.message || err}`);
  }
}

async function loadOwnerOfficeForTeam(code) {
  if (!state.teamData) return;
  if (!canViewOwnerOfficeForTeam(code)) {
    state.teamData.owner_office = null;
    return;
  }
  try {
    const res = await api(`/api/teams/${encodeURIComponent(code)}/owner-office`);
    state.teamData.owner_office = res.owner_office || null;
  } catch (err) {
    state.teamData.owner_office = null;
  }
}

function renderOwnerOffice() {
  const section = document.getElementById('ownerOfficeSection');
  const content = document.getElementById('ownerOfficeContent');
  const subtitle = document.getElementById('ownerOfficeSubtitle');
  const select = document.getElementById('ownerOfficeSeasonSelect');
  if (!section || !content || !select) return;
  if (!canViewOwnerOfficeForTeam()) {
    content.innerHTML = '';
    section.classList.add('section-hidden');
    syncTeamTabs();
    return;
  }
  const season = selectedOwnerOfficeSeason();
  const entry = ownerOfficeEntryForSeason(season);
  select.innerHTML = ownerOfficeSeasonOptions()
    .map((year) => `<option value="${year}" ${year === season ? 'selected' : ''}>${seasonLabel(year)}</option>`)
    .join('');
  if (subtitle) subtitle.textContent = `${state.teamCode || ''} · ${seasonLabel(season)}`;
  const balanceRank = entry.balance_rank && entry.balance_rank_total
    ? `<span class="owner-office-rank">#${entry.balance_rank} de ${entry.balance_rank_total}</span>`
    : '';
  const confidenceRank = entry.confidence_rank && entry.confidence_rank_total
    ? `<span class="owner-office-rank">#${entry.confidence_rank} de ${entry.confidence_rank_total}</span>`
    : '';
  const incomeRows = ownerOfficeMergedRows(OWNER_OFFICE_INCOME_ROWS, entry.income_rows);
  const expenseRows = ownerOfficeMergedRows(OWNER_OFFICE_EXPENSE_ROWS, entry.expenses_rows);
  const profile = state.teamData?.owner_office?.owner_profile || {};
  const exitSeason = ownerExitInterviewSeason();
  const exitEntry = ownerOfficeEntryForSeason(exitSeason);
  content.innerHTML = `
    ${ownerOfficeExitInterviewCard(exitEntry, exitSeason)}
    ${ownerOfficeProfileSummary(profile)}
    <div class="owner-office-overview">
      <article class="owner-office-panel">
        <h3>Confianza</h3>
        <table class="owner-office-table owner-office-mini-table">
          <tbody>
            <tr>
              <th>Confianza actual</th>
              <td>${ownerOfficeReadonlyCell(entry.confidence_current, confidenceRank)}</td>
            </tr>
            <tr>
              <th>Cambio ${escapeHtml(seasonLabel(season))}</th>
              <td>${ownerOfficeReadonlyCell(entry.confidence_change)}</td>
            </tr>
            ${entry.new_gm_after_dismissal || entry.gm_midseason_arrival ? `
              <tr>
                <th>Contexto GM</th>
                <td>${ownerOfficeReadonlyCell([
                  entry.new_gm_after_dismissal ? 'Nuevo GM tras destitución' : '',
                  entry.gm_midseason_arrival ? 'Llegó a mediados de la temporada pasada' : '',
                ].filter(Boolean).join(' · '))}</td>
              </tr>
            ` : ''}
          </tbody>
        </table>
      </article>
      <article class="owner-office-panel">
        <h3>Resultados económicos</h3>
        <table class="owner-office-table owner-office-mini-table">
          <tbody>
            <tr>
              <th>Ingresos</th>
              <td>${ownerOfficeReadonlyCell(entry.revenue)}</td>
            </tr>
            <tr>
              <th>Gastos</th>
              <td>${ownerOfficeReadonlyCell(entry.expenses)}</td>
            </tr>
            <tr>
              <th>Balance</th>
              <td>${ownerOfficeReadonlyCell(entry.balance, balanceRank)}</td>
            </tr>
          </tbody>
        </table>
      </article>
      <article class="owner-office-panel">
        <h3>Objetivos</h3>
        <table class="owner-office-table owner-office-mini-table">
          <tbody>
            <tr>
              <th>Objetivo fijado</th>
              <td>${ownerOfficeReadonlyCell(entry.season_goal_set)}</td>
            </tr>
            <tr>
              <th>Objetivo cumplido</th>
              <td>${ownerOfficeReadonlyCell(entry.season_goal_achieved)}</td>
            </tr>
            <tr>
              <th>Evaluación</th>
              <td>${ownerOfficeReadonlyCell(entry.season_goal_evaluation || 'No evaluable')}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </div>
    ${ownerOfficePerformanceTable(entry, season)}
    <div class="owner-office-breakdowns">
      ${ownerOfficeBreakdownTable('Ingresos', 'income', incomeRows)}
      ${ownerOfficeBreakdownTable('Gastos', 'expenses', expenseRows)}
    </div>
  `;
  content.querySelector('[data-owner-exit-open]')?.addEventListener('click', () => {
    void openOwnerExitInterview();
  });
  syncTeamTabs();
}

function renderCards() {
  const wrap = document.getElementById('teamMeta');
  const t = state.teamData.team;
  const s = summaryForBalanceSeason(state.teamData);
  setPageHeading(t.name || 'Team', t.gm || '');
  renderCapStatusPills(s);
  wrap.innerHTML = buildSummaryCardsHtml(s);
  wrap.querySelectorAll('[data-move-log-bucket]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const bucket = normalizeMoveBucket(btn.dataset.moveLogBucket);
      const selectedSeason = selectedSeasonStart();
      const rows = (moveSummaryForSeason(state.teamData, selectedSeason)?.log || []).filter((item) => normalizeMoveBucket(item.bucket) === bucket);
      openMoveLog(`${t.code} · ${seasonLabel(selectedSeason)} · ${moveBucketLabel(bucket)}`, rows);
    });
  });
}

function renderImportantFigures() {
  const table = document.getElementById('importantFiguresTable');
  if (!table) return;
  const selectedYear = selectedSeasonStart();
  const seasons = balanceSeasonYears();
  const seasonData = seasons.map((season) => ({ season, balances: seasonBalances(season) }));
  const rows = [
    { label: 'CAP TOTAL', key: 'cap_total', tooltip: capTotalTooltipText() },
    { label: 'GASTO TOTAL', key: 'gasto_total' },
    { label: 'Cuenta del APRON', key: 'apron_account', tooltip: apronTooltipText() },
    { label: 'Luxury tax', key: 'luxury_tax' },
  ];
  table.innerHTML = `
    <thead>
      <tr>
        <th class="balance-row-heading">Balance</th>
        ${seasons.map((season) => `
          <th class="${season === selectedYear ? 'is-current-year' : ''}">${seasonSlashLabel(season)}</th>
        `).join('')}
      </tr>
    </thead>
    <tbody>
      ${rows.map(({ label, key, tooltip }) => `
        <tr>
          <th class="balance-row-label"${tooltip ? ` title="${escapeHtml(tooltip)}"` : ''}>${label}</th>
          ${seasonData.map(({ season, balances }) => {
            const value = Number(balances[key] || 0);
            const isLiability = key === 'luxury_tax';
            const valueClass = isLiability
              ? (value > 0 ? 'is-negative' : '')
              : (value < 0 ? 'is-negative' : value > 0 ? 'is-positive' : '');
            const breakdownText = balanceBreakdownTooltip(label, value, balanceBreakdownLines(balances, key));
            return `
              <td class="${season === selectedYear ? 'is-current-year' : ''}">
                <span class="balance-value-wrap">
                  <span class="balance-value ${valueClass}"${tooltip ? ` title="${escapeHtml(tooltip)}"` : ''}>${formatMoneyDots(value)}</span>
                  ${balanceInfoControlHtml(breakdownText)}
                </span>
              </td>
            `;
          }).join('')}
        </tr>
      `).join('')}
    </tbody>
  `;
  table.querySelectorAll('[data-balance-info-toggle]').forEach((btn) => setupBalanceInfoButton(btn));

  const appendix = document.getElementById('importantFiguresAppendix');
  if (!appendix) return;
  const salaryCap = capForSeason(selectedYear);
  const luxuryCap = luxuryCapForSeason(selectedYear);
  const firstApron = firstApronForSeason(selectedYear);
  const secondApron = secondApronForSeason(selectedYear);
  const salaryFloor = salaryFloorForSeason(selectedYear);
  const appendixRows = [
    ['Temporada seleccionada', seasonLabel(selectedYear)],
    ['Salary cap', formatDots(salaryCap)],
    ['Salary floor', formatDots(salaryFloor)],
    ['Luxury cap', formatDots(luxuryCap)],
    ['1er Apron', formatDots(firstApron)],
    ['2do Apron', formatDots(secondApron)],
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
  if (view === 'cards') bindGmOptionRequestButtons(cardsWrap);
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
  const currentYear = currentSeasonStart();
  const selected = selectedSeasonStart();
  const optionsHtml = availableSeasonViewStarts()
    .map((season) => {
      const suffix = season === currentYear ? ' (current)' : '';
      return `<option value="${season}">${seasonLabel(season)}${suffix}</option>`;
    })
    .join('');
  document.querySelectorAll('[data-season-view-select]').forEach((select) => {
    select.innerHTML = optionsHtml;
    select.value = String(selected);
  });
}

function renderFiguresSeasonControl() {
  const select = document.getElementById('figuresSeasonSelect');
  if (!select) return;
  const currentYear = currentSeasonStart();
  const selected = selectedFiguresSeasonStart();
  select.innerHTML = availableSeasonViewStarts()
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

function setSeasonViewStart(startYear) {
  state.ui.seasonViewStart = normalizeSeasonViewStart(startYear);
  renderSeasonViewControl();
  if (state.teamCode) setTeamInUrl(state.teamCode);
  if (!state.teamData) return;
  renderCards();
  renderPlayers();
  renderDeadContracts();
  renderExceptions();
  renderAssets();
  renderImportantFigures();
  renderOwnerOffice();
}

function setupSeasonViewControl() {
  renderSeasonViewControl();
  document.querySelectorAll('[data-season-view-select]').forEach((select) => {
    select.addEventListener('change', () => {
      setSeasonViewStart(select.value);
    });
  });
}

function setupOwnerOfficeControls() {
  const select = document.getElementById('ownerOfficeSeasonSelect');
  if (!select) return;
  select.addEventListener('change', () => {
    state.ui.ownerOfficeSeason = Number(select.value);
    renderOwnerOffice();
  });
  document.getElementById('ownerExitCloseBtn')?.addEventListener('click', closeOwnerExitModal);
  document.getElementById('ownerExitModal')?.addEventListener('click', (event) => {
    if (event.target === event.currentTarget) closeOwnerExitModal();
  });
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
    const hasVisibleCapHold = playerHasVisibleCapHold(p);
    if (showPositionGroups) {
      const positionKey = rosterPositionKey(p);
      if (positionKey !== previousPositionKey) {
        appendRosterPositionSeparator(tbody, positionKey, positionCounts[positionKey] || 0, 3 + seasons.length);
        previousPositionKey = positionKey;
      }
    }
    const birdYears = normalizeBirdYears(p.years_left);
    const metaPayload = {
      position: p.position || '',
      rating: p.rating || '',
      contract: p.bird_rights || '',
      years: birdYears,
    };
    const tr = document.createElement('tr');
    if (hasVisibleCapHold) tr.classList.add('roster-row--cap-hold');
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
      <td class="bird-years-cell">${birdYearsCellHtml(birdYears)}</td>
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
      if (hasVisibleCapHold) card.classList.add('player-card--cap-hold');
      card.innerHTML = `
        <div class="player-card-head">
          <div class="player-card-name">${escapeHtml(p.name || '')}</div>
          <div class="player-card-tags">
            ${p.position ? `<span class="pos-pill">${escapeHtml(p.position)}</span>` : ''}
            ${p.rating ? `<span class="meta-pill">${escapeHtml(p.rating)}</span>` : ''}
            ${p.bird_rights ? `<span class="type-pill ${typeClass(p.bird_rights)}">${escapeHtml(p.bird_rights)}</span>` : ''}
            ${birdYears ? birdYearsCellHtml(birdYears) : ''}
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
  bindGmOptionRequestButtons(tbody);
  bindGmOptionRequestButtons(cardsWrap);
  renderRosterTotals(rows, seasons);
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
    renderFrozenDraftPicksGuest(board);
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
        const isStepienRestricted = Number(pick.draft_pick_stepien_restricted || 0) !== 0;
        const isProtected = Number(pick.draft_pick_protected || 0) !== 0;
        const isFrozen = Number(pick.draft_pick_frozen || 0) !== 0;
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
          isFrozen ? '<span class="pick-frozen-tag">Frozen</span>' : '',
          isRestricted ? '<span class="pick-restricted-tag">Restricted</span>' : '',
          isStepienRestricted ? '<span class="pick-stepien-tag">Stepien</span>' : '',
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
        if (isStepienRestricted) card.classList.add('draft-pick-card--stepien');
        if (isProtected) card.classList.add('draft-pick-card--protected');
        if (isFrozen) card.classList.add('draft-pick-card--frozen');
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
  renderFrozenDraftPicksGuest(board);
}

function renderFrozenDraftPicksGuest(container) {
  const rows = (state.teamData?.frozen_draft_picks || [])
    .slice()
    .sort((a, b) => Number(a.draft_year || 0) - Number(b.draft_year || 0));
  if (!rows.length) return;
  const panel = document.createElement('section');
  panel.className = 'frozen-picks-panel';
  panel.innerHTML = `
    <div class="frozen-picks-heading">
      <h3>Rondas congeladas</h3>
      <p>Penalizaciones por finalizar la temporada por encima del 2do apron.</p>
    </div>
    <div class="table-wrap frozen-picks-table-wrap">
      <table class="frozen-picks-table">
        <thead>
          <tr>
            <th>Temporada penalizada</th>
            <th>Ronda congelada</th>
            <th>Motivo</th>
            <th>Notas</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(seasonLabel(Number(row.penalty_season_year || 0)))}</td>
              <td><span class="pick-frozen-tag">Frozen</span> ${escapeHtml(String(row.draft_year || ''))} ${escapeHtml(String(row.draft_round || '1st').toUpperCase())}</td>
              <td>${escapeHtml(row.reason || 'Finalizó por encima del 2do apron')}</td>
              <td>${escapeHtml(row.notes || '')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
  container.appendChild(panel);
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
  const openRosterHoldRow = openRosterSpotDeadContractRow(seasons);
  if (openRosterHoldRow) rows.push(openRosterHoldRow);
  rows.forEach((d) => {
    const tr = document.createElement('tr');
    if (d.is_system_cap_hold) tr.classList.add('dead-contract-system-row');
    const typePill = deadTypePillHtml(d.dead_type);
    const exclusionPills = deadExclusionPillsHtml(d);
    const systemPill = d.is_system_cap_hold
      ? '<span class="dead-system-pill" title="Cap hold calculado automáticamente">Sistema</span>'
      : '';
    tr.innerHTML = `
      <td colspan="3" class="dead-contract-meta-cell">
        <div class="player-cell dead-contract-meta">
          <span class="player-name">${escapeHtml(d.label || '')}</span>
          <span class="player-tags">
            ${typePill}
            ${exclusionPills}
            ${systemPill}
          </span>
        </div>
      </td>
      ${seasons.map((season) => `<td>${salaryCellHtml(d, season, true)}</td>`).join('')}
    `;
    tbody.appendChild(tr);
  });
}

function exceptionModeLabel(mode) {
  switch (String(mode || '')) {
    case 'room':
      return 'Equipo con espacio salarial';
    case 'choice_pending':
      return 'Decisión pendiente';
    case 'over_cap_below_first':
      return 'Over the cap / bajo 1er apron';
    case 'above_first_below_second':
      return 'Entre 1er y 2do apron';
    case 'above_second_apron':
      return 'Por encima del 2do apron';
    default:
      return 'Estimación';
  }
}

function exceptionHardCapLabel(value) {
  if (value === 'first') return 'Hard cap: 1er apron';
  if (value === 'second') return 'Hard cap: 2do apron';
  return 'Sin hard cap automático';
}

function exceptionEstimateItemHtml(item) {
  return `
    <div class="exception-estimate-card">
      <div class="exception-estimate-name">${escapeHtml(item.short_label || item.label || '')}</div>
      <div class="exception-estimate-amount">${formatMoneyDots(item.amount)}</div>
      <div class="exception-estimate-note">${escapeHtml(exceptionHardCapLabel(item.hard_cap))}</div>
    </div>
  `;
}

function renderExceptionEstimate() {
  const panel = document.getElementById('exceptionEstimatePanel');
  if (!panel) return;
  const selected = selectedSeasonStart();
  const estimate = (state.teamData?.exception_estimates || {})[String(selected)];
  if (!estimate) {
    panel.innerHTML = '';
    return;
  }
  const eligible = Array.isArray(estimate.eligible) ? estimate.eligible : [];
  const paths = Array.isArray(estimate.paths) ? estimate.paths : [];
  const official = Array.isArray(estimate.official_exceptions) ? estimate.official_exceptions : [];
  const notes = Array.isArray(estimate.notes) ? estimate.notes : [];
  const choiceHtml = paths.length
    ? `
      <div class="exception-estimate-paths">
        ${paths.map((path) => `
          <div class="exception-estimate-path">
            <div class="exception-estimate-path-title">${escapeHtml(path.label || '')}</div>
            <div class="exception-estimate-path-copy">${escapeHtml(path.description || '')}</div>
            <div class="exception-estimate-cards">
              ${(path.eligible || []).map(exceptionEstimateItemHtml).join('') || '<span class="muted">Sin excepción principal</span>'}
            </div>
          </div>
        `).join('')}
      </div>
    `
    : `
      <div class="exception-estimate-cards">
        ${eligible.map(exceptionEstimateItemHtml).join('') || '<span class="muted">Sin excepciones principales proyectadas.</span>'}
      </div>
    `;
  const officialHtml = estimate.official_generated
    ? `<div class="exception-estimate-official">Oficial generado: ${official.map((item) => escapeHtml(item.label || item.key || '')).join(', ') || 'sí'}</div>`
    : '<div class="exception-estimate-official is-estimate">Estimación pendiente de confirmación admin</div>';
  panel.innerHTML = `
    <details class="exception-estimate-box exception-estimate-box--collapsible">
      <summary class="exception-estimate-head">
        <div>
          <h3>Excepciones estimadas</h3>
          <p>${escapeHtml(seasonLabel(selected))} · ${escapeHtml(exceptionModeLabel(estimate.operating_mode))}</p>
        </div>
        <span class="exception-estimate-badge">${estimate.status === 'choice_pending' ? 'Revisión' : 'Estimación'}</span>
      </summary>
      <div class="exception-estimate-body">
        <div class="exception-estimate-metrics">
          <span>Espacio bruto CAP <strong>${formatMoneyDots(estimate.raw_cap_space)}</strong></span>
          <span>Cuenta apron <strong>${formatMoneyDots(estimate.apron_account)}</strong></span>
        </div>
        ${choiceHtml}
        ${notes.length ? `<ul class="exception-estimate-notes">${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ul>` : ''}
        ${officialHtml}
      </div>
    </details>
  `;
}

function renderExceptions() {
  const tbody = document.querySelector('#exceptionsTable tbody');
  if (!tbody) return;
  renderExceptionEstimate();
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
      <td class="dead-contract-meta-cell exception-meta-cell">
        <div class="player-cell dead-contract-meta exception-meta">
          <span class="player-name">${escapeHtml(item.label || '')}</span>
          ${hasDetail ? '<button type="button" class="exception-detail-icon" data-exception-detail-toggle aria-label="Ver detalles de la excepción">!</button>' : ''}
          <span class="player-tags">
            ${showTypeTag ? `<span class="type-pill exception-type-pill">${escapeHtml(item.exception_type)}</span>` : ''}
          </span>
        </div>
        ${hasDetail ? `<div class="exception-detail-pop">${escapeHtml(item.detail || '')}</div>` : ''}
      </td>
      <td>${item.amount_num != null ? `<div class="salary-chip"><span class="salary-chip-main">${formatDots(item.amount_num)}</span></div>` : (item.amount_text || '')}</td>
      <td class="details-cell exception-details-cell">${hasDetail ? escapeHtml(item.detail || '') : '<span class="muted">-</span>'}</td>
    `;
    if (hasDetail) {
      tr.querySelector('[data-exception-detail-toggle]')?.addEventListener('click', (event) => {
        event.stopPropagation();
        tr.classList.toggle('show-detail');
      });
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
  const data = await api(`/api/teams/${encodeURIComponent(code)}?season=${encodeURIComponent(selectedSeasonStart())}`);
  state.teamCode = code;
  state.teamData = data;
  state.ui.ownerOfficeSeason = null;
  await loadOwnerOfficeForTeam(code);
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
  renderOwnerOffice();
  renderGmTimelineSection();
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

async function loadTracker(season = null) {
  const selected = normalizeTrackerSeason(season ?? state.ui.trackerSeason ?? defaultSeasonViewStart());
  const res = await api(`/api/tracker?season=${encodeURIComponent(selected)}`);
  state.trackerRows = res.tracker || [];
  state.trackerSeasons = res.seasons || [];
  state.ui.trackerSeason = Number(res.season_year || selected);
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
  await loadTrackerEconomy();
  renderImportantFigures();
}

async function loadFigures() {
  state.teamCode = null;
  state.teamData = null;
  setTeamInUrl(null);
  try {
    window.localStorage.removeItem(LAST_TEAM_STORAGE_KEY);
  } catch {
    // ignore localStorage errors
  }
  applyTeamTheme('');
  setViewMode('figures');
  setPageHeading('Cifras', 'Guía de importes derivados del Salary Cap');
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  renderFigures();
}

async function loadFreeAgents() {
  const [res, waiverRes] = await Promise.all([
    api('/api/free-agents'),
    api('/api/waivers').catch(() => ({ waivers: [] })),
  ]);
  state.freeAgents = res.free_agents || [];
  state.waivers = Array.isArray(waiverRes.waivers) ? waiverRes.waivers : [];
  resetPagination('freeAgents');
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
  setPageHeading('Agentes libres', '');
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  renderWaiversPanel();
  renderFreeAgents();
}

function walletSeasonOptions() {
  const seasons = new Set(
    (state.wallet.seasons || [])
      .map((season) => Number(season))
      .filter((season) => Number.isInteger(season) && season >= 2000 && season <= 2100)
  );
  availableSeasonViewStarts().forEach((season) => seasons.add(season));
  return Array.from(seasons).sort((a, b) => a - b);
}

function selectedWalletSeason() {
  const options = walletSeasonOptions();
  const requested = Number(state.wallet.season ?? currentSeasonStart());
  const selected = options.includes(requested) ? requested : (options[0] || currentSeasonStart());
  state.wallet.season = selected;
  return selected;
}

function renderWalletControls() {
  const seasonSelect = document.getElementById('walletSeasonSelect');
  const amountInput = document.getElementById('walletAmountInput');
  if (seasonSelect) {
    const selected = selectedWalletSeason();
    seasonSelect.innerHTML = walletSeasonOptions()
      .map((season) => `<option value="${season}" ${season === selected ? 'selected' : ''}>${seasonLabel(season)}</option>`)
      .join('');
  }
  if (amountInput && document.activeElement !== amountInput) {
    amountInput.value = state.wallet.amountText || '';
  }
}

const WALLET_CLIENTS_PAGE_SIZE = 20;

function renderWalletTabs() {
  const activeTab = state.wallet.activeTab === 'tools' ? 'tools' : 'clients';
  state.wallet.activeTab = activeTab;
  document.querySelectorAll('[data-wallet-tab]').forEach((button) => {
    const isActive = button.dataset.walletTab === activeTab;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  document.getElementById('walletClientsPanel')?.classList.toggle('section-hidden', activeTab !== 'clients');
  document.getElementById('walletToolsPanel')?.classList.toggle('section-hidden', activeTab !== 'tools');
}

function selectedWalletAppealClient() {
  const clients = Array.isArray(state.wallet.clients) ? state.wallet.clients : [];
  const selectedId = Number(state.wallet.appealSelectedFreeAgentId);
  if (Number.isFinite(selectedId) && selectedId > 0) {
    const selected = clients.find((client) => Number(client.id) === selectedId);
    if (selected) return selected;
  }
  const fallback = clients[0] || null;
  state.wallet.appealSelectedFreeAgentId = fallback ? Number(fallback.id) : null;
  return fallback;
}

function renderWalletAppealPlayerSelect() {
  const select = document.getElementById('walletAppealPlayerSelect');
  if (!select) return;
  const clients = sortedWalletClients();
  const selected = selectedWalletAppealClient();
  select.innerHTML = clients.length
    ? clients.map((client) => {
      const id = Number(client.id);
      return `<option value="${id}" ${selected && Number(selected.id) === id ? 'selected' : ''}>${escapeHtml(client.name || 'Jugador')}</option>`;
    }).join('')
    : '<option value="">Sin jugadores</option>';
  select.disabled = !clients.length;
}

function walletClientTeamCodes(client, key) {
  const items = Array.isArray(client?.[key]) ? client[key] : [];
  return new Set(items.map((item) => {
    if (typeof item === 'string') return item.trim().toUpperCase();
    return String(item.team_code || '').trim().toUpperCase();
  }).filter(Boolean));
}

function walletMatchRowsByTeam() {
  const amount = parseAmountLike(state.wallet.amountText);
  const rows = Array.isArray(state.wallet.rows) ? state.wallet.rows : [];
  if (!amount || amount <= 0 || state.wallet.loading || state.wallet.error) return new Map();
  return new Map(
    rows
      .map((row) => [String(row?.team_code || '').trim().toUpperCase(), row])
      .filter(([code]) => Boolean(code))
  );
}

function walletRenounceInfoHtml(matchRow) {
  const rights = Array.isArray(matchRow?.rights_to_renounce) ? matchRow.rights_to_renounce : [];
  const needsReview = Boolean(matchRow?.needs_renounce_review);
  if (!rights.length && !needsReview) return '';
  const content = rights.length
    ? rights.map((right) => {
      const name = escapeHtml(right.player_name || 'Jugador');
      const hold = escapeHtml(right.hold_label || 'Cap hold');
      return `<li><strong>${name}</strong><span>${hold}</span></li>`;
    }).join('')
    : '<li><strong>Revisión necesaria</strong><span>Puede requerir renuncias o limpieza de derechos.</span></li>';
  return `
    <span class="wallet-team-info" tabindex="0" aria-label="Renuncias posibles">
      i
      <span class="wallet-team-info-popover">
        <strong>Para llegar a este importe</strong>
        <ul>${content}</ul>
      </span>
    </span>
  `;
}

async function toggleWalletRuleoutTeam(teamCode) {
  const selectedClient = selectedWalletAppealClient();
  const code = String(teamCode || '').trim().toUpperCase();
  const clientId = Number(selectedClient?.id || 0);
  if (!clientId || !code) return;
  const ruledOutTeams = walletClientTeamCodes(selectedClient, 'ruled_out_teams');
  const nextRuledOut = !ruledOutTeams.has(code);
  try {
    const data = await api(`/api/cartera/clients/${clientId}/ruleout`, {
      method: 'POST',
      body: JSON.stringify({ team_code: code, ruled_out: nextRuledOut }),
    });
    selectedClient.ruled_out_teams = Array.isArray(data.ruled_out_teams) ? data.ruled_out_teams : [];
    renderWalletAppeal();
  } catch (err) {
    state.wallet.appealError = err.message || 'No se pudo actualizar el descarte del equipo.';
    renderWalletAppeal();
  }
}

function renderWalletAppeal() {
  renderWalletAppealPlayerSelect();
  const status = document.getElementById('walletAppealStatus');
  const table = document.getElementById('walletAppealTable');
  const thead = table?.querySelector('thead');
  const tbody = table?.querySelector('tbody');
  if (!status || !thead || !tbody) return;

  const columns = Array.isArray(state.wallet.appealColumns) ? state.wallet.appealColumns : [];
  const rankings = Array.isArray(state.wallet.appealRankings) ? state.wallet.appealRankings : [];
  const rows = Array.isArray(state.wallet.appealRows) ? state.wallet.appealRows : [];
  const selectedClient = selectedWalletAppealClient();
  const offerTeams = walletClientTeamCodes(selectedClient, 'offers');
  const interestTeams = walletClientTeamCodes(selectedClient, 'interests');
  const ruledOutTeams = walletClientTeamCodes(selectedClient, 'ruled_out_teams');
  const matchRowsByTeam = walletMatchRowsByTeam();
  const amount = parseAmountLike(state.wallet.amountText);
  const affordabilityFilterActive = Boolean(amount && amount > 0 && !state.wallet.loading && !state.wallet.error);

  status.classList.toggle('is-error', Boolean(state.wallet.appealError));
  if (state.wallet.appealLoading) {
    status.textContent = 'Cargando tablas de atractivo...';
  } else if (state.wallet.appealError) {
    status.textContent = state.wallet.appealError;
  } else if (!rankings.length && !rows.length) {
    status.textContent = 'Todavía no hay tabla de atractivo cargada por la administración.';
  } else if (selectedClient) {
    const filterText = affordabilityFilterActive
      ? ` · ${matchRowsByTeam.size} llegan a ${formatMoneyDots(amount)}`
      : '';
    status.textContent = `${rows.length || rankings.length} equipos · ${offerTeams.size} con oferta · ${interestTeams.size} con interés · ${ruledOutTeams.size} descartados${filterText} para ${selectedClient.name || 'este jugador'}.`;
  } else {
    status.textContent = 'Selecciona un jugador representado para ver señales de mercado.';
  }

  const groupedColumns = [];
  columns.forEach((column) => {
    const group = String(column.group || column.label || '').trim();
    const last = groupedColumns[groupedColumns.length - 1];
    if (last && last.group === group) {
      last.columns.push(column);
    } else {
      groupedColumns.push({ group, columns: [column] });
    }
  });
  thead.innerHTML = `
    <tr>
      <th rowspan="2">Rank</th>
      ${groupedColumns.map((group) => `<th colspan="${group.columns.length}" class="wallet-appeal-group-head">${escapeHtml(group.group || 'Ranking')}</th>`).join('')}
    </tr>
    <tr>
      ${columns.map((column) => `<th>${escapeHtml(column.sub_label || column.label || column.key)}</th>`).join('')}
    </tr>
  `;
  if (state.wallet.appealLoading) {
    tbody.innerHTML = `<tr><td colspan="${columns.length + 1}">Cargando...</td></tr>`;
    return;
  }
  if (!rankings.length) {
    tbody.innerHTML = `<tr><td colspan="${columns.length + 1}">Sin datos de atractivo.</td></tr>`;
    return;
  }
  tbody.innerHTML = rankings.map((row) => {
    const rank = Number(row.rank || 0);
    return `
      <tr class="wallet-appeal-row wallet-appeal-rank-row wallet-appeal-rank-row--${rank <= 3 ? 'elite' : rank <= 9 ? 'strong' : rank <= 16 ? 'mid' : rank <= 22 ? 'low' : rank <= 25 ? 'risk' : 'bottom'}">
        <td class="wallet-appeal-rank">${rank || ''}</td>
        ${columns.map((column) => {
          const cell = row[column.key] || {};
          const code = String(cell.team_code || '').trim().toUpperCase();
          const hasOffer = offerTeams.has(code);
          const hasInterest = !hasOffer && interestTeams.has(code);
          const isRuledOut = ruledOutTeams.has(code);
          const matchRow = code ? matchRowsByTeam.get(code) : null;
          const isUnreachable = Boolean(code && affordabilityFilterActive && !matchRow);
          const classes = [
            hasOffer ? 'wallet-appeal-cell--offer' : '',
            hasInterest ? 'wallet-appeal-cell--interest' : '',
            isUnreachable ? 'wallet-appeal-cell--unreachable' : '',
            isRuledOut ? 'wallet-appeal-cell--ruled-out' : '',
          ].filter(Boolean).join(' ');
          const titleParts = [
            cell.team_name || code,
            isUnreachable ? 'No llega al importe filtrado' : '',
            isRuledOut ? 'Descartado por el agente' : '',
          ].filter(Boolean);
          return `
            <td class="${classes}" title="${escapeHtml(titleParts.join(' · '))}">
              ${code ? `
                <span class="wallet-appeal-team">
                  ${draftOrderLogoHtml(code, 'wallet-rights-logo')}
                  <strong>${escapeHtml(code)}</strong>
                  ${matchRow ? walletRenounceInfoHtml(matchRow) : ''}
                  <button
                    type="button"
                    class="wallet-ruleout-btn ${isRuledOut ? 'is-active' : ''}"
                    data-wallet-ruleout-team="${escapeHtml(code)}"
                    title="${isRuledOut ? 'Reactivar equipo para este jugador' : 'Descartar equipo para este jugador'}"
                    aria-label="${isRuledOut ? 'Reactivar equipo para este jugador' : 'Descartar equipo para este jugador'}"
                  >${isRuledOut ? '↺' : '×'}</button>
                </span>
              ` : '-'}
            </td>
          `;
        }).join('')}
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('[data-wallet-ruleout-team]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      void toggleWalletRuleoutTeam(button.dataset.walletRuleoutTeam);
    });
  });
}

function walletClientRightsLabel(client) {
  const rightsTeam = String(client?.rights_team_code || '').trim().toUpperCase();
  if (!rightsTeam) return 'Sin derechos retenidos';
  return `Derechos ${rightsTeam}`;
}

function walletClientInterestDetailsHtml(client) {
  const interests = Array.isArray(client?.interests) ? client.interests : [];
  if (!interests.length) {
    return '<div class="wallet-interest-empty">Sin interés registrado todavía.</div>';
  }
  return `
    <div class="wallet-interest-list">
      ${interests.map((interest) => {
        const teamCode = String(interest.team_code || '').trim().toUpperCase();
        const teamName = String(interest.team_name || teamCode).trim();
        const updated = interest.updated_at ? new Date(interest.updated_at).toLocaleString() : '';
        const economic = String(interest.economic_offer || '').trim();
        const role = String(interest.role_offer || '').trim();
        const comments = String(interest.comments || '').trim();
        return `
          <article class="wallet-interest-card">
            <div class="wallet-interest-card-head">
              <span>${draftOrderLogoHtml(teamCode, 'wallet-interest-team-logo')}</span>
              <strong>${escapeHtml(teamCode)}</strong>
              <small>${escapeHtml(teamName)}</small>
            </div>
            <dl>
              ${economic ? `<dt>Oferta económica</dt><dd>${escapeHtml(economic)}</dd>` : ''}
              ${role ? `<dt>Rol</dt><dd>${escapeHtml(role)}</dd>` : ''}
              ${comments ? `<dt>Comentarios</dt><dd>${escapeHtml(comments)}</dd>` : ''}
            </dl>
            ${updated ? `<div class="wallet-interest-updated">${escapeHtml(updated)}</div>` : ''}
          </article>
        `;
      }).join('')}
    </div>
  `;
}

function renderWalletClientsPagination(totalPages) {
  const page = Math.min(Math.max(1, Number(state.wallet.clientsPage || 1)), Math.max(1, totalPages));
  state.wallet.clientsPage = page;
  const html = totalPages <= 1
    ? ''
    : `
      <button type="button" data-wallet-clients-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>Anterior</button>
      <span>Página ${page} de ${totalPages}</span>
      <button type="button" data-wallet-clients-page="${page + 1}" ${page >= totalPages ? 'disabled' : ''}>Siguiente</button>
    `;
  ['walletClientsPaginationTop', 'walletClientsPaginationBottom'].forEach((id) => {
    const container = document.getElementById(id);
    if (!container) return;
    container.innerHTML = html;
    container.querySelectorAll('[data-wallet-clients-page]').forEach((button) => {
      button.addEventListener('click', () => {
        const nextPage = Number(button.dataset.walletClientsPage);
        if (!Number.isFinite(nextPage)) return;
        state.wallet.clientsPage = Math.min(Math.max(1, nextPage), totalPages);
        renderWalletClients();
      });
    });
  });
}

function sortedWalletClients() {
  const clients = Array.isArray(state.wallet.clients) ? [...state.wallet.clients] : [];
  const sort = state.wallet.clientsSort || { key: 'interest_count', dir: 'desc' };
  const direction = sort.dir === 'asc' ? 1 : -1;
  return clients.sort((a, b) => {
    if (['interest_count', 'favorite_count'].includes(sort.key)) {
      const diff = Number(a?.[sort.key] || 0) - Number(b?.[sort.key] || 0);
      if (diff) return diff * direction;
    }
    return String(a?.name || '').localeCompare(String(b?.name || ''), 'es', { sensitivity: 'base' });
  });
}

function walletFavoriteDetailsHtml(client) {
  const favorites = Array.isArray(client?.favorites) ? client.favorites : [];
  if (!favorites.length) return '<div class="wallet-interest-empty">Ningún equipo lo tiene en favoritos.</div>';
  return `
    <div class="wallet-favorite-list">
      ${favorites.map((item) => {
        const code = String(item.team_code || '').trim().toUpperCase();
        return `
          <span class="wallet-favorite-team" title="${escapeHtml(item.team_name || code)}">
            ${draftOrderLogoHtml(code, 'wallet-interest-team-logo')}
            <strong>${escapeHtml(code)}</strong>
          </span>
        `;
      }).join('')}
    </div>
  `;
}

function renderWalletClients() {
  const tbody = document.querySelector('#walletClientsTable tbody');
  const status = document.getElementById('walletClientsStatus');
  const agentLabel = document.getElementById('walletAgentLabel');
  if (!tbody || !status || !agentLabel) return;

  const clients = sortedWalletClients();
  const agentName = String(state.wallet.agentName || '').trim();
  agentLabel.textContent = agentName ? `Agente asignado: ${agentName}` : 'Sin agente asignado';
  status.classList.toggle('is-error', Boolean(state.wallet.clientsError || state.wallet.missingAgent));

  if (state.wallet.clientsLoading) {
    status.textContent = 'Cargando clientes...';
  } else if (state.wallet.clientsError) {
    status.textContent = state.wallet.clientsError;
  } else if (state.wallet.missingAgent) {
    status.textContent = 'Tu usuario co-admin no tiene agente asignado todavía. Un admin puede asignarlo en Users.';
  } else {
    status.textContent = `${clients.length} cliente${clients.length === 1 ? '' : 's'} en cartera.`;
  }

  const totalPages = Math.max(1, Math.ceil(clients.length / WALLET_CLIENTS_PAGE_SIZE));
  const page = Math.min(Math.max(1, Number(state.wallet.clientsPage || 1)), totalPages);
  state.wallet.clientsPage = page;
  const start = (page - 1) * WALLET_CLIENTS_PAGE_SIZE;
  const visibleClients = clients.slice(start, start + WALLET_CLIENTS_PAGE_SIZE);

  if (state.wallet.clientsLoading) {
    tbody.innerHTML = '<tr><td colspan="4">Cargando...</td></tr>';
    renderWalletClientsPagination(totalPages);
    return;
  }
  if (!visibleClients.length) {
    tbody.innerHTML = '<tr><td colspan="4">No hay clientes para mostrar.</td></tr>';
    renderWalletClientsPagination(totalPages);
    return;
  }

  tbody.innerHTML = visibleClients.map((client) => {
    const clientId = Number(client.id);
    const interestCount = Number(client.interest_count || 0);
    const favoriteCount = Number(client.favorite_count || 0);
    const expanded = state.wallet.expandedClientIds.has(clientId);
    const favoritesExpanded = state.wallet.expandedFavoriteClientIds.has(clientId);
    const rightsTeam = String(client.rights_team_code || '').trim().toUpperCase();
    const interestControl = interestCount > 0
      ? `<button type="button" class="wallet-interest-count" data-wallet-client-toggle="${clientId}" aria-expanded="${expanded ? 'true' : 'false'}">${interestCount}</button>`
      : '<span class="wallet-interest-zero">0</span>';
    const favoriteControl = favoriteCount > 0
      ? `<button type="button" class="wallet-interest-count wallet-favorite-count" data-wallet-client-favorites-toggle="${clientId}" aria-expanded="${favoritesExpanded ? 'true' : 'false'}" title="${escapeHtml((client.favorites || []).map((item) => item.team_code).filter(Boolean).join(', '))}">${favoriteCount}</button>`
      : '<span class="wallet-interest-zero">0</span>';
    return `
      <tr class="wallet-client-row">
        <td><strong>${escapeHtml(client.name || 'Jugador')}</strong></td>
        <td>
          ${rightsTeam ? `<span class="wallet-rights-owner">${draftOrderLogoHtml(rightsTeam, 'wallet-rights-logo')} ${escapeHtml(walletClientRightsLabel(client))}</span>` : escapeHtml(walletClientRightsLabel(client))}
        </td>
        <td>${interestControl}</td>
        <td>${favoriteControl}</td>
      </tr>
      ${expanded ? `<tr class="wallet-client-detail-row"><td colspan="4">${walletClientInterestDetailsHtml(client)}</td></tr>` : ''}
      ${favoritesExpanded ? `<tr class="wallet-client-detail-row"><td colspan="4">${walletFavoriteDetailsHtml(client)}</td></tr>` : ''}
    `;
  }).join('');

  tbody.querySelectorAll('[data-wallet-client-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const clientId = Number(button.dataset.walletClientToggle);
      if (!Number.isFinite(clientId)) return;
      if (state.wallet.expandedClientIds.has(clientId)) {
        state.wallet.expandedClientIds.delete(clientId);
      } else {
        state.wallet.expandedClientIds.add(clientId);
      }
      renderWalletClients();
    });
  });
  tbody.querySelectorAll('[data-wallet-client-favorites-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const clientId = Number(button.dataset.walletClientFavoritesToggle);
      if (!Number.isFinite(clientId)) return;
      if (state.wallet.expandedFavoriteClientIds.has(clientId)) {
        state.wallet.expandedFavoriteClientIds.delete(clientId);
      } else {
        state.wallet.expandedFavoriteClientIds.add(clientId);
      }
      renderWalletClients();
    });
  });
  document.querySelectorAll('[data-wallet-sort]').forEach((button) => {
    const sort = state.wallet.clientsSort || {};
    button.classList.toggle('is-active', sort.key === button.dataset.walletSort);
    button.textContent = `${button.dataset.walletSort === 'favorite_count' ? 'Favoritos' : 'Interés'}${sort.key === button.dataset.walletSort ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}`;
  });
  renderWalletClientsPagination(totalPages);
}

async function fetchWalletClients() {
  state.wallet.clientsLoading = true;
  state.wallet.clientsError = '';
  renderWalletClients();
  try {
    const data = await api('/api/cartera/clients');
    state.wallet.clients = Array.isArray(data.clients) ? data.clients : [];
    state.wallet.agentName = String(data.agent_name || '').trim();
    state.wallet.missingAgent = Boolean(data.missing_agent);
    state.wallet.clientsPage = 1;
    state.wallet.clientsError = '';
  } catch (err) {
    state.wallet.clients = [];
    state.wallet.clientsError = err.message || 'No se pudo cargar la lista de clientes.';
  } finally {
    state.wallet.clientsLoading = false;
    renderWalletClients();
    renderWalletAppeal();
  }
}

async function fetchWalletAppeal() {
  state.wallet.appealLoading = true;
  state.wallet.appealError = '';
  renderWalletAppeal();
  try {
    const data = await api('/api/cartera/appeal');
    state.wallet.appealRows = Array.isArray(data.rows) ? data.rows : [];
    state.wallet.appealColumns = Array.isArray(data.columns) ? data.columns : [];
    state.wallet.appealRankings = Array.isArray(data.rankings) ? data.rankings : [];
    state.wallet.appealError = '';
  } catch (err) {
    state.wallet.appealRows = [];
    state.wallet.appealColumns = [];
    state.wallet.appealRankings = [];
    state.wallet.appealError = err.message || 'No se pudo cargar la tabla de atractivo.';
  } finally {
    state.wallet.appealLoading = false;
    renderWalletAppeal();
  }
}

function walletPathHtml(path) {
  const type = String(path?.type || '').trim();
  const label = escapeHtml(path?.label || 'Ruta');
  const source = escapeHtml(path?.source || '');
  const details = escapeHtml(path?.details || '');
  const amount = formatMoneyDots(path?.amount || 0);
  return `
    <li class="wallet-path wallet-path--${type || 'default'}">
      <div>
        <strong>${label}</strong>
        ${source ? `<span>${source}</span>` : ''}
        ${details ? `<small>${details}</small>` : ''}
      </div>
      <b>${amount}</b>
    </li>
  `;
}

function walletRightsHtml(row) {
  const rights = Array.isArray(row?.rights_to_renounce) ? row.rights_to_renounce : [];
  if (!rights.length) return '';
  return `
    <details class="wallet-rights" open>
      <summary>
        Derechos a revisar/renunciar
        <span>${formatMoneyDots(row.cap_hold_total || 0)}</span>
      </summary>
      <ul>
        ${rights.map((right) => `
          <li>
            <span>
              <strong>${escapeHtml(right.player_name || 'Jugador')}</strong>
              <small>${escapeHtml(right.hold_label || 'Cap hold')}</small>
            </span>
            <b>${formatMoneyDots(right.amount || 0)}</b>
          </li>
        `).join('')}
      </ul>
    </details>
  `;
}

function walletResultHtml(row) {
  const code = String(row?.team_code || '').toUpperCase();
  const name = row?.team_name || code;
  const paths = Array.isArray(row?.paths) ? row.paths : [];
  const renounceNotice = row?.needs_renounce_review
    ? '<div class="wallet-renounce-alert">Podría necesitar limpiar/renunciar derechos antes de ejecutar esta vía.</div>'
    : '';
  return `
    <article class="wallet-result-card">
      <div class="wallet-result-head">
        <button type="button" class="wallet-team-btn" data-team-code="${escapeHtml(code)}">
          ${draftOrderLogoHtml(code, 'wallet-team-logo')}
          <span>
            <strong>${escapeHtml(code)}</strong>
            <small>${escapeHtml(name)}</small>
          </span>
        </button>
        <span class="wallet-path-count">${paths.length} vía${paths.length === 1 ? '' : 's'}</span>
      </div>
      <div class="wallet-metrics">
        <span><small>CAP total</small><strong>${formatMoneyDots(row.cap_total || 0)}</strong></span>
        <span><small>Espacio CAP</small><strong class="${Number(row.cap_space || 0) >= 0 ? 'positive' : 'negative'}">${formatMoneyDots(row.cap_space || 0)}</strong></span>
        <span><small>Cuenta APRON</small><strong>${formatMoneyDots(row.apron_account || 0)}</strong></span>
      </div>
      <ul class="wallet-paths">${paths.map(walletPathHtml).join('')}</ul>
      ${renounceNotice}
      ${walletRightsHtml(row)}
    </article>
  `;
}

function renderWallet() {
  renderWalletTabs();
  renderWalletControls();
  renderWalletAppeal();
  const status = document.getElementById('walletStatus');
  if (!status) return;

  const amount = parseAmountLike(state.wallet.amountText);
  const rows = Array.isArray(state.wallet.rows) ? state.wallet.rows : [];
  status.classList.toggle('is-error', Boolean(state.wallet.error));
  if (state.wallet.loading) {
    status.textContent = 'Calculando filtro de importe...';
  } else if (state.wallet.error) {
    status.textContent = state.wallet.error;
  } else if (!amount || amount <= 0) {
    status.textContent = 'Introduce un importe para sombrear en la tabla los equipos que no llegan a esa cifra.';
  } else {
    status.textContent = `${rows.length} equipo${rows.length === 1 ? '' : 's'} pueden llegar a ${formatMoneyDots(amount)} en ${seasonLabel(selectedWalletSeason())}. El resto aparece atenuado.`;
  }
}

async function fetchWalletResults() {
  const amountInput = document.getElementById('walletAmountInput');
  if (amountInput) state.wallet.amountText = String(amountInput.value || '').trim();
  const amount = parseAmountLike(state.wallet.amountText);
  if (!amount || amount <= 0) {
    state.wallet.rows = [];
    state.wallet.error = 'Introduce un importe válido mayor que cero.';
    renderWallet();
    return;
  }
  state.wallet.loading = true;
  state.wallet.error = '';
  renderWallet();
  try {
    const season = selectedWalletSeason();
    const data = await api(`/api/cartera?amount=${encodeURIComponent(state.wallet.amountText)}&season=${encodeURIComponent(season)}`);
    state.wallet.rows = Array.isArray(data.rows) ? data.rows : [];
    state.wallet.seasons = Array.isArray(data.seasons) ? data.seasons : [];
    state.wallet.season = Number(data.season_year || season);
    state.wallet.error = '';
  } catch (err) {
    state.wallet.rows = [];
    state.wallet.error = err.message || 'No se pudo cargar Cartera.';
  } finally {
    state.wallet.loading = false;
    renderWallet();
  }
}

async function loadWallet() {
  state.teamCode = null;
  state.teamData = null;
  setTeamInUrl(null);
  try {
    window.localStorage.removeItem(LAST_TEAM_STORAGE_KEY);
  } catch {
    // ignore localStorage errors
  }
  applyTeamTheme('');
  setViewMode('wallet');
  setPageHeading('Cartera', 'Espacio salarial y excepciones disponibles');
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  if (!canViewWallet()) {
    state.wallet.rows = [];
    state.wallet.error = 'Esta herramienta solo está disponible para admins y co-admins.';
    state.wallet.clients = [];
    state.wallet.clientsError = '';
    state.wallet.missingAgent = false;
    state.wallet.agentName = '';
    renderWallet();
    renderWalletClients();
    return;
  }
  if (!state.wallet.season) state.wallet.season = currentSeasonStart();
  state.wallet.error = '';
  renderWallet();
  await Promise.all([fetchWalletClients(), fetchWalletAppeal()]);
}

async function fetchLeaguePlayersFallback() {
  if (!state.teams.length) {
    const teamsRes = await api('/api/teams');
    state.teams = teamsRes.teams || [];
  }
  const loaded = await Promise.all((state.teams || []).map(async (team) => {
    const code = String(team.code || '').trim().toUpperCase();
    if (!code) return [];
    const data = await api(`/api/teams/${encodeURIComponent(code)}`);
    return (data.players || []).map((player) => ({
      ...player,
      profile_id: player.profile_id || player.id,
      player_id: player.id,
      status: 'active',
      status_label: 'En roster',
      team_code: data.team?.code || code,
      team_name: data.team?.name || team.name || code,
      active_contract: true,
      active_contract_summary: [
        data.team?.code || code,
        player.position,
        player.bird_rights,
        player.years_left ? `${player.years_left} birds` : '',
      ].filter(Boolean).join(' · ') || 'Sí',
      transaction_logs: Array.isArray(player.transaction_logs) ? player.transaction_logs : [],
    }));
  }));
  return loaded.flat().sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'es'));
}

async function loadLeaguePlayers() {
  let players = [];
  try {
    const res = await api('/api/players');
    players = Array.isArray(res.players) ? res.players : [];
  } catch (err) {
    console.warn('API /api/players not available, using team roster fallback.', err);
  }
  if (!players.length) {
    players = await fetchLeaguePlayersFallback();
  }
  state.leaguePlayers = players;
  resetPagination('leaguePlayers');
  state.teamCode = null;
  state.teamData = null;
  setTeamInUrl(null);
  try {
    window.localStorage.removeItem(LAST_TEAM_STORAGE_KEY);
  } catch {
    // ignore localStorage errors
  }
  applyTeamTheme('');
  setViewMode('league-players');
  setPageHeading('Jugadores', 'Perfiles de jugadores de la liga');
  renderCapStatusPills({});
  renderTeamStrip();
  renderMobileTeamGrid();
  renderLeaguePlayers();
  updateSortIndicators('leaguePlayersTable', state.sort.league_players);
}

async function loadDraftOrder(draftYearInput = null) {
  const draftYear = Number(draftYearInput || document.getElementById('draftYearSelect')?.value || state.draftOrder?.draft_year || currentSeasonStart() + 1);
  const res = await api(`/api/draft-live?year=${encodeURIComponent(draftYear)}`);
  setDraftLiveState(res);
  const loadedDraftYear = Number(state.draftOrder?.draft_year || draftYear);
  try {
    state.draftLedger = await api(`/api/draft-pick-ledger?year=${encodeURIComponent(loadedDraftYear)}`);
  } catch (err) {
    console.warn('Draft pick ledger load failed', err);
    state.draftLedger = null;
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
          id: `profile-${player.profile_id || player.id}`,
          profile_id: player.profile_id || null,
          player_id: player.id,
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
          id: item.profile_id ? `profile-${item.profile_id}` : `dead-${item.id}`,
          profile_id: item.profile_id || null,
          dead_contract_id: item.id,
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
        team_name: 'Agentes libres',
        source: 'Agente libre',
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
  const teamHomeBtn = document.getElementById('mobileTeamHomeBtn');
  const trackerBtn = document.getElementById('mobileTrackerBtn');
  const figuresBtn = document.getElementById('mobileFiguresBtn');
  const draftBtn = document.getElementById('mobileDraftBtn');
  const leaguePlayersBtn = document.getElementById('mobileLeaguePlayersBtn');
  const freeAgentsBtn = document.getElementById('mobileFreeAgentsBtn');
  const gmOfficeBtn = document.getElementById('mobileGmOfficeBtn');
  const tradeMachineBtn = document.getElementById('mobileTradeMachineBtn');
  const walletBtn = document.getElementById('mobileWalletBtn');
  const coadminVotesBtn = document.getElementById('mobileCoadminVotesBtn');
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
  if (teamHomeBtn) {
    teamHomeBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadCurrentTeamHome();
    });
  }
  if (trackerBtn) {
    trackerBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadTracker();
    });
  }
  if (figuresBtn) {
    figuresBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadFigures();
    });
  }
  if (draftBtn) {
    draftBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadDraftOrder();
    });
  }
  if (leaguePlayersBtn) {
    leaguePlayersBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadLeaguePlayers();
    });
  }
  if (freeAgentsBtn) {
    freeAgentsBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadFreeAgents();
    });
  }
  if (gmOfficeBtn) {
    gmOfficeBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadGmOffice();
    });
  }
  if (tradeMachineBtn) {
    tradeMachineBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadTradeMachine();
    });
  }
  if (walletBtn) {
    walletBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadWallet();
    });
  }
  if (coadminVotesBtn) {
    coadminVotesBtn.addEventListener('click', async () => {
      closeMobileSidebar();
      await loadCoadminVotes();
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
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.balance-value-wrap')) closeBalanceInfoPopovers();
  });
  state.auth = await api('/api/auth/status');
  state.csrfToken = state.auth?.csrf_token || null;
  const settingsRes = await api('/api/settings');
  state.settings = settingsRes.settings || state.settings;
  state.ui.seasonViewStart = normalizeSeasonViewStart(readInitialSeasonStart());
  renderAuthControls();
  await refreshWaiverBadges();
  await loadGmNotifications().catch((err) => console.warn('Could not load GM notifications', err));
  startGmNotificationsPolling();

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST', body: '{}' });
    window.location.href = '/';
  });
  document.getElementById('teamHomeBtn').addEventListener('click', async () => {
    await loadCurrentTeamHome();
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
  document.getElementById('leaguePlayersHomeBtn').addEventListener('click', async () => {
    await loadLeaguePlayers();
  });
  document.getElementById('freeAgentsHomeBtn').addEventListener('click', async () => {
    await loadFreeAgents();
  });
  document.getElementById('gmOfficeHomeBtn')?.addEventListener('click', async () => {
    await loadGmOffice();
  });
  document.getElementById('walletHomeBtn')?.addEventListener('click', async () => {
    await loadWallet();
  });
  document.getElementById('walletSearchBtn')?.addEventListener('click', () => {
    void fetchWalletResults();
  });
  document.getElementById('walletAmountInput')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      void fetchWalletResults();
    }
  });
  document.getElementById('walletSeasonSelect')?.addEventListener('change', (event) => {
    const amountInput = document.getElementById('walletAmountInput');
    if (amountInput) state.wallet.amountText = String(amountInput.value || '').trim();
    state.wallet.season = Number(event.target.value || currentSeasonStart());
    if (parseAmountLike(state.wallet.amountText) > 0) {
      void fetchWalletResults();
    } else {
      renderWallet();
    }
  });
  document.querySelectorAll('[data-wallet-tab]').forEach((button) => {
    button.addEventListener('click', () => {
      state.wallet.activeTab = button.dataset.walletTab === 'tools' ? 'tools' : 'clients';
      renderWalletTabs();
      renderWalletAppeal();
    });
  });
  document.getElementById('walletAppealPlayerSelect')?.addEventListener('change', (event) => {
    state.wallet.appealSelectedFreeAgentId = Number(event.target.value || 0) || null;
    renderWalletAppeal();
  });
  document.querySelectorAll('[data-wallet-sort]').forEach((button) => {
    button.addEventListener('click', () => {
      const key = String(button.dataset.walletSort || 'interest_count');
      const current = state.wallet.clientsSort || { key: 'interest_count', dir: 'desc' };
      state.wallet.clientsSort = {
        key,
        dir: current.key === key && current.dir === 'desc' ? 'asc' : 'desc',
      };
      state.wallet.clientsPage = 1;
      renderWalletClients();
    });
  });
  document.getElementById('coadminVotesHomeBtn')?.addEventListener('click', async () => {
    await loadCoadminVotes();
  });
  document.getElementById('coadminVotesBoard')?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-coadmin-vote-submit]');
    if (!btn) return;
    void submitCoadminVote(btn.dataset.coadminVoteSubmit);
  });
  document.getElementById('freeAgentSearchInput')?.addEventListener('input', (event) => {
    state.ui.freeAgentSearch = String(event.target.value || '');
    resetPagination('freeAgents');
    renderFreeAgents();
  });
  document.getElementById('freeAgentOfferYears')?.addEventListener('change', () => {
    renderFreeAgentOfferYearsTable({ preserveFirstAmount: true });
  });
  document.getElementById('freeAgentOfferTeam')?.addEventListener('change', () => {
    updateFreeAgentOfferSummary();
    syncFreeAgentOfferAmounts();
  });
  document.getElementById('freeAgentOfferType')?.addEventListener('change', syncFreeAgentOfferAmounts);
  document.getElementById('freeAgentOfferRaisePct')?.addEventListener('input', syncFreeAgentOfferAmounts);
  document.getElementById('freeAgentOfferCloseBtn')?.addEventListener('click', closeFreeAgentOfferModal);
  document.getElementById('freeAgentOfferSubmitBtn')?.addEventListener('click', () => { void submitFreeAgentOffer(); });
  document.getElementById('freeAgentOfferModal')?.addEventListener('click', (event) => {
    if (event.target === event.currentTarget) closeFreeAgentOfferModal();
  });
  document.getElementById('freeAgentNegotiateCloseBtn')?.addEventListener('click', closeFreeAgentNegotiateModal);
  document.getElementById('freeAgentNegotiateSubmitBtn')?.addEventListener('click', () => { void submitFreeAgentNegotiation(); });
  document.getElementById('freeAgentNegotiateModal')?.addEventListener('click', (event) => {
    if (event.target === event.currentTarget) closeFreeAgentNegotiateModal();
  });

  const teamsRes = await api('/api/teams');
  state.teams = teamsRes.teams;
  await refreshCoadminVoteRequests();
  setupSorting();
  setupLocatorModal();
  setupMobileNav();
  setupTradeMachineControls();
  setupTrackerTabs();
  setupTrackerSeasonControl();
  setupTrackerEconomySeasonControl();
  setupTeamTabs();
  setupTeamNavControls();
  setupRosterViewControl();
  setupGmOptionRequestDelegation();
  setupSeasonViewControl();
  setupOwnerOfficeControls();
  setupFiguresSeasonControl();
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
  const initialTeam = readInitialTeamCode() || (hasGmLevelRole(state.auth?.role) ? state.auth?.team_code : '');
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
