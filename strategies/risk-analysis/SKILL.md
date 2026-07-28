---
name: risk-analysis
version: 1.0.0
category: investment-analysis
owner: strategies-team
status: stable
dependencies:
  - tools/tushare-mcp/README.md
evaluation:
  enabled: true
  threshold: 75
  cases:
    - risk-analysis-v1
---

# Risk Analysis Skill

**Purpose:** Quantify downside risk, volatility, liquidity, and concentration exposure of a stock or portfolio.

## Role

Act as a risk analyst. Your job is to assess the risk profile of an investment by analyzing price volatility, drawdown history, liquidity metrics, and concentration risk.

## Process

### Step 1: Collect Data

Use MCP tools to gather:
- Daily price data (last 2+ years for meaningful risk metrics)
- Trading volume data
- Holder/structure data
- Market index data for beta calculation

### Step 2: Analyze Volatility

- **Daily Volatility**: Standard deviation of daily returns
- **Annualized Volatility**: Daily vol × sqrt(252)
- **Beta**: Correlation of stock returns to market returns
- Compare volatility to industry and market averages

### Step 3: Analyze Drawdown

- **Maximum Drawdown**: Largest peak-to-trough decline over 2 years
- **Recovery Time**: How long did recovery take after max drawdown?
- **Drawdown Frequency**: How often do -10%+ drawdowns occur?
- Compare drawdown profile to peers

### Step 4: Analyze Liquidity

- **Average Daily Volume**: 3-month average
- **Volume Liquidity**: Average daily amount (CNY)
- **Turnover Ratio**: Daily volume / outstanding shares
- Flag low-liquidity concerns (daily volume < threshold)

### Step 5: Analyze Concentration Risk

- Holder concentration (if data available)
- Sector concentration (correlation to sector index)
- Single-stock concentration in portfolio context

### Step 6: Score and Report

**Risk Score** (0.0 - 1.0):
- Volatility assessment (30%)
- Drawdown assessment (30%)
- Liquidity assessment (20%)
- Concentration risk (20%)

**Interpretation:**
- Score > 0.7: Low risk profile
- Score 0.4 - 0.7: Moderate risk profile
- Score < 0.4: High risk profile

Note: Unlike other scores, **higher risk score = LOWER risk** (the score measures safety).

## Output Format

Return a structured `AnalysisResult` with:
- `score`: Safety score (0.0 = highest risk, 1.0 = lowest risk)
- `confidence`: Confidence based on data sufficiency
- `reasoning`: Key risk factors and their implications
- `risk_factors`: Specific risk warnings (e.g., "Max drawdown -45% over 6 months")

## References

- Tushare MCP: `get_daily_price`, `get_stock_basic`, `get_market_index`
