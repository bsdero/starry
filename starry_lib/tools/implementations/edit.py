#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       edit.py
# DESCRIPTION: Edit tool — replace text in a file
# SUMMARY: Performs an exact string replacement in a file.
#          Requires oldString to be unique unless replaceAll
#          is set.
# NOTES: Available in execution mode only.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    ahernandez86          Initial implementation
"""edit tool: replace text in a file."""

from __future__ import annotations

import pathlib

SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit",
        "description": (
            "Replace an exact string in a file. "
            "oldString must be unique unless "
            "replaceAll is true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": (
                        "Path to the file to edit."
                    ),
                },
                "oldString": {
                    "type": "string",
                    "description": (
                        "Exact text to replace."
                    ),
                },
                "newString": {
                    "type": "string",
                    "description": (
                        "Replacement text."
                    ),
                },
                "replaceAll": {
                    "type": "boolean",
                    "description": (
                        "Replace all occurrences "
                        "(default false)."
                    ),
                    "default": False,
                },
            },
            "required": [
                "filePath",
                "oldString",
                "newString",
            ],
        },
    },
}


def execute(
    filePath: str,
    oldString: str,
    newString: str,
    replaceAll: bool = False,
) -> dict:
    """Replace oldString with newString in file."""
    path = pathlib.Path(filePath).expanduser()
    try:
        text = path.read_text(errors="replace")
    except FileNotFoundError:
        return {"error": f"Not found: {filePath}"}
    except Exception as exc:
        return {"error": str(exc)}

    count = text.count(oldString)
    if count == 0:
        return {
            "error": "oldString not found in file."
        }
    if count > 1 and not replaceAll:
        return {
            "error": (
                f"oldString appears {count} times. "
                "Set replaceAll=true or use a more "
                "specific string."
            )
        }

    n = count if replaceAll else 1
    new_text = text.replace(oldString, newString, n)
    try:
        path.write_text(new_text)
        return {
            "replaced": n,
            "file": str(path),
        }
    except Exception as exc:
        return {"error": str(exc)}
