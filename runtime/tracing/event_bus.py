# EventBus — In-process event system
#
# All runtime components emit events through the EventBus.
# Events enable observability, tracing, replay, and trajectory evaluation.

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

from runtime.models import Event

EventCallback = Callable[[Event], None]


class EventBus:
    """In-process event bus with subscribe/replay/export.

    Usage:
        bus = EventBus()

        # Subscribe to events
        bus.subscribe("ToolInvoked", my_handler)
        bus.subscribe("Tool*", all_tool_handler)   # prefix match
        bus.subscribe("*", catch_all_handler)       # all events

        # Emit an event
        bus.emit(Event(
            id="...",
            type="ToolInvoked",
            timestamp="...",
            correlation_id="...",
            payload={"tool_name": "get_stock_basic"},
        ))

        # Replay a session
        async for event in bus.replay(session_id="abc"):
            print(event)

        # Export trace
        trace = bus.export_trace(session_id="abc")
    """

    def __init__(self):
        self._subscribers: list[tuple[str, EventCallback]] = []
        self._history: list[Event] = []
        self._lock = asyncio.Lock()

    def emit(self, event: Event) -> None:
        """Emit an event to all matching subscribers.

        Subscribers are called synchronously in subscription order.
        The event is also appended to the in-memory history for replay.
        """
        self._history.append(event)
        for pattern, callback in self._subscribers:
            if self._matches(pattern, event.type):
                try:
                    callback(event)
                except Exception:
                    # Subscriber failures must not break the event loop.
                    # In production, this would log the subscriber error.
                    pass

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Subscribe to events matching a type pattern.

        Patterns:
          - "ToolInvoked"     → exact match
          - "Tool*"           → prefix match (ToolInvoked, ToolFinished, ...)
          - "*"               → match all
        """
        self._subscribers.append((event_type, callback))

    def unsubscribe(self, callback: EventCallback) -> None:
        """Remove a subscriber."""
        self._subscribers = [
            (p, c) for p, c in self._subscribers if c is not callback
        ]

    async def replay(self, session_id: str) -> AsyncIterator[Event]:
        """Replay all events from a session in order.

        Filters by correlation_id == session_id since the correlation_id
        is set to the session_id for all events in a workflow run.
        """
        for event in self._history:
            if event.correlation_id == session_id:
                yield event

    def export_trace(self, session_id: str) -> list[dict]:
        """Export full trace as a JSON-serializable list of dicts.

        Used for trajectory evaluation and debugging.
        """
        return [
            {
                "id": e.id,
                "type": e.type,
                "timestamp": e.timestamp,
                "correlation_id": e.correlation_id,
                "parent_id": e.parent_id,
                "payload": e.payload,
                "metadata": e.metadata,
            }
            for e in self._history
            if e.correlation_id == session_id
        ]

    def get_history(self) -> list[Event]:
        """Get all events (for debugging / monitoring)."""
        return list(self._history)

    def clear(self) -> None:
        """Clear all event history (for testing)."""
        self._history.clear()

    @staticmethod
    def _matches(pattern: str, event_type: str) -> bool:
        """Check if an event type matches a pattern."""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            return event_type.startswith(pattern[:-1])
        return pattern == event_type
