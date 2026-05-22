#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       todowrite.py
# DESCRIPTION: Todowrite tool — manage a persistent task list
# SUMMARY: Writes the full todo list as JSON to a file in
#          the user's home directory. Replaces the whole list
#          on each call (snapshot model).
# NOTES: Available in plan and execution modes.
#        File: ~/.local/starry/todos.json
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    bsdero          Initial implementation
"""todowrite tool: manage a persistent task list."""

from __future__ import annotations

import json
import pathlib

_TODO_FILE = (
    pathlib.Path.home()
    / ".local" / "starry" / "todos.json"
)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "todowrite",
        "description": (
            "Overwrite the persistent task list "
            "with the provided todos array. "
            "Each item requires id, content, "
            "and status fields."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": (
                        "Full list of todo items."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string"
                            },
                            "content": {
                                "type": "string"
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                ],
                            },
                            "priority": {
                                "type": "string",
                                "enum": [
                                    "low",
                                    "medium",
                                    "high",
                                ],
                            },
                        },
                        "required": [
                            "id",
                            "content",
                            "status",
                        ],
                    },
                }
            },
            "required": ["todos"],
        },
    },
}


def execute(todos: list) -> dict:
    """Persist the todo list to disk."""
    try:
        _TODO_FILE.parent.mkdir(
            parents=True, exist_ok=True
        )
        _TODO_FILE.write_text(
            json.dumps(todos, indent=2)
        )
        return {
            "saved": len(todos),
            "file": str(_TODO_FILE),
        }
    except Exception as exc:
        return {"error": str(exc)}
