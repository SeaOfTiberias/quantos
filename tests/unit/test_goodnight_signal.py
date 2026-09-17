"""Tests for core/goodnight_scalper/signal.py -- entry detection only."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from core.goodnight_scalper.signal import detect_entry  # noqa: E402


def _bar(start, i, o, h, l, c):
    return OHLCV(timestamp=start + timedelta(minutes=i), open=o, high=h, low=l, close=c, volume=1000)


START = datetime(2026, 9, 17, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def test_setup_a_open_equals_low_gives_call():
    candles = [
        _bar(START, 0, 100.0, 101.0, 100.0, 100.5),  # low == open -> Setup A
        _bar(START, 1, 100.6, 101.0, 100.4, 100.8),
    ]
    sig = detect_entry(candles)
    assert sig is not None
    assert sig.direction == "CALL"
    assert sig.setup == "A"
    assert sig.entry_index == 1
    assert sig.entry_price == 100.6
    assert sig.entry_timestamp == candles[1].timestamp


def test_setup_b_open_equals_high_gives_put():
    candles = [
        _bar(START, 0, 100.0, 100.0, 99.0, 99.5),  # high == open -> Setup B
        _bar(START, 1, 99.4, 99.8, 99.0, 99.2),
    ]
    sig = detect_entry(candles)
    assert sig is not None
    assert sig.direction == "PUT"
    assert sig.setup == "B"


def test_no_signal_when_neither_setup_fires():
    candles = [
        _bar(START, 0, 100.0, 100.5, 99.5, 100.2),  # open != low, open != high
        _bar(START, 1, 100.2, 100.6, 99.9, 100.3),
    ]
    assert detect_entry(candles) is None


def test_degenerate_zero_range_candle_is_ambiguous_no_trade():
    candles = [
        _bar(START, 0, 100.0, 100.0, 100.0, 100.0),  # open == high == low
        _bar(START, 1, 100.0, 100.1, 99.9, 100.0),
    ]
    assert detect_entry(candles) is None


def test_fewer_than_two_candles_gives_no_signal():
    candles = [_bar(START, 0, 100.0, 101.0, 100.0, 100.5)]  # only the opening candle, no execution candle
    assert detect_entry(candles) is None


def test_no_candles_gives_no_signal():
    assert detect_entry([]) is None
