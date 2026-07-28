# Tushare Investment Research Agent — Main Entry Point
#
# Usage:
#   python -m agent --requirement "Find investment opportunities under medium risk preference"
#   python -m agent --workflow portfolio-review --portfolio portfolio.json
#   python -m agent --interactive

import asyncio
import argparse
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))


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

    args = parser.parse_args()

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
                await run_research(req, args.output)
            except KeyboardInterrupt:
                print("\nExiting...")
                break
    elif args.requirement:
        await run_research(args.requirement, args.output)
    else:
        parser.print_help()


async def run_research(requirement: str, output_dir: str):
    """Run the investment research workflow for a given requirement.

    TODO: Wire up the full agent pipeline:
    1. Planner.create_plan(requirement)
    2. Executor.execute_plan(plan)
    3. Verifier.verify(plan, results)
    4. ReportGenerator.generate(plan, results, verification)
    5. ReportGenerator.format_markdown(report)
    6. Save to output_dir
    """
    print(f"\n{'='*60}")
    print(f"Investment Research Agent")
    print(f"{'='*60}")
    print(f"Requirement: {requirement}")
    print(f"Workflow: investment-research")
    print(f"{'='*60}\n")

    print("[TODO] Planner: Analyzing requirement...")
    print("[TODO] Executor: Collecting data...")
    print("[TODO] Executor: Running multi-strategy analysis...")
    print("[TODO] Verifier: Verifying results...")
    print("[TODO] Report Generator: Generating report...")

    print(f"\nReport will be saved to: {output_dir}/")
    print("(Full pipeline implementation pending — see docs/design.md)")


if __name__ == "__main__":
    asyncio.run(main())
