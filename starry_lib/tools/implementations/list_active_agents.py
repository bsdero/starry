#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       list_active_agents.py
# DESCRIPTION: Tool — list running named agents
# SUMMARY: Returns all live agent sessions from
#          the ActiveRegistry as a list of dicts.
# NOTES: Available in both plan and execution mode.
#        Requires set_registry() at startup.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    ahernandez86    Initial implementation
"""list_active_agents tool."""

from __future__ import annotations

_registry = None


def set_registry(registry) -> None:
    """Inject the active ActiveRegistry."""
    global _registry
    _registry = registry


SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_active_agents",
        "description": (
            "List all currently running named "
            "agent sessions. Returns name, "
            "session_id, role, provider, model, "
            "turn_count, and token_usage."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


def execute() -> list:
    """Return active agents as a list of dicts."""
    if _registry is None:
        return []
    return [
        {
            "name": info.name,
            "session_id": info.session_id,
            "role": info.role,
            "provider": info.provider,
            "model": info.model,
            "turn_count": info.turn_count,
            "token_usage": info.token_usage,
        }
        for info in _registry.list_active()
    ]
