# DavyAgent — Session 02 Plan

## What this document is

The work plan for Session 02, agreed on 2026-04-04.
It captures every feature to build, every file to touch,
and the exact execution order. Read this before writing any code.

---

## Session 01 recap — current state

- 40/40 tests passing (`pytest -m 'not live'`)
- Install path resolution fixed (launcher passes `--config`)
- `/help` slash command added to REPL
- `docs/user_manual.md` updated with `/help` documentation
- No git repository yet — first commit is part of this session

---

## Features to build

### Feature 1 — Function-calling tools

Wire OpenAI function-calling into the orchestrator.
No Python 3.12 required. Uses the same protocol demonstrated
in `davyagent/example_tools.py`.

**Design summary:**

- Tools are plain Python functions + JSON schema dicts
  (OpenAI `type: "function"` format — the de-facto standard)
- Each role declares its allowed tools by name in `default.toml`
- The orchestrator runs a tool-call loop: send → check for
  `tool_calls` → execute locally → append result → send again
  → stream final answer
- Tool calls and results are rendered in the terminal as they happen
- Tools run in-process (no subprocess, no MCP, works on Python 3.11)

**Built-in tools (first set):**

| Name | Description | Opt-in required |
|------|-------------|-----------------|
| `read_file` | Read a local file, return text | No |
| `write_file` | Write text to a local file | No |
| `list_dir` | List directory contents | No |
| `fetch_url` | HTTP GET a URL, return text | No |
| `calculate` | Evaluate a safe math expression | No |
| `get_sysinfo` | Hostname, OS, cwd, Python version | No |
| `run_shell` | Run a shell command, return output | **Yes — explicit opt-in** |

`run_shell` is defined but not assigned to any role by default.
The user adds it explicitly to a role's `tools = [...]` list.

**Third-party tool compatibility:**
The OpenAI function-calling JSON schema is the de-facto standard.
Any tool that exposes a schema in this format plugs in directly.
LangChain tools can be adapted via `convert_to_openai_function()`.
MCP servers remain a parallel path (Python 3.12+, existing stub
in `tools/registry.py` is kept).

---

### Feature 2 — Plan / Exec modes

Two operating modes, Claude Code-style.

**Plan mode (`◈ PLAN`)**

- System prompt is augmented with a plan-mode addendum that
  instructs the LLM to output a numbered plan instead of acting
- `tools=` is NOT passed to the API call — the model cannot invoke
  tools even if it tries
- Output is a structured Markdown plan:
  ```
  Step 1: <action>
    Tool   : <tool name or "none">
    Args   : <arguments>
    Expects: <expected result>
  ...
  Plan summary: <one line>
  ```
- Toolbar shows `◈ PLAN` badge

**Exec mode (`▶ EXEC`)**

- Normal operation — tools active, tool-call loop runs
- Toolbar shows `▶ EXEC` badge

**Plan-mode system prompt addendum (appended at runtime):**

```
--- PLAN MODE ---
You are in PLAN mode. Do NOT call any tools or execute any actions.
Output a numbered plan of exactly what you would do:

  Step N: <action description>
  Tool   : <tool name> (or "none")
  Args   : <arguments you would pass>
  Expects: <what you expect to get back>

End with one line: "Plan summary: ..."
Do not perform the task. Only plan it.
```

**Mode transitions:**

- Default mode set in `[app] mode = "exec"` in `default.toml`
- `/plan` command — switches to plan mode
- `/exec` command — switches to exec mode; if the last user
  message produced a plan, re-runs it automatically in exec mode
- `/mode` command — prints current mode without switching
- `davyagent --mode plan` / `--mode exec` — startup override

**Re-run behaviour after `/exec`:**
The REPL stores the last user message text. When the user types
`/exec` after reviewing a plan, the orchestrator re-sends that
message immediately with tools enabled.

---

### Feature 3 — `/themes` REPL slash command

A new slash command that exposes theme listing and switching
from inside the REPL (no need to exit and use the CLI).

```
  › /themes              — list all themes, show active
  › /themes dracula      — switch to dracula immediately
  › /themes preview nord — preview nord without activating
```

Theme switch takes effect immediately (rebuilds the Rich console
on the next render). No restart required.

---

### Feature 4 — Mode indicator in the bottom toolbar

Current toolbar:
```
 provider | DavyAI   model | gpt-oss-120b-thinking   role | Coder
```

New toolbar:
```
 provider | DavyAI   model | gpt-oss-120b-thinking   role | Coder   ◈ PLAN
```
or:
```
 provider | DavyAI   model | gpt-oss-120b-thinking   role | Coder   ▶ EXEC
```

The mode badge is the rightmost item, always visible.

---

### Feature 5 — First git commit

Initialise the repository and make the first commit containing
the complete current codebase. Done last, after all features
are implemented and tests pass.

`.gitignore` must exclude:
- `certs/` (TLS certificates — sensitive)
- `.env` (API keys)
- `__pycache__/`, `*.pyc`, `*.egg-info/`
- `.venv/`
- `sandbox/` (any debug install)

---

## Files to create or modify

### New files

| File | Purpose |
|------|---------|
| `davyagent/tools/builtins.py` | Built-in tool functions + JSON schemas |
| `.gitignore` | Exclude secrets, caches, venv from version control |

### Modified files

| File | Changes |
|------|---------|
| `davyagent/tools/registry.py` | Rewrite: drop MCP stub, add `get_schemas(names)` and `call_tool(name, args)` |
| `davyagent/agents/base.py` | Add `tool_schemas: list` field; extend `build_messages()` to accept `plan_mode` flag and prior message history |
| `davyagent/agents/roles.py` | Pass resolved tool schemas from registry into `build_agent()` |
| `davyagent/agents/orchestrator.py` | Add `mode` state; full rewrite of `run()` — plan branch + exec tool-call loop |
| `davyagent/config/settings.py` | Add `mode: str = "exec"` to `AppSettings` |
| `davyagent/cli/repl.py` | Add `/plan`, `/exec`, `/mode`, `/themes` commands; update toolbar with mode badge; store last user message |
| `davyagent/cli/renderer.py` | Add `render_plan_header()` — styled separator before plan output |
| `davyagent/cli/app.py` | Add `--mode` startup option |
| `config/default.toml` | Add `mode = "exec"` under `[app]`; add `tools = [...]` to each role |
| `docs/user_manual.md` | Document tools, plan/exec modes, `/themes`, `/plan`, `/exec`, `/mode` |
| `README.md` | Update feature table and slash command reference |
| `tests/unit/test_tools.py` | Unit tests for registry: `get_schemas`, `call_tool`, error cases |
| `tests/integration/test_orchestrator_tools.py` | Integration tests for tool-call loop and plan mode |

---

## Execution order

Work in this exact order. Run `pytest -m 'not live'` after each
step before moving to the next.

### Step 1 — `davyagent/tools/builtins.py`
Define `TOOLS` (list of JSON schema dicts) and `FUNCTIONS`
(dict of name → callable) for all seven built-in tools.
`run_shell` is defined but documented as opt-in only.

### Step 2 — `davyagent/tools/registry.py`
Rewrite with two public functions:
- `get_schemas(names: list[str]) -> list[dict]`
  Returns the JSON schemas for the requested tool names.
  Raises `KeyError` for unknown names.
- `call_tool(name: str, arguments: dict) -> str`
  Calls the function and returns the result as a JSON string.
  Never raises — wraps errors in `{"error": "..."}`.

Keep the existing MCP stub as a comment block for future use.

### Step 3 — `davyagent/agents/base.py`
- Add `tool_schemas: list = field(default_factory=list)`
- Change `build_messages()` signature:
  ```python
  def build_messages(
      self,
      user_input: str,
      plan_mode: bool = False,
      history: list[dict] | None = None,
  ) -> list[dict]
  ```
  When `plan_mode=True`, appends the plan-mode addendum to the
  system prompt.
  When `history` is provided, inserts it between system and user.

### Step 4 — `davyagent/agents/roles.py`
Import registry. In `build_agent()`, resolve `role_cfg.tools`
(list of names) to actual schemas via `registry.get_schemas()`.
Pass them as `extra_tools` to `BaseAgent`.

### Step 5 — `davyagent/config/settings.py`
Add `mode: str = "exec"` to `AppSettings`.
Validate: must be `"plan"` or `"exec"`.

### Step 6 — `davyagent/agents/orchestrator.py`
- Add `self.mode: str` (from settings or constructor arg)
- Add `self._last_user_message: str = ""`
- Rewrite `run()`:
  - Plan branch: calls `build_messages(plan_mode=True)`, sends
    without `tools=`, streams result
  - Exec branch: tool-call loop (see design above)
  - Yields text tokens OR `ToolCallEvent` / `ToolResultEvent`
    named tuples so the REPL can dispatch to the right renderer
- Add `switch_mode(mode: str)` method

### Step 7 — `davyagent/cli/renderer.py`
Add `render_plan_header(console)` — prints a styled rule with
the text `"  ◈  plan  "` using the `separator` semantic style.

### Step 8 — `davyagent/cli/repl.py`
- Add `/plan`, `/exec`, `/mode`, `/themes` to `_SLASH_COMMANDS`
- Store last user message in a local variable before sending
- Update `_toolbar_factory()` to include the mode badge
- Add handlers for the four new commands:
  - `/plan` — `orc.switch_mode("plan")`
  - `/exec` — `orc.switch_mode("exec")`; if `_last_msg` is set,
    immediately re-run it
  - `/mode` — print current mode
  - `/themes [name|preview name]` — list, switch, or preview
- Update `_repl_loop()` to handle `ToolCallEvent` and
  `ToolResultEvent` yielded by `orc.run()`
- Update `_render_help()` to include the new commands

### Step 9 — `davyagent/cli/app.py`
Add `--mode` option (choices: `plan`, `exec`).
Pass it to `Orchestrator` constructor.

### Step 10 — `config/default.toml`
```toml
[app]
mode = "exec"

[agents.assistant]
tools = []

[agents.coder]
tools = ["read_file", "list_dir", "write_file", "calculate"]

[agents.researcher]
tools = ["fetch_url", "calculate", "get_sysinfo"]
```

### Step 11 — Tests
- `tests/unit/test_tools.py` — registry unit tests
- `tests/integration/test_orchestrator_tools.py` — mock API,
  test tool-call loop and plan mode branching

### Step 12 — Docs
- `docs/user_manual.md` — new sections for tools, plan/exec,
  `/themes`, `/plan`, `/exec`, `/mode`
- `README.md` — update feature table and slash command table

### Step 13 — Git
```bash
cd /home/armando/davy_agent
git init
git add .
git commit -m "Initial commit: DavyAgent v0.1 with tools and plan/exec modes"
```

---

## `.gitignore` contents

```
# Secrets and certs
.env
certs/*.crt
certs/*.pem
certs/*.key

# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/

# Virtual environments
.venv/
venv/

# Install artifacts
sandbox/

# Editor
.idea/
.vscode/
*.swp
```

---

## Test targets after all steps

```
pytest -m 'not live'   →   target: all pass, no failures
```

New test files bring the total to approximately 55+ tests.

---

## How to resume from this document

1. Open `/home/armando/davy_agent/` as working directory
2. Read `Session01.md` for prior context
3. Read this file (`Session02.md`) to orient
4. Run `.venv/bin/pytest -m 'not live'` — confirm 40/40 green
5. Execute steps 1–13 in order
6. After each step, run pytest before proceeding

---

*Last updated: 2026-04-04 — agreed at end of Session 01 / start of Session 02*
