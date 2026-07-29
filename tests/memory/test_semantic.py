"""Tests for memory/semantic.py — Semantic Memory."""

import pytest
from memory.semantic import SemanticMemory


@pytest.fixture
def memory(tmp_path):
    return SemanticMemory(directory=str(tmp_path / "semantic"))


@pytest.mark.asyncio
class TestSemanticMemory:
    async def test_store_and_retrieve(self, memory):
        await memory.store("my-fact", {"content": "**Value:** 42", "type": "fact"})
        result = await memory.retrieve("my-fact")
        assert result is not None
        assert "42" in str(result)

    async def test_retrieve_nonexistent(self, memory):
        assert await memory.retrieve("nope") is None

    async def test_search_content(self, memory):
        await memory.store("fact-a", {"content": "Revenue grew 15%", "type": "fact"})
        await memory.store("fact-b", {"content": "Profit margin: 12%", "type": "fact"})

        results = await memory.search("Revenue")
        assert len(results) == 1

    async def test_delete(self, memory):
        await memory.store("key", {"content": "test"})
        assert await memory.delete("key") is True
        assert await memory.retrieve("key") is None

    async def test_clear(self, memory):
        await memory.store("a", {"content": "A"})
        await memory.store("b", {"content": "B"})
        count = await memory.clear("*")
        assert count == 2

    async def test_stats(self, memory):
        await memory.store("x", {"content": "Hello World"})
        stats = await memory.stats()
        assert stats.entry_count == 1
        assert stats.total_size_bytes > 0

    async def test_key_sanitization(self, memory):
        await memory.store("my/key:with spaces!", {"content": "test"})
        # Should be stored as a sanitized filename
        result = await memory.retrieve("my/key:with spaces!")
        assert result is not None
