"""CCI + monthly CPR runner (scripts/backtest_cci_cpr.py, scripts/backtest_cci_rsi_filters.py): returns,
benchmark, bootstrap, Holm and the filter blocks, on tiny synthetic inputs."""

import numpy as np
import pandas as pd
import pytest

from scripts import backtest_cci_cpr as r
from scripts.backtest_cci_rsi_filters import blocked


def test_forward_return_is_open_to_close_over_h_sessions():
    O = np.array([[100.0], [110.0], [120.0], [130.0]])
    C = np.array([[105.0], [115.0], [125.0], [135.0]])
    F = r.forward(O, C, 2)                      # open of i to close of i+1
    assert F[0, 0] == pytest.approx(15.0) and F[1, 0] == pytest.approx((125 / 110 - 1) * 100)
    assert np.isnan(F[3, 0])


def test_benchmark_uses_next_session_and_signal_day_universe():
    F = np.array([[1.0, 2.0, 3.0], [10.0, 20.0, 99.0], [0.0, 0.0, 0.0]])
    U = np.array([[True, True, False], [True, True, True], [True, True, True]])
    B = r.bench(F, U)
    assert B[0] == pytest.approx(15.0)          # row 1, stocks 0 and 1 (in the universe on day 0)
    assert np.isnan(B[2])                       # no next session


def test_holm_step_down():
    assert r.holm({1: 0.01, -1: 0.04}) == {1: True, -1: True}
    assert r.holm({1: 0.03, -1: 0.04}) == {1: False, -1: False}
    assert r.holm({1: 0.02, -1: 0.30}) == {1: True, -1: False}


def test_bootstrap_is_seeded_and_centred():
    rng = np.random.default_rng(0)
    dates = pd.Series(pd.bdate_range("2020-01-01", periods=400))
    x = rng.normal(1.0, 1.0, 400)
    a, b = r.boot_mean(x, dates), r.boot_mean(x, dates)
    assert a == b
    lo, hi, p = a
    assert lo < x.mean() < hi and p < 0.01
    dlo, dhi = r.boot_diff(x, dates, x - 0.5, dates)
    assert dlo == pytest.approx(0.5) and dhi == pytest.approx(0.5)


def test_summary_halves_split_at_the_median_date():
    t = pd.DataFrame({"date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]),
                      "x": [1.0, 3.0, -1.0, -3.0]})
    s = r.summary(t, "x")
    assert s["n"] == 4 and s["h1"] == 2.0 and s["h2"] == -2.0 and s["win"] == 0.5


def test_filter_blocks_match_the_preregistration():
    assert blocked("cci", (-51.0, 50.0), -1) and not blocked("cci", (-49.0, 50.0), -1)
    assert blocked("cci", (51.0, 50.0), 1) and not blocked("cci", (49.0, 50.0), 1)
    assert blocked("rsi", (0.0, 39.9), -1) and not blocked("rsi", (0.0, 40.0), -1)
    assert blocked("rsi", (0.0, 60.1), 1) and not blocked("rsi", (0.0, 60.0), 1)
