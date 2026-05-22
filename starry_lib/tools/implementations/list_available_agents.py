#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       list_available_agents.py
# DESCRIPTION: Tool — list stored named agents
# SUMMARY: Returns all AgentConfigs from the
#          agent store as a JSON-serialisable list.
# NOTES: Available in both plan and execution mode.
#        No dependency injection required.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    bsdero    Initial implementation
"""list_available_agents tool."""

from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_available_agents",
        "description": (
            "List all named agents available "
            "to spawn. Returns name, label, role, "
            "provider, model, and description."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


def execute() -> list:
    """Return stored agents as a list of dicts."""
    from starry_lib.agents.agent_store import (
        list_agents,
    )
    agents = list_agents()
    return [
        {
            "name": a.name,
            "label": a.label,
            "role": a.role,
            "provider": a.provider,
            "model": (
                a.model
                or "(provider default)"
            ),
            "description": a.description,
        }
        for a in agents
    ]
