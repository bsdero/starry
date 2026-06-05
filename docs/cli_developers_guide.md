# StarryCLI — Developer Guide

Reference for agents and developers extending `starry_cli/main.py`.
All public APIs live in that single file unless noted otherwise.

---

## 1. Architecture Overview

```
starry_cli/main.py  (~9 500 lines, all TUI logic)
├── Theme engine           starry_cli/themes/loader.py
├── StarryLib library      starry_lib/
└── prompt_toolkit         (full-screen async TUI)
```

### Layout tree

```
root_container  FloatContainer
│  ← _active_floats list (notifications + dialogs)
└── base_container  HSplit
    ├── top_bar          Window  height=3  (framed header)
    ├── tab_bar_window   Window  height=1  (tab strip)
    ├── body_container   DynamicContainer  (active tab)
    ├── bot_bar          Window  height=3  (framed footer)
    └── input_area       TextArea          (user input)
```

The `DynamicContainer` calls `_get_body_window()` on every
redraw — switching `tab_mgr.active` instantly swaps the
visible buffer without rebuilding the layout.

---

## 2. Color Palette and Theme Variables

Loaded from the active theme JSON file at startup.
All are module-level strings (hex color codes or
prompt_toolkit color names).

| Variable | Role |
|---|---|
| `BG_DEEP` | Canvas background |
| `BG_PANEL` | Bars, panels |
| `BG_SCROLL` | Scroll area background |
| `BORDER` | Frame borders (blue-grey) |
| `TEXT` | Default foreground |
| `ACCENT_1` | Lime green highlights |
| `ACCENT_2` | Fuchsia highlights |
| `SYS_TEXT` | Orange system text |
| `LIGHT_TEXT` | Secondary bright text |
| `MUTED` | Dimmed / inactive text |
| `DIM_TEXT` | Very dimmed text |
| `WHITE` | Pure white |
| `ERROR_RED` | Error frames |
| `CODE_INL_BG` | Inline code background |
| `MODE_CLR_EXEC` | Execution mode color |
| `MODE_CLR_PLAN` | Plan mode color |

To add a new theme variable, add it to the theme JSON file
and bind it in the palette block at the top of `starry_cli/main.py`.

---

## 3. Style System

### `build_style(mode="execution") -> Style`

Rebuilds the full `prompt_toolkit.styles.Style` dict.
Called at startup and on every mode switch (Ctrl+P).

```python
APP_STYLE = build_style("execution")
# After a mode switch:
app.style = build_style(_exec_mode)
```

### Style class names reference

| Class | Usage |
|---|---|
| `top-bar`, `top-bar.*` | Header bar tokens |
| `bot-bar`, `bot-bar.*` | Footer bar tokens |
| `scroll-area` | Body scroll window |
| `input-area`, `input-prompt` | Input text area |
| `tab-bar` | Tab strip background |
| `tab-bar.active` | Active tab label |
| `tab-bar.inactive` | Inactive tab labels |
| `tab-bar.sep` | Separator between tabs |
| `line.*` | Lexer line styles (see §6) |
| `span.*` | Inline span styles (see §6) |
| `notif.frame`, `notif.text`, `notif.bg` | Toast floats |
| `menu.frame`, `menu.item`, `menu.selected`, `menu.label` | SelectionMenu |
| `dialog`, `dialog.body`, `dialog frame.label` | Dialog chrome |
| `button`, `button.focused` | Dialog buttons |
| `thinking` | Spinner / thinking animation |

To add a new style, insert a key/value into the `return
Style.from_dict({...})` block inside `build_style()`.

---

## 4. Marker System

Every line appended to a scroll buffer carries a 2-char
**marker prefix** that `FrameLexer` reads to choose the
`prompt_toolkit` style class for that line.
`MarkerStripProcessor` then hides those 2 chars before
display.

### Marker constants

```python
M_UFRAME  = "Uf"   # user frame border
M_UCONTENT = "Uc"  # user frame content
M_UTEXT   = "Uw"   # user frame body text
M_AFRAME  = "Af"   # AI frame border
M_ACONTENT = "Ac"  # AI frame content
M_AHEADER = "Ah"   # markdown H1/H2/H3
M_ABOLD   = "Ab"   # markdown bold
M_ACODE   = "Ak"   # inline code block
M_ABULLET = "Al"   # bullet list item
M_ATHINK  = "At"   # thinking spinner line
M_PLAIN   = "Pl"   # unstyled text
M_DIM     = "Dm"   # dim text
M_MULTI   = "Mx"   # multi-color line (inline spans)
M_NFRAME  = "Nf"   # inline-notification border
M_NCONTENT = "Nc"  # inline-notification content
M_EFRAME  = "Ef"   # error frame border  (red)
M_ECONTENT = "Ec"  # error frame content (red)
M_WFRAME  = "Wf"   # warning frame border
M_WCONTENT = "Wc"  # warning frame content
M_UPLAN   = "UP"   # user frame, plan mode (color baked in)
M_UEXEC   = "UX"   # user frame, exec mode (color baked in)
```

### Writing a raw marked line

```python
# Single styled line
line = f"{M_AFRAME} {TL}{HZ * inner}{TR}"

# Append to scroll buffer
append_text(line)
```

The space after the marker is the separator; actual content
starts at column 3.

### Inline span system (`M_MULTI` lines)

Within an `M_MULTI` line, multi-color fragments use the
delimiter pair `SOL` (`\x01`) + `EOL` (`\x02`):

```
SOL <style_code> EOL <text> SOL
```

Style codes (single char):

| Code | Prompt_toolkit class |
|---|---|
| `B` | `span.bold` (fuchsia bold) |
| `C` | `span.code` (lime on dark bg) |
| `I` | `span.italic` |
| `L` | `span.light` |
| `O` | `span.orange` |
| `W` | `span.white` |
| `D` | `span.dim` |
| `G` | `span.lime` |

```python
# Build a multi-color line with the _inline() helper
from starry_cli.main import SOL, EOL, M_MULTI
fragment = f"{SOL}B{EOL}bold text{SOL} plain text"
line = f"{M_MULTI} {fragment}"
append_text(line)
```

---

## 5. Buffer System

Three persistent scroll buffers, all `read_only=True`
(use `bypass_readonly=True` to write).

| Buffer | Name | Visible in tab |
|---|---|---|
| `main_buffer` | `"main_output"` | Chat |
| `tool_output_buffer` | `"tool_output"` | Tool Output |
| `logs_buffer` | `"logs"` | Logs |

### Write helpers

```python
append_text(text)         # → main_buffer (Chat tab)
append_tool_output(text)  # → tool_output_buffer
append_log(text)          # → logs_buffer
```

All three call the shared internal `_buf_append(buf, text)`.
Content is joined with `"\n"` separators; cursor is kept at
the end so the view auto-scrolls.

```python
replace_last_block(n_lines, new_text)
# Replaces the last n_lines in main_buffer with new_text.
# Used by the spinner animation to update in-place.
```

### Scratch tab buffers

Scratch tabs created by `tab_mgr.new_tab()` own `read_only=False`
`Buffer` instances. Write to them directly:

```python
tab = tab_mgr.new_tab("My Tab")
tab.buffer.set_document(
    Document(text="hello", cursor_position=5)
)
```

---

## 6. Frame Builders

High-level helpers that produce fully-styled, marker-prefixed
multi-line strings ready for `append_text()`.

```python
build_user_frame(cmd_text, mode="execution") -> str
# Orange (exec) or blue (plan) user command block.
# mode is baked into the marker so it does not repaint
# if the user switches modes later.

build_ai_frame(md_text) -> str
# Blue AI response frame with markdown parsing:
# headers, bold, inline code, bullet lists, word wrap.

build_thinking_frame(spinner_ch="⠋", message=...) -> str
# Animated thinking indicator. Replace with
# replace_last_block() on each spinner tick.

build_inline_notif(message, label="🔔") -> str
# White framed inline notification block.

build_error_frame(message) -> str
# Red framed error block.

build_warn_frame(message) -> str
# Cyan framed warning block.

build_role_info_frame(role_name) -> str
# Info block shown after a role switch.

build_question_frame(questions) -> str
# Prompt block for multi-question flows.

build_wizard_prompt_frame(prompt_text) -> str
# Single-prompt block used by the provider wizard.

build_setup_list_frame(title, items) -> str
# List display frame (provider/model lists).

build_tools_frame(schemas) -> str
# Renders a list of tool schemas.
```

---

## 7. Notification System (Floating Toasts)

`notif_mgr` is the module-level `NotificationManager` instance.
Toasts appear top-right and auto-dismiss.

```python
notif_mgr.notify(message, duration=3.0)
# Shows a floating toast for `duration` seconds.
# Safe to call from any coroutine or sync context.
```

Internally, toasts are `Float` objects pushed into
`_active_floats` and merged with dialog floats via
`_rebuild_floats()`.

---

## 8. Dialog System

Dialogs are modal `Float` overlays that sit on top of the
entire layout. They use the same float layer as notifications
but persist until explicitly closed.

### Building a dialog

```python
from prompt_toolkit.widgets import Dialog, Button
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.layout.containers import Float
from prompt_toolkit.widgets import TextArea

def make_confirm_dialog(app, question, on_yes, on_no):
    float_ref = [None]   # forward reference

    def _yes():
        close_dialog(app, float_ref[0])
        on_yes()

    def _no():
        close_dialog(app, float_ref[0])
        on_no()

    dlg = Dialog(
        title="Confirm",
        body=HSplit([
            TextArea(
                text=question,
                multiline=False,
                read_only=True,
            ),
        ]),
        buttons=[
            Button("Yes", handler=_yes),
            Button("No",  handler=_no),
        ],
    )
    f = Float(content=dlg, xcursor=True, ycursor=True)
    float_ref[0] = f
    show_dialog(app, f)
```

### API

```python
show_dialog(app, float_obj)
# Pushes float_obj into _dialog_floats, rebuilds the
# float list, and calls app.invalidate().

close_dialog(app, float_obj)
# Removes float_obj, restores focus to input_area,
# calls app.invalidate().
```

### Style the dialog via `build_style()`

| Key | Applied to |
|---|---|
| `"dialog"` | Outer dialog container |
| `"dialog.body"` | Body region |
| `"dialog frame.label"` | Title bar text |
| `"button"` | Unfocused button |
| `"button.focused"` | Focused button |

### Wizard pattern

A wizard is a chain of dialogs. Each dialog's confirm handler
closes itself and opens the next one.

```python
steps = []   # list of (float, dialog) pairs
results = {}

def step1(app):
    field = TextArea(multiline=False, text="")
    def _next():
        results["name"] = field.text
        close_dialog(app, steps[0])
        step2(app)
    def _cancel():
        close_dialog(app, steps[0])
    dlg = Dialog(
        title="Step 1 — Name",
        body=field,
        buttons=[
            Button("Next",   handler=_next),
            Button("Cancel", handler=_cancel),
        ],
    )
    f = Float(content=dlg, xcursor=True, ycursor=True)
    steps.append(f)
    show_dialog(app, f)

def step2(app):
    # ... same pattern, calls on_wizard_complete() at end
    pass
```

---

## 9. Selection Menu (Inline Arrow-Key Menu)

`SelectionMenu` renders a framed, arrow-key-navigable list
directly into the scroll buffer (not a float).

```python
sel_menu   # module-level singleton

sel_menu.show(
    title,          # str — displayed in frame label
    options,        # list[str]
    callback,       # callable(selected_index: int)
    white=False,    # True → white/notification style
)
menu_text = sel_menu.build_frame()
sel_menu._prev_lines = menu_text.count("\n") + 1
append_text(menu_text)
app.invalidate()
```

Key bindings are wired automatically while `sel_menu.active`
is `True`:

| Key | Action |
|---|---|
| `Up` | `sel_menu.move_up()` |
| `Down` | `sel_menu.move_down()` |
| `Enter` | `sel_menu.confirm()` → fires `callback(idx)` |
| `Escape` | `sel_menu.dismiss()` → clears menu lines |

Use for quick lists where the result is a single selection.
Use a **Dialog** instead when you need text input, multi-step
flows, or a more prominent UI surface.

---

## 10. Tab System

### Data model

```python
class Tab:
    name: str          # label shown in tab bar
    buffer: Buffer     # prompt_toolkit Buffer
    read_only: bool    # True for output tabs

class TabManager:
    tabs: list[Tab]
    active: int        # index of focused tab
```

### Module-level instance

```python
tab_mgr   # TabManager with 3 predefined tabs:
          #   0 → Chat         (main_buffer)
          #   1 → Tool Output  (tool_output_buffer)
          #   2 → Logs         (logs_buffer)
```

### TabManager API

```python
tab_mgr.next_tab()            # advance active by 1 (wraps)
tab_mgr.prev_tab()            # go back by 1 (wraps)
tab_mgr.goto_tab(n)           # jump to index n (0-based)
tab_mgr.active_buffer()       # → Buffer of active tab

tab = tab_mgr.new_tab(name="Scratch")
# Creates a Buffer named "scratch_N", read_only=False.
# Sets active to the new tab. Returns the Tab object.

tab_mgr.close_tab(index=None)
# Closes index (default: active). No-op if only 1 tab.
```

### Key bindings

| Key | Action |
|---|---|
| `Ctrl+Right` | `tab_mgr.next_tab()` |
| `Ctrl+Left` | `tab_mgr.prev_tab()` |
| `Ctrl+T` | `tab_mgr.new_tab()` |
| `Ctrl+W` | `tab_mgr.close_tab()` |
| `Alt+1` … `Alt+9` | `tab_mgr.goto_tab(n-1)` |

(`Alt+N` is sent as `Escape N` by most terminals.)

### Adding a programmatic tab

```python
# Create a tab, write initial content, show it.
tab = tab_mgr.new_tab("Trace")
tab.buffer.set_document(
    Document(
        text="=== Trace output ===\n",
        cursor_position=20,
    )
)
tab_mgr.goto_tab(len(tab_mgr.tabs) - 1)
app.invalidate()
```

### Feeding content to existing tabs

```python
append_text(frame)          # Chat tab
append_tool_output(text)    # Tool Output tab
append_log(text)            # Logs tab
```

For any tab's buffer you can also call `_buf_append` directly:

```python
from starry_cli.main import _buf_append
_buf_append(my_tab.buffer, "raw text")
```

---

## 11. Key Bindings

All bindings live in the module-level `KeyBindings` instance `kb`.

```python
@kb.add("c-x")           # Ctrl+X
def my_handler(event):
    event.app.invalidate()

@kb.add("f5")            # F5
def refresh(event): ...

@kb.add("escape", "x")  # Alt+X  (escape sequence)
def alt_x(event): ...

# Conditional binding (only fires when predicate is True)
from prompt_toolkit.filters import Condition

@kb.add(
    "enter",
    filter=Condition(lambda: sel_menu.active),
)
def on_enter_menu(event):
    sel_menu.confirm()
    event.app.invalidate()
```

To register many variants with a factory:

```python
def _register(ch):
    @kb.add("escape", ch)
    def _h(event):
        do_something(ch)

for c in "abcde":
    _register(c)
```

---

## 12. Application State Globals

Read these to know the current session context.

```python
_cur_provider: str      # active provider name
_cur_model: str         # active model name
_cur_role: str          # active agent role name
_cur_theme: str         # active theme name
_exec_mode: str         # "execution" | "plan"
_tui_input_mode: str    # "chat" | "question" | "wizard"
_da_settings            # da.AppSettings or None
_da_session             # da.Session or None
_da_pool                # da.AgentPool or None
_active_registry        # da.ActiveRegistry or None
_ai_task                # asyncio.Task | None (active LLM call)
session_stack           # list[dict] — named agent routing stack
```

`session_stack` entries are `{"name": str, "owned": bool}`.
When non-empty, prompt input routes to the named agent session
at the top of the stack instead of the main session. `owned=True`
means `/close` will kill the agent; `owned=False` leaves it alive.

---

## 13. Adding a Slash Command

Adding a new built-in slash command requires four updates:

**1. Handler** in `accept_handler()` inside `setup_input_handler()`
(~line 9582). Add a branch before the default LLM dispatch:

```python
# ── /mycommand ────────────────────────
if text.lower().startswith("/mycommand"):
    append_text(
        build_user_frame(text, _exec_mode)
    )
    arg = text[len("/mycommand"):].strip()
    # async work must use ensure_future — never await here
    asyncio.ensure_future(_my_coro(app, arg))
    return
```

**2. `_ALL_COMMANDS` list** (~line 9648) — add the command name
so 4+-character prefix auto-expansion works:

```python
_ALL_COMMANDS = [
    ...
    "/mycommand",
    ...
]
```

**3. `/help` text** in `_build_help_md()`:

```python
"- `/mycommand` — One-line description\n"
```

**4. `_BUILTIN_NAMES`** in `starry_lib/commands/store.py` — add
the name so users cannot shadow it with a custom command:

```python
_BUILTIN_NAMES: frozenset[str] = frozenset({
    ...,
    "mycommand",
})
```

---

## 14. Adding to the Top or Bottom Bar

Both bars are `FormattedText` lists built by `get_top_bar()`
and `get_bot_bar()`. Add a tuple `(style_class, text)` to
the `parts` list before the padding / closing border:

```python
parts.append(
    ("class:top-bar.label", " │ ")
)
parts.append(
    ("class:top-bar.version", my_value)
)
```

The padding logic (`vis - w - 2`) auto-adjusts, but check
that the bar still fits at 80 columns.

---

## 15. Scroll Behavior

`_scroll_main(event, delta)` scrolls **the active tab's
buffer** (not necessarily `main_buffer`). It uses
`tab_mgr.active_buffer()` so PgUp/PgDn and mouse-wheel work
on whichever tab is focused.

To scroll a specific buffer programmatically:

```python
buf = main_buffer          # or any Buffer
doc = buf.document
rows = doc.lines
target_row = max(0, doc.cursor_position_row + delta)
target_row = min(len(rows) - 1, target_row)
pos = sum(len(rows[i]) + 1 for i in range(target_row))
buf.set_document(
    Document(
        text=doc.text,
        cursor_position=min(pos, len(doc.text)),
    ),
    bypass_readonly=True,
)
```

---

## 16. Box-Drawing Constants

```python
TL = "╭"   TR = "╮"
BL = "╰"   BR = "╯"
HZ = "─"   VT = "│"
```

Used in every frame builder. Use them directly when writing
custom frames.

---

## 17. Telemetry State

```python
telemetry         # TelemetryState singleton

telemetry.ai_status   # "idle" | "thinking" | "streaming"
telemetry.tick()      # update uptime counter
telemetry.next_spinner() -> str  # advance spinner frame
telemetry.uptime()    # → "HH:MM:SS" string
```

The bottom bar reads `telemetry.ai_status` to render the
status indicator. Set it from the LLM response handler:

```python
telemetry.ai_status = "thinking"   # before LLM call
telemetry.ai_status = "streaming"  # on first token
telemetry.ai_status = "idle"       # after completion
```

---

## 18. Quick Reference Cheat Sheet

| Goal | Call |
|---|---|
| Write to Chat | `append_text(build_ai_frame(md))` |
| Write to Tool Output | `append_tool_output(text)` |
| Write to Logs | `append_log(text)` |
| Show toast | `notif_mgr.notify("msg", 3.0)` |
| Show inline error | `append_text(build_error_frame("msg"))` |
| Show inline warning | `append_text(build_warn_frame("msg"))` |
| Show selection menu | `sel_menu.show(title, opts, cb)` |
| Show modal dialog | `show_dialog(app, Float(content=Dialog(...)))` |
| Close modal dialog | `close_dialog(app, float_obj)` |
| Switch to tab N | `tab_mgr.goto_tab(N)` |
| New scratch tab | `tab_mgr.new_tab("Label")` |
| Force redraw | `app.invalidate()` |
| Current provider | `_cur_provider` |
| Current model | `_cur_model` |

---

## 19. Named Agent Buffers

Each active named agent has two TUI buffers backed by one `Session`:

| Buffer name | Created | Writable by |
|-------------|---------|-------------|
| `agent:<name>:chat` | At spawn time | User (via `session_stack`) |
| `agent:<name>:log` | Lazily on first `call_agent` | `call_agent` tool — read-only to user |

### Routing prompt input to a named agent

Push an entry onto `session_stack` to redirect all prompt input:

```python
session_stack.append({
    "name": "agent:<name>",
    "owned": True,   # True → kill agent on /close
})
app.invalidate()
```

`/close` pops the stack and, if `owned=True`, terminates the agent.

### Writing to an agent's log buffer

`call_agent` writes to the log buffer while streaming the
agent's reply. To write directly from TUI code:

```python
log_buf = tab_mgr.get_buffer("agent:myagent:log")
if log_buf:
    _buf_append(log_buf, build_ai_frame(text))
```

### Accessing the agent's session

```python
session = _active_registry.get_session("myagent")
if session:
    async for event in session.chat_auto("Hello"):
        ...
```

---

## 20. Custom Command System

User-defined `/` commands are stored as `{name: prompt}` JSON
entries and dispatched by `accept_handler()` before the built-in
command block.

**Storage:**
- Global: `~/.local/starry/conf/commands.json`
- Project: `.starry/commands.json` (overrides global by name)

**`$ARGUMENTS` substitution:** if the prompt contains
`$ARGUMENTS`, everything the user typed after the command name
is substituted in. Commands with `$ARGUMENTS` require at least
one argument word; the TUI shows an error if run bare.

**API** (`starry_lib/commands/store.py`):

```python
from starry_lib.commands.store import (
    list_commands,    # () -> list[{"name", "prompt"}]
    get_command,      # (name) -> str | None
    command_exists,   # (name) -> bool
    validate_name,    # (name) -> error_str | None
    save_command,     # (name, prompt) -> None  (global file)
    delete_command,   # (name) -> bool
    seed_builtin_commands,  # () -> None  (first-run only)
)
```

`seed_builtin_commands()` is called at TUI startup. It writes
the built-in defaults (`recap`, `review`, `focus`, `goal`,
`project`, `branch`) to the global file only if the file does
not yet exist — preserving any user edits.

Built-in TUI command names are listed in `_BUILTIN_NAMES`; the
`validate_name()` function rejects any name that conflicts.
