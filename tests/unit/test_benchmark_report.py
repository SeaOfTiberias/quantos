"""core/ops/benchmark.py and core/market_map/index_bars.py benchmark parsing (E4). Synthetic data only."""
from datetime import date, timedelta

import pandas as pd
import pytest

from core.market_map import index_bars as ib
from core.ops import benchmark as bm


def frame(start: date, closes: list[float]) -> pd.DataFrame:
    ds, d = [], start
    while len(ds) < len(closes):
        if d.weekday() < 5:
            ds.append(d)
        d += timedelta(days=1)
    return pd.DataFrame(dict(date=pd.to_datetime(ds), o=closes, h=closes, l=closes, c=closes))


MON = date(2026, 1, 5)                                   # a Monday
IDX = {"NIFTY": frame(MON, [100, 101, 102, 103, 104, 105, 106, 107, 108, 110]),
       "NIFTY200MOM30": frame(MON, [200] * 10)}


def test_index_return_uses_close_before_entry_to_exit_close():
    # entry Wed 01-07 -> previous close Tue 101; exit Fri 01-16 -> 110
    assert bm.index_return(IDX["NIFTY"], date(2026, 1, 7), date(2026, 1, 16)) == pytest.approx(110 / 101 - 1)


def test_index_return_none_before_history():
    assert bm.index_return(IDX["NIFTY"], MON, date(2026, 1, 9)) is None


def test_fund_return_deducts_ter_pro_rata():
    assert bm.fund_return(0.10, date(2026, 1, 1), date(2027, 1, 1), 0.40) == pytest.approx(0.096)
    assert bm.fund_return(None, MON, MON, 0.4) is None


@pytest.mark.parametrize("start,today,n", [
    (date(2026, 7, 27), date(2026, 11, 20), 1),         # 09-30 only
    (date(2026, 9, 30), date(2026, 11, 20), 0),         # the start's own quarter end doesn't count
    (date(2026, 7, 27), date(2027, 6, 30), 4),
    (date(2026, 7, 27), date(2027, 6, 29), 3),
])
def test_quarters_completed(start, today, n):
    assert bm.quarters_completed(start, today) == n


def trades(n):
    return [bm.DarvasTrade("SYN", date(2026, 1, 7), date(2026, 1, 16), 100.0, 110.0) for _ in range(n)]


def test_darvas_locked_never_computes_returns():
    def boom(*_):
        raise AssertionError("net_fn called while locked")
    sec = bm.darvas_section(trades(19), 3, IDX, date(2026, 1, 16), boom)
    assert sec["locked"] and sec["closed"] == 19 and "trades" not in sec and "mean_net" not in sec
    assert sec["index_since_first_entry"]["NIFTY"] is not None        # index-only figure is allowed


def test_darvas_unlocked_excess_per_index():
    sec = bm.darvas_section(trades(20), 0, IDX, date(2026, 1, 16), lambda e, x: x / e - 1)
    assert not sec["locked"] and sec["mean_net"] == pytest.approx(0.10)
    nifty = bm.fund_return(110 / 101 - 1, date(2026, 1, 7), date(2026, 1, 16), bm.FUND_TER["NIFTY"])
    assert sec["mean_excess_NIFTY"] == pytest.approx(0.10 - nifty)
    assert sec["beat_NIFTY200MOM30"] == 20 and sec["n_NIFTY200MOM30"] == 20


def test_momentum_locked_until_four_quarters():
    st = dict(initial_capital=100.0, equity_curve=[dict(date="2026-01-06", equity=100.0),
                                                     dict(date="2026-03-31", equity=150.0)])
    sec = bm.momentum_section(st, IDX, date(2026, 11, 20))
    assert sec["locked"] and sec["quarters"] == 3 and "ret" not in sec


def test_momentum_unlocked_uses_last_mark():
    st = dict(initial_capital=100.0, equity_curve=[dict(date="2026-01-06", equity=100.0),
                                                     dict(date="2026-01-16", equity=120.0)])
    sec = bm.momentum_section(st, IDX, date(2027, 1, 5))
    assert not sec["locked"] and sec["ret"] == pytest.approx(0.20)
    assert sec["NIFTY200MOM30"] == pytest.approx(-0.004 * 10 / 365)   # flat index less TER


def test_render_locked_shows_no_strategy_return():
    rep = dict(as_of="2026-11-20",
               darvas=bm.darvas_section(trades(5), 3, IDX, date(2026, 1, 16), lambda *_: 1 / 0),
               momentum=bm.momentum_section({}, IDX, date(2026, 11, 20)))
    txt = bm.render_text(rep)
    assert "LOCKED" in txt and "mean net" not in txt and "return to" not in txt


FILE = """Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield
Nifty 50,01-09-2020,11464.3,11553.55,11366.9,11470.25,82.75,.73,783769555,36752.54,32.53,3.22,1.45
Nifty200 Momentum 30,01-09-2020,-,-,-,11933.25,273.78,2.35,185311647,14541.07,69.46,6.03,.68
Nifty Midcap150 Momentum 50,01-09-2020,1,2,1,2,0,0,0,0,0,0,0
"""


def test_parse_day_reads_close_only_benchmark_rows():
    out = ib.parse_day(FILE, date(2020, 9, 1))
    assert set(out) == {"NIFTY", "NIFTY200MOM30"}
    m = out["NIFTY200MOM30"]
    assert m["o"] == m["h"] == m["l"] == m["c"] == 11933.25
    assert "NIFTY200MOM30" not in ib.INDICES.values()     # the map's index list is unchanged
