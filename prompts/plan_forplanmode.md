# Plan: Merged Plan Mode Prompt

## Goal

Merge the opencode plan_mode prompt (our standard) with the Claude Code
plan_mode prompt into a single, improved plan mode system reminder for Starry.

## Source Files

| File | Role |
|------|------|
| `starry_lib/prompts/plan_mode.txt` | Current standard (opencode) |
| `prompts/plan_mode.txt` | Reference (Claude Code) |
| `prompts/new_plan_mode.txt` | Draft output (review before deploying) |

## What to Keep from Each

### From opencode (standard)
- `<system-reminder>` wrapper
- Strong CRITICAL/FORBIDDEN language with specific forbidden commands
  (sed, tee, echo, cat, any bash file manipulation)
- `## Responsibility` section text
- `## Important` final reinforcement — stating no-edit constraint twice
  makes it harder for the LLM to rationalize violations
- Concise, direct tone

### From Claude Code (reference)
- Phased workflow structure (Phases 1–4, adapted for Starry)
- Parallel subagent guidance: when to use 1 vs 3, how to split focus
- Task-type perspective examples (new feature / bug fix / refactor)
- Subagent prompt guidelines (filenames, code traces, constraints)

## What to Drop from Claude Code

| Element | Reason |
|---------|--------|
| `${planInfo}` placeholder | Claude Code artifact; no equivalent in Starry |
| "the only file you can edit" | Starry has no plan file concept |
| Phase 5 / `plan_exit` tool | Claude Code-specific; does not exist in Starry |
| "explore subagent type" | Claude Code agent taxonomy; not ours |

## Constraints

### Constraint 1: No plan file concept
Starry has no dedicated plan file and no `plan_exit` tool. Phase 4 must
instruct the LLM to present the plan **inline in the chat**, not by writing
to a file.

Phase 4 language target: summarize the recommended approach, list critical
files and required changes, include a verification section.

### Constraint 2: Parallel agents via `task` tool
Starry supports subagents through the `task` tool (not a named "explore
subagent type"). Keep the parallel-agent guidance from Claude Code but
replace "explore subagent type" with "spawn a read-only subagent via the
`task` tool."

## Target Structure

```
<system-reminder>
  CRITICAL: READ-ONLY constraint          ← opencode
  ## Responsibility                       ← opencode
  ## Plan Workflow
    Phase 1: Initial Understanding        ← Claude Code (adapted)
    Phase 2: Design                       ← Claude Code (adapted)
    Phase 3: Review                       ← Claude Code (adapted)
    Phase 4: Present the Plan             ← adapted (no plan file)
  ## Important                            ← opencode final reinforcement
</system-reminder>
```

## Deployment (after review and sign-off)

1. Replace `starry_lib/prompts/plan_mode.txt` with approved draft
2. Replace `~/.local/starry/prompts/plan_mode.txt` with approved draft
3. `prompts/new_plan_mode.txt` becomes the reference copy in the design dir
