# Roundtable Implementation Plan (v2)

## What this plan does

Adds a `/team` command to the StarryCLI TUI.
When activated, a menu lists all team modes (A–D).
Selecting **Roundtable** opens an agent-picker toggle
dialog; confirming with ≥ 2 agents opens a shared
"Room" buffer where the user and the selected agents
converse together.
Each agent's response is shown in the room buffer.
The user can address all agents at once or target one
specific agent with `@agentname message`.
Typing `/close` exits the roundtable (consistent with
how `/close` exits an agent chat session).
The bottom status bar shows `ROUNDTABLE(N)` while the
room is active.

---

## Rules you MUST follow

- Every line you write must be 79 characters or shorter.
- Do not rename any existing function or variable.
- Do not delete any existing code unless this plan
  tells you to.
- Apply changes in the exact order listed below.
- If a code block says "insert after LINE X", place
  the new code immediately after that line, with one
  blank line separating them.

---

## Files involved

| Action | File |
|--------|------|
| CREATE | `starry_lib/agents/roundtable.py` |
| MODIFY | `starry_cli/main.py` |
| MODIFY | `starry_lib/commands/store.py` |

---

## STEP 1 — Create `starry_lib/agents/roundtable.py`

Create the file with this exact content:

```python
#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       roundtable.py
# DESCRIPTION: Roundtable — shared multi-agent chat room
# SUMMARY: Maintains a shared transcript across agents
#          and broadcasts user messages to all of them.
# NOTES: Agents use session.chat() (no tools) so that
#        conversation stays clean and focused.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# MM/DD/YYYY    bsdero          Initial implementation
"""Roundtable: shared transcript + broadcast."""

from __future__ import annotations

from collections.abc import AsyncIterator

from starry_lib.types import AgentEvent


class Roundtable:
    """Shared chat room for user + multiple agents.

    Usage::

        rt = Roundtable(pool, {"alpha": "agent-alpha",
                               "beta":  "agent-beta"})
        async for event in rt.post("Hello everyone!"):
            print(event.type, event.data)
    """

    def __init__(
        self,
        pool: object,
        session_map: dict[str, str],
    ) -> None:
        """
        Args:
            pool: An AgentPool instance.
            session_map: Mapping of agent name to
                session_id.  Example:
                {"alpha": "agent-alpha"}.
        """
        self._pool = pool
        self._session_map: dict[str, str] = (
            dict(session_map)
        )
        self._sid_to_name: dict[str, str] = {
            sid: name
            for name, sid in session_map.items()
        }
        self._transcript: list[dict[str, str]] = []

    # ── Public properties ─────────────────────────

    @property
    def agent_names(self) -> list[str]:
        """Return names of all agents in the room."""
        return list(self._session_map.keys())

    @property
    def session_ids(self) -> list[str]:
        """Return session_ids of all agents."""
        return list(self._session_map.values())

    @property
    def transcript(self) -> list[dict[str, str]]:
        """Return the full shared transcript."""
        return self._transcript

    # ── Transcript helpers ────────────────────────

    def get_name_for_sid(
        self, sid: str
    ) -> str | None:
        """Return agent name for a session_id."""
        return self._sid_to_name.get(sid)

    def record_user(self, text: str) -> None:
        """Append a user turn to the transcript."""
        self._transcript.append(
            {"name": "You", "text": text}
        )

    def record_response(
        self, name: str, text: str
    ) -> None:
        """Append an agent response to transcript."""
        self._transcript.append(
            {"name": name, "text": text}
        )

    def format_context(
        self, limit: int = 10
    ) -> str:
        """Format the last `limit` transcript entries.

        Returns a string like:
            [You]: Hello
            [alpha]: Hi there!
        Returns an empty string if the transcript
        is empty.
        """
        recent = self._transcript[-limit:]
        if not recent:
            return ""
        return "\n".join(
            f"[{e['name']}]: {e['text']}"
            for e in recent
        )

    # ── Core broadcast ────────────────────────────

    async def post(
        self,
        user_text: str,
        target_name: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Broadcast user_text to agents or one target.

        Prepends conversation context to the prompt
        so agents can see what was said before.

        Args:
            user_text: The message to send.
            target_name: If given, send only to this
                agent. Otherwise send to all agents.

        Yields:
            AgentEvent objects with type "token",
            "done", or "error". Each event carries
            session_id so you can identify the agent.
        """
        ctx = self.format_context()
        if ctx:
            prompt = (
                "[Conversation context]\n"
                f"{ctx}\n\n{user_text}"
            )
        else:
            prompt = user_text

        if target_name is not None:
            sid = self._session_map.get(
                target_name
            )
            if sid is None:
                return
            session = self._pool.get(sid)
            async for event in session.chat(prompt):
                yield event
        else:
            async for event in (
                self._pool.broadcast(
                    prompt,
                    list(
                        self._session_map.values()
                    ),
                )
            ):
                yield event
```

---

## STEP 2 — Add two globals to `starry_cli/main.py`

Find this exact block in `main.py` (around line 990):

```
_session_stack: list = []      # agent routing stack
_active_registry = None        # ActiveRegistry
```

Replace it with:

```
_session_stack: list = []      # agent routing stack
_active_registry = None        # ActiveRegistry
_roundtable = None             # Roundtable | None
_rt_room_buf = None            # room Buffer | None
```

---

## STEP 3 — Add `_append_room()` to `starry_cli/main.py`

Find this exact block (around line 2707):

```
def append_tool_output(text):
    """Append plain text to Tool Output tab."""
    _buf_append(tool_output_buffer, text)
    for _t in tab_mgr.tabs:
        if _t.buffer is tool_output_buffer:
            _t.scroll_pos = 0
```

Insert this new function immediately after it (one
blank line gap):

```
def _append_room(text):
    """Append plain text to the room buffer.

    Does nothing if the room buffer does not exist.
    """
    if _rt_room_buf is not None:
        _buf_append(_rt_room_buf, text)
```

---

## STEP 4 — Add `_spawn_roundtable_bufs()` to `starry_cli/main.py`

Find this exact block (around line 3071):

```
def _close_agent_bufs(name):
    """Remove agent buffers from registry + tabs."""
    buf_reg._entries.pop(
        f"agent:{name}:chat", None
    )
    buf_reg._entries.pop(
        f"agent:{name}:log", None
    )
    tab_mgr.close_tab_by_name(
        f"Agent:{name}"
    )
    tab_mgr.close_tab_by_name(
        f"Agent:{name}:log"
    )
```

Insert this new function immediately after the whole
`_close_agent_bufs` block (one blank line gap):

```
def _spawn_roundtable_bufs(app, agent_names):
    """Create Room tab and per-agent buffers.

    Creates a read-only Room buffer registered as
    'roundtable:room' and adds a Room tab.
    For each agent name that has no buffer yet,
    calls _spawn_agent_bufs() to create one.
    Switches the active tab to the Room tab.
    Returns the room Buffer object.
    """
    from prompt_toolkit.buffer import Buffer
    room_buf = Buffer(
        name="roundtable_room",
        read_only=True,
    )
    buf_reg.register("roundtable:room", room_buf)
    room_tab = Tab(
        "Room", room_buf, read_only=True
    )
    tab_mgr.tabs.append(room_tab)
    tab_mgr.active = len(tab_mgr.tabs) - 1
    for name in agent_names:
        if _agent_chat_buf(name) is None:
            _spawn_agent_bufs(app, name)
    app.invalidate()
    return room_buf
```

---

## STEP 5 — Add `handle_roundtable_response()` to `starry_cli/main.py`

Find the end of the `handle_agent_response` function.
It ends with this block (around line 3240):

```
    except Exception as exc:
        _abuf(build_error_frame(str(exc)))
    finally:
        if not stop_spinner.is_set():
            stop_spinner.set()
            try:
                await spin_task
            except Exception:
                pass
        telemetry.ai_status = "idle"
        app.invalidate()
```

Insert this new function immediately after that
`finally` block closes (one blank line gap):

```
async def handle_roundtable_response(
    app, user_text, target=None
):
    """Stream responses from all roundtable agents.

    Calls _roundtable.post() and routes each event:
    - "token" events are accumulated per agent.
    - "done" events write the full response to the
      room buffer and record it in the transcript.
    - "error" events write an error line to the room.
    Records the user message to the transcript AFTER
    all agents have responded, so format_context()
    inside post() sees only the prior history.
    """
    global _roundtable, _rt_room_buf
    if _roundtable is None or _rt_room_buf is None:
        return

    _append_room(f"\n[You]: {user_text}\n")
    app.invalidate()

    accumulated: dict[str, str] = {}

    async for event in _roundtable.post(
        user_text, target
    ):
        name = _roundtable.get_name_for_sid(
            event.session_id
        )
        if name is None:
            continue
        if event.type == "token":
            accumulated[name] = (
                accumulated.get(name, "")
                + str(event.data)
            )
        elif event.type == "done":
            full = str(event.data) or (
                accumulated.get(name, "")
            )
            accumulated[name] = full
            _append_room(
                f"[{name}]: {full}\n"
            )
            _roundtable.record_response(
                name, full
            )
            app.invalidate()
        elif event.type == "error":
            _append_room(
                f"[{name} error]: {event.data}\n"
            )
            app.invalidate()

    _roundtable.record_user(user_text)
    app.invalidate()
```

---

## STEP 6 — Add `_do_start_roundtable()` to `starry_cli/main.py`

Find this exact block (around line 9451):

```
async def _spawn_and_enter(app, name, owned):
    """Spawn agent, create buffers, push stack."""
```

Insert this new async function immediately BEFORE
`_spawn_and_enter` (one blank line gap):

```
async def _do_start_roundtable(app, names):
    """Spawn named agents and open the Room tab.

    Called by the /team command handler.
    Spawns each agent in names if not yet active,
    builds the session_map, creates the Roundtable,
    and opens the Room buffer.
    """
    global _roundtable, _rt_room_buf
    global _active_registry
    if _active_registry is None:
        from starry_lib.agents.active_registry\
            import ActiveRegistry
        _active_registry = ActiveRegistry()
        _init_agent_tools()
    session_map = {}
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
        session_map[name] = f"agent-{name}"
    from starry_lib.agents.roundtable import (
        Roundtable,
    )
    _roundtable = Roundtable(_da_pool, session_map)
    _rt_room_buf = _spawn_roundtable_bufs(
        app, list(session_map.keys())
    )
    joined = ", ".join(names)
    _append_room(
        f"Roundtable started with: {joined}\n"
        "Type a message to address all agents.\n"
        "Type @name message to target one agent.\n"
        "Type /close to exit.\n"
    )
    app.invalidate()
```

---

## STEP 7 — Add roundtable gate in `accept_handler()`

Find this exact block (around line 9652):

```
        # ── Agent session routing ──────────
        global _session_stack, _active_registry
        global _ai_task
        if _session_stack:
```

Insert this new block immediately BEFORE those lines
(one blank line gap):

```
        # ── Roundtable routing ────────────
        global _roundtable, _rt_room_buf
        if _roundtable is not None:
            if text.lower() == "/close":
                _roundtable = None
                _rt_room_buf = None
                tab_mgr.goto_tab(0)
                app.invalidate()
                return
            target = None
            msg = text
            if text.startswith("@"):
                parts = text.split(None, 1)
                cand = parts[0][1:]
                if cand in _roundtable.agent_names:
                    target = cand
                    msg = (
                        parts[1]
                        if len(parts) > 1
                        else ""
                    )
            if msg:
                append_text(
                    build_user_frame(
                        text, _exec_mode
                    )
                )
                app.invalidate()
                asyncio.ensure_future(
                    handle_roundtable_response(
                        app, msg, target
                    )
                )
            return

```

IMPORTANT: the block above ends with `return` and a
blank line. Make sure the `# ── Agent session routing`
comment follows right after.

---

## STEP 8 — Add `bot-bar.roundtable` style to `build_style()`

Find this exact block (around line 258):

```
            "bot-bar.net": (
                f"{ACCENT_2} bg:{BG_PANEL}"
            ),
```

Insert the new style entry immediately after it (one
blank line gap):

```
            "bot-bar.roundtable": (
                f"bold {ACCENT_2} bg:{BG_PANEL}"
            ),
```

---

## STEP 9 — Update `get_bot_bar()` to show ROUNDTABLE indicator

Find this exact block in `get_bot_bar()` (around
line 1621):

```
    if _session_stack:
        _bot_rlabel = (
            "agent "
        )
        _bot_rval = (
            _session_stack[-1]["name"][:10]
            or "—"
        )
    else:
        _bot_rlabel = "role "
        _bot_rval = _active_role()[:10] or "—"
    parts.append((
        "class:bot-bar.label", _bot_rlabel
    ))
    parts.append((
        "class:bot-bar.version", _bot_rval
    ))
```

Replace it with:

```
    if _roundtable is not None:
        _n = len(_roundtable.agent_names)
        parts.append((
            "class:bot-bar.label", "room "
        ))
        parts.append((
            "class:bot-bar.roundtable",
            f"ROUNDTABLE({_n})",
        ))
    elif _session_stack:
        parts.append((
            "class:bot-bar.label", "agent "
        ))
        parts.append((
            "class:bot-bar.version",
            _session_stack[-1]["name"][:10] or "—",
        ))
    else:
        parts.append((
            "class:bot-bar.label", "role "
        ))
        parts.append((
            "class:bot-bar.version",
            _active_role()[:10] or "—",
        ))
```

---

## STEP 10 — Add `/team` command in `accept_handler()`

Find this exact block (around line 9722):

```
        # ── /exit ─────────────────────────
        if text.lower() == "/exit":
```

Insert the following new command block immediately
BEFORE that line (one blank line gap):

```
        # ── /team ─────────────────────────
        if text.lower() == "/team":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            _TEAM_OPTIONS = [
                "A. Roundtable",
                "B. Facilitator (soon)",
                "C. Structured Debate (soon)",
                "D. Collaborative Chain (soon)",
            ]

            def _on_team_select(idx):
                if idx != 0:
                    append_text(
                        build_warn_frame(
                            "Not yet implemented."
                        )
                    )
                    app.invalidate()
                    return
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
                if not agent_cfgs:
                    append_text(
                        build_warn_frame(
                            "No agents stored."
                            " Use /agent → Create"
                            " first."
                        )
                    )
                    app.invalidate()
                    return
                agent_names = [
                    cfg.name for cfg in agent_cfgs
                ]

                def _on_agents_confirm(indices):
                    if len(indices) < 2:
                        append_text(
                            build_warn_frame(
                                "Select at least"
                                " 2 agents."
                            )
                        )
                        app.invalidate()
                        return
                    names = [
                        agent_names[i]
                        for i in indices
                    ]
                    asyncio.ensure_future(
                        _do_start_roundtable(
                            app, names
                        )
                    )

                _dlg.show_toggle_dialog(
                    app,
                    title=(
                        "Roundtable"
                        " — Select Agents"
                    ),
                    items=agent_names,
                    on_confirm=_on_agents_confirm,
                    refocus=input_area,
                    max_visible=8,
                )

            _dlg.show_menu_dialog(
                app,
                title="Team Mode",
                options=_TEAM_OPTIONS,
                on_select=_on_team_select,
                refocus=input_area,
            )
            return

```

---

## STEP 11 — Add `/team` to `_ALL_COMMANDS` list

Find this exact block (around line 9696):

```
        _ALL_COMMANDS = [
            "/exit", "/clear", "/rewind",
            "/summarize", "/compact",
            "/help", "/tools",
            "/skills", "/sessions", "/rename",
            "/btw", "/trace", "/mode",
            "/role", "/setup", "/init",
            "/buffer", "/stats", "/agent",
            "/close", "/aboutme",
            "/new", "/save", "/load",
            "/add-dir", "/doctor", "/mcp",
        ]
```

Replace it with:

```
        _ALL_COMMANDS = [
            "/exit", "/clear", "/rewind",
            "/summarize", "/compact",
            "/help", "/tools",
            "/skills", "/sessions", "/rename",
            "/btw", "/trace", "/mode",
            "/role", "/setup", "/init",
            "/buffer", "/stats", "/agent",
            "/close", "/aboutme",
            "/new", "/save", "/load",
            "/add-dir", "/doctor", "/mcp",
            "/team",
        ]
```

---

## STEP 12 — Add `team` to `_BUILTIN_NAMES`

Find this exact block in `starry_lib/commands/store.py`
(around line 35):

```
_BUILTIN_NAMES: frozenset[str] = frozenset({
    "exit", "clear", "rewind", "summarize",
    "compact", "help", "tools", "skills",
    "sessions", "rename", "btw", "trace",
    "mode", "role", "setup", "init",
    "buffer", "stats", "agent", "close",
    "aboutme",
    "recap", "review", "focus", "goal",
    "project", "branch",
    "new", "add-dir", "save", "load",
    "doctor", "mcp",
})
```

Replace it with:

```
_BUILTIN_NAMES: frozenset[str] = frozenset({
    "exit", "clear", "rewind", "summarize",
    "compact", "help", "tools", "skills",
    "sessions", "rename", "btw", "trace",
    "mode", "role", "setup", "init",
    "buffer", "stats", "agent", "close",
    "aboutme",
    "recap", "review", "focus", "goal",
    "project", "branch",
    "new", "add-dir", "save", "load",
    "doctor", "mcp",
    "team",
})
```

---

## STEP 13 — Verify your work

```bash
cd /home/armando/starry
source .venv/bin/activate

# 1. Syntax checks:
python -c "import starry_lib.agents.roundtable"
python -c "import starry_lib.commands.store"
python -m py_compile starry_cli/main.py && echo OK

# 2. Unit tests:
pytest tests/unit/ -v -q
```

If `py_compile` reports a SyntaxError, the message
gives the line number. Fix and rerun.

---

## How to test manually

1. Start the TUI: `python -m starry_cli`
2. Create two agents if none exist:
   `/agent` → A. Create agent → name "alpha" → Save.
   Repeat for "beta".
3. Type `/team` → menu appears → select
   "A. Roundtable".
4. Toggle dialog appears — Space/T to check agents,
   Enter to confirm (need ≥ 2).
5. Room tab opens. Type a message — both agents
   respond. Status bar shows `ROUNDTABLE(2)`.
6. Type `@alpha hello only you` — only alpha responds.
7. Type `/close` — returns to Chat tab;
   status bar reverts to `role …`.

---

## Common mistakes to avoid

- Do NOT call `record_user()` before `post()`.
  `post()` reads the transcript via `format_context()`
  to build context for agents, so the user message
  must be recorded AFTER `post()` finishes. STEP 5
  already does this correctly; do not reorder.

- Do NOT use `await` inside `accept_handler()`.
  It is a synchronous function. Always wrap async
  calls with `asyncio.ensure_future()`.

- The `_ALL_COMMANDS` list is defined INSIDE
  `accept_handler()`, not at module level. Edit the
  one inside the function (around line 9696).

- The roundtable gate in STEP 7 MUST be inserted
  BEFORE the `# ── Agent session routing` block so
  that `/close` is intercepted by the roundtable
  handler first when a room is active.
