"""L1 zones (core/market_map/zones.py): definitions v1 §3, on synthetic bars with ATR = 1."""

import numpy as np
import pandas as pd

from core.market_map import structure as st
from core.market_map import zones as zn



def _bars(ohlc):
    df = pd.DataFrame(ohlc, columns=["o", "h", "l", "c"])
    df["period"] = [f"P{i:02d}" for i in range(len(df))]
    df["date"] = pd.bdate_range("2026-01-05", periods=len(df))
    return df


def _flat(n, x=10.0):
    return [(x, x + 0.25, x - 0.25, x)] * n


def test_demand_base_departure_strength_tests_and_body_top():
    rows = [(5, 9, 1, 5)] + [(10, 10.3, 9.8, 10.2), (10.1, 10.25, 9.7, 9.9)] + \
           [(10.5, 12.0, 10.4, 11.0), (11, 13.5, 11, 13.0), (13, 14, 12.5, 12.6)] + \
           [(12, 12.5, 10.1, 11.0), (11, 11.5, 9.9, 11.2)]
    b = _bars(rows)
    z = zn.bases(b, np.ones(len(b)))
    assert len(z) == 1
    d = z[0]
    assert d["kind"] == "demand" and d["base"] == "P01..P02" and d["base_bars"] == 2
    assert (d["lo"], d["hi"]) == (9.7, 10.2)                        # lowest low .. highest body top
    assert d["departed"] == "P04" and d["strength_atr"] == round(13.0 - 10.3, 2)
    assert d["tests"] == 2 and d["last_test"] == "P07"              # P06 (low 10.1) and P07 trade into it


def test_a_close_below_a_demand_zone_drops_it():
    rows = _flat(2) + [(10.5, 13, 10.4, 12.9), (12, 12.5, 9, 9.5)]
    assert zn.bases(_bars(rows), np.ones(4)) == []


def test_supply_mirror_and_no_departure_means_no_zone():
    rows = _flat(2) + [(9.5, 9.6, 7.5, 7.6)]
    z = zn.bases(_bars(rows), np.ones(3))
    assert [(x["kind"], x["lo"], x["hi"]) for x in z] == [("supply", 10.0, 10.25)]
    assert zn.bases(_bars(_flat(2) + [(10, 11, 9, 10)] * 3 + [(10, 13, 10, 12.9)]), np.ones(6)) == []


def test_a_long_tight_run_keeps_its_last_six_bars():
    rows = _flat(9) + [(10.5, 13, 10.4, 12.9)]
    z = zn.bases(_bars(rows), np.ones(10))
    assert z[0]["base"] == "P03..P08" and z[0]["base_bars"] == 6


def test_multi_touch_needs_three_swings_over_26_bars():
    b = _bars(_flat(60))
    sw = [st.Swing("H", 0, 100.0, 3), st.Swing("L", 20, 100.2, 23), st.Swing("H", 40, 100.1, 43),
          st.Swing("L", 50, 90.0, 53)]
    m = zn.multi_touch(b, sw, 1.0)
    assert [(x["level"], x["lo"], x["hi"], x["touches"]) for x in m] == [(100.1, 100.0, 100.2, 3)]
    sw[2] = st.Swing("H", 25, 100.1, 28)                             # first to last: 25 bars
    assert zn.multi_touch(b, sw, 1.0) == []


def test_order_block_is_the_last_opposite_bar_near_the_protected_bar():
    rows = [(10, 11, 9, 10.5), (10.5, 10.6, 8, 8.2), (8.2, 8.5, 7, 8.4), (8.4, 9, 8, 8.8),
            (8.8, 12, 8.7, 11.8), (11.8, 12.5, 11, 12)]
    b = _bars(rows)
    ob = zn.order_blocks(b, [dict(type="BOS", direction="up", i=4, prot_i=2)])
    assert [(x["kind"], x["bar"], x["lo"], x["hi"], x["mitigated"]) for x in ob] == [
        ("bull_ob", "P01", 8.0, 10.6, False)]                       # P02 is an up bar; P01 is the last down bar
    rows[1] = (10, 10.6, 8, 10.5)                                    # no down bar in reach: the protected bar
    ob = zn.order_blocks(_bars(rows), [dict(type="BOS", direction="up", i=4, prot_i=2)])
    assert ob[0]["bar"] == "P02"
    rows.append((12, 12, 6, 6.5))                                    # a close below it: invalidated
    assert zn.order_blocks(_bars(rows), [dict(type="BOS", direction="up", i=4, prot_i=2)]) == []


def _eq_case(tail):
    rows = [(9, 10, 8.5, 9.5)] * 12 + tail
    rows[2] = (9.5, 12.0, 9, 9.6)
    rows[8] = (9.5, 12.05, 9, 9.6)
    b = _bars(rows)
    sw = [st.Swing("H", 2, 12.0, 4), st.Swing("L", 5, 8.5, 7), st.Swing("H", 8, 12.05, 10)]
    return [x for x in zn.equal_levels(b, sw, np.ones(len(b))) if x["kind"] == "EQH"]


def test_equal_highs_active_swept_and_broken():
    assert [(x["level"], x["status"]) for x in _eq_case([])] == [(12.05, "active")]
    assert [(x["status"], x["at"]) for x in _eq_case([(10, 12.5, 9, 11.9)])] == [("swept", "P12")]
    assert [x["status"] for x in _eq_case([(10, 12.5, 9, 12.2)])] == ["broken"]


def test_equal_highs_need_five_bars_apart():
    rows = [(9, 10, 8.5, 9.5)] * 12
    rows[2], rows[6] = (9.5, 12.0, 9, 9.6), (9.5, 12.05, 9, 9.6)
    sw = [st.Swing("H", 2, 12.0, 4), st.Swing("L", 4, 8.5, 6), st.Swing("H", 6, 12.05, 8)]
    assert zn.equal_levels(_bars(rows), sw, np.ones(12)) == []


def test_premium_discount_position_in_the_dealing_range():
    up = dict(state="up", protected=dict(price=100.0), weak=dict(price=200.0))
    assert zn.premium_discount(up, 175.0) == dict(lo=100.0, hi=200.0, eq=150.0, position_pct=75.0, side="premium")
    dn = dict(state="down", protected=dict(price=200.0), weak=dict(price=100.0))
    assert zn.premium_discount(dn, 120.0)["side"] == "discount"
    assert zn.premium_discount(dict(state="none"), 120.0) is None


def test_nearest_zones_split_inside_below_above():
    l1 = dict(price=100.0, zones=[
        dict(kind="demand", lo=90, hi=95, tf="W"), dict(kind="supply", lo=110, hi=112, tf="M"),
        dict(kind="bull_ob", lo=98, hi=102, tf="W"), dict(kind="EQL", lo=96, hi=96, tf="W", status="swept"),
        dict(kind="EQL", lo=97, hi=97, tf="W", status="active")])
    inside, below, above = st.nearest_zones(l1)
    assert [z["kind"] for z in inside] == ["bull_ob"]
    assert [z["lo"] for z in below] == [97, 90] and [z["kind"] for z in above] == ["supply"]
