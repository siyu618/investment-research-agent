# Data Collector — the ONLY component that touches MarketDataProvider
#
# Skills must never call a provider. The Data Collector:
#   1. Reads stocks / prices / financials / valuation from the provider
#   2. Wraps everything in a ResearchDataset of DataSnapshots
#   3. Records per-call provenance via trace_span (real duration + hash)
#
# The ResearchDataset is immutable → replayable, point-in-time.

from __future__ import annotations

from datetime import datetime

from runtime.run_recorder import RunRecorder
from runtime.snapshot import DataSnapshot, ResearchDataset
from runtime.tracing.trace_span import trace_span
from tools.providers import MarketDataProvider, StockBasic


def _as_of_iso(as_of: str | None) -> str:
    """Normalize an as_of value to ISO date (YYYY-MM-DD) for comparison.

    Accepts ISO ('2024-06-30') or compact ('20240630'); empty → ''.
    """
    if not as_of:
        return ""
    a = as_of.replace("-", "").replace("/", "")
    if len(a) == 8:
        return f"{a[:4]}-{a[4:6]}-{a[6:8]}"
    return as_of


class DataCollector:
    """Exclusive provider accessor producing an immutable ResearchDataset."""

    def __init__(
        self,
        provider: MarketDataProvider,
        recorder: RunRecorder | None = None,
        run_id: str = "",
        policy_mode: str = "standard",
    ):
        self._provider = provider
        self._recorder = recorder
        self._run_id = run_id
        self._policy_mode = policy_mode
        self._pit_stats: dict[str, dict] = {}  # per-layer PIT filter counts
        self._trace: list[dict] = []

    @property
    def trace_records(self) -> list[dict]:
        return self._trace

    async def collect(
        self,
        stock_codes: list[str] | None = None,
        start_date: str = "20240101",
        end_date: str = "20251231",
        as_of: str | None = None,
        load_financials: bool = True,
        load_valuation: bool = True,
    ) -> ResearchDataset:
        """Collect all data layers and return a ResearchDataset.

        Provider calls happen here ONLY. Financial/valuation failures are
        recorded as degraded traces but do not fail the run.
        """
        stocks = await self._fetch_stocks(stock_codes)
        prices = await self._fetch_prices(stocks, start_date, end_date, as_of)
        financials = (
            await self._fetch_financials(stocks, start_date, end_date, as_of)
            if load_financials
            else {}
        )
        valuation = (
            await self._fetch_valuation(stocks, as_of)
            if load_valuation
            else {}
        )

        snapshot = DataSnapshot.build(
            as_of=as_of or datetime.now().strftime("%Y-%m-%d"),
            source=self._provider.__class__.__name__,
            query_params={
                "stock_codes": stock_codes or None,
                "start_date": start_date,
                "end_date": end_date,
            },
            stocks=stocks,
            prices=prices,
            financials=financials,
            valuation=valuation,
            publish_date=datetime.now().strftime("%Y-%m-%d"),
            trade_date=end_date,
        )

        return ResearchDataset([snapshot])

    # ─── Per-layer fetches ─────────────────────────────────────────────

    async def _fetch_stocks(self, stock_codes: list[str] | None) -> list[StockBasic]:
        """Fetch stock universe. Degrades to code stubs for single-stock."""
        async with trace_span(
            self._run_id, "data-collector", "tool", "get_stock_basic",
            sink=self._trace,
        ) as span:
            span.set_input({"stock_codes": stock_codes or None})
            try:
                if stock_codes:
                    stocks = await self._provider.get_stock_basic(ts_codes=stock_codes)
                else:
                    stocks = await self._provider.get_stock_basic()
                span.set_output([s.ts_code for s in stocks])
                return stocks
            except Exception as e:
                # Degrade: for explicit codes we can still analyse prices/valuation
                if stock_codes:
                    stubs = [StockBasic(ts_code=c, name=c, industry="") for c in stock_codes]
                    span.set_output({"note": f"degraded: {e}"})
                    span.status = "error"
                    span.error = str(e)[:200]
                    return stubs
                raise

    async def _fetch_prices(
        self,
        stocks: list[StockBasic],
        start_date: str,
        end_date: str,
        as_of: str | None = None,
    ) -> dict[str, list]:
        """Fetch daily prices for all stocks, filtering by as_of (PIT)."""
        import asyncio

        async def one(s: StockBasic) -> tuple[str, list]:
            async with trace_span(
                self._run_id, "data-collector", "tool", "get_daily_price",
                sink=self._trace,
            ) as span:
                span.set_input({"ts_code": s.ts_code})
                try:
                    rows = await self._provider.get_daily_price(
                        s.ts_code, start_date, end_date)
                    as_of_iso = _as_of_iso(as_of)
                    filtered = [
                        r for r in rows
                        if not as_of_iso or r.available_at <= as_of_iso
                    ]
                    span.set_output({"rows": len(rows), "kept": len(filtered)})
                    return s.ts_code, [r.__dict__ for r in filtered]
                except Exception as e:
                    span.status = "error"
                    span.error = str(e)[:200]
                    span.set_output({})
                    return s.ts_code, []

        results = await asyncio.gather(*(one(s) for s in stocks))
        return {code: rows for code, rows in results}

    async def _fetch_financials(
        self,
        stocks: list[StockBasic],
        start_date: str,
        end_date: str,
        as_of: str | None = None,
    ) -> dict[str, list]:
        """Fetch financial statements, filtering by ann_date <= as_of (PIT)."""
        import asyncio

        async def one(s: StockBasic) -> tuple[str, list]:
            async with trace_span(
                self._run_id, "data-collector", "tool", "get_financial_summary",
                sink=self._trace,
            ) as span:
                span.set_input({"ts_code": s.ts_code})
                try:
                    rows = await self._provider.get_financial_summary(
                        s.ts_code, start_date, end_date)
                    # PIT: keep only records disclosed by as_of (available_at)
                    as_of_iso = _as_of_iso(as_of)
                    filtered = []
                    filtered_future = 0
                    filtered_unknown = 0
                    for r in rows:
                        # Unknown announcement date: strict → exclude + error,
                        # standard → exclude + warning; never assume public
                        if as_of_iso and not getattr(r, "ann_date", ""):
                            filtered_unknown += 1
                            continue
                        if as_of_iso and r.available_at > as_of_iso:
                            filtered_future += 1
                            continue
                        filtered.append(r)
                    span.set_output({"periods": len(rows), "kept": len(filtered),
                                     "filtered_future": filtered_future,
                                     "filtered_unknown": filtered_unknown})
                    self._pit_stats[f"financial:{s.ts_code}"] = {
                        "fetched": len(rows),
                        "kept": len(filtered),
                        "filtered_future": filtered_future,
                        "filtered_unknown_date": filtered_unknown,
                    }
                    return s.ts_code, [r.__dict__ for r in filtered]
                except Exception as e:
                    span.status = "error"
                    span.error = str(e)[:200]
                    span.set_output({})
                    return s.ts_code, []

        results = await asyncio.gather(*(one(s) for s in stocks))
        return {code: rows for code, rows in results}

    async def _fetch_valuation(
        self, stocks: list[StockBasic], as_of: str | None = None
    ) -> dict[str, dict]:
        """Fetch PE/PB valuation, validating trade_date <= as_of (PIT)."""
        import asyncio

        as_of_iso = _as_of_iso(as_of)

        async def one(s: StockBasic) -> tuple[str, dict]:
            async with trace_span(
                self._run_id, "data-collector", "tool", "get_valuation",
                sink=self._trace,
            ) as span:
                span.set_input({"ts_code": s.ts_code, "as_of": as_of_iso})
                try:
                    val = await self._provider.get_valuation(s.ts_code, trade_date=as_of or "")
                    val = val or {}
                    # PIT: future valuation (trade_date > as_of) must not enter
                    vdate = val.get("trade_date", "")
                    if as_of_iso and vdate and vdate > as_of_iso:
                        span.set_output({"filtered": "future_valuation",
                                         "trade_date": vdate, "as_of": as_of_iso})
                        return s.ts_code, {}
                    span.set_output(val)
                    return s.ts_code, val
                except Exception as e:
                    span.status = "error"
                    span.error = str(e)[:200]
                    span.set_output({})
                    return s.ts_code, {}

        results = await asyncio.gather(*(one(s) for s in stocks))
        return {code: val for code, val in results}
