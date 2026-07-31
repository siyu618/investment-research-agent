# Runtime Framework — Unified Agent Harness
#
# The Harness is the universal entry point for running agents.
# It owns the full lifecycle: Plan → Execute → Verify → Report.
#
# Every step is wrapped with:
#   - Lifecycle hooks (logging, metrics, audit) with proper drain
#   - Event emission (observability, tracing, replay)
#   - Error classification and recovery
#   - Timeout enforcement
#   - Context propagation

from __future__ import annotations

import asyncio
import builtins
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from runtime.errors import FatalError, RecoverableError, TimeoutError
from runtime.lifecycle import LifecycleHook
from runtime.models import (
    AgentResult,
    Event,
    EventType,
    ExecutionContext,
    RuntimeConfig,
)
from runtime.tracing import EventBus

logger = logging.getLogger("agent.harness")


class Harness:
    """Unified agent runtime.

    Usage:
        harness = Harness(config=RuntimeConfig(trace_enabled=True))
        result = await harness.run(
            planner=my_planner,
            executor=my_executor,
            verifier=my_verifier,
            reporter=my_reporter,
            requirement="Analyze ...",
        )
    """

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        event_bus: EventBus | None = None,
    ):
        self.config = config or RuntimeConfig()
        self.event_bus = event_bus or EventBus()
        self.hooks: list[LifecycleHook] = []
        self._correlation_id = ""
        self._pending_hook_tasks: list[asyncio.Task] = []
        self.hook_error_count: int = 0

    def add_hook(self, hook: LifecycleHook) -> None:
        """Register a lifecycle hook."""
        self.hooks.append(hook)

    async def run(
        self,
        planner: Any,
        executor: Any,
        verifier: Any,
        reporter: Any,
        requirement: str,
        **kwargs,
    ) -> AgentResult:
        """Run the full agent lifecycle."""
        start_time = datetime.now()
        session_id = f"session-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            session_id=session_id,
            correlation_id=session_id,
            user_requirement=requirement,
            config=self.config,
        )
        self._correlation_id = session_id

        try:
            await self._fire_on_start(context)

            # Step 1: Plan
            self._emit(EventType.PLANNING_STARTED, {"requirement": requirement})
            plan = await self._run_step(
                "plan",
                lambda: planner.create_plan(requirement, **kwargs),
                context,
            )
            self._emit(EventType.PLANNING_COMPLETED, {"plan": str(type(plan))})

            # Step 2: Execute
            self._emit(EventType.WORKFLOW_STARTED, {
                "workflow": getattr(plan, "workflow_name", "default"),
            })
            exec_result = await self._run_step(
                "execute",
                lambda: executor.execute_plan(plan),
                context,
            )

            # Step 3: Verify
            self._emit(EventType.VERIFICATION_STARTED, {})
            verification = await self._run_step(
                "verify",
                lambda: verifier.verify(plan, exec_result),
                context,
            )
            self._emit(EventType.VERIFICATION_COMPLETED, {
                "passed": verification.passed,
            })

            # Step 4: Report
            report = await self._run_step(
                "report",
                lambda: reporter.generate(plan, exec_result, verification),
                context,
            )
            self._emit(EventType.REPORT_GENERATED, {
                "report_id": getattr(report, "report_id", "unknown"),
            })

            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            self._emit(EventType.WORKFLOW_FINISHED, {
                "status": "success",
                "total_duration_ms": duration,
            })

            result = AgentResult(
                session_id=session_id,
                success=True,
                output=report,
                total_duration_ms=duration,
                event_count=len(self.event_bus.get_history()),
            )

            await self._drain_hooks()
            await self._fire_on_finish(context, result, None)
            return result

        except FatalError as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            self._emit(EventType.WORKFLOW_FINISHED, {
                "status": "failed",
                "error": str(e),
                "total_duration_ms": duration,
            })
            result = AgentResult(
                session_id=session_id,
                success=False,
                total_duration_ms=duration,
                error=str(e),
            )
            await self._drain_hooks()
            await self._fire_on_finish(context, result, e)
            return result

    async def _run_step(
        self, step_name: str, step_fn: Callable, context: ExecutionContext,
    ) -> Any:
        """Execute a step with retry/timeout/error handling.

        NOTE: Harness retries ONLY the top-level step.
        Sub-steps (within Scheduler) have their own retry policies.
        This prevents double-retry amplification.
        """
        last_error: Exception | None = None
        for attempt in range(1 + self.config.max_retries):
            try:
                return await asyncio.wait_for(
                    step_fn(),
                    timeout=self.config.default_timeout,
                )
            except builtins.TimeoutError:
                last_error = TimeoutError(
                    f"Step '{step_name}' timed out after {self.config.default_timeout}s",
                )
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "step": step_name, "error": str(last_error), "attempt": attempt,
                    "will_retry": attempt < self.config.max_retries,
                })
                if attempt < self.config.max_retries:
                    await self._fire_on_error(context, last_error, step_name)
                    continue
                raise last_error from None
            except RecoverableError as e:
                last_error = e
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "step": step_name, "error": str(e), "attempt": attempt,
                    "will_retry": attempt < self.config.max_retries,
                })
                if attempt < self.config.max_retries:
                    await self._fire_on_error(context, e, step_name)
                    delay = e.retry_after or 1.0
                    await asyncio.sleep(delay)
                    continue
                raise FatalError(
                    f"Step '{step_name}' failed after {self.config.max_retries} retries"
                ) from e
            except FatalError:
                raise
            except Exception as e:
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "step": step_name, "error": str(e), "attempt": attempt,
                    "will_retry": False,
                })
                await self._fire_on_error(context, e, step_name)
                raise FatalError(
                    f"Step '{step_name}' failed with unexpected error: {e}"
                ) from e
        raise FatalError(f"Step '{step_name}' failed after all retries")

    # ─── Hook Management ────────────────────────────────────────────────

    def _fire_hook_event(self, event: Event) -> None:
        """Fire hook.on_event without blocking the main flow.

        Hook exceptions are logged but do not interrupt the agent.
        Failed tasks are tracked and drained before finish.
        """
        for hook in self.hooks:
            try:
                task = asyncio.ensure_future(hook.on_event(event))
                self._pending_hook_tasks.append(task)
            except Exception:
                self.hook_error_count += 1
                logger.exception("Failed to schedule hook.on_event")

    async def _drain_hooks(self) -> None:
        """Wait for all pending hook tasks and log any exceptions."""
        tasks = self._pending_hook_tasks[:]
        self._pending_hook_tasks.clear()
        if not tasks:
            return
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                self.hook_error_count += 1
                logger.error("Hook task failed: %s", r)

    async def _fire_on_start(self, context: ExecutionContext) -> None:
        for hook in self.hooks:
            try:
                await hook.on_start(context)
            except Exception:
                self.hook_error_count += 1
                logger.exception("Hook on_start failed")

    async def _fire_on_error(self, context, error, step) -> None:
        for hook in self.hooks:
            try:
                await hook.on_error(context, error, step)
            except Exception:
                self.hook_error_count += 1
                logger.exception("Hook on_error failed")

    async def _fire_on_finish(self, context, result, error) -> None:
        for hook in self.hooks:
            try:
                await hook.on_finish(context, result, error)
            except Exception:
                self.hook_error_count += 1
                logger.exception("Hook on_finish failed")

    def _emit(self, event_type: str, payload: dict) -> None:
        """Emit an event through the EventBus."""
        event = Event(
            id=f"{self._correlation_id}-{uuid.uuid4().hex[:8]}",
            type=event_type,
            timestamp=datetime.now().isoformat(),
            correlation_id=self._correlation_id,
            payload=payload,
        )
        self.event_bus.emit(event)
        self._fire_hook_event(event)
