# Architecture Decision Record: Runtime/Harness Architecture

**Status:** Accepted
**Decision:** #006
**Date:** 2026-07-29

## Context

The current agent core (`agent/planner.py`, `agent/executor.py`, `agent/verifier.py`, `agent/report_generator.py`) embeds both business logic (investment analysis) and execution concerns (lifecycle management, retry, error handling, timing) in the same classes. This creates several problems:

1. **Cross-cutting concerns are duplicated**: If both the Executor and Verifier need retry logic, each must implement it separately.
2. **Business logic is not testable without runtime**: Testing the Planner requires mocking the entire agent environment.
3. **Observability is ad-hoc**: There is no centralized event emission. Adding logging requires modifying each component.
4. **No lifecycle management**: No hooks for "before step", "after step", "on error" — making it hard to add metrics, audit trails, or debugging.
5. **Domain coupling**: The agent components know they're doing "investment research" — they can't be reused for another domain.

The engineering-ai-standards runtime patterns describe a verification loop and memory policy but do not prescribe a runtime architecture.

## Decision

**Decision:** We will extract all cross-cutting runtime concerns into a new `runtime/` package with these components:

### `runtime/harness.py` — Unified Agent Runtime

The Harness owns the full agent lifecycle:

```
on_start
  → plan()          [calls Planner]
  → on_planning_done
  → execute()       [calls Scheduler → Skills → Tools]
  → on_execution_done
  → verify()        [calls Verifier]
  → on_verification_done
  → report()        [calls ReportGenerator]
  → on_report_done
→ on_finish
```

Every step is wrapped with:
- **Retry**: Recoverable errors are retried with exponential backoff.
- **Timeout**: Each step has a configurable timeout.
- **Error classification**: Errors are classified as Recoverable, Fatal, Timeout, or RateLimited.
- **Event emission**: Every step emits typed Events to the EventBus.
- **Context propagation**: An `ExecutionContext` flows through every call, providing correlation_id, session_id, and config.

### `runtime/lifecycle.py` — Lifecycle Hooks

Lifecycle hooks are the extension point for cross-cutting concerns:

```python
class LifecycleHook:
    async def on_event(self, event: Event): ...       # Logging, metrics
    async def on_error(self, context, error): ...      # Error reporting
    async def on_timeout(self, context, step): ...     # Timeout handling
```

Built-in hooks: LoggingHook (console), MetricsHook (counters), TraceHook (event recording for replay).

### `runtime/tracing.py` — Event System

The EventBus is the central nervous system of the runtime. All components emit events, and any component can subscribe to events it cares about. This replaces ad-hoc logging with structured, typed, subscribable events.

### `runtime/errors.py` — Error Taxonomy

Errors are classified so the Harness knows how to handle them:

| Error Class | Handling | Example |
|-------------|----------|---------|
| `RecoverableError` | Retry with backoff | Rate limit, transient API failure |
| `FatalError` | Fail immediately | Missing API token, invalid config |
| `TimeoutError` | Retry once, then fail | Tool timeout |
| `SkillError` | Log and continue | Skill-specific failure |

### `runtime/cache.py` — Generic Cache

A cache provider interface with a built-in TTL implementation. Used by the ToolRegistry (Phase 3) and memory (Phase 4).

## Rationale

- **Separation of concerns**: The `runtime/` package owns all cross-cutting concerns. Business code (`agent/`, `strategies/`) owns none of them. This is the foundation of "Framework First."
- **Lifecycle hooks enable extensibility**: Without hooks, adding metrics requires modifying every component. With hooks, you add one hook class and register it.
- **Event system enables observability**: Every state change is an Event. Events can be logged, traced, replayed, exported, or served to a UI — all without changing business code.
- **Error taxonomy enables recovery**: Classifying errors at the source lets the runtime make intelligent recovery decisions. A rate limit error should be retried; a missing token should not.
- **Thin abstraction**: The Harness is intentionally thin. It doesn't implement business logic — it orchestrates it. This prevents framework bloat.

## Consequences

### Positive

- Business logic becomes testable: Planner, Verifier, and ReportGenerator can be unit-tested with mock data and no runtime.
- Adding observability (metrics, tracing, audit) requires only adding a LifecycleHook — no business code changes.
- The Harness can be reused for any domain. Swap the Planner/Skills/Verifier and you have a different agent.
- Error recovery is centralized and consistent. No component needs to implement retry logic.
- New cross-cutting concerns (circuit breakers, rate limiters, budget tracking) can be added as lifecycle hooks.

### Negative

- One more abstraction layer. New developers must understand both `runtime/` and `agent/`.
- Harness assumes a specific lifecycle (Plan → Execute → Verify → Report). Domains with different lifecycles need a new harness or configurable hooks.
- Event emission adds overhead (~0.1ms per event). Not significant for agent workloads but measurable at high throughput.

### Neutral

- The Harness starts with one concrete lifecycle. If multiple lifecycles emerge, the pattern is to extract a base class.
- The `agent/` components become "strategies" that the Harness calls. This reframing is conceptual — the code largely stays as-is.

## Alternatives Considered

### Alternative 1: Keep current architecture, add decorators

- **Description**: Instead of a Harness, use Python decorators (`@retry`, `@timeout`, `@trace`) on existing methods.
- **Pros**: Minimal structural change; decorators are well-understood Python patterns.
- **Cons**: Decorators don't provide lifecycle management; no centralized error taxonomy; events are emitted per-method, not per-step; cross-cutting concerns still live in business code.
- **Why rejected**: Decorators solve the "add retry" problem but not the "observe the full lifecycle" problem. The Harness provides structure beyond what decorators can offer.

### Alternative 2: Use an existing framework (LangChain, LangGraph)

- **Description**: Replace the agent core with a third-party agent framework.
- **Pros**: Battle-tested; rich ecosystem; many built-in tools.
- **Cons**: Framework lock-in; doesn't demonstrate our own engineering-ai-standards; the project is a *reference implementation*, not a production system; third-party frameworks have their own opinions about lifecycle, memory, and evaluation.
- **Why rejected**: The project's primary goal is to be a reference implementation of engineering-ai-standards. Using an external framework would undermine this goal and limit our ability to demonstrate our own architecture decisions.

### Alternative 3: Message-passing between agent components

- **Description**: Planner, Executor, Verifier, and ReportGenerator are independent services that communicate via a message queue.
- **Pros**: Maximum decoupling; natural parallelism; service-level isolation.
- **Cons**: Heavy infrastructure (message broker, serialization, service discovery); over-engineering for a single-process agent; latency overhead.
- **Why rejected**: Premature distribution. The single-process Harness with event-driven communication provides sufficient decoupling without distributed system complexity.

## Related Decisions

- [ADR-001: Agent Architecture](001-agent-architecture.md) — Original agent pattern decision
- [ADR-007: DAG-based Workflow Engine](007-dag-workflow-engine.md) — Scheduler builds on Harness
- [ADR-008: Event-Driven Observability](008-event-driven-observability.md) — Event system details

## Notes

The Harness is designed to be the **only** component that imports `runtime/` internals. `agent/` components should never import from `runtime/` directly — they receive context and return results through the Harness interface. This prevents circular dependencies and keeps the boundary clean.
