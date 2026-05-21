# plan_skills.md — Native Skills + MCP Support
# Date: 04/21/2026

Goal: replace the flat markdown-file "skill" pattern with
proper agentic tool conventions. Each skill becomes a
self-contained Python module with an OpenAI-format JSON
descriptor. MCP support is also hardened so it works
without the openai-agents SDK constraint.

---

## Overview of Changes

```
davyagent/skills/
    <name>/
        descriptor.json   ← OpenAI function schema
        skill.py          ← execute(**kwargs) -> dict
    network_scan/         ← example skill (done)
    sys_info/             ← example skill (done)

davyagent/tools/
    skill_loader.py       ← auto-discovers skills/ modules
    tool_loader.py        ← updated to include skill_loader
    mcp_client.py         ← new: direct MCP client (no SDK dep)
    registry.py           ← updated: use mcp_client as fallback
```

---

## Task 1 — Define the skill module protocol

Every skill under `davyagent/skills/<name>/` must expose:

- `descriptor.json` — valid OpenAI function-calling schema:
  ```json
  {
    "type": "function",
    "function": {
      "name": "<name>",
      "description": "...",
      "parameters": { ... }
    }
  }
  ```
- `skill.py` — must define:
  ```python
  async def execute(**kwargs) -> dict: ...
  ```
  Sync `execute()` is also acceptable; the loader wraps it.

### Acceptance criteria
- A skill with either async or sync `execute()` loads correctly.
- Missing `descriptor.json` raises `SkillLoadError` at startup,
  not at call time.
- Missing or non-callable `execute` raises `SkillLoadError`.

---

## Task 2 — Write `davyagent/tools/skill_loader.py`

New module that replaces the current `skill.py` tool.

### Responsibilities
1. Walk `davyagent/skills/*/` at import time.
2. For each subdirectory:
   a. Load and validate `descriptor.json`.
   b. Import `skill.py` and resolve `execute`.
   c. Build a tool object `{schema, execute}`.
3. Expose:
   ```python
   def load_skills() -> list[SkillTool]: ...
   ```
   where `SkillTool` is a simple dataclass:
   ```python
   @dataclass
   class SkillTool:
       SCHEMA: dict
       execute: Callable
   ```
4. Errors in individual skills are logged as warnings and
   skipped — they must not abort startup.

### Notes
- Use `importlib.util.spec_from_file_location` to load
  `skill.py` dynamically (avoids polluting `sys.modules`
  with arbitrary names).
- `_SKILLS_DIR` = `Path(__file__).parent.parent / "skills"`.
- Cache the result so `load_skills()` is called once.

---

## Task 3 — Update `davyagent/tools/tool_loader.py`

- Remove the import of the old `skill` module.
- Call `skill_loader.load_skills()` to get the dynamic list.
- Append all loaded skill tools to both `_PLAN_TOOLS` and
  `_EXECUTION_TOOLS` (skills are available in both modes
  unless their descriptor carries a `"mode"` extension key).
- `get_tool_schemas()` and `get_tool_executor()` require no
  signature changes — the returned lists grow automatically
  as skills are added to the directory.

### Migration
- Remove `davyagent/tools/implementations/skill.py` once
  `skill_loader.py` is in place and tests pass.
- The old flat `skills/*.md` directory at the project root
  can be kept for human-readable documentation but is no
  longer used by the agent at runtime.

---

## Task 4 — Create example skill: `network_scan`

Already scaffolded at `davyagent/skills/network_scan/`.

Files:
- `descriptor.json` — parameters: `target` (str, CIDR or host),
  `ports` (str, optional, default "22,80,443,8080"),
  `timeout` (int, optional, default 5).
- `skill.py` — uses `asyncio.create_subprocess_exec` to run
  `nmap -sV --open -p <ports> <target>` and parses stdout
  into a structured dict `{hosts: [{ip, hostname, ports}]}`.
  Falls back to a pure-Python ping sweep if nmap is absent.

### Acceptance criteria
- Calling with `target="127.0.0.1"` returns a dict with at
  least `{"hosts": [...]}`.
- If nmap is not installed, returns `{"error": "nmap not found",
  "hint": "install nmap or use ping_sweep mode"}` — no crash.

---

## Task 5 — Create example skill: `sys_info`

Already scaffolded at `davyagent/skills/sys_info/`.

Files:
- `descriptor.json` — parameters: `sections` (array of strings,
  optional, enum: `["cpu", "memory", "disk", "network", "os"]`,
  default all).
- `skill.py` — uses `psutil` (already a common dep) or falls
  back to `/proc` reads and `platform` stdlib. Returns a dict
  keyed by section name.

### Acceptance criteria
- Returns a non-empty dict for each requested section.
- Works without `psutil` (graceful degradation to `/proc`).

---

## Task 6 — Remove old `skill` tool from implementations

Once Tasks 2–5 are complete and tests pass:

1. Delete `davyagent/tools/implementations/skill.py`.
2. Remove `skill` from the import list in `tool_loader.py`
   (replaced by `skill_loader` output).
3. Update `tests/unit/test_tools.py` — remove tests that
   reference the old `skill` SCHEMA directly; add tests for
   `skill_loader.load_skills()`.
4. Verify the TUI `/skills` command (if it exists) now lists
   dynamically loaded skills from `skill_loader`.

---

## Task 7 — Harden MCP support (`mcp_client.py`)

Current problem: `registry.py` imports from `agents.mcp`
(openai-agents SDK) which requires Python 3.12+. The `mcp`
package (already in `pyproject.toml`) provides a direct client
that works on Python 3.11.

### New file: `davyagent/tools/mcp_client.py`

Implement a thin wrapper that:
1. Uses `mcp` stdlib client to connect to stdio/http servers.
2. Calls `list_tools()` on connect to discover available tools.
3. Exposes each remote tool as a `SkillTool`-compatible object
   (same `SCHEMA` + `execute` interface as native skills).
4. `execute(**kwargs)` sends a `call_tool` request and returns
   the result dict.

```python
async def connect_mcp_server(cfg: MCPServerConfig) -> list[SkillTool]:
    """Connect to one MCP server; return its tools as SkillTools."""
    ...

async def build_mcp_tools(settings: AppSettings) -> list[SkillTool]:
    """Build tools from all configured MCP servers."""
    ...
```

### Update `registry.py`

- Keep the existing `build_mcp_servers()` for the openai-agents
  SDK path (Python 3.12+).
- Add a second entry point `build_mcp_tools(settings)` that
  calls `mcp_client.build_mcp_tools()` and works on 3.11.
- `tool_loader.py` calls `build_mcp_tools()` and merges the
  resulting `SkillTool` list into the active tool set.

### Acceptance criteria
- On Python 3.11, `build_mcp_tools()` successfully connects to
  a stdio MCP server (e.g., `mcp-server-fetch`) and its tools
  appear in `get_tool_schemas("execution")`.
- On Python 3.12+, both paths work; the SDK path is preferred.
- A misconfigured MCP server logs a warning and is skipped;
  other tools are unaffected.

---

## Task 8 — Update `AgentPool` and `Session` to inject MCP tools

Currently MCP servers are passed to the openai-agents SDK's
runner. With the new `mcp_client.py`, tools are resolved to
plain `SkillTool` objects.

Changes needed in `session.py`:
- Accept an optional `extra_tools: list[SkillTool]` parameter.
- Merge them into the tool schemas / executor dicts returned by
  `get_tool_schemas()` / `get_tool_executor()`.

Changes needed in `pool.py` (`AgentPool.__aenter__`):
- Call `await build_mcp_tools(settings)` once at pool startup.
- Store the result and pass it to every `Session` via `spawn()`.

---

## Task 9 — Tests

### Unit tests (`tests/unit/`)
- `test_skill_loader.py`:
  - Valid skill directory loads correctly.
  - Missing `descriptor.json` raises `SkillLoadError`.
  - Missing `execute` raises `SkillLoadError`.
  - Broken skill is skipped; others still load.
- `test_mcp_client.py`:
  - `connect_mcp_server()` with a mock stdio server returns
    correctly typed `SkillTool` objects.
  - Failed connection returns empty list + logged warning.

### Integration tests (`tests/integration/`)
- `test_skills_integration.py`:
  - `network_scan` skill returns expected dict shape for
    `target="127.0.0.1"`.
  - `sys_info` skill returns all sections when called with
    no `sections` argument.

---

## Task 10 — Documentation

- Update `CLAUDE.md` to document the new skill directory
  convention and how to add a skill.
- Add a `davyagent/skills/README.md` explaining the
  `descriptor.json` + `skill.py` contract.
- Update `config/default.toml` comments to reflect that
  MCP server tools now appear in the tool list automatically.

---

## Dependency order

```
Task 1  (protocol)
    └─ Task 2  (skill_loader)
           ├─ Task 3  (tool_loader update)
           ├─ Task 4  (network_scan example)
           ├─ Task 5  (sys_info example)
           └─ Task 6  (remove old skill.py)
Task 7  (mcp_client)
    └─ Task 8  (AgentPool/Session injection)
Tasks 4,5,7,8 → Task 9  (tests)
Task 9         → Task 10 (docs)
```
