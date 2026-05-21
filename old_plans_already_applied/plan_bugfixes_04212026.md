# plan_bugfixes_04212026.md — Bug Fix Backlog
# Date: 04/21/2026

Tracks confirmed bugs with root-cause analysis and a
concrete fix for each. Add new entries as bugs are found.

Status values: open | in_progress | fixed

---

## BUG-001 — chat_with_tools(): follow-up response uses
##            stream=True, so done.data is always ""
##            after a tool call round-trip

**Status**: fixed
**File**: `davyagent/agents/session.py`
**Method**: `chat_with_tools()` (line ≈ 612–633)
**Failing test**:
  `tests/integration/test_streaming.py::
   test_chat_with_tools_yields_done_with_final`

### Root cause

`chat_with_tools()` is documented as a "Non-streaming
turn": the **first** LLM request is made without
`stream=True` and the content is read directly from
`response.choices[0].message.content`.

When the model returns `finish_reason == "tool_calls"`,
the method executes the tools and then makes a **second**
LLM request to get the final answer. That second request
is incorrectly made with `stream=True`:

```python
stream = await self._client.chat.completions.create(
    model=self._agent.model,
    messages=messages,
    stream=True,          # ← wrong for non-streaming method
)
async for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        final_tokens.append(delta.content)
        ...
```

After the loop, the final text is assembled with:

```python
final = (
    "".join(final_tokens)   # empty when stream=True mock
    if tool_calls_made       # yields nothing
    else response.choices[0].message.content
)
```

Because `async for chunk in stream:` iterates a plain
`MagicMock` (non-async-iterable) that yields nothing,
`final_tokens` stays `[]` and `final == ""`.  The `done`
event therefore carries an empty string instead of the
model's actual answer.

### Fix

Replace the streaming follow-up call with a plain
non-streaming call and read content the same way as the
no-tool path:

```python
# replace the stream=True block with:
async with self._semaphore:
    followup = (
        await self._client.chat.completions.create(
            model=self._agent.model,
            messages=messages,
        )
    )
final_text = (
    followup.choices[0].message.content or ""
)
final_tokens.append(final_text)
```

Remove the token-yielding loop for the follow-up (no
streaming tokens are emitted in a "Non-streaming turn").
The `done` event then carries the correct full text.

### Impact

- `done.data` is always `""` when any tool was called,
  regardless of what the model returns.
- Every flow that uses tool calling (all execution-mode
  sessions) silently loses the model's final answer.
- History is also corrupt: the assistant message stored
  in `_history` is `""` after any tool-call round-trip.

### Acceptance criteria

- `test_chat_with_tools_yields_done_with_final` passes.
- `done.data` equals the model's actual response content.
- History entry for the assistant turn is non-empty.
- No regression in the other `chat_with_tools` tests.

---

## BUG-002 — No world-state context: agent wastes a tool
##            call on basic orientation every session

**Status**: fixed
**File**: `davyagent/agents/base.py`,
          `davyagent/context/world_state.py` (new)
**Method / area**: `BaseAgent.build_messages()`
**Failing test**: none (missing feature)

### Root cause

`build_messages()` injects only the role's system prompt.
There is no ambient block describing the current date,
working directory, hostname, git branch, or OS. The agent
must call `bash` with `pwd`, `date`, `git branch`, etc.
to orient itself — wasting a full turn on context that
every production framework provides automatically.

### Fix

Add a `davyagent/context/world_state.py` helper that
assembles a lightweight environment snapshot:

```python
def build_world_state() -> str:
    """Return a markdown environment block."""
    # reads: datetime.now(), os.getcwd(),
    # platform, socket.gethostname(), os.getenv("USER"),
    # subprocess git rev-parse + git status --short
    # git calls must fail silently outside a repo
```

In `BaseAgent.build_messages()`, append a
`role="system"` message after the main system prompt
containing the rendered block. The block must be
regenerated on every call (not cached at session start)
so `cwd`, time, and git state stay accurate.

Delimit the block clearly so it does not blend with the
role's instructions:

```
<environment>
date: 2026-04-21  time: 14:32 UTC
cwd:  /home/armando/davy_agent
host: workstation  user: armando
git:  main (clean)
os:   Ubuntu 22.04  Python 3.11.9
</environment>
```

### Impact

- Agent spends the first tool call of every task just
  discovering its own working directory and date.
- Git-aware tasks (branch names, status) require an
  explicit `bash` call even when the info is trivially
  available.

### Acceptance criteria

- Every LLM call includes an up-to-date environment
  block injected as a system message.
- The block reflects the actual cwd, date, and git
  branch at call time, not session-start time.
- When not in a git repo, the git fields are absent
  and no exception is raised.
- Unit test: `build_world_state()` returns a non-empty
  string containing at least `date`, `cwd`, and `os`.

---

## BUG-003 — Conversation history grows unbounded;
##            exceeding the context window causes
##            silent truncation or API failure

**Status**: fixed
**File**: `davyagent/agents/session.py`,
          `davyagent/context/window_manager.py` (new),
          `davyagent/config/settings.py`
**Method / area**: `Session._build_messages()`
**Failing test**: none (missing feature, silent failure)

### Root cause

`_build_messages()` appends the full `_history` list to
every LLM call with no length check. As the session grows,
the message list eventually exceeds the model's context
limit. The provider either:

1. Returns an API error (hard failure, no recovery).
2. Silently truncates from an arbitrary position,
   corrupting the dialogue mid-thought.

There is no per-provider `context_window` declaration and
no truncation strategy.

### Fix

**Step 1 — declare context limits in config**

Add an optional field to `ProviderConfig`:

```toml
[providers.davy]
context_window = 128000   # tokens; omit to disable mgmt
```

```python
class ProviderConfig(BaseModel):
    context_window: int | None = None
```

**Step 2 — add `davyagent/context/window_manager.py`**

```python
def truncate_messages(
    messages: list[dict],
    limit: int,
    model: str,
) -> list[dict]:
    """Trim messages to fit within limit tokens.

    Strategy (applied in order):
    1. Drop tool results (role="tool") oldest-first.
    2. Drop user/assistant turns oldest-first,
       always keeping the system prompt(s) and the
       last 4 turns.
    3. Hard-truncate content strings as a last resort.
    """
```

Token counting uses `len(json.dumps(msg)) // 4` as a
cheap approximation (no tiktoken dependency).

**Step 3 — call from `_build_messages()`**

```python
def _build_messages(self, user_input, history=None):
    msgs = ...  # current assembly
    limit = self._context_window  # from provider config
    if limit:
        msgs = truncate_messages(msgs, limit, self._agent.model)
    return msgs
```

### Impact

- Long sessions fail with cryptic API errors or produce
  incoherent responses due to silent mid-history cuts.
- No warning is emitted; the user has no idea why the
  agent "forgot" earlier context.

### Acceptance criteria

- A session with a message list exceeding `context_window`
  tokens is silently trimmed before each LLM call.
- System prompts and the most recent 4 turns are always
  preserved.
- Tool results are dropped before user/assistant turns.
- Unit test: `truncate_messages()` with a tight limit
  returns a list whose serialised size is under the limit.
- No regression when `context_window` is not set
  (manager is bypassed entirely).

---

## Template for new entries

```
## BUG-XXX — <one-line title>

**Status**: open
**File**: `<path>`
**Method / area**: `<name>` (line ≈ N)
**Failing test**: `<test path>::<test name>` (or "none")

### Root cause
<brief explanation>

### Fix
<what to change>

### Impact
<what breaks in production>

### Acceptance criteria
- <test that must pass>
- <observable behavior>
```
