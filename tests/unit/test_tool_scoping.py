"""Unit tests for role-driven tool/skill scoping in Session."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from starry_lib.agents.base import BaseAgent
from starry_lib.agents.session import Session
from starry_lib.config.settings import (
    AppSettings,
    RoleConfig as AgentConfig,
)


def _make_agent(
    allowed_tools=None,
    denied_tools=None,
    allowed_skills=None,
    denied_skills=None,
) -> BaseAgent:
    return BaseAgent(
        name="test",
        label="Test",
        system_prompt="prompt",
        model="m",
        allowed_tools=allowed_tools,
        denied_tools=denied_tools or [],
        allowed_skills=allowed_skills,
        denied_skills=denied_skills or [],
    )


def _make_session(agent: BaseAgent) -> Session:
    import asyncio
    return Session(
        session_id="s1",
        agent=agent,
        client=MagicMock(),
        provider_name="p",
        semaphore=asyncio.Semaphore(1),
        mode="execution",
    )


# ── Tool permission init from agent ──────────────────────────────

def test_allowed_tools_initialised_from_agent():
    agent = _make_agent(allowed_tools=["bash", "read"])
    session = _make_session(agent)
    assert session.allowed_tools == ["bash", "read"]


def test_denied_tools_initialised_from_agent():
    agent = _make_agent(denied_tools=["bash"])
    session = _make_session(agent)
    assert session.denied_tools == ["bash"]


# ── _tool_permitted ───────────────────────────────────────────────

def test_allowed_tools_whitelist_blocks_others():
    agent = _make_agent(allowed_tools=["bash", "read"])
    session = _make_session(agent)
    assert session._tool_permitted("bash") is True
    assert session._tool_permitted("read") is True
    assert session._tool_permitted("write") is False
    assert session._tool_permitted("grep") is False


def test_denied_tools_removes_tool():
    agent = _make_agent(denied_tools=["bash"])
    session = _make_session(agent)
    assert session._tool_permitted("bash") is False
    assert session._tool_permitted("read") is True


# ── _skill_permitted ──────────────────────────────────────────────

def test_skill_allowed_when_no_restrictions():
    agent = _make_agent()
    session = _make_session(agent)
    assert session._skill_permitted("sys_info") is True
    assert session._skill_permitted("network_scan") is True


def test_skill_whitelist_blocks_others():
    agent = _make_agent(allowed_skills=["sys_info"])
    session = _make_session(agent)
    assert session._skill_permitted("sys_info") is True
    assert session._skill_permitted("network_scan") is False


def test_skill_denied_list_blocks_skill():
    agent = _make_agent(denied_skills=["network_scan"])
    session = _make_session(agent)
    assert session._skill_permitted("sys_info") is True
    assert session._skill_permitted("network_scan") is False


# ── switch_role updates filters ───────────────────────────────────

def test_switch_role_updates_tool_filters():
    agent = _make_agent(allowed_tools=None)
    session = _make_session(agent)
    assert session.allowed_tools is None

    settings = MagicMock(spec=AppSettings)
    new_role_cfg = AgentConfig(
        name="coder",
        label="Coder",
        allowed_tools=["bash", "read"],
        denied_tools=[],
    )
    provider_cfg = MagicMock()
    provider_cfg.default_model = "m"
    settings.agents = {"coder": new_role_cfg}
    settings.providers = {"p": provider_cfg}

    with patch(
        "starry_lib.agents.roles.build_agent"
    ) as mock_build:
        new_agent = _make_agent(
            allowed_tools=["bash", "read"]
        )
        mock_build.return_value = new_agent
        session.switch_role("coder", settings)

    assert session.allowed_tools == ["bash", "read"]
    assert session.denied_tools == []
