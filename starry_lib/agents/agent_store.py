#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       agent_store.py
# DESCRIPTION: CRUD for persistent agent configs
# SUMMARY: Module-level functions to read/write
#          AgentConfig JSON files under
#          ~/.local/starry/agents/.
# NOTES: One JSON file per agent: <name>.json.
#        Invalid files are silently skipped on
#        list_agents().
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    bsdero    Initial implementation
# 05/06/2026    bsdero    Move storage to ~/.local/starry/
"""AgentStore: CRUD for ~/.local/starry/agents/."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from starry_lib.agents.agent_config import AgentConfig

_STORE_DIR = (
    Path.home() / ".local" / "starry" / "agents"
)


def _ensure_dir() -> Path:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORE_DIR


def _path(name: str) -> Path:
    return _ensure_dir() / f"{name}.json"


def list_agents() -> list[AgentConfig]:
    """Return all stored AgentConfig objects."""
    d = _ensure_dir()
    result: list[AgentConfig] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            result.append(AgentConfig(**data))
        except Exception:
            pass
    return result


def get_agent(name: str) -> AgentConfig | None:
    """Return AgentConfig by name, or None."""
    p = _path(name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return AgentConfig(**data)
    except Exception:
        return None


def save_agent(cfg: AgentConfig) -> None:
    """Create or overwrite an agent config."""
    _path(cfg.name).write_text(
        json.dumps(asdict(cfg), indent=2)
    )


def delete_agent(name: str) -> None:
    """Remove agent config file if it exists."""
    p = _path(name)
    if p.exists():
        p.unlink()


def agent_exists(name: str) -> bool:
    """True if an agent named *name* is stored."""
    return _path(name).exists()
