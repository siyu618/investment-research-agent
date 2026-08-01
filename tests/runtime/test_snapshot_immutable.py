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

    def test_content_hash_stable_across_snapshots(self):
        a = _make_snapshot()
        b = _make_snapshot()
        # content_hash excludes run-varying timestamps → stable
        assert a.content_hash == b.content_hash

    def test_snapshot_hash_differs_with_as_of(self):
        """snapshot_hash includes as_of → different across runs."""
        from runtime.snapshot import DataSnapshot

        a = DataSnapshot.build(source="mock", as_of="2024-01-01",
                               stocks=[{"ts_code": "x"}])
        b = DataSnapshot.build(source="mock", as_of="2025-01-01",
                               stocks=[{"ts_code": "x"}])
        assert a.content_hash == b.content_hash  # same data
        assert a.snapshot_hash != b.snapshot_hash  # different as_of

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


class TestSnapshotSerialization:
    def test_roundtrip_preserves_time_fields(self):
        """to_dict → from_dict must preserve as_of/publish/effective/trade."""
        s = DataSnapshot.build(
            source="mock", as_of="2024-06-30",
            query_params={"market": "SSE"},
            stocks=[{"ts_code": "600519.SH"}],
            publish_date="2024-06-30",
            trade_date="20240630",
        )
        d = s.to_dict()
        rebuilt = DataSnapshot.from_dict(d)
        assert rebuilt.as_of == "2024-06-30"
        assert rebuilt.publish_date == "2024-06-30"
        assert rebuilt.effective_date == "2024-06-30"
        assert rebuilt.trade_date == "20240630"
        assert rebuilt.source == "mock"

    def test_roundtrip_preserves_data_layers(self):
        s = _make_snapshot()
        d = s.to_dict()
        rebuilt = DataSnapshot.from_dict(d)
        assert rebuilt.stocks[0]["ts_code"] == "600519.SH"
        assert rebuilt.prices["600519.SH"][0]["close"] == 100.0
        assert rebuilt.financials["600519.SH"][0]["revenue"] == 1e9
        assert rebuilt.valuation["600519.SH"]["pe"] == 20.0

    def test_snapshot_hash_roundtrip_stable(self):
        s = _make_snapshot()
        rebuilt = DataSnapshot.from_dict(s.to_dict())
        assert rebuilt.snapshot_hash == s.snapshot_hash

    def test_content_hash_roundtrip_stable(self):
        s = _make_snapshot()
        rebuilt = DataSnapshot.from_dict(s.to_dict())
        assert rebuilt.content_hash == s.content_hash


class TestObjectImmutability:
    def test_snapshot_field_reassignment_raises(self):
        s = _make_snapshot()
        with pytest.raises(Exception):
            s.as_of = "9999-01-01"  # type: ignore[misc]

    def test_snapshot_source_reassignment_raises(self):
        s = _make_snapshot()
        with pytest.raises(Exception):
            s.source = "hacked"  # type: ignore[misc]

    def test_dataset_attribute_assignment_raises(self):
        ds = ResearchDataset([_make_snapshot()])
        with pytest.raises(AttributeError):
            ds._slices = ()  # type: ignore[assignment]

    def test_dataset_slices_is_tuple(self):
        ds = ResearchDataset([_make_snapshot()])
        assert isinstance(ds.slices, tuple)

    def test_dataset_prices_read_only(self):
        ds = ResearchDataset([_make_snapshot()])
        prices = ds.prices("600519.SH")
        assert isinstance(prices, tuple)
        with pytest.raises(TypeError):
            prices[0]["close"] = 999.0  # type: ignore[index]
