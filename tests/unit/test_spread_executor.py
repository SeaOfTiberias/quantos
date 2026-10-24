"""core/spread_watcher/executor.py -- short leg bought back first, retries, hand-off."""

from datetime import date

from core.orders.gateway import Result
from core.spread_watcher.executor import MAX_ATTEMPTS, SpreadExecutor, leg_exit
from core.spread_watcher.legs import Leg, Spread
from core.spread_watcher.rules import SpreadState

EXP = date(2026, 11, 23)
SP = Spread(long=Leg("INDHOT", EXP, "call", 820.0, 1000, 5.45 + 8.10),
            short=Leg("INDHOT", EXP, "call", 860.0, -1000, 2.95))


class FakeGW:
    live = True

    def __init__(self, results):
        self.results = list(results)
        self.sent = []

    def work(self, intent):
        self.sent.append((intent.action, intent.strike, intent.qty, intent.purpose))
        return self.results.pop(0)


OK, NO = Result(True, True, "OID"), Result(False, True, None, ["exit not filled after 6 tries"])


def state():
    return SpreadState.open(SP)


def test_leg_exit_orders():
    s, lg = leg_exit(SP.short, "icici-spouse"), leg_exit(SP.long, "icici-spouse")
    assert (s.action, s.qty, s.right, s.strike, s.purpose, s.product) == ("buy", 1000, "call", 860.0, "exit", "options")
    assert (lg.action, lg.qty, lg.strike) == ("sell", 1000, 820.0)


def test_close_buys_back_the_short_first():
    gw, msgs = FakeGW([OK, OK]), []
    ex, st = SpreadExecutor(gw, msgs.append), state()
    ex.request(st, "giveback")
    assert ex.close(SP, st, "INDHOT bull call")
    assert gw.sent == [("buy", 860.0, 1000, "exit"), ("sell", 820.0, 1000, "exit")]
    assert st.close_reason is None and "Closed" in msgs[-1] and "giveback" in msgs[-1]


def test_failed_short_sends_nothing_else_and_retries_then_stops():
    gw, msgs = FakeGW([NO] * MAX_ATTEMPTS), []
    ex, st = SpreadExecutor(gw, msgs.append), state()
    ex.request(st, "exit_day")
    for _ in range(MAX_ATTEMPTS + 2):
        assert not ex.close(SP, st, "X")
    assert len(gw.sent) == MAX_ATTEMPTS and all(a == "buy" for a, *_ in gw.sent)
    assert "Retrying" in msgs[0] and "close it by hand" in msgs[-1]


def test_failed_long_after_short_hands_off_once():
    gw, msgs = FakeGW([OK, NO]), []
    ex, st = SpreadExecutor(gw, msgs.append), state()
    ex.request(st, "trail_stock")
    assert not ex.close(SP, st, "X")
    assert "Sell it by hand" in msgs[-1] and st.close_reason is None
    assert not ex.close(SP, st, "X") and len(gw.sent) == 2          # no second attempt


def test_kinds_filter_and_one_request_at_a_time():
    ex, st = SpreadExecutor(FakeGW([]), [].append, kinds=("exit_day",)), state()
    ex.request(st, "giveback")
    assert st.close_reason is None
    ex.request(st, "exit_day")
    ex.request(st, "trail_stock")
    assert st.close_reason == "exit_day"


def test_state_round_trip_keeps_close_fields():
    st = state()
    st.close_reason, st.close_attempts = "giveback", 2
    back = SpreadState.from_dict(st.to_dict())
    assert (back.close_reason, back.close_attempts) == ("giveback", 2)
    old = st.to_dict()
    del old["close_reason"], old["close_attempts"]
    assert SpreadState.from_dict(old).close_reason is None
