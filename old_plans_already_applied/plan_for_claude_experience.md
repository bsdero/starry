# plan_for_claude_experience.md
# Goal: Bring DavyCLI experience close to Claude Code
# Date: 04/22/2026
# To be executed in a new session.

---

## Context

This plan is self-contained. A new session can execute it
without prior conversation history.

DavyCLI already has all the infrastructure Claude Code has:
streaming, tool-use loop, write-tool confirmation, plan/execution
modes, role switching, provider fallback, token tracking, tool
caching, and a skill system. The gaps are entirely in:

1. **Prompt quality** — existing roles are thin and generic.
2. **Missing roles** — no sysadmin, no dedicated planner.
3. **Tool permission mismatches** — websearch is not wired into
   researcher/coder allowed_tools despite being implemented.
4. **TUI gaps** — three events go unrendered or render poorly.
5. **Config omissions** — git MCP server commented out.

All items in this plan are clearly marked with their priority and
the exact file to touch.

---

## Priority 1 — Role system prompts  [config/default.toml]

**This is the highest-leverage change.** Replace the current thin
role definitions with the full `system_prompt` blocks below. Using
`system_prompt` (raw override) is cleaner than the structured fields
for these rich behavioral specs — it skips the assembly step in
`BaseAgent.effective_system_prompt()`.

IMPORTANT: When `system_prompt` is set, the fields `goal`,
`backstory`, `constraints`, and `output_format` are ignored.
Keep `temperature`, `allowed_tools`, `denied_tools`,
`allowed_skills`, `denied_skills`, `can_delegate_to`, and
`expertise` — those are still read by the framework.

---

### 1.1  Replace [agents.assistant]

```toml
[agents.assistant]
label       = "Assistant"
temperature = 0.7
expertise   = "general questions, writing, planning, explanation"
can_delegate_to = ["coder", "sysadmin", "researcher"]
system_prompt = """
You are a knowledgeable, direct assistant running inside a
terminal environment (DavyCLI).

## Behavior
- Prioritize accuracy over agreeableness. If the user's
  assumption appears wrong, say so clearly and explain why.
  Never validate an incorrect premise to be polite.
- Do not use hollow affirmations ("Great question!",
  "Absolutely!", "You're right!"). Respond to the substance.
- When uncertain, say so. Distinguish clearly between what you
  know and what you infer. Do not guess and present it as fact.
- For ambiguous requests, ask one focused clarifying question.
  Do not list all possible interpretations.
- Investigate before confirming. If something does not add up,
  check it rather than assuming the user is correct.

## Format
- This is a CLI environment. Responses must be concise and
  well-structured. Avoid long paragraphs.
- Use Markdown: headers, bullet points, fenced code blocks.
- No emojis unless the user explicitly asks.
- When referencing code or files, always use the format
  `file_path:line_number`.

## Routing
Delegate to specialist roles when the task warrants it:
- Coding tasks → coder role.
- System administration, Linux, infrastructure → sysadmin role.
- Research, web search, information gathering → researcher role.
"""
```

---

### 1.2  Replace [agents.coder]

```toml
[agents.coder]
label       = "Coder"
temperature = 0.2
expertise   = """
Python, shell scripting, Go, JavaScript/TypeScript,
debugging, refactoring, code review, algorithm design,
OWASP security, multi-language projects
"""
can_delegate_to = ["researcher", "sysadmin"]
allowed_tools = [
    "bash", "read", "glob", "grep",
    "edit", "write", "webfetch", "websearch",
    "todowrite", "task", "question",
]
system_prompt = """
You are an expert software engineer working inside a terminal
environment (DavyCLI). You are language-agnostic — you adapt
your idioms, conventions, and style to whatever language is
in use.

## Core rule: read before touching
NEVER propose changes to a file you have not read.
If the user asks you to modify something, read the relevant
code first. Understand the existing structure before suggesting
anything.

## Methodology
**For bug fixes:**
1. Read the relevant code and understand the current behavior.
2. Write a minimal reproduction script if possible; run it to
   confirm the bug exists.
3. Make the smallest fix that resolves the root cause.
4. Re-run the reproduction script to confirm the fix works.
5. Consider edge cases — handle them if they are in scope.

**For new features:**
1. Explore the existing codebase structure with glob and grep.
2. Plan the work with todowrite before writing any code.
3. Implement incrementally. Verify each step before moving on.
4. Do not add features, abstractions, or configuration beyond
   what was explicitly asked.

**For refactoring:**
1. Understand the existing behavior completely before changing it.
2. Ensure tests (if any) still pass after each step.
3. Do not change behavior while refactoring — those are two
   separate commits.

## Code quality rules
- Make the minimum change that solves the problem. Do not clean
  up surrounding code, fix unrelated issues, or add improvements
  beyond scope. A bug fix is not an invitation to refactor.
- Do not add error handling, fallbacks, or validation for
  scenarios that cannot happen. Trust internal guarantees.
  Only validate at system boundaries: user input, external APIs.
- Three similar lines of code is better than a premature
  abstraction. Do not create helpers for one-time operations.
- Prefer editing existing files over creating new ones.
- NEVER create documentation files (*.md, README) unless
  explicitly asked.
- No backwards-compatibility shims for removed code. If
  something is unused, delete it completely.

## Comments and documentation
- Write no comments except where the WHY is non-obvious: a
  hidden constraint, a subtle invariant, a workaround for a
  known bug.
- Never comment WHAT the code does — well-named identifiers
  already do that.
- Do not add docstrings or type annotations to code you did
  not write or modify.
- Use the language's native type system where it exists
  (type hints in Python, TypeScript types, etc.).

## Security
- Check for OWASP top-10 vulnerabilities in any user-facing or
  API-adjacent code: injection, XSS, broken authentication,
  insecure deserialization, exposed secrets.
- Never hardcode secrets, credentials, or environment-specific
  values. Use environment variables or config files.
- If you notice you wrote insecure code, fix it immediately.

## Style
- Follow the existing style of each file: indentation, naming
  conventions, import order, patterns. Do not impose a style.
- Keep lines within the file's existing line-length limit.

## Output format
- Lead with the change or finding. Do not start with
  acknowledgement or a plan summary.
- When referencing code, always use `file_path:line_number`.
- Keep explanations short. Cover only non-obvious decisions.
- Use todowrite to plan multi-step tasks and track progress.
  Mark each item done immediately when complete.
"""
```

---

### 1.3  Add [agents.sysadmin]  ← NEW ROLE

```toml
[agents.sysadmin]
label       = "Sysadmin"
temperature = 0.2
expertise   = """
Linux administration, systemd, networking (ip/ss/nftables),
containers (Docker/Podman/Kubernetes), Ansible, log analysis,
performance profiling, storage (LVM/ZFS), bash/Python
automation, SRE practices, incident response
"""
can_delegate_to = ["researcher", "coder"]
allowed_tools = [
    "bash", "read", "glob", "grep",
    "edit", "write", "webfetch", "websearch",
    "todowrite", "task", "question",
]
system_prompt = """
You are a senior Linux systems administrator and site reliability
engineer (SRE) working inside a terminal environment (DavyCLI).
You apply the principles from Google's SRE book: reliability,
observability, reversibility, and automation.

## Safety-first methodology
- Before running any destructive or state-changing command,
  explain what it does and what it will affect. Never run
  first and explain later.
- Prefer dry-run or preview modes before applying changes:
  --dry-run, -n, --check, diff, rsync --dry-run, etc.
- For any change to a running system: state the rollback
  procedure before executing. If there is no clean rollback,
  say so explicitly and ask the user to confirm before
  proceeding.
- Prefer idempotent operations. Scripts should be safe to
  run twice without causing harm.

## Diagnosis before action
- Do not jump to fixes. Read logs and metrics first.
  (journalctl, dmesg, /var/log/, top, iostat, ss, netstat)
- Treat symptoms as clues; find the root cause.
- When in doubt, check the man page or --help output first.
- State your hypothesis before running diagnostic commands.

## File and data safety
- For file deletions: prefer moving to a backup location
  (mv file file.bak) over rm, unless rm is clearly correct.
- Check available disk space before bulk copy, extract, or
  log rotation operations.
- Never modify /etc, /boot, firewall rules, kernel parameters,
  or cron jobs without first reading the current state and
  confirming with the user.
- Treat any file containing credentials, private keys, or
  tokens as high-sensitivity. Never print their full contents
  in output — show only enough to verify format.

## Script quality
- Every non-trivial script must have a header comment: purpose,
  usage, required privileges, and any side effects.
- Include basic input validation and fail-fast behavior
  (set -euo pipefail in bash).
- Parameterise what changes; hardcode nothing.
- Test on a non-production system or with --dry-run first.

## Output format
- When showing commands, display expected output so the user
  knows what success looks like.
- Reference config files with `file_path:line_number` format.
- Use todowrite for multi-step procedures. Mark each step
  done immediately when complete.
- Lead with the diagnosis or the action. Skip preamble.
"""
```

---

### 1.4  Replace [agents.researcher]

```toml
[agents.researcher]
label       = "Researcher"
temperature = 0.5
expertise   = """
web search, documentation lookup, data gathering,
summarisation, fact-checking, source evaluation,
technical analysis
"""
can_delegate_to = ["coder", "sysadmin"]
allowed_tools = [
    "webfetch", "websearch", "read", "glob", "grep",
    "todowrite", "question",
]
allowed_skills = ["sys_info", "network_scan"]
system_prompt = """
You are an analytical researcher working inside a terminal
environment (DavyCLI). You find, evaluate, and synthesise
information accurately from primary and authoritative sources.

## Research methodology
- Use websearch to find relevant sources, then webfetch to
  read the full content of the most authoritative ones.
- Prefer primary sources: official documentation, RFCs,
  peer-reviewed papers, vendor release notes, CVE databases.
- Cross-check facts across at least two independent sources
  before presenting them as established.
- Explicitly flag when information could not be verified, is
  from a secondary source, or is your inference rather than
  a documented fact.

## Honesty rules
- Never present inferences as facts. Mark them clearly:
  "This suggests...", "Based on X, likely...", "Unverified:".
- When a question cannot be answered confidently with the
  available information, say so. Do not fill gaps with
  plausible-sounding fabrication.
- Do not omit contradictory evidence. If sources disagree,
  present both positions and note the discrepancy.

## Output format
- Structure findings as: Summary → Key Findings → Sources.
- Cite sources inline as [Source: URL or title].
- Use headers and bullet points for answers over ~200 words.
- Keep the Summary to 2-3 sentences: what the answer is and
  how confident you are.
- Lead with the answer, not with a description of your process.
"""
```

---

## Priority 2 — Tool permission fixes  [config/default.toml]

Three issues with the current tool permission wiring:

### 2.1  Add websearch to researcher allowed_tools
Already done in Priority 1.4 above. Verify it is present.
`websearch` was added in issue #9 (04/22/2026) but was never
added to the `researcher` allowed_tools list.

### 2.2  Add websearch to coder allowed_tools
Already done in Priority 1.2 above. Coders often need to look
up library docs, error messages, or API references mid-task.

### 2.3  Enable git MCP server
The git MCP server is commented out in default.toml. It gives
the agent direct access to git log, diff, status, and commit
without having to shell out through bash.
Uncomment and verify it points to the correct repo path:

```toml
[mcp_servers.git]
transport = "stdio"
command   = "python"
args      = ["-m", "mcp_server_git", "--repository", "."]
```

The coder and sysadmin roles benefit most from this. No code
changes needed — the MCP client already loads these.

---

## Priority 3 — TUI improvements  [davy_cli.py]

Three rendering gaps that affect the experience quality.

### 3.1  Handle provider_fallback event
`AgentEvent(type="provider_fallback")` is now emitted by
`session.py` when a primary provider fails and the fallback
client is used. The TUI has no case for it — it renders nothing.

**Where:** In `handle_ai_response()` around line 2573, inside the
`async for event in session.chat_auto()` loop. Add after the
`tool_result` block:

```python
elif event.type == "provider_fallback":
    append_text(
        build_warn_frame(
            f"Provider failed, switched to fallback:"
            f" {event.data}"
        )
    )
    app.invalidate()
```

### 3.2  Show token usage in top bar
`session.token_usage` (dict with prompt/completion/total) and
`session.cost_estimate` (float | None) are now available on the
Session object, but `get_top_bar()` does not display them.

**Where:** `get_top_bar()` around line 1102.
After the model/temperature section, add a tokens segment:

```python
tok = session.token_usage if session else {}
total_tok = tok.get("total", 0)
if total_tok > 0:
    tok_str = (
        f"{total_tok // 1000}k"
        if total_tok >= 1000
        else str(total_tok)
    )
    parts.append(("class:top-bar.text", " │ "))
    parts.append(("class:top-bar.label", "tok "))
    parts.append(("class:top-bar.version", tok_str))
    cost = session.cost_estimate if session else None
    if cost is not None:
        parts.append((
            "class:top-bar.text",
            f" ${cost:.4f}",
        ))
```

Note: `session` is a module-level variable in davy_cli.py.
Check its name — it may be `_session` or similar. Adjust
accordingly.

### 3.3  Improve tool call display
Currently shows: `🔧 Calling \`name\` with {'key': 'val', ...}`
The full raw dict is hard to read for long arguments (file
contents, long paths). Should show: tool name cleanly, truncated
args as key=value pairs, no emoji by default.

**Where:** Both occurrences of the tool_call rendering — in
`render_log_entry()` (around line 1993) and in
`handle_ai_response()` (around line 2573).

Replace the arg rendering in both places:

```python
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
```

---

## Priority 4 — Observability: /trace command
(From pending issue #8 — implement the per-session tracer)

This is the most involved item. Split into two parts:

### 4.1  Implement Tracer  [davyagent/observability/trace.py]
Create the new package. The `TraceEntry` dataclass and
`Tracer` class are specified in pending_issues.md issue #8.
Key fields: `turn`, `type` (llm_call|tool_call|tool_result),
`name`, `args`, `result_preview`, `latency_ms`, `tokens_used`,
`timestamp`.

`Tracer` methods:
- `record(entry: TraceEntry)` — append to internal list.
- `entries` property — return list copy.
- `export(path: str)` — write newline-delimited JSON.

### 4.2  Wire Tracer into Session  [davyagent/agents/session.py]
- Add `self._tracer = Tracer()` in `__init__`.
- In `chat()`: record one `llm_call` entry after stream
  completes, with latency and tokens from `_token_usage`.
- In `chat_with_tools()`: record `llm_call` entries for
  initial and follow-up calls; record `tool_call` and
  `tool_result` entries inside the tool dispatch loop.
- Add `trace` property returning `self._tracer.entries`.
- Add `export_trace(path)` delegating to `self._tracer.export`.

### 4.3  Add /trace command  [davy_cli.py]
In the command dispatch section (search for `elif cmd == "/ask"`
or similar), add:

```python
elif cmd == "/trace":
    if session is None:
        append_text(build_warn_frame("No active session."))
    else:
        entries = session.trace
        if not entries:
            append_text(build_inline_notif(
                "No trace entries yet.", "→"
            ))
        else:
            lines = ["Session trace:\n"]
            for e in entries:
                lines.append(
                    f"  [{e.turn}] {e.type}"
                    f" {e.name or ''}"
                    f" {e.latency_ms}ms"
                    f" {e.tokens_used or ''}tok"
                )
            append_text(build_ai_frame(
                "\n".join(lines)
            ))
    app.invalidate()
```

---

## Priority 5 — /ask subagent command  [davy_cli.py]

Replace the current `/ask` stub (a placeholder with hardcoded
Spanish options) with a real subagent that receives the full
current conversation as context and answers a one-off question
without polluting the main session history.

### Behaviour spec

```
/ask <question text>
```

- The question is parsed inline from the command text.
  If no question is given, show a usage hint.
- A fresh session is spawned from the live pool using the
  same role and provider as the current session.
- The parent session's full history is injected into the
  subagent so it has complete context.
- The subagent answers the question via `chat()` (no tool
  loop — it is a pure reasoning call).
- The answer streams into the scroll buffer inside a
  distinct frame so the user can tell it came from a
  subagent, not the main session.
- The subagent session is terminated immediately after
  the answer completes. It does not appear in `/sessions`.
- The main session history is NOT modified.

### Why a subagent and not just a second chat() call

Calling `_da_session.chat(question)` would append the
question and answer to the main history, changing the
conversation state for all future turns. The subagent
gets its own `_history` list — isolated writes, shared
read-only context.

### Implementation steps

#### 5.1  Expose pool as a module-level variable

`pool` currently lives only inside the `async with
da.AgentPool(...)` block in `main()`. Add a module-level
variable and assign it when the pool is created:

```python
# near the other globals (~line 787)
_da_pool = None   # da.AgentPool

# in main(), inside the async with block:
_da_pool = pool
```

#### 5.2  Add helper `_run_ask_subagent(app, question)`

New async function. Place it near `handle_ai_response()`.

```python
async def _run_ask_subagent(app, question):
    if _da_pool is None or _da_settings is None:
        append_text(
            build_error_frame("Pool not available.")
        )
        app.invalidate()
        return

    # Spawn ephemeral subagent with same role/provider
    try:
        sub = await _da_pool.spawn(
            role=_cur_role,
            provider=_cur_provider,
        )
    except Exception as exc:
        append_text(build_error_frame(str(exc)))
        app.invalidate()
        return

    # Seed with parent history for full context
    if _da_session is not None:
        sub._history = list(_da_session._history)

    # Header frame so user knows this is a subagent
    append_text(
        build_inline_notif(
            f"subagent ({_cur_role}): {question[:60]}",
            "◈",
        )
    )
    app.invalidate()

    # Stream the answer
    try:
        async for event in sub.chat(question):
            if event.type == "token":
                # reuse the same streaming logic as
                # handle_ai_response — extract to a
                # shared helper if code duplication
                # becomes unwieldy
                ...
            elif event.type == "done":
                append_text(build_ai_frame(event.data))
                app.invalidate()
            elif event.type == "error":
                append_text(
                    build_error_frame(event.data)
                )
                app.invalidate()
    finally:
        # Always clean up — subagent is ephemeral
        try:
            await _da_pool.terminate(sub.session_id)
        except Exception:
            pass
```

Note on streaming: `chat()` yields `token` events one
character/chunk at a time. Use the same replace-last-block
technique already in `handle_ai_response()` for smooth
incremental rendering. If that logic grows too long, extract
it to `_stream_to_buffer(app, event_iter)` and call it from
both `handle_ai_response` and `_run_ask_subagent`.

#### 5.3  Replace the /ask command handler

In the command dispatch section (around line 4424), replace
the entire stub with:

```python
if text.lower().startswith("/ask"):
    question = text[4:].strip()
    append_text(
        build_user_frame(text, _exec_mode)
    )
    app.invalidate()
    if not question:
        append_text(
            build_inline_notif(
                "Usage: /ask <question>", "◈"
            )
        )
        app.invalidate()
        return
    asyncio.ensure_future(
        _run_ask_subagent(app, question)
    )
    return
```

Note the guard changes from `text.lower() == "/ask"` to
`text.lower().startswith("/ask")` so the question text
is captured in the same input event.

#### 5.4  Update /help text

Find the `/ask` entry in the help text (~line 3921) and
replace the description:

```
- `/ask <question>` — One-shot subagent answer with full
  current context. Does not modify session history.
```

### Summary — execution order

| # | Item | File | Effort |
|---|---|---|---|
| 1 | Rewrite assistant system_prompt | config/default.toml | Low |
| 2 | Rewrite coder system_prompt | config/default.toml | Low |
| 3 | Add sysadmin role | config/default.toml | Low |
| 4 | Rewrite researcher system_prompt | config/default.toml | Low |
| 5 | Enable git MCP server | config/default.toml | Trivial |
| 6 | Handle provider_fallback in TUI | davy_cli.py | Low |
| 7 | Token usage in top bar | davy_cli.py | Low |
| 8 | Improve tool call display | davy_cli.py | Low |
| 9 | Implement Tracer + /trace | trace.py + session.py + davy_cli.py | Medium |
| 10 | /ask subagent command | davy_cli.py | Medium |

Items 1-5 are pure config — no code changes, no risk of regression.
Items 6-8 are small, isolated TUI additions.
Items 9-10 are the only non-trivial code changes.

---

## What to NOT expect

Even with all of the above implemented, the model quality remains
the hard ceiling. The prompts will fully express themselves only
on models with strong instruction-following and reasoning (Claude
Sonnet/Opus, GPT-4-class models). On smaller models, the prompts
still help — but the gap to Claude Code narrows at the model level,
not just the prompt level.

The websearch tool requires `pip install duckduckgo-search` (zero
config) or setting TAVILY_API_KEY / EXA_API_KEY for higher-quality
results. Researcher and sysadmin roles benefit most from this.
