"""
10:10 Breakout — Signal Unit Tests

Covers the pure (I/O-free) reference-candle breakout detection and
single-day index-level trade simulation in core/breakout1010/signal.py
per docs/BREAKOUT_1010_METHODOLOGY.md.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.breakout1010.signal import (  # noqa: E402
    MAX_STOP_POINTS,
    REFERENCE_CANDLE_INDEX,
    TARGET_POINTS,
    simulate_day,
)

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(i: int, o: float, h: float, l: float, c: float, v: int = 1000) -> OHLCV:
    return OHLCV(timestamp=SESSION_START + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=v)


def flat_bars(n: int, price: float = 50000.0) -> list:
    return [bar(i, price, price + 1, price - 1, price) for i in range(n)]


def with_reference(candles: list, ref_high: float, ref_low: float) -> list:
    """Overwrites the reference candle (index REFERENCE_CANDLE_INDEX) with
    an explicit (high, low) range, leaving open/close as flat-bar defaults."""
    i = REFERENCE_CANDLE_INDEX
    o, c = candles[i].open, candles[i].close
    candles[i] = bar(i, o, ref_high, ref_low, c)
    return candles


# ─── No signal cases ─────────────────────────────────────────────────────

def test_too_few_candles_returns_none():
    candles = flat_bars(REFERENCE_CANDLE_INDEX)  # one short of having a reference candle
    assert simulate_day(candles) is None


def test_no_breakout_returns_none():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50010.0, ref_low=49990.0)
    # every other candle stays within [49990, 50010] -- never closes outside
    assert simulate_day(candles) is None


# ─── Entry direction and no-same-bar execution ──────────────────────────

def test_call_signal_on_close_above_reference_high():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50010.0, ref_low=49990.0)
    breakout_i = REFERENCE_CANDLE_INDEX + 2
    candles[breakout_i] = bar(breakout_i, 50000, 50025, 49995, 50020)  # closes above ref high
    trade = simulate_day(candles)
    assert trade is not None
    assert trade.direction == "CALL"
    # execution is the OPEN of the next candle, not the signal candle's own price
    assert trade.entry_index == breakout_i + 1
    assert trade.entry_price == candles[breakout_i + 1].open


def test_put_signal_on_close_below_reference_low():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50010.0, ref_low=49990.0)
    breakout_i = REFERENCE_CANDLE_INDEX + 2
    candles[breakout_i] = bar(breakout_i, 50000, 50005, 49975, 49980)  # closes below ref low
    trade = simulate_day(candles)
    assert trade is not None
    assert trade.direction == "PUT"
    assert trade.entry_index == breakout_i + 1


def test_first_breakout_only_ignores_a_later_opposite_breakout():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50010.0, ref_low=49990.0)
    up_i = REFERENCE_CANDLE_INDEX + 2
    candles[up_i] = bar(up_i, 50000, 50025, 49995, 50020)  # CALL breakout first
    down_i = up_i + 5
    candles[down_i] = bar(down_i, 49000, 49005, 48000, 48500)  # a later, huge down move
    trade = simulate_day(candles)
    assert trade.direction == "CALL"  # the later down-move is irrelevant -- one trade/day


# ─── Stop / target mechanics, index points ──────────────────────────────

def test_call_stop_capped_at_40_points_even_with_a_wider_reference_candle():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50100.0, ref_low=49850.0)  # 250pt range >> cap
    breakout_i = REFERENCE_CANDLE_INDEX + 2
    candles[breakout_i] = bar(breakout_i, 50000, 50120, 49995, 50110)
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    # next candle drives price down through a 40pt stop but not through
    # what an un-capped (250pt) stop would have required
    candles[entry_i + 1] = bar(entry_i + 1, entry_price, entry_price + 1,
                                entry_price - 45, entry_price - 20)
    trade = simulate_day(candles)
    assert trade.exit_reason == "stop"
    assert trade.exit_price == entry_price - MAX_STOP_POINTS


def test_put_target_is_200_points_below_entry():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50010.0, ref_low=49990.0)
    breakout_i = REFERENCE_CANDLE_INDEX + 2
    candles[breakout_i] = bar(breakout_i, 50000, 50005, 49975, 49980)
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    target_level = entry_price - TARGET_POINTS
    candles[entry_i + 1] = bar(entry_i + 1, entry_price, entry_price + 1,
                                target_level - 5, target_level - 2)
    trade = simulate_day(candles)
    assert trade.exit_reason == "target"
    assert trade.exit_price == target_level


def test_same_candle_stop_and_target_resolves_to_stop():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50100.0, ref_low=49850.0)  # 250pt range >> cap
    breakout_i = REFERENCE_CANDLE_INDEX + 2
    candles[breakout_i] = bar(breakout_i, 50000, 50120, 49995, 50110)  # CALL
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    stop_level = entry_price - MAX_STOP_POINTS
    target_level = entry_price + TARGET_POINTS
    # one huge-range candle spans BOTH the stop and the target
    candles[entry_i + 1] = bar(entry_i + 1, entry_price, target_level + 10,
                                stop_level - 10, entry_price)
    trade = simulate_day(candles)
    assert trade.exit_reason == "stop"
    assert trade.exit_price == stop_level


def test_session_flatten_when_neither_stop_nor_target_hit():
    candles = flat_bars(80, price=50000.0)
    candles = with_reference(candles, ref_high=50010.0, ref_low=49990.0)
    breakout_i = REFERENCE_CANDLE_INDEX + 2
    candles[breakout_i] = bar(breakout_i, 50000, 50025, 49995, 50020)  # CALL
    # every candle after entry drifts sideways, never touching stop/target,
    # until one lands exactly at/after 15:20 IST (09:50 UTC)
    entry_i = breakout_i + 1
    flatten_index = None
    for i in range(entry_i + 1, len(candles)):
        if candles[i].timestamp.time() >= __import__("datetime").time(9, 50):
            flatten_index = i
            break
    assert flatten_index is not None, "test fixture must run long enough to reach flatten time"
    trade = simulate_day(candles)
    assert trade.exit_reason == "session_flatten"
    assert trade.exit_index == flatten_index
