# Agent Executor — Bridges Planner's AnalysisPlan with Scheduler + Skills
#
# Provider isolation:
#   DataCollector (exclusive provider access) → ResearchDataset → Skills
#
# Skills NEVER call a provider. They consume the immutable ResearchDataset
# injected into their context. This guarantees reproducibility and replay.

from __future__ import annotations

from typing import Any

from agent.data_collector import DataCollector
from runtime.graph import build_graph
from runtime.models import GraphResult, RuntimeConfig, TaskGraph
from runtime.run_recorder import RunRecorder
from runtime.scheduler import Scheduler
from runtime.snapshot import ResearchDataset
from strategies.base.models import AnalysisPlan
from strategies.loader import load_skill
from tools.providers import MarketDataProvider


class SkillMap:
    """Maps skill names to SkillLifecycle instances."""

    def __init__(self):
        self._map: dict[str, Any] = {
            "data-collector": None,
            "fundamental-analysis": load_skill("fundamental-analysis"),
            "valuation-analysis": load_skill("valuation-analysis"),
            "risk-analysis": load_skill("risk-analysis"),
            "portfolio-selection": None,
            "verifier": None,
            "report-generator": None,
        }

    def get(self, name: str) -> Any:
        return self._map.get(name)


class Executor:
    """Carries out the analysis plan via the DAG Scheduler.

    Data access pattern:
      DataCollector → ResearchDataset → skill context
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
        self.skills = SkillMap()
        self.event_bus = event_bus
        self.config = config
        self.recorder = recorder
        self.run_id = run_id
        self.collector = DataCollector(provider, recorder, run_id)
        self.scheduler: Scheduler | None = None
        self._last_graph_result: GraphResult | None = None
        self._stocks: list = []
        self._dataset: ResearchDataset | None = None
        self._requested_codes: list[str] = []
        self._agent_trace: list[dict] = []  # skill-level lifecycle entries

    # ─── Execution ─────────────────────────────────────────────────────

    async def execute_plan(self, plan: AnalysisPlan) -> dict:
        """Execute an AnalysisPlan using the Scheduler."""
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
            from runtime.snapshot import hash_of
            from runtime.tracing.trace_span import trace_span
            from skills.base.skill_sdk import SkillPlan

            if node.skill == "data-collector":
                return await self._run_data_collector(input_data)
            skill = self.skills.get(node.skill)
            if skill is None:
                async with trace_span(
                    self.run_id, node.id, "skill", node.skill,
                    sink=self._agent_trace,
                ) as span:
                    span.status = "error"
                    span.error = f"skill '{node.skill}' not implemented"
                    span.set_input(input_data)
                return {"note": f"skill '{node.skill}' not implemented as skill",
                        "input": input_data}

            # Snapshot immutability guard: hash BEFORE the skill runs
            pre_hash = hash_of(self._dataset.to_dict()) if self._dataset else ""

            async with trace_span(
                self.run_id, node.id, "skill", node.skill,
                sink=self._agent_trace,
            ) as span:
                ctx = dict(input_data)
                ctx["stocks"] = self._stock_objects()
                ctx["dataset"] = self._dataset  # Skills consume snapshots only
                span.set_input({"stock_count": len(self._stocks)})
                try:
                    output = await skill.execute(ctx, SkillPlan())

                    # Verify the skill did NOT mutate shared data
                    post_hash = hash_of(self._dataset.to_dict()) if self._dataset else ""
                    if pre_hash and post_hash != pre_hash:
                        from runtime.errors import FatalError

                        raise FatalError(
                            f"Skill '{node.skill}' mutated shared snapshot data "
                            f"(hash changed: {pre_hash[:8]} → {post_hash[:8]})"
                        )

                    span.set_output({"score": getattr(output, "score", None)})
                    return output
                except Exception as e:
                    span.set_output({})
                    span.error = str(e)[:200]
                    span.status = "error"
                    raise

        result = await self.scheduler.run(
            graph=graph,
            context=context,
            skill_executor=skill_executor,
        )

        self._last_graph_result = result

        # Fail loudly if the data-collector step failed — an empty
        # universe would otherwise produce a misleading "no candidates" report.
        for node_id, node_result in result.node_results.items():
            if node_id == "step-1" and not node_result.success:
                from runtime.errors import FatalError

                raise FatalError(
                    f"Data collection step failed: {node_result.error}"
                )

        return {
            node_id: node_result.output or {}
            for node_id, node_result in result.node_results.items()
        }

    # ─── Data Collection (delegated to DataCollector) ──────────────────

    def set_dataset(self, dataset: ResearchDataset) -> None:
        """Inject a pre-built dataset (used by replay — no provider access)."""
        self._dataset = dataset
        self._stocks = dataset.stocks()

    async def _run_data_collector(self, input_data: dict) -> dict:
        """Collect all data layers via DataCollector → ResearchDataset.

        In replay mode (dataset pre-injected), reuses the dataset instead
        of touching the provider.
        """
        if self._dataset is not None:
            return {
                "stock_count": len(self._stocks),
                "stocks": self._stocks,
                "stocks_basic": self._stocks,
                "dataset": self._dataset.to_dict(),
                "replayed": True,
            }
        requested = list(input_data.get("stock_codes") or []) or self._requested_codes
        start_date = str(input_data.get("start_date", "20240101"))
        end_date = str(input_data.get("end_date", "20251231"))
        as_of = input_data.get("as_of") or None

        dataset = await self.collector.collect(
            stock_codes=requested or None,
            start_date=start_date,
            end_date=end_date,
            as_of=as_of,
        )
        self._dataset = dataset
        self._stocks = dataset.stocks()
        return {
            "stock_count": len(self._stocks),
            "stocks": self._stocks,
            "stocks_basic": [
                {"ts_code": s["ts_code"], "name": s.get("name", s["ts_code"]),
                 "industry": s.get("industry", "")}
                for s in self._stocks
            ],
            "dataset": dataset.to_dict(),
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
        """Serialized dataset slices for data_snapshot.json."""
        if self._dataset:
            return [s.to_dict() for s in self._dataset.slices]
        return []

    def trace_records(self) -> list[dict]:
        """Serialized tool-call trace (for tool_trace.jsonl)."""
        return list(self.collector.trace_records)

    def agent_trace_records(self) -> list[dict]:
        """Unified lifecycle trace: collector tool calls + skill executions."""
        return list(self.collector.trace_records) + list(self._agent_trace)

    def get_graph_result(self) -> GraphResult | None:
        return self._last_graph_result

    def _stock_objects(self) -> list:
        """Convert dataset stock dicts to StockBasic objects for skills."""
        from tools.providers import StockBasic

        return [
            StockBasic(
                ts_code=s.get("ts_code", ""),
                name=s.get("name", s.get("ts_code", "")),
                industry=s.get("industry", ""),
                market=s.get("market", ""),
                list_date=s.get("list_date", ""),
            )
            for s in self._stocks
        ]

    @property
    def stocks(self) -> list:
        return self._stocks

    @property
    def dataset(self) -> ResearchDataset | None:
        return self._dataset
