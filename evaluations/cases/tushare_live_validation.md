# Tushare Live Validation

Real-account verification of the Tushare provider (2026-07-31).

## Account limits discovered

| Interface | Status | Note |
|-----------|--------|------|
| `daily` (行情) | ✅ Working | Free tier, real OHLCV |
| `daily_basic` (PE/PB) | ✅ Working | 1/min quota |
| `stock_basic` | ⚠️ Hourly quota | 1/hour on this account |
| `income` / `balancesheet` / `cashflow` | ❌ No permission | Requires higher points tier |

## What was verified

1. **Multi-stock daily data** — `600519.SH`, `000001.SZ`, `300750.SZ` each
   fetched real bars (e.g. 600519.SH 2025-01-15 close 1471.27).
   Redacted sample: `evaluations/cases/tushare_redacted_sample.json`.

2. **Single-stock end-to-end** (`--provider tushare`):
   - Run: `run-20260731-214419-4d7492`
   - Snapshot source = `OfficialTushareMCPProvider`
   - 485 real price bars captured for 600519.SH
   - Risk score based on real volatility/max-drawdown
   - Financial data empty (no income permission) — correctly recorded
     as degraded, not failing the run

3. **Graceful degradation**:
   - `stock_basic` hourly limit → falls back to code stubs, analysis continues
   - `income` no permission → recorded in trace as error, financials empty
   - Permission-denied errors now fail fast (no 60s retry loop)

## Redacted sample

`tushare_redacted_sample.json` contains real OHLCV rows for the three stocks
with identifiers kept (public market data), no sensitive account info.

## Limitations for this account

- Fundamental analysis (ROE / revenue growth / cash flow) cannot run on
  real data without a higher Tushare points tier.
- Real end-to-end is therefore limited to: real prices + real PE/PB +
  real risk metrics.
