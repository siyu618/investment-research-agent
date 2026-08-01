# Data Snapshot — uniform point-in-time data container
#
# A DataSnapshot wraps ALL data a Skill consumes. Skills MUST NOT call
# MarketDataProvider directly — they only read snapshots. This guarantees:
#   - Reproducibility: same snapshot → same result, anywhere, any time
#   - Replay: snapshots are serialized to runs/{run_id}/data_snapshot.json
#   - Point-in-time: as_of/publish_date/effective_date prevent look-ahead
#   - Provenance: source/query_params/data_hash/version for every value

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# ─── Deterministic hashing ───────────────────────────────────────────────


def hash_of(data: Any) -> str:
    """Stable SHA-256 of JSON-serializable data.

    Deterministic across processes (unlike Python's hash()).
    """
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _serialize(rows: list[Any]) -> list[dict]:
    """Convert dataclass rows to plain dicts (JSON-serializable)."""
    if rows and hasattr(rows[0], "__dataclass_fields__"):
        return [asdict(r) for r in rows]
    return [r if isinstance(r, dict) else dict(r) for r in rows]


# ─── DataSnapshot ────────────────────────────────────────────────────────


def _deep_freeze(obj: Any) -> Any:
    """Recursively freeze a nested list/dict into immutable structures.

    list → tuple, dict → MappingProxyType (read-only), recursively.
    Scalars returned as-is. Used to make DataSnapshot truly immutable —
    no callable path can mutate shared data.
    """
    import copy
    from types import MappingProxyType

    if isinstance(obj, dict):
        return MappingProxyType({
            k: _deep_freeze(v) for k, v in obj.items()
        })
    if isinstance(obj, (list, tuple)):
        return tuple(_deep_freeze(v) for v in obj)
    if hasattr(obj, "__dataclass_fields__"):
        return _deep_freeze(copy.deepcopy(obj))
    return obj


def _deep_unfreeze(obj: Any) -> Any:
    """Convert frozen structures back to plain list/dict (for serialization)."""
    from types import MappingProxyType

    if isinstance(obj, MappingProxyType):
        return {k: _deep_unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [_deep_unfreeze(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _deep_unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_unfreeze(v) for v in obj]
    return obj


@dataclass
class DataSnapshot:
    """Immutable point-in-time view of one data slice.

    Layers (all optional, populated by the Data Collector):
      - stocks:     list[StockBasic] dicts
      - prices:     list[DailyPrice] dicts (per stock)
      - financials: list[FinancialStatement] dicts (per stock)
      - valuation:  dict of {ts_code: {pe, pb, trade_date}}

    Metadata (required for PIT analysis):
      as_of, source, query_params, version, publish_date,
      effective_date, trade_date.

    Immutability: __post_init__ deep-freezes all data layers into
    tuples + read-only MappingProxyType. Query accessors return deep
    copies. Mutating an internal container raises TypeError.
    """

    as_of: str
    source: str
    query_params: dict = field(default_factory=dict)

    # Data layers (deep-frozen in __post_init__)
    stocks: list[dict] = field(default_factory=list)
    prices: dict[str, list[dict]] = field(default_factory=dict)
    financials: dict[str, list[dict]] = field(default_factory=dict)
    valuation: dict[str, dict] = field(default_factory=dict)

    version: str = "2.0.0"

    # Time semantics
    publish_date: str = ""
    effective_date: str = ""
    trade_date: str = ""

    def __post_init__(self) -> None:
        """Deep-freeze all data layers so the snapshot is truly immutable."""
        self.query_params = _deep_freeze(self.query_params)  # type: ignore[assignment]
        self.stocks = _deep_freeze(self.stocks)  # type: ignore[assignment]
        self.prices = _deep_freeze(self.prices)  # type: ignore[assignment]
        self.financials = _deep_freeze(self.financials)  # type: ignore[assignment]
        self.valuation = _deep_freeze(self.valuation)  # type: ignore[assignment]

    # ─── Hash ──────────────────────────────────────────────────────────

    @property
    def data_hash(self) -> str:
        """Stable hash of all content (for replay verification).

        Hashes the content WITHOUT the hash field itself (no recursion).
        """
        payload = json.dumps(self._content_dict(),
                             sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _content_dict(self) -> dict[str, Any]:
        """Content for hashing — EXCLUDES run-varying timestamps.

        as_of/publish_date/effective_date change between runs; the content
        hash must be stable so the same data replayable anywhere, any time.
        """
        d: dict[str, Any] = {
            "source": self.source,
            "query_params": _deep_unfreeze(self.query_params),
            "version": self.version,
            "trade_date": self.trade_date,
            "stocks": _deep_unfreeze(self.stocks),
            "prices": _deep_unfreeze(self.prices),
            "financials": _deep_unfreeze(self.financials),
            "valuation": _deep_unfreeze(self.valuation),
        }
        return d

    # ─── Serialization ─────────────────────────────────────────────────

    def to_dict(self, include_data: bool = True) -> dict:
        d: dict[str, Any] = dict(self._content_dict())
        d["data_hash"] = self.data_hash
        if include_data:
            d.update({
                "stock_count": len(self.stocks),
                "price_series": {k: len(v) for k, v in self.prices.items()},
                "financial_series": {k: len(v) for k, v in self.financials.items()},
                "valuation_count": len(self.valuation),
            })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> DataSnapshot:
        """Rebuild a snapshot from a serialized dict (for replay)."""
        return cls(
            as_of=d.get("as_of", ""),
            source=d.get("source", ""),
            query_params=d.get("query_params", {}),
            stocks=d.get("stocks", []),
            prices=d.get("prices", {}),
            financials=d.get("financials", {}),
            valuation=d.get("valuation", {}),
            version=d.get("version", "2.0.0"),
            publish_date=d.get("publish_date", ""),
            effective_date=d.get("effective_date", ""),
            trade_date=d.get("trade_date", ""),
        )

    # ─── Convenience builders ──────────────────────────────────────────

    @classmethod
    def build(
        cls,
        *,
        as_of: str | None = None,
        source: str,
        query_params: dict | None = None,
        stocks: list[Any] | None = None,
        prices: dict[str, list[Any]] | None = None,
        financials: dict[str, list[Any]] | None = None,
        valuation: dict[str, dict] | None = None,
        publish_date: str = "",
        trade_date: str = "",
    ) -> DataSnapshot:
        """Build a snapshot from raw dataclass rows (serializes internally)."""
        return cls(
            as_of=as_of or datetime.now().isoformat(),
            source=source,
            query_params=query_params or {},
            stocks=_serialize(stocks) if stocks else [],
            prices={k: _serialize(v) for k, v in (prices or {}).items()},
            financials={k: _serialize(v) for k, v in (financials or {}).items()},
            valuation=valuation or {},
            publish_date=publish_date,
            effective_date=publish_date or (as_of or ""),
            trade_date=trade_date,
        )


# ─── ResearchDataset (multi-slice aggregate) ─────────────────────────────


class ResearchDataset:
    """Aggregate of DataSnapshots for one analysis run.

    Skills receive a ResearchDataset (or a slice) rather than a provider.
    It exposes typed accessors so Skills never touch raw providers.

    Immutable once built: slices cannot be added after creation,
    guaranteeing deterministic replay.
    """

    def __init__(self, slices: list[DataSnapshot]):
        self._slices = slices
        self._frozen = True

    @property
    def slices(self) -> list[DataSnapshot]:
        return self._slices

    @property
    def as_of(self) -> str:
        return self._slices[-1].as_of if self._slices else ""

    def stocks(self) -> list[dict]:
        """All stocks across all slices (deduplicated by ts_code)."""
        seen: dict[str, dict] = {}
        for s in self._slices:
            for st in s.stocks:
                seen[st["ts_code"]] = st
        return list(seen.values())

    def prices(self, ts_code: str) -> list[dict]:
        """Price series for a stock across all slices."""
        out: list[dict] = []
        for s in self._slices:
            out.extend(s.prices.get(ts_code, []))
        return out

    def financials(self, ts_code: str) -> list[dict]:
        """Financial statements for a stock across all slices."""
        out: list[dict] = []
        for s in self._slices:
            out.extend(s.financials.get(ts_code, []))
        return out

    def valuation(self, ts_code: str) -> dict:
        """Latest valuation for a stock."""
        latest: dict = {}
        for s in self._slices:
            if ts_code in s.valuation:
                latest = s.valuation[ts_code]
        return latest

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "slice_count": len(self._slices),
            "slices": [s.to_dict() for s in self._slices],
        }

    @classmethod
    def from_dict(cls, d: dict) -> ResearchDataset:
        slices = [DataSnapshot.from_dict(s) for s in d.get("slices", [])]
        return cls(slices)
