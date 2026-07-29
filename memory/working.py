# Working Memory — In-memory dict, session-scoped
#
# Fastest tier. No persistence. Cleared at session end.

from __future__ import annotations

from typing import Any, Optional

from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats, MemoryTier


class WorkingMemory(MemoryProvider):
    """In-memory key-value store for current session data.

    Characteristics:
    - O(1) read/write
    - Volatile: lost when session ends
    - No serialization overhead
    - Suitable for: current plan, intermediate results, step state
    """

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._hit_count = 0
        self._miss_count = 0

    @property
    def tier(self) -> MemoryTier:
        return MemoryTier.WORKING

    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store in working memory. TTL is ignored (session-scoped)."""
        self._data[key] = value

    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve from working memory."""
        value = self._data.get(key)
        if value is not None:
            self._hit_count += 1
        else:
            self._miss_count += 1
        return value

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Search keys by prefix. 'foo' matches 'foobar'."""
        results = []
        for key, value in self._data.items():
            if query.lower() in key.lower():
                results.append(MemoryEntry(
                    key=key,
                    value=value,
                    tier=self.tier.value,
                ))
                if len(results) >= limit:
                    break
        return results

    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def clear(self, pattern: str = "*") -> int:
        """Clear all keys matching pattern.

        * = clear all. Otherwise prefix match.
        """
        if pattern == "*":
            count = len(self._data)
            self._data.clear()
            return count
        keys_to_delete = [k for k in self._data if k.startswith(pattern)]
        for k in keys_to_delete:
            del self._data[k]
        return len(keys_to_delete)

    async def stats(self) -> MemoryStats:
        import json
        try:
            total_size = len(json.dumps(self._data))
        except Exception:
            total_size = 0
        return MemoryStats(
            tier=self.tier.value,
            entry_count=len(self._data),
            total_size_bytes=total_size,
            hit_count=self._hit_count,
            miss_count=self._miss_count,
        )
