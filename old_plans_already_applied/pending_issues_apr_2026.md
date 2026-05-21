# pending_issues.md — Missing Standard Agentic Capabilities
# Date: 04/21/2026

Missing functionalities common in production agentic frameworks
that DavyAgent does not yet implement. Ranked by how immediately
felt the gap is in day-to-day use.

Issues #1 (World-state context injection) and #2 (Context
window management) have been moved to plan_bugfixes_04212026.md
as BUG-002 and BUG-003 respectively.

Issues #2 (Token tracking), #3 (Retry/fallback), #4 (Structured
output), #6 (Tool caching), and #9 (Websearch) were implemented
on 04/22/2026 and moved to bug_fixes_applied_04222026.md.

---

## 5. Long-term memory

### Problem
Sessions are isolated. Knowledge from a past session is lost.
There is no mechanism for the agent to recall facts, decisions,
or summaries across separate runs.

### Expected behaviour
A pluggable memory backend that persists key facts between
sessions:
- **Short-term** (already exists): in-session `_history`.
- **Episodic** (missing): auto-summarise each session on end
  and write to a local JSON/SQLite store keyed by topic tags.
- **Retrieval** (missing): at session start, query the store
  with the first user message and inject the top-K relevant
  memories as a `role="system"` block.

### Where to implement
`davyagent/memory/` — new package:
- `store.py` — read/write to `~/.davyagent_memory.db`
  (SQLite, simple BM25 keyword search to start).
- `episodic.py` — triggered by `on_session_end` event;
  summarises the session and stores it.
- `retriever.py` — called at session start; injects relevant
  memories into `_internal_messages`.

---

## 7. Guardrails

### Problem
There are no hooks to inspect or modify content before it
reaches the LLM (input) or the user (output). Sensitive data
(API keys, personal information) in tool results can be
forwarded to the LLM verbatim. There is no policy enforcement
layer.

### Expected behaviour
A lightweight hook chain on `Session`:

```python
session.add_input_guard(fn)   # fn(text) -> text
session.add_output_guard(fn)  # fn(text) -> text
```

Guards run in registration order. A guard may raise
`GuardViolation` to abort the turn with an error frame
instead of sending to the LLM.

Built-in optional guards:
- `SecretScrubber` — regex-redact patterns matching
  common secret formats (API keys, tokens, passwords).
- `LengthLimiter` — truncate tool results over N chars
  before they enter the message list.

### Open question before coding
Should `SecretScrubber` be on by default or opt-in?
This decision affects session.py integration.

### Where to implement
`davyagent/guardrails/` — new package with `base.py`,
`secret_scrubber.py`, `length_limiter.py`.
`session.py` — call input guards before appending user
messages; call output guards before yielding `token` events.

---

## 8. Observability / tracing

### Problem
When a multi-agent pipeline misbehaves there is no structured
record of what happened: which tools were called, in what order,
with what arguments, how long each took, and how many tokens
each turn consumed. Debugging requires adding print statements.

### Expected behaviour
Each session maintains a structured trace:

```python
@dataclass
class TraceEntry:
    turn: int
    type: str        # "llm_call" | "tool_call" | "tool_result"
    name: str | None
    args: dict | None
    result_preview: str | None
    latency_ms: int
    tokens_used: int | None
    timestamp: datetime
```

- `session.trace` returns the full list.
- `session.export_trace(path)` writes it as newline-delimited
  JSON for ingestion by external tools.
- The TUI gains a `/trace` command that renders the current
  session trace as a formatted table in the scroll buffer.
- `AgentPool` aggregates traces across sessions for pipeline
  debugging.

### Open question before coding
How `AgentPool` aggregates traces across sessions is not yet
designed. The per-session part is ready to implement; the
pool-level aggregation needs a design pass first.

### Where to implement
`davyagent/observability/trace.py` — `TraceEntry` dataclass
and `Tracer` class.
`session.py` — instantiate a `Tracer`; record entries at each
LLM call and tool execution point.
`davy_cli.py` — `/trace` command.

---

## 10. Context compaction

### Problem
A truncator exists (`davyagent/context/window_manager.py`)
but it only drops old messages. Information is silently lost
when the context window fills. The truncator is also inactive
by default — `context_window` is `None` in `ProviderConfig`
unless explicitly set in `config/default.toml`.

### Difference from truncation
Truncation drops turns. Compaction calls the LLM to summarise
the oldest portion of the history into a short
`role="system"` block, then replaces those turns with the
summary. Information is compressed, not deleted.

### Expected behaviour
- A threshold (e.g. 80 % of `context_window`) triggers
  compaction instead of truncation.
- One extra LLM call produces a summary of the turns that
  would otherwise be dropped.
- The summary is injected as a `role="system"` message
  immediately after the primary system prompt.
- The compacted turns are removed from `_history`.
- A `compaction` event is emitted so the TUI can show a
  warning frame ("Context compacted — N turns summarised").

### Open question before coding
Should compaction be the default strategy when
`context_window` is set, or an explicit opt-in flag
(e.g. `compaction = true` in the provider config)?
Compaction costs one extra LLM call per trigger.

### Where to implement
`davyagent/context/compactor.py` — `compact_messages()`
function; takes a message list, a budget, and an LLM client;
returns the compacted list.
`session.py` — in `_build_messages()`, at the point where
`truncate_messages` is called (line ~360), check the
compaction flag and call `compact_messages()` instead.
`config/settings.py` — add `compaction: bool = False` to
`ProviderConfig` (or `AgentConfig`).
`davy_cli.py` — handle the `compaction` event and render a
warning frame.
