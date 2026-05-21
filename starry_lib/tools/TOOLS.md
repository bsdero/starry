# StarryLib Tool Reference

All tools are Python functions exposed to the LLM via OpenAI
function-calling format. The set of active tools depends on
the current execution mode.

---

## Mode Tool Matrix

| Tool                  | Plan & Research | Execution & Implementation |
|-----------------------|:--------------:|:-------------------------:|
| todowrite             | ✓              | ✓                         |
| task                  | ✓              | ✓                         |
| question              | ✓              | ✓                         |
| webfetch              | ✓              | ✓                         |
| websearch             | ✓              | ✓                         |
| skill                 | ✓              | ✓                         |
| glob                  | ✓              | ✓                         |
| grep                  | ✓              | ✓                         |
| read                  | ✓              | ✓                         |
| calculator            | ✓              | ✓                         |
| list_available_agents | ✓              | ✓                         |
| list_active_agents    | ✓              | ✓                         |
| describe_agent        | ✓              | ✓                         |
| bash                  |                | ✓                         |
| edit                  |                | ✓                         |
| write                 |                | ✓                         |
| call_agent            |                | ✓                         |
| stop_agent            |                | ✓                         |

---

## Per-Tool Permission Model

Each `Session` instance exposes two optional lists:

- `session.allowed_tools: list[str] | None` —
  When set, only tools whose names appear in this
  list are made available to the LLM.  All others
  are silently filtered out.

- `session.denied_tools: list[str] | None` —
  When set, tools whose names appear in this list
  are removed from the active schema and executor,
  even if they would normally be available for the
  current mode.

Both lists are applied inside
`Session.get_tool_schemas()` and
`Session.get_tool_executor()`. Set to `None`
to clear all restrictions.

### TUI controls

- `/setup → Toggle tool` — Shows an interactive
  menu where `✓` means enabled and `✗` means
  denied. Toggling a tool adds or removes it from
  `session.denied_tools`.

---

## Tool Descriptions

### bash
Execute a shell command and capture its output.

**Args:**
- `command` *(required)* — Shell command string.
- `timeout` — Timeout in seconds (default 30).
- `workdir` — Working directory for the command.

**Returns:** `{ stdout, stderr, returncode }` or `{ error }`.

---

### read
Read a file's contents or list a directory's entries.

**Args:**
- `filePath` *(required)* — Path to file or directory.
- `limit` — Maximum number of lines to return.
- `offset` — Starting line number, 0-based (default 0).

**Returns:** `{ content, lines, path }` for files,
`{ type, path, entries }` for directories, or `{ error }`.

---

### glob
Find files matching a glob pattern under a base directory.

**Args:**
- `pattern` *(required)* — Glob pattern, e.g. `**/*.py`.
- `path` — Base directory to search (default `.`).

**Returns:** `{ matches, count }` or `{ error }`.

---

### grep
Search file contents for a regex pattern.

**Args:**
- `pattern` *(required)* — Regex pattern.
- `include` — Filename glob filter, e.g. `*.py` (default `*`).
- `path` — File or directory to search (default `.`).

**Returns:** `{ matches: [{file, line, content}], count }`
or `{ error }`.

---

### edit
Replace an exact string in a file.

**Args:**
- `filePath` *(required)* — Path to the file.
- `oldString` *(required)* — Exact text to replace.
- `newString` *(required)* — Replacement text.
- `replaceAll` — Replace all occurrences (default false).
  If false and oldString appears more than once, returns error.

**Returns:** `{ replaced, file }` or `{ error }`.

---

### write
Create or overwrite a file with the given content.
Parent directories are created automatically.

**Args:**
- `filePath` *(required)* — Path to write.
- `content` *(required)* — Content to write.

**Returns:** `{ written, file }` or `{ error }`.

---

### task
Launch an autonomous subagent for a specific task.
The runtime (AgentPool) dispatches the subagent.

**Args:**
- `subagent_type` *(required)* — `assistant`, `coder`,
  or `researcher`.
- `prompt` — Task prompt for the subagent.
- `command` — Optional shell command for context.
- `task_id` — Optional identifier string.

**Returns:** `{ type: "subagent_request", subagent_type,
prompt, command, task_id }`.

---

### webfetch
Retrieve content from a URL via HTTP GET.

**Args:**
- `url` *(required)* — URL to fetch.
- `format` *(required)* — `text` or `json`.
- `timeout` — Timeout in seconds (default 15).

**Returns:** `{ content }` or `{ error }`.

---

### todowrite
Overwrite the persistent task list
(`~/.local/starry/todos.json`).

**Args:**
- `todos` *(required)* — Array of todo objects, each with:
  - `id` *(string, required)*
  - `content` *(string, required)*
  - `status` *(required)*: `pending`, `in_progress`,
    or `completed`
  - `priority` *(optional)*: `low`, `medium`, or `high`

**Returns:** `{ saved, file }` or `{ error }`.

---

### skill
Load specialized workflow instructions by name.
Reads from `<project_root>/skills/<name>.md`.

**Args:**
- `name` *(required)* — Skill name to load.

**Returns:** `{ skill, content }` or `{ error }`.

---

### question
Ask the user one or more questions. The TUI presentation
layer handles actual input collection.

**Args:**
- `questions` *(required)* — Array of question strings.

**Returns:** `{ type: "user_input_required", questions }`.

---

### websearch
Search the web using DuckDuckGo and return a list
of results with title, URL, and snippet.

**Args:**
- `query` *(required)* — Search query string.
- `max_results` — Maximum results to return (default 5).

**Returns:** `{ results: [{title, url, snippet}], count }`
or `{ error }`.

---

### calculator
Evaluate a mathematical expression safely without
calling the LLM.

**Args:**
- `expression` *(required)* — Math expression string,
  e.g. `"2 ** 10 + sqrt(3)"`. Supports standard
  arithmetic and common `math` module functions.

**Returns:** `{ result }` or `{ error }`.

---

### list_available_agents
List all named agent configurations stored on disk.
Use this before `call_agent` to see what agents exist.

**Args:** none.

**Returns:** Array of objects, each with:
`name`, `label`, `role`, `provider`, `model`,
`description`.

---

### list_active_agents
List all named agents currently running as live
sessions in the AgentPool.

**Args:** none.

**Returns:** Array of objects, each with:
`name`, `session_id`, `role`, `provider`, `model`,
`turn_count`, `token_usage`.

---

### describe_agent
Return the full configuration of a specific named
agent before calling it.

**Args:**
- `name` *(required)* — Agent name to describe.

**Returns:** Full `AgentConfig` as a dict, or
`{ error }` if the agent is not found.

---

### call_agent
Send a message to a named persistent agent. The agent
is spawned automatically if not already active and
retains its state across calls.
Execution mode only.

**Args:**
- `name` *(required)* — Name of the agent to call.
- `message` *(required)* — Message to send.
- `context` — Optional context injected as a system
  message before the agent's very first turn.

**Returns:** The agent's full response string.

---

### stop_agent
Terminate a running named agent session. The agent's
conversation state is permanently lost. The main LLM
is notified via a system message.
Execution mode only.

**Args:**
- `name` *(required)* — Name of the agent to stop.
- `reason` — Optional reason for stopping.

**Returns:** Confirmation string or error message.
