#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       agent_config.py
# DESCRIPTION: Persistence format for named agents
# SUMMARY: AgentConfig — a named, spawnable agent.
#          Pure data record. No runtime logic.
# NOTES: Stored as JSON in
#        ~/.local/starry/agents/<name>.json.
#        Converted to BaseAgent at spawn time via
#        roles.build_agent_from_persistent().
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    ahernandez86    Initial implementation
"""Persistence dataclass for named agents."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Named agent persistence record.

    Bound to a role + provider + optional model.
    Converted to BaseAgent at spawn time.
    """

    name: str
    label: str
    role: str
    provider: str
    model: str = ""
    system_prompt_addon: str = ""
    temperature: float = 0.0
    allowed_tools: list[str] = field(
        default_factory=list
    )
    denied_tools: list[str] = field(
        default_factory=list
    )
    allowed_skills: list[str] = field(
        default_factory=list
    )
    denied_skills: list[str] = field(
        default_factory=list
    )
    description: str = ""
