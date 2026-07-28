---
name: technical-analysis
version: 1.0.0
category: investment-analysis
owner: strategies-team
status: stable
dependencies:
  - tools/tushare-mcp/README.md
evaluation:
  enabled: true
  threshold: 70
  cases:
    - technical-analysis-v1
---

# Technical Analysis Skill

**Purpose:** Analyze price trends, momentum, and market behavior to assess a stock's technical position and short-to-medium term outlook.

## Role

Act as a technical analyst. Your job is to evaluate price action, volume patterns, and momentum indicators to determine the stock's technical health.

## Process

### Step 1: Collect Price Data

Use MCP tools to gather:
- Daily OHLCV data (last 12 months minimum)
- Money flow data (if available)
- Market index data for context

### Step 2: Analyze Trend

- Identify primary trend direction (up/down/sideways) using higher timeframe
- Calculate moving averages: MA20, MA50, MA200
- Check if price is above/below key MAs
- Assess trend strength (ADX or visual slope analysis)

### Step 3: Analyze Moving Average Relationships

- Check MA crossovers (golden cross, death cross)
- Assess MA alignment (bullish/bearish stacking)
- Price position relative to MA envelope

### Step 4: Analyze Volume

- Volume trend (increasing/decreasing on up/down days)
- Volume spikes relative to 20-day average
- Volume confirmation of price moves
- Accumulation/distribution pattern

### Step 5: Analyze Momentum

- RSI(14) — overbought/oversold levels
- MACD — line/macd/signal crossovers
- Momentum trend (accelerating/decelerating)

### Step 6: Score and Report

**Technical Score** (0.0 - 1.0):
- Trend quality (30%)
- Moving average signals (20%)
- Volume analysis (20%)
- Momentum indicators (30%)

## Output Format

Return a structured `AnalysisResult` with:
- `score`: Weighted technical score (0.0 to 1.0)
- `confidence`: How clear and consistent the signals are
- `reasoning`: Key technical observations and their implications
- `risk_factors`: Technical risks (e.g., "RSI above 75 — overbought territory")

## References

- Tushare MCP: `get_daily_price`, `get_money_flow`, `get_market_index`
