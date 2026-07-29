# Episodic Memory — SQLite-backed session history
#
# Stores past analysis sessions, tool calls, and intermediate results.
# Append-only. Queryable by session_id.

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats, MemoryTier


class EpisodicMemory(MemoryProvider):
    """Persistent SQLite store for session history.

    Characteristics:
    - Append-only: sessions are never modified
    - Queryable by session_id, time range, or content
    - Structured tables for sessions, tool_calls, analysis_results
    - Survives process restarts
    """

    def __init__(self, db_path: str = "memory/episodic.db"):
        self.db_path = str(Path(db_path).absolute())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._hit_count = 0
        self._miss_count = 0
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP,
                    ttl_seconds INTEGER DEFAULT NULL,
                    metadata TEXT DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_episodes_key ON episodes(key);
                CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);
            """)

    @property
    def tier(self) -> MemoryTier:
        return MemoryTier.EPISODIC

    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO episodes (key, value, created_at, ttl_seconds)
                   VALUES (?, ?, ?, ?)""",
                (key, json.dumps(value), datetime.now().isoformat(), ttl),
            )

    async def retrieve(self, key: str) -> Optional[Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value, ttl_seconds, created_at FROM episodes WHERE key = ?",
                (key,),
            ).fetchone()

            if row is None:
                self._miss_count += 1
                return None

            value_json, ttl, created_at = row
            if ttl is not None:
                created = datetime.fromisoformat(created_at)
                if (datetime.now() - created).total_seconds() > ttl:
                    conn.execute("DELETE FROM episodes WHERE key = ?", (key,))
                    self._miss_count += 1
                    return None

            self._hit_count += 1
            return json.loads(value_json)

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT key, value, created_at FROM episodes WHERE key LIKE ? LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()

        results = []
        for key, value_json, created_at in rows:
            results.append(MemoryEntry(
                key=key,
                value=json.loads(value_json),
                tier=self.tier.value,
                created_at=created_at,
            ))
        return results

    async def delete(self, key: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM episodes WHERE key = ?", (key,))
            return cursor.rowcount > 0

    async def clear(self, pattern: str = "*") -> int:
        with sqlite3.connect(self.db_path) as conn:
            if pattern == "*":
                cursor = conn.execute("DELETE FROM episodes")
            else:
                cursor = conn.execute(
                    "DELETE FROM episodes WHERE key LIKE ?", (f"{pattern}%",)
                )
            return cursor.rowcount

    async def stats(self) -> MemoryStats:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(value)), 0) FROM episodes"
            ).fetchone()
            count, total_size = row or (0, 0)
        return MemoryStats(
            tier=self.tier.value,
            entry_count=count,
            total_size_bytes=total_size,
            hit_count=self._hit_count,
            miss_count=self._miss_count,
        )
