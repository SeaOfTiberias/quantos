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

`harsh_trade_cost()` (added 2026-07-28, POST-HOC — after the pre-
registered Clean/Stressed backtest already ran and passed) is an
additional stress test Fable's adversarial review recommended, not a
retroactive change to Clean/Stressed's own definitions (which stay
exactly as reported — see the methodology doc's "what would make this
untrustworthy" list). It targets two gaps Fable found: (1) the %-capped
brokerage formula above, inherited unchanged from candidate 15 where the
cap never bound (that strategy's premiums were much larger) — at this
candidate's smaller ATM premiums it charges ~Rs3-10/trade instead of the
flat ~Rs20/leg a real discount F&O broker charges; harsh mode forces the
cap to always bind. (2) NIFTY's DTE-floor rule (core/orb_scalping/
backtest.py) routes ~40% of NIFTY trades into a next-week contract that's
typically less liquid than the front week — harsh mode charges that
subset a higher slippage rate instead of the same flat 15bps as
everything else.
"""

from __future__ import annotations

from datetime import date

from core.options.vrp.costs import EXCHANGE_TXN_PCT, stt_sell_rate
from core.risk.costs import CostBreakdown, CostModel

STRESSED_SLIPPAGE_BPS = 15.0   # methodology doc: midpoint of the reviewed 10-20bps range

# ── Harsh (post-hoc, Fable-recommended) ─────────────────────────────────────
# Forces CostModel's min(brokerage_pct * turnover, brokerage_flat) to always
# resolve to the flat Rs20/leg side: brokerage_pct=1.0 (100% of turnover)
# exceeds Rs20 for any turnover above Rs20, true of every real trade here.
HARSH_BROKERAGE_PCT = 1.0
HARSH_FRONT_WEEK_SLIPPAGE_BPS = 15.0   # same as Stressed for the more-liquid subset
HARSH_NEXT_WEEK_SLIPPAGE_BPS = 30.0    # double, for the DTE-floor-rolled (less liquid) subset


def _model(entry_date: date, slippage_bps: float, brokerage_pct: float = 0.0003) -> CostModel:
    return CostModel(
        stt_pct=stt_sell_rate(entry_date),
        exchange_txn_pct=EXCHANGE_TXN_PCT,
        slippage_bps=slippage_bps,
        brokerage_pct=brokerage_pct,
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


def harsh_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                      entry_date: date, liquidity_tier: str = "front_week") -> CostBreakdown:
    """POST-HOC additional stress test (Fable's recommendation, 2026-07-28)
    — not part of the pre-registered Clean/Stressed pair. Always forces the
    flat Rs20/leg brokerage side of the cap (see module docstring), and
    charges a higher slippage rate on `liquidity_tier="next_week"` (the
    NIFTY DTE-floor-rolled subset) than on `"front_week"` (everything
    else, including all of BankNifty)."""
    if liquidity_tier == "next_week":
        slippage_bps = HARSH_NEXT_WEEK_SLIPPAGE_BPS
    elif liquidity_tier == "front_week":
        slippage_bps = HARSH_FRONT_WEEK_SLIPPAGE_BPS
    else:
        raise ValueError(f"unsupported liquidity_tier: {liquidity_tier!r}")
    return _model(entry_date, slippage_bps, brokerage_pct=HARSH_BROKERAGE_PCT).round_trip(
        buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size,
    )
