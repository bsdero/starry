"""Unit tests for StarryLib tool implementations
and the tool loader/session mode integration."""

import asyncio
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Tool modules ──────────────────────────────────────────────────
from starry_lib.tools.implementations import (
    bash,
    edit,
    glob,
    grep,
    question,
    read,
    task,
    todowrite,
    webfetch,
    write,
)
from starry_lib.tools.skill_loader import load_skills
from starry_lib.tools.tool_loader import (
    get_tool_executor,
    get_tool_schemas,
)

# ── Helpers ───────────────────────────────────────────────────────

_STATIC_PLAN_NAMES = {
    "todowrite", "task", "calculator",
    "question", "webfetch", "websearch",
    "glob", "grep", "read",
    "list_available_agents",
    "list_active_agents",
    "describe_agent",
}
_SKILL_NAMES = {
    t.SCHEMA["function"]["name"]
    for t in load_skills()
}
_PLAN_TOOL_NAMES = _STATIC_PLAN_NAMES | _SKILL_NAMES
_EXEC_ONLY_NAMES = {
    "bash", "edit", "write",
    "call_agent", "stop_agent",
}
_ALL_TOOL_NAMES = _PLAN_TOOL_NAMES | _EXEC_ONLY_NAMES


def _schema_name(mod):
    return mod.SCHEMA["function"]["name"]


def _schema_required(mod):
    return (
        mod.SCHEMA["function"]["parameters"]
        .get("required", [])
    )


# ═══════════════════════════════════════════════════════════════════
# bash
# ═══════════════════════════════════════════════════════════════════


class TestBashTool:
    def test_schema_name(self):
        assert _schema_name(bash) == "bash"

    def test_schema_requires_command(self):
        assert "command" in _schema_required(bash)

    def test_execute_returns_stdout(self):
        r = bash.execute("echo hello")
        assert r["returncode"] == 0
        assert "hello" in r["stdout"]

    def test_execute_captures_stderr(self):
        r = bash.execute(
            "echo err >&2", timeout=5
        )
        assert "err" in r["stderr"]

    def test_execute_nonzero_returncode(self):
        r = bash.execute("exit 42", timeout=5)
        assert r["returncode"] == 42

    def test_execute_timeout_returns_error(self):
        r = bash.execute("sleep 60", timeout=1)
        assert "error" in r
        assert "timed out" in r["error"].lower()

    def test_execute_workdir(self, tmp_path):
        r = bash.execute("pwd", workdir=str(tmp_path))
        assert r["returncode"] == 0
        assert str(tmp_path) in r["stdout"]


# ═══════════════════════════════════════════════════════════════════
# read
# ═══════════════════════════════════════════════════════════════════


class TestReadTool:
    def test_schema_name(self):
        assert _schema_name(read) == "read"

    def test_schema_requires_filepath(self):
        assert "filePath" in _schema_required(read)

    def test_reads_file_content(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3")
        r = read.execute(str(f))
        assert r["content"] == "line1\nline2\nline3"
        assert r["lines"] == 3

    def test_limit_truncates_lines(self, tmp_path):
        f = tmp_path / "many.txt"
        f.write_text("\n".join(
            str(i) for i in range(10)
        ))
        r = read.execute(str(f), limit=3)
        assert r["lines"] == 3
        assert "0" in r["content"]
        assert "3" not in r["content"]

    def test_offset_skips_lines(self, tmp_path):
        f = tmp_path / "offset.txt"
        f.write_text("a\nb\nc\nd")
        r = read.execute(str(f), offset=2)
        assert "a" not in r["content"]
        assert "c" in r["content"]

    def test_lists_directory(self, tmp_path):
        (tmp_path / "alpha.txt").write_text("x")
        (tmp_path / "beta.txt").write_text("y")
        r = read.execute(str(tmp_path))
        assert r["type"] == "directory"
        names = [
            pathlib.Path(e).name
            for e in r["entries"]
        ]
        assert "alpha.txt" in names
        assert "beta.txt" in names

    def test_missing_file_returns_error(self):
        r = read.execute("/no/such/file.txt")
        assert "error" in r
        assert "Not found" in r["error"]


# ═══════════════════════════════════════════════════════════════════
# glob
# ═══════════════════════════════════════════════════════════════════


class TestGlobTool:
    def test_schema_name(self):
        assert _schema_name(glob) == "glob"

    def test_schema_requires_pattern(self):
        assert "pattern" in _schema_required(glob)

    def test_finds_matching_files(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        r = glob.execute("*.py", path=str(tmp_path))
        names = [
            pathlib.Path(m).name
            for m in r["matches"]
        ]
        assert "a.py" in names
        assert "b.py" in names
        assert "c.txt" not in names

    def test_no_matches_returns_empty(self, tmp_path):
        r = glob.execute(
            "*.xyz", path=str(tmp_path)
        )
        assert r["matches"] == []
        assert r["count"] == 0

    def test_recursive_pattern(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("")
        r = glob.execute(
            "**/*.py", path=str(tmp_path)
        )
        assert r["count"] >= 1
        found = any(
            "deep.py" in m for m in r["matches"]
        )
        assert found

    def test_count_matches_length(self, tmp_path):
        for i in range(4):
            (tmp_path / f"f{i}.md").write_text("")
        r = glob.execute(
            "*.md", path=str(tmp_path)
        )
        assert r["count"] == len(r["matches"])


# ═══════════════════════════════════════════════════════════════════
# grep
# ═══════════════════════════════════════════════════════════════════


class TestGrepTool:
    def test_schema_name(self):
        assert _schema_name(grep) == "grep"

    def test_schema_requires_pattern(self):
        assert "pattern" in _schema_required(grep)

    def test_finds_matching_line(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text(
            "def foo():\n    pass\n"
            "def bar():\n    return 1\n"
        )
        r = grep.execute(
            "def foo", path=str(f)
        )
        assert r["count"] == 1
        assert r["matches"][0]["line"] == 1
        assert "def foo" in r["matches"][0]["content"]

    def test_include_filter_limits_files(
        self, tmp_path
    ):
        (tmp_path / "a.py").write_text("TARGET")
        (tmp_path / "b.txt").write_text("TARGET")
        r = grep.execute(
            "TARGET",
            include="*.py",
            path=str(tmp_path),
        )
        files = {m["file"] for m in r["matches"]}
        assert all(f.endswith(".py") for f in files)

    def test_invalid_regex_returns_error(self):
        r = grep.execute("[invalid(")
        assert "error" in r
        assert "regex" in r["error"].lower()

    def test_no_match_returns_empty(self, tmp_path):
        (tmp_path / "x.txt").write_text("hello")
        r = grep.execute(
            "NOMATCH", path=str(tmp_path)
        )
        assert r["count"] == 0
        assert r["matches"] == []

    def test_returns_file_line_content_keys(
        self, tmp_path
    ):
        f = tmp_path / "f.txt"
        f.write_text("find me here\n")
        r = grep.execute("find me", path=str(f))
        assert r["count"] == 1
        m = r["matches"][0]
        assert "file" in m
        assert "line" in m
        assert "content" in m


# ═══════════════════════════════════════════════════════════════════
# edit
# ═══════════════════════════════════════════════════════════════════


class TestEditTool:
    def test_schema_name(self):
        assert _schema_name(edit) == "edit"

    def test_schema_required_fields(self):
        req = _schema_required(edit)
        assert "filePath" in req
        assert "oldString" in req
        assert "newString" in req

    def test_replaces_text(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello world")
        r = edit.execute(
            str(f), "hello", "goodbye"
        )
        assert r["replaced"] == 1
        assert f.read_text() == "goodbye world"

    def test_error_when_old_not_found(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello world")
        r = edit.execute(str(f), "nope", "x")
        assert "error" in r
        assert "not found" in r["error"].lower()

    def test_error_when_ambiguous_without_flag(
        self, tmp_path
    ):
        f = tmp_path / "file.txt"
        f.write_text("aa aa aa")
        r = edit.execute(str(f), "aa", "bb")
        assert "error" in r
        assert "3" in r["error"]

    def test_replace_all_replaces_every_occurrence(
        self, tmp_path
    ):
        f = tmp_path / "file.txt"
        f.write_text("aa aa aa")
        r = edit.execute(
            str(f), "aa", "bb", replaceAll=True
        )
        assert r["replaced"] == 3
        assert f.read_text() == "bb bb bb"

    def test_error_on_missing_file(self, tmp_path):
        r = edit.execute(
            str(tmp_path / "gone.txt"),
            "x",
            "y",
        )
        assert "error" in r
        assert "Not found" in r["error"]


# ═══════════════════════════════════════════════════════════════════
# write
# ═══════════════════════════════════════════════════════════════════


class TestWriteTool:
    def test_schema_name(self):
        assert _schema_name(write) == "write"

    def test_schema_required_fields(self):
        req = _schema_required(write)
        assert "filePath" in req
        assert "content" in req

    def test_creates_file(self, tmp_path):
        f = tmp_path / "new.txt"
        r = write.execute(str(f), "hello")
        assert r["written"] == len("hello")
        assert f.read_text() == "hello"

    def test_overwrites_existing_file(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("old content")
        write.execute(str(f), "new content")
        assert f.read_text() == "new content"

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "a" / "b" / "c.txt"
        write.execute(str(f), "deep")
        assert f.read_text() == "deep"

    def test_written_matches_content_length(
        self, tmp_path
    ):
        content = "abcdef"
        f = tmp_path / "len.txt"
        r = write.execute(str(f), content)
        assert r["written"] == len(content)


# ═══════════════════════════════════════════════════════════════════
# webfetch
# ═══════════════════════════════════════════════════════════════════


class TestWebfetchTool:
    def test_schema_name(self):
        assert _schema_name(webfetch) == "webfetch"

    def test_schema_required_fields(self):
        req = _schema_required(webfetch)
        assert "url" in req
        assert "format" in req

    def _mock_urlopen(self, body: bytes):
        """Context manager mock for urlopen."""
        cm = MagicMock()
        cm.__enter__ = MagicMock(
            return_value=MagicMock(
                read=MagicMock(return_value=body)
            )
        )
        cm.__exit__ = MagicMock(
            return_value=False
        )
        return cm

    def test_returns_text_content(self):
        body = b"hello from web"
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_urlopen(body),
        ):
            r = webfetch.execute(
                "http://example.com", "text"
            )
        assert r["content"] == "hello from web"

    def test_returns_parsed_json(self):
        payload = json.dumps(
            {"key": "value"}
        ).encode()
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_urlopen(
                payload
            ),
        ):
            r = webfetch.execute(
                "http://example.com/api", "json"
            )
        assert r["content"] == {"key": "value"}

    def test_json_parse_failure_returns_error(self):
        body = b"not json {"
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_urlopen(body),
        ):
            r = webfetch.execute(
                "http://example.com", "json"
            )
        assert "error" in r
        assert "JSON" in r["error"]

    def test_url_error_returns_error(self):
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError(
                "unreachable"
            ),
        ):
            r = webfetch.execute(
                "http://nowhere.invalid", "text"
            )
        assert "error" in r
        assert "URL error" in r["error"]


# ═══════════════════════════════════════════════════════════════════
# todowrite
# ═══════════════════════════════════════════════════════════════════


class TestTodowriteTool:
    def test_schema_name(self):
        assert _schema_name(todowrite) == "todowrite"

    def test_schema_requires_todos(self):
        assert "todos" in _schema_required(todowrite)

    def test_writes_todos_to_file(self, tmp_path):
        target = tmp_path / "todos.json"
        with patch.object(
            todowrite, "_TODO_FILE", target
        ):
            items = [
                {
                    "id": "1",
                    "content": "do something",
                    "status": "pending",
                }
            ]
            r = todowrite.execute(items)
        assert r["saved"] == 1
        saved = json.loads(target.read_text())
        assert saved[0]["content"] == "do something"

    def test_empty_list_clears_file(self, tmp_path):
        target = tmp_path / "todos.json"
        with patch.object(
            todowrite, "_TODO_FILE", target
        ):
            r = todowrite.execute([])
        assert r["saved"] == 0
        assert json.loads(target.read_text()) == []

    def test_multiple_todos(self, tmp_path):
        target = tmp_path / "todos.json"
        items = [
            {
                "id": str(i),
                "content": f"task {i}",
                "status": "pending",
            }
            for i in range(5)
        ]
        with patch.object(
            todowrite, "_TODO_FILE", target
        ):
            r = todowrite.execute(items)
        assert r["saved"] == 5


# ═══════════════════════════════════════════════════════════════════
# question
# ═══════════════════════════════════════════════════════════════════


class TestQuestionTool:
    def test_schema_name(self):
        assert _schema_name(question) == "question"

    def test_schema_requires_questions(self):
        assert "questions" in _schema_required(
            question
        )

    def test_returns_user_input_required(self):
        r = question.execute(["What is your name?"])
        assert r["type"] == "user_input_required"

    def test_returns_all_questions(self):
        qs = ["Q1?", "Q2?", "Q3?"]
        r = question.execute(qs)
        assert r["questions"] == qs

    def test_empty_list_accepted(self):
        r = question.execute([])
        assert r["type"] == "user_input_required"
        assert r["questions"] == []


# ═══════════════════════════════════════════════════════════════════
# task
# ═══════════════════════════════════════════════════════════════════


class TestTaskTool:
    def test_schema_name(self):
        assert _schema_name(task) == "task"

    def test_schema_requires_subagent_type(self):
        assert "subagent_type" in _schema_required(
            task
        )

    @pytest.mark.asyncio
    async def test_returns_error_without_pool(self):
        r = await task.execute(
            "coder", prompt="fix bug"
        )
        assert r["type"] == "error"
        assert "AgentPool" in r["message"]

    @pytest.mark.asyncio
    async def test_task_id_generated_when_omitted(
        self,
    ):
        r = await task.execute("researcher")
        assert r["task_id"] != ""

    @pytest.mark.asyncio
    async def test_explicit_task_id_preserved(self):
        r = await task.execute(
            "assistant",
            task_id="my-task-42",
        )
        assert r["task_id"] == "my-task-42"

    @pytest.mark.asyncio
    async def test_prompt_included_in_pool_call(self):
        from unittest.mock import AsyncMock
        from starry_lib.tools.implementations import task as t

        mock_pool = MagicMock()
        mock_pool.run_subtask = AsyncMock(
            return_value="done"
        )
        original = t._pool
        t._pool = mock_pool
        try:
            r = await t.execute(
                "coder", prompt="fix it"
            )
        finally:
            t._pool = original
        assert r["type"] == "subagent_result"
        assert r["result"] == "done"


# ═══════════════════════════════════════════════════════════════════
# tool_loader
# ═══════════════════════════════════════════════════════════════════


class TestToolLoader:
    def test_plan_schema_count(self):
        schemas = get_tool_schemas("plan")
        assert len(schemas) == len(_PLAN_TOOL_NAMES)

    def test_execution_schema_count(self):
        schemas = get_tool_schemas("execution")
        assert len(schemas) == len(_ALL_TOOL_NAMES)

    def test_plan_names_correct(self):
        names = {
            s["function"]["name"]
            for s in get_tool_schemas("plan")
        }
        assert names == _PLAN_TOOL_NAMES

    def test_execution_includes_all_tools(self):
        names = {
            s["function"]["name"]
            for s in get_tool_schemas("execution")
        }
        assert names == _ALL_TOOL_NAMES

    def test_plan_excludes_write_tools(self):
        names = {
            s["function"]["name"]
            for s in get_tool_schemas("plan")
        }
        assert "bash" not in names
        assert "edit" not in names
        assert "write" not in names

    def test_execution_includes_write_tools(self):
        names = {
            s["function"]["name"]
            for s in get_tool_schemas("execution")
        }
        assert "bash" in names
        assert "edit" in names
        assert "write" in names

    def test_schemas_are_openai_format(self):
        for schema in get_tool_schemas("execution"):
            assert schema["type"] == "function"
            assert "function" in schema
            fn = schema["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_executor_keys_match_schema_names(self):
        for mode in ("plan", "execution"):
            schemas = get_tool_schemas(mode)
            executor = get_tool_executor(mode)
            schema_names = {
                s["function"]["name"]
                for s in schemas
            }
            assert set(executor.keys()) == (
                schema_names
            )

    def test_executor_values_are_callable(self):
        executor = get_tool_executor("execution")
        for name, fn in executor.items():
            assert callable(fn), (
                f"{name} executor is not callable"
            )

    def test_unknown_mode_defaults_to_plan(self):
        # Any non-"execution" value uses plan set
        schemas = get_tool_schemas("unknown")
        names = {
            s["function"]["name"] for s in schemas
        }
        assert names == _PLAN_TOOL_NAMES


# ═══════════════════════════════════════════════════════════════════
# Session mode and chat_auto
# ═══════════════════════════════════════════════════════════════════


def _make_session(mode="execution"):
    """Build a Session with a mock client."""
    from starry_lib.agents.base import BaseAgent
    from starry_lib.agents.session import Session

    agent = BaseAgent(
        name="assistant",
        label="Assistant",
        system_prompt="You help.",
        model="test-model",
    )
    client = MagicMock()
    sem = asyncio.Semaphore(1)
    return Session(
        session_id="test-session",
        agent=agent,
        client=client,
        provider_name="davy",
        semaphore=sem,
        mode=mode,
    )


class TestSessionMode:
    def test_default_mode_is_execution(self):
        s = _make_session()
        assert s.mode == "execution"

    def test_mode_set_to_plan(self):
        s = _make_session()
        s.mode = "plan"
        assert s.mode == "plan"

    def test_invalid_mode_raises_value_error(self):
        s = _make_session()
        with pytest.raises(ValueError, match="invalid"):
            s.mode = "invalid"

    def test_get_tool_schemas_execution(self):
        s = _make_session("execution")
        schemas = s.get_tool_schemas()
        names = {
            sc["function"]["name"] for sc in schemas
        }
        assert names == _ALL_TOOL_NAMES

    def test_get_tool_schemas_plan(self):
        s = _make_session("plan")
        schemas = s.get_tool_schemas()
        names = {
            sc["function"]["name"] for sc in schemas
        }
        assert names == _PLAN_TOOL_NAMES

    def test_get_tool_executor_returns_dict(self):
        s = _make_session()
        exc = s.get_tool_executor()
        assert isinstance(exc, dict)
        assert "bash" in exc

    def test_plan_executor_excludes_write_tools(self):
        s = _make_session("plan")
        exc = s.get_tool_executor()
        assert "bash" not in exc
        assert "edit" not in exc
        assert "write" not in exc

    def test_plan_task_executor_is_mode_wrapped(self):
        s = _make_session("plan")
        exc = s.get_tool_executor()
        assert "task" in exc
        assert exc["task"].__name__ == (
            "_task_with_mode"
        )

    def test_mode_change_updates_schemas(self):
        s = _make_session("execution")
        assert len(s.get_tool_schemas()) == len(
            _ALL_TOOL_NAMES
        )
        s.mode = "plan"
        assert len(s.get_tool_schemas()) == len(
            _PLAN_TOOL_NAMES
        )

    @pytest.mark.asyncio
    async def test_chat_auto_calls_chat_with_tools(self):
        """chat_auto delegates to chat_with_tools when
        schemas are available."""
        s = _make_session("execution")
        collected = []

        async def fake_cwt(user_input, tools, exc):
            collected.append(
                (user_input, len(tools))
            )
            from starry_lib.types import AgentEvent
            yield AgentEvent(
                type="done",
                session_id="test-session",
                data="ok",
            )

        with patch.object(
            s, "chat_with_tools", fake_cwt
        ):
            events = [
                e
                async for e in s.chat_auto("hello")
            ]

        assert len(collected) == 1
        prompt, n_tools = collected[0]
        assert prompt == "hello"
        assert n_tools == len(_ALL_TOOL_NAMES)

    @pytest.mark.asyncio
    async def test_chat_auto_falls_back_to_chat(self):
        """chat_auto uses chat() when no schemas returned."""
        s = _make_session("execution")
        chat_called = []

        async def fake_chat(user_input):
            chat_called.append(user_input)
            from starry_lib.types import AgentEvent
            yield AgentEvent(
                type="token",
                session_id="test-session",
                data="tok",
            )

        with patch.object(
            s, "get_tool_schemas", return_value=[]
        ):
            with patch.object(
                s, "chat", fake_chat
            ):
                events = [
                    e
                    async for e in s.chat_auto(
                        "hi"
                    )
                ]

        assert chat_called == ["hi"]
        assert events[0].type == "token"
