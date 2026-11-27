"""Strategy Lab: the registry's integrity, the stats/curve arithmetic, the bars reader and the routes."""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloud.api import lab_routes as lab

REPO = Path(__file__).resolve().parents[2]
STATUSES = {"FAIL", "PAPER", "SHELVED", "CLOSED", "PENDING"}
VERIF = {"reproduced", "reproduced_with_differences", "corrected", "cannot_reproduce", "saved_at_run", "not_attempted"}
REQUIRED = ("id", "name", "family", "tested", "status", "rationale", "test", "result", "why", "metrics", "docs", "trades")


def test_registry_is_complete_and_its_links_exist():
    reg = lab.registry()
    ids = [s["id"] for s in reg]
    assert len(ids) == len(set(ids)) and len(ids) >= 30
    for s in reg:
        missing = [k for k in REQUIRED if k not in s]
        assert not missing, (s.get("id"), missing)
        assert s["status"] in STATUSES, s["id"]
        assert s["docs"], s["id"]
        for d in s["docs"]:
            assert (REPO / d).exists(), (s["id"], d)
        if s["trades"]:
            assert (lab.LAB / "trades" / f"{s['trades']}.csv").exists(), s["id"]
            assert s.get("pnl_unit") in ("inr", "bps", "pct"), s["id"]
        assert (s.get("verification") or {}).get("status") in VERIF, s["id"]
    tested = [s["tested"] for s in reg]
    assert tested == sorted(tested, reverse=True)                          # newest first


def _rows(nets, syms=None):
    syms = syms or ["A"] * len(nets)
    return [{"exit_time": f"2024-01-{i + 1:02d}", "net": x, "chart_symbol": s} for i, (x, s) in enumerate(zip(nets, syms))]


def test_stats_arithmetic():
    s = lab.stats(_rows([10.0, -5.0, 20.0, -15.0]))
    assert s == {"n": 4, "total": 10.0, "mean": 2.5, "win_rate": 0.5, "profit_factor": 1.5, "max_drawdown": -15.0}
    assert lab.stats([{"net": None}]) == {"n": 1}


def test_equity_one_curve_per_symbol_only_when_few():
    two = lab.equity(_rows([1.0, 2.0, 3.0], ["NIFTY", "BANKNIFTY", "NIFTY"]))
    assert [c["name"] for c in two] == ["BANKNIFTY", "NIFTY"]
    assert two[1]["points"] == [{"t": "2024-01-01", "v": 1.0}, {"t": "2024-01-03", "v": 4.0}]
    many = lab.equity(_rows([1.0] * 5, ["A", "B", "C", "D", "E"]))
    assert len(many) == 1 and many[0]["name"] == "All trades" and many[0]["points"][-1]["v"] == 5.0


def test_daily_bars_index_then_stock_store(tmp_path):
    (tmp_path / "index_bars").mkdir()
    (tmp_path / "index_bars" / "NIFTY.csv").write_text(
        "date,o,h,l,c,vol,val\n2024-01-01,1,2,0.5,1.5,1,1\n2024-01-02,2,3,1,2.5,1,1\n2024-02-01,9,9,9,9,1,1\n")
    (tmp_path / "l1_store" / "bars").mkdir(parents=True)
    (tmp_path / "l1_store" / "bars" / "TCS.csv").write_text("date,series,o,h,l,c,vol,val\n")
    b = lab.daily_bars("nifty", date(2024, 1, 1), date(2024, 1, 31), tmp_path)
    assert [x["time"] for x in b] == ["2024-01-01", "2024-01-02"] and b[1]["close"] == 2.5
    import pandas as pd
    seen = {}

    def frame(sym, home, as_of):
        seen["as_of"] = as_of
        return pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                             "series": ["EQ", "XX", "EQ"], "o": [10, 1, 11], "h": [11, 1, 12], "l": [9, 1, 10], "c": [10.5, 1, 11.5]})
    t = lab.daily_bars("TCS", date(2024, 1, 1), date(2024, 1, 31), tmp_path, as_of=date(2026, 7, 19), frame_fn=frame)
    assert [x["time"] for x in t] == ["2024-01-01", "2024-01-03"] and seen["as_of"] == date(2026, 7, 19)
    with pytest.raises(lab.HTTPException):
        lab.daily_bars("NOPE", date(2024, 1, 1), date(2024, 1, 31), tmp_path)


def test_stock_frame_adjusts_only_for_actions_up_to_as_of(monkeypatch, tmp_path):
    calls = {}

    class FakeStore:
        def __init__(self, root):
            pass

        def actions(self):
            return {"X": [{"ex": "2024-06-01", "factor": 0.5}, {"ex": "2026-11-04", "factor": 0.5}]}

        def adjusted(self, sym, actions):
            calls["acts"] = actions[sym]
            return "df", []
    import core.market_map.l1_store as l1
    monkeypatch.setattr(l1, "Store", FakeStore)
    lab._stock_frame("X", tmp_path, date(2026, 7, 19))
    assert [a["ex"] for a in calls["acts"]] == ["2024-06-01"]
    lab._stock_frame("X", tmp_path, None)
    assert len(calls["acts"]) == 2


def test_routes(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    (root / "trades").mkdir(parents=True)
    (root / "strategies.json").write_text(json.dumps({"strategies": [
        {"id": "x", "name": "X", "family": "F", "status": "FAIL", "tested": "2026-01-01", "trades": "x", "pnl_unit": "bps"},
        {"id": "y", "name": "Y", "family": "F", "status": "SHELVED", "tested": "2025-01-01", "trades": None}]}))
    (root / "trades" / "x.csv").write_text(
        "trade_id,symbol,side,entry_time,entry_price,exit_time,exit_price,qty,gross,cost,net,chart_symbol,note\n"
        "1,N,long,2024-01-01 15:30,100,2024-01-02 09:15,101,1,10,3,7,NIFTY,\n")
    monkeypatch.setattr(lab, "LAB", root)
    monkeypatch.setattr(lab, "registry", lambda r=root: json.loads((root / "strategies.json").read_text())["strategies"])
    monkeypatch.setattr(lab, "_trades_path", lambda s, r=root: (root / "trades" / f"{s['trades']}.csv") if s.get("trades") else None)
    app = FastAPI()
    app.include_router(lab.router)
    c = TestClient(app)
    ls = c.get("/lab/strategies").json()["strategies"]
    assert [(s["id"], s["has_trades"]) for s in ls] == [("x", True), ("y", False)]
    d = c.get("/lab/strategies/x").json()
    assert d["stats"]["total"] == 7.0 and d["equity"][0]["points"] == [{"t": "2024-01-02", "v": 7.0}]
    assert c.get("/lab/strategies/y").json()["trade_rows"] == []
    assert c.get("/lab/strategies/nope").status_code == 404
    r = c.get("/lab/strategies/x/trades.csv")
    assert r.status_code == 200 and r.text.startswith("trade_id,")
    assert c.get("/lab/strategies/y/trades.csv").status_code == 404
    assert c.get("/lab/bars", params={"symbol": "N", "start": "bad", "end": "2024-01-01"}).status_code == 400
