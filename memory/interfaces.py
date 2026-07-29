# Memory System — Abstract Interfaces
#
# Defines the MemoryProvider ABC that all 7 memory tiers implement.
# This enables the CompositeMemoryManager to route operations transparently.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class MemoryTier(str, Enum):
    """All memory tiers in the system."""
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    RESEARCH = "research"
    TOOL_CACHE = "tool-cache"
    EXECUTION = "execution"
    ARTIFACTS = "artifacts"


@dataclass
class MemoryEntry:
    """A single entry retrieved from any memory tier."""
    key: str
    value: Any
    tier: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ttl: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    @property
    def size_bytes(self) -> int:
        """Approximate memory size of this entry."""
        import json
        try:
            return len(json.dumps(self.value))
        except Exception:
            return len(str(self.value))


@dataclass
class MemoryStats:
    """Aggregate statistics for a memory tier."""
    tier: str
    entry_count: int
    total_size_bytes: int
    hit_count: int = 0
    miss_count: int = 0


class MemoryProvider(ABC):
    """Abstract memory provider. All memory tiers implement this.

    Each tier stores and retrieves data with a consistent interface.
    Tiers differ in storage backend, persistence, and TTL semantics.
    """

    @property
    @abstractmethod
    def tier(self) -> MemoryTier:
        """Return the tier identifier."""
        ...

    @abstractmethod
    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value under the given key.

        Args:
            key: Unique identifier within this tier.
            value: Any JSON-serializable value.
            ttl: Time-to-live in seconds. None = tier default.
        """
        ...

    @abstractmethod
    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a value by key.

        Returns None if the key doesn't exist or has expired.
        """
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Search entries by query string.

        Each tier defines its own search semantics:
        - Dict-based: prefix match on keys
        - SQLite-based: LIKE query on keys/values
        - Markdown-based: full-text search in content
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a single entry. Returns True if existed."""
        ...

    @abstractmethod
    async def clear(self, pattern: str = "*") -> int:
        """Clear entries matching a pattern. Returns count cleared."""
        ...

    async def stats(self) -> MemoryStats:
        """Return statistics for this tier.

        Override for tier-specific metrics.
        """
        return MemoryStats(
            tier=self.tier.value,
            entry_count=0,
            total_size_bytes=0,
        )

    async def exists(self, key: str) -> bool:
        """Check if a key exists without retrieving its value."""
        return await self.retrieve(key) is not None
