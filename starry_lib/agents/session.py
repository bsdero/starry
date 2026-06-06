#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       session.py
# DESCRIPTION: Session — single conversation with history
# SUMMARY: Wraps one agent + LLM client; maintains conversation
#          history and yields AgentEvent streams.
# NOTES: The shared Semaphore (from AgentPool) caps concurrent
#        LLM requests across all sessions in the pool.
#        Obtain a Session via AgentPool.spawn(), not directly.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/15/2026    bsdero          Initial implementation
# 04/17/2026    bsdero          Add mode, tool schemas,
#                               chat_auto()
"""Session: one conversation with persistent history."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Literal

from openai import AsyncOpenAI

from starry_lib.agents.base import BaseAgent
from starry_lib.llm.client import call_with_retry
from starry_lib.config.settings import (
    AppSettings,
    ProviderConfig,
)
from starry_lib.types import AgentEvent, Message, SessionInfo
from starry_lib.observability.trace import (
    Tracer,
    TraceEntry,
)


class Session:
    """One conversation: agent + client + history + semaphore.

    Obtain a Session via AgentPool.spawn() rather than
    constructing directly.
    """

    def __init__(
        self,
        session_id: str,
        agent: BaseAgent,
        client: AsyncOpenAI,
        provider_name: str,
        semaphore: asyncio.Semaphore,
        mode: str = "execution",
        extra_tools: list | None = None,
        context_window: int | None = None,
        settings: AppSettings | None = None,
        fallback_client: AsyncOpenAI | None = None,
        fallback_provider_name: str | None = None,
    ) -> None:
        self._id = session_id
        self._agent = agent
        self._client = client
        self._provider_name = provider_name
        self._semaphore = semaphore
        self._history: list[Message] = []
        self._status: Literal[
            "idle", "running", "stopped"
        ] = "idle"
        self._created_at: datetime = datetime.now(
            timezone.utc
        )
        self._mode: str = mode
        self._context_window: int | None = context_window
        self._extra_tools: list = extra_tools or []
        self.active_skills: list[str] = []
        self._internal_messages: list[str] = []
        # Init tool/skill filters from agent role
        self.allowed_tools: list[str] | None = (
            agent.allowed_tools
        )
        self.denied_tools: list[str] = list(
            agent.denied_tools
        )
        self._token_usage: dict = {
            "prompt": 0,
            "completion": 0,
            "total": 0,
        }
        self._turn: int = 0
        self._tracer: Tracer = Tracer()
        self._settings: AppSettings | None = settings
        self._fallback_client: AsyncOpenAI | None = (
            fallback_client
        )
        self._fallback_provider_name: str | None = (
            fallback_provider_name
        )
        self._tool_cache: dict = {}
        self._display_log: list[dict] = []
        self.require_confirmation: bool = False
        self._confirm_queue: (
            asyncio.Queue | None
        ) = None
        self._question_queue: (
            asyncio.Queue | None
        ) = None
        self._pending_events: list[str] = []

    # ── Identity ──────────────────────────────────────────────

    @property
    def id(self) -> str:
        """Unique session identifier."""
        return self._id

    @property
    def provider(self) -> str:
        """Active provider name."""
        return self._provider_name

    @property
    def model(self) -> str:
        """Active model identifier."""
        return self._agent.model

    @property
    def role(self) -> str:
        """Active agent role name."""
        return self._agent.role or self._agent.name

    @property
    def token_usage(self) -> dict:
        """Accumulated token counts for this session."""
        return dict(self._token_usage)

    @property
    def cost_estimate(self) -> float | None:
        """Estimated USD cost using provider price table.

        Returns None if pricing is not configured.
        """
        if self._settings is None:
            return None
        prov = self._settings.providers.get(
            self._provider_name
        )
        if prov is None:
            return None
        p = prov.cost_per_1k_prompt
        c = prov.cost_per_1k_completion
        if p is None and c is None:
            return None
        prompt_cost = (
            self._token_usage["prompt"] / 1000
        ) * (p or 0.0)
        compl_cost = (
            self._token_usage["completion"] / 1000
        ) * (c or 0.0)
        return prompt_cost + compl_cost

    @property
    def trace(self) -> list[TraceEntry]:
        """Structured execution log for this session."""
        return self._tracer.entries

    def export_trace(self, path: str) -> None:
        """Write trace as newline-delimited JSON."""
        self._tracer.export(path)

    @property
    def info(self) -> SessionInfo:
        """Serialisable snapshot of this session's state."""
        return SessionInfo(
            session_id=self._id,
            role=self._agent.name,
            provider=self._provider_name,
            created_at=self._created_at,
            message_count=len(self._history),
            status=self._status,
        )

    # ── Mode & tools ─────────────────────────────────────────

    @property
    def mode(self) -> str:
        """Active execution mode: plan|execution."""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("plan", "execution"):
            raise ValueError(
                f"Invalid mode '{value}'. "
                "Use 'plan' or 'execution'."
            )
        old = self._mode
        self._mode = value
        if old != value:
            self.log_event(
                "mode_change",
                old_mode=old,
                new_mode=value,
            )

    # ── Display log ───────────────────────────────────────

    def log_event(
        self, event_type: str, **kwargs
    ) -> None:
        """Append a state-change entry to the
        display log.

        This is the only authorised write path
        for _display_log.  The library calls it
        internally; external callers (e.g. the
        CLI) must use it for any custom entries.
        """
        self._display_log.append(
            {"type": event_type, **kwargs}
        )

    @property
    def display_log(self) -> list[dict]:
        """Read-only snapshot of the display log."""
        return list(self._display_log)

    @property
    def extra_tools(self) -> list:
        """Read-only list of extra tools."""
        return list(self._extra_tools)

    @property
    def context_window(self) -> int | None:
        """Model context window size in tokens."""
        return self._context_window

    def arm_confirm_queue(self) -> None:
        """Create a fresh confirm queue so the session
        will pause and wait for send_confirm() instead
        of auto-approving write-tool calls.

        Call this before starting a chat turn that
        requires confirmation prompts.
        """
        self._confirm_queue = asyncio.Queue()

    def send_confirm(self, result: bool) -> None:
        """Send an approval/rejection to the pending
        confirmation request.

        Safe to call when no confirmation is pending.
        """
        if self._confirm_queue is not None:
            try:
                self._confirm_queue.put_nowait(result)
            except Exception:
                pass

    def cancel_confirm(self) -> None:
        """Reject a pending confirmation (sends False).

        Safe to call when no confirmation is pending.
        """
        self.send_confirm(False)

    def answer_question(self, text: str) -> None:
        """Send an answer (or empty str to cancel) to
        a pending interactive question.

        Safe to call when no question is pending.
        """
        if self._question_queue is not None:
            try:
                self._question_queue.put_nowait(text)
            except Exception:
                pass

    def clear_interaction_queues(self) -> None:
        """Null out confirm/question queues after
        a task cancellation so stale state is gone.
        """
        self._confirm_queue = None
        self._question_queue = None

    # ── Tool schemas / executor ───────────────────────────

    def get_tool_schemas(self) -> list[dict]:
        """Return tool schemas filtered by permission lists."""
        from starry_lib.tools.skill_loader import load_skills
        from starry_lib.tools.tool_loader import (
            get_tool_schemas,
        )
        skill_names = {
            t.SCHEMA["function"]["name"]
            for t in load_skills()
        }
        schemas = get_tool_schemas(self._mode)
        for t in self._extra_tools:
            schemas.append(t.SCHEMA)
        return [
            s for s in self._filter_tools(schemas)
            if (
                s["function"]["name"] not in skill_names
                or self._skill_permitted(
                    s["function"]["name"]
                )
            )
        ]

    def get_tool_executor(
        self,
    ) -> dict[str, object]:
        """Return name→execute map filtered by permissions.

        Wraps the 'task' tool to propagate the current
        session mode to spawned subagents, preventing
        plan-mode sessions from escalating to bash/write
        through a child agent.
        """
        from starry_lib.tools.skill_loader import load_skills
        from starry_lib.tools.tool_loader import (
            get_tool_executor,
            wrap_with_cache,
        )
        skill_names = {
            t.SCHEMA["function"]["name"]
            for t in load_skills()
        }
        executor = get_tool_executor(self._mode)
        executor = wrap_with_cache(
            executor, self._tool_cache
        )
        for t in self._extra_tools:
            name = t.SCHEMA["function"]["name"]
            executor[name] = t.execute
        if "task" in executor:
            _task_fn = executor["task"]
            _mode = self._mode

            async def _task_with_mode(**kwargs):
                return await _task_fn(
                    mode=_mode, **kwargs
                )

            executor["task"] = _task_with_mode
        allowed = {
            name: fn
            for name, fn in executor.items()
            if self._tool_permitted(name)
            and (
                name not in skill_names
                or self._skill_permitted(name)
            )
        }
        return allowed

    def _filter_tools(
        self, schemas: list[dict]
    ) -> list[dict]:
        """Apply allowed_tools / denied_tools filter."""
        return [
            s for s in schemas
            if self._tool_permitted(
                s["function"]["name"]
            )
        ]

    def _tool_permitted(self, name: str) -> bool:
        """Return True if *name* passes permission lists."""
        if (
            self.allowed_tools is not None
            and name not in self.allowed_tools
        ):
            return False
        if name in self.denied_tools:
            return False
        return True

    def _skill_permitted(self, name: str) -> bool:
        """Return True if skill *name* is allowed."""
        if (
            self._agent.allowed_skills is not None
            and name not in self._agent.allowed_skills
        ):
            return False
        if name in self._agent.denied_skills:
            return False
        return True

    def _accumulate_usage(self, usage) -> None:
        """Add LLM response usage counts to session totals."""
        if usage is None:
            return
        self._token_usage["prompt"] += (
            getattr(usage, "prompt_tokens", 0) or 0
        )
        self._token_usage["completion"] += (
            getattr(usage, "completion_tokens", 0) or 0
        )
        self._token_usage["total"] += (
            getattr(usage, "total_tokens", 0) or 0
        )

    def _estimate_usage(
        self,
        messages: list[dict],
        response_text: str,
    ) -> None:
        """Fallback token estimation when the provider
        does not return usage data in the stream.
        Uses len(json_bytes)//4 as a rough approximation,
        the same heuristic used by window_manager.py.
        """
        prompt = len(json.dumps(messages)) // 4
        completion = len(response_text) // 4
        self._token_usage["prompt"] += prompt
        self._token_usage["completion"] += completion
        self._token_usage["total"] += prompt + completion

    # ── LLM helpers ───────────────────────────────────────────

    def _llm_kwargs(self) -> dict:
        """Build per-request LLM kwargs from role params."""
        kw: dict = {"model": self._agent.model}
        if self._agent.temperature is not None:
            kw["temperature"] = self._agent.temperature
        if self._agent.max_tokens is not None:
            kw["max_tokens"] = self._agent.max_tokens
        if self._agent.top_p is not None:
            kw["top_p"] = self._agent.top_p
        return kw

    # ── Internal helpers ──────────────────────────────────────

    def _history_to_dicts(self) -> list[dict]:
        """Serialise _history to API-ready dicts.

        Preserves metadata fields (tool_calls,
        tool_call_id) needed for tool-call turns.
        """
        result = []
        for m in self._history:
            d = {
                "role": m.role,
                "content": m.content,
            }
            if m.metadata:
                d.update(m.metadata)
            result.append(d)
        return result

    def _build_messages(
        self,
        user_input: str,
        history: list[dict] | None = None,
    ) -> list[dict]:
        """Build messages with skill and event injections.

        Order: primary system → skill system messages →
        pending event system message (if any) →
        history → current user turn.
        Pending events are cleared after injection.
        """
        msgs = self._agent.build_messages(
            user_input, history=history
        )
        if self._internal_messages:
            system = msgs[:1]
            rest = msgs[1:]
            skill_msgs = [
                {"role": "system", "content": c}
                for c in self._internal_messages
            ]
            msgs = system + skill_msgs + rest
        if self._pending_events:
            n_sys = 1 + len(
                self._internal_messages
            )
            event_content = "\n\n".join(
                self._pending_events
            )
            event_msg = {
                "role": "system",
                "content": event_content,
            }
            msgs = (
                msgs[:n_sys]
                + [event_msg]
                + msgs[n_sys:]
            )
            self._pending_events.clear()
        if self._context_window:
            from starry_lib.context.window_manager import (
                truncate_messages,
            )
            msgs = truncate_messages(
                msgs,
                self._context_window,
                self._agent.model,
            )
        if self._mode == "plan":
            from starry_lib.prompts.loader import (
                load_plan_prompt,
            )
            plan_text = load_plan_prompt()
            if plan_text:
                for i in reversed(range(len(msgs))):
                    if msgs[i]["role"] == "user":
                        msgs[i] = dict(msgs[i])
                        msgs[i]["content"] = (
                            msgs[i]["content"]
                            + "\n\n"
                            + plan_text
                        )
                        break
        elif self._mode == "deep":
            from starry_lib.prompts.loader import (
                load_deep_prompt,
            )
            deep_text = load_deep_prompt()
            if deep_text:
                for i in reversed(range(len(msgs))):
                    if msgs[i]["role"] == "user":
                        msgs[i] = dict(msgs[i])
                        msgs[i]["content"] = (
                            msgs[i]["content"]
                            + "\n\n"
                            + deep_text
                        )
                        break
        return msgs

    # ── Core I/O ──────────────────────────────────────────────

    async def chat(
        self, user_input: str
    ) -> AsyncIterator[AgentEvent]:
        """Stream a response, maintaining conversation history.

        Yields token events as they arrive, then a final done
        event carrying the full assembled response text.
        On error, yields a single error event and returns.
        """
        messages = self._build_messages(
            user_input,
            history=self._history_to_dicts(),
        )
        self._history.append(
            Message(role="user", content=user_input)
        )
        self.log_event(
            "user",
            content=user_input,
            mode=self._mode,
        )
        self._status = "running"
        self._turn += 1
        _chat_turn = self._turn
        _chat_t0 = time.monotonic()
        _chat_tok0 = self._token_usage["total"]
        tokens: list[str] = []

        _client = self._client
        _create_err: Exception | None = None
        stream = None
        try:
            async with self._semaphore:
                stream = await call_with_retry(
                    lambda: _client.chat.completions.create(
                        **self._llm_kwargs(),
                        messages=messages,
                        stream=True,
                        stream_options={
                            "include_usage": True
                        },
                    )
                )
        except Exception as exc:  # noqa: BLE001
            _create_err = exc

        if _create_err is not None:
            if self._fallback_client is not None:
                yield AgentEvent(
                    type="provider_fallback",
                    session_id=self._id,
                    data=str(_create_err),
                )
                _client = self._fallback_client
                try:
                    async with self._semaphore:
                        stream = await call_with_retry(
                            lambda: (
                                _client.chat.completions
                                .create(
                                    **self._llm_kwargs(),
                                    messages=messages,
                                    stream=True,
                                    stream_options={
                                        "include_usage": True
                                    },
                                )
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    self._status = "idle"
                    yield AgentEvent(
                        type="error",
                        session_id=self._id,
                        data=str(exc),
                    )
                    return
            else:
                self._status = "idle"
                self.log_event(
                    "error",
                    content=str(_create_err),
                )
                yield AgentEvent(
                    type="error",
                    session_id=self._id,
                    data=str(_create_err),
                )
                return

        try:
            async for chunk in stream:
                if not chunk.choices:
                    if chunk.usage:
                        self._accumulate_usage(
                            chunk.usage
                        )
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    tokens.append(delta.content)
                    yield AgentEvent(
                        type="token",
                        session_id=self._id,
                        data=delta.content,
                    )
                if chunk.usage:
                    self._accumulate_usage(chunk.usage)
        except Exception as exc:  # noqa: BLE001
            self._status = "idle"
            self.log_event(
                "error", content=str(exc)
            )
            yield AgentEvent(
                type="error",
                session_id=self._id,
                data=str(exc),
            )
            return

        response_text = "".join(tokens)
        if self._token_usage["total"] == _chat_tok0:
            self._estimate_usage(
                messages, response_text
            )
        self._tracer.record(TraceEntry(
            turn=_chat_turn,
            type="llm_call",
            latency_ms=int(
                (time.monotonic() - _chat_t0)
                * 1000
            ),
            tokens_used=(
                self._token_usage["total"]
                - _chat_tok0
            ),
        ))
        self._history.append(
            Message(role="assistant", content=response_text)
        )
        self.log_event(
            "assistant", content=response_text
        )
        self._status = "idle"
        yield AgentEvent(
            type="done",
            session_id=self._id,
            data=response_text,
        )

    async def chat_complete(self, user_input: str) -> str:
        """Return the full response as a single string.

        Convenience wrapper around chat() for callers that do
        not need token-by-token streaming.
        """
        result: list[str] = []
        async for event in self.chat(user_input):
            if event.type == "token":
                result.append(str(event.data))
        return "".join(result)

    async def chat_auto(
        self, user_input: str
    ) -> AsyncIterator[AgentEvent]:
        """Stream a response with mode-selected tools.

        Behaves like chat() when no tools are active.
        Uses chat_with_tools() otherwise, automatically
        injecting the schemas and executor for the
        current mode.
        """
        schemas = self.get_tool_schemas()
        if not schemas:
            async for event in self.chat(user_input):
                yield event
            return
        async for event in self.chat_with_tools(
            user_input,
            schemas,
            self.get_tool_executor(),
        ):
            yield event

    async def chat_with_tools(
        self,
        user_input: str,
        tools: list[dict[str, Any]],
        tool_executor: (
            dict[str, Callable[..., Any]]
            | Callable[[str, dict[str, Any]], Any]
        ),
    ) -> AsyncIterator[AgentEvent]:
        """Streaming turn with OpenAI-style tool support.

        Runs the full multi-round tool-call loop:
        1. Sends the message with tool schemas attached
           via a streaming call.
        2. If the model streams text tokens, yields them
           immediately so the TUI shows them in real time.
        3. If the model requests tool calls, executes them
           via *tool_executor* (yielding tool_call and
           tool_result events) then re-submits the full
           message history with tools attached and loops.
        4. Repeats until the model returns a final answer
           (finish_reason != "tool_calls").
        5. Updates conversation history on completion.

        Parameters
        ----------
        tools:
            List of tool schemas in OpenAI function format.

        tool_executor:
            Either a ``dict`` mapping function names to
            callables, or a single callable with signature
            ``(name: str, args: dict) -> Any``.
            Return value is JSON-serialised and sent back
            to the model as the tool result.
        """
        messages = self._build_messages(
            user_input,
            history=self._history_to_dicts(),
        )
        self.log_event(
            "user",
            content=user_input,
            mode=self._mode,
        )
        self._status = "running"
        self._turn += 1
        _WRITE_TOOLS: frozenset[str] = frozenset(
            {"bash", "edit", "write"}
        )

        async def _dispatch(
            name: str, args: dict
        ) -> str:
            if isinstance(tool_executor, dict):
                fn = tool_executor.get(name)
                if fn is None:
                    return json.dumps({
                        "error": (
                            f"unknown tool {name!r}"
                        )
                    })
                result = fn(**args)
            else:
                result = tool_executor(name, args)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, str):
                return result
            return json.dumps(result)

        final_tokens: list[str] = []
        tool_calls_made = False
        tool_exchange: list[Message] = []
        _client = self._client
        _cwt_tok0 = self._token_usage["total"]

        try:
            while True:
                _t0 = time.monotonic()
                _tok0 = self._token_usage["total"]
                async with self._semaphore:
                    stream = await call_with_retry(
                        lambda: (
                            _client.chat.completions
                            .create(
                                **self._llm_kwargs(),
                                messages=messages,
                                tools=tools,
                                tool_choice="auto",
                                stream=True,
                                stream_options={
                                    "include_usage":
                                    True,
                                },
                            )
                        )
                    )

                # Accumulate text and tool-call deltas
                # from the stream. Text tokens are yielded
                # immediately so the TUI can show them.
                text_chunks: list[str] = []
                # index → {id, name, arguments}
                acc_tc: dict[int, dict] = {}
                finish_reason: str | None = None
                asst_content = ""

                async for chunk in stream:
                    if not chunk.choices:
                        if chunk.usage:
                            self._accumulate_usage(
                                chunk.usage
                            )
                        continue
                    c = chunk.choices[0]
                    delta = c.delta
                    if c.finish_reason:
                        finish_reason = (
                            c.finish_reason
                        )
                    if delta.content:
                        asst_content += delta.content
                        text_chunks.append(
                            delta.content
                        )
                        yield AgentEvent(
                            type="token",
                            session_id=self._id,
                            data=delta.content,
                        )
                    if delta.tool_calls:
                        for tcd in delta.tool_calls:
                            idx = tcd.index
                            if idx not in acc_tc:
                                acc_tc[idx] = {
                                    "id": "",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tcd.id:
                                acc_tc[idx][
                                    "id"
                                ] += tcd.id
                            fn = tcd.function
                            if fn:
                                if fn.name:
                                    acc_tc[idx][
                                        "name"
                                    ] += fn.name
                                if fn.arguments:
                                    acc_tc[idx][
                                        "arguments"
                                    ] += fn.arguments
                    if chunk.usage:
                        self._accumulate_usage(
                            chunk.usage
                        )

                self._tracer.record(TraceEntry(
                    turn=self._turn,
                    type="llm_call",
                    latency_ms=int(
                        (time.monotonic() - _t0)
                        * 1000
                    ),
                    tokens_used=(
                        self._token_usage["total"]
                        - _tok0
                    ),
                ))

                if (
                    finish_reason != "tool_calls"
                    or not acc_tc
                ):
                    # Final text response — loop done.
                    final_tokens.append(
                        "".join(text_chunks)
                    )
                    break

                # ── Tool-call round ───────────────────
                tool_calls_made = True
                tc_list = [
                    acc_tc[i]
                    for i in sorted(acc_tc.keys())
                ]
                tc_dicts = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": (
                                tc["arguments"]
                            ),
                        },
                    }
                    for tc in tc_list
                ]
                messages.append({
                    "role": "assistant",
                    "content": asst_content,
                    "tool_calls": tc_dicts,
                })
                tool_exchange.append(Message(
                    role="assistant",
                    content=asst_content,
                    metadata={
                        "tool_calls": tc_dicts
                    },
                ))

                for tc in tc_list:
                    name = tc["name"]
                    args = json.loads(
                        tc["arguments"]
                    )
                    tc_id = tc["id"]

                    self.log_event(
                        "tool_call",
                        name=name,
                        args=args,
                    )
                    yield AgentEvent(
                        type="tool_call",
                        session_id=self._id,
                        data={
                            "id": tc_id,
                            "name": name,
                            "args": args,
                        },
                    )
                    self._tracer.record(TraceEntry(
                        turn=self._turn,
                        type="tool_call",
                        name=name,
                        args=args,
                    ))

                    if name == "question":
                        questions = args.get(
                            "questions", []
                        )
                        self._question_queue = (
                            asyncio.Queue()
                        )
                        yield AgentEvent(
                            type=(
                                "tool_question"
                                "_request"
                            ),
                            session_id=self._id,
                            data={
                                "id": tc_id,
                                "questions": (
                                    questions
                                ),
                            },
                        )
                        answer = (
                            await self
                            ._question_queue
                            .get()
                        )
                        self._question_queue = (
                            None
                        )
                        result_str = json.dumps({
                            "type": "answers",
                            "answers": (
                                answer
                                if isinstance(
                                    answer, list
                                )
                                else [answer]
                            ),
                        })
                    else:
                        need_confirm = (
                            name in _WRITE_TOOLS
                            or self.require_confirmation
                        )
                        if need_confirm:
                            yield AgentEvent(
                                type=(
                                    "tool_confirm"
                                    "_request"
                                ),
                                session_id=(
                                    self._id
                                ),
                                data={
                                    "id": tc_id,
                                    "name": name,
                                    "args": args,
                                },
                            )
                            approved = True
                            if (
                                self._confirm_queue
                                is not None
                            ):
                                approved = (
                                    await self
                                    ._confirm_queue
                                    .get()
                                )
                        else:
                            approved = True

                        if approved:
                            result_str = (
                                await _dispatch(
                                    name, args
                                )
                            )
                        else:
                            result_str = (
                                json.dumps({
                                    "error": (
                                        "denied"
                                        " by user"
                                    )
                                })
                            )

                    self.log_event(
                        "tool_result",
                        name=name,
                        result=result_str,
                    )
                    yield AgentEvent(
                        type="tool_result",
                        session_id=self._id,
                        data={
                            "id": tc_id,
                            "name": name,
                            "result": result_str,
                        },
                    )
                    self._tracer.record(TraceEntry(
                        turn=self._turn,
                        type="tool_result",
                        name=name,
                        result_preview=(
                            result_str[:120] + "…"
                            if len(result_str) > 120
                            else result_str
                        ),
                    ))

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result_str,
                    })
                    tool_exchange.append(Message(
                        role="tool",
                        content=result_str,
                        metadata={
                            "tool_call_id": tc_id
                        },
                    ))
                # End tool-call round; loop to re-submit

        except Exception as exc:  # noqa: BLE001
            self._status = "idle"
            self._question_queue = None
            yield AgentEvent(
                type="error",
                session_id=self._id,
                data=str(exc),
            )
            return

        final = "".join(final_tokens)
        if self._token_usage["total"] == _cwt_tok0:
            self._estimate_usage(messages, final)
        self._history.append(
            Message(role="user", content=user_input)
        )
        self._history.extend(tool_exchange)
        self._history.append(
            Message(role="assistant", content=final)
        )
        self.log_event("assistant", content=final)
        self._status = "idle"
        yield AgentEvent(
            type="done",
            session_id=self._id,
            data=final,
        )

    async def chat_structured(
        self,
        prompt: str,
        schema,
    ):
        """Call LLM and return a validated Pydantic model.

        Sends the prompt with a JSON-mode hint and parses
        the response into *schema* (a BaseModel subclass).
        Retries up to 2 times on validation failure,
        feeding the error back to the model each time.
        Falls back to prompt-engineering if the provider
        does not support response_format=json_object.
        """
        from pydantic import ValidationError

        import json as _json

        schema_str = _json.dumps(
            schema.model_json_schema(), indent=2
        )
        sys_msg = (
            "Respond only with valid JSON matching "
            f"this schema:\n{schema_str}"
        )
        messages: list[dict] = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt},
        ]
        kw = {**self._llm_kwargs(), "messages": messages}

        try:
            kw["response_format"] = {
                "type": "json_object"
            }
            response = await call_with_retry(
                lambda: self._client.chat.completions.create(
                    **kw
                )
            )
        except Exception:
            kw.pop("response_format", None)
            response = await call_with_retry(
                lambda: self._client.chat.completions.create(
                    **kw
                )
            )

        if response.usage:
            self._accumulate_usage(response.usage)

        content = (
            response.choices[0].message.content or ""
        )
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                last_exc = exc
                if attempt < 2:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": content,
                        }
                    )
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Invalid JSON: {exc}. "
                            "Try again."
                        ),
                    })
                    kw["messages"] = messages
                    response = await call_with_retry(
                        lambda: (
                            self._client.chat.completions
                            .create(**kw)
                        )
                    )
                    if response.usage:
                        self._accumulate_usage(
                            response.usage
                        )
                    content = (
                        response.choices[0].message.content
                        or ""
                    )
        raise last_exc  # type: ignore[misc]

    # ── History ───────────────────────────────────────────────

    def get_history(self) -> list[Message]:
        """Return a copy of the conversation history."""
        return list(self._history)

    def clear_history(self) -> None:
        """Reset conversation history."""
        self._history = []

    def inject_system_message(
        self, content: str
    ) -> None:
        """Append a system message to history.

        Does not trigger a new LLM turn. Used to
        inform the LLM of out-of-band state changes
        (e.g. an agent was terminated).
        """
        self._history.append(
            Message(role="system", content=content)
        )

    def rewind(self) -> int:
        """Remove the last exchange from history.

        If the last message is from the assistant,
        removes both it and the preceding user message
        (one complete turn).  If the last message is
        a user message only (response never recorded,
        e.g. after a cancellation), removes just that
        message.
        Returns the number of messages removed.
        """
        if not self._history:
            return 0
        removed = 0
        if self._history[-1].role == "assistant":
            self._history.pop()
            removed += 1
        if self._history and (
            self._history[-1].role == "user"
        ):
            self._history.pop()
            removed += 1
        return removed

    def reset_tokens(self) -> None:
        """Zero out accumulated token counters."""
        self._token_usage = {
            "prompt": 0,
            "completion": 0,
            "total": 0,
        }

    def new_session(self) -> str:
        """Reset conversation state and issue a
        new session ID.

        Clears history, zeroes token counters,
        resets turn count, and returns the new ID.
        The LLM client and agent config are kept.
        """
        import uuid
        self.clear_history()
        self.reset_tokens()
        self._turn = 0
        self._tool_cache = {}
        self._display_log = []
        self._id = (
            "session-"
            + uuid.uuid4().hex[:8]
        )
        return self._id

    def get_context_snapshot(self) -> dict:
        """Read-only snapshot of the current LLM context.

        Returns session metadata and the message list as
        it would be sent on the next turn (system prompt,
        world state, active skill injections, history).
        Does not add a user turn or mutate any state.
        """
        from starry_lib.context.world_state import (
            build_world_state,
        )
        msgs: list[dict] = [
            {
                "role": "system",
                "label": "system",
                "content": (
                    self._agent
                    .effective_system_prompt()
                ),
            },
            {
                "role": "system",
                "label": "world state",
                "content": build_world_state(),
            },
        ]
        for i, content in enumerate(
            self._internal_messages
        ):
            skill = (
                self.active_skills[i]
                if i < len(self.active_skills)
                else f"skill_{i}"
            )
            msgs.append({
                "role": "system",
                "label": f"skill: {skill}",
                "content": content,
            })
        for m in self._history:
            entry: dict = {
                "role": m.role,
                "label": m.role,
                "content": m.content,
            }
            if m.metadata:
                entry["metadata"] = dict(
                    m.metadata
                )
            msgs.append(entry)
        return {
            "session_id": self._id,
            "role": self._agent.name,
            "provider": self._provider_name,
            "model": self._agent.model,
            "mode": self._mode,
            "token_usage": dict(self._token_usage),
            "context_window": self._context_window,
            "messages": msgs,
        }

    # ── Runtime switches ──────────────────────────────────────

    def switch_role(
        self, role: str, settings: AppSettings
    ) -> None:
        """Rebuild the agent with a different role.

        Conversation history is preserved.
        Logs a role_change entry to the display log.
        """
        if role not in settings.agents:
            raise KeyError(f"Role '{role}' not found.")
        from starry_lib.agents.roles import build_agent

        old_role = self._agent.name
        role_cfg = settings.agents[role]
        provider_cfg = settings.providers[
            self._provider_name
        ]
        self._agent = build_agent(role_cfg, provider_cfg)
        # Re-apply tool/skill filters from the new role
        self.allowed_tools = self._agent.allowed_tools
        self.denied_tools = list(self._agent.denied_tools)
        if old_role != role:
            self.log_event(
                "role_change",
                old_role=old_role,
                new_role=role,
            )

    def switch_provider(
        self,
        provider: str | ProviderConfig,
        settings: AppSettings,
    ) -> None:
        """Rebuild the client with a different provider.

        Accepts either a provider name (looked up in settings)
        or a ProviderConfig object (e.g. from make_provider()).
        The agent's model is updated to the new provider's
        default unless the role has a model_override.
        Conversation history is preserved.
        Logs a provider_change entry to the display log.
        """
        from starry_lib.agents.roles import build_agent
        from starry_lib.llm.client import build_client

        old_name = self._provider_name
        if isinstance(provider, ProviderConfig):
            provider_cfg = provider
        else:
            if provider not in settings.providers:
                raise KeyError(
                    f"Provider '{provider}' not found."
                )
            provider_cfg = settings.providers[provider]

        self._client = build_client(provider_cfg)
        self._provider_name = provider_cfg.name
        role_cfg = settings.agents[self._agent.name]
        self._agent = build_agent(role_cfg, provider_cfg)
        self._context_window = provider_cfg.context_window
        if old_name != self._provider_name:
            self.log_event(
                "provider_change",
                old_provider=old_name,
                new_provider=self._provider_name,
            )

    def set_model(self, model_id: str) -> None:
        """Override the model for this session.

        Takes effect on the next LLM call.
        Does not switch provider or rebuild the
        agent.  Logs a model_change entry.
        """
        old = self._agent.model
        self._agent.model = model_id
        if old != model_id:
            self.log_event(
                "model_change",
                old_model=old,
                new_model=model_id,
            )

    def restore_from(
        self,
        saved: dict,
        settings: AppSettings,
    ) -> dict:
        """Restore session state from a saved dict.

        Restores history, mode, provider, model,
        role, and display_log.  All switching is
        done directly (no intermediate log events)
        so the saved display_log is the final
        authoritative log after this call.

        Returns:
            dict with keys: mode, provider, model,
            role, warnings (list[str]).
        """
        from starry_lib.agents.roles import (
            build_agent,
        )
        from starry_lib.llm.client import build_client
        from starry_lib.types import Message

        warnings: list[str] = []

        # ── History ───────────────────────────
        self._history.clear()
        for m in saved.get("history", []):
            meta: dict = {}
            if "tool_calls" in m:
                meta["tool_calls"] = (
                    m["tool_calls"]
                )
            if "tool_call_id" in m:
                meta["tool_call_id"] = (
                    m["tool_call_id"]
                )
            self._history.append(Message(
                role=m["role"],
                content=m["content"],
                metadata=meta,
            ))

        # ── Provider ──────────────────────────
        sv_prov = saved.get("provider", "")
        if sv_prov and sv_prov != self._provider_name:
            if sv_prov in settings.providers:
                pcfg = settings.providers[sv_prov]
                self._client = build_client(pcfg)
                self._provider_name = sv_prov
                rname = self._agent.name
                if rname in settings.agents:
                    rcfg = settings.agents[rname]
                    self._agent = build_agent(
                        rcfg, pcfg
                    )
            else:
                warnings.append(
                    f"Provider '{sv_prov}'"
                    f" not found; using"
                    f" '{self._provider_name}'"
                )

        # ── Role ──────────────────────────────
        sv_role = saved.get("role", "")
        if (
            sv_role
            and sv_role != self._agent.name
        ):
            if sv_role in settings.agents:
                pcfg = settings.providers.get(
                    self._provider_name
                )
                if pcfg:
                    rcfg = settings.agents[sv_role]
                    self._agent = build_agent(
                        rcfg, pcfg
                    )
                    self.allowed_tools = (
                        self._agent.allowed_tools
                    )
                    self.denied_tools = list(
                        self._agent.denied_tools
                    )
            else:
                warnings.append(
                    f"Role '{sv_role}' not found;"
                    f" using '{self._agent.name}'"
                )

        # ── Model (set last — provider/role ───
        # ── rebuilds may reset it)         ───
        sv_model = saved.get("model", "")
        if sv_model:
            self._agent.model = sv_model

        # ── Mode ──────────────────────────────
        sv_mode = saved.get("mode", "execution")
        if sv_mode not in ("plan", "execution"):
            sv_mode = "execution"
        self._mode = sv_mode

        # ── Display log (authoritative) ───────
        self._display_log = list(
            saved.get("display_log", [])
        )

        return {
            "mode": self._mode,
            "provider": self._provider_name,
            "model": self._agent.model,
            "role": self._agent.name,
            "warnings": warnings,
        }

    # ── Skills ────────────────────────────────────────────────

    def add_skill(self, name: str) -> None:
        """Load a skill and inject it as a system message.

        The skill content is added to active_skills and
        prepended to subsequent LLM calls as an extra
        system message block.
        """
        from starry_lib.skills.loader import load_skill
        content = load_skill(name)
        if name not in self.active_skills:
            self.active_skills.append(name)
            self._internal_messages.append(content)

    def remove_skill(self, name: str) -> None:
        """Remove a skill from the active list.

        Does not raise if the skill is not loaded.
        """
        if name in self.active_skills:
            idx = self.active_skills.index(name)
            self.active_skills.pop(idx)
            self._internal_messages.pop(idx)

    # ── Events ────────────────────────────────────────────────

    def fire_event(
        self, name: str, **kwargs: str
    ) -> None:
        """Inject a rendered event message into history.

        Renders the named event template, then appends
        the result as a role="user" Message marked
        as internal (not shown in TUI chat history).
        Silently does nothing if the event file is absent.
        """
        from starry_lib.events.loader import load_event
        text = load_event(name, **kwargs)
        if text is None:
            return
        self._pending_events.append(text)
