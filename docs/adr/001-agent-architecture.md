# Architecture Decision Record: Agent Architecture Pattern

**Status:** Accepted
**Decision:** #001
**Date:** 2026-07-28

## Context

The Tushare Investment Research Agent needs an architecture that balances structured workflow orchestration with flexible analytical reasoning. Investment research involves both predictable phases (data collection → analysis → verification → report) and unpredictable analytical paths (the specific analysis depends on the data retrieved).

We need an agent pattern that:

1. Makes the overall research workflow observable and controllable (phases, ordering, gates)
2. Allows flexible reasoning within each analysis step (LLM can adapt to data conditions)
3. Supports parallel execution of independent analyses (fundamental + technical simultaneously)
4. Enables independent versioning and replacement of individual analysis strategies
5. Recovers gracefully from tool failures mid-analysis

Three candidate agent patterns were evaluated: pure ReAct, Tool-Use, and Orchestrated.

## Decision

**Decision:** We will use a **Hybrid Orchestrated + ReAct** agent architecture.

The top-level is an **Orchestrated Agent** with three orchestrated stages (Planner → Executor → Verifier), and within the Executor stage, each skill invocation runs a **ReAct loop** (Think → Act → Observe).

## Rationale

- **Separation of planning from execution** makes the agent's intent observable before any action is taken. The Planner produces a structured plan that can be reviewed and approved before execution begins.
- **ReAct within skills** provides the flexibility needed for data-dependent analysis. An analyst doesn't know the valuation score until they see the PE ratio — the ReAct loop naturally handles this.
- **Parallel execution** of independent skills (fundamental, technical, valuation, risk) is natural in the Orchestrated pattern — step dependencies in the plan express this explicitly.
- **Skill isolation** means each strategy can be versioned, tested, and replaced independently. A change to the fundamental analysis model doesn't affect the technical analysis skill.
- **Verification as a separate stage** enforces a quality gate before report generation, catching errors before they reach the user.

## Consequences

### Positive

- Clear responsibility boundaries: each component has a well-defined job.
- Each stage is independently testable (Planner output, individual skill output, Verifier decisions).
- Skill swapping is safe — skills follow a fixed interface.
- The plan-first approach makes the agent's reasoning transparent.

### Negative

- More components to implement than a monolithic ReAct agent (higher initial build cost).
- Coordination overhead between Planner and Executor (the plan must be faithfully executed).
- Requires explicit error handling for each stage boundary.

### Neutral

- The Executor is the most complex component — it must interpret plans, invoke skills, and manage tool calls.
- Planning latency is added before execution begins (offset by parallel execution within skills).

## Alternatives Considered

### Alternative 1: Pure ReAct Agent

- **Description**: A single LLM loop that reasons and acts iteratively until the research report is complete.
- **Pros**: Simplest implementation; no stage boundaries; fully flexible.
- **Cons**: No observability into the plan before execution; hard to verify individual analysis quality; any prompt change affects the entire system; cannot parallelize skill execution.
- **Why rejected**: Lack of modularity and observability is unacceptable for a P8/P9 reference architecture.

### Alternative 2: Tool-Use Agent

- **Description**: The agent is given a set of tools and decides which to call based on user request. No separate planning phase.
- **Pros**: Simpler than full orchestration; tools are well-defined.
- **Cons**: No structured plan; hard to guarantee complete analysis coverage; no verification stage boundary.
- **Why rejected**: Too unstructured — investment research requires complete, systematic coverage of all analysis dimensions.

### Alternative 3: Microservice Agent (Agent Network)

- **Description**: Separate agents for each analysis type communicating asynchronously.
- **Pros**: Maximum isolation; independent scaling; natural parallel execution.
- **Cons**: High infrastructure cost; inter-agent communication complexity; over-engineering for reference project scope.
- **Why rejected**: Premature complexity; adds distributed system concerns (message ordering, delivery guarantees) without proportional benefit.

## Related Decisions

- [ADR-002: Skill System Design](002-skill-system.md)
- [ADR-004: MCP Integration Strategy](004-mcp-integration.md)

## Notes

The hybrid pattern is a well-established approach in production agent systems. It was documented in the engineering-ai-standards patterns before this decision. This ADR applies the pattern to the investment research domain with domain-specific adaptations (parallel skill execution, verification stage, report generation).
