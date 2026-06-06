#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       debate.py
# DESCRIPTION: Debate — turn-based multi-agent debate engine
# SUMMARY: Agents speak in round-robin order for a fixed
#          number of rounds. User can inject messages
#          between turns via inject().
# NOTES: Agents use session.chat() (no tools) so that
#        debate turns stay clean and focused.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Debate: turn-based multi-agent structured debate."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from starry_lib.types import AgentEvent


class Debate:
    """Turn-based multi-agent debate engine.

    Agents speak in round-robin order for a fixed
    number of rounds. User can inject messages
    between turns via inject().

    Usage::

        debate = Debate(
            pool,
            [("alpha", "agent-alpha"),
             ("beta",  "agent-beta")],
            topic="Is Python better than Rust?",
            rounds=2,
        )
        async for event in debate.run():
            print(event.session_id, event.data)
    """

    def __init__(
        self,
        pool: object,
        agents: list[tuple[str, str]],
        topic: str,
        rounds: int = 3,
    ) -> None:
        """
        Args:
            pool: An AgentPool instance.
            agents: Ordered list of (name, session_id)
                pairs. Example:
                [("alpha", "agent-alpha"),
                 ("beta",  "agent-beta")].
            topic: The debate topic string.
            rounds: How many full cycles through all
                agents (one cycle = every agent speaks
                once). Minimum 1.
        """
        self._pool = pool
        self._agents: list[tuple[str, str]] = (
            list(agents)
        )
        self._topic = topic
        self._rounds = max(1, rounds)
        self._transcript: list[dict[str, str]] = []
        self._injection_queue: asyncio.Queue = (
            asyncio.Queue()
        )

    # ── Public properties ─────────────────────────

    @property
    def agent_names(self) -> list[str]:
        """Ordered list of participant names."""
        return [name for name, _ in self._agents]

    @property
    def session_ids(self) -> list[str]:
        """Ordered list of session_ids."""
        return [sid for _, sid in self._agents]

    # ── Transcript helpers ────────────────────────

    def record_turn(
        self, name: str, text: str
    ) -> None:
        """Append an agent turn to the transcript."""
        self._transcript.append(
            {"name": name, "text": text}
        )

    def record_user(self, text: str) -> None:
        """Append a user injection to transcript."""
        self._transcript.append(
            {"name": "You", "text": text}
        )

    def format_context(
        self, limit: int = 10
    ) -> str:
        """Format last `limit` transcript entries.

        Returns a string like:
            [alpha]: Hello
            [beta]: Hi there!
        Returns empty string if transcript is empty.
        """
        recent = self._transcript[-limit:]
        if not recent:
            return ""
        return "\n".join(
            f"[{e['name']}]: {e['text']}"
            for e in recent
        )

    def inject(self, text: str) -> None:
        """Queue a user message for the next turn.

        The message will be prepended to the next
        agent's prompt as [User]: text.
        """
        self._injection_queue.put_nowait(text)

    def get_name_for_sid(
        self, sid: str
    ) -> str | None:
        """Return agent name for a session_id."""
        for name, s in self._agents:
            if s == sid:
                return name
        return None

    # ── Main debate loop ──────────────────────────

    async def run(
        self,
    ) -> AsyncIterator[AgentEvent]:
        """Run the full debate and yield AgentEvents.

        Yields token and done events per turn, then
        a final sentinel when all rounds are complete.
        The sentinel has type="done",
        data="__debate_complete__", session_id="".

        Each non-sentinel done event carries the
        session_id of the agent that just spoke, so
        the TUI can label the output.
        """
        n = len(self._agents)
        total_turns = self._rounds * n

        # Seed each agent with context about the debate
        names_str = ", ".join(self.agent_names)
        seed = (
            f"You are participating in a structured"
            f" debate on: {self._topic}. "
            f"Other participants: {names_str}. "
            f"Argue your perspective clearly and"
            f" respond to what others say."
        )
        for name, sid in self._agents:
            session = self._pool.get(sid)
            session.inject_system_message(seed)

        for turn_index in range(total_turns):
            name, sid = self._agents[turn_index % n]
            session = self._pool.get(sid)

            # Check for user injection (non-blocking)
            injection = None
            try:
                injection = (
                    self._injection_queue.get_nowait()
                )
            except asyncio.QueueEmpty:
                pass

            # Build the prompt for this turn
            if turn_index == 0:
                base = (
                    f"Open the debate on:"
                    f" {self._topic}"
                )
            else:
                ctx = self.format_context()
                base = (
                    f"[Conversation so far]\n"
                    f"{ctx}\n\n"
                    f"Now give your response."
                )

            if injection is not None:
                prompt = (
                    f"[User]: {injection}\n\n{base}"
                )
                self.record_user(injection)
            else:
                prompt = base

            # Stream this agent's turn
            accumulated = ""
            async for event in session.chat(prompt):
                if event.type == "token":
                    accumulated += str(event.data)
                    yield event
                elif event.type == "done":
                    full = (
                        str(event.data) or accumulated
                    )
                    self.record_turn(name, full)
                    yield AgentEvent(
                        type="done",
                        session_id=sid,
                        data=full,
                    )
                elif event.type == "error":
                    yield event

        # Final sentinel — signals debate is complete
        yield AgentEvent(
            type="done",
            session_id="",
            data="__debate_complete__",
        )
