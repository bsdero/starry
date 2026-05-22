#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       bash.py
# DESCRIPTION: Bash tool — executes shell commands
# SUMMARY: Runs a shell command via subprocess and returns
#          stdout, stderr, and the exit code.
# NOTES: Available in execution mode only.
#        timeout default: 30s. Runs in workdir if given.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    bsdero          Initial implementation
"""bash tool: execute shell commands."""

from __future__ import annotations

import subprocess

SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Execute a shell command and return "
            "stdout, stderr, and exit code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "Shell command to execute."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Timeout in seconds "
                        "(default 30)."
                    ),
                    "default": 30,
                },
                "workdir": {
                    "type": "string",
                    "description": (
                        "Working directory for "
                        "the command."
                    ),
                },
            },
            "required": ["command"],
        },
    },
}


def execute(
    command: str,
    timeout: int = 30,
    workdir: str | None = None,
) -> dict:
    """Run a shell command, return output dict."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "error": (
                f"Command timed out after "
                f"{timeout}s"
            )
        }
    except Exception as exc:
        return {"error": str(exc)}
