"""Discord/press message composition, independent from HTTP delivery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

try:
    from ..domain._values import parse_amount_like, parse_bool, parse_float, parse_int, season_label
    from ..domain.cap import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR
    from ..domain.trade_rules import format_trade_money, normalize_trade_bucket
    from ..integrations.discord import truncate_text
except ImportError:  # pragma: no cover - supports direct app imports.
    from domain._values import parse_amount_like, parse_bool, parse_float, parse_int, season_label
    from domain.cap import CAP_FORECAST_MAX_YEAR, CAP_FORECAST_MIN_YEAR
    from domain.trade_rules import format_trade_money, normalize_trade_bucket
    from integrations.discord import truncate_text


@dataclass(frozen=True)
class EventNotification:
    """Transport-neutral content for one league event notification."""

    title: str
    description: str
    fields: List[Dict[str, Any]]
    color: int
    image_prompt: Dict[str, Any]
    image_reference_url: str = ""
    image_fallback_prompt: Optional[Dict[str, Any]] = None


def contract_offer_salary_lines(payload: Dict[str, Any]) -> str:
    """Format contract salaries consistently for notification composition."""
    raw_by_season = payload.get("salary_by_season")
    raw_options_by_season = payload.get("option_by_season")
    options_by_season = raw_options_by_season if isinstance(raw_options_by_season, dict) else {}

    def value_with_option(season: int, value: str) -> str:
        option = str(
            options_by_season.get(str(season))
            if str(season) in options_by_season
            else options_by_season.get(season, "")
        ).strip().upper()
        return f"{value} ({option})" if option else value

    lines: List[str] = []
    if isinstance(raw_by_season, dict):
        for season_key in sorted(raw_by_season, key=lambda value: parse_int(str(value)) or 9999):
            season = parse_int(str(season_key))
            if season is None:
                continue
            value = str(raw_by_season.get(season_key) or "").strip()
            if value:
                lines.append(f"{season_label(season)}: {value_with_option(season, value)}")
    for season in range(CAP_FORECAST_MIN_YEAR, CAP_FORECAST_MAX_YEAR + 1):
        value = str(payload.get(f"salary_{season}") or "").strip()
        if value and not any(line.startswith(season_label(season)) for line in lines):
            lines.append(f"{season_label(season)}: {value_with_option(season, value)}")
    return "\n".join(lines[:8]) or "Sin importes detallados"


def discord_notify_requested(payload: Dict[str, Any]) -> bool:
    return True if "notify_discord" not in payload else parse_bool(payload.get("notify_discord"))


def discord_image_requested(payload: Dict[str, Any]) -> bool:
    return True if "generate_discord_image" not in payload else parse_bool(payload.get("generate_discord_image"))


def free_agent_signed_notification(
    player: Dict[str, Any],
    *,
    offer_payload: Any = None,
    offer_type: Optional[str] = None,
) -> EventNotification:
    """Compose a signing notification from either offer or persisted salary data."""
    salary_summary = ""
    if isinstance(offer_payload, dict) and isinstance(offer_payload.get("salary_by_season"), dict):
        salary_summary = contract_offer_salary_lines(offer_payload)
    if not salary_summary or salary_summary == "Sin importes detallados":
        lines: List[str] = []
        for season in range(CAP_FORECAST_MIN_YEAR, CAP_FORECAST_MAX_YEAR + 1):
            salary_text = str(player.get(f"salary_{season}_text") or "").strip()
            if not salary_text:
                continue
            amount = parse_amount_like(salary_text)
            if amount is not None:
                salary_text = f"{int(round(amount)):,}".replace(",", ".")
            option_text = str(player.get(f"option_{season}") or "").strip().upper()
            if option_text:
                salary_text = f"{salary_text} ({option_text})"
            lines.append(f"{season_label(season)}: {salary_text}")
        salary_summary = "\n".join(lines[:3]) or "Sin salario registrado"
    return NotificationCompositionService.free_agent_signed(
        player,
        salary_summary=salary_summary,
        offer_type=offer_type,
    )


class NotificationCompositionService:
    """Create bounded Discord payloads without performing network operations."""

    @staticmethod
    def notification_payload(
        title: Any,
        description: Any,
        *,
        fields: Optional[Iterable[Dict[str, Any]]] = None,
        color: int = 0x0F766E,
        role_id: str = "",
        image_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_fields: List[Dict[str, Any]] = []
        for field in fields or []:
            name = truncate_text(field.get("name"), 256)
            value = truncate_text(field.get("value"), 1024)
            if name and value:
                normalized_fields.append(
                    {"name": name, "value": value, "inline": bool(field.get("inline"))}
                )

        embed: Dict[str, Any] = {
            "title": truncate_text(title, 256),
            "description": truncate_text(description, 4096),
            "color": color,
        }
        if normalized_fields:
            embed["fields"] = normalized_fields[:25]
        if image_filename:
            embed["image"] = {"url": f"attachment://{image_filename}"}

        allowed_mentions: Dict[str, Any] = {"parse": []}
        payload: Dict[str, Any] = {"embeds": [embed], "allowed_mentions": allowed_mentions}
        clean_role_id = str(role_id or "")
        if re.fullmatch(r"\d+", clean_role_id):
            payload["content"] = f"<@&{clean_role_id}>"
            allowed_mentions["roles"] = [clean_role_id]
        return payload

    @staticmethod
    def press_article_payload(text: Any, article_url: Any, image_filename: str) -> Dict[str, Any]:
        article_text = str(text or "").strip()
        if not article_text:
            raise ValueError("article_text_required")
        full_article_url = str(article_url or "").strip()
        if not full_article_url:
            raise ValueError("article_url_required")
        teaser = re.sub(r"\s+", " ", article_text).strip()
        if len(teaser) > 1000:
            teaser = f"{teaser[:997].rstrip()}..."
        return {
            "embeds": [
                {
                    "title": "ANBA News",
                    "description": f"{teaser}\n\n[Accede al artículo completo]({full_article_url})",
                    "url": full_article_url,
                    "color": 0x0F766E,
                    "image": {"url": f"attachment://{image_filename}"},
                }
            ],
            "allowed_mentions": {"parse": []},
        }

    @staticmethod
    def free_agent_negotiation_payload(
        *,
        team_code: str,
        player_name: str,
        agent_name: str,
        economic_offer: str,
        role_offer: str,
        comments: str,
    ) -> Dict[str, Any]:
        fields = [
            {"name": "Equipo", "value": team_code, "inline": True},
            {"name": "Jugador", "value": truncate_text(player_name, 1024), "inline": True},
            {"name": "Agente", "value": truncate_text(agent_name, 1024), "inline": True},
            {"name": "Oferta económica", "value": truncate_text(economic_offer, 1024), "inline": False},
            {"name": "Rol ofrecido", "value": truncate_text(role_offer, 1024), "inline": False},
            {"name": "Comentario del GM", "value": truncate_text(comments, 1024), "inline": False},
        ]
        return {
            "embeds": [
                {
                    "title": truncate_text(f"{team_code} inicia negociación por {player_name}", 256),
                    "description": "Solicitud de negociación enviada desde agentes libres.",
                    "fields": fields,
                    "color": 0x2563EB,
                }
            ],
            "allowed_mentions": {"parse": []},
        }

    @staticmethod
    def player_cut(result: Dict[str, Any]) -> EventNotification:
        team_code = str(result.get("team_code") or "").upper()
        team_name = str(result.get("team_name") or team_code)
        player_name = str(result.get("player_name") or "Jugador")
        reference_url = str(result.get("reference_image_url") or "").strip()
        title = f"{team_code} corta a {player_name}"
        description = "El jugador pasa a agentes libres y su contrato queda registrado como contrato muerto."
        if result.get("waiver"):
            description = "El jugador queda en waivers durante 48h. El jugador puede ser reclamado de waivers durante las siguientes 48h."
        elif not result.get("dead_contract_id"):
            description = "El contrato se termina de forma inmediata y el jugador pasa a agentes libres."
        fields = [
            {"name": "Equipo", "value": team_code, "inline": True},
            {"name": "Jugador", "value": player_name, "inline": True},
        ]
        if result.get("waiver_expires_at"):
            fields.append({"name": "Waivers hasta", "value": str(result["waiver_expires_at"]), "inline": True})
        generic = {
            "headline": title,
            "description": description,
            "teams": [team_code],
            "players": [player_name],
            "context": "Transaction: the team cuts the player. Visual should feel like a clean basketball news announcement.",
        }
        reference = {
            "headline": title,
            "description": description,
            "teams": [team_code],
            "players": [player_name],
            "team_name": team_name,
            "team_code": team_code,
            "player_name": player_name,
            "secondary_headline": description,
            "additional_details": description,
            "transaction_type": "Released",
            "use_player_reference": bool(reference_url),
        }
        return EventNotification(title, description, fields, 0xB91C1C, reference, reference_url, generic)

    @staticmethod
    def free_agent_signed(
        player: Dict[str, Any],
        *,
        salary_summary: str,
        offer_type: Optional[str] = None,
    ) -> EventNotification:
        team_code = str(player.get("team_code") or "").upper()
        team_name = str(player.get("team_name") or team_code)
        player_name = str(player.get("name") or "Jugador")
        reference_url = str(player.get("reference_image_url") or "").strip()
        contract_type = str(player.get("bird_rights") or "").strip()
        position = str(player.get("position") or "").strip()
        is_renewal = str(offer_type or "").strip().lower() == "renewal"
        details = " · ".join(part for part in [position, contract_type] if part)
        title = f"{team_code} renueva a {player_name}" if is_renewal else f"{team_code} firma a {player_name}"
        description = "El jugador firma un nuevo contrato con el equipo." if is_renewal else "El jugador llega desde la agencia libre."
        if details:
            description = f"{description} {details}."
        fields = [
            {"name": "Equipo", "value": team_code, "inline": True},
            {"name": "Jugador", "value": player_name, "inline": True},
        ]
        if position:
            fields.append({"name": "Posición", "value": position, "inline": True})
        if contract_type:
            fields.append({"name": "Contrato", "value": contract_type, "inline": True})
        fields.append({"name": "Salario", "value": salary_summary, "inline": False})
        generic = {
            "headline": title,
            "description": description,
            "teams": [team_code],
            "players": [player_name],
            "context": f"Free agency signing: {team_code} signs {player_name}. Contract details: {details or 'not specified'}.",
        }
        reference = {
            "headline": title,
            "description": description,
            "teams": [team_code],
            "players": [player_name],
            "team_name": team_name,
            "team_code": team_code,
            "player_name": player_name,
            "secondary_headline": description,
            "additional_details": f"Contrato: {details or 'sin detalles'}. Salario: {salary_summary.replace(chr(10), '; ')}.",
            "transaction_type": "Re-signing" if is_renewal else "Free Agency Signing",
            "use_player_reference": bool(reference_url),
        }
        return EventNotification(title, description, fields, 0x0F766E, reference, reference_url, generic)

    @staticmethod
    def _trade_pick_ref(value: Any) -> str:
        text = str(value or "").strip()
        for pattern, replacement in [
            (r"\b1st[-\s]?round\b", "1ª ronda"),
            (r"\bfirst[-\s]?round\b", "1ª ronda"),
            (r"\b2nd[-\s]?round\b", "2ª ronda"),
            (r"\bsecond[-\s]?round\b", "2ª ronda"),
            (r"\b1st\b", "1ª ronda"),
            (r"\b2nd\b", "2ª ronda"),
        ]:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @classmethod
    def trade_asset_summary(
        cls,
        players: List[Any],
        pick_count: Any,
        right_count: Any,
        swap_count: Any = 0,
        pick_refs: Optional[List[Any]] = None,
        swap_refs: Optional[List[Any]] = None,
        cash_amount: Any = 0,
    ) -> str:
        items = [str(name) for name in players or [] if str(name or "").strip()]
        picks, rights, swaps = parse_int(str(pick_count)), parse_int(str(right_count)), parse_int(str(swap_count))
        pick_labels = [label for ref in pick_refs or [] if (label := cls._trade_pick_ref(ref))]
        swap_labels = [label for ref in swap_refs or [] if (label := cls._trade_pick_ref(ref))]
        if pick_labels:
            items.extend(pick_labels)
        elif picks and picks > 0:
            items.append(f"{picks} ronda(s) del draft")
        if swap_labels:
            items.extend(swap_labels)
        elif swaps and swaps > 0:
            items.append(f"{swaps} derecho(s) de swap")
        if rights and rights > 0:
            items.append(f"{rights} derecho(s) de jugador")
        cash = parse_float(cash_amount) or 0.0
        if cash > 0:
            items.append(f"Cash: {format_trade_money(cash)}")
        return "\n".join(f"- {item}" for item in items) if items else "Sin activos registrados"

    @classmethod
    def trade_processed(cls, result: Dict[str, Any]) -> EventNotification:
        team_entries = [entry for entry in result.get("teams") or [] if isinstance(entry, dict)]
        bucket_label = "movimientos pre-30" if normalize_trade_bucket(result.get("trade_bucket")) == "pre30" else "movimientos post-30"
        description = f"El movimiento queda registrado en la cuenta de {bucket_label}."
        if team_entries:
            team_codes = [str(entry.get("code") or "").upper() for entry in team_entries if str(entry.get("code") or "").strip()]
            title = f"{' / '.join(team_codes)} cierran un traspaso"
            fields, player_names, context_parts = [], [], []
            for entry in team_entries:
                code = str(entry.get("code") or "").upper()
                received, sent = entry.get("received") or {}, entry.get("sent") or {}
                receives_text = cls.trade_asset_summary(
                    received.get("players") or [], received.get("pick_count"), received.get("right_count"),
                    received.get("swap_count"), received.get("picks") or [], received.get("swaps") or [],
                    received.get("cash_amount") or 0,
                )
                fields.append({"name": f"{code} recibe", "value": receives_text, "inline": False})
                player_names.extend(str(name) for name in sent.get("players") or [] if str(name or "").strip())
                context_parts.append(f"{code} receives: {receives_text}.")
            image = {"headline": title, "description": description, "teams": team_codes, "players": player_names[:6], "context": " ".join(context_parts)}
            return EventNotification(title, description, fields[:10], 0x0F766E, image)

        team_a = str(result.get("team_a", {}).get("code") or "").upper()
        team_b = str(result.get("team_b", {}).get("code") or "").upper()
        title = f"{team_a} y {team_b} cierran un traspaso"
        team_a_receives = cls.trade_asset_summary(
            result.get("players_b") or [], result.get("pick_count_b"), result.get("right_count_b"),
            result.get("swap_count_b"), result.get("pick_refs_b") or [], result.get("swap_refs_b") or [], result.get("cash_b") or 0,
        )
        team_b_receives = cls.trade_asset_summary(
            result.get("players_a") or [], result.get("pick_count_a"), result.get("right_count_a"),
            result.get("swap_count_a"), result.get("pick_refs_a") or [], result.get("swap_refs_a") or [], result.get("cash_a") or 0,
        )
        player_names = [str(name) for name in list(result.get("players_a") or []) + list(result.get("players_b") or []) if str(name or "").strip()]
        image = {
            "headline": title, "description": description, "teams": [team_a, team_b], "players": player_names[:6],
            "context": f"{team_a} receives: {team_a_receives}. {team_b} receives: {team_b_receives}.",
        }
        fields = [
            {"name": f"{team_a} recibe", "value": team_a_receives, "inline": False},
            {"name": f"{team_b} recibe", "value": team_b_receives, "inline": False},
        ]
        return EventNotification(title, description, fields, 0x0F766E, image)

    @staticmethod
    def draft_pick_selection(request: Dict[str, Any], current_draft_year: int) -> EventNotification:
        team_code = str(request.get("team_code") or request.get("owner_team_code") or "").upper()
        team_name = str(request.get("team_name") or team_code)
        player_name = str(request.get("selection_text") or "Jugador")
        draft_year = parse_int(request.get("draft_year")) or current_draft_year
        pick_number = parse_int(request.get("pick_number")) or 0
        draft_round = str(request.get("draft_round") or "").strip()
        round_label = "1ª ronda" if draft_round == "1st" else "2ª ronda" if draft_round == "2nd" else draft_round or "ronda"
        title = f"{team_code} elige a {player_name}"
        description = f"Pick #{pick_number} de la {round_label} del Draft {draft_year}."
        image = {
            "headline": title, "description": description, "teams": [team_code], "players": [player_name],
            "team_name": team_name, "team_code": team_code, "player_name": player_name,
            "secondary_headline": description, "additional_details": f"Draft {draft_year}. Pick #{pick_number}. {round_label}.",
            "transaction_type": "Draft Selection",
        }
        fields = [
            {"name": "Equipo", "value": team_code, "inline": True}, {"name": "Jugador", "value": player_name, "inline": True},
            {"name": "Pick", "value": f"#{pick_number}", "inline": True}, {"name": "Ronda", "value": round_label, "inline": True},
        ]
        return EventNotification(title, description, fields, 0x0F766E, image)

    @staticmethod
    def contract_option_action(player: Dict[str, Any], season: int, option_value: str, action: str) -> EventNotification:
        team_code = str(player.get("team_code") or "").upper()
        team_name = str(player.get("team_name") or team_code)
        player_name = str(player.get("name") or "Jugador")
        reference_url = str(player.get("reference_image_url") or "").strip()
        option_type = option_value.strip().upper()
        normalized_action = "accepted" if action == "accepted" else "rejected"
        verb = "acepta" if normalized_action == "accepted" else "rechaza"
        if option_type == "TO":
            title = f"{team_code} {verb} la team option de {player_name}"
        elif option_type == "PO":
            title = f"{player_name} {verb} su player option con {team_code}"
        elif option_type == "QO":
            title = f"{team_code} {verb} la qualifying offer de {player_name}"
        elif option_type == "GAP":
            title = f"{team_code} {verb} la opción GAP de {player_name}"
        else:
            title = f"{team_code} {verb} la opción {option_type} de {player_name}"
        season_text = f"{season}-{(season + 1) % 100:02d}"
        description = f"Decisión registrada para la temporada {season_text}."
        option_context = {"TO": "team option", "PO": "player option", "QO": "qualifying offer", "GAP": "GAP option"}.get(option_type, f"{option_type} option")
        transaction_type = {
            ("TO", "accepted"): "Team Option Exercised", ("TO", "rejected"): "Team Option Declined",
            ("PO", "accepted"): "Player Option Exercised", ("PO", "rejected"): "Player Option Declined",
            ("QO", "accepted"): "Qualifying Offer Accepted", ("QO", "rejected"): "Qualifying Offer Rejected",
            ("GAP", "accepted"): "Contract Guaranteed", ("GAP", "rejected"): "Contract Non-Guaranteed",
        }.get((option_type, normalized_action), "Contract Decision")
        generic = {"headline": title, "description": description, "teams": [team_code], "players": [player_name], "context": f"Contract decision: the {option_context} was {normalized_action} for season {season_text}."}
        reference = {
            "headline": title, "description": description, "teams": [team_code], "players": [player_name],
            "team_name": team_name, "team_code": team_code, "player_name": player_name,
            "secondary_headline": description, "additional_details": f"Temporada {season_text}. Opcion: {option_type}. Decision: {normalized_action}.",
            "transaction_type": transaction_type, "use_player_reference": bool(reference_url),
        }
        fields = [
            {"name": "Equipo", "value": team_code, "inline": True}, {"name": "Jugador", "value": player_name, "inline": True},
            {"name": "Temporada", "value": season_text, "inline": True}, {"name": "Opción", "value": option_type, "inline": True},
        ]
        color = 0x7C3AED if normalized_action == "accepted" else 0xB91C1C
        return EventNotification(title, description, fields, color, reference, reference_url, generic)

    @staticmethod
    def bird_rights_renounced(player: Dict[str, Any], season: int, rights_value: str) -> EventNotification:
        team_code = str(player.get("team_code") or "").upper()
        team_name = str(player.get("team_name") or team_code)
        player_name = str(player.get("name") or "Jugador")
        reference_url = str(player.get("reference_image_url") or "").strip()
        rights = rights_value.strip().upper()
        rights_label = {"FB": "Full Bird", "EB": "Early Bird", "NB": "Non-Bird"}.get(rights, rights)
        season_text = f"{season}-{(season + 1) % 100:02d}"
        title = f"{team_code} renuncia a los derechos {rights_label} de {player_name}"
        description = f"El cap hold queda eliminado para la temporada {season_text}."
        generic = {"headline": title, "description": description, "teams": [team_code], "players": [player_name], "context": f"Transaction: {team_code} renounces {rights_label} rights for {player_name}, removing the cap hold for {season_text}."}
        reference = {
            "headline": title, "description": description, "teams": [team_code], "players": [player_name],
            "team_name": team_name, "team_code": team_code, "player_name": player_name,
            "secondary_headline": description, "additional_details": f"Temporada {season_text}. Derechos: {rights_label}.",
            "transaction_type": "Rights Renounced", "use_player_reference": bool(reference_url),
        }
        fields = [
            {"name": "Equipo", "value": team_code, "inline": True}, {"name": "Jugador", "value": player_name, "inline": True},
            {"name": "Temporada", "value": season_text, "inline": True}, {"name": "Derechos", "value": rights_label, "inline": True},
        ]
        return EventNotification(title, description, fields, 0xB91C1C, reference, reference_url, generic)
