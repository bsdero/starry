#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       skill_loader.py
# DESCRIPTION: Auto-discovers native skill modules
# SUMMARY: Walks starry_lib/skills/*/ at import time.
#          Loads descriptor.json + skill.py from each
#          subdirectory and returns SkillTool objects.
# NOTES: Invalid skills are logged and skipped;
#        they do not abort startup.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/21/2026    bsdero    Initial implementation
"""skill_loader: auto-discover native skill modules."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent / "skills"
)


class SkillLoadError(Exception):
    """Raised when a skill directory is malformed."""


@dataclass
class SkillTool:
    """One discovered skill: schema + executor."""

    SCHEMA: dict
    execute: Callable


_cache: list[SkillTool] | None = None


def load_skills() -> list[SkillTool]:
    """Return all valid skill tools.

    Results are cached after the first call.
    Individual skills that fail to load are skipped
    with a warning; they do not abort startup.
    """
    global _cache
    if _cache is not None:
        return _cache
    result: list[SkillTool] = []
    if not _SKILLS_DIR.is_dir():
        _cache = result
        return result
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("_"):
            continue
        try:
            result.append(_load_one(skill_dir))
        except SkillLoadError as exc:
            log.warning(
                "Skipping skill %s: %s",
                skill_dir.name,
                exc,
            )
    _cache = result
    return result


def _load_one(skill_dir: Path) -> SkillTool:
    """Load and validate one skill directory."""
    desc_path = skill_dir / "descriptor.json"
    if not desc_path.exists():
        raise SkillLoadError(
            f"Missing descriptor.json in {skill_dir}"
        )
    try:
        schema = json.loads(
            desc_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise SkillLoadError(
            f"Invalid JSON in {desc_path}: {exc}"
        ) from exc

    skill_py = skill_dir / "skill.py"
    if not skill_py.exists():
        raise SkillLoadError(
            f"Missing skill.py in {skill_dir}"
        )
    spec = importlib.util.spec_from_file_location(
        f"_skill_{skill_dir.name}", skill_py
    )
    if spec is None or spec.loader is None:
        raise SkillLoadError(
            f"Cannot create spec for {skill_py}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(  # type: ignore[union-attr]
        module
    )

    fn = getattr(module, "execute", None)
    if fn is None or not callable(fn):
        raise SkillLoadError(
            f"No callable execute in {skill_py}"
        )

    if not asyncio.iscoroutinefunction(fn):
        _sync = fn

        async def _wrapped(**kwargs):
            return _sync(**kwargs)

        execute: Callable = _wrapped
    else:
        execute = fn

    return SkillTool(SCHEMA=schema, execute=execute)
