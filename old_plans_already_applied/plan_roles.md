# plan_roles.md — Standard Agentic Role System
# Date: 04/21/2026

Goal: elevate roles from "named system prompts" to first-class
agent definitions aligned with how production agentic frameworks
(CrewAI, AutoGen, LangGraph) model agents. Each role gets
structured prompt composition, per-role LLM parameters, explicit
tool/skill scoping, and the multi-agent routing hooks needed for
orchestrated pipelines.

---

## What changes and why

| Area | Today | After |
|------|-------|-------|
| Prompt | Free-text `system_prompt` | Structured fields assembled by a builder |
| LLM params | Model only (or provider default) | Temperature, max_tokens, top_p per role |
| Tool access | Mode-only (plan/execution) | Per-role allowed/denied tool + skill lists |
| Multi-agent | Pool picks role by name | Roles declare delegation targets + handoff rules |
| Config | 3 fields in TOML | ~12 fields; backwards-compatible |
| BaseAgent | Passive dataclass | Carries all role parameters; owns prompt build |

---

## Task 1 — Expand `AgentConfig` (settings.py)

Replace the current three-field model with the full role spec.
All new fields have defaults so existing TOML files keep working.

```python
class AgentConfig(BaseModel):
    # ── Identity ──────────────────────────────────────────
    name: str
    label: str

    # ── Structured prompt composition ─────────────────────
    # Each field is optional. If system_prompt is set it
    # takes precedence over the assembled fields (escape
    # hatch for roles that need full manual control).
    goal: str = ""
    backstory: str = ""
    constraints: list[str] = []
    output_format: str = ""
    system_prompt: str = ""   # overrides assembly when set

    # ── LLM parameters ────────────────────────────────────
    model_override: str | None = None
    temperature: float | None = None   # None = provider default
    max_tokens: int | None = None
    top_p: float | None = None

    # ── Tool + skill scoping ──────────────────────────────
    # None = inherit from mode (current behaviour).
    # A list = explicit whitelist; empty list = no tools.
    allowed_tools: list[str] | None = None
    denied_tools: list[str] = []
    allowed_skills: list[str] | None = None
    denied_skills: list[str] = []

    # ── Multi-agent routing ───────────────────────────────
    # Names of roles this agent may delegate work to.
    can_delegate_to: list[str] = []
    # Names of roles that may delegate to this agent.
    # Used by AgentPool.route() to build the routing table.
    accepts_from: list[str] = []
    # Short description used by the orchestrator when
    # deciding which agent to route a task to.
    expertise: str = ""
```

### Acceptance criteria
- Existing `config/default.toml` loads without errors.
- New fields missing from TOML resolve to their defaults.
- `load_settings()` validates that names in
  `can_delegate_to` refer to roles that exist in
  `settings.agents` (warn, do not hard-fail).

---

## Task 2 — Structured system prompt builder (base.py)

`BaseAgent.build_system_prompt()` assembles the prompt from
structured fields. `build_messages()` calls it instead of
using `self.system_prompt` directly.

### Assembly order (when `system_prompt` is empty)

```
You are {label}.

Goal:
{goal}

Background:
{backstory}

Constraints:
- {constraint[0]}
- {constraint[1]}
...

Output format:
{output_format}
```

Sections with empty values are omitted entirely — a role
with only `goal` set produces a clean two-line prompt.

### Rules
- If `system_prompt` is non-empty it is used verbatim;
  structured fields are ignored. This preserves backwards
  compatibility for the three existing roles.
- The builder is a pure function (no I/O, no side effects)
  so it can be unit-tested in isolation.
- Max assembled length: warn (do not truncate) if the
  prompt exceeds 2000 tokens (rough char estimate: 8000).

### BaseAgent changes
```python
@dataclass
class BaseAgent:
    name: str
    label: str
    system_prompt: str        # raw override
    goal: str = ""
    backstory: str = ""
    constraints: list[str] = field(default_factory=list)
    output_format: str = ""
    tools: list = field(default_factory=list)
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] = field(default_factory=list)
    allowed_skills: list[str] | None = None
    denied_skills: list[str] = field(default_factory=list)
    can_delegate_to: list[str] = field(default_factory=list)
    expertise: str = ""

    def effective_system_prompt(self) -> str:
        """Return the assembled or overridden prompt."""
        ...

    def build_messages(self, user_input, history=None):
        """Use effective_system_prompt() as system message."""
        ...
```

---

## Task 3 — Update `build_agent()` (roles.py)

Pass all new `AgentConfig` fields through to `BaseAgent`.

```python
def build_agent(
    role_cfg: AgentConfig,
    provider_cfg: ProviderConfig,
) -> BaseAgent:
    model = role_cfg.model_override or provider_cfg.default_model
    return BaseAgent(
        name=role_cfg.name,
        label=role_cfg.label,
        system_prompt=role_cfg.system_prompt,
        goal=role_cfg.goal,
        backstory=role_cfg.backstory,
        constraints=role_cfg.constraints,
        output_format=role_cfg.output_format,
        model=model,
        temperature=role_cfg.temperature,
        max_tokens=role_cfg.max_tokens,
        top_p=role_cfg.top_p,
        allowed_tools=role_cfg.allowed_tools,
        denied_tools=role_cfg.denied_tools,
        allowed_skills=role_cfg.allowed_skills,
        denied_skills=role_cfg.denied_skills,
        can_delegate_to=role_cfg.can_delegate_to,
        expertise=role_cfg.expertise,
    )
```

Remove the unused `extra_tools` parameter — tool scoping
is now role-driven, not caller-driven.

---

## Task 4 — Wire tool/skill scoping into Session (session.py)

### On spawn
`AgentPool.spawn()` initialises the session's tool filters
from the agent's fields, not from external callers:

```python
session.allowed_tools = agent.allowed_tools
session.denied_tools  = agent.denied_tools
```

`_tool_permitted()` already exists and respects these lists —
no logic change needed there, only the initialisation point.

### Skill scoping
`session.py` currently has no skill filtering. Add:

```python
def _skill_permitted(self, name: str) -> bool:
    if (self._agent.allowed_skills is not None
            and name not in self._agent.allowed_skills):
        return False
    if name in self._agent.denied_skills:
        return False
    return True
```

`get_tool_executor()` must call `_skill_permitted()` for
every tool whose name matches a loaded skill (after Task 2
of plan_skills.md is done, skill names come from
`skill_loader.load_skills()`).

### On `switch_role()`
Re-apply tool/skill filters from the new role's `AgentConfig`
after rebuilding `self._agent`. Currently `switch_role()` only
replaces the agent; filters on the session are left stale.

---

## Task 5 — Propagate LLM parameters (session.py + client.py)

Every LLM call in `session.py` (`chat()`, `chat_complete()`,
`chat_with_tools()`) must pass the role's LLM parameters to
the API. Currently only `model` is forwarded.

### Change in session.py
Build a `_llm_kwargs()` helper:

```python
def _llm_kwargs(self) -> dict:
    kw = {"model": self._agent.model}
    if self._agent.temperature is not None:
        kw["temperature"] = self._agent.temperature
    if self._agent.max_tokens is not None:
        kw["max_tokens"] = self._agent.max_tokens
    if self._agent.top_p is not None:
        kw["top_p"] = self._agent.top_p
    return kw
```

All `client.chat.completions.create(...)` calls replace
their inline kwargs with `**self._llm_kwargs()`.

### No change to `build_client()`
The AsyncOpenAI client is provider-scoped, not role-scoped.
Parameters are passed per-request, not on the client object.

---

## Task 6 — Multi-agent routing in AgentPool (pool.py)

### `AgentPool.route()`
New method that selects the best session for a task based
on role `expertise` fields and the `can_delegate_to` /
`accepts_from` declaration graph.

```python
async def route(
    self,
    prompt: str,
    from_role: str | None = None,
) -> Session:
    """Return the most appropriate session for prompt.

    Selection strategy (in order):
    1. If from_role is set, only consider sessions whose
       role appears in from_role's can_delegate_to list.
    2. Among candidates, pick the session whose role
       expertise string is most relevant to prompt
       (simple keyword overlap; no LLM call needed).
    3. If no candidate matches, fall back to the default
       active_role session.
    """
    ...
```

### `AgentPool.delegate_auto()`
Wraps `route()` + `run_subtask()` for single-call
orchestration:

```python
async def delegate_auto(
    self,
    prompt: str,
    from_role: str | None = None,
) -> str:
    """Route prompt to the best agent and return response."""
    session = await self.route(prompt, from_role)
    return await session.chat_complete(prompt)
```

### Routing table helper
Build a cached adjacency structure at `AgentPool.__aenter__`:

```python
# {role_name: set_of_role_names_it_can_delegate_to}
self._routing_table: dict[str, set[str]] = {
    name: set(cfg.can_delegate_to)
    for name, cfg in self._settings.agents.items()
}
```

### Notes
- `route()` must not spawn new sessions — it selects among
  existing ones registered in `self._sessions`.
- If no session exists for the chosen role, raise
  `RuntimeError("No active session for role '<name>'")`.
  The caller is responsible for spawning sessions upfront.

---

## Task 7 — Update `config/default.toml`

Rewrite the three existing role blocks using the new schema.
Show all available fields so the file acts as documentation.

```toml
[agents.assistant]
label        = "Assistant"
goal         = "Help the user with any task concisely."
backstory    = ""
constraints  = ["Be concise.", "Format responses in Markdown."]
output_format = ""
# system_prompt = ""   # uncomment to override assembly
temperature  = 0.7
# max_tokens  = 2048
# allowed_tools = []   # None = all tools for the active mode
# can_delegate_to = ["researcher", "coder"]
expertise    = "general questions, writing, planning"

[agents.coder]
label        = "Coder"
goal         = "Write correct, clean Python 3.11+ code."
backstory    = "Expert software engineer with 10+ years experience."
constraints  = [
    "Use type hints.",
    "Prefer stdlib over third-party when equal.",
    "Format all code blocks with the correct language tag.",
]
output_format = "Code block first, explanation after."
temperature  = 0.2
allowed_tools = ["bash", "read", "glob", "grep", "edit", "write"]
can_delegate_to = ["researcher"]
expertise    = "code, debugging, refactoring, Python, shell scripts"

[agents.researcher]
label        = "Researcher"
goal         = "Find and summarise information accurately."
backstory    = "Analytical researcher who cites sources inline."
constraints  = [
    "Cite sources inline.",
    "Use headers and bullet points for long answers.",
]
output_format = "Summary → Findings → Sources"
temperature  = 0.5
allowed_tools = ["webfetch", "read", "glob", "grep", "todowrite"]
allowed_skills = ["sys_info", "network_scan"]
expertise    = "research, analysis, summarisation, data gathering"
```

---

## Task 8 — TUI updates (davy_cli.py)

### `/role` menu
Extend the selection menu to show more than just the label.
Each menu entry: `<label>  —  <expertise[:50]>`.

### Role info frame
After a role switch, display a brief role info frame in the
scroll buffer:

```
● Role: Coder
  Goal:    Write correct, clean Python 3.11+ code.
  Tools:   bash, read, glob, grep, edit, write
  Skills:  (all)
  Model:   gpt-oss-120b-thinking  temp=0.2
```

### top_bar
Add temperature to the top bar display alongside the model
(only when a role-level override is active):

```
davy  |  coder  |  gpt-oss-120b  t=0.2  |  CPU 12%
```

### Session restore
When restoring a session, re-apply tool and skill filters
from the saved role name (already done via `switch_role()`;
just verify it picks up the new fields).

---

## Task 9 — Tests

### Unit tests (`tests/unit/`)

`test_agent_config.py`:
- All new `AgentConfig` fields default correctly.
- `effective_system_prompt()` assembles from structured
  fields when `system_prompt` is empty.
- `effective_system_prompt()` returns `system_prompt`
  verbatim when set (overrides structured fields).
- Prompt assembly omits sections with empty values.

`test_tool_scoping.py`:
- Session initialised from a role with
  `allowed_tools = ["bash", "read"]` exposes only those two.
- `denied_tools` removes a tool from an otherwise full set.
- `allowed_skills = ["sys_info"]` blocks `network_scan`
  from the executor.
- `switch_role()` updates filters to the new role's lists.

`test_llm_kwargs.py`:
- `_llm_kwargs()` includes `temperature` only when set.
- Role with `temperature=None` omits the key entirely.

`test_routing.py`:
- `route()` returns the session whose role is in
  `can_delegate_to` of `from_role`.
- `route()` falls back to `active_role` when no candidate
  matches.
- `route()` raises `RuntimeError` when chosen role has no
  active session.

### Integration tests (`tests/integration/`)

`test_role_delegation.py`:
- Spawn `coder` + `researcher` sessions.
- `delegate_auto("summarise the latest Python changelog",
  from_role="coder")` routes to `researcher` and returns
  a non-empty string.

---

## Task 10 — Documentation

- Update `CLAUDE.md` roles section with the new TOML schema.
- Update `README.md` API examples to show `temperature` and
  `allowed_tools` in a spawn call.
- Add a `config/default.toml` header comment block that
  lists every supported `[agents.*]` field with a one-line
  description.

---

## Task 11 — Port existing roles to the new schema

Migrate all three roles in `config/default.toml` from the
legacy `system_prompt` block to the full structured format
defined in Task 7. This is a config-only change — no Python
code is touched — but it validates that the prompt builder
(Task 2) reproduces the intent of the original prompts.

### assistant

```toml
[agents.assistant]
label         = "Assistant"
goal          = """
Help the user with any task. Be concise and direct.
"""
constraints   = [
    "Format all responses in Markdown.",
    "Ask for clarification when the request is ambiguous.",
]
temperature   = 0.7
expertise     = "general questions, writing, planning, explanation"
can_delegate_to = ["coder", "researcher"]
```

### coder

Original intent: expert Python engineer, clean code,
type hints, stdlib preference, correct language tags.

```toml
[agents.coder]
label         = "Coder"
goal          = """
Write correct, idiomatic Python 3.11+ code that solves
the user's problem with minimal complexity.
"""
backstory     = """
Senior software engineer with deep Python expertise.
Defaults to the standard library and reaches for
third-party packages only when they offer a clear
advantage.
"""
constraints   = [
    "Always use type hints.",
    "Prefer stdlib over third-party when capability is equal.",
    "Every code block must carry the correct language tag.",
    "Write no comments except where the WHY is non-obvious.",
]
output_format = "Code block first. Brief explanation after."
temperature   = 0.2
allowed_tools = [
    "bash", "read", "glob", "grep", "edit", "write",
    "todowrite", "task", "question",
]
can_delegate_to = ["researcher"]
expertise     = """
Python, shell scripting, debugging, refactoring,
code review, algorithm design
"""
```

### researcher

Original intent: research analyst, clear summaries,
inline citations, headers + bullets for long answers.

```toml
[agents.researcher]
label         = "Researcher"
goal          = """
Find, evaluate, and summarise information accurately.
Prefer primary sources. Flag uncertainty explicitly.
"""
backstory     = """
Analytical researcher trained to synthesise information
from multiple sources and present it with clarity.
"""
constraints   = [
    "Cite sources inline using [Source: ...] notation.",
    "Use headers and bullet points for answers over ~200 words.",
    "Flag gaps in available information rather than guessing.",
]
output_format = "Summary → Key Findings → Sources"
temperature   = 0.5
allowed_tools = [
    "webfetch", "read", "glob", "grep",
    "todowrite", "question",
]
allowed_skills = ["sys_info", "network_scan"]
can_delegate_to = ["coder"]
expertise     = """
research, web search, data gathering, summarisation,
analysis, fact-checking
"""
```

### Verification checklist
After porting, confirm:
- [ ] `load_settings()` parses all three roles without errors.
- [ ] `effective_system_prompt()` for each role produces
      a prompt that covers the same intent as the original
      free-text block (manual review, not automated).
- [ ] `/role` menu in the TUI shows the new `expertise`
      snippet for each role.
- [ ] All three existing unit tests that depend on
      role system prompts still pass.

---

## Dependency order

```
Task 1  (AgentConfig expansion)
    └─ Task 2  (prompt builder in BaseAgent)
           └─ Task 3  (build_agent() update)
                  ├─ Task 4  (Session tool/skill scoping)
                  ├─ Task 5  (LLM param propagation)
                  └─ Task 7  (TOML schema — new roles)
                         └─ Task 11 (port existing roles)
Task 4 + Task 5 → Task 6  (AgentPool routing)
Tasks 4,5,6,7  → Task 8  (TUI updates)
Tasks 1-7,11   → Task 9  (tests)
Task 9         → Task 10 (docs)
```

## Files touched

| File | Change |
|------|--------|
| `davyagent/config/settings.py` | Expand `AgentConfig` |
| `davyagent/agents/base.py` | New fields + `effective_system_prompt()` |
| `davyagent/agents/roles.py` | Pass all fields; remove `extra_tools` |
| `davyagent/agents/session.py` | Init filters from agent; `_llm_kwargs()`; skill filter; `switch_role()` fix |
| `davyagent/agents/pool.py` | `route()`, `delegate_auto()`, routing table |
| `config/default.toml` | Rewrite role blocks (Task 7 schema + Task 11 port) |
| `davy_cli.py` | Role menu, info frame, top_bar |
| `tests/unit/test_agent_config.py` | New |
| `tests/unit/test_tool_scoping.py` | New |
| `tests/unit/test_llm_kwargs.py` | New |
| `tests/unit/test_routing.py` | New |
| `tests/integration/test_role_delegation.py` | New |
