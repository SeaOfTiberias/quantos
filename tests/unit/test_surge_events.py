"""Unit tests for core/surge/events.py (docs/SURGE_DIRECTION_METHODOLOGY.md)."""

from datetime import date, timedelta

import numpy as np
import pytest

from core.pairs.backtest import FuturesDay
from core.statarb.residuals import build_panel
from core.surge.events import (
    HISTORY, SurgeEvent, find_events, judge, results_rows, split, stats,
)


def _days(n, start=date(2020, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _series(prices, days):
    return [FuturesDay(d, p, 1, date(2099, 1, 1), adj_close=p) for d, p in zip(days, prices)]


def _flat_panel(n_sym=4, n=HISTORY + 60, shocks=None):
    """Flat 100 prices; shocks = {(symbol_index, row): multiplier applied from that row on}."""
    days = _days(n)
    series = {}
    for j in range(n_sym):
        p = np.full(n, 100.0)
        for (sj, row), mult in (shocks or {}).items():
            if sj == j:
                p[row:] *= mult
        series[f"S{j}"] = _series(p, days)
    return build_panel(series), days


def test_detects_surge_and_excess():
    t = HISTORY + 10
    panel, _ = _flat_panel(shocks={(0, t): 1.06, (0, t + 5): 1.02})
    events, _ = find_events(panel, {})
    assert [(e.symbol, e.t) for e in events] == [("S0", t)]
    e = events[0]
    assert e.surge == pytest.approx(0.06)
    assert e.raw[5] == pytest.approx(0.02)
    assert e.excess[5] == pytest.approx(0.02)  # peers flat
    assert e.raw[3] == pytest.approx(0.0)


def test_conditions():
    t = HISTORY + 10
    panel, _ = _flat_panel(shocks={(0, t): 1.08})
    (e,) = find_events(panel, {})[0]
    assert e.cond["breakout52"] is True
    assert e.cond["big_z"] is True        # flat history -> zero sd
    assert e.cond["market_day"] is True   # 8% on one of 4 names lifts the EW average to 2%
    assert e.cond["extended"] is False


def test_cooldown_and_history_exclusions():
    t = HISTORY + 10
    panel, _ = _flat_panel(shocks={(0, t): 1.06, (0, t + 4): 1.06, (1, 50): 1.06})
    events, excl = find_events(panel, {})
    assert [(e.symbol, e.t) for e in events] == [("S0", t)]
    assert excl.cooldown == 1 and excl.history == 1


def test_forward_window_and_corp_action():
    n = HISTORY + 60
    panel, _ = _flat_panel(n=n, shocks={(0, n - 3): 1.06, (1, HISTORY + 10): 1.06, (1, HISTORY + 12): 0.4})
    events, excl = find_events(panel, {})
    assert events == []
    assert excl.forward == 1 and excl.corp_action == 1


def test_results_rows_window():
    days = _days(10)
    panel = build_panel({"A": _series([100.0] * 10, days)})
    sat = days[4] + timedelta(days=(5 - days[4].weekday()) % 7 or 7)  # a weekend day
    rows = results_rows(panel, {"A": [days[2], sat]})["A"]
    assert {2, 3} <= rows                                   # meeting day and the next session
    assert days.index(min(d for d in days if d > sat)) in rows   # weekend meeting -> next session


def _ev(t, d, x):
    return SurgeEvent("S", t, d, 0.06, {h: x for h in (1, 3, 5, 8, 10)}, {h: x for h in (1, 3, 5, 8, 10)},
                      {c: True for c in ("results", "breakout52", "big_z", "market_day", "extended")})


def test_stats_clusters_by_date():
    d = date(2024, 1, 1)
    evs = [_ev(1, d, 0.10), _ev(1, d, 0.10), _ev(2, d + timedelta(1), -0.02)]
    s = stats(evs)
    assert s.n == 3 and s.n_dates == 2
    assert s.clustered_mean == pytest.approx(0.04)   # (0.10 + -0.02) / 2, not the event mean
    assert s.event_mean == pytest.approx(0.06)


def test_split_never_breaks_a_date():
    base = date(2024, 1, 1)
    evs = [_ev(i, base + timedelta(i // 2), 0.01) for i in range(10)]
    m, h, cut = split(evs)
    assert {e.day for e in m}.isdisjoint({e.day for e in h})
    assert all(e.day >= cut for e in h)


def test_judge_requires_holdout_confirmation():
    rng = np.random.default_rng(0)
    base = date(2020, 1, 1)
    mining = [_ev(i, base + timedelta(i), 0.01 + rng.normal(0, 0.005)) for i in range(60)]
    good = [_ev(100 + i, base + timedelta(100 + i), 0.01 + rng.normal(0, 0.005)) for i in range(40)]
    bad = [_ev(100 + i, base + timedelta(100 + i), -0.01 + rng.normal(0, 0.005)) for i in range(40)]
    assert judge("x", mining, good).passed
    r = judge("x", mining, bad)
    assert not r.passed and "holdout" in r.reason
    assert not judge("x", mining[:20], good).passed
