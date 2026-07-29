# Architecture Decision Record: Memory Expansion Architecture

**Status:** Proposed
**Decision:** #010
**Date:** 2026-07-29

## Context

The current memory system has three tiers (Working, Episodic, Semantic) managed by a single `MemoryManager` class. While this is functional, several gaps have emerged as we plan the production-grade runtime:

1. **No execution checkpoints**: If a long-running workflow is interrupted (timeout, crash, user stops it), there is no mechanism to resume from the last completed step.
2. **Tool calls are not cached across sessions**: The market-data cache (`tools/market-data/cache.py`) is separate from the memory system. Tool calls are cached locally but not deduplicated across the entire execution.
3. **No artifact storage**: Generated reports, charts, and data exports have no dedicated storage tier. They're written to disk ad-hoc by each component.
4. **Research results not persisted**: Long-term research results (analyses that should be kept for weeks/months) are stored as semantic markdown files. No structured query support.
5. **No unified memory interface**: Components must know which tier to use. A unified `MemoryProvider` interface would allow components to access memory without caring about the storage backend.

## Decision

**Decision:** We will expand the memory system to 7 specialized tiers with a unified `MemoryProvider` interface.

### Memory Tiers

| Tier | Storage | Purpose | Access Pattern | TTL |
|------|---------|---------|----------------|-----|
| **Working** | In-memory dict | Current session state (plan, intermediate results) | Read/write per step | Session |
| **Episodic** | SQLite | Past session history (tool calls, results) | Append, query by session | Forever |
| **Semantic** | Markdown files | Cross-session knowledge (recommendations, preferences) | Write once, read by key | Forever |
| **Research** | SQLite + JSON | Long-term research results (structured) | Write per analysis, query by stock | Forever |
| **Tool Cache** | SQLite | Deduplicated tool call results | Read before tool call, write after | Per-tool config |
| **Execution** | JSON files | Step-by-step execution state | Write per step, read on resume | Session or resume |
| **Artifacts** | Filesystem | Generated outputs (reports, charts, exports) | Write per generation, read by report | Forever |

### MemoryProvider Interface

```python
class MemoryProvider(ABC):
    """Abstract memory provider. All tiers implement this."""

    @abstractmethod
    async def store(self, key: str, value: Any,
                    ttl: Optional[int] = None) -> None: ...

    @abstractmethod
    async def retrieve(self, key: str) -> Optional[Any]: ...

    @abstractmethod
    async def search(self, query: str,
                     limit: int = 10) -> list[MemoryEntry]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def clear(self, pattern: str = "*") -> None: ...
```

### ExecutionCheckpoint (Execution Tier)

The execution tier enables resumability:

```python
class ExecutionMemory(MemoryProvider):
    """Stores execution state for resume capability."""

    async def save_checkpoint(
        self, node_id: str, state: dict
    ) -> None:
        """Save execution state after a node completes."""

    async def load_checkpoint(self) -> Optional[dict]:
        """Load the most recent checkpoint."""

    async def get_completed_nodes(self) -> set[str]:
        """Get IDs of all completed nodes (skip on resume)."""

    async def get_execution_trace(self) -> list[dict]:
        """Get ordered list of all completed steps."""
```

### ToolCache (Tool Cache Tier)

The tool cache is managed by the ToolRegistry (Phase 3) but stored via the Memory Provider:

```python
class ToolCacheMemory(MemoryProvider):
    """Deduplicated cache for tool call results.

    Key = hash(tool_name + canonical_args)
    Value = tool result

    Cache hit → skip tool call, emit ToolCacheHit event
    Cache miss → call tool, store result, emit ToolCacheMiss event
    """
```

### CompositeMemoryManager

The old `MemoryManager` is refactored to delegate to the appropriate tier:

```python
class CompositeMemoryManager:
    """Facade over all memory tiers. Routes operations to the right tier."""

    def __init__(self):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.research = ResearchMemory()
        self.tool_cache = ToolCacheMemory()
        self.execution = ExecutionMemory()
        self.artifacts = ArtifactMemory()
```

## Rationale

- **Resumability is critical for production**: Long-running analyses (scanning 100+ stocks) may take minutes. A crash at 90% means restarting from scratch — unless checkpoints are saved.
- **Tool caching saves cost**: The market-data cache already demonstrates this. Moving it into the memory system with a unified interface makes it available to all tools via the ToolRegistry (Phase 3).
- **Artifact isolation**: Generated reports are conceptually different from analysis results. A dedicated tier makes backup, cleanup, and sharing straightforward.
- **Unified interface simplifies consumption**: Components call `memory.store()` or `memory.retrieve()` without knowing which tier handles it. The CompositeMemoryManager routes based on key prefix or configuration.
- **Gradual migration**: New tiers can be added one at a time. The old MemoryManager continues to work as a facade.

## Consequences

### Positive

- Workflow resumability: interrupting and resuming a long analysis saves time and compute.
- Tool caching: reduced API calls, faster subsequent runs.
- Artifact management: reports have a known location and naming convention.
- Research knowledge accumulates: queryable across weeks/months.
- Unified interface: components don't need to know memory internals.

### Negative

- 7 tiers is more complex than 3. Developers must understand which tier to use for what.
- Storage duplication: the same data may exist in multiple tiers (semantic + research). Mitigated by clear tier ownership.
- Execution memory consumes disk space proportional to run complexity (~1KB per checkpoint). Cleanup policies needed.

### Neutral

- The old `MemoryManager` class is not deleted — it becomes the `CompositeMemoryManager`.
- Existing code that uses `memory.set(key, value)` continues to work (routes to working memory by default).

## Alternatives Considered

### Alternative 1: Single SQLite database for all persistent memory

- **Description**: One SQLite database with separate tables for episodic, semantic, research, tool cache, and execution memory.
- **Pros**: Single backup; atomic transactions across tiers; consistent query interface.
- **Cons**: Mixing concerns in one DB; hard to reset one tier without affecting others; markdown semantic memory loses human readability.
- **Why rejected**: The separation of tiers is intentional — different access patterns, backup policies, and lifecycle requirements.

### Alternative 2: Keep 3 tiers, add execution checkpoints as files

- **Description**: Don't add new memory tiers. Just save execution checkpoints to disk as JSON files.
- **Pros**: Minimal change; solves the most critical gap (resumability).
- **Cons**: Tool caching remains outside memory; artifacts still ad-hoc; research results unstructured; misses the opportunity for a unified memory interface.
- **Why rejected**: The 3-tier model gets us to "good enough" but not to "reference implementation." The 7-tier model demonstrates comprehensive memory architecture.

### Alternative 3: Vector database for semantic/research memory

- **Description**: Use Chroma/Qdrant/Milvus for semantic search over research results and past recommendations.
- **Pros**: Semantic search ("find analyses similar to this stock"); embedding-based retrieval.
- **Cons**: Infrastructure dependency; embedding costs; over-engineering for current scale.
- **Why rejected**: Deferred. The markdown + SQLite approach handles ≤1000 analyses. Vector DB is a future optimization when the knowledge base grows.

## Related Decisions

- [ADR-003: Memory Architecture](003-memory-architecture.md) — Original memory design
- [ADR-006: Runtime Architecture](006-runtime-architecture.md) — Harness uses CompositeMemoryManager
- engineering-ai-standards: `runtime/memory-policy.md`

## Notes

Memory tier ownership:

| Tier | Writes | Reads |
|------|--------|-------|
| Working | Harness, Skills | Harness, Skills |
| Episodic | Harness | Verifier, ReportGenerator |
| Semantic | ReportGenerator | Planner (requirement analysis) |
| Research | Skills, ReportGenerator | Planner, Verifier |
| Tool Cache | ToolRegistry | ToolRegistry |
| Execution | Scheduler | Harness (on resume) |
| Artifacts | ReportGenerator | User (via CLI) |
