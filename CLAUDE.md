# Agentic Investment Research Platform — CLAUDE.md

## Identity

You are a Principal AI Engineer building the **Agentic Investment Research Platform** — a production-grade **Agent Platform** whose reference domain is investment research. It demonstrates the full agent-infrastructure stack: dynamic planning, a unified agent runtime, tool orchestration (MCP ecosystem), a RAG knowledge layer, persistent memory, trajectory evaluation, and observability.

This project is the **reference implementation** of the [engineering-ai-standards](engineering-ai-standards/) framework applied to the investment research domain. The platform core is domain-agnostic; the investment domain is a concrete implementation on top of it.

## Project Architecture

```
docs/design.md          → Full system design document (platform positioning)
docs/adr/               → Architecture Decision Records (001-015)
agent/                  → Smart Decision layer (dynamic Planner, Executor, Runtime Adapter, Verifier, Report Gen)
runtime/                → Framework Core (AgentRuntime, Scheduler, Graph, Snapshot, Tracing, RunRecorder)
strategies/             → Investment analysis skills (fund, tech, val, risk, portfolio)
skills/                 → Skill SDK (5-phase lifecycle)
tools/                  → External capability layer (ToolRegistry, Providers, Backtest, registry.d)
workflows/              → Workflow definitions (investment-research, portfolio-review)
registry/               → Skill registry
memory/                 → 7-tier memory (Research + retrieval.py RAG knowledge layer)
evaluations/            → Strategy performance + agent quality + trajectory evaluation
demo/                   → Platform capability demo script
reports/                → Generated investment reports
```

## Key Design Decisions

1. **Unified AgentRuntime (ADR-015)** — one lifecycle engine `create_task → plan → schedule → execute → aggregate → report`, domain-agnostic, with business components injected via `agent/runtime_adapter.py`.
2. **Dynamic Planning** — `Planner.plan_for_goal` decomposes a goal into a variable task set by intent keywords + tool capabilities (LLM first, rule fallback); no fixed workflow template.
3. **Metadata-driven Tool Registry** — tools declare JSON Schema/capability/source_type (local|mcp|api)/cost/rate_limit/cache_policy; the Planner discovers by capability.
4. **RAG Knowledge Layer** — `memory/retrieval.py` recalls prior research by company/industry/theme and persists results back for cross-session knowledge accumulation.
5. **Skills follow engineering-ai-standards format** — Each strategy has SKILL.md, metadata.yaml, analyzer.py, eval/, examples/, CHANGELOG.md.
6. **Provider isolation** — DataCollector is the only provider accessor; skills consume immutable `ResearchDataset` (replayable, PIT).
7. **Evaluation + Observability** — AgentRunStats (task/tool success, latency, token cost, evidence) from real spans; full chain `User Query → Planner → Agent → Tool → Retrieval → LLM → Result` observable in agent_trace.jsonl + Mermaid + CLI.

## Workflow

For any task in this project:

1. **Understand** — Read the design document (docs/design.md) and relevant ADRs first.
2. **Design** — Reference the engineering-ai-standards patterns (architecture, memory, tool-use, evaluation).
3. **Implement** — Follow the skill format and interface contracts defined in strategies/base/models.py.
4. **Evaluate** — Run evaluation cases before concluding. Check evaluations/ for applicable cases.

## Key Files

| Path | Purpose |
|------|---------|
| `docs/design.md` | Full system architecture design (platform) |
| `docs/adr/015-agent-runtime-unification.md` | Unified AgentRuntime decision |
| `runtime/agent_runtime.py` | Unified lifecycle engine + AgentRunStats |
| `agent/runtime_adapter.py` | Bridges AgentRuntime ↔ investment components |
| `agent/planner.py` | Dynamic Planner (plan_for_goal, intent decomposition) |
| `agent/executor.py` | AnalysisPlan → TaskGraph → Scheduler |
| `agent/llm.py` | LLM backend (token/latency spans) |
| `tools/registry.py` | Metadata-driven ToolRegistry (local/mcp/api) |
| `memory/retrieval.py` | RAG knowledge layer (company/industry/theme) |
| `memory/research.py` | Long-term research storage (SQLite) |
| `runtime/tracing/formatters.py` | CLI full-chain trace formatter |
| `agent/report_generator.py` | Plan-aware investment report generation |
| `agent/verifier.py` | Multi-phase verification (policy gate) |
| `strategies/base/models.py` | Shared interfaces and data models |
| `evaluations/trajectory/evaluator.py` | Trajectory evaluation scoring |
| `registry/skills.yaml` | Central skill registry |

## Standards

Follow the engineering-ai-standards framework:

- AGENTS.md — Architecture and agent requirements
- Skills/ — Each skill has SKILL.md, metadata.yaml, eval/
- Runtime/ — Verification loop, memory policy, tool policy
- Evaluations/ — Evaluation runner and scorecard

## Communication

Be concise. Explain trade-offs. Ask clarifying questions when requirements are ambiguous.
