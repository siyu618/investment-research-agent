# Workflow: Stock Selection

**Version:** 1.0.0
**Composes Skills:** planner, data-collection, screening, fundamental-analysis, valuation-analysis, portfolio-selection, report-generator
**Trigger:** User wants to screen for stocks matching specific criteria

## Workflow Description

Screen and filter stocks based on user-defined criteria (industry, market cap, valuation range, technical setup) then perform detailed analysis on screened candidates.

## Steps

### 1. Screening Criteria

Parse user's screening criteria:
- Market (SSE/SZSE/BJSE)
- Industry sector
- Market cap range
- Valuation filters (PE range, PB range)
- Technical filters (MA cross, RSI range)

### 2. Market Scan

Query Tushare for all stocks matching criteria. Apply filters to narrow list.

### 3. Preliminary Screening

Apply basic financial filters to the screened list:
- Minimum revenue growth
- Positive net profit (last 2 periods)
- Minimum trading volume

### 4. Detailed Analysis

For top candidates from screening:
- Fundamental analysis
- Valuation analysis
- Risk assessment

### 5. Selection & Report

Rank analyzed candidates, select top N (configurable), generate selection report with rationale.
