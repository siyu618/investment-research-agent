# Risk Analysis Skill — volatility, max drawdown with provenance

from __future__ import annotations

import math
from dataclasses import dataclass, field

from skills.base.skill_sdk import (
    SkillLifecycle,
    SkillMetadata,
    SkillOutput,
    SkillPlan,
    SkillVerdict,
)
from tools.providers import DailyPrice, MarketDataProvider, StockBasic


@dataclass
class RiskProfile:
    ts_code: str
    name: str
    industry: str
    annual_volatility: float = 0.0    # annualized std of daily returns
    max_drawdown: float = 0.0          # max peak-to-trough (positive = % loss)
    score: float = 0.5                 # higher = safer
    confidence: float = 0.5
    summary: str = ""
    warnings: list[str] = field(default_factory=list)


def compute_volatility(prices: list[DailyPrice]) -> tuple[float, float]:
    """Compute annualized volatility from daily returns.

    Returns:
        (annual_volatility, confidence)
    """
    if len(prices) < 20:
        return 0.0, 0.1

    closes = [p.close for p in prices if p.close > 0]
    if len(closes) < 20:
        return 0.0, 0.1

    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    if not returns:
        return 0.0, 0.1

    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    daily_std = math.sqrt(variance)
    annual_vol = daily_std * math.sqrt(252)  # annualize

    confidence = min(1.0, len(prices) / 500)
    return round(annual_vol, 4), round(confidence, 4)


def compute_max_drawdown(prices: list[DailyPrice]) -> float:
    """Compute maximum drawdown percentage.

    Returns:
        positive float: e.g. 0.25 = 25% max drawdown
    """
    if len(prices) < 2:
        return 0.0

    closes = [p.close for p in prices if p.close > 0]
    if len(closes) < 2:
        return 0.0

    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


class RiskAnalysisSkill(SkillLifecycle):
    """Quantifies risk via volatility and maximum drawdown."""

    def __init__(self, provider: MarketDataProvider | None = None):
        self._provider = provider

    def set_provider(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="risk-analysis",
            version="2.0.0",
            description="Analyze risk via annualized volatility and max drawdown",
            category="analysis",
            tags=["risk"],
            data_requirements=["daily_price"],
            timeout=90,
        )

    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        provider: MarketDataProvider | None = context.get("provider") or self._provider
        stocks: list[StockBasic] = context.get("stocks", [])
        if not stocks or provider is None:
            return SkillOutput(score=0.5, confidence=0.0, data={"error": "missing provider or stocks"})

        profiles = []
        for s in stocks:
            try:
                prices = await provider.get_daily_price(s.ts_code, "20240101", "20251231")
            except Exception:
                profiles.append(RiskProfile(
                    ts_code=s.ts_code, name=s.name, industry=s.industry,
                    score=0.0, confidence=0.0, warnings=["价格数据获取失败"],
                ))
                continue

            vol, vol_conf = compute_volatility(prices)
            mdd = compute_max_drawdown(prices)

            warning = ""
            if mdd > 0.40:
                warning = f"最大回撤 {mdd:.1%}，偏高风险"
            elif mdd > 0.25:
                warning = f"最大回撤 {mdd:.1%}，中等风险"

            # Score: lower volatility + lower drawdown = safer
            # Use sigmoid-like scoring for robustness to outliers
            vol_score = 1.0 / (1.0 + vol * 5) if vol > 0 else 0.5
            dd_score = 1.0 / (1.0 + mdd * 5) if mdd > 0 else 0.5
            risk_score = round(vol_score * 0.5 + dd_score * 0.5, 4)

            profiles.append(RiskProfile(
                ts_code=s.ts_code, name=s.name, industry=s.industry,
                annual_volatility=vol, max_drawdown=mdd,
                score=risk_score, confidence=vol_conf,
                summary=f"年化波动={vol:.1%} 最大回撤={mdd:.1%}",
                warnings=[warning] if warning else [],
            ))

        avg_score = sum(p.score for p in profiles) / len(profiles) if profiles else 0.5
        return SkillOutput(
            score=round(avg_score, 4),
            confidence=round(sum(p.confidence for p in profiles) / len(profiles), 4) if profiles else 0.5,
            data={"profiles": profiles, "stock_count": len(profiles)},
            reasoning=f"Risk analysis for {len(profiles)} stocks",
        )

    async def verify(self, context, output) -> SkillVerdict:
        return SkillVerdict(passed=True)

    async def summarize(self, output) -> str:
        profiles = output.data.get("profiles", [])
        top = sorted(profiles, key=lambda p: p.score)[:3]
        lines = [f"风险评分完成: {len(profiles)} 只"]
        for p in top:
            lines.append(f"  {p.name}: 波动={p.annual_volatility:.1%} 回撤={p.max_drawdown:.1%} 评分={p.score:.2f}")
        return "\n".join(lines)
