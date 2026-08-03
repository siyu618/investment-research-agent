"""Tests for memory/research.py — Research Memory."""

import sqlite3

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

    async def test_get_by_subject_company(self, memory):
        """Company-level knowledge accumulates and is retrievable."""
        await memory.store("r1", {
            "company": "600519.SH", "score": 0.85,
            "reasoning": "strong brand", "subject_type": "company",
            "subject": "600519.SH",
        })
        results = await memory.get_by_subject("company", "600519.SH")
        assert len(results) == 1
        assert results[0].value["score"] == 0.85

    async def test_get_by_subject_industry(self, memory):
        """Industry-level knowledge accumulates across companies."""
        await memory.store("r1", {
            "industry": "白酒", "theme": "消费",
            "subject_type": "industry", "subject": "白酒",
        })
        await memory.store("r2", {
            "industry": "白酒", "theme": "消费",
            "subject_type": "industry", "subject": "白酒",
        })
        results = await memory.get_by_subject("industry", "白酒")
        assert len(results) == 2

    async def test_subject_tagging_at_store(self, memory):
        """subject_type + subject are tagged for search."""
        await memory.store("r1", {
            "subject_type": "theme", "subject": "AI",
            "note": "AI sector momentum",
        })
        results = await memory.get_by_subject("theme", "AI")
        assert len(results) == 1
        assert "AI" in results[0].value["note"]

    async def test_unicode_subject_search_roundtrip(self, memory):
        """Chinese subjects survive the store→search roundtrip.

        Regression: json.dumps defaults to ensure_ascii=True, which escapes
        Chinese tags to '\\uXXXX' and silently breaks LIKE-based search.
        """
        await memory.store("r1", {
            "subject_type": "industry", "subject": "白酒",
            "note": "白酒行业龙头研究",
        })
        # Search by the raw Chinese string — must match after the fix.
        results = await memory.search("industry:白酒")
        assert len(results) == 1
        assert results[0].value["note"] == "白酒行业龙头研究"
        # And the stored tags must be human-readable (not ASCII-escaped).
        with sqlite3.connect(memory.db_path) as conn:
            row = conn.execute(
                "SELECT tags FROM research WHERE key = 'r1'"
            ).fetchone()
        assert "白酒" in row[0]
