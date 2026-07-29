"""Tests for memory/artifacts.py — Artifact Memory."""

import pytest
from memory.artifacts import ArtifactMemory


@pytest.fixture
def memory(tmp_path):
    return ArtifactMemory(directory=str(tmp_path / "artifacts"))


@pytest.mark.asyncio
class TestArtifactMemory:
    async def test_store_markdown(self, memory):
        await memory.store("report-001", {
            "content": "# Report\n\nAnalysis complete.",
            "type": "markdown",
        })
        result = await memory.retrieve("report-001")
        assert result is not None
        assert "# Report" in str(result)

    async def test_store_json_data(self, memory):
        await memory.store("data-001", {"scores": [0.8, 0.9], "type": "json"})
        result = await memory.retrieve("data-001")
        assert result is not None

    async def test_retrieve_nonexistent(self, memory):
        assert await memory.retrieve("nonexistent") is None

    async def test_search(self, memory):
        await memory.store("report-fundamentals", {
            "content": "Fundamental analysis result",
            "type": "markdown",
        })
        await memory.store("chart-price", {
            "content": "...",
            "type": "chart",
        })

        results = await memory.search("report")
        assert len(results) >= 1

    async def test_delete_with_metadata(self, memory):
        await memory.store("to-delete", {
            "content": "content",
            "type": "markdown",
        })
        assert await memory.delete("to-delete") is True

    async def test_clear(self, memory):
        await memory.store("a", {"content": "A", "type": "markdown"})
        await memory.store("b", {"content": "B", "type": "json"})
        count = await memory.clear("a")
        assert count == 1  # only "a" files, not "b"

    async def test_stats(self, memory):
        await memory.store("s1", {"content": "Hello World", "type": "markdown"})
        stats = await memory.stats()
        assert stats.entry_count == 1
        assert stats.total_size_bytes > 0
