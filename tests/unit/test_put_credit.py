"""core/surge/put_credit.py -- Black-76 round trip, strike choice by delta, the exit walk and marks."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from core.surge.put_credit import (
    Calendar, b76, b76_delta, b76_iv, choose_strikes, marks_for, walk, years,
)

D = date(2025, 3, 3)
E = date(2025, 3, 27)


def test_iv_round_trip_and_delta_signs():
    F, K, T, v = 1000.0, np.array([900.0, 1000.0, 1100.0]), 0.08, 0.35
    for put in (True, False):
        p = b76(F, K, T, v, put)
        assert np.allclose(b76_iv(p, F, K, T, put), v, atol=1e-6)
    assert (b76_delta(F, K, T, v, True) < 0).all() and (b76_delta(F, K, T, v, False) > 0).all()
    assert np.isnan(b76_iv(np.array([50.0]), 1000.0, 1100.0, T, True))[0]       # below intrinsic


def test_choose_strikes_by_delta():
    F, T = 1000.0, years(D, E)
    ks = np.arange(800.0, 1001.0, 10.0)
    chain = pd.DataFrame({"strike": ks, "close": b76(F, ks, T, 0.40, True), "contracts": 10.0})
    s, lo = choose_strikes(chain, F, D, E)
    ds = -b76_delta(F, np.array([s["strike"], lo["strike"]]), T, 0.40, True)
    assert 0.30 <= ds[0] <= 0.40 and 0.10 <= ds[1] <= 0.15 and lo["strike"] < s["strike"]


def test_walk_take_profit_stop_and_time():
    days = [D + timedelta(days=i) for i in range(0, 30) if (D + timedelta(days=i)).weekday() < 5]
    cal = Calendar(days)

    def rows(vs):    # short value path, long stays 1.0
        out = {}
        for d, v in zip(days, vs):
            out[(d, 950.0)] = (v, v, 5)
            out[(d, 900.0)] = (1.0, 1.0, 5)
        return out
    credit = 9.0                                                     # 10 - 1
    ex, vals, why, _ = walk("X", days[0], E, 950.0, 900.0, credit, 100, rows([10, 8, 5.4, 3]), {}, cal)
    assert why == "take profit" and ex == days[2]                   # value 4.4 <= 4.5
    ex, vals, why, _ = walk("X", days[0], E, 950.0, 900.0, credit, 100, rows([10, 15, 24]), {}, cal)
    assert why == "stop" and ex == days[2]                          # value 23 >= 22.5
    ex, vals, why, _ = walk("X", days[0], E, 950.0, 900.0, credit, 100, rows([10] * len(days)), {}, cal)
    assert why == "time" and ex == max(d for d in days if d < E)


def test_marks_net_of_costs():
    vals = {D: (10.0, 1.0), D + timedelta(days=1): (5.0, 0.5)}
    m = marks_for(D, 9.0, 50.0, 100, 10.0, 1.0, vals, 0.02)
    assert m[D] < 0                                                  # closing at once costs money
    assert 0 < m[D + timedelta(days=1)] < 4.5 / 41.0                 # gross 4.5 on risk 41, less costs
