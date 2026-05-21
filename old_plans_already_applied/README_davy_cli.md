# DavyAgent TUI

A classic, high-fidelity Terminal User Interface for the
**DavyAgent** agentic AI tool. Built entirely with
`prompt_toolkit`, featuring a Tokyo Night color palette,
TrueColor rendering, real LLM streaming with markdown
support, native tool calling, floating notifications,
inline alerts, and an interactive selection menu.

---

## Screenshots

```
╭──────────────────────────────────────────────────╮
│ A C T O R 💠  v0.1.0-alpha │ sess_a1b2 │ CPU ██ │
╰──────────────────────────────────────────────────╯
 ╭─ User Command [16:30:42] ─────────────────────╮
 │ ❯❯ analyze the infrastructure                 │
 ╰───────────────────────────────────────────────-╯
 ╭─ ✦ DavyAgent Insight ─────────────────────────╮
 │                                                │
 │ ✦ Análisis Completo                            │
 │ ──────────────────                             │
 │                                                │
 │   He revisado los logs del sistema e           │
 │   identifiqué **3 anomalías** en los           │
 │   patrones de tráfico.                         │
 │                                                │
 ╰────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────╮
│ AI: IDLE │ PgUp/PgDn scroll │ Ctrl-C quit │ ... │
╰──────────────────────────────────────────────────╯
 ❯❯ _
```

---

## Features

- **Three-tier framed layout**: top bar (telemetry),
  scrollable body (conversation), bottom bar (status),
  input prompt — all with rounded Unicode frames
- **Tokyo Night theme**: full 24-bit TrueColor palette
  with no hardcoded colors — everything uses named
  palette variables
- **Multicolor markdown rendering**: headers, bold,
  italic, inline code, fenced code blocks, bullets,
  and numbered lists — all styled with different colors
  inside AI response frames
- **Frame border coloring**: left/right `│` borders
  match top/bottom `─` border colors on every frame
  type (orange for user, blue for AI, white for alerts)
- **Word-wrapped content**: both AI responses and long
  user commands wrap cleanly inside their frames
- **Real LLM streaming**: connects to DavyAgent library
  and streams tokens from any OpenAI-compatible provider
- **Native tool calling**: LLM tool calls displayed as
  warning frames; results shown as inline notifications
- **Execution modes**: toggle between `plan` (read-only
  research) and `execution` (full read/write/run) with
  Ctrl+P; mode shown in the status bar
- **Role switching**: change agent role mid-session via
  `/role` command; active role shown in the top bar
- **Provider & model switching**: `/setup` walks through
  provider → model → role selection interactively
- **Floating notifications**: toast popups in the
  top-right corner that auto-dismiss
- **Inline alert notifications**: white-framed alerts
  embedded in the scroll buffer
- **Interactive selection menus**: arrow-key navigable
  option picker with highlighted selection
- **Mouse wheel scroll**: works immediately without
  needing to focus the scroll area first
- **Dynamic frame widths**: all frames resize to the
  terminal width automatically

---

## Requirements

- Python 3.11+
- `prompt_toolkit` >= 3.0
- `davyagent` library (same repo)
- `psutil` (for CPU telemetry)

---

## Installation

```bash
# Developer install (editable, includes test deps)
pip install -e ".[dev]"

# Copy and configure .env
cp .env.example .env
# Set DAVY_API_KEY and/or OPENWEBUI_API_KEY

# Run the TUI
python davy_cli.py
```

---

## Usage

### Commands

| Command           | Description                              |
|-------------------|------------------------------------------|
| `<any text>`      | Send message to DavyAgent LLM            |
| `/help`           | Show available commands                  |
| `/clear`          | Clear the scroll buffer                  |
| `/exit`           | Shut down DavyAgent                      |
| `/setup`          | Interactive provider → model → role flow |
| `/mode`           | Switch between plan / execution modes    |
| `/role`           | Switch agent role mid-session            |

### Keyboard Shortcuts

| Shortcut      | Action                                   |
|---------------|------------------------------------------|
| `Ctrl+C`      | Quit                                     |
| `PgUp/PgDn`   | Scroll buffer up/down                    |
| `Mouse wheel` | Scroll buffer (works globally)           |
| `Ctrl+P`      | Toggle plan / execution mode             |
| `↑/↓`         | Navigate selection menu (when active)    |
| `Enter`       | Confirm menu selection                   |

---

## Architecture

### File Structure

```
davy_cli.py         — TUI application (prompt_toolkit)
davyagent/          — Library: AgentPool, Session, tools
config/default.toml — Provider and agent configuration
.env                — API keys (gitignored)
```

### Core Design: Marker-Based Line Styling

The scrollable body uses a `prompt_toolkit` `Buffer` +
`BufferControl` for native scroll support. Each line in
the buffer starts with a **2-character marker prefix**
that is invisible to the user:

| Marker | Style Class        | Visual Use               |
|--------|--------------------|--------------------------|
| `Uf`   | `line.uframe`      | User frame border (orange)|
| `Uc`   | `line.ucontent`    | User command text (orange)|
| `Uw`   | `line.utext`       | User secondary text (white)|
| `Af`   | `line.aframe`      | AI frame border (blue)    |
| `Ac`   | `line.acontent`    | AI normal text            |
| `Ah`   | `line.header`      | Markdown headers (cyan)   |
| `Ab`   | `line.bold`        | Bold text (fuchsia)       |
| `Ak`   | `line.code`        | Code blocks (lime)        |
| `Al`   | `line.bullet`      | Bullets/lists (cyan)      |
| `At`   | `line.think`       | Thinking spinner (fuchsia)|
| `Mx`   | *(multi-fragment)* | Inline styled spans       |
| `Nf`   | `line.nframe`      | Notification frame (white)|
| `Nc`   | `line.ncontent`    | Notification text (white) |
| `Pl`   | `line.plain`       | Plain text                |
| `Dm`   | `line.dim`         | Dim/muted text            |

**How it works:**

1. `FrameLexer.lex_document()` reads each line's 2-char
   marker and returns styled fragments
2. For content lines inside frames, `_split_borders()`
   splits the `│` border characters into separate
   fragments with the frame's color, while the inner
   content keeps its own style
3. `MarkerStripProcessor.apply_transformation()` removes
   the 2-char marker prefix before display, preserving
   the lexer's style assignments
4. For `Mx` (multi-color) lines, inline style spans use
   `\x01<code>\x02<text>\x01` delimiters parsed by
   `_parse_inner_spans()`

### Inline Style Span Codes

| Code | Style Class    | Color          |
|------|--------------- |----------------|
| `B`  | `span.bold`    | Fuchsia bold   |
| `C`  | `span.code`    | Lime on dark   |
| `I`  | `span.italic`  | Italic silver  |
| `L`  | `span.light`   | Cyan           |
| `O`  | `span.orange`  | Orange bold    |
| `W`  | `span.white`   | White          |
| `D`  | `span.dim`     | Dim gray       |
| `G`  | `span.lime`    | Lime green     |

### Color Palette (Tokyo Night)

All colors are defined as module-level constants
and referenced by name throughout the style dict.
**No hex values are hardcoded in style definitions.**

```python
BG_DEEP       = "#0f141e"   # Deep background
BG_PANEL      = "#1e253c"   # Panel/bar background
BG_SCROLL     = "#121629"   # Scroll area background
BORDER        = "#3d59a1"   # Frame borders (blue)
TEXT          = "#c0caf5"   # Default text (silver)
SYS_TEXT      = "#ff9e64"   # System/labels (orange)
ACCENT_LIME   = "#9ece6a"   # Code/success (lime)
ACCENT_FUCHSIA= "#bb9af7"   # Emphasis (fuchsia)
LIGHT_TEXT    = "#7dcfff"   # Headers/bullets (cyan)
CODE_INL_BG   = "#161b22"   # Code background
MUTED         = "#565f89"   # Muted elements
DIM_TEXT      = "#7982a9"   # Dim text
WHITE         = "#e0e0e0"   # Bright text/notifs
```

### Component Map

```
┌─────────────────────────────────────────────┐
│ main()                                      │
│   ├─ da.load_settings()                     │
│   ├─ da.AgentPool(settings)                 │
│   ├─ pool.spawn(mode="execution")           │
│   └─ app.run_async()                        │
│                                             │
│ create_app()                                │
│   └─ FloatContainer                         │
│       ├─ HSplit (base_container)            │
│       │   ├─ top_bar    (provider/role/CPU) │
│       │   ├─ body_window (BufferControl)    │
│       │   │   ├─ FrameLexer                 │
│       │   │   ├─ MarkerStripProcessor       │
│       │   │   └─ _body_mouse_handler        │
│       │   ├─ bot_bar    (mode/status/hints) │
│       │   └─ input_area (TextArea)          │
│       └─ _active_floats (notifications)     │
│                                             │
│ setup_input_handler(app)                    │
│   └─ accept_handler (dispatches commands)   │
│       ├─ /setup → _show_setup()             │
│       ├─ /mode  → mode selection menu       │
│       ├─ /role  → _show_change_role()       │
│       └─ <text> → handle_ai_response()      │
│                                             │
│ handle_ai_response(app, user_input)         │
│   ├─ session.mode = _exec_mode              │
│   ├─ session.chat_auto(user_input)          │
│   ├─ token    → streaming into AI frame     │
│   ├─ tool_call  → warning frame             │
│   ├─ tool_result → inline notification      │
│   └─ done      → render final response      │
│                                             │
│ Background tasks:                           │
│   └─ telemetry_refresh()  (2s interval)     │
└─────────────────────────────────────────────┘
```

---

## Execution Modes

The TUI exposes two execution modes that control which
tools are sent to the LLM:

| Mode | Tools available |
|------|----------------|
| `plan` | `todowrite` `task` `question` `webfetch` `skill` `glob` `grep` `read` |
| `execution` | All plan tools + `bash` `edit` `write` |

Switch modes at any time:
- **Ctrl+P** — toggle between plan and execution
- **`/mode`** — pick from a selection menu

The current mode is shown in the status bar. The session
starts in `execution` mode by default.

---

## Customization

### Theme

All colors are in the module-level palette constants.
Change them to switch themes:

```python
# Example: Solarized Dark
BG_DEEP       = "#002b36"
BG_PANEL      = "#073642"
BG_SCROLL     = "#002b36"
BORDER        = "#268bd2"
TEXT          = "#839496"
SYS_TEXT      = "#cb4b16"
ACCENT_LIME   = "#859900"
ACCENT_FUCHSIA= "#d33682"
LIGHT_TEXT    = "#2aa198"
```

The `APP_STYLE` dict references these variables via
f-strings, so changing the constants changes the
entire theme.

### Custom Frame Types

To add a new frame type (e.g., "warning"):

1. Define a new marker:
   ```python
   M_WFRAME = "Wf"
   M_WCONTENT = "Wc"
   ```

2. Add to `MARKER_STYLE`:
   ```python
   M_WFRAME: "class:line.wframe",
   M_WCONTENT: "class:line.wcontent",
   ```

3. Add styles to `APP_STYLE`:
   ```python
   "line.wframe": f"{SYS_TEXT}",
   "line.wcontent": f"{SYS_TEXT}",
   ```

4. Add the set check in `FrameLexer.get_line()`:
   ```python
   if marker in _WARNING_CONTENT_MARKERS:
       return _split_borders(
           line, marker, _FRAME_STYLE_WARNING,
       )
   ```

5. Build a frame function following the pattern
   in `build_user_frame()` or `build_ai_frame()`.

### Key API Functions

| Function                          | Purpose                    |
|-----------------------------------|----------------------------|
| `append_text(text)`               | Add text to scroll buffer  |
| `replace_last_block(n, text)`     | Replace last N lines       |
| `build_user_frame(cmd)`           | Orange user command frame  |
| `build_ai_frame(markdown)`        | Blue AI response frame     |
| `build_thinking_frame(spinner)`   | Thinking spinner frame     |
| `build_inline_notif(msg)`         | White inline alert frame   |
| `notif_mgr.notify(msg, secs)`     | Floating toast popup       |
| `sel_menu.show(title, opts, cb)`  | Selection menu             |
| `_inline(text)`                   | Markdown → style spans     |
| `_wrap_text(text, width)`         | Word-wrap with style spans |
| `_pad_line(text, width)`          | Pad to exact width         |

---

## License

Proprietary. See LICENSE for terms.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Keep all lines under 79 characters
4. Use the palette variables — never hardcode hex
5. Add markers for any new styled line types
6. Test with `python -c "import ast; ast.parse(...)"`
7. Submit a pull request
