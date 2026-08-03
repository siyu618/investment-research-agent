# Trace Formatters — Human-readable and JSON trace output
#
# The trace formatter converts a raw event list into readable output
# for CLI debugging and JSON export for trajectory evaluation.

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime.models import EventType

# ─── CLI Trace Formatter ─────────────────────────────────────────────────


def format_trace_cli(
    trace: list[dict],
    session_id: str = "",
    duration_ms: int = 0,
    event_count: int = 0,
) -> str:
    """Format a full execution trace as human-readable CLI output.

    Produces output like:
        ═══════════════════════════════════════════════
         Execution Trace: session-a1b2c3d4
        ═══════════════════════════════════════════════
         09:30:01.000 [PLAN]     PlanningStarted        requirement="Analyze..."
         09:30:02.150 [GRAPH]    GraphResolved          9 nodes, 4 layers
         09:30:02.200 [TOOL]     ToolInvoked            get_stock_basic(market=SSE)
         09:30:02.800 [TOOL]     ToolFinished           892ms
         09:33:01.200 [DONE]     WorkflowFinished       120.3s total, 32 events
    """
    lines = []
    header_len = 60

    lines.append("═" * header_len)
    lines.append(f" Execution Trace: {session_id or 'unknown'}")
    lines.append("═" * header_len)

    if not trace:
        lines.append(" (no events recorded)")
        lines.append("")
        return "\n".join(lines)

    for event in trace:
        ts = event.get("timestamp", "")
        etype = event.get("type", "???")
        payload = event.get("payload", {})

        # Format timestamp to HH:MM:SS.fff
        time_str = _format_timestamp(ts)

        # Determine category label
        label = _event_category(etype)

        # Format payload
        payload_str = _format_payload(etype, payload, max_len=80)

        lines.append(f" {time_str} [{label:<6}] {etype:<25} {payload_str}")

    lines.append("═" * header_len)

    # Summary line
    if duration_ms:
        lines.append(
            f" {event_count} events, "
            f"{duration_ms / 1000:.1f}s total"
        )

    lines.append("")
    return "\n".join(lines)


def format_scorecard_cli(score) -> str:
    """Format a TrajectoryScore as human-readable CLI output."""
    lines = []
    lines.append("─" * 60)
    lines.append(f" Trajectory Score: {score.overall_score:.1f}/100")
    lines.append(f" Case: {score.case_id or 'N/A'}")
    lines.append(f" Verdict: {'PASS' if score.passed else 'FAIL'}")
    lines.append("─" * 60)

    # Per-dimension breakdown
    for dim_name in [
        "planning", "tool_selection", "execution_efficiency",
        "error_recovery", "verification", "overall_quality",
    ]:
        dim = score.dimensions.get(dim_name)
        if dim is None:
            continue

        bar = _score_bar(dim.score)
        lines.append(
            f" {bar} {dim_name:<22} {dim.score:>5.1f}/100 "
            f"(weight: {int(dim.weight * 100)}%)"
        )
        for met in dim.criteria_met:
            lines.append(f"       ✓ {met}")
        for missed in dim.criteria_missed:
            lines.append(f"       ✗ {missed}")

    if score.exceptions:
        lines.append("─" * 60)
        lines.append(f" Exceptions ({len(score.exceptions)}):")
        for exc in score.exceptions[:5]:
            lines.append(f"   • {exc[:120]}")

    lines.append("─" * 60)
    return "\n".join(lines)


def format_trace_chain_cli(
    spans: list[dict],
    query: str = "",
    duration_ms: int = 0,
) -> str:
    """Render the full agent chain from real spans.

    The chain reflects the actual lifecycle stages recorded during the run:

        User Query → Planner → Agent(Skill) → Tool → Retrieval → LLM → Final Result

    Span kinds are mapped to chain stages; each line shows the stage label,
    span name, status, latency, and (for LLM) token usage. This is the
    production-style "agent debugging" view.
    """
    lines = []
    lines.append("─" * 60)
    lines.append(" 🔍 Agent Chain (User Query → … → Final Result)")
    lines.append("─" * 60)
    lines.append(f"  QUERY    {query[:80] if query else '(no query)'}")
    lines.append("")

    if not spans:
        lines.append("  (no spans recorded)")
    else:
        for span in spans:
            kind = span.get("kind", "?")
            name = span.get("name", "?")
            status = span.get("status", "ok")
            dur = span.get("duration_ms", 0)
            stage = _span_stage(kind)
            mark = "✓" if status == "ok" else "✗" if status == "error" else "•"
            seg = f"  {mark} [{stage:<5}] {name}"
            extras = []
            if dur:
                extras.append(f"{dur}ms")
            if kind == "llm":
                usage = span.get("token_usage") or {}
                in_tok = usage.get("input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)
                if in_tok or out_tok:
                    extras.append(f"{in_tok}+{out_tok} tok")
            if span.get("output_summary"):
                extras.append(span["output_summary"][:40])
            if extras:
                seg += "  (" + ", ".join(extras) + ")"
            lines.append(seg)
        lines.append("")
        lines.append(f"  {len(spans)} spans total")

    if duration_ms:
        lines.append(f"  duration: {duration_ms}ms")
    lines.append("─" * 60)
    return "\n".join(lines)


def _span_stage(kind: str) -> str:
    """Map a span kind to its chain-stage label."""
    mapping = {
        "planner": "PLAN",
        "scheduler": "SCHED",
        "agent": "AGENT",
        "skill": "SKILL",
        "tool": "TOOL",
        "retrieval": "RETR",
        "llm": "LLM",
        "verifier": "VERIFY",
        "aggregator": "AGG",
        "reporter": "REPORT",
    }
    return mapping.get(kind, kind.upper()[:5])


# ─── JSON Trace Export ──────────────────────────────────────────────────


def export_trace_json(
    trace: list[dict],
    score: Any = None,
    filepath: str | None = None,
) -> str:
    """Export trace and optional score to JSON.

    Returns the JSON string. If filepath is provided, also writes to file.
    """
    output = {
        "exported_at": datetime.now().isoformat(),
        "event_count": len(trace),
        "trace": trace,
    }

    if score is not None:
        import dataclasses
        try:
            output["score"] = dataclasses.asdict(score)
        except TypeError:
            output["score"] = str(score)

    json_str = json.dumps(output, indent=2, default=str)

    if filepath:
        Path(filepath).write_text(json_str)

    return json_str


# ─── Helpers ────────────────────────────────────────────────────────────


def _format_timestamp(ts: str) -> str:
    """Convert ISO timestamp to HH:MM:SS.fff."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
    except (ValueError, TypeError):
        return ts[-12:] if ts else "???"


def _event_category(etype: str) -> str:
    """Determine a short category label for an event type."""
    if etype.startswith("Plan"):
        return "PLAN"
    if etype.startswith("Graph") or etype.startswith("Node") or etype.startswith("Workflow"):
        return "FLOW"
    if etype.startswith("Tool"):
        return "TOOL"
    if etype.startswith("Skill"):
        return "SKILL"
    if etype.startswith("Memory") or "Cache" in etype:
        return "CACHE"
    if etype.startswith("Verify") or etype.startswith("Verif"):
        return "CHECK"
    if etype.startswith("Report"):
        return "REPORT"
    if etype.startswith("Error"):
        return "ERROR"
    if etype.startswith("User"):
        return "USER"
    if "Started" in etype:
        return "START"
    if "Finish" in etype or "Complete" in etype:
        return "DONE"
    return "INFO"


def _format_payload(etype: str, payload: dict, max_len: int = 80) -> str:
    """Format event payload as a compact string."""
    if not payload:
        return ""

    if etype == EventType.TOOL_INVOKED:
        tn = payload.get("tool_name", "")
        inp = payload.get("input", {})
        params = ",".join(f"{k}={v}" for k, v in inp.items() if k != "correlation_id")
        return f"{tn}({params})"[:max_len]

    if etype == EventType.TOOL_FINISHED:
        dur = payload.get("duration_ms", 0)
        return f"{dur}ms"

    if etype == EventType.TOOL_FAILED:
        err = payload.get("error", "")
        return f"FAIL: {err}"[:max_len]

    if etype in (EventType.GRAPH_RESOLVED,):
        nc = payload.get("node_count", "?")
        lc = payload.get("layer_count", "?")
        return f"{nc} nodes, {lc} layers"

    if etype == EventType.WORKFLOW_FINISHED:
        dur = payload.get("total_duration_ms", 0)
        status = payload.get("status", "?")
        return f"{dur}ms, status={status}"

    if etype == EventType.NODE_STARTED:
        return payload.get("label", payload.get("skill", ""))

    if etype == EventType.NODE_COMPLETED:
        dur = payload.get("duration_ms", 0)
        return f"{dur}ms"

    if etype == EventType.NODE_FAILED:
        err = payload.get("error", "")
        return f"FAIL: {err}"[:max_len]

    if etype == EventType.ERROR_ENCOUNTERED:
        err = payload.get("error", "")
        step = payload.get("step", payload.get("node_id", ""))
        return f"[{step}] {err}"[:max_len]

    if etype == EventType.REPORT_GENERATED:
        rid = payload.get("report_id", "")
        return rid

    if etype == EventType.TOOL_CACHE_HIT:
        tn = payload.get("tool_name", "")
        saved = payload.get("saved_ms", "")
        return f"{tn} (cached, saved {saved}ms)" if saved else f"{tn} (cached)"

    if etype == EventType.TOOL_CACHE_MISS:
        tn = payload.get("tool_name", "")
        return f"{tn} (cache miss)"

    if "plan" in str(payload.get("plan", "")):
        return f"plan={str(payload['plan'])[:60]}"

    return str(payload)[:max_len]


def _score_bar(score: float, width: int = 16) -> str:
    """Generate a unicode bar for a score."""
    filled = int(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    return bar
