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

# ── Sampled-spread (post-hoc, 3x/day timer, 2026-07-29 to 2026-07-30) ──────
# `deploy/systemd/quantos-orb-spread-probe.{service,timer}` (deployed
# 2026-07-28) appends every fire to data_cache/orb_scalping_spread_samples.
# csv. First two days of REAL fires (n=7 per leg — the 2026-07-28 fire
# itself failed on a stale VM token, confirming wiring not data) give a
# blended round-trip spread of NIFTY 0.196%, BANKNIFTY 0.235% of mid — both
# well BELOW even Harsh's flat 0.15-0.30% assumption, and 5-11x tighter
# than the single 2026-07-28 post-close snapshot above (that day happened
# to be both NIFTY's weekly AND BankNifty's monthly expiry, plausibly an
# unusually wide-spread outlier day, not a representative one).
#   NIFTY:     mean CE 0.208%, PE 0.185%  -> blended 0.196% -> bps = 50*0.196 = 9.8
#   BANKNIFTY: mean CE 0.208%, PE 0.263%  -> blended 0.235% -> bps = 50*0.235 = 11.8
# Still only 2 distinct days / 7 fires per leg -- same "directional, not yet
# a rigorously sampled rate" caveat as Real-spread above, just with a
# larger (still small) n. Recompute again once the timer has accumulated
# more sessions.
SAMPLED_SPREAD_SLIPPAGE_BPS = {"NIFTY": 9.8, "BANKNIFTY": 11.8}

# ── Stratified (post-hoc, THE recheck Fable's 2026-07-31 review required,
#    first computed 2026-08-31, CORRECTED 2026-09-01/02) ───────────────────
# The whole reason Sampled-spread above was not trustworthy: its 2-day
# window (2026-07-29/30) contained ZERO expiry-day samples, so its blended
# rate was a non-expiry-day-only rate by accident. By 2026-08-31 the timer
# had accumulated a full month, and the first stratified rates below
# (11.1/20.5 NIFTY, 13.6/18.7 BANKNIFTY) claimed expiry-day spread was
# "roughly DOUBLE" the ordinary-day rate on both indices.
#
# THAT CLAIM WAS WRONG. Fable's adversarial review of the recheck
# (2026-09-01) found two rows in the accumulated dataset that predate
# market open — 2026-08-04 02:10 UTC (07:40 IST) and 2026-07-30 02:55 UTC
# (08:25 IST), neither matching the probe timer's own 04:05/06:30/09:45 UTC
# fires (leftover manual test runs) — and NIFTY's CE/PE spreads on the
# pre-open row were 10-15x every legitimate intraday sample (1.528%/3.368%
# vs a normal 0.1-0.4%). That single row, sitting inside an n=13 expiry-day
# stratum, single-handedly manufactured the "roughly DOUBLE" finding.
# scripts/analyze_orb_spread_samples.py now filters to the 09:15-15:30 IST
# trading session before computing any mean (is_in_session()), and the
# numbers below are the corrected re-run against the same (now larger, 244
# in-session rows / 20 days / 5 expiry days) CSV.
#
# Corrected finding: NIFTY's expiry-day rate is now statistically
# INDISTINGUISHABLE from its ordinary-day rate (11.8 vs 11.0 bps) — the
# "expiry days are riskier" concern does not hold up for NIFTY once the
# contaminated row is removed. BankNifty's expiry-day stratum (n=3, all
# from the single 2026-08-25 monthly expiry) is unaffected by this specific
# bug and still reads meaningfully wider (18.7 vs 13.2), but Fable flagged a
# SEPARATE, still-open concern about it: real probe data shows BankNifty's
# own DTE-floor-style roll actually triggers on/around its monthly expiry
# (DTE 0-1), contradicting the methodology doc's claim that BankNifty
# "never triggers" a DTE floor — meaning the BN expiry-day rate may have
# been measured on a different contract tier than the one the backtest
# actually holds on that day, and Black-Scholes premium reconstruction at
# DTE=0 needs its own check. NOT yet resolved; tracked in project memory,
# not silently assumed fine.
#   NIFTY:     non-expiry n=46/leg  mean CE 0.206%/PE 0.235% -> blended 0.221% -> bps=11.0
#              expiry-day n=15/leg  mean CE 0.202%/PE 0.271% -> blended 0.237% -> bps=11.8
#   BANKNIFTY: non-expiry n=58/leg  mean CE 0.251%/PE 0.276% -> blended 0.264% -> bps=13.2
#              expiry-day n=3/leg   mean CE 0.403%/PE 0.346% -> blended 0.375% -> bps=18.7 (unchanged, see above)
# (conversion identical to every prior spread variant: slippage_bps is
# charged on both legs, so round-trip spread_pct = 2*slippage_bps/100.)
#
# THIS IS STILL THE LOCKED FINAL COST VARIANT — the 2026-09-01/02 update is
# a CORRECTION within it (a data-quality bug fix), not a sixth variant.
# Fable was explicit that a genuine correction, found by inspecting the
# same locked methodology more carefully, is not the same failure mode as
# the earlier four-variant progression (Clean -> Stressed -> Harsh ->
# Real-spread -> Sampled-spread), which had no pre-registered stopping rule
# and happened to stop exactly when the number turned favorable. If this
# verdict needs revisiting again, the right move is a fresh, larger sample
# under this SAME stratified-and-session-filtered methodology, not a new
# cost-model tier.
STRATIFIED_SPREAD_SLIPPAGE_BPS = {
    ("NIFTY", False):     11.0,   # non-expiry-day
    ("NIFTY", True):      11.8,   # expiry-day
    ("BANKNIFTY", False): 13.2,
    ("BANKNIFTY", True):  18.7,   # unchanged -- see BankNifty caveat above, still open
}


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


def sampled_spread_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                               entry_date: date, underlying: str) -> CostBreakdown:
    """POST-HOC (2026-07-30) — same idea as `real_spread_trade_cost()` but
    uses the 3x/day timer's accumulating multi-session average instead of
    one post-close snapshot. Still a small sample (see module docstring
    above `SAMPLED_SPREAD_SLIPPAGE_BPS`) — a better directional estimate
    than the single-day Real-spread variant, not yet a final rate."""
    if underlying not in SAMPLED_SPREAD_SLIPPAGE_BPS:
        raise ValueError(f"unsupported underlying: {underlying!r}")
    return _model(
        entry_date, SAMPLED_SPREAD_SLIPPAGE_BPS[underlying], brokerage_pct=HARSH_BROKERAGE_PCT,
    ).round_trip(buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size)


def stratified_spread_trade_cost(entry_premium: float, exit_premium: float, lot_size: float,
                                  entry_date: date, underlying: str,
                                  is_expiry_day: bool) -> CostBreakdown:
    """THE LOCKED FINAL COST VARIANT (2026-08-31) — see module docstring
    above `STRATIFIED_SPREAD_SLIPPAGE_BPS`. Same rate-lookup pattern as
    Real-spread/Sampled-spread, but keyed by (underlying, is_expiry_day)
    instead of underlying alone: whether ENTRY_DATE ITSELF is a NIFTY
    weekly / BankNifty monthly expiry day (a market-wide condition, not
    which contract this particular trade holds — see
    core/orb_scalping/backtest.py's is_expiry_day computation)."""
    key = (underlying, bool(is_expiry_day))
    if key not in STRATIFIED_SPREAD_SLIPPAGE_BPS:
        raise ValueError(f"unsupported (underlying, is_expiry_day): {key!r}")
    return _model(
        entry_date, STRATIFIED_SPREAD_SLIPPAGE_BPS[key], brokerage_pct=HARSH_BROKERAGE_PCT,
    ).round_trip(buy_price=entry_premium, sell_price=exit_premium, quantity=lot_size)
