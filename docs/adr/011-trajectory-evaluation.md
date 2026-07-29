# Architecture Decision Record: Trajectory Evaluation

**Status:** Proposed
**Decision:** #011
**Date:** 2026-07-29

## Context

The current evaluation system has two tracks:

1. **Strategy Performance** (`evaluations/strategy-score/`): Scores investment strategy outputs (is the fundamental score correct?).
2. **Agent Quality** (`evaluations/agent-quality/`): Scores final report quality (is the report complete and explainable?).

Both tracks are **output-only** — they evaluate the *final artifact* (score, report) but not the *process* that produced it. This creates a blind spot:

- An agent could produce a good report through a terrible process (wasted tool calls, circular reasoning, ignoring errors).
- An agent could produce a poor report despite an excellent process (bad data, unlucky edge case).
- Without process evaluation, we cannot distinguish between "good agent, bad outcome" and "bad agent, good outcome."

Modern agent evaluation research (AgentBench, GAIA, WebArena) emphasizes trajectory evaluation — scoring the *execution path* not just the *final answer*. The engineering-ai-standards evaluation framework supports multiple evaluation types (rule-based, LLM-judge, execution-based) but does not specifically address trajectory evaluation.

## Decision

**Decision:** We will add a third evaluation track — **Trajectory Evaluation** — that scores the agent's execution path using the event trace produced by the EventBus (Phase 1/Phase 4).

### `evaluations/trajectory/` — Trajectory Evaluation

```python
class TrajectoryEvaluator:
    """Scores the full execution trajectory of an agent run.

    Input:  List[Event] — Full event trace from a session
    Output: TrajectoryScore — Per-phase scores + composite
    """

    async def evaluate(
        self,
        trace: list[Event],
        expected: TrajectoryExpectations,
    ) -> TrajectoryScore:
        """Score the execution path across all phases."""
        ...
```

### Evaluation Dimensions

| Phase | Metrics | Data Source |
|-------|---------|-------------|
| **Planning** | Requirements coverage, dependency accuracy, strategy weight alignment | PlanningStarted/Completed events |
| **Tool Selection** | Appropriate tool choice, unnecessary calls, cache utilization | ToolInvoked/ToolCacheHit events |
| **Data Collection** | Coverage, freshness, completeness | Tool results in trace |
| **Skill Execution** | Reasoning quality, parameter correctness, skill invocation accuracy | SkillStarted/Completed, StepStarted/Completed events |
| **Error Handling** | Recovery quality, retry efficiency, failure escalation | ToolFailed/StepFailed/ErrorEncountered events |
| **Reflection** | Quality of intermediate adjustments, self-correction | ReflectionStarted (future event) |
| **Efficiency** | Steps vs optimal path, tool calls per step, time per step | All events (latency tracking) |
| **Overall** | Composite trajectory score | All dimensions weighted |

### Trajectory Scoring Example

```yaml
evaluation:
  case: fundamental-analysis-trace-v1
  phase: execution
  metrics:
    - name: tool_selection_appropriateness
      description: "Did the agent call the right tools for fundamental analysis?"
      measure: >
        Count of relevant tools vs irrelevant tools.
        Relevant: get_income_statement, get_balance_sheet, get_cashflow
        Irrelevant: get_daily_price (not needed for fundamental), get_money_flow
      ideal: "All calls are to relevant tools"
      weight: 0.3

    - name: redundant_calls
      description: "Did the agent call the same tool twice with same params?"
      measure: >
        Count of duplicate tool invocations (same tool + same args)
      ideal: "0 redundant calls"
      weight: 0.2

    - name: error_recovery_quality
      description: "How well did the agent handle tool errors?"
      measure: >
        On ToolFailed event, did the next event indicate retry
        (same tool, same args) or alternative approach?
      ideal: "Appropriate retry or fallback"
      weight: 0.3

    - name: reasoning_consistency
      description: "Does the reasoning flow logically from data to conclusion?"
      measure: >
        LLM-judge evaluates the reasoning chain extracted from events
      ideal: "Clear, logical progression"
      weight: 0.2
```

### Replay-Based Evaluation

Since the EventBus supports replay, trajectory evaluation can run on past sessions:

```python
# Evaluate a past session
trace = await event_bus.export_trace(session_id="a1b2c3d4")
score = await trajectory_evaluator.evaluate(
    trace=trace,
    expected=load_case("fundamental-analysis-trace-v1"),
)
print(f"Trajectory score: {score.overall}/100")
```

### CLI Integration

```bash
# Run with trajectory evaluation
python -m agent --requirement "Analyze ..." --eval-trajectory

# Evaluate a past session
python -m agent --eval-trajectory --session a1b2c3d4

# Compare trajectories
python -m agent --compare-trajectories session-a session-b
```

## Rationale

- **Process reveals quality that output hides**: An agent that wastes 50 tool calls then produces a good report is not a good agent. Output-only evaluation misses this.
- **Events enable trajectory analysis**: The EventBus (ADR-008) captures every state change. Trajectory evaluation is a consumer of these events — the infrastructure cost is already paid.
- **Trajectory insights drive improvement**: If the "tool selection" dimension scores low, we know to improve tool discovery or the Planner's tool reasoning. Output-only scores don't tell us *what* to fix.
- **Evaluation is replayable**: Past sessions can be re-scored after improving the evaluator — no re-execution needed.

## Consequences

### Positive

- Complete evaluation picture: output quality + process quality.
- Actionable feedback: low trajectory dimension scores directly suggest what to improve.
- Detects regressions in process efficiency even when output quality stays the same.
- Replay-based evaluation enables scoring every past session without re-running the agent.

### Negative

- Trajectory evaluation requires a full event trace. Sessions before the event system was deployed cannot be evaluated.
- Some dimensions (reasoning quality) require LLM-judge evaluation, adding cost and latency.
- Defining trajectory expectations (what is a "good" trajectory?) is subjective and requires iteration.

### Neutral

- Trajectory evaluation is complementary to, not a replacement for, output evaluation. Both tracks are maintained.
- The trajectory evaluator can be a simple scorer in Phase 5 and enhanced with LLM-judge later.

## Alternatives Considered

### Alternative 1: Continue with output-only evaluation

- **Description**: Only score final reports and strategy scores. Ignore process.
- **Pros**: No new infrastructure; simpler evaluation suites; faster evaluation runs.
- **Cons**: Cannot detect process regressions; no actionable process improvement signal; misses the "good process, bad outcome" scenario.
- **Why rejected**: Output-only evaluation is insufficient for a production-grade agent framework. Process quality is essential for trust, debugging, and improvement.

### Alternative 2: Manual trajectory review

- **Description**: Human reviewers read execution logs and score trajectory quality.
- **Pros**: Deep understanding; can catch nuanced quality issues.
- **Cons**: Not scalable (hours per trajectory); expensive; inconsistent across reviewers; cannot be run in CI.
- **Why rejected**: Automation is essential for regression detection in CI. Manual review is too slow and inconsistent.

### Alternative 3: Only count errors and warnings

- **Description**: Trajectory quality = low error count. Score by counting ToolFailed and StepFailed events.
- **Pros**: Simple to implement; objectively measurable.
- **Cons**: Error count alone doesn't capture reasoning quality, tool selection appropriateness, or efficiency. A trajectory with 0 errors but 50 redundant calls is bad but scores high.
- **Why rejected**: Too simplistic. Trajectory quality has more dimensions than error rate.

## Related Decisions

- [ADR-005: Evaluation Framework](005-evaluation-framework.md) — Original evaluation design
- [ADR-008: Event-Driven Observability](008-event-driven-observability.md) — Events are the data source for trajectory evaluation

## Notes

Trajectory evaluation is the third and final evaluation track, completing the picture:

| Track | What it scores | Data Source | When |
|-------|----------------|-------------|------|
| Strategy Performance | Investment outcome | Backtest results | Offline (periodic) |
| Agent Quality | Report correctness | Agent output | Per-run |
| Trajectory | Execution process | Event trace | Per-run |

All three tracks should pass before a skill/agent version is released.
