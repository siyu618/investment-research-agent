# Tushare Investment Research Agent

An AI Agent system for automated investment research, built as a **reference implementation** of the [engineering-ai-standards](engineering-ai-standards/) agent framework. It demonstrates a **bounded, observable, reproducible, replayable** research workflow: requirement parsing → DAG scheduling → skill-based multi-strategy analysis → verification → Markdown report — with every run fully auditable.

> ⚠️ **免责声明**：本系统生成的报告仅供研究参考，不构成投资建议。默认使用 Mock 模拟数据；接入真实 Tushare 数据需要 API Token。策略回测为实验性，未经过严格 point-in-time / 成本 / 幸存者偏差处理。

---

## 快速开始

```bash
# 运行投资研究（Mock 数据，无需 API Key）
python -m agent --requirement "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"

# 单只股票研究（自动识别股票代码）
python -m agent --requirement "分析 600519.SH"

# 重放历史运行（基于快照，确定性复现）
python -m agent --replay runs/{run_id}

# 交互模式
python -m agent --interactive

# 使用真实 Tushare 数据（需要 TUSHARE_TOKEN）
export TUSHARE_TOKEN=your_token_here
python -m agent --requirement "分析 600519.SH" --provider tushare
```

每次正常运行会生成 **12 个 Artifact**；Replay 额外生成 `replay_verification.json`：

```
manifest.json            Artifact 清单（每个文件的 sha256 + schema version + 用途）
request.json             原始需求
plan.json                结构化计划（objective/weights/steps）
tool_trace.jsonl         工具调用级 trace（输入/输出 hash、耗时、重试）
agent_trace.jsonl        统一生命周期 trace（真实 span：planner→tools→skills→verifier→report）
data_snapshot.json       完整 point-in-time 数据快照（含 content_hash + snapshot_hash）
execution_outputs.json   每个 DAG 节点的标准化输出 + hash（Replay 逐节点比较）
result_manifest.json     标准化业务结果（候选排序/评分、组合、Verification、报告内容 hash）
verification.json        校验结果（severity + policy mode + blocked）
execution_graph.mmd      Mermaid 执行流程图
report.md                最终 Markdown 报告
meta.json                运行元信息（状态/耗时/事件数/错误）
```

**Hash 体系**：`content_hash` 只覆盖数据内容（跨环境稳定，供缓存）；`snapshot_hash` 覆盖内容 + as_of/publish_date/effective_date 等完整上下文（供 Replay 等价验证）。两者均已由测试验证。

## Replay 验证

```bash
# 跑一次完整 run
python -m agent --requirement "分析 600519.SH"
R=$(ls -t runs/ | head -1)

# Deterministic Replay Verification：恢复 request/plan/snapshot，
# 按原 DAG 重放全部节点（Provider 禁止访问），逐节点比较
python -m agent --replay "runs/$R"
# 期望输出：状态 PASSED，Provider 访问尝试 0 次，快照/计划/节点 hash 全部一致
```

**Artifact 完整性门禁**：Replay 启动前先校验 `manifest.json` 的 schema version、每个必需 Artifact 的文件 hash；若 `execution_outputs.json` 缺失、manifest 缺失/版本不支持、或任何文件 hash 不匹配（被篡改/损坏），直接返回 `artifact_missing` 失败并给出原因——绝不跳过比较或默认通过。

Replay 期间通过 `ForbiddenProvider` 禁止任何外部数据访问（任何 Provider 调用立即抛错）。执行后逐项比较：
- **snapshot_hash**（完整上下文，非 content_hash）
- **plan_hash**
- **每个真实 Skill 节点的 output_hash**（来自 `execution_outputs.json`，逐节点比较）
- **result_manifest**：候选排序 + 综合评分（逐项）、VerificationResult、组合建议、报告内容 hash（结构化事实，非 Markdown 文本）
- 报告章节结构（次要，辅助项）

**严格确定性 Replay**：只有在节点输出、候选排序、Verification、结构化报告内容与 Artifact Hash 全部通过自动比较后，才称为严格确定性 Replay（status=PASSED）。任何一项不匹配即 `failed`，输出详细 diff（含期望/实际 hash 前缀与差异节点）。结果写入 `runs/{run_id}/replay_verification.json`。

---

## 系统架构

```
                    ┌──────────────────┐
                    │      CLI          │
                    └────────┬─────────┘
                             │
                ┌────────────┴────────────┐
                │         Harness          │
                │  Plan→Execute→Verify→Rpt │
                │  (retry, timeout, gate)  │
                └────────────┬────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐   ┌────────────────┐   ┌────────────────┐
│  Planner      │   │   Scheduler     │   │  Verifier       │
│ (LLM+rules)  │   │ (DAG / parallel)│   │ (severity+mode) │
└──────────────┘   └───────┬────────┘   └────────────────┘
                           │
                  ┌────────┴────────┐
                  │  Skill Executor  │
                  │  (fund/val/risk) │
                  │  ← consumes      │
                  └────────┬────────┘
                           │ ResearchDataset (immutable)
                  ┌────────┴────────┐
                  │   DataCollector  │  ← ONLY provider accessor
                  └────────┬────────┘
                           │
                  ┌────────┴────────┐
                  │ MarketDataProvider │  ← abstract
                  │ (Mock | Tushare)   │
                  └─────────────────┘
```

**Provider 隔离**：Skills 永不直接访问 Provider。`DataCollector` 是唯一访问 Provider 的组件，把所有数据包装成不可变的 `ResearchDataset`（点时间快照），Skills 只消费快照。这保证了**相同快照 → 相同结果**（可重放），并防止未来函数。

---

## 能力状态

### ✅ 已实现

| 能力 | 说明 |
|------|------|
| **Planner** | LLM 结构化解析（受控）+ 规则回退；支持中英文、股票代码识别 |
| **DAG Scheduler** | 自动拓扑排序 + 并行执行独立 Skill |
| **Provider 隔离** | DataCollector 独占 Provider；Skills 只消费 ResearchDataset |
| **DataSnapshot** | 真正不可变快照（深层冻结为 tuple/只读 Mapping，防修改有测试）；完整 PIT 字段（as_of + 每条记录的 ann_date/trade_date）；DataCollector 按 as_of 过滤未来数据 |
| **Replay** | `python -m agent --replay runs/{run_id}` 完整 DAG 重放（禁 Provider，等价性校验有测试） |
| **Mock Provider** | sha256 稳定数据 + 真实交易日历 + growth/value/cyclical/abnormal 四画像 |
| **Tushare Provider** | `TushareSdkProvider`（SDK 实现）；已验证 daily/daily_basic；权限/限频优雅降级 |
| **基本面分析** | ROE、营收/利润增长、现金流质量、负债率、毛利率（含 provenance） |
| **估值分析** | PE/PB 相对分位评分（真实 PE/PB 优先） |
| **风险分析** | 年化波动率、最大回撤 |
| **组合评分** | 多策略加权综合评分 + 排名 |
| **Verifier** | severity(info/warning/error/fatal) + policy_mode(permissive/standard/strict)；未来函数→fatal 阻断 |
| **报告生成** | 结构化 Markdown（表格 + 详细分析 + 免责声明） |
| **受控 LLM** | 仅 NL→InvestmentRequest + 报告润色；不生成 DAG/不选工具/不计算 |
| **RunRecorder** | 每次运行 12 个 Artifact（含 manifest + execution_outputs + result_manifest + Mermaid 图） |
| **评估框架** | Agent 执行质量（agent-quality + trajectory）+ 实验性策略评估 |
| **工程规范** | pyproject.toml、ruff、mypy、pre-commit、GitHub Actions CI |

### 🔲 部分实现

| 能力 | 现状 | 差距 |
|------|------|------|
| 基本面（真实数据） | Mock 完整；Tushare 受账号权限限制 | 需更高 Tushare 积分访问 income/balance/cashflow |
| 技术分析 | 目录/元数据存在 | 无 analyzer 实现 |
| 回测 | `BacktestEngine` 计算标准指标 | 实验性：无 PIT/成本/滑点/停牌/幸存者偏差 |

### 🔲 规划中

| 能力 | 说明 |
|------|------|
| 真实 MCP Server | 将 Tushare 工具暴露为标准 MCP 协议 |
| 技术分析 Skill | 趋势/均线/动量/成交量 |
| 严格回测 | 需 point-in-time 数据 + 完整市场结构建模 |
| Web UI / Dashboard | Streamlit/Gradio |
| 向量记忆 | Embedding 语义检索 |

---

## 工程规范

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试（当前 278 个）
pytest tests/

# 静态检查
ruff check agent runtime strategies tools memory skills
mypy --explicit-package-bases agent runtime strategies tools memory skills

# 覆盖率
pytest tests/ --cov=agent --cov=runtime --cov=strategies --cov=tools

# pre-commit
pre-commit install
```

### 环境配置

复制 `.env.example` 为 `.env` 并填入你的值：

```bash
TUSHARE_TOKEN=your_token_here        # 真实数据需要
ANTHROPIC_API_KEY=your_key_here      # 受控 LLM（可选，缺省用规则）
AGENT_PROVIDER=mock                  # mock | tushare
AGENT_TOP_K=5
```

---

## 项目结构

```
agent/                    # 业务逻辑（投资领域）
├── planner.py           # LLM+规则 需求解析 → AnalysisPlan
├── executor.py          # Scheduler 桥接 + Skill 编排
├── data_collector.py    # 唯一 Provider 访问者 → ResearchDataset
├── verifier.py          # severity + policy_mode 校验
├── report_generator.py  # Markdown 报告
├── llm.py               # 受控 LLM（NL 解析 + 报告润色）
├── memory.py            # 7 层 Memory 外观
└── __main__.py          # CLI（run + replay）

runtime/                 # 框架核心（领域无关）
├── harness.py           # 生命周期管理（含 hook drain + verify gate）
├── scheduler.py         # DAG 并行调度
├── graph.py             # TaskGraph 验证 + 拓扑排序
├── snapshot.py          # DataSnapshot + ResearchDataset（PIT）
├── run_recorder.py      # runs/{run_id}/ 审计输出 + Mermaid 图
├── tracing/             # EventBus + AgentTrace + 格式化器
└── ...

strategies/              # 分析策略 Skills（underscore 目录为可导入模块）
├── fundamental_analysis/  # 基本面评分（已实现）
├── valuation_analysis/    # 估值评分（已实现）
├── risk_analysis/         # 风险评分（已实现）
└── base/                  # Skill SDK + 数据模型

tools/
├── providers.py          # MarketDataProvider 协议 + Mock + Tushare + Cached
├── registry.py           # 元数据驱动工具注册
└── backtest/engine.py    # 实验性回测引擎

evaluations/
├── cases/                # 可复现端到端案例 + Tushare 真实验证记录
├── agent-quality/        # 执行质量评估
├── trajectory/           # 轨迹评估
└── historical-backtest/  # 实验性策略回测

runs/                     # 运行时产物（gitignored）
```

---

## 关键架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Provider 隔离 | DataCollector 独占 Provider，Skills 消费 ResearchDataset | 可重放、防未来函数、可测试 |
| 数据时间性 | DataSnapshot（as_of/hash/时间字段） | 支持 point-in-time 分析 |
| Planner | 受控 LLM + 规则回退 | LLM 只填结构化请求，DAG 模板确定性 |
| Verifier | severity + policy_mode | 未来函数/权重错误按策略阻断流程 |
| 重试边界 | Tool 层网络抖动，Scheduler 节点失败 | 避免多层重试放大 |
| 运行审计 | 9 文件（含 agent_trace + Mermaid） | 可审计、可复现、可排查 |

---

## 真实 Tushare 验证（2026-07-31）

- **daily / daily_basic**：真实数据可用（如 600519.SH 2025-01-15 收盘 1471.27）
- **stock_basic**：免费档小时限频 → 优雅降级为代码 stub，分析继续
- **income/balance/cashflow**：当前账号无权限 → trace 记录为错误，基本面降级
- 真实端到端 run 捕获 485 条真实行情，风险指标基于真实数据

详见 [evaluations/cases/tushare_live_validation.md](evaluations/cases/tushare_live_validation.md)。

---

## 已知限制

1. **Mock 数据**：确定性生成，不反映真实市场
2. **基本面真实数据受限**：当前 Tushare 账号无财务接口权限
3. **LLM 受控**：仅 NL 解析 + 报告润色，未接入其他 LLM 能力
4. **技术分析未实现**：仅基本面/估值/风险
5. **回测实验性**：无 PIT/成本/滑点/停牌/退市/幸存者偏差，勿用于投资结论
6. **单进程**：Scheduler 为单进程 asyncio 并发

---

## 测试

```bash
# 全部 278 个测试
pytest tests/

# 确定性指标计算
pytest tests/strategies/test_fundamental_metrics.py

# Planner + LLM 解析
pytest tests/strategies/test_planner.py tests/agent/test_llm.py

# Verifier severity/policy
pytest tests/agent/test_verifier.py

# 端到端（Mock）+ 重放
pytest tests/evaluations/test_mock_e2e.py

# 回测指标（实验性）
pytest tests/tools/test_backtest.py

# 运行时（图/调度/工作流）
pytest tests/runtime/
```

---

## 参考文献

- [设计文档](docs/design.md)
- [演进路线图](docs/evolutionary-roadmap.md)
- [ADR-001~014](docs/adr/)
  - ADR-012: 统一 trace_span 可观测性
  - ADR-013: Point-in-Time 数据字段 + as_of 过滤
  - ADR-014: Deterministic Replay + content_hash/snapshot_hash 拆分
- [评估框架](evaluations/README.md)
- [可复现案例](evaluations/cases/README.md)
- [Tushare 真实验证](evaluations/cases/tushare_live_validation.md)
- [engineering-ai-standards](engineering-ai-standards/)
