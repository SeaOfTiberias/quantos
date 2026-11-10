"""L2 daily layer (core/market_map/daily.py), on synthetic bars."""

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from core.market_map import daily as dl


def _daily(rows):
    dates = pd.bdate_range("2026-01-05", periods=len(rows))
    df = pd.DataFrame(rows, columns=["h", "l", "c"])
    df["o"], df["vol"], df["date"] = df["c"], 1000.0, dates
    return df


def test_day_pivots_by_hand():
    d = _daily([(110, 100, 105), (112, 104, 111)])
    p = dl.day_pivots(d)
    assert p["from_session"] == d["date"].iat[-1].date().isoformat()
    assert (p["cpr"]["P"], p["cpr"]["BC"], p["cpr"]["TC"]) == (109, 108, 110)
    assert p["cpr"]["reading"] == "wide" and p["cpr"]["width_pct"] == pytest.approx(200 / 109, abs=1e-3)
    assert p["relationship"] == "higher value"                 # BC 108 above the previous TC 105
    lv = {x["name"]: x["price"] for x in p["levels"]}
    assert (lv["R1"], lv["S1"], lv["H3"], lv["L3"]) == (114, 106, 113.2, 108.8)
    assert [x["price"] for x in p["levels"]] == sorted(lv.values(), reverse=True)
    assert dl.day_pivots(d.iloc[:1]) is None


def _m5(d):
    """15 five-minute bars a session from 09:15, each spanning the day's low to high."""
    rows = []
    for day, h, l in zip(d["date"], d["h"], d["l"]):
        for k in range(15):
            t = day + timedelta(hours=9, minutes=15 + 5 * k)
            rows.append(dict(dt=t, date=day, o=(h + l) / 2, h=h, l=l, c=(h + l) / 2, vol=100.0))
    return pd.DataFrame(rows)


def test_session_levels_stay_virgin_until_a_later_daily_bar_spans_them():
    base = [100 + 5 * i for i in range(20)]                    # each day above the last: nothing is revisited
    d = _daily([(b + 1, b - 1, b) for b in base])
    as_of = d["date"].iat[-1] + timedelta(days=1)
    rd = dl.read(d, as_of, float(d["c"].iat[-1]), _m5(d))
    assert rd["status"] == "untested" and rd["sessions"] > 0
    assert rd["n_virgin"] == 6 * (rd["sessions"] - 1)           # v2 G5: the last session isn't virgin yet
    assert rd["last_session"]["session"] == d["date"].iat[-1].date().isoformat()
    assert all(x["price"] < d["c"].iat[-1] for x in rd["virgin_below"]) and len(rd["virgin_below"]) == dl.VIRGIN_SHOWN
    assert [x["price"] for x in rd["virgin_below"]] == sorted((x["price"] for x in rd["virgin_below"]), reverse=True)

    d2 = _daily([(b + 1, b - 1, b) for b in base] + [(1000, 1, 500)])     # one bar spans every earlier level
    m5 = _m5(d2)
    rd2 = dl.read(d2, d2["date"].iat[-1] + timedelta(days=1), 500.0, m5)
    assert rd2["n_virgin"] == 0                                # v1 listed the last session's own 6 levels
    assert rd2["virgin_below"] == [] and rd2["virgin_above"] == []


def test_the_read_uses_only_sessions_before_as_of_and_lines_name_the_layer():
    base = [100 + 5 * i for i in range(20)]
    d = _daily([(b + 1, b - 1, b) for b in base])
    cut = d["date"].iat[15]
    rd = dl.read(d, cut, float(d["c"].iat[14]), _m5(d))
    assert rd["pivots"]["from_session"] == d["date"].iat[14].date().isoformat()
    assert rd["last_session"]["session"] == d["date"].iat[14].date().isoformat()
    txt = dl.lines(rd, float(d["c"].iat[14]))
    assert txt[0].startswith("L2   daily layer (untested") and "never clustered" in txt[0]
    assert any("virgin session levels" in t for t in txt)
    assert dl.read(d, cut, 100.0, None)["sessions"] == 0
