"""Outbound service adapters used by the ANBA application."""

from .discord import DiscordConfig, DiscordIntegration
from .openai import OpenAIConfig, OpenAIIntegration

__all__ = [
    "DiscordConfig",
    "DiscordIntegration",
    "OpenAIConfig",
    "OpenAIIntegration",
]
