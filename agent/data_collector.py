# Data Collector — the ONLY component that touches MarketDataProvider
#
# Skills must never call a provider. The Data Collector:
#   1. Reads stocks / prices / financials / valuation from the provider
#   2. Wraps everything in a ResearchDataset of DataSnapshots
#   3. Records per-call provenance + trace records for the run
#
# The ResearchDataset is immutable → replayable, point-in-time.

from __future__ import annotations

from datetime import datetime

from runtime.run_recorder import RunRecorder
from runtime.snapshot import DataSnapshot, ResearchDataset
from runtime.tracing.agent_trace import TraceRecord
from tools.providers import MarketDataProvider, StockBasic


class DataCollector:
    """Exclusive provider accessor producing an immutable ResearchDataset."""

    def __init__(
        self,
        provider: MarketDataProvider,
        recorder: RunRecorder | None = None,
        run_id: str = "",
    ):
        self._provider = provider
        self._recorder = recorder
        self._run_id = run_id
        self._trace: list[TraceRecord] = []

    @property
    def trace_records(self) -> list[TraceRecord]:
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
        prices = await self._fetch_prices(stocks, start_date, end_date)
        financials = await self._fetch_financials(stocks, start_date, end_date) if load_financials else {}
        valuation = await self._fetch_valuation(stocks) if load_valuation else {}

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
        try:
            if stock_codes:
                stocks = await self._provider.get_stock_basic(ts_codes=stock_codes)
            else:
                stocks = await self._provider.get_stock_basic()
            self._trace.append(TraceRecord.make(
                run_id=self._run_id, step_id="data-collector", kind="tool",
                name="get_stock_basic",
                input_data={"stock_codes": stock_codes or None},
                output_data=[s.ts_code for s in stocks],
                duration_ms=0,
            ))
            return stocks
        except Exception as e:
            # Degrade: for explicit codes we can still analyse prices/valuation
            if stock_codes:
                stubs = [StockBasic(ts_code=c, name=c, industry="") for c in stock_codes]
                self._trace.append(TraceRecord.make(
                    run_id=self._run_id, step_id="data-collector", kind="tool",
                    name="get_stock_basic",
                    input_data={"stock_codes": stock_codes},
                    output_data={"note": f"degraded: {e}"},
                    status="error", error=str(e)[:200],
                ))
                return stubs
            raise

    async def _fetch_prices(
        self, stocks: list[StockBasic], start_date: str, end_date: str
    ) -> dict[str, list]:
        """Fetch daily prices for all stocks (parallel where possible)."""
        import asyncio

        async def one(s: StockBasic) -> tuple[str, list]:
            try:
                rows = await self._provider.get_daily_price(
                    s.ts_code, start_date, end_date)
                self._trace.append(TraceRecord.make(
                    run_id=self._run_id, step_id="data-collector", kind="tool",
                    name="get_daily_price",
                    input_data={"ts_code": s.ts_code},
                    output_data={"rows": len(rows)},
                    duration_ms=0,
                ))
                return s.ts_code, [r.__dict__ for r in rows]
            except Exception as e:
                self._trace.append(TraceRecord.make(
                    run_id=self._run_id, step_id="data-collector", kind="tool",
                    name="get_daily_price",
                    input_data={"ts_code": s.ts_code},
                    output_data={},
                    status="error", error=str(e)[:200],
                ))
                return s.ts_code, []

        results = await asyncio.gather(*(one(s) for s in stocks))
        return {code: rows for code, rows in results}

    async def _fetch_financials(
        self, stocks: list[StockBasic], start_date: str, end_date: str
    ) -> dict[str, list]:
        """Fetch financial statements (income/balance/cashflow merged)."""
        import asyncio

        async def one(s: StockBasic) -> tuple[str, list]:
            try:
                rows = await self._provider.get_financial_summary(
                    s.ts_code, start_date, end_date)
                self._trace.append(TraceRecord.make(
                    run_id=self._run_id, step_id="data-collector", kind="tool",
                    name="get_financial_summary",
                    input_data={"ts_code": s.ts_code},
                    output_data={"periods": len(rows)},
                    duration_ms=0,
                ))
                return s.ts_code, [r.__dict__ for r in rows]
            except Exception as e:
                self._trace.append(TraceRecord.make(
                    run_id=self._run_id, step_id="data-collector", kind="tool",
                    name="get_financial_summary",
                    input_data={"ts_code": s.ts_code},
                    output_data={},
                    status="error", error=str(e)[:200],
                ))
                return s.ts_code, []

        results = await asyncio.gather(*(one(s) for s in stocks))
        return {code: rows for code, rows in results}

    async def _fetch_valuation(self, stocks: list[StockBasic]) -> dict[str, dict]:
        """Fetch PE/PB valuation for all stocks."""
        import asyncio

        async def one(s: StockBasic) -> tuple[str, dict]:
            try:
                val = await self._provider.get_valuation(s.ts_code)
                self._trace.append(TraceRecord.make(
                    run_id=self._run_id, step_id="data-collector", kind="tool",
                    name="get_valuation",
                    input_data={"ts_code": s.ts_code},
                    output_data=val,
                    duration_ms=0,
                ))
                return s.ts_code, val or {}
            except Exception as e:
                self._trace.append(TraceRecord.make(
                    run_id=self._run_id, step_id="data-collector", kind="tool",
                    name="get_valuation",
                    input_data={"ts_code": s.ts_code},
                    output_data={},
                    status="error", error=str(e)[:200],
                ))
                return s.ts_code, {}

        results = await asyncio.gather(*(one(s) for s in stocks))
        return {code: val for code, val in results}
