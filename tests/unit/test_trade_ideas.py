"""Trade-idea log: core/ideas/log.py scoring, scripts/trade_ideas.py storage, GET /ideas."""

import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from core.ideas.log import (IST, IdeaError, entry_cost, evaluate, exit_value, intrinsic, make_idea,
                            option_symbol, scoreboard)

NOW = datetime(2026, 10, 21, 10, 0, tzinfo=IST)
NESTLE = {"symbol": "nestleind", "view": "bear", "action": "enter_if",
          "trigger": {"kind": "close_below", "level": 1238},
          "cancel": {"kind": "close_above", "level": 1276},
          "stop": {"kind": "close_above", "level": 1290},
          "structure": {"kind": "bear_put", "expiry": "2026-11-23", "long_strike": 1250, "short_strike": 1200, "lot": 500},
          "spot": 1236.6, "debit": 20.4}


def _mark(d, lb, la, sb, sa, spot=None):
    return {"date": d, "spot": spot, "long_bid": lb, "long_ask": la, "short_bid": sb, "short_ask": sa}


def test_make_idea_normalises_and_ids():
    i = make_idea(NESTLE, now=NOW)
    assert i["symbol"] == "NESTLEIND" and i["id"] == "2026-10-21-NESTLEIND-bear_put-1250-1200"
    assert i["created_at"].startswith("2026-10-21T10:00") and i["marks"] == [] and i["source"] == "claude"


@pytest.mark.parametrize("bad", [
    {"action": "maybe"}, {"view": "up"}, {"trigger": None}, {"symbol": "../x"},
    {"structure": {**NESTLE["structure"], "kind": "iron_fly"}},
    {"trigger": {"kind": "close_between", "low": 10, "high": 5}},
])
def test_make_idea_rejects(bad):
    with pytest.raises(IdeaError):
        make_idea({**NESTLE, **bad}, now=NOW)


def test_intrinsic_and_quote_math():
    assert intrinsic("bear_put", 1250, 1200, 1180) == 50
    assert intrinsic("bear_put", 1250, 1200, 1230) == 20
    assert intrinsic("bull_call", 680, 720, 700) == 20
    assert intrinsic("bull_call", 680, 720, 650) == 0
    m = _mark("2026-10-21", 35.25, 36.05, 15.65, 15.9)
    assert entry_cost(m) == pytest.approx(20.4) and exit_value(m) == pytest.approx(19.35)
    assert option_symbol("NESTLEIND", "2026-11-23", 1250.0, "PE") == "NSE:NESTLEIND26NOV1250PE"


def test_watching_until_trigger_then_marked_pnl():
    i = make_idea(NESTLE, now=NOW)
    ev = evaluate(i, [("2026-10-21", 1241.0)], today=date(2026, 10, 21))
    assert ev["status"] == "watching" and ev["trigger_date"] is None
    i["marks"] = [_mark("2026-10-22", 35.0, 36.0, 15.5, 16.0), _mark("2026-10-23", 44.0, 45.0, 19.0, 19.5)]
    ev = evaluate(i, [("2026-10-21", 1241.0), ("2026-10-22", 1235.0), ("2026-10-23", 1222.0)], today=date(2026, 10, 23))
    assert ev["status"] == "triggered" and ev["trigger_date"] == "2026-10-22" and ev["entry_spot"] == 1235.0
    assert ev["entry_cost"] == pytest.approx(20.5)            # 36.0 ask - 15.5 bid
    assert ev["value"] == pytest.approx(24.5)                 # 44.0 bid - 19.5 ask
    assert ev["pnl"] == pytest.approx(2000) and ev["pnl_pct"] == pytest.approx(19.5, abs=0.1)


def test_cancel_before_trigger():
    i = make_idea(NESTLE, now=NOW)
    ev = evaluate(i, [("2026-10-21", 1250.0), ("2026-10-22", 1280.0), ("2026-10-23", 1230.0)], today=date(2026, 10, 23))
    assert ev["status"] == "cancelled" and ev["trigger_date"] is None


def test_stop_after_trigger_exits_at_that_mark():
    i = make_idea(NESTLE, now=NOW)
    i["marks"] = [_mark("2026-10-21", 35.0, 36.0, 15.5, 16.0), _mark("2026-10-28", 9.0, 9.5, 3.0, 3.4)]
    closes = [("2026-10-21", 1236.0), ("2026-10-27", 1270.0), ("2026-10-28", 1295.0), ("2026-10-29", 1200.0)]
    ev = evaluate(i, closes, today=date(2026, 10, 29))
    assert ev["status"] == "exited" and ev["exit_reason"] == "stop level hit" and ev["exit_date"] == "2026-10-28"
    assert ev["pnl"] == pytest.approx((5.6 - 20.5) * 500)


def test_expiry_settles_at_intrinsic():
    i = make_idea({**NESTLE, "action": "enter_now", "trigger": None, "stop": None}, now=NOW)
    closes = [("2026-10-21", 1236.0), ("2026-11-23", 1190.0), ("2026-11-24", 1300.0)]
    ev = evaluate(i, closes, today=date(2026, 11, 25))
    assert ev["exit_reason"] == "expiry" and ev["value"] == 50 and ev["pnl"] == pytest.approx((50 - 20.4) * 500)


def test_avoid_is_scored_as_counterfactual():
    techm = {"symbol": "TECHM", "view": "bull", "action": "avoid", "spot": 1816.7, "debit": 29.55,
             "structure": {"kind": "bull_call", "expiry": "2026-11-23", "long_strike": 1820, "short_strike": 1900, "lot": 600}}
    i = make_idea(techm, now=NOW)
    closes = [("2026-10-21", 1816.7)] + [(f"2026-10-{22 + k}", 1816.7 + 10 * (k + 1)) for k in range(6)]
    ev = evaluate(i, closes, today=date(2026, 10, 27))
    assert ev["status"] == "avoided" and ev["fwd"][5] == pytest.approx(100 * 50 / 1816.7, abs=0.01)
    assert ev["entry_cost"] == pytest.approx(29.55)          # creation-day debit stands in for the mark


def test_scoreboard_counts():
    a = make_idea(NESTLE, now=NOW)
    b = make_idea({**NESTLE, "symbol": "DLF", "action": "avoid"}, now=NOW)
    sb = scoreboard([(a, {"trigger_date": "2026-10-22", "pnl": 2000}), (b, {"trigger_date": "2026-10-21", "pnl": -500})])
    assert sb["enter_if"] == {"ideas": 1, "triggered": 1, "scored": 1, "pnl": 2000, "wins": 1, "taken": 0, "actual_pnl": 0}
    assert sb["avoid"]["wins"] == 0


def test_cli_storage_and_route(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    from scripts import trade_ideas as ti
    assert ti.main(["add", "--json", json.dumps(NESTLE)]) == 0
    assert ti.main(["add", "--json", json.dumps(NESTLE)]) == 0          # same day, same legs -> suffixed id
    ids = [i["id"] for i in ti.load()]
    assert len(set(ids)) == 2
    assert ti.main(["take", ids[0], "--debit", "20.5"]) == 0
    assert ti.main(["close", ids[0], "--value", "30.5"]) == 0
    assert ti.load()[0]["closed"]["pnl"] == pytest.approx(5000)
    assert ti.main(["add", "--json", json.dumps({**NESTLE, "action": "nope"})]) == 1
    from cloud.api.main import app
    body = TestClient(app).get("/ideas").json()
    assert len(body["ideas"]) == 2 and body["scoreboard"]["enter_if"]["ideas"] == 2


def test_closed_trade_keeps_paper_and_actual():
    i = make_idea({**NESTLE, "action": "enter_now", "trigger": None, "stop": None}, now=NOW)
    i["taken"] = {"debit": 20.4, "lots": 1}
    closes = [("2026-10-21", 1236.0), ("2026-11-23", 1190.0)]
    assert evaluate(i, closes, today=date(2026, 10, 22))["status"] == "taken"
    i["closed"] = {"value": 24.0, "pnl": 1800}
    ev = evaluate(i, closes, today=date(2026, 11, 25))
    assert ev["status"] == "closed" and ev["actual_pnl"] == 1800 and ev["pnl"] == pytest.approx((50 - 20.4) * 500)
    assert scoreboard([(i, ev)])["enter_now"]["actual_pnl"] == 1800


def test_structure_route_validates_and_serialises(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    import cloud.api.ideas_routes as r
    from core.ideas.structure import Candidate
    from cloud.api.main import app
    c = TestClient(app)
    body = {"symbol": "nestleind", "direction": "bear", "target": 1180, "stop": 1232, "days": 5}
    assert c.post("/ideas/structure", json={**body, "symbol": "../x"}).status_code == 400
    assert c.post("/ideas/structure", json={**body, "direction": "sideways"}).status_code == 422
    seen = {}

    def fake_run(req):
        seen["sym"] = req.symbol
        cand = Candidate("bear put 1200/1120", date(2026, 11, 23), [(1, None, 1200, "PE")], 19.65, 3912.0, -3690.0, 9825.0, be_p=0.48)
        return {"symbol": req.symbol, "best": [r._row(cand)], "top": [r._row(cand)]}
    monkeypatch.setattr(r, "_run", fake_run)
    out = c.post("/ideas/structure", json=body).json()
    assert seen["sym"] == "NESTLEIND" and out["best"][0]["family"] == "debit" and out["best"][0]["expiry"] == "2026-11-23"
    assert "legs" not in out["best"][0]
