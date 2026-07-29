"""Tests for memory/working.py — Working Memory."""

import pytest
from memory.working import WorkingMemory


@pytest.fixture
def memory():
    return WorkingMemory()


@pytest.mark.asyncio
class TestWorkingMemory:
    async def test_store_and_retrieve(self, memory):
        await memory.store("key1", "value1")
        result = await memory.retrieve("key1")
        assert result == "value1"

    async def test_retrieve_nonexistent(self, memory):
        result = await memory.retrieve("nonexistent")
        assert result is None

    async def test_overwrite(self, memory):
        await memory.store("key", "old")
        await memory.store("key", "new")
        result = await memory.retrieve("key")
        assert result == "new"

    async def test_search_by_prefix(self, memory):
        await memory.store("alpha", 1)
        await memory.store("beta", 2)
        await memory.store("alpine", 3)

        results = await memory.search("alp")
        assert len(results) == 2

    async def test_search_limit(self, memory):
        await memory.store("a1", 1)
        await memory.store("a2", 2)
        await memory.store("a3", 3)

        results = await memory.search("a", limit=2)
        assert len(results) == 2

    async def test_delete_existing(self, memory):
        await memory.store("key", "value")
        assert await memory.delete("key") is True
        assert await memory.retrieve("key") is None

    async def test_delete_nonexistent(self, memory):
        assert await memory.delete("nonexistent") is False

    async def test_clear_all(self, memory):
        await memory.store("a", 1)
        await memory.store("b", 2)
        count = await memory.clear("*")
        assert count == 2
        assert await memory.retrieve("a") is None

    async def test_clear_pattern(self, memory):
        await memory.store("foo:1", 1)
        await memory.store("foo:2", 2)
        await memory.store("bar:1", 3)

        count = await memory.clear("foo:")
        assert count == 2
        assert await memory.retrieve("bar:1") == 3

    async def test_stats(self, memory):
        await memory.store("a", "hello")
        await memory.store("b", 42)
        stats = await memory.stats()
        assert stats.entry_count == 2
        assert stats.total_size_bytes > 0

    async def test_exists(self, memory):
        await memory.store("key", "val")
        assert await memory.exists("key") is True
        assert await memory.exists("nope") is False
