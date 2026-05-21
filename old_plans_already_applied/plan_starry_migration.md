# Plan: Migrate DavyAgent → Starry (StarryLib / StarryCLI)

## Decision record

| Topic | Decision |
|---|---|
| Repo root | `davy_agent/` → `starry/` (user renames manually, Phase 10) |
| Library package | `davyagent/` → `starry_lib/` |
| CLI package | `cli/` + `davy_cli.py` → `starry_cli/` (with `main.py`, `__main__.py`, `dialogs.py`, `themes/`) |
| pyproject.toml | Single file; project name `"starry-lib"`; console script `starry_cli = "starry_cli.main:run"` |
| Entry-point group | `starry_lib.tools` |
| Default provider | None hardcoded in Python — `Optional[str] = None` |
| Config load order | Bundled `config/default.toml` → merge `~/.local/starry/config.toml` on top |
| Provider writes | `providers.py` writes to `~/.local/starry/config.toml` |
| Provider key | `[providers.davy]` (server alias, not brand) |
| `ssl_verify` cert | Copied to `~/.local/starry/certs/`; user config stores absolute path |
| `.env` location | `~/.local/starry/.env` (user moves before Phase 1) |
| `~/.local/` rename | User runs `mv ~/.local/davyagent ~/.local/starry` before Phase 1 |
| Runtime data paths | All `~/.local/davyagent/` → `~/.local/starry/` |
| `demo_LLM_lib.py` | Filename stays; imports and header updated in-place |
| `hello.py` | Does not exist; removed from plan |
| Phases | 10 phases, one commit each |

---

## Pre-conditions (user does these before Phase 1)

```bash
mv ~/.local/davyagent ~/.local/starry
mv /home/armando/davy_agent/.env ~/.local/starry/.env
```

---

## Phase 0 — Pre-flight verification

First action of the plan: verify pre-conditions are met.

```bash
ls ~/.local/starry/          # must exist
ls ~/.local/starry/.env      # must exist
```

Abort and ask user if either is missing.

---

## Phase 1 — Directory structure and import paths

**Git operations:**
```bash
git mv davyagent/ starry_lib/
# Create starry_cli/ from cli/ + davy_cli.py:
git mv davy_cli.py starry_cli/main.py
git mv cli/dialogs.py starry_cli/dialogs.py
git mv cli/themes/ starry_cli/themes/
git mv cli/__init__.py starry_cli/__init__.py
# cli/ is now empty — delete it
```

**New files to create:**
- `starry_cli/__main__.py` — two-line stub:
  ```python
  from starry_cli.main import run
  run()
  ```

**Import path updates (every affected file):**

| Old | New |
|---|---|
| `from davyagent.X import Y` | `from starry_lib.X import Y` |
| `import davyagent as da` | `import starry_lib as sl` |
| `from cli.themes.loader import …` | `from .themes.loader import …` |
| `from cli.dialogs import …` | `from .dialogs import …` |

**Files with import changes:**
- All `starry_lib/**/*.py` (internal cross-module imports)
- `starry_cli/main.py` (was davy_cli.py — 30+ import occurrences)
- `starry_cli/__init__.py`
- `starry_cli/themes/loader.py`
- `demo_LLM_lib.py`
- `tests/conftest.py`
- `tests/unit/` (10 files)
- `tests/integration/` (3 files)
- `tests/smoke/` (1 file)

**Commit:** `rename: davyagent→starry_lib, cli+davy_cli→starry_cli package`

---

## Phase 2 — pyproject.toml

| Key | Old | New |
|---|---|---|
| `[project] name` | `"davyagent"` | `"starry-lib"` |
| `packages.find include` | `["davyagent*", "cli*"]` | `["starry_lib*", "starry_cli*"]` |
| `py-modules` | `["davy_cli"]` | `[]` (removed) |
| `[project.scripts]` | `davyagent = "davy_cli:run"` | `starry_cli = "starry_cli.main:run"` |
| entry-point group | `[project.entry-points."davyagent.tools"]` | `[project.entry-points."starry_lib.tools"]` |

**Also:**
- Check `*.egg-info/` is in `.gitignore`; add if missing
- Delete `davyagent.egg-info/`
- Run `pip install -e .` → creates `starry_lib.egg-info/`

**Commit:** `chore: update pyproject.toml for starry_lib/starry_cli packages`

---

## Phase 3 — Runtime paths

Every `~/.local/davyagent/` in code → `~/.local/starry/`:

| File | Change |
|---|---|
| `starry_lib/sessions/store.py` | path + `DAVYAGENT_SESSIONS_DIR` → `STARRY_SESSIONS_DIR` |
| `starry_lib/agents/agent_store.py` | `~/.local/davyagent/agents/` → `~/.local/starry/agents/` |
| `starry_lib/tools/implementations/todowrite.py` | `~/.local/davyagent/todos.json` → `~/.local/starry/todos.json` |
| `starry_lib/config/settings.py` | `~/.local/davyagent/history` (×2) → `~/.local/starry/history` |
| `starry_cli/main.py` | `_DAVYAGENT_DIR` → `_STARRY_DIR = Path.home() / ".local" / "starry"` |
| `starry_cli/main.py` | `user.json`, `user_roles.json` paths under `_STARRY_DIR` |

**Commit:** `fix: update all runtime paths to ~/.local/starry/`

---

## Phase 4 — User config architecture

### `starry_lib/config/settings.py`
- `active_provider: str = "davy"` → `active_provider: Optional[str] = None`
- `app_block.get("active_provider", "davy")` → `app_block.get("active_provider")`
- `load_settings()` gains two-file merge:
  1. Load bundled `config/default.toml`
  2. If `~/.local/starry/config.toml` exists → deep-merge on top (user wins)
  3. Return merged `AppSettings`; `active_provider` may be `None`

### `starry_lib/providers.py`
- All config-write functions target `~/.local/starry/config.toml`
- `get_default_paths()` returns user config path

### `starry_cli/main.py`
- `load_dotenv()` → `load_dotenv(Path.home() / ".local" / "starry" / ".env")`
- First-run guard: if `settings.active_provider is None` → auto-enter `/setup` wizard

### Create `~/.local/starry/config.toml` (migrate current providers)
```bash
mkdir -p ~/.local/starry/certs
cp certs/davy.labs.lenovo.com.crt ~/.local/starry/certs/
```

Generated `~/.local/starry/config.toml`:
```toml
# StarryCLI user configuration

[app]
active_provider = "davy"

[providers.davy]
base_url      = "https://davy.labs.lenovo.com:5000/v1"
api_key_env   = "STARRY_API_KEY"
ssl_verify    = "/home/armando/.local/starry/certs/davy.labs.lenovo.com.crt"
default_model = "<value from current config/default.toml>"
label         = "<value from current config/default.toml>"
```

### Also in Phase 4
- Delete `starry_lib/davy.labs.lenovo.com.crt` (stale cert copy, now unused)

**Commit:** `feat: user config at ~/.local/starry/config.toml, no hardcoded provider defaults`

---

## Phase 5 — Bundled `config/default.toml` cleanup

- Remove `[providers.*]` section entirely
- Remove `active_provider = "davy"` from `[app]`
- Add comment: `# active_provider is set in ~/.local/starry/config.toml`
- `DavyCLI` → `StarryCLI` in all agent system prompts
- `# DavyAgent default configuration` → `# StarryLib default configuration`
- `.env.example`: `DAVY_API_KEY=...` → `STARRY_API_KEY=...`

**Commit:** `chore: clean bundled config, remove provider section`

---

## Phase 6 — Brand display strings

### Python files

| Location | Old | New |
|---|---|---|
| All file headers `NAME:`/`DESCRIPTION:` | `DavyAgent`, `DavyCLI` | `StarryLib`, `StarryCLI` |
| `starry_lib/__init__.py` docstring | `"DavyAgent — multi-agent AI library"` | `"StarryLib — multi-agent AI library"` |
| `starry_lib/__init__.py` example | `import davyagent as da` | `import starry_lib as sl` |
| `starry_lib/tools/implementations/webfetch.py` | `"DavyAgent/0.1"` | `"StarryLib/0.1"` |
| `starry_lib/tools/registry.py` (×2) | `"davyagent.tools"` | `"starry_lib.tools"` |
| `starry_lib/tools/registry.py` docstring | `"DavyAgent tool protocol"` | `"StarryLib tool protocol"` |
| `starry_lib/config/settings.py` docstrings | `DavyAgent` | `StarryLib` |
| `starry_lib/providers.py` docstring | `davyagent` example | `starry_lib` |
| `demo_LLM_lib.py` header + NOTES | `DavyAgent`, `DAVY_API_KEY` | `StarryLib`, `STARRY_API_KEY` |

**`starry_cli/main.py` (69 occurrences):**
- `DAVYCLI` → `STARRYCLI`
- `DavyCLI` → `StarryCLI`
- `DavyAgent` → `StarryLib`
- `argparse` prog / description
- All display labels, dialog titles, status messages

**Env var name references in code:**
- `DAVY_API_KEY` → `STARRY_API_KEY`
- `DAVYAGENT_SESSIONS_DIR` → `STARRY_SESSIONS_DIR`

**Commit:** `rename: update all brand display strings and identifiers`

---

## Phase 7 — `install.sh`

| Old | New |
|---|---|
| `INSTALL_DIR="$HOME/.local/davyagent"` | `INSTALL_DIR="$HOME/.local/starry"` |
| `LAUNCHER="$BIN_DIR/davyagent"` | `LAUNCHER="$BIN_DIR/starry_cli"` |
| `for item in davyagent cli davy_cli.py …` | `for item in starry_lib starry_cli` |
| Display text | `"StarryCLI installer"`, `"Installing StarryCLI"` etc. |
| Launcher shebang comment | `# StarryCLI launcher` |
| Usage examples | `starry_cli`, `starry_cli --provider` |
| *(new)* cert copy step | `cp -r certs/ $INSTALL_DIR/certs/` |
| *(new)* config check | warn if `~/.local/starry/config.toml` missing, point to `/setup` |

**Commit:** `chore: update install.sh for starry layout`

---

## Phase 8 — Tests

Update all test files (13 files):
- `from davyagent.X` → `from starry_lib.X`
- `import davyagent` → `import starry_lib`

Files:
- `tests/conftest.py`
- `tests/unit/test_agent_config.py`
- `tests/unit/test_config.py`
- `tests/unit/test_llm_kwargs.py`
- `tests/unit/test_mcp_client.py`
- `tests/unit/test_provider_client.py`
- `tests/unit/test_providers.py`
- `tests/unit/test_routing.py`
- `tests/unit/test_skill_loader.py`
- `tests/unit/test_tool_scoping.py`
- `tests/unit/test_tools.py`
- `tests/integration/test_agent.py`
- `tests/integration/test_skills_integration.py`
- `tests/integration/test_streaming.py`
- `tests/smoke/test_smoke_providers.py`

Run `pytest tests/unit/ -v` → fix failures.
Run `pytest tests/integration/ -v` → fix failures.

**Commit only after pytest is green:**
`test: update imports to starry_lib, verify suite passes`

---

## Phase 9 — Documentation and tooling

**Files:**
- `AGENTS.md` — package paths, file names, runtime paths, entry-point group, console script
- `CLAUDE.md` — same sweep
- `starry_lib/tools/TOOLS.md` — todos path, any other davy refs
- `docs/user_manual.md` — brand, API key, paths, pip install name
- `docs/cli_developers_guide.md` — same
- `.claude/settings.local.json` — update all Bash/Read permission entries:
  - `davyagent` → `starry_lib` / `starry_cli` / `starry`
  - `~/.local/davyagent/` → `~/.local/starry/`
  - `davy_cli.py` → `starry_cli`
- `plan_massive_renaming.md` → move to `old_plans_already_applied/`
- `plan_starry_migration.md` → move to `old_plans_already_applied/` when done

**Commit:** `docs: update AGENTS.md, CLAUDE.md, docs/, and .claude/settings`

---

## Phase 10 — Final cleanup and repo rename

1. `pip install -e .` — confirm `starry-lib.egg-info/` created, no `davyagent.egg-info/`
2. `pytest` — full suite must be green
3. Verify `starry_cli` in terminal launches the TUI
4. **Commit:** `chore: final verification, all phases complete`
5. **User runs in shell (outside Claude Code):**
   ```bash
   mv /home/armando/davy_agent /home/armando/starry
   ```

---

## Files NOT in scope

- `old_plans_already_applied/` — historical docs, leave as-is
- `certs/davy.labs.lenovo.com.crt` — domain certificate, must keep filename
- `config/default.toml` `base_url` and `ssl_verify` values — server endpoint, not brand
- `.git/` — version history internals
- `.venv/` — third-party packages
