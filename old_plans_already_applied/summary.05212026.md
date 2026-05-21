# Migration Session Summary — 05/21/2026

**Branch:** main  
**Plan file:** `plan_starry_migration.md`  
**Goal:** Migrate DavyAgent → Starry (StarryLib / StarryCLI), 10 phases.

---

## Pre-conditions verified

Both were already satisfied before starting:
- `~/.local/starry/` exists (renamed from `~/.local/davyagent/` by user)
- `~/.local/starry/.env` exists
- `~/.local/davyagent/` no longer exists

---

## Phases completed this session

### Phase 1 — Directory structure and import paths
**Commit:** `e3622c5`

- `git mv davyagent/ → starry_lib/` (83 files)
- `git mv cli/ + davy_cli.py → starry_cli/` (19 files: `main.py`, `dialogs.py`, `themes/`, `__init__.py`)
- Created `starry_cli/__main__.py` entry-point stub
- Replaced all `from davyagent.` → `from starry_lib.` across `starry_lib/`, `starry_cli/`, `tests/`, `demo_LLM_lib.py`
- Replaced `from cli.themes.` / `from cli.dialogs` → relative imports in `starry_cli/main.py`

**Bug found and fixed (separate commit `db9860b`):**  
`patch()` string targets in unit tests (e.g. `"davyagent.tools.mcp_client._connect_stdio"`) are runtime strings, not import statements — the sed pass missed them. Fixed in `test_mcp_client.py`, `test_providers.py`, `test_tool_scoping.py`.

---

### Phase 2 — pyproject.toml
**Commit:** `b23380c`

| Field | Before | After |
|---|---|---|
| `[project] name` | `"davyagent"` | `"starry-lib"` |
| `packages.find include` | `["davyagent*", "cli*"]` | `["starry_lib*", "starry_cli*"]` |
| `py-modules` | `["davy_cli"]` | removed |
| `[project.scripts]` | `davyagent = "davy_cli:run"` | `starry_cli = "starry_cli.main:run"` |
| entry-point group | `"davyagent.tools"` | `"starry_lib.tools"` |

**Additional:** Upgraded `setuptools` in `.venv` from 59.6.0 → 82.0.1 (old version could not read `pyproject.toml` for editable installs). Used `python3.11 -m pip` to work around broken shebang in `.venv/bin/pip` (still points to old `~/.local/davy_agent` path).

Package verified: `pip show starry-lib` → `Name: starry-lib, Version: 0.1.0`.

---

### Phase 3 — Runtime paths
**Commit:** `ed75091`

All `~/.local/davyagent/` hardcoded paths replaced with `~/.local/starry/`:

| File | Change |
|---|---|
| `starry_lib/sessions/store.py` | `DAVYAGENT_SESSIONS_DIR` → `STARRY_SESSIONS_DIR`; path updated |
| `starry_lib/agents/agent_store.py` | `_STORE_DIR` path updated |
| `starry_lib/agents/agent_config.py` | Header comment updated |
| `starry_lib/tools/implementations/todowrite.py` | `_TODO_FILE` path updated |
| `starry_lib/config/settings.py` | `history_file` default updated (×2) |
| `starry_cli/main.py` | `_DAVYAGENT_DIR` → `_STARRY_DIR` |
| `tests/conftest.py` | `MINIMAL_TOML` history_file path updated |

---

### Phase 4 — User config architecture
**Commit:** `4218ce2`

**`starry_lib/config/settings.py`:**
- `active_provider: str = "davy"` → `active_provider: str | None = None`
- `load_settings()` now does a two-file merge:
  1. Load bundled `config/default.toml`
  2. Deep-merge `~/.local/starry/config.toml` on top (user values win)
- `.env` load order: project `.env` first, then `~/.local/starry/.env` (override=True)
- Active-provider validation guarded: skipped when `None`
- Added `_deep_merge()` helper; `_USER_CONFIG` and `_USER_ENV` path constants

**`starry_lib/providers.py`:**
- `get_default_paths()` now returns `(~/.local/starry/config.toml, ~/.local/starry/.env)` — all provider write operations target the user config

**`starry_cli/main.py`:**
- Startup sequence handles `active_provider=None` without crashing
- First-run guard: if no active provider, `_app_mode = "setup"` → TUI starts directly in setup wizard

**External files created:**
- `~/.local/starry/config.toml` — user config with `davy` provider, `STARRY_API_KEY`, cert at `/home/armando/.local/starry/certs/davy.labs.lenovo.com.crt`
- Cert was already in `~/.local/starry/certs/` from the pre-condition rename

**Deleted:** `starry_lib/davy.labs.lenovo.com.crt` (stale copy, now unused)

---

## Verification

Unit test suite run after each phase and after bug fix:

```
166 passed, 0 failed   (pytest tests/unit/ -v)
```

Import smoke-check: `import starry_lib` → resolves to `starry_lib/__init__.py` ✓

---

## Known remaining items (not bugs)

- **`.venv/bin/pip` shebang is broken** — points to old `/home/armando/davy_agent/.venv/bin/python3.11`. Workaround: always use `python3.11 -m pip` instead of `pip` directly. This will be permanently fixed when the venv is rebuilt (outside scope of this migration).
- **5 test module docstrings** still say `"Unit tests for davyagent.xxx."` — will be cleaned in Phase 6 (brand strings).
- **`starry_lib/tools/registry.py` line 88**: `entry_points(group="davyagent.tools")` — this is a functional entry-point group name that Phase 6 will update to `"starry_lib.tools"`. Third-party tool plugins are not loaded correctly until Phase 6 completes.

---

## Phases remaining

| Phase | Description |
|---|---|
| **5** | `config/default.toml` cleanup — strip `[providers.*]`, remove `active_provider`, update system prompts (`DavyCLI` → `StarryCLI`) |
| **6** | Brand display strings — all `DavyAgent`/`DavyCLI` in Python files, env var names (`DAVY_API_KEY` → `STARRY_API_KEY`), `davyagent.tools` entry-point group in `registry.py` |
| **7** | `install.sh` — paths, launcher name, cert copy step, config check |
| **8** | Tests — run full suite, fix remaining failures |
| **9** | Docs — `AGENTS.md`, `CLAUDE.md`, `docs/`, `.claude/settings.local.json` |
| **10** | Final verification — `pip install -e .`, full pytest, TUI launch check; user renames repo dir |

---

## How to resume

Open this repo in Claude Code and reference this file plus `plan_starry_migration.md`.  
Start with **Phase 5**.

```bash
# Reminder: use python3.11 -m pip, not pip directly
/home/armando/starry/.venv/bin/python3.11 -m pytest tests/unit/ -v
```
