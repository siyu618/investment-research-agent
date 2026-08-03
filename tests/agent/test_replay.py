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
    """Run the agent pipeline against mock provider and save ALL run
    artifacts (execution_outputs, result_manifest, manifest) to tmp_path.
    Returns the run dir path."""
    from runtime.snapshot import hash_of

    run_id = "test-run-1"
    recorder = RunRecorder(runs_dir=str(tmp_path))

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
                "status": s.status, "tool": getattr(s, "tool", ""),
            }
            for s in plan.analysis_steps
        ],
        "risk_preference": plan.risk_preference,
    }
    # Run executor with real mock provider
    await executor.execute_plan(plan)

    # Build a minimal verification (real Verifier) + report-like result
    from agent.verifier import Verifier
    from strategies.base.models import AnalysisPlan, AnalysisStep

    exec_results = executor._last_graph_result
    results_dict = {
        nid: nr.output for nid, nr in exec_results.node_results.items()
    } if exec_results else {}

    # Minimal AnalysisPlan for the verifier
    verifier_plan = AnalysisPlan(
        objective=plan_dict["objective"],
        strategy_weights=plan_dict["strategy_weights"],
        data_requirements=plan_dict["data_requirements"],
        analysis_steps=[
            AnalysisStep(id=s["id"], skill=s["skill"], target=s["target"],
                         depends_on=s["depends_on"], params=s["params"])
            for s in plan_dict["analysis_steps"]
        ],
        risk_preference=plan_dict["risk_preference"],
    )
    verification = await Verifier("standard").verify(verifier_plan, results_dict)

    # Generate a real report so candidate_order/portfolio match Replay's view
    from agent.report_generator import ReportGenerator

    report = await ReportGenerator().generate(
        verifier_plan, results_dict, verification)
    candidates = []
    for c in getattr(report, "candidates", []):
        candidates.append({
            "ts_code": getattr(c, "ts_code", ""),
            "composite_score": getattr(c, "composite_score", 0),
        })
    portfolio = getattr(report, "portfolio_suggestion", "")

    result_manifest = {
        "schema_version": "1.0.0",
        "candidates": candidates,
        "candidate_order": candidates,
        "portfolio_suggestion": portfolio,
        "verification": verification.to_dict(),
        "report_content_hash": hash_of({
            "candidate_order": candidates,
            "portfolio": portfolio,
            "verification": verification.to_dict(),
        }),
    }

    report_md = ReportGenerator().format_markdown(report)
    recorder.save_full_run(
        run_id=run_id,
        request={"requirement": requirement, "provider": "mock"},
        plan=plan_dict,
        tool_trace=executor.trace_records(),
        snapshots=executor.snapshot_records(),
        verification=verification.to_dict(),
        report_md=report_md,
        meta={"status": "success", "duration_ms": 0, "event_count": 0,
              "error": "", "hook_errors": 0},
        agent_trace=executor.agent_trace_records(),
        execution_outputs=executor.execution_outputs(),
        result_manifest=result_manifest,
    )
    return str(recorder.runs_dir / run_id)


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
    async def test_replay_node_outputs_match(self, tmp_path):
        """Every real skill node's output hash must match the original."""
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        verification = await run_full_replay(pathlib.Path(run_dir_path))
        node_checks = verification["checks"]["node_outputs"]
        assert node_checks, "expected node_outputs comparison"
        for nid, chk in node_checks.items():
            assert chk["match"] is True, (
                f"node {nid} output mismatch: {chk}"
            )

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


class TestReplayArtifactGate:
    @pytest.mark.asyncio
    async def test_missing_execution_outputs_fails(self, tmp_path):
        """Replay must fail with artifact_missing when execution_outputs missing."""
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        p = pathlib.Path(run_dir_path)
        (p / "execution_outputs.json").unlink()
        verification = await run_full_replay(p)
        assert verification["status"] == "artifact_missing"
        assert "execution_outputs" in verification["reason"]

    @pytest.mark.asyncio
    async def test_missing_manifest_fails(self, tmp_path):
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        p = pathlib.Path(run_dir_path)
        (p / "manifest.json").unlink()
        verification = await run_full_replay(p)
        assert verification["status"] == "artifact_missing"
        assert "manifest" in verification["reason"]

    @pytest.mark.asyncio
    async def test_tampered_node_hash_fails(self, tmp_path):
        """Tampering a node output hash must fail node comparison."""
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        p = pathlib.Path(run_dir_path)
        outputs = json.loads((p / "execution_outputs.json").read_text())
        # Corrupt the output_hash of the first real skill node
        for nid in outputs:
            if "output_hash" in outputs[nid]:
                outputs[nid]["output_hash"] = "0" * 64
                break
        (p / "execution_outputs.json").write_text(json.dumps(outputs))
        verification = await run_full_replay(p)
        # Manifest hash check detects tampering → artifact_missing
        assert verification["status"] == "artifact_missing"
        assert "hash mismatch" in verification["reason"]

    @pytest.mark.asyncio
    async def test_tampered_manifest_fails(self, tmp_path):
        """Editing a file after run → manifest hash mismatch blocks replay."""
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        p = pathlib.Path(run_dir_path)
        # Modify plan.json content (tamper)
        plan = json.loads((p / "plan.json").read_text())
        plan["objective"] = "tampered"
        (p / "plan.json").write_text(json.dumps(plan))
        verification = await run_full_replay(p)
        assert verification["status"] == "artifact_missing"
        assert "hash mismatch" in verification["reason"]

    @pytest.mark.asyncio
    async def test_run_generates_manifest_and_outputs(self, tmp_path):
        """A real run must produce manifest.json + execution_outputs.json."""
        run_dir_path = await _run_and_capture("分析 600519.SH", tmp_path)
        import pathlib
        p = pathlib.Path(run_dir_path)
        assert (p / "manifest.json").exists()
        assert (p / "execution_outputs.json").exists()
        assert (p / "result_manifest.json").exists()
        manifest = json.loads((p / "manifest.json").read_text())
        assert manifest["manifest_version"] == "1.0.0"
        assert "execution_outputs.json" in manifest["artifacts"]
        assert "result_manifest.json" in manifest["artifacts"]


class TestDynamicPlanPlaceholder:
    """Placeholder detection is skill-based, not step-position-based.

    Dynamic plans place portfolio/verifier/report at varying step ids
    (e.g. step-4 in a 6-step screening plan). Replay must exclude them
    regardless of position, or a live run won't match its replay.
    """

    def test_placeholder_detection_skill_based(self, tmp_path):
        from agent.executor import Executor
        from strategies.base.models import AnalysisPlan, AnalysisStep
        from tools.providers import MockMarketDataProvider

        plan = AnalysisPlan(
            objective="screening",
            strategy_weights={},
            data_requirements=["csi300"],
            analysis_steps=[
                AnalysisStep(id=1, skill="data-collector", target="csi300"),
                AnalysisStep(id=2, skill="fundamental-analysis", target="csi300"),
                AnalysisStep(id=3, skill="valuation-analysis", target="csi300"),
                AnalysisStep(id=4, skill="portfolio-selection", target="csi300"),
                AnalysisStep(id=5, skill="verifier", target="csi300"),
                AnalysisStep(id=6, skill="report-generator", target="csi300"),
            ],
        )
        ex = Executor(provider=MockMarketDataProvider())
        ex._last_plan = plan
        # step-4 is portfolio-selection in this dynamic plan → placeholder
        assert ex._is_placeholder_node("step-4") is True
        # step-2/3 are real analysis skills → not placeholders
        assert ex._is_placeholder_node("step-2") is False
        assert ex._is_placeholder_node("step-3") is False
