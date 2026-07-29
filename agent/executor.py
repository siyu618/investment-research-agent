# Agent Executor — Bridges Planner's AnalysisPlan with Scheduler + Skills
#
# Converts AnalysisPlan to TaskGraph, registers skills, and passes
# MarketDataProvider to all skills through shared state.

from __future__ import annotations

from typing import Any, Callable, Optional

from runtime.graph import build_graph
from runtime.models import GraphResult, RuntimeConfig, TaskGraph
from runtime.scheduler import Scheduler
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

    Converts AnalysisPlan → TaskGraph → Scheduler.
    Injects MarketDataProvider and stock universe into skill context.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        event_bus: Any = None,
        config: Optional[RuntimeConfig] = None,
    ):
        self.provider = provider
        self.skills = SkillMap(provider)
        self.event_bus = event_bus
        self.config = config
        self.scheduler: Optional[Scheduler] = None
        self._last_graph_result: Optional[GraphResult] = None
        self._stocks: list = []  # loaded by data-collector step

    async def execute_plan(self, plan: AnalysisPlan) -> dict:
        """Execute an AnalysisPlan using the Scheduler."""
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

        # Create a skill executor callable that the Scheduler calls
        async def skill_executor(node, input_data, context):
            if node.skill == "data-collector":
                return await self._run_data_collector(input_data)
            skill = self.skills.get(node.skill)
            if skill is None:
                return {"note": f"skill '{node.skill}' not implemented as skill", "input": input_data}
            # Inject stocks + provider into context
            ctx = dict(input_data)
            ctx["stocks"] = self._stocks
            ctx["provider"] = self.provider
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

    async def _run_data_collector(self, input_data: dict) -> dict:
        """Load stock universe from provider."""
        stocks = await self.provider.get_stock_basic()
        self._stocks = stocks
        return {
            "stock_count": len(stocks),
            "stocks": stocks,
            "stocks_basic": [{"ts_code": s.ts_code, "name": s.name, "industry": s.industry} for s in stocks],
        }

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

    def get_graph_result(self) -> Optional[GraphResult]:
        return self._last_graph_result

    @property
    def stocks(self) -> list:
        return self._stocks
