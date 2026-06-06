#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       commands/store.py
# DESCRIPTION: CRUD for user-defined custom commands
# SUMMARY: Load/save commands.json under the global
#          and project conf directories.
# NOTES: Global file: ~/.local/starry/conf/commands.json
#        Project file: .starry/commands.json
#        Project entries override global ones by name.
#        Names must match ^[a-zA-Z0-9-]+$ and may not
#        shadow built-in TUI commands.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 06/04/2026    bsdero    Initial implementation
"""CRUD for user-defined custom commands."""

from __future__ import annotations

import json
import re
from pathlib import Path

from starry_lib.config.paths import (
    global_conf_dir,
    project_conf_dir,
)

_GLOBAL_FILE = global_conf_dir() / "commands.json"

_NAME_RE = re.compile(r"^[a-zA-Z0-9-]+$")

_BUILTIN_NAMES: frozenset[str] = frozenset({
    "exit", "clear", "rewind", "summarize",
    "compact", "help", "tools", "skills",
    "sessions", "rename", "btw", "trace",
    "mode", "role", "setup", "init",
    "buffer", "stats", "agent", "close",
    "aboutme",
    "recap", "review", "focus", "goal",
    "project", "branch",
    "new", "add-dir", "save", "load",
    "doctor", "mcp",
    "team",
})


def _read_file(path: Path) -> dict[str, str]:
    """Return {name: prompt} from a commands JSON file."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        cmds = data.get("commands", {})
        return {
            k: v
            for k, v in cmds.items()
            if isinstance(k, str)
            and isinstance(v, str)
        }
    except Exception:
        return {}


def _write_global(cmds: dict[str, str]) -> None:
    _GLOBAL_FILE.parent.mkdir(
        parents=True, exist_ok=True
    )
    _GLOBAL_FILE.write_text(
        json.dumps({"commands": cmds}, indent=2)
    )


_BUILTIN_COMMANDS: dict[str, str] = {
    "recap": (
        "Provide a concise recap of what"
        " has been discussed and"
        " accomplished in this"
        " conversation so far. List"
        " decisions made, files changed,"
        " and any open questions."
    ),
    "review": (
        "Review the recent code changes"
        " in this project. Run git diff"
        " to see what changed, then give"
        " feedback on correctness, style,"
        " and potential issues. Flag"
        " anything that looks risky."
    ),
    "focus": (
        "For the rest of this session,"
        " focus your attention on:"
        " $ARGUMENTS. Keep this context"
        " in mind when reading files or"
        " answering questions."
    ),
    "goal": (
        "My goal for this session is:"
        " $ARGUMENTS. Acknowledge this"
        " goal and keep it in mind"
        " throughout our conversation."
    ),
    "project": (
        "Describe the current project."
        " Read CLAUDE.md or README.md if"
        " present. Summarise the project"
        " structure, entry points, and"
        " key modules."
    ),
    "branch": (
        "Help me work with git branch"
        " '$ARGUMENTS'. If the branch"
        " does not exist, create it."
        " If it does, switch to it."
        " Then confirm the current"
        " branch and status."
    ),
}


def seed_builtin_commands() -> None:
    """Write built-in commands to global
    commands.json if the file is absent.

    Does nothing if the file already
    exists (preserves user edits).
    """
    if _GLOBAL_FILE.exists():
        return
    _write_global(dict(_BUILTIN_COMMANDS))


def list_commands() -> list[dict]:
    """Return all commands merged from global + project.

    Project entries win on name collision.
    Returns list of {'name': str, 'prompt': str},
    sorted by name.
    """
    merged: dict[str, str] = _read_file(
        _GLOBAL_FILE
    )
    proj = project_conf_dir()
    if proj is not None:
        proj_file = proj / "commands.json"
        merged.update(_read_file(proj_file))
    return [
        {"name": k, "prompt": v}
        for k, v in sorted(merged.items())
    ]


def get_command(name: str) -> str | None:
    """Return the prompt for *name*, or None."""
    for entry in list_commands():
        if entry["name"] == name:
            return entry["prompt"]
    return None


def command_exists(name: str) -> bool:
    """Return True if *name* is a defined command."""
    return get_command(name) is not None


def validate_name(name: str) -> str | None:
    """Validate a candidate command name.

    Returns an error string on failure, or None if
    the name is acceptable.
    """
    if not name:
        return "Command name cannot be empty."
    if not _NAME_RE.match(name):
        return (
            "Name must contain only letters,"
            " digits, and hyphens."
        )
    if name.lower() in _BUILTIN_NAMES:
        return (
            f"'{name}' conflicts with a"
            " built-in command."
        )
    return None


def save_command(name: str, prompt: str) -> None:
    """Create or update a command in the global store."""
    cmds = _read_file(_GLOBAL_FILE)
    cmds[name] = prompt
    _write_global(cmds)


def delete_command(name: str) -> bool:
    """Delete *name* from the global store.

    Returns True if the entry was found and removed,
    False if it was not present.
    """
    cmds = _read_file(_GLOBAL_FILE)
    if name not in cmds:
        return False
    del cmds[name]
    _write_global(cmds)
    return True
