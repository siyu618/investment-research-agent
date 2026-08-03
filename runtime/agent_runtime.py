# Agent Runtime — unified, domain-agnostic agent lifecycle
#
# The Agent Runtime owns the FULL lifecycle of any agent task:
#   create_task → plan → schedule → execute → aggregate → report
#
# It is intentionally decoupled from business logic: the Planner, Executor
# (via Scheduler), Tool Registry, Memory, and Reporter are injected. Any
# domain (investment research, code review, QA) can drive this runtime by
# supplying its own components.
#
# Lifecycle with real trace spans (Observability):
#   User Query → create_task (trace: task)
#             → plan        (trace: planner)
#             → schedule    (trace: scheduler)
#             → execute     (trace: agent/tool/skill per node)
#             → aggregate   (trace: aggregator)
#             → report      (trace: reporter)

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from runtime.tracing.trace_span import trace_span


@dataclass
class AgentTask:
    """A single agent task — created from a user query, executed by the runtime."""
    task_id: str
    user_query: str
    goal: str = ""
    status: str = "created"      # created → planned → running → completed/failed
    plan: Any = None             # structured TaskPlan from Planner
    result: Any = None           # final report / output
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""
    spans: list[dict] = field(default_factory=list)  # real trace spans


@dataclass
class AgentRunStats:
    """Execution-quality metrics collected during a run."""
    task_id: str
    task_success: bool = False
    node_total: int = 0
    node_success: int = 0
    node_failed: int = 0
    tool_calls: int = 0
    tool_success: int = 0
    tool_failed: int = 0
    latency_ms: int = 0
    token_usage: dict = field(default_factory=dict)
    evidence_count: int = 0      # data points cited in the final output

    @property
    def task_success_rate(self) -> float:
        return 1.0 if self.task_success else 0.0

    @property
    def tool_success_rate(self) -> float:
        return self.tool_success / self.tool_calls if self.tool_calls else 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_success": self.task_success,
            "task_success_rate": self.task_success_rate,
            "node_total": self.node_total,
            "node_success": self.node_success,
            "node_failed": self.node_failed,
            "tool_calls": self.tool_calls,
            "tool_success": self.tool_success,
            "tool_failed": self.tool_failed,
            "tool_success_rate": self.tool_success_rate,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
            "evidence_count": self.evidence_count,
        }


class AgentRuntime:
    """Unified agent lifecycle runtime (domain-agnostic).

    Usage:
        runtime = AgentRuntime(
            planner=my_planner,        # has async plan(goal, tools) -> TaskPlan
            scheduler=my_scheduler,    # has async run(graph, ...) -> GraphResult
            reporter=my_reporter,      # has async report(task, result) -> Any
            span_sink=[],              # collects real trace spans
        )
        task = await runtime.create_task("分析某股票投资价值")
        result = await runtime.run(task, tools=registry)

    The runtime records real spans for each lifecycle stage; business logic
    never touches the scheduler/tools directly at this layer.
    """

    def __init__(
        self,
        planner: Any = None,
        scheduler: Any = None,
        reporter: Any = None,
        aggregator: Any = None,
        span_sink: list[dict] | None = None,
    ):
        self._planner = planner
        self._scheduler = scheduler
        self._reporter = reporter
        self._aggregator = aggregator
        self._span_sink = span_sink if span_sink is not None else []
        self._tasks: dict[str, AgentTask] = {}

    # ─── Task lifecycle ────────────────────────────────────────────────

    async def create_task(self, user_query: str, goal: str = "") -> AgentTask:
        """Create a task from a user query (stage: create_task)."""
        task = AgentTask(
            task_id=f"task-{uuid.uuid4().hex[:10]}",
            user_query=user_query,
            goal=goal or user_query,
        )
        self._tasks[task.task_id] = task
        return task

    async def run(
        self,
        task: AgentTask,
        tools: Any = None,
        memory: Any = None,
        context: dict | None = None,
    ) -> AgentTask:
        """Execute the full agent lifecycle for a task.

        Stages (each with a real trace span):
          plan      — decompose goal into a structured TaskPlan
          schedule  — turn the plan into an executable graph and run it
          aggregate — merge node outputs into a structured result
          report    — produce the final deliverable
        """
        from datetime import datetime as _dt

        task.status = "running"
        ctx = dict(context or {})
        if tools is not None:
            ctx["tools"] = tools
        if memory is not None:
            ctx["memory"] = memory

        try:
            # Stage: plan
            async with trace_span(task.task_id, "planner", "planner",
                                  "Planner", sink=self._span_sink) as span:
                span.set_input({"goal": task.goal, "query": task.user_query})
                plan = await self._plan(task, ctx)
                task.plan = plan
                span.set_output({"plan": str(type(plan))})
            task.status = "planned"

            # Stage: schedule + execute
            async with trace_span(task.task_id, "scheduler", "scheduler",
                                  "Scheduler", sink=self._span_sink) as span:
                span.set_input({"plan": str(type(plan))})
                exec_result = await self._execute(task, plan, ctx)
                span.set_output({"graph_result": str(type(exec_result))})

            # Stage: aggregate
            async with trace_span(task.task_id, "aggregator", "aggregator",
                                  "Aggregator", sink=self._span_sink) as span:
                span.set_input({"exec_result": str(type(exec_result))})
                aggregated = await self._aggregate(task, plan, exec_result, ctx)
                span.set_output({"aggregated": bool(aggregated)})

            # Stage: report
            async with trace_span(task.task_id, "reporter", "reporter",
                                  "Reporter", sink=self._span_sink) as span:
                span.set_input({"aggregated": str(type(aggregated))})
                task.result = await self._report(task, aggregated, ctx)
                span.set_output({"result": str(type(task.result))})

            task.status = "completed"
            task.completed_at = _dt.now().isoformat()
            return task

        except Exception as e:
            task.status = "failed"
            task.error = str(e)[:300]
            task.completed_at = _dt.now().isoformat()
            raise

    # ─── Stage implementations (override in subclasses / via injection) ─

    async def _plan(self, task: AgentTask, ctx: dict) -> Any:
        if self._planner is None:
            raise RuntimeError("AgentRuntime requires a planner")
        tools = ctx.get("tools")
        if hasattr(self._planner, "plan_for_goal"):
            return await self._planner.plan_for_goal(task.goal, tools=tools)
        if hasattr(self._planner, "create_plan"):
            return await self._planner.create_plan(task.user_query)
        raise RuntimeError("Planner must expose plan_for_goal() or create_plan()")

    async def _execute(self, task: AgentTask, plan: Any, ctx: dict) -> Any:
        if self._scheduler is None:
            raise RuntimeError("AgentRuntime requires a scheduler")
        if hasattr(self._scheduler, "run"):
            return await self._scheduler.run(plan, ctx)
        if hasattr(self._scheduler, "execute_plan"):
            return await self._scheduler.execute_plan(plan)
        raise RuntimeError("Scheduler must expose run() or execute_plan()")

    async def _aggregate(self, task, plan, exec_result, ctx) -> Any:
        if self._aggregator is not None:
            return await self._aggregator(exec_result, ctx)
        return exec_result

    async def _report(self, task: AgentTask, aggregated: Any, ctx: dict) -> Any:
        if self._reporter is not None:
            return await self._reporter(task, aggregated, ctx)
        return aggregated

    # ─── Stats / observability ─────────────────────────────────────────

    def collect_stats(self, task: AgentTask) -> AgentRunStats:
        """Compute execution-quality metrics from the task's spans."""
        stats = AgentRunStats(task_id=task.task_id)
        # Aggregate from recorded spans (real data, not fabricated)
        for span in self._span_sink:
            if span.get("run_id") != task.task_id:
                continue
            kind = span.get("kind", "")
            if kind == "tool":
                stats.tool_calls += 1
                if span.get("status") == "ok":
                    stats.tool_success += 1
                else:
                    stats.tool_failed += 1
            if kind == "skill" or kind == "agent":
                stats.node_total += 1
                if span.get("status") == "ok":
                    stats.node_success += 1
                else:
                    stats.node_failed += 1
            stats.token_usage.update(span.get("token_usage") or {})
            dur = span.get("duration_ms", 0)
            if kind == "scheduler":
                stats.latency_ms += dur
        stats.task_success = task.status == "completed"
        stats.latency_ms = stats.latency_ms or 0
        return stats

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    @property
    def spans(self) -> list[dict]:
        return list(self._span_sink)
