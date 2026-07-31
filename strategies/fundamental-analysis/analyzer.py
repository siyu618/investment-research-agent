# Fundamental Analysis — real metric calculation with provenance
#
# Calculates: ROE, revenue growth, profit growth, cash flow quality,
# debt ratio, gross margin trend.
#
# Each metric carries full provenance: metric, value, unit, period,
# available_at, source, tool_call_id.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from skills.base.skill_sdk import (
    SkillLifecycle,
    SkillMetadata,
    SkillOutput,
    SkillPlan,
    SkillVerdict,
)
from tools.providers import FinancialStatement, MarketDataProvider, StockBasic

# ─── Provenance ───────────────────────────────────────────────────────────


@dataclass
class MetricProvenance:
    """Traceable evidence for a single metric value."""
    metric: str
    value: float
    unit: str
    period: str                      # e.g. "2024" or "2024-2025"
    available_at: str                # ISO date of source data
    source: str                      # "income_statement" | "balance_sheet" | ...
    tool_call_id: str = ""           # Trace ID if from tool invocation
    warning: str = ""                # Data quality warning (e.g. "stale", "estimated")

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "period": self.period,
            "available_at": self.available_at,
            "source": self.source,
            "tool_call_id": self.tool_call_id,
            "warning": self.warning,
        }


@dataclass
class CompanyFundamentalProfile:
    """Aggregated fundamental analysis result for one stock."""
    ts_code: str
    name: str
    industry: str

    metrics: list[MetricProvenance] = field(default_factory=list)
    score: float = 0.5               # 0-1 composite
    confidence: float = 0.5

    revenue_trend: str = ""          # "growing" | "stable" | "declining" | "unknown"
    profit_trend: str = ""
    summary: str = ""

    missing_data_flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── Calculation Functions ────────────────────────────────────────────────


def compute_roe(stmts: list[FinancialStatement]) -> list[MetricProvenance]:
    """Return ROE per annual period: net_profit / equity."""
    results = []
    for s in sorted(stmts, key=lambda x: x.end_date):
        if s.report_type != "annual" or s.net_profit is None or s.equity is None or s.equity == 0:
            continue
        roe = round(s.net_profit / s.equity, 4)
        results.append(MetricProvenance(
            metric="roe",
            value=roe,
            unit="ratio",
            period=s.end_date[:4],
            available_at=f"{s.end_date[:4]}-12-31",
            source="financial_summary",
            warning="" if 0 < roe < 1 else "异常值: ROE超出正常范围",
        ))
    return results


def compute_revenue_growth(stmts: list[FinancialStatement]) -> list[MetricProvenance]:
    """Year-over-year revenue growth rate."""
    annuals = sorted(
        [s for s in stmts if s.report_type == "annual" and s.revenue is not None],
        key=lambda x: x.end_date,
    )
    results = []
    for i in range(1, len(annuals)):
        prev, curr = annuals[i - 1], annuals[i]
        prev_rev = prev.revenue
        curr_rev = curr.revenue
        if prev_rev and prev_rev != 0 and curr_rev is not None:
            growth = (curr_rev - prev_rev) / prev_rev
            results.append(MetricProvenance(
                metric="revenue_growth",
                value=round(growth, 4),
                unit="ratio",
                period=f"{prev.end_date[:4]}-{curr.end_date[:4]}",
                available_at=f"{curr.end_date[:4]}-12-31",
                source="income_statement",
                warning="缺失前期数据" if prev_rev is None else "",
            ))
    return results


def compute_profit_growth(stmts: list[FinancialStatement]) -> list[MetricProvenance]:
    """Year-over-year net profit growth rate."""
    annuals = sorted(
        [s for s in stmts if s.report_type == "annual" and s.net_profit is not None],
        key=lambda x: x.end_date,
    )
    results = []
    for i in range(1, len(annuals)):
        prev, curr = annuals[i - 1], annuals[i]
        prev_np = prev.net_profit
        curr_np = curr.net_profit
        if prev_np and prev_np != 0 and curr_np is not None:
            growth = (curr_np - prev_np) / abs(prev_np)
            results.append(MetricProvenance(
                metric="net_profit_growth",
                value=round(growth, 4),
                unit="ratio",
                period=f"{prev.end_date[:4]}-{curr.end_date[:4]}",
                available_at=f"{curr.end_date[:4]}-12-31",
                source="income_statement",
            ))
    return results


def compute_cashflow_quality(stmts: list[FinancialStatement]) -> list[MetricProvenance]:
    """Operating cash flow / net profit ratio."""
    results = []
    for s in sorted(stmts, key=lambda x: x.end_date):
        if s.report_type != "annual":
            continue
        if s.operating_cash_flow is None or s.net_profit is None or s.net_profit == 0:
            continue
        ratio = round(s.operating_cash_flow / s.net_profit, 4)
        warning = ""
        if ratio < 0:
            warning = "经营现金流为负"
        elif ratio < 0.5:
            warning = "现金流覆盖利润不足50%"
        elif ratio > 3:
            warning = "现金流异常偏高"
        results.append(MetricProvenance(
            metric="ocf_to_net_profit",
            value=ratio,
            unit="ratio",
            period=s.end_date[:4],
            available_at=f"{s.end_date[:4]}-12-31",
            source="cashflow",
            warning=warning,
        ))
    return results


def compute_debt_ratio(stmts: list[FinancialStatement]) -> list[MetricProvenance]:
    """资产负债率 = total_liabilities / total_assets per period."""
    results = []
    for s in sorted(stmts, key=lambda x: x.end_date):
        if s.report_type != "annual":
            continue
        if s.total_liabilities is None or s.total_assets is None or s.total_assets == 0:
            continue
        ratio = round(s.total_liabilities / s.total_assets, 4)
        warning = ""
        if ratio > 0.85:
            warning = "资产负债率超过85%，财务风险较高"
        elif ratio < 0.05:
            warning = "资产负债率过低，可能资金利用不足"
        results.append(MetricProvenance(
            metric="debt_ratio",
            value=ratio,
            unit="ratio",
            period=s.end_date[:4],
            available_at=f"{s.end_date[:4]}-12-31",
            source="balance_sheet",
            warning=warning,
        ))
    return results


def compute_gross_margin_change(stmts: list[FinancialStatement]) -> list[MetricProvenance]:
    """毛利率变化趋势."""
    annuals = sorted(
        [s for s in stmts if s.report_type == "annual" and s.gross_margin is not None],
        key=lambda x: x.end_date,
    )
    results = []
    for s in annuals:
        gm = s.gross_margin
        if gm is None:
            continue
        results.append(MetricProvenance(
            metric="gross_margin",
            value=round(gm, 4),
            unit="ratio",
            period=s.end_date[:4],
            available_at=f"{s.end_date[:4]}-12-31",
            source="income_statement",
        ))
    return results


# ─── Scoring ──────────────────────────────────────────────────────────────


def compute_fundamental_score(
    roes: list[MetricProvenance],
    rev_growth: list[MetricProvenance],
    profit_growth: list[MetricProvenance],
    cf_quality: list[MetricProvenance],
    debt_ratios: list[MetricProvenance],
    margins: list[MetricProvenance],
) -> tuple[float, float, str]:
    """Compute composite fundamental score and confidence.

    Returns:
        (score 0-1, confidence 0-1, explanation)
    """
    score_parts = []

    # ROE scoring (weight 25%)
    if roes:
        latest_roe = roes[-1].value
        if latest_roe > 0.20:
            roe_score = 1.0
        elif latest_roe > 0.15:
            roe_score = 0.8
        elif latest_roe > 0.10:
            roe_score = 0.6
        elif latest_roe > 0.05:
            roe_score = 0.4
        else:
            roe_score = 0.2
        score_parts.append(("ROE", roe_score * 0.25, f"ROE={latest_roe:.1%}"))
    else:
        score_parts.append(("ROE", 0.0, "无ROE数据"))

    # Revenue growth scoring (weight 20%)
    if rev_growth:
        avg_growth = sum(m.value for m in rev_growth) / len(rev_growth)
        if avg_growth > 0.15:
            rev_score = 1.0
        elif avg_growth > 0.08:
            rev_score = 0.8
        elif avg_growth > 0.03:
            rev_score = 0.6
        elif avg_growth > -0.03:
            rev_score = 0.4
        else:
            rev_score = 0.1
        score_parts.append(("营收增长", rev_score * 0.20, f"平均增速={avg_growth:.1%}"))
    else:
        score_parts.append(("营收增长", 0.0, "无营收数据"))

    # Profit growth scoring (weight 20%)
    if profit_growth:
        avg_pg = sum(m.value for m in profit_growth) / len(profit_growth)
        if avg_pg > 0.15:
            pg_score = 1.0
        elif avg_pg > 0.08:
            pg_score = 0.8
        elif avg_pg > 0.03:
            pg_score = 0.6
        elif avg_pg > -0.03:
            pg_score = 0.4
        else:
            pg_score = 0.1
        score_parts.append(("净利润增长", pg_score * 0.20, f"平均增速={avg_pg:.1%}"))
    else:
        score_parts.append(("净利润增长", 0.0, "无数据"))

    # Cash flow quality (weight 15%)
    if cf_quality:
        latest_cf = cf_quality[-1].value
        if latest_cf >= 1.0:
            cf_score = 1.0
        elif latest_cf >= 0.7:
            cf_score = 0.8
        elif latest_cf >= 0.5:
            cf_score = 0.6
        elif latest_cf >= 0:
            cf_score = 0.3
        else:
            cf_score = 0.0
        score_parts.append(("现金流质量", cf_score * 0.15, f"OCF/NP={latest_cf:.2f}"))
    else:
        score_parts.append(("现金流质量", 0.0, "无现金流数据"))

    # Debt ratio scoring (weight 10%)
    if debt_ratios:
        latest_debt = debt_ratios[-1].value
        if latest_debt <= 0.30:
            debt_score = 1.0
        elif latest_debt <= 0.50:
            debt_score = 0.8
        elif latest_debt <= 0.65:
            debt_score = 0.6
        elif latest_debt <= 0.80:
            debt_score = 0.4
        else:
            debt_score = 0.1
        score_parts.append(("负债率", debt_score * 0.10, f"负债率={latest_debt:.1%}"))
    else:
        score_parts.append(("负债率", 0.0, "无数据"))

    # Margin trend (weight 10%)
    if margins:
        trend = margins[-1].value - margins[0].value if len(margins) > 1 else 0
        if margins[-1].value > 0.40:
            margin_score = 1.0
        elif margins[-1].value > 0.25:
            margin_score = 0.8
        elif margins[-1].value > 0.15:
            margin_score = 0.6
        elif margins[-1].value > 0.05:
            margin_score = 0.4
        else:
            margin_score = 0.2
        trend_note = f", 趋势变动={trend:+.1%}" if abs(trend) > 0.01 else ""
        score_parts.append(("毛利率", margin_score * 0.10, f"最新毛利率={margins[-1].value:.1%}{trend_note}"))
    else:
        score_parts.append(("毛利率", 0.0, "无毛利数据"))

    # Total score
    total = sum(weighted for _, weighted, _ in score_parts)

    # Confidence: based on data completeness
    filled = sum(1 for _, w, _ in score_parts if w > 0)
    confidence = min(1.0, filled / 6)

    # Explanation
    lines = [f"基本面评分: {total:.2f}/1.00"]
    for name, weighted, detail in score_parts:
        if weighted > 0:
            lines.append(f"  {name}: {weighted/ (0.25 if name == 'ROE' else 0.20 if name in ('营收增长','净利润增长') else 0.15 if name == '现金流质量' else 0.10):.0%} → 贡献{weighted:.3f} ({detail})")
        else:
            lines.append(f"  {name}: 无法评分 ({detail})")

    return total, confidence, "\n".join(lines)


# ─── SkillLifecycle Implementation ────────────────────────────────────────


class FundamentalAnalysisSkill(SkillLifecycle):
    """Fundamental analysis skill using the standardized lifecycle.

    Depends on MarketDataProvider for all data access.
    """

    def __init__(self, provider: MarketDataProvider | None = None):
        self._provider = provider
        self._profile_cache: dict[str, CompanyFundamentalProfile] = {}

    def set_provider(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="fundamental-analysis",
            version="2.0.0",
            description="Analyze company fundamentals: ROE, revenue/profit growth, cash flow quality, debt ratio, margin trends",
            category="analysis",
            tags=["fundamental", "quality"],
            data_requirements=["income_statement", "balance_sheet", "cashflow"],
            tool_requirements=["get_financial_summary"],
            timeout=120,
        )

    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        """Execute fundamental analysis for all stocks in context.

        Expected context keys:
          - dataset: ResearchDataset  (immutable, populated by Data Collector)
          - stocks:  list[StockBasic]
        """
        from runtime.snapshot import ResearchDataset

        dataset: ResearchDataset | None = context.get("dataset")
        if dataset is None:
            return SkillOutput(
                score=0.0, confidence=0.0,
                data={"error": "No ResearchDataset in context"},
                reasoning="Analysis skipped: dataset required (Skills consume snapshots, not providers)",
                warnings=["ResearchDataset is required"],
            )

        stocks: list[StockBasic] = context.get("stocks", [])
        if not stocks:
            return SkillOutput(
                score=0.0, confidence=0.0,
                data={"error": "No stocks provided in context"},
                reasoning="Analysis skipped: empty stock list",
            )

        profiles = []
        for stock in stocks:
            profile = self._analyze_one(dataset, stock)
            profiles.append(profile)

        # Score across all stocks
        score = sum(p.score for p in profiles) / len(profiles) if profiles else 0.0
        conf = sum(p.confidence for p in profiles) / len(profiles) if profiles else 0.0

        return SkillOutput(
            score=round(score, 4),
            confidence=round(conf, 4),
            data={
                "profiles": profiles,
                "stock_count": len(profiles),
            },
            reasoning=f"Fundamental analysis of {len(profiles)} stocks completed",
            warnings=[w for p in profiles for w in p.warnings],
        )

    def _analyze_one(self, dataset: Any, stock: StockBasic) -> CompanyFundamentalProfile:
        """Analyze fundamentals for a single stock from the dataset.

        Pure function of the dataset — no provider access. Deterministic
        and replayable.
        """
        from tools.providers import FinancialStatement

        stmts_dicts = dataset.financials(stock.ts_code)
        stmts = [FinancialStatement(**{k: v for k, v in d.items() if k in FinancialStatement.__dataclass_fields__})
                 for d in stmts_dicts]

        if not stmts:
            return CompanyFundamentalProfile(
                ts_code=stock.ts_code, name=stock.name, industry=stock.industry,
                score=0.0, confidence=0.1,
                warnings=["无财务报表数据"],
                missing_data_flags=["financials unavailable for this stock"],
            )

        # Compute metrics
        roes = compute_roe(stmts)
        rev_growth = compute_revenue_growth(stmts)
        profit_growth = compute_profit_growth(stmts)
        cf_quality = compute_cashflow_quality(stmts)
        debt_ratios = compute_debt_ratio(stmts)
        margins = compute_gross_margin_change(stmts)

        # Collect all metrics
        all_metrics: list[MetricProvenance] = []
        all_metrics.extend(roes)
        all_metrics.extend(rev_growth)
        all_metrics.extend(profit_growth)
        all_metrics.extend(cf_quality)
        all_metrics.extend(debt_ratios)
        all_metrics.extend(margins)

        # Score
        score, confidence, explanation = compute_fundamental_score(
            roes, rev_growth, profit_growth, cf_quality, debt_ratios, margins,
        )

        # Trends
        rev_trend = "unknown"
        if len(rev_growth) >= 2:
            avg_g = sum(m.value for m in rev_growth) / len(rev_growth)
            if avg_g > 0.05:
                rev_trend = "growing"
            elif avg_g > -0.02:
                rev_trend = "stable"
            else:
                rev_trend = "declining"

        profit_trend = "unknown"
        if len(profit_growth) >= 2:
            avg_p = sum(m.value for m in profit_growth) / len(profit_growth)
            if avg_p > 0.05:
                profit_trend = "growing"
            elif avg_p > -0.02:
                profit_trend = "stable"
            else:
                profit_trend = "declining"

        # Missing data flags
        missing_flags = []
        if not roes:
            missing_flags.append("roe")
        if not rev_growth:
            missing_flags.append("revenue_growth")
        if not profit_growth:
            missing_flags.append("profit_growth")

        warnings = [m.warning for m in all_metrics if m.warning]

        return CompanyFundamentalProfile(
            ts_code=stock.ts_code,
            name=stock.name,
            industry=stock.industry,
            metrics=all_metrics,
            score=score,
            confidence=confidence,
            revenue_trend=rev_trend,
            profit_trend=profit_trend,
            summary=explanation,
            missing_data_flags=missing_flags,
            warnings=warnings,
        )

    async def verify(self, context: dict, output: SkillOutput) -> SkillVerdict:
        """Self-verification: check output consistency."""
        checks = []
        errors = []

        data = output.data
        profiles = data.get("profiles", [])

        if not profiles:
            errors.append("No stock profiles in output")
        else:
            checks.append({"name": "stock_count", "passed": True, "detail": f"{len(profiles)} stocks"})

            for p in profiles:
                if p.missing_data_flags:
                    checks.append({
                        "name": f"missing_data_{p.ts_code}",
                        "passed": False,
                        "detail": f"{p.ts_code}: missing {', '.join(p.missing_data_flags)}",
                    })

        return SkillVerdict(passed=len(errors) == 0, checks=checks, errors=errors)

    async def summarize(self, output: SkillOutput) -> str:
        """Produce a one-line summary."""
        profiles = output.data.get("profiles", [])
        top = sorted(profiles, key=lambda p: p.score, reverse=True)[:3]
        lines = [f"分析 {len(profiles)} 只股票，综合评分 {output.score:.2f}"]
        for p in top:
            lines.append(f"  {p.name} ({p.ts_code}): {p.score:.2f} - {p.summary.split(chr(10))[0]}")
        return "\n".join(lines)
