"""Unit tests for starry_lib.config.settings."""

import pytest
from pathlib import Path

from starry_lib.config.settings import load_settings


def test_load_settings_parses_minimal_toml(tmp_config):
    """load_settings parses MINIMAL_TOML without error."""
    settings = load_settings(tmp_config / "config" / "default.toml")
    assert settings is not None


def test_active_provider_is_davy(tmp_config):
    """active_provider defaults to 'davy'."""
    settings = load_settings(tmp_config / "config" / "default.toml")
    assert settings.active_provider == "davy"


def test_provider_base_url(tmp_config):
    """providers['davy'].base_url is correct."""
    settings = load_settings(tmp_config / "config" / "default.toml")
    assert settings.providers["davy"].base_url == (
        "https://davy.labs.lenovo.com:5000/v1"
    )


def test_provider_api_key_reads_from_env(tmp_config, monkeypatch):
    """providers['davy'].api_key reads from the env var."""
    monkeypatch.setenv("STARRY_API_KEY", "my-secret")
    settings = load_settings(tmp_config / "config" / "default.toml")
    assert settings.providers["davy"].api_key == "my-secret"


def test_missing_env_var_raises_runtime_error(tmp_config, monkeypatch):
    """Missing env var raises RuntimeError with provider name."""
    settings = load_settings(tmp_config / "config" / "default.toml")
    monkeypatch.delenv("STARRY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="davy"):
        _ = settings.providers["davy"].api_key


def test_ssl_verify_true_returns_true(tmp_config):
    """ssl_verify = true -> ssl_verify_value returns True."""
    settings = load_settings(tmp_config / "config" / "default.toml")
    # MINIMAL_TOML has ssl_verify = true
    assert settings.providers["davy"].ssl_verify_value is True


def test_ssl_verify_false_returns_false(tmp_config):
    """ssl_verify = false -> ssl_verify_value returns False."""
    toml_text = (tmp_config / "config" / "default.toml").read_text()
    toml_text = toml_text.replace(
        "ssl_verify = true", "ssl_verify = false"
    )
    (tmp_config / "config" / "default.toml").write_text(toml_text)
    settings = load_settings(tmp_config / "config" / "default.toml")
    assert settings.providers["davy"].ssl_verify_value is False


def test_ssl_verify_cert_path_existing_file(tmp_config):
    """ssl_verify = path with existing file returns absolute path."""
    cert = tmp_config / "config" / "test.crt"
    cert.write_text("cert-data")
    toml_text = (tmp_config / "config" / "default.toml").read_text()
    toml_text = toml_text.replace(
        "ssl_verify = true",
        f'ssl_verify = "{cert}"',
    )
    (tmp_config / "config" / "default.toml").write_text(toml_text)
    settings = load_settings(tmp_config / "config" / "default.toml")
    result = settings.providers["davy"].ssl_verify_value
    assert isinstance(result, str)
    assert Path(result).is_absolute()
    assert Path(result).exists()


def test_ssl_verify_missing_cert_raises_value_error(tmp_config):
    """ssl_verify path to nonexistent file raises ValueError."""
    toml_text = (tmp_config / "config" / "default.toml").read_text()
    toml_text = toml_text.replace(
        "ssl_verify = true",
        'ssl_verify = "certs/missing.crt"',
    )
    (tmp_config / "config" / "default.toml").write_text(toml_text)
    settings = load_settings(tmp_config / "config" / "default.toml")
    with pytest.raises(ValueError):
        _ = settings.providers["davy"].ssl_verify_value


def test_unknown_active_provider_raises_value_error(tmp_config):
    """active_provider referencing nonexistent profile raises ValueError."""
    toml_text = (tmp_config / "config" / "default.toml").read_text()
    toml_text = toml_text.replace(
        'active_provider = "davy"',
        'active_provider = "nonexistent"',
    )
    (tmp_config / "config" / "default.toml").write_text(toml_text)
    with pytest.raises(ValueError, match="nonexistent"):
        load_settings(tmp_config / "config" / "default.toml")
