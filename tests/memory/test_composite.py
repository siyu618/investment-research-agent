"""Tests for agent/memory.py — CompositeMemoryManager."""

import pytest
from agent.memory import CompositeMemoryManager


@pytest.fixture
def memory(tmp_path):
    m = CompositeMemoryManager(data_dir=str(tmp_path))
    yield m


@pytest.mark.asyncio
class TestCompositeMemoryManager:
    async def test_working_tier_by_default(self, memory):
        await memory.store("key1", "value1")
        result = await memory.retrieve("key1")
        assert result == "value1"

    async def test_episodic_tier_by_prefix(self, memory):
        await memory.store("episodic:session:abc", {"status": "done"})
        result = await memory.retrieve("episodic:session:abc")
        assert result["status"] == "done"

    async def test_semantic_tier_by_prefix(self, memory):
        await memory.store("semantic:fact:xyz", {"content": "test fact", "type": "fact"})
        result = await memory.retrieve("semantic:fact:xyz")
        assert result is not None

    async def test_research_tier_by_prefix(self, memory):
        await memory.store("research:000001:20260728", {"score": 0.9})
        result = await memory.retrieve("research:000001:20260728")
        assert result["score"] == 0.9

    async def test_tool_cache_tier_by_prefix(self, memory):
        await memory.store("tool:get_data:hash", {"data": [1, 2, 3]})
        result = await memory.retrieve("tool:get_data:hash")
        assert result["data"] == [1, 2, 3]

    async def test_execution_tier_by_prefix(self, memory):
        await memory.store("exec:session-1:node-a", {"result": "ok"})
        result = await memory.retrieve("exec:session-1:node-a")
        assert result["result"] == "ok"

    async def test_artifact_tier_by_prefix(self, memory):
        await memory.store("artifact:my-report", {
            "content": "# Report",
            "type": "markdown",
        })
        result = await memory.retrieve("artifact:my-report")
        assert result is not None

    async def test_search_cross_tier(self, memory):
        await memory.store("working-key", "working value")
        await memory.store("episodic:test-key", {"data": "episodic value"})
        await memory.store("semantic:other-key", {"content": "semantic value", "type": "fact"})

        results = await memory.search("value")
        assert len(results) >= 1

    async def test_delete(self, memory):
        await memory.store("to-delete", "value")
        assert await memory.delete("to-delete") is True
        assert await memory.retrieve("to-delete") is None

    async def test_stats_all_tiers(self, memory):
        await memory.store("a", 1)
        await memory.store("episodic:s1", {"id": 1})
        await memory.store("semantic:f1", {"content": "fact", "type": "fact"})

        stats = await memory.stats()
        assert len(stats) >= 3  # at least 3 tiers have entries

    async def test_legacy_sync_api(self, memory):
        """Backward compat: sync set/get on working memory."""
        memory.set("legacy-key", "legacy-value")
        result = memory.get("legacy-key")
        assert result == "legacy-value"

    async def test_legacy_sync_get_default(self, memory):
        result = memory.get("nonexistent", "default")
        assert result == "default"

    async def test_legacy_clear_working(self, memory):
        memory.set("temp", "value")
        memory.clear_working()
        assert memory.get("temp") is None

    async def test_save_and_get_recommendations(self, memory):
        await memory.save_recommendation("000001.SZ", 0.85, "Good value", "value")
        recs = await memory.get_recommendations(limit=1)
        assert len(recs) >= 1

    async def test_save_and_get_sessions(self, memory):
        await memory.save_session("session-1", "Find value stocks", {"steps": []})
        sessions = await memory.get_recent_sessions(limit=1)
        assert len(sessions) >= 1
