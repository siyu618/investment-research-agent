# Runtime Framework — Unified Agent Harness
#
# The Harness is the universal entry point for running agents.
# It owns the full lifecycle: Plan → Execute → Verify → Report.
#
# Every step is wrapped with:
#   - Lifecycle hooks (logging, metrics, audit)
#   - Event emission (observability, tracing, replay)
#   - Error classification and recovery
#   - Timeout enforcement
#   - Context propagation

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from runtime.models import (
    AgentResult,
    Event,
    EventType,
    ExecutionContext,
    RuntimeConfig,
)
from runtime.errors import AgentError, RecoverableError, FatalError, TimeoutError
from runtime.lifecycle import LifecycleHook
from runtime.tracing import EventBus


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

    The Harness is domain-agnostic. The planner/executor/verifier/reporter
    are injected — swap them for a different domain.
    """

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.config = config or RuntimeConfig()
        self.event_bus = event_bus or EventBus()
        self.hooks: list[LifecycleHook] = []
        self._correlation_id = ""

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
        """Run the full agent lifecycle.

        Lifecycle:
        1. on_start (hooks)
        2. Plan   → planner (with retry/timeout)
        3. Execute → executor (delegates to Scheduler)
        4. Verify  → verifier (multi-phase checks)
        5. Report  → reporter (format output)
        6. on_finish (hooks)
        """
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
            # Hook: on_start
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

            # Done
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
            await self._fire_on_finish(context, result, e)
            return result

    async def _run_step(
        self,
        step_name: str,
        step_fn: Callable,
        context: ExecutionContext,
    ) -> Any:
        """Execute a single step with retry/timeout/error handling."""
        last_error = None
        for attempt in range(1 + self.config.max_retries):
            try:
                return await asyncio.wait_for(
                    step_fn(),
                    timeout=self.config.default_timeout,
                )
            except asyncio.TimeoutError:
                last_error = TimeoutError(
                    f"Step '{step_name}' timed out after {self.config.default_timeout}s",
                    context={"attempt": attempt},
                )
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "step": step_name,
                    "error": str(last_error),
                    "attempt": attempt,
                    "will_retry": attempt < self.config.max_retries,
                })
                # Timeout can be retried once
                if attempt < self.config.max_retries:
                    await self._fire_on_error(context, last_error, step_name)
                    continue
                raise last_error

            except RecoverableError as e:
                last_error = e
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "step": step_name,
                    "error": str(e),
                    "attempt": attempt,
                    "will_retry": attempt < self.config.max_retries,
                })
                if attempt < self.config.max_retries:
                    await self._fire_on_error(context, e, step_name)
                    delay = e.retry_after or (self.config.default_timeout * 0.5)
                    await asyncio.sleep(delay)
                    continue
                raise FatalError(
                    f"Step '{step_name}' failed after {self.config.max_retries} retries",
                    context={"last_error": str(e)},
                )

            except FatalError:
                raise

            except Exception as e:
                last_error = e
                self._emit(EventType.ERROR_ENCOUNTERED, {
                    "step": step_name,
                    "error": str(e),
                    "attempt": attempt,
                    "will_retry": False,
                })
                await self._fire_on_error(context, e, step_name)
                raise FatalError(
                    f"Step '{step_name}' failed with unexpected error",
                    context={"error": str(e)},
                )

        # Should not reach here, but safety net
        raise FatalError(
            f"Step '{step_name}' failed after all retries",
            context={"last_error": str(last_error)},
        )

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

        # Also notify lifecycle hooks
        for hook in self.hooks:
            try:
                asyncio.ensure_future(hook.on_event(event))
            except Exception:
                pass

    async def _fire_on_start(self, context: ExecutionContext) -> None:
        for hook in self.hooks:
            try:
                await hook.on_start(context)
            except Exception:
                pass

    async def _fire_on_error(
        self, context: ExecutionContext, error: Exception, step: str
    ) -> None:
        for hook in self.hooks:
            try:
                await hook.on_error(context, error, step)
            except Exception:
                pass

    async def _fire_on_finish(
        self, context: ExecutionContext, result: Any, error: Optional[Exception]
    ) -> None:
        for hook in self.hooks:
            try:
                await hook.on_finish(context, result, error)
            except Exception:
                pass
