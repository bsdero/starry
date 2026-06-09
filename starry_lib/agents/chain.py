#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       chain.py
# DESCRIPTION: Chain — sequential multi-agent pipeline
# SUMMARY: Agents work in order; each agent output
#          becomes the next agent input.
# NOTES: The TUI drives execution stage-by-stage.
#        Chain has no run() method. Use get_session()
#        and record_stage() from the TUI.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Chain: sequential multi-agent pipeline."""

from __future__ import annotations

import asyncio


class Chain:
    """Sequential agent pipeline.

    The TUI calls get_session(idx) to get the Session
    for a stage, streams it, and records the output
    with record_stage(). This design lets checkpoint
    menus pause execution between stages.

    Usage::

        chain = Chain(
            pool,
            agents=[
                ("writer", "agent-writer"),
                ("editor", "agent-editor"),
            ],
        )
        # Stage 0:
        session = chain.get_session(0)
        # stream session.chat(task) ...
        chain.record_stage("writer", output)
        # Stage 1:
        session = chain.get_session(1)
        # stream session.chat(output) ...
        chain.record_stage("editor", final)
    """

    def __init__(
        self,
        pool: object,
        agents: list[tuple[str, str]],
    ) -> None:
        """
        Args:
            pool: An AgentPool instance.
            agents: Ordered list of (name, session_id)
                pairs. Chain runs in this order.
        """
        self._pool = pool
        self._agents: list[tuple[str, str]] = (
            list(agents)
        )
        self._transcript: list[dict[str, str]] = []
        self._stage_outputs: list[str] = []

    # ── Public properties ─────────────────────────

    @property
    def agent_names(self) -> list[str]:
        """Ordered list of agent names."""
        return [n for n, _ in self._agents]

    @property
    def agents(self) -> list[tuple[str, str]]:
        """Ordered (name, session_id) pairs."""
        return list(self._agents)

    @property
    def stage_count(self) -> int:
        """Total number of stages in the chain."""
        return len(self._agents)

    # ── Stage accessors ───────────────────────────

    def get_session(self, idx: int):
        """Return Session for stage idx, or None."""
        if 0 <= idx < len(self._agents):
            _, sid = self._agents[idx]
            return self._pool.get(sid)
        return None

    def get_name(self, idx: int) -> str | None:
        """Return agent name for stage idx."""
        if 0 <= idx < len(self._agents):
            return self._agents[idx][0]
        return None

    def get_sid(self, idx: int) -> str | None:
        """Return session_id for stage idx."""
        if 0 <= idx < len(self._agents):
            return self._agents[idx][1]
        return None

    # ── Transcript helpers ────────────────────────

    def record_stage(
        self, name: str, text: str
    ) -> None:
        """Record a completed stage output.

        Call this after each stage's done event.
        The text is also stored in _stage_outputs
        (indexed by insertion order = stage order).
        """
        self._transcript.append(
            {"name": name, "text": text}
        )
        self._stage_outputs.append(text)

    def format_context(
        self, limit: int = 10
    ) -> str:
        """Format last `limit` transcript entries.

        Returns a string like:
            [writer]: Draft content here.
            [editor]: Revised content here.
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
        """Ask each agent for a 2-3 sentence summary.

        Concurrent chat_complete() calls. Returns
        {name: summary_text}. Does not touch
        transcript. Used by _continue_chain to
        re-seed sessions after history clear.
        """
        prompt = (
            "In 2-3 sentences, summarize your"
            " contribution and the key output"
            " you produced. Be concise."
        )

        async def _one(name, sid):
            session = self._pool.get(sid)
            try:
                text = await session.chat_complete(
                    prompt
                )
            except Exception:
                text = ""
            return name, text

        results = await asyncio.gather(
            *[
                _one(name, sid)
                for name, sid in self._agents
            ]
        )
        return dict(results)
