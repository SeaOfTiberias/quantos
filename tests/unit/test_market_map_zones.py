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


# ─── v3 (docs/MARKET_MAP_DEFINITIONS_V3.md): FVGs, daily mitigation, at a break ─────────────

def _daily(rows, start="2026-02-02"):
    df = pd.DataFrame(rows, columns=["h", "l", "c"])
    df["date"] = pd.bdate_range(start, periods=len(df))
    return df


def _z(kind, lo, hi, formed="2026-01-30", **kw):
    return dict(kind=kind, lo=lo, hi=hi, formed=formed, tf="W", **kw)


def test_v3_h5_fvg_three_bar_gap_both_ways_and_minimum_size():
    rows = [(10, 10.5, 9.5, 10), (10.5, 12.5, 10.4, 12.3), (12.3, 13, 11, 12.8),       # bull: 11 > 10.5
            (12, 12.2, 11.95, 12), (11.9, 12, 11.7, 11.8)]                              # 11.7 vs 11.95-0.1: no
    z = zn.fvgs(_bars(rows), np.ones(5))
    assert [(g["kind"], g["lo"], g["hi"], g["bar"]) for g in z] == [("bull_fvg", 10.5, 11.0, "P02")]
    rows = [(10, 10.5, 9.5, 10), (9.5, 9.6, 8, 8.2), (8.2, 9.0, 7.5, 8.5)]                # bear: 9.0 < 9.5
    z = zn.fvgs(_bars(rows), np.ones(3))
    assert [(g["kind"], g["lo"], g["hi"]) for g in z] == [("bear_fvg", 9.0, 9.5)]
    rows = [(10, 10.5, 9.5, 10), (10.5, 12, 10.4, 11.9), (11.9, 12, 10.55, 11.9)]       # 0.05 < 0.1 ATR
    assert zn.fvgs(_bars(rows), np.ones(3)) == []


def test_v3_h5_a_gap_is_trimmed_then_removed_when_filled():
    g = _z("bull_fvg", 10.0, 11.0)
    kept, gone = zn.mitigate([g], _daily([(12, 10.6, 11.5), (11.8, 10.4, 11.0)]))
    assert gone == [] and kept[0]["hi"] == 10.4 and kept[0]["lo"] == 10.0              # top down to the lowest low
    kept, gone = zn.mitigate([g], _daily([(12, 10.6, 11.5), (11, 9.9, 10.8)]))
    assert kept == [] and gone[0]["removed"] == "filled" and gone[0]["removed_on"] == "2026-02-03"
    b = _z("bear_fvg", 10.0, 11.0)
    kept, gone = zn.mitigate([b], _daily([(10.3, 9, 9.5)]))
    assert kept[0]["lo"] == 10.3 and kept[0]["hi"] == 11.0


def test_v3_h2_touch_runs_tested_once_then_spent():
    d = _z("demand", 10.0, 11.0)
    out = [(13, 12, 12.5),                                   # away
           (12, 10.8, 11.5), (11.5, 10.5, 11.2),             # touch 1: two days, one run
           (13, 11.5, 12.8)]                                 # wholly outside: the run ends
    kept, gone = zn.mitigate([d], _daily(out))
    assert gone == [] and kept[0]["touches"] == 1 and kept[0]["tested_once"] and not kept[0]["fresh"]
    assert kept[0]["last_touch"] == "2026-02-03"
    kept, gone = zn.mitigate([d], _daily(out + [(12, 10.9, 11.4)]))                    # touch 2
    assert kept == [] and gone[0]["removed"] == "spent" and gone[0]["removed_on"] == "2026-02-06"
    kept, _ = zn.mitigate([d], _daily([(13, 12, 12.5)]))
    assert kept[0]["fresh"] and kept[0]["touches"] == 0


def test_v3_h2_a_daily_close_through_the_far_edge_breaks_it():
    d = _z("demand", 10.0, 11.0)
    kept, gone = zn.mitigate([d], _daily([(13, 12, 12.5), (12, 9.5, 9.8)]))
    assert kept == [] and gone[0]["removed"] == "broken" and gone[0]["removed_on"] == "2026-02-03"
    s = _z("bear_ob", 10.0, 11.0)
    kept, gone = zn.mitigate([s], _daily([(9.5, 9, 9.2), (11.5, 9.5, 11.2)]))
    assert gone[0]["removed"] == "broken"
    kept, gone = zn.mitigate([d], _daily([(13, 12, 12.5), (12, 9.5, 10.2)]))            # wick only: a touch
    assert gone == [] and kept[0]["tested_once"]


def test_v3_h2_bars_up_to_the_formed_day_do_not_count_and_other_zones_pass():
    d = _z("demand", 10.0, 11.0, formed="2026-02-03")
    kept, gone = zn.mitigate([d], _daily([(12, 10.5, 11.5), (12, 10.5, 11.5), (13, 12, 12.5)]))
    assert kept[0]["fresh"] and gone == []                  # the two touching days are on or before formed
    m = dict(kind="multi_touch", level=10.5, lo=10, hi=11, tf="W")
    assert zn.mitigate([m], _daily([(12, 9, 9.5)])) == ([m], [])


def test_v3_h3_a_base_is_at_a_break_only_with_a_same_way_event_in_its_window():
    rows = [(5, 9, 1, 5)] + [(10, 10.3, 9.8, 10.2), (10.1, 10.25, 9.7, 9.9)] + \
           [(10.5, 12.0, 10.4, 11.0), (11, 13.5, 11, 13.0), (13, 14, 12.5, 12.6)]
    b = _bars(rows)
    up = [dict(type="BOS", direction="up", i=4, level=12)]
    assert zn.bases(b, np.ones(len(b)), up)[0]["at_break"]
    assert not zn.bases(b, np.ones(len(b)), [dict(type="BOS", direction="down", i=4, level=9)])[0]["at_break"]
    assert not zn.bases(b, np.ones(len(b)), [dict(type="BOS", direction="up", i=0, level=9)])[0]["at_break"]
    assert zn.bases(b, np.ones(len(b)))[0]["formed"] == "2026-01-09"       # departure bar P04's session
