# Plan: CLI UI Elements for davy_cli.py

## Context

`davy_cli.py` is a large (~4500+ lines) TUI built entirely on `prompt_toolkit`. Key
existing infrastructure:

- Single `main_buffer` (read-only scroll area) + one `TextArea` input at bottom
- `FloatContainer` + `_active_floats` list for floating toasts (already working)
- Custom `FrameLexer` + `MarkerStripProcessor` for styled marker-prefixed lines
- `SelectionMenu` class renders arrow-key menus into the scroll buffer
- Theme engine (JSON files, global palette vars)
- Async throughout (`asyncio`, `prompt_toolkit` async app loop)

## Decision: Stay on prompt_toolkit

Do NOT rewrite in curses or switch to Textual. Reasons:

- Rewriting would discard the lexer, marker system, theme engine, float layer,
  async support, and mouse support — months of existing work.
- `prompt_toolkit.widgets` already ships `Dialog`, `Button`, `TextArea`,
  `RadioList`, `CheckboxList`, `Frame` — everything needed.
- Modal dialogs are just larger `Float` objects in `_active_floats`, the same
  pattern already used for toast notifications.
- Multi-buffer + tabs fit naturally into the existing `Buffer` / `BufferControl`
  architecture.

## Features to Implement

### 1. Buttons

**Library:** `prompt_toolkit.widgets.Button`

```python
from prompt_toolkit.widgets import Button
btn = Button("OK", handler=on_ok)
```

Buttons are composed inside `Dialog` or `HSplit`/`VSplit` layouts. Style them via
the existing `Style` dict in `build_style()`.

---

### 2. Text Fields

**Library:** `prompt_toolkit.widgets.TextArea` (already imported)

- Single-line: `TextArea(multiline=False, ...)`
- Multiline: `TextArea(multiline=True, ...)`

The existing `input_area` at the bottom is already a `TextArea`. New instances can
be embedded inside dialogs.

---

### 3. Dialogs

**Library:** `prompt_toolkit.widgets.Dialog`

A dialog is a `Float` wrapping a `Dialog` widget, appended to `_active_floats`.

```python
from prompt_toolkit.widgets import Dialog, Button, TextArea

def show_dialog(app, title, body, buttons):
    dlg = Dialog(title=title, body=body, buttons=buttons)
    f = Float(content=dlg, xcursor=True, ycursor=True)
    _active_floats.append(f)
    app.layout.focus(dlg)
    app.invalidate()

def close_dialog(app, f):
    _active_floats.remove(f)
    app.layout.focus(input_area)
    app.invalidate()
```

Style the dialog chrome via new entries in `build_style()`:
`"dialog"`, `"dialog.body"`, `"dialog frame.label"`, `"button"`,
`"button.focused"`.

---

### 4. Wizards

A wizard is a sequence of `Dialog` floats shown one at a time. Each dialog's
confirm button callback dismisses the current float and shows the next one.

Pattern:

```python
steps = [step1_dialog, step2_dialog, step3_dialog]

def advance(idx, result):
    close_dialog(steps[idx])
    if idx + 1 < len(steps):
        show_dialog(steps[idx + 1])
    else:
        on_wizard_complete(collected_results)
```

This is the same async callback pattern used by the existing `SelectionMenu`.

The `/setup` wizard (provider/model/role/theme selection) is a candidate for
conversion to this pattern.

---

### 5. Tab Bar + Multi-Buffer (vim-style tabs)

#### Data model

```python
class Tab:
    name: str          # display label
    buffer: Buffer     # prompt_toolkit Buffer instance
    read_only: bool    # True for output tabs

class TabManager:
    tabs: list[Tab]
    active: int        # index of focused tab

    def new_tab(name, read_only=True) -> Tab
    def close_tab(index)
    def next_tab()       # gt
    def prev_tab()       # gT
    def goto_tab(n)      # 1-9
    def active_buffer() -> Buffer
```

#### Tab bar rendering

A new `Window` between the top bar and `body_window`, rendered via
`FormattedTextControl`:

```
 ╭─[ Chat ]──[ Tool Output ]──[ Scratch ]─────────╮
```

Active tab is highlighted with `ACCENT_1`; inactive tabs use `MUTED`.
Rendered as `FormattedText` fragments, same pattern as `get_top_bar()` and
`get_bot_bar()`.

#### Layout change

```python
base_container = HSplit([
    top_bar,
    tab_bar_window,    # NEW — Window with FormattedTextControl
    body_window,       # body_window swaps BufferControl on tab switch
    bot_bar,
    input_area,
])
```

`body_window` needs to use a `DynamicContainer` or have its content replaced when
the active tab changes.

Simplest approach: rebuild `body_window` with a new `BufferControl` pointing at
`tab_mgr.active_buffer()` and call `app.layout = Layout(...)` on switch. Or use a
wrapper `DynamicContainer(lambda: current_body_window)`.

#### Key bindings to add

| Key | Action |
|-----|--------|
| `g t` (sequence) or `Ctrl+Right` | Next tab |
| `g T` (sequence) or `Ctrl+Left`  | Previous tab |
| `1`…`9` (with modifier, e.g. `Alt+N`) | Jump to tab N |
| `Ctrl+T` | New scratch tab |
| `Ctrl+W` | Close current tab |

#### Predefined tabs (suggested)

| # | Name | Buffer | Notes |
|---|------|--------|-------|
| 1 | Chat | `main_buffer` | existing conversation |
| 2 | Tool Output | new buffer | tool call results |
| 3 | Logs | new buffer | debug/observability output |
| 4+ | Scratch | new buffer | user-created, editable |

---

## Target Layout (after all features)

```
╭─ top bar ──────────────────────────────────────────╮
│ DAVYCLI v0.1.0  session-xxxx  openai  gpt-4o       │
╰────────────────────────────────────────────────────╯
 ╭─[ Chat ]──[ Tool Output ]──[ Logs ]───────────────╮   ← tab bar
 │                                                    │
 │  (active buffer — read-only or editable)           │
 │                                                    │
 ╰────────────────────────────────────────────────────╯
╭─ bottom bar ───────────────────────────────────────╮
│ AI: idle │ PgUp/PgDn scroll │ /setup │ EXECUTION   │
╰────────────────────────────────────────────────────╯
❯❯ _
```

Modal dialog floats over the layout when active (centered, focused).

---

## Implementation Order (suggested)

1. **Dialogs + Buttons** — lower risk, self-contained, useful immediately for
   `/setup` wizard and confirmation prompts.
2. **Wizards** — refactor `/setup` to use the new dialog stack.
3. **Tab bar + TabManager** — adds `tab_bar_window` to `HSplit`, wires `gt`/`gT`.
4. **Multi-buffer** — swap `body_window` buffer on tab switch; add Tool Output and
   Logs tabs fed by existing event streams.

## Files to Modify

- `davy_cli.py` — layout, key bindings, `build_style()`, dialog helpers, TabManager
- `cli/__init__.py` — can house `TabManager`, dialog helpers as submodules

## Dependencies (no new packages needed)

All features use `prompt_toolkit` which is already installed. No new dependencies.
