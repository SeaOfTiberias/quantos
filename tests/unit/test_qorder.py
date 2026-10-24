"""scripts/qorder.py -- nothing goes without --yes, and spread legs go in the safe order."""

from datetime import datetime

import pytest

import core.orders.gateway as gw_mod
import scripts.qorder as q
from tests.unit.test_order_gateway import FakeBreeze

MON = datetime(2026, 10, 26, 10, 0, tzinfo=gw_mod.IST)


class OptBreeze(FakeBreeze):
    """Quotes by strike; positions follow the fills, so the short leg sees the long leg it needs."""
    QUOTES = {820.0: (12.9, 13.1), 860.0: (5.3, 5.5)}

    def get_quotes(self, **kw):
        bid, ask = self.QUOTES.get(float(kw.get("strike_price") or 0), (self.bid, self.ask))
        return {"Status": 200, "Success": [{"best_bid_price": bid, "best_offer_price": ask, "right": kw.get("right")}]}

    def place_order(self, **kw):
        r = super().place_order(**kw)
        qty = int(kw["quantity"]) * (1 if kw["action"] == "buy" else -1)
        self.rows.append({"stock_code": kw["stock_code"], "action": "Buy" if qty > 0 else "Sell",
                          "quantity": str(abs(qty)), "product_type": "Options", "expiry_date": "23-Nov-2026",
                          "right": kw["right"].capitalize(), "strike_price": kw["strike_price"]})
        return r


@pytest.fixture
def broker(tmp_path, monkeypatch):
    b = OptBreeze(fill_after=1)
    monkeypatch.setattr(q.breeze_auth, "connect", lambda: b)
    monkeypatch.setattr(q, "orders_cfg", lambda: {"live": True})
    monkeypatch.setattr(gw_mod, "JOURNAL", tmp_path / "orders.jsonl")
    monkeypatch.setattr(gw_mod, "KILL_SWITCH", tmp_path / "ORDERS_OFF")

    real = gw_mod.Gateway.__init__

    def init(self, client, **kw):
        real(self, client, journal=tmp_path / "orders.jsonl", kill_switch=tmp_path / "ORDERS_OFF",
             clock=lambda: MON, **{k: v for k, v in kw.items() if k not in ("journal", "kill_switch", "clock")})
        self._lots["INDHOT"] = 1000
    monkeypatch.setattr(gw_mod.Gateway, "__init__", init)
    monkeypatch.setattr(gw_mod.time, "sleep", lambda s: None)
    return b


def test_without_yes_nothing_is_sent(broker, capsys):
    assert q.main(["buy", "INDHOT", "2026-11-23", "1000", "13.1", "--right", "call", "--strike", "820"]) == 0
    assert broker.calls == [] and "Not sent" in capsys.readouterr().out


def test_spread_open_buys_the_long_leg_first(broker):
    assert q.main(["spread-open", "INDHOT", "2026-11-23", "call", "820", "860", "1000", "--max-debit", "8", "--yes"]) == 0
    sent = [(c[1]["action"], c[1]["strike_price"], c[1]["price"]) for c in broker.calls if c[0] == "place"]
    assert sent == [("buy", "820", "13.10"), ("sell", "860", "5.30")]


def test_spread_open_refused_over_max_debit(broker):
    assert q.main(["spread-open", "INDHOT", "2026-11-23", "call", "820", "860", "1000", "--max-debit", "5", "--yes"]) == 1
    assert broker.calls == []


def test_spread_close_buys_back_the_short_first(broker):
    broker.rows = [
        {"stock_code": "INDHOT", "action": "Buy", "quantity": "1000", "product_type": "Options",
         "expiry_date": "23-Nov-2026", "right": "Call", "strike_price": "820"},
        {"stock_code": "INDHOT", "action": "Sell", "quantity": "1000", "product_type": "Options",
         "expiry_date": "23-Nov-2026", "right": "Call", "strike_price": "860"}]
    broker.place_order = lambda **kw: (broker.calls.append(("place", kw)),
                                       {"Status": 200, "Success": {"order_id": "X"}})[1]
    assert q.main(["spread-close", "INDHOT", "2026-11-23", "call", "820", "860", "1000", "--yes"]) == 0
    sent = [(c[1]["action"], c[1]["strike_price"]) for c in broker.calls if c[0] == "place"]
    assert sent == [("buy", "860"), ("sell", "820")]


def test_a_naked_short_is_refused(broker):
    assert q.main(["sell", "INDHOT", "2026-11-23", "1000", "5.3", "--right", "call", "--strike", "860", "--yes"]) == 1
    assert broker.calls == []
