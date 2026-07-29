# Tracing / Event System
#
# The EventBus is the central nervous system of the runtime.
# All components emit events; consumers subscribe to what they need.
#
# Usage:
#     bus = EventBus()
#     bus.emit(Event(id=uuid, type="ToolInvoked", ...))
#     bus.subscribe("Tool*", my_handler)

from .event_bus import EventBus
from .event_types import EventType

__all__ = ["EventBus", "EventType"]
