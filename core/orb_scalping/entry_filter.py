"""
QuantOS — Candidate 18b entry filter (docs/ORB_ENTRY_FILTER_METHODOLOGY.md)
────────────────────────────────────────────────────────────────────────────
Candidate 18b is candidate 18's signal with an entry gate layered on top --
a distinct strategy in its own right (own live process, own position store,
own dry-run log, own prospective verdict), named "b" rather than the next
open candidate number to record that direct lineage. Gates entries on the
two conditions docs/ORB_CONDITION_MINING_RESULTS.md found informative,
replicated twice (2026-09-03 and 2026-09-21, each with fresh trades folded
in): NIFTY only on Monday/Friday, BankNifty only on a >0.3% gap day.
Exactly the mined pairing, applied to its own index only — see the
methodology doc's Scope section for why NIFTY does not also get the gap
filter and vice versa (both cross-applications were tested in the mining
exercise and failed).

Pure functions only, no I/O, no config. The live script decides WHETHER
to call these (only `--variant filtered`, i.e. candidate 18b, does;
unfiltered candidate 18 never calls this module at all) and supplies
whatever data each predicate needs.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from core.orb_scalping.conditions import gap_pct as _gap_pct

# core/orb_scalping/conditions.py's own pre-registered value
# (docs/ORB_CONDITION_MINING_METHODOLOGY.md's "big gap" predicate),
# reused unmodified -- this document does not re-tune it.
BIG_GAP_THRESHOLD_PCT = 0.3

# Python's date.weekday(): Monday=0 ... Sunday=6.
_MONDAY = 0
_FRIDAY = 4


def nifty_entry_allowed(trade_date: date) -> bool:
    """Monday or Friday only. docs/ORB_CONDITION_MINING_RESULTS.md's
    `monday_or_friday` condition."""
    return trade_date.weekday() in (_MONDAY, _FRIDAY)


def banknifty_entry_allowed(today_first_candle_open: float,
                             prior_daily_close: Optional[float]) -> bool:
    """|gap%| > BIG_GAP_THRESHOLD_PCT vs. the prior trading day's daily
    close. docs/ORB_CONDITION_MINING_RESULTS.md's `big_gap` condition.

    False (not None/raise) when there is no prior close to compare — an
    unclassifiable day is not a gap day, same "exclude, don't guess"
    convention condition-mining's own predicates use for a missing input."""
    gap = _gap_pct(today_first_candle_open, prior_daily_close)
    if gap is None:
        return False
    return abs(gap) > BIG_GAP_THRESHOLD_PCT
