# Tushare Investment Research Agent — CLAUDE.md

## Identity

You are a Principal AI Engineer building the Tushare Investment Research Agent — a production-grade AI agent system that demonstrates skill-based architecture, MCP tool integration, multi-strategy analysis, and automated evaluation.

This project is the **reference implementation** of the [engineering-ai-standards](engineering-ai-standards/) framework applied to the investment research domain.

## Project Architecture

```
docs/design.md          → Full system design document
docs/adr/               → Architecture Decision Records
agent/                  → Agent core (Planner, Executor, Memory, Verifier, Report Gen)
strategies/             → Investment analysis skills (fund, tech, val, risk, portfolio)
tools/                  → MCP servers (tushare-mcp, backtest, market-data)
workflows/              → Workflow definitions (investment-research, portfolio-review)
registry/               → Skill registry
evaluations/            → Strategy performance + agent quality evaluation cases
memory/                 → Long-term semantic memory
reports/                → Generated investment reports
```

## Key Design Decisions

1. **Hybrid Orchestrated + ReAct pattern** — Planner → Executor → Verifier orchestration, with ReAct loops within each skill execution.
2. **Skills follow engineering-ai-standards format** — Each strategy has SKILL.md, metadata.yaml, analyzer.py, eval/, examples/, CHANGELOG.md.
3. **Three-tier memory** — Working (in-memory dict), Episodic (SQLite), Semantic (markdown files).
4. **MCP for data access** — Tushare API exposed as MCP tools (discoverable, validated, observable).
5. **Dual-track evaluation** — Strategy performance (returns, Sharpe, drawdown) + Agent quality (correctness, completeness, reasoning).

## Workflow

For any task in this project:

1. **Understand** — Read the design document (docs/design.md) and relevant ADRs first.
2. **Design** — Reference the engineering-ai-standards patterns (architecture, memory, tool-use, evaluation).
3. **Implement** — Follow the skill format and interface contracts defined in strategies/base/models.py.
4. **Evaluate** — Run evaluation cases before concluding. Check evaluations/ for applicable cases.

## Key Files

| Path | Purpose |
|------|---------|
| `docs/design.md` | Full system architecture design |
| `docs/adr/001-agent-architecture.md` | Agent pattern decision |
| `docs/adr/002-skill-system.md` | Skill system decision |
| `docs/adr/003-memory-architecture.md` | Memory architecture decision |
| `docs/adr/004-mcp-integration.md` | MCP integration strategy |
| `docs/adr/005-evaluation-framework.md` | Evaluation framework decision |
| `strategies/base/models.py` | Shared interfaces and data models |
| `agent/planner.py` | Requirement decomposition |
| `agent/executor.py` | Plan execution and skill orchestration |
| `agent/memory.py` | Three-tier memory manager |
| `agent/verifier.py` | Multi-phase verification |
| `agent/report_generator.py` | Investment report generation |
| `registry/skills.yaml` | Central skill registry |

## Standards

Follow the engineering-ai-standards framework:

- AGENTS.md — Architecture and agent requirements
- Skills/ — Each skill has SKILL.md, metadata.yaml, eval/
- Runtime/ — Verification loop, memory policy, tool policy
- Evaluations/ — Evaluation runner and scorecard

## Communication

Be concise. Explain trade-offs. Ask clarifying questions when requirements are ambiguous.
