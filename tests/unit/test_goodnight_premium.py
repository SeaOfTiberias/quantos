"""Tests for core/goodnight_scalper/premium.py -- realized vol + premium walk."""

import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from core.goodnight_scalper.premium import (  # noqa: E402
    FLATTEN_TIME_UTC,
    STOP_PCT,
    TARGET_PCT,
    realized_volatility,
    reconstruct_trade,
)
from core.goodnight_scalper.signal import EntrySignal  # noqa: E402


def _bar(start, i, o, h, l, c):
    return OHLCV(timestamp=start + timedelta(minutes=i), open=o, high=h, low=l, close=c, volume=1000)


START = datetime(2026, 9, 17, 3, 46, tzinfo=timezone.utc)  # 09:16 IST, the execution candle


def _signal(direction="CALL", setup="A", entry_price=100.0):
    return EntrySignal(direction=direction, setup=setup, entry_index=0,
                        entry_timestamp=START, entry_price=entry_price)


# ─── realized_volatility ─────────────────────────────────────────────────

def test_realized_volatility_zero_for_constant_closes():
    closes = [100.0] * 21
    assert realized_volatility(closes) == pytest.approx(0.0, abs=1e-9)


def test_realized_volatility_positive_for_varying_closes():
    closes = [100.0, 102.0, 98.0, 103.0, 97.0, 101.0]
    vol = realized_volatility(closes)
    assert vol > 0


def test_realized_volatility_raises_on_too_few_closes():
    with pytest.raises(ValueError):
        realized_volatility([100.0])


def test_realized_volatility_raises_on_all_non_positive():
    with pytest.raises(ValueError):
        realized_volatility([0.0, -1.0])


# ─── reconstruct_trade ────────────────────────────────────────────────────

def test_exit_via_target():
    # Deep favorable spot move should push the CALL premium up 10%+ quickly.
    candles = [_bar(START, i, 100 + i * 2, 100 + i * 2 + 1, 100 + i * 2 - 1, 100 + i * 2)
               for i in range(10)]
    trade = reconstruct_trade("TESTSTOCK", _signal(entry_price=candles[0].open), candles,
                               strike_interval=50.0, expiry=date(2026, 9, 29), implied_vol=0.30)
    assert trade.exit_reason == "target"
    assert trade.exit_premium == pytest.approx(trade.entry_premium * (1 + TARGET_PCT), rel=1e-6)


def test_exit_via_stop():
    # Deep adverse spot move for a CALL should hit the -15% premium stop.
    candles = [_bar(START, i, 100 - i * 2, 100 - i * 2 + 1, 100 - i * 2 - 1, 100 - i * 2)
               for i in range(10)]
    trade = reconstruct_trade("TESTSTOCK", _signal(entry_price=candles[0].open), candles,
                               strike_interval=50.0, expiry=date(2026, 9, 29), implied_vol=0.30)
    assert trade.exit_reason == "stop"
    assert trade.exit_premium == pytest.approx(trade.entry_premium * (1 - STOP_PCT), rel=1e-6)


def test_exit_via_session_flatten_when_neither_target_nor_stop_hit():
    # Flat spot the whole way -- premium barely moves, runs to 09:30 IST flatten.
    candles = [_bar(START, i, 100.0, 100.1, 99.9, 100.0) for i in range(20)]  # 09:16..09:35 IST
    trade = reconstruct_trade("TESTSTOCK", _signal(entry_price=100.0), candles,
                               strike_interval=50.0, expiry=date(2026, 9, 29), implied_vol=0.20)
    assert trade.exit_reason == "session_flatten"
    assert trade.exit_timestamp.time() >= FLATTEN_TIME_UTC


def test_target_and_stop_levels_never_overlap():
    # target_level (entry * 1.10) must always sit strictly above stop_level
    # (entry * 0.85) for any positive premium -- confirms there is no
    # same-candle target-vs-stop ambiguity for reconstruct_trade to resolve
    # (see its docstring), rather than assuming it.
    for entry_premium in (1.0, 50.0, 999.5):
        target_level = entry_premium * (1 + TARGET_PCT)
        stop_level = entry_premium * (1 - STOP_PCT)
        assert target_level > stop_level


def test_put_exit_via_stop_on_adverse_upward_move():
    # PUT premium falls as spot rises -- a sharp upward move should hit
    # the -15% premium stop.
    candles = [_bar(START, i, 100 + i * 5, 100 + i * 5 + 1, 100 + i * 5 - 1, 100 + i * 5)
               for i in range(10)]
    trade = reconstruct_trade("TESTSTOCK", _signal(direction="PUT", setup="B", entry_price=candles[0].open),
                               candles, strike_interval=50.0, expiry=date(2026, 9, 29), implied_vol=0.30)
    assert trade.exit_reason == "stop"


def test_entry_premium_uses_black_scholes_with_given_iv():
    candles = [_bar(START, i, 100.0, 100.1, 99.9, 100.0) for i in range(2)]
    trade = reconstruct_trade("TESTSTOCK", _signal(entry_price=100.0), candles,
                               strike_interval=50.0, expiry=date(2026, 9, 29), implied_vol=0.20)
    assert trade.entry_premium > 0
    assert trade.strike == 100.0  # ATM at 50pt interval rounds 100.0 to itself


def test_exit_reason_never_missing_when_candles_run_out_before_flatten():
    # Only 2 candles provided, well before 09:30 IST -- no exit condition
    # fires within the data, so the fallback path (last available reading)
    # must still return a real StockPremiumTrade, not raise.
    candles = [_bar(START, i, 100.0, 100.1, 99.9, 100.0) for i in range(2)]
    trade = reconstruct_trade("TESTSTOCK", _signal(entry_price=100.0), candles,
                               strike_interval=50.0, expiry=date(2026, 9, 29), implied_vol=0.20)
    assert trade.exit_reason == "session_flatten"
    assert trade.exit_timestamp == candles[-1].timestamp
