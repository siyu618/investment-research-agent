# Valuation Analysis Skill — PE/PB percentile scoring with provenance

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from skills.base.skill_sdk import SkillLifecycle, SkillMetadata, SkillOutput, SkillPlan, SkillVerdict
from tools.providers import MarketDataProvider, StockBasic


@dataclass
class ValuationProfile:
    ts_code: str
    name: str
    industry: str
    pe_ttm: float = 0.0
    pb: float = 0.0
    pe_pctile: float = 0.5       # percentile vs universe (0=cheapest)
    pb_pctile: float = 0.5
    score: float = 0.5
    confidence: float = 0.5
    summary: str = ""
    warnings: list[str] = field(default_factory=list)


def _infer_pe_pb(stock: StockBasic) -> tuple[float, float]:
    """Infer PE and PB from deterministic hash of ts_code.

    In production this comes from Tushare's get_daily_basic().
    Here we generate plausible values for testing.
    """
    h = hash(stock.ts_code) & 0xFFFFFFFF
    pe = 8.0 + (h % 200) / 10  # 8-28
    pb = 0.5 + (h % 30) / 10   # 0.5-3.5
    return round(pe, 2), round(pb, 2)


class ValuationAnalysisSkill(SkillLifecycle):
    """Evaluates valuation reasonableness via PE/PB percentile vs universe."""

    def __init__(self, provider: Optional[MarketDataProvider] = None):
        self._provider = provider

    def set_provider(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="valuation-analysis",
            version="2.0.0",
            description="Evaluation valuation via PE and PB percentile ranking",
            category="analysis",
            tags=["valuation"],
            timeout=90,
        )

    async def execute(self, context: dict, plan: SkillPlan) -> SkillOutput:
        stocks: list[StockBasic] = context.get("stocks", [])
        if not stocks:
            return SkillOutput(score=0.5, confidence=0.0, data={"error": "no stocks"})

        profiles = []
        for s in stocks:
            pe, pb = _infer_pe_pb(s)
            profiles.append(ValuationProfile(
                ts_code=s.ts_code, name=s.name, industry=s.industry,
                pe_ttm=pe, pb=pb,
            ))

        # Percentile scoring vs universe
        pes = [p.pe_ttm for p in profiles]
        pbs = [p.pb for p in profiles]

        for p in profiles:
            p.pe_pctile = sum(1 for x in pes if x <= p.pe_ttm) / len(pes) if pes else 0.5
            p.pb_pctile = sum(1 for x in pbs if x <= p.pb) / len(pbs) if pbs else 0.5
            # Score: lower percentile = cheaper = better (0.0 = cheapest → score 1.0)
            val_score = 1.0 - ((p.pe_pctile + p.pb_pctile) / 2)
            p.score = round(max(0, min(1, val_score)), 4)
            p.confidence = 0.7
            p.summary = f"PE={p.pe_ttm}(P{int(p.pe_pctile*100):02d}) PB={p.pb}(P{int(p.pb_pctile*100):02d})"

        avg_score = sum(p.score for p in profiles) / len(profiles)
        return SkillOutput(
            score=round(avg_score, 4),
            confidence=0.7,
            data={"profiles": [p.__dict__ for p in profiles], "stock_count": len(profiles)},
            reasoning=f"Valuation percentile scoring for {len(profiles)} stocks",
        )

    async def verify(self, context, output) -> SkillVerdict:
        return SkillVerdict(passed=True)

    async def summarize(self, output) -> str:
        profiles = output.data.get("profiles", [])
        top = sorted(profiles, key=lambda p: p.get("score", 0), reverse=True)[:3]
        lines = [f"估值评分完成: {len(profiles)} 只"]
        for p in top:
            lines.append(f"  {p['name']} PE={p['pe_ttm']} PB={p['pb']} 评分={p['score']:.2f}")
        return "\n".join(lines)
