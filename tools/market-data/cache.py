# Local market data cache — reduces redundant Tushare API calls

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class DataCache:
    """Local SQLite cache for Tushare market data.

    Reduces API calls by caching frequently accessed data.
    TTL varies by data type:
    - Stock basics: 24h
    - Daily prices: 4h (refreshed after market close)
    - Financial statements: never (immutable historical data)
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".tushare_cache" / "cache.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT,
                    created_at TIMESTAMP,
                    ttl_seconds INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_cache_key ON cache(cache_key);
            """)

    def get(self, cache_key: str) -> Optional[any]:
        """Get cached data if still fresh."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data, created_at, ttl_seconds FROM cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

            if row is None:
                return None

            data, created_at, ttl = row
            created = datetime.fromisoformat(created_at)

            if datetime.now() - created > timedelta(seconds=ttl):
                conn.execute("DELETE FROM cache WHERE cache_key = ?", (cache_key,))
                return None

            return json.loads(data)

    def set(self, cache_key: str, data: any, ttl_seconds: int = 3600):
        """Cache data with TTL."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache (cache_key, data, created_at, ttl_seconds)
                   VALUES (?, ?, ?, ?)""",
                (cache_key, json.dumps(data), datetime.now().isoformat(), ttl_seconds),
            )
