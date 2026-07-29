# Tool Cache Memory — SQLite-backed tool call cache
#
# Deduplicates identical tool calls to reduce API costs.
# Used by the ToolRegistry automatically when cache_policy is configured.

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats, MemoryTier


class ToolCacheMemory(MemoryProvider):
    """Cache for tool call results with TTL-based expiration.

    Key format: "tool:{tool_name}:{arg_hash}"
    TTL is set per cache policy (typically 1h-24h depending on data type).

    This tier is used by ToolRegistry.invoke() automatically.
    Components should not write to this tier directly.
    """

    def __init__(self, db_path: str = "memory/tool_cache.db"):
        self.db_path = str(Path(db_path).absolute())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._hit_count = 0
        self._miss_count = 0
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tool_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP,
                    expires_at TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_tool_cache_key ON tool_cache(key);
                CREATE INDEX IF NOT EXISTS idx_tool_cache_expires ON tool_cache(expires_at);
            """)

    @property
    def tier(self) -> MemoryTier:
        return MemoryTier.TOOL_CACHE

    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires_at = None
        if ttl is not None:
            expires_at = (datetime.now() + timedelta(seconds=ttl)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tool_cache (key, value, created_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (key, json.dumps(value), datetime.now().isoformat(), expires_at),
            )

    async def retrieve(self, key: str) -> Optional[Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM tool_cache WHERE key = ?",
                (key,),
            ).fetchone()

            if row is None:
                self._miss_count += 1
                return None

            value_json, expires_at = row

            # Check expiration
            if expires_at is not None:
                expire_time = datetime.fromisoformat(expires_at)
                if datetime.now() > expire_time:
                    conn.execute("DELETE FROM tool_cache WHERE key = ?", (key,))
                    self._miss_count += 1
                    return None

            self._hit_count += 1
            return json.loads(value_json)

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT key, value, created_at FROM tool_cache
                   WHERE key LIKE ? AND (expires_at IS NULL OR expires_at > ?)
                   LIMIT ?""",
                (f"%{query}%", datetime.now().isoformat(), limit),
            ).fetchall()

        return [
            MemoryEntry(
                key=row[0],
                value=json.loads(row[1]),
                tier=self.tier.value,
                created_at=row[2],
            )
            for row in rows
        ]

    async def delete(self, key: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM tool_cache WHERE key = ?", (key,))
            return cursor.rowcount > 0

    async def clear(self, pattern: str = "*") -> int:
        with sqlite3.connect(self.db_path) as conn:
            if pattern == "*":
                conn.execute("DELETE FROM tool_cache")
                # Also clean up expired entries
                count = conn.execute(
                    "DELETE FROM tool_cache WHERE expires_at < ?",
                    (datetime.now().isoformat(),),
                ).rowcount
                return count
            else:
                cursor = conn.execute(
                    "DELETE FROM tool_cache WHERE key LIKE ?", (f"{pattern}%",)
                )
                return cursor.rowcount

    async def stats(self) -> MemoryStats:
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM tool_cache").fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) FROM tool_cache WHERE expires_at < ?", (now,)
            ).fetchone()[0]
            size_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(value)), 0) FROM tool_cache"
            ).fetchone()
            total_size = size_row[0] if size_row else 0
        return MemoryStats(
            tier=self.tier.value,
            entry_count=total - expired,
            total_size_bytes=total_size,
            hit_count=self._hit_count,
            miss_count=self._miss_count,
        )
