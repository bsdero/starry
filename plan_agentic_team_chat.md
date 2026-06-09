# Implementation Plan — Team Chat B (Facilitator) and D (Chain)

> **Audience**: This document is meant to be followed
> step-by-step with no prior knowledge of the codebase.
> Read every section fully before touching any file.
> All decisions have already been made; do not invent
> alternatives.

---

## 0. Context and decisions already made

The `starry` project is a Python TUI + LLM
orchestration system. Two team chat modes, A
(Roundtable) and C (Debate), are already implemented.
You are implementing B (Facilitator) and D (Chain)
following the exact same patterns.

**All design decisions are fixed:**
- Facilitator always spawned in execution mode
  (needs `call_agent` tool).
- Chain agents spawned normally (execution mode via
  `ActiveRegistry`); chain uses `session.chat()`
  so tools are never invoked during stages.
- Transparent mode shows dim tool-traffic lines.
- Chain order = agent list order (no reordering).
- Checkpoint appears after every stage including
  the last.
- Synthesis follows C4/C5/C6 from
  `common_behavior_team_chat.md` for both modes.
- Pool factory methods added for both modes.

---

## 1. Files to create (new files)

| File | Purpose |
|------|---------|
| `starry_lib/agents/facilitator.py` | `Facilitator` class |
| `starry_lib/agents/chain.py` | `Chain` class |

## 2. Files to modify (existing files)

| File | What changes |
|------|-------------|
| `starry_lib/agents/pool.py` | Add `facilitator()` and `chain()` factory methods |
| `starry_cli/main.py` | Globals, helpers, handlers, routing, menus |

---

## 3. Common behavior rules (C1–C10)

These rules from `common_behavior_team_chat.md` apply
to BOTH modes. Check them off for every function you
write.

| Rule | When | What to do |
|------|------|-----------|
| C1 | Mode start | Append room tab, record its index, spawn agent tabs, restore `tab_mgr.active` to room tab index |
| C2 | Streaming | Accumulate tokens in `partial_text[name]`; on `done` append `build_team_agent_frame(name, full, color)` to room buffer |
| C3 | `/exit` | `_teardown_<mode>(app)` then `asyncio.ensure_future` a coroutine that sleeps 0.3s and calls `app.exit()` |
| C4 | `/close` | Call `_run_<mode>_synthesis(app)` and return |
| C5 | Synthesis | Run `_da_pool.run_subtask(prompt, mode="plan")`; no yes/no dialog; parse with `_extract_follow_ups` |
| C6 | After synthesis | Level 1: Save & continue / Save & close. Level 2: follow-up questions + End session |
| C7 | Teardown | Clear all mode globals, clear `_team_agent_colors`, reset `_team_color_next = 0`, call `tab_mgr.goto_tab(0)` |
| C8 | User input | Append `build_user_frame(text, _exec_mode)` to the room buffer |
| C9 | After agents finish | Append `build_inline_notif("Your turn", "→")` to room buffer |
| C10 | Mode start | Append dim welcome lines to room buffer; last line must say `/close — finish & synthesize \| /exit — quit` |

---

## 4. Key existing helpers in `main.py`

You will use all of these. They are already defined;
**do not redefine them.**

```
M_DIM         line ~507    dim text marker (str "Dm")
M_NFRAME      line ~511    notification frame marker
M_EFRAME      line ~514    error frame marker
frame_width() line ~185    returns terminal width (int)

_buf_append(buf, text)
    line ~2914  appends text to a Buffer object

_replace_buf_last(buf, n_lines, new_text)
    line ~3269  replaces last N lines in a Buffer

build_user_frame(text, mode)
    renders user input as a styled frame string

build_team_agent_frame(name, text, color_idx)
    renders an agent response frame string

build_synthesis_frame(text)
    renders synthesis result as a styled frame string

build_inline_notif(label, icon)
    returns a single notification line string

build_error_frame(text)
    returns an error frame string

build_warn_frame(text)
    returns a warning frame string

_get_team_color(name)
    returns a palette color index (int 0-7);
    auto-assigns on first call

_extract_follow_ups(text)
    parses synthesis output; returns (clean_text, fups)
    where fups is a list of question strings

_save_synthesis_file(mode_name, text)
    saves synthesis to
    ~/.local/starry/summaries/<mode>_<ts>.md
    returns Path on success, None on error

_spawn_agent_bufs(app, name)
    creates chat + log buffers for a named agent;
    appends a tab; sets tab_mgr.active

_agent_chat_buf(name)
    returns chat Buffer for named agent or None

debate_menu
    line ~1525  shared SelectionMenu() instance;
    ALL team modes reuse this same object

_dlg
    dialogs module; provides:
      _dlg.show_menu_dialog(app, title, options,
                            on_select, refocus)
      _dlg.show_toggle_dialog(app, title, items,
                              on_confirm, refocus,
                              max_visible)
      _dlg.show_input_dialog(app, title, label,
                             on_confirm, refocus,
                             initial_text="")
      _dlg.show_button_dialog(app, title, message,
                              buttons, on_button,
                              refocus)

input_area   the TUI input widget (for refocus=)
buf_reg      buffer registry:
               buf_reg.register(key, buf)
               buf_reg.get(key)
tab_mgr      tab manager:
               tab_mgr.tabs     list of Tab objects
               tab_mgr.active   int, active tab index
               tab_mgr.goto_tab(n)
Tab(label, buffer, read_only=bool)
               creates a tab object

_da_pool     the active AgentPool (can be None)
_da_settings the active AppSettings (can be None)
_active_registry  the ActiveRegistry (can be None)
_exec_mode   current execution mode string
asyncio.ensure_future(coro())
             use this inside accept_handler() because
             accept_handler is sync — never await there
```

---

## 5. Step 1 — Create `starry_lib/agents/facilitator.py`

Create this file. Copy the header format from
`debate.py` (first 17 lines). The class wraps a
single facilitator session and yields all events
from `session.chat_auto()`.

**Important**: `chat_auto()` is required (not
`chat()`) because the facilitator needs the
`call_agent` tool to delegate to specialists.

```python
#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       facilitator.py
# DESCRIPTION: Facilitator — coordinator agent with
#              specialist delegation
# SUMMARY: One facilitator session receives user
#          messages and uses call_agent to delegate
#          subtasks to specialist agents.
# NOTES: Uses chat_auto() so call_agent tool is
#        available. TUI drives the session.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Facilitator: coordinator + specialist delegation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from starry_lib.types import AgentEvent


class Facilitator:
    """Coordinator agent that delegates to specialists.

    One facilitator session receives user messages and
    uses the call_agent tool to route subtasks to named
    specialist agents, then synthesizes a reply.

    Usage::

        fac = Facilitator(
            pool,
            facilitator_name="coordinator",
            facilitator_sid="agent-coordinator",
            specialist_names=["researcher", "coder"],
        )
        async for event in fac.post("Help!"):
            print(event.type, event.data)
    """

    def __init__(
        self,
        pool: object,
        facilitator_name: str,
        facilitator_sid: str,
        specialist_names: list[str],
    ) -> None:
        self._pool = pool
        self._facilitator_name = facilitator_name
        self._facilitator_sid = facilitator_sid
        self._specialist_names = list(
            specialist_names
        )
        self._transcript: list[dict[str, str]] = []

    # ── Public properties ─────────────────────────

    @property
    def facilitator_name(self) -> str:
        """Name of the facilitator agent."""
        return self._facilitator_name

    @property
    def specialist_names(self) -> list[str]:
        """Names of all specialist agents."""
        return list(self._specialist_names)

    @property
    def all_agent_names(self) -> list[str]:
        """Facilitator name + specialist names."""
        return (
            [self._facilitator_name]
            + self._specialist_names
        )

    # ── Transcript helpers ────────────────────────

    def record_user(self, text: str) -> None:
        """Append a user message to the transcript."""
        self._transcript.append(
            {"name": "You", "text": text}
        )

    def record_response(self, text: str) -> None:
        """Append a facilitator reply to transcript."""
        self._transcript.append(
            {
                "name": self._facilitator_name,
                "text": text,
            }
        )

    def format_context(
        self, limit: int = 10
    ) -> str:
        """Format last `limit` transcript entries.

        Returns a string like:
            [You]: Hello
            [coordinator]: I'll look into that.
        Returns empty string if transcript is empty.
        """
        recent = self._transcript[-limit:]
        if not recent:
            return ""
        return "\n".join(
            f"[{e['name']}]: {e['text']}"
            for e in recent
        )

    async def summarize_positions(
        self,
    ) -> dict[str, str]:
        """Ask the facilitator to summarize session.

        Returns {facilitator_name: summary_text}.
        Does not record to transcript.
        Used by _continue_facilitator to re-seed
        the session after a history clear.
        """
        session = self._pool.get(
            self._facilitator_sid
        )
        prompt = (
            "In 2-3 sentences, summarize the key"
            " outcomes and decisions from this"
            " session. Be concise."
        )
        try:
            text = await session.chat_complete(
                prompt
            )
        except Exception:
            text = ""
        return {self._facilitator_name: text}

    # ── Core post ─────────────────────────────────

    async def post(
        self, user_text: str
    ) -> AsyncIterator[AgentEvent]:
        """Stream the facilitator response.

        Sends user_text to the facilitator session
        using chat_auto() (tool-enabled). Yields ALL
        event types: token, done, tool_call,
        tool_result, error.

        The TUI is responsible for rendering each
        event type appropriately.
        """
        session = self._pool.get(
            self._facilitator_sid
        )
        async for event in session.chat_auto(
            user_text
        ):
            yield event
```

---

## 6. Step 2 — Create `starry_lib/agents/chain.py`

The Chain class only stores state. The TUI drives
execution stage-by-stage by calling
`chain.get_session(idx)` and streaming directly
from that session. This design is intentional: it
allows checkpoint pauses between stages.

```python
#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       chain.py
# DESCRIPTION: Chain — sequential multi-agent pipeline
# SUMMARY: Agents work in order; each agent output
#          becomes the next agent input.
# NOTES: The TUI drives execution stage-by-stage.
#        Chain has no run() method. Use get_session()
#        and record_stage() from the TUI.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Chain: sequential multi-agent pipeline."""

from __future__ import annotations

import asyncio


class Chain:
    """Sequential agent pipeline.

    The TUI calls get_session(idx) to get the Session
    for a stage, streams it, and records the output
    with record_stage(). This design lets checkpoint
    menus pause execution between stages.

    Usage::

        chain = Chain(
            pool,
            agents=[
                ("writer", "agent-writer"),
                ("editor", "agent-editor"),
            ],
        )
        # Stage 0:
        session = chain.get_session(0)
        # stream session.chat(task) ...
        chain.record_stage("writer", output)
        # Stage 1:
        session = chain.get_session(1)
        # stream session.chat(output) ...
        chain.record_stage("editor", final)
    """

    def __init__(
        self,
        pool: object,
        agents: list[tuple[str, str]],
    ) -> None:
        """
        Args:
            pool: An AgentPool instance.
            agents: Ordered list of (name, session_id)
                pairs. Chain runs in this order.
        """
        self._pool = pool
        self._agents: list[tuple[str, str]] = (
            list(agents)
        )
        self._transcript: list[dict[str, str]] = []
        self._stage_outputs: list[str] = []

    # ── Public properties ─────────────────────────

    @property
    def agent_names(self) -> list[str]:
        """Ordered list of agent names."""
        return [n for n, _ in self._agents]

    @property
    def agents(self) -> list[tuple[str, str]]:
        """Ordered (name, session_id) pairs."""
        return list(self._agents)

    @property
    def stage_count(self) -> int:
        """Total number of stages in the chain."""
        return len(self._agents)

    # ── Stage accessors ───────────────────────────

    def get_session(self, idx: int):
        """Return Session for stage idx, or None."""
        if 0 <= idx < len(self._agents):
            _, sid = self._agents[idx]
            return self._pool.get(sid)
        return None

    def get_name(self, idx: int) -> str | None:
        """Return agent name for stage idx."""
        if 0 <= idx < len(self._agents):
            return self._agents[idx][0]
        return None

    def get_sid(self, idx: int) -> str | None:
        """Return session_id for stage idx."""
        if 0 <= idx < len(self._agents):
            return self._agents[idx][1]
        return None

    # ── Transcript helpers ────────────────────────

    def record_stage(
        self, name: str, text: str
    ) -> None:
        """Record a completed stage output.

        Call this after each stage's done event.
        The text is also stored in _stage_outputs
        (indexed by insertion order = stage order).
        """
        self._transcript.append(
            {"name": name, "text": text}
        )
        self._stage_outputs.append(text)

    def format_context(
        self, limit: int = 10
    ) -> str:
        """Format last `limit` transcript entries.

        Returns a string like:
            [writer]: Draft content here.
            [editor]: Revised content here.
        Returns empty string if transcript is empty.
        """
        recent = self._transcript[-limit:]
        if not recent:
            return ""
        return "\n".join(
            f"[{e['name']}]: {e['text']}"
            for e in recent
        )

    async def summarize_positions(
        self,
    ) -> dict[str, str]:
        """Ask each agent for a 2-3 sentence summary.

        Concurrent chat_complete() calls. Returns
        {name: summary_text}. Does not touch
        transcript. Used by _continue_chain to
        re-seed sessions after history clear.
        """
        prompt = (
            "In 2-3 sentences, summarize your"
            " contribution and the key output"
            " you produced. Be concise."
        )

        async def _one(name, sid):
            session = self._pool.get(sid)
            try:
                text = await session.chat_complete(
                    prompt
                )
            except Exception:
                text = ""
            return name, text

        results = await asyncio.gather(
            *[
                _one(name, sid)
                for name, sid in self._agents
            ]
        )
        return dict(results)
```

---

## 7. Step 3 — Modify `starry_lib/agents/pool.py`

### 7a. Add imports at the top of the file

After the existing import:
```python
from starry_lib.agents.debate import Debate
```
Add these two lines:
```python
from starry_lib.agents.facilitator import Facilitator
from starry_lib.agents.chain import Chain
```

### 7b. Add two factory methods

Insert both methods **inside** the `AgentPool` class,
**after** the existing `debate()` method (around
line 471, after the closing of `debate()`).

```python
    def facilitator(
        self,
        facilitator_name: str,
        facilitator_sid: str,
        specialist_names: list[str],
    ) -> Facilitator:
        """Create a Facilitator instance.

        Validates that facilitator_sid is registered.
        Does NOT start anything — just creates the
        Facilitator object.

        Args:
            facilitator_name: Display name for the
                coordinator agent.
            facilitator_sid: Registered session ID,
                e.g. 'agent-coordinator'.
            specialist_names: Display names of
                specialist agents (they must already
                be spawned before calling this).

        Raises:
            KeyError: if facilitator_sid not found.

        Returns:
            A Facilitator instance ready to use.
        """
        if facilitator_sid not in self._sessions:
            raise KeyError(
                f"Session '{facilitator_sid}'"
                " not found."
            )
        return Facilitator(
            pool=self,
            facilitator_name=facilitator_name,
            facilitator_sid=facilitator_sid,
            specialist_names=specialist_names,
        )

    def chain(
        self,
        agents: list[tuple[str, str]],
    ) -> Chain:
        """Create a Chain instance.

        Validates all session_ids are registered.
        Does NOT start anything — just creates the
        Chain object.

        Args:
            agents: Ordered list of (name, session_id)
                pairs. All session_ids must already
                be registered in this pool.

        Raises:
            KeyError: if any session_id is not found.

        Returns:
            A Chain instance ready to use.
        """
        for name, sid in agents:
            if sid not in self._sessions:
                raise KeyError(
                    f"Session '{sid}' for agent"
                    f" '{name}' is not registered."
                )
        return Chain(pool=self, agents=agents)
```

---

## 8. Step 4 — Modify `starry_cli/main.py`

`main.py` is a ~12 900-line file. Work through the
sub-steps below in order. Use function names as
anchors (do NOT rely on line numbers alone; they
shift with each insertion).

---

### 8a. Add new global variables

**Where**: in the globals block, after this line:
```python
_debate_room_buf = None        # debate room Buffer | None
```

**Add**:
```python
_facilitator = None          # Facilitator | None
_facilitator_room_buf = None # room Buffer | None
_facilitator_transparent = True  # show tool traffic
_chain = None                # Chain | None
_chain_room_buf = None       # room Buffer | None
_chain_checkpoint = False    # pause between stages
_chain_stage_idx = 0         # active stage index
_chain_running = False       # chain executing now
_chain_auto_closed = False   # synthesis auto-fired
```

---

### 8b. Add two append-helper functions

**Where**: directly after the `_append_debate_room`
function. Insert both together.

```python
def _append_facilitator_room(text):
    """Append text to the facilitator room buffer.

    Does nothing if the buffer does not exist.
    """
    if _facilitator_room_buf is not None:
        _buf_append(_facilitator_room_buf, text)


def _append_chain_room(text):
    """Append text to the chain room buffer.

    Does nothing if the buffer does not exist.
    """
    if _chain_room_buf is not None:
        _buf_append(_chain_room_buf, text)
```

---

### 8c. Add two spawn-buffer functions

**Where**: directly after `_spawn_debate_bufs`.

These follow the exact C1 pattern:
1. Create a read-only Buffer.
2. Register it in `buf_reg`.
3. Create a Tab and append to `tab_mgr.tabs`.
4. Record `room_tab_idx = len(tab_mgr.tabs) - 1`
   **before** the agent-spawn loop.
5. Loop through agent names and call
   `_spawn_agent_bufs(app, name)` for new agents.
6. Restore `tab_mgr.active = room_tab_idx`.
7. Call `app.invalidate()`.
8. Return the room Buffer.

```python
def _spawn_facilitator_bufs(app, agent_names):
    """Create Facilitator Room tab and agent bufs.

    Creates a read-only room buffer registered as
    'facilitator:room'. Adds a Facilitator Room tab.
    For each agent name without a buffer, calls
    _spawn_agent_bufs(). Restores focus to the
    room tab (C1). Returns the room Buffer.
    """
    from prompt_toolkit.buffer import Buffer
    room_buf = Buffer(
        name="facilitator_room",
        read_only=True,
    )
    buf_reg.register("facilitator:room", room_buf)
    room_tab = Tab(
        "Facilitator Room",
        room_buf,
        read_only=True,
    )
    tab_mgr.tabs.append(room_tab)
    room_tab_idx = len(tab_mgr.tabs) - 1
    for name in agent_names:
        if _agent_chat_buf(name) is None:
            _spawn_agent_bufs(app, name)
    # Restore: _spawn_agent_bufs overwrites active.
    tab_mgr.active = room_tab_idx
    app.invalidate()
    return room_buf


def _spawn_chain_bufs(app, agent_names):
    """Create Chain Room tab and agent bufs.

    Creates a read-only room buffer registered as
    'chain:room'. Adds a Chain Room tab. For each
    agent name without a buffer, calls
    _spawn_agent_bufs(). Restores focus to the
    room tab (C1). Returns the room Buffer.
    """
    from prompt_toolkit.buffer import Buffer
    room_buf = Buffer(
        name="chain_room",
        read_only=True,
    )
    buf_reg.register("chain:room", room_buf)
    room_tab = Tab(
        "Chain Room",
        room_buf,
        read_only=True,
    )
    tab_mgr.tabs.append(room_tab)
    room_tab_idx = len(tab_mgr.tabs) - 1
    for name in agent_names:
        if _agent_chat_buf(name) is None:
            _spawn_agent_bufs(app, name)
    # Restore: _spawn_agent_bufs overwrites active.
    tab_mgr.active = room_tab_idx
    app.invalidate()
    return room_buf
```

---

### 8d. Add two response handlers

**Where**: directly after `handle_debate_response`.

#### `handle_facilitator_response`

Streams the facilitator's response. Handles tokens
and tool_call/tool_result events for transparent
mode. Follows C2, C8, C9.

```python
async def handle_facilitator_response(
    app, user_text
):
    """Stream the facilitator response to room buf.

    Sends user_text to the facilitator via
    _facilitator.post() and routes each event:
    - token: accumulate (C2)
    - done: flush build_team_agent_frame (C2),
            record transcript
    - tool_call: if transparent and call_agent,
                 append dim delegation line
    - tool_result: if transparent,
                   append dim result line
    - error: append error line
    After all events: record user, append
    'Your turn' notif (C9).
    """
    global _facilitator, _facilitator_room_buf
    fac = _facilitator
    if fac is None or _facilitator_room_buf is None:
        return

    _append_facilitator_room(
        build_user_frame(user_text, _exec_mode)
    )
    app.invalidate()

    partial_text: dict[str, str] = {}
    fac_name = fac.facilitator_name
    color = _get_team_color(fac_name)
    last_agent_called = ""

    async for event in fac.post(user_text):
        if event.type == "token":
            partial_text[fac_name] = (
                partial_text.get(fac_name, "")
                + str(event.data)
            )
        elif event.type == "done":
            full = str(event.data) or (
                partial_text.get(fac_name, "")
            )
            frame = build_team_agent_frame(
                fac_name, full, color
            )
            _append_facilitator_room(frame)
            fac.record_response(full)
            partial_text.pop(fac_name, None)
            await asyncio.sleep(0)
            app.invalidate()
        elif event.type == "tool_call":
            if _facilitator_transparent:
                d = event.data or {}
                if d.get("name") == "call_agent":
                    tgt = (
                        d.get("args", {})
                        .get("name", "?")
                    )
                    last_agent_called = tgt
                    _append_facilitator_room(
                        f"{M_DIM}"
                        f" [→ {tgt}]"
                        f" delegating…"
                    )
                    app.invalidate()
        elif event.type == "tool_result":
            if _facilitator_transparent:
                d = event.data or {}
                raw = str(
                    d.get("result", "")
                )
                first = (
                    raw.split("\n")[0][:80]
                )
                lbl = (
                    last_agent_called
                    or "agent"
                )
                _append_facilitator_room(
                    f"{M_DIM}"
                    f" [← {lbl}]: {first}"
                )
                app.invalidate()
        elif event.type == "error":
            _append_facilitator_room(
                f"{M_EFRAME}"
                f" [facilitator error]:"
                f" {event.data}"
            )
            app.invalidate()

    fac.record_user(user_text)
    _append_facilitator_room(
        build_inline_notif("Your turn", "→")
    )
    app.invalidate()
```

#### `handle_chain_stage`

Runs one stage of the chain. Uses `session.chat()`
(NOT `chat_auto`) so chain stages stay clean.
Follows C2, C8. After the last stage, auto-fires
synthesis. Otherwise, either auto-continues or
shows a checkpoint menu.

```python
async def handle_chain_stage(
    app, stage_idx, input_text
):
    """Run one stage of the chain.

    Streams session.chat(input_text) for the agent
    at stage_idx. Records output. After done:
    - if checkpoint: show checkpoint menu
    - elif last stage: fire _offer_chain_synthesis
    - else: auto-continue to next stage

    Uses session.chat() (no tools) to keep stages
    clean. (C2, C8)
    """
    global _chain, _chain_room_buf
    global _chain_stage_idx, _chain_running
    global _chain_auto_closed
    ch = _chain
    if ch is None or _chain_room_buf is None:
        return

    total = ch.stage_count
    name = ch.get_name(stage_idx)
    session = ch.get_session(stage_idx)
    if name is None or session is None:
        return

    _chain_stage_idx = stage_idx
    _chain_running = True
    color = _get_team_color(name)

    sep = "─" * (frame_width() - 4)
    _append_chain_room(
        f"{M_DIM}"
        f" ╌{sep}╌\n"
        f"{M_DIM}"
        f" Stage {stage_idx + 1} of {total}:"
        f" {name}"
    )
    _append_chain_room(
        build_user_frame(input_text, _exec_mode)
    )
    app.invalidate()

    partial_text: dict[str, str] = {}

    async for event in session.chat(input_text):
        if event.type == "token":
            partial_text[name] = (
                partial_text.get(name, "")
                + str(event.data)
            )
        elif event.type == "done":
            full = str(event.data) or (
                partial_text.get(name, "")
            )
            frame = build_team_agent_frame(
                name, full, color
            )
            _append_chain_room(frame)
            ch.record_stage(name, full)
            partial_text.pop(name, None)
            _chain_running = False
            await asyncio.sleep(0)
            app.invalidate()

            is_last = (
                stage_idx == total - 1
            )
            if _chain_checkpoint:
                _show_chain_checkpoint_menu(
                    app,
                    stage_idx,
                    full,
                )
            elif is_last:
                _chain_auto_closed = True
                _offer_chain_synthesis(app)
            else:
                asyncio.ensure_future(
                    handle_chain_stage(
                        app,
                        stage_idx + 1,
                        full,
                    )
                )
            return
        elif event.type == "error":
            _chain_running = False
            _append_chain_room(
                f"{M_EFRAME}"
                f" [{name} error]:"
                f" {event.data}"
            )
            app.invalidate()
            return

    _chain_running = False
```

---

### 8e. Add the chain checkpoint menu

**Where**: directly after `handle_chain_stage`.

This menu appears after each chain stage when
`_chain_checkpoint` is True. At intermediate stages
it offers "Continue" to the next stage; at the last
stage it offers "Finish & synthesize".

```python
def _show_chain_checkpoint_menu(
    app, stage_idx, stage_output
):
    """Checkpoint menu after a chain stage completes.

    At intermediate stages (not the last):
        Continue → stage N+1
        Edit output
        Stop chain
    At the last stage:
        Finish & synthesize
        Edit output
        Stop chain
    Escape / cancel → Stop (run synthesis).
    """
    global _chain, _chain_room_buf
    if _chain is None or _chain_room_buf is None:
        return

    total = _chain.stage_count
    is_last = stage_idx == total - 1
    next_n = stage_idx + 2  # 1-based next stage

    if is_last:
        options = [
            "Finish & synthesize",
            "Edit output",
            "Stop chain",
        ]
    else:
        options = [
            f"Continue → stage {next_n}",
            "Edit output",
            "Stop chain",
        ]

    def on_select(idx):
        prev = debate_menu._prev_lines
        if prev > 0 and _chain_room_buf:
            _replace_buf_last(
                _chain_room_buf, prev, ""
            )
        if idx == 0:
            # Continue or Finish
            if is_last:
                global _chain_auto_closed
                _chain_auto_closed = True
                _offer_chain_synthesis(app)
            else:
                asyncio.ensure_future(
                    handle_chain_stage(
                        app,
                        stage_idx + 1,
                        stage_output,
                    )
                )
        elif idx == 1:
            # Edit output
            def on_edit(edited_text):
                use = (
                    edited_text.strip()
                    or stage_output
                )
                if is_last:
                    global _chain_auto_closed
                    _chain_auto_closed = True
                    _offer_chain_synthesis(app)
                else:
                    asyncio.ensure_future(
                        handle_chain_stage(
                            app,
                            stage_idx + 1,
                            use,
                        )
                    )
            _dlg.show_input_dialog(
                app,
                title=(
                    f"Edit stage"
                    f" {stage_idx + 1} output"
                ),
                label="Edit before passing on:",
                on_confirm=on_edit,
                refocus=input_area,
                initial_text=stage_output[:500],
            )
        else:
            # Stop chain → synthesis
            _run_chain_synthesis(app)

    def on_cancel():
        prev = debate_menu._prev_lines
        if prev > 0 and _chain_room_buf:
            _replace_buf_last(
                _chain_room_buf, prev, ""
            )
        _run_chain_synthesis(app)

    debate_menu.show(
        f"Stage {stage_idx + 1} complete",
        options,
        on_select,
        white=True,
        on_cancel=on_cancel,
    )
    menu_text = debate_menu.build_frame()
    debate_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    _append_chain_room(menu_text)
    app.invalidate()
```

---

### 8f. Add teardown functions

**Where**: directly after `_teardown_debate`.

```python
def _teardown_facilitator(app):
    """Clear all facilitator state, go to tab 0."""
    global _facilitator, _facilitator_room_buf
    global _facilitator_transparent
    global _team_agent_colors, _team_color_next
    _facilitator = None
    _facilitator_room_buf = None
    _facilitator_transparent = True
    _team_agent_colors.clear()
    _team_color_next = 0
    tab_mgr.goto_tab(0)
    app.invalidate()


def _teardown_chain(app):
    """Clear all chain state, go to tab 0."""
    global _chain, _chain_room_buf
    global _chain_checkpoint, _chain_stage_idx
    global _chain_running, _chain_auto_closed
    global _team_agent_colors, _team_color_next
    _chain = None
    _chain_room_buf = None
    _chain_checkpoint = False
    _chain_stage_idx = 0
    _chain_running = False
    _chain_auto_closed = False
    _team_agent_colors.clear()
    _team_color_next = 0
    tab_mgr.goto_tab(0)
    app.invalidate()
```

---

### 8g. Add follow-up menus

**Where**: directly after `_show_roundtable_follow_up`
(for facilitator) and again (for chain).

Both follow the exact same pattern as the existing
roundtable and debate follow-up menus. Use
`debate_menu` (shared instance) for all modes.

```python
def _show_facilitator_follow_up(app, questions):
    """Follow-up scroll menu in facilitator room.

    Options are the follow-up questions plus
    '── End session'. Selecting a question calls
    _continue_facilitator(); End session tears down.
    """
    global _facilitator_room_buf
    if _facilitator_room_buf is None:
        return

    options = (
        list(questions) + ["── End session"]
    )

    def on_select(idx):
        prev = debate_menu._prev_lines
        if prev > 0 and _facilitator_room_buf:
            _replace_buf_last(
                _facilitator_room_buf, prev, ""
            )
        if idx == len(options) - 1:
            _teardown_facilitator(app)
            return
        chosen_q = questions[idx]
        asyncio.ensure_future(
            _continue_facilitator(app, chosen_q)
        )

    def on_cancel():
        if _facilitator_room_buf:
            _append_facilitator_room(
                f"{M_DIM} Follow-up dismissed."
            )
        app.invalidate()

    debate_menu.show(
        "Follow-up questions",
        options,
        on_select,
        white=True,
        on_cancel=on_cancel,
    )
    menu_text = debate_menu.build_frame()
    debate_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    _append_facilitator_room(menu_text)
    app.invalidate()


def _show_chain_follow_up(app, questions):
    """Follow-up scroll menu in chain room.

    Options are the follow-up questions plus
    '── End session'. Selecting a question calls
    _continue_chain(); End session tears down.
    """
    global _chain_room_buf
    if _chain_room_buf is None:
        return

    options = (
        list(questions) + ["── End session"]
    )

    def on_select(idx):
        prev = debate_menu._prev_lines
        if prev > 0 and _chain_room_buf:
            _replace_buf_last(
                _chain_room_buf, prev, ""
            )
        if idx == len(options) - 1:
            _teardown_chain(app)
            return
        chosen_q = questions[idx]
        asyncio.ensure_future(
            _continue_chain(app, chosen_q)
        )

    def on_cancel():
        if _chain_room_buf:
            _append_chain_room(
                f"{M_DIM} Follow-up dismissed."
            )
        app.invalidate()

    debate_menu.show(
        "Follow-up questions",
        options,
        on_select,
        white=True,
        on_cancel=on_cancel,
    )
    menu_text = debate_menu.build_frame()
    debate_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    _append_chain_room(menu_text)
    app.invalidate()
```

---

### 8h. Add save menus

**Where**: directly after the follow-up menus you just
added.

Both follow the exact same pattern as
`_show_roundtable_save_menu` and
`_show_debate_save_menu`.

```python
def _show_facilitator_save_menu(app, fups, clean):
    """Level 1 post-synthesis save menu (facilitator).

    Options: Save & continue / Save & close.
    Escape skips saving and goes to Level 2.
    """
    global _facilitator_room_buf
    if _facilitator_room_buf is None:
        return

    options = ["Save & continue", "Save & close"]

    def _do_save():
        path = _save_synthesis_file(
            "facilitator", clean
        )
        if path:
            _append_facilitator_room(
                f"{M_DIM} Saved to {path}"
            )
            app.invalidate()

    def on_select(idx):
        prev = debate_menu._prev_lines
        if prev > 0 and _facilitator_room_buf:
            _replace_buf_last(
                _facilitator_room_buf, prev, ""
            )
        _do_save()
        if idx == 1:
            _teardown_facilitator(app)
        else:
            if fups:
                _show_facilitator_follow_up(
                    app, fups
                )
            else:
                _teardown_facilitator(app)

    def on_cancel():
        prev = debate_menu._prev_lines
        if prev > 0 and _facilitator_room_buf:
            _replace_buf_last(
                _facilitator_room_buf, prev, ""
            )
        if fups:
            _show_facilitator_follow_up(app, fups)
        else:
            _teardown_facilitator(app)

    debate_menu.show(
        "Save synthesis",
        options,
        on_select,
        white=True,
        on_cancel=on_cancel,
    )
    menu_text = debate_menu.build_frame()
    debate_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    _append_facilitator_room(menu_text)
    app.invalidate()


def _show_chain_save_menu(app, fups, clean):
    """Level 1 post-synthesis save menu (chain).

    Options: Save & continue / Save & close.
    Escape skips saving and goes to Level 2.
    """
    global _chain_room_buf
    if _chain_room_buf is None:
        return

    options = ["Save & continue", "Save & close"]

    def _do_save():
        path = _save_synthesis_file(
            "chain", clean
        )
        if path:
            _append_chain_room(
                f"{M_DIM} Saved to {path}"
            )
            app.invalidate()

    def on_select(idx):
        prev = debate_menu._prev_lines
        if prev > 0 and _chain_room_buf:
            _replace_buf_last(
                _chain_room_buf, prev, ""
            )
        _do_save()
        if idx == 1:
            _teardown_chain(app)
        else:
            if fups:
                _show_chain_follow_up(app, fups)
            else:
                _teardown_chain(app)

    def on_cancel():
        prev = debate_menu._prev_lines
        if prev > 0 and _chain_room_buf:
            _replace_buf_last(
                _chain_room_buf, prev, ""
            )
        if fups:
            _show_chain_follow_up(app, fups)
        else:
            _teardown_chain(app)

    debate_menu.show(
        "Save synthesis",
        options,
        on_select,
        white=True,
        on_cancel=on_cancel,
    )
    menu_text = debate_menu.build_frame()
    debate_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    _append_chain_room(menu_text)
    app.invalidate()
```

---

### 8i. Add continue functions

**Where**: directly after `_continue_roundtable`.

These reset agent histories and re-run the mode
with a new question (follow-up flow). They follow
the exact same pattern as `_continue_roundtable`
and `_continue_debate`.

```python
async def _continue_facilitator(app, new_question):
    """Reset histories and continue facilitator session.

    1. Ask facilitator for a 2-3 sentence summary.
    2. Clear facilitator + all specialist sessions.
    3. Re-inject the summary into the facilitator.
    4. Re-seed facilitator with its role context.
    5. Show a separator line.
    6. Post the new question.
    """
    global _facilitator, _facilitator_room_buf
    if _facilitator is None or _da_pool is None:
        return

    _append_facilitator_room(
        f"{M_DIM} Gathering session summary…"
    )
    app.invalidate()

    summaries = (
        await _facilitator.summarize_positions()
    )

    # Clear facilitator session history.
    fac_sid = (
        f"agent-{_facilitator.facilitator_name}"
    )
    fac_session = _da_pool.get(fac_sid)
    fac_session.clear_history()
    summ = summaries.get(
        _facilitator.facilitator_name, ""
    )
    if summ:
        fac_session.inject_system_message(
            f"[Prior session summary]: {summ}"
        )

    # Clear specialist sessions.
    for spec_name in _facilitator.specialist_names:
        spec_sid = f"agent-{spec_name}"
        try:
            spec_session = _da_pool.get(spec_sid)
            spec_session.clear_history()
        except KeyError:
            pass

    # Re-seed facilitator with coordination context.
    spec_list = ", ".join(
        _facilitator.specialist_names
    )
    fac_session.inject_system_message(
        "You are a facilitator coordinating"
        " a team of specialist agents."
        f" Available specialists: {spec_list}."
        " Use the call_agent tool to delegate"
        " subtasks. Synthesize replies for"
        " the user."
    )

    sep = "─" * (frame_width() - 4)
    _append_facilitator_room(
        f"{M_NFRAME} ╌{sep}╌\n"
        f"{M_DIM} ↻ Continuing: {new_question}"
    )
    app.invalidate()
    asyncio.ensure_future(
        handle_facilitator_response(
            app, new_question
        )
    )


async def _continue_chain(app, new_task):
    """Reset histories and re-run the chain.

    1. Ask each agent for a 2-3 sentence summary.
    2. Clear each agent's history, re-inject summary.
    3. Create a fresh Chain with the same agents.
    4. Reset chain globals.
    5. Show a separator line.
    6. Start the chain from stage 0 with new_task.
    """
    global _chain, _chain_room_buf
    global _chain_stage_idx, _chain_running
    global _chain_auto_closed
    if _chain is None or _da_pool is None:
        return

    _append_chain_room(
        f"{M_DIM} Gathering stage summaries…"
    )
    app.invalidate()

    summaries = await _chain.summarize_positions()

    for name, sid in _chain.agents:
        session = _da_pool.get(sid)
        session.clear_history()
        summ = summaries.get(name, "")
        if summ:
            session.inject_system_message(
                f"[Your prior contribution]:"
                f" {summ}"
            )

    # Fresh chain with same agents, cleared state.
    _chain = _da_pool.chain(_chain.agents)
    _chain_stage_idx = 0
    _chain_running = False
    _chain_auto_closed = False

    sep = "─" * (frame_width() - 4)
    _append_chain_room(
        f"{M_NFRAME} ╌{sep}╌\n"
        f"{M_DIM} ↻ Continuing: {new_task}"
    )
    app.invalidate()
    asyncio.ensure_future(
        handle_chain_stage(app, 0, new_task)
    )
```

---

### 8j. Add synthesis functions

**Where**: directly after `_run_roundtable_synthesis`.

```python
def _run_facilitator_synthesis(app):
    """Run synthesis when facilitator session closes.

    Runs a throwaway subtask to summarize the session.
    Shows synthesis in a white frame and shows the
    save menu. Teardown is deferred. (C4, C5)
    """
    global _facilitator
    if _facilitator is None or _da_pool is None:
        _teardown_facilitator(app)
        return

    transcript_text = _facilitator.format_context(
        limit=200
    )

    async def _do_synthesis():
        prompt = (
            "Summarize the following facilitated"
            " session and identify the main"
            " outcomes and decisions.\n"
            "After the summary, on its own"
            " line append exactly:\n"
            '{"follow_ups": ["<q1>",'
            ' "<q2>", "<q3>"]}\n'
            "where q1-q3 are insightful"
            " follow-up questions.\n\n"
            f"{transcript_text}"
        )
        summary = await _da_pool.run_subtask(
            prompt, mode="plan"
        )
        clean, fups = _extract_follow_ups(summary)
        _append_facilitator_room(
            build_synthesis_frame(clean)
        )
        app.invalidate()
        _show_facilitator_save_menu(
            app, fups, clean
        )

    asyncio.ensure_future(_do_synthesis())


def _offer_chain_synthesis(app):
    """Auto-run synthesis when chain ends naturally.

    Called automatically after the last stage
    completes (no checkpoint) or after the last
    stage's checkpoint menu chooses Finish.
    Also called by _run_chain_synthesis (C4).
    """
    global _chain
    if _chain is None or _da_pool is None:
        _teardown_chain(app)
        return

    transcript_text = _chain.format_context(
        limit=200
    )

    async def _do_synthesis():
        prompt = (
            "Summarize the following pipeline"
            " output and identify the main"
            " themes and results.\n"
            "After the summary, on its own"
            " line append exactly:\n"
            '{"follow_ups": ["<q1>",'
            ' "<q2>", "<q3>"]}\n'
            "where q1-q3 are insightful"
            " follow-up questions.\n\n"
            f"{transcript_text}"
        )
        summary = await _da_pool.run_subtask(
            prompt, mode="plan"
        )
        clean, fups = _extract_follow_ups(summary)
        _append_chain_room(
            build_synthesis_frame(clean)
        )
        app.invalidate()
        _show_chain_save_menu(app, fups, clean)

    asyncio.ensure_future(_do_synthesis())


def _run_chain_synthesis(app):
    """Run synthesis when /close is typed.

    Delegates to _offer_chain_synthesis. Use this
    function from the routing block so both the
    /close path and the Stop checkpoint path share
    the same logic.
    """
    _offer_chain_synthesis(app)
```

---

### 8k. Update `_redraw_debate_menu`

**Where**: find the existing `_redraw_debate_menu`
function. It currently reads:

```python
    buf = _debate_room_buf or _rt_room_buf
```

Replace that single line with:

```python
    buf = (
        _debate_room_buf
        or _rt_room_buf
        or _facilitator_room_buf
        or _chain_room_buf
    )
```

This ensures the shared `debate_menu` widget can
redraw itself in any team chat room buffer.

---

### 8l. Add do-start coroutines

**Where**: directly after `_do_start_debate`.

```python
async def _do_start_facilitator(
    app, fac_name, specialist_names, transparent
):
    """Spawn agents and open the Facilitator Room tab.

    Spawns the facilitator first (execution mode is
    hardcoded in ActiveRegistry.spawn_agent), then
    all specialists. Creates the Facilitator instance
    via pool.facilitator(), opens the room buffer,
    and prints welcome lines (C10).

    Args:
        app: The prompt_toolkit Application.
        fac_name: Name of the facilitator agent.
        specialist_names: list[str] specialist names.
        transparent: bool — show tool call traffic.
    """
    global _facilitator, _facilitator_room_buf
    global _facilitator_transparent
    global _active_registry
    if _active_registry is None:
        from starry_lib.agents.active_registry\
            import ActiveRegistry
        _active_registry = ActiveRegistry()
        _init_agent_tools()

    all_names = [fac_name] + specialist_names
    for name in all_names:
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

    _facilitator = _da_pool.facilitator(
        fac_name,
        f"agent-{fac_name}",
        specialist_names,
    )
    _facilitator_transparent = transparent

    # Seed facilitator with its coordination role.
    fac_session = _da_pool.get(
        f"agent-{fac_name}"
    )
    spec_list = ", ".join(specialist_names)
    fac_session.inject_system_message(
        "You are a facilitator coordinating"
        " a team of specialist agents."
        f" Available specialists: {spec_list}."
        " Use the call_agent tool to delegate"
        " subtasks to them. Synthesize their"
        " responses into a unified reply for"
        " the user."
    )

    _facilitator_room_buf = _spawn_facilitator_bufs(
        app, all_names
    )
    t_mode = "on" if transparent else "off"
    joined_specs = ", ".join(specialist_names)
    for _ln in [
        f"Facilitator started —"
        f" coordinator: {fac_name}",
        f"Specialists: {joined_specs}",
        f"Transparent mode: {t_mode}",
        "Type a message to the facilitator.",
        "/close — finish & synthesize"
        " | /exit — quit",
    ]:
        _append_facilitator_room(f"{M_DIM} {_ln}")
    app.invalidate()


async def _do_start_chain(
    app, names, initial_task, checkpoint
):
    """Spawn named agents and open the Chain Room tab.

    Spawns each agent, creates the Chain instance via
    pool.chain(), opens the room buffer, prints
    welcome lines (C10), and fires the first stage.

    Args:
        app: The prompt_toolkit Application.
        names: list[str] of agent names in order.
              The chain runs agents in THIS order.
        initial_task: str — input for stage 0.
        checkpoint: bool — pause after each stage.
    """
    global _chain, _chain_room_buf
    global _chain_checkpoint, _chain_stage_idx
    global _chain_running, _chain_auto_closed
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
    _chain = _da_pool.chain(agents)
    _chain_checkpoint = checkpoint
    _chain_stage_idx = 0
    _chain_running = False
    _chain_auto_closed = False

    _chain_room_buf = _spawn_chain_bufs(app, names)
    joined = ", ".join(names)
    cp_hint = "on" if checkpoint else "off"
    for _ln in [
        f"Chain started — stages: {joined}",
        f"Checkpoint mode: {cp_hint}",
        f"Initial task: {initial_task}",
        "/close — finish & synthesize"
        " | /exit — quit",
    ]:
        _append_chain_room(f"{M_DIM} {_ln}")
    app.invalidate()
    asyncio.ensure_future(
        handle_chain_stage(app, 0, initial_task)
    )
```

---

### 8m. Add routing blocks in `accept_handler`

**Where**: in the `accept_handler` function, add
both blocks **after** the Debate routing block and
**before** the "Agent session routing" block.

The Debate routing block ends with `return` after
injecting a message. Add the two new blocks right
after that closing `return`.

#### Facilitator routing block

```python
        # ── Facilitator routing ───────────────────
        global _facilitator, _facilitator_room_buf
        if _facilitator is not None:
            tl = text.lower()
            if tl == "/close":
                _run_facilitator_synthesis(app)
                return
            if tl == "/exit":
                _teardown_facilitator(app)
                async def _fexit():
                    await asyncio.sleep(0.3)
                    app.exit()
                asyncio.ensure_future(_fexit())
                return
            if text:
                asyncio.ensure_future(
                    handle_facilitator_response(
                        app, text
                    )
                )
            return
```

#### Chain routing block

```python
        # ── Chain routing ─────────────────────────
        global _chain, _chain_room_buf
        global _chain_running
        if _chain is not None:
            tl = text.lower()
            if tl == "/close":
                if _chain_auto_closed:
                    _teardown_chain(app)
                else:
                    _run_chain_synthesis(app)
                return
            if tl == "/exit":
                _teardown_chain(app)
                async def _cexit():
                    await asyncio.sleep(0.3)
                    app.exit()
                asyncio.ensure_future(_cexit())
                return
            if _chain_running:
                _append_chain_room(
                    f"{M_DIM} Chain in progress…"
                )
                app.invalidate()
            elif text:
                _chain_auto_closed = False
                asyncio.ensure_future(
                    handle_chain_stage(
                        app, 0, text
                    )
                )
            return
```

**Note on `_chain_auto_closed`**: this flag is set to
`True` when the chain completes naturally (last stage
done) and synthesis is auto-fired. When the user then
types `/close`, it means the synthesis has already
been shown, so teardown runs directly. If
`_chain_auto_closed` is False, synthesis has not run
yet, so `/close` runs it.

---

### 8n. Update the `/team` menu

**Where**: find the `/team` command handler in
`accept_handler`. It currently shows four options and
handles only idx==0 (Roundtable) and idx==2 (Debate).
Options B and D fall into an `else` branch that
prints "Not yet implemented."

**Step 1**: Update `_TEAM_OPTIONS` to remove "(soon)":

```python
            _TEAM_OPTIONS = [
                "A. Roundtable",
                "B. Facilitator",
                "C. Structured Debate",
                "D. Collaborative Chain",
            ]
```

**Step 2**: The `_on_team_select` function currently
has:
```python
                elif idx == 2:
                    # Debate code ...
                else:
                    append_text(build_warn_frame(
                        "Not yet implemented."))
                    app.invalidate()
```

Replace the entire `else` block with handlers for
`elif idx == 1` (Facilitator) and
`elif idx == 3` (Chain). Keep the Roundtable (idx==0)
and Debate (idx==2) code unchanged.

#### Handler for idx == 1 (Facilitator)

Dialog flow:
1. Check at least 2 agents exist.
2. Menu dialog to select the facilitator (1 agent).
3. Toggle dialog to select specialists (1+ agents,
   excluding the chosen facilitator).
4. Button dialog: Transparent mode? Yes / No.
5. Call `_do_start_facilitator`.

```python
                elif idx == 1:
                    # ── Facilitator ────────────────
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
                                "Need at least"
                                " 2 agents."
                                " Use /agent →"
                                " Create first."
                            )
                        )
                        app.invalidate()
                        return
                    all_names = [
                        cfg.name
                        for cfg in agent_cfgs
                    ]

                    def _on_fac_pick(fac_idx):
                        fac_name = (
                            all_names[fac_idx]
                        )
                        remaining = [
                            n for i, n
                            in enumerate(all_names)
                            if i != fac_idx
                        ]

                        def _on_specs(indices):
                            if not indices:
                                append_text(
                                    build_warn_frame(
                                        "Select at"
                                        " least 1"
                                        " specialist."
                                    )
                                )
                                app.invalidate()
                                return
                            specs = [
                                remaining[i]
                                for i in indices
                            ]

                            def _on_transparent(
                                bidx
                            ):
                                transparent = (
                                    bidx == 0
                                )
                                asyncio\
                                    .ensure_future(
                                    _do_start_facilitator(
                                        app,
                                        fac_name,
                                        specs,
                                        transparent,
                                    )
                                )

                            _dlg.show_button_dialog(
                                app,
                                title=(
                                    "Facilitator"
                                    " — Transparent"
                                    " mode?"
                                ),
                                message=(
                                    "Show tool"
                                    " call traffic"
                                    " in room?"
                                ),
                                buttons=[
                                    "Yes",
                                    "No",
                                ],
                                on_button=(
                                    _on_transparent
                                ),
                                refocus=input_area,
                            )

                        _dlg.show_toggle_dialog(
                            app,
                            title=(
                                "Facilitator"
                                " — Select"
                                " Specialists"
                            ),
                            items=remaining,
                            on_confirm=_on_specs,
                            refocus=input_area,
                            max_visible=8,
                        )

                    _dlg.show_menu_dialog(
                        app,
                        title=(
                            "Facilitator"
                            " — Select Facilitator"
                        ),
                        options=all_names,
                        on_select=_on_fac_pick,
                        refocus=input_area,
                    )
```

#### Handler for idx == 3 (Chain)

Dialog flow:
1. Check at least 2 agents exist.
2. Toggle dialog: select 2+ agents.
   **Note in dialog title**: "Chain order = agent
   list order". The order of the selected agents in
   the pipeline equals the order they appear in the
   stored agents list, not the check order.
3. Input dialog: enter initial task.
4. Button dialog: Checkpoint between stages? Yes / No.
5. Call `_do_start_chain`.

```python
                elif idx == 3:
                    # ── Collaborative Chain ────────
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
                                "Need at least"
                                " 2 agents."
                                " Use /agent →"
                                " Create first."
                            )
                        )
                        app.invalidate()
                        return
                    chain_names = [
                        cfg.name
                        for cfg in agent_cfgs
                    ]

                    def _on_chain_agents(indices):
                        if len(indices) < 2:
                            append_text(
                                build_warn_frame(
                                    "Select at least"
                                    " 2 agents."
                                )
                            )
                            app.invalidate()
                            return
                        chosen = [
                            chain_names[i]
                            for i in indices
                        ]

                        def _on_task(task_text):
                            if not task_text\
                                    .strip():
                                append_text(
                                    build_warn_frame(
                                        "Task cannot"
                                        " be empty."
                                    )
                                )
                                app.invalidate()
                                return

                            def _on_checkpoint(
                                bidx
                            ):
                                checkpoint = (
                                    bidx == 0
                                )
                                asyncio\
                                    .ensure_future(
                                    _do_start_chain(
                                        app,
                                        chosen,
                                        task_text
                                        .strip(),
                                        checkpoint,
                                    )
                                )

                            _dlg.show_button_dialog(
                                app,
                                title=(
                                    "Chain"
                                    " — Checkpoint"
                                    " mode?"
                                ),
                                message=(
                                    "Pause after"
                                    " each stage?"
                                ),
                                buttons=[
                                    "Yes",
                                    "No",
                                ],
                                on_button=(
                                    _on_checkpoint
                                ),
                                refocus=input_area,
                            )

                        _dlg.show_input_dialog(
                            app,
                            title=(
                                "Chain"
                                " — Initial Task"
                            ),
                            label=(
                                "Enter the task"
                                " for the chain:"
                            ),
                            on_confirm=_on_task,
                            refocus=input_area,
                        )

                    _dlg.show_toggle_dialog(
                        app,
                        title=(
                            "Chain — Select Agents"
                            "\n(order = list order)"
                        ),
                        items=chain_names,
                        on_confirm=_on_chain_agents,
                        refocus=input_area,
                        max_visible=8,
                    )
```

---

## 9. Optional: update the bot-bar indicator

The bot-bar currently shows `ROUNDTABLE(n)` when
roundtable is active. You can add similar indicators
for facilitator and chain. Find the bot-bar section
near the `_roundtable is not None` check (around
line 1725).

Add `elif` branches after the existing roundtable
check:

```python
    elif _facilitator is not None:
        parts.append((
            "class:bot-bar.label", "room "
        ))
        parts.append((
            "class:bot-bar.roundtable",
            "FACILITATOR",
        ))
    elif _chain is not None:
        parts.append((
            "class:bot-bar.label", "room "
        ))
        parts.append((
            "class:bot-bar.roundtable",
            f"CHAIN({_chain_stage_idx + 1}"
            f"/{_chain.stage_count})",
        ))
```

This reuses the existing `"bot-bar.roundtable"` CSS
class (bold accent color) without needing new style
entries.

---

## 10. Final checklist

After completing all steps, verify each point:

### Facilitator

- [ ] `facilitator.py` created with correct header
- [ ] `Facilitator.post()` uses `chat_auto()` (NOT `chat()`)
- [ ] `pool.facilitator()` factory method added and imports `Facilitator`
- [ ] Globals `_facilitator`, `_facilitator_room_buf`, `_facilitator_transparent` added
- [ ] `_append_facilitator_room` defined
- [ ] `_spawn_facilitator_bufs` follows C1 exactly
- [ ] `handle_facilitator_response` follows C2 (accumulate, flush on done) and C8 (user frame) and C9 (Your turn)
- [ ] Transparent mode: dim `[→ name] delegating…` and `[← name]: first_line`
- [ ] `_teardown_facilitator` clears ALL globals including `_team_agent_colors` (C7)
- [ ] `_run_facilitator_synthesis` uses `_da_pool.run_subtask(prompt, mode="plan")` (C5)
- [ ] `_show_facilitator_save_menu` Level 1 (C6)
- [ ] `_show_facilitator_follow_up` Level 2 (C6)
- [ ] `_continue_facilitator` clears ALL sessions (facilitator + specialists)
- [ ] `_do_start_facilitator` welcome lines end with `/close — finish & synthesize | /exit — quit` (C10)
- [ ] Routing block: `/close` → synthesis, `/exit` → teardown + app.exit() (C3, C4)
- [ ] `/team` menu idx==1 handler wired up
- [ ] `_redraw_debate_menu` updated to include `_facilitator_room_buf`

### Chain

- [ ] `chain.py` created with correct header
- [ ] `Chain.get_session()` and `Chain.record_stage()` implemented
- [ ] `pool.chain()` factory method added and imports `Chain`
- [ ] Globals `_chain`, `_chain_room_buf`, `_chain_checkpoint`, `_chain_stage_idx`, `_chain_running`, `_chain_auto_closed` added
- [ ] `_append_chain_room` defined
- [ ] `_spawn_chain_bufs` follows C1 exactly
- [ ] `handle_chain_stage` uses `session.chat()` (NOT `chat_auto()`)
- [ ] `handle_chain_stage` follows C2 (accumulate, flush on done) and C8 (user frame via `build_user_frame`)
- [ ] `handle_chain_stage` shows stage separator line before each stage
- [ ] After last stage without checkpoint: auto-fires `_offer_chain_synthesis` and sets `_chain_auto_closed = True`
- [ ] `_show_chain_checkpoint_menu` defined; last stage shows "Finish & synthesize"; intermediate shows "Continue → stage N"
- [ ] `_teardown_chain` clears ALL globals including `_team_agent_colors` (C7)
- [ ] `_offer_chain_synthesis` and `_run_chain_synthesis` both exist; `_run_chain_synthesis` delegates to `_offer_chain_synthesis`
- [ ] `_show_chain_save_menu` Level 1 (C6)
- [ ] `_show_chain_follow_up` Level 2 (C6)
- [ ] `_continue_chain` creates a fresh `Chain` instance (same agents) and resets `_chain_auto_closed = False`
- [ ] `_do_start_chain` welcome lines end with `/close — finish & synthesize | /exit — quit` (C10)
- [ ] Routing block: `/close` with `_chain_auto_closed` check, `/exit` teardown + app.exit(), running guard (C3, C4)
- [ ] `/team` menu idx==3 handler wired up
- [ ] `_redraw_debate_menu` updated to include `_chain_room_buf`

### Common

- [ ] All Python lines ≤ 79 characters (ruff enforces this)
- [ ] No line uses `await` inside `accept_handler` — use `asyncio.ensure_future()` only
- [ ] All file headers match the project format (see `debate.py` lines 1–17 for reference)
- [ ] `ruff check .` passes with no errors after all changes

---

## 11. Frequently anticipated questions

**Q: What is `debate_menu`?**
A: It is a shared `SelectionMenu()` instance defined
near line 1525 in `main.py`. ALL team chat modes reuse
the same object for their menus. Never create a new
one.

**Q: What does `_replace_buf_last(buf, n, text)`
do?**
A: It replaces the last `n` lines of the buffer with
`text`. Used to clear a menu frame from the buffer
before showing the next one.

**Q: Why use `session.chat()` for chain stages
instead of `session.chat_auto()`?**
A: Chain stages should stay clean with no tool calls.
`chat()` is a plain streaming call; `chat_auto()` adds
tool-call loops. The facilitator uses `chat_auto()`
because it needs the `call_agent` tool.

**Q: Why does `ActiveRegistry.spawn_agent` not take a
`mode` parameter?**
A: Looking at the source (`active_registry.py` line
113), `spawn_agent` hardcodes `mode="execution"` when
calling `pool.spawn()`. All named agents always run in
execution mode. The facilitator therefore already has
access to `call_agent`. For chain, we call
`session.chat()` explicitly, so execution mode on the
session does not affect chain stage behavior.

**Q: Where exactly does `_chain_auto_closed` get set
to True?**
A: In exactly two places:
1. In `handle_chain_stage`, after the last stage's
   `done` event, before calling
   `_offer_chain_synthesis(app)`.
2. In `_show_chain_checkpoint_menu`, inside
   `on_select(idx)` when `idx == 0` and `is_last`.
Never set it anywhere else.

**Q: What is the `global` keyword used for?**
A: Python requires `global <name>` at the top of any
function that _assigns_ to a module-level variable.
Reading a module-level variable does not need
`global`. All functions that set `_facilitator`,
`_chain`, etc. must declare them with `global` first.

**Q: Can I use `await` inside `accept_handler`?**
A: No. `accept_handler` is a synchronous function.
Always wrap coroutines with
`asyncio.ensure_future(coro())` to schedule them.

**Q: Do I need to add `_facilitator` and `_chain` to
`_BUILTIN_NAMES` in `store.py`?**
A: No. `_BUILTIN_NAMES` prevents users from naming
custom commands the same as built-in TUI commands
(like `/team`). The new modes are not TUI commands
themselves; they are activated through the `/team`
menu.
