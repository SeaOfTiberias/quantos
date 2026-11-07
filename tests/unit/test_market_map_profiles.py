"""L1 profiles (core/market_map/profiles.py): definitions v1 §4 profiles and virgin levels, §5."""

from datetime import date

import numpy as np
import pandas as pd

from core.market_map import profiles as pf
from core.price_map.levels import profile


def _daily(rows, start="2026-01-01"):
    d = pd.DataFrame(rows, columns=["l", "h", "vol"])
    d["date"] = pd.bdate_range(start, periods=len(d))
    d["o"] = d["c"] = (d["l"] + d["h"]) / 2
    return d


def test_the_fast_profile_matches_the_existing_rule():
    rng = np.random.default_rng(11)
    lo = rng.uniform(90, 110, 200)
    d = _daily(list(zip(lo, lo + rng.uniform(0, 6, 200), rng.uniform(1e3, 1e5, 200))))
    for step in (0.2, 0.5, 2):
        a, b = pf.vol_profile(d, step), profile(pf._bars(d), step)
        assert a.keys() == b.keys()
        assert all(abs(a[k] - b[k]) <= 1e-6 * b[k] for k in a)


def test_tpo_counts_one_per_bar_per_bucket():
    d = _daily([(100.0, 101.9, 5), (101.0, 102.4, 9)])
    assert pf.tpo(d, 1) == {100.0: 1, 101.0: 2, 102.0: 1}


def test_money_zone_poc_tie_goes_to_the_middle_and_value_area_reaches_70pct():
    h = {100.0: 3, 101.0: 3, 102.0: 1, 103.0: 3, 104.0: 1}
    poc, val, vah = pf.money_zone(h, mid=103.4, step=1)
    assert poc == 103.0
    covered = sum(v for k, v in h.items() if val <= k <= vah)
    assert covered >= 0.7 * sum(h.values()) and val <= poc <= vah


def _profs():
    return [dict(tf="M", period="2026-01", end_i=4, step=1,
                 mz=dict(POC=100.0, VAL=98.0, VAH=103.0), vol=dict(POC=100.0, VAL=98.0, VAH=103.0))]


def test_virgin_levels_retire_on_a_bar_that_spans_them_not_on_a_gap():
    rows = [(99, 101, 1)] * 5 + [(104, 106, 1), (101.5, 102.5, 1), (92, 95, 1)]  # gap up, back to 102, gap down
    d = _daily(rows)
    v = pf.virgin_levels(d, _profs(), date(2026, 2, 1), price=104.0, atr_now=2.0)
    mz = {x["name"]: x for x in v if x["kind"] == "money zone"}
    assert mz["POC"]["filled"] is None and mz["VAL"]["filled"] is None and mz["VAH"]["filled"] is None
    rows[6] = (102.5, 103.5, 1)                                                     # this bar trades through 103
    v = pf.virgin_levels(_daily(rows), _profs(), date(2026, 2, 1), price=104.0, atr_now=2.0)
    mz = {x["name"]: x for x in v if x["kind"] == "money zone"}
    assert mz["VAH"]["filled"] == _daily(rows)["date"].iat[6].date().isoformat()
    assert mz["POC"]["watch"] and mz["VAL"]["watch"] and not mz["VAH"]["watch"]  # VAH filled: VAL is the edge left
    assert mz["POC"]["distance_atr"] == 2.0 and mz["POC"]["age_periods"] == 1


def test_vpoc_relationship_and_unchanged_run():
    mk = lambda p: dict(vol=dict(POC=p, VAL=p - 5, VAH=p + 5))
    assert pf.vpoc_relationship([mk(100), mk(110), mk(110.5), mk(110.2)]) == dict(relationship="unchanged",
                                                                               unchanged_run=2)
    assert pf.vpoc_relationship([mk(100), mk(95)])["relationship"] == "lower"


def test_long_profile_finds_shelves_and_the_thin_area_between_them():
    # two broad areas (90-104, 116-130) with a peak in each, and a thin stretch (105-115) between
    rows = ([(90, 104, 1500)] * 40 + [(96, 98, 3000)] * 20 + [(105, 115, 11)] * 2
            + [(116, 130, 1500)] * 40 + [(122, 124, 3000)] * 20)
    d = _daily(rows)
    lp = pf.long_profile(d, date(2027, 1, 1), len(rows), atr_now=20.0)
    assert lp["label"] == "approximation (daily bars)" and lp["step"] == 1
    assert [(x["lo"], x["hi"]) for x in lp["hvn"]] == [(96.0, 99.0), (122.0, 125.0)]
    assert [(x["lo"], x["hi"]) for x in lp["lvn"]] == [(105.0, 116.0)]
    assert lp["lvn"][0]["family"] == "imbalance" and lp["hvn"][0]["family"] == "volume"
    assert pf.long_profile(d, date(2027, 1, 1), 250, atr_now=20.0) is None          # not enough sessions


def test_read_leaves_out_the_current_month_and_labels_q_and_y():
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, 800))
    d = _daily(list(zip(c - 1, c + 1, rng.uniform(1e3, 1e4, 800))), start="2023-01-02")
    as_of = date(2025, 12, 10)
    pr = pf.read(d, as_of, float(c[-1]))
    assert pr["periods"]["M"]["from_period"] == "2025-11" and pr["periods"]["Y"]["from_period"] == "2024"
    assert "not Ochoa" in pr["periods"]["Q"]["note"] and "not Ochoa" not in pr["periods"]["M"]["note"]
    assert all(v["filled"] is None for v in pr["virgin"])
    assert pr["long"]["750"] is not None
