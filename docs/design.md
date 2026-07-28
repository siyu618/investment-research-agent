# Design Document: Tushare Investment Research AI Agent

**Status:** Draft
**Author(s):** Principal AI Engineer
**Date:** 2026-07-28
**PR/FD:** TBD

## 1. Background

Investment research is a knowledge-intensive process requiring multi-source data aggregation, cross-dimensional analysis, and rigorous verification. Traditional approaches rely on manual research — analysts review financial statements, market data, technical indicators, and risk metrics independently, then synthesize conclusions. This process is slow, inconsistent across analysts, and difficult to scale.

Recent advances in LLM-based agent systems make it possible to automate portions of this workflow while maintaining the rigor and explainability required for investment decisions. However, the investment domain presents unique challenges:

- **Data latency**: market data changes in real time; stale data leads to incorrect conclusions.
- **Multi-dimensionality**: a single investment decision requires fundamental, technical, valuation, and risk analysis concurrently.
- **Verifiability**: every recommendation must be traceable to specific data points and reasoning steps.
- **Regulatory sensitivity**: investment recommendations carry legal implications; the system must clearly disclaim AI-generated advice.
- **Strategy diversity**: different investors (value, growth, momentum, dividend) require different analytical lenses.

This project builds the **Tushare Investment Research Agent** — an AI agent system that demonstrates production-grade agent architecture, skill orchestration, MCP tool integration, multi-strategy analysis, and automated evaluation — using the engineering-ai-standards framework as its foundation.

## 2. Goals

- **G1**: Design an AI agent that, given a user investment requirement, autonomously collects Tushare market data, performs multi-strategy analysis, and generates a verifiable investment research report.
- **G2**: Create a reusable skill system for investment analysis strategies (fundamental, technical, valuation, risk, portfolio selection) following the engineering-ai-standards format.
- **G3**: Implement a workflow engine that orchestrates planner → executor → verifier → report generator phases with clear observability.
- **G4**: Build an MCP server wrapping Tushare API for standardized tool access by the agent.
- **G5**: Establish an evaluation framework measuring both investment strategy performance (returns, Sharpe, drawdown) and agent quality (reasoning, correctness, risk awareness).
- **G6**: Serve as a reference implementation of the engineering-ai-standards agent runtime model — demonstrating memory, verification loops, tool policy, and evaluation in a real domain.

## 3. Non-Goals

- **NG1**: Real-time trading or trade execution. This is a research and analysis system, not a trading bot.
- **NG2**: Portfolio management with real money. The system produces recommendations only.
- **NG3**: Regulatory compliance certification. Disclaimer language is included but no financial regulatory review is performed.
- **NG4**: Coverage of all Tushare API endpoints. A representative subset sufficient for the analysis pipeline.
- **NG5**: Production deployment infrastructure (Kubernetes, monitoring stack). The project focuses on architecture and implementation, not ops.

## 4. Requirements

### Functional Requirements

| ID | Description | Priority |
|----|-------------|----------|
| FR1 | Accept natural language investment requirements from the user | P0 |
| FR2 | Collect market data from Tushare (stock basics, daily prices, financial statements) | P0 |
| FR3 | Analyze companies using multiple strategies simultaneously | P0 |
| FR4 | Generate composite investment scores with reasoning | P0 |
| FR5 | Verify results for data completeness and strategy consistency | P1 |
| FR6 | Generate structured investment research reports | P1 |
| FR7 | Support portfolio review workflow (existing holdings analysis) | P2 |
| FR8 | Maintain memory of past analyses for cross-session reference | P2 |
| FR9 | Backtest strategy performance against historical data | P2 |
| FR10 | Evaluate agent output quality against defined criteria | P1 |

### Non-Functional Requirements

| Dimension | Target | Rationale |
|-----------|--------|-----------|
| **Architecture** | Modular, skill-based, observable | Enables independent strategy evolution and debugging |
| **Extensibility** | Add new strategy in ≤1 day of dev | Strategy skills follow a fixed interface; MCP tools are self-describing |
| **Explainability** | Every recommendation traceable to data | Structured output with reasoning chains per analysis step |
| **Observability** | Every agent step, tool call, and decision logged | Required for debugging, audit, and evaluation |
| **Data Accuracy** | Market data ≤1 session stale | Tushare MCP tools load fresh data per analysis run |
| **Safety** | Clear disclaimer; no actionable trades without user confirmation | Investment advice carries legal liability |
| **Evaluation** | Automated regression suite for strategy and agent quality | Ensures changes don't degrade analytical quality |

## 5. Architecture

### 5.1 System Context

```
┌──────────────────────────────────────────────────────────────┐
│                    Investment Research Agent                   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    Agent Core                           │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ Planner  │ │ Executor │ │ Verifier │ │  Report  │  │  │
│  │  │          │ │          │ │          │ │  Gen     │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│  │                                                       │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │  │
│  │  │  Memory  │ │ Workflow │ │    Skill Registry    │  │  │
│  │  │  System  │ │  Engine  │ │ (fund/tech/val/risk) │  │  │
│  │  └──────────┘ └──────────┘ └──────────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                           │                                   │
│                           ▼                                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    MCP Layer                            │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────────┐     │  │
│  │  │ Tushare    │ │ Market     │ │ Backtest       │     │  │
│  │  │ Data MCP   │ │ Data MCP   │ │ Engine MCP     │     │  │
│  │  └────────────┘ └────────────┘ └────────────────┘     │  │
│  └────────────────────────────────────────────────────────┘  │
│                           │                                   │
└───────────────────────────┼───────────────────────────────────┘
                            │
                    ┌───────▼───────┐
                    │   Tushare     │
                    │   API Server  │
                    └───────────────┘
```

### 5.2 Components

| Component | Responsibility | Technology | Rationale |
|-----------|---------------|------------|-----------|
| **Planner** | Decompose user requirement into an analysis plan with ordered steps | Python + LLM | Separates "what to do" from "how to do it"; enables observability of the plan |
| **Executor** | Execute analysis steps by invoking skills and MCP tools | Python + LLM | Carries out the plan; handles tool calls, error recovery, retries |
| **Memory System** | Store short-term context, intermediate results, and long-term analysis history | Python (SQLite + file) | Multi-tier memory: working memory for current analysis, semantic memory for cross-session knowledge |
| **Skill Registry** | Catalog of analysis skills with metadata, versions, and evaluation status | YAML + Python | Each investment strategy is a skill — enables independent versioning, evaluation, and replacement |
| **Workflow Engine** | Orchestrate multi-step workflows (investment research, portfolio review) | Python | Composition of skills with ordering, branching, and error handling |
| **Verifier** | Check data completeness, strategy consistency, risk exposure, historical performance | Python | Verification loop before report generation catches errors |
| **Report Generator** | Produce structured investment reports from analysis results | Python + templates | Separates analysis from presentation; supports multiple output formats |
| **Tushare MCP Server** | Expose Tushare API endpoints as MCP tools | Python (MCP SDK) | Standardized tool interface; tools are self-describing with JSON Schema |
| **Market Data MCP** | Local cache and aggregation layer over Tushare data | Python (SQLite) | Reduces API calls; enables backtesting against cached historical data |
| **Backtest Engine** | Execute strategy rules against historical price/financial data | Python | Validates strategy performance before inclusion in reports |
| **Evaluation Runner** | Run evaluation cases and produce scores | Python (from eng-ai-standards) | Reuses existing evaluator/scorecard infrastructure |

### 5.3 Data Flow

**Write path (investment research):**

```
User Input
    │
    ▼
┌────────────────┐
│  Planner       │  Decompose requirement into analysis plan
│  (LLM + Plan)  │  Plan: [collect data, fund analysis, tech analysis, ...]
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  Executor      │  For each step in plan:
│  (LLM + Tools) │    - Select skill from registry
│                │    - Invoke skill → agent decides which MCP tools to call
│                │    - Store intermediate results in working memory
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  Memory        │  Consolidate results: combine scores, track reasoning
│  (System)      │  Write to long-term memory if significant
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  Verifier      │  Check: data completeness, strategy consistency,
│  (LLM + Rules) │  risk exposure, historical backtest alignment
└───────┬────────┘
        │
   ┌────┴────┐
   │         │
   ▼         ▼ (fail → re-execute)
┌────────────────┐
│  Report Gen    │  Generate structured investment report
│  (Templates)   │  Sections: overview, candidates, scores,
│                │  fundamental, technical, risk, portfolio, disclaimer
└───────┬────────┘
        │
        ▼
   Final Report
```

**Read path (portfolio review):**

```
Existing Holdings
    │
    ▼
┌────────────────┐
│  Risk Analysis │  Analyze each holding: volatility, drawdown, liquidity
│  (Risk Skill)  │  Composite risk score per position
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  Performance   │  Return analysis, benchmark comparison, attribution
│  (Fund + Tech) │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  Rebalance     │  Generate rebalance recommendations
│  (Portfolio    │  Target weights, trade suggestions, risk warnings
│   Selection)   │
└───────┬────────┘
        │
        ▼
   Rebalance Report
```

### 5.4 Data Model

```yaml
entities:
  Stock:
    ts_code: str          # Tushare stock code
    name: str             # Stock name
    industry: str         # Industry classification
    market: str           # Market (SSE/SZSE)
    list_date: date       # IPO date
    is_active: bool       # Currently trading

  FinancialStatement:
    ts_code: str          # Stock code
    end_date: date        # Report period end
    report_type: str      # Q1/Q2/Q3/Q4/annual
    revenue: float        # Operating revenue
    net_profit: float     # Net profit attributable
    total_assets: float
    total_liabilities: float
    cash_flow: float      # Net operating cash flow
    roe: float            # Return on equity
    basic_eps: float      # EPS

  DailyPrice:
    ts_code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    change_pct: float     # Change percentage

  AnalysisResult:
    id: uuid
    created_at: timestamp
    stock: Stock
    strategy_scores: dict  # {fundamental: 0.85, technical: 0.72, ...}
    composite_score: float
    reasoning: str
    risk_factors: list
    confidence: float

  InvestmentReport:
    id: uuid
    created_at: timestamp
    user_requirement: str
    market_overview: str
    candidates: list[AnalysisResult]
    portfolio_suggestion: str
    disclaimer: str
    version: str          # Agent skill version
```

Storage: SQLite for structured data (prices, financials, reports); file-based markdown for agent memory (analysis histories, evaluation results).

## 6. Alternatives Considered

| Alternative | Pros | Cons | Verdict |
|-------------|------|------|---------|
| **Single monolithic agent** | Simple initial implementation; lower overhead | Poor separation of concerns; hard to evaluate individual strategies; any change retrains the whole system | Rejected |
| **Planner + Executor + Verifier (chosen)** | Clear responsibility boundaries; each component independently testable; strategy skills are pluggable | More components to implement; coordination overhead | Chosen — modularity wins for P8/P9 architecture |
| **Microservice per strategy** | Maximum isolation; independent scaling | Premature complexity for this scope; inter-service latency; requires service mesh | Rejected — over-engineering |
| **Vector DB for memory** | Semantic search over past analyses | Added infrastructure dependency; project scope is reference implementation | Deferred — file-based memory first, vector optional |
| **Backtrader for backtesting** | Mature, well-documented backtesting framework | Additional dependency; customizable but complex | Chosen — but abstracted behind MCP interface |
| **Direct Tushare API calls from agent** | Simpler implementation | Couples agent to raw API; no schema enforcement; hard to mock/test | Rejected — MCP layer provides abstraction, validation, and testability |

## 7. Agent Architecture Design

### 7.1 Agent Pattern: Orchestrated + ReAct Hybrid

The agent uses a hybrid pattern: an **Orchestrated Agent** at the top level (Planner → Executor → Verifier) with **ReAct loops** within each skill execution phase. This combines structured workflow orchestration with flexible reasoning within each analysis step.

```
                Orchestration Layer
┌─────────────────────────────────────────────────────────┐
│  Planner (decomposes) → Executor (orchestrates) → Verifier │
└─────────────────────────────────────────────────────────┘
         │
         ▼
    ReAct Loop per skill
┌─────────────────────────────────────────────────────────┐
│  Think → Act (call MCP tool) → Observe → Think → ...   │
│  → Skill Output (structured)                           │
└─────────────────────────────────────────────────────────┘
```

**Why hybrid?**
- The orchestration layer makes the overall workflow observable, testable, and controllable.
- The ReAct loop within each skill gives the LLM flexibility to adapt its analysis to the actual data it retrieves (e.g., if a stock lacks data for one metric, it can adjust).
- The separation prevents any single LLM call from needing to manage both the overall plan AND detailed analysis.

### 7.2 Planner Design

The Planner is a lightweight LLM call specialized in requirement decomposition.

**Input:** User's natural language investment requirement.
**Output:** Structured analysis plan.

```python
class AnalysisPlan(BaseModel):
    objective: str                    # Restated objective
    strategy_weights: dict[str, float]  # e.g., {"fundamental": 0.4, "growth": 0.25, ...}
    data_requirements: list[str]      # Tushare data needed
    analysis_steps: list[AnalysisStep]
    risk_preference: str              # low/medium/high

class AnalysisStep(BaseModel):
    id: int
    skill: str                        # Which skill to invoke
    target: str                       # What to analyze
    depends_on: list[int]             # Step dependencies
```

**Design decisions:**
- Planner output is structured (Pydantic model), not free text — enables the Executor to iterate over steps programmatically.
- Step dependencies enable parallel execution where possible (e.g., fundamental and technical analysis are independent; portfolio selection depends on all prior steps).
- Strategy weights are elicited from the user requirement and refined by the planner.

### 7.3 Executor Design

The Executor reads the plan from the Planner and executes each step by invoking the appropriate skill.

```
Executor:
  for each step in plan:
    if step.dependencies not met: wait/skip
    load skill from registry
    skill.execute(step.target, context=working_memory)
    store result in working memory
    if step fails: retry or log and continue
  after all steps: aggregate results
```

**Error handling:**
- Each step has a max retry count (default 2).
- Tool failures within a step are handled by the ReAct loop (try alternative approach).
- Non-recoverable steps are logged with partial results; the report generator handles partial data gracefully.

### 7.4 Verifier Design

The Verifier runs a multi-phase verification loop before report generation:

```
Phase 1 — Data completeness:
  - Are all expected data points present?
  - Are financial statements from the expected period?
  - Are price ranges reasonable (no obvious data errors)?

Phase 2 — Strategy consistency:
  - Do the assigned strategy weights match the executed analysis?
  - Are individual strategy scores internally consistent?
  - Are there contradictions between strategies (high fundamental + low growth)?

Phase 3 — Risk validation:
  - Is every recommendation accompanied by a risk warning?
  - Are risk scores above a minimum threshold flagged?
  - Is concentration risk addressed for portfolio suggestions?

Phase 4 — Historical alignment (optional):
  - Does the strategy show consistent performance in backtests?
  - Are current recommendations aligned with historical patterns?
```

Each phase produces a PASS/WARN/FAIL status. FAIL blocks report generation and triggers re-execution.

### 7.5 Report Generator Design

Template-driven report generation with structured sections:

```
Report Profile:
  - Report ID, generation timestamp, agent version
  - User requirement summary

1. Market Overview:
   - Current market context (index levels, sector performance)
   - Data freshness indicators

2. Candidate Selection:
   - Screening criteria applied
   - Candidate list with basic profiles
   - Exclusion rationale for non-selected candidates

3. Strategy Scores:
   - Composite score composition
   - Per-strategy breakdown
   - Weight justification

4. Fundamental Analysis:
   - Revenue/profit trends
   - ROE and efficiency
   - Cash flow health
   - Debt structure
   - Industry position
   - Score and reasoning

5. Technical Analysis:
   - Trend direction and strength
   - Moving average signals
   - Volume analysis
   - Momentum indicators
   - Score and reasoning

6. Risk Analysis:
   - Volatility assessment
   - Maximum drawdown
   - Liquidity analysis
   - Concentration risk
   - Risk score and warnings

7. Portfolio Suggestion:
   - Recommended portfolio structure
   - Position sizing guidance
   - Rebalance suggestions (if applicable)

8. Disclaimer:
   - AI-generated content notice
   - Not financial advice
   - Data source attribution
```

## 8. Skill System Design

### 8.1 Skill Architecture

Each investment strategy is a **skill** following the engineering-ai-standards format:

```
strategies/<strategy-name>/
├── SKILL.md              # Skill definition with YAML frontmatter
├── metadata.yaml         # Machine-readable metadata
├── __init__.py           # Python skill interface
├── analyzer.py           # Core analysis logic
├── prompt.md             # LLM prompt template
├── examples/             # Example inputs/outputs
│   └── example-1.yaml
├── eval/                 # Evaluation cases
│   └── case-1.yaml
└── CHANGELOG.md          # Version history with backtest results
```

### 8.2 Skill Interface

Every investment analysis skill implements a common interface:

```python
class AnalysisContext(BaseModel):
    stock: Stock
    financial_data: list[FinancialStatement]
    price_data: list[DailyPrice]
    market_data: dict                      # Broader market context
    user_preferences: dict                 # From requirement analysis
    memory: MemoryAccess                   # Read/write memory

class AnalysisResult(BaseModel):
    skill_name: str
    skill_version: str
    score: float                           # 0.0 - 1.0
    confidence: float                      # 0.0 - 1.0
    reasoning: str                         # Human-readable explanation
    risk_factors: list[RiskFactor]         # Risks identified
    supporting_data: dict                  # Key data points
    warnings: list[str]                    # Data quality warnings

class InvestmentSkill(ABC):
    @abstractmethod
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        """Execute the strategy analysis."""
        pass

    @abstractmethod
    def get_metadata(self) -> SkillMetadata:
        """Return skill metadata for registry."""
        pass
```

### 8.3 Skill Definitions

The system defines 5 initial investment strategy skills. Detailed SKILL.md files are created per skill.

| Skill | Purpose | Key Metrics | Weight Range |
|-------|---------|-------------|--------------|
| **fundamental-analysis** | Evaluate company financial health | Revenue growth, profit growth, ROE, cash flow, debt ratio, industry position | 25-40% |
| **technical-analysis** | Analyze price trends and momentum | Trend direction, MA cross, volume, momentum, price patterns | 15-25% |
| **valuation-analysis** | Assess fair value relative to peers | PE, PB, PEG, historical percentile | 15-25% |
| **risk-analysis** | Quantify downside and volatility | Volatility, max drawdown, liquidity, concentration | 10-20% |
| **portfolio-selection** | Combine strategies into composite score | Composite score, diversification, sector exposure | Orchestration only |

### 8.4 Skill Versioning

Skills follow semantic versioning:

| Version Change | When | Backtest Required |
|----------------|------|-------------------|
| Patch (1.0.0→1.0.1) | Bug fix, prompt refinement | No |
| Minor (1.0→1.1) | New metric, adjusted weights | Yes |
| Major (1.0→2.0) | Changed scoring methodology | Yes + Full regression |

Each strategy's CHANGELOG.md documents:
- Version change
- Description of change
- Backtest results before/after
- Performance comparison (return, drawdown, Sharpe)

## 9. Workflow Design

### 9.1 Investment Research Workflow

```yaml
workflow: investment-research
version: 1.0.0

steps:
  - id: requirement-analysis
    skill: planner
    description: Analyze user requirement, determine strategy weights, plan data needs
    output: research_plan

  - id: data-collection
    skill: executor (data)
    description: Collect market data via Tushare MCP tools
    depends_on: [requirement-analysis]
    output: market_data_context

  - id: fundamental-analysis
    skill: fundamental-analysis
    depends_on: [data-collection]
    parallel: true
    output: fundamental_scores

  - id: technical-analysis
    skill: technical-analysis
    depends_on: [data-collection]
    parallel: true
    output: technical_scores

  - id: valuation-analysis
    skill: valuation-analysis
    depends_on: [data-collection]
    parallel: true
    output: valuation_scores

  - id: risk-analysis
    skill: risk-analysis
    depends_on: [data-collection]
    parallel: true
    output: risk_scores

  - id: portfolio-selection
    skill: portfolio-selection
    depends_on: [fundamental-analysis, technical-analysis, valuation-analysis, risk-analysis]
    output: candidate_list

  - id: verification
    skill: verifier
    depends_on: [portfolio-selection]
    output: verification_result

  - id: report-generation
    skill: report-generator
    depends_on: [verification]
    output: investment_report

error_handling:
  strategy: retry-on-failure
  max_retries: 2
  partial_results: true
```

### 9.2 Portfolio Review Workflow

```yaml
workflow: portfolio-review
version: 1.0.0

steps:
  - id: portfolio-load
    skill: data (portfolio)
    description: Load existing holdings
    output: portfolio

  - id: risk-analysis
    skill: risk-analysis
    description: Analyze each holding's risk profile
    output: risk_profile

  - id: performance-analysis
    skill: fundamental-analysis + technical-analysis
    description: Evaluate each holding's performance
    depends_on: [portfolio-load]
    parallel: true
    output: performance_scores

  - id: rebalance-recommendation
    skill: portfolio-selection
    description: Generate rebalance recommendations
    depends_on: [risk-analysis, performance-analysis]
    output: rebalance_plan

  - id: report-generation
    skill: report-generator
    depends_on: [rebalance-recommendation]
    output: portfolio_report
```

## 10. MCP Tool Design

### 10.1 Tushare MCP Server Tools

| Tool Name | Description | Parameters | Returns |
|-----------|-------------|------------|---------|
| `get_stock_basic` | List stocks by market/industry | market?, industry? | List of stock profiles |
| `get_daily_price` | Daily price data for a stock | ts_code, start_date, end_date | OHLCV time series |
| `get_trade_calendar` | Trading calendar dates | start_date, end_date | List of trading days |
| `get_income_statement` | Income statement data | ts_code, start_date, end_date | Revenue/profit series |
| `get_balance_sheet` | Balance sheet data | ts_code, start_date, end_date | Asset/liability series |
| `get_cashflow` | Cash flow statement | ts_code, start_date, end_date | Cash flow series |
| `get_money_flow` | Capital flow data | ts_code, trade_date | Money flow metrics |
| `get_holder_change` | Major holder changes | ts_code, start_date, end_date | Holder data |
| `get_market_index` | Market index data | index_code, start_date, end_date | Index OHLCV |

### 10.2 Tool Design Principles

Following the tool-use patterns from engineering-ai-standards:

1. **One tool = one responsibility.** Each tool maps to one Tushare API endpoint.
2. **JSON Schema validation.** Every parameter is validated before API call.
3. **Rate limiting.** Tushare API rate limits are enforced at the MCP server level (max 200 queries/min).
4. **Caching.** Frequently accessed data (stock basics, trade calendar) is cached locally with T+1 staleness.
5. **Error propagation.** API errors are wrapped with descriptive messages and recovery hints.
6. **Idempotent reads.** All market data tools are read-only — safe to retry.

### 10.3 Tool Implementation Pattern

```python
# tools/tushare_mcp/server.py

@mcp.tool()
async def get_daily_price(
    ts_code: str = Field(description="Tushare stock code, e.g., '000001.SZ'"),
    start_date: str = Field(description="Start date YYYYMMDD"),
    end_date: str = Field(description="End date YYYYMMDD"),
) -> list[dict]:
    """Get daily OHLCV price data for a stock over a date range."""
    try:
        cache_key = f"daily_{ts_code}_{start_date}_{end_date}"
        if cached := await cache.get(cache_key):
            return cached

        df = await tushare_api.daily(ts_code=ts_code,
                                     start_date=start_date,
                                     end_date=end_date)
        result = df.to_dict(orient="records")

        await cache.set(cache_key, result, ttl=3600)  # 1h cache
        return result

    except TushareRateLimitError:
        raise ToolError(
            message="Tushare API rate limit exceeded. Please wait 30s and retry.",
            recoverable=True,
        )
    except TushareAuthError:
        raise ToolError(
            message="Tushare API token invalid or expired.",
            recoverable=False,
        )
    except Exception as e:
        raise ToolError(
            message=f"Failed to fetch price data: {str(e)}",
            recoverable=False,
        )
```

## 11. Memory System Design

### 11.1 Memory Architecture

Following the engineering-ai-standards memory policy:

```
┌─────────────────────────────────────────────┐
│              Memory System                    │
│                                               │
│  Working Memory (current analysis session):   │
│    - User requirement                        │
│    - Analysis plan in progress               │
│    - Intermediate results per step           │
│    - Current step context                    │
│    - Volatile: lost when session ends        │
│                                               │
│  Episodic Memory (past sessions):             │
│    - Analysis history (report summaries)     │
│    - Tool call patterns                      │
│    - Session summaries                       │
│    - SQLite-backed, append-only              │
│                                               │
│  Semantic Memory (cross-session knowledge):   │
│    - Historical recommendations              │
│    - Strategy performance records            │
│    - Evaluation results                      │
│    - User preferences                        │
│    - File-based markdown with frontmatter    │
└─────────────────────────────────────────────┘
```

### 11.2 Storage Implementation

**Working Memory:** In-memory Python dict, managed by the Executor.

**Episodic Memory:** SQLite database with schema:
```sql
CREATE TABLE analysis_sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    user_requirement TEXT,
    plan JSON,
    status TEXT
);

CREATE TABLE tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES analysis_sessions(id),
    step_id TEXT,
    tool_name TEXT,
    input JSON,
    output JSON,
    duration_ms INTEGER,
    success BOOLEAN,
    created_at TIMESTAMP
);

CREATE TABLE analysis_results (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES analysis_sessions(id),
    skill TEXT,
    stock_code TEXT,
    score REAL,
    confidence REAL,
    reasoning TEXT,
    created_at TIMESTAMP
);
```

**Semantic Memory:** Markdown files with frontmatter:
```markdown
---
name: recommendation-20260728
description: Investment recommendation from Jul 28, 2026 analysis
metadata:
  type: recommendation
  score: 0.82
  strategy: value-growth
---

**Stock:** 000001.SZ
**Composite Score:** 0.82
**Reasoning:** [summary]
**Outcome:** [if later verified]
```

### 11.3 Retrieval Strategy

1. On session start, load recent semantic memories (last 5 recommendations).
2. During requirement analysis, search semantic memory for similar past analyses.
3. During execution, the Executor reads/writes working memory.
4. On session end, consolidate key results into semantic memory.
5. Episodic queries happen on explicit demand ("what did we analyze last time?").

## 12. Verification Loop

Following the engineering-ai-standards verification loop:

```
┌─────────────────────────────────────────────────────┐
│                    ANALYSIS DONE?                     │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  1. GENERATE                                         │
│  - Was the analysis plan executed completely?        │
│  - Are all strategy scores produced?                 │
│  - Are intermediate results stored?                  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  2. VERIFY DATA                                      │
│  - Are data sources complete (no gaps >5% missing)? │
│  - Are financial statements from the latest period?  │
│  - Are price ranges physically reasonable?           │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  3. VERIFY STRATEGY                                  │
│  - Is each strategy score internally consistent?     │
│  - Are score weights aligned with user requirement?  │
│  - Are contradictions between strategies explained?  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  4. VERIFY RISK                                      │
│  - Is every recommendation paired with risk warning? │
│  - Are high-risk positions flagged?                  │
│  - Is concentration risk addressed?                  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  5. VERIFY HISTORY (optional)                        │
│  - Does the strategy perform consistently in BT?    │
│  - Are current recommendations aligned historically? │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
                    ┌─────────┐
                    │  REPORT │
                    └─────────┘
```

If any check fails:
1. Log the specific gap with severity.
2. Return to the failing step (re-execute with corrected approach).
3. Re-verify after fix.
4. Escalate to user if retries exhausted.

## 13. Evaluation Framework

### 13.1 Strategy Performance Evaluation

| Metric | Description | Calculation |
|--------|-------------|-------------|
| **Return** | Total return over evaluation period | (End value - Start value) / Start value |
| **Max Drawdown** | Maximum peak-to-trough decline | Min(peak - trough) / peak |
| **Sharpe Ratio** | Risk-adjusted return | (Return - risk_free) / std_dev(returns) |
| **Win Rate** | Percentage of positive periods | Winning periods / Total periods |
| **Hit Rate** | Percentage of correct recommendations | Correct calls / Total calls |

### 13.2 Agent Quality Evaluation

Following the evaluation schema from engineering-ai-standards:

| Dimension | Weight | Criteria |
|-----------|--------|----------|
| **Correctness** | 30% | Data accuracy, calculation validity, no hallucinated metrics |
| **Completeness** | 25% | All analysis dimensions covered, data sources cited, risks documented |
| **Reasoning Quality** | 20% | Logical flow, trade-offs acknowledged, assumptions stated |
| **Risk Awareness** | 15% | Risks identified, severity assessed, mitigation suggested |
| **Explainability** | 10% | Scores traceable to data points, reasoning human-readable |

### 13.3 Evaluation Cases

Following the engineering-ai-standards evaluation case schema:

```yaml
# evaluations/strategy-score/fundamental-analysis.yaml
id: fundamental-analysis-v1
skill: fundamental-analysis
category: investment-analysis
version: 1.0.0
task: >
  Analyze 000001.SZ using fundamental analysis.
  Evaluate revenue growth, profit trends, ROE, debt ratio, and cash flow.
context:
  - Financial data from 2023Q1-2025Q4
  - Industry: banking
expected:
  must_include:
    - revenue_growth_trend
    - net_profit_margin_analysis
    - roe_assessment
    - debt_ratio_evaluation
    - cash_flow_health
    - score_with_rationale
    - risk_factors
  forbidden:
    - hallucinated_financial_metrics
    - missing_disclaimer
scoring:
  threshold: 75
  correctness:
    weight: 30
    description: "Financial metrics correctly calculated and interpreted"
    criteria:
      - "Revenue growth rate correctly derived from income statements"
      - "ROE matches reported financial data"
      - "Debt ratio correctly calculated from balance sheet"
  completeness:
    weight: 25
    description: "All fundamental dimensions covered"
    criteria:
      - "All 5 core metrics (revenue, profit, ROE, debt, cash flow) analyzed"
      - "Industry context considered"
  reasoning_quality:
    weight: 20
    description: "Analysis logic and explanation quality"
    criteria:
      - "Trend analysis covers at least 3 periods"
      - "Strengths and weaknesses both discussed"
  risk_awareness:
    weight: 15
    description: "Risk identification and assessment"
    criteria:
      - "At least 3 risk factors identified"
      - "Risk severity rated"
  explainability:
    weight: 10
    description: "Traceability of score to data"
    criteria:
      - "Each score component references specific data points"
      - "Confidence level stated with reasoning"
```

### 13.4 Evaluation Pipeline

```
1. Load evaluation cases from evaluations/<category>/<case>.yaml
2. For each case:
   a. Inject context into the agent
   b. Run the agent with the task prompt
   c. Score output against expected criteria
   d. Record scores
3. Compare against baseline scores
4. Generate evaluation report:
   - Overall score
   - Per-case breakdown
   - Regressions vs baseline
   - Trend over last N runs
```

The existing engineering-ai-standards evaluator (`evaluations/runner/evaluator.py`) and scorecard (`evaluations/runner/scorecard.py`) are extended or configured for investment analysis dimensions.

## 14. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Tushare API rate limits during analysis** | Medium | High — analysis stalls mid-flow | MCP server queues and rate-limits; agent retries with exponential backoff |
| **Stale or incomplete financial data** | Medium | Medium — incorrect scores | Data freshness check in verifier; report includes data timestamp disclaimer |
| **LLM hallucinates financial metrics** | Low | High — misleading recommendations | Structured output with validation; verifier checks data against known ranges |
| **Strategy weights misaligned with user intent** | Medium | Medium — irrelevant recommendations | Planner restates requirement for user confirmation before execution |
| **Agent enters infinite ReAct loop** | Low | High — wasted tokens and timeout | Max iteration limit (15 per skill); circuit breaker in Executor |
| **Market regime change invalidates strategy** | High (long-term) | Medium — degraded recommendations | Periodic backtest validation; strategy versioning captures performance drift |
| **SQLite concurrency for memory** | Low (single user) | Low | File-level locking for writes; read replicas not needed at reference scale |

## 15. Implementation Plan

### Phase 1: Foundation (Week 1)
- Repository structure and CI setup
- Tushare MCP server with basic tools
- Agent core: Planner, Executor skeleton
- Memory system (working + episodic SQLite)

### Phase 2: Skills (Week 2)
- Fundamental analysis skill (SKILL.md + Python)
- Technical analysis skill
- Valuation analysis skill
- Risk analysis skill

### Phase 3: Workflows (Week 3)
- Portfolio selection skill
- Investment research workflow
- Portfolio review workflow
- Verifier implementation
- Report generator

### Phase 4: Evaluation & Polish (Week 4)
- Evaluation cases for each skill
- Backtest engine integration
- Evaluation runner setup
- Documentation and examples

## 16. Appendix

### 16.1 Glossary

| Term | Definition |
|------|------------|
| **Tushare** | Chinese financial data API providing stock, fund, and market data |
| **MCP** | Model Context Protocol — standardized protocol for LLM tool invocation |
| **Skill** | A reusable, versioned analysis capability following eng-ai-standards format |
| **Workflow** | Orchestrated sequence of skills to accomplish a multi-step task |
| **ReAct** | Reasoning + Acting loop: Think → Act → Observe |
| **Sharpe Ratio** | (Portfolio Return - Risk-Free Rate) / Standard Deviation of Returns |
| **ROE** | Return on Equity — net income / shareholders' equity |
| **Max Drawdown** | Maximum observed loss from a peak to a trough |
| **PEG** | Price/Earnings to Growth ratio |

### 16.2 Related Documents

- [ADR-001: Agent Architecture Pattern](adr/001-agent-architecture.md)
- [ADR-002: Skill System Design](adr/002-skill-system.md)
- [ADR-003: Memory Architecture](adr/003-memory-architecture.md)
- [ADR-004: MCP Integration Strategy](adr/004-mcp-integration.md)
- [ADR-005: Evaluation Framework](adr/005-evaluation-framework.md)
- [engineering-ai-standards principles](../../engineering-ai-standards/principles/engineering-principles.md)
- [engineering-ai-standards agent runtime](../../engineering-ai-standards/runtime/verification-loop.md)

### 16.3 Architecture Diagram (ASCII)

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
│  │  Planner                                             │  │
│  │  ├─ Parse requirement → strategy_weights, plan       │  │
│  │  └─ Output: AnalysisPlan                             │  │
│  └──────────────────────────┬───────────────────────────┘  │
│                             │                              │
│                             ▼                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Executor                                            │  │
│  │  ├─ For each step: load skill → ReAct → store       │  │
│  │  ├─ Tool calls via MCP layer                         │  │
│  │  └─ Error handling: retry/log/pass                   │  │
│  └──────────────────────────┬───────────────────────────┘  │
│                             │                              │
│              ┌──────────────┼──────────────┐               │
│              ▼              ▼              ▼               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ Fundamental  │ │  Technical   │ │  Valuation   │       │
│  │ Analysis     │ │  Analysis    │ │  Analysis    │       │
│  │ Skill        │ │  Skill       │ │  Skill       │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│  ┌──────────────┐ ┌──────────────────────────────────┐     │
│  │ Risk         │ │  Portfolio Selection             │     │
│  │ Analysis     │ │  (combines scores → ranking)     │     │
│  └──────────────┘ └──────────────────────────────────┘     │
│                             │                              │
│                             ▼                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Verifier                                            │  │
│  │  ├─ Data completeness check                          │  │
│  │  ├─ Strategy consistency check                       │  │
│  │  └─ Risk validation                                  │  │
│  └──────────────────────────┬───────────────────────────┘  │
│                             │                              │
│                             ▼                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Report Generator                                    │  │
│  │  ├─ Template-based report assembly                   │  │
│  │  └─ Output: InvestmentReport                         │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │  Investment      │
                    │  Research Report │
                    └──────────────────┘

┌───────────────────────────────────────────────────────────┐
│  MCP Layer                                                │
│  ┌─────────────────┐ ┌─────────────────┐                 │
│  │ Tushare MCP     │ │ Backtest MCP    │                 │
│  │ ├─ stock_basic  │ │ ├─ run_backtest │                 │
│  │ ├─ daily_price  │ │ └─ get_results  │                 │
│  │ ├─ financials   │ └─────────────────┘                 │
│  │ └─ money_flow   │                                     │
│  └─────────────────┘                                     │
└───────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────┐
│  Memory System                                            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ Working      │ │ Episodic    │ │ Semantic     │      │
│  │ (in-memory)  │ │ (SQLite)    │ │ (markdown)   │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
└───────────────────────────────────────────────────────────┘
```
