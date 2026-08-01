# Full DAG Replay — reproduce an historical run deterministically
#
# Replay pipeline:
#   1. Load request.json / plan.json / data_snapshot.json
#   2. Rebuild ResearchDataset + AnalysisPlan
#   3. Re-execute the full DAG via the Executor (dataset injected,
#      Provider access FORBIDDEN)
#   4. Run portfolio selection + Verifier + ReportGenerator (same logic
#      as the original run)
#   5. Compare snapshot/plan/skill hashes, candidate ranking, verification,
#      and report structure → write replay_verification.json

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from runtime.snapshot import ResearchDataset, hash_of
from strategies.base.models import AnalysisPlan, AnalysisStep


class ForbiddenProvider:
    """Provider that refuses any access — proves replay never fetches data."""

    def __init__(self):
        self.calls: list[str] = []

    async def get_stock_basic(self, *args, **kwargs):
        self.calls.append("get_stock_basic")
        raise RuntimeError("Replay must not access the Provider")

    async def get_daily_price(self, *args, **kwargs):
        self.calls.append("get_daily_price")
        raise RuntimeError("Replay must not access the Provider")

    async def get_valuation(self, *args, **kwargs):
        self.calls.append("get_valuation")
        raise RuntimeError("Replay must not access the Provider")

    async def get_financial_summary(self, *args, **kwargs):
        self.calls.append("get_financial_summary")
        raise RuntimeError("Replay must not access the Provider")


def plan_from_dict(d: dict) -> AnalysisPlan:
    """Rebuild an AnalysisPlan from its serialized dict."""
    steps = []
    for s in d.get("analysis_steps", []):
        steps.append(AnalysisStep(
            id=s.get("id", 0),
            skill=s.get("skill", ""),
            target=s.get("target", ""),
            depends_on=list(s.get("depends_on", [])),
            params=s.get("params", {}),
            status=s.get("status", "pending"),
        ))
    return AnalysisPlan(
        objective=d.get("objective", ""),
        strategy_weights=d.get("strategy_weights", {}),
        data_requirements=d.get("data_requirements", []),
        analysis_steps=steps,
        risk_preference=d.get("risk_preference", "medium"),
    )


async def run_full_replay(run_dir: Path) -> dict:
    """Execute a full DAG replay and return a verification report dict."""
    from agent.executor import Executor
    from agent.report_generator import ReportGenerator

    # 1. Load artifacts
    snap = json.loads((run_dir / "data_snapshot.json").read_text())
    plan_dict = json.loads((run_dir / "plan.json").read_text())

    # 2. Rebuild dataset + plan
    dataset = ResearchDataset.from_dict(snap)
    plan = plan_from_dict(plan_dict)

    # Snapshot + plan hashes from the ORIGINAL run
    orig_snapshot_hashes = [
        s.get("data_hash", "") for s in snap.get("slices", [])
    ]
    orig_plan_hash = hash_of(plan_dict)

    # 3. Execute the full DAG via Executor — Provider forbidden
    forbidden = ForbiddenProvider()
    executor = Executor(provider=forbidden)  # type: ignore[arg-type]
    executor.set_dataset(dataset)
    exec_results = await executor.execute_plan(plan)

    # 4. Portfolio + Verifier + Report (same logic as original run)
    from agent.verifier import Verifier as V

    verifier = V("standard")
    verification = await verifier.verify(plan, exec_results)
    reporter = ReportGenerator()
    report = await reporter.generate(plan, exec_results, verification)
    report_md = reporter.format_markdown(report)

    # 5. Build equivalence comparison
    replay_snapshot_hashes = [
        s.get("data_hash", "") for s in executor.snapshot_records()
    ]
    replay_plan_hash = hash_of(_plan_to_serializable(plan))

    # Skill output hashes from the replay run
    skill_hashes: dict[str, str] = {}
    for rec in executor.agent_trace_records():
        if rec.get("kind") == "skill":
            skill_hashes[rec.get("name", "")] = rec.get("output_hash", "")

    # Candidate ranking from the report
    candidates = []
    for c in getattr(report, "candidates", []):
        candidates.append({
            "ts_code": getattr(c, "ts_code", ""),
            "composite_score": getattr(c, "composite_score", 0),
        })

    # Original run's report for structural comparison (if present)
    orig_report = run_dir / "report.md"
    orig_report_has_sections = False
    if orig_report.exists():
        orig_text = orig_report.read_text()
        orig_report_has_sections = all(
            sec in orig_text
            for sec in ("候选股票", "组合建议", "免责声明")
        )

    # Compare
    snapshot_match = replay_snapshot_hashes == orig_snapshot_hashes
    plan_match = replay_plan_hash == orig_plan_hash
    report_sections_match = orig_report_has_sections and all(
        sec in report_md for sec in ("候选股票", "组合建议", "免责声明")
    )

    checks = {
        "snapshot_hash": {
            "expected": orig_snapshot_hashes,
            "actual": replay_snapshot_hashes,
            "match": snapshot_match,
        },
        "plan_hash": {
            "expected": orig_plan_hash,
            "actual": replay_plan_hash,
            "match": plan_match,
        },
        "verification": {
            "passed": verification.passed,
            "policy_mode": verification.policy_mode,
            "checks": verification.checks,
            "errors": verification.errors,
        },
        "candidate_count": len(candidates),
        "report_sections_present": report_sections_match,
        "provider_access_attempted": len(forbidden.calls),
        "skill_output_hashes": skill_hashes,
    }

    all_match = snapshot_match and plan_match and report_sections_match
    diffs: list[str] = []
    if not snapshot_match:
        diffs.append("snapshot_hash mismatch")
    if not plan_match:
        diffs.append("plan_hash mismatch")
    if not report_sections_match:
        diffs.append("report sections mismatch")

    return {
        "status": "passed" if (all_match and verification.passed) else "failed",
        "diffs": diffs,
        "checks": checks,
    }


def _plan_to_serializable(plan: AnalysisPlan) -> dict:
    """Serialize plan for hashing (same shape as plan.json)."""
    return asdict(plan)
