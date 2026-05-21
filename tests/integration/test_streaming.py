"""Integration tests for Session streaming via AgentEvents."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from starry_lib.agents.pool import AgentPool
from starry_lib.config.settings import load_settings
from starry_lib.providers import make_provider
from starry_lib.types import AgentEvent


@pytest.fixture
def settings(tmp_config):
    return load_settings(
        tmp_config / "config" / "default.toml"
    )


def _make_stream(*tokens: str):
    """Async generator yielding fake chat completion chunks."""

    async def _gen():
        for tok in tokens:
            delta = MagicMock()
            delta.content = tok
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            yield chunk

    return _gen()


# ── Session.chat() ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_yields_token_events(
    settings, monkeypatch
):
    """chat() yields one token event per LLM token."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()
    session._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("Hello", " world")
    )

    events = [e async for e in session.chat("hi")]
    tokens = [e for e in events if e.type == "token"]

    assert len(tokens) == 2
    assert tokens[0].data == "Hello"
    assert tokens[1].data == " world"


@pytest.mark.asyncio
async def test_chat_yields_done_event_with_full_text(
    settings, monkeypatch
):
    """chat() final event is done with assembled response."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()
    session._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("Hello", " world")
    )

    events = [e async for e in session.chat("hi")]
    done = [e for e in events if e.type == "done"]

    assert len(done) == 1
    assert done[0].data == "Hello world"


@pytest.mark.asyncio
async def test_chat_maintains_history(
    settings, monkeypatch
):
    """chat() appends user and assistant messages to history."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()
    session._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("reply")
    )

    async for _ in session.chat("first message"):
        pass

    history = session.get_history()
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "first message"
    assert history[1].role == "assistant"
    assert history[1].content == "reply"


@pytest.mark.asyncio
async def test_chat_history_included_in_next_call(
    settings, monkeypatch
):
    """chat() includes prior turns when building messages."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()
    session._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("first reply")
    )
    async for _ in session.chat("first"):
        pass

    session._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("second reply")
    )
    async for _ in session.chat("second"):
        pass

    call_kwargs = (
        session._client.chat.completions
        .create.call_args.kwargs
    )
    messages = call_kwargs.get("messages", [])
    roles = [m["role"] for m in messages]
    # system + user + assistant + user
    assert roles.count("user") == 2
    assert roles.count("assistant") == 1


@pytest.mark.asyncio
async def test_chat_complete_assembles_string(
    settings, monkeypatch
):
    """chat_complete() returns full response as a string."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()
    session._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("Hello", ", ", "world!")
    )

    result = await session.chat_complete("greet")
    assert result == "Hello, world!"


@pytest.mark.asyncio
async def test_chat_clear_history_resets(
    settings, monkeypatch
):
    """clear_history() removes all prior messages."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()
    session._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("r")
    )
    async for _ in session.chat("msg"):
        pass

    session.clear_history()
    assert session.get_history() == []


# ── Custom provider via make_provider() ──────────────────────────


@pytest.mark.asyncio
async def test_spawn_with_custom_provider_config(settings):
    """spawn() accepts a ProviderConfig object directly."""
    custom = make_provider(
        name="custom",
        base_url="http://custom-server/v1",
        api_key="my-token",
        model="custom-model",
    )
    pool = AgentPool(settings)
    session = await pool.spawn(provider=custom)

    assert session.info.provider == "custom"
    assert session._agent.model == "custom-model"


@pytest.mark.asyncio
async def test_spawn_custom_provider_uses_inline_key(
    settings,
):
    """Session built from make_provider() uses inline api_key."""
    custom = make_provider(
        name="mine",
        base_url="http://mine/v1",
        api_key="inline-secret",
        model="m",
    )
    pool = AgentPool(settings)
    session = await pool.spawn(provider=custom)

    assert (
        session._client.api_key == "inline-secret"
    )


# ── AgentPool multi-agent ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_yields_events_from_all_sessions(
    settings, monkeypatch
):
    """broadcast() multiplexes events from all sessions."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    s1 = await pool.spawn(session_id="s1")
    s2 = await pool.spawn(session_id="s2")
    s1._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("A")
    )
    s2._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("B")
    )

    events = [e async for e in pool.broadcast("test")]
    session_ids = {e.session_id for e in events}

    assert "s1" in session_ids
    assert "s2" in session_ids


@pytest.mark.asyncio
async def test_delegate_returns_per_session_responses(
    settings, monkeypatch
):
    """delegate() returns a response string per session."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    s1 = await pool.spawn(session_id="s1")
    s2 = await pool.spawn(session_id="s2")
    s1._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("ans1")
    )
    s2._client.chat.completions.create = AsyncMock(
        return_value=_make_stream("ans2")
    )

    results = await pool.delegate(
        {"s1": "prompt one", "s2": "prompt two"}
    )

    assert results["s1"] == "ans1"
    assert results["s2"] == "ans2"


@pytest.mark.asyncio
async def test_pipeline_chains_sessions_sequentially(
    settings, monkeypatch
):
    """pipeline() feeds each agent's output to the next."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    s1 = await pool.spawn(session_id="s1")
    s2 = await pool.spawn(session_id="s2")

    received: list[str] = []

    async def mock_create_s1(*a, **kw):
        received.append(
            kw["messages"][-1]["content"]
        )
        return _make_stream("step-one-output")

    async def mock_create_s2(*a, **kw):
        received.append(
            kw["messages"][-1]["content"]
        )
        return _make_stream("final-output")

    s1._client.chat.completions.create = mock_create_s1
    s2._client.chat.completions.create = mock_create_s2

    result = await pool.pipeline(
        ["s1", "s2"], "initial input"
    )

    assert received[0] == "initial input"
    assert received[1] == "step-one-output"
    assert result == "final-output"


# ── Session.chat_with_tools() ─────────────────────────────────────


def _make_tool_stream(
    call_id: str,
    fn_name: str,
    fn_args: dict,
):
    """Streaming response with one tool-call round."""
    async def _gen():
        tcd = MagicMock()
        tcd.index = 0
        tcd.id = call_id
        tcd.function = MagicMock()
        tcd.function.name = fn_name
        tcd.function.arguments = json.dumps(fn_args)

        delta = MagicMock()
        delta.content = None
        delta.tool_calls = [tcd]

        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = "tool_calls"

        chunk = MagicMock()
        chunk.choices = [choice]
        chunk.usage = None
        yield chunk

    return _gen()


def _make_text_stream(*tokens: str):
    """Streaming response yielding text tokens then stop."""
    async def _gen():
        last = len(tokens) - 1
        for i, tok in enumerate(tokens):
            delta = MagicMock()
            delta.content = tok
            delta.tool_calls = None

            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = (
                "stop" if i == last else None
            )

            chunk = MagicMock()
            chunk.choices = [choice]
            chunk.usage = None
            yield chunk

    return _gen()


@pytest.mark.asyncio
async def test_chat_with_tools_yields_tool_call_event(
    settings, monkeypatch
):
    """chat_with_tools() yields a tool_call event."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()

    session._client.chat.completions.create = AsyncMock(
        side_effect=[
            _make_tool_stream(
                "cid-1", "add", {"a": 1, "b": 2}
            ),
            _make_text_stream("3"),
        ]
    )

    events = [
        e async for e in session.chat_with_tools(
            "add 1 and 2",
            tools=[],
            tool_executor={"add": lambda a, b: a + b},
        )
    ]
    tc_events = [
        e for e in events if e.type == "tool_call"
    ]
    assert len(tc_events) == 1
    assert tc_events[0].data["name"] == "add"
    assert tc_events[0].data["args"] == {
        "a": 1, "b": 2
    }


@pytest.mark.asyncio
async def test_chat_with_tools_yields_tool_result_event(
    settings, monkeypatch
):
    """chat_with_tools() yields a tool_result event."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()

    session._client.chat.completions.create = AsyncMock(
        side_effect=[
            _make_tool_stream(
                "cid-2", "echo", {"msg": "hello"}
            ),
            _make_text_stream("done"),
        ]
    )

    events = [
        e async for e in session.chat_with_tools(
            "echo",
            tools=[],
            tool_executor={"echo": lambda msg: msg},
        )
    ]
    tr_events = [
        e for e in events if e.type == "tool_result"
    ]
    assert len(tr_events) == 1
    assert "hello" in tr_events[0].data["result"]


@pytest.mark.asyncio
async def test_chat_with_tools_yields_done_with_final(
    settings, monkeypatch
):
    """chat_with_tools() done event contains final answer."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()

    session._client.chat.completions.create = AsyncMock(
        side_effect=[
            _make_tool_stream("cid-3", "noop", {}),
            _make_text_stream("final answer"),
        ]
    )

    events = [
        e async for e in session.chat_with_tools(
            "go",
            tools=[],
            tool_executor={"noop": lambda: "ok"},
        )
    ]
    done_events = [
        e for e in events if e.type == "done"
    ]
    assert len(done_events) == 1
    assert done_events[0].data == "final answer"


@pytest.mark.asyncio
async def test_chat_with_tools_updates_history(
    settings, monkeypatch
):
    """chat_with_tools() appends user+assistant to history."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()

    session._client.chat.completions.create = AsyncMock(
        return_value=_make_text_stream("answer")
    )

    async for _ in session.chat_with_tools(
        "question",
        tools=[],
        tool_executor={},
    ):
        pass

    history = session.get_history()
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "question"
    assert history[1].role == "assistant"
    assert history[1].content == "answer"


@pytest.mark.asyncio
async def test_chat_with_tools_callable_executor(
    settings, monkeypatch
):
    """tool_executor can be a single dispatch callable."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()

    session._client.chat.completions.create = AsyncMock(
        side_effect=[
            _make_tool_stream(
                "cid-4", "ping", {"x": 99}
            ),
            _make_text_stream("pong"),
        ]
    )

    calls: list[tuple] = []

    def dispatcher(name: str, args: dict):
        calls.append((name, args))
        return {"dispatched": True}

    async for _ in session.chat_with_tools(
        "ping",
        tools=[],
        tool_executor=dispatcher,
    ):
        pass

    assert calls == [("ping", {"x": 99})]


@pytest.mark.asyncio
async def test_chat_with_tools_no_tools_needed(
    settings, monkeypatch
):
    """If model returns stop immediately, no tool events."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    pool = AgentPool(settings)
    session = await pool.spawn()

    session._client.chat.completions.create = AsyncMock(
        return_value=_make_text_stream("direct reply")
    )

    events = [
        e async for e in session.chat_with_tools(
            "no tools needed",
            tools=[],
            tool_executor={},
        )
    ]
    types = {e.type for e in events}
    assert "tool_call" not in types
    assert "tool_result" not in types
    assert "done" in types
