# AGENTIC FUNCTIONALITY — IMPLEMENTATION PLAN
# Covers plan.md items 18–23
# All design decisions resolved. Ready to implement.

---

## What Already Exists

- `AgentPool` (`agents/pool.py`) — N concurrent `Session` objects.
- `Session` (`agents/session.py`) — streaming chat + tool loop,
  provider/model/role hot-swap, event streaming.
- `BaseAgent` (`agents/base.py`) — runtime identity + permission dataclass.
- `roles.py` — `build_agent(role_cfg, provider_cfg)` factory from TOML.
- `task` tool — one-shot ephemeral subagent via `AgentPool.run_subtask()`.
  **Distinction from `call_agent`:** `task` creates a throwaway subagent
  from a role; `call_agent` targets a named, persistent, stateful agent.

---

## Conceptual Model

```
Role        — behavior template (system_prompt, tools, temperature)
              Lives in config/default.toml [agents.*]

AgentConfig — named persistent config bound to a role + provider + model.
              Persistence format only. Stored as JSON.
              Converted to BaseAgent at spawn time.
              Lives in ~/.davyagent/agents/<name>.json

Active Agent — an AgentConfig that has a live Session in the AgentPool.
               Spawned by the user (/agent menu) or by the LLM
               (call_agent tool). Has two dedicated TUI buffers.
```

---

## Resolved Design Decisions

| Decision | Resolution |
|----------|-----------|
| AgentConfig vs BaseAgent | AgentConfig = persistence only; converted to BaseAgent at spawn |
| Storage format | One JSON file per agent under `~/.davyagent/agents/` |
| Agent session state | Stateful across multiple `call_agent` calls; reset only on kill |
| call_agent response | Buffer full response → return to LLM; stream to log buffer in parallel |
| Concurrent call_agent calls | Per-agent async lock — serialize into a queue |
| Tool modes | `list_*` + `describe_agent` → both modes; `call_agent` + `stop_agent` → execution mode only |
| Tool dependency injection | `ctx` dict passed to every executor at call time (see Phase 3) |
| Input routing | `session_stack: list[str]`; `/close` pops top entry and kills that agent |
| Buffers per agent | Two buffers: **log** (read-only) and **chat** (interactive) |
| Shared session | Both buffers point to the same agent session; user + LLM share context |
| Log buffer creation | Created on first traffic, not at spawn |
| User + LLM concurrent chat | Same session, serialized via per-agent lock |
| Slash commands in agent buffer | Apply to the agent session, not the main session |
| Orphaned agents on session restore | call_agent auto-respawns if agent is missing; informs LLM |
| inject_system_message() | New method on Session; implement in Phase 2 |
| describe_agent tool | New tool; complements list_available_agents with full config detail |

---

## Phase 1 — Agent Persistence Layer

**New files:** `davyagent/agents/agent_config.py`,
               `davyagent/agents/agent_store.py`

### AgentConfig dataclass (`agent_config.py`)

```
name                str         unique slug, e.g. "devbot"
label               str         display name
role                str         role name from config [agents.*]
provider            str         provider name from config [providers.*]
model               str         model id; "" = provider default
system_prompt_addon str         appended to role's system prompt at spawn
temperature         float       overrides role default; 0.0 = use role default
allowed_tools       list[str]   merged with role's list at spawn (union)
denied_tools        list[str]   merged with role's list at spawn (deny wins)
allowed_skills      list[str]
denied_skills       list[str]
description         str         one-liner shown in list_available_agents
```

AgentConfig is a pure data object. No runtime logic here.

### AgentStore (`agent_store.py`)

Storage: `~/.davyagent/agents/` — one JSON file per agent.

```python
list_agents()  -> list[AgentConfig]
get_agent(name) -> AgentConfig | None
save_agent(cfg: AgentConfig)   # create or overwrite
delete_agent(name)             # remove file
agent_exists(name) -> bool
```

### roles.py edit

Update `build_agent()` to accept an `AgentConfig`:
- Append `system_prompt_addon` to the role's system prompt.
- Merge tool/skill lists: `role_list ∪ agent_list`; deny lists take
  precedence over allow lists.

---

## Phase 2 — Active Agent Registry + Session.inject_system_message()

**New file:** `davyagent/agents/active_registry.py`
**Edit:** `davyagent/agents/session.py`

### Session.inject_system_message(content: str)

Add this method to `Session`. It inserts a system-role message directly
into the conversation history without triggering a new LLM turn. Used by
Phase 6 to notify the main LLM when an agent is killed.

### ActiveRegistry (`active_registry.py`)

Singleton held on `AppState`. Maps agent name → session_id. Also holds
a per-agent async lock for serializing concurrent `call_agent` calls.

```python
spawn_agent(name, pool, settings, ctx) -> Session
    # Load AgentConfig → build_agent() → pool.spawn()
    # Register name → session.id
    # Register per-agent asyncio.Lock
    # Emit create_chat_buffer event (chat buffer; log buffer on first traffic)

kill_agent(name, pool)
    # pool.terminate(session_id)
    # Remove from registry and lock dict
    # Emit close_buffer events for both buffers
    # If name is on session_stack, pop it

kill_all(pool)
    # Calls kill_agent() for all entries

list_active() -> list[ActiveAgentInfo]
    # Returns: name, session_id, role, provider, model,
    #          spawned_at, turn_count, token_usage

get_session(name) -> Session | None
get_lock(name) -> asyncio.Lock | None
```

---

## Phase 3 — New LLM Tools (5 files)

**New files:** `davyagent/tools/implementations/`

### Dependency injection pattern

Every tool executor receives a `ctx` dict as a keyword argument:

```python
async def execute(params, ctx: dict = {}):
    registry = ctx.get("active_registry")
    pool     = ctx.get("pool")
    session  = ctx.get("main_session")
    settings = ctx.get("settings")
```

`tool_loader.py` builds `ctx` from `AppState` and passes it on every
executor call. Existing tools ignore `ctx` (default `{}`); no changes
needed to them.

---

### 3a. `list_available_agents.py` — both modes

- **Parameters:** none
- **execute(ctx):** calls `AgentStore.list_agents()`, returns JSON list
  with `name`, `label`, `role`, `provider`, `model`, `description`.

### 3b. `list_active_agents.py` — both modes

- **Parameters:** none
- **execute(ctx):** calls `ActiveRegistry.list_active()`, returns JSON
  list with `name`, `session_id`, `role`, `provider`, `model`,
  `turn_count`, `token_usage`.

### 3c. `describe_agent.py` — both modes

- **Parameters:** `name: str` (required)
- **execute(name, ctx):** calls `AgentStore.get_agent(name)`, returns
  full `AgentConfig` as JSON. Returns error string if not found.
- **Purpose:** LLM inspects full config of a specific agent before
  calling it.

### 3d. `call_agent.py` — execution mode only

- **Parameters:** `name: str` (required), `message: str` (required),
  `context: str` (optional — injected as system message before first turn)
- **execute(name, message, context, ctx):**
  1. If agent not in registry: `ActiveRegistry.spawn_agent(name, ...)`.
     If AgentConfig not found: return error string.
  2. If session was previously active but is now gone (restored session):
     re-spawn agent, then inject into main session:
     `"[System] Agent <name> was re-spawned (previous session expired)."`
  3. Acquire per-agent lock (serializes concurrent calls).
  4. If `context` provided and this is first call: inject as system msg.
  5. Send `message` via `session.chat_auto()`. Buffer full response.
  6. Stream response tokens to log buffer in parallel (fire-and-forget;
     log buffer is created now if it does not yet exist).
  7. Release lock. Return full response string to LLM.

### 3e. `stop_agent.py` — execution mode only

- **Parameters:** `name: str` (required), `reason: str` (optional)
- **execute(name, reason, ctx):**
  1. `ActiveRegistry.kill_agent(name, pool)`.
  2. `main_session.inject_system_message(
       f'[System] Agent "{name}" has been terminated and is no longer
       available.')`.
  3. Return confirmation string.

### tool_loader.py edits

- Register all 5 tools.
- Add `ctx` dict construction and injection into every executor call.
- `call_agent` and `stop_agent` go in `_STATIC_EXEC` (execution mode).
- `list_available_agents`, `list_active_agents`, `describe_agent` go in
  `_STATIC_PLAN` (both modes).

---

## Phase 4 — `/agent` TUI Command

**Edit:** `davy_cli.py` (`accept_handler`)

Uses existing `cli/dialogs.py` floating dialogs.

```
/agent
  A. Create agent
  B. List agents
  C. Edit agent
  D. Remove agent
  ─────────────────
  E. Chat with agent        (spawns session; /close ends it)
  F. List active agents
  G. Chat with active agent
  H. Kill active agent
```

### Option A — Create agent

Dialog flow (sequential, single-line inputs unless noted):
1. Agent name (slug; validate unique via `AgentStore.agent_exists()`).
2. Select role (options menu from config).
3. Select provider (options menu from config).
4. Model (blank = provider default).
5. System prompt addon (multiline; hint shown).
6. Temperature (blank = role default).
7. Description (one liner).
8. Confirm → `AgentStore.save_agent()`.

### Option B — List agents

Read-only dialog: `name | role | provider | model | description`

### Option C — Edit agent

1. Select agent (options menu).
2. Same flow as A, fields pre-filled.
3. `AgentStore.save_agent()` overwrites.

### Option D — Remove agent

1. Select agent.
2. If active: warn user. Confirm.
3. Kill agent (if active), then `AgentStore.delete_agent()`.

### Option E — Chat with agent

1. Select agent from stored list.
2. `ActiveRegistry.spawn_agent()`.
3. Push agent onto `session_stack`. TUI switches to chat buffer.
4. User input routes to agent session while buffer is active.
5. `/close` → pop stack → kill agent → close both buffers → return to
   previous buffer.

### Option F — List active agents

Read-only dialog: `name | session_id | role | provider | turns | tokens`

### Option G — Chat with active agent

1. Select from active agents.
2. Push agent onto `session_stack`. TUI switches to its chat buffer.
3. `/close` to exit (does NOT kill the agent — it stays active).

### Option H — Kill active agent

1. Select active agent.
2. Confirm.
3. `ActiveRegistry.kill_agent()` → both buffers closed.
4. `main_session.inject_system_message(...)` (Phase 6).

---

## Phase 5 — Dual Buffer Model

Each active agent has exactly two buffers:

| Buffer | Name | Who writes | User input |
|--------|------|-----------|-----------|
| Log | `agent:<name>:log` | `call_agent` tool (main LLM ↔ agent traffic) | read-only |
| Chat | `agent:<name>:chat` | User direct interaction via TUI | interactive |

Both buffers display output from the **same agent session**. The agent
maintains one conversation history; both buffers are views into it.

**Lifecycle:**
- Chat buffer created at `spawn_agent()`.
- Log buffer created on first `call_agent` traffic (lazy).
- Both closed and deregistered on `kill_agent()`.

**Log buffer content:**
`call_agent` writes two entries per call:
1. `[LLM→agent] <message text>`
2. `[agent→LLM] <response text>`

**Session stack (input routing):**

```python
session_stack: list[str]  # TUI state field; initialized to ["main"]

current_input_target()  -> session_stack[-1]
push_agent(name)        -> session_stack.append(f"agent:{name}")
pop_agent()             -> session_stack.pop() if len > 1
```

- When `session_stack[-1]` is `"agent:<name>"`, all prompt input routes
  to that agent's session.
- Slash commands (e.g. `/model`, `/provider`) apply to the currently
  active session (agent session when an agent buffer is active).
- `/close` calls `pop_agent()`. If the popped entry is from Option E
  (opened via "Chat with agent"), the agent session is killed. If from
  Option G (opened via "Chat with active agent"), the agent stays alive.
  Track this by storing `{"name": ..., "owned": bool}` in the stack
  instead of a plain string.

---

## Phase 6 — Notify Main LLM on Agent Kill

Triggered by: `stop_agent` tool, `/agent → H`, `/agent → D` (if active).

```python
main_session.inject_system_message(
    f'[System] Agent "{name}" has been terminated '
    f'and is no longer available.'
)
```

`inject_system_message(content)` appends `{"role": "system",
"content": content}` to the session's message history without triggering
a new LLM turn.

---

## File Change Summary

| File | Change | Notes |
|------|--------|-------|
| `davyagent/agents/agent_config.py` | New | AgentConfig dataclass |
| `davyagent/agents/agent_store.py` | New | CRUD for `~/.davyagent/agents/` |
| `davyagent/agents/active_registry.py` | New | name→session + locks + buffer events |
| `davyagent/agents/session.py` | Edit | Add `inject_system_message()` |
| `davyagent/agents/roles.py` | Edit | Accept AgentConfig; merge addon prompt + tool lists |
| `davyagent/tools/implementations/list_available_agents.py` | New | both modes |
| `davyagent/tools/implementations/list_active_agents.py` | New | both modes |
| `davyagent/tools/implementations/describe_agent.py` | New | both modes |
| `davyagent/tools/implementations/call_agent.py` | New | execution mode only |
| `davyagent/tools/implementations/stop_agent.py` | New | execution mode only |
| `davyagent/tools/tool_loader.py` | Edit | Register 5 tools; add ctx injection |
| `davy_cli.py` | Edit | /agent dialogs + session_stack + dual buffer routing |

---

## Implementation Order

1. `agent_config.py` — standalone, no deps.
2. `agent_store.py` — depends on agent_config.
3. `session.py` edit — add `inject_system_message()`; no other deps.
4. `roles.py` edit — accept AgentConfig, merge prompts + tool lists.
5. `active_registry.py` — depends on store, pool, session.
6. 5 new tool files — each independent once registry exists.
7. `tool_loader.py` edit — register tools + ctx injection.
8. `davy_cli.py` edit — /agent dialogs + session_stack + buffer routing
   (Phases 4 + 5 together).

---

## Non-Goals

- Agents talking to each other without LLM direction — tools enable it
  but scheduling logic is out of scope.
- Persistent agent conversation history across TUI sessions — agent
  sessions are ephemeral; main session persists as before.
- Agent-to-agent direct communication — all routing goes through
  AgentPool and tool infrastructure.
