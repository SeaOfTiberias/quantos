"""Tests for scripts/probe_orb_scalping_real_spreads.py's expiry selection.

Added 2026-09-02 after Fable's adversarial review of the Stratified cost
variant found the probe applied NIFTY's DTE floor to BankNifty too — every
"BankNifty expiry-day" spread sample had actually been measured on the
WRONG contract (next month, ~30 DTE) instead of the current month's
contract the real backtest holds (DTE 0-1) near BankNifty's own expiry.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.probe_orb_scalping_real_spreads import DTE_FLOOR_DAYS, select_expiry  # noqa: E402


def test_select_expiry_applies_the_floor():
    today = date(2026, 8, 24)
    expiries = [date(2026, 8, 25), date(2026, 9, 1)]  # 1 DTE, 8 DTE
    assert select_expiry(expiries, today, dte_floor_days=2) == date(2026, 9, 1)


def test_select_expiry_with_zero_floor_takes_the_nearest_expiry_even_at_zero_dte():
    # This is the case that matters: BankNifty entered ON its own monthly
    # expiry day must select THAT contract (DTE=0), not roll to next month —
    # matching core/orb_scalping/backtest.py's resolve_banknifty_expiry(),
    # which has no floor at all.
    today = date(2026, 8, 25)
    expiries = [date(2026, 8, 25), date(2026, 9, 29)]
    assert select_expiry(expiries, today, dte_floor_days=0) == date(2026, 8, 25)


def test_select_expiry_returns_none_when_everything_is_too_close():
    today = date(2026, 8, 24)
    expiries = [date(2026, 8, 25)]  # 1 DTE, floor needs 2
    assert select_expiry(expiries, today, dte_floor_days=2) is None


def test_nifty_and_banknifty_select_different_contracts_near_banknifty_expiry():
    """The exact scenario that was broken: on the day before BankNifty's
    monthly expiry, with a shared floor both underlyings would have rolled
    past the near contract. NIFTY (its own weekly, unrelated to this date)
    is unaffected; BankNifty with floor=0 must select the imminent monthly,
    not skip it."""
    today = date(2026, 8, 24)
    banknifty_expiries = [date(2026, 8, 25), date(2026, 9, 29)]
    with_nifty_floor = select_expiry(banknifty_expiries, today, dte_floor_days=DTE_FLOOR_DAYS)
    with_no_floor = select_expiry(banknifty_expiries, today, dte_floor_days=0)
    assert with_nifty_floor == date(2026, 9, 29)   # the 2026-09-02 bug's behavior
    assert with_no_floor == date(2026, 8, 25)       # correct: matches the backtest
    assert with_nifty_floor != with_no_floor
