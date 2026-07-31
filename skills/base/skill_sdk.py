# Skill SDK — Standardized lifecycle for all skills
#
# Every skill follows a 5-phase lifecycle:
#   1. metadata()   — Declare identity, schema, data requirements
#   2. plan()       — Given execution context, decide sub-steps
#   3. execute()    — Core analysis logic
#   4. verify()     — Self-verify output consistency
#   5. summarize()  — Produce human-readable summary
#
# Usage:
#     class MySkill(SkillLifecycle):
#         def metadata(self) -> SkillMetadata: ...
#         async def plan(self, context: dict) -> SkillPlan: ...
#         async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput: ...
#         async def verify(self, context: dict, output: SkillOutput) -> SkillVerdict: ...
#         async def summarize(self, output: SkillOutput) -> str: ...

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ─── Lifecycle Status ────────────────────────────────────────────────────


class SkillStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


# ─── Metadata ────────────────────────────────────────────────────────────


@dataclass
class SkillMetadata:
    """Rich metadata for skill discovery and scheduling.

    Declared once by the skill; consumed by the Planner, Scheduler,
    and ToolRegistry for automatic orchestration.
    """
    name: str
    version: str
    description: str
    category: str                        # "analysis" | "data" | "orchestration" | "verification"
    tags: list[str] = field(default_factory=list)

    # JSON Schema for expected input context
    input_schema: dict = field(default_factory=dict)

    # JSON Schema for produced output
    output_schema: dict = field(default_factory=dict)

    # Declarative data requirements — enables Planner to discover
    # which tools/skills are needed for a given analysis
    data_requirements: list[str] = field(default_factory=list)

    # Execution constraints
    timeout: int = 60                     # Default timeout in seconds
    cost: float = 1.0                     # Relative compute cost (1.0 = baseline)

    # Dependencies on other skills
    dependencies: list[str] = field(default_factory=list)

    # Which tools this skill typically consumes
    tool_requirements: list[str] = field(default_factory=list)


# ─── Plan ────────────────────────────────────────────────────────────────


@dataclass
class SkillPlan:
    """Sub-steps that the skill intends to execute.

    The runtime can inspect this plan for observability.
    """
    steps: list[dict] = field(default_factory=list)
    data_needed: list[str] = field(default_factory=list)
    tools_needed: list[str] = field(default_factory=list)
    estimated_duration: int = 30          # seconds


# ─── Output ──────────────────────────────────────────────────────────────


@dataclass
class SkillOutput:
    """Standardised output from any skill.

    `data` carries the domain-specific result.
    `artifacts` carries generated files (reports, charts, etc.).
    """
    score: float | None = None         # 0.0 - 1.0 (if applicable)
    confidence: float | None = None    # 0.0 - 1.0
    data: dict = field(default_factory=dict)
    reasoning: str = ""
    warnings: list[str] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ─── Verdict ──────────────────────────────────────────────────────────────


@dataclass
class SkillVerdict:
    """Result of a skill's self-verification."""
    passed: bool = True
    checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ─── Skill Lifecycle ABC ────────────────────────────────────────────────


class SkillLifecycle(ABC):
    """Standardised lifecycle for all skills in the framework.

    A skill progresses through:
    1. metadata()   — Declare identity, capabilities, dependencies
    2. plan()       — Given context, decide what to do (sub-steps)
    3. execute()    — Execute the analysis, return results
    4. verify()     — Self-verify: is the output consistent?
    5. summarize()  — Produce human-readable summary

    The runtime (Harness/Scheduler) orchestrates this lifecycle.
    Skills never call the runtime directly.
    """

    @abstractmethod
    def metadata(self) -> SkillMetadata:
        """Declare skill identity and capabilities.

        Called once at registration time. The returned metadata
        is cached by the SkillRegistry for discovery.
        """
        ...

    async def plan(self, context: dict) -> SkillPlan:
        """Given execution context, decide what sub-steps to execute.

        Override this if your skill has decomposable work.
        Default: returns an empty plan (single-step execution).
        """
        return SkillPlan()

    @abstractmethod
    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        """Execute the skill's core logic.

        Args:
            context: Input data assembled by the runtime from graph state
                     and tool results.
            plan: The SkillPlan returned by plan().

        Returns:
            SkillOutput with results, reasoning, and optional artifacts.
        """
        ...

    async def verify(self, context: dict, output: SkillOutput) -> SkillVerdict:
        """Self-verify: is the output consistent with the input data?

        Override this to add domain-specific verification.
        Default: returns PASS with no checks.
        """
        return SkillVerdict(passed=True)

    async def summarize(self, output: SkillOutput) -> str:
        """Produce a human-readable summary of the skill's output.

        Override this to provide custom summaries.
        Default: returns output.reasoning.
        """
        return output.reasoning or ""


# ─── Legacy Adapter ─────────────────────────────────────────────────────


class LegacySkillAdapter(SkillLifecycle):
    """Wraps an old InvestmentSkill into the new SkillLifecycle.

    Legacy skills lose sub-step planning and self-verification
    capabilities but continue to work without any code change.

    Usage:
        legacy = LegacySkillAdapter(MyOldSkill())
        result = await legacy.execute(context, SkillPlan())
    """

    def __init__(self, skill: Any):
        self._skill = skill

    def metadata(self) -> SkillMetadata:
        """Derive SkillMetadata from the legacy skill's properties."""
        name = getattr(self._skill, "name", None) or getattr(self._skill, "skill_name", "unknown")
        version = getattr(self._skill, "version", "1.0.0")

        # Try get_metadata() if available
        try:
            raw = self._skill.get_metadata() if hasattr(self._skill, "get_metadata") else {}
            if callable(raw):
                raw = raw()
        except Exception:
            raw = {}

        return SkillMetadata(
            name=str(name),
            version=str(version),
            description=str(raw.get("description") or name),
            category=str(raw.get("category") or "analysis"),
            tags=list(raw.get("tags") or []),
            input_schema=dict(raw.get("input_schema") or {}),
            output_schema=dict(raw.get("output_schema") or {}),
            timeout=int(raw.get("timeout") or 60),
        )

    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        """Bridge to the old analyze() method."""
        from strategies.base.models import AnalysisContext, AnalysisResult

        # Build old-style context if the skill expects it
        if hasattr(self._skill, "analyze"):
            try:
                # Convert dict context to AnalysisContext if possible
                if "stock" in context or "financial_data" in context:
                    from typing import cast

                    from strategies.base.models import Stock

                    old_ctx = AnalysisContext(
                        stock=cast(Stock, context.get("stock")),
                        financial_data=context.get("financial_data", []),
                        price_data=context.get("price_data", []),
                        market_data=context.get("market_data", {}),
                        user_preferences=context.get("user_preferences", {}),
                    )
                else:
                    # Pass the raw dict as kwarg
                    old_result = await self._skill.analyze(context)
                    return self._convert_result(old_result)

                old_result = await self._skill.analyze(old_ctx)
                return self._convert_result(old_result)

            except TypeError:
                # analyze() takes different args — fallback to direct call
                result = await self._skill.analyze(context)
                if isinstance(result, AnalysisResult):
                    return self._convert_result(result)
                return SkillOutput(data={"result": result})

        return SkillOutput(data={"note": "legacy skill adapter executed"})

    async def verify(self, context: dict, output: SkillOutput) -> SkillVerdict:
        """Legacy skills don't self-verify — always pass."""
        return SkillVerdict(passed=True)

    async def summarize(self, output: SkillOutput) -> str:
        """Use reasoning or data as summary."""
        return output.reasoning or str(output.data)[:500]

    @staticmethod
    def _convert_result(old: Any) -> SkillOutput:
        """Convert old AnalysisResult to new SkillOutput."""
        return SkillOutput(
            score=old.score,
            confidence=old.confidence,
            data=old.supporting_data,
            reasoning=old.reasoning,
            warnings=old.warnings,
            artifacts=[],       # legacy skills don't produce artifacts
        )


# ─── Skill SDK convenience helpers ───────────────────────────────────────


def is_legacy_skill(skill: Any) -> bool:
    """Check if a skill uses the legacy InvestmentSkill interface.

    Uses duck-typing: if the object has an async `analyze` method
    and is NOT a SkillLifecycle, it's treated as a legacy skill.
    """
    if isinstance(skill, SkillLifecycle):
        return False
    return hasattr(skill, "analyze") and callable(skill.analyze)


def ensure_skill_lifecycle(skill: Any) -> SkillLifecycle:
    """Wraps a legacy skill if needed, otherwise returns as-is."""
    if isinstance(skill, SkillLifecycle):
        return skill
    if is_legacy_skill(skill):
        return LegacySkillAdapter(skill)
    raise TypeError(
        f"Expected SkillLifecycle or InvestmentSkill (object with analyze() method), "
        f"got {type(skill).__name__}"
    )
