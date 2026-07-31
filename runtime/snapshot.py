# Data Snapshot — uniform wrapper around all data a Skill consumes
#
# Every Skill reads data through a DataSnapshot, NOT directly from an
# unvalidated data source. This enables:
#   - Point-in-time auditability (as_of, publish_date, effective_date, trade_date)
#   - Future-function prevention (Skills can only see data <= as_of)
#   - Replay support (same snapshot → same result)
#   - Provenance (source, query_params, data_hash)

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DataSnapshot:
    """Immutable view of data at a point in time.

    Attributes:
        as_of:          Analysis cutoff datetime (ISO). Skills must not see
                        data published after this.
        source:         Provider that produced the data (e.g. "tushare", "mock").
        query_params:   Parameters used to fetch the data.
        data_hash:      SHA-256 of the canonical serialized data.
        version:        Snapshot schema version.
        data:           The actual payload (list of dicts / dict).
        publish_date:   When the source published this data (ISO).
        effective_date: When this data becomes effective (ISO).
        trade_date:     Trading date this data belongs to (YYYYMMDD).
    """

    as_of: str
    source: str
    query_params: dict = field(default_factory=dict)
    data: Any = field(default_factory=list)
    version: str = "1.0.0"

    # Time semantics (for future-function prevention / replay)
    publish_date: str = ""
    effective_date: str = ""
    trade_date: str = ""

    @property
    def data_hash(self) -> str:
        """SHA-256 of canonical data representation."""
        payload = json.dumps(self.data, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "source": self.source,
            "query_params": self.query_params,
            "data_hash": self.data_hash,
            "version": self.version,
            "publish_date": self.publish_date,
            "effective_date": self.effective_date,
            "trade_date": self.trade_date,
            "row_count": len(self.data) if isinstance(self.data, list) else 1,
            "data": self.data,
        }

    @classmethod
    def from_rows(
        cls,
        rows: list[Any],
        source: str,
        query_params: dict,
        as_of: str | None = None,
        publish_date: str = "",
        trade_date: str = "",
    ) -> DataSnapshot:
        """Build a snapshot from dataclass rows (StockBasic/DailyPrice/etc).

        Converts dataclasses to dicts via dataclasses.asdict.
        """
        from dataclasses import asdict

        if rows and hasattr(rows[0], "__dataclass_fields__"):
            serialized = [asdict(r) for r in rows]
        else:
            serialized = list(rows)

        return cls(
            as_of=as_of or datetime.now().isoformat(),
            source=source,
            query_params=query_params,
            data=serialized,
            publish_date=publish_date,
            trade_date=trade_date,
            effective_date=publish_date or (as_of or ""),
        )


def hash_of(data: Any) -> str:
    """Compute a stable hash of arbitrary JSON-serializable data."""
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
