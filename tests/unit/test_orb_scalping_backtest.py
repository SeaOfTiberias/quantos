import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.backtest import (  # noqa: E402
    BANKNIFTY_LOT_SIZE,
    NIFTY_LOT_SIZE,
    group_by_day,
    resolve_banknifty_expiry,
    resolve_nifty_expiry,
    run_index_backtest,
)
from core.orb_scalping.signal import OPENING_RANGE_CANDLES  # noqa: E402

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(day: date, i: int, price: float, v: int = 1000) -> OHLCV:
    ts = datetime.combine(day, SESSION_START.time(), tzinfo=timezone.utc) + timedelta(minutes=5 * i)
    return OHLCV(timestamp=ts, open=price, high=price + 1, low=price - 1, close=price, volume=v)


def flat_day(day: date, n: int, price: float = 24000.0) -> list:
    return [bar(day, i, price) for i in range(n)]


# ─── group_by_day ─────────────────────────────────────────────────────────

def test_group_by_day_splits_and_sorts():
    d1, d2 = date(2024, 1, 2), date(2024, 1, 3)
    candles = flat_day(d2, 5) + flat_day(d1, 5)  # deliberately out of order
    by_day = group_by_day(candles)
    assert set(by_day.keys()) == {d1, d2}
    assert by_day[d1] == sorted(by_day[d1], key=lambda c: c.timestamp)


# ─── Expiry resolution ────────────────────────────────────────────────────

def test_resolve_banknifty_expiry_matches_monthly_calendar():
    trading_days = {date(2026, 7, 1), date(2026, 7, 28)}
    expiry, tier = resolve_banknifty_expiry(date(2026, 7, 1), trading_days)
    assert expiry == date(2026, 7, 28)  # last Tuesday of July 2026
    assert tier == "front_week"


def test_resolve_nifty_expiry_applies_dte_floor():
    # Nearest weekly on/after 2026-07-27 (Monday) would normally be
    # 2026-07-28 (Tuesday) -- only 1 day away, so the DTE floor (<2 days)
    # must roll to the FOLLOWING weekly (2026-08-04) instead.
    trading_days = {date(2026, 7, 27), date(2026, 7, 28), date(2026, 8, 4)}
    expiry, tier = resolve_nifty_expiry(date(2026, 7, 27), trading_days)
    assert expiry == date(2026, 8, 4)
    assert tier == "next_week"


def test_resolve_nifty_expiry_no_floor_needed_when_dte_is_healthy():
    # 2026-07-22 is a Wednesday -- the nearest Tuesday expiry on/after it is
    # 2026-07-28, 6 days out, clear of the 2-day floor. (An entry date that
    # IS itself an expiry Tuesday would resolve to 0 DTE and correctly
    # trigger the floor -- not what this test is checking.)
    trading_days = {date(2026, 7, 22), date(2026, 7, 28)}
    expiry, tier = resolve_nifty_expiry(date(2026, 7, 22), trading_days)
    assert expiry == date(2026, 7, 28)
    assert tier == "front_week"


# ─── run_index_backtest ────────────────────────────────────────────────────

def test_run_index_backtest_produces_one_trade_per_variant_per_signal_day():
    day1 = date(2024, 1, 2)   # Tuesday
    candles = flat_day(day1, OPENING_RANGE_CANDLES, price=24000.0)
    breakout_i = OPENING_RANGE_CANDLES
    candles.append(bar(day1, breakout_i, 24030.0))  # breaks out above the flat range
    candles += flat_day(day1, 1, price=24030.0)[0:0]  # no-op, keeps structure clear
    # extend the day with enough flat candles afterward for a session flatten
    for i in range(breakout_i + 1, breakout_i + 60):
        candles.append(bar(day1, i, 24030.0))

    vix_candles = [bar(day1, i, 15.0) for i in range(len(candles))]

    clean, stressed, harsh, real_spread = run_index_backtest(candles, vix_candles, underlying="NIFTY")

    assert len(clean) == 1
    assert len(stressed) == 1
    assert len(harsh) == 1
    assert len(real_spread) == 1
    assert clean[0].qty == NIFTY_LOT_SIZE
    # Same gross profit, different (higher) cost under Stressed/Harsh/RealSpread.
    assert clean[0].profit == stressed[0].profit == harsh[0].profit == real_spread[0].profit
    assert stressed[0].costs > clean[0].costs
    assert harsh[0].costs > clean[0].costs
    assert real_spread[0].costs > clean[0].costs


def test_run_index_backtest_uses_banknifty_lot_size():
    day1 = date(2024, 1, 2)
    candles = flat_day(day1, OPENING_RANGE_CANDLES, price=50000.0)
    breakout_i = OPENING_RANGE_CANDLES
    candles.append(bar(day1, breakout_i, 50100.0))
    for i in range(breakout_i + 1, breakout_i + 60):
        candles.append(bar(day1, i, 50100.0))
    vix_candles = [bar(day1, i, 15.0) for i in range(len(candles))]

    clean, _, _, _ = run_index_backtest(candles, vix_candles, underlying="BANKNIFTY")
    assert len(clean) == 1
    assert clean[0].qty == BANKNIFTY_LOT_SIZE


def test_run_index_backtest_skips_days_missing_vix():
    day1 = date(2024, 1, 2)
    candles = flat_day(day1, OPENING_RANGE_CANDLES, price=24000.0)
    candles.append(bar(day1, OPENING_RANGE_CANDLES, 24030.0))
    for i in range(OPENING_RANGE_CANDLES + 1, OPENING_RANGE_CANDLES + 60):
        candles.append(bar(day1, i, 24030.0))

    clean, stressed, harsh, real_spread = run_index_backtest(candles, [], underlying="NIFTY")
    assert clean == []
    assert stressed == []
    assert harsh == []
    assert real_spread == []


def test_run_index_backtest_no_breakout_produces_no_trades():
    day1 = date(2024, 1, 2)
    candles = flat_day(day1, 80, price=24000.0)  # never breaks out
    vix_candles = [bar(day1, i, 15.0) for i in range(len(candles))]
    clean, stressed, harsh, real_spread = run_index_backtest(candles, vix_candles, underlying="NIFTY")
    assert clean == []
    assert stressed == []
    assert harsh == []
    assert real_spread == []


def test_run_index_backtest_rejects_unknown_underlying():
    import pytest
    with pytest.raises(ValueError):
        run_index_backtest([], [], underlying="SENSEX")
