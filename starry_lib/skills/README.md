# Native Skills

Each subdirectory under `starry_lib/skills/` is a
self-contained skill that is auto-loaded at startup and
exposed to the agent as an OpenAI-compatible tool call.

## Directory layout

```
starry_lib/skills/
    <skill_name>/
        descriptor.json   — OpenAI function schema
        skill.py          — execute(**kwargs) -> dict
```

## descriptor.json

Must be a valid OpenAI function-calling schema:

```json
{
  "type": "function",
  "function": {
    "name": "skill_name",
    "description": "What this skill does.",
    "parameters": {
      "type": "object",
      "properties": {
        "arg": { "type": "string", "description": "..." }
      },
      "required": ["arg"]
    }
  }
}
```

## skill.py

Must define an `execute` function (sync or async):

```python
async def execute(**kwargs) -> dict:
    ...
    return {"result": "..."}
```

Sync functions are automatically wrapped in an async
shim by the loader.

## Error handling

- Missing `descriptor.json` or `skill.py` raises
  `SkillLoadError` at startup — the skill is skipped
  with a warning.
- Errors inside `execute` should be caught and returned
  as `{"error": "..."}` rather than raised.

## Built-in skills

| Skill          | Description                          |
|----------------|--------------------------------------|
| `network_scan` | Host/port discovery via nmap or TCP  |
| `sys_info`     | CPU, memory, disk, network, OS info  |
