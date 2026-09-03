"""
ORB Options Scalping — Live State Unit Tests

Covers core/orb_scalping/live_state.py's partial-day state machine, plus
a differential check against core/orb_scalping/signal.py's simulate_day():
replaying a full day incrementally through compute_live_state() must land
on the same entry/direction/stop as feeding the whole day at once to
simulate_day() -- the guarantee that the live-shaped sibling didn't drift
from the tested backtest logic it mirrors.
"""

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.live_state import compute_live_state  # noqa: E402
from core.orb_scalping.signal import OPENING_RANGE_CANDLES, simulate_day  # noqa: E402

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(i: int, o: float, h: float, l: float, c: float, v: int = 1000) -> OHLCV:
    return OHLCV(timestamp=SESSION_START + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=v)


def flat_bars(n: int, price: float = 24000.0) -> list:
    return [bar(i, price, price + 1, price - 1, price) for i in range(n)]


def with_opening_range(candles: list, range_high: float, range_low: float) -> list:
    mid = (range_high + range_low) / 2
    candles[0] = bar(0, mid, range_high, range_low, mid)
    for i in range(1, OPENING_RANGE_CANDLES):
        candles[i] = bar(i, mid, mid + 1, mid - 1, mid)
    return candles


# ─── Partial-day status progression ──────────────────────────────────────

def test_forming_range_before_opening_range_closes():
    candles = flat_bars(OPENING_RANGE_CANDLES)
    assert compute_live_state(candles).status == "forming_range"


def test_no_breakout_yet_once_range_known():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    state = compute_live_state(candles[:OPENING_RANGE_CANDLES + 2])
    assert state.status == "no_breakout_yet"
    assert state.range_high == 24010.0
    assert state.range_low == 23990.0


def test_pending_entry_right_after_breakout_close():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # closes above range
    state = compute_live_state(candles[:breakout_i + 1])
    assert state.status == "pending_entry"
    assert state.direction == "CALL"


def test_in_position_with_no_stop_hit_yet():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)
    entry_i = breakout_i + 1
    # entry candle only, plus one more flat candle sitting well above the stop
    state = compute_live_state(candles[:entry_i + 2])
    assert state.status == "in_position"
    assert state.direction == "CALL"
    assert state.entry_price == candles[entry_i].open
    assert state.current_stop == 23990.0  # initial stop, not yet armed
    assert state.armed is False


def test_current_stop_ratchets_up_once_armed_mid_day():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)  # 20pt range
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    a = entry_i + 1
    candles[a] = bar(a, entry_price, entry_price + 25, entry_price + 22, entry_price + 24)  # arms
    state = compute_live_state(candles[:a + 1])
    assert state.status == "in_position"
    assert state.armed is True
    assert state.current_stop == entry_price + 22


def test_flattened_when_a_closed_candle_already_crossed_the_stop():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    candles[entry_i + 1] = bar(entry_i + 1, entry_price, entry_price + 1, 23985, 23988)  # crashes through initial stop
    state = compute_live_state(candles[:entry_i + 2])
    assert state.status == "flattened"
    assert state.current_stop == 23990.0
    assert state.exit_reason == "stop"  # not yet armed -- initial stop, not the trailing one


def test_flattened_at_session_flatten_time_with_no_stop_hit():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)
    flatten_index = next(i for i, c in enumerate(candles) if c.timestamp.time() >= time(9, 50))
    state = compute_live_state(candles[:flatten_index + 1])
    assert state.status == "flattened"
    assert state.exit_reason == "session_flatten"  # NOT a stop-out -- callers must not log this as one


# ─── Differential check against simulate_day() ───────────────────────────

def _incremental_final_state(candles: list):
    """Replay the whole day one closed candle at a time -- the shape a
    real 1-minute poll would see across the session -- and return
    whatever compute_live_state() reports once every candle has been fed."""
    state = None
    for n in range(OPENING_RANGE_CANDLES + 1, len(candles) + 1):
        state = compute_live_state(candles[:n])
    return state


def test_incremental_replay_agrees_with_simulate_day_on_trailing_stop_exit():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # CALL
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    a = entry_i + 1
    candles[a] = bar(a, entry_price, entry_price + 22, entry_price + 5, entry_price + 20)  # arms
    b = a + 1
    candles[b] = bar(b, entry_price + 20, entry_price + 30, entry_price + 15, entry_price + 28)
    c = b + 1
    trail_hit_level = entry_price + 5
    candles[c] = bar(c, entry_price + 28, entry_price + 29, trail_hit_level - 1, trail_hit_level - 0.5)

    trade = simulate_day(candles)
    assert trade.exit_reason == "trailing_stop"

    final_state = _incremental_final_state(candles[:c + 1])
    assert final_state.status == "flattened"
    assert final_state.exit_reason == trade.exit_reason
    assert final_state.direction == trade.direction
    assert final_state.entry_price == trade.entry_price
    assert final_state.current_stop == trade.exit_price


def test_incremental_replay_agrees_with_simulate_day_on_session_flatten():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # CALL, then drifts flat -> flatten

    trade = simulate_day(candles)
    assert trade.exit_reason == "session_flatten"

    final_state = _incremental_final_state(candles)
    assert final_state.status == "flattened"
    assert final_state.exit_reason == "session_flatten"
    assert final_state.direction == trade.direction
    assert final_state.entry_price == trade.entry_price


def test_incremental_replay_agrees_with_simulate_day_on_no_trade_day():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)  # never breaks out

    assert simulate_day(candles) is None
    final_state = _incremental_final_state(candles)
    assert final_state.status == "no_breakout_yet"
