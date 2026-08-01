# Agent Planner — Requirement decomposition into structured AnalysisPlan
#
# Uses a two-phase approach:
#   1. Parse natural language requirement into InvestmentRequest (Pydantic)
#   2. Convert structured request → templated AnalysisPlan (limited graph shapes)
#
# The LLM only fills the InvestmentRequest struct. The plan structure is
# deterministic — no LLM-generated execution graphs.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from strategies.base.models import AnalysisPlan, AnalysisStep

logger = logging.getLogger("agent.planner")


class InvestmentObjective(str, Enum):
    VALUE = "value"               # 价值投资 — 低PE/PB, 稳健增长
    GROWTH = "growth"             # 成长投资 — 高增长, 高估值容忍
    QUALITY = "quality"           # 质量投资 — 高ROE, 强现金流
    MOMENTUM = "momentum"         # 趋势投资 — 价格动量
    INCOME = "income"             # 收益投资 — 高股息
    MIXED = "mixed"               # 综合


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HoldingPeriod(str, Enum):
    SHORT = "short"       # < 3 months
    MEDIUM = "medium"     # 3-12 months
    LONG = "long"         # > 12 months


@dataclass
class InvestmentRequest:
    """Structured investment requirement parsed from user input.

    All fields have defaults. The Planner fills this from the user's
    natural language requirement using a simple rule-based parser.
    """
    stock_pool: str = "csi300"           # Stock universe identifier
    stock_codes: list[str] = field(default_factory=list)  # explicit ts_codes (e.g. 600519.SH)
    objective: InvestmentObjective = InvestmentObjective.MIXED
    risk_level: RiskLevel = RiskLevel.MEDIUM
    holding_period: HoldingPeriod = HoldingPeriod.MEDIUM
    top_k: int = 5                       # Number of stocks to recommend
    constraints: list[str] = field(default_factory=list)

    # Data period for analysis
    data_start_date: str = "20240101"
    data_end_date: str = "20251231"

    # Strategy weights (auto-derived from objective)
    strategy_weights: dict[str, float] = field(default_factory=dict)


class Planner:
    """Decomposes user investment requirements into structured analysis plans.

    Phase 1: requirement → InvestmentRequest
        - LLM structured output (if configured) → validated InvestmentRequest
        - deterministic rule-based fallback (always available)
    Phase 2: InvestmentRequest → templated AnalysisPlan (always deterministic)

    The LLM never shapes the DAG; it only fills the structured request.
    """

    def __init__(self, llm: Any = None):
        self.llm = llm

    async def create_plan(
        self,
        requirement: str,
        available_skills: list[dict] | None = None,
    ) -> AnalysisPlan:
        """Parse user requirement and produce a structured AnalysisPlan.

        Tries LLM structured extraction first, falling back to rules.
        The returned plan is always deterministic (templated steps).
        """
        request = await self._parse_requirement(requirement)
        return self._request_to_plan(request)

    async def _parse_requirement(self, requirement: str) -> InvestmentRequest:
        """Requirement → InvestmentRequest (LLM first, rules fallback)."""
        # 1. Try LLM structured extraction (bounded, Pydantic-validated)
        if self.llm is not None and getattr(self.llm, "available", False):
            try:
                raw = await self.llm.parse_investment_request(requirement)
                merged = self._merge_llm_request(raw, requirement)
                return merged
            except Exception:
                logger.warning("LLM plan parse failed; falling back to rules",
                               exc_info=True)

        # 2. Deterministic rule-based fallback
        return self._rule_parse(requirement)

    def _merge_llm_request(self, raw: dict, requirement: str) -> InvestmentRequest:
        """Merge LLM extraction with rule defaults (fills missing fields)."""
        base = self._rule_parse(requirement)
        # Override only fields the LLM explicitly provided and valid
        if raw.get("stock_codes"):
            base.stock_codes = [str(c) for c in raw["stock_codes"]]
            base.stock_pool = "single"
        if isinstance(raw.get("stock_pool"), str):
            base.stock_pool = raw["stock_pool"]
        try:
            if raw.get("objective") in {o.value for o in InvestmentObjective}:
                base.objective = InvestmentObjective(raw["objective"])
        except ValueError:
            pass
        try:
            if raw.get("risk_level") in {r.value for r in RiskLevel}:
                base.risk_level = RiskLevel(raw["risk_level"])
        except ValueError:
            pass
        try:
            if raw.get("holding_period") in {h.value for h in HoldingPeriod}:
                base.holding_period = HoldingPeriod(raw["holding_period"])
        except ValueError:
            pass
        if isinstance(raw.get("top_k"), int) and raw["top_k"] > 0:
            base.top_k = min(50, max(1, raw["top_k"]))
        if isinstance(raw.get("constraints"), list):
            base.constraints = [str(c) for c in raw["constraints"]]

        # Recompute weights from merged objective/risk
        base.strategy_weights = self._default_weights(base.objective, base.risk_level)
        return base

    def _rule_parse(self, requirement: str) -> InvestmentRequest:
        """Deterministic rule-based parser (keyword matching + defaults).

        Supports Chinese and English keywords.
        Falls back to sensible defaults for ambiguous input.
        """
        req_orig = requirement

        # --- Stock pool ---
        stock_pool = "csi300"
        if any(kw in req_orig for kw in ["沪深300", "hs300", "csi300"]):
            stock_pool = "csi300"
        elif any(kw in req_orig for kw in ["上证50", "sse50"]):
            stock_pool = "sse50"
        elif any(kw in req_orig for kw in ["全市场", "all", "全部"]):
            stock_pool = "all"

        # --- Objective ---
        objective = InvestmentObjective.MIXED
        if any(kw in req_orig for kw in ["价值", "低估", "便宜", "value", "undervalued"]):
            objective = InvestmentObjective.VALUE
        elif any(kw in req_orig for kw in ["成长", "增长", "增长快", "growth", "高增长"]):
            objective = InvestmentObjective.GROWTH
        elif any(kw in req_orig for kw in ["质量", "优质", "roe", "quality", "稳健"]):
            objective = InvestmentObjective.QUALITY
        elif "基本面" in req_orig or "稳健" in req_orig:
            objective = InvestmentObjective.QUALITY
        elif any(kw in req_orig for kw in ["动量", "趋势", "momentum", "momentum"]):
            objective = InvestmentObjective.MOMENTUM
        elif any(kw in req_orig for kw in ["股息", "分红", "income", "dividend"]):
            objective = InvestmentObjective.INCOME

        # --- Risk level ---
        risk_level = RiskLevel.MEDIUM
        if any(kw in req_orig for kw in ["低风险", "保守", "稳健", "low risk", "conservative"]):
            risk_level = RiskLevel.LOW
        elif any(kw in req_orig for kw in ["高风险", "激进", "high risk", "aggressive"]):
            risk_level = RiskLevel.HIGH

        # --- Holding period ---
        period = HoldingPeriod.MEDIUM
        if any(kw in req_orig for kw in ["短期", "短线", "short", "quick"]):
            period = HoldingPeriod.SHORT
        elif any(kw in req_orig for kw in ["长期", "长线", "long", "持有"]):
            period = HoldingPeriod.LONG

        # --- Top K ---
        top_k = 5
        match = re.search(r'(\d+)\s*[只|个|支|stock|个股票]', req_orig)
        if match:
            top_k = int(match.group(1))
            top_k = max(1, min(50, top_k))

        # --- Constraints ---
        constraints = []
        if any(kw in req_orig for kw in ["回撤", "drawdown", "跌幅"]):
            constraints.append("max_drawdown_controlled")
        if any(kw in req_orig for kw in ["估值合理", "合理估值", "fairly valued"]):
            constraints.append("reasonable_valuation")
        if any(kw in req_orig for kw in ["分红", "股息"]):
            constraints.append("dividend_yield")
        if "中等风险" in req_orig:
            risk_level = RiskLevel.MEDIUM

        # --- Explicit stock codes (e.g. "分析 600519.SH") ---
        matches = re.findall(r"\b(\d{6})\.(SH|SZ|BJ)\b", req_orig, re.IGNORECASE)
        stock_codes = [f"{code}.{suffix.upper()}" for code, suffix in matches]
        if stock_codes:
            stock_pool = "single"  # override universe

        # --- Strategy weights ---
        strategy_weights = self._default_weights(objective, risk_level)

        return InvestmentRequest(
            stock_pool=stock_pool,
            stock_codes=stock_codes,
            objective=objective,
            risk_level=risk_level,
            holding_period=period,
            top_k=top_k,
            constraints=constraints,
            strategy_weights=strategy_weights,
        )

    def _request_to_plan(self, req: InvestmentRequest) -> AnalysisPlan:
        """Convert structured request into a templated AnalysisPlan.

        The plan has 7 fixed steps with computed dependencies:
          1. data collection (no deps)
          2-4. fundamental/valuation/risk analysis (depends on data)
          5. portfolio selection (depends on all analyses)
          6. verification (depends on portfolio)
          7. report generation (depends on verification)
        """
        steps = [
            AnalysisStep(id=1, skill="data-collector",
                         target=req.stock_pool,
                         depends_on=[],
                         params={"start_date": req.data_start_date,
                                 "end_date": req.data_end_date,
                                 "stock_codes": req.stock_codes,
                                 "timeout": 60}),
            AnalysisStep(id=2, skill="fundamental-analysis",
                         target=req.stock_pool,
                         depends_on=[1],
                         params={"timeout": 120}),
            AnalysisStep(id=3, skill="valuation-analysis",
                         target=req.stock_pool,
                         depends_on=[1],
                         params={"timeout": 90}),
            AnalysisStep(id=4, skill="risk-analysis",
                         target=req.stock_pool,
                         depends_on=[1],
                         params={"timeout": 90}),
            AnalysisStep(id=5, skill="portfolio-selection",
                         target=req.stock_pool,
                         depends_on=[2, 3, 4],
                         params={"top_k": req.top_k,
                                 "strategy_weights": req.strategy_weights,
                                 "timeout": 60}),
            AnalysisStep(id=6, skill="verifier",
                         target=req.stock_pool,
                         depends_on=[5],
                         params={"timeout": 30}),
            AnalysisStep(id=7, skill="report-generator",
                         target=req.stock_pool,
                         depends_on=[6],
                         params={"timeout": 30}),
        ]

        return AnalysisPlan(
            objective=f"stock_pool={req.stock_pool} "
                      f"objective={req.objective.value} "
                      f"risk={req.risk_level.value} "
                      f"top_k={req.top_k}",
            strategy_weights=req.strategy_weights,
            data_requirements=[req.stock_pool],
            analysis_steps=steps,
            risk_preference=req.risk_level.value,
        )

    @staticmethod
    def _default_weights(obj: InvestmentObjective, risk: RiskLevel) -> dict[str, float]:
        """Return strategy weights based on objective and risk preference."""
        base = {
            InvestmentObjective.VALUE: {"fundamental-analysis": 0.35, "valuation-analysis": 0.35,
                                        "risk-analysis": 0.20, "technical-analysis": 0.10},
            InvestmentObjective.GROWTH: {"fundamental-analysis": 0.45, "valuation-analysis": 0.15,
                                         "risk-analysis": 0.25, "technical-analysis": 0.15},
            InvestmentObjective.QUALITY: {"fundamental-analysis": 0.50, "valuation-analysis": 0.20,
                                          "risk-analysis": 0.20, "technical-analysis": 0.10},
            InvestmentObjective.MOMENTUM: {"fundamental-analysis": 0.15, "valuation-analysis": 0.10,
                                           "risk-analysis": 0.30, "technical-analysis": 0.45},
            InvestmentObjective.INCOME: {"fundamental-analysis": 0.35, "valuation-analysis": 0.20,
                                         "risk-analysis": 0.15, "technical-analysis": 0.30},
            InvestmentObjective.MIXED: {"fundamental-analysis": 0.35, "valuation-analysis": 0.25,
                                        "risk-analysis": 0.20, "technical-analysis": 0.20},
        }

        weights = dict(base.get(obj, base[InvestmentObjective.MIXED]))

        # Risk adjustment
        if risk == RiskLevel.LOW:
            weights["risk-analysis"] = min(1.0, weights.get("risk-analysis", 0.20) + 0.10)
            weights["technical-analysis"] = max(0.0, weights.get("technical-analysis", 0.20) - 0.10)
        elif risk == RiskLevel.HIGH:
            weights["technical-analysis"] = min(1.0, weights.get("technical-analysis", 0.20) + 0.10)
            weights["risk-analysis"] = max(0.0, weights.get("risk-analysis", 0.20) - 0.10)

        # Normalise to 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        return weights

    async def adjust_plan(self, plan: AnalysisPlan, feedback: str) -> AnalysisPlan:
        """Adjust an existing plan based on user feedback."""
        req = await self._parse_requirement(feedback)
        # Merge: keep steps, update weights
        plan.strategy_weights = req.strategy_weights
        plan.risk_preference = req.risk_level.value
        return plan
