"""Unit tests for AgentConfig and BaseAgent prompt assembly."""

import pytest

from starry_lib.agents.base import BaseAgent
from starry_lib.config.settings import RoleConfig as AgentConfig


# ── AgentConfig field defaults ────────────────────────────────────

def test_agent_config_required_fields():
    cfg = AgentConfig(name="x", label="X")
    assert cfg.name == "x"
    assert cfg.label == "X"


def test_agent_config_new_fields_default():
    cfg = AgentConfig(name="x", label="X")
    assert cfg.goal == ""
    assert cfg.backstory == ""
    assert cfg.constraints == []
    assert cfg.output_format == ""
    assert cfg.system_prompt == ""
    assert cfg.temperature is None
    assert cfg.max_tokens is None
    assert cfg.top_p is None
    assert cfg.allowed_tools is None
    assert cfg.denied_tools == []
    assert cfg.allowed_skills is None
    assert cfg.denied_skills == []
    assert cfg.can_delegate_to == []
    assert cfg.accepts_from == []
    assert cfg.expertise == ""


def test_agent_config_model_override_default():
    cfg = AgentConfig(name="x", label="X")
    assert cfg.model_override is None


# ── effective_system_prompt assembly ─────────────────────────────

def _make_agent(**kwargs) -> BaseAgent:
    defaults = dict(
        name="test",
        label="Tester",
        system_prompt="",
        goal="",
        backstory="",
        constraints=[],
        output_format="",
        model="m",
    )
    defaults.update(kwargs)
    return BaseAgent(**defaults)


def test_prompt_verbatim_when_system_prompt_set():
    agent = _make_agent(
        system_prompt="My custom prompt.",
        goal="Ignored goal.",
    )
    assert agent.effective_system_prompt() == (
        "My custom prompt."
    )


def test_prompt_assembled_from_structured_fields():
    agent = _make_agent(
        goal="Do something useful.",
        backstory="Experienced engineer.",
        constraints=["Be concise.", "Use markdown."],
        output_format="Bullet list.",
    )
    prompt = agent.effective_system_prompt()
    assert "You are Tester." in prompt
    assert "Goal:" in prompt
    assert "Do something useful." in prompt
    assert "Background:" in prompt
    assert "Experienced engineer." in prompt
    assert "Constraints:" in prompt
    assert "- Be concise." in prompt
    assert "- Use markdown." in prompt
    assert "Output format:" in prompt
    assert "Bullet list." in prompt


def test_prompt_omits_empty_sections():
    agent = _make_agent(goal="Just a goal.")
    prompt = agent.effective_system_prompt()
    assert "Background:" not in prompt
    assert "Constraints:" not in prompt
    assert "Output format:" not in prompt
    assert "Goal:" in prompt
    assert "Just a goal." in prompt


def test_prompt_label_only_when_all_empty():
    agent = _make_agent()
    prompt = agent.effective_system_prompt()
    assert prompt == "You are Tester."


def test_prompt_system_prompt_whitespace_triggers_assembly():
    # Whitespace-only system_prompt counts as empty
    agent = _make_agent(
        system_prompt="   \n  ",
        goal="Active goal.",
    )
    prompt = agent.effective_system_prompt()
    assert "Goal:" in prompt
    assert "Active goal." in prompt
