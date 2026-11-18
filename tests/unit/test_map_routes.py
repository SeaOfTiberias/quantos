"""cloud/api/map_routes.py -- GET /map/{symbol}, POST /map/{symbol}/check; a synthetic v3 map, no Fyers."""

import pytest
from fastapi.testclient import TestClient

import core.market_map.read as mr


def zone(low, high, why, strong=True):
    return {"low": low, "high": high, "mid": round((low + high) / 2, 2), "strong": strong,
            "families": ["structure"], "tfs": ["W"], "n": 1, "why": why}


# The 11-02 HDFCBANK shape: a strong 688.77-693 zone above the 10-23 short at 678, a weak one at 672.
MAP = {"symbol": "HDFCBANK", "built_for": "2026-11-02", "close": 692.8, "atr": 13.96, "zone_width": 4.19,
       "status": "untested", "map": mr.MAP_NAME,
       "zones": [zone(672, 672, "W EQL", strong=False), zone(688.77, 693, "W bear OB"),
                 zone(712.13, 718.25, "M supply base")]}


@pytest.fixture
def client(monkeypatch):
    def fake(sym, as_of=None, **kw):
        m = dict(MAP) if sym == "HDFCBANK" else {"symbol": sym, "error": f"{sym} is not in the L1 store"}
        return (m, {"error": "synthetic"}) if kw.get("with_l1") else m
    monkeypatch.setattr(mr, "current_map", fake)
    import cloud.api.map_routes as routes
    monkeypatch.setattr(routes, "_live", lambda sym: (None, None))            # Fyers down: read at the map's close
    from cloud.api.main import app
    return TestClient(app)


def test_get_map_draws_the_whole_ladder_with_its_status(client):
    out = client.get("/map/hdfcbank").json()
    assert out["symbol"] == "HDFCBANK" and out["price"] == 692.8 and out["price_source"] == "map close"
    assert [z["range"] for z in out["zones"]] == ["712.13–718.25", "688.77–693", "672"]     # high to low
    assert [z["strong"] for z in out["zones"]] == [True, True, False]
    assert {z["test"] for z in out["zones"]} == {"untested"} and out["status"] == "untested"
    assert out["inside"]["range"] == "688.77–693"
    assert [(z["where"], z["distance"]) for z in out["zones"]] == [("above", 19.33), ("inside", 0), ("below", 20.8)]
    assert out["zones"][0]["distance_atr"] == 1.38 and out["zones"][2]["distance_pct"] == 3.0
    assert out["layers"] is not None and out["zone_width"] == 4.19 and out["source"] == "l1"
    assert "fallback" not in out


def test_get_map_reads_at_the_live_price_when_fyers_answers(client, monkeypatch):
    import cloud.api.map_routes as routes
    monkeypatch.setattr(routes, "_live", lambda sym: (None, 700.0))
    out = client.get("/map/HDFCBANK").json()
    assert out["price"] == 700.0 and out["price_source"] == "live" and out["inside"] is None


def test_the_10_23_short_has_its_stop_inside_the_688_77_693_zone(client):
    out = client.post("/map/HDFCBANK/check", json={"side": "short", "entry": 678, "stop": 690, "target": 660}).json()
    t = out["trade"]
    assert out["price"] == 678 and out["price_source"] == "entry"
    assert t["r"] == 12 and t["target_r"] == 1.5 and t["stop_in_zone"]["range"] == "688.77–693"
    assert t["flags"] == ["stop 690 is inside the strong zone 688.77–693"]
    assert t["first_obstacle"] is None                                           # nothing strong below


def test_check_validates_the_trade(client):
    assert client.post("/map/../x/check", json={"side": "long", "entry": 1, "stop": 0.5}).status_code in (400, 404)
    assert client.post("/map/A$B/check", json={"side": "long", "entry": 1, "stop": 0.5}).status_code == 400
    assert client.post("/map/HDFCBANK/check", json={"side": "flat", "entry": 1, "stop": 0.5}).status_code == 422
    assert client.post("/map/HDFCBANK/check", json={"side": "short", "entry": 678, "stop": 670}).status_code == 400
    assert client.post("/map/HDFCBANK/check", json={"side": "long", "entry": 678, "stop": 670, "target": 660}).status_code == 400
    ok = client.post("/map/HDFCBANK/check", json={"side": "long", "entry": 678, "stop": 670}).json()
    assert ok["trade"]["target"] is None and ok["trade"]["target_r"] is None


def test_no_map_is_a_502_not_a_crash(client):
    r = client.get("/map/TCS")
    assert r.status_code == 502 and "TCS" in r.json()["detail"]
