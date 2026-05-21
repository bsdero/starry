#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       webfetch.py
# DESCRIPTION: Webfetch tool — retrieve web content
# SUMMARY: HTTP GET via urllib. Returns raw text or parsed
#          JSON. Uses a StarryLib User-Agent header.
# NOTES: Available in plan and execution modes.
#        No third-party HTTP deps required.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/17/2026    ahernandez86          Initial implementation
"""webfetch tool: retrieve content from a URL."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

SCHEMA = {
    "type": "function",
    "function": {
        "name": "webfetch",
        "description": (
            "Retrieve content from a URL via HTTP "
            "GET. Returns text or parsed JSON."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch.",
                },
                "format": {
                    "type": "string",
                    "description": (
                        "Response format: "
                        "'text' or 'json'."
                    ),
                    "enum": ["text", "json"],
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Timeout in seconds "
                        "(default 15)."
                    ),
                    "default": 15,
                },
            },
            "required": ["url", "format"],
        },
    },
}


def execute(
    url: str,
    format: str = "text",
    timeout: int = 15,
) -> dict:
    """Fetch URL and return content."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "StarryLib/0.1"
            },
        )
        with urllib.request.urlopen(
            req, timeout=timeout
        ) as resp:
            raw = resp.read().decode(
                "utf-8", errors="replace"
            )
    except urllib.error.URLError as exc:
        return {"error": f"URL error: {exc}"}
    except Exception as exc:
        return {"error": str(exc)}

    if format == "json":
        try:
            return {"content": json.loads(raw)}
        except json.JSONDecodeError as exc:
            return {
                "error": (
                    f"JSON parse failed: {exc}"
                ),
                "raw": raw[:500],
            }
    return {"content": raw}
