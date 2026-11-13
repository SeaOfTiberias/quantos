"""core/market_map/book.py, book_judge.validate and index_bars.parse_day on synthetic data."""
from datetime import date

import pandas as pd

from core.market_map import book as bk
from core.market_map import book_judge as bj
from core.market_map.index_bars import parse_day


def _setup(side, entry, stop, target, half=False):
    return dict(status="SETUP", setup="P2" if half else "P1", side=side, entry=entry, stop=stop, target=target,
                risk=abs(entry - stop), half_risk=half, valid=10, far=stop)


def _pos(pid, side, group, prio, half=True):
    e = 100.0
    return dict(id=pid, sym=pid.split(":")[0], track=pid.split(":")[1],
                setup=_setup(side, e, e - 5 if side == "long" else e + 5, e + 15 if side == "long" else e - 15, half),
                group=group, priority=prio)


def _walker(results):
    return lambda p, daily_for, first: results[p["id"]]


def _filled(d, r=0.0):
    return dict(outcome="open", fill=100.0, mark=100.0 + 5 * r, r=r, log=[(d, "filled 100")])


PENDING = dict(outcome="pending", log=[])


def _book(**kw):
    b = dict(id="B", first_session="2026-11-13",
             positions=[_pos("A:p2", "long", "g", 1), _pos("B:p2", "long", "g", 2), _pos("C:p2", "long", "g", 3),
                        _pos("S:p1", "short", "S", 1, half=False)],
             rules=dict(max_fills={"g": 2}, guards=[]), cancels=[])
    b.update(kw)
    return b


IDX = pd.DataFrame(dict(date=pd.to_datetime(["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]),
                        o=[25100.0] * 4, h=[25200.0] * 4, l=[25050.0, 24900.0, 24700.0, 24600.0], c=[25100.0] * 4))


def _rows(book, res):
    return {r["id"]: r for r in bk.advance(book, None, lambda s: IDX, walk=_walker(res))}


def test_group_cap_cancels_later_and_unfilled():
    res = {"A:p2": _filled("2026-11-16"), "B:p2": _filled("2026-11-17"), "C:p2": _filled("2026-11-18"),
           "S:p1": PENDING}
    rows = _rows(_book(), res)
    assert rows["A:p2"]["status"] == "open" and rows["B:p2"]["status"] == "open"
    assert rows["C:p2"]["status"] == "cancelled" and "full" in rows["C:p2"]["reason"]
    assert rows["S:p1"]["status"] == "pending"


def test_group_cap_same_day_by_priority():
    res = {"A:p2": _filled("2026-11-17"), "B:p2": _filled("2026-11-16"), "C:p2": _filled("2026-11-16"),
           "S:p1": PENDING}
    rows = _rows(_book(), res)
    assert rows["B:p2"]["status"] == "open" and rows["C:p2"]["status"] == "open"
    assert rows["A:p2"]["status"] == "cancelled"


def test_index_guard_cancels_unfilled_longs_only_and_keeps_same_day_fill():
    g = dict(index="NIFTY", below=24774.0, cancels="long", since="2026-11-13")
    res = {"A:p2": _filled("2026-11-17"), "B:p2": PENDING, "C:p2": _filled("2026-11-18"), "S:p1": PENDING}
    rows = _rows(_book(rules=dict(max_fills={}, guards=[g])), res)
    assert bk.guard_date(g, IDX) == "2026-11-17"
    assert rows["A:p2"]["status"] == "open"            # filled on the breach day: counts as filled
    assert rows["B:p2"]["status"] == "cancelled" and "index guard" in rows["B:p2"]["reason"]
    assert rows["C:p2"]["status"] == "cancelled"       # would have filled after the breach
    assert rows["S:p1"]["status"] == "pending"         # a long guard leaves shorts alone


def test_judgment_cancel_never_touches_a_fill():
    res = {"A:p2": _filled("2026-11-13"), "B:p2": PENDING, "C:p2": PENDING, "S:p1": PENDING}
    b = _book(cancels=[dict(id="A:p2", date="2026-11-14", why="x"), dict(id="B:p2", date="2026-11-14", why="y")])
    rows = _rows(b, res)
    assert rows["A:p2"]["status"] == "open"
    assert rows["B:p2"]["status"] == "cancelled" and rows["B:p2"]["reason"] == "judgment: y"
    assert bk.live_unfilled(list(rows.values())) == ["C:p2", "S:p1"]


def test_score_half_weight_and_judgment_edge():
    res = {"A:p2": dict(outcome="closed", fill=100.0, exit=115.0, r=3.0, log=[("2026-11-16", "filled 100")]),
           "B:p2": PENDING, "C:p2": PENDING, "S:p1": PENDING,
           "X:p1": dict(outcome="closed", fill=100.0, exit=95.0, r=-1.0, log=[("2026-11-16", "filled 100")])}
    b = _book(baseline=[dict(id="A:p2", setup=_pos("A:p2", "long", "g", 1)["setup"]),
                        dict(id="X:p1", setup=_setup("long", 100.0, 95.0, 115.0))])
    rows = bk.advance(b, None, lambda s: IDX, walk=_walker(res))
    sc = bk.score_book(b, rows, None, walk=_walker(res))
    assert 1.3 < sc["book"]["net_r"] < 1.5            # 0.5 x (3R - costs)
    assert sc["book"]["n"] == 4 and sc["baseline"]["n"] == 2
    assert sc["judgment_edge_r_per_position"] == round(sc["book"]["net_r_per_position"]
                                                       - sc["baseline"]["net_r_per_position"], 3)
    assert not sc["resolved"]


CTX = dict(book_day=True, open_books=[dict(id="B", live_unfilled=["C:p2"])],
           setups=[dict(id="X:p1"), dict(id="Y:p2")])
CLOSES = {"NIFTY": 25100.0, "BANKNIFTY": 61000.0}


def test_validate_accepts_good_and_rejects_bad():
    ans = dict(index_read="up",
               cancels=[dict(book="B", id="C:p2", why="ok"), dict(book="B", id="A:p2", why="filled")],
               guards=[dict(book="B", index="NIFTY", below=24774, cancels="long", why="g"),
                       dict(book="B", index="NIFTY", below=26000, cancels="long", why="already breached"),
                       dict(book="B", index="NIFTY", below=15000, cancels="long", why="too far")],
               new_book=dict(why="w", positions=[dict(id="X:p1", group="h", priority=1), dict(id="Z:p1", group="h")],
                             max_fills={"h": 1, "nope": 2}, guards=[]))
    out, errs = bj.validate(ans, CTX, CLOSES)
    assert [c["id"] for c in out["cancels"]] == ["C:p2"]
    assert len(out["guards"]) == 1 and out["guards"][0]["below"] == 24774.0
    assert [p["id"] for p in out["new_book"]["positions"]] == ["X:p1"]
    assert out["new_book"]["max_fills"] == {"h": 1}
    assert any("A:p2" in e for e in errs) and any("Z:p1" in e for e in errs)
    assert any("breached" in e for e in errs) and any("more than" in e for e in errs)


def test_validate_no_new_book_off_book_day_and_size_cap():
    out, errs = bj.validate(dict(new_book=dict(positions=[dict(id="X:p1")])), dict(CTX, book_day=False), CLOSES)
    assert out["new_book"] is None and errs == ["new_book: not a book day"]
    many = dict(CTX, setups=[dict(id=f"S{i}:p1") for i in range(12)])
    out, errs = bj.validate(dict(new_book=dict(positions=[dict(id=f"S{i}:p1", priority=i) for i in range(12)])),
                            many, CLOSES)
    assert len(out["new_book"]["positions"]) == bj.MAX_POSITIONS


def test_parse_answer_takes_last_json_block():
    t = 'x ```json\n{"a": 1}\n``` y ```json\n{"index_read": "z"}\n```'
    assert bj.parse_answer(t) == {"index_read": "z"}
    assert bj.parse_answer("no json") is None


def test_parse_index_day_new_and_old_names():
    new = ("Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,"
           "Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield\n"
           "Nifty 50,12-11-2026,25213.5,25384.8,25142.95,25299.35,44.3,.18,349198003,33608.35,20.62,3.1,1.39\n"
           "Nifty Bank,11-11-2026,1,2,0.5,1.5,0,0,1,1,1,1,1\n")
    got = parse_day(new, date(2026, 11, 12))
    assert set(got) == {"NIFTY"} and got["NIFTY"]["l"] == 25142.95 and got["NIFTY"]["val"] == 33608.35e7
    old = new.replace("Nifty 50,12-11-2026", "CNX Nifty,12/11/2026")
    assert parse_day(old, date(2026, 11, 12))["NIFTY"]["c"] == 25299.35
