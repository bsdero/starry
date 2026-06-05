# Commands Implementation Plan

Commands to implement (item 8 of next_fixes.md):
`/new`, `/project`, `/branch`, `/add-dir`, `/focus`, `/goal`,
`/recap`, `/review`, `/doctor`, `/mcp`, `/save`, `/load`

`/vim` is deferred — do not implement it now.

Goal: match the Claude Code user experience as closely as possible.

---

## Important facts before starting

- All slash command handlers live inside `accept_handler()` in
  `starry_cli/main.py`. Every handler follows this exact pattern:
  ```python
  if text.lower() == "/cmdname":
      append_text(build_user_frame(text, _exec_mode))
      app.invalidate()
      # ... do the work
      return
  ```

- `_da_session` (type `da.Session`) and `_da_settings` (type
  `da.AppSettings`) are module-level globals declared at line 961.
  They are always available inside `accept_handler()`.

- `append_text(s)` writes a string into the main scroll buffer.
  Use `build_inline_notif(message, icon)` for info/status lines and
  `build_error_frame(message)` for errors. Both return strings.

- `app.invalidate()` must be called after every `append_text()` to
  force a screen redraw.

- Async work (network calls, LLM calls) must be wrapped in
  `asyncio.ensure_future(some_coroutine())` so the TUI stays
  responsive. Do not use `await` directly inside `accept_handler()`.

- The prefix auto-expansion list `_ALL_COMMANDS` is at line 9350.
  Every new built-in command name must be added to this list.

- The `/help` text is built in the function starting at line 8302.
  Every new built-in command must be added there too.

- The `_BUILTIN_NAMES` frozenset in `starry_lib/commands/store.py`
  lists names that user custom commands cannot shadow. Every new
  built-in command name must be added there.

- Global config dir: `~/.local/starry/conf/`
  (returned by `global_conf_dir()` from `starry_lib/config/paths.py`)
- Project config dir: `<cwd>/.starry/`
  (returned by `project_conf_dir()`, returns `None` if not present)

---

## Phase 1 — `$ARGUMENTS` substitution in custom commands

**File:** `starry_cli/main.py`

**Why:** argument-driven commands (`/focus`, `/goal`, `/branch`) are
implemented as custom commands. Claude Code custom commands support a
`$ARGUMENTS` placeholder: whatever the user types after the command
name is substituted into the stored prompt before sending to the LLM.

**Location:** the custom command dispatch block, currently at line
~10292. Current code:

```python
# ── Custom commands ───────────────
if text.startswith("/"):
    from starry_lib.commands.store import (
        get_command,
    )
    _cmd_name = text[1:].split()[0]
    _cmd_prompt = get_command(_cmd_name)
    if _cmd_prompt is not None:
        append_text(
            build_user_frame(
                text, _exec_mode
            )
        )
        app.invalidate()
        _ai_task = (
            asyncio.ensure_future(
                handle_ai_response(
                    app,
                    _cmd_prompt,
                    _da_session,
                )
            )
        )
        return
```

**Replace with:**

```python
# ── Custom commands ───────────────
if text.startswith("/"):
    from starry_lib.commands.store import (
        get_command,
    )
    _cmd_name = text[1:].split()[0]
    _cmd_prompt = get_command(_cmd_name)
    if _cmd_prompt is not None:
        _cmd_args = text[
            len(_cmd_name) + 2:
        ].strip()
        if (
            "$ARGUMENTS" in _cmd_prompt
            and not _cmd_args
        ):
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            append_text(
                build_error_frame(
                    f"/{_cmd_name} requires"
                    " an argument."
                    " Usage: /"
                    f"{_cmd_name} <text>"
                )
            )
            app.invalidate()
            return
        _cmd_prompt = _cmd_prompt.replace(
            "$ARGUMENTS", _cmd_args
        )
        append_text(
            build_user_frame(
                text, _exec_mode
            )
        )
        app.invalidate()
        _ai_task = (
            asyncio.ensure_future(
                handle_ai_response(
                    app,
                    _cmd_prompt,
                    _da_session,
                )
            )
        )
        return
```

**Explanation of `len(_cmd_name) + 2`:** the command text is e.g.
`"/focus some topic"`. The name `"focus"` is 5 chars. The slash takes
1 char, and the space between name and args takes 1 char, so args
start at index `1 + 5 + 1 = 7 = len("focus") + 2`.

---

## Phase 2 — Built-in custom commands

These commands are implemented as pre-defined entries seeded into
`~/.local/starry/conf/commands.json` at startup. The user may edit
that file to change the prompts. The project file `.starry/commands.json`
overrides individual entries by name.

### 2a — Seed function in `starry_lib/commands/store.py`

Add a function `seed_builtin_commands()` that writes the built-in
commands to `~/.local/starry/conf/commands.json` **only if the file
does not already exist**. This preserves any edits the user has made.

```python
_BUILTIN_COMMANDS: dict[str, str] = {
    "recap": (
        "Provide a concise recap of what"
        " has been discussed and"
        " accomplished in this"
        " conversation so far. List"
        " decisions made, files changed,"
        " and any open questions."
    ),
    "review": (
        "Review the recent code changes"
        " in this project. Run git diff"
        " to see what changed, then give"
        " feedback on correctness, style,"
        " and potential issues. Flag"
        " anything that looks risky."
    ),
    "focus": (
        "For the rest of this session,"
        " focus your attention on:"
        " $ARGUMENTS. Keep this context"
        " in mind when reading files or"
        " answering questions."
    ),
    "goal": (
        "My goal for this session is:"
        " $ARGUMENTS. Acknowledge this"
        " goal and keep it in mind"
        " throughout our conversation."
    ),
    "project": (
        "Describe the current project."
        " Read CLAUDE.md or README.md if"
        " present. Summarise the project"
        " structure, entry points, and"
        " key modules."
    ),
    "branch": (
        "Help me work with git branch"
        " '$ARGUMENTS'. If the branch"
        " does not exist, create it."
        " If it does, switch to it."
        " Then confirm the current"
        " branch and status."
    ),
}


def seed_builtin_commands() -> None:
    """Write built-in commands to global
    commands.json if the file is absent.

    Does nothing if the file already
    exists (preserves user edits).
    """
    if _GLOBAL_FILE.exists():
        return
    _write_global(dict(_BUILTIN_COMMANDS))
```

Note: `/project` has no `$ARGUMENTS` in its template intentionally.
It works without arguments. If the user wants to add context, they can
type it as regular chat after running `/project`.

### 2b — Call `seed_builtin_commands()` at startup

**File:** `starry_cli/main.py`

Find where the TUI starts (inside `async def main()`, before the
application runs). Import and call:

```python
from starry_lib.commands.store import (
    seed_builtin_commands,
)
seed_builtin_commands()
```

### 2c — Update `_BUILTIN_NAMES` in `store.py`

Add the six new command names to `_BUILTIN_NAMES`:

```python
_BUILTIN_NAMES: frozenset[str] = frozenset({
    # existing entries ...
    "recap", "review", "focus",
    "goal", "project", "branch",
    # new built-in TUI commands from Phase 3:
    "new", "add-dir", "save", "load",
    # new built-in TUI commands from Phase 4:
    "doctor", "mcp",
})
```

---

## Phase 3 — New built-in TUI commands

### `/new`

**What it does:** start a completely fresh conversation. Clears history,
resets token counters, generates a new session ID, and resets the
scroll buffer. Unlike `/clear`, it does not ask for confirmation —
Claude Code's `/new` is immediate.

**Step 1 — Add `new_session()` to `starry_lib/agents/session.py`**

The session ID (`self._id`) is set at construction. To get a new ID
without destroying the session object (which owns the LLM client and
other expensive state), add a method that resets the conversation-level
state and issues a new ID.

Add this method to the `Session` class, alongside the existing
`clear_history()` and `reset_tokens()` methods:

```python
def new_session(self) -> str:
    """Reset conversation state and issue a
    new session ID.

    Clears history, zeroes token counters,
    resets turn count, and returns the new ID.
    The LLM client and agent config are kept.
    """
    import uuid
    self.clear_history()
    self.reset_tokens()
    self._turn = 0
    self._tool_cache = {}
    self._display_log = []
    self._id = (
        "session-"
        + uuid.uuid4().hex[:8]
    )
    return self._id
```

**Step 2 — Add `/new` handler in `starry_cli/main.py`**

Insert after the `/clear` handler (around line 9454):

```python
# ── /new ──────────────────────────
if text.lower() == "/new":
    append_text(
        build_user_frame(text, _exec_mode)
    )
    app.invalidate()
    global SESSION_NAME
    global _auto_approved
    global _autosum_triggered
    if _da_session is not None:
        new_id = _da_session.new_session()
        SESSION_NAME = new_id
    _auto_approved.clear()
    _autosum_triggered = False
    welcome = make_welcome()
    main_buffer.set_document(
        Document(
            text=welcome,
            cursor_position=len(welcome),
        ),
        bypass_readonly=True,
    )
    append_text(
        build_inline_notif(
            "New session started.", "✦"
        )
    )
    app.invalidate()
    return
```

**Step 3 — Add `"/new"` to `_ALL_COMMANDS`** (line ~9350) and to
`/help` text.

---

### `/save`

**What it does:** save the current session to disk immediately, without
exiting. The same `store_save()` call used on exit is reused here.

Add the handler in `main.py` after the `/sessions` handler:

```python
# ── /save ─────────────────────────
if text.lower() == "/save":
    append_text(
        build_user_frame(text, _exec_mode)
    )
    app.invalidate()
    if _da_session is None:
        append_text(
            build_error_frame(
                "No active session to save."
            )
        )
        app.invalidate()
        return
    try:
        from starry_lib.sessions.store\
            import save as store_save
        store_save(_da_session)
        append_text(
            build_inline_notif(
                f"Session saved:"
                f" {_da_session.id}",
                "💾",
            )
        )
    except Exception as exc:
        append_text(
            build_error_frame(
                f"Could not save session:"
                f" {exc}"
            )
        )
    app.invalidate()
    return
```

Add `"/save"` to `_ALL_COMMANDS` and to `/help` text.

---

### `/load`

**What it does:** open the saved sessions menu and let the user pick
one to restore. This is identical to `/sessions`. Implement it as a
simple alias: set `text = "/sessions"` and fall through to the
existing `/sessions` handler.

Insert this block **before** the `/sessions` handler:

```python
# ── /load (alias for /sessions) ───
if text.lower() == "/load":
    text = "/sessions"
```

Note: do not add `return` here. The code falls through to the
`/sessions` handler on the next line.

Add `"/load"` to `_ALL_COMMANDS` and to `/help` text.

---

### `/add-dir`

**What it does:** tell the LLM about an additional directory so it can
read files from it. Accepts a path as argument. Injects a system
message and then asks the LLM to list the directory.

**Why no `ctx` plumbing is needed:** Starry's tools (`read`, `glob`,
`grep`) already accept absolute paths. The LLM will use absolute paths
when calling tools. We only need to make the LLM aware of the directory.

**Implementation:**

This is a built-in command with an argument. It does NOT go through the
custom command system. It needs its own handler in `accept_handler()`.

Insert after the `/add-dir` label (add it near `/new`):

```python
# ── /add-dir ──────────────────────
if text.lower().startswith("/add-dir"):
    _add_dir_arg = text[9:].strip()
    append_text(
        build_user_frame(text, _exec_mode)
    )
    app.invalidate()
    if not _add_dir_arg:
        append_text(
            build_error_frame(
                "/add-dir requires a path."
                " Usage: /add-dir <path>"
            )
        )
        app.invalidate()
        return
    import os
    _dir_path = os.path.expanduser(
        _add_dir_arg
    )
    if not os.path.isdir(_dir_path):
        append_text(
            build_error_frame(
                f"Directory not found:"
                f" {_dir_path}"
            )
        )
        app.invalidate()
        return
    if _da_session is not None:
        _da_session.inject_system_message(
            f"The user has added directory"
            f" '{_dir_path}' to the"
            f" session context. You may"
            f" read files from it using"
            f" your tools."
        )
    _ai_task = asyncio.ensure_future(
        handle_ai_response(
            app,
            f"List the contents of"
            f" '{_dir_path}' and give a"
            f" brief summary of what is"
            f" in it.",
            _da_session,
        )
    )
    return
```

Note: `text[9:]` because `"/add-dir "` is 9 characters
(`/` + `add-dir` + ` `).

Add `"/add-dir"` to the prefix expansion list and to `/help`.

Because `/add-dir` takes a required argument and uses `startswith`
instead of `==`, it must be added to `_ALL_COMMANDS` carefully.
The prefix expansion block checks `" " not in text` before expanding,
so `/add-dir` with an argument will not be auto-expanded — that is
correct behaviour.

---

## Phase 4 — New commands: `/doctor` and `/mcp`

### `/doctor`

**What it does:** run a set of health checks and display the results
as a formatted report in the scroll buffer. Mirrors Claude Code's
`/doctor`.

**Checks (in order):**

1. Python version: pass if `>= 3.11`, warn if `< 3.12` (MCP needs
   3.12 for full support), fail if `< 3.11`.
2. Global config file: check `~/.local/starry/conf/config.toml` exists.
3. `.env` file: check `~/.local/starry/conf/.env` exists.
4. Active provider: read from `_da_settings.active_provider`; check
   the env var for its API key is set and non-empty.
5. Provider reachability: call `probe_provider(cfg)` for the active
   provider only (not all providers — this keeps it fast).
   `probe_provider` is in `starry_lib/providers.py`.
6. MCP servers: for each entry in `_da_settings.mcp_servers`, call
   `connect_mcp_server(cfg)` from
   `starry_lib/tools/mcp_client.py`. Report how many tools it
   returned, or "unreachable" on failure.
7. Tools and skills: report the count of built-in tools and loaded
   skills from `get_tool_schemas("execution")` and
   `skill_loader.load_all_skills()`.

**Output symbols:**
- `✓` — check passed
- `✗` — check failed (error)
- `⚠` — warning (works but with caveats)

**Implementation outline:**

Add the handler in `accept_handler()`:

```python
# ── /doctor ───────────────────────
if text.lower() == "/doctor":
    append_text(
        build_user_frame(text, _exec_mode)
    )
    append_text(
        build_inline_notif(
            "Running diagnostics…", "🩺"
        )
    )
    app.invalidate()
    asyncio.ensure_future(
        _run_doctor(app, _da_settings)
    )
    return
```

Add the coroutine as a module-level async function (not inside
`accept_handler`):

```python
async def _run_doctor(app, settings) -> None:
    """Run health checks and display results."""
    import sys
    from pathlib import Path
    from starry_lib.config.paths import (
        global_conf_dir,
    )
    from starry_lib.providers import (
        probe_provider,
    )
    from starry_lib.tools.mcp_client import (
        connect_mcp_server,
    )

    lines = ["## Starry Diagnostics\n"]

    # 1. Python version
    v = sys.version_info
    if v >= (3, 12):
        lines.append(
            f"✓ Python {v.major}.{v.minor}"
            " (full MCP support)"
        )
    elif v >= (3, 11):
        lines.append(
            f"⚠ Python {v.major}.{v.minor}"
            " (MCP needs 3.12 for"
            " full support)"
        )
    else:
        lines.append(
            f"✗ Python {v.major}.{v.minor}"
            " — StarryLib requires 3.11+"
        )

    # 2. Config file
    cfg_file = global_conf_dir() / "config.toml"
    if cfg_file.exists():
        lines.append("✓ config.toml found")
    else:
        lines.append("✗ config.toml not found"
                     f" ({cfg_file})")

    # 3. .env file
    env_file = global_conf_dir() / ".env"
    if env_file.exists():
        lines.append("✓ .env file found")
    else:
        lines.append(
            "⚠ .env file not found"
            f" ({env_file})"
        )

    # 4 & 5. Active provider
    if settings is None:
        lines.append("✗ Settings not loaded")
    else:
        pname = settings.active_provider
        if not pname:
            lines.append(
                "✗ No active provider set"
            )
        else:
            pcfg = settings.providers.get(
                pname
            )
            if pcfg is None:
                lines.append(
                    f"✗ Provider '{pname}'"
                    " not found in config"
                )
            else:
                # Check API key env var
                import os
                key_var = pcfg.api_key_env
                key_val = os.environ.get(
                    key_var, ""
                )
                if key_val:
                    lines.append(
                        f"✓ API key env var"
                        f" {key_var} is set"
                    )
                else:
                    lines.append(
                        f"✗ API key env var"
                        f" {key_var} is NOT set"
                    )
                # Probe reachability
                try:
                    models = await (
                        probe_provider(pcfg)
                    )
                    lines.append(
                        f"✓ Provider '{pname}'"
                        f" reachable"
                        f" ({len(models)}"
                        f" models)"
                    )
                except Exception as exc:
                    lines.append(
                        f"✗ Provider '{pname}'"
                        f" unreachable:"
                        f" {exc}"
                    )

        # 6. MCP servers
        if not settings.mcp_servers:
            lines.append(
                "⚠ No MCP servers configured"
            )
        else:
            for sname, scfg in (
                settings.mcp_servers.items()
            ):
                try:
                    tools = await (
                        connect_mcp_server(scfg)
                    )
                    lines.append(
                        f"✓ MCP '{sname}'"
                        f" ({len(tools)} tools)"
                    )
                except Exception as exc:
                    lines.append(
                        f"✗ MCP '{sname}'"
                        f" failed: {exc}"
                    )

        # 7. Tools and skills
        try:
            from starry_lib.tools.tool_loader\
                import get_tool_schemas
            from starry_lib.tools.skill_loader\
                import load_all_skills
            schemas = get_tool_schemas(
                "execution"
            )
            skills = load_all_skills()
            lines.append(
                f"✓ {len(schemas)} built-in"
                f" tools loaded,"
                f" {len(skills)} skills"
                f" discovered"
            )
        except Exception as exc:
            lines.append(
                f"⚠ Could not count tools:"
                f" {exc}"
            )

    report = "\n".join(lines)
    append_text(
        build_inline_notif(report, "🩺")
    )
    app.invalidate()
```

**Important:** check what `load_all_skills()` is actually called in
`skill_loader.py` before using it — the function name may differ.
Search for `def load` in `starry_lib/tools/skill_loader.py` and use
the actual function name.

Add `"/doctor"` to `_ALL_COMMANDS` and `/help`.

---

### `/mcp`

**What it does:** list all configured MCP servers with their connection
status and tool count. First version: list and info only.
Reconnect is deferred.

**Sub-commands (parsed from text after `/mcp`):**
- `/mcp` or `/mcp list` — show all servers as a table
- `/mcp info <name>` — list individual tools from one server

**Implementation:**

Add handler in `accept_handler()`:

```python
# ── /mcp ──────────────────────────
if text.lower().startswith("/mcp"):
    _mcp_arg = text[5:].strip()
    append_text(
        build_user_frame(text, _exec_mode)
    )
    app.invalidate()
    asyncio.ensure_future(
        _run_mcp_cmd(
            app, _da_settings, _mcp_arg
        )
    )
    return
```

Note: `text[5:]` because `"/mcp "` is 5 characters.
For `/mcp` with no args, `text[5:]` is an empty string — that is fine.

Add module-level coroutine:

```python
async def _run_mcp_cmd(
    app, settings, sub: str
) -> None:
    """Handle /mcp sub-commands."""
    from starry_lib.tools.mcp_client import (
        connect_mcp_server,
    )

    if settings is None:
        append_text(
            build_error_frame(
                "Settings not loaded."
            )
        )
        app.invalidate()
        return

    servers = settings.mcp_servers
    if not servers:
        append_text(
            build_inline_notif(
                "No MCP servers configured.",
                "🔌",
            )
        )
        app.invalidate()
        return

    parts = sub.split(None, 1)
    sub_cmd = parts[0].lower() if parts else ""
    sub_arg = parts[1] if len(parts) > 1 else ""

    # /mcp or /mcp list
    if sub_cmd in ("", "list"):
        lines = ["## MCP Servers\n"]
        for sname, scfg in servers.items():
            try:
                tools = await (
                    connect_mcp_server(scfg)
                )
                status = (
                    f"✓ {len(tools)} tools"
                )
            except Exception:
                status = "✗ unreachable"
            lines.append(
                f"- **{sname}**"
                f" [{scfg.transport}]"
                f" {status}"
            )
        append_text(
            build_inline_notif(
                "\n".join(lines), "🔌"
            )
        )
        app.invalidate()
        return

    # /mcp info <name>
    if sub_cmd == "info":
        if not sub_arg:
            append_text(
                build_error_frame(
                    "Usage: /mcp info <name>"
                )
            )
            app.invalidate()
            return
        scfg = servers.get(sub_arg)
        if scfg is None:
            append_text(
                build_error_frame(
                    f"MCP server '{sub_arg}'"
                    " not found."
                )
            )
            app.invalidate()
            return
        try:
            tools = await (
                connect_mcp_server(scfg)
            )
            lines = [
                f"## MCP '{sub_arg}'"
                f" tools\n"
            ]
            for t in tools:
                lines.append(
                    f"- {t.name}:"
                    f" {t.description}"
                )
            append_text(
                build_inline_notif(
                    "\n".join(lines), "🔌"
                )
            )
        except Exception as exc:
            append_text(
                build_error_frame(
                    f"Could not connect to"
                    f" '{sub_arg}': {exc}"
                )
            )
        app.invalidate()
        return

    # unknown sub-command
    append_text(
        build_error_frame(
            f"Unknown /mcp sub-command:"
            f" '{sub_cmd}'."
            " Use: /mcp, /mcp list,"
            " /mcp info <name>"
        )
    )
    app.invalidate()
```

**Important:** check the `SkillTool` fields in
`starry_lib/tools/skill_loader.py` before accessing `t.name` and
`t.description`. Use the actual field names.

Add `"/mcp"` to `_ALL_COMMANDS` and to `/help`.

---

## Phase 5 — Deferred

### `/vim`
Deferred. Do not implement now.

---

## Implementation order

Do the steps in this exact order. Each step depends on the previous.

| Step | What | File(s) |
|------|------|---------|
| 1 | `$ARGUMENTS` substitution + error guard | `main.py` |
| 2 | `seed_builtin_commands()` + `_BUILTIN_COMMANDS` dict | `commands/store.py` |
| 3 | Call `seed_builtin_commands()` at startup | `main.py` |
| 4 | Update `_BUILTIN_NAMES` in store | `commands/store.py` |
| 5 | Add `new_session()` to `Session` | `agents/session.py` |
| 6 | `/new` handler | `main.py` |
| 7 | `/save` handler | `main.py` |
| 8 | `/load` alias | `main.py` |
| 9 | `/add-dir` handler | `main.py` |
| 10 | `_run_doctor()` coroutine + `/doctor` handler | `main.py` |
| 11 | `_run_mcp_cmd()` coroutine + `/mcp` handler | `main.py` |
| 12 | Update `_ALL_COMMANDS` list | `main.py` |
| 13 | Update `/help` text | `main.py` |

---

## Open questions — verify before implementing

1. **`load_all_skills()` name:** check the actual exported function
   name in `starry_lib/tools/skill_loader.py` before using it in
   `_run_doctor()`.

2. **`SkillTool` fields:** check the actual attribute names on the
   `SkillTool` dataclass in `starry_lib/tools/skill_loader.py` before
   accessing `t.name` and `t.description` in `_run_mcp_cmd()`.

3. **`probe_provider` signature:** confirm that `probe_provider(cfg)`
   in `starry_lib/providers.py` is an `async` function and returns a
   list of model names. If it raises on unreachable provider, the
   try/except in `_run_doctor()` handles it correctly.

4. **`_auto_approved` type:** in the `/new` handler, `_auto_approved.clear()`
   is called. Confirm this variable is a `set` or `dict` (has a
   `.clear()` method). This pattern is copied directly from the
   existing `/clear` handler so it should be safe.

5. **`_turn` visibility:** `new_session()` sets `self._turn = 0`.
   Confirm that `_turn` exists as an instance attribute in `Session.__init__`
   (it is declared at line ~93 as `self._turn: int = 0`).
