#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       write.py
# DESCRIPTION: Write tool — create or overwrite a file
# SUMMARY: Writes content to a file, creating parent dirs
#          as needed. Overwrites if the file exists.
# NOTES: Available in execution mode only.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    ahernandez86          Initial implementation
"""write tool: create or overwrite a file."""

from __future__ import annotations

import pathlib

SCHEMA = {
    "type": "function",
    "function": {
        "name": "write",
        "description": (
            "Create or overwrite a file with the "
            "given content. Parent directories are "
            "created automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": (
                        "Path to the file to write."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Content to write to "
                        "the file."
                    ),
                },
            },
            "required": ["filePath", "content"],
        },
    },
}


def execute(filePath: str, content: str) -> dict:
    """Write content to filePath."""
    path = pathlib.Path(filePath).expanduser()
    try:
        path.parent.mkdir(
            parents=True, exist_ok=True
        )
        path.write_text(content)
        return {
            "written": len(content),
            "file": str(path),
        }
    except Exception as exc:
        return {"error": str(exc)}
