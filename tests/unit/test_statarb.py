"""Unit tests for core/statarb (docs/STATARB_BANKNIFTY_METHODOLOGY.md)."""

import io
import math
import zipfile
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from core.pairs.backtest import FuturesDay
from core.statarb.backtest import calibrate, compute_scores, simulate
from core.statarb.data import parse_legacy_near_month, reaction_day_index
from core.statarb.residuals import (
    PCA_WINDOW, build_panel, ou_fit, pca_weights, regress, score,
)


def _ou_increments(n, b, sigma, seed):
    """Residual increments whose cumulative sum is an AR(1) with slope b."""
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for k in range(1, n):
        x[k] = b * x[k - 1] + rng.normal(0, sigma)
    return np.diff(np.concatenate([[0.0], x]))


class TestOUFit:
    def test_recovers_fast_mean_reversion(self):
        fits = [ou_fit(_ou_increments(60, 0.8, 0.01, seed)) for seed in range(50)]
        taus = [f.tau_days for f in fits if f]
        # true tau = -1/ln(0.8) ~ 4.5 days; AR(1) slope is biased down on 60 obs
        assert np.median(taus) < 8
        assert sum(f.speed_ok for f in fits if f) > 40

    def test_speed_filter_prefers_ou_over_random_walk(self):
        # Weak by construction: AR(1) slope on 60 obs is biased down, so most
        # random walks still pass tau < 30 (~65% here). Only relative
        # discrimination is asserted -- see the results doc's disclosure.
        rng = np.random.default_rng(1)
        rw = [ou_fit(rng.normal(0, 0.01, 60)) for _ in range(200)]
        ou = [ou_fit(_ou_increments(60, 0.8, 0.01, s)) for s in range(200)]
        rate = lambda fits: sum(1 for f in fits if f and f.speed_ok) / len(fits)  # noqa: E731
        assert rate(ou) > rate(rw) + 0.2

    def test_s_sign_follows_displacement(self):
        eps = _ou_increments(60, 0.7, 0.01, 3)
        eps[-1] += 0.08  # stock jumps above its family at the end
        fit = ou_fit(eps)
        assert fit is not None and fit.s > 1.0

    def test_non_reverting_slope_returns_none(self):
        assert ou_fit(np.full(60, 0.01)) is None  # X strictly trending, b ~ 1


def test_regress_recovers_beta():
    rng = np.random.default_rng(0)
    f = rng.normal(0, 0.01, 200)
    y = 0.0005 + 1.3 * f + rng.normal(0, 0.001, 200)
    alpha, betas, resid = regress(y, f[:, None])
    assert betas[0] == pytest.approx(1.3, abs=0.05)
    assert abs(resid.mean()) < 1e-12


def test_pca_weights_sign_is_deterministic():
    rng = np.random.default_rng(0)
    common = rng.normal(0, 0.01, (252, 1))
    rets = common + rng.normal(0, 0.005, (252, 6))
    w1 = pca_weights(rets)
    assert w1[:, 0].sum() > 0 and w1[:, 1].sum() > 0


def _trading_days(n, start=date(2020, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _synthetic_series(n_days=PCA_WINDOW + 120, n_stocks=6, seed=0, shock=None):
    """Family factor + idiosyncratic OU residuals. shock=(stock, day, size)
    adds a one-day residual displacement that then reverts."""
    rng = np.random.default_rng(seed)
    days = _trading_days(n_days)
    fam = rng.normal(0, 0.012, n_days)
    out = {}
    for i in range(n_stocks):
        x = np.zeros(n_days)
        for k in range(1, n_days):
            x[k] = 0.75 * x[k - 1] + rng.normal(0, 0.004)
            if shock and shock[0] == i and k == shock[1]:
                x[k] += shock[2]
        logp = np.cumsum(fam) + x + math.log(100)
        expiry = lambda d: date(d.year, d.month, 25) if d.day <= 25 else (  # noqa: E731
            date(d.year + (d.month == 12), d.month % 12 + 1, 25))
        out[f"S{i}"] = [FuturesDay(d, float(np.exp(lp)), 100, expiry(d), adj_close=float(np.exp(lp)))
                        for d, lp in zip(days, logp)]
    return out


class TestScoring:
    def test_leave_one_out_peers_and_hedge(self):
        panel = build_panel(_synthetic_series())
        t = len(panel.dates) - 1
        sc = score(panel, t, 0, "M1")
        assert 0 not in sc.peer_idx and len(sc.peer_idx) == 5
        assert sum(sc.hedge) == pytest.approx(sc.betas[0])
        assert sc.betas[0] == pytest.approx(1.0, abs=0.25)

    def test_m2_hedge_is_linear_in_peer_weights(self):
        panel = build_panel(_synthetic_series())
        sc = score(panel, len(panel.dates) - 1, 2, "M2")
        assert len(sc.betas) == 2 and len(sc.hedge) == 5

    def test_short_history_excluded(self):
        panel = build_panel(_synthetic_series())
        assert score(panel, 10, 0, "M1").excluded == "insufficient_history"

    def test_corp_action_jump_excluded(self):
        series = _synthetic_series()
        s0 = series["S0"]
        series["S0"] = s0[:-5] + [FuturesDay(d.trade_date, d.close / 2.5, d.lot_size, d.expiry,
                                             adj_close=d.adj_close / 2.5) for d in s0[-5:]]
        panel = build_panel(series)
        assert score(panel, len(panel.dates) - 1, 0, "M1").excluded == "corp_action_jump"


class TestSimulation:
    def test_shock_triggers_short_that_reverts(self):
        day = PCA_WINDOW + 60
        panel = build_panel(_synthetic_series(shock=(1, day, 0.06)))
        start = PCA_WINDOW + 1
        scores = compute_scores(panel, "M1", start)
        assert scores[day][1].s > 1.25
        trades = [t for t in simulate(panel, scores, start, {}) if t.symbol == "S1"]
        hit = [t for t in trades if t.signal_date == panel.dates[day]]
        assert hit and hit[0].side == "SHORT"
        assert hit[0].entry_date == panel.dates[day + 1]  # filled next close
        assert hit[0].gross_pnl > 0

    def test_results_blackout_blocks_entry(self):
        day = PCA_WINDOW + 60
        panel = build_panel(_synthetic_series(shock=(1, day, 0.06)))
        start = PCA_WINDOW + 1
        scores = compute_scores(panel, "M1", start)
        trades = simulate(panel, scores, start, {"S1": {day + 2}})
        assert not [t for t in trades if t.symbol == "S1" and t.signal_date == panel.dates[day]]

    def test_calibration_runs(self):
        panel = build_panel(_synthetic_series())
        start = PCA_WINDOW + 1
        cal = calibrate(panel, compute_scores(panel, "M1", start), start)
        assert sum(n for n, _ in cal.buckets.values()) > 0


def test_parse_legacy_near_month():
    csv_text = (
        "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,"
        "CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
        "FUTSTK,SBIN,28-Mar-2019,0,XX,1,1,1,281.7,0,0,0,0,0,11-FEB-2019,\n"
        "FUTSTK,SBIN,28-Feb-2019,0,XX,1,1,1,280.45,0,0,0,0,0,11-FEB-2019,\n"
        "FUTIDX,BANKNIFTY,28-Feb-2019,0,XX,1,1,1,27295.9,0,0,0,0,0,11-FEB-2019,\n"
        "OPTSTK,SBIN,28-Feb-2019,300,CE,1,1,1,2.0,0,0,0,0,0,11-FEB-2019,\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fo11FEB2019bhav.csv", csv_text)
    rows = parse_legacy_near_month(buf.getvalue(), date(2019, 2, 11))
    assert set(rows) == {"SBIN"}
    assert rows["SBIN"].close == 280.45
    assert rows["SBIN"].expiry == date(2019, 2, 28)
    assert rows["SBIN"].next_month_close == 281.7


def test_reaction_day_after_close_maps_to_next_session():
    days = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    assert reaction_day_index(datetime(2024, 1, 1, 14, 0), days) == 0
    assert reaction_day_index(datetime(2024, 1, 1, 16, 0), days) == 1
    assert reaction_day_index(datetime(2024, 1, 3, 18, 0), days) is None


class TestNifty50Models:
    def test_pca5_hedge_has_five_betas(self):
        panel = build_panel(_synthetic_series(n_stocks=10))
        sc = score(panel, len(panel.dates) - 1, 0, "PCA5")
        assert len(sc.betas) == 5 and len(sc.hedge) == 9

    def test_mkt_sector_hedge_adds_sector_weight(self):
        panel = build_panel(_synthetic_series(n_stocks=8))
        sectors = {"S0": "a", "S1": "a", "S2": "a", "S3": "b", "S4": "b", "S5": "b"}
        sc = score(panel, len(panel.dates) - 1, 0, "MKT_SECTOR", sectors=sectors)
        assert len(sc.betas) == 2
        b_mkt, b_sec = sc.betas
        h = dict(zip(sc.peer_idx, sc.hedge))
        assert h[1] == pytest.approx(b_mkt / 7 + b_sec / 2)
        assert h[3] == pytest.approx(b_mkt / 7)

    def test_mkt_sector_excludes_lonely_sector(self):
        panel = build_panel(_synthetic_series(n_stocks=6))
        sc = score(panel, len(panel.dates) - 1, 0, "MKT_SECTOR", sectors={"S0": "a", "S1": "a"})
        assert sc.excluded == "no_sector_peers"

    def test_m1_unchanged_with_precomputed_reasons(self):
        from core.statarb.residuals import exclusion_reasons
        panel = build_panel(_synthetic_series())
        t = len(panel.dates) - 1
        assert score(panel, t, 2, "M1") == score(panel, t, 2, "M1", exclusion_reasons(panel, t))


def test_rename_splice(tmp_path, monkeypatch):
    import core.statarb.data as data
    days = _trading_days(4)
    old = [FuturesDay(d, 100.0 + i, 1, date(2020, 1, 30)) for i, d in enumerate(days[:2])]
    new = [FuturesDay(d, 102.0 + i, 1, date(2020, 1, 30)) for i, d in enumerate(days[2:])]
    data._write_panel_cache(tmp_path / "futures_panel_all.csv", {"ZOMATO": old, "ETERNAL": new})
    monkeypatch.setattr(data, "_last_cached_raw_day", lambda _: days[-1])
    out = data.load_futures_panel(["ETERNAL"], days[-1], raw_cache_dir=tmp_path, cache_dir=tmp_path,
                                  allow_network=False)
    assert [d.close for d in out["ETERNAL"]] == [100.0, 101.0, 102.0, 103.0]
