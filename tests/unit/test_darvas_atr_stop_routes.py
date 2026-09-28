"""
Darvas ATR-Stop Routes — Unit Tests
─────────────────────────────────────
GET /darvas-atr-stop/status is a read-only mirror of the executor's own files
in ~/.quantos. Covers: the real file shapes round-trip, missing/corrupt files
degrade to empty, and nothing from agent/config.yaml beyond the four
darvas_atr_stop display keys can leak into the response.
"""

import json

import pytest
from httpx import AsyncClient, ASGITransport

from cloud.api.main import app


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTOS_HOME_DIR", str(tmp_path))
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "brokers:\n  fyers:\n    credentials:\n      api_secret: SHOULD-NOT-LEAK\n"
        "darvas_atr_stop:\n  enabled: true\n  dry_run: true\n"
        "  equity_fraction: 0.09\n  starting_capital: 250000\n  universe_file: x.txt\n"
    )
    monkeypatch.setenv("QUANTOS_AGENT_CONFIG", str(cfg))
    return tmp_path


async def _get():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.get("/darvas-atr-stop/status")


@pytest.mark.asyncio
async def test_empty_home_returns_empty_sections():
    r = await _get()
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] is None
    assert body["open_positions"] == []
    assert body["closed_trades"] == []
    assert body["settings"] == {"enabled": True, "dry_run": True,
                                "equity_fraction": 0.09, "starting_capital": 250000}
    assert "SHOULD-NOT-LEAK" not in r.text


@pytest.mark.asyncio
async def test_real_file_shapes(_isolated):
    home = _isolated
    (home / "darvas_atr_stop_plan.json").write_text(json.dumps({
        "generated_at": "2026-09-25T18:10:02+00:00", "through": "2026-09-25",
        "bars_as_of": "2026-09-25", "symbols_scanned": 500,
        "entries": [{"symbol": "ZYDUSLIFE", "initial_stop": 1124.27, "target": 1527.5,
                     "box_ceiling": 1181.5, "box_width_pct": 41.4,
                     "last_close": 1203.9, "tags": []}],
        "position_actions": {},
        "failures": {"HFCL": "x", "HEG": "y"},
        "executed_on": "2026-09-28",
    }))
    (home / "darvas_atr_stop_open_positions.json").write_text(json.dumps({
        "ZYDUSLIFE": {"symbol": "ZYDUSLIFE", "quantity": 18, "entry_price": 1218.4,
                      "entry_date": "2026-09-28", "box_width_pct": 41.4,
                      "seen_ceiling": 1181.5, "current_stop": 1124.27,
                      "current_target": 1527.5, "entry_order_id": "",
                      "stop_order_id": ""},
    }))
    (home / "darvas_atr_stop_dry_run_trades.jsonl").write_text(json.dumps({
        "symbol": "ABC", "entry_timestamp": "2026-09-01", "entry_price": 100.0,
        "exit_timestamp": "2026-09-10", "exit_reason": "stop", "quantity": 10,
        "box_width_pct": 40.0, "seen_ceiling": 98.0, "boundary_price": 95.0,
        "exit_ltp": 94.8,
    }) + "\nnot json\n")

    body = (await _get()).json()
    assert body["plan"]["executed_on"] == "2026-09-28"
    assert body["plan"]["entries"][0]["symbol"] == "ZYDUSLIFE"
    assert body["plan"]["failed_symbols"] == ["HEG", "HFCL"]

    [pos] = body["open_positions"]
    assert pos["symbol"] == "ZYDUSLIFE"
    assert pos["notional"] == pytest.approx(21931.2)
    assert pos["risk_pct"] == pytest.approx(-7.73)
    assert pos["reward_pct"] == pytest.approx(25.37)
    assert "entry_order_id" not in pos

    [trade] = body["closed_trades"]          # the malformed line is skipped
    assert trade["pnl_pct"] == pytest.approx(-5.0)
    assert trade["pnl"] == pytest.approx(-50.0)


@pytest.mark.asyncio
async def test_corrupt_plan_and_missing_config_degrade(_isolated, monkeypatch):
    (_isolated / "darvas_atr_stop_plan.json").write_text("{truncated")
    monkeypatch.setenv("QUANTOS_AGENT_CONFIG", str(_isolated / "missing.yaml"))
    r = await _get()
    assert r.status_code == 200
    assert r.json()["plan"] is None
    assert r.json()["settings"] == {}
