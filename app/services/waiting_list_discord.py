"""Discord waiting-list onboarding workflow composition."""

from __future__ import annotations

import re
from typing import Any, Dict
from urllib.parse import urlencode

try:
    from .waiting_list import WAITING_LIST_DISCORD_ROLE_ID, WAITING_LIST_INTEREST_PROMPT, WaitingListService
except ImportError:  # pragma: no cover
    from services.waiting_list import WAITING_LIST_DISCORD_ROLE_ID, WAITING_LIST_INTEREST_PROMPT, WaitingListService


class WaitingListDiscordService:
    YES_CUSTOM_ID = "waiting_list:yes"
    NO_CUSTOM_ID = "waiting_list:no"

    def __init__(
        self,
        waiting_list: WaitingListService,
        discord: Any,
        *,
        public_base_url: str,
        role_id: str = WAITING_LIST_DISCORD_ROLE_ID,
        invite_ttl_seconds: int = 604800,
    ) -> None:
        self.waiting_list = waiting_list
        self.discord = discord
        self.public_base_url = str(public_base_url or "").strip().rstrip("/")
        self.role_id = re.sub(r"\D+", "", str(role_id or ""))
        self.invite_ttl_seconds = max(60, int(invite_ttl_seconds or 604800))

    @staticmethod
    def user_display_name(user: Dict[str, Any]) -> str:
        global_name = str(user.get("global_name") or "").strip()
        username = str(user.get("username") or "").strip()
        discriminator = str(user.get("discriminator") or "").strip()
        if global_name:
            return global_name
        if username and discriminator and discriminator != "0":
            return f"{username}#{discriminator}"
        return username

    def prompt_payload(self) -> Dict[str, Any]:
        return {
            "content": WAITING_LIST_INTEREST_PROMPT,
            "allowed_mentions": {"parse": []},
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 3,
                            "label": "Sí",
                            "emoji": {"name": "✅"},
                            "custom_id": self.YES_CUSTOM_ID,
                        },
                        {
                            "type": 2,
                            "style": 4,
                            "label": "No",
                            "emoji": {"name": "❌"},
                            "custom_id": self.NO_CUSTOM_ID,
                        },
                    ],
                }
            ],
        }

    def invite_url(self, token: str) -> str:
        if not self.public_base_url:
            raise ValueError("waiting_list_public_base_url_required")
        return f"{self.public_base_url}/login?{urlencode({'waiting_list_token': token})}"

    def send_role_prompt(self, *, discord_id: Any) -> bool:
        clean_id = re.sub(r"\D+", "", str(discord_id or ""))
        if not clean_id:
            return False
        return bool(self.discord.send_dm(clean_id, self.prompt_payload()))

    def member_has_waiting_role(self, payload: Dict[str, Any]) -> bool:
        roles = {re.sub(r"\D+", "", str(role or "")) for role in payload.get("roles") or []}
        return bool(self.role_id and self.role_id in roles)

    def handle_member_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        discord_id = re.sub(r"\D+", "", str(user.get("id") or ""))
        if not discord_id:
            return {"handled": False, "reason": "discord_user_id_missing"}
        if not self.member_has_waiting_role(payload):
            return {"handled": False, "reason": "waiting_list_role_absent", "discord_id": discord_id}
        sent = self.send_role_prompt(discord_id=discord_id)
        return {"handled": sent, "discord_id": discord_id, "prompt_sent": sent}

    def handle_interaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        custom_id = str(data.get("custom_id") or "").strip()
        user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        if not user and isinstance(payload.get("member"), dict):
            user = payload["member"].get("user") if isinstance(payload["member"].get("user"), dict) else {}
        discord_id = re.sub(r"\D+", "", str(user.get("id") or ""))
        discord_username = self.user_display_name(user)
        interaction_id = str(payload.get("id") or "").strip()
        interaction_token = str(payload.get("token") or "").strip()
        if custom_id == self.YES_CUSTOM_ID:
            invite = self.waiting_list.create_invite(
                discord_id=discord_id,
                discord_username=discord_username,
                ttl_seconds=self.invite_ttl_seconds,
            )
            token = str(invite.get("token") or "")
            self.waiting_list.accept_invite_token(token)
            url = self.invite_url(token)
            content = (
                "Perfecto. Crea tu cuenta o inicia sesión con Google desde este enlace "
                f"para entrar en la Lista de espera: {url}"
            )
            if interaction_id and interaction_token:
                self.discord.respond_to_interaction(interaction_id, interaction_token, self.interaction_response_payload(content))
            return {"handled": True, "action": "accepted", "discord_id": discord_id, "invite_url": url}
        if custom_id == self.NO_CUSTOM_ID:
            self.waiting_list.decline_discord_interest(
                discord_id=discord_id,
                discord_username=discord_username,
            )
            content = "Entendido. No te añadiremos a la Lista de espera."
            if interaction_id and interaction_token:
                self.discord.respond_to_interaction(interaction_id, interaction_token, self.interaction_response_payload(content))
            return {"handled": True, "action": "declined", "discord_id": discord_id}
        return {"handled": False, "reason": "unknown_interaction", "custom_id": custom_id}

    @staticmethod
    def interaction_response_payload(content: str) -> Dict[str, Any]:
        return {
            "type": 4,
            "data": {
                "content": content,
                "flags": 64,
                "allowed_mentions": {"parse": []},
            },
        }
