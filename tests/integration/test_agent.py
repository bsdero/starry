"""Integration tests for agents — base, roles, and orchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from starry_lib.config.settings import (
    load_settings,
    RoleConfig as AgentConfig,
)
from starry_lib.agents.base import BaseAgent
from starry_lib.agents.roles import build_agent
from starry_lib.agents.orchestrator import Orchestrator


@pytest.fixture
def settings(tmp_config):
    return load_settings(tmp_config / "config" / "default.toml")


@pytest.fixture
def role_cfg(settings):
    return settings.agents["assistant"]


@pytest.fixture
def provider_cfg(settings):
    return settings.providers["davy"]


# ── Test 1 ────────────────────────────────────────────────────────────


def test_build_agent_has_correct_system_prompt(
    role_cfg, provider_cfg
):
    """build_agent produces a BaseAgent with the correct system_prompt."""
    agent = build_agent(role_cfg, provider_cfg)
    assert isinstance(agent, BaseAgent)
    assert "helpful assistant" in agent.system_prompt


# ── Test 2 ────────────────────────────────────────────────────────────


def test_model_override_takes_precedence(provider_cfg):
    """model_override in role config overrides provider default_model."""
    role_cfg = AgentConfig(
        name="coder",
        label="Coder",
        system_prompt="You code.",
        tools=[],
        model_override="gpt-4o-mini",
    )
    agent = build_agent(role_cfg, provider_cfg)
    assert agent.model == "gpt-4o-mini"
    assert agent.model != provider_cfg.default_model


# ── Test 3 ────────────────────────────────────────────────────────────


def test_orchestrator_switch_role(settings, monkeypatch):
    """Orchestrator.switch_role changes the active role."""
    # Add a second role to settings so we can switch
    from starry_lib.config.settings import (
        RoleConfig as AgentConfig,
    )

    settings.agents["coder"] = AgentConfig(
        name="coder",
        label="Coder",
        system_prompt="You are a coder.",
        tools=[],
    )
    monkeypatch.setenv("STARRY_API_KEY", "test-key")

    orc = Orchestrator(settings)
    assert orc.active_role_label == "Assistant"

    orc.switch_role("coder")
    assert orc.active_role_label == "Coder"


# ── Test 4 ────────────────────────────────────────────────────────────


def test_orchestrator_switch_provider_rebuilds_client(
    settings, monkeypatch
):
    """Orchestrator.switch_provider rebuilds the client."""
    from starry_lib.config.settings import ProviderConfig

    settings.providers["openai"] = ProviderConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        ssl_verify=True,
        default_model="gpt-4o",
        label="OpenAI",
    )
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    orc = Orchestrator(settings)
    original_client = orc.client

    orc.switch_provider("openai")
    assert orc.client is not original_client


# ── Test 5 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_run_passes_user_input(
    settings, monkeypatch
):
    """Orchestrator.run passes user_input to the completions API."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    orc = Orchestrator(settings)

    # Build a mock streaming response with one chunk
    mock_delta = MagicMock()
    mock_delta.content = "hi"
    mock_choice = MagicMock()
    mock_choice.delta = mock_delta
    mock_chunk = MagicMock()
    mock_chunk.choices = [mock_choice]

    async def fake_aiter(*args, **kwargs):
        yield mock_chunk

    mock_stream = MagicMock()
    mock_stream.__aiter__ = fake_aiter

    mock_create = AsyncMock(return_value=mock_stream)
    orc.client.chat.completions.create = mock_create

    tokens = [t async for t in orc.run("say hello")]

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    # user_input should appear in the messages list
    messages = call_kwargs.get("messages", [])
    user_messages = [
        m for m in messages if m["role"] == "user"
    ]
    assert any("say hello" in m["content"] for m in user_messages)
    assert "".join(tokens) == "hi"
