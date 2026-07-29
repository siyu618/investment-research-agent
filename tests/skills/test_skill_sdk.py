"""Tests for skills/base/skill_sdk.py — Skill SDK standardised lifecycle."""

import pytest
from skills.base.skill_sdk import (
    LegacySkillAdapter,
    SkillLifecycle,
    SkillMetadata,
    SkillOutput,
    SkillPlan,
    SkillStatus,
    SkillVerdict,
    ensure_skill_lifecycle,
    is_legacy_skill,
)


# ─── Test Implementations ────────────────────────────────────────────────


class SimpleTestSkill(SkillLifecycle):
    """A minimal skill for testing."""

    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="test-skill",
            version="1.0.0",
            description="A test skill",
            category="analysis",
            tags=["test"],
        )

    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        return SkillOutput(
            score=0.85,
            confidence=0.9,
            data={"result": "test output"},
            reasoning="Test reasoning",
        )


class VerifyingTestSkill(SkillLifecycle):
    """A skill that overrides verify()."""

    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="verify-skill", version="1.0.0", description="", category="analysis")

    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        score = context.get("input_score", 0.5)
        return SkillOutput(score=score, reasoning=f"Score: {score}")

    async def verify(self, context: dict, output: SkillOutput) -> SkillVerdict:
        if output.score and output.score > 1.0:
            return SkillVerdict(
                passed=False,
                errors=[f"Score {output.score} > 1.0 out of range"],
            )
        if output.score and output.score < 0.0:
            return SkillVerdict(
                passed=False,
                errors=[f"Score {output.score} < 0.0 out of range"],
            )
        return SkillVerdict(passed=True)


class PlanningTestSkill(SkillLifecycle):
    """A skill that overrides plan()."""

    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="plan-skill", version="1.0.0", description="", category="analysis")

    async def plan(self, context: dict) -> SkillPlan:
        return SkillPlan(
            steps=[{"action": "step1"}, {"action": "step2"}],
            data_needed=["price_data", "financials"],
            tools_needed=["get_daily_price"],
            estimated_duration=60,
        )

    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        return SkillOutput(
            score=0.9,
            data={"steps": plan.steps, "needs": plan.data_needed},
            reasoning=f"Planned {len(plan.steps)} steps",
        )


# ─── Legacy Mock ─────────────────────────────────────────────────────────


class LegacyMockSkill:
    """Simulates the old InvestmentSkill interface."""

    name = "legacy-mock"
    version = "1.2.0"

    async def analyze(self, context) -> dict:
        from strategies.base.models import AnalysisResult
        return AnalysisResult(
            skill_name="legacy-mock",
            skill_version="1.2.0",
            score=0.75,
            confidence=0.8,
            reasoning="Legacy analysis done",
            risk_factors=[],
            supporting_data={"key": "value"},
            warnings=["test warning"],
        )

    def get_metadata(self) -> dict:
        return {
            "description": "A legacy skill",
            "category": "analysis",
            "tags": ["legacy"],
            "timeout": 30,
        }


# ─── SkillLifecycle Tests ────────────────────────────────────────────────


class TestSkillLifecycle:
    @pytest.mark.asyncio
    async def test_basic_execute(self):
        """A simple skill should execute and return structured output."""
        skill = SimpleTestSkill()
        output = await skill.execute({}, SkillPlan())
        assert isinstance(output, SkillOutput)
        assert output.score == 0.85
        assert output.confidence == 0.9
        assert output.reasoning == "Test reasoning"

    @pytest.mark.asyncio
    async def test_metadata(self):
        skill = SimpleTestSkill()
        meta = skill.metadata()
        assert isinstance(meta, SkillMetadata)
        assert meta.name == "test-skill"
        assert meta.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_default_plan(self):
        """Skills that don't override plan() should get an empty plan."""
        skill = SimpleTestSkill()
        plan = await skill.plan({})
        assert isinstance(plan, SkillPlan)
        assert plan.steps == []
        assert plan.data_needed == []
        assert plan.tools_needed == []

    @pytest.mark.asyncio
    async def test_default_verify_passes(self):
        """Skills that don't override verify() should pass."""
        skill = SimpleTestSkill()
        verdict = await skill.verify({}, SkillOutput())
        assert verdict.passed is True
        assert verdict.errors == []

    @pytest.mark.asyncio
    async def test_default_summarize(self):
        """Default summarize() should return reasoning."""
        skill = SimpleTestSkill()
        summary = await skill.summarize(SkillOutput(reasoning="Test reasoning"))
        assert summary == "Test reasoning"


# ─── Self-Verification Tests ──────────────────────────────────────────────


class TestSelfVerification:
    @pytest.mark.asyncio
    async def test_passes_good_score(self):
        skill = VerifyingTestSkill()
        output = await skill.execute({"input_score": 0.7}, SkillPlan())
        verdict = await skill.verify({}, output)
        assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_fails_over_1(self):
        skill = VerifyingTestSkill()
        output = await skill.execute({"input_score": 1.5}, SkillPlan())
        verdict = await skill.verify({}, output)
        assert verdict.passed is False
        assert len(verdict.errors) > 0

    @pytest.mark.asyncio
    async def test_fails_under_0(self):
        skill = VerifyingTestSkill()
        output = await skill.execute({"input_score": -0.1}, SkillPlan())
        verdict = await skill.verify({}, output)
        assert verdict.passed is False


# ─── Planning Tests ──────────────────────────────────────────────────────


class TestPlanning:
    @pytest.mark.asyncio
    async def test_custom_plan(self):
        skill = PlanningTestSkill()
        plan = await skill.plan({})
        assert len(plan.steps) == 2
        assert "price_data" in plan.data_needed
        assert "get_daily_price" in plan.tools_needed

    @pytest.mark.asyncio
    async def test_plan_flows_to_execution(self):
        skill = PlanningTestSkill()
        plan = await skill.plan({})
        output = await skill.execute({}, plan)
        assert output.score == 0.9
        assert "step1" in str(output.data)


# ─── Legacy Adapter Tests ────────────────────────────────────────────────


class TestLegacyAdapter:
    @pytest.mark.asyncio
    async def test_wraps_legacy_skill(self):
        legacy = LegacyMockSkill()
        adapter = LegacySkillAdapter(legacy)

        # metadata
        meta = adapter.metadata()
        assert meta.name == "legacy-mock"
        assert meta.version == "1.2.0"
        assert meta.category == "analysis"

        # execute bridges to analyze()
        output = await adapter.execute({}, SkillPlan())
        assert output.score == 0.75
        assert output.confidence == 0.8
        assert "test warning" in output.warnings

        # verify passes for legacy skills
        verdict = await adapter.verify({}, output)
        assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_ensure_wraps_legacy(self):
        legacy = LegacyMockSkill()
        wrapped = ensure_skill_lifecycle(legacy)
        assert isinstance(wrapped, LegacySkillAdapter)

    @pytest.mark.asyncio
    async def test_ensure_passes_through(self):
        skill = SimpleTestSkill()
        result = ensure_skill_lifecycle(skill)
        assert result is skill  # same instance, not wrapped

    def test_is_legacy_detection(self):
        legacy = LegacyMockSkill()
        modern = SimpleTestSkill()
        assert is_legacy_skill(legacy) is True
        assert is_legacy_skill(modern) is False

    def test_ensure_raises_on_invalid(self):
        with pytest.raises(TypeError, match="SkillLifecycle"):
            ensure_skill_lifecycle("not-a-skill")  # type: ignore


# ─── SkillOutput Tests ───────────────────────────────────────────────────


class TestSkillOutput:
    def test_default_values(self):
        output = SkillOutput()
        assert output.score is None
        assert output.confidence is None
        assert output.data == {}
        assert output.reasoning == ""
        assert output.warnings == []
        assert output.artifacts == []

    def test_artifact_carries_metadata(self):
        output = SkillOutput(
            score=0.9,
            data={"symbol": "000001.SZ"},
            artifacts=[{"path": "/tmp/chart.png", "type": "chart"}],
        )
        assert len(output.artifacts) == 1
        assert output.artifacts[0]["type"] == "chart"


# ─── SkillVerdict Tests ──────────────────────────────────────────────────


class TestSkillVerdict:
    def test_passed_default(self):
        v = SkillVerdict()
        assert v.passed is True

    def test_checks_and_warnings(self):
        v = SkillVerdict(
            passed=True,
            checks=[{"name": "range_check", "passed": True}],
            warnings=["marginally above threshold"],
        )
        assert len(v.checks) == 1
        assert len(v.warnings) == 1
