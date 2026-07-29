# Research Memory — SQLite-backed long-term research storage
#
# Preserves analysis results across sessions in a structured,
# queryable format. Unlike Episodic (full session dump), this
# tier stores curated research facts: scores, rankings, reasoning.

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats, MemoryTier


class ResearchMemory(MemoryProvider):
    """Persistent research result storage.

    Each entry stores a structured analysis result keyed by
    stock_code + date for easy cross-session comparison.

    Schema:
        key: "research:{stock_code}:{date}" or free-form
        value: JSON dict with scores, reasoning, risk factors
    """

    def __init__(self, db_path: str = "memory/research.db"):
        self.db_path = str(Path(db_path).absolute())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._hit_count = 0
        self._miss_count = 0
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS research (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP,
                    ttl_seconds INTEGER DEFAULT NULL,
                    tags TEXT DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_research_key ON research(key);
                CREATE INDEX IF NOT EXISTS idx_research_tags ON research(tags);
            """)

    @property
    def tier(self) -> MemoryTier:
        return MemoryTier.RESEARCH

    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        tags = []
        if isinstance(value, dict):
            tags = value.get("tags", [])
            if "stock_code" in value:
                tags.append(f"stock:{value['stock_code']}")
            if "strategy" in value:
                tags.append(f"strategy:{value['strategy']}")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO research (key, value, created_at, ttl_seconds, tags)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, json.dumps(value), datetime.now().isoformat(), ttl, json.dumps(tags)),
            )

    async def retrieve(self, key: str) -> Optional[Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM research WHERE key = ?", (key,),
            ).fetchone()
            if row is None:
                self._miss_count += 1
                return None
            self._hit_count += 1
            return json.loads(row[0])

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT key, value, created_at FROM research
                   WHERE key LIKE ? OR tags LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
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
            cursor = conn.execute("DELETE FROM research WHERE key = ?", (key,))
            return cursor.rowcount > 0

    async def clear(self, pattern: str = "*") -> int:
        with sqlite3.connect(self.db_path) as conn:
            if pattern == "*":
                cursor = conn.execute("DELETE FROM research")
            else:
                cursor = conn.execute(
                    "DELETE FROM research WHERE key LIKE ?", (f"{pattern}%",)
                )
            return cursor.rowcount

    async def get_by_stock(self, stock_code: str, limit: int = 5) -> list[MemoryEntry]:
        """Convenience: get all research entries for a stock code."""
        return await self.search(f"stock:{stock_code}", limit)

    async def stats(self) -> MemoryStats:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(value)), 0) FROM research"
            ).fetchone()
            count, total_size = row or (0, 0)
        return MemoryStats(
            tier=self.tier.value,
            entry_count=count,
            total_size_bytes=total_size,
            hit_count=self._hit_count,
            miss_count=self._miss_count,
        )
