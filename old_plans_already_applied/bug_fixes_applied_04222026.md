# bug_fixes_applied_04222026.md
# Date: 04/22/2026
# Engineer: ahernandez86

Applied from pending_issues.md. All items below were
implemented, tested at the unit level, and removed from
the pending list.

---

## #2 — Token and cost tracking

### Files changed
- `davyagent/config/settings.py` — added
  `cost_per_1k_prompt: float | None` and
  `cost_per_1k_completion: float | None` to `ProviderConfig`.
- `davyagent/agents/session.py` — added `_token_usage` dict,
  `_accumulate_usage()` private helper, `token_usage` property,
  `cost_estimate` property. All LLM calls now capture
  `response.usage` and accumulate totals. Streaming calls use
  `stream_options={"include_usage": True}` to receive usage in
  the final chunk.

---

## #3 — Retry and fallback providers

### Files changed
- `davyagent/config/settings.py` — added
  `fallback: str | None` to `ProviderConfig`.
- `davyagent/llm/client.py` — new `call_with_retry(factory)`
  async function: 3 attempts, delays 1s/2s/4s, retries on
  `RateLimitError` (429) and `APIStatusError` (5xx only).
- `davyagent/agents/session.py` — `__init__` accepts optional
  `fallback_client` and `fallback_provider_name`. Both `chat()`
  and `chat_with_tools()` wrap all
  `client.chat.completions.create()` calls with
  `call_with_retry`. On exhausted retries in `chat()`, if a
  fallback client is set the session emits a
  `"provider_fallback"` `AgentEvent` and retries with the
  fallback. `chat_with_tools()` retries only (no mid-
  conversation provider switch).
- `davyagent/types.py` — added `"provider_fallback"` to the
  `AgentEvent.type` Literal.

---

## #4 — Structured output / response validation

### Files changed
- `davyagent/agents/session.py` — new `chat_structured(prompt,
  schema)` async method. Calls the LLM with
  `response_format={"type": "json_object"}`, falling back to
  prompt-engineering if the provider rejects the parameter.
  Parses the response with `schema.model_validate_json()` and
  retries up to 2 times on `ValidationError`, feeding the
  error message back each time. Returns a validated Pydantic
  model instance.

---

## #6 — Tool result caching

### Files changed
- `davyagent/tools/tool_loader.py` — added `_READ_ONLY`
  frozenset (`read`, `glob`, `grep`, `webfetch`, `websearch`),
  `_WRITE` frozenset (`bash`, `edit`, `write`), and
  `wrap_with_cache(executor, cache)` public function. Read-only
  tools are wrapped with an in-memory LRU-style dict cache
  keyed by `(tool_name, json_kwargs)`. Write tools are wrapped
  to call `cache.clear()` before execution. Async tools bypass
  caching.
- `davyagent/agents/session.py` — added `_tool_cache: dict`
  to `__init__`. `get_tool_executor()` now calls
  `wrap_with_cache(executor, self._tool_cache)` so the cache
  is session-scoped and cleared on every write-tool call.

---

## #9 — Websearch tool

### Files changed
- `davyagent/tools/implementations/websearch.py` — new tool.
  Supports three backends: DuckDuckGo (zero-config, via
  `duckduckgo-search`), Tavily (requires `TAVILY_API_KEY`),
  and Exa (requires `EXA_API_KEY`). In `auto` mode tries
  Tavily → Exa → DuckDuckGo, skipping backends with no key
  set. Returns `{results, count, backend}` with an optional
  `warnings` list if backends were tried and failed.
- `davyagent/tools/tool_loader.py` — `websearch` added to
  `_STATIC_PLAN`; available in both plan and execution modes.
  Also added to `_READ_ONLY` for session-scoped caching.
- `davyagent/tools/TOOLS.md` — websearch row added to the
  mode matrix (✓ in both columns).
- `davyagent/config/settings.py` — `AppSettings` gains
  `websearch_backend: str = "auto"` and
  `websearch_max_results: int = 5`.
- `pyproject.toml` — added `[project.optional-dependencies]`
  group `search` with `duckduckgo-search>=6`, `tavily-python`,
  and `exa-py`. Install with `pip install davyagent[search]`.
