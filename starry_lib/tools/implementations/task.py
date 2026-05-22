#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       task.py
# DESCRIPTION: Task tool — launch autonomous subagents
# SUMMARY: Returns a subagent_request dict for the runtime
#          (AgentPool) to dispatch. Actual spawning is
#          handled by the caller after inspecting the result.
# NOTES: Available in plan and execution modes.
#        subagent_type must match an agents key in config.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    bsdero          Initial implementation
"""task tool: launch autonomous subagents."""

from __future__ import annotations

_pool = None


def set_pool(pool: object) -> None:
    """Inject the active AgentPool at startup."""
    global _pool
    _pool = pool

SCHEMA = {
    "type": "function",
    "function": {
        "name": "task",
        "description": (
            "Launch an autonomous subagent to "
            "handle a specific task. The subagent "
            "runs independently and returns its "
            "result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subagent_type": {
                    "type": "string",
                    "description": (
                        "Role of the subagent to "
                        "launch: assistant, coder, "
                        "sysadmin, researcher, "
                        "manager, reviewer, "
                        "integrator, or tester."
                    ),
                    "enum": [
                        "assistant",
                        "coder",
                        "sysadmin",
                        "researcher",
                        "manager",
                        "reviewer",
                        "integrator",
                        "tester",
                    ],
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "Task prompt for the "
                        "subagent."
                    ),
                },
                "command": {
                    "type": "string",
                    "description": (
                        "Optional shell command "
                        "for the subagent context."
                    ),
                },
                "task_id": {
                    "type": "string",
                    "description": (
                        "Optional task identifier."
                    ),
                },
            },
            "required": ["subagent_type"],
        },
    },
}


async def execute(
    subagent_type: str,
    prompt: str = "",
    command: str = "",
    task_id: str = "",
    mode: str = "execution",
) -> dict:
    """Run a subagent via AgentPool and return
    its response. Falls back to a stub dict if
    no pool is available.
    """
    tid = task_id or f"task_{abs(hash(prompt))}"
    if _pool is None:
        return {
            "type": "error",
            "task_id": tid,
            "message": "AgentPool not available",
        }
    full_prompt = prompt
    if command:
        full_prompt = (
            f"{prompt}\n\nCommand: {command}"
        )
    try:
        result = await _pool.run_subtask(
            full_prompt,
            role=subagent_type,
            mode=mode,
        )
        return {
            "type": "subagent_result",
            "task_id": tid,
            "result": result,
        }
    except Exception as exc:
        return {
            "type": "error",
            "task_id": tid,
            "message": str(exc),
        }
