# Agent Runtime Adapter — bridges the domain components into AgentRuntime
#
# AgentRuntime (runtime/agent_runtime.py) is the SINGLE, domain-agnostic
# lifecycle engine:
#
#   create_task → plan → schedule → execute → aggregate → report
#
# This adapter supplies the runtime's injected contracts from the
# investment domain:
#
#   planner    — Planner.plan_for_goal (dynamic, tool-aware) | create_plan
#   scheduler  — Executor.execute_plan (AnalysisPlan → TaskGraph → Scheduler)
#   verifier   — Verifier.verify (multi-phase, policy gated)
#   reporter   — ReportGenerator.generate (structured InvestmentReport)
#   aggregator — collects per-node outputs into a standardized result dict
#
# Business logic (skills, verifier, reporter) never touches the runtime
# directly; it is injected here. The runtime records a real trace span for
# every stage, so the full chain is observable.
#
# The `verifier` is a genuine lifecycle stage in AgentRuntime: verification
# runs INSIDE the scheduler's execute step via the executor's skill_executor
# closure, and the report stage gates on it (FatalError on failure).

from __future__ import annotations

from typing import Any

from runtime.errors import FatalError
from runtime.tracing.trace_span import trace_span
from strategies.base.models import AnalysisPlan

# ─── Verifier stage ──────────────────────────────────────────────────────


class InvestmentVerifierStage:
    """Runs Verifier.verify inside the AgentRuntime aggregate stage.

    The runtime calls `aggregator(exec_result, ctx)` between execute and
    report. We use that hook to run the domain verifier and enforce the
    policy gate BEFORE the report is produced.
    """

    def __init__(self, verifier: Any, span_sink: list[dict] | None = None):
        self.verifier = verifier
        self.span_sink = span_sink

    async def __call__(self, exec_result: dict, ctx: dict) -> dict:
        plan = ctx.get("plan")
        if plan is None or not hasattr(plan, "analysis_steps"):
            return exec_result

        run_id = ctx.get("run_id", "runtime")
        # Real verification span — recorded into the shared sink so the
        # full chain (User Query → Planner → Agent → Tool → Verifier → Result)
        # is observable from agent_trace.jsonl.
        async with trace_span(
            run_id, "verifier", "verifier", "Verifier", sink=self.span_sink,
        ) as span:
            span.set_input({"plan": getattr(plan, "objective", "")})
            verification = await self.verifier.verify(plan, exec_result)
            span.set_output(verification.to_dict()
                            if hasattr(verification, "to_dict") else {})
            if not verification.passed:
                span.status = "failed"
                span.error = "; ".join(getattr(verification, "errors", [])[:2])

        ctx["verification"] = verification
        if not verification.passed:
            raise FatalError(
                "Verification failed: "
                + "; ".join(getattr(verification, "errors", [])[:3])
            )
        return exec_result


# ─── Reporter stage ──────────────────────────────────────────────────────


class InvestmentReporterStage:
    """Runs ReportGenerator.generate with the verification result in scope."""

    def __init__(self, reporter: Any):
        self.reporter = reporter

    async def __call__(self, task: Any, aggregated: dict, ctx: dict) -> Any:
        plan = ctx.get("plan")
        verification = ctx.get("verification")
        if plan is None or verification is None:
            return aggregated
        return await self.reporter.generate(plan, aggregated, verification)


# ─── Scheduler adapter ───────────────────────────────────────────────────


class InvestmentExecutorAdapter:
    """Adapts the domain Executor (AnalysisPlan → TaskGraph → Scheduler)
    to the runtime's injected scheduler contract.

    The runtime's _execute stage calls `scheduler.run(plan, ctx)`; the
    Executor already converts an AnalysisPlan to a TaskGraph and runs it.
    """

    def __init__(self, executor: Any):
        self.executor = executor

    async def run(self, plan: AnalysisPlan, ctx: dict) -> dict:
        return await self.executor.execute_plan(plan)


# ─── Aggregate stage ─────────────────────────────────────────────────────


class ResultAggregator:
    """Merges per-node outputs into a standardized result dict.

    The domain verifier and reporter consume this shape, so the aggregator
    only has to pass through the executor's node-result dict.
    """

    def __init__(self):
        pass

    async def __call__(self, exec_result: dict, ctx: dict) -> dict:
        # exec_result is already {node_id: output}. Keep it stable.
        return exec_result


def build_runtime(
    *,
    planner: Any,
    executor: Any,
    verifier: Any,
    reporter: Any,
    span_sink: list[dict] | None = None,
) -> Any:
    """Assemble an AgentRuntime from the investment domain components.

    Returns a fully-wired AgentRuntime whose injected stages are the
    domain adapters above.
    """
    from runtime.agent_runtime import AgentRuntime

    sink = span_sink if span_sink is not None else []
    scheduler = InvestmentExecutorAdapter(executor)
    aggregator = InvestmentVerifierStage(verifier, span_sink=sink)
    reporter_stage = InvestmentReporterStage(reporter)

    return AgentRuntime(
        planner=planner,
        scheduler=scheduler,
        aggregator=aggregator,
        reporter=reporter_stage,
        span_sink=sink,
    )
