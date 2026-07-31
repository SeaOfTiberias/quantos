import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.analyze_orb_spread_samples import (  # noqa: E402
    is_banknifty_monthly_expiry_day,
    is_nifty_weekly_expiry_day,
    ist_date,
    load_rows,
)


def test_ist_date_converts_utc_to_ist_calendar_date():
    # 2026-07-30T09:45:08Z (UTC) is 15:15 IST the SAME calendar day.
    assert ist_date("2026-07-30T09:45:08.619316+00:00") == date(2026, 7, 30)


def test_ist_date_rolls_forward_across_midnight_utc():
    # 2026-07-30T19:00:00Z (UTC) is 00:30 IST the NEXT calendar day.
    assert ist_date("2026-07-30T19:00:00+00:00") == date(2026, 7, 31)


def test_nifty_weekly_expiry_day_true_on_the_expiry_itself():
    # 2026-08-04 is a Tuesday (post-cutover NIFTY weekly expiry day).
    assert is_nifty_weekly_expiry_day(date(2026, 8, 4)) is True


def test_nifty_weekly_expiry_day_false_on_an_ordinary_day():
    assert is_nifty_weekly_expiry_day(date(2026, 7, 29)) is False


def test_banknifty_monthly_expiry_day_true_on_the_expiry_itself():
    assert is_banknifty_monthly_expiry_day(date(2026, 8, 25)) is True


def test_banknifty_monthly_expiry_day_false_on_an_ordinary_day():
    assert is_banknifty_monthly_expiry_day(date(2026, 8, 4)) is False


def test_none_of_the_2026_07_29_30_samples_are_expiry_days():
    # Confirms the current dataset (deployed 2026-07-28, sampled 07-29/30)
    # has zero expiry-day rows -- the whole reason this script exists is
    # that SAMPLED_SPREAD_SLIPPAGE_BPS is currently a non-expiry-day-only
    # rate by accident, per Fable's 2026-07-31 review.
    csv_path = Path(__file__).resolve().parents[2] / "data_cache" / "orb_scalping_spread_samples.csv"
    if not csv_path.exists():
        return  # data_cache/ is gitignored -- skip where the file isn't present (e.g. fresh clone)
    rows = load_rows(csv_path)
    assert all(not r["_is_expiry_day"] for r in rows)
