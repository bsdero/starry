#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       providers.py
# DESCRIPTION: Provider management — pure library functions
# SUMMARY: CRUD operations for LLM provider profiles stored
#          in a TOML config file. No UI dependencies.
# NOTES: TOML editing is regex-based to preserve comments
#        and formatting in the original file.
#        The caller is responsible for writing API keys to
#        .env before or after add_provider().
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/15/2026    bsdero          Extracted from cli/commands/provider
"""Provider management — pure business logic, no UI."""

from __future__ import annotations

import re
from pathlib import Path

from starry_lib.config.settings import (
    AppSettings,
    ProviderConfig,
    load_settings,
)


# ── Transient provider factory ────────────────────────────────────


def make_provider(
    name: str,
    base_url: str,
    api_key: str,
    model: str,
    ssl_verify: bool | str = True,
    label: str = "",
) -> ProviderConfig:
    """Create a transient ProviderConfig without a config file.

    The API key is held in memory only — it is never written
    to disk or injected into environment variables.

    Use this when a user supplies their own endpoint, model,
    and token at runtime, without persisting the provider.

    Args:
        name:       Identifier for this provider instance.
        base_url:   OpenAI-compatible API endpoint URL.
        api_key:    API token / bearer key.
        model:      Default model ID to use.
        ssl_verify: True, False (skip), or path to a cert.
        label:      Human-readable name (defaults to name).

    Returns:
        A ProviderConfig ready to pass to AgentPool.spawn()
        or Session.switch_provider().

    Example::

        import starry_lib as da

        custom = da.make_provider(
            name="mine",
            base_url="http://my-server:8080/v1",
            api_key="my-token",
            model="llama-3.1-8b",
        )
        async with da.AgentPool(settings) as pool:
            s = await pool.spawn(provider=custom)
    """
    return ProviderConfig(
        name=name,
        base_url=base_url,
        api_key_env="",
        api_key_value=api_key,
        ssl_verify=ssl_verify,
        default_model=model,
        label=label or name,
    )


# ── Read operations ───────────────────────────────────────────────


def list_providers(
    settings: AppSettings,
) -> list[ProviderConfig]:
    """Return all configured provider profiles."""
    return list(settings.providers.values())


def get_provider(
    settings: AppSettings, name: str
) -> ProviderConfig:
    """Return a provider profile by name.

    Raises:
        KeyError: if name is not found in settings.
    """
    if name not in settings.providers:
        raise KeyError(f"Provider '{name}' not found.")
    return settings.providers[name]


# ── Write operations ──────────────────────────────────────────────


def set_active_provider(
    config_path: Path, name: str
) -> None:
    """Set active_provider in the TOML config file.

    Raises:
        KeyError: if name is not a configured provider.
    """
    settings = load_settings(config_path)
    if name not in settings.providers:
        raise KeyError(f"Provider '{name}' not found.")
    text = config_path.read_text(encoding="utf-8")
    text = _set_app_value(text, "active_provider", name)
    config_path.write_text(text, encoding="utf-8")


def add_provider(
    config_path: Path, cfg: ProviderConfig
) -> None:
    """Append a new [providers.<name>] block to the TOML file.

    The caller is responsible for writing the API key to .env
    before or after calling this function.
    """
    ssl_val = _ssl_toml_value(cfg.ssl_verify)
    block = (
        f"\n[providers.{cfg.name}]\n"
        f'base_url      = "{cfg.base_url}"\n'
        f'api_key_env   = "{cfg.api_key_env}"\n'
        f"ssl_verify    = {ssl_val}\n"
        f'default_model = "{cfg.default_model}"\n'
        f'label         = "{cfg.label}"\n'
    )
    existing = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        existing + block, encoding="utf-8"
    )


def remove_provider(
    config_path: Path, name: str
) -> None:
    """Remove a [providers.<name>] block from the TOML file.

    Raises:
        KeyError: if name is not a configured provider.
    """
    settings = load_settings(config_path)
    if name not in settings.providers:
        raise KeyError(f"Provider '{name}' not found.")
    text = config_path.read_text(encoding="utf-8")
    text = re.sub(
        r"\[providers\."
        + re.escape(name)
        + r"\][^\[]*",
        "",
        text,
        flags=re.DOTALL,
    )
    config_path.write_text(text, encoding="utf-8")


# ── Connectivity ──────────────────────────────────────────────────


async def probe_provider(cfg: ProviderConfig) -> list[str]:
    """Probe provider connectivity by listing available models.

    Returns:
        Sorted list of model IDs.

    Raises:
        ConnectionError: if the provider returns no models.
    """
    from starry_lib.llm.client import list_models

    models = await list_models(cfg)
    if not models:
        raise ConnectionError(
            f"Provider '{cfg.name}' returned no models "
            f"(connection failed or endpoint misconfigured)."
        )
    return models


# ── Internal helpers ──────────────────────────────────────────────


def _set_app_value(
    toml_text: str, key: str, value: str
) -> str:
    """Replace key = "..." in the [app] section of a TOML string."""
    pattern = (
        r"(\[app\][^\[]*?"
        + re.escape(key)
        + r'\s*=\s*)"[^"]*"'
    )
    new_text, n = re.subn(
        pattern,
        rf'\g<1>"{value}"',
        toml_text,
        flags=re.DOTALL,
    )
    if n == 0:
        new_text = re.sub(
            r"(\[app\])",
            rf'\1\n{key} = "{value}"',
            toml_text,
        )
    return new_text


def get_default_paths() -> tuple[Path, Path]:
    """Return (config_path, env_path) for the
    user config layout at ~/.local/starry/.

    Returns:
        (~/.local/starry/config.toml,
         ~/.local/starry/.env) as Paths.
    """
    base = Path.home() / ".local" / "starry"
    base.mkdir(parents=True, exist_ok=True)
    return (
        base / "config.toml",
        base / ".env",
    )


def write_env_key(
    env_path: Path, key: str, value: str
) -> None:
    """Write or update KEY=value in an .env file.

    Creates the file if it does not exist.
    Replaces the existing line if the key is
    already present; otherwise appends.
    """
    if env_path.exists():
        lines = env_path.read_text(
            encoding="utf-8"
        ).splitlines(keepends=True)
    else:
        lines = []

    pattern = re.compile(
        r"^" + re.escape(key) + r"\s*="
    )
    replaced = False
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}\n"
            replaced = True
            break
    if not replaced:
        if lines and not lines[-1].endswith(
            "\n"
        ):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")

    env_path.write_text(
        "".join(lines), encoding="utf-8"
    )


def _ssl_toml_value(ssl_verify: bool | str) -> str:
    """Render ssl_verify as a TOML literal."""
    if isinstance(ssl_verify, bool):
        return "true" if ssl_verify else "false"
    return f'"{ssl_verify}"'
