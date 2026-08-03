# ADR-015: Unified Agent Runtime

**Status:** Accepted
**Date:** 2026-08-03

## Context

The codebase evolved two parallel lifecycle engines:

- **Harness** (`runtime/harness.py`) — the production path: `Plan → Execute → Verify → Report`, wired into the CLI, producing 12 run artifacts + deterministic replay.
- **AgentRuntime** (`runtime/agent_runtime.py`) — a newer, domain-agnostic engine: `create_task → plan → schedule → execute → aggregate → report`, with injected planner/scheduler/reporter and real trace spans. It collected `AgentRunStats` (task/tool success, latency, token cost, evidence) but was **orphaned**: not exported, not wired to the CLI, not tested.

Meanwhile the platform capabilities the AgentRuntime was designed to orchestrate — ToolRegistry, the RAG knowledge layer, LLM telemetry, dynamic planning (`plan_for_goal`) — were all **dormant** in the production path:

- The CLI never constructed a `ToolRegistry`; the provider was called directly.
- No memory/retrieval was injected; re-analyzing a company couldn't read prior research.
- `LLMBackend._complete` discarded the API `usage` field, so token cost/latency were invisible.
- The Planner's dynamic decomposition was never used on the default path.

Two lifecycle engines, two observability streams (span-sink vs EventBus), and a production path blind to the platform's own infrastructure.

## Decision

**Unify onto `AgentRuntime` as the single lifecycle engine.** The CLI now drives `AgentRuntime`; the domain components (Planner, Executor, Verifier, ReportGenerator) are injected through a thin adapter (`agent/runtime_adapter.py`):

```
AgentRuntime (domain-agnostic)
  ├── planner     ← Planner.plan_for_goal (dynamic, tool-aware)
  ├── scheduler   ← InvestmentExecutorAdapter (AnalysisPlan → TaskGraph → Scheduler)
  ├── aggregator  ← InvestmentVerifierStage (policy-gated verification)
  └── reporter    ← InvestmentReporterStage (ReportGenerator.generate)
```

**Interface contracts:**
- The runtime requires a planner with `plan_for_goal(goal, tools, span_sink)` (dynamic) or `create_plan`.
- The scheduler adapter exposes `run(plan, ctx)`; the runtime passes an `AnalysisPlan` (not a `TaskGraph`) — the adapter owns the plan→graph conversion.
- The aggregator stage runs the domain Verifier and raises `FatalError` on a failed policy gate (verification still gates the report).
- The reporter stage runs `ReportGenerator.generate` with the verification in scope.
- The runtime mirrors its run `ctx` back into the caller's context dict, so the caller reads the `verification` and `plan` after `run()` returns.

**Platform wiring (all in `agent/__main__.py`):**
- `ToolRegistry.register_from_provider(provider)` + `register_from_yaml("tools/registry.d")` → Planner tool discovery.
- `KnowledgeRetriever.recall(goal, span_sink)` before planning → RAG recall; `store_result(...)` after → persistence.
- `LLMBackend._complete(..., span_sink)` → `kind="llm"` spans with token usage.
- `runtime.collect_stats(task)` after merging executor tool/skill spans → `AgentRunStats` persisted in `meta.json` + `result_manifest.execution_stats`.
- `--eval-trajectory runs/{id}` scores a recorded run's trajectory from its real spans.

## Consequences

**Positive**
- One lifecycle engine, one span sink, one observability story: `User Query → Planner → Agent → Tool → Retrieval → LLM → Verifier → Final Result` is fully captured in `agent_trace.jsonl`.
- The platform capabilities (ToolRegistry, RAG, LLM telemetry, dynamic planning) are exercised on the default path — the reference implementation actually demonstrates them.
- `AgentRunStats` feeds real execution-quality metrics (task success, tool success, latency, token cost, evidence count) into every run artifact.
- Replay is preserved: the latest runs replay `PASSED` through the existing `ForbiddenProvider` path.
- Backward compatible: `Harness` remains for non-investment agents; `test_verification_persist` still exercises it.

**Negative / Trade-offs**
- Two engines still coexist in the repo (`Harness` kept for backward compat), which adds a small conceptual surface. Documented here so future readers know AgentRuntime is the primary path.
- The adapter layer is a thin bridge; its contract (runtime passes `AnalysisPlan`, not `TaskGraph`) means the executor's plan→graph conversion lives outside the runtime.

## Alternatives

1. **Keep Harness + add a demo entry point** — lower risk, but leaves two paths in production and keeps the platform capabilities dormant on the default path.
2. **Evolve Harness** — would bolt memory/tools/plan_for_goal/LLM spans onto the Plan→Execute→Verify→Report shape, but Harness couples to the investment domain's method names (`planner.create_plan`, `executor.execute_plan`); AgentRuntime was already the domain-agnostic shape.
