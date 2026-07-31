# Tushare Investment Research Agent

An AI Agent system for automated investment research, built as a **reference implementation** of the [engineering-ai-standards](engineering-ai-standards/) agent framework. It demonstrates a bounded, observable, reproducible research workflow: requirement parsing → DAG scheduling → skill-based multi-strategy analysis → verification → Markdown report.

> ⚠️ **免责声明**：本系统生成的报告仅供研究参考，不构成投资建议。默认使用 Mock 模拟数据；接入真实 TuShare 数据需要 API Token。策略回测为实验性，未经过严格 point-in-time / 成本 / 幸存者偏差处理。

---

## 快速开始

```bash
# 运行投资研究（Mock 数据，无需 API Key）
python -m agent --requirement "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"

# 单只股票研究（自动识别股票代码）
python -m agent --requirement "分析 600519.SH"

# 交互模式
python -m agent --interactive

# 使用真实 Tushare 数据（需要 TUSHARE_TOKEN）
export TUSHARE_TOKEN=your_token_here
python -m agent --requirement "分析 600519.SH" --provider tushare
```

每次运行会在 `runs/{run_id}/` 生成完整的审计记录：
`request.json`、`plan.json`、`tool_trace.jsonl`、`data_snapshot.json`、`verification.json`、`report.md`、`meta.json`。

### 示例输出

运行 `python -m agent --requirement "分析 600519.SH"` 会生成：

```
# 📊 投资研究报告
## 一、用户需求
stock_pool=single objective=mixed risk=medium top_k=5
## 二、市场概况
共从股票池中获取 1 只股票数据。
## 三、候选股票评分及排名
| 排名 | 股票代码 | 股票名称 | 行业 | 基本面 | 估值 | 风险 | 综合 |
| 🥇 | 600519.SH | 贵州茅台 | 白酒 | 0.59 | 0.83 | 0.56 | **0.64** |
📝 分析说明
  基本面评分: 0.59/1.00
  ROE: 40% → 贡献0.100 (ROE=6.2%)
  ...
## 四、组合建议
## 免责声明
```

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
                │  (retry, timeout, hooks) │
                └────────────┬────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐   ┌────────────────┐   ┌────────────────┐
│  Planner      │   │   Scheduler     │   │  Verifier       │
│ (rules→plan) │   │ (DAG / parallel)│   │ (5-phase)       │
└──────────────┘   └───────┬────────┘   └────────────────┘
                           │
                  ┌────────┴────────┐
                  │   Skill Executor │
                  │  (fund/val/risk) │
                  └────────┬────────┘
                           │
                  ┌────────┴────────┐
                  │ MarketDataProvider │  ← abstract
                  │ (Mock | Tushare)   │
                  └────────┬────────┘
                           │
                  ┌────────┴────────┐
                  │  DataSnapshot    │  ← point-in-time wrapper
                  │  (as_of/hash)    │
                  └─────────────────┘
```

每次运行结束后，`RunRecorder` 将完整记录写入 `runs/{run_id}/`，保证可审计、可复现、可排查。

---

## 能力状态

### ✅ 已实现

| 能力 | 说明 |
|------|------|
| **Planner** | 规则解析 + 模板化 Plan；支持中英文需求、股票代码识别（`分析 600519.SH`） |
| **DAG Scheduler** | 自动拓扑排序 + 并行执行独立 Skill |
| **MarketDataProvider** | 抽象协议；Mock（15 只股票）+ Tushare 真实实现 + Cached 包装 |
| **基本面分析** | ROE、营收/利润增长率、现金流质量、负债率、毛利率（含 provenance） |
| **估值分析** | PE/PB 相对分位评分 |
| **风险分析** | 年化波动率、最大回撤（Sigmoid 评分） |
| **组合评分** | 多策略加权综合评分 + 排名 |
| **Verifier** | 数据新鲜度、未来函数、权重、缺失数据、证据链 5 阶段校验 |
| **报告生成** | 结构化 Markdown（表格 + 详细分析 + 免责声明） |
| **RunRecorder** | 每次运行 7 个审计文件（request/plan/tool_trace/snapshot/verification/report/meta） |
| **DataSnapshot** | 统一数据快照（as_of/source/query_params/data_hash/version + 时间字段） |
| **工程规范** | pyproject.toml、ruff、mypy、pre-commit、GitHub Actions CI |
| **评估框架** | 执行质量评估（agent-quality + trajectory）+ 实验性策略评估 |

### 🔲 部分实现

| 能力 | 现状 | 差距 |
|------|------|------|
| Tushare 数据 | `OfficialTushareMCPProvider` 已实现 | 无真实 Token 环境验证；MCP 协议包装尚未做 |
| 技术分析 | 目录/元数据存在 | 无 analyzer 实现 |
| 回测 | `tools/backtest/engine.py` 骨架 | 未实现，且明确标注实验性 |
| LLM 集成 | 未接入 | Planner/Verifier 当前为规则/算法驱动 |

### 🔲 规划中

| 能力 | 说明 |
|------|------|
| 真实 MCP Server | 将 Tushare 工具暴露为标准 MCP 协议 |
| 技术分析 Skill | 趋势/均线/动量/成交量 |
| 回测引擎 | 需要严格 point-in-time、手续费、滑点、停牌、退市、幸存者偏差处理 |
| Web UI / Dashboard | Streamlit/Gradio |
| 向量记忆 | Embedding 语义检索 |

---

## 工程规范

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试（当前 206 个）
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
AGENT_PROVIDER=mock                  # mock | tushare
AGENT_TOP_K=5
```

---

## 项目结构

```
agent/                    # 业务逻辑（投资领域）
├── planner.py           # 需求解析 → AnalysisPlan
├── executor.py          # Scheduler 桥接 + Skill 编排 + DataSnapshot
├── verifier.py          # 5 阶段验证
├── report_generator.py  # Markdown 报告
├── memory.py            # 7 层 Memory 外观
└── __main__.py          # CLI 入口（含 RunRecorder）

runtime/                 # 框架核心（领域无关）
├── harness.py           # 生命周期管理（含 hook drain）
├── scheduler.py         # DAG 并行调度
├── graph.py             # TaskGraph 验证 + 拓扑排序
├── snapshot.py          # DataSnapshot（point-in-time 数据包装）
├── run_recorder.py      # runs/{run_id}/ 审计输出
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
└── tushare-mcp/          # MCP 扩展位置（待实现）

evaluations/
├── cases/                # 三个可复现端到端案例
├── agent-quality/        # 执行质量评估
├── trajectory/           # 轨迹评估
└── historical-backtest/  # 实验性策略回测（未实现）

runs/                     # 运行时产物（gitignored）
```

---

## 关键架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据抽象 | `MarketDataProvider` 协议 | 技能不绑定具体数据源，可测试、可切换 |
| Planner | 规则解析 + 模板化 Plan | 可控、可复现，不给 LLM 任意生成执行图 |
| 数据时间性 | `DataSnapshot`（as_of/hash） | 防止未来函数，支持回放审计 |
| 重试边界 | Tool 层处理网络抖动，Scheduler 处理节点失败 | 避免多层重试放大调用 |
| 异步 Hook | `ensure_future` + drain | 不阻塞主流程，错误写入 logger + 计数 |
| 运行审计 | `RunRecorder` 每次运行 7 个文件 | 可审计、可复现、可排查 |

---

## 已知限制

1. **Mock 数据**：默认使用确定性哈希生成的模拟财务/价格数据，不反映真实市场
2. **Tushare 未在真实环境验证**：`OfficialTushareMCPProvider` 已实现，但当前环境无有效 Token，未经真实数据验证
3. **无 LLM**：Planner 为规则驱动，Skills 为算法驱动，未接入 LLM structured output
4. **技术分析未实现**：仅基本面/估值/风险
5. **回测为实验性**：未处理 point-in-time、手续费、滑点、停牌、退市、幸存者偏差，勿用于投资结论
6. **单进程**：Scheduler 为单进程 asyncio 并发

---

## 测试

```bash
# 全部 206 个测试
pytest tests/

# 确定性指标计算
pytest tests/strategies/test_fundamental_metrics.py

# Planner 解析
pytest tests/strategies/test_planner.py

# 端到端（Mock）
pytest tests/evaluations/test_mock_e2e.py

# 运行时（图/调度/工作流）
pytest tests/runtime/
```

---

## 参考文献

- [设计文档](docs/design.md)
- [演进路线图](docs/evolutionary-roadmap.md)
- [ADR-001~011](docs/adr/)
- [评估框架](evaluations/README.md)
- [可复现案例](evaluations/cases/README.md)
- [engineering-ai-standards](engineering-ai-standards/)
