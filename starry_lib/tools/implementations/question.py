#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       question.py
# DESCRIPTION: Question tool — request user input
# SUMMARY: Returns the question list as a structured dict
#          signaling the caller (TUI/CLI) that user input
#          is required. Actual collection is done by the
#          presentation layer.
# NOTES: Available in plan and execution modes.
#        Returns type="user_input_required" for the TUI.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    ahernandez86          Initial implementation
"""question tool: request user input interactively."""

from __future__ import annotations

SCHEMA = {
    "type": "function",
    "function": {
        "name": "question",
        "description": (
            "Ask the user one or more questions "
            "and wait for their responses. Use "
            "when clarification is needed before "
            "proceeding."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": (
                        "List of questions to "
                        "present to the user."
                    ),
                    "items": {"type": "string"},
                },
            },
            "required": ["questions"],
        },
    },
}


def execute(questions: list) -> dict:
    """
    Signal the presentation layer that user input
    is required. The TUI handles actual collection.
    """
    return {
        "type": "user_input_required",
        "questions": questions,
    }
