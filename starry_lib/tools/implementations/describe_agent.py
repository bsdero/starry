#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       describe_agent.py
# DESCRIPTION: Tool — full config of a named agent
# SUMMARY: Returns the full AgentConfig for a
#          named agent so the LLM can inspect it
#          before calling it.
# NOTES: Available in both plan and execution mode.
#        No dependency injection required.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    ahernandez86    Initial implementation
"""describe_agent tool."""

from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "describe_agent",
        "description": (
            "Get the full configuration of a "
            "specific named agent before calling "
            "it. Useful for understanding its "
            "role, provider, and capabilities."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Name of the agent "
                        "to describe."
                    ),
                },
            },
            "required": ["name"],
        },
    },
}


def execute(name: str) -> dict:
    """Return AgentConfig as a dict, or error."""
    from dataclasses import asdict
    from starry_lib.agents.agent_store import (
        get_agent,
    )
    cfg = get_agent(name)
    if cfg is None:
        return {
            "error": (
                f"Agent '{name}' not found."
            )
        }
    return asdict(cfg)
