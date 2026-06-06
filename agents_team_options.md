# Multi-Agent Conversation Options

Options for enabling conversations between two or more agents and the user.

---

## Option A — Roundtable (selected for implementation)

A `/roundtable` TUI command that opens a shared chat room where the user
and N named agents all see the same transcript.

### How it works

1. User runs `/roundtable agent-a agent-b` — spawns agents if not active.
2. A `Roundtable` class (`starry_lib/agents/roundtable.py`) owns a
   **shared transcript**: a list of `{role, name, text}` dicts.
3. User posts a message → appended to transcript and broadcast to all
   agents via `pool.broadcast()`.
4. Each agent's response is shown in its own TUI buffer AND appended to
   the transcript with their name as attribution.
5. On each turn the transcript (formatted as `[agentA]: ...`) is
   prepended to the outgoing prompt so every agent sees what everyone
   said.
6. User can target one agent with `@name message`; unaddressed agents
   see the exchange but do not respond.

### Existing infrastructure reused

- `pool.broadcast()` — fan-out to multiple sessions
- `_session_stack` — input routing in the TUI
- Per-agent log/chat buffers — display

### New pieces needed

| Piece | Location | Purpose |
|-------|----------|---------|
| `Roundtable` class | `starry_lib/agents/roundtable.py` | Shared transcript + post/address |
| `/roundtable` command | `starry_cli/main.py` `accept_handler()` | TUI entry point |
| `_ALL_COMMANDS` entry | `starry_cli/main.py` | 4-char prefix auto-expansion |
| `/help` entry | `starry_cli/main.py` | Help text |
| `_BUILTIN_NAMES` entry | `starry_lib/commands/store.py` | Prevent shadowing |
| Room-view TUI buffer | `starry_cli/main.py` | Merged transcript display |

---

## Option B — Facilitator (orchestrator-driven)

A designated facilitator agent mediates everything. The user talks only
to the facilitator; it decides which specialist to call and synthesizes
the result for the user.

### How it works

1. User addresses a facilitator agent (a named agent with a coordination
   role).
2. The facilitator uses `call_agent` to route subtasks to specialist
   agents and collects their responses.
3. The facilitator synthesizes a unified reply back to the user.
4. A "transparent mode" flag streams the agent-to-agent traffic into the
   main buffer so the user can observe the reasoning chain.

### Existing infrastructure reused

- `pool.route()` + `pool.delegate_auto()` — routing logic
- `call_agent` tool — LLM-driven delegation
- `ActiveRegistry` — agent lifecycle

### New pieces needed

- Transparent mode flag on `call_agent` that mirrors agent↔agent traffic
  into the main session buffer.
- A facilitator role definition in `config/default.toml`.

---

## Option C — Structured Debate

Two agents are assigned opposing stances and take turns responding to
each other for N rounds, then produce a synthesis. The user is
observer/judge and can interject at any time.

### How it works

1. User runs `/debate agent-a agent-b "topic" --rounds 3`.
2. A `pool.debate()` method alternates turns: A responds to B's last
   message, B responds to A's, repeat N times.
3. After the rounds, an optional synthesizer agent (or the user) draws
   conclusions.
4. The user can inject a message at any point to steer the debate.

### Existing infrastructure reused

- `run_subtask_with_review()` — critic/revision loop pattern
- `call_agent` critic loop — already implements a two-agent review cycle

### New pieces needed

- `pool.debate(session_a, session_b, topic, rounds)` method in
  `starry_lib/agents/pool.py`.
- `/debate` TUI command.

---

## Option D — Collaborative Chain

Agents work sequentially: each agent's output becomes the next agent's
input, with optional user checkpoints between stages. The final output is
the end of the chain.

### How it works

1. User defines a pipeline: `/chain agent-a agent-b agent-c "task"`.
2. `pool.pipeline()` runs each agent in order, passing the prior output
   as the next agent's input.
3. Optional `--checkpoint` flag pauses after each stage so the user can
   review, edit, or approve before proceeding.
4. Each stage output is shown in the agent's own buffer and in a
   summary "chain view" buffer.

### Existing infrastructure reused

- `pool.pipeline()` — already implements sequential chaining by session
  ID.
- Per-agent log buffers — stage output display.

### New pieces needed

- Checkpoint pause mechanism in `pool.pipeline()` (an optional
  `asyncio.Event` barrier per stage).
- `/chain` TUI command.
- Chain-view TUI buffer showing all stage outputs in order.

---

## Comparison

| Option | User role | Agent coordination | Turn control | Complexity |
|--------|-----------|-------------------|--------------|------------|
| A Roundtable | Active participant | Shared transcript | User-driven | Medium |
| B Facilitator | Talks to one agent | Orchestrator routes | Orchestrator-driven | Low (mostly exists) |
| C Debate | Observer/judge | Turn-alternating | Fixed N rounds | Medium |
| D Collaborative chain | Approver (optional) | Sequential pipeline | Stage-gated | Low-Medium |
