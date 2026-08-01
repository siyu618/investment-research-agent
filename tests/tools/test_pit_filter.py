"""Tests for Point-in-Time (PIT) filtering in DataCollector."""

import asyncio

import pytest
from agent.data_collector import DataCollector
from tools.providers import MockMarketDataProvider


@pytest.mark.asyncio
class TestPITFilter:
    async def test_future_annual_excluded(self):
        """FY2024 annual (ann ~2025-03) must be excluded at as_of=2024-06-30."""
        dc = DataCollector(MockMarketDataProvider())
        ds = await dc.collect(stock_codes=["600519.SH"], as_of="20240630",
                              load_valuation=False)
        fin = ds.financials("600519.SH")
        assert len(fin) == 0  # no report disclosed by 2024-06-30

    async def test_past_annual_included(self):
        """FY2024 annual included when as_of is after its announcement."""
        dc = DataCollector(MockMarketDataProvider())
        ds = await dc.collect(stock_codes=["600519.SH"], as_of="20251231",
                              load_valuation=False)
        fin = ds.financials("600519.SH")
        assert len(fin) == 1  # FY2024 annual
        assert fin[0]["end_date"] == "20241231"

    async def test_prices_filtered_by_trade_date(self):
        """Prices after as_of must not enter the dataset."""
        dc = DataCollector(MockMarketDataProvider())
        ds = await dc.collect(stock_codes=["600519.SH"], as_of="20240110",
                              load_valuation=False)
        prices = ds.prices("600519.SH")
        assert len(prices) > 0
        # Every kept price must be <= as_of
        for p in prices:
            assert p["trade_date"] <= "20240110"

    async def test_all_records_have_ann_date(self):
        """Mock financial records must carry a disclosure date > period end."""
        dc = DataCollector(MockMarketDataProvider())
        ds = await dc.collect(stock_codes=["600519.SH"], as_of="20261231",
                              load_valuation=False)
        for f in ds.financials("600519.SH"):
            assert f["ann_date"], "financial record missing ann_date"
            assert f["ann_date"] > f["end_date"], "ann_date must be after end_date"

    async def test_no_as_of_keeps_all(self):
        """Without as_of, no filtering applied (all records kept)."""
        dc = DataCollector(MockMarketDataProvider())
        ds = await dc.collect(stock_codes=["600519.SH"], load_valuation=False)
        assert len(ds.financials("600519.SH")) >= 1

    async def test_valuation_future_excluded(self):
        """Valuation with trade_date > as_of must not enter the dataset."""
        dc = DataCollector(MockMarketDataProvider())
        # as_of before the mock valuation's trade_date (20251231)
        ds = await dc.collect(stock_codes=["600519.SH"], as_of="20250101",
                              load_financials=False)
        val = ds.valuation("600519.SH")
        # Mock valuation trade_date is 20251231 > 20250101 → excluded
        assert val == {}

    async def test_valuation_past_included(self):
        dc = DataCollector(MockMarketDataProvider())
        ds = await dc.collect(stock_codes=["600519.SH"], as_of="20261231",
                              load_financials=False)
        val = ds.valuation("600519.SH")
        assert val.get("pe") is not None

    async def test_pit_stats_recorded(self):
        """DataCollector must record per-layer PIT filter statistics."""
        dc = DataCollector(MockMarketDataProvider())
        await dc.collect(stock_codes=["600519.SH"], as_of="20250101",
                         load_valuation=False)
        stats = dc._pit_stats
        assert stats, "expected PIT stats to be recorded"
        for key, counts in stats.items():
            assert "fetched" in counts
            assert "kept" in counts
            assert "filtered_future" in counts
            assert "filtered_unknown_date" in counts
