# Architecture Decision Record: Event-Driven Observability

**Status:** Accepted
**Decision:** #008
**Date:** 2026-07-29

## Context

The current system has no structured observability. Debugging an agent run requires reading console output, checking log files, or adding temporary print statements. This is inadequate for a production-grade agent framework for several reasons:

1. **No execution trace**: After a run completes, there is no record of what happened, in what order, or how long each step took.
2. **No tool call audit**: If a tool call fails, there is no structured record of the input, output, or error.
3. **No debugging support**: Developers cannot replay a session to understand agent behavior.
4. **No metrics**: Latency, success rates, tool usage counts — none of these are tracked.
5. **No error aggregation**: Errors are logged ad-hoc, making it hard to identify patterns.

Modern agent runtimes (Claude Code, OpenAI Deep Research, LangGraph) all provide event-based observability. The engineering-ai-standards runtime patterns mention observability as a requirement but don't prescribe implementation.

## Decision

**Decision:** We will implement a fully event-driven observability system in `runtime/tracing/` based on:

### Core Abstractions

```python
@dataclass
class Event:
    """Every state change in the system is an Event."""
    id: str                 # UUID
    type: str               # "PlanningStarted" | "ToolInvoked" | ...
    timestamp: str          # ISO-8601
    correlation_id: str     # Links events across components
    parent_id: Optional[str]  # Parent event for nesting
    payload: dict           # Type-specific data
    metadata: dict          # Additional context (session_id, agent_version)
```

### EventBus

```python
class EventBus:
    """In-process event bus with subscribe/replay/export."""

    def emit(self, event: Event) -> None:
        """Emit an event to all subscribers."""

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Subscribe to events matching a type pattern.
        Patterns: "ToolInvoked" (exact), "Tool*" (prefix), "*" (all).
        """

    def replay(self, session_id: str) -> AsyncIterator[Event]:
        """Replay all events from a session in order."""

    def export_trace(self, session_id: str) -> list[dict]:
        """Export full trace as JSON for evaluation or visualization."""
```

### Event Catalog

All events emitted by the runtime are documented in `runtime/tracing/event_types.py`. Events are organized by source component:

| Source | Events |
|--------|--------|
| Harness | PlanningStarted, PlanningCompleted, WorkflowStarted, WorkflowFinished |
| Scheduler | GraphResolved, NodeStarted, NodeCompleted, NodeFailed, NodeRetried |
| ToolRegistry | ToolInvoked, ToolFinished, ToolFailed, ToolCacheHit, ToolCacheMiss |
| Skill | SkillStarted, SkillCompleted, SkillVerifying, SkillVerificationDone |
| Memory | MemoryRead, MemoryWritten, MemoryCacheHit, MemoryCacheMiss |
| Verifier | VerificationStarted, VerificationCheck, VerificationCompleted |
| ReportGenerator | ReportGenerated |
| Base | ErrorEncountered, WarningEmitted, UserFeedbackRequested |

### Consumers

Event consumers are pluggable LifecycleHooks:

| Consumer | Purpose | Implementation |
|----------|---------|----------------|
| ConsoleTracer | Human-readable trace output | `runtime/tracing/formatters.py` |
| JSONExporter | Structured event export | `runtime/tracing/exporters.py` |
| TrajectoryEvaluator | Score execution path | `evaluations/trajectory/evaluator.py` |
| ReplayEngine | Re-run analysis of events | `runtime/tracing/replay.py` |

### CLI Integration

```bash
# Full trace output
python -m agent --requirement "Analyze ..." --trace

# Export as JSON for analysis
python -m agent --requirement "Analyze ..." --trace-export trace.json

# Replay a previous session for debugging
python -m agent --replay session-a1b2c3d4
```

## Rationale

- **Events are the right abstraction**: Every significant state change in an agent system can be represented as an event. Events are composable, storable, and replayable.
- **Decouples producers from consumers**: The ToolRegistry doesn't need to know about logging, metrics, or tracing. It just emits events. Consumers subscribe to what they care about.
- **Enables trajectory evaluation**: The full execution trace (events in order) is the input to trajectory evaluation. Without events, we cannot score the execution path.
- **Standard debugging pattern**: Event-based tracing is the standard in modern systems (Node.js EventEmitter, React DevTools, Azure Event Grid). Developers already understand the pattern.
- **Future-proof**: Events can be streamed to OpenTelemetry, written to a database, served to a web UI, or fed to a debugger — all without changing the emitting code.

## Consequences

### Positive

- Full execution trace for every run, stored and replayable.
- Tool call audit trail (every call logged with input, output, duration, success/failure).
- Latency breakdown per step, per tool, per skill.
- Error aggregation: all errors are typed and attributed to a source.
- Debugging sessions without reproducing: just replay the events.
- Trajectory evaluation becomes possible (needs the event trace).

### Negative

- Event emission adds overhead (~0.1ms per event). For a typical run (50-200 events), this is 5-20ms — negligible.
- Event storage requires disk space (~1KB per event). A 200-event session uses ~200KB. Acceptable for reference scale.
- Subscription pattern can lead to memory leaks if subscribers are not properly cleaned up. Mitigated by having a fixed, well-known set of subscribers.

### Neutral

- Events are in-process only initially. Cross-process event streaming (to a database or UI) is a future concern.
- The EventBus interface is stable. The implementation can evolve from in-process dict to Redis/PostgreSQL without changing emitting code.

## Alternatives Considered

### Alternative 1: Python logging only

- **Description**: Use `logging.debug/info/warning/error` throughout the codebase with structured logging (extra= dict).
- **Pros**: Zero new infrastructure; familiar to all Python developers; works with existing log aggregators.
- **Cons**: Logs are strings, not typed events; no subscribe/replay/export API; no correlation_id propagation by default; no event hierarchy (parent_id); hard to build trajectory evaluation from log strings.
- **Why rejected**: Logging is an output channel, not an observability architecture. Events can be logged, but logging alone cannot provide the structured, typed, queryable events needed for trajectory evaluation.

### Alternative 2: OpenTelemetry

- **Description**: Use OpenTelemetry Tracing SDK for spans, events, and metrics.
- **Pros**: Industry standard; rich ecosystem; export to Jaeger, Zipkin, etc.
- **Cons**: Heavy dependency; designed for distributed tracing (service→service), not in-process agent events; span model (parent/child) is close but not identical to agent event model; adds significant configuration overhead.
- **Why rejected**: OpenTelemetry is a better choice when the agent runs in a distributed environment. For our single-process reference architecture, a lightweight EventBus is more appropriate. We can add an OTel exporter later if needed.

### Alternative 3: Callback-based (no events)

- **Description**: Pass callback functions to each component for observability (e.g., `on_tool_call=my_handler`).
- **Pros**: Explicit; no event dispatch overhead; type-safe per callback.
- **Cons**: Extending observability requires adding a new callback parameter to every component; N callbacks per component = N parameters; no replay support; no event history; callback explosion ("I need a callback for when the tool starts, when it finishes, when it fails, when it's retried...").
- **Why rejected**: Callbacks don't scale. For 3-4 hooks they're fine. For 20+ event types, events are strictly better.

## Related Decisions

- [ADR-006: Runtime Architecture](006-runtime-architecture.md) — Events are emitted by the Harness
- [ADR-010: Trajectory Evaluation](010-trajectory-evaluation.md) — Trajectory evaluation consumes events
- engineering-ai-standards: `runtime/verification-loop.md`

## Notes

Event design principles:
1. **Events are facts, not opinions**: An event says "Tool X was invoked with these parameters" — not "Tool X was invoked correctly."
2. **Events are immutable**: Once emitted, an event should never change. New events supersede old ones.
3. **Events are typed**: The `type` field is a stable identifier. Consuming code should switch on type, not parse.
4. **Correlation IDs connect events**: Every event in a workflow run shares the same `correlation_id`. This enables trace reconstruction.
5. **Events are cheap to create**: ~1KB each, ~0.1ms to emit. Never hesitate to add an event.
