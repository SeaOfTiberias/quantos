"""
Tests for core/orb_scalping/entry_filter.py --
docs/ORB_ENTRY_FILTER_METHODOLOGY.md's two mined-and-replicated
predicates. Pure functions, no I/O.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.entry_filter import (  # noqa: E402
    BIG_GAP_THRESHOLD_PCT,
    banknifty_entry_allowed,
    nifty_entry_allowed,
)


# ─── nifty_entry_allowed: Monday or Friday only ────────────────────────────

def test_monday_and_friday_are_allowed():
    assert nifty_entry_allowed(date(2026, 9, 21)) is True   # a Monday
    assert nifty_entry_allowed(date(2026, 9, 25)) is True   # a Friday


def test_tuesday_through_thursday_are_not_allowed():
    assert nifty_entry_allowed(date(2026, 9, 22)) is False  # Tuesday
    assert nifty_entry_allowed(date(2026, 9, 23)) is False  # Wednesday
    assert nifty_entry_allowed(date(2026, 9, 24)) is False  # Thursday


def test_weekend_is_not_allowed():
    """Never a real trading day, but the predicate itself should be honest
    about it rather than silently matching Monday/Friday's neighbors."""
    assert nifty_entry_allowed(date(2026, 9, 26)) is False  # Saturday
    assert nifty_entry_allowed(date(2026, 9, 27)) is False  # Sunday


# ─── banknifty_entry_allowed: |gap%| > 0.3 ──────────────────────────────────

def test_big_gap_up_is_allowed():
    # +0.5% gap
    assert banknifty_entry_allowed(today_first_candle_open=50250.0, prior_daily_close=50000.0) is True


def test_big_gap_down_is_allowed_symmetrically():
    # -0.5% gap
    assert banknifty_entry_allowed(today_first_candle_open=49750.0, prior_daily_close=50000.0) is True


def test_small_gap_is_not_allowed():
    # +0.1% gap, under the threshold
    assert banknifty_entry_allowed(today_first_candle_open=50050.0, prior_daily_close=50000.0) is False


def test_gap_exactly_at_threshold_is_not_allowed():
    """Strict '>', matching condition-mining's own predicate exactly --
    an exact-threshold day is not a big-gap day."""
    prior_close = 50000.0
    open_at_exactly_threshold = prior_close * (1 + BIG_GAP_THRESHOLD_PCT / 100.0)
    assert banknifty_entry_allowed(open_at_exactly_threshold, prior_close) is False


def test_no_prior_close_is_not_allowed():
    """No prior close means the gap can't be computed -- excluded, not
    guessed, same convention as an unclassified condition anywhere else in
    this project."""
    assert banknifty_entry_allowed(today_first_candle_open=50000.0, prior_daily_close=None) is False


def test_no_prior_close_does_not_raise():
    banknifty_entry_allowed(today_first_candle_open=50000.0, prior_daily_close=0.0)
