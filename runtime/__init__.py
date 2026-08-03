# Tushare Investment Research Agent — Runtime Framework
#
# Domain-agnostic agent runtime with lifecycle management,
# event-driven observability, DAG-based workflows, and error handling.
#
# This package is the "Framework Core" — it owns cross-cutting concerns
# and knows nothing about the investment domain.

from .agent_runtime import AgentRunStats, AgentRuntime, AgentTask
from .cache import CachePolicy, CacheProvider, TTLCache
from .errors import AgentError, FatalError, RecoverableError, SkillError, TimeoutError, ToolError
from .graph import (
    ExecutionLayer,
    GraphState,
    GraphValidationError,
    build_graph,
    compute_layers,
    validate_graph,
)
from .harness import Harness
from .lifecycle import LifecycleHook, LoggingHook
from .models import (
    AgentResult,
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
    WorkflowDefinition,
)
from .run_recorder import RunRecorder
from .scheduler import Scheduler
from .snapshot import DataSnapshot, hash_of
from .workflow import (
    WorkflowLoadError,
    WorkflowRegistry,
    load_workflow_from_dict,
    load_workflow_from_yaml,
)

__all__ = [
    # Unified AgentRuntime
    "AgentRuntime", "AgentTask", "AgentRunStats",
    # Core models
    "Event", "EventType", "ExecutionContext", "RuntimeConfig",
    "AgentResult", "GraphResult", "NodeResult",
    # Graph
    "TaskGraph", "TaskNode", "TaskConfig", "Edge",
    "ExecutionLayer", "GraphState",
    "GraphValidationError", "build_graph", "compute_layers", "validate_graph",
    # Scheduler
    "Scheduler",
    # Harness
    "Harness", "LifecycleHook", "LoggingHook",
    # Errors
    "AgentError", "RecoverableError", "FatalError", "TimeoutError",
    "SkillError", "ToolError",
    # Cache
    "CacheProvider", "CachePolicy", "TTLCache",
    # Snapshot / Run
    "DataSnapshot", "hash_of", "RunRecorder",
    # Workflow
    "WorkflowDefinition", "WorkflowRegistry",
    "WorkflowLoadError", "load_workflow_from_dict", "load_workflow_from_yaml",
]
