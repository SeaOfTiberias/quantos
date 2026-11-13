"""core/market_map/triage.py on synthetic plans."""
from core.market_map.triage import pairs, triage, triage_one


def _p(side, entry, stop, target, status="SETUP", **kw):
    return dict(status=status, side=side, entry=entry, stop=stop, target=target, **kw)


def test_short_near_entry_is_actionable_with_lot_risk():
    t = triage_one("AAA", "p1", _p("short", 110.0, 115.0, 90.0), price=106.0, atr_d=2.0, lots={"AAA": 500})
    assert t["actionable"] and t["drop"] == []
    assert t["dist_atr"] == 2.0
    assert t["lot_risk"] == 2500.0  # 5 points x 500
    assert t["risk_pct"] == round(5 / 110 * 100, 2)


def test_far_entry_is_dropped():
    t = triage_one("AAA", "p1", _p("short", 120.0, 125.0, 90.0), price=106.0, atr_d=2.0, lots={"AAA": 500})
    assert not t["actionable"] and t["drop"][0].startswith("far")


def test_missed_target_long_and_short():
    lo = triage_one("B", "p2", _p("long", 100.0, 95.0, 120.0), price=121.0, atr_d=10.0, lots={})
    sh = triage_one("C", "p1", _p("short", 100.0, 105.0, 80.0), price=79.5, atr_d=10.0, lots={"C": 1})
    assert "missed" in lo["drop"][0] and "missed" in sh["drop"][0]


def test_short_without_futures_dropped_but_long_kept():
    sh = triage_one("D", "p1", _p("short", 101.0, 103.0, 90.0), price=100.0, atr_d=2.0, lots={})
    lo = triage_one("D", "p2", _p("long", 99.0, 97.0, 110.0), price=100.0, atr_d=2.0, lots={})
    assert sh["drop"] == ["short with no futures"]
    assert lo["actionable"] and lo["lot_risk"] is None


def test_non_setup_ignored_and_order():
    rows = [dict(sym="X", price=100.0, atr_d=1.0, p1=_p("short", 110.0, 112.0, 90.0), p2=dict(status="NO TRADE")),
            dict(sym="Y", price=100.0, atr_d=1.0, p1=_p("short", 101.0, 102.0, 90.0), p2=dict(status="WAIT")),
            dict(sym="Z", error="no data")]
    out = triage(rows, {"X": 10, "Y": 10})
    assert [t["sym"] for t in out] == ["Y", "X"]


def test_pairs_p2_target_equals_p1_entry():
    r = dict(sym="M", p1=_p("short", 13501.0, 14420.2, 10985.0), p2=_p("long", 11555.0, 10912.8, 13501.0))
    s = dict(sym="N", p1=_p("short", 500.0, 520.0, 400.0), p2=_p("long", 300.0, 290.0, 450.0))
    assert pairs([r, s]) == ["M"]
