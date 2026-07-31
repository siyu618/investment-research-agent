# Agent Trace — unified per-step execution record
#
# A TraceRecord captures one meaningful step in a run:
#   run_id, step_id, kind (skill|tool|llm|memory), name,
#   input/output summary + hash, latency, retries, status, error, tokens.
#
# The RunRecorder persists these to runs/{run_id}/tool_trace.jsonl.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from runtime.snapshot import hash_of


@dataclass
class TraceRecord:
    """A single auditable step in an agent run."""

    run_id: str
    step_id: str
    kind: str                    # "skill" | "tool" | "llm" | "memory" | "node"
    name: str                    # skill name / tool name / node id
    status: str = "ok"           # "ok" | "error" | "skipped" | "retried"

    # Input/output: keep a hash + size to avoid bloating traces
    input_summary: str = ""
    input_hash: str = ""
    output_summary: str = ""
    output_hash: str = ""
    output_size: int = 0

    duration_ms: int = 0
    retry_count: int = 0
    error: str = ""

    # LLM usage (when applicable)
    token_usage: dict = field(default_factory=dict)

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_jsonl(self) -> dict:
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
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "error": self.error,
            "token_usage": self.token_usage,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def make(
        run_id: str,
        step_id: str,
        kind: str,
        name: str,
        input_data: Any = None,
        output_data: Any = None,
        status: str = "ok",
        duration_ms: int = 0,
        retry_count: int = 0,
        error: str = "",
        token_usage: dict | None = None,
    ) -> TraceRecord:
        """Build a TraceRecord with computed hashes and summaries."""
        input_summary = ""
        input_hash = ""
        if input_data is not None:
            input_hash = hash_of(input_data)
            input_summary = _summarize(input_data)

        output_summary = ""
        output_hash = ""
        output_size = 0
        if output_data is not None:
            output_hash = hash_of(output_data)
            output_summary = _summarize(output_data)
            output_size = len(output_summary)

        return TraceRecord(
            run_id=run_id,
            step_id=step_id,
            kind=kind,
            name=name,
            status=status,
            input_summary=input_summary,
            input_hash=input_hash,
            output_summary=output_summary,
            output_hash=output_hash,
            output_size=output_size,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error=error,
            token_usage=token_usage or {},
        )


def _summarize(data: Any, max_len: int = 300) -> str:
    """Short human-readable summary of data for trace output."""
    try:
        text = str(data)
    except Exception:
        return "<unserializable>"
    if len(text) > max_len:
        return text[:max_len] + f"...({len(text)} chars)"
    return text
