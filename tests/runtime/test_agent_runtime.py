"""Tests for the unified AgentRuntime + domain adapter.

Verifies the SINGLE lifecycle engine:
    create_task → plan → schedule → execute → aggregate → report

with the investment domain injected via agent/runtime_adapter.py:
    - dynamic planner (plan_for_goal)
    - executor adapter (AnalysisPlan → TaskGraph → Scheduler)
    - verifier aggregator (policy gate)
    - reporter stage (InvestmentReport)
"""

import pytest
from agent.executor import Executor
from agent.planner import Planner
from agent.report_generator import ReportGenerator
from agent.runtime_adapter import build_runtime
from agent.verifier import Verifier
from runtime import RuntimeConfig
from tools.providers import MockMarketDataProvider


@pytest.fixture
def components():
    provider = MockMarketDataProvider()
    planner = Planner()
    executor = Executor(provider=provider, config=RuntimeConfig(
        default_timeout=30, max_retries=1))
    verifier = Verifier()
    reporter = ReportGenerator()
    return {"planner": planner, "executor": executor,
            "verifier": verifier, "reporter": reporter}


@pytest.mark.asyncio
class TestAgentRuntimeUnified:
    async def test_full_lifecycle_dynamic_plan(self, components):
        """Dynamic plan flows through the runtime to a completed report."""
        sink: list[dict] = []
        runtime = build_runtime(span_sink=sink, **components)
        task = await runtime.create_task("分析 600519.SH 投资价值")
        result = await runtime.run(task)
        assert result.status == "completed"
        assert result.plan is not None
        assert result.result is not None
        assert getattr(result.result, "report_id", "")
        assert result.result.candidates
        assert result.result.candidates[0].ts_code == "600519.SH"

    async def test_lifecycle_emits_planner_and_report_spans(self, components):
        """Every runtime stage records a real span into the shared sink."""
        sink: list[dict] = []
        runtime = build_runtime(span_sink=sink, **components)
        task = await runtime.create_task("分析 600519.SH")
        await runtime.run(task)
        kinds = {s["kind"] for s in sink}
        assert {"planner", "scheduler", "aggregator", "reporter"} <= kinds
        assert all("duration_ms" in s for s in sink)

    async def test_stats_collected_from_real_spans(self, components):
        """AgentRunStats aggregates real tool/skill/latency metrics."""
        sink: list[dict] = []
        runtime = build_runtime(span_sink=sink, **components)
        task = await runtime.create_task("分析 600519.SH")
        await runtime.run(task)
        # Merge executor spans (tool/skill) into the shared sink first,
        # exactly as the CLI does.
        sink.extend(components["executor"].agent_trace_records())
        stats = runtime.collect_stats(task)
        assert stats.task_success is True
        assert stats.tool_calls >= 3
        assert stats.tool_success == stats.tool_calls
        assert stats.latency_ms >= 0

    async def test_verifier_gate_runs_inside_runtime(self, components):
        """The verifier runs in the aggregate stage and gates the report."""
        sink: list[dict] = []
        runtime = build_runtime(span_sink=sink, **components)
        task = await runtime.create_task("分析 600519.SH")
        ctx: dict = {}
        await runtime.run(task, context=ctx)
        # The runtime mirrors the run context back to the caller, so the
        # verification result is observable.
        assert ctx.get("verification") is not None
        assert ctx["verification"].passed is True

    async def test_failed_run_marks_task_failed(self, components):
        """A failing plan stage marks the task failed with an error."""
        class BrokenPlanner:
            async def plan_for_goal(self, goal, tools=None, span_sink=None):
                raise RuntimeError("boom")

        runtime = build_runtime(planner=BrokenPlanner(),
                                span_sink=[], **{k: v for k, v in components.items()
                                                 if k != "planner"})
        task = await runtime.create_task("分析 600519.SH")
        with pytest.raises(RuntimeError):
            await runtime.run(task)
        assert task.status == "failed"
        assert "boom" in task.error
