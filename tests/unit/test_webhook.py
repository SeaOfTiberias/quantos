"""
US-01 Webhook Bridge — Unit Tests

Covers the hardened webhook contract (Sprint 4 / S4-3):
fail-closed secret, replay guard, and the same-day dedup guard
including EXECUTED / BLOCKED_EVENT_RISK statuses.
"""

import time
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from cloud.api.main import app
from cloud.api.db import get_db, Signal

SECRET = "test_webhook_secret"


def _payload(symbol: str, **overrides) -> dict:
    p = {
        "symbol": symbol, "action": "BUY", "price": 2950.0,
        "timeframe": "1h", "strategy": "darvas_breakout",
        "confluence_score": 85, "secret": SECRET,
        "timestamp": time.time(),
    }
    p.update(overrides)
    return p


async def _post(payload: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/webhook/tradingview", json=payload)


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Secret validation (fail closed) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    r = await _post(_payload("RELIANCE", secret="wrong_secret"))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_webhook_fails_closed_when_secret_unset(monkeypatch):
    """P0-1: a missing WEBHOOK_SECRET must disable the endpoint entirely,
    not silently skip the check."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    r = await _post(_payload("RELIANCE"))
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_webhook_fails_closed_when_secret_empty(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    r = await _post(_payload("RELIANCE"))
    assert r.status_code == 503


# ── Replay guard ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_rejects_missing_timestamp(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    r = await _post(_payload("RELIANCE", timestamp=None))
    assert r.status_code == 401
    assert "timestamp" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_rejects_stale_timestamp(monkeypatch):
    """P1-11 AC: a replayed 10-minute-old payload is rejected."""
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    r = await _post(_payload("RELIANCE", timestamp=time.time() - 600))
    assert r.status_code == 401
    assert "stale" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_rejects_far_future_timestamp(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    r = await _post(_payload("RELIANCE", timestamp=time.time() + 600))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_webhook_accepts_slightly_old_timestamp(monkeypatch):
    """A payload inside the freshness window (delivery lag) still passes."""
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    payload = _payload("INFY", timestamp=time.time() - 60)
    with patch("cloud.api.main.analyse_signal", new_callable=AsyncMock, return_value=82.5), \
         patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main._send_confirmation_request", new_callable=AsyncMock):
        r = await _post(payload)
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING_CONFIRMATION"


# ── Pipeline behavior ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_rejects_low_confluence(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "70")
    payload = _payload("TCS", confluence_score=55)
    with patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main.send_telegram", new_callable=AsyncMock):
        r = await _post(payload)
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED_LOW_CONFLUENCE"


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signal(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "70")
    payload = _payload("INFY", confluence_score=88)
    with patch("cloud.api.main.analyse_signal", new_callable=AsyncMock, return_value=82.5), \
         patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main._send_confirmation_request", new_callable=AsyncMock):
        r = await _post(payload)
    data = r.json()
    assert r.status_code == 200
    assert data["status"] == "PENDING_CONFIRMATION"
    assert data["symbol"] == "INFY"
    assert data["confidence_score"] == 82.5
    assert data["signal_id"].startswith("SIG-")


@pytest.mark.asyncio
async def test_signal_id_format(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    payload = _payload("HDFC", action="SELL", confluence_score=91)
    with patch("cloud.api.main.analyse_signal", new_callable=AsyncMock, return_value=75.0), \
         patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main._send_confirmation_request", new_callable=AsyncMock):
        r = await _post(payload)
    signal_id = r.json()["signal_id"]
    # Format: SIG-DARV-XXXXXXXX
    assert signal_id.startswith("SIG-DARV-")
    assert len(signal_id) == 17


# ── Same-day dedup guard ─────────────────────────────────────────────────────

async def _seed_signal(symbol: str, signal_status: str) -> None:
    db = await get_db()
    await db.insert_signal(Signal(
        signal_id=f"SIG-TEST-{uuid.uuid4().hex[:8].upper()}",
        user_id="system", symbol=symbol, action="BUY", price=100.0,
        timeframe="1h", strategy="darvas_breakout", confluence_score=90,
        confidence_score=80.0, stop_loss=95.0, status=signal_status,
        created_at=datetime.now(timezone.utc),
    ))


@pytest.mark.parametrize("existing_status", [
    "PENDING_CONFIRMATION", "CONFIRMED", "EXECUTED", "BLOCKED_EVENT_RISK",
])
@pytest.mark.asyncio
async def test_webhook_dedup_blocks_same_day_refire(monkeypatch, existing_status):
    """P1-3 AC: a re-fired alert after execution (or block) is rejected as a
    duplicate — not just while pending/confirmed."""
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    symbol = f"DUP{uuid.uuid4().hex[:6].upper()}"  # unique per run: shared in-memory DB
    await _seed_signal(symbol, existing_status)
    with patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main.analyse_signal", new_callable=AsyncMock, return_value=80.0), \
         patch("cloud.api.main._send_confirmation_request", new_callable=AsyncMock):
        r = await _post(_payload(symbol))
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED_DUPLICATE"


@pytest.mark.parametrize("existing_status", [
    "SKIPPED", "REJECTED_LOW_CONFLUENCE", "FAILED", "CLOSED",
])
@pytest.mark.asyncio
async def test_webhook_dedup_ignores_settled_statuses(monkeypatch, existing_status):
    """A skipped/rejected/closed signal must NOT block a fresh setup on the
    same symbol later the same day."""
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    symbol = f"OK{uuid.uuid4().hex[:6].upper()}"
    await _seed_signal(symbol, existing_status)
    with patch("cloud.api.main._persist_signal", new_callable=AsyncMock), \
         patch("cloud.api.main.analyse_signal", new_callable=AsyncMock, return_value=80.0), \
         patch("cloud.api.main._send_confirmation_request", new_callable=AsyncMock):
        r = await _post(_payload(symbol))
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING_CONFIRMATION"
