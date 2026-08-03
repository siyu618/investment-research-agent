# Agentic Investment Research Platform

A **production-grade Agent Platform** for automated investment research — a reference implementation of how a modern AI agent system should be architected: **dynamic planning, tool orchestration, a RAG knowledge layer, persistent memory, trajectory evaluation, and full observability** — applied to the investment domain.

> This is not an "investment research bot." It is an **Agent Platform** whose reference domain is investment research. The platform core (`runtime/`, `tools/registry.py`, `memory/`, `skills/base/skill_sdk.py`) is domain-agnostic; the investment domain (`agent/`, `strategies/`) is a concrete implementation on top of it — the same way you'd build an agent for code review, QA, or support on the same core.

> ⚠️ **免责声明**：本系统生成的报告仅供研究参考，不构成投资建议。默认使用 Mock 模拟数据；接入真实 Tushare 数据需要 API Token。策略回测为实验性，未经过严格 point-in-time / 成本 / 幸存者偏差处理。

---

## 平台能力一览

| 能力 | 说明 | 入口 |
|------|------|------|
| **Agent Runtime** | 统一生命周期 `create_task → plan → schedule → execute → aggregate → report`，领域无关，业务组件注入 | `runtime/agent_runtime.py` + `agent/runtime_adapter.py` |
| **Dynamic Planning** | 根据用户目标自动拆解任务（`plan_for_goal`），按意图选择分析维度并映射工具；LLM 分解 + 规则回退 | `agent/planner.py` |
| **MCP Tool Ecosystem** | 元数据驱动的 ToolRegistry：Local / MCP / API 来源、JSON Schema、capability、cost、rate limit、cache policy | `tools/registry.py` + `tools/registry.d/` |
| **RAG Knowledge Layer** | 按公司/行业/主题召回历史研究并回写，跨会话知识积累 | `memory/retrieval.py` + `memory/research.py` |
| **Memory** | 7 层内存体系（Working / Episodic / Semantic / Research / ToolCache / Execution / Artifacts） | `memory/` |
| **Evaluation** | AgentRunStats（task/tool success、latency、token cost、evidence）+ 轨迹评分 | `runtime/agent_runtime.py` + `evaluations/trajectory/` |
| **Observability** | 完整链路 `User Query → Planner → Agent → Tool → Retrieval → LLM → Result`，CLI 链路图 + Mermaid + JSONL trace | `runtime/tracing/` + `runtime/run_recorder.py` |

---

## 快速开始

```bash
# 完整 Demo（动态规划 + RAG + 评估 + 可观测 + 重放）
bash demo/run_demo.sh

# 单只股票研究（自动识别股票代码 → 动态规划任务分解）
python -m agent --requirement "分析 600519.SH 投资价值"

# 多股票筛选（动态计划 → 并行 52 次工具调用）
python -m agent --requirement "从沪深300筛选基本面稳健、估值合理的5只股票"

# 启用 RAG 知识层（按公司/行业/主题召回历史研究并回写）
python -m agent --requirement "重新分析 600519.SH" --reuse-memory

# 轨迹评估（对某次运行评分）
python -m agent --eval-trajectory runs/{run_id}

# 确定性重放（恢复快照，禁 Provider，逐节点比较 hash）
python -m agent --replay runs/{run_id}

# 交互模式
python -m agent --interactive --reuse-memory

# 使用真实 Tushare 数据（需要 TUSHARE_TOKEN）
export TUSHARE_TOKEN=your_token_here
python -m agent --requirement "分析 600519.SH" --provider tushare
```

---

## 统一 Agent Runtime

所有运行走**同一条生命周期**——领域无关的 `AgentRuntime`，业务组件通过适配器注入：

```
User Query
    │  create_task（真实 span: task）
    ▼
Planner ──────────────────── plan_for_goal（动态分解，LLM + 规则）
    │                        （真实 span: planner）
    ▼
Executor Adapter ─────────── AnalysisPlan → TaskGraph → Scheduler（DAG 并行）
    │                        （真实 span: scheduler / tool / skill）
    ▼
Verifier Stage ───────────── 多阶段校验 + policy gate（真实 span: verifier）
    │
    ▼
Reporter Stage ───────────── ReportGenerator.generate（真实 span: reporter）
    │
    ▼
Final Report + AgentRunStats + 12 Artifacts
```

每次运行生成 **13 个 Artifact**（含 `execution_stats` 与轨迹评分）：

```
manifest.json            Artifact 清单（每个文件的 sha256 + schema version + 用途）
request.json             原始需求
plan.json                结构化计划（objective/weights/steps，动态分解）
tool_trace.jsonl         工具调用级 trace（输入/输出 hash、耗时、重试）
agent_trace.jsonl        统一生命周期 trace（真实 span：retrieval→planner→tools→skills→verifier→report）
data_snapshot.json       完整 point-in-time 数据快照（含 content_hash + snapshot_hash）
execution_outputs.json   每个 DAG 节点的标准化输出 + hash（Replay 逐节点比较）
result_manifest.json     标准化业务结果（候选排序/评分、Verification、执行指标）
verification.json        校验结果（severity + policy mode + blocked）
execution_graph.mmd      Mermaid 执行流程图
report.md                最终 Markdown 报告
meta.json                运行元信息（状态/耗时/事件数/执行指标 AgentRunStats）
trajectory_score.json    轨迹评估（--eval-trajectory 生成）
```

---

## 动态 Planning

Planner 根据用户**目标意图**自动拆解任务，而不是固定 7 步模板：

```
"分析 600519.SH 投资价值"  →  [data, fundamental, valuation, risk, portfolio, verify, report]
"从沪深300筛选稳健的5只股票" →  [data, fundamental+risk, portfolio, verify, report]
"看下估值"                  →  [data, valuation, risk, verify, report]
```

- 意图关键词 → 分析维度（基本面/估值/风险/技术）
- 每个维度映射到 ToolRegistry 的能力（capability → tool）
- LLM 分解 + 确定性规则回退（无 key 也可运行）
- 输出结构化 `AnalysisPlan`（step/tool/depends_on），供 Runtime 执行

---

## MCP Tool Ecosystem（Tool Registry）

工具通过**元数据驱动**注册与发现，Planner 据此动态选择：

```yaml
# tools/registry.d/tushare-tools.yaml
get_daily_price:
  description: "Get daily OHLCV price data for a stock over a date range"
  capability: "market-data"
  source_type: "local"        # local | mcp | api
  schema: { ... }             # JSON Schema（输入）
  returns: { ... }            # JSON Schema（输出）
  timeout: 15
  cost: 1
  rate_limit: "200/min"
  cache_policy: { ttl: 14400 }
```

- **来源统一**：Local 函数 / MCP Server / API 端点都注册进同一个 Registry
- **自动 Schema**：未手写 schema 时从函数签名推断
- **Planner 发现**：`find_by_capability()` / `get_schemas_for_llm()`（含 capability/source/cost）
- **运行时强制**：timeout、rate limit、cache、事件发射（ToolInvoked/Finished/Failed）

---

## RAG Knowledge Layer（记忆）

跨会话知识积累：再次分析某公司/行业/主题时，自动**召回**之前的研究结果：

```
第一次运行 "分析 600519.SH"  →  知识层写入（company:600519.SH, industry:白酒, score）
第二次运行 "重新分析 600519.SH" → 知识层召回 1 条历史研究 → 注入运行上下文
```

- 按 **company / industry / theme** 三轴检索（`get_by_subject`）
- 每次召回记录真实 `kind="retrieval"` span（可见于 agent_trace.jsonl）
- 中文关键词检索（修复了 `json.dumps` 的 ASCII 转义 bug）
- 7 层 Memory 体系：Working（会话）/ Episodic（历史会话）/ Semantic（markdown 知识）/ Research（研究结果）/ ToolCache / Execution / Artifacts

---

## Evaluation（执行质量）

每次运行收集真实执行指标（从真实 trace span 聚合，非估算）：

| 指标 | 来源 |
|------|------|
| Task Success Rate | 任务状态 |
| Tool Calling Success Rate | tool spans（成功/失败） |
| Response Latency | scheduler span 真实耗时 |
| Token Cost | LLM API `usage` 字段（input/output/cache） |
| Citation / Evidence Coverage | 数据集实际消费的行数（价格 + 财务） |

轨迹评估（`--eval-trajectory`）按 6 个维度给运行评分：

```
Trajectory Score: 97.0/100  (PASS)
  planning           100/100
  tool_selection      85/100
  execution_efficiency 100/100
  error_recovery     100/100
  verification       100/100
  overall_quality    100/100
```

---

## Observability（可观测性）

每次运行后 CLI 直接展示**完整 Agent 链路**（真实 span，含耗时与 token）：

```
🔍 Agent Chain (User Query → … → Final Result)
  QUERY    分析 600519.SH 投资价值
  ✓ [RETR ] retrieve:600519.SH  ({'hits': 1})
  ✓ [PLAN ] Planner
  ✓ [SCHED] Scheduler  (52ms)
  ✓ [VERIFY] Verifier  ({'passed': True, ...})
  ✓ [TOOL ] get_stock_basic
  ✓ [TOOL ] get_daily_price  (1ms, {'rows': 522, 'kept': 522})
  ✓ [SKILL] fundamental-analysis  (5ms, {'score': 0.46})
  ✓ [LLM  ] generate_plan  (300ms, 812+95 tok)
```

外加：`agent_trace.jsonl`（全链路 JSONL）、`execution_graph.mmd`（Mermaid 流程图）、`tool_trace.jsonl`（工具级）。

---

## 系统架构

```
┌─────────────────────────┐
│          CLI             │  python -m agent ...
└────────────┬────────────┘
             │
┌────────────▼────────────┐
│     AgentRuntime         │  ← 领域无关统一生命周期
│  create_task → plan →    │     schedule → execute →
│  aggregate → report      │     aggregate → report
└────────────┬────────────┘
             │  adapter injection (agent/runtime_adapter.py)
   ┌─────────┼──────────────┬──────────────┐
   ▼         ▼              ▼              ▼
 Planner    Executor      Verifier      Reporter
 (dynamic)  (DAG→Skills)  (policy gate) (report)
   │         │              │              │
   │         │   ┌──────────▼─────────┐    │
   │         └──▶│ ToolRegistry (MCP)  │────┘
   │             │ local/mcp/api       │
   │             └──────────┬─────────┘
   │             ┌──────────▼─────────┐
   └────────────▶│ KnowledgeRetriever  │   RAG 知识层
                 │ ResearchMemory       │
                 └─────────────────────┘
```

**Provider 隔离**：Skills 永不直接访问 Provider。`DataCollector` 是唯一访问 Provider 的组件，把所有数据包装成不可变的 `ResearchDataset`（点时间快照）。这保证了**相同快照 → 相同结果**（可重放），并防止未来函数。

---

## 分层架构

| 层 | 目录 | 职责 |
|----|------|------|
| **智能决策层** | `agents/` | Planner（动态分解）、Runtime Adapter（生命周期桥接）、Verifier |
| **任务编排层** | `workflows/` + `runtime/` | DAG 调度、图验证、工作流定义 |
| **能力封装层** | `skills/` + `strategies/` | Skill SDK（5 阶段生命周期）、分析策略 |
| **外部能力层** | `tools/` | ToolRegistry、Provider（Mock/Tushare）、Backtest |

```
strategies/              # 分析策略 Skills（fundamental/valuation/risk）
workflows/               # 工作流定义（investment-research / portfolio-review）
agents/ → agent/         # 智能决策（Planner / Executor / Verifier / Report Gen）
tools/                   # 外部能力（ToolRegistry / Provider / Backtest）
```

---

## 工程规范

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试（当前 316 个）
pytest tests/

# 静态检查
ruff check agent runtime tools memory strategies
mypy --explicit-package-bases agent runtime strategies tools memory

# 覆盖率
pytest tests/ --cov=agent --cov=runtime --cov=strategies --cov=tools

# pre-commit
pre-commit install
```

### 环境配置

复制 `.env.example` 为 `.env` 并填入你的值：

```bash
TUSHARE_TOKEN=your_token_here        # 真实数据需要
ANTHROPIC_API_KEY=your_key_here      # 动态规划 LLM（可选，缺省用规则）
AGENT_PROVIDER=mock                  # mock | tushare
AGENT_TOP_K=5
```

---

## 项目结构

```
agent/                    # 智能决策层（投资领域）
├── planner.py           # 动态 Planner（plan_for_goal，意图分解 + 工具映射）
├── executor.py          # AnalysisPlan → TaskGraph → Scheduler
├── runtime_adapter.py   # 桥接 AgentRuntime ↔ 领域组件（统一生命周期）
├── data_collector.py    # 唯一 Provider 访问者 → ResearchDataset
├── verifier.py          # severity + policy_mode 校验
├── report_generator.py  # Markdown 报告（plan-aware）
├── llm.py               # LLM 后端（含 token/latency span）
└── __main__.py          # CLI（run + replay + eval-trajectory）

runtime/                 # 框架核心（领域无关）
├── agent_runtime.py     # 统一 AgentRuntime（生命周期 + AgentRunStats）
├── scheduler.py         # DAG 并行调度
├── graph.py             # TaskGraph 验证 + 拓扑排序
├── snapshot.py          # DataSnapshot + ResearchDataset（PIT）
├── run_recorder.py      # runs/{run_id}/ 审计输出 + Mermaid 图
├── tracing/             # EventBus + trace_span + formatters
└── ...

strategies/              # 分析策略 Skills（underscore 目录为可导入模块）
├── fundamental_analysis/  # 基本面评分（已实现）
├── valuation_analysis/    # 估值评分（已实现）
├── risk_analysis/         # 风险评分（已实现）
└── base/                  # Skill SDK + 数据模型

skills/
└── base/skill_sdk.py    # Skill 5 阶段生命周期（metadata/plan/execute/verify/summarize）

tools/
├── registry.py          # 元数据驱动 ToolRegistry（local/mcp/api）
├── registry.d/          # 工具元数据声明（YAML + JSON Schema）
├── providers.py         # MarketDataProvider 协议 + Mock + Tushare
└── backtest/engine.py   # 实验性回测引擎

memory/
├── interfaces.py        # MemoryProvider ABC
├── research.py          # 长期研究结果（公司/行业/主题）
├── retrieval.py         # RAG 知识层（KnowledgeRetriever）
└── ...

evaluations/
├── trajectory/          # 轨迹评估（TrajectoryEvaluator）
├── agent-quality/       # 执行质量评估
└── cases/               # 可复现端到端案例

demo/
└── run_demo.sh          # 平台能力 Demo

runs/                    # 运行时产物（gitignored）
```

---

## 关键架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent Runtime | AgentRuntime 统一生命周期，业务组件注入 | 领域无关、可观测、可测试 |
| Planner | LLM + 规则动态分解（plan_for_goal） | 自动拆解任务，工具发现 |
| Tool Registry | 元数据驱动（schema/capability/source） | Planner 动态选择工具 |
| Provider 隔离 | DataCollector 独占 Provider，Skills 消费快照 | 可重放、防未来函数 |
| 数据时间性 | DataSnapshot（as_of/hash） | point-in-time 分析 |
| 知识层 | ResearchMemory + 主题标签（公司/行业/主题） | 跨会话知识积累 |
| Verifier | severity + policy_mode | 未来函数/权重错误阻断流程 |
| 运行审计 | 13 文件（含 agent_trace + Mermaid + stats） | 可审计、可复现、可排查 |
| Replay | ForbiddenProvider + 逐节点 hash 比较 | 确定性复现 |

---

## 演进路线

详见 [docs/evolutionary-roadmap.md](docs/evolutionary-roadmap.md) 与 [docs/adr/](docs/adr/)。

最近的架构里程碑：
- **ADR-015** — 统一 Agent Runtime（AgentRuntime 作为唯一生命周期引擎）
- **ADR-012** — 统一 trace_span 可观测性
- **ADR-013** — Point-in-Time 数据字段 + as_of 过滤
- **ADR-014** — Deterministic Replay + content_hash/snapshot_hash 拆分

---

## 参考文献

- [设计文档](docs/design.md)
- [演进路线图](docs/evolutionary-roadmap.md)
- [评估框架](evaluations/README.md)
- [可复现案例](evaluations/cases/README.md)
- [engineering-ai-standards](engineering-ai-standards/)
