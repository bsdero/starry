"""Base agent dataclass for StarryLib."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from starry_lib.context.world_state import build_world_state

log = logging.getLogger(__name__)

_PROMPT_WARN_CHARS = 8000


@dataclass
class BaseAgent:
    """Holds the configuration for one agent role."""

    name: str
    label: str
    system_prompt: str
    goal: str = ""
    backstory: str = ""
    constraints: list[str] = field(default_factory=list)
    output_format: str = ""
    tools: list = field(default_factory=list)
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] = field(default_factory=list)
    allowed_skills: list[str] | None = None
    denied_skills: list[str] = field(default_factory=list)
    can_delegate_to: list[str] = field(
        default_factory=list
    )
    expertise: str = ""

    def effective_system_prompt(self) -> str:
        """Return the assembled or overridden prompt.

        If system_prompt is non-empty it is used verbatim.
        Otherwise the prompt is assembled from structured
        fields, omitting sections whose values are empty.
        """
        if self.system_prompt.strip():
            return self.system_prompt.strip()

        parts: list[str] = [f"You are {self.label}."]

        if self.goal.strip():
            parts.append(
                f"\nGoal:\n{self.goal.strip()}"
            )

        if self.backstory.strip():
            parts.append(
                f"\nBackground:\n{self.backstory.strip()}"
            )

        if self.constraints:
            lines = "\n".join(
                f"- {c}" for c in self.constraints
            )
            parts.append(f"\nConstraints:\n{lines}")

        if self.output_format.strip():
            parts.append(
                f"\nOutput format:\n"
                f"{self.output_format.strip()}"
            )

        prompt = "\n".join(parts)
        if len(prompt) > _PROMPT_WARN_CHARS:
            log.warning(
                "Role '%s': assembled system prompt "
                "exceeds 8000 chars (%d). "
                "Consider using system_prompt directly.",
                self.name,
                len(prompt),
            )
        return prompt

    def build_messages(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Return the message list for a chat completion call.

        Args:
            user_input: The current user message.
            history: Prior turns as role/content dicts,
                     excluding the system prompt.
        """
        msgs: list[dict[str, str]] = [
            {
                "role": "system",
                "content": self.effective_system_prompt(),
            },
            {
                "role": "system",
                "content": build_world_state(),
            },
        ]
        if history:
            msgs.extend(history)
        msgs.append({"role": "user", "content": user_input})
        return msgs
