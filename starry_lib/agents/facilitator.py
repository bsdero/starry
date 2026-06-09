#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       facilitator.py
# DESCRIPTION: Facilitator — coordinator agent with
#              specialist delegation
# SUMMARY: One facilitator session receives user
#          messages and uses call_agent to delegate
#          subtasks to specialist agents.
# NOTES: Uses chat_auto() so call_agent tool is
#        available. TUI drives the session.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Facilitator: coordinator + specialist delegation."""

from __future__ import annotations

from collections.abc import AsyncIterator

from starry_lib.types import AgentEvent


class Facilitator:
    """Coordinator agent that delegates to specialists.

    One facilitator session receives user messages and
    uses the call_agent tool to route subtasks to named
    specialist agents, then synthesizes a reply.

    Usage::

        fac = Facilitator(
            pool,
            facilitator_name="coordinator",
            facilitator_sid="agent-coordinator",
            specialist_names=["researcher", "coder"],
        )
        async for event in fac.post("Help!"):
            print(event.type, event.data)
    """

    def __init__(
        self,
        pool: object,
        facilitator_name: str,
        facilitator_sid: str,
        specialist_names: list[str],
    ) -> None:
        self._pool = pool
        self._facilitator_name = facilitator_name
        self._facilitator_sid = facilitator_sid
        self._specialist_names = list(
            specialist_names
        )
        self._transcript: list[dict[str, str]] = []

    # ── Public properties ─────────────────────────

    @property
    def facilitator_name(self) -> str:
        """Name of the facilitator agent."""
        return self._facilitator_name

    @property
    def specialist_names(self) -> list[str]:
        """Names of all specialist agents."""
        return list(self._specialist_names)

    @property
    def all_agent_names(self) -> list[str]:
        """Facilitator name + specialist names."""
        return (
            [self._facilitator_name]
            + self._specialist_names
        )

    # ── Transcript helpers ────────────────────────

    def record_user(self, text: str) -> None:
        """Append a user message to the transcript."""
        self._transcript.append(
            {"name": "You", "text": text}
        )

    def record_response(self, text: str) -> None:
        """Append a facilitator reply to transcript."""
        self._transcript.append(
            {
                "name": self._facilitator_name,
                "text": text,
            }
        )

    def format_context(
        self, limit: int = 10
    ) -> str:
        """Format last `limit` transcript entries.

        Returns a string like:
            [You]: Hello
            [coordinator]: I'll look into that.
        Returns empty string if transcript is empty.
        """
        recent = self._transcript[-limit:]
        if not recent:
            return ""
        return "\n".join(
            f"[{e['name']}]: {e['text']}"
            for e in recent
        )

    async def summarize_positions(
        self,
    ) -> dict[str, str]:
        """Ask the facilitator to summarize session.

        Returns {facilitator_name: summary_text}.
        Does not record to transcript.
        Used by _continue_facilitator to re-seed
        the session after a history clear.
        """
        session = self._pool.get(
            self._facilitator_sid
        )
        prompt = (
            "In 2-3 sentences, summarize the key"
            " outcomes and decisions from this"
            " session. Be concise."
        )
        try:
            text = await session.chat_complete(
                prompt
            )
        except Exception:
            text = ""
        return {self._facilitator_name: text}

    # ── Core post ─────────────────────────────────

    async def post(
        self, user_text: str
    ) -> AsyncIterator[AgentEvent]:
        """Stream the facilitator response.

        Sends user_text to the facilitator session
        using chat_auto() (tool-enabled). Yields ALL
        event types: token, done, tool_call,
        tool_result, error.

        The TUI is responsible for rendering each
        event type appropriately.
        """
        session = self._pool.get(
            self._facilitator_sid
        )
        async for event in session.chat_auto(
            user_text
        ):
            yield event
