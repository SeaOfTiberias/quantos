"""CCI + monthly CPR pre-registration (2026-11-07), Part A building blocks, on synthetic bars."""

import numpy as np
import pandas as pd
import pytest

from core.backtest import cci_cpr as m
from core.techno_funda.prices import wilder_rsi as panel_rsi


def _naive_cci(h, l, c, n):
    tp = (h + l + c) / 3
    out = np.full(len(tp), np.nan)
    for i in range(n - 1, len(tp)):
        w = tp[i - n + 1:i + 1]
        mu = w.mean()
        md = np.abs(w - mu).mean()
        out[i] = (tp[i] - mu) / (0.015 * md) if md else 0.0
    return out


def test_cci_matches_the_formula():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 120))
    h, l = c + rng.uniform(0, 2, 120), c - rng.uniform(0, 2, 120)
    got, want = m.cci(h, l, c), _naive_cci(h, l, c, 34)
    assert np.isnan(got[:33]).all()
    np.testing.assert_allclose(got[33:], want[33:], rtol=1e-10)


def test_rsi_matches_the_panel_rsi():
    c = 100 + np.cumsum(np.random.default_rng(2).normal(0, 1, 80))
    np.testing.assert_allclose(m.wilder_rsi(c), panel_rsi(pd.Series(c)).to_numpy(), equal_nan=True)


def test_cpr_values_hdfcbank_october_2026():
    bc, p, tc = m.cpr_values(734.90, 669.20, 692.80)
    assert round(bc, 2) == 702.05 and round(p, 2) == 698.97 and round(tc, 2) == 695.88


def test_monthly_cpr_uses_the_previous_calendar_month():
    dates = pd.to_datetime(["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-11-02"])
    h = np.array([110.0, 120.0, 200.0, 210.0, 300.0])
    l = np.array([90.0, 100.0, 150.0, 160.0, 250.0])
    c = np.array([100.0, 115.0, 180.0, 170.0, 280.0])
    top, bot = m.monthly_cpr(dates.to_numpy(), h, l, c)
    assert np.isnan(top[0]) and np.isnan(top[1])                     # no August bars
    bc, p, tc = m.cpr_values(120, 90, 115)                            # September
    assert top[2] == top[3] == pytest.approx(max(bc, tc)) and bot[2] == pytest.approx(min(bc, tc))
    bc, p, tc = m.cpr_values(210, 150, 170)                           # October
    assert top[4] == pytest.approx(max(bc, tc))


def test_monthly_cpr_skips_a_missing_month():
    dates = pd.to_datetime(["2026-08-31", "2026-10-01"])
    top, _ = m.monthly_cpr(dates.to_numpy(), np.array([10.0, 11]), np.array([9.0, 10]), np.array([9.5, 10.5]))
    assert np.isnan(top[1])                                           # September missing -> no CPR


def test_cci_crosses_up_and_down():
    cci = np.array([-50, -10, 5, 20, -5, -30], float)
    avg = np.zeros(6)
    assert list(m.cci_crosses(cci, avg, 1)) == [2]
    assert list(m.cci_crosses(cci, avg, -1)) == [4]


def test_slope_tolerance():
    avg = np.array([0, 0, 0, 0, 0, -5, -5.01], float)
    assert m.slope_ok(avg, 5, 1)                  # -5 vs 0: exactly at the limit, flat
    assert not m.slope_ok(np.r_[0.0, avg], 7, 1)   # -5.01 vs 0: falling
    assert m.slope_ok(np.array([0, 0, 0, 0, 0, 5.0]), 5, -1)
    assert not m.slope_ok(np.array([0, 0, 0, 0, 0, 5.01]), 5, -1)
    assert not m.slope_ok(avg, 4, 1)              # not enough history


def test_cpr_cross_needs_a_real_cross_not_a_month_change():
    s5 = np.array([100.0, 100.0, 100.0, 103.0])
    top = np.array([101.0, 101.0, 99.0, 99.0])    # month change at index 2 drops the CPR under price
    assert list(m.cpr_crosses(s5, top, top, 1)) == []
    top2 = np.array([101.0, 101.0, 101.0, 101.0])
    assert list(m.cpr_crosses(s5, top2, top2, 1)) == [3]
    bot = np.array([99.0, 99.0, 99.0, 99.0])
    assert list(m.cpr_crosses(np.array([100.0, 100, 98, 97]), bot, bot, -1)) == [2]


def test_pair_window_and_signal_day():
    assert list(m.pair(np.array([10]), np.array([13]))) == [13]
    assert list(m.pair(np.array([10]), np.array([7]))) == [10]
    assert list(m.pair(np.array([10]), np.array([14, 6]))) == []


def test_skip_rule_counts_only_kept_signals():
    assert m.apply_skip([27, 5, 10, 15, 16]) == [5, 16, 27]


def test_candidate_days_runs_on_a_long_series():
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2020-01-01", periods=400).to_numpy()
    c = 100 + np.cumsum(rng.normal(0, 1.5, 400))
    h, l = c + 1, c - 1
    out = m.candidate_days(h, l, c, dates)
    assert set(out) == {(a, s) for a in m.ARMS for s in (1, -1)}
    # the full rule is a subset of the no-slope rule
    assert set(out[("full", 1)]) <= set(out[("no_slope", 1)])
    assert all(d >= 34 + 52 - 1 for d in out[("cci_only", 1)])
