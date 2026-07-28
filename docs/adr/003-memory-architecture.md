# Architecture Decision Record: Memory Architecture

**Status:** Accepted
**Decision:** #003
**Date:** 2026-07-28

## Context

The investment research agent needs to maintain state across multiple analysis steps within a session, and retain knowledge across sessions for continuity. The engineering-ai-standards memory policy defines three memory tiers (working, episodic, semantic), but leaves implementation choices open.

Key requirements:

1. **Working memory**: Current analysis context (plan, intermediate results, current skill state) — must persist across ReAct loop iterations within a single skill, and across multiple skill invocations within one analysis run.
2. **Episodic memory**: Past analysis sessions — needed for comparing results over time ("how did this stock's score change?") and for evaluation.
3. **Semantic memory**: Cross-session knowledge — investment preferences, strategy performance history, evaluation baselines.
4. **Observability**: Memory reads/writes should be logged for debugging and audit.

## Decision

**Decision:** We will implement a **three-tier memory system** using:

- **Working Memory**: Python `dict` managed by the `MemoryManager` class (in-memory, per-session)
- **Episodic Memory**: SQLite database with session, tool_call, and analysis_result tables (persistent, append-only)
- **Semantic Memory**: Markdown files with YAML frontmatter in `memory/` directory (persistent, mutable via file write)

The `MemoryManager` class provides a unified interface:
```python
class MemoryManager:
    # Working memory
    def set(key, value): ...
    def get(key): ...
    
    # Episodic memory
    def save_session(requirement, plan, status): ...
    def save_tool_call(session_id, step_id, tool_name, input, output, duration_ms, success): ...
    def get_recent_sessions(limit=5): ...
    
    # Semantic memory
    def save_recommendation(stock, score, reasoning): ...
    def get_recommendations(limit=5): ...
    def get_recommendation_by_stock(stock_code): ...
```

## Rationale

- **Working memory dict**: Simplest possible implementation with zero serialization overhead. The entire analysis session fits in a few KB of structured data, well within memory constraints. Dict provides O(1) read/write.
- **SQLite for episodic**: Transactional, concurrent-read safe, zero-dependency (stdlib), and queryable with SQL. Analysis histories naturally form relational data (sessions → tool_calls → results). No external database server needed.
- **Markdown files for semantic**: Aligns with the engineering-ai-standards memory file format. Human-readable and editable. Git-trackable for version history. No additional parsing tooling needed — standard YAML frontmatter + markdown body.
- **Unified MemoryManager interface**: The Executor, Verifier, and Report Generator don't need to know which storage backend is used. The interface abstracts storage decisions.

## Consequences

### Positive

- Working memory is fast (no I/O) and trivially simple.
- Episodic memory supports complex queries (`SELECT * FROM analyses WHERE stock_code = ? ORDER BY created_at DESC`).
- Semantic memory is human-readable and git-manageable.
- The three-tier design directly implements the engineering-ai-standards memory policy without custom infrastructure.
- Memory can be reset or archived by deleting files/database — useful for evaluation runs.

### Negative

- SQLite has limited concurrency (single writer). Acceptable for a reference project, but would need migration for multi-user scenarios.
- Markdown files don't support atomic cross-file updates. If a write fails midway, some files may be inconsistent. Mitigating with write-then-rename pattern.
- No vector search for semantic memory. Retrieval is by explicit key or list scan. Acceptable for ≤100 recommendations.

### Neutral

- Memory format is project-specific but designed to be convertible. Export to JSON/Parquet for analysis is straightforward.
- The SQLite schema may need migration as the project evolves. Using raw SQL (no ORM) means manual migration scripts.

## Alternatives Considered

### Alternative 1: Single SQLite for all memory

- **Description**: Both episodic and semantic memory in SQLite. Working memory in a `sessions` table.
- **Pros**: Single query interface; atomic updates across memory types; simpler backup.
- **Cons**: Semantic memory loses human readability; git history not meaningful; harder to inspect/modify manually.
- **Why rejected**: Semantic memory is git-tracked documentation as much as data — markdown format is intentionally human-first.

### Alternative 2: Vector database (Chroma/Qdrant)

- **Description**: Embedding-based retrieval for episodic and semantic memory.
- **Pros**: Semantic search over past analyses; similarity-based recommendation retrieval.
- **Cons**: Infrastructure dependency; embedding costs; over-engineering for current scale.
- **Why rejected**: Deferred as a future optimization. The file + SQLite approach handles ≤1000 sessions without issue.

### Alternative 3: Redis for working memory

- **Description**: External key-value store for working memory.
- **Pros**: Shared memory across processes; built-in TTL; persistence optional.
- **Cons**: Adds a server dependency; the agent runs as a single process — shared memory is unnecessary.
- **Why rejected**: Simple in-memory dict is sufficient for a single-process agent.

## Related Decisions

- [ADR-001: Agent Architecture](001-agent-architecture.md) (MemoryManager is used by Executor)
- engineering-ai-standards: `runtime/memory-policy.md`

## Notes

Memory capacity limits:
- Working memory: ~100 KB per session (analysis context, intermediate results). Freed on session end.
- Episodic memory: ~1 MB per 100 sessions (estimated). SQLite is efficient for this scale.
- Semantic memory: ~10 KB per recommendation. Aim to keep ≤100 recommendations (≤1 MB total) to maintain fast list scans.
