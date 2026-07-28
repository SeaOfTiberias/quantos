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

`real_spread_trade_cost()` (added 2026-07-28, same day) goes one step
further: `scripts/probe_orb_scalping_real_spreads.py` fetched a REAL, live
bid-ask option chain (NIFTY next-weekly, BankNifty next-monthly, both
skipping any 0-DTE-today contract) and found round-trip bid-ask-crossing
cost of 1.1-3.2% of premium (NIFTY) and 0.6-2.0% (BankNifty) — 2-10x
LARGER than even Harsh's 0.3-0.6% assumption. This is a SINGLE post-
market-close snapshot on one day, not a sampled average across sessions —
disclosed as a rough, directional estimate, not a rigorously sampled rate
the way Stressed/Harsh's bps were chosen. Uses a blended (CALL+PUT
averaged) round-trip rate per index, converted to an equivalent
per-leg slippage_bps (round-trip spread %% = 2 * slippage_bps / 100, i.e.
slippage_bps = 50 * spread_pct), plus the same forced flat-brokerage
harsh mode already applies.
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

# ── Real-spread (post-hoc, one live snapshot 2026-07-28 18:03 IST) ─────────
# Measured ATM CALL/PUT round-trip bid-ask spread as %% of mid, blended:
#   NIFTY:     CALL 1.1%, PUT 3.2%  -> blended 2.15%  -> slippage_bps = 50*2.15 = 107.5
#   BANKNIFTY: CALL 0.6%, PUT 2.0%  -> blended 1.3%   -> slippage_bps = 50*1.3  = 65.0
# (round-trip spread_pct = 2 * slippage_bps / 100, since CostModel charges
# slippage_bps on BOTH the buy and sell leg's own turnover -- see
# core/risk/costs.py's _slippage()/round_trip().)
REAL_SPREAD_SLIPPAGE_BPS = {"NIFTY": 107.5, "BANKNIFTY": 65.0}


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


def real_spread_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                            entry_date: date, underlying: str) -> CostBreakdown:
    """POST-HOC, rough directional estimate (2026-07-28) — uses a real,
    live-measured option bid-ask spread instead of an assumed slippage
    rate. See module docstring: this is ONE snapshot, not a sampled
    average, so treat this as a sanity check on Harsh's assumption, not a
    fourth rigorously pre-registered tier."""
    if underlying not in REAL_SPREAD_SLIPPAGE_BPS:
        raise ValueError(f"unsupported underlying: {underlying!r}")
    return _model(
        entry_date, REAL_SPREAD_SLIPPAGE_BPS[underlying], brokerage_pct=HARSH_BROKERAGE_PCT,
    ).round_trip(buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size)
