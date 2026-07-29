# Tushare Investment Research Agent

An AI Agent system for automated investment research. Built as a **reference implementation** of the [engineering-ai-standards](engineering-ai-standards/) agent framework — demonstrating skill-based architecture, DAG workflow orchestration, MCP-style tool integration, multi-strategy analysis, verification loops, and trajectory evaluation.

> ⚠️ **免责声明**：本系统生成的报告仅供研究参考，不构成投资建议。当前使用 Mock 模拟数据，尚未接入真实 TuShare 数据。过往表现不代表未来收益。

---

## 快速开始

```bash
# 运行投资研究（Mock 数据，无需 API Key）
python -m agent --requirement "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"

# 交互模式
python -m agent --interactive

# 带执行跟踪
python -m agent --requirement "筛选5只低风险股票" --trace
```

### 示例输出

运行 `python -m agent --requirement "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"`：

```
# 📊 投资研究报告

## 一、用户需求
stock_pool=csi300 objective=quality risk=medium top_k=5
策略权重: fundamental-analysis=50%, valuation-analysis=20%, risk-analysis=20%, technical-analysis=10%

## 二、市场概况
共从股票池中获取 15 只股票数据。

## 三、候选股票评分及排名
| 排名 | 股票代码 | 股票名称 | 行业 | 基本面 | 估值 | 风险 | 综合 |
|------|----------|----------|------|--------|------|------|------|
| 🥇 | 600900.SH | 长江电力 | 电力 | 0.61 | 0.77 | 0.56 | **0.63** |
| 🥈 | 002415.SZ | 海康威视 | 计算机 | 0.49 | 0.83 | 0.56 | **0.60** |
...

📝 分析说明
基本面评分: 0.61/1.00
  ROE: 80% → 贡献0.200 (ROE=15.2%)
  营收增长: 40% → 贡献0.080 (平均增速=0.0%)
  ...
```

---

## 系统架构

```
                        ┌──────────────────┐
                        │     User CLI      │
                        └────────┬─────────┘
                                 │
                    ┌────────────┴────────────┐
                    │         Harness          │
                    │  Plan→Execute→Verify→Rpt│
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
     │   Scheduler     │ │   Verifier     │ │ ReportGenerator│
     │ (DAG / 并行)    │ │ (5-phase)      │ │ (Markdown)     │
     └───────┬────────┘ └────────────────┘ └────────────────┘
             │
    ┌────────┴────────┐
    │  Skill Executor  │
    │  (ReAct Loop)    │
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │ MarketDataProvider│  ← 抽象数据接口
    │ (Mock|Tushare)   │
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │  15 CSI 300      │  ← Mock 股票池
    │  Mock 数据       │
    └─────────────────┘
```

---

## 能力状态

### ✅ 已实现能力

| 能力 | 说明 |
|------|------|
| **Planner** | 规则解析 + Pydantic 结构化输出，支持中英文需求 |
| **MarketDataProvider** | `MarketDataProvider` 抽象协议，12 只股票 Mock 数据 |
| **基本面分析** | ROE、营收/利润增长率、现金流质量、负债率、毛利率 |
| **估值分析** | PE/PB 相对分位评分 |
| **风险分析** | 年化波动率、最大回撤评分 |
| **组合评分** | 多策略加权综合评分 |
| **Verifier** | 5 阶段验证（数据新鲜度、未来函数、权重、缺失数据、证据） |
| **Report Generator** | Markdown 表格 + 详细分析说明 |
| **DAG Scheduler** | 自动检测并行节点，分层并发执行 |
| **Skill SDK** | 5 阶段生命周期（metadata/plan/execute/verify/summarize） |
| **Tool Registry** | 元数据驱动的工具注册 + Schema 校验 + 缓存 + 限流 |
| **Memory 7-tier** | Working/Episodic/Semantic/Research/ToolCache/Execution/Artifacts |
| **EventBus** | 25+ 事件类型，支持 subscribe/replay/export |
| **Trajectory Evaluation** | 6 维度执行路径评分 |
| **CLI 一键运行** | `python -m agent --requirement "..."` |

### 🔲 规划能力

| 能力 | 依赖 | 优先级 |
|------|------|--------|
| TuShare 真实数据接入 | Tushare Token + `OfficialTushareMCPProvider` | 高 |
| LLM 集成（Planner/Verifier） | LLM API Key + structured output | 中 |
| 技术分析 Skill | 需补充价格形态识别 | 中 |
| 回测引擎 | 需历史持仓数据 | 低 |
| Web UI / Dashboard | Streamlit/Gradio | 低 |
| CI Pipeline | GitHub Actions | 低 |

---

## 测试

```bash
# 运行全部 206 个测试
pytest tests/

# 确定性指标计算测试
pytest tests/strategies/test_fundamental_metrics.py

# 集成测试
pytest tests/evaluations/test_mock_e2e.py

# Planner 测试
pytest tests/strategies/test_planner.py
```

---

## 项目结构

```
agent/                    # 业务逻辑（投资领域）
├── planner.py           # 需求解析 → AnalysisPlan
├── executor.py          # Scheduler 桥接 + Skill 编排
├── verifier.py          # 5 阶段验证
├── report_generator.py  # Markdown 报告
├── memory.py            # 7 层 Memory 外观
└── __main__.py          # CLI 入口

runtime/                 # 框架核心（领域无关）
├── harness.py           # 生命周期管理
├── scheduler.py         # DAG 并行调度
├── graph.py             # TaskGraph 验证 + 拓扑排序
├── workflow.py          # YAML → TaskGraph
├── models.py            # 事件/状态/图模型
├── errors.py            # 错误分类
└── tracing/             # EventBus + 格式化器

strategies/              # 分析策略 Skills
├── fundamental_analysis/  # 基本面评分（已实现）
├── valuation_analysis/    # 估值评分（已实现）
├── risk_analysis/         # 风险评分（已实现）
└── base/                  # Skill SDK + 数据模型

tools/
├── providers.py          # MarketDataProvider 协议 + Mock
├── registry.py           # 元数据驱动工具注册
└── tushare-mcp/          # TuShare MCP 扩展位置

memory/                   # 7 层内存系统
├── working.py / episodic.py / semantic.py / ...
```

---

## 关键架构决策

| 决策 | 选择 | 替代方案 | 理由 |
|------|------|----------|------|
| 数据抽象 | `MarketDataProvider` 协议 | 直接调用 Tushare | 可测试性，技能不绑定具体数据源 |
| Planner | 规则解析 + 模板化 Plan | LLM 生成任意 Graph | 可控性，确定性测试 |
| 重试边界 | Tool 层处理网络抖动，Scheduler 处理节点失败 | 多层重试 | 避免指数放大 |
| 异步 Hook | `ensure_future` + drain 机制 | fire-and-forget | 不阻塞主流程同时记录错误 |
| 报告格式 | Markdown | PDF/HTML | 可直接查看，无需额外渲染 |
| 模拟数据 | MockMarketDataProvider（15 只 CSI 300） | 全量 A 股 | 测试确定性，运行快速 |

---

## 已知限制

1. **Mock 数据**：当前使用确定性哈希生成模拟财务和价格数据，不反映真实市场
2. **无 LLM**：Planner 使用规则解析，Skills 使用算法计算，未接入 LLM
3. **技术分析未实现**：只有基本面/估值/风险，技术分析 Skill 尚为占位
4. **Stock 池固定**：Mock 数据固定 15 只代表性股票
5. **无回测验证**：策略评分未经过历史回测验证
6. **单进程**：Scheduler 目前为单进程 asyncio 并发

---

## 测试结果

```
206 passed in 4.20s
```

| 测试类别 | 数量 | 内容 |
|----------|------|------|
| Runtime (Graph/Scheduler/Workflow) | 55 | 图验证、拓扑排序、DAG 执行、重试、超时 |
| Memory (7 tiers) | 67 | 读写、搜索、TTL、过期、断点续跑 |
| Skills SDK | 19 | 生命周期、适配器、自检 |
| Tools Registry | 20 | 注册、发现、调用、缓存、限流 |
| Trajectory Evaluation | 17 | 维度评分、全量评估、空 Trace |
| Fundamental Metrics | 15 | ROE、增长率、现金流、负债率等确定性计算 |
| Planner | 7 | 需求分类、权重、依赖排序 |
| End-to-End | 4 | Planner→Executor→Report 全链路 |
| **Total** | **206** | |

---

## 参考文献

- [设计文档](docs/design.md)
- [演进路线图](docs/evolutionary-roadmap.md)
- [ADR-001~011](docs/adr/)
- [engineering-ai-standards](engineering-ai-standards/)
