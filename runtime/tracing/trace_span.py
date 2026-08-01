# trace_span — unified execution span for agent observability
#
# Wraps any async operation (planner / LLM / tool / skill / verifier /
# report) and automatically records:
#   - real start/end timestamps + duration_ms
#   - input/output summary + stable SHA-256 hash
#   - exception → status="error" + error message
#   - retry_count, token_usage (set by caller)
#
# Produces the same JSON shape as TraceRecord.to_jsonl(), so spans can be
# appended directly to agent_trace.jsonl.

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from runtime.snapshot import hash_of


class SpanEntry:
    """Mutable span state; finalizes itself on exit."""

    def __init__(
        self,
        run_id: str,
        step_id: str,
        kind: str,
        name: str,
        retry_count: int = 0,
    ):
        self.run_id = run_id
        self.step_id = step_id
        self.kind = kind
        self.name = name
        self.status = "ok"
        self.error = ""
        self.retry_count = retry_count
        self.token_usage: dict = {}
        self.input_summary = ""
        self.input_hash = ""
        self.output_summary = ""
        self.output_hash = ""
        self.output_size = 0
        self.timestamp = datetime.now().isoformat()
        self._start = datetime.now()

    def set_input(self, data: Any) -> None:
        """Record input data (computes stable hash + summary)."""
        self.input_hash = hash_of(data)
        self.input_summary = _summarize(data)

    def set_output(self, data: Any) -> None:
        """Record output data (computes stable hash + summary)."""
        self.output_hash = hash_of(data)
        self.output_summary = _summarize(data)
        self.output_size = len(self.output_summary)

    def finalize(self) -> dict:
        """Compute duration and return the JSONL record."""
        duration_ms = int((datetime.now() - self._start).total_seconds() * 1000)
        return {
            "run_id": self.run_id,
            "step_id": self.step_id,
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "input_summary": self.input_summary,
            "input_hash": self.input_hash,
            "output_summary": self.output_summary,
            "output_hash": self.output_hash,
            "output_size": self.output_size,
            "duration_ms": duration_ms,
            "retry_count": self.retry_count,
            "error": self.error,
            "token_usage": self.token_usage,
            "timestamp": self.timestamp,
        }


@asynccontextmanager
async def trace_span(
    run_id: str,
    step_id: str,
    kind: str,
    name: str,
    *,
    retry_count: int = 0,
    sink: list[dict] | None = None,
) -> AsyncIterator[SpanEntry]:
    """Async context manager that records a span into `sink`.

    Usage:
        async with trace_span(run_id, "step-2", "skill", "fundamental-analysis",
                              sink=self._agent_trace) as span:
            span.set_input(context)
            output = await skill.execute(...)
            span.set_output({"score": output.score})
        # on exception: span.status="error", span.error=..., re-raised

    The finalized dict is appended to `sink` on clean or error exit.
    """
    span = SpanEntry(run_id, step_id, kind, name, retry_count=retry_count)
    try:
        yield span
    except Exception as e:
        span.status = "error"
        span.error = str(e)[:200]
        if sink is not None:
            sink.append(span.finalize())
        raise
    else:
        if sink is not None:
            sink.append(span.finalize())


def _summarize(data: Any, max_len: int = 300) -> str:
    """Short human-readable summary of data."""
    try:
        text = str(data)
    except Exception:
        return "<unserializable>"
    if len(text) > max_len:
        return text[:max_len] + f"...({len(text)} chars)"
    return text
