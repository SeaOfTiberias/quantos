"""Playbook S8 test pieces (core/market_map/playbook_s8.py; prereg
docs/MARKET_PLAYBOOK_S8_PREREG_2026-11-13.md) on synthetic bars and rows."""

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from core.market_map import playbook as pb
from core.market_map import playbook_s8 as s8
from core.market_map import structure as st
from core.market_map.l1_store import Store
from tests.unit.test_market_playbook import _band, _l1, _l1_p2, _sweep_bars, _z


# ─── calendar, universe, segments ────────────────────────────────────────────

def test_p1_read_dates_first_session_of_even_iso_weeks():
    days = list(pd.bdate_range("2013-01-01", "2013-02-01").date)
    days.remove(date(2013, 1, 7))                      # a Monday holiday: Tuesday is the week's first session
    got = s8.p1_read_dates(days)
    assert got == [date(2013, 1, 8), date(2013, 1, 21)]          # ISO weeks 2 and 4
    assert all(d.isocalendar()[1] % 2 == 0 for d in got)


def test_universe_table_matches_store_universe(tmp_path):
    rng = np.random.default_rng(1)
    store = Store(tmp_path)
    dates = pd.bdate_range("2024-01-01", periods=30)
    raw = {}
    for k, sym in enumerate(["AAA", "BBB", "CCC", "DDD", "ETF1", "LATE"]):
        dd = dates[10:] if sym == "LATE" else dates
        df = pd.DataFrame(dict(date=dd, series="EQ", o=1.0, h=1.0, l=1.0, c=1.0, vol=1,
                               val=rng.uniform(1, 100, len(dd)) * (k + 1)))
        if sym == "BBB":
            df.loc[df.index[-3], "series"] = "BE"                    # off EQ on one day
        store.write_symbol(sym, df)
        raw[sym] = store.read_raw(sym)
    store.add_etfs(["ETF1"])
    tab = s8.universe_table(raw, store.etfs(), top_n=3, med_n=5)
    for d in dates[4::3]:                              # Store.universe ranks on a store's last day
        cut = Store(tmp_path / d.strftime("%Y%m%d"))
        cut.add_etfs(["ETF1"])
        for sym, g in raw.items():
            if (g["date"] <= d).any():
                cut.write_symbol(sym, g[g["date"] <= d])
        want = {r["sym"] for r in cut.universe(d.date(), top_n=3, med_n=5)}
        assert tab.get(d.date(), frozenset()) == want, d
    assert len(tab[dates[-1].date()]) == 3 and "ETF1" not in tab[dates[-1].date()]


def test_segment_at_takes_the_segment_of_the_last_bar_before_the_read():
    adj = pd.DataFrame(dict(date=pd.bdate_range("2024-01-01", periods=5), seg=[0, 0, 0, 1, 1], c=range(5)))
    assert list(s8.segment_at(adj, date(2024, 1, 4))["c"]) == [0, 1, 2]       # last bar before is Jan 3 (seg 0)
    assert list(s8.segment_at(adj, date(2024, 1, 9))["c"]) == [3, 4]
    assert s8.segment_at(adj, date(2023, 12, 1)).empty


def test_excluded_within_60_sessions_of_a_case():
    sess = list(pd.bdate_range("2025-01-01", "2025-12-31").date)
    i = sess.index(date(2025, 6, 23))
    assert s8.excluded("KEI", sess[i + 60], sess) and s8.excluded("KEI", sess[i - 60], sess)
    assert not s8.excluded("KEI", sess[i + 61], sess) and not s8.excluded("TCS", sess[i], sess)
    assert s8.excluded("HDFCBANK", date(2026, 9, 1), sess)


# ─── fast completed bars ─────────────────────────────────────────────────────

def _walk(n=400, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    df = pd.DataFrame(dict(o=c * (1 + rng.normal(0, 0.003, n)), c=c))
    df["h"] = df[["o", "c"]].max(axis=1) * 1.01
    df["l"] = df[["o", "c"]].min(axis=1) * 0.99
    df["date"] = pd.bdate_range("2020-01-01", periods=n)
    df["vol"] = 1
    return df


def test_segbars_equals_structure_completed_and_states():
    df = _walk()
    sb = s8.SegBars(df)
    ref = pb._States(df)
    for as_of in [date(2020, 3, 2), date(2020, 6, 17), date(2020, 7, 4), date(2021, 2, 1), date(2021, 7, 30)]:
        for tf in ("M", "W", "D"):
            pd.testing.assert_frame_equal(sb.completed(tf, as_of), st.completed(df, tf, as_of))
        a, b = sb.at(as_of), ref.at(as_of)
        assert {k: (v["state"], (v.get("protected") or {}).get("price")) for k, v in a.items()} == \
               {k: (v["state"], (v.get("protected") or {}).get("price")) for k, v in b.items()}


def test_events_prefix_and_p2_triggers():
    df = _walk()
    assert s8.events_prefix_ok(df, [120, 200, 333])
    ev = [e for e in s8.d_events(df) if e["type"] == "CHoCH"]
    trig = s8.p2_triggers(df)
    assert len(trig) == len([e for e in ev if e["i"] + 1 < len(df)])
    assert trig[0] == (df["date"].iat[ev[0]["i"] + 1].date(), ev[0]["direction"])


# ─── controls ────────────────────────────────────────────────────────────────

def _rd(l1):
    return s8.compact_read(dict(l1, htf=dict(l1["htf"]), tf=l1["tf"]))


def test_placebo_same_width_and_risk_zone_free_in_discount_deterministic():
    l1 = _l1(price=100.0, w=("up", 60.0, 120.0), zones=[_z(_band("bull_ob", 82.0, 85.0)), _z(_band("demand", 70.0, 72.0))])
    p = pb.plan_p1(l1)
    assert p["status"] == "SETUP" and p["entry"] == 85.0
    rd = s8.compact_read(l1)
    pl = s8.placebo_setups(rd, p, s8.rng_for("X", date(2024, 1, 1)))
    assert len(pl) == 3
    for q in pl:
        lo, hi = q["far"], q["entry"]
        assert hi < 90.0 and lo >= 60.0                                   # eq = 90, protected low 60
        assert not any(lo <= zh and zl <= hi for zl, zh in rd["zones"])
        assert abs(q["risk"] - p["risk"]) <= 0.11 and q["target"] == 120.0 and q["rr"] >= 2
        assert q["stop"] == pb._down(lo - 0.5)
    assert pl == s8.placebo_setups(rd, p, s8.rng_for("X", date(2024, 1, 1)))
    assert pl != s8.placebo_setups(rd, p, s8.rng_for("X", date(2024, 1, 2)))
    at_open = pb.plan_p1(_l1(price=94.0, zones=[_z(_band("bull_ob", 92.0, 95.0))]))
    assert s8.placebo_setups(s8.compact_read(_l1(price=94.0)), at_open, s8.rng_for("X", date(2024, 1, 1))) == []


def test_placebo_short_mirrors():
    l1 = _l1(price=100.0, w=("down", 140.0, 80.0), m=("down", 160.0, 60.0), zones=[_z(_band("supply", 115.0, 118.0))])
    p = pb.plan_p1(l1)
    assert p["status"] == "SETUP" and p["side"] == "short"
    for q in s8.placebo_setups(s8.compact_read(l1), p, s8.rng_for("Y", date(2024, 1, 1))):
        assert q["entry"] > 110.0 and q["far"] <= 140.0 and not (q["entry"] <= 118.0 and q["far"] >= 115.0)


def test_market_setup_and_no_e3():
    l1 = _l1(price=100.0, w=("up", 60.0, 120.0), zones=[_z(_band("bull_ob", 82.0, 85.0))])
    p = pb.plan_p1(l1)
    m = s8.market_setup(s8.compact_read(l1), p)
    assert m["entry_at_open"] and m["entry"] == 100.0 and m["stop"] == pb._down(100.0 - p["risk"])
    assert s8.no_e3(dict(p, side="long"))["swept_level"] == -math.inf


def test_p2_control_after_a_plain_break_and_none_when_swept():
    df, as_of = _sweep_bars(sweep_low=99.95)                              # under the weak low, not a sweep
    c = s8.plan_p2_control(_l1_p2(126.0), df, as_of)
    assert c["status"] == "SETUP" and c["setup"] == "P2C" and c["side"] == "long" and c["half_risk"]
    d = st.completed(df, "D", as_of)
    ev = st.run(d, st.TF_K["D"]).events[-1]
    from core.market_map import zones as zn
    assert c["entry"] == pb._down(zn.order_blocks(d, [ev])[0]["hi"]) and c["target"] == 140.0
    assert c["swept_level"] == -math.inf
    ext = d["l"].iloc[max(ev["i"] - 10, 0):ev["i"]].min()
    assert c["far"] == ext and c["stop"] == pb._down(ext - 0.25 * 2.4)
    df, as_of = _sweep_bars()                                             # a real sweep: P2, not a control
    assert s8.plan_p2_control(_l1_p2(126.0), df, as_of)["status"] == "NO TRADE"


# ─── scoring and statistics ──────────────────────────────────────────────────

class _Cost:
    def cost_of(self, e, x, q, d):
        return 0.001 * (e + x) * q


def test_score_closed_unfilled_and_segment_end():
    s = dict(side="long", risk=5.0)
    r = s8.score(s, dict(outcome="closed", fill=100.0, exit=110.0, mfe=2.1, mae=-0.2, sessions=7, end="x"), _Cost())
    assert r["filled"] and r["gross_r"] == 2.0 and r["cost_r"] == pytest.approx(0.042) and r["net_r"] == pytest.approx(1.958)
    assert s8.score(s, dict(outcome="expired", end="x"), _Cost())["net_r"] == 0.0
    o = s8.score(dict(side="short", risk=5.0), dict(outcome="open", fill=100.0, mark=95.0), _Cost())
    assert o["seg_end"] and o["gross_r"] == 1.0


def test_simulate_reports_its_end_date():
    from tests.unit.test_market_playbook import _run
    r = _run([(98, 99, 94.5, 96), (96, 97, 95.5, 96.5)])
    assert r["outcome"] == "open" and r["end"]


def test_month_boot_and_holm():
    rows = [(f"2020-{m:02d}-05", 1.0 + 0.1 * m) for m in range(1, 13)]
    b = s8.month_boot({"x": rows}, s8.mean_of("x"), n=500)
    assert b["point"] == pytest.approx(1.65) and b["lo"] > 1.0 and b["p"] == 0.0 and b["months"] == 12
    d = s8.month_boot({"a": rows, "b": [(d, v - 0.5) for d, v in rows]}, s8.diff_of("a", "b"), n=200)
    assert d["point"] == pytest.approx(0.5) and d["lo"] == pytest.approx(0.5)
    assert s8.holm({"P1": 0.01, "P2": 0.04}) == {"P1": True, "P2": True}
    assert s8.holm({"P1": 0.03, "P2": 0.04}) == {"P1": False, "P2": False}
    assert s8.holm({"P1": 0.02, "P2": None}) == {"P1": True, "P2": False}


def _rows(n, diff, side="long", start=2014):
    out = []
    for i in range(n):
        d = f"{start + i % 12}-{1 + i % 12:02d}-10"
        rid = f"S{i}|{side}"
        out.append(dict(track="P1", id=rid, match=None, read=d, side=side, excluded=False, filled=True, net_r=0.3 + diff))
        out.append(dict(track="P1-placebo", id=rid + "|0", match=rid, read=d, side=side, excluded=False, filled=True,
                        net_r=0.3))
    return out


def test_verdict_passes_and_fails_by_the_criteria():
    rows = _rows(300, 0.2) + _rows(150, 0.2, "short")
    v = s8.verdict(rows, n=300)
    assert v["p1"]["passed"] and all(v["p1"]["criteria"].values())
    assert v["p2"]["testable"] is False and not v["p2"]["passed"]
    v = s8.verdict(_rows(300, 0.05) + _rows(150, 0.05, "short"), n=300)       # beats placebo by < 0.10R
    assert not v["p1"]["criteria"]["A2"] and v["p1"]["criteria"]["A1"]
    v = s8.verdict(_rows(300, 0.2) + _rows(150, -0.1, "short"), n=300)       # shorts lose to placebo
    assert not v["p1"]["criteria"]["A4"]
    v = s8.verdict(_rows(300, 0.2) + _rows(50, -0.1, "short"), n=300)        # thin shorts: judged long-only
    assert v["p1"]["criteria"]["A4"] and v["p1"]["untested_sides"] == ["short"]
