# Workflow: Portfolio Review

**Version:** 1.0.0
**Composes Skills:** risk-analysis, fundamental-analysis, technical-analysis, portfolio-selection, report-generator
**Trigger:** User submits an existing portfolio for review

## Workflow Description

Analyze an existing portfolio's risk profile, performance characteristics, and generate rebalance recommendations.

## Steps

### 1. Portfolio Loading

Load the user's existing holdings (stock codes, position sizes).

### 2. Risk Analysis (per position)

For each holding, analyze risk profile:
- Volatility and beta
- Maximum drawdown
- Liquidity assessment
- Concentration risk relative to portfolio

### 3. Performance Analysis (per position)

For each holding, analyze performance:
- Return over multiple periods (1m, 3m, 6m, 1y)
- Benchmark-relative performance
- Fundamental health assessment (if financial data available)

### 4. Rebalance Recommendation

Aggregate per-position analysis and generate rebalance suggestions:
- Positions to increase (high score, low current weight)
- Positions to reduce (low score, high current weight)
- Positions to exit (high risk, poor performance)
- Suggested new positions (diversification, score improvement)

### 5. Report Generation

Generate portfolio review report with current state, risk profile, and rebalance recommendations.
