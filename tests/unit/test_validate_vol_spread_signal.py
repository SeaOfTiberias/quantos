"""
IV-minus-RV Vol Spread Signal — Unit Tests

Covers the pure (I/O-free) replay/bucket logic in
scripts/validate_vol_spread_signal.py per docs/VOL_SPREAD_METHODOLOGY.md.
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import pstdev

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from scripts.validate_vol_spread_signal import (  # noqa: E402
    RV_WINDOW,
    SpreadDay,
    _annualized_rv,
    assign_bucket,
    compute_daily_series,
    quintile_cutoffs,
    summarize,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

def make_candle(day_offset: int, close: float, base=datetime(2024, 1, 1, tzinfo=timezone.utc)) -> OHLCV:
    ts = base + timedelta(days=day_offset)
    return OHLCV(timestamp=ts, open=close, high=close, low=close, close=close, volume=1000)


def make_series(closes: list[float], base=datetime(2024, 1, 1, tzinfo=timezone.utc)) -> list[OHLCV]:
    return [make_candle(i, c, base) for i, c in enumerate(closes)]


# ─── _annualized_rv ──────────────────────────────────────────────────────────

def test_annualized_rv_zero_for_flat_prices():
    assert _annualized_rv([100.0] * 10) == 0.0


def test_annualized_rv_matches_independent_formula():
    closes = [100, 101, 99, 102, 98, 103, 97, 104]
    rets_pct = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100 for i in range(1, len(closes))]
    expected = pstdev(rets_pct) * math.sqrt(252)
    assert _annualized_rv(closes) == pytest.approx(expected)


def test_annualized_rv_needs_at_least_two_closes():
    assert _annualized_rv([100.0]) == 0.0
    assert _annualized_rv([]) == 0.0


# ─── compute_daily_series: no-lookahead + windowing ─────────────────────────

def test_compute_daily_series_skips_days_before_rv_window():
    nifty = make_series([100.0 + i for i in range(60)])
    vix = make_series([15.0] * 60)
    days = compute_daily_series(nifty, vix)
    # First RV_WINDOW candles (indices 0..RV_WINDOW-1) can't form a full
    # trailing window, so the first scored day is at index RV_WINDOW.
    assert days[0].date == nifty[RV_WINDOW].timestamp


def test_compute_daily_series_fwd_rv_none_near_series_end():
    nifty = make_series([100.0 + i for i in range(60)])
    vix = make_series([15.0] * 60)
    days = compute_daily_series(nifty, vix)
    # The last RV_WINDOW scored days have no full forward window available.
    assert days[-1].fwd_rv is None
    assert days[-RV_WINDOW].fwd_rv is None
    # But the day just before that boundary does have one.
    assert days[-RV_WINDOW - 1].fwd_rv is not None


def test_compute_daily_series_no_lookahead_extending_future_leaves_past_unchanged():
    """Appending more candles at the end must not change any earlier day's
    IV, trailing RV, or spread — those must only ever depend on data up to
    that day."""
    closes = [100.0 + (i % 7) for i in range(80)]
    nifty_short = make_series(closes[:60])
    vix_short = make_series([15.0 + (i % 3) for i in range(60)])
    days_short = compute_daily_series(nifty_short, vix_short)

    nifty_long = make_series(closes)
    vix_long = make_series([15.0 + (i % 3) for i in range(80)])
    days_long = compute_daily_series(nifty_long, vix_long)

    by_date_long = {d.date: d for d in days_long}
    for d in days_short:
        match = by_date_long[d.date]
        assert match.iv == d.iv
        assert match.rv_trailing == pytest.approx(d.rv_trailing)
        assert match.spread == pytest.approx(d.spread)


def test_compute_daily_series_iv_uses_last_available_vix_on_or_before_date():
    nifty = make_series([100.0 + i for i in range(30)])
    # VIX only has data every other day (simulates a gap/holiday mismatch).
    vix_candles = [make_candle(i, 20.0 + i) for i in range(0, 30, 2)]
    days = compute_daily_series(nifty, vix_candles)
    for d in days:
        # IV must come from a VIX candle dated on or before the NIFTY day.
        eligible = [c.close for c in vix_candles if c.timestamp <= d.date]
        assert d.iv == eligible[-1]


def test_compute_daily_series_skips_days_before_first_vix_date():
    nifty = make_series([100.0 + i for i in range(40)])
    # VIX history starts after NIFTY's entire range ends (day 39) — no VIX
    # candle is ever dated on or before any NIFTY day being scored.
    vix_candles = make_series([15.0] * 10, base=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=45))
    days = compute_daily_series(nifty, vix_candles)
    assert days == []


# ─── Bucketing ────────────────────────────────────────────────────────────

def test_quintile_cutoffs_splits_into_five_equal_groups():
    values = list(range(1, 11))  # 1..10
    cutoffs = quintile_cutoffs([float(v) for v in values])
    assert len(cutoffs) == 4
    buckets = {b: 0 for b in range(1, 6)}
    for v in values:
        buckets[assign_bucket(float(v), cutoffs)] += 1
    assert buckets == {1: 2, 2: 2, 3: 2, 4: 2, 5: 2}


def test_assign_bucket_lowest_and_highest():
    cutoffs = [1.0, 2.0, 3.0, 4.0]
    assert assign_bucket(-100.0, cutoffs) == 1
    assert assign_bucket(100.0, cutoffs) == 5


# ─── summarize: report arithmetic ───────────────────────────────────────────

def _spread_day(offset, iv, rv_trailing, fwd_rv):
    return SpreadDay(
        date=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset),
        iv=iv, rv_trailing=rv_trailing, spread=iv - rv_trailing, fwd_rv=fwd_rv,
    )


def test_summarize_reports_gap_between_q5_and_q1():
    # 20 days with distinct, ascending spreads (-10..+9) and forward RV held
    # constant at the trailing RV (15.0), so earned premium == spread
    # exactly — makes the expected per-bucket arithmetic easy to verify
    # independently, and quintiles split evenly (4 days/bucket) since the
    # spread values are all distinct.
    days = [
        _spread_day(i, iv=15.0 + (-10 + i), rv_trailing=15.0, fwd_rv=15.0)
        for i in range(20)
    ]

    report = summarize(days)
    assert "Q1" in report and "Q5" in report
    assert "gap = " in report
    # Q1 = spreads -10..-7, mean = -8.5, all premiums negative -> 0% hit rate.
    # Q5 = spreads +6..+9, mean = +7.5, all premiums positive -> 100% hit rate.
    assert "-8.50" in report
    assert "+7.50" in report
    assert "0%" in report
    assert "100%" in report


def test_summarize_handles_no_scored_days():
    report = summarize([_spread_day(0, iv=15.0, rv_trailing=15.0, fwd_rv=None)])
    assert "No days scored" in report
