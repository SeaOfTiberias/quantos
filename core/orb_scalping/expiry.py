"""
QuantOS — NIFTY Weekly Expiry Calendar (candidate 18, Open Item #3)
────────────────────────────────────────────────────────────────────
NIFTY weekly options expired on Thursday through 2025-08-31, then moved to
Tuesday from 2025-09-01 — the same SEBI/HO/MRD/TPD-1/P/CIR/2025/76 cutover
already coded for BankNifty's MONTHLY expiry in
scripts/gutcheck_expiry_day_effect.py, applied here to NIFTY's WEEKLY
cadence instead.

Confirmed against real NSE bhavcopy 2026-07-28 (already-cached VRP data,
data_cache/nse_bhavcopy/parsed/): the last Thursday-based weekly was
2025-08-28, the first Tuesday-based weekly was 2025-09-02 — a clean
one-week cutover with no overlap, matching this module's logic exactly
across every transition-week date checked (2025-08-18 through 2025-09-05).

`adjust_for_holiday()`/`LAST_THURSDAY_CUTOFF` are reused unchanged from
scripts/gutcheck_expiry_day_effect.py — same precedent as candidate 15's
reuse of that module for BankNifty's monthly calendar, not reimplemented
here.
"""

from __future__ import annotations

from datetime import date, timedelta

from scripts.gutcheck_expiry_day_effect import LAST_THURSDAY_CUTOFF, adjust_for_holiday

_THURSDAY = 3
_TUESDAY = 1


def _nearest_weekday_on_or_after(d: date, weekday: int) -> date:
    """weekday: Monday=0 ... Sunday=6."""
    delta = (weekday - d.weekday()) % 7
    return d + timedelta(days=delta)


def nifty_weekly_expiry_unadjusted(trade_date: date) -> date:
    """The nearest weekly expiry on/after `trade_date`, before holiday
    adjustment. Thursday-based if that candidate falls on/before
    LAST_THURSDAY_CUTOFF, else Tuesday-based — confirmed live against real
    bhavcopy transition-week data (module docstring)."""
    thursday_candidate = _nearest_weekday_on_or_after(trade_date, _THURSDAY)
    if thursday_candidate <= LAST_THURSDAY_CUTOFF:
        return thursday_candidate
    return _nearest_weekday_on_or_after(trade_date, _TUESDAY)


def nifty_weekly_expiry(trade_date: date, trading_days: set) -> date:
    """Holiday-adjusted nearest NIFTY weekly expiry on/after `trade_date`."""
    return adjust_for_holiday(nifty_weekly_expiry_unadjusted(trade_date), trading_days)


def next_nifty_weekly_expiry(expiry: date, trading_days: set) -> date:
    """The weekly expiry immediately after `expiry` — used by the DTE-floor
    rule (methodology doc's Contract selection section): when an entry's
    days_to_expiry on the nearest weekly is <2, roll to this contract
    instead."""
    return nifty_weekly_expiry(expiry + timedelta(days=1), trading_days)


def is_nifty_weekly_expiry_day(trade_date: date, trading_days: set) -> bool:
    """True iff `trade_date` is itself NIFTY's own (holiday-adjusted) weekly
    expiry date — a market-wide condition (every NIFTY contract trading that
    day sees it, not only the one this backtest happens to hold), used to
    stratify option spread cost by expiry-day vs ordinary-day. See
    core/orb_scalping/costs.py's stratified_spread_trade_cost, which is the
    reason this predicate exists: scripts/analyze_orb_spread_samples.py
    found expiry-day round-trip spreads roughly DOUBLE the ordinary-day
    rate on real sampled data."""
    return nifty_weekly_expiry(trade_date, trading_days) == trade_date
