"""HTF zones (core/market_map/htf.py): definitions v1 §6 and §6.1, on synthetic elements."""

from core.market_map import htf


def _e(px, fam, tf="W", formula=None, period="2026-W40", label=None):
    return dict(price=px, family=fam, tf=tf, kind="x", label=label or f"{fam} {px}", period=period, formula=formula)


def test_clustering_is_the_existing_rule_and_strong_needs_two_families():
    els = [_e(100, "structure"), _e(100.8, "pivot"), _e(101.5, "pivot"), _e(102.2, "volume"),   # 102.2 - 100 > 1.5 w
           _e(110, "volume"), _e(110.5, "volume")]
    zs = htf.cluster(els, 1.0)
    assert [(z["low"], z["high"], z["families"], z["strong"]) for z in zs] == [
        (100, 101.5, ["structure", "pivot"], True), (102.2, 102.2, ["volume"], False),
        (110, 110.5, ["volume"], False)]                    # money zone + VPOC agreeing: one family, not strong


def test_v2_g2_pivot_and_volume_alone_are_not_strong():
    zs = htf.cluster([_e(100, "pivot"), _e(100.5, "volume")], 1.0)
    assert zs[0]["families"] == ["volume", "pivot"] and not zs[0]["strong"]
    zs = htf.cluster([_e(100, "liquidity"), _e(100.5, "volume")], 1.0)
    assert zs[0]["strong"]


def test_v2_g2_a_band_enters_whole_and_is_never_split():
    l1 = dict(tf={}, zones=[dict(kind="demand", tf="M", lo=90.0, hi=95.0, departed="2020-01")], pivots={},
              profiles=None)
    els = htf.elements(l1, {})
    assert [(e["lo"], e["hi"], e["family"], e["band"]) for e in els] == [(90.0, 95.0, "imbalance", True)]
    # a pivot inside the band and a volume level 0.8 above it join it; a far level stays apart
    zs = htf.cluster(els + [_e(92, "pivot"), _e(95.8, "volume"), _e(99, "structure")], 1.0)
    assert [(z["low"], z["high"], z["families"], z["strong"]) for z in zs] == [
        (90.0, 95.8, ["imbalance", "volume", "pivot"], True), (99, 99, ["structure"], False)]


def test_v2_g2_overlapping_bands_merge_and_a_cluster_joins_the_nearest_band():
    b = lambda lo, hi, fam="imbalance": dict(_e(lo, fam), lo=lo, hi=hi, band=True)
    zs = htf.cluster([b(90, 95), b(94, 96), b(97.5, 98, "volume"), _e(96.8, "pivot")], 1.0)
    assert [(z["low"], z["high"]) for z in zs] == [(90, 96), (96.8, 98)]    # 96.8: 0.8 from 96, 0.7 from 97.5


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
