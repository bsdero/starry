"""Integration tests for native skills."""

import pytest

from starry_lib.tools import skill_loader


@pytest.fixture(autouse=True)
def reset_cache():
    skill_loader._cache = None
    yield
    skill_loader._cache = None


class TestNetworkScanSkill:
    @pytest.mark.asyncio
    async def test_loopback_returns_hosts_key(self):
        skills = skill_loader.load_skills()
        tool = next(
            (
                t
                for t in skills
                if t.SCHEMA["function"]["name"]
                == "network_scan"
            ),
            None,
        )
        assert tool is not None, "network_scan not loaded"
        result = await tool.execute(target="127.0.0.1")
        assert "hosts" in result

    @pytest.mark.asyncio
    async def test_loopback_result_is_list(self):
        skills = skill_loader.load_skills()
        tool = next(
            t
            for t in skills
            if t.SCHEMA["function"]["name"]
            == "network_scan"
        )
        result = await tool.execute(target="127.0.0.1")
        assert isinstance(result["hosts"], list)


class TestSysInfoSkill:
    @pytest.mark.asyncio
    async def test_all_sections_returned(self):
        skills = skill_loader.load_skills()
        tool = next(
            (
                t
                for t in skills
                if t.SCHEMA["function"]["name"]
                == "sys_info"
            ),
            None,
        )
        assert tool is not None, "sys_info not loaded"
        result = await tool.execute()
        assert isinstance(result, dict)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_single_section(self):
        skills = skill_loader.load_skills()
        tool = next(
            t
            for t in skills
            if t.SCHEMA["function"]["name"] == "sys_info"
        )
        result = await tool.execute(sections=["os"])
        assert "os" in result
        assert isinstance(result["os"], dict)

    @pytest.mark.asyncio
    async def test_cpu_section_has_expected_keys(self):
        skills = skill_loader.load_skills()
        tool = next(
            t
            for t in skills
            if t.SCHEMA["function"]["name"] == "sys_info"
        )
        result = await tool.execute(sections=["cpu"])
        assert "cpu" in result
        cpu = result["cpu"]
        assert isinstance(cpu, dict)
        assert len(cpu) > 0

    @pytest.mark.asyncio
    async def test_memory_section_has_total(self):
        skills = skill_loader.load_skills()
        tool = next(
            t
            for t in skills
            if t.SCHEMA["function"]["name"] == "sys_info"
        )
        result = await tool.execute(sections=["memory"])
        assert "memory" in result
        mem = result["memory"]
        assert "total_mb" in mem
