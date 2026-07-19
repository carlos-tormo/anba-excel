"""Generate the administrative league workbook read model."""

from __future__ import annotations

from typing import Any, Callable, Dict, List


class LeagueWorkbookExportService:
    def __init__(
        self,
        db: Any,
        *,
        get_settings: Callable[..., Dict[str, Any]],
        list_teams: Callable[..., List[Dict[str, Any]]],
        list_tracker: Callable[..., Dict[str, Any]],
        list_players: Callable[..., List[Dict[str, Any]]],
        list_free_agents: Callable[..., List[Dict[str, Any]]],
        get_team: Callable[..., Any],
        parse_bool: Callable[[Any], bool],
        normalize_team_codes: Callable[[Any], List[str]],
        season_label: Callable[[int], str],
        public_settings_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
        workbook_bytes: Callable[[List[Dict[str, Any]]], bytes],
        unrestricted_type: str,
        min_year: int,
        max_year: int,
    ) -> None:
        self._db = db
        self._get_settings = get_settings
        self._list_teams = list_teams
        self._list_tracker = list_tracker
        self._list_players = list_players
        self._list_free_agents = list_free_agents
        self._get_team = get_team
        self._parse_bool = parse_bool
        self._normalize_team_codes = normalize_team_codes
        self._season_label = season_label
        self._public_settings_payload = public_settings_payload
        self._workbook_bytes = workbook_bytes
        self._unrestricted_type = unrestricted_type
        self._min_year = min_year
        self._max_year = max_year

    def export(self) -> bytes:
        settings = self._get_settings()
        teams = self._list_teams()
        tracker = self._list_tracker()
        players_catalog = self._list_players()
        free_agents = self._list_free_agents()
        seasons = list(range(self._min_year, self._max_year + 1))
        team_payloads = [
            data
            for data in (self._get_team(str(team.get("code") or "")) for team in teams)
            if data
        ]

        def yn(value: Any) -> str:
            return "Sí" if self._parse_bool(value) else "No"

        def codes(value: Any) -> str:
            return ", ".join(self._normalize_team_codes(value))

        def text(value: Any) -> str:
            return "" if value is None else str(value)

        summary_rows: List[List[Any]] = [
            [
                "Equipo",
                "Nombre",
                "Temporada",
                "CAP TOTAL",
                "GASTO TOTAL",
                "Espacio CAP",
                "Espacio luxury",
                "Luxury tax",
                "Espacio 1er apron",
                "Espacio 2do apron",
                "Hard cap apron",
                "Contratos STD",
                "Contratos TW",
                "1as rondas",
                "2as rondas",
            ]
        ]
        for row in tracker.get("rows") or []:
            summary_rows.append(
                [
                    row.get("team_code"),
                    row.get("team_name"),
                    tracker.get("season_year"),
                    row.get("cap_total"),
                    row.get("gasto_total"),
                    row.get("espacio_cap"),
                    row.get("espacio_luxury"),
                    row.get("luxury_tax"),
                    row.get("espacio_1er_apron"),
                    row.get("espacio_2do_apron"),
                    row.get("apron_hard_cap"),
                    row.get("roster_standard_count"),
                    row.get("roster_two_way_count"),
                    row.get("draft_first_count"),
                    row.get("draft_second_count"),
                ]
            )

        team_rows: List[List[Any]] = [["Equipo", "Nombre", "GM", "Cash recibido", "Cash enviado"]]
        balance_rows: List[List[Any]] = [
            [
                "Equipo",
                "Nombre",
                "Temporada",
                "CAP TOTAL",
                "GASTO TOTAL",
                "Cuenta apron",
                "Espacio CAP",
                "Espacio luxury",
                "Luxury tax",
                "Espacio 1er apron",
                "Espacio 2do apron",
                "Salary cap",
                "Salary floor",
                "Luxury cap",
                "1er apron",
                "2do apron",
                "Open roster spot hold",
                "Hard cap apron",
            ]
        ]
        move_rows: List[List[Any]] = [
            [
                "Equipo",
                "Nombre",
                "Temporada",
                "Límite pre-30",
                "Usado pre-30",
                "Disponible pre-30",
                "Límite post-30",
                "Usado post-30",
                "Disponible post-30",
            ]
        ]
        hard_cap_rows: List[List[Any]] = [["Equipo", "Nombre", "Temporada", "Hard cap apron"]]
        roster_header = [
            "Equipo",
            "Nombre equipo",
            "Contract ID",
            "Profile ID",
            "Jugador",
            "Posición",
            "Tipo",
            "Rating",
            "Birds",
            "YOS",
            "Two-way",
            "Exhibit 10",
            "Firmado FA",
        ]
        for season in seasons:
            roster_header.extend([self._season_label(season), f"Opción {self._season_label(season)}"])
        roster_rows: List[List[Any]] = [roster_header]

        dead_header = [
            "Equipo",
            "Nombre equipo",
            "CAP muerto ID",
            "Profile ID",
            "Nombre",
            "Tipo",
            "Exclude from Gasto",
            "Exclude from CAP",
        ]
        for season in seasons:
            dead_header.append(self._season_label(season))
        dead_rows: List[List[Any]] = [dead_header]

        exception_rows: List[List[Any]] = [["Equipo", "Nombre equipo", "Asset ID", "Nombre", "Tipo", "Valor", "Detalles"]]
        draft_rows: List[List[Any]] = [
            [
                "Equipo",
                "Nombre equipo",
                "Asset ID",
                "Año",
                "Ronda",
                "Tipo",
                "Owner original",
                "Vendido a",
                "Equipos condicionales",
                "Restricted",
                "Stepien restricted",
                "Protected",
                "Frozen",
                "Label",
                "Detalles",
            ]
        ]
        rights_rows: List[List[Any]] = [["Equipo", "Nombre equipo", "Asset ID", "Nombre", "Detalles"]]
        frozen_rows: List[List[Any]] = [["Equipo", "Nombre equipo", "Penalty season", "Draft year", "Ronda", "Motivo", "Notas"]]
        gm_history_rows: List[List[Any]] = [["Equipo", "Nombre equipo", "GM", "Fecha inicio", "Color"]]

        for payload in team_payloads:
            team = payload.get("team") or {}
            code = team.get("code")
            name = team.get("name")
            team_rows.append([code, name, team.get("gm"), team.get("cash_received"), team.get("cash_sent")])
            season_summaries = payload.get("season_summaries") if isinstance(payload.get("season_summaries"), dict) else {}
            for season_key, summary in season_summaries.items():
                if not isinstance(summary, dict):
                    continue
                balance_rows.append(
                    [
                        code,
                        name,
                        summary.get("current_year") or season_key,
                        summary.get("cap_figure"),
                        summary.get("payroll"),
                        summary.get("apron_account"),
                        summary.get("room_to_cap"),
                        summary.get("room_to_luxury"),
                        summary.get("luxury_tax"),
                        summary.get("room_to_first_apron"),
                        summary.get("room_to_second_apron"),
                        summary.get("salary_cap"),
                        summary.get("salary_floor"),
                        summary.get("luxury_cap"),
                        summary.get("first_apron"),
                        summary.get("second_apron"),
                        summary.get("open_roster_spot_cap_hold"),
                        summary.get("apron_hard_cap"),
                    ]
                )
            move_summaries = payload.get("move_summaries") if isinstance(payload.get("move_summaries"), dict) else {}
            for season_key, move in move_summaries.items():
                if not isinstance(move, dict):
                    continue
                move_rows.append(
                    [
                        code,
                        name,
                        move.get("season_year") or season_key,
                        move.get("limit_pre30"),
                        move.get("used_pre30"),
                        move.get("remaining_pre30"),
                        move.get("limit_post30"),
                        move.get("used_post30"),
                        move.get("remaining_post30"),
                    ]
                )
            for hard_cap in payload.get("apron_hard_caps") or []:
                hard_cap_rows.append([code, name, hard_cap.get("season_year"), hard_cap.get("hard_cap")])
            for player in payload.get("players") or []:
                row = [
                    code,
                    name,
                    player.get("id"),
                    player.get("profile_id"),
                    player.get("name"),
                    player.get("position"),
                    player.get("bird_rights"),
                    player.get("rating"),
                    player.get("years_left"),
                    player.get("experience_years"),
                    yn(player.get("is_two_way")),
                    yn(player.get("is_exhibit10")),
                    yn(player.get("signed_as_free_agent")),
                ]
                for season in seasons:
                    row.extend([player.get(f"salary_{season}_text"), player.get(f"option_{season}")])
                roster_rows.append(row)
            for dead in payload.get("dead_contracts") or []:
                row = [
                    code,
                    name,
                    dead.get("id"),
                    dead.get("profile_id"),
                    dead.get("label"),
                    dead.get("dead_type"),
                    yn(dead.get("exclude_from_gasto")),
                    yn(dead.get("exclude_from_cap")),
                ]
                for season in seasons:
                    row.append(dead.get(f"salary_{season}_text"))
                dead_rows.append(row)
            for asset in payload.get("assets") or []:
                asset_type = str(asset.get("asset_type") or "").strip()
                if asset_type == "exception":
                    exception_rows.append(
                        [
                            code,
                            name,
                            asset.get("id"),
                            asset.get("label"),
                            asset.get("exception_type"),
                            asset.get("amount_text"),
                            asset.get("detail"),
                        ]
                    )
                elif asset_type == "draft_pick":
                    draft_rows.append(
                        [
                            code,
                            name,
                            asset.get("id"),
                            asset.get("year"),
                            asset.get("draft_round"),
                            asset.get("draft_pick_type"),
                            asset.get("original_owner"),
                            codes(asset.get("draft_pick_sold_to")),
                            codes(asset.get("draft_pick_conditional_teams")),
                            yn(asset.get("draft_pick_restricted")),
                            yn(asset.get("draft_pick_stepien_restricted")),
                            yn(asset.get("draft_pick_protected")),
                            yn(asset.get("draft_pick_frozen")),
                            asset.get("label"),
                            asset.get("detail"),
                        ]
                    )
                elif asset_type == "player_right":
                    rights_rows.append([code, name, asset.get("id"), asset.get("label"), asset.get("detail")])
            for frozen in payload.get("frozen_draft_picks") or []:
                frozen_rows.append(
                    [
                        code,
                        name,
                        frozen.get("penalty_season_year"),
                        frozen.get("draft_year"),
                        frozen.get("draft_round"),
                        frozen.get("reason"),
                        frozen.get("notes"),
                    ]
                )
            for gm in payload.get("gm_history") or []:
                gm_history_rows.append([code, name, gm.get("gm_name"), gm.get("start_date"), gm.get("color")])

        free_agent_header = ["Agente libre ID", "Profile ID", "Jugador", "Posición", "Rating", "Tipo FA", "Agente", "Tipo", "Birds", "YOS", "Detalles"]
        free_agent_rows = [free_agent_header] + [
            [
                item.get("id"),
                item.get("profile_id"),
                item.get("name"),
                item.get("position"),
                item.get("rating"),
                item.get("free_agent_type") or self._unrestricted_type,
                item.get("agent"),
                item.get("bird_rights"),
                item.get("years_left"),
                item.get("experience_years"),
                item.get("notes"),
            ]
            for item in free_agents
        ]

        profile_rows: List[List[Any]] = [
            [
                "Profile ID",
                "Jugador",
                "Estado",
                "Equipo",
                "YOS",
                "DOB",
                "Nacionalidad",
                "Fuente YOS",
                "Contrato activo",
                "CAP muerto",
                "Últimos movimientos",
            ]
        ]
        tx_rows: List[List[Any]] = [["Profile ID", "Jugador", "Fecha", "Acción", "Equipo", "Desde", "A", "Resumen"]]
        for item in players_catalog:
            logs = item.get("transaction_logs") if isinstance(item.get("transaction_logs"), list) else []
            profile_rows.append(
                [
                    item.get("profile_id") or item.get("id"),
                    item.get("name"),
                    item.get("status_label"),
                    item.get("team_code"),
                    item.get("experience_years"),
                    item.get("date_of_birth"),
                    item.get("nationality"),
                    item.get("yos_source"),
                    item.get("active_contract_summary"),
                    item.get("dead_contract_summary"),
                    " | ".join(str(log.get("summary") or "") for log in logs[:3]),
                ]
            )
            for log in logs:
                tx_rows.append(
                    [
                        item.get("profile_id") or item.get("id"),
                        item.get("name"),
                        log.get("created_at"),
                        log.get("action"),
                        log.get("team_code"),
                        log.get("from_team_code"),
                        log.get("to_team_code"),
                        log.get("summary"),
                    ]
                )

        with self._db.connect() as conn:
            economy_cur = conn.execute(
                """
                SELECT t.code AS team_code, t.name AS team_name, e.season_year, e.balance, e.revenue, e.expenses
                FROM team_economy e
                JOIN teams t ON t.id = e.team_id
                ORDER BY e.season_year, t.code
                """
            )
            economy_rows = [["Equipo", "Nombre", "Temporada", "Balance", "Ingresos", "Gastos"]] + [
                [
                    row["team_code"],
                    row["team_name"],
                    row["season_year"],
                    row["balance"],
                    row["revenue"],
                    row["expenses"],
                ]
                for row in economy_cur.fetchall()
            ]
            draft_cur = conn.execute(
                """
                SELECT
                    d.*,
                    COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                    COALESCE(original.name, d.original_team_code) AS original_team_name,
                    s.selection_text,
                    COALESCE(s.skipped, 0) AS skipped
                FROM draft_order d
                LEFT JOIN teams owner ON owner.code = d.owner_team_code
                LEFT JOIN teams original ON original.code = d.original_team_code
                LEFT JOIN draft_live_selections s ON s.draft_order_id = d.id
                ORDER BY d.draft_year,
                    CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                    d.pick_number,
                    d.id
                """
            )
            draft_order_rows = [
                ["Draft year", "Ronda", "#", "Equipo dueño", "Nombre dueño", "Vía", "Nombre original", "Selección"]
            ] + [
                [
                    row["draft_year"],
                    row["draft_round"],
                    row["pick_number"],
                    row["owner_team_code"],
                    row["owner_team_name"],
                    "" if row["owner_team_code"] == row["original_team_code"] else row["original_team_code"],
                    "" if row["owner_team_code"] == row["original_team_code"] else row["original_team_name"],
                    "Saltado" if self._parse_bool(row["skipped"]) else row["selection_text"],
                ]
                for row in draft_cur.fetchall()
            ]

        public_settings = self._public_settings_payload(settings)
        settings_rows = [["Clave", "Valor"]] + [[key, text(public_settings.get(key))] for key in sorted(public_settings.keys())]

        return self._workbook_bytes(
            [
                {"name": "Resumen", "rows": summary_rows},
                {"name": "Equipos", "rows": team_rows},
                {"name": "Balances", "rows": balance_rows},
                {"name": "Movimientos", "rows": move_rows},
                {"name": "Hard caps", "rows": hard_cap_rows},
                {"name": "Roster", "rows": roster_rows},
                {"name": "CAP muerto", "rows": dead_rows},
                {"name": "Exceptions", "rows": exception_rows},
                {"name": "Draft assets", "rows": draft_rows},
                {"name": "Player rights", "rows": rights_rows},
                {"name": "Frozen picks", "rows": frozen_rows},
                {"name": "Draft order", "rows": draft_order_rows},
                {"name": "Agentes libres", "rows": free_agent_rows},
                {"name": "Jugadores", "rows": profile_rows},
                {"name": "Movimientos jugadores", "rows": tx_rows},
                {"name": "Economía", "rows": economy_rows},
                {"name": "Cifras", "rows": settings_rows},
                {"name": "GM history", "rows": gm_history_rows},
            ]
        )

