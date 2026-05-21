"""Unit tests for starry_lib.llm.client."""

import pytest
import httpx
from unittest.mock import patch
from openai import AsyncOpenAI

from starry_lib.config.settings import ProviderConfig
from starry_lib.llm.client import build_client


def _make_provider(**overrides) -> ProviderConfig:
    """Create a minimal ProviderConfig for testing."""
    defaults = {
        "name": "davy",
        "base_url": "https://davy.labs.lenovo.com:5000/v1",
        "api_key_env": "STARRY_API_KEY",
        "ssl_verify": True,
        "default_model": "gpt-oss-120b-thinking",
        "label": "DavyAI test",
    }
    defaults.update(overrides)
    return ProviderConfig(**defaults)


def test_build_client_returns_async_openai(monkeypatch):
    """build_client returns an AsyncOpenAI instance."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    provider = _make_provider()
    client = build_client(provider)
    assert isinstance(client, AsyncOpenAI)


def test_build_client_passes_base_url(monkeypatch):
    """build_client sets the correct base_url on the client."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    provider = _make_provider(
        base_url="https://davy.labs.lenovo.com:5000/v1"
    )
    client = build_client(provider)
    assert "davy.labs.lenovo.com" in str(client.base_url)


def test_build_client_non_true_ssl_uses_httpx_client(monkeypatch):
    """When ssl_verify is not True, an httpx.AsyncClient is passed.

    ssl_verify=False exercises the same code path as a cert path string
    without requiring a real certificate file. The cert-path variant is
    already covered by test_ssl_verify_cert_path_existing_file in
    test_config.py (ssl_verify_value resolution).
    """
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    provider = _make_provider(ssl_verify=False)
    client = build_client(provider)
    assert isinstance(client, AsyncOpenAI)
    # openai SDK stores the http_client as ._client
    assert isinstance(client._client, httpx.AsyncClient)


def test_build_client_ssl_true_no_custom_http_client(monkeypatch):
    """When ssl_verify=True, no custom http_client is passed."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    provider = _make_provider(ssl_verify=True)

    captured: dict = {}
    original = AsyncOpenAI.__init__

    def capturing_init(self, **kwargs):
        captured.update(kwargs)
        original(self, **kwargs)

    with patch.object(AsyncOpenAI, "__init__", capturing_init):
        build_client(provider)

    assert "http_client" not in captured


def test_build_client_missing_env_raises_runtime_error(monkeypatch):
    """Missing env var raises RuntimeError before client is built."""
    monkeypatch.delenv("STARRY_API_KEY", raising=False)
    provider = _make_provider()
    with pytest.raises(RuntimeError, match="STARRY_API_KEY"):
        build_client(provider)


def test_openwebui_base_url_results_in_correct_endpoint(monkeypatch):
    """OpenWebUI base_url 'http://host/api' is preserved on the client.

    The openai SDK appends /chat/completions to base_url, so setting
    base_url to 'http://host/api' makes requests go to
    'http://host/api/chat/completions' as required.
    """
    monkeypatch.setenv("OPENWEBUI_API_KEY", "test-key")
    provider = ProviderConfig(
        name="openwebui",
        base_url="http://lico1:8080/api",
        api_key_env="OPENWEBUI_API_KEY",
        ssl_verify=True,
        default_model="gpt-oss-120b-thinking",
        label="Open WebUI",
    )
    client = build_client(provider)
    assert "lico1:8080" in str(client.base_url)
    assert "/api" in str(client.base_url)
