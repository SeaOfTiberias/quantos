"""HTF zones (core/market_map/htf.py): definitions v1 §6 and §6.1 as amended by v2 G2 and v3 H1-H4, on
synthetic elements."""

from core.market_map import htf


def _e(px, fam, tf="W", formula=None, period="2026-W40", label=None):
    return dict(price=px, family=fam, tf=tf, kind="x", label=label or f"{fam} {px}", period=period, formula=formula)


def _band(lo, hi, at_break=True, fresh=True):
    return dict(_e(lo, "imbalance"), lo=lo, hi=hi, band=True, at_break=at_break, fresh=fresh)


def test_clustering_is_the_existing_rule():
    els = [_e(100, "structure"), _e(100.8, "structure"), _e(101.5, "liquidity"), _e(102.2, "structure")]
    zs = htf.cluster(els, 1.0)                              # 102.2 - 100 > 1.5 w: a new cluster
    assert [(z["low"], z["high"], z["families"]) for z in zs] == [
        (100, 101.5, ["structure", "liquidity"]), (102.2, 102.2, ["structure"])]


def test_v3_h1_pivot_and_volume_never_make_or_widen_a_zone():
    zs = htf.htf_zones([_e(100, "pivot"), _e(100.5, "volume")], 1 / 0.3)
    assert zs == []
    zs = htf.htf_zones([_e(100, "structure"), _e(100.9, "volume")], 1 / 0.3)
    assert [(z["low"], z["high"], z["families"]) for z in zs] == [(100, 100, ["structure"])]
    assert zs[0]["confluence"] == ["volume 100.9"] and not zs[0]["strong"]    # no band at a break


def test_v3_h3_strong_needs_a_fresh_band_at_a_break_and_a_level():
    w = 1 / 0.3                                             # atr_w such that 0.3 ATR(W) = 1.0
    lvl = _e(95.8, "pivot")                                 # 0.8 above the band: within 1.0
    assert htf.htf_zones([_band(90, 95), lvl], w)[0]["strong"]
    assert not htf.htf_zones([_band(90, 95)], w)[0]["strong"]                          # no confluence
    assert not htf.htf_zones([_band(90, 95, fresh=False), lvl], w)[0]["strong"]        # tested once
    assert not htf.htf_zones([_band(90, 95, at_break=False), lvl], w)[0]["strong"]     # an FVG or a base off-break
    assert not htf.htf_zones([_band(90, 95), _e(96.5, "pivot")], w)[0]["strong"]       # 1.5 away


def test_v3_a_band_enters_whole_and_carries_its_flags():
    l1 = dict(tf={}, zones=[dict(kind="demand", tf="M", lo=90.0, hi=95.0, departed="2020-01", at_break=True,
                                 fresh=False, tested_once=True),
                            dict(kind="bull_fvg", tf="W", lo=80.0, hi=82.0, bar="2020-W02", at_break=False)],
              pivots={}, profiles=None)
    els = htf.elements(l1, {})
    assert [(e["lo"], e["hi"], e["family"], e["at_break"], e["fresh"]) for e in els] == [
        (90.0, 95.0, "imbalance", True, False), (80.0, 82.0, "imbalance", False, True)]
    assert "tested once" in els[0]["label"] and "bull FVG" in els[1]["label"]


def test_v3_h4_coverage_merges_overlaps_and_clips_to_the_window():
    zs = [dict(low=98, high=101, strong=True), dict(low=100, high=102, strong=False),
          dict(low=50, high=60, strong=False), dict(low=109, high=120, strong=False)]
    cv = htf.coverage(zs, 100.0, 10 / 3)                   # window 90..110
    assert cv["window"] == [90.0, 110.0] and cv["pct"] == 25.0 and cv["strong_pct"] == 15.0
    assert cv["zones"] == 3 and cv["strong"] == 1
    assert htf.coverage(zs, None, 1.0) is None


def test_v2_g2_rev1_bands_never_merge_and_a_cluster_joins_the_nearest_band():
    b = lambda lo, hi: dict(_e(lo, "imbalance"), lo=lo, hi=hi, band=True)
    zs = htf.cluster([b(90, 95), b(94, 96), b(97.5, 98), _e(96.8, "pivot")], 1.0)
    assert [(z["low"], z["high"]) for z in zs] == [(90, 95), (94, 96), (96.8, 98)]   # 96.8: 0.8 from 96, 0.7 from 97.5


def test_v2_g2_only_unbroken_swings_and_watched_virgin_levels_enter():
    l1 = dict(tf={}, zones=[], pivots={}, profiles=dict(periods={}, long={}, virgin=[
        dict(tf="W", period="2026-W40", kind="money zone", name="POC", price=100.0, watch=True),
        dict(tf="W", period="2026-W40", kind="money zone", name="VAH", price=104.0, watch=False)]))
    els = htf.elements(l1, {"W": [("H", "LH", 120.0, "2026-W30")]})
    assert sorted(e["price"] for e in els) == [100.0, 120.0]


def test_hot_zones_dpz_mtz_and_gpz():
    els = [_e(100, "pivot", "W", "floor", "2026-W40"), _e(100.2, "pivot", "M", "camarilla", "2026-09"),
           _e(120, "pivot", "W", "floor"), _e(120.1, "pivot", "W", "floor"),              # same formula and period
           _e(130, "structure")]
    l1 = dict(pivots=dict(M=dict(from_period="2026-09", cpr=dict(BC=99.0, TC=101.0),
                                 camarilla=dict(H3=100.5, L3=95.0))),
              profiles=dict(periods=dict(M=dict(money_zone=dict(POC=100.0, VAL=97.0, VAH=103.0),
                                                volume=dict(POC=98.0)))))
    hot = htf.hot_zones(els, 10.0 / 3, l1, strong=[dict(low=99.5, high=100.5)])
    assert len(hot["dpz"]) == 1 and hot["dpz"][0]["mtz"] and hot["dpz"][0]["strong_zone"]
    assert [(g["member"], g["direction"]) for g in hot["gpz"]] == [("H3", "bearish"), ("MZ POC", None)]


def test_nearest_strong():
    zs = [dict(low=90, high=92, strong=True), dict(low=95, high=96, strong=False), dict(low=99, high=101, strong=True),
          dict(low=110, high=111, strong=True)]
    n = htf.nearest_strong(zs, 100.0)
    assert n["below"]["low"] == 90 and n["above"]["low"] == 110 and n["inside"]["low"] == 99


def test_v2_g2_a_cluster_inside_overlapping_bands_joins_each():
    b = lambda lo, hi: dict(_e(lo, "imbalance"), lo=lo, hi=hi, band=True)
    zs = htf.cluster([b(90, 95), b(92, 98), _e(93, "pivot")], 1.0)
    assert [(z["low"], z["high"], z["families"]) for z in zs] == [
        (90, 95, ["imbalance", "pivot"]), (92, 98, ["imbalance", "pivot"])]
