#!/usr/bin/env bash
# Agentic Investment Research Platform — full capability demo
#
# Runs the platform's key features back-to-back so an interviewer can see:
#   1. Dynamic Planning  — planner decomposes a goal, not a fixed template
#   2. Unified Runtime   — create_task → plan → schedule → execute → report
#   3. MCP Tool Ecosystem — ToolRegistry with capability metadata
#   4. RAG Knowledge Layer — store + recall prior research (company/industry)
#   5. Memory            — cross-session knowledge accumulation
#   6. Evaluation        — AgentRunStats + trajectory scorecard
#   7. Observability     — full chain + Mermaid graph + JSONL trace
#   8. Deterministic Replay — replay a run with the Provider forbidden
#
# Usage:
#   bash demo/run_demo.sh            # full demo
#   bash demo/run_demo.sh quick      # minimal (single run + replay)

set -euo pipefail
cd "$(dirname "$0")/.."

QUICK="${1:-full}"

say() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }

say "Agentic Investment Research Platform — Demo"

# ── 1. Dynamic Planning + Unified Runtime (single run) ──────────────────
say "[1/8] Dynamic Planning + Unified AgentRuntime"
python -m agent --requirement "分析 600519.SH 投资价值" --reuse-memory

if [ "$QUICK" = "quick" ]; then
  say "[done] quick demo — run + replay only"
  LATEST=$(ls -td runs/run-* | head -1)
  say "[quick] Deterministic Replay"
  python -m agent --replay "$LATEST"
  exit 0
fi

# ── 2. RAG Knowledge Layer — recall the stored research ──────────────────
say "[2/8] RAG Knowledge Layer — prior research is recalled (公司: 600519.SH)"
python -m agent --requirement "重新评估 600519.SH 的基本面" --reuse-memory

# ── 3. Industry-level accumulation ──────────────────────────────────────
say "[3/8] Industry knowledge accumulates (行业: 白酒)"
python -m agent --requirement "对比分析白酒行业龙头" --reuse-memory

# ── 4. Evaluation — trajectory scorecard on the latest run ──────────────
LATEST=$(ls -td runs/run-* | head -1)
say "[4/8] Evaluation — trajectory scorecard ($LATEST)"
python -m agent --eval-trajectory "$LATEST"

# ── 5. Observability — the run's artifacts ──────────────────────────────
say "[5/8] Observability — run artifacts"
echo "  agent_trace.jsonl: $(wc -l < "$LATEST/agent_trace.jsonl") spans"
echo "  execution_graph.mmd: $(wc -l < "$LATEST/execution_graph.mmd") lines (Mermaid)"
echo "  stats: $(python3 -c "import json; s=json.load(open('$LATEST/meta.json'))['stats']; print(f'task_success={s[\"task_success_rate\"]}, tool_success={s[\"tool_success_rate\"]}, latency={s[\"latency_ms\"]}ms, evidence={s[\"evidence_count\"]}')")"

# ── 6. Screening (multi-stock) on the unified runtime ────────────────────
say "[6/8] Multi-stock screening (dynamic plan → 52 tool calls)"
python -m agent --requirement "从沪深300筛选基本面稳健、估值合理的5只股票"

# ── 7. Deterministic Replay ─────────────────────────────────────────────
SAVE=$(ls -td runs/run-* | head -1)
say "[7/8] Deterministic Replay — Provider forbidden, hashes compared ($SAVE)"
python -m agent --replay "$SAVE"

# ── 8. Interactive pointer ──────────────────────────────────────────────
say "[8/8] Interactive mode"
echo "  python -m agent --interactive --reuse-memory"

say "Demo complete. See README.md for the full platform story."
