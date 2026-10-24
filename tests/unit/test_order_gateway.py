"""core/orders/gateway.py -- against a fake Breeze client; nothing reaches a broker."""

import json
from datetime import date, datetime

from core.orders.checks import Intent
from core.orders.gateway import IST, Gateway

EXP = date(2026, 11, 23)
MON = datetime(2026, 10, 26, 10, 0, tzinfo=IST)


class FakeBreeze:
    def __init__(self, positions=(), bid=781.5, ask=782.0, fill_after=1):
        self.rows = list(positions)
        self.bid, self.ask = bid, ask
        self.calls = []
        self.fill_after = fill_after          # status checks before an order shows executed
        self.n = 0

    def get_portfolio_positions(self):
        return {"Status": 200, "Success": self.rows}

    def get_quotes(self, **kw):
        return {"Status": 200, "Success": [{"best_bid_price": self.bid, "best_offer_price": self.ask, "ltp": self.ask,
                                            "right": kw.get("right")}]}

    def get_names(self, **kw):
        return {"exchange_stock_code": "INDHOTEL"}

    def place_order(self, **kw):
        self.calls.append(("place", kw))
        return {"Status": 200, "Success": {"order_id": f"OID{len(self.calls)}"}}

    def gtt_three_leg_place_order(self, **kw):
        self.calls.append(("oco", kw))
        return {"Status": 200, "Success": {"gtt_order_id": "GTT1"}}

    def cancel_order(self, **kw):
        self.calls.append(("cancel", kw))
        return {"Status": 200}

    def get_order_detail(self, **kw):
        self.n += 1
        return {"Success": [{"status": "Executed" if self.n >= self.fill_after else "Ordered"}]}


def fut_row(qty=1000, action="Buy"):
    return {"stock_code": "INDHOT", "action": action, "quantity": str(qty), "average_price": "782",
            "product_type": "Futures", "expiry_date": "23-Nov-2026", "right": "Others", "strike_price": "0"}


def gw(client, tmp_path, live=True):
    g = Gateway(client, live=live, journal=tmp_path / "orders.jsonl", kill_switch=tmp_path / "ORDERS_OFF",
                clock=lambda: MON)
    g._lots["INDHOT"] = 1000
    return g


def entry(price=782.0):
    return Intent("icici-spouse", "futures", "INDHOT", EXP, "buy", 1000, price, "entry")


def test_paper_mode_journals_but_sends_nothing(tmp_path):
    b = FakeBreeze()
    r = gw(b, tmp_path, live=False).place(entry())
    assert r.ok and not r.sent and b.calls == []
    rec = json.loads((tmp_path / "orders.jsonl").read_text().splitlines()[0])
    assert rec["kind"] == "place" and rec["live"] is False and rec["ok"] is True


def test_refusals_never_reach_the_broker(tmp_path):
    b = FakeBreeze()
    g = gw(b, tmp_path)
    assert not g.place(entry(price=820.0)).ok                         # 5% over the ask
    (tmp_path / "ORDERS_OFF").write_text("")
    r = g.place(entry())
    assert not r.ok and any("kill switch" in x for x in r.reasons)
    assert b.calls == []
    assert len((tmp_path / "orders.jsonl").read_text().splitlines()) == 2


def test_live_place_sends_breeze_fields(tmp_path):
    b = FakeBreeze()
    r = gw(b, tmp_path).place(entry())
    assert r.ok and r.sent and r.order_id == "OID1"
    kw = b.calls[0][1]
    assert (kw["product"], kw["action"], kw["order_type"], kw["quantity"], kw["price"], kw["right"], kw["strike_price"]) \
        == ("futures", "buy", "limit", "1000", "782.00", "others", "0")
    assert kw["expiry_date"] == "2026-11-23T06:00:00.000Z" and kw["validity"] == "day"


def test_oco_on_an_open_long(tmp_path):
    b = FakeBreeze(positions=[fut_row()])
    tgt = Intent("icici-spouse", "futures", "INDHOT", EXP, "sell", 1000, 835.0, "target", trigger=835.0, gtt=True)
    stp = Intent("icici-spouse", "futures", "INDHOT", EXP, "sell", 1000, 728.0, "stop", trigger=735.0, gtt=True)
    r = gw(b, tmp_path).place_oco(tgt, stp)
    assert r.ok and r.order_id == "GTT1"
    kw = b.calls[0][1]
    assert kw["gtt_type"] == "oco" and kw["quantity"] == "1000"
    assert [(d["gtt_leg_type"], d["action"], d["trigger_price"]) for d in kw["order_details"]] == \
        [("target", "sell", "835.00"), ("stoploss", "sell", "735.00")]


def test_oco_refused_without_a_position_or_with_mismatched_legs(tmp_path):
    b = FakeBreeze()
    tgt = Intent("icici-spouse", "futures", "INDHOT", EXP, "sell", 1000, 835.0, "target", trigger=835.0, gtt=True)
    stp = Intent("icici-spouse", "futures", "INDHOT", EXP, "sell", 1000, 728.0, "stop", trigger=735.0, gtt=True)
    assert not gw(b, tmp_path).place_oco(tgt, stp).ok                 # nothing held: would open a short
    b.rows = [fut_row()]
    half = Intent(**{**stp.__dict__, "qty": 2000})
    r = gw(b, tmp_path).place_oco(tgt, half)
    assert not r.ok and b.calls == []


def test_work_exit_reprices_until_filled(tmp_path):
    b = FakeBreeze(positions=[fut_row()], fill_after=12)               # not filled in the first 10 s window
    ex = Intent("icici-spouse", "futures", "INDHOT", EXP, "sell", 1000, 781.5, "exit")
    r = gw(b, tmp_path).work_exit(ex, tries=3, wait_s=10, sleep=lambda s: None)
    assert r.ok
    kinds = [c[0] for c in b.calls]
    assert kinds == ["place", "cancel", "place"]                      # one re-price, then filled
    assert b.calls[0][1]["price"] == "781.50" and b.calls[0][1]["action"] == "sell"


def test_work_exit_cannot_oversell(tmp_path):
    b = FakeBreeze(positions=[fut_row(qty=1000)])
    ex = Intent("icici-spouse", "futures", "INDHOT", EXP, "sell", 2000, 781.5, "exit")
    r = gw(b, tmp_path).work_exit(ex, tries=2, wait_s=1, sleep=lambda s: None)
    assert not r.ok and b.calls == []
