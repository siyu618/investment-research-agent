# Event Type Definitions
#
# Central catalog of all events emitted by the runtime.
# Import EventType from runtime.models for the enum.
# This file documents usage patterns for each event type.

"""
Event type documentation:

Harness Lifecycle
-----------------
PlanningStarted:
    Payload: {"requirement": str}
    When: Planner begins requirement decomposition.

PlanningCompleted:
    Payload: {"plan": dict}
    When: Planner returns a structured plan.

WorkflowStarted:
    Payload: {"workflow": str, "graph_node_count": int}
    When: Harness begins workflow execution.

WorkflowFinished:
    Payload: {"status": str, "total_duration_ms": int}
    When: All workflow steps complete.

ErrorEncountered:
    Payload: {"error_type": str, "message": str, "step": str}
    When: Non-fatal error occurs during execution.

Scheduler / Graph
-----------------
GraphResolved:
    Payload: {"node_count": int, "edge_count": int, "layers": int}
    When: TaskGraph is validated and topologically sorted.

NodeStarted:
    Payload: {"node_id": str, "skill": str, "retry_count": int}
    When: A TaskNode begins execution.

NodeCompleted:
    Payload: {"node_id": str, "duration_ms": int}
    When: A TaskNode completes successfully.

NodeFailed:
    Payload: {"node_id": str, "error": str, "retry_count": int, "will_retry": bool}
    When: A TaskNode fails.

NodeRetried:
    Payload: {"node_id": str, "attempt": int, "max_retries": int}
    When: A failed TaskNode is retried.

Tool Invocations
----------------
ToolInvoked:
    Payload: {"tool_name": str, "input": dict}
    When: A tool is called via ToolRegistry.

ToolFinished:
    Payload: {"tool_name": str, "duration_ms": int}
    When: A tool returns successfully (output excluded for size).

ToolFailed:
    Payload: {"tool_name": str, "error": str, "recoverable": bool}
    When: A tool raises an error.

ToolCacheHit:
    Payload: {"tool_name": str, "args_key": str, "saved_ms": int}
    When: ToolRegistry returns cached result.

ToolCacheMiss:
    Payload: {"tool_name": str, "args_key": str}
    When: ToolRegistry has no cached result for this call.

Skill Lifecycle
---------------
SkillStarted:
    Payload: {"skill_name": str, "version": str}
    When: A skill begins its execute() phase.

SkillCompleted:
    Payload: {"skill_name": str, "duration_ms": int}
    When: A skill completes its execute() phase.

SkillVerifying:
    Payload: {"skill_name": str, "check": str}
    When: A skill begins a self-verification check.

SkillVerificationDone:
    Payload: {"skill_name": str, "passed": bool}
    When: A skill completes self-verification.

Memory
------
MemoryRead:
    Payload: {"tier": str, "key": str, "hit": bool}
    When: Any memory tier is read.

MemoryWritten:
    Payload: {"tier": str, "key": str, "size_bytes": int}
    When: Any memory tier is written.

MemoryCacheHit:
    Payload: {"tier": str, "key": str}
    When: Cache tier returns cached data.

MemoryCacheMiss:
    Payload: {"tier": str, "key": str}
    When: Cache tier has no cached data.

Verification
------------
VerificationStarted:
    Payload: {"phase_count": int}
    When: Verifier begins its multi-phase check.

VerificationCheck:
    Payload: {"phase": str, "passed": bool, "detail": str}
    When: A single verification check completes.

VerificationCompleted:
    Payload: {"passed": bool, "warning_count": int, "error_count": int}
    When: All verification checks complete.

Report
------
ReportGenerated:
    Payload: {"report_id": str, "format": str}
    When: ReportGenerator produces final output.

User Interaction
----------------
UserFeedbackRequested:
    Payload: {"question": str, "options": list}
    When: Agent requires user input.

UserFeedbackReceived:
    Payload: {"response": str}
    When: User provides input.
"""
