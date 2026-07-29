# Evolutionary Roadmap: From Investment Agent to Production-Grade Agent Framework

**Status:** Draft
**Author(s):** Principal AI Engineer
**Date:** 2026-07-29
**PR/FD:** TBD

---

## 0. Executive Summary

### Current State

The Tushare Investment Research Agent is a well-structured investment-domain application with:

- `agent/` — Planner, Executor, Verifier, ReportGenerator coupled to investment domain
- `strategies/` — 5 skill modules following eng-ai-standards format
- `tools/` — MCP server stubs, market cache, backtest engine stubs
- `workflows/` — Markdown workflow definitions (not executable)
- `evaluations/` — YAML evaluation cases
- `docs/` — Design doc + 5 ADRs

### Target State

A **production-grade Agent Framework + Reference Implementation** that demonstrates how modern AI agent systems should be architected. The framework (`runtime/`) is domain-agnostic; the investment domain (`agent/`, `strategies/`) is a concrete implementation *on top* of it.

| Aspect | Current | Target |
|--------|---------|--------|
| **Core** | Domain-coupled | Framework-first: `runtime/` is domain-agnostic |
| **Executor** | Procedural stub | Harness: lifecycle, retry, timeout, cache, context management |
| **Workflow** | Markdown docs | Executable Task Graph (DAG) with Scheduler |
| **Skills** | Loose interface | Standardized SDK with lifecycle hooks |
| **Tools** | Python functions | Metadata-rich Tool Registry (name, schema, cost, version, cache policy) |
| **Memory** | 3-tier basic | 7-tier: +Research, ToolCache, Execution, Artifact |
| **Observability** | None | Full event system: every step emits typed Event |
| **Evaluation** | Static YAML | Trajectory-aware: scores reasoning + tool selection + reflection |

### Guiding Principles

1. **Framework First** — `runtime/` owns all cross-cutting concerns. Business code owns none of them.
2. **Plugin-based** — Skills, Tools, and Workflows are plugins to the runtime. No hardcoded wiring.
3. **Event Driven** — Every state change is an Event. Events enable tracing, replay, debugging, UI.
4. **High Cohesion, Low Coupling** — Each component does one thing and knows nothing about unrelated components.
5. **Backward Compatible Throughout** — Each phase leaves the project runnable and testable.
6. **Every Change Gets an ADR** — Architecture decisions documented with rationale and alternatives.

---

## 1. Phase Overview

```
Phase 1: Runtime Core + Event System     ← NOW
  ├── runtime/ (Harness, Lifecycle, Tracing)
  ├── Core Event Types
  └── ADR-006: Runtime Architecture

Phase 2: Task Graph + Scheduler
  ├── runtime/graph.py (DAG definitions)
  ├── runtime/scheduler.py (parallel executor)
  ├── Investment workflows as executable TaskGraphs
  └── ADR-007: DAG-based Workflow Engine

Phase 3: Skill SDK + Tool Registry
  ├── skills/base/skill_sdk.py (standardized lifecycle)
  ├── tools/registry.py (metadata-rich ToolRegistry)
  ├── Migrate existing skills
  └── ADR-008: Skill SDK Standardization

Phase 4: Memory Expansion + Observability
  ├── Memory layers (Research, Execution, ToolCache, Artifact)
  ├── Full event instrumentation
  ├── CLI trace output
  └── ADR-009: Memory Expansion

Phase 5: Trajectory Evaluation + Integration
  ├── evaluations/trajectory/ (execution path scoring)
  ├── Full end-to-end flow
  ├── Example user scenarios as integration tests
  ├── Update docs/design.md
  └── ADR-010: Trajectory Evaluation
```

---

## 2. Phase 1 — Runtime Core + Event System

### Goal

Extract the cross-cutting runtime concerns (lifecycle, retry, timeout, cache, context, logging, observability) from the business logic. The investment-domain `agent/` classes become **business logic** that runs *on top of* the runtime, not *as* the runtime.

### What We Have Today

```
agent/planner.py     → CEO-level, domain-coupled
agent/executor.py    → TODO stub, would become a monolith if implemented
agent/verifier.py    → Domain-verification logic only
agent/memory.py      → Storage implementation mixed with domain logic
agent/registry.py    → Skills-only, tools not covered
```

### What Changes

#### New: `runtime/` package

```
runtime/
├── __init__.py
├── harness.py          ← Unified execution harness
├── lifecycle.py        ← Lifecycle hooks (on_start, on_step, on_error, on_finish)
├── tracing.py          ← Event system (emit, subscribe, replay)
├── context.py          ← Execution context (correlation_id, session_id, parent_span)
├── errors.py           ← Error taxonomy (Recoverable, Fatal, Timeout, RateLimited)
├── cache.py            ← Generic cache provider (TTL-based, LRU)
└── models.py           ← Core framework models (Event, LifecycleHook, ExecutionContext)
```

#### `runtime/models.py` — Core Abstractions

```python
@dataclass
class Event:
    """Every state change in the system is an Event."""
    id: str                  # uuid
    type: str                # "PlanningStarted" | "ToolInvoked" | ...
    timestamp: str           # ISO-8601
    correlation_id: str      # Trace across components
    parent_id: Optional[str] # Parent event for nesting
    payload: dict            # Type-specific data
    metadata: dict           # Additional context

@dataclass
class ExecutionContext:
    """Pervasive context across all runtime operations."""
    session_id: str
    correlation_id: str
    user_requirement: str
    start_time: str
    config: dict            # Runtime config (max_retries, timeouts)
    tags: dict              # Arbitrary labels for filtering
```

#### `runtime/harness.py` — The Agent Runtime

The Harness replaces the old `Executor` concept. It:

1. **Manages lifecycle**: `on_start → plan → on_planning_done → execute → on_execution_done → verify → on_verification_done → report → on_report_done → on_finish`
2. **Wraps every operation with**: retry, timeout, error classification, event emission
3. **Provides context**: ExecutionContext flows through every call
4. **Handles recovery**: Recovers from Recoverable errors, fails fast on Fatal
5. **Instruments everything**: Every step emits typed Events

```python
class Harness:
    """The universal agent runtime.

    Usage:
        harness = Harness(config=RuntimeConfig(...))
        result = await harness.run(
            planner=MyPlanner(),
            skills=[SkillA(), SkillB()],
            tools=[tool_registry],
            memory=memory_manager,
            verifier=MyVerifier(),
            reporter=MyReporter(),
            requirement="Analyze ..."
        )
    """

    async def run(self, ...) -> AgentResult:
        """Full lifecycle: Plan → Execute → Verify → Report."""
        ...
```

#### `runtime/lifecycle.py` — Hooks

```python
class LifecycleHook:
    """Hook point for cross-cutting concerns.

    Examples:
        - LoggingHook: logs each event
        - MetricsHook: tracks latency counters
        - AuditHook: records every tool call for audit
        - DebugHook: captures full traces for debugging
    """
    async def on_event(self, event: Event) -> None: ...
    async def on_error(self, context: ExecutionContext, error: Exception) -> None: ...
    async def on_timeout(self, context: ExecutionContext, step: str) -> None: ...
```

#### `runtime/tracing.py` — Event System

```python
class EventBus:
    """In-process event bus. All runtime operations emit events here.

    Supports:
        - Subscribe by event type pattern
        - Replay stored events
        - Export to JSON/OpenTelemetry
    """
    def emit(self, event: Event) -> None: ...
    def subscribe(self, event_type: str, handler: Callable) -> None: ...
    def replay(self, session_id: str) -> AsyncIterator[Event]: ...
    def export_trace(self, session_id: str) -> list[dict]: ...
```

#### `runtime/errors.py` — Error Taxonomy

```python
class AgentError(Exception):
    """Base error for all agent runtime errors."""

class RecoverableError(AgentError):
    """Error that can be retried (rate limit, timeout, transient)."""

class FatalError(AgentError):
    """Error that cannot be recovered (invalid config, missing token)."""

class SkillError(AgentError):
    """Error during skill execution."""

class ToolError(AgentError):
    """Error during tool invocation."""
```

#### `runtime/cache.py` — Generic Cache

```python
class CacheProvider(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]: ...
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int) -> None: ...
    @abstractmethod
    async def invalidate(self, pattern: str) -> None: ...

class TTLCache(CacheProvider):
    """In-memory TTL cache with optional SQLite persistence."""
```

### Event Types

All events emitted by the runtime:

| Event Type | When | Payload |
|------------|------|---------|
| `PlanningStarted` | Planner begins | `{requirement}` |
| `PlanningCompleted` | Planner finishes | `{plan}` |
| `StepStarted` | A workflow step begins | `{step_id, skill}` |
| `StepCompleted` | A workflow step finishes | `{step_id, result}` |
| `StepFailed` | A workflow step fails | `{step_id, error}` |
| `ToolInvoked` | A tool is called | `{tool_name, input}` |
| `ToolFinished` | A tool returns | `{tool_name, output, duration_ms}` |
| `ToolFailed` | A tool errors | `{tool_name, error, recoverable}` |
| `MemoryUpdated` | Memory is written | `{tier, key, size}` |
| `SkillStarted` | A skill begins execution | `{skill_name, context}` |
| `SkillCompleted` | A skill finishes | `{skill_name, score, confidence}` |
| `SkillVerifying` | A skill self-verifies | `{skill_name, check}` |
| `VerificationStarted` | Verifier begins | `{step_count}` |
| `VerificationCompleted` | Verifier finishes | `{passed, warnings}` |
| `ReflectionStarted` | LLM self-reflection | `{recent_events}` |
| `ReportGenerated` | Report is ready | `{report_id}` |
| `WorkflowFinished` | Full workflow done | `{status, duration_ms}` |
| `ErrorEncountered` | Non-fatal error | `{error, context}` |

### Backward Compatibility

- `agent/executor.py` is **NOT removed**. It gains a new implementation that delegates to `runtime/harness.py`.
- `agent/planner.py` continues to work; Harness calls it as a strategy.
- `agent/verifier.py` continues to work; Harness calls it as a strategy.
- `agent/report_generator.py` continues to work; Harness calls it as a strategy.
- `agent/__main__.py` is updated to create a Harness and run through it.

### Files Changed

| File | Action |
|------|--------|
| `runtime/__init__.py` | CREATE |
| `runtime/models.py` | CREATE — Event, ExecutionContext |
| `runtime/harness.py` | CREATE — AgentRuntime |
| `runtime/lifecycle.py` | CREATE — LifecycleHook |
| `runtime/tracing.py` | CREATE — EventBus |
| `runtime/errors.py` | CREATE — Error taxonomy |
| `runtime/cache.py` | CREATE — Cache provider |
| `agent/__main__.py` | MODIFY — Use Harness |
| `agent/executor.py` | MODIFY — Delegate to Harness |
| `README.md` | MODIFY — Updated architecture |

### Risks

| Risk | Mitigation |
|------|------------|
| Runtime abstraction premature (YAGNI) | Harness is thin — just lifecycle + event + retry. Only adds value when you want observability. |
| Over-engineering | Harness has a single concrete implementation initially. No abstract interface until Phase 4 proves one is needed. |
| Migration cost for existing code | All existing code continues to work. Harness wraps it, doesn't replace it. |

---

## 3. Phase 2 — Task Graph + Scheduler

### Goal

Upgrade from serial/markdown workflows to an executable Task Graph (DAG) with automated parallelism, dependency resolution, retry strategies, timeout management, and cancellation.

### What We Have Today

```
workflows/
├── investment-research.md    → Markdown (not executable)
├── portfolio-review.md       → Markdown (not executable)
└── stock-selection.md        → Markdown (not executable)
```

The `AnalysisPlan` has `analysis_steps: list[AnalysisStep]` with `depends_on` — but no engine to execute this as a DAG with parallelism.

### What Changes

#### New: `runtime/graph.py` — Task Graph

```python
@dataclass
class TaskNode:
    id: str
    label: str
    skill: str                # Which skill to run
    input_mapping: dict       # Map graph state → skill input
    output_mapping: dict      # Map skill output → graph state
    config: TaskConfig        # Timeout, retries, resources

@dataclass
class Edge:
    source_id: str
    target_id: str
    condition: Optional[str]  # "success" | "failure" | "always"

@dataclass
class TaskGraph:
    nodes: dict[str, TaskNode]
    edges: list[Edge]
    entry_points: list[str]   # Nodes with no inbound edges
    output_nodes: list[str]   # Nodes that produce final output
```

#### New: `runtime/scheduler.py` — DAG Scheduler

```python
class Scheduler:
    """Executes a TaskGraph with parallel awareness.

    Capabilities:
    - Topological sort → parallel batches
    - Parallel execution of independent nodes (asyncio.gather)
    - Per-node timeout and retry
    - Graceful cancellation
    - Resource limiting (max_concurrent)
    - State management (shared graph state)
    - Event emission for every state change
    """

    async def run(
        self,
        graph: TaskGraph,
        context: ExecutionContext,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
        memory: MemoryManager,
    ) -> GraphResult:
        """Execute the graph and return results."""
        ...
```

#### New: `runtime/workflow.py` — Workflow Definition

```python
class Workflow:
    """A named, versioned, reusable workflow definition.

    A workflow wraps a TaskGraph with metadata:
    - name, version, description
    - input_schema, output_schema
    - tags, owner
    """

    name: str
    version: str
    description: str
    graph: TaskGraph
    input_schema: dict  # JSON Schema
    output_schema: dict
    default_config: WorkflowConfig
```

#### Migrating Investment Research to TaskGraph

The existing markdown workflow becomes an executable graph:

```python
research_graph = TaskGraph(
    nodes={
        "requirement": TaskNode(id="req", skill="planner", ...),
        "data": TaskNode(id="data", skill="data-collector",
                         depends_on=["req"], ...),
        "fundamental": TaskNode(id="fund", skill="fundamental-analysis",
                                depends_on=["data"], ...),
        "technical": TaskNode(id="tech", skill="technical-analysis",
                              depends_on=["data"], ...),
        "valuation": TaskNode(id="val", skill="valuation-analysis",
                              depends_on=["data"], ...),
        "risk": TaskNode(id="risk", skill="risk-analysis",
                         depends_on=["data"], ...),
        "portfolio": TaskNode(id="port", skill="portfolio-selection",
                              depends_on=["fund", "tech", "val", "risk"], ...),
        "verify": TaskNode(id="verify", skill="verifier",
                           depends_on=["port"], ...),
        "report": TaskNode(id="report", skill="report-generator",
                           depends_on=["verify"], ...),
    },
    edges=[
        Edge("req", "data"),
        Edge("data", "fund"), Edge("data", "tech"),
        Edge("data", "val"), Edge("data", "risk"),
        Edge("fund", "port"), Edge("tech", "port"),
        Edge("val", "port"), Edge("risk", "port"),
        Edge("port", "verify"),
        Edge("verify", "report"),
    ],
    entry_points=["req"],
    output_nodes=["report"],
)
```

The scheduler automatically detects that `fund`, `tech`, `val`, `risk` are independent and runs them concurrently.

#### Workflow YAML Format (Optional)

Workflows can still be defined declaratively:

```yaml
# workflows/graphs/investment-research.yaml
name: investment-research
version: 2.0.0
description: End-to-end investment research workflow

nodes:
  requirement-analysis:
    skill: planner
    timeout: 30s

  data-collection:
    skill: data-collector
    depends_on: [requirement-analysis]
    timeout: 60s

  fundamental-analysis:
    skill: fundamental-analysis
    depends_on: [data-collection]
    timeout: 120s

  technical-analysis:
    skill: technical-analysis
    depends_on: [data-collection]
    timeout: 120s

  # ... etc

edges:
  - from: requirement-analysis
    to: data-collection
  - from: data-collection
    to: [fundamental-analysis, technical-analysis, valuation-analysis, risk-analysis]
  - from: [fundamental-analysis, technical-analysis, valuation-analysis, risk-analysis]
    to: portfolio-selection
  - from: portfolio-selection
    to: verification
  - from: verification
    to: report-generation
```

### Scheduler Internals

```
Scheduler.run(graph):
  1. Validate graph (no cycles, all deps resolvable)
  2. Topological sort → layers
  3. For each layer:
     a. Gather all runnable nodes (all deps satisfied)
     b. Run them concurrently via asyncio.gather()
     c. Each node: emit StepStarted → exec skill → emit StepCompleted
     d. On failure: check retry policy → retry or mark failed
  4. After all layers: return accumulated GraphResult
  5. Emit WorkflowFinished

Retry strategy (per-node):
  - On RecoverableError: retry up to N times with exponential backoff
  - On ToolError (rate limit): wait, retry
  - On TimeoutError: mark failed, skip downstream unless fallback exists
  - On FatalError: fail immediately, cancel graph
```

### Backward Compatibility

- Old `AnalysisPlan` with `list[AnalysisStep]` is still supported. A thin adapter converts it to `TaskGraph`.
- `workflows/investment-research.md` is kept as documentation. The *executable* version moves to `workflows/graphs/investment-research.yaml`.
- The `Planner` can output either format — if it outputs the old list format, the Harness adapts.

### Files Changed

| File | Action |
|------|--------|
| `runtime/graph.py` | CREATE — TaskNode, Edge, TaskGraph |
| `runtime/scheduler.py` | CREATE — Scheduler |
| `runtime/workflow.py` | CREATE — Workflow definition |
| `workflows/graphs/investment-research.yaml` | CREATE — Executable graph |
| `workflows/graphs/portfolio-review.yaml` | CREATE — Executable graph |
| `agent/executor.py` | MODIFY — Delegate to Scheduler |
| `runtime/harness.py` | MODIFY — Integrate Scheduler |

---

## 4. Phase 3 — Skill SDK + Tool Registry

### Goal

Standardize the Skill lifecycle into a proper SDK (not just an ABC with `analyze()`), and create a metadata-rich Tool Registry so the Planner can discover and reason about tools instead of hardcoding calls.

### What We Have Today

#### Skill Interface (current)

```python
class InvestmentSkill(ABC):
    @abstractmethod
    async def analyze(self, context: AnalysisContext) -> AnalysisResult: ...
    @abstractmethod
    def get_metadata(self) -> dict: ...
    @property
    def name(self) -> str: ...
    @property
    def version(self) -> str: ...
```

**Problems:**
- Only has `analyze()` — no verify, no summarize, no plan phase within the skill
- `get_metadata()` returns a raw dict — no schema validation
- No self-verification hook
- No way for skills to declare their data dependencies declaratively

#### Tool Definitions (current)

```python
# tools/tushare-mcp/server.py
def get_stock_basic(market=None, industry=None) -> list[dict]: ...
def get_daily_price(ts_code, start_date, end_date) -> list[dict]: ...
```

**Problems:**
- No metadata (cost, version, cache policy, permission)
- No formal schema (docstrings, not JSON Schema)
- No discovery (Planner can't enumerate available tools)
- No timeout management
- No rate limiting awareness

### What Changes

#### New Skill SDK: `skills/base/skill_sdk.py`

```python
class SkillLifecycle(ABC):
    """Standardized lifecycle for all skills in the framework.

    A skill progresses through:
    1. metadata()   — Declare identity, capabilities, dependencies
    2. plan()       — Given context, decide what to do (sub-steps)
    3. execute()    — Execute the analysis, return results
    4. verify()     — Self-verify: is the output consistent?
    5. summarize()  — Produce human-readable summary
    """

    @abstractmethod
    def metadata(self) -> SkillMetadata:
        """Declare skill identity and capabilities."""
        ...

    @abstractmethod
    async def plan(self, context: dict) -> SkillPlan:
        """Given context, decide what sub-steps to execute.

        Returns a plan (can be empty if execution is trivial).
        The runtime can inspect the plan for observability.
        """
        ...

    @abstractmethod
    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        """Execute the skill's core logic.

        context contains all data the skill requested in plan().
        """
        ...

    @abstractmethod
    async def verify(self, context: dict, output: SkillOutput) -> SkillVerdict:
        """Self-verify: is the output consistent with the input data?

        Returns PASS/WARN/FAIL with reasons.
        """
        ...

    @abstractmethod
    async def summarize(self, output: SkillOutput) -> str:
        """Produce a human-readable summary of the skill's output."""
        ...


@dataclass
class SkillMetadata:
    name: str
    version: str
    description: str
    category: str
    tags: list[str]
    input_schema: dict       # JSON Schema for expected input
    output_schema: dict      # JSON Schema for guaranteed output
    data_requirements: list[str]  # Declarative: "needs income_statement"
    timeout: int             # Default timeout in seconds
    cost: float              # Relative cost (1-10)
    dependencies: list[str]  # Other skills this depends on
```

#### Migration Path for Existing Skills

The old `InvestmentSkill` interface is NOT removed. A compatibility adapter wraps it:

```python
class LegacySkillAdapter(SkillLifecycle):
    """Wraps an old InvestmentSkill into the new SkillLifecycle.

    - metadata() → InvestmentSkill.get_metadata()
    - plan() → returns empty plan (legacy skills don't plan)
    - execute() → InvestmentSkill.analyze()
    - verify() → always returns PASS (legacy doesn't self-verify)
    - summarize() → returns AnalysisResult.reasoning
    """
    ...

    async def execute(self, context, plan) -> SkillOutput:
        old_context = self._convert_context(context)
        result = await self._skill.analyze(old_context)
        return self._convert_result(result)
```

All 5 existing skills keep working. New skills use the new SDK natively.

#### New Tool Registry: `tools/registry.py`

```python
@dataclass
class ToolMetadata:
    name: str
    description: str
    schema: dict               # JSON Schema for input parameters
    returns: dict              # JSON Schema for return value
    capability: str            # "market-data" | "financials" | "analysis"
    timeout: int               # Max execution time (seconds)
    cost: int                  # Relative cost (1-10, for planner optimization)
    version: str               # Tool version
    permission: str            # "read" | "write" | "admin"
    cache_policy: CachePolicy  # TTL-based or no-cache
    rate_limit: Optional[str]  # e.g., "200/min"
    errors: list[str]          # Known error types


class ToolRegistry:
    """Central registry of all available tools.

    - Tools declare rich metadata
    - Planner can discover tools by capability
    - Runtime enforces timeouts and rate limits
    - Cache policy is managed by the runtime, not the tool
    """

    def register(self, tool: ToolMetadata, implementation: Callable) -> None: ...

    def find_by_capability(self, capability: str) -> list[ToolMetadata]: ...

    def get_schemas_for_llm(self) -> list[dict]:
        """Return tool schemas formatted for LLM tool-use API."""
        ...

    async def invoke(
        self,
        tool_name: str,
        args: dict,
        context: ExecutionContext,
    ) -> ToolResult:
        """Invoke a tool with runtime-managed:
        - Timeout enforcement
        - Retry for recoverable errors
        - Cache lookup
        - Event emission (ToolInvoked, ToolFinished)
        - Metrics recording
        """
        ...
```

#### Tushare Tools Migrated

```yaml
tools:
  get_stock_basic:
    description: "List stocks by market/industry"
    capability: "market-data"
    timeout: 10
    cost: 1
    version: "1.0.0"
    permission: "read"
    cache_policy:
      ttl: 86400  # 24h
    rate_limit: "200/min"

  get_daily_price:
    description: "Daily OHLCV price data"
    capability: "market-data"
    timeout: 15
    cost: 1
    version: "1.0.0"
    permission: "read"
    cache_policy:
      ttl: 14400  # 4h

  get_income_statement:
    description: "Income statement data"
    capability: "financials"
    timeout: 15
    cost: 2
    version: "1.0.0"
    permission: "read"
    cache_policy:
      ttl: 0  # No cache (immutable but refresh on demand)
```

### Impact

- Planner can now answer: "What tools do I need for fundamental analysis?" by matching skill `data_requirements` to tool `capability`.
- Runtime can now enforce timeouts, rate limits, and cache policies transparently.
- New tools can be added by registration — no code changes beyond the implementation.

### Files Changed

| File | Action |
|------|--------|
| `skills/base/skill_sdk.py` | CREATE — SkillLifecycle, SkillMetadata, LegacySkillAdapter |
| `tools/registry.py` | CREATE — ToolMetadata, ToolRegistry |
| `agent/registry.py` | MODIFY — Extend to work with ToolRegistry |
| `tools/tushare-mcp/tools.yaml` | CREATE — Tool metadata declarations |
| `tools/tushare-mcp/server.py` | MODIFY — Register tools with ToolRegistry |
| `runtime/harness.py` | MODIFY — Integrate ToolRegistry for tool invocation |
| `agent/planner.py` | MODIFY — Use ToolRegistry for tool discovery |

---

## 5. Phase 4 — Memory Expansion + Observability

### Goal

Extend the memory system from 3 tiers to 7 specialized tiers, and wire the Event System throughout the entire runtime for full observability.

### What We Have Today

```
memory/
├── short-term/         → Working memory (per-session)
└── long-term/          → Semantic memory (recommendations)

agent/memory.py
  - MemoryManager (working + episodic SQLite + semantic)
```

### What Changes

#### Expanded Memory: `memory/`

```
memory/
├── working/             ← Old: short-term (in-memory dict)
├── episodic/            ← Old: SQLite session history
├── semantic/            ← Old: markdown recommendations
├── research/            ← NEW: Long-term research results
├── tool-cache/          ← NEW: Deduplicated tool call results
├── execution/           ← NEW: Full execution state for resumability
└── artifacts/           ← NEW: Generated reports, charts, data exports
```

#### Memory Interface: `memory/interfaces.py`

```python
class MemoryProvider(ABC):
    """Abstract memory provider. All memory tiers implement this."""

    @abstractmethod
    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None: ...

    @abstractmethod
    async def retrieve(self, key: str) -> Optional[Any]: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def clear(self, pattern: str = "*") -> None: ...
```

#### New Memory Tier Details

| Tier | Storage | Purpose | TTL |
|------|---------|---------|-----|
| Working | In-memory dict | Current session state | Session |
| Episodic | SQLite | Past session histories | Forever |
| Semantic | Markdown | Cross-session knowledge | Forever |
| Research | SQLite + JSON | Long-term research results | Forever |
| Tool Cache | SQLite | Deduplicate identical tool calls | Per-tool config |
| Execution | JSON files | Step-by-step execution state | Session or Resume |
| Artifacts | Filesystem | Reports, charts, exports | Forever |

#### `memory/execution.py` — Resumability

```python
class ExecutionMemory:
    """Stores the full execution state for resume capability.

    If a workflow is interrupted (timeout, crash), the next run can
    resume from the last completed step rather than starting over.
    """

    async def save_checkpoint(self, step_id: str, state: dict) -> None: ...
    async def load_checkpoint(self) -> Optional[dict]: ...
    async def get_execution_trace(self) -> list[dict]: ...
    ...
```

#### Full Event Instrumentation

Every component now emits events through the EventBus:

- **Harness**: emits lifecycle events (PlanningStarted → WorkflowFinished)
- **Scheduler**: emits per-node events (StepStarted, StepCompleted, StepFailed)
- **ToolRegistry**: emits per-tool events (ToolInvoked, ToolFinished, ToolFailed)
- **Skill**: emits per-skill events (SkillStarted, SkillCompleted, SkillVerifying)
- **Memory**: emits memory events (MemoryUpdated, MemoryCacheHit, MemoryCacheMiss)
- **Planner**: emits plan events (PlanningStarted, PlanningCompleted)

#### CLI Trace Output

```bash
$ python -m agent --requirement "Find opportunities" --trace

═══════════════════════════════════════════════════════════
 Execution Trace: session-a1b2c3d4
═══════════════════════════════════════════════════════════
 09:30:01.000 [PLAN]     PlanningStarted        requirement="Find opportunities"
 09:30:02.150 [PLAN]     PlanningCompleted       4 steps, 3 data requirements
 09:30:02.151 [GRAPH]    GraphResolved           9 nodes, 4 parallel batches
 09:30:02.200 [TOOL]     ToolInvoked             get_stock_basic(market=SSE)
 09:30:02.800 [TOOL]     ToolFinished            142 stocks (892ms)
 09:30:02.801 [CACHE]    MemoryCacheHit          stock_basic_SSE (886ms saved)
 09:30:03.000 [SKILL]    SkillStarted            fundamental-analysis (4 stocks)
 09:30:03.150 [TOOL]     ToolInvoked             get_income_statement(000001.SZ)
 09:30:03.900 [TOOL]     ToolFinished            8 periods (750ms)
 09:30:04.500 [TOOL]     ToolInvoked             get_balance_sheet(000001.SZ)
 ...
 09:31:30.000 [SKILL]    SkillCompleted          fundamental-analysis score=0.82
 09:31:30.001 [SKILL]    SkillStarted            technical-analysis (4 stocks)
 ...
 09:33:00.000 [VERIFY]   VerificationStarted     3 checks
 09:33:00.500 [VERIFY]   VerificationCompleted   passed=True
 09:33:01.000 [REPORT]   ReportGenerated         report-20260729-093301.md
 09:33:01.200 [DONE]     WorkflowFinished        120.3s total, 32 tool calls

 Memory usage: 14 entries (working), 23 sessions (episodic)
 Tool cache: 8 hits / 32 calls (25% hit rate)
═══════════════════════════════════════════════════════════
```

#### Files Changed

| File | Action |
|------|--------|
| `memory/interfaces.py` | CREATE — MemoryProvider ABC |
| `memory/research.py` | CREATE — Research memory tier |
| `memory/execution.py` | CREATE — Execution memory + checkpoints |
| `memory/tool_cache.py` | CREATE — Tool cache tier |
| `memory/artifacts.py` | CREATE — Artifact memory tier |
| `agent/memory.py` | MODIFY — Delegate to new tiers |
| `runtime/tracing.py` | MODIFY — Full instrumentation of all events |
| `runtime/harness.py` | MODIFY — Emit all lifecycle events |
| `runtime/scheduler.py` | MODIFY — Emit per-node events |
| `tools/registry.py` | MODIFY — Emit tool events |
| `agent/__main__.py` | MODIFY — --trace flag support |

---

## 6. Phase 5 — Trajectory Evaluation + Integration

### Goal

Add trajectory-aware evaluation that scores not just the *final output* but the entire *execution path* — tool selection quality, reasoning steps, reflection quality, error recovery.

### What We Have Today

```
evaluations/
├── agent-quality/        → Scores final report quality
├── strategy-score/       → Scores strategy performance
└── historical-backtest/  → Scores backtest results
```

All current evaluation is **output-only** — it looks at the final report or final score, not at *how* the agent got there.

### What Changes

#### New: `evaluations/trajectory/`

```yaml
# evaluations/trajectory/agent-trajectory.yaml
id: trajectory-v1
skill: fundamental-analysis
category: trajectory
version: 1.0.0
task: >
  Analyze 000001.SZ using fundamental analysis.
  The agent should collect financial data, analyze metrics,
  reason about trends, and produce a score.

measurements:
  - step: planning
    metrics:
      - name: requirement_coverage
        description: "Does the plan address all parts of the requirement?"
      - name: tool_selection_quality
        description: "Are the right tools selected for the task?"
      - name: dependency_accuracy
        description: "Are dependencies between steps correctly identified?"

  - step: data_collection
    metrics:
      - name: tool_call_efficiency
        description: "Are unnecessary tool calls avoided?"
        measures: [tool_cache_hit_rate, redundant_calls]
      - name: data_completeness
        description: "Does collected data cover analysis needs?"

  - step: execution
    metrics:
      - name: reasoning_quality
        description: "Quality of LLM reasoning at each step"
      - name: error_recovery
        description: "How well does the agent handle tool failures?"
      - name: skill_invocation_accuracy
        description: "Are skills invoked with correct parameters?"

  - step: verification
    metrics:
      - name: self_check_quality
        description: "Does the agent correctly identify issues?"
      - name: false_positive_rate
        description: "Are non-issues incorrectly flagged?"

  - step: overall
    metrics:
      - name: tool_call_ratio
        description: "Tool calls per step — too many indicates inefficiency"
      - name: reflection_depth
        description: "Does the agent reflect on intermediate results?"
      - name: completion_efficiency
        description: "Steps taken vs. optimal steps"
```

#### Trajectory Scoring Engine

```python
class TrajectoryEvaluator:
    """Evaluates the full execution trajectory of an agent run.

    Input: Full trace of Events from a session
    Output: Per-step scores + overall trajectory score
    """

    async def evaluate(
        self,
        trace: list[Event],
        expected: TrajectoryExpectations,
    ) -> TrajectoryScore:
        """Score the execution path.

        Analysis dimensions:
        - Planning quality: Did the Planner produce a reasonable graph?
        - Tool selection: Were appropriate tools chosen?
        - Execution efficiency: Number of steps vs optimal path
        - Error recovery: Quality of error handling
        - Reflection: Did the agent adjust based on intermediate results?
        - Overall: Composite trajectory quality score
        """
        ...
```

#### Replay Support

The EventBus supports replay:

```python
# Replay a session for debugging
events = await event_bus.replay(session_id="a1b2c3d4")
for event in events:
    print(f"[{event.timestamp}] {event.type}: {event.payload}")

# Export for evaluation
trace = await event_bus.export_trace(session_id="a1b2c3d4")
score = await trajectory_evaluator.evaluate(trace, expected_case)
```

#### Full End-to-End Flow

After Phase 5, the complete flow works as a demonstration:

```
User Requirement
    │
    ▼
Planner → TaskGraph
    │
    ▼
Scheduler (parallel DAG execution via Harness)
    │
    ├── Data Collection  →  ToolRegistry.invoke (cached, traced)
    ├── Fundamental      →  SkillSDK.execute (lifecycle, events)
    ├── Technical        →  SkillSDK.execute (parallel)
    ├── Valuation        →  SkillSDK.execute (parallel)
    ├── Risk             →  SkillSDK.execute (parallel)
    ├── Portfolio        →  SkillSDK.execute (depends on prior)
    ├── Verification     →  Verifier.verify
    └── Report           →  ReportGenerator.generate
    │
    ▼
Investment Report (markdown)
    │
    ▼
Events → Trajectory Evaluation → Scores
```

#### Files Changed

| File | Action |
|------|--------|
| `evaluations/trajectory/agent-trajectory.yaml` | CREATE — Trajectory case |
| `evaluations/trajectory/evaluator.py` | CREATE — TrajectoryEvaluator |
| `evaluations/trajectory/scorer.py` | CREATE — Per-metric scoring |
| `runtime/tracing.py` | MODIFY — Replay support |
| `agent/__main__.py` | MODIFY — Trajectory evaluation mode |
| `tests/e2e/test_investment_research.py` | CREATE — End-to-end test |
| `docs/design.md` | MODIFY — Updated architecture |

---

## 7. Summary: Target Architecture

```
# After all 5 phases =====================================

tushare-investment-agent/
│
├── runtime/                          # ── Framework Core (domain-agnostic)
│   ├── __init__.py
│   ├── models.py                     # Event, ExecutionContext, RuntimeConfig
│   ├── harness.py                    # Unified agent runtime (lifecycle mgmt)
│   ├── lifecycle.py                  # Lifecycle hooks (logging, metrics, audit)
│   ├── errors.py                     # Error taxonomy (Recoverable, Fatal, etc.)
│   ├── cache.py                      # Generic cache provider
│   ├── graph.py                      # TaskGraph, TaskNode, Edge
│   ├── scheduler.py                  # DAG scheduler (parallel execution)
│   ├── workflow.py                   # Workflow metadata + loader
│   └── tracing/                      # Event system
│       ├── __init__.py
│       ├── event_bus.py              # Emit, subscribe, replay, export
│       ├── event_types.py            # All event type definitions
│       └── formatters.py             # CLI, JSON, OpenTelemetry output
│
├── agent/                            # ── Business Logic (Investment Domain)
│   ├── planner.py                    # Requirement → TaskGraph (uses ToolRegistry)
│   ├── executor.py                   # Thin wrapper → delegates to Scheduler
│   ├── verifier.py                   # Multi-phase verification skill
│   ├── report_generator.py           # Template-based report skill
│   ├── memory.py                     # Memory facade → delegates to memory/ tiers
│   ├── registry.py                   # SkillRegistry + ToolRegistry facade
│   └── __main__.py                   # CLI entry (Harness-based)
│
├── skills/                           # ── Skills (domain-specific or generic)
│   ├── base/
│   │   ├── skill_sdk.py             # SkillLifecycle ABC + LegacySkillAdapter
│   │   └── models.py                # SkillMetadata, SkillPlan, SkillOutput
│   ├── fundamental-analysis/        # (unchanged interface, uses SDK)
│   ├── technical-analysis/          # (unchanged interface, uses SDK)
│   ├── valuation-analysis/          # (unchanged interface, uses SDK)
│   ├── risk-analysis/               # (unchanged interface, uses SDK)
│   └── portfolio-selection/         # (unchanged interface, uses SDK)
│
├── tools/                            # ── Tools
│   ├── registry.py                  # ToolRegistry (metadata + invocation)
│   ├── tushare-mcp/
│   │   ├── tools.yaml               # Tool metadata declarations
│   │   └── server.py                # MCP server (registers with ToolRegistry)
│   ├── market-data/
│   │   └── cache.py                 # Local data cache
│   └── backtest/
│       └── engine.py                # Backtest engine
│
├── workflows/                        # ── Workflow Definitions
│   ├── graphs/
│   │   ├── investment-research.yaml # Executable TaskGraph definition
│   │   └── portfolio-review.yaml    # Executable TaskGraph definition
│   ├── investment-research.md       # (kept: human-readable documentation)
│   ├── portfolio-review.md          # (kept: human-readable documentation)
│   └── stock-selection.md           # (kept: human-readable documentation)
│
├── memory/                           # ── Memory Tiers
│   ├── interfaces.py                # MemoryProvider ABC
│   ├── working.py                   # In-memory session state
│   ├── episodic.py                  # SQLite session history
│   ├── semantic.py                  # Markdown knowledge
│   ├── research.py                  # Long-term research results (+SQLite)
│   ├── tool_cache.py                # Tool call deduplication (+SQLite)
│   ├── execution.py                 # Execution checkpoints (+JSON)
│   └── artifacts.py                 # Generated reports (+filesystem)
│
├── evaluations/                      # ── Evaluation
│   ├── agent-quality/
│   ├── strategy-score/
│   ├── historical-backtest/
│   └── trajectory/                  # NEW: Trajectory evaluation
│       ├── agent-trajectory.yaml    # Evaluation case
│       └── evaluator.py             # Trajectory scoring engine
│
├── docs/
│   ├── design.md                    # Updated architecture
│   └── adr/
│       ├── 001-agent-architecture.md
│       ├── 002-skill-system.md
│       ├── 003-memory-architecture.md
│       ├── 004-mcp-integration.md
│       ├── 005-evaluation-framework.md
│       ├── 006-runtime-architecture.md     # NEW
│       ├── 007-dag-workflow-engine.md      # NEW
│       ├── 008-skill-sdk-standardization.md  # NEW
│       ├── 009-memory-expansion.md         # NEW
│       └── 010-trajectory-evaluation.md    # NEW
│
└── tests/
    ├── agent/
    ├── skills/
    ├── tools/
    ├── runtime/                     # NEW: Runtime tests
    ├── evaluations/
    └── e2e/                         # NEW: End-to-end tests
```

---

## 8. Principles: Architecture Guardrails

### High Cohesion

Each module has one clear responsibility. `runtime/harness.py` does lifecycle — it doesn't call Tushare. `tools/registry.py` manages tool metadata — it doesn't execute analysis.

### Low Coupling

Components communicate through interfaces, not concrete classes. The Harness depends on `MemoryProvider` (ABC), not `MemoryManager` (concrete). Skills depend on `SkillLifecycle` (ABC), not `Harness`.

### Plugin-based

New skills, tools, and workflows are registered, not imported. Adding a skill: implement `SkillLifecycle`, add to `registry/skills.yaml`. Adding a tool: implement function, define `ToolMetadata`, register with `ToolRegistry`.

### Event Driven

Every state change is an Event. Events flow through the EventBus. Components subscribe to events they care about. No component calls another component's methods directly for cross-cutting concerns.

### Observable

Every step, every tool call, every memory access emits an Event. The CLI `--trace` flag shows the full execution trace. Events can be replayed for debugging and evaluation.

### Testable

- `Harness` accepts mock skills, mock tools, mock memory — unit test without LLM.
- `Scheduler` accepts a TaskGraph and mock nodes — test parallelism without execution.
- `EventBus` can record and replay — test observability without real runs.
- Evaluation cases are YAML — add cases without writing code.

### Production Ready

- Error taxonomy with recovery strategies.
- Timeout enforcement at every level (tool, skill, node, workflow).
- Rate limiting and caching built into ToolRegistry.
- Resumability via ExecutionMemory checkpoints.

### AI Native

- Skills are designed for LLM-in-the-loop execution (plan → execute → verify → summarize).
- Tools declare metadata the LLM can reason about (capability, cost, rate limit).
- The Planner uses ToolRegistry for automatic tool discovery.
- Trajectory evaluation scores LLM reasoning paths, not just outputs.

---

## 9. Appendix: Phase Dependency Graph

```
Phase 1: Runtime Core
├── Creates: runtime/harness.py, runtime/tracing.py, runtime/lifecycle.py
├── Enables: Event system, retry, timeout, lifecycle hooks
└── Required by: All later phases

Phase 2: Task Graph + Scheduler
├── Creates: runtime/graph.py, runtime/scheduler.py
├── Depends on: Phase 1 (Harness invokes Scheduler)
└── Enables: Parallel execution, DAG workflows

Phase 3: Skill SDK + Tool Registry
├── Creates: skills/base/skill_sdk.py, tools/registry.py
├── Depends on: Phase 1 (runtime types), Phase 2 (Scheduler runs skills)
└── Enables: Standardized skill lifecycle, tool discovery

Phase 4: Memory Expansion
├── Creates: memory/tiers
├── Depends on: Phase 1 (runtime types)
└── Enables: Resumability, tool caching, artifact storage

Phase 5: Trajectory Evaluation
├── Creates: evaluations/trajectory/
├── Depends on: Phase 1 (EventBus for replay), Phase 4 (full trace)
└── Enables: Trajectory scoring, end-to-end tests
```

**Parallelism note:** Phases 2 and 3 have no dependency on each other — they can be developed in parallel once Phase 1 is complete.

---

## 10. Appendix: Effort Estimation

| Phase | Files | Est. Effort | Risk | Business Value |
|-------|-------|-------------|------|----------------|
| 1. Runtime Core | 8 new, 2 modified | High (foundation) | Medium | High (establishes architecture) |
| 2. Task Graph | 3 new, 3 modified | Medium | Low | High (parallelism = speed) |
| 3. Skill SDK | 2 new, 4 modified | Medium | Low | Medium (standardization) |
| 4. Memory | 6 new, 2 modified | Medium | Low | Medium (resumability, caching) |
| 5. Trajectory Eval | 3 new, 2 modified | Low | Low | High (measurable quality) |

**Total:** ~22 new files, ~13 modified files across 5 phases.

**Recommended order:** Phase 1 → [Phase 2 + Phase 3 in parallel] → Phase 4 → Phase 5.
