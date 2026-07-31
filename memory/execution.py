# Execution Memory — Checkpoint-based resumability
#
# Stores step-by-step execution state for workflow resume capability.
# If a workflow is interrupted (timeout, crash), the next run can
# resume from the last completed checkpoint.

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats, MemoryTier


class ExecutionMemory(MemoryProvider):
    """Checkpoint-based execution state for workflow resumability.

    Each entry is a JSON file storing a single checkpoint.
    Checkpoints are written per completed node and can be
    read to skip already-completed steps on resume.

    File layout:
        memory/execution/{session_id}/
            checkpoint-{node_id}.json
            trace.json              (ordered list of completed steps)
    """

    def __init__(self, directory: str = "memory/execution"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def tier(self) -> MemoryTier:
        return MemoryTier.EXECUTION

    async def store(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Save a checkpoint.

        Key format: "{session_id}/{node_id}" or free-form.
        """
        filepath = self._key_to_path(key)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "key": key,
            "value": value,
            "created_at": datetime.now().isoformat(),
        }
        filepath.write_text(json.dumps(entry, indent=2, default=str))

    async def retrieve(self, key: str) -> Any | None:
        filepath = self._key_to_path(key)
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text())
            return data.get("value")
        except (json.JSONDecodeError, OSError):
            return None

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        results: list[MemoryEntry] = []
        for filepath in sorted(self.directory.rglob("*.json")):
            if len(results) >= limit:
                break
            if query.lower() in filepath.stem.lower():
                try:
                    data = json.loads(filepath.read_text())
                    results.append(MemoryEntry(
                        key=data.get("key", filepath.stem),
                        value=data.get("value"),
                        tier=self.tier.value,
                        created_at=data.get("created_at", ""),
                    ))
                except (json.JSONDecodeError, OSError):
                    pass
        return results

    async def delete(self, key: str) -> bool:
        filepath = self._key_to_path(key)
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    async def clear(self, pattern: str = "*") -> int:
        count = 0
        for filepath in list(self.directory.rglob("*.json")):
            if pattern == "*":
                filepath.unlink()
                count += 1
            elif filepath.stem.startswith(pattern) or pattern in str(filepath):
                filepath.unlink()
                count += 1
            elif (self.directory / pattern / filepath.name).exists():
                # Pattern is a session directory name
                if pattern in str(filepath.parent):
                    filepath.unlink()
                    count += 1
        # Clean up empty dirs
        for dirpath in sorted(self.directory.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                dirpath.rmdir()
        return count

    # ─── Resume-Specific API ─────────────────────────────────────────────

    async def save_checkpoint(self, session_id: str, node_id: str, state: dict) -> None:
        """Save a checkpoint for a specific node in a session."""
        key = f"{session_id}/{node_id}"
        await self.store(key, state)

    async def get_completed_nodes(self, session_id: str) -> list[str]:
        """Get all completed node IDs for a session (for resume)."""
        session_dir = self.directory / session_id
        if not session_dir.exists():
            return []
        return sorted([
            f.stem.replace("checkpoint-", "")
            for f in session_dir.glob("*.json")
            if f.stem != "trace"
        ])

    async def load_session_state(self, session_id: str) -> dict:
        """Load aggregate state for a session from all checkpoints."""
        state: dict = {}
        session_dir = self.directory / session_id
        if not session_dir.exists():
            return state
        for filepath in session_dir.glob("*.json"):
            try:
                data = json.loads(filepath.read_text())
                val = data.get("value", {})
                if isinstance(val, dict):
                    state[filepath.stem] = val
            except (json.JSONDecodeError, OSError):
                pass
        return state

    async def stats(self) -> MemoryStats:
        total_size = 0
        count = 0
        for filepath in self.directory.rglob("*.json"):
            count += 1
            total_size += filepath.stat().st_size
        return MemoryStats(
            tier=self.tier.value,
            entry_count=count,
            total_size_bytes=total_size,
        )

    def _key_to_path(self, key: str) -> Path:
        """Convert a key to a file path.

        Key "session-abc/node-1" → memory/execution/session-abc/node-1.json
        Key "simple-key" → memory/execution/simple-key.json
        """
        if "/" in key:
            parts = key.split("/")
            return self.directory / parts[0] / f"{parts[1]}.json"
        return self.directory / f"{key}.json"
