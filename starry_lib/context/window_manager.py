#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       window_manager.py
# DESCRIPTION: Context-window truncation for LLM message lists
# SUMMARY: truncate_messages() trims a message list to fit within
#          a token budget, preserving system prompts and recent turns.
# NOTES: Token count uses len(json.dumps(msg))//4 — a cheap
#        approximation that avoids the tiktoken dependency.
#        Truncation order: tool results first, then old
#        user/assistant turns, then hard content truncation.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/21/2026    ahernandez86    Initial implementation
"""Context-window manager: trim messages to fit a token budget."""

from __future__ import annotations

import json


def _token_estimate(msgs: list[dict]) -> int:
    """Cheap token approximation: JSON bytes / 4."""
    return len(json.dumps(msgs)) // 4


def truncate_messages(
    messages: list[dict],
    limit: int,
    model: str = "",  # reserved for future tiktoken use
) -> list[dict]:
    """Trim *messages* so the estimated token count is under *limit*.

    Strategy (applied in order until the list fits):
    1. Drop ``role="tool"`` entries oldest-first.
    2. Drop ``role="user"`` / ``role="assistant"`` turns
       oldest-first, always keeping system prompt(s) and
       the last 4 non-system messages.
    3. Hard-truncate the content of the oldest non-system
       message as a last resort.

    System messages are never dropped. Returns the original
    list unchanged when it already fits.
    """
    if _token_estimate(messages) <= limit:
        return messages

    msgs = list(messages)

    # Step 1: drop tool results oldest-first
    i = 0
    while i < len(msgs) and _token_estimate(msgs) > limit:
        if msgs[i].get("role") == "tool":
            msgs.pop(i)
        else:
            i += 1

    if _token_estimate(msgs) <= limit:
        return msgs

    # Separate system from non-system messages
    sys_msgs = [m for m in msgs if m.get("role") == "system"]
    non_sys = [m for m in msgs if m.get("role") != "system"]

    # Step 2: drop user/assistant turns oldest-first,
    # always keeping the last 4 non-system messages.
    while (
        len(non_sys) > 4
        and _token_estimate(sys_msgs + non_sys) > limit
    ):
        non_sys.pop(0)

    msgs = sys_msgs + non_sys
    if _token_estimate(msgs) <= limit:
        return msgs

    # Step 3: hard-truncate the oldest non-system message
    for idx, m in enumerate(msgs):
        if m.get("role") == "system":
            continue
        if _token_estimate(msgs) <= limit:
            break
        content = m.get("content") or ""
        # Trim by halving until it fits or hits 64 chars
        while (
            len(content) > 64
            and _token_estimate(msgs) > limit
        ):
            content = content[: len(content) // 2]
        msgs[idx] = {**m, "content": content}

    return msgs
