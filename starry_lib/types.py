#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       types.py
# DESCRIPTION: Shared data types for the StarryLib library
# SUMMARY: Message, SessionInfo, AgentEvent dataclasses used
#          across library components and consumer code.
# NOTES: These types form the public contract between the
#        library and any consumer (CLI, web app, etc.).
#        AgentEvent is the single currency of the streaming
#        API — every output from a session flows as events.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/15/2026    bsdero          Initial implementation
"""Shared data types for the StarryLib library."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class Message:
    """One message in a conversation history."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionInfo:
    """Serialisable snapshot of a Session's state."""

    session_id: str
    role: str
    provider: str
    created_at: datetime
    message_count: int
    status: Literal["idle", "running", "stopped"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AgentEvent:
    """Single event emitted during agent execution.

    type values:
        token       — one streaming token from the LLM
        tool_call   — agent is invoking a tool
        tool_result — tool returned a result
        error       — exception during execution
        done        — stream complete; data holds full response
    """

    type: Literal[
        "token",
        "tool_call",
        "tool_result",
        "error",
        "done",
        "provider_fallback",
    ]
    session_id: str
    data: str | dict[str, Any]
    timestamp: datetime = field(default_factory=_utcnow)
