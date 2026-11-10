"""L1 period pivots (core/market_map/pivots.py): definitions v1 §4, on synthetic numbers."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from core.market_map import pivots as pv
from core.market_map import structure as s


def test_floor_pivots_match_the_book_and_the_old_map_algebra():
    h, l, c = 110.0, 90.0, 105.0
    f = pv.floor(h, l, c)
    p = (h + l + c) / 3
    assert f["P"] == pytest.approx(p)
    assert (f["R1"], f["S1"]) == pytest.approx((2 * p - l, 2 * p - h))
    assert (f["R2"], f["S2"]) == pytest.approx((p + 20, p - 20))
    assert f["R3"] == pytest.approx(h + 2 * (p - l)) and f["S3"] == pytest.approx(l - 2 * (h - p))
    assert f["R4"] == pytest.approx(f["R3"] + f["R2"] - f["R1"]) and f["S4"] == pytest.approx(f["S3"] - (f["S1"] - f["S2"]))


def test_cpr_swaps_so_tc_is_the_higher_edge():
    up = pv.cpr(110.0, 90.0, 108.0)       # close in the upper half: the formula's TC sits above BC
    dn = pv.cpr(110.0, 90.0, 92.0)        # lower half: the formula's TC sits below BC, swapped
    for x in (up, dn):
        assert x["TC"] > x["BC"]
        assert x["width_pct"] == pytest.approx((x["TC"] - x["BC"]) / x["P"] * 100)
    assert up["BC"] == pytest.approx(100.0) and dn["TC"] == pytest.approx(100.0)
    assert dn["TC"] - dn["BC"] == pytest.approx(abs(2 * 92 - 110 - 90) / 3)


def test_camarilla_expanded_formula():
    k = pv.camarilla(110.0, 90.0, 100.0)
    assert (k["H3"], k["L3"]) == pytest.approx((100 + 20 * 1.1 / 4, 100 - 20 * 1.1 / 4))
    assert (k["H4"], k["H1"]) == pytest.approx((100 + 11, 100 + 20 * 1.1 / 12))
    assert k["H5"] == pytest.approx(110 / 90 * 100) and k["L5"] == pytest.approx(100 - (k["H5"] - 100))


@pytest.mark.parametrize("cur,prev,rel", [
    ((100.05, 101.95), (100, 102), "unchanged"),
    ((103, 104), (100, 102), "higher value"),
    ((97, 99), (100, 102), "lower value"),
    ((99, 103), (100, 102), "outside"),
    ((100.5, 101.5), (100, 102), "inside"),
    ((101, 103), (100, 102), "overlapping higher"),
    ((99, 101), (100, 102), "overlapping lower"),
    ((101, 102), (100, 102), "unclassified"),          # top edge exactly equal: none of the seven
])
def test_two_period_relationships(cur, prev, rel):
    assert pv.relationship(*cur, *prev) == rel


def test_width_percentile_needs_eight_previous_periods_and_uses_twenty():
    assert pv.pctile(1.0, np.arange(7.0)) is None
    assert pv.pctile(3.5, np.arange(8.0)) == 0.5
    assert pv.pctile(100.0, np.r_[np.full(10, 1000.0), np.arange(20.0)]) == 1.0   # only the last 20 count
    assert (pv.reading(0.25), pv.reading(0.5), pv.reading(0.75)) == ("narrow", "average", "wide")


def _bars(hlc, tf="M"):
    df = pd.DataFrame(hlc, columns=["h", "l", "c"])
    df["o"] = df["c"]
    df["period"] = [f"2025-{i + 1:02d}" for i in range(len(df))]
    return df


def test_period_pivots_readings_trend_and_map_levels():
    # 11 quiet months closing above the CPR in force, then a month with a wide Camarilla
    rows = [(100 + i + 2, 100 + i - 2, 100 + i + 1.5) for i in range(11)] + [(140, 100, 139)]
    m = pv.period_pivots(_bars(rows), "M")
    assert m["from_period"] == "2025-12" and m["close_half"] == "upper"
    assert m["close_vs_cpr_in_force"] == "above TC"
    assert m["cpr_trend"]["side"] == "above" and m["cpr_trend"]["run"] == 11
    assert m["camarilla"]["width"] == "wide"
    names = {x["name"]: x for x in m["levels"]}
    assert names["R3"]["in_map"] and names["H3"]["in_map"] and names["prev L"]["in_map"]
    assert not names["H5"]["in_map"] and "H1" in names and not names["H1"]["in_map"]
    assert all(x["family"] == "pivot" for x in m["levels"])
    w = pv.period_pivots(_bars(rows), "W")
    assert not {x["name"]: x for x in w["levels"]}["R3"]["in_map"]          # week: outer layer shown only
    q = pv.period_pivots(_bars(rows[:3]), "Q")
    assert q["note"].startswith("quarterly pivots are not Ochoa") and q["cpr"]["width"] is None
    assert "H1" not in {x["name"] for x in q["levels"]}                     # no width reading, no hidden layers


def test_a_read_inside_a_month_uses_the_last_completed_month_quarter_and_year():
    days = pd.bdate_range("2024-01-01", "2026-03-20")
    d = pd.DataFrame({"date": days, "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0, "vol": 1})
    rd = s.l1_read(d, date(2026, 3, 18))
    p = rd["pivots"]
    assert (p["W"]["from_period"], p["M"]["from_period"], p["Q"]["from_period"], p["Y"]["from_period"]) == (
        "2026-W11", "2026-02", "2025-Q4", "2025")
    assert any(ln.startswith("     pivots (untested") for ln in s.lines(rd))


def test_v2_g6_camarilla_width_is_over_the_pivot_like_cpr_width():
    from core.market_map import pivots as pv_
    cam, cp = pv_.camarilla(120.0, 80.0, 85.0), pv_.cpr(120.0, 80.0, 85.0)
    p = (120.0 + 80.0 + 85.0) / 3
    assert abs(cam["width_pct"] - (cam["H3"] - cam["L3"]) / p * 100) < 1e-12
    assert abs(cp["width_pct"] - (cp["TC"] - cp["BC"]) / p * 100) < 1e-12
