"""Discord Gateway worker for waiting-list onboarding.

Run with:

    python -m app.workers.discord_waiting_list_bot --db data/league.db

Required environment:

    DISCORD_BOT_TOKEN
    PUBLIC_BASE_URL or WAITING_LIST_PUBLIC_BASE_URL

The bot must have the Discord privileged Server Members intent enabled.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from ..db.migrations import now_iso
    from ..db.repositories.waiting_list import WaitingListRepository
    from ..integrations.discord import DiscordConfig, DiscordIntegration, redact_secrets
    from ..integrations.discord_gateway import DiscordGatewayClient, DiscordGatewayConfig, WAITING_LIST_GATEWAY_INTENTS
    from ..runtime import load_env_file
    from ..server import LeagueDB
    from ..services.waiting_list import WAITING_LIST_DISCORD_ROLE_ID, WaitingListService
    from ..services.waiting_list_discord import WaitingListDiscordService
except ImportError:  # pragma: no cover - direct script support
    from db.migrations import now_iso
    from db.repositories.waiting_list import WaitingListRepository
    from integrations.discord import DiscordConfig, DiscordIntegration, redact_secrets
    from integrations.discord_gateway import DiscordGatewayClient, DiscordGatewayConfig, WAITING_LIST_GATEWAY_INTENTS
    from runtime import load_env_file
    from server import LeagueDB
    from services.waiting_list import WAITING_LIST_DISCORD_ROLE_ID, WaitingListService
    from services.waiting_list_discord import WaitingListDiscordService


logger = logging.getLogger("anba.waiting_list.discord_worker")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discord waiting-list onboarding worker")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/league.db"), help="SQLite database path")
    parser.add_argument("--env-file", default=os.getenv("ENV_FILE", ".env"), help="Optional env file path")
    parser.add_argument("--public-base-url", default=os.getenv("WAITING_LIST_PUBLIC_BASE_URL") or os.getenv("PUBLIC_BASE_URL") or "")
    parser.add_argument("--role-id", default=os.getenv("WAITING_LIST_DISCORD_ROLE_ID") or WAITING_LIST_DISCORD_ROLE_ID)
    parser.add_argument("--gateway-url", default=os.getenv("DISCORD_GATEWAY_URL", "wss://gateway.discord.gg"))
    parser.add_argument("--api-base-url", default=os.getenv("DISCORD_API_BASE_URL", "https://discord.com/api/v10"))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.getenv("DISCORD_WEBHOOK_TIMEOUT_SECONDS", "5") or "5"))
    parser.add_argument("--invite-ttl-seconds", type=int, default=int(os.getenv("WAITING_LIST_INVITE_TTL_SECONDS", "604800") or "604800"))
    parser.add_argument("--once", action="store_true", help="Process one Gateway connection instead of reconnecting forever")
    return parser.parse_args(argv)


def build_service(args: argparse.Namespace) -> WaitingListDiscordService:
    token = str(os.getenv("DISCORD_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")
    if not str(args.public_base_url or "").strip():
        raise RuntimeError("WAITING_LIST_PUBLIC_BASE_URL or PUBLIC_BASE_URL is required")
    db = LeagueDB(args.db)
    db.ensure_auth_schema()
    repository = getattr(db, "_waiting_list_repository", None) or WaitingListRepository(db, now=now_iso)
    waiting_list = WaitingListService(repository)
    discord = DiscordIntegration(
        DiscordConfig(
            bot_token=token,
            api_base_url=args.api_base_url,
            timeout_seconds=args.timeout_seconds,
        )
    )
    return WaitingListDiscordService(
        waiting_list,
        discord,
        public_base_url=args.public_base_url,
        role_id=args.role_id,
        invite_ttl_seconds=args.invite_ttl_seconds,
    )


def event_handler(service: WaitingListDiscordService) -> Any:
    def handle(event_type: str, payload: Dict[str, Any]) -> None:
        try:
            if event_type == "GUILD_MEMBER_UPDATE":
                result = service.handle_member_update(payload)
                if result.get("prompt_sent"):
                    logger.info("Waiting-list prompt sent discord_id=%s", result.get("discord_id"))
                return
            if event_type == "INTERACTION_CREATE":
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                custom_id = str(data.get("custom_id") or "")
                if custom_id.startswith("waiting_list:"):
                    result = service.handle_interaction(payload)
                    logger.info(
                        "Waiting-list interaction handled action=%s discord_id=%s handled=%s",
                        result.get("action"),
                        result.get("discord_id"),
                        result.get("handled"),
                    )
        except Exception as err:  # noqa: BLE001 - worker event boundary.
            logger.error("Waiting-list Discord event failed type=%s: %s", event_type, redact_secrets(err))

    return handle


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args(argv)
    env_path = Path(args.env_file)
    if env_path.exists():
        load_env_file(env_path)
        args = parse_args(argv)
    token = str(os.getenv("DISCORD_BOT_TOKEN") or "").strip()
    service = build_service(args)
    gateway = DiscordGatewayClient(
        DiscordGatewayConfig(
            token=token,
            gateway_url=args.gateway_url,
            intents=WAITING_LIST_GATEWAY_INTENTS,
        ),
        on_dispatch=event_handler(service),
        logger=logger,
    )
    logger.info("Starting Discord waiting-list worker role_id=%s", args.role_id)
    if args.once:
        gateway.run_once()
    else:
        gateway.run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
