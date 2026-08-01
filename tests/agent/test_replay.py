"""Tests for full DAG replay — equivalence, provider isolation."""

import json

import pytest
from agent.executor import Executor
from agent.planner import Planner
from agent.replay import ForbiddenProvider, plan_from_dict, run_full_replay
from runtime.run_recorder import RunRecorder
from runtime.snapshot import ResearchDataset
from tools.providers import MockMarketDataProvider


async def _run_and_capture(requirement: str, tmp_path) -> str:
    """Run the agent pipeline against mock provider, save run to tmp_path,
    return the run dir path."""
    run_id = "test-run-1"
    recorder = RunRecorder(runs_dir=str(tmp_path))
    run_dir = recorder.create_run(run_id)

    planner = Planner()
    executor = Executor(provider=MockMarketDataProvider(), run_id=run_id)

    plan = await planner.create_plan(requirement)
    plan_dict = {
        "objective": plan.objective,
        "strategy_weights": plan.strategy_weights,
        "data_requirements": plan.data_requirements,
        "analysis_steps": [
            {
                "id": s.id, "skill": s.skill, "target": s.target,
                "depends_on": s.depends_on, "params": s.params,
                "status": s.status,
            }
            for s in plan.analysis_steps
        ],
        "risk_preference": plan.risk_preference,
    }
    # Run executor with real mock provider
    await executor.execute_plan(plan)
    # Persist artifacts needed for replay
    recorder.write_json(run_id, "plan.json", plan_dict)
    recorder.write_json(run_id, "request.json",
                        {"requirement": requirement, "provider": "mock"})
    recorder.write_json(run_id, "data_snapshot.json", {
        "slice_count": len(executor.snapshot_records()),
        "as_of": executor.snapshot_records()[0].get("as_of", "") if executor.snapshot_records() else "",
        "slices": executor.snapshot_records(),
    })
    # Per-node outputs for deterministic replay comparison
    recorder.write_json(run_id, "execution_outputs.json", executor.execution_outputs())
    # Report with the expected structural sections (replay compares these)
    recorder.write_text(
        run_id, "report.md",
        "# 报告\n\n## 三、候选股票评分及排名\n\n## 四、组合建议\n\n## 免责声明\n",
    )
    return str(run_dir)


class TestForbiddenProvider:
    @pytest.mark.asyncio
    async def test_refuses_all_access(self):
        fp = ForbiddenProvider()
        with pytest.raises(RuntimeError):
            await fp.get_stock_basic()
        with pytest.raises(RuntimeError):
            await fp.get_daily_price("x", "1", "2")
        assert len(fp.calls) == 2


class TestPlanFromDict:
    def test_roundtrip(self):
        d = {
            "objective": "stock_pool=csi300 objective=quality risk=medium top_k=5",
            "strategy_weights": {"fundamental-analysis": 0.5},
            "data_requirements": ["csi300"],
            "analysis_steps": [
                {"id": 1, "skill": "data-collector", "target": "csi300",
                 "depends_on": [], "params": {}, "status": "pending"},
                {"id": 2, "skill": "fundamental-analysis", "target": "csi300",
                 "depends_on": [1], "params": {}, "status": "pending"},
            ],
            "risk_preference": "medium",
        }
        plan = plan_from_dict(d)
        assert len(plan.analysis_steps) == 2
        assert plan.analysis_steps[1].depends_on == [1]


class TestFullReplay:
    @pytest.mark.asyncio
    async def test_replay_passes_equivalence(self, tmp_path):
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        verification = await run_full_replay(pathlib.Path(run_dir_path))
        assert verification["status"] == "passed", verification.get("diffs")
        assert verification["checks"]["provider_access_attempted"] == 0
        assert verification["checks"]["snapshot_hash"]["match"] is True
        assert verification["checks"]["plan_hash"]["match"] is True

    @pytest.mark.asyncio
    async def test_replay_forbids_provider(self, tmp_path):
        """Replay must never call the provider."""
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        verification = await run_full_replay(pathlib.Path(run_dir_path))
        assert verification["checks"]["provider_access_attempted"] == 0

    @pytest.mark.asyncio
    async def test_replay_rebuilds_dataset(self, tmp_path):
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        snap = json.loads((pathlib.Path(run_dir_path) / "data_snapshot.json").read_text())
        dataset = ResearchDataset.from_dict(snap)
        assert len(dataset.stocks()) >= 1
