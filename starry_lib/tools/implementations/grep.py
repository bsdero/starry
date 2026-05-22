#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       grep.py
# DESCRIPTION: Grep tool — search file contents by regex
# SUMMARY: Walks a directory (or single file), applies a
#          compiled regex, and returns matching lines with
#          file path and line number.
# NOTES: Available in plan and execution modes.
#        include is a glob filter for filenames.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    bsdero          Initial implementation
"""grep tool: search file contents for a regex pattern."""

from __future__ import annotations

import pathlib
import re

SCHEMA = {
    "type": "function",
    "function": {
        "name": "grep",
        "description": (
            "Search file contents for a regex "
            "pattern. Returns matching lines with "
            "file path and line number."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Regex pattern to search."
                    ),
                },
                "include": {
                    "type": "string",
                    "description": (
                        "Filename glob filter "
                        "(e.g. '*.py'). "
                        "Default '*'."
                    ),
                    "default": "*",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "File or directory to "
                        "search (default '.')."
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
    include: str = "*",
    path: str = ".",
) -> dict:
    """Search files for regex pattern."""
    base = pathlib.Path(path).expanduser()
    results: list[dict] = []
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return {"error": f"Invalid regex: {exc}"}

    try:
        files = (
            [base]
            if base.is_file()
            else base.rglob(include)
        )
        for fp in files:
            if not fp.is_file():
                continue
            try:
                for lineno, line in enumerate(
                    fp.read_text(
                        errors="replace"
                    ).splitlines(),
                    start=1,
                ):
                    if rx.search(line):
                        results.append({
                            "file": str(fp),
                            "line": lineno,
                            "content": (
                                line.rstrip()
                            ),
                        })
            except Exception:
                continue
        return {
            "matches": results,
            "count": len(results),
        }
    except Exception as exc:
        return {"error": str(exc)}
