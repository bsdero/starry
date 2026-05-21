# DavyAgent

A Python library for building multi-agent AI applications on top of
OpenAI-compatible LLM providers. Supports streaming, conversation
history, native tool calling with execution modes, and parallel
multi-agent patterns.

For the complete API reference see **[docs/user_manual.md](docs/user_manual.md)**.

---

## Requirements

- Python 3.11+
- An OpenAI-compatible LLM endpoint (DavyAI, Open WebUI, OpenAI, …)

---

## Quick start

### 1. Install

```bash
# Developer install (editable, includes test deps)
pip install -e ".[dev]"
```

### 2. Set API keys

```bash
cp .env.example .env
# Edit .env:
# DAVY_API_KEY=quill
# OPENWEBUI_API_KEY=sk-your-key
```

### 3. Place the DavyAI TLS certificate *(if using davy)*

```bash
cp davy.labs.lenovo.com.crt certs/
```

### 4. Run the demo

```bash
python demo.py                      # DavyAI provider
python demo.py --provider openwebui # Open WebUI provider
python demo.py --model gemma-4-31b-it
```

---

## Usage

### Streaming chat

```python
import asyncio
import davyagent as da

async def main():
    settings = da.load_settings()

    async with da.AgentPool(settings) as pool:
        session = await pool.spawn(role="coder")

        # Streaming (tokens only, no tools)
        async for event in session.chat("Explain asyncio."):
            if event.type == "token":
                print(event.data, end="", flush=True)
        print()

        # Non-streaming
        reply = await session.chat_complete("Summarise.")
        print(reply)

asyncio.run(main())
```

### Chat with automatic tools

`chat_auto()` selects tools based on the session mode and wires
everything automatically. Use this as the default for the TUI.

```python
async with da.AgentPool(settings) as pool:
    # execution mode (default) — all 11 tools available
    session = await pool.spawn(mode="execution")

    async for event in session.chat_auto("List Python files here."):
        if event.type == "token":
            print(event.data, end="", flush=True)
        elif event.type == "tool_call":
            print(f"\n[tool] {event.data['name']}({event.data['args']})")
        elif event.type == "tool_result":
            print(f"[result] {event.data['result'][:80]}")
        elif event.type == "done":
            print()

    # Switch to plan mode at runtime — drops bash/edit/write
    session.mode = "plan"
    async for event in session.chat_auto("Research asyncio."):
        ...
```

---

## Execution modes

Tools sent to the LLM depend on the current mode:

| Mode | Available tools |
|------|----------------|
| **`plan`** | `todowrite` `task` `question` `webfetch` `skill` `glob` `grep` `read` |
| **`execution`** | All plan tools + `bash` `edit` `write` |

Change mode on a live session at any time:

```python
session.mode = "plan"       # read-only + research
session.mode = "execution"  # full read/write/run
```

---

## Providers

Two providers are pre-configured:

| Name | Endpoint | Default model |
|------|----------|---------------|
| `davy` (default) | `https://davy.labs.lenovo.com:5000/v1` | `gemma-4-31b-it` |
| `openwebui` | `http://lico1:8080/api` | `gpt-oss-120b-thinking` |

Add a runtime provider without editing any file:

```python
custom = da.make_provider(
    name="local",
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    model="llama3",
)
session = await pool.spawn(provider=custom)
```

---

## Multi-agent patterns

```python
async with da.AgentPool(settings) as pool:
    s1 = await pool.spawn(role="researcher", session_id="r")
    s2 = await pool.spawn(role="coder",      session_id="c")

    # Parallel delegation — different tasks, same time
    results = await pool.delegate({
        "r": "What problem does async I/O solve?",
        "c": "Show a minimal asyncio.gather() example.",
    })

    # Sequential pipeline — output feeds next agent
    final = await pool.pipeline(["r", "c"], "initial prompt")

    # Broadcast — same question to all agents
    async for ev in pool.broadcast("your specialty?"):
        if ev.type == "done":
            print(ev.session_id, "→", ev.data)
```

---

## Native tools

DavyAgent ships 11 built-in Python tools. Each tool exposes a
`SCHEMA` (OpenAI function format) and an `execute()` function:

| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands |
| `read` | Read files or list directories |
| `glob` | Find files by glob pattern |
| `grep` | Search file contents by regex |
| `edit` | Replace exact text in a file |
| `write` | Create or overwrite a file |
| `task` | Launch autonomous subagents |
| `webfetch` | Retrieve web content via HTTP |
| `todowrite` | Manage a persistent task list |
| `skill` | Load specialized skill instructions |
| `question` | Request user input interactively |

See **[davyagent/tools/TOOLS.md](davyagent/tools/TOOLS.md)** for
the full argument and return-value reference.

### Third-party tool auto-discovery

Installed packages can register tools via Python entry points:

```toml
# In your package's pyproject.toml:
[project.entry-points."davyagent.tools"]
my_tools = "my_package.tools:get_tools"
```

```python
# Discover and load all registered tools:
extra_tools = da.discover_entry_point_tools()
```

---

## Manual tool calling

You can also supply tools explicitly via `chat_with_tools()`:

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Evaluate a math expression",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"],
        },
    },
}]

async for event in session.chat_with_tools(
    "What is 12 * 34?",
    tools=TOOLS,
    tool_executor={"calculate": lambda expression: eval(expression)},
):
    if event.type == "tool_call":
        print("calling", event.data["name"])
    elif event.type == "tool_result":
        print("result", event.data["result"])
    elif event.type == "done":
        print("answer:", event.data)
```

---

## Development

```bash
# Run all non-live tests
.venv/bin/pytest

# Run tool-specific tests
.venv/bin/pytest tests/unit/test_tools.py -v

# Run live smoke tests (require real API keys)
.venv/bin/pytest -m live

# Lint
.venv/bin/ruff check .
```

---

## File layout

```
davy_agent/
├── config/
│   └── default.toml              # Provider and agent config
├── certs/                        # TLS certificates
├── .env                          # API keys (gitignored)
├── davyagent/                    # Library source
│   ├── __init__.py               # Public API
│   ├── agents/                   # Session, AgentPool, BaseAgent
│   ├── config/                   # Settings (Pydantic)
│   ├── llm/                      # AsyncOpenAI client factory
│   ├── providers.py              # Provider CRUD functions
│   ├── tools/
│   │   ├── TOOLS.md              # Tool reference documentation
│   │   ├── registry.py           # MCP server registry
│   │   ├── tool_loader.py        # Mode → tool set mapping
│   │   └── implementations/      # Native Python tool modules
│   │       ├── bash.py
│   │       ├── read.py
│   │       ├── glob.py
│   │       ├── grep.py
│   │       ├── edit.py
│   │       ├── write.py
│   │       ├── task.py
│   │       ├── webfetch.py
│   │       ├── todowrite.py
│   │       ├── skill.py
│   │       └── question.py
│   └── types.py                  # AgentEvent, Message, SessionInfo
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_provider_client.py
│   │   ├── test_providers.py
│   │   └── test_tools.py         # 86 tool + mode tests
│   ├── integration/
│   └── smoke/
├── davy_cli.py                   # TUI (prompt_toolkit)
└── demo.py                       # End-to-end API walkthrough
```
