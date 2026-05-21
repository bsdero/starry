"""MCP server registry for StarryLib.

Note: MCPServerStdio and MCPServerStreamableHttp come from the
openai-agents SDK (agents.mcp), which requires Python >=3.12.
On Python 3.11 this module returns an empty list; full MCP support
becomes available once running on Python 3.12+.
"""

from __future__ import annotations

import sys
import warnings

from starry_lib.config.settings import AppSettings


def build_mcp_servers(settings: AppSettings) -> list:
    """Build MCP server objects from config.

    Returns an empty list if the openai-agents SDK is unavailable
    (Python <3.12 environments). Emits a RuntimeWarning on
    Python 3.11 so callers are aware MCP is not active.
    """
    if not settings.mcp_servers:
        return []

    try:
        from agents.mcp import (  # type: ignore[import]
            MCPServerStdio,
            MCPServerStreamableHttp,
        )
    except Exception:
        if sys.version_info < (3, 12):
            warnings.warn(
                f"MCP support requires Python >=3.12. "
                f"Running {sys.version_info.major}."
                f"{sys.version_info.minor}. "
                "Upgrade to Python 3.12+ for MCP tools.",
                RuntimeWarning,
                stacklevel=2,
            )
        return []

    servers: list = []
    for _name, cfg in settings.mcp_servers.items():
        if cfg.transport == "stdio":
            servers.append(
                MCPServerStdio(
                    params={
                        "command": cfg.command,
                        "args": cfg.args,
                    },
                    cache_tools_list=True,
                )
            )
        elif cfg.transport == "http":
            servers.append(
                MCPServerStreamableHttp(
                    params={"url": cfg.url},
                    cache_tools_list=True,
                )
            )
    return servers


def discover_entry_point_tools() -> list:
    """Discover tools registered via Python entry points.

    Third-party packages register tools by adding to their
    pyproject.toml::

        [project.entry-points."starry_lib.tools"]
        my_tools = "my_package.tools:get_tools"

    Each entry point must point to a zero-argument callable
    that returns a list of tool objects compatible with the
    StarryLib tool protocol.

    Returns a flat list of all discovered tool objects.
    Silently skips entries that fail to load.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return []

    tools: list = []
    eps = entry_points(group="starry_lib.tools")
    for ep in eps:
        try:
            loader = ep.load()
            result = loader()
            if isinstance(result, list):
                tools.extend(result)
        except Exception:
            pass
    return tools
