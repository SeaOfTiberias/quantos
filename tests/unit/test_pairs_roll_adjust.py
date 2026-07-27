"""
Pairs Trading v2 — Point-in-Time-Safe Futures-Roll Back-Adjustment

Covers core/pairs/roll_adjust.py per
docs/PAIRS_TRADING_V2_METHODOLOGY.md's Fix 2 construction: a roll seam's
adjustment must depend only on data known as of the roll (never a later
day), and must exactly cancel the pure contract-switch artifact while
leaving every non-roll day's return untouched.
"""

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.pairs.backtest import FuturesDay  # noqa: E402
from core.pairs.roll_adjust import build_adjusted_series  # noqa: E402

EXPIRY_1 = date(2026, 7, 28)
EXPIRY_2 = date(2026, 8, 25)


def _day(i: int, close: float, expiry: date, next_month_close=None) -> FuturesDay:
    return FuturesDay(date(2026, 7, 1) + timedelta(days=i), close, 1, expiry,
                       next_month_close=next_month_close)


def test_empty_input_returns_empty():
    series, n_unadjusted = build_adjusted_series([])
    assert series == []
    assert n_unadjusted == 0


def test_no_roll_adj_close_equals_raw_close():
    raw = [_day(0, 100.0, EXPIRY_1), _day(1, 102.0, EXPIRY_1), _day(2, 101.0, EXPIRY_1)]
    series, n_unadjusted = build_adjusted_series(raw)
    assert [d.adj_close for d in series] == pytest.approx([100.0, 102.0, 101.0])
    assert n_unadjusted == 0


def test_roll_day_return_uses_the_successor_contracts_real_return():
    # Day 0-1: old contract (EXPIRY_1) trades 100 -> 105, with next_month
    # (EXPIRY_2) priced 110 on day 1 (the last day both are observed).
    # Day 2: EXPIRY_2 becomes near-month, priced 112 (its own 110->112 move).
    raw = [
        _day(0, 100.0, EXPIRY_1),
        _day(1, 105.0, EXPIRY_1, next_month_close=110.0),
        _day(2, 112.0, EXPIRY_2),
    ]
    series, n_unadjusted = build_adjusted_series(raw)
    assert n_unadjusted == 0
    # Pre-roll days are untouched raw prices.
    assert series[0].adj_close == pytest.approx(100.0)
    assert series[1].adj_close == pytest.approx(105.0)
    # Post-roll: adj_close[2]/adj_close[1] must equal the REAL new-contract
    # return (112/110), not the raw seam jump (112/105).
    ratio = series[2].adj_close / series[1].adj_close
    assert math.isclose(ratio, 112.0 / 110.0, rel_tol=1e-9)


def test_two_consecutive_rolls_compound_correctly():
    EXPIRY_3 = date(2026, 9, 29)
    raw = [
        _day(0, 100.0, EXPIRY_1, next_month_close=110.0),   # roll 1 ratio measured here
        _day(1, 112.0, EXPIRY_2, next_month_close=120.0),   # roll 2 ratio measured here
        _day(2, 125.0, EXPIRY_3),
    ]
    series, n_unadjusted = build_adjusted_series(raw)
    assert n_unadjusted == 0
    r1 = series[1].adj_close / series[0].adj_close
    assert math.isclose(r1, 112.0 / 110.0, rel_tol=1e-9)
    r2 = series[2].adj_close / series[1].adj_close
    assert math.isclose(r2, 125.0 / 120.0, rel_tol=1e-9)


def test_missing_next_month_close_leaves_seam_unadjusted_and_is_counted():
    raw = [
        _day(0, 100.0, EXPIRY_1),   # no next_month_close available at the roll
        _day(1, 200.0, EXPIRY_2),   # a raw seam jump that can't be ratio-adjusted
    ]
    series, n_unadjusted = build_adjusted_series(raw)
    assert n_unadjusted == 1
    # Falls back to the original candidate-12 behavior for this one seam:
    # adj_close just carries the raw (unadjusted) price forward.
    assert series[1].adj_close == pytest.approx(200.0)


def test_adjustment_at_day_t_never_depends_on_a_later_roll():
    """Point-in-time safety: two series identical through day 5, differing
    only in what happens AFTER day 5 (a roll or not), must produce the
    IDENTICAL adj_close for every day up to and including day 5."""
    common_prefix = [_day(0, 100.0, EXPIRY_1), _day(1, 101.0, EXPIRY_1),
                      _day(2, 102.0, EXPIRY_1, next_month_close=108.0)]

    no_roll_yet = common_prefix + [_day(3, 103.0, EXPIRY_1)]
    rolls_later = common_prefix + [_day(3, 109.0, EXPIRY_2)]

    series_a, _ = build_adjusted_series(no_roll_yet)
    series_b, _ = build_adjusted_series(rolls_later)

    for i in range(3):  # days 0, 1, 2 -- before either series' divergence point
        assert series_a[i].adj_close == series_b[i].adj_close
