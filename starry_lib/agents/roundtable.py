#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       roundtable.py
# DESCRIPTION: Roundtable — shared multi-agent chat room
# SUMMARY: Maintains a shared transcript across agents
#          and broadcasts user messages to all of them.
# NOTES: Agents use session.chat() (no tools) so that
#        conversation stays clean and focused.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Roundtable: shared transcript + broadcast."""

from __future__ import annotations

from collections.abc import AsyncIterator

from starry_lib.types import AgentEvent


class Roundtable:
    """Shared chat room for user + multiple agents.

    Usage::

        rt = Roundtable(pool, {"alpha": "agent-alpha",
                               "beta":  "agent-beta"})
        async for event in rt.post("Hello everyone!"):
            print(event.type, event.data)
    """

    def __init__(
        self,
        pool: object,
        session_map: dict[str, str],
    ) -> None:
        """
        Args:
            pool: An AgentPool instance.
            session_map: Mapping of agent name to
                session_id.  Example:
                {"alpha": "agent-alpha"}.
        """
        self._pool = pool
        self._session_map: dict[str, str] = (
            dict(session_map)
        )
        self._sid_to_name: dict[str, str] = {
            sid: name
            for name, sid in session_map.items()
        }
        self._transcript: list[dict[str, str]] = []

    # ── Public properties ─────────────────────────

    @property
    def agent_names(self) -> list[str]:
        """Return names of all agents in the room."""
        return list(self._session_map.keys())

    @property
    def session_ids(self) -> list[str]:
        """Return session_ids of all agents."""
        return list(self._session_map.values())

    @property
    def transcript(self) -> list[dict[str, str]]:
        """Return the full shared transcript."""
        return self._transcript

    # ── Transcript helpers ────────────────────────

    def get_name_for_sid(
        self, sid: str
    ) -> str | None:
        """Return agent name for a session_id."""
        return self._sid_to_name.get(sid)

    def record_user(self, text: str) -> None:
        """Append a user turn to the transcript."""
        self._transcript.append(
            {"name": "You", "text": text}
        )

    def record_response(
        self, name: str, text: str
    ) -> None:
        """Append an agent response to transcript."""
        self._transcript.append(
            {"name": name, "text": text}
        )

    def format_context(
        self, limit: int = 10
    ) -> str:
        """Format the last `limit` transcript entries.

        Returns a string like:
            [You]: Hello
            [alpha]: Hi there!
        Returns an empty string if the transcript
        is empty.
        """
        recent = self._transcript[-limit:]
        if not recent:
            return ""
        return "\n".join(
            f"[{e['name']}]: {e['text']}"
            for e in recent
        )

    # ── Core broadcast ────────────────────────────

    async def post(
        self,
        user_text: str,
        target_name: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Broadcast user_text to agents or one target.

        Prepends conversation context to the prompt
        so agents can see what was said before.

        Args:
            user_text: The message to send.
            target_name: If given, send only to this
                agent. Otherwise send to all agents.

        Yields:
            AgentEvent objects with type "token",
            "done", or "error". Each event carries
            session_id so you can identify the agent.
        """
        ctx = self.format_context()
        if ctx:
            prompt = (
                "[Conversation context]\n"
                f"{ctx}\n\n{user_text}"
            )
        else:
            prompt = user_text

        if target_name is not None:
            sid = self._session_map.get(
                target_name
            )
            if sid is None:
                return
            session = self._pool.get(sid)
            async for event in session.chat(prompt):
                yield event
        else:
            async for event in (
                self._pool.broadcast(
                    prompt,
                    list(
                        self._session_map.values()
                    ),
                )
            ):
                yield event
