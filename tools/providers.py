# Market Data Provider — Abstract protocol + mock implementation
#
# This is the single abstraction over market data access.
# All skills depend on this protocol, NOT on Tushare MCP or any
# specific data source. This enables:
#   - Unit testing with MockProvider
#   - Seamless swap between Tushare / local CSV / cache / future sources
#   - Provider composability (CachedProvider wrapping another provider)

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# ─── Data Models ──────────────────────────────────────────────────────────


@dataclass
class StockBasic:
    ts_code: str
    name: str
    industry: str = ""
    market: str = ""
    list_date: str = ""
    is_active: bool = True


@dataclass
class DailyPrice:
    ts_code: str
    trade_date: str
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    amount: float = 0.0
    change_pct: float = 0.0


@dataclass
class FinancialStatement:
    """Unified financial statement row.

    Maps from any provider's column naming to a standard schema.
    """
    ts_code: str
    end_date: str                    # e.g. "20241231"
    report_type: str = "annual"      # annual | q1 | q2 | q3

    # Income statement
    revenue: Optional[float] = None          # 营业总收入
    net_profit: Optional[float] = None        # 归母净利润
    operating_profit: Optional[float] = None  # 营业利润

    # Balance sheet
    total_assets: Optional[float] = None      # 资产总计
    total_liabilities: Optional[float] = None # 负债合计
    equity: Optional[float] = None            # 归母股东权益

    # Cash flow
    operating_cash_flow: Optional[float] = None  # 经营活动现金流净额
    free_cash_flow: Optional[float] = None        # 自由现金流

    # Per share
    basic_eps: Optional[float] = None         # 基本每股收益
    bvps: Optional[float] = None              # 每股净资产

    # Calculated fields
    gross_margin: Optional[float] = None      # (revenue - cost) / revenue
    roe: Optional[float] = None               # net_profit / equity


# ─── Provider Interface ────────────────────────────────────────────────────


class MarketDataProvider(ABC):
    """Abstract interface for all market data sources.

    All methods are async. All return lists of standardised dataclasses.
    Skills MUST NOT import or call any other data source.
    """

    @abstractmethod
    async def get_stock_basic(
        self, market: Optional[str] = None, industry: Optional[str] = None
    ) -> list[StockBasic]:
        ...

    @abstractmethod
    async def get_daily_price(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[DailyPrice]:
        ...

    @abstractmethod
    async def get_income_statement(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        ...

    @abstractmethod
    async def get_balance_sheet(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        ...

    @abstractmethod
    async def get_cashflow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        ...

    @abstractmethod
    async def get_financial_summary(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        """Convenience: merges income, balance, and cashflow into unified statements."""
        ...


# ─── Mock Provider ────────────────────────────────────────────────────────


_STOCK_UNIVERSE: dict[str, dict] = {
    "000001.SZ": {"name": "平安银行", "industry": "银行"},
    "000002.SZ": {"name": "万科A", "industry": "房地产"},
    "000333.SZ": {"name": "美的集团", "industry": "家用电器"},
    "000651.SZ": {"name": "格力电器", "industry": "家用电器"},
    "000858.SZ": {"name": "五粮液", "industry": "白酒"},
    "002415.SZ": {"name": "海康威视", "industry": "计算机"},
    "002475.SZ": {"name": "立讯精密", "industry": "电子"},
    "300750.SZ": {"name": "宁德时代", "industry": "电力设备"},
    "600036.SH": {"name": "招商银行", "industry": "银行"},
    "600519.SH": {"name": "贵州茅台", "industry": "白酒"},
    "600887.SH": {"name": "伊利股份", "industry": "食品饮料"},
    "600900.SH": {"name": "长江电力", "industry": "电力"},
    "601318.SH": {"name": "中国平安", "industry": "保险"},
    "601398.SH": {"name": "工商银行", "industry": "银行"},
    "603259.SH": {"name": "药明康德", "industry": "医药生物"},
}


def _make_financials(ts_code: str, years: int = 3) -> list[FinancialStatement]:
    """Generate deterministic mock financial data for a stock."""
    # Use hash of ts_code for deterministic pseudo-random values
    h = hash(ts_code) & 0xFFFFFFFF
    np_base = 50_000_000 + (h % 200_000_000)
    rev_base = 500_000_000 + (h % 2_000_000_000)

    results = []
    for i in range(years):
        year = 2024 - i
        # Each year revenue and profit grow/shrink deterministically
        rev = rev_base * (1.0 + (h % 10 - 5) / 100)  # +/-5% variation
        np = np_base * (1.0 + (h % 10 - 5) / 100)
        assets = rev * (2.0 + (h % 100) / 100)
        liab = assets * (0.4 + (h % 30) / 100)
        equity = assets - liab
        ocf = np * (0.7 + (h % 50) / 100)
        gross_margin = 0.25 + (h % 50) / 100
        eps = np / 5_000_000
        bvps_val = equity / 5_000_000

        for suffix in ["1231", "0930", "0630", "0331"]:
            if i == 0 and suffix != "1231":
                continue
            end_date = f"{year}{suffix}"
            results.append(FinancialStatement(
                ts_code=ts_code,
                end_date=end_date,
                report_type="annual" if suffix == "1231" else ("q3" if suffix == "0930" else "q2" if suffix == "0630" else "q1"),
                revenue=rev,
                net_profit=np,
                operating_profit=np * 1.05,
                total_assets=assets,
                total_liabilities=liab,
                equity=equity,
                operating_cash_flow=ocf,
                free_cash_flow=ocf * 0.8,
                basic_eps=eps,
                bvps=bvps_val,
                gross_margin=gross_margin,
                roe=np / equity if equity else 0.0,
            ))
    return results


def _make_prices(ts_code: str) -> list[DailyPrice]:
    """Generate deterministic mock daily price data (2 years)."""
    h = hash(ts_code) & 0xFFFFFFFF
    base_price = 20.0 + (h % 100)  # 20-120
    prices = []
    # Random walk with drift, bounded volatility
    for day in range(500):
        year = 2024 if day < 365 else 2025
        doy = (day % 365) + 101
        date = f"{year}{doy:03d}"
        # Daily change: -3% to +3.5%, small positive drift
        change_pct = ((h + day * 7) % 65 - 30) / 1000  # -3% to +3.5%
        if day > 0:
            close = prices[-1].close * (1.0 + change_pct)
        else:
            close = base_price
        open_p = close * (1.0 + ((h + day) % 21 - 10) / 1000)
        high = max(open_p, close) * 1.015
        low = min(open_p, close) * 0.985
        volume = int(5_000_000 + (hash(f"{ts_code}-{day}") % 15_000_000))
        prices.append(DailyPrice(
            ts_code=ts_code,
            trade_date=date,
            open=round(max(open_p, 0.5), 2),
            high=round(max(high, 0.5), 2),
            low=round(max(low, 0.5), 2),
            close=round(max(close, 0.5), 2),
            volume=volume,
            amount=round(volume * close, 2),
            change_pct=round(change_pct * 100, 2),
        ))
    return prices


class MockMarketDataProvider(MarketDataProvider):
    """Deterministic mock provider for testing.

    Generates realistic financial and price data for a fixed
    universe of 15 CSI 300 constituent stocks.

    Usage:
        provider = MockMarketDataProvider()
        stocks = await provider.get_stock_basic(market="SZSE")
        prices = await provider.get_daily_price("000001.SZ", "20240101", "20251231")
    """

    def __init__(self):
        self._cache: dict[str, Any] = {}

    async def get_stock_basic(
        self, market: Optional[str] = None, industry: Optional[str] = None
    ) -> list[StockBasic]:
        results = []
        for ts_code, info in _STOCK_UNIVERSE.items():
            if industry and info["industry"] != industry:
                continue
            mkt = "SZSE" if ts_code.endswith(".SZ") else "SSE"
            if market and mkt != market:
                continue
            results.append(StockBasic(
                ts_code=ts_code,
                name=info["name"],
                industry=info["industry"],
                market=mkt,
                list_date="2000-01-01",
                is_active=True,
            ))
        return results

    async def get_daily_price(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[DailyPrice]:
        cache_key = f"price:{ts_code}"
        if cache_key not in self._cache:
            self._cache[cache_key] = _make_prices(ts_code)
        return [
            p for p in self._cache[cache_key]
            if start_date <= p.trade_date <= end_date
        ]

    async def get_income_statement(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        return await self.get_financial_summary(ts_code, start_date, end_date)

    async def get_balance_sheet(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        return await self.get_financial_summary(ts_code, start_date, end_date)

    async def get_cashflow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        return await self.get_financial_summary(ts_code, start_date, end_date)

    async def get_financial_summary(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        cache_key = f"fin:{ts_code}"
        if cache_key not in self._cache:
            self._cache[cache_key] = _make_financials(ts_code)
        return [
            s for s in self._cache[cache_key]
            if start_date <= s.end_date <= end_date
        ]


# ─── Provider Extension Points ─────────────────────────────────────────────


class OfficialTushareMCPProvider(MarketDataProvider):
    """Production Tushare provider via MCP.

    Extension point: implement when Tushare token is available.
    """
    async def get_stock_basic(self, market=None, industry=None):
        raise NotImplementedError("OfficialTushareMCPProvider: call tushare.pro_api().stock_basic()")

    async def get_daily_price(self, ts_code, start_date, end_date):
        raise NotImplementedError("OfficialTushareMCPProvider: call tushare.pro_api().daily()")

    async def get_income_statement(self, ts_code, start_date, end_date):
        raise NotImplementedError

    async def get_balance_sheet(self, ts_code, start_date, end_date):
        raise NotImplementedError

    async def get_cashflow(self, ts_code, start_date, end_date):
        raise NotImplementedError

    async def get_financial_summary(self, ts_code, start_date, end_date):
        raise NotImplementedError


class CachedMarketDataProvider(MarketDataProvider):
    """Wraps another provider with an in-memory cache layer.

    Extension point: add SQLite or Redis persistence as needed.
    """
    def __init__(self, inner: MarketDataProvider, ttl_seconds: int = 300):
        self._inner = inner
        self._cache: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds

    async def _cached(self, key: str, fn):
        import time
        now = time.monotonic()
        if key in self._cache:
            ts, val = self._cache[key]
            if now - ts < self._ttl:
                return val
        val = await fn()
        self._cache[key] = (now, val)
        return val

    async def get_stock_basic(self, market=None, industry=None):
        return await self._cached(f"basic:{market}:{industry}",
            lambda: self._inner.get_stock_basic(market, industry))

    async def get_daily_price(self, ts_code, start_date, end_date):
        return await self._cached(f"price:{ts_code}:{start_date}:{end_date}",
            lambda: self._inner.get_daily_price(ts_code, start_date, end_date))

    async def get_income_statement(self, ts_code, start_date, end_date):
        return await self._cached(f"inc:{ts_code}:{start_date}:{end_date}",
            lambda: self._inner.get_income_statement(ts_code, start_date, end_date))

    async def get_balance_sheet(self, ts_code, start_date, end_date):
        return await self._cached(f"bal:{ts_code}:{start_date}:{end_date}",
            lambda: self._inner.get_balance_sheet(ts_code, start_date, end_date))

    async def get_cashflow(self, ts_code, start_date, end_date):
        return await self._cached(f"cf:{ts_code}:{start_date}:{end_date}",
            lambda: self._inner.get_cashflow(ts_code, start_date, end_date))

    async def get_financial_summary(self, ts_code, start_date, end_date):
        return await self._inner.get_financial_summary(ts_code, start_date, end_date)
