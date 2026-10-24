"""core/fx_coint/model.py -- on synthetic data: a cointegrated pair is found and traded, random walks are not."""

import numpy as np
import pandas as pd

from core.fx_coint.model import fit, run


def frame(eur, gbp):
    idx = pd.bdate_range("2001-01-01", periods=len(eur))
    return pd.DataFrame({"eur": eur, "gbp": gbp, "inr": 80.0, "r_usd": 2.0, "r_eur": 1.0, "r_gbp": 3.0}, index=idx)


def coint_pair(n=900, seed=1):
    rng = np.random.default_rng(seed)
    common = np.cumsum(rng.normal(0, 0.005, n))
    noise = np.zeros(n)
    for t in range(1, n):                                 # AR(1) spread, half-life ~ 7 days
        noise[t] = 0.9 * noise[t - 1] + rng.normal(0, 0.004)
    y = np.log(1.3) + common
    x = np.log(1.1) + 0.8 * common + noise
    return np.exp(x), np.exp(y)


def test_fit_finds_a_cointegrated_pair_and_its_half_life():
    e, g = coint_pair()
    f = fit(np.log(e[-252:]), np.log(g[-252:]))
    assert f.ok and f.trace_ok and f.adf_p < 0.05
    assert -1.0 < f.b < -0.6 and 2 < f.hl < 20


def test_random_walks_are_rejected():
    rng = np.random.default_rng(7)
    x, y = np.cumsum(rng.normal(0, 0.006, 252)), np.cumsum(rng.normal(0, 0.006, 252))
    assert not fit(x, y).ok


def test_run_trades_the_reversion_profitably_before_costs_matter():
    e, g = coint_pair()
    trades, counts = run(frame(e, g), "base")
    assert counts["signals"] == len(trades) and len(trades) > 10
    assert sum(t.ret > 0 for t in trades) / len(trades) > 0.5
    for t in trades:
        assert min(t.marks) == t.entry and max(t.marks) == t.exit and t.margin_per_lot > 0
