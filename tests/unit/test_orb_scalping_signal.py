"""
ORB Options Scalping — Signal Unit Tests

Covers the pure (I/O-free) opening-range breakout detection and
single-day index-level trade simulation in core/orb_scalping/signal.py
per docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md.
"""

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.signal import (  # noqa: E402
    OPENING_RANGE_CANDLES,
    simulate_day,
)

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(i: int, o: float, h: float, l: float, c: float, v: int = 1000) -> OHLCV:
    return OHLCV(timestamp=SESSION_START + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=v)


def flat_bars(n: int, price: float = 24000.0) -> list:
    return [bar(i, price, price + 1, price - 1, price) for i in range(n)]


def with_opening_range(candles: list, range_high: float, range_low: float) -> list:
    """Overwrites the first OPENING_RANGE_CANDLES candles so their combined
    high/low equal the given range, leaving the rest of each bar's shape
    (open/close) at the flat-bar defaults."""
    mid = (range_high + range_low) / 2
    candles[0] = bar(0, mid, range_high, range_low, mid)
    for i in range(1, OPENING_RANGE_CANDLES):
        candles[i] = bar(i, mid, mid + 1, mid - 1, mid)
    return candles


# ─── No signal cases ─────────────────────────────────────────────────────

def test_too_few_candles_returns_none():
    candles = flat_bars(OPENING_RANGE_CANDLES)  # no candles left to evaluate a breakout
    assert simulate_day(candles) is None


def test_no_breakout_returns_none():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    assert simulate_day(candles) is None


# ─── Entry direction and no-same-bar execution ──────────────────────────

def test_call_signal_on_close_above_range_high():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # closes above range high
    trade = simulate_day(candles)
    assert trade is not None
    assert trade.direction == "CALL"
    assert trade.entry_index == breakout_i + 1
    assert trade.entry_price == candles[breakout_i + 1].open
    assert trade.initial_stop == 23990.0  # opposite side of the opening range


def test_put_signal_on_close_below_range_low():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24005, 23975, 23980)  # closes below range low
    trade = simulate_day(candles)
    assert trade is not None
    assert trade.direction == "PUT"
    assert trade.entry_index == breakout_i + 1
    assert trade.initial_stop == 24010.0


def test_first_breakout_only_ignores_a_later_opposite_breakout():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    up_i = OPENING_RANGE_CANDLES + 2
    candles[up_i] = bar(up_i, 24000, 24025, 23995, 24020)  # CALL breakout first
    down_i = up_i + 5
    candles[down_i] = bar(down_i, 23000, 23005, 22000, 22500)  # a later, huge down move
    trade = simulate_day(candles)
    assert trade.direction == "CALL"  # the later down-move is irrelevant -- one trade/day


# ─── Initial stop (opposite side of the opening range) ──────────────────

def test_call_initial_stop_hit_before_trailing_arms():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    # next candle drives price straight down through the initial stop
    # (range_low = 23990), well before 1 range-width (20pt) of profit
    candles[entry_i + 1] = bar(entry_i + 1, entry_price, entry_price + 1, 23985, 23988)
    trade = simulate_day(candles)
    assert trade.exit_reason == "stop"
    assert trade.exit_price == 23990.0


def test_same_candle_stop_and_arm_trigger_resolves_to_stop():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)  # 20pt range
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # CALL
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    # one huge-range candle spans BOTH the initial stop and the 1R arm level
    candles[entry_i + 1] = bar(entry_i + 1, entry_price, entry_price + 100, 23985, entry_price)
    trade = simulate_day(candles)
    assert trade.exit_reason == "stop"
    assert trade.exit_price == 23990.0


# ─── Trailing stop mechanics ─────────────────────────────────────────────

def test_trailing_stop_arms_and_ratchets_up_on_a_call():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)  # 20pt range width
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # CALL
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open  # 24020

    # Candle A: closes at entry_price + 20 (= 1 range-width) -> arms trailing.
    a = entry_i + 1
    candles[a] = bar(a, entry_price, entry_price + 22, entry_price + 5, entry_price + 20)
    # Candle B: continues higher; its low (entry_price+15) becomes part of
    # the 3-candle trailing lookback once armed.
    b = a + 1
    candles[b] = bar(b, entry_price + 20, entry_price + 30, entry_price + 15, entry_price + 28)
    # Candle C: pulls back and hits the trailing stop (should now be the
    # min low of the last 3 candles: min(23995 [pre-arm candle not counted,
    # since lookback only spans post-entry candles], entry_price+5, entry_price+15)).
    c = b + 1
    trail_hit_level = entry_price + 5   # candle A's low, the tightest of the post-arm lookback
    candles[c] = bar(c, entry_price + 28, entry_price + 29, trail_hit_level - 1, trail_hit_level - 0.5)

    trade = simulate_day(candles)
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == trail_hit_level


def test_trailing_stop_exit_uses_the_persisted_ratcheted_level():
    # Once armed, the stop is a running max() over every prior window
    # recompute (signal.py's `stop = max(stop, ...)` for a CALL) -- it can
    # only tighten, never loosen. A candle whose low crashes straight
    # through that persisted level must exit AT that level, not at some
    # value freshly derived from the crashing candle itself (e.g. its own
    # low, or an average) -- that would indicate the ratchet isn't being
    # carried forward correctly.
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # CALL
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open

    a = entry_i + 1
    candles[a] = bar(a, entry_price, entry_price + 25, entry_price + 22, entry_price + 24)  # arms, ratchets stop to entry_price+22
    b = a + 1
    # Crashes straight through the ratcheted stop -- must exit exactly at
    # entry_price+22 (the persisted level), not at this candle's own much
    # lower low (entry_price-50).
    candles[b] = bar(b, entry_price + 24, entry_price + 26, entry_price - 50, entry_price + 25)

    trade = simulate_day(candles)
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == entry_price + 22


# ─── Session flatten ──────────────────────────────────────────────────────

def test_session_flatten_when_nothing_else_triggers():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # CALL
    entry_i = breakout_i + 1
    flatten_index = None
    for i in range(entry_i + 1, len(candles)):
        if candles[i].timestamp.time() >= time(9, 50):
            flatten_index = i
            break
    assert flatten_index is not None, "test fixture must run long enough to reach flatten time"
    trade = simulate_day(candles)
    assert trade.exit_reason == "session_flatten"
    assert trade.exit_index == flatten_index
