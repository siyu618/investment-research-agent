# Agent Executor — Plan execution via Scheduler + Skill registry
#
# This bridges the Planner's output (AnalysisPlan) with the Scheduler.
# It converts plans into TaskGraphs and delegates execution to the Scheduler.

from __future__ import annotations

from typing import Any, Callable, Optional

from runtime.graph import build_graph
from runtime.models import (
    GraphResult,
    RuntimeConfig,
    TaskGraph,
)
from runtime.scheduler import Scheduler
from strategies.base.models import AnalysisPlan, AnalysisResult


class Executor:
    """Carries out the analysis plan via the DAG Scheduler.

    Converts the Planner's AnalysisPlan into a TaskGraph and
    delegates to the Scheduler for parallel DAG execution.
    """

    def __init__(
        self,
        skill_registry: Any = None,
        event_bus: Any = None,
        config: Optional[RuntimeConfig] = None,
    ):
        self.skill_registry = skill_registry
        self.event_bus = event_bus
        self.config = config
        self.scheduler: Optional[Scheduler] = None
        self._last_graph_result: Optional[GraphResult] = None

    async def execute_plan(
        self,
        plan: AnalysisPlan,
        skill_executor: Optional[Callable] = None,
    ) -> dict:
        """Execute an AnalysisPlan using the Scheduler.

        Converts the plan to a TaskGraph, then runs it.
        If the plan is already a TaskGraph, runs it directly.

        Args:
            plan: AnalysisPlan (or TaskGraph) from the Planner.
            skill_executor: Optional callable for skill invocation.

        Returns:
            Dict of step_id → result (backward compatible) or
            GraphResult.node_results if plan was already a TaskGraph.
        """
        # Check if this is already a TaskGraph
        if isinstance(plan, TaskGraph):
            return await self._execute_graph(plan, skill_executor)

        # Convert AnalysisPlan to TaskGraph
        graph = self._plan_to_graph(plan)

        # Execute
        result = await self._execute_graph(graph, skill_executor)

        # Backward compat: convert to step_id → result dict
        return {
            node_id: node_result.output
            for node_id, node_result in result.node_results.items()
        }

    async def _execute_graph(
        self,
        graph: TaskGraph,
        skill_executor: Optional[Callable] = None,
    ) -> GraphResult:
        """Execute a TaskGraph via the Scheduler."""
        from runtime.models import ExecutionContext

        # Create scheduler if not exists
        if self.scheduler is None:
            self.scheduler = Scheduler(
                skill_registry=self.skill_registry,
                event_bus=self.event_bus,
                config=self.config,
            )

        # Build minimal context
        context = ExecutionContext(
            session_id="executor-run",
            correlation_id="executor-run",
            user_requirement="execute_plan",
        )

        result = await self.scheduler.run(
            graph=graph,
            context=context,
            skill_executor=skill_executor,
        )

        self._last_graph_result = result
        return result

    def _plan_to_graph(self, plan: AnalysisPlan) -> TaskGraph:
        """Convert an AnalysisPlan to a TaskGraph.

        Maps each AnalysisStep to a TaskNode, preserving dependencies
        so the Scheduler can parallelize independent steps.
        """
        nodes = []
        for step in plan.analysis_steps:
            # Determine tags from step status
            tags = []
            if step.depends_on:
                tags.append("sequential")
            else:
                tags.append("parallel-capable")

            nodes.append({
                "id": f"step-{step.id}",
                "label": f"{step.skill}: {step.target}",
                "skill": step.skill,
                "timeout": step.params.get("timeout", 60),
                "max_retries": step.params.get("max_retries", 2),
                "tags": tags,
            })

        edges = []
        for step in plan.analysis_steps:
            for dep_id in step.depends_on:
                edges.append((f"step-{dep_id}", f"step-{step.id}"))

        # Auto-detect entry points and output nodes
        all_targets = {t for _, t in edges}
        entry_points = [
            n["id"] for n in nodes if n["id"] not in all_targets
        ]
        all_sources = {s for s, _ in edges}
        output_nodes = [
            n["id"] for n in nodes if n["id"] not in all_sources
        ]

        return build_graph(
            nodes=nodes,
            edges=edges,
            entry_points=entry_points or None,
            output_nodes=output_nodes or None,
        )

    def get_graph_result(self) -> Optional[GraphResult]:
        """Get the last graph execution result."""
        return self._last_graph_result
