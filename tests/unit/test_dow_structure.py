"""
Dow Theory / Market Structure Trend Following — Unit Tests

Covers the pure (I/O-free) fractal detection and single-day trade
simulation in core/trend/dow_structure.py per
docs/DOW_THEORY_TREND_METHODOLOGY.md.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.trend.dow_structure import (  # noqa: E402
    SESSION_FLATTEN_UTC,
    _active_swing,
    find_confirmed_swings,
    simulate_day,
)

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(i: int, o: float, h: float, l: float, c: float, v: int = 1000) -> OHLCV:
    return OHLCV(timestamp=SESSION_START + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=v)


def flat_bars(n: int, price: float = 100.0) -> list:
    return [bar(i, price, price + 0.1, price - 0.1, price) for i in range(n)]


# ─── find_confirmed_swings ────────────────────────────────────────────────

def test_finds_simple_swing_high():
    candles = flat_bars(7)
    candles[3] = bar(3, 100, 110, 99.5, 105)  # a clean spike at index 3
    swings = find_confirmed_swings(candles, k=2)
    highs = [s for s in swings if s.kind == "high"]
    assert len(highs) == 1
    assert highs[0].index == 3
    assert highs[0].price == 110


def test_finds_simple_swing_low():
    candles = flat_bars(7)
    candles[3] = bar(3, 100, 100.5, 90, 95)
    swings = find_confirmed_swings(candles, k=2)
    lows = [s for s in swings if s.kind == "low"]
    assert len(lows) == 1
    assert lows[0].index == 3
    assert lows[0].price == 90


def test_tie_is_not_a_confirmed_swing():
    candles = flat_bars(7)
    candles[2] = bar(2, 100, 110, 99, 100)
    candles[4] = bar(4, 100, 110, 99, 100)  # same high, ties out index 2/4's uniqueness
    swings = find_confirmed_swings(candles, k=2)
    assert not any(s.kind == "high" and s.index in (2, 3, 4) for s in swings)


def test_no_swings_possible_with_too_few_bars():
    candles = flat_bars(3)
    assert find_confirmed_swings(candles, k=2) == []


# ─── _active_swing lag ────────────────────────────────────────────────────

def test_swing_not_active_before_confirmation_lag():
    candles = flat_bars(7)
    candles[2] = bar(2, 100, 110, 99, 100)  # confirms at index 4 (2+k)
    swings = find_confirmed_swings(candles, k=2)
    assert _active_swing(swings, 3, "high", 2) is None   # not yet confirmed
    assert _active_swing(swings, 4, "high", 2) is not None  # confirmed exactly at 2+k


# ─── simulate_day: entry mechanics ────────────────────────────────────────

SWING_LOW = 90.0
SWING_HIGH = 110.0


def _day_with_swing_and_breakout(breakout_close: float, k: int = 2) -> list:
    """Bar 2: a spike forming a unique swing high=110 (confirms at bar 4).
    Bar 3: a dip forming a unique swing low=90 (confirms at bar 5, exactly
    when the breakout bar itself lands -- both references are active by
    the time bar 5's close is evaluated). Entry executes at bar 6's open."""
    candles = flat_bars(10, price=100.0)
    candles[2] = bar(2, 100, SWING_HIGH, 99.9, 100)   # unique high, tied low -> swing HIGH only
    candles[3] = bar(3, 100, 100.1, SWING_LOW, 100)   # tied high, unique low -> swing LOW only
    candles[5] = bar(5, 100, 100.2, 99.8, breakout_close)
    candles[6] = bar(6, 105, 105.5, 104.5, 105)
    for i in range(7, 10):
        candles[i] = bar(i, 105, 105.2, 104.8, 105)
    return candles


def test_breakout_above_swing_high_triggers_long_next_bar_open():
    candles = _day_with_swing_and_breakout(breakout_close=111)  # breaks the 110 high
    trades = simulate_day(candles, k=2)
    assert len(trades) >= 1
    first = trades[0]
    assert first.direction == "LONG"
    assert first.entry_index == 6
    assert first.entry_price == candles[6].open


def test_no_entry_signal_possible_before_any_confirmed_swing():
    # Breakout attempted at bar 1, long before bar 2's spike even exists.
    candles = flat_bars(10, price=100.0)
    candles[1] = bar(1, 100, 200, 99, 150)  # a huge move with no swing history yet
    trades = simulate_day(candles, k=2)
    assert trades == []


# ─── simulate_day: exit mechanics ─────────────────────────────────────────

def test_stop_loss_exit():
    candles = _day_with_swing_and_breakout(breakout_close=111)
    candles[7] = bar(7, 105, 105.2, 70, 75)  # crashes through the SWING_LOW (90) stop
    trades = simulate_day(candles, k=2)
    stop_trades = [t for t in trades if t.exit_reason == "stop"]
    assert len(stop_trades) == 1
    assert stop_trades[0].quantity_fraction == 1.0


def test_scale_out_at_1r_then_breakeven_stop():
    candles = _day_with_swing_and_breakout(breakout_close=111)
    entry_price = candles[6].open  # 105
    initial_stop = SWING_LOW
    risk = entry_price - initial_stop
    target = entry_price + risk
    candles[7] = bar(7, 105, target + 1, 104.5, target + 0.5)  # reaches 1R target
    candles[8] = bar(8, target, target, initial_stop - 1, initial_stop - 1)  # falls all the way through old stop
    trades = simulate_day(candles, k=2)
    scale_out = [t for t in trades if t.exit_reason == "scale_out_1R"]
    assert len(scale_out) == 1
    assert scale_out[0].quantity_fraction == 0.5
    # remaining runner's stop should have moved to breakeven (entry_price),
    # so falling through the OLD stop (SWING_LOW) but stopping at breakeven
    # means the final exit price should be entry_price, not the old stop.
    remainder = [t for t in trades if t.quantity_fraction == 0.5 and t.exit_reason != "scale_out_1R"]
    assert len(remainder) == 1
    assert remainder[0].exit_price == entry_price


def test_session_flatten_closes_open_position():
    candles = _day_with_swing_and_breakout(breakout_close=111)
    # Push remaining bars past the flatten time with nothing else happening.
    flatten_dt = SESSION_START.replace(hour=9, minute=55)  # after 09:50 UTC cutoff
    for i in range(7, 10):
        candles[i] = OHLCV(timestamp=flatten_dt + timedelta(minutes=5 * (i - 7)),
                            open=105, high=105.2, low=104.8, close=105, volume=1000)
    trades = simulate_day(candles, k=2)
    flatten_trades = [t for t in trades if t.exit_reason == "session_flatten"]
    assert len(flatten_trades) == 1
    assert flatten_trades[0].quantity_fraction == 1.0


def test_same_bar_stop_and_target_resolves_to_stop():
    candles = _day_with_swing_and_breakout(breakout_close=111)
    entry_price = candles[6].open
    initial_stop = SWING_LOW
    risk = entry_price - initial_stop
    target = entry_price + risk
    # One bar whose range spans BOTH the target and the stop.
    candles[7] = bar(7, entry_price, target + 5, initial_stop - 5, entry_price)
    trades = simulate_day(candles, k=2)
    assert trades[0].exit_reason == "stop"
    assert trades[0].quantity_fraction == 1.0


def test_gap_through_stop_at_entry_skips_trade():
    candles = flat_bars(10, price=100.0)
    candles[2] = bar(2, 100, 110, 50, 100)  # swing high=110, swing low=50 (wide)
    candles[5] = bar(5, 100, 100.2, 99.8, 111)  # breakout close
    # Next bar opens AT/BELOW the swing-low stop (50) -- risk would be <= 0
    # -- then settles back between the two swing levels (50, 110) so no
    # secondary signal confounds the assertion.
    candles[6] = bar(6, 45, 46, 44, 70)
    for i in range(7, 10):
        candles[i] = bar(i, 70, 70.2, 69.8, 70)
    trades = simulate_day(candles, k=2)
    assert trades == []
