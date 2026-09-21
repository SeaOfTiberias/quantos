"""
Tests for scripts/analyze_orb_arm_giveback.py's pure logic: bucket
classification, the signed final-move convention, and the day-list
aggregation. No network, no broker -- synthetic candles only, same
fixtures shape as tests/unit/test_orb_scalping_signal.py.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.signal import IndexTrade, OPENING_RANGE_CANDLES  # noqa: E402
from scripts.analyze_orb_arm_giveback import (  # noqa: E402
    ARMED,
    NEVER_ARMED_FLATTEN,
    NEVER_ARMED_STOPPED,
    _classify,
    _final_move,
    collect_trades,
)

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(i, o, h, l, c, v=1000):
    return OHLCV(timestamp=SESSION_START + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=v)


def flat_bars(n, price=24000.0):
    return [bar(i, price, price + 1, price - 1, price) for i in range(n)]


def with_opening_range(candles, range_high, range_low):
    mid = (range_high + range_low) / 2
    candles[0] = bar(0, mid, range_high, range_low, mid)
    for i in range(1, OPENING_RANGE_CANDLES):
        candles[i] = bar(i, mid, mid + 1, mid - 1, mid)
    return candles


def trade(direction="CALL", entry_price=24020.0, exit_price=24020.0, exit_reason="session_flatten",
         armed=False, mfe=0.0):
    return IndexTrade(direction=direction, entry_index=5, entry_price=entry_price,
                      exit_index=20, exit_price=exit_price, initial_stop=23990.0,
                      exit_reason=exit_reason, armed=armed, max_favorable_points=mfe)


# ─── _classify ──────────────────────────────────────────────────────────────

def test_never_armed_flatten_is_its_own_bucket():
    assert _classify(trade(armed=False, exit_reason="session_flatten")) == NEVER_ARMED_FLATTEN


def test_never_armed_stopped_is_a_different_bucket():
    assert _classify(trade(armed=False, exit_reason="stop")) == NEVER_ARMED_STOPPED


def test_armed_is_its_own_bucket_regardless_of_exit_reason():
    assert _classify(trade(armed=True, exit_reason="trailing_stop")) == ARMED
    assert _classify(trade(armed=True, exit_reason="session_flatten")) == ARMED


# ─── _final_move sign convention ───────────────────────────────────────────

def test_final_move_is_positive_for_a_call_that_closed_above_entry():
    t = trade(direction="CALL", entry_price=100.0, exit_price=110.0)
    assert _final_move(t) == 10.0


def test_final_move_is_positive_for_a_put_that_closed_below_entry():
    t = trade(direction="PUT", entry_price=100.0, exit_price=90.0)
    assert _final_move(t) == 10.0


def test_final_move_is_negative_when_the_trade_lost():
    t = trade(direction="CALL", entry_price=100.0, exit_price=95.0)
    assert _final_move(t) == -5.0


# ─── collect_trades: end-to-end over synthetic days ────────────────────────

def test_collect_trades_flags_a_rally_that_never_arms_and_gives_it_back():
    """The exact 2026-09-21 BankNifty shape: rallies short of 1 range-width,
    fully round-trips back to entry by the close."""
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)  # 20pt range
    breakout_i = OPENING_RANGE_CANDLES + 2
    candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)  # CALL
    entry_i = breakout_i + 1
    entry_price = candles[entry_i].open
    peak_i = entry_i + 1
    candles[peak_i] = bar(peak_i, entry_price, entry_price + 12, entry_price - 1, entry_price + 10)
    for i in range(peak_i + 1, len(candles)):
        candles[i] = bar(i, entry_price, entry_price + 1, entry_price - 1, entry_price)

    rows = collect_trades({"2026-09-21": candles})
    assert len(rows) == 1
    row = rows[0]
    assert row.bucket == NEVER_ARMED_FLATTEN
    assert row.mfe_points == 12.0
    assert row.final_move_points == 0.0    # closed flat vs entry
    assert row.given_back_points == 12.0   # gave back the entire 12pt peak


def test_collect_trades_skips_days_with_no_breakout():
    candles = flat_bars(80, price=24000.0)
    candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
    rows = collect_trades({"no-breakout-day": candles})
    assert rows == []


def test_collect_trades_reports_multiple_days_independently():
    def make_day(gain):
        candles = flat_bars(80, price=24000.0)
        candles = with_opening_range(candles, range_high=24010.0, range_low=23990.0)
        breakout_i = OPENING_RANGE_CANDLES + 2
        candles[breakout_i] = bar(breakout_i, 24000, 24025, 23995, 24020)
        entry_i = breakout_i + 1
        entry_price = candles[entry_i].open
        peak_i = entry_i + 1
        candles[peak_i] = bar(peak_i, entry_price, entry_price + gain, entry_price - 1, entry_price + gain - 2)
        for i in range(peak_i + 1, len(candles)):
            candles[i] = bar(i, entry_price, entry_price + 1, entry_price - 1, entry_price)
        return candles

    rows = collect_trades({"day1": make_day(5), "day2": make_day(8)})
    assert len(rows) == 2
    assert {r.mfe_points for r in rows} == {5.0, 8.0}
