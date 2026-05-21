#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       cli/themes/loader.py
# DESCRIPTION: Theme loader for StarryCLI TUI
# SUMMARY: Reads JSON theme files from the
#          cli/themes package directory.
#          Active theme is stored in a
#          module-level dict accessed via
#          theme[key].
# NOTES: If a key is missing from the loaded
#        theme, falls back to the default theme
#        to avoid KeyError crashes.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/28/2026    ahernandez86    Moved from
#                               starry_lib/themes/
"""Theme loader: reads JSON color-theme files."""

from __future__ import annotations

import json
from pathlib import Path

_THEMES_DIR = Path(__file__).parent

_active: dict[str, str] = {}


def load_theme(name: str = "jalisco") -> dict:
    """Load theme by name; returns the color map.

    Falls back to jalisco.json if the named
    theme file is missing.
    """
    global _active
    path = _THEMES_DIR / f"{name}.json"
    if not path.exists():
        path = _THEMES_DIR / "jalisco.json"
    with path.open(encoding="utf-8") as fh:
        _active = json.load(fh)
    return _active


def get_theme() -> dict[str, str]:
    """Return the currently loaded theme dict.

    Loads default if nothing has been loaded.
    """
    if not _active:
        load_theme()
    return _active


def list_themes() -> list[str]:
    """Return names of all available .json themes."""
    return sorted(
        p.stem
        for p in _THEMES_DIR.glob("*.json")
    )
