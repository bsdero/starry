#! /usr/bin/env python3
#
# Copyright 2025-present Lenovo
#
# NAME:       websearch.py
# DESCRIPTION: Websearch tool — keyword-based web search
# SUMMARY: Supports DuckDuckGo (free), Tavily, and Exa
#          backends selected via 'backend' arg or config.
# NOTES: Available in plan and execution modes.
#        API keys read from env: TAVILY_API_KEY, EXA_API_KEY.
#        Falls back to DuckDuckGo when no key is configured.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/22/2026    ahernandez86    Initial implementation
"""websearch tool: keyword-based web search."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

SCHEMA = {
    "type": "function",
    "function": {
        "name": "websearch",
        "description": (
            "Search the web by keyword and return "
            "a list of results with title, url, "
            "and snippet."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": (
                        "Maximum results to return "
                        "(default 5)."
                    ),
                    "default": 5,
                },
                "backend": {
                    "type": "string",
                    "description": (
                        "Search backend: 'auto', "
                        "'duckduckgo', 'tavily', "
                        "or 'exa'."
                    ),
                    "enum": [
                        "auto",
                        "duckduckgo",
                        "tavily",
                        "exa",
                    ],
                    "default": "auto",
                },
            },
            "required": ["query"],
        },
    },
}


def _tavily(query: str, max_results: int) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY not set")
    payload = json.dumps({
        "query": query,
        "max_results": max_results,
    }).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        }
        for r in data.get("results", [])
    ]


def _exa(query: str, max_results: int) -> list[dict]:
    key = os.environ.get("EXA_API_KEY")
    if not key:
        raise RuntimeError("EXA_API_KEY not set")
    try:
        from exa_py import Exa  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "exa-py not installed: "
            "pip install exa-py"
        ) from exc
    client = Exa(api_key=key)
    resp = client.search(query, num_results=max_results)
    return [
        {
            "title": getattr(r, "title", ""),
            "url": getattr(r, "url", ""),
            "snippet": getattr(r, "text", ""),
        }
        for r in resp.results
    ]


def _duckduckgo(
    query: str, max_results: int
) -> list[dict]:
    try:
        from duckduckgo_search import (  # type: ignore
            DDGS,
        )
    except ImportError as exc:
        raise RuntimeError(
            "duckduckgo-search not installed: "
            "pip install duckduckgo-search"
        ) from exc
    results = list(
        DDGS().text(query, max_results=max_results)
    )
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results
    ]


# (name, requires_env_key)
_BACKENDS: dict[str, tuple] = {
    "tavily": (_tavily, "TAVILY_API_KEY"),
    "exa": (_exa, "EXA_API_KEY"),
    "duckduckgo": (_duckduckgo, None),
}
_AUTO_ORDER = ["tavily", "exa", "duckduckgo"]


def execute(
    query: str,
    max_results: int = 5,
    backend: str = "auto",
) -> dict:
    """Search the web and return results."""
    order = (
        _AUTO_ORDER if backend == "auto" else [backend]
    )
    warnings: list[str] = []

    for name in order:
        fn, key_env = _BACKENDS[name]
        if (
            backend == "auto"
            and key_env is not None
            and not os.environ.get(key_env)
        ):
            continue
        try:
            results = fn(query, max_results)
            out: dict = {
                "results": results,
                "count": len(results),
                "backend": name,
            }
            if warnings:
                out["warnings"] = warnings
            return out
        except Exception as exc:
            warnings.append(f"{name}: {exc}")

    return {
        "error": "All backends failed",
        "warnings": warnings,
    }
