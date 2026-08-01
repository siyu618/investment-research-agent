# Architecture Decision Record: Unified trace_span

**Status:** Accepted
**Decision:** #012
**Date:** 2026-08-01

## Context

Agent observability previously recorded trace entries by hand: the DataCollector had 8 `TraceRecord.make` call sites, the executor and CLI hand-rolled planner/verifier records. This produced inconsistent traces:

- `duration_ms=0` hardcoded on all success paths (real elapsed time never measured)
- empty `input_hash`/`output_hash` on verifier/planner records
- hardcoded `status="ok"` regardless of outcome
- the Mermaid execution graph always rendered nodes as `pending` (it read plan `status`, which never updates)

The Mermaid graph's `results` parameter was dead code — real per-node success/failure/retry state lived in the Scheduler's `GraphResult` but was never wired in.

## Decision

Introduce a unified `trace_span` async context manager (`runtime/tracing/trace_span.py`) that wraps any async operation and automatically records:

- real start/end timestamps and `duration_ms`
- input/output summary + stable SHA-256 hash (`SpanEntry.set_input`/`set_output`)
- exception → `status="error"` + error message (re-raised)
- `retry_count`, `token_usage` (set by caller)

All spans emit the same JSON shape as `TraceRecord.to_jsonl()`, so they append directly to `agent_trace.jsonl`.

Applied to: DataCollector (8 tool calls), executor skill_executor (incl. the previously-unrecorded `skill is None` path), CLI planner/verifier entries. The Mermaid graph now consumes the real `GraphResult` (per-node `success`/`retry_count`) instead of the dead `results` param.

## Rationale

- Single source of truth for timing/hashing/status — no manual `duration_ms=0` drift.
- All hashes use stable SHA-256 (`hash_of`), consistent with replay equivalence checking.
- The real Scheduler node results were already computed but disconnected; wiring them makes the graph truthful.
- Context-manager form is hard to misuse: timing brackets the actual work, exceptions are captured automatically.

## Consequences

### Positive

- Every trace record has real duration and content hashes (verified by tests: `tests/runtime/test_trace_span.py`).
- Mermaid graph shows actual ✓/✗/! node states (verified end-to-end).
- `skill is None` and verifier/planner failures are no longer silent.

### Negative

- `trace_span` is async-only; sync call sites (if any) need a sync variant or wrapping.
- Hash semantics changed for tool records (now over real rows, not `{"rows": N}`) — replay equivalence tests cover the impact.

### Neutral

- `TraceRecord` still exists for the memory/event paths that use it; `trace_span` is the recommended path for new spans.

## Alternatives Considered

### Alternative 1: Fix each call site manually
Add `time.monotonic()` around each of the 8+ sites. Pro: no new abstraction. Con: 8+ near-duplicate timing blocks; easy to miss one; no shared error handling. Rejected.

### Alternative 2: Decorator-based
A `@trace` decorator on provider methods. Pro: terse. Con: doesn't work for spans that need to record input before and output after an `await` with intermediate steps; async decorators complicate signatures. Rejected in favor of context manager.

## Related Decisions

- [ADR-008: Event-Driven Observability](008-event-driven-observability.md)
- [ADR-013: Point-in-Time](013-point-in-time.md)
