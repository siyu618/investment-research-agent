# Base Pydantic models for investment analysis
# These define the shared interfaces all skills and agent components use.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrategyCategory(str, Enum):
    FUNDAMENTAL = "fundamental-analysis"
    TECHNICAL = "technical-analysis"
    VALUATION = "valuation-analysis"
    RISK = "risk-analysis"
    PORTFOLIO = "portfolio-selection"


# ─── Data Models ───────────────────────────────────────────────────────


@dataclass
class Stock:
    """Represents a stock entity from Tushare data."""
    ts_code: str
    name: str
    industry: str | None = None
    market: str | None = None
    list_date: str | None = None
    is_active: bool = True


@dataclass
class FinancialStatement:
    """Financial statement data point."""
    ts_code: str
    end_date: str
    report_type: str
    revenue: float | None = None
    net_profit: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    cash_flow: float | None = None
    roe: float | None = None
    basic_eps: float | None = None


@dataclass
class DailyPrice:
    """Daily OHLCV price data."""
    ts_code: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    change_pct: float


@dataclass
class RiskFactor:
    """Identified risk factor in analysis."""
    category: str
    description: str
    severity: RiskLevel
    metric_value: float | None = None


# ─── Analysis Context & Result ──────────────────────────────────────────


@dataclass
class MemoryAccess:
    """Interface for skill to read/write memory during analysis."""
    session_id: str

    def get(self, key: str):
        """Read from working memory."""
        ...

    def set(self, key: str, value):
        """Write to working memory."""
        ...


@dataclass
class AnalysisContext:
    """Full context provided to a skill for analysis."""
    stock: Stock
    financial_data: list[FinancialStatement] = field(default_factory=list)
    price_data: list[DailyPrice] = field(default_factory=list)
    market_data: dict = field(default_factory=dict)
    user_preferences: dict = field(default_factory=dict)
    memory: MemoryAccess | None = None


@dataclass
class AnalysisResult:
    """Output from a single skill's analysis."""
    skill_name: str
    skill_version: str
    score: float
    confidence: float
    reasoning: str
    risk_factors: list[RiskFactor] = field(default_factory=list)
    supporting_data: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ─── Plan Models ────────────────────────────────────────────────────────


@dataclass
class AnalysisStep:
    """A single step in the analysis plan."""
    id: int
    skill: str
    target: str
    depends_on: list[int] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    status: str = "pending"  # pending | running | completed | failed | skipped


@dataclass
class AnalysisPlan:
    """Structured plan produced by the Planner."""
    objective: str
    strategy_weights: dict[str, float]
    data_requirements: list[str]
    analysis_steps: list[AnalysisStep]
    risk_preference: str = "medium"


# ─── Skill Interface ────────────────────────────────────────────────────


class InvestmentSkill(ABC):
    """Abstract base class for all investment analysis skills."""

    @abstractmethod
    async def analyze(self, context: AnalysisContext) -> AnalysisResult:
        """Execute the strategy analysis and return results."""
        ...

    @abstractmethod
    def get_metadata(self) -> dict:
        """Return skill metadata for registry."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill name matching SKILL.md frontmatter."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Current skill version."""
        ...


# ─── Report Models ──────────────────────────────────────────────────────


@dataclass
class VerificationResult:
    """Output from the Verifier stage."""
    passed: bool
    data_complete: bool
    strategy_consistent: bool
    risk_validated: bool
    checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class InvestmentReport:
    """Structured investment research report."""
    report_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    agent_version: str = "1.0.0"
    user_requirement: str = ""
    market_overview: str = ""
    candidates: list[Any] = field(default_factory=list)
    portfolio_suggestion: str = ""
    disclaimer: str = (
        "This report is AI-generated for reference only. "
        "It does not constitute investment advice. "
        "Past performance is not indicative of future results. "
        "Always conduct your own research before making investment decisions."
    )
