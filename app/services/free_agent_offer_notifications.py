"""Discord delivery orchestration for free-agent contract offers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.error import HTTPError, URLError

try:
    from ..auth.policies import normalize_team_code
    from ..domain_rules import (
        parse_amount_like,
        parse_bool,
        parse_free_agent_rep_discord_ids,
        parse_int,
    )
    from ..integrations.discord import DiscordIntegration, http_error_excerpt, truncate_text
    from .notifications import contract_offer_salary_lines
except ImportError:  # pragma: no cover - supports direct script execution.
    from auth.policies import normalize_team_code
    from domain_rules import (
        parse_amount_like,
        parse_bool,
        parse_free_agent_rep_discord_ids,
        parse_int,
    )
    from integrations.discord import DiscordIntegration, http_error_excerpt, truncate_text
    from services.notifications import contract_offer_salary_lines


@dataclass(frozen=True)
class FreeAgentOfferDiscordConfig:
    enabled: bool
    webhook_url: str
    forum_tag_ids: tuple[str, ...] = ()
    offer_role_id: str = ""
    bot_token: str = ""


class FreeAgentOfferNotificationService:
    """Creates/reuses offer threads and privately delivers offer details."""

    def __init__(
        self,
        discord: DiscordIntegration,
        free_agents: Any,
        settings: Any,
        offer_policy: Any,
        config: FreeAgentOfferDiscordConfig,
        *,
        log_error: Optional[Callable[..., None]] = None,
    ) -> None:
        self.discord = discord
        self.free_agents = free_agents
        self.settings = settings
        self.offer_policy = offer_policy
        self.config = config
        self.log_error = log_error or (lambda *_args: None)

    def agent_discord_id(self, free_agent: Dict[str, Any]) -> Optional[str]:
        rep_map = parse_free_agent_rep_discord_ids(
            self.settings.get_all().get("free_agent_rep_discord_ids")
        )
        agent_name = str(free_agent.get("agent") or "").strip()
        if agent_name:
            for configured_name, configured_id in rep_map.items():
                if configured_name.casefold() == agent_name.casefold():
                    return configured_id
        return None

    def deliver(
        self,
        free_agent: Dict[str, Any],
        team_code: str,
        payload: Dict[str, Any],
        offer_type: Optional[str] = None,
    ) -> Dict[str, bool]:
        return self.notify(
            free_agent,
            team_code,
            payload,
            offer_type,
            self.agent_discord_id(free_agent),
        )

    def notify(
        self,
        free_agent: Dict[str, Any],
        team_code: str,
        payload: Dict[str, Any],
        offer_type: Optional[str] = None,
        agent_discord_id: Optional[str] = None,
    ) -> Dict[str, bool]:
        result = {
            "thread_sent": False,
            "agent_dm_sent": False,
            "agent_discord_configured": False,
        }
        if not self.config.enabled:
            return result

        settings = self.settings.get_all()
        public_payload, private_payload, thread_name = self._payloads(
            free_agent, team_code, payload, offer_type
        )
        self._deliver_forum_thread(
            free_agent,
            public_payload,
            thread_name,
            parse_bool(settings.get("discord_free_agent_offer_role_ping_enabled", "1")),
            result,
        )
        self._deliver_agent_dm(agent_discord_id, private_payload, result)
        return result

    def _deliver_forum_thread(
        self,
        free_agent: Dict[str, Any],
        payload: Dict[str, Any],
        thread_name: str,
        role_ping_enabled: bool,
        result: Dict[str, bool],
    ) -> None:
        if not self.config.webhook_url:
            return
        try:
            existing_thread = self.free_agents.get_offer_thread(free_agent)
            if existing_thread and existing_thread.get("thread_id"):
                try:
                    reuse_payload = dict(payload)
                    reuse_payload.pop("applied_tags", None)
                    self.discord.post_webhook_json(
                        reuse_payload,
                        webhook_url=self.config.webhook_url,
                        thread_id=str(existing_thread["thread_id"]),
                    )
                    result["thread_sent"] = True
                except HTTPError as error:
                    if error.code not in {400, 404, 405}:
                        raise
                    self.log_error(
                        "Discord offer thread reuse failed; creating new thread: %s",
                        http_error_excerpt(error),
                    )
            if not result["thread_sent"]:
                self._create_forum_thread(
                    free_agent, payload, thread_name, role_ping_enabled
                )
                result["thread_sent"] = True
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            self.log_error(
                "Discord free-agent offer notification failed: %s",
                http_error_excerpt(error) if isinstance(error, HTTPError) else error,
            )

    def _create_forum_thread(
        self,
        free_agent: Dict[str, Any],
        payload: Dict[str, Any],
        thread_name: str,
        role_ping_enabled: bool,
    ) -> None:
        creation_payload = {
            **payload,
            "allowed_mentions": dict(payload.get("allowed_mentions") or {}),
        }
        offer_role_id = re.sub(r"\D+", "", self.config.offer_role_id)
        if offer_role_id and role_ping_enabled:
            creation_payload["content"] = f"<@&{offer_role_id}>"
            creation_payload["allowed_mentions"]["parse"] = []
            creation_payload["allowed_mentions"]["roles"] = [offer_role_id]
        try:
            response = self.discord.post_webhook_json(
                creation_payload,
                webhook_url=self.config.webhook_url,
                thread_name=thread_name,
                wait=True,
            )
            thread_id = response.get("channel_id") if isinstance(response, dict) else None
            if thread_id:
                self.free_agents.upsert_offer_thread(
                    free_agent, str(thread_id), thread_name
                )
        except HTTPError as error:
            if error.code not in {400, 404, 405}:
                raise
            self.log_error(
                "Discord offer thread creation failed: %s", http_error_excerpt(error)
            )

    def _deliver_agent_dm(
        self,
        agent_discord_id: Optional[str],
        payload: Dict[str, Any],
        result: Dict[str, bool],
    ) -> None:
        clean_id = re.sub(r"\D+", "", str(agent_discord_id or ""))
        result["agent_discord_configured"] = bool(clean_id)
        if not clean_id:
            return
        if not self.config.bot_token:
            self.log_error(
                "Discord free-agent offer DM failed: DISCORD_BOT_TOKEN is not configured"
            )
            return
        try:
            result["agent_dm_sent"] = self.discord.send_dm(clean_id, payload)
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as error:
            self.log_error(
                "Discord free-agent offer DM failed: %s",
                http_error_excerpt(error) if isinstance(error, HTTPError) else error,
            )

    def _payloads(
        self,
        free_agent: Dict[str, Any],
        team_code: str,
        payload: Dict[str, Any],
        offer_type: Optional[str],
    ) -> tuple[Dict[str, Any], Dict[str, Any], str]:
        player_name = str(free_agent.get("name") or "Jugador")
        team = normalize_team_code(team_code) or str(team_code or "").upper()
        years = parse_int(payload.get("years"))
        raise_percent = parse_amount_like(payload.get("annual_raise_percent"))
        normalized_offer_type = str(offer_type or "").strip().lower()
        is_renewal = normalized_offer_type == "renewal" or (
            not normalized_offer_type
            and self.offer_policy.is_renewal(free_agent, team)
        )
        if raise_percent is not None and raise_percent > 0:
            raise_text = f"Subidas {raise_percent:g}%"
        elif raise_percent is not None and raise_percent < 0:
            raise_text = f"Bajadas {abs(raise_percent):g}%"
        else:
            raise_text = "Sin subidas"
        private_embed: Dict[str, Any] = {
            "title": truncate_text(
                f"Oferta de renovación de {team} por {player_name}"
                if is_renewal
                else f"Oferta de {team} por {player_name}",
                256,
            ),
            "description": "Detalles privados de la oferta enviada desde agentes libres.",
            "color": 0x0F766E,
            "fields": [
                {"name": "Equipo", "value": team, "inline": True},
                {"name": "Jugador", "value": truncate_text(player_name, 1024), "inline": True},
                {
                    "name": "Agente",
                    "value": truncate_text(
                        free_agent.get("agent") or "Agente sin asignar", 1024
                    ),
                    "inline": True,
                },
                {"name": "Modalidad", "value": "Oferta de renovación" if is_renewal else "Oferta", "inline": True},
                {
                    "name": "Tipo",
                    "value": truncate_text(
                        payload.get("contract_type") or "Sin tipo definido", 1024
                    ),
                    "inline": True,
                },
                {
                    "name": "Duración",
                    "value": (
                        f"{years} año(s)"
                        if years and years > 0
                        else "Sin duración definida"
                    ),
                    "inline": True,
                },
                {"name": "Subidas", "value": raise_text, "inline": True},
                {
                    "name": "Rol",
                    "value": truncate_text(
                        payload.get("role") or "Sin rol definido", 1024
                    ),
                    "inline": True,
                },
                {
                    "name": "Importes",
                    "value": truncate_text(contract_offer_salary_lines(payload), 1024),
                    "inline": False,
                },
            ],
        }
        notes = str(payload.get("notes") or "").strip()
        if notes:
            private_embed["fields"].append(
                {"name": "Comentarios", "value": truncate_text(notes, 1024), "inline": False}
            )
        public_payload: Dict[str, Any] = {
            "embeds": [{
                "title": "Oferta recibida",
                "description": (
                    "Se ha creado este hilo automáticamente al recibir una oferta por el jugador. "
                    "El agente posteará aquí los detalles cuando lo considere necesario."
                ),
                "color": 0x0F766E,
            }],
            "allowed_mentions": {"parse": []},
        }
        if self.config.forum_tag_ids:
            public_payload["applied_tags"] = list(self.config.forum_tag_ids)
        private_payload = {
            "embeds": [private_embed],
            "allowed_mentions": {"parse": []},
        }
        return (
            public_payload,
            private_payload,
            truncate_text(player_name, 100) or "Jugador",
        )
