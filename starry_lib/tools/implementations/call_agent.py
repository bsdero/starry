#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       call_agent.py
# DESCRIPTION: Tool — send a message to a named agent
# SUMMARY: Spawns the agent if not already active,
#          acquires its per-agent lock, sends the
#          message via chat_auto(), and returns the
#          full response string to the LLM.
# NOTES: Execution mode only.
#        call set_context() at startup.
#        context arg is only injected on first call
#        (when the session has no history yet).
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 05/05/2026    bsdero    Initial implementation
# 06/05/2026    bsdero    Add critic_role/max_retries
"""call_agent tool."""

from __future__ import annotations

from pydantic import BaseModel


class _CriticVerdict(BaseModel):
    verdict: str  # "PASS" or "FAIL"
    feedback: str


_registry = None
_pool = None
_settings = None
_on_log = None  # callable(name, direction, text)


def set_context(
    registry,
    pool,
    settings,
    on_log=None,
) -> None:
    """Inject runtime dependencies at startup."""
    global _registry, _pool, _settings, _on_log
    _registry = registry
    _pool = pool
    _settings = settings
    _on_log = on_log


SCHEMA = {
    "type": "function",
    "function": {
        "name": "call_agent",
        "description": (
            "Send a message to a named persistent "
            "agent. The agent is spawned if not "
            "already active and keeps state across "
            "calls. Returns the agent's full "
            "response."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Name of the agent to call."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": (
                        "Message to send to the "
                        "agent."
                    ),
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Optional context injected "
                        "as a system message before "
                        "the first turn only."
                    ),
                },
                "critic_role": {
                    "type": "string",
                    "description": (
                        "If set, a critic agent of "
                        "this role reviews the "
                        "response and sends a "
                        "revision request to the "
                        "agent on FAIL. Omit to "
                        "skip review."
                    ),
                },
                "max_retries": {
                    "type": "integer",
                    "description": (
                        "Maximum revision cycles. "
                        "Default 2."
                    ),
                },
            },
            "required": ["name", "message"],
        },
    },
}


async def execute(
    name: str,
    message: str,
    context: str = "",
    critic_role: str = "",
    max_retries: int = 2,
) -> str:
    """Call the named agent and return its reply."""
    if _registry is None or _pool is None:
        return (
            "Error: agent runtime not initialized."
        )

    session = _registry.get_session(name)
    if session is None:
        try:
            session = await _registry.spawn_agent(
                name, _pool, _settings
            )
        except KeyError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Error spawning agent: {exc}"

    lock = _registry.get_lock(name)
    if lock is None:
        return f"Error: no lock for '{name}'."

    async with lock:
        is_first = (
            len(session.get_history()) == 0
        )
        if context and is_first:
            session.inject_system_message(
                f"[Context]\n{context}"
            )

        if _on_log:
            _on_log(name, "LLM→agent", message)

        response = ""
        async for event in session.chat_auto(
            message
        ):
            if event.type == "done":
                response = str(event.data)
                break
            if event.type == "error":
                response = (
                    f"[error] {event.data}"
                )
                break

        if _on_log:
            _on_log(name, "agent→LLM", response)

        if critic_role:
            for _ in range(max_retries):
                critic = None
                passed = True
                fb = ""
                try:
                    critic = await _pool.spawn(
                        role=critic_role,
                        mode="plan",
                    )
                    cp = (
                        "ORIGINAL TASK:\n"
                        f"{message}\n\n"
                        "AGENT RESPONSE:\n"
                        f"{response}"
                    )
                    verdict = (
                        await critic.chat_structured(
                            cp, _CriticVerdict
                        )
                    )
                    passed = (
                        verdict.verdict.upper()
                        == "PASS"
                    )
                    fb = verdict.feedback
                except Exception:
                    pass
                finally:
                    if critic is not None:
                        await _pool.terminate(
                            critic.id
                        )
                if passed:
                    break
                followup = (
                    "[Revision requested]\n"
                    f"{fb}\n\n"
                    "Please revise your response."
                )
                if _on_log:
                    _on_log(
                        name, "LLM→agent", followup
                    )
                response = ""
                async for event in (
                    session.chat_auto(followup)
                ):
                    if event.type == "done":
                        response = str(event.data)
                        break
                    if event.type == "error":
                        response = (
                            f"[error] {event.data}"
                        )
                        break
                if _on_log:
                    _on_log(
                        name, "agent→LLM", response
                    )

        return response or "[no response]"
