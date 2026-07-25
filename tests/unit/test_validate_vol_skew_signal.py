"""
Option Skew Signal — Unit Tests

Covers the pure (I/O-free) selection/replay/bucket logic in
scripts/validate_vol_skew_signal.py per docs/VOL_SKEW_METHODOLOGY.md and
docs/VOL_SKEW_METHODOLOGY_BANKNIFTY_ADDENDUM.md.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.options.greeks import DEFAULT_RISK_FREE_RATE, compute_greeks  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from scripts.validate_vol_skew_signal import (  # noqa: E402
    MIN_DTE,
    OptionRow,
    SkewDay,
    _within_moneyness_tolerance,
    _would_hit_iv_fallback,
    compute_daily_series,
    compute_skew_for_date,
    select_expiry,
    select_otm_row,
    summarize,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

def _theo_price(spot: float, strike: float, dte: int, iv: float, option_type: OptionType) -> float:
    return compute_greeks(
        spot=spot, strike=strike, days_to_expiry=dte, implied_vol=iv,
        option_type=option_type, risk_free_rate=DEFAULT_RISK_FREE_RATE,
    ).theoretical_price


def make_row(expiry: date, strike: float, option_type: OptionType,
             settle_price: float, underlying_close: float = 24000.0) -> OptionRow:
    return OptionRow(expiry=expiry, strike=strike, option_type=option_type,
                      settle_price=settle_price, underlying_close=underlying_close)


def make_chain(trade_date: date, spot: float, expiry: date, dte: int,
                put_iv: float, call_iv: float,
                strikes: list[float] = None) -> list[OptionRow]:
    """A full-ish OTM strike ladder around spot*0.95/spot*1.05, each leg's
    settle price back-solved from a known IV so compute_skew_for_date's
    recovered skew can be checked against an expected value."""
    if strikes is None:
        strikes = [round(spot * m / 50) * 50 for m in
                   (0.90, 0.93, 0.95, 0.97, 1.00, 1.03, 1.05, 1.07, 1.10)]
    rows = []
    for k in strikes:
        rows.append(make_row(expiry, k, OptionType.PUT,
                              _theo_price(spot, k, dte, put_iv, OptionType.PUT), spot))
        rows.append(make_row(expiry, k, OptionType.CALL,
                              _theo_price(spot, k, dte, call_iv, OptionType.CALL), spot))
    return rows


# ─── select_expiry ───────────────────────────────────────────────────────────

def test_select_expiry_skips_near_dated():
    trade_date = date(2026, 7, 22)
    expiries = [date(2026, 7, 23), date(2026, 7, 24), date(2026, 7, 28)]
    assert select_expiry(expiries, trade_date) == date(2026, 7, 28)


def test_select_expiry_exact_min_dte_boundary_included():
    trade_date = date(2026, 7, 22)
    expiries = [trade_date + timedelta(days=MIN_DTE)]
    assert select_expiry(expiries, trade_date) == expiries[0]


def test_select_expiry_none_when_all_too_near():
    trade_date = date(2026, 7, 22)
    expiries = [trade_date, trade_date + timedelta(days=1)]
    assert select_expiry(expiries, trade_date) is None


# ─── select_otm_row ──────────────────────────────────────────────────────────

def test_select_otm_row_picks_nearest_to_target():
    expiry = date(2026, 8, 1)
    rows = [make_row(expiry, k, OptionType.PUT, 10.0) for k in (22000, 22500, 22800, 23000)]
    spot = 24000.0  # 5% OTM put target = 22800
    best = select_otm_row(rows, spot, OptionType.PUT)
    assert best.strike == 22800


def test_select_otm_row_tiebreak_prefers_further_otm():
    expiry = date(2026, 8, 1)
    spot = 24000.0  # 5% OTM put target = 22800, equidistant candidates 22750/22850
    rows = [make_row(expiry, 22750, OptionType.PUT, 10.0),
            make_row(expiry, 22850, OptionType.PUT, 10.0)]
    assert select_otm_row(rows, spot, OptionType.PUT).strike == 22750  # further OTM (smaller)

    rows_call = [make_row(expiry, 25150, OptionType.CALL, 10.0),
                 make_row(expiry, 25250, OptionType.CALL, 10.0)]
    assert select_otm_row(rows_call, spot, OptionType.CALL).strike == 25250  # further OTM (larger)


def test_select_otm_row_none_when_no_candidates_of_type():
    expiry = date(2026, 8, 1)
    rows = [make_row(expiry, 22800, OptionType.CALL, 10.0)]
    assert select_otm_row(rows, 24000.0, OptionType.PUT) is None


# ─── _within_moneyness_tolerance ──────────────────────────────────────────────

def test_moneyness_tolerance_boundaries():
    spot = 24000.0
    expiry = date(2026, 8, 1)
    on_target = make_row(expiry, spot * 0.95, OptionType.PUT, 10.0)
    assert _within_moneyness_tolerance(on_target, spot)
    at_edge = make_row(expiry, spot * 0.93, OptionType.PUT, 10.0)  # exactly 7% OTM
    assert _within_moneyness_tolerance(at_edge, spot)
    outside = make_row(expiry, spot * 0.90, OptionType.PUT, 10.0)  # 10% OTM
    assert not _within_moneyness_tolerance(outside, spot)


# ─── _would_hit_iv_fallback ────────────────────────────────────────────────────

def test_iv_fallback_guard_catches_zero_dte():
    assert _would_hit_iv_fallback(10.0, 24000.0, 22800.0, 0, OptionType.PUT)


def test_iv_fallback_guard_catches_zero_price():
    assert _would_hit_iv_fallback(0.0, 24000.0, 22800.0, 5, OptionType.PUT)


def test_iv_fallback_guard_catches_below_intrinsic():
    # deep ITM put (strike > spot) priced below intrinsic value
    assert _would_hit_iv_fallback(100.0, 24000.0, 25000.0, 5, OptionType.PUT)


def test_iv_fallback_guard_passes_normal_otm_quote():
    assert not _would_hit_iv_fallback(50.0, 24000.0, 22800.0, 5, OptionType.PUT)


# ─── compute_skew_for_date ────────────────────────────────────────────────────

def test_compute_skew_for_date_recovers_known_skew():
    trade_date = date(2026, 7, 22)
    expiry = date(2026, 7, 29)  # DTE 7
    spot = 24000.0
    rows = make_chain(trade_date, spot, expiry, dte=7, put_iv=0.20, call_iv=0.15)
    got_spot, skew, reason = compute_skew_for_date(rows, trade_date)
    assert reason == ""
    assert got_spot == spot
    assert skew == pytest.approx(0.05, abs=0.01)  # put_iv - call_iv


def test_compute_skew_for_date_no_rows():
    assert compute_skew_for_date([], date(2026, 7, 22)) == (None, None, "no_rows")


def test_compute_skew_for_date_no_underlying_close():
    rows = [OptionRow(expiry=date(2026, 8, 1), strike=22800, option_type=OptionType.PUT,
                       settle_price=10.0, underlying_close=None)]
    spot, skew, reason = compute_skew_for_date(rows, date(2026, 7, 22))
    assert (spot, skew, reason) == (None, None, "no_underlying_close")


def test_compute_skew_for_date_no_valid_expiry():
    trade_date = date(2026, 7, 22)
    rows = [make_row(trade_date + timedelta(days=1), 22800, OptionType.PUT, 10.0)]
    spot, skew, reason = compute_skew_for_date(rows, trade_date)
    assert reason == "no_valid_expiry"


def test_compute_skew_for_date_moneyness_tolerance_skip():
    trade_date = date(2026, 7, 22)
    expiry = date(2026, 7, 29)
    spot = 24000.0
    # Only strikes far outside the 3-7% OTM band on both sides.
    rows = [make_row(expiry, spot * 0.80, OptionType.PUT, 10.0, spot),
            make_row(expiry, spot * 1.20, OptionType.CALL, 10.0, spot)]
    _, skew, reason = compute_skew_for_date(rows, trade_date)
    assert skew is None
    assert reason == "moneyness_tolerance"


def test_compute_skew_for_date_iv_fallback_skip():
    trade_date = date(2026, 7, 22)
    expiry = date(2026, 7, 29)
    spot = 24000.0
    put_strike = round(spot * 0.95 / 50) * 50
    call_strike = round(spot * 1.05 / 50) * 50
    rows = [make_row(expiry, put_strike, OptionType.PUT, 0.0, spot),   # price 0 -> fallback
            make_row(expiry, call_strike, OptionType.CALL, 50.0, spot)]
    _, skew, reason = compute_skew_for_date(rows, trade_date)
    assert skew is None
    assert reason == "iv_fallback_put"


# ─── compute_daily_series: windowing + no lookahead ─────────────────────────

def _build_rows_by_date(n_days: int, spot_path: list[float], put_iv=0.18, call_iv=0.16,
                         start=date(2026, 1, 5)) -> dict[date, list["OptionRow"]]:
    rows_by_date = {}
    d = start
    for i in range(n_days):
        expiry = d + timedelta(days=10)
        rows_by_date[d] = make_chain(d, spot_path[i], expiry, dte=10, put_iv=put_iv, call_iv=call_iv)
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    return rows_by_date


def test_compute_daily_series_skips_days_before_rv_window():
    from scripts.validate_vol_skew_signal import RV_WINDOW
    spot_path = [24000.0 + i for i in range(60)]
    rows_by_date = _build_rows_by_date(60, spot_path)
    days = compute_daily_series(rows_by_date)
    dates_sorted = sorted(rows_by_date)
    assert days[0].date == dates_sorted[RV_WINDOW]


def test_compute_daily_series_fwd_rv_none_near_series_end():
    from scripts.validate_vol_skew_signal import RV_WINDOW
    spot_path = [24000.0 + i for i in range(60)]
    rows_by_date = _build_rows_by_date(60, spot_path)
    days = compute_daily_series(rows_by_date)
    assert days[-1].fwd_rv is None
    assert days[-RV_WINDOW].fwd_rv is None
    assert days[-RV_WINDOW - 1].fwd_rv is not None


def test_compute_daily_series_no_lookahead_extending_future_leaves_past_unchanged():
    spot_path = [24000.0 + (i % 50) for i in range(80)]
    rows_short = _build_rows_by_date(60, spot_path[:60])
    rows_long = _build_rows_by_date(80, spot_path)

    days_short = compute_daily_series(rows_short)
    days_long = compute_daily_series(rows_long)

    by_date_long = {d.date: d for d in days_long}
    for d in days_short:
        match = by_date_long[d.date]
        assert match.skew == pytest.approx(d.skew)
        assert match.rv_trailing == pytest.approx(d.rv_trailing)


def test_compute_daily_series_records_skip_reason():
    trade_date = date(2026, 1, 5)
    rows_by_date = _build_rows_by_date(30, [24000.0] * 30, start=trade_date)
    # Break one mid-series day so it has no valid expiry.
    broken_date = sorted(rows_by_date)[22]
    rows_by_date[broken_date] = [make_row(broken_date + timedelta(days=1), 22800,
                                           OptionType.PUT, 10.0, 24000.0)]
    days = compute_daily_series(rows_by_date)
    broken_day = next(d for d in days if d.date == broken_date)
    assert broken_day.skew is None
    assert broken_day.skip_reason == "no_valid_expiry"


# ─── summarize ────────────────────────────────────────────────────────────────

def _skew_day(offset, skew, fwd_rv, skip_reason=""):
    return SkewDay(date=date(2026, 1, 5) + timedelta(days=offset), spot=24000.0,
                    skew=skew, skip_reason=skip_reason, rv_trailing=15.0, fwd_rv=fwd_rv)


def test_summarize_monotonic_case_passes():
    # 20 days, skew and fwd_rv both strictly ascending -> clean monotonic PASS.
    days = [_skew_day(i, skew=-10 + i, fwd_rv=10.0 + i) for i in range(20)]
    report = summarize(days, "NIFTY")
    assert "PASS" in report
    assert "Q1" in report and "Q5" in report


def test_summarize_flat_case_fails():
    # fwd_rv constant regardless of skew -> no separation -> FAIL.
    days = [_skew_day(i, skew=-10 + i, fwd_rv=15.0) for i in range(20)]
    report = summarize(days, "NIFTY")
    assert "FAIL" in report


def test_summarize_reports_skip_reasons():
    days = [_skew_day(i, skew=-10 + i, fwd_rv=10.0 + i) for i in range(20)]
    days.append(_skew_day(20, skew=None, fwd_rv=None, skip_reason="moneyness_tolerance"))
    report = summarize(days, "BANKNIFTY")
    assert "moneyness_tolerance" in report
    assert "# BANKNIFTY Option Skew Validation" in report


def test_summarize_no_scored_days():
    report = summarize([_skew_day(0, skew=None, fwd_rv=None, skip_reason="no_rows")], "NIFTY")
    assert "No days scored" in report
