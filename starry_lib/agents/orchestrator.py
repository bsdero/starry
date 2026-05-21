"""Orchestrator: routes user input to the active agent and provider."""

from __future__ import annotations

from typing import AsyncIterator

from starry_lib.agents.base import BaseAgent
from starry_lib.agents.roles import build_agent
from starry_lib.config.settings import AppSettings
from starry_lib.llm.client import build_client


class Orchestrator:
    """Manages the active agent role and LLM provider.

    Streams response tokens for each user message using the raw
    OpenAI chat completions API.

    Note: openai-agents SDK is not used directly because it requires
    Python >=3.12. The same streaming behaviour is implemented via
    client.chat.completions.create(stream=True).
    """

    def __init__(
        self,
        settings: AppSettings,
        role: str | None = None,
        provider: str | None = None,
    ) -> None:
        self._settings = settings

        active_provider = provider or settings.active_provider
        active_role = role or settings.active_role

        if active_provider not in settings.providers:
            raise KeyError(
                f"Provider '{active_provider}' not found."
            )
        if active_role not in settings.agents:
            raise KeyError(
                f"Role '{active_role}' not found."
            )

        self._active_provider = active_provider
        self._active_role = active_role
        self._provider_cfg = settings.providers[active_provider]
        self._role_cfg = settings.agents[active_role]
        self.client = build_client(self._provider_cfg)
        self._agent: BaseAgent = build_agent(
            self._role_cfg, self._provider_cfg
        )

    @property
    def active_role_label(self) -> str:
        """Human-readable label of the active role."""
        return self._agent.label

    async def run(self, user_input: str) -> AsyncIterator[str]:
        """Stream response tokens for a user message."""
        messages = self._agent.build_messages(user_input)
        stream = await self.client.chat.completions.create(
            model=self._agent.model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def switch_role(self, role: str) -> None:
        """Switch the active agent role by name."""
        if role not in self._settings.agents:
            raise KeyError(f"Role '{role}' not found.")
        self._active_role = role
        self._role_cfg = self._settings.agents[role]
        self._agent = build_agent(
            self._role_cfg, self._provider_cfg
        )

    def switch_provider(self, provider: str) -> None:
        """Switch the active provider and rebuild the client."""
        if provider not in self._settings.providers:
            raise KeyError(
                f"Provider '{provider}' not found."
            )
        self._active_provider = provider
        self._provider_cfg = self._settings.providers[provider]
        self.client = build_client(self._provider_cfg)
        self._agent = build_agent(
            self._role_cfg, self._provider_cfg
        )
