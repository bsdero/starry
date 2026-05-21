"""Unit tests for Session._llm_kwargs()."""

import asyncio
from unittest.mock import MagicMock

import pytest

from starry_lib.agents.base import BaseAgent
from starry_lib.agents.session import Session


def _make_session(
    temperature=None,
    max_tokens=None,
    top_p=None,
) -> Session:
    agent = BaseAgent(
        name="test",
        label="Test",
        system_prompt="p",
        model="test-model",
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
    )
    return Session(
        session_id="s1",
        agent=agent,
        client=MagicMock(),
        provider_name="p",
        semaphore=asyncio.Semaphore(1),
        mode="execution",
    )


def test_llm_kwargs_always_has_model():
    session = _make_session()
    kw = session._llm_kwargs()
    assert kw["model"] == "test-model"


def test_llm_kwargs_omits_temperature_when_none():
    session = _make_session(temperature=None)
    assert "temperature" not in session._llm_kwargs()


def test_llm_kwargs_includes_temperature_when_set():
    session = _make_session(temperature=0.3)
    assert session._llm_kwargs()["temperature"] == 0.3


def test_llm_kwargs_omits_max_tokens_when_none():
    session = _make_session(max_tokens=None)
    assert "max_tokens" not in session._llm_kwargs()


def test_llm_kwargs_includes_max_tokens_when_set():
    session = _make_session(max_tokens=512)
    assert session._llm_kwargs()["max_tokens"] == 512


def test_llm_kwargs_omits_top_p_when_none():
    session = _make_session(top_p=None)
    assert "top_p" not in session._llm_kwargs()


def test_llm_kwargs_includes_top_p_when_set():
    session = _make_session(top_p=0.9)
    assert session._llm_kwargs()["top_p"] == 0.9


def test_llm_kwargs_all_params():
    session = _make_session(
        temperature=0.5,
        max_tokens=1024,
        top_p=0.95,
    )
    kw = session._llm_kwargs()
    assert kw == {
        "model": "test-model",
        "temperature": 0.5,
        "max_tokens": 1024,
        "top_p": 0.95,
    }
