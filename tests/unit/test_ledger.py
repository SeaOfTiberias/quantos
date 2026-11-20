"""core/ledger (E5): schema validation and R scoring. Synthetic symbols and bars only."""
from datetime import datetime, timedelta, timezone

import pytest

from core.ledger import schema as sc
from core.ledger import score as sx

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 20, 20, 0, tzinfo=IST)
READ = {"symbol": "SYN", "price": 100.0}


def call(**kw):
    raw = dict(symbol="syn", side="long", who="claude", entry={"kind": "open"}, stop=95, target=110,
               salvage="cut at the stop", decision="taken", why="test")
    raw.update(kw)
    return sc.make_call(raw, now=NOW, as_of="2026-11-20", ref_close=100.0, atr=2.0, map_read=READ, map_plan=None)


def bars(rows):
    out = []
    for i, r in enumerate(rows):
        o, h, l, c = r
        out.append(dict(date=f"2026-12-{i + 1:02d}", o=o, h=h, l=l, c=c))
    return out


# ─── schema ───────────────────────────────────────────────────────────────────

def test_make_call_fills_code_fields():
    c = call()
    assert c["id"] == "2026-11-20-claude-SYN-1" and c["symbol"] == "SYN" and c["max_hold"] == 15
    assert c["map_read"] == READ and c["ref_close"] == 100.0


@pytest.mark.parametrize("kw,msg", [
    (dict(side="up"), "side"), (dict(who="bot"), "who"), (dict(decision="maybe"), "decision"),
    (dict(why=""), "why"), (dict(salvage=""), "salvage"), (dict(stop=None), "stop is required"),
    (dict(stop=105), "wrong side"), (dict(target=90), "wrong side"),
    (dict(entry={"kind": "limit"}), "entry.price"), (dict(entry={"kind": "market"}), "entry.kind"),
])
def test_make_call_refuses(kw, msg):
    with pytest.raises(sc.CallError, match=msg):
        call(**kw)


def test_no_map_read_no_call():
    with pytest.raises(sc.CallError, match="No map read"):
        sc.make_call(dict(symbol="SYN", side="long", who="user", stop=95, salvage="x", decision="taken", why="x"),
                     now=NOW, as_of="2026-11-20", ref_close=100.0, atr=2.0, map_read={"error": "x"}, map_plan=None)


def test_mechanical_call_needs_no_stop_or_salvage():
    c = call(who="screener", stop=None, target=None, salvage="")
    assert c["stop"] is None


# ─── call scoring ─────────────────────────────────────────────────────────────

def test_open_entry_target():
    s = sx.score_call(call(), bars([(100, 103, 99, 102), (102, 111, 101, 110)]))
    assert s["state"] == "target" and s["entry"] == 100 and s["exit"] == 110 and s["r"] == 2.0


def test_stop_wins_when_both_on_one_bar():
    s = sx.score_call(call(), bars([(100, 112, 94, 100)]))
    assert s["state"] == "stopped" and s["r"] == -1.0


def test_gap_through_stop_fills_at_open():
    s = sx.score_call(call(), bars([(100, 101, 99, 100), (90, 92, 89, 91)]))
    assert s["state"] == "stopped" and s["exit"] == 90 and s["r"] == -2.0


def test_open_beyond_stop_is_skipped():
    assert sx.score_call(call(), bars([(94, 96, 93, 95)]))["state"] == "skipped"


def test_time_exit_and_open_mark():
    c = call(max_hold=2, target=None)
    s = sx.score_call(c, bars([(100, 101, 99, 100), (100, 102, 99, 101), (101, 103, 100, 103)]))
    assert s["state"] == "time" and s["exit"] == 101 and s["r"] == 0.2
    s = sx.score_call(call(target=None), bars([(100, 101, 99, 100), (100, 102, 99, 102.5)]))
    assert s["state"] == "open" and s["r"] == 0.5 and s["exit_date"] is None


def test_limit_entry_fills_then_only_stop_checked_on_fill_bar():
    c = call(entry={"kind": "limit", "price": 98}, stop=96, target=104)
    s = sx.score_call(c, bars([(100, 105, 97.5, 104), (104, 105, 103, 104)]))   # fill bar's 105 doesn't count
    assert s["entry"] == 98 and s["entry_date"] == "2026-12-01"
    assert s["state"] == "target" and s["exit_date"] == "2026-12-02" and s["r"] == 3.0


def test_limit_gap_below_fills_at_open():
    c = call(entry={"kind": "limit", "price": 98}, stop=96, target=104)
    assert sx.score_call(c, bars([(97, 99, 96.5, 98)]))["entry"] == 97


def test_limit_unfilled_after_window_and_pending_before():
    c = call(entry={"kind": "limit", "price": 90, "window": 2}, stop=88, target=104)
    assert sx.score_call(c, bars([(100, 101, 99, 100)]))["state"] == "pending"
    assert sx.score_call(c, bars([(100, 101, 99, 100)] * 2))["state"] == "unfilled"


def test_short_stop_entry_and_target():
    c = call(side="short", entry={"kind": "stop", "price": 98}, stop=101, target=92)
    s = sx.score_call(c, bars([(99, 99.5, 97, 97.5), (97, 97.5, 91, 92)]))
    assert s["entry"] == 98 and s["state"] == "target" and s["exit"] == 92 and s["r"] == 2.0


def test_scale_rescales_levels_after_a_split():
    c = call()                                          # levels 95/110 on the old basis; bars halved
    s = sx.score_call(c, bars([(50, 51.5, 49.5, 51), (51, 55.5, 50.5, 55)]), scale=0.5)
    assert s["state"] == "target" and s["r"] == 2.0


# ─── baselines and headline ───────────────────────────────────────────────────

def test_as_sent_uses_call_risk_and_max_hold():
    c = call(max_hold=2)
    s = sx.score_as_sent(c, bars([(101, 102, 100, 101), (101, 104, 100, 103), (103, 104, 100, 90)]))
    assert s["state"] == "time" and s["entry"] == 101 and s["exit"] == 103 and s["r"] == pytest.approx(2 / 5, abs=1e-3)


def test_no_map_plan_scores_zero():
    s = sx.score(call(), bars([(100, 103, 99, 102)]))
    assert s["map_plan"]["state"] == "no plan" and s["r_map_plan"] == 0.0


def test_map_plan_walks_call_plan_step():
    plan = dict(as_of="2026-11-20", price=100.0, atr=2.0, target=dict(level=106.0, kind="x"),
                sweep=dict(level=97.0, kinds=["D protected"], level_kinds=["D protected"], target=dict(level=106.0, kind="x")))
    c = sc.make_call(dict(symbol="SYN", side="long", who="claude", stop=95, target=110, salvage="x",
                          decision="taken", why="x"), now=NOW, as_of="2026-11-20", ref_close=100.0, atr=2.0,
                     map_read=READ, map_plan=plan)
    # sweep 97 by >= 0.25 ATR (to 96.2), reclaim close back above 97, enter next open, run to 106
    b = bars([(99, 99.5, 96.2, 96.8), (96.8, 98, 96.5, 97.6), (98, 100, 97.8, 99.5), (99.5, 106.5, 99, 106)])
    m = sx.score_map_plan(c, b)
    assert m.get("entry") is not None, m
    assert m["state"] in ("target", "triggered")


def test_avoided_call_counts_zero_but_reports_if_taken():
    s = sx.score(call(decision="avoided"), bars([(100, 103, 99, 102), (102, 111, 101, 110)]))
    assert s["r_call"] == 0.0 and s["r_if_taken"] == 2.0


def test_summary_groups():
    a, b = call(), call(who="user", decision="avoided")
    b["id"] = "b"
    m = call(who="screener", stop=None, target=None, salvage="")
    m["id"] = "m"
    bs = bars([(100, 103, 99, 102), (102, 111, 101, 110)])
    scores = {x["id"]: sx.score(x, bs) for x in (a, b, m)}
    s = sx.summary([a, b, m], scores)
    assert s["discretionary"]["n"] == 2 and s["discretionary"]["mean_r"] == 1.0
    assert s["user"]["avoided"] == 1 and s["user"]["avoided_if_taken"] == 2.0
    assert s["mechanical"]["n"] == 1 and s["claude"]["n"] == 1


def test_close_above_enters_next_open():
    c = call(entry={"kind": "close_above", "price": 101}, stop=97, target=109)
    s = sx.score_call(c, bars([(100, 102, 99, 100.5), (100.5, 102, 100, 101.5), (102, 103, 101, 102), (102, 110, 101, 109)]))
    assert s["entry"] == 102 and s["entry_date"] == "2026-12-03" and s["state"] == "target" and s["r"] == 1.4


def test_close_trigger_on_last_bar_is_pending():
    c = call(entry={"kind": "close_above", "price": 101}, stop=97, target=109)
    assert sx.score_call(c, bars([(100, 102, 99, 101.5)]))["state"] == "pending"


def test_close_between_and_bad_range():
    c = call(entry={"kind": "close_between", "low": 99, "high": 100}, stop=96, target=106)
    s = sx.score_call(c, bars([(101, 102, 100.5, 101), (100, 101, 99, 99.5), (100, 101, 99.5, 100)]))
    assert s["entry"] == 100 and s["state"] == "open"
    with pytest.raises(sc.CallError, match="low must be below"):
        call(entry={"kind": "close_between", "low": 100, "high": 99})
