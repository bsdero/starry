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
from starry_lib.config.paths import (
    global_conf_dir,
    project_conf_dir,
)

_STORE_DIR = global_conf_dir() / "agents"


def _ensure_dir() -> Path:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORE_DIR


def _path(name: str) -> Path:
    return _ensure_dir() / f"{name}.json"


def list_agents() -> list[AgentConfig]:
    """Return all stored AgentConfig objects.

    Merges global and project agents.
    Project agents shadow global agents with the same name.
    """
    d = _ensure_dir()
    seen: dict[str, AgentConfig] = {}

    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            cfg = AgentConfig(**data)
            seen[cfg.name] = cfg
        except Exception:
            pass

    proj = project_conf_dir()
    if proj is not None:
        proj_agents = proj / "agents"
        if proj_agents.is_dir():
            for f in sorted(
                proj_agents.glob("*.json")
            ):
                try:
                    data = json.loads(f.read_text())
                    cfg = AgentConfig(**data)
                    seen[cfg.name] = cfg
                except Exception:
                    pass

    return list(seen.values())


def get_agent(name: str) -> AgentConfig | None:
    """Return AgentConfig by name, or None.

    Checks pwd/.starry/agents/ first, then the global dir.
    """
    proj = project_conf_dir()
    if proj is not None:
        proj_p = proj / "agents" / f"{name}.json"
        if proj_p.exists():
            try:
                data = json.loads(proj_p.read_text())
                return AgentConfig(**data)
            except Exception:
                pass
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
