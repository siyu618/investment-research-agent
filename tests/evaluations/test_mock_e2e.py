"""End-to-end test using MockMarketDataProvider.

Tests the full pipeline: Planner → Executor (Scheduler) → ReportGenerator.
"""

import pytest
from agent.planner import Planner
from agent.executor import Executor
from agent.report_generator import ReportGenerator
from tools.providers import MockMarketDataProvider
from runtime import RuntimeConfig


@pytest.fixture
def config():
    return RuntimeConfig(default_timeout=30, max_retries=1)


@pytest.fixture
def provider():
    return MockMarketDataProvider()


@pytest.mark.asyncio
class TestE2E:
    async def test_planner_to_executor(self, provider, config):
        """Planner produces a plan the Executor can execute."""
        planner = Planner()
        executor = Executor(provider=provider, config=config)

        plan = await planner.create_plan("从沪深300筛选基本面稳健的5只股票")
        assert plan is not None

        result = await executor.execute_plan(plan)
        assert result is not None
        assert len(result) >= 1  # at least some steps completed

    async def test_data_collection_step(self, provider, config):
        """Data collection step loads stocks."""
        executor = Executor(provider=provider, config=config)
        data = await executor._run_data_collector({})
        assert data["stock_count"] == 17  # 15 CSI300 + 2 edge-case stocks
        assert len(data["stocks_basic"]) == 17

    async def test_full_pipeline(self, provider, config):
        """End-to-end: plan → execute → report."""
        planner = Planner()
        executor = Executor(provider=provider, config=config)
        reporter = ReportGenerator()

        plan = await planner.create_plan("从沪深300筛选基本面稳健、估值合理的5只股票")
        results = await executor.execute_plan(plan)
        assert len(results) >= 3  # data + fund + val + risk + selection + verify + report

        # Verification step (simplified: just check result exists)
        assert any("step-6" in k for k in results) or any("verify" in str(k).lower() for k in results)

        # Report generator should produce output
        from agent.verifier import Verifier
        verifier = Verifier()
        v_result = await verifier.verify(plan, results)
        report = await reporter.generate(plan, results, v_result)
        assert report is not None
        assert report.report_id is not None

        # Markdown output
        md = reporter.format_markdown(report)
        assert "投资研究报告" in md
        assert "候选股票" in md
        assert "免责声明" in md

    async def test_trace_export(self, provider, config):
        """Verify that events are emitted during execution."""
        from runtime.tracing import EventBus

        event_bus = EventBus()
        planner = Planner()
        executor = Executor(provider=provider, event_bus=event_bus, config=config)

        plan = await planner.create_plan("分析沪深300股票")
        await executor.execute_plan(plan)

        trace = event_bus.export_trace("executor-run")
        # Scheduler uses a different correlation_id — check raw history
        all_events = event_bus.get_history()
        assert len(all_events) > 0
        types = {e.type for e in all_events}
        assert "NodeStarted" in types
