#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       glob.py
# DESCRIPTION: Glob tool — find files by pattern
# SUMMARY: Uses pathlib.Path.glob() to match files under
#          a base directory.
# NOTES: Available in plan and execution modes.
#        Uses pathlib — does not import stdlib glob.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    ahernandez86          Initial implementation
"""glob tool: find files matching a glob pattern."""

from __future__ import annotations

import pathlib

SCHEMA = {
    "type": "function",
    "function": {
        "name": "glob",
        "description": (
            "Find files whose paths match a glob "
            "pattern under a base directory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern, e.g. "
                        "'**/*.py'."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Base directory to search "
                        "(default '.')."
                    ),
                    "default": ".",
                },
            },
            "required": ["pattern"],
        },
    },
}


def execute(
    pattern: str,
    path: str = ".",
) -> dict:
    """Return files matching pattern under path."""
    base = pathlib.Path(path).expanduser()
    try:
        matches = sorted(
            str(p) for p in base.glob(pattern)
        )
        return {
            "matches": matches,
            "count": len(matches),
        }
    except Exception as exc:
        return {"error": str(exc)}
