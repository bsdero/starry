#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       sessions/store.py
# DESCRIPTION: Session persistence — save/load/list
# SUMMARY: Serialises Session state to JSON files
#          under ~/.local/starry/sessions/<id>/.
#          Each session lives in its own directory.
#          load() accepts a full session_id or a
#          unique prefix of one.
# NOTES: Per-session directory layout:
#          <sessions_root>/
#            session-<uuid>/   ← default name
#              session.json    ← session data
#              summary_*.md    ← /summarize outputs
#        Custom-named sessions use the user name
#        as directory name (no session- prefix).
#        Legacy flat <uuid>.json files are still
#        readable for backward compatibility.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/21/2026    bsdero     Initial implementation
# 04/30/2026    bsdero     Per-session directories
"""Session persistence: save, load, list."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sessions_dir() -> Path:
    """Return (and create) the sessions root."""
    base = Path(
        os.environ.get(
            "STARRY_SESSIONS_DIR",
            Path.home() / ".local" / "starry" / "sessions",
        )
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def session_dir(session_id: str) -> Path:
    """Return (and create) the session directory.

    The directory is:
      <sessions_root>/<session_id>/
    session_id is used as-is (already includes
    the 'session-' prefix for default sessions).
    """
    d = _sessions_dir() / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(session: Any) -> Path:
    """Serialise *session* to disk.

    Writes to:
      <sessions_root>/<session._id>/session.json

    Returns the Path of the written file.
    """
    sid = session._id
    history = []
    for m in session._history:
        entry = {
            "role": m.role,
            "content": m.content,
        }
        if m.metadata:
            entry.update(m.metadata)
        history.append(entry)
    data = {
        "session_id": sid,
        "saved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "mode": session._mode,
        "provider": session._provider_name,
        "model": session._agent.model,
        "role": session._agent.name,
        "message_count": len(history),
        "history": history,
        "display_log": session._display_log,
    }
    sdir = session_dir(sid)
    path = sdir / "session.json"
    path.write_text(
        json.dumps(
            data, indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    return path


# ── Internal helpers ─────────────────────────────


def _load_dir(p: Path) -> dict:
    """Read session.json from a session dir."""
    return json.loads(
        (p / "session.json").read_text(
            encoding="utf-8"
        )
    )


def _iter_session_dirs(d: Path):
    """Yield directories that contain session.json."""
    if not d.exists():
        return
    for p in d.iterdir():
        if p.is_dir() and (
            p / "session.json"
        ).exists():
            yield p


def _iter_legacy_files(d: Path):
    """Yield legacy flat *.json session files."""
    if not d.exists():
        return
    for p in d.glob("*.json"):
        yield p


# ── Public API ───────────────────────────────────


def load(hash_arg: str) -> dict:
    """Load a session by id or unique prefix.

    Accepts:
      session-<id>   canonical form
      <id>           bare UUID or custom name
      <prefix>       unique prefix of either

    Raises FileNotFoundError if nothing matches,
    or ValueError if the prefix is ambiguous.
    """
    d = _sessions_dir()
    bare = (
        hash_arg[8:]
        if hash_arg.startswith("session-")
        else hash_arg
    )

    dirs = list(_iter_session_dirs(d))

    # Exact match (fast path)
    for p in dirs:
        if (
            p.name == hash_arg
            or p.name == f"session-{bare}"
        ):
            return _load_dir(p)

    # Prefix match across all session dirs
    seen: set = set()
    matches = []
    for p in dirs:
        if (
            p.name.startswith(hash_arg)
            or p.name.startswith(
                f"session-{bare}"
            )
        ) and p not in seen:
            seen.add(p)
            matches.append(p)

    if len(matches) == 1:
        return _load_dir(matches[0])
    if len(matches) > 1:
        ids = ", ".join(
            p.name for p in matches
        )
        raise ValueError(
            f"Ambiguous prefix '{hash_arg}'"
            f" matches: {ids}"
        )

    # Legacy flat-file fallback
    for p in _iter_legacy_files(d):
        if p.stem in (bare, hash_arg):
            return json.loads(
                p.read_text(encoding="utf-8")
            )
    leg = [
        p for p in _iter_legacy_files(d)
        if (
            p.stem.startswith(bare)
            or p.stem.startswith(hash_arg)
        )
    ]
    if len(leg) == 1:
        return json.loads(
            leg[0].read_text(encoding="utf-8")
        )
    if len(leg) > 1:
        ids = ", ".join(p.stem for p in leg)
        raise ValueError(
            f"Ambiguous prefix '{hash_arg}'"
            f" matches: {ids}"
        )

    raise FileNotFoundError(
        f"No session matching '{hash_arg}'."
    )


def delete(session_id: str) -> bool:
    """Delete a session by id or unique prefix.

    Returns True if deleted, False otherwise.
    """
    d = _sessions_dir()
    bare = (
        session_id[8:]
        if session_id.startswith("session-")
        else session_id
    )

    dirs = list(_iter_session_dirs(d))
    matches = [
        p for p in dirs
        if (
            p.name == session_id
            or p.name == f"session-{bare}"
            or p.name.startswith(session_id)
            or p.name.startswith(
                f"session-{bare}"
            )
        )
    ]
    if len(matches) == 1:
        shutil.rmtree(
            matches[0], ignore_errors=True
        )
        return True

    # Legacy flat-file fallback
    for p in _iter_legacy_files(d):
        if p.stem in (bare, session_id):
            p.unlink(missing_ok=True)
            return True
    return False


def delete_all() -> int:
    """Delete all saved sessions.

    Returns the number of sessions removed.
    """
    d = _sessions_dir()
    count = 0
    for p in _iter_session_dirs(d):
        shutil.rmtree(p, ignore_errors=True)
        count += 1
    for p in _iter_legacy_files(d):
        p.unlink(missing_ok=True)
        count += 1
    return count


def rename_session(
    old_id: str,
    new_name: str,
) -> bool:
    """Rename a session directory.

    old_id   — current session id (canonical or bare)
    new_name — new identifier (no path separators)

    Returns True on success, False if not found or
    destination already exists.
    """
    d = _sessions_dir()
    bare = (
        old_id[8:]
        if old_id.startswith("session-")
        else old_id
    )

    dirs = list(_iter_session_dirs(d))
    matches = [
        p for p in dirs
        if (
            p.name == old_id
            or p.name == f"session-{bare}"
        )
    ]
    if len(matches) != 1:
        return False

    src = matches[0]
    dst = d / new_name
    if dst.exists():
        return False

    src.rename(dst)

    sj = dst / "session.json"
    if sj.exists():
        data = json.loads(
            sj.read_text(encoding="utf-8")
        )
        data["session_id"] = new_name
        sj.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return True


def list_sessions() -> list[dict]:
    """Return metadata for all saved sessions.

    Each entry contains:
      session_id    — canonical session id
      hash          — directory/file name on disk
      role          — agent role name
      provider      — provider name
      model         — model name
      mode          — plan | execution
      message_count — number of history messages
      saved_at      — ISO-8601 timestamp string
      last_used_at  — 'YYYY-MM-DD HH:MM'
    Sorted newest first by saved_at.
    """
    d = _sessions_dir()
    raw = []

    for p in _iter_session_dirs(d):
        try:
            data = json.loads(
                (p / "session.json").read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            continue
        msg_count = data.get("message_count", 0)
        if msg_count == 0:
            continue
        saved_at = data.get("saved_at", "")
        sid = data.get("session_id", p.name)
        raw.append((saved_at, {
            "session_id": sid,
            "hash": p.name,
            "role": data.get("role", ""),
            "provider": data.get("provider", ""),
            "model": data.get("model", ""),
            "mode": data.get(
                "mode", "execution"
            ),
            "message_count": msg_count,
            "saved_at": saved_at,
            "last_used_at": _fmt_time(saved_at),
        }))

    # Legacy flat-file support
    for p in _iter_legacy_files(d):
        try:
            data = json.loads(
                p.read_text(encoding="utf-8")
            )
        except Exception:
            continue
        msg_count = data.get("message_count", 0)
        if msg_count == 0:
            continue
        saved_at = data.get("saved_at", "")
        sid = data.get("session_id", p.stem)
        # Normalise legacy IDs to session- form
        if not sid.startswith("session-"):
            sid = f"session-{sid}"
        raw.append((saved_at, {
            "session_id": sid,
            "hash": p.stem,
            "role": data.get("role", ""),
            "provider": data.get("provider", ""),
            "model": data.get("model", ""),
            "mode": data.get(
                "mode", "execution"
            ),
            "message_count": msg_count,
            "saved_at": saved_at,
            "last_used_at": _fmt_time(saved_at),
        }))

    raw.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in raw]


def _fmt_time(iso_str: str) -> str:
    """Format ISO timestamp to 'YYYY-MM-DD HH:MM'."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16].replace("T", " ")
