"""
10:10 Breakout — Backtest Orchestration Unit Tests

Covers core/breakout1010/backtest.py: expiry-date resolution (calendar
construction, cross-verified in docs/BREAKOUT_1010_METHODOLOGY.md against
real bhavcopy ground truth) and the end-to-end run_backtest() wiring.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.breakout1010.backtest import LOT_SIZE, resolve_expiry, run_backtest  # noqa: E402
from core.breakout1010.signal import REFERENCE_CANDLE_INDEX  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402

SESSION_START = datetime(2026, 6, 15, 3, 45, tzinfo=timezone.utc)  # 09:15 IST, a Monday


def bar(day_offset: int, i: int, price: float, high=None, low=None, v: int = 1000) -> OHLCV:
    ts = SESSION_START + timedelta(days=day_offset) + timedelta(minutes=5 * i)
    return OHLCV(timestamp=ts, open=price, high=high if high is not None else price + 1,
                 low=low if low is not None else price - 1, close=price, volume=v)


def _all_days(start: date, end: date) -> set:
    days = set()
    d = start
    while d <= end:
        days.add(d)
        d += timedelta(days=1)
    return days


# ─── resolve_expiry ───────────────────────────────────────────────────────

def test_resolve_expiry_matches_real_bhavcopy_ground_truth():
    """Cross-checked live 2026-07-27 against real BANKNIFTY bhavcopy rows
    (see docs/BREAKOUT_1010_METHODOLOGY.md's "Data sources" section) --
    these exact (entry_date -> expiry) pairs are not invented."""
    trading_days = _all_days(date(2026, 1, 1), date(2026, 7, 31))
    assert resolve_expiry(date(2026, 6, 20), trading_days) == date(2026, 6, 30)
    assert resolve_expiry(date(2026, 4, 20), trading_days) == date(2026, 4, 28)
    assert resolve_expiry(date(2026, 2, 20), trading_days) == date(2026, 2, 24)


def test_resolve_expiry_rolls_to_next_month_once_this_months_has_passed():
    trading_days = _all_days(date(2026, 1, 1), date(2026, 7, 31))
    assert resolve_expiry(date(2026, 7, 1), trading_days) == date(2026, 7, 28)


def test_resolve_expiry_holiday_adjusts_to_the_nearest_earlier_trading_day():
    # the raw calendar expiry (last Tuesday of the month) is deliberately
    # excluded from trading_days, forcing a roll-back
    year, month = 2026, 6
    from core.breakout1010.backtest import calendar_expiry_date
    raw = calendar_expiry_date(year, month)
    trading_days = _all_days(date(2026, 1, 1), date(2026, 7, 31)) - {raw}
    resolved = resolve_expiry(date(2026, 6, 20), trading_days)
    assert resolved < raw
    assert resolved in trading_days


# ─── run_backtest end-to-end wiring ──────────────────────────────────────

def _one_trading_day(day_offset: int, breakout: bool = True) -> list[OHLCV]:
    candles = [bar(day_offset, i, 50000.0) for i in range(80)]
    ref_i = REFERENCE_CANDLE_INDEX
    candles[ref_i] = bar(day_offset, ref_i, 50000.0, high=50010.0, low=49990.0)
    if breakout:
        breakout_i = ref_i + 2
        candles[breakout_i] = bar(day_offset, breakout_i, 50020.0, high=50025.0, low=49995.0)
    return candles


def test_run_backtest_produces_one_trade_for_a_breakout_day():
    day_candles = _one_trading_day(day_offset=0, breakout=True)
    vix_candles = [bar(0, i, 15.0, high=15.0, low=15.0) for i in range(80)]

    trades = run_backtest(day_candles, vix_candles)

    assert len(trades) == 1
    assert trades[0].qty == LOT_SIZE
    assert trades[0].direction == "Long"   # buying a CALL or PUT is always a long-premium position


def test_run_backtest_skips_a_day_with_no_vix_data():
    day_candles = _one_trading_day(day_offset=0, breakout=True)
    trades = run_backtest(day_candles, vix_candles=[])
    assert trades == []


def test_run_backtest_skips_a_day_with_no_breakout():
    day_candles = _one_trading_day(day_offset=0, breakout=False)
    vix_candles = [bar(0, i, 15.0, high=15.0, low=15.0) for i in range(80)]
    trades = run_backtest(day_candles, vix_candles)
    assert trades == []


def test_run_backtest_numbers_trades_sequentially_across_days():
    d0 = _one_trading_day(day_offset=0, breakout=True)
    d1 = _one_trading_day(day_offset=1, breakout=True)
    bn_candles = d0 + d1
    vix_candles = [bar(0, i, 15.0, high=15.0, low=15.0) for i in range(80)] + \
                  [bar(1, i, 15.0, high=15.0, low=15.0) for i in range(80)]

    trades = run_backtest(bn_candles, vix_candles)

    assert len(trades) == 2
    assert [t.trade_num for t in trades] == [1, 2]
