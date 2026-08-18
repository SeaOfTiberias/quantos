"""
QuantOS — India reference data.

The rules of the market, as distinct from the market's data. Nothing in here
touches the network at runtime: these are facts about how NSE works, derived
or transcribed once, committed, and read from disk.

This package is the moat named in docs/SCOPE.md. A global vendor must average
India's rules away against forty other venues; we do not, and being correct
here is the entire content of "smarter". Correctness that a global tool
structurally cannot afford is worth more than data breadth it can trivially
buy.

    from core.reference.calendar import is_trading_day, trading_days

Contents:
  calendar.py — whether a date was an NSE session. The authority; nothing
                else may decide this for itself.

Planned, in the order docs/SCOPE.md commits to:
  expiries      — promoted out of core/orb_scalping/expiry.py, which already
                  handles the 2025-09-01 Thursday->Tuesday weekly cutover
                  correctly and cites the SEBI circular for it
  lot_sizes     — historical revisions, not today's snapshot
  membership    — point-in-time index constituents, folded in from
                  core/rotation/nifty500_reconstitution.py
  charges       — folded in from core/risk/costs.py
"""

from core.reference.calendar import (
    CalendarError,
    DateOutOfRange,
    coverage,
    filter_sessions,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    session_count,
    shift_sessions,
    trading_days,
)

__all__ = [
    "CalendarError",
    "DateOutOfRange",
    "coverage",
    "filter_sessions",
    "is_trading_day",
    "next_trading_day",
    "previous_trading_day",
    "session_count",
    "shift_sessions",
    "trading_days",
]
