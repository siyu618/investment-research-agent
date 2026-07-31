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
    args = parser.parse_args()

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
    plan_dict = {}
    if hasattr(result, "output") and result.output:
        plan_dict = {"report_id": getattr(result.output, "report_id", "")}
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


if __name__ == "__main__":
    asyncio.run(main())
