#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       cli/dialogs.py
# DESCRIPTION: Floating dialog library for StarryCLI
# SUMMARY: Self-contained floating dialogs that
#          integrate with FloatContainer via init().
#          Provides input, menu, toggle, and button
#          dialogs with theme colors and focus
#          trapping.
# NOTES: Call dialogs.init(rebuild_fn) once after
#        NotificationManager is created. Nav
#        dialogs use per-control key_bindings for
#        Up/Down/Enter/Space so they compose well
#        with global bindings.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/30/2026    bsdero    Initial implementation
"""Floating dialog library for StarryCLI."""

import shutil
import textwrap
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import (
    KeyBindings,
)
from prompt_toolkit.layout.containers import (
    Float,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import (
    FormattedTextControl,
)
from prompt_toolkit.layout.dimension import (
    Dimension,
)
from prompt_toolkit.mouse_events import (
    MouseEventType,
)
from prompt_toolkit.widgets import (
    Button,
    TextArea,
)

# Box-drawing characters
TL = "╭"
TR = "╮"
BL = "╰"
BR = "╯"
HZ = "─"
VT = "│"

# CSS class names — must match build_style()
_SF = "class:line.aframe"    # frame / border
_SC = "class:line.acontent"  # body text
_SH = "class:line.header"    # title / selected item
_SD = "class:dialog"         # dialog background


# ──────────────────────────────────────────────
# Module state
# ──────────────────────────────────────────────

# Active dialog Floats (shared with FloatContainer
# via _rebuild_fn + get_floats()).
_floats: list = []

# Stack: (Float, cancel_fn, _NavState | None)
_dialog_stack: list = []

# Called after every push/pop to sync _active_floats.
_rebuild_fn = None


class _NavState:
    """Selection state for menu / toggle dialogs."""

    def __init__(self, options, toggles=False):
        self.options = list(options)
        self.selected = 0
        self.scroll_offset = 0
        self.toggles = toggles
        self.checked = (
            [False] * len(options)
            if toggles else []
        )

    def move_up(self):
        if self.selected > 0:
            self.selected -= 1

    def move_down(self):
        n = len(self.options)
        if self.selected < n - 1:
            self.selected += 1

    def toggle(self):
        if self.toggles:
            i = self.selected
            self.checked[i] = (
                not self.checked[i]
            )

    def checked_indices(self):
        return [
            i for i, v
            in enumerate(self.checked) if v
        ]


# ──────────────────────────────────────────────
# Public helpers
# ──────────────────────────────────────────────

def init(rebuild_fn):
    """Wire the library to davy_cli's rebuild_fn.

    Call once after NotificationManager is created:
      _dlg.init(notif_mgr._rebuild_floats)
    """
    global _rebuild_fn
    _rebuild_fn = rebuild_fn


def get_floats() -> list:
    """Return active dialog Floats."""
    return list(_floats)


def is_dialog_active() -> bool:
    return bool(_dialog_stack)


def close_top_dialog(app, refocus=None):
    """Close topmost dialog via its cancel fn."""
    if _dialog_stack:
        _, cancel_fn, _ = _dialog_stack[-1]
        if cancel_fn:
            cancel_fn()
            return
    app.invalidate()


# ──────────────────────────────────────────────
# Internal push / pop
# ──────────────────────────────────────────────

def _push(app, float_obj, cancel_fn, nav=None):
    _floats.append(float_obj)
    _dialog_stack.append(
        (float_obj, cancel_fn, nav)
    )
    if _rebuild_fn:
        _rebuild_fn()
    app.invalidate()


def _pop(app, float_obj, refocus=None):
    if float_obj in _floats:
        _floats.remove(float_obj)
    _dialog_stack[:] = [
        e for e in _dialog_stack
        if e[0] is not float_obj
    ]
    if _rebuild_fn:
        _rebuild_fn()
    if refocus is not None:
        try:
            app.layout.focus(refocus)
        except Exception:
            pass
    app.invalidate()


# ──────────────────────────────────────────────
# Global key bindings
# ──────────────────────────────────────────────

dialog_kb = KeyBindings()


@dialog_kb.add(
    "tab",
    filter=Condition(is_dialog_active),
    eager=True,
)
def _dlg_tab(event):
    event.app.layout.focus_next()


@dialog_kb.add(
    "s-tab",
    filter=Condition(is_dialog_active),
    eager=True,
)
def _dlg_stab(event):
    event.app.layout.focus_previous()


@dialog_kb.add(
    "escape",
    filter=Condition(is_dialog_active),
    eager=True,
)
def _dlg_escape(event):
    if _dialog_stack:
        _, cancel_fn, _ = _dialog_stack[-1]
        if cancel_fn:
            cancel_fn()


# ──────────────────────────────────────────────
# Layout helpers
# ──────────────────────────────────────────────

def _win(frags, h=1, w=None):
    kw = dict(
        content=FormattedTextControl(
            frags,
            show_cursor=False,
            focusable=False,
        ),
        height=h,
        dont_extend_height=True,
        style=_SD,
    )
    if w is not None:
        kw["width"] = w
        kw["dont_extend_width"] = True
    return Window(**kw)


def _top_border(iw, title=""):
    t = f" {title} " if title else ""
    lpad = max(0, (iw - len(t)) // 2)
    rpad = max(0, iw - len(t) - lpad)
    return _win([
        (_SF, TL),
        (_SF, HZ * lpad),
        (_SH, t),
        (_SF, HZ * rpad),
        (_SF, TR),
    ])


def _bot_border(iw):
    return _win([
        (_SF, BL),
        (_SF, HZ * iw),
        (_SF, BR),
    ])


def _pad_row(iw):
    return _win([
        (_SF, VT),
        (_SC, " " * iw),
        (_SF, VT),
    ])


def _label_row(iw, text, center=False):
    pad = (
        text.center(iw) if center
        else f" {text}".ljust(iw)
    )
    return _win([
        (_SF, VT),
        (_SC, pad[:iw]),
        (_SF, VT),
    ])


def _inner_top(iw, fiw, margin):
    return _win([
        (_SF, VT),
        (_SC, " " * margin),
        (_SF, f"{TL}{HZ * fiw}{TR}"),
        (_SC, " " * margin),
        (_SF, VT),
    ])


def _inner_bot(iw, fiw, margin):
    return _win([
        (_SF, VT),
        (_SC, " " * margin),
        (_SF, f"{BL}{HZ * fiw}{BR}"),
        (_SC, " " * margin),
        (_SF, VT),
    ])


def _vt_win(h=1):
    text = "\n".join([VT] * h)
    return Window(
        content=FormattedTextControl(
            [(_SF, text)],
            show_cursor=False,
            focusable=False,
        ),
        width=1,
        dont_extend_width=True,
        height=h,
        dont_extend_height=True,
        style=_SD,
    )


def _flex():
    return Window(
        content=FormattedTextControl(
            "",
            show_cursor=False,
            focusable=False,
        ),
        width=Dimension(weight=1),
        style=_SD,
    )


def _gap(n=2, h=1):
    text = "\n".join([" " * n] * h)
    return Window(
        content=FormattedTextControl(
            [(_SC, text)],
            show_cursor=False,
            focusable=False,
        ),
        width=n,
        dont_extend_width=True,
        height=h,
        dont_extend_height=True,
        style=_SD,
    )


def _wrap_text(text, usable_w):
    """Wrap text into lines ≤ usable_w chars.

    Splits on existing newlines first, then
    wraps each paragraph with textwrap.
    Empty paragraphs become empty strings.
    """
    result = []
    for para in text.split("\n"):
        if not para:
            result.append("")
        elif len(para) <= usable_w:
            result.append(para)
        else:
            result.extend(
                textwrap.wrap(para, usable_w)
                or [""]
            )
    return result


def _label_rows(iw, text):
    """Wrapped _label_row windows for text.

    Returns one Window per wrapped line so
    long labels flow naturally inside dialogs.
    """
    usable = iw - 2
    lines = _wrap_text(text, usable)
    return [
        _label_row(iw, ln) for ln in lines
    ]


def _auto_width(options, title, extra=0):
    """Auto-compute dialog width from content.

    extra: extra chars per option beyond the
           option text itself (e.g. 4 for the
           toggle mark "[✓] ").
    Minimum 40; capped at terminal width - 4.
    """
    cols = shutil.get_terminal_size().columns
    max_opt = max(
        (len(o) for o in options),
        default=0,
    )
    # nav prefix 3 chars + VT borders 2 chars
    from_opts = max_opt + extra + 5
    # " title " centered + 2 HZ chars each side
    from_title = len(title) + 6
    desired = max(from_opts, from_title, 40)
    return min(desired, cols - 4)


def _make_btn_row(iw, buttons):
    """Centered button row with VT borders."""
    parts = [_vt_win(), _flex()]
    for i, b in enumerate(buttons):
        if i > 0:
            parts.append(_gap(2))
        parts.append(b)
    parts += [_flex(), _vt_win()]
    return VSplit(parts, style=_SD)


def _centered_float(container, width, height):
    cols = shutil.get_terminal_size().columns
    rows = shutil.get_terminal_size().lines
    return Float(
        content=container,
        left=max(0, (cols - width) // 2),
        top=max(2, (rows - height) // 2),
    )


def _btn(text, handler, width=12):
    return Button(
        text,
        handler=handler,
        width=width,
        left_symbol="[",
        right_symbol="]",
    )


# ──────────────────────────────────────────────
# show_input_dialog
# ──────────────────────────────────────────────

def show_input_dialog(
    app,
    title,
    label,
    on_confirm,
    on_cancel=None,
    multiline=False,
    width=64,
    refocus=None,
    field_height=None,
    initial_text="",
):
    """Single or multiline text input dialog.

    on_confirm(text: str) — called with stripped text.
    on_cancel()           — optional, called on cancel.
    multiline=True        — enables multiline TextArea.
    initial_text          — pre-fills the field.
    """
    f_ref = [None]
    iw = width - 2
    margin = 2
    fiw = iw - margin * 2 - 2
    fh = field_height or (5 if multiline else 1)

    field = TextArea(
        multiline=multiline,
        scrollbar=multiline,
        focusable=True,
        style="class:text-area",
        height=fh,
        text=initial_text,
    )

    def _confirm():
        text = field.text.strip()
        _pop(app, f_ref[0], refocus)
        if on_confirm:
            on_confirm(text)

    def _cancel():
        _pop(app, f_ref[0], refocus)
        if on_cancel:
            on_cancel()

    if not multiline:
        field.accept_handler = (
            lambda _: _confirm()
        )

    rows = [_top_border(iw, title), _pad_row(iw)]
    lbl_wins = _label_rows(iw, label) if label else []
    if lbl_wins:
        rows += lbl_wins + [_pad_row(iw)]
    rows += [
        _inner_top(iw, fiw, margin),
        VSplit([
            _vt_win(fh), _gap(margin, fh),
            _vt_win(fh), field,
            _vt_win(fh), _gap(margin, fh),
            _vt_win(fh),
        ], style=_SD),
        _inner_bot(iw, fiw, margin),
        _pad_row(iw),
        _make_btn_row(iw, [
            _btn(" Cancel ", _cancel, 12),
            _btn(" Submit ", _confirm, 12),
        ]),
        _pad_row(iw),
        _bot_border(iw),
    ]

    n_lbl = len(lbl_wins)
    container = HSplit(rows, style=_SD, width=width)
    h = 8 + fh + (n_lbl + 1 if n_lbl else 0)
    fl = _centered_float(container, width, h)
    f_ref[0] = fl
    _push(app, fl, _cancel)
    app.layout.focus(field)


# ──────────────────────────────────────────────
# show_menu_dialog
# ──────────────────────────────────────────────

def show_menu_dialog(
    app,
    title,
    options,
    on_select,
    on_cancel=None,
    width=None,
    refocus=None,
    max_visible=None,
):
    """Floating arrow-key navigable menu dialog.

    on_select(index: int) — called with chosen index.
    on_cancel()           — optional.
    max_visible           — cap visible rows; adds
                            scroll indicators when
                            the list is longer.
    Keys: Up/Down navigate, Enter selects, Escape
    cancels.
    """
    f_ref = [None]
    if width is None:
        width = _auto_width(options, title)
    ns = _NavState(options)
    iw = width - 2
    mv = max_visible  # None = no cap

    def _confirm():
        idx = ns.selected
        _pop(app, f_ref[0], refocus)
        if on_select:
            on_select(idx)

    def _cancel():
        _pop(app, f_ref[0], refocus)
        if on_cancel:
            on_cancel()

    nav_kb = KeyBindings()

    @nav_kb.add("up")
    def _up(event):
        ns.move_up()
        if mv is not None:
            if ns.selected < ns.scroll_offset:
                ns.scroll_offset = ns.selected
        event.app.invalidate()

    @nav_kb.add("down")
    def _down(event):
        ns.move_down()
        if mv is not None:
            if ns.selected >= (
                ns.scroll_offset + mv
            ):
                ns.scroll_offset = (
                    ns.selected - mv + 1
                )
        event.app.invalidate()

    @nav_kb.add("enter")
    def _enter(event):
        _confirm()

    def _render():
        frags = []
        if mv is None:
            # No scroll cap — render all items
            for i, opt in enumerate(options):
                def _click(me, idx=i):
                    if me.event_type == (
                        MouseEventType.MOUSE_UP
                    ):
                        ns.selected = idx
                        _confirm()
                pfx = (
                    " ▶ " if i == ns.selected
                    else "   "
                )
                text = (
                    f"{pfx}{opt}".ljust(iw)[:iw]
                )
                st = (
                    _SH if i == ns.selected
                    else _SC
                )
                frags += [
                    (_SF, VT),
                    (st, text, _click),
                    (_SF, VT + "\n"),
                ]
        else:
            off = ns.scroll_offset
            vis = options[off:off + mv]
            n_above = off
            n_below = max(
                0,
                len(options) - off - mv,
            )
            # Top scroll indicator row
            if n_above > 0:
                ind = (
                    f"  ↑ {n_above} more above"
                )
                frags += [
                    (_SF, VT),
                    (
                        _SC,
                        ind.ljust(iw)[:iw],
                    ),
                    (_SF, VT + "\n"),
                ]
            else:
                frags += [
                    (_SF, VT),
                    (_SC, " " * iw),
                    (_SF, VT + "\n"),
                ]
            # Visible items
            for i, opt in enumerate(vis):
                ai = i + off  # actual index
                def _click(me, idx=ai):
                    if me.event_type == (
                        MouseEventType.MOUSE_UP
                    ):
                        ns.selected = idx
                        _confirm()
                pfx = (
                    " ▶ " if ai == ns.selected
                    else "   "
                )
                text = (
                    f"{pfx}{opt}".ljust(iw)[:iw]
                )
                st = (
                    _SH if ai == ns.selected
                    else _SC
                )
                frags += [
                    (_SF, VT),
                    (st, text, _click),
                    (_SF, VT + "\n"),
                ]
            # Bottom scroll indicator row
            if n_below > 0:
                ind = (
                    f"  ↓ {n_below} more below"
                )
                frags += [
                    (_SF, VT),
                    (
                        _SC,
                        ind.ljust(iw)[:iw],
                    ),
                    (_SF, VT + "\n"),
                ]
            else:
                frags += [
                    (_SF, VT),
                    (_SC, " " * iw),
                    (_SF, VT + "\n"),
                ]
        return frags

    nav_h = (
        len(options)
        if mv is None
        else min(len(options), mv) + 2
    )
    nav_ctrl = FormattedTextControl(
        _render,
        show_cursor=False,
        focusable=True,
        key_bindings=nav_kb,
    )
    nav_win = Window(
        content=nav_ctrl,
        height=nav_h,
        dont_extend_height=True,
        style=_SD,
    )

    rows = [
        _top_border(iw, title),
        _pad_row(iw),
        nav_win,
        _pad_row(iw),
        _make_btn_row(iw, [
            _btn(" Cancel ", _cancel, 12),
            _btn(" Select ", _confirm, 12),
        ]),
        _pad_row(iw),
        _bot_border(iw),
    ]
    container = HSplit(rows, style=_SD, width=width)
    h = 7 + nav_h
    fl = _centered_float(container, width, h)
    f_ref[0] = fl
    _push(app, fl, _cancel, nav=ns)
    app.layout.focus(nav_win)


# ──────────────────────────────────────────────
# show_toggle_dialog
# ──────────────────────────────────────────────

def show_toggle_dialog(
    app,
    title,
    items,
    on_confirm,
    on_cancel=None,
    width=None,
    refocus=None,
    initial_checked=None,
    max_visible=None,
):
    """Floating toggle-list dialog.

    on_confirm(checked: list[int]) — indices of
        checked items.
    on_cancel()       — optional.
    initial_checked   — list[int] of pre-checked
        indices.
    max_visible       — cap visible rows; adds
        scroll indicators for longer lists.
    Keys: Up/Down navigate, Space or T toggles,
          Escape cancels. OK button confirms.
    """
    f_ref = [None]
    if width is None:
        # extra=4: "[✓] " mark (3) + space (1)
        width = _auto_width(items, title, 4)
    ns = _NavState(items, toggles=True)
    if initial_checked:
        for i in initial_checked:
            if 0 <= i < len(items):
                ns.checked[i] = True
    iw = width - 2
    mv = max_visible

    def _confirm():
        checked = ns.checked_indices()
        _pop(app, f_ref[0], refocus)
        if on_confirm:
            on_confirm(checked)

    def _cancel():
        _pop(app, f_ref[0], refocus)
        if on_cancel:
            on_cancel()

    nav_kb = KeyBindings()

    @nav_kb.add("up")
    def _up(event):
        ns.move_up()
        if mv is not None:
            if ns.selected < ns.scroll_offset:
                ns.scroll_offset = ns.selected
        event.app.invalidate()

    @nav_kb.add("down")
    def _down(event):
        ns.move_down()
        if mv is not None:
            if ns.selected >= (
                ns.scroll_offset + mv
            ):
                ns.scroll_offset = (
                    ns.selected - mv + 1
                )
        event.app.invalidate()

    @nav_kb.add(" ")
    @nav_kb.add("t")
    def _toggle(event):
        ns.toggle()
        event.app.invalidate()

    def _render():
        frags = []
        if mv is None:
            for i, item in enumerate(items):
                def _click(me, idx=i):
                    if me.event_type == (
                        MouseEventType.MOUSE_UP
                    ):
                        ns.selected = idx
                        ns.toggle()
                        app.invalidate()
                pfx = (
                    " ▶ " if i == ns.selected
                    else "   "
                )
                mark = (
                    "[✓]" if ns.checked[i]
                    else "[✗]"
                )
                text = (
                    f"{pfx}{mark} {item}"
                ).ljust(iw)[:iw]
                st = (
                    _SH if i == ns.selected
                    else _SC
                )
                frags += [
                    (_SF, VT),
                    (st, text, _click),
                    (_SF, VT + "\n"),
                ]
        else:
            off = ns.scroll_offset
            vis_items = items[off:off + mv]
            n_above = off
            n_below = max(
                0, len(items) - off - mv,
            )
            # Top indicator
            if n_above > 0:
                ind = (
                    f"  ↑ {n_above} more above"
                )
                frags += [
                    (_SF, VT),
                    (
                        _SC,
                        ind.ljust(iw)[:iw],
                    ),
                    (_SF, VT + "\n"),
                ]
            else:
                frags += [
                    (_SF, VT),
                    (_SC, " " * iw),
                    (_SF, VT + "\n"),
                ]
            for i, item in enumerate(vis_items):
                ai = i + off
                def _click(me, idx=ai):
                    if me.event_type == (
                        MouseEventType.MOUSE_UP
                    ):
                        ns.selected = idx
                        ns.toggle()
                        app.invalidate()
                pfx = (
                    " ▶ " if ai == ns.selected
                    else "   "
                )
                mark = (
                    "[✓]" if ns.checked[ai]
                    else "[✗]"
                )
                text = (
                    f"{pfx}{mark} {item}"
                ).ljust(iw)[:iw]
                st = (
                    _SH if ai == ns.selected
                    else _SC
                )
                frags += [
                    (_SF, VT),
                    (st, text, _click),
                    (_SF, VT + "\n"),
                ]
            # Bottom indicator
            if n_below > 0:
                ind = (
                    f"  ↓ {n_below} more below"
                )
                frags += [
                    (_SF, VT),
                    (
                        _SC,
                        ind.ljust(iw)[:iw],
                    ),
                    (_SF, VT + "\n"),
                ]
            else:
                frags += [
                    (_SF, VT),
                    (_SC, " " * iw),
                    (_SF, VT + "\n"),
                ]
        return frags

    nav_h = (
        len(items)
        if mv is None
        else min(len(items), mv) + 2
    )
    nav_ctrl = FormattedTextControl(
        _render,
        show_cursor=False,
        focusable=True,
        key_bindings=nav_kb,
    )
    nav_win = Window(
        content=nav_ctrl,
        height=nav_h,
        dont_extend_height=True,
        style=_SD,
    )

    rows = [
        _top_border(iw, title),
        _pad_row(iw),
        nav_win,
        _pad_row(iw),
        _make_btn_row(iw, [
            _btn(" Cancel ", _cancel, 12),
            _btn("  OK  ", _confirm, 10),
        ]),
        _pad_row(iw),
        _bot_border(iw),
    ]
    container = HSplit(rows, style=_SD, width=width)
    h = 7 + nav_h
    fl = _centered_float(container, width, h)
    f_ref[0] = fl
    _push(app, fl, _cancel, nav=ns)
    app.layout.focus(nav_win)


# ──────────────────────────────────────────────
# show_button_dialog
# ──────────────────────────────────────────────

def show_button_dialog(
    app,
    title,
    message,
    buttons,
    on_button,
    on_cancel=None,
    width=64,
    refocus=None,
):
    """Dialog with a message and N labeled buttons.

    buttons   — list[str] button labels.
    on_button(index: int) — called with button index.
    on_cancel()           — optional, called on Escape.
    """
    f_ref = [None]
    iw = width - 2

    def _cancel():
        _pop(app, f_ref[0], refocus)
        if on_cancel:
            on_cancel()

    btn_widgets = []
    for i, lbl in enumerate(buttons):
        def _make_h(idx=i):
            def _h():
                _pop(app, f_ref[0], refocus)
                if on_button:
                    on_button(idx)
            return _h
        btn_widgets.append(
            _btn(lbl, _make_h(), len(lbl) + 4)
        )

    raw_lines = message.splitlines() or [""]
    msg_lines = []
    for ln in raw_lines:
        msg_lines.extend(
            _wrap_text(ln, iw - 2) or [""]
        )
    if not msg_lines:
        msg_lines = [""]
    rows = [_top_border(iw, title), _pad_row(iw)]
    for line in msg_lines:
        rows.append(_label_row(iw, line))
    rows += [
        _pad_row(iw),
        _make_btn_row(iw, btn_widgets),
        _pad_row(iw),
        _bot_border(iw),
    ]
    container = HSplit(rows, style=_SD, width=width)
    h = 7 + len(msg_lines)
    fl = _centered_float(container, width, h)
    f_ref[0] = fl
    _push(app, fl, _cancel)
    if btn_widgets:
        app.layout.focus(btn_widgets[0])
