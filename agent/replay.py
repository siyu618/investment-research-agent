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
            tool=s.get("tool", ""),
        ))
    return AnalysisPlan(
        objective=d.get("objective", ""),
        strategy_weights=d.get("strategy_weights", {}),
        data_requirements=d.get("data_requirements", []),
        analysis_steps=steps,
        risk_preference=d.get("risk_preference", "medium"),
    )


REQUIRED_ARTIFACTS = [
    "manifest.json",
    "request.json",
    "plan.json",
    "data_snapshot.json",
    "execution_outputs.json",
]

MANIFEST_SCHEMA = "1.0.0"


def _check_artifacts(run_dir: Path) -> dict:
    """Validate manifest + required artifacts before replay.

    Returns {"ok": True} or a failing report with the reason.
    """
    missing = [a for a in REQUIRED_ARTIFACTS if not (run_dir / a).exists()]
    if missing:
        return {
            "status": "artifact_missing",
            "ok": False,
            "reason": f"required artifact(s) missing: {missing}",
        }

    # Manifest schema version
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if manifest.get("manifest_version") != MANIFEST_SCHEMA:
        return {
            "status": "artifact_missing",
            "ok": False,
            "reason": f"unsupported manifest_version "
                      f"{manifest.get('manifest_version')} (expected {MANIFEST_SCHEMA})",
        }

    # Per-artifact hash vs manifest (detect tampering / corruption)
    tampered = []
    for fname, info in (manifest.get("artifacts") or {}).items():
        fpath = run_dir / fname
        if not fpath.exists():
            continue
        actual_hash = hash_of(fpath.read_text(encoding="utf-8"))
        if info.get("sha256") and actual_hash != info["sha256"]:
            tampered.append(fname)
    if tampered:
        return {
            "status": "artifact_missing",
            "ok": False,
            "reason": f"artifact hash mismatch (tampered/corrupted): {tampered}",
        }

    # execution_outputs schema version
    exec_outputs = json.loads((run_dir / "execution_outputs.json").read_text())
    if isinstance(exec_outputs, dict) and exec_outputs.get("schema_version") == "missing":
        return {"status": "artifact_missing", "ok": False,
                "reason": "execution_outputs schema unsupported"}

    return {"status": "ok", "ok": True}


async def run_full_replay(run_dir: Path) -> dict:
    """Deterministic Replay Verification.

    Re-executes the full DAG (Provider forbidden) and compares EVERY node
    against the original run's execution_outputs.json, plus snapshot/plan
    hashes, candidate ranking, verification, and report structure.
    Produces a detailed diff for any mismatch.

    Artifact gate: if manifest.json or execution_outputs.json is missing,
    or an artifact hash fails against the manifest, returns artifact_missing
    instead of silently passing.
    """
    from agent.executor import Executor
    from agent.report_generator import ReportGenerator

    # 0. Artifact integrity gate (manifest + required files)
    gate = _check_artifacts(run_dir)
    if gate["ok"] is not True:
        return gate

    # 1. Load artifacts
    snap = json.loads((run_dir / "data_snapshot.json").read_text())
    plan_dict = json.loads((run_dir / "plan.json").read_text())
    orig_exec_outputs = json.loads((run_dir / "execution_outputs.json").read_text())
    orig_result_manifest = {}
    if (run_dir / "result_manifest.json").exists():
        orig_result_manifest = json.loads((run_dir / "result_manifest.json").read_text())

    # 2. Rebuild dataset + plan
    dataset = ResearchDataset.from_dict(snap)
    plan = plan_from_dict(plan_dict)

    # Original hashes (snapshot_hash, not content_hash — full context)
    orig_snapshot_hashes = [
        s.get("snapshot_hash", s.get("data_hash", "")) for s in snap.get("slices", [])
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

    # 5. Node-by-node comparison against original execution_outputs
    replay_exec_outputs = executor.execution_outputs()
    node_checks: dict[str, dict] = {}
    node_diffs: list[str] = []
    all_nodes = set(orig_exec_outputs) | set(replay_exec_outputs)
    for nid in sorted(all_nodes):
        expected = orig_exec_outputs.get(nid, {}).get("output_hash", "")
        actual = replay_exec_outputs.get(nid, {}).get("output_hash", "")
        match = bool(expected and actual and expected == actual)
        node_checks[nid] = {
            "expected": expected,
            "actual": actual,
            "match": match,
        }
        if not match:
            node_diffs.append(
                f"node {nid} output mismatch "
                f"(expected {expected[:12]}, got {actual[:12]})"
            )

    # 6. Snapshot / plan comparison
    replay_snapshot_hashes = [
        s.get("snapshot_hash", s.get("data_hash", "")) for s in executor.snapshot_records()
    ]
    replay_plan_hash = hash_of(_plan_to_serializable(plan))
    snapshot_match = replay_snapshot_hashes == orig_snapshot_hashes
    plan_match = replay_plan_hash == orig_plan_hash

    # 7. Business results comparison against result_manifest.json
    result_diffs: list[str] = []
    result_checks: dict[str, dict] = {}
    if orig_result_manifest:
        # 7a. Candidate order + composite scores
        replay_candidates = []
        for c in getattr(report, "candidates", []):
            replay_candidates.append({
                "ts_code": getattr(c, "ts_code", ""),
                "composite_score": getattr(c, "composite_score", 0),
            })
        orig_order = orig_result_manifest.get("candidate_order", [])
        order_match = replay_candidates == orig_order
        result_checks["candidate_order"] = {
            "expected": orig_order,
            "actual": replay_candidates,
            "match": order_match,
        }
        if not order_match:
            result_diffs.append(
                f"candidate order/score mismatch "
                f"(expected {len(orig_order)} ranked, got {len(replay_candidates)})"
            )

        # 7b. Verification result comparison
        orig_verification = orig_result_manifest.get("verification", {})
        replay_verification = verification.to_dict()
        verification_match = (
            orig_verification.get("passed") == replay_verification.get("passed")
            and orig_verification.get("policy_mode") == replay_verification.get("policy_mode")
        )
        result_checks["verification"] = {
            "expected": orig_verification,
            "actual": replay_verification,
            "match": verification_match,
        }
        if not verification_match:
            result_diffs.append("verification result mismatch")

        # 7c. Portfolio suggestion (standardized string)
        orig_portfolio = orig_result_manifest.get("portfolio_suggestion", "")
        replay_portfolio = getattr(report, "portfolio_suggestion", "")
        portfolio_match = orig_portfolio == replay_portfolio
        result_checks["portfolio_suggestion"] = {
            "expected": orig_portfolio,
            "actual": replay_portfolio,
            "match": portfolio_match,
        }
        if not portfolio_match:
            result_diffs.append("portfolio suggestion mismatch")

        # 7d. Report content hash (over structured facts, not Markdown)
        orig_rep_hash = orig_result_manifest.get("report_content_hash", "")
        replay_rep_hash = hash_of({
            "candidate_order": replay_candidates,
            "portfolio": replay_portfolio,
            "verification": replay_verification,
        })
        report_content_match = bool(orig_rep_hash) and orig_rep_hash == replay_rep_hash
        result_checks["report_content_hash"] = {
            "expected": orig_rep_hash,
            "actual": replay_rep_hash,
            "match": report_content_match,
        }
        if not report_content_match:
            result_diffs.append("report content hash mismatch")

    # 8. Report structure (section presence — secondary, not primary)
    orig_report = run_dir / "report.md"
    orig_report_has_sections = False
    if orig_report.exists():
        orig_text = orig_report.read_text()
        orig_report_has_sections = all(
            sec in orig_text
            for sec in ("候选股票", "组合建议", "免责声明")
        )
    report_sections_match = orig_report_has_sections and all(
        sec in report_md for sec in ("候选股票", "组合建议", "免责声明")
    )

    # 9. Aggregate diffs
    diffs: list[str] = list(node_diffs) + list(result_diffs)
    if not snapshot_match:
        diffs.append("snapshot_hash mismatch")
    if not plan_match:
        diffs.append("plan_hash mismatch")
    if not report_sections_match:
        diffs.append("report sections mismatch")

    all_match = (
        snapshot_match and plan_match and report_sections_match
        and not node_diffs and not result_diffs
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
        "node_outputs": node_checks,
        "result_manifest": result_checks,
        "candidate_count": len(getattr(report, "candidates", [])),
        "report_sections_present": report_sections_match,
        "provider_access_attempted": len(forbidden.calls),
    }

    return {
        "status": "passed" if (all_match and verification.passed) else "failed",
        "diffs": diffs,
        "checks": checks,
    }


def _plan_to_serializable(plan: AnalysisPlan) -> dict:
    """Serialize plan for hashing (same shape as plan.json)."""
    return asdict(plan)
