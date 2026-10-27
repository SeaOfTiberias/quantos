"""core/orders/gateway.py -- against a fake Breeze client; nothing reaches a broker."""

import json
from datetime import date, datetime, timedelta

from core.orders.checks import Intent
from core.orders.gateway import IST, Gateway, tick_from_master

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
                clock=lambda: MON, fo_master=tmp_path / "no_master.csv")
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


class BreezeQuotesLikeLive(FakeBreeze):
    """Live quote rows label the right "P"/"C" (2026-10-26); the first n calls fail like Breeze's empty body."""
    def __init__(self, fail_first=0, **kw):
        super().__init__(**kw)
        self.fail_first = fail_first

    def get_quotes(self, **kw):
        if self.fail_first:
            self.fail_first -= 1
            raise Exception("Error in get_quotes(): Expecting value: line 1 column 1 (char 0)")
        return {"Status": 200, "Success": [{"best_bid_price": 22.5, "best_offer_price": 22.65, "ltp": 22.8,
                                            "right": "P", "strike_price": 700.0}]}


def put_leg():
    return Intent("icici-spouse", "options", "HDFBAN", EXP, "buy", 650, 22.65, "entry", right="put", strike=700.0)


def test_option_quote_matches_breeze_single_letter_right(tmp_path):
    q = gw(BreezeQuotesLikeLive(), tmp_path).quote(put_leg())
    assert (q["bid"], q["ask"]) == (22.5, 22.65)


def test_option_quote_retries_an_empty_body(tmp_path, monkeypatch):
    monkeypatch.setattr("core.orders.gateway.time.sleep", lambda s: None)
    q = gw(BreezeQuotesLikeLive(fail_first=2), tmp_path).quote(put_leg())
    assert q["ask"] == 22.65


# ── contract tick (27-Oct: SUPIND FUT is 0.10; the code assumed 0.05) ───────────

NOV_EPOCH = "1795428600"          # 23-Nov-2026 10:00 UTC, as Fyers' master writes it


def master_row(sym, tick, opt="XX", strike="-1.0"):
    # synthetic NSE_FO master row: col 4 tick, 8 expiry epoch, 13 underlying, 15 strike, 16 CE/PE/XX
    return ",".join(["1", f"{sym} 23 Nov 26", "13", "100", tick, "", "", "2026-10-23", NOV_EPOCH,
                     f"NSE:{sym}X", "10", "11", "1", sym, "1", strike, opt, "1", "None", "0", "0.0"])


def test_tick_from_master(tmp_path):
    f = tmp_path / "m.csv"
    f.write_text("\n".join([master_row("INDHOTEL", "0.1"), master_row("INDHOTEL", "0.05", "PE", "780.0"),
                            master_row("OTHER", "1.0")]) + "\n")
    assert tick_from_master(f, "INDHOTEL", EXP) == 0.1
    assert tick_from_master(f, "INDHOTEL", EXP, "put", 780.0) == 0.05
    assert tick_from_master(f, "INDHOTEL", date(2026, 12, 28)) is None


class TickyBreeze(FakeBreeze):
    """Refuses any price off a 0.10 step, the way ICICI did on 27-Oct."""

    def gtt_three_leg_place_order(self, **kw):
        self.calls.append(("oco", kw))
        for d in kw["order_details"]:
            for k in ("limit_price", "trigger_price"):
                if round(float(d[k]) * 10, 6) % 1:
                    return {"Success": None, "Status": 500, "Error": "Price should be in multiples of: 0.10"}
        return {"Status": 200, "Success": {"gtt_order_id": "GTT2"}}


def short_oco():
    tgt = Intent("icici-spouse", "futures", "INDHOT", EXP, "buy", 1000, 3150.47, "target", trigger=3150.47, gtt=True)
    stp = Intent("icici-spouse", "futures", "INDHOT", EXP, "buy", 1000, 3476.65, "stop", trigger=3442.23, gtt=True)
    return tgt, stp


def test_oco_snaps_to_the_master_tick(tmp_path):
    b = TickyBreeze(positions=[fut_row(action="Sell")])
    g = gw(b, tmp_path)
    (tmp_path / "no_master.csv").write_text(master_row("INDHOTEL", "0.1") + "\n")
    r = g.place_oco(*short_oco())
    assert r.ok and r.order_id == "GTT2" and len(b.calls) == 1
    legs = b.calls[0][1]["order_details"]
    assert [(d["limit_price"], d["trigger_price"]) for d in legs] == [("3150.50", "3150.50"), ("3476.70", "3442.30")]


def test_oco_learns_the_tick_from_the_refusal_and_goes_once_more(tmp_path):
    b = TickyBreeze(positions=[fut_row(action="Sell")])                # no master: starts at 0.05
    r = gw(b, tmp_path).place_oco(*short_oco())
    assert r.ok and [c[0] for c in b.calls] == ["oco", "oco"]
    assert b.calls[1][1]["order_details"][1]["trigger_price"] == "3442.30"


def test_a_refusal_that_isnt_about_the_tick_is_not_retried(tmp_path):
    class Denied(FakeBreeze):
        def gtt_three_leg_place_order(self, **kw):
            self.calls.append(("oco", kw))
            return {"Status": 5, "Error": "Request Denied: The IP address used does not match"}
    b = Denied(positions=[fut_row(action="Sell")])
    r = gw(b, tmp_path).place_oco(*short_oco())
    assert not r.ok and len(b.calls) == 1


# ── GTT book (27-Oct: 30-day range refused; the id sits on the legs) ─────────────

class BookBreeze(FakeBreeze):
    def __init__(self, book=(), status=200, **kw):
        super().__init__(**kw)
        self.book, self.status, self.ranges = list(book), status, []

    def gtt_order_book(self, exchange_code, from_date, to_date):
        f, t = date.fromisoformat(from_date[:10]), date.fromisoformat(to_date[:10])
        self.ranges.append((f, t))
        if (t - f).days > 10:
            return {"Success": None, "Status": 500,
                    "Error": "Number of days between from_date & to_date should not be more than 10"}
        if self.status != 200:
            return {"Success": None, "Status": self.status, "Error": "down"}
        return {"Status": 200, "Success": self.book if t == MON.date() else []}


def book_row(gid="GTT9", action="Buy", qty=1000, status="Active"):
    return {"order_details": [{"gtt_leg_type": "Target", "action": action, "trigger_price": 3150.4,
                               "limit_price": 3150.4, "status": status, "gtt_order_id": gid},
                              {"gtt_leg_type": "Stoploss", "action": action, "trigger_price": 3440.0,
                               "limit_price": 3474.4, "status": status, "gtt_order_id": gid}],
            "exchange_code": "NFO", "product_type": "Futures", "stock_code": "INDHOT", "expiry_date": "23-Nov-2026",
            "strike_price": 0.0, "right": "Others", "quantity": qty, "gtt_type": "OCO"}


def test_gtt_book_reads_30_days_in_10_day_windows(tmp_path):
    b = BookBreeze(book=[book_row()])
    assert len(gw(b, tmp_path).gtt_book()) == 1
    assert len(b.ranges) == 3 and all((t - f).days <= 9 for f, t in b.ranges)
    assert b.ranges[0][1] == MON.date() and b.ranges[1][1] == b.ranges[0][0] - timedelta(days=1)


def test_an_unreadable_gtt_book_raises_rather_than_reading_empty(tmp_path):
    import pytest
    with pytest.raises(RuntimeError):
        gw(BookBreeze(status=500), tmp_path).verify_gtt("GTT9")


def test_verify_gtt_finds_the_id_on_the_legs_and_skips_finished_ones(tmp_path):
    assert gw(BookBreeze(book=[book_row()]), tmp_path).verify_gtt("GTT9") is not None
    assert gw(BookBreeze(book=[book_row(status="Cancelled")]), tmp_path).verify_gtt("GTT9") is None
    assert gw(BookBreeze(book=[book_row()]), tmp_path).verify_gtt("GTT1") is None


def test_find_gtt_matches_contract_side_and_qty(tmp_path):
    g = gw(BookBreeze(book=[book_row()]), tmp_path)
    assert g.find_gtt("INDHOT", EXP, "buy", 1000) == "GTT9"
    assert g.find_gtt("INDHOT", EXP, "sell", 1000) is None             # closes a long: not this one
    assert g.find_gtt("INDHOT", EXP, "buy", 2000) is None
    assert g.find_gtt("INDHOT", date(2026, 12, 28), "buy", 1000) is None
    assert gw(BookBreeze(book=[book_row(status="Executed")]), tmp_path).find_gtt("INDHOT", EXP, "buy", 1000) is None


def test_gtt_book_retries_an_empty_body_and_reads_no_data_as_empty(tmp_path, monkeypatch):
    # 27-Oct on the VM: one window raised "Expecting value", then answered seconds later
    monkeypatch.setattr("core.orders.gateway.time.sleep", lambda s: None)

    class Flaky(BookBreeze):
        fails = 1

        def gtt_order_book(self, **kw):
            if self.fails:
                self.fails -= 1
                raise Exception("Error in gtt_order_book(): Expecting value: line 1 column 1 (char 0)")
            if kw["to_date"][:10] != MON.date().isoformat():
                return {"Success": None, "Status": 500, "Error": "No Data Found"}
            return super().gtt_order_book(**kw)
    assert gw(Flaky(book=[book_row()]), tmp_path).verify_gtt("GTT9") is not None
