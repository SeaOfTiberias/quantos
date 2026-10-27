"""core/position_manager/executor.py -- the plan's exits as orders, against a fake gateway."""

from datetime import date

from core.orders.gateway import Result
from core.position_manager.executor import Executor, oco_legs
from core.position_manager.rules import FutPosition, Plan, make_plan

D = date(2026, 10, 26)
EXP = date(2026, 11, 23)


class FakeGW:
    def __init__(self, ok=True, book=True, resting=None, readable=True):
        self.ok, self.book, self.resting, self.readable = ok, book, resting, readable
        self.calls = []

    def find_gtt(self, code, expiry, action, qty):
        self.calls.append(("find", code, action, qty))
        if not self.readable:
            raise RuntimeError("gtt book: down")
        return self.resting

    def place_oco(self, tgt, stp, positions=None):
        self.calls.append(("oco", tgt, stp))
        return Result(True, True, "GTT7") if self.ok else Result(False, False, reasons=["refused"])

    def cancel_gtt(self, gid):
        self.calls.append(("cancel_gtt", gid))
        return Result(True, True, gid)

    def verify_gtt(self, gid):
        self.calls.append(("verify", gid))
        if not self.readable:
            raise RuntimeError("gtt book: down")
        return {"gtt_order_id": gid} if self.book else None

    def work_exit(self, ex):
        self.calls.append(("exit", ex))
        return Result(True, True, "OID9")


def long_plan():
    return make_plan(FutPosition("INDHOT", EXP, 1000, 782.0), "INDHOTEL", 21.6, D, {"stop": 757, "target": 835})


def test_oco_legs_for_long_and_short():
    tgt, stp = oco_legs(long_plan(), "icici-spouse")
    assert (tgt.action, tgt.price, tgt.trigger, tgt.purpose, tgt.gtt) == ("sell", 835.0, 835.0, "target", True)
    assert (stp.action, stp.trigger, stp.price, stp.purpose) == ("sell", 735.4, 728.0, "stop")   # 1% under 735.4
    s = make_plan(FutPosition("POWFIN", EXP, -1300, 334.0), "PFC", 8.8, D)
    tgt, stp = oco_legs(s, "icici-spouse")
    assert tgt.action == "buy" and tgt.price == 327.4 and stp.trigger == 349.4 and stp.price == 352.9
    assert oco_legs(make_plan(FutPosition("X", EXP, 100, 10.0), "X", None, D), "icici-spouse") is None


def test_rest_places_and_replaces():
    gw, msgs = FakeGW(), []
    ex, p = Executor(gw, msgs.append), long_plan()
    ex.rest("k", p)
    assert p.gtt_id == "GTT7" and "resting OCO placed" in msgs[-1]
    ex.rest("k", p)                                                    # levels changed: cancel, then re-place
    assert [c[0] for c in gw.calls] == ["find", "oco", "cancel_gtt", "oco"]


def test_refused_oco_says_so():
    msgs = []
    p = long_plan()
    Executor(FakeGW(ok=False), msgs.append).rest("k", p)
    assert p.gtt_id is None and "NOT placed" in msgs[-1]


def test_daily_check_replaces_a_missing_gtt_once():
    gw, msgs = FakeGW(book=False), []
    ex, p = Executor(gw, msgs.append), long_plan()
    p.gtt_id = "GTT1"
    ex.daily_check("k", p)
    assert [c[0] for c in gw.calls] == ["verify", "find", "oco"] and p.gtt_id == "GTT7"
    ex.daily_check("k", p)
    assert len(gw.calls) == 3                                           # once a day


def test_daily_check_places_an_oco_for_a_position_opened_before_auto():
    gw = FakeGW()
    p = long_plan()
    Executor(gw, [].append).daily_check("k", p)
    assert [c[0] for c in gw.calls] == ["find", "oco"] and p.gtt_id == "GTT7"


def test_limits_from_config():
    from core.orders.gateway import limits_from
    lim = limits_from({"live": True, "max_lots": 2, "accounts": ["icici-spouse"], "unknown": 1})
    assert lim.max_lots == 2 and lim.accounts == ("icici-spouse",) and lim.max_fut_notional == 1_000_000.0


def test_exit_now_cancels_the_gtt_first():
    gw, msgs = FakeGW(), []
    p = long_plan()
    p.gtt_id, p.last_price = "GTT7", 755.0
    assert Executor(gw, msgs.append).exit_now(p, "daily close below 757")
    assert [c[0] for c in gw.calls] == ["cancel_gtt", "exit"]
    ex = gw.calls[1][1]
    assert (ex.action, ex.qty, ex.purpose) == ("sell", 1000, "exit") and p.gtt_id is None


def test_plan_state_round_trips_with_and_without_gtt():
    p = long_plan()
    p.gtt_id = "GTT7"
    assert Plan.from_dict(p.to_dict()).gtt_id == "GTT7"
    old = p.to_dict()
    del old["gtt_id"]                                                   # a state file from before this field
    assert Plan.from_dict(old).gtt_id is None


def short_plan():
    return make_plan(FutPosition("SUPIND", EXP, -175, 3238.0), "SUPREMEIND", 116.7, D)


def test_an_oco_already_at_the_broker_is_adopted_not_doubled():
    # 27-Oct: the OCO went in by hand (qorder) after the manager's own attempt was refused;
    # placing a second would buy 350 at the target and leave the account long 175
    gw, msgs = FakeGW(resting="2026102700001295"), []
    ex, p = Executor(gw, msgs.append), short_plan()
    ex.daily_check("k", p)
    assert [c[0] for c in gw.calls] == ["find"] and gw.calls[0][2:] == ("buy", 175)
    assert p.gtt_id == "2026102700001295" and "adopted" in msgs[-1]
    assert Executor(gw, msgs.append).exit_now(p, "daily close above 3325.53")
    assert gw.calls[-2] == ("cancel_gtt", "2026102700001295")         # the exit takes the adopted OCO with it


def test_an_unreadable_gtt_book_places_and_cancels_nothing():
    gw, msgs = FakeGW(readable=False), []
    ex, p = Executor(gw, msgs.append), short_plan()
    ex.rest("k", p)
    assert [c[0] for c in gw.calls] == ["find"] and p.gtt_id is None and "couldn't read" in msgs[-1]
    p.gtt_id = "GTT1"
    ex.daily_check("k2", p)
    assert gw.calls[-1][0] == "verify" and p.gtt_id == "GTT1" and "leaving OCO GTT1" in msgs[-1]
