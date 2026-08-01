"""Tests that verification.json + verifier trace carry REAL VerificationResult."""

import json

import pytest
from agent.verifier import Verifier
from runtime.harness import Harness
from runtime.models import RuntimeConfig
from runtime.run_recorder import RunRecorder
from strategies.base.models import AnalysisPlan, AnalysisStep


def _make_plan(weights=None) -> AnalysisPlan:
    return AnalysisPlan(
        objective="test",
        strategy_weights=weights or {
            "fundamental-analysis": 0.35,
            "valuation-analysis": 0.25,
            "risk-analysis": 0.20,
            "technical-analysis": 0.20,
        },
        data_requirements=[],
        analysis_steps=[AnalysisStep(id=1, skill="data", target="x")],
    )


class _FakeExecutor:
    def __init__(self, results):
        self._results = results

    async def execute_plan(self, plan):
        return self._results

    def get_graph_result(self):
        return None


class _FakePlanner:
    def __init__(self, plan):
        self._plan = plan

    async def create_plan(self, requirement, **kwargs):
        return self._plan


class _FakeReporter:
    async def generate(self, plan, results, verification):
        from strategies.base.models import InvestmentReport
        return InvestmentReport(report_id="report-x")

    def format_markdown(self, report):
        return "# Report"


class TestVerificationPersistence:
    @pytest.mark.asyncio
    async def test_harness_exposes_real_verification(self):
        """Harness.last_verification is a real VerificationResult, not hardcoded."""
        harness = Harness(config=RuntimeConfig(max_retries=1, default_timeout=30))
        verifier = Verifier("standard")
        results = {}  # empty results → weights pass, no evidence findings

        result = await harness.run(
            planner=_FakePlanner(_make_plan()),
            executor=_FakeExecutor(results),
            verifier=verifier,
            reporter=_FakeReporter(),
            requirement="测试需求",
        )

        assert result.success is True
        v = harness.last_verification
        assert v is not None
        assert v.policy_mode == "standard"
        assert isinstance(v.checks, list)

    @pytest.mark.asyncio
    async def test_verification_dict_has_policy_and_blocked(self):
        verifier = Verifier("strict")
        # empty results + weights summing to 0.5 → error in strict
        plan = _make_plan(weights={"a": 0.5})
        v = await verifier.verify(plan, {})
        d = v.to_dict()
        assert d["policy_mode"] == "strict"
        assert d["passed"] is False
        assert d["blocked"] is True
        assert "policy_mode" in d and "blocked" in d

    def test_verification_json_shape(self):
        """verification.json contains checks/severity/policy (no hardcoded passed)."""
        # Simulate what save_full_run writes
        verifier = Verifier("standard")
        import asyncio
        v = asyncio.run(verifier.verify(_make_plan(), {}))
        d = v.to_dict()
        assert "checks" in d and "policy_mode" in d and "blocked" in d
        # Must NOT be the old hardcoded {"passed": True, ...}
        assert set(d.keys()) != {"passed", "warnings", "errors"}
