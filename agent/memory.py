# Agent Memory — Three-tier memory system (working, episodic, semantic)

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class MemoryManager:
    """Unified interface for the three-tier memory system.

    Working memory: in-memory dict (current session context)
    Episodic memory: SQLite database (past sessions, tool calls)
    Semantic memory: Markdown files (recommendations, preferences)
    """

    def __init__(self, data_dir: str = "memory"):
        self.data_dir = Path(data_dir)
        self.short_term_dir = self.data_dir / "short-term"
        self.long_term_dir = self.data_dir / "long-term"
        self.db_path = self.data_dir / "episodic.db"

        # Working memory (in-memory, per-session)
        self._working: dict = {}

        # Ensure directories exist
        self.short_term_dir.mkdir(parents=True, exist_ok=True)
        self.long_term_dir.mkdir(parents=True, exist_ok=True)

        # Initialize episodic DB
        self._init_db()

    def _init_db(self):
        """Create episodic memory tables if they don't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS analysis_sessions (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    user_requirement TEXT,
                    plan JSON,
                    status TEXT DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES analysis_sessions(id),
                    step_id TEXT,
                    tool_name TEXT,
                    input JSON,
                    output JSON,
                    duration_ms INTEGER,
                    success BOOLEAN,
                    created_at TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES analysis_sessions(id),
                    skill TEXT,
                    stock_code TEXT,
                    score REAL,
                    confidence REAL,
                    reasoning TEXT,
                    risk_factors JSON,
                    created_at TIMESTAMP
                );
            """)

    # ─── Working Memory ────────────────────────────────────────────────

    def set(self, key: str, value):
        """Write to working memory."""
        self._working[key] = value

    def get(self, key: str, default=None):
        """Read from working memory."""
        return self._working.get(key, default)

    def clear_working(self):
        """Clear working memory (new session)."""
        self._working.clear()

    # ─── Episodic Memory ───────────────────────────────────────────────

    def save_session(self, session_id: str, requirement: str, plan: dict):
        """Record a new analysis session."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO analysis_sessions (id, created_at, user_requirement, plan) VALUES (?, ?, ?, ?)",
                (session_id, datetime.now().isoformat(), requirement, json.dumps(plan)),
            )

    def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        """Retrieve recent analysis sessions."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM analysis_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── Semantic Memory ──────────────────────────────────────────────

    def save_recommendation(
        self,
        stock_code: str,
        score: float,
        reasoning: str,
        strategy: str = "mixed",
    ):
        """Save an investment recommendation as a semantic memory file."""
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"recommendation-{stock_code}-{date_str}.md"
        filepath = self.long_term_dir / filename

        content = f"""---
name: recommendation-{stock_code}-{date_str}
description: Investment recommendation for {stock_code}
metadata:
  type: recommendation
  score: {score}
  strategy: {strategy}
  created: {datetime.now().isoformat()}
---

**Stock:** {stock_code}
**Composite Score:** {score}
**Reasoning:** {reasoning}
"""
        filepath.write_text(content)

    def get_recommendations(self, limit: int = 5) -> list[dict]:
        """List recent recommendations from semantic memory."""
        files = sorted(self.long_term_dir.glob("*.md"), reverse=True)[:limit]
        recommendations = []
        for f in files:
            # Parse frontmatter and body (simplified)
            content = f.read_text()
            recommendations.append({
                "file": f.name,
                "content": content,
            })
        return recommendations
