import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.analyze_orb_spread_samples import (  # noqa: E402
    is_banknifty_monthly_expiry_day,
    is_in_session,
    is_nifty_weekly_expiry_day,
    ist_date,
    load_rows,
)
from scripts.probe_orb_scalping_real_spreads import LOG_FIELDS  # noqa: E402


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


# ─── Session-time filter ────────────────────────────────────────────────────
# Added after Fable's 2026-09-01 adversarial review of the Stratified cost
# variant: two rows in the live dataset predated market open (07:40 IST and
# 08:25 IST -- neither matches the timer's own 09:35/12:00/15:15 IST fires,
# both leftover manual test runs), and one of them alone manufactured the
# entire "expiry-day spread is roughly DOUBLE" finding for NIFTY. An
# in-session-only filter removes them regardless of how they got there.

def test_is_in_session_true_for_a_scheduled_fire():
    # 09:45 UTC = 15:15 IST, the timer's own third daily fire.
    assert is_in_session("2026-07-30T09:45:08.619316+00:00") is True


def test_is_in_session_false_before_market_open():
    # 02:10 UTC = 07:40 IST -- the exact pre-open row Fable's review found.
    assert is_in_session("2026-08-04T02:10:00+00:00") is False


def test_is_in_session_false_after_market_close():
    # 10:30 UTC = 16:00 IST, after the 15:30 close.
    assert is_in_session("2026-07-30T10:30:00+00:00") is False


def test_is_in_session_boundaries_are_inclusive_exclusive():
    assert is_in_session("2026-07-30T03:45:00+00:00") is True   # 09:15 IST, open
    assert is_in_session("2026-07-30T10:00:00+00:00") is False  # 15:30 IST, closed


def _write_csv(tmp_path, rows):
    path = tmp_path / "samples.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(sampled_at_utc, underlying="NIFTY", option_type="CE", spread=0.20):
    return {"sampled_at_utc": sampled_at_utc, "underlying": underlying,
            "option_type": option_type, "strike": 24000, "dte": 7,
            "spot": 24000, "bid": 100, "ask": 100.2, "ltp": 100.1,
            "spread_pct_of_mid": spread}


def test_load_rows_discards_out_of_session_rows_and_reports_them(tmp_path):
    # A pre-open row parked inside an otherwise-legitimate day must be
    # split out, not blended into the in-session mean.
    csv_path = _write_csv(tmp_path, [
        _row("2026-08-04T02:10:00+00:00", spread=1.528),  # 07:40 IST, pre-open
        _row("2026-08-04T04:05:00+00:00", spread=0.200),  # 09:35 IST, legitimate
    ])
    rows, discarded = load_rows(csv_path)
    assert len(rows) == 1 and rows[0]["spread_pct_of_mid"] == "0.2"
    assert len(discarded) == 1 and discarded[0]["spread_pct_of_mid"] == "1.528"


def test_load_rows_keeps_every_row_when_all_are_in_session(tmp_path):
    csv_path = _write_csv(tmp_path, [
        _row("2026-08-04T04:05:00+00:00"),
        _row("2026-08-04T06:30:00+00:00"),
    ])
    rows, discarded = load_rows(csv_path)
    assert len(rows) == 2
    assert discarded == []
