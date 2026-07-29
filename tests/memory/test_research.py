"""Tests for memory/research.py — Research Memory."""

import pytest
from memory.research import ResearchMemory


@pytest.fixture
def memory(tmp_path):
    return ResearchMemory(db_path=str(tmp_path / "research.db"))


@pytest.mark.asyncio
class TestResearchMemory:
    async def test_store_and_retrieve(self, memory):
        await memory.store("000001.SZ:20260728", {
            "stock_code": "000001.SZ",
            "score": 0.85,
            "strategy": "value",
            "reasoning": "Strong fundamentals",
        })
        result = await memory.retrieve("000001.SZ:20260728")
        assert result["score"] == 0.85
        assert result["stock_code"] == "000001.SZ"

    async def test_get_by_stock(self, memory):
        await memory.store("a:1", {"stock_code": "STOCK_A"})
        await memory.store("a:2", {"stock_code": "STOCK_A"})
        await memory.store("b:1", {"stock_code": "STOCK_B"})

        results = await memory.get_by_stock("STOCK_A")
        assert len(results) == 2

    async def test_search_by_strategy(self, memory):
        await memory.store("r1", {"stock_code": "A", "strategy": "value", "tags": ["strategy:value"]})
        await memory.store("r2", {"stock_code": "B", "strategy": "growth", "tags": ["strategy:growth"]})

        results = await memory.search("strategy:value")
        assert len(results) == 1

    async def test_delete(self, memory):
        await memory.store("key", {"data": "test"})
        assert await memory.delete("key") is True

    async def test_stats(self, memory):
        await memory.store("k1", {"data": "x" * 50})
        await memory.store("k2", {"data": "y" * 50})
        stats = await memory.stats()
        assert stats.entry_count == 2
        assert stats.total_size_bytes > 50
