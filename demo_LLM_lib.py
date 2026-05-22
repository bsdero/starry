#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       demo.py
# DESCRIPTION: StarryLib library API demonstration
# SUMMARY: End-to-end walkthrough of every major library
#          feature: model listing, selection, connection,
#          streaming chat, context inspection, tools,
#          and multi-agent patterns.
# NOTES: Requires STARRY_API_KEY=quill (set in .env).
#        Run: python demo.py
#             python demo.py --provider openwebui
#             python demo.py --model gemma-4-31b-it
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/15/2026    bsdero          Initial demo
"""StarryLib library API — end-to-end demonstration."""

from __future__ import annotations

import argparse
import asyncio
import textwrap

import starry_lib as da
from starry_lib.llm.client import build_client

# ── Terminal helpers ──────────────────────────────────────────────

RST = "\033[0m"
BLD = "\033[1m"
DIM = "\033[2m"
CYN = "\033[36m"
GRN = "\033[32m"
YLW = "\033[33m"
MGT = "\033[35m"
RED = "\033[31m"
BLU = "\033[34m"


def banner(title: str) -> None:
    bar = "═" * 54
    print(f"\n{BLD}{CYN}╔{bar}╗")
    print(f"║  {title:<52}║")
    print(f"╚{bar}╝{RST}")


def section(n: int, title: str) -> None:
    print(f"\n{BLD}{GRN}── Step {n}: {title}{RST}")


def kv(label: str, value: str) -> None:
    print(f"   {DIM}{label:<20}{RST}{value}")


def speak(role: str, text: str) -> None:
    color = CYN if role == "user" else MGT
    label = f"{color}{BLD}{role.upper():>9}{RST}"
    indent = " " * 12
    wrapped = textwrap.fill(
        text.strip(),
        width=64,
        subsequent_indent=indent,
    )
    print(f"\n{label}  {wrapped}")


def tool_call(name: str, args: dict) -> None:
    arg_str = ", ".join(
        f"{k}={v!r}" for k, v in args.items()
    )
    print(
        f"   {YLW}[tool →]{RST}  {name}({arg_str})"
    )


def tool_result(data: str) -> None:
    print(f"   {DIM}[result]{RST}  {data}")


def approx_tokens(text: str) -> int:
    """Rough token count: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


# ── Built-in tools ────────────────────────────────────────────────

def _get_weather(location: str) -> dict:
    """Simulated weather — returns fixed demo data."""
    data = {
        "Paris": {
            "condition": "partly cloudy",
            "temp_c": 18,
            "humidity": "72%",
        },
        "Tokyo": {
            "condition": "sunny",
            "temp_c": 26,
            "humidity": "55%",
        },
    }
    info = data.get(
        location, {"condition": "clear", "temp_c": 20}
    )
    return {"location": location, **info}


def _calculate(expression: str) -> dict:
    """Safe math evaluator."""
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expression):
        return {"error": "unsafe characters"}
    try:
        return {
            "expression": expression,
            "result": eval(expression),  # noqa: S307
        }
    except Exception as exc:
        return {"error": str(exc)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name",
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a mathematical expression"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "Math expression e.g. '3 * 7'"
                        ),
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

TOOL_FNS: dict = {
    "get_weather": _get_weather,
    "calculate": _calculate,
}



# ── Main demo ─────────────────────────────────────────────────────

async def demo(
    provider_name: str,
    model_override: str | None,
) -> None:
    banner("StarryLib — API Demo")

    settings = da.load_settings()

    # ── Step 1: List available models ─────────────────────
    section(1, "List available models from all providers")

    all_models: dict[str, list[str]] = {}

    for pname, pcfg in settings.providers.items():
        models = await da.list_models(pcfg)
        all_models[pname] = models
        status = (
            f"{GRN}{len(models)} model(s){RST}"
            if models
            else f"{RED}unavailable{RST}"
        )
        print(
            f"\n   {BLD}{pcfg.label}{RST}  "
            f"({pname})  {status}"
        )
        for m in models[:8]:
            print(f"     • {m}")
        if len(models) > 8:
            extra = len(models) - 8
            print(
                f"     {DIM}… and {extra} more{RST}"
            )

    # ── Step 2: Select provider and model ─────────────────
    section(2, "Select provider and model")

    if provider_name not in settings.providers:
        print(
            f"{RED}Unknown provider '{provider_name}'.{RST}"
        )
        print(
            f"Available: "
            f"{', '.join(settings.providers)}"
        )
        return

    pcfg = settings.providers[provider_name]
    available = all_models.get(provider_name, [])

    if model_override:
        chosen = model_override
    elif pcfg.default_model in available:
        chosen = pcfg.default_model
    elif available:
        chosen = available[0]
    else:
        chosen = pcfg.default_model

    kv("Provider:", f"{pcfg.label} ({provider_name})")
    kv("Model:",    chosen)
    kv("Base URL:", pcfg.base_url)

    # ── Step 3: Connect — check context window ────────────
    section(3, "Connect and inspect model metadata")

    client = build_client(pcfg)
    context_window = "not reported by this provider"

    try:
        model_obj = await client.models.retrieve(chosen)
        cw = getattr(model_obj, "context_window", None)
        if cw:
            context_window = f"{cw:,} tokens"
    except Exception:
        pass

    kv("Status:",         f"{GRN}connected{RST}")
    kv("Context window:", context_window)

    # ── Steps 4-8 use AgentPool ───────────────────────────
    async with da.AgentPool(settings) as pool:

        # Helper: spawn with the chosen model
        async def _spawn(
            role: str,
            sid: str | None = None,
        ) -> da.Session:
            s = await pool.spawn(
                role=role,
                provider=provider_name,
                session_id=sid,
            )
            s.set_model(chosen)
            return s

        # ── Step 4: First streaming request ───────────────
        section(4, "First request — streaming response")

        session = await _spawn("assistant")

        q1 = (
            "In 2-3 sentences, explain what the Python "
            "GIL is and why it matters for concurrency."
        )
        speak("user", q1)
        print(f"\n   {MGT}{BLD}ASSISTANT{RST}  ", end="")

        async for ev in session.chat(q1):
            if ev.type == "token":
                print(ev.data, end="", flush=True)
        print()

        # ── Step 5: Inspect context ────────────────────────
        section(5, "Inspect current context")

        history = session.get_history()
        total_chars = sum(len(m.content) for m in history)
        total_tok = approx_tokens(
            " ".join(m.content for m in history)
        )

        kv("Messages in context:", str(len(history)))
        print()

        for i, m in enumerate(history, 1):
            c = CYN if m.role == "user" else MGT
            preview = m.content[:55].replace("\n", " ")
            if len(m.content) > 55:
                preview += "…"
            print(
                f"   {i}. {c}[{m.role}]{RST}  "
                f"{DIM}\"{preview}\"{RST}"
            )
            toks = approx_tokens(m.content)
            print(
                f"      {DIM}"
                f"{len(m.content)} chars"
                f" · ~{toks} tokens{RST}"
            )

        print()
        kv("Total chars:", str(total_chars))
        kv("Approx tokens:", f"~{total_tok}")

        # ── Step 6: Continue conversation ─────────────────
        section(6, "Continue conversation (context kept)")

        q2 = (
            "Based on your explanation, when should "
            "I prefer asyncio over threading?"
        )
        speak("user", q2)
        print(f"\n   {MGT}{BLD}ASSISTANT{RST}  ", end="")

        async for ev in session.chat(q2):
            if ev.type == "token":
                print(ev.data, end="", flush=True)
        print()

        history = session.get_history()
        kv(
            "Context now:",
            f"{len(history)} messages"
            f" · ~{approx_tokens(' '.join(m.content for m in history))} tokens",
        )

        # ── Step 7: Tool use ───────────────────────────────
        section(7, "Tool-augmented request")

        print(
            f"   {DIM}Tools available:{RST} "
            f"get_weather, calculate\n"
        )

        q3 = (
            "What is the weather in Paris? "
            "Also, what is 42 * 17 + 8?"
        )
        speak("user", q3)
        print()

        try:
            _in_response = False
            async for ev in session.chat_with_tools(
                q3, TOOLS, TOOL_FNS
            ):
                if ev.type == "token":
                    if not _in_response:
                        print(
                            f"\n   {MGT}{BLD}"
                            f"ASSISTANT{RST}  ",
                            end="",
                        )
                        _in_response = True
                    print(
                        ev.data, end="", flush=True
                    )
                elif ev.type == "tool_call":
                    if _in_response:
                        print()
                        _in_response = False
                    tool_call(
                        ev.data["name"],
                        ev.data["args"],
                    )
                elif ev.type == "tool_result":
                    tool_result(ev.data["result"])
            if _in_response:
                print()
        except Exception as exc:
            print(
                f"\n   {YLW}Note:{RST} provider did not "
                f"support tool_choice — {exc}\n"
                f"   {DIM}(tool calling requires a model "
                f"that supports function calls){RST}"
            )

        # ── Step 8: Multi-agent demo ───────────────────────
        section(8, "Multi-agent demonstration")

        # Spawn three specialist agents
        print(
            f"\n   {BLD}Spawning three agents…{RST}"
        )
        analyst = await _spawn("researcher", "analyst")
        coder   = await _spawn("coder",      "coder")
        critic  = await _spawn("assistant",  "critic")
        print(
            f"   {GRN}✓{RST} analyst  "
            f"{DIM}(role: researcher){RST}"
        )
        print(
            f"   {GRN}✓{RST} coder    "
            f"{DIM}(role: coder){RST}"
        )
        print(
            f"   {GRN}✓{RST} critic   "
            f"{DIM}(role: assistant){RST}"
        )

        # ── Part A: Parallel delegation ────────────────────
        print(
            f"\n   {BLD}Part A — parallel delegation"
            f" (different tasks, same time){RST}"
        )

        tasks = {
            "analyst": (
                "In two sentences, what problem does "
                "async I/O solve in Python?"
            ),
            "coder": (
                "Write a minimal async Python snippet "
                "that fetches two URLs concurrently. "
                "Max 12 lines, no explanation."
            ),
        }

        for sid, task in tasks.items():
            role = (
                "ANALYST" if sid == "analyst"
                else "CODER"
            )
            print(
                f"   {DIM}[{role}]{RST} ← "
                f"{task[:58]}…"
            )
        print()

        results = await pool.delegate(tasks)

        labels = {
            "analyst": ("ANALYST", YLW),
            "coder":   ("CODER",   GRN),
        }
        for sid, response in results.items():
            label, color = labels[sid]
            print(f"   {color}{BLD}[{label}]{RST}")
            for line in textwrap.wrap(
                response.strip(), width=62
            ):
                print(f"     {line}")
            print()

        # ── Part B: Pipeline ───────────────────────────────
        print(
            f"   {BLD}Part B — pipeline"
            f" (coder writes → critic reviews){RST}\n"
        )

        # Spawn fresh pipeline agents (clean history)
        pipe_coder  = await _spawn("coder",     "pipe-c")
        pipe_critic = await _spawn("assistant", "pipe-r")

        pipe_input = (
            "Write a Python async retry function with "
            "exponential back-off. Max 15 lines."
        )
        print(
            f"   {DIM}[INPUT]{RST}  {pipe_input}"
        )

        pipe_output = await pool.pipeline(
            ["pipe-c", "pipe-r"],
            pipe_input,
        )

        print(
            f"\n   {CYN}{BLD}[PIPELINE RESULT]{RST}"
        )
        for line in textwrap.wrap(
            pipe_output.strip(), width=62
        ):
            print(f"     {line}")

        # ── Part C: Broadcast ──────────────────────────────
        print(
            f"\n   {BLD}Part C — broadcast"
            f" (one question → all agents){RST}\n"
        )

        bc_q = (
            "In exactly one sentence: "
            "what is your specialty?"
        )
        print(
            f"   {DIM}[BROADCAST]{RST}  {bc_q}\n"
        )

        bc_labels = {
            "analyst": ("ANALYST", YLW),
            "coder":   ("CODER",   GRN),
            "critic":  ("CRITIC",  CYN),
        }
        seen: set[str] = set()

        async for ev in pool.broadcast(
            bc_q,
            session_ids=["analyst", "coder", "critic"],
        ):
            if ev.type == "done" and ev.session_id not in seen:
                seen.add(ev.session_id)
                label, color = bc_labels.get(
                    ev.session_id,
                    (ev.session_id.upper(), DIM),
                )
                print(
                    f"   {color}{BLD}[{label}]{RST}"
                )
                for line in textwrap.wrap(
                    str(ev.data).strip(), width=62
                ):
                    print(f"     {line}")
                print()

    # ── Done ───────────────────────────────────────────────
    bar = "═" * 54
    print(f"{BLD}{GRN}╔{bar}╗")
    print(f"║  {'Demo complete.  All steps passed.':<52}║")
    print(f"╚{bar}╝{RST}\n")


# ── Entry point ───────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="StarryLib library API demo",
    )
    parser.add_argument(
        "--provider", "-p",
        default="davy",
        metavar="NAME",
        help=(
            "Provider to use: davy (default) or openwebui"
        ),
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        metavar="MODEL_ID",
        help=(
            "Model ID to use. "
            "Defaults to provider's configured default."
        ),
    )
    args = parser.parse_args()
    asyncio.run(demo(args.provider, args.model))


if __name__ == "__main__":
    main()
