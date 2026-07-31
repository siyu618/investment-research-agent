# Reproducible Evaluation Cases

Three end-to-end scenarios that exercise the full research pipeline.
Each case keeps a complete record: input, plan, tool calls, data snapshot,
verification, and final report (see `runs/{run_id}/` after running).

## Case 1 — Single Stock Research

- **Command:** `python -m agent --requirement "分析 600519.SH"`
- **Input:** single stock code
- **Expected:** Planner detects `600519.SH`, focuses data collection on that
  stock, and produces a focused report.

## Case 2 — Conditional Screening

- **Command:** `python -m agent --requirement "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"`
- **Input:** natural language screening criteria
- **Expected:** Planner classifies objective/risk, ranks candidates, returns top 5.

## Case 3 — Portfolio Review

- **Command:** `python -m agent --requirement "组合诊断：平安银行、招商银行、贵州茅台，分析持仓风险"`
- **Input:** named holdings + risk review intent
- **Expected:** risk + valuation + fundamental analysis per holding.

## How to verify a case

```bash
# Run the case
python -m agent --requirement "..." --output /tmp/reports

# Inspect the run record
ls runs/$(ls -t runs/ | head -1)/
cat runs/$(ls -t runs/ | head -1)/plan.json        # structured plan
cat runs/$(ls -t runs/ | head -1)/tool_trace.jsonl # every tool call
cat runs/$(ls -t runs/ | head -1)/data_snapshot.json # point-in-time data
cat runs/$(ls -t runs/ | head -1)/report.md        # final report
```

> Note: runs use the Mock provider by default. To use real Tushare data,
> set `TUSHARE_TOKEN` and pass `--provider tushare`.
