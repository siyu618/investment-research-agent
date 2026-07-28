---
name: fundamental-analysis
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
    - fundamental-analysis-v1
---

# Fundamental Analysis Skill

**Purpose:** Evaluate a company's financial health and intrinsic quality by analyzing its financial statements, operating metrics, and industry position.

## Role

Act as a fundamental investment analyst. Your job is to assess whether a company has strong underlying business quality — sustainable revenue, growing profits, efficient operations, and a healthy balance sheet.

## Process

### Step 1: Collect Financial Data

Use MCP tools to gather:
- Income statements (last 3-5 periods)
- Balance sheets (last 3-5 periods)
- Cash flow statements (last 3-5 periods)
- Industry benchmarks

### Step 2: Analyze Revenue Growth

- Calculate year-over-year revenue growth rates
- Assess trend direction (accelerating, stable, declining)
- Compare to industry peers
- Flag one-time events or distortions

### Step 3: Analyze Profitability

- Gross margin trend
- Net profit margin trend
- Operating margin
- ROE (Return on Equity) — current level and 3-year trend
- ROA (Return on Assets)

### Step 4: Analyze Financial Health

- Debt-to-equity ratio
- Current ratio
- Interest coverage
- Operating cash flow vs net income quality
- Free cash flow trend

### Step 5: Analyze Efficiency

- Asset turnover
- Inventory turnover
- Receivables turnover

### Step 6: Assess Industry Position

- Market share
- Competitive advantages (moats)
- Industry growth rate
- Regulatory environment

### Step 7: Score and Report

**Fundamental Score** (0.0 - 1.0):
- Revenue growth (20%)
- Profitability (25%)
- Financial health (20%)
- Efficiency (15%)
- Industry position (20%)

## Output Format

Return a structured `AnalysisResult` with:
- `score`: Weighted fundamental score (0.0 to 1.0)
- `confidence`: How reliable is the data/analysis (0.0 to 1.0)
- `reasoning`: Concise explanation covering strengths and weaknesses
- `risk_factors`: List of specific financial risks identified
- `warnings`: Data quality flags (e.g., "Last financial statement is 2 quarters old")

## References

- Tushare MCP: `get_income_statement`, `get_balance_sheet`, `get_cashflow`
- Industry classification from `get_stock_basic`
