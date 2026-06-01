# Plan: Configuration Directories (#10 and #11) — [COMPLETE]

## Goal

**#10** — Move the user config files from `~/.local/starry/` into a new
subdirectory `~/.local/starry/conf/`.

**#11** — Support a per-project config overlay in `pwd/.starry/` that
overrides the global config for the current working directory.

---

## New Directory Layout

### Global (user-wide)
```
~/.local/starry/              ← app root (unchanged)
  conf/                       ← NEW — all config lives here now
    config.toml               ← active provider, role, format
    .env                      ← API keys
    user.json                 ← TUI preferences (theme, exec mode)
    user_roles.json           ← user-defined roles
    agents/                   ← named agent configs (<name>.json)
    sessions/                 ← saved sessions (<id>/session.json)
```

### Project (directory-scoped, wins over global)
```
pwd/
  .starry/                    ← NEW — project config overlay
    config.toml               ← overrides conf/config.toml
    .env                      ← overrides conf/.env
    user.json                 ← overrides conf/user.json
    user_roles.json           ← merged with global (project wins)
    agents/                   ← checked before global agents/
```

`sessions/` stays global only — sessions are personal, not
project-scoped.

---

## Config Load Order (final precedence, later wins)

**TOML settings:**
```
1. config/default.toml              (bundled defaults)
2. ~/.local/starry/conf/config.toml (global user config)
3. pwd/.starry/config.toml          (project override)
```

**Environment variables:**
```
1. ~/.local/starry/conf/.env        (global)
2. pwd/.starry/.env                 (project — wins)
```

**Agent file resolution (get_agent):**
```
1. pwd/.starry/agents/<name>.json   (project — checked first)
2. ~/.local/starry/conf/agents/<name>.json  (global fallback)
```

**Role lists (list_agents / list_user_roles):**
```
Union of global + project files.
On a name collision, the project entry wins.
```

---

## Step-by-Step Implementation

Every step shows the EXACT lines to change: what exists now and what
to write instead. Do not change anything else in each file.

---

### Step 1 — Create `starry_lib/config/paths.py` ✓

This is a **new file**. It is the single place that knows all runtime
paths. Every other module must import from here instead of
hardcoding paths.

Create the file with exactly this content:

```python
#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       paths.py
# DESCRIPTION: Runtime path constants for StarryLib
# SUMMARY: Single source of truth for all config paths.
# NOTES: No other module should hardcode ~/.local/starry.
#        Import global_conf_dir() or project_conf_dir() here.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Runtime path constants for StarryLib."""

from pathlib import Path

_INSTALL_ROOT = Path.home() / ".local" / "starry"
_GLOBAL_CONF = _INSTALL_ROOT / "conf"


def global_conf_dir() -> Path:
    """Return ~/.local/starry/conf/ (global config root)."""
    return _GLOBAL_CONF


def project_conf_dir() -> Path | None:
    """Return pwd/.starry/ if it exists, else None.

    Only the current working directory is checked.
    No directory tree walk is performed.
    """
    p = Path.cwd() / ".starry"
    return p if p.is_dir() else None


def effective_conf_dirs() -> list[Path]:
    """Return [global_conf_dir()] plus project dir if it exists.

    The project dir is always last — it wins on conflicts.
    Example return values:
      [~/.local/starry/conf/]               (no .starry/ found)
      [~/.local/starry/conf/, pwd/.starry/] (.starry/ found)
    """
    dirs = [_GLOBAL_CONF]
    proj = project_conf_dir()
    if proj is not None:
        dirs.append(proj)
    return dirs
```

---

### Step 2 — Update `starry_lib/config/settings.py` ✓

**What to change:** replace the two path constants and extend
`load_settings()` to load the project config layer.

**2a. Replace the two path constants (lines 152–155).**

Remove:
```python
_USER_CONFIG = (
    Path.home() / ".local" / "starry" / "config.toml"
)
_USER_ENV = Path.home() / ".local" / "starry" / ".env"
```

Write instead:
```python
from starry_lib.config.paths import (
    global_conf_dir,
    project_conf_dir,
)

_USER_CONFIG = global_conf_dir() / "config.toml"
_USER_ENV = global_conf_dir() / ".env"
```

**2b. Extend `load_settings()` to add the project layer.**

The function already loads `_USER_CONFIG` and then calls
`load_dotenv(_USER_ENV)`. After those two lines, add the
project layer. Find this block inside `load_settings()`:

```python
        if _USER_CONFIG.exists():
            user_raw = tomllib.loads(
                _USER_CONFIG.read_text()
            )
            raw = _deep_merge(raw, user_raw)

        # Load env: project .env first, user .env wins
        proj_env = root / ".env"
        if proj_env.exists():
            load_dotenv(proj_env)
        if _USER_ENV.exists():
            load_dotenv(_USER_ENV, override=True)
```

Replace it with:
```python
        if _USER_CONFIG.exists():
            user_raw = tomllib.loads(
                _USER_CONFIG.read_text()
            )
            raw = _deep_merge(raw, user_raw)

        # Project config layer (pwd/.starry/config.toml)
        _proj = project_conf_dir()
        if _proj is not None:
            _proj_cfg = _proj / "config.toml"
            if _proj_cfg.exists():
                proj_raw = tomllib.loads(
                    _proj_cfg.read_text()
                )
                raw = _deep_merge(raw, proj_raw)

        # Load env: project .env first, user .env wins
        proj_env = root / ".env"
        if proj_env.exists():
            load_dotenv(proj_env)
        if _USER_ENV.exists():
            load_dotenv(_USER_ENV, override=True)

        # Project .env wins over everything
        if _proj is not None:
            _proj_env = _proj / ".env"
            if _proj_env.exists():
                load_dotenv(_proj_env, override=True)
```

Note: `_deep_merge` already exists in this file. Do not create
a second one.

---

### Step 3 — Update `starry_lib/agents/agent_store.py` ✓

**What to change:** move the agents directory from
`~/.local/starry/agents/` to `~/.local/starry/conf/agents/`,
and make `get_agent()` and `list_agents()` check the project
directory first.

**3a. Replace the store dir constant (lines 28–30).**

Remove:
```python
_STORE_DIR = (
    Path.home() / ".local" / "starry" / "agents"
)
```

Write instead:
```python
from starry_lib.config.paths import (
    global_conf_dir,
    project_conf_dir,
)

_STORE_DIR = global_conf_dir() / "agents"
```

**3b. Replace `get_agent()`.**

Remove:
```python
def get_agent(name: str) -> AgentConfig | None:
    """Return AgentConfig by name, or None."""
    p = _path(name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return AgentConfig(**data)
    except Exception:
        return None
```

Write instead:
```python
def get_agent(name: str) -> AgentConfig | None:
    """Return AgentConfig by name, or None.

    Checks pwd/.starry/agents/ first, then the global dir.
    """
    proj = project_conf_dir()
    if proj is not None:
        proj_p = proj / "agents" / f"{name}.json"
        if proj_p.exists():
            try:
                data = json.loads(proj_p.read_text())
                return AgentConfig(**data)
            except Exception:
                pass
    p = _path(name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return AgentConfig(**data)
    except Exception:
        return None
```

**3c. Replace `list_agents()`.**

Remove:
```python
def list_agents() -> list[AgentConfig]:
    """Return all stored AgentConfig objects."""
    d = _ensure_dir()
    result: list[AgentConfig] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            result.append(AgentConfig(**data))
        except Exception:
            pass
    return result
```

Write instead:
```python
def list_agents() -> list[AgentConfig]:
    """Return all stored AgentConfig objects.

    Merges global and project agents.
    Project agents shadow global agents with the same name.
    """
    d = _ensure_dir()
    seen: dict[str, AgentConfig] = {}

    # Load global agents first
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            cfg = AgentConfig(**data)
            seen[cfg.name] = cfg
        except Exception:
            pass

    # Project agents override global on name collision
    proj = project_conf_dir()
    if proj is not None:
        proj_agents = proj / "agents"
        if proj_agents.is_dir():
            for f in sorted(
                proj_agents.glob("*.json")
            ):
                try:
                    data = json.loads(f.read_text())
                    cfg = AgentConfig(**data)
                    seen[cfg.name] = cfg
                except Exception:
                    pass

    return list(seen.values())
```

`save_agent()`, `delete_agent()`, and `agent_exists()` do not
change — they always operate on the global dir.

---

### Step 4 — Update `starry_lib/sessions/store.py` ✓

**What to change:** move the sessions directory from
`~/.local/starry/sessions/` to `~/.local/starry/conf/sessions/`.

Find `_sessions_dir()` (lines 38–47):

```python
def _sessions_dir() -> Path:
    """Return (and create) the sessions root."""
    base = Path(
        os.environ.get(
            "STARRY_SESSIONS_DIR",
            Path.home() / ".local" / "starry" / "sessions",
        )
    )
    base.mkdir(parents=True, exist_ok=True)
    return base
```

Replace with:
```python
from starry_lib.config.paths import global_conf_dir


def _sessions_dir() -> Path:
    """Return (and create) the sessions root."""
    base = Path(
        os.environ.get(
            "STARRY_SESSIONS_DIR",
            str(global_conf_dir() / "sessions"),
        )
    )
    base.mkdir(parents=True, exist_ok=True)
    return base
```

Note: `os.environ.get` needs a string default, so wrap
`global_conf_dir() / "sessions"` in `str(...)`. Sessions stay
global only — no project-level sessions.

---

### Step 5 — Update `starry_lib/providers.py` ✓

**What to change:** `get_default_paths()` returns the paths for
`config.toml` and `.env`. Move both from `~/.local/starry/` to
`~/.local/starry/conf/`.

Find `get_default_paths()` (around line 224):

```python
def get_default_paths() -> tuple[Path, Path]:
    """Return (config_path, env_path) for the
    user config layout at ~/.local/starry/.

    Returns:
        (~/.local/starry/config.toml,
         ~/.local/starry/.env) as Paths.
    """
    base = Path.home() / ".local" / "starry"
    base.mkdir(parents=True, exist_ok=True)
    return (
        base / "config.toml",
        base / ".env",
    )
```

Replace with:
```python
from starry_lib.config.paths import global_conf_dir


def get_default_paths() -> tuple[Path, Path]:
    """Return (config_path, env_path) for the
    user config layout at ~/.local/starry/conf/.

    Returns:
        (~/.local/starry/conf/config.toml,
         ~/.local/starry/conf/.env) as Paths.
    """
    base = global_conf_dir()
    base.mkdir(parents=True, exist_ok=True)
    return (
        base / "config.toml",
        base / ".env",
    )
```

---

### Step 6 — Update `starry_cli/main.py` ✓

**What to change:** `_STARRY_DIR` points to the old location.
Update it and also update `_load_user_roles()` to merge in
project roles.

**6a. Replace `_STARRY_DIR` (lines 935–938).**

Remove:
```python
_STARRY_DIR = Path.home() / ".local" / "starry"
_STARRY_DIR.mkdir(parents=True, exist_ok=True)
USER_PREFS_PATH = _STARRY_DIR / "user.json"
USER_ROLES_PATH = _STARRY_DIR / "user_roles.json"
```

Write instead:
```python
from starry_lib.config.paths import (
    global_conf_dir,
    project_conf_dir,
)

_STARRY_DIR = global_conf_dir()
_STARRY_DIR.mkdir(parents=True, exist_ok=True)
USER_PREFS_PATH = _STARRY_DIR / "user.json"
USER_ROLES_PATH = _STARRY_DIR / "user_roles.json"
```

`USER_PREFS_PATH` and `USER_ROLES_PATH` keep their same names
and are derived from `_STARRY_DIR`, so all existing code that
uses them gets the new path for free.

**6b. Update `_load_user_roles()` to merge project roles.**

Find `_load_user_roles()`. It currently reads only
`USER_ROLES_PATH`. Add a project merge after that:

Existing code (paraphrased):
```python
def _load_user_roles() -> None:
    if not USER_ROLES_PATH.exists():
        return
    ...load USER_ROLES_PATH into _user_roles...
```

After the existing load of `USER_ROLES_PATH` completes, add:
```python
    # Merge project roles — project wins on name collision
    proj = project_conf_dir()
    if proj is not None:
        proj_roles_path = proj / "user_roles.json"
        if proj_roles_path.exists():
            try:
                proj_data = json.loads(
                    proj_roles_path.read_text()
                )
                # proj_data is a dict; merge into _user_roles
                _user_roles.update(proj_data)
            except Exception:
                pass
```

`_save_user_roles()` does not change — it always writes to the
global `USER_ROLES_PATH`.

---

### Step 7 — Migration on First Launch ✓

Add a migration check at startup in `starry_cli/main.py`, before
settings are loaded. The migration runs once automatically if the
old layout exists and the new `conf/` directory does not.

Add this function and call it early in `main()`:

```python
def _migrate_conf_dir() -> None:
    """Move config files from ~/.local/starry/ into conf/.

    Runs only when conf/ does not exist yet and at least one
    config file is present in the old location.
    """
    old = Path.home() / ".local" / "starry"
    new = old / "conf"

    if new.exists():
        return  # Already migrated, nothing to do

    candidates = [
        "config.toml",
        ".env",
        "user.json",
        "user_roles.json",
        "agents",
        "sessions",
    ]
    found = [
        old / name
        for name in candidates
        if (old / name).exists()
    ]
    if not found:
        return  # Nothing to migrate

    new.mkdir(parents=True, exist_ok=True)
    import shutil
    for src in found:
        dst = new / src.name
        if src.is_dir():
            shutil.copytree(src, dst)
            shutil.rmtree(src)
        else:
            src.rename(dst)
    print("Migrated config to ~/.local/starry/conf/")
```

Call `_migrate_conf_dir()` as the very first line of `main()`
before any other initialisation.

---

### Step 8 — Update `install.sh` and `.env.example` ✓

**`install.sh`**: find every `mkdir` that creates
`~/.local/starry/` and add a line to also create
`~/.local/starry/conf/`. Find every instruction that copies or
references `.env`, `config.toml`, `user.json`, or `agents/`
under `~/.local/starry/` and update the path to
`~/.local/starry/conf/`.

**`.env.example`**: find the comment that says to copy to
`~/.local/starry/.env` and change it to
`~/.local/starry/conf/.env`.

---

### Step 9 — Update `tests/conftest.py` ✓

The `tmp_config` fixture creates a temp dir and passes it to
`load_settings(config_path=...)`. Tests that only call
`load_settings()` do not need changes because `config_path`
bypasses normal path resolution entirely.

Tests that directly construct agent or session paths (e.g.
`tmp_path / "agents"`) need to add `/ "conf"` to match the new
layout. Check each test file that references `~/.local/starry/`
and update the path accordingly.

---

## Files Changed Summary

| File | Change |
|------|--------|
| `starry_lib/config/paths.py` | **NEW** — all path constants |
| `starry_lib/config/settings.py` | Use `paths.py`; add project TOML + `.env` layer |
| `starry_lib/agents/agent_store.py` | Use `paths.py`; project-first lookup in `get_agent` and `list_agents` |
| `starry_lib/sessions/store.py` | Use `paths.py` for default sessions dir |
| `starry_lib/providers.py` | Use `paths.py` in `get_default_paths()` |
| `starry_cli/main.py` | Use `paths.py`; project role merge in `_load_user_roles`; migration at startup |
| `install.sh` | Update `mkdir` and copy instructions to `conf/` |
| `.env.example` | Update copy instruction comment |
| `tests/conftest.py` | Update any test that constructs paths manually |

---

## Decisions Already Made

1. **`user.json` merge semantics**: full override — the project
   file replaces the global file entirely. No key-by-key merge.
   Rationale: preferences are a small flat file and partial
   merges produce surprising results.

2. **Creating `.starry/` in a project**: nothing creates it
   automatically. The user creates `pwd/.starry/` manually and
   drops files into it. A future `/project init` command (#8)
   will automate this.

3. **`save_agent()` always writes globally**: even when inside a
   project, saving an agent writes to
   `~/.local/starry/conf/agents/`. Project agents are
   hand-managed files. This can be revisited when `/project`
   commands are implemented.
