"""scripts/backtest_alpha50.py -- synthetic data only (docs/ALPHA50_REBUILD_PREREG_2026-11-27.md)."""

import random
from datetime import date, timedelta

import pytest

from scripts import backtest_alpha50 as ab


def weekdays(a, b):
    d, out = a, []
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_expiry_and_review_dates():
    s = weekdays(date(2017, 1, 1), date(2017, 12, 31))
    assert ab.expiry_day(s, 2017, 3) == date(2017, 3, 30)               # last Thursday
    s2 = [d for d in s if d != date(2017, 3, 30)]                       # a holiday on the Thursday
    assert ab.expiry_day(s2, 2017, 3) == date(2017, 3, 29)
    assert ab.expiry_day(s, 2017, 12) == date(2017, 12, 28)
    r = ab.reviews(s, 2017, date(2017, 12, 31))
    assert r[0] == (date(2017, 2, 28), date(2017, 3, 30))
    assert [c.month for c, _ in r] == [2, 5, 8, 11] and [e.month for _, e in r] == [3, 6, 9, 12]


def test_ols_alpha_recovers_a_known_line():
    rng = random.Random(1)
    m = [rng.gauss(0, 0.01) for _ in range(252)]
    r = [0.0004 + 1.3 * x for x in m]
    a, b = ab.ols_alpha(r, m)
    assert b == pytest.approx(1.3) and a == pytest.approx(0.0004 * 252)


def test_selection_keeps_buffer_members_and_drops_negative_alpha():
    al = {f"S{i:03d}": 1.0 - i / 100 for i in range(150)}               # S000 best ... S100 = 0, then negative
    existing = {"S070", "S099", "S120", "S010"}
    names = ab.select(al, existing, n=50, buffer=100)
    assert len(names) == 50
    assert "S070" in names and "S010" in names                          # ranked inside 100: kept
    assert "S120" not in names                                          # negative alpha: never kept
    assert "S099" in names                                              # rank 100 (index 99): still inside the buffer
    assert names[:3] == ["S010", "S070", "S099"]                       # kept first, then the fill
    assert ab.select({"A": -1.0}, {"X"}) == ["X"]                       # no positive alpha: keep existing


def test_alpha_weights_sum_to_one_and_follow_alpha():
    w = ab.alpha_weights(["A", "B"], {"A": 0.3, "B": 0.1})
    assert w == pytest.approx({"A": 0.75, "B": 0.25})


def test_eligibility_order_listing_and_frequency():
    sessions = weekdays(date(2015, 1, 1), date(2017, 2, 28))
    def b(vals, start=sessions[0], skip=()):
        return {d: {"c": 100, "val": vals} for d in sessions if d >= start and d not in skip}
    bars = {"BIG": b(100), "NEW": b(500, start=date(2016, 9, 1)), "GAP": b(400, skip={date(2016, 6, 1)}),
            "MID": b(50), "TINY": b(1)}
    out = ab.eligible(bars, sessions, date(2017, 2, 28), top=4)
    assert out == ["BIG", "MID"]       # top 4 by value = NEW, GAP, BIG, MID; NEW too young, GAP missed a day


def test_window_alpha_needs_coverage_and_skips_months():
    sessions = weekdays(date(2015, 1, 1), date(2017, 2, 28))
    rng = random.Random(2)
    mkt, px, lvl = {}, {}, 100.0
    for d in sessions:
        r = rng.gauss(0, 0.01)
        lvl *= 1 + r
        mkt[d] = lvl
    p = 100.0
    prev = None
    for d in sessions:
        if prev:
            p *= 1 + 0.001 + (mkt[d] / mkt[prev] - 1)
        px[d] = {"c": p}
        prev = d
    a, beta = ab.window_alpha(px, mkt, sessions, date(2017, 2, 28), ab.Version(1, 12))
    assert beta == pytest.approx(1.0, abs=1e-6) and a == pytest.approx(0.001 * 252, rel=0.01)
    holey = {d: x for i, (d, x) in enumerate(px.items()) if i % 10}     # 90% coverage
    assert ab.window_alpha(holey, mkt, sessions, date(2017, 2, 28), ab.BASE) is None


def test_walk_costs_lots_and_filter():
    sessions = weekdays(date(2016, 1, 1), date(2017, 12, 29))
    close = {"A": {d: 100.0 * (1.001 ** i) for i, d in enumerate(sessions)},
             "B": {d: 50.0 for d in sessions}}
    last = {"A": sessions[-1], "B": sessions[-1]}
    eff = date(2017, 3, 30)
    targets = [(eff, {"A": 0.5, "B": 0.5})]
    n500 = [(d, 1000.0) for d in sessions]
    w = ab.walk(ab.BASE, sessions, close, last, targets, n500, 0.0, date(2017, 3, 31), date(2017, 12, 29))
    v0 = w["values"][0][1]
    assert v0 == pytest.approx(ab.CAPITAL * (0.5 * 1.001 + 0.5))     # one day of A's drift
    wc = ab.walk(ab.BASE, sessions, close, last, targets, n500, 0.001, date(2017, 3, 31), date(2017, 12, 29))
    assert wc["cost"] == pytest.approx(ab.CAPITAL * 0.001, rel=0.01)  # one full buy at 10 bps
    # filter: NIFTY 500 drops below its SMA at a month-end -> all cash, cost charged, value frozen
    n500b = [(d, 1000.0 if d < date(2017, 6, 1) else 1000.0 - 2.0 * (d - date(2017, 6, 1)).days) for d in sessions]
    wf = ab.walk(ab.Version(0, 12, 20), sessions, close, last, targets, n500b, 0.0, date(2017, 3, 31), date(2017, 12, 29))
    assert wf["switches"][0][0] == date(2017, 6, 30) and wf["switches"][0][1] == "out"
    tail = [x for d, x in wf["values"] if d > date(2017, 6, 30)]
    assert max(tail) == pytest.approx(min(tail))                      # flat in cash
    assert wf["in_cash_days"] > 100


def test_delisted_holding_is_sold_and_spread():
    sessions = weekdays(date(2017, 3, 1), date(2017, 6, 30))
    close = {"A": {d: 100.0 for d in sessions}, "B": {d: 100.0 for d in sessions if d <= date(2017, 4, 28)}}
    last = {"A": sessions[-1], "B": date(2017, 4, 28)}
    w = ab.walk(ab.BASE, sessions, close, last, [(date(2017, 3, 30), {"A": 0.5, "B": 0.5})],
                [(d, 1.0) for d in sessions], 0.0, date(2017, 3, 31), date(2017, 6, 30))
    assert w["values"][-1][1] == pytest.approx(ab.CAPITAL)


def test_tax_lots_split_short_and_long():
    bk = ab.Book(cash=1000.0)
    bk._buy("A", 1000.0, 10.0, date(2017, 1, 2), 0.0)
    bk._sell("A", 50.0, 10.0, date(2017, 6, 1), 0.0)
    bk._sell("A", 50.0, 12.0, date(2018, 1, 5), 0.0)
    assert bk.sold_short == pytest.approx(500.0) and bk.sold_long == pytest.approx(600.0)


def test_stats():
    v = [(date(2017, 1, 1), 100.0), (date(2018, 1, 1), 120.0), (date(2019, 1, 1), 90.0), (date(2020, 1, 1), 121.0)]
    assert ab.max_drawdown(v) == pytest.approx(-0.25)
    assert ab.cagr(v) == pytest.approx(1.21 ** (1 / ((date(2020, 1, 1) - date(2017, 1, 1)).days / 365.25)) - 1)
    rng = random.Random(3)
    base = [rng.gauss(0.01, 0.05) for _ in range(80)]
    better = [x + 0.01 for x in base]
    assert ab.block_bootstrap_share(better, base, boot=500) > 0.99
    assert ab.block_bootstrap_share(base, better, boot=500) < 0.01


def test_correlation():
    assert ab.correlation([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert ab.correlation([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert ab.correlation([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)


def test_grid_is_twelve_versions_without_the_base():
    assert len(ab.GRID) == 12 and ab.BASE not in ab.GRID
