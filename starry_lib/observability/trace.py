#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       trace.py
# DESCRIPTION: Per-session structured execution tracer
# SUMMARY: TraceEntry dataclass and Tracer class.
#          Records llm_call, tool_call, tool_result
#          events with latency, token, and timestamp
#          metadata. Supports NDJSON export.
# NOTES: Attached to Session via self._tracer.
#        Access via session.trace property or
#        export via session.export_trace(path).
#
# BACKLOG:
# Date m/d/Y    Engineer    Summary
# 04/23/2026    bsdero    Initial implementation
"""Per-session execution tracer."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TraceEntry:
    turn: int
    type: str        # llm_call | tool_call | tool_result
    name: str | None = None
    args: dict[str, Any] | None = None
    result_preview: str | None = None
    latency_ms: int | None = None
    tokens_used: int | None = None
    timestamp: float = field(
        default_factory=time.time
    )


class Tracer:
    """Collects TraceEntry records for one session."""

    def __init__(self) -> None:
        self._entries: list[TraceEntry] = []

    def record(self, entry: TraceEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[TraceEntry]:
        return list(self._entries)

    def export(self, path: str) -> None:
        """Write entries as newline-delimited JSON."""
        with open(path, "w") as fh:
            for entry in self._entries:
                fh.write(
                    json.dumps(asdict(entry)) + "\n"
                )
