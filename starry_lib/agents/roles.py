#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       roles.py
# DESCRIPTION: Factory for building BaseAgent objects
# SUMMARY: build_agent() creates a BaseAgent from a
#          TOML RoleConfig + ProviderConfig.
#          build_agent_from_persistent() merges a
#          stored AgentConfig with its role's config.
# NOTES: Model resolution order (highest priority
#        first): AgentConfig.model →
#        RoleConfig.model_override →
#        ProviderConfig.default_model.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/15/2026    bsdero    Initial implementation
# 05/05/2026    bsdero    Add
#               build_agent_from_persistent
"""Factory for building BaseAgent instances from config."""

from __future__ import annotations

from starry_lib.agents.base import BaseAgent
from starry_lib.config.settings import (
    AppSettings,
    ProviderConfig,
    RoleConfig,
)


def build_agent(
    role_cfg: RoleConfig,
    provider_cfg: ProviderConfig,
) -> BaseAgent:
    """Create a BaseAgent from role and provider config.

    Model resolution: role_cfg.model_override takes
    precedence over provider_cfg.default_model.
    """
    model = (
        role_cfg.model_override
        or provider_cfg.default_model
    )
    return BaseAgent(
        name=role_cfg.name,
        label=role_cfg.label,
        system_prompt=role_cfg.system_prompt,
        goal=role_cfg.goal,
        backstory=role_cfg.backstory,
        constraints=role_cfg.constraints,
        output_format=role_cfg.output_format,
        model=model,
        temperature=role_cfg.temperature,
        max_tokens=role_cfg.max_tokens,
        top_p=role_cfg.top_p,
        allowed_tools=role_cfg.allowed_tools,
        denied_tools=role_cfg.denied_tools,
        allowed_skills=role_cfg.allowed_skills,
        denied_skills=role_cfg.denied_skills,
        can_delegate_to=role_cfg.can_delegate_to,
        expertise=role_cfg.expertise,
    )


def _merge_allowed(
    role_list: list[str] | None,
    agent_list: list[str],
) -> list[str] | None:
    """Compute union of two allow lists.

    None means 'inherit from mode'. Empty list
    means 'no tools allowed'. Two None values
    return None (inherit from mode).
    """
    if role_list is None and not agent_list:
        return None
    base = list(role_list) if role_list else []
    combined = list({*base, *agent_list})
    return combined if combined else None


def build_agent_from_persistent(
    agent_cfg,
    settings: AppSettings,
) -> tuple[BaseAgent, ProviderConfig]:
    """Build a BaseAgent from a persistent AgentConfig.

    Merges the referenced role's settings with the
    AgentConfig overrides:
    - system_prompt_addon appended to role prompt.
    - tool/skill allow lists: role ∪ agent (union).
    - deny lists: role ∪ agent (union; deny wins).
    - temperature: agent value > 0 overrides role.
    - model: agent value overrides role + provider.

    Returns (BaseAgent, ProviderConfig) so the caller
    can build a client from the provider.
    """
    role_cfg = settings.agents.get(agent_cfg.role)
    if role_cfg is None:
        raise KeyError(
            f"Role '{agent_cfg.role}' not found."
        )
    provider_cfg = settings.providers.get(
        agent_cfg.provider
    )
    if provider_cfg is None:
        raise KeyError(
            f"Provider '{agent_cfg.provider}'"
            " not found."
        )

    # Model resolution
    model = (
        agent_cfg.model
        or role_cfg.model_override
        or provider_cfg.default_model
    )

    # Merge system prompt
    base = (
        role_cfg.system_prompt.strip()
        if role_cfg.system_prompt.strip()
        else ""
    )
    addon = agent_cfg.system_prompt_addon.strip()
    if base and addon:
        system_prompt = base + "\n" + addon
    elif addon:
        system_prompt = addon
    else:
        system_prompt = base

    # Merge tool / skill lists
    allowed = _merge_allowed(
        role_cfg.allowed_tools,
        agent_cfg.allowed_tools,
    )
    denied = list({
        *list(role_cfg.denied_tools),
        *agent_cfg.denied_tools,
    })
    allowed_sk = _merge_allowed(
        role_cfg.allowed_skills,
        agent_cfg.allowed_skills,
    )
    denied_sk = list({
        *list(role_cfg.denied_skills or []),
        *agent_cfg.denied_skills,
    })

    # Temperature: agent > 0 overrides role
    temp = (
        agent_cfg.temperature
        if agent_cfg.temperature > 0.0
        else role_cfg.temperature
    )

    agent = BaseAgent(
        name=agent_cfg.name,
        label=agent_cfg.label,
        system_prompt=system_prompt,
        goal=(
            ""
            if system_prompt
            else role_cfg.goal
        ),
        backstory=role_cfg.backstory,
        constraints=list(role_cfg.constraints),
        output_format=role_cfg.output_format,
        model=model,
        temperature=temp,
        max_tokens=role_cfg.max_tokens,
        top_p=role_cfg.top_p,
        allowed_tools=allowed,
        denied_tools=denied,
        allowed_skills=allowed_sk,
        denied_skills=denied_sk,
        can_delegate_to=list(
            role_cfg.can_delegate_to
        ),
        expertise=role_cfg.expertise,
    )
    return agent, provider_cfg
