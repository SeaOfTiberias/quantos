"""
Candle-Confirm Momentum Gut-Check — Unit Tests

Covers the pure (I/O-free) signal-classification and forward-return logic
in scripts/gutcheck_candle_confirm_momentum.py per
docs/CANDLE_CONFIRM_MOMENTUM_GUTCHECK_METHODOLOGY.md.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from scripts.gutcheck_candle_confirm_momentum import (  # noqa: E402
    MIN_CANDLES_FOR_SIGNAL,
    classify_day,
    classify_day_unconditional,
    group_by_day,
)

BASE = datetime(2026, 1, 5, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def _candle(minute_offset: int, open_: float, close: float, high: float = None, low: float = None) -> OHLCV:
    ts = BASE + timedelta(minutes=minute_offset)
    hi = high if high is not None else max(open_, close)
    lo = low if low is not None else min(open_, close)
    return OHLCV(timestamp=ts, open=open_, high=hi, low=lo, close=close, volume=1000)


def _make_day(c1_dir: str, c2_dir: str, entry: float = 100.0, n: int = 20) -> list:
    """Build a day of n synthetic 1-minute candles. c1_dir/c2_dir in
    {"up", "down", "flat"} control candle1/candle2 shape; remaining
    candles drift flat at `entry` unless overridden by the caller."""
    def shaped(offset, o, direction):
        if direction == "up":
            return _candle(offset, o, o + 1)
        if direction == "down":
            return _candle(offset, o, o - 1)
        return _candle(offset, o, o)

    candles = [shaped(0, entry - 1, c1_dir)]
    c1_close = candles[0].close
    candles.append(shaped(1, c1_close, c2_dir))
    c2_close = candles[1].close
    price = c2_close
    for i in range(2, n):
        candles.append(_candle(i, price, price))
    return candles


# ─── classify_day: signal direction ──────────────────────────────────────────

def test_call_bias_when_both_candles_green():
    day = _make_day("up", "up")
    result = classify_day(day)
    assert result.direction == "CALL"
    assert result.skip_reason is None


def test_put_bias_when_both_candles_red():
    day = _make_day("down", "down")
    result = classify_day(day)
    assert result.direction == "PUT"
    assert result.skip_reason is None


def test_doji_candle1_skips_day():
    day = _make_day("flat", "up")
    result = classify_day(day)
    assert result.direction is None
    assert result.skip_reason == "doji_candle1"


def test_opposed_candle2_skips_call_bias():
    day = _make_day("up", "down")
    result = classify_day(day)
    assert result.direction is None
    assert result.skip_reason == "opposed_candle2"


def test_opposed_candle2_skips_put_bias():
    day = _make_day("down", "up")
    result = classify_day(day)
    assert result.direction is None
    assert result.skip_reason == "opposed_candle2"


def test_flat_candle2_does_not_oppose_call_bias():
    day = _make_day("up", "flat")
    result = classify_day(day)
    assert result.direction == "CALL"
    assert result.skip_reason is None


def test_flat_candle2_does_not_oppose_put_bias():
    day = _make_day("down", "flat")
    result = classify_day(day)
    assert result.direction == "PUT"
    assert result.skip_reason is None


def test_short_session_skipped():
    day = _make_day("up", "up", n=MIN_CANDLES_FOR_SIGNAL - 1)
    result = classify_day(day)
    assert result.direction is None
    assert result.skip_reason == "short_session"


def test_exactly_min_candles_not_skipped_for_length():
    day = _make_day("up", "up", n=MIN_CANDLES_FOR_SIGNAL)
    result = classify_day(day)
    assert result.skip_reason != "short_session"


# ─── classify_day: entry price + forward returns ─────────────────────────────

def test_entry_price_is_candle_index_2_open_no_lookahead():
    day = _make_day("up", "up", entry=100.0)
    result = classify_day(day)
    # candle index 2's open == candle index 1's close (the drift-flat tail
    # starts from c2_close per _make_day's construction).
    assert result.entry_price == day[2].open


def test_forward_return_positive_move_for_call_bias():
    day = _make_day("up", "up", entry=100.0)
    entry_price = day[2].open
    day[12] = _candle(12, entry_price, entry_price * 1.01)  # +1% at +10min
    result = classify_day(day)
    assert result.fwd_return_pct["10min"] > 0
    assert abs(result.fwd_return_pct["10min"] - 1.0) < 1e-6


def test_all_three_horizons_present_when_signaled():
    day = _make_day("up", "up")
    result = classify_day(day)
    assert set(result.fwd_return_pct.keys()) == {"5min", "10min", "15min"}


def test_no_forward_returns_when_no_signal():
    day = _make_day("flat", "up")
    result = classify_day(day)
    assert result.fwd_return_pct == {}


# ─── classify_day_unconditional ──────────────────────────────────────────────

def test_unconditional_ignores_signal_and_always_measures():
    day = _make_day("flat", "up")  # would be skipped by classify_day
    result = classify_day_unconditional(day)
    assert "10min" in result


def test_unconditional_short_session_returns_empty():
    day = _make_day("up", "up", n=MIN_CANDLES_FOR_SIGNAL - 1)
    result = classify_day_unconditional(day)
    assert result == {}


def test_unconditional_entry_matches_classify_day_when_signaled():
    day = _make_day("up", "up")
    signaled = classify_day(day)
    unconditional = classify_day_unconditional(day)
    assert unconditional["10min"] == signaled.fwd_return_pct["10min"]


# ─── group_by_day ─────────────────────────────────────────────────────────────

def test_group_by_day_splits_on_utc_calendar_date():
    day1 = _make_day("up", "up")
    day2_base = BASE + timedelta(days=1)
    day2 = [OHLCV(timestamp=day2_base + timedelta(minutes=i), open=1, high=1, low=1, close=1, volume=1)
            for i in range(MIN_CANDLES_FOR_SIGNAL)]
    grouped = group_by_day(day1 + day2)
    assert len(grouped) == 2


def test_group_by_day_sorts_within_day():
    day = _make_day("up", "up")
    shuffled = list(reversed(day))
    grouped = group_by_day(shuffled)
    (only_day,) = grouped.values()
    assert [c.timestamp for c in only_day] == [c.timestamp for c in day]
