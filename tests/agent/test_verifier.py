"""Tests for Verifier — severity + policy_mode gating."""

from datetime import datetime, timedelta

import pytest
from agent.verifier import PolicyMode, Severity, Verifier, VerificationFinding
from strategies.base.models import AnalysisPlan, AnalysisStep


def _make_plan(weights: dict | None = None) -> AnalysisPlan:
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


def _metric_profile(name="测试股", available_at=None, metrics=1, score=0.5, missing=()):
    """Build a fake profile object mimicking CompanyFundamentalProfile."""
    from types import SimpleNamespace

    if available_at is None:
        available_at = datetime.now().strftime("%Y-%m-%d")

    class Metric:
        def __init__(self, at):
            self.metric = "roe"
            self.available_at = at

    metric_list = [Metric(available_at) for _ in range(metrics)]
    return SimpleNamespace(
        name=name,
        metrics=metric_list,
        score=score,
        missing_data_flags=list(missing),
    )


def _result_with(profile) -> dict:
    """Wrap a profile in a results dict the verifier expects."""
    step = type("Step", (), {"profiles": [profile]})()
    return {1: step}


class TestSeverityModel:
    def test_policy_blocks(self):
        assert PolicyMode.PERMISSIVE.blocks == {Severity.FATAL}
        assert PolicyMode.STANDARD.blocks == {Severity.FATAL, Severity.ERROR}
        assert PolicyMode.STRICT.blocks == {Severity.FATAL, Severity.ERROR, Severity.WARNING}


class TestVerifierGating:
    @pytest.mark.asyncio
    async def test_standard_passes_clean_run(self):
        plan = _make_plan()
        profile = _metric_profile()
        v = Verifier("standard")
        result = await v.verify(plan, _result_with(profile))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_lookahead_is_fatal_everywhere(self):
        """Future data must block under ALL policies."""
        plan = _make_plan()
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        profile = _metric_profile(available_at=future)
        for mode in ("permissive", "standard", "strict"):
            v = Verifier(mode)
            result = await v.verify(plan, _result_with(profile))
            assert result.passed is False, f"mode={mode} should block future data"
            assert any("future" in c["message"] for c in result.checks)

    @pytest.mark.asyncio
    async def test_bad_weights_block_standard_but_not_permissive(self):
        plan = _make_plan(weights={"a": 0.5})  # sums to 0.5
        profile = _metric_profile()
        v_perm = Verifier("permissive")
        assert (await v_perm.verify(plan, _result_with(profile))).passed is True

        v_std = Verifier("standard")
        assert (await v_std.verify(plan, _result_with(profile))).passed is False

    @pytest.mark.asyncio
    async def test_missing_data_warning_not_blocking_standard(self):
        """Flagged missing data → warning → passes standard."""
        plan = _make_plan()
        profile = _metric_profile(metrics=0, score=0.0, missing=("roe",))
        v = Verifier("standard")
        result = await v.verify(plan, _result_with(profile))
        assert result.passed is True
        assert any(c["severity"] == "warning" for c in result.checks)

    @pytest.mark.asyncio
    async def test_strict_blocks_warning(self):
        """In strict mode, warnings block."""
        plan = _make_plan()
        profile = _metric_profile(metrics=0, score=0.0, missing=("roe",))
        v = Verifier("strict")
        result = await v.verify(plan, _result_with(profile))
        assert result.passed is False  # warning blocks in strict

    @pytest.mark.asyncio
    async def test_score_without_evidence_is_error(self):
        """Score > 0 with zero metrics → error (blocks standard)."""
        plan = _make_plan()
        profile = _metric_profile(metrics=0, score=0.8)
        v = Verifier("standard")
        result = await v.verify(plan, _result_with(profile))
        assert result.passed is False
        assert any(c["severity"] == "error" for c in result.checks)


class TestFindingModel:
    def test_to_dict(self):
        f = VerificationFinding("test", Severity.ERROR, "message", "detail")
        d = f.to_dict()
        assert d["phase"] == "test"
        assert d["severity"] == "error"
        assert d["message"] == "message"
