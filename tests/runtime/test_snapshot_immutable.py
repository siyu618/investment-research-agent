"""Tests for DataSnapshot / ResearchDataset immutability."""

import pytest
from runtime.snapshot import DataSnapshot, ResearchDataset


def _make_snapshot() -> DataSnapshot:
    return DataSnapshot.build(
        source="mock",
        query_params={"market": "SSE"},
        stocks=[{"ts_code": "600519.SH", "name": "贵州茅台"}],
        prices={"600519.SH": [{"ts_code": "600519.SH", "trade_date": "20240102",
                               "close": 100.0}]},
        financials={"600519.SH": [{"ts_code": "600519.SH", "end_date": "20241231",
                                   "revenue": 1e9}]},
        valuation={"600519.SH": {"pe": 20.0, "pb": 3.0}},
    )


class TestSnapshotImmutability:
    def test_internal_lists_are_tuples(self):
        from types import MappingProxyType

        s = _make_snapshot()
        assert isinstance(s.stocks, tuple)
        assert isinstance(s.prices, MappingProxyType)
        assert isinstance(s.stocks[0], MappingProxyType)

    def test_mutating_internal_dict_raises(self):
        from types import MappingProxyType

        s = _make_snapshot()
        # stocks entries are read-only proxies
        stock = s.stocks[0]
        assert isinstance(stock, MappingProxyType)
        with pytest.raises(TypeError):
            stock["name"] = "HACK"  # type: ignore[index]

    def test_mutating_nested_price_raises(self):
        s = _make_snapshot()
        price = s.prices["600519.SH"][0]
        with pytest.raises(TypeError):
            price["close"] = 999.0  # type: ignore[index]

    def test_valuation_is_read_only(self):
        s = _make_snapshot()
        with pytest.raises(TypeError):
            s.valuation["600519.SH"]["pe"] = 999.0  # type: ignore[index]

    def test_hash_stable_across_snapshots(self):
        a = _make_snapshot()
        b = _make_snapshot()
        assert a.data_hash == b.data_hash

    def test_research_dataset_stocks_read_only(self):
        ds = ResearchDataset([_make_snapshot()])
        stocks = ds.stocks()
        with pytest.raises(TypeError):
            stocks[0]["name"] = "HACK"  # type: ignore[index]

    def test_serialization_roundtrip_preserves_content(self):
        s = _make_snapshot()
        d = s.to_dict()
        assert d["stocks"][0]["ts_code"] == "600519.SH"
        assert d["prices"]["600519.SH"][0]["close"] == 100.0
        assert d["valuation"]["600519.SH"]["pe"] == 20.0
