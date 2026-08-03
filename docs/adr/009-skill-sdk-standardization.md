# Architecture Decision Record: Skill SDK Standardization

**Status:** Accepted
**Decision:** #009
**Date:** 2026-07-29

## Context

The current skill interface (`InvestmentSkill` in `strategies/base/models.py`) defines a single method:

```python
class InvestmentSkill(ABC):
    async def analyze(self, context: AnalysisContext) -> AnalysisResult: ...
    def get_metadata(self) -> dict: ...
```

This interface has several limitations:

1. **Single-phase execution**: Skills only have `analyze()`. There is no `plan()`, `verify()`, or `summarize()` phase. This means skills cannot decompose their own work, self-verify their output, or produce human-readable summaries.
2. **No declarative metadata**: `get_metadata()` returns a raw dict. There's no schema for what metadata should contain, and consumers must guess at its structure.
3. **Domain coupling**: The interface is specifically `InvestmentSkill` with `AnalysisContext` and `AnalysisResult`. A different domain cannot reuse this interface.
4. **No lifecycle**: Skills have no hooks for initialization, cleanup, or error handling.
5. **No data requirement declaration**: Skills cannot declaratively state "I need income statements and balance sheets for 3 periods." The executor must know this out-of-band.

## Decision

**Decision:** We will create a new universal skill SDK in `skills/base/skill_sdk.py` with a 5-phase lifecycle and a compatibility adapter for existing skills.

### New Skill Lifecycle

```python
class SkillLifecycle(ABC):
    """Standardized lifecycle for all skills."""

    @abstractmethod
    def metadata(self) -> SkillMetadata:
        """Declare skill identity, capabilities, and requirements."""
        ...

    @abstractmethod
    async def plan(self, context: dict) -> SkillPlan:
        """Given execution context, decide what sub-steps to perform."""
        ...

    @abstractmethod
    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        """Execute the core analysis and return results."""
        ...

    @abstractmethod
    async def verify(self, context: dict, output: SkillOutput) -> SkillVerdict:
        """Self-verify: is the output consistent with input data?"""
        ...

    @abstractmethod
    async def summarize(self, output: SkillOutput) -> str:
        """Produce human-readable summary."""
        ...
```

### Legacy Compatibility

```python
class LegacySkillAdapter(SkillLifecycle):
    """Wraps an existing InvestmentSkill into the new SkillLifecycle.

    Legacy skills lose plan/verify/summarize capabilities but
    continue to work without modification.
    """

    def __init__(self, skill: InvestmentSkill):
        self._skill = skill

    async def execute(self, context, plan) -> SkillOutput:
        old_ctx = AnalysisContext(**context)
        result = await self._skill.analyze(old_ctx)
        return SkillOutput(
            score=result.score,
            data=result.supporting_data,
            reasoning=result.reasoning,
            warnings=result.warnings,
        )

    # plan() → empty plan (no decomposition)
    # verify() → always pass (no self-verification)
    # summarize() → returns existing reasoning text
```

### SkillMetadata Schema

```python
class SkillMetadata:
    name: str
    version: str
    description: str
    category: str                # "analysis" | "orchestration" | "data" | "verification"
    tags: list[str]
    input_schema: dict           # JSON Schema for expected context
    output_schema: dict          # JSON Schema for produced output
    data_requirements: list[str] # e.g., ["income_statement", "balance_sheet", "daily_price"]
    timeout: int                 # Default execution timeout (seconds)
    cost: float                  # Relative compute cost (1.0 = baseline)
    dependencies: list[str]      # Other skills this depends on
```

## Rationale

- **5-phase lifecycle aligns with agent research**: Academic and industry agent frameworks (LangGraph, AutoGen, Semantic Kernel) converge on multi-phase skill execution with explicit plan/execute/verify phases.
- **Declarative metadata enables discovery**: The Planner can discover skills by `data_requirements` — "I need to analyze income statements → skill with data_requirements=['income_statement']". This is essential for automatic workflow construction.
- **Self-verification improves reliability**: A skill that checks its own output ("Does this PE ratio pass sanity check?") catches errors before they propagate.
- **Legacy adapter ensures backward compatibility**: All 5 existing skills continue to work. New skills use the full SDK.
- **Domain-agnostic**: The SkillLifecycle uses generic `dict` for context I/O, not `AnalysisContext`. A non-investment skill can use the same interface.

## Consequences

### Positive

- New skills get plan/verify/summarize for free.
- Existing skills keep working with zero modifications.
- The Planner can discover skills by capability.
- Skill metadata is now schema-validated, not a raw dict.
- The interface is universal — any domain can implement it.

### Negative

- More methods to implement for new skills (5 vs 1).
- Legacy adapter loses plan/verify/summarize capabilities (acceptable — legacy skills are migrated on their own schedule).
- Generic `dict` I/O loses type safety compared to typed `AnalysisContext`.

### Neutral

- The 5-phase lifecycle is recommended, not required. Skills can leave `plan()` empty or `verify()` as always-pass.
- Migration of existing skills to native `SkillLifecycle` is a best-effort task, not a blocker.

## Alternatives Considered

### Alternative 1: Keep single `analyze()` method, add optional hooks

- **Description**: Keep the existing interface but add optional `verify()` and `summarize()` methods with default no-op implementations.
- **Pros**: Minimal change; backward compatible without adapter.
- **Cons**: Doesn't solve discoverability (metadata still a raw dict); doesn't solve domain coupling; optional methods are less discoverable than abstract methods.
- **Why rejected**: The existing interface's problems go beyond missing verify/summarize. The metadata structure and domain coupling need addressing.

### Alternative 2: Protocol/structural typing instead of ABC

- **Description**: Define SkillLifecycle as a Protocol (structural subtyping) instead of an ABC. Any object with the right methods is a skill.
- **Pros**: Duck typing; no forced inheritance; easier to test (mock = any object with the methods).
- **Cons**: Less explicit; harder to document; no `isinstance` checks; Python Protocol has limitations with async methods.
- **Why rejected**: ABC with abstract methods is more explicit and provides better developer experience (IDE support, error messages on missing methods). The Framework should be explicit.

### Alternative 3: Separate skill interface per category

- **Description**: Different interfaces for analysis skills, data skills, orchestration skills, verification skills.
- **Pros**: Interface matches capability; no wasted no-op methods.
- **Cons**: Many interfaces to learn; skill categorization changes; hard to write generic runtime code that handles any skill.
- **Why rejected**: One unified interface is simpler for the runtime and more flexible for the future. Skills can no-op phases they don't need.

## Related Decisions

- [ADR-002: Skill System Design](002-skill-system.md) — Original skill design
- [ADR-006: Runtime Architecture](006-runtime-architecture.md) — Harness calls skill lifecycle
- engineering-ai-standards: `skills/ai-agent-development/SKILL.md`

## Notes

The `data_requirements` field in SkillMetadata is a key enabler for automatic tool discovery (Phase 3 of the evolutionary roadmap). When a skill declares `data_requirements=["income_statement", "balance_sheet"]`, the Planner can query the ToolRegistry for tools with matching capabilities and automatically construct the data collection sub-graph.
