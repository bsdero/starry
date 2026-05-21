#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       tool_loader.py
# DESCRIPTION: Tool loader — maps modes to tool sets
# SUMMARY: Defines which tools are active in each execution
#          mode and provides schema/executor helpers.
#          Native skills are auto-loaded from skills/.
# NOTES: plan mode: read-only + research tools + skills.
#        execution mode: plan tools + write/run tools.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    ahernandez86    Initial implementation
# 04/21/2026    ahernandez86    Replace flat skill tool
#                               with skill_loader
"""Tool loader: mode-aware tool schema and executor."""

from __future__ import annotations

import asyncio
import json

from starry_lib.tools.implementations import (
    bash,
    calculator,
    call_agent,
    describe_agent,
    edit,
    glob,
    grep,
    list_active_agents,
    list_available_agents,
    question,
    read,
    stop_agent,
    task,
    todowrite,
    webfetch,
    websearch,
    write,
)
from starry_lib.tools.skill_loader import load_skills

# Static tools available in both modes
_STATIC_PLAN = [
    todowrite,
    task,
    calculator,
    question,
    webfetch,
    websearch,
    glob,
    grep,
    read,
    list_available_agents,
    list_active_agents,
    describe_agent,
]

_READ_ONLY = frozenset({
    "read", "glob", "grep", "webfetch", "websearch",
})
_WRITE = frozenset({"bash", "edit", "write"})


def _cache_key(name: str, kwargs: dict) -> str:
    try:
        return (
            f"{name}:"
            f"{json.dumps(kwargs, sort_keys=True)}"
        )
    except TypeError:
        return f"{name}:{repr(sorted(kwargs.items()))}"


def _make_cached(name: str, fn, cache: dict):
    if asyncio.iscoroutinefunction(fn):
        return fn

    def _cached(**kw):
        key = _cache_key(name, kw)
        if key not in cache:
            cache[key] = fn(**kw)
        return cache[key]

    return _cached


def _make_invalidating(fn, cache: dict):
    def _inv(**kw):
        cache.clear()
        return fn(**kw)

    return _inv


def wrap_with_cache(
    executor: dict, cache: dict
) -> dict:
    """Return executor with read-only tools cached.

    Write tools (bash/edit/write) clear the entire
    cache on execution since file state may change.
    """
    wrapped = {}
    for name, fn in executor.items():
        if name in _READ_ONLY:
            wrapped[name] = _make_cached(
                name, fn, cache
            )
        elif name in _WRITE:
            wrapped[name] = _make_invalidating(
                fn, cache
            )
        else:
            wrapped[name] = fn
    return wrapped

# Tools added only in execution mode
_EXEC_ONLY = [
    bash,
    edit,
    write,
    call_agent,
    stop_agent,
]


def _plan_tools():
    return _STATIC_PLAN + load_skills()


def _exec_tools():
    return _plan_tools() + _EXEC_ONLY


def get_tool_schemas(
    mode: str = "execution",
) -> list[dict]:
    """Return OpenAI function schemas for the mode."""
    tools = (
        _exec_tools()
        if mode == "execution"
        else _plan_tools()
    )
    return [t.SCHEMA for t in tools]


def get_tool_executor(
    mode: str = "execution",
) -> dict[str, object]:
    """Return name→execute mapping for the mode."""
    tools = (
        _exec_tools()
        if mode == "execution"
        else _plan_tools()
    )
    return {
        t.SCHEMA["function"]["name"]: t.execute
        for t in tools
    }
