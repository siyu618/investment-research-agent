# Data Snapshot — uniform point-in-time data container
#
# A DataSnapshot wraps ALL data a Skill consumes. Skills MUST NOT call
# MarketDataProvider directly — they only read snapshots. This guarantees:
#   - Reproducibility: same snapshot → same result, anywhere, any time
#   - Replay: snapshots are serialized to runs/{run_id}/data_snapshot.json
#   - Point-in-time: as_of/publish_date/effective_date prevent look-ahead
#   - Provenance: source/query_params/content_hash/snapshot_hash/version

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, ClassVar

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


# ─── Freeze / unfreeze ───────────────────────────────────────────────────


def _deep_freeze(obj: Any) -> Any:
    """Recursively freeze a nested list/dict into immutable structures.

    list → tuple, dict → MappingProxyType (read-only), recursively.
    Scalars returned as-is. Used to make DataSnapshot truly immutable —
    no callable path can mutate shared data.
    """
    import copy

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
    if isinstance(obj, MappingProxyType):
        return {k: _deep_unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [_deep_unfreeze(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _deep_unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_unfreeze(v) for v in obj]
    return obj


# ─── DataSnapshot ────────────────────────────────────────────────────────


@dataclass(frozen=True)
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

    Immutability:
      - dataclass(frozen=True) blocks field re-assignment
      - __post_init__ deep-freezes containers into tuples + read-only
        MappingProxyType (object.__setattr__ bypasses frozen for init)
      - accessors return read-only views; mutation raises TypeError

    Hashing:
      - content_hash: over data layers + query context, EXCLUDES
        run-varying timestamps — stable for caching / cross-env compare
      - snapshot_hash: over content_hash + as_of/publish_date/effective_date/
        version — the full context, used for Replay equivalence
    """

    VERSION: ClassVar[str] = "2.0.0"

    as_of: str
    source: str
    query_params: dict = field(default_factory=dict)

    # Data layers (deep-frozen in __post_init__)
    stocks: tuple = field(default_factory=tuple)
    prices: dict = field(default_factory=dict)
    financials: dict = field(default_factory=dict)
    valuation: dict = field(default_factory=dict)

    version: str = field(default_factory=lambda: DataSnapshot.VERSION)

    # Time semantics
    publish_date: str = ""
    effective_date: str = ""
    trade_date: str = ""

    def __post_init__(self) -> None:
        """Deep-freeze all containers (frozen dataclass + immutable inner)."""
        object.__setattr__(self, "query_params", _deep_freeze(self.query_params))
        object.__setattr__(self, "stocks", _deep_freeze(self.stocks))
        object.__setattr__(self, "prices", _deep_freeze(self.prices))
        object.__setattr__(self, "financials", _deep_freeze(self.financials))
        object.__setattr__(self, "valuation", _deep_freeze(self.valuation))

    # ─── Content hash (data only, no run-varying timestamps) ────────────

    def _content_dict(self) -> dict[str, Any]:
        """Data content for content_hash — EXCLUDES as_of/publish/effective.

        content_hash is stable across runs of the same underlying data,
        suitable for caching and cross-environment comparison.
        """
        return {
            "source": self.source,
            "query_params": _deep_unfreeze(self.query_params),
            "version": self.version,
            "trade_date": self.trade_date,
            "stocks": _deep_unfreeze(self.stocks),
            "prices": _deep_unfreeze(self.prices),
            "financials": _deep_unfreeze(self.financials),
            "valuation": _deep_unfreeze(self.valuation),
        }

    @property
    def content_hash(self) -> str:
        """Hash over data content only (stable across runs)."""
        return hash_of(self._content_dict())

    # ─── Snapshot hash (full context, for Replay) ───────────────────────

    def _snapshot_dict(self) -> dict[str, Any]:
        """Full context for snapshot_hash — content + time semantics."""
        d = self._content_dict()
        d.update({
            "as_of": self.as_of,
            "publish_date": self.publish_date,
            "effective_date": self.effective_date,
        })
        return d

    @property
    def snapshot_hash(self) -> str:
        """Hash over full context incl. timestamps — used for Replay."""
        return hash_of(self._snapshot_dict())

    # Backward-compat alias (older code used data_hash)
    @property
    def data_hash(self) -> str:
        """Deprecated alias for snapshot_hash (full-context hash)."""
        return self.snapshot_hash

    # ─── Serialization (FULL data, all fields preserved) ────────────────

    def to_dict(self, include_data: bool = True) -> dict:
        """Serialize the COMPLETE snapshot — every field + time semantics.

        Unlike content_hash (which drops run-varying timestamps), the
        persisted JSON keeps as_of / publish_date / effective_date so a
        run can be fully reconstructed.
        """
        d: dict[str, Any] = {
            "as_of": self.as_of,
            "source": self.source,
            "query_params": _deep_unfreeze(self.query_params),
            "version": self.version,
            "publish_date": self.publish_date,
            "effective_date": self.effective_date,
            "trade_date": self.trade_date,
            "content_hash": self.content_hash,
            "snapshot_hash": self.snapshot_hash,
            # legacy alias for compat
            "data_hash": self.snapshot_hash,
        }
        if include_data:
            d.update({
                "stocks": _deep_unfreeze(self.stocks),
                "prices": _deep_unfreeze(self.prices),
                "financials": _deep_unfreeze(self.financials),
                "valuation": _deep_unfreeze(self.valuation),
            })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> DataSnapshot:
        """Rebuild a snapshot from a serialized dict (for replay).

        Reads all business fields including time semantics. Ignores the
        hash fields (recomputed on the rebuilt object).
        """
        return cls(
            as_of=d.get("as_of", ""),
            source=d.get("source", ""),
            query_params=d.get("query_params", {}),
            stocks=tuple(d.get("stocks", [])),
            prices=d.get("prices", {}),
            financials=d.get("financials", {}),
            valuation=d.get("valuation", {}),
            version=d.get("version", DataSnapshot.VERSION),
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
        as_of_val = as_of or datetime.now().isoformat()
        return cls(
            as_of=as_of_val,
            source=source,
            query_params=query_params or {},
            stocks=tuple(_serialize(stocks)) if stocks else (),
            prices={k: _serialize(v) for k, v in (prices or {}).items()},
            financials={k: _serialize(v) for k, v in (financials or {}).items()},
            valuation=valuation or {},
            publish_date=publish_date,
            effective_date=publish_date or as_of_val,
            trade_date=trade_date,
        )


# ─── ResearchDataset (multi-slice aggregate) ─────────────────────────────


class ResearchDataset:
    """Aggregate of DataSnapshots for one analysis run.

    Skills receive a ResearchDataset (or a slice) rather than a provider.
    It exposes typed accessors so Skills never touch raw providers.

    Truly immutable: slices held as a tuple; the container cannot be
    reassigned or extended after construction.
    """

    _slices: tuple[DataSnapshot, ...]

    def __init__(self, slices: list[DataSnapshot]):
        object.__setattr__(self, "_slices", tuple(slices))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: Any) -> None:
        """Block any attribute assignment after construction."""
        raise AttributeError(f"ResearchDataset is immutable: cannot set '{name}'")

    @property
    def slices(self) -> tuple[DataSnapshot, ...]:
        return self._slices

    @property
    def as_of(self) -> str:
        return self._slices[-1].as_of if self._slices else ""

    def stocks(self) -> list[dict]:
        """All stocks across all slices (deduplicated by ts_code).

        Returns read-only proxy views; mutation raises TypeError.
        """
        seen: dict[str, Any] = {}
        for s in self._slices:
            for st in s.stocks:
                seen[st["ts_code"]] = st
        return list(seen.values())

    def prices(self, ts_code: str) -> tuple:
        """Price series for a stock across all slices (read-only)."""
        out: list[dict] = []
        for s in self._slices:
            out.extend(s.prices.get(ts_code, ()))
        return tuple(out)

    def financials(self, ts_code: str) -> tuple:
        """Financial statements for a stock across all slices (read-only)."""
        out: list[dict] = []
        for s in self._slices:
            out.extend(s.financials.get(ts_code, ()))
        return tuple(out)

    def valuation(self, ts_code: str) -> dict:
        """Latest valuation for a stock (read-only proxy)."""
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
