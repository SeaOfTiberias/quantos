"""
Known-Event Proximity Signal — Unit Tests

Covers the pure (I/O-free) event-flagging/replay/summary logic in
scripts/validate_event_proximity_signal.py per
docs/EVENT_PROXIMITY_METHODOLOGY.md.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.validate_vol_skew_signal import OptionRow  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from scripts.validate_event_proximity_signal import (  # noqa: E402
    EVENT_WINDOW_CALENDAR_DAYS,
    EventProximityDay,
    compute_daily_series,
    is_event_day,
    summarize,
)


# ─── is_event_day ────────────────────────────────────────────────────────────

def test_is_event_day_exact_match():
    events = [date(2026, 8, 6)]
    assert is_event_day(date(2026, 8, 6), events)


def test_is_event_day_within_window():
    events = [date(2026, 8, 6)]
    assert is_event_day(date(2026, 8, 5), events)  # -1 day
    assert is_event_day(date(2026, 8, 7), events)  # +1 day


def test_is_event_day_outside_window():
    events = [date(2026, 8, 6)]
    assert not is_event_day(date(2026, 8, 4), events)  # -2 days
    assert not is_event_day(date(2026, 8, 8), events)  # +2 days


def test_is_event_day_empty_calendar():
    assert not is_event_day(date(2026, 8, 6), [])


def test_is_event_day_custom_window():
    events = [date(2026, 8, 6)]
    assert is_event_day(date(2026, 8, 9), events, window_days=3)
    assert not is_event_day(date(2026, 8, 10), events, window_days=3)


# ─── compute_daily_series: windowing + no lookahead ─────────────────────────

def _row(d: date, close: float):
    return OptionRow(expiry=d + timedelta(days=30), strike=close, option_type=OptionType.CALL,
                      settle_price=10.0, underlying_close=close)


def _build_rows_by_date(n_days: int, closes: list[float], start=date(2026, 1, 5)) -> dict:
    rows_by_date = {}
    d = start
    for i in range(n_days):
        rows_by_date[d] = [_row(d, closes[i])]
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    return rows_by_date


def test_compute_daily_series_skips_days_before_rv_window():
    from scripts.validate_vol_spread_signal import RV_WINDOW
    closes = [24000.0 + i for i in range(60)]
    rows_by_date = _build_rows_by_date(60, closes)
    days = compute_daily_series(rows_by_date)
    dates_sorted = sorted(rows_by_date)
    assert days[0].date == dates_sorted[RV_WINDOW]


def test_compute_daily_series_fwd_rv_none_near_series_end():
    from scripts.validate_vol_spread_signal import RV_WINDOW
    closes = [24000.0 + i for i in range(60)]
    rows_by_date = _build_rows_by_date(60, closes)
    days = compute_daily_series(rows_by_date)
    assert days[-1].fwd_rv is None
    assert days[-RV_WINDOW - 1].fwd_rv is not None


def test_compute_daily_series_flags_known_rbi_date():
    # 2026-06-05 is a real pre-registered RBI resolution date.
    start = date(2026, 5, 1)
    closes = [24000.0 + i for i in range(45)]
    rows_by_date = _build_rows_by_date(45, closes, start=start)
    days = compute_daily_series(rows_by_date)
    flagged = next((d for d in days if d.date == date(2026, 6, 5)), None)
    assert flagged is not None
    assert flagged.is_rbi
    assert flagged.is_event


def test_compute_daily_series_no_lookahead_extending_future_leaves_past_unchanged():
    closes = [24000.0 + (i % 50) for i in range(80)]
    rows_short = _build_rows_by_date(60, closes[:60])
    rows_long = _build_rows_by_date(80, closes)

    days_short = compute_daily_series(rows_short)
    days_long = compute_daily_series(rows_long)

    by_date_long = {d.date: d for d in days_long}
    for d in days_short:
        match = by_date_long[d.date]
        assert match.rv_trailing == pytest.approx(d.rv_trailing)
        assert match.is_event == d.is_event


# ─── summarize ────────────────────────────────────────────────────────────────

def _pd(offset, fwd_rv, is_rbi=False, is_budget=False):
    return EventProximityDay(date=date(2026, 1, 5) + timedelta(days=offset), close=24000.0,
                              is_rbi=is_rbi, is_budget=is_budget, rv_trailing=15.0, fwd_rv=fwd_rv)


def test_summarize_event_days_higher_fwd_rv_passes():
    days = ([_pd(i, fwd_rv=10.0) for i in range(50)]
            + [_pd(i, fwd_rv=20.0, is_rbi=True) for i in range(50, 55)])
    report = summarize(days, "NIFTY")
    assert "PASS" in report


def test_summarize_no_difference_fails():
    days = ([_pd(i, fwd_rv=15.0) for i in range(50)]
            + [_pd(i, fwd_rv=15.0, is_rbi=True) for i in range(50, 55)])
    report = summarize(days, "NIFTY")
    assert "FAIL" in report


def test_summarize_reports_both_pooled_and_rbi_only_breakdown():
    days = ([_pd(i, fwd_rv=10.0) for i in range(50)]
            + [_pd(i, fwd_rv=20.0, is_budget=True) for i in range(50, 53)])
    report = summarize(days, "BANKNIFTY")
    assert "Pooled: RBI + Budget" in report
    assert "RBI-only" in report
    assert "# BANKNIFTY Known-Event Proximity Validation" in report


def test_summarize_no_scored_days():
    report = summarize([EventProximityDay(date=date(2026, 1, 5), close=24000.0,
                                           is_rbi=False, is_budget=False,
                                           rv_trailing=None, fwd_rv=None)], "NIFTY")
    assert "No days scored" in report
