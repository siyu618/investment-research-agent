"""Tests for evaluations/trajectory/ — Trajectory Evaluation framework."""

import yaml
import pytest
from evaluations.trajectory.evaluator import TrajectoryEvaluator
from evaluations.trajectory.models import (
    DimensionScore,
    TrajectoryExpectations,
    TrajectoryScore,
)


# ─── Sample Traces ───────────────────────────────────────────────────────


def sample_successful_trace() -> list[dict]:
    """A trace representing a fully successful agent run."""
    return [
        {"type": "PlanningStarted", "timestamp": "2026-07-29T09:30:01.000", "payload": {"requirement": "Analyze stocks"}},
        {"type": "PlanningCompleted", "timestamp": "2026-07-29T09:30:02.150", "payload": {"plan": "..."}},
        {"type": "GraphResolved", "timestamp": "2026-07-29T09:30:02.151", "payload": {"node_count": 5, "layer_count": 3}},
        {"type": "NodeStarted", "timestamp": "2026-07-29T09:30:02.200", "payload": {"node_id": "plan", "skill": "planner"}},
        {"type": "NodeCompleted", "timestamp": "2026-07-29T09:30:04.000", "payload": {"node_id": "plan", "duration_ms": 1800}},
        {"type": "ToolInvoked", "timestamp": "2026-07-29T09:30:04.100", "payload": {"tool_name": "get_stock_basic", "input": {"market": "SSE"}}},
        {"type": "ToolFinished", "timestamp": "2026-07-29T09:30:04.800", "payload": {"tool_name": "get_stock_basic", "duration_ms": 700}},
        {"type": "ToolInvoked", "timestamp": "2026-07-29T09:30:05.000", "payload": {"tool_name": "get_income_statement", "input": {"ts_code": "000001.SZ"}}},
        {"type": "ToolFinished", "timestamp": "2026-07-29T09:30:05.900", "payload": {"tool_name": "get_income_statement", "duration_ms": 900}},
        {"type": "ToolInvoked", "timestamp": "2026-07-29T09:30:06.000", "payload": {"tool_name": "get_balance_sheet", "input": {"ts_code": "000001.SZ"}}},
        {"type": "ToolFinished", "timestamp": "2026-07-29T09:30:06.700", "payload": {"tool_name": "get_balance_sheet", "duration_ms": 700}},
        {"type": "ToolCacheHit", "timestamp": "2026-07-29T09:30:07.000", "payload": {"tool_name": "get_daily_price", "saved_ms": 500}},
        {"type": "ToolCacheMiss", "timestamp": "2026-07-29T09:30:07.100", "payload": {"tool_name": "get_daily_price"}},
        {"type": "SkillStarted", "timestamp": "2026-07-29T09:30:07.200", "payload": {"skill_name": "fundamental-analysis"}},
        {"type": "SkillCompleted", "timestamp": "2026-07-29T09:30:30.000", "payload": {"skill_name": "fundamental-analysis", "duration_ms": 22800}},
        {"type": "VerificationStarted", "timestamp": "2026-07-29T09:30:31.000", "payload": {}},
        {"type": "VerificationCompleted", "timestamp": "2026-07-29T09:30:31.500", "payload": {"passed": True}},
        {"type": "ReportGenerated", "timestamp": "2026-07-29T09:30:32.000", "payload": {"report_id": "report-20260729"}},
        {"type": "WorkflowFinished", "timestamp": "2026-07-29T09:30:33.000", "payload": {"status": "success", "total_duration_ms": 32000}},
    ]


def sample_failing_trace() -> list[dict]:
    """A trace with errors, retries, and a node failure."""
    return [
        {"type": "PlanningStarted", "timestamp": "2026-07-29T10:00:01.000", "payload": {"requirement": "Analyze stocks"}},
        {"type": "PlanningCompleted", "timestamp": "2026-07-29T10:00:02.150", "payload": {"plan": "..."}},
        {"type": "GraphResolved", "timestamp": "2026-07-29T10:00:02.151", "payload": {"node_count": 3, "layer_count": 2}},
        {"type": "ToolInvoked", "timestamp": "2026-07-29T10:00:03.000", "payload": {"tool_name": "get_daily_price", "input": {"ts_code": "000001.SZ"}}},
        {"type": "ToolFailed", "timestamp": "2026-07-29T10:00:03.500", "payload": {"tool_name": "get_daily_price", "error": "Rate limit exceeded", "recoverable": True}},
        {"type": "ToolInvoked", "timestamp": "2026-07-29T10:00:04.000", "payload": {"tool_name": "get_daily_price", "input": {"ts_code": "000001.SZ"}}},
        {"type": "ToolFinished", "timestamp": "2026-07-29T10:00:04.500", "payload": {"tool_name": "get_daily_price", "duration_ms": 500}},
        {"type": "NodeStarted", "timestamp": "2026-07-29T10:00:05.000", "payload": {"node_id": "analysis"}},
        {"type": "NodeRetried", "timestamp": "2026-07-29T10:00:05.100", "payload": {"node_id": "analysis", "attempt": 1}},
        {"type": "NodeFailed", "timestamp": "2026-07-29T10:00:30.000", "payload": {"node_id": "analysis", "error": "Timeout"}},
        {"type": "ErrorEncountered", "timestamp": "2026-07-29T10:00:30.100", "payload": {"node_id": "analysis", "error": "Timeout after 25s"}},
        {"type": "WorkflowFinished", "timestamp": "2026-07-29T10:00:31.000", "payload": {"status": "failed", "total_duration_ms": 30000}},
    ]


# ─── Trace Analysis Tests ────────────────────────────────────────────────


class TestTraceAnalysis:
    @pytest.mark.asyncio
    async def test_analyze_successful_trace(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_successful_trace())

        assert metrics["event_count"] == 19
        assert metrics["tool_call_count"] == 3
        assert metrics["tool_fail_count"] == 0
        assert metrics["has_planning"] is True
        assert metrics["has_graph"] is True
        assert metrics["has_verification"] is True
        assert metrics["has_report"] is True
        assert metrics["graph_node_count"] == 5
        assert metrics["retry_count"] == 0
        assert metrics["total_duration_ms"] == 32000

    @pytest.mark.asyncio
    async def test_analyze_failing_trace(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_failing_trace())

        assert metrics["event_count"] == 12
        assert metrics["tool_call_count"] == 2  # first attempt + retry
        assert metrics["tool_fail_count"] == 1
        assert metrics["node_failed"] == 1
        assert metrics["retry_count"] == 1
        assert metrics["error_count"] == 1
        assert metrics["has_report"] is False


# ─── Dimension Scoring Tests ─────────────────────────────────────────────


class TestDimensionScoring:
    @pytest.mark.asyncio
    async def test_planning_score_success(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_successful_trace())
        expected = TrajectoryExpectations(
            required_events=["PlanningStarted", "GraphResolved", "ReportGenerated"],
        )
        score = evaluator._score_planning(metrics, expected)
        assert score.score >= 80  # All required events present

    @pytest.mark.asyncio
    async def test_tool_selection_score_no_failures(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_successful_trace())
        expected = TrajectoryExpectations(optimal_tool_call_count=4)
        score = evaluator._score_tool_selection(metrics, expected)
        assert score.score >= 70

    @pytest.mark.asyncio
    async def test_tool_selection_score_with_failures(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_failing_trace())
        expected = TrajectoryExpectations()
        score = evaluator._score_tool_selection(metrics, expected)
        assert score.score < 100
        assert "tool failure" in str(score.criteria_missed).lower()

    @pytest.mark.asyncio
    async def test_execution_efficiency_score(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_successful_trace())
        expected = TrajectoryExpectations(
            expected_duration_ms=30000,
            optimal_node_count=5,
        )
        score = evaluator._score_execution_efficiency(metrics, expected)
        assert score.score >= 70

    @pytest.mark.asyncio
    async def test_error_recovery_score(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_failing_trace())
        expected = TrajectoryExpectations()
        score = evaluator._score_error_recovery(metrics, expected)
        assert score.score < 100  # penalised for node failure

    @pytest.mark.asyncio
    async def test_error_recovery_forbidden_events(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_successful_trace())
        expected = TrajectoryExpectations(forbidden_events=["NodeFailed"])
        score = evaluator._score_error_recovery(metrics, expected)
        assert score.score == 100  # no forbidden events in successful trace

    @pytest.mark.asyncio
    async def test_verification_score(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_successful_trace())
        score = evaluator._score_verification(metrics, TrajectoryExpectations())
        assert score.score == 100

    @pytest.mark.asyncio
    async def test_verification_score_missing(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_failing_trace())
        score = evaluator._score_verification(metrics, TrajectoryExpectations())
        assert score.score < 100

    @pytest.mark.asyncio
    async def test_overall_quality(self):
        evaluator = TrajectoryEvaluator()
        metrics = evaluator._analyze_trace(sample_successful_trace())
        score = evaluator._score_overall_quality(metrics, TrajectoryExpectations())
        assert score.score >= 70


# ─── Full Evaluation Tests ───────────────────────────────────────────────


class TestFullEvaluation:
    @pytest.mark.asyncio
    async def test_evaluate_successful_trace(self):
        evaluator = TrajectoryEvaluator()
        score = await evaluator.evaluate(
            sample_successful_trace(),
            TrajectoryExpectations(
                optimal_node_count=5,
                optimal_tool_call_count=4,
                expected_duration_ms=30000,
                required_events=["PlanningStarted", "VerificationCompleted", "ReportGenerated"],
            ),
        )
        assert isinstance(score, TrajectoryScore)
        assert score.overall_score >= 60
        assert score.passed is True
        assert len(score.dimensions) == 6  # all 6 dimensions
        assert score.exceptions == []  # no errors

    @pytest.mark.asyncio
    async def test_evaluate_failing_trace(self):
        evaluator = TrajectoryEvaluator()
        score = await evaluator.evaluate(
            sample_failing_trace(),
            TrajectoryExpectations(),
        )
        assert isinstance(score, TrajectoryScore)
        assert score.overall_score < 100  # failures reduce score
        assert len(score.exceptions) > 0  # errors captured
        # Node failure + tool failure + no verification → should be < 80
        assert score.overall_score < 80

    @pytest.mark.asyncio
    async def test_evaluate_with_case_file(self, tmp_path):
        """Load expectations from a YAML case file."""
        case_file = tmp_path / "test_case.yaml"
        case_file.write_text("""
expectations:
  optimal_node_count: 5
  optimal_tool_call_count: 3
  expected_duration_ms: 35000
  required_events:
    - PlanningStarted
    - GraphResolved
    - ReportGenerated
  forbidden_events:
    - NodeFailed
""")
        evaluator = TrajectoryEvaluator()
        score = await evaluator.evaluate(
            sample_successful_trace(),
            case_path=str(case_file),
        )
        assert isinstance(score, TrajectoryScore)
        assert score.passed is True

    @pytest.mark.asyncio
    async def test_empty_trace(self):
        evaluator = TrajectoryEvaluator()
        score = await evaluator.evaluate([], TrajectoryExpectations())
        # Empty trace penalised: no events, no report, no diversity
        assert score.overall_score <= 81


# ─── TrajectoryScore Model Tests ─────────────────────────────────────────


class TestTrajectoryScore:
    def test_dimension_score_weighted(self):
        dim = DimensionScore(name="test", score=80.0, weight=0.25)
        assert dim.weighted_score == 20.0  # 80 * 0.25

    def test_trajectory_score_defaults(self):
        score = TrajectoryScore()
        assert score.session_id == ""
        assert score.overall_score == 0.0
        assert score.passed is True
        assert score.dimensions == {}
        assert score.exceptions == []
