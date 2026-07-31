# Runtime Framework — Lifecycle Hooks
#
# Lifecycle hooks are the extension point for cross-cutting concerns.
# Add logging, metrics, auditing, or debugging without modifying business code.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from runtime.models import Event, ExecutionContext


class LifecycleHook(ABC):
    """Base class for lifecycle hooks.

    Hooks are called by the Harness at various points in the agent lifecycle.
    Multiple hooks can be registered; they are called in registration order.

    Built-in hooks:
        - LoggingHook: Logs each event to console
        - MetricsHook: Tracks latency counters
        - AuditHook: Records every tool call for audit
        - DebugHook: Captures full traces for debugging
    """

    @abstractmethod
    async def on_start(self, context: ExecutionContext) -> None:
        """Called when the Harness begins a run."""
        ...

    @abstractmethod
    async def on_event(self, event: Event) -> None:
        """Called for every event emitted during the run."""
        ...

    @abstractmethod
    async def on_error(
        self, context: ExecutionContext, error: Exception, step: str
    ) -> None:
        """Called when an error occurs."""
        ...

    @abstractmethod
    async def on_finish(
        self, context: ExecutionContext, result: Any, error: Exception | None
    ) -> None:
        """Called when the Harness completes a run."""
        ...


class LoggingHook(LifecycleHook):
    """Logs lifecycle events to stdout/stderr.

    In verbose mode, prints every event.
    In normal mode, prints major lifecycle events only.
    """

    MAJOR_EVENTS = {
        "WorkflowStarted",
        "WorkflowFinished",
        "NodeFailed",
        "ToolFailed",
        "VerificationCompleted",
        "ReportGenerated",
        "ErrorEncountered",
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    async def on_start(self, context: ExecutionContext) -> None:
        print(f"[START] Session: {context.session_id}")
        print(f"  Requirement: {context.user_requirement[:80]}...")

    async def on_event(self, event: Event) -> None:
        if self.verbose or event.type in self.MAJOR_EVENTS:
            print(f"  [{event.type}] {event.payload}")

    async def on_error(
        self, context: ExecutionContext, error: Exception, step: str
    ) -> None:
        print(f"[ERROR] Step={step}: {error}")

    async def on_finish(
        self, context: ExecutionContext, result: Any, error: Exception | None
    ) -> None:
        status = "FAILED" if error else "SUCCESS"
        print(f"[FINISH] {status} — Session: {context.session_id}")
