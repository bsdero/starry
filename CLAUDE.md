# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

StarryLib is a two-layer project:

1. **Library** (`starry_lib/`) — async Python library for multi-agent LLM orchestration
2. **TUI** (`starry_cli/main.py`) — full-screen terminal UI built on `prompt_toolkit`

All LLM calls use an OpenAI-compatible API format, making providers interchangeable
at runtime. Configuration lives in `config/default.toml`; secrets are never in TOML —
they are read from environment variables (via `.env` or shell).

## Common Commands

```bash
# Editable install with dev extras (use the project venv)
source .venv/bin/activate
pip install -e ".[dev]"

# Also install search extras to enable webfetch/websearch tools
pip install -e ".[dev,search]"

# First-time setup: copy env example to user config dir and fill in API keys
cp .env.example ~/.local/starry/.env
$EDITOR ~/.local/starry/.env
# Then launch the TUI and use /setup to select a provider
# (writes active_provider to ~/.local/starry/config.toml)

# Launch the TUI (two ways after install)
python -m starry_cli
starry_cli

# Restore a saved session
starry_cli --session <session_id>

# Library demo
python demo_LLM_lib.py

# Tests (unit + integration; skips live API calls by default)
# pytest.ini addopts: -v --tb=short -m 'not live'
# asyncio_mode = "auto" — no @pytest.mark.asyncio needed
pytest

# Run by directory (unit / integration / smoke)
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/smoke/ -v          # smoke tests also need real APIs

# Run a single test file
pytest tests/unit/test_tools.py -v

# Run tests that require real API keys
pytest -m live

# Run slow tests (not excluded by default, but skippable)
pytest -m slow

# Lint / format
ruff check . && ruff format .

# Install to ~/.local/starry/ for end-user use
bash install.sh
bash install.sh --uninstall
```

## Architecture

### Library (`starry_lib/`)

| Module | Purpose |
|--------|---------|
| `config/settings.py` | `load_settings()` → `AppSettings`; walks up from its own path to find `config/default.toml` |
| `providers.py` | CRUD for `ProviderConfig` in TOML; `probe_provider()` for connectivity |
| `llm/client.py` | `build_client(provider)` → `AsyncOpenAI`; `call_with_retry()` for exponential backoff on 429/5xx |
| `agents/base.py` | `BaseAgent` dataclass; assembles system prompt from structured fields |
| `agents/session.py` | Single conversation: streaming `chat()`, tool loop, provider/model/role hot-swap |
| `agents/pool.py` | N concurrent sessions; `broadcast`, `delegate`, `pipeline` patterns |
| `agents/orchestrator.py` | Simpler single-agent manager without pool overhead; uses raw streaming API directly (Python 3.11-compatible); suitable for scripts |
| `agents/roles.py` | `build_agent(role_cfg, provider_cfg)` factory; `build_agent_from_persistent(cfg, settings)` for named agents |
| `agents/agent_config.py` | `AgentConfig` dataclass — named agent persistence record (pure data, no runtime logic) |
| `agents/agent_store.py` | CRUD for `~/.local/starry/agents/`; `list_agents()`, `get_agent()`, `save_agent()`, `delete_agent()` |
| `agents/active_registry.py` | `ActiveRegistry` — maps agent name → `session_id`; holds per-agent `asyncio.Lock` |
| `tools/` | Tool schemas + executors; implementations live in `tools/implementations/` |
| `tools/tool_loader.py` | `get_tool_schemas(mode)` / `get_tool_executor(mode)`; `wrap_with_cache()` caches read-only tool results and invalidates on writes |
| `tools/mcp_client.py` | Direct MCP client using the `mcp` package — works on Python 3.11+; reconnects per call (stateless) |
| `tools/registry.py` | MCP via the `openai-agents` SDK — requires Python 3.12+; emits `RuntimeWarning` on 3.11 |
| `tools/skill_loader.py` | Auto-discovers `starry_lib/skills/*/` at import; returns cached `SkillTool` list |
| `skills/` | Auto-discovered native skills (each is a subdirectory with `descriptor.json` + `skill.py`) |
| `sessions/store.py` | JSON persistence under `~/.local/starry/sessions/<session_id>/session.json` |
| `observability/trace.py` | Per-session `Tracer`; exports NDJSON |
| `context/world_state.py` | `build_world_state()` — regenerated per turn (date, cwd, git, OS) |
| `context/window_manager.py` | `truncate_messages()` — trims message list to token budget (tool results → old turns → hard truncation) |
| `events/loader.py` | `load_event(name, **kwargs)` — renders `starry_lib/events/<name>.md` templates with `{{variable}}` substitution; returns `None` if file absent |

### Session state — single source of truth

`Session` (in `agents/session.py`) owns all runtime state. Read active values through
its public properties — never mirror them into CLI globals:

```python
session.provider   # active provider name
session.model      # active model identifier
session.role       # active agent role name
session.id         # unique session identifier
```

**Session chat methods:**

| Method | When to use |
|--------|-------------|
| `chat(user_input)` | Raw streaming without tools — pure token stream |
| `chat_auto(user_input)` | Streaming with mode-selected tools injected automatically; used by the TUI and `call_agent` |
| `chat_with_tools(user_input, schemas, executor)` | Explicit tool list — when you supply your own schemas and executor |
| `chat_complete(user_input)` | Non-streaming; returns the full response string |

In `starry_cli/main.py`, the three helper functions bridge the brief pre-session startup
phase (before `pool.spawn()`) and the live session:

```python
_active_provider()   # session.provider or settings fallback
_active_model()      # session.model or ""
_active_role()       # session.role or settings fallback
```

Runtime switches go through `session.switch_provider()`, `session.set_model()`,
`session.switch_role()` — these update internal state and emit `display_log` events.

`session.inject_system_message(content)` appends a system-role message to history
without triggering a new LLM turn (used to notify the main session when a named
agent is killed).

### Tools & Skills

**Two modes** (toggled with `/mode` in the TUI; stored in `_exec_mode` in `main.py`;
passed to `get_tool_schemas(mode)` and `get_tool_executor(mode)`):

- **Plan / Research** — read-only + research tools; safe for exploration without
  side effects
- **Execution** — all plan tools plus write/run tools; default mode at startup

Tool implementations live in `starry_lib/tools/implementations/` (one module per
tool). `tool_loader.py` provides `get_tool_schemas(mode)` and `get_tool_executor(mode)`
for mode-aware selection.

Every executor receives a `ctx: dict` keyword argument injected by `tool_loader.py`
at call time, carrying: `active_registry`, `pool`, `main_session`, `settings`.
Existing tools that don't need it simply ignore the default `{}`.

- **Both modes**: `read`, `glob`, `grep`, `webfetch`, `websearch`, `todowrite`,
  `task`, `question`, `calculator`, `list_available_agents`, `list_active_agents`,
  `describe_agent`
- **Execution mode only** (adds): `bash`, `edit`, `write`, `call_agent`, `stop_agent`
- Per-session filtering: `allowed_tools` (whitelist) and `denied_tools` (blacklist)
  applied inside `get_tool_schemas()` / `get_tool_executor()`
- **Skills** auto-discovered from `starry_lib/skills/*/`; built-in skills are
  `sys_info` and `network_scan`; invalid skills are logged and skipped, never
  abort startup
- Third-party tools register via the `starry_lib.tools` setuptools entry point

#### Adding a built-in tool

1. Create `starry_lib/tools/implementations/<name>.py` with a module-level `SCHEMA`
   dict (OpenAI function schema) and an `execute(**kwargs)` function.
2. Import the module in `tool_loader.py` and append it to `_STATIC_PLAN` (both
   modes) or `_EXEC_ONLY` (execution mode only).

#### Adding a native skill

1. Create `starry_lib/skills/<name>/` with:
   - `descriptor.json` — an OpenAI function schema
   - `skill.py` — a module with an `execute(**kwargs)` function (sync or async)
2. `skill_loader.py` auto-discovers it on the next startup; no registration needed.

### Named Agent System

Named agents are persistent, stateful agent configurations that can be spawned
into live Sessions and called by the LLM via the `call_agent` tool.

**Conceptual layers:**

```
Role         — behavior template from config/default.toml [agents.*]
AgentConfig  — named persistent config (role + provider + model + overrides)
               stored as ~/.local/starry/agents/<name>.json
Active Agent — an AgentConfig with a live Session in the AgentPool
               session_id is always "agent-<name>"
```

**Key distinction:** the `task` tool creates a throwaway ephemeral subagent from a
role; `call_agent` targets a named, persistent, stateful agent that survives across
multiple tool calls.

**`call_agent` behavior:**
1. If the agent is not active, `ActiveRegistry.spawn_agent()` is called first.
2. Acquires the per-agent `asyncio.Lock` to serialize concurrent calls.
3. Sends the message via `session.chat_auto()`; buffers the full response to return
   to the LLM while streaming tokens to the agent's log buffer in parallel.

**`stop_agent` behavior:** kills the agent via `ActiveRegistry.kill_agent()`, then
calls `main_session.inject_system_message()` to inform the main LLM.

**Dual-buffer model:** each active agent has exactly two TUI buffers that share one
Session:

| Buffer | Name | Writable by |
|--------|------|-------------|
| Log | `agent:<name>:log` | `call_agent` tool (LLM ↔ agent traffic) — read-only to user |
| Chat | `agent:<name>:chat` | User direct interaction via TUI |

Chat buffer is created at `spawn_agent()`; log buffer is created lazily on first
`call_agent` traffic.

**Input routing (`session_stack`):** a `list[str]` in TUI state. When
`session_stack[-1]` is `"agent:<name>"`, all prompt input routes to that agent's
session. `/close` pops the stack. Stack entries are `{"name": ..., "owned": bool}`;
`owned=True` (from `/agent → Chat with agent`) kills the agent on close, while
`owned=False` (from `/agent → Chat with active agent`) leaves it alive.

**`/agent` TUI command** (8 sub-options via `starry_cli/dialogs.py` menus):
- A. Create agent — wizard: name, role, provider, model, prompt addon, temperature, description
- B. List agents — read-only table
- C. Edit agent — same wizard, fields pre-filled
- D. Remove agent — warns if active, kills then deletes
- E. Chat with agent — spawns session, pushes to `session_stack` (owned)
- F. List active agents — name, session_id, role, provider, turns, tokens
- G. Chat with active agent — pushes to `session_stack` (not owned)
- H. Kill active agent — confirm, kill, inject system message into main session

### Events System

`starry_lib/events/` contains one `.md` template file per event name.
`events/loader.py::load_event(name, **kwargs)` reads and renders them, substituting
`{{variable}}` placeholders with the provided kwargs. Returns `None` if the file is
absent — the event is silently skipped, never an error. Add new events by dropping
a new `.md` file into the directory.

Available event hooks: `on_session_start`, `on_session_end`, `on_tool_call`,
`on_tool_result`, `on_tool_error`, `on_tool_change`, `on_context_limit`,
`on_error`, `on_mode_change`, `on_provider_switch`, `on_role_switch`,
`on_skill_change`, `on_llm_request_cancel`.

### TUI (`starry_cli/main.py`)

Single ~9 000-line file.

**TUI commands** (unambiguous 4+-char prefixes are auto-expanded):

| Command | Description |
|---------|-------------|
| `/setup` | Configure providers, models, tools, themes |
| `/agent` | Create, list, edit, chat with named agents (8 sub-options) |
| `/mode` | Toggle Plan/Research ↔ Execution |
| `/role` | Switch active agent role |
| `/provider` | Switch active LLM provider |
| `/model` | Switch active model |
| `/save` / `/load` | Save / restore session |
| `/clear` | Clear conversation history |
| `/rewind` | Remove last N turns |
| `/summarize` | Summarise history to free context |
| `/stats` | Show token usage and session info |
| `/help` | Show all commands |
| `/exit` | Exit the TUI |

**Key patterns:**

- **Marker-based rendering:** every line in the scroll buffer carries a 2-char invisible
  marker (e.g. `Uf`, `Ac`) that `FrameLexer` parses into color fragments
- **Layout:** `FloatContainer` → top_bar / tab_bar / body (`DynamicContainer`) /
  bot_bar / input_area
- **Command dispatch:** `accept_handler()` inside `setup_input_handler()`. Commands
  start with `/`. A prefix auto-run block at the top of the handler expands unambiguous
  4+-character prefixes to the full command before dispatch.
- **Themes:** JSON files in `starry_cli/themes/`; active theme loaded into `build_style(mode)`
- **Dialogs:** `starry_cli/dialogs.py` — floating selection menus and text input dialogs used
  by `/setup`, `/agent`, and all other command menus
- **Entry point:** `run()` (sync) → `asyncio.run(main())`; registered as the
  `starry_cli` console script in `pyproject.toml`

### Configuration

`config/default.toml` sections:

```toml
[app]               # active_provider, active_role, context_format
[providers.<name>]  # base_url, api_key_env, ssl_verify, default_model,
                    # context_window, fallback (provider name to chain to)
[agents.<name>]     # system_prompt (or goal/backstory/constraints/output_format),
                    # temperature, allowed_tools, can_delegate_to
[mcp_servers.<name>] # transport (stdio/http), command, args
```

**Config layering** (`load_settings()` merges in order, later wins):
1. Bundled `config/default.toml` (roles, MCP servers, provider presets)
2. `~/.local/starry/config.toml` (user overlay — active provider set here by `/setup`)
3. Project root `.env` (if present), then `~/.local/starry/.env` (wins on conflicts)

**User data directory** (`~/.local/starry/`):

| Path | Contents |
|------|----------|
| `config.toml` | Active provider; written by `/setup` |
| `.env` | API keys (`cp .env.example ~/.local/starry/.env`) |
| `user.json` | TUI preferences: theme, exec mode, context format |
| `user_roles.json` | User-created role keys (added via `/role`) |
| `sessions/<id>/session.json` | Saved conversation sessions |
| `agents/<name>.json` | Named agent configs (managed by `AgentStore`) |

### Session Persistence

Saved sessions live in `~/.local/starry/sessions/<session_id>/session.json`.
`list_sessions()`, `save()`, `load()` (accepts full ID or unique prefix) are the
public interface in `starry_lib/sessions/store.py`.

Named agent configs are stored separately in `~/.local/starry/agents/<name>.json`
(managed by `AgentStore`). Agent sessions are ephemeral — they do not persist
across TUI restarts.

### Tests

`tests/conftest.py` provides shared fixtures:

- `tmp_config(tmp_path, monkeypatch)` — isolated config dir with minimal TOML and
  pre-set env vars (`STARRY_API_KEY`, `OPENWEBUI_API_KEY`); use in any test that
  calls `load_settings()`
- `mock_completion` — a single non-streaming `ChatCompletion` mock object
- `mock_llm` — `AsyncMock` for `AsyncCompletions.create`; return value is `mock_completion`

## Code Conventions

- Lines must stay at or under 79 characters (enforced by `ruff`, `line-length = 79`).
  Rethink the code if a line is longer.
- Discuss any solution before touching files. Get explicit sign-off before editing.
- Ask questions if anything is unclear before proceeding.
- All Python files use this header:

```python
#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       filename.py
# DESCRIPTION: ...
# SUMMARY: ...
# NOTES: ...
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    username        Description of change
```

### `starry_lib` Public API

`import starry_lib as sl` (or `as da` in the TUI source) exposes:

```python
# Config & settings
sl.load_settings()          # → AppSettings; merges TOML + env
sl.AppSettings, sl.ProviderConfig, sl.RoleConfig
sl.AgentConfig, sl.MCPServerConfig

# Types (the streaming currency)
sl.AgentEvent   # type: token | tool_call | tool_result | error | done
sl.Message, sl.SessionInfo

# Agents
sl.AgentPool    # async context manager; spawn() → Session
sl.Session      # chat(), chat_auto(), chat_with_tools(), chat_complete()

# LLM client
sl.build_client(provider)   # → AsyncOpenAI
sl.list_models(provider)    # → list[str]

# Provider CRUD (used by /setup)
sl.list_providers(), sl.add_provider(), sl.remove_provider()
sl.set_active_provider(), sl.probe_provider()

# Tool helpers
sl.get_tool_schemas(mode)   # "plan" | "execution"
sl.get_tool_executor(mode)
sl.build_mcp_servers(settings)
```

## Key Dependencies

- `openai>=1.50.0`, `openai-agents>=0.0.19`
- `prompt_toolkit>=3.0` (TUI)
- `pydantic-settings[toml]>=2.3.0`, `python-dotenv>=1.0.0`
- `httpx>=0.27.0` (custom TLS)
- `mcp>=1.0.0` — full MCP support requires Python 3.12+; degrades gracefully on 3.11
- `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `ruff>=0.4.0` (dev)
