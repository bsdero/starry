# StarryLib — Library API Manual

## Table of contents

1. [Installation and setup](#1-installation-and-setup)
2. [Configuration](#2-configuration)
3. [Settings API](#3-settings-api)
4. [LLM client](#4-llm-client)
5. [Provider management](#5-provider-management)
6. [Session — single-agent conversations](#6-session--single-agent-conversations)
7. [AgentPool — multi-agent orchestration](#7-agentpool--multi-agent-orchestration)
8. [Tool calling](#8-tool-calling)
   - [8.1 Native tools](#81-native-tools)
   - [8.2 Execution modes](#82-execution-modes)
   - [8.3 Custom / manual tools](#83-custom--manual-tools)
9. [Event types](#9-event-types)
10. [Data types](#10-data-types)
11. [MCP tool servers and third-party tools](#11-mcp-tool-servers-and-third-party-tools)
12. [Configuration reference](#12-configuration-reference)
13. [Named agent system](#13-named-agent-system)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Installation and setup

### Install

```bash
pip install -e ".[dev]"          # developer / editable
pip install starry-lib            # production (once published)
```

Requires **Python 3.11+**.

### API keys

Copy `.env.example` to `.env` and fill in your keys:

```
STARRY_API_KEY=your-api-key
OPENWEBUI_API_KEY=sk-your-key
```

Keys are read at runtime from the environment variables named in
`api_key_env` inside each provider block. They are never written to
TOML.

### TLS certificate *(DavyAI only)*

```bash
cp davy.labs.lenovo.com.crt certs/
```

---

## 2. Configuration

All persistent settings live in `config/default.toml`.

```toml
[app]
active_provider = "davy"         # default provider
active_role     = "assistant"    # default agent role
history_file    = "~/.local/starry/history"

[providers.davy]
base_url      = "https://davy.labs.lenovo.com:5000/v1"
api_key_env   = "STARRY_API_KEY"
ssl_verify    = "certs/davy.labs.lenovo.com.crt"
default_model = "gemma-4-31b-it"
label         = "DavyAI (Lenovo)"

[providers.openwebui]
base_url      = "http://lico1:8080/api"
api_key_env   = "OPENWEBUI_API_KEY"
ssl_verify    = true
default_model = "gpt-oss-120b-thinking"
label         = "Open WebUI (lico1)"

[agents.assistant]
label         = "Assistant"
system_prompt = "You are a helpful general-purpose assistant."
tools         = []

[agents.coder]
label         = "Coder"
system_prompt = "You are an expert software engineer…"
tools         = []
```

---

## 3. Settings API

### `load_settings(config_path=None) -> AppSettings`

Load configuration from TOML. If `config_path` is `None`, the library
walks up from its own `__file__` until it finds `config/default.toml`.

```python
import starry_lib as sl

settings = sl.load_settings()
settings = sl.load_settings("/path/to/my.toml")
```

### `AppSettings` fields

| Field | Type | Description |
|-------|------|-------------|
| `active_provider` | `str` | Name of the default provider |
| `active_role` | `str` | Name of the default agent role |
| `history_file` | `str` | Path for CLI history (unused by library) |
| `providers` | `dict[str, ProviderConfig]` | All configured providers |
| `agents` | `dict[str, AgentConfig]` | All configured agent roles |
| `mcp_servers` | `dict[str, MCPServerConfig]` | Configured MCP servers |

### `ProviderConfig` fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Profile key (e.g. `"davy"`) |
| `base_url` | `str` | OpenAI-compatible API base URL |
| `api_key_env` | `str` | Env var name holding the API key |
| `ssl_verify` | `bool \| str` | `True`, `False`, or cert path |
| `default_model` | `str` | Model used unless overridden |
| `label` | `str` | Human-readable display name |
| `api_key` *(property)* | `str` | Reads key from env (raises `RuntimeError` if unset) |
| `ssl_verify_value` *(property)* | `bool \| str` | Resolved, validated SSL setting |

### Role config fields (TOML `[agents.*]`)

These are the **role templates** defined in `config/default.toml`.
They are distinct from the `AgentConfig` persistence dataclass used
by the named agent system (see §13).

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Role key (e.g. `"coder"`) |
| `label` | `str` | Display name |
| `system_prompt` | `str` | Instructions sent as the system message |
| `tools` | `list[str]` | Reserved for future use |
| `model_override` | `str \| None` | Override provider's `default_model` |

---

## 4. LLM client

### `build_client(provider: ProviderConfig) -> AsyncOpenAI`

Build an `AsyncOpenAI` client pre-configured with the provider's
base URL, API key, and SSL settings.

```python
from starry_lib.llm.client import build_client

client = build_client(settings.providers["davy"])
response = await client.chat.completions.create(
    model="gemma-4-31b-it",
    messages=[{"role": "user", "content": "hi"}],
)
```

### `list_models(provider: ProviderConfig) -> list[str]`

Return a sorted list of model IDs from `GET {base_url}/models`.
Returns `[]` on any error; never raises.

```python
from starry_lib.llm.client import list_models

models = await list_models(settings.providers["davy"])
# ["gemma-4-31b-it", "llama3", …]
```

---

## 5. Provider management

All functions are importable from `starry_lib` directly.

### `list_providers(settings) -> list[ProviderConfig]`

Return all configured providers in settings order as
`ProviderConfig` objects.

```python
providers = sl.list_providers(settings)
for cfg in providers:
    print(cfg.name, cfg.label)
# davy      DavyAI (Lenovo)
# openwebui Open WebUI (lico1)
```

### `get_provider(settings, name) -> ProviderConfig`

Return one provider config. Raises `KeyError` if not found.

```python
cfg = sl.get_provider(settings, "davy")
```

### `set_active_provider(config_path, name) -> None`

Update `active_provider` in the TOML file. Raises `KeyError` if
`name` is not an existing provider.

```python
sl.set_active_provider("~/.local/starry/config.toml", "openwebui")
```

### `add_provider(config_path, cfg: ProviderConfig) -> None`

Append a new `[providers.<name>]` block to the TOML file.

```python
cfg = sl.make_provider(
    name="local",
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    model="llama3",
)
sl.add_provider("~/.local/starry/config.toml", cfg)
```

### `remove_provider(config_path, name) -> None`

Remove a provider block from the TOML file. Raises `KeyError` if
not found.

```python
sl.remove_provider("~/.local/starry/config.toml", "local")
```

### `make_provider(name, base_url, api_key, model, ssl_verify=True, label="") -> ProviderConfig`

Create a **transient** provider that holds its API key in memory.
The key is never read from or written to any env var or file.
Useful for runtime-configured providers without touching `.env`.

```python
custom = sl.make_provider(
    name="mycloud",
    base_url="https://my-llm.example.com/v1",
    api_key="secret-token",
    model="my-model-7b",
    ssl_verify=True,
    label="My Cloud LLM",
)
session = await pool.spawn(provider=custom)
```

### `probe_provider(cfg: ProviderConfig) -> list[str]`

Test connectivity and return the list of available models.
Raises `RuntimeError` if unreachable or the model list is empty.

```python
models = await sl.probe_provider(settings.providers["davy"])
```

---

## 6. Session — single-agent conversations

Obtain a `Session` via `AgentPool.spawn()` rather than constructing
directly.

### `session.chat(user_input) -> AsyncIterator[AgentEvent]`

Stream a response token by token. Conversation history is maintained
automatically.

```python
async for event in session.chat("Explain Python asyncio."):
    if event.type == "token":
        print(event.data, end="", flush=True)
    elif event.type == "done":
        full_response = event.data
    elif event.type == "error":
        print("Error:", event.data)
```

Events yielded (in order):

| Event type | `data` | Description |
|-----------|--------|-------------|
| `"token"` | `str` | One chunk of streamed text |
| `"done"` | `str` | Full assembled response |
| `"error"` | `str` | Error message; no `done` follows |

### `session.chat_complete(user_input) -> str`

Convenience wrapper. Collects all tokens and returns the full
response string.

```python
reply = await session.chat_complete("What is 2 + 2?")
```

### `session.chat_with_tools(user_input, tools, tool_executor) -> AsyncIterator[AgentEvent]`

Streaming turn with OpenAI function-calling support. Runs the
full multi-round tool-call loop and yields events for each step,
including streamed text tokens as they arrive.

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"}
            },
            "required": ["city"],
        },
    },
}]

async for event in session.chat_with_tools(
    "What is the weather in Paris?",
    tools=TOOLS,
    tool_executor={"get_weather": my_weather_fn},
):
    if event.type == "tool_call":
        print("→ calling", event.data["name"],
              "with", event.data["args"])
    elif event.type == "tool_result":
        print("← result:", event.data["result"])
    elif event.type == "done":
        print("answer:", event.data)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tools` | `list[dict]` | Tool schemas (OpenAI function format) |
| `tool_executor` | `dict[str, Callable]` or `Callable[[str, dict], Any]` | Tool implementations. As a dict: maps function name → callable. As a single callable: receives `(name, args)` and dispatches. |

Events yielded:

| Event type | `data` | Description |
|-----------|--------|-------------|
| `"tool_call"` | `{"id", "name", "args"}` | Model requested a tool |
| `"tool_result"` | `{"id", "name", "result"}` | Tool executed; JSON result |
| `"done"` | `str` | Final model answer |
| `"error"` | `str` | Error; no `done` follows |

### `session.inject_system_message(content) -> None`

Append a system-role message to conversation history without
triggering a new LLM turn. Used to inform the session of
external state changes (e.g. a named agent being terminated).

```python
session.inject_system_message(
    '[System] Agent "researcher" has been terminated.'
)
```

### `session.get_history() -> list[Message]`

Return a copy of the conversation history.

```python
for msg in session.get_history():
    print(msg.role, msg.content[:60])
```

### `session.clear_history() -> None`

Reset conversation history. Does not affect the LLM client or agent.

### `session.switch_role(role, settings) -> None`

Rebuild the agent with a different role. History is preserved.

```python
session.switch_role("coder", settings)
```

### `session.switch_provider(provider, settings) -> None`

Rebuild the client with a different provider. Accepts a provider
name (str) or a `ProviderConfig` object from `make_provider()`.
History is preserved.

```python
session.switch_provider("openwebui", settings)
session.switch_provider(custom_cfg, settings)
```

### `session.mode` property

Get or set the session execution mode. Accepted values:
`"plan"` (read-only research) or `"execution"` (full
read/write/run). Raises `ValueError` for unknown modes.

```python
session.mode = "plan"       # research only
session.mode = "execution"  # full capabilities
print(session.mode)         # "execution"
```

### `session.get_tool_schemas() -> list[dict]`

Return the OpenAI function-calling schemas for all tools
available in the current mode. Equivalent to
`sl.get_tool_schemas(session.mode)`.

### `session.get_tool_executor() -> dict[str, Callable]`

Return a name → callable map for all tools available in
the current mode. Equivalent to
`sl.get_tool_executor(session.mode)`.

### `session.chat_auto(user_input) -> AsyncIterator[AgentEvent]`

Auto-selects the right chat method based on the current
mode. If the mode has tools configured (always true for
`"plan"` and `"execution"`), calls `chat_with_tools()`
with the auto-selected schemas and executor. Otherwise
falls back to `chat()`.

This is the recommended method for the TUI and most
application code.

```python
session.mode = "execution"
async for event in session.chat_auto("List Python files here."):
    if event.type == "token":
        print(event.data, end="", flush=True)
    elif event.type == "tool_call":
        print(f"\n[tool] {event.data['name']}")
    elif event.type == "tool_result":
        print(f"[result] {event.data['result'][:80]}")
    elif event.type == "done":
        print()
```

Events yielded are the same as `chat_with_tools()`:
`token`, `tool_call`, `tool_result`, `done`, `error`.

### `session.id -> str`

Unique session identifier.

### `session.info -> SessionInfo`

Serialisable snapshot: `session_id`, `role`, `provider`,
`created_at`, `message_count`, `status`.

---

## 7. AgentPool — multi-agent orchestration

`AgentPool` manages a collection of `Session` objects with shared
concurrency control.

```python
async with sl.AgentPool(settings, max_concurrent=10) as pool:
    ...
```

### `pool.spawn(role=None, provider=None, session_id=None, mode="execution") -> Session`

Create a new session in the pool.

- `role`: agent role name (default: `settings.active_role`)
- `provider`: provider name (str) or `ProviderConfig` object
- `session_id`: optional stable ID (auto-generated UUID if omitted)
- `mode`: initial execution mode — `"plan"` or `"execution"` (default)

```python
s = await pool.spawn(role="coder", provider="davy")
s = await pool.spawn(mode="plan", session_id="researcher")
s = await pool.spawn(provider=custom_cfg, session_id="my-id")
```

### `pool.get(session_id) -> Session`

Look up an existing session. Raises `KeyError` if not found.

### `pool.list() -> list[SessionInfo]`

Return `SessionInfo` snapshots for all sessions in the pool.

### `pool.terminate(session_id) -> None`

Remove a session from the pool.

### `pool.terminate_all() -> None`

Remove all sessions from the pool.

### `pool.delegate(tasks: dict[str, str]) -> dict[str, str]`

Send different prompts to different sessions in parallel. Returns a
dict mapping each session ID to its full response string.

```python
results = await pool.delegate({
    "analyst": "Summarise async I/O in 2 sentences.",
    "coder":   "Write minimal asyncio.gather() example.",
})
# results["analyst"] == "..."
# results["coder"]   == "..."
```

### `pool.broadcast(user_input, session_ids=None) -> AsyncIterator[AgentEvent]`

Send the same prompt to multiple sessions simultaneously. Events
arrive as they are produced (any order). `session_ids=None` targets
all sessions in the pool.

```python
async for event in pool.broadcast(
    "What is your specialty?",
    session_ids=["analyst", "coder", "critic"],
):
    if event.type == "done":
        print(event.session_id, "→", event.data)
```

### `pool.pipeline(session_ids, initial_input) -> str`

Run sessions sequentially: each session's output becomes the next
session's input. Returns the final session's output.

```python
final = await pool.pipeline(
    ["writer", "reviewer"],
    "Write a Python retry decorator.",
)
```

---

## 8. Tool calling

StarryLib supports OpenAI-style function calling through
`Session.chat_with_tools()` and the higher-level
`Session.chat_auto()`. Tools are plain Python dicts with the
standard OpenAI schema; executors are ordinary Python callables.

---

### 8.1 Native tools

StarryLib ships 18 built-in Python tools. Each is an
independent module under `starry_lib/tools/implementations/`
exposing a `SCHEMA` dict and an `execute(**kwargs) -> dict`.

| Tool | Description | plan | execution |
|------|-------------|------|-----------|
| `todowrite` | Manage a persistent task list | ✓ | ✓ |
| `task` | Launch autonomous subagents | ✓ | ✓ |
| `question` | Request user input interactively | ✓ | ✓ |
| `webfetch` | Retrieve web content via HTTP | ✓ | ✓ |
| `websearch` | Search the web via DuckDuckGo | ✓ | ✓ |
| `skill` | Load specialized skill instructions | ✓ | ✓ |
| `glob` | Find files by glob pattern | ✓ | ✓ |
| `grep` | Search file contents by regex | ✓ | ✓ |
| `read` | Read files or list directories | ✓ | ✓ |
| `calculator` | Evaluate math expressions | ✓ | ✓ |
| `list_available_agents` | List stored named agent configs | ✓ | ✓ |
| `list_active_agents` | List running named agent sessions | ✓ | ✓ |
| `describe_agent` | Get full config of a named agent | ✓ | ✓ |
| `bash` | Execute shell commands | — | ✓ |
| `edit` | Replace exact text in a file | — | ✓ |
| `write` | Create or overwrite a file | — | ✓ |
| `call_agent` | Send a message to a named agent | — | ✓ |
| `stop_agent` | Terminate a named agent session | — | ✓ |

See **[starry_lib/tools/TOOLS.md](../starry_lib/tools/TOOLS.md)**
for the full argument and return-value reference.

---

### 8.2 Execution modes

The set of tools sent to the LLM depends on the session mode:

```python
# plan mode — research and read-only operations
session.mode = "plan"

# execution mode — full read/write/run (default)
session.mode = "execution"
```

Retrieve the schemas or executor map for the current mode:

```python
schemas  = session.get_tool_schemas()   # list[dict]
executor = session.get_tool_executor()  # dict[str, Callable]
```

Or use the module-level helpers directly:

```python
import starry_lib as sl

schemas  = sl.get_tool_schemas("plan")
executor = sl.get_tool_executor("execution")
```

Use `session.chat_auto()` to wire everything automatically:

```python
async for event in session.chat_auto("List Python files here."):
    if event.type == "token":
        print(event.data, end="", flush=True)
    elif event.type == "tool_call":
        print(f"\n[tool] {event.data['name']}")
    elif event.type == "tool_result":
        print(f"[result] {event.data['result'][:80]}")
    elif event.type == "done":
        print()
```

---

### 8.3 Custom / manual tools

Define tools as plain OpenAI function dicts and pass them in:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from disk",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path",
                    }
                },
                "required": ["path"],
            },
        },
    }
]
```

**Dict executor (recommended)** — map each function name to a
callable; the library calls `fn(**args)`:

```python
EXECUTOR = {
    "read_file": lambda path: open(path).read(),
}
```

**Callable executor (dispatch pattern)** — a single function
that receives `(name, args)`:

```python
def my_executor(name: str, args: dict):
    if name == "read_file":
        return open(args["path"]).read()
    raise ValueError(f"Unknown tool: {name}")
```

**Full example:**

```python
async def answer_with_tools(session, question):
    full = ""
    async for event in session.chat_with_tools(
        question,
        tools=TOOLS,
        tool_executor=EXECUTOR,
    ):
        if event.type == "tool_call":
            print(f"  [call] {event.data['name']}")
        elif event.type == "tool_result":
            print(f"  [res]  {event.data['result'][:60]}")
        elif event.type == "done":
            full = str(event.data)
        elif event.type == "error":
            raise RuntimeError(event.data)
    return full
```

To add a new tool: write a Python function, add its schema to
the `tools` list, and add `"function_name": fn` to the executor
dict. No library changes are needed.

---

## 9. Event types

All streaming methods yield `AgentEvent` objects:

```python
@dataclass
class AgentEvent:
    type: str            # see table below
    session_id: str      # which session produced this
    data: str | dict     # payload
    timestamp: datetime  # UTC time of event
```

| `type` | `data` type | Description |
|--------|-------------|-------------|
| `"token"` | `str` | One streamed text chunk |
| `"tool_call"` | `dict` | `{"id", "name", "args"}` |
| `"tool_result"` | `dict` | `{"id", "name", "result"}` |
| `"error"` | `str` | Error message; stream ends after this |
| `"done"` | `str` | Full assembled response; stream ends |

---

## 10. Data types

### `Message`

```python
@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    metadata: dict[str, Any]
```

### `SessionInfo`

```python
@dataclass
class SessionInfo:
    session_id: str
    role: str
    provider: str
    created_at: datetime
    message_count: int
    status: Literal["idle", "running", "stopped"]
```

---

## 11. MCP tool servers and third-party tools

### MCP (Model Context Protocol) servers

> **Requires Python 3.12+.** On Python 3.11 a `RuntimeWarning`
> is emitted and MCP support is silently disabled.

MCP servers give the agent external capabilities via subprocesses
or HTTP endpoints. Configure them in `config/default.toml`:

```toml
[mcp_servers.git]
transport = "stdio"
command   = "python"
args      = ["-m", "mcp_server_git", "--repository", "."]

[mcp_servers.fetch]
transport = "stdio"
command   = "python"
args      = ["-m", "mcp_server_fetch"]

[mcp_servers.remote]
transport = "http"
url       = "http://localhost:8000/mcp"
```

Build the server list:

```python
from starry_lib.tools.registry import build_mcp_servers

servers = build_mcp_servers(settings)
```

### `discover_entry_point_tools() -> list`

Discover and load tools registered by installed third-party
packages via Python entry points. Any package can contribute
tools by declaring an entry point in its `pyproject.toml`:

```toml
# In the third-party package's pyproject.toml:
[project.entry-points."starry_lib.tools"]
my_tools = "my_package.tools:get_tools"
```

The loader function must return a `list` of tool dicts
(OpenAI function-calling format):

```python
# my_package/tools.py
def get_tools() -> list:
    return [MY_TOOL_SCHEMA_1, MY_TOOL_SCHEMA_2]
```

Discover all registered tools:

```python
import starry_lib as sl

extra_tools = sl.discover_entry_point_tools()
# extra_tools is a flat list of tool schema dicts

async for event in session.chat_with_tools(
    "Do something using extra tools.",
    tools=extra_tools,
    tool_executor=my_executor,
):
    ...
```

Errors in individual loaders are silently ignored so one
bad package cannot prevent others from loading.

---

## 12. Configuration reference

### `[app]`

| Key | Default | Description |
|-----|---------|-------------|
| `active_provider` | `None` | Provider used by default |
| `active_role` | `"assistant"` | Agent role used by default |
| `history_file` | `"~/.local/starry/history"` | CLI input history path |

### `[providers.<name>]`

| Key | Description |
|-----|-------------|
| `base_url` | Full base URL of the OpenAI-compatible API |
| `api_key_env` | Name of the env var holding the API key |
| `ssl_verify` | `true` / `false` / `"path/to/cert.crt"` |
| `default_model` | Model used unless overridden |
| `label` | Human-readable display name |

### `[agents.<name>]`

| Key | Description |
|-----|-------------|
| `label` | Display name |
| `system_prompt` | Instructions sent as the system message |
| `tools` | Reserved (pass tools via `chat_with_tools()`) |
| `model_override` | Override the provider's `default_model` |

### `[mcp_servers.<name>]`

| Key | Description |
|-----|-------------|
| `transport` | `"stdio"` (subprocess) or `"http"` (remote) |
| `command` | Executable for stdio servers |
| `args` | Argument list for stdio servers |
| `url` | Endpoint URL for http servers |

---

## 13. Named agent system

Named agents are persistent, stateful agent configurations stored
on disk. Unlike the ephemeral `task` tool subagents, named agents
keep their conversation history across multiple `call_agent` calls
within a session.

### AgentConfig persistence dataclass

Defined in `starry_lib/agents/agent_config.py`.
Stored as JSON in `~/.local/starry/agents/<name>.json`.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `name` | `str` | — | Unique key; also the filename |
| `label` | `str` | — | Human-readable display name |
| `role` | `str` | — | Role key from `config/default.toml` |
| `provider` | `str` | — | Provider name |
| `model` | `str` | `""` | Override model; empty = provider default |
| `system_prompt_addon` | `str` | `""` | Appended to role's system prompt |
| `temperature` | `float` | `0.0` | LLM temperature override |
| `allowed_tools` | `list[str]` | `[]` | Tool whitelist (empty = all) |
| `denied_tools` | `list[str]` | `[]` | Tool blacklist |
| `allowed_skills` | `list[str]` | `[]` | Skill whitelist |
| `denied_skills` | `list[str]` | `[]` | Skill blacklist |
| `description` | `str` | `""` | Human-readable summary |

### AgentStore API

```python
from starry_lib.agents.agent_store import (
    list_agents,    # () -> list[AgentConfig]
    get_agent,      # (name) -> AgentConfig | None
    save_agent,     # (cfg) -> None
    delete_agent,   # (name) -> None
    agent_exists,   # (name) -> bool
)
```

Storage: `~/.local/starry/agents/<name>.json`

### ActiveRegistry

`ActiveRegistry` (in `starry_lib/agents/active_registry.py`)
maps agent name → live `Session` inside the `AgentPool`.

```python
# held as a single instance on TUI / application state
registry = ActiveRegistry()

await registry.spawn_agent(name, pool, settings)
await registry.kill_agent(name, pool)
await registry.kill_all(pool)

registry.is_active(name)      # -> bool
registry.get_session(name)    # -> Session | None
registry.get_lock(name)       # -> asyncio.Lock | None
registry.list_active()        # -> list[ActiveAgentInfo]
```

`session_id` for named agents is always `"agent-<name>"`.
Per-agent `asyncio.Lock` serializes concurrent `call_agent` calls.

### Using named agents from LLM tools

The LLM can interact with named agents via four tools:

```
list_available_agents  — see what agents exist on disk
describe_agent         — inspect one agent's full config
call_agent             — send a message; spawns if not active
stop_agent             — terminate and free the session
```

`call_agent` accepts an optional `context` string that is
injected as a system message before the agent's very first turn.

### Programmatic usage

```python
from starry_lib.agents.agent_config import AgentConfig
from starry_lib.agents.agent_store import save_agent
from starry_lib.agents.active_registry import ActiveRegistry

# Create and store a named agent
cfg = AgentConfig(
    name="analyst",
    label="Data Analyst",
    role="researcher",
    provider="davy",
    description="Specialized in data analysis.",
)
save_agent(cfg)

# Spawn it into the pool
registry = ActiveRegistry()
session = await registry.spawn_agent("analyst", pool, settings)

# Use the session directly
async for event in session.chat_auto("Summarise this CSV: ..."):
    if event.type == "done":
        print(event.data)

# Clean up
await registry.kill_agent("analyst", pool)
```

See `AGENTS.md` for a full named agent system reference.

---

## 14. Troubleshooting

### `RuntimeError: env var 'STARRY_API_KEY' is not set`

The key is missing from the environment. Set it in `.env`:

```
STARRY_API_KEY=your-api-key
```

Make sure `.env` is loaded before calling `load_settings()`.

### `ssl.SSLError` or certificate errors

Place the certificate and ensure `ssl_verify` points to it:

```toml
[providers.davy]
ssl_verify = "certs/davy.labs.lenovo.com.crt"
```

Or temporarily disable verification (dev only):

```toml
ssl_verify = false
```

### `ModuleNotFoundError: No module named 'tomllib'`

Python 3.10 or older is being used. The library requires Python 3.11+.
Check your venv:

```bash
.venv/bin/python --version
```

If needed, recreate the venv with Python 3.11:

```bash
python3.11 -m venv .venv
pip install -e ".[dev]"
```

### `KeyError: provider 'X' not found`

The provider name is not in `config/default.toml`. Check with:

```python
print(list(settings.providers.keys()))
```

### Provider shows as unavailable

Run `probe_provider` to diagnose:

```python
models = await sl.probe_provider(settings.providers["openwebui"])
```

Common causes: wrong `base_url`, missing API key, SSL cert issues.

### Open WebUI connectivity

The OpenWebUI endpoint is `/api/chat/completions`. The SDK appends
`/chat/completions` to `base_url`, so set:

```toml
[providers.openwebui]
base_url = "http://lico1:8080/api"
```

Do not add `/v1` — that would produce `/v1/chat/completions`.
