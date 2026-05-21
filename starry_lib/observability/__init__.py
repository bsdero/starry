#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       __init__.py
# DESCRIPTION: starry_lib.observability package
# SUMMARY: Exports Tracer and TraceEntry.
# NOTES: --
#
# BACKLOG:
# Date m/d/Y    Engineer    Summary
# 04/23/2026    ahernandez86    Initial implementation
"""starry_lib.observability — per-session tracing."""

from starry_lib.observability.trace import (
    Tracer,
    TraceEntry,
)

__all__ = ["Tracer", "TraceEntry"]
