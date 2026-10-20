"""GET /spreads, POST /spreads/level (cloud/api/spreads_routes.py) and GET /auth/fyers/status."""

import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from cloud.api.spreads_routes import IST


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    from cloud.api.main import app
    return TestClient(app)


def test_empty(tmp_path, monkeypatch):
    body = _client(tmp_path, monkeypatch).get("/spreads").json()
    assert body["spreads"] == [] and body["alerts"] == [] and body["uncovered"] == []
    assert body["watcher"]["alive"] is False


def test_reads_watcher_files(tmp_path, monkeypatch):
    now = datetime.now(IST)
    key = "TECMAH|2026-10-27|call|1740|1800"
    (tmp_path / "spread_watcher_state.json").write_text(json.dumps({key: {
        "key": key, "entry": 26.3, "qty": 600, "last_pnl": 3300.0, "sent": ["trail_armed"],
        "view": {"stock_code": "TECMAH", "kind": "bull call", "long_strike": 1740.0, "short_strike": 1800.0,
                 "long_quote": [53.75, 54.55, 54.0], "short_quote": [21.7, 21.95, 21.8]}}}))
    (tmp_path / "spread_watcher_heartbeat.json").write_text(json.dumps({
        "at": now.isoformat(timespec="seconds"), "session_ok": True, "spreads": 1, "rules": {"stock_trail_pct": 0.8},
        "naked": [{"stock_code": "INFTEC", "label": "1500 CE", "expiry": "2026-10-27", "qty": 400, "avg_price": 12.0}]}))
    (tmp_path / "spread_watcher_alerts.jsonl").write_text(
        "\n".join(json.dumps({"at": now.isoformat(), "text": f"alert {i}"}) for i in range(3)) + "\nnot json\n")
    body = _client(tmp_path, monkeypatch).get("/spreads").json()
    s = body["spreads"][0]
    assert s["stock_code"] == "TECMAH" and s["last_pnl"] == 3300.0 and s["long_quote"][0] == 53.75 and "view" not in s
    assert body["watcher"]["alive"] and body["watcher"]["session_ok"]
    assert body["uncovered"][0]["stock_code"] == "INFTEC"
    assert [a["text"] for a in body["alerts"]] == ["alert 2", "alert 1", "alert 0"]       # newest first


def test_stale_heartbeat_hides_uncovered(tmp_path, monkeypatch):
    old = (datetime.now(IST) - timedelta(minutes=10)).isoformat(timespec="seconds")
    (tmp_path / "spread_watcher_heartbeat.json").write_text(json.dumps({"at": old, "naked": [{"stock_code": "X"}]}))
    body = _client(tmp_path, monkeypatch).get("/spreads").json()
    assert body["watcher"]["alive"] is False and body["uncovered"] == []


def test_set_and_clear_level(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.post("/spreads/level", json={"stock_code": "tecmah", "level": 1775}).json()["levels"] == {"TECMAH": 1775}
    assert json.loads((tmp_path / "spread_watcher_levels.json").read_text()) == {"TECMAH": 1775}
    assert c.post("/spreads/level", json={"stock_code": "TECMAH", "level": None}).json()["levels"] == {}
    assert c.post("/spreads/level", json={"stock_code": "../etc", "level": 1}).status_code == 400
    assert c.post("/spreads/level", json={"stock_code": "TECMAH", "level": -5}).status_code == 400


def test_fyers_status(tmp_path, monkeypatch):
    import cloud.api.fyers_auth_routes as fr
    c = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(fr, "TOKEN_PATH", tmp_path / "fyers_token")
    assert c.get("/auth/fyers/status").json() == {"refreshed_today": False, "at": None}
    (tmp_path / "fyers_token").write_text("x")
    assert c.get("/auth/fyers/status").json()["refreshed_today"] is True
