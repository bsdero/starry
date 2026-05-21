#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       read.py
# DESCRIPTION: Read tool — reads a file or lists a directory
# SUMMARY: Returns file contents (optionally sliced) or a
#          directory entry listing.
# NOTES: Available in plan and execution modes.
#        offset and limit are 0-based line numbers.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    ahernandez86          Initial implementation
"""read tool: read file contents or list a directory."""

from __future__ import annotations

import pathlib

SCHEMA = {
    "type": "function",
    "function": {
        "name": "read",
        "description": (
            "Read a file's contents or list a "
            "directory's entries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": (
                        "Path to the file or "
                        "directory."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of lines "
                        "to return."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "description": (
                        "Line number to start "
                        "reading from (0-based)."
                    ),
                    "default": 0,
                },
            },
            "required": ["filePath"],
        },
    },
}


def execute(
    filePath: str,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    """Read file or list directory."""
    path = pathlib.Path(filePath).expanduser()

    if path.is_dir():
        try:
            entries = sorted(
                str(p) for p in path.iterdir()
            )
            return {
                "type": "directory",
                "path": str(path),
                "entries": entries,
            }
        except Exception as exc:
            return {"error": str(exc)}

    try:
        lines = path.read_text(
            errors="replace"
        ).splitlines()
        if offset:
            lines = lines[offset:]
        if limit is not None:
            lines = lines[:limit]
        return {
            "content": "\n".join(lines),
            "lines": len(lines),
            "path": str(path),
        }
    except FileNotFoundError:
        return {
            "error": f"Not found: {filePath}"
        }
    except Exception as exc:
        return {"error": str(exc)}
