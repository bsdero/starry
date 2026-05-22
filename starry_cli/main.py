#!/usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:        davy_cli.py
# DESCRIPTION: StarryCLI Terminal User Interface
# SUMMARY: TUI for the StarryCLI agentic AI tool.
#          Integrates with the starry_lib library for
#          real LLM streaming. Features Tokyo Night
#          palette, markdown rendering, /setup command
#          for runtime provider/model switching, and
#          error/warning inline frames.
# NOTES: Requires starry_lib library and .env with
#        provider API keys.
#
# BACKLOG:
# Date m/d/Y    Engineer    Summary
# 04/16/2026    bsdero      Library integration,
#                           /setup command,
#                           error/warning frames,
#                           hash-based session ID
# 05/05/2026    bsdero      /stats command,
#                           Provider submenu (#26),
#                           llama.cpp preset (#30),
#                           About dialog (#31),
#                           version 0.2.0-alpha
"""
starry_cli — StarryCLI Terminal User Interface
================================================
Built with prompt_toolkit. Real LLM streaming via
the starry_lib library. Tokyo Night color palette,
TrueColor rendering, markdown rendering, and full
mouse/keyboard scroll support.

Layout:
  Top Bar: STARRYCLI version session prov model CPU MEM
  Scrollable Body: user/AI/error/warning frames
  Bottom Bar: AI status keybindings telemetry
  Input: ❯❯ prompt

Commands: /help /setup /mode /role /clear /rewind /summarize /rename /exit /ask /buffer
Requirements: prompt_toolkit >= 3.0, starry_lib
"""

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import sys
import textwrap   # noqa: F401 (kept for future)
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import starry_lib as da
from .themes.loader import (
    load_theme,
    list_themes,
)
from starry_cli import dialogs as _dlg
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import (
    FormattedText,
)
from prompt_toolkit.key_binding import (
    KeyBindings,
    merge_key_bindings,
)
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import (
    DynamicContainer,
    FloatContainer,
    Float,
    HSplit,
    VSplit,
    Window,
    WindowAlign,
)
from prompt_toolkit.layout.controls import (
    BufferControl,
    FormattedTextControl,
)
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.dimension import (
    Dimension,
)
from prompt_toolkit.layout.processors import (
    Processor,
    Transformation,
)
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import (
    TextArea,
)


# ---------------------------------------------------
# Color Palette — loaded from active theme
# ---------------------------------------------------
_theme = load_theme()

BG_DEEP     = _theme["bg_deep"]
BG_PANEL    = _theme["bg_panel"]
BG_SCROLL   = _theme["bg_scroll"]
BORDER      = _theme["border"]
TEXT        = _theme["text"]
SYS_TEXT    = _theme["sys_text"]
ACCENT_1    = _theme["accent_1"]
ACCENT_2    = _theme["accent_2"]
LIGHT_TEXT  = _theme["light_text"]
CODE_INL_BG = _theme["code_inl_bg"]
MUTED       = _theme["muted"]
DIM_TEXT    = _theme["dim_text"]
WHITE       = _theme["white"]
ERROR_RED   = _theme["error_red"]
MODE_CLR_EXEC = _theme["text_mode_execution"]
MODE_CLR_PLAN = _theme["text_mode_plan"]

VERSION = "v0.2.0-alpha"


# ---------------------------------------------------
# Session display name — set to "session-<uuid>"
# after the pool spawns the session.
# ---------------------------------------------------
SESSION_NAME: str = "..."

# Box-drawing characters
TL = "╭"
TR = "╮"
BL = "╰"
BR = "╯"
HZ = "─"
VT = "│"

# Spinner frames
SPINNER = [
    "⠋", "⠙", "⠹", "⠸", "⠼", "⠴",
    "⠦", "⠧", "⠇", "⠏",
]

# Marker prefix length (hidden from display)
MARKER_LEN = 2

# Inline style delimiters for multi-color
# text within a single line.
# Format: SOL<style_code>EOL<text>SOL
# where style_code is a single char:
#   B=bold/fuchsia  C=code/lime  I=italic
#   L=light_text    O=orange     W=white
#   D=dim           G=lime green
SOL = "\x01"  # start of style span
EOL = "\x02"  # end of style code


# ---------------------------------------------------
# Terminal width helpers
# ---------------------------------------------------
def term_width():
    """Get current terminal width."""
    return shutil.get_terminal_size(
        (80, 24)
    ).columns


def frame_width():
    """Frame width with 2-char padding sides."""
    return term_width() - 4


def bar_full_width():
    """Full width for top/bottom bars."""
    return term_width() - 2


# ---------------------------------------------------
# Application Style (mode-aware)
# ---------------------------------------------------
def build_style(mode: str = "execution") -> Style:
    """Build a prompt_toolkit Style for the given mode.

    User frame and input colors reflect the active
    execution mode (execution=orange, plan=blue-white).
    Called at startup and on every mode switch.
    """
    mc = (
        MODE_CLR_EXEC
        if mode == "execution"
        else MODE_CLR_PLAN
    )
    return Style.from_dict(
        {
            "": f"{TEXT} bg:{BG_DEEP}",
            # Top bar
            "top-bar": (
                f"{TEXT} bg:{BG_PANEL}"
            ),
            "top-bar.frame": f"{BORDER}",
            "top-bar.actor": (
                f"bold {SYS_TEXT}"
                f" bg:{BG_PANEL}"
            ),
            "top-bar.version": (
                f"{ACCENT_1} bg:{BG_PANEL}"
            ),
            "top-bar.session": (
                f"{DIM_TEXT} bg:{BG_PANEL}"
            ),
            "top-bar.label": (
                f"bold {SYS_TEXT}"
                f" bg:{BG_PANEL}"
            ),
            "top-bar.bar-fill": (
                f"{SYS_TEXT} bg:{BG_PANEL}"
            ),
            "top-bar.bar-empty": (
                f"{MUTED} bg:{BG_PANEL}"
            ),
            "top-bar.text": (
                f"{TEXT} bg:{BG_PANEL}"
            ),
            # Scroll area
            "scroll-area": (
                f"{TEXT} bg:{BG_SCROLL}"
            ),
            # Bottom bar
            "bot-bar": (
                f"{TEXT} bg:{BG_PANEL}"
            ),
            "bot-bar.frame": f"{BORDER}",
            "bot-bar.status": (
                f"bold {ACCENT_1}"
                f" bg:{BG_PANEL}"
            ),
            "bot-bar.key": (
                f"bold {SYS_TEXT}"
                f" bg:{BG_PANEL}"
            ),
            "bot-bar.label": (
                f"{DIM_TEXT} bg:{BG_PANEL}"
            ),
            "bot-bar.version": (
                f"{ACCENT_1} bg:{BG_PANEL}"
            ),
            "bot-bar.net": (
                f"{ACCENT_2} bg:{BG_PANEL}"
            ),
            # Input (mode-dependent color)
            "input-area": (
                f"{mc} bg:{BG_DEEP}"
            ),
            "input-prompt": f"bold {mc}",
            # Cursor matches mode color
            "cursor": f"bg:{mc} {BG_DEEP}",
            # Scrollbar
            "scrollbar.background": (
                f"bg:{BG_PANEL}"
            ),
            "scrollbar.button": (
                f"bg:{BORDER}"
            ),
            "scrollbar.arrow": f"{BORDER}",
            # Thinking
            "thinking": (
                f"bold italic {ACCENT_2}"
            ),
            # Lexer line styles
            # (user frame: mode-dependent)
            "line.uframe": f"{mc}",
            "line.ucontent": f"bold {mc}",
            # Static user frame styles — frozen
            # at render time using fixed palette
            # values, not the mutable mc variable.
            "line.uframe_plan": (
                f"{MODE_CLR_PLAN}"
            ),
            "line.ucontent_plan": (
                f"bold {MODE_CLR_PLAN}"
            ),
            "line.uframe_exec": (
                f"{MODE_CLR_EXEC}"
            ),
            "line.ucontent_exec": (
                f"bold {MODE_CLR_EXEC}"
            ),
            "line.utext": f"{WHITE}",
            "line.aframe": f"{BORDER}",
            "line.acontent": f"{TEXT}",
            "line.header": (
                f"bold {LIGHT_TEXT}"
            ),
            "line.bold": f"{ACCENT_2}",
            "line.code": (
                f"{ACCENT_1} bg:{CODE_INL_BG}"
            ),
            "line.bullet": f"{LIGHT_TEXT}",
            "line.think": (
                f"bold italic {ACCENT_2}"
            ),
            "line.plain": f"{TEXT}",
            "line.dim": f"{DIM_TEXT}",
            # Inline notification
            "line.nframe": f"{WHITE}",
            "line.ncontent": f"{WHITE}",
            # Error frame (red)
            "line.eframe": f"{ERROR_RED}",
            "line.econtent": f"{ERROR_RED}",
            # Warning frame (cyan/blue)
            "line.wframe": f"{LIGHT_TEXT}",
            "line.wcontent": f"{LIGHT_TEXT}",
            # Inline span styles
            "span.bold": (
                f"bold {ACCENT_2}"
            ),
            "span.code": (
                f"{ACCENT_1} bg:{CODE_INL_BG}"
            ),
            "span.italic": f"italic {TEXT}",
            "span.light": f"{LIGHT_TEXT}",
            "span.orange": f"bold {SYS_TEXT}",
            "span.white": f"{WHITE}",
            "span.dim": f"{DIM_TEXT}",
            "span.lime": f"{ACCENT_1}",
            # Notification float
            "notif.frame": f"{WHITE}",
            "notif.text": (
                f"{WHITE} bg:{BG_PANEL}"
            ),
            "notif.bg": f"bg:{BG_PANEL}",
            # Selection menu
            "menu.frame": f"{ACCENT_1}",
            "menu.item": f"{TEXT}",
            "menu.selected": (
                f"bold {BG_DEEP}"
                f" bg:{ACCENT_1}"
            ),
            "menu.label": f"bold {ACCENT_1}",
            # Tab bar
            "tab-bar": (
                f"{TEXT} bg:{BG_PANEL}"
            ),
            "tab-bar.active": (
                f"bold {BG_DEEP}"
                f" bg:{ACCENT_1}"
            ),
            "tab-bar.inactive": (
                f"{MUTED} bg:{BG_PANEL}"
            ),
            "tab-bar.sep": (
                f"{BORDER} bg:{BG_PANEL}"
            ),
            "tab-bar.close": (
                f"bold {ACCENT_2} bg:{BG_PANEL}"
            ),
            "tab-bar.close-dim": (
                f"{MUTED} bg:{BG_PANEL}"
            ),
            # Dialogs / Buttons
            "dialog": f"bg:{BG_PANEL}",
            "dialog.body": (
                f"{TEXT} bg:{BG_PANEL}"
            ),
            "dialog frame.label": (
                f"bold {ACCENT_1}"
                f" bg:{BG_PANEL}"
            ),
            "frame.border": (
                f"{BORDER} bg:{BG_PANEL}"
            ),
            "button": (
                f"{BG_DEEP} bg:{MUTED}"
            ),
            "button.focused": (
                f"bold {BG_DEEP}"
                f" bg:{ACCENT_1}"
            ),
            # TextArea inside dialogs/wizards
            "text-area": (
                f"{TEXT} bg:{BG_SCROLL}"
            ),
            "text-area focused": (
                f"{WHITE} bg:{BG_SCROLL}"
            ),
        }
    )


APP_STYLE = build_style("execution")

# Map inline style codes to class names
SPAN_STYLES = {
    "B": "class:span.bold",
    "C": "class:span.code",
    "I": "class:span.italic",
    "L": "class:span.light",
    "O": "class:span.orange",
    "W": "class:span.white",
    "D": "class:span.dim",
    "G": "class:span.lime",
}


# ---------------------------------------------------
# Markers
# ---------------------------------------------------
M_UFRAME = "Uf"
M_UCONTENT = "Uc"
M_UTEXT = "Uw"
M_AFRAME = "Af"
M_ACONTENT = "Ac"
M_AHEADER = "Ah"
M_ABOLD = "Ab"
M_ACODE = "Ak"
M_ABULLET = "Al"
M_ATHINK = "At"
M_PLAIN = "Pl"
M_DIM = "Dm"
# Multi-color line (parsed into fragments)
M_MULTI = "Mx"
# Inline notification (scroll buffer)
M_NFRAME = "Nf"
M_NCONTENT = "Nc"
# Error frame (red)
M_EFRAME = "Ef"
M_ECONTENT = "Ec"
# Warning frame (cyan/blue)
M_WFRAME = "Wf"
M_WCONTENT = "Wc"
# Mode-baked user frame markers (color is frozen
# at render time, does not repaint on mode switch)
M_UPLAN = "UP"
M_UEXEC = "UX"

MARKER_STYLE = {
    M_UFRAME: "class:line.uframe",
    M_UCONTENT: "class:line.ucontent",
    M_UTEXT: "class:line.utext",
    M_AFRAME: "class:line.aframe",
    M_ACONTENT: "class:line.acontent",
    M_AHEADER: "class:line.header",
    M_ABOLD: "class:line.bold",
    M_ACODE: "class:line.code",
    M_ABULLET: "class:line.bullet",
    M_ATHINK: "class:line.think",
    M_PLAIN: "class:line.plain",
    M_DIM: "class:line.dim",
    M_MULTI: "class:line.acontent",
    M_NFRAME: "class:line.nframe",
    M_NCONTENT: "class:line.ncontent",
    M_EFRAME: "class:line.eframe",
    M_ECONTENT: "class:line.econtent",
    M_WFRAME: "class:line.wframe",
    M_WCONTENT: "class:line.wcontent",
    M_UPLAN: "class:line.uframe_plan",
    M_UEXEC: "class:line.uframe_exec",
}


# ---------------------------------------------------
# Multi-fragment Lexer
# ---------------------------------------------------
# Markers whose │ borders should be colored
# as frame (blue), not content color.
_AI_CONTENT_MARKERS = {
    M_ACONTENT, M_AHEADER, M_ABOLD,
    M_ACODE, M_ABULLET, M_ATHINK,
    M_MULTI, M_DIM,
}
_USER_CONTENT_MARKERS = {
    M_UCONTENT, M_UTEXT,
}
_NOTIF_CONTENT_MARKERS = {M_NCONTENT}
_ERROR_CONTENT_MARKERS = {M_ECONTENT}
_WARN_CONTENT_MARKERS = {M_WCONTENT}

_FRAME_STYLE_AI = "class:line.aframe"
_FRAME_STYLE_USER = "class:line.uframe"
_FRAME_STYLE_NOTIF = "class:line.nframe"
_FRAME_STYLE_ERROR = "class:line.eframe"
_FRAME_STYLE_WARN = "class:line.wframe"


class FrameLexer(Lexer):
    """
    Reads the 2-char marker prefix per line.
    For content lines inside frames, splits
    the │ borders into frame-colored fragments
    so borders match the top/bottom edges.
    For M_MULTI lines, also parses inline
    style spans.
    """

    def lex_document(self, document):
        lines = document.lines

        def get_line(lineno):
            if lineno >= len(lines):
                return [
                    ("class:line.plain", "")
                ]
            line = lines[lineno]
            if len(line) < MARKER_LEN:
                return [
                    ("class:line.plain", line)
                ]
            marker = line[:MARKER_LEN]

            if marker == M_MULTI:
                return _split_borders_multi(
                    line
                )

            if marker == M_UPLAN:
                return _split_borders(
                    line, marker,
                    "class:line.uframe_plan",
                    "class:line.ucontent_plan",
                )

            if marker == M_UEXEC:
                return _split_borders(
                    line, marker,
                    "class:line.uframe_exec",
                    "class:line.ucontent_exec",
                )

            if marker in _AI_CONTENT_MARKERS:
                return _split_borders(
                    line, marker,
                    _FRAME_STYLE_AI,
                )

            if marker in _USER_CONTENT_MARKERS:
                return _split_borders(
                    line, marker,
                    _FRAME_STYLE_USER,
                )

            if marker in _NOTIF_CONTENT_MARKERS:
                return _split_borders(
                    line, marker,
                    _FRAME_STYLE_NOTIF,
                )

            if marker in _ERROR_CONTENT_MARKERS:
                return _split_borders(
                    line, marker,
                    _FRAME_STYLE_ERROR,
                )

            if marker in _WARN_CONTENT_MARKERS:
                return _split_borders(
                    line, marker,
                    _FRAME_STYLE_WARN,
                )

            style = MARKER_STYLE.get(
                marker, "class:line.plain"
            )
            return [(style, line)]

        return get_line


def _split_borders(
    line, marker, frame_style,
    content_style=None,
):
    """
    Split a line so │ borders get frame_style
    while inner content gets the marker style.
    Line format: <marker> <│>content<│>
    Pass content_style explicitly to override
    the MARKER_STYLE lookup (used for mode-baked
    user frame markers).
    """
    if content_style is None:
        content_style = MARKER_STYLE.get(
            marker, "class:line.plain"
        )
    text = line[MARKER_LEN:]
    # Find first and last │
    first_vt = text.find(VT)
    last_vt = text.rfind(VT)

    if (
        first_vt == -1
        or first_vt == last_vt
    ):
        # No paired │, single style
        return [
            (content_style, line)
        ]

    frags = []
    # Marker (will be stripped)
    frags.append(
        (content_style, line[:MARKER_LEN])
    )
    # Space before first │
    if first_vt > 0:
        frags.append(
            (frame_style, text[:first_vt])
        )
    # Left │
    frags.append(
        (frame_style, VT)
    )
    # Inner content
    inner = text[first_vt + 1:last_vt]
    frags.append(
        (content_style, inner)
    )
    # Right │
    frags.append(
        (frame_style, VT)
    )
    return frags


def _split_borders_multi(line):
    """
    Like _split_borders but the inner content
    is parsed for inline style spans.
    """
    text = line[MARKER_LEN:]
    base = "class:line.acontent"
    frame = _FRAME_STYLE_AI

    first_vt = text.find(VT)
    last_vt = text.rfind(VT)

    if (
        first_vt == -1
        or first_vt == last_vt
    ):
        return _parse_inline_spans(line)

    frags = []
    # Marker (stripped by processor)
    frags.append(
        (base, line[:MARKER_LEN])
    )
    # Space before │
    if first_vt > 0:
        frags.append(
            (frame, text[:first_vt])
        )
    # Left │
    frags.append((frame, VT))
    # Inner content with spans
    inner = text[first_vt + 1:last_vt]
    frags.extend(
        _parse_inner_spans(inner, base)
    )
    # Right │
    frags.append((frame, VT))
    return frags


def _parse_inline_spans(text):
    """Fallback: parse spans with no borders."""
    base = "class:line.acontent"
    return _parse_inner_spans(text, base)


def _parse_inner_spans(text, base):
    """
    Parse inline style spans in text content
    (without marker prefix or │ borders).
    """
    fragments = []
    pos = 0
    while pos < len(text):
        sol_idx = text.find(SOL, pos)
        if sol_idx == -1:
            fragments.append(
                (base, text[pos:])
            )
            break
        if sol_idx > pos:
            fragments.append(
                (base, text[pos:sol_idx])
            )
        eol_idx = text.find(
            EOL, sol_idx + 1
        )
        if eol_idx == -1:
            fragments.append(
                (base, text[sol_idx:])
            )
            break
        code = text[sol_idx + 1:eol_idx]
        end_idx = text.find(
            SOL, eol_idx + 1
        )
        if end_idx == -1:
            span_text = text[eol_idx + 1:]
            end_idx = len(text)
        else:
            span_text = (
                text[eol_idx + 1:end_idx]
            )
        style = SPAN_STYLES.get(code, base)
        fragments.append(
            (style, span_text)
        )
        pos = end_idx + 1
    return fragments


# ---------------------------------------------------
# Marker-aware Processor
# ---------------------------------------------------
class MarkerStripProcessor(Processor):
    """
    Strips the 2-char marker prefix from each
    line. Preserves the lexer styles by only
    removing characters from the first fragment.
    """

    def apply_transformation(
        self, transformation_input
    ):
        fragments = list(
            transformation_input.fragments
        )
        if not fragments:
            return Transformation(fragments)

        # The marker is in the first fragment
        style, text = fragments[0]
        if len(text) >= MARKER_LEN:
            fragments[0] = (
                style,
                text[MARKER_LEN:],
            )
        elif len(text) > 0:
            # Marker split across fragments
            remaining = MARKER_LEN - len(text)
            fragments[0] = (style, "")
            if (
                len(fragments) > 1
                and remaining > 0
            ):
                s2, t2 = fragments[1]
                fragments[1] = (
                    s2,
                    t2[remaining:],
                )

        return Transformation(fragments)


# ---------------------------------------------------
# Telemetry
# ---------------------------------------------------
# ---------------------------------------------------
# User preferences (persisted across sessions)
# ---------------------------------------------------

def _load_user_prefs() -> dict:
    """Return saved user prefs, or {} if none."""
    try:
        if USER_PREFS_PATH.exists():
            return json.loads(
                USER_PREFS_PATH.read_text()
            )
    except Exception:
        pass
    return {}


def _save_user_prefs() -> None:
    """Write current provider/model/role/theme to disk."""
    prefs = {
        "provider": _active_provider(),
        "model": _active_model(),
        "role": _active_role(),
        "theme": _cur_theme,
        "context_format": _context_format,
        "autosum_enabled": _autosum_enabled,
        "autosum_threshold": _autosum_threshold,
        "autosum_msg_limit": _autosum_msg_limit,
        "default_system_prompt": (
            _default_system_prompt
        ),
        "default_temperature": _default_temperature,
        "default_max_tokens": _default_max_tokens,
        "default_top_p": _default_top_p,
        "user_name": _user_name,
        "user_profile": _user_profile,
    }
    try:
        USER_PREFS_PATH.write_text(
            json.dumps(prefs, indent=2)
        )
    except Exception:
        pass


def _load_user_roles() -> None:
    """Merge user-created roles from disk into
    _da_settings.agents."""
    global _user_roles
    if _da_settings is None:
        return
    if not USER_ROLES_PATH.exists():
        return
    try:
        raw = json.loads(
            USER_ROLES_PATH.read_text()
        )
        for key, entry in raw.items():
            entry["name"] = key
            try:
                rcfg = da.RoleConfig(**entry)
                _da_settings.agents[key] = rcfg
                _user_roles.add(key)
            except Exception:
                pass
    except Exception:
        pass


def _save_user_roles() -> None:
    """Persist user-created roles to disk."""
    if _da_settings is None:
        return
    data = {}
    for key in _user_roles:
        rcfg = _da_settings.agents.get(key)
        if rcfg is None:
            continue
        data[key] = {
            "label": rcfg.label,
            "expertise": rcfg.expertise,
            "system_prompt": rcfg.system_prompt,
            "temperature": rcfg.temperature,
            "model_override": rcfg.model_override,
        }
    try:
        USER_ROLES_PATH.write_text(
            json.dumps(data, indent=2)
        )
    except Exception:
        pass


def _apply_theme(name: str) -> None:
    """Apply a named theme to all global color vars."""
    global BG_DEEP, BG_PANEL, BG_SCROLL
    global BORDER, TEXT, SYS_TEXT
    global ACCENT_1, ACCENT_2, LIGHT_TEXT
    global CODE_INL_BG, MUTED, DIM_TEXT
    global WHITE, ERROR_RED
    global MODE_CLR_EXEC, MODE_CLR_PLAN
    global _cur_theme
    try:
        t = load_theme(name)
        BG_DEEP       = t["bg_deep"]
        BG_PANEL      = t["bg_panel"]
        BG_SCROLL     = t["bg_scroll"]
        BORDER        = t["border"]
        TEXT          = t["text"]
        SYS_TEXT      = t["sys_text"]
        ACCENT_1      = t["accent_1"]
        ACCENT_2      = t["accent_2"]
        LIGHT_TEXT    = t["light_text"]
        CODE_INL_BG   = t["code_inl_bg"]
        MUTED         = t["muted"]
        DIM_TEXT      = t["dim_text"]
        WHITE         = t["white"]
        ERROR_RED     = t["error_red"]
        MODE_CLR_EXEC = t["text_mode_execution"]
        MODE_CLR_PLAN = t["text_mode_plan"]
        _cur_theme    = name
    except Exception:
        pass


class TelemetryState:
    """Simulated system metrics."""

    def __init__(self):
        self.cpu = 12.0
        self.mem = 34.0
        self.net_in = 0.0
        self.net_out = 0.0
        self.ai_status = "idle"
        self.start_time = time.monotonic()
        self.spinner_idx = 0

    def tick(self):
        # cpu/mem/net are not real metrics
        # self.cpu = max(2.0, min(98.0,
        #     self.cpu + random.uniform(-5, 5)))
        # self.mem = max(20.0, min(85.0,
        #     self.mem + random.uniform(-2, 2)))
        # self.net_in = random.uniform(0.1, 12.5)
        # self.net_out = random.uniform(0.05, 4.8)
        pass

    def next_spinner(self):
        ch = SPINNER[
            self.spinner_idx % len(SPINNER)
        ]
        self.spinner_idx += 1
        return ch

    @property
    def uptime(self):
        elapsed = int(
            time.monotonic() - self.start_time
        )
        m, s = divmod(elapsed, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


telemetry = TelemetryState()


# ---------------------------------------------------
# App state (set by main before app starts)
# ---------------------------------------------------
_STARRY_DIR = Path.home() / ".local" / "starry"
_STARRY_DIR.mkdir(parents=True, exist_ok=True)
USER_PREFS_PATH = _STARRY_DIR / "user.json"
USER_ROLES_PATH = _STARRY_DIR / "user_roles.json"

_app_mode: str = "standard"    # standard|setup
_prev_mode: str = "standard"   # before setup
_user_roles: set = set()       # user-created role keys
_cur_theme: str = ""           # active theme name
_context_format: str = "markdown"  # markdown|json
_exec_mode: str = "execution"  # plan|execution
_tui_input_mode: str = "chat"  # chat|question
_wizard_cancel_fn = None       # active dialog cancel
_avail_models: dict = {}       # pname→[models]
_da_settings = None            # da.AppSettings
_da_session = None             # da.Session
_da_pool = None                # da.AgentPool
_ai_task = None                # active LLM asyncio.Task
_session_stack: list = []      # agent routing stack
_active_registry = None        # ActiveRegistry


# ── Session-state accessors ────────────────────────
# Single source of truth: the session object.
# Fall back to _da_settings during the brief
# pre-session startup phase.

def _active_provider() -> str:
    if _da_session is not None:
        return _da_session.provider
    if _da_settings is not None:
        return _da_settings.active_provider
    return ""


def _active_model() -> str:
    if _da_session is not None:
        return _da_session.model
    return ""


def _active_role() -> str:
    if _da_session is not None:
        return _da_session.role
    if _da_settings is not None:
        return _da_settings.active_role
    return ""
_auto_approved: dict = {}      # tool→set(args_json)
_pending_questions: list = []  # questions awaiting answer

# ── Autosummarize state ────────────────────────────
_autosum_enabled: bool = True   # feature on/off
_autosum_threshold: int = 75    # % of ctx_window
_autosum_msg_limit: int = 10    # msgs when no ctx_window
_autosum_triggered: bool = False  # already fired this session

# ── Default conversation overrides ─────────────────
_default_system_prompt: str = ""
_default_temperature: float | None = None
_default_max_tokens: int | None = None
_default_top_p: float | None = None

# ── User personalization ────────────────────────────
_user_name: str = ""
_user_profile: str = ""


# ===================================================
# Notification System (floating toasts)
# ===================================================
class NotificationManager:
    """
    Manages floating notification toasts.
    Each notification auto-dismisses after
    a configurable duration.
    """

    def __init__(self):
        self.notifications = []
        self._app = None

    def set_app(self, app):
        self._app = app

    def notify(self, message, duration=3.0):
        """
        Show a floating notification.
        """
        notif_id = id(message) + len(
            self.notifications
        )
        self.notifications.append({
            "id": notif_id,
            "message": message,
        })
        self._rebuild_floats()
        if self._app:
            self._app.invalidate()

        async def dismiss():
            await asyncio.sleep(duration)
            self.notifications = [
                n for n in self.notifications
                if n["id"] != notif_id
            ]
            self._rebuild_floats()
            if self._app:
                self._app.invalidate()

        asyncio.ensure_future(dismiss())

    def get_floats(self):
        """
        Return Float objects for active
        notifications, stacked from top-right.
        """
        floats = []
        for i, notif in enumerate(
            self.notifications
        ):
            msg = notif["message"]
            w = len(msg) + 6
            content = self._build_notif(
                msg, w
            )
            float_win = Float(
                content=Window(
                    content=(
                        FormattedTextControl(
                            content
                        )
                    ),
                    width=w + 2,
                    height=3,
                    style="class:notif.bg",
                ),
                right=2,
                top=1 + (i * 4),
            )
            floats.append(float_win)
        return floats

    def _rebuild_floats(self):
        """Update the shared float list."""
        global _active_floats
        _active_floats.clear()
        _active_floats.extend(
            self.get_floats()
        )
        _active_floats.extend(_dialog_floats)
        _active_floats.extend(_dlg.get_floats())

    @staticmethod
    def _build_notif(msg, w):
        """Build notification content."""
        inner = w
        padded_msg = f" 🔔 {msg} "
        pad = max(
            0, inner - len(padded_msg) - 1
        )
        parts = [
            (
                "class:notif.frame",
                f"{TL}{HZ * inner}{TR}\n",
            ),
            ("class:notif.frame", VT),
            (
                "class:notif.text",
                f"{padded_msg}{' ' * pad}",
            ),
            (
                "class:notif.frame",
                f"{VT}\n",
            ),
            (
                "class:notif.frame",
                f"{BL}{HZ * inner}{BR}",
            ),
        ]
        return parts


notif_mgr = NotificationManager()
_dlg.init(notif_mgr._rebuild_floats)

# Persistent dialog floats (separate from
# notification toasts so they survive
# notification rebuilds).
_dialog_floats = []


def show_dialog(app, float_obj):
    """Push a dialog Float and redraw."""
    _dialog_floats.append(float_obj)
    notif_mgr._rebuild_floats()
    app.invalidate()


def close_dialog(app, float_obj):
    """Remove a dialog Float, refocus input."""
    if float_obj in _dialog_floats:
        _dialog_floats.remove(float_obj)
    notif_mgr._rebuild_floats()
    app.layout.focus(input_area)
    app.invalidate()


# ===================================================
# Selection Menu (arrow-key navigable)
# ===================================================
class SelectionMenu:
    """
    An arrow-key navigable selection menu
    shown inline in the scroll buffer.
    When active, captures Up/Down/Enter.
    white_mode=True uses white notification
    colors instead of the default AI blue.
    """

    def __init__(self):
        self.active = False
        self.options = []
        self.selected = 0
        self.title = ""
        self._callback = None
        self.white_mode = False
        self._prev_lines = 0
        self.checkbox_mode = False
        self.checkboxes = []      # list[bool]
        # only first num_checkboxes items get boxes
        self.num_checkboxes = 0

    def show(
        self, title, options,
        callback, white=False,
        checkbox=False, num_checkboxes=None,
    ):
        """
        Activate the menu with given options.
        callback(selected_index) on Enter.
        white=True → white notification style.
        checkbox=True → show [ ]/[x] toggles.
        num_checkboxes overrides how many items
        get checkboxes (default: all items).
        """
        self.active = True
        self.title = title
        self.options = list(options)
        self.selected = 0
        self._callback = callback
        self.white_mode = white
        self.checkbox_mode = checkbox
        if checkbox:
            n = (
                num_checkboxes
                if num_checkboxes is not None
                else len(self.options)
            )
            self.num_checkboxes = n
            self.checkboxes = [False] * n
        else:
            self.num_checkboxes = 0
            self.checkboxes = []

    def toggle_checkbox(self):
        """Toggle the checkbox of the selected item."""
        idx = self.selected
        if (
            self.checkbox_mode
            and idx < self.num_checkboxes
        ):
            self.checkboxes[idx] = (
                not self.checkboxes[idx]
            )

    def checked_indices(self):
        """Return list of checked item indices."""
        return [
            i for i, c
            in enumerate(self.checkboxes)
            if c
        ]

    def move_up(self):
        if self.selected > 0:
            self.selected -= 1

    def move_down(self):
        if self.selected < (
            len(self.options) - 1
        ):
            self.selected += 1

    def confirm(self):
        """Confirm selection, deactivate."""
        self.active = False
        idx = self.selected
        cb = self._callback
        self._callback = None
        if cb:
            cb(idx)

    def dismiss(self):
        """Cancel the menu without calling the callback."""
        self.active = False
        self._callback = None

    def build_frame(self):
        """
        Build the menu as marker-prefixed
        lines for the scroll buffer.
        """
        w = frame_width()
        inner = w - 2
        lines = []

        # Pick frame/content markers by mode
        if self.white_mode:
            fm = M_NFRAME
            cm = M_NCONTENT
        else:
            fm = M_AFRAME
            cm = M_ACONTENT

        # Top border
        label = f" {self.title} "
        rest = max(
            0, inner - len(label) - 1
        )
        top = (
            f"{HZ}{label}"
            f"{HZ * rest}{TR}"
        )
        lines.append(
            f"{fm} {TL}{top}"
        )

        # Empty line
        lines.append(
            f"{cm} {VT}"
            f"{' ' * inner}{VT}"
        )

        # Options
        for i, opt in enumerate(
            self.options
        ):
            has_cb = (
                self.checkbox_mode
                and i < self.num_checkboxes
            )
            if has_cb:
                checked = (
                    i < len(self.checkboxes)
                    and self.checkboxes[i]
                )
                cb_str = (
                    "[x] " if checked else "[ ] "
                )
            else:
                cb_str = ""

            if self.white_mode:
                # White mode: plain ▶ indicator
                if i == self.selected:
                    text = f" ▶ {cb_str}{opt}"
                else:
                    text = f"   {cb_str}{opt}"
                p = _pad_line(text, inner)
                lines.append(
                    f"{cm} {VT}{p}{VT}"
                )
            else:
                # Default: colored lime spans
                if i == self.selected:
                    marker = (
                        f"{SOL}G{EOL}"
                        f" ▶ {cb_str}{opt}"
                        f"{SOL}"
                    )
                    styled = (
                        f"   {marker}"
                    )
                else:
                    styled = (
                        f"     {cb_str}{opt}"
                    )
                p = _pad_line(styled, inner)
                lines.append(
                    f"{M_MULTI} {VT}{p}{VT}"
                )

        # Empty line
        lines.append(
            f"{cm} {VT}"
            f"{' ' * inner}{VT}"
        )

        # Hint line
        if self.white_mode:
            hint = (
                "   ↑/↓ navigate  "
                "Enter select  "
                "Esc cancel"
            )
            ph = _pad_line(hint, inner)
            lines.append(
                f"{cm} {VT}{ph}{VT}"
            )
        elif self.checkbox_mode:
            hint = (
                f"   {SOL}D{EOL}"
                "↑/↓ navigate  "
                "x toggle  "
                "r remove marked  "
                "Enter select  "
                "Esc cancel"
                f"{SOL}"
            )
            ph = _pad_line(hint, inner)
            lines.append(
                f"{M_MULTI} {VT}{ph}{VT}"
            )
        else:
            hint = (
                f"   {SOL}D{EOL}"
                "↑/↓ navigate  "
                "Enter select  "
                "Esc cancel"
                f"{SOL}"
            )
            ph = _pad_line(hint, inner)
            lines.append(
                f"{M_MULTI} {VT}{ph}{VT}"
            )

        lines.append(
            f"{fm} {BL}"
            f"{HZ * inner}{BR}"
        )
        return "\n".join(lines)


sel_menu = SelectionMenu()

# Holds the sessions list while a sessions menu
# is active, for use by 'r' key handler.
_session_menu_saved: list = []


# ---------------------------------------------------
# Progress bar — not used (CPU/MEM not operational)
# ---------------------------------------------------
# def make_bar(pct, width=12):
#     filled = int(pct / 100.0 * width)
#     empty = width - filled
#     return [
#         ("class:top-bar.bar-fill", "█" * filled),
#         ("class:top-bar.bar-empty", "░" * empty),
#     ]


# ---------------------------------------------------
# Top Bar (3-line framed)
# Displays: STARRYCLI | VERSION |
#           tok TOKENS | TIME
# ---------------------------------------------------
def get_top_bar():
    telemetry.tick()
    w = bar_full_width()
    now = datetime.now().strftime("%H:%M:%S")

    parts = []
    # Top border
    parts.append(
        ("class:top-bar.frame", f"{TL}")
    )
    parts.append((
        "class:top-bar.frame",
        f"{HZ * w}",
    ))
    parts.append(
        ("class:top-bar.frame", f"{TR}\n")
    )

    # Content line
    parts.append(
        ("class:top-bar.frame", f"{VT}")
    )
    parts.append(
        ("class:top-bar.text", " ")
    )
    parts.append((
        "class:top-bar.actor",
        " ✦ S T A R R Y ✦ ",
    ))
    parts.append(
        ("class:top-bar.text", " ")
    )
    parts.append((
        "class:top-bar.version",
        f"{VERSION}",
    ))
    tok = (
        _da_session.token_usage
        if _da_session is not None
        else {}
    )
    total_tok = tok.get("total", 0)
    ctx_win = (
        _da_session.context_window
        if _da_session is not None
        else None
    )
    if ctx_win:
        pct = int(total_tok * 100 / ctx_win)
        tok_str = (
            f"[ {total_tok}/{ctx_win} : {pct}% ]"
        )
    else:
        tok_str = f"[ {total_tok}/? : ?% ]"
    parts.append(
        ("class:top-bar.text", " │ ")
    )
    parts.append(
        ("class:top-bar.label", "tok ")
    )
    parts.append((
        "class:top-bar.version", tok_str
    ))
    cost = (
        _da_session.cost_estimate
        if _da_session is not None
        else None
    )
    if cost is not None:
        parts.append((
            "class:top-bar.text",
            f" ${cost:.4f}",
        ))
    parts.append(
        ("class:top-bar.text", " │ ")
    )
    parts.append((
        "class:top-bar.session",
        f"{now} ",
    ))

    # Pad to fill and close
    vis = sum(
        len(t) for _, t in parts
        if "\n" not in t
    )
    content_len = vis - 1 - w
    pad = max(0, w - content_len)
    parts.append(
        ("class:top-bar.text", " " * pad)
    )
    parts.append(
        ("class:top-bar.frame", f"{VT}\n")
    )

    # Bottom border
    parts.append(
        ("class:top-bar.frame", f"{BL}")
    )
    parts.append((
        "class:top-bar.frame",
        f"{HZ * w}",
    ))
    parts.append(
        ("class:top-bar.frame", f"{BR}")
    )
    return parts


# ---------------------------------------------------
# Bottom Bar (3-line framed)
# ---------------------------------------------------
def get_bot_bar():
    w = bar_full_width()
    st_style = "class:bot-bar.status"
    st_label = telemetry.ai_status.upper()
    if telemetry.ai_status == "thinking":
        st_style = "class:thinking"

    parts = []
    parts.append(
        ("class:bot-bar.frame", f"{TL}")
    )
    parts.append((
        "class:bot-bar.frame",
        f"{HZ * w}",
    ))
    parts.append(
        ("class:bot-bar.frame", f"{TR}\n")
    )

    # Abbreviate provider/model for bottom bar
    _bot_pname = (_active_provider() or "")[:10] or "—"
    _bot_mname = _active_model()
    if len(_bot_mname) > 14:
        _bot_mname = _bot_mname[:13] + "…"
    if not _bot_mname:
        _bot_mname = "—"

    parts.append(
        ("class:bot-bar.frame", f"{VT}")
    )
    parts.append(
        ("class:bot-bar.label", " AI: ")
    )
    parts.append(
        (st_style, f" {st_label} ")
    )
    parts.append(
        ("class:bot-bar.label", " │ ")
    )
    parts.append((
        "class:bot-bar.status",
        f" {_exec_mode.upper()} ",
    ))
    parts.append(
        ("class:bot-bar.label", " │ ")
    )
    parts.append(
        ("class:bot-bar.label", "prov ")
    )
    parts.append((
        "class:bot-bar.version", _bot_pname
    ))
    parts.append(
        ("class:bot-bar.label", " │ ")
    )
    parts.append(
        ("class:bot-bar.label", "model ")
    )
    parts.append((
        "class:bot-bar.version", _bot_mname
    ))
    parts.append(
        ("class:bot-bar.label", " │ ")
    )
    parts.append(
        ("class:bot-bar.label", "role ")
    )
    rlabel = _active_role()[:10] or "—"
    parts.append((
        "class:bot-bar.version", rlabel
    ))
    parts.append(
        ("class:bot-bar.label", " │ ")
    )
    parts.append(
        ("class:bot-bar.key", "/help")
    )
    parts.append(
        ("class:bot-bar.label", " help ")
    )
    # net KB/s not operational (simulated values)
    # parts.append(("class:bot-bar.label", " │ "))
    # parts.append(("class:bot-bar.label", " ↑ "))
    # parts.append(("class:bot-bar.net",
    #     f"{telemetry.net_in:5.1f} KB/s"))
    # parts.append(("class:bot-bar.label", " ↓ "))
    # parts.append(("class:bot-bar.net",
    #     f"{telemetry.net_out:5.1f} KB/s"))

    vis = sum(
        len(t) for _, t in parts
        if "\n" not in t
    )
    content_len = vis - w - 2
    pad = max(0, w - content_len)
    parts.append(
        ("class:bot-bar.label", " " * pad)
    )
    parts.append(
        ("class:bot-bar.frame", f"{VT}\n")
    )

    parts.append(
        ("class:bot-bar.frame", f"{BL}")
    )
    parts.append((
        "class:bot-bar.frame",
        f"{HZ * w}",
    ))
    parts.append(
        ("class:bot-bar.frame", f"{BR}")
    )
    return parts


# ===================================================
# Text helpers
# ===================================================
def _pad_line(text, inner_w):
    """Pad text with spaces to inner_w."""
    vis = _visible_len(text)
    need = max(0, inner_w - vis)
    return text + " " * need


def _col_width(ch):
    """Terminal column width of a single char.

    Wide (W/F): 2 columns.
    Combining/control (Mn, Me, Cf): 0 columns.
    Everything else: 1 column.
    """
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 2
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):
        return 0
    return 1


def _visible_len(text):
    """Column width of text, excluding inline
    style markers (SOL/EOL and style codes).
    Uses terminal column widths so wide chars
    (emoji, etc.) count as 2.

    Handles multi-codepoint sequences:
    - ZWJ (U+200D) joins; next cp is skipped
    - Regional indicator pairs (flags) = 2
    - Emoji skin-tone modifiers = 0 extra
    """
    clean = re.sub(
        f"{re.escape(SOL)}.?"
        f"{re.escape(EOL)}",
        "",
        text,
    )
    clean = clean.replace(SOL, "")
    total = 0
    skip = False
    ri_pending = False
    for ch in clean:
        if skip:
            skip = False
            continue
        cp = ord(ch)
        # Regional indicator pair = 1 flag glyph
        if 0x1F1E6 <= cp <= 0x1F1FF:
            if ri_pending:
                ri_pending = False
            else:
                ri_pending = True
                total += 2
            continue
        ri_pending = False
        # Skin-tone modifier combines with base
        if 0x1F3FB <= cp <= 0x1F3FF:
            continue
        w = _col_width(ch)
        # ZWJ merges next cp into this cluster
        if ch == "\u200d":
            skip = True
        total += w
    return total


def _wrap_text(text, width):
    """
    Word-wrap text respecting inline style
    markers. Returns list of wrapped lines.
    """
    if _visible_len(text) <= width:
        return [text]

    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        test = (
            f"{current} {word}"
            if current else word
        )
        if _visible_len(test) <= width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _inline(text):
    """
    Convert markdown inline formatting to
    style span markers.
    Handles: `code`, ***bold italic***,
    **bold**, *italic*.
    Code is processed first so that bold/italic
    inside code spans does not create nested
    markers (which renders as ^A/^B garbage).
    """
    # Inline code `...` FIRST — highest priority
    text = re.sub(
        r"`([^`]+)`",
        lambda m: (
            f"{SOL}C{EOL}"
            f" {m.group(1)} "
            f"{SOL}"
        ),
        text,
    )
    # Bold italic ***...*** — skip if already styled
    text = re.sub(
        r"\*\*\*(.+?)\*\*\*",
        lambda m: (
            f"{SOL}B{EOL}{m.group(1)}{SOL}"
            if SOL not in m.group(1)
            else m.group(1)
        ),
        text,
    )
    # Bold **...** — skip if already styled
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: (
            f"{SOL}B{EOL}{m.group(1)}{SOL}"
            if SOL not in m.group(1)
            else m.group(1)
        ),
        text,
    )
    # Italic *...* — skip if already styled
    text = re.sub(
        r"(?<!\*)\*([^*]+?)\*(?!\*)",
        lambda m: (
            f"{SOL}I{EOL}{m.group(1)}{SOL}"
            if SOL not in m.group(1)
            else m.group(1)
        ),
        text,
    )
    return text


# ===================================================
# Frame builders
# ===================================================
def build_user_frame(
    cmd_text, mode="execution"
):
    """
    User command frame with mode-baked color.
    Uses M_UEXEC or M_UPLAN so the color is
    frozen at render time and does not repaint
    when the active mode changes later.
    """
    w = frame_width()
    inner = w - 2
    ts = datetime.now().strftime("%H:%M:%S")
    fm = (
        M_UEXEC
        if mode == "execution"
        else M_UPLAN
    )

    lines = []
    # Top with timestamp in label
    label = f" User Command [{ts}] "
    rest = max(
        0, inner - _visible_len(label) - 1
    )
    top = f"{HZ}{label}{HZ * rest}{TR}"
    lines.append(
        f"{fm} {TL}{top}"
    )
    # Content: wrap long text
    prefix = " ❯❯ "
    content_w = inner - _visible_len(prefix) - 1
    if _visible_len(cmd_text) <= content_w:
        padded = _pad_line(
            f"{prefix}{cmd_text}", inner
        )
        lines.append(
            f"{fm} {VT}"
            f"{padded}{VT}"
        )
    else:
        # First line with arrow
        first = cmd_text[:content_w]
        padded = _pad_line(
            f"{prefix}{first}", inner
        )
        lines.append(
            f"{fm} {VT}"
            f"{padded}{VT}"
        )
        # Continuation lines
        indent = " " * len(prefix)
        remaining = cmd_text[content_w:]
        while remaining:
            chunk = remaining[:content_w]
            remaining = remaining[
                content_w:
            ]
            padded = _pad_line(
                f"{indent}{chunk}", inner
            )
            lines.append(
                f"{fm} {VT}"
                f"{padded}{VT}"
            )
    # Bottom
    lines.append(
        f"{fm} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_ai_frame(md_text):
    """
    AI response in blue frame with parsed
    multicolor markdown, word-wrapped.
    """
    w = frame_width()
    inner = w - 2

    lines = []
    label = " ✦ StarryLib Insight "
    rest = max(
        0, inner - _visible_len(label) - 1
    )
    top = f"{HZ}{label}{HZ * rest}{TR}"
    lines.append(
        f"{M_AFRAME} {TL}{top}"
    )
    # Empty line after caption
    lines.append(
        f"{M_ACONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )

    md_lines = _parse_markdown(
        md_text, inner
    )
    lines.extend(md_lines)

    lines.append(
        f"{M_AFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_thinking_frame(
    spinner_ch="⠋",
    message="StarryCLI is thinking...",
):
    """Thinking frame with spinner."""
    w = frame_width()
    inner = w - 2

    lines = []
    label = " ✦ StarryCLI "
    rest = max(
        0, inner - _visible_len(label) - 1
    )
    top = f"{HZ}{label}{HZ * rest}{TR}"
    lines.append(
        f"{M_AFRAME} {TL}{top}"
    )

    content = f" {spinner_ch} {message}"
    padded = _pad_line(content, inner)
    lines.append(
        f"{M_ATHINK} {VT}{padded}{VT}"
    )

    lines.append(
        f"{M_AFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_inline_notif(message, label="🔔"):
    """
    Build an inline notification frame for
    the scroll buffer. White frame and text
    by default, using M_NFRAME/M_NCONTENT.
    """
    w = frame_width()
    inner = w - 2
    ts = datetime.now().strftime("%H:%M:%S")

    lines = []
    # Top
    title = f" {label} Notification [{ts}] "
    rest = max(
        0, inner - _visible_len(title) - 1
    )
    top = f"{HZ}{title}{HZ * rest}{TR}"
    lines.append(
        f"{M_NFRAME} {TL}{top}"
    )
    # Empty line
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    # Content — split on newlines, then wrap
    content_w = inner - 4
    prefix = "   "
    all_wrapped = []
    for para in message.split("\n"):
        if para.strip():
            all_wrapped.extend(
                _wrap_text(para, content_w)
            )
    for wline in all_wrapped:
        c = f"{prefix}{wline}"
        p = _pad_line(c, inner)
        lines.append(
            f"{M_NCONTENT} {VT}{p}{VT}"
        )
    # Empty line
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    # Bottom
    lines.append(
        f"{M_NFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_role_info_frame(role_name: str) -> str:
    """Build a role info frame shown after a role switch."""
    if _da_settings is None:
        return ""
    rcfg = _da_settings.agents.get(role_name)
    if rcfg is None:
        return ""
    w = frame_width()
    inner = w - 2
    lines = []
    title = f" ● Role: {rcfg.label} "
    rest = max(
        0, inner - _visible_len(title) - 1
    )
    top = f"{HZ}{title}{HZ * rest}{TR}"
    lines.append(f"{M_NFRAME} {TL}{top}")
    lines.append(
        f"{M_NCONTENT} {VT}{' ' * inner}{VT}"
    )

    def _row(key: str, val: str) -> str:
        content_w = inner - 2
        label_str = f"  {key:<8} {val}"
        p = _pad_line(label_str, content_w)
        return f"{M_NCONTENT} {VT} {p}{VT}"

    # Goal (first line only, truncated)
    goal = rcfg.goal.strip().replace("\n", " ")
    if len(goal) > inner - 14:
        goal = goal[:inner - 17] + "…"
    if goal:
        lines.append(_row("Goal:", goal))

    # Tools
    if rcfg.allowed_tools is not None:
        tools_str = ", ".join(rcfg.allowed_tools)
    else:
        tools_str = "(all)"
    lines.append(_row("Tools:", tools_str))

    # Skills
    if rcfg.allowed_skills is not None:
        skills_str = ", ".join(rcfg.allowed_skills)
    else:
        skills_str = "(all)"
    lines.append(_row("Skills:", skills_str))

    # Model + temperature
    provider_cfg = None
    if _da_settings:
        provider_cfg = _da_settings.providers.get(
            _active_provider()
        )
    model_str = _active_model() or "—"
    if rcfg.temperature is not None:
        model_str += f"  temp={rcfg.temperature}"
    lines.append(_row("Model:", model_str))

    lines.append(
        f"{M_NCONTENT} {VT}{' ' * inner}{VT}"
    )
    lines.append(
        f"{M_NFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_error_frame(message):
    """
    Error notification in red frame.
    Uses M_EFRAME/M_ECONTENT markers.
    """
    w = frame_width()
    inner = w - 2
    ts = datetime.now().strftime("%H:%M:%S")

    lines = []
    title = f" ✗ Error [{ts}] "
    rest = max(
        0, inner - _visible_len(title) - 1
    )
    top = f"{HZ}{title}{HZ * rest}{TR}"
    lines.append(
        f"{M_EFRAME} {TL}{top}"
    )
    lines.append(
        f"{M_ECONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    content_w = inner - 4
    prefix = "   "
    wrapped = _wrap_text(
        str(message), content_w
    )
    for wline in wrapped:
        c = f"{prefix}{wline}"
        p = _pad_line(c, inner)
        lines.append(
            f"{M_ECONTENT} {VT}{p}{VT}"
        )
    lines.append(
        f"{M_ECONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    lines.append(
        f"{M_EFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_warn_frame(message):
    """
    Warning notification in cyan/blue frame.
    Uses M_WFRAME/M_WCONTENT markers.
    """
    w = frame_width()
    inner = w - 2
    ts = datetime.now().strftime("%H:%M:%S")

    lines = []
    title = f" ⚠ Warning [{ts}] "
    rest = max(
        0, inner - _visible_len(title) - 1
    )
    top = f"{HZ}{title}{HZ * rest}{TR}"
    lines.append(
        f"{M_WFRAME} {TL}{top}"
    )
    lines.append(
        f"{M_WCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    content_w = inner - 4
    prefix = "   "
    wrapped = _wrap_text(
        str(message), content_w
    )
    for wline in wrapped:
        c = f"{prefix}{wline}"
        p = _pad_line(c, inner)
        lines.append(
            f"{M_WCONTENT} {VT}{p}{VT}"
        )
    lines.append(
        f"{M_WCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    lines.append(
        f"{M_WFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_question_frame(questions):
    """
    Inline prompt frame for question tool input.
    Shows each question and asks user to reply.
    Uses M_NFRAME/M_NCONTENT markers.
    """
    w = frame_width()
    inner = w - 2
    ts = datetime.now().strftime("%H:%M:%S")

    lines = []
    title = f" ❓ StarryCLI asks [{ts}] "
    rest = max(
        0, inner - _visible_len(title) - 1
    )
    top = f"{HZ}{title}{HZ * rest}{TR}"
    lines.append(f"{M_NFRAME} {TL}{top}")
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    content_w = inner - 4
    for i, q in enumerate(questions, 1):
        prefix = f"   {i}. "
        wrapped = _wrap_text(
            str(q), content_w - len(prefix) + 4
        )
        for j, wline in enumerate(wrapped):
            c = (
                f"   {i}. {wline}"
                if j == 0
                else f"      {wline}"
            )
            p = _pad_line(c, inner)
            lines.append(
                f"{M_NCONTENT} {VT}{p}{VT}"
            )
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    hint = "   ↳ Type your answer and Enter"
    ph = _pad_line(hint, inner)
    lines.append(
        f"{M_NCONTENT} {VT}{ph}{VT}"
    )
    lines.append(
        f"{M_NFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_wizard_prompt_frame(prompt_text):
    """
    White prompt frame for the new-provider
    wizard. Uses M_NFRAME/M_NCONTENT markers.
    """
    w = frame_width()
    inner = w - 2
    ts = datetime.now().strftime("%H:%M:%S")
    lines = []
    title = f" ✦ New provider [{ts}] "
    rest = max(
        0, inner - _visible_len(title) - 1
    )
    top = f"{HZ}{title}{HZ * rest}{TR}"
    lines.append(f"{M_NFRAME} {TL}{top}")
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    content_w = inner - 4
    wrapped = _wrap_text(
        str(prompt_text), content_w
    )
    for wline in wrapped:
        c = f"   {wline}"
        p = _pad_line(c, inner)
        lines.append(
            f"{M_NCONTENT} {VT}{p}{VT}"
        )
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    hint = "   ↳ Type your answer and Enter"
    ph = _pad_line(hint, inner)
    lines.append(
        f"{M_NCONTENT} {VT}{ph}{VT}"
    )
    lines.append(
        f"{M_NFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_setup_list_frame(title, items):
    """
    White-framed list for /setup display.
    Uses M_NFRAME/M_NCONTENT markers.
    """
    w = frame_width()
    inner = w - 2

    lines = []
    label = f" {title} "
    rest = max(
        0, inner - _visible_len(label) - 1
    )
    top = f"{HZ}{label}{HZ * rest}{TR}"
    lines.append(
        f"{M_NFRAME} {TL}{top}"
    )
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    for item in items:
        c = f"   {item}"
        p = _pad_line(c, inner)
        lines.append(
            f"{M_NCONTENT} {VT}{p}{VT}"
        )
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    lines.append(
        f"{M_NFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def build_tools_frame(schemas: list) -> str:
    """Render a tool-list frame from tool schemas.

    Each entry shows tool name and its one-line
    description. Uses inline-notification style.
    """
    w = frame_width()
    inner = w - 2
    lines = []
    label = " Active Tools "
    rest = max(
        0, inner - _visible_len(label) - 1
    )
    top = f"{HZ}{label}{HZ * rest}{TR}"
    lines.append(f"{M_NFRAME} {TL}{top}")
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    if not schemas:
        p = _pad_line("  (none)", inner)
        lines.append(
            f"{M_NCONTENT} {VT}{p}{VT}"
        )
    else:
        for s in schemas:
            fn = s.get("function", {})
            name = fn.get("name", "?")
            desc = fn.get("description", "")
            first_line = (
                desc.split("\n")[0]
                if desc else ""
            )
            entry = (
                f"  {name} — {first_line}"
            )
            p = _pad_line(entry, inner)
            lines.append(
                f"{M_NCONTENT} {VT}{p}{VT}"
            )
    lines.append(
        f"{M_NCONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    lines.append(
        f"{M_NFRAME} {BL}{HZ * inner}{BR}"
    )
    return "\n".join(lines)


def _replay_display_entry(entry: dict) -> None:
    """Render a single display_log entry into
    the scroll buffer using the correct frame
    type and colors.
    """
    t = entry.get("type", "")
    content = entry.get("content", "")
    if t == "user":
        if content.startswith("[internal event]"):
            return
        mode = entry.get("mode", "execution")
        append_text(
            build_user_frame(content, mode)
        )
    elif t == "assistant":
        if content:
            append_text(
                build_ai_frame(content)
            )
    elif t == "tool_call":
        name = entry.get("name", "?")
        args = entry.get("args", {})
        arg_parts = []
        for k, v in args.items():
            v_str = str(v)
            if len(v_str) > 60:
                v_str = v_str[:57] + "..."
            arg_parts.append(f"{k}={v_str!r}")
        arg_str = ", ".join(arg_parts)
        msg = f"tool:{name}({arg_str})"
        append_text(build_warn_frame(msg))
    elif t == "tool_result":
        name = entry.get("name", "?")
        result = entry.get("result", "")
        preview = (
            result[:120] + "…"
            if len(result) > 120
            else result
        )
        append_text(
            build_inline_notif(
                f"`{name}` → {preview}", "→"
            )
        )
    elif t == "mode_change":
        old = entry.get("old_mode", "?")
        new = entry.get("new_mode", "?")
        append_text(
            build_inline_notif(
                f"Mode: {old.upper()} → "
                f"{new.upper()}",
                "⚙",
            )
        )
    elif t == "provider_change":
        old = entry.get("old_provider", "?")
        new = entry.get("new_provider", "?")
        append_text(
            build_inline_notif(
                f"Provider: {old} → {new}",
                "✓",
            )
        )
    elif t == "model_change":
        old = entry.get("old_model", "?")
        new = entry.get("new_model", "?")
        append_text(
            build_inline_notif(
                f"Model: {old} → {new}",
                "✓",
            )
        )
    elif t == "role_change":
        old = entry.get("old_role", "?")
        new = entry.get("new_role", "?")
        append_text(
            build_inline_notif(
                f"Role: {old} → {new}",
                "✦",
            )
        )
    elif t == "error":
        append_text(
            build_error_frame(content)
        )


# ===================================================
# Markdown parser → framed lines
# ===================================================
def _parse_markdown(md_text, inner_w):
    """
    Convert markdown into marker-prefixed,
    word-wrapped, multi-color lines.
    """
    result = []
    raw_lines = md_text.split("\n")
    in_code = False

    for raw in raw_lines:
        stripped = raw.strip()

        # --- Code fences ---
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                lang = stripped[3:].strip()
                if lang:
                    c = f"   [{lang}]"
                    p = _pad_line(c, inner_w)
                    result.append(
                        f"{M_ACODE} {VT}"
                        f"{p}{VT}"
                    )
                continue
            else:
                in_code = False
                continue

        if in_code:
            c = f"   {raw}"
            p = _pad_line(c, inner_w)
            result.append(
                f"{M_ACODE} {VT}{p}{VT}"
            )
            continue

        # --- Blank ---
        if not stripped:
            p = " " * inner_w
            result.append(
                f"{M_ACONTENT} {VT}"
                f"{p}{VT}"
            )
            continue

        # --- H3 ---
        if stripped.startswith("### "):
            txt = stripped[4:]
            c = f"   {txt}"
            p = _pad_line(c, inner_w)
            result.append(
                f"{M_AHEADER} {VT}{p}{VT}"
            )
            continue

        # --- H2 ---
        if stripped.startswith("## "):
            txt = stripped[3:]
            c = f" ✦ {txt}"
            p = _pad_line(c, inner_w)
            result.append(
                f"{M_AHEADER} {VT}{p}{VT}"
            )
            bar = HZ * (_visible_len(txt) + 4)
            b = f" {bar}"
            pb = _pad_line(b, inner_w)
            result.append(
                f"{M_AHEADER} {VT}{pb}{VT}"
            )
            continue

        # --- H1 ---
        if stripped.startswith("# "):
            txt = stripped[2:]
            c = f" ◆ {txt}"
            p = _pad_line(c, inner_w)
            result.append(
                f"{M_AHEADER} {VT}{p}{VT}"
            )
            bar = "═" * (_visible_len(txt) + 4)
            b = f" {bar}"
            pb = _pad_line(b, inner_w)
            result.append(
                f"{M_AHEADER} {VT}{pb}{VT}"
            )
            continue

        # --- Bullet ---
        bm = re.match(
            r"^(\s*)[-*]\s+(.*)", stripped
        )
        if bm:
            ind = bm.group(1)
            con = bm.group(2)
            prefix = f"   {ind}• "
            _emit_wrapped(
                result, con, prefix,
                inner_w, M_MULTI,
            )
            continue

        # --- Numbered list ---
        nm = re.match(
            r"^(\d+)\.\s+(.*)", stripped
        )
        if nm:
            num = nm.group(1)
            con = nm.group(2)
            prefix = f"   {num}. "
            _emit_wrapped(
                result, con, prefix,
                inner_w, M_MULTI,
            )
            continue

        # --- Normal paragraph ---
        prefix = "   "
        _emit_wrapped(
            result, stripped, prefix,
            inner_w, M_MULTI,
        )

    return result


def _emit_wrapped(
    result, raw_text, prefix,
    inner_w, marker,
):
    """
    Word-wrap raw (unstyled) text, apply
    inline spans per wrapped line, then emit
    framed lines with the given marker.

    content_w is derived from inner_w and the
    actual visible prefix width — avoids the
    off-by-N overflow when prefix > 4 chars.

    Wrapping on raw text prevents inline span
    markers from being split across lines,
    which would cause control chars to bleed
    through as visible ^A/^B characters.
    """
    prefix_w = _visible_len(prefix)
    content_w = inner_w - prefix_w
    wrapped = _wrap_text(raw_text, content_w)
    indent = " " * prefix_w

    for i, wline in enumerate(wrapped):
        styled = _inline(wline)
        if i == 0:
            c = f"{prefix}{styled}"
        else:
            c = f"{indent}{styled}"
        p = _pad_line(c, inner_w)
        result.append(
            f"{marker} {VT}{p}{VT}"
        )


# ===================================================
# Follow-up detection
# ===================================================
def _extract_follow_ups(text):
    """Strip trailing follow-ups JSON block.
    Handles plain JSON and ```json code fences.
    Returns (clean_text, questions_list).
    Returns (text, []) when not found."""
    if '"follow_ups"' not in text:
        return text, []
    key_idx = text.rfind('"follow_ups"')
    brace = text.rfind('{', 0, key_idx)
    if brace == -1:
        return text, []
    try:
        obj, end = json.JSONDecoder().raw_decode(
            text, brace
        )
        # Only strip if nothing but whitespace
        # or a closing code fence follows the JSON
        tail = text[end:].strip()
        if tail and tail != '```':
            return text, []
        qs = obj.get("follow_ups", [])
        if not (isinstance(qs, list) and qs):
            return text, []
        # Strip optional opening code fence
        strip_from = brace
        prefix = text[:brace].rstrip()
        if prefix.endswith('```json'):
            strip_from = len(prefix) - 7
        elif prefix.endswith('```'):
            strip_from = len(prefix) - 3
        return text[:strip_from].rstrip(), qs
    except (json.JSONDecodeError, ValueError):
        return text, []


def _show_follow_up_dialog(app, questions):
    """Floating follow-up menu after response.
    Populates input_area on selection; Escape
    dismisses with no side effect."""
    def on_select(idx):
        input_area.buffer.set_document(
            Document(text=questions[idx]),
            bypass_readonly=True,
        )
        app.layout.focus(input_area)

    _dlg.show_menu_dialog(
        app,
        title="Follow-up questions",
        options=questions,
        on_select=on_select,
        refocus=input_area,
    )


# ===================================================
# Main Buffer
# ===================================================
main_buffer = Buffer(
    name="main_output",
    read_only=True,
)

tool_output_buffer = Buffer(
    name="tool_output",
    read_only=True,
)

logs_buffer = Buffer(
    name="logs",
    read_only=True,
)

context_buffer = Buffer(
    name="context_view",
    read_only=True,
)


# ===================================================
# Buffer Registry
# ===================================================
class BufferRegistry:
    """
    Central registry of all named buffers.
    Buffers may or may not have an open tab.
    Lookup is case-insensitive.
    """

    def __init__(self):
        # lower_name -> (canonical_name, buffer)
        self._entries = {}

    def register(self, name, buffer):
        self._entries[name.lower()] = (
            name, buffer
        )

    def get(self, name):
        e = self._entries.get(name.lower())
        return e[1] if e else None

    def canonical(self, name):
        e = self._entries.get(name.lower())
        return e[0] if e else None

    def list_all(self):
        """Return list of (canonical_name, buffer)."""
        return list(self._entries.values())


buf_reg = BufferRegistry()


def _buf_append(buf, text):
    """Append text to any read-only Buffer."""
    current = buf.text
    new = current + "\n" + text if current else text
    buf.set_document(
        Document(
            text=new,
            cursor_position=len(new),
        ),
        bypass_readonly=True,
    )


def append_text(text):
    """Append text and cursor to end."""
    _buf_append(main_buffer, text)
    tab_mgr.tabs[0].scroll_pos = 0


def append_tool_output(text):
    """Append plain text to Tool Output tab."""
    _buf_append(tool_output_buffer, text)
    for _t in tab_mgr.tabs:
        if _t.buffer is tool_output_buffer:
            _t.scroll_pos = 0
            break


def append_log(text):
    """Append plain text to Logs tab."""
    _buf_append(logs_buffer, text)
    for _t in tab_mgr.tabs:
        if _t.buffer is logs_buffer:
            _t.scroll_pos = 0
            break


def replace_last_block(
    old_lines, new_text
):
    """Replace last N lines with new text."""
    current = main_buffer.text
    lines = current.split("\n")
    keep = lines[:len(lines) - old_lines]
    new = "\n".join(keep)
    if new:
        new = new + "\n" + new_text
    else:
        new = new_text
    main_buffer.set_document(
        Document(
            text=new,
            cursor_position=len(new),
        ),
        bypass_readonly=True,
    )
    tab_mgr.tabs[0].scroll_pos = 0


# ---------------------------------------------------
# Welcome banner
# ---------------------------------------------------
def make_welcome():
    """Build welcome banner with markers."""
    w = frame_width()
    inner = w - 2

    lines = []
    lines.append(f"{M_PLAIN}")

    lines.append(
        f"{M_AFRAME} {TL}{HZ * inner}{TR}"
    )
    lines.append(
        f"{M_ACONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    _art = [
        (
            "  · ★ · ✦ · ★ · ✦ · ★ · ✦ · ★ · ✦ ·",
            M_DIM,
        ),
        (
            " _____ _____  _    ____  ____  __   __",
            M_AHEADER,
        ),
        (
            "/ ___||_   _|/ \\  |  _ \\|  _ \\ \\ \\ / /",
            M_AHEADER,
        ),
        (
            "\\___ \\  | | / _ \\ | |_) | |_) | \\ V / ",
            M_AHEADER,
        ),
        (
            " ___) | | |/ ___ \\|  _ <|  _ <   | |  ",
            M_AHEADER,
        ),
        (
            "|____/ |_|/_/   \\_\\_| \\_\\_| \\_\\  |_|  ",
            M_AHEADER,
        ),
        (
            "  · ✦ · ★ · ✦ · ★ · ✦ · ★ · ✦ · ★ ·",
            M_DIM,
        ),
    ]
    for _al, _am in _art:
        _ap = _pad_line(_al, inner)
        lines.append(
            f"{_am} {VT}{_ap}{VT}"
        )
    lines.append(
        f"{M_ACONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    sub = (
        f"   Tokyo Night · prompt_toolkit"
        f" · {VERSION}"
    )
    ps = _pad_line(sub, inner)
    lines.append(
        f"{M_DIM} {VT}{ps}{VT}"
    )
    lines.append(
        f"{M_ACONTENT} {VT}"
        f"{' ' * inner}{VT}"
    )
    lines.append(
        f"{M_AFRAME} {BL}{HZ * inner}{BR}"
    )
    lines.append(f"{M_PLAIN}")
    lines.append(
        f"{M_PLAIN}"
        "   Welcome, Architect."
    )
    lines.append(
        f"{M_PLAIN}"
        "   Type a command below."
        " /exit to quit."
        " /setup for config."
    )
    lines.append(
        f"{M_PLAIN}"
        "   PgUp/PgDn or mouse wheel"
        " to scroll."
    )
    lines.append(f"{M_PLAIN}")
    return "\n".join(lines)


# ===================================================
# SIMULATED AI (kept for reference)
# ===================================================
# AI_RESPONSES = [
#     (
#         "## Análisis Completo\n"
#         "\n"
#         "He revisado los logs del sistema "
#         "e identifiqué **3 anomalías** "
#         "en los patrones de tráfico de "
#         "red.\n"
#         "\n"
#         "### Hallazgos Clave\n"
#         "\n"
#         "- Pico en conexiones salientes "
#         "a las 03:14 UTC en el puerto "
#         "`8443`\n"
#         "- Patrón inusual de resolución "
#         "DNS desde la subred "
#         "`10.0.3.0/24`\n"
#         "- Desajuste de certificado en "
#         "el endpoint del "
#         "***ingress controller***\n"
#         "\n"
#         "### Acciones Recomendadas\n"
#         "\n"
#         "1. Rotar los certificados TLS "
#         "en los endpoints afectados\n"
#         "2. Auditar las reglas de firewall "
#         "para egreso en puerto `8443`\n"
#         "3. Habilitar logging verbose "
#         "en el resolver DNS\n"
#         "\n"
#         "¿Genero el playbook de "
#         "remediación?"
#     ),
#     (
#         "## Escaneo de Infraestructura\n"
#         "\n"
#         "Ejecutando inventario en todos "
#         "los nodos registrados...\n"
#         "\n"
#         "```\n"
#         "  NODO        ESTADO   CARGA\n"
#         "  lico1       ● UP     0.42\n"
#         "  lico2       ● UP     0.78\n"
#         "  edge-gw     ● UP     0.15\n"
#         "  kv-store    ○ WARN   0.91\n"
#         "```\n"
#         "\n"
#         "El nodo `kv-store` opera al "
#         "**91% de capacidad**. "
#         "Considere escalar la instancia "
#         "o habilitar *page eviction* "
#         "en la capa de caché KV.\n"
#         "\n"
#         "La presión de memoria es el "
#         "cuello de botella probable "
#         "según el perfil de asignación."
#     ),
#     (
#         "## Tarea Aceptada\n"
#         "\n"
#         "Procesaré esa solicitud ahora. "
#         "Aquí un resumen del plan de "
#         "ejecución:\n"
#         "\n"
#         "**Fase 1**: Validar entradas "
#         "y verificar dependencias\n"
#         "**Fase 2**: Ejecutar el pipeline "
#         "principal de transformación\n"
#         "**Fase 3**: Verificar salidas "
#         "contra el esquema\n"
#         "\n"
#         "Estimación: ~12s\n"
#         "Todos los artefactos intermedios "
#         "se registrarán en la "
#         "transcripción de sesión."
#     ),
# ]
#
#
# async def simulate_ai_response(app):
#     """
#     Show spinner ~1s, then stream AI
#     response chunk by chunk (simulated).
#     KEPT FOR REFERENCE — replaced by
#     handle_ai_response() below.
#     """
#     telemetry.ai_status = "thinking"
#
#     spinner_text = build_thinking_frame(
#         SPINNER[0]
#     )
#     append_text(spinner_text)
#     app.invalidate()
#
#     spin_lines = (
#         spinner_text.count("\n") + 1
#     )
#     for tick in range(20):
#         await asyncio.sleep(0.1)
#         ch = telemetry.next_spinner()
#         new_think = build_thinking_frame(ch)
#         replace_last_block(
#             spin_lines, new_think
#         )
#         app.invalidate()
#
#     replace_last_block(spin_lines, "")
#     telemetry.ai_status = "streaming"
#     app.invalidate()
#
#     md_full = random.choice(AI_RESPONSES)
#     words = md_full.split(" ")
#     accumulated = ""
#     prev_lc = 0
#
#     for i, word in enumerate(words):
#         accumulated += word
#         if i < len(words) - 1:
#             accumulated += " "
#
#         is_last = (i == len(words) - 1)
#         if not is_last and len(word) < 3:
#             continue
#
#         frame_text = build_ai_frame(
#             accumulated
#         )
#         new_lc = (
#             frame_text.count("\n") + 1
#         )
#
#         if prev_lc > 0:
#             replace_last_block(
#                 prev_lc, frame_text
#             )
#         else:
#             append_text(frame_text)
#
#         prev_lc = new_lc
#         app.invalidate()
#
#         if not is_last:
#             await asyncio.sleep(
#                 random.uniform(0.02, 0.06)
#             )
#
#     telemetry.ai_status = "idle"
#     app.invalidate()


# ===================================================
# Agent buffer helpers
# ===================================================

def _agent_chat_buf(name):
    """Return agent chat Buffer or None."""
    return buf_reg.get(f"agent:{name}:chat")


def _agent_log_buf(name):
    """Return agent log Buffer or None."""
    return buf_reg.get(f"agent:{name}:log")


def _append_agent_buf(name, text):
    """Append text to agent chat buffer."""
    buf = _agent_chat_buf(name)
    if buf:
        _buf_append(buf, text)


def _replace_buf_last(buf, old_lines, new_text):
    """Replace last N lines in a buffer."""
    current = buf.text
    lines = current.split("\n")
    keep = lines[:len(lines) - old_lines]
    new = "\n".join(keep)
    if new:
        new = new + "\n" + new_text
    else:
        new = new_text
    buf.set_document(
        Document(
            text=new,
            cursor_position=len(new),
        ),
        bypass_readonly=True,
    )


def _spawn_agent_bufs(app, name):
    """Create chat + log buffers for a named agent."""
    from prompt_toolkit.buffer import Buffer
    chat_buf = Buffer(
        name=f"agent_{name}_chat",
        read_only=False,
    )
    log_buf = Buffer(
        name=f"agent_{name}_log",
        read_only=True,
    )
    buf_reg.register(
        f"agent:{name}:chat", chat_buf
    )
    buf_reg.register(
        f"agent:{name}:log", log_buf
    )
    new_tab = Tab(
        f"Agent:{name}", chat_buf,
        read_only=False,
    )
    tab_mgr.tabs.append(new_tab)
    tab_mgr.active = len(tab_mgr.tabs) - 1
    app.invalidate()
    return chat_buf, log_buf


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


async def _do_kill_agent(app, name):
    """Kill agent session and close TUI buffers."""
    global _active_registry
    if _active_registry is not None and (
        _da_pool is not None
    ):
        await _active_registry.kill_agent(
            name, _da_pool
        )
        if _da_session is not None:
            _da_session.inject_system_message(
                f'[System] Agent "{name}" has'
                f' been terminated and is no'
                f' longer available.'
            )
    _close_agent_bufs(name)
    tab_mgr.goto_tab(0)
    app.invalidate()


def _on_agent_log(name, direction, text):
    """Write LLM↔agent traffic to log buffer."""
    log_buf = _agent_log_buf(name)
    if log_buf is None:
        from prompt_toolkit.buffer import Buffer
        log_buf = Buffer(
            name=f"agent_{name}_log",
            read_only=True,
        )
        buf_reg.register(
            f"agent:{name}:log", log_buf
        )
    _buf_append(
        log_buf,
        f"[{direction}] {text}"
    )


# ===================================================
# Agent session response handler
# ===================================================
async def handle_agent_response(
    app, user_input, session, agent_name
):
    """Stream an agent session response into its
    chat buffer. Mirrors handle_ai_response but
    writes to the agent's dedicated buffer.
    """
    chat_buf = _agent_chat_buf(agent_name)
    if chat_buf is None or session is None:
        return

    def _abuf(text):
        _buf_append(chat_buf, text)
        app.invalidate()

    session.mode = _exec_mode
    session.arm_confirm_queue()

    telemetry.ai_status = "thinking"
    spinner_text = build_thinking_frame(
        SPINNER[0]
    )
    _abuf(spinner_text)
    spin_lines = spinner_text.count("\n") + 1
    stop_spinner = asyncio.Event()

    async def _spin():
        while not stop_spinner.is_set():
            await asyncio.sleep(0.1)
            ch = telemetry.next_spinner()
            _replace_buf_last(
                chat_buf,
                spin_lines,
                build_thinking_frame(ch),
            )
            app.invalidate()

    spin_task = asyncio.ensure_future(_spin())
    accumulated = ""
    prev_lc = 0

    try:
        async for event in session.chat_auto(
            user_input
        ):
            if not stop_spinner.is_set():
                stop_spinner.set()
                await spin_task
                _replace_buf_last(
                    chat_buf, spin_lines, ""
                )
                telemetry.ai_status = "streaming"
                app.invalidate()
            if event.type == "token":
                accumulated += str(event.data)
                frame_text = build_ai_frame(
                    accumulated
                )
                new_lc = (
                    frame_text.count("\n") + 1
                )
                if prev_lc > 0:
                    _replace_buf_last(
                        chat_buf,
                        prev_lc,
                        frame_text,
                    )
                else:
                    _abuf(frame_text)
                prev_lc = new_lc
                app.invalidate()
            elif event.type == "done":
                if not accumulated:
                    raw = str(event.data)
                    clean, fups = (
                        _extract_follow_ups(raw)
                    )
                    _abuf(build_ai_frame(clean))
                    if fups:
                        _show_follow_up_dialog(
                            app, fups
                        )
                break
            elif event.type == "error":
                _abuf(
                    build_error_frame(
                        str(event.data)
                    )
                )
                break
        if accumulated and prev_lc > 0:
            clean, fups = (
                _extract_follow_ups(accumulated)
            )
            if fups:
                frame = build_ai_frame(clean)
                _replace_buf_last(
                    chat_buf, prev_lc, frame
                )
                prev_lc = frame.count("\n") + 1
                _show_follow_up_dialog(
                    app, fups
                )
                app.invalidate()
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


# ===================================================
# Real LLM handler
# ===================================================
async def handle_ai_response(
    app, user_input, session
):
    """
    Stream a real LLM response into the TUI.
    Uses session.chat_auto() which selects tools
    based on the current execution mode.
    Handles token, tool_call, tool_result, done,
    and error events.
    """
    if session is None:
        append_text(
            build_error_frame(
                "No LLM session available. "
                "Check .env and config."
            )
        )
        app.invalidate()
        return

    # Sync exec mode to the session
    session.mode = _exec_mode

    # Arm the session so it will pause for
    # user approval before write tools
    # (bash/edit/write) or when
    # require_confirmation is set.
    session.arm_confirm_queue()

    telemetry.ai_status = "thinking"
    spinner_text = build_thinking_frame(
        SPINNER[0]
    )
    append_text(spinner_text)
    app.invalidate()

    spin_lines = (
        spinner_text.count("\n") + 1
    )
    stop_spinner = asyncio.Event()

    async def _spin():
        while not stop_spinner.is_set():
            await asyncio.sleep(0.1)
            ch = telemetry.next_spinner()
            replace_last_block(
                spin_lines,
                build_thinking_frame(ch),
            )
            app.invalidate()

    spin_task = asyncio.ensure_future(_spin())

    accumulated = ""
    prev_lc = 0

    try:
        async for event in session.chat_auto(
            user_input
        ):
            if not stop_spinner.is_set():
                stop_spinner.set()
                await spin_task
                replace_last_block(
                    spin_lines, ""
                )
                telemetry.ai_status = "streaming"
                app.invalidate()
            if event.type == "token":
                accumulated += str(event.data)
                frame_text = build_ai_frame(
                    accumulated
                )
                new_lc = (
                    frame_text.count("\n") + 1
                )
                if prev_lc > 0:
                    replace_last_block(
                        prev_lc, frame_text
                    )
                else:
                    append_text(frame_text)
                prev_lc = new_lc
                app.invalidate()

            elif event.type == "tool_call":
                d = event.data
                name = d.get("name", "?")
                args = d.get("args", {})
                arg_parts = []
                for k, v in args.items():
                    v_str = str(v)
                    if len(v_str) > 60:
                        v_str = v_str[:57] + "..."
                    arg_parts.append(
                        f"{k}={v_str!r}"
                    )
                arg_str = ", ".join(arg_parts)
                msg = f"tool:{name}({arg_str})"
                append_text(
                    build_warn_frame(msg)
                )
                append_tool_output(
                    f"▶ {msg}"
                )
                # Reset so the next token event
                # opens a fresh AI frame after the
                # tool frames rather than replacing
                # the lines above.
                prev_lc = 0
                accumulated = ""
                app.invalidate()

            elif event.type == "tool_result":
                d = event.data
                name = d.get("name", "?")
                result = d.get("result", "")
                preview = (
                    result[:120] + "…"
                    if len(result) > 120
                    else result
                )
                msg = (
                    f"`{name}` → {preview}"
                )
                append_text(
                    build_inline_notif(msg, "→")
                )
                append_tool_output(
                    f"◀ {msg}"
                )
                app.invalidate()

            elif event.type == "provider_fallback":
                append_text(
                    build_warn_frame(
                        "Provider failed, switched"
                        f" to fallback: {event.data}"
                    )
                )
                app.invalidate()

            elif event.type == (
                "tool_confirm_request"
            ):
                d = event.data
                name = d.get("name", "?")
                args = d.get("args", {})
                args_key = json.dumps(
                    args, sort_keys=True
                )
                if (
                    name in _auto_approved
                    and args_key
                    in _auto_approved[name]
                ):
                    append_text(
                        build_inline_notif(
                            f"Auto-approved:"
                            f" {name}",
                            "✓",
                        )
                    )
                    if session is not None:
                        session.send_confirm(True)
                    app.invalidate()
                else:
                    a_str = str(args)
                    preview = (
                        a_str[:60] + "…"
                        if len(a_str) > 60
                        else a_str
                    )
                    title = (
                        f"Run [{name}]"
                        f" {preview}?"
                    )
                    opts = [
                        "Yes, once",
                        "Yes, always"
                        " this session",
                        "No",
                    ]

                    def on_confirm(
                        idx,
                        _name=name,
                        _key=args_key,
                        _sess=session,
                    ):
                        chosen = opts[idx]
                        approved = (
                            chosen != "No"
                        )
                        if chosen == (
                            "Yes, always"
                            " this session"
                        ):
                            if _name not in (
                                _auto_approved
                            ):
                                _auto_approved[
                                    _name
                                ] = set()
                            _auto_approved[
                                _name
                            ].add(_key)
                        if _sess is not None:
                            _sess.send_confirm(
                                approved
                            )

                    sel_menu.show(
                        title,
                        opts,
                        on_confirm,
                        white=True,
                    )
                    menu_text = (
                        sel_menu.build_frame()
                    )
                    sel_menu._prev_lines = (
                        menu_text.count("\n")
                        + 1
                    )
                    append_text(menu_text)
                    app.invalidate()

            elif event.type == (
                "tool_question_request"
            ):
                global _tui_input_mode
                global _pending_questions
                d = event.data
                qs = d.get("questions", [])
                _pending_questions = list(qs)
                _tui_input_mode = "question"
                append_text(
                    build_question_frame(qs)
                )
                app.invalidate()

            elif event.type == "done":
                if not accumulated:
                    raw = str(event.data)
                    clean, fups = (
                        _extract_follow_ups(raw)
                    )
                    frame_text = build_ai_frame(
                        clean
                    )
                    if prev_lc > 0:
                        replace_last_block(
                            prev_lc, frame_text
                        )
                    else:
                        append_text(frame_text)
                    app.invalidate()
                    if fups:
                        _show_follow_up_dialog(
                            app, fups
                        )
                if (
                    tab_mgr.active_buffer()
                    is context_buffer
                ):
                    _refresh_context_buffer()
                    app.invalidate()

            elif event.type == "error":
                err_msg = str(event.data)
                append_text(
                    build_error_frame(err_msg)
                )
                app.invalidate()
                if session is not None:
                    session.fire_event(
                        "on_error",
                        error_message=err_msg,
                    )
                break
        if accumulated and prev_lc > 0:
            clean, fups = (
                _extract_follow_ups(accumulated)
            )
            if fups:
                frame = build_ai_frame(clean)
                replace_last_block(
                    prev_lc, frame
                )
                prev_lc = frame.count("\n") + 1
                _show_follow_up_dialog(
                    app, fups
                )
                app.invalidate()
    except Exception as exc:
        err_msg = str(exc)
        append_text(
            build_error_frame(err_msg)
        )
        app.invalidate()
        if session is not None:
            session.fire_event(
                "on_error",
                error_message=err_msg,
            )
    finally:
        try:
            if not stop_spinner.is_set():
                stop_spinner.set()
                await spin_task
                replace_last_block(
                    spin_lines, ""
                )
                app.invalidate()
        except asyncio.CancelledError:
            replace_last_block(spin_lines, "")
            app.invalidate()
        session.clear_interaction_queues()
        _tui_input_mode = "chat"
        _pending_questions.clear()

    telemetry.ai_status = "idle"
    app.invalidate()
    _check_autosummarize(app)


async def _run_ask_subagent(app, question):
    """One-shot subagent. Shares parent context,
    does not modify main session history."""
    if _da_pool is None or _da_settings is None:
        append_text(
            build_error_frame("Pool not available.")
        )
        app.invalidate()
        return

    try:
        sub = await _da_pool.spawn(
            role=_active_role(),
            provider=_active_provider(),
        )
    except Exception as exc:
        append_text(
            build_error_frame(str(exc))
        )
        app.invalidate()
        return

    if _da_session is not None:
        sub._history = list(
            _da_session.get_history()
        )

    q_preview = question[:60]
    append_text(
        build_inline_notif(
            f"subagent ({_active_role()}): {q_preview}",
            "◈",
        )
    )
    app.invalidate()

    accumulated = ""
    prev_lc = 0
    try:
        async for event in sub.chat(question):
            if event.type == "token":
                accumulated += str(event.data)
                frame_text = build_ai_frame(
                    accumulated
                )
                new_lc = (
                    frame_text.count("\n") + 1
                )
                if prev_lc > 0:
                    replace_last_block(
                        prev_lc, frame_text
                    )
                else:
                    append_text(frame_text)
                prev_lc = new_lc
                app.invalidate()
            elif event.type == "error":
                append_text(
                    build_error_frame(
                        str(event.data)
                    )
                )
                app.invalidate()
    finally:
        try:
            await _da_pool.terminate(sub.id)
        except Exception:
            pass


async def _run_summarize(app):
    """Summarize the current conversation via a
    sub-session.  Saves the result to a dated file
    and offers continue options via sel_menu.
    """
    if _da_pool is None or _da_session is None:
        append_text(
            build_error_frame(
                "No session available."
            )
        )
        app.invalidate()
        return

    history = _da_session.get_history()
    if not history:
        append_text(
            build_inline_notif(
                "No conversation to summarize.",
                "💬",
            )
        )
        app.invalidate()
        return

    # Build prompt from conversation history
    conv_lines = []
    for m in history:
        role = m.role.upper()
        content = (m.content or "").strip()
        if content:
            conv_lines.append(
                f"[{role}]: {content}"
            )
    conv_text = "\n\n".join(conv_lines)
    prompt = (
        "Summarize the following conversation "
        "concisely, capturing key topics, "
        "decisions, and context needed to "
        "continue it:\n\n" + conv_text
    )

    # Show spinner while working
    telemetry.ai_status = "thinking"
    spinner_text = build_thinking_frame(
        SPINNER[0]
    )
    append_text(spinner_text)
    app.invalidate()
    spin_lines = spinner_text.count("\n") + 1
    stop_spinner = asyncio.Event()

    async def _spin():
        while not stop_spinner.is_set():
            await asyncio.sleep(0.1)
            ch = telemetry.next_spinner()
            replace_last_block(
                spin_lines,
                build_thinking_frame(ch),
            )
            app.invalidate()

    spin_task = asyncio.ensure_future(_spin())

    summary_text = None
    try:
        sub = await _da_pool.spawn(
            role=_active_role(),
            provider=_active_provider(),
        )
        summary_text = (
            await sub.chat_complete(prompt)
        )
    except Exception as exc:
        stop_spinner.set()
        await spin_task
        replace_last_block(spin_lines, "")
        append_text(
            build_error_frame(
                f"Summarization failed: {exc}"
            )
        )
        app.invalidate()
        telemetry.ai_status = "idle"
        return
    finally:
        if not stop_spinner.is_set():
            stop_spinner.set()
            await spin_task
            replace_last_block(spin_lines, "")
            app.invalidate()
        try:
            await _da_pool.terminate(sub.id)
        except Exception:
            pass

    telemetry.ai_status = "idle"

    # Save summary to file
    ts = datetime.now().strftime(
        "%m%d%Y-%H%M%S"
    )
    from starry_lib.sessions.store import (
        session_dir as _sdir,
    )
    _sd = _sdir(SESSION_NAME)
    fname = _sd / f"summary_{ts}.md"
    try:
        fname.write_text(
            "# Conversation Summary\n\n"
            f"Session: {SESSION_NAME}\n"
            f"Date: "
            f"{datetime.now().isoformat()}\n\n"
            f"---\n\n{summary_text}\n"
        )
    except Exception as exc:
        append_text(
            build_error_frame(
                f"Could not save summary: {exc}"
            )
        )
        app.invalidate()
        return

    append_text(
        build_inline_notif(
            f"Summary saved to: {fname}", "💾"
        )
    )
    app.invalidate()

    # Capture for use in callback closure
    _summary = summary_text

    def on_summarize_choice(idx):
        global _auto_approved, _autosum_triggered
        if idx == 1:
            # Clear and continue with summary
            if _da_session is not None:
                _da_session.clear_history()
                _da_session.reset_tokens()
                _autosum_triggered = False
                _da_session.active_skills.append(
                    "summary"
                )
                _da_session._internal_messages\
                    .append(
                    "Conversation summary "
                    f"(prior context):\n"
                    f"{_summary}"
                )
            _auto_approved.clear()
            welcome = make_welcome()
            main_buffer.set_document(
                Document(
                    text=welcome,
                    cursor_position=len(welcome),
                ),
                bypass_readonly=True,
            )
            append_text(
                build_inline_notif(
                    "New session started with "
                    "summary as context.",
                    "✓",
                )
            )
        else:
            append_text(
                build_inline_notif(
                    "Continuing conversation.",
                    "↩",
                )
            )
        app.invalidate()

    sel_menu.show(
        "Summary ready — what would you like?",
        [
            "1. Continue as is",
            "2. Clear all and start with"
            " this summary",
        ],
        on_summarize_choice,
        white=True,
    )
    menu_text = sel_menu.build_frame()
    sel_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    append_text(menu_text)
    app.invalidate()


# ===================================================
# Autosummarize
# ===================================================
def _check_autosummarize(app) -> None:
    """Check if the context has reached the
    autosummarize threshold and prompt the user
    if so.  Fires at most once per session
    (until context is cleared).
    """
    global _autosum_triggered

    if _autosum_triggered:
        return
    if not _autosum_enabled:
        return
    if _da_session is None:
        return

    ctx_win = _da_session.context_window
    if ctx_win:
        tok = _da_session.token_usage.get(
            "total", 0
        )
        pct = int(tok * 100 / ctx_win)
        if pct < _autosum_threshold:
            return
        label = (
            f"Context is at {pct}% capacity "
            f"({tok}/{ctx_win} tokens). "
            f"Threshold: {_autosum_threshold}%."
        )
    else:
        hist = _da_session.get_history()
        msg_count = len(hist)
        if msg_count < _autosum_msg_limit:
            return
        label = (
            f"Conversation has {msg_count} "
            f"messages (limit: "
            f"{_autosum_msg_limit})."
        )

    _autosum_triggered = True

    opts = [
        "1. Summarize now",
        "2. Continue without summarizing",
        "3. Disable autosummarize",
    ]

    def on_autosum(idx):
        global _autosum_enabled
        if idx == 0:
            asyncio.ensure_future(
                _run_summarize(app)
            )
        elif idx == 2:
            _autosum_enabled = False
            _save_user_prefs()
            append_text(
                build_inline_notif(
                    "Autosummarize disabled.",
                    "✓",
                )
            )
            app.invalidate()

    sel_menu.show(
        f"Auto-summarize — {label}",
        opts,
        on_autosum,
        white=True,
    )
    menu_text = sel_menu.build_frame()
    sel_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    append_text(menu_text)
    app.invalidate()


def _show_default_convo(app) -> None:
    """Floating sub-menu for default conversation
    parameters (system prompt, temperature, etc.)."""
    dc_opts = [
        "System prompt",
        "Temperature",
        "Max tokens",
        "Top-p",
    ]

    def _on_dc_select(idx):
        chosen = dc_opts[idx]
        if chosen == "System prompt":
            _edit_default_system_prompt(app)
        elif chosen == "Temperature":
            _edit_default_temperature(app)
        elif chosen == "Max tokens":
            _edit_default_max_tokens(app)
        elif chosen == "Top-p":
            _edit_default_top_p(app)

    _dlg.show_menu_dialog(
        app,
        title="Default conversation",
        options=dc_opts,
        on_select=_on_dc_select,
        refocus=input_area,
    )


def _edit_default_system_prompt(app) -> None:
    """Dialog to view and edit the default system
    prompt that is prepended to every role prompt."""
    global _default_system_prompt
    label = (
        "SYSTEM PROMPT: The global instruction"
        " preamble sent to the model on every"
        " session. Each role's own prompt is"
        " appended after this text."
    )
    if _default_system_prompt.strip():
        current = _default_system_prompt
    elif (
        _da_settings is not None
        and _active_role() in _da_settings.agents
    ):
        current = (
            _da_settings
            .agents[_active_role()]
            .system_prompt
        )
    else:
        current = ""

    def _on_confirm(text):
        global _default_system_prompt
        _default_system_prompt = text
        _save_user_prefs()
        _apply_session_overrides(_da_session)
        append_text(
            build_inline_notif(
                "Default system prompt updated.",
                "✓",
            )
        )
        app.invalidate()

    _dlg.show_input_dialog(
        app,
        title="System prompt",
        label=label,
        on_confirm=_on_confirm,
        multiline=True,
        field_height=8,
        initial_text=current,
        refocus=input_area,
    )


def _edit_default_temperature(app) -> None:
    """Dialog to set the default temperature."""
    global _default_temperature
    label = (
        "TEMPERATURE: Sampling randomness"
        " (0.0 = focused, 2.0 = creative)."
        " Role values override this default."
    )
    if _default_temperature is not None:
        cur = str(_default_temperature)
    elif (
        _da_settings is not None
        and _active_role() in _da_settings.agents
    ):
        t = _da_settings.agents[_active_role()].temperature
        cur = str(t) if t is not None else ""
    else:
        cur = ""

    def _on_confirm(text):
        global _default_temperature
        text = text.strip()
        if not text:
            _default_temperature = None
            _save_user_prefs()
            _apply_session_overrides(_da_session)
            append_text(
                build_inline_notif(
                    "Default temperature cleared.",
                    "✓",
                )
            )
            app.invalidate()
            return
        try:
            val = float(text)
            if not 0.0 <= val <= 2.0:
                raise ValueError
        except ValueError:
            append_text(
                build_warn_frame(
                    f"Invalid temperature: {text!r}."
                    " Enter a float 0.0–2.0."
                )
            )
            app.invalidate()
            return
        _default_temperature = val
        _save_user_prefs()
        _apply_session_overrides(_da_session)
        append_text(
            build_inline_notif(
                f"Default temperature → {val}.",
                "✓",
            )
        )
        app.invalidate()

    _dlg.show_input_dialog(
        app,
        title="Temperature",
        label=label,
        on_confirm=_on_confirm,
        initial_text=cur,
        refocus=input_area,
    )


def _edit_default_max_tokens(app) -> None:
    """Dialog to set the default max_tokens."""
    global _default_max_tokens
    label = (
        "MAX TOKENS: Maximum tokens in each"
        " model response. Leave blank to use"
        " the model's default. Role values"
        " override this default."
    )
    cur = (
        str(_default_max_tokens)
        if _default_max_tokens is not None
        else ""
    )

    def _on_confirm(text):
        global _default_max_tokens
        text = text.strip()
        if not text:
            _default_max_tokens = None
            _save_user_prefs()
            _apply_session_overrides(_da_session)
            append_text(
                build_inline_notif(
                    "Default max tokens cleared.",
                    "✓",
                )
            )
            app.invalidate()
            return
        try:
            val = int(text)
            if val <= 0:
                raise ValueError
        except ValueError:
            append_text(
                build_warn_frame(
                    f"Invalid value: {text!r}."
                    " Enter a positive integer."
                )
            )
            app.invalidate()
            return
        _default_max_tokens = val
        _save_user_prefs()
        _apply_session_overrides(_da_session)
        append_text(
            build_inline_notif(
                f"Default max tokens → {val}.",
                "✓",
            )
        )
        app.invalidate()

    _dlg.show_input_dialog(
        app,
        title="Max tokens",
        label=label,
        on_confirm=_on_confirm,
        initial_text=cur,
        refocus=input_area,
    )


def _edit_default_top_p(app) -> None:
    """Dialog to set the default top-p."""
    global _default_top_p
    label = (
        "TOP-P: Nucleus sampling threshold"
        " (0.0–1.0). Limits the probability"
        " mass the model samples from."
        " Role values override this default."
    )
    cur = (
        str(_default_top_p)
        if _default_top_p is not None
        else ""
    )

    def _on_confirm(text):
        global _default_top_p
        text = text.strip()
        if not text:
            _default_top_p = None
            _save_user_prefs()
            _apply_session_overrides(_da_session)
            append_text(
                build_inline_notif(
                    "Default top-p cleared.",
                    "✓",
                )
            )
            app.invalidate()
            return
        try:
            val = float(text)
            if not 0.0 <= val <= 1.0:
                raise ValueError
        except ValueError:
            append_text(
                build_warn_frame(
                    f"Invalid top-p: {text!r}."
                    " Enter a float 0.0–1.0."
                )
            )
            app.invalidate()
            return
        _default_top_p = val
        _save_user_prefs()
        _apply_session_overrides(_da_session)
        append_text(
            build_inline_notif(
                f"Default top-p → {val}.",
                "✓",
            )
        )
        app.invalidate()

    _dlg.show_input_dialog(
        app,
        title="Top-p",
        label=label,
        on_confirm=_on_confirm,
        initial_text=cur,
        refocus=input_area,
    )


def _show_user_personalization(app) -> None:
    """Sequential dialogs to set user name and
    profile, appended to the system prompt."""

    def _ask_profile(saved_name):
        label = (
            "USER PROFILE: Your profession or"
            " background (optional). The model"
            " uses this to tailor responses."
            " Leave blank for the default."
        )
        cur = _user_profile or "Human user"

        def _on_profile(text):
            global _user_name, _user_profile
            _user_name = saved_name or "User"
            _user_profile = text or "Human user"
            _save_user_prefs()
            _apply_session_overrides(_da_session)
            append_text(
                build_inline_notif(
                    "User personalization saved.",
                    "✓",
                )
            )
            app.invalidate()

        _dlg.show_input_dialog(
            app,
            title="User profile",
            label=label,
            on_confirm=_on_profile,
            multiline=True,
            field_height=4,
            initial_text=cur,
            refocus=input_area,
        )

    label = (
        "USER NAME: How you identify yourself"
        " to the model. Used in the system"
        " prompt so the model knows who it is"
        " talking to."
    )
    cur = _user_name or "User"
    _dlg.show_input_dialog(
        app,
        title="User name",
        label=label,
        on_confirm=_ask_profile,
        initial_text=cur,
        refocus=input_area,
    )


def _show_autosummarize_setup(app) -> None:
    """Sub-menu to configure autosummarize."""
    global _autosum_enabled
    global _autosum_threshold
    global _autosum_msg_limit

    ctx_win = (
        _da_session.context_window
        if _da_session is not None
        else None
    )
    state = "On" if _autosum_enabled else "Off"

    if ctx_win:
        thresh_label = (
            f"Set threshold % "
            f"(currently {_autosum_threshold}%)"
        )
    else:
        thresh_label = (
            f"Set message limit "
            f"(currently {_autosum_msg_limit})"
        )

    opts = [
        f"Enable / Disable (currently: {state})",
        thresh_label,
    ]

    def on_autosum_setup(idx):
        global _autosum_enabled
        global _autosum_threshold
        global _autosum_msg_limit

        if idx == 0:
            _autosum_enabled = not _autosum_enabled
            new_state = (
                "On" if _autosum_enabled else "Off"
            )
            _save_user_prefs()
            append_text(
                build_inline_notif(
                    f"Autosummarize: {new_state}.",
                    "✓",
                )
            )
            app.invalidate()

        elif idx == 1:
            if ctx_win:
                pct_opts = [
                    "50%", "60%", "70%",
                    "75%", "80%", "85%", "90%",
                ]
                pct_vals = [
                    50, 60, 70, 75, 80, 85, 90,
                ]

                def on_pct(pidx):
                    global _autosum_threshold
                    _autosum_threshold = (
                        pct_vals[pidx]
                    )
                    _save_user_prefs()
                    append_text(
                        build_inline_notif(
                            "Autosummarize threshold"
                            f" set to "
                            f"{_autosum_threshold}%.",
                            "✓",
                        )
                    )
                    app.invalidate()

                _dlg.show_menu_dialog(
                    app,
                    title=(
                        "Select threshold %"
                    ),
                    options=pct_opts,
                    on_select=on_pct,
                    refocus=input_area,
                )
            else:
                msg_opts = [
                    "5 messages",
                    "8 messages",
                    "10 messages",
                    "15 messages",
                    "20 messages",
                    "25 messages",
                ]
                msg_vals = [
                    5, 8, 10, 15, 20, 25,
                ]

                def on_msg(midx):
                    global _autosum_msg_limit
                    _autosum_msg_limit = (
                        msg_vals[midx]
                    )
                    _save_user_prefs()
                    append_text(
                        build_inline_notif(
                            "Autosummarize limit set"
                            f" to "
                            f"{_autosum_msg_limit}"
                            " messages.",
                            "✓",
                        )
                    )
                    app.invalidate()

                _dlg.show_menu_dialog(
                    app,
                    title="Select message limit",
                    options=msg_opts,
                    on_select=on_msg,
                    refocus=input_area,
                )

    _dlg.show_menu_dialog(
        app,
        title="AutoSummarize settings",
        options=opts,
        on_select=on_autosum_setup,
        refocus=input_area,
    )


# ===================================================
# Context buffer helpers
# ===================================================
def _format_context_markdown(snap: dict) -> str:
    """Render a context snapshot as a Markdown string."""
    tok = snap["token_usage"]
    cw = snap["context_window"]
    tok_str = str(tok["total"])
    if cw:
        pct = tok["total"] * 100 // cw
        tok_str += f" / {cw}  ({pct}%)"
    lines = [
        f"## Context — {snap['session_id']}",
        (
            f"Provider: {snap['provider']}"
            f"  |  Model: {snap['model']}"
        ),
        (
            f"Role: {snap['role']}"
            f"  |  Mode: {snap['mode']}"
        ),
        f"Tokens: {tok_str}",
    ]
    sep = "─" * 60
    turn = 0
    for msg in snap["messages"]:
        role = msg["role"]
        label = msg.get("label", role)
        if role == "user":
            turn += 1
            header = f"[user — turn {turn}]"
        elif role == "assistant":
            header = f"[assistant — turn {turn}]"
        elif role == "tool":
            header = "[tool result]"
        else:
            header = f"[system — {label}]"
        content = msg.get("content") or ""
        meta = msg.get("metadata", {})
        if (
            not content
            and meta.get("tool_calls")
        ):
            names = [
                tc.get("function", {}).get(
                    "name", "?"
                )
                for tc in meta["tool_calls"]
            ]
            content = (
                "[called: "
                + ", ".join(names)
                + "]"
            )
        lines.append(f"\n{sep}")
        lines.append(header)
        lines.append(content)
    return "\n".join(lines)


def _refresh_context_buffer() -> None:
    """Rewrite the Context buffer with the current state."""
    if _da_session is None:
        text = "No active session."
    else:
        snap = _da_session.get_context_snapshot()
        if _context_format == "json":
            text = json.dumps(snap, indent=2)
        else:
            text = _format_context_markdown(snap)
    context_buffer.set_document(
        Document(
            text=text,
            cursor_position=len(text),
        ),
        bypass_readonly=True,
    )


def _refresh_tool_output_buffer() -> None:
    """Rebuild Tool Output buffer from display_log."""
    if _da_session is None:
        text = "No active session."
    else:
        entries = [
            e for e in _da_session.display_log
            if e.get("type") in (
                "tool_call", "tool_result"
            )
        ]
        if not entries:
            text = (
                "(No tool calls in this session.)"
            )
        else:
            lines = []
            for e in entries:
                et = e.get("type", "")
                name = e.get("name", "?")
                if et == "tool_call":
                    args = e.get("args", {})
                    parts = []
                    for k, v in args.items():
                        vs = str(v)
                        if len(vs) > 60:
                            vs = vs[:57] + "..."
                        parts.append(
                            f"{k}={vs!r}"
                        )
                    astr = ", ".join(parts)
                    lines.append(
                        f"▶ tool:{name}({astr})"
                    )
                elif et == "tool_result":
                    result = str(
                        e.get("result", "")
                    )
                    preview = (
                        result[:120] + "…"
                        if len(result) > 120
                        else result
                    )
                    lines.append(
                        f"◀ {name} → {preview}"
                    )
            text = "\n".join(lines)
    tool_output_buffer.set_document(
        Document(
            text=text,
            cursor_position=len(text),
        ),
        bypass_readonly=True,
    )
    for _t in tab_mgr.tabs:
        if _t.buffer is tool_output_buffer:
            _t.scroll_pos = 0
            break


# ===================================================
# Session-override helpers
# ===================================================

def _build_user_persona_block() -> str:
    """Return the user persona system prompt block,
    or '' if no personalization has been saved."""
    if not _user_name and not _user_profile:
        return ""
    name = _user_name or "User"
    profile = _user_profile or "Human user"
    lines = [
        "---",
        "## User context",
        f"Name: {name}",
    ]
    if profile.strip():
        lines.append(f"Profile: {profile.strip()}")
    return "\n".join(lines)


def _apply_session_overrides(session) -> None:
    """Apply default system prompt, LLM params, and
    user persona to the live session agent.

    Call after pool.spawn(), switch_role(), or
    switch_provider().
    """
    if session is None or _da_settings is None:
        return
    role_cfg = _da_settings.agents.get(session.role)
    if role_cfg is None:
        return

    # System prompt: default + role + persona
    role_sys = role_cfg.system_prompt.strip()
    parts = []
    if _default_system_prompt.strip():
        parts.append(
            _default_system_prompt.strip()
        )
    if role_sys:
        parts.append(role_sys)
    persona = _build_user_persona_block()
    if persona:
        parts.append(persona)
    if parts:
        session._agent.system_prompt = (
            "\n\n".join(parts)
        )

    # LLM params: role overrides default
    if (
        role_cfg.temperature is None
        and _default_temperature is not None
    ):
        session._agent.temperature = (
            _default_temperature
        )
    if (
        role_cfg.max_tokens is None
        and _default_max_tokens is not None
    ):
        session._agent.max_tokens = (
            _default_max_tokens
        )
    if (
        role_cfg.top_p is None
        and _default_top_p is not None
    ):
        session._agent.top_p = _default_top_p


# ===================================================
# /setup helpers
# ===================================================
def _show_providers(app):
    """
    Display all configured providers as a
    white-framed list in the scroll buffer.
    """
    if _da_settings is None:
        append_text(
            build_warn_frame(
                "Settings not loaded."
            )
        )
        app.invalidate()
        return
    items = []
    for pcfg in da.list_providers(
        _da_settings
    ):
        pname = pcfg.name
        tag = (
            " ◀ active"
            if pname == _active_provider()
            else ""
        )
        items.append(
            f"{pcfg.label} ({pname}){tag}"
        )
    append_text(
        build_setup_list_frame(
            "Configured Providers", items
        )
    )
    append_text(
        build_inline_notif(
            "Done. StarryCLI is ready", "✓"
        )
    )
    app.invalidate()


def _show_list_providers_dlg(app):
    """Show configured providers in a dialog."""
    if _da_settings is None:
        _dlg.show_button_dialog(
            app,
            title="Providers",
            message="Settings not loaded.",
            buttons=["Close"],
            on_button=lambda _: None,
            width=44,
            refocus=input_area,
        )
        return
    lines = []
    for pcfg in da.list_providers(
        _da_settings
    ):
        tag = (
            " ◀ active"
            if pcfg.name == _active_provider()
            else ""
        )
        lines.append(
            f"{pcfg.label} ({pcfg.name}){tag}"
        )
    msg = (
        "\n".join(lines)
        if lines
        else "No providers configured."
    )
    _dlg.show_button_dialog(
        app,
        title="Configured Providers",
        message=msg,
        buttons=["Close"],
        on_button=lambda _: None,
        width=56,
        refocus=input_area,
    )


def _show_remove_provider(app):
    """Menu to select and remove a provider."""
    if _da_settings is None:
        _dlg.show_button_dialog(
            app,
            title="Remove Provider",
            message="Settings not loaded.",
            buttons=["Close"],
            on_button=lambda _: None,
            width=44,
            refocus=input_area,
        )
        return
    providers = da.list_providers(
        _da_settings
    )
    if not providers:
        _dlg.show_button_dialog(
            app,
            title="Remove Provider",
            message="No providers configured.",
            buttons=["Close"],
            on_button=lambda _: None,
            width=44,
            refocus=input_area,
        )
        return
    labels = []
    for pcfg in providers:
        tag = (
            " ◀ active"
            if pcfg.name == _active_provider()
            else ""
        )
        labels.append(
            f"{pcfg.label} ({pcfg.name}){tag}"
        )

    def on_select(idx):
        pcfg = providers[idx]
        is_active = (
            pcfg.name == _active_provider()
        )
        if is_active:
            msg = (
                f"WARNING: '{pcfg.name}' is"
                " the ACTIVE provider.\n"
                "Removing it will leave no"
                " active provider.\n"
                "\nRemove it anyway?"
            )
        else:
            msg = (
                f"Remove provider"
                f" '{pcfg.name}'?"
            )

        def on_btn(bidx):
            if bidx != 1:
                return
            global _da_settings
            cfg_path, _ = (
                da.get_default_paths()
            )
            try:
                da.remove_provider(
                    cfg_path, pcfg.name
                )
                _da_settings = (
                    da.load_settings(cfg_path)
                )
            except Exception as exc:
                append_text(
                    build_error_frame(
                        str(exc)
                    )
                )
                app.invalidate()
                return
            append_text(
                build_inline_notif(
                    f"Provider"
                    f" '{pcfg.name}' removed.",
                    "✓",
                )
            )
            app.invalidate()

        _dlg.show_button_dialog(
            app,
            title="Remove Provider",
            message=msg,
            buttons=["Cancel", "Remove"],
            on_button=on_btn,
            width=54,
            refocus=input_area,
        )

    _dlg.show_menu_dialog(
        app,
        title="Remove Provider",
        options=labels,
        on_select=on_select,
        refocus=input_area,
    )


async def _fetch_and_select_model(
    app, pcfg
):
    """Fetch models for pcfg, select first,
    then notify the user.
    """
    global _avail_models
    pname = pcfg.name
    try:
        models = await da.list_models(pcfg)
    except Exception:
        models = []
    if not models:
        models = [pcfg.default_model]
    _avail_models[pname] = models
    first = models[0]
    if _da_session is not None:
        _da_session.set_model(first)
    _save_user_prefs()
    notif_mgr.notify(
        f"Provider → {pname} │ "
        f"Model → {first[:16]}",
        4.0,
    )
    append_text(
        build_inline_notif(
            f"Provider {pname}, "
            f"model {first} is in use",
            "✓",
        )
    )
    app.invalidate()


async def _provider_switched_pick_model_async(
    app, pcfg
):
    """Fetch models for the new provider with
    a spinner, cache them, then show the model
    selection menu so the user can pick.
    """
    global _avail_models
    pname = pcfg.name
    msg = "Fetching models..."
    telemetry.ai_status = "thinking"
    spin_text = build_thinking_frame(
        SPINNER[0], msg
    )
    append_text(spin_text)
    app.invalidate()
    spin_lines = spin_text.count("\n") + 1
    spin_stop = asyncio.Event()

    async def _spin():
        while not spin_stop.is_set():
            await asyncio.sleep(0.1)
            ch = telemetry.next_spinner()
            replace_last_block(
                spin_lines,
                build_thinking_frame(ch, msg),
            )
            app.invalidate()

    spin_task = asyncio.ensure_future(_spin())
    try:
        models = await da.list_models(pcfg)
    except Exception:
        models = []
    spin_stop.set()
    await spin_task
    replace_last_block(spin_lines, "")
    telemetry.ai_status = "idle"

    if not models:
        models = [pcfg.default_model]
    _avail_models[pname] = models

    await _show_change_model_async(app)


def _show_change_provider(app):
    """
    Show provider selection submenu
    in white style.
    """
    if _da_settings is None:
        append_text(
            build_warn_frame(
                "Settings not loaded."
            )
        )
        app.invalidate()
        return

    providers = da.list_providers(
        _da_settings
    )
    labels = []
    for pcfg in providers:
        pname = pcfg.name
        tag = (
            " ◀ active"
            if pname == _active_provider()
            else ""
        )
        labels.append(
            f"{pcfg.label} ({pname}){tag}"
        )

    def on_select(idx):
        global _app_mode
        pcfg = providers[idx]
        pname = pcfg.name
        try:
            _da_session.switch_provider(
                pname, _da_settings
            )
        except Exception as exc:
            append_text(
                build_error_frame(str(exc))
            )
            app.invalidate()
            _app_mode = _prev_mode
            return
        _app_mode = _prev_mode
        _apply_session_overrides(_da_session)
        asyncio.ensure_future(
            _provider_switched_pick_model_async(
                app, pcfg
            )
        )
        _save_user_prefs()
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Select Provider",
        options=labels,
        on_select=on_select,
        refocus=input_area,
    )


async def _show_models_async(app):
    """
    Fetch models for the current provider
    with a spinner, then display as a list.
    Side-effect: caches in _avail_models.
    """
    global _avail_models
    if _da_settings is None:
        append_text(
            build_warn_frame(
                "Settings not loaded."
            )
        )
        app.invalidate()
        return

    msg = "Reading models..."
    telemetry.ai_status = "thinking"
    spinner_text = build_thinking_frame(
        SPINNER[0], msg
    )
    append_text(spinner_text)
    app.invalidate()

    spin_lines = (
        spinner_text.count("\n") + 1
    )
    for _ in range(8):
        await asyncio.sleep(0.1)
        ch = telemetry.next_spinner()
        replace_last_block(
            spin_lines,
            build_thinking_frame(ch, msg),
        )
        app.invalidate()

    replace_last_block(spin_lines, "")
    telemetry.ai_status = "idle"

    pcfg = da.get_provider(
        _da_settings, _active_provider()
    )
    try:
        models = await da.list_models(pcfg)
    except Exception as exc:
        append_text(
            build_error_frame(
                f"Model list failed: {exc}"
            )
        )
        app.invalidate()
        return

    if not models:
        models = [pcfg.default_model]
    _avail_models[_active_provider()] = models

    append_text(
        build_setup_list_frame(
            f"Models — {_active_provider()}",
            models,
        )
    )
    append_text(
        build_inline_notif(
            "Done. StarryCLI is ready", "✓"
        )
    )
    app.invalidate()


async def _show_change_model_async(app):
    """Show model selection; auto-fetches
    if no cached models for current provider.
    """
    global _avail_models
    models = _avail_models.get(
        _active_provider(), []
    )
    if not models:
        if _da_settings is None:
            append_text(
                build_warn_frame(
                    "Settings not loaded."
                )
            )
            app.invalidate()
            return
        pcfg = da.get_provider(
            _da_settings, _active_provider()
        )
        try:
            models = await da.list_models(
                pcfg
            )
        except Exception:
            models = []
        if not models:
            models = [pcfg.default_model]
        _avail_models[_active_provider()] = models

    def on_select(idx):
        global _app_mode
        model = models[idx]
        if _da_session is not None:
            _da_session.set_model(model)
        _save_user_prefs()
        notif_mgr.notify(
            f"Model → {model}", 4.0
        )
        append_text(
            build_inline_notif(
                f"New model: {model}",
                "✓",
            )
        )
        _app_mode = _prev_mode
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Select Model",
        options=models,
        on_select=on_select,
        refocus=input_area,
        max_visible=12,
    )


async def _show_list_models_dlg(app):
    """Show available models in a dialog."""
    global _avail_models
    if _da_settings is None:
        _dlg.show_button_dialog(
            app,
            title="List Models",
            message="Settings not loaded.",
            buttons=["Close"],
            on_button=lambda _: None,
            width=44,
            refocus=input_area,
        )
        return
    models = _avail_models.get(
        _active_provider(), []
    )
    if not models:
        try:
            pcfg = da.get_provider(
                _da_settings, _active_provider()
            )
            models = await da.list_models(pcfg)
        except Exception as exc:
            _dlg.show_button_dialog(
                app,
                title="List Models",
                message=f"Fetch failed: {exc}",
                buttons=["Close"],
                on_button=lambda _: None,
                width=52,
                refocus=input_area,
            )
            return
        if not models:
            models = [pcfg.default_model]
        _avail_models[_active_provider()] = models
    msg = "\n".join(models)
    _dlg.show_button_dialog(
        app,
        title=f"Models — {_active_provider()}",
        message=msg,
        buttons=["Close"],
        on_button=lambda _: None,
        width=56,
        refocus=input_area,
    )


def _show_provider_submenu(app):
    """Provider management submenu."""
    opts = [
        "New provider",
        "List providers",
        "Change provider",
        "Remove provider",
        "List models",
        "Change model",
    ]

    def on_select(idx):
        chosen = opts[idx]
        if chosen == "New provider":
            _new_provider_wizard_dialog(app)
        elif chosen == "List providers":
            _show_list_providers_dlg(app)
        elif chosen == "Change provider":
            _show_change_provider(app)
        elif chosen == "Remove provider":
            _show_remove_provider(app)
        elif chosen == "List models":
            asyncio.ensure_future(
                _show_list_models_dlg(app)
            )
        elif chosen == "Change model":
            asyncio.ensure_future(
                _show_change_model_async(app)
            )

    _dlg.show_menu_dialog(
        app,
        title="Provider",
        options=opts,
        on_select=on_select,
        refocus=input_area,
    )


def _show_change_role(app):
    """
    Show role selection submenu in white style.
    On confirm, switches the session role and
    shows the StarryCLI ready notification.
    """
    if _da_settings is None:
        append_text(
            build_warn_frame(
                "Settings not loaded."
            )
        )
        app.invalidate()
        return
    if _da_session is None:
        append_text(
            build_warn_frame(
                "No active session."
            )
        )
        app.invalidate()
        return

    roles = list(
        _da_settings.agents.keys()
    )
    labels = []
    for rname in roles:
        rcfg = _da_settings.agents[rname]
        tag = (
            " ◀ active"
            if rname == _active_role()
            else ""
        )
        exp = rcfg.expertise.strip().replace(
            "\n", " "
        )
        if len(exp) > 50:
            exp = exp[:49] + "…"
        exp_part = f"  —  {exp}" if exp else ""
        labels.append(
            f"{rcfg.label} ({rname}){exp_part}{tag}"
        )

    def on_select(idx):
        rname = roles[idx]
        old_role = _active_role()
        try:
            _da_session.switch_role(
                rname, _da_settings
            )
        except Exception as exc:
            append_text(
                build_error_frame(str(exc))
            )
            app.invalidate()
            return
        _apply_session_overrides(_da_session)
        _save_user_prefs()
        notif_mgr.notify(
            f"Role → {rname}", 4.0
        )
        append_text(
            build_inline_notif(
                f"Role: {old_role} → {rname}",
                "✦",
            )
        )
        info = build_role_info_frame(rname)
        if info:
            append_text(info)
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Select Role",
        options=labels,
        on_select=on_select,
        refocus=input_area,
        max_visible=10,
    )


# ──────────────────────────────────────────────
# Role CRUD
# ──────────────────────────────────────────────

def _role_menu(app):
    """Show the /role submenu."""
    if _da_settings is None:
        append_text(
            build_warn_frame(
                "Settings not loaded."
            )
        )
        app.invalidate()
        return

    options = [
        "Set role",
        "Create role",
        "Update role",
        "Remove role",
    ]

    def on_select(idx):
        if idx == 0:
            _show_change_role(app)
        elif idx == 1:
            _role_create(app)
        elif idx == 2:
            _role_update(app)
        elif idx == 3:
            _role_remove(app)

    _dlg.show_menu_dialog(
        app,
        title="Role",
        options=options,
        on_select=on_select,
        refocus=input_area,
    )


def _role_create(app):
    """Step-by-step dialog to create a new role."""
    if _da_settings is None:
        return
    data = {}

    def _finish():
        key = data["name"]
        try:
            rcfg = da.RoleConfig(
                name=key,
                label=data["label"],
                expertise=data.get(
                    "expertise", ""
                ),
                temperature=data.get(
                    "temperature"
                ),
                model_override=data.get(
                    "model_override"
                ) or None,
                system_prompt=data.get(
                    "system_prompt", ""
                ),
            )
        except Exception as exc:
            append_text(
                build_error_frame(str(exc))
            )
            app.invalidate()
            return
        _da_settings.agents[key] = rcfg
        _user_roles.add(key)
        _save_user_roles()
        append_text(
            build_inline_notif(
                f"Role '{key}' created.", "✓"
            )
        )
        app.invalidate()

    def step_system_prompt():
        dsp = _default_system_prompt.strip()
        if dsp:
            preview = dsp[:120]
            if len(dsp) > 120:
                preview += "…"
            hint = (
                "Default system prompt (prepended):\n"
                f"{preview}\n\n"
                "Enter role-specific prompt to append:"
            )
        else:
            hint = (
                "No default system prompt is set.\n"
                "Enter the system prompt for this role:"
            )
        def _on_confirm(text):
            data["system_prompt"] = text
            _finish()
        _dlg.show_input_dialog(
            app,
            title="Role System Prompt (5/5)",
            label=hint,
            on_confirm=_on_confirm,
            multiline=True,
            field_height=6,
            width=72,
            refocus=input_area,
        )

    def step_model():
        def _on_confirm(text):
            data["model_override"] = (
                text.strip() or None
            )
            step_system_prompt()
        _dlg.show_input_dialog(
            app,
            title="Model Override (4/5)",
            label=(
                "Model to use for this role."
                " Leave blank for provider default."
            ),
            on_confirm=_on_confirm,
            refocus=input_area,
        )

    def step_temperature():
        def _on_confirm(text):
            text = text.strip()
            if not text:
                data["temperature"] = None
                step_model()
                return
            try:
                val = float(text)
                if not 0.0 <= val <= 2.0:
                    raise ValueError
            except ValueError:
                append_text(
                    build_warn_frame(
                        "Temperature must be"
                        " 0.0–2.0."
                    )
                )
                app.invalidate()
                step_temperature()
                return
            data["temperature"] = val
            step_model()
        _dlg.show_input_dialog(
            app,
            title="Temperature (3/5)",
            label=(
                "Sampling randomness 0.0–2.0."
                " Leave blank for default."
            ),
            on_confirm=_on_confirm,
            refocus=input_area,
        )

    def step_expertise():
        def _on_confirm(text):
            data["expertise"] = text.strip()
            step_temperature()
        _dlg.show_input_dialog(
            app,
            title="Description (2/5)",
            label="One-line description of this role.",
            on_confirm=_on_confirm,
            refocus=input_area,
        )

    def step_name_key():
        def _on_confirm(text):
            key = (
                text.strip()
                .lower()
                .replace(" ", "_")
            )
            if not key:
                append_text(
                    build_warn_frame(
                        "Role key cannot be empty."
                    )
                )
                app.invalidate()
                step_name_key()
                return
            if key in _da_settings.agents:
                append_text(
                    build_warn_frame(
                        f"Role '{key}' already exists."
                    )
                )
                app.invalidate()
                step_name_key()
                return
            data["name"] = key
            step_expertise()
        _dlg.show_input_dialog(
            app,
            title="Role Key (1/5)",
            label=(
                "Unique ID for this role"
                " (e.g. my_role). No spaces."
            ),
            on_confirm=_on_confirm,
            refocus=input_area,
        )

    def step_label():
        def _on_confirm(text):
            text = text.strip()
            if not text:
                append_text(
                    build_warn_frame(
                        "Label cannot be empty."
                    )
                )
                app.invalidate()
                step_label()
                return
            data["label"] = text
            step_name_key()
        _dlg.show_input_dialog(
            app,
            title="Create Role — Display Name",
            label=(
                "Display name shown in menus"
                " (e.g. My Specialist)."
            ),
            on_confirm=_on_confirm,
            refocus=input_area,
        )

    step_label()


def _role_update(app):
    """Select a role then edit its fields."""
    if _da_settings is None:
        return

    roles = list(_da_settings.agents.keys())
    labels = []
    for rname in roles:
        rcfg = _da_settings.agents[rname]
        tag = (
            " ◀ active" if rname == _active_role()
            else ""
        )
        user_tag = (
            " [user]" if rname in _user_roles
            else ""
        )
        labels.append(
            f"{rcfg.label} ({rname})"
            f"{user_tag}{tag}"
        )

    def on_role_selected(idx):
        key = roles[idx]
        rcfg = _da_settings.agents[key]
        data = {
            "name": key,
            "label": rcfg.label,
            "expertise": rcfg.expertise,
            "temperature": rcfg.temperature,
            "model_override": (
                rcfg.model_override or ""
            ),
            "system_prompt": rcfg.system_prompt,
        }

        def _finish():
            try:
                new_rcfg = da.RoleConfig(
                    name=key,
                    label=data["label"],
                    expertise=data["expertise"],
                    temperature=data[
                        "temperature"
                    ],
                    model_override=data.get(
                        "model_override"
                    ) or None,
                    system_prompt=data[
                        "system_prompt"
                    ],
                    # preserve non-edited fields
                    goal=rcfg.goal,
                    backstory=rcfg.backstory,
                    constraints=rcfg.constraints,
                    output_format=rcfg.output_format,
                    allowed_tools=(
                        rcfg.allowed_tools
                    ),
                    denied_tools=rcfg.denied_tools,
                    can_delegate_to=(
                        rcfg.can_delegate_to
                    ),
                    accepts_from=rcfg.accepts_from,
                )
            except Exception as exc:
                append_text(
                    build_error_frame(str(exc))
                )
                app.invalidate()
                return
            _da_settings.agents[key] = new_rcfg
            _user_roles.add(key)
            _save_user_roles()
            if key == _active_role() and (
                _da_session is not None
            ):
                try:
                    _da_session.switch_role(
                        key, _da_settings
                    )
                    _apply_session_overrides(
                        _da_session
                    )
                except Exception:
                    pass
            append_text(
                build_inline_notif(
                    f"Role '{key}' updated.", "✓"
                )
            )
            app.invalidate()

        def step_system_prompt():
            dsp = _default_system_prompt.strip()
            if dsp:
                preview = dsp[:120]
                if len(dsp) > 120:
                    preview += "…"
                hint = (
                    "Default system prompt"
                    " (prepended):\n"
                    f"{preview}\n\n"
                    "Role-specific prompt to append:"
                )
            else:
                hint = (
                    "No default system prompt set.\n"
                    "Enter system prompt for this role:"
                )
            def _on_confirm(text):
                data["system_prompt"] = text
                _finish()
            _dlg.show_input_dialog(
                app,
                title="System Prompt (5/5)",
                label=hint,
                on_confirm=_on_confirm,
                multiline=True,
                field_height=6,
                width=72,
                initial_text=data[
                    "system_prompt"
                ],
                refocus=input_area,
            )

        def step_model():
            def _on_confirm(text):
                data["model_override"] = (
                    text.strip() or None
                )
                step_system_prompt()
            _dlg.show_input_dialog(
                app,
                title="Model Override (4/5)",
                label=(
                    "Model for this role."
                    " Blank = provider default."
                ),
                on_confirm=_on_confirm,
                initial_text=data[
                    "model_override"
                ],
                refocus=input_area,
            )

        def step_temperature():
            cur_t = data["temperature"]
            cur_str = (
                str(cur_t)
                if cur_t is not None else ""
            )
            def _on_confirm(text):
                text = text.strip()
                if not text:
                    data["temperature"] = None
                    step_model()
                    return
                try:
                    val = float(text)
                    if not 0.0 <= val <= 2.0:
                        raise ValueError
                except ValueError:
                    append_text(
                        build_warn_frame(
                            "Temperature must be"
                            " 0.0–2.0."
                        )
                    )
                    app.invalidate()
                    step_temperature()
                    return
                data["temperature"] = val
                step_model()
            _dlg.show_input_dialog(
                app,
                title="Temperature (3/5)",
                label=(
                    "Sampling randomness 0.0–2.0."
                    " Blank = default."
                ),
                on_confirm=_on_confirm,
                initial_text=cur_str,
                refocus=input_area,
            )

        def step_expertise():
            def _on_confirm(text):
                data["expertise"] = text.strip()
                step_temperature()
            _dlg.show_input_dialog(
                app,
                title="Description (2/5)",
                label=(
                    "One-line description"
                    " of this role."
                ),
                on_confirm=_on_confirm,
                initial_text=data["expertise"],
                refocus=input_area,
            )

        def step_label():
            def _on_confirm(text):
                text = text.strip()
                if not text:
                    append_text(
                        build_warn_frame(
                            "Label cannot be empty."
                        )
                    )
                    app.invalidate()
                    step_label()
                    return
                data["label"] = text
                step_expertise()
            _dlg.show_input_dialog(
                app,
                title=(
                    f"Update '{key}'"
                    " — Display Name (1/5)"
                ),
                label=(
                    "Display name shown in menus."
                ),
                on_confirm=_on_confirm,
                initial_text=data["label"],
                refocus=input_area,
            )

        step_label()

    _dlg.show_menu_dialog(
        app,
        title="Update Role — Select",
        options=labels,
        on_select=on_role_selected,
        refocus=input_area,
    )


def _role_remove(app):
    """Select a role and confirm removal."""
    if _da_settings is None:
        return

    roles = list(_da_settings.agents.keys())
    labels = []
    for rname in roles:
        rcfg = _da_settings.agents[rname]
        tag = (
            " ◀ active" if rname == _active_role()
            else ""
        )
        user_tag = (
            " [user]" if rname in _user_roles
            else ""
        )
        labels.append(
            f"{rcfg.label} ({rname})"
            f"{user_tag}{tag}"
        )

    def on_role_selected(idx):
        key = roles[idx]
        is_active = (key == _active_role())
        warn = (
            f"\nWARNING: '{key}' is the active"
            " role. Switch role first."
            if is_active else ""
        )
        msg = (
            f"Remove role '{key}'?"
            f"{warn}\n"
            "This cannot be undone."
        )

        def on_btn(bidx):
            if bidx == 0:
                return  # Cancel
            if is_active:
                append_text(
                    build_warn_frame(
                        "Cannot remove the active"
                        " role. Switch first."
                    )
                )
                app.invalidate()
                return
            del _da_settings.agents[key]
            _user_roles.discard(key)
            _save_user_roles()
            append_text(
                build_inline_notif(
                    f"Role '{key}' removed.", "✓"
                )
            )
            app.invalidate()

        _dlg.show_button_dialog(
            app,
            title="Remove Role",
            message=msg,
            buttons=["Cancel", "Remove"],
            on_button=on_btn,
            refocus=input_area,
        )

    _dlg.show_menu_dialog(
        app,
        title="Remove Role — Select",
        options=labels,
        on_select=on_role_selected,
        refocus=input_area,
    )


def _show_toggle_tool(app):
    """Show a menu to enable/disable tools."""
    if _da_session is None:
        append_text(
            build_warn_frame("No active session.")
        )
        app.invalidate()
        return
    from starry_lib.tools.tool_loader import (
        get_tool_schemas as _get_mode_schemas,
    )
    # Include MCP/extra tools so Disable all
    # covers them too, preventing "model does
    # not support tools" after disabling.
    mode_schemas = _get_mode_schemas(_exec_mode)
    extra_schemas = [
        t.SCHEMA
        for t in (
            _da_session.extra_tools or []
        )
    ]
    all_schemas = mode_schemas + extra_schemas
    all_names = [
        s["function"]["name"]
        for s in all_schemas
    ]
    if not all_names:
        append_text(
            build_inline_notif(
                "No tools in current mode.", "🔧"
            )
        )
        app.invalidate()
        return

    denied = list(_da_session.denied_tools or [])
    desc_map = {
        s["function"]["name"]: s["function"].get(
            "description", ""
        )
        for s in all_schemas
    }
    labels = [
        (
            f"{'✗' if n in denied else '✓'}"
            f" {n}"
            + (
                f" — {desc_map.get(n, '')[:35]}"
                if desc_map.get(n) else ""
            )
        )
        for n in all_names
    ]
    labels.append("⊕  Enable all")
    labels.append("⊘  Disable all")

    def _notify_llm():
        act = [
            n for n in all_names
            if n not in (
                _da_session.denied_tools or []
            )
        ]
        dis = list(
            _da_session.denied_tools or []
        )
        _da_session.fire_event(
            "on_tool_change",
            active_tools=(
                ", ".join(act) or "(none)"
            ),
            disabled_tools=(
                ", ".join(dis) or "(none)"
            ),
        )

    def on_toggle(idx):
        if idx == len(all_names):
            _da_session.denied_tools = []
            _notify_llm()
            append_text(
                build_inline_notif(
                    "All tools enabled."
                    " StarryCLI is ready.",
                    "🔧",
                )
            )
            app.invalidate()
            return
        if idx == len(all_names) + 1:
            _da_session.denied_tools = (
                list(all_names)
            )
            _notify_llm()
            append_text(
                build_inline_notif(
                    "All tools disabled."
                    " StarryCLI is ready.",
                    "🔧",
                )
            )
            app.invalidate()
            return
        name = all_names[idx]
        current = list(
            _da_session.denied_tools or []
        )
        if name in current:
            current.remove(name)
            state = "enabled"
        else:
            current.append(name)
            state = "disabled"
        _da_session.denied_tools = current
        _notify_llm()
        append_text(
            build_inline_notif(
                f"Tool '{name}' {state}."
                " StarryCLI is ready.",
                "🔧",
            )
        )
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Toggle Tool (✓=on ✗=off)",
        options=labels,
        on_select=on_toggle,
        refocus=input_area,
        max_visible=12,
    )


def _show_toggle_skill(app):
    """Show a menu to enable/disable skills."""
    if _da_session is None:
        append_text(
            build_warn_frame("No active session.")
        )
        app.invalidate()
        return
    from starry_lib.skills.loader import list_skills
    skill_names = list_skills()
    if not skill_names:
        append_text(
            build_inline_notif(
                "No skills available.", "✦"
            )
        )
        app.invalidate()
        return

    active = list(_da_session.active_skills or [])
    labels = [
        (
            f"{'✓' if n in active else '✗'}"
            f" {n}"
        )
        for n in skill_names
    ]
    labels.append("⊕  Enable all")
    labels.append("⊘  Disable all")

    def _notify_llm():
        act = list(
            _da_session.active_skills or []
        )
        _da_session.fire_event(
            "on_skill_change",
            active_skills=(
                ", ".join(act) or "(none)"
            ),
        )

    def on_toggle(idx):
        if idx == len(skill_names):
            for n in skill_names:
                if n not in (
                    _da_session.active_skills
                    or []
                ):
                    try:
                        _da_session.add_skill(n)
                    except Exception:
                        pass
            _notify_llm()
            append_text(
                build_inline_notif(
                    "All skills enabled."
                    " StarryCLI is ready.",
                    "✦",
                )
            )
            app.invalidate()
            return
        if idx == len(skill_names) + 1:
            for n in list(
                _da_session.active_skills or []
            ):
                try:
                    _da_session.remove_skill(n)
                except Exception:
                    pass
            _notify_llm()
            append_text(
                build_inline_notif(
                    "All skills disabled."
                    " StarryCLI is ready.",
                    "✦",
                )
            )
            app.invalidate()
            return
        name = skill_names[idx]
        if name in (
            _da_session.active_skills or []
        ):
            _da_session.remove_skill(name)
            state = "disabled"
        else:
            _da_session.add_skill(name)
            state = "enabled"
        _notify_llm()
        append_text(
            build_inline_notif(
                f"Skill '{name}' {state}."
                " StarryCLI is ready.",
                "✦",
            )
        )
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Toggle Skill (✓=on ✗=off)",
        options=labels,
        on_select=on_toggle,
        refocus=input_area,
        max_visible=12,
    )


def _make_wizard_float(
    title, label, field, width=64,
):
    """Custom rounded-frame Float dialog
    matching the scrollable-frame style.

    title  — title string
    label  — body label (centered)
    field  — TextArea widget
    width  — total dialog width in chars
    """

    fw = width
    iw = fw - 2      # inside outer VT chars
    margin = 2       # inner padding each side
    fiw = iw - margin * 2 - 2  # field inner

    fs = "class:line.aframe"
    cs = "class:line.acontent"
    hs = "class:line.header"
    ds = "class:dialog"

    def _win(frags, h=1, w=None):
        kw = dict(
            content=FormattedTextControl(
                frags,
                show_cursor=False,
                focusable=False,
            ),
            height=h,
            dont_extend_height=True,
            style=ds,
        )
        if w is not None:
            kw["width"] = w
            kw["dont_extend_width"] = True
        return Window(**kw)

    # Outer top border — centered title
    t = f" {title} "
    tl = len(t)
    lpad = max(0, (iw - tl) // 2)
    rpad = max(0, iw - tl - lpad)
    top_frags = [
        (fs, TL),
        (fs, HZ * lpad),
        (hs, t),
        (fs, HZ * rpad),
        (fs, TR),
    ]

    def _pad_row():
        return _win([
            (fs, VT),
            (cs, " " * iw),
            (fs, VT),
        ])

    # Centered label row
    lbl = label.center(iw)
    label_frags = [
        (fs, VT),
        (cs, lbl),
        (fs, VT),
    ]

    # Inner field frame
    field_top_frags = [
        (fs, VT),
        (cs, " " * margin),
        (fs, f"{TL}{HZ * fiw}{TR}"),
        (cs, " " * margin),
        (fs, VT),
    ]

    def _vt_win():
        return _win([(fs, VT)], w=1)

    def _sp_win(n):
        return _win([(cs, " " * n)], w=n)

    field_row = VSplit(
        [
            _vt_win(),
            _sp_win(margin),
            _vt_win(),
            field,
            _vt_win(),
            _sp_win(margin),
            _vt_win(),
        ],
        style=ds,
    )

    field_bot_frags = [
        (fs, VT),
        (cs, " " * margin),
        (fs, f"{BL}{HZ * fiw}{BR}"),
        (cs, " " * margin),
        (fs, VT),
    ]

    # Outer bottom border
    bot_frags = [
        (fs, BL),
        (fs, HZ * iw),
        (fs, BR),
    ]

    container = HSplit(
        [
            _win(top_frags),
            _pad_row(),
            _win(label_frags),
            _pad_row(),
            _win(field_top_frags),
            field_row,
            _win(field_bot_frags),
            _pad_row(),
            _win(bot_frags),
        ],
        style=ds,
    )

    cols = shutil.get_terminal_size().columns
    rows = shutil.get_terminal_size().lines
    return Float(
        content=container,
        left=max(0, (cols - fw) // 2),
        top=max(2, (rows - 13) // 2),
    )


def _new_provider_wizard_dialog(app):
    """Dialog-chain wizard: Name → URL →
    Token → probe endpoint → model select
    → save to config.
    """
    results = {}

    async def _probe_and_finish():
        global _da_settings, _avail_models

        name = results["name"]
        url = results["url"]
        token = results["token"]

        # ── Probe endpoint ─────────────────
        msg = "Connecting to provider..."
        telemetry.ai_status = "thinking"
        spin_text = build_thinking_frame(
            SPINNER[0], msg
        )
        append_text(spin_text)
        app.invalidate()
        spin_lines = (
            spin_text.count("\n") + 1
        )
        probe_cfg = da.make_provider(
            name=name,
            base_url=url,
            api_key=token,
            model="placeholder",
        )
        spin_stop = asyncio.Event()

        async def _spin():
            while not spin_stop.is_set():
                await asyncio.sleep(0.1)
                ch = telemetry.next_spinner()
                replace_last_block(
                    spin_lines,
                    build_thinking_frame(
                        ch, msg
                    ),
                )
                app.invalidate()

        spin_task = asyncio.ensure_future(
            _spin()
        )
        try:
            models = await da.list_models(
                probe_cfg
            )
        except Exception as exc:
            spin_stop.set()
            await spin_task
            replace_last_block(spin_lines, "")
            telemetry.ai_status = "idle"
            append_text(
                build_error_frame(
                    f"Connection failed: {exc}"
                )
            )
            app.invalidate()
            return
        spin_stop.set()
        await spin_task
        replace_last_block(spin_lines, "")
        telemetry.ai_status = "idle"

        if not models:
            append_text(
                build_warn_frame(
                    "No models returned."
                    " Check the endpoint URL."
                )
            )
            app.invalidate()
            return

        # ── Model selection ────────────────
        def on_model_select(idx):
            selected = models[idx]
            asyncio.ensure_future(
                _save_and_switch(
                    selected, models
                )
            )

        _dlg.show_menu_dialog(
            app,
            title="Select model",
            options=models,
            on_select=on_model_select,
            refocus=input_area,
            max_visible=12,
        )

    async def _save_and_switch(
        selected, models
    ):
        global _da_settings, _avail_models

        name = results["name"]
        url = results["url"]
        token = results["token"]
        env_key = (
            name.upper().replace("-", "_")
            + "_API_KEY"
        )
        cfg_path, env_path = (
            da.get_default_paths()
        )
        new_cfg = da.ProviderConfig(
            name=name,
            base_url=url,
            api_key_env=env_key,
            ssl_verify=True,
            default_model=selected,
            label=name,
        )
        try:
            da.add_provider(cfg_path, new_cfg)
            da.write_env_key(
                env_path, env_key, token
            )
        except Exception as exc:
            append_text(
                build_error_frame(
                    f"Save failed: {exc}"
                )
            )
            app.invalidate()
            return
        try:
            _da_settings = da.load_settings(
                cfg_path
            )
        except Exception as exc:
            append_text(
                build_error_frame(
                    f"Settings reload"
                    f" failed: {exc}"
                )
            )
            app.invalidate()
            return
        _avail_models[name] = models
        if _da_session is not None:
            try:
                _da_session.switch_provider(
                    name, _da_settings
                )
                _da_session.set_model(selected)
                _apply_session_overrides(
                    _da_session
                )
            except Exception as exc:
                append_text(
                    build_error_frame(str(exc))
                )
                app.invalidate()
                return
        global _wizard_cancel_fn
        _wizard_cancel_fn = None
        _save_user_prefs()
        notif_mgr.notify(
            f"Provider → {name} │ "
            f"Model → {selected[:16]}",
            4.0,
        )
        append_text(
            build_inline_notif(
                f"Provider {name},"
                f" model {selected}"
                " is now active.",
                "✓",
            )
        )
        app.invalidate()

    def _cancelled(f_ref):
        global _wizard_cancel_fn
        _wizard_cancel_fn = None
        close_dialog(app, f_ref[0])
        append_text(
            build_inline_notif(
                "Wizard cancelled.", "↩"
            )
        )
        app.invalidate()

    def step3():
        f_ref = [None]
        _cb = [None]
        field = TextArea(
            multiline=False, text="",
            accept_handler=lambda buf: (
                _cb[0]() if _cb[0] else None
            ),
        )

        def _finish():
            raw = field.text.strip()
            results["token"] = (
                raw if raw else "ollama"
            )
            close_dialog(app, f_ref[0])
            asyncio.ensure_future(
                _probe_and_finish()
            )

        def _cancel():
            _cancelled(f_ref)

        _cb[0] = _finish
        f = _make_wizard_float(
            "New Provider 3/3 — Token",
            "Bearer token (blank = ollama):",
            field,
        )
        f_ref[0] = f
        global _wizard_cancel_fn
        _wizard_cancel_fn = _cancel
        show_dialog(app, f)
        app.layout.focus(field)

    def step2():
        f_ref = [None]
        _cb = [None]
        field = TextArea(
            multiline=False, text="",
            accept_handler=lambda buf: (
                _cb[0]() if _cb[0] else None
            ),
        )

        def _next():
            val = field.text.strip()
            if not val:
                return
            results["url"] = val
            close_dialog(app, f_ref[0])
            step3()

        def _cancel():
            _cancelled(f_ref)

        _cb[0] = _next
        f = _make_wizard_float(
            "New Provider 2/3 — URL",
            "Endpoint URL (e.g. http://host:11434/v1):",
            field,
        )
        f_ref[0] = f
        global _wizard_cancel_fn
        _wizard_cancel_fn = _cancel
        show_dialog(app, f)
        app.layout.focus(field)

    def step1(skip_url_token=False):
        f_ref = [None]
        _cb = [None]
        field = TextArea(
            multiline=False, text="",
            accept_handler=lambda buf: (
                _cb[0]() if _cb[0] else None
            ),
        )

        def _next():
            val = field.text.strip()
            if not val:
                return
            if not re.match(
                r'^[a-z0-9][a-z0-9_-]*$', val
            ):
                close_dialog(app, f_ref[0])
                append_text(
                    build_error_frame(
                        "Invalid name."
                        " Use a-z, 0-9, _ or -"
                        " starting with a"
                        " letter or digit."
                    )
                )
                app.invalidate()
                return
            if (
                _da_settings is not None
                and val
                in _da_settings.providers
            ):
                close_dialog(app, f_ref[0])
                append_text(
                    build_error_frame(
                        f"Provider '{val}'"
                        " already exists."
                    )
                )
                app.invalidate()
                return
            results["name"] = val
            close_dialog(app, f_ref[0])
            if skip_url_token:
                asyncio.ensure_future(
                    _probe_and_finish()
                )
            else:
                step2()

        def _cancel():
            _cancelled(f_ref)

        _cb[0] = _next
        f = _make_wizard_float(
            "New Provider 1/3 — Name",
            "Provider name (e.g. my_ollama):",
            field,
        )
        f_ref[0] = f
        global _wizard_cancel_fn
        _wizard_cancel_fn = _cancel
        show_dialog(app, f)
        app.layout.focus(field)

    def step0():
        presets = [
            "Custom (OpenAI-compatible URL)",
            "llama.cpp (localhost:8080)",
        ]

        def on_type(idx):
            if idx == 1:
                results["url"] = (
                    "http://localhost:8080/v1"
                )
                results["token"] = "none"
                step1(skip_url_token=True)
            else:
                step1()

        _dlg.show_menu_dialog(
            app,
            title="New Provider — Type",
            options=presets,
            on_select=on_type,
            refocus=input_area,
        )

    step0()


def _show_change_theme(app):
    """Show a theme selection submenu."""
    themes = list_themes()
    if not themes:
        append_text(
            build_warn_frame(
                "No themes available."
            )
        )
        app.invalidate()
        return

    def on_theme_select(idx):
        name = themes[idx]
        _apply_theme(name)
        app.style = build_style(_exec_mode)
        _save_user_prefs()
        append_text(
            build_inline_notif(
                f"Theme → {name}", "🎨"
            )
        )
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Select Theme",
        options=themes,
        on_select=on_theme_select,
        refocus=input_area,
        max_visible=10,
    )


def _reset_defaults(app):
    """Reset provider, model, role to config defaults."""
    if _da_settings is None:
        append_text(
            build_warn_frame(
                "Settings not loaded."
            )
        )
        app.invalidate()
        return
    def_provider = _da_settings.active_provider
    def_role = _da_settings.active_role
    def_model = ""
    try:
        pcfg = da.get_provider(
            _da_settings, def_provider
        )
        def_model = pcfg.default_model
    except Exception:
        pass
    if _da_session is not None:
        try:
            _da_session.switch_provider(
                def_provider, _da_settings
            )
        except Exception:
            pass
        try:
            _da_session.switch_role(
                def_role, _da_settings
            )
        except Exception:
            pass
        if def_model:
            try:
                _da_session.set_model(def_model)
            except Exception:
                pass
    _apply_theme("jalisco")
    app.style = build_style(_exec_mode)
    try:
        USER_PREFS_PATH.write_text(
            json.dumps({}, indent=2)
        )
    except Exception:
        pass
    m = _active_model()
    mname = m[:14] + "…" if len(m) > 14 else m
    append_text(
        build_inline_notif(
            f"Reset to defaults."
            f" Provider: {_active_provider()},"
            f" Model: {mname},"
            f" Role: {_active_role()}."
            f" StarryCLI is ready.",
            "↺",
        )
    )
    app.invalidate()


def _show_about(app):
    """About StarryCLI info dialog."""
    msg = (
        "StarryCLI — Agentic Terminal Interface\n"
        "\n"
        f"Version:    {VERSION}\n"
        "\n"
        "Multi-agent LLM orchestration TUI.\n"
        "Supports multiple providers, roles,\n"
        "skills, tools, and sessions.\n"
        "\n"
        "Developer:  BSDero\n"
        "Contact:    bsdero@gmail.com\n"
    )
    _dlg.show_button_dialog(
        app,
        title="About StarryCLI",
        message=msg,
        buttons=["Close"],
        on_button=lambda _: None,
        width=52,
        refocus=input_area,
    )


def _show_stats(app):
    """Floating dialog with session stats."""
    if _da_session is None:
        _dlg.show_button_dialog(
            app,
            title="Session Stats",
            message="No active session.",
            buttons=["Close"],
            on_button=lambda _: None,
            width=44,
            refocus=input_area,
        )
        return
    tok = _da_session.token_usage
    ctx = _da_session.context_window or 0
    pct = (
        int(tok["total"] * 100 / ctx)
        if ctx else 0
    )
    hist = _da_session.get_history()
    turns = sum(
        1 for m in hist
        if m.get("role") == "user"
    )
    cost = _da_session.cost_estimate
    cost_str = (
        f"${cost:.4f}"
        if cost is not None
        else "N/A"
    )
    skills = _da_session.active_skills
    skl = (
        ", ".join(skills) if skills
        else "none"
    )
    sid = _da_session.id
    role = _active_role() or "default"
    msg = (
        f"Session:    {sid}\n"
        f"Provider:   {_active_provider()}\n"
        f"Model:      {_active_model()}\n"
        f"Role:       {role}\n"
        f"Mode:       {_exec_mode}\n"
        f"Turns:      {turns}\n"
        f"Tokens:     {tok['total']}"
        f" / {ctx} ({pct}%)\n"
        f"  Prompt:   {tok['prompt']}\n"
        f"  Compl.:   {tok['completion']}\n"
        f"Cost est:   {cost_str}\n"
        f"Skills:     {skl}\n"
    )
    _dlg.show_button_dialog(
        app,
        title="Session Stats",
        message=msg,
        buttons=["Close"],
        on_button=lambda _: None,
        width=58,
        refocus=input_area,
    )


def _show_context_format(app):
    """Sub-menu to choose Context buffer format."""
    global _context_format
    fmt_opts = ["Markdown", "JSON"]

    def _on_fmt(idx):
        global _context_format
        _context_format = fmt_opts[idx].lower()
        _save_user_prefs()
        append_text(
            build_inline_notif(
                f"Context format set to"
                f" {fmt_opts[idx]}.",
                "✓",
            )
        )
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Context format",
        options=fmt_opts,
        on_select=_on_fmt,
        refocus=input_area,
    )


async def _prefetch_models_task():
    """
    Background task: cache available models
    for all providers at startup.
    """
    global _avail_models
    if _da_settings is None:
        return
    for pname, pcfg in (
        _da_settings.providers.items()
    ):
        try:
            models = await da.list_models(pcfg)
            if models:
                _avail_models[pname] = models
        except Exception:
            pass


# ---------------------------------------------------
# Input area
# ---------------------------------------------------
input_area = TextArea(
    height=Dimension(min=1, max=3),
    prompt=FormattedText(
        [("class:input-prompt", " ❯❯ ")]
    ),
    style="class:input-area",
    multiline=False,
    wrap_lines=True,
    focus_on_click=True,
)


# ===================================================
# Tab Manager
# ===================================================
class Tab:
    """Represents a single TUI tab."""

    def __init__(
        self, name, buffer, read_only=True
    ):
        self.name = name
        self.buffer = buffer
        self.read_only = read_only
        # Saved cursor position for scroll restore
        self.scroll_pos: int = 0


class TabManager:
    """Manages the set of open tabs."""

    def __init__(self, tabs):
        self.tabs = list(tabs)
        self.active = 0

    def next_tab(self):
        if self.tabs:
            self.active = (
                (self.active + 1)
                % len(self.tabs)
            )

    def prev_tab(self):
        if self.tabs:
            self.active = (
                (self.active - 1)
                % len(self.tabs)
            )

    def goto_tab(self, n):
        if 0 <= n < len(self.tabs):
            self.active = n

    def new_tab(self, name="Scratch"):
        buf = Buffer(
            name=(
                f"scratch_{len(self.tabs)}"
            ),
            read_only=False,
        )
        tab = Tab(name, buf, read_only=False)
        self.tabs.append(tab)
        self.active = len(self.tabs) - 1
        return tab

    def active_buffer(self):
        """Return the active tab's Buffer."""
        return self.tabs[self.active].buffer

    def close_tab(self, index=None):
        if index is None:
            index = self.active
        if len(self.tabs) <= 1:
            return
        if 0 <= index < len(self.tabs):
            self.tabs.pop(index)
            self.active = min(
                self.active,
                len(self.tabs) - 1,
            )

    # ── Buffer-registry-aware helpers ────

    def has_tab(self, name):
        """True if a tab for this buffer name exists."""
        return self.find_tab_index(name) is not None

    def find_tab_index(self, name):
        """Return index of tab with given name, or None."""
        lo = name.lower()
        for i, tab in enumerate(self.tabs):
            if tab.name.lower() == lo:
                return i
        return None

    def open_buffer(self, name):
        """
        Open a tab for the named buffer or switch
        to an existing tab.
        Returns 'switched', 'opened', or 'not_found'.
        """
        idx = self.find_tab_index(name)
        if idx is not None:
            self.active = idx
            return "switched"
        buf = buf_reg.get(name)
        if buf is None:
            return "not_found"
        canonical = buf_reg.canonical(name)
        tab = Tab(
            canonical, buf, read_only=True
        )
        self.tabs.append(tab)
        self.active = len(self.tabs) - 1
        return "opened"

    def close_tab_by_name(self, name):
        """
        Close the tab for the named buffer and
        switch to Chat.
        Returns True or an error string.
        """
        if name.lower() == "chat":
            return (
                "The Chat tab cannot be closed."
            )
        idx = self.find_tab_index(name)
        if idx is None:
            return (
                f"No open tab named '{name}'."
            )
        self.tabs.pop(idx)
        # Always land on Chat (index 0)
        self.active = 0
        return True


tab_mgr = TabManager([
    Tab(
        "Chat",
        main_buffer,
        read_only=True,
    ),
])

# Register all buffers; only Chat has a tab.
buf_reg.register("Chat", main_buffer)
buf_reg.register(
    "Tool Output", tool_output_buffer
)
buf_reg.register("Logs", logs_buffer)
buf_reg.register("Context", context_buffer)


# ---------------------------------------------------
# Rewind helper — shared by /rewind and Escape key
# ---------------------------------------------------
def _do_rewind(app):
    """Cancel active LLM task and remove the last
    exchange from session history.

    Called by both the /rewind command and the
    Escape key interrupt handler so behaviour is
    identical in both paths.
    """
    global _ai_task, _tui_input_mode
    global _pending_questions
    if _ai_task is not None:
        _ai_task.cancel()
    telemetry.ai_status = "idle"
    _tui_input_mode = "chat"
    _pending_questions.clear()
    if _da_session is not None:
        _da_session.cancel_confirm()
        _da_session.answer_question("")
        _da_session.rewind()
    _ai_task = None
    append_text(
        build_warn_frame(
            "Cancelled, what will I do instead?"
        )
    )
    app.invalidate()


# ---------------------------------------------------
# Key bindings
# ---------------------------------------------------
kb = KeyBindings()


@kb.add("c-c")
def handle_ctrl_c(event):
    event.app.exit()


@kb.add("pageup", eager=True)
def handle_pgup(event):
    _scroll_main(event, -15)


@kb.add("pagedown", eager=True)
def handle_pgdn(event):
    _scroll_main(event, 15)


@kb.add(
    "up",
    filter=Condition(
        lambda: sel_menu.active
    ),
)
def handle_up(event):
    """Menu navigate up."""
    sel_menu.move_up()
    _redraw_menu(event.app)


@kb.add(
    "down",
    filter=Condition(
        lambda: sel_menu.active
    ),
)
def handle_down(event):
    """Menu navigate down."""
    sel_menu.move_down()
    _redraw_menu(event.app)


@kb.add(
    "enter",
    filter=Condition(
        lambda: sel_menu.active
    ),
)
def handle_enter(event):
    """Menu confirm selection."""
    sel_menu.confirm()
    event.app.invalidate()


@kb.add(
    "escape",
    filter=Condition(
        lambda: sel_menu.active
    ),
)
def handle_escape(event):
    """Cancel active menu."""
    prev_lines = sel_menu._prev_lines
    sel_menu.dismiss()
    if _da_session is not None:
        _da_session.cancel_confirm()
    if prev_lines > 0:
        replace_last_block(prev_lines, "")
    append_text(
        build_inline_notif(
            "StarryCLI is ready.",
            "↩",
        )
    )
    if _da_session is not None:
        _da_session.fire_event(
            "on_llm_request_cancel"
        )
    event.app.invalidate()


@kb.add(
    "x",
    filter=Condition(
        lambda: (
            sel_menu.active
            and sel_menu.checkbox_mode
        )
    ),
)
@kb.add(
    "X",
    filter=Condition(
        lambda: (
            sel_menu.active
            and sel_menu.checkbox_mode
        )
    ),
)
def handle_toggle_checkbox(event):
    """Toggle checkbox of highlighted item."""
    sel_menu.toggle_checkbox()
    _redraw_menu(event.app)


@kb.add(
    "r",
    filter=Condition(
        lambda: (
            sel_menu.active
            and sel_menu.checkbox_mode
        )
    ),
)
@kb.add(
    "R",
    filter=Condition(
        lambda: (
            sel_menu.active
            and sel_menu.checkbox_mode
        )
    ),
)
def handle_remove_marked(event):
    """Remove sessions that are checked."""
    checked = sel_menu.checked_indices()
    if not checked:
        return
    saved_ref = list(_session_menu_saved)
    checked_ref = list(checked)
    prev_lines = sel_menu._prev_lines
    sel_menu.dismiss()
    if prev_lines > 0:
        replace_last_block(prev_lines, "")
    count = len(checked_ref)

    def on_confirm(idx):
        if idx == 0:
            from starry_lib.sessions.store import (
                delete as _del,
            )
            for i in checked_ref:
                _del(saved_ref[i]["hash"])
            append_text(
                build_inline_notif(
                    f"Deleted {count} session(s).",
                    "🗑",
                )
            )
        else:
            append_text(
                build_inline_notif(
                    "Delete cancelled.", "↩"
                )
            )
        event.app.invalidate()

    _dlg.show_button_dialog(
        event.app,
        title="Confirm Delete",
        message=(
            f"Delete {count} session(s)?"
        ),
        buttons=[
            f"Yes, delete {count}",
            "Cancel",
        ],
        on_button=on_confirm,
        refocus=input_area,
    )


@kb.add(
    "escape",
    filter=Condition(
        lambda: (
            _ai_task is not None
            and not _ai_task.done()
            and not sel_menu.active
        )
    ),
)
def handle_escape_interrupt(event):
    """Cancel active LLM request (same as /rewind).

    Removes the in-progress turn from history and
    shows the 'what will I do instead?' prompt.
    """
    _do_rewind(event.app)


@kb.add(
    "escape",
    filter=Condition(
        lambda: (
            bool(_dialog_floats)
            and not sel_menu.active
        )
    ),
)
def handle_escape_dialog(event):
    """Cancel an open wizard dialog."""
    if _wizard_cancel_fn is not None:
        _wizard_cancel_fn()
    event.app.invalidate()


def _scroll_main(event, delta):
    """
    Scroll the active tab buffer by delta
    lines. Works regardless of focus.
    Saves the new cursor position in tab.scroll_pos
    so it is preserved across tab switches.
    """
    tab = tab_mgr.tabs[tab_mgr.active]
    buf = tab.buffer
    if not buf:
        return
    doc = buf.document
    row = doc.cursor_position_row
    lines = doc.lines
    target = max(
        0,
        min(len(lines) - 1, row + delta),
    )
    pos = sum(
        len(lines[i]) + 1
        for i in range(target)
    )
    new_pos = min(pos, len(doc.text))
    buf.set_document(
        Document(
            text=doc.text,
            cursor_position=new_pos,
        ),
        bypass_readonly=True,
    )
    tab.scroll_pos = new_pos


# Mouse scroll bindings (work globally)
@kb.add(Keys.ScrollUp)
def handle_scroll_up(event):
    """Mouse wheel scroll up."""
    _scroll_main(event, -3)


@kb.add(Keys.ScrollDown)
def handle_scroll_down(event):
    """Mouse wheel scroll down."""
    _scroll_main(event, 3)


# ---------------------------------------------------
# Tab bindings
# ---------------------------------------------------
def _maybe_refresh_context(app) -> None:
    """Refresh dynamic buffers (Context, Tool Output)
    when their tab is the active one.
    """
    buf = tab_mgr.active_buffer()
    if buf is context_buffer:
        _refresh_context_buffer()
        app.invalidate()
    elif buf is tool_output_buffer:
        _refresh_tool_output_buffer()
        app.invalidate()


@kb.add("c-right")
def handle_tab_next(event):
    """Switch to next tab."""
    tab_mgr.next_tab()
    _maybe_refresh_context(event.app)
    event.app.invalidate()


@kb.add("c-left")
def handle_tab_prev(event):
    """Switch to previous tab."""
    tab_mgr.prev_tab()
    _maybe_refresh_context(event.app)
    event.app.invalidate()


@kb.add("c-t")
def handle_tab_new(event):
    """Open a new scratch tab."""
    tab_mgr.new_tab()
    event.app.invalidate()


@kb.add("c-w")
def handle_tab_close(event):
    """Close the active tab."""
    tab_mgr.close_tab()
    event.app.invalidate()


def _register_tab_jump(n):
    @kb.add("escape", str(n))
    def _jump(event):
        tab_mgr.goto_tab(n - 1)
        _maybe_refresh_context(event.app)
        event.app.invalidate()


for _tab_n in range(1, 10):
    _register_tab_jump(_tab_n)


# Debug: floating notification demo (no binding)
def _demo_notif():
    """Show floating notification (debug)."""
    notif_mgr.notify(
        "Operación completada con éxito",
        4.0,
    )


# Debug: inline notification demo (no binding)
def _demo_inline_notif(app):
    """Show inline notification (debug)."""
    append_text(
        build_inline_notif(
            "Sistema actualizado "
            "correctamente. Todos los "
            "servicios están operando "
            "con normalidad."
        )
    )
    app.invalidate()


# Debug: selection menu demo (no binding)
def _demo_selection_menu(app):
    """Show example selection menu (debug)."""
    options = [
        "Opción A: Analizar código",
        "Opción B: Generar reporte",
        "Opción C: Revisar logs",
    ]

    def on_select(idx):
        chosen = options[idx]
        notif_mgr.notify(
            f"✓ {chosen}", 3.0,
        )
        append_text(
            build_user_frame(chosen, _exec_mode)
        )
        app.invalidate()
        asyncio.ensure_future(
            handle_ai_response(
                app,
                chosen,
                _da_session,
            )
        )

    sel_menu.show(
        "¿Qué desea hacer?",
        options,
        on_select,
    )
    menu_text = sel_menu.build_frame()
    sel_menu._prev_lines = (
        menu_text.count("\n") + 1
    )
    append_text(menu_text)
    app.invalidate()


# Ctrl+P: toggle plan/execution mode
@kb.add("c-p")
def handle_ctrl_p(event):
    """Toggle plan/execution mode."""
    global _exec_mode
    old_mode = _exec_mode
    _exec_mode = (
        "plan"
        if _exec_mode == "execution"
        else "execution"
    )
    event.app.style = build_style(_exec_mode)
    append_text(
        build_inline_notif(
            f"Mode → {_exec_mode.upper()}",
            "⚙",
        )
    )
    if _da_session is not None:
        _da_session.mode = _exec_mode
        tool_names = ", ".join(
            s["function"]["name"]
            for s in _da_session.get_tool_schemas()
        )
        _da_session.fire_event(
            "on_mode_change",
            old_mode=old_mode,
            new_mode=_exec_mode,
            tools=tool_names,
        )
    event.app.invalidate()


def _redraw_menu(app):
    """Redraw the menu in the buffer."""
    if not sel_menu.active:
        return
    menu_text = sel_menu.build_frame()
    lc = menu_text.count("\n") + 1
    replace_last_block(
        sel_menu._prev_lines, menu_text
    )
    sel_menu._prev_lines = lc
    app.invalidate()


# ---------------------------------------------------
# Layout
# ---------------------------------------------------
top_bar = Window(
    content=FormattedTextControl(
        get_top_bar
    ),
    height=3,
    style=f"bg:{BG_PANEL}",
    align=WindowAlign.LEFT,
)

bot_bar = Window(
    content=FormattedTextControl(
        get_bot_bar
    ),
    height=3,
    style=f"bg:{BG_PANEL}",
    align=WindowAlign.LEFT,
)


# ---------------------------------------------------
# Tab bar (1-line strip between top bar and body)
# ---------------------------------------------------
def get_tab_bar():
    """Render tab bar: single-line strip.
    Each tab label is mouse-clickable.
    """
    from prompt_toolkit.mouse_events import (
        MouseEventType,
    )
    from prompt_toolkit.application import (
        get_app,
    )

    def _make_click(idx):
        def _handler(mouse_event):
            if mouse_event.event_type == (
                MouseEventType.MOUSE_UP
            ):
                tab_mgr.goto_tab(idx)
                _maybe_refresh_context(
                    get_app()
                )
                get_app().invalidate()
        return _handler

    w = bar_full_width()
    parts = []

    # ── Tab labels ───────────────────────────
    parts.append(("class:tab-bar", " "))
    tab_vis = 1
    for i, tab in enumerate(tab_mgr.tabs):
        sty = (
            "class:tab-bar.active"
            if i == tab_mgr.active
            else "class:tab-bar.inactive"
        )
        label = f" {tab.name} "
        parts.append(
            (sty, label, _make_click(i))
        )
        tab_vis += len(label)
        if i < len(tab_mgr.tabs) - 1:
            parts.append(
                ("class:tab-bar.sep", VT)
            )
            tab_vis += 1

    # ── ☒ close button (right-aligned) ───────
    close_btn = " ☒ "  # U+2612 ☒
    btn_w = len(close_btn)
    pad = max(0, w - tab_vis - btn_w)
    parts.append(
        ("class:tab-bar", " " * pad)
    )
    on_chat = tab_mgr.active == 0
    close_sty = (
        "class:tab-bar.close-dim"
        if on_chat
        else "class:tab-bar.close"
    )

    def _close_handler(mouse_event):
        if mouse_event.event_type == (
            MouseEventType.MOUSE_UP
        ):
            if tab_mgr.active != 0:
                tab_mgr.close_tab()
                get_app().invalidate()

    parts.append(
        (close_sty, close_btn, _close_handler)
    )
    return parts


tab_bar_window = Window(
    content=FormattedTextControl(
        get_tab_bar,
        focusable=False,
        show_cursor=False,
    ),
    height=1,
    style="class:top-bar",
    align=WindowAlign.LEFT,
)


def _make_scrollbar_text(content_win):
    """
    Return FormattedText for a 1-column scrollbar.
    Up/down arrow characters carry mouse handlers
    so clicking them scrolls the active tab buffer.
    """
    from prompt_toolkit.application import (
        get_app,
    )

    def _up(e):
        tab = tab_mgr.tabs[tab_mgr.active]
        buf = tab.buffer
        if not buf:
            return
        doc = buf.document
        lines = doc.lines
        inf = getattr(
            content_win, "render_info", None
        )
        if inf is not None:
            target = max(
                0, inf.vertical_scroll - 1
            )
        else:
            target = max(
                0,
                doc.cursor_position_row - 1,
            )
        pos = sum(
            len(lines[i]) + 1
            for i in range(target)
        )
        new_pos = min(pos, len(doc.text))
        buf.set_document(
            Document(
                text=doc.text,
                cursor_position=new_pos,
            ),
            bypass_readonly=True,
        )
        tab.scroll_pos = new_pos
        try:
            get_app().invalidate()
        except Exception:
            pass

    def _down(e):
        tab = tab_mgr.tabs[tab_mgr.active]
        buf = tab.buffer
        if not buf:
            return
        doc = buf.document
        lines = doc.lines
        inf = getattr(
            content_win, "render_info", None
        )
        if inf is not None:
            target = min(
                len(lines) - 1,
                inf.vertical_scroll
                + inf.window_height,
            )
        else:
            target = min(
                len(lines) - 1,
                doc.cursor_position_row + 1,
            )
        pos = sum(
            len(lines[i]) + 1
            for i in range(target)
        )
        new_pos = min(pos, len(doc.text))
        buf.set_document(
            Document(
                text=doc.text,
                cursor_position=new_pos,
            ),
            bypass_readonly=True,
        )
        tab.scroll_pos = new_pos
        try:
            get_app().invalidate()
        except Exception:
            pass

    info = getattr(content_win, "render_info", None)
    if info is None:
        return [
            ("class:scrollbar.arrow", "^", _up),
            ("", "\n"),
            ("class:scrollbar.background", " "),
            ("", "\n"),
            ("class:scrollbar.arrow", "v", _down),
        ]

    content_h = info.content_height
    win_h = info.window_height
    track_h = max(1, win_h - 2)

    try:
        frac_vis = (
            len(info.displayed_lines)
            / float(content_h)
        )
        frac_above = (
            info.vertical_scroll
            / float(content_h)
        )
        btn_h = max(
            1, int(track_h * frac_vis)
        )
        btn_top = int(track_h * frac_above)
    except ZeroDivisionError:
        btn_h = track_h
        btn_top = 0

    def _is_btn(row):
        return btn_top <= row < btn_top + btn_h

    frags = [
        ("class:scrollbar.arrow", "^", _up),
        ("", "\n"),
    ]
    for i in range(track_h):
        if _is_btn(i):
            st = (
                "class:scrollbar.button,scrollbar.end"
                if not _is_btn(i + 1)
                else "class:scrollbar.button"
            )
        else:
            st = (
                "class:scrollbar.background,"
                "scrollbar.start"
                if _is_btn(i + 1)
                else "class:scrollbar.background"
            )
        frags.append((st, " "))
        frags.append(("", "\n"))

    frags.append(
        ("class:scrollbar.arrow", "v", _down)
    )
    return frags


def _make_sb_win(get_win):
    """Build a 1-column scrollbar Window."""
    return Window(
        content=FormattedTextControl(
            lambda: _make_scrollbar_text(get_win())
        ),
        width=1,
        style="class:scrollbar.background",
    )


body_window = Window(
    content=BufferControl(
        buffer=main_buffer,
        lexer=FrameLexer(),
        input_processors=[
            MarkerStripProcessor(),
        ],
        focusable=False,
    ),
    style="class:scroll-area",
    wrap_lines=True,
    cursorline=False,
)

_body_sb_win = _make_sb_win(lambda: body_window)
_body_vsplit = VSplit([body_window, _body_sb_win])


def _make_tab_vsplit(tab):
    """Build content + scrollbar VSplit for a Tab."""
    if tab.read_only:
        _marked = tab.buffer is main_buffer
        win = Window(
            content=BufferControl(
                buffer=tab.buffer,
                lexer=(
                    FrameLexer() if _marked
                    else None
                ),
                input_processors=(
                    [MarkerStripProcessor()]
                    if _marked else []
                ),
                focusable=False,
            ),
            style="class:scroll-area",
            wrap_lines=True,
            cursorline=False,
        )
    else:
        win = Window(
            content=BufferControl(
                buffer=tab.buffer,
                focusable=True,
            ),
            style="class:scroll-area",
            wrap_lines=True,
        )
    sb = _make_sb_win(lambda: win)
    return VSplit([win, sb])


# Pre-build Chat window; body_window is reused
# so existing scroll-state is preserved.
# Other tabs are created lazily via open_buffer.
_tab_windows = {
    id(tab_mgr.tabs[0]): _body_vsplit,
}


def _get_body_window():
    """Return the VSplit for the active tab.

    Also restores the tab's saved scroll position
    into the buffer so the view resumes where the
    user last scrolled.
    """
    tab = tab_mgr.tabs[tab_mgr.active]
    key = id(tab)
    if key not in _tab_windows:
        _tab_windows[key] = _make_tab_vsplit(tab)
    # Restore saved scroll position if it differs
    # from the buffer's current cursor position.
    if tab.scroll_pos > 0:
        doc = tab.buffer.document
        cur = doc.cursor_position
        if cur != tab.scroll_pos:
            new_pos = min(
                tab.scroll_pos, len(doc.text)
            )
            tab.buffer.set_document(
                Document(
                    text=doc.text,
                    cursor_position=new_pos,
                ),
                bypass_readonly=True,
            )
    return _tab_windows[key]


body_container = DynamicContainer(
    _get_body_window
)

base_container = HSplit(
    [
        top_bar,
        tab_bar_window,
        body_container,
        bot_bar,
        input_area,
    ]
)


# Shared mutable float list
_active_floats = []


root_container = FloatContainer(
    content=base_container,
    floats=_active_floats,
)


# ---------------------------------------------------
# Dialog library test bindings (Ctrl+Z/X/V/B/N)
# ---------------------------------------------------

@kb.add("c-z")
def _test_dlg_input(event):
    """Test: single-line input dialog."""
    def _on_confirm(text):
        append_text(
            build_inline_notif(
                f"Input → {text!r}", "📝"
            )
        )
        event.app.invalidate()
    _dlg.show_input_dialog(
        event.app,
        title="Single-Line Input",
        label="Type something and press Submit:",
        on_confirm=_on_confirm,
        refocus=input_area,
    )


@kb.add("c-x")
def _close_current_tab(event):
    """Close the active tab (Ctrl+X).
    The Chat tab cannot be closed."""
    if tab_mgr.active == 0:
        return
    tab_mgr.close_tab()
    event.app.invalidate()


@kb.add("c-v")
def _test_dlg_menu(event):
    """Test: floating menu dialog."""
    options = [
        "Option Alpha",
        "Option Beta",
        "Option Gamma",
        "Option Delta",
    ]

    def _on_select(idx):
        append_text(
            build_inline_notif(
                f"Selected → {options[idx]}",
                "☑",
            )
        )
        event.app.invalidate()
    _dlg.show_menu_dialog(
        event.app,
        title="Menu Demo",
        options=options,
        on_select=_on_select,
        refocus=input_area,
    )


@kb.add("c-b")
def _test_dlg_toggle(event):
    """Test: toggle list dialog."""
    items = [
        "Feature: dark theme",
        "Feature: autosave",
        "Feature: spell check",
        "Feature: line numbers",
    ]

    def _on_confirm(checked):
        names = [items[i] for i in checked]
        msg = (
            ", ".join(names) if names
            else "(none)"
        )
        append_text(
            build_inline_notif(
                f"Enabled → {msg}", "✦"
            )
        )
        event.app.invalidate()
    _dlg.show_toggle_dialog(
        event.app,
        title="Toggle Demo",
        items=items,
        on_confirm=_on_confirm,
        refocus=input_area,
    )


@kb.add("c-n")
def _test_dlg_buttons(event):
    """Test: button dialog."""
    def _on_button(idx):
        labels = ["Yes", "No", "Cancel"]
        append_text(
            build_inline_notif(
                f"Button → {labels[idx]}", "🔘"
            )
        )
        event.app.invalidate()
    _dlg.show_button_dialog(
        event.app,
        title="Confirm Action",
        message=(
            "Do you want to proceed?\n"
            "This cannot be undone."
        ),
        buttons=["Yes", "No", "Cancel"],
        on_button=_on_button,
        refocus=input_area,
    )


# ---------------------------------------------------
# Application
# ---------------------------------------------------
def create_app():
    return Application(
        layout=Layout(
            root_container,
            focused_element=input_area,
        ),
        style=APP_STYLE,
        key_bindings=merge_key_bindings(
            [kb, _dlg.dialog_kb]
        ),
        full_screen=True,
        mouse_support=True,
        color_depth=None,
    )


# ---------------------------------------------------
# Input handler
def _build_help_md() -> str:
    """Return the /help command markdown text."""
    return (
        "## Available Commands\n"
        "\n"
        "- `/exit` — Shut down StarryCLI\n"
        "- `/clear` — Reset conversation "
        "and context (asks confirmation)\n"
        "- `/rewind` — Remove last message"
        " and response from context\n"
        "- `/summarize` — Summarize the "
        "conversation and save to file\n"
        "- `/help` — Show this help\n"
        "- `/init` — Generate AGENTS.md\n"
        "- `/setup` — Change provider, "
        "model, tools and theme\n"
        "- `/mode` — Select execution mode\n"
        "- `/role` — Display and change "
        "agent role\n"
        "- `/tools` — List active tools\n"
        "- `/skills` — Load a skill into "
        "the session\n"
        "- `/sessions` — Browse and resume "
        "saved sessions\n"
        "- `/rename` — Rename current session\n"
        "- `/buffer` — Manage buffers and"
        " tabs (list, open, close)\n"
        "- `/ask <question>` — One-shot "
        "subagent answer with full context."
        " Does not modify session history.\n"
        "- `/trace` — Show per-turn LLM and "
        "tool execution log for this session.\n"
        "- `<text>` — Send to StarryCLI AI\n"
        "\n"
        "### Keyboard Shortcuts\n"
        "\n"
        "- `Ctrl+P` — Toggle "
        "plan/execution mode\n"
        "- `Escape` — Cancel active AI "
        "request (/rewind) / cancel wizard\n"
        "- `PgUp/PgDn` — Scroll buffer\n"
        "- `Mouse wheel` — Scroll buffer\n"
        "- `Ctrl+C` — Quit\n"
        "\n"
        "**Tabs:**\n"
        "\n"
        "- `Ctrl+Right/Left` — "
        "Next/previous tab\n"
        "- `Ctrl+T` — New scratch tab\n"
        "- `Ctrl+W` — Close active tab\n"
        "- `Alt+1-9` — Jump to tab N\n"
        "\n"
        "**Selection menu** "
        "(when a menu is shown):\n"
        "\n"
        "- `Up/Down` — Navigate options\n"
        "- `Enter` — Confirm selection\n"
        "- `Escape` — Dismiss menu\n"
    )


def _build_agents_md() -> str:
    """Build AGENTS.md markdown from live config."""
    lines = [
        "# StarryLib — AGENTS.md\n\n",
        "## Overview\n\n",
        f"- Active provider: `{_active_provider()}`\n",
        f"- Active role: `{_active_role()}`\n",
        f"- Active mode: `{_exec_mode}`\n\n",
    ]
    lines.append("## Agents / Roles\n\n")
    if _da_settings:
        for rname, rcfg in (
            _da_settings.agents.items()
        ):
            tag = (
                " *(active)*"
                if rname == _active_role()
                else ""
            )
            lines.append(
                f"### {rname}{tag}\n\n"
            )
            lines.append(
                f"- Label: {rcfg.label}\n"
            )
            if rcfg.allowed_tools:
                tlist = ", ".join(rcfg.allowed_tools)
                lines.append(
                    f"- Tools: {tlist}\n"
                )
            if rcfg.model_override:
                lines.append(
                    f"- Model: "
                    f"{rcfg.model_override}\n"
                )
            lines.append("\n")
    lines.append("## Providers\n\n")
    if _da_settings:
        for pname, pcfg in (
            _da_settings.providers.items()
        ):
            tag = (
                " *(active)*"
                if pname == _active_provider()
                else ""
            )
            lbl = pcfg.label or pname
            lines.append(
                f"- **{lbl}** (`{pname}`)"
                f"{tag}: "
                f"`{pcfg.default_model}`\n"
            )
    lines.append("\n")
    lines.append("## Tools\n\n")
    if _da_session:
        schemas = (
            _da_session.get_tool_schemas()
        )
        for s in schemas:
            fn = s.get("function", {})
            n = fn.get("name", "?")
            d = fn.get("description", "")
            lines.append(f"- `{n}`: {d}\n")
        if not schemas:
            lines.append("- (none active)\n")
    else:
        lines.append("- (no session)\n")
    lines.append("\n")
    lines.append("## Skills\n\n")
    try:
        from starry_lib.skills.loader import (
            list_skills,
        )
        sk_list = list_skills()
        for sk in sk_list:
            loaded = (
                " *(loaded)*"
                if (
                    _da_session
                    and sk
                    in _da_session.active_skills
                )
                else ""
            )
            lines.append(
                f"- `{sk}`{loaded}\n"
            )
        if not sk_list:
            lines.append("- (none)\n")
    except Exception:
        lines.append("- (unavailable)\n")
    lines.append("\n")
    lines.append("## Events\n\n")
    try:
        import starry_lib as _da_mod
        evts_path = os.path.join(
            os.path.dirname(
                os.path.abspath(
                    _da_mod.__file__
                )
            ),
            "events",
        )
        evts = sorted(
            os.path.splitext(f)[0]
            for f in os.listdir(evts_path)
            if f.endswith(".md")
        )
        for ev in evts:
            lines.append(f"- `{ev}`\n")
        if not evts:
            lines.append("- (none)\n")
    except Exception:
        lines.append("- (unavailable)\n")
    return "".join(lines)


def _write_agents_md(
    path: str, content: str, app
) -> None:
    """Write content to *path* and notify."""
    try:
        with open(
            path, "w", encoding="utf-8"
        ) as fh:
            fh.write(content)
        append_text(
            build_inline_notif(
                f"AGENTS.md written to {path}",
                "📄",
            )
        )
    except Exception as exc:
        append_text(
            build_error_frame(str(exc))
        )
    app.invalidate()


# ===================================================
# /agent command — sub-handlers
# ===================================================


def _strip_addon_header(text: str) -> str:
    """Remove comment-header lines prepended by
    the prompt-addon dialogs before storing.
    Drops every leading line that starts with '#'
    and any blank lines that follow them.
    """
    lines = text.splitlines()
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines)

def _show_agent_menu(app):
    """Show the /agent top-level menu."""
    opts = [
        "A. Create agent",
        "B. List agents",
        "C. Edit agent",
        "D. Remove agent",
        "E. Chat with agent",
        "F. List active agents",
        "G. Chat with active agent",
        "H. Kill active agent",
    ]

    def on_select(idx):
        ch = opts[idx][0]
        if ch == "A":
            _agent_create(app)
        elif ch == "B":
            _agent_list(app)
        elif ch == "C":
            _agent_edit(app)
        elif ch == "D":
            _agent_remove(app)
        elif ch == "E":
            _agent_chat_start(app)
        elif ch == "F":
            _agent_list_active(app)
        elif ch == "G":
            _agent_chat_active(app)
        elif ch == "H":
            _agent_kill(app)

    _dlg.show_menu_dialog(
        app,
        title="/agent",
        options=opts,
        on_select=on_select,
        refocus=input_area,
    )


def _agent_create(app):
    """Wizard: create and save a new named agent."""
    from starry_lib.agents.agent_config import (
        AgentConfig as PAC,
    )
    from starry_lib.agents.agent_store import (
        agent_exists,
        save_agent,
    )
    _d: dict = {}

    def _step1():
        _dlg.show_input_dialog(
            app,
            title="Create Agent — Name",
            label="Agent slug (e.g. devbot):",
            on_confirm=_got_name,
            refocus=input_area,
        )

    def _got_name(name):
        name = name.strip().lower()
        name = name.replace(" ", "_")
        if not name:
            append_text(
                build_error_frame(
                    "Name cannot be empty."
                )
            )
            app.invalidate()
            return
        if agent_exists(name):
            append_text(
                build_warn_frame(
                    f"Agent '{name}' already"
                    " exists. Use Edit."
                )
            )
            app.invalidate()
            return
        _d["name"] = name
        _step2()

    def _step2():
        if _da_settings is None:
            return
        roles = list(
            _da_settings.agents.keys()
        )
        _dlg.show_menu_dialog(
            app,
            title="Create Agent — Role",
            options=roles,
            on_select=lambda i: _got_role(
                roles[i]
            ),
            refocus=input_area,
        )

    def _got_role(role):
        _d["role"] = role
        _step3()

    def _step3():
        if _da_settings is None:
            return
        provs = list(
            _da_settings.providers.keys()
        )
        _dlg.show_menu_dialog(
            app,
            title="Create Agent — Provider",
            options=provs,
            on_select=lambda i: _got_prov(
                provs[i]
            ),
            refocus=input_area,
        )

    def _got_prov(prov):
        _d["provider"] = prov
        asyncio.ensure_future(_step4_async())

    async def _step4_async():
        global _avail_models
        pname = _d["provider"]
        models = _avail_models.get(pname, [])
        if not models:
            if _da_settings is None:
                _got_model("")
                return
            pcfg = da.get_provider(
                _da_settings, pname
            )
            try:
                models = await da.list_models(
                    pcfg
                )
            except Exception:
                models = []
            if not models:
                models = [pcfg.default_model]
            _avail_models[pname] = models
        options = ["(default)"] + models
        _dlg.show_menu_dialog(
            app,
            title="Create Agent — Model",
            options=options,
            on_select=lambda i: _got_model(
                "" if i == 0 else models[i - 1]
            ),
            refocus=input_area,
        )

    def _got_model(model):
        _d["model"] = model.strip()
        _step5()

    def _step5():
        header = (
            f"# Role: {_d['role']}"
            " — your text below is"
            " appended to the role's"
            " system prompt\n\n"
        )
        _dlg.show_input_dialog(
            app,
            title="Create Agent — Prompt addon",
            label=(
                "Appended to the role's"
                " system prompt at spawn."
                " Add custom instructions"
                " below the comment line:"
            ),
            initial_text=header,
            on_confirm=_got_prompt,
            multiline=True,
            field_height=8,
            refocus=input_area,
        )

    def _got_prompt(prompt):
        _d["system_prompt_addon"] = (
            _strip_addon_header(prompt)
        )
        _step6()

    def _step6():
        _dlg.show_input_dialog(
            app,
            title="Create Agent — Temperature",
            label=(
                "Temperature"
                " (blank = role default):"
            ),
            on_confirm=_got_temp,
            refocus=input_area,
        )

    def _got_temp(temp):
        try:
            _d["temperature"] = (
                float(temp)
                if temp.strip()
                else 0.0
            )
        except ValueError:
            _d["temperature"] = 0.0
        _step7()

    def _step7():
        _dlg.show_input_dialog(
            app,
            title="Create Agent — Description",
            label="One-line description:",
            on_confirm=_got_desc,
            refocus=input_area,
        )

    def _got_desc(desc):
        _d["description"] = desc.strip()
        _d["label"] = (
            _d["name"]
            .replace("_", " ")
            .title()
        )
        cfg = PAC(**_d)
        save_agent(cfg)
        append_text(
            build_inline_notif(
                f"Agent '{cfg.name}' created.",
                "✓",
            )
        )
        app.invalidate()

    _step1()


def _agent_list(app):
    """Show a read-only list of stored agents."""
    from starry_lib.agents.agent_store import (
        list_agents,
    )
    agents = list_agents()
    if not agents:
        append_text(
            build_inline_notif(
                "No agents stored yet."
                " Use /agent → Create.",
                "i",
            )
        )
        app.invalidate()
        return
    lines = ["Stored agents:\n"]
    for a in agents:
        mdl = a.model or "(default)"
        lines.append(
            f"  {a.name}  role={a.role}"
            f"  provider={a.provider}"
            f"  model={mdl}\n"
            f"    {a.description}\n"
        )
    append_text(
        build_ai_frame("".join(lines))
    )
    app.invalidate()


def _agent_edit(app):
    """Edit an existing stored agent."""
    from starry_lib.agents.agent_store import (
        get_agent,
        list_agents,
        save_agent,
    )
    from starry_lib.agents.agent_config import (
        AgentConfig as PAC,
    )
    agents = list_agents()
    if not agents:
        append_text(
            build_warn_frame("No agents stored.")
        )
        app.invalidate()
        return
    names = [a.name for a in agents]
    _d: dict = {}

    def _pick(idx):
        cfg = get_agent(names[idx])
        if cfg is None:
            return
        _d.update({
            "name": cfg.name,
            "label": cfg.label,
            "role": cfg.role,
            "provider": cfg.provider,
            "model": cfg.model,
            "system_prompt_addon": (
                cfg.system_prompt_addon
            ),
            "temperature": cfg.temperature,
            "description": cfg.description,
            "allowed_tools": cfg.allowed_tools,
            "denied_tools": cfg.denied_tools,
            "allowed_skills": (
                cfg.allowed_skills
            ),
            "denied_skills": cfg.denied_skills,
        })
        asyncio.ensure_future(
            _edit_model_async()
        )

    async def _edit_model_async():
        global _avail_models
        pname = _d["provider"]
        models = _avail_models.get(pname, [])
        if not models:
            if _da_settings is None:
                _edit_prompt()
                return
            pcfg = da.get_provider(
                _da_settings, pname
            )
            try:
                models = await da.list_models(
                    pcfg
                )
            except Exception:
                models = []
            if not models:
                models = [pcfg.default_model]
            _avail_models[pname] = models
        current = _d.get("model", "")
        options = [
            "(default)"
            + (" ◀" if not current else "")
        ] + [
            m + (" ◀" if m == current else "")
            for m in models
        ]

        def _on_select(i):
            chosen = (
                "" if i == 0
                else models[i - 1]
            )
            _d["model"] = chosen
            _edit_prompt()

        _dlg.show_menu_dialog(
            app,
            title=(
                f"Edit {_d['name']}"
                " — Model"
            ),
            options=options,
            on_select=_on_select,
            refocus=input_area,
        )

    def _edit_prompt():
        header = (
            f"# Role: {_d['role']}"
            " — your text below is"
            " appended to the role's"
            " system prompt\n\n"
        )
        existing = _d.get(
            "system_prompt_addon", ""
        )
        _dlg.show_input_dialog(
            app,
            title=(
                f"Edit {_d['name']}"
                " — Prompt addon"
            ),
            label=(
                "Appended to the role's"
                " system prompt at spawn."
                " Edit your custom"
                " instructions below:"
            ),
            initial_text=header + existing,
            on_confirm=_save_prompt,
            multiline=True,
            field_height=8,
            refocus=input_area,
        )

    def _save_prompt(v):
        _d["system_prompt_addon"] = (
            _strip_addon_header(v)
        )
        _edit_temp()

    def _edit_temp():
        _dlg.show_input_dialog(
            app,
            title=(
                f"Edit {_d['name']}"
                " — Temperature"
            ),
            label=(
                "Temperature"
                " (0 = role default):"
            ),
            initial_text=str(
                _d["temperature"]
            ),
            on_confirm=_save_temp,
            refocus=input_area,
        )

    def _save_temp(v):
        try:
            _d["temperature"] = (
                float(v) if v.strip() else 0.0
            )
        except ValueError:
            _d["temperature"] = 0.0
        _edit_desc()

    def _edit_desc():
        _dlg.show_input_dialog(
            app,
            title=(
                f"Edit {_d['name']}"
                " — Description"
            ),
            label="Description:",
            initial_text=_d["description"],
            on_confirm=_save_all,
            refocus=input_area,
        )

    def _save_all(desc):
        _d["description"] = desc.strip()
        cfg = PAC(**_d)
        save_agent(cfg)
        append_text(
            build_inline_notif(
                f"Agent '{cfg.name}' updated.",
                "✓",
            )
        )
        app.invalidate()

    _dlg.show_menu_dialog(
        app,
        title="Edit — Select agent",
        options=names,
        on_select=_pick,
        refocus=input_area,
    )


def _agent_remove(app):
    """Remove a stored agent (kill if active)."""
    from starry_lib.agents.agent_store import (
        delete_agent,
        list_agents,
    )
    agents = list_agents()
    if not agents:
        append_text(
            build_warn_frame("No agents stored.")
        )
        app.invalidate()
        return
    names = [a.name for a in agents]

    def _pick(idx):
        name = names[idx]
        is_active = (
            _active_registry is not None
            and _active_registry.is_active(name)
        )
        msg = f"Remove agent '{name}'?"
        if is_active:
            msg += " (currently active — will kill)"

        def _confirm(bidx):
            if bidx != 0:
                return
            if is_active and _active_registry:
                asyncio.ensure_future(
                    _do_kill_agent(app, name)
                )
            delete_agent(name)
            append_text(
                build_inline_notif(
                    f"Agent '{name}' removed.",
                    "✓",
                )
            )
            app.invalidate()

        _dlg.show_button_dialog(
            app,
            title="Remove agent",
            message=msg,
            buttons=["Yes, remove", "Cancel"],
            on_button=_confirm,
            refocus=input_area,
        )

    _dlg.show_menu_dialog(
        app,
        title="Remove — Select agent",
        options=names,
        on_select=_pick,
        refocus=input_area,
    )


def _agent_chat_start(app):
    """Option E: spawn + chat with an agent."""
    from starry_lib.agents.agent_store import (
        list_agents,
    )
    if _da_settings is None or _da_pool is None:
        append_text(
            build_warn_frame(
                "Session not ready."
            )
        )
        app.invalidate()
        return
    agents = list_agents()
    if not agents:
        append_text(
            build_warn_frame(
                "No agents stored."
                " Use /agent → Create."
            )
        )
        app.invalidate()
        return
    names = [a.name for a in agents]

    def _pick(idx):
        name = names[idx]
        asyncio.ensure_future(
            _spawn_and_enter(app, name, owned=True)
        )

    _dlg.show_menu_dialog(
        app,
        title="Chat with agent",
        options=names,
        on_select=_pick,
        refocus=input_area,
    )


async def _spawn_and_enter(app, name, owned):
    """Spawn agent, create buffers, push stack."""
    global _active_registry, _session_stack
    if _active_registry is None:
        from starry_lib.agents.active_registry\
            import ActiveRegistry
        _active_registry = ActiveRegistry()
        _init_agent_tools()
    if _active_registry.is_active(name):
        session = _active_registry.get_session(
            name
        )
    else:
        try:
            session = (
                await _active_registry
                .spawn_agent(
                    name, _da_pool, _da_settings
                )
            )
        except Exception as exc:
            append_text(
                build_error_frame(
                    f"Could not spawn"
                    f" '{name}': {exc}"
                )
            )
            app.invalidate()
            return
    if _agent_chat_buf(name) is None:
        _spawn_agent_bufs(app, name)
    _session_stack.append(
        {"name": name, "owned": owned}
    )
    app.invalidate()


def _agent_list_active(app):
    """Option F: list all active agents."""
    if _active_registry is None:
        append_text(
            build_inline_notif(
                "No agents are currently active.",
                "i",
            )
        )
        app.invalidate()
        return
    active = _active_registry.list_active()
    if not active:
        append_text(
            build_inline_notif(
                "No active agents.", "i"
            )
        )
        app.invalidate()
        return
    lines = ["Active agents:\n"]
    for info in active:
        lines.append(
            f"  {info.name}"
            f"  role={info.role}"
            f"  turns={info.turn_count}\n"
        )
    append_text(
        build_ai_frame("".join(lines))
    )
    app.invalidate()


def _agent_chat_active(app):
    """Option G: enter chat with active agent."""
    if (
        _active_registry is None
        or not _active_registry.list_names()
    ):
        append_text(
            build_warn_frame(
                "No active agents."
            )
        )
        app.invalidate()
        return
    names = _active_registry.list_names()

    def _pick(idx):
        name = names[idx]
        asyncio.ensure_future(
            _spawn_and_enter(
                app, name, owned=False
            )
        )

    _dlg.show_menu_dialog(
        app,
        title="Chat with active agent",
        options=names,
        on_select=_pick,
        refocus=input_area,
    )


def _agent_kill(app):
    """Option H: kill an active agent."""
    if (
        _active_registry is None
        or not _active_registry.list_names()
    ):
        append_text(
            build_warn_frame(
                "No active agents."
            )
        )
        app.invalidate()
        return
    names = _active_registry.list_names()

    def _pick(idx):
        name = names[idx]

        def _confirm(bidx):
            if bidx != 0:
                return
            asyncio.ensure_future(
                _do_kill_agent(app, name)
            )

        _dlg.show_button_dialog(
            app,
            title="Kill agent",
            message=(
                f"Kill agent '{name}'?"
            ),
            buttons=["Yes, kill", "Cancel"],
            on_button=_confirm,
            refocus=input_area,
        )

    _dlg.show_menu_dialog(
        app,
        title="Kill agent — Select",
        options=names,
        on_select=_pick,
        refocus=input_area,
    )


def _init_agent_tools():
    """Wire up agent tools with registry + pool."""
    from starry_lib.tools.implementations\
        .list_active_agents import (
        set_registry as _set_lar,
    )
    from starry_lib.tools.implementations\
        .call_agent import (
        set_context as _set_ca,
    )
    from starry_lib.tools.implementations\
        .stop_agent import (
        set_context as _set_sa,
    )
    _set_lar(_active_registry)
    _set_ca(
        _active_registry,
        _da_pool,
        _da_settings,
        _on_agent_log,
    )
    _set_sa(
        _active_registry,
        _da_pool,
        lambda: _da_session,
    )


# ---------------------------------------------------
def setup_input_handler(app):
    notif_mgr.set_app(app)

    def accept_handler(buff):
        global _app_mode, _prev_mode
        global _tui_input_mode
        global _pending_questions
        text = buff.text.strip()
        if not text:
            return

        # ── question answer gate ───────────
        if _tui_input_mode == "question":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            if _da_session is not None:
                _da_session.answer_question(text)
            _tui_input_mode = "chat"
            _pending_questions.clear()
            app.invalidate()
            return

        # ── Agent session routing ──────────
        global _session_stack, _active_registry
        global _ai_task
        if _session_stack:
            top = _session_stack[-1]
            aname = top["name"]
            if text.lower() == "/close":
                _session_stack.pop()
                if top.get("owned"):
                    asyncio.ensure_future(
                        _do_kill_agent(
                            app, aname
                        )
                    )
                else:
                    tab_mgr.goto_tab(0)
                    app.invalidate()
                return
            if text.lower() != "/exit":
                asc = (
                    _active_registry
                    .get_session(aname)
                    if _active_registry
                    else None
                )
                if asc is not None:
                    _append_agent_buf(
                        aname,
                        build_user_frame(
                            text, _exec_mode
                        ),
                    )
                    app.invalidate()
                    _ai_task = (
                        asyncio.ensure_future(
                            handle_agent_response(
                                app, text,
                                asc, aname,
                            )
                        )
                    )
                    return

        # ── Command prefix auto-run ───────
        _ALL_COMMANDS = [
            "/exit", "/clear", "/rewind",
            "/summarize", "/help", "/tools",
            "/skills", "/sessions", "/rename",
            "/ask", "/trace", "/mode",
            "/role", "/setup", "/init",
            "/buffer", "/stats", "/agent",
            "/close",
        ]
        if (
            text.startswith("/")
            and " " not in text
            and len(text) >= 4
            and text.lower() not in _ALL_COMMANDS
        ):
            tl = text.lower()
            matches = [
                c for c in _ALL_COMMANDS
                if c.startswith(tl)
            ]
            if len(matches) == 1:
                text = matches[0]

        # ── /exit ─────────────────────────
        if text.lower() == "/exit":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            append_text(
                f"{M_ATHINK}"
                "  Shutting down"
                " StarryCLI..."
            )
            app.invalidate()

            async def delayed_exit():
                await asyncio.sleep(0.5)
                app.exit()

            asyncio.ensure_future(
                delayed_exit()
            )
            return

        # ── /clear ────────────────────────
        if text.lower() == "/clear":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            app.invalidate()

            def on_clear_confirm(idx):
                global _auto_approved
                global _autosum_triggered
                if idx == 0:
                    if _da_session is not None:
                        _da_session\
                            .clear_history()
                        _da_session\
                            .reset_tokens()
                    _auto_approved.clear()
                    _autosum_triggered = False
                    welcome = make_welcome()
                    main_buffer.set_document(
                        Document(
                            text=welcome,
                            cursor_position=len(
                                welcome
                            ),
                        ),
                        bypass_readonly=True,
                    )
                    append_text(
                        build_inline_notif(
                            "Conversation"
                            " cleared.",
                            "✓",
                        )
                    )
                else:
                    append_text(
                        build_inline_notif(
                            "Cancelled.", "↩"
                        )
                    )
                app.invalidate()

            _dlg.show_button_dialog(
                app,
                title="Clear conversation",
                message=(
                    "This will reset the"
                    " conversation."
                    " Continue?"
                ),
                buttons=[
                    "Yes, clear everything",
                    "No, cancel",
                ],
                on_button=on_clear_confirm,
                refocus=input_area,
            )
            return

        # ── /rewind ───────────────────────
        if text.lower() == "/rewind":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            app.invalidate()
            _do_rewind(app)
            return

        # ── /summarize ────────────────────
        if text.lower() == "/summarize":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            app.invalidate()
            asyncio.ensure_future(
                _run_summarize(app)
            )
            return

        # ── /help ─────────────────────────
        if text.lower() == "/help":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            append_text(
                build_ai_frame(_build_help_md())
            )
            app.invalidate()
            return

        # ── /tools ────────────────────────
        if text.lower() == "/tools":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            _show_toggle_tool(app)
            return

        # ── /skills ───────────────────────
        if text.lower() == "/skills":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            _show_toggle_skill(app)
            return

        # ── /sessions ─────────────────────
        if text.lower() == "/sessions":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            try:
                from starry_lib.sessions.store\
                    import list_sessions
                saved = list_sessions()
            except Exception:
                saved = []
            if not saved:
                append_text(
                    build_inline_notif(
                        "No saved sessions.",
                        "💾",
                    )
                )
                app.invalidate()
                return
            labels = [
                (
                    f"{s['session_id']} "
                    f"{s['role']} "
                    f"[{s['provider']}/"
                    f"{s['model']}] "
                    f"{s['message_count']}msg "
                    f"{s.get('last_used_at', s['saved_at'][:16])}"
                )
                for s in saved
            ]
            labels.append(
                "── Remove all sessions"
            )

            def _do_restore(chosen):
                global _exec_mode
                if _da_session is None:
                    return
                try:
                    from starry_lib.sessions\
                        .store import load
                    data = load(
                        chosen["hash"]
                    )
                    restored = (
                        _da_session.restore_from(
                            data, _da_settings
                        )
                    )
                    global SESSION_NAME
                    raw_id = data.get(
                        "session_id",
                        chosen["hash"],
                    )
                    if not raw_id.startswith(
                        "session-"
                    ):
                        raw_id = (
                            f"session-{raw_id}"
                        )
                    _da_session._id = raw_id
                    SESSION_NAME = raw_id
                    _exec_mode = (
                        restored["mode"]
                    )
                    app.style = build_style(
                        _exec_mode
                    )
                    for w in (
                        restored["warnings"]
                    ):
                        append_text(
                            build_warn_frame(w)
                        )
                    append_text(
                        build_inline_notif(
                            "Session restored."
                            f" Provider:"
                            f" {_da_session.provider},"
                            f" Model:"
                            f" {_da_session.model}",
                            "↩",
                        )
                    )
                    for entry in (
                        _da_session.display_log
                    ):
                        _replay_display_entry(
                            entry
                        )
                    _refresh_tool_output_buffer()
                except Exception as exc:
                    append_text(
                        build_error_frame(
                            str(exc)
                        )
                    )
                app.invalidate()

            def on_session_select(idx):
                if idx == len(saved):
                    # Remove all sessions
                    def on_confirm_all(cidx):
                        if cidx == 0:
                            from starry_lib\
                                .sessions.store\
                                import delete_all
                            n = delete_all()
                            append_text(
                                build_inline_notif(
                                    f"Deleted"
                                    f" {n}"
                                    " session(s).",
                                    "🗑",
                                )
                            )
                        else:
                            append_text(
                                build_inline_notif(
                                    "Delete"
                                    " cancelled.",
                                    "↩",
                                )
                            )
                        app.invalidate()

                    _dlg.show_button_dialog(
                        app,
                        title=(
                            "Remove all sessions"
                        ),
                        message=(
                            "Delete ALL saved"
                            " sessions?"
                            " This cannot be"
                            " undone."
                        ),
                        buttons=[
                            "Yes, delete all",
                            "Cancel",
                        ],
                        on_button=on_confirm_all,
                        refocus=input_area,
                    )
                    return

                # Session selected — open or delete
                chosen = saved[idx]
                short = chosen["session_id"]

                def on_session_action(aidx):
                    if aidx == 0:
                        _do_restore(chosen)
                    elif aidx == 1:
                        def on_del_confirm(
                            cidx
                        ):
                            if cidx == 0:
                                from starry_lib\
                                    .sessions\
                                    .store import (
                                        delete
                                        as _del,
                                    )
                                _del(
                                    chosen["hash"]
                                )
                                append_text(
                                    build_inline_notif(
                                        "Session"
                                        " deleted.",
                                        "🗑",
                                    )
                                )
                            else:
                                append_text(
                                    build_inline_notif(
                                        "Cancelled.",
                                        "↩",
                                    )
                                )
                            app.invalidate()

                        _dlg.show_button_dialog(
                            app,
                            title=(
                                "Delete session"
                            ),
                            message=(
                                f"Delete"
                                f" {short}?"
                            ),
                            buttons=[
                                "Yes, delete",
                                "Cancel",
                            ],
                            on_button=(
                                on_del_confirm
                            ),
                            refocus=input_area,
                        )

                _dlg.show_menu_dialog(
                    app,
                    title="Session",
                    options=[
                        "Open session",
                        "Delete this session",
                    ],
                    on_select=on_session_action,
                    refocus=input_area,
                )

            _dlg.show_menu_dialog(
                app,
                title="Sessions",
                options=labels,
                on_select=on_session_select,
                refocus=input_area,
                max_visible=12,
            )
            return

        # ── /rename ───────────────────────
        if text.lower() == "/rename":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            app.invalidate()

            def _rename_dialog(app=app):
                f_ref = [None]
                _cb = [None]
                field = TextArea(
                    multiline=False,
                    text=SESSION_NAME,
                    accept_handler=(
                        lambda buf: (
                            _cb[0]()
                            if _cb[0]
                            else None
                        )
                    ),
                )

                def _finish():
                    new_name = (
                        field.text.strip()
                    )
                    if not new_name:
                        return
                    # Check uniqueness
                    from starry_lib\
                        .sessions.store import (
                        _sessions_dir,
                    )
                    sd = _sessions_dir()
                    if (sd / new_name).exists():
                        append_text(
                            build_warn_frame(
                                f"Name "
                                f"'{new_name}'"
                                f" already in"
                                f" use."
                            )
                        )
                        app.invalidate()
                        return
                    global SESSION_NAME
                    old = SESSION_NAME
                    # Rename on disk if saved
                    from starry_lib\
                        .sessions.store import (
                        rename_session,
                    )
                    rename_session(old, new_name)
                    # Update in-memory state
                    if _da_session is not None:
                        _da_session._id = (
                            new_name
                        )
                    SESSION_NAME = new_name
                    global _wizard_cancel_fn
                    _wizard_cancel_fn = None
                    close_dialog(app, f_ref[0])
                    append_text(
                        build_inline_notif(
                            f"Session renamed"
                            f" to: {new_name}",
                            "✏",
                        )
                    )
                    app.invalidate()

                def _cancel():
                    global _wizard_cancel_fn
                    _wizard_cancel_fn = None
                    close_dialog(app, f_ref[0])
                    append_text(
                        build_inline_notif(
                            "Rename cancelled.",
                            "↩",
                        )
                    )
                    app.invalidate()

                _cb[0] = _finish
                f = _make_wizard_float(
                    "Rename Session",
                    "New session name:",
                    field,
                )
                f_ref[0] = f
                global _wizard_cancel_fn
                _wizard_cancel_fn = _cancel
                show_dialog(app, f)
                app.layout.focus(field)

            _rename_dialog()
            return

        # ── /ask ──────────────────────────
        if text.lower().startswith("/ask"):
            question = text[4:].strip()
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            if not question:
                append_text(
                    build_inline_notif(
                        "Usage: /ask <question>",
                        "◈",
                    )
                )
                app.invalidate()
                return
            asyncio.ensure_future(
                _run_ask_subagent(app, question)
            )
            return

        # ── /trace ────────────────────────
        if text.lower() == "/trace":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            if _da_session is None:
                append_text(
                    build_warn_frame(
                        "No active session."
                    )
                )
            else:
                entries = _da_session.trace
                if not entries:
                    append_text(
                        build_inline_notif(
                            "No trace entries yet.",
                            "→",
                        )
                    )
                else:
                    lines = ["Session trace:\n"]
                    for e in entries:
                        tok = (
                            str(e.tokens_used)
                            if e.tokens_used
                            else ""
                        )
                        lat = (
                            f"{e.latency_ms}ms"
                            if e.latency_ms
                            else ""
                        )
                        lines.append(
                            f"  [{e.turn}]"
                            f" {e.type}"
                            f" {e.name or ''}"
                            f" {lat}"
                            f" {tok + 'tok' if tok else ''}"
                        )
                    append_text(
                        build_ai_frame(
                            "\n".join(lines)
                        )
                    )
            app.invalidate()
            return

        # ── /mode ─────────────────────────
        if text.lower() == "/mode":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            modes = ["plan", "execution"]

            def on_mode_select(idx):
                global _exec_mode
                old_mode = _exec_mode
                _exec_mode = modes[idx]
                app.style = build_style(
                    _exec_mode
                )
                append_text(
                    build_inline_notif(
                        f"Mode → "
                        f"{_exec_mode.upper()}",
                        "⚙",
                    )
                )
                if _da_session is not None:
                    _da_session.mode = _exec_mode
                    tool_names = ", ".join(
                        s["function"]["name"]
                        for s in _da_session.get_tool_schemas()
                    )
                    _da_session.fire_event(
                        "on_mode_change",
                        old_mode=old_mode,
                        new_mode=_exec_mode,
                        tools=tool_names,
                    )
                app.invalidate()

            _dlg.show_menu_dialog(
                app,
                title="Select Mode",
                options=modes,
                on_select=on_mode_select,
                refocus=input_area,
            )
            return

        # ── /role ─────────────────────────
        if text.lower() == "/role":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            _role_menu(app)
            return

        # ── /setup ────────────────────────
        if text.lower() == "/setup":
            append_text(
                build_user_frame(text, _exec_mode)
            )
            app.invalidate()
            _prev_mode = _app_mode
            _app_mode = "setup"

            setup_opts = [
                "Provider",
                "Toggle tool",
                "Toggle skill",
                "Theme",
                "Context format",
                "AutoSummarize",
                "Default conversation",
                "User personalization",
                "Reset defaults",
                "About",
            ]

            def on_setup_select(idx):
                global _app_mode
                chosen = setup_opts[idx]

                if chosen == "Provider":
                    _show_provider_submenu(app)
                    _app_mode = _prev_mode

                elif chosen == "Toggle tool":
                    _show_toggle_tool(app)
                    _app_mode = _prev_mode

                elif chosen == "Toggle skill":
                    _show_toggle_skill(app)
                    _app_mode = _prev_mode

                elif chosen == "Theme":
                    _show_change_theme(app)
                    _app_mode = _prev_mode

                elif chosen == (
                    "Context format"
                ):
                    _show_context_format(app)
                    _app_mode = _prev_mode

                elif chosen == "AutoSummarize":
                    _show_autosummarize_setup(
                        app
                    )
                    _app_mode = _prev_mode

                elif chosen == (
                    "Default conversation"
                ):
                    _show_default_convo(app)
                    _app_mode = _prev_mode

                elif chosen == (
                    "User personalization"
                ):
                    _show_user_personalization(
                        app
                    )
                    _app_mode = _prev_mode

                elif chosen == "Reset defaults":
                    _reset_defaults(app)
                    _app_mode = _prev_mode

                elif chosen == "About":
                    _show_about(app)
                    _app_mode = _prev_mode

            _dlg.show_menu_dialog(
                app,
                title="Setup",
                options=setup_opts,
                on_select=on_setup_select,
                refocus=input_area,
            )
            return

        # ── /stats ────────────────────────
        if text.lower() == "/stats":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            app.invalidate()
            _show_stats(app)
            return

        # ── /init ─────────────────────────
        if text.lower() == "/init":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            if _da_settings is None:
                append_text(
                    build_warn_frame(
                        "Settings not loaded."
                        " Cannot generate"
                        " AGENTS.md."
                    )
                )
                app.invalidate()
                return
            content = _build_agents_md()
            append_text(
                build_ai_frame(content)
            )
            app.invalidate()
            out = os.path.join(
                os.getcwd(), "AGENTS.md"
            )
            if os.path.exists(out):
                def on_overwrite(idx):
                    if idx == 0:
                        _write_agents_md(
                            out, content, app
                        )
                _dlg.show_button_dialog(
                    app,
                    title="AGENTS.md exists",
                    message=(
                        "AGENTS.md already"
                        " exists. Overwrite?"
                    ),
                    buttons=[
                        "Yes, overwrite",
                        "No, keep existing",
                    ],
                    on_button=on_overwrite,
                    refocus=input_area,
                )
            else:
                _write_agents_md(
                    out, content, app
                )
            return

        # ── /close ────────────────────────
        if text.lower() == "/close":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            append_text(
                build_warn_frame(
                    "No active agent session."
                )
            )
            app.invalidate()
            return

        # ── /agent ────────────────────────
        if text.lower() == "/agent":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            app.invalidate()
            _show_agent_menu(app)
            return

        # ── /buffer ───────────────────────
        if text.lower() == "/buffer":
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            app.invalidate()

            buf_opts = [
                "Open buffer",
                "Close tab",
            ]

            def _on_buffer_menu(idx):
                chosen = buf_opts[idx]

                if chosen == "Open buffer":
                    all_bufs = buf_reg.list_all()
                    open_labels = []
                    for cname, _ in all_bufs:
                        marker = (
                            "*"
                            if tab_mgr.has_tab(
                                cname
                            )
                            else " "
                        )
                        open_labels.append(
                            f"[{marker}] {cname}"
                        )

                    def _on_open(i):
                        cname = (
                            all_bufs[i][0]
                        )
                        result = (
                            tab_mgr.open_buffer(
                                cname
                            )
                        )
                        if result == "switched":
                            msg = (
                                f"Switched to"
                                f" existing tab"
                                f" **{cname}**."
                            )
                        else:
                            msg = (
                                f"Opened new tab"
                                f" **{cname}**."
                            )
                        _maybe_refresh_context(
                            app
                        )
                        append_text(
                            build_ai_frame(msg)
                        )
                        app.invalidate()

                    _dlg.show_menu_dialog(
                        app,
                        title="Open buffer",
                        options=open_labels,
                        on_select=_on_open,
                        refocus=input_area,
                        max_visible=12,
                    )

                elif chosen == "Close tab":
                    closeable = [
                        tab.name
                        for tab in tab_mgr.tabs
                        if tab.name.lower()
                        != "chat"
                    ]
                    if not closeable:
                        append_text(
                            build_warn_frame(
                                "No tabs to"
                                " close (only"
                                " Chat is open)."
                            )
                        )
                        app.invalidate()
                        return

                    def _on_close(i):
                        name = closeable[i]
                        result = (
                            tab_mgr
                            .close_tab_by_name(
                                name
                            )
                        )
                        if result is True:
                            append_text(
                                build_ai_frame(
                                    f"Closed tab"
                                    f" **{name}**."
                                    " Switched to"
                                    " Chat."
                                )
                            )
                        else:
                            append_text(
                                build_error_frame(
                                    result
                                )
                            )
                        app.invalidate()

                    _dlg.show_menu_dialog(
                        app,
                        title="Close tab",
                        options=closeable,
                        on_select=_on_close,
                        refocus=input_area,
                        max_visible=12,
                    )

            _dlg.show_menu_dialog(
                app,
                title="Buffer",
                options=buf_opts,
                on_select=_on_buffer_menu,
                refocus=input_area,
            )
            return

        # ── Unknown slash command ──────────
        if text.startswith("/"):
            append_text(
                build_user_frame(
                    text, _exec_mode
                )
            )
            append_text(
                build_error_frame(
                    f"Unknown command:"
                    f" '{text}'. "
                    "Type /help for a"
                    " list of commands."
                )
            )
            append_text(
                build_ai_frame(
                    _build_help_md()
                )
            )
            app.invalidate()
            return

        # ── Default: send to LLM ──────────
        append_text(
            build_user_frame(text, _exec_mode)
        )
        app.invalidate()
        _ai_task = asyncio.ensure_future(
            handle_ai_response(
                app, text, _da_session
            )
        )

    input_area.buffer.accept_handler = (
        accept_handler
    )


# ---------------------------------------------------
# Telemetry refresh
# ---------------------------------------------------
async def telemetry_refresh(app):
    while True:
        await asyncio.sleep(2.0)
        try:
            app.invalidate()
        except Exception:
            break


# ---------------------------------------------------
# Entry point
# ---------------------------------------------------
def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for davy_cli."""
    parser = argparse.ArgumentParser(
        prog="davy_cli.py",
        description="StarryCLI TUI",
    )
    parser.add_argument(
        "--session",
        metavar="HASH",
        default=None,
        help=(
            "Resume a saved session by hash "
            "or hash prefix."
        ),
    )
    return parser.parse_args()


async def _save_session_on_exit(
    session,
) -> None:
    """Save session to disk and print resume hint."""
    if session is None:
        return
    try:
        from starry_lib.sessions.store import (
            save as store_save,
        )
        store_save(session)
        print(
            f"\nSession saved.\n"
            f"Resume with: davy_cli.py"
            f" --session {session.id}",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"\nCould not save session: {exc}",
            file=sys.stderr,
        )


async def main():
    global _da_settings, _da_session
    global _exec_mode
    global _context_format
    global _autosum_enabled, _autosum_threshold
    global _autosum_msg_limit
    global _default_system_prompt
    global _default_temperature
    global _default_max_tokens, _default_top_p
    global _user_name, _user_profile

    args = _parse_args()

    # Load library settings; keep startup locals
    # until the session is created.
    init_err = None
    _first_run = False
    _init_provider = ""
    _init_role = ""
    _init_model = ""
    try:
        _da_settings = da.load_settings()
        _init_provider = (
            _da_settings.active_provider or ""
        )
        _init_role = (
            _da_settings.active_role
        )
        if _init_provider:
            pcfg = da.get_provider(
                _da_settings, _init_provider
            )
            _init_model = pcfg.default_model
        else:
            # No active_provider → first run
            _first_run = True
    except Exception as exc:
        init_err = str(exc)
        _da_settings = None

    # Merge user-created roles
    if _da_settings is not None:
        _load_user_roles()

    # Apply saved user preferences
    if _da_settings is not None:
        _prefs = _load_user_prefs()
        if (
            _prefs.get("provider")
            and _prefs["provider"]
            in _da_settings.providers
        ):
            _init_provider = _prefs["provider"]
            try:
                pcfg = da.get_provider(
                    _da_settings, _init_provider
                )
                _init_model = pcfg.default_model
            except Exception:
                pass
        if _prefs.get("model"):
            _init_model = _prefs["model"]
        if (
            _prefs.get("role")
            and _prefs["role"]
            in _da_settings.agents
        ):
            _init_role = _prefs["role"]
        if _prefs.get("theme"):
            _apply_theme(_prefs["theme"])
        if _prefs.get("context_format") in (
            "markdown", "json"
        ):
            _context_format = (
                _prefs["context_format"]
            )
        if isinstance(
            _prefs.get("autosum_enabled"), bool
        ):
            _autosum_enabled = (
                _prefs["autosum_enabled"]
            )
        if isinstance(
            _prefs.get("autosum_threshold"), int
        ):
            _autosum_threshold = (
                _prefs["autosum_threshold"]
            )
        if isinstance(
            _prefs.get("autosum_msg_limit"), int
        ):
            _autosum_msg_limit = (
                _prefs["autosum_msg_limit"]
            )
        if isinstance(
            _prefs.get("default_system_prompt"),
            str,
        ):
            _default_system_prompt = (
                _prefs["default_system_prompt"]
            )
        if isinstance(
            _prefs.get("default_temperature"),
            (int, float),
        ):
            _default_temperature = float(
                _prefs["default_temperature"]
            )
        if isinstance(
            _prefs.get("default_max_tokens"), int
        ):
            _default_max_tokens = (
                _prefs["default_max_tokens"]
            )
        if isinstance(
            _prefs.get("default_top_p"),
            (int, float),
        ):
            _default_top_p = float(
                _prefs["default_top_p"]
            )
        if isinstance(
            _prefs.get("user_name"), str
        ):
            _user_name = _prefs["user_name"]
        if isinstance(
            _prefs.get("user_profile"), str
        ):
            _user_profile = (
                _prefs["user_profile"]
            )

    app = create_app()
    setup_input_handler(app)

    # Build initial buffer content
    welcome = make_welcome()
    if init_err:
        init_content = (
            welcome + "\n"
            + build_error_frame(
                f"Config error: {init_err}"
            )
        )
    else:
        init_content = welcome

    main_buffer.set_document(
        Document(
            text=init_content,
            cursor_position=len(init_content),
        ),
        bypass_readonly=True,
    )

    refresh_task = asyncio.ensure_future(
        telemetry_refresh(app)
    )

    # Startup toast
    notif_mgr.notify(
        "StarryCLI ready",
        4.0,
    )

    # First-run: no provider configured → enter setup
    if _first_run:
        global _app_mode, _prev_mode
        _prev_mode = _app_mode
        _app_mode = "setup"

    if _da_settings is not None:
        prefetch_task = asyncio.ensure_future(
            _prefetch_models_task()
        )
        async with da.AgentPool(
            _da_settings
        ) as pool:
            global _da_pool
            _da_pool = pool
            from starry_lib.tools.implementations\
                .task import set_pool as _set_pool
            _set_pool(pool)
            # Bootstrap agent registry + tools
            global _active_registry
            from starry_lib.agents.active_registry\
                import ActiveRegistry
            _active_registry = ActiveRegistry()
            _init_agent_tools()
            try:
                _da_session = (
                    await pool.spawn(
                        role=_init_role,
                        provider=_init_provider,
                    )
                )
            except Exception as exc:
                append_text(
                    build_error_frame(
                        f"Session failed: "
                        f"{exc}"
                    )
                )
            if _da_session is not None:
                # Prefix id to canonical form
                _da_session._id = (
                    "session-"
                    + _da_session._id
                )
                SESSION_NAME = _da_session._id
                try:
                    _da_session.set_model(
                        _init_model
                    )
                except Exception:
                    pass
                _apply_session_overrides(
                    _da_session
                )
            # Restore saved session history
            if (
                args.session is not None
                and _da_session is not None
            ):
                try:
                    from starry_lib.sessions.store\
                        import load as store_load
                    saved = store_load(
                        args.session
                    )
                    restored = (
                        _da_session.restore_from(
                            saved, _da_settings
                        )
                    )
                    # Sync session id & name
                    raw_id = saved.get(
                        "session_id",
                        args.session,
                    )
                    if not raw_id.startswith(
                        "session-"
                    ):
                        raw_id = (
                            f"session-{raw_id}"
                        )
                    _da_session._id = raw_id
                    SESSION_NAME = raw_id
                    _exec_mode = (
                        restored["mode"]
                    )
                    app.style = build_style(
                        _exec_mode
                    )
                    for w in (
                        restored["warnings"]
                    ):
                        append_text(
                            build_warn_frame(w)
                        )
                    append_text(
                        build_inline_notif(
                            "Session restored."
                            f" Provider:"
                            f" {_da_session.provider},"
                            f" Model:"
                            f" {_da_session.model}",
                            "↩",
                        )
                    )
                    for entry in (
                        _da_session.display_log
                    ):
                        _replay_display_entry(
                            entry
                        )
                    _refresh_tool_output_buffer()
                except Exception as exc:
                    append_text(
                        build_error_frame(
                            f"Could not restore "
                            f"session: {exc}"
                        )
                    )
            try:
                await app.run_async()
            finally:
                refresh_task.cancel()
                prefetch_task.cancel()
                for t in [
                    refresh_task,
                    prefetch_task,
                ]:
                    try:
                        await t
                    except (
                        asyncio.CancelledError
                    ):
                        pass
                await _save_session_on_exit(
                    _da_session
                )
    else:
        # Offline mode — no LLM available
        try:
            await app.run_async()
        finally:
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass


def run():
    """Sync entry point for console_scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
