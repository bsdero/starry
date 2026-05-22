#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       stop_agent.py
# DESCRIPTION: Tool — terminate a named agent
# SUMMARY: Kills a running named agent session and
#          notifies the main LLM via an injected
#          system message.
# NOTES: Execution mode only.
#        Call set_context() at startup.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    bsdero    Initial implementation
"""stop_agent tool."""

from __future__ import annotations

_registry = None
_pool = None
_get_main_session = None  # callable → Session|None


def set_context(
    registry,
    pool,
    get_main_session=None,
) -> None:
    """Inject runtime dependencies at startup."""
    global _registry, _pool, _get_main_session
    _registry = registry
    _pool = pool
    _get_main_session = get_main_session


SCHEMA = {
    "type": "function",
    "function": {
        "name": "stop_agent",
        "description": (
            "Terminate a running named agent "
            "session. The agent's state is lost. "
            "The main LLM is notified."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Name of the agent to stop."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "Optional reason for "
                        "stopping the agent."
                    ),
                },
            },
            "required": ["name"],
        },
    },
}


async def execute(
    name: str,
    reason: str = "",
) -> str:
    """Kill the named agent and return status."""
    if _registry is None or _pool is None:
        return (
            "Error: agent runtime not initialized."
        )

    if not _registry.is_active(name):
        return f"Agent '{name}' is not active."

    await _registry.kill_agent(name, _pool)

    if _get_main_session is not None:
        ms = _get_main_session()
        if ms is not None:
            ms.inject_system_message(
                f'[System] Agent "{name}" has been'
                f' terminated and is no longer'
                f' available.'
            )

    return (
        f"Agent '{name}' terminated successfully."
    )
