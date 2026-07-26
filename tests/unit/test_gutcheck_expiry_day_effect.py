"""
F&O Expiry-Day Effect Gut-Check — Unit Tests

Covers the pure (I/O-free) expiry-construction and day-classification logic
in scripts/gutcheck_expiry_day_effect.py per
docs/EXPIRY_DAY_EFFECT_GUTCHECK_METHODOLOGY.md.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.gutcheck_expiry_day_effect import (  # noqa: E402
    LAST_THURSDAY_CUTOFF,
    adjust_for_holiday,
    calendar_expiry_date,
    classify_days,
    expiry_dates_in_range,
)


# ─── calendar_expiry_date ────────────────────────────────────────────────────

def test_last_thursday_before_cutoff():
    # July 2025: last Thursday is 2025-07-31, well before the cutoff.
    assert calendar_expiry_date(2025, 7) == date(2025, 7, 31)
    assert calendar_expiry_date(2025, 7).weekday() == 3  # Thursday


def test_last_tuesday_after_cutoff():
    # October 2025: last Thursday would be 2025-10-30, AFTER LAST_THURSDAY_CUTOFF
    # (2025-08-31) -- so the Tuesday convention applies.
    result = calendar_expiry_date(2025, 10)
    assert result.weekday() == 1  # Tuesday
    assert result == date(2025, 10, 28)


def test_cutoff_month_uses_thursday():
    # August 2025's own last-Thursday date is 2025-08-28, on/before the
    # 2025-08-31 cutoff -- still Thursday convention.
    result = calendar_expiry_date(2025, 8)
    assert result.weekday() == 3
    assert result <= LAST_THURSDAY_CUTOFF


def test_september_2025_switches_to_tuesday():
    result = calendar_expiry_date(2025, 9)
    assert result.weekday() == 1


# ─── adjust_for_holiday ──────────────────────────────────────────────────────

def test_holiday_rolls_to_earlier_trading_day():
    trading_days = {date(2025, 7, 29), date(2025, 7, 30)}  # 31st missing (holiday)
    assert adjust_for_holiday(date(2025, 7, 31), trading_days) == date(2025, 7, 30)


def test_no_adjustment_when_already_trading_day():
    trading_days = {date(2025, 7, 31)}
    assert adjust_for_holiday(date(2025, 7, 31), trading_days) == date(2025, 7, 31)


# ─── expiry_dates_in_range ───────────────────────────────────────────────────

def test_expiry_dates_one_per_month():
    start, end = date(2024, 1, 1), date(2024, 4, 30)
    trading_days = set()
    d = start
    while d <= end:
        if d.weekday() < 5:
            trading_days.add(d)
        d += timedelta(days=1)
    expiries = expiry_dates_in_range(start, end, trading_days)
    assert len(expiries) == 4
    assert all(e.weekday() == 3 for e in expiries)  # all Thursdays, pre-cutover


def test_expiry_dates_span_convention_change():
    start, end = date(2025, 8, 1), date(2025, 10, 31)
    trading_days = set()
    d = start
    while d <= end:
        if d.weekday() < 5:
            trading_days.add(d)
        d += timedelta(days=1)
    expiries = expiry_dates_in_range(start, end, trading_days)
    assert len(expiries) == 3
    aug, sep, oct_ = expiries
    assert aug.weekday() == 3   # last Thursday convention
    assert sep.weekday() == 1   # already switched
    assert oct_.weekday() == 1


# ─── classify_days ────────────────────────────────────────────────────────────

def _consecutive_trading_days(start: date, n: int) -> list:
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_classify_marks_expiry_pre_post():
    days = _consecutive_trading_days(date(2024, 1, 1), 10)
    expiry = days[5]
    labels, overlaps = classify_days(days, [expiry])
    assert labels[expiry] == "expiry"
    assert labels[days[4]] == "pre_expiry"
    assert labels[days[6]] == "post_expiry"
    assert labels[days[0]] == "other"
    assert overlaps == []


def test_classify_expiry_priority_over_pre_post_on_overlap():
    # Two expiries on adjacent trading days -- e1's "post" target and e2's
    # "pre" target both land on the OTHER expiry's own day. Per the
    # methodology doc, expiry wins and both collisions get logged.
    days = _consecutive_trading_days(date(2024, 1, 1), 10)
    e1, e2 = days[3], days[4]
    labels, overlaps = classify_days(days, [e1, e2])
    assert labels[e1] == "expiry"
    assert labels[e2] == "expiry"
    assert labels[days[2]] == "pre_expiry"   # e1's own pre-day, unaffected
    assert labels[days[5]] == "post_expiry"  # e2's own post-day, unaffected
    assert len(overlaps) == 2
    assert {ov.kind for ov in overlaps} == {"pre_expiry_overlap", "post_expiry_overlap"}


def test_classify_expiry_at_first_or_last_day_no_crash():
    days = _consecutive_trading_days(date(2024, 1, 1), 5)
    labels, overlaps = classify_days(days, [days[0], days[-1]])
    assert labels[days[0]] == "expiry"
    assert labels[days[-1]] == "expiry"
    assert overlaps == []
