"""Tests for core/orb_scalping/exit_policies.py (2026-09-30 exit study)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.exit_policies import ExitPolicy, simulate_day_with_policy  # noqa: E402
from core.orb_scalping.signal import simulate_day  # noqa: E402

START = datetime(2026, 9, 3, 3, 45, tzinfo=timezone.utc)


def bar(i, o, h, l, c):
    return OHLCV(timestamp=START + timedelta(minutes=5 * i), open=o, high=h, low=l, close=c, volume=1)


def day(path):
    """Opening range 23990-24010 (candles 0-2), breakout close 24020 on candle 3,
    entry at candle 4's open, then `path` closes (each bar +-2 around its close)."""
    cs = [bar(0, 24000, 24010, 23990, 24000), bar(1, 24000, 24001, 23999, 24000),
          bar(2, 24000, 24001, 23999, 24000), bar(3, 24000, 24021, 23999, 24020)]
    for i, c in enumerate(path, start=4):
        cs.append(bar(i, c, c + 2, c - 2, c))
    return cs


def test_v0_reproduces_simulate_day_on_varied_paths():
    for path in ([24020 + i for i in range(75)], [24020 - i for i in range(75)],
                 [24020 + (i % 9) * 5 for i in range(75)], [24020] * 75):
        d = day(path)
        assert simulate_day_with_policy(d, ExitPolicy()) == simulate_day(d)


def test_time_stop_exits_a_trade_that_never_arms():
    d = day([24022] * 75)                    # drifts nowhere, never arms (RW = 20)
    t = simulate_day_with_policy(d, ExitPolicy(time_stop_minutes=60))
    assert t.exit_reason == "time_stop"
    assert (t.exit_index - t.entry_index) * 5 == 60


def test_breakeven_moves_the_stop_to_entry():
    path = [24020, 24032, 24034, 24030] + [24010] * 70     # +12 (0.6 RW) then falls back
    t = simulate_day_with_policy(day(path), ExitPolicy(breakeven_at=0.5))
    assert t.exit_reason == "breakeven_stop" and t.exit_price == t.entry_price


def test_trail_from_entry_locks_in_part_of_a_move():
    path = [24020 + 10 * i for i in range(10)] + [24090 - 10 * i for i in range(65)]
    t = simulate_day_with_policy(day(path), ExitPolicy(trail_from_entry=1.0))
    assert t.exit_reason == "trailing_stop"
    assert t.exit_price > t.entry_price + 40              # kept most of a ~70-point run
