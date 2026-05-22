#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       active_registry.py
# DESCRIPTION: Registry of live named agent sessions
# SUMMARY: Maps agent name → session_id. Holds
#          per-agent async locks for serializing
#          concurrent call_agent calls.
# NOTES: Held as a single instance on TUI state.
#        Spawn and kill via public methods only —
#        never touch the pool directly for named
#        agents.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    bsdero    Initial implementation
"""ActiveRegistry: live named-agent session map."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


@dataclass
class ActiveAgentInfo:
    """Snapshot of a running named agent."""

    name: str
    session_id: str
    role: str
    provider: str
    model: str
    spawned_at: datetime
    turn_count: int
    token_usage: dict = field(
        default_factory=dict
    )


class ActiveRegistry:
    """Maps agent name → live Session.

    Holds per-agent asyncio.Locks to serialize
    concurrent call_agent calls into the same
    agent session.
    """

    def __init__(
        self,
        on_event: Callable | None = None,
    ) -> None:
        self._name_to_sid: dict[str, str] = {}
        self._configs: dict = {}
        self._spawn_times: dict[
            str, datetime
        ] = {}
        self._locks: dict[
            str, asyncio.Lock
        ] = {}
        self._on_event = on_event
        self._sessions: dict = {}

    def _emit(
        self, event_type: str, **kwargs
    ) -> None:
        if self._on_event:
            try:
                self._on_event(
                    event_type, **kwargs
                )
            except Exception:
                pass

    async def spawn_agent(
        self,
        name: str,
        pool,
        settings,
    ):
        """Spawn a named agent and register it.

        Loads AgentConfig from store, builds a
        BaseAgent, spawns a Session in the pool,
        and registers name → session_id.
        """
        from starry_lib.agents.agent_store import (
            get_agent,
        )
        from starry_lib.agents.roles import (
            build_agent_from_persistent,
        )

        cfg = get_agent(name)
        if cfg is None:
            raise KeyError(
                f"No agent config found:"
                f" '{name}'."
            )
        agent, provider_cfg = (
            build_agent_from_persistent(
                cfg, settings
            )
        )
        sid = f"agent-{name}"
        session = await pool.spawn(
            agent=agent,
            provider=provider_cfg,
            session_id=sid,
            mode="execution",
        )
        self._name_to_sid[name] = sid
        self._configs[name] = cfg
        self._spawn_times[name] = datetime.now(
            timezone.utc
        )
        self._locks[name] = asyncio.Lock()
        self._sessions[sid] = session
        self._emit("spawn", name=name, sid=sid)
        return session

    async def kill_agent(
        self,
        name: str,
        pool,
    ) -> None:
        """Stop and deregister a named agent."""
        sid = self._name_to_sid.get(name)
        if sid is None:
            return
        try:
            await pool.terminate(sid)
        except Exception:
            pass
        self._name_to_sid.pop(name, None)
        self._configs.pop(name, None)
        self._spawn_times.pop(name, None)
        self._locks.pop(name, None)
        self._sessions.pop(sid, None)
        self._emit("kill", name=name)

    async def kill_all(self, pool) -> None:
        """Kill all registered agents."""
        for name in list(self._name_to_sid):
            await self.kill_agent(name, pool)

    def list_active(
        self,
    ) -> list[ActiveAgentInfo]:
        """Snapshot of all running agents."""
        result: list[ActiveAgentInfo] = []
        for name, sid in (
            self._name_to_sid.items()
        ):
            session = self._sessions.get(sid)
            cfg = self._configs.get(name)
            usage: dict = {}
            turns: int = 0
            if session is not None:
                usage = session.token_usage
                turns = session._turn
            result.append(ActiveAgentInfo(
                name=name,
                session_id=sid,
                role=(
                    cfg.role
                    if cfg is not None
                    else ""
                ),
                provider=(
                    cfg.provider
                    if cfg is not None
                    else ""
                ),
                model=(
                    cfg.model
                    if cfg is not None
                    else ""
                ),
                spawned_at=(
                    self._spawn_times.get(
                        name,
                        datetime.now(
                            timezone.utc
                        ),
                    )
                ),
                turn_count=turns,
                token_usage=usage,
            ))
        return result

    def get_session(self, name: str):
        """Return Session for named agent or None."""
        sid = self._name_to_sid.get(name)
        if sid is None:
            return None
        return self._sessions.get(sid)

    def get_lock(
        self, name: str
    ) -> asyncio.Lock | None:
        """Return per-agent lock, or None."""
        return self._locks.get(name)

    def is_active(self, name: str) -> bool:
        """True if named agent is running."""
        return name in self._name_to_sid

    def list_names(self) -> list[str]:
        """Return names of all active agents."""
        return list(self._name_to_sid.keys())
