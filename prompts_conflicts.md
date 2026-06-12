# Prompt Conflicts Report

Analysis of unresolved directive conflicts between role prompts and
mode prompts (`beast.md`, `new_plan_mode.txt`).

Resolved conflicts are not listed here.

---

## High severity

*(No unresolved high-severity conflicts.)*

---

## Medium severity

*(No unresolved medium-severity conflicts.)*

---

## Low severity

*(No unresolved low-severity conflicts.)*

---

## Conflicts resolved this session (for reference)

| Conflict | Resolution |
|---|---|
| Beast + all roles: communication style | Removed `# Communication Guidelines` section from `beast.md` and `beast.txt` |
| Plan mode + SAGE: single recommendation vs. explore alternatives | Changed plan mode to require alternatives summary before recommendation |
| Beast + SYSADMIN: autonomy vs. safety confirmations | Added carve-out to Beast's autonomy directives: pauses when risk is high, operation is unwanted, root access is required, or operation is irreversible |
| Beast + INTEGRATOR: autonomy vs. safety confirmations | Same carve-out as SYSADMIN — irreversible and high-risk ops (force-push, branch delete) now pause |
| Beast + CODER: "keep going" vs. scope discipline | Carve-out tightened to "unwanted or out of scope" — explicitly covers scope creep |
| Plan mode + REVIEWER: read-only vs. mandatory test run | Added "Plan mode" section + softened workflow step 3 to "run tests or describe which tests you would run" |
| Plan mode + TESTER: read-only vs. mandatory baseline run | Added "Plan mode" section + softened step 0 to "run suite or describe which suite you would run" |
| Plan mode + INTEGRATOR: read-only vs. mandatory baseline test run | Added "Plan mode" section + softened step 0 inline to same pattern |
| Plan mode + PILOT: read-only subagents vs. execution delegation | Added PILOT exception to plan mode: produce delegation plan without invoking `task` |
| Beast + REVIEWER: "fully solve" vs. review-only boundary | Added to REVIEWER: "Your finished review is considered the solution to the problem." |
| Beast + CODER/ORACLE: pre-announce tool calls vs. no preamble | Removed announcement directive from `beast.md` and `beast.txt` |
| Beast + PILOT: do-it vs. delegate | Added to PILOT: "Your complete, executable delegation plan is considered the solution to the problem." |
| Beast + ASSISTANT/SAGE: autonomous vs. ask when ambiguous | Added "Clarifying questions" carve-out to `beast.md` and `beast.txt`: one question permitted when genuine ambiguity changes the answer |
| Beast + ASSISTANT: keep-going vs. mandatory follow-up JSON | Added "Beast mode" note to both `assistant.txt`: suppress JSON block in intermediate responses; append only in the final response |
| Plan mode + CODER: read-only vs. running reproduction scripts | Added `# Plan mode` section to both `coder.txt`; softened bug-fix step 2 inline to "or in plan mode describe what you would run" |
| Beast + all roles: identity collision — `"You are opencode"` overrides role identity | Removed `"You are opencode, an agent - "` prefix from `beast.md` and `beast.txt` |
| Beast + all roles: memory backend — `# Memory` section references VS Code/Copilot `.github/instructions/` file incompatible with Starry's `~/.local/starry/conf/` system | Removed entire `# Memory` section from `beast.md` and `beast.txt` |
| Beast + TESTER: "no code display" vs. "verbatim error output" | Narrowed beast directive to source code listings only; command output, error messages, and stack traces are always shown verbatim |
| Beast + CODER/TESTER/REVIEWER/INTEGRATOR: mandatory internet research overrides code-centric role workflows | Replaced absolute mandate with conditional rule: webfetch required when installing third-party libraries; optional for code-centric roles on pure code tasks |
| Beast + CODER/REVIEWER/TESTER: per-step todo redisplay vs. anti-preamble | Added carve-out: CODER, REVIEWER, TESTER suppress per-step todo redisplay and lead with the finding or change |
| Beast + CODER: 2000-line read mandate vs. targeted reads | Reframed as ceiling: "up to 2000 lines"; CODER prefers targeted reads of the relevant section |
