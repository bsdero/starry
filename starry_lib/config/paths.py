#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       paths.py
# DESCRIPTION: Runtime path constants for StarryLib
# SUMMARY: Single source of truth for all config paths.
# NOTES: No other module should hardcode ~/.local/starry.
#        Import global_conf_dir() or project_conf_dir() here.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 06/01/2026    bsdero          Initial implementation
"""Runtime path constants for StarryLib."""

from pathlib import Path

_INSTALL_ROOT = Path.home() / ".local" / "starry"
_GLOBAL_CONF = _INSTALL_ROOT / "conf"


def global_conf_dir() -> Path:
    """Return ~/.local/starry/conf/ (global config root)."""
    return _GLOBAL_CONF


def project_conf_dir() -> Path | None:
    """Return pwd/.starry/ if it exists, else None.

    Only the current working directory is checked.
    No directory tree walk is performed.
    """
    p = Path.cwd() / ".starry"
    return p if p.is_dir() else None


def effective_conf_dirs() -> list[Path]:
    """Return [global_conf_dir()] plus project dir if present.

    The project dir is always last — it wins on conflicts.
    Example return values:
      [~/.local/starry/conf/]               (no .starry/ found)
      [~/.local/starry/conf/, pwd/.starry/] (.starry/ found)
    """
    dirs = [_GLOBAL_CONF]
    proj = project_conf_dir()
    if proj is not None:
        dirs.append(proj)
    return dirs
