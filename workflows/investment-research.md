# Workflow: Investment Research

**Version:** 1.0.0
**Composes Skills:** planner, fundamental-analysis, technical-analysis, valuation-analysis, risk-analysis, portfolio-selection, verifier, report-generator
**Trigger:** User submits an investment research requirement

## Workflow Description

End-to-end investment research process. Given a user's investment requirement (e.g., "Find investment opportunities under medium risk preference"), the agent:

1. Analyzes the requirement to extract strategy weights and risk preference
2. Collects market data via Tushare MCP tools
3. Runs multi-strategy analysis in parallel (fundamental, technical, valuation, risk)
4. Combines scores into composite ranking
5. Verifies results for completeness, consistency, and risk awareness
6. Generates a structured investment research report

## Steps

### 1. Requirement Analysis

**Skill:** planner
**Input:** User's natural language requirement
**Output:** AnalysisPlan (objective, strategy_weights, data_requirements, analysis_steps, risk_preference)

**Process:**
1. Parse user requirement
2. Classify investment style (value/growth/momentum/dividend/mixed)
3. Determine risk preference from language cues
4. Assign strategy weights based on style and preference
5. Generate ordered analysis plan with step dependencies
6. Present plan to user for confirmation (optional)

### 2. Data Collection

**Skill:** executor (data)
**Input:** Data requirements from plan
**Output:** Market data context (stock list, prices, financials)

**Process:**
1. Query Tushare for stock basics (filtered by market/industry)
2. Fetch income statements, balance sheets, cash flows for target stocks
3. Fetch daily price data for the analysis period
4. Fetch market index data for context
5. Cache results in local market data cache
6. Log data freshness indicators

### 3. Fundamental Analysis (parallel)

**Skill:** fundamental-analysis
**Input:** Stock + financial data + market context
**Output:** AnalysisResult (score, reasoning, risk_factors)

**Process:**
1. Analyze revenue growth trends (3-5 periods)
2. Analyze profitability (gross margin, net margin, ROE, ROA)
3. Analyze financial health (debt ratio, current ratio, cash flow)
4. Analyze efficiency (asset turnover)
5. Assess industry position and competitive advantages
6. Compute weighted fundamental score
7. Identify risk factors and data quality warnings

### 4. Technical Analysis (parallel)

**Skill:** technical-analysis
**Input:** Stock + daily price data
**Output:** AnalysisResult (score, reasoning, risk_factors)

**Process:**
1. Analyze trend direction and strength
2. Analyze moving average relationships (MA20, MA50, MA200)
3. Analyze volume patterns and confirmation
4. Analyze momentum (RSI, MACD)
5. Compute weighted technical score
6. Identify technical risk factors

### 5. Valuation Analysis (parallel)

**Skill:** valuation-analysis
**Input:** Stock + financial data + price data
**Output:** AnalysisResult (score, reasoning, risk_factors)

**Process:**
1. Calculate PE, PB, PEG, PS ratios
2. Compare to 3-year historical percentiles
3. Compare to industry averages
4. Assess growth-adjusted valuation
5. Compute weighted valuation score
6. Flag overvalued/undervalued signals

### 6. Risk Analysis (parallel)

**Skill:** risk-analysis
**Input:** Stock + price data
**Output:** AnalysisResult (score, reasoning, risk_factors)

**Process:**
1. Calculate daily and annualized volatility
2. Calculate beta vs market index
3. Calculate maximum drawdown and recovery time
4. Analyze liquidity (volume, turnover)
5. Assess concentration risks
6. Compute weighted risk score (higher = safer)

### 7. Portfolio Selection

**Skill:** portfolio-selection
**Input:** All analysis results from steps 3-6
**Output:** AnalysisResult (composite_score, ranking, portfolio_suggestion)

**Process:**
1. Apply strategy weights from plan
2. Compute composite scores for all candidates
3. Rank candidates into tiers (strong buy, watch, not recommended)
4. Build portfolio suggestion with position sizing
5. Identify portfolio-level risks (concentration, sector exposure)
6. Score and output composite recommendation

### 8. Verification

**Skill:** verifier
**Input:** Analysis plan + all results
**Output:** VerificationResult (passed, checks, warnings, errors)

**Process:**
1. Check data completeness (all expected data present?)
2. Check strategy consistency (scores internally coherent?)
3. Check risk validation (all recommendations have risk warnings?)
4. If any check fails: log gap, return to relevant step, re-verify
5. If all pass: proceed to report generation

### 9. Report Generation

**Skill:** report-generator
**Input:** All results + verification
**Output:** InvestmentReport (structured markdown)

**Process:**
1. Assemble market overview section
2. Compile candidate analyses with scores and reasoning
3. Build portfolio suggestion section
4. Include disclaimer
5. Format as structured markdown report
6. Output to console and/or save to reports/ directory

## Data Flow

```
User Requirement
    │
    ▼
┌──────────────────────┐
│ Requirement Analysis │  →  AnalysisPlan
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   Data Collection    │  →  MarketDataContext
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Fund    │ │ Tech    │ │ Val     │ │ Risk    │
│ Analysis│ │ Analysis│ │ Analysis│ │ Analysis│
└────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     │           │           │           │
     └───────────┴─────┬─────┴───────────┘
                       │
                       ▼
┌──────────────────────────┐
│  Portfolio Selection     │  →  Composite Ranking
└─────────────┬────────────┘
              │
              ▼
┌──────────────────────────┐
│  Verification            │  →  Pass/Fail + Warnings
└─────────────┬────────────┘
              │
              ▼
┌──────────────────────────┐
│  Report Generation       │  →  Markdown Report
└──────────────────────────┘
```

## Error Handling

| Error | Action | Retry? |
|-------|--------|--------|
| Tushare API rate limit | Wait 30s, retry | Yes (3x) |
| Missing financial data | Skip stock, log warning | No |
| LLM parse failure | Re-prompt with stricter format | Yes (2x) |
| Skill timeout (>30s) | Mark step failed, continue | No |

## Configuration

```yaml
workflow: investment-research
version: 1.0.0
max_parallel_skills: 4
max_retries_per_step: 2
verification_required: true
report_format: markdown
```
