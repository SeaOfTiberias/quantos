"""
QuantOS — ORB Options Scalping Cost Model (candidate 18)
──────────────────────────────────────────────────────────
Buy-to-open / sell-to-close option round-trip cost, per
docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md's "Cost model" section. Reuses
candidate 15's exact F&O rate sourcing unchanged (`core/options/vrp/
costs.py`'s time-varying `stt_sell_rate()`/`EXCHANGE_TXN_PCT`, composed
with `core/risk/costs.py`'s `CostModel.round_trip()`), and adds the
Clean/Stressed split this candidate's methodology doc requires: every
backtest run reports BOTH a frictionless-slippage number and one stressed
by an extra 15bps/leg — using `CostModel`'s own existing `slippage_bps`
parameter and `_slippage()`/`round_trip()` plumbing directly, no new
slippage mechanic needed.
"""

from __future__ import annotations

from datetime import date

from core.options.vrp.costs import EXCHANGE_TXN_PCT, stt_sell_rate
from core.risk.costs import CostBreakdown, CostModel

STRESSED_SLIPPAGE_BPS = 15.0   # methodology doc: midpoint of the reviewed 10-20bps range


def _model(entry_date: date, slippage_bps: float) -> CostModel:
    return CostModel(
        stt_pct=stt_sell_rate(entry_date),
        exchange_txn_pct=EXCHANGE_TXN_PCT,
        slippage_bps=slippage_bps,
    )


def clean_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                      entry_date: date) -> CostBreakdown:
    """Round-trip cost (INR), no slippage stress — the cost model exactly
    as specified in the methodology doc's base Cost model section."""
    return _model(entry_date, 0.0).round_trip(
        buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size,
    )


def stressed_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                         entry_date: date) -> CostBreakdown:
    """Same cost model plus an additional 15bps-per-leg slippage penalty —
    the methodology doc's Stressed variant, which gates any live-capital
    move (a Clean-only pass is not sufficient)."""
    return _model(entry_date, STRESSED_SLIPPAGE_BPS).round_trip(
        buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size,
    )
