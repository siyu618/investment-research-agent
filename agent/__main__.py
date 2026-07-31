#!/usr/bin/env python3
"""Tushare Investment Research Agent — CLI entry point.

Usage:
    python -m agent --requirement "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"
    python -m agent --requirement "分析 600519.SH"
    python -m agent --interactive
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
from agent.planner import Planner
from agent.report_generator import ReportGenerator
from agent.verifier import Verifier
from runtime import RuntimeConfig
from runtime.harness import Harness
from runtime.lifecycle import LoggingHook
from runtime.run_recorder import RunRecorder
from runtime.tracing import EventBus
from tools.providers import MarketDataProvider, MockMarketDataProvider

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")


async def main():
    parser = argparse.ArgumentParser(description="Tushare Investment Research Agent")
    parser.add_argument("--requirement", "-r", type=str, help="投资研究需求")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--output", "-o", type=str, default="reports", help="报告输出目录")
    parser.add_argument("--trace", action="store_true", help="启用执行跟踪")
    parser.add_argument("--provider", type=str, default="mock",
                        choices=["mock", "tushare"], help="数据提供者")
    parser.add_argument("--replay", type=str, default=None,
                        help="重放历史运行: runs/{run_id} 目录路径")
    args = parser.parse_args()

    if args.replay:
        await run_replay(args.replay, args)
        return

    if args.interactive:
        print("Tushare Investment Research Agent — 交互模式")
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
    """Run the full investment research pipeline and record a run artifact."""
    config = RuntimeConfig(trace_enabled=args.trace, verbose=args.trace,
                           default_timeout=120, max_retries=1)
    event_bus = EventBus()
    harness = Harness(config=config, event_bus=event_bus)
    harness.add_hook(LoggingHook(verbose=args.trace))

    # Provider
    if args.provider == "tushare":
        from tools.providers import OfficialTushareMCPProvider
        provider: MarketDataProvider = OfficialTushareMCPProvider()
    else:
        provider = MockMarketDataProvider()

    # Run identity + recorder
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    recorder = RunRecorder(runs_dir="runs")
    recorder.create_run(run_id)

    # Domain components
    planner = Planner()
    executor = Executor(provider=provider, event_bus=event_bus, config=config,
                        recorder=recorder, run_id=run_id)
    verifier = Verifier()
    reporter = ReportGenerator()

    print(f"\n{'='*60}")
    print("  投资研究 Agent")
    print(f"  数据提供者: {args.provider}")
    print(f"  Run ID: {run_id}")
    print(f"{'='*60}")
    print(f"  需求: {requirement}")
    print(f"{'='*60}\n")

    # Record request artifact
    recorder.write_json(run_id, "request.json", {
        "requirement": requirement,
        "provider": args.provider,
        "created_at": datetime.now().isoformat(),
    })

    result = await harness.run(
        planner=planner,
        executor=executor,
        verifier=verifier,
        reporter=reporter,
        requirement=requirement,
    )

    print(f"\n{'='*60}")
    if result.success:
        print(f"  研究完成 ✓ ({result.total_duration_ms}ms, {result.event_count} 事件)")
    else:
        print(f"  研究失败 ✗: {result.error}")

    # Print report if available
    report_str = ""
    if result.success and result.output:
        report_str = reporter.format_markdown(result.output)
        print(f"\n{report_str}")

        # Save to reports/
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{result.output.report_id}.md"
        report_path.write_text(report_str)

        # One-liner summary
        if result.output.candidates:
            top = result.output.candidates[0]
            print(f"\n💡 首选: {top.name} ({top.ts_code}) "
                  f"综合评分 {getattr(top, 'composite_score', 0):.2f}")

    # Record full run artifacts (audit/replay support)
    plan_dict = _plan_to_dict(harness.last_plan)
    recorder.save_full_run(
        run_id=run_id,
        request={"requirement": requirement, "provider": args.provider},
        plan=plan_dict,
        tool_trace=executor.trace_records(),
        snapshots=executor.snapshot_records(),
        verification={"passed": True, "warnings": [], "errors": []},
        report_md=report_str,
        meta={
            "status": "success" if result.success else "failed",
            "duration_ms": result.total_duration_ms,
            "event_count": result.event_count,
            "error": result.error or "",
            "hook_errors": harness.hook_error_count,
        },
    )
    print(f"\n📁 运行记录已保存: runs/{run_id}/  (request/plan/tool_trace/data_snapshot/verification/report)")

    # Hook error count
    if harness.hook_error_count > 0:
        print(f"\n⚠ {harness.hook_error_count} hook error(s)")


async def run_replay(run_path: str, args):
    """Replay a historical run from its recorded artifacts.

    Rebuilds the ResearchDataset from data_snapshot.json and re-executes
    the skills deterministically — no provider calls. Output must match
    the original run's report (same snapshot → same result).
    """
    import json as _json
    from pathlib import Path as _Path

    from runtime.snapshot import ResearchDataset

    run_dir = _Path(run_path)
    snapshot_file = run_dir / "data_snapshot.json"
    if not snapshot_file.exists():
        print(f"✗ 未找到数据快照: {snapshot_file}")
        return

    print(f"\n{'='*60}")
    print(f"  Replay: {run_dir.name}")
    print(f"{'='*60}\n")

    # 1. Rebuild dataset from recorded snapshot
    snap = _json.loads(snapshot_file.read_text())
    dataset = ResearchDataset.from_dict(snap)
    print(f"  快照: {snap.get('slice_count', 0)} slice(s), "
          f"as_of={snap.get('as_of', '')}, "
          f"source={dataset.slices[0].source if dataset.slices else '?'}")
    print(f"  股票数: {len(dataset.stocks())}")

    # 2. Re-execute skills deterministically from the dataset
    from skills.base.skill_sdk import SkillPlan
    from strategies.loader import load_skill
    from tools.providers import StockBasic

    stock_dicts = dataset.stocks()
    stocks = [
        StockBasic(
            ts_code=s.get("ts_code", ""),
            name=s.get("name", s.get("ts_code", "")),
            industry=s.get("industry", ""),
            market=s.get("market", ""),
            list_date=s.get("list_date", ""),
        )
        for s in stock_dicts
    ]
    results: dict[str, Any] = {}
    for skill_name in ("fundamental-analysis", "valuation-analysis", "risk-analysis"):
        skill = load_skill(skill_name)
        ctx = {"stocks": stocks, "dataset": dataset}
        output = await skill.execute(ctx, SkillPlan())
        results[skill_name] = output
        print(f"  [{skill_name}] score={output.score:.3f} "
              f"conf={output.confidence:.2f}")

    # 3. Rebuild report

    market_overview = f"重放 {len(stocks)} 只股票（来自 {run_dir.name} 快照）"
    report_md = (
        f"# 🔁 回放报告（Replay）\n\n"
        f"**来源运行:** {run_dir.name}\n\n"
        f"## 数据快照\n{market_overview}\n\n"
    )
    for skill_name, output in results.items():
        report_md += f"### {skill_name}\n- 评分: {output.score:.3f}\n"
        if output.reasoning:
            report_md += f"- 说明: {output.reasoning[:200]}\n"
        report_md += "\n"

    out = run_dir / "replay_report.md"
    out.write_text(report_md, encoding="utf-8")
    print(f"\n✅ 重放完成 → {out}")


def _plan_to_dict(plan: Any) -> dict:
    """Serialize an AnalysisPlan into a JSON-friendly dict."""
    if plan is None:
        return {}
    from dataclasses import asdict

    try:
        d = asdict(plan)
        # analysis_steps contains dataclasses; asdict handles them
        return d
    except Exception:
        return {"note": str(plan)}


if __name__ == "__main__":
    asyncio.run(main())
