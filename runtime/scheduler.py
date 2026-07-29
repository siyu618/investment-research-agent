# Runtime Framework — DAG Scheduler
#
# The Scheduler executes a TaskGraph by:
# 1. Validating and topologically sorting the graph
# 2. Executing layers sequentially (within-layer = parallel)
# 3. Managing shared GraphState across layers
# 4. Emitting events for every state change
# 5. Handling per-node retries, timeouts, and error propagation
#
# Usage:
#     scheduler = Scheduler(event_bus=bus, skill_registry=registry)
#     result = await scheduler.run(graph, context, initial_state={...})

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from runtime.errors import (
    AgentError,
    FatalError,
    RecoverableError,
    SkillError,
    TimeoutError,
)
from runtime.graph import (
    GraphState,
    ExecutionLayer,
    compute_layers,
    validate_graph,
)
from runtime.models import (
    Edge,
    Event,
    EventType,
    ExecutionContext,
    GraphResult,
    NodeResult,
    RuntimeConfig,
    TaskConfig,
    TaskGraph,
    TaskNode,
)


class Scheduler:
    """Executes a TaskGraph with automatic parallelism.

    The Scheduler is the core execution engine. It:
    - Topologically sorts nodes into parallel layers
    - Executes each layer concurrently
    - Manages shared state across nodes
    - Handles retries, timeouts, and error propagation
    - Emits typed events for observability
    """

    def __init__(
        self,
        skill_registry: Any = None,
        event_bus: Any = None,
        config: Optional[RuntimeConfig] = None,
    ):
        self.skill_registry = skill_registry
        self.event_bus = event_bus
        self.config = config or RuntimeConfig()
        self._cancelled = False
        self._results: dict[str, NodeResult] = {}

    async def run(
        self,
        graph: TaskGraph,
        context: ExecutionContext,
        initial_state: Optional[dict] = None,
        skill_executor: Optional[Callable] = None,
    ) -> GraphResult:
        """Execute the full TaskGraph.

        Args:
            graph: The validated TaskGraph to execute.
            context: Execution context for this run.
            initial_state: Optional initial data for graph state.
            skill_executor: Async callable(node, state, context) -> Any.
                If None, uses the default executor (looks up skill registry).

        Returns:
            GraphResult with per-node results and aggregate metrics.
        """
        start_time = time.monotonic()
        self._cancelled = False
        self._results = {}
        state = GraphState(initial_state)

        # Phase 1: Validate
        validate_graph(graph)
        layers = compute_layers(graph)

        # Emit GraphResolved
        self._emit(EventType.GRAPH_RESOLVED, {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "layer_count": len(layers),
            "entry_points": graph.entry_points,
            "output_nodes": graph.output_nodes,
        })

        # Phase 2: Execute layers sequentially
        try:
            for layer in layers:
                if self._cancelled:
                    break
                await self._execute_layer(
                    layer, graph, context, state, skill_executor
                )

        except FatalError as e:
            # Propagate to all still-running nodes? Already handled by _execute_layer.
            pass
        except asyncio.CancelledError:
            self._cancelled = True

        # Phase 3: Build result
        total_ms = int((time.monotonic() - start_time) * 1000)
        output_nodes_completed = all(
            nid in self._results and self._results[nid].success
            for nid in graph.output_nodes
        )

        return GraphResult(
            session_id=context.session_id,
            success=output_nodes_completed and not self._cancelled,
            node_results=self._results,
            total_duration_ms=total_ms,
            error=None if output_nodes_completed else "graph execution incomplete",
        )

    def cancel(self) -> None:
        """Request cancellation of the current execution.

        The scheduler will stop processing after the current layer completes.
        """
        self._cancelled = True

    # ─── Layer Execution ─────────────────────────────────────────────────

    async def _execute_layer(
        self,
        layer: ExecutionLayer,
        graph: TaskGraph,
        context: ExecutionContext,
        state: GraphState,
        skill_executor: Optional[Callable],
    ) -> None:
        """Execute all nodes in a layer concurrently."""
        tasks = []
        semaphore = asyncio.Semaphore(self.config.max_parallel)

        async def run_node(node_id: str) -> None:
            async with semaphore:
                if self._cancelled:
                    return
                await self._execute_node(
                    node_id, graph, context, state, skill_executor
                )

        for node_id in layer.node_ids:
            tasks.append(asyncio.create_task(run_node(node_id)))

        # Wait for all nodes in this layer (gather with return_exceptions)
        # so one failure doesn't cancel the entire layer.
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for unexpected errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                node_id = layer.node_ids[i]
                self._results[node_id] = NodeResult(
                    node_id=node_id,
                    success=False,
                    error=f"Unhandled exception: {result}",
                )

    async def _execute_node(
        self,
        node_id: str,
        graph: TaskGraph,
        context: ExecutionContext,
        state: GraphState,
        skill_executor: Optional[Callable],
    ) -> None:
        """Execute a single node with retry/timeout/error handling."""
        node = graph.nodes[node_id]
        start_time = time.monotonic()

        self._emit(EventType.NODE_STARTED, {
            "node_id": node_id,
            "skill": node.skill,
            "label": node.label,
            "layer_deps": self._get_dependency_ids(graph, node_id),
        })

        last_error: Optional[str] = None
        success = False
        output = None
        retry_count = 0

        for attempt in range(1 + node.config.max_retries):
            if attempt > 0:
                retry_count = attempt
                self._emit(EventType.NODE_RETRIED, {
                    "node_id": node_id,
                    "attempt": attempt,
                    "max_retries": node.config.max_retries,
                })

            try:
                # Build input from graph state
                input_data = self._build_node_input(node, state)

                # Execute with timeout
                output = await asyncio.wait_for(
                    self._invoke_skill(
                        node, input_data, context, skill_executor
                    ),
                    timeout=node.config.timeout,
                )

                # Apply output mapping to graph state
                self._apply_node_output(node, output, state)

                success = True
                break

            except asyncio.TimeoutError:
                last_error = f"Timeout after {node.config.timeout}s"
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "node_id": node_id,
                    "error": last_error,
                    "attempt": attempt,
                    "will_retry": attempt < node.config.max_retries,
                })
                if attempt < node.config.max_retries:
                    delay = node.config.retry_delay * (node.config.retry_backoff ** attempt)
                    await asyncio.sleep(delay)
                    continue
                break

            except RecoverableError as e:
                last_error = str(e)
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "node_id": node_id,
                    "error": last_error,
                    "attempt": attempt,
                    "will_retry": attempt < node.config.max_retries,
                    "recoverable": True,
                })
                if attempt < node.config.max_retries:
                    delay = node.config.retry_delay * (node.config.retry_backoff ** attempt)
                    await asyncio.sleep(delay)
                    continue
                break

            except FatalError as e:
                last_error = str(e)
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "node_id": node_id,
                    "error": last_error,
                    "attempt": attempt,
                    "will_retry": False,
                    "fatal": True,
                })
                break

            except Exception as e:
                last_error = f"Unexpected error: {e}"
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "node_id": node_id,
                    "error": last_error,
                    "attempt": attempt,
                    "will_retry": attempt < node.config.max_retries,
                })
                if attempt < node.config.max_retries:
                    await asyncio.sleep(node.config.retry_delay)
                    continue
                break

        duration_ms = int((time.monotonic() - start_time) * 1000)

        self._results[node_id] = NodeResult(
            node_id=node_id,
            success=success,
            output=output,
            error=last_error,
            duration_ms=duration_ms,
            retry_count=retry_count,
        )

        if success:
            self._emit(EventType.NODE_COMPLETED, {
                "node_id": node_id,
                "skill": node.skill,
                "duration_ms": duration_ms,
                "retry_count": retry_count,
            })
        else:
            self._emit(EventType.NODE_FAILED, {
                "node_id": node_id,
                "skill": node.skill,
                "error": last_error,
                "duration_ms": duration_ms,
                "retry_count": retry_count,
                "will_retry": False,  # all retries exhausted
            })

    # ─── Skill Invocation ────────────────────────────────────────────────

    async def _invoke_skill(
        self,
        node: TaskNode,
        input_data: dict,
        context: ExecutionContext,
        skill_executor: Optional[Callable],
    ) -> Any:
        """Invoke the skill for this node using the SkillLifecycle.

        Resolution order:
        1. Explicit skill_executor callable
        2. Skill registry lookup → load via SkillLifecycle
        3. Fallback: treat node.skill as module path

        Lifecycle called: plan() → execute() → verify()
        """
        if skill_executor is not None:
            return await skill_executor(node, input_data, context)

        skill = await self._load_skill_instance(node.skill)
        if skill is None:
            raise FatalError(
                f"Cannot execute node '{node.id}': "
                f"no skill_executor provided and skill '{node.skill}' "
                f"could not be loaded"
            )

        from skills.base.skill_sdk import SkillLifecycle, ensure_skill_lifecycle
        skill_lifecycle = ensure_skill_lifecycle(skill)

        # Emit lifecycle events
        self._emit(EventType.SKILL_STARTED, {
            "skill_name": node.skill,
            "node_id": node.id,
        })

        # Phase 1: Plan
        plan = await skill_lifecycle.plan(input_data)

        # Phase 2: Execute
        output = await skill_lifecycle.execute(input_data, plan)

        # Phase 3: Verify
        if await self._config_should_verify():
            verdict = await skill_lifecycle.verify(input_data, output)
            self._emit(EventType.SKILL_VERIFYING, {
                "skill_name": node.skill,
                "passed": verdict.passed,
                "checks": len(verdict.checks),
            })

        self._emit(EventType.SKILL_COMPLETED, {
            "skill_name": node.skill,
            "node_id": node.id,
        })

        return output

    async def _load_skill_instance(self, skill_name: str) -> Any:
        """Load a skill instance from the registry or module path.

        Returns the skill instance, or None if unresolvable.
        """
        if self.skill_registry is None:
            return None

        skill_meta = self.skill_registry.get_skill(skill_name)
        if skill_meta is None:
            return None

        # Check for explicit module path
        module_path = skill_meta.get("module", "")
        if module_path:
            # Check for class reference (last part = class name)
            parts = module_path.split(".")
            try:
                # Try as a module path ending with class name
                import importlib
                if len(parts) > 1 and parts[-1][0].isupper():
                    module_name = ".".join(parts[:-1])
                    class_name = parts[-1]
                    module = importlib.import_module(module_name)
                    cls = getattr(module, class_name)
                    return cls()
                else:
                    # Module path points to a module; look for a default skill
                    module = importlib.import_module(module_path)
                    # Try common naming conventions
                    for candidate in (skill_name.replace("-", "_"), "Skill", "DefaultSkill"):
                        if hasattr(module, candidate):
                            return getattr(module, candidate)()
            except (ImportError, AttributeError, TypeError) as e:
                raise FatalError(
                    f"Cannot load skill '{skill_name}' from module "
                    f"'{module_path}': {e}"
                )

        return None

    async def _config_should_verify(self) -> bool:
        """Check if skill self-verification is enabled.

        Controlled by config; can be overridden per-skill in the future.
        """
        return True

    # ─── Input/Output Mapping ────────────────────────────────────────────

    @staticmethod
    def _build_node_input(node: TaskNode, state: GraphState) -> dict:
        """Build input for a node from graph state.

        If input_mapping is specified, applies the mapping.
        Otherwise passes the full state snapshot.
        """
        if node.input_mapping:
            return {
                target_key: state.get(source_key)
                for target_key, source_key in node.input_mapping.items()
            }
        return state.snapshot()

    @staticmethod
    def _apply_node_output(node: TaskNode, output: Any, state: GraphState) -> None:
        """Apply node output to graph state.

        If output_mapping is specified, maps output keys to state keys.
        Otherwise stores under node.skill name.
        """
        if node.output_mapping:
            if not isinstance(output, dict):
                # If output is not a dict but mapping is specified, wrap it
                output = {"result": output}
            for state_key, output_key in node.output_mapping.items():
                state.set(state_key, output.get(output_key))
        elif isinstance(output, dict):
            state.update(output)
        else:
            state.set(node.skill, output)

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_dependency_ids(graph: TaskGraph, node_id: str) -> list[str]:
        """Get IDs of nodes that this node depends on."""
        return [
            edge.source_id
            for edge in graph.edges
            if edge.target_id == node_id
        ]

    def _emit(self, event_type: str, payload: dict) -> None:
        """Emit an event if event_bus is configured."""
        if self.event_bus is None:
            return
        event = Event(
            id=f"sched-{uuid.uuid4().hex[:8]}",
            type=event_type,
            timestamp=datetime.now().isoformat(),
            correlation_id="",
            payload=payload,
        )
        self.event_bus.emit(event)

    def get_result(self, node_id: str) -> Optional[NodeResult]:
        """Get the result for a specific node."""
        return self._results.get(node_id)

    @property
    def completed_node_ids(self) -> list[str]:
        """Get IDs of all completed nodes (success or failure)."""
        return list(self._results.keys())

    @property
    def successful_node_ids(self) -> list[str]:
        """Get IDs of successfully completed nodes."""
        return [
            nid for nid, r in self._results.items() if r.success
        ]

    @property
    def failed_node_ids(self) -> list[str]:
        """Get IDs of failed nodes."""
        return [
            nid for nid, r in self._results.items() if not r.success
        ]
