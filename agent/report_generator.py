# Agent Report Generator — produces structured Markdown investment report
#
# Input: plan, results dict (step_id → output), verification
# Output: InvestmentReport with formatted Markdown

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from strategies.base.models import InvestmentReport


class ReportGenerator:
    """Produces structured Markdown investment reports."""

    DISCLAIMER = (
        "> ⚠️ **免责声明**：本报告由 AI 自动生成，仅供研究参考，不构成投资建议。\n"
        "> 过往表现不代表未来收益。投资有风险，决策需谨慎。\n"
        "> 数据来源：MockMarketDataProvider（模拟数据）。\n"
    )

    def __init__(self, agent_version: str = "2.0.0"):
        self.agent_version = agent_version

    async def generate(
        self,
        plan: Any,
        results: dict[int, Any],
        verification: Any,
    ) -> InvestmentReport:
        """Generate a structured report from analysis results."""
        report_id = f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Extract step outputs
        data_output = self._extract_step(results, "step-1")
        fund_output = self._extract_step(results, "step-2")
        val_output = self._extract_step(results, "step-3")
        risk_output = self._extract_step(results, "step-4")
        port_output = self._extract_step(results, "step-5")

        market_overview = self._build_market_overview(data_output)
        candidates = self._build_candidates(fund_output, val_output, risk_output)

        return InvestmentReport(
            report_id=report_id,
            agent_version=self.agent_version,
            user_requirement=self._format_requirement(plan),
            market_overview=market_overview,
            candidates=candidates,
            portfolio_suggestion=self._format_portfolio(candidates),
            disclaimer=str(self.DISCLAIMER),
        )

    def format_markdown(self, report: InvestmentReport) -> str:
        """Render the report as a Markdown string."""
        lines = [
            f"# 📊 投资研究报告",
            f"",
            f"**报告编号：** {report.report_id}",
            f"**生成时间：** {report.created_at[:19]}",
            f"**Agent 版本：** {report.agent_version}",
            f"",
            f"---",
            f"",
            f"## 一、用户需求",
            f"",
            f"{report.user_requirement}",
            f"",
        ]

        # Market overview
        if report.market_overview:
            lines.extend([
                f"## 二、市场概况",
                f"",
                report.market_overview,
                f"",
            ])

        # Candidate table
        lines.extend([f"## 三、候选股票评分及排名", f""])

        if report.candidates:
            lines.append("| 排名 | 股票代码 | 股票名称 | 行业 | 基本面 | 估值 | 风险 | 综合 |")
            lines.append("|------|----------|----------|------|--------|------|------|------|")
            for i, c in enumerate(report.candidates, 1):
                rank_icon = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f" {i} "
                fund = getattr(c, "fundamental_score", 0)
                val = getattr(c, "val_score", 0)
                risk = getattr(c, "risk_score", 0)
                comp = getattr(c, "composite_score", 0)
                lines.append(f"| {rank_icon} | {c.ts_code} | {c.name} | {c.industry} | {fund:.2f} | {val:.2f} | {risk:.2f} | **{comp:.2f}** |")

            # Detail
            for c in report.candidates:
                lines.extend([
                    f"",
                    f"### {c.ts_code} {c.name}（{c.industry}）",
                    f"",
                    f"- **基本面评分：** {getattr(c, 'fundamental_score', 0):.2f}",
                    f"- **估值评分：** {getattr(c, 'val_score', 0):.2f}",
                    f"- **风险评分：** {getattr(c, 'risk_score', 0):.2f}",
                    f"- **综合评分：** {getattr(c, 'composite_score', 0):.2f}",
                ])
                explanation = getattr(c, "explanation", "")
                if explanation:
                    lines.extend([
                        f"",
                        f"📝 **分析说明**",
                        f"",
                        f"```",
                        explanation[:500],
                        f"```",
                    ])

        lines.extend([
            f"",
            f"## 四、组合建议",
            f"",
            report.portfolio_suggestion,
            f"",
            f"---",
            f"",
            f"## 免责声明",
            f"",
            report.disclaimer,
            f"",
        ])

        return "\n".join(lines)

    # ─── Internal helpers ───────────────────────────────────────────────

    def _build_market_overview(self, data_output: Optional[dict]) -> str:
        if not data_output:
            return "未获取到市场数据。"
        count = data_output.get("stock_count", 0)
        return (
            f"共从股票池中获取 **{count}** 只股票数据。\n\n"
        )

    def _build_candidates(self, fund, val, risk) -> list[Any]:
        """Merge skill outputs into candidate list sorted by composite score."""
        from dataclasses import dataclass

        @dataclass
        class Candidate:
            ts_code: str
            name: str
            industry: str
            fundamental_score: float = 0.0
            val_score: float = 0.0
            risk_score: float = 0.0
            composite_score: float = 0.0
            explanation: str = ""
            warnings: list[str] = None

        fund_profiles = self._get_profiles(fund)
        val_profiles = self._get_profiles(val)
        risk_profiles = self._get_profiles(risk)

        stock_map: dict[str, Candidate] = {}

        for p in fund_profiles:
            stock_map[p.ts_code] = Candidate(
                ts_code=p.ts_code,
                name=getattr(p, "name", p.ts_code),
                industry=getattr(p, "industry", ""),
                fundamental_score=getattr(p, "score", 0),
                explanation=getattr(p, "summary", ""),
                warnings=getattr(p, "warnings", []),
            )

        for p in val_profiles:
            ts = p.get("ts_code") if isinstance(p, dict) else getattr(p, "ts_code", "")
            if ts in stock_map:
                stock_map[ts].val_score = p.get("score") if isinstance(p, dict) else getattr(p, "score", 0)

        for p in risk_profiles:
            ts = p.ts_code if not isinstance(p, dict) else p.get("ts_code", "")
            if ts in stock_map:
                stock_map[ts].risk_score = p.score if not isinstance(p, dict) else p.get("score", 0)

        # Compute composite
        for c in stock_map.values():
            w_fund, w_val, w_risk = 0.40, 0.25, 0.35
            c.composite_score = round(
                c.fundamental_score * w_fund +
                c.val_score * w_val +
                c.risk_score * w_risk,
                4,
            )

        candidates = sorted(stock_map.values(), key=lambda c: c.composite_score, reverse=True)
        return candidates[:5]

    @staticmethod
    def _get_profiles(output: Optional[dict]) -> list:
        if output is None:
            return []
        data = output.get("data", output)
        if isinstance(data, dict):
            return data.get("profiles", [])
        return []

    @staticmethod
    def _extract_step(results: dict, step_id: str) -> Optional[dict]:
        """Extract a single step's output from results dict."""
        raw = results.get(step_id)
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        # SkillOutput objects
        if hasattr(raw, "data"):
            return getattr(raw, "data", raw)
        return {"raw": raw}

    def _format_requirement(self, plan: Any) -> str:
        obj = getattr(plan, "objective", str(plan))
        weights = getattr(plan, "strategy_weights", {})
        risk = getattr(plan, "risk_preference", "medium")
        w_str = ", ".join(f"{k}={v:.0%}" for k, v in weights.items()) if weights else "默认权重"
        return f"{obj}\n\n策略权重: {w_str}\n风险偏好: {risk}"

    def _format_portfolio(self, candidates: list) -> str:
        if not candidates:
            return "无候选股票。"
        top = candidates[0]
        return (
            f"基于综合评分，建议重点关注 **{top.name}（{top.ts_code}）**，"
            f"综合评分 {top.composite_score:.2f}。\n\n"
            f"前 5 只候选股票按综合评分排序如上表所示。"
        )
