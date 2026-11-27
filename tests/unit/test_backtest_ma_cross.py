"""scripts/backtest_ma_cross.py -- synthetic bars only (docs/MA_CROSS_PREREG_2026-11-27.md)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import _atr
from scripts import backtest_ma_cross as mc

ALL = (lambda d: True)
D0 = date(2017, 1, 2)


def bars(closes, start=D0, opens=None, spread=1.0):
    out, d = [], start
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        o = opens[i] if opens else c
        out.append(dict(date=d, o=o, h=max(o, c) + spread, l=min(o, c) - spread, c=c))
        d += timedelta(days=1)
    return out


def test_sma_and_atr_match_the_reference():
    assert mc.sma([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]
    rows = bars([100 + (i % 7) * 1.5 - (i % 3) for i in range(60)])
    atr = mc.wilder_atr(rows)
    assert atr[13] is None and atr[14] is not None
    ref = [OHLCV(timestamp=datetime(r["date"].year, r["date"].month, r["date"].day, tzinfo=timezone.utc),
                 open=r["o"], high=r["h"], low=r["l"], close=r["c"], volume=1) for r in rows]
    for i in (14, 30, 59):
        assert atr[i] == pytest.approx(_atr(ref[: i + 1]))


def test_rule_b_enters_next_open_and_exits_next_open_after_a_close_below():
    # SMA3: flat 100s, then a rise (cross up), then a drop (close below)
    closes = [100, 100, 100, 99, 104, 106, 108, 101, 100, 100]
    opens = [c + 0.5 for c in closes]
    rows = bars(closes, opens=opens)
    [t] = mc.simulate(rows, "B", 3, None, None, ALL, entry_from=D0, entry_to=date(2030, 1, 1))
    assert t["signal_date"] == rows[4]["date"].isoformat()        # 104 > SMA3 (101), 99 <= SMA3 before
    assert t["entry_price"] == opens[5] and t["entry_date"] == rows[5]["date"].isoformat()
    assert t["reason"] == "signal" and t["exit_date"] == rows[8]["date"].isoformat()   # 101 < SMA3 at 7
    assert t["exit_price"] == opens[8] and t["hold"] == 3


def test_rule_a_golden_and_death_cross():
    closes = [10] * 6 + [9, 8, 12, 14, 15, 15, 11, 8, 6, 6]
    rows = bars(closes)
    f, s = mc.sma(closes, 2), mc.sma(closes, 4)
    [t] = mc.simulate(rows, "A", 2, 4, None, ALL, entry_from=D0, entry_to=date(2030, 1, 1))
    i = [r["date"].isoformat() for r in rows].index(t["signal_date"])
    assert f[i] > s[i] and f[i - 1] <= s[i - 1]
    x = [r["date"].isoformat() for r in rows].index(t["exit_date"]) - 1      # exit signal close
    assert f[x] < s[x] and all(f[j] >= s[j] for j in range(i, x))


def test_atr_trail_exits_before_the_signal_and_only_rises():
    # B on SMA10; a strong run then a sharp drop that stays above SMA10 (it lags) for a while
    closes = [100] * 20 + [101, 110, 120, 130, 140, 150, 130, 125, 120, 100, 90, 90]
    rows = bars(closes, spread=0.5)
    sig = mc.simulate(rows, "B", 10, None, None, ALL, entry_from=D0, entry_to=date(2030, 1, 1))
    tr = mc.simulate(rows, "B", 10, None, 2.0, ALL, entry_from=D0, entry_to=date(2030, 1, 1))
    assert tr[0]["reason"] == "trail" and tr[0]["exit_date"] < sig[0]["exit_date"]
    # the 130 close (after the 150 high) is below 150 - 2*ATR: exit at the next open
    i = [r["date"].isoformat() for r in rows].index(tr[0]["exit_date"]) - 1
    assert closes[i] == 130


def test_trail_cannot_fire_on_the_entry_day_and_reentry_needs_a_new_cross():
    closes = [100] * 6 + [105, 70, 70, 71, 72, 110, 111, 111]
    rows = bars(closes, spread=0.2)
    trades = mc.simulate(rows, "B", 5, None, 1.0, ALL, entry_from=D0, entry_to=date(2030, 1, 1))
    assert trades[0]["hold"] >= 1
    assert len(trades) == 2 and trades[1]["signal_date"] == rows[11]["date"].isoformat()


def test_eligibility_window_and_data_end():
    closes = [100] * 6 + [105, 106, 107, 108]
    rows = bars(closes)
    assert mc.simulate(rows, "B", 5, None, None, lambda d: False, entry_from=D0, entry_to=date(2030, 1, 1)) == []
    assert mc.simulate(rows, "B", 5, None, None, ALL, entry_from=date(2030, 1, 1), entry_to=date(2031, 1, 1)) == []
    [t] = mc.simulate(rows, "B", 5, None, None, ALL, entry_from=D0, entry_to=date(2030, 1, 1))
    assert t["reason"] == "delisted" and t["exit_price"] == 108          # series ends in 2017: marked at last close


def test_exit_signal_on_the_last_bar_is_marked_at_that_close():
    closes = [100] * 6 + [105, 106, 90]
    rows = bars(closes)
    [t] = mc.simulate(rows, "B", 5, None, None, ALL, entry_from=D0, entry_to=date(2030, 1, 1))
    assert t["exit_price"] == 90 and t["exit_date"] == rows[-1]["date"].isoformat()


def test_median_version_is_the_lower_middle():
    s = {f"v{i:03d}": float(i) for i in range(100)}
    assert mc.median_version(s) == "v049"                               # 50th lowest of 100
    s20 = {f"v{i:02d}": float(i) for i in range(20)}
    assert mc.median_version(s20) == "v09"


def test_grid_sizes():
    g = mc.grid()
    assert sum(1 for x in g if x[0] == "A") == 100 and sum(1 for x in g if x[0] == "B") == 20


def T(entry, excess, net=None, exit_=None):
    return dict(entry_date=entry, exit_date=exit_ or entry, excess=excess, net=excess if net is None else net)


def test_walk_forward_uses_only_earlier_years():
    by = {"good-early": [T("2017-03-01", 0.05), T("2018-03-01", -0.10)],
          "good-late": [T("2017-03-01", 0.01), T("2018-03-01", 0.20), T("2019-03-01", 0.30)]}
    kept, chosen = mc.walk_forward(by, years=range(2018, 2020))
    assert chosen == [(2018, "good-early"), (2019, "good-late")]
    assert [t["excess"] for t in kept] == [-0.10, 0.30]


def test_verdict_and_stats():
    trades = [T(f"2017-0{m}-0{d}", 0.02) for m in range(1, 9) for d in range(1, 6)] + \
             [T(f"2021-0{m}-0{d}", 0.01) for m in range(1, 9) for d in range(1, 6)]
    scores = {f"v{i}": (0.01 if i < 70 else -0.01) for i in range(100)}
    v = mc.verdict(scores, trades, trades)
    assert all(ok for _, ok, _ in v)
    scores[f"v{69}"] = -0.01                                            # 69 of 100: breadth fails
    assert not mc.verdict(scores, trades, trades)[1][1]
    assert mc.profit_factor([0.1, -0.05]) == pytest.approx(2.0)
    assert mc.worst_drawdown([T("2017-01-02", 0.1, exit_="2017-01-03"), T("2017-01-02", -0.3, exit_="2017-01-04"),
                              T("2017-01-02", 0.1, exit_="2017-01-05")]) == pytest.approx(-0.3)
