"""
ORB condition-mining — Unit Tests

Covers core/orb_scalping/conditions.py's six pure functions per
docs/ORB_CONDITION_MINING_METHODOLOGY.md. Condition 1 (stage) is tested
against the REAL Weinstein note (obsidian_vault/QuantOS/brain/), same
precedent as tests/unit/test_vault_stages.py, rather than a synthetic
clause set — this exercise is defined as "whatever the brain/ note says",
so testing against a private copy would test the wrong thing.
"""

import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.orb_scalping.conditions import (  # noqa: E402
    bucket_dte,
    day_of_week,
    gap_pct,
    index_stage_at,
    load_weinstein_clauses,
    opening_range_width,
    range_width_ratio,
)
from core.vault.models import Stage  # noqa: E402

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def daily_bars(closes: list[float]) -> list[OHLCV]:
    return [
        OHLCV(timestamp=_BASE + timedelta(days=i), open=c, high=c * 1.01,
              low=c * 0.99, close=c, volume=100_000)
        for i, c in enumerate(closes)
    ]


def five_min_bar(minute: int, o: float, h: float, l: float, c: float) -> OHLCV:
    ts = datetime(2026, 1, 6, 3, 45, tzinfo=timezone.utc) + timedelta(minutes=5 * minute)
    return OHLCV(timestamp=ts, open=o, high=h, low=l, close=c, volume=1000)


# 400 rising daily bars — same window test_vault_stages.py uses to warm up
# sma(150)[125] (needs 275 bars).
def rising(n=400, rate=0.004, start=100.0):
    return [start * math.exp(i * rate) for i in range(n)]


# ─── opening_range_width ─────────────────────────────────────────────────

def test_opening_range_width_is_high_minus_low_of_first_n_candles():
    candles = [
        five_min_bar(0, 100, 105, 98, 102),
        five_min_bar(1, 102, 103, 95, 100),
        five_min_bar(2, 100, 110, 99, 108),
        five_min_bar(3, 108, 112, 107, 111),  # outside the 3-candle window
    ]
    assert opening_range_width(candles) == 110 - 95


# ─── day_of_week ─────────────────────────────────────────────────────────

def test_day_of_week_matches_calendar():
    assert day_of_week(date(2026, 9, 3)) == "Thursday"
    assert day_of_week(date(2026, 9, 7)) == "Monday"


# ─── range_width_ratio ───────────────────────────────────────────────────

def test_range_width_ratio_no_trailing_history_is_none():
    candles = [five_min_bar(i, 100, 101, 99, 100) for i in range(3)]
    assert range_width_ratio(candles, trailing_widths=[]) is None


def test_range_width_ratio_wider_than_usual_is_above_one():
    candles = [
        five_min_bar(0, 100, 120, 80, 110),   # width 40
        five_min_bar(1, 110, 111, 109, 110),
        five_min_bar(2, 110, 111, 109, 110),
    ]
    # trailing average width was 10 -> today's 40 is 4x
    ratio = range_width_ratio(candles, trailing_widths=[10.0, 10.0, 10.0])
    assert ratio == 4.0


def test_range_width_ratio_zero_average_is_none():
    candles = [five_min_bar(i, 100, 101, 99, 100) for i in range(3)]
    assert range_width_ratio(candles, trailing_widths=[0.0, 0.0]) is None


# ─── gap_pct ──────────────────────────────────────────────────────────────

def test_gap_pct_positive_gap():
    assert gap_pct(today_first_candle_open=102.0, prior_daily_close=100.0) == 2.0


def test_gap_pct_negative_gap():
    assert gap_pct(today_first_candle_open=98.0, prior_daily_close=100.0) == -2.0


def test_gap_pct_no_prior_close_is_none():
    assert gap_pct(today_first_candle_open=100.0, prior_daily_close=None) is None
    assert gap_pct(today_first_candle_open=100.0, prior_daily_close=0.0) is None


# ─── bucket_dte ───────────────────────────────────────────────────────────

def test_bucket_dte_boundaries():
    assert bucket_dte(0) == "0-1"
    assert bucket_dte(1) == "0-1"
    assert bucket_dte(2) == "2-4"
    assert bucket_dte(4) == "2-4"
    assert bucket_dte(5) == "5-9"
    assert bucket_dte(9) == "5-9"
    assert bucket_dte(10) == "10+"
    assert bucket_dte(30) == "10+"


# ─── load_weinstein_clauses ────────────────────────────────────────────────

def test_load_weinstein_clauses_reads_the_real_brain_note():
    clauses = load_weinstein_clauses()
    assert len(clauses) >= 4
    assert clauses[-1].is_default   # a terminal default must exist


# ─── index_stage_at ─────────────────────────────────────────────────────

def test_index_stage_at_matches_direct_classify_call():
    bars = daily_bars(rising())
    clauses = load_weinstein_clauses()
    entry_date = bars[-1].timestamp.date()
    stage = index_stage_at(bars, entry_date, clauses)
    # A steadily rising 400-bar series is Weinstein's textbook Stage 2.
    assert stage is Stage.ADVANCING


def test_index_stage_at_unknown_date_is_none():
    bars = daily_bars(rising())
    clauses = load_weinstein_clauses()
    stage = index_stage_at(bars, date(1999, 1, 1), clauses)
    assert stage is None


def test_index_stage_at_no_lookahead():
    """Appending future bars after the entry date must not change the
    classification AT that date — same invariant every no-lookahead test
    in this project asserts (e.g. test_validate_vol_spread_signal.py)."""
    closes = rising(n=350)
    bars_full = daily_bars(closes)
    entry_date = bars_full[299].timestamp.date()
    clauses = load_weinstein_clauses()

    stage_partial = index_stage_at(bars_full[:300], entry_date, clauses)
    stage_with_future = index_stage_at(bars_full, entry_date, clauses)

    assert stage_partial == stage_with_future
