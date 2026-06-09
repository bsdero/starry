# Common behavior — all team chat modes

Applies to every team chat mode (Roundtable, and
any future modes). Implement each point exactly as
described so behavior is consistent across modes.

---

## C1 — Room tab focused on start

After spawning per-agent buffers, the active tab
must be the Room tab — not the last agent tab.

**Pattern:**
```python
tab_mgr.tabs.append(room_tab)
# Capture index BEFORE the agent-spawn loop.
room_tab_idx = len(tab_mgr.tabs) - 1
for name in agent_names:
    if _agent_chat_buf(name) is None:
        _spawn_agent_bufs(app, name)
# Restore — _spawn_agent_bufs overwrites active.
tab_mgr.active = room_tab_idx
app.invalidate()
```

---

## C2 — Token streaming: accumulate, flush on done

Accumulate tokens silently per agent. Append the
complete frame once on `done`. Do **not** use
`_replace_buf_last` for multi-agent (broadcast)
streaming: concurrent agents interleave writes to
the shared buffer, so the partial frame is not
guaranteed to be at the tail when the next token
arrives. Attempting in-place replacement corrupts
the buffer and produces duplicate or truncated
agent frames.

**Pattern inside the streaming loop:**
```python
partial_text: dict[str, str] = {}

# on "token":
partial_text[name] = (
    partial_text.get(name, "") + str(event.data)
)

# on "done":
full = str(event.data) or partial_text.get(name, "")
frame = build_team_agent_frame(name, full, color)
_append_room(frame)
# record transcript here
partial_text.pop(name, None)
await asyncio.sleep(0)   # yield for scroll / UI
app.invalidate()
```

---

## C3 — `/exit` = immediate quit

In the mode's routing block, `/exit` always means
immediate teardown plus scheduled `app.exit()`.
No synthesis, no dialog, no follow-up menu.

```python
if tl == "/exit":
    _teardown_<mode>(app)
    async def _exit_coro():
        await asyncio.sleep(0.3)
        app.exit()
    asyncio.ensure_future(_exit_coro())
    return
```

---

## C4 — `/close` = end-of-session synthesis

`/close` triggers automatic synthesis. Teardown is
deferred — it fires only after the user acts on the
post-synthesis menus (see C5, C6, C7).

```python
if tl == "/close":
    _run_<mode>_synthesis(app)
    return
```

For modes with a **natural end** (e.g. debate after
N rounds), synthesis fires automatically at that
point; `/close` still tears down immediately because
synthesis was already shown.

---

## C5 — Auto synthesis, no dialog

Synthesis always runs unconditionally. No Yes/No
dialog is shown. A throwaway session is used.

```python
def _run_<mode>_synthesis(app):
    if _<mode> is None or _da_pool is None:
        _teardown_<mode>(app)
        return

    transcript_text = _<mode>.format_context(limit=200)

    async def _do_synthesis():
        prompt = (
            "Summarize the following conversation"
            " and identify the main themes discussed.\n"
            "After the summary, on its own line append"
            " exactly:\n"
            '{"follow_ups": ["<q1>", "<q2>", "<q3>"]}\n'
            "where q1-q3 are insightful follow-up"
            " questions.\n\n"
            f"{transcript_text}"
        )
        summary = await _da_pool.run_subtask(
            prompt, mode="plan"
        )
        clean, fups = _extract_follow_ups(summary)
        _append_<mode>_room(build_synthesis_frame(clean))
        app.invalidate()
        _show_<mode>_save_menu(app, fups)

    asyncio.ensure_future(_do_synthesis())
```

The model used is the active provider's default model
(same as the main chat session — no special model).

---

## C6 — Two-level post-synthesis menu

### Level 1 — Save menu

Appears immediately after the synthesis frame.
Only two options:

```
  Save & continue
  Save & close
```

- **Save & continue** → saves synthesis to file →
  shows Level 2 (follow-up questions menu).
- **Save & close** → saves synthesis to file →
  calls `_teardown_<mode>(app)`.
- **Escape / cancel** → skips saving, goes directly
  to Level 2 (follow-up questions menu).

Save target: `~/.local/starry/summaries/<mode>_<timestamp>.md`

The summaries directory is created automatically on
first save — do not rely on `install.sh` for this:
```python
path.parent.mkdir(parents=True, exist_ok=True)
```

After saving, append a dim confirmation line to the
room buffer (no dialog):
```python
_append_<mode>_room(
    f"{M_DIM} Saved to {path}"
)
```

### Level 2 — Follow-up questions menu

Appears after "Save & continue" or after Escape on
Level 1. Uses the existing `debate_menu` widget.

```
  <Q1 from synthesis>
  <Q2 from synthesis>
  <Q3 from synthesis>
  ── End session
```

- Picking a question → `_continue_<mode>(app, q)`
- "End session" → `_teardown_<mode>(app)`
- Escape / cancel → dim "Follow-up dismissed" line

---

## C7 — Shared teardown helper per mode

Each mode has its own `_teardown_<mode>(app)` that
clears all mode-specific globals and navigates away.

```python
def _teardown_<mode>(app):
    global _<mode>, _<mode>_room_buf
    global _team_agent_colors, _team_color_next
    _<mode> = None
    _<mode>_room_buf = None
    _team_agent_colors.clear()
    _team_color_next = 0
    tab_mgr.goto_tab(0)
    app.invalidate()
```

---

## C8 — User input shown as a frame in the room buffer

Render the user's message with `build_user_frame`
in the room buffer — not as a bare dim line.
This keeps the visual language consistent with the
main chat tab.

```python
_append_room(
    build_user_frame(user_text, _exec_mode)
)
app.invalidate()
```

---

## C9 — "Your turn" notification after agents finish

After all agents have responded (the streaming loop
exits), append a white inline notification so the
user knows they can type a follow-up.

```python
_append_room(
    build_inline_notif("Your turn", "→")
)
app.invalidate()
```

---

## C10 — Welcome messages on mode start

Every mode must print dim status lines to the room
buffer immediately after it opens. The last line
must state the available exit commands, matching
what the routing block actually handles.

**Pattern:**

```python
for _ln in [
    f"<Mode> started — <summary line>",
    "<instruction line>",   # e.g. @name targeting
    "<exit hint>",          # see below
]:
    _append_<mode>_room(f"{M_DIM} {_ln}")
app.invalidate()
```

**Exit hint wording (keep consistent):**

| Mode | `/close` meaning | Exit hint line |
|------|-----------------|----------------|
| Roundtable | Ends session, runs synthesis | `"/close — finish & synthesize \| /exit — quit"` |
| Debate | Immediate teardown (synthesis auto-ran) | `"/close — end debate \| /exit — quit"` |

The hint must use `—` (em dash) and `|` as
separators. No full-stop at the end.

---

## Summary table

| Rule | Trigger | Action |
|------|---------|--------|
| C1 | Mode start | Room tab focused after agent bufs spawn |
| C2 | Every token | Accumulate per agent; flush complete frame on done |
| C3 | `/exit` | Immediate teardown + app.exit() |
| C4 | `/close` | Fire synthesis, defer teardown |
| C5 | End of session | Synthesis auto-runs, no dialog |
| C6 | After synthesis | Save menu (L1) → follow-up menu (L2) |
| C7 | Any teardown | Shared helper clears state + goes to tab 0 |
| C8 | User input | Render with `build_user_frame` in room buffer |
| C9 | Agents done | Append `build_inline_notif("Your turn", "→")` |
| C10 | Mode start | Print dim welcome lines; last line states `/close` and `/exit` |
