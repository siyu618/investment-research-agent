# Agent Executor — Bridges Planner's AnalysisPlan with Scheduler + Skills
#
# Converts AnalysisPlan to TaskGraph, registers skills, and passes
# MarketDataProvider to all skills through shared state.
# Data flows through DataSnapshot wrappers so every run is auditable
# and replayable (as_of, source, query_params, data_hash, version).

from __future__ import annotations

from datetime import datetime
from typing import Any

from runtime.graph import build_graph
from runtime.models import GraphResult, RuntimeConfig, TaskGraph
from runtime.run_recorder import RunRecorder
from runtime.scheduler import Scheduler
from runtime.snapshot import DataSnapshot
from runtime.tracing.agent_trace import TraceRecord
from strategies.base.models import AnalysisPlan
from strategies.loader import load_skill
from tools.providers import MarketDataProvider


class SkillMap:
    """Maps skill names to SkillLifecycle instances."""

    def __init__(self, provider: MarketDataProvider):
        self._map: dict[str, Any] = {
            "data-collector": None,
            "fundamental-analysis": load_skill("fundamental-analysis", provider=provider),
            "valuation-analysis": load_skill("valuation-analysis", provider=provider),
            "risk-analysis": load_skill("risk-analysis", provider=provider),
            "portfolio-selection": None,
            "verifier": None,
            "report-generator": None,
        }

    def get(self, name: str) -> Any:
        return self._map.get(name)


class Executor:
    """Carries out the analysis plan via the DAG Scheduler.

    Data access pattern:
      data-collector → MarketDataProvider → DataSnapshot → skill context

    Every snapshot is recorded for the run output. Skill inputs are
    derived from the snapshot so Skills never read uncontrolled data.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        event_bus: Any = None,
        config: RuntimeConfig | None = None,
        recorder: RunRecorder | None = None,
        run_id: str = "",
    ):
        self.provider = provider
        self.skills = SkillMap(provider)
        self.event_bus = event_bus
        self.config = config
        self.recorder = recorder
        self.run_id = run_id
        self.scheduler: Scheduler | None = None
        self._last_graph_result: GraphResult | None = None
        self._stocks: list = []
        self._snapshots: list[DataSnapshot] = []
        self._trace_records: list[TraceRecord] = []
        self._requested_codes: list[str] = []

    # ─── Execution ─────────────────────────────────────────────────────

    async def execute_plan(self, plan: AnalysisPlan) -> dict:
        """Execute an AnalysisPlan using the Scheduler.

        Extracts requested stock codes from the plan's data step so the
        data-collector can filter the universe even when the Scheduler
        passes an empty graph state (first node has no upstream input).
        """
        for step in plan.analysis_steps:
            if step.skill == "data-collector":
                self._requested_codes = list(step.params.get("stock_codes") or [])
                break
        graph = self._plan_to_graph(plan)
        return await self._execute_graph(graph)

    async def _execute_graph(self, graph: TaskGraph) -> dict:
        from runtime.models import ExecutionContext

        if self.scheduler is None:
            self.scheduler = Scheduler(
                event_bus=self.event_bus,
                config=self.config,
            )

        context = ExecutionContext(
            session_id="executor-run",
            correlation_id="executor-run",
            user_requirement="execute_plan",
        )

        async def skill_executor(node, input_data, context):
            if node.skill == "data-collector":
                return await self._run_data_collector(input_data)
            skill = self.skills.get(node.skill)
            if skill is None:
                return {"note": f"skill '{node.skill}' not implemented as skill", "input": input_data}
            ctx = dict(input_data)
            ctx["stocks"] = self._stocks
            ctx["provider"] = self.provider
            # Attach latest snapshot metadata so skills can validate as_of
            if self._snapshots:
                ctx["snapshot"] = self._snapshots[-1]
            from skills.base.skill_sdk import SkillPlan
            return await skill.execute(ctx, SkillPlan())

        result = await self.scheduler.run(
            graph=graph,
            context=context,
            skill_executor=skill_executor,
        )

        self._last_graph_result = result
        return {
            node_id: node_result.output or {}
            for node_id, node_result in result.node_results.items()
        }

    # ─── Data Collection (snapshot-backed) ─────────────────────────────

    async def _run_data_collector(self, input_data: dict) -> dict:
        """Load stock universe from provider and wrap it in a DataSnapshot.

        Honors explicit ts_code requests (single-stock analysis) by
        filtering the provider's universe to the requested codes.
        """
        start = datetime.now()
        stocks = await self.provider.get_stock_basic()

        requested = list(input_data.get("stock_codes") or []) or self._requested_codes
        if requested:
            requested_set = set(requested)
            stocks = [s for s in stocks if s.ts_code in requested_set]

        # Build a point-in-time snapshot
        as_of = input_data.get("end_date", "20251231")
        snapshot = DataSnapshot.from_rows(
            rows=stocks,
            source=self.provider.__class__.__name__,
            query_params={"stock_codes": requested or None},
            as_of=as_of,
            publish_date=datetime.now().strftime("%Y-%m-%d"),
        )
        self._snapshots.append(snapshot)

        # Record tool trace
        self._trace_records.append(TraceRecord.make(
            run_id=self.run_id,
            step_id="data-collector",
            kind="tool",
            name="get_stock_basic",
            input_data={"stock_codes": requested or None},
            output_data=snapshot.to_dict(),
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
        ))

        self._stocks = stocks
        return {
            "stock_count": len(stocks),
            "stocks": stocks,
            "stocks_basic": [
                {"ts_code": s.ts_code, "name": s.name, "industry": s.industry}
                for s in stocks
            ],
            "snapshot": snapshot.to_dict(),
        }

    # ─── Plan → Graph ──────────────────────────────────────────────────

    def _plan_to_graph(self, plan: AnalysisPlan) -> TaskGraph:
        """Convert AnalysisPlan to TaskGraph, preserving dependencies for parallelism."""
        nodes = []
        for step in plan.analysis_steps:
            nodes.append({
                "id": f"step-{step.id}",
                "label": f"{step.skill}: {step.target}",
                "skill": step.skill,
                "timeout": step.params.get("timeout", 60),
                "max_retries": 1,
                "tags": [],
            })

        edges = []
        for step in plan.analysis_steps:
            for dep_id in step.depends_on:
                edges.append((f"step-{dep_id}", f"step-{step.id}"))

        all_targets = {t for _, t in edges}
        entry_points = [n["id"] for n in nodes if n["id"] not in all_targets]
        all_sources = {s for s, _ in edges}
        output_nodes = [n["id"] for n in nodes if n["id"] not in all_sources]

        return build_graph(
            nodes=nodes,
            edges=edges,
            entry_points=entry_points or None,
            output_nodes=output_nodes or None,
        )

    # ─── Run artifact accessors ────────────────────────────────────────

    def snapshot_records(self) -> list[dict]:
        """Serialized snapshots for the data_snapshot.json artifact."""
        return [s.to_dict() for s in self._snapshots]

    def trace_records(self) -> list[dict]:
        """Serialized trace records for tool_trace.jsonl."""
        return [r.to_jsonl() for r in self._trace_records]

    def get_graph_result(self) -> GraphResult | None:
        return self._last_graph_result

    @property
    def stocks(self) -> list:
        return self._stocks
