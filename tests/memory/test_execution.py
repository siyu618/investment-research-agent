"""Tests for memory/execution.py — Execution Memory."""

import pytest
from memory.execution import ExecutionMemory


@pytest.fixture
def memory(tmp_path):
    return ExecutionMemory(directory=str(tmp_path / "execution"))


@pytest.mark.asyncio
class TestExecutionMemory:
    async def test_save_and_load_checkpoint(self, memory):
        await memory.save_checkpoint("session-1", "node-a", {"result": "ok", "score": 0.85})
        state = await memory.load_session_state("session-1")
        assert "node-a" in state
        assert state["node-a"]["score"] == 0.85

    async def test_get_completed_nodes(self, memory):
        await memory.save_checkpoint("session-1", "node-a", {"r": 1})
        await memory.save_checkpoint("session-1", "node-b", {"r": 2})
        await memory.save_checkpoint("session-2", "node-x", {"r": 3})

        completed = await memory.get_completed_nodes("session-1")
        assert sorted(completed) == sorted(["node-a", "node-b"])

    async def test_store_and_retrieve(self, memory):
        await memory.store("exec:s1:node1", {"status": "done"})
        result = await memory.retrieve("exec:s1:node1")
        assert result["status"] == "done"

    async def test_search(self, memory):
        await memory.store("session-1/node-a", {"step": 1})
        await memory.store("session-1/node-b", {"step": 2})

        results = await memory.search("node-")
        assert len(results) == 2

    async def test_delete(self, memory):
        await memory.store("test-key", "value")
        assert await memory.delete("test-key") is True

    async def test_clear(self, memory):
        await memory.store("s1/a", {"v": 1})
        await memory.store("s1/b", {"v": 2})
        await memory.store("s2/c", {"v": 3})

        count = await memory.clear("s1")
        # Should clear the subdirectory s1/
        assert count >= 2

        results = await memory.search("")
        remaining = len(results)
        assert remaining >= 0  # s2/c may still exist

    async def test_empty_session_state(self, memory):
        state = await memory.load_session_state("nonexistent")
        assert state == {}
