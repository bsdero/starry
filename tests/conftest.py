"""Shared pytest fixtures for StarryLib tests."""

import pytest
from unittest.mock import AsyncMock
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

MINIMAL_TOML = """
[app]
active_provider = "davy"
active_role = "assistant"
history_file = "~/.local/starry/history"

[providers.davy]
base_url = "https://davy.labs.lenovo.com:5000/v1"
api_key_env = "STARRY_API_KEY"
ssl_verify = true
default_model = "gemma-4-31b-it"
label = "DavyAI test"

[providers.openwebui]
base_url = "http://lico1:8080/api"
api_key_env = "OPENWEBUI_API_KEY"
ssl_verify = true
default_model = "gemma-4-31b-it"
label = "Open WebUI test"

[agents.assistant]
label = "Assistant"
system_prompt = "You are a helpful assistant."
tools = []
"""


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Isolated config dir with minimal TOML and empty .env."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.toml").write_text(MINIMAL_TOML)
    (tmp_path / ".env").write_text(
        "STARRY_API_KEY=test-key\n"
        "OPENWEBUI_API_KEY=test-key\n"
    )
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    monkeypatch.setenv("OPENWEBUI_API_KEY", "test-key")
    return tmp_path


@pytest.fixture
def mock_completion():
    """A single non-streaming ChatCompletion mock."""
    return ChatCompletion(
        id="test-id",
        model="gemma-4-31b-it",
        object="chat.completion",
        created=0,
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage(
                    role="assistant",
                    content="Hello from mock",
                ),
            )
        ],
    )


@pytest.fixture
def mock_llm(mock_completion):
    """AsyncMock for AsyncCompletions.create."""
    mock = AsyncMock(return_value=mock_completion)
    return mock
