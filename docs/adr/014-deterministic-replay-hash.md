# Architecture Decision Record: Deterministic Replay + Hash Split

**Status:** Accepted
**Decision:** #014
**Date:** 2026-08-01

## Context

Replay was upgraded from "re-run a few skills" to "full DAG replay", but the equivalence check compared only snapshot/plan hashes against hand-built summaries, not the original node outputs. Two problems:

1. **Hash conflation**: `data_hash` mixed content-only hashing with full-context hashing. Replay needed the full context (as_of, publish_date, effective_date) but caching needed content-only stability. One field couldn't serve both.
2. **Node outputs not persisted**: There was no artifact holding each DAG node's standardized output + hash, so Replay couldn't compare node-by-node — it compared against a summary built from the replay run itself (self-referential, not truly verifying equivalence).

## Decision

### Hash split (R6)

- **`content_hash`** — over data content + query context only. EXCLUDES run-varying timestamps (as_of/publish_date/effective_date). Stable across runs/environments → for caching.
- **`snapshot_hash`** — over content + as_of/publish_date/effective_date/version. Full context → for Replay equivalence.
- `data_hash` retained as a deprecated alias → `snapshot_hash` for backward compatibility.
- `to_dict()` emits both `content_hash` and `snapshot_hash`.

### Deterministic Replay Verification (R3)

- New artifact **`execution_outputs.json`**: per-DAG-node standardized output (score + per-profile ts_code/score) + stable hash.
- Only **real analysis skill nodes** (fund/val/risk) are compared. The data-collector and portfolio/verifier/report-generator placeholder nodes differ between a live run and a replay by design (their logic lives in the Harness), so they are excluded.
- Replay reads the original `execution_outputs.json` and compares **every node's output_hash** against the replay run, plus snapshot_hash, plan_hash, candidate count, verification, and report structure.
- Any mismatch produces a detailed diff (per-node expected/actual hash prefixes) and marks the run `failed`.

## Rationale

- Separating content hash from snapshot hash gives both caching stability and replay-fidelity without one compromising the other.
- Persisting node outputs makes Replay a **true** equivalence check — the replay is compared against what the original run actually produced, not against itself.
- Excluding placeholder nodes keeps the check meaningful: only deterministic analysis outputs are verified.

## Consequences

### Positive

- Verified by tests: `content_hash` stable across processes and runs; `snapshot_hash` differs with as_of; Replay node outputs all match (`tests/agent/test_replay.py`, `tests/tools/test_mock_determinism.py`).
- Live run → replay produces `status: passed` with `provider_access_attempted: 0` and per-node hash equality.

### Negative

- Old runs without `execution_outputs.json` cannot do node-level comparison (fall back to snapshot/plan/report checks).
- `data_hash` is deprecated; consumers should migrate to `content_hash`/`snapshot_hash`.

### Neutral

- The Replay CLI (`python -m agent --replay runs/{id}`) now reports detailed diffs instead of a bare pass/fail.

## Alternatives Considered

### Alternative 1: Compare report Markdown text
Rejected in favor of structured node outputs — Markdown is presentation, not data; structurally identical reports with different internal state would pass.

### Alternative 2: Keep a single `data_hash` covering everything
Rejected: caching would break (timestamps make hashes differ every run), and Replay couldn't isolate content changes from time-context changes.

## Related Decisions

- [ADR-012: trace_span](012-trace-span.md)
- [ADR-013: Point-in-Time](013-point-in-time.md)
