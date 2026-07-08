"""
Fill reconciliation (Sprint 6) — measure realized entry slippage.

Compares each executed signal's *intended* entry (the alert `price`) against the
*actual* broker fill (`execution_price`) and reports the slippage, per trade and
in aggregate.

The aggregate `suggested_slippage_bps` is the empirical feed for the S5-1 cost
model's per-leg `slippage_bps` parameter. `DEFAULT_COST_MODEL` keeps slippage at
0 (realized fills already embed it), but a *backtest* needs a realistic per-leg
slippage assumption to avoid frictionless, over-optimistic fills — and this is
where that number comes from once real trades accrue.

Scope: only the ENTRY leg is measured. A signal stores its intended entry but
not an intended exit, so exit slippage is not observable from stored data. The
suggestion therefore assumes exit slippage is similar in magnitude to entry
slippage — a documented approximation, to be revisited if fill capture later
records intended exits.

Sign convention (unified across direction): **positive slippage_bps = adverse**
(a worse fill than the signal implied — a real cost); negative = favorable.
- BUY  (long entry):  adverse when fill > signal  → (fill - signal)/signal
- SELL (short entry): adverse when fill < signal  → (signal - fill)/signal
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class FillDelta:
    """Entry-slippage of a single executed signal."""
    signal_id:        str
    symbol:           str
    action:           str          # BUY = long, anything else = short/SELL
    signal_price:     float        # intended entry (alert price)
    execution_price:  float        # actual broker fill
    slippage_bps:     float        # signed; + = adverse (cost), - = favorable

    @property
    def is_adverse(self) -> bool:
        return self.slippage_bps > 0

    @property
    def slippage_abs(self) -> float:
        """Signed rupee slippage per share (+ = paid more / received less)."""
        if self.action.upper() == "BUY":
            return self.execution_price - self.signal_price
        return self.signal_price - self.execution_price


@dataclass(frozen=True)
class SlippageReport:
    """Aggregate entry-slippage across a set of executed signals."""
    count:                  int
    deltas:                 list[FillDelta] = field(default_factory=list)
    mean_bps:               float = 0.0
    median_bps:             float = 0.0
    adverse_count:          int = 0
    adverse_rate:           float = 0.0     # fraction of fills worse than signal
    worst_bps:              float = 0.0     # most adverse (max signed bps)
    best_bps:               float = 0.0     # most favorable (min signed bps)
    suggested_slippage_bps: float = 0.0     # per-leg feed for the S5-1 cost model

    def to_dict(self) -> dict:
        return {
            "count":                  self.count,
            "mean_bps":               round(self.mean_bps, 2),
            "median_bps":             round(self.median_bps, 2),
            "adverse_count":          self.adverse_count,
            "adverse_rate":           round(self.adverse_rate, 3),
            "worst_bps":              round(self.worst_bps, 2),
            "best_bps":               round(self.best_bps, 2),
            "suggested_slippage_bps": round(self.suggested_slippage_bps, 2),
            "deltas": [
                {
                    "signal_id":       d.signal_id,
                    "symbol":          d.symbol,
                    "action":          d.action,
                    "signal_price":    d.signal_price,
                    "execution_price": d.execution_price,
                    "slippage_bps":    round(d.slippage_bps, 2),
                }
                for d in self.deltas
            ],
        }


def _entry_slippage_bps(action: str, signal_price: float, execution_price: float) -> float:
    """Signed entry slippage in basis points (+ = adverse). `signal_price` must
    be > 0 (guarded by the caller)."""
    if action.upper() == "BUY":
        raw = (execution_price - signal_price) / signal_price
    else:  # SELL / short entry — adverse when the fill is below the signal
        raw = (signal_price - execution_price) / signal_price
    return raw * 10_000.0


def delta_from_record(record: dict) -> Optional[FillDelta]:
    """Build a FillDelta from a signal dict (the shape SignalDB returns), or
    None if the signal wasn't filled or lacks a usable entry price. Skipping
    keeps the aggregate clean without the caller pre-filtering by status."""
    signal_price    = record.get("price")
    execution_price = record.get("execution_price")
    if execution_price is None or signal_price is None:
        return None
    if signal_price <= 0 or execution_price <= 0:
        return None
    action = record.get("action") or ""
    return FillDelta(
        signal_id=record.get("signal_id", ""),
        symbol=record.get("symbol", ""),
        action=action,
        signal_price=float(signal_price),
        execution_price=float(execution_price),
        slippage_bps=_entry_slippage_bps(action, float(signal_price), float(execution_price)),
    )


def reconcile(records: Iterable[dict]) -> SlippageReport:
    """
    Reconcile intended vs actual entry fills across `records` (signal dicts).
    Records without an `execution_price` (never filled) or a positive
    `price`/`execution_price` are skipped. Returns an empty-but-valid report
    when nothing reconcilable is present.

    `suggested_slippage_bps` = max(0, mean_bps): if fills are on average adverse,
    feed that per-leg cost into a backtest's CostModel; if they're on average
    favorable, suggest 0 rather than banking on luck you can't count on.
    """
    deltas = [d for d in (delta_from_record(r) for r in records) if d is not None]
    if not deltas:
        return SlippageReport(count=0)

    bps = [d.slippage_bps for d in deltas]
    mean_bps   = statistics.fmean(bps)
    median_bps = statistics.median(bps)
    adverse    = [d for d in deltas if d.is_adverse]

    return SlippageReport(
        count=len(deltas),
        deltas=deltas,
        mean_bps=mean_bps,
        median_bps=median_bps,
        adverse_count=len(adverse),
        adverse_rate=len(adverse) / len(deltas),
        worst_bps=max(bps),
        best_bps=min(bps),
        suggested_slippage_bps=max(0.0, mean_bps),
    )
