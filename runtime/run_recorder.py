# Run Recorder — persists every agent run for audit, replay, and debugging
#
# Writes to runs/{run_id}/:
#   manifest.json          — artifact list + hashes + schema versions (Replay gate)
#   request.json           — original user requirement + parsed InvestmentRequest
#   plan.json              — the AnalysisPlan (steps, weights, params)
#   tool_trace.jsonl       — one JSON object per tool call (inputs/outputs-hash, latency, retries)
#   agent_trace.jsonl      — unified lifecycle trace
#   data_snapshot.json     — all DataSnapshots consumed during the run
#   execution_outputs.json — per-DAG-node outputs + hashes
#   result_manifest.json   — standardized business results (candidates, verification)
#   verification.json      — Verifier result (checks, warnings, errors)
#   execution_graph.mmd    — Mermaid flowchart
#   report.md              — final Markdown report
#   meta.json              — run metadata (status, duration, event count)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.snapshot import hash_of

# Schema versions — bump when a file's shape changes so old runs remain
# distinguishable from incompatible new ones.
SCHEMA_VERSIONS = {
    "manifest.json": "1.0.0",
    "request.json": "1.0.0",
    "plan.json": "1.0.0",
    "data_snapshot.json": "2.0.0",
    "execution_outputs.json": "1.0.0",
    "result_manifest.json": "1.0.0",
    "verification.json": "1.0.0",
    "agent_trace.jsonl": "1.0.0",
    "tool_trace.jsonl": "1.0.0",
}


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat()


def _artifact_purpose(fname: str) -> str:
    """Short purpose description for each run artifact."""
    purposes = {
        "request.json": "original user requirement + provider",
        "plan.json": "structured analysis plan",
        "data_snapshot.json": "point-in-time data snapshots",
        "execution_outputs.json": "per-DAG-node outputs + hashes (Replay)",
        "result_manifest.json": "standardized business results (Replay)",
        "verification.json": "verifier checks + policy + blocked",
        "agent_trace.jsonl": "unified lifecycle trace",
        "tool_trace.jsonl": "tool-call granularity trace",
        "report.md": "final markdown report",
        "meta.json": "run metadata",
        "execution_graph.mmd": "mermaid execution flowchart",
    }
    return purposes.get(fname, "run artifact")


class RunRecorder:
    """Writes a complete, auditable record of an agent run."""

    def __init__(self, runs_dir: str = "runs"):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create_run(self, run_id: str) -> Path:
        """Create the directory for a new run. Returns its path."""
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def write_json(self, run_id: str, filename: str, data: Any) -> Path:
        """Write a JSON artifact for a run."""
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return path

    def write_text(self, run_id: str, filename: str, content: str) -> Path:
        """Write a text artifact (e.g. report.md)."""
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def append_jsonl(self, run_id: str, filename: str, record: dict) -> None:
        """Append a line to a JSONL trace file."""
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / filename
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ─── Convenience: full run ──────────────────────────────────────────

    def save_full_run(
        self,
        run_id: str,
        request: dict,
        plan: dict,
        tool_trace: list[dict],
        snapshots: list[dict],
        verification: dict,
        report_md: str,
        meta: dict,
        agent_trace: list[dict] | None = None,
        graph_mmd: str = "",
        execution_outputs: dict | None = None,
        result_manifest: dict | None = None,
    ) -> Path:
        """Write all standard artifacts for a run. Returns run dir.

        Extra artifacts (when provided):
          - agent_trace:        unified lifecycle trace (planner/skill/tool/verifier/llm)
          - graph_mmd:          Mermaid execution flowchart
          - execution_outputs:  per-DAG-node outputs + hashes (for Replay)
          - result_manifest:    standardized business results (for Replay)
        """
        run_dir = self.create_run(run_id)

        self.write_json(run_id, "request.json", request)
        self.write_json(run_id, "plan.json", plan)
        self.write_json(run_id, "data_snapshot.json", {
            "slice_count": len(snapshots),
            "as_of": snapshots[-1].get("as_of", "") if snapshots else "",
            "slices": snapshots,
        })
        self.write_json(run_id, "verification.json", verification)
        self.write_json(run_id, "meta.json", meta)
        self.write_text(run_id, "report.md", report_md)

        # tool_trace.jsonl — one object per line (tool-call granularity)
        trace_path = run_dir / "tool_trace.jsonl"
        with open(trace_path, "w", encoding="utf-8") as f:
            for rec in tool_trace:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

        # agent_trace.jsonl — unified lifecycle (planner/skill/verifier/llm/...)
        if agent_trace is not None:
            agent_path = run_dir / "agent_trace.jsonl"
            with open(agent_path, "w", encoding="utf-8") as f:
                for rec in agent_trace:
                    f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

        # execution_graph.mmd — Mermaid flowchart
        if graph_mmd:
            self.write_text(run_id, "execution_graph.mmd", graph_mmd)

        # execution_outputs.json — per-node outputs + hashes (for Replay)
        if execution_outputs:
            self.write_json(run_id, "execution_outputs.json", execution_outputs)

        # result_manifest.json — standardized business results (for Replay)
        if result_manifest:
            self.write_json(run_id, "result_manifest.json", result_manifest)

        # manifest.json — artifact list + hashes + schema versions (Replay gate)
        self._write_manifest(run_id, run_dir)

        return run_dir

    def _write_manifest(self, run_id: str, run_dir: Path) -> None:
        """Compute per-artifact hashes and write manifest.json."""
        artifacts: dict[str, dict] = {}
        for fname in sorted(p.name for p in run_dir.iterdir() if p.is_file()):
            if fname == "manifest.json":
                continue
            raw = (run_dir / fname).read_bytes()
            artifacts[fname] = {
                "sha256": hash_of(raw.decode("utf-8", errors="replace")),
                "size_bytes": len(raw),
                "schema_version": SCHEMA_VERSIONS.get(fname, "1.0.0"),
                "purpose": _artifact_purpose(fname),
            }
        manifest = {
            "manifest_version": "1.0.0",
            "run_id": run_id,
            "created_at": _now_iso(),
            "artifacts": artifacts,
        }
        self.write_json(run_id, "manifest.json", manifest)

    # ─── Mermaid graph helpers ──────────────────────────────────────────

    @staticmethod
    def build_execution_graph(plan: dict, graph_result: Any) -> str:
        """Build a Mermaid flowchart from the plan steps + real node results.

        Nodes = analysis steps; edges = dependencies.
        Status from the Scheduler's GraphResult: ✓ success / ✗ failed /
        ! retried — not from plan status (which is always pending).
        """
        steps = plan.get("analysis_steps", [])
        if not steps:
            return ""

        # Real per-node status from the scheduler
        node_status: dict[str, dict] = {}
        if graph_result is not None and hasattr(graph_result, "node_results"):
            for nid, nr in graph_result.node_results.items():
                node_status[nid] = {
                    "success": getattr(nr, "success", True),
                    "retries": getattr(nr, "retry_count", 0),
                }

        lines = ["flowchart TD"]
        node_ids = {}

        # Step 1: define nodes
        for s in steps:
            sid = s.get("id")
            skill = s.get("skill", "?")
            nid = f"n{sid}"
            node_ids[sid] = nid

            # Real status from graph result (keyed by "step-{id}")
            actual = node_status.get(f"step-{sid}", {})
            if actual.get("success") is False:
                label = f"{sid}:{skill} ✗"
            elif actual.get("retries", 0) > 0:
                label = f"{sid}:{skill} !"
            elif actual:  # present and success
                label = f"{sid}:{skill} ✓"
            else:
                label = f"{sid}:{skill}"
            lines.append(f'    {nid}["{label}"]')

        # Step 2: edges from depends_on
        for s in steps:
            for dep in s.get("depends_on", []):
                lines.append(f"    {node_ids.get(dep, '?')} --> {node_ids.get(s.get('id'), '?')}")

        return "\n".join(lines)
