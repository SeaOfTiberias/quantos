"""
US-15 Deployment — Health Endpoint Tests
"""

import pytest
from httpx import AsyncClient, ASGITransport

from cloud.api.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_readiness_returns_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ready", "degraded")
    assert "checks" in data
    assert "claude_api_key" in data["checks"]
    assert "whatsapp" in data["checks"]


@pytest.mark.asyncio
async def test_readiness_degraded_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["checks"]["claude_api_key"] is False


@pytest.mark.asyncio
async def test_status_endpoint_structure():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "QuantOS Cloud API"
    assert "uptime" in data
    assert "market" in data
    assert data["market"] in ("OPEN", "CLOSED")
    assert "config" in data


@pytest.mark.asyncio
async def test_status_config_reflects_env(monkeypatch):
    monkeypatch.setenv("MIN_CONFLUENCE_SCORE", "75")
    monkeypatch.setenv("REGIME_CACHE_TTL", "600")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/status")
    data = r.json()
    assert data["config"]["min_confluence_score"] == 75.0
    assert data["config"]["regime_cache_ttl"] == 600


@pytest.mark.asyncio
async def test_uptime_increases():
    """Two consecutive calls should show increasing uptime_seconds."""
    import asyncio
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/status")
        await asyncio.sleep(0.05)
        r2 = await client.get("/status")
    assert r2.json()["uptime_seconds"] >= r1.json()["uptime_seconds"]
