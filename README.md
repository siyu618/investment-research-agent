# Tushare Investment Research Agent

A production-grade AI agent system for automated investment research using Tushare financial data. Built as a **reference implementation** of the [engineering-ai-standards](engineering-ai-standards/) framework — demonstrating skill-based agent architecture, MCP tool integration, multi-strategy analysis, verification loops, and automated evaluation.

> ⚠️ **Disclaimer**: This system generates investment research reports for reference only. It does **not** constitute financial advice. Past performance is not indicative of future results. Always conduct your own research before making investment decisions.

---

## Architecture Overview

```
                        ┌──────────────┐
                        │    User      │
                        │ (Requirement)│
                        └──────┬───────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│                    Agent Core                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Planner → Executor → Verifier → Report Generator   │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │  Memory System (Working / Episodic / Semantic) │   │  │
│  │  └──────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│  Skills Layer (Fundamental · Technical · Valuation · Risk)│
│  Each skill: SKILL.md + analyzer.py + eval/ + examples/   │
└───────────────────────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────┐
│  MCP Layer (Tushare Data · Market Cache · Backtest Engine)│
└───────────────────────────────────────────────────────────┘
                               │
                               ▼
                        ┌───────────────┐
                        │   Tushare API │
                        └───────────────┘
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Agent Pattern** | Orchestrated + ReAct Hybrid | Structured workflow with flexible ReAct loops per skill |
| **Skill System** | Per-skill modules (eng-ai-standards format) | Independent versioning, evaluation, and replacement |
| **Memory** | Three-tier (Working/Episodic/Semantic) | In-memory dict + SQLite + Markdown files |
| **Data Access** | MCP Server over Tushare API | Standardized tool discovery, validation, and observability |
| **Evaluation** | Dual-track (Strategy + Agent Quality) | Separates investment performance from analysis quality |

See [docs/adr/](docs/adr/) for all Architecture Decision Records.

---

## Repository Structure

```
tushare-investment-agent/
├── agent/                          # Agent core components
│   ├── planner.py                  # Requirement → analysis plan
│   ├── executor.py                 # Plan execution & skill orchestration
│   ├── memory.py                   # Three-tier memory manager
│   ├── verifier.py                 # Multi-phase verification
│   ├── report_generator.py         # Investment report generation
│   ├── registry.py                 # Skill registry loader
│   └── __main__.py                 # CLI entry point
│
├── strategies/                     # Investment analysis skills
│   ├── base/models.py              # Shared interfaces & data models
│   ├── fundamental-analysis/       # Fundamental analysis skill
│   ├── technical-analysis/         # Technical analysis skill
│   ├── valuation-analysis/         # Valuation analysis skill
│   ├── risk-analysis/              # Risk analysis skill
│   └── portfolio-selection/        # Portfolio selection skill
│
├── tools/                          # MCP servers & data tools
│   ├── tushare-mcp/                # Tushare API MCP server
│   ├── market-data/                # Local data cache
│   └── backtest/                   # Backtesting engine
│
├── workflows/                      # Workflow definitions
│   ├── investment-research.md      # End-to-end research workflow
│   ├── portfolio-review.md         # Portfolio review workflow
│   └── stock-selection.md          # Stock screening workflow
│
├── evaluations/                    # Evaluation cases
│   ├── strategy-score/             # Strategy performance evaluation
│   ├── agent-quality/              # Agent output quality evaluation
│   └── historical-backtest/        # Historical strategy backtesting
│
├── registry/skills.yaml            # Central skill registry
│
├── memory/                         # Long-term semantic memory
│   ├── short-term/                 # Per-session working memory
│   └── long-term/                  # Cross-session knowledge
│
├── reports/                        # Generated investment reports
│
├── docs/
│   ├── design.md                   # Full system design document
│   └── adr/                        # Architecture Decision Records
│       ├── 001-agent-architecture.md
│       ├── 002-skill-system.md
│       ├── 003-memory-architecture.md
│       ├── 004-mcp-integration.md
│       └── 005-evaluation-framework.md
│
├── tests/                          # Test suite
├── requirements.txt                # Python dependencies
└── CLAUDE.md                       # Project instructions
```

---

## Agent Components

### Planner

Decomposes natural language investment requirements into structured analysis plans.

**Input:** User requirement (e.g., "Find investment opportunities under medium risk preference")
**Output:** `AnalysisPlan` with objective, strategy weights, data requirements, and ordered analysis steps

### Executor

Carries out the analysis plan by invoking skills and MCP tools. Handles step dependencies, parallel execution, retries, and partial results.

- Topological sort by step dependencies
- In-order execution with parallelism for independent steps
- Each skill runs in a ReAct loop (Think → Act → Observe) using MCP tools
- Configurable max retries (default: 2) and per-step timeout (default: 30s)

### Memory System

Three-tier memory following the [engineering-ai-standards memory policy](engineering-ai-standards/runtime/memory-policy.md):

| Tier | Storage | Contents | Persistence |
|------|---------|----------|-------------|
| Working | Python dict | Current session context, intermediate results | Volatile (per-session) |
| Episodic | SQLite | Session history, tool calls, previous analyses | Persistent |
| Semantic | Markdown files | Recommendations, preferences, evaluation history | Persistent, git-tracked |

### Verifier

Multi-phase verification before report generation:

1. **Data completeness** — All expected data points present; financials from expected period; prices physically reasonable
2. **Strategy consistency** — Scores internally coherent; assigned weights match executed analysis
3. **Risk validation** — Every recommendation has risk warnings; high-risk positions flagged
4. **Historical alignment** (optional) — Strategy performs consistently in backtests

### Report Generator

Template-driven report generation with structured markdown output.

---

## Skills

Each investment strategy is a skill module following the engineering-ai-standards format:

```
strategies/<name>/
├── SKILL.md           # LLM-readable instructions
├── metadata.yaml      # Machine-readable registry metadata
├── analyzer.py        # Python analysis implementation
├── prompt.md          # LLM prompt template
├── examples/          # Example inputs/outputs
├── eval/              # Evaluation cases
└── CHANGELOG.md       # Version history with backtest results
```

### Available Skills

| Skill | Purpose | Key Metrics | Default Weight |
|-------|---------|-------------|:------:|
| **fundamental-analysis** | Financial health & business quality | Revenue growth, ROE, debt ratio, cash flow, industry position | 40% |
| **technical-analysis** | Price trends & momentum | Trend, MA crossovers, volume, RSI, MACD | 20% |
| **valuation-analysis** | Fair value assessment | PE, PB, PEG, historical percentile, peer comparison | 20% |
| **risk-analysis** | Downside & volatility | Volatility, max drawdown, liquidity, beta | 20% |
| **portfolio-selection** | Composite scoring & ranking | Composite score, diversification, sector exposure | Orchestration |

---

## Workflows

### Investment Research

```
User Requirement → Plan → Collect Data → Analyze (×4 in parallel) → Combine → Verify → Report
```

The primary workflow. Given a user's investment requirement, the agent conducts full-spectrum analysis and produces a structured report.

### Portfolio Review

```
Existing Holdings → Risk Analysis → Performance Analysis → Rebalance Recommendation → Report
```

Analyze an existing portfolio, identify risks, evaluate performance, and suggest rebalancing.

### Stock Selection

```
Screening Criteria → Market Scan → Filter → Detailed Analysis → Rank → Report
```

Screen stocks by user-defined criteria, then perform detailed analysis on top candidates.

---

## MCP Tools

The Tushare MCP Server exposes these tools to the agent:

| Tool | Description | Read/Write |
|------|-------------|:----------:|
| `get_stock_basic` | List stocks by market/industry | Read |
| `get_daily_price` | Daily OHLCV price data | Read |
| `get_trade_calendar` | Trading calendar dates | Read |
| `get_income_statement` | Income statement data | Read |
| `get_balance_sheet` | Balance sheet data | Read |
| `get_cashflow` | Cash flow statement data | Read |
| `get_money_flow` | Capital flow data | Read |
| `get_holder_change` | Major holder changes | Read |
| `get_market_index` | Market index OHLCV | Read |

All tools are **read-only** — no write operations are exposed to the agent.

---

## Evaluation Framework

The system implements a **dual-track evaluation**:

### Track 1: Strategy Performance

Objective backtest-based evaluation using historical data:

| Metric | Description |
|--------|-------------|
| **Return** | Total and annualized return |
| **Max Drawdown** | Maximum peak-to-trough decline |
| **Sharpe Ratio** | Risk-adjusted return |
| **Win Rate** | Percentage of profitable periods |

### Track 2: Agent Quality

Evaluation of analytical output quality:

| Dimension | Weight | Criteria |
|-----------|--------|----------|
| Correctness | 30% | Data accuracy, calculation validity, no hallucinated metrics |
| Completeness | 25% | All dimensions covered, data sources cited, risks documented |
| Reasoning Quality | 20% | Logical flow, trade-offs acknowledged, assumptions stated |
| Risk Awareness | 15% | Risks identified, severity assessed, mitigation suggested |
| Explainability | 10% | Scores traceable to data, reasoning human-readable |

Evaluation cases follow the engineering-ai-standards [evaluation case schema](engineering-ai-standards/evaluations/schema.yaml) and reuse the [evaluation runner](engineering-ai-standards/evaluations/runner/evaluator.py).

---

## Getting Started

### Prerequisites

- Python 3.11+
- Tushare API token ([register here](https://tushare.pro/register?reg=124432))
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/tushare-investment-agent.git
cd tushare-investment-agent

# Install dependencies
pip install -r requirements.txt

# Set Tushare token
export TUSHARE_TOKEN=your_token_here
```

### Running

```bash
# Run research for a specific requirement
python -m agent --requirement "Find investment opportunities under medium risk preference"

# Interactive mode
python -m agent --interactive

# Portfolio review
python -m agent --workflow portfolio-review --portfolio portfolio.json
```

### Development

```bash
# Run tests
pytest tests/

# Run evaluation cases
python -m evaluations.runner.evaluator --case fundamental-analysis-v1

# Validate skill registry
python -m evaluations.runner.run --registry registry/skills.yaml
```

---

## Example User Scenarios

### Scenario 1: Value Investment Research

> **User:** "Find undervalued stocks in the SSE 180 with strong fundamentals and low risk."

**Agent Process:**
1. Planner classifies as value investment with low risk preference
2. Strategy weights: Fundamental 45%, Valuation 25%, Technical 10%, Risk 20%
3. Data collection: SSE 180 constituents → financials → prices
4. Fundamental analysis: screens for ROE > 15%, debt < 50%, positive cash flow
5. Valuation analysis: screens for PE < industry average, PB < 1.5
6. Risk analysis: volatility < 30%, liquidity > 10M daily volume
7. Portfolio selection: ranks candidates, produces top-5 recommendations
8. Verification: checks data completeness, strategy consistency
9. Report generated with full analysis

### Scenario 2: Portfolio Review

> **User:** "Review my portfolio: 000001.SZ (30%), 600519.SH (40%), 300750.SZ (30%). Medium risk."

### Scenario 3: Growth Stock Screening

> **User:** "Find growth stocks in the tech sector with revenue growth > 20% and reasonable PE."

---

## Evaluation Design

### Strategy Performance Evaluation

```yaml
evaluation:
  strategy: value-investing
  period: 2020-2025
  universe: CSI 300
  metrics:
    return: 12.5%
    max_drawdown: -15.3%
    sharpe_ratio: 0.85
    win_rate: 68%
```

### Agent Quality Evaluation

```yaml
evaluation:
  case: fundamental-analysis-v1
  skill: fundamental-analysis
  scoring:
    correctness: 85/100
    completeness: 80/100
    reasoning_quality: 78/100
    risk_awareness: 72/100
    explainability: 75/100
  overall: 79/100
```

---

## Future Improvements

| Area | Improvement | Priority |
|------|-------------|----------|
| **LLM Integration** | Wire up actual LLM (GPT-4/Claude) for Planner, Verifier, and skill execution | P0 |
| **Tushare MCP** | Implement full MCP server with live API connection | P0 |
| **Backtest Engine** | Full backtesting with transaction costs and slippage | P1 |
| **Vector Memory** | Embedding-based semantic search for memory retrieval | P2 |
| **Multi-user** | Session management and per-user memory isolation | P2 |
| **Web UI** | Streamlit/Gradio interface for interactive reports | P2 |
| **CI Pipeline** | GitHub Actions for evaluation regression detection | P1 |
| **More Strategies** | Momentum, dividend, quantitative factor strategies | P2 |
| **NLP Sentiment** | News sentiment analysis as additional signal | P3 |
| **Real-time Data** | WebSocket connection for live market data | P3 |

---

## Related Documents

- [System Design Document](docs/design.md) — Full architecture, data flow, and design decisions
- [ADR-001: Agent Architecture](docs/adr/001-agent-architecture.md) — Why Orchestrated + ReAct hybrid
- [ADR-002: Skill System](docs/adr/002-skill-system.md) — Why per-skill modules
- [ADR-003: Memory Architecture](docs/adr/003-memory-architecture.md) — Why three-tier memory
- [ADR-004: MCP Integration](docs/adr/004-mcp-integration.md) — Why MCP for data access
- [ADR-005: Evaluation Framework](docs/adr/005-evaluation-framework.md) — Why dual-track evaluation
- [engineering-ai-standards](engineering-ai-standards/) — The framework this project extends

---

## License

MIT

## Acknowledgments

- [Tushare Pro](https://tushare.pro/) for providing Chinese financial market data
- [engineering-ai-standards](engineering-ai-standards/) for the agent architecture framework
- [Model Context Protocol](https://modelcontextprotocol.io/) for the tool integration standard
