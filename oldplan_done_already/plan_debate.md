# Structured Debate — Implementation Plan

Multi-agent structured debate: N agents take turns arguing perspectives
on a topic for a fixed number of rounds. The user observes in a shared
room buffer and can inject messages between turns.
Accessed via `/team → C. Structured Debate`.

Read this plan from top to bottom before writing any code.
Implement each section in the order listed.

---

## Prerequisites — understand these before writing code

### What is `AgentEvent`?
A dataclass defined in `starry_lib/types.py`:
```python
@dataclass
class AgentEvent:
    type: str        # "token" | "done" | "error" | ...
    session_id: str  # identifies which agent spoke
    data: str | dict # token text or full response
```
`session.chat(prompt)` is an async generator that yields `AgentEvent`
objects. You iterate it with `async for event in session.chat(prompt)`.

### What is `session.chat()`?
`session.chat(prompt)` streams the LLM response as `AgentEvent`s:
- `type="token"` events: one chunk of text in `event.data`
- `type="done"` event: `event.data` holds the full response string
- `type="error"` event: `event.data` holds the error message

Use `session.chat()` (not `chat_auto()`) for debate turns — no tools.

### How to get a Session from the pool
```python
session = pool.get(session_id)  # raises KeyError if not found
```

### What is `inject_system_message()`?
```python
session.inject_system_message("some text")
```
Appends a system message to the session's history without calling the
LLM. Used to give agents context at the start of a debate.

### What are `_da_pool` and `_da_settings`?
Module-level globals in `starry_cli/main.py`. Access them directly —
do NOT pass them as parameters to `_do_start_debate`.

### How do dialogs work?
All dialogs are in `starry_cli/dialogs.py` and accessed via `_dlg`.
Callbacks passed to dialogs are synchronous. If you need to call an
async function from a dialog callback, wrap it:
```python
asyncio.ensure_future(my_async_fn(...))
```

### What is `asyncio.Queue`?
A thread-safe queue for passing data between coroutines.
- `queue.put_nowait(item)` — add item without waiting
- `queue.get_nowait()` — get item or raise `asyncio.QueueEmpty`
Import: `import asyncio` (already imported in both files).

---

## Step 1 — Create `starry_lib/agents/debate.py`

Create this file from scratch. Copy the file header format from
`starry_lib/agents/roundtable.py` and adapt it.

### Imports
```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from starry_lib.types import AgentEvent
```

### Class: `Debate`

```python
class Debate:
    """Turn-based multi-agent debate engine.

    Agents speak in round-robin order for a fixed
    number of rounds. User can inject messages
    between turns via inject().

    Usage::

        debate = Debate(
            pool,
            [("alpha", "agent-alpha"),
             ("beta",  "agent-beta")],
            topic="Is Python better than Rust?",
            rounds=2,
        )
        async for event in debate.run():
            print(event.session_id, event.data)
    """
```

### `__init__`

```python
def __init__(
    self,
    pool: object,
    agents: list[tuple[str, str]],
    topic: str,
    rounds: int = 3,
) -> None:
    """
    Args:
        pool: An AgentPool instance.
        agents: Ordered list of (name, session_id)
            pairs. Example:
            [("alpha", "agent-alpha"),
             ("beta",  "agent-beta")].
        topic: The debate topic string.
        rounds: How many full cycles through all
            agents (one cycle = every agent speaks
            once). Minimum 1.
    """
    self._pool = pool
    self._agents: list[tuple[str, str]] = (
        list(agents)
    )
    self._topic = topic
    self._rounds = max(1, rounds)
    self._transcript: list[dict[str, str]] = []
    self._injection_queue: asyncio.Queue = (
        asyncio.Queue()
    )
```

### Properties

```python
@property
def agent_names(self) -> list[str]:
    """Ordered list of participant names."""
    return [name for name, _ in self._agents]

@property
def session_ids(self) -> list[str]:
    """Ordered list of session_ids."""
    return [sid for _, sid in self._agents]
```

### Transcript helpers

```python
def record_turn(
    self, name: str, text: str
) -> None:
    """Append an agent turn to the transcript."""
    self._transcript.append(
        {"name": name, "text": text}
    )

def record_user(self, text: str) -> None:
    """Append a user injection to transcript."""
    self._transcript.append(
        {"name": "You", "text": text}
    )

def format_context(
    self, limit: int = 10
) -> str:
    """Format last `limit` transcript entries.

    Returns a string like:
        [alpha]: Hello
        [beta]: Hi there!
    Returns empty string if transcript is empty.
    """
    recent = self._transcript[-limit:]
    if not recent:
        return ""
    return "\n".join(
        f"[{e['name']}]: {e['text']}"
        for e in recent
    )
```

### `inject`

```python
def inject(self, text: str) -> None:
    """Queue a user message for the next turn.

    The message will be prepended to the next
    agent's prompt as [User]: text.
    """
    self._injection_queue.put_nowait(text)
```

### `get_name_for_sid`

```python
def get_name_for_sid(
    self, sid: str
) -> str | None:
    """Return agent name for a session_id."""
    for name, s in self._agents:
        if s == sid:
            return name
    return None
```

### `run` — the main debate loop

This is the most important method. Read it carefully.

**Turn structure:**
- Total turns = `rounds × N` where N = number of agents.
- Turn index goes from 0 to (rounds × N - 1).
- Agent for turn i = `agents[i % N]`.
- Turn 0 is the opening: prompt = `"Open the debate on: {topic}"`.
- All other turns: prompt = formatted context + `"\n\nNow give your response."`.

**Between turns**, drain the injection queue. If there is a user
message waiting, prepend it to the prompt and record it.

**Sentinel at the end**: after all turns, yield one final
`AgentEvent` with `type="done"` and `data="__debate_complete__"`
and `session_id=""`. The TUI uses this to know the debate finished.

```python
async def run(
    self,
) -> AsyncIterator[AgentEvent]:
    """Run the full debate and yield AgentEvents.

    Yields token and done events per turn, then
    a final sentinel when all rounds are complete.
    The sentinel has type="done",
    data="__debate_complete__", session_id="".

    Each non-sentinel done event carries the
    session_id of the agent that just spoke, so
    the TUI can label the output.
    """
    n = len(self._agents)
    total_turns = self._rounds * n

    # Seed each agent with context about the debate
    names_str = ", ".join(self.agent_names)
    seed = (
        f"You are participating in a structured"
        f" debate on: {self._topic}. "
        f"Other participants: {names_str}. "
        f"Argue your perspective clearly and"
        f" respond to what others say."
    )
    for name, sid in self._agents:
        session = self._pool.get(sid)
        session.inject_system_message(seed)

    for turn_index in range(total_turns):
        name, sid = self._agents[turn_index % n]
        session = self._pool.get(sid)

        # Check for user injection (non-blocking)
        injection = None
        try:
            injection = (
                self._injection_queue.get_nowait()
            )
        except asyncio.QueueEmpty:
            pass

        # Build the prompt for this turn
        if turn_index == 0:
            base = (
                f"Open the debate on:"
                f" {self._topic}"
            )
        else:
            ctx = self.format_context()
            base = (
                f"[Conversation so far]\n"
                f"{ctx}\n\n"
                f"Now give your response."
            )

        if injection is not None:
            prompt = (
                f"[User]: {injection}\n\n{base}"
            )
            self.record_user(injection)
        else:
            prompt = base

        # Stream this agent's turn
        accumulated = ""
        async for event in session.chat(prompt):
            if event.type == "token":
                accumulated += str(event.data)
                yield event
            elif event.type == "done":
                full = str(event.data) or accumulated
                self.record_turn(name, full)
                yield AgentEvent(
                    type="done",
                    session_id=sid,
                    data=full,
                )
            elif event.type == "error":
                yield event

    # Final sentinel — signals debate is complete
    yield AgentEvent(
        type="done",
        session_id="",
        data="__debate_complete__",
    )
```

---

## Step 2 — Add `pool.debate()` to `starry_lib/agents/pool.py`

Add this method to the `AgentPool` class, inside the
`# ── Multi-agent patterns ──────────────────────────────────────`
section (after the `pipeline` method).

Also add the import at the top of the file:
```python
# Add to existing imports, near the other from-imports:
from starry_lib.agents.debate import Debate
```

### Method

```python
async def debate(
    self,
    agents: list[tuple[str, str]],
    topic: str,
    rounds: int = 3,
) -> Debate:
    """Create a Debate instance for the given agents.

    Validates that all session_ids are registered.
    Does NOT start the debate — call debate.run()
    to begin.

    Args:
        agents: Ordered list of (name, session_id).
            All session_ids must already be
            registered in this pool.
        topic: The debate topic.
        rounds: Full cycles through all agents.

    Raises:
        KeyError: if any session_id is not found.

    Returns:
        A Debate instance ready to run.
    """
    for name, sid in agents:
        if sid not in self._sessions:
            raise KeyError(
                f"Session '{sid}' for agent"
                f" '{name}' is not registered."
            )
    return Debate(
        pool=self,
        agents=agents,
        topic=topic,
        rounds=rounds,
    )
```

---

## Step 3 — Changes in `starry_cli/main.py`

Make changes in the order listed below.

### 3a — New globals

Find this block in `main.py`:
```python
_roundtable = None             # Roundtable | None
_rt_room_buf = None            # room Buffer | None
```

Add these two lines immediately after it:
```python
_debate = None                 # Debate | None
_debate_room_buf = None        # debate room Buffer | None
```

### 3b — `_append_debate_room` helper

Find the `_append_room` function:
```python
def _append_room(text):
    """Append plain text to the room buffer.
    ...
    """
    if _rt_room_buf is not None:
        _buf_append(_rt_room_buf, text)
```

Add this new function immediately after `_append_room`:
```python
def _append_debate_room(text):
    """Append plain text to the debate room buffer.

    Does nothing if the debate buffer does not exist.
    """
    if _debate_room_buf is not None:
        _buf_append(_debate_room_buf, text)
```

### 3c — `_spawn_debate_bufs`

Find the `_spawn_roundtable_bufs` function (search for
`def _spawn_roundtable_bufs`). Add the new function
immediately after it (after the closing line of
`_spawn_roundtable_bufs`):

```python
def _spawn_debate_bufs(app, agent_names):
    """Create Debate Room tab and spawn agent bufs.

    Creates a read-only Debate Room buffer registered
    as 'debate:room' and adds a Debate Room tab.
    For each agent name that has no buffer yet,
    calls _spawn_agent_bufs() to create one.
    Switches the active tab to the Debate Room tab.
    Returns the room Buffer object.
    """
    from prompt_toolkit.buffer import Buffer
    room_buf = Buffer(
        name="debate_room",
        read_only=True,
    )
    buf_reg.register("debate:room", room_buf)
    room_tab = Tab(
        "Debate Room", room_buf, read_only=True
    )
    tab_mgr.tabs.append(room_tab)
    tab_mgr.active = len(tab_mgr.tabs) - 1
    for name in agent_names:
        if _agent_chat_buf(name) is None:
            _spawn_agent_bufs(app, name)
    app.invalidate()
    return room_buf
```

### 3d — `handle_debate_response`

Find `handle_roundtable_response`. Add this new async
function immediately after it:

```python
async def handle_debate_response(app):
    """Drive the debate loop and render to room buffer.

    Iterates debate.run() and routes each event:
    - token: accumulate per session_id (not rendered)
    - done with data="__debate_complete__": debate over
    - done with agent data: write [name]: text to room
    - error: write error line to room buffer
    """
    global _debate, _debate_room_buf
    if _debate is None or _debate_room_buf is None:
        return

    accumulated: dict[str, str] = {}

    async for event in _debate.run():
        if event.type == "token":
            accumulated[event.session_id] = (
                accumulated.get(
                    event.session_id, ""
                )
                + str(event.data)
            )
        elif event.type == "done":
            if event.data == "__debate_complete__":
                _append_debate_room(
                    "\n--- Debate complete ---\n"
                )
                app.invalidate()
                _offer_debate_synthesis(app)
                return
            name = _debate.get_name_for_sid(
                event.session_id
            )
            if name is None:
                continue
            full = str(event.data) or (
                accumulated.get(
                    event.session_id, ""
                )
            )
            _append_debate_room(
                f"\n[{name}]: {full}\n"
            )
            app.invalidate()
        elif event.type == "error":
            name = _debate.get_name_for_sid(
                event.session_id
            ) or "agent"
            _append_debate_room(
                f"[{name} error]: {event.data}\n"
            )
            app.invalidate()
```

### 3e — `_offer_debate_synthesis`

Add this function immediately after
`handle_debate_response`:

```python
def _offer_debate_synthesis(app):
    """Ask if user wants a synthesis summary.

    Shows a Yes/No button dialog. If Yes, spawns
    a throwaway agent to summarize the debate
    transcript.
    """
    global _debate
    if _debate is None:
        return

    transcript_text = _debate.format_context(
        limit=200
    )

    def _on_button(idx):
        if idx != 0:  # 0 = Yes, 1 = No
            return
        if _da_pool is None:
            return

        async def _do_synthesis():
            prompt = (
                "Summarize the following debate"
                " and identify the strongest"
                " arguments on each side:\n\n"
                f"{transcript_text}"
            )
            summary = await _da_pool.run_subtask(
                prompt, mode="plan"
            )
            _append_debate_room(
                f"\n[Synthesis]:\n{summary}\n"
            )
            app.invalidate()

        asyncio.ensure_future(_do_synthesis())

    _dlg.show_button_dialog(
        app,
        title="Debate complete",
        message=(
            "Would you like a synthesis summary?"
        ),
        buttons=["Yes", "No"],
        on_button=_on_button,
        refocus=input_area,
    )
```

### 3f — `_do_start_debate`

Find `_do_start_roundtable`. Add the new function
immediately after it:

```python
async def _do_start_debate(
    app, names, topic, rounds
):
    """Spawn named agents and open the Debate Room tab.

    Called by the /team command handler.
    Spawns each agent in names if not yet active,
    builds the agents list, creates the Debate,
    and opens the Debate Room buffer.

    Args:
        app: The prompt_toolkit Application.
        names: list[str] of agent names.
        topic: The debate topic string.
        rounds: Number of full cycles (int >= 1).
    """
    global _debate, _debate_room_buf
    global _active_registry
    if _active_registry is None:
        from starry_lib.agents.active_registry\
            import ActiveRegistry
        _active_registry = ActiveRegistry()
        _init_agent_tools()
    for name in names:
        try:
            if not _active_registry.is_active(name):
                await _active_registry.spawn_agent(
                    name,
                    _da_pool,
                    _da_settings,
                )
        except Exception as exc:
            append_text(
                build_error_frame(
                    f"Cannot spawn '{name}': {exc}"
                )
            )
            app.invalidate()
            return

    agents = [
        (name, f"agent-{name}") for name in names
    ]
    _debate = await _da_pool.debate(
        agents, topic, rounds
    )
    _debate_room_buf = _spawn_debate_bufs(
        app, names
    )
    joined = ", ".join(names)
    _append_debate_room(
        f"Debate started — topic: {topic}\n"
        f"Participants: {joined}\n"
        f"Rounds: {rounds}\n"
        "Type a message to inject into the debate.\n"
        "Type /close to exit.\n"
        "─" * 40 + "\n"
    )
    app.invalidate()
    asyncio.ensure_future(
        handle_debate_response(app)
    )
```

### 3g — Update `/team` option list and handler

Find this list in the `/team` handler:
```python
_TEAM_OPTIONS = [
    "A. Roundtable",
    "B. Facilitator (soon)",
    "C. Structured Debate (soon)",
    "D. Collaborative Chain (soon)",
]
```

Change only the third entry:
```python
    "C. Structured Debate",
```

Then find the `_on_team_select` callback inside the `/team`
handler. It currently checks `if idx != 0: ... return`.

Change it so that `idx == 0` handles Roundtable (existing
code, no change) and `idx == 2` handles Structured Debate.
Add a new `elif idx == 2:` branch:

```python
elif idx == 2:
    # ── Structured Debate ─────────────────────
    if (
        _da_settings is None
        or _da_pool is None
    ):
        append_text(
            build_error_frame(
                "Session not ready."
            )
        )
        app.invalidate()
        return
    from starry_lib.agents\
        .agent_store import list_agents
    agent_cfgs = list_agents()
    if len(agent_cfgs) < 2:
        append_text(
            build_warn_frame(
                "Need at least 2 agents."
                " Use /agent → Create first."
            )
        )
        app.invalidate()
        return
    agent_names = [
        cfg.name for cfg in agent_cfgs
    ]

    def _on_debate_agents(indices):
        if len(indices) < 2:
            append_text(
                build_warn_frame(
                    "Select at least 2 agents."
                )
            )
            app.invalidate()
            return
        chosen = [
            agent_names[i] for i in indices
        ]

        def _on_topic(topic_text):
            if not topic_text.strip():
                append_text(
                    build_warn_frame(
                        "Topic cannot be empty."
                    )
                )
                app.invalidate()
                return

            def _on_rounds(rounds_text):
                try:
                    rounds = int(
                        rounds_text.strip()
                    )
                    if rounds < 1:
                        raise ValueError
                except ValueError:
                    rounds = 3
                asyncio.ensure_future(
                    _do_start_debate(
                        app,
                        chosen,
                        topic_text.strip(),
                        rounds,
                    )
                )

            _dlg.show_input_dialog(
                app,
                title=(
                    "Structured Debate"
                    " — Rounds"
                ),
                label=(
                    "Number of rounds"
                    " (default 3):"
                ),
                on_confirm=_on_rounds,
                refocus=input_area,
                initial_text="3",
            )

        _dlg.show_input_dialog(
            app,
            title="Structured Debate — Topic",
            label="Enter the debate topic:",
            on_confirm=_on_topic,
            refocus=input_area,
        )

    _dlg.show_toggle_dialog(
        app,
        title=(
            "Structured Debate"
            " — Select Agents"
        ),
        items=agent_names,
        on_confirm=_on_debate_agents,
        refocus=input_area,
        max_visible=8,
    )
```

### 3h — Debate input routing in `accept_handler`

Find the Roundtable routing block in `accept_handler`:
```python
        # ── Roundtable routing ────────────
        global _roundtable, _rt_room_buf
        if _roundtable is not None:
```

Add a new block **immediately after** the roundtable
routing block (after its closing `return`):

```python
        # ── Debate routing ────────────────
        global _debate, _debate_room_buf
        if _debate is not None:
            if text.lower() == "/close":
                _debate = None
                _debate_room_buf = None
                tab_mgr.goto_tab(0)
                app.invalidate()
                return
            if text:
                _debate.inject(text)
                _append_debate_room(
                    f"[You]: {text}\n"
                )
                app.invalidate()
            return
```

**Important:** the `/close` check inside `_debate is not None`
handles closing the debate. The global `/close` handler further
down in `accept_handler` does not need to change.

---

## Step 4 — Verify the turn-count example

With 3 agents (`alpha`, `beta`, `gamma`) and `rounds=2`:

```
total_turns = 2 × 3 = 6

Turn 0  → alpha  (opening statement on topic)
Turn 1  → beta   (context from transcript)
Turn 2  → gamma  (context from transcript)
Turn 3  → alpha  (context from transcript)
Turn 4  → beta   (context from transcript)
Turn 5  → gamma  (context from transcript)
--- Debate complete ---
```

Each agent speaks exactly `rounds` times.

---

## Common mistakes to avoid

1. **Do NOT use `await` in dialog callbacks.** Dialogs call their
   `on_confirm` synchronously. Wrap async calls with
   `asyncio.ensure_future(coro())`.

2. **Do NOT call `session.chat_auto()`** in the debate loop. Use
   `session.chat(prompt)` — no tools in debate turns.

3. **Do NOT confuse the sentinel with a normal done event.** Check
   `event.data == "__debate_complete__"` before treating a `done`
   event as an agent response.

4. **`asyncio.QueueEmpty` must be caught** when calling
   `get_nowait()`. If you forget, the loop crashes when there is no
   injection waiting.

5. **`_da_pool` and `_da_settings` are globals in `main.py`.**
   Do not shadow them with local parameters of the same name inside
   `_do_start_debate`.

6. **The `Debate` import in `pool.py`** must be a module-level
   import (top of file), not inside the method.

---

## File summary

| File | Change |
|------|--------|
| `starry_lib/agents/debate.py` | Create new file — `Debate` class |
| `starry_lib/agents/pool.py` | Import `Debate`; add `pool.debate()` method |
| `starry_cli/main.py` | Steps 3a–3h above |
