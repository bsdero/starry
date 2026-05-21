"""Unit tests for starry_lib.tools.mcp_client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from starry_lib.tools.mcp_client import (
    build_mcp_tools,
    connect_mcp_server,
)
from starry_lib.tools.skill_loader import SkillTool


def _make_cfg(transport="stdio", command="echo", args=None,
              url=""):
    cfg = MagicMock()
    cfg.transport = transport
    cfg.command = command
    cfg.args = args or []
    cfg.url = url
    return cfg


def _make_settings(servers=None):
    s = MagicMock()
    s.mcp_servers = servers or {}
    return s


class TestConnectMcpServer:
    @pytest.mark.asyncio
    async def test_unknown_transport_returns_empty(self):
        cfg = _make_cfg(transport="ftp")
        tools = await connect_mcp_server(cfg)
        assert tools == []

    @pytest.mark.asyncio
    async def test_stdio_import_error_returns_empty(self):
        cfg = _make_cfg(transport="stdio")
        with patch.dict(
            "sys.modules", {"mcp": None}
        ):
            tools = await connect_mcp_server(cfg)
        assert tools == []

    @pytest.mark.asyncio
    async def test_stdio_connection_error_returns_empty(
        self,
    ):
        cfg = _make_cfg(transport="stdio")

        async def _fail(*a, **k):
            raise ConnectionError("refused")

        with patch(
            "starry_lib.tools.mcp_client._connect_stdio",
            side_effect=_fail,
        ):
            tools = await connect_mcp_server(cfg)
        assert tools == []

    @pytest.mark.asyncio
    async def test_http_import_error_returns_empty(self):
        cfg = _make_cfg(
            transport="http", url="http://localhost"
        )
        with patch.dict(
            "sys.modules", {"mcp": None}
        ):
            tools = await connect_mcp_server(cfg)
        assert tools == []


class TestBuildMcpTools:
    @pytest.mark.asyncio
    async def test_no_servers_returns_empty(self):
        settings = _make_settings(servers={})
        tools = await build_mcp_tools(settings)
        assert tools == []

    @pytest.mark.asyncio
    async def test_failed_server_skipped(self):
        cfg = _make_cfg(transport="stdio")
        settings = _make_settings(
            servers={"srv": cfg}
        )
        with patch(
            "starry_lib.tools.mcp_client"
            ".connect_mcp_server",
            side_effect=RuntimeError("boom"),
        ):
            tools = await build_mcp_tools(settings)
        assert tools == []

    @pytest.mark.asyncio
    async def test_merges_tools_from_multiple_servers(
        self,
    ):
        t1 = MagicMock(spec=SkillTool)
        t2 = MagicMock(spec=SkillTool)

        async def _fake_connect(cfg):
            if cfg.transport == "stdio":
                return [t1]
            return [t2]

        cfg1 = _make_cfg(transport="stdio")
        cfg2 = _make_cfg(transport="http")
        settings = _make_settings(
            servers={"a": cfg1, "b": cfg2}
        )
        with patch(
            "starry_lib.tools.mcp_client"
            ".connect_mcp_server",
            side_effect=_fake_connect,
        ):
            tools = await build_mcp_tools(settings)
        assert t1 in tools
        assert t2 in tools
        assert len(tools) == 2
