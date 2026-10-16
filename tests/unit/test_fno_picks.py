"""
core/fno_screener/spreads.py, core/fno_screener/outcomes.py and the
GET /fno-picks route (cloud/api/fno_picks_routes.py).
"""

import dataclasses
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.fno_screener.bhavcopy import FnoDay, OptionQuote
from core.fno_screener.outcomes import pick_key, returns_at, summarize, track_pick
from core.fno_screener.spreads import COST_FLAG_PCT, build_spreads, spread_line
from core.options.models import OptionType

CE, PE = OptionType.CALL, OptionType.PUT
D0 = date(2026, 10, 16)
NOV = date(2026, 11, 23)
LOT = 400


def _day(d: date, spot: float, prices: dict) -> FnoDay:
    """prices: {(strike, side): close}"""
    opts = [OptionQuote("AAA", NOV, k, side, close, 100, 50, LOT) for (k, side), close in prices.items()]
    return FnoDay(trade_date=d, spot={"AAA": spot}, futures_oi={"AAA": {NOV: 1}}, options={"AAA": opts})


CALLS = {(k, CE): c for k, c in [(960, 62.0), (980, 48.0), (1000, 36.0), (1020, 26.0), (1040, 18.0),
                                  (1060, 12.0), (1080, 8.0), (1100, 5.0), (1120, 3.0), (1140, 2.0)]}
PUTS = {(k, PE): c for k, c in [(1040, 52.0), (1020, 40.0), (1000, 30.0), (980, 22.0), (960, 15.0),
                                 (940, 10.0), (920, 6.5), (900, 4.0), (880, 2.5)]}


def test_bull_call_strikes_scale_with_expected_move():
    s = build_spreads(_day(D0, 1000.0, CALLS), "AAA", CE, NOV, 980.0, 38, 0.30)
    # expected move = 1000 x 0.30 x sqrt(38/365) ~ 96.8 -> targets ~1048 / 1097 / 1145
    assert [i.short_strike for i in s.ideas] == [1040.0, 1100.0, 1140.0]
    near = s.ideas[0]
    assert near.priced_from == "close" and near.cost_pct is None and not near.cost_flag
    assert near.debit == pytest.approx(30.0) and near.max_loss == 30 * LOT
    assert near.max_profit == (60 - 30) * LOT and near.reward_risk == pytest.approx(1.0)
    assert near.breakeven == pytest.approx(1010.0) and near.breakeven_move_pct == pytest.approx(1.0)
    assert s.kind == "bull_call" and not s.iv_assumed


def test_quotes_price_at_bid_ask_and_flag_cost():
    quotes = {980.0: (47.0, 49.0), 1040.0: (17.0, 19.0), 1100.0: (4.9, 5.1), 1140.0: (0.0, 2.2)}
    s = build_spreads(_day(D0, 1000.0, CALLS), "AAA", CE, NOV, 980.0, 38, 0.30, quotes)
    near, mid, far = s.ideas
    assert near.priced_from == "quotes" and near.debit == pytest.approx(49.0 - 17.0)
    # mid debit 48 - 18 = 30, real 32 -> round trip 2 x 2 / 32
    assert near.cost_pct == pytest.approx(12.5) and near.cost_flag == (12.5 > COST_FLAG_PCT)
    assert mid.priced_from == "quotes"
    assert far.priced_from == "close"                     # 1140 has no bid: not two-sided


def test_bear_put_mirrors():
    s = build_spreads(_day(D0, 1000.0, PUTS), "AAA", PE, NOV, 1020.0, 38, 0.30)
    assert s.kind == "bear_put"
    assert all(i.short_strike < 1020 for i in s.ideas)
    i = s.ideas[0]
    assert i.breakeven == pytest.approx(1020 - i.debit) and i.breakeven_move_pct < 0 and i.target_move_pct < 0


def test_missing_long_leg_or_iv():
    assert build_spreads(_day(D0, 1000.0, CALLS), "AAA", CE, NOV, 990.0, 38, 0.3) is None
    s = build_spreads(_day(D0, 1000.0, CALLS), "AAA", CE, NOV, 980.0, 38, None)
    assert s.iv_assumed and s.ideas
    assert "bull call: buy 980 / sell" in spread_line(s)


def _cand(spreads):
    return {"symbol": "AAA", "side": "CE", "close": 1000.0,
            "contract": {"quote": {"expiry": NOV.isoformat(), "strike": 980.0, "close": 48.0, "lot_size": LOT},
                         "dte": 38, "iv": 0.3},
            "spreads": dataclasses.asdict(spreads)}


def test_track_pick_and_returns():
    s = build_spreads(_day(D0, 1000.0, CALLS), "AAA", CE, NOV, 980.0, 38, 0.30)
    up = {k: v * 1.5 for k, v in CALLS.items()}
    days = [_day(date(2026, 10, 19), 1030.0, up), _day(date(2026, 10, 20), 1010.0, CALLS)]
    o = track_pick("2026-10-16", _cand(s), days)
    assert o["key"] == pick_key("2026-10-16", "CE", "AAA") and not o["complete"] and len(o["sessions"]) == 2
    r1 = returns_at(o, 1)
    assert r1["stock_pct"] == pytest.approx(3.0) and r1["option_pct"] == pytest.approx(50.0)
    assert r1["spreads"]["near"] == pytest.approx(50.0)   # (72 - 27) / 30 - 1
    assert returns_at(o, 3) is None
    st = summarize([o])
    assert st["CE"]["picks"] == 1 and st["CE"]["horizons"]["1"]["option"]["n"] == 1
    assert st["PE"]["picks"] == 0 and st["PE"]["horizons"]["1"]["option"] is None


def test_put_stock_move_is_signed_for_the_pick():
    s = build_spreads(_day(D0, 1000.0, PUTS), "AAA", PE, NOV, 1020.0, 38, 0.30)
    cand = {**_cand(s), "side": "PE",
            "contract": {"quote": {"expiry": NOV.isoformat(), "strike": 1020.0, "close": 40.0, "lot_size": LOT}}}
    o = track_pick("2026-10-16", cand, [_day(date(2026, 10, 19), 980.0, PUTS)])
    assert returns_at(o, 1)["stock_pct"] == pytest.approx(2.0)


def test_route_reads_the_files(tmp_path, monkeypatch):
    s = build_spreads(_day(D0, 1000.0, CALLS), "AAA", CE, NOV, 980.0, 38, 0.30)
    rec = {"trade_date": "2026-10-16", "generated_at": "x", "scanned": 200, "calls": [_cand(s)], "puts": []}
    (tmp_path / "fno_screener_history.jsonl").write_text(json.dumps(rec, default=str) + "\n")
    (tmp_path / "fno_screener_latest.json").write_text(json.dumps(rec, default=str))
    o = track_pick("2026-10-16", _cand(s), [_day(date(2026, 10, 19), 1030.0, CALLS)])
    (tmp_path / "fno_screener_outcomes.json").write_text(json.dumps({o["key"]: o}, default=str))
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))

    from cloud.api.main import app
    body = TestClient(app).get("/fno-picks").json()
    pick = body["latest"]["calls"][0]
    assert pick["symbol"] == "AAA" and len(pick["spreads"]["ideas"]) == 3
    assert pick["outcome"]["sessions"] == 1 and pick["outcome"]["returns"]["1"]["stock_pct"] == pytest.approx(3.0)
    assert body["history"][0]["trade_date"] == "2026-10-16"
    assert body["stats"]["CE"]["picks"] == 1 and body["outcomes_tracked"] == 1


def test_route_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    from cloud.api.main import app
    body = TestClient(app).get("/fno-picks").json()
    assert body["latest"] is None and body["history"] == [] and body["stats"]["CE"]["picks"] == 0
