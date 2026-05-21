#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       loader.py
# DESCRIPTION: Skill loader for StarryLib
# SUMMARY: Lists and reads markdown skill files
#          from the skills package directory.
#          Skills are injected as system messages
#          into the active session.
# NOTES: Raises FileNotFoundError when a skill
#        is requested by name but not found.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/20/2026    ahernandez86          Initial implementation
"""Skill loader: reads markdown skill files."""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent


def list_skills() -> list[str]:
    """Return names of all available .md skills."""
    return sorted(
        p.stem
        for p in _SKILLS_DIR.glob("*.md")
    )


def load_skill(name: str) -> str:
    """Read and return skill file content.

    Raises
    ------
    FileNotFoundError
        If no skill named *name* exists.
    """
    path = _SKILLS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Skill '{name}' not found."
        )
    return path.read_text(encoding="utf-8")
