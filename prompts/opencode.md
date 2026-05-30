# OpenCode Research Notes

Source repo: https://github.com/anomalyco/opencode  
Branch: `dev`  
Date researched: 2026-05-29

---

## Plan Mode — How It Works

### Prompt file

`packages/opencode/src/session/prompt/plan.txt`

```
<system-reminder>
# Plan Mode - System Reminder

CRITICAL: Plan mode ACTIVE - you are in READ-ONLY phase. STRICTLY FORBIDDEN:
ANY file edits, modifications, or system changes. Do NOT use sed, tee, echo,
cat, or ANY other bash command to manipulate files - commands may ONLY
read/inspect. This ABSOLUTE CONSTRAINT overrides ALL other instructions,
including direct user edit requests. You may ONLY observe, analyze, and plan.
Any modification attempt is a critical violation. ZERO exceptions.

---

## Responsibility

Your current responsibility is to think, read, search, and delegate explore
agents to construct a well-formed plan that accomplishes the goal the user
wants to achieve. Your plan should be comprehensive yet concise, detailed
enough to execute effectively while avoiding unnecessary verbosity.

Ask the user clarifying questions or ask for their opinion when weighing
tradeups.

**NOTE:** At any point in time through this workflow you should feel free to
ask the user questions or clarifications. Don't make large assumptions about
user intent. The goal is to present a well researched plan to the user, and
tie any loose ends before implementation begins.

---

## Important

The user indicated that they do not want you to execute yet -- you MUST NOT
make any edits, run any non-readonly tools (including changing configs or
making commits), or otherwise make any changes to the system. This supersedes
any other instructions you have received.
</system-reminder>
```

### Injection mechanism

**Does NOT modify the system prompt.**

Instead, on every LLM turn while the active agent is `"plan"`, opencode
**appends plan.txt as a synthetic text part to the last user message**.

Key file: `packages/opencode/src/session/reminders.ts`

```typescript
import PROMPT_PLAN from "./prompt/plan.txt"

// Called just before the LLM request, inside prompt.ts:
// msgs = yield* SessionReminders.apply({ messages, agent, session })

// Inside reminders.ts — non-experimental plan mode:
const userMessage = input.messages.findLast(
  (msg) => msg.info.role === "user"
)

if (input.agent.name === "plan") {
  userMessage.parts.push({
    id: PartID.ascending(),
    messageID: userMessage.info.id,
    sessionID: userMessage.info.sessionID,
    type: "text",
    text: PROMPT_PLAN,
    synthetic: true,   // hidden from UI
  })
}
```

### Placement

- The **system prompt array** (`system: [...]`) is unchanged.
- `plan.txt` is appended to the **last user message's content** every turn.
- Marked `synthetic: true` → not shown in UI history.
- Fires on every turn where the active agent is `"plan"`.

### Experimental plan mode

A companion file `plan-mode.txt` is used when `flags.experimentalPlanMode`
is true. It is more elaborate (5-phase workflow, instructs the agent to write
a plan file to disk). Same injection mechanism — appended to last user message.

---

## Starry Implementation (applied 2026-05-29)

We mirrored the opencode approach:

- `starry_lib/prompts/plan_mode.txt` — bundled prompt (opencode content)
- `starry_lib/prompts/loader.py` — loads with user override:
  checks `~/.local/starry/prompts/plan_mode.txt` first, then bundled file
- `starry_lib/agents/session.py` — `_build_messages()` appends the plan
  prompt to the last user message when `self._mode == "plan"`, after
  context window truncation.

---

## Other opencode patterns to explore

- How opencode handles multi-agent orchestration / agent delegation
- The experimental plan mode (`plan-mode.txt`) 5-phase workflow
- How `reminders.ts` handles other injection types (not just plan mode)
- The `system.ts` structure (env + instructions + skills)
- Session persistence and restore mechanism
