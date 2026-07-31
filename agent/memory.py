# Agent Memory — CompositeMemoryManager facade
#
# Unified interface over all 7 memory tiers.
# Routes operations to the appropriate tier based on key conventions.
# Backward-compatible with the previous MemoryManager API.

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from memory.artifacts import ArtifactMemory
from memory.episodic import EpisodicMemory
from memory.execution import ExecutionMemory
from memory.interfaces import MemoryEntry, MemoryProvider, MemoryStats
from memory.research import ResearchMemory
from memory.semantic import SemanticMemory
from memory.tool_cache import ToolCacheMemory
from memory.working import WorkingMemory


class CompositeMemoryManager:
    """Unified facade over all 7 memory tiers.

    Routes operations to the right tier:
    - set/get with key prefix "" → working (backward compat)
    - set/get with prefix "episodic:" → episodic
    - set/get with prefix "semantic:" → semantic
    - set/get with prefix "research:" → research
    - set/get with prefix "tool:" → tool_cache (for ToolRegistry)
    - set/get with prefix "exec:" → execution
    - set/get with prefix "artifact:" → artifacts

    Legacy API (save_session, save_recommendation, etc.)
    continues to work and routes to the appropriate tier.
    """

    def __init__(self, data_dir: str = "memory"):
        self.data_dir = Path(data_dir)

        # 7 memory tiers
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(
            db_path=str(self.data_dir / "episodic.db")
        )
        self.semantic = SemanticMemory(
            directory=str(self.data_dir / "semantic")
        )
        self.research = ResearchMemory(
            db_path=str(self.data_dir / "research.db")
        )
        self.tool_cache = ToolCacheMemory(
            db_path=str(self.data_dir / "tool_cache.db")
        )
        self.execution = ExecutionMemory(
            directory=str(self.data_dir / "execution")
        )
        self.artifacts = ArtifactMemory(
            directory=str(self.data_dir / "artifacts")
        )

        # Tier lookup by prefix
        self._tiers: dict[str, MemoryProvider] = {
            "": self.working,
            "working:": self.working,
            "episodic:": self.episodic,
            "semantic:": self.semantic,
            "research:": self.research,
            "tool:": self.tool_cache,
            "exec:": self.execution,
            "artifact:": self.artifacts,
        }

    # ─── Unified Store/Retrieve ─────────────────────────────────────────

    async def store(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store in the appropriate tier based on key prefix."""
        tier, inner_key = self._resolve_tier(key)
        await tier.store(inner_key, value, ttl)

    async def retrieve(self, key: str) -> Any | None:
        """Retrieve from the appropriate tier based on key prefix."""
        tier, inner_key = self._resolve_tier(key)
        return await tier.retrieve(inner_key)

    async def delete(self, key: str) -> bool:
        tier, inner_key = self._resolve_tier(key)
        return await tier.delete(inner_key)

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Search across all tiers. Returns tier-tagged results."""
        all_results = []
        for tier in self._tiers.values():
            results = await tier.search(query, limit)
            all_results.extend(results)
        # Sort by created_at desc, limit total
        all_results.sort(
            key=lambda e: e.created_at or "",
            reverse=True,
        )
        return all_results[:limit]

    async def clear(self, pattern: str = "*") -> int:
        """Clear entries across all tiers."""
        total = 0
        for prefix, tier in self._tiers.items():
            if prefix == "":
                continue  # skip working (cleared separately)
            total += await tier.clear(pattern)
        return total

    async def stats(self) -> dict[str, MemoryStats]:
        """Get stats for all tiers."""
        return {tier.tier.value: await tier.stats() for tier in self._tiers.values()}

    # ─── Legacy Backward Compat API ─────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Legacy sync set → working memory (backward compat).

        Operates directly on the WorkingMemory dict to avoid
        event-loop issues in sync contexts.
        """
        self.working._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Legacy sync get → working memory (backward compat)."""
        return self.working._data.get(key, default)

    def clear_working(self) -> None:
        """Clear working memory for a new session."""
        self.working._data.clear()

    async def save_session(self, session_id: str, requirement: str, plan: dict) -> None:
        """Record a new analysis session in episodic memory."""
        key = f"episodic:session:{session_id}"
        await self.store(key, {
            "session_id": session_id,
            "requirement": requirement,
            "plan": plan,
            "created_at": datetime.now().isoformat(),
            "status": "completed",
        })

    async def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        """Retrieve recent analysis sessions from episodic memory."""
        results = await self.episodic.search("session:", limit)
        sessions = []
        for r in results:
            val = r.value
            if isinstance(val, dict):
                sessions.append(val)
        return sessions

    async def save_recommendation(
        self, stock_code: str, score: float, reasoning: str, strategy: str = "mixed",
    ) -> None:
        """Save an investment recommendation to semantic memory."""
        date_str = datetime.now().strftime("%Y%m%d")
        key = f"semantic:recommendation-{stock_code}-{date_str}"
        stock_key = f"research:{stock_code}:{date_str}"
        await self.store(key, {
            "type": "recommendation",
            "score": score,
            "strategy": strategy,
            "reasoning": reasoning,
        })
        await self.store(stock_key, {
            "stock_code": stock_code,
            "score": score,
            "strategy": strategy,
            "reasoning": reasoning,
            "tags": [f"stock:{stock_code}", f"strategy:{strategy}"],
        })

    async def get_recommendations(self, limit: int = 5) -> list[dict]:
        """List recent recommendations from semantic memory."""
        results = await self.semantic.search("recommendation", limit)
        recs = []
        for r in results:
            val = r.value
            if isinstance(val, dict):
                recs.append(val)
        return recs

    # ─── Tier Resolution ────────────────────────────────────────────────

    def _resolve_tier(self, key: str) -> tuple[MemoryProvider, str]:
        """Resolve key prefix to a memory tier and inner key."""
        for prefix, tier in self._tiers.items():
            if prefix and key.startswith(prefix):
                return tier, key[len(prefix):]
        return self.working, key


# Short alias
MemoryManager = CompositeMemoryManager
