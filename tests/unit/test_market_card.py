"""core/market_map/card.py on a synthetic L1 read (no household data)."""
import pandas as pd

from core.market_map import card as cd


def _l1():
    tf = lambda state, atr, prot, weak, sweeps=(), fails=(): dict(
        state=state, age_bars=3, atr=atr, last_event=dict(type="BOS", direction=state, level=95.0, date="2026-11-02"),
        protected=dict(price=prot), weak=dict(price=weak), sweeps=list(sweeps), failed_breaks=list(fails),
        premium_discount=dict(lo=80.0, hi=120.0, position_pct=50.0, side="premium"),
        liquidity=dict(above=[dict(kind="EQH", level=104.0, status="active"),
                              dict(kind="EQH", level=400.0, status="active")],
                       below=[dict(kind="EQL", level=97.0, status="swept")]))
    zones = [dict(low=101.0, high=102.0, strong=False, why="W multi-touch x3"),
             dict(low=103.0, high=105.0, strong=False, why="a"),
             dict(low=106.0, high=107.0, strong=False, why="b"),
             dict(low=110.0, high=112.0, strong=True, why="M bear OB"),          # 4th above, strong, in reach
             dict(low=150.0, high=160.0, strong=True, why="far"),                 # strong but out of reach
             dict(low=95.0, high=98.0, strong=True, why="W bull OB"),
             dict(low=99.5, high=100.5, strong=False, why="inside")]
    return dict(as_of="2026-11-14", last_date="2026-11-13", price=100.0,
                tf=dict(M=tf("up", 8.0, 80.0, 120.0), W=tf("down", 4.0, 110.0, 90.0),
                        D=tf("up", 2.0, 96.0, 104.0,
                             sweeps=[dict(side="low", level=96.5, extreme=96.0, date="2026-11-10"),
                                     dict(side="low", level=90.0, extreme=89.0, date="2026-08-03")])),
                alignment=dict(text="not aligned: up on M, D, W down"),
                htf=dict(atr_w=4.0, zones=zones, coverage=dict(pct=40.0)),
                pivots=dict(W=dict(cpr=dict(P=99.0, BC=98.5, TC=99.5, width="narrow", relationship="higher value",
                                            bias="bullish"), close_vs_cpr_in_force="above TC",
                                   cpr_trend=dict(side="above", run=2),
                                   levels=[dict(name="R1", kind="floor", price=103.0),
                                           dict(name="S1", kind="floor", price=97.0)])),
                profiles=dict(periods=dict(M=dict(from_period="2026-10", money_zone=dict(VAL=95.0, POC=97.0, VAH=99.0,
                                                                                         relationship="higher value"))),
                              virgin=[dict(tf="M", kind="volume", name="POC", period="2026-08", price=108.0)]),
                l2=dict(pivots=dict(from_session="2026-11-13", cpr=dict(BC=99.8, P=100.0, TC=100.2, reading="narrow"))))


def test_distances_signed_in_atr_and_pct():
    assert cd.dist(104.0, 100.0, 2.0) == dict(px=104.0, pct=4.0, atr=2.0)
    assert cd.dist(97.0, 100.0, 2.0) == dict(px=97.0, pct=-3.0, atr=-1.5)
    assert cd.dist(None, 100.0, 2.0) == {}


def test_card_structure_zones_liquidity_and_value():
    c = cd.card("TEST", _l1())
    assert c["structure"]["W"]["protected"] == dict(px=110.0, pct=10.0, atr=5.0)
    above = c["zones"]["above"]
    assert [z["lo"] for z in above] == [101.0, 103.0, 106.0, 110.0]     # nearest 3 + strong within reach
    assert above[0]["edge_atr"] == 0.5 and above[3]["strong"]
    assert c["zones"]["below"][0]["edge_atr"] == -1.0                   # 98 is the near edge of 95-98
    assert [z["why"] for z in c["zones"]["inside"]] == ["inside"]
    assert c["liquidity"]["above"] == [dict(kind="EQH", px=104.0, pct=4.0, atr=2.0)]   # 400 out of reach
    assert c["liquidity"]["below"] == []                                               # swept: not active
    assert c["value"]["M"]["price"] == "above VAH"
    assert c["pivots"]["levels_above"][0]["name"] == "W floor R1"


def test_recent_events_drop_old_sweeps():
    c = cd.card("TEST", _l1())
    assert len(c["events"]) == 1
    e = c["events"][0]
    assert (e["tf"], e["kind"], e["side"], e["level"], e["ago"]) == ("D", "sweep", "low", 96.5, 3)
    assert "3 sessions ago" in cd.event_text(e)


def test_action_uses_only_bars_before_as_of():
    d = pd.DataFrame(dict(date=pd.bdate_range("2026-01-01", periods=30), o=1.0, h=0.0, l=0.0, c=0.0))
    d["c"] = [100.0 + i for i in range(30)]
    d["h"], d["l"] = d["c"] + 1, d["c"] - 1
    a = cd.action(d, d["date"].iat[-1].date())                          # the last bar is excluded
    assert a["chg_1d"] == round((128 / 127 - 1) * 100, 2)
    assert a["from_52w_high_pct"] == round((128 / 129 - 1) * 100, 2)


def test_text_is_compact_and_carries_status():
    t = cd.text(cd.card("TEST", _l1(), plans=["P1 long 98 stop 95 target 110"], notes=["results 2026-11-20"]))
    assert "UNTESTED" in t and "STRONG 110-112" in t and "plan: P1 long" in t and "note: results" in t
    assert len(t) < 3500
    assert cd.text(cd.card("X", {"error": "not in store"})) == "## X: no read (not in store)"


# ─── frozen context rules (core/market_map/context_rules.py) ─────────────────

from core.market_map import context_rules as cr  # noqa: E402


def test_rules_on_synthetic_card():
    c = cd.card("TEST", _l1())
    # long: nearest strong above is 110-112, edge +5 ATR -> room; a D low sweep 3 sessions ago is not opposing
    assert cr.r1_room(c, "CE") and cr.r2_no_sweep(c, "CE")
    # short: nearest strong below is 95-98, edge -1 ATR -> no room; the low sweep is opposing
    assert not cr.r1_room(c, "PE") and not cr.r2_no_sweep(c, "PE")
    # W is down: a long needs location -> strong zone below within 1 ATR (edge -1.0) -> passes
    assert cr.r4_structure_or_location(c, "CE") and cr.r4_structure_or_location(c, "PE")
    ev = cr.evaluate(c, c, "CE")
    assert ev == dict(R1=True, R2=True, R3=True, R4=True, keep=True)
    assert cr.evaluate(c, None, "PE")["keep"] is False
    assert cr.evaluate({"error": "x"}, None, "CE") is None


def test_r4_fails_against_w_without_location():
    l1 = _l1()
    l1["htf"]["zones"] = [z for z in l1["htf"]["zones"] if z["why"] != "W bull OB"]
    c = cd.card("TEST", l1)
    assert not cr.r4_structure_or_location(c, "CE")       # W down, no strong zone below within 1 ATR


def test_daily_zones_near_the_price():
    from core.market_map.card import d_zones_near
    zs = [dict(kind="bear_ob", lo=102.0, hi=104.0, formed="2026-06-04", touches=0),
          dict(kind="bear_fvg", lo=120.0, hi=121.0, formed="2026-05-01"),        # 10 ATR: within reach
          dict(kind="bear_fvg", lo=200.0, hi=201.0, formed="2026-01-01"),        # beyond reach
          dict(kind="bear_ob", lo=98.0, hi=110.0, formed="2026-09-09", touches=1),
          dict(kind="bull_fvg", lo=94.0, hi=97.0, formed="2026-11-11")]
    d = d_zones_near(zs, 100.0, 2.0)
    assert [z["name"] for z in d["above"]] == ["D bear OB 102-104", "D bear FVG 120-121"]
    assert d["above"][0]["touched"] == "untouched" and d["above"][0]["lo_atr"] == 1.0
    assert [z["name"] for z in d["inside"]] == ["D bear OB 98-110"] and d["inside"][0]["touched"] == "tested once"
    assert [z["name"] for z in d["below"]] == ["D bull FVG 94-97"]
