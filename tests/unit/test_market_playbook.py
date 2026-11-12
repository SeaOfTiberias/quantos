"""Market playbook v1 (core/market_map/playbook.py; docs/MARKET_PLAYBOOK_V1.md) on synthetic
reads and bars. Every price below is worked by hand from the rules."""

from datetime import date

import pandas as pd
import pytest

from core.market_map import playbook as pb


def _tf(state, prot, weak, atr=None):
    return dict(state=state, protected=dict(price=prot, period="P"), weak=dict(price=weak, period="P"), atr=atr)


def _band(kind, lo, hi, at_break=True, fresh=True):
    return dict(kind=kind, tf="W", lo=lo, hi=hi, at_break=at_break, fresh=fresh, period="2026-W40")


def _l1(price=100.0, w=("up", 80.0, 120.0), m=("up", 50.0, 130.0), zones=(), atr_d=2.0, atr_w=8.0):
    return dict(price=price, tf=dict(M=_tf(*m), W=_tf(*w), D=_tf("up", 90, 101, atr=atr_d)),
                htf=dict(atr_w=atr_w, zones=list(zones)), zones=[], swings={})


def _z(*bands, strong=True):
    return dict(strong=strong, low=min(b["lo"] for b in bands), high=max(b["hi"] for b in bands), bands=list(bands))


# ─── P1 plan ─────────────────────────────────────────────────────────────────

def test_p1_long_from_the_nearest_fresh_strong_bullish_band():
    l1 = _l1(zones=[_z(_band("bull_ob", 92.0, 95.0)), _z(_band("demand", 85.0, 88.0)),
                    _z(_band("bull_ob", 96.0, 98.0, fresh=False)),                    # tested once: not an entry
                    _z(_band("bull_ob", 97.0, 99.0), strong=False)])                   # not strong
    p = pb.plan_p1(l1)
    assert p["status"] == "SETUP" and p["side"] == "long" and not p["entry_at_open"]
    assert (p["entry"], p["stop"], p["target"]) == (95.0, 91.5, 120.0)               # 92 - 0.25*2 = 91.5
    assert p["risk"] == 3.5 and p["rr"] == round(25 / 3.5, 2) and p["far"] == 92.0


def test_p1_inside_the_band_enters_at_the_next_open():
    p = pb.plan_p1(_l1(price=94.0, zones=[_z(_band("bull_ob", 92.0, 95.0))]))
    assert p["status"] == "SETUP" and p["entry_at_open"] and p["entry"] == 94.0


def test_p1_short_mirrors_with_ticks_rounded_against_the_trade():
    l1 = _l1(price=100.0, w=("down", 120.0, 70.0), m=("down", 150.0, 60.0),
             zones=[_z(_band("supply", 104.03, 107.01))], atr_d=2.02)
    p = pb.plan_p1(l1)
    assert p["side"] == "short" and p["entry"] == 104.05 and p["stop"] == 107.55      # 107.01 + 0.505 -> up to 107.55
    assert p["target"] == 70.0 and p["risk"] == 3.5


def test_p1_timeframes_disagree_says_what_to_wait_for():
    p = pb.plan_p1(_l1(m=("down", 130.0, 60.0), zones=[_z(_band("bull_ob", 92.0, 95.0))]))
    assert p["status"] == "WAIT" and "M protected high 130" in p["wait_for"]


@pytest.mark.parametrize("kw, why", [
    (dict(zones=[_z(_band("bull_ob", 101.0, 103.0))]), "no fresh strong bullish zone below"),
    (dict(zones=[_z(_band("bull_ob", 100.5, 101.5))], price=102.0), "not in W discount"),     # eq = 100
    (dict(zones=[_z(_band("bull_ob", 70.0, 95.0))]), "zone too wide"),                       # risk 25.5 > 12
    (dict(zones=[_z(_band("bull_ob", 92.0, 95.0))], w=("up", 91.0, 101.0)), "only 1.71R"),     # eq 96
])
def test_p1_no_trade_reasons(kw, why):
    p = pb.plan_p1(_l1(**kw))
    assert p["status"] == "NO TRADE" and why in p["reason"]


# ─── forward walk ────────────────────────────────────────────────────────────

class Fixed:
    """States after each close: W/M/D given per session index (default all up)."""

    def __init__(self, days, seq=None):
        self.days, self.seq = days, seq or {}

    def at(self, nxt):
        k = max(i for i, d in enumerate(self.days) if d < nxt)
        w, m, d = self.seq.get(k, ("up", "up", "up"))
        return dict(W=dict(state=w), M=dict(state=m),
                    D=dict(state=d, protected=dict(price=self.dprot.get(k, 0)) if hasattr(self, "dprot") else None,
                           atr=2.0, last_event=getattr(self, "ev", {}).get(k)))


def _bars(rows, start="2026-11-02"):
    df = pd.DataFrame(rows, columns=["o", "h", "l", "c"])
    df["date"] = pd.bdate_range(start, periods=len(df))
    df["vol"] = 1
    return df


def _setup(**kw):
    s = dict(setup="P1", status="SETUP", side="long", entry=95.0, stop=91.5, target=120.0, risk=3.5, rr=7.14,
             entry_at_open=False, far=92.0, valid=10, half_risk=False, cancel=[])
    s.update(kw)
    return s


def _run(rows, setup=None, seq=None, **kw):
    df = _bars(rows)
    fx = Fixed([d.date() for d in df["date"]], seq)
    for k, v in kw.items():
        setattr(fx, k, v)
    return pb.simulate(setup or _setup(), df, date(2026, 11, 2), opp_strong=kw.get("opp"), states=fx)


def test_fill_then_target():
    r = _run([(98, 99, 94, 96), (96, 110, 95, 109), (109, 121, 108, 120)])
    assert r["outcome"] == "closed" and r["fill"] == 95.0 and r["exit"] == 120.0 and r["reason"] == "target"
    assert r["r"] == round(25 / 3.5, 2)


def test_gap_fill_at_the_open_and_gap_through_the_stop():
    r = _run([(93, 94, 92, 93.5), (90, 91, 89, 90)])
    assert r["fill"] == 93.0 and r["exit"] == 90.0 and r["reason"] == "stop (gap)"
    assert r["r"] == round((90 - 93) / 3.5, 2)


def test_stop_and_target_on_one_bar_is_the_stop():
    r = _run([(98, 99, 94.5, 96), (96, 121, 91, 100)])
    assert r["exit"] == 91.5 and r["reason"] == "stop"


def test_break_even_then_trail_on_the_d_protected_low():
    rows = [(98, 99, 94.5, 96), (96, 99.5, 95.5, 99), (99, 104, 98.5, 103.8), (103, 103.5, 99.0, 99.5)]
    r = _run(rows, dprot={2: 100.0})
    # close 99 >= 95 + 3.5: stop to 95 after session 1; after session 2 D up with protected 100 -> 99.5
    assert any("break-even 95" in t for _, t in r["log"]) and any("-> 99.5" in t for _, t in r["log"])
    assert r["exit"] == 99.5 and r["reason"] == "trailing stop"


def test_c1_cancels_a_resting_order_when_w_flips():
    r = _run([(100, 101, 99, 100), (100, 100.5, 98, 99), (99, 99.5, 94, 95)], seq={1: ("down", "up", "down")})
    assert r["outcome"] == "cancelled" and r["reason"].startswith("C1 W turned down")


def test_c3_and_c4_and_a_drop_through_the_band_is_a_fill_then_a_stop():
    r = _run([(98, 99, 96, 97), (97, 97, 90, 91.9)])          # C2 can't come first: the limit is crossed on the way
    assert r["outcome"] == "closed" and r["fill"] == 95.0 and r["exit"] == 91.5
    r = _run([(98, 99, 96, 97), (97, 121, 96, 120)])
    assert r["reason"].startswith("C3")
    r = _run([(98, 99, 96, 97)] * 11)
    assert r["outcome"] == "expired"


def test_e1_thesis_exit_at_the_next_open_when_w_flips_after_the_fill():
    r = _run([(98, 99, 94.5, 96), (96, 97, 93, 94), (93.5, 94, 92, 93)], seq={1: ("down", "up", "down")})
    assert r["exit"] == 93.5 and r["reason"].startswith("E1 W turned down")


def test_e2_stall_in_an_opposing_strong_zone_then_d_choch():
    rows = [(98, 99, 94.5, 96), (96, 107, 95.5, 106), (106, 106.5, 103, 104), (103, 104, 102, 103)]
    ev = {2: dict(type="CHoCH", direction="down", date="2026-11-04")}
    r = _run(rows, seq={2: ("up", "up", "down")}, opp=[(105.0, 108.0)], ev=ev)
    assert r["exit"] == 103.0 and r["reason"].startswith("E2")


def test_time_exit_and_open_trade_mark():
    rows = [(98, 99, 94.5, 96)] + [(96, 97, 95.5, 96.5)] * 41
    r = _run(rows)
    assert r["reason"] == "time (40 sessions)" and r["exit"] == 96.5
    r = _run([(98, 99, 94.5, 96), (96, 97, 95.5, 96.5)])
    assert r["outcome"] == "open" and r["mark"] == 96.5


def test_p2_e3_close_back_below_the_swept_level():
    s = _setup(setup="P2", swept_level=94.0, half_risk=True)
    r = _run([(98, 99, 94.5, 96), (96, 96.5, 93.6, 93.8), (93.7, 94, 93, 93.5)], setup=s)
    assert r["exit"] == 93.7 and r["reason"].startswith("E3")


def test_no_setup_and_lines():
    assert pb.simulate(dict(status="NO TRADE"), _bars([(1, 1, 1, 1)]), date(2026, 11, 2))["outcome"] == "no setup"
    p = dict(status=pb.STATUS, as_of="2026-11-13", price=100.0,
             p1=pb.plan_p1(_l1(zones=[_z(_band("bull_ob", 92.0, 95.0))])), p2=dict(setup="P2", status="NO TRADE",
                                                                                 reason="no recent D CHoCH up"))
    txt = pb.lines(p)
    assert txt[0].startswith("PLAY 2026-11-13") and "P1 SETUP long: limit 95" in txt[1] and "P2 NO TRADE" in txt[2]


# ─── P2 plan on synthetic daily bars ─────────────────────────────────────────

def _sweep_bars(sweep_low=97.5, close=101.2):
    import numpy as np
    c = [150.0]
    for _ in range(5):                                     # lower highs and lower lows: D down
        c += list(np.linspace(c[-1], c[-1] - 12, 9)[1:])
        c += list(np.linspace(c[-1], c[-1] + 6, 7)[1:])
    c += list(np.linspace(c[-1], 101, 7)[1:])
    rows = [(x + 0.3, x + 1.2, x - 1.2, x) for x in c]
    rows += [(101.5, 102, sweep_low, close)]              # below the W weak low 100, back above it
    rows += [(x - 1.5, x + 1.0, x - 2.0, x) for x in np.linspace(close, 126, 9)[1:]]
    df = pd.DataFrame(rows, columns=["o", "h", "l", "c"])
    df["date"] = pd.bdate_range("2026-06-01", periods=len(df))
    df["vol"] = 1
    return df, (df["date"].iat[-1] + pd.Timedelta(days=3)).date()


def _l1_p2(price, atr_w=8.0):
    return dict(price=price, tf=dict(W=dict(state="down", protected=dict(price=140.0), weak=dict(price=100.0)),
                                     M=dict(state="down", protected=dict(price=160.0), weak=dict(price=100.0)),
                                     D=dict(atr=2.4)), htf=dict(atr_w=atr_w, zones=[]), zones=[], swings={})


def test_p2_sweep_of_the_w_weak_low_then_a_d_choch_up():
    df, as_of = _sweep_bars()
    p = pb.plan_p2(_l1_p2(126.0), df, as_of)
    assert p["status"] == "SETUP" and p["side"] == "long" and p["half_risk"]
    assert (p["entry"], p["stop"], p["target"]) == (102.0, 96.9, 140.0)             # 97.5 - 0.25*2.4 = 96.9
    assert p["swept_level"] == 100.0 and "swept to 97.5" in p["swept"] and "CHoCH up" in p["shift"]


def test_p2_no_sweep_and_risk_cap():
    df, as_of = _sweep_bars(sweep_low=99.95)                # not 0.1 ATR(D) below 100
    assert "no sweep" in pb.plan_p2(_l1_p2(126.0), df, as_of)["reason"]
    df, as_of = _sweep_bars()
    assert "sweep low too far" in pb.plan_p2(_l1_p2(126.0, atr_w=3.0), df, as_of)["reason"]   # 5.1 > 4.5
