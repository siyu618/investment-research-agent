# Trajectory Evaluator — scores the full execution path of an agent run
#
# Input:  A list of Events (full execution trace from EventBus)
# Output: TrajectoryScore with per-dimension breakdowns
#
# Scoring dimensions:
#   - planning:       Was a valid plan produced with correct structure?
#   - tool_selection: Were appropriate tools called efficiently?
#   - execution_efficiency: Speed and resource usage
#   - error_recovery: Quality of error handling
#   - verification:   Thoroughness of self-verification
#   - overall_quality: Holistic completeness

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Optional

from runtime.models import Event, EventType

from .models import (
    DimensionScore,
    TrajectoryExpectations,
    TrajectoryScore,
)


class TrajectoryEvaluator:
    """Scores the full execution trajectory of an agent run.

    Usage:
        evaluator = TrajectoryEvaluator()
        trace = event_bus.export_trace(session_id="abc")
        score = await evaluator.evaluate(trace, expectations)
    """

    async def evaluate(
        self,
        trace: list[dict],
        expectations: Optional[TrajectoryExpectations] = None,
        case_path: Optional[str] = None,
    ) -> TrajectoryScore:
        """Evaluate a full execution trace.

        Args:
            trace: List of event dicts from EventBus.export_trace().
            expectations: Expected metrics for comparison.
            case_path: Path to a YAML case file (alternative to expectations).

        Returns:
            TrajectoryScore with per-dimension breakdown.
        """
        if case_path:
            expectations = self._load_case(case_path)
        if expectations is None:
            expectations = TrajectoryExpectations()

        # Pre-process trace into counts and metrics
        metrics = self._analyze_trace(trace)

        # Score each dimension
        dims = {}
        dims["planning"] = self._score_planning(metrics, expectations)
        dims["tool_selection"] = self._score_tool_selection(metrics, expectations)
        dims["execution_efficiency"] = self._score_execution_efficiency(metrics, expectations)
        dims["error_recovery"] = self._score_error_recovery(metrics, expectations)
        dims["verification"] = self._score_verification(metrics, expectations)
        dims["overall_quality"] = self._score_overall_quality(metrics, expectations)

        # Compute weighted overall score
        total_weight = sum(d.weight for d in dims.values())
        overall = (
            sum(d.weighted_score for d in dims.values()) / total_weight
            if total_weight > 0 else 0.0
        )

        # Collect exceptions
        exceptions = []
        for event in trace:
            if event.get("type") == "ErrorEncountered":
                exc = event.get("payload", {}).get("error", "")
                if exc:
                    exceptions.append(exc)

        return TrajectoryScore(
            case_id=case_path or "",
            overall_score=round(overall, 1),
            passed=overall >= 60.0,
            dimensions=dims,
            exceptions=exceptions,
        )

    # ─── Trace Analysis ─────────────────────────────────────────────────

    def _analyze_trace(self, trace: list[dict]) -> dict:
        """Analyze a trace and produce aggregate metrics."""
        event_types = [e.get("type", "") for e in trace]
        payloads = {e.get("type", ""): e.get("payload", {}) for e in trace}

        # Count event types
        from collections import Counter
        counts = Counter(event_types)

        # Extract node events
        node_events = [e for e in trace if e.get("type", "").startswith("Node")]
        tool_events = [e for e in trace if e.get("type", "").startswith("Tool")]
        skill_events = [e for e in trace if e.get("type", "").startswith("Skill")]
        error_events = [e for e in trace if e.get("type", "") == "ErrorEncountered"]

        # Extract timing
        start_events = [e for e in trace if e.get("type") in (
            "PlanningStarted", "WorkflowStarted", "NodeStarted",
        )]
        end_events = [e for e in trace if e.get("type") in (
            "WorkflowFinished", "NodeCompleted", "NodeFailed",
        )]

        # Node and tool call counts
        node_starts = sum(1 for e in trace if e.get("type") == "NodeStarted")
        node_completes = sum(1 for e in trace if e.get("type") == "NodeCompleted")
        node_fails = sum(1 for e in trace if e.get("type") == "NodeFailed")
        tool_calls = sum(1 for e in trace if e.get("type") == "ToolInvoked")
        tool_fails = sum(1 for e in trace if e.get("type") == "ToolFailed")
        cache_hits = sum(1 for e in trace if e.get("type") == "ToolCacheHit")
        cache_misses = sum(1 for e in trace if e.get("type") == "ToolCacheMiss")
        retries = sum(1 for e in trace if e.get("type") == "NodeRetried")

        # Count retried nodes
        retried_nodes = set()
        for e in trace:
            if e.get("type") == "NodeRetried":
                nid = e.get("payload", {}).get("node_id", "")
                if nid:
                    retried_nodes.add(nid)

        # Find total duration
        total_duration = 0
        for e in trace:
            if e.get("type") == "WorkflowFinished":
                total_duration = e.get("payload", {}).get("total_duration_ms", 0)

        # Graph info
        graph_resolved = None
        for e in trace:
            if e.get("type") == "GraphResolved":
                graph_resolved = e.get("payload", {})

        return {
            "event_count": len(trace),
            "event_types": event_types,
            "counts": dict(counts),
            "node_count": node_starts,
            "node_completed": node_completes,
            "node_failed": node_fails,
            "tool_call_count": tool_calls,
            "tool_fail_count": tool_fails,
            "cache_hit_count": cache_hits,
            "cache_miss_count": cache_misses,
            "retry_count": retries,
            "retried_nodes": retried_nodes,
            "total_duration_ms": total_duration,
            "error_count": len(error_events),
            "graph_node_count": (graph_resolved or {}).get("node_count", 0),
            "graph_layer_count": (graph_resolved or {}).get("layer_count", 0),
            "has_planning": "PlanningStarted" in event_types,
            "has_graph": "GraphResolved" in event_types,
            "has_verification": "VerificationCompleted" in event_types,
            "has_report": "ReportGenerated" in event_types,
        }

    # ─── Dimension Scoring ──────────────────────────────────────────────

    def _score_planning(
        self, metrics: dict, expected: TrajectoryExpectations
    ) -> DimensionScore:
        """Score planning quality."""
        criteria_met = []
        criteria_missed = []

        if metrics["has_planning"]:
            criteria_met.append("Plan was produced (PlanningStarted event present)")
        else:
            criteria_missed.append("No planning events found")

        if metrics["has_graph"]:
            criteria_met.append(f"Graph resolved with {metrics['graph_node_count']} nodes")
        else:
            criteria_missed.append("No GraphResolved event found")

        if metrics["has_report"]:
            criteria_met.append("Workflow completed successfully")

        # Check required events
        for req in expected.required_events:
            if req in metrics["event_types"]:
                criteria_met.append(f"Required event '{req}' present")
            else:
                criteria_missed.append(f"Required event '{req}' missing")

        # Score: -20 per missing required, base 100
        score = max(0, 100.0 - len(criteria_missed) * 20)

        return DimensionScore(
            name="planning",
            score=score,
            weight=0.15,
            description="Quality of requirement decomposition and graph construction",
            criteria_met=criteria_met,
            criteria_missed=criteria_missed,
        )

    def _score_tool_selection(
        self, metrics: dict, expected: TrajectoryExpectations
    ) -> DimensionScore:
        """Score tool selection quality."""
        criteria_met = []
        criteria_missed = []

        tc = metrics["tool_call_count"]
        cache_hits = metrics["cache_hit_count"]
        cache_misses = metrics["cache_miss_count"]

        criteria_met.append(f"{tc} tool calls made" if tc > 0 else "No tool calls")

        # Expected tool call count
        if expected.optimal_tool_call_count > 0:
            if tc <= expected.optimal_tool_call_count:
                criteria_met.append(f"Tool calls ({tc}) within expected ({expected.optimal_tool_call_count})")
            else:
                criteria_missed.append(
                    f"Tool calls ({tc}) exceed optimal ({expected.optimal_tool_call_count})"
                )

        # Cache efficiency
        total_lookups = cache_hits + cache_misses
        if total_lookups > 0:
            hit_rate = cache_hits / total_lookups * 100
            criteria_met.append(f"Tool cache hit rate: {hit_rate:.0f}% ({cache_hits}/{total_lookups})")
        elif tc > 0:
            pass  # No cache configured — neutral

        # Tool failures
        if metrics["tool_fail_count"] == 0:
            criteria_met.append("No tool failures")
        else:
            criteria_missed.append(f"{metrics['tool_fail_count']} tool failures occurred")

        score = 100.0
        if expected.optimal_tool_call_count > 0:
            ratio = abs(tc - expected.optimal_tool_call_count) / max(1, expected.optimal_tool_call_count)
            if ratio > 0.5:
                score -= 30
            elif ratio > 0.2:
                score -= 15
        score -= metrics["tool_fail_count"] * 25
        score = max(0, score)

        return DimensionScore(
            name="tool_selection",
            score=score,
            weight=0.20,
            description="Appropriateness and efficiency of tool usage",
            criteria_met=criteria_met,
            criteria_missed=criteria_missed,
        )

    def _score_execution_efficiency(
        self, metrics: dict, expected: TrajectoryExpectations
    ) -> DimensionScore:
        """Score execution speed and resource usage."""
        criteria_met = []
        criteria_missed = []

        dur = metrics["total_duration_ms"]
        nc = metrics["node_count"]

        if dur > 0:
            criteria_met.append(f"Total duration: {dur}ms")
        if expected.expected_duration_ms > 0:
            if dur <= expected.expected_duration_ms * 1.5:
                criteria_met.append(f"Duration within expected range")
            else:
                criteria_missed.append(
                    f"Duration ({dur}ms) exceeds expected ({expected.expected_duration_ms}ms)"
                )

        if expected.optimal_node_count > 0:
            if nc <= expected.optimal_node_count:
                criteria_met.append(f"Node count ({nc}) within optimal ({expected.optimal_node_count})")
            else:
                criteria_missed.append(
                    f"Node count ({nc}) exceeds optimal ({expected.optimal_node_count})"
                )

        # Retries
        if metrics["retry_count"] <= expected.expected_retry_count:
            criteria_met.append(f"No excessive retries ({metrics['retry_count']})")
        else:
            criteria_missed.append(f"Excessive retries: {metrics['retry_count']}")

        score = 100.0
        if expected.expected_duration_ms > 0 and dur > 0:
            ratio = dur / max(1, expected.expected_duration_ms)
            if ratio > 2.0:
                score -= 30
            elif ratio > 1.5:
                score -= 15
        if metrics["retry_count"] > expected.expected_retry_count:
            score -= metrics["retry_count"] * 15
        score = max(0, score)

        return DimensionScore(
            name="execution_efficiency",
            score=score,
            weight=0.20,
            description="Completion speed and resource usage",
            criteria_met=criteria_met,
            criteria_missed=criteria_missed,
        )

    def _score_error_recovery(
        self, metrics: dict, expected: TrajectoryExpectations
    ) -> DimensionScore:
        """Score error handling and recovery quality."""
        criteria_met = []
        criteria_missed = []

        retried = metrics["retried_nodes"]
        failed = metrics["node_failed"]
        errors = metrics["error_count"]

        if errors == 0:
            criteria_met.append("No errors encountered")
        else:
            criteria_met.append(f"{errors} error(s) encountered")
            if retried:
                criteria_met.append(f"Recovered from errors on nodes: {', '.join(sorted(retried))}")

        if failed == 0:
            criteria_met.append("No node failures")
        else:
            criteria_missed.append(f"{failed} node(s) failed permanently")

        # Check forbidden events
        for forbidden in expected.forbidden_events:
            if forbidden in metrics["event_types"]:
                criteria_missed.append(f"Forbidden event '{forbidden}' occurred")

        score = 100.0
        # Only penalize forbidden events if they actually occurred
        for forbidden in expected.forbidden_events:
            if forbidden in metrics["event_types"]:
                criteria_missed.append(f"Forbidden event '{forbidden}' occurred")
                score -= 30
        score -= failed * 25
        score = max(0, score)

        return DimensionScore(
            name="error_recovery",
            score=score,
            weight=0.20,
            description="Quality of error handling and recovery",
            criteria_met=criteria_met,
            criteria_missed=criteria_missed,
        )

    def _score_verification(
        self, metrics: dict, expected: TrajectoryExpectations
    ) -> DimensionScore:
        """Score verification thoroughness."""
        criteria_met = []
        criteria_missed = []

        if metrics["has_verification"]:
            criteria_met.append("Verification was performed")
        else:
            criteria_missed.append("No verification events found")

        # Check for verification-related events
        skill_verify_count = 0
        for et in metrics["event_types"]:
            if "SkillVerifying" in et or "SkillVerification" in et:
                skill_verify_count += 1

        if skill_verify_count > 0:
            criteria_met.append(f"{skill_verify_count} skill verification(s) performed")

        score = 100.0 if metrics["has_verification"] else 40.0
        score = max(0, score)

        return DimensionScore(
            name="verification",
            score=score,
            weight=0.15,
            description="Thoroughness of self-verification",
            criteria_met=criteria_met,
            criteria_missed=criteria_missed,
        )

    def _score_overall_quality(
        self, metrics: dict, expected: TrajectoryExpectations
    ) -> DimensionScore:
        """Score holistic trajectory quality."""
        criteria_met = []
        criteria_missed = []

        # Event diversity
        unique_types = len(set(metrics["event_types"]))
        if unique_types >= 5:
            criteria_met.append(f"Good event diversity ({unique_types} unique types)")
        else:
            criteria_missed.append(f"Low event diversity ({unique_types} unique types)")

        # Event total
        total = metrics["event_count"]
        if 10 <= total <= 200:
            criteria_met.append(f"Reasonable event count ({total})")
        elif total > 200:
            criteria_missed.append(f"Excessive event count ({total})")

        # End-to-end completion
        if metrics["has_report"]:
            criteria_met.append("End-to-end completion: report generated")
        else:
            criteria_missed.append("No report generation event")

        score = 100.0
        if not metrics["has_report"]:
            score -= 30
        if unique_types < 5:
            score -= 15
        if total > 200:
            score -= 10
        # Empty trace penalty
        if total == 0:
            score -= 50
        score = max(0, score)

        return DimensionScore(
            name="overall_quality",
            score=score,
            weight=0.10,
            description="Holistic trajectory quality",
            criteria_met=criteria_met,
            criteria_missed=criteria_missed,
        )

    # ─── Case Loading ──────────────────────────────────────────────────

    @staticmethod
    def _load_case(case_path: str) -> TrajectoryExpectations:
        """Load expectations from a YAML evaluation case file."""
        path = Path(case_path)
        if not path.exists():
            raise FileNotFoundError(f"Trajectory evaluation case not found: {case_path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        expectations = data.get("expectations", {})
        return TrajectoryExpectations(
            optimal_node_count=expectations.get("optimal_node_count", -1),
            optimal_tool_call_count=expectations.get("optimal_tool_call_count", -1),
            expected_duration_ms=expectations.get("expected_duration_ms", -1),
            expected_retry_count=expectations.get("expected_retry_count", 0),
            required_events=expectations.get("required_events", []),
            forbidden_events=expectations.get("forbidden_events", []),
        )


# ─── Convenience method ─────────────────────────────────────────────────


def evaluate_trace_from_bus(
    event_bus,
    session_id: str,
    case_path: Optional[str] = None,
) -> TrajectoryScore:
    """Evaluate a trace from an EventBus session.

    Convenience entry point for CLI and Harness integration.
    """
    import asyncio
    trace = event_bus.export_trace(session_id)
    evaluator = TrajectoryEvaluator()
    return asyncio.run(evaluator.evaluate(trace, case_path=case_path))
