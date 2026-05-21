#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       loader.py
# DESCRIPTION: Event loader for StarryLib
# SUMMARY: Reads markdown event templates from
#          the events package directory and
#          substitutes {{variable}} placeholders.
# NOTES: Returns None if the event file is absent
#        (event silently skipped). Missing
#        template variables are left as-is.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/20/2026    ahernandez86          Initial implementation
"""Event loader: renders markdown event templates."""

from __future__ import annotations

import re
from pathlib import Path

_EVENTS_DIR = Path(__file__).parent


def load_event(
    name: str, **kwargs: str
) -> str | None:
    """Read an event template and substitute vars.

    Parameters
    ----------
    name:
        Event name without extension, e.g.
        ``"on_session_start"``.
    **kwargs:
        Variable substitutions for
        ``{{variable}}`` placeholders.

    Returns
    -------
    str | None
        Rendered template string, or ``None`` if
        the event file does not exist.
    """
    path = _EVENTS_DIR / f"{name}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        return kwargs.get(key, match.group(0))

    return re.sub(
        r"\{\{(\w+)\}\}", _replace, text
    )
