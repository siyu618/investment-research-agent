# Evaluations

This project separates evaluation into two distinct tracks, because
"is the agent behaving well?" and "is the strategy profitable?" are
different questions with different methods.

## 1. Agent Execution Quality (implemented)

Measures **how well the agent performs** the research task, independent
of whether the picks make money.

| Dimension | Weight | What it checks |
|-----------|--------|----------------|
| Correctness | 30% | Data accuracy, calculation validity, no hallucinated metrics |
| Completeness | 25% | All dimensions covered, data sources cited, risks documented |
| Reasoning Quality | 20% | Logical flow, trade-offs acknowledged, assumptions stated |
| Risk Awareness | 15% | Risks identified, severity assessed, mitigation suggested |
| Explainability | 10% | Scores traceable to data, reasoning human-readable |

Existing cases: `agent-quality/*.yaml`, `trajectory/*.yaml`.

## 2. Investment Strategy Quality (EXPERIMENTAL)

Measures **whether the strategy produces good returns**. This track is
**experimental** because we do not yet enforce strict point-in-time data,
transaction costs, slippage, trading halts, price-limit days, delistings,
or survivorship bias. Any backtest output is illustrative only.

| Metric | Meaning |
|--------|---------|
| Return | Total / annualized return |
| Max Drawdown | Peak-to-trough decline |
| Sharpe Ratio | Risk-adjusted return |
| Win Rate | Fraction of positive periods |

**Status: NOT production-ready.** Do not draw investment conclusions from
`historical-backtest/` or `strategy-score/` outputs. They exist to
demonstrate the evaluation framework, not to validate real strategies.

### Backtest engine interface (reserved, experimental)

`tools/backtest/engine.py` provides a `BacktestEngine` that computes the
standard metrics (return / annualized / max drawdown / Sharpe / win rate)
from signal + price series, plus a `cost_bps` parameter.

The interface is **reserved for strict backtesting**, but the current
implementation is **explicitly experimental**:
- It models no transaction costs beyond a flat basis-point deduction
- No slippage, trading halts, price-limit days, delistings, or
  survivorship-bias handling
- No point-in-time data enforcement

Every `BacktestResult` carries `experimental: true` so consumers cannot
mistake it for a production backtest. Complete these preconditions before
treating any backtest output as investment-relevant.

## Reproducible end-to-end cases

See [cases/README.md](cases/README.md) for three runnable scenarios that
exercise the full pipeline (single-stock, screening, portfolio review).
