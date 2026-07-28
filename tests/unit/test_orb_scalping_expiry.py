import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.orb_scalping.expiry import (  # noqa: E402
    next_nifty_weekly_expiry,
    nifty_weekly_expiry,
    nifty_weekly_expiry_unadjusted,
)

# Real (trade_date, expected nearest weekly expiry) pairs, derived from the
# already-cached VRP NSE bhavcopy data (data_cache/nse_bhavcopy/parsed/) —
# see core/orb_scalping/expiry.py's module docstring for how these were
# extracted. Covers the full Thursday->Tuesday transition week.
REAL_SAMPLES = [
    ("2023-07-24", "2023-07-27"),
    ("2024-01-02", "2024-01-04"),
    ("2024-04-01", "2024-04-04"),
    ("2024-07-01", "2024-07-04"),
    ("2024-10-01", "2024-10-03"),
    ("2025-01-02", "2025-01-02"),
    ("2025-04-01", "2025-04-03"),
    ("2025-07-01", "2025-07-03"),
    ("2025-08-01", "2025-08-07"),
    ("2025-08-18", "2025-08-21"),
    ("2025-08-22", "2025-08-28"),
    ("2025-08-25", "2025-08-28"),
    ("2025-08-29", "2025-09-02"),
    ("2025-09-01", "2025-09-02"),
    ("2025-09-02", "2025-09-02"),
    ("2025-09-03", "2025-09-09"),
    ("2026-01-02", "2026-01-06"),
    ("2026-04-01", "2026-04-07"),
    ("2026-07-01", "2026-07-07"),
    ("2026-07-22", "2026-07-28"),
]


def test_matches_real_bhavcopy_samples():
    for trade_str, expected_str in REAL_SAMPLES:
        got = nifty_weekly_expiry_unadjusted(date.fromisoformat(trade_str))
        assert got == date.fromisoformat(expected_str), trade_str


def test_thursday_side_before_cutoff():
    assert nifty_weekly_expiry_unadjusted(date(2025, 8, 28)).strftime("%A") == "Thursday"


def test_tuesday_side_after_cutoff():
    assert nifty_weekly_expiry_unadjusted(date(2025, 9, 2)).strftime("%A") == "Tuesday"


def test_holiday_adjustment_rolls_earlier():
    # If the raw Tuesday itself isn't a trading day, roll to the nearest
    # earlier date that is.
    trading_days = {date(2026, 7, 6)}  # 7th (the raw Tuesday) is NOT a trading day
    got = nifty_weekly_expiry(date(2026, 7, 1), trading_days)
    assert got == date(2026, 7, 6)


def test_next_weekly_expiry_rolls_forward_one_cycle():
    trading_days = {date(2026, 7, 7), date(2026, 7, 14)}
    current = nifty_weekly_expiry(date(2026, 7, 1), trading_days)
    assert current == date(2026, 7, 7)
    nxt = next_nifty_weekly_expiry(current, trading_days)
    assert nxt == date(2026, 7, 14)
    assert nxt > current


def test_next_weekly_expiry_across_thursday_tuesday_cutover():
    # Last Thursday weekly (2025-08-28) rolling forward must land on the
    # first Tuesday weekly (2025-09-02), not skip or double back.
    trading_days = {date(2025, 8, 28), date(2025, 9, 2)}
    nxt = next_nifty_weekly_expiry(date(2025, 8, 28), trading_days)
    assert nxt == date(2025, 9, 2)
