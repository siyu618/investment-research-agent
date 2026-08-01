# Architecture Decision Record: Point-in-Time Data Handling

**Status:** Accepted
**Decision:** #013
**Date:** 2026-08-01

## Context

The README claimed point-in-time (PIT) semantics, but the implementation only stored a **global** `publish_date` on the snapshot. Per-record disclosure dates did not exist:

- `FinancialStatement` had only `end_date` (report period end) — no `ann_date` (announcement date). A FY2024 report was returned even when queried with `as_of` before its announcement.
- The Mock provider generated no disclosure lag; `available_at` was synthesized in the analyzer as `f"{end_date[:4]}-12-31"` (fiscal year end, not disclosure).
- `DataCollector.collect` accepted `as_of` but never used it to filter; the executor didn't thread it from the plan.
- The verifier's lookahead check compared against `datetime.now()`, not the analysis `as_of`, and in the live path couldn't reach `profiles` nested inside `output.data`.

Result: "data published after the analysis date" could reach Skills — a PIT violation.

## Decision

- **Per-record PIT fields**: `FinancialStatement.ann_date` (disclosure date YYYYMMDD). `DailyPrice.trade_date` already exists and serves as its PIT anchor.
- **Mock disclosure lag**: `_announcement_date()` adds realistic lag by report type (annual ~90d, Q3 ~30d, Q2 ~45d, Q1 ~30d) plus deterministic jitter, guaranteeing `ann_date > end_date`.
- **Tushare mapping**: income/balance/cashflow request and map `f_ann_date`/`ann_date` via `_pick_ann_date()`.
- **DataCollector filtering**: `collect(as_of=...)` filters prices by `trade_date <= as_of` and financials by `ann_date <= as_of`. Filtered records never enter the dataset, so Skills cannot see future data. `as_of` is threaded from plan params → executor → collector.
- **Analyzer provenance**: `available_at` derives from `ann_date` (via `_available_at()`), falling back to `end_date`.
- **Verifier second line**: `_check_lookahead` remains as a fatal gate for any residual future data.

## Rationale

- Filtering at the DataCollector (the only provider accessor) is the correct enforcement point — Skills are guaranteed to consume only records disclosed by `as_of`.
- Per-record `ann_date` is the industry-standard disclosure anchor (Tushare provides it), far more accurate than a global snapshot `publish_date`.
- The Mock lag models real-world disclosure timing so PIT tests are meaningful.

## Consequences

### Positive

- PIT filtering verified by tests: `as_of=20240630` excludes the FY2024 annual (ann ~2025-03); `as_of=20251231` includes it (`tests/tools/test_pit_filter.py`).
- Every mock financial record now carries `ann_date > end_date` (tested).
- `available_at` in reports reflects actual disclosure dates, not fiscal year end.

### Negative

- Old snapshots without `ann_date` fall back to `end_date` (no filter applied) — a migration concern for existing runs.
- Querying with a restrictive `as_of` can yield empty financials (correct, but callers must handle empty data).

### Neutral

- The verifier's lookahead check still compares against `datetime.now()` in some paths; the DataCollector filter is the primary guarantee.

## Alternatives Considered

### Alternative 1: Filter in each provider
Pass `as_of` into every provider method. Pro: fewer records fetched. Con: couples providers to PIT semantics; the abstract interface stays generic. Rejected — filtering in DataCollector keeps providers reusable.

### Alternative 2: Filter in the verifier only
Let future data through and rely on the fatal lookahead gate. Con: violates "Skills must not see future data"; wastes compute on filtered records. Rejected.

## Related Decisions

- [ADR-012: trace_span](012-trace-span.md)
- [ADR-006: Runtime Architecture](006-runtime-architecture.md)
