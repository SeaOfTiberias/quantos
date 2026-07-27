"""
ATM IV Term Structure Signal — Unit Tests

Covers the pure (I/O-free) selection/replay/bucket logic in
scripts/validate_vol_term_structure_signal.py per
docs/VOL_TERM_STRUCTURE_METHODOLOGY.md.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.options.greeks import DEFAULT_RISK_FREE_RATE, compute_greeks  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from scripts.validate_vol_skew_signal import OptionRow  # noqa: E402
from scripts.validate_vol_term_structure_signal import (  # noqa: E402
    MIN_DTE,
    TermStructureDay,
    _within_atm_tolerance,
    compute_daily_series,
    compute_term_structure_for_date,
    select_atm_row,
    select_expiry_pair,
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


def make_expiry_leg(spot: float, expiry: date, dte: int, atm_iv: float,
                     strikes: list[float] = None) -> list[OptionRow]:
    """A small ATM-centered strike ladder for one expiry, each leg's settle
    price back-solved from a single known IV (both call and put), so
    compute_term_structure_for_date's recovered ATM IV can be checked
    against a known value."""
    if strikes is None:
        strikes = [round(spot * m / 50) * 50 for m in (0.98, 1.00, 1.02)]
    rows = []
    for k in strikes:
        rows.append(make_row(expiry, k, OptionType.PUT,
                              _theo_price(spot, k, dte, atm_iv, OptionType.PUT), spot))
        rows.append(make_row(expiry, k, OptionType.CALL,
                              _theo_price(spot, k, dte, atm_iv, OptionType.CALL), spot))
    return rows


def make_two_expiry_chain(spot: float, front_expiry: date, front_dte: int, front_iv: float,
                           back_expiry: date, back_dte: int, back_iv: float) -> list[OptionRow]:
    return (make_expiry_leg(spot, front_expiry, front_dte, front_iv)
            + make_expiry_leg(spot, back_expiry, back_dte, back_iv))


# ─── select_expiry_pair ──────────────────────────────────────────────────────

def test_select_expiry_pair_skips_near_dated_and_orders_front_back():
    trade_date = date(2026, 7, 22)
    expiries = [date(2026, 7, 23), date(2026, 7, 28), date(2026, 8, 25)]
    assert select_expiry_pair(expiries, trade_date) == (date(2026, 7, 28), date(2026, 8, 25))


def test_select_expiry_pair_exact_min_dte_boundary_included():
    trade_date = date(2026, 7, 22)
    e1 = trade_date + timedelta(days=MIN_DTE)
    e2 = trade_date + timedelta(days=MIN_DTE + 30)
    assert select_expiry_pair([e1, e2], trade_date) == (e1, e2)


def test_select_expiry_pair_none_when_fewer_than_two_qualify():
    trade_date = date(2026, 7, 22)
    # One too-near (excluded), one qualifying -- only 1 usable expiry.
    expiries = [trade_date + timedelta(days=1), trade_date + timedelta(days=10)]
    assert select_expiry_pair(expiries, trade_date) is None
    assert select_expiry_pair([], trade_date) is None


# ─── select_atm_row ──────────────────────────────────────────────────────────

def test_select_atm_row_picks_nearest_to_spot():
    expiry = date(2026, 8, 1)
    rows = [make_row(expiry, k, OptionType.CALL, 10.0) for k in (23800, 23950, 24100, 24500)]
    assert select_atm_row(rows, 24000.0, OptionType.CALL).strike == 23950


def test_select_atm_row_tiebreak_prefers_lower_strike():
    expiry = date(2026, 8, 1)
    rows = [make_row(expiry, 23950, OptionType.PUT, 10.0),
            make_row(expiry, 24050, OptionType.PUT, 10.0)]
    assert select_atm_row(rows, 24000.0, OptionType.PUT).strike == 23950


def test_select_atm_row_none_when_no_candidates_of_type():
    expiry = date(2026, 8, 1)
    rows = [make_row(expiry, 24000, OptionType.CALL, 10.0)]
    assert select_atm_row(rows, 24000.0, OptionType.PUT) is None


# ─── _within_atm_tolerance ────────────────────────────────────────────────────

def test_atm_tolerance_boundaries():
    spot = 24000.0
    expiry = date(2026, 8, 1)
    on_target = make_row(expiry, spot, OptionType.CALL, 10.0)
    assert _within_atm_tolerance(on_target, spot)
    at_edge = make_row(expiry, spot * 1.015, OptionType.CALL, 10.0)  # exactly 1.5% away
    assert _within_atm_tolerance(at_edge, spot)
    outside = make_row(expiry, spot * 1.03, OptionType.CALL, 10.0)  # 3% away
    assert not _within_atm_tolerance(outside, spot)


# ─── compute_term_structure_for_date ─────────────────────────────────────────

def test_compute_term_structure_recovers_known_spread():
    trade_date = date(2026, 7, 22)
    front_expiry, back_expiry = date(2026, 7, 29), date(2026, 8, 26)  # DTE 7 / 35
    spot = 24000.0
    rows = make_two_expiry_chain(spot, front_expiry, 7, 0.22, back_expiry, 35, 0.15)
    got_spot, spread, reason = compute_term_structure_for_date(rows, trade_date)
    assert reason == ""
    assert got_spot == spot
    assert spread == pytest.approx(0.07, abs=0.01)  # front_iv - back_iv, backwardation


def test_compute_term_structure_no_rows():
    assert compute_term_structure_for_date([], date(2026, 7, 22)) == (None, None, "no_rows")


def test_compute_term_structure_no_underlying_close():
    rows = [OptionRow(expiry=date(2026, 8, 1), strike=24000, option_type=OptionType.CALL,
                       settle_price=10.0, underlying_close=None)]
    spot, spread, reason = compute_term_structure_for_date(rows, date(2026, 7, 22))
    assert (spot, spread, reason) == (None, None, "no_underlying_close")


def test_compute_term_structure_insufficient_expiries():
    trade_date = date(2026, 7, 22)
    # Only one expiry listed at all.
    rows = [make_row(trade_date + timedelta(days=10), 24000, OptionType.CALL, 10.0)]
    spot, spread, reason = compute_term_structure_for_date(rows, trade_date)
    assert reason == "insufficient_expiries"


def test_compute_term_structure_front_moneyness_tolerance_skip():
    trade_date = date(2026, 7, 22)
    front_expiry, back_expiry = date(2026, 7, 29), date(2026, 8, 26)
    spot = 24000.0
    # Front expiry only has strikes way outside the 1.5% ATM band.
    front_rows = [make_row(front_expiry, spot * 0.80, OptionType.CALL, 10.0, spot),
                  make_row(front_expiry, spot * 0.80, OptionType.PUT, 10.0, spot)]
    back_rows = make_expiry_leg(spot, back_expiry, 35, 0.15)
    _, spread, reason = compute_term_structure_for_date(front_rows + back_rows, trade_date)
    assert spread is None
    assert reason == "front_moneyness_tolerance"


def test_compute_term_structure_back_iv_fallback_skip():
    trade_date = date(2026, 7, 22)
    front_expiry, back_expiry = date(2026, 7, 29), date(2026, 8, 26)
    spot = 24000.0
    front_rows = make_expiry_leg(spot, front_expiry, 7, 0.22)
    back_rows = [make_row(back_expiry, spot, OptionType.CALL, 0.0, spot),  # price 0 -> fallback
                 make_row(back_expiry, spot, OptionType.PUT, 50.0, spot)]
    _, spread, reason = compute_term_structure_for_date(front_rows + back_rows, trade_date)
    assert spread is None
    assert reason == "back_iv_fallback_call"


# ─── compute_daily_series: windowing + no lookahead ─────────────────────────

def _build_rows_by_date(n_days: int, spot_path: list[float], front_iv=0.18, back_iv=0.16,
                         start=date(2026, 1, 5)) -> dict:
    rows_by_date = {}
    d = start
    for i in range(n_days):
        front_expiry = d + timedelta(days=10)
        back_expiry = d + timedelta(days=40)
        rows_by_date[d] = make_two_expiry_chain(
            spot_path[i], front_expiry, 10, front_iv, back_expiry, 40, back_iv)
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    return rows_by_date


def test_compute_daily_series_skips_days_before_rv_window():
    from scripts.validate_vol_spread_signal import RV_WINDOW
    spot_path = [24000.0 + i for i in range(60)]
    rows_by_date = _build_rows_by_date(60, spot_path)
    days = compute_daily_series(rows_by_date)
    dates_sorted = sorted(rows_by_date)
    assert days[0].date == dates_sorted[RV_WINDOW]


def test_compute_daily_series_fwd_rv_none_near_series_end():
    from scripts.validate_vol_spread_signal import RV_WINDOW
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
        assert match.spread == pytest.approx(d.spread)
        assert match.rv_trailing == pytest.approx(d.rv_trailing)


def test_compute_daily_series_records_skip_reason():
    trade_date = date(2026, 1, 5)
    rows_by_date = _build_rows_by_date(30, [24000.0] * 30, start=trade_date)
    # Break one mid-series day so it has only one listed expiry.
    broken_date = sorted(rows_by_date)[22]
    rows_by_date[broken_date] = [make_row(broken_date + timedelta(days=10), 24000,
                                           OptionType.CALL, 10.0, 24000.0)]
    days = compute_daily_series(rows_by_date)
    broken_day = next(d for d in days if d.date == broken_date)
    assert broken_day.spread is None
    assert broken_day.skip_reason == "insufficient_expiries"


# ─── summarize ────────────────────────────────────────────────────────────────

def _ts_day(offset, spread, fwd_rv, skip_reason=""):
    return TermStructureDay(date=date(2026, 1, 5) + timedelta(days=offset), spot=24000.0,
                             spread=spread, skip_reason=skip_reason, rv_trailing=15.0, fwd_rv=fwd_rv)


def test_summarize_monotonic_case_passes():
    days = [_ts_day(i, spread=-10 + i, fwd_rv=10.0 + i) for i in range(20)]
    report = summarize(days, "NIFTY")
    assert "PASS" in report
    assert "Q1" in report and "Q5" in report


def test_summarize_flat_case_fails():
    days = [_ts_day(i, spread=-10 + i, fwd_rv=15.0) for i in range(20)]
    report = summarize(days, "NIFTY")
    assert "FAIL" in report


def test_summarize_reports_skip_reasons():
    days = [_ts_day(i, spread=-10 + i, fwd_rv=10.0 + i) for i in range(20)]
    days.append(_ts_day(20, spread=None, fwd_rv=None, skip_reason="insufficient_expiries"))
    report = summarize(days, "BANKNIFTY")
    assert "insufficient_expiries" in report
    assert "# BANKNIFTY ATM IV Term Structure Validation" in report


def test_summarize_no_scored_days():
    report = summarize([_ts_day(0, spread=None, fwd_rv=None, skip_reason="no_rows")], "NIFTY")
    assert "No days scored" in report
