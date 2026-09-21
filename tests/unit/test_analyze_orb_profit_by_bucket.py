"""
Tests for scripts/analyze_orb_profit_by_bucket.py -- joins the arm-bucket
classification to real Stratified-cost net profit. No network/broker;
synthetic multi-day candles, same fixture shape as
tests/unit/test_orb_scalping_backtest.py.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.signal import OPENING_RANGE_CANDLES  # noqa: E402
from scripts.analyze_orb_arm_giveback import ARMED, NEVER_ARMED_FLATTEN, NEVER_ARMED_STOPPED  # noqa: E402
from scripts.analyze_orb_profit_by_bucket import _section, bucketed_stratified_trades  # noqa: E402

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(day: date, i: int, price: float, v: int = 1000) -> OHLCV:
    ts = datetime.combine(day, SESSION_START.time(), tzinfo=timezone.utc) + timedelta(minutes=5 * i)
    return OHLCV(timestamp=ts, open=price, high=price + 1, low=price - 1, close=price, volume=v)


def armed_day(day: date, base_price: float = 24000.0) -> list:
    """A big, clean rally that clears the 1-range-width arm level and keeps
    running -- lands in the ARMED bucket."""
    candles = [bar(day, i, base_price) for i in range(OPENING_RANGE_CANDLES)]
    candles[0] = OHLCV(timestamp=candles[0].timestamp, open=base_price, high=base_price + 5,
                       low=base_price - 5, close=base_price, volume=1000)
    breakout_i = OPENING_RANGE_CANDLES
    candles.append(bar(day, breakout_i, base_price + 30))  # closes well above the 10pt range
    price = base_price + 30
    for i in range(breakout_i + 1, breakout_i + 60):
        price += 5  # keeps climbing -- easily clears a 10pt range-width arm level
        candles.append(bar(day, i, price))
    return candles


def never_armed_flatten_day(day: date, base_price: float = 24000.0) -> list:
    """A small, short-lived rally that never reaches the arm level, then
    flatlines to the session close -- NEVER_ARMED_FLATTEN."""
    candles = [bar(day, i, base_price) for i in range(OPENING_RANGE_CANDLES)]
    candles[0] = OHLCV(timestamp=candles[0].timestamp, open=base_price, high=base_price + 5,
                       low=base_price - 5, close=base_price, volume=1000)
    breakout_i = OPENING_RANGE_CANDLES
    candles.append(bar(day, breakout_i, base_price + 6))
    for i in range(breakout_i + 1, breakout_i + 60):
        candles.append(bar(day, i, base_price + 6))
    return candles


def vix_for(candles: list) -> list:
    days = sorted({c.timestamp.date() for c in candles})
    out = []
    for d in days:
        day_len = sum(1 for c in candles if c.timestamp.date() == d)
        out += [bar(d, i, 15.0) for i in range(day_len)]
    return out


def test_bucketed_stratified_trades_classifies_and_costs_each_day():
    d1, d2 = date(2024, 1, 2), date(2024, 1, 3)
    candles = armed_day(d1) + never_armed_flatten_day(d2)
    vix_candles = vix_for(candles)

    by_bucket = bucketed_stratified_trades(candles, vix_candles, underlying="NIFTY")

    assert len(by_bucket[ARMED]) == 1
    assert len(by_bucket[NEVER_ARMED_FLATTEN]) == 1
    assert len(by_bucket[NEVER_ARMED_STOPPED]) == 0
    # Both are real BacktestTrade rows with a computed profit and costs.
    assert by_bucket[ARMED][0].qty == 65  # NIFTY_LOT_SIZE
    assert by_bucket[ARMED][0].costs > 0
    assert by_bucket[NEVER_ARMED_FLATTEN][0].costs > 0


def test_bucketed_stratified_trades_skips_days_without_vix():
    d1 = date(2024, 1, 2)
    candles = armed_day(d1)
    by_bucket = bucketed_stratified_trades(candles, [], underlying="NIFTY")
    assert sum(len(v) for v in by_bucket.values()) == 0


def test_section_reports_non_armed_subset_separately():
    d1, d2, d3 = date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)
    candles = armed_day(d1) + never_armed_flatten_day(d2) + never_armed_flatten_day(d3)
    vix_candles = vix_for(candles)
    by_bucket = bucketed_stratified_trades(candles, vix_candles, underlying="NIFTY")

    text = _section("NIFTY", by_bucket)
    assert "## NIFTY" in text
    assert "Non-armed trades alone" in text
    assert ARMED in text
    assert NEVER_ARMED_FLATTEN in text
