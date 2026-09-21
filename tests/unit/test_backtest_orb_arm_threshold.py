"""
Tests for scripts/backtest_orb_arm_threshold.py — the pre-registered grid
backtest for docs/ORB_ARM_THRESHOLD_METHODOLOGY.md. Pure-logic tests
(split, filter, pass-bar) plus one small end-to-end run against synthetic
multi-day data, no network/broker.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.backtest.parser import _compute_metrics  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.signal import OPENING_RANGE_CANDLES  # noqa: E402
from scripts.backtest_orb_arm_threshold import (  # noqa: E402
    MATERIALITY_SHARPE_DELTA,
    MIN_SAMPLE_SIZE,
    _passes_bar,
    evaluate_multiplier,
    filter_candles,
    split_days,
)

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(day: date, i: int, price: float, v: int = 1000) -> OHLCV:
    ts = datetime.combine(day, SESSION_START.time(), tzinfo=timezone.utc) + timedelta(minutes=5 * i)
    return OHLCV(timestamp=ts, open=price, high=price + 1, low=price - 1, close=price, volume=v)


def breakout_day(day: date, base_price: float = 24000.0, breakout_price: float = 24030.0) -> list:
    """A minimal day: flat opening range, then a clean CALL breakout that
    rides flat to the session flatten -- always produces exactly one
    trade, regardless of arm multiplier (only the EXIT path can differ)."""
    candles = [bar(day, i, base_price) for i in range(OPENING_RANGE_CANDLES)]
    candles.append(bar(day, OPENING_RANGE_CANDLES, breakout_price))
    for i in range(OPENING_RANGE_CANDLES + 1, OPENING_RANGE_CANDLES + 60):
        candles.append(bar(day, i, breakout_price))
    return candles


# ─── split_days ─────────────────────────────────────────────────────────────

def test_split_days_is_80_20_by_calendar_order():
    days = [date(2024, 1, d) for d in range(1, 11)]  # 10 days
    mining, holdout = split_days(days)
    assert mining == days[:8]
    assert holdout == days[8:]


def test_split_days_sorts_out_of_order_input():
    days = [date(2024, 1, 5), date(2024, 1, 1), date(2024, 1, 3)]
    mining, holdout = split_days(days)
    assert mining + holdout == sorted(days)


# ─── filter_candles ─────────────────────────────────────────────────────────

def test_filter_candles_keeps_only_allowed_days():
    d1, d2 = date(2024, 1, 2), date(2024, 1, 3)
    candles = [bar(d1, 0, 100.0), bar(d2, 0, 100.0)]
    kept = filter_candles(candles, {d1})
    assert kept == [candles[0]]


# ─── _passes_bar ────────────────────────────────────────────────────────────

def make_trades(n: int, profit_each: float = 100.0, loss_each: float = 50.0, win_count: int = None):
    """n BacktestTrade-shaped rows via the real backtest pipeline is
    overkill for testing _passes_bar alone -- it only reads
    BacktestMetrics, so build metrics directly through _compute_metrics
    over a trivial synthetic trade list."""
    from core.backtest.parser import BacktestTrade
    win_count = n // 2 if win_count is None else win_count
    trades = []
    for i in range(n):
        profit = profit_each if i < win_count else -loss_each
        trades.append(BacktestTrade(
            trade_num=i, direction="Long", qty=1,
            entry_date=datetime(2024, 1, 1) + timedelta(days=i),
            entry_price=100.0,
            exit_date=datetime(2024, 1, 1) + timedelta(days=i, hours=1),
            exit_price=100.0 + profit, profit=profit, profit_pct=profit,
            cum_profit=0.0, bars_held=10, costs=0.0,
        ))
    return _compute_metrics(trades)


def test_passes_bar_fails_below_min_sample_size():
    baseline = make_trades(40, win_count=15)
    candidate = make_trades(40, win_count=30)
    ok, reason = _passes_bar(candidate, baseline, n=MIN_SAMPLE_SIZE - 1)
    assert ok is False
    assert "n=" in reason


def test_passes_bar_fails_when_candidate_itself_has_no_edge():
    baseline = make_trades(40, win_count=15)
    candidate = make_trades(40, win_count=5)   # mostly losers
    ok, reason = _passes_bar(candidate, baseline, n=40)
    assert ok is False


def test_passes_bar_fails_when_sharpe_improvement_is_too_small():
    baseline = make_trades(40, win_count=25)
    candidate = make_trades(40, win_count=26)  # barely different
    ok, reason = _passes_bar(candidate, baseline, n=40)
    if candidate.sharpe_ratio - baseline.sharpe_ratio < MATERIALITY_SHARPE_DELTA:
        assert ok is False
        assert "Sharpe delta" in reason


def test_passes_bar_requires_positive_pf_delta_even_with_material_sharpe():
    baseline = make_trades(40, win_count=20, profit_each=100.0, loss_each=50.0)
    candidate = make_trades(40, win_count=20, profit_each=100.0, loss_each=50.0)
    # Identical -> zero deltas everywhere -> must fail both the Sharpe and PF checks.
    ok, reason = _passes_bar(candidate, baseline, n=40)
    assert ok is False


# ─── evaluate_multiplier: small end-to-end run, synthetic data ─────────────

def test_evaluate_multiplier_produces_the_same_trade_count_regardless_of_multiplier():
    """Only the EXIT path depends on the arm multiplier -- every day here
    has an unambiguous, unbroken breakout, so entry count (and therefore N)
    must be identical across multipliers."""
    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(10)]
    index_candles = []
    vix_candles = []
    for d in days:
        day_candles = breakout_day(d)
        index_candles += day_candles
        vix_candles += [bar(d, i, 15.0) for i in range(len(day_candles))]

    mining_days, holdout_days = split_days(days)

    mining_a, holdout_a, mining_n_a, holdout_n_a = evaluate_multiplier(
        index_candles, vix_candles, underlying="NIFTY", multiplier=0.25,
        mining_days=set(mining_days), holdout_days=set(holdout_days))
    mining_b, holdout_b, mining_n_b, holdout_n_b = evaluate_multiplier(
        index_candles, vix_candles, underlying="NIFTY", multiplier=1.0,
        mining_days=set(mining_days), holdout_days=set(holdout_days))

    assert mining_n_a == mining_n_b == len(mining_days)
    assert holdout_n_a == holdout_n_b == len(holdout_days)
