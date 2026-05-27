#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       pool.py
# DESCRIPTION: AgentPool — concurrent multi-agent manager
# SUMMARY: Creates, tracks, and runs multiple Sessions.
#          Provides fan-out (broadcast), parallel delegation
#          (delegate), and sequential pipeline patterns.
# NOTES: All LLM I/O is async; a shared Semaphore caps
#        concurrent requests. For CPU-bound tool work use
#        loop.run_in_executor(pool._executor, fn, *args).
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/15/2026    bsdero          Initial implementation
"""AgentPool: concurrent multi-agent session manager."""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator

from starry_lib.agents.roles import build_agent
from starry_lib.agents.session import Session
from starry_lib.config.settings import AppSettings, ProviderConfig
from starry_lib.llm.client import (
    build_client,
    get_model_context_window,
)
from starry_lib.types import AgentEvent, SessionInfo


class AgentPool:
    """Manages N Sessions running concurrently.

    All LLM calls are async I/O — the asyncio event loop
    multiplexes them without OS thread overhead. A shared
    Semaphore caps the maximum concurrent LLM requests.
    A ThreadPoolExecutor is provided for any CPU-bound tool
    work via loop.run_in_executor(pool._executor, fn, *args).

    Usage::

        async with AgentPool(settings) as pool:
            s = await pool.spawn(role="coder")
            async for event in s.chat("hello"):
                print(event.data, end="")
    """

    def __init__(
        self,
        settings: AppSettings,
        max_concurrent: int = 10,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._settings = settings
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._own_executor = executor is None
        self._executor: ThreadPoolExecutor = (
            executor or ThreadPoolExecutor()
        )
        self._sessions: dict[str, Session] = {}
        self._mcp_tools: list = []
        self._routing_table: dict[str, set[str]] = {}

    # ── Session lifecycle ─────────────────────────────────────

    async def spawn(
        self,
        role: str | None = None,
        provider: str | ProviderConfig | None = None,
        session_id: str | None = None,
        mode: str = "execution",
        agent=None,
    ) -> Session:
        """Create and register a new Session.

        Args:
            role: Agent role name; defaults to
                  settings.active_role.
            provider: Provider name (must exist in
                      settings) OR a ProviderConfig
                      object. Defaults to
                      settings.active_provider.
            session_id: Custom ID; auto-generated
                        if None.
            agent: Pre-built BaseAgent. When given,
                   role lookup is skipped and
                   provider must be a ProviderConfig
                   or a provider name string.

        Raises:
            KeyError: if role or provider not found.

        Example — custom provider at runtime::

            custom = make_provider(
                name="mine",
                base_url="http://host/v1",
                api_key="token",
                model="llama-3",
            )
            session = await pool.spawn(
                provider=custom
            )
        """
        if agent is not None:
            # Custom agent — skip role lookup
            if isinstance(provider, ProviderConfig):
                provider_cfg = provider
                provider_name = provider.name
            elif provider is not None:
                provider_name = str(provider)
                if provider_name not in (
                    self._settings.providers
                ):
                    raise KeyError(
                        f"Provider"
                        f" '{provider_name}'"
                        " not found."
                    )
                provider_cfg = (
                    self._settings.providers[
                        provider_name
                    ]
                )
            else:
                raise ValueError(
                    "provider is required when "
                    "agent is given explicitly."
                )
        else:
            active_role = (
                role or self._settings.active_role
            )
            if active_role not in (
                self._settings.agents
            ):
                raise KeyError(
                    f"Role '{active_role}'"
                    " not found."
                )
            if isinstance(
                provider, ProviderConfig
            ):
                provider_cfg = provider
                provider_name = provider.name
            else:
                provider_name = (
                    provider
                    or self._settings.active_provider
                )
                if provider_name not in (
                    self._settings.providers
                ):
                    raise KeyError(
                        f"Provider"
                        f" '{provider_name}'"
                        " not found."
                    )
                provider_cfg = (
                    self._settings.providers[
                        provider_name
                    ]
                )
            role_cfg = (
                self._settings.agents[active_role]
            )
            agent = build_agent(
                role_cfg, provider_cfg
            )

        sid = session_id or str(uuid.uuid4())
        client = build_client(provider_cfg)

        ctx_window = provider_cfg.context_window
        if ctx_window is None:
            ctx_window = await get_model_context_window(
                provider_cfg, agent.model
            )

        session = Session(
            session_id=sid,
            agent=agent,
            client=client,
            provider_name=provider_name,
            semaphore=self._semaphore,
            mode=mode,
            extra_tools=self._mcp_tools,
            context_window=ctx_window,
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Session:
        """Return a registered Session by ID.

        Raises:
            KeyError: if session_id is not found.
        """
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(
                f"Session '{session_id}' not found."
            )

    def list(self) -> list[SessionInfo]:
        """Return a snapshot of all active sessions."""
        return [s.info for s in self._sessions.values()]

    async def terminate(self, session_id: str) -> None:
        """Stop and remove a session by ID."""
        session = self.get(session_id)
        session._status = "stopped"
        del self._sessions[session_id]

    async def terminate_all(self) -> None:
        """Stop and remove all sessions."""
        for session in self._sessions.values():
            session._status = "stopped"
        self._sessions.clear()

    async def run_subtask(
        self,
        prompt: str,
        role: str | None = None,
        mode: str = "execution",
    ) -> str:
        """Spawn a child Session, run one turn,
        terminate it, and return the response.

        Args:
            prompt: The task prompt.
            role: Agent role; defaults to
                  settings.active_role.
            mode: Execution mode for the child.

        Returns:
            Full response string from the child.
        """
        session = await self.spawn(
            role=role, mode=mode
        )
        try:
            return await session.chat_complete(
                prompt
            )
        finally:
            await self.terminate(session.id)

    # ── Multi-agent patterns ──────────────────────────────────

    async def broadcast(
        self,
        user_input: str,
        session_ids: list[str] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Fan-out: same prompt to multiple agents in parallel.

        Yields a single multiplexed stream of AgentEvents.
        Each event carries a session_id so the caller can
        route tokens to the correct output panel.

        Args:
            user_input: Prompt sent to all sessions.
            session_ids: Subset of sessions; None = all.
        """
        ids = session_ids or list(self._sessions.keys())
        if not ids:
            return

        queue: asyncio.Queue[
            AgentEvent | None
        ] = asyncio.Queue()

        async def _feed(session: Session) -> None:
            async for event in session.chat(user_input):
                await queue.put(event)
            await queue.put(None)  # per-session sentinel

        tasks = [
            asyncio.create_task(
                _feed(self._sessions[sid])
            )
            for sid in ids
        ]

        done_count = 0
        while done_count < len(ids):
            item = await queue.get()
            if item is None:
                done_count += 1
            else:
                yield item

        await asyncio.gather(*tasks, return_exceptions=True)

    async def delegate(
        self,
        tasks: dict[str, str],
    ) -> dict[str, str]:
        """Run different prompts on different agents in parallel.

        Args:
            tasks: Mapping of session_id → prompt.

        Returns:
            Mapping of session_id → full response string.
        """

        async def _run(
            sid: str, prompt: str
        ) -> tuple[str, str]:
            response = await self._sessions[
                sid
            ].chat_complete(prompt)
            return sid, response

        results = await asyncio.gather(
            *(
                _run(sid, prompt)
                for sid, prompt in tasks.items()
            ),
            return_exceptions=False,
        )
        return dict(results)  # type: ignore[arg-type]

    async def pipeline(
        self,
        session_ids: list[str],
        initial_input: str,
    ) -> str:
        """Sequential chain: each agent's output feeds the next.

        Args:
            session_ids: Ordered list of session IDs.
            initial_input: Input to the first agent.

        Returns:
            Output of the final agent in the chain.
        """
        current = initial_input
        for sid in session_ids:
            current = await self._sessions[
                sid
            ].chat_complete(current)
        return current

    # ── Multi-agent routing ───────────────────────────────────

    async def route(
        self,
        prompt: str,
        from_role: str | None = None,
    ) -> Session:
        """Return the best session for *prompt*.

        Selection strategy (in order):
        1. If *from_role* is set, only consider sessions
           whose role appears in from_role's
           can_delegate_to list.
        2. Among candidates, pick the session whose role
           expertise overlaps most with *prompt* keywords.
        3. Fall back to the active_role session.

        Raises RuntimeError if the chosen role has no
        active session.
        """
        # Build candidate set
        if from_role is not None:
            allowed = self._routing_table.get(
                from_role, set()
            )
        else:
            allowed = None  # all sessions eligible

        candidates: list[Session] = []
        for session in self._sessions.values():
            role_name = session._agent.name
            if allowed is None or role_name in allowed:
                candidates.append(session)

        if not candidates:
            # Fall back to active_role
            for session in self._sessions.values():
                if (
                    session._agent.name
                    == self._settings.active_role
                ):
                    return session
            raise RuntimeError(
                f"No active session for role "
                f"'{self._settings.active_role}'"
            )

        # Score candidates by expertise keyword overlap
        prompt_words = set(prompt.lower().split())

        def _score(s: Session) -> int:
            exp = s._agent.expertise.lower()
            return sum(
                1 for w in prompt_words if w in exp
            )

        best = max(candidates, key=_score)

        # Verify session is reachable
        if best._agent.name not in {
            s._agent.name for s in self._sessions.values()
        }:
            raise RuntimeError(
                f"No active session for role "
                f"'{best._agent.name}'"
            )
        return best

    async def delegate_auto(
        self,
        prompt: str,
        from_role: str | None = None,
    ) -> str:
        """Route *prompt* to the best agent and return response."""
        session = await self.route(prompt, from_role)
        return await session.chat_complete(prompt)

    # ── Context manager ───────────────────────────────────────

    async def __aenter__(self) -> AgentPool:
        from starry_lib.tools.mcp_client import (
            build_mcp_tools,
        )
        self._mcp_tools = await build_mcp_tools(
            self._settings
        )
        # Build routing table: role → set of delegatable roles
        self._routing_table: dict[str, set[str]] = {
            name: set(cfg.can_delegate_to)
            for name, cfg in self._settings.agents.items()
        }
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.terminate_all()
        if self._own_executor:
            self._executor.shutdown(wait=False)
