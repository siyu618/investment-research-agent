# Architecture Decision Record: Skill System Design

**Status:** Accepted
**Decision:** #002
**Date:** 2026-07-28

## Context

The investment agent performs multi-strategy analysis (fundamental, technical, valuation, risk, portfolio selection). These strategies differ in their analytical approach, data requirements, and output format. We need a system for defining, versioning, discovering, and executing these strategies that is:

1. Consistent with the existing engineering-ai-standards skill framework
2. Independently versionable (a change to fundamental analysis doesn't affect technical analysis)
3. Evaluable per strategy (each strategy has its own evaluation cases and metrics)
4. Discoverable by the agent at runtime (the Executor needs to know what skills exist)
5. Composable into multi-step workflows

## Decision

**Decision:** Each investment strategy will be implemented as a **skill module** following the engineering-ai-standards skill format, with a Python abstract base class defining the skill interface.

Each skill lives under `strategies/<strategy-name>/` and contains:
- `SKILL.md` — LLM-readable instruction file with YAML frontmatter (metadata, version, dependencies)
- `metadata.yaml` — Machine-readable metadata for the registry
- `analyzer.py` — Python implementation of the analysis logic
- `prompt.md` — LLM prompt template for the ReAct loop within this skill
- `eval/` — Per-skill evaluation cases
- `examples/` — Example inputs and outputs
- `CHANGELOG.md` — Version history with backtest results

Skills are registered in a central `registry/skills.yaml` (extending the engineering-ai-standards registry format).

## Rationale

- **Consistency with engineering-ai-standards**: Reusing the established skill format means evaluation tools, CI workflows, and governance processes work without modification.
- **Independent versioning**: Each strategy evolves at its own pace. A fundamental analysis model improvement doesn't require re-releasing the technical analysis skill.
- **Pluggability**: The abstract base class (`InvestmentSkill`) defines a clean interface. New strategies are added by creating a new module implementing this interface — no changes to the Executor.
- **LLM-readable instruction**: `SKILL.md` serves as the system prompt when the LLM runs this skill, ensuring the agent correctly applies the strategy methodology.
- **Evaluation per strategy**: Strategy-specific evaluation cases measure whether that skill produces correct, complete, and explainable analyses.

## Consequences

### Positive

- Skills are self-contained — a developer can work on a single strategy without understanding the full system.
- Skill swapping is safe: as long as the interface is satisfied, the Executor can use the skill.
- Evaluation granularity: per-skill evaluation identifies exactly which strategy regressed.
- Registry enables tooling: `python -m tools.registry list-skills`, `validate`, etc.

### Negative

- Boilerplate: each skill requires 7+ files (SKILL.md, metadata.yaml, analyzer.py, prompt.md, eval/, examples/, CHANGELOG.md).
- Interface discipline: all skills must adhere to the `AnalysisContext` → `AnalysisResult` contract. If the contract changes, all skills need updating.
- Skill discovery is file-system based — not suitable for dynamic runtime loading in a distributed system (acceptable for this scope).

### Neutral

- The skill format is more structured than a simple Python function call — but the structure enables evaluation and versioning.
- SKILL.md may duplicate some information in analyzer.py (both describe what the skill does) — but they serve different audiences (LLM vs developer).

## Alternatives Considered

### Alternative 1: Single monolithic analysis module

- **Description**: One Python module with separate functions for each analysis type, no skill metadata.
- **Pros**: Simpler; fewer files; faster to implement.
- **Cons**: Cannot version strategies independently; no evaluability per strategy; no LLM-readable instructions; doesn't follow engineering-ai-standards.
- **Why rejected**: Violates the project goal of being a reference AI Agent implementation.

### Alternative 2: Plugin architecture with dynamic discovery

- **Description**: Skills are Python packages discovered via entry points (setuptools), dynamically loaded at runtime.
- **Pros**: Maximum extensibility; no registry maintenance; third-party skills possible.
- **Cons**: Over-engineered for current scope; adds packaging complexity; dynamic loading needs careful security consideration.
- **Why rejected**: Premature. File-based discovery with a YAML registry is sufficient and standard-compliant.

### Alternative 3: MCP-based skill execution

- **Description**: Each skill is a separate MCP server, invoked by the Executor via MCP protocol.
- **Pros**: Language-agnostic; network-decoupled; maximum isolation.
- **Cons**: Significant operational overhead; each skill needs its own server process; latency per skill call.
- **Why rejected**: Over-engineering for a reference project. MCP is used for data access (Tushare), not for skill execution.

## Related Decisions

- [ADR-001: Agent Architecture](001-agent-architecture.md) (Executors invoke skills)
- [ADR-005: Evaluation Framework](005-evaluation-framework.md) (per-skill evaluation)
- engineering-ai-standards: `registry/skills.yaml`, `skills/<name>/SKILL.md`

## Notes

The skill interface (`InvestmentSkill`) and context/result models (`AnalysisContext`, `AnalysisResult`) are defined in `strategies/base.py`. All new skills import from this base module. If the interface needs to evolve, a major version bump with migration period is the standard approach.
