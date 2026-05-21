"""Unit tests for starry_lib.tools.skill_loader."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from starry_lib.tools import skill_loader
from starry_lib.tools.skill_loader import (
    SkillLoadError,
    SkillTool,
    load_skills,
)


def _make_skill_dir(
    tmp_path: Path,
    name: str,
    descriptor: dict | None = None,
    skill_src: str | None = None,
) -> Path:
    """Create a minimal skill directory under tmp_path."""
    d = tmp_path / name
    d.mkdir()
    if descriptor is not None:
        (d / "descriptor.json").write_text(
            json.dumps(descriptor), encoding="utf-8"
        )
    if skill_src is not None:
        (d / "skill.py").write_text(
            skill_src, encoding="utf-8"
        )
    return d


_VALID_DESCRIPTOR = {
    "type": "function",
    "function": {
        "name": "my_skill",
        "description": "test skill",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

_ASYNC_SKILL_SRC = textwrap.dedent("""\
    async def execute(**kwargs):
        return {"ok": True}
""")

_SYNC_SKILL_SRC = textwrap.dedent("""\
    def execute(**kwargs):
        return {"sync": True}
""")


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset skill_loader cache before each test."""
    skill_loader._cache = None
    yield
    skill_loader._cache = None


class TestLoadSkillsValid:
    def test_loads_async_skill(self, tmp_path):
        _make_skill_dir(
            tmp_path,
            "my_skill",
            _VALID_DESCRIPTOR,
            _ASYNC_SKILL_SRC,
        )
        with patch.object(
            skill_loader, "_SKILLS_DIR", tmp_path
        ):
            tools = load_skills()
        assert len(tools) == 1
        assert isinstance(tools[0], SkillTool)

    @pytest.mark.asyncio
    async def test_loads_sync_skill_wraps_async(
        self, tmp_path
    ):
        _make_skill_dir(
            tmp_path,
            "sync_skill",
            _VALID_DESCRIPTOR,
            _SYNC_SKILL_SRC,
        )
        with patch.object(
            skill_loader, "_SKILLS_DIR", tmp_path
        ):
            tools = load_skills()
        assert len(tools) == 1
        result = await tools[0].execute()
        assert result == {"sync": True}

    def test_schema_preserved(self, tmp_path):
        _make_skill_dir(
            tmp_path,
            "my_skill",
            _VALID_DESCRIPTOR,
            _ASYNC_SKILL_SRC,
        )
        with patch.object(
            skill_loader, "_SKILLS_DIR", tmp_path
        ):
            tools = load_skills()
        assert tools[0].SCHEMA == _VALID_DESCRIPTOR

    def test_execute_is_callable(self, tmp_path):
        _make_skill_dir(
            tmp_path,
            "my_skill",
            _VALID_DESCRIPTOR,
            _ASYNC_SKILL_SRC,
        )
        with patch.object(
            skill_loader, "_SKILLS_DIR", tmp_path
        ):
            tools = load_skills()
        assert callable(tools[0].execute)

    def test_result_cached(self, tmp_path):
        _make_skill_dir(
            tmp_path,
            "my_skill",
            _VALID_DESCRIPTOR,
            _ASYNC_SKILL_SRC,
        )
        with patch.object(
            skill_loader, "_SKILLS_DIR", tmp_path
        ):
            t1 = load_skills()
            t2 = load_skills()
        assert t1 is t2

    def test_skips_underscore_dirs(self, tmp_path):
        _make_skill_dir(
            tmp_path,
            "__pycache__",
            _VALID_DESCRIPTOR,
            _ASYNC_SKILL_SRC,
        )
        with patch.object(
            skill_loader, "_SKILLS_DIR", tmp_path
        ):
            tools = load_skills()
        assert tools == []

    def test_nonexistent_skills_dir_returns_empty(
        self, tmp_path
    ):
        missing = tmp_path / "no_such_dir"
        with patch.object(
            skill_loader, "_SKILLS_DIR", missing
        ):
            tools = load_skills()
        assert tools == []


class TestLoadSkillsErrors:
    def test_missing_descriptor_raises(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "skill.py").write_text(
            _ASYNC_SKILL_SRC
        )
        from starry_lib.tools.skill_loader import (
            _load_one,
        )
        with pytest.raises(SkillLoadError, match="descriptor"):
            _load_one(d)

    def test_missing_skill_py_raises(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "descriptor.json").write_text(
            json.dumps(_VALID_DESCRIPTOR)
        )
        from starry_lib.tools.skill_loader import (
            _load_one,
        )
        with pytest.raises(SkillLoadError, match="skill.py"):
            _load_one(d)

    def test_invalid_json_raises(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "descriptor.json").write_text("{bad json")
        (d / "skill.py").write_text(_ASYNC_SKILL_SRC)
        from starry_lib.tools.skill_loader import (
            _load_one,
        )
        with pytest.raises(SkillLoadError, match="JSON"):
            _load_one(d)

    def test_missing_execute_raises(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "descriptor.json").write_text(
            json.dumps(_VALID_DESCRIPTOR)
        )
        (d / "skill.py").write_text(
            "# no execute function\n"
        )
        from starry_lib.tools.skill_loader import (
            _load_one,
        )
        with pytest.raises(
            SkillLoadError, match="execute"
        ):
            _load_one(d)

    def test_broken_skill_skipped_others_loaded(
        self, tmp_path
    ):
        _make_skill_dir(
            tmp_path, "good", _VALID_DESCRIPTOR,
            _ASYNC_SKILL_SRC,
        )
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "skill.py").write_text(
            _ASYNC_SKILL_SRC
        )
        # no descriptor.json in bad/
        with patch.object(
            skill_loader, "_SKILLS_DIR", tmp_path
        ):
            tools = load_skills()
        names = [
            t.SCHEMA["function"]["name"]
            for t in tools
        ]
        assert "my_skill" in names
        assert len(tools) == 1
