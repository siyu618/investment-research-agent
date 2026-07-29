# Tushare Investment Research Agent — Main Entry Point
#
# Usage:
#   python -m agent --requirement "Find investment opportunities under medium risk preference"
#   python -m agent --workflow portfolio-review --portfolio portfolio.json
#   python -m agent --interactive
#   python -m agent --requirement "Analyze ..." --trace     (full event trace)
#   python -m agent --replay session-a1b2c3d4               (replay session)

import asyncio
import argparse
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.executor import Executor
from agent.planner import Planner
from agent.verifier import Verifier
from agent.report_generator import ReportGenerator
from agent.memory import MemoryManager
from agent.registry import SkillRegistry
from runtime import RuntimeConfig
from runtime.harness import Harness
from runtime.lifecycle import LoggingHook
from runtime.tracing import EventBus
from runtime.models import Event, EventType


async def main():
    parser = argparse.ArgumentParser(
        description="Tushare Investment Research Agent"
    )
    parser.add_argument(
        "--requirement", "-r",
        type=str,
        help="Investment research requirement",
    )
    parser.add_argument(
        "--workflow", "-w",
        type=str,
        default="investment-research",
        choices=["investment-research", "portfolio-review", "stock-selection"],
        help="Workflow to execute",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode (prompt for requirements)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="reports",
        help="Report output directory",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable full event trace output",
    )
    parser.add_argument(
        "--trace-export",
        type=str,
        default=None,
        help="Export trace to JSON file",
    )
    parser.add_argument(
        "--replay",
        type=str,
        default=None,
        help="Replay events from a previous session",
    )

    args = parser.parse_args()

    # Replay mode
    if args.replay:
        # TODO: Load session from episodic memory and replay events
        print(f"[TODO] Replay mode for session: {args.replay}")
        return

    if args.interactive:
        print("Tushare Investment Research Agent — Interactive Mode")
        print("Enter your investment requirement (or 'quit' to exit):")
        while True:
            try:
                req = input("\n> ").strip()
                if req.lower() in ("quit", "exit", "q"):
                    break
                if not req:
                    continue
                result = await run_research(req, args.output, args.trace)
                if args.trace_export:
                    export_trace(result, args.trace_export)
            except KeyboardInterrupt:
                print("\nExiting...")
                break
    elif args.requirement:
        result = await run_research(args.requirement, args.output, args.trace)
        if args.trace_export:
            export_trace(result, args.trace_export)
    else:
        parser.print_help()


async def run_research(
    requirement: str,
    output_dir: str,
    trace_enabled: bool = False,
):
    """Run the investment research workflow using the Harness runtime."""
    config = RuntimeConfig(
        trace_enabled=trace_enabled,
        verbose=trace_enabled,
    )

    # Create runtime components
    event_bus = EventBus()
    harness = Harness(config=config, event_bus=event_bus)
    harness.add_hook(LoggingHook(verbose=trace_enabled))

    # Create domain components
    memory = MemoryManager()
    registry = SkillRegistry()
    planner = Planner()
    executor = Executor(memory=memory)
    verifier = Verifier()
    reporter = ReportGenerator()

    # Emit startup events
    event_bus.emit(Event(
        id="startup",
        type="WorkflowStarted",
        timestamp=__import__("datetime").datetime.now().isoformat(),
        correlation_id="system",
        payload={"workflow": "investment-research", "requirement": requirement},
    ))

    print(f"\n{'='*60}")
    print(f"Investment Research Agent")
    print(f"Runtime: Harness v1.0 + EventBus")
    print(f"{'='*60}")
    print(f"Requirement: {requirement}")
    print(f"Trace: {'enabled' if trace_enabled else 'disabled'}")
    print(f"{'='*60}\n")

    # Run through Harness
    result = await harness.run(
        planner=planner,
        executor=executor,
        verifier=verifier,
        reporter=reporter,
        requirement=requirement,
        registry=registry,
    )

    # Print summary
    print(f"\n{'='*60}")
    if result.success:
        print(f"✓ Research Complete ({result.total_duration_ms}ms)")
    else:
        print(f"✗ Research Failed: {result.error}")
    print(f"  Session: {result.session_id}")
    print(f"  Events emitted: {result.event_count}")
    print(f"{'='*60}")

    return result


def export_trace(result, filepath: str):
    """Export event trace to JSON file."""
    print(f"[TODO] Export trace to {filepath}")


if __name__ == "__main__":
    asyncio.run(main())
