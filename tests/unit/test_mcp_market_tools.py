"""core/mcp_tools/market.py -- the T0 market tools, against a fake market."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from core.brokers.base import OHLCV
from core.fno_screener.bhavcopy import FnoDay, OptionQuote
from core.ideas.structure import Chain, Quote
from core.mcp_tools import market as mt
from core.options.models import OptionType

IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST).date()
EXP = TODAY + timedelta(days=30)


class FakeMarket:
    def __init__(self):
        start = datetime.combine(TODAY - timedelta(days=400), datetime.min.time(), tzinfo=IST)
        self.bars = [OHLCV(timestamp=start + timedelta(days=i), open=100 + i * 0.1, high=101 + i * 0.1,
                           low=99 + i * 0.1, close=100 + i * 0.1, volume=1000) for i in range(300)]

    def quotes(self, names):
        return {n: {"lp": 105.0, "prev_close_price": 100.0, "bid": 104.9, "ask": 105.1, "tt": 1_760_000_000}
                for n in names}

    def daily(self, symbol, days):
        return self.bars

    def chain(self, symbol, steps):
        ch = Chain(symbol=symbol, spot=1000.0, lot=100, today=TODAY)
        for k, ce, pe in ((960, (50, 51), (8, 8.5)), (1000, (24, 25), (22, 23)), (1040, (9, 9.5), (48, 49))):
            ch.options[(EXP, float(k), "CE")] = Quote(*ce)
            ch.options[(EXP, float(k), "PE")] = Quote(*pe)
        ch.futures[EXP] = Quote(1004, 1005)
        return ch

    def fno_day(self, d):
        if d.weekday() >= 5:
            return None
        n = (TODAY - d).days
        q = [OptionQuote("ABC", EXP, 1000.0, OptionType.CALL, 24.0, 300, 900, 100)]
        return FnoDay(trade_date=d, spot={"ABC": 1000.0 - n}, futures_oi={"ABC": {EXP: 10000 + 500 * (10 - n)}},
                      options={"ABC": q})


def test_quote_and_index_mapping():
    (q,) = mt.quote(FakeMarket(), ["nifty"])
    assert q["fyers"] == "NSE:NIFTY50-INDEX" and q["chg_pct"] == 5.0 and q["time"]
    assert mt.fyers_symbol("TCS") == "NSE:TCS-EQ"


def test_levels_uses_completed_sessions():
    lv = mt.levels(FakeMarket(), "abc")
    assert lv["symbol"] == "ABC" and lv["atr14"] > 0 and lv["trend"] == "up"
    assert lv["as_of"] < TODAY.isoformat() and len(lv["recent"]) == 10
    assert lv["high_52w"] >= lv["close"] >= lv["low_52w"]


def test_option_chain_rows_iv_and_bhav_oi():
    oc = mt.option_chain(FakeMarket(), "ABC", right="CE")
    assert oc["expiry"] == EXP.isoformat() and [r["strike"] for r in oc["rows"]] == [960.0, 1000.0, 1040.0]
    atm = oc["rows"][1]
    assert atm["oi_lots_prev"] == 300 and atm["iv_pct"] and 0 < atm["spread_pct"] < 5
    assert oc["rows"][0]["itm"] and not oc["rows"][2]["itm"]


def test_price_spread_fills_at_ask_and_bid():
    sp = mt.price_spread(FakeMarket(), "ABC", EXP.isoformat(), "CE", 1000, 1040)
    assert sp["debit"] == pytest.approx(25 - 9) and sp["max_loss"] == 1600 and sp["max_profit"] == 2400
    assert sp["breakeven"] == pytest.approx(1016) and sp["round_trip_cost_pct"] > 0
    assert "error" in mt.price_spread(FakeMarket(), "ABC", EXP.isoformat(), "CE", 1040, 1000)


def test_pick_structure_returns_families():
    ps = mt.pick_structure(FakeMarket(), "ABC", "bull", target=1060, stop=980, days=3)
    fams = {r["structure"].split()[0] for r in ps["best_by_family"]}
    assert ps["best_by_family"] and ("long" in fams or "bull" in fams) and ps["view"]["gap_pct"] == 3.5


def test_oi_buildup_from_bhavcopies():
    b = mt.oi_buildup(FakeMarket(), "ABC")
    assert b["label"] == "long build-up" and b["price_chg_pct"] > 0 and b["oi_chg_pct"] > 0


def test_screener_and_ideas_files(tmp_path):
    (tmp_path / "fno_screener_latest.json").write_text(json.dumps({"trade_date": "2026-10-22", "calls": [], "puts": [
        {"symbol": "PFC", "side": "PE", "close": 326.9, "breakout_state": "OUT", "days_out": 4, "box_level": 336.3,
         "atr": 8.8, "oi": {"label": "short build-up"}, "contract": None}]}))
    s = mt.screener(tmp_path)
    assert s["puts"][0]["symbol"] == "PFC" and s["puts"][0]["oi"] == "short build-up"
    (tmp_path / "trade_ideas.json").write_text(json.dumps([
        {"id": "a", "symbol": "TCS", "action": "enter_if", "eval": {"status": "watching"}},
        {"id": "b", "symbol": "TCS", "action": "enter_now", "eval": {"status": "closed"}}]))
    assert [i["id"] for i in mt.ideas(tmp_path, "tcs", open_only=True)] == ["a"]
