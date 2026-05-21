"""Unit tests for starry_lib.providers."""

import pytest
from unittest.mock import patch

from starry_lib.config.settings import (
    ProviderConfig,
    load_settings,
)
from starry_lib.providers import (
    add_provider,
    get_provider,
    list_providers,
    make_provider,
    probe_provider,
    remove_provider,
    set_active_provider,
)


@pytest.fixture
def settings(tmp_config):
    return load_settings(
        tmp_config / "config" / "default.toml"
    )


@pytest.fixture
def cfg_path(tmp_config):
    return tmp_config / "config" / "default.toml"


# ── list_providers ────────────────────────────────────────────────


def test_list_providers_returns_all(settings):
    """list_providers returns one entry per configured provider."""
    result = list_providers(settings)
    assert len(result) == len(settings.providers)
    names = {p.name for p in result}
    assert "davy" in names
    assert "openwebui" in names


def test_list_providers_returns_provider_config(settings):
    """list_providers items are ProviderConfig instances."""
    for prov in list_providers(settings):
        assert isinstance(prov, ProviderConfig)


# ── get_provider ──────────────────────────────────────────────────


def test_get_provider_returns_correct_config(settings):
    """get_provider returns the matching ProviderConfig."""
    prov = get_provider(settings, "davy")
    assert prov.name == "davy"
    assert "davy.labs.lenovo.com" in prov.base_url


def test_get_provider_unknown_raises_key_error(settings):
    """get_provider raises KeyError for unknown name."""
    with pytest.raises(KeyError, match="nope"):
        get_provider(settings, "nope")


# ── set_active_provider ───────────────────────────────────────────


def test_set_active_provider_updates_toml(
    cfg_path, monkeypatch
):
    """set_active_provider writes the new name to the TOML file."""
    monkeypatch.setenv("OPENWEBUI_API_KEY", "test-key")
    set_active_provider(cfg_path, "openwebui")
    text = cfg_path.read_text()
    assert 'active_provider = "openwebui"' in text


def test_set_active_provider_reverts_to_original(
    cfg_path, monkeypatch
):
    """set_active_provider can set back to an existing provider."""
    monkeypatch.setenv("STARRY_API_KEY", "test-key")
    set_active_provider(cfg_path, "davy")
    text = cfg_path.read_text()
    assert 'active_provider = "davy"' in text


def test_set_active_provider_unknown_raises_key_error(
    cfg_path,
):
    """set_active_provider raises KeyError for unknown name."""
    with pytest.raises(KeyError, match="ghost"):
        set_active_provider(cfg_path, "ghost")


# ── add_provider ──────────────────────────────────────────────────


def test_add_provider_appends_block(cfg_path, monkeypatch):
    """add_provider appends a [providers.<name>] block."""
    monkeypatch.setenv("NEW_API_KEY", "key123")
    new_prov = ProviderConfig(
        name="newprov",
        base_url="http://new.example.com/v1",
        api_key_env="NEW_API_KEY",
        ssl_verify=True,
        default_model="some-model",
        label="New Provider",
    )
    add_provider(cfg_path, new_prov)
    text = cfg_path.read_text()
    assert "[providers.newprov]" in text
    assert "http://new.example.com/v1" in text
    assert 'default_model = "some-model"' in text


def test_add_provider_ssl_false_writes_toml_false(
    cfg_path, monkeypatch
):
    """add_provider writes ssl_verify = false for bool False."""
    monkeypatch.setenv("SKIP_API_KEY", "k")
    prov = ProviderConfig(
        name="skipssl",
        base_url="http://skipssl.example.com/v1",
        api_key_env="SKIP_API_KEY",
        ssl_verify=False,
        default_model="m",
        label="Skip SSL",
    )
    add_provider(cfg_path, prov)
    text = cfg_path.read_text()
    assert "ssl_verify    = false" in text


# ── remove_provider ───────────────────────────────────────────────


def test_remove_provider_deletes_block(cfg_path, monkeypatch):
    """remove_provider removes the provider block from TOML."""
    monkeypatch.setenv("TODEL_API_KEY", "k")
    extra = ProviderConfig(
        name="todel",
        base_url="http://todel.example.com/v1",
        api_key_env="TODEL_API_KEY",
        ssl_verify=False,
        default_model="m",
        label="To Delete",
    )
    add_provider(cfg_path, extra)
    assert "[providers.todel]" in cfg_path.read_text()

    remove_provider(cfg_path, "todel")
    assert "[providers.todel]" not in cfg_path.read_text()


def test_remove_provider_leaves_others_intact(
    cfg_path, monkeypatch
):
    """remove_provider does not affect other provider blocks."""
    monkeypatch.setenv("EXTRA_API_KEY", "k")
    extra = ProviderConfig(
        name="extra",
        base_url="http://extra.example.com/v1",
        api_key_env="EXTRA_API_KEY",
        ssl_verify=True,
        default_model="m",
        label="Extra",
    )
    add_provider(cfg_path, extra)
    remove_provider(cfg_path, "extra")
    text = cfg_path.read_text()
    assert "[providers.davy]" in text
    assert "[providers.openwebui]" in text


def test_remove_provider_unknown_raises_key_error(cfg_path):
    """remove_provider raises KeyError for unknown name."""
    with pytest.raises(KeyError, match="ghost"):
        remove_provider(cfg_path, "ghost")


# ── make_provider ────────────────────────────────────────────────


def test_make_provider_returns_provider_config():
    """make_provider returns a ProviderConfig instance."""
    prov = make_provider(
        name="custom",
        base_url="http://my-server/v1",
        api_key="my-token",
        model="llama-3",
    )
    assert isinstance(prov, ProviderConfig)
    assert prov.name == "custom"
    assert prov.base_url == "http://my-server/v1"
    assert prov.default_model == "llama-3"


def test_make_provider_api_key_readable():
    """make_provider stores the key so api_key property works."""
    prov = make_provider(
        name="custom",
        base_url="http://my-server/v1",
        api_key="secret-token",
        model="llama-3",
    )
    assert prov.api_key == "secret-token"


def test_make_provider_no_env_var_needed(monkeypatch):
    """make_provider works without a matching env var."""
    monkeypatch.delenv("CUSTOM_API_KEY", raising=False)
    prov = make_provider(
        name="custom",
        base_url="http://my-server/v1",
        api_key="token",
        model="m",
    )
    assert prov.api_key == "token"


def test_make_provider_label_defaults_to_name():
    """make_provider uses name as label when omitted."""
    prov = make_provider(
        name="myhost",
        base_url="http://x/v1",
        api_key="t",
        model="m",
    )
    assert prov.label == "myhost"


def test_make_provider_ssl_verify_false():
    """make_provider passes ssl_verify=False through."""
    prov = make_provider(
        name="insecure",
        base_url="http://x/v1",
        api_key="t",
        model="m",
        ssl_verify=False,
    )
    assert prov.ssl_verify is False


def test_make_provider_key_excluded_from_dump():
    """api_key_value is excluded from model serialisation."""
    prov = make_provider(
        name="custom",
        base_url="http://x/v1",
        api_key="secret",
        model="m",
    )
    dumped = prov.model_dump()
    assert "api_key_value" not in dumped
    assert "secret" not in str(dumped)


# ── probe_provider ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_test_provider_returns_model_list(settings):
    """test_provider returns models when provider responds."""

    async def fake_list(prov):
        return ["gemma-4-31b-it", "model-b"]

    with patch(
        "starry_lib.llm.client.list_models",
        side_effect=fake_list,
    ):
        models = await probe_provider(
            settings.providers["davy"]
        )
    assert "gemma-4-31b-it" in models


@pytest.mark.asyncio
async def test_test_provider_raises_on_empty(settings):
    """test_provider raises ConnectionError when no models returned."""

    async def fake_list(prov):
        return []

    with patch(
        "starry_lib.llm.client.list_models",
        side_effect=fake_list,
    ):
        with pytest.raises(ConnectionError, match="davy"):
            await probe_provider(settings.providers["davy"])
