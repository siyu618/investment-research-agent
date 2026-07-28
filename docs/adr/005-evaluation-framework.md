# Architecture Decision Record: Evaluation Framework

**Status:** Accepted
**Decision:** #005
**Date:** 2026-07-28

## Context

The investment research agent must be evaluated on two distinct dimensions:

1. **Strategy Performance**: Does the investment analysis produce good investment outcomes? Measured by returns, Sharpe ratio, drawdown, win rate.
2. **Agent Quality**: Does the agent perform the analysis correctly, completely, and explainably? Measured by correctness, completeness, reasoning quality, risk awareness, explainability.

These dimensions require different evaluation approaches. Strategy performance requires backtesting against historical data — an objective, quantitative measurement. Agent quality requires comparing the agent's output against expected criteria — a combination of rule-based checks and LLM-judge evaluation.

The existing engineering-ai-standards evaluation framework supports rule-based and LLM-judge evaluation but does not have investment-specific metrics (Sharpe, drawdown). We must extend it.

## Decision

**Decision:** We will implement a **dual-track evaluation framework**:

### Track 1: Strategy Performance Evaluation

Evaluation cases under `evaluations/strategy-score/` measure investment strategy performance through backtesting.

- Each evaluation case defines a strategy, a historical period, and a universe of stocks.
- The backtest engine runs the strategy against historical data.
- Metrics (return, drawdown, Sharpe, win rate) are computed from backtest results.
- Scores are numerical (0-100) with regression tracking.

### Track 2: Agent Quality Evaluation

Evaluation cases under `evaluations/agent-quality/` measure the agent's analytical output quality.

- Each evaluation case defines a task, expected output criteria, and forbidden behaviors.
- The agent is run against the task. Output is scored using:
  - Rule-based checks (must_include keywords, structure validation)
  - LLM-as-Judge for qualitative dimensions (reasoning quality, explainability)
- Dimensions follow the engineering-ai-standards scoring schema (correctness, completeness, reasoning_quality, risk_awareness, explainability) with investment-specific criteria.

Both tracks reuse the existing `evaluations/runner/evaluator.py` and `evaluations/runner/scorecard.py` from engineering-ai-standards, with extensions for investment metrics.

## Rationale

- **Dual track separates concerns**: A strategy can have high agent quality (well-reasoned analysis) but poor strategy performance (the strategy loses money), and vice versa. Both must be measured independently to improve the system.
- **Extends, doesn't replace**: The existing evaluator handles rule-based scoring and LLM-judge prompting. We extend it with investment-specific metrics rather than building a new system.
- **Backtesting provides ground truth**: Strategy performance evaluation is objective — you either made money or you didn't. This grounds the evaluation in measurable outcomes.
- **LLM-as-Judge for agent quality**: Correctness and reasoning quality are inherently subjective — an LLM judge calibrated against expert-labeled examples is the practical standard.

## Consequences

### Positive

- Detecting regressions: A SKILL.md change that improves reasoning quality but degrades backtest performance is caught before release.
- Holistic improvement tracking: Both tracks combined give a complete picture of agent quality.
- Evaluation cases are investment-domain-specific, making them meaningful to the project's stakeholders.

### Negative

- Backtest evaluation is computationally expensive (running strategies against years of daily data).
- LLM-judge evaluation has inherent bias and variance — multiple runs may give different scores.
- Dual track means more evaluation cases to maintain.

### Neutral

- Evaluation results are stored in `evaluations/` following engineering-ai-standards conventions (`latest.json`, `history.json`).
- Strategy performance evaluation requires the Backtest Engine MCP, which is Phase 4 work.

## Alternatives Considered

### Alternative 1: Single evaluation track

- **Description**: One evaluation case type that combines strategy metrics and agent quality into a single score.
- **Pros**: Simpler to manage; single score to track.
- **Cons**: Conflates two independent quality dimensions; can't tell if a score drop is from strategy or agent issues; hard to improve.
- **Why rejected**: A single score hides critical signal. If the agent starts making bad recommendations, is it because the strategy is bad or the analysis is wrong? Dual track tells you immediately.

### Alternative 2: Finance-only evaluation (backtest only)

- **Description**: Only measure strategy performance through backtesting. Ignore agent quality evaluation.
- **Pros**: Objective metrics; no LLM-judge bias.
- **Cons**: A strategy that works in backtesting may be poorly explained or incorrectly applied by the agent; no way to measure reasoning quality.
- **Why rejected**: Backtest results alone don't measure whether the agent is correctly implementing the analysis methodology.

### Alternative 3: LLM-only evaluation (no backtesting)

- **Description**: Only use LLM-judge for all evaluation dimensions, including strategy quality.
- **Pros**: No backtest infrastructure needed; faster evaluation.
- **Cons**: LLM cannot reliably predict investment returns; strategy quality is fundamentally an empirical question.
- **Why rejected**: Investment outcomes must be measured against real data. An LLM judge saying "this strategy seems good" is no substitute for a backtest.

## Related Decisions

- [ADR-002: Skill System Design](002-skill-system.md) (per-skill evaluation)
- engineering-ai-standards: `evaluations/runner/evaluator.py`, `evaluations/runner/scorecard.py`, `evaluations/schema.yaml`

## Notes

Evaluation case files are in:

```
evaluations/
├── strategy-score/
│   ├── fundamental-analysis.yaml
│   ├── technical-analysis.yaml
│   ├── valuation-analysis.yaml
│   ├── risk-analysis.yaml
│   ├── portfolio-selection.yaml
│   └── README.md
├── agent-quality/
│   ├── data-completeness.yaml
│   ├── reasoning-quality.yaml
│   ├── risk-awareness.yaml
│   └── README.md
└── historical-backtest/
    ├── value-strategy-backtest.yaml
    ├── growth-strategy-backtest.yaml
    └── README.md
```

The `strategy-score` cases evaluate the skill output (algorithm-driven scoring). The `agent-quality` cases evaluate the agent's execution (LLM-driven analysis quality). The `historical-backtest` cases evaluate end-to-end strategy performance vs historical data.
