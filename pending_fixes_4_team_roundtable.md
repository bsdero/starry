# Pending fixes — `/team` Roundtable mode

Applies the same six fixes already merged for the
Structured Debate mode. File references are relative
to the repo root.

---

## Fix 1 — Prompt: enforce 3-5 sentences per response

### `starry_lib/agents/roundtable.py`

**Add `inject_seed()` method** after the existing
`record_response()` method (around line 94):

```python
def inject_seed(self, seed: str) -> None:
    """Inject a system message into every session.

    Call once after construction to prime agents
    with shared context (topic, constraints, etc.).
    """
    for sid in self._session_map.values():
        session = self._pool.get(sid)
        session.inject_system_message(seed)
```

**Add `agents` and `session_map` properties** after
`session_ids` (around line 67) so the continue-flow
in Fix 7 can reconstruct state:

```python
@property
def session_map(self) -> dict[str, str]:
    """Mapping of agent name → session_id."""
    return dict(self._session_map)
```

**Add `summarize_positions()` method** (identical
pattern to `Debate.summarize_positions()`), after
`inject_seed()`:

```python
async def summarize_positions(
    self,
) -> dict[str, str]:
    """Ask each agent to summarise their stance.

    Concurrent chat_complete() calls. Returns
    {name: summary_text}. Does not touch transcript.
    """
    import asyncio
    prompt = (
        "In 2-3 sentences, summarize your"
        " main points and position from"
        " this conversation. Be concise."
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
            for name, sid
            in self._session_map.items()
        ]
    )
    return dict(results)
```

**In `post()`, append the length constraint** to the
prompt (around line 139):

```python
# existing
if ctx:
    prompt = (
        "[Conversation context]\n"
        f"{ctx}\n\n{user_text}"
    )
else:
    prompt = user_text

# ADD this line after building prompt:
prompt += (
    "\nReply in 3-5 sentences maximum."
)
```

### `starry_cli/main.py` — `_do_start_roundtable()`

After `_roundtable = Roundtable(_da_pool, session_map)`
(around line 10255), inject the seed:

```python
_roundtable.inject_seed(
    "You are in a shared conversation room."
    " Keep every reply to 3-5 sentences"
    " maximum. Be direct and stay on topic."
)
```

---

## Fix 2 — Live token streaming (unresponsiveness)

### `starry_cli/main.py` — `handle_roundtable_response()`

Current code (around line 3571) accumulates tokens
silently and only renders on `done`. Replace with
the live partial-frame pattern:

```python
async def handle_roundtable_response(
    app, user_text, target=None
):
    global _roundtable, _rt_room_buf
    if _roundtable is None or _rt_room_buf is None:
        return

    _append_room(f"{M_DIM} ❯ {user_text}")
    app.invalidate()

    partial_text: dict[str, str] = {}
    partial_lines: dict[str, int] = {}

    async for event in _roundtable.post(
        user_text, target
    ):
        name = _roundtable.get_name_for_sid(
            event.session_id
        )
        if name is None:
            continue
        if event.type == "token":
            partial_text[name] = (
                partial_text.get(name, "")
                + str(event.data)
            )
            frame = build_team_agent_frame(
                name,
                partial_text[name],
                _get_team_color(name),
            )
            lc = frame.count("\n") + 1
            if name in partial_lines:
                _replace_buf_last(
                    _rt_room_buf,
                    partial_lines[name],
                    frame,
                )
            else:
                _append_room(frame)
            partial_lines[name] = lc
            app.invalidate()
        elif event.type == "done":
            full = str(event.data) or (
                partial_text.get(name, "")
            )
            _roundtable.record_response(name, full)
            partial_text.pop(name, None)
            partial_lines.pop(name, None)
            await asyncio.sleep(0)
            app.invalidate()
        elif event.type == "error":
            _append_room(
                f"{M_EFRAME} [{name} error]:"
                f" {event.data}"
            )
            app.invalidate()

    _roundtable.record_user(user_text)
    app.invalidate()
```

Key changes vs original:
- `partial_text` / `partial_lines` dicts per agent
- On `token`: live-render and replace partial frame
  via `_replace_buf_last(_rt_room_buf, ...)`
- On `done`: record transcript, clear partial state,
  yield with `await asyncio.sleep(0)`

---

## Fix 3 — Synthesis in white frame after `/close`

### `starry_cli/main.py` — new function `_offer_roundtable_synthesis()`

Add this function near `_offer_debate_synthesis`
(around line 3806). The roundtable has no automatic
"complete" signal, so synthesis is offered when the
user types `/close`.

```python
def _offer_roundtable_synthesis(app):
    """Ask user if they want a synthesis on /close.

    Yes → runs a subtask, shows result in a white
    frame, then shows follow-up questions via
    the debate_menu scroll menu.
    """
    global _roundtable
    if _roundtable is None:
        return

    transcript_text = _roundtable.format_context(
        limit=200
    )

    def _on_button(idx):
        if idx != 0:
            return
        if _da_pool is None:
            return

        async def _do_synthesis():
            prompt = (
                "Summarize the following"
                " conversation and identify"
                " the main themes discussed.\n"
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
            clean, fups = _extract_follow_ups(
                summary
            )
            _append_room(
                build_synthesis_frame(clean)
            )
            app.invalidate()
            if fups:
                _show_roundtable_follow_up(
                    app, fups
                )

        asyncio.ensure_future(_do_synthesis())

    _dlg.show_button_dialog(
        app,
        title="Roundtable recap",
        message=(
            "Show a synthesis before closing?"
        ),
        buttons=["Yes", "Close now"],
        on_button=_on_button,
        refocus=input_area,
    )
```

### `starry_cli/main.py` — new function `_show_roundtable_follow_up()`

Similar to `_show_debate_follow_up()` but writes to
`_rt_room_buf` and triggers `_continue_roundtable()`:

```python
def _show_roundtable_follow_up(app, questions):
    """Follow-up scroll menu in the Room buffer."""
    global _rt_room_buf
    if _rt_room_buf is None:
        return

    options = list(questions) + ["── End session"]

    def on_select(idx):
        prev = debate_menu._prev_lines
        if prev > 0 and _rt_room_buf:
            _replace_buf_last(
                _rt_room_buf, prev, ""
            )
        if idx == len(options) - 1:
            _append_room(
                f"{M_DIM} Session closed."
            )
            app.invalidate()
            return
        chosen_q = questions[idx]
        asyncio.ensure_future(
            _continue_roundtable(app, chosen_q)
        )

    def on_cancel():
        if _rt_room_buf:
            _append_room(
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
    _append_room(menu_text)
    app.invalidate()
```

---

## Fix 7 — Continue roundtable after question select

### `starry_cli/main.py` — new function `_continue_roundtable()`

Same pattern as `_continue_debate()`: summarize,
clear histories, reseed, post the question.

```python
async def _continue_roundtable(app, new_question):
    """Reset agent histories and continue chat.

    1. Ask each agent for a 2-3 sentence summary.
    2. Clear each agent's conversation history.
    3. Inject each agent's own summary back in.
    4. Post the selected question to kick off the
       new conversation.

    No files in ~/.local/starry/ are touched.
    """
    global _roundtable, _rt_room_buf
    if _roundtable is None or _da_pool is None:
        return

    _append_room(
        f"{M_DIM}"
        " Gathering position summaries…"
    )
    app.invalidate()

    summaries = (
        await _roundtable.summarize_positions()
    )

    for name, sid in (
        _roundtable.session_map.items()
    ):
        session = _da_pool.get(sid)
        session.clear_history()
        summ = summaries.get(name, "")
        if summ:
            session.inject_system_message(
                f"[Your prior position]: {summ}"
            )

    sep = "─" * (frame_width() - 4)
    _append_room(
        f"{M_NFRAME} ╌{sep}╌\n"
        f"{M_DIM} ↻ Continuing:"
        f" {new_question}"
    )
    app.invalidate()
    asyncio.ensure_future(
        handle_roundtable_response(
            app, new_question
        )
    )
```

---

## Fix 4 — Room tab focused when roundtable starts

### `starry_cli/main.py` — `_spawn_roundtable_bufs()`

Same root cause as the debate bug: `_spawn_agent_bufs`
called in the loop overwrites `tab_mgr.active` for
each agent tab, so by the time the function returns
`active` points to the last agent's tab, not the Room.

**Current code (around line 3350):**
```python
tab_mgr.tabs.append(room_tab)
tab_mgr.active = len(tab_mgr.tabs) - 1
for name in agent_names:
    if _agent_chat_buf(name) is None:
        _spawn_agent_bufs(app, name)
app.invalidate()
return room_buf
```

**Replace with:**
```python
tab_mgr.tabs.append(room_tab)
# Record index before agent tabs are appended.
room_tab_idx = len(tab_mgr.tabs) - 1
for name in agent_names:
    if _agent_chat_buf(name) is None:
        _spawn_agent_bufs(app, name)
# Restore focus; _spawn_agent_bufs overwrites active.
tab_mgr.active = room_tab_idx
app.invalidate()
return room_buf
```

---

## Fix 5 — `/exit` command in roundtable mode

### `starry_cli/main.py` — Roundtable routing block

**Current code (around line 10538):**
```python
if _roundtable is not None:
    if text.lower() == "/close":
        _roundtable = None
        _rt_room_buf = None
        _team_agent_colors.clear()
        global _team_color_next
        _team_color_next = 0
        tab_mgr.goto_tab(0)
        app.invalidate()
        return
```

**Replace with** (also wire synthesis offer into
`/close` — see Fix 3):
```python
if _roundtable is not None:
    tl = text.lower()
    if tl in ("/close", "/exit"):
        # Offer synthesis before closing.
        # Cleanup happens inside the button
        # callback; offer_roundtable_synthesis
        # must call the teardown on "No" too.
        _offer_roundtable_synthesis(app)
        # Defer state teardown to the dialog cb.
        # If /exit: also schedule app.exit() after
        # the dialog resolves.
        # ── Implementation note ──────────────────
        # The simplest approach: call synthesis
        # offer first (which shows a dialog), then
        # tear down state only after the user
        # answers. To do this cleanly, pass a
        # `on_close` callback into
        # _offer_roundtable_synthesis that does:
        #   _roundtable = None; _rt_room_buf = None
        #   _team_agent_colors.clear(); goto_tab(0)
        #   if was_exit: app.exit()
        # See implementation detail below.
        return
    target = None
    ...
```

**Implementation detail for `/close` + `/exit` with
synthesis offer:**

Refactor `_offer_roundtable_synthesis(app, on_close)`
to accept an `on_close` callable. The caller passes
`on_close=lambda: _teardown_roundtable(app)`.
`/exit` passes `on_close=lambda: (_teardown_roundtable(app), asyncio.ensure_future(_exit_coro(app)))`.

Add a shared teardown helper:

```python
def _teardown_roundtable(app):
    global _roundtable, _rt_room_buf
    global _team_agent_colors, _team_color_next
    _roundtable = None
    _rt_room_buf = None
    _team_agent_colors.clear()
    _team_color_next = 0
    tab_mgr.goto_tab(0)
    app.invalidate()
```

---

## Fix 6 — Scroll unresponsiveness

`PageUp`/`PageDown` bindings already exist globally
(added for the debate fix); no new bindings needed.

The only change: the `await asyncio.sleep(0)` yield
is already included in the rewritten
`handle_roundtable_response()` above (Fix 2), which
gives the UI event loop room to process between agent
responses in a broadcast turn.

---

## Summary of files to change

| File | What changes |
|------|-------------|
| `starry_lib/agents/roundtable.py` | `inject_seed()`, `summarize_positions()`, `session_map` property, length constraint in `post()` |
| `starry_cli/main.py` | `_spawn_roundtable_bufs()` tab-focus fix; rewrite `handle_roundtable_response()` with live streaming; add `_offer_roundtable_synthesis()`, `_show_roundtable_follow_up()`, `_continue_roundtable()`, `_teardown_roundtable()`; update roundtable routing block for `/close`+`/exit` |

**$HOME constraint**: no changes touch
`~/.local/starry/`. `clear_history()` and
`inject_system_message()` only mutate in-memory
session state.
