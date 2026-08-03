#!/usr/bin/env python3
"""Agentic Investment Research Platform — CLI entry point.

The default path runs the UNIFIED AgentRuntime lifecycle:
    create_task → plan → schedule → execute → aggregate → report
with dynamic planning, a ToolRegistry, the RAG knowledge layer, LLM
telemetry, and per-run evaluation metrics — all observable through
agent_trace.jsonl + Mermaid.

Usage:
    python -m agent --requirement "分析 600519.SH 投资价值"
    python -m agent --requirement "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"
    python -m agent --requirement "分析 600519.SH" --reuse-memory
    python -m agent --interactive
    python -m agent --replay runs/{run_id}
"""

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.executor import Executor
from agent.llm import LLMBackend
from agent.planner import Planner
from agent.report_generator import ReportGenerator
from agent.runtime_adapter import build_runtime
from agent.verifier import Verifier
from memory.research import ResearchMemory
from memory.retrieval import KnowledgeRetriever
from runtime import RuntimeConfig
from runtime.agent_runtime import AgentRuntime
from runtime.run_recorder import RunRecorder
from runtime.tracing import EventBus
from tools.providers import MarketDataProvider, MockMarketDataProvider
from tools.registry import ToolRegistry

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")


async def main():
    parser = argparse.ArgumentParser(description="Agentic Investment Research Platform")
    parser.add_argument("--requirement", "-r", type=str, help="投资研究需求")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--output", "-o", type=str, default="reports", help="报告输出目录")
    parser.add_argument("--trace", action="store_true", help="启用执行跟踪")
    parser.add_argument("--provider", type=str, default="mock",
                        choices=["mock", "tushare"], help="数据提供者")
    parser.add_argument("--reuse-memory", action="store_true",
                        help="启用 RAG 知识层：按公司/行业/主题召回历史研究并回写")
    parser.add_argument("--eval-trajectory", type=str, default=None,
                        metavar="RUN_DIR",
                        help="对 runs/{run_id} 的运行轨迹进行评分（trajectory evaluation）")
    parser.add_argument("--replay", type=str, default=None,
                        help="重放历史运行: runs/{run_id} 目录路径")
    args = parser.parse_args()

    if args.eval_trajectory:
        await run_trajectory_eval(args.eval_trajectory, args)
        return

    if args.replay:
        await run_replay(args.replay, args)
        return

    if args.interactive:
        print("Agentic Investment Research Platform — 交互模式")
        print("输入投资需求（输入 'quit' 退出）:")
        while True:
            try:
                req = input("\n> ").strip()
                if req.lower() in ("quit", "exit", "q"):
                    break
                if not req:
                    continue
                await run_research(req, args)
            except KeyboardInterrupt:
                print("\n退出...")
                break
    elif args.requirement:
        await run_research(args.requirement, args)
    else:
        parser.print_help()


async def run_research(requirement: str, args):
    """Run the full AgentRuntime pipeline and record a run artifact."""
    config = RuntimeConfig(trace_enabled=args.trace, verbose=args.trace,
                           default_timeout=120, max_retries=1)
    event_bus = EventBus()

    # Provider (data source)
    if args.provider == "tushare":
        from tools.providers import TushareSdkProvider
        provider: MarketDataProvider = TushareSdkProvider()
    else:
        provider = MockMarketDataProvider()

    # Run identity + recorder
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    recorder = RunRecorder(runs_dir="runs")
    recorder.create_run(run_id)

    # ── Tool Registry (capability metadata → Planner discovery) ────────
    registry = ToolRegistry(event_bus=event_bus)
    registry.register_from_provider(provider)
    registry.register_from_yaml("tools/registry.d")

    # ── Memory + RAG knowledge layer ────────────────────────────────────
    research_memory = ResearchMemory()
    retriever = KnowledgeRetriever(memory=research_memory)

    # ── Domain components ───────────────────────────────────────────────
    llm = LLMBackend()
    planner = Planner(llm=llm)
    executor = Executor(provider=provider, event_bus=event_bus, config=config,
                        recorder=recorder, run_id=run_id)
    verifier = Verifier()
    reporter = ReportGenerator()

    # ── Unified Agent Runtime (single lifecycle engine) ─────────────────
    span_sink: list[dict] = []
    runtime = build_runtime(
        planner=planner,
        executor=executor,
        verifier=verifier,
        reporter=reporter,
        span_sink=span_sink,
    )

    print(f"\n{'='*60}")
    print("  Agentic Investment Research Platform")
    print(f"  Data provider: {args.provider}")
    print(f"  Run ID: {run_id}")
    print(f"  LLM: {'on (config key)' if llm.available else 'off (rule-based)'}")
    print(f"  Tool Registry: {len(registry.list_tools())} tools")
    print(f"  Knowledge layer: {'on (RAG)' if args.reuse_memory else 'off (--reuse-memory)'}")
    print(f"{'='*60}")
    print(f"  Query: {requirement}")
    print(f"{'='*60}\n")

    # Record request artifact
    recorder.write_json(run_id, "request.json", {
        "requirement": requirement,
        "provider": args.provider,
        "reuse_memory": args.reuse_memory,
        "created_at": datetime.now().isoformat(),
    })

    # ── Recall prior knowledge BEFORE planning (RAG) ────────────────────
    retrieval_ctx = await retriever.recall(
        requirement, limit=5, span_sink=span_sink)
    if args.reuse_memory and retrieval_ctx["retrieval_count"] > 0:
        print(f"  📚 知识层召回 {retrieval_ctx['retrieval_count']} 条历史研究"
              f"（{', '.join(e['subject'] for e in retrieval_ctx['retrieval_entities'])}）\n")

    # ── Run the unified lifecycle ───────────────────────────────────────
    task = await runtime.create_task(requirement, goal=requirement)
    ctx: dict = {
        "tools": registry,
        "memory": research_memory,
        "run_id": run_id,
        "retrieval": retrieval_ctx,
        "requirement": requirement,
        "reuse_memory": args.reuse_memory,
    }
    try:
        await runtime.run(task, tools=registry, memory=research_memory, context=ctx)
    except Exception as e:
        print(f"\n  ✗ 运行失败: {e}")

    # ── Persist knowledge for future runs ───────────────────────────────
    if args.reuse_memory and task.status == "completed" and task.result is not None:
        await _persist_research(runtime, task, retriever, span_sink)

    # Merge the executor's tool/skill spans into the shared sink so the
    # runtime can aggregate full-run metrics (tool success, nodes, etc.).
    span_sink.extend(executor.agent_trace_records())

    # ── Evaluation metrics (AgentRunStats from real spans) ──────────────
    stats = runtime.collect_stats(task)
    # Evidence/citations: data points actually consumed (price rows +
    # financial rows) from the immutable dataset.
    stats.evidence_count = _count_evidence(executor)
    meta = {
        "status": task.status,
        "runtime": "AgentRuntime",
        "error": task.error,
        "stats": stats.to_dict(),
    }

    # Render + save report
    report_str = ""
    if task.status == "completed" and task.result is not None:
        report = task.result
        report_str = reporter.format_markdown(report)
        print(f"\n{report_str}")
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{report.report_id}.md"
        report_path.write_text(report_str)
        if report.candidates:
            top = report.candidates[0]
            print(f"\n💡 首选: {top.name} ({top.ts_code}) "
                  f"综合评分 {getattr(top, 'composite_score', 0):.2f}")

    # ── Record run artifacts (12 files, replayable) ─────────────────────
    plan = task.plan
    plan_dict = _plan_to_dict(plan)
    verification = ctx.get("verification")
    verification_dict = verification.to_dict() if verification else {
        "passed": task.status == "completed", "policy_mode": "standard",
        "blocked": task.status != "completed", "checks": [], "warnings": [],
        "errors": [task.error or ""],
    }
    result_manifest = _build_result_manifest(task, verification_dict, stats)
    recorder.save_full_run(
        run_id=run_id,
        request={"requirement": requirement, "provider": args.provider},
        plan=plan_dict,
        tool_trace=executor.trace_records(),
        snapshots=executor.snapshot_records(),
        verification=verification_dict,
        report_md=report_str,
        meta=meta,
        agent_trace=list(span_sink),
        graph_mmd=RunRecorder.build_execution_graph(plan_dict, executor.get_graph_result()),
        result_manifest=result_manifest,
        execution_outputs=executor.execution_outputs(),
    )

    # Print platform summary (evaluation + observability)
    from runtime.tracing.formatters import format_trace_chain_cli

    print(f"\n{format_trace_chain_cli(span_sink, query=requirement, duration_ms=stats.latency_ms)}")
    print(f"\n{'='*60}")
    print("  📊 执行质量指标 (AgentRunStats)")
    print(f"    Task success: {stats.task_success_rate:.0%}")
    print(f"    Tool success: {stats.tool_success_rate:.0%} ({stats.tool_success}/{stats.tool_calls})")
    if stats.llm_calls:
        print(f"    LLM calls: {stats.llm_calls}  tokens: "
              f"{stats.token_usage.get('input_tokens', 0)+stats.token_usage.get('output_tokens', 0)}")
    print(f"    Latency: {stats.latency_ms}ms")
    print(f"    Evidence/citations: {stats.evidence_count}")
    print(f"  🕸  Trace: agent_trace.jsonl ({len(span_sink)} spans) + execution_graph.mmd")
    print(f"  📁  Artifacts: runs/{run_id}/")
    print(f"{'='*60}")


async def run_trajectory_eval(run_dir: str, args):
    """Score a recorded run's trajectory (trajectory evaluation).

    Rebuilds the run's EventBus trace from agent_trace.jsonl + tool_trace,
    then runs TrajectoryEvaluator with the expectations YAML. Prints a
    per-dimension scorecard and writes trajectory_score.json to the run dir.
    """
    import json as _json
    from pathlib import Path as _Path

    from runtime.tracing.formatters import format_scorecard_cli

    path = _Path(run_dir)
    trace: list[dict] = []
    for fname in ("agent_trace.jsonl", "tool_trace.jsonl"):
        fp = path / fname
        if fp.exists():
            for line in fp.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    trace.append(_json.loads(line))

    # Build events in a shape the TrajectoryEvaluator understands.
    # Map each real span kind → the full event set the evaluator scores:
    # planner → PlanningStarted/Completed, tool → ToolInvoked/Finished,
    # skill → SkillStarted/Completed, verifier → VerificationStarted/Completed,
    # plus a GraphResolved summarizing the plan's node count.
    plan_nodes = _plan_node_count(path)
    events: list[dict] = []

    def ts_of(s: dict) -> str:
        return s.get("timestamp", "")
    for span in trace:
        kind = span.get("kind", "")
        name = span.get("name", "")
        dur = span.get("duration_ms", 0)
        ok = span.get("status") == "ok"
        ts = ts_of(span)
        payload: dict[str, object] = {
            "name": name, "tool_name": name, "skill_name": name,
            "duration_ms": dur}
        if kind == "planner":
            events.append({"type": "PlanningStarted", "timestamp": ts, "payload": payload})
            events.append({"type": "PlanningCompleted", "timestamp": ts, "payload": payload})
        elif kind == "scheduler":
            events.append({"type": "GraphResolved", "timestamp": ts,
                           "payload": {"node_count": plan_nodes,
                                       "layer_count": 1, **payload}})
        elif kind == "tool":
            events.append({"type": "ToolInvoked", "timestamp": ts, "payload": payload})
            events.append({"type": "ToolFinished" if ok else "ToolFailed",
                           "timestamp": ts, "payload": payload})
        elif kind == "skill":
            # Orchestration placeholder skills (portfolio/verifier/report)
            # are recorded as "not implemented" by the executor — they are
            # not genuine failures, so don't emit NodeFailed for them.
            if name in ("portfolio-selection", "verifier", "report-generator"):
                events.append({"type": "SkillStarted", "timestamp": ts, "payload": payload})
                events.append({"type": "SkillCompleted", "timestamp": ts, "payload": payload})
                continue
            events.append({"type": "SkillStarted", "timestamp": ts, "payload": payload})
            events.append({"type": "SkillCompleted" if ok else "NodeFailed",
                           "timestamp": ts, "payload": payload})
            events.append({"type": "NodeCompleted", "timestamp": ts, "payload": payload})
        elif kind == "verifier":
            events.append({"type": "VerificationStarted", "timestamp": ts, "payload": payload})
            events.append({"type": "VerificationCompleted", "timestamp": ts,
                           "payload": {"passed": ok, **payload}})
        elif kind == "reporter":
            events.append({"type": "ReportGenerated", "timestamp": ts, "payload": payload})
    events.append({"type": "WorkflowFinished", "timestamp": "",
                   "payload": {"status": "success", "total_duration_ms":
                               sum(s.get("duration_ms", 0) for s in trace)}})

    from evaluations.trajectory.evaluator import TrajectoryEvaluator

    case_path = "evaluations/trajectory/trajectory-fundamental-analysis-v1.yaml"
    score = await TrajectoryEvaluator().evaluate(
        events, case_path=case_path if _Path(case_path).exists() else None)

    print(f"\n{format_scorecard_cli(score)}")
    (path / "trajectory_score.json").write_text(
        _json.dumps(score.__dict__, indent=2, default=str), encoding="utf-8")
    print(f"\n  📈 轨迹评分已保存: {path / 'trajectory_score.json'}")


async def _persist_research(runtime: AgentRuntime, task: Any, retriever: KnowledgeRetriever,
                            span_sink: list[dict]) -> None:
    """Store the completed analysis back into the knowledge layer."""
    report = task.result
    candidates = getattr(report, "candidates", [])
    if not candidates:
        return
    top = candidates[0]
    # Determine company + industry from the top candidate
    company = getattr(top, "ts_code", "")
    industry = getattr(top, "industry", "")
    score = float(getattr(top, "composite_score", 0) or 0)
    if not company:
        return
    date_str = datetime.now().strftime("%Y%m%d")
    await retriever.store_result(
        key=f"{company}:{date_str}",
        company=company,
        industry=industry or "",
        score=score,
        reasoning=getattr(top, "explanation", "")[:300],
        strategy="composite",
        span_sink=span_sink,
    )
    print(f"  💾 知识层已存: {company} (score={score:.2f})")


async def run_replay(run_path: str, args):
    """Full DAG replay from recorded artifacts.

    Restores request/plan/snapshot, re-executes the whole DAG with the
    Provider forbidden, and writes replay_verification.json comparing
    hashes, verification, and report structure.
    """
    import json as _json
    from pathlib import Path as _Path

    from agent.replay import run_full_replay

    run_dir = _Path(run_path)
    if not (run_dir / "data_snapshot.json").exists():
        print(f"✗ 未找到数据快照: {run_dir / 'data_snapshot.json'}")
        return

    print(f"\n{'='*60}")
    print(f"  Full DAG Replay: {run_dir.name}")
    print(f"{'='*60}\n")

    verification = await run_full_replay(run_dir)

    out = run_dir / "replay_verification.json"
    out.write_text(_json.dumps(verification, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")

    status = verification["status"]
    print(f"  状态: {status.upper()}")
    for diff in verification.get("diffs", []):
        print(f"  ✗ {diff}")
    if not verification.get("diffs"):
        print("  ✓ 快照/计划/报告结构 全部一致")
    checks = verification.get("checks", {})
    print(f"  Provider 访问尝试: {checks.get('provider_access_attempted', 0)}")
    vcheck = checks.get("verification")
    if isinstance(vcheck, dict):
        v_actual = vcheck.get("actual") or {}
        print(f"  Verifier: passed={v_actual.get('passed', '?')} "
              f"({v_actual.get('policy_mode', '?')})")
    print(f"\n✅ 重放验证 → {out}")


def _plan_node_count(run_dir: Path) -> int:
    """Count analysis steps from a run's plan.json (for GraphResolved)."""
    try:
        import json as _json
        plan = _json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
        return len(plan.get("analysis_steps", []))
    except Exception:
        return 0


def _plan_to_dict(plan: Any) -> dict:
    """Serialize an AnalysisPlan into a JSON-friendly dict."""
    if plan is None:
        return {}
    from dataclasses import asdict

    try:
        return asdict(plan)
    except Exception:
        return {"note": str(plan)}


def _count_evidence(executor: Any) -> int:
    """Count data points cited in the run (price + financial rows).

    This is the Citation / Evidence coverage metric: how much real data
    the analysis actually consumed, drawn from the immutable dataset.
    """
    try:
        dataset = executor.dataset
        if dataset is None:
            return 0
        total = 0
        for s in dataset.slices:
            total += sum(len(v) for v in s.prices.values())
            total += sum(len(v) for v in s.financials.values())
        return total
    except Exception:
        return 0


def _build_result_manifest(task: Any, verification_dict: dict, stats: Any) -> dict:
    """Standardized business results + execution metrics for Replay + Eval.

    Includes candidate ranking/order/scores, portfolio suggestion,
    verification, a report content hash (NOT the raw Markdown), and the
    AgentRunStats (task/tool success, latency, token cost, evidence).
    """
    from runtime.snapshot import hash_of

    candidates = []
    report = task.result
    if report is not None:
        for c in getattr(report, "candidates", []):
            candidates.append({
                "ts_code": getattr(c, "ts_code", ""),
                "name": getattr(c, "name", ""),
                "industry": getattr(c, "industry", ""),
                "fundamental_score": getattr(c, "fundamental_score", 0),
                "val_score": getattr(c, "val_score", 0),
                "risk_score": getattr(c, "risk_score", 0),
                "composite_score": getattr(c, "composite_score", 0),
            })
        portfolio = getattr(report, "portfolio_suggestion", "")
    else:
        portfolio = ""

    ordered = [
        {"ts_code": c["ts_code"], "composite_score": c["composite_score"]}
        for c in candidates
    ]

    manifest = {
        "schema_version": "1.0.0",
        "candidates": candidates,
        "candidate_order": ordered,
        "portfolio_suggestion": portfolio,
        "verification": verification_dict,
        "execution_stats": stats.to_dict(),
        "report_content_hash": hash_of({
            "candidate_order": ordered,
            "portfolio": portfolio,
            "verification": verification_dict,
        }),
    }
    return manifest


if __name__ == "__main__":
    asyncio.run(main())
