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
# 06/05/2026    bsdero          Add critic_role/max_retries
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
                "critic_role": {
                    "type": "string",
                    "description": (
                        "If set, a critic agent of "
                        "this role reviews the "
                        "result and triggers a "
                        "retry on FAIL. Omit to "
                        "skip review."
                    ),
                },
                "max_retries": {
                    "type": "integer",
                    "description": (
                        "Maximum retry attempts "
                        "after the first run. "
                        "Default 2."
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
    critic_role: str = "",
    max_retries: int = 2,
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
        if critic_role:
            result = (
                await _pool.run_subtask_with_review(
                    full_prompt,
                    role=subagent_type,
                    critic_role=critic_role,
                    max_retries=max_retries,
                    mode=mode,
                )
            )
        else:
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
