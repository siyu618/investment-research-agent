# Market Data Provider — Abstract protocol + mock implementation
#
# This is the single abstraction over market data access.
# All skills depend on this protocol, NOT on Tushare MCP or any
# specific data source. This enables:
#   - Unit testing with MockProvider
#   - Seamless swap between Tushare / local CSV / cache / future sources
#   - Provider composability (CachedProvider wrapping another provider)

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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
    revenue: float | None = None          # 营业总收入
    net_profit: float | None = None        # 归母净利润
    operating_profit: float | None = None  # 营业利润

    # Balance sheet
    total_assets: float | None = None      # 资产总计
    total_liabilities: float | None = None # 负债合计
    equity: float | None = None            # 归母股东权益

    # Cash flow
    operating_cash_flow: float | None = None  # 经营活动现金流净额
    free_cash_flow: float | None = None        # 自由现金流

    # Per share
    basic_eps: float | None = None         # 基本每股收益
    bvps: float | None = None              # 每股净资产

    # Calculated fields
    gross_margin: float | None = None      # (revenue - cost) / revenue
    roe: float | None = None               # net_profit / equity


# ─── Provider Interface ────────────────────────────────────────────────────


class MarketDataProvider(ABC):
    """Abstract interface for all market data sources.

    All methods are async. All return lists of standardised dataclasses.
    Skills MUST NOT import or call any other data source.
    """

    @abstractmethod
    async def get_stock_basic(
        self,
        market: str | None = None,
        industry: str | None = None,
        ts_codes: list[str] | None = None,
    ) -> list[StockBasic]:
        ...

    @abstractmethod
    async def get_daily_price(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[DailyPrice]:
        ...

    @abstractmethod
    async def get_valuation(
        self, ts_code: str, trade_date: str = ""
    ) -> dict:
        """Return PE/PB valuation metrics for a stock.

        Keys: pe, pb, trade_date (empty dict if unavailable).
        """
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


# Company archetypes for realistic mock data coverage:
#   growth  — high revenue/profit growth, lower margins, higher leverage
#   value   — stable growth, moderate margins, low leverage
#   cyclical— volatile revenue/profit (boom/bust), mid leverage
#   abnormal— negative profit / cashflow stress (edge-case testing)
_ARCHETYPE = {
    "growth": {"rev_growth": 0.25, "profit_growth": 0.30, "margin": 0.30,
               "debt": 0.55, "ocf_ratio": 0.8},
    "value": {"rev_growth": 0.06, "profit_growth": 0.07, "margin": 0.40,
              "debt": 0.30, "ocf_ratio": 1.1},
    "cyclical": {"rev_growth": 0.12, "profit_growth": 0.05, "margin": 0.25,
                 "debt": 0.50, "ocf_ratio": 0.9},
    "abnormal": {"rev_growth": -0.05, "profit_growth": -0.20, "margin": 0.10,
                 "debt": 0.75, "ocf_ratio": 0.2},
}

# Assign an archetype per stock (stable across processes).
_ARCHETYPE_BY_CODE = {
    "000001.SZ": "value", "000002.SZ": "cyclical", "000333.SZ": "growth",
    "000651.SZ": "value", "000858.SZ": "growth", "002415.SZ": "growth",
    "002475.SZ": "growth", "300750.SZ": "growth", "600036.SH": "value",
    "600519.SH": "growth", "600887.SH": "value", "600900.SH": "value",
    "601318.SH": "value", "601398.SH": "value", "603259.SH": "growth",
    # Edge-case: abnormal company (negative/stressed fundamentals)
    "000007.SZ": "abnormal", "000009.SZ": "cyclical",
}

# Add a few abnormal/cyclical stocks for edge-case coverage.
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
    # Edge-case coverage
    "000007.SZ": {"name": "全新好", "industry": "房地产"},
    "000009.SZ": {"name": "中国宝安", "industry": "综合"},
}


def _stable_seed(ts_code: str, salt: str = "") -> int:
    """Deterministic 32-bit seed from a stock code (cross-process stable)."""
    h = hashlib.sha256(f"{ts_code}:{salt}".encode()).hexdigest()
    return int(h[:8], 16)


def _stable_float(ts_code: str, salt: str, lo: float, hi: float) -> float:
    """Deterministic float in [lo, hi) from ts_code+salt."""
    seed = _stable_seed(ts_code, salt)
    return lo + (seed % 10000) / 10000 * (hi - lo)


# Real trading calendar (weekdays, skipping weekends) — no string concat.
# Deterministic across processes (pure datetime arithmetic, no pandas needed).
def _build_trading_dates() -> list[str]:
    from datetime import date as _date
    from datetime import timedelta as _td

    _d = _date(2024, 1, 2)
    _end = _date(2025, 12, 31)
    _dates: list[str] = []
    while _d <= _end:
        if _d.weekday() < 5:  # Mon-Fri
            _dates.append(_d.strftime("%Y%m%d"))
        _d += _td(days=1)
    return _dates


_TRADING_DATES = _build_trading_dates()


def _make_financials(ts_code: str, years: int = 3) -> list[FinancialStatement]:
    """Generate deterministic mock financial data by company archetype."""
    archetype = _ARCHETYPE.get(_ARCHETYPE_BY_CODE.get(ts_code, "value"),
                               _ARCHETYPE["value"])

    rev_base = _stable_float(ts_code, "rev", 3e8, 8e8)
    np_base = rev_base * _stable_float(ts_code, "npm", 0.05, 0.15)
    margin = archetype["margin"] + _stable_float(ts_code, "margin_jit", -0.03, 0.03)
    debt = archetype["debt"] + _stable_float(ts_code, "debt_jit", -0.05, 0.05)

    results = []
    for i in range(years):
        year = 2024 - i
        # Compound growth/decline by archetype (deterministic per year)
        g_rev = archetype["rev_growth"] + _stable_float(ts_code, f"rev_jit{i}", -0.03, 0.03)
        g_np = archetype["profit_growth"] + _stable_float(ts_code, f"np_jit{i}", -0.04, 0.04)

        rev = rev_base * (1 + g_rev) ** (years - 1 - i)
        np = np_base * (1 + g_np) ** (years - 1 - i)

        # Cyclical: alternate boom/bust around base
        if archetype is _ARCHETYPE["cyclical"]:
            cycle = 1 + 0.3 * ((-1) ** i)  # +30% / -30% alternate
            rev = rev * (1 + 0.2 * cycle)
            np = np * (1 + 0.5 * cycle)

        assets = rev * (2.0 + _stable_float(ts_code, f"assets{i}", 0, 1))
        liab = assets * max(0.05, min(0.95, debt))
        equity = assets - liab
        ocf = np * archetype["ocf_ratio"]
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
                gross_margin=margin,
                roe=np / equity if equity else 0.0,
            ))
    return results


def _make_prices(ts_code: str) -> list[DailyPrice]:
    """Generate deterministic mock daily price data (real trading dates)."""
    base_price = 20.0 + _stable_float(ts_code, "base_price", 0, 100)
    prices: list[DailyPrice] = []
    close = base_price
    dates = _TRADING_DATES  # real Mon-Fri calendar, cross-process stable

    for day, date in enumerate(dates):
        # Daily change: -3% to +3.5% (deterministic per ts_code+day)
        change_pct = _stable_float(ts_code, f"chg{day}", -0.03, 0.035)
        close = close * (1.0 + change_pct)
        open_p = close * (1.0 + _stable_float(ts_code, f"open{day}", -0.01, 0.01))
        high = max(open_p, close) * 1.015
        low = min(open_p, close) * 0.985
        volume = int(5_000_000 + _stable_float(ts_code, f"vol{day}", 0, 1) * 15_000_000)
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
        self,
        market: str | None = None,
        industry: str | None = None,
        ts_codes: list[str] | None = None,
    ) -> list[StockBasic]:
        results = []
        for ts_code, info in _STOCK_UNIVERSE.items():
            if ts_codes and ts_code not in ts_codes:
                continue
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

    async def get_valuation(self, ts_code: str, trade_date: str = "") -> dict:
        """Mock PE/PB from stable sha256 seed (cross-process deterministic)."""
        h = _stable_seed(ts_code, "valuation")
        pe = round(8.0 + (h % 2000) / 100, 2)
        pb = round(0.5 + (h % 300) / 100, 2)
        return {"ts_code": ts_code, "pe": pe, "pb": pb,
                "trade_date": trade_date or "20251231"}

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


# ─── Tushare Provider ───────────────────────────────────────────────────


class TushareClientError(Exception):
    """Raised when Tushare API returns an error."""


class OfficialTushareMCPProvider(MarketDataProvider):
    """Real Tushare data provider.

    Uses the `tushare` package (pro_api). Requires TUSHARE_TOKEN.
    Fetches stock basics, daily prices, and financial statements,
    mapping them to the unified MarketDataProvider schema.

    Usage:
        provider = OfficialTushareMCPProvider(token="...")
        stocks = await provider.get_stock_basic(market="SSE")
    """

    STOCK_BASIC_TTL = 6 * 3600  # cache stock_basic for 6h (hourly quota)

    def __init__(self, token: str = "", max_retries: int = 3):
        self._token = token or os.environ.get("TUSHARE_TOKEN", "")
        self._max_retries = max_retries
        self._pro = None
        self._stock_basic_cache: list[StockBasic] | None = None
        self._stock_basic_cached_at: float = 0.0
        if self._token:
            try:
                import tushare as ts
                ts.set_token(self._token)
                self._pro = ts.pro_api()
            except Exception as e:
                raise TushareClientError(f"Failed to init Tushare: {e}") from e

    def _ensure_pro(self):
        if self._pro is None:
            raise TushareClientError(
                "TUSHARE_TOKEN not configured. Set TUSHARE_TOKEN env var "
                "or pass token= to the provider."
            )
        return self._pro

    async def _call(self, fn, **kwargs):
        """Call a tushare API with retries on transient errors.

        Rate-limit handling:
          - "N次/分钟" windows are short: retry once after the window.
          - "N次/小时" windows are long: fail fast with a clear error
            instead of blocking the pipeline for up to an hour.
        """
        import asyncio

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                # tushare API is sync; run in thread pool
                return await asyncio.to_thread(fn, **kwargs)
            except Exception as e:
                last_err = e
                msg = str(e)
                if "没有" in msg and "权限" in msg:
                    # Permanent: no API permission — do NOT retry.
                    raise TushareClientError(
                        f"Tushare permission denied: {e}"
                    ) from e
                if "频率超限" in msg or "频次超限" in msg or "frequency" in msg.lower():
                    if "小时" in msg or "hour" in msg.lower():
                        # Hour-level quota: don't block the pipeline.
                        raise TushareClientError(
                            f"Tushare rate limit (hourly) exceeded: {e}"
                        ) from e
                    # Minute-level: wait the window once, then retry
                    wait = 60.0
                else:
                    wait = 0.5 * (attempt + 1)
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(wait)
        raise TushareClientError(f"Tushare call failed: {last_err}") from last_err

    async def get_stock_basic(
        self,
        market: str | None = None,
        industry: str | None = None,
        ts_codes: list[str] | None = None,
    ) -> list[StockBasic]:
        """Fetch stock basics with an in-process cache.

        The full universe is fetched once (stock_basic has a tight quota on
        free tiers) and cached for STOCK_BASIC_TTL. Single-stock lookups
        then filter from the cached universe without another API call.
        """
        import time

        # Use cached full universe if fresh
        if self._stock_basic_cache is not None:
            elapsed = time.monotonic() - self._stock_basic_cached_at
            if elapsed < self.STOCK_BASIC_TTL:
                return self._filter_basic(self._stock_basic_cache, market, industry, ts_codes)

        pro = self._ensure_pro()
        kwargs: dict = {"exchange": "", "list_status": "L",
                        "fields": "ts_code,name,industry,area,market,list_date"}
        if ts_codes and self._stock_basic_cache is None:
            # First fetch: request only the needed codes to stay small.
            kwargs["ts_code"] = ",".join(ts_codes)

        try:
            df = await self._call(pro.stock_basic, **kwargs)
        except TushareClientError:
            # Rate-limited: fall back to stale cache if we have one.
            if self._stock_basic_cache:
                return self._filter_basic(self._stock_basic_cache, market, industry, ts_codes)
            raise

        results = []
        for _, row in df.iterrows():
            if market and row["market"] not in market:
                continue
            if industry and row["industry"] != industry:
                continue
            results.append(StockBasic(
                ts_code=row["ts_code"],
                name=row["name"],
                industry=row.get("industry", "") or "",
                market=row.get("market", "") or "",
                list_date=row.get("list_date", "") or "",
                is_active=True,
            ))

        # Cache the full universe on first success (may be partial if filtered)
        if self._stock_basic_cache is None:
            self._stock_basic_cache = results
            self._stock_basic_cached_at = time.monotonic()
        return self._filter_basic(results, market, industry, ts_codes)

    @staticmethod
    def _filter_basic(
        stocks: list[StockBasic],
        market: str | None,
        industry: str | None,
        ts_codes: list[str] | None,
    ) -> list[StockBasic]:
        """Filter a stock list by market/industry/codes."""
        results = stocks
        if market:
            results = [s for s in results if market in s.market]
        if industry:
            results = [s for s in results if s.industry == industry]
        if ts_codes:
            wanted = set(ts_codes)
            results = [s for s in results if s.ts_code in wanted]
        return results

    async def get_valuation(self, ts_code: str, trade_date: str = "") -> dict:
        """Real PE/PB from daily_basic (available on free/low tiers)."""
        pro = self._ensure_pro()
        kwargs: dict = {"ts_code": ts_code}
        if trade_date:
            kwargs["trade_date"] = trade_date
        try:
            df = await self._call(
                pro.daily_basic, **kwargs,
                fields="ts_code,trade_date,pe,pb",
            )
        except TushareClientError:
            # daily_basic may be quota-limited; return empty rather than fail
            return {}
        if df is None or df.empty:
            return {}
        row = df.iloc[0]
        return {
            "ts_code": ts_code,
            "pe": float(row.get("pe") or 0),
            "pb": float(row.get("pb") or 0),
            "trade_date": str(row.get("trade_date", trade_date)),
        }

    async def get_daily_price(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[DailyPrice]:
        pro = self._ensure_pro()
        df = await self._call(
            pro.daily, ts_code=ts_code, start_date=start_date, end_date=end_date,
        )
        results = []
        for _, row in df.iterrows():
            results.append(DailyPrice(
                ts_code=ts_code,
                trade_date=str(row["trade_date"]),
                open=float(row.get("open", 0) or 0),
                high=float(row.get("high", 0) or 0),
                low=float(row.get("low", 0) or 0),
                close=float(row.get("close", 0) or 0),
                volume=int(row.get("vol", 0) or 0),
                amount=float(row.get("amount", 0) or 0),
                change_pct=float(row.get("pct_chg", 0) or 0),
            ))
        return results

    async def get_income_statement(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        pro = self._ensure_pro()
        df = await self._call(
            pro.income, ts_code=ts_code, start_date=start_date, end_date=end_date,
            fields="ts_code,end_date,report_type,revenue,n_income,operate_profit",
        )
        return self._map_income(df)

    async def get_balance_sheet(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        pro = self._ensure_pro()
        df = await self._call(
            pro.balancesheet, ts_code=ts_code, start_date=start_date, end_date=end_date,
            fields="ts_code,end_date,report_type,total_assets,total_liab,total_hldr_eqy_exc_min_int",
        )
        results = []
        for _, row in df.iterrows():
            assets = float(row.get("total_assets", 0) or 0)
            liab = float(row.get("total_liab", 0) or 0)
            equity = float(row.get("total_hldr_eqy_exc_min_int", 0) or 0)
            results.append(FinancialStatement(
                ts_code=ts_code,
                end_date=str(row["end_date"]),
                report_type=_report_type(str(row.get("report_type", "1"))),
                total_assets=assets,
                total_liabilities=liab,
                equity=equity,
            ))
        return results

    async def get_cashflow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        pro = self._ensure_pro()
        df = await self._call(
            pro.cashflow, ts_code=ts_code, start_date=start_date, end_date=end_date,
            fields="ts_code,end_date,report_type,n_cashflow_act",
        )
        results = []
        for _, row in df.iterrows():
            results.append(FinancialStatement(
                ts_code=ts_code,
                end_date=str(row["end_date"]),
                report_type=_report_type(str(row.get("report_type", "1"))),
                operating_cash_flow=float(row.get("n_cashflow_act", 0) or 0),
            ))
        return results

    async def get_financial_summary(
        self, ts_code: str, start_date: str, end_date: str
    ) -> list[FinancialStatement]:
        """Merge income + balance + cashflow into unified statements."""
        income = await self.get_income_statement(ts_code, start_date, end_date)
        balance = await self.get_balance_sheet(ts_code, start_date, end_date)
        cashflow = await self.get_cashflow(ts_code, start_date, end_date)

        by_period: dict[str, FinancialStatement] = {}
        for stmt in income + balance + cashflow:
            key = stmt.end_date
            if key not in by_period:
                by_period[key] = stmt
            else:
                target = by_period[key]
                for field_name in ("revenue", "net_profit", "operating_profit",
                                   "total_assets", "total_liabilities", "equity",
                                   "operating_cash_flow"):
                    src = getattr(stmt, field_name)
                    if src is not None and getattr(target, field_name) is None:
                        setattr(target, field_name, src)

        # Compute derived metrics
        for stmt in by_period.values():
            if stmt.equity and stmt.equity > 0 and stmt.net_profit is not None:
                stmt.roe = stmt.net_profit / stmt.equity
            if stmt.bvps is None and stmt.equity and stmt.net_profit:
                stmt.bvps = stmt.equity / (stmt.net_profit / (stmt.basic_eps or 1) if stmt.basic_eps else 1)

        return list(by_period.values())

    def _map_income(self, df) -> list[FinancialStatement]:
        results = []
        for _, row in df.iterrows():
            results.append(FinancialStatement(
                ts_code=str(row["ts_code"]),
                end_date=str(row["end_date"]),
                report_type=_report_type(str(row.get("report_type", "1"))),
                revenue=float(row.get("revenue", 0) or 0),
                net_profit=float(row.get("n_income", 0) or 0),
                operating_profit=float(row.get("operate_profit", 0) or 0),
            ))
        return results


def _report_type(rt: str) -> str:
    """Map Tushare report_type codes to unified names."""
    mapping = {
        "1": "annual",
        "2": "q1",
        "3": "q2",
        "4": "q3",
        "5": "annual",
    }
    return mapping.get(rt, "annual")


# ─── Provider Extension Points ─────────────────────────────────────────────


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

    async def get_stock_basic(self, market=None, industry=None, ts_codes=None):
        return await self._cached(f"basic:{market}:{industry}:{ts_codes}",
            lambda: self._inner.get_stock_basic(market, industry, ts_codes))

    async def get_daily_price(self, ts_code, start_date, end_date):
        return await self._cached(f"price:{ts_code}:{start_date}:{end_date}",
            lambda: self._inner.get_daily_price(ts_code, start_date, end_date))

    async def get_valuation(self, ts_code, trade_date=""):
        return await self._cached(f"val:{ts_code}:{trade_date}",
            lambda: self._inner.get_valuation(ts_code, trade_date))

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
