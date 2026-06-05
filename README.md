# Starry

**Starry** is a two-layer Python project for multi-agent LLM orchestration:

- **`starry_lib/`** — async library for building multi-agent pipelines
- **`starry_cli/`** — full-screen terminal UI (TUI) powered by `prompt_toolkit`

All LLM calls use the OpenAI-compatible API format, making providers
interchangeable at runtime. Works with OpenWebUI, Ollama, OpenAI, or any
compatible endpoint.

---

## Features

- **Multi-agent patterns** — broadcast, delegate, and pipeline across concurrent
  sessions
- **Named agents** — persistent, stateful agent configs that survive across
  tool calls
- **8 built-in roles** — assistant, coder, sysadmin, researcher, manager,
  reviewer, integrator, tester (each with tailored system prompts and tool
  access)
- **19 built-in tools** — bash, read, glob, grep, edit, write, websearch,
  webfetch, calculator, task, call_agent, stop_agent, and more
- **MCP support** — connect to any stdio or HTTP MCP server (git, fetch,
  sqlite, custom)
- **Native skills** — auto-discovered plugins with `descriptor.json` +
  `skill.py` (built-in: `sys_info`, `network_scan`)
- **Session persistence** — save and restore conversations under
  `~/.local/starry/conf/sessions/`
- **Custom commands** — user-defined `/` commands stored in
  `~/.local/starry/conf/commands.json`; support `$ARGUMENTS` substitution
- **Streaming** — token-by-token streaming with tool-call events
- **Per-session tool permissions** — whitelist (`allowed_tools`) and blacklist
  (`denied_tools`) per agent
- **Observability** — per-session NDJSON trace export
- **12 themes** — tokyonight, catppuccin, cyberpunk, nordic, gruvbox-light,
  rosepine, and more

---

## Requirements

- Python 3.11+
- An OpenAI-compatible LLM API endpoint

---

## Installation

### Editable install (development)

```bash
git clone <repo-url>
cd starry
python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"

# Optional: enable web search tools
pip install -e ".[dev,search]"
```

### End-user install

```bash
bash install.sh
# Uninstall: bash install.sh --uninstall
```

---

## Configuration

Copy the example env file and fill in your API keys:

```bash
cp .env.example ~/.local/starry/conf/.env
$EDITOR ~/.local/starry/conf/.env
```

```env
STARRY_API_KEY=your-api-key-here
OPENWEBUI_API_KEY=sk-your-openwebui-key-here
OPENAI_API_KEY=sk-your-openai-key-here
OLLAMA_API_KEY=ollama
```

Providers, roles, and MCP servers are configured in `config/default.toml`.
The active provider is set in `~/.local/starry/conf/config.toml` (written by
`/setup` in the TUI).

---

## Usage

### TUI

```bash
starry_cli

# Restore a previous session
starry_cli --session <session_id>
```

#### TUI commands

Unambiguous 4+-character prefixes are auto-expanded.

| Command           | Description                                        |
|-------------------|----------------------------------------------------|
| `/setup`          | Configure providers, models, tools, themes         |
| `/agent`          | Create, list, edit, chat with named agents         |
| `/mode`           | Toggle Plan/Research ↔ Execution                   |
| `/role`           | Switch active agent role                           |
| `/provider`       | Switch active LLM provider                         |
| `/model`          | Switch active model                                |
| `/new`            | Start a fresh conversation (new session ID)        |
| `/save`           | Save current session to disk immediately           |
| `/load`           | Open session restore menu (alias for `/sessions`)  |
| `/sessions`       | Browse and restore saved sessions                  |
| `/clear`          | Clear conversation history                         |
| `/rewind`         | Remove last N turns                                |
| `/summarize`      | Summarise history to free context                  |
| `/add-dir <path>` | Add a directory to the session context             |
| `/doctor`         | Health checks: Python, config, provider, MCP       |
| `/mcp [list\|info]` | List MCP servers or inspect one server's tools   |
| `/recap`          | Recap what has been discussed and accomplished     |
| `/review`         | Review recent git changes                          |
| `/focus <text>`   | Focus the session on a topic                       |
| `/goal <text>`    | Set the session goal                               |
| `/project`        | Describe the current project                       |
| `/branch <name>`  | Work with a git branch                             |
| `/stats`          | Show token usage and session info                  |
| `/btw`            | Add background context without triggering LLM      |
| `/aboutme`        | Store user self-description for the agent          |
| `/trace`          | Export session trace as NDJSON                     |
| `/help`           | Show all commands                                  |
| `/exit`           | Exit the TUI                                       |

### Library

```python
import starry_lib as da
import asyncio

async def main():
    settings = da.load_settings()

    async with da.AgentPool(settings) as pool:
        session = await pool.spawn(role="assistant", provider="openwebui")

        # Streaming chat
        async for ev in session.chat("Explain the Python GIL in two sentences."):
            if ev.type == "token":
                print(ev.data, end="", flush=True)
        print()

        # Multi-agent delegation
        analyst = await pool.spawn(role="researcher", session_id="analyst")
        coder   = await pool.spawn(role="coder",      session_id="coder")

        results = await pool.delegate({
            "analyst": "What problem does async I/O solve?",
            "coder":   "Write a minimal asyncio fetch snippet.",
        })

        # Pipeline: coder writes, critic reviews
        critic = await pool.spawn(role="assistant", session_id="critic")
        output = await pool.pipeline(
            ["coder", "critic"],
            "Write a Python retry function with exponential back-off.",
        )

asyncio.run(main())
```

See `demo_LLM_lib.py` for a full walkthrough of every library feature.

---

## Architecture

```
starry_lib/
  agents/         — Session, AgentPool, BaseAgent, named agent CRUD
  commands/       — CRUD for user-defined custom slash commands
  config/         — Settings loader + runtime path constants
  llm/            — AsyncOpenAI client builder, retry logic
  tools/          — built-in tools + MCP client + skill loader
  skills/         — Auto-discovered native skills (descriptor.json + skill.py)
  sessions/       — JSON session persistence
  context/        — World state injection, context-window manager
  events/         — Markdown event templates (on_session_start, on_error, …)
  observability/  — Per-session NDJSON tracer

starry_cli/
  main.py         — TUI entry point (~9 500 lines, marker-based rendering)
  dialogs.py      — Floating menus and text input dialogs
  themes/         — 12 JSON color themes
```

---

## Tools

Tools are mode-scoped. Both modes get read-only tools; execution mode adds
write/shell tools.

| Tool                  | Plan & Research | Execution |
|-----------------------|:---------------:|:---------:|
| read, glob, grep      | ✓               | ✓         |
| webfetch, websearch   | ✓               | ✓         |
| todowrite, task       | ✓               | ✓         |
| question, calculator  | ✓               | ✓         |
| list/describe_agent   | ✓               | ✓         |
| bash, edit, write     |                 | ✓         |
| call_agent            |                 | ✓         |
| stop_agent            |                 | ✓         |

---

## Adding a Native Skill

1. Create `starry_lib/skills/<name>/`
2. Add `descriptor.json` (OpenAI function schema)
3. Add `skill.py` with an `execute(**kwargs)` function (sync or async)

The skill is auto-discovered on next startup — no registration needed.

Third-party tools can register via the `starry_lib.tools` setuptools entry
point.

---

## Testing

```bash
# Unit + integration tests (no live API calls)
pytest

# By layer
pytest tests/unit/
pytest tests/integration/
pytest tests/smoke/        # requires real API keys

# Include live API tests
pytest -m live

# Lint and format
ruff check . && ruff format .
```

---

## License

Copyright 2025-present bsdero
