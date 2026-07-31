# Runtime Framework — Core Data Models
#
# These models are the shared language across all runtime components.
# They are domain-agnostic — no investment-specific fields.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ─── Event System ───────────────────────────────────────────────────────


class EventType(str, Enum):
    """All event types emitted by the runtime.

    Organized by source component for discoverability.
    """

    # Harness lifecycle
    PLANNING_STARTED = "PlanningStarted"
    PLANNING_COMPLETED = "PlanningCompleted"
    WORKFLOW_STARTED = "WorkflowStarted"
    WORKFLOW_FINISHED = "WorkflowFinished"
    ERROR_ENCOUNTERED = "ErrorEncountered"

    # Scheduler / Graph
    GRAPH_RESOLVED = "GraphResolved"
    NODE_STARTED = "NodeStarted"
    NODE_COMPLETED = "NodeCompleted"
    NODE_FAILED = "NodeFailed"
    NODE_RETRIED = "NodeRetried"

    # Tool invocations
    TOOL_INVOKED = "ToolInvoked"
    TOOL_FINISHED = "ToolFinished"
    TOOL_FAILED = "ToolFailed"
    TOOL_CACHE_HIT = "ToolCacheHit"
    TOOL_CACHE_MISS = "ToolCacheMiss"

    # Skill lifecycle
    SKILL_STARTED = "SkillStarted"
    SKILL_COMPLETED = "SkillCompleted"
    SKILL_VERIFYING = "SkillVerifying"
    SKILL_VERIFICATION_DONE = "SkillVerificationDone"

    # Memory
    MEMORY_READ = "MemoryRead"
    MEMORY_WRITTEN = "MemoryWritten"
    MEMORY_CACHE_HIT = "MemoryCacheHit"
    MEMORY_CACHE_MISS = "MemoryCacheMiss"

    # Verification
    VERIFICATION_STARTED = "VerificationStarted"
    VERIFICATION_CHECK = "VerificationCheck"
    VERIFICATION_COMPLETED = "VerificationCompleted"

    # Report
    REPORT_GENERATED = "ReportGenerated"

    # User interaction
    USER_FEEDBACK_REQUESTED = "UserFeedbackRequested"
    USER_FEEDBACK_RECEIVED = "UserFeedbackReceived"


@dataclass
class Event:
    """Every state change in the system is an Event.

    Events are immutable facts. They are the foundation of observability,
    tracing, replay, and trajectory evaluation.
    """

    id: str
    type: str
    timestamp: str
    correlation_id: str
    payload: dict = field(default_factory=dict)
    parent_id: str | None = None
    metadata: dict = field(default_factory=dict)


# ─── Execution Context ─────────────────────────────────────────────────


@dataclass
class RuntimeConfig:
    """Configuration for a single agent run."""
    max_retries: int = 3
    default_timeout: int = 60  # seconds
    max_parallel: int = 10
    cache_enabled: bool = True
    trace_enabled: bool = False
    verbose: bool = False


@dataclass
class ExecutionContext:
    """Pervasive context flowing through every runtime operation.

    Every component receives this context. It enables correlation,
    configuration, and cross-cutting concern propagation.
    """

    session_id: str
    correlation_id: str
    user_requirement: str
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    config: RuntimeConfig = field(default_factory=RuntimeConfig)
    tags: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# ─── Task Graph Models ─────────────────────────────────────────────────


@dataclass
class TaskConfig:
    """Per-task execution configuration."""
    timeout: int = 60
    max_retries: int = 2
    retry_delay: float = 1.0  # seconds
    retry_backoff: float = 2.0
    resources: dict = field(default_factory=dict)


@dataclass
class TaskNode:
    """A single node in the execution graph."""
    id: str
    label: str
    skill: str
    config: TaskConfig = field(default_factory=TaskConfig)
    input_mapping: dict = field(default_factory=dict)
    output_mapping: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class Edge:
    """A dependency edge between two nodes."""
    source_id: str
    target_id: str
    condition: str = "success"  # success | failure | always


@dataclass
class TaskGraph:
    """A directed acyclic graph of executable tasks.

    Nodes represent executable units (skills).
    Edges represent dependencies.
    The Scheduler executes the graph with automatic parallelism.
    """
    nodes: dict[str, TaskNode]
    edges: list[Edge]
    entry_points: list[str] = field(default_factory=list)
    output_nodes: list[str] = field(default_factory=list)


# ─── Workflow Models ───────────────────────────────────────────────────


@dataclass
class WorkflowDefinition:
    """A named, versioned workload definition.

    Wraps a TaskGraph with metadata for discovery and management.
    """
    name: str
    version: str
    description: str
    graph: TaskGraph
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class NodeResult:
    """Result from executing a single TaskNode."""
    node_id: str
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: int = 0
    retry_count: int = 0


@dataclass
class GraphResult:
    """Result from executing the full TaskGraph."""
    session_id: str
    success: bool
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    total_duration_ms: int = 0
    error: str | None = None


# ─── Agent Result ──────────────────────────────────────────────────────


@dataclass
class AgentResult:
    """Final output from a full Harness run."""
    session_id: str
    success: bool
    output: Any = None
    graph_result: GraphResult | None = None
    total_duration_ms: int = 0
    event_count: int = 0
    error: str | None = None
