"""Unit tests for AgentPool.route() and delegate_auto()."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from starry_lib.agents.base import BaseAgent
from starry_lib.agents.pool import AgentPool
from starry_lib.agents.session import Session
from starry_lib.config.settings import (
    AppSettings,
    RoleConfig as AgentConfig,
)


def _make_agent(name: str, expertise: str = "") -> BaseAgent:
    return BaseAgent(
        name=name,
        label=name.capitalize(),
        system_prompt="",
        model="m",
        expertise=expertise,
    )


def _make_session(agent: BaseAgent) -> Session:
    return Session(
        session_id=f"s-{agent.name}",
        agent=agent,
        client=MagicMock(),
        provider_name="p",
        semaphore=asyncio.Semaphore(1),
        mode="execution",
    )


def _make_pool_with_sessions(
    sessions: list[Session],
    active_role: str = "assistant",
    routing_table: dict | None = None,
) -> AgentPool:
    settings = MagicMock(spec=AppSettings)
    settings.active_role = active_role
    settings.agents = {}
    settings.providers = {}
    pool = AgentPool.__new__(AgentPool)
    pool._settings = settings
    pool._sessions = {s.id: s for s in sessions}
    pool._routing_table = routing_table or {}
    return pool


# ── route() by can_delegate_to ────────────────────────────────────

@pytest.mark.asyncio
async def test_route_restricts_to_delegatable_roles():
    coder = _make_agent("coder", expertise="code python")
    researcher = _make_agent(
        "researcher", expertise="research"
    )
    sess_coder = _make_session(coder)
    sess_researcher = _make_session(researcher)

    pool = _make_pool_with_sessions(
        [sess_coder, sess_researcher],
        active_role="assistant",
        routing_table={"assistant": {"researcher"}},
    )

    result = await pool.route(
        "summarise the changelog", from_role="assistant"
    )
    assert result._agent.name == "researcher"


@pytest.mark.asyncio
async def test_route_falls_back_to_active_role():
    assistant = _make_agent("assistant", expertise="general")
    sess = _make_session(assistant)

    pool = _make_pool_with_sessions(
        [sess],
        active_role="assistant",
        routing_table={"assistant": {"coder"}},
    )

    # "coder" session doesn't exist → falls back to assistant
    result = await pool.route(
        "help me", from_role="assistant"
    )
    assert result._agent.name == "assistant"


@pytest.mark.asyncio
async def test_route_raises_when_no_session_for_active_role():
    coder = _make_agent("coder")
    sess = _make_session(coder)

    pool = _make_pool_with_sessions(
        [sess],
        active_role="assistant",  # no assistant session
        # from_role="assistant" can only delegate to nothing
        routing_table={"assistant": set()},
    )

    # Candidates are empty (assistant delegates to no one
    # and no assistant session exists for fallback)
    with pytest.raises(RuntimeError, match="assistant"):
        await pool.route("help", from_role="assistant")


@pytest.mark.asyncio
async def test_route_picks_best_by_expertise():
    coder = _make_agent("coder", expertise="python code")
    researcher = _make_agent(
        "researcher", expertise="research web data"
    )
    sess_coder = _make_session(coder)
    sess_researcher = _make_session(researcher)

    pool = _make_pool_with_sessions(
        [sess_coder, sess_researcher],
        active_role="coder",
        routing_table={},
    )

    result = await pool.route("research web")
    assert result._agent.name == "researcher"
