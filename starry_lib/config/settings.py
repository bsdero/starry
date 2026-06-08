#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       settings.py
# DESCRIPTION: Settings models and loader for StarryLib
# SUMMARY: Pydantic models for config; load_settings reads TOML.
# NOTES: API keys are never stored in config; they come from
#        environment variables named in api_key_env.
#        ThemeConfig and UIConfig were removed — those are
#        CLI concerns, not library concerns.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/15/2026    bsdero          Remove ThemeConfig, UIConfig
"""Settings models and loader for StarryLib."""

import logging
import os
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]  # py<3.11
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from starry_lib.prompts.loader import load_role_prompt

log = logging.getLogger(__name__)


class ProviderConfig(BaseModel):
    """Configuration for one LLM provider profile.

    Two ways to supply the API key:
    - api_key_env: name of an environment variable (default,
      used for persistent config-file providers).
    - api_key_value: literal key stored in memory only, never
      written to disk. Set via make_provider() for transient
      custom providers. Takes precedence over api_key_env.
    """

    name: str
    base_url: str
    api_key_env: str = ""
    ssl_verify: bool | str = True
    default_model: str
    label: str = ""
    context_window: int | None = None
    fallback: str | None = None
    cost_per_1k_prompt: float | None = None
    cost_per_1k_completion: float | None = None
    # In-memory key — excluded from serialisation/TOML
    api_key_value: str | None = Field(
        default=None, exclude=True
    )

    @property
    def api_key(self) -> str:
        """Return the API key, preferring api_key_value."""
        if self.api_key_value:
            return self.api_key_value
        if not self.api_key_env:
            raise RuntimeError(
                f"Provider '{self.name}': no api_key_value "
                f"set and api_key_env is empty."
            )
        value = os.environ.get(self.api_key_env)
        if value is None:
            raise RuntimeError(
                f"Provider '{self.name}' requires env var "
                f"'{self.api_key_env}' but it is not set."
            )
        return value

    @property
    def ssl_verify_value(self) -> bool | str:
        """Resolve ssl_verify to a bool or absolute cert path."""
        if isinstance(self.ssl_verify, bool):
            return self.ssl_verify
        path = Path(self.ssl_verify).expanduser()
        if not path.is_absolute():
            root = _find_project_root()
            path = (root / path).resolve()
        if not path.exists():
            raise ValueError(
                f"Provider '{self.name}': ssl_verify cert "
                f"not found at '{path}'."
            )
        return str(path)


class RoleConfig(BaseModel):
    """Configuration for one agent role."""

    # ── Identity ──────────────────────────────────
    name: str
    label: str

    # ── Structured prompt composition ─────────────
    # If system_prompt is set it takes precedence
    # over the assembled structured fields.
    goal: str = ""
    backstory: str = ""
    constraints: list[str] = []
    output_format: str = ""
    system_prompt: str = ""

    # ── LLM parameters ────────────────────────────
    model_override: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None

    # ── Tool + skill scoping ──────────────────────
    # None = inherit from mode (current behaviour).
    # A list = explicit whitelist; [] = no tools.
    allowed_tools: list[str] | None = None
    denied_tools: list[str] = []
    allowed_skills: list[str] | None = None
    denied_skills: list[str] = []

    # ── Multi-agent routing ───────────────────────
    can_delegate_to: list[str] = []
    accepts_from: list[str] = []
    expertise: str = ""


class MCPServerConfig(BaseModel):
    """Configuration for one MCP server."""

    transport: str
    command: str = ""
    args: list[str] = []
    url: str = ""


class AppSettings(BaseModel):
    """Root settings object for StarryLib."""

    active_provider: str | None = None
    active_role: str = "assistant"
    history_file: str = "~/.local/starry/history"
    websearch_backend: str = "auto"
    websearch_max_results: int = 5
    context_format: str = "markdown"
    providers: dict[str, ProviderConfig] = {}
    agents: dict[str, RoleConfig]
    mcp_servers: dict[str, MCPServerConfig] = {}


from starry_lib.config.paths import (
    global_conf_dir,
    project_conf_dir,
)

_USER_CONFIG = global_conf_dir() / "config.toml"
_USER_ENV = global_conf_dir() / ".env"


def _find_project_root() -> Path:
    """Walk up from this file until config/default.toml found."""
    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "default.toml").exists():
            return candidate
    raise FileNotFoundError(
        "Cannot find 'config/default.toml' in any parent "
        "directory."
    )


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base; override values win."""
    result = dict(base)
    for key, val in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(val, dict)
        ):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_settings(
    config_path: Path | None = None,
) -> AppSettings:
    """Load and validate settings from TOML config files.

    Load order (later wins):
    1. Bundled config/default.toml
    2. ~/.local/starry/config.toml  (user config)

    When config_path is given it is used instead of step 1
    and user-config merging is skipped (test/override mode).
    """
    if config_path is not None:
        # Explicit path: single-file mode (tests / overrides)
        root = config_path.parent.parent
        env_file = root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        raw = tomllib.loads(config_path.read_text())
    else:
        # Normal startup: bundled defaults + user overlay
        root = _find_project_root()
        bundled = (
            root / "config" / "default.toml"
        )
        raw = tomllib.loads(bundled.read_text())

        if _USER_CONFIG.exists():
            user_raw = tomllib.loads(
                _USER_CONFIG.read_text()
            )
            raw = _deep_merge(raw, user_raw)

        # Project config layer (pwd/.starry/config.toml)
        _proj = project_conf_dir()
        if _proj is not None:
            _proj_cfg = _proj / "config.toml"
            if _proj_cfg.exists():
                proj_raw = tomllib.loads(
                    _proj_cfg.read_text()
                )
                raw = _deep_merge(raw, proj_raw)

        # Load env: project .env first, user .env wins
        proj_env = root / ".env"
        if proj_env.exists():
            load_dotenv(proj_env)
        if _USER_ENV.exists():
            load_dotenv(_USER_ENV, override=True)

        # Project .env wins over everything
        if _proj is not None:
            _proj_env = _proj / ".env"
            if _proj_env.exists():
                load_dotenv(_proj_env, override=True)

    # Flatten [app] keys into the top level
    app_block = raw.pop("app", {})
    raw.setdefault(
        "active_provider",
        app_block.get("active_provider"),
    )
    raw.setdefault(
        "active_role",
        app_block.get("active_role", "assistant"),
    )
    raw.setdefault(
        "history_file",
        app_block.get(
            "history_file", "~/.local/starry/history"
        ),
    )
    raw.setdefault(
        "context_format",
        app_block.get("context_format", "markdown"),
    )

    # Drop CLI-only sections
    raw.pop("theme", None)
    raw.pop("ui", None)

    # Inject name key into each provider and agent entry
    for key, entry in raw.get("providers", {}).items():
        entry["name"] = key
    for key, entry in raw.get("agents", {}).items():
        entry["name"] = key

    settings = AppSettings(**raw)

    # Fill system_prompt from roles/<name>.txt when absent
    for name, role_cfg in settings.agents.items():
        if not role_cfg.system_prompt:
            role_cfg.system_prompt = load_role_prompt(name)

    if (
        settings.active_provider is not None
        and settings.active_provider
        not in settings.providers
    ):
        raise ValueError(
            f"active_provider"
            f" '{settings.active_provider}'"
            f" is not defined in [providers]."
        )
    if settings.active_role not in settings.agents:
        raise ValueError(
            f"active_role '{settings.active_role}'"
            f" is not defined in [agents]."
        )

    role_names = set(settings.agents.keys())
    for rname, rcfg in settings.agents.items():
        for target in rcfg.can_delegate_to:
            if target not in role_names:
                log.warning(
                    "Role '%s': can_delegate_to '%s' "
                    "does not exist in [agents].",
                    rname,
                    target,
                )

    return settings


def get_active_provider() -> ProviderConfig:
    """Return the active ProviderConfig from default settings."""
    settings = load_settings()
    return settings.providers[settings.active_provider]


def get_active_agent() -> RoleConfig:
    """Return the active RoleConfig from default settings."""
    settings = load_settings()
    return settings.agents[settings.active_role]
