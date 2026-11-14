"""core/market_map/call_plan.py: map plans for screener calls (synthetic cards and bars only)."""
import pandas as pd

from core.market_map import call_plan as cp


def _bars(lows, highs=None, closes=None, start="2026-10-01"):
    n = len(lows)
    highs = highs or [x + 4 for x in lows]
    closes = closes or [x + 2 for x in lows]
    return pd.DataFrame(dict(date=pd.bdate_range(start, periods=n), o=[x + 1 for x in lows], h=highs, l=lows, c=closes))


def _card(price=100.0, atr=2.0, **kw):
    c = dict(sym="TEST", price=price, atr_d=atr, last_date="2026-10-30",
             structure=dict(D=dict(protected=dict(px=90.0), weak=dict(px=104.0)),
                            W=dict(protected=dict(px=110.0), weak=dict(px=85.0))),
             liquidity=dict(above=[], below=[]),
             zones=dict(above=[dict(lo=106.0, hi=108.0, strong=True, why="W bear OB 106-108")],
                        below=[dict(lo=80.0, hi=84.0, strong=False, why="W bull FVG")], inside=[]),
             pivots=dict(W=dict(BC=97.0, P=97.5, TC=98.0), M=dict(BC=91.0, P=91.0, TC=91.0)))
    c.update(kw)
    return c


def test_swing_points_need_two_bars_each_side():
    b = _bars([100, 99, 96, 99, 100, 98])                 # 96 is a swing low; 98 is unconfirmed (last bar)
    assert cp.swing_points(b, "CE") == [(96.0, "D swing low 05 Oct")]


def test_sweep_level_pools_nearby_liquidity():
    # W CPR 97-98 and a swing low at 96.5 are within 0.5 ATR of each other: the pool's far edge is 96.5
    b = _bars([100, 99, 96.5, 99, 100, 101, 100])
    sw = cp.sweep_level(_card(), b, "CE")
    assert sw["level"] == 96.5 and "W CPR BC" in sw["kinds"] and any("swing low" in k for k in sw["kinds"])
    # a put looks above: D weak 104 (2 ATR) is the nearest; W bear OB edge 106 is 1 ATR beyond it -> separate
    assert cp.sweep_level(_card(), b, "PE")["level"] == 104.0


def test_target_is_nearest_opposing_level_at_least_one_atr_away():
    t = cp.target(_card(), "CE", entry_ref=100.0)
    assert t == dict(level=104.0, kind="D weak")
    t = cp.target(_card(), "CE", entry_ref=103.0)          # 104 is 0.5 ATR away: too close -> the OB at 106
    assert t["level"] == 106.0


def _version(level=96.5, target=104.0, atr=2.0):
    return dict(atr=atr, sweep=dict(level=level, kinds=["x"], atr_away=1.75, target=dict(level=target, kind="D weak")))


def _bar(d, o, h, l, c):
    return dict(date=d, o=o, h=h, l=l, c=c)


def test_sweep_reclaim_entry_and_target():
    v = _version()
    t = cp.new_track("sweep", "CE")
    t = cp.step(t, v, _bar("2026-11-02", 99, 100, 97, 98))         # no sweep yet
    assert t["state"] == "waiting"
    t = cp.step(t, v, _bar("2026-11-03", 98, 98.5, 95.0, 96.0))    # swept 96.5, closed below
    assert t["state"] == "swept" and t["extreme"] == 95.0
    t = cp.step(t, v, _bar("2026-11-04", 96, 98, 94.5, 97.5))      # new extreme 94.5, close back above 96.5
    assert t["state"] == "trigger_pending" and t["stop"] == 94.3   # 94.5 - 0.1 ATR
    t = cp.step(t, v, _bar("2026-11-05", 98.0, 101, 97.5, 100))     # entered at the open, no exit
    assert t["state"] == "triggered" and t["entry"] == 98.0 and abs(t["risk"] - 3.7) < 1e-9
    t = cp.step(t, v, _bar("2026-11-06", 101, 105, 100, 104.5))    # target 104
    assert t["state"] == "target" and t["exit"] == 104.0 and t["r"] == round(6.0 / 3.7, 2)


def test_put_mirror_stops_out():
    v = dict(atr=2.0, sweep=dict(level=104.0, kinds=["x"], atr_away=2.0, target=dict(level=96.0, kind="y")))
    t = cp.new_track("sweep", "PE")
    t = cp.step(t, v, _bar("2026-11-02", 102, 105.0, 101, 103.0))   # swept 104 and closed back below: trigger
    assert t["state"] == "trigger_pending" and t["stop"] == 105.2
    t = cp.step(t, v, _bar("2026-11-03", 102.5, 106, 102, 105.5))   # enter 102.5, stop 105.2 hit
    assert t["state"] == "stopped" and t["exit"] == 105.2 and t["r"] == -1.0 and t["pct"] < 0


def test_broke_lapsed_and_skipped():
    v = _version()
    t = cp.new_track("sweep", "CE")
    t = cp.step(t, v, _bar("2026-11-02", 97, 97, 94, 95))           # swept, no reclaim x3 -> broke
    for d in ("2026-11-03", "2026-11-04", "2026-11-05"):
        t = cp.step(t, v, _bar(d, 95, 96, 93, 94))
    assert t["state"] == "broke"
    t = cp.step(cp.new_track("sweep", "CE"), v, _bar("2026-11-02", 100, 104.5, 99, 104))
    assert t["state"] == "lapsed" and "ran without us" in t["events"][-1]["what"]
    t = cp.new_track("sweep", "CE")
    t = cp.step(t, v, _bar("2026-11-02", 97, 98, 95, 97), nxt=_bar("2026-11-03", 94.0, 95, 93, 94))
    assert t["state"] == "skipped"                                   # opened below the stop (94.8)


def test_waiting_plan_expires():
    v = _version()
    t = cp.new_track("sweep", "CE")
    for i in range(cp.EXPIRY):
        t = cp.step(t, v, _bar(f"2026-11-{i + 2:02d}", 99, 100, 98, 99))
    assert t["state"] == "lapsed"


def test_make_plan_and_lines():
    b = _bars([100, 99, 96.5, 99, 100, 101, 100])
    v = cp.make_plan(_card(), b, "CE")
    assert v["sweep"]["level"] == 96.5 and v["sweep"]["target"]["level"] == 104.0
    assert "breakout" not in v                                       # D weak 104 is 2 ATR away: no breakout plan
    lines = cp.plan_lines("TEST", "CE", 100.0, v, "2026-11-13")
    assert "don't chase" in lines[0] and "sweep: 96.5" in lines[1] and "target 104" in lines[1]
    assert "Paper plan, not an order." in lines[-1]
    assert cp.make_plan({"error": "x"}, b, "CE")["error"] == "x"


def test_breakout_plan_only_right_under_a_level():
    b = _bars([100, 99, 96.5, 99, 100, 101, 100])
    c = _card(structure=dict(D=dict(protected=dict(px=90.0), weak=dict(px=100.8)), W=dict(protected=dict(px=110.0))))
    v = cp.make_plan(c, b, "CE")
    assert v["breakout"]["level"] >= 100.8 and v["breakout"]["stop_ref"] == 100.0
