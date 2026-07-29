# Architecture Decision Record: DAG-based Workflow Engine

**Status:** Proposed
**Decision:** #007
**Date:** 2026-07-29

## Context

The current workflow system has two limitations:

1. **Workflows are documentation, not executable code**: `workflows/investment-research.md` describes steps but cannot be executed. The `AnalysisPlan` in `strategies/base/models.py` has a `list[AnalysisStep]` but no engine to execute it as a DAG with parallelism.
2. **No automatic parallelism**: The `depends_on` field on steps implies a DAG, but the Executor has no scheduler. Independent steps (fundamental, technical, valuation, risk) must be explicitly parallelized in code.

The investment research workflow has a clear DAG structure:

```
         Planner
            │
            ▼
      Data Collection
       │   │   │   │
       ▼   ▼   ▼   ▼
      F    T    V   R    ← Independent (can run in parallel)
       │   │   │   │
       └───┴───┴───┘
            │
            ▼
    Portfolio Selection
            │
            ▼
       Verification
            │
            ▼
    Report Generation
```

Without a DAG-aware scheduler, we lose:
- Parallel execution speedup (4 independent analyses × N stocks)
- Structured retry policies per node
- Visual workflow debugging
- Cancellation propagation
- Progress tracking

## Decision

**Decision:** We will implement a DAG-based Workflow Engine in `runtime/graph.py` and `runtime/scheduler.py`.

### `runtime/graph.py` — Task Graph

A Task Graph is a directed acyclic graph (DAG) where:
- **Nodes** (`TaskNode`) represent executable units (skills, tool calls, LLM calls)
- **Edges** (`Edge`) represent dependencies with optional conditions
- The graph has entry points (nodes with no dependencies) and output nodes (nodes that produce final results)

### `runtime/scheduler.py` — DAG Scheduler

The Scheduler executes a TaskGraph:

1. **Validate**: Check for cycles, missing dependencies, and orphaned nodes.
2. **Topological sort**: Compute execution layers (batches of parallel nodes).
3. **Execute layers**: For each layer, run all nodes concurrently via `asyncio.gather()`.
4. **State propagation**: Each node reads from and writes to a shared graph state.
5. **Error handling**: Per-node retry policy, failure propagation, optional cancellation.
6. **Emit events**: Every node lifecycle change emits an Event (StepStarted, StepCompleted, StepFailed).

### TaskNode Definition

```python
class TaskNode:
    id: str                    # Unique identifier
    label: str                 # Human-readable name
    skill: str                 # Skill name from registry
    config: TaskConfig         # Timeout, retries, resources
    input_mapping: dict        # Map graph state → skill input context
    output_mapping: dict       # Map skill output → graph state keys
```

### Parallel Execution Model

The scheduler uses layered topological ordering:

```
Layer 0: [Planner]                    (1 node, serial)
Layer 1: [DataCollection]             (1 node, serial)
Layer 2: [Fund, Tech, Val, Risk]      (4 nodes, parallel)
Layer 3: [Portfolio]                  (1 node, serial)
Layer 4: [Verifier]                   (1 node, serial)
Layer 5: [Report]                     (1 node, serial)
```

Within Layer 2, all 4 skills execute concurrently. The scheduler waits for all of them before proceeding to Layer 3.

## Rationale

- **DAG is the natural model**: Investment research is inherently a DAG — data collection feeds multiple independent analyses which feed a synthesis step. The DAG model captures this accurately.
- **Parallelism without complexity**: The scheduler automatically detects parallelism from the graph structure. No explicit parallel programming needed.
- **Recoverability**: Per-node retry and timeout policies mean a temporary failure in one branch doesn't block other branches.
- **Observability**: The graph structure provides a natural progress model. "3/5 nodes complete, 2 running."
- **Declarative workflows**: Workflows can be defined as YAML (declarative) or code (imperative). Both produce the same TaskGraph structure.
- **Graph is inspectable**: Before execution, the full graph can be displayed for debugging or user approval.

## Consequences

### Positive

- Investment research runs ~2-3× faster with parallel execution of 4 independent strategies.
- Workflows become executable, testable, and visible.
- Retry policies are per-node, not one-size-fits-all.
- New workflows can be added as YAML without writing Python.
- The Scheduler is domain-agnostic — it can execute any TaskGraph.

### Negative

- TaskGraph adds complexity compared to a linear script. Simple workflows (2-3 serial steps) may be over-engineered as DAGs.
- Debugging parallel execution is harder than debugging serial execution (race conditions, shared state).
- Graph state management requires discipline — nodes should only read their declared inputs.

### Neutral

- The old `list[AnalysisStep]` format is still supported via an adapter.
- The Scheduler uses `asyncio` — a single-threaded concurrency model. True parallelism (multi-process) would need a different scheduler.

## Alternatives Considered

### Alternative 1: Serial execution with explicit parallelism

- **Description**: Keep the current `list[AnalysisStep]` approach but mark steps as "parallel" and execute them with `asyncio.gather()` in code.
- **Pros**: Simpler implementation; no graph abstraction needed.
- **Cons**: No validation (cycles, missing deps); no graph visualization; no per-node retry policy; no declarative YAML workflows; parallelism logic scattered across code.
- **Why rejected**: The DAG model is only slightly more complex but provides significantly more structure, safety, and observability.

### Alternative 2: External workflow engine (Airflow, Prefect, Temporal)

- **Description**: Use an existing workflow orchestration platform.
- **Pros**: Battle-tested; scheduling, retries, monitoring built-in; web UI.
- **Cons**: Heavy infrastructure; Python agent would need to run as tasks in an external system; defeats "reference implementation" purpose; overkill for single-process agent.
- **Why rejected**: These tools are designed for distributed pipelines running over hours. Our workflows run in seconds-to-minutes in a single process.

### Alternative 3: Reactive execution (each node subscribes to dependencies)

- **Description**: Instead of a scheduler, each node waits for its dependencies and executes when they're ready.
- **Pros**: Fully decentralized; natural parallelism; no central scheduler needed.
- **Cons**: Hard to reason about; no global view of progress; difficult to implement retry/cancellation; event storms.
- **Why rejected**: A centralized scheduler is simpler to implement, debug, and observe.

## Related Decisions

- [ADR-006: Runtime Architecture](006-runtime-architecture.md) — Harness integrates Scheduler
- [ADR-008: Event-Driven Observability](008-event-driven-observability.md) — Scheduler emits events

## Notes

The Scheduler does NOT replace the Planner. The Planner produces a TaskGraph (or its output is converted to one). The Scheduler executes it.

Maximum practical parallelism: 10-20 concurrent skill executions. Beyond that, resource limiting in the Scheduler prevents overload.
