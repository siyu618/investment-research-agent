"""Tests for memory/episodic.py — Episodic Memory."""

import pytest
from memory.episodic import EpisodicMemory


@pytest.fixture
def memory(tmp_path):
    return EpisodicMemory(db_path=str(tmp_path / "episodic.db"))


@pytest.mark.asyncio
class TestEpisodicMemory:
    async def test_store_and_retrieve(self, memory):
        await memory.store("session:abc", {"step": 1, "result": "ok"})
        result = await memory.retrieve("session:abc")
        assert result["step"] == 1
        assert result["result"] == "ok"

    async def test_retrieve_nonexistent(self, memory):
        assert await memory.retrieve("nope") is None

    async def test_overwrite(self, memory):
        await memory.store("key", {"v": 1})
        await memory.store("key", {"v": 2})
        result = await memory.retrieve("key")
        assert result["v"] == 2

    async def test_search_like(self, memory):
        await memory.store("session:001", {"id": 1})
        await memory.store("session:002", {"id": 2})
        await memory.store("other:003", {"id": 3})

        results = await memory.search("session:")
        assert len(results) == 2

    async def test_delete(self, memory):
        await memory.store("key", "val")
        assert await memory.delete("key") is True
        assert await memory.retrieve("key") is None

    async def test_clear_all(self, memory):
        await memory.store("a", 1)
        await memory.store("b", 2)
        count = await memory.clear("*")
        assert count == 2

    async def test_ttl_expiration(self, memory):
        await memory.store("key", "val", ttl=0)  # 0 TTL = immediate expire
        import asyncio
        await asyncio.sleep(0.01)
        result = await memory.retrieve("key")
        assert result is None

    async def test_stats(self, memory):
        await memory.store("a", "x" * 100)
        stats = await memory.stats()
        assert stats.entry_count == 1
        assert stats.total_size_bytes >= 100
