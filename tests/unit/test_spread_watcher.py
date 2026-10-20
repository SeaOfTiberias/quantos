"""core/spread_watcher (legs, payoff, rules) and scripts/run_spread_watcher.py with a fake Breeze client."""

from datetime import date, time

import pytest

from core.spread_watcher.legs import Leg, Spread, group_legs, parse_leg
from core.spread_watcher.rules import SpreadRules, SpreadState, evaluate, payoff

OCT27 = date(2026, 10, 27)
R = SpreadRules()


def row(action, right, strike, qty=600, price=0.0, code="TECMAH", expiry="27-Oct-2026", product="Options"):
    return {"stock_code": code, "exchange_code": "NFO", "product_type": product, "expiry_date": expiry,
            "right": right, "strike_price": str(strike), "action": action, "quantity": str(qty),
            "average_price": str(price)}


def techm() -> Spread:
    return Spread(long=Leg("TECMAH", OCT27, "call", 1740.0, 600, 45.50),
                  short=Leg("TECMAH", OCT27, "call", 1800.0, -600, 19.20))


# ─── legs ────────────────────────────────────────────────────────────────────

def test_parse_leg_breeze_shapes():
    long_ = parse_leg(row("Buy", "Call", 1740, price=45.5))
    short = parse_leg(row("Sell", "Call", 1800, price=19.2))
    assert long_ == Leg("TECMAH", OCT27, "call", 1740.0, 600, 45.5)
    assert short.qty == -600 and short.label == "1800 CE"
    assert parse_leg({**row("Sell", "P", 700), "expiry_date": "2026-10-27T06:00:00.000Z"}).right == "put"
    assert parse_leg(row("Buy", "Call", 1740, product="Cash")) is None
    assert parse_leg(row("Buy", "Others", 0)) is None
    assert parse_leg({**row("Buy", "Call", 1740), "average_price": None, "average_cost": "12.85"}).avg_price == 12.85


def test_grouping_spread_naked_and_partial():
    legs = [parse_leg(row("Buy", "Call", 1740, price=45.5)), parse_leg(row("Sell", "Call", 1800, price=19.2))]
    spreads, naked, lone = group_legs(legs)
    assert len(spreads) == 1 and spreads[0].kind == "bull call" and not naked and not lone
    # 2026-10-19: the long leg closed, the short left behind
    spreads, naked, lone = group_legs(legs[1:])
    assert not spreads and naked[0].strike == 1800
    # 2 lots long vs 1 short: one spread plus a lone long lot
    spreads, naked, lone = group_legs([parse_leg(row("Buy", "Put", 710, qty=1300, price=17.4)),
                                       parse_leg(row("Sell", "Put", 670, qty=650, price=5.9))])
    assert spreads[0].kind == "bear put" and spreads[0].qty == 650 and lone[0].qty == 650 and not naked
    # different stocks never pair
    spreads, naked, _ = group_legs([parse_leg(row("Buy", "Call", 1740)), parse_leg(row("Sell", "Call", 1800, code="INFTEC"))])
    assert not spreads and len(naked) == 1


# ─── payoff ──────────────────────────────────────────────────────────────────

def test_payoff_debit_and_credit():
    p = payoff(techm())
    assert (p.max_profit, p.max_loss, p.breakeven, p.bullish) == (20220.0, 15780.0, 1766.3, True)
    bear_put = Spread(Leg("HDFBAN", OCT27, "put", 710.0, 650, 17.4), Leg("HDFBAN", OCT27, "put", 670.0, -650, 5.9))
    p = payoff(bear_put)
    assert p.max_profit == pytest.approx(18525) and p.breakeven == pytest.approx(698.5) and not p.bullish
    bear_call = Spread(Leg("TECMAH", OCT27, "call", 1840.0, 600, 6.1), Leg("TECMAH", OCT27, "call", 1800.0, -600, 22.0))
    p = payoff(bear_call)
    assert bear_call.kind == "bear call" and p.entry == pytest.approx(-15.9)
    assert p.max_profit == pytest.approx(15.9 * 600) and p.max_loss == pytest.approx(24.1 * 600)
    assert p.breakeven == pytest.approx(1815.9) and not p.bullish


# ─── rules ───────────────────────────────────────────────────────────────────

def ev(st, spot, value, day=date(2026, 10, 19), at=time(10, 0)):
    return [e.kind for e in evaluate(st, spot, value, day, at, R)]


def test_techm_replay_stock_trail_fires():
    """19-Oct as it happened: +Rs2,190 at the open, +Rs3,300 by 09:53, then
    TechM slid. Best P&L was 16% of max, under the 20% give-back arm, so the
    stock trail is what fires: 0.8% behind the 1,790 best = 1,775.68."""
    st = SpreadState.open(techm())
    assert ev(st, 1789.0, 29.95) == ["trail_armed"]
    assert ev(st, 1790.0, 31.80) == [] and st.peak_pnl == pytest.approx(3300)
    assert st.stock_stop == pytest.approx(1775.68)
    assert ev(st, 1779.0, 28.0) == []
    out = evaluate(st, 1775.5, 27.2, date(2026, 10, 19), time(11, 0), R)
    assert [e.kind for e in out] == ["trail_stock"] and out[0].close
    assert ev(st, 1770.0, 26.0) == []                        # fires once


def test_giveback_arms_at_20pct_and_fires_at_half():
    st = SpreadState.open(techm())
    ev(st, 1800.0, 26.30 + 7000 / 600)                         # +7,000 > 20% of 20,220
    assert "giveback" in ev(st, 1799.0, 26.30 + 3400 / 600)     # <= half of 7,000
    st2 = SpreadState.open(techm())
    ev(st2, 1790.0, 26.30 + 3300 / 600)                         # +3,300 < 4,044: not armed
    assert "giveback" not in ev(st2, 1789.0, 26.30 + 100 / 600)


def test_breakeven_rearms_and_near_max():
    st = SpreadState.open(techm())
    ev(st, 1785.0, 30.0)
    assert "breakeven" in ev(st, 1765.0, 25.0)
    assert "breakeven" not in ev(st, 1764.0, 24.5)
    ev(st, 1770.0, 27.0)
    assert "breakeven" in ev(st, 1760.0, 24.0)
    st2 = SpreadState.open(techm())
    assert "near_max" in ev(st2, 1830.0, 26.30 + 18300 / 600)


def test_exit_day_from_0930_the_session_before_expiry():
    st = SpreadState.open(techm())
    assert "exit_day" not in ev(st, 1790.0, 30.0, day=date(2026, 10, 23), at=time(10, 0))   # Fri: 2 sessions left
    assert "exit_day" not in ev(st, 1790.0, 30.0, day=date(2026, 10, 26), at=time(9, 20))
    assert "exit_day" in ev(st, 1790.0, 30.0, day=date(2026, 10, 26), at=time(9, 31))


def test_user_level_and_bearish_trail():
    st = SpreadState.open(techm())
    st.level = 1775.0
    assert ev(st, 1780.0, 24.0) == [] and st.stock_stop == 1775.0       # no profit needed for a set level
    assert ev(st, 1774.0, 23.0) == ["trail_stock"]
    bear = SpreadState.open(Spread(Leg("HDFBAN", OCT27, "put", 710.0, 650, 17.4),
                                   Leg("HDFBAN", OCT27, "put", 670.0, -650, 5.9)))
    ev(bear, 700.0, 13.0)                                                # in profit: best = 700
    ev(bear, 695.0, 15.0)
    assert bear.stock_stop == pytest.approx(695 * 1.008)
    assert "trail_stock" in ev(bear, 701.0, 12.5)


def test_state_roundtrip():
    st = SpreadState.open(techm())
    ev(st, 1790.0, 31.8)
    assert SpreadState.from_dict(st.to_dict()) == st


# ─── script, with a fake Breeze ──────────────────────────────────────────────

class FakeBreeze:
    def __init__(self, rows, spot, quotes):
        self.rows, self.spot, self.quotes = rows, spot, quotes

    def get_portfolio_positions(self):
        return {"Status": 200, "Success": self.rows or None, "Error": None if self.rows else "No Positions available."}

    def get_quotes(self, stock_code, exchange_code, expiry_date, product_type, right, strike_price):
        if exchange_code == "NSE":
            return {"Status": 200, "Success": [{"exchange_code": "NSE", "ltp": self.spot}]}
        bid, ask = self.quotes[float(strike_price)]
        return {"Status": 200, "Success": [{"best_bid_price": bid, "best_offer_price": ask, "ltp": (bid + ask) / 2}]}


def test_watcher_end_to_end(tmp_path, monkeypatch):
    import scripts.run_spread_watcher as w
    monkeypatch.setattr(w, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(w, "LEVELS_PATH", tmp_path / "levels.json")
    sent = []
    notifier = w.Notifier(enabled=False)
    monkeypatch.setattr(notifier, "send", sent.append)
    fake = FakeBreeze([row("Buy", "Call", 1740, price=45.5), row("Sell", "Call", 1800, price=19.2)],
                      1790.0, {1740.0: (53.75, 54.55), 1800.0: (21.7, 21.95)})
    watcher = w.SpreadWatcher(SpreadRules(), notifier)
    watcher.client = fake
    watcher.refresh_positions()
    watcher.price_spreads()
    assert sent[0].startswith("👀 Watching TECMAH bull call 1740/1800 CE 27-Oct ×600")
    assert "max loss ₹15,780" in sent[0] and "breakeven 1,766.30" in sent[0]
    assert "trail armed" in sent[1]
    st = watcher.states[techm().key]
    assert st.last_pnl == pytest.approx((53.75 - 21.95 - 26.30) * 600)
    fake.spot, fake.quotes = 1775.0, {1740.0: (46.0, 46.5), 1800.0: (18.9, 19.1)}
    watcher.price_spreads()
    assert sent[-1].startswith("🔴 CLOSE") and "SELL 1740 CE @ bid 46.00, BUY 1800 CE @ ask 19.10" in sent[-1]
    # long leg closed, short left: spread gone + uncovered-short warning
    fake.rows = fake.rows[1:]
    watcher.refresh_positions()
    assert any(m.startswith("✅ TECMAH bull call") for m in sent)
    assert sent[-1].startswith("🚨 UNCOVERED SHORT: TECMAH 1800 CE")
    # a restart reloads the state file; a spread closed while down is reported once
    fake.rows = [row("Buy", "Call", 1740, price=45.5), row("Sell", "Call", 1800, price=19.2)]
    watcher.refresh_positions()
    fresh = w.SpreadWatcher(SpreadRules(), notifier)
    fresh.client = FakeBreeze([], 1790.0, {})
    fresh.refresh_positions()
    assert sent[-1].startswith("✅ TECMAH") and not fresh.states
