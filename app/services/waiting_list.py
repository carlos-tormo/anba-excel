"""Waiting-list application service."""

from __future__ import annotations

from typing import Any, Dict


WAITING_LIST_DISCORD_ROLE_ID = "1164127012403810315"
WAITING_LIST_INTEREST_PROMPT = (
    "Estás interesado en unirte a la liga? Responde marcando el icono de check verde "
    "para confirmar que sí, o la cruz roja para indicar que no"
)


class WaitingListService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def list(self) -> Dict[str, Any]:
        return self.repository.list()

    def get(self, entry_id: Any) -> Dict[str, Any] | None:
        return self.repository.get(entry_id)

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.create(payload or {})

    def update(self, entry_id: Any, payload: Dict[str, Any]) -> Dict[str, Any] | None:
        return self.repository.update(entry_id, payload or {})

    def delete(self, entry_id: Any) -> bool:
        return self.repository.delete(entry_id)

    def confirm_discord_interest(
        self,
        *,
        discord_id: Any,
        display_name: Any = None,
        user_id: Any = None,
    ) -> Dict[str, Any]:
        return self.repository.upsert_discord_signup(
            discord_id=discord_id,
            display_name=display_name,
            user_id=user_id,
        )

    def monthly_interest_prompt(self) -> Dict[str, Any]:
        return {
            "role_id": WAITING_LIST_DISCORD_ROLE_ID,
            "message": WAITING_LIST_INTEREST_PROMPT,
        }

    def create_invite(self, *, discord_id: Any, discord_username: Any = None, ttl_seconds: int = 604800) -> Dict[str, Any]:
        return self.repository.create_invite(
            discord_id=discord_id,
            discord_username=discord_username,
            ttl_seconds=ttl_seconds,
        )

    def accept_invite_token(self, token: Any) -> Dict[str, Any] | None:
        return self.repository.mark_invite_accepted(token)

    def decline_discord_interest(self, *, discord_id: Any, discord_username: Any = None) -> Dict[str, Any]:
        return self.repository.mark_invite_declined(
            discord_id=discord_id,
            discord_username=discord_username,
        )

    def consume_invite_token(self, *, token: Any, user_id: Any, display_name: Any = None) -> Dict[str, Any] | None:
        return self.repository.consume_invite_for_user(
            token=token,
            user_id=user_id,
            display_name=display_name,
        )
