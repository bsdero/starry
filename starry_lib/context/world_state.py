#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       world_state.py
# DESCRIPTION: Environment snapshot injected into every LLM call
# SUMMARY: build_world_state() returns a markdown block with date,
#          cwd, host, user, git branch/status, and OS version.
# NOTES: Git calls fail silently when outside a repo or when
#        git is not installed. Always call at request time, not
#        at session start, so cwd and time stay current.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/21/2026    bsdero    Initial implementation
"""World-state: ambient environment block for LLM context."""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone


def _git_info() -> str | None:
    """Return 'branch (status)' or None if outside a repo."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    try:
        dirty = subprocess.check_output(
            ["git", "status", "--short"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = "dirty" if dirty else "clean"
    except (subprocess.CalledProcessError, FileNotFoundError):
        status = "unknown"

    return f"{branch} ({status})"


def build_world_state() -> str:
    """Return a delimited environment block for system injection.

    Regenerate on every call so date, cwd, and git state
    reflect the actual moment of the LLM request.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M UTC")

    cwd = os.getcwd()
    host = socket.gethostname()
    user = os.environ.get("USER", os.environ.get("USERNAME", ""))
    os_ver = platform.platform(terse=True)
    py_ver = (
        f"Python {sys.version_info.major}"
        f".{sys.version_info.minor}"
        f".{sys.version_info.micro}"
    )

    lines = [
        "<environment>",
        f"date: {date_str}  time: {time_str}",
        f"cwd:  {cwd}",
        f"host: {host}  user: {user}",
    ]

    git = _git_info()
    if git:
        lines.append(f"git:  {git}")

    lines.append(f"os:   {os_ver}  {py_ver}")
    lines.append("</environment>")

    return "\n".join(lines)
