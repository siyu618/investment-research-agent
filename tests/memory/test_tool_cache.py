"""Tests for memory/tool_cache.py — Tool Cache Memory."""

import pytest
from memory.tool_cache import ToolCacheMemory


@pytest.fixture
def memory(tmp_path):
    return ToolCacheMemory(db_path=str(tmp_path / "tool_cache.db"))


@pytest.mark.asyncio
class TestToolCacheMemory:
    async def test_store_and_retrieve(self, memory):
        await memory.store("tool:get_stock_basic:abc123", [{"ts_code": "000001.SZ"}])
        result = await memory.retrieve("tool:get_stock_basic:abc123")
        assert result[0]["ts_code"] == "000001.SZ"

    async def test_cache_miss(self, memory):
        result = await memory.retrieve("tool:nonexistent:xxx")
        assert result is None

    async def test_ttl_expiration(self, memory):
        await memory.store("tool:test:x1", "data", ttl=0)
        import asyncio
        await asyncio.sleep(0.01)
        result = await memory.retrieve("tool:test:x1")
        assert result is None

    async def test_auto_cleanup_expired(self, memory):
        """Expired entries should not block retrieval of fresh ones."""
        await memory.store("tool:test:old", "old", ttl=0)
        await memory.store("tool:test:new", "new", ttl=3600)

        import asyncio
        await asyncio.sleep(0.01)

        old_result = await memory.retrieve("tool:test:old")
        new_result = await memory.retrieve("tool:test:new")
        assert old_result is None
        assert new_result == "new"

    async def test_search(self, memory):
        await memory.store("tool:a:1", "val1", ttl=3600)
        await memory.store("tool:b:2", "val2", ttl=3600)

        results = await memory.search("tool:a")
        assert len(results) == 1

    async def test_delete(self, memory):
        await memory.store("tool:test:k", "v")
        assert await memory.delete("tool:test:k") is True
        assert await memory.retrieve("tool:test:k") is None

    async def test_stats(self, memory):
        await memory.store("tool:t1:k", "x" * 100, ttl=3600)
        stats = await memory.stats()
        assert stats.entry_count == 1
