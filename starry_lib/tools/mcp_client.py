#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       mcp_client.py
# DESCRIPTION: Direct MCP client — no openai-agents SDK dep
# SUMMARY: Connects to stdio/http MCP servers using the
#          mcp package directly. Works on Python 3.11+.
#          Each discovered tool is returned as a SkillTool.
# NOTES: execute() reconnects per call (stateless model).
#        A failed server logs a warning and is skipped.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/21/2026    bsdero    Initial implementation
"""mcp_client: direct MCP server connection for SkillTools."""

from __future__ import annotations

import json
import logging
from typing import Any

from starry_lib.tools.skill_loader import SkillTool

log = logging.getLogger(__name__)


async def connect_mcp_server(cfg) -> list[SkillTool]:
    """Connect to one MCP server; return its tools.

    Parameters
    ----------
    cfg:
        MCPServerConfig with transport, command/args or url.

    Returns an empty list on any connection failure.
    """
    try:
        if cfg.transport == "stdio":
            return await _connect_stdio(cfg)
        if cfg.transport == "http":
            return await _connect_http(cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "MCP server connect failed: %s", exc
        )
        return []
    log.warning(
        "Unknown MCP transport %r; skipping.",
        cfg.transport,
    )
    return []


async def build_mcp_tools(settings) -> list[SkillTool]:
    """Build tools from all configured MCP servers.

    Parameters
    ----------
    settings:
        AppSettings instance.

    Returns a flat list of SkillTools from all servers.
    A misconfigured server logs a warning and is skipped.
    """
    if not settings.mcp_servers:
        return []
    tools: list[SkillTool] = []
    for name, cfg in settings.mcp_servers.items():
        try:
            server_tools = await connect_mcp_server(cfg)
            tools.extend(server_tools)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "MCP server %r failed: %s", name, exc
            )
    return tools


# ── stdio transport ───────────────────────────────────────


async def _connect_stdio(cfg) -> list[SkillTool]:
    try:
        from mcp import (  # type: ignore[import]
            ClientSession,
            StdioServerParameters,
        )
        from mcp.client.stdio import (  # type: ignore[import]
            stdio_client,
        )
    except ImportError:
        log.warning(
            "mcp package not available; "
            "stdio MCP tools disabled."
        )
        return []

    params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args,
    )
    try:
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr) as sess:
                await sess.initialize()
                res = await sess.list_tools()
                return [
                    _make_tool(t, cfg, "stdio")
                    for t in res.tools
                ]
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "stdio MCP connect failed: %s", exc
        )
        return []


# ── http transport ────────────────────────────────────────


async def _connect_http(cfg) -> list[SkillTool]:
    try:
        from mcp import (  # type: ignore[import]
            ClientSession,
        )
        from mcp.client.streamable_http import (  # type: ignore[import]
            streamablehttp_client,
        )
    except ImportError:
        log.warning(
            "mcp package not available; "
            "http MCP tools disabled."
        )
        return []

    try:
        async with streamablehttp_client(
            cfg.url
        ) as (rd, wr, _):
            async with ClientSession(rd, wr) as sess:
                await sess.initialize()
                res = await sess.list_tools()
                return [
                    _make_tool(t, cfg, "http")
                    for t in res.tools
                ]
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "http MCP connect failed: %s", exc
        )
        return []


# ── tool factory ──────────────────────────────────────────


def _make_tool(tool, cfg, transport: str) -> SkillTool:
    """Build a SkillTool from an MCP tool descriptor."""
    schema: dict = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": (
                tool.inputSchema
                if tool.inputSchema
                else {
                    "type": "object",
                    "properties": {},
                }
            ),
        },
    }
    _cfg = cfg
    _name = tool.name
    _transport = transport

    async def execute(**kwargs: Any) -> dict:
        return await _call_tool(
            _cfg, _transport, _name, kwargs
        )

    return SkillTool(SCHEMA=schema, execute=execute)


# ── per-call dispatch ─────────────────────────────────────


async def _call_tool(
    cfg,
    transport: str,
    name: str,
    kwargs: dict,
) -> dict:
    if transport == "stdio":
        return await _call_stdio(cfg, name, kwargs)
    if transport == "http":
        return await _call_http_tool(
            cfg, name, kwargs
        )
    return {"error": f"unknown transport: {transport}"}


async def _call_stdio(
    cfg, name: str, kwargs: dict
) -> dict:
    from mcp import (  # type: ignore[import]
        ClientSession,
        StdioServerParameters,
    )
    from mcp.client.stdio import (  # type: ignore[import]
        stdio_client,
    )

    params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args,
    )
    async with stdio_client(params) as (rd, wr):
        async with ClientSession(rd, wr) as sess:
            await sess.initialize()
            result = await sess.call_tool(name, kwargs)
            return _result_to_dict(result)


async def _call_http_tool(
    cfg, name: str, kwargs: dict
) -> dict:
    from mcp import (  # type: ignore[import]
        ClientSession,
    )
    from mcp.client.streamable_http import (  # type: ignore[import]
        streamablehttp_client,
    )

    async with streamablehttp_client(cfg.url) as (
        rd,
        wr,
        _,
    ):
        async with ClientSession(rd, wr) as sess:
            await sess.initialize()
            result = await sess.call_tool(name, kwargs)
            return _result_to_dict(result)


def _result_to_dict(result) -> dict:
    """Convert MCP CallToolResult to a plain dict."""
    texts: list[str] = []
    for item in result.content:
        if hasattr(item, "text"):
            texts.append(item.text)
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except (json.JSONDecodeError, ValueError):
            return {"result": texts[0]}
    return {"results": texts}
