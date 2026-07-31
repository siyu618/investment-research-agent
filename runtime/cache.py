# Runtime Framework — Generic Cache Provider
#
# Provides TTL-based caching for tool results, skill outputs,
# and any other runtime data that benefits from caching.

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class CacheProvider(ABC):
    """Abstract cache provider interface."""

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int) -> None: ...

    @abstractmethod
    async def invalidate(self, pattern: str) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...


class TTLCache(CacheProvider):
    """Simple in-memory TTL cache.

    For production use, replace with Redis or SQLite-backed cache.
    """

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = time.monotonic() + ttl
        self._store[key] = (value, expires_at)

    async def invalidate(self, pattern: str) -> None:
        """Invalidate keys matching a prefix pattern.

        pattern: "get_stock_basic:" → invalidates all keys with that prefix
        """
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            self._store = {
                k: v for k, v in self._store.items()
                if not k.startswith(prefix)
            }
        else:
            self._store.pop(pattern, None)

    async def clear(self) -> None:
        self._store.clear()


class CachePolicy:
    """Cache policy configuration for tools and skills."""

    def __init__(
        self,
        ttl: int = 0,
        key_prefix: str = "",
        enabled: bool = True,
    ):
        self.ttl = ttl
        self.key_prefix = key_prefix
        self.enabled = enabled

    def build_key(self, namespace: str, *args) -> str:
        """Build a cache key from namespace and arguments."""
        key = f"{namespace}:{':'.join(str(a) for a in args)}"
        return key
