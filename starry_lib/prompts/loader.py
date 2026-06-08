#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       loader.py
# DESCRIPTION: Prompt loader for built-in mode prompts
# SUMMARY: Loads prompt files from starry_lib/prompts/
#          with user-override support from
#          ~/.local/starry/prompts/.
#          Role prompts live in roles/<name>.txt;
#          user overrides in
#          ~/.local/starry/prompts/roles/<name>.txt.
# NOTES: User file wins over bundled file. Returns
#        empty string if neither exists so callers
#        can safely skip injection.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/29/2026    bsdero          Initial implementation
"""Prompt loader: bundled prompts with user override."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_USER_PROMPTS_DIR = (
    Path.home() / ".local" / "starry" / "prompts"
)


def load_plan_prompt() -> str:
    """Return plan mode prompt text.

    Checks ~/.local/starry/prompts/plan_mode.txt first;
    falls back to the bundled starry_lib/prompts file.
    Returns empty string if neither exists.
    """
    user_file = _USER_PROMPTS_DIR / "plan_mode.txt"
    if user_file.exists():
        return user_file.read_text(encoding="utf-8")
    bundled = _PROMPTS_DIR / "plan_mode.txt"
    if bundled.exists():
        return bundled.read_text(encoding="utf-8")
    return ""


def load_deep_prompt() -> str:
    """Return deep mode prompt text.

    Checks ~/.local/starry/prompts/deep_mode.txt first;
    falls back to the bundled starry_lib/prompts file.
    Returns empty string if neither exists.
    """
    user_file = _USER_PROMPTS_DIR / "deep_mode.txt"
    if user_file.exists():
        return user_file.read_text(encoding="utf-8")
    bundled = _PROMPTS_DIR / "deep_mode.txt"
    if bundled.exists():
        return bundled.read_text(encoding="utf-8")
    return ""


def load_role_prompt(role_name: str) -> str:
    """Return system prompt text for a named role.

    Checks ~/.local/starry/prompts/roles/<name>.txt
    first; falls back to the bundled
    starry_lib/prompts/roles/<name>.txt.
    Returns empty string if neither exists.
    """
    filename = f"{role_name}.txt"
    user_file = (
        _USER_PROMPTS_DIR / "roles" / filename
    )
    if user_file.exists():
        return user_file.read_text(encoding="utf-8")
    bundled = _PROMPTS_DIR / "roles" / filename
    if bundled.exists():
        return bundled.read_text(encoding="utf-8")
    return ""
