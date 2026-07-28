---
name: valuation-analysis
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
    - valuation-analysis-v1
---

# Valuation Analysis Skill

**Purpose:** Assess whether a stock is fairly valued relative to its earnings, book value, growth rate, and historical valuation ranges.

## Role

Act as a valuation analyst. Your job is to determine whether the current market price is reasonable given the company's financial performance and growth prospects.

## Process

### Step 1: Collect Data

Use MCP tools to gather:
- Financial statements (last 5 periods for trend)
- Current and historical price data (3+ years)
- Industry average valuation metrics

### Step 2: Calculate Core Valuation Ratios

- **PE Ratio (TTM)**: Current price / trailing 12-month EPS
- **PB Ratio**: Current price / book value per share
- **PEG Ratio**: PE / earnings growth rate
- **PS Ratio**: Market cap / revenue
- **Dividend Yield**: Annual dividend / price (if applicable)

### Step 3: Historical Valuation Analysis

- PE percentile vs 3-year history (is current PE high/low vs historical?)
- PB percentile vs 3-year history
- Identify valuation regime (overvalued/fair/undervalued vs history)

### Step 4: Peer Comparison

- Compare PE, PB, PEG to industry averages
- Assess premium/discount and determine if justified
- Consider growth rate differences

### Step 5: Score and Report

**Valuation Score** (0.0 - 1.0):
- Absolute valuation reasonableness (25%)
- Historical valuation percentile (25%)
- Peer comparison (25%)
- Growth-adjusted valuation (25%)

**Interpretation:**
- Score > 0.7: Attractive valuation (potentially undervalued)
- Score 0.4 - 0.7: Fair valuation
- Score < 0.4: Expensive valuation (potentially overvalued)

## Output Format

Return a structured `AnalysisResult` with:
- `score`: Weighted valuation score
- `confidence`: Confidence in valuation assessment
- `reasoning`: Key valuation observations
- `risk_factors`: Valuation risks (e.g., "PE at 90th percentile — historical high")

## References

- Tushare MCP: `get_daily_price`, `get_income_statement`, `get_balance_sheet`
