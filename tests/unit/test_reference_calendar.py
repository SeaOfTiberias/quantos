"""
Tests for core/reference/calendar.py.

These lean deliberately on the *real committed data file* rather than a
fixture. The calendar's whole value is that it encodes what actually happened
on NSE, so a test against a synthetic three-day calendar would pass while the
shipped data was wrong. The specific dates asserted below are verifiable
public events — Budget sessions, Muhurat trading, the 2024 disaster-recovery
special sessions — and each is named so a failure says which fact broke.

The one thing NOT pinned here is the coverage end date, which moves every time
the derivation is re-run. Pinning it would make this a wall-clock time bomb,
which is the exact defect already open in test_fyers_symbol_master.py.
"""

from datetime import date, datetime

import pytest

from core.reference import calendar as cal


# ── Weekend sessions: the 11 days the naive helper drops ────────────────────
# Budget days that fell on a weekend, Muhurat (Diwali) sessions, and the three
# 2024 special live trading sessions run from the disaster-recovery site.

BUDGET_WEEKEND = [
    date(2015, 2, 28),   # Saturday
    date(2020, 2, 1),    # Saturday
    date(2025, 2, 1),    # Saturday
    date(2026, 2, 1),    # Sunday
]

MUHURAT = [
    date(2016, 10, 30),  # Sunday
    date(2019, 10, 27),  # Sunday
    date(2020, 11, 14),  # Saturday
    date(2023, 11, 12),  # Sunday
]

SPECIAL_2024 = [
    date(2024, 1, 20),   # Saturday
    date(2024, 3, 2),    # Saturday
    date(2024, 5, 18),   # Saturday
]


@pytest.mark.parametrize("d", BUDGET_WEEKEND, ids=lambda d: f"budget-{d}")
def test_weekend_budget_sessions_are_trading_days(d):
    assert cal.is_trading_day(d), f"{d} was a Budget session held on a weekend"


@pytest.mark.parametrize("d", MUHURAT, ids=lambda d: f"muhurat-{d}")
def test_muhurat_sessions_are_trading_days(d):
    assert cal.is_trading_day(d), f"{d} was a Muhurat (Diwali) session"


@pytest.mark.parametrize("d", SPECIAL_2024, ids=lambda d: f"special-{d}")
def test_2024_special_sessions_are_trading_days(d):
    assert cal.is_trading_day(d), f"{d} was a special live trading session"


def test_every_weekend_session_is_actually_a_weekend():
    """Guards the derivation, not the calendar: if a re-run silently lost the
    range-fetch property, these would quietly stop being weekends."""
    for d in BUDGET_WEEKEND + MUHURAT + SPECIAL_2024:
        assert d.weekday() >= 5, f"{d} is not a weekend — fixture is wrong"


# ── Holidays: the far larger error the naive helper makes ───────────────────

@pytest.mark.parametrize("d,name", [
    (date(2025, 1, 26), "Republic Day"),
    (date(2025, 8, 15), "Independence Day"),
    (date(2025, 10, 2), "Gandhi Jayanti"),
    (date(2024, 1, 26), "Republic Day"),
    (date(2024, 8, 15), "Independence Day"),
])
def test_national_holidays_are_not_trading_days(d, name):
    assert not cal.is_trading_day(d), f"{d} ({name}) is an NSE holiday"


def test_weekends_are_not_trading_days_by_default():
    # An ordinary Saturday and Sunday with no special session.
    assert not cal.is_trading_day(date(2025, 6, 7))    # Saturday
    assert not cal.is_trading_day(date(2025, 6, 8))    # Sunday


# ── Fail-closed contract ────────────────────────────────────────────────────

def test_before_coverage_raises_rather_than_guessing():
    lo, _ = cal.coverage()
    with pytest.raises(cal.DateOutOfRange):
        cal.is_trading_day(date(lo.year - 1, 6, 10))


def test_after_coverage_raises_rather_than_guessing():
    _, hi = cal.coverage()
    with pytest.raises(cal.DateOutOfRange):
        cal.is_trading_day(date(hi.year + 5, 6, 10))


def test_out_of_range_message_names_the_window_and_the_fix():
    lo, _ = cal.coverage()
    with pytest.raises(cal.DateOutOfRange, match="derive_nse_calendar"):
        cal.is_trading_day(date(lo.year - 1, 6, 10))


# ── Ranges ──────────────────────────────────────────────────────────────────

def test_trading_days_is_inclusive_of_both_ends():
    days = cal.trading_days(date(2025, 1, 1), date(2025, 1, 31))
    assert days[0] == date(2025, 1, 1)      # a session
    assert date(2025, 1, 26) not in days    # Republic Day
    assert all(date(2025, 1, 1) <= d <= date(2025, 1, 31) for d in days)


def test_trading_days_counts_a_known_month_correctly():
    """January 2025: 31 days, 8 weekend days, Republic Day on a Sunday
    (so it costs nothing extra), leaving 23 sessions."""
    assert cal.session_count(date(2025, 1, 1), date(2025, 1, 31)) == 23


def test_a_full_year_is_in_the_expected_band():
    """NSE runs ~245-252 sessions a year. A derivation that broke would land
    far outside this band rather than a few days off."""
    n = cal.session_count(date(2025, 1, 1), date(2025, 12, 31))
    assert 240 <= n <= 255, f"2025 derived {n} sessions"


def test_reversed_range_is_an_error_not_an_empty_list():
    with pytest.raises(ValueError):
        cal.trading_days(date(2025, 3, 1), date(2025, 2, 1))


def test_trading_days_never_returns_a_non_session():
    for d in cal.trading_days(date(2024, 1, 1), date(2024, 12, 31)):
        assert cal.is_trading_day(d)


# ── Navigation ──────────────────────────────────────────────────────────────

def test_next_trading_day_skips_a_holiday_weekend():
    # 2025-01-25 Sat, 26 Sun (Republic Day), so Friday 24th -> Monday 27th.
    assert cal.next_trading_day(date(2025, 1, 24)) == date(2025, 1, 27)


def test_previous_trading_day_skips_a_holiday_weekend():
    assert cal.previous_trading_day(date(2025, 1, 27)) == date(2025, 1, 24)


def test_next_and_previous_are_strict_not_inclusive():
    d = date(2025, 6, 10)
    assert cal.is_trading_day(d)
    assert cal.next_trading_day(d) != d
    assert cal.previous_trading_day(d) != d


def test_next_then_previous_round_trips():
    d = date(2025, 6, 10)
    assert cal.previous_trading_day(cal.next_trading_day(d)) == d


def test_shift_sessions_forward_and_back():
    d = date(2025, 6, 10)
    assert cal.shift_sessions(cal.shift_sessions(d, 5), -5) == d


def test_shift_sessions_by_one_matches_next_trading_day():
    d = date(2025, 6, 10)
    assert cal.shift_sessions(d, 1) == cal.next_trading_day(d)


def test_shift_sessions_zero_on_a_non_session_is_an_error():
    with pytest.raises(ValueError):
        cal.shift_sessions(date(2025, 1, 26), 0)   # Republic Day


def test_shift_sessions_past_the_window_raises():
    _, hi = cal.coverage()
    with pytest.raises(cal.DateOutOfRange):
        cal.shift_sessions(hi, 10_000)


# ── Input coercion ──────────────────────────────────────────────────────────

def test_accepts_date_datetime_and_iso_string_alike():
    d = date(2025, 6, 10)
    assert cal.is_trading_day(d)
    assert cal.is_trading_day(datetime(2025, 6, 10, 15, 30))
    assert cal.is_trading_day("2025-06-10")


def test_rejects_an_unsupported_type():
    with pytest.raises(TypeError):
        cal.is_trading_day(20250610)


# ── filter_sessions ─────────────────────────────────────────────────────────

def test_filter_sessions_keeps_only_real_sessions():
    kept = cal.filter_sessions([
        date(2025, 1, 24),   # session
        date(2025, 1, 25),   # Saturday
        date(2025, 1, 26),   # Republic Day
        date(2025, 1, 27),   # session
    ])
    assert kept == [date(2025, 1, 24), date(2025, 1, 27)]


def test_filter_sessions_drops_out_of_range_silently():
    lo, _ = cal.coverage()
    kept = cal.filter_sessions([date(lo.year - 1, 6, 10), date(2025, 1, 24)])
    assert kept == [date(2025, 1, 24)]


def test_filter_sessions_deduplicates_and_sorts():
    kept = cal.filter_sessions(
        ["2025-01-27", date(2025, 1, 24), "2025-01-27"]
    )
    assert kept == [date(2025, 1, 24), date(2025, 1, 27)]


# ── The data file itself ────────────────────────────────────────────────────

def test_data_file_is_committed_and_non_trivial():
    """The VM has no bhavcopy cache and cannot regenerate this locally, so it
    must travel with the repo."""
    assert cal.DATA_PATH.exists()
    lo, hi = cal.coverage()
    assert lo <= date(2015, 1, 2)
    assert cal.session_count(lo, hi) > 2_500


def test_sessions_are_unique_and_sorted():
    days = cal._sessions()
    assert list(days) == sorted(days)
    assert len(set(days)) == len(days)
