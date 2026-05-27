"""StarryLib — multi-agent AI library.

Public API — import everything you need from here::

    import starry_lib as sl

    settings = da.load_settings()
    async with da.AgentPool(settings) as pool:
        session = await pool.spawn(role="coder")
        async for event in session.chat("hello"):
            if event.type == "token":
                print(event.data, end="", flush=True)
"""

from starry_lib.agents.pool import AgentPool
from starry_lib.agents.session import Session
from starry_lib.agents.agent_config import (
    AgentConfig,
)
from starry_lib.config.settings import (
    AppSettings,
    MCPServerConfig,
    ProviderConfig,
    RoleConfig,
    load_settings,
)
from starry_lib.llm.client import (
    build_client,
    get_model_context_window,
    list_models,
)
from starry_lib.providers import (
    add_provider,
    get_default_paths,
    get_provider,
    list_providers,
    make_provider,
    probe_provider,
    remove_provider,
    set_active_provider,
    write_env_key,
)
from starry_lib.tools.registry import (
    build_mcp_servers,
    discover_entry_point_tools,
)
from starry_lib.tools.tool_loader import (
    get_tool_schemas,
    get_tool_executor,
)
from starry_lib.types import (
    AgentEvent,
    Message,
    SessionInfo,
)

__all__ = [
    # Config
    "AppSettings",
    "ProviderConfig",
    "RoleConfig",
    "AgentConfig",
    "MCPServerConfig",
    "load_settings",
    # Types
    "Message",
    "SessionInfo",
    "AgentEvent",
    # Single-agent
    "Session",
    # Multi-agent
    "AgentPool",
    # LLM
    "build_client",
    "list_models",
    "get_model_context_window",
    # Provider management
    "list_providers",
    "get_provider",
    "add_provider",
    "remove_provider",
    "set_active_provider",
    "get_default_paths",
    "make_provider",
    "probe_provider",
    "write_env_key",
    # Tools
    "build_mcp_servers",
    "discover_entry_point_tools",
    "get_tool_schemas",
    "get_tool_executor",
]
