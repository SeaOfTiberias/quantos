"""
US-01 Webhook Bridge — Unit Tests
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from cloud.api.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "correct_secret")
    payload = {
        "symbol": "RELIANCE", "action": "BUY", "price": 2950.0,
        "timeframe": "1h", "strategy": "darvas_breakout",
        "confluence_score": 85, "secret": "wrong_secret",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/webhook/tradingview", json=payload)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_low_confluence(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "70")
    payload = {
        "symbol": "TCS", "action": "BUY", "price": 3800.0,
        "timeframe": "1h", "strategy": "darvas_breakout",
        "confluence_score": 55,   # below threshold
        "secret": "",
    }
    with patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main.send_whatsapp", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/tradingview", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED_LOW_CONFLUENCE"


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signal(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "70")
    payload = {
        "symbol": "INFY", "action": "BUY", "price": 1520.0,
        "timeframe": "1h", "strategy": "darvas_breakout",
        "confluence_score": 88,
        "secret": "",
    }
    with patch("cloud.api.main.analyse_signal", new_callable=AsyncMock, return_value=82.5), \
         patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main._send_confirmation_request", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/tradingview", json=payload)
    data = r.json()
    assert r.status_code == 200
    assert data["status"] == "PENDING_CONFIRMATION"
    assert data["symbol"] == "INFY"
    assert data["confidence_score"] == 82.5
    assert data["signal_id"].startswith("SIG-")


@pytest.mark.asyncio
async def test_signal_id_format(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    payload = {
        "symbol": "HDFC", "action": "SELL", "price": 1680.0,
        "timeframe": "D", "strategy": "darvas_breakout",
        "confluence_score": 91, "secret": "",
    }
    with patch("cloud.api.main.analyse_signal", new_callable=AsyncMock, return_value=75.0), \
         patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main._send_confirmation_request", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/webhook/tradingview", json=payload)
    signal_id = r.json()["signal_id"]
    # Format: SIG-DARV-XXXXXXXX
    assert signal_id.startswith("SIG-DARV-")
    assert len(signal_id) == 17
