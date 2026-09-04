"""
QuantOS — ORB Scalping: Shared Contract-Selection Helpers (candidate 18)
──────────────────────────────────────────────────────────────────────
Extracted, not duplicated, from the two existing spread probes so a new
order-placing layer-2 script (scripts/run_orb_scalping_live.py) doesn't
become a third copy of the same DTE-floor/strike-matching logic. This
project already hit one real bug from exactly this kind of duplication
drifting: scripts/probe_orb_scalping_real_spreads.py's 2026-09-02 fix,
where NIFTY's DTE floor had been silently applied to BankNifty too.

`scripts/probe_orb_scalping_real_spreads.py` now imports `select_expiry`
from here instead of defining it (thin, behavior-preserving change).
`scripts/probe_orb_scalping_stopout_spreads.py` is UNCHANGED -- it is
mid-way through its own separate pre-registered data collection and must
not be touched by this refactor; it still defines its own
NIFTY_DTE_FLOOR_DAYS/BANKNIFTY_DTE_FLOOR_DAYS constants locally and
imports select_expiry from the real-spreads probe, which now re-exports
this module's version unchanged.
"""

from __future__ import annotations

from datetime import date

NIFTY_DTE_FLOOR_DAYS = 2       # core/orb_scalping/backtest.py's resolve_nifty_expiry
BANKNIFTY_DTE_FLOOR_DAYS = 0   # resolve_banknifty_expiry has no floor


def select_expiry(expiries: list[date], today: date, dte_floor_days: int) -> date | None:
    """The nearest expiry on/after `today` whose days-to-expiry clears
    `dte_floor_days`, or None if every listed expiry is too close. Pure and
    broker-free so this selection rule is independently testable -- it is
    the exact piece that had the 2026-09-02 bug (a shared floor silently
    applied to both underlyings)."""
    for e in expiries:
        if (e - today).days < dte_floor_days:
            continue
        return e
    return None


def fetch_chain_row_near_strike(broker, underlying: str, expiry: date, strike: float,
                                 option_type: str, strike_interval: float) -> dict | None:
    """Nearest row to `strike` for the given option_type -- tolerant match
    (within half a strike interval) rather than an exact float equality
    check, since this strike was fixed at entry and never re-struck (per
    core/orb_scalping/premium.py's atm_strike() contract). `expiry` must
    already be resolved to the exact expiry the caller holds (or intends
    to hold) -- this function does no expiry-selection logic of its own."""
    from core.options import fyers_symbol_master as sm

    expiry_epoch = sm.get_expiry_epoch(underlying, expiry)
    raw_chain = broker.get_option_chain(underlying, expiry_epoch)
    rows = raw_chain.get("optionsChain", [])
    candidates = [r for r in rows if r.get("option_type") == option_type]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda r: abs(r.get("strike_price", 0) - strike))
    if abs(nearest.get("strike_price", 0) - strike) > strike_interval / 2:
        return None
    return nearest
