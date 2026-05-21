# DavyAgent — Session 01 State Document

## What this document is

A snapshot of the project state as of 2026-04-04, capturing what was
built, what works, what is broken, and what needs to be done next.

---

## Project Summary

**DavyAgent** is a Python CLI AI agent framework with a Claude Code-like
terminal REPL experience. It supports multiple LLM providers
(DavyAI/Lenovo, OpenWebUI, OpenAI), named agent roles, switchable
themes, and MCP agentic tools — all via a Rich + prompt-toolkit terminal
UI. No web app; purely a terminal tool.

- Source: `/home/armando/davy_agent/`
- Install: `~/.local/davyagent/`
- Launcher: `~/.local/bin/davyagent`

---

## File Tree

```
davy_agent/
├── pyproject.toml               # build, deps, ruff, pytest config
├── install.sh                   # production installer → ~/.local/davyagent/
├── setup.sh                     # dev bootstrap (venv in ./venv)
├── README.md                    # quick-start user guide
├── plan.md                      # original feature spec (DO NOT DELETE)
├── .env.example                 # API key template
├── config/
│   ├── default.toml             # all configuration (providers, agents, theme, ui, mcp)
│   └── themes/
│       ├── dark.ini
│       ├── light.ini
│       ├── dracula.ini
│       ├── nord.ini
│       └── mono.ini
├── certs/                       # TLS certificate for DavyAI (gitignored)
├── docs/
│   └── user_manual.md           # full 13-section user reference
├── davyagent/
│   ├── __init__.py
│   ├── config/
│   │   └── settings.py          # pydantic settings model + loader
│   ├── llm/
│   │   └── client.py            # AsyncOpenAI wrapper + list_models()
│   ├── agents/
│   │   ├── base.py              # BaseAgent dataclass
│   │   ├── roles.py             # build_agent() factory
│   │   └── orchestrator.py      # Orchestrator: run/switch_role/switch_provider
│   ├── tools/
│   │   └── registry.py          # build_mcp_servers() (Python 3.12+ only)
│   └── cli/
│       ├── renderer.py          # Rich console, theme, render_stream()
│       ├── repl.py              # prompt-toolkit REPL loop
│       ├── app.py               # typer main entry point
│       └── commands/
│           ├── provider.py      # `davyagent provider` sub-commands
│           └── theme.py         # `davyagent theme` sub-commands
└── tests/
    ├── conftest.py              # fixtures: tmp_config, mock_completion, etc.
    ├── unit/
    │   ├── test_config.py       # 10 tests (9 pass, 1 FAIL — see bugs)
    │   ├── test_provider_client.py  # 6 tests (all pass)
    │   └── test_theme.py        # 4 tests (all pass)
    ├── integration/
    │   ├── test_agent.py        # 5 tests (all pass)
    │   └── test_streaming.py    # 4 tests (all pass)
    ├── cli/
    │   ├── test_cli_provider.py # 6 tests (all pass)
    │   └── test_cli_theme.py    # 5 tests (all pass)
    └── smoke/
        └── test_smoke_providers.py  # 2 live tests (skipped by default)
```

---

## Architecture

### Three-layer stack

```
User (terminal)
    │
    ▼
cli/repl.py  ←→  cli/commands/{provider,theme}.py
    │                    │
    ▼                    ▼
agents/orchestrator.py   cli/app.py (typer entry point)
    │
    ├── agents/roles.py  (build_agent factory)
    ├── agents/base.py   (BaseAgent dataclass)
    └── llm/client.py    (AsyncOpenAI, list_models)
            │
            ▼
    LLM Provider (DavyAI / OpenWebUI / OpenAI)
```

### Key design decisions

- **No openai-agents SDK** — uses raw `AsyncOpenAI.chat.completions.create(stream=True)`.
  Reason: openai-agents SDK requires Python 3.12+, machine has 3.11.0rc1.
- **MCP servers deferred** — `tools/registry.py` handles the Python 3.12 check
  gracefully (returns `[]`). Config is already wired; activation requires 3.12+.
- **Semantic styles** — all Rich styles use names like `"agent.prefix"`, never
  raw colour strings. Themes are `.ini` files merged with inline TOML overrides.
- **api_key never in TOML** — only `api_key_env` key name stored; value read from
  the environment at runtime via `ProviderConfig.api_key` property.
- **Editable install** — `pip install -e $INSTALL_DIR` so the package code lives
  at `~/.local/davyagent/davyagent/` and `__file__` resolves correctly there.

---

## Test Status

```
pytest -m 'not live'   →   39 passed, 1 failed, 2 deselected
```

| File | Tests | Status |
|------|-------|--------|
| unit/test_config.py | 10 | 9 pass / **1 FAIL** |
| unit/test_provider_client.py | 6 | all pass |
| unit/test_theme.py | 4 | all pass |
| integration/test_agent.py | 5 | all pass |
| integration/test_streaming.py | 4 | all pass |
| cli/test_cli_provider.py | 6 | all pass |
| cli/test_cli_theme.py | 5 | all pass |
| smoke/test_smoke_providers.py | 2 | skipped (live) |

---

## Known Bugs

### Bug 1 — `test_missing_env_var_raises_runtime_error` (unit test failure)

**Test:** `tests/unit/test_config.py::test_missing_env_var_raises_runtime_error`

**What it tests:** After calling `monkeypatch.delenv("DAVY_API_KEY")`, accessing
`settings.providers["davy"].api_key` should raise `RuntimeError`.

**Why it fails:** `load_settings()` calls `load_dotenv(env_file)` which reloads
the key from the project's `.env.example` (or the real `.env` if found). Because
`python-dotenv` runs after `monkeypatch.delenv`, the variable gets re-populated,
so no `RuntimeError` is raised.

**Root cause:** `load_dotenv()` is called inside `load_settings()`. The test
patches the env var first, then calls `load_settings()`, which re-injects it.

**Fix needed:** In the test, monkeypatch the env var *after* calling
`load_settings()`, not before. Or: in the test, pass `override=True` to confirm
the behaviour, or ensure `load_dotenv` doesn't override already-cleared vars.
The simplest correct fix is to reorder the test:

```python
def test_missing_env_var_raises_runtime_error(tmp_config, monkeypatch):
    settings = load_settings(tmp_config / "config" / "default.toml")
    monkeypatch.delenv("DAVY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="davy"):
        _ = settings.providers["davy"].api_key
```

---

### Bug 2 — Path resolution fails from installed location (CRITICAL)

**Symptom:** `davyagent provider test davy` reports:

```
ssl_verify cert not found at '/home/armando/davy_agent/certs/davy.labs.lenovo.com.crt'
```

The path points to the **source** directory, not `~/.local/davyagent/certs/`.

**Root cause:** `_find_project_root()` in `settings.py` walks up from
`__file__` to find `config/default.toml`. With an editable install
(`pip install -e ~/.local/davyagent/`), `__file__` for
`davyagent/config/settings.py` resolves to the install directory
`~/.local/davyagent/davyagent/config/settings.py` — which is correct.

However, the walker finds `~/.local/davyagent/config/default.toml` first
(that's correct too), so `root = ~/.local/davyagent`. Then `env_file =
root / ".env"` which is `~/.local/davyagent/.env` — **also correct**.

**Re-evaluation:** After install, the test showed the key was reading from
`.env.example` (`your-d***`). That means `load_dotenv` found the *source* `.env`
or `.env.example`, not `~/.local/davyagent/.env`. This can happen if:

1. A stale `.env` in the source dir (`/home/armando/davy_agent/.env`) contains
   a placeholder value, and
2. `_find_project_root()` is somehow resolving to the source dir instead of the
   install dir.

**Definitive check needed:** Add a debug print to `load_settings()` to confirm
exactly which `config_path` and `env_file` paths are being used at runtime from
the installed launcher.

**Likely fix:** Either:

- Option A: Pass `config_path` explicitly from the launcher (most reliable).
  Add an env var `DAVYAGENT_CONFIG` and check it first in `load_settings()`.
- Option B: Introduce a `DAVYAGENT_ROOT` env var set by the launcher script to
  `~/.local/davyagent`, and use that in `_find_project_root()` when set.
- Option C: Change the launcher to set the config path explicitly:
  ```bash
  exec "$VENV/bin/davyagent" --config "$INSTALL_DIR/config/default.toml" "$@"
  ```
  This guarantees root = `~/.local/davyagent` regardless of `__file__`.

**Option C is the simplest and most robust** — zero code change, just
update `install.sh` to embed `--config` in the launcher.

---

## Pending Work (in priority order)

### P0 — Must fix before the tool is usable

1. **Fix Bug 2 (path resolution)** — implement Option C: update the launcher
   written by `install.sh` to include `--config $INSTALL_DIR/config/default.toml`.
   Re-run `bash install.sh`, then test `davyagent provider test davy`.

2. **Fix Bug 1 (unit test)** — reorder the monkeypatch call in
   `test_missing_env_var_raises_runtime_error` as shown above. All 40 tests
   should then pass.

### P1 — End-to-end validation (after P0 is resolved)

3. **Run full REPL session** — start `davyagent`, send a message, confirm
   streaming response renders correctly in Rich Markdown.

4. **Test slash commands** — `/role coder`, `/provider openai`, `/tools`,
   `/clear`, `/exit` all function correctly.

5. **Test theme switching** — `davyagent theme set dracula`, restart, confirm
   colours changed.

6. **Test provider commands** — `davyagent provider list`, `provider use openwebui`,
   `provider test openwebui` all work.

### P2 — Nice to have / future sessions

7. **Python 3.12 upgrade** — once 3.12 is available on the machine, re-test MCP
   server activation (`mcp-server-git`, `mcp-server-fetch`, `mcp-server-sqlite`).

8. **Smoke tests** — run `pytest -m live` against real DavyAI endpoint after P0
   is resolved and API key is confirmed working.

9. **Conversation history** — currently the REPL maintains an in-memory
   `messages` list but it is reset on exit. Adding persistence to
   `~/.davyagent_history.json` or SQLite would enable cross-session memory.

10. **`provider add` wizard** — the interactive add command works but relies on
    regex TOML writing. Consider adding `tomli-w` as a dependency for reliable
    TOML serialisation.

---

## Configuration Quick Reference

**Install paths:**

| Path | Contents |
|------|----------|
| `~/.local/davyagent/` | Install root |
| `~/.local/davyagent/.venv/` | Isolated Python 3.11 venv |
| `~/.local/davyagent/config/default.toml` | All configuration |
| `~/.local/davyagent/config/themes/` | Bundled theme .ini files |
| `~/.local/davyagent/certs/` | TLS certificates |
| `~/.local/davyagent/.env` | API keys (not synced by rsync) |
| `~/.local/bin/davyagent` | Bash launcher |
| `~/.davyagent_history` | REPL input history |

**API keys (.env):**

```
DAVY_API_KEY=your-key
OPENWEBUI_API_KEY=sk-your-key
OPENAI_API_KEY=sk-your-key
```

**Key TOML sections:**

```toml
[app]
active_provider = "davy"
active_role     = "assistant"

[providers.davy]
base_url      = "https://davy.labs.lenovo.com:5000/v1"
api_key_env   = "DAVY_API_KEY"
ssl_verify    = "certs/davy.labs.lenovo.com.crt"
default_model = "gpt-oss-120b-thinking"

[theme]
name       = "dark"
code_theme = "monokai"
```

---

## How to Run

```bash
# Start REPL (default: davy provider, assistant role)
davyagent

# Override at startup
davyagent --provider openai --role coder

# Provider management
davyagent provider list
davyagent provider test davy
davyagent provider use openai

# Theme management
davyagent theme list
davyagent theme set dracula
davyagent theme preview nord

# Dev: run tests
cd /home/armando/davy_agent
.venv/bin/pytest

# Reinstall after changes
bash install.sh
```

---

## How to Resume Development

1. Open `/home/armando/davy_agent/` as the working directory.
2. Read this file (`Session01.md`) to re-orient.
3. Fix P0 bugs first (Bug 2 launcher path → Bug 1 test reorder).
4. Run `.venv/bin/pytest` — should be 40/40 green.
5. Run `bash install.sh` to push the fix to `~/.local/davyagent/`.
6. Run `davyagent provider test davy` to confirm end-to-end.
7. Then proceed with P1 manual validation.

---

*Last updated: 2026-04-04 — end of Session 01*
